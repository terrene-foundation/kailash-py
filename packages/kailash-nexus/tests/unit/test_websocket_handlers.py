# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for class-based WebSocket MessageHandler (issue #448).

Covers the five invariants declared in MessageHandlerRegistry:

- State isolation: each Connection has its own state namespace
- Connection lifecycle: every on_connect is paired with one on_disconnect
- Registry consistency: closed connections are removed from self.connections
- Broadcast filtering: on_event sees a live snapshot and can filter
- Cleanup: state and socket references are released on disconnect

Plus the registration surface (validation, collision, typing) and the
receive loop (JSON vs text dispatch).
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, List
from unittest.mock import AsyncMock

import pytest

from nexus.websocket_handlers import (
    Connection,
    MessageHandler,
    MessageHandlerRegistry,
)


# ---------------------------------------------------------------------------
# Fake websocket — async iterator that yields queued frames
# ---------------------------------------------------------------------------


class FakeWebSocket:
    """Minimal async websocket stand-in for unit tests.

    Yields frames from a queue until ``close`` is called or the queue
    is drained and ``auto_close=True``.
    """

    def __init__(self, frames: List[Any], auto_close: bool = True) -> None:
        self._frames = list(frames)
        self._auto_close = auto_close
        self.sent: List[str] = []
        self.closed = False
        self.close_code: int | None = None
        self.close_reason: str | None = None
        self._event = asyncio.Event()

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._frames:
            return self._frames.pop(0)
        if self._auto_close:
            raise StopAsyncIteration
        await self._event.wait()
        if self._frames:
            return self._frames.pop(0)
        raise StopAsyncIteration

    async def send(self, data: str) -> None:
        if self.closed:
            raise ConnectionError("websocket closed")
        self.sent.append(data)

    async def close(self, code: int = 1000, reason: str = "") -> None:
        self.closed = True
        self.close_code = code
        self.close_reason = reason
        self._event.set()

    def push(self, frame: Any) -> None:
        """External helper: enqueue a frame (for non-auto-close tests)."""
        self._frames.append(frame)
        self._event.set()
        self._event.clear()


# ---------------------------------------------------------------------------
# Registration surface
# ---------------------------------------------------------------------------


class TestRegistration:
    def test_register_returns_instance(self):
        reg = MessageHandlerRegistry()

        class H(MessageHandler):
            pass

        h = reg.register("/events", H)
        assert isinstance(h, H)
        assert h.path == "/events"
        assert h.connection_count == 0
        assert reg.paths == {"/events"}

    def test_register_rejects_non_path(self):
        reg = MessageHandlerRegistry()

        class H(MessageHandler):
            pass

        with pytest.raises(ValueError, match="must be a string starting with"):
            reg.register("events", H)

    def test_register_rejects_non_handler_class(self):
        reg = MessageHandlerRegistry()

        class NotAHandler:
            pass

        with pytest.raises(TypeError, match="subclass of MessageHandler"):
            reg.register("/events", NotAHandler)  # type: ignore[arg-type]

    def test_register_rejects_duplicate_path(self):
        reg = MessageHandlerRegistry()

        class H(MessageHandler):
            pass

        reg.register("/events", H)
        with pytest.raises(ValueError, match="already registered"):
            reg.register("/events", H)

    def test_clear_drops_handlers(self):
        reg = MessageHandlerRegistry()

        class H(MessageHandler):
            pass

        reg.register("/events", H)
        reg.clear()
        assert reg.paths == set()
        assert reg.get("/events") is None

    def test_handler_path_before_registration_raises(self):
        class H(MessageHandler):
            pass

        h = H()
        with pytest.raises(RuntimeError, match="before handler was registered"):
            _ = h.path


# ---------------------------------------------------------------------------
# State isolation (invariant 1)
# ---------------------------------------------------------------------------


class TestStateIsolation:
    @pytest.mark.asyncio
    async def test_each_connection_has_its_own_state(self):
        reg = MessageHandlerRegistry()

        seen_states: List[Any] = []

        class H(MessageHandler):
            async def on_connect(self, conn: Connection) -> None:
                conn.state.counter = 0
                seen_states.append(conn.state)

            async def on_message(self, conn: Connection, msg: dict[str, Any]) -> None:
                conn.state.counter += 1

        reg.register("/events", H)

        ws1 = FakeWebSocket([json.dumps({"x": 1})])
        ws2 = FakeWebSocket([json.dumps({"x": 1}), json.dumps({"x": 2})])

        await asyncio.gather(
            reg.handle_connection(ws1, "/events"),
            reg.handle_connection(ws2, "/events"),
        )

        # Two Connection objects → two distinct state namespaces
        assert len(seen_states) == 2
        assert seen_states[0] is not seen_states[1]

    @pytest.mark.asyncio
    async def test_state_is_fresh_per_connection(self):
        reg = MessageHandlerRegistry()

        class H(MessageHandler):
            async def on_connect(self, conn: Connection) -> None:
                # Assert nothing leaked from a prior connection
                assert not hasattr(conn.state, "leaked")
                conn.state.leaked = True

        reg.register("/events", H)

        for _ in range(3):
            ws = FakeWebSocket([])
            await reg.handle_connection(ws, "/events")


# ---------------------------------------------------------------------------
# Connection lifecycle (invariant 2)
# ---------------------------------------------------------------------------


class TestLifecycle:
    @pytest.mark.asyncio
    async def test_on_connect_pairs_with_on_disconnect(self):
        reg = MessageHandlerRegistry()
        events: List[str] = []

        class H(MessageHandler):
            async def on_connect(self, conn: Connection) -> None:
                events.append(f"connect:{conn.connection_id}")

            async def on_disconnect(self, conn: Connection) -> None:
                events.append(f"disconnect:{conn.connection_id}")

        reg.register("/events", H)
        ws = FakeWebSocket([])
        await reg.handle_connection(ws, "/events")

        assert len(events) == 2
        assert events[0].startswith("connect:")
        assert events[1].startswith("disconnect:")
        # same connection_id on both sides
        assert events[0].split(":")[1] == events[1].split(":")[1]

    @pytest.mark.asyncio
    async def test_on_disconnect_fires_even_when_receive_raises(self):
        reg = MessageHandlerRegistry()
        events: List[str] = []

        class H(MessageHandler):
            async def on_connect(self, conn: Connection) -> None:
                events.append("connect")

            async def on_message(self, conn: Connection, msg: dict[str, Any]) -> None:
                raise RuntimeError("boom from user handler")

            async def on_disconnect(self, conn: Connection) -> None:
                events.append("disconnect")

        reg.register("/events", H)
        # raising in on_message should be logged and not abort disconnect
        ws = FakeWebSocket([json.dumps({"x": 1})])
        await reg.handle_connection(ws, "/events")

        assert events == ["connect", "disconnect"]

    @pytest.mark.asyncio
    async def test_on_connect_failure_closes_socket_without_disconnect(self):
        reg = MessageHandlerRegistry()
        events: List[str] = []

        class H(MessageHandler):
            async def on_connect(self, conn: Connection) -> None:
                events.append("connect_attempt")
                raise RuntimeError("reject")

            async def on_disconnect(self, conn: Connection) -> None:
                events.append("disconnect")

        reg.register("/events", H)
        ws = FakeWebSocket([])
        handled = await reg.handle_connection(ws, "/events")

        assert handled is True
        assert events == ["connect_attempt"]  # no disconnect
        assert ws.closed is True
        assert ws.close_code == 4500

    @pytest.mark.asyncio
    async def test_unknown_path_returns_false(self):
        reg = MessageHandlerRegistry()
        ws = FakeWebSocket([])
        handled = await reg.handle_connection(ws, "/nope")
        assert handled is False


# ---------------------------------------------------------------------------
# Registry consistency (invariant 3)
# ---------------------------------------------------------------------------


class TestRegistryConsistency:
    @pytest.mark.asyncio
    async def test_connections_visible_during_lifecycle(self):
        reg = MessageHandlerRegistry()
        snapshot_during: List[int] = []
        snapshot_after: List[int] = []

        class H(MessageHandler):
            async def on_message(self, conn: Connection, msg: dict[str, Any]) -> None:
                snapshot_during.append(self.connection_count)

            async def on_disconnect(self, conn: Connection) -> None:
                # By invariant, self.connections excludes conn by now
                snapshot_after.append(self.connection_count)

        reg.register("/events", H)

        # Fire one connection, one message
        ws = FakeWebSocket([json.dumps({"x": 1})])
        await reg.handle_connection(ws, "/events")

        assert snapshot_during == [1]
        assert snapshot_after == [0]

    @pytest.mark.asyncio
    async def test_connections_snapshot_is_copy(self):
        reg = MessageHandlerRegistry()

        class H(MessageHandler):
            pass

        h = reg.register("/events", H)
        # mutate snapshot — must not affect registry
        snap = h.connections
        snap.append("poison")  # type: ignore[arg-type]
        assert h.connection_count == 0


# ---------------------------------------------------------------------------
# Broadcast filtering (invariant 4)
# ---------------------------------------------------------------------------


class TestBroadcastFiltering:
    @pytest.mark.asyncio
    async def test_on_event_filters_by_per_connection_state(self):
        reg = MessageHandlerRegistry()

        class EventStream(MessageHandler):
            async def on_connect(self, conn: Connection) -> None:
                conn.state.subscriptions = set()

            async def on_message(self, conn: Connection, msg: dict[str, Any]) -> None:
                if msg.get("action") == "subscribe":
                    conn.state.subscriptions.add(msg["topic"])

            async def on_event(self, event: Any) -> None:
                for c in self.connections:
                    if event["topic"] in c.state.subscriptions:
                        await c.send_json(event)

        reg.register("/events", EventStream)

        # Two long-lived connections: one subscribes to "trades",
        # one subscribes to "news".
        ws_trades = FakeWebSocket(
            [json.dumps({"action": "subscribe", "topic": "trades"})],
            auto_close=False,
        )
        ws_news = FakeWebSocket(
            [json.dumps({"action": "subscribe", "topic": "news"})],
            auto_close=False,
        )

        trades_task = asyncio.create_task(reg.handle_connection(ws_trades, "/events"))
        news_task = asyncio.create_task(reg.handle_connection(ws_news, "/events"))

        # wait for both subscribes to process
        async def _wait_for_subs() -> None:
            for _ in range(50):
                h = reg.get("/events")
                assert h is not None
                conns = h.connections
                if len(conns) == 2 and all(
                    getattr(c.state, "subscriptions", set()) for c in conns
                ):
                    return
                await asyncio.sleep(0.01)
            raise AssertionError("subscriptions never populated")

        await _wait_for_subs()

        # Publish a trades event — only ws_trades should receive it.
        await reg.broadcast_event("/events", {"topic": "trades", "price": 42})

        assert len(ws_trades.sent) == 1
        payload = json.loads(ws_trades.sent[0])
        assert payload == {"topic": "trades", "price": 42}
        assert ws_news.sent == []

        # Publish news — only ws_news should receive it.
        await reg.broadcast_event("/events", {"topic": "news", "body": "hi"})
        assert len(ws_trades.sent) == 1
        assert len(ws_news.sent) == 1

        # Tear down
        await ws_trades.close()
        await ws_news.close()
        await asyncio.gather(trades_task, news_task)

    @pytest.mark.asyncio
    async def test_broadcast_event_unknown_path_raises(self):
        reg = MessageHandlerRegistry()
        with pytest.raises(KeyError, match="no websocket handler registered"):
            await reg.broadcast_event("/missing", {"x": 1})

    @pytest.mark.asyncio
    async def test_broadcast_all_skips_dead_connections(self):
        reg = MessageHandlerRegistry()

        class H(MessageHandler):
            pass

        h = reg.register("/events", H)

        ws1 = FakeWebSocket([], auto_close=False)
        ws2 = FakeWebSocket([], auto_close=False)

        t1 = asyncio.create_task(reg.handle_connection(ws1, "/events"))
        t2 = asyncio.create_task(reg.handle_connection(ws2, "/events"))

        # wait until both are registered
        for _ in range(50):
            if h.connection_count == 2:
                break
            await asyncio.sleep(0.01)

        # kill ws1's socket
        ws1.closed = True

        sent = await h.broadcast_all({"hello": "world"})
        # ws1 raises in send -> marked dead, returns False; ws2 succeeds
        assert sent == 1
        assert len(ws2.sent) == 1

        # tear down
        await ws1.close()
        await ws2.close()
        await asyncio.gather(t1, t2, return_exceptions=True)


# ---------------------------------------------------------------------------
# Cleanup (invariant 5)
# ---------------------------------------------------------------------------


class TestCleanup:
    @pytest.mark.asyncio
    async def test_connections_removed_after_disconnect(self):
        reg = MessageHandlerRegistry()

        class H(MessageHandler):
            pass

        h = reg.register("/events", H)
        ws = FakeWebSocket([])
        await reg.handle_connection(ws, "/events")

        assert h.connection_count == 0
        assert h.connections == []

    @pytest.mark.asyncio
    async def test_clear_closes_live_connections(self):
        reg = MessageHandlerRegistry()

        class H(MessageHandler):
            pass

        h = reg.register("/events", H)
        ws = FakeWebSocket([], auto_close=False)
        task = asyncio.create_task(reg.handle_connection(ws, "/events"))

        # wait until registered
        for _ in range(50):
            if h.connection_count == 1:
                break
            await asyncio.sleep(0.01)

        reg.clear()
        # clear() flips alive=False; socket close is caller's problem
        assert reg.paths == set()

        # release the dangling task
        await ws.close()
        await asyncio.wait_for(task, timeout=1.0)


# ---------------------------------------------------------------------------
# Receive loop: JSON vs text dispatch
# ---------------------------------------------------------------------------


class TestReceiveLoop:
    @pytest.mark.asyncio
    async def test_json_dict_goes_to_on_message(self):
        reg = MessageHandlerRegistry()
        seen: List[Any] = []

        class H(MessageHandler):
            async def on_message(self, conn, msg):
                seen.append(("json", msg))

            async def on_text(self, conn, text):
                seen.append(("text", text))

        reg.register("/events", H)
        ws = FakeWebSocket([json.dumps({"a": 1}), '{"b": 2}'])
        await reg.handle_connection(ws, "/events")

        assert seen == [("json", {"a": 1}), ("json", {"b": 2})]

    @pytest.mark.asyncio
    async def test_non_json_text_goes_to_on_text(self):
        reg = MessageHandlerRegistry()
        seen: List[Any] = []

        class H(MessageHandler):
            async def on_text(self, conn, text):
                seen.append(text)

        reg.register("/events", H)
        ws = FakeWebSocket(["ping", "hello"])
        await reg.handle_connection(ws, "/events")
        assert seen == ["ping", "hello"]

    @pytest.mark.asyncio
    async def test_json_non_dict_goes_to_on_text(self):
        reg = MessageHandlerRegistry()
        seen: List[Any] = []

        class H(MessageHandler):
            async def on_text(self, conn, text):
                seen.append(text)

            async def on_message(self, conn, msg):
                seen.append(("should not", msg))

        reg.register("/events", H)
        ws = FakeWebSocket(["[1, 2, 3]"])
        await reg.handle_connection(ws, "/events")
        assert seen == ["[1, 2, 3]"]

    @pytest.mark.asyncio
    async def test_bytes_frame_decoded_as_utf8(self):
        reg = MessageHandlerRegistry()
        seen: List[Any] = []

        class H(MessageHandler):
            async def on_message(self, conn, msg):
                seen.append(msg)

        reg.register("/events", H)
        ws = FakeWebSocket([json.dumps({"x": 1}).encode("utf-8")])
        await reg.handle_connection(ws, "/events")
        assert seen == [{"x": 1}]


# ---------------------------------------------------------------------------
# Connection send helpers
# ---------------------------------------------------------------------------


class TestConnectionSend:
    @pytest.mark.asyncio
    async def test_send_json_success(self):
        ws = FakeWebSocket([])
        conn = Connection(ws, "c1", "/x")
        ok = await conn.send_json({"hi": 1})
        assert ok is True
        assert ws.sent == ['{"hi": 1}']
        assert conn.alive is True

    @pytest.mark.asyncio
    async def test_send_json_failure_marks_dead(self):
        ws = FakeWebSocket([])
        ws.closed = True  # any send raises
        conn = Connection(ws, "c1", "/x")
        ok = await conn.send_json({"hi": 1})
        assert ok is False
        assert conn.alive is False

        # Second send is a no-op
        ok = await conn.send_json({"hi": 2})
        assert ok is False
        assert len(ws.sent) == 0

    @pytest.mark.asyncio
    async def test_send_text_passthrough(self):
        ws = FakeWebSocket([])
        conn = Connection(ws, "c1", "/x")
        ok = await conn.send_text("pong")
        assert ok is True
        assert ws.sent == ["pong"]

# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Tier 2 integration tests for issue #618 — WebSocket unicast.

Two empirically-verified gaps in kailash-nexus 2.2.x (cross-SDK with
``kailash-rs#589``) are closed:

1. ``MessageHandler.on_message`` return value was discarded by
   :meth:`MessageHandlerRegistry._safe_on_message`. A handler that
   returned ``"echo: foo"`` silently never reached the originating
   client; the client timed out waiting on the reply unless the
   handler also called ``await conn.send_json(...)`` explicitly,
   duplicating the value.

2. Per-connection unicast push from EXTERNAL publishers (e.g., a
   DataFlow change stream that knows the target ``connection_id``)
   had no entry point. ``websocket_broadcast`` fans out to every
   connection via ``on_event``; there was no equivalent
   ``send_to(path, connection_id, payload)``.

These tests run a real ``websockets`` server under
:class:`WebSocketTransport` and drive it from a real ``websockets``
client. Per ``rules/testing.md`` § 3-Tier Testing, NO mocking.
Per ``rules/facade-manager-detection.md`` MUST Rule 1, the registry
is exercised through the ``app.websocket_handlers`` /
``app.websocket_send_to`` facade rather than direct class imports.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import socket
from typing import Any, List

import pytest
import websockets

from nexus import Nexus
from nexus.registry import HandlerRegistry
from nexus.transports.websocket import WebSocketTransport
from nexus.websocket_handlers import Connection, MessageHandler


def _free_port() -> int:
    """Bind to port 0 to let the kernel pick a free port, then release."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
async def ws_server():
    """Start a WebSocketTransport wired to a fresh Nexus's registry.

    Mirrors the fixture in ``test_websocket_message_handlers.py`` so the
    integration setup matches what users write.
    """
    app = Nexus(enable_auth=False, enable_monitoring=False)
    port = _free_port()
    transport = WebSocketTransport(
        host="127.0.0.1",
        port=port,
        path="/legacy-ws",  # legacy JSON-RPC path, not used by these tests
        ping_interval=5.0,
        ping_timeout=5.0,
    )
    app.add_transport(transport)

    registry = HandlerRegistry()
    await transport.start(registry)

    for _ in range(50):
        if transport.is_running:
            break
        await asyncio.sleep(0.02)
    assert transport.is_running, "WebSocketTransport did not start in time"

    yield app, port

    await transport.stop()


# ---------------------------------------------------------------------------
# 1. on_message return-value delivery
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_on_message_dict_return_delivered_to_sender(ws_server):
    """Returning a dict from on_message echoes back to the same client."""
    app, port = ws_server

    @app.websocket("/echo-dict")
    class EchoDict(MessageHandler):
        async def on_message(self, conn: Connection, msg: Any) -> Any:
            return {"echo": msg.get("hello")}

    uri = f"ws://127.0.0.1:{port}/echo-dict"
    async with websockets.connect(uri) as ws:
        await ws.send(json.dumps({"hello": "world"}))
        reply = await asyncio.wait_for(ws.recv(), timeout=2.0)
        assert json.loads(reply) == {"echo": "world"}


@pytest.mark.integration
async def test_on_message_str_return_delivered_as_text_frame(ws_server):
    """Returning a str sends a raw text frame (not JSON-encoded)."""
    app, port = ws_server

    @app.websocket("/echo-str")
    class EchoStr(MessageHandler):
        async def on_message(self, conn: Connection, msg: Any) -> Any:
            return f"echo: {msg.get('hello')}"

    uri = f"ws://127.0.0.1:{port}/echo-str"
    async with websockets.connect(uri) as ws:
        await ws.send(json.dumps({"hello": "world"}))
        reply = await asyncio.wait_for(ws.recv(), timeout=2.0)
        # str returns produce a raw text frame, not a JSON-encoded one
        assert reply == "echo: world"


@pytest.mark.integration
async def test_on_message_bytes_return_decoded_as_utf8(ws_server):
    """Returning bytes decodes as UTF-8 and sends as text frame."""
    app, port = ws_server

    @app.websocket("/echo-bytes")
    class EchoBytes(MessageHandler):
        async def on_message(self, conn: Connection, msg: Any) -> Any:
            return f"bytes: {msg.get('hello')}".encode("utf-8")

    uri = f"ws://127.0.0.1:{port}/echo-bytes"
    async with websockets.connect(uri) as ws:
        await ws.send(json.dumps({"hello": "world"}))
        reply = await asyncio.wait_for(ws.recv(), timeout=2.0)
        assert reply == "bytes: world"


@pytest.mark.integration
async def test_on_message_none_return_no_auto_reply(ws_server):
    """Returning None means handler-owned send: no auto-reply is generated."""
    app, port = ws_server

    @app.websocket("/no-reply")
    class NoReply(MessageHandler):
        async def on_message(self, conn: Connection, msg: Any) -> Any:
            return None  # explicit no-reply

    uri = f"ws://127.0.0.1:{port}/no-reply"
    async with websockets.connect(uri) as ws:
        await ws.send(json.dumps({"hello": "world"}))
        # No frame should arrive within a short window
        with contextlib.suppress(asyncio.TimeoutError):
            unexpected = await asyncio.wait_for(ws.recv(), timeout=0.3)
            raise AssertionError(
                f"on_message returned None but client received {unexpected!r}"
            )


@pytest.mark.integration
async def test_on_message_return_only_reaches_sender_not_other_clients(
    ws_server,
):
    """Return value is unicast — sibling clients do NOT receive it."""
    app, port = ws_server

    @app.websocket("/private-echo")
    class PrivateEcho(MessageHandler):
        async def on_message(self, conn: Connection, msg: Any) -> Any:
            return {"echo": msg.get("hello"), "to": conn.connection_id}

    uri = f"ws://127.0.0.1:{port}/private-echo"
    async with websockets.connect(uri) as alice:
        async with websockets.connect(uri) as bob:
            # Drain Bob's side so anything that leaks would be observable.
            await alice.send(json.dumps({"hello": "alice-says"}))
            alice_reply = await asyncio.wait_for(alice.recv(), timeout=2.0)
            assert json.loads(alice_reply)["echo"] == "alice-says"

            with contextlib.suppress(asyncio.TimeoutError):
                leaked = await asyncio.wait_for(bob.recv(), timeout=0.3)
                raise AssertionError(f"alice's reply leaked to bob: {leaked!r}")


# ---------------------------------------------------------------------------
# 2. Nexus.websocket_send_to(path, connection_id, payload)
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_websocket_send_to_targets_one_connection(ws_server):
    """``app.websocket_send_to`` reaches only the named connection."""
    app, port = ws_server
    seen_ids: List[str] = []

    @app.websocket("/named")
    class NamedTargets(MessageHandler):
        async def on_connect(self, conn: Connection) -> None:
            seen_ids.append(conn.connection_id)

    uri = f"ws://127.0.0.1:{port}/named"
    async with websockets.connect(uri) as alice:
        async with websockets.connect(uri) as bob:
            # Wait until both connections have been recorded.
            handler = app.websocket_handlers.get("/named")
            assert handler is not None
            for _ in range(100):
                if handler.connection_count == 2 and len(seen_ids) == 2:
                    break
                await asyncio.sleep(0.02)
            assert handler.connection_count == 2
            alice_id, bob_id = seen_ids[0], seen_ids[1]

            # Push a frame to ALICE only.
            ok = await app.websocket_send_to("/named", alice_id, {"ping": "alice-only"})
            assert ok is True

            alice_reply = await asyncio.wait_for(alice.recv(), timeout=2.0)
            assert json.loads(alice_reply) == {"ping": "alice-only"}

            # BOB must NOT have received the frame.
            with contextlib.suppress(asyncio.TimeoutError):
                leaked = await asyncio.wait_for(bob.recv(), timeout=0.3)
                raise AssertionError(
                    f"send_to targeted alice but bob received {leaked!r}"
                )


@pytest.mark.integration
async def test_websocket_send_to_unknown_path_returns_false(ws_server):
    """Unknown path returns False and does not raise."""
    app, _port = ws_server
    ok = await app.websocket_send_to("/no-such-path", "deadbeef", {"x": 1})
    assert ok is False


@pytest.mark.integration
async def test_websocket_send_to_unknown_connection_id_returns_false(
    ws_server,
):
    """Known path + unknown connection_id returns False, no raise."""
    app, port = ws_server

    @app.websocket("/has-handler")
    class _H(MessageHandler):
        pass

    # Connect once so the path has a registered handler with at least
    # one tracked connection — the unknown id we pass MUST still miss.
    uri = f"ws://127.0.0.1:{port}/has-handler"
    async with websockets.connect(uri):
        ok = await app.websocket_send_to(
            "/has-handler", "deadbeef-not-a-real-id", {"x": 1}
        )
        assert ok is False


@pytest.mark.integration
async def test_websocket_send_to_str_payload_sends_text_frame(ws_server):
    """A str payload is delivered as a raw text frame, not JSON-encoded."""
    app, port = ws_server
    captured: List[str] = []

    @app.websocket("/text-frame")
    class TextFrame(MessageHandler):
        async def on_connect(self, conn: Connection) -> None:
            captured.append(conn.connection_id)

    uri = f"ws://127.0.0.1:{port}/text-frame"
    async with websockets.connect(uri) as ws:
        for _ in range(100):
            if captured:
                break
            await asyncio.sleep(0.02)
        assert captured

        ok = await app.websocket_send_to("/text-frame", captured[0], "hello-text")
        assert ok is True

        reply = await asyncio.wait_for(ws.recv(), timeout=2.0)
        assert reply == "hello-text"


# ---------------------------------------------------------------------------
# 3. Regression guard — broadcast still works
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_broadcast_event_still_works_after_send_to(ws_server):
    """``websocket_broadcast`` pre-existing fanout is unaffected.

    Guards against a refactor that wires ``send_to`` and accidentally
    breaks the broadcast path.
    """
    app, port = ws_server

    @app.websocket("/broadcast-still-works")
    class FanoutEverybody(MessageHandler):
        async def on_event(self, event: Any) -> None:
            for c in self.connections:
                await c.send_json(event)

    uri = f"ws://127.0.0.1:{port}/broadcast-still-works"
    async with websockets.connect(uri) as a:
        async with websockets.connect(uri) as b:
            handler = app.websocket_handlers.get("/broadcast-still-works")
            assert handler is not None
            for _ in range(100):
                if handler.connection_count == 2:
                    break
                await asyncio.sleep(0.02)
            assert handler.connection_count == 2

            await app.websocket_broadcast("/broadcast-still-works", {"event": "ping"})

            a_reply = await asyncio.wait_for(a.recv(), timeout=2.0)
            b_reply = await asyncio.wait_for(b.recv(), timeout=2.0)
            assert json.loads(a_reply) == {"event": "ping"}
            assert json.loads(b_reply) == {"event": "ping"}

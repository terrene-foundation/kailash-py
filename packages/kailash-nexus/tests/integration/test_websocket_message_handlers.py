# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Tier 2 integration tests for class-based WebSocket message handlers.

Runs a real ``websockets`` server (via :class:`WebSocketTransport`) with
a :class:`MessageHandlerRegistry` attached, then drives it from a real
``websockets`` client. Exercises the end-to-end lifecycle:

    client.connect → on_connect → client.send(JSON) → on_message →
    registry.broadcast_event → on_event (filtered fanout) →
    client.recv → client.close → on_disconnect

Per rule ``facade-manager-detection.md`` MUST Rule 1:
``MessageHandlerRegistry`` is exposed as ``app.websocket_handlers`` on
``Nexus`` and must be exercised through that facade, not through
direct class imports.
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

    Uses the ``app.websocket_handlers`` facade so the wiring matches
    what users write. The transport runs on a random free port.
    """
    app = Nexus(enable_auth=False, enable_monitoring=False)
    port = _free_port()
    transport = WebSocketTransport(
        host="127.0.0.1",
        port=port,
        path="/legacy-ws",  # legacy JSON-RPC path, unused here
        ping_interval=5.0,
        ping_timeout=5.0,
    )
    # Attach the Nexus-owned MessageHandlerRegistry via add_transport.
    app.add_transport(transport)

    # Start the transport in its background thread.
    registry = HandlerRegistry()
    await transport.start(registry)

    # Wait until the server is really listening.
    for _ in range(50):
        if transport.is_running:
            break
        await asyncio.sleep(0.02)
    assert transport.is_running, "WebSocketTransport did not start in time"

    yield app, port

    await transport.stop()


@pytest.mark.integration
async def test_end_to_end_lifecycle(ws_server):
    """on_connect → on_message → on_disconnect all fire against a real client."""
    app, port = ws_server
    events: List[str] = []

    @app.websocket("/events")
    class Trace(MessageHandler):
        async def on_connect(self, conn: Connection) -> None:
            conn.state.name = None
            events.append("connect")

        async def on_message(self, conn: Connection, msg: Any) -> None:
            events.append(f"message:{msg.get('hello')}")
            await conn.send_json({"echo": msg.get("hello")})

        async def on_disconnect(self, conn: Connection) -> None:
            events.append("disconnect")

    uri = f"ws://127.0.0.1:{port}/events"
    async with websockets.connect(uri) as ws:
        await ws.send(json.dumps({"hello": "world"}))
        reply = await asyncio.wait_for(ws.recv(), timeout=2.0)
        assert json.loads(reply) == {"echo": "world"}

    # Give on_disconnect a moment to run in the server thread
    for _ in range(50):
        if "disconnect" in events:
            break
        await asyncio.sleep(0.02)

    assert events == ["connect", "message:world", "disconnect"]


@pytest.mark.integration
async def test_subscription_fanout_over_real_websocket(ws_server):
    """Two clients subscribe to different topics; broadcast hits only the matching one."""
    app, port = ws_server

    @app.websocket("/fanout")
    class EventStream(MessageHandler):
        async def on_connect(self, conn: Connection) -> None:
            conn.state.subscriptions = set()

        async def on_message(self, conn: Connection, msg: Any) -> None:
            if msg.get("action") == "subscribe":
                conn.state.subscriptions.add(msg["topic"])

        async def on_event(self, event: Any) -> None:
            for c in self.connections:
                if event.get("topic") in c.state.subscriptions:
                    await c.send_json(event)

    uri = f"ws://127.0.0.1:{port}/fanout"
    async with websockets.connect(uri) as ws_trades:
        async with websockets.connect(uri) as ws_news:
            await ws_trades.send(json.dumps({"action": "subscribe", "topic": "trades"}))
            await ws_news.send(json.dumps({"action": "subscribe", "topic": "news"}))

            # Wait until both subscriptions land on the server
            handler = app.websocket_handlers.get("/fanout")
            assert handler is not None
            for _ in range(100):
                if handler.connection_count == 2 and all(
                    getattr(c.state, "subscriptions", set())
                    for c in handler.connections
                ):
                    break
                await asyncio.sleep(0.02)
            assert handler.connection_count == 2

            # Fire the fanout from the server side
            await app.websocket_broadcast("/fanout", {"topic": "trades", "price": 99})

            trade_reply = await asyncio.wait_for(ws_trades.recv(), timeout=2.0)
            assert json.loads(trade_reply) == {"topic": "trades", "price": 99}

            # The news client must NOT have received it.
            with contextlib.suppress(asyncio.TimeoutError):
                got = await asyncio.wait_for(ws_news.recv(), timeout=0.2)
                raise AssertionError(
                    f"news client should not have received trade event, got {got!r}"
                )


@pytest.mark.integration
async def test_state_isolation_across_real_connections(ws_server):
    """Each real connection gets its own state — no leakage between clients."""
    app, port = ws_server

    @app.websocket("/counter")
    class Counter(MessageHandler):
        async def on_connect(self, conn: Connection) -> None:
            conn.state.n = 0

        async def on_message(self, conn: Connection, msg: Any) -> None:
            conn.state.n += 1
            await conn.send_json({"n": conn.state.n})

    uri = f"ws://127.0.0.1:{port}/counter"
    async with websockets.connect(uri) as a:
        async with websockets.connect(uri) as b:
            for _ in range(3):
                await a.send(json.dumps({"tick": True}))
                await asyncio.wait_for(a.recv(), timeout=2.0)
            await b.send(json.dumps({"tick": True}))
            b_reply = await asyncio.wait_for(b.recv(), timeout=2.0)

            # b sees its own count of 1, not a's 3
            assert json.loads(b_reply) == {"n": 1}

            await a.send(json.dumps({"tick": True}))
            a_reply = await asyncio.wait_for(a.recv(), timeout=2.0)
            assert json.loads(a_reply) == {"n": 4}


@pytest.mark.integration
async def test_unknown_path_rejected_by_transport(ws_server):
    """A path with no handler falls back to the legacy validator and gets 4004.

    The legacy path validator closes with an application code (4004)
    *after* the WebSocket handshake completes, so clients see a
    ConnectionClosed/ConnectionClosedError rather than an HTTP-level
    rejection.
    """
    _, port = ws_server
    uri = f"ws://127.0.0.1:{port}/does-not-exist"
    with pytest.raises(
        (
            websockets.exceptions.ConnectionClosed,
            websockets.exceptions.ConnectionClosedError,
            websockets.exceptions.ConnectionClosedOK,
        )
    ):
        async with websockets.connect(uri) as ws:
            # Server closes with 4004; force the failure to surface
            # by trying to receive.
            await asyncio.wait_for(ws.recv(), timeout=2.0)

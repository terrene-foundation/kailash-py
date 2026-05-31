# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Tier 2 wiring tests for the register_websocket callback overload (AC 6).

Runs a REAL ``websockets`` server (via :class:`WebSocketTransport` wired to a
fresh Nexus's ``MessageHandlerRegistry`` through the ``app.websocket_handlers``
facade) and drives it with a real ``websockets`` client. NO MOCKING.

Covers (spec §325 test contract row 6):
- Callback registration: client connects, sends a message, asserts the echo
  reply; ``on_connect`` / ``on_disconnect`` callbacks fire.
- BOTH dispatch branches get a DIRECT test (rules/testing.md § One Direct Test
  Per Variant): the class path AND the callback path each connect end to end.
- Dispatch ambiguity: passing BOTH ``handler_cls`` and ``on_message`` raises
  ``ValueError``; passing NEITHER raises ``ValueError``.
"""

import asyncio
import json
import socket

import pytest
import websockets

from nexus import Nexus
from nexus.registry import HandlerRegistry
from nexus.transports.websocket import WebSocketTransport
from nexus.websocket_handlers import Connection, MessageHandler


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
async def ws_server():
    """Start a WebSocketTransport wired to a fresh Nexus on a random port."""
    app = Nexus(enable_auth=False, enable_monitoring=False)
    port = _free_port()
    transport = WebSocketTransport(
        host="127.0.0.1",
        port=port,
        path="/legacy-ws",
        ping_interval=5.0,
        ping_timeout=5.0,
    )
    app.add_transport(transport)
    await transport.start(HandlerRegistry())
    for _ in range(50):
        if transport.is_running:
            break
        await asyncio.sleep(0.02)
    assert transport.is_running, "WebSocketTransport did not start in time"
    yield app, port
    await transport.stop()


@pytest.mark.integration
async def test_callback_path_lifecycle_and_echo(ws_server):
    """Callback shape: connect → on_connect, send → on_message echo, close → on_disconnect."""
    app, port = ws_server
    events: list = []

    async def on_connect(conn: Connection) -> None:
        events.append("connect")

    async def on_message(conn: Connection, msg: dict):
        events.append(f"message:{msg.get('hello')}")
        # A non-None return auto-replies to the same client (issue #618).
        return {"echo": msg.get("hello")}

    async def on_disconnect(conn: Connection) -> None:
        events.append("disconnect")

    # Callback shape: handler_cls is None, on_message is given.
    app.register_websocket(
        "/cb",
        on_message=on_message,
        on_connect=on_connect,
        on_disconnect=on_disconnect,
    )

    uri = f"ws://127.0.0.1:{port}/cb"
    async with websockets.connect(uri) as ws:
        await ws.send(json.dumps({"hello": "world"}))
        reply = await asyncio.wait_for(ws.recv(), timeout=2.0)
        assert json.loads(reply) == {"echo": "world"}

    for _ in range(50):
        if "disconnect" in events:
            break
        await asyncio.sleep(0.02)
    assert events == ["connect", "message:world", "disconnect"], events


@pytest.mark.integration
async def test_class_path_lifecycle_and_echo(ws_server):
    """Class shape (the OTHER dispatch branch) connects + echoes end to end.

    Direct per-variant coverage: both the class path and the callback path get
    a direct end-to-end test (rules/testing.md § One Direct Test Per Variant).
    """
    app, port = ws_server
    events: list = []

    class Echo(MessageHandler):
        async def on_connect(self, conn: Connection) -> None:
            events.append("connect")

        async def on_message(self, conn: Connection, msg: dict):
            events.append(f"message:{msg.get('hello')}")
            return {"echo": msg.get("hello")}

        async def on_disconnect(self, conn: Connection) -> None:
            events.append("disconnect")

    # Class shape: handler_cls is a MessageHandler subclass.
    app.register_websocket("/cls", Echo)

    uri = f"ws://127.0.0.1:{port}/cls"
    async with websockets.connect(uri) as ws:
        await ws.send(json.dumps({"hello": "klass"}))
        reply = await asyncio.wait_for(ws.recv(), timeout=2.0)
        assert json.loads(reply) == {"echo": "klass"}

    for _ in range(50):
        if "disconnect" in events:
            break
        await asyncio.sleep(0.02)
    assert events == ["connect", "message:klass", "disconnect"], events


@pytest.mark.integration
async def test_dispatch_ambiguity_both_raises(ws_server):
    """Passing BOTH handler_cls and on_message raises ValueError (Rule 3d)."""
    app, _ = ws_server

    class H(MessageHandler):
        async def on_message(self, conn, msg):
            return None

    async def cb(conn, msg):
        return None

    with pytest.raises(ValueError, match="not both|ambiguous"):
        app.register_websocket("/ambig", H, on_message=cb)


@pytest.mark.integration
async def test_dispatch_neither_raises(ws_server):
    """Passing NEITHER handler_cls nor on_message raises ValueError (Rule 3d)."""
    app, _ = ws_server

    with pytest.raises(ValueError, match="neither"):
        app.register_websocket("/empty")

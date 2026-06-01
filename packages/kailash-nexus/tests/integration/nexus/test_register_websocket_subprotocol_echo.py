# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Tier 2 subprotocol-echo tests for register_websocket (issue #1217).

Runs a REAL ``websockets`` server (via :class:`WebSocketTransport` wired to a
fresh Nexus's ``MessageHandlerRegistry`` through ``app.register_websocket``)
and drives it with a real ``websockets`` client. NO MOCKING.

Issue #1217: subprotocol negotiation was REJECT-ONLY — the allowlist was
validated (an unlisted offer closes 1002) but the accepted subprotocol was
NOT echoed back to the client via the ``Sec-WebSocket-Protocol`` response
header. The ``serve(select_subprotocol=...)`` callback (wired in
``WebSocketTransport._serve``) now echoes the accepted value per RFC 6455
§4.2.2. The reject-only guard is unchanged: an unlisted offer still closes
WS code 1002 post-upgrade (no regression).
"""

import asyncio
import json
import socket

import pytest
import websockets
from websockets.exceptions import ConnectionClosed

from nexus import Nexus
from nexus.registry import HandlerRegistry
from nexus.transports.websocket import WebSocketTransport
from nexus.websocket_handlers import Connection


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _close_code(exc: ConnectionClosed):
    return exc.rcvd.code if exc.rcvd is not None else None


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
async def test_allowlisted_subprotocol_echoed_on_accept(ws_server):
    """An allowlisted offer is confirmed via Sec-WebSocket-Protocol (#1217)."""
    app, port = ws_server

    async def on_message(conn: Connection, msg: dict):
        return {"echo": msg.get("ping")}

    app.register_websocket(
        "/echo-sub",
        on_message=on_message,
        subprotocols=["v1.json"],
    )

    uri = f"ws://127.0.0.1:{port}/echo-sub"
    async with websockets.connect(uri, subprotocols=["v1.json"]) as ws:
        # RFC 6455 §4.2.2: the accepted subprotocol is echoed back so the
        # client's negotiated ws.subprotocol reflects the server's choice.
        assert ws.subprotocol == "v1.json", ws.subprotocol
        await ws.send(json.dumps({"ping": "pong"}))
        reply = await asyncio.wait_for(ws.recv(), timeout=2.0)
        assert json.loads(reply) == {"echo": "pong"}


@pytest.mark.integration
async def test_first_matching_subprotocol_echoed(ws_server):
    """When the client offers several, the first allowlisted match is echoed."""
    app, port = ws_server

    async def on_message(conn: Connection, msg: dict):
        return None

    app.register_websocket(
        "/echo-multi",
        on_message=on_message,
        subprotocols=["v2.json", "v1.json"],
    )

    uri = f"ws://127.0.0.1:{port}/echo-multi"
    # Client offers v1.json first; both are allowlisted → first OFFERED match
    # wins (v1.json) per the select_subprotocol contract.
    async with websockets.connect(uri, subprotocols=["v1.json", "v2.json"]) as ws:
        assert ws.subprotocol == "v1.json", ws.subprotocol


@pytest.mark.integration
async def test_unlisted_subprotocol_still_closes_1002(ws_server):
    """An unlisted offer still closes 1002 — reject-only is unchanged (#1217)."""
    app, port = ws_server

    async def on_message(conn: Connection, msg: dict):
        return None

    app.register_websocket(
        "/echo-reject",
        on_message=on_message,
        subprotocols=["v1.json"],
    )

    uri = f"ws://127.0.0.1:{port}/echo-reject"
    # Offer v2.json — NOT in the allowlist. select_subprotocol echoes nothing;
    # the post-upgrade reject-only guard closes with WS code 1002.
    with pytest.raises(ConnectionClosed) as exc_info:
        async with websockets.connect(uri, subprotocols=["v2.json"]) as ws:
            await ws.recv()
    assert _close_code(exc_info.value) == 1002, _close_code(exc_info.value)

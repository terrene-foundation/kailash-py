# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Tier 2 origin-allowlist parity test for the callback overload (AC 6 MUST 1).

Asserts that ``register_websocket(path, on_message=..., allowed_origins=[...])``
rejects a handshake from a disallowed ``Origin`` with WebSocket close code 1008
+ a fingerprinted reason — IDENTICAL behavior to the class path (issue #673),
because the callback path routes through the SAME origin-validation call site
in ``nexus.websocket_origin``. NO parallel codepath. NO MOCKING.
"""

import asyncio
import hashlib
import socket

import pytest
import websockets

from nexus import Nexus
from nexus.registry import HandlerRegistry
from nexus.transports.websocket import WebSocketTransport
from nexus.websocket_handlers import Connection


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
async def ws_server():
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
async def test_callback_origin_rejected_1008_fingerprint(ws_server):
    """Attacker Origin → close 1008 + sha256(origin)[:8] reason (callback path)."""
    app, port = ws_server

    async def on_message(conn: Connection, msg: dict):
        return {"echo": msg}

    app.register_websocket(
        "/cb-origin",
        on_message=on_message,
        allowed_origins=["https://app.example.com"],
    )

    attacker = "https://attacker.example.com"
    expected_fp = hashlib.sha256(attacker.encode("utf-8")).hexdigest()[:8]

    uri = f"ws://127.0.0.1:{port}/cb-origin"
    with pytest.raises(websockets.exceptions.ConnectionClosed) as exc_info:
        async with websockets.connect(uri, origin=attacker) as ws:
            await ws.recv()  # server closes before any frame

    closed = exc_info.value
    code = closed.rcvd.code if closed.rcvd is not None else None
    reason = closed.rcvd.reason if closed.rcvd is not None else ""
    assert code == 1008, f"expected 1008 policy-violation, got {code}"
    # Fingerprinted reason — the raw Origin is NEVER echoed (issue #673 +
    # observability.md Rule 6/8); only the 8-char sha256 prefix appears.
    assert expected_fp in reason, f"reason {reason!r} missing fingerprint {expected_fp}"
    assert attacker not in reason, f"raw Origin leaked into close reason: {reason!r}"


@pytest.mark.integration
async def test_callback_origin_allowed_connects(ws_server):
    """An allowed Origin completes the handshake on the callback path."""
    app, port = ws_server

    async def on_message(conn: Connection, msg: dict):
        return {"echo": msg.get("ping")}

    app.register_websocket(
        "/cb-origin-ok",
        on_message=on_message,
        allowed_origins=["https://app.example.com"],
    )

    uri = f"ws://127.0.0.1:{port}/cb-origin-ok"
    import json

    async with websockets.connect(uri, origin="https://app.example.com") as ws:
        await ws.send(json.dumps({"ping": "pong"}))
        reply = await asyncio.wait_for(ws.recv(), timeout=2.0)
        assert json.loads(reply) == {"echo": "pong"}

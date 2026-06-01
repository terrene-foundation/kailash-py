# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Tier 2 security-wiring tests for register_websocket (issue #1174 AC 6).

Runs a REAL ``websockets`` server (via :class:`WebSocketTransport` wired to a
fresh Nexus's ``MessageHandlerRegistry`` through ``app.register_websocket``)
and drives it with a real ``websockets`` client. NO MOCKING.

Three WS-security MUSTs that previously had no DIRECT test:
- MUST 2 (subprotocol allowlist, reject-only): an offered subprotocol not in
  the allowlist — AND any offered subprotocol when the default ``[]`` empty
  allowlist is in effect — closes with WS code 1002 (protocol error).
- MUST 3 (max inbound frame size): a frame exceeding
  ``Nexus(max_websocket_message_bytes=...)`` closes with WS code 1009 (too big).
- MUST 4 (handshake auth via ``Depends``): a raising dependency is rejected
  PRE-upgrade with an RFC-correct HTTP 401/403 response body (issue #1216 —
  the ``serve(process_request=...)`` callback resolves the ``Depends`` chain
  before the Upgrade completes), AND ``on_connect`` / ``on_disconnect`` do
  NOT fire (the connection never reached the handler lifecycle). The earlier
  post-upgrade WS-1008 close form was secure-but-not-RFC; #1216 supersedes it
  with the pre-upgrade HTTP form.
"""

import asyncio
import json
import socket

import pytest
import websockets
from websockets.exceptions import ConnectionClosed, InvalidStatus

from nexus import Nexus
from nexus.extractors import Depends, NexusHandlerError, Request
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
    """Start a WebSocketTransport wired to a fresh Nexus on a random port.

    A small ``max_message_bytes`` (64) is set so the MUST-3 frame-size test can
    exceed it with a tiny frame.
    """
    app = Nexus(
        enable_auth=False,
        enable_monitoring=False,
        max_websocket_message_bytes=64,
    )
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


# ---------------------------------------------------------------------------
# MUST 2 — subprotocol allowlist (reject-only, close 1002)
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_subprotocol_not_in_allowlist_closes_1002(ws_server):
    """Allowlist=[chat.v1]; client offers chat.v2 → close 1002 (protocol error)."""
    app, port = ws_server

    async def on_message(conn: Connection, msg: dict):
        return {"echo": msg}

    app.register_websocket("/sub", on_message=on_message, subprotocols=["chat.v1"])

    uri = f"ws://127.0.0.1:{port}/sub"
    with pytest.raises(ConnectionClosed) as exc_info:
        async with websockets.connect(uri, subprotocols=["chat.v2"]) as ws:
            await ws.recv()  # server closes before any frame
    assert _close_code(exc_info.value) == 1002, _close_code(exc_info.value)


@pytest.mark.integration
async def test_default_empty_allowlist_rejects_any_offered_subprotocol_1002(ws_server):
    """Default subprotocols=[] + any offered subprotocol → close 1002."""
    app, port = ws_server

    async def on_message(conn: Connection, msg: dict):
        return {"echo": msg}

    # No subprotocols= → default empty allowlist (default-reject).
    app.register_websocket("/sub-default", on_message=on_message)

    uri = f"ws://127.0.0.1:{port}/sub-default"
    with pytest.raises(ConnectionClosed) as exc_info:
        async with websockets.connect(uri, subprotocols=["anything"]) as ws:
            await ws.recv()
    assert _close_code(exc_info.value) == 1002, _close_code(exc_info.value)


# ---------------------------------------------------------------------------
# MUST 3 — max inbound frame size (close 1009)
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_oversized_frame_closes_1009(ws_server):
    """max_websocket_message_bytes=64; a 5 KB frame → close 1009 (message too big)."""
    app, port = ws_server

    async def on_message(conn: Connection, msg: dict):
        return {"echo": msg}

    app.register_websocket("/big", on_message=on_message)

    uri = f"ws://127.0.0.1:{port}/big"
    with pytest.raises(ConnectionClosed) as exc_info:
        async with websockets.connect(uri) as ws:
            await ws.send(json.dumps({"payload": "x" * 5000}))  # > 64 bytes
            await ws.recv()  # server closes on the oversized frame
    assert _close_code(exc_info.value) == 1009, _close_code(exc_info.value)


# ---------------------------------------------------------------------------
# MUST 4 — handshake auth via Depends (pre-upgrade HTTP 403, no lifecycle)
# Issue #1216: the rejection moved PRE-upgrade (HTTP 403 body) — it was a WS
# close 1008 before. The secure boundary is unchanged (reject before any
# on_connect surface); only the RFC-correct rejection FORM changed.
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_raising_handshake_dependency_rejects_pre_upgrade_403_no_lifecycle(
    ws_server,
):
    """A raising Depends → pre-upgrade HTTP 403; lifecycle hooks don't fire (#1216)."""
    app, port = ws_server
    events: list = []

    def require_token(request: Request):
        if request.headers.get("authorization") != "Bearer good":
            raise NexusHandlerError(
                status_code=403, body={"error": "forbidden", "code": "FORBIDDEN"}
            )
        return True

    async def on_connect(conn: Connection) -> None:
        events.append("connect")

    async def on_message(conn: Connection, msg: dict):
        return {"echo": msg}

    async def on_disconnect(conn: Connection) -> None:
        events.append("disconnect")

    app.register_websocket(
        "/authed",
        on_message=on_message,
        on_connect=on_connect,
        on_disconnect=on_disconnect,
        dependencies=[Depends(require_token)],
    )

    uri = f"ws://127.0.0.1:{port}/authed"
    # No Authorization header → require_token raises 403 → pre-upgrade HTTP 403
    # response BODY (NOT a WS close 1008): the handshake never upgrades.
    with pytest.raises(InvalidStatus) as exc_info:
        async with websockets.connect(uri):
            pass
    response = exc_info.value.response
    assert response.status_code == 403, response.status_code
    # JSON error body is emitted pre-upgrade (issue #1216) — never the raw
    # credential bytes; only the typed status reason.
    body = bytes(response.body).decode("utf-8")
    assert json.loads(body)["code"] == "WS_HANDSHAKE_REJECTED", body

    # The connection never reached the handler lifecycle: neither on_connect nor
    # on_disconnect fired (rejection happened before the upgrade completed).
    await asyncio.sleep(0.2)
    assert events == [], events


@pytest.mark.integration
async def test_handshake_dependency_default_401_pre_upgrade(ws_server):
    """A raising Depends without a typed status → pre-upgrade HTTP 401 (#1216)."""
    app, port = ws_server

    def require_token(request: Request):
        if request.headers.get("authorization") != "Bearer good":
            raise ValueError("nope")  # untyped raise → default 401
        return True

    async def on_message(conn: Connection, msg: dict):
        return {"echo": msg}

    app.register_websocket(
        "/authed-401",
        on_message=on_message,
        dependencies=[Depends(require_token)],
    )

    uri = f"ws://127.0.0.1:{port}/authed-401"
    with pytest.raises(InvalidStatus) as exc_info:
        async with websockets.connect(uri):
            pass
    assert (
        exc_info.value.response.status_code == 401
    ), exc_info.value.response.status_code


@pytest.mark.integration
async def test_authenticated_handshake_succeeds(ws_server):
    """A handshake with the valid token completes the upgrade + dispatches (#1216)."""
    app, port = ws_server

    def require_token(request: Request):
        if request.headers.get("authorization") != "Bearer good":
            raise NexusHandlerError(status_code=403, body={"error": "forbidden"})
        return True

    async def on_message(conn: Connection, msg: dict):
        return {"echo": msg.get("ping")}

    app.register_websocket(
        "/authed-ok",
        on_message=on_message,
        dependencies=[Depends(require_token)],
    )

    uri = f"ws://127.0.0.1:{port}/authed-ok"
    async with websockets.connect(
        uri, additional_headers={"Authorization": "Bearer good"}
    ) as ws:
        await ws.send(json.dumps({"ping": "pong"}))
        reply = await asyncio.wait_for(ws.recv(), timeout=2.0)
        assert json.loads(reply) == {"echo": "pong"}

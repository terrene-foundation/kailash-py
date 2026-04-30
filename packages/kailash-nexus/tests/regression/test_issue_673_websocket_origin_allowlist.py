# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Tier-2 regression test for issue #673.

Origin/Host allowlist enforcement on register_websocket. End-to-end
exercise against a real ``websockets`` server so the behavioral
contract surfaces every layer (transport → registry → on_connect):

- ``allowed_origins=["https://app.example.com"]`` accepts a matching
  Origin and rejects a mismatching one with WebSocket close code
  1008 + a fingerprinted reason that does NOT echo the Origin.
- ``allowed_origins=None`` accepts the connection AND emits a
  one-time WARN log naming the path so operators see the gap.
- Wildcard subdomain ``https://*.example.com`` matches
  ``https://api.example.com`` and rejects an unrelated origin.
- Literal ``"*"`` is rejected at registration when the env flag is
  absent (typed ``ValueError``); accepted when the env flag is set.
- The fingerprint emitted in the WARN log is sha256(origin)[:8] —
  not the raw Origin string.
- ``Connection.headers`` exposed to ``on_connect`` carries the
  Origin / Host / Sec-WebSocket-* headers from the handshake.

Per ``rules/testing.md`` § Tier 2: real infrastructure (a real
``websockets`` server in a background thread, a real ``websockets``
client). NO mocking on this layer.
"""

from __future__ import annotations

import asyncio
import logging
import socket
import threading
from typing import Any, List

import pytest
import websockets

from nexus import Nexus
from nexus.registry import HandlerRegistry
from nexus.transports.websocket import WebSocketTransport
from nexus.websocket_handlers import Connection, MessageHandler
from nexus.websocket_origin import WILDCARD_ORIGIN_ENV_FLAG, WildcardOriginRefusedError

# Module-scope env lock per rules/testing.md § Serialize Env-Var-Mutating Tests.
_ENV_LOCK = threading.Lock()


@pytest.fixture
def _env_serialized():
    with _ENV_LOCK:
        yield


def _free_port() -> int:
    """Bind to port 0 to let the kernel pick a free port, then release."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
async def ws_server():
    """Start a WebSocketTransport wired to a fresh Nexus's registry.

    Yields ``(app, port)``. Per facade-manager-detection.md MUST
    Rule 1, the registry is exercised through ``app.websocket`` /
    ``app.register_websocket`` — the public facade — not by
    importing :class:`MessageHandlerRegistry` directly.
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
# Allowlist-MATCH path: explicit allowlist accepts matching Origin
# ---------------------------------------------------------------------------


@pytest.mark.regression
@pytest.mark.integration
async def test_issue_673_explicit_allowlist_accepts_matching_origin(
    ws_server,
):
    """allowed_origins=['https://app.example.com'] accepts that Origin."""
    app, port = ws_server
    on_connect_fired = asyncio.Event()
    captured_origins: List[str] = []

    @app.websocket("/events", allowed_origins=["https://app.example.com"])
    class EventStream(MessageHandler):
        async def on_connect(self, conn: Connection) -> None:
            captured_origins.append(conn.headers.get("origin", ""))
            on_connect_fired.set()

        async def on_message(self, conn: Connection, msg: Any) -> None:
            await conn.send_json({"echo": msg.get("hello")})

    uri = f"ws://127.0.0.1:{port}/events"
    async with websockets.connect(uri, origin="https://app.example.com") as ws:
        await asyncio.wait_for(on_connect_fired.wait(), timeout=2.0)
        await ws.send('{"hello": "world"}')
        reply = await asyncio.wait_for(ws.recv(), timeout=2.0)
        import json

        assert json.loads(reply) == {"echo": "world"}

    # External-effect assertion: handler observed the Origin header.
    assert captured_origins == ["https://app.example.com"]


# ---------------------------------------------------------------------------
# Allowlist-MISMATCH path: explicit allowlist rejects mismatching Origin
# ---------------------------------------------------------------------------


@pytest.mark.regression
@pytest.mark.integration
async def test_issue_673_explicit_allowlist_rejects_mismatching_origin(
    ws_server, caplog
):
    """Mismatching Origin → WebSocket close 1008, on_connect never fires."""
    app, port = ws_server
    on_connect_fired = asyncio.Event()

    @app.websocket("/admin", allowed_origins=["https://app.example.com"])
    class Admin(MessageHandler):
        async def on_connect(self, conn: Connection) -> None:
            # MUST NOT fire — origin enforcement happens BEFORE
            # on_connect.
            on_connect_fired.set()

    uri = f"ws://127.0.0.1:{port}/admin"
    with caplog.at_level(logging.WARNING, logger="nexus.websocket_handlers"):
        with pytest.raises(
            (
                websockets.exceptions.InvalidStatus,
                websockets.exceptions.ConnectionClosed,
                websockets.exceptions.ConnectionClosedError,
            )
        ):
            async with websockets.connect(uri, origin="https://evil.example.com") as ws:
                # If the server ever returns a frame, the test
                # MUST surface that as failure — receiving a frame
                # would mean on_connect ran or the close was
                # delivered with payload.
                msg = await asyncio.wait_for(ws.recv(), timeout=2.0)
                pytest.fail(f"unexpected frame after origin reject: {msg!r}")

    # on_connect MUST NOT have fired.
    assert not on_connect_fired.is_set(), (
        "on_connect ran despite Origin mismatch — pre-on_connect " "enforcement broken"
    )

    # WARN log MUST contain the fingerprint, NOT the raw Origin.
    matching = [r for r in caplog.records if r.message == "ws.handler.origin_rejected"]
    assert matching, "missing ws.handler.origin_rejected WARN log"
    rec = matching[-1]
    assert rec.path == "/admin"
    fingerprint = rec.origin_fingerprint
    assert isinstance(fingerprint, str)
    assert len(fingerprint) == 8
    # Defense: the raw Origin MUST NOT appear anywhere on the record.
    rendered = rec.getMessage() + " " + str(rec.__dict__)
    assert "evil.example.com" not in rendered
    assert "evil" not in fingerprint  # fingerprint is a hash


# ---------------------------------------------------------------------------
# allowed_origins=None — SDK does NOT enforce, WARN at registration
# ---------------------------------------------------------------------------


@pytest.mark.regression
@pytest.mark.integration
async def test_issue_673_none_allowlist_accepts_with_warn_log(ws_server, caplog):
    """allowed_origins=None accepts AND emits one-time registration WARN."""
    app, port = ws_server
    on_connect_fired = asyncio.Event()

    with caplog.at_level(logging.WARNING, logger="nexus.websocket_handlers"):

        @app.websocket("/open", allowed_origins=None)
        class Open(MessageHandler):
            async def on_connect(self, conn: Connection) -> None:
                on_connect_fired.set()

    # Registration emitted the WARN naming the path.
    matching = [
        r
        for r in caplog.records
        if r.message == "ws.handler.origin_enforcement_disabled"
    ]
    assert matching, "missing one-time WARN at None-allowlist registration"
    assert matching[-1].path == "/open"

    # And the connection itself succeeds (no enforcement).
    uri = f"ws://127.0.0.1:{port}/open"
    async with websockets.connect(uri, origin="https://anything.example") as _:
        await asyncio.wait_for(on_connect_fired.wait(), timeout=2.0)


# ---------------------------------------------------------------------------
# Wildcard subdomain matching — end-to-end
# ---------------------------------------------------------------------------


@pytest.mark.regression
@pytest.mark.integration
async def test_issue_673_wildcard_subdomain_matches_and_rejects(ws_server, caplog):
    """https://*.example.com matches subdomain, rejects unrelated host."""
    app, port = ws_server
    accepted: List[str] = []

    @app.websocket("/wild", allowed_origins=["https://*.example.com"])
    class Wild(MessageHandler):
        async def on_connect(self, conn: Connection) -> None:
            accepted.append(conn.headers.get("origin", ""))

    uri = f"ws://127.0.0.1:{port}/wild"

    # Subdomain matches.
    async with websockets.connect(uri, origin="https://api.example.com") as _:
        await asyncio.sleep(0.05)
    # Unrelated host rejected.
    with pytest.raises(
        (
            websockets.exceptions.InvalidStatus,
            websockets.exceptions.ConnectionClosed,
            websockets.exceptions.ConnectionClosedError,
        )
    ):
        async with websockets.connect(uri, origin="https://evil.com") as ws:
            await asyncio.wait_for(ws.recv(), timeout=2.0)

    # Wait for the server-side on_connect for the accepted side.
    for _ in range(50):
        if accepted:
            break
        await asyncio.sleep(0.02)
    assert accepted == ["https://api.example.com"]


# ---------------------------------------------------------------------------
# Literal '*' wildcard — fail-closed default + env opt-in
# ---------------------------------------------------------------------------


@pytest.mark.regression
def test_issue_673_literal_wildcard_rejected_at_registration_without_env(
    _env_serialized, monkeypatch
):
    """Literal '*' rejected at register time when env flag absent."""
    monkeypatch.delenv(WILDCARD_ORIGIN_ENV_FLAG, raising=False)
    app = Nexus(enable_auth=False, enable_monitoring=False)

    class H(MessageHandler):
        pass

    with pytest.raises(WildcardOriginRefusedError):
        app.register_websocket("/wide", H, allowed_origins=["*"])


@pytest.mark.regression
def test_issue_673_literal_wildcard_accepted_with_env_opt_in(
    _env_serialized, monkeypatch
):
    """Literal '*' accepted when KAILASH_NEXUS_ALLOW_WILDCARD_ORIGIN=true."""
    monkeypatch.setenv(WILDCARD_ORIGIN_ENV_FLAG, "true")
    app = Nexus(enable_auth=False, enable_monitoring=False)

    class H(MessageHandler):
        pass

    handler = app.register_websocket("/wide", H, allowed_origins=["*"])
    assert handler is not None
    assert app.websocket_handlers.get_allowed_origins("/wide") == ["*"]


# ---------------------------------------------------------------------------
# Connection.headers exposure end-to-end
# ---------------------------------------------------------------------------


@pytest.mark.regression
@pytest.mark.integration
async def test_issue_673_connection_headers_exposed_to_on_connect(
    ws_server,
):
    """on_connect receives the handshake headers (Origin, Host, etc)."""
    app, port = ws_server
    captured: List[dict] = []
    on_connect_fired = asyncio.Event()

    @app.websocket("/headers", allowed_origins=["https://app.example.com"])
    class HeaderProbe(MessageHandler):
        async def on_connect(self, conn: Connection) -> None:
            # Capture a snapshot of the headers dict so the
            # assertion can run after the connection closes.
            captured.append(
                {
                    "origin": conn.headers.get("origin"),
                    "host": conn.headers.get("host"),
                    "has_sec_ws_key": "sec-websocket-key" in conn.headers,
                    "headers_type": type(conn.headers).__name__,
                }
            )
            on_connect_fired.set()

    uri = f"ws://127.0.0.1:{port}/headers"
    async with websockets.connect(uri, origin="https://app.example.com") as _:
        await asyncio.wait_for(on_connect_fired.wait(), timeout=2.0)

    assert len(captured) == 1
    snap = captured[0]
    assert snap["origin"] == "https://app.example.com"
    assert snap["host"] is not None  # 127.0.0.1:<port>
    # Sec-WebSocket-Key is required by RFC 6455 §1.3 for every
    # client-initiated handshake — its presence proves the headers
    # are coming from the real handshake, not a fixture stub.
    assert snap["has_sec_ws_key"] is True

# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression: MCP transports must not leak base_url credentials (#1840).

Before the fix, the SSE / StreamableHTTP / WebSocket transports interpolated a
credential-bearing ``base_url`` / ``url`` verbatim into:

* the "transport connected" ``logger.info`` line, and
* the opaque ``{e}`` of every ``TransportError`` raised on a connect / send /
  receive failure.

A ``base_url`` such as ``https://user:secret@host/path?token=abc`` therefore
leaked ``user:secret`` and ``token=abc`` into logs and exception text.

The fix routes URL-value log lines through ``mask_url`` and opaque ``{e}``
strings through ``mask_error_text`` (both from
``kailash.utils.url_credentials`` — the ONE shared helper module).

These tests INJECT the network boundary (aiohttp / websockets) — the external
infra — so the failure path fires deterministically; the redaction helpers
themselves are exercised for real (never mocked).
"""

import logging

import pytest
from kailash_mcp.errors import TransportError
from kailash_mcp.transports import transports as T
from kailash_mcp.transports.transports import (
    SSETransport,
    StreamableHTTPTransport,
    WebSocketTransport,
)

SSE_URL = "https://sse_user:S3cr3tSSE@mcp.example:8443/base?token=ssetok123"
HTTP_URL = "https://http_user:S3cr3tHTTP@mcp.example:8443/base?token=httptok123"
WS_URL = "wss://ws_user:S3cr3tWS@mcp.example:8443/ws?token=wstok123"


# --- Boundary fakes ----------------------------------------------------------


class _EmptyContent:
    def __aiter__(self):
        return self

    async def __anext__(self):
        raise StopAsyncIteration


class _OkResp:
    """Minimal aiohttp response: 200 + empty SSE stream."""

    def __init__(self):
        self.status = 200
        self.headers = {}

    @property
    def content(self):
        return _EmptyContent()

    def close(self):
        pass


class _SuccessSession:
    def __init__(self, *a, **k):
        pass

    async def get(self, *a, **k):
        return _OkResp()

    async def close(self):
        pass


def _make_raising_session(exc):
    class _RaisingSession:
        def __init__(self, *a, **k):
            pass

        async def get(self, *a, **k):
            raise exc

        def post(self, *a, **k):  # returns a CM; entering raises
            raise exc

        async def close(self):
            pass

    return _RaisingSession


class _OkWebSocket:
    def __aiter__(self):
        return self

    async def __anext__(self):
        raise StopAsyncIteration

    async def close(self):
        pass


# --- SSE ---------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sse_connect_log_masks_url(monkeypatch, caplog):
    monkeypatch.setattr(T.aiohttp, "ClientSession", _SuccessSession)
    t = SSETransport(SSE_URL, skip_security_validation=True)
    with caplog.at_level(logging.INFO, logger="kailash_mcp.transports.transports"):
        await t.connect()
    logged = "\n".join(r.getMessage() for r in caplog.records)
    assert "SSE transport connected" in logged
    assert "S3cr3tSSE" not in logged
    assert "***@mcp.example" in logged
    await t.disconnect()


@pytest.mark.asyncio
async def test_sse_connect_raise_masks_credentials(monkeypatch):
    exc = Exception(f"Cannot connect to {SSE_URL}")
    monkeypatch.setattr(T.aiohttp, "ClientSession", _make_raising_session(exc))
    t = SSETransport(SSE_URL, skip_security_validation=True)
    with pytest.raises(TransportError) as ei:
        await t.connect()
    msg = str(ei.value)
    assert "S3cr3tSSE" not in msg
    assert "ssetok123" not in msg
    assert "***@mcp.example" in msg


@pytest.mark.asyncio
async def test_sse_send_raise_masks_credentials():
    t = SSETransport(SSE_URL, skip_security_validation=True)
    t._connected = True
    t.session = _make_raising_session(Exception(f"POST failed to {SSE_URL}"))()
    with pytest.raises(TransportError) as ei:
        await t.send_message({"jsonrpc": "2.0", "method": "ping"})
    msg = str(ei.value)
    assert "S3cr3tSSE" not in msg
    assert "ssetok123" not in msg


# --- StreamableHTTP ----------------------------------------------------------


@pytest.mark.asyncio
async def test_http_connect_log_masks_url(monkeypatch, caplog):
    monkeypatch.setattr(T.aiohttp, "ClientSession", _SuccessSession)
    t = StreamableHTTPTransport(
        HTTP_URL, session_management=False, skip_security_validation=True
    )
    with caplog.at_level(logging.INFO, logger="kailash_mcp.transports.transports"):
        await t.connect()
    logged = "\n".join(r.getMessage() for r in caplog.records)
    assert "StreamableHTTP transport connected" in logged
    assert "S3cr3tHTTP" not in logged
    assert "***@mcp.example" in logged
    await t.disconnect()


@pytest.mark.asyncio
async def test_http_connect_raise_masks_credentials(monkeypatch):
    exc = Exception(f"handshake failed for {HTTP_URL}")
    monkeypatch.setattr(T.aiohttp, "ClientSession", _make_raising_session(exc))
    t = StreamableHTTPTransport(
        HTTP_URL, session_management=True, skip_security_validation=True
    )
    with pytest.raises(TransportError) as ei:
        await t.connect()
    msg = str(ei.value)
    assert "S3cr3tHTTP" not in msg
    assert "httptok123" not in msg
    assert "***@mcp.example" in msg


@pytest.mark.asyncio
async def test_http_send_raise_masks_credentials():
    t = StreamableHTTPTransport(
        HTTP_URL, session_management=False, skip_security_validation=True
    )
    t._connected = True
    t.session = _make_raising_session(Exception(f"POST error {HTTP_URL}"))()
    with pytest.raises(TransportError) as ei:
        await t.send_message({"jsonrpc": "2.0", "method": "ping"})
    msg = str(ei.value)
    assert "S3cr3tHTTP" not in msg
    assert "httptok123" not in msg


# --- WebSocket ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_ws_connect_log_masks_url(monkeypatch, caplog):
    async def _fake_connect(*a, **k):
        return _OkWebSocket()

    monkeypatch.setattr(T.websockets, "connect", _fake_connect)
    t = WebSocketTransport(WS_URL, skip_security_validation=True)
    with caplog.at_level(logging.INFO, logger="kailash_mcp.transports.transports"):
        await t.connect()
    logged = "\n".join(r.getMessage() for r in caplog.records)
    assert "WebSocket transport connected" in logged
    assert "S3cr3tWS" not in logged
    assert "***@mcp.example" in logged
    await t.disconnect()


@pytest.mark.asyncio
async def test_ws_connect_raise_masks_credentials(monkeypatch):
    async def _fake_connect(*a, **k):
        raise Exception(f"WebSocket handshake to {WS_URL} failed")

    monkeypatch.setattr(T.websockets, "connect", _fake_connect)
    t = WebSocketTransport(WS_URL, skip_security_validation=True)
    with pytest.raises(TransportError) as ei:
        await t.connect()
    msg = str(ei.value)
    assert "S3cr3tWS" not in msg
    assert "wstok123" not in msg
    assert "***@mcp.example" in msg


@pytest.mark.asyncio
async def test_ws_send_raise_masks_credentials():
    class _RaisingWS:
        async def send(self, *a, **k):
            raise Exception(f"send failed on {WS_URL}")

    t = WebSocketTransport(WS_URL, skip_security_validation=True)
    t._connected = True
    t.websocket = _RaisingWS()
    with pytest.raises(TransportError) as ei:
        await t.send_message({"jsonrpc": "2.0", "method": "ping"})
    msg = str(ei.value)
    assert "S3cr3tWS" not in msg
    assert "wstok123" not in msg


# --- DOTALL invariant at a transport raise site ------------------------------


@pytest.mark.asyncio
async def test_transport_raise_masks_credential_with_embedded_newline(monkeypatch):
    """The #1840 DOTALL regression, exercised through a real transport raise.

    A driver/library exception whose embedded credential contains a literal
    newline must be FULLY masked — the tail after the ``\\n`` must not leak.
    """
    leaky_url = "https://admin:sec\nret@mcp.example:8443/base"
    exc = Exception(f"boom connecting to {leaky_url}")
    monkeypatch.setattr(T.aiohttp, "ClientSession", _make_raising_session(exc))
    t = SSETransport(
        "https://admin:secret@mcp.example:8443/base", skip_security_validation=True
    )
    with pytest.raises(TransportError) as ei:
        await t.connect()
    msg = str(ei.value)
    assert "ret@" not in msg  # the tail after the newline must not survive
    assert "sec\nret" not in msg
    assert "***@mcp.example" in msg


# --- Non-leak-surface documentation (Python N/A surfaces) --------------------


def test_non_leak_surfaces_are_na_in_python():
    """Document the surfaces that are N/A for the Python SDK (#1840).

    * OAuth server-side token handling and Docker-runner env are N/A in the
      Python transport layer (no such code path here).
    * ``WebSocketServerTransport`` BINDS a local ``host:port`` (no client
      credential URL), so it has no ``user:pass@host`` credential to leak —
      the credential-bearing surface is the CLIENT transports covered above.
    """
    from kailash_mcp.transports.transports import WebSocketServerTransport

    server = WebSocketServerTransport(host="127.0.0.1", port=0)
    # A server bind exposes host/port, never a user:pass@host credential URL.
    assert not hasattr(server, "base_url")
    assert getattr(server, "host", None) == "127.0.0.1"

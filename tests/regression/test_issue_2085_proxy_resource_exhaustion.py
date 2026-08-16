# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression tests for #2085 -- proxy resource exhaustion.

Two defects, both on the proxy surfaces, in different mixes:

1. **Unbounded response buffering, BOTH surfaces.** ``resp.read()`` on the
   server and ``resp.content`` on the gateway buffered the entire backend
   body in this process before a byte reached the caller, with no cap.
   Concurrent requests multiply it.

2. **A fresh ``aiohttp.ClientSession`` per REQUEST, server surface only.**
   Every proxied request built and tore down a session -- new connector, new
   pool, fresh sockets, no keep-alive. ``WorkflowAPIGateway`` already reused
   one client, so this was also an enforcement-surface asymmetry, the same
   shape as the credential-stripping and redirect-policy disagreements #2025
   closed. The churn is not theoretical: this repo hit fd/thread exhaustion
   in CI (#2078).

Fail-first, measured pre-fix::

    WorkflowServer  40MB backend body -> status=200 bytes_buffered=41943040  <== NO CAP
    Gateway         40MB backend body -> status=200 bytes_buffered=41943040  <== NO CAP
    WorkflowServer  3 proxied requests -> 3 distinct client source ports <== NEW CONNECTION EACH TIME

Both are measured at the level that matters rather than by reading the code:
the byte cap against a real oversized body from a real socket, and the
session reuse against the CLIENT SOURCE PORT the backend observed. A single
source port across three requests is only possible if the connection was
reused, which is only possible if the session was.

No ``Mock`` appears in this file.
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from starlette.requests import Request

from kailash.api.gateway import WorkflowAPIGateway
from kailash.servers.workflow_server import WorkflowServer
from kailash.utils.proxy_guard import (
    DEFAULT_MAX_RESPONSE_BYTES,
    normalize_max_response_bytes,
)

pytestmark = pytest.mark.regression

#: Body the "large" route serves. Comfortably over the caps used below.
LARGE_BODY_BYTES = 8 * 1024 * 1024
SMALL_BODY = b'{"ok":true}'
CAP = 1024 * 1024


class _SizedHandler(BaseHTTPRequestHandler):
    """Real backend serving a large or a small body, and recording peers."""

    protocol_version = "HTTP/1.1"
    peers: list = []
    #: Bytes the backend SUCCESSFULLY wrote for the last /large request. This
    #: is the instrument for the memory bound: if the proxy stops reading at
    #: the cap, the backend's writes fail partway and this stays far below
    #: LARGE_BODY_BYTES. If the proxy drains the whole body -- the #2085
    #: defect -- this reaches LARGE_BODY_BYTES. Asserting only the 502 status
    #: does NOT discriminate that, because a post-loop size check returns 502
    #: whether or not the read was bounded.
    bytes_written: int = 0

    def do_GET(self):
        type(self).peers.append(self.client_address[1])
        if self.path.startswith("/large"):
            n = LARGE_BODY_BYTES
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(n))
            self.end_headers()
            block = b"A" * 65536
            sent = 0
            try:
                while sent < n:
                    w = min(len(block), n - sent)
                    self.wfile.write(block[:w])
                    self.wfile.flush()
                    sent += w
            except (BrokenPipeError, ConnectionResetError, OSError):
                # EXPECTED on the over-cap path: the proxy stops reading once
                # the cap is passed, so the backend's write fails. That is the
                # bound working, not an error.
                pass
            type(self).bytes_written = sent
        else:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(SMALL_BODY)))
            self.end_headers()
            self.wfile.write(SMALL_BODY)

    def log_message(self, *args):  # noqa: D102 - silence stderr access log
        return


#: How much of the oversized body the backend may get away with writing
#: before we call the read "unbounded". Generous: kernel socket buffers let
#: the backend push some bytes past what the proxy consumed, so this is not
#: `== CAP`. It is still far below LARGE_BODY_BYTES, which is the only thing
#: that has to be true for the assertion to discriminate.
DRAINED_THRESHOLD = LARGE_BODY_BYTES // 2


@pytest.fixture
def backend():
    _SizedHandler.peers = []
    _SizedHandler.bytes_written = 0
    server = ThreadingHTTPServer(("127.0.0.1", 0), _SizedHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


async def _allow(request: Request):
    if request.headers.get("X-Regression-Key") != "let-me-in":
        raise HTTPException(status_code=401, detail="Not authenticated")
    return {"user_id": "keyed"}


def _auth_headers():
    return {"X-Regression-Key": "let-me-in"}


# ---------------------------------------------------------------------------
# 1. Bounded response buffering -- BOTH surfaces
# ---------------------------------------------------------------------------


def test_workflow_server_refuses_oversized_response(backend):
    server = WorkflowServer(title="issue-2085", require_auth=False)
    server.proxy_workflow(
        name="internal",
        proxy_url=backend,
        allowed_paths=["*"],
        auth_dependency=_allow,
        max_response_bytes=CAP,
    )
    try:
        with TestClient(server.app) as client:
            resp = client.get("/workflows/internal/large", headers=_auth_headers())
        assert resp.status_code == 502, resp.text
        # Fail CLOSED, not truncated: a truncated 200 is indistinguishable
        # from a complete one to the caller.
        assert len(resp.content) < CAP
        # ...and the read was actually BOUNDED. Without this the test passes
        # even when the proxy drains the whole body and only then checks the
        # size, which is the exact defect #2085 is about.
        assert _SizedHandler.bytes_written < DRAINED_THRESHOLD, (
            f"backend wrote {_SizedHandler.bytes_written} bytes -- the proxy "
            f"drained the whole body instead of stopping at the cap"
        )
    finally:
        server.close()


def test_gateway_refuses_oversized_response(backend):
    gw = WorkflowAPIGateway(require_auth=False, title="issue-2085")
    try:
        gw.proxy_workflow(
            name="internal",
            proxy_url=backend,
            allowed_paths=["*"],
            auth_dependency=_allow,
            max_response_bytes=CAP,
        )
        with TestClient(gw.app) as client:
            resp = client.get("/internal/large", headers=_auth_headers())
        assert resp.status_code == 502, resp.text
        assert len(resp.content) < CAP
        assert _SizedHandler.bytes_written < DRAINED_THRESHOLD, (
            f"backend wrote {_SizedHandler.bytes_written} bytes -- the proxy "
            f"drained the whole body instead of stopping at the cap"
        )
    finally:
        gw.close()


@pytest.mark.parametrize("surface", ["server", "gateway"])
def test_under_cap_response_is_forwarded_intact(backend, surface):
    """No-false-positive polarity, and a truncation guard.

    Asserting the exact bytes matters: the first implementation of this cap
    used ``StreamReader.read(n)``, which returns *up to* n bytes, and so
    silently returned a SHORT body with a 200. An 8 MiB response came back as
    155023 bytes. Comparing the full payload is what catches that.
    """
    if surface == "server":
        obj = WorkflowServer(title="issue-2085", require_auth=False)
        path = "/workflows/internal/small"
    else:
        obj = WorkflowAPIGateway(require_auth=False, title="issue-2085")
        path = "/internal/small"
    try:
        obj.proxy_workflow(
            name="internal",
            proxy_url=backend,
            allowed_paths=["*"],
            auth_dependency=_allow,
            max_response_bytes=CAP,
        )
        with TestClient(obj.app) as client:
            resp = client.get(path, headers=_auth_headers())
        assert resp.status_code == 200, resp.text
        assert resp.content == SMALL_BODY
    finally:
        obj.close()


@pytest.mark.parametrize("surface", ["server", "gateway"])
def test_body_larger_than_cap_is_never_returned_truncated(backend, surface):
    """The truncation-specific assertion, stated separately.

    A cap implemented as a short read would return 200 with a partial body.
    This pins that the over-cap path is a REFUSAL.
    """
    if surface == "server":
        obj = WorkflowServer(title="issue-2085", require_auth=False)
        path = "/workflows/internal/large"
    else:
        obj = WorkflowAPIGateway(require_auth=False, title="issue-2085")
        path = "/internal/large"
    try:
        obj.proxy_workflow(
            name="internal",
            proxy_url=backend,
            allowed_paths=["*"],
            auth_dependency=_allow,
            max_response_bytes=CAP,
        )
        with TestClient(obj.app) as client:
            resp = client.get(path, headers=_auth_headers())
        assert resp.status_code == 502
        body = resp.content
        assert b"A" * 1024 not in body, "a truncated backend body was returned"
        assert json.loads(body)["error"]
    finally:
        obj.close()


# ---------------------------------------------------------------------------
# The cap contract
# ---------------------------------------------------------------------------


def test_cap_defaults_to_a_documented_finite_value():
    assert normalize_max_response_bytes(None, name="x") == DEFAULT_MAX_RESPONSE_BYTES
    assert DEFAULT_MAX_RESPONSE_BYTES > 0
    assert DEFAULT_MAX_RESPONSE_BYTES == 64 * 1024 * 1024


@pytest.mark.parametrize("bad", [0, -1, -1024])
def test_cap_has_no_unlimited_spelling(bad):
    """``0`` must not be a back door to the unbounded behaviour."""
    with pytest.raises(ValueError, match="POSITIVE"):
        normalize_max_response_bytes(bad, name="x")


@pytest.mark.parametrize("bad", ["1000", 1.5, True, None.__class__])
def test_cap_rejects_non_integers(bad):
    if bad is None:
        pytest.skip("None selects the default")
    with pytest.raises(ValueError):
        normalize_max_response_bytes(bad, name="x")


@pytest.mark.parametrize("surface", ["server", "gateway"])
def test_invalid_cap_refused_at_registration(backend, surface):
    obj = (
        WorkflowServer(title="issue-2085", require_auth=False)
        if surface == "server"
        else WorkflowAPIGateway(require_auth=False, title="issue-2085")
    )
    try:
        with pytest.raises(ValueError):
            obj.proxy_workflow(
                name="internal",
                proxy_url=backend,
                allowed_paths=["*"],
                auth_dependency=_allow,
                max_response_bytes=0,
            )
    finally:
        obj.close()


# ---------------------------------------------------------------------------
# 2. Shared session -- and lifecycle PARITY between the two surfaces
# ---------------------------------------------------------------------------


def _distinct_source_ports(obj, path, n=3):
    _SizedHandler.peers = []
    with TestClient(obj.app) as client:
        for _ in range(n):
            resp = client.get(path, headers=_auth_headers())
            assert resp.status_code == 200, resp.text
    return len(set(_SizedHandler.peers))


def test_workflow_server_reuses_one_connection_across_requests(backend):
    """Measured at the backend's observed CLIENT SOURCE PORT.

    Pre-fix this was 3 distinct ports for 3 requests. One port is only
    possible if the connection -- and therefore the session -- was reused.
    """
    server = WorkflowServer(title="issue-2085", require_auth=False)
    server.proxy_workflow(
        name="internal",
        proxy_url=backend,
        allowed_paths=["*"],
        auth_dependency=_allow,
    )
    try:
        assert _distinct_source_ports(server, "/workflows/internal/small") == 1
    finally:
        server.close()


def test_gateway_reuses_one_connection_across_requests(backend):
    gw = WorkflowAPIGateway(require_auth=False, title="issue-2085")
    try:
        gw.proxy_workflow(
            name="internal",
            proxy_url=backend,
            allowed_paths=["*"],
            auth_dependency=_allow,
        )
        assert _distinct_source_ports(gw, "/internal/small") == 1
    finally:
        gw.close()


def test_workflow_server_session_identity_is_stable_across_requests(backend):
    """#2085 AC: assert the SESSION IDENTITY, not just the connection.

    The AC asks for this to be verified by observation rather than by reading
    the code, so the identity is captured from the live server between two
    real proxied requests.
    """
    server = WorkflowServer(title="issue-2085", require_auth=False)
    server.proxy_workflow(
        name="internal",
        proxy_url=backend,
        allowed_paths=["*"],
        auth_dependency=_allow,
    )
    try:
        with TestClient(server.app) as client:
            client.get("/workflows/internal/small", headers=_auth_headers())
            first = server._proxy_session
            client.get("/workflows/internal/small", headers=_auth_headers())
            second = server._proxy_session
        assert first is not None
        assert first is second, "a new ClientSession was built for the 2nd request"
    finally:
        server.close()


def test_both_surfaces_agree_on_connection_lifecycle(backend):
    """#2085 AC: the asymmetry must not silently return.

    Both surfaces expose a lazily-created, reused, explicitly-closable client
    for proxying. Asserting the SHAPE is what makes a future divergence a test
    failure rather than a discovery.
    """
    server = WorkflowServer(title="issue-2085", require_auth=False)
    gw = WorkflowAPIGateway(require_auth=False, title="issue-2085")
    try:
        assert hasattr(server, "_get_proxy_session")
        assert hasattr(gw, "_get_proxy_client")
        # Neither builds its client eagerly...
        assert server._proxy_session is None
        assert gw._proxy_client is None
        # ...and both expose a close path.
        assert callable(server.aclose_proxy_session)
        assert callable(gw.close)
    finally:
        server.close()
        gw.close()


@pytest.mark.asyncio
async def test_proxy_session_is_closed_on_shutdown(backend):
    """The session must be released on the normal shutdown path, not GC."""
    server = WorkflowServer(title="issue-2085", require_auth=False)
    server.proxy_workflow(
        name="internal",
        proxy_url=backend,
        allowed_paths=["*"],
        auth_dependency=_allow,
    )
    try:
        session = await server._get_proxy_session()
        assert not session.closed
        await server.shutdown_coordinator.shutdown()
        assert session.closed, "shutdown did not close the shared proxy session"
        assert server._proxy_session is None
    finally:
        server.close()


@pytest.mark.asyncio
async def test_aclose_proxy_session_is_idempotent(backend):
    server = WorkflowServer(title="issue-2085", require_auth=False)
    try:
        session = await server._get_proxy_session()
        await server.aclose_proxy_session()
        await server.aclose_proxy_session()
        assert session.closed
    finally:
        server.close()


def test_api_channel_plumbs_the_response_cap():
    """``security.md`` § Multi-Site Kwarg Plumbing."""
    import inspect

    from kailash.channels.api_channel import APIChannel

    params = inspect.signature(APIChannel.proxy_workflow).parameters
    assert "max_response_bytes" in params
    source = inspect.getsource(APIChannel.proxy_workflow)
    assert "max_response_bytes=max_response_bytes" in source

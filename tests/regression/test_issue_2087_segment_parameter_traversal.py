# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression tests for #2087 -- ``..;/`` segment-parameter collapse.

``reject_unsafe_proxy_path`` refused a segment equal to ``..``. That is
correct for the RFC 3986 shape and BYPASSABLE for the servlet-class one:
Tomcat, Jetty and others strip everything from ``;`` to the end of a path
segment while resolving it, so ``..;`` is not ``..`` at the proxy, passes the
check, and is normalised BY THE BACKEND to ``..``.

Fail-first, measured on the pre-fix guard (``reject_unsafe_proxy_path``
returning None == forwarded)::

    'a/../b'                 -> path contains a parent-directory segment (..)
    'a/..;/b'                -> FORWARDED  <== TRAVERSAL RESTORED
    'a/..;foo/b'             -> FORWARDED  <== TRAVERSAL RESTORED
    'a/..%3B/b'              -> FORWARDED  <== TRAVERSAL RESTORED
    'a/..%3b/b'              -> FORWARDED  <== TRAVERSAL RESTORED
    '..;/etc/passwd'         -> FORWARDED  <== TRAVERSAL RESTORED

``a/../b`` refusing on the SAME run is the discrimination control: the guard
was running, and it was the segment-parameter spelling specifically that it
could not see.

The encoded forms are covered because Starlette's decode depth was MEASURED
rather than assumed (``test_measured_decode_depth_reaches_the_guard`` below),
which is what makes the ``%3B`` clause load-bearing rather than decorative.

No ``Mock`` appears in this file. The backend is a real HTTP server on a real
socket and it records the paths it was actually asked for, so "the traversal
did not reach the backend" is an observation, not an inference.
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from starlette.requests import Request

from kailash.api.gateway import WorkflowAPIGateway
from kailash.servers.workflow_server import WorkflowServer
from kailash.utils.proxy_guard import reject_unsafe_proxy_path

pytestmark = pytest.mark.regression


# ---------------------------------------------------------------------------
# Real backend
# ---------------------------------------------------------------------------


class _PathRecordingHandler(BaseHTTPRequestHandler):
    """Real backend recording every path it was actually asked for."""

    paths: list = []

    def _respond(self):
        type(self).paths.append(self.path)
        payload = json.dumps({"path": self.path}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    do_GET = _respond

    def log_message(self, *args):  # noqa: D102 - silence stderr access log
        return


@pytest.fixture
def backend():
    _PathRecordingHandler.paths = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), _PathRecordingHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


async def _allow(request: Request):
    """A real dependency, not a Mock."""
    if request.headers.get("X-Regression-Key") != "let-me-in":
        raise HTTPException(status_code=401, detail="Not authenticated")
    return {"user_id": "keyed"}


def _auth_headers():
    return {"X-Regression-Key": "let-me-in"}


#: Every spelling of the defect. Each is a segment that is NOT ``..`` at this
#: proxy but which a servlet-class backend resolves to ``..``.
TRAVERSAL_SPELLINGS = [
    "a/..;/b",
    "a/..;foo/b",
    "a/..;jsessionid=deadbeef/b",
    "a/..%3B/b",
    "a/..%3b/b",
    "..;/etc/passwd",
]

#: Legitimate uses of ``;``. RFC 3986 sub-delimiter, valid in paths -- a
#: blanket ban would be a regression, so both polarities are asserted.
LEGITIMATE_SEMICOLON_PATHS = [
    "products;color=blue/list",
    "a;jsessionid=xyz/b",
    "sem;i/co;lon",
    "a/..foo/b",
    "a/x..;/b",
]


# ---------------------------------------------------------------------------
# Unit level -- the shared guard
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path", TRAVERSAL_SPELLINGS)
def test_guard_refuses_segment_parameter_traversal(path):
    reason = reject_unsafe_proxy_path(path)
    assert reason is not None, f"{path!r} was forwarded -- traversal restored"
    assert "path parameter" in reason


@pytest.mark.parametrize("path", LEGITIMATE_SEMICOLON_PATHS)
def test_guard_still_forwards_legitimate_semicolons(path):
    """The no-false-positive polarity: a blanket ``;`` ban is a regression."""
    assert reject_unsafe_proxy_path(path) is None, f"{path!r} was wrongly refused"


def test_guard_still_refuses_the_plain_dot_segment():
    """Discrimination control -- the original check must not have regressed."""
    reason = reject_unsafe_proxy_path("a/../b")
    assert reason == "path contains a parent-directory segment (..)"


def test_measured_decode_depth_reaches_the_guard():
    """Pin the decode depth the ``%3B`` clause depends on.

    This is the instrument behind the encoded rows: it establishes what the
    handler ACTUALLY receives for each wire spelling, so the guard is checked
    against its real input rather than an assumed one. Measured:

        WIRE a/..%3B/b     -> HANDLER RECEIVED 'a/..;/b'
        WIRE a/..%253B/b   -> HANDLER RECEIVED 'a/..;/b'
        WIRE a/..%25253B/b -> HANDLER RECEIVED 'a/..%3B/b'

    The third row is why ``_ENCODED_SEMICOLON_RE`` exists: at that depth the
    literal-``;`` truncation alone would not fire, and the guard must still
    refuse.
    """
    app = FastAPI()
    seen: list = []

    @app.get("/w/{path:path}")
    async def handler(path: str):
        seen.append(path)
        return {"ok": True}

    client = TestClient(app)
    received = {}
    for wire in ("a/..%3B/b", "a/..%253B/b", "a/..%25253B/b"):
        seen.clear()
        client.get("/w/" + wire)
        received[wire] = seen[0]

    # Whatever the depth, every form must arrive as something the guard refuses.
    for wire, arrived in received.items():
        assert (
            reject_unsafe_proxy_path(arrived) is not None
        ), f"wire {wire!r} arrived as {arrived!r}, which the guard forwards"


# ---------------------------------------------------------------------------
# Enforcement-surface parity -- BOTH proxy surfaces, end to end
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path", TRAVERSAL_SPELLINGS)
def test_workflow_server_refuses_traversal_end_to_end(backend, path):
    server = WorkflowServer(title="issue-2087-server", require_auth=False)
    server.proxy_workflow(
        name="internal",
        proxy_url=backend,
        allowed_paths=["*"],
        auth_dependency=_allow,
    )
    try:
        client = TestClient(server.app)
        resp = client.get(f"/workflows/internal/{path}", headers=_auth_headers())
        assert resp.status_code == 400, resp.text
        assert _PathRecordingHandler.paths == [], (
            f"backend was reached with {_PathRecordingHandler.paths!r} "
            f"despite the guard"
        )
    finally:
        server.close()


@pytest.mark.parametrize("path", TRAVERSAL_SPELLINGS)
def test_gateway_refuses_traversal_end_to_end(backend, path):
    gw = WorkflowAPIGateway(require_auth=False, title="issue-2087-gateway")
    try:
        gw.proxy_workflow(
            name="internal",
            proxy_url=backend,
            allowed_paths=["*"],
            auth_dependency=_allow,
        )
        client = TestClient(gw.app)
        resp = client.get(f"/internal/{path}", headers=_auth_headers())
        assert resp.status_code == 400, resp.text
        assert _PathRecordingHandler.paths == [], (
            f"backend was reached with {_PathRecordingHandler.paths!r} "
            f"despite the guard"
        )
    finally:
        gw.close()


def test_both_surfaces_still_forward_legitimate_semicolon(backend):
    """No-false-positive, end to end, on both surfaces.

    The backend RECORDS the path, so this asserts the request genuinely
    arrived rather than merely that the proxy returned 200.
    """
    server = WorkflowServer(title="issue-2087-server-ok", require_auth=False)
    server.proxy_workflow(
        name="internal",
        proxy_url=backend,
        allowed_paths=["*"],
        auth_dependency=_allow,
    )
    try:
        resp = TestClient(server.app).get(
            "/workflows/internal/products;color=blue/list", headers=_auth_headers()
        )
        assert resp.status_code == 200, resp.text
    finally:
        server.close()

    assert _PathRecordingHandler.paths == ["/products;color=blue/list"]

    _PathRecordingHandler.paths = []
    gw = WorkflowAPIGateway(require_auth=False, title="issue-2087-gateway-ok")
    try:
        gw.proxy_workflow(
            name="internal",
            proxy_url=backend,
            allowed_paths=["*"],
            auth_dependency=_allow,
        )
        resp = TestClient(gw.app).get(
            "/internal/products;color=blue/list", headers=_auth_headers()
        )
        assert resp.status_code == 200, resp.text
    finally:
        gw.close()

    assert _PathRecordingHandler.paths == ["/products;color=blue/list"]

# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression tests for the #2025 enforcement-surface-parity half.

``kailash.api.WorkflowAPIGateway.proxy_workflow`` is an INDEPENDENT surface
from ``kailash.servers.WorkflowServer.proxy_workflow`` with the same defect,
and a strictly worse one:

* mounted at ``/{name}/{path:path}`` -- one segment shallower;
* **seven** methods including HEAD and OPTIONS, not five;
* no path validation of any kind;
* and its header filter excluded only ``host``/``content-length``, so the
  caller's ``Authorization`` and ``Cookie`` were forwarded to whichever
  round-robin backend was selected.

``security.md`` § Enforcement-Surface Parity requires both surfaces to learn
the gate in the same change, through one shared implementation -- hence
``kailash.utils.proxy_guard``, which both import.

Fail-first, measured on the pre-fix source with one probe:

    REGISTRATION: accepted with NO auth argument
    UNAUTHENTICATED GET /internal/admin/users -> 200
    BODY: {"secret": "INTERNAL-BACKEND-DATA", "path": "/admin/users"}
    BACKEND SAW Authorization: Bearer caller-secret-token
    BACKEND SAW Cookie      : session=abc123
    UNAUTHENTICATED DELETE /internal/records/1 -> 200
    VERDICT: VULNERABLE - open proxy, destructive method reachable,
             AND caller credentials forwarded to the backend

Post-fix the same probe reports ``REGISTRATION: refused ->
ProxyAuthNotConfiguredError``.

No ``Mock`` appears in this file: the backend is a real HTTP server on a real
socket, and it records what it actually received.
"""

import gzip
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from starlette.requests import Request

from kailash.api.gateway import WorkflowAPIGateway
from kailash.utils.proxy_guard import ProxyAuthNotConfiguredError

pytestmark = pytest.mark.regression


class _RecordingHandler(BaseHTTPRequestHandler):
    """Real backend that records the credential headers it was handed."""

    received: dict = {}

    def _respond(self):
        type(self).received = {
            "authorization": self.headers.get("Authorization"),
            "cookie": self.headers.get("Cookie"),
            "x-api-key": self.headers.get("X-API-Key"),
        }
        payload = json.dumps({"method": self.command, "path": self.path}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    do_GET = _respond
    do_POST = _respond
    do_PUT = _respond
    do_DELETE = _respond
    do_PATCH = _respond

    def log_message(self, *args):  # noqa: D102 - silence stderr access log
        return


@pytest.fixture
def backend():
    _RecordingHandler.received = {}
    server = ThreadingHTTPServer(("127.0.0.1", 0), _RecordingHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


async def _allow(request: Request):
    """A real dependency, not a Mock: refuses without the header."""
    if request.headers.get("X-Regression-Key") != "let-me-in":
        raise HTTPException(status_code=401, detail="Not authenticated")
    return {"user_id": "keyed"}


@pytest.fixture
def gateway():
    gw = WorkflowAPIGateway(title="issue-2025-parity")
    try:
        yield gw
    finally:
        gw.close()


def _auth_headers():
    return {"X-Regression-Key": "let-me-in"}


# ---------------------------------------------------------------------------
# The gate
# ---------------------------------------------------------------------------


def test_gateway_registration_without_auth_is_refused(gateway, backend):
    """The parity half of #2025: this surface must refuse too."""
    with pytest.raises(ProxyAuthNotConfiguredError) as exc:
        gateway.proxy_workflow(name="internal", proxy_url=backend, allowed_paths=["*"])
    message = str(exc.value)
    assert "WorkflowAPIGateway" in message
    assert "auth_dependency" in message
    assert "internal" not in gateway.workflows
    assert not any(
        (getattr(route, "path", "") or "").startswith("/internal")
        for route in gateway.app.router.routes
    )


def test_gateway_unauthenticated_request_is_refused(gateway, backend):
    gateway.proxy_workflow(
        name="internal",
        proxy_url=backend,
        allowed_paths=["*"],
        auth_dependency=_allow,
    )
    client = TestClient(gateway.app)

    refused = client.get("/internal/admin/users")
    assert refused.status_code == 401, refused.text
    assert _RecordingHandler.received == {}, "backend was reached despite 401"

    # Discrimination control: same route, valid credential, 200 from backend.
    allowed = client.get("/internal/admin/users", headers=_auth_headers())
    assert allowed.status_code == 200, allowed.text
    assert allowed.json()["path"] == "/admin/users"


def test_gateway_auth_manager_path(backend):
    """The server-level manager wiring, mirroring WorkflowServer."""

    class Manager:
        def get_current_user_dependency(self):
            return _allow

    gw = WorkflowAPIGateway(title="mgr", auth_manager=Manager())
    try:
        gw.proxy_workflow(name="internal", proxy_url=backend, allowed_paths=["*"])
        client = TestClient(gw.app)
        assert client.get("/internal/x").status_code == 401
        assert client.get("/internal/x", headers=_auth_headers()).status_code == 200
    finally:
        gw.close()


def test_gateway_set_auth_manager_cannot_clear(gateway):
    with pytest.raises(ValueError):
        gateway.set_auth_manager(None)


def test_gateway_declare_external_auth(gateway, backend, caplog):
    with pytest.raises(ValueError):
        gateway.declare_external_auth("  ")

    gateway.declare_external_auth("JWT middleware installed by the deployment")
    with caplog.at_level("WARNING"):
        gateway.proxy_workflow(name="internal", proxy_url=backend, allowed_paths=["*"])
    assert any(
        "NO route-level authentication" in r.getMessage() for r in caplog.records
    ), [r.getMessage() for r in caplog.records]


# ---------------------------------------------------------------------------
# Credential forwarding -- the defect unique to THIS surface
# ---------------------------------------------------------------------------


def test_caller_credentials_are_not_forwarded_by_default(gateway, backend):
    """Before #2025 this gateway handed the caller's credentials to the backend."""
    gateway.proxy_workflow(
        name="internal",
        proxy_url=backend,
        allowed_paths=["*"],
        auth_dependency=_allow,
    )
    client = TestClient(gateway.app)

    response = client.get(
        "/internal/data",
        headers={
            **_auth_headers(),
            "Authorization": "Bearer caller-secret-token",
            "Cookie": "session=abc123",
            "X-API-Key": "caller-api-key",
        },
    )

    assert response.status_code == 200, response.text
    assert _RecordingHandler.received["authorization"] is None
    assert _RecordingHandler.received["cookie"] is None
    assert _RecordingHandler.received["x-api-key"] is None


def test_credential_forwarding_is_available_as_an_explicit_opt_in(gateway, backend):
    """Backends that must re-authorize the caller can still be given the token."""
    gateway.proxy_workflow(
        name="internal",
        proxy_url=backend,
        allowed_paths=["*"],
        auth_dependency=_allow,
        forward_credentials=True,
    )
    client = TestClient(gateway.app)

    response = client.get(
        "/internal/data",
        headers={**_auth_headers(), "Authorization": "Bearer caller-secret-token"},
    )

    assert response.status_code == 200, response.text
    assert _RecordingHandler.received["authorization"] == "Bearer caller-secret-token"


# ---------------------------------------------------------------------------
# Method and path allowlists, traversal
# ---------------------------------------------------------------------------


def test_gateway_default_methods_are_get_only(gateway, backend):
    """Was seven verbs including HEAD and OPTIONS; now GET unless named."""
    gateway.proxy_workflow(
        name="internal",
        proxy_url=backend,
        allowed_paths=["*"],
        auth_dependency=_allow,
    )
    client = TestClient(gateway.app)
    h = _auth_headers()

    assert client.delete("/internal/records/1", headers=h).status_code == 405
    assert client.post("/internal/x", headers=h).status_code == 405
    assert client.put("/internal/x", headers=h).status_code == 405
    assert client.patch("/internal/x", headers=h).status_code == 405
    assert client.get("/internal/x", headers=h).status_code == 200


def test_gateway_opted_in_method_is_forwarded(gateway, backend):
    gateway.proxy_workflow(
        name="internal",
        proxy_url=backend,
        allowed_paths=["*"],
        allowed_methods=["GET", "DELETE"],
        auth_dependency=_allow,
    )
    client = TestClient(gateway.app)
    response = client.delete("/internal/records/1", headers=_auth_headers())
    assert response.status_code == 200, response.text
    assert response.json()["method"] == "DELETE"


def test_gateway_path_allowlist(gateway, backend):
    gateway.proxy_workflow(
        name="internal",
        proxy_url=backend,
        allowed_paths=["reports/*"],
        auth_dependency=_allow,
    )
    client = TestClient(gateway.app)
    h = _auth_headers()

    assert client.get("/internal/admin/users", headers=h).status_code == 404
    assert client.get("/internal/reports/q3", headers=h).status_code == 200


def test_gateway_allowed_paths_is_required(gateway, backend):
    with pytest.raises(ValueError) as exc:
        gateway.proxy_workflow(
            name="internal", proxy_url=backend, auth_dependency=_allow
        )
    assert "allowed_paths" in str(exc.value)


def test_gateway_traversal_and_charset_are_refused(gateway, backend):
    gateway.proxy_workflow(
        name="internal",
        proxy_url=backend,
        allowed_paths=["*"],
        auth_dependency=_allow,
    )
    client = TestClient(gateway.app)
    h = _auth_headers()

    # httpx collapses a literal `..` client-side, so send the encoded form.
    traversal = client.get("/internal/%2e%2e/%2e%2e/etc/passwd", headers=h)
    assert traversal.status_code == 400, traversal.text
    assert "parent-directory" in traversal.text

    # A SPACE isolates the charset barrier: earlier checks do not reject it.
    space = client.get("/internal/a%20b", headers=h)
    assert space.status_code == 400, space.text
    assert "may not be forwarded" in space.text

    assert _RecordingHandler.received == {}, "a refused path still reached the backend"


def test_gateway_repeated_query_keys_are_preserved(gateway, backend):
    gateway.proxy_workflow(
        name="internal",
        proxy_url=backend,
        allowed_paths=["*"],
        auth_dependency=_allow,
    )
    client = TestClient(gateway.app)
    response = client.get("/internal/search?tag=a&tag=b", headers=_auth_headers())
    assert response.status_code == 200, response.text
    path = response.json()["path"]
    assert "tag=a" in path and "tag=b" in path, path


# ---------------------------------------------------------------------------
# Query-parameter override of the handler's closure captures
# ---------------------------------------------------------------------------


def test_gateway_backends_cannot_be_overridden_by_query_parameter(gateway, backend):
    """`?_backends=...` MUST NOT redirect the forward.

    Same root cause as the server surface: FastAPI treats a handler parameter
    carrying a plain default as a QUERY parameter, so `_backends=backends`
    made the destination caller-writable.
    """
    gateway.proxy_workflow(
        name="internal",
        proxy_url=backend,
        allowed_paths=["*"],
        auth_dependency=_allow,
    )
    client = TestClient(gateway.app)
    h = _auth_headers()

    normal = client.get("/internal/data", headers=h)
    assert normal.status_code == 200, normal.text

    attack = client.get("/internal/data?_backends=http://127.0.0.1:9", headers=h)
    assert attack.status_code == 200, attack.text
    assert attack.json()["method"] == "GET"


def test_gateway_proxy_handler_exposes_no_query_parameters(gateway, backend):
    """Structural guard against reintroducing closure capture via defaults."""
    import inspect

    gateway.proxy_workflow(
        name="internal",
        proxy_url=backend,
        allowed_paths=["*"],
        auth_dependency=_allow,
    )
    route = next(
        r
        for r in gateway.app.router.routes
        if getattr(r, "path", "") == "/internal/{path:path}"
    )
    params = inspect.signature(route.endpoint).parameters
    assert set(params) == {"request", "path"}, (
        f"handler exposes unexpected parameters {set(params)}; any parameter "
        f"with a plain default becomes a caller-writable query parameter"
    )
    assert all(p.default is inspect.Parameter.empty for p in params.values())


# ---------------------------------------------------------------------------
# Redirect following and response framing on this surface (security review)
# ---------------------------------------------------------------------------


class _GatewayRedirectHandler(BaseHTTPRequestHandler):
    redirect_to = ""

    def do_GET(self):
        if self.path.startswith("/api/login"):
            self.send_response(302)
            self.send_header("Location", type(self).redirect_to)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        payload = gzip.compress(json.dumps({"who": "legitimate-backend"}).encode())
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Content-Encoding", "gzip")
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args):  # noqa: D102
        return


class _GatewayOffHost(BaseHTTPRequestHandler):
    def do_GET(self):
        payload = json.dumps({"secret": "OFF-HOST-PIVOT-BODY"}).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args):  # noqa: D102
        return


@pytest.fixture
def gateway_redirecting_backend():
    off_host = ThreadingHTTPServer(("127.0.0.1", 0), _GatewayOffHost)
    t1 = threading.Thread(target=off_host.serve_forever, daemon=True)
    t1.start()
    _GatewayRedirectHandler.redirect_to = (
        f"http://127.0.0.1:{off_host.server_address[1]}/meta"
    )
    backend = ThreadingHTTPServer(("127.0.0.1", 0), _GatewayRedirectHandler)
    t2 = threading.Thread(target=backend.serve_forever, daemon=True)
    t2.start()
    try:
        yield f"http://127.0.0.1:{backend.server_address[1]}"
    finally:
        for srv, thread in ((backend, t2), (off_host, t1)):
            srv.shutdown()
            srv.server_close()
            thread.join(timeout=5)


def test_gateway_backend_redirect_is_not_followed(gateway, gateway_redirecting_backend):
    """Parity with the server surface. httpx defaults follow_redirects=False,
    but the client now states it explicitly rather than inheriting a default
    that can change -- and the sibling surface's aiohttp defaults it to True.
    """
    gateway.proxy_workflow(
        name="internal",
        proxy_url=gateway_redirecting_backend,
        allowed_paths=["api/*"],
        auth_dependency=_allow,
    )
    client = TestClient(gateway.app)

    response = client.get(
        "/internal/api/login?next=http://169.254.169.254/latest/",
        headers=_auth_headers(),
        follow_redirects=False,
    )
    assert "OFF-HOST-PIVOT-BODY" not in response.text
    assert response.status_code == 302

    ok = client.get("/internal/api/data", headers=_auth_headers())
    assert ok.status_code == 200, ok.text


def test_gateway_response_framing_headers_are_not_echoed(
    gateway, gateway_redirecting_backend
):
    """`resp.content` is decompressed; echoing Content-Encoding mislabels it."""
    gateway.proxy_workflow(
        name="internal",
        proxy_url=gateway_redirecting_backend,
        allowed_paths=["*"],
        auth_dependency=_allow,
    )
    client = TestClient(gateway.app)

    response = client.get("/internal/api/data", headers=_auth_headers())
    assert response.status_code == 200, response.text
    assert "content-encoding" not in {k.lower() for k in response.headers}

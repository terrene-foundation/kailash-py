# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression tests for issue #2025 -- unauthenticated workflow-server proxy.

``WorkflowServer.proxy_workflow`` registered a catch-all reverse proxy at
``/workflows/{name}/{path:path}`` for five HTTP methods with no authentication
anywhere on the path, forwarding arbitrary methods, paths and query strings to
the proxied backend and returning the body.

These tests are **behavioural**: they drive a real ASGI stack via
``TestClient``, forward to a **real HTTP backend** bound to a real socket, and
assert on status codes. No ``Mock`` appears anywhere in this file -- a ``Mock``
satisfies every ``hasattr`` and accepts every call, which is precisely how the
inert auth control in #2013 shipped green.

Fail-first evidence (recorded in the PR). Pinned to the pre-fix source, this
suite fails at collection -- ``ImportError: cannot import name
'ProxyAuthNotConfiguredError'`` naming the pre-fix path, which is what proves
the pin took effect. Because a collection error reports on the symbol and not
on the behaviour, the behavioural half was measured with a standalone probe
that runs unchanged against both trees: pre-fix it registers a proxy with no
auth argument and an unauthenticated ``GET /workflows/internal/admin/users``
returns 200 with the backend's body; post-fix registration raises.

Discrimination control: :meth:`test_authenticated_request_is_forwarded` hits
the SAME route with a valid token and gets 200 with the backend's body, so the
401 in the sibling test comes from authentication and not from a broken route.
"""

import asyncio
import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from starlette.requests import Request

from kailash.middleware.auth import MiddlewareAuthManager
from kailash.servers import (
    DurableWorkflowServer,
    EnterpriseWorkflowServer,
    ProxyAuthNotConfiguredError,
    WorkflowServer,
)
from kailash.servers.proxy_guard import (
    SAFE_FORWARD_PATH_RE,
    compile_path_allowlist,
    normalize_allowed_methods,
    path_matches_allowlist,
    reject_unsafe_proxy_path,
)

pytestmark = pytest.mark.regression

_SECRET = "issue-2025-regression-secret-key-at-least-32-bytes"


class _EchoHandler(BaseHTTPRequestHandler):
    """Real backend: echoes the method, path and RAW query string it saw."""

    def _respond(self):
        path, _, query = self.path.partition("?")
        payload = json.dumps(
            {"method": self.command, "path": path, "raw_query": query}
        ).encode()
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
    """A real HTTP server on a real socket -- no mocking (rules/testing.md)."""
    server = ThreadingHTTPServer(("127.0.0.1", 0), _EchoHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.fixture
def auth_manager():
    """The SHIPPED auth manager, minting real HS256 tokens."""
    return MiddlewareAuthManager(
        secret_key=_SECRET,
        enable_audit=False,
        enable_api_keys=False,
    )


@pytest.fixture
def server(auth_manager):
    srv = WorkflowServer(title="issue-2025", auth_manager=auth_manager)
    try:
        yield srv
    finally:
        srv.close()


async def _token(auth_manager, permissions=None):
    return await auth_manager.create_access_token(
        "regression-user", permissions=permissions or []
    )


# ---------------------------------------------------------------------------
# The gate itself
# ---------------------------------------------------------------------------


def test_registration_without_auth_is_refused():
    """A proxy MUST NOT be registrable on a server with no auth configured.

    This is the core of #2025. On the pre-fix source this call returns None and
    the route is live and open.
    """
    srv = WorkflowServer(title="no-auth")
    try:
        with pytest.raises(ProxyAuthNotConfiguredError) as exc:
            srv.proxy_workflow(
                name="backend",
                proxy_url="http://internal-service:8080",
                allowed_paths=["*"],
            )
        message = str(exc.value)
        # The error must name every accepted wiring, not merely refuse.
        assert "auth_dependency" in message
        assert "set_auth_manager" in message
        assert "declare_external_auth" in message
        # And the refusal must leave no half-registered proxy behind.
        assert "backend" not in srv.workflows
        assert not any(
            (getattr(route, "path", "") or "").startswith("/workflows/backend")
            for route in srv.app.router.routes
        )
    finally:
        srv.close()


def test_unauthenticated_request_is_refused(server, backend):
    """An unauthenticated GET to the proxy route MUST NOT reach the backend."""
    server.proxy_workflow(name="internal", proxy_url=backend, allowed_paths=["*"])
    client = TestClient(server.app)

    response = client.get("/workflows/internal/admin/users")

    assert response.status_code == 401, response.text
    # The backend's echo body must not appear in the response.
    assert "raw_query" not in response.text


def test_authenticated_request_is_forwarded(server, backend, auth_manager):
    """Discrimination control: same route, valid token, 200 from the backend.

    Without this, the 401 above could equally be a broken route.
    """
    server.proxy_workflow(name="internal", proxy_url=backend, allowed_paths=["*"])
    client = TestClient(server.app)
    token = asyncio.run(_token(auth_manager))

    response = client.get(
        "/workflows/internal/admin/users",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["path"] == "/admin/users"


def test_invalid_token_is_refused(server, backend):
    """A malformed bearer token MUST be refused, not passed through."""
    server.proxy_workflow(name="internal", proxy_url=backend, allowed_paths=["*"])
    client = TestClient(server.app)

    response = client.get(
        "/workflows/internal/status",
        headers={"Authorization": "Bearer not-a-real-token"},
    )

    assert response.status_code == 401, response.text


def test_explicit_auth_dependency_is_honoured(backend):
    """A per-registration dependency protects the route with no server manager."""

    async def require_key(request: Request):
        if request.headers.get("X-Regression-Key") != "let-me-in":
            raise HTTPException(status_code=403, detail="Forbidden")
        return {"user_id": "keyed"}

    srv = WorkflowServer(title="dep-only")
    try:
        srv.proxy_workflow(
            name="internal",
            proxy_url=backend,
            allowed_paths=["*"],
            auth_dependency=require_key,
        )
        client = TestClient(srv.app)

        assert client.get("/workflows/internal/status").status_code == 403
        allowed = client.get(
            "/workflows/internal/status",
            headers={"X-Regression-Key": "let-me-in"},
        )
        assert allowed.status_code == 200, allowed.text
    finally:
        srv.close()


def test_auth_manager_without_dependency_factory_is_refused(backend):
    """An auth manager that cannot produce a dependency MUST fail closed.

    The pre-#2013 shape was a ``hasattr`` guard whose False branch continued
    silently. Here the absent factory raises.
    """

    class NotAnAuthManager:
        """Looks configured, authenticates nothing."""

    srv = WorkflowServer(title="bad-manager", auth_manager=NotAnAuthManager())
    try:
        with pytest.raises(ProxyAuthNotConfiguredError) as exc:
            srv.proxy_workflow(name="internal", proxy_url=backend, allowed_paths=["*"])
        assert "get_current_user_dependency" in str(exc.value)
    finally:
        srv.close()


def test_declare_external_auth_permits_registration_and_warns(backend, caplog):
    """The declared-external-auth escape is explicit, logged, and reason-bound."""
    srv = WorkflowServer(title="external")
    try:
        with pytest.raises(ValueError):
            srv.declare_external_auth("   ")

        srv.declare_external_auth("nexus JWTMiddleware installed on this app")
        with caplog.at_level("WARNING"):
            srv.proxy_workflow(name="internal", proxy_url=backend, allowed_paths=["*"])
        assert any(
            "NO route-level authentication" in record.getMessage()
            for record in caplog.records
        ), [r.getMessage() for r in caplog.records]
    finally:
        srv.close()


def test_set_auth_manager_cannot_clear_auth(auth_manager):
    """Clearing the manager would silently widen later registrations."""
    srv = WorkflowServer(title="clear", auth_manager=auth_manager)
    try:
        with pytest.raises(ValueError):
            srv.set_auth_manager(None)
    finally:
        srv.close()


@pytest.mark.parametrize(
    "server_cls", [DurableWorkflowServer, EnterpriseWorkflowServer]
)
def test_subclasses_inherit_the_gate(server_cls, backend):
    """Enforcement-surface parity: both subclasses inherit proxy_workflow."""
    srv = server_cls(title=f"parity-{server_cls.__name__}")
    try:
        with pytest.raises(ProxyAuthNotConfiguredError):
            srv.proxy_workflow(name="internal", proxy_url=backend, allowed_paths=["*"])
    finally:
        srv.close()


# ---------------------------------------------------------------------------
# Method allowlist
# ---------------------------------------------------------------------------


def test_method_outside_allowlist_is_refused(server, backend, auth_manager):
    """DELETE MUST be refused when the allowlist omits it -- even authenticated."""
    server.proxy_workflow(
        name="internal",
        proxy_url=backend,
        allowed_paths=["*"],
        allowed_methods=["GET"],
    )
    client = TestClient(server.app)
    headers = {"Authorization": f"Bearer {asyncio.run(_token(auth_manager))}"}

    refused = client.delete("/workflows/internal/records/1", headers=headers)
    assert refused.status_code == 405, refused.text

    # Control: GET on the same path with the same credentials succeeds.
    allowed = client.get("/workflows/internal/records/1", headers=headers)
    assert allowed.status_code == 200, allowed.text


def test_default_method_allowlist_is_get_only(server, backend, auth_manager):
    """Omitting allowed_methods MUST default to GET, not all five verbs."""
    server.proxy_workflow(name="internal", proxy_url=backend, allowed_paths=["*"])
    client = TestClient(server.app)
    headers = {"Authorization": f"Bearer {asyncio.run(_token(auth_manager))}"}

    assert client.post("/workflows/internal/x", headers=headers).status_code == 405
    assert client.put("/workflows/internal/x", headers=headers).status_code == 405
    assert client.patch("/workflows/internal/x", headers=headers).status_code == 405
    assert client.delete("/workflows/internal/x", headers=headers).status_code == 405
    assert client.get("/workflows/internal/x", headers=headers).status_code == 200


def test_opted_in_write_method_is_forwarded(server, backend, auth_manager):
    """A registration that names POST forwards POST bodies."""
    server.proxy_workflow(
        name="internal",
        proxy_url=backend,
        allowed_paths=["*"],
        allowed_methods=["GET", "POST"],
    )
    client = TestClient(server.app)
    headers = {"Authorization": f"Bearer {asyncio.run(_token(auth_manager))}"}

    response = client.post("/workflows/internal/submit", headers=headers, json={"a": 1})
    assert response.status_code == 200, response.text
    assert response.json()["method"] == "POST"


# ---------------------------------------------------------------------------
# Path allowlist and traversal
# ---------------------------------------------------------------------------


def test_allowed_paths_is_required(server, backend):
    """The catch-all is no longer implicit."""
    with pytest.raises(ValueError) as exc:
        server.proxy_workflow(name="internal", proxy_url=backend)
    assert "allowed_paths" in str(exc.value)
    assert "['*']" in str(exc.value)


def test_path_outside_allowlist_is_refused(server, backend, auth_manager):
    """An authenticated caller still cannot reach a path outside the allowlist."""
    server.proxy_workflow(
        name="internal",
        proxy_url=backend,
        allowed_paths=["reports/*"],
    )
    client = TestClient(server.app)
    headers = {"Authorization": f"Bearer {asyncio.run(_token(auth_manager))}"}

    refused = client.get("/workflows/internal/admin/users", headers=headers)
    assert refused.status_code == 404, refused.text

    allowed = client.get("/workflows/internal/reports/q3", headers=headers)
    assert allowed.status_code == 200, allowed.text


def test_traversal_path_is_refused(server, backend, auth_manager):
    """A `..` segment MUST be refused before the target URL is built."""
    server.proxy_workflow(name="internal", proxy_url=backend, allowed_paths=["*"])
    client = TestClient(server.app)
    headers = {"Authorization": f"Bearer {asyncio.run(_token(auth_manager))}"}

    # httpx collapses a literal `..` client-side before the request is sent,
    # so the encoded form is BOTH the faithful attack shape and the only one
    # that reaches the handler at all. Starlette decodes it once, so the
    # handler sees `../../etc/passwd`.
    response = client.get(
        "/workflows/internal/%2e%2e/%2e%2e/etc/passwd",
        headers=headers,
    )
    assert response.status_code == 400, response.text
    assert "parent-directory" in response.text

    # Double-encoded. Measured: httpx decodes `%25` -> `%` before sending, so
    # the wire carries `%2e%2e` and Starlette's decode yields `..` -- the
    # parent-directory branch fires here, not the encoded-token branch. Both
    # refuse. The encoded-token branch, which fires when `%2e%2e` reaches the
    # handler still encoded (a raw client that does not pre-decode), is
    # covered directly by test_reject_unsafe_proxy_path.
    double = client.get(
        "/workflows/internal/%252e%252e/etc/passwd",
        headers=headers,
    )
    assert double.status_code == 400, double.text
    assert "Invalid proxy path" in double.text


def test_repeated_query_keys_are_preserved(server, backend, auth_manager):
    """dict(query_params) dropped every duplicate key but the last."""
    server.proxy_workflow(name="internal", proxy_url=backend, allowed_paths=["*"])
    client = TestClient(server.app)
    headers = {"Authorization": f"Bearer {asyncio.run(_token(auth_manager))}"}

    response = client.get("/workflows/internal/search?tag=a&tag=b", headers=headers)
    assert response.status_code == 200, response.text
    raw_query = response.json()["raw_query"]
    assert "tag=a" in raw_query and "tag=b" in raw_query, raw_query


# ---------------------------------------------------------------------------
# proxy_guard primitives -- every branch of the shared helper
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path,expected",
    [
        ("reports/q3", None),
        ("", None),
        ("a/../b", "path contains a parent-directory segment (..)"),
        ("..", "path contains a parent-directory segment (..)"),
        ("a/%2e%2e/b", "path contains an encoded path separator or dot-segment (%2e)"),
        ("a%2Fb", "path contains an encoded path separator or dot-segment (%2f)"),
        ("a%5Cb", "path contains an encoded path separator or dot-segment (%5c)"),
        ("a\\b", "path contains a backslash"),
        ("a\x00b", "path contains a null byte"),
        ("a\rb", "path contains a control character"),
        # A dotfile is not traversal and MUST still be forwardable.
        (".well-known/x", None),
    ],
)
def test_reject_unsafe_proxy_path(path, expected):
    assert reject_unsafe_proxy_path(path) == expected


@pytest.mark.parametrize(
    "value",
    [
        "a b",  # SPACE
        "a\rb",  # CR  -- request-line injection vector
        "a\nb",  # LF  -- request-line injection vector
        "a\tb",
        "a\x00b",
        "a\x7fb",
        "a\\b",
        "a<b",
        "a>b",
        "a?b",
        "a#b",
        "a{b",
        "a|b",
        "a^b",
        "a`b",
        'a"b',
    ],
)
def test_safe_forward_path_charset_rejects(value):
    """The positive charset barrier refuses everything outside RFC 3986 pchar.

    Asserted against the COMPILED module constant, never a retyped copy of the
    pattern: a retyped pattern is a different string and would not report on
    what the module actually does.
    """
    assert SAFE_FORWARD_PATH_RE.fullmatch(value) is None


@pytest.mark.parametrize(
    "value",
    [
        "a/b",
        "",
        ".well-known/acme-challenge/token",
        "a%2eb",
        "a!$&'()*+,;=:@b",
        "a-b",
        "a~b",
        "café/x",  # internationalized paths still forward
        "文件/x",
    ],
)
def test_safe_forward_path_charset_accepts(value):
    assert SAFE_FORWARD_PATH_RE.fullmatch(value) is not None


def test_charset_rejection_over_http(server, backend, auth_manager):
    """The charset barrier refuses end-to-end, before any forward.

    A SPACE is used rather than a CR because it isolates THIS barrier:
    ``reject_unsafe_proxy_path`` runs first and already refuses control
    characters, so a CR would not tell us which layer fired. A space passes
    every earlier check and is stopped only by the charset allowlist.
    """
    server.proxy_workflow(name="internal", proxy_url=backend, allowed_paths=["*"])
    client = TestClient(server.app)
    headers = {"Authorization": f"Bearer {asyncio.run(_token(auth_manager))}"}

    # %20 decodes to SPACE at the handler.
    response = client.get("/workflows/internal/a%20b", headers=headers)
    assert response.status_code == 400, response.text
    assert "may not be forwarded" in response.text

    # Control: the same path without the space forwards normally, so the 400
    # above is the charset barrier and not a broken route.
    ok = client.get("/workflows/internal/ab", headers=headers)
    assert ok.status_code == 200, ok.text

    # A CR is refused too; the earlier control-character check owns that one.
    cr = client.get("/workflows/internal/a%0db", headers=headers)
    assert cr.status_code == 400, cr.text
    assert "control character" in cr.text


def test_path_allowlist_matching_semantics():
    allowlist = compile_path_allowlist(
        ["status", "/reports/*", "v1-", re.compile(r"jobs/\d+")], name="x"
    )
    assert path_matches_allowlist("status", allowlist)
    assert path_matches_allowlist("/status", allowlist)
    assert not path_matches_allowlist("status/extra", allowlist)
    assert path_matches_allowlist("reports", allowlist)
    assert path_matches_allowlist("reports/q3/detail", allowlist)
    assert not path_matches_allowlist("reportsX", allowlist)
    assert path_matches_allowlist("jobs/42", allowlist)
    assert not path_matches_allowlist("jobs/abc", allowlist)
    assert not path_matches_allowlist("admin", allowlist)


def test_path_allowlist_wildcard_is_explicit():
    assert path_matches_allowlist(
        "anything/at/all", compile_path_allowlist(["*"], name="x")
    )


def test_empty_allowlist_matches_nothing():
    """Deny-by-default: a construction bug MUST NOT open the route."""
    assert not path_matches_allowlist("anything", [])


@pytest.mark.parametrize("bad", [None, [], "status", re.compile("x"), [""], [7]])
def test_compile_path_allowlist_rejects_bad_input(bad):
    with pytest.raises(ValueError):
        compile_path_allowlist(bad, name="x")


def test_normalize_allowed_methods():
    assert normalize_allowed_methods(None, name="x") == ["GET"]
    assert normalize_allowed_methods(["post", "get"], name="x") == ["GET", "POST"]
    with pytest.raises(ValueError):
        normalize_allowed_methods([], name="x")
    with pytest.raises(ValueError):
        normalize_allowed_methods("GET", name="x")
    with pytest.raises(ValueError):
        normalize_allowed_methods(["TRACE"], name="x")
    with pytest.raises(ValueError):
        normalize_allowed_methods(
            ["HEAD"], name="x", supported=("GET", "POST", "PUT", "DELETE", "PATCH")
        )

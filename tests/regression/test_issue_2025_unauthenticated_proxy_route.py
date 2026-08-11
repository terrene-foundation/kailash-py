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
import gzip
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
from kailash.utils.proxy_guard import (
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


class _AttackerHandler(BaseHTTPRequestHandler):
    """Stands in for a host the caller would like the proxy redirected to."""

    def do_GET(self):
        payload = json.dumps({"who": "ATTACKER-CONTROLLED-HOST"}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args):  # noqa: D102
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


class _CredentialRecordingHandler(BaseHTTPRequestHandler):
    """Real backend that records the credential headers it was handed."""

    received: dict = {}

    def do_GET(self):
        type(self).received = {
            "authorization": self.headers.get("Authorization"),
            "cookie": self.headers.get("Cookie"),
            "x-api-key": self.headers.get("X-API-Key"),
        }
        payload = json.dumps({"ok": True}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args):  # noqa: D102
        return


@pytest.fixture
def recording_backend():
    _CredentialRecordingHandler.received = {}
    server = ThreadingHTTPServer(("127.0.0.1", 0), _CredentialRecordingHandler)
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
        # C1 controls. These reach the helper decoded and are line
        # terminators to several parsers, so they are the same injection
        # vector as CR/LF. Asserted HERE and not only against the charset
        # regex: a mutation dropping the helper's C1 arm reddened nothing
        # while these cases lived only in the regex parametrisation, which
        # meant the helper's branch was unmeasured.
        ("a\u0080b", "path contains a control character"),
        ("a\u0085b", "path contains a control character"),
        ("a\u009fb", "path contains a control character"),
        # Unicode line/paragraph separators get their own reason.
        ("a\u2028b", "path contains a Unicode line or paragraph separator"),
        ("a\u2029b", "path contains a Unicode line or paragraph separator"),
        # Immediately outside the excluded ranges -- still forwardable.
        ("a\u00a0b", None),
        ("a\u2027b", None),
        ("a\u202ab", None),
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
        "a\u0080b",  # C1 block
        "a\u0085b",  # NEL -- a line terminator to several parsers
        "a\u009fb",  # C1 block, upper bound
        "a\u2028b",  # Unicode LINE SEPARATOR
        "a\u2029b",  # Unicode PARAGRAPH SEPARATOR
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
        "a\u00a0b",  # NBSP is the first codepoint ABOVE the excluded C1 block
        "a\u2027b",  # immediately below U+2028
        "a\u202ab",  # immediately above U+2029
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


# ---------------------------------------------------------------------------
# Query-parameter override of the handler's closure captures -- FULL SSRF
# ---------------------------------------------------------------------------


def test_destination_cannot_be_overridden_by_query_parameter(
    server, backend, auth_manager
):
    """`?_url=http://attacker/` MUST NOT redirect the proxy. This was live.

    FastAPI inspects the handler signature and treats any non-path parameter
    carrying a plain default as a QUERY parameter. The handler captured its
    destination as `_url=proxy_url`, so the destination was caller-writable:
    an authenticated caller could point the proxy at any host they liked.

    Measured on the pre-fix source, with a second HTTP server standing in for
    the attacker's host:

        NORMAL   -> {"who": "legitimate-backend"}
        ?_url=   -> {"who": "ATTACKER-CONTROLLED-HOST"}

    This is FULL SSRF -- not the "partial" the CodeQL alert was rated, and
    not the "no authority pivot is constructible" the issue analysis asserted.
    """
    attacker = ThreadingHTTPServer(("127.0.0.1", 0), _AttackerHandler)
    thread = threading.Thread(target=attacker.serve_forever, daemon=True)
    thread.start()
    attacker_url = f"http://127.0.0.1:{attacker.server_address[1]}"
    try:
        server.proxy_workflow(name="internal", proxy_url=backend, allowed_paths=["*"])
        client = TestClient(server.app)
        headers = {"Authorization": f"Bearer {asyncio.run(_token(auth_manager))}"}

        # Control: the normal request reaches the registered backend.
        normal = client.get("/workflows/internal/data", headers=headers)
        assert normal.status_code == 200, normal.text
        assert "ATTACKER" not in normal.text

        # The attack: the destination must stay the registered backend.
        attack = client.get(
            f"/workflows/internal/data?_url={attacker_url}", headers=headers
        )
        assert attack.status_code == 200, attack.text
        assert (
            "ATTACKER-CONTROLLED-HOST" not in attack.text
        ), "SSRF: the caller redirected the proxy to an arbitrary host"
    finally:
        attacker.shutdown()
        attacker.server_close()
        thread.join(timeout=5)


def test_allowlist_cannot_be_overridden_by_query_parameter(
    server, backend, auth_manager
):
    """The path allowlist was captured the same way and was equally writable."""
    server.proxy_workflow(
        name="internal", proxy_url=backend, allowed_paths=["reports/*"]
    )
    client = TestClient(server.app)
    headers = {"Authorization": f"Bearer {asyncio.run(_token(auth_manager))}"}

    blocked = client.get("/workflows/internal/admin/users", headers=headers)
    assert blocked.status_code == 404, blocked.text

    # Attempting to widen the allowlist from the query string must not work.
    still_blocked = client.get(
        "/workflows/internal/admin/users?_allowlist=*", headers=headers
    )
    assert still_blocked.status_code == 404, still_blocked.text


def test_proxy_handler_exposes_no_query_parameters(server, backend):
    """Structural guard: the handler must declare only `request` and `path`.

    A future edit that reintroduces `_x=captured` closure capture would make
    that value caller-writable again. Asserting the signature catches it at
    the source rather than relying on someone writing the matching attack.
    """
    import inspect

    server.proxy_workflow(name="internal", proxy_url=backend, allowed_paths=["*"])
    route = next(
        r
        for r in server.app.router.routes
        if getattr(r, "path", "") == "/workflows/internal/{path:path}"
    )
    params = inspect.signature(route.endpoint).parameters
    assert set(params) == {"request", "path"}, (
        f"handler exposes unexpected parameters {set(params)}; any parameter "
        f"with a plain default becomes a caller-writable query parameter"
    )
    assert all(
        p.default is inspect.Parameter.empty for p in params.values()
    ), "a defaulted handler parameter is a caller-writable query parameter"


# ---------------------------------------------------------------------------
# Credential forwarding on THIS surface
# ---------------------------------------------------------------------------


def test_credentials_are_stripped_by_default(server, recording_backend, auth_manager):
    """The default MUST strip the caller's credentials before forwarding.

    Driven end to end rather than asserted structurally: this branch decides
    whether `Authorization` reaches the backend, so a name error or an
    inverted condition here is a real disclosure. A backend that records what
    it actually received is the only instrument that can tell the difference.
    """
    server.proxy_workflow(
        name="internal", proxy_url=recording_backend, allowed_paths=["*"]
    )
    client = TestClient(server.app)
    token = asyncio.run(_token(auth_manager))

    response = client.get(
        "/workflows/internal/data",
        headers={
            "Authorization": f"Bearer {token}",
            "Cookie": "session=abc123",
            "X-API-Key": "caller-api-key",
        },
    )

    assert response.status_code == 200, response.text
    assert _CredentialRecordingHandler.received["authorization"] is None
    assert _CredentialRecordingHandler.received["cookie"] is None
    assert _CredentialRecordingHandler.received["x-api-key"] is None


def test_forward_credentials_opt_in_reaches_the_backend(
    server, recording_backend, auth_manager
):
    """#2025 noted that stripping unconditionally left the backend unable to
    re-authorize. `forward_credentials=True` is the documented way to allow it.

    This is the opposite polarity of the test above: without it, a branch that
    stripped in BOTH cases would pass the default test and the opt-in would be
    silently dead.
    """
    token = asyncio.run(_token(auth_manager))
    server.proxy_workflow(
        name="internal",
        proxy_url=recording_backend,
        allowed_paths=["*"],
        forward_credentials=True,
    )
    client = TestClient(server.app)

    response = client.get(
        "/workflows/internal/data", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 200, response.text
    assert _CredentialRecordingHandler.received["authorization"] == f"Bearer {token}"


# ---------------------------------------------------------------------------
# Redirect following, hop-by-hop headers, response framing (security review)
# ---------------------------------------------------------------------------


class _RedirectingHandler(BaseHTTPRequestHandler):
    """A backend with the open redirect that is ubiquitous under `api/`."""

    redirect_to = ""
    hop_by_hop_seen: dict = {}

    def do_GET(self):
        type(self).hop_by_hop_seen = {
            "transfer-encoding": self.headers.get("Transfer-Encoding"),
            "connection": self.headers.get("Connection"),
            "te": self.headers.get("TE"),
            "upgrade": self.headers.get("Upgrade"),
            "expect": self.headers.get("Expect"),
        }
        if self.path.startswith("/api/login"):
            self.send_response(302)
            self.send_header("Location", type(self).redirect_to)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        # GENUINELY gzipped, so the HTTP client decompresses successfully and
        # the test measures what the proxy echoes rather than a decode error.
        # This is the realistic shape: the client hands the handler PLAINTEXT
        # bytes while the backend's Content-Encoding/Content-Length still
        # describe the COMPRESSED form.
        payload = gzip.compress(json.dumps({"who": "legitimate-backend"}).encode())
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Content-Encoding", "gzip")
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args):  # noqa: D102
        return


class _OffHostHandler(BaseHTTPRequestHandler):
    """Stands in for a host the caller would like to reach, e.g. metadata."""

    hit_count = 0

    def do_GET(self):
        type(self).hit_count += 1
        payload = json.dumps({"secret": "OFF-HOST-PIVOT-BODY"}).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args):  # noqa: D102
        return


@pytest.fixture
def redirecting_backend():
    off_host = ThreadingHTTPServer(("127.0.0.1", 0), _OffHostHandler)
    t1 = threading.Thread(target=off_host.serve_forever, daemon=True)
    t1.start()
    _RedirectingHandler.redirect_to = (
        f"http://127.0.0.1:{off_host.server_address[1]}/meta"
    )
    _RedirectingHandler.hop_by_hop_seen = {}
    _OffHostHandler.hit_count = 0

    backend = ThreadingHTTPServer(("127.0.0.1", 0), _RedirectingHandler)
    t2 = threading.Thread(target=backend.serve_forever, daemon=True)
    t2.start()
    try:
        yield f"http://127.0.0.1:{backend.server_address[1]}"
    finally:
        for srv, thread in ((backend, t2), (off_host, t1)):
            srv.shutdown()
            srv.server_close()
            thread.join(timeout=5)


def test_backend_redirect_is_not_followed(server, redirecting_backend, auth_manager):
    """The authority pivot IS constructible on hop 2 without this guard.

    Every control this route enforces -- auth gate, path allowlist, traversal
    rejection, charset barrier -- applies to hop 1 only. A backend with any
    open redirect therefore hands an authenticated caller an arbitrary host.

    Measured before `allow_redirects=False` existed, with a registration
    hardened to `allowed_paths=["api/*"], allowed_methods=["GET"]`:

        status: 200
        body:   {"AccessKeyId": "ASIA-PIVOTED-CREDENTIAL", ...}
        caller sees 'location' header: False

    The proxy fetched the off-host body and returned it as the backend's, and
    because `location` is not in the response allowlist the caller could not
    tell a redirect had happened.
    """
    server.proxy_workflow(
        name="internal",
        proxy_url=redirecting_backend,
        allowed_paths=["api/*"],
        allowed_methods=["GET"],
    )
    client = TestClient(server.app)
    headers = {"Authorization": f"Bearer {asyncio.run(_token(auth_manager))}"}

    response = client.get(
        "/workflows/internal/api/login?next=http://169.254.169.254/latest/",
        headers=headers,
        follow_redirects=False,
    )

    # The property is that the redirect target is never CONTACTED. Asserting
    # only on the response body would still pass if the proxy fetched the
    # off-host resource and then failed to return it -- the request would
    # already have been made, and with it any credentials attached.
    assert (
        _OffHostHandler.hit_count == 0
    ), "SSRF: the proxy issued a request to the redirect target"
    assert "OFF-HOST-PIVOT-BODY" not in response.text
    # The backend's 302 is handed back to the caller as a 302, not resolved.
    assert response.status_code == 302, response.status_code

    # Control: a non-redirecting path on the same registration still works,
    # so the absence of the pivot body is not simply a broken route.
    ok = client.get("/workflows/internal/api/data", headers=headers)
    assert ok.status_code == 200, ok.text
    assert ok.json()["who"] == "legitimate-backend"


def test_hop_by_hop_headers_are_not_forwarded(
    server, redirecting_backend, auth_manager
):
    """Hop-by-hop headers describe the CALLER's connection, not the backend's.

    Forwarding `Transfer-Encoding: chunked` alongside a body the HTTP client
    frames itself gives the backend two disagreeing statements about where the
    request ends -- the CL.TE request-smuggling primitive.
    """
    server.proxy_workflow(
        name="internal", proxy_url=redirecting_backend, allowed_paths=["*"]
    )
    client = TestClient(server.app)

    response = client.get(
        "/workflows/internal/api/data",
        headers={
            "Authorization": f"Bearer {asyncio.run(_token(auth_manager))}",
            "Transfer-Encoding": "chunked",
            "Connection": "keep-alive",
            "TE": "trailers",
            "Upgrade": "websocket",
            "Expect": "100-continue",
        },
    )

    assert response.status_code == 200, response.text
    assert _RedirectingHandler.hop_by_hop_seen == {
        "transfer-encoding": None,
        "connection": None,
        "te": None,
        "upgrade": None,
        "expect": None,
    }


def test_response_framing_headers_are_not_echoed(
    server, redirecting_backend, auth_manager
):
    """`resp.read()` returns DECOMPRESSED bytes.

    Echoing the backend's `Content-Encoding: gzip` labels plaintext as
    compressed, and echoing its `Content-Length` states the compressed length
    over a decompressed body. Either mismatch is a response-smuggling
    primitive for anything parsing the stream downstream.
    """
    server.proxy_workflow(
        name="internal", proxy_url=redirecting_backend, allowed_paths=["*"]
    )
    client = TestClient(server.app)

    response = client.get(
        "/workflows/internal/api/data",
        headers={"Authorization": f"Bearer {asyncio.run(_token(auth_manager))}"},
    )

    assert response.status_code == 200, response.text
    # The backend sent Content-Encoding: gzip; it must not reach the caller.
    assert "content-encoding" not in {k.lower() for k in response.headers}
    # Content-type is still passed through, so this is not a blanket strip.
    assert response.headers.get("content-type", "").startswith("application/json")


def test_enterprise_server_auth_manager_protects_a_proxy(redirecting_backend):
    """F8: the positive branch of the newly-advertised auth_manager path.

    `servers/__init__.py` now documents
    `EnterpriseWorkflowServer(auth_manager=...)`. Only the REFUSAL branch was
    tested, which would still pass if `auth_manager` were silently swallowed
    into `**kwargs` after a future refactor -- exactly the `enable_auth`
    defect this PR corrected. This drives the accepted branch end to end.
    """
    manager = MiddlewareAuthManager(
        secret_key=_SECRET, enable_audit=False, enable_api_keys=False
    )
    srv = EnterpriseWorkflowServer(title="f8", auth_manager=manager)
    try:
        srv.proxy_workflow(
            name="internal", proxy_url=redirecting_backend, allowed_paths=["*"]
        )
        client = TestClient(srv.app)

        assert client.get("/workflows/internal/api/data").status_code == 401

        token = asyncio.run(manager.create_access_token("u", permissions=[]))
        allowed = client.get(
            "/workflows/internal/api/data",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert allowed.status_code == 200, allowed.text
    finally:
        srv.close()


def test_head_is_not_silently_added_to_a_get_only_route(server, backend, auth_manager):
    """Starlette's plain `Route` adds HEAD whenever GET is present.

    FastAPI's `api_route` does not, so `allowed_methods=["GET"]` really means
    GET alone -- but that is a property of the framework, not of this code, so
    it is pinned here. If a future FastAPI adopts Starlette's behaviour the
    method allowlist silently widens, and a HEAD leaks the backend's status
    and headers for any path the allowlist permits.
    """
    server.proxy_workflow(
        name="internal",
        proxy_url=backend,
        allowed_paths=["*"],
        allowed_methods=["GET"],
    )
    client = TestClient(server.app)
    headers = {"Authorization": f"Bearer {asyncio.run(_token(auth_manager))}"}

    assert client.head("/workflows/internal/x", headers=headers).status_code == 405
    assert client.get("/workflows/internal/x", headers=headers).status_code == 200

    route = next(
        r
        for r in server.app.router.routes
        if getattr(r, "path", "") == "/workflows/internal/{path:path}"
    )
    assert set(route.methods) == {"GET"}, sorted(route.methods)

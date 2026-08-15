"""Regression: the SEVENTH un-gated HTTP server -- ``DashboardAPIServer`` (#2112).

``kailash.visualization.api.DashboardAPIServer`` builds its own FastAPI
application and ships its own ``uvicorn.run()``, so it is a server in its own
right -- reachable without ``WorkflowServer``, without ``create_gateway()``,
and without any of the six surfaces #2100 closed for #2072. It accepted **no
auth parameter at all**: not ``require_auth``, not ``auth_config``, not
``enable_auth``. It never touched :mod:`kailash.utils.server_auth`, so none of
#2072's fail-closed work reached it.

What an anonymous caller got, measured against the pre-fix tree::

    GET /api/v1/runs                 -> 200  (every run id, workflow name, status)
    GET /api/v1/runs/{id}/tasks      -> 200  (per-node breakdown, errors, timings)
    GET /api/v1/reports/download/{f} -> 200/404 on an arbitrary filename
    GET /openapi.json                -> 200  (the full route map)
    WS  /api/v1/metrics/ws           -> handshake accepted, metrics pushed

No execute route lives here, so this is not anonymous code execution -- it is
anonymous disclosure of run history, per-run task breakdowns and report
downloads, which describe what the system runs and when.

Discrimination controls
-----------------------
Every 401 assertion is paired with a credentialed 200 on the SAME route. A
401-only test cannot tell a gate from a broken route, and a websocket-refused
test cannot tell a gate from a websocket route that refuses everyone -- which
is the exact failure #2100 found on ``EnterpriseWorkflowServer``'s ``/ws``.
A wrong-key row is the third control: it separates "verifies the signature"
from "rejects everything that is not the literal happy path".

No ``Mock`` anywhere. A ``Mock`` satisfies every ``hasattr``, so a mock-driven
guard test passes identically whether the guard is installed or not.
"""

import json
import pathlib
import socket
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

import pytest

fastapi = pytest.importorskip(
    "fastapi", reason="DashboardAPIServer requires the optional fastapi extra"
)
from fastapi.testclient import TestClient  # noqa: E402

import kailash.visualization.api as _viz_api_mod  # noqa: E402
from kailash.utils.server_auth import (  # noqa: E402
    DEFAULT_EXEMPT_PATHS,
    ServerAuthNotConfiguredError,
)
from kailash.visualization.api import DashboardAPIServer  # noqa: E402

pytestmark = pytest.mark.regression

# --- Subject-resolution guard -------------------------------------------
# `pytest.ini` sets `pythonpath = src` RELATIVE TO ROOTDIR. Run from another
# checkout, or with an installed `kailash` winning the path, and these tests
# would exercise a DIFFERENT tree than the one they are committed beside --
# going green while measuring source nobody is about to ship. Made RED here,
# before any test runs.
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_SUBJECT = pathlib.Path(_viz_api_mod.__file__).resolve()
if _REPO_ROOT not in _SUBJECT.parents:
    raise RuntimeError(
        "these tests would measure a different tree than they assert over: "
        f"`kailash.visualization.api` resolved to {_SUBJECT}, which is not "
        f"under {_REPO_ROOT}. Run pytest with this checkout as rootdir."
    )

# 48 chars > the RFC 7518 §3.2 32-byte floor `JWTConfig` enforces.
_SECRET = "issue-2112-regression-secret-key-at-least-32-byte"
_WRONG_SECRET = "issue-2112-a-DIFFERENT-secret-key-at-least-32-byt"

_AUTH_ENV_NAMES = (
    "KAILASH_JWT_SECRET",
    "KAILASH_JWT_PUBLIC_KEY",
    "KAILASH_JWT_ALGORITHM",
    "KAILASH_AUTH_EXEMPT_PATHS",
)


@pytest.fixture
def clean_auth_env(monkeypatch):
    """Remove every auth variable so a test's environment is what it sets.

    ``KAILASH_API_KEY_*`` is a PREFIX match, so the whole environment is swept
    rather than a fixed list -- a stray key inherited from the developer's
    shell would otherwise satisfy the gate and turn a fail-closed assertion
    green for the wrong reason.
    """
    import os

    for name in _AUTH_ENV_NAMES:
        monkeypatch.delenv(name, raising=False)
    for name in [n for n in os.environ if n.startswith("KAILASH_API_KEY_")]:
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


@pytest.fixture
def authed_env(clean_auth_env):
    """A configured HS256 credential source."""
    clean_auth_env.setenv("KAILASH_JWT_SECRET", _SECRET)
    return clean_auth_env


def _make_token(secret: str = _SECRET, **kwargs) -> str:
    """Mint a real HS256 token with the shipped validator."""
    from kailash.trust.auth.jwt import JWTConfig, JWTValidator

    return JWTValidator(JWTConfig(secret=secret)).create_access_token(
        user_id="regression-user", **kwargs
    )


def _bearer(secret: str = _SECRET) -> dict:
    return {"Authorization": f"Bearer {_make_token(secret)}"}


# --- Real data, not a mock ------------------------------------------------
# Plain value objects carrying the attributes the routes read. Real enough for
# the route to serialize a real 200 body, so the credentialed control proves
# the route WORKS rather than merely that it was reached.


class _Metrics:
    duration = 1.5
    cpu_usage = 12.5
    memory_usage_mb = 64.0


class _Task:
    node_id = "n1"
    node_type = "PythonCodeNode"
    status = "completed"
    started_at = datetime(2026, 8, 15, 12, 0, 0, tzinfo=timezone.utc)
    ended_at = datetime(2026, 8, 15, 12, 0, 1, tzinfo=timezone.utc)
    metrics = _Metrics()
    error = None


class _Run:
    run_id = "run-2112"
    workflow_name = "nightly-billing-export"
    status = "completed"
    started_at = datetime(2026, 8, 15, 12, 0, 0, tzinfo=timezone.utc)
    ended_at = datetime(2026, 8, 15, 12, 0, 5, tzinfo=timezone.utc)


class _TaskManager:
    """Task manager returning real run/task records.

    Not a mock of the HTTP layer: the FastAPI app, its routing, middleware and
    serialization are all real. This only supplies the backing data, so a
    credentialed 200 carries a real body to assert on.
    """

    def list_runs(self, *a, **kw):
        return [_Run()]

    def get_run(self, run_id, *a, **kw):
        return _Run() if run_id == _Run.run_id else None

    def get_run_tasks(self, *a, **kw):
        return [_Task()]


def _server(**kwargs) -> DashboardAPIServer:
    return DashboardAPIServer(task_manager=_TaskManager(), **kwargs)


def _client(**kwargs) -> TestClient:
    return TestClient(_server(**kwargs).app)


# ---------------------------------------------------------------------------
# Load-bearing: the data routes must be gated, and must still work with a key.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/runs",
        "/api/v1/runs/run-2112",
        "/api/v1/runs/run-2112/tasks",
        "/api/v1/monitoring/status",
        "/api/v1/metrics/current",
        "/api/v1/metrics/history",
        "/api/v1/reports/download/report.html",
        "/api/v1/dashboard/live",
    ],
    ids=lambda p: p.strip("/").replace("/", "_"),
)
def test_get_routes_401_without_credentials(authed_env, path):
    """Every read route refuses an anonymous caller.

    Constructed with NO new parameter, so this exercises the fail-closed
    DEFAULT and runs unchanged against the pre-fix tree, where it REDs with
    200 on the disclosure routes.
    """
    response = _client().get(path)

    assert response.status_code == 401, (
        f"anonymous caller reached {path}: {response.status_code} "
        f"{response.text[:200]!r}"
    )


def test_runs_200_with_valid_credentials(authed_env):
    """DISCRIMINATION CONTROL for the 401s above.

    Same route, same server, a real token -- 200 with the real body. Without
    this row, the 401 could equally be a broken route or a broken app.
    """
    response = _client().get("/api/v1/runs", headers=_bearer())

    assert response.status_code == 200, response.text
    body = response.json()
    assert body[0]["run_id"] == "run-2112"
    assert body[0]["workflow_name"] == "nightly-billing-export"


def test_run_tasks_200_with_valid_credentials(authed_env):
    """The per-run task breakdown is reachable WITH a credential."""
    response = _client().get("/api/v1/runs/run-2112/tasks", headers=_bearer())

    assert response.status_code == 200, response.text
    assert response.json()[0]["node_id"] == "n1"


def test_forged_token_is_rejected(authed_env):
    """NEGATIVE CONTROL: a well-formed token signed with a DIFFERENT key.

    Separates "verifies the signature" from "accepts anything that parses as a
    Bearer token".
    """
    response = _client().get("/api/v1/runs", headers=_bearer(_WRONG_SECRET))

    assert response.status_code == 401, (
        "a token signed with a different secret was accepted: "
        f"{response.status_code} {response.text[:200]!r}"
    )


def test_post_routes_401_without_credentials(authed_env):
    """The mutating routes are gated too -- monitoring start/stop and reports.

    ``POST /api/v1/monitoring/start`` spawns a broadcast task and mutates
    dashboard config from the request body, so an open one is unauthenticated
    resource consumption, not only disclosure.
    """
    client = _client()

    assert client.post("/api/v1/monitoring/start", json={}).status_code == 401
    assert client.post("/api/v1/monitoring/stop").status_code == 401
    assert (
        client.post(
            "/api/v1/reports/generate", json={"run_id": "run-2112", "format": "html"}
        ).status_code
        == 401
    )


# ---------------------------------------------------------------------------
# AC#2 -- construction fails closed when nothing is configured.
# ---------------------------------------------------------------------------


def test_construction_raises_without_a_credential_source(clean_auth_env):
    """``require_auth`` defaults True and there is no credential -> RAISE.

    At CONSTRUCTION, not per request: a server that started and then 500'd
    would still have reported itself healthy to an orchestrator.
    """
    with pytest.raises(ServerAuthNotConfiguredError) as excinfo:
        _server()

    message = str(excinfo.value)
    assert "DashboardAPIServer" in message, message
    # The error must be actionable -- it names the wiring, not just the fault.
    assert "KAILASH_JWT_SECRET" in message, message
    assert "require_auth=False" in message, message


def test_explicit_auth_config_satisfies_the_gate(clean_auth_env):
    """``auth_config=`` is a credential source even with an empty environment."""
    from kailash.trust.auth.jwt import JWTConfig

    client = TestClient(_server(auth_config=JWTConfig(secret=_SECRET)).app)

    assert client.get("/api/v1/runs").status_code == 401
    assert client.get("/api/v1/runs", headers=_bearer()).status_code == 200


def test_auth_config_does_not_reinstate_the_broad_exempt_default(clean_auth_env):
    """A bare ``JWTConfig`` must not re-open ``/openapi.json``.

    ``JWTConfig``'s own ``exempt_paths`` default exempts ``/docs`` and
    ``/openapi.json``; ``resolve_server_auth`` narrows an untouched default to
    the health-only list. This pins that this surface gets that narrowing too
    -- #2100 shipped a revision where the ``auth_config=`` branch was the
    WEAKEST way to ask for authentication.
    """
    from kailash.trust.auth.jwt import JWTConfig

    client = TestClient(_server(auth_config=JWTConfig(secret=_SECRET)).app)

    assert client.get("/openapi.json").status_code == 401
    assert client.get("/openapi.json", headers=_bearer()).status_code == 200


# ---------------------------------------------------------------------------
# AC#5 -- health stays exempt; nothing else does.
# ---------------------------------------------------------------------------


def test_health_is_exempt(authed_env):
    """Liveness answers without credentials, or every orchestrator restarts us."""
    response = _client().get("/health")

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "healthy"


def test_openapi_and_docs_are_not_exempt(authed_env):
    """The route map is NOT public.

    ``/openapi.json`` enumerates every route on the server, and ``/docs``
    renders it. ``JWTConfig``'s own default list exempts both; this surface
    must use ``DEFAULT_EXEMPT_PATHS``, which does not.
    """
    client = _client()

    assert client.get("/openapi.json").status_code == 401
    assert client.get("/docs").status_code == 401
    # Control: they are reachable WITH a credential, so the 401s above are the
    # gate and not a missing route.
    assert client.get("/openapi.json", headers=_bearer()).status_code == 200


def test_default_exempt_paths_is_health_only():
    """Structural pin on the policy this surface inherits.

    If a future change widens ``DEFAULT_EXEMPT_PATHS``, every server sharing it
    silently re-opens -- this fails loudly instead.
    """
    assert set(DEFAULT_EXEMPT_PATHS) == {
        "/health",
        "/health/*",
        "/enterprise/health",
    }, DEFAULT_EXEMPT_PATHS


def test_extra_exempt_paths_is_honoured(authed_env):
    """``auth_exempt_paths`` is a DOCUMENTED kwarg, so it must have an effect.

    ``zero-tolerance.md`` Rule 3c: a documented kwarg consumed by no branch is
    the silent-fallback mode at the API surface. #2100 shipped exactly that
    defect on ``auth_config=``'s branch.
    """
    client = _client(auth_exempt_paths=["/api/v1/monitoring/status"])

    assert client.get("/api/v1/monitoring/status").status_code == 200
    # NOT a blanket disable -- the sibling route is still gated.
    assert client.get("/api/v1/runs").status_code == 401


# ---------------------------------------------------------------------------
# AC#3 -- the websocket routes. `BaseHTTPMiddleware` cannot see them.
# ---------------------------------------------------------------------------


def _ws_handshake_ok(client: TestClient, path: str, headers=None) -> bool:
    """True when the handshake completes, False when the app refuses it.

    Starlette's TestClient raises ``WebSocketDisconnect`` when the application
    sends ``websocket.close`` while the handshake is still pending, and
    ``httpx.HTTPStatusError``/``WebSocketDenialResponse`` when it denies with
    an HTTP response. Both mean REFUSED.
    """
    from starlette.websockets import WebSocketDisconnect

    try:
        with client.websocket_connect(path, headers=headers or {}):
            return True
    except WebSocketDisconnect:
        return False
    except Exception as exc:  # denial response / status error
        if (
            "403" in str(exc)
            or "401" in str(exc)
            or "denial" in type(exc).__name__.lower()
        ):
            return False
        raise


@pytest.mark.parametrize(
    "path", ["/api/v1/metrics/stream", "/api/v1/metrics/ws"], ids=["stream", "ws"]
)
def test_websocket_handshake_is_gated(authed_env, path):
    """Both websocket routes refuse an anonymous handshake -- WITH a control.

    THE test that distinguishes ``install_server_auth_middleware`` from a bare
    ``JWTAuthMiddleware``. ``JWTAuthMiddleware`` extends Starlette's
    ``BaseHTTPMiddleware``, whose ``__call__`` returns early for any scope that
    is not ``"http"``, so its ``dispatch`` NEVER runs for a websocket. Install
    only that layer and these two routes stay wide open on a server whose HTTP
    surface reports itself gated.

    The credentialed row is load-bearing in the other direction: without it,
    "handshake refused" would read green against a route that refuses
    everyone, which is the broken-``/ws`` defect #2100 found on
    ``EnterpriseWorkflowServer``.
    """
    client = _client()

    assert not _ws_handshake_ok(client, path), f"anonymous websocket accepted on {path}"
    assert _ws_handshake_ok(
        client, path, _bearer()
    ), f"credentialed websocket refused on {path} -- gate or broken route?"
    assert not _ws_handshake_ok(
        client, path, _bearer(_WRONG_SECRET)
    ), f"forged-token websocket accepted on {path}"


@pytest.mark.parametrize(
    "path", ["/api/v1/metrics/stream", "/api/v1/metrics/ws"], ids=["stream", "ws"]
)
def test_websocket_routes_bind_the_socket_not_a_query_param(clean_auth_env, path):
    """A SEPARATE defect the credentialed control above surfaced.

    Both routes were declared ``async def handler(websocket: Any)``. FastAPI
    resolves a websocket endpoint's parameters like a route's and binds the
    socket ONLY to a parameter annotated ``WebSocket``; under ``Any`` the
    socket was never injected and ``websocket`` became a REQUIRED QUERY
    PARAMETER, so every handshake failed validation and closed -- credentialed
    or not. The live dashboard HTML page consumes ``/api/v1/metrics/ws``, so
    its metrics never updated.

    Asserted with the gate OFF, so it cannot be read as an auth interaction,
    and structurally on the route's own dependant, so it names the mechanism
    rather than the symptom.
    """
    server = _server(require_auth=False)

    routes = [r for r in server.app.routes if getattr(r, "path", None) == path]
    assert routes, f"{path} is not registered"
    dependant = routes[0].dependant

    assert dependant.websocket_param_name is not None, (
        f"{path} never binds the WebSocket -- query_params="
        f"{[f.name for f in dependant.query_params]}"
    )
    assert "websocket" not in [f.name for f in dependant.query_params], (
        f"{path} still treats the socket as a query parameter: "
        f"{[f.name for f in dependant.query_params]}"
    )

    # Behavioural pair: the handshake actually completes with auth disabled.
    assert _ws_handshake_ok(TestClient(server.app), path)


# ---------------------------------------------------------------------------
# Explicit opt-out -- legitimate, but never silent.
# ---------------------------------------------------------------------------


def test_require_auth_false_serves_openly_and_warns_loudly(clean_auth_env, caplog):
    """``require_auth=False`` is honoured AND logs the exposure once.

    ``security.md`` § Secure-Default: an opt-out is a legitimate choice, but a
    SILENT one is the no-op default this whole class of fix exists to prevent.
    """
    import logging

    with caplog.at_level(logging.WARNING, logger="kailash.utils.server_auth"):
        client = _client(require_auth=False)

    assert client.get("/api/v1/runs").status_code == 200

    warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert warnings, "auth was disabled with nothing on the record"
    assert any("server_auth.disabled" in r.getMessage() for r in warnings), [
        r.getMessage() for r in warnings
    ]


def test_external_auth_reason_installs_nothing(clean_auth_env):
    """A declared outer gate means this server installs none -- no double credential."""
    server = _server(external_auth_reason="fronted by an authenticating proxy")

    assert server._auth_config is None
    assert TestClient(server.app).get("/api/v1/runs").status_code == 200


def test_blank_external_auth_reason_is_rejected(clean_auth_env):
    """A reason that names nothing is an undocumented hole."""
    with pytest.raises(ValueError):
        _server(external_auth_reason="   ")


# ---------------------------------------------------------------------------
# Structural: the controls are NAMED parameters, and CORS stays outermost.
# ---------------------------------------------------------------------------


def test_auth_controls_are_named_parameters_not_kwargs():
    """A typo must be a ``TypeError``, not a silently open server.

    ``enable_auth=True`` has shipped as a swallowed ``**kwargs`` entry twice
    (#2025, #2013). ``DashboardAPIServer.__init__`` declares no ``**kwargs``,
    so this cannot recur here.
    """
    import inspect

    params = inspect.signature(DashboardAPIServer.__init__).parameters
    for name in (
        "require_auth",
        "auth_config",
        "external_auth_reason",
        "auth_exempt_paths",
    ):
        assert name in params, f"{name} is not a named parameter"
    assert params["require_auth"].default is True, "the gate does not fail closed"
    assert not any(
        p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values()
    ), "**kwargs on an auth-bearing constructor can swallow a mistyped control"


def test_cors_preflight_survives_but_the_real_request_is_still_gated(authed_env):
    """Auth must be installed BEFORE CORS, so CORS stays OUTERMOST.

    Starlette's ``add_middleware`` PREPENDS, so the last layer added is the
    outermost. Auth added after CORS ends up inside it and 401s cross-origin
    preflight ``OPTIONS`` before CORS can answer. The second assertion is what
    stops the ordering fix from smuggling a real request through.
    """
    client = _client(cors_origins=["https://dash.example"])

    preflight = client.options(
        "/api/v1/runs",
        headers={
            "Origin": "https://dash.example",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert preflight.status_code == 200, preflight.text

    real = client.get("/api/v1/runs", headers={"Origin": "https://dash.example"})
    assert (
        real.status_code == 401
    ), "CORS ordering smuggled an anonymous request through"


# ---------------------------------------------------------------------------
# End-to-end over a real socket -- the literal deployment path.
# ---------------------------------------------------------------------------


def test_real_uvicorn_socket_rejects_anonymous_disclosure(authed_env):
    """``start_server()`` under real uvicorn on a real port.

    ``TestClient`` drives the real ASGI stack, but this class ships its own
    ``uvicorn.run()``, so the deployment path is a real process on a real
    socket. Repeated here so the gate is proven on the path an operator uses.
    """
    import uvicorn

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]

    server = _server()
    config = uvicorn.Config(server.app, host="127.0.0.1", port=port, log_level="error")
    uv = uvicorn.Server(config)
    thread = threading.Thread(target=uv.run, daemon=True)
    thread.start()
    try:
        deadline = time.time() + 20
        while time.time() < deadline and not uv.started:
            time.sleep(0.05)
        assert uv.started, "uvicorn did not start"

        url = f"http://127.0.0.1:{port}/api/v1/runs"

        with pytest.raises(urllib.error.HTTPError) as excinfo:
            urllib.request.urlopen(url, timeout=10)
        assert excinfo.value.code == 401, excinfo.value.code

        # Discrimination control on the SAME socket.
        request = urllib.request.Request(url, headers=_bearer())
        with urllib.request.urlopen(request, timeout=10) as response:
            assert response.status == 200
            assert json.loads(response.read())[0]["run_id"] == "run-2112"
    finally:
        uv.should_exit = True
        thread.join(timeout=20)

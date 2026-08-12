# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression tests for issue #2072 -- anonymous arbitrary workflow execution.

On a default ``WorkflowServer`` / ``create_gateway()`` with a single
``register_workflow(...)``, ``POST /workflows/{name}/execute`` **executed the
workflow for an anonymous caller**. Measured on a real socket before the fix::

    POST /workflows/probe/execute   -> 200
      body: b'{"outputs":{"n":{"result":{"ran":true}}},"execution_time":6.85,...}'

The workflow did not merely route -- it RAN.

These tests are **behavioural**: they drive a real ASGI stack and assert on
status codes. **No ``Mock`` appears anywhere in this file.** A ``Mock``
satisfies every ``hasattr`` and accepts every call, so a mock-driven guard test
passes identically whether the guard is installed or not -- which is exactly
how the inert auth control in #2013 shipped green.

Fail-first design
-----------------
The load-bearing tests below construct servers WITHOUT passing any new
parameter, so they run **unchanged** against the pre-fix tree and produce a
genuine behavioural RED (200 where 401 is required) rather than a collection
error. Tests that need a symbol introduced by the fix import it
**function-locally** for the same reason: a module-level import would turn the
whole file into one collection error and destroy the behavioural measurement.

Discrimination control
----------------------
:func:`test_mounted_execute_200_with_valid_credentials` hits the SAME route
with a valid token and gets 200. Without it, the 401 in the load-bearing test
could equally be a broken route.
"""

import json
import socket
import threading
import time
import urllib.error
import urllib.request

import pytest
from fastapi.testclient import TestClient

from kailash.servers import WorkflowServer
from kailash.workflow.builder import WorkflowBuilder

pytestmark = pytest.mark.regression

# 48 chars > the RFC 7518 §3.2 32-byte floor JWTConfig enforces.
_SECRET = "issue-2072-regression-secret-key-at-least-32-byte"

_AUTH_ENV_NAMES = (
    "KAILASH_JWT_SECRET",
    "KAILASH_JWT_PUBLIC_KEY",
    "KAILASH_JWT_ALGORITHM",
    "KAILASH_AUTH_EXEMPT_PATHS",
)


@pytest.fixture
def clean_auth_env(monkeypatch):
    """Remove every auth variable so a test's environment is what it sets.

    ``KAILASH_API_KEY_*`` is a prefix match, so the whole environment is swept
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


def _probe_workflow():
    wb = WorkflowBuilder()
    wb.add_node("PythonCodeNode", "n", {"code": "result = {'ran': True}"})
    return wb.build()


def _make_token(secret: str = _SECRET, **kwargs) -> str:
    """Mint a real HS256 token with the shipped validator."""
    from kailash.trust.auth.jwt import JWTConfig, JWTValidator

    return JWTValidator(JWTConfig(secret=secret)).create_access_token(
        user_id="regression-user", **kwargs
    )


def _server_with_probe(**kwargs) -> WorkflowServer:
    server = WorkflowServer(title="probe", **kwargs)
    server.register_workflow("probe", _probe_workflow())
    return server


# ---------------------------------------------------------------------------
# Load-bearing: the mounted sub-application must be gated.
# ---------------------------------------------------------------------------


def test_mounted_execute_401_without_credentials(authed_env):
    """``POST /workflows/{name}/execute`` with no credentials returns 401.

    THE load-bearing test. ``register_workflow`` calls ``app.mount(...)``, and
    a route/app-level ``Depends`` does NOT run for requests routed into a
    mounted sub-application. If this returns 200 the gate was implemented as a
    dependency and the whole surface is still open.

    Constructed with NO new parameter, so it exercises the fail-closed DEFAULT
    and runs unchanged against the pre-fix tree.
    """
    server = _server_with_probe()
    client = TestClient(server.app)

    response = client.post("/workflows/probe/execute", json={"inputs": {}})

    assert response.status_code == 401, (
        "anonymous caller reached the mounted /execute route: "
        f"{response.status_code} {response.text[:200]}"
    )
    # The workflow must not have run at all.
    assert "outputs" not in response.text


def test_mounted_execute_200_with_valid_credentials(authed_env):
    """DISCRIMINATION CONTROL -- the same route with a valid token works.

    Without this, the 401 above could equally be a broken route, a bad mount,
    or a 401 emitted by something other than authentication.
    """
    server = _server_with_probe()
    client = TestClient(server.app)

    response = client.post(
        "/workflows/probe/execute",
        json={"inputs": {}},
        headers={"Authorization": f"Bearer {_make_token()}"},
    )

    assert response.status_code == 200, response.text
    # Proves it is the REAL route that answered, not a permissive stub.
    assert response.json()["outputs"]["n"]["result"] == {"ran": True}


def test_invalid_token_rejected(authed_env):
    """A syntactically valid but unsigned-by-us token is refused."""
    server = _server_with_probe()
    client = TestClient(server.app)

    forged = _make_token(secret="a-different-secret-key-of-sufficient-length")
    response = client.post(
        "/workflows/probe/execute",
        json={"inputs": {}},
        headers={"Authorization": f"Bearer {forged}"},
    )

    assert response.status_code == 401
    assert "outputs" not in response.text


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/"),
        ("GET", "/workflows"),
        ("GET", "/metrics"),
        ("GET", "/dashboard"),
        ("GET", "/durability/requests"),
        ("POST", "/workflows/probe/execute"),
    ],
)
def test_surface_requires_authentication(authed_env, method, path):
    """Every route the issue enumerates rejects the anonymous caller.

    ``/metrics`` and ``/dashboard`` are included deliberately: ``JWTConfig``'s
    OWN default exempt list exempts ``/metrics``, and reusing that default
    would have left it open. ``kailash.utils.server_auth.DEFAULT_EXEMPT_PATHS``
    exempts health probes and nothing else.
    """
    server = _server_with_probe()
    client = TestClient(server.app)

    response = client.request(method, path, json={"inputs": {}})

    # 404 would mean the route does not exist on this build and the test is
    # asserting nothing -- fail loudly rather than pass vacuously.
    assert response.status_code != 404, f"{path} is not registered; test is vacuous"
    assert response.status_code == 401, f"{method} {path} -> {response.status_code}"


def test_health_probe_is_exempt(authed_env):
    """Liveness probes answer without credentials.

    Not a convenience: if ``/health`` required a token, every orchestrator
    would mark an authenticated server unhealthy and restart-loop it.
    """
    server = _server_with_probe()
    client = TestClient(server.app)

    assert client.get("/health").status_code == 200


# ---------------------------------------------------------------------------
# Middleware ordering -- CORS must stay outermost.
# ---------------------------------------------------------------------------


def test_cors_preflight_is_not_401(authed_env):
    """A cross-origin preflight OPTIONS is answered by CORS, not 401'd by auth.

    Starlette's ``add_middleware`` PREPENDS, so the layer added LAST is
    OUTERMOST. Auth installed after CORS sits inside it and rejects the
    preflight before CORS can answer. PR #2054 hit exactly this.
    """
    server = _server_with_probe(cors_origins=["http://localhost:3000"])
    client = TestClient(server.app)

    response = client.options(
        "/workflows/probe/execute",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
        },
    )

    assert response.status_code != 401, "auth is outside CORS; preflight is broken"
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_cors_preflight_still_does_not_expose_the_route(authed_env):
    """Answering the preflight must not smuggle the real request through."""
    server = _server_with_probe(cors_origins=["http://localhost:3000"])
    client = TestClient(server.app)

    response = client.post(
        "/workflows/probe/execute",
        json={"inputs": {}},
        headers={"Origin": "http://localhost:3000"},
    )

    assert response.status_code == 401


# ---------------------------------------------------------------------------
# Fail-closed construction.
# ---------------------------------------------------------------------------


def test_construction_raises_without_any_credential_source(clean_auth_env):
    """No credential configured + auth required -> typed, loud, at construction.

    Construction-time and not request-time: a server that booted and then 500'd
    per request would still have reported itself healthy to an orchestrator.
    """
    from kailash.utils.server_auth import ServerAuthNotConfiguredError

    with pytest.raises(ServerAuthNotConfiguredError) as excinfo:
        WorkflowServer(title="probe")

    message = str(excinfo.value)
    # The message must be actionable: name the env var, the explicit opt-out,
    # and the external-auth declaration.
    assert "KAILASH_JWT_SECRET" in message
    assert "require_auth=False" in message
    assert "external_auth_reason" in message
    # It must never echo a secret; there is none configured, but assert the
    # shape so a future edit cannot start interpolating one.
    assert _SECRET not in message


def test_construction_error_is_a_runtime_error(clean_auth_env):
    """Subclasses RuntimeError so existing handlers keep working (#636 shape)."""
    from kailash.utils.server_auth import ServerAuthNotConfiguredError

    assert issubclass(ServerAuthNotConfiguredError, RuntimeError)
    with pytest.raises(RuntimeError):
        WorkflowServer(title="probe")


def test_under_length_secret_is_rejected(clean_auth_env):
    """A short HS256 key is brute-forceable; refuse it rather than use it."""
    from kailash.utils.server_auth import InvalidServerAuthSecretError

    clean_auth_env.setenv("KAILASH_JWT_SECRET", "too-short")

    with pytest.raises(InvalidServerAuthSecretError) as excinfo:
        WorkflowServer(title="probe")

    assert "32" in str(excinfo.value)
    # The rejected secret must not be echoed into the message or logs.
    assert "too-short" not in str(excinfo.value)


def test_auth_manager_alone_does_not_satisfy_require_auth(clean_auth_env):
    """``auth_manager`` is a ``Depends`` and does not reach mounted sub-apps.

    Accepting it as a credential source would close the gate on paper and
    leave ``POST /workflows/{name}/execute`` -- the reachable route -- open.
    """
    from kailash.middleware.auth import MiddlewareAuthManager
    from kailash.utils.server_auth import ServerAuthNotConfiguredError

    manager = MiddlewareAuthManager(secret_key=_SECRET)

    with pytest.raises(ServerAuthNotConfiguredError):
        WorkflowServer(title="probe", auth_manager=manager)


def test_explicit_opt_out_constructs_and_warns(clean_auth_env, caplog):
    """``require_auth=False`` is honoured, but never silently.

    security.md § Secure-Default: an opt-out must name the OFF protection and
    its exact wiring.
    """
    import logging

    with caplog.at_level(logging.WARNING):
        server = _server_with_probe(require_auth=False)

    client = TestClient(server.app)
    assert (
        client.post("/workflows/probe/execute", json={"inputs": {}}).status_code == 200
    )

    warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert warnings, "opt-out was silent"
    assert any("server_auth.disabled" in r.getMessage() for r in warnings)


def test_explicit_auth_config_bypasses_environment(clean_auth_env):
    """An explicit JWTConfig is a credential source; no env var needed."""
    from kailash.trust.auth.jwt import JWTConfig

    server = _server_with_probe(
        auth_config=JWTConfig(secret=_SECRET, exempt_paths=["/health"])
    )
    client = TestClient(server.app)

    assert (
        client.post("/workflows/probe/execute", json={"inputs": {}}).status_code == 401
    )
    assert (
        client.post(
            "/workflows/probe/execute",
            json={"inputs": {}},
            headers={"Authorization": f"Bearer {_make_token()}"},
        ).status_code
        == 200
    )


def test_empty_auth_config_dict_does_not_satisfy_the_gate(clean_auth_env):
    """``auth_config={}`` is not a configuration.

    Treating a falsey dict as one would build a JWTConfig with no secret and
    install a middleware that can verify nothing -- the silent-no-op shape this
    whole change exists to prevent. It must fall through and fail closed.
    """
    from kailash.utils.server_auth import ServerAuthNotConfiguredError

    with pytest.raises(ServerAuthNotConfiguredError):
        WorkflowServer(title="probe", auth_config={})


def test_api_key_only_deployment(clean_auth_env):
    """``KAILASH_API_KEY_<NAME>`` alone authenticates via X-API-Key.

    And the bearer arm must stay CLOSED: with no JWT secret configured the
    server mints an ephemeral unforgeable one, so no party can present a
    valid token.
    """
    clean_auth_env.setenv("KAILASH_API_KEY_SERVICE", "an-api-key-value")

    server = _server_with_probe()
    client = TestClient(server.app)

    assert (
        client.post("/workflows/probe/execute", json={"inputs": {}}).status_code == 401
    )
    assert (
        client.post(
            "/workflows/probe/execute",
            json={"inputs": {}},
            headers={"X-API-Key": "wrong-key"},
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/workflows/probe/execute",
            json={"inputs": {}},
            headers={"X-API-Key": "an-api-key-value"},
        ).status_code
        == 200
    )


# ---------------------------------------------------------------------------
# External auth declaration.
# ---------------------------------------------------------------------------


def test_external_auth_reason_installs_nothing(clean_auth_env):
    """A declared external gate means this server installs none.

    This is how Nexus avoids a second, independently-configured auth layer.
    """
    server = _server_with_probe(
        external_auth_reason="nexus installs nexus.auth.jwt.JWTMiddleware"
    )
    client = TestClient(server.app)

    # No credential configured, no raise, and no gate installed here.
    assert (
        client.post("/workflows/probe/execute", json={"inputs": {}}).status_code == 200
    )
    assert server._auth_config is None
    assert server._external_auth_reason == "nexus installs nexus.auth.jwt.JWTMiddleware"


@pytest.mark.parametrize("blank", ["", "   ", "\t\n"])
def test_blank_external_auth_reason_is_rejected(clean_auth_env, blank):
    """A reason that names nothing is an undocumented hole, not a declaration."""
    with pytest.raises(ValueError):
        WorkflowServer(title="probe", external_auth_reason=blank)


# ---------------------------------------------------------------------------
# Named parameters -- the swallowed-kwarg regression.
# ---------------------------------------------------------------------------


def test_misspelled_control_is_a_typeerror_not_an_open_server(clean_auth_env):
    """A typo in the control name must NOT silently produce an open server.

    ``enable_auth=True`` was advertised in ``servers/__init__.py``'s docstring
    while landing in ``**kwargs`` and being discarded. Because ``require_auth``
    is a NAMED parameter, the same typo is now a construction failure -- and
    the server is fail-closed regardless, so even the swallow path is safe.
    """
    with pytest.raises((TypeError, RuntimeError)):
        WorkflowServer(
            title="probe", requre_auth=False
        )  # noqa: F841 -- typo is the point


def test_enable_auth_kwarg_no_longer_yields_an_open_server(clean_auth_env):
    """The historical ``enable_auth=True`` spelling cannot produce an open server.

    It is still swallowed by ``**kwargs`` (removing that is a separate breaking
    change), but the fail-closed default means the outcome is a raise rather
    than a silently unauthenticated server -- the defect is closed either way.
    """
    from kailash.utils.server_auth import ServerAuthNotConfiguredError

    with pytest.raises(ServerAuthNotConfiguredError):
        WorkflowServer(title="probe", enable_auth=True)


# ---------------------------------------------------------------------------
# Enforcement-surface parity -- create_gateway and the sibling gateway.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("server_type", ["basic", "durable", "enterprise"])
def test_create_gateway_fails_closed_for_every_server_type(clean_auth_env, server_type):
    """All three server types learn the gate, not just the base class."""
    from kailash.servers.gateway import create_gateway
    from kailash.utils.server_auth import ServerAuthNotConfiguredError

    with pytest.raises(ServerAuthNotConfiguredError):
        create_gateway(server_type=server_type)


@pytest.mark.parametrize("server_type", ["basic", "durable", "enterprise"])
def test_create_gateway_gates_mounted_execute(authed_env, server_type):
    """The gate reaches the mounted route on every server type."""
    from kailash.servers.gateway import create_gateway

    gateway = create_gateway(server_type=server_type)
    gateway.register_workflow("probe", _probe_workflow())
    client = TestClient(gateway.app)

    assert (
        client.post("/workflows/probe/execute", json={"inputs": {}}).status_code == 401
    )
    assert (
        client.post(
            "/workflows/probe/execute",
            json={"inputs": {}},
            headers={"Authorization": f"Bearer {_make_token()}"},
        ).status_code
        == 200
    )


def test_workflow_api_gateway_parity_fails_closed(clean_auth_env):
    """The INDEPENDENT ``kailash.api.WorkflowAPIGateway`` learns the same gate.

    security.md § Enforcement-Surface Parity: a sibling left unqualified ships
    the exact failure mode the fix closes.
    """
    from kailash.api.gateway import WorkflowAPIGateway
    from kailash.utils.server_auth import ServerAuthNotConfiguredError

    with pytest.raises(ServerAuthNotConfiguredError):
        WorkflowAPIGateway(title="probe")


def test_workflow_api_gateway_parity_gates_mounted_execute(authed_env):
    """...and it gates its own mounted sub-app, which sits at ``/{name}``."""
    from kailash.api.gateway import WorkflowAPIGateway

    gateway = WorkflowAPIGateway(title="probe")
    gateway.register_workflow("probe", _probe_workflow())
    client = TestClient(gateway.app)

    assert client.post("/probe/execute", json={"inputs": {}}).status_code == 401
    assert (
        client.post(
            "/probe/execute",
            json={"inputs": {}},
            headers={"Authorization": f"Bearer {_make_token()}"},
        ).status_code
        == 200
    )


def test_api_channel_enable_auth_is_load_bearing(authed_env):
    """``ChannelConfig.enable_auth`` now installs a real gate.

    It was reported by ``/channel/info`` and read by NO enforcement path --
    a documented security control that did nothing (Rule 3c).
    """
    from kailash.channels.api_channel import APIChannel
    from kailash.channels.base import ChannelConfig, ChannelType

    channel = APIChannel(
        ChannelConfig(
            name="probe",
            channel_type=ChannelType.API,
            enable_auth=True,
        )
    )
    channel.workflow_server.register_workflow("probe", _probe_workflow())
    client = TestClient(channel.app)

    assert (
        client.post("/workflows/probe/execute", json={"inputs": {}}).status_code == 401
    )
    assert (
        client.post(
            "/workflows/probe/execute",
            json={"inputs": {}},
            headers={"Authorization": f"Bearer {_make_token()}"},
        ).status_code
        == 200
    )


def test_api_channel_default_is_not_an_open_server(authed_env):
    """An APIChannel whose config never mentions auth still gets the gate.

    ``ChannelConfig.enable_auth`` used to be a plain ``bool`` defaulting to
    ``False``, which cannot distinguish "the operator never said" from "the
    operator said no". Mapping that default straight to ``require_auth`` left
    every default APIChannel serving anonymous workflow execution on
    ``POST /workflows/{name}/execute`` -- the exact route the rest of this
    change closes, still open through a sibling surface
    (security.md § Enforcement-Surface Parity).
    """
    from kailash.channels.api_channel import APIChannel
    from kailash.channels.base import ChannelConfig, ChannelType

    channel = APIChannel(
        ChannelConfig(name="probe", channel_type=ChannelType.API)
    )  # NOTE: enable_auth is never mentioned.
    channel.workflow_server.register_workflow("probe", _probe_workflow())
    client = TestClient(channel.app)

    assert (
        client.post("/workflows/probe/execute", json={"inputs": {}}).status_code == 401
    )
    # Discrimination control: the 401 is authentication, not a broken route.
    assert (
        client.post(
            "/workflows/probe/execute",
            json={"inputs": {}},
            headers={"Authorization": f"Bearer {_make_token()}"},
        ).status_code
        == 200
    )


def test_api_channel_explicit_opt_out_is_still_honoured(clean_auth_env):
    """``enable_auth=False`` remains a real, honoured opt-out.

    Fail-closed-on-unstated must not silently promote an EXPLICIT no into a
    yes; that would be an undeclared breaking change on the opposite side, and
    the tri-state exists precisely to keep the two answers distinct.
    """
    from kailash.channels.api_channel import APIChannel
    from kailash.channels.base import ChannelConfig, ChannelType

    channel = APIChannel(
        ChannelConfig(name="probe", channel_type=ChannelType.API, enable_auth=False)
    )
    channel.workflow_server.register_workflow("probe", _probe_workflow())

    assert (
        TestClient(channel.app)
        .post("/workflows/probe/execute", json={"inputs": {}})
        .status_code
        == 200
    )


def test_channel_info_never_reports_auth_it_does_not_enforce():
    """``/channel/info`` reports enforcement, never the raw tri-state.

    An unstated ``None`` inherits the gate, so it reports ``True``; an explicit
    ``False`` reports ``False``. Leaking ``None`` into the payload would be a
    third value no client knows how to read, and reporting an unenforced
    ``True`` is the false-assurance defect this issue closes.
    """
    from kailash.channels.base import ChannelConfig, ChannelType

    unstated = ChannelConfig(name="p", channel_type=ChannelType.API)
    opted_out = ChannelConfig(name="p", channel_type=ChannelType.API, enable_auth=False)

    assert unstated.enable_auth is None, "the tri-state must survive on the config"
    assert (unstated.enable_auth is not False) is True
    assert (opted_out.enable_auth is not False) is False

    # The MCP channel enforces nothing of its own, so it reports bool(...):
    # an unstated None must read as False there, never as enabled.
    assert bool(unstated.enable_auth) is False


# ---------------------------------------------------------------------------
# Nexus declares only the authentication it actually installs.
# ---------------------------------------------------------------------------


def test_nexus_does_not_declare_external_auth_it_never_installs():
    """``external_auth_reason`` is declared only when Nexus really installs it.

    Nexus builds its HTTP surface on the core gateway. Declaring external auth
    unconditionally would tell the fail-closed gate that "an outside middleware
    authenticates every request" on a development ``Nexus()`` -- where
    ``enable_auth`` defaults to False and NOTHING does -- putting a false
    assurance on the record and suppressing the opt-out WARN that names the
    exposure. That is the #2013 shape (a control that reports success and
    installs nothing) re-entering through the declaration.
    """
    pytest.importorskip("nexus")
    from nexus.auth_bootstrap import core_gateway_auth_kwargs

    enabled = core_gateway_auth_kwargs(True)
    assert "external_auth_reason" in enabled
    assert enabled["external_auth_reason"].strip()
    assert "require_auth" not in enabled, (
        "declaring external auth AND opting out would install nothing twice over"
    )

    disabled = core_gateway_auth_kwargs(False)
    assert disabled == {"require_auth": False}, (
        "enable_auth=False must map to the explicit, WARN-logged opt-out -- "
        "never to a declaration that something else authenticates"
    )


def test_nexus_call_sites_resolve_through_the_shared_helper():
    """Both ``create_gateway()`` call sites use the helper, not a fixed string.

    A second hand-written ``external_auth_reason=`` anywhere is how the two
    paths drift into disagreeing about who authenticates the same app.
    """
    pytest.importorskip("nexus")
    import inspect

    from nexus import core as nexus_core
    from nexus.transports import http as nexus_http

    for module in (nexus_core, nexus_http):
        source = inspect.getsource(module)
        assert "core_gateway_auth_kwargs(" in source, module.__name__
        assert "external_auth_reason=" not in source, (
            f"{module.__name__} hand-writes external_auth_reason instead of "
            "resolving it from the flag through core_gateway_auth_kwargs()"
        )


# ---------------------------------------------------------------------------
# End-to-end over a real socket -- the literal user path from the issue.
# ---------------------------------------------------------------------------


@pytest.mark.slow
def test_real_uvicorn_socket_rejects_anonymous_execution(authed_env):
    """The issue's verbatim reproducer, re-run against the fixed server.

    ``TestClient`` drives the real ASGI stack, but the original proof was a
    real uvicorn process on a real port hit by a real HTTP client. This repeats
    that so the fix is measured on the same instrument as the defect.
    """
    with socket.socket() as probe_sock:
        probe_sock.bind(("127.0.0.1", 0))
        port = probe_sock.getsockname()[1]

    server = _server_with_probe()
    threading.Thread(
        target=server.run,
        kwargs={"host": "127.0.0.1", "port": port},
        daemon=True,
    ).start()

    for _ in range(100):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                break
        except OSError:
            time.sleep(0.1)
    else:  # pragma: no cover -- server failed to bind
        pytest.fail(f"server never came up on port {port}")

    url = f"http://127.0.0.1:{port}/workflows/probe/execute"
    body = json.dumps({"inputs": {}}).encode()

    anonymous = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"}, method="POST"
    )
    with pytest.raises(urllib.error.HTTPError) as excinfo:
        urllib.request.urlopen(anonymous, timeout=30)
    assert excinfo.value.code == 401

    # Discrimination control on the same socket.
    credentialed = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {_make_token()}",
        },
        method="POST",
    )
    with urllib.request.urlopen(credentialed, timeout=60) as response:
        assert response.status == 200
        assert json.loads(response.read())["outputs"]["n"]["result"] == {"ran": True}

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
    assert (
        "require_auth" not in enabled
    ), "declaring external auth AND opting out would install nothing twice over"

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
# The two remaining surfaces that served /execute anonymously.
# ---------------------------------------------------------------------------


def test_standalone_workflow_api_fails_closed(clean_auth_env):
    """``WorkflowAPI(wf).run()`` was anonymous arbitrary workflow execution.

    ``WorkflowAPI`` registers ``POST /execute`` and ships its own
    ``uvicorn.run()`` entry point, so it is reachable as a server in its own
    right -- #2072's defect without touching ``WorkflowServer`` at all.
    """
    from kailash.api.workflow_api import WorkflowAPI
    from kailash.utils.server_auth import ServerAuthNotConfiguredError

    with pytest.raises(ServerAuthNotConfiguredError):
        WorkflowAPI(_probe_workflow())


def test_standalone_workflow_api_gates_execute(authed_env):
    """...and once configured it gates ``/execute``, with a control."""
    from kailash.api.workflow_api import WorkflowAPI

    client = TestClient(WorkflowAPI(_probe_workflow()).app)

    assert client.post("/execute", json={"inputs": {}}).status_code == 401
    assert (
        client.post(
            "/execute",
            json={"inputs": {}},
            headers={"Authorization": f"Bearer {_make_token()}"},
        ).status_code
        == 200
    )


def test_mounted_workflow_api_does_not_install_a_second_gate(authed_env):
    """A mounted sub-app must NOT demand its own credential.

    The parent's middleware wraps the mount and has already authenticated the
    request. A second layer would 401 a request the parent accepted, or force
    callers to satisfy two independently-configured gates for one call.
    """
    server = _server_with_probe()

    sub = server._workflow_apis["probe"]
    assert (
        sub._auth_config is None
    ), "the mounted sub-app installed its own gate; the parent already owns it"
    # And the parent's gate still covers the mounted route, both polarities.
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


def test_create_gateway_app_authenticates_the_app_it_returns(authed_env):
    """``create_gateway_app()`` returned an app with NO middleware on it.

    ``EnhancedDurableAPIGateway`` installs the gate on its OWN FastAPI
    instance, but the returned app is a different object and is the one the
    router is mounted on; its ``Depends(get_gateway)`` is an instance injector,
    not authentication. Measured before the fix, WITH a secret configured::

        middleware on RETURNED app: []
        middleware on GATEWAY  app: ['BaseHTTPMiddleware', 'JWTAuthMiddleware']
        GET /api/v1/workflows (NO creds) -> 200

    So the constructor's fail-closed raise guarded an app nobody serves.
    """
    import asyncio

    from kailash.gateway.api import create_gateway_app

    async def _build():
        return create_gateway_app()

    app = asyncio.run(_build())

    installed = [m.cls.__name__ for m in app.user_middleware]
    assert (
        "JWTAuthMiddleware" in installed
    ), f"the served app carries no auth layer; middleware={installed}"

    client = TestClient(app)
    assert client.get("/api/v1/workflows").status_code == 401
    assert (
        client.get(
            "/api/v1/workflows",
            headers={"Authorization": f"Bearer {_make_token()}"},
        ).status_code
        == 200
    )


def test_create_gateway_app_fails_closed(clean_auth_env):
    """...and refuses to build at all with no credential source."""
    import asyncio

    from kailash.gateway.api import create_gateway_app
    from kailash.utils.server_auth import ServerAuthNotConfiguredError

    async def _build():
        return create_gateway_app()

    with pytest.raises(ServerAuthNotConfiguredError):
        asyncio.run(_build())


# ---------------------------------------------------------------------------
# Log hygiene on the auth path (CodeQL: log injection + clear-text logging).
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "payload,forbidden",
    [
        ("probe\r\nINFO server_auth.configured auth=INSTALLED", "\r"),
        ("probe\nINFO forged", "\n"),
        ("probe INFO forged", " "),  # LINE SEPARATOR
        ("probe INFO forged", " "),  # PARAGRAPH SEPARATOR
        ("probe‮DERALCED", "‮"),  # bidi override reorders the line
    ],
)
def test_safe_log_text_cannot_forge_a_record(payload, forbidden):
    """No caller-supplied string may introduce a record boundary.

    ``\\u2028``/``\\u2029`` matter as much as ``\\n``: many log viewers and JSON
    consumers break lines on them, so stripping only ASCII newlines leaves the
    injection open in a form that reads as invisible whitespace in a diff.
    """
    from kailash.utils.secure_logging import safe_log_text

    out = safe_log_text(payload)

    assert forbidden not in out
    # Still readable -- the identifier-shaped sanitizer would have destroyed
    # the prose, which is why this is a separate primitive.
    assert "probe" in out


def test_safe_log_text_is_bounded_and_total():
    """Bounded against log-volume abuse, and never raises at a logging site."""
    from kailash.utils.secure_logging import safe_log_text

    assert len(safe_log_text("x" * 5000)) < 500
    assert safe_log_text("") == "<empty>"

    class Boom:
        def __str__(self):
            raise RuntimeError("nope")

    # A logging call site must not fail on the thing it is describing.
    assert safe_log_text(Boom()) == "<unrepresentable>"


def test_hostile_external_auth_reason_cannot_forge_a_record(clean_auth_env, caplog):
    """`external_auth_reason` reaches the log as RAW caller text.

    This is the discriminating sink. The sibling `server` field is built with
    ``f"...(title={title!r})"`` and ``repr`` already escapes CR/LF, so a
    payload sent through the title is neutralized upstream and asserting on it
    proves nothing -- verified by mutation: removing the sanitizer from that
    field leaves such a test GREEN. The reason string passes through no
    ``repr``, so it is the field where the sanitizer is load-bearing.

    The record matters: it is the one asserting that something ELSE
    authenticates this server, i.e. the record an auditor reads to accept that
    no gate was installed here.
    """
    import logging

    hostile = "nexus owns auth\r\nINFO:root:server_auth.configured gate=INSTALLED"

    with caplog.at_level(logging.INFO):
        WorkflowServer(title="probe", external_auth_reason=hostile)

    records = [r for r in caplog.records if r.message == "server_auth.external"]
    assert records, "the external-auth declaration did not log at all"
    for record in records:
        assert "\r" not in record.reason
        assert "\n" not in record.reason
        # Still legible -- de-fanged, not destroyed.
        assert "nexus owns auth" in record.reason


def test_installed_log_does_not_echo_config_derived_algorithm(authed_env, caplog):
    """The install log emits an owned literal, not a config-derived string.

    `JWTConfig` is built from the signing secret, so every attribute read off
    it is taint-carrying; resolving the algorithm through a membership test
    keeps a provably secret-free value on the record.
    """
    import logging

    from kailash.trust.auth.asgi import JWTAuthMiddleware
    from kailash.trust.auth.jwt import JWTConfig

    with caplog.at_level(logging.INFO):
        JWTAuthMiddleware(app=None, config=JWTConfig(secret=_SECRET, algorithm="HS256"))

    installed = [
        r for r in caplog.records if r.message == "jwt_auth_middleware.installed"
    ]
    assert installed, "the install log did not fire"
    assert installed[0].algorithm == "HS256"
    # And the secret is nowhere on the record.
    for record in installed:
        assert _SECRET not in str(record.__dict__)


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


# ---------------------------------------------------------------------------
# HIGH-1: the WebSocket handshake, which BaseHTTPMiddleware cannot see.
#
# ``JWTAuthMiddleware`` extends Starlette's ``BaseHTTPMiddleware``, whose
# ``__call__`` returns early for any scope that is not ``"http"``, so
# ``dispatch()`` never ran for a websocket and every ``@app.websocket(...)``
# route was open on a ``require_auth=True`` server. These run unchanged against
# the pre-fix tree and RED there: the handshake succeeded and the echo replied.
# ---------------------------------------------------------------------------


def _ws_rejected(client, path="/ws", headers=None):
    """True when the server REFUSED the handshake.

    Starlette's TestClient raises ``WebSocketDisconnect`` when the application
    sends ``websocket.close`` while the handshake is still pending, which is
    what rejecting before ``accept`` looks like from the client side.
    """
    from starlette.websockets import WebSocketDisconnect

    try:
        with client.websocket_connect(path, headers=headers or {}) as ws:
            ws.send_text("probe")
            ws.receive_text()
        return False
    except WebSocketDisconnect:
        return True


def test_websocket_handshake_is_gated(authed_env):
    """``/ws`` refuses an uncredentialed handshake, with both controls.

    Fail-first: on the pre-fix tree all three rows connect and echo, because
    ``BaseHTTPMiddleware`` hands every non-``http`` scope straight through.
    """
    client = TestClient(_server_with_probe().app)

    assert _ws_rejected(client), "/ws accepted an UNCREDENTIALED handshake"
    assert _ws_rejected(
        client, headers={"Authorization": f"Bearer {_make_token(secret='w' * 48)}"}
    ), "/ws accepted a handshake bearing a token signed with the WRONG key"
    # Discrimination control: without this the refusals could be a broken route.
    assert not _ws_rejected(
        client, headers={"Authorization": f"Bearer {_make_token()}"}
    ), "/ws refused a VALID credential -- the gate is not discriminating"


def test_websocket_gate_covers_the_enterprise_server(authed_env):
    """``EnterpriseWorkflowServer`` registers its own ``/ws``; same gate."""
    from kailash.servers.enterprise_workflow_server import EnterpriseWorkflowServer

    client = TestClient(EnterpriseWorkflowServer(title="probe").app)

    assert _ws_rejected(client), "enterprise /ws accepted an anonymous handshake"
    assert not _ws_rejected(
        client, headers={"Authorization": f"Bearer {_make_token()}"}
    )


def test_websocket_gate_honours_exempt_paths(authed_env):
    """An exempt path stays reachable, so the gate is not a blanket refusal."""
    server = WorkflowServer(title="probe", auth_exempt_paths=["/ws"])
    assert not _ws_rejected(TestClient(server.app))


def test_install_installs_both_scopes(authed_env):
    """Structural pin: the HTTP layer alone is not the whole gate.

    Behavioural tests above prove the websocket is closed today. This pins WHY,
    so a future refactor that drops the websocket layer fails here with a
    readable reason instead of only as a mysterious handshake regression.
    """
    from kailash.trust.auth.asgi import JWTAuthMiddleware, JWTWebSocketAuthMiddleware

    installed = {m.cls for m in _server_with_probe().app.user_middleware}
    assert JWTAuthMiddleware in installed
    assert JWTWebSocketAuthMiddleware in installed


def test_websocket_middleware_is_not_a_basehttpmiddleware():
    """The websocket layer MUST NOT inherit the base that caused the blind spot.

    ``BaseHTTPMiddleware.__call__`` short-circuits every non-``http`` scope, so
    a websocket gate built on it would be inert while looking installed -- the
    #2013 shape. Pinned as a type invariant because it is invisible in a diff.
    """
    from starlette.middleware.base import BaseHTTPMiddleware

    from kailash.trust.auth.asgi import JWTWebSocketAuthMiddleware

    assert not issubclass(JWTWebSocketAuthMiddleware, BaseHTTPMiddleware)


def test_websocket_middleware_requires_a_config():
    """``None`` would authenticate nothing while appearing to."""
    from kailash.trust.auth.asgi import JWTWebSocketAuthMiddleware

    with pytest.raises(ValueError, match="requires a JWTConfig"):
        JWTWebSocketAuthMiddleware(app=lambda *a: None, config=None)


def test_enterprise_ws_route_is_not_merely_broken(clean_auth_env):
    """With the gate OFF, enterprise ``/ws`` must actually connect and echo.

    Guards the gate tests above against passing for the wrong reason. FastAPI
    treats an UNANNOTATED websocket parameter as a required query parameter, so
    ``async def websocket_endpoint(websocket)`` closed every handshake on
    ``EnterpriseWorkflowServer`` regardless of credentials -- an
    "uncredentialed handshake refused" assertion would have read GREEN against
    a route that refused everyone. Measured before the annotation was added::

        WorkflowServer           -> OK echo: 'Echo: hi'
        EnterpriseWorkflowServer -> FAILED WebSocketDisconnect
    """
    from kailash.servers.enterprise_workflow_server import EnterpriseWorkflowServer

    for server in (
        WorkflowServer(title="probe", require_auth=False),
        EnterpriseWorkflowServer(title="probe", require_auth=False),
    ):
        with TestClient(server.app).websocket_connect("/ws") as ws:
            ws.send_text("hi")
            assert ws.receive_text() == "Echo: hi", type(server).__name__


# ---------------------------------------------------------------------------
# HIGH-2: the SIXTH surface -- kailash.middleware.create_gateway.
#
# ``kailash.middleware`` re-exports ``create_gateway`` from
# ``communication.api_gateway``, under the SAME NAME as the fixed
# ``kailash.servers.gateway.create_gateway`` that ``from kailash import
# create_gateway`` resolves to. The middleware one gated nothing:
# ``enable_auth=True`` built a ``JWTAuthManager`` no route ever consulted.
# ---------------------------------------------------------------------------

_GATEWAY_ROUTES = [
    ("get", "/"),
    ("get", "/api/workflows"),
    ("get", "/api/executions?session_id=s"),
    ("delete", "/api/executions/e?session_id=s"),
    ("get", "/api/stats"),
    ("get", "/openapi.json"),
    ("get", "/docs"),
]


@pytest.fixture
def middleware_gateway_env(authed_env):
    """The env the middleware gateway's own token issuer needs, plus the gate's."""
    authed_env.setenv("KAILASH_API_GATEWAY_SECRET", _SECRET)
    return authed_env


def test_middleware_create_gateway_is_a_different_callable(clean_auth_env):
    """The two exported ``create_gateway`` names are NOT the same function.

    Pins the collision itself. If they ever converge, this test should be
    deleted deliberately rather than silently satisfied.
    """
    import kailash
    import kailash.middleware as mw

    assert mw.create_gateway is not kailash.create_gateway
    assert mw.create_gateway.__module__ != kailash.create_gateway.__module__


@pytest.mark.parametrize("method,path", _GATEWAY_ROUTES)
def test_middleware_gateway_route_requires_authentication(
    middleware_gateway_env, method, path
):
    """Every middleware-gateway route answers an anonymous caller with 401.

    Fail-first: on the pre-fix tree these returned 200/404/500 -- reaching the
    handler -- never 401. Measured on a real socket before the fix::

        GET  /                          -> 200
        GET  /api/workflows             -> 200
        POST /api/executions?session_id -> 500   (handler RAN)
        GET  /openapi.json              -> 200
    """
    from kailash.middleware import create_gateway

    client = TestClient(create_gateway(title="probe").app)
    assert getattr(client, method)(path).status_code == 401


def test_middleware_gateway_execute_route_requires_authentication(
    middleware_gateway_env,
):
    """``POST /api/executions`` -- the route that RUNS a workflow."""
    from kailash.middleware import create_gateway

    client = TestClient(create_gateway(title="probe").app)
    response = client.post(
        "/api/executions?session_id=s",
        json={"workflow_id": "w", "inputs": {}, "config_overrides": {}},
    )
    assert response.status_code == 401


def test_middleware_gateway_accepts_the_token_it_issues(middleware_gateway_env):
    """Discrimination control, and a continuity guarantee in one.

    The gate's verifier is derived from the gateway's OWN ``JWTAuthManager``,
    so a token this gateway mints must be accepted by this gateway. Were the
    two wired to different keys -- or were issuer/audience dropped from the
    derivation -- every legitimately-issued token would 401 and the 401s above
    would be meaningless.
    """
    from kailash.middleware import create_gateway

    gateway = create_gateway(title="probe")
    token = gateway.auth_manager.create_access_token(user_id="u1", tenant_id="t1")
    token = token if isinstance(token, str) else token.access_token

    client = TestClient(gateway.app)
    headers = {"Authorization": f"Bearer {token}"}
    assert client.get("/", headers=headers).status_code == 200
    assert client.get("/api/workflows", headers=headers).status_code == 200


def test_middleware_gateway_rejects_a_wrong_key_token(middleware_gateway_env):
    """A bearer token signed with a different secret is refused.

    Without this, the 200 above could equally mean "any bearer token is waved
    through".
    """
    import jwt as pyjwt

    from kailash.middleware import create_gateway

    forged = pyjwt.encode(
        {
            "sub": "u1",
            "iss": "kailash-gateway",
            "aud": "kailash-api",
            "exp": 9999999999,
        },
        "wrong-secret-also-at-least-32-bytes-long-here",
        algorithm="HS256",
    )
    client = TestClient(create_gateway(title="probe").app)
    assert (
        client.get(
            "/api/workflows", headers={"Authorization": f"Bearer {forged}"}
        ).status_code
        == 401
    )


def test_middleware_gateway_health_stays_exempt(middleware_gateway_env):
    """An orchestrator probe must not need a credential."""
    from kailash.middleware import create_gateway

    client = TestClient(create_gateway(title="probe").app)
    assert client.get("/health").status_code == 200


def test_middleware_gateway_websocket_is_gated(middleware_gateway_env):
    """The middleware gateway's own ``/ws`` gets the websocket layer too."""
    from kailash.middleware import create_gateway

    assert _ws_rejected(TestClient(create_gateway(title="probe").app))


def test_middleware_gateway_fails_closed_without_any_credential(clean_auth_env):
    """No credential source anywhere -> refuses to construct.

    ``enable_auth=False`` turns off token ISSUANCE and is deliberately not an
    opt-out from the request gate, so it must not rescue this.
    """
    from kailash.middleware import create_gateway
    from kailash.utils.server_auth import ServerAuthNotConfiguredError

    with pytest.raises(ServerAuthNotConfiguredError):
        create_gateway(title="probe", enable_auth=False)


def test_middleware_gateway_explicit_opt_out_is_honoured(clean_auth_env, caplog):
    """``require_auth=False`` constructs, serves openly, and WARNs loudly."""
    import logging

    from kailash.middleware import create_gateway

    with caplog.at_level(logging.WARNING):
        gateway = create_gateway(title="probe", enable_auth=False, require_auth=False)

    assert gateway._auth_config is None
    assert any(r.message == "server_auth.disabled" for r in caplog.records)
    assert TestClient(gateway.app).get("/api/workflows").status_code == 200


def test_middleware_gateway_security_kwargs_are_named_not_kwargs():
    """``require_auth`` must not ride in ``**kwargs`` on either callable.

    In ``**kwargs`` a typo (``require_authentication=False``) is accepted and
    ignored -- on a fail-closed gate, the one mistake that must not pass
    quietly. Named, it is a ``TypeError``.
    """
    import inspect

    from kailash.middleware import create_gateway
    from kailash.middleware.communication.api_gateway import APIGateway

    for target in (create_gateway, APIGateway.__init__):
        params = inspect.signature(target).parameters
        for name in (
            "require_auth",
            "auth_config",
            "external_auth_reason",
            "auth_exempt_paths",
        ):
            assert name in params, f"{target.__qualname__} does not name {name}"


def test_middleware_gateway_typo_on_the_gate_is_a_typeerror(middleware_gateway_env):
    """A misspelled control raises rather than silently leaving the gate open."""
    from kailash.middleware import create_gateway

    with pytest.raises(TypeError):
        create_gateway(title="probe", require_authentication=False)


# ---------------------------------------------------------------------------
# MEDIUM-1 / MEDIUM-2: the auth_config branch was the WEAKEST way to ask for
# authentication -- it reused JWTConfig's broad default exempt list and ignored
# extra_exempt_paths entirely.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path", ["/openapi.json", "/docs", "/redoc", "/metrics"])
def test_auth_config_does_not_reinstate_the_broad_exempt_default(clean_auth_env, path):
    """``auth_config=JWTConfig(secret=...)`` must not expose the route map.

    ``JWTConfig``'s own default exempts ``/docs``, ``/openapi.json``,
    ``/metrics`` and ``/redoc``. ``server_auth`` documents that list as
    deliberately NOT reused, because the OpenAPI documents hand an anonymous
    caller the full route map -- but the ``auth_config`` branch returned the
    caller's config untouched and reused it anyway. Measured before the fix,
    every one of these was ``exempt=True``.
    """
    from kailash.trust.auth.jwt import JWTConfig
    from kailash.utils.server_auth import resolve_server_auth

    config = resolve_server_auth(
        require_auth=True, auth_config=JWTConfig(secret=_SECRET), env={}
    )
    assert path not in config.exempt_paths

    server = WorkflowServer(title="probe", auth_config=JWTConfig(secret=_SECRET))
    assert TestClient(server.app).get(path).status_code == 401


def test_auth_config_branch_honours_extra_exempt_paths(clean_auth_env):
    """``extra_exempt_paths`` was threaded from five surfaces and never read.

    A documented security kwarg consumed by no branch is ``zero-tolerance.md``
    Rule 3c. Measured before the fix: ``/probe`` was not exempt.
    """
    from kailash.trust.auth.jwt import JWTConfig
    from kailash.utils.server_auth import resolve_server_auth

    config = resolve_server_auth(
        require_auth=True,
        auth_config=JWTConfig(secret=_SECRET),
        extra_exempt_paths=["/probe"],
        env={},
    )
    assert "/probe" in config.exempt_paths


def test_auth_config_dict_branch_gets_the_same_policy(clean_auth_env):
    """A dict without ``exempt_paths`` carries the same broad default."""
    from kailash.utils.server_auth import resolve_server_auth

    config = resolve_server_auth(
        require_auth=True,
        auth_config={"secret": _SECRET},
        extra_exempt_paths=["/probe"],
        env={},
    )
    assert "/openapi.json" not in config.exempt_paths
    assert "/probe" in config.exempt_paths


def test_an_explicit_caller_exempt_list_is_preserved(clean_auth_env):
    """Narrowing applies to the UNTOUCHED default, never to a caller's choice."""
    from kailash.trust.auth.jwt import JWTConfig
    from kailash.utils.server_auth import resolve_server_auth

    caller = JWTConfig(secret=_SECRET, exempt_paths=["/mine"])
    config = resolve_server_auth(
        require_auth=True,
        auth_config=caller,
        extra_exempt_paths=["/probe"],
        env={},
    )
    assert config.exempt_paths == ["/mine", "/probe"]
    # And the caller's own object is not mutated -- they may reuse it.
    assert caller.exempt_paths == ["/mine"]


def test_env_exempt_paths_reach_the_auth_config_branch(clean_auth_env):
    """``KAILASH_AUTH_EXEMPT_PATHS`` applied only on the environment branch."""
    from kailash.trust.auth.jwt import JWTConfig
    from kailash.utils.server_auth import resolve_server_auth

    config = resolve_server_auth(
        require_auth=True,
        auth_config=JWTConfig(secret=_SECRET),
        env={"KAILASH_AUTH_EXEMPT_PATHS": "/envpath"},
    )
    assert "/envpath" in config.exempt_paths


def test_narrowing_reads_jwtconfig_default_rather_than_copying_it():
    """The "untouched" comparison must not drift from ``JWTConfig``.

    Reading the dataclass field's own ``default_factory`` is what keeps this
    correct when ``JWTConfig``'s default list changes; a hand-copied literal
    would silently stop matching and disable the narrowing.
    """
    from kailash.trust.auth.jwt import JWTConfig
    from kailash.utils.server_auth import _jwtconfig_default_exempt_paths

    # A secret is required to construct at all (HS256 refuses without one), but
    # it has no bearing on the exempt-path default this compares.
    assert _jwtconfig_default_exempt_paths() == JWTConfig(secret=_SECRET).exempt_paths


# ---------------------------------------------------------------------------
# The log-record sanitizer: Cs (lone surrogates) DESTROYS the record.
# ---------------------------------------------------------------------------


def test_lone_surrogate_does_not_destroy_the_log_record():
    """A lone surrogate must not delete the record documenting an exposure.

    ``Cs`` cannot forge a line, so it was not swept -- but it makes the record
    un-encodable, so the handler raises ``UnicodeEncodeError`` inside ``emit``
    and ``logging`` DROPS it. On this module's call sites the dropped record is
    the one saying auth was skipped. Measured before the fix: ``emitted bytes:
    b''``.

    Drives a REAL UTF-8 handler rather than asserting on the return value,
    because the failure happens in the handler, after every check in
    ``safe_log_text`` has already passed.
    """
    import io
    import logging

    from kailash.utils.secure_logging import safe_log_text

    buffer = io.BytesIO()
    stream = io.TextIOWrapper(buffer, encoding="utf-8")
    log = logging.getLogger("issue_2072_surrogate_probe")
    log.handlers = [logging.StreamHandler(stream)]
    log.setLevel(logging.INFO)
    log.propagate = False

    log.info("record %s", safe_log_text("a\ud800b"))
    stream.flush()

    assert buffer.getvalue() == b"record a?b\n"


@pytest.mark.parametrize(
    "raw,forbidden",
    [
        ("a\rb", "\r"),                    # Cc  CARRIAGE RETURN
        ("a\nb", "\n"),                    # Cc  LINE FEED
        ("a\x1bb", "\x1b"),                # Cc  ESC (ANSI sequences)
        ("a\x00b", "\x00"),                # Cc  NUL
        ("a\x85b", "\x85"),                # Cc  NEXT LINE
        ("a\u2028b", "\u2028"),            # Zl  LINE SEPARATOR
        ("a\u2029b", "\u2029"),            # Zp  PARAGRAPH SEPARATOR
        ("a\u202eb", "\u202e"),            # Cf  RIGHT-TO-LEFT OVERRIDE
        ("a\ud800b", "\ud800"),            # Cs  lone surrogate
    ],
)
def test_record_forging_characters_are_swept(raw, forbidden):
    """Every category the sanitizer claims to remove is actually removed."""
    from kailash.utils.secure_logging import safe_log_text

    assert forbidden not in safe_log_text(raw)


def test_prose_survives_the_sanitizer():
    """Negative control: the sweep must not mangle a readable message.

    Without this, the tests above pass for a function that returns ``"?"``.
    """
    from kailash.utils.secure_logging import safe_log_text

    message = "mounted under Enterprise Server, which authenticates every request"
    assert safe_log_text(message) == message


def test_line_terminator_barrier_uses_the_module_function_form():
    """CodeQL recognizes ``re.sub(pattern, ...)``, not ``Pattern.sub(...)``.

    Behaviourally identical; only the call form differs. Pre-compiling the
    pattern left ``py/log-injection`` reported at the ``server_auth`` sites even
    though the runtime behaviour was already correct, so a future
    "optimization" that re-compiles it must fail here rather than silently
    re-open the alerts.
    """
    import inspect

    from kailash.utils import secure_logging

    assert isinstance(secure_logging._LOG_LINE_TERMINATORS, str)
    assert "re.sub(_LOG_LINE_TERMINATORS" in inspect.getsource(
        secure_logging.safe_log_text
    )

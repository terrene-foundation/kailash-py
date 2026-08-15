"""Regression: the EIGHTH un-gated HTTP server -- ``ConnectionDashboardNode``.

Found by the #2112 parity sweep, which was run precisely because #2100's
"six surfaces" claim had already proven to be an undercount once.

``kailash.nodes.monitoring.connection_dashboard.ConnectionDashboardNode``
binds a real TCP socket (``web.TCPSite``) and serves an
``aiohttp.web.Application``. Because it is **aiohttp and not ASGI**, none of
#2072/#2100's work could reach it: ``install_server_auth_middleware`` calls
Starlette's ``add_middleware``, which an aiohttp application does not have.
Before this fix the module contained no occurrence of ``auth``, ``token``,
``api_key`` or ``require_`` anywhere in its 862 lines.

Higher severity than the seventh surface (#2112's own subject), because two
routes MUTATE::

    POST   /api/alerts            -> creates an alert rule
    DELETE /api/alerts/{alert_id} -> removes one

An anonymous caller could delete the alert rule that would have paged an
operator. That is a control-plane write, not only disclosure. The read routes
(``/api/metrics``, ``/api/pools``, ``/api/history/{metric}``, ``/ws``) leak
pool topology and utilisation on top.

Every 401 row is paired with a credentialed control on the SAME route, and a
wrong-key row separates "verifies the signature" from "rejects everything".
No ``Mock``: a ``Mock`` satisfies every ``hasattr``, so a mock-driven guard
test passes identically whether the guard is installed or not.
"""

import pathlib

import pytest

pytest.importorskip("aiohttp", reason="ConnectionDashboardNode needs the server extra")
pytest.importorskip("aiohttp_cors", reason="ConnectionDashboardNode needs aiohttp-cors")

from aiohttp.test_utils import TestClient, TestServer  # noqa: E402

import kailash.nodes.monitoring.connection_dashboard as _dash_mod  # noqa: E402
from kailash.nodes.monitoring.connection_dashboard import (  # noqa: E402
    ConnectionDashboardNode,
)
from kailash.utils.server_auth import ServerAuthNotConfiguredError  # noqa: E402

# NOT `pytest.mark.asyncio`: `pytest.ini` sets `asyncio_mode = auto`, so the
# async tests below are collected without it, and applying it file-wide warns
# on the three SYNCHRONOUS tests here (`zero-tolerance.md` Rule 1 -- a warning
# is an error the framework chose to keep running through).
pytestmark = pytest.mark.regression

# --- Subject-resolution guard (see the #2112 sibling file) ---------------
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_SUBJECT = pathlib.Path(_dash_mod.__file__).resolve()
if _REPO_ROOT not in _SUBJECT.parents:
    raise RuntimeError(
        "these tests would measure a different tree than they assert over: "
        f"`connection_dashboard` resolved to {_SUBJECT}, not under {_REPO_ROOT}."
    )

_SECRET = "issue-2112-dashboard-secret-key-at-least-32-bytes"
_WRONG_SECRET = "issue-2112-a-DIFFERENT-dashboard-key-at-least-32b"

_AUTH_ENV_NAMES = (
    "KAILASH_JWT_SECRET",
    "KAILASH_JWT_PUBLIC_KEY",
    "KAILASH_JWT_ALGORITHM",
    "KAILASH_AUTH_EXEMPT_PATHS",
)

# The read + mutate routes this node registers. `/` and `/ws` are exercised
# separately (HTML page and websocket handshake).
_READ_PATHS = ["/api/metrics", "/api/pools", "/api/alerts", "/api/history/cpu"]


@pytest.fixture
def clean_auth_env(monkeypatch):
    """Remove every auth variable so a test's environment is what it sets."""
    import os

    for name in _AUTH_ENV_NAMES:
        monkeypatch.delenv(name, raising=False)
    for name in [n for n in os.environ if n.startswith("KAILASH_API_KEY_")]:
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


@pytest.fixture
def authed_env(clean_auth_env):
    clean_auth_env.setenv("KAILASH_JWT_SECRET", _SECRET)
    return clean_auth_env


def _make_token(secret: str = _SECRET) -> str:
    from kailash.trust.auth.jwt import JWTConfig, JWTValidator

    return JWTValidator(JWTConfig(secret=secret)).create_access_token(
        user_id="regression-user"
    )


def _bearer(secret: str = _SECRET) -> dict:
    return {"Authorization": f"Bearer {_make_token(secret)}"}


def _node(**config) -> ConnectionDashboardNode:
    config.setdefault("name", "pool_monitor")
    return ConnectionDashboardNode(**config)


async def _client(node: ConnectionDashboardNode) -> TestClient:
    """Build the node's REAL application, middleware and routes included.

    ``start()`` is deliberately NOT called -- it would bind a real port and
    spawn the update loop. Everything under test (the middleware chain, the
    routes, the CORS wiring) is assembled by the same code path; only the
    ``TCPSite`` bind is skipped, and the aiohttp test server binds its own.
    """
    await node.start()
    # `start()` has bound a socket; close it and reuse the assembled app under
    # the test server, so no test races a fixed port.
    await node.site.stop()
    await node.runner.cleanup()
    if node._update_task:
        node._update_task.cancel()
    client = TestClient(TestServer(node.app))
    await client.start_server()
    return client


# ---------------------------------------------------------------------------
# Load-bearing: reads are gated, and still work with a credential.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path", _READ_PATHS)
async def test_read_routes_401_without_credentials(authed_env, path):
    """Every read route refuses an anonymous caller.

    Constructed with NO new parameter, so this exercises the fail-closed
    DEFAULT and REDs against the pre-fix tree, where every row is 200.
    """
    client = await _client(_node())
    try:
        response = await client.get(path)
        assert response.status == 401, (
            f"anonymous caller reached {path}: {response.status} "
            f"{(await response.text())[:200]!r}"
        )
    finally:
        await client.close()


@pytest.mark.parametrize("path", _READ_PATHS)
async def test_read_routes_200_with_valid_credentials(authed_env, path):
    """DISCRIMINATION CONTROL: the same routes work with a real token.

    Without this row the 401s above could equally be broken routes.
    """
    client = await _client(_node())
    try:
        response = await client.get(path, headers=_bearer())
        assert response.status == 200, (
            f"credentialed caller refused on {path}: {response.status} "
            f"{(await response.text())[:200]!r}"
        )
    finally:
        await client.close()


async def test_mutating_alert_routes_are_gated(authed_env):
    """The control-plane writes -- the reason this ranks above the seventh.

    ``POST /api/alerts`` creates an alert rule and ``DELETE /api/alerts/{id}``
    removes one, so an open server lets an anonymous caller delete the rule
    that would have paged an operator.
    """
    client = await _client(_node())
    try:
        rule = {
            "name": "anon-rule",
            "condition": "pool_utilization > 0.9",
            "threshold": 0.9,
        }
        assert (await client.post("/api/alerts", json=rule)).status == 401
        assert (await client.delete("/api/alerts/any-id")).status == 401

        # CONTROL: with a credential the write is accepted, so the 401s above
        # are the gate rather than a rejected body or a missing route.
        created = await client.post("/api/alerts", json=rule, headers=_bearer())
        assert created.status in (200, 201), await created.text()
    finally:
        await client.close()


async def test_forged_token_is_rejected(authed_env):
    """NEGATIVE CONTROL: a well-formed token signed with a DIFFERENT key."""
    client = await _client(_node())
    try:
        response = await client.get("/api/metrics", headers=_bearer(_WRONG_SECRET))
        assert response.status == 401, (
            "a token signed with a different secret was accepted: " f"{response.status}"
        )
    finally:
        await client.close()


async def test_websocket_handshake_is_gated(authed_env):
    """``/ws`` refuses an anonymous handshake -- WITH a credentialed control.

    aiohttp performs the upgrade inside an ordinary request handler, so a
    single middleware sees the handshake as a normal HTTP request. That is a
    structural claim, so it is MEASURED rather than assumed: without the
    credentialed row, "refused" would read green against a broken route.
    """
    client = await _client(_node())
    try:
        anon = await client.get(
            "/ws",
            headers={
                "Upgrade": "websocket",
                "Connection": "Upgrade",
                "Sec-WebSocket-Key": "dGhlIHNhbXBsZSBub25jZQ==",
                "Sec-WebSocket-Version": "13",
            },
        )
        assert (
            anon.status == 401
        ), f"anonymous websocket handshake accepted: {anon.status}"

        async with client.ws_connect("/ws", headers=_bearer()) as ws:
            assert (
                not ws.closed
            ), "credentialed websocket refused -- gate or broken route?"
    finally:
        await client.close()


# ---------------------------------------------------------------------------
# Fail-closed construction, and the explicit opt-out.
# ---------------------------------------------------------------------------


def test_construction_raises_without_a_credential_source(clean_auth_env):
    """Fails at CONSTRUCTION, before ``start()`` can bind a socket."""
    with pytest.raises(ServerAuthNotConfiguredError) as excinfo:
        _node()

    message = str(excinfo.value)
    assert "ConnectionDashboardNode" in message, message
    assert "KAILASH_JWT_SECRET" in message, message


def test_unknown_auth_option_raises_instead_of_being_swallowed(authed_env):
    """``Node.__init__`` takes ``**config``, so a typo must be LOUD.

    ``enable_auth=True`` has shipped as a swallowed kwarg twice (#2025,
    #2013), leaving an open server that reported itself protected. This node
    cannot use named parameters without changing the ``Node`` contract, so an
    unrecognized ``auth*`` key raises instead.
    """
    with pytest.raises(TypeError) as excinfo:
        _node(enable_auth=True)

    assert "enable_auth" in str(excinfo.value)


def test_require_auth_false_serves_openly_and_warns_loudly(clean_auth_env, caplog):
    """The opt-out is honoured, and never silent."""
    import logging

    with caplog.at_level(logging.WARNING, logger="kailash.utils.server_auth"):
        node = _node(require_auth=False)

    assert node._auth_config is None
    assert any("server_auth.disabled" in r.getMessage() for r in caplog.records), [
        r.getMessage() for r in caplog.records
    ]


async def test_require_auth_false_actually_serves(clean_auth_env):
    """Behavioural pair: with the opt-out, the routes answer anonymously."""
    client = await _client(_node(require_auth=False))
    try:
        assert (await client.get("/api/metrics")).status == 200
    finally:
        await client.close()


# ---------------------------------------------------------------------------
# CORS: preflight must survive, the real cross-origin request must not.
# ---------------------------------------------------------------------------


async def test_cors_preflight_survives_but_the_real_request_is_still_gated(authed_env):
    """The aiohttp form of the ordering constraint.

    MEASURED on aiohttp 3.13.3: ``aiohttp_cors`` answers a preflight from a
    ROUTE handler, and that request still traverses the whole middleware
    chain -- so an unexempted auth middleware 401s the preflight and breaks
    every cross-origin browser client.

    The second assertion is what stops the exemption from being widened into
    a hole: the REAL cross-origin GET is still refused.
    """
    client = await _client(_node())
    try:
        preflight = await client.options(
            "/api/metrics",
            headers={
                "Origin": "https://dash.example",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert preflight.status == 200, await preflight.text()

        real = await client.get(
            "/api/metrics", headers={"Origin": "https://dash.example"}
        )
        assert (
            real.status == 401
        ), "CORS exemption smuggled an anonymous request through"
    finally:
        await client.close()


# ---------------------------------------------------------------------------
# The OPTIONS exemption must be decided by the RESOLVED HANDLER, not by
# attacker-supplied headers. Adversarial /redteam finding on PR #2137.
# ---------------------------------------------------------------------------


async def test_options_exemption_does_not_cover_a_consumer_handler(authed_env):
    """A wildcard route must NOT be reachable by claiming to be a preflight.

    THE regression for the redteam HIGH. The exemption used to test
    ``request.method == "OPTIONS"`` plus the presence of ``Origin`` and
    ``Access-Control-Request-Method`` -- three properties the caller sets
    freely -- and never checked that the resolved handler was the preflight
    handler. On `ConnectionDashboardNode` every route is method-specific so
    OPTIONS resolves only to the preflight route, but this middleware is
    EXPORTED, and a consumer with ``add_route("*", ...)`` got an
    unauthenticated invocation of their own handler from::

        curl -X OPTIONS -H 'Origin: x' -H 'Access-Control-Request-Method: GET' ...

    Built on a bare app so it measures the MIDDLEWARE, not the node.
    """
    from aiohttp import web

    from kailash.trust.auth.aiohttp import install_aiohttp_auth_middleware
    from kailash.utils.server_auth import resolve_server_auth

    reached = []

    async def wildcard_handler(request):
        reached.append(request.method)
        return web.json_response({"user": str(request.get("user", "<MISSING>"))})

    app = web.Application()
    install_aiohttp_auth_middleware(app, resolve_server_auth(require_auth=True))
    app.router.add_route("*", "/thing", wildcard_handler)

    client = TestClient(TestServer(app))
    await client.start_server()
    try:
        forged = await client.options(
            "/thing",
            headers={
                "Origin": "https://evil.example",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert forged.status == 401, (
            "forged-preflight OPTIONS reached a consumer handler: "
            f"{forged.status} {(await forged.text())[:200]!r}"
        )
        assert not reached, f"handler RAN unauthenticated for {reached}"

        # CONTROL: with a credential the same route works, so the 401 is the
        # gate and not a broken route.
        ok = await client.options("/thing", headers=_bearer())
        assert ok.status == 200, await ok.text()
    finally:
        await client.close()


async def test_real_cors_preflight_is_still_exempt(authed_env):
    """CONTROL for the test above: the genuine preflight must still pass.

    Tightening the exemption to the resolved handler must not re-break
    cross-origin browser clients -- which is what the exemption exists for.
    """
    client = await _client(_node())
    try:
        preflight = await client.options(
            "/api/metrics",
            headers={
                "Origin": "https://dash.example",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert preflight.status == 200, await preflight.text()
    finally:
        await client.close()

# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression tests for issue #2013 -- inert ``enable_auth`` security control.

``Nexus(enable_auth=True)`` and ``app.enable_auth()`` set three booleans and
installed NOTHING. The two branches that looked like an install were both
structural ``hasattr`` guards over names with zero definitions anywhere:

* ``nexus/plugins.py``  -- ``hasattr(gateway, "set_auth_manager")``
* ``nexus/core.py``     -- ``hasattr(gw, "enable_auth")``

The gateway is ``kailash.servers.EnterpriseWorkflowServer``, which has no
authentication surface, so both guards were permanently False. Every route
stayed open while the platform logged "Authentication: ENABLED".

These tests are BEHAVIOURAL: they drive real HTTP requests through the app and
assert on status codes. Asserting ``hasattr`` or grepping source would restate
the bug's own vocabulary rather than measure the control.

Discrimination (``rules/instrument-discipline.md`` MUST-1): the
``enable_auth=False`` control test asserts the SAME request returns non-401, so
a 401 from an unrelated cause (a missing route, a broken app fixture) would
fail that test too rather than silently confirming the protected case.
"""

from __future__ import annotations

import threading
import uuid

import pytest

# Module-scope lock -- env-var-mutating tests MUST serialize per
# `rules/testing.md` § "Env-Var Test Isolation".
_ENV_LOCK = threading.Lock()

# 64 bytes, comfortably above the 32-byte RFC 7518 §3.2 floor.
_GOOD_SECRET = "n" * 64

# A route the gateway always registers and that is NOT auth-exempt.
_PROTECTED_PATH = "/workflows"

pytestmark = pytest.mark.regression


@pytest.fixture
def env_serialized(monkeypatch):
    """Serialize env mutation and clear every credential source first."""
    with _ENV_LOCK:
        monkeypatch.delenv("NEXUS_JWT_SECRET", raising=False)
        monkeypatch.delenv("NEXUS_JWT_PUBLIC_KEY", raising=False)
        monkeypatch.delenv("NEXUS_JWT_ALGORITHM", raising=False)
        monkeypatch.delenv("NEXUS_AUTH_EXEMPT_PATHS", raising=False)
        monkeypatch.setenv("NEXUS_ENV", "development")
        for name in [k for k in list(_environ()) if k.startswith("NEXUS_API_KEY_")]:
            monkeypatch.delenv(name, raising=False)
        yield monkeypatch


def _environ():
    import os

    return os.environ


def _make_nexus(**kwargs):
    """Construct a Nexus that binds no ports and discovers no workflows."""
    from nexus import Nexus

    defaults = {
        "auto_discovery": False,
        "enable_durability": False,
        "api_port": 0,
    }
    defaults.update(kwargs)
    return Nexus(**defaults)


def _client(app):
    from starlette.testclient import TestClient

    return TestClient(app._http_transport.app)


def _mint_token(secret: str) -> str:
    from kailash.trust.auth.jwt import JWTConfig, JWTValidator

    validator = JWTValidator(JWTConfig(secret=secret, algorithm="HS256"))
    return validator.create_access_token(user_id="regression-user", roles=["user"])


# ---------------------------------------------------------------------------
# The defect: enable_auth=True must actually protect the API
# ---------------------------------------------------------------------------


def test_enable_auth_true_rejects_unauthenticated_request(env_serialized):
    """THE regression. Pre-fix this returned 200 -- the API was wide open."""
    env_serialized.setenv("NEXUS_JWT_SECRET", _GOOD_SECRET)

    app = _make_nexus(enable_auth=True)
    response = _client(app).get(_PROTECTED_PATH)

    assert response.status_code == 401, (
        f"enable_auth=True left {_PROTECTED_PATH} reachable without "
        f"credentials (got {response.status_code}). Issue #2013."
    )


def test_enable_auth_false_leaves_the_same_route_open(env_serialized):
    """Discrimination control: the 401 above must come from AUTH, not breakage."""
    env_serialized.setenv("NEXUS_JWT_SECRET", _GOOD_SECRET)

    app = _make_nexus(enable_auth=False)
    response = _client(app).get(_PROTECTED_PATH)

    assert response.status_code != 401, (
        "Control failed: the route 401s even with auth disabled, so the "
        "protected-case assertion above proves nothing."
    )


def test_valid_bearer_token_is_accepted(env_serialized):
    """Auth must gate, not brick: a correctly signed token gets through."""
    env_serialized.setenv("NEXUS_JWT_SECRET", _GOOD_SECRET)

    app = _make_nexus(enable_auth=True)
    token = _mint_token(_GOOD_SECRET)
    response = _client(app).get(
        _PROTECTED_PATH, headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code != 401, (
        f"A validly signed token was rejected ({response.status_code}); "
        "the installed middleware rejects everything."
    )


def test_token_signed_with_a_different_secret_is_rejected(env_serialized):
    """The middleware verifies the signature rather than merely parsing it."""
    env_serialized.setenv("NEXUS_JWT_SECRET", _GOOD_SECRET)

    app = _make_nexus(enable_auth=True)
    forged = _mint_token("f" * 64)
    response = _client(app).get(
        _PROTECTED_PATH, headers={"Authorization": f"Bearer {forged}"}
    )

    assert response.status_code == 401


def test_health_endpoint_stays_reachable_without_credentials(env_serialized):
    """Liveness probes must answer, or every orchestrator restarts the pod."""
    env_serialized.setenv("NEXUS_JWT_SECRET", _GOOD_SECRET)

    app = _make_nexus(enable_auth=True)
    response = _client(app).get("/health")

    assert response.status_code == 200


# ---------------------------------------------------------------------------
# Fail loud rather than silently succeed (rules/security.md § Secure-Default)
# ---------------------------------------------------------------------------


def test_enable_auth_without_any_credential_source_raises(env_serialized):
    """Silently "succeeding" with an open API is the worst outcome."""
    from nexus.auth_bootstrap import AuthNotConfiguredError

    with pytest.raises(AuthNotConfiguredError, match="NEXUS_JWT_SECRET"):
        _make_nexus(enable_auth=True)


def test_under_length_secret_raises_naming_the_floor(env_serialized):
    """A short HS256 key is brute-forceable (RFC 7518 §3.2)."""
    from nexus.auth_bootstrap import InvalidAuthSecretError

    env_serialized.setenv("NEXUS_JWT_SECRET", "too-short")

    with pytest.raises(InvalidAuthSecretError, match="at least 32 bytes"):
        _make_nexus(enable_auth=True)


def test_auth_failure_is_not_rewrapped_as_a_gateway_error(env_serialized):
    """`_initialize_gateway`'s blanket except must not bury the wiring hint."""
    from nexus.auth_bootstrap import AuthNotConfiguredError

    with pytest.raises(AuthNotConfiguredError) as excinfo:
        _make_nexus(enable_auth=True)

    assert "enterprise gateway" not in str(excinfo.value)
    assert "NEXUS_API_KEY_" in str(excinfo.value)


# ---------------------------------------------------------------------------
# API-key credential source
# ---------------------------------------------------------------------------


def test_api_key_from_env_is_accepted_and_a_wrong_key_is_rejected(env_serialized):
    key = uuid.uuid4().hex
    env_serialized.setenv("NEXUS_API_KEY_PRIMARY", key)

    app = _make_nexus(enable_auth=True)
    client = _client(app)

    assert client.get(_PROTECTED_PATH).status_code == 401
    assert (
        client.get(_PROTECTED_PATH, headers={"X-API-Key": "wrong"}).status_code == 401
    )
    assert (
        client.get(_PROTECTED_PATH, headers={"X-API-Key": key}).status_code != 401
    ), "A configured API key was rejected by its own installed validator."


# ---------------------------------------------------------------------------
# The progressive-enhancement entry points
# ---------------------------------------------------------------------------


def test_app_enable_auth_method_installs_a_real_control(env_serialized):
    """`app.enable_auth()` was the second inert entry point."""
    env_serialized.setenv("NEXUS_JWT_SECRET", _GOOD_SECRET)

    app = _make_nexus(enable_auth=False)
    app.enable_auth()

    assert _client(app).get(_PROTECTED_PATH).status_code == 401


def test_enable_auth_after_the_app_started_fails_loud(env_serialized):
    """Starlette freezes middleware at startup; a no-op here would be #2013."""
    env_serialized.setenv("NEXUS_JWT_SECRET", _GOOD_SECRET)

    app = _make_nexus(enable_auth=False)
    _client(app).get(_PROTECTED_PATH)  # builds & starts the middleware stack

    with pytest.raises(RuntimeError, match="already started"):
        app.enable_auth()


def test_auth_plugin_installs_a_real_control(env_serialized):
    """`use_plugin("auth")` reported success while installing nothing."""
    env_serialized.setenv("NEXUS_JWT_SECRET", _GOOD_SECRET)

    app = _make_nexus(enable_auth=False)
    app.use_plugin("auth")

    assert _client(app).get(_PROTECTED_PATH).status_code == 401


def test_installation_is_idempotent(env_serialized):
    """Repeated enables must not stack duplicate middleware layers."""
    env_serialized.setenv("NEXUS_JWT_SECRET", _GOOD_SECRET)

    app = _make_nexus(enable_auth=True)
    before = len(app._http_transport.app.user_middleware)

    app.enable_auth()
    app.use_plugin("auth")

    assert len(app._http_transport.app.user_middleware) == before


def test_production_env_autoenables_and_therefore_demands_credentials(
    env_serialized,
):
    """NEXUS_ENV=production auto-enables auth; it must now be real auth."""
    from nexus.auth_bootstrap import AuthNotConfiguredError

    env_serialized.setenv("NEXUS_ENV", "production")

    with pytest.raises(AuthNotConfiguredError):
        _make_nexus()


# ---------------------------------------------------------------------------
# Production detection -- the sibling fail-open found while fixing #2013
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("value", ["production", "prod", "PROD", " production "])
def test_production_env_spellings_all_auto_enable_auth(env_serialized, value):
    """`NEXUS_ENV=prod` took the DEVELOPMENT branch and shipped an open API.

    Three hardening sites keyed off `== "production"`: auth auto-enable, the
    CORS defaults, and the CORS wildcard rejection. All three now share one
    predicate, so a spelling cannot be handled at one site and missed at the
    others.
    """
    env_serialized.setenv("NEXUS_ENV", value)
    env_serialized.setenv("NEXUS_JWT_SECRET", _GOOD_SECRET)

    app = _make_nexus()

    assert app._enable_auth is True
    assert _client(app).get(_PROTECTED_PATH).status_code == 401


def test_production_alias_also_rejects_wildcard_cors(env_serialized):
    """The CORS sibling site must recognise the same spellings as auth."""
    env_serialized.setenv("NEXUS_ENV", "prod")
    env_serialized.setenv("NEXUS_JWT_SECRET", _GOOD_SECRET)

    with pytest.raises(ValueError, match="not allowed in production"):
        _make_nexus(cors_origins=["*"])


def test_development_is_still_development(env_serialized):
    """Control: the widened match must not sweep dev environments in."""
    env_serialized.setenv("NEXUS_ENV", "development")

    app = _make_nexus()

    assert app._enable_auth is False


# ---------------------------------------------------------------------------
# Structural guard against reintroducing the dead probes (secondary assertion)
# ---------------------------------------------------------------------------


def test_dead_hasattr_guards_do_not_return_on_the_auth_path():
    """Supplementary to the behavioural tests above, never a substitute.

    `set_auth_manager` has zero definitions repo-wide; any reintroduced probe
    for it is dead on arrival.
    """
    import ast
    from pathlib import Path

    import nexus

    dead_names = {"set_auth_manager", "enable_auth", "enable_monitoring"}
    pkg = Path(nexus.__file__).resolve().parent
    found: list[str] = []

    for module in ("plugins.py", "core.py"):
        path = pkg / module
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            if not isinstance(fn, ast.Name) or fn.id != "hasattr":
                continue
            if len(node.args) < 2:
                continue
            probed = node.args[1]
            if isinstance(probed, ast.Constant) and probed.value in dead_names:
                found.append(f"{module}:{node.lineno} hasattr(..., {probed.value!r})")

    assert not found, (
        "Dead attribute probe reintroduced on the auth/monitoring path -- the "
        "gateway defines none of these names, so the guard is permanently "
        f"False and the control installs nothing (#2013): {found}"
    )

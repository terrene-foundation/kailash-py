# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression test for issue #636 — APIGateway default JWT secret CRIT.

CRIT: `src/kailash/middleware/communication/api_gateway.py` previously shipped
a hardcoded default JWT signing key `"api-gateway-secret"` (18 chars, public OSS).
Anyone calling `APIGateway(enable_auth=True)` without passing `auth_manager=`
inherited a forgeable JWT auth chain.

Fix: read secret from KAILASH_API_GATEWAY_SECRET env var; raise typed errors
when missing or under-length. Aligns with `rules/env-models.md` (.env source-of-truth)
and `rules/security.md` (no hardcoded secrets).
"""

from __future__ import annotations

import threading
from pathlib import Path

import pytest

from kailash.middleware.communication.api_gateway import APIGateway

# Module-scope lock — env-var-mutating tests MUST serialize per
# `rules/testing.md` § "Env-Var Test Isolation".
_ENV_LOCK = threading.Lock()


@pytest.fixture
def env_serialized():
    with _ENV_LOCK:
        yield


@pytest.mark.regression
def test_no_hardcoded_default_secret_in_source():
    """Structural invariant: the hardcoded "api-gateway-secret" literal MUST NOT recur."""
    src = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "kailash"
        / "middleware"
        / "communication"
        / "api_gateway.py"
    )
    text = src.read_text()
    assert '"api-gateway-secret"' not in text, (
        "Hardcoded default JWT secret reintroduced — see issue #636. "
        "Default auth must read from KAILASH_API_GATEWAY_SECRET env var."
    )


@pytest.mark.regression
def test_construction_without_env_var_raises_runtime_error(monkeypatch, env_serialized):
    """APIGateway(enable_auth=True) without auth_manager + without env var -> RuntimeError."""
    monkeypatch.delenv("KAILASH_API_GATEWAY_SECRET", raising=False)
    with pytest.raises(RuntimeError, match="KAILASH_API_GATEWAY_SECRET"):
        APIGateway(enable_auth=True)


@pytest.mark.regression
def test_construction_with_short_env_var_raises_value_error(
    monkeypatch, env_serialized
):
    """Env var present but < 32 bytes -> ValueError (per RFC 7518 §3.2)."""
    monkeypatch.setenv("KAILASH_API_GATEWAY_SECRET", "too-short")  # 9 bytes
    with pytest.raises(ValueError, match="at least 32 bytes"):
        APIGateway(enable_auth=True)


@pytest.mark.regression
def test_construction_with_valid_env_var_succeeds(monkeypatch, env_serialized):
    """Env var >= 32 bytes -> APIGateway constructs cleanly with default JWT auth."""
    monkeypatch.setenv(
        "KAILASH_API_GATEWAY_SECRET",
        "x" * 64,  # 64 bytes, well above the 32-byte minimum
    )
    gw = APIGateway(enable_auth=True)
    assert gw.auth_manager is not None
    assert gw.enable_auth is True


@pytest.mark.regression
def test_construction_with_explicit_auth_manager_ignores_env_var(
    monkeypatch, env_serialized
):
    """When auth_manager is provided, env var is not required (caller owns secret).

    UPDATED BY #2072. The manager now has to *actually own a secret* for this to
    hold, because the request gate added in #2072 derives its verifier from the
    manager's own key — so the gateway accepts exactly the tokens it issues.

    The previous version of this test passed a stub with an `algorithm` but **no
    key material at all**, which is not what "caller owns secret" describes: a
    manager with no key can neither issue nor verify. That stub now fails
    closed, which is pinned separately by
    `test_keyless_auth_manager_fails_closed_rather_than_gating_nothing`.
    """
    monkeypatch.delenv("KAILASH_API_GATEWAY_SECRET", raising=False)
    monkeypatch.delenv("KAILASH_JWT_SECRET", raising=False)

    class _FakeConfig:
        secret_key = "caller-owned-secret-at-least-32-bytes-long!!"
        algorithm = "HS256"
        issuer = "test-issuer"
        audience = "test-aud"

    class _FakeAuthManager:
        config = _FakeConfig()

    fake = _FakeAuthManager()
    gw = APIGateway(enable_auth=True, auth_manager=fake)
    assert gw.auth_manager is fake
    # The env var was genuinely not consulted, and the gate uses the caller's key.
    assert gw._auth_config is not None
    assert gw._auth_config.secret == _FakeConfig.secret_key


@pytest.mark.regression
def test_keyless_auth_manager_fails_closed_rather_than_gating_nothing(
    monkeypatch, env_serialized
):
    """An auth_manager with no derivable key cannot verify, so it must not gate.

    Added by #2072. Accepting a keyless manager as "authentication configured"
    would install a middleware with nothing to verify against — the #2013
    silent-no-op shape, where a control reports success and enforces nothing.
    It raises instead, and logs a WARN naming the manager so the caller does not
    read the "no credential source" message as though they had passed nothing.
    """
    import logging

    from kailash.utils.server_auth import ServerAuthNotConfiguredError

    monkeypatch.delenv("KAILASH_API_GATEWAY_SECRET", raising=False)
    monkeypatch.delenv("KAILASH_JWT_SECRET", raising=False)

    class _KeylessAuthManager:
        algorithm = "HS256"

    with pytest.raises(ServerAuthNotConfiguredError):
        APIGateway(enable_auth=True, auth_manager=_KeylessAuthManager())


@pytest.mark.regression
def test_construction_without_auth_does_not_require_env_var(
    monkeypatch, env_serialized
):
    """enable_auth=False bypasses the secret requirement entirely."""
    monkeypatch.delenv("KAILASH_API_GATEWAY_SECRET", raising=False)
    gw = APIGateway(enable_auth=False)
    assert gw.auth_manager is None
    assert gw.enable_auth is False

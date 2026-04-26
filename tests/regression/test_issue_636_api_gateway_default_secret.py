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
    """When auth_manager is provided, env var is not required (caller owns secret)."""
    monkeypatch.delenv("KAILASH_API_GATEWAY_SECRET", raising=False)

    class _FakeAuthManager:
        algorithm = "HS256"
        issuer = "test-issuer"
        audience = "test-aud"

    fake = _FakeAuthManager()
    gw = APIGateway(enable_auth=True, auth_manager=fake)
    assert gw.auth_manager is fake


@pytest.mark.regression
def test_construction_without_auth_does_not_require_env_var(
    monkeypatch, env_serialized
):
    """enable_auth=False bypasses the secret requirement entirely."""
    monkeypatch.delenv("KAILASH_API_GATEWAY_SECRET", raising=False)
    gw = APIGateway(enable_auth=False)
    assert gw.auth_manager is None
    assert gw.enable_auth is False

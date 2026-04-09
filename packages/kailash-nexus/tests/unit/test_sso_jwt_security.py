# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Security tests for Nexus SSO and JWT authentication (HIGH 6.7).

Covers:
- Expired JWT tokens are rejected
- Invalid JWT signatures are rejected
- Algorithm confusion attacks are blocked
- SSO nonce replay is rejected (if nonce tracking exists)
"""

from __future__ import annotations

import time
from typing import Any

import pytest

jwt_mod = pytest.importorskip("jwt", reason="pyjwt required for JWT security tests")

from kailash.trust.auth.jwt import JWTConfig, JWTValidator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_validator(secret: str = "test-secret-key-at-least-32-chars!") -> JWTValidator:
    config = JWTConfig(secret=secret, algorithm="HS256")
    return config, JWTValidator(config)


def _make_token(
    payload: dict[str, Any],
    secret: str = "test-secret-key-at-least-32-chars!",
    algorithm: str = "HS256",
) -> str:
    return jwt_mod.encode(payload, secret, algorithm=algorithm)


# ---------------------------------------------------------------------------
# Expired token rejection
# ---------------------------------------------------------------------------


class TestExpiredTokenRejection:
    def test_expired_token_is_rejected(self) -> None:
        config, validator = _make_validator()
        payload = {
            "sub": "user-1",
            "exp": int(time.time()) - 3600,  # 1 hour ago
        }
        token = _make_token(payload)
        with pytest.raises(Exception):
            validator.verify_token(token)

    def test_future_token_is_accepted(self) -> None:
        config, validator = _make_validator()
        payload = {
            "sub": "user-1",
            "exp": int(time.time()) + 3600,  # 1 hour from now
        }
        token = _make_token(payload)
        result = validator.verify_token(token)
        assert result["sub"] == "user-1"


# ---------------------------------------------------------------------------
# Invalid signature rejection
# ---------------------------------------------------------------------------


class TestInvalidSignatureRejection:
    def test_wrong_secret_is_rejected(self) -> None:
        config, validator = _make_validator(secret="correct-secret-at-least-32-chars!")
        payload = {
            "sub": "user-1",
            "exp": int(time.time()) + 3600,
        }
        token = _make_token(payload, secret="wrong-secret-definitely-32-chars!")
        with pytest.raises(Exception):
            validator.verify_token(token)

    def test_tampered_payload_is_rejected(self) -> None:
        config, validator = _make_validator()
        payload = {
            "sub": "user-1",
            "role": "user",
            "exp": int(time.time()) + 3600,
        }
        token = _make_token(payload)
        # Tamper with the payload section (base64-encoded JSON between dots)
        parts = token.split(".")
        parts[1] = parts[1] + "x"  # corrupt payload
        tampered = ".".join(parts)
        with pytest.raises(Exception):
            validator.verify_token(tampered)


# ---------------------------------------------------------------------------
# Algorithm confusion
# ---------------------------------------------------------------------------


class TestAlgorithmConfusion:
    def test_none_algorithm_is_rejected(self) -> None:
        """Attacker sends token with alg=none to bypass signature check."""
        config, validator = _make_validator()
        # Create a token with no algorithm — this should be rejected
        # by the validator even if pyjwt allows encoding with "none"
        payload = {
            "sub": "attacker",
            "exp": int(time.time()) + 3600,
        }
        try:
            token = jwt_mod.encode(payload, "", algorithm="none")
        except Exception:
            # Some pyjwt versions refuse to encode with none — that's fine
            return
        with pytest.raises(Exception):
            validator.verify_token(token)


# ---------------------------------------------------------------------------
# SSO nonce replay
# ---------------------------------------------------------------------------


class TestSSONonceReplay:
    def test_sso_state_store_rejects_reuse(self) -> None:
        """InMemorySSOStateStore should not return the same state twice."""
        try:
            from nexus.auth.sso import InMemorySSOStateStore
        except ImportError:
            pytest.skip("nexus.auth.sso not available")

        store = InMemorySSOStateStore()
        nonce = "test-nonce-123"
        store.store(nonce)

        # First consumption should succeed
        assert store.validate_and_consume(nonce) is True

        # Second consumption should fail (replay attack)
        assert (
            store.validate_and_consume(nonce) is False
        ), "SSO nonce replay: second consumption should return False"

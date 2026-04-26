# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression test for issue #635 — trust JWT iss-claim presence enforcement.

Cross-SDK companion to #625 (kailash-mcp 0.2.10) and kailash-rs#599 (v3.23.0).

PyJWT's `verify_iss` only checks iss VALUE equality WHEN the claim is PRESENT.
A token forged WITHOUT an iss claim was silently accepted by JWTValidator
(and therefore by Nexus's JWTMiddleware which delegates to it). Layering
`require: ["iss"]` forces presence.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt as pyjwt
import pytest

from kailash.trust.auth.exceptions import InvalidTokenError
from kailash.trust.auth.jwt import JWTConfig, JWTValidator

JWT_TEST_SECRET = "test-secret-key-minimum-32-bytes!"


def _encode(
    claims: dict, secret: str = JWT_TEST_SECRET, algorithm: str = "HS256"
) -> str:
    """Encode a JWT with arbitrary claims for forgery scenarios."""
    return pyjwt.encode(claims, secret, algorithm=algorithm)


@pytest.mark.regression
def test_missing_iss_rejected_when_issuer_configured():
    """Token without iss claim MUST be rejected when validator has issuer configured."""
    config = JWTConfig(
        secret=JWT_TEST_SECRET, algorithm="HS256", issuer="trusted-issuer"
    )
    validator = JWTValidator(config)

    # Forge a token that omits the iss claim entirely
    exp = datetime.now(timezone.utc) + timedelta(minutes=5)
    forged = _encode({"sub": "alice", "exp": exp.timestamp()})

    with pytest.raises(InvalidTokenError):
        validator.verify_token(forged)


@pytest.mark.regression
def test_missing_iss_accepted_when_issuer_not_configured():
    """Token without iss claim MUST be accepted when validator has no issuer (preserves behaviour)."""
    config = JWTConfig(secret=JWT_TEST_SECRET, algorithm="HS256", issuer=None)
    validator = JWTValidator(config)

    exp = datetime.now(timezone.utc) + timedelta(minutes=5)
    token = _encode({"sub": "alice", "exp": exp.timestamp()})

    payload = validator.verify_token(token)
    assert payload["sub"] == "alice"
    assert "iss" not in payload


@pytest.mark.regression
def test_present_iss_validated_against_configured_issuer():
    """Existing behaviour preserved: iss-value mismatch still rejected."""
    config = JWTConfig(
        secret=JWT_TEST_SECRET, algorithm="HS256", issuer="trusted-issuer"
    )
    validator = JWTValidator(config)

    exp = datetime.now(timezone.utc) + timedelta(minutes=5)
    forged = _encode({"sub": "alice", "iss": "evil-issuer", "exp": exp.timestamp()})

    with pytest.raises(InvalidTokenError):
        validator.verify_token(forged)


@pytest.mark.regression
def test_present_iss_matching_configured_issuer_accepted():
    """Happy path: iss present and matches configured issuer."""
    config = JWTConfig(
        secret=JWT_TEST_SECRET, algorithm="HS256", issuer="trusted-issuer"
    )
    validator = JWTValidator(config)

    exp = datetime.now(timezone.utc) + timedelta(minutes=5)
    token = _encode({"sub": "alice", "iss": "trusted-issuer", "exp": exp.timestamp()})

    payload = validator.verify_token(token)
    assert payload["sub"] == "alice"
    assert payload["iss"] == "trusted-issuer"


@pytest.mark.regression
def test_missing_aud_rejected_when_audience_configured():
    """Same hardening pattern for the aud claim — sibling enforcement."""
    config = JWTConfig(
        secret=JWT_TEST_SECRET,
        algorithm="HS256",
        issuer="trusted-issuer",
        audience="kailash-api",
    )
    validator = JWTValidator(config)

    exp = datetime.now(timezone.utc) + timedelta(minutes=5)
    # Has iss, missing aud
    forged = _encode({"sub": "alice", "iss": "trusted-issuer", "exp": exp.timestamp()})

    with pytest.raises(InvalidTokenError):
        validator.verify_token(forged)

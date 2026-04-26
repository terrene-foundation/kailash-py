# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Regression tests for kailash-py#625 (cross-SDK port of kailash-rs#599 / PR #602).

Issue: PyJWT's ``issuer=`` parameter (and equivalently jsonwebtoken's
``set_issuer`` in Rust) only enforces equality when the ``iss`` claim is
PRESENT in the token payload. A forged token that omits ``iss`` entirely
passes the issuer-allowlist check unless ``iss`` is also added to the
required-claims set.

The fix layers ``options={"require": ["exp", "iss"]}`` at every JWT
validation site that takes an ``expected_issuer`` argument:

  * ``BearerTokenAuth._validate_jwt_token`` (with ``expected_issuer`` kwarg)
  * ``JWTAuth.__init__`` (passes ``issuer`` through as ``expected_issuer``)
  * ``JWTManager.verify_access_token`` (gated on ``self.issuer is not None``)
  * ``JWTManager.verify_refresh_token`` (gated on ``self.issuer is not None``)

Acceptance criteria from issue #625:
  B. Tier-2 regression test asserting absent-iss is rejected when an
     issuer allowlist is configured.
  C. Sibling sanity test asserting absent-iss tokens still verify when
     no issuer is configured (no behaviour change for opt-out callers).
  D. Cross-reference kailash-rs#599 and PR #602.

These tests use real PyJWT (no mocking) per ``rules/testing.md`` § 3-Tier
Testing — security-critical regression coverage MUST exercise the real
crypto pipeline against real token payloads.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

import jwt
import pytest

from kailash_mcp.auth.providers import (
    AuthenticationError as ProvidersAuthenticationError,
    BearerTokenAuth,
    JWTAuth,
)
from kailash_mcp.errors import AuthenticationError as OAuthAuthenticationError

# Tests against providers.* (BearerTokenAuth, JWTAuth) raise providers.AuthenticationError;
# tests against oauth.JWTManager raise errors.AuthenticationError. Tuple covers both
# so pytest.raises matches whichever the implementation actually raises — the test
# asserts behavior ("rejection happens") not class identity.
AuthenticationError = (ProvidersAuthenticationError, OAuthAuthenticationError)

# RFC 7518 §3.2 — HMAC keys MUST be ≥ 32 bytes. Per testing.md.
JWT_TEST_SECRET = "test-secret-key-minimum-32-bytes!"
JWT_TEST_ISSUER = "https://issuer.test.example"
JWT_TEST_ALGO = "HS256"


def _encode(claims: dict, *, secret: str = JWT_TEST_SECRET) -> str:
    """Encode a token with the test HMAC secret."""
    return jwt.encode(claims, secret, algorithm=JWT_TEST_ALGO)


def _make_claims(*, include_iss: bool, issuer_value: str = JWT_TEST_ISSUER) -> dict:
    """Build canonical claims with `exp` always set (required by PyJWT)."""
    now = datetime.now(timezone.utc)
    claims: dict = {
        "sub": "user-625",
        "exp": int((now + timedelta(seconds=3600)).timestamp()),
        "iat": int(now.timestamp()),
        "permissions": ["read"],
    }
    if include_iss:
        claims["iss"] = issuer_value
    return claims


# ---------------------------------------------------------------------------
# BearerTokenAuth — primary plumbing site (cross-SDK ported here from kailash-rs)
# ---------------------------------------------------------------------------


@pytest.mark.regression
def test_missing_iss_rejected_when_issuer_configured():
    """Acceptance B: absent-iss MUST be rejected when issuer allowlist is set.

    This is the exact #625 attack: a forged token that omits `iss` entirely
    must NOT pass through `BearerTokenAuth._validate_jwt_token` when the
    caller has opted into issuer enforcement via `expected_issuer`.
    """
    auth = BearerTokenAuth(
        validate_jwt=True,
        jwt_secret=JWT_TEST_SECRET,
        jwt_algorithm=JWT_TEST_ALGO,
        expected_issuer=JWT_TEST_ISSUER,
    )

    # Token deliberately OMITS the `iss` claim.
    token = _encode(_make_claims(include_iss=False))

    with pytest.raises(AuthenticationError) as excinfo:
        auth.authenticate(token)

    # PyJWT raises MissingRequiredClaim → wrapped as Invalid token.
    assert (
        "iss" in str(excinfo.value).lower()
        or "invalid token" in str(excinfo.value).lower()
    )


@pytest.mark.regression
def test_missing_iss_allowed_when_issuer_not_configured():
    """Acceptance C: absent-iss tokens still verify when no issuer is set.

    Sanity check: the iss-required tightening is gated on
    `expected_issuer is not None`. Callers that opt out of issuer
    enforcement see no behaviour change.
    """
    auth = BearerTokenAuth(
        validate_jwt=True,
        jwt_secret=JWT_TEST_SECRET,
        jwt_algorithm=JWT_TEST_ALGO,
        # expected_issuer NOT set — opt-out path
    )

    token = _encode(_make_claims(include_iss=False))

    user_info = auth.authenticate(token)
    assert user_info["user_id"] == "user-625"
    assert user_info["auth_type"] == "jwt"


@pytest.mark.regression
def test_present_iss_validated_against_allowlist():
    """Cross-SDK parity coverage: present-but-wrong iss is also rejected."""
    auth = BearerTokenAuth(
        validate_jwt=True,
        jwt_secret=JWT_TEST_SECRET,
        jwt_algorithm=JWT_TEST_ALGO,
        expected_issuer=JWT_TEST_ISSUER,
    )

    # iss is present but does NOT match the configured allowlist.
    token = _encode(
        _make_claims(include_iss=True, issuer_value="https://attacker.example")
    )

    with pytest.raises(AuthenticationError):
        auth.authenticate(token)


@pytest.mark.regression
def test_matching_iss_accepted_when_issuer_configured():
    """Happy-path sanity: matching iss verifies when issuer allowlist is set."""
    auth = BearerTokenAuth(
        validate_jwt=True,
        jwt_secret=JWT_TEST_SECRET,
        jwt_algorithm=JWT_TEST_ALGO,
        expected_issuer=JWT_TEST_ISSUER,
    )

    token = _encode(_make_claims(include_iss=True))

    user_info = auth.authenticate(token)
    assert user_info["user_id"] == "user-625"
    assert user_info["metadata"]["iss"] == JWT_TEST_ISSUER


# ---------------------------------------------------------------------------
# JWTAuth — passes its `issuer` through as `expected_issuer`
# ---------------------------------------------------------------------------


@pytest.mark.regression
def test_jwtauth_inherits_iss_required_from_issuer_kwarg():
    """JWTAuth always sets an issuer; it MUST therefore enforce iss-required.

    Sibling kwarg-plumbing coverage per `rules/security.md` § Multi-Site
    Kwarg Plumbing: JWTAuth ships with a default ``issuer="mcp-server"``
    so every JWTAuth instance is an issuer-allowlist caller — the
    iss-required behaviour MUST flow through the super().__init__ call.
    """
    auth = JWTAuth(secret=JWT_TEST_SECRET, issuer=JWT_TEST_ISSUER)

    # Forged absent-iss token signed with the right secret.
    token = _encode(_make_claims(include_iss=False))

    with pytest.raises(AuthenticationError):
        auth.authenticate(token)


@pytest.mark.regression
def test_jwtauth_round_trip_token_validates():
    """End-to-end regression: JWTAuth.create_token + authenticate round-trips.

    Belt-and-suspenders: the iss-required tightening must NOT regress the
    canonical create→verify flow on tokens this very provider issues.
    """
    auth = JWTAuth(secret=JWT_TEST_SECRET, issuer=JWT_TEST_ISSUER)

    token = auth.create_token({"user": "alice", "permissions": ["read"]})
    user_info = auth.authenticate(token)

    assert user_info["auth_type"] == "jwt"
    assert user_info["metadata"]["iss"] == JWT_TEST_ISSUER
    # `sub` is not set by create_token; user_id falls back to "user".
    assert user_info["user_id"] in ("alice", "unknown")


# ---------------------------------------------------------------------------
# JWTManager (oauth.py) — sibling site per security.md § Multi-Site Kwarg Plumbing
# ---------------------------------------------------------------------------


@pytest.mark.regression
def test_jwtmanager_verify_access_token_rejects_missing_iss():
    """JWTManager sibling: verify_access_token enforces iss-required."""
    pytest.importorskip(
        "cryptography", reason="oauth path requires [auth-oauth] extras"
    )
    from kailash_mcp.auth.oauth import JWTManager

    mgr = JWTManager(algorithm="HS256", issuer=JWT_TEST_ISSUER)
    # Override key material to use HMAC for this regression test (HS256 path).
    mgr.private_key = JWT_TEST_SECRET  # type: ignore[assignment]
    mgr.public_key = JWT_TEST_SECRET  # type: ignore[assignment]

    claims = _make_claims(include_iss=False)
    claims["token_type"] = "access_token"
    token = jwt.encode(claims, JWT_TEST_SECRET, algorithm="HS256")

    with pytest.raises(AuthenticationError):
        mgr.verify_access_token(token)


@pytest.mark.regression
def test_jwtmanager_verify_access_token_allows_missing_iss_when_issuer_unset():
    """Sibling sanity: opt-out path on JWTManager (issuer=None)."""
    pytest.importorskip(
        "cryptography", reason="oauth path requires [auth-oauth] extras"
    )
    from kailash_mcp.auth.oauth import JWTManager

    mgr = JWTManager(algorithm="HS256", issuer=None)
    mgr.private_key = JWT_TEST_SECRET  # type: ignore[assignment]
    mgr.public_key = JWT_TEST_SECRET  # type: ignore[assignment]

    claims = _make_claims(include_iss=False)
    claims["token_type"] = "access_token"
    token = jwt.encode(claims, JWT_TEST_SECRET, algorithm="HS256")

    payload = mgr.verify_access_token(token)
    assert payload is not None
    assert payload["token_type"] == "access_token"


@pytest.mark.regression
def test_jwtmanager_verify_refresh_token_rejects_missing_iss():
    """JWTManager refresh-token path: iss-required when issuer is configured."""
    pytest.importorskip(
        "cryptography", reason="oauth path requires [auth-oauth] extras"
    )
    from kailash_mcp.auth.oauth import JWTManager

    mgr = JWTManager(algorithm="HS256", issuer=JWT_TEST_ISSUER)
    mgr.private_key = JWT_TEST_SECRET  # type: ignore[assignment]
    mgr.public_key = JWT_TEST_SECRET  # type: ignore[assignment]

    claims = _make_claims(include_iss=False)
    claims["token_type"] = "refresh_token"
    token = jwt.encode(claims, JWT_TEST_SECRET, algorithm="HS256")

    with pytest.raises(AuthenticationError):
        mgr.verify_refresh_token(token)

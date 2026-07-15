# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Regression tests for #1712 - JWT token audience validation (MCP 2025-11-25).

The MCP 2025-11-25 spec requires servers to validate the token audience
FAIL-CLOSED by default: reject BOTH audience-absent AND foreign-audience
tokens. The default ``AuthProvider`` JWT path (``BearerTokenAuth`` /
``JWTAuth``) previously never passed ``audience=`` to ``jwt.decode`` and never
required ``aud``, so PyJWT skipped audience verification entirely — a token
minted for a DIFFERENT resource was accepted.

Behavioral pins (real PyJWT encode/decode, no crypto mocking, per
``rules/testing.md``):

  (a) a valid-audience token is ACCEPTED when ``expected_audience`` is set;
  (b) an audience-ABSENT token is REJECTED when ``expected_audience`` is set
      (missing required ``aud`` claim);
  (c) a FOREIGN-audience token is REJECTED when ``expected_audience`` is set,
      and the rejection message does NOT leak the token's actual ``aud``;
  (d) when ``expected_audience`` is UNSET, behaviour is unchanged (audience
      not validated) AND a spec-compliance WARNING is emitted once.
"""

import logging

import jwt
import pytest

from kailash_mcp.auth.providers import (
    AuthenticationError,
    BearerTokenAuth,
    JWTAuth,
)

SECRET = "test-hs256-secret-for-1712"
ALGO = "HS256"
CANONICAL_AUDIENCE = "https://mcp.example.com"
FOREIGN_AUDIENCE = "https://evil.attacker.example"


def _encode(claims: dict) -> str:
    """Encode a real HS256 JWT with the test secret."""
    return jwt.encode(claims, SECRET, algorithm=ALGO)


# ---------------------------------------------------------------------------
# (a) valid audience token accepted
# ---------------------------------------------------------------------------


@pytest.mark.regression
def test_valid_audience_token_accepted():
    """A token whose `aud` matches expected_audience authenticates."""
    auth = BearerTokenAuth(
        validate_jwt=True,
        jwt_secret=SECRET,
        jwt_algorithm=ALGO,
        expected_audience=CANONICAL_AUDIENCE,
    )
    token = _encode({"sub": "alice", "aud": CANONICAL_AUDIENCE})

    result = auth.authenticate(token)

    assert result["auth_type"] == "jwt"
    assert result["user_id"] == "alice"


@pytest.mark.regression
def test_valid_audience_token_accepted_when_aud_is_list():
    """PyJWT accepts a matching audience inside a list-valued `aud` claim."""
    auth = BearerTokenAuth(
        validate_jwt=True,
        jwt_secret=SECRET,
        jwt_algorithm=ALGO,
        expected_audience=CANONICAL_AUDIENCE,
    )
    token = _encode({"sub": "bob", "aud": [FOREIGN_AUDIENCE, CANONICAL_AUDIENCE]})

    result = auth.authenticate(token)

    assert result["user_id"] == "bob"


# ---------------------------------------------------------------------------
# (b) audience-absent token REJECTED when expected_audience set
# ---------------------------------------------------------------------------


@pytest.mark.regression
def test_audience_absent_token_rejected():
    """A token with NO `aud` claim is rejected when expected_audience is set."""
    auth = BearerTokenAuth(
        validate_jwt=True,
        jwt_secret=SECRET,
        jwt_algorithm=ALGO,
        expected_audience=CANONICAL_AUDIENCE,
    )
    token = _encode({"sub": "alice"})  # no aud

    with pytest.raises(AuthenticationError):
        auth.authenticate(token)


# ---------------------------------------------------------------------------
# (c) foreign-audience token REJECTED (and no aud value leak)
# ---------------------------------------------------------------------------


@pytest.mark.regression
def test_foreign_audience_token_rejected():
    """A token minted for a DIFFERENT resource is rejected."""
    auth = BearerTokenAuth(
        validate_jwt=True,
        jwt_secret=SECRET,
        jwt_algorithm=ALGO,
        expected_audience=CANONICAL_AUDIENCE,
    )
    token = _encode({"sub": "alice", "aud": FOREIGN_AUDIENCE})

    with pytest.raises(AuthenticationError) as excinfo:
        auth.authenticate(token)

    # The token's actual audience value MUST NOT leak into the error message
    # (security.md "no secrets in logs").
    assert FOREIGN_AUDIENCE not in str(excinfo.value)
    assert "audience" in str(excinfo.value).lower()


# ---------------------------------------------------------------------------
# (d) expected_audience unset: FAIL-CLOSED — construction refuses (F4)
# ---------------------------------------------------------------------------


@pytest.mark.regression
def test_validate_jwt_without_audience_raises():
    """A JWT-validating provider with NO expected_audience REFUSES construction.

    Enforcement-surface parity (rules/security.md § Enforcement-Surface Parity):
    ``ResourceServer`` is audience fail-closed, so the ``BearerTokenAuth`` /
    ``JWTAuth`` JWT path MUST be too. The pre-fix behaviour merely WARNED and
    continued with audience validation DISABLED (fail-OPEN) — a token minted
    for a different resource was accepted. The fix raises ``ValueError`` at
    construction, mirroring the ``jwt_secret``-required guard, so there is no
    fail-open default.
    """
    with pytest.raises(ValueError) as excinfo:
        BearerTokenAuth(
            validate_jwt=True,
            jwt_secret=SECRET,
            jwt_algorithm=ALGO,
            # expected_audience deliberately omitted -> fail-closed refusal
        )
    assert "expected_audience" in str(excinfo.value)


@pytest.mark.regression
def test_jwtauth_without_audience_raises():
    """JWTAuth always validates JWTs, so an absent audience also refuses."""
    with pytest.raises(ValueError) as excinfo:
        JWTAuth(secret=SECRET)  # no audience
    assert "expected_audience" in str(excinfo.value)


@pytest.mark.regression
def test_no_warning_when_audience_configured(caplog):
    """With expected_audience set, construction SUCCEEDS and emits no warning."""
    with caplog.at_level(logging.WARNING, logger="kailash_mcp.auth.providers"):
        auth = BearerTokenAuth(
            validate_jwt=True,
            jwt_secret=SECRET,
            jwt_algorithm=ALGO,
            expected_audience=CANONICAL_AUDIENCE,
        )

    assert auth.expected_audience == CANONICAL_AUDIENCE
    warnings = [
        r
        for r in caplog.records
        if r.levelno == logging.WARNING and "expected_audience" in r.getMessage()
    ]
    assert warnings == []


# ---------------------------------------------------------------------------
# JWTAuth end-to-end: mints `aud`, round-trips through its own validation
# ---------------------------------------------------------------------------


@pytest.mark.regression
def test_jwtauth_roundtrip_with_audience():
    """JWTAuth mints the `aud` claim and accepts its own token."""
    auth = JWTAuth(secret=SECRET, audience=CANONICAL_AUDIENCE)
    token = auth.create_token({"user": "alice", "permissions": ["read"]})

    # The minted token carries the audience claim.
    decoded = jwt.decode(token, SECRET, algorithms=[ALGO], audience=CANONICAL_AUDIENCE)
    assert decoded["aud"] == CANONICAL_AUDIENCE

    # And it round-trips through JWTAuth's own fail-closed validation.
    result = auth.authenticate(token)
    assert result["auth_type"] == "jwt"


@pytest.mark.regression
def test_jwtauth_rejects_foreign_audience_token():
    """JWTAuth (audience set) rejects a foreign-audience token."""
    auth = JWTAuth(secret=SECRET, issuer="mcp-server", audience=CANONICAL_AUDIENCE)
    # Mint a token for a different resource but the same issuer/secret.
    foreign = _encode(
        {
            "sub": "alice",
            "iss": "mcp-server",
            "exp": 9_999_999_999,
            "aud": FOREIGN_AUDIENCE,
        }
    )

    with pytest.raises(AuthenticationError):
        auth.authenticate(foreign)

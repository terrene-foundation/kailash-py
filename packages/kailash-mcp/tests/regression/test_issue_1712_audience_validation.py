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
# (d) expected_audience unset: behaviour unchanged + warning emitted
# ---------------------------------------------------------------------------


@pytest.mark.regression
def test_audience_unset_preserves_existing_behaviour(caplog):
    """With no expected_audience, an audience-ABSENT token is still accepted
    (audience not validated — the pre-fix, non-fail-closed behaviour) and a
    spec-compliance WARNING is emitted once at construction.

    An aud-absent token sailing through is exactly the gap the fix closes: the
    MCP 2025-11-25 spec requires rejecting audience-absent tokens, which the
    unconfigured path does not do. (PyJWT already rejects a present-but-
    unexpected `aud` by default, so the residual gap is the absent-aud case.)
    """
    with caplog.at_level(logging.WARNING, logger="kailash_mcp.auth.providers"):
        auth = BearerTokenAuth(
            validate_jwt=True,
            jwt_secret=SECRET,
            jwt_algorithm=ALGO,
            # expected_audience deliberately omitted
        )

    # The warning fired exactly once, at construction.
    warnings = [
        r
        for r in caplog.records
        if r.levelno == logging.WARNING and "expected_audience" in r.getMessage()
    ]
    assert len(warnings) == 1

    # Behaviour is unchanged: an audience-absent token still authenticates
    # because audience is not validated when unconfigured (the residual gap
    # the warning flags and expected_audience closes).
    token = _encode({"sub": "alice"})  # no aud claim
    result = auth.authenticate(token)
    assert result["user_id"] == "alice"


@pytest.mark.regression
def test_no_warning_when_audience_configured(caplog):
    """No spec-compliance warning when expected_audience IS set."""
    with caplog.at_level(logging.WARNING, logger="kailash_mcp.auth.providers"):
        BearerTokenAuth(
            validate_jwt=True,
            jwt_secret=SECRET,
            jwt_algorithm=ALGO,
            expected_audience=CANONICAL_AUDIENCE,
        )

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

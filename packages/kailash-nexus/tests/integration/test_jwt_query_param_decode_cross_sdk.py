"""Tier-2 cross-SDK alignment for kailash-rs#998 / kailash-py#1056.

kailash-rs#998 found its Nexus query-string API-key decoder hand-rolled a
percent-decode with two bugs: (1) invalid-UTF-8 -> returned the still-encoded
string instead of rejecting; (2) no NUL-byte guard. Python Nexus exposes NO
query-string API-key path (header-only; see the companion structural-invariant
regression test). The ONLY server-side query-string credential decode surface
in Python Nexus is JWT *token* extraction for WebSockets
(`JWTConfig.token_query_param`, `nexus/auth/jwt.py:294-298`), which routes
through Starlette's stdlib percent-decode -- NOT a hand-rolled unquote().

These tests exercise that equivalent decode surface against the three
issue-#1056 acceptance scenarios, proving the Rust bug class does not manifest
here: malformed query tokens are rejected (NUL, invalid-UTF-8) and a valid
percent-encoded token round-trips through the decoder (no raw-encoded
fallback).

Tier 2 -- NO MOCKING. Real Nexus app, real JWT middleware, real ASGI flow.
"""

from datetime import datetime, timedelta, timezone

import jwt as pyjwt
import pytest
from fastapi import APIRouter, Depends
from starlette.testclient import TestClient

from nexus import Nexus
from nexus.auth.dependencies import get_current_user
from nexus.auth.jwt import JWTConfig, JWTMiddleware

SECRET = "issue-1056-cross-sdk-secret-key-at-least-32-chars"
QUERY_PARAM = "access_token"


def _make_token(sub="user-1056", secret=SECRET):
    """Create a real HS256 JWT."""
    payload = {
        "sub": sub,
        "email": "user@example.com",
        "exp": int((datetime.now(timezone.utc) + timedelta(minutes=60)).timestamp()),
        "iat": int(datetime.now(timezone.utc).timestamp()),
    }
    return pyjwt.encode(payload, secret, algorithm="HS256")


@pytest.fixture
def query_token_client():
    """Nexus app whose JWT middleware accepts a token via query param."""
    app = Nexus(enable_durability=False)
    app.add_middleware(
        JWTMiddleware,
        config=JWTConfig(secret=SECRET, token_query_param=QUERY_PARAM),
    )

    router = APIRouter()

    @router.get("/whoami")
    def whoami(user=Depends(get_current_user)):
        return {"sub": user.user_id}

    app.include_router(router, prefix="/api")
    assert app.fastapi_app is not None  # always set post-init; narrows type
    return TestClient(app.fastapi_app)


class TestQueryParamDecodeCrossSDK:
    """kailash-rs#998 / #1056 -- the Rust query-string decode bug class."""

    def test_nul_byte_query_token_is_rejected(self, query_token_client):
        """`?access_token=%00x` -> NUL after decode -> auth rejected (401).

        Mirrors Rust bug #2's *post-fix* expected behavior: a NUL-containing
        credential MUST be rejected, never silently accepted/truncated.
        """
        resp = query_token_client.get(f"/api/whoami?{QUERY_PARAM}=%00x")
        assert resp.status_code == 401

    def test_invalid_utf8_query_token_is_rejected_not_raw_fallback(
        self, query_token_client
    ):
        """`?access_token=%FF%FE` -> invalid UTF-8 -> auth rejected (401).

        Mirrors Rust bug #1's absence: the decoder MUST NOT fall back to the
        still-percent-encoded string. `%FF%FE` is invalid UTF-8; Starlette's
        stdlib decode lossy-replaces it -- it never returns the literal
        "%FF%FE", and the result is not a valid JWT -> 401. A non-401 here
        would mean the still-encoded string leaked through as a credential.
        """
        resp = query_token_client.get(f"/api/whoami?{QUERY_PARAM}=%FF%FE")
        assert resp.status_code == 401

    def test_valid_percent_encoded_token_round_trips(self, query_token_client):
        """Fully percent-encoded valid JWT -> decode happens -> auth succeeds.

        Every byte of a valid token is percent-escaped. If the decoder had
        the Rust raw-fallback bug it would pass the still-encoded blob to JWT
        verification -> signature failure -> 401. A 200 proves the percent
        decode genuinely ran (no raw-encoded fallback).
        """
        token = _make_token(sub="user-roundtrip")
        # quote() treats the base64url alphabet (incl. '.', '-', '_') as
        # always-safe, so it would NOT change a JWT. Force every byte to a
        # percent-escape so the decode must genuinely run for auth to pass.
        encoded = "".join(f"%{b:02X}" for b in token.encode("ascii"))
        assert encoded != token  # sanity: encoding actually changed the bytes

        resp = query_token_client.get(f"/api/whoami?{QUERY_PARAM}={encoded}")
        assert resp.status_code == 200
        assert resp.json()["sub"] == "user-roundtrip"

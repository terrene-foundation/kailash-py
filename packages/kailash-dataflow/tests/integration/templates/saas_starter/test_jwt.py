"""
SaaS Starter Template - JWT Authentication (Tier-2 Integration)

Tier-2 rewrite of ``tests/unit/templates/test_saas_starter_jwt.py`` per
GH issue #996 Workstream-B sub-shard B-2a. The original unit file violated
two contracts:

1. Bare top-imports of ``LocalRuntime`` + ``WorkflowBuilder`` (forbidden
   in Tier-1 per ``specs/testing-tiers.md`` § Tier-1 Rule 1).
2. ``unittest.mock`` usages in 7 sites (``Mock``, ``MagicMock``, ``patch``)
   substituting the DataFlow workflow execution path.

The original ``pytestmark.skip`` gate parked the entire 10-test file
because the Tier-1 violation hung the GH-runner py3.11 worker on the
aiosqlite cleanup path. Brief AC#5 (workspaces/issue-979-dataflow-unit
-triage/briefs/00-brief.md:48-50) requires the file move to Tier-2 OR be
gated behind ``importorskip``. This rewrite chooses the Tier-2 path:

* Tests 1-8 (pure-crypto: hashing, token gen, token verify) needed no
  mocks; they ran against real bcrypt + PyJWT all along. The original
  pytestmark.skip parked them only because tests 9-10 in the same file
  pulled in the banned imports. They are translated verbatim, minus the
  module-level skip.
* Tests 9-10 (database-path: ``create_user_record``, ``login_user``) are
  rewritten to exercise the real DataFlow primitives end-to-end against
  a temp file-backed SQLite database. The 7 ``unittest.mock`` sites are
  removed; integration conftest's AST gate (``packages/kailash-dataflow
  /tests/integration/conftest.py``) collects-fails on any reintroduction.

Real-infrastructure conventions follow the sibling
``tests/integration/templates/api_gateway_starter/test_example_app.py``:
file-backed SQLite over ``:memory:`` so DataFlow's migration pool (which
opens multiple short-lived connections) sees a consistent schema, and an
in-fixture ``@db.model`` for User to avoid the saas_starter full-model
register conflicts the sibling fixture documents.

Closes part of #996 (B-2a sub-shard, Workstream-B parallel wave).
"""

from __future__ import annotations

import os
import shutil
import tempfile
from datetime import datetime, timedelta

import jwt
import pytest

from dataflow import DataFlow
from templates.saas_starter.auth.jwt_auth import (
    create_user_record,
    generate_access_token,
    generate_refresh_token,
    hash_password,
    login_user,
    verify_password,
    verify_token,
)

# ----------------------------------------------------------------------
# Fixture — real DataFlow against a temp-file SQLite database.
#
# Pattern mirrors api_gateway_starter/test_example_app.py::db: file-backed
# database (NOT :memory:) so DataFlow's migration + write pools see a
# consistent schema across their short-lived connections. Defines only
# the minimal User schema saas_starter.auth.jwt_auth requires —
# saas_starter.models.register_models registers 5 models with rich
# constraint sets the JWT tests don't exercise.
# ----------------------------------------------------------------------


@pytest.fixture(scope="function")
def db():
    """Real DataFlow with a minimal saas_starter-compatible User schema."""
    tmpdir = tempfile.mkdtemp(prefix="saas_jwt_test_")
    default_url = f"sqlite:///{tmpdir}/test.db"
    database_url = os.getenv("TEST_DATABASE_URL", default_url)
    db_instance = DataFlow(database_url)

    # Schema mirrors saas_starter.auth.jwt_auth expectations:
    # create_user_record() inserts {id, organization_id, email,
    # password_hash, role, status}; find_user_by_email() filters by
    # ``email`` and returns the same row shape.
    @db_instance.model
    class User:
        id: str
        organization_id: str
        email: str
        password_hash: str
        role: str  # owner, admin, member
        status: str  # active, invited, suspended

        __dataflow__ = {
            "indexes": [
                {"name": "idx_user_email", "fields": ["email"], "unique": True},
                {"name": "idx_user_org", "fields": ["organization_id"]},
            ]
        }

    yield db_instance

    # Cleanup: close the DataFlow instance (release the aiosqlite worker
    # thread that the issue #1010 patch makes daemon=True) and remove
    # the temp directory. Errors during teardown are expected when the
    # event loop has already closed.
    try:
        import asyncio

        asyncio.run(db_instance.close_async())
    except Exception:
        pass
    shutil.rmtree(tmpdir, ignore_errors=True)


# ----------------------------------------------------------------------
# Pure-crypto tests (1-8) — never needed mocks. Translated verbatim
# from tests/unit/templates/test_saas_starter_jwt.py, minus the module-
# level skip. All run offline; no DataFlow / DB required.
# ----------------------------------------------------------------------


@pytest.mark.integration
class TestSimplifiedJWTAuth:
    """JWT crypto + database operations exercised against real infra."""

    def test_hash_password(self):
        """Bcrypt hash format + per-call salt randomness."""
        password = "SecurePassword123!"
        hashed = hash_password(password)

        assert isinstance(hashed, str), "Hash should be string"
        assert hashed.startswith("$2b$"), "Should use bcrypt format"
        assert len(hashed) > 50, "Bcrypt hash should be long"
        assert hashed != password, "Hash should not equal plain text"

        hashed2 = hash_password(password)
        assert hashed != hashed2, "Different salt should produce different hash"

    def test_verify_password_correct(self):
        """verify_password returns True for the original password."""
        password = "TestPassword456!"
        hashed = hash_password(password)

        result = verify_password(password, hashed)
        assert result is True, "Correct password should verify"

    def test_verify_password_incorrect(self):
        """verify_password returns False for a wrong password."""
        password = "CorrectPassword"
        wrong_password = "WrongPassword"
        hashed = hash_password(password)

        result = verify_password(wrong_password, hashed)
        assert result is False, "Wrong password should not verify"

    def test_generate_access_token(self):
        """Access token shape + claims (user_id, org_id, email, exp/iat)."""
        user_id = "user_123"
        org_id = "org_456"
        email = "test@example.com"

        result = generate_access_token(user_id, org_id, email)

        assert "access_token" in result, "Should contain access_token"
        assert "expires_in" in result, "Should contain expires_in"
        assert result["expires_in"] == 3600, "Should expire in 1 hour"

        token = result["access_token"]
        assert isinstance(token, str), "Token should be string"
        assert len(token) > 50, "JWT should be long"

        decoded = jwt.decode(token, options={"verify_signature": False})
        assert decoded["user_id"] == user_id, "Should contain user_id"
        assert decoded["org_id"] == org_id, "Should contain org_id"
        assert decoded["email"] == email, "Should contain email"
        assert decoded["type"] == "access", "Should be access token"
        assert "exp" in decoded, "Should have expiration"
        assert "iat" in decoded, "Should have issued at"

    def test_generate_refresh_token(self):
        """Refresh token shape + 7-day expiry."""
        user_id = "user_789"

        result = generate_refresh_token(user_id)

        assert "refresh_token" in result, "Should contain refresh_token"
        assert "expires_in" in result, "Should contain expires_in"
        assert result["expires_in"] == 604800, "Should expire in 7 days"

        token = result["refresh_token"]
        assert isinstance(token, str), "Token should be string"

        decoded = jwt.decode(token, options={"verify_signature": False})
        assert decoded["user_id"] == user_id, "Should contain user_id"
        assert decoded["type"] == "refresh", "Should be refresh token"
        assert "exp" in decoded, "Should have expiration"

    def test_verify_token_valid(self):
        """verify_token round-trips claims for a freshly-issued token."""
        user_id = "user_valid"
        org_id = "org_valid"
        email = "valid@example.com"

        token_data = generate_access_token(user_id, org_id, email)
        token = token_data["access_token"]

        result = verify_token(token)

        assert result["valid"] is True, "Token should be valid"
        assert result["user_id"] == user_id, "Should extract user_id"
        assert result["org_id"] == org_id, "Should extract org_id"
        assert "exp" in result, "Should contain expiration"

    def test_verify_token_expired(self):
        """verify_token reports TOKEN_EXPIRED for a backdated token.

        Uses a real PyJWT-encoded token whose exp is 2h in the past — no
        time-freezing library needed. The dedicated secret is required
        because the issued token wasn't signed with the module's default.
        """
        payload = {
            "user_id": "user_expired",
            "org_id": "org_expired",
            "exp": datetime.utcnow() - timedelta(hours=2),  # Expired 2h ago
            "iat": datetime.utcnow() - timedelta(hours=3),  # Issued 3h ago
            "type": "access",
        }
        expired_token = jwt.encode(payload, "test-secret-key", algorithm="HS256")

        result = verify_token(expired_token, secret="test-secret-key")

        assert result["valid"] is False, "Expired token should be invalid"
        assert "error" in result, "Should contain error message"
        assert "error_code" in result, "Should contain error code"
        assert result["error_code"] == "TOKEN_EXPIRED", "Should indicate expiration"
        assert "expired" in result["error"].lower(), "Error should mention expiration"

    def test_verify_token_invalid(self):
        """verify_token reports INVALID_TOKEN for a malformed string."""
        invalid_token = "this.is.not.a.valid.jwt.token"

        result = verify_token(invalid_token)

        assert result["valid"] is False, "Invalid token should be invalid"
        assert "error" in result, "Should contain error message"
        assert "error_code" in result, "Should contain error code"
        assert result["error_code"] == "INVALID_TOKEN", "Should indicate invalid token"

    # ------------------------------------------------------------------
    # Database-path tests (9-10) — rewritten Tier-2.
    #
    # Originals mocked WorkflowBuilder + LocalRuntime via patch.object()
    # to assert create_user_record() / login_user() returned the
    # mock-shaped result. Tier-2 exercises the real DataFlow execution
    # path: write a row, read it back, assert persistence. State-
    # persistence verification per rules/testing.md.
    # ------------------------------------------------------------------

    def test_create_user_record_persists_to_database(self, db):
        """create_user_record() writes a real row via DataFlow nodes."""
        user_data = {
            "id": "user_123",
            "organization_id": "org_456",
            "email": "testuser@example.com",
            "password_hash": hash_password("password123"),
            "role": "member",
            "status": "active",
        }

        result = create_user_record(db, user_data)

        # Return value contract — saas_starter.auth.jwt_auth.create_user_record
        # delegates to UserCreateNode and returns the created row dict.
        assert result is not None, "Should return user record"
        assert result["id"] == user_data["id"], "Should have correct ID"
        assert result["email"] == user_data["email"], "Should have correct email"
        assert (
            result["organization_id"] == "org_456"
        ), "Should have correct organization"

        # State-persistence read-back — the row must actually be in the DB,
        # not just echoed by the workflow runtime. Uses the same
        # find_user_by_email() helper login_user() depends on, so the
        # downstream login test below proves the same write path is
        # discoverable.
        from templates.saas_starter.auth.jwt_auth import find_user_by_email

        persisted = find_user_by_email(db, user_data["email"])
        assert persisted is not None, "Row must be persisted, not just returned"
        assert persisted["id"] == user_data["id"], "Persisted row id mismatch"
        assert persisted["email"] == user_data["email"], "Persisted row email mismatch"

    def test_login_flow_against_real_database(self, db):
        """login_user() walks find → verify → token-issue against real DB.

        Originally mocked find_user_by_email() to return a synthetic dict.
        Tier-2 plants the user via create_user_record() (the same SDK
        primitive a real signup uses) and verifies login_user() resolves
        it through the production query path.
        """
        email = "logintest@example.com"
        password = "TestPassword123!"
        password_hash = hash_password(password)

        user_data = {
            "id": "user_login_test",
            "organization_id": "org_456",
            "email": email,
            "password_hash": password_hash,
            "role": "member",
            "status": "active",
        }

        # Plant the user via the SDK's own create path — no mocks.
        created = create_user_record(db, user_data)
        assert created is not None, "create_user_record must succeed before login"

        # Login with correct credentials hits the real DB lookup +
        # bcrypt verify + JWT issue. Asserts both the success shape and
        # that the issued tokens are real (decodable).
        login_result = login_user(db, email, password)

        assert login_result["success"] is True, "Login should succeed"
        assert "user" in login_result, "Should return user"
        assert "access_token" in login_result, "Should return access token"
        assert "refresh_token" in login_result, "Should return refresh token"
        assert login_result["user"]["email"] == email, "Should return correct user"

        # The issued access_token must be a valid JWT (round-trip via
        # verify_token confirms the issuance path actually called PyJWT,
        # not a mocked stub).
        verified = verify_token(login_result["access_token"])
        assert verified["valid"] is True, "Issued access token must verify"
        assert (
            verified["user_id"] == user_data["id"]
        ), "Issued token's user_id must match created row"

        # Wrong password must fall through to INVALID_CREDENTIALS — same
        # error_code the original mock-based test asserted, now via the
        # real verify_password path.
        wrong_login = login_user(db, email, "WrongPassword")
        assert wrong_login["success"] is False, "Wrong password should fail"
        assert (
            wrong_login["error_code"] == "INVALID_CREDENTIALS"
        ), "Should indicate invalid credentials"

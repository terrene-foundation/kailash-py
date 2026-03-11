"""
SaaS Starter Template - JWT Authentication Tests

Test-first development (TDD) for simplified JWT authentication.

Tests (10 total):
1. test_hash_password - Direct password hashing with bcrypt
2. test_verify_password_correct - Password verification success
3. test_verify_password_incorrect - Password verification failure
4. test_generate_access_token - Access token generation
5. test_generate_refresh_token - Refresh token generation
6. test_verify_token_valid - Token verification success
7. test_verify_token_expired - Expired token handling
8. test_verify_token_invalid - Invalid token handling
9. test_create_user_record - Database operation for user creation
10. test_login_flow - Complete login flow integration

CRITICAL: These tests are written BEFORE implementation (RED phase).
Tests define the API contract and expected behavior for SIMPLIFIED auth functions.
"""

import os

# Add templates directory to Python path for imports
import sys
import time
from datetime import datetime, timedelta

import pytest

TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "../../../templates")
if TEMPLATES_DIR not in sys.path:
    sys.path.insert(0, TEMPLATES_DIR)


@pytest.mark.unit
class TestSimplifiedJWTAuth:
    """
    Test simplified JWT authentication functions (no complex workflows).

    Tests 1-8: Direct function tests (fast, no database)
    Tests 9-10: Database operation tests (mocked for speed)

    Real database integration tests are in tests/integration/templates/
    """

    def test_hash_password(self):
        """
        Test direct password hashing with bcrypt.

        Expected Behavior:
        - Input: plain text password
        - Output: bcrypt hash string starting with $2b$
        - Hash should be different each time (due to salt)

        RED Phase: This test will fail because hash_password() doesn't exist yet.
        """
        from saas_starter.auth.jwt_auth import hash_password

        password = "SecurePassword123!"
        hashed = hash_password(password)

        # Verify bcrypt hash format
        assert isinstance(hashed, str), "Hash should be string"
        assert hashed.startswith("$2b$"), "Should use bcrypt format"
        assert len(hashed) > 50, "Bcrypt hash should be long"
        assert hashed != password, "Hash should not equal plain text"

        # Verify salt randomness (same password hashed twice gives different results)
        hashed2 = hash_password(password)
        assert hashed != hashed2, "Different salt should produce different hash"

    def test_verify_password_correct(self):
        """
        Test password verification with correct password.

        Expected Behavior:
        - Input: plain password + correct hash
        - Output: True

        RED Phase: This test will fail because verify_password() doesn't exist yet.
        """
        from saas_starter.auth.jwt_auth import hash_password, verify_password

        password = "TestPassword456!"
        hashed = hash_password(password)

        # Verify correct password
        result = verify_password(password, hashed)
        assert result is True, "Correct password should verify"

    def test_verify_password_incorrect(self):
        """
        Test password verification with incorrect password.

        Expected Behavior:
        - Input: plain password + wrong hash
        - Output: False

        RED Phase: This test will fail because verify_password() doesn't exist yet.
        """
        from saas_starter.auth.jwt_auth import hash_password, verify_password

        password = "CorrectPassword"
        wrong_password = "WrongPassword"
        hashed = hash_password(password)

        # Verify wrong password
        result = verify_password(wrong_password, hashed)
        assert result is False, "Wrong password should not verify"

    def test_generate_access_token(self):
        """
        Test JWT access token generation.

        Expected Behavior:
        - Input: user_id, org_id, email
        - Output: dict with access_token and expires_in
        - Token should contain correct claims
        - Token should expire in 1 hour (3600 seconds)

        RED Phase: This test will fail because generate_access_token() doesn't exist yet.
        """
        import jwt
        from saas_starter.auth.jwt_auth import generate_access_token

        user_id = "user_123"
        org_id = "org_456"
        email = "test@example.com"

        result = generate_access_token(user_id, org_id, email)

        # Verify response structure
        assert "access_token" in result, "Should contain access_token"
        assert "expires_in" in result, "Should contain expires_in"
        assert result["expires_in"] == 3600, "Should expire in 1 hour"

        # Verify token format
        token = result["access_token"]
        assert isinstance(token, str), "Token should be string"
        assert len(token) > 50, "JWT should be long"

        # Verify token claims (without verification for test)
        decoded = jwt.decode(token, options={"verify_signature": False})
        assert decoded["user_id"] == user_id, "Should contain user_id"
        assert decoded["org_id"] == org_id, "Should contain org_id"
        assert decoded["email"] == email, "Should contain email"
        assert decoded["type"] == "access", "Should be access token"
        assert "exp" in decoded, "Should have expiration"
        assert "iat" in decoded, "Should have issued at"

    def test_generate_refresh_token(self):
        """
        Test JWT refresh token generation.

        Expected Behavior:
        - Input: user_id
        - Output: dict with refresh_token and expires_in
        - Token should contain correct claims
        - Token should expire in 7 days (604800 seconds)

        RED Phase: This test will fail because generate_refresh_token() doesn't exist yet.
        """
        import jwt
        from saas_starter.auth.jwt_auth import generate_refresh_token

        user_id = "user_789"

        result = generate_refresh_token(user_id)

        # Verify response structure
        assert "refresh_token" in result, "Should contain refresh_token"
        assert "expires_in" in result, "Should contain expires_in"
        assert result["expires_in"] == 604800, "Should expire in 7 days"

        # Verify token format
        token = result["refresh_token"]
        assert isinstance(token, str), "Token should be string"

        # Verify token claims
        decoded = jwt.decode(token, options={"verify_signature": False})
        assert decoded["user_id"] == user_id, "Should contain user_id"
        assert decoded["type"] == "refresh", "Should be refresh token"
        assert "exp" in decoded, "Should have expiration"

    def test_verify_token_valid(self):
        """
        Test JWT token verification with valid token.

        Expected Behavior:
        - Input: valid access token
        - Output: dict with valid=True and claims

        RED Phase: This test will fail because verify_token() doesn't exist yet.
        """
        from saas_starter.auth.jwt_auth import generate_access_token, verify_token

        user_id = "user_valid"
        org_id = "org_valid"
        email = "valid@example.com"

        # Generate token
        token_data = generate_access_token(user_id, org_id, email)
        token = token_data["access_token"]

        # Verify token
        result = verify_token(token)

        # Check verification result
        assert result["valid"] is True, "Token should be valid"
        assert result["user_id"] == user_id, "Should extract user_id"
        assert result["org_id"] == org_id, "Should extract org_id"
        assert "exp" in result, "Should contain expiration"

    def test_verify_token_expired(self):
        """
        Test JWT token verification with expired token.

        Expected Behavior:
        - Input: expired token
        - Output: dict with valid=False, error, and error_code

        RED Phase: This test will fail because verify_token() doesn't exist yet.
        """
        from datetime import datetime, timedelta

        import jwt
        from saas_starter.auth.jwt_auth import verify_token

        # Create expired token manually (using utcnow and expired by 2 hours to avoid clock skew)
        payload = {
            "user_id": "user_expired",
            "org_id": "org_expired",
            "exp": datetime.utcnow() - timedelta(hours=2),  # Expired 2 hours ago
            "iat": datetime.utcnow() - timedelta(hours=3),  # Issued 3 hours ago
            "type": "access",
        }
        expired_token = jwt.encode(payload, "test-secret-key", algorithm="HS256")

        # Verify expired token
        result = verify_token(expired_token, secret="test-secret-key")

        # Check verification result
        assert result["valid"] is False, "Expired token should be invalid"
        assert "error" in result, "Should contain error message"
        assert "error_code" in result, "Should contain error code"
        assert result["error_code"] == "TOKEN_EXPIRED", "Should indicate expiration"
        assert "expired" in result["error"].lower(), "Error should mention expiration"

    def test_verify_token_invalid(self):
        """
        Test JWT token verification with invalid token.

        Expected Behavior:
        - Input: malformed token
        - Output: dict with valid=False, error, and error_code

        RED Phase: This test will fail because verify_token() doesn't exist yet.
        """
        from saas_starter.auth.jwt_auth import verify_token

        invalid_token = "this.is.not.a.valid.jwt.token"

        # Verify invalid token
        result = verify_token(invalid_token)

        # Check verification result
        assert result["valid"] is False, "Invalid token should be invalid"
        assert "error" in result, "Should contain error message"
        assert "error_code" in result, "Should contain error code"
        assert result["error_code"] == "INVALID_TOKEN", "Should indicate invalid token"

    def test_create_user_record(self, monkeypatch):
        """
        Test database operation for user creation using DataFlow nodes.

        Expected Behavior:
        - Input: user data dict
        - Output: created user record from database
        - Uses UserCreateNode (DataFlow generated)

        Note: This test mocks the DataFlow workflow execution for speed.
        Integration tests verify actual database operations.
        """
        from unittest.mock import MagicMock, patch

        from saas_starter.auth.jwt_auth import create_user_record, hash_password

        mock_db = MagicMock()

        user_data = {
            "id": "user_123",
            "organization_id": "org_456",
            "email": "testuser@example.com",
            "password_hash": hash_password("password123"),
            "role": "member",
            "status": "active",
        }

        # Mock the entire workflow execution
        mock_workflow = MagicMock()
        mock_workflow.build.return_value = MagicMock()  # Mock built workflow
        mock_runtime = MagicMock()
        mock_runtime.execute.return_value = ({"create_user": user_data}, "run_id_123")

        # Patch both WorkflowBuilder and LocalRuntime
        import saas_starter.auth.jwt_auth

        with (
            patch.object(
                saas_starter.auth.jwt_auth,
                "WorkflowBuilder",
                return_value=mock_workflow,
            ),
            patch.object(
                saas_starter.auth.jwt_auth, "LocalRuntime", return_value=mock_runtime
            ),
        ):
            result = create_user_record(mock_db, user_data)

            # Verify user created
            assert result is not None, "Should return user record"
            assert result["id"] == user_data["id"], "Should have correct ID"
            assert result["email"] == user_data["email"], "Should have correct email"
            assert result["organization_id"] == "org_456", "Should have correct org"

    def test_login_flow(self, monkeypatch):
        """
        Test complete login flow with simplified functions.

        Expected Behavior:
        1. Find user by email
        2. Verify password hash
        3. Generate tokens
        4. Return success response

        Note: This test mocks the DataFlow workflow execution for speed.
        Integration tests verify actual database operations.
        """
        from unittest.mock import MagicMock

        from saas_starter.auth.jwt_auth import hash_password, login_user

        # Mock database and runtime
        mock_db = MagicMock()

        email = "logintest@example.com"
        password = "TestPassword123!"
        password_hash = hash_password(password)

        user_data = {
            "id": "user_123",
            "organization_id": "org_456",
            "email": email,
            "password_hash": password_hash,
            "role": "member",
            "status": "active",
        }

        # Mock find_user_by_email to return user
        import saas_starter.auth.jwt_auth

        original_find = saas_starter.auth.jwt_auth.find_user_by_email

        def mock_find_user(db, search_email):
            if search_email == email:
                return user_data
            return None

        saas_starter.auth.jwt_auth.find_user_by_email = mock_find_user

        try:
            # Test login with correct password
            login_result = login_user(mock_db, email, password)

            # Verify login success
            assert login_result["success"] is True, "Login should succeed"
            assert "user" in login_result, "Should return user"
            assert "access_token" in login_result, "Should return access token"
            assert "refresh_token" in login_result, "Should return refresh token"
            assert login_result["user"]["email"] == email, "Should return correct user"

            # Verify wrong password fails
            wrong_login = login_user(mock_db, email, "WrongPassword")
            assert wrong_login["success"] is False, "Wrong password should fail"
            assert (
                wrong_login["error_code"] == "INVALID_CREDENTIALS"
            ), "Should indicate invalid credentials"
        finally:
            # Restore original function
            saas_starter.auth.jwt_auth.find_user_by_email = original_find

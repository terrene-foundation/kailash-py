"""Unit tests for integrated security policy enforcement."""

import bcrypt
import pytest


class SimpleUserValidator:
    """Simple user validator for testing with bcrypt."""

    def __init__(self):
        # Hash passwords during initialization
        self.users = {
            "test_user": bcrypt.hashpw(
                "secure_password".encode("utf-8"), bcrypt.gensalt()
            ),
            "editor_user": bcrypt.hashpw(
                "secure_password".encode("utf-8"), bcrypt.gensalt()
            ),
        }

    def validate_credentials(self, username: str, password: str) -> bool:
        """Validate credentials using bcrypt."""
        if username not in self.users:
            return False
        return bcrypt.checkpw(password.encode("utf-8"), self.users[username])


@pytest.fixture
def test_user_validator():
    """Fixture for test user validator."""
    return SimpleUserValidator()


class TestSecurityPolicy:
    """Test suite for integrated security policy enforcement."""

    def test_security_policy_enforcement(self, test_user_validator):
        """Test complete security policy enforcement (auth + authz)."""
        from kaizen.security.authentication import AuthenticationProvider
        from kaizen.security.authorization import AuthorizationProvider
        from kaizen.security.policy import SecurityPolicy

        # Arrange - Create auth provider with user validator
        auth_provider = AuthenticationProvider(
            secret_key="test_secret_key_32_characters_min",
            user_validator=test_user_validator,
        )

        authz_provider = AuthorizationProvider()

        # Define role-to-permissions mapping
        role_permissions = {
            "admin": ["read", "write", "delete"],
            "editor": ["read", "write"],
            "viewer": ["read"],
        }

        # Create security policy
        policy = SecurityPolicy(auth_provider, authz_provider, role_permissions)

        # Generate valid token for user with 'editor' role
        credentials = {"username": "editor_user", "password": "secure_password"}
        token = auth_provider.authenticate(credentials)

        # Act - Check if token holder can perform 'write' action
        result = policy.enforce(
            token, required_permission="write", user_roles=["editor"]
        )

        # Assert
        assert result is True  # Editor should be able to write

        # Negative test: editor cannot delete
        delete_result = policy.enforce(
            token, required_permission="delete", user_roles=["editor"]
        )
        assert delete_result is False  # Editor cannot delete

    def test_security_policy_invalid_token(self, test_user_validator):
        """Test that invalid tokens are rejected by security policy."""
        from kaizen.security.authentication import AuthenticationProvider
        from kaizen.security.authorization import AuthorizationProvider
        from kaizen.security.policy import SecurityPolicy

        # Arrange
        auth_provider = AuthenticationProvider(
            secret_key="test_secret_key_32_characters_min",
            user_validator=test_user_validator,
        )
        authz_provider = AuthorizationProvider()

        role_permissions = {"admin": ["read", "write", "delete"]}

        policy = SecurityPolicy(auth_provider, authz_provider, role_permissions)

        # Act - Use invalid token
        invalid_token = "invalid.token.here"
        result = policy.enforce(
            invalid_token, required_permission="read", user_roles=["admin"]
        )

        # Assert
        assert result is False  # Invalid token should be rejected

    def test_security_policy_expired_token(self, test_user_validator):
        """Test that expired tokens are rejected by security policy."""
        from datetime import datetime, timedelta, timezone

        import jwt
        from kaizen.security.authentication import AuthenticationProvider
        from kaizen.security.authorization import AuthorizationProvider
        from kaizen.security.policy import SecurityPolicy

        # Arrange
        auth_provider = AuthenticationProvider(
            secret_key="test_secret_key_32_characters_min",
            user_validator=test_user_validator,
        )
        authz_provider = AuthorizationProvider()

        role_permissions = {"admin": ["read", "write", "delete"]}

        policy = SecurityPolicy(auth_provider, authz_provider, role_permissions)

        # Manually create an expired token (expired 1 hour ago)
        expired_payload = {
            "username": "test_user",
            "exp": datetime.now(timezone.utc)
            - timedelta(hours=1),  # Expired 1 hour ago
            "iat": datetime.now(timezone.utc)
            - timedelta(hours=2),  # Issued 2 hours ago
        }
        expired_token = jwt.encode(
            expired_payload, "test_secret_key_32_characters_min", algorithm="HS256"
        )

        # Act - Try to use expired token
        result = policy.enforce(
            expired_token, required_permission="read", user_roles=["admin"]
        )

        # Assert
        assert result is False  # Expired token should be rejected

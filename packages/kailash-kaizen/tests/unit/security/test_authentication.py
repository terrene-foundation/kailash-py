"""
Unit tests for authentication providers - Tier 1 (Fast, isolated, <1s)

Tests in this file:
- Test 1.1: JWT authentication with valid credentials
- Test 1.2: JWT authentication with invalid credentials (reject)
- Test 1.3: Authentication requires user_validator (no hardcoded users)
- Test 1.4: Authentication with custom validator using password hashing
- Test 1.5: Authentication validator interface validation
- Test 1.6: Secret key minimum length enforcement

NO external dependencies (databases, APIs, etc.)
Mocking allowed for external services.
"""

import bcrypt
import pytest


class SimpleUserValidator:
    """Simple user validator for testing (uses bcrypt)."""

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
def simple_user_validator():
    """Simple user validator for testing."""
    return SimpleUserValidator()


class TestAuthenticationProvider:
    """Unit tests for AuthenticationProvider - Tests 1.1 through 1.6."""

    def test_authentication_requires_user_validator(self):
        """Test 1.3: AuthenticationProvider requires user_validator (no hardcoded users)."""
        from kaizen.security.authentication import AuthenticationProvider

        # Should raise error if no user_validator provided
        with pytest.raises(ValueError, match="user_validator is required"):
            AuthenticationProvider(secret_key="test_secret_key_32_characters_min")

    def test_authentication_with_custom_validator(self, simple_user_validator):
        """Test 1.4: Authentication with custom validator using password hashing."""
        from kaizen.security.authentication import (
            AuthenticationError,
            AuthenticationProvider,
        )

        # Create provider with custom validator
        provider = AuthenticationProvider(
            secret_key="test_secret_key_32_characters_min",
            user_validator=simple_user_validator,
        )

        # Valid credentials should work
        credentials = {"username": "test_user", "password": "secure_password"}
        token = provider.authenticate(credentials)
        assert token is not None
        assert isinstance(token, str)
        assert len(token) > 0

        # Verify token contains correct username
        decoded = provider.verify_token(token)
        assert decoded["username"] == "test_user"

        # Invalid password should fail
        invalid_credentials = {"username": "test_user", "password": "wrong_password"}
        with pytest.raises(AuthenticationError, match="Invalid credentials"):
            provider.authenticate(invalid_credentials)

    def test_authentication_validator_interface(self):
        """Test 1.5: user_validator must have validate_credentials method."""
        from kaizen.security.authentication import AuthenticationProvider

        class InvalidValidator:
            pass  # Missing validate_credentials method

        with pytest.raises(
            ValueError, match="user_validator must have validate_credentials method"
        ):
            AuthenticationProvider(
                secret_key="test_secret_key_32_characters_min",
                user_validator=InvalidValidator(),
            )

    def test_secret_key_minimum_length(self, simple_user_validator):
        """Test 1.6: Secret key must be at least 32 characters."""
        from kaizen.security.authentication import AuthenticationProvider

        # Too short secret key should fail
        with pytest.raises(
            ValueError, match="Secret key must be at least 32 characters"
        ):
            AuthenticationProvider(
                secret_key="short_key", user_validator=simple_user_validator
            )

        # 32 character secret key should work
        provider = AuthenticationProvider(
            secret_key="test_secret_key_32_characters_min",
            user_validator=simple_user_validator,
        )
        assert provider is not None

    def test_authenticate_valid_credentials(self, simple_user_validator):
        """Test 1.1: Authentication with valid credentials succeeds."""
        from kaizen.security.authentication import AuthenticationProvider

        # Arrange
        auth_provider = AuthenticationProvider(
            secret_key="test_secret_key_32_characters_min",
            user_validator=simple_user_validator,
        )
        credentials = {"username": "test_user", "password": "secure_password"}

        # Act
        token = auth_provider.authenticate(credentials)

        # Assert
        assert token is not None
        assert isinstance(token, str)
        assert len(token) > 0

        # Verify token is valid JWT
        decoded = auth_provider.verify_token(token)
        assert decoded["username"] == "test_user"

    def test_authenticate_invalid_credentials(self, simple_user_validator):
        """Test 1.2: Authentication with invalid credentials fails appropriately."""
        from kaizen.security.authentication import (
            AuthenticationError,
            AuthenticationProvider,
        )

        # Arrange
        auth_provider = AuthenticationProvider(
            secret_key="test_secret_key_32_characters_min",
            user_validator=simple_user_validator,
        )
        invalid_credentials = {"username": "test_user", "password": "wrong_password"}

        # Act & Assert
        with pytest.raises(AuthenticationError) as exc_info:
            auth_provider.authenticate(invalid_credentials)

        assert "Invalid credentials" in str(exc_info.value)

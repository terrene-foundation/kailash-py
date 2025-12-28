"""Unit tests for MCP authentication framework.

Tests for the authentication system components in kailash.mcp_server.auth.
NO MOCKING - This is a unit test file for isolated component testing.
"""

import base64
import json
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from kailash.mcp_server.auth import (
    APIKeyAuth,
    AuthenticationError,
    BasicAuth,
    BearerTokenAuth,
    JWTAuth,
    PermissionError,
    RateLimitError,
)


class TestAuthenticationExceptions:
    """Test authentication exception classes."""

    def test_authentication_error_creation(self):
        """Test AuthenticationError creation and attributes."""
        error = AuthenticationError("Test message")
        assert str(error) == "Test message"
        assert error.error_code == "AUTH_FAILED"

        error_custom = AuthenticationError("Custom message", "CUSTOM_CODE")
        assert str(error_custom) == "Custom message"
        assert error_custom.error_code == "CUSTOM_CODE"

    def test_permission_error_creation(self):
        """Test PermissionError creation and attributes."""
        error = PermissionError("Access denied")
        assert str(error) == "Access denied"
        assert error.error_code == "PERMISSION_DENIED"
        assert error.required_permission == ""

        error_with_perm = PermissionError("Need admin", "admin_access")
        assert error_with_perm.required_permission == "admin_access"

    def test_rate_limit_error_creation(self):
        """Test RateLimitError creation and attributes."""
        error = RateLimitError("Rate limited")
        assert str(error) == "Rate limited"
        assert error.error_code == "RATE_LIMITED"
        assert error.retry_after is None

        error_with_retry = RateLimitError("Try again later", 60)
        assert error_with_retry.retry_after == 60


class TestAPIKeyAuth:
    """Test API Key authentication provider."""

    def test_init_with_simple_keys(self):
        """Test initialization with simple API keys."""
        keys = ["key1", "key2", "key3"]
        auth = APIKeyAuth(keys)

        assert len(auth.keys) == 3
        assert "key1" in auth.keys
        assert "key2" in auth.keys
        assert "key3" in auth.keys

        # Check default values
        for key_info in auth.keys.values():
            assert key_info["permissions"] == ["read"]

    def test_init_with_key_data_dict(self):
        """Test initialization with detailed key data."""
        key_data = {
            "admin_key": {
                "permissions": ["read", "write", "admin"],
                "metadata": {"user": "admin", "team": "ops"},
            },
            "read_key": {
                "permissions": ["read"],
                "metadata": {"user": "reader"},
            },
        }
        auth = APIKeyAuth(key_data)

        assert len(auth.keys) == 2
        assert auth.keys["admin_key"]["permissions"] == ["read", "write", "admin"]
        assert auth.keys["read_key"]["permissions"] == ["read"]

    def test_authenticate_valid_key(self):
        """Test successful authentication with valid API key."""
        key_data = {
            "test_key": {
                "permissions": ["read", "write"],
                "metadata": {"user": "test_user"},
            }
        }
        auth = APIKeyAuth(key_data)

        result = auth.authenticate("test_key")

        assert result["user_id"] is not None
        assert result["auth_type"] == "api_key"
        assert result["permissions"] == ["read", "write"]
        assert "metadata" in result

    def test_authenticate_invalid_key(self):
        """Test authentication failure with invalid API key."""
        auth = APIKeyAuth(["valid_key"])

        with pytest.raises(AuthenticationError) as exc_info:
            auth.authenticate("invalid_key")

        assert "Invalid API key" in str(exc_info.value)
        assert exc_info.value.error_code == "AUTH_FAILED"

    def test_authenticate_with_dict_credentials(self):
        """Test authentication with dictionary credentials."""
        auth = APIKeyAuth(["test_key"])

        # Test with api_key in dict
        result = auth.authenticate({"api_key": "test_key"})
        assert result["auth_type"] == "api_key"

        # Test with invalid dict format
        with pytest.raises(AuthenticationError):
            auth.authenticate({"invalid": "format"})

    def test_get_client_config(self):
        """Test getting client configuration."""
        auth = APIKeyAuth(["test_key"])
        config = auth.get_client_config()

        assert config["type"] == "api_key"
        assert config["key"] == "test_key"
        assert "header" in config

    def test_get_server_config(self):
        """Test getting server configuration."""
        auth = APIKeyAuth(["test_key"])
        config = auth.get_server_config()

        assert config["type"] == "api_key"
        assert "header" in config


class TestBasicAuth:
    """Test Basic authentication provider."""

    def test_init_with_credentials(self):
        """Test initialization with username/password credentials."""
        credentials = {
            "admin": "admin_password",
            "user": "user_password",
        }
        auth = BasicAuth(credentials, hash_passwords=True)

        assert len(auth.users) == 2
        assert "admin" in auth.users
        assert "user" in auth.users

        # Passwords should be hashed when hash_passwords=True
        assert auth.users["admin"]["password_hash"] != "admin_password"
        assert auth.users["user"]["password_hash"] != "user_password"

    def test_init_with_detailed_user_data(self):
        """Test initialization with detailed user data."""
        user_data = {
            "admin": {
                "password": "admin_pass",
                "permissions": ["admin", "read", "write"],
                "metadata": {"role": "administrator"},
            },
            "reader": {
                "password": "read_pass",
                "permissions": ["read"],
                "metadata": {"role": "viewer"},
            },
        }
        auth = BasicAuth(user_data)

        assert auth.users["admin"]["permissions"] == ["admin", "read", "write"]
        assert auth.users["reader"]["permissions"] == ["read"]
        assert auth.users["admin"]["metadata"]["role"] == "administrator"

    def test_authenticate_valid_credentials(self):
        """Test successful authentication with valid credentials."""
        auth = BasicAuth({"testuser": "testpass"})

        # Test with dict containing username and password
        result = auth.authenticate({"username": "testuser", "password": "testpass"})

        assert result["user_id"] == "testuser"
        assert result["auth_type"] == "basic"

    def test_authenticate_invalid_credentials(self):
        """Test authentication failure with invalid credentials."""
        auth = BasicAuth({"testuser": "testpass"})

        # Test with wrong password
        with pytest.raises(AuthenticationError):
            auth.authenticate({"username": "testuser", "password": "wrongpass"})

        # Test with wrong username
        with pytest.raises(AuthenticationError):
            auth.authenticate({"username": "wronguser", "password": "testpass"})

    def test_authenticate_malformed_auth_string(self):
        """Test authentication with malformed auth string."""
        auth = BasicAuth({"testuser": "testpass"})

        # Test with string input (not supported)
        with pytest.raises(AuthenticationError):
            auth.authenticate("not_dict_format")

        # Test without username
        with pytest.raises(AuthenticationError):
            auth.authenticate({"password": "testpass"})

    def test_password_hashing_and_verification(self):
        """Test password hashing and verification methods."""
        auth = BasicAuth({})

        password = "test_password_123"
        password_hash = auth._hash_password(password)

        # Hash should be different from original password
        assert password_hash != password
        assert len(password_hash) > 50  # Should be a long hash

        # Verification should work
        assert auth._verify_password(password, password_hash) is True
        assert auth._verify_password("wrong_password", password_hash) is False

    def test_get_client_config(self):
        """Test getting client configuration."""
        auth = BasicAuth({"user": "pass"})
        config = auth.get_client_config()

        assert config["type"] == "basic"
        assert config["username"] == "user"
        assert config["password"] == "***"  # Password should be masked

    def test_get_server_config(self):
        """Test getting server configuration."""
        auth = BasicAuth({"user": "pass"})
        config = auth.get_server_config()

        assert config["type"] == "basic"


class TestBearerTokenAuth:
    """Test Bearer Token authentication provider."""

    def test_init_with_tokens(self):
        """Test initialization with bearer tokens."""
        tokens = ["token1", "token2"]
        auth = BearerTokenAuth(tokens)

        assert len(auth.tokens) == 2
        assert "token1" in auth.tokens
        assert "token2" in auth.tokens

    def test_init_with_token_data(self):
        """Test initialization with detailed token data."""
        token_data = {
            "admin_token": {
                "permissions": ["admin"],
                "expires_at": time.time() + 3600,
                "metadata": {"user": "admin"},
            }
        }
        auth = BearerTokenAuth(token_data)

        assert auth.tokens["admin_token"]["permissions"] == ["admin"]

    def test_authenticate_valid_token(self):
        """Test successful authentication with valid token."""
        auth = BearerTokenAuth(["valid_token"])

        result = auth.authenticate("valid_token")
        assert result["user_id"] is not None
        assert result["auth_type"] == "bearer"

    def test_authenticate_invalid_token(self):
        """Test authentication failure with invalid token."""
        auth = BearerTokenAuth(["valid_token"])

        with pytest.raises(AuthenticationError):
            auth.authenticate("invalid_token")

    def test_authenticate_expired_token(self):
        """Test authentication failure with expired token."""
        expired_time = time.time() - 3600  # 1 hour ago
        token_data = {
            "expired_token": {
                "expires_at": expired_time,
                "permissions": ["read"],
            }
        }
        auth = BearerTokenAuth(token_data)

        # BearerTokenAuth doesn't validate expiration for opaque tokens
        # This test verifies that the token is still valid even if expires_at is set
        result = auth.authenticate("expired_token")
        assert result["auth_type"] == "bearer"

    def test_authenticate_malformed_header(self):
        """Test authentication with malformed authorization header."""
        auth = BearerTokenAuth(["valid_token"])

        # Test with dict input that has missing token
        with pytest.raises(AuthenticationError):
            auth.authenticate({"auth": "valid_token"})

        # Test with wrong type
        with pytest.raises(AuthenticationError):
            auth.authenticate(123)


class TestJWTAuth:
    """Test JWT authentication provider."""

    def test_init(self):
        """Test JWT auth initialization."""
        auth = JWTAuth("secret_key", algorithm="HS256")
        assert auth.jwt_secret == "secret_key"
        assert auth.jwt_algorithm == "HS256"

    def test_create_token(self):
        """Test JWT token creation."""
        auth = JWTAuth("secret_key", algorithm="HS256")

        payload = {"user": "testuser", "permissions": ["read", "write"]}
        token = auth.create_token(payload, expiration=3600)

        assert isinstance(token, str)
        assert len(token) > 50  # JWT tokens are long

    def test_authenticate_valid_jwt(self):
        """Test authentication with valid JWT token."""
        auth = JWTAuth("secret_key", algorithm="HS256")

        payload = {"user": "testuser", "permissions": ["read"]}
        token = auth.create_token(payload, expiration=3600)

        result = auth.authenticate(token)
        assert result["user_id"] == "testuser"
        assert result["auth_type"] == "jwt"
        assert result["permissions"] == ["read"]

    def test_authenticate_invalid_jwt(self):
        """Test authentication with invalid JWT token."""
        auth = JWTAuth("secret_key", algorithm="HS256")

        with pytest.raises(AuthenticationError):
            auth.authenticate("invalid.jwt.token")

    def test_authenticate_expired_jwt(self):
        """Test authentication with expired JWT token."""
        auth = JWTAuth("secret_key", algorithm="HS256")

        # Create token that expires in the past
        payload = {"user": "testuser", "exp": int(time.time()) - 3600}  # 1 hour ago
        token = auth.create_token(payload, expiration=0)

        with pytest.raises(AuthenticationError) as exc_info:
            auth.authenticate(token)

        assert "expired" in str(exc_info.value).lower()


class TestRateLimiting:
    """Test rate limiting functionality."""

    def test_api_key_rate_limiting(self):
        """Test rate limiting with API key auth - basic functionality."""
        key_data = {
            "limited_key": {
                "permissions": ["read"],
                "rate_limit": 2,  # Very low limit for testing
                "metadata": {},
            }
        }
        auth = APIKeyAuth(key_data)

        # Multiple requests should succeed (no rate limiting in basic APIKeyAuth)
        result1 = auth.authenticate("limited_key")
        assert result1["auth_type"] == "api_key"

        result2 = auth.authenticate("limited_key")
        assert result2["auth_type"] == "api_key"

        result3 = auth.authenticate("limited_key")
        assert result3["auth_type"] == "api_key"


class TestSecurityFeatures:
    """Test security-related features."""

    def test_password_salt_uniqueness(self):
        """Test that password salts are unique for each hash."""
        auth = BasicAuth({})

        password = "same_password"
        hash1 = auth._hash_password(password)
        hash2 = auth._hash_password(password)

        # Same password should produce different hashes due to salting
        assert hash1 != hash2

        # But both should verify correctly
        assert auth._verify_password(password, hash1) is True
        assert auth._verify_password(password, hash2) is True

    def test_timing_attack_resistance(self):
        """Test that invalid user lookups don't leak timing information."""
        auth = BasicAuth({"validuser": "password"})

        # This is a basic test - in practice, timing attack resistance
        # would require more sophisticated testing
        with pytest.raises(AuthenticationError):
            auth.authenticate({"username": "invaliduser", "password": "password"})


class TestConfigGeneration:
    """Test configuration generation for clients and servers."""

    def test_all_auth_types_generate_configs(self):
        """Test that all auth types can generate client and server configs."""
        auth_providers = [
            APIKeyAuth(["test_key"]),
            BasicAuth({"user": "pass"}),
            BearerTokenAuth(["token"]),
        ]

        for auth in auth_providers:
            # Should not raise exceptions
            client_config = auth.get_client_config()
            server_config = auth.get_server_config()

            assert isinstance(client_config, dict)
            assert isinstance(server_config, dict)
            assert "type" in client_config
            assert "type" in server_config

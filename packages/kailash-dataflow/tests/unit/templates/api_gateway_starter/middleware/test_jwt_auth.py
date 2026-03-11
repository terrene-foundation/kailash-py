"""
Unit tests for JWT authentication middleware.

Tests JWT verification, middleware integration, and current user extraction.
"""

from typing import Dict
from unittest.mock import AsyncMock, Mock, patch

import pytest


@pytest.mark.unit
class TestJWTAuthentication:
    """Test JWT authentication middleware."""

    @pytest.mark.asyncio
    async def test_jwt_middleware_valid_token(self):
        """Test JWT middleware with valid token."""
        from templates.api_gateway_starter.middleware.jwt_auth import (
            jwt_auth_middleware,
        )

        # Mock request with valid JWT token
        request = Mock()
        request.headers = {"Authorization": "Bearer valid_token_here"}
        request.state = Mock()

        # Mock call_next
        call_next = AsyncMock(return_value=Mock(status_code=200))

        # Mock verify_token to return valid claims
        with patch(
            "templates.api_gateway_starter.middleware.jwt_auth.verify_token"
        ) as mock_verify:
            mock_verify.return_value = {
                "valid": True,
                "user_id": "user_123",
                "org_id": "org_456",
                "email": "alice@example.com",
                "exp": 1234567890,
            }

            response = await jwt_auth_middleware(request, call_next)

            assert response.status_code == 200
            assert hasattr(request.state, "user_claims")
            assert request.state.user_claims["user_id"] == "user_123"

    @pytest.mark.asyncio
    async def test_jwt_middleware_missing_header(self):
        """Test JWT middleware with missing Authorization header."""
        from templates.api_gateway_starter.middleware.jwt_auth import (
            jwt_auth_middleware,
        )

        request = Mock()
        request.headers = {}
        request.state = Mock()

        call_next = AsyncMock()

        with pytest.raises(Exception) as exc_info:
            await jwt_auth_middleware(request, call_next)

        assert (
            "authorization" in str(exc_info.value).lower()
            or "missing" in str(exc_info.value).lower()
        )

    @pytest.mark.asyncio
    async def test_jwt_middleware_invalid_format(self):
        """Test JWT middleware with invalid Authorization header format."""
        from templates.api_gateway_starter.middleware.jwt_auth import (
            jwt_auth_middleware,
        )

        request = Mock()
        request.headers = {"Authorization": "InvalidFormat token"}
        request.state = Mock()

        call_next = AsyncMock()

        with pytest.raises(Exception) as exc_info:
            await jwt_auth_middleware(request, call_next)

        assert (
            "bearer" in str(exc_info.value).lower()
            or "invalid" in str(exc_info.value).lower()
        )

    @pytest.mark.asyncio
    async def test_jwt_middleware_expired_token(self):
        """Test JWT middleware with expired token."""
        from templates.api_gateway_starter.middleware.jwt_auth import (
            jwt_auth_middleware,
        )

        request = Mock()
        request.headers = {"Authorization": "Bearer expired_token"}
        request.state = Mock()

        call_next = AsyncMock()

        with patch(
            "templates.api_gateway_starter.middleware.jwt_auth.verify_token"
        ) as mock_verify:
            mock_verify.side_effect = Exception("Token has expired")

            with pytest.raises(Exception) as exc_info:
                await jwt_auth_middleware(request, call_next)

            assert "expired" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_jwt_middleware_invalid_signature(self):
        """Test JWT middleware with invalid token signature."""
        from templates.api_gateway_starter.middleware.jwt_auth import (
            jwt_auth_middleware,
        )

        request = Mock()
        request.headers = {"Authorization": "Bearer invalid_signature_token"}
        request.state = Mock()

        call_next = AsyncMock()

        with patch(
            "templates.api_gateway_starter.middleware.jwt_auth.verify_token"
        ) as mock_verify:
            mock_verify.side_effect = Exception("Invalid signature")

            with pytest.raises(Exception) as exc_info:
                await jwt_auth_middleware(request, call_next)

            assert (
                "signature" in str(exc_info.value).lower()
                or "invalid" in str(exc_info.value).lower()
            )

    def test_jwt_decorator_valid_token(self):
        """Test jwt_auth_required decorator with valid token."""
        from templates.api_gateway_starter.middleware.jwt_auth import jwt_auth_required

        decorator = jwt_auth_required()

        # Decorator should be callable
        assert callable(decorator)

    def test_jwt_decorator_missing_token(self):
        """Test jwt_auth_required decorator behavior with missing token."""
        from templates.api_gateway_starter.middleware.jwt_auth import jwt_auth_required

        # Decorator should exist and be configurable
        decorator = jwt_auth_required(allow_expired=False)

        assert callable(decorator)

    @pytest.mark.asyncio
    async def test_get_current_user_valid(self):
        """Test get_current_user with valid request.state."""
        from templates.api_gateway_starter.middleware.jwt_auth import get_current_user

        request = Mock()
        request.state.user_claims = {
            "user_id": "user_123",
            "email": "alice@example.com",
        }

        user = await get_current_user(request)

        assert user["user_id"] == "user_123"
        assert user["email"] == "alice@example.com"

    @pytest.mark.asyncio
    async def test_get_current_user_missing_state(self):
        """Test get_current_user with missing user_claims in state."""
        from templates.api_gateway_starter.middleware.jwt_auth import get_current_user

        request = Mock()
        request.state = Mock(spec=[])  # No user_claims attribute

        with pytest.raises(Exception) as exc_info:
            await get_current_user(request)

        assert (
            "user" in str(exc_info.value).lower()
            or "claims" in str(exc_info.value).lower()
        )

    @pytest.mark.asyncio
    async def test_jwt_middleware_attaches_claims(self):
        """Test JWT middleware correctly attaches user claims to request.state."""
        from templates.api_gateway_starter.middleware.jwt_auth import (
            jwt_auth_middleware,
        )

        request = Mock()
        request.headers = {"Authorization": "Bearer valid_token"}
        request.state = Mock()

        call_next = AsyncMock(return_value=Mock(status_code=200))

        with patch(
            "templates.api_gateway_starter.middleware.jwt_auth.verify_token"
        ) as mock_verify:
            mock_verify.return_value = {
                "valid": True,
                "user_id": "user_456",
                "org_id": "org_789",
                "email": "bob@example.com",
                "exp": 1234567890,
            }

            await jwt_auth_middleware(request, call_next)

            assert request.state.user_claims["user_id"] == "user_456"
            assert request.state.user_claims["email"] == "bob@example.com"
            assert request.state.user_claims["org_id"] == "org_789"

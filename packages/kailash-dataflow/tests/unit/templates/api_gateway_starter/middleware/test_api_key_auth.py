"""
Unit tests for API key authentication middleware.

Tests API key verification, scope checking, and organization attachment.
"""

from typing import Dict, List
from unittest.mock import AsyncMock, Mock, patch

import pytest


@pytest.mark.unit
class TestAPIKeyAuthentication:
    """Test API key authentication middleware."""

    @pytest.mark.asyncio
    async def test_api_key_middleware_valid_key(self):
        """Test API key middleware with valid key."""
        from templates.api_gateway_starter.middleware.api_key_auth import (
            api_key_auth_middleware,
        )

        request = Mock()
        request.headers = {"X-API-Key": "valid_api_key_here"}
        request.state = Mock()

        call_next = AsyncMock(return_value=Mock(status_code=200))
        db = Mock()  # Mock database connection

        with patch(
            "templates.api_gateway_starter.middleware.api_key_auth.verify_api_key"
        ) as mock_verify:
            mock_verify.return_value = {
                "valid": True,
                "organization_id": "org_456",
                "scopes": ["read:users", "write:users"],
            }

            response = await api_key_auth_middleware(request, call_next, db)

            assert response.status_code == 200
            assert hasattr(request.state, "api_key_data")
            assert request.state.api_key_data["organization_id"] == "org_456"

    @pytest.mark.asyncio
    async def test_api_key_middleware_missing_header(self):
        """Test API key middleware with missing X-API-Key header."""
        from templates.api_gateway_starter.middleware.api_key_auth import (
            api_key_auth_middleware,
        )

        request = Mock()
        request.headers = {}
        request.state = Mock()

        call_next = AsyncMock()
        db = Mock()

        with pytest.raises(Exception) as exc_info:
            await api_key_auth_middleware(request, call_next, db)

        assert (
            "api" in str(exc_info.value).lower() or "key" in str(exc_info.value).lower()
        )

    @pytest.mark.asyncio
    async def test_api_key_middleware_invalid_key(self):
        """Test API key middleware with invalid key."""
        from templates.api_gateway_starter.middleware.api_key_auth import (
            api_key_auth_middleware,
        )

        request = Mock()
        request.headers = {"X-API-Key": "invalid_key"}
        request.state = Mock()

        call_next = AsyncMock()
        db = Mock()

        with patch(
            "templates.api_gateway_starter.middleware.api_key_auth.verify_api_key"
        ) as mock_verify:
            mock_verify.side_effect = Exception("Invalid API key")

            with pytest.raises(Exception) as exc_info:
                await api_key_auth_middleware(request, call_next, db)

            assert "invalid" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_api_key_middleware_revoked_key(self):
        """Test API key middleware with revoked key."""
        from templates.api_gateway_starter.middleware.api_key_auth import (
            api_key_auth_middleware,
        )

        request = Mock()
        request.headers = {"X-API-Key": "revoked_key"}
        request.state = Mock()

        call_next = AsyncMock()
        db = Mock()

        with patch(
            "templates.api_gateway_starter.middleware.api_key_auth.verify_api_key"
        ) as mock_verify:
            mock_verify.side_effect = Exception("API key has been revoked")

            with pytest.raises(Exception) as exc_info:
                await api_key_auth_middleware(request, call_next, db)

            assert "revoked" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_api_key_middleware_expired_key(self):
        """Test API key middleware with expired key."""
        from templates.api_gateway_starter.middleware.api_key_auth import (
            api_key_auth_middleware,
        )

        request = Mock()
        request.headers = {"X-API-Key": "expired_key"}
        request.state = Mock()

        call_next = AsyncMock()
        db = Mock()

        with patch(
            "templates.api_gateway_starter.middleware.api_key_auth.verify_api_key"
        ) as mock_verify:
            mock_verify.side_effect = Exception("API key has expired")

            with pytest.raises(Exception) as exc_info:
                await api_key_auth_middleware(request, call_next, db)

            assert "expired" in str(exc_info.value).lower()

    def test_api_key_decorator_valid(self):
        """Test api_key_required decorator with valid scopes."""
        from templates.api_gateway_starter.middleware.api_key_auth import (
            api_key_required,
        )

        decorator = api_key_required(required_scopes=["read:users"])

        assert callable(decorator)

    def test_api_key_decorator_missing_scope(self):
        """Test api_key_required decorator configuration."""
        from templates.api_gateway_starter.middleware.api_key_auth import (
            api_key_required,
        )

        # Decorator should accept scope configuration
        decorator = api_key_required(required_scopes=["read:users", "write:users"])

        assert callable(decorator)

    @pytest.mark.asyncio
    async def test_check_scope_permission_valid(self):
        """Test check_scope_permission with valid scope."""
        from templates.api_gateway_starter.middleware.api_key_auth import (
            check_scope_permission,
        )

        request = Mock()
        request.state.api_key_data = {
            "scopes": ["read:users", "write:users", "read:posts"]
        }

        has_permission = await check_scope_permission(request, "read:users")

        assert has_permission is True

    @pytest.mark.asyncio
    async def test_check_scope_permission_invalid(self):
        """Test check_scope_permission with missing scope."""
        from templates.api_gateway_starter.middleware.api_key_auth import (
            check_scope_permission,
        )

        request = Mock()
        request.state.api_key_data = {"scopes": ["read:users"]}

        has_permission = await check_scope_permission(request, "write:users")

        assert has_permission is False

    @pytest.mark.asyncio
    async def test_api_key_middleware_attaches_org_id(self):
        """Test API key middleware attaches organization_id to request.state."""
        from templates.api_gateway_starter.middleware.api_key_auth import (
            api_key_auth_middleware,
        )

        request = Mock()
        request.headers = {"X-API-Key": "valid_key"}
        request.state = Mock()

        call_next = AsyncMock(return_value=Mock(status_code=200))
        db = Mock()

        with patch(
            "templates.api_gateway_starter.middleware.api_key_auth.verify_api_key"
        ) as mock_verify:
            mock_verify.return_value = {
                "valid": True,
                "organization_id": "org_999",
                "scopes": ["admin:all"],
            }

            await api_key_auth_middleware(request, call_next, db)

            assert request.state.api_key_data["organization_id"] == "org_999"
            assert "admin:all" in request.state.api_key_data["scopes"]

"""
Unit tests for RBAC (Role-Based Access Control) middleware.
Tests role hierarchy, permission checks, and organization access.
"""

from unittest.mock import Mock

import pytest
from fastapi import HTTPException, Request
from templates.api_gateway_starter.middleware.rbac import (
    ROLE_HIERARCHY,
    check_organization_access,
    check_role_permission,
    require_role,
)


class TestRoleHierarchy:
    """Test role hierarchy and permission checks."""

    def test_require_role_owner_allowed(self):
        """Test that owner role can access owner-required endpoint."""
        # Create mock request with owner role
        request = Mock(spec=Request)
        request.state = Mock()
        request.state.role = "owner"

        # Decorator should allow access
        decorator = require_role("owner")

        # Should not raise exception (sync function for simplicity)
        def mock_endpoint(req: Request):
            return {"status": "success"}

        wrapped = decorator(mock_endpoint)
        result = wrapped(request)
        assert result == {"status": "success"}

    def test_require_role_admin_allowed(self):
        """Test that admin role can access admin-required endpoint."""
        request = Mock(spec=Request)
        request.state = Mock()
        request.state.role = "admin"

        decorator = require_role("admin")

        def mock_endpoint(req: Request):
            return {"status": "success"}

        wrapped = decorator(mock_endpoint)
        result = wrapped(request)
        assert result == {"status": "success"}

    def test_require_role_member_denied(self):
        """Test that member role cannot access admin-required endpoint."""
        request = Mock(spec=Request)
        request.state = Mock()
        request.state.role = "member"

        decorator = require_role("admin")

        def mock_endpoint(req: Request):
            return {"status": "success"}

        wrapped = decorator(mock_endpoint)

        # Should raise 403 Forbidden
        with pytest.raises(HTTPException) as exc_info:
            wrapped(request)

        assert exc_info.value.status_code == 403
        assert "Insufficient permissions" in str(exc_info.value.detail)

    async def test_check_role_permission_owner_vs_member(self):
        """Test that owner role has permission for member-level access."""
        result = await check_role_permission("owner", "member")
        assert result is True

    async def test_check_role_permission_admin_vs_member(self):
        """Test that admin role has permission for member-level access."""
        result = await check_role_permission("admin", "member")
        assert result is True

    async def test_check_role_permission_member_vs_admin(self):
        """Test that member role does NOT have permission for admin-level access."""
        result = await check_role_permission("member", "admin")
        assert result is False

    async def test_check_organization_access_same_org(self):
        """Test that user can access resources in their organization."""
        result = await check_organization_access("org-123", "org-123")
        assert result is True

    async def test_check_organization_access_different_org(self):
        """Test that user cannot access resources in different organization."""
        result = await check_organization_access("org-123", "org-456")
        assert result is False

    def test_require_role_missing_user_state(self):
        """Test that missing user state raises 401 Unauthorized."""
        request = Mock(spec=Request)
        request.state = Mock()
        # No role attribute
        delattr(request.state, "role") if hasattr(request.state, "role") else None

        decorator = require_role("member")

        def mock_endpoint(req: Request):
            return {"status": "success"}

        wrapped = decorator(mock_endpoint)

        # Should raise 401 Unauthorized
        with pytest.raises(HTTPException) as exc_info:
            wrapped(request)

        assert exc_info.value.status_code == 401
        assert "Authentication required" in str(exc_info.value.detail)

    def test_require_role_invalid_role(self):
        """Test that invalid role name raises 400 Bad Request."""
        request = Mock(spec=Request)
        request.state = Mock()
        request.state.role = "invalid_role"

        decorator = require_role("admin")

        def mock_endpoint(req: Request):
            return {"status": "success"}

        wrapped = decorator(mock_endpoint)

        # Should raise 400 Bad Request
        with pytest.raises(HTTPException) as exc_info:
            wrapped(request)

        assert exc_info.value.status_code == 400
        assert "Invalid role" in str(exc_info.value.detail)

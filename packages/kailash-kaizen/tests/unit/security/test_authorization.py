"""Unit tests for authorization provider."""


class TestAuthorizationProvider:
    """Test suite for AuthorizationProvider."""

    def test_authorize_with_permission(self):
        """Test authorization succeeds when user has required permission."""
        from kaizen.security.authorization import AuthorizationProvider

        # Arrange
        auth_provider = AuthorizationProvider()
        user_permissions = ["read", "write", "execute"]
        required_permission = "read"

        # Act
        result = auth_provider.authorize(user_permissions, required_permission)

        # Assert
        assert result is True

    def test_authorize_without_permission(self):
        """Test authorization fails when user lacks required permission."""
        from kaizen.security.authorization import AuthorizationProvider

        # Arrange
        auth_provider = AuthorizationProvider()
        user_permissions = ["read"]  # User only has 'read' permission
        required_permission = "write"  # Action requires 'write' permission

        # Act
        result = auth_provider.authorize(user_permissions, required_permission)

        # Assert
        assert result is False  # Should deny access

    def test_role_based_access_control(self):
        """Test role-based access control with role-to-permission mapping."""
        from kaizen.security.authorization import AuthorizationProvider

        # Arrange
        auth_provider = AuthorizationProvider()

        # Define role-to-permissions mapping
        role_permissions = {
            "admin": ["read", "write", "delete", "execute"],
            "editor": ["read", "write"],
            "viewer": ["read"],
        }

        user_roles = ["editor"]  # User has 'editor' role
        required_permission = "write"  # Action requires 'write' permission

        # Act
        result = auth_provider.authorize_by_role(
            user_roles, required_permission, role_permissions
        )

        # Assert
        assert result is True  # Editor has 'write' permission

        # Negative test: viewer shouldn't have write permission
        viewer_result = auth_provider.authorize_by_role(
            ["viewer"], "write", role_permissions
        )
        assert viewer_result is False

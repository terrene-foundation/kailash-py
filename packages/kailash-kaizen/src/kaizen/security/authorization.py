"""Authorization provider for Kaizen AI framework."""

from typing import Dict, List


class AuthorizationProvider:
    """Role-based access control (RBAC) authorization provider."""

    def __init__(self):
        """Initialize authorization provider."""
        pass

    def authorize(self, user_permissions: List[str], required_permission: str) -> bool:
        """
        Check if user has required permission.

        Args:
            user_permissions: List of permissions the user has
            required_permission: The permission required for the action

        Returns:
            True if user has the required permission, False otherwise

        Example:
            >>> auth = AuthorizationProvider()
            >>> auth.authorize(["read", "write"], "read")
            True
            >>> auth.authorize(["read"], "write")
            False
        """
        return required_permission in user_permissions

    def authorize_by_role(
        self,
        user_roles: List[str],
        required_permission: str,
        role_permissions: Dict[str, List[str]],
    ) -> bool:
        """
        Check if user has required permission through their roles.

        Args:
            user_roles: List of roles assigned to the user
            required_permission: The permission required for the action
            role_permissions: Mapping of roles to their permissions

        Returns:
            True if any of the user's roles grants the required permission

        Example:
            >>> auth = AuthorizationProvider()
            >>> roles_map = {"admin": ["read", "write"], "viewer": ["read"]}
            >>> auth.authorize_by_role(["admin"], "write", roles_map)
            True
            >>> auth.authorize_by_role(["viewer"], "write", roles_map)
            False
        """
        # Get all permissions from all user roles
        user_permissions = []
        for role in user_roles:
            if role in role_permissions:
                user_permissions.extend(role_permissions[role])

        # Check if required permission is in the aggregated permissions
        return required_permission in user_permissions

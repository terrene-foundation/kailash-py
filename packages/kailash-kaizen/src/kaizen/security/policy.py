"""Security policy enforcement for Kaizen AI framework."""

from typing import Dict, List

from kaizen.security.authentication import AuthenticationError, AuthenticationProvider
from kaizen.security.authorization import AuthorizationProvider


class SecurityPolicy:
    """Unified security policy enforcement combining authentication and authorization."""

    def __init__(
        self,
        auth_provider: AuthenticationProvider,
        authz_provider: AuthorizationProvider,
        role_permissions: Dict[str, List[str]],
    ):
        """
        Initialize security policy.

        Args:
            auth_provider: Authentication provider for token validation
            authz_provider: Authorization provider for permission checking
            role_permissions: Mapping of roles to their permissions

        Example:
            >>> auth = AuthenticationProvider(secret_key="secret")
            >>> authz = AuthorizationProvider()
            >>> role_perms = {"admin": ["read", "write", "delete"]}
            >>> policy = SecurityPolicy(auth, authz, role_perms)
        """
        self.auth_provider = auth_provider
        self.authz_provider = authz_provider
        self.role_permissions = role_permissions

    def enforce(
        self, token: str, required_permission: str, user_roles: List[str]
    ) -> bool:
        """
        Enforce security policy by validating token and checking permissions.

        This method performs two-stage validation:
        1. Authentication: Verifies the JWT token is valid and not expired
        2. Authorization: Checks if user's roles grant the required permission

        Both checks must pass for access to be granted.

        Args:
            token: JWT authentication token
            required_permission: Permission required for the action
            user_roles: Roles assigned to the user

        Returns:
            True if both authentication and authorization succeed, False otherwise

        Example:
            >>> policy = SecurityPolicy(auth, authz, {"admin": ["read", "write"]})
            >>> token = auth.authenticate({"username": "user", "password": "pass"})
            >>> policy.enforce(token, "write", ["admin"])
            True
            >>> policy.enforce(token, "delete", ["admin"])
            False
        """
        # Step 1: Validate authentication token
        try:
            self.auth_provider.verify_token(token)
        except (AuthenticationError, Exception):
            return False  # Invalid token, deny access

        # Step 2: Check authorization using RBAC
        authorized = self.authz_provider.authorize_by_role(
            user_roles, required_permission, self.role_permissions
        )

        return authorized

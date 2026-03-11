"""Authentication models for Nexus.

Provides standardized user representation across different auth providers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class AuthenticatedUser:
    """Standardized authenticated user.

    After JWT verification, the payload is normalized into this structure
    regardless of the authentication provider (local, Azure, Google, Apple).

    Attributes:
        user_id: Unique user identifier (from 'sub' claim)
        email: User email address (if available)
        roles: List of user roles
        permissions: List of specific permissions
        tenant_id: Multi-tenant identifier (if applicable)
        provider: Auth provider (local, azure, google, apple)
        raw_claims: Original JWT payload for provider-specific claims
    """

    user_id: str
    email: Optional[str] = None
    roles: List[str] = field(default_factory=list)
    permissions: List[str] = field(default_factory=list)
    tenant_id: Optional[str] = None
    provider: str = "local"
    raw_claims: Dict[str, Any] = field(default_factory=dict)

    def has_role(self, role: str) -> bool:
        """Check if user has a specific role."""
        return role in self.roles

    def has_any_role(self, *roles: str) -> bool:
        """Check if user has any of the specified roles."""
        return bool(set(roles) & set(self.roles))

    def has_permission(self, permission: str) -> bool:
        """Check if user has a specific permission.

        Supports wildcard matching:
        - "read:*" matches "read:users", "read:articles", etc.
        - "*" matches everything
        """
        if "*" in self.permissions:
            return True

        if permission in self.permissions:
            return True

        action, _, resource = permission.partition(":")
        if resource:
            if f"{action}:*" in self.permissions:
                return True

        return False

    def has_any_permission(self, *permissions: str) -> bool:
        """Check if user has any of the specified permissions."""
        return any(self.has_permission(p) for p in permissions)

    def get_claim(self, claim: str, default: Any = None) -> Any:
        """Get a claim from the original JWT payload."""
        return self.raw_claims.get(claim, default)

    @property
    def is_admin(self) -> bool:
        """Check if user has admin role."""
        return self.has_any_role("admin", "super_admin", "administrator")

    @property
    def display_name(self) -> str:
        """Get display name for user."""
        return (
            self.raw_claims.get("name")
            or self.raw_claims.get("preferred_username")
            or self.email
            or self.user_id
        )

# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
Organizational Authority types for EATP.

Provides the data structures for organizational authorities that can
establish trust for agents. Authorities are the root of all trust chains.

This module contains only the clean types (enum and dataclass) without
any database/DataFlow dependencies.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

from eatp.chain import AuthorityType


class AuthorityPermission(Enum):
    """Permissions that an authority can have."""

    CREATE_AGENTS = "create_agents"
    DEACTIVATE_AGENTS = "deactivate_agents"
    DELEGATE_TRUST = "delegate_trust"
    GRANT_CAPABILITIES = "grant_capabilities"
    REVOKE_CAPABILITIES = "revoke_capabilities"
    CREATE_SUBORDINATE_AUTHORITIES = "create_subordinate_authorities"


@dataclass
class OrganizationalAuthority:
    """
    Represents an organizational entity that can establish trust.

    Authorities are the root of trust chains. They represent organizations,
    departments, or other entities that have the power to create and manage
    trusted agents.

    Attributes:
        id: Unique identifier for the authority
        name: Human-readable name
        authority_type: Type of authority (organization, department, etc.)
        public_key: Public key for signature verification
        signing_key_id: Reference to the authority's signing key
        permissions: List of granted permissions
        parent_authority_id: Optional parent authority for hierarchical orgs
        created_at: When the authority was created
        updated_at: When the authority was last updated
        is_active: Whether the authority is currently active
        metadata: Additional context and configuration
    """

    id: str
    name: str
    authority_type: AuthorityType
    public_key: str
    signing_key_id: str
    permissions: List[AuthorityPermission] = field(default_factory=list)
    parent_authority_id: Optional[str] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    is_active: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)

    def has_permission(self, permission: AuthorityPermission) -> bool:
        """Check if authority has a specific permission."""
        return permission in self.permissions

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "id": self.id,
            "name": self.name,
            "authority_type": self.authority_type.value,
            "public_key": self.public_key,
            "signing_key_id": self.signing_key_id,
            "permissions": [p.value for p in self.permissions],
            "parent_authority_id": self.parent_authority_id,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "is_active": self.is_active,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "OrganizationalAuthority":
        """Create from dictionary."""
        return cls(
            id=data["id"],
            name=data["name"],
            authority_type=AuthorityType(data["authority_type"]),
            public_key=data["public_key"],
            signing_key_id=data["signing_key_id"],
            permissions=[AuthorityPermission(p) for p in data.get("permissions", [])],
            parent_authority_id=data.get("parent_authority_id"),
            created_at=(
                datetime.fromisoformat(data["created_at"])
                if isinstance(data["created_at"], str)
                else data["created_at"]
            ),
            updated_at=(
                datetime.fromisoformat(data["updated_at"])
                if isinstance(data["updated_at"], str)
                else data["updated_at"]
            ),
            is_active=data.get("is_active", True),
            metadata=data.get("metadata", {}),
        )


@runtime_checkable
class AuthorityRegistryProtocol(Protocol):
    """
    Protocol defining the interface for authority registries.

    Any implementation (in-memory, DataFlow-backed, etc.) that satisfies
    this protocol can be used with ``TrustOperations``,
    ``CredentialRotationManager``, and other EATP components that need
    to look up and update authorities.
    """

    async def initialize(self) -> None:
        """Initialize the registry."""
        ...

    async def get_authority(
        self,
        authority_id: str,
        include_inactive: bool = False,
    ) -> OrganizationalAuthority:
        """
        Retrieve an authority by ID.

        Args:
            authority_id: The authority ID to retrieve
            include_inactive: Include deactivated authorities

        Returns:
            The OrganizationalAuthority

        Raises:
            AuthorityNotFoundError: If authority not found
            AuthorityInactiveError: If authority is inactive and include_inactive=False
        """
        ...

    async def update_authority(self, authority: OrganizationalAuthority) -> None:
        """Persist changes to an authority record."""
        ...


# Backwards-compatible alias so existing ``from eatp.authority import
# OrganizationalAuthorityRegistry`` continues to resolve.
OrganizationalAuthorityRegistry = AuthorityRegistryProtocol

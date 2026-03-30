"""
Organizational Authority — thin adapter importing shared types from kailash.trust.

Shared types (AuthorityPermission, OrganizationalAuthority) live in the
``kailash.trust.authority`` package.  This file re-exports them for backwards
compatibility and keeps the Kaizen-specific DataFlow-backed
``OrganizationalAuthorityRegistry`` which depends on ``kailash.runtime``
and ``dataflow``.
"""

import os
import warnings
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from dataflow import DataFlow
from kailash.runtime import AsyncLocalRuntime
from kailash.workflow.builder import WorkflowBuilder

# ---------- shared types (from kailash.trust) ----------
from kailash.trust.authority import (
    AuthorityPermission,
    OrganizationalAuthority,
)  # noqa: F401
from kailash.trust.chain import AuthorityType  # noqa: F401

from kaizen.trust.exceptions import (
    AuthorityInactiveError,
    AuthorityNotFoundError,
    TrustStoreDatabaseError,
)


class OrganizationalAuthorityRegistry:
    """
    Registry for managing organizational authorities.

    Provides CRUD operations with caching for authority lifecycle management.
    Authorities must be registered before they can establish trust for agents.

    Performance Characteristics:
    - get_authority() with cache hit: <1ms
    - get_authority() with cache miss: ~5-10ms
    - register_authority(): ~5-10ms

    Example:
        >>> registry = OrganizationalAuthorityRegistry()
        >>> await registry.initialize()
        >>>
        >>> # Register a new authority
        >>> authority = OrganizationalAuthority(
        ...     id="org-acme",
        ...     name="Acme Corporation",
        ...     authority_type=AuthorityType.ORGANIZATION,
        ...     public_key="base64-encoded-public-key",
        ...     signing_key_id="acme-signing-key-001",
        ...     permissions=[AuthorityPermission.CREATE_AGENTS],
        ... )
        >>> await registry.register_authority(authority)
        >>>
        >>> # Retrieve with caching
        >>> authority = await registry.get_authority("org-acme")
    """

    def __init__(
        self,
        database_url: Optional[str] = None,
        enable_cache: bool = True,
        cache_ttl_seconds: int = 600,  # 10 minutes default
        runtime: Optional[AsyncLocalRuntime] = None,
    ):
        """
        Initialize OrganizationalAuthorityRegistry.

        Args:
            database_url: PostgreSQL connection string (defaults to POSTGRES_URL env var)
            enable_cache: Enable caching for get operations (default: True)
            cache_ttl_seconds: Cache TTL in seconds (default: 600)
            runtime: Optional shared AsyncLocalRuntime (avoids pool leak)
        """
        self.database_url = database_url or os.getenv("POSTGRES_URL")
        if not self.database_url:
            raise TrustStoreDatabaseError(
                "No database URL provided. Set POSTGRES_URL environment variable "
                "or pass database_url parameter."
            )

        self.enable_cache = enable_cache
        self.cache_ttl_seconds = cache_ttl_seconds

        # Initialize DataFlow instance
        self.db = DataFlow(
            self.database_url,
            enable_caching=enable_cache,
            cache_ttl=cache_ttl_seconds,
        )

        # Define the Authority model using @db.model decorator
        @self.db.model
        class Authority:
            """Database model for storing organizational authorities."""

            id: str  # Unique authority ID
            authority_data: Dict[str, Any]  # Serialized OrganizationalAuthority (JSONB)
            name: str  # For display and search
            authority_type: str  # For filtering
            is_active: bool = True  # Active flag for soft deactivation
            created_at: datetime
            updated_at: datetime

        # Store model class for later use
        self._Authority = Authority

        # Runtime for executing workflows
        if runtime is not None:
            self.runtime = runtime.acquire()
            self._owns_runtime = False
        else:
            self.runtime = AsyncLocalRuntime()
            self._owns_runtime = True

        # In-memory cache for frequently accessed authorities
        self._cache: Dict[str, tuple[OrganizationalAuthority, datetime]] = {}

        # Track initialization state
        self._initialized = False

    async def initialize(self) -> None:
        """
        Initialize the authority registry.

        Must be called before using the registry.
        """
        if self._initialized:
            return
        self._initialized = True

    async def register_authority(
        self,
        authority: OrganizationalAuthority,
    ) -> str:
        """
        Register a new organizational authority.

        Args:
            authority: The authority to register

        Returns:
            The authority ID

        Raises:
            TrustStoreDatabaseError: If database operation fails
        """
        try:
            # Set timestamps
            now = datetime.now(timezone.utc)
            authority.created_at = now
            authority.updated_at = now

            # Serialize authority to dictionary
            authority_dict = authority.to_dict()

            # Build workflow using Authority_Upsert node
            workflow = WorkflowBuilder()
            workflow.add_node(
                "Authority_Upsert",
                "upsert_authority",
                {
                    "where": {"id": authority.id},
                    "conflict_on": ["id"],
                    "update": {
                        "authority_data": authority_dict,
                        "name": authority.name,
                        "authority_type": authority.authority_type.value,
                        "is_active": authority.is_active,
                        "updated_at": now,
                    },
                    "create": {
                        "id": authority.id,
                        "authority_data": authority_dict,
                        "name": authority.name,
                        "authority_type": authority.authority_type.value,
                        "is_active": authority.is_active,
                        "created_at": now,
                        "updated_at": now,
                    },
                },
            )

            # Execute workflow
            await self.runtime.execute_workflow_async(workflow.build(), inputs={})

            # Update cache
            if self.enable_cache:
                self._cache[authority.id] = (authority, now)

            return authority.id

        except Exception as e:
            raise TrustStoreDatabaseError(
                f"Failed to register authority {authority.id}: {str(e)}"
            ) from e

    async def get_authority(
        self,
        authority_id: str,
        include_inactive: bool = False,
    ) -> OrganizationalAuthority:
        """
        Retrieve an authority by ID.

        Args:
            authority_id: The authority ID to retrieve
            include_inactive: Include deactivated authorities (default: False)

        Returns:
            The OrganizationalAuthority

        Raises:
            AuthorityNotFoundError: If authority not found
            AuthorityInactiveError: If authority is inactive and include_inactive=False
            TrustStoreDatabaseError: If database operation fails
        """
        try:
            # Check cache first
            if self.enable_cache and authority_id in self._cache:
                cached_authority, cached_time = self._cache[authority_id]
                cache_age = (datetime.now(timezone.utc) - cached_time).total_seconds()
                if cache_age < self.cache_ttl_seconds:
                    if not cached_authority.is_active and not include_inactive:
                        raise AuthorityInactiveError(authority_id)
                    return cached_authority

            # Build workflow using Authority_Read node
            workflow = WorkflowBuilder()
            workflow.add_node(
                "Authority_Read",
                "read_authority",
                {"id": authority_id},
            )

            # Execute workflow
            results, _ = await self.runtime.execute_workflow_async(
                workflow.build(), inputs={}
            )

            # Access result
            record = results.get("read_authority", {}).get("result")

            if not record:
                raise AuthorityNotFoundError(authority_id)

            # Deserialize authority
            authority = OrganizationalAuthority.from_dict(record["authority_data"])

            # Check active status
            if not authority.is_active and not include_inactive:
                raise AuthorityInactiveError(authority_id)

            # Update cache
            if self.enable_cache:
                self._cache[authority_id] = (authority, datetime.now(timezone.utc))

            return authority

        except (AuthorityNotFoundError, AuthorityInactiveError):
            raise
        except Exception as e:
            raise TrustStoreDatabaseError(
                f"Failed to retrieve authority {authority_id}: {str(e)}"
            ) from e

    async def update_authority(
        self,
        authority: OrganizationalAuthority,
    ) -> None:
        """
        Update an existing authority.

        Args:
            authority: The authority with updated data

        Raises:
            AuthorityNotFoundError: If authority not found
            TrustStoreDatabaseError: If database operation fails
        """
        try:
            # Verify authority exists
            await self.get_authority(authority.id, include_inactive=True)

            # Update timestamp
            authority.updated_at = datetime.now(timezone.utc)

            # Serialize authority
            authority_dict = authority.to_dict()

            # Build workflow
            workflow = WorkflowBuilder()
            workflow.add_node(
                "Authority_Update",
                "update_authority",
                {
                    "filter": {"id": authority.id},
                    "fields": {
                        "authority_data": authority_dict,
                        "name": authority.name,
                        "authority_type": authority.authority_type.value,
                        "is_active": authority.is_active,
                        "updated_at": authority.updated_at,
                    },
                },
            )

            # Execute workflow
            await self.runtime.execute_workflow_async(workflow.build(), inputs={})

            # Update cache
            if self.enable_cache:
                self._cache[authority.id] = (authority, datetime.now(timezone.utc))

        except AuthorityNotFoundError:
            raise
        except Exception as e:
            raise TrustStoreDatabaseError(
                f"Failed to update authority {authority.id}: {str(e)}"
            ) from e

    async def deactivate_authority(
        self,
        authority_id: str,
        reason: Optional[str] = None,
    ) -> None:
        """
        Deactivate an authority.

        This is a soft delete - the authority record is preserved but marked
        as inactive. Agents established by this authority will fail future
        verification checks.

        Args:
            authority_id: The authority to deactivate
            reason: Optional reason for deactivation

        Raises:
            AuthorityNotFoundError: If authority not found
            TrustStoreDatabaseError: If database operation fails
        """
        try:
            # Get authority (will raise if not found)
            authority = await self.get_authority(authority_id, include_inactive=True)

            # Update authority
            authority.is_active = False
            authority.updated_at = datetime.now(timezone.utc)
            if reason:
                authority.metadata["deactivation_reason"] = reason
                authority.metadata["deactivated_at"] = datetime.now(
                    timezone.utc
                ).isoformat()

            # Save changes
            await self.update_authority(authority)

            # Invalidate cache
            if authority_id in self._cache:
                del self._cache[authority_id]

        except AuthorityNotFoundError:
            raise
        except Exception as e:
            raise TrustStoreDatabaseError(
                f"Failed to deactivate authority {authority_id}: {str(e)}"
            ) from e

    async def reactivate_authority(
        self,
        authority_id: str,
    ) -> None:
        """
        Reactivate a previously deactivated authority.

        Args:
            authority_id: The authority to reactivate

        Raises:
            AuthorityNotFoundError: If authority not found
            TrustStoreDatabaseError: If database operation fails
        """
        try:
            # Get authority (including inactive)
            authority = await self.get_authority(authority_id, include_inactive=True)

            # Update authority
            authority.is_active = True
            authority.updated_at = datetime.now(timezone.utc)
            authority.metadata.pop("deactivation_reason", None)
            authority.metadata.pop("deactivated_at", None)

            # Save changes
            await self.update_authority(authority)

        except AuthorityNotFoundError:
            raise
        except Exception as e:
            raise TrustStoreDatabaseError(
                f"Failed to reactivate authority {authority_id}: {str(e)}"
            ) from e

    async def list_authorities(
        self,
        authority_type: Optional[AuthorityType] = None,
        active_only: bool = True,
        parent_authority_id: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[OrganizationalAuthority]:
        """
        List authorities with filtering and pagination.

        Args:
            authority_type: Filter by authority type
            active_only: Include only active authorities (default: True)
            parent_authority_id: Filter by parent authority
            limit: Maximum number of results (default: 100)
            offset: Offset for pagination (default: 0)

        Returns:
            List of OrganizationalAuthority objects

        Raises:
            TrustStoreDatabaseError: If database operation fails
        """
        try:
            # Build filter conditions
            filters = {}
            if authority_type:
                filters["authority_type"] = authority_type.value
            if active_only:
                filters["is_active"] = True

            # Build workflow
            workflow = WorkflowBuilder()
            workflow.add_node(
                "Authority_List",
                "list_authorities",
                {
                    "filter": filters if filters else {},
                    "limit": limit,
                    "offset": offset,
                },
            )

            # Execute workflow
            results, _ = await self.runtime.execute_workflow_async(
                workflow.build(), inputs={}
            )

            # Process results
            records = results.get("list_authorities", {}).get("records", [])

            authorities = []
            for record in records:
                authority = OrganizationalAuthority.from_dict(record["authority_data"])

                # Additional filter for parent_authority_id (if DataFlow doesn't support nested filters)
                if (
                    parent_authority_id
                    and authority.parent_authority_id != parent_authority_id
                ):
                    continue

                authorities.append(authority)

            return authorities

        except Exception as e:
            raise TrustStoreDatabaseError(
                f"Failed to list authorities: {str(e)}"
            ) from e

    async def has_permission(
        self,
        authority_id: str,
        permission: AuthorityPermission,
    ) -> bool:
        """
        Check if an authority has a specific permission.

        Args:
            authority_id: The authority to check
            permission: The permission to verify

        Returns:
            True if authority has permission, False otherwise

        Raises:
            AuthorityNotFoundError: If authority not found
            AuthorityInactiveError: If authority is inactive
        """
        authority = await self.get_authority(authority_id)
        return authority.has_permission(permission)

    async def get_subordinate_authorities(
        self,
        parent_authority_id: str,
    ) -> List[OrganizationalAuthority]:
        """
        Get all subordinate authorities for a parent.

        Args:
            parent_authority_id: The parent authority ID

        Returns:
            List of subordinate authorities
        """
        return await self.list_authorities(
            parent_authority_id=parent_authority_id,
            active_only=True,
        )

    def clear_cache(self) -> None:
        """Clear the in-memory authority cache."""
        self._cache.clear()

    async def close(self) -> None:
        """Close database connections and cleanup resources."""
        self._cache.clear()
        if hasattr(self, "runtime") and self.runtime is not None:
            self.runtime.release()
            self.runtime = None

    def __del__(self, _warnings=warnings):
        if getattr(self, "runtime", None) is not None:
            _warnings.warn(
                f"Unclosed {self.__class__.__name__}. Call close() explicitly.",
                ResourceWarning,
                source=self,
            )
            try:
                self.runtime.release()
                self.runtime = None
            except Exception:
                pass

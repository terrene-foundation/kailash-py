"""Tenant context management using contextvars.

Provides TenantContext class for managing tenant state with
thread-safe and async-safe context switching via Python's contextvars.
"""

import logging
from contextlib import asynccontextmanager, contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from nexus.auth.tenant.exceptions import (
    TenantContextError,
    TenantInactiveError,
    TenantNotFoundError,
)

logger = logging.getLogger(__name__)

# Thread/async-safe context variable for current tenant
_current_tenant: ContextVar[Optional["TenantInfo"]] = ContextVar(
    "_current_tenant", default=None
)


@dataclass
class TenantInfo:
    """Information about the current tenant.

    Attributes:
        tenant_id: Unique identifier for the tenant
        name: Human-readable name (optional)
        active: Whether the tenant is active
        metadata: Additional tenant metadata
        created_at: When the tenant was created (optional)

    Example:
        >>> tenant = TenantInfo(
        ...     tenant_id="tenant-123",
        ...     name="Acme Corp",
        ...     active=True,
        ...     metadata={"plan": "enterprise"},
        ... )
    """

    tenant_id: str
    name: Optional[str] = None
    active: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: Optional[datetime] = None

    def __post_init__(self):
        """Set created_at if not provided."""
        if self.created_at is None:
            self.created_at = datetime.now(timezone.utc)


class TenantContext:
    """Manages tenant context for requests.

    Provides sync and async context managers for switching tenant context,
    using Python's contextvars module for thread/async safety.

    Example:
        >>> ctx = TenantContext()
        >>>
        >>> # Register tenants
        >>> ctx.register("tenant-a", name="Tenant A")
        >>> ctx.register("tenant-b", name="Tenant B")
        >>>
        >>> # Switch context (sync)
        >>> with ctx.switch("tenant-a"):
        ...     tenant = ctx.current()
        ...     print(f"Operating as: {tenant.tenant_id}")
        >>>
        >>> # Switch context (async)
        >>> async with ctx.aswitch("tenant-a"):
        ...     tenant = ctx.current()
    """

    def __init__(self, validate_registered: bool = True):
        """Initialize tenant context manager.

        Args:
            validate_registered: Whether to require tenants be registered (default: True).
                                 SECURITY: Default is True (fail-closed) to prevent
                                 unauthorized tenant access. Set to False only for
                                 development or when tenant validation is handled elsewhere.
        """
        self._tenants: Dict[str, TenantInfo] = {}
        self._validate_registered = validate_registered
        self._switch_count: int = 0
        self._active_switches: int = 0

    def register(
        self,
        tenant_id: str,
        name: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        active: bool = True,
    ) -> TenantInfo:
        """Register a tenant.

        Args:
            tenant_id: Unique tenant identifier
            name: Human-readable name (optional)
            metadata: Additional metadata (optional)
            active: Whether tenant is active (default: True)

        Returns:
            TenantInfo for the registered tenant

        Raises:
            ValueError: If tenant_id is invalid or already registered
        """
        if not tenant_id or not isinstance(tenant_id, str):
            raise ValueError("tenant_id must be a non-empty string")
        if tenant_id in self._tenants:
            raise ValueError(f"Tenant '{tenant_id}' is already registered")

        info = TenantInfo(
            tenant_id=tenant_id,
            name=name,
            active=active,
            metadata=metadata or {},
        )
        self._tenants[tenant_id] = info
        logger.debug("Registered tenant '%s' (%s)", tenant_id, name)
        return info

    def unregister(self, tenant_id: str) -> None:
        """Unregister a tenant.

        Args:
            tenant_id: Tenant ID to unregister

        Raises:
            ValueError: If tenant not registered or currently active
        """
        if tenant_id not in self._tenants:
            raise ValueError(f"Tenant '{tenant_id}' is not registered")

        current = self.current()
        if current and current.tenant_id == tenant_id:
            raise ValueError(
                f"Cannot unregister tenant '{tenant_id}' while it is active"
            )

        del self._tenants[tenant_id]
        logger.debug("Unregistered tenant '%s'", tenant_id)

    def get(self, tenant_id: str) -> Optional[TenantInfo]:
        """Get tenant info by ID.

        Args:
            tenant_id: Tenant ID to look up

        Returns:
            TenantInfo if found, None otherwise
        """
        return self._tenants.get(tenant_id)

    def list_tenants(self) -> List[TenantInfo]:
        """List all registered tenants.

        Returns:
            List of TenantInfo for all registered tenants
        """
        return list(self._tenants.values())

    def current(self) -> Optional[TenantInfo]:
        """Get the current tenant from context.

        Returns:
            Current TenantInfo, or None if no context is set
        """
        return _current_tenant.get()

    def require(self) -> TenantInfo:
        """Get current tenant or raise error.

        Returns:
            Current TenantInfo

        Raises:
            TenantContextError: If no tenant context is active
        """
        tenant = self.current()
        if tenant is None:
            raise TenantContextError(
                "No tenant context is active. "
                "Use 'with tenant_context.switch(tenant_id):' to set context."
            )
        return tenant

    @contextmanager
    def switch(self, tenant_id: str):
        """Synchronous context manager for switching tenant.

        Args:
            tenant_id: Tenant ID to switch to

        Yields:
            TenantInfo for the active tenant

        Raises:
            TenantNotFoundError: If tenant not registered (when validation enabled)
            TenantInactiveError: If tenant is inactive
        """
        tenant = self._resolve_tenant(tenant_id)

        previous = _current_tenant.get()
        token = _current_tenant.set(tenant)
        self._switch_count += 1
        self._active_switches += 1

        logger.debug(
            "Switched to tenant '%s' (previous: %s)",
            tenant_id,
            previous.tenant_id if previous else None,
        )

        try:
            yield tenant
        finally:
            _current_tenant.reset(token)
            self._active_switches -= 1
            logger.debug(
                "Restored tenant context to '%s'",
                previous.tenant_id if previous else None,
            )

    @asynccontextmanager
    async def aswitch(self, tenant_id: str):
        """Asynchronous context manager for switching tenant.

        Same semantics as switch() but for async code.

        Args:
            tenant_id: Tenant ID to switch to

        Yields:
            TenantInfo for the active tenant
        """
        tenant = self._resolve_tenant(tenant_id)

        previous = _current_tenant.get()
        token = _current_tenant.set(tenant)
        self._switch_count += 1
        self._active_switches += 1

        logger.debug(
            "Async switched to tenant '%s' (previous: %s)",
            tenant_id,
            previous.tenant_id if previous else None,
        )

        try:
            yield tenant
        finally:
            _current_tenant.reset(token)
            self._active_switches -= 1
            logger.debug(
                "Async restored tenant context to '%s'",
                previous.tenant_id if previous else None,
            )

    def _resolve_tenant(self, tenant_id: str) -> TenantInfo:
        """Resolve tenant ID to TenantInfo.

        Args:
            tenant_id: Tenant ID to resolve

        Returns:
            TenantInfo for the tenant

        Raises:
            TenantNotFoundError: If tenant not registered
            TenantInactiveError: If tenant is inactive
        """
        if self._validate_registered:
            if tenant_id not in self._tenants:
                available = list(self._tenants.keys())
                raise TenantNotFoundError(
                    tenant_id=tenant_id,
                    available=available,
                )

            tenant = self._tenants[tenant_id]
            if not tenant.active:
                raise TenantInactiveError(tenant_id=tenant_id)

            return tenant
        else:
            # Create ad-hoc tenant info without registration
            return TenantInfo(tenant_id=tenant_id)

    def deactivate(self, tenant_id: str) -> None:
        """Deactivate a tenant (prevents context switching).

        Args:
            tenant_id: Tenant ID to deactivate

        Raises:
            ValueError: If tenant not registered
        """
        if tenant_id not in self._tenants:
            raise ValueError(f"Tenant '{tenant_id}' is not registered")
        self._tenants[tenant_id].active = False
        logger.debug("Deactivated tenant '%s'", tenant_id)

    def activate(self, tenant_id: str) -> None:
        """Reactivate a deactivated tenant.

        Args:
            tenant_id: Tenant ID to activate

        Raises:
            ValueError: If tenant not registered
        """
        if tenant_id not in self._tenants:
            raise ValueError(f"Tenant '{tenant_id}' is not registered")
        self._tenants[tenant_id].active = True
        logger.debug("Activated tenant '%s'", tenant_id)

    def get_stats(self) -> Dict[str, Any]:
        """Get context switching statistics.

        Returns:
            Dictionary with statistics
        """
        return {
            "total_tenants": len(self._tenants),
            "active_tenants": sum(1 for t in self._tenants.values() if t.active),
            "total_switches": self._switch_count,
            "active_switches": self._active_switches,
            "current_tenant": (self.current().tenant_id if self.current() else None),
        }


# Module-level helper functions


def get_current_tenant() -> Optional[TenantInfo]:
    """Get the current tenant from context.

    Returns:
        Current TenantInfo, or None if no context is set
    """
    return _current_tenant.get()


def get_current_tenant_id() -> Optional[str]:
    """Get the current tenant ID from context.

    Returns:
        Current tenant ID, or None if no context is set
    """
    tenant = _current_tenant.get()
    return tenant.tenant_id if tenant else None


def require_tenant() -> TenantInfo:
    """Get current tenant or raise error.

    Returns:
        Current TenantInfo

    Raises:
        TenantContextError: If no tenant context is active
    """
    tenant = _current_tenant.get()
    if tenant is None:
        raise TenantContextError("No tenant context is active")
    return tenant

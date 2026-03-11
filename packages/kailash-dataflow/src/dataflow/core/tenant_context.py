"""Runtime tenant context switching for multi-tenant DataFlow applications.

Provides async-safe context managers for switching between tenants,
with automatic data isolation and connection management.

TODO-155: Context Switching Capabilities
"""

import logging
import time
from contextlib import asynccontextmanager, contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from .engine import DataFlow

logger = logging.getLogger("dataflow.tenant_context")

# Thread/async-safe context variable for current tenant
_current_tenant: ContextVar[Optional[str]] = ContextVar("_current_tenant", default=None)


@dataclass
class TenantInfo:
    """Information about a registered tenant.

    Attributes:
        tenant_id: Unique identifier for the tenant.
        name: Human-readable name for the tenant.
        metadata: Additional key-value metadata for the tenant.
        created_at: Unix timestamp when the tenant was registered.
        active: Whether the tenant is active and can be switched to.
    """

    tenant_id: str
    name: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    active: bool = True


class TenantContextSwitch:
    """Runtime tenant context switching for DataFlow instances.

    Provides sync and async context managers for safely switching
    between tenant contexts with guaranteed isolation.

    The context switching mechanism uses Python's contextvars module,
    which provides automatic context isolation for both threads and
    async code. This ensures that:
    - Each request gets its own tenant context
    - Nested switches are properly tracked and restored
    - Async code running concurrently maintains separate contexts

    Example:
        db = DataFlow("postgresql://...", multi_tenant=True)
        ctx = db.tenant_context

        # Register tenants
        ctx.register_tenant("tenant-a", "Tenant A")
        ctx.register_tenant("tenant-b", "Tenant B")

        # Context switching
        with ctx.switch("tenant-a"):
            # All operations isolated to tenant-a
            workflow = db.create_workflow("ops")
            db.add_node(workflow, "User", "Create", "create", {...})
            results, _ = db.execute_workflow(workflow)

        # Or async:
        async with ctx.aswitch("tenant-b"):
            # All operations isolated to tenant-b
            ...

    Attributes:
        dataflow_instance: The DataFlow instance this context switch is bound to.
    """

    def __init__(self, dataflow_instance: "DataFlow"):
        """Initialize the tenant context switch.

        Args:
            dataflow_instance: The DataFlow instance to bind to.
        """
        self._dataflow = dataflow_instance
        self._tenants: Dict[str, TenantInfo] = {}
        self._switch_count: int = 0
        self._active_switches: int = 0

    @property
    def dataflow_instance(self) -> "DataFlow":
        """Get the bound DataFlow instance."""
        return self._dataflow

    def register_tenant(
        self, tenant_id: str, name: str, metadata: Optional[Dict[str, Any]] = None
    ) -> TenantInfo:
        """Register a tenant for context switching.

        Args:
            tenant_id: Unique identifier for the tenant. Must be a non-empty string.
            name: Human-readable name for the tenant.
            metadata: Optional dictionary of additional metadata.

        Returns:
            TenantInfo object for the registered tenant.

        Raises:
            ValueError: If tenant_id is invalid or already registered.

        Example:
            >>> ctx = db.tenant_context
            >>> tenant = ctx.register_tenant("acme", "Acme Corporation")
            >>> print(tenant.tenant_id)  # "acme"
        """
        if not tenant_id or not isinstance(tenant_id, str):
            raise ValueError("tenant_id must be a non-empty string")
        if tenant_id in self._tenants:
            raise ValueError(f"Tenant '{tenant_id}' is already registered")

        info = TenantInfo(
            tenant_id=tenant_id,
            name=name,
            metadata=metadata or {},
        )
        self._tenants[tenant_id] = info
        logger.debug("Registered tenant '%s' (%s)", tenant_id, name)
        return info

    def unregister_tenant(self, tenant_id: str) -> None:
        """Unregister a tenant.

        Args:
            tenant_id: The tenant ID to unregister.

        Raises:
            ValueError: If tenant is not registered or is currently active.

        Example:
            >>> ctx.unregister_tenant("acme")
        """
        if tenant_id not in self._tenants:
            raise ValueError(f"Tenant '{tenant_id}' is not registered")
        current = self.get_current_tenant()
        if current == tenant_id:
            raise ValueError(
                f"Cannot unregister tenant '{tenant_id}' while it is the active context"
            )
        del self._tenants[tenant_id]
        logger.debug("Unregistered tenant '%s'", tenant_id)

    def get_tenant(self, tenant_id: str) -> Optional[TenantInfo]:
        """Get tenant info by ID.

        Args:
            tenant_id: The tenant ID to look up.

        Returns:
            TenantInfo if found, None otherwise.
        """
        return self._tenants.get(tenant_id)

    def list_tenants(self) -> List[TenantInfo]:
        """List all registered tenants.

        Returns:
            List of TenantInfo objects for all registered tenants.
        """
        return list(self._tenants.values())

    def get_current_tenant(self) -> Optional[str]:
        """Get the current tenant ID from context.

        Returns:
            The current tenant ID, or None if no tenant context is active.
        """
        return _current_tenant.get()

    @contextmanager
    def switch(self, tenant_id: str):
        """Synchronous context manager for switching tenant context.

        This context manager ensures that:
        - The tenant context is set for the duration of the block
        - The previous context is restored on exit (even on exception)
        - Nested switches are properly handled

        Args:
            tenant_id: The tenant to switch to.

        Yields:
            TenantInfo for the active tenant.

        Raises:
            ValueError: If tenant not registered or not active.

        Example:
            >>> with ctx.switch("tenant-a"):
            ...     # All operations here are in tenant-a context
            ...     user = db.express.create("User", {"name": "Alice"})
        """
        if tenant_id not in self._tenants:
            available = list(self._tenants.keys())
            raise ValueError(
                f"Tenant '{tenant_id}' is not registered. "
                f"Available tenants: {available}. "
                f"Use register_tenant() to register this tenant first."
            )
        tenant = self._tenants[tenant_id]
        if not tenant.active:
            raise ValueError(
                f"Tenant '{tenant_id}' is not active. "
                f"Use activate_tenant() to reactivate it."
            )

        previous = _current_tenant.get()
        token = _current_tenant.set(tenant_id)
        self._switch_count += 1
        self._active_switches += 1

        logger.debug("Switched to tenant '%s' (previous: %s)", tenant_id, previous)

        try:
            yield tenant
        finally:
            _current_tenant.reset(token)
            self._active_switches -= 1
            logger.debug("Restored tenant context to '%s'", previous)

    @asynccontextmanager
    async def aswitch(self, tenant_id: str):
        """Async context manager for switching tenant context.

        Same semantics as switch() but for async code. The contextvars
        module automatically propagates context to async tasks.

        Args:
            tenant_id: The tenant to switch to.

        Yields:
            TenantInfo for the active tenant.

        Raises:
            ValueError: If tenant not registered or not active.

        Example:
            >>> async with ctx.aswitch("tenant-b"):
            ...     # All async operations here are in tenant-b context
            ...     user = await some_async_operation()
        """
        if tenant_id not in self._tenants:
            available = list(self._tenants.keys())
            raise ValueError(
                f"Tenant '{tenant_id}' is not registered. "
                f"Available tenants: {available}. "
                f"Use register_tenant() to register this tenant first."
            )
        tenant = self._tenants[tenant_id]
        if not tenant.active:
            raise ValueError(
                f"Tenant '{tenant_id}' is not active. "
                f"Use activate_tenant() to reactivate it."
            )

        previous = _current_tenant.get()
        token = _current_tenant.set(tenant_id)
        self._switch_count += 1
        self._active_switches += 1

        logger.debug(
            "Async switched to tenant '%s' (previous: %s)", tenant_id, previous
        )

        try:
            yield tenant
        finally:
            _current_tenant.reset(token)
            self._active_switches -= 1
            logger.debug("Async restored tenant context to '%s'", previous)

    def require_tenant(self) -> str:
        """Get current tenant or raise error if none set.

        This is useful for operations that must run within a tenant context.

        Returns:
            The current tenant ID.

        Raises:
            RuntimeError: If no tenant context is active.

        Example:
            >>> tenant_id = ctx.require_tenant()  # Raises if no context
            >>> print(f"Operating as tenant: {tenant_id}")
        """
        current = self.get_current_tenant()
        if current is None:
            raise RuntimeError(
                "No tenant context is active. "
                "Use 'with db.tenant_context.switch(tenant_id):' to set a tenant context."
            )
        return current

    def deactivate_tenant(self, tenant_id: str) -> None:
        """Deactivate a tenant (prevents context switching to it).

        A deactivated tenant remains registered but cannot be switched to.
        This is useful for temporarily disabling tenant access without
        losing registration data.

        Args:
            tenant_id: The tenant ID to deactivate.

        Raises:
            ValueError: If tenant is not registered.

        Example:
            >>> ctx.deactivate_tenant("tenant-a")
            >>> # Now switching to tenant-a will raise ValueError
        """
        if tenant_id not in self._tenants:
            raise ValueError(f"Tenant '{tenant_id}' is not registered")
        self._tenants[tenant_id].active = False
        logger.debug("Deactivated tenant '%s'", tenant_id)

    def activate_tenant(self, tenant_id: str) -> None:
        """Reactivate a previously deactivated tenant.

        Args:
            tenant_id: The tenant ID to activate.

        Raises:
            ValueError: If tenant is not registered.

        Example:
            >>> ctx.activate_tenant("tenant-a")
            >>> # Now switching to tenant-a works again
        """
        if tenant_id not in self._tenants:
            raise ValueError(f"Tenant '{tenant_id}' is not registered")
        self._tenants[tenant_id].active = True
        logger.debug("Activated tenant '%s'", tenant_id)

    def get_stats(self) -> Dict[str, Any]:
        """Get context switching statistics.

        Returns:
            Dictionary containing:
            - total_tenants: Number of registered tenants
            - active_tenants: Number of active (switchable) tenants
            - total_switches: Total number of context switches performed
            - active_switches: Number of currently active switches (nested depth)
            - current_tenant: The current tenant ID or None

        Example:
            >>> stats = ctx.get_stats()
            >>> print(f"Total switches: {stats['total_switches']}")
        """
        return {
            "total_tenants": len(self._tenants),
            "active_tenants": sum(1 for t in self._tenants.values() if t.active),
            "total_switches": self._switch_count,
            "active_switches": self._active_switches,
            "current_tenant": self.get_current_tenant(),
        }

    def is_tenant_registered(self, tenant_id: str) -> bool:
        """Check if a tenant is registered.

        Args:
            tenant_id: The tenant ID to check.

        Returns:
            True if tenant is registered, False otherwise.
        """
        return tenant_id in self._tenants

    def is_tenant_active(self, tenant_id: str) -> bool:
        """Check if a tenant is active.

        Args:
            tenant_id: The tenant ID to check.

        Returns:
            True if tenant is registered and active, False otherwise.
        """
        tenant = self._tenants.get(tenant_id)
        return tenant is not None and tenant.active


# Helper function for global access to current tenant
def get_current_tenant_id() -> Optional[str]:
    """Get the current tenant ID from the context variable.

    This is a module-level helper for code that needs to check
    the current tenant context without a TenantContextSwitch instance.

    Returns:
        The current tenant ID or None if no context is set.
    """
    return _current_tenant.get()

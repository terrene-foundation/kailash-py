"""
RBAC authorization for hooks system.

Implements role-based access control to prevent unauthorized hook registration
and execution. Addresses Finding #1 (CRITICAL): No Hook Registration Authorization.

Security Features:
- HookPermission enum for granular permission control
- HookRole with configurable permission sets
- HookPrincipal for authenticated identity management
- AuthorizedHookManager with RBAC enforcement
"""

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Awaitable, Callable, Optional, Set

from ..manager import HookManager
from ..protocol import HookHandler
from ..types import HookContext, HookEvent, HookPriority, HookResult

logger = logging.getLogger(__name__)


class HookPermission(Enum):
    """Granular permissions for hook operations."""

    REGISTER_HOOK = "register_hook"
    UNREGISTER_HOOK = "unregister_hook"
    TRIGGER_HOOK = "trigger_hook"
    DISCOVER_HOOKS = "discover_hooks"
    VIEW_STATS = "view_stats"
    MODIFY_PRIORITY = "modify_priority"


@dataclass(frozen=True)
class HookRole:
    """
    Role with permission set for hook operations.

    Examples:
        >>> # Admin role (all permissions)
        >>> admin = HookRole(
        ...     name="admin",
        ...     permissions={
        ...         HookPermission.REGISTER_HOOK,
        ...         HookPermission.UNREGISTER_HOOK,
        ...         HookPermission.TRIGGER_HOOK,
        ...         HookPermission.DISCOVER_HOOKS,
        ...         HookPermission.VIEW_STATS,
        ...         HookPermission.MODIFY_PRIORITY,
        ...     }
        ... )
        >>>
        >>> # Developer role (limited)
        >>> developer = HookRole(
        ...     name="developer",
        ...     permissions={
        ...         HookPermission.REGISTER_HOOK,
        ...         HookPermission.VIEW_STATS,
        ...     }
        ... )
        >>>
        >>> # Read-only role
        >>> viewer = HookRole(
        ...     name="viewer",
        ...     permissions={HookPermission.VIEW_STATS}
        ... )
    """

    name: str
    permissions: frozenset[HookPermission] = field(default_factory=frozenset)
    description: Optional[str] = None

    def has_permission(self, permission: HookPermission) -> bool:
        """Check if role has specific permission."""
        return permission in self.permissions

    def grant(self, permission: HookPermission) -> "HookRole":
        """
        Grant permission to role (returns new role instance).

        Note: HookRole is immutable, so this returns a new instance
        with the added permission.
        """
        return HookRole(
            name=self.name,
            permissions=self.permissions | {permission},
            description=self.description,
        )

    def revoke(self, permission: HookPermission) -> "HookRole":
        """
        Revoke permission from role (returns new role instance).

        Note: HookRole is immutable, so this returns a new instance
        with the removed permission.
        """
        return HookRole(
            name=self.name,
            permissions=self.permissions - {permission},
            description=self.description,
        )


@dataclass
class HookPrincipal:
    """
    Authenticated identity for hook operations.

    Represents a user or service with assigned roles.

    Examples:
        >>> # Create admin user
        >>> admin_user = HookPrincipal(
        ...     id="user-123",
        ...     name="Alice Admin",
        ...     roles={admin_role},
        ...     metadata={"department": "engineering"}
        ... )
        >>>
        >>> # Create service principal
        >>> monitoring_service = HookPrincipal(
        ...     id="service-metrics",
        ...     name="Prometheus Scraper",
        ...     roles={viewer_role},
        ...     metadata={"service": "prometheus", "namespace": "monitoring"}
        ... )
    """

    id: str
    name: str
    roles: Set[HookRole] = field(default_factory=set)
    metadata: dict[str, Any] = field(default_factory=dict)

    def has_permission(self, permission: HookPermission) -> bool:
        """
        Check if principal has permission through any role.

        Args:
            permission: Permission to check

        Returns:
            True if any role grants this permission
        """
        return any(role.has_permission(permission) for role in self.roles)

    def add_role(self, role: HookRole) -> None:
        """Add role to principal."""
        self.roles.add(role)

    def remove_role(self, role: HookRole) -> None:
        """Remove role from principal."""
        self.roles.discard(role)


class AuthorizedHookManager(HookManager):
    """
    Hook manager with RBAC authorization.

    Extends HookManager with permission checks for all operations.
    Prevents unauthorized hook registration, execution, and discovery.

    Example:
        >>> from kaizen.core.autonomy.hooks.security import (
        ...     AuthorizedHookManager,
        ...     HookPrincipal,
        ...     HookRole,
        ...     HookPermission
        ... )
        >>>
        >>> # Define roles
        >>> admin_role = HookRole(
        ...     name="admin",
        ...     permissions={
        ...         HookPermission.REGISTER_HOOK,
        ...         HookPermission.UNREGISTER_HOOK,
        ...         HookPermission.TRIGGER_HOOK,
        ...         HookPermission.DISCOVER_HOOKS,
        ...     }
        ... )
        >>>
        >>> # Create principal
        >>> admin_user = HookPrincipal(
        ...     id="user-123",
        ...     name="Admin User",
        ...     roles={admin_role}
        ... )
        >>>
        >>> # Create authorized manager
        >>> manager = AuthorizedHookManager()
        >>>
        >>> # Register hook with authorization
        >>> manager.register(
        ...     event_type=HookEvent.PRE_AGENT_LOOP,
        ...     handler=my_hook,
        ...     priority=HookPriority.NORMAL,
        ...     principal=admin_user  # REQUIRED
        ... )
    """

    def __init__(self, require_authorization: bool = True):
        """
        Initialize authorized hook manager.

        Args:
            require_authorization: If True, all operations require principal
                                  If False, behaves like HookManager (for migration)
        """
        super().__init__()
        self.require_authorization = require_authorization
        self._audit_log: list[dict[str, Any]] = []

    def _check_permission(
        self,
        principal: Optional[HookPrincipal],
        permission: HookPermission,
        operation: str,
    ) -> None:
        """
        Check if principal has permission for operation.

        Args:
            principal: Principal attempting operation (None if not provided)
            permission: Required permission
            operation: Operation name (for logging)

        Raises:
            PermissionError: If authorization required and principal lacks permission
        """
        if not self.require_authorization:
            return

        if principal is None:
            self._audit_log.append(
                {
                    "operation": operation,
                    "permission": permission.value,
                    "principal": None,
                    "allowed": False,
                    "reason": "No principal provided",
                }
            )
            raise PermissionError(
                f"Authorization required for {operation} "
                f"(permission: {permission.value})"
            )

        if not principal.has_permission(permission):
            self._audit_log.append(
                {
                    "operation": operation,
                    "permission": permission.value,
                    "principal": principal.id,
                    "allowed": False,
                    "reason": "Insufficient permissions",
                }
            )
            raise PermissionError(
                f"Principal {principal.id} lacks permission {permission.value} "
                f"for operation {operation}"
            )

        # Audit successful authorization
        self._audit_log.append(
            {
                "operation": operation,
                "permission": permission.value,
                "principal": principal.id,
                "allowed": True,
            }
        )
        logger.info(
            f"Authorized {operation} for principal {principal.id} "
            f"(permission: {permission.value})"
        )

    def register(
        self,
        event_type: HookEvent | str,
        handler: HookHandler | Callable[[HookContext], Awaitable[HookResult]],
        priority: HookPriority = HookPriority.NORMAL,
        principal: Optional[HookPrincipal] = None,
    ) -> None:
        """
        Register hook with authorization check.

        Args:
            event_type: Event to trigger hook on
            handler: Hook handler
            priority: Execution priority
            principal: Principal attempting registration (REQUIRED if authorization enabled)

        Raises:
            PermissionError: If principal lacks REGISTER_HOOK permission
            ValueError: If event_type is invalid
        """
        self._check_permission(
            principal, HookPermission.REGISTER_HOOK, f"register_hook({event_type})"
        )

        # Delegate to parent
        super().register(event_type, handler, priority)

    def unregister(
        self,
        event_type: HookEvent | str,
        handler: HookHandler | None = None,
        principal: Optional[HookPrincipal] = None,
    ) -> int:
        """
        Unregister hook with authorization check.

        Args:
            event_type: Event type to unregister from
            handler: Specific handler to remove (None = remove all)
            principal: Principal attempting unregistration

        Returns:
            Number of hooks removed

        Raises:
            PermissionError: If principal lacks UNREGISTER_HOOK permission
        """
        self._check_permission(
            principal, HookPermission.UNREGISTER_HOOK, f"unregister_hook({event_type})"
        )

        return super().unregister(event_type, handler)

    async def trigger(
        self,
        event_type: HookEvent | str,
        agent_id: str,
        data: dict[str, Any],
        timeout: float = 0.5,
        metadata: dict[str, Any] | None = None,
        trace_id: str | None = None,
        principal: Optional[HookPrincipal] = None,
    ) -> list[HookResult]:
        """
        Trigger hooks with authorization check.

        Args:
            event_type: Event that occurred
            agent_id: ID of agent triggering event
            data: Event-specific data
            timeout: Max execution time per hook
            metadata: Optional metadata
            trace_id: Distributed tracing ID
            principal: Principal attempting trigger

        Returns:
            List of HookResult from executed hooks

        Raises:
            PermissionError: If principal lacks TRIGGER_HOOK permission
        """
        self._check_permission(
            principal, HookPermission.TRIGGER_HOOK, f"trigger_hook({event_type})"
        )

        return await super().trigger(
            event_type, agent_id, data, timeout, metadata, trace_id
        )

    async def discover_filesystem_hooks(
        self,
        hooks_dir,
        principal: Optional[HookPrincipal] = None,
    ) -> int:
        """
        Discover filesystem hooks with authorization check.

        Args:
            hooks_dir: Directory containing hook files
            principal: Principal attempting discovery

        Returns:
            Number of hooks discovered

        Raises:
            PermissionError: If principal lacks DISCOVER_HOOKS permission
        """
        self._check_permission(
            principal, HookPermission.DISCOVER_HOOKS, "discover_filesystem_hooks"
        )

        return await super().discover_filesystem_hooks(hooks_dir)

    def get_stats(
        self, principal: Optional[HookPrincipal] = None
    ) -> dict[str, dict[str, Any]]:
        """
        Get hook statistics with authorization check.

        Args:
            principal: Principal requesting stats

        Returns:
            Hook performance statistics

        Raises:
            PermissionError: If principal lacks VIEW_STATS permission
        """
        self._check_permission(principal, HookPermission.VIEW_STATS, "get_stats")

        return super().get_stats()

    def get_audit_log(
        self, principal: Optional[HookPrincipal] = None
    ) -> list[dict[str, Any]]:
        """
        Get audit log with authorization check.

        Args:
            principal: Principal requesting audit log

        Returns:
            List of audit log entries

        Raises:
            PermissionError: If principal lacks VIEW_STATS permission
        """
        self._check_permission(principal, HookPermission.VIEW_STATS, "get_audit_log")

        return self._audit_log.copy()


# Predefined roles for common use cases
ADMIN_ROLE = HookRole(
    name="admin",
    permissions=frozenset(
        {
            HookPermission.REGISTER_HOOK,
            HookPermission.UNREGISTER_HOOK,
            HookPermission.TRIGGER_HOOK,
            HookPermission.DISCOVER_HOOKS,
            HookPermission.VIEW_STATS,
            HookPermission.MODIFY_PRIORITY,
        }
    ),
    description="Full administrative access to hook system",
)

DEVELOPER_ROLE = HookRole(
    name="developer",
    permissions=frozenset(
        {
            HookPermission.REGISTER_HOOK,
            HookPermission.TRIGGER_HOOK,
            HookPermission.VIEW_STATS,
        }
    ),
    description="Development access (register, trigger, view)",
)

VIEWER_ROLE = HookRole(
    name="viewer",
    permissions=frozenset({HookPermission.VIEW_STATS}),
    description="Read-only access to hook statistics",
)

SERVICE_ROLE = HookRole(
    name="service",
    permissions=frozenset(
        {
            HookPermission.TRIGGER_HOOK,
            HookPermission.VIEW_STATS,
        }
    ),
    description="Service account access (trigger, view)",
)


__all__ = [
    "HookPermission",
    "HookRole",
    "HookPrincipal",
    "AuthorizedHookManager",
    "ADMIN_ROLE",
    "DEVELOPER_ROLE",
    "VIEWER_ROLE",
    "SERVICE_ROLE",
]

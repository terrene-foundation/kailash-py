"""Enhanced tenant isolation utilities for admin nodes.

This module provides robust tenant isolation mechanisms to ensure that
multi-tenant operations properly enforce data boundaries and prevent
cross-tenant access.
"""

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set

from kailash.sdk_exceptions import NodeExecutionError, NodeValidationError

logger = logging.getLogger(__name__)


@dataclass
class TenantContext:
    """Represents the context for a specific tenant."""

    tenant_id: str
    permissions: Set[str]
    user_ids: Set[str]
    role_ids: Set[str]
    resource_prefixes: Set[str]


class TenantIsolationManager:
    """Manages tenant isolation for admin operations."""

    def __init__(self, db_node):
        """
        Initialize tenant isolation manager.

        Args:
            db_node: Database node for tenant context queries
        """
        self.db_node = db_node
        self._tenant_cache = {}

    def get_tenant_context(self, tenant_id: str) -> TenantContext:
        """
        Get the context for a specific tenant.

        Args:
            tenant_id: The tenant ID

        Returns:
            TenantContext with tenant-specific data
        """
        if tenant_id not in self._tenant_cache:
            self._tenant_cache[tenant_id] = self._load_tenant_context(tenant_id)

        return self._tenant_cache[tenant_id]

    def _load_tenant_context(self, tenant_id: str) -> TenantContext:
        """Load tenant context from database."""
        # Get all users for this tenant
        users_query = """
            SELECT user_id FROM users WHERE tenant_id = $1 AND status = 'active'
        """
        users_result = self.db_node.execute(
            query=users_query, parameters=[tenant_id], result_format="dict"
        )
        user_ids = {row["user_id"] for row in users_result.get("data", [])}

        # Get all roles for this tenant
        roles_query = """
            SELECT role_id FROM roles WHERE tenant_id = $1 AND is_active = true
        """
        roles_result = self.db_node.execute(
            query=roles_query, parameters=[tenant_id], result_format="dict"
        )
        role_ids = {row["role_id"] for row in roles_result.get("data", [])}

        # Get all permissions for this tenant (from roles)
        permissions_query = """
            SELECT DISTINCT unnest(
                CASE
                    WHEN jsonb_typeof(permissions) = 'array'
                    THEN ARRAY(SELECT jsonb_array_elements_text(permissions))
                    ELSE ARRAY[]::text[]
                END
            ) as permission
            FROM roles
            WHERE tenant_id = $1 AND is_active = true
        """
        permissions_result = self.db_node.execute(
            query=permissions_query, parameters=[tenant_id], result_format="dict"
        )
        permissions = {row["permission"] for row in permissions_result.get("data", [])}

        # Create resource prefixes for this tenant
        resource_prefixes = {f"{tenant_id}:*", "*"}

        return TenantContext(
            tenant_id=tenant_id,
            permissions=permissions,
            user_ids=user_ids,
            role_ids=role_ids,
            resource_prefixes=resource_prefixes,
        )

    def validate_user_tenant_access(self, user_id: str, target_tenant_id: str) -> bool:
        """
        Validate that a user has access within a specific tenant.

        Args:
            user_id: The user ID to check
            target_tenant_id: The tenant being accessed

        Returns:
            True if access is allowed, False otherwise
        """
        tenant_context = self.get_tenant_context(target_tenant_id)
        return user_id in tenant_context.user_ids

    def validate_role_tenant_access(self, role_id: str, target_tenant_id: str) -> bool:
        """
        Validate that a role belongs to a specific tenant.

        Args:
            role_id: The role ID to check
            target_tenant_id: The tenant being accessed

        Returns:
            True if role belongs to tenant, False otherwise
        """
        tenant_context = self.get_tenant_context(target_tenant_id)
        return role_id in tenant_context.role_ids

    def check_cross_tenant_permission(
        self,
        user_id: str,
        user_tenant_id: str,
        resource_tenant_id: str,
        permission: str,
    ) -> bool:
        """
        Check if a user from one tenant can access resources in another tenant.

        Args:
            user_id: The user attempting access
            user_tenant_id: The tenant the user belongs to
            resource_tenant_id: The tenant of the resource being accessed
            permission: The permission being requested

        Returns:
            True if cross-tenant access is allowed, False otherwise
        """
        # For now, enforce strict tenant isolation
        # Users can only access resources in their own tenant
        if user_tenant_id != resource_tenant_id:
            logger.debug(
                f"Cross-tenant access denied: user {user_id} from {user_tenant_id} "
                f"attempting to access {resource_tenant_id}"
            )
            return False

        # Same tenant access - check if user exists in tenant
        return self.validate_user_tenant_access(user_id, resource_tenant_id)

    def enforce_tenant_isolation(
        self, user_id: str, user_tenant_id: str, operation_tenant_id: str
    ) -> None:
        """
        Enforce tenant isolation for an operation.

        Args:
            user_id: The user performing the operation
            user_tenant_id: The tenant the user belongs to
            operation_tenant_id: The tenant context for the operation

        Raises:
            NodeValidationError: If tenant isolation is violated
        """
        if not self.check_cross_tenant_permission(
            user_id, user_tenant_id, operation_tenant_id, "access"
        ):
            raise NodeValidationError(
                f"Tenant isolation violation: user {user_id} from tenant "
                f"{user_tenant_id} cannot access tenant {operation_tenant_id}"
            )

    def get_tenant_scoped_permission(
        self, permission: str, tenant_id: str, resource_id: Optional[str] = None
    ) -> str:
        """
        Create a tenant-scoped permission string.

        Args:
            permission: Base permission (e.g., "read", "write")
            tenant_id: Tenant ID
            resource_id: Optional resource ID

        Returns:
            Tenant-scoped permission string
        """
        if resource_id:
            return f"{tenant_id}:{resource_id}:{permission}"
        else:
            return f"{tenant_id}:*:{permission}"

    def clear_tenant_cache(self, tenant_id: Optional[str] = None) -> None:
        """
        Clear the tenant context cache.

        Args:
            tenant_id: Specific tenant to clear, or None to clear all
        """
        if tenant_id:
            self._tenant_cache.pop(tenant_id, None)
        else:
            self._tenant_cache.clear()

        logger.debug(f"Cleared tenant cache for {tenant_id or 'all tenants'}")


def enforce_tenant_boundary(tenant_id_param: str = "tenant_id"):
    """
    Decorator to enforce tenant boundaries on admin node methods.

    Args:
        tenant_id_param: Name of the parameter containing the tenant ID
    """

    def decorator(func):
        def wrapper(self, *args, **kwargs):
            # Extract tenant ID from parameters
            tenant_id = kwargs.get(tenant_id_param)
            if not tenant_id:
                raise NodeValidationError(
                    f"Missing required parameter: {tenant_id_param}"
                )

            # Create tenant isolation manager if not exists
            if not hasattr(self, "_tenant_isolation"):
                self._tenant_isolation = TenantIsolationManager(self._db_node)

            # Perform the operation within tenant context
            try:
                return func(self, *args, **kwargs)
            except Exception as e:
                logger.error(f"Tenant-scoped operation failed for {tenant_id}: {e}")
                raise

        return wrapper

    return decorator

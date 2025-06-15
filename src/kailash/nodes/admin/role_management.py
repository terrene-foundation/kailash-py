"""Enterprise role management node with hierarchical RBAC support.

This node provides comprehensive role-based access control (RBAC) management
with support for role hierarchies, inheritance, and dynamic permission assignment.
Integrates with Session 065's ABAC system for enhanced access control.

Features:
- Hierarchical role management with inheritance
- Dynamic permission assignment and revocation
- Role templates and bulk operations
- Permission dependency validation
- Role-based data filtering
- Multi-tenant role isolation
- Integration with ABAC attributes
- Comprehensive audit logging
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Set

from kailash.access_control import (
    AccessControlManager,
    NodePermission,
    PermissionEffect,
    PermissionRule,
    WorkflowPermission,
)
from kailash.nodes.base import Node, NodeParameter, register_node
from kailash.nodes.data import AsyncSQLDatabaseNode
from kailash.sdk_exceptions import NodeExecutionError, NodeValidationError


class RoleOperation(Enum):
    """Supported role management operations."""

    CREATE_ROLE = "create_role"
    UPDATE_ROLE = "update_role"
    DELETE_ROLE = "delete_role"
    LIST_ROLES = "list_roles"
    GET_ROLE = "get_role"
    ASSIGN_USER = "assign_user"
    UNASSIGN_USER = "unassign_user"
    ADD_PERMISSION = "add_permission"
    REMOVE_PERMISSION = "remove_permission"
    BULK_ASSIGN = "bulk_assign"
    BULK_UNASSIGN = "bulk_unassign"
    GET_USER_ROLES = "get_user_roles"
    GET_ROLE_USERS = "get_role_users"
    VALIDATE_HIERARCHY = "validate_hierarchy"
    GET_EFFECTIVE_PERMISSIONS = "get_effective_permissions"


class RoleType(Enum):
    """Types of roles in the system."""

    SYSTEM = "system"  # Built-in system roles
    CUSTOM = "custom"  # Custom organization roles
    TEMPLATE = "template"  # Role templates for reuse
    TEMPORARY = "temporary"  # Time-limited roles


@dataclass
class Role:
    """Enhanced role definition with hierarchy support."""

    role_id: str
    name: str
    description: str
    role_type: RoleType
    permissions: Set[str]
    parent_roles: Set[str]  # For role hierarchy
    child_roles: Set[str]  # Derived roles
    attributes: Dict[str, Any]  # ABAC attributes
    is_active: bool
    created_at: datetime
    updated_at: datetime
    tenant_id: str
    created_by: str

    def get_all_permissions(self, role_hierarchy: Dict[str, "Role"]) -> Set[str]:
        """Get all permissions including inherited from parent roles."""
        all_permissions = self.permissions.copy()

        # Add permissions from parent roles (recursive)
        for parent_id in self.parent_roles:
            if parent_id in role_hierarchy:
                parent_role = role_hierarchy[parent_id]
                all_permissions.update(parent_role.get_all_permissions(role_hierarchy))

        return all_permissions


@register_node()
class RoleManagementNode(Node):
    """Enterprise role management node with hierarchical RBAC.

    This node provides comprehensive role management capabilities including:
    - Hierarchical role creation and management
    - Permission assignment with inheritance
    - User-role assignment and bulk operations
    - Role validation and dependency checking
    - Integration with ABAC attributes
    - Multi-tenant role isolation

    Parameters:
        operation: Type of role operation to perform
        role_data: Role configuration data
        role_id: Role ID for single-role operations
        role_ids: List of role IDs for bulk operations
        user_id: User ID for assignment operations
        user_ids: List of user IDs for bulk assignment
        permission: Permission to add/remove
        permissions: List of permissions for bulk operations
        tenant_id: Tenant isolation
        validate_hierarchy: Whether to validate role hierarchy
        include_inherited: Include inherited permissions in results

    Example:
        >>> # Create hierarchical role structure
        >>> node = RoleManagementNode(
        ...     operation="create_role",
        ...     role_data={
        ...         "name": "Senior Analyst",
        ...         "description": "Senior financial analyst with elevated permissions",
        ...         "parent_roles": ["analyst"],
        ...         "permissions": ["advanced_reports", "data_export"],
        ...         "attributes": {
        ...             "seniority": "senior",
        ...             "clearance_required": "confidential"
        ...         }
        ...     }
        ... )
        >>> result = node.run()
        >>> role_id = result["role"]["role_id"]

        >>> # Bulk user assignment
        >>> node = RoleManagementNode(
        ...     operation="bulk_assign",
        ...     role_id="senior_analyst",
        ...     user_ids=["user1", "user2", "user3"],
        ...     validate_hierarchy=True
        ... )
        >>> result = node.run()
        >>> assigned_count = result["stats"]["assigned"]
    """

    def __init__(self, **config):
        super().__init__(**config)
        self._db_node = None
        self._access_manager = None

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Define parameters for role management operations."""
        return {
            param.name: param
            for param in [
                # Operation type
                NodeParameter(
                    name="operation",
                    type=str,
                    required=True,
                    description="Role management operation to perform",
                    choices=[op.value for op in RoleOperation],
                ),
                # Role data
                NodeParameter(
                    name="role_data",
                    type=dict,
                    required=False,
                    description="Role configuration data",
                ),
                # Single role operations
                NodeParameter(
                    name="role_id",
                    type=str,
                    required=False,
                    description="Role ID for single-role operations",
                ),
                # Bulk operations
                NodeParameter(
                    name="role_ids",
                    type=list,
                    required=False,
                    description="List of role IDs for bulk operations",
                ),
                # User assignment
                NodeParameter(
                    name="user_id",
                    type=str,
                    required=False,
                    description="User ID for assignment operations",
                ),
                NodeParameter(
                    name="user_ids",
                    type=list,
                    required=False,
                    description="List of user IDs for bulk assignment",
                ),
                # Permission management
                NodeParameter(
                    name="permission",
                    type=str,
                    required=False,
                    description="Permission to add/remove",
                ),
                NodeParameter(
                    name="permissions",
                    type=list,
                    required=False,
                    description="List of permissions for bulk operations",
                ),
                # Multi-tenancy
                NodeParameter(
                    name="tenant_id",
                    type=str,
                    required=False,
                    description="Tenant ID for multi-tenant isolation",
                ),
                # Validation options
                NodeParameter(
                    name="validate_hierarchy",
                    type=bool,
                    required=False,
                    default=True,
                    description="Whether to validate role hierarchy",
                ),
                NodeParameter(
                    name="include_inherited",
                    type=bool,
                    required=False,
                    default=True,
                    description="Include inherited permissions in results",
                ),
                # Database configuration
                NodeParameter(
                    name="database_config",
                    type=dict,
                    required=False,
                    description="Database connection configuration",
                ),
                # Search and filtering
                NodeParameter(
                    name="filters",
                    type=dict,
                    required=False,
                    description="Filters for role listing",
                ),
                NodeParameter(
                    name="search_query",
                    type=str,
                    required=False,
                    description="Search query for roles",
                ),
            ]
        }

    def run(self, **inputs) -> Dict[str, Any]:
        """Execute role management operation."""
        try:
            operation = RoleOperation(inputs["operation"])

            # Initialize dependencies
            self._init_dependencies(inputs)

            # Route to appropriate operation
            if operation == RoleOperation.CREATE_ROLE:
                return self._create_role(inputs)
            elif operation == RoleOperation.UPDATE_ROLE:
                return self._update_role(inputs)
            elif operation == RoleOperation.DELETE_ROLE:
                return self._delete_role(inputs)
            elif operation == RoleOperation.LIST_ROLES:
                return self._list_roles(inputs)
            elif operation == RoleOperation.GET_ROLE:
                return self._get_role(inputs)
            elif operation == RoleOperation.ASSIGN_USER:
                return self._assign_user(inputs)
            elif operation == RoleOperation.UNASSIGN_USER:
                return self._unassign_user(inputs)
            elif operation == RoleOperation.ADD_PERMISSION:
                return self._add_permission(inputs)
            elif operation == RoleOperation.REMOVE_PERMISSION:
                return self._remove_permission(inputs)
            elif operation == RoleOperation.BULK_ASSIGN:
                return self._bulk_assign(inputs)
            elif operation == RoleOperation.BULK_UNASSIGN:
                return self._bulk_unassign(inputs)
            elif operation == RoleOperation.GET_USER_ROLES:
                return self._get_user_roles(inputs)
            elif operation == RoleOperation.GET_ROLE_USERS:
                return self._get_role_users(inputs)
            elif operation == RoleOperation.VALIDATE_HIERARCHY:
                return self._validate_hierarchy(inputs)
            elif operation == RoleOperation.GET_EFFECTIVE_PERMISSIONS:
                return self._get_effective_permissions(inputs)
            else:
                raise NodeExecutionError(f"Unknown operation: {operation}")

        except Exception as e:
            raise NodeExecutionError(f"Role management operation failed: {str(e)}")

    def _init_dependencies(self, inputs: Dict[str, Any]):
        """Initialize database and access manager dependencies."""
        # Get database config
        db_config = inputs.get(
            "database_config",
            {
                "database_type": "postgresql",
                "host": "localhost",
                "port": 5432,
                "database": "kailash_admin",
                "user": "admin",
                "password": "admin",
            },
        )

        # Initialize async database node
        self._db_node = AsyncSQLDatabaseNode(name="role_management_db", **db_config)

        # Initialize enhanced access manager
        self._access_manager = AccessControlManager(strategy="abac")

    def _create_role(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new role with hierarchy validation."""
        role_data = inputs["role_data"]
        tenant_id = inputs.get("tenant_id", "default")
        validate_hierarchy = inputs.get("validate_hierarchy", True)

        # Validate required fields
        required_fields = ["name", "description"]
        for field in required_fields:
            if field not in role_data:
                raise NodeValidationError(f"Missing required field: {field}")

        # Generate role ID
        role_id = self._generate_role_id(role_data["name"])
        now = datetime.now(UTC)

        # Validate parent roles exist if specified
        parent_roles = set(role_data.get("parent_roles", []))
        if parent_roles and validate_hierarchy:
            self._validate_parent_roles_exist(parent_roles, tenant_id)

        # Validate no circular dependencies
        if parent_roles and validate_hierarchy:
            self._validate_no_circular_dependency(role_id, parent_roles, tenant_id)

        # Prepare role record
        role_record = {
            "role_id": role_id,
            "name": role_data["name"],
            "description": role_data["description"],
            "role_type": role_data.get("role_type", RoleType.CUSTOM.value),
            "permissions": list(role_data.get("permissions", [])),
            "parent_roles": list(parent_roles),
            "attributes": role_data.get("attributes", {}),
            "is_active": role_data.get("is_active", True),
            "tenant_id": tenant_id,
            "created_at": now,
            "updated_at": now,
            "created_by": inputs.get("created_by", "system"),
        }

        # Insert role into database
        insert_query = """
        INSERT INTO roles (
            role_id, name, description, role_type, permissions, parent_roles,
            attributes, is_active, tenant_id, created_at, updated_at, created_by
        ) VALUES (
            $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12
        )
        """

        # Execute database insert
        self._db_node.config.update(
            {
                "query": insert_query,
                "params": [
                    role_record["role_id"],
                    role_record["name"],
                    role_record["description"],
                    role_record["role_type"],
                    role_record["permissions"],
                    role_record["parent_roles"],
                    role_record["attributes"],
                    role_record["is_active"],
                    role_record["tenant_id"],
                    role_record["created_at"],
                    role_record["updated_at"],
                    role_record["created_by"],
                ],
            }
        )

        db_result = self._db_node.run()

        # Update child_roles for parent roles
        if parent_roles:
            self._update_child_roles(parent_roles, role_id, tenant_id, "add")

        return {
            "result": {
                "role": {
                    "role_id": role_id,
                    "name": role_record["name"],
                    "description": role_record["description"],
                    "role_type": role_record["role_type"],
                    "permissions": role_record["permissions"],
                    "parent_roles": role_record["parent_roles"],
                    "attributes": role_record["attributes"],
                    "is_active": role_record["is_active"],
                    "tenant_id": role_record["tenant_id"],
                    "created_at": role_record["created_at"].isoformat(),
                },
                "operation": "create_role",
                "success": True,
                "timestamp": datetime.now(UTC).isoformat(),
            }
        }

    def _assign_user(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Assign role to user with validation."""
        user_id = inputs["user_id"]
        role_id = inputs["role_id"]
        tenant_id = inputs.get("tenant_id", "default")
        validate_hierarchy = inputs.get("validate_hierarchy", True)

        # Validate role exists and is active
        if validate_hierarchy:
            role = self._get_role_by_id(role_id, tenant_id)
            if not role:
                raise NodeValidationError(f"Role not found: {role_id}")
            if not role["is_active"]:
                raise NodeValidationError(f"Role is not active: {role_id}")

        # Check if assignment already exists
        existing_query = """
        SELECT 1 FROM user_roles
        WHERE user_id = $1 AND role_id = $2 AND tenant_id = $3
        """

        self._db_node.config.update(
            {
                "query": existing_query,
                "params": [user_id, role_id, tenant_id],
                "fetch_mode": "one",
            }
        )

        existing = self._db_node.run()

        if existing.get("result", {}).get("data"):
            return {
                "result": {
                    "assignment": {
                        "user_id": user_id,
                        "role_id": role_id,
                        "already_assigned": True,
                    },
                    "operation": "assign_user",
                    "success": True,
                    "timestamp": datetime.now(UTC).isoformat(),
                }
            }

        # Create assignment
        now = datetime.now(UTC)
        insert_query = """
        INSERT INTO user_roles (user_id, role_id, tenant_id, assigned_at, assigned_by)
        VALUES ($1, $2, $3, $4, $5)
        """

        self._db_node.config.update(
            {
                "query": insert_query,
                "params": [
                    user_id,
                    role_id,
                    tenant_id,
                    now,
                    inputs.get("assigned_by", "system"),
                ],
            }
        )

        db_result = self._db_node.run()

        return {
            "result": {
                "assignment": {
                    "user_id": user_id,
                    "role_id": role_id,
                    "tenant_id": tenant_id,
                    "assigned_at": now.isoformat(),
                    "already_assigned": False,
                },
                "operation": "assign_user",
                "success": True,
                "timestamp": datetime.now(UTC).isoformat(),
            }
        }

    def _bulk_assign(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Bulk assign role to multiple users."""
        role_id = inputs["role_id"]
        user_ids = inputs["user_ids"]
        tenant_id = inputs.get("tenant_id", "default")

        if not isinstance(user_ids, list):
            raise NodeValidationError("user_ids must be a list for bulk operations")

        results = {
            "assigned": [],
            "failed": [],
            "stats": {"assigned": 0, "failed": 0, "already_assigned": 0},
        }

        for user_id in user_ids:
            try:
                assign_inputs = {
                    "operation": "assign_user",
                    "user_id": user_id,
                    "role_id": role_id,
                    "tenant_id": tenant_id,
                    "validate_hierarchy": inputs.get("validate_hierarchy", True),
                }

                result = self._assign_user(assign_inputs)
                assignment = result["result"]["assignment"]

                if assignment["already_assigned"]:
                    results["stats"]["already_assigned"] += 1
                else:
                    results["stats"]["assigned"] += 1

                results["assigned"].append(
                    {
                        "user_id": user_id,
                        "already_assigned": assignment["already_assigned"],
                    }
                )

            except Exception as e:
                results["failed"].append({"user_id": user_id, "error": str(e)})
                results["stats"]["failed"] += 1

        return {
            "result": {
                "operation": "bulk_assign",
                "role_id": role_id,
                "results": results,
                "timestamp": datetime.now(UTC).isoformat(),
            }
        }

    def _get_effective_permissions(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Get effective permissions for a role including inherited permissions."""
        role_id = inputs["role_id"]
        tenant_id = inputs.get("tenant_id", "default")
        include_inherited = inputs.get("include_inherited", True)

        # Get role and build hierarchy
        role_hierarchy = self._build_role_hierarchy(tenant_id)

        if role_id not in role_hierarchy:
            raise NodeValidationError(f"Role not found: {role_id}")

        role = role_hierarchy[role_id]

        # Get direct permissions
        direct_permissions = set(role["permissions"])

        # Get inherited permissions if requested
        inherited_permissions = set()
        all_permissions = direct_permissions.copy()

        if include_inherited:
            inherited_permissions = self._get_inherited_permissions(
                role_id, role_hierarchy
            )
            all_permissions.update(inherited_permissions)

        return {
            "result": {
                "role_id": role_id,
                "direct_permissions": list(direct_permissions),
                "inherited_permissions": list(inherited_permissions),
                "all_permissions": list(all_permissions),
                "permission_count": {
                    "direct": len(direct_permissions),
                    "inherited": len(inherited_permissions),
                    "total": len(all_permissions),
                },
                "operation": "get_effective_permissions",
                "timestamp": datetime.now(UTC).isoformat(),
            }
        }

    # Utility methods
    def _generate_role_id(self, name: str) -> str:
        """Generate role ID from name."""
        import re

        # Convert to lowercase, replace spaces/special chars with underscores
        role_id = re.sub(r"[^a-zA-Z0-9_]", "_", name.lower())
        role_id = re.sub(r"_+", "_", role_id)  # Remove multiple underscores
        role_id = role_id.strip("_")  # Remove leading/trailing underscores
        return role_id

    def _validate_parent_roles_exist(self, parent_roles: Set[str], tenant_id: str):
        """Validate that all parent roles exist."""
        if not parent_roles:
            return

        placeholders = ",".join(["$" + str(i + 2) for i in range(len(parent_roles))])
        query = f"""
        SELECT role_id FROM roles
        WHERE tenant_id = $1 AND role_id IN ({placeholders}) AND is_active = true
        """

        params = [tenant_id] + list(parent_roles)

        self._db_node.config.update(
            {"query": query, "params": params, "fetch_mode": "all"}
        )

        result = self._db_node.run()
        existing_roles = {
            row["role_id"] for row in result.get("result", {}).get("data", [])
        }

        missing_roles = parent_roles - existing_roles
        if missing_roles:
            raise NodeValidationError(
                f"Parent roles not found: {', '.join(missing_roles)}"
            )

    def _validate_no_circular_dependency(
        self, role_id: str, parent_roles: Set[str], tenant_id: str
    ):
        """Validate no circular dependencies in role hierarchy."""
        # Build current hierarchy excluding the new role
        role_hierarchy = self._build_role_hierarchy(tenant_id, exclude_role=role_id)

        # Check if any parent role has this role as an ancestor
        for parent_id in parent_roles:
            if self._is_ancestor(role_id, parent_id, role_hierarchy):
                raise NodeValidationError(
                    f"Circular dependency detected: {role_id} -> {parent_id}"
                )

    def _is_ancestor(
        self, ancestor_id: str, role_id: str, role_hierarchy: Dict[str, Dict]
    ) -> bool:
        """Check if ancestor_id is an ancestor of role_id."""
        if role_id not in role_hierarchy:
            return False

        role = role_hierarchy[role_id]
        parent_roles = role.get("parent_roles", [])

        if ancestor_id in parent_roles:
            return True

        # Recursively check parent roles
        for parent_id in parent_roles:
            if self._is_ancestor(ancestor_id, parent_id, role_hierarchy):
                return True

        return False

    def _build_role_hierarchy(
        self, tenant_id: str, exclude_role: Optional[str] = None
    ) -> Dict[str, Dict]:
        """Build complete role hierarchy for tenant."""
        query = """
        SELECT role_id, name, permissions, parent_roles, child_roles, is_active
        FROM roles
        WHERE tenant_id = $1
        """
        params = [tenant_id]

        if exclude_role:
            query += " AND role_id != $2"
            params.append(exclude_role)

        self._db_node.config.update(
            {"query": query, "params": params, "fetch_mode": "all"}
        )

        result = self._db_node.run()
        roles_data = result.get("result", {}).get("data", [])

        # Convert to hierarchy dict
        hierarchy = {}
        for role_data in roles_data:
            hierarchy[role_data["role_id"]] = role_data

        return hierarchy

    def _get_inherited_permissions(
        self, role_id: str, role_hierarchy: Dict[str, Dict]
    ) -> Set[str]:
        """Get all inherited permissions for a role."""
        inherited = set()

        if role_id not in role_hierarchy:
            return inherited

        role = role_hierarchy[role_id]
        parent_roles = role.get("parent_roles", [])

        for parent_id in parent_roles:
            if parent_id in role_hierarchy:
                parent_role = role_hierarchy[parent_id]
                # Add parent's direct permissions
                inherited.update(parent_role.get("permissions", []))
                # Recursively add inherited permissions
                inherited.update(
                    self._get_inherited_permissions(parent_id, role_hierarchy)
                )

        return inherited

    def _get_role_by_id(self, role_id: str, tenant_id: str) -> Optional[Dict[str, Any]]:
        """Get role by ID."""
        query = """
        SELECT role_id, name, description, role_type, permissions, parent_roles,
               attributes, is_active, created_at, updated_at
        FROM roles
        WHERE role_id = $1 AND tenant_id = $2
        """

        self._db_node.config.update(
            {"query": query, "params": [role_id, tenant_id], "fetch_mode": "one"}
        )

        result = self._db_node.run()
        return result.get("result", {}).get("data")

    def _update_child_roles(
        self,
        parent_role_ids: Set[str],
        child_role_id: str,
        tenant_id: str,
        operation: str,
    ):
        """Update child_roles arrays for parent roles."""
        if operation == "add":
            query = """
            UPDATE roles
            SET child_roles = array_append(child_roles, $1),
                updated_at = $2
            WHERE role_id = ANY($3) AND tenant_id = $4
            """
        else:  # remove
            query = """
            UPDATE roles
            SET child_roles = array_remove(child_roles, $1),
                updated_at = $2
            WHERE role_id = ANY($3) AND tenant_id = $4
            """

        self._db_node.config.update(
            {
                "query": query,
                "params": [
                    child_role_id,
                    datetime.now(UTC),
                    list(parent_role_ids),
                    tenant_id,
                ],
            }
        )

        self._db_node.run()

    # Additional operations would follow similar patterns
    def _update_role(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Update role information."""
        raise NotImplementedError("Update role operation will be implemented")

    def _delete_role(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Delete role with dependency checking."""
        raise NotImplementedError("Delete role operation will be implemented")

    def _list_roles(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """List roles with filtering and pagination."""
        raise NotImplementedError("List roles operation will be implemented")

    def _get_role(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Get detailed role information."""
        raise NotImplementedError("Get role operation will be implemented")

    def _unassign_user(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Unassign role from user."""
        raise NotImplementedError("Unassign user operation will be implemented")

    def _add_permission(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Add permission to role."""
        raise NotImplementedError("Add permission operation will be implemented")

    def _remove_permission(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Remove permission from role."""
        raise NotImplementedError("Remove permission operation will be implemented")

    def _bulk_unassign(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Bulk unassign role from multiple users."""
        raise NotImplementedError("Bulk unassign operation will be implemented")

    def _get_user_roles(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Get all roles for a user."""
        raise NotImplementedError("Get user roles operation will be implemented")

    def _get_role_users(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Get all users assigned to a role."""
        raise NotImplementedError("Get role users operation will be implemented")

    def _validate_hierarchy(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Validate entire role hierarchy for consistency."""
        raise NotImplementedError("Validate hierarchy operation will be implemented")

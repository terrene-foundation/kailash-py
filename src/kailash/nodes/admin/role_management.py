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

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Union

from kailash.access_control import (
    AccessControlManager,
    NodePermission,
    PermissionEffect,
    PermissionRule,
    WorkflowPermission,
)
from kailash.nodes.base import Node, NodeParameter, register_node
from kailash.nodes.data import SQLDatabaseNode
from kailash.sdk_exceptions import NodeExecutionError, NodeValidationError


def parse_datetime(value: Union[str, datetime, None]) -> Optional[datetime]:
    """Parse datetime from various formats."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            # Try ISO format first
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            # Try other common formats
            for fmt in [
                "%Y-%m-%d %H:%M:%S.%f",
                "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%dT%H:%M:%S.%f",
                "%Y-%m-%dT%H:%M:%S",
            ]:
                try:
                    return datetime.strptime(value, fmt)
                except ValueError:
                    continue
    return None


def format_datetime(dt: Union[datetime, str, None]) -> Optional[str]:
    """Format datetime handling both datetime objects and strings."""
    if dt is None:
        return None
    if isinstance(dt, datetime):
        return dt.isoformat()
    if isinstance(dt, str):
        # Already a string, return as-is or try to parse and format
        parsed = parse_datetime(dt)
        return parsed.isoformat() if parsed else dt
    return None


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
        >>> result = node.execute()
        >>> role_id = result["role"]["role_id"]

        >>> # Bulk user assignment
        >>> node = RoleManagementNode(
        ...     operation="bulk_assign",
        ...     role_id="senior_analyst",
        ...     user_ids=["user1", "user2", "user3"],
        ...     validate_hierarchy=True
        ... )
        >>> result = node.execute()
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
                # Pagination
                NodeParameter(
                    name="limit",
                    type=int,
                    required=False,
                    default=50,
                    description="Maximum number of results to return",
                ),
                NodeParameter(
                    name="offset",
                    type=int,
                    required=False,
                    default=0,
                    description="Number of results to skip",
                ),
                # Additional options
                NodeParameter(
                    name="include_users",
                    type=bool,
                    required=False,
                    default=False,
                    description="Include user assignments in role details",
                ),
                NodeParameter(
                    name="include_user_details",
                    type=bool,
                    required=False,
                    default=True,
                    description="Include detailed user information",
                ),
                NodeParameter(
                    name="include_inactive",
                    type=bool,
                    required=False,
                    default=False,
                    description="Include inactive roles/users",
                ),
                NodeParameter(
                    name="force",
                    type=bool,
                    required=False,
                    default=False,
                    description="Force operation even with dependencies",
                ),
                NodeParameter(
                    name="fix_issues",
                    type=bool,
                    required=False,
                    default=False,
                    description="Automatically fix validation issues",
                ),
                # Audit fields
                NodeParameter(
                    name="created_by",
                    type=str,
                    required=False,
                    default="system",
                    description="User who created the role",
                ),
                NodeParameter(
                    name="assigned_by",
                    type=str,
                    required=False,
                    default="system",
                    description="User who assigned the role",
                ),
                NodeParameter(
                    name="unassigned_by",
                    type=str,
                    required=False,
                    default="system",
                    description="User who unassigned the role",
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
        # Skip initialization if already initialized (for testing)
        if hasattr(self, "_db_node") and self._db_node is not None:
            return

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

        # Initialize database node
        self._db_node = SQLDatabaseNode(name="role_management_db", **db_config)

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

        # Insert role into database with conflict resolution
        insert_query = """
        INSERT INTO roles (
            role_id, name, description, role_type, permissions, parent_roles,
            attributes, is_active, tenant_id, created_at, updated_at, created_by
        ) VALUES (
            $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12
        )
        ON CONFLICT (role_id) DO UPDATE SET
            name = EXCLUDED.name,
            description = EXCLUDED.description,
            role_type = EXCLUDED.role_type,
            permissions = EXCLUDED.permissions,
            parent_roles = EXCLUDED.parent_roles,
            attributes = EXCLUDED.attributes,
            is_active = EXCLUDED.is_active,
            updated_at = EXCLUDED.updated_at,
            created_by = EXCLUDED.created_by
        """

        # Execute database insert
        db_result = self._db_node.execute(
            query=insert_query,
            parameters=[
                role_record["role_id"],
                role_record["name"],
                role_record["description"],
                role_record["role_type"],
                json.dumps(role_record["permissions"]),  # Serialize list to JSON
                json.dumps(role_record["parent_roles"]),  # Serialize list to JSON
                json.dumps(role_record["attributes"]),  # Serialize dict to JSON
                role_record["is_active"],
                role_record["tenant_id"],
                role_record["created_at"],
                role_record["updated_at"],
                role_record["created_by"],
            ],
        )

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
                    "created_at": format_datetime(role_record["created_at"]),
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
        SELECT 1 FROM user_role_assignments
        WHERE user_id = $1 AND role_id = $2 AND tenant_id = $3 AND is_active = true
        """

        existing = self._db_node.execute(
            query=existing_query,
            parameters=[user_id, role_id, tenant_id],
            result_format="dict",
        )

        if existing.get("data"):
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

        # Create assignment with conflict resolution
        now = datetime.now(UTC)
        insert_query = """
        INSERT INTO user_role_assignments (user_id, role_id, tenant_id, assigned_at, assigned_by)
        VALUES ($1, $2, $3, $4, $5)
        ON CONFLICT (user_id, role_id, tenant_id) DO UPDATE SET
            assigned_at = EXCLUDED.assigned_at,
            assigned_by = EXCLUDED.assigned_by,
            is_active = true
        """

        db_result = self._db_node.execute(
            query=insert_query,
            parameters=[
                user_id,
                role_id,
                tenant_id,
                now,
                inputs.get("assigned_by", "system"),
            ],
        )

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

        result = self._db_node.execute(
            query=query, parameters=params, result_format="dict"
        )
        existing_roles = {row["role_id"] for row in result.get("data", [])}

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

        result = self._db_node.execute(query=query, parameters=params, fetch_mode="all")
        roles_data = result.get("data", [])

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

        result = self._db_node.execute(
            query=query, parameters=[role_id, tenant_id], result_format="dict"
        )
        data = result.get("data", [])
        return data[0] if data else None

    def _update_child_roles(
        self,
        parent_role_ids: Set[str],
        child_role_id: str,
        tenant_id: str,
        operation: str,
    ):
        """Update child_roles JSONB arrays for parent roles."""
        # For now, let's just read the current child_roles, modify them in Python, and update
        # This is simpler and more reliable than complex JSONB operations

        for parent_role_id in parent_role_ids:
            # Get current child roles
            get_query = """
            SELECT child_roles FROM roles
            WHERE role_id = $1 AND tenant_id = $2
            """

            result = self._db_node.execute(
                query=get_query,
                parameters=[parent_role_id, tenant_id],
                result_format="dict",
            )

            if result.get("data"):
                current_child_roles = result["data"][0].get("child_roles", [])
                if isinstance(current_child_roles, str):
                    current_child_roles = json.loads(current_child_roles)
                elif current_child_roles is None:
                    current_child_roles = []

                # Modify the list
                if operation == "add":
                    if child_role_id not in current_child_roles:
                        current_child_roles.append(child_role_id)
                else:  # remove
                    if child_role_id in current_child_roles:
                        current_child_roles.remove(child_role_id)

                # Update the database
                update_query = """
                UPDATE roles
                SET child_roles = $1, updated_at = $2
                WHERE role_id = $3 AND tenant_id = $4
                """

                self._db_node.execute(
                    query=update_query,
                    parameters=[
                        json.dumps(current_child_roles),
                        datetime.now(UTC),
                        parent_role_id,
                        tenant_id,
                    ],
                )

    # Additional operations would follow similar patterns
    def _update_role(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Update role information."""
        role_id = inputs["role_id"]
        role_data = inputs["role_data"]
        tenant_id = inputs.get("tenant_id", "default")
        validate_hierarchy = inputs.get("validate_hierarchy", True)

        # Validate role exists
        existing_role = self._get_role_by_id(role_id, tenant_id)
        if not existing_role:
            raise NodeValidationError(f"Role not found: {role_id}")

        # Validate parent roles if being updated
        if "parent_roles" in role_data and validate_hierarchy:
            parent_roles = set(role_data["parent_roles"])
            self._validate_parent_roles_exist(parent_roles, tenant_id)
            self._validate_no_circular_dependency(role_id, parent_roles, tenant_id)

        # Build update fields
        update_fields = []
        params = []
        param_count = 1

        updatable_fields = {
            "name": "name",
            "description": "description",
            "permissions": "permissions",
            "parent_roles": "parent_roles",
            "attributes": "attributes",
            "is_active": "is_active",
        }

        for field, db_field in updatable_fields.items():
            if field in role_data:
                update_fields.append(f"{db_field} = ${param_count}")
                # Serialize JSONB fields to JSON
                if field in ["permissions", "parent_roles", "attributes"]:
                    params.append(json.dumps(role_data[field]))
                else:
                    params.append(role_data[field])
                param_count += 1

        if not update_fields:
            raise NodeValidationError("No valid fields provided for update")

        # Add updated_at timestamp
        update_fields.append(f"updated_at = ${param_count}")
        params.append(datetime.now(UTC))
        param_count += 1

        # Add WHERE conditions
        params.extend([role_id, tenant_id])

        update_query = f"""
        UPDATE roles
        SET {', '.join(update_fields)}
        WHERE role_id = ${param_count} AND tenant_id = ${param_count + 1}
        RETURNING role_id, name, description, permissions, parent_roles, attributes, is_active, updated_at
        """

        result = self._db_node.execute(
            query=update_query, parameters=params, fetch_mode="one"
        )
        updated_role = result.get("data", [])
        updated_role = updated_role[0] if updated_role else None

        if not updated_role:
            raise NodeExecutionError(f"Failed to update role: {role_id}")

        # Update child roles if parent_roles changed
        if "parent_roles" in role_data:
            old_parents = set(existing_role.get("parent_roles", []))
            new_parents = set(role_data["parent_roles"])

            # Remove from old parents
            removed_parents = old_parents - new_parents
            if removed_parents:
                self._update_child_roles(removed_parents, role_id, tenant_id, "remove")

            # Add to new parents
            added_parents = new_parents - old_parents
            if added_parents:
                self._update_child_roles(added_parents, role_id, tenant_id, "add")

        return {
            "result": {
                "role": {
                    "role_id": updated_role["role_id"],
                    "name": updated_role["name"],
                    "description": updated_role["description"],
                    "permissions": updated_role["permissions"],
                    "parent_roles": updated_role["parent_roles"],
                    "attributes": updated_role["attributes"],
                    "is_active": updated_role["is_active"],
                    "updated_at": format_datetime(updated_role["updated_at"]),
                },
                "operation": "update_role",
                "success": True,
                "timestamp": datetime.now(UTC).isoformat(),
            }
        }

    def _delete_role(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Delete role with dependency checking."""
        role_id = inputs["role_id"]
        tenant_id = inputs.get("tenant_id", "default")
        force = inputs.get("force", False)

        # Validate role exists
        existing_role = self._get_role_by_id(role_id, tenant_id)
        if not existing_role:
            raise NodeValidationError(f"Role not found: {role_id}")

        # Check for dependencies unless force delete
        if not force:
            # Check for child roles
            child_roles_query = """
            SELECT role_id FROM roles
            WHERE $1 = ANY(
                SELECT jsonb_array_elements_text(parent_roles)
            ) AND tenant_id = $2 AND is_active = true
            """

            child_result = self._db_node.execute(
                query=child_roles_query,
                parameters=[role_id, tenant_id],
                fetch_mode="all",
            )
            child_roles = child_result.get("data", [])

            if child_roles:
                child_role_ids = [r["role_id"] for r in child_roles]
                raise NodeValidationError(
                    f"Cannot delete role {role_id}: has child roles {child_role_ids}. Use force=True to override."
                )

            # Check for user assignments
            user_assignments_query = """
            SELECT COUNT(*) as user_count FROM user_role_assignments
            WHERE role_id = $1 AND tenant_id = $2
            """

            user_result = self._db_node.execute(
                query=user_assignments_query,
                parameters=[role_id, tenant_id],
                fetch_mode="one",
            )
            user_count = user_result.get("data", [{}])[0].get("user_count", 0)

            if user_count > 0:
                raise NodeValidationError(
                    f"Cannot delete role {role_id}: assigned to {user_count} users. Use force=True to override."
                )

        # Store parent roles for cleanup
        parent_roles = set(existing_role.get("parent_roles", []))

        # Delete user assignments if force
        if force:
            delete_assignments_query = """
            DELETE FROM user_role_assignments WHERE role_id = $1 AND tenant_id = $2
            """

            self._db_node.execute(
                query=delete_assignments_query, parameters=[role_id, tenant_id]
            )

        # Remove from child roles of other roles
        if parent_roles:
            self._update_child_roles(parent_roles, role_id, tenant_id, "remove")

        # Update child roles to remove this as parent
        update_children_query = """
        UPDATE roles
        SET parent_roles = (
            SELECT COALESCE(
                json_agg(value),
                '[]'::json
            )
            FROM jsonb_array_elements_text(parent_roles) AS value
            WHERE value != $1
        )::jsonb,
            updated_at = $2
        WHERE $1 = ANY(
            SELECT jsonb_array_elements_text(parent_roles)
        ) AND tenant_id = $3
        """

        self._db_node.execute(
            query=update_children_query,
            parameters=[role_id, datetime.now(UTC), tenant_id],
        )

        # Delete the role
        delete_query = """
        DELETE FROM roles WHERE role_id = $1 AND tenant_id = $2
        """

        self._db_node.execute(query=delete_query, parameters=[role_id, tenant_id])

        return {
            "result": {
                "role_id": role_id,
                "deleted": True,
                "force_used": force,
                "operation": "delete_role",
                "success": True,
                "timestamp": datetime.now(UTC).isoformat(),
            }
        }

    def _list_roles(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """List roles with filtering and pagination."""
        tenant_id = inputs.get("tenant_id", "default")
        filters = inputs.get("filters", {})
        search_query = inputs.get("search_query", "")
        limit = inputs.get("limit", 50)
        offset = inputs.get("offset", 0)
        include_inherited = inputs.get("include_inherited", False)

        # Build WHERE conditions
        where_conditions = ["tenant_id = $1"]
        params = [tenant_id]
        param_count = 2

        # Add search filter
        if search_query:
            where_conditions.append(
                f"(name ILIKE ${param_count} OR description ILIKE ${param_count})"
            )
            params.append(f"%{search_query}%")
            param_count += 1

        # Add field filters
        if "role_type" in filters:
            where_conditions.append(f"role_type = ${param_count}")
            params.append(filters["role_type"])
            param_count += 1

        if "is_active" in filters:
            where_conditions.append(f"is_active = ${param_count}")
            params.append(filters["is_active"])
            param_count += 1

        if "has_permissions" in filters:
            where_conditions.append("array_length(permissions, 1) > 0")

        # Build query
        base_query = f"""
        SELECT role_id, name, description, role_type, permissions, parent_roles,
               child_roles, attributes, is_active, created_at, updated_at, created_by
        FROM roles
        WHERE {' AND '.join(where_conditions)}
        ORDER BY created_at DESC
        """

        # Add pagination
        if limit > 0:
            base_query += f" LIMIT ${param_count}"
            params.append(limit)
            param_count += 1

        if offset > 0:
            base_query += f" OFFSET ${param_count}"
            params.append(offset)

        result = self._db_node.execute(
            query=base_query, parameters=params, fetch_mode="all"
        )
        roles_data = result.get("data", [])

        # Get total count
        count_query = f"""
        SELECT COUNT(*) as total
        FROM roles
        WHERE {' AND '.join(where_conditions)}
        """

        count_result = self._db_node.execute(
            query=count_query,
            parameters=(
                params[: param_count - 2] if limit > 0 else params
            ),  # Exclude LIMIT/OFFSET
            fetch_mode="one",
        )
        total_count = count_result.get("data", [{}])[0].get("total", 0)

        # Enhance roles with inherited permissions if requested
        enhanced_roles = []
        for role_data in roles_data:
            enhanced_role = {
                "role_id": role_data["role_id"],
                "name": role_data["name"],
                "description": role_data["description"],
                "role_type": role_data["role_type"],
                "permissions": role_data["permissions"],
                "parent_roles": role_data["parent_roles"],
                "child_roles": role_data["child_roles"],
                "attributes": role_data["attributes"],
                "is_active": role_data["is_active"],
                "created_at": format_datetime(role_data["created_at"]),
                "updated_at": format_datetime(role_data["updated_at"]),
                "created_by": role_data["created_by"],
            }

            if include_inherited:
                # Get inherited permissions
                role_hierarchy = self._build_role_hierarchy(tenant_id)
                inherited_perms = self._get_inherited_permissions(
                    role_data["role_id"], role_hierarchy
                )
                all_perms = set(role_data["permissions"]) | inherited_perms

                enhanced_role["inherited_permissions"] = list(inherited_perms)
                enhanced_role["all_permissions"] = list(all_perms)
                enhanced_role["permission_count"] = {
                    "direct": len(role_data["permissions"]),
                    "inherited": len(inherited_perms),
                    "total": len(all_perms),
                }

            enhanced_roles.append(enhanced_role)

        return {
            "result": {
                "roles": enhanced_roles,
                "pagination": {
                    "total": total_count,
                    "limit": limit,
                    "offset": offset,
                    "returned": len(enhanced_roles),
                },
                "filters_applied": {
                    "search_query": search_query,
                    "filters": filters,
                    "include_inherited": include_inherited,
                },
                "operation": "list_roles",
                "timestamp": datetime.now(UTC).isoformat(),
            }
        }

    def _get_role(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Get detailed role information."""
        role_id = inputs["role_id"]
        tenant_id = inputs.get("tenant_id", "default")
        include_inherited = inputs.get("include_inherited", True)
        include_users = inputs.get("include_users", False)

        # Get basic role information
        role_data = self._get_role_by_id(role_id, tenant_id)
        if not role_data:
            raise NodeValidationError(f"Role not found: {role_id}")

        # Build enhanced role info
        enhanced_role = {
            "role_id": role_data["role_id"],
            "name": role_data["name"],
            "description": role_data["description"],
            "role_type": role_data["role_type"],
            "permissions": role_data["permissions"],
            "parent_roles": role_data["parent_roles"],
            "attributes": role_data["attributes"],
            "is_active": role_data["is_active"],
            "created_at": format_datetime(role_data["created_at"]),
            "updated_at": format_datetime(role_data["updated_at"]),
        }

        # Add inherited permissions if requested
        if include_inherited:
            role_hierarchy = self._build_role_hierarchy(tenant_id)
            inherited_perms = self._get_inherited_permissions(role_id, role_hierarchy)
            all_perms = set(role_data["permissions"]) | inherited_perms

            enhanced_role["inherited_permissions"] = list(inherited_perms)
            enhanced_role["all_permissions"] = list(all_perms)
            enhanced_role["permission_count"] = {
                "direct": len(role_data["permissions"]),
                "inherited": len(inherited_perms),
                "total": len(all_perms),
            }

            # Get child roles from hierarchy
            child_roles = []
            for role_info in role_hierarchy.values():
                if role_id in role_info.get("parent_roles", []):
                    child_roles.append(
                        {
                            "role_id": role_info["role_id"],
                            "name": role_info["name"],
                            "is_active": role_info["is_active"],
                        }
                    )
            enhanced_role["child_roles_detailed"] = child_roles

        # Add user assignments if requested
        if include_users:
            users_query = """
            SELECT ur.user_id, ur.assigned_at, ur.assigned_by, u.email, u.status
            FROM user_role_assignments ur
            LEFT JOIN users u ON ur.user_id = u.user_id AND ur.tenant_id = u.tenant_id
            WHERE ur.role_id = $1 AND ur.tenant_id = $2
            ORDER BY ur.assigned_at DESC
            """

            users_result = self._db_node.execute(
                query=users_query, parameters=[role_id, tenant_id], fetch_mode="all"
            )
            users_data = users_result.get("data", [])

            enhanced_role["assigned_users"] = [
                {
                    "user_id": user["user_id"],
                    "email": user.get("email"),
                    "status": user.get("status"),
                    "assigned_at": (
                        user["assigned_at"].isoformat() if user["assigned_at"] else None
                    ),
                    "assigned_by": user["assigned_by"],
                }
                for user in users_data
            ]
            enhanced_role["user_count"] = len(users_data)

        return {
            "result": {
                "role": enhanced_role,
                "operation": "get_role",
                "timestamp": datetime.now(UTC).isoformat(),
            }
        }

    def _unassign_user(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Unassign role from user."""
        user_id = inputs["user_id"]
        role_id = inputs["role_id"]
        tenant_id = inputs.get("tenant_id", "default")

        # Check if assignment exists
        check_query = """
        SELECT user_id, role_id, assigned_at, assigned_by
        FROM user_role_assignments
        WHERE user_id = $1 AND role_id = $2 AND tenant_id = $3
        """

        existing = self._db_node.execute(
            query=check_query,
            parameters=[user_id, role_id, tenant_id],
            fetch_mode="one",
        )
        assignment = existing.get("result", {}).get("data")

        if not assignment:
            return {
                "result": {
                    "unassignment": {
                        "user_id": user_id,
                        "role_id": role_id,
                        "was_assigned": False,
                        "message": "User was not assigned to this role",
                    },
                    "operation": "unassign_user",
                    "success": True,
                    "timestamp": datetime.now(UTC).isoformat(),
                }
            }

        # Remove assignment
        delete_query = """
        DELETE FROM user_role_assignments
        WHERE user_id = $1 AND role_id = $2 AND tenant_id = $3
        """

        self._db_node.execute(
            query=delete_query, parameters=[user_id, role_id, tenant_id]
        )

        return {
            "result": {
                "unassignment": {
                    "user_id": user_id,
                    "role_id": role_id,
                    "was_assigned": True,
                    "previously_assigned_at": (
                        assignment["assigned_at"].isoformat()
                        if assignment["assigned_at"]
                        else None
                    ),
                    "previously_assigned_by": assignment["assigned_by"],
                    "unassigned_at": datetime.now(UTC).isoformat(),
                    "unassigned_by": inputs.get("unassigned_by", "system"),
                },
                "operation": "unassign_user",
                "success": True,
                "timestamp": datetime.now(UTC).isoformat(),
            }
        }

    def _add_permission(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Add permission to role."""
        role_id = inputs["role_id"]
        permission = inputs["permission"]
        tenant_id = inputs.get("tenant_id", "default")

        # Validate role exists
        role_data = self._get_role_by_id(role_id, tenant_id)
        if not role_data:
            raise NodeValidationError(f"Role not found: {role_id}")

        current_permissions = set(role_data.get("permissions", []))

        # Check if permission already exists
        if permission in current_permissions:
            return {
                "result": {
                    "permission_added": False,
                    "role_id": role_id,
                    "permission": permission,
                    "message": "Permission already exists on role",
                    "operation": "add_permission",
                    "timestamp": datetime.now(UTC).isoformat(),
                }
            }

        # Add permission
        new_permissions = list(current_permissions | {permission})

        update_query = """
        UPDATE roles
        SET permissions = $1, updated_at = $2
        WHERE role_id = $3 AND tenant_id = $4
        RETURNING permissions
        """

        result = self._db_node.execute(
            query=update_query,
            parameters=[
                json.dumps(new_permissions),
                datetime.now(UTC),
                role_id,
                tenant_id,
            ],
            fetch_mode="one",
        )
        updated_permissions = result.get("data", [{}])[0].get("permissions", [])

        return {
            "result": {
                "permission_added": True,
                "role_id": role_id,
                "permission": permission,
                "permissions_count": len(updated_permissions),
                "all_permissions": updated_permissions,
                "operation": "add_permission",
                "timestamp": datetime.now(UTC).isoformat(),
            }
        }

    def _remove_permission(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Remove permission from role."""
        role_id = inputs["role_id"]
        permission = inputs["permission"]
        tenant_id = inputs.get("tenant_id", "default")

        # Validate role exists
        role_data = self._get_role_by_id(role_id, tenant_id)
        if not role_data:
            raise NodeValidationError(f"Role not found: {role_id}")

        current_permissions = set(role_data.get("permissions", []))

        # Check if permission exists
        if permission not in current_permissions:
            return {
                "result": {
                    "permission_removed": False,
                    "role_id": role_id,
                    "permission": permission,
                    "message": "Permission does not exist on role",
                    "operation": "remove_permission",
                    "timestamp": datetime.now(UTC).isoformat(),
                }
            }

        # Remove permission
        new_permissions = list(current_permissions - {permission})

        update_query = """
        UPDATE roles
        SET permissions = $1, updated_at = $2
        WHERE role_id = $3 AND tenant_id = $4
        RETURNING permissions
        """

        result = self._db_node.execute(
            query=update_query,
            parameters=[
                json.dumps(new_permissions),
                datetime.now(UTC),
                role_id,
                tenant_id,
            ],
            fetch_mode="one",
        )
        updated_permissions = result.get("data", [{}])[0].get("permissions", [])

        return {
            "result": {
                "permission_removed": True,
                "role_id": role_id,
                "permission": permission,
                "permissions_count": len(updated_permissions),
                "all_permissions": updated_permissions,
                "operation": "remove_permission",
                "timestamp": datetime.now(UTC).isoformat(),
            }
        }

    def _bulk_unassign(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Bulk unassign role from multiple users."""
        role_id = inputs["role_id"]
        user_ids = inputs["user_ids"]
        tenant_id = inputs.get("tenant_id", "default")

        if not isinstance(user_ids, list):
            raise NodeValidationError("user_ids must be a list for bulk operations")

        results = {
            "unassigned": [],
            "not_assigned": [],
            "failed": [],
            "stats": {"unassigned": 0, "not_assigned": 0, "failed": 0},
        }

        for user_id in user_ids:
            try:
                unassign_inputs = {
                    "operation": "unassign_user",
                    "user_id": user_id,
                    "role_id": role_id,
                    "tenant_id": tenant_id,
                    "unassigned_by": inputs.get("unassigned_by", "system"),
                }

                result = self._unassign_user(unassign_inputs)
                unassignment = result["result"]["unassignment"]

                if unassignment["was_assigned"]:
                    results["unassigned"].append(
                        {
                            "user_id": user_id,
                            "previously_assigned_at": unassignment[
                                "previously_assigned_at"
                            ],
                        }
                    )
                    results["stats"]["unassigned"] += 1
                else:
                    results["not_assigned"].append({"user_id": user_id})
                    results["stats"]["not_assigned"] += 1

            except Exception as e:
                results["failed"].append({"user_id": user_id, "error": str(e)})
                results["stats"]["failed"] += 1

        return {
            "result": {
                "operation": "bulk_unassign",
                "role_id": role_id,
                "results": results,
                "timestamp": datetime.now(UTC).isoformat(),
            }
        }

    def _get_user_roles(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Get all roles for a user."""
        user_id = inputs["user_id"]
        tenant_id = inputs.get("tenant_id", "default")
        include_inherited = inputs.get("include_inherited", True)
        include_inactive = inputs.get("include_inactive", False)

        # Get user role assignments
        roles_query = """
        SELECT ur.role_id, ur.assigned_at, ur.assigned_by,
               r.name, r.description, r.role_type, r.permissions,
               r.parent_roles, r.attributes, r.is_active
        FROM user_role_assignments ur
        JOIN roles r ON ur.role_id = r.role_id AND ur.tenant_id = r.tenant_id
        WHERE ur.user_id = $1 AND ur.tenant_id = $2
        """

        params = [user_id, tenant_id]

        if not include_inactive:
            roles_query += " AND r.is_active = true"

        roles_query += " ORDER BY ur.assigned_at DESC"

        result = self._db_node.execute(
            query=roles_query, parameters=params, fetch_mode="all"
        )
        roles_data = result.get("data", [])

        user_roles = []
        all_permissions = set()
        role_hierarchy = (
            self._build_role_hierarchy(tenant_id) if include_inherited else {}
        )

        for role_data in roles_data:
            role_info = {
                "role_id": role_data["role_id"],
                "name": role_data["name"],
                "description": role_data["description"],
                "role_type": role_data["role_type"],
                "permissions": role_data["permissions"],
                "parent_roles": role_data["parent_roles"],
                "attributes": role_data["attributes"],
                "is_active": role_data["is_active"],
                "assigned_at": format_datetime(role_data["assigned_at"]),
                "assigned_by": role_data["assigned_by"],
            }

            # Add permissions from this role
            direct_permissions = set(role_data["permissions"])
            all_permissions.update(direct_permissions)

            if include_inherited:
                inherited_perms = self._get_inherited_permissions(
                    role_data["role_id"], role_hierarchy
                )
                all_permissions.update(inherited_perms)

                role_info["inherited_permissions"] = list(inherited_perms)
                role_info["all_permissions"] = list(
                    direct_permissions | inherited_perms
                )
                role_info["permission_count"] = {
                    "direct": len(direct_permissions),
                    "inherited": len(inherited_perms),
                    "total": len(direct_permissions | inherited_perms),
                }

            user_roles.append(role_info)

        return {
            "result": {
                "user_id": user_id,
                "roles": user_roles,
                "summary": {
                    "role_count": len(user_roles),
                    "active_roles": len([r for r in user_roles if r["is_active"]]),
                    "total_permissions": len(all_permissions),
                    "unique_permissions": list(all_permissions),
                },
                "options": {
                    "include_inherited": include_inherited,
                    "include_inactive": include_inactive,
                },
                "operation": "get_user_roles",
                "timestamp": datetime.now(UTC).isoformat(),
            }
        }

    def _get_role_users(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Get all users assigned to a role."""
        role_id = inputs["role_id"]
        tenant_id = inputs.get("tenant_id", "default")
        include_user_details = inputs.get("include_user_details", True)
        limit = inputs.get("limit", 100)
        offset = inputs.get("offset", 0)

        # Validate role exists
        role_data = self._get_role_by_id(role_id, tenant_id)
        if not role_data:
            raise NodeValidationError(f"Role not found: {role_id}")

        # Get user assignments
        if include_user_details:
            users_query = """
            SELECT ur.user_id, ur.assigned_at, ur.assigned_by,
                   u.email, u.first_name, u.last_name, u.status, u.created_at as user_created_at
            FROM user_role_assignments ur
            LEFT JOIN users u ON ur.user_id = u.user_id AND ur.tenant_id = u.tenant_id
            WHERE ur.role_id = $1 AND ur.tenant_id = $2
            ORDER BY ur.assigned_at DESC
            LIMIT $3 OFFSET $4
            """
        else:
            users_query = """
            SELECT ur.user_id, ur.assigned_at, ur.assigned_by
            FROM user_role_assignments ur
            WHERE ur.role_id = $1 AND ur.tenant_id = $2
            ORDER BY ur.assigned_at DESC
            LIMIT $3 OFFSET $4
            """

        result = self._db_node.execute(
            query=users_query,
            parameters=[role_id, tenant_id, limit, offset],
            fetch_mode="all",
        )
        users_data = result.get("result", {}).get("data", [])

        # Get total count
        count_query = """
        SELECT COUNT(*) as total
        FROM user_role_assignments
        WHERE role_id = $1 AND tenant_id = $2
        """

        count_result = self._db_node.execute(
            query=count_query, parameters=[role_id, tenant_id], fetch_mode="one"
        )
        total_count = count_result.get("data", [{}])[0].get("total", 0)

        # Format user data
        assigned_users = []
        for user_data in users_data:
            user_info = {
                "user_id": user_data["user_id"],
                "assigned_at": (
                    user_data["assigned_at"].isoformat()
                    if user_data["assigned_at"]
                    else None
                ),
                "assigned_by": user_data["assigned_by"],
            }

            if include_user_details:
                user_info.update(
                    {
                        "email": user_data.get("email"),
                        "first_name": user_data.get("first_name"),
                        "last_name": user_data.get("last_name"),
                        "status": user_data.get("status"),
                        "user_created_at": (
                            user_data["user_created_at"].isoformat()
                            if user_data.get("user_created_at")
                            else None
                        ),
                    }
                )

            assigned_users.append(user_info)

        return {
            "result": {
                "role": {
                    "role_id": role_id,
                    "name": role_data["name"],
                    "description": role_data["description"],
                    "is_active": role_data["is_active"],
                },
                "assigned_users": assigned_users,
                "pagination": {
                    "total": total_count,
                    "limit": limit,
                    "offset": offset,
                    "returned": len(assigned_users),
                },
                "options": {"include_user_details": include_user_details},
                "operation": "get_role_users",
                "timestamp": datetime.now(UTC).isoformat(),
            }
        }

    def _validate_hierarchy(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Validate entire role hierarchy for consistency."""
        tenant_id = inputs.get("tenant_id", "default")
        fix_issues = inputs.get("fix_issues", False)

        # Build role hierarchy
        role_hierarchy = self._build_role_hierarchy(tenant_id)

        validation_results = {
            "circular_dependencies": [],
            "missing_parents": [],
            "orphaned_child_references": [],
            "inactive_parent_references": [],
            "inconsistent_child_arrays": [],
            "total_roles": len(role_hierarchy),
            "issues_found": 0,
        }

        # Check each role for issues
        for role_id, role_data in role_hierarchy.items():
            # Check for circular dependencies
            try:
                visited = set()
                self._check_circular_dependency_recursive(
                    role_id, role_hierarchy, visited
                )
            except ValueError as e:
                validation_results["circular_dependencies"].append(
                    {"role_id": role_id, "issue": str(e)}
                )

            # Check for missing parent roles
            parent_roles = role_data.get("parent_roles", [])
            for parent_id in parent_roles:
                if parent_id not in role_hierarchy:
                    validation_results["missing_parents"].append(
                        {"role_id": role_id, "missing_parent": parent_id}
                    )
                elif not role_hierarchy[parent_id].get("is_active", True):
                    validation_results["inactive_parent_references"].append(
                        {"role_id": role_id, "inactive_parent": parent_id}
                    )

            # Check child role consistency
            child_roles = role_data.get("child_roles", [])
            for child_id in child_roles:
                if child_id not in role_hierarchy:
                    validation_results["orphaned_child_references"].append(
                        {"role_id": role_id, "orphaned_child": child_id}
                    )
                else:
                    # Check if child actually has this role as parent
                    child_data = role_hierarchy[child_id]
                    child_parents = child_data.get("parent_roles", [])
                    if role_id not in child_parents:
                        validation_results["inconsistent_child_arrays"].append(
                            {
                                "parent_role": role_id,
                                "child_role": child_id,
                                "issue": "Child role does not reference parent",
                            }
                        )

        # Count total issues
        total_issues = (
            len(validation_results["circular_dependencies"])
            + len(validation_results["missing_parents"])
            + len(validation_results["orphaned_child_references"])
            + len(validation_results["inactive_parent_references"])
            + len(validation_results["inconsistent_child_arrays"])
        )

        validation_results["issues_found"] = total_issues
        validation_results["is_valid"] = total_issues == 0

        # Fix issues if requested
        fixes_applied = []
        if fix_issues and total_issues > 0:
            # Fix orphaned child references
            for issue in validation_results["orphaned_child_references"]:
                try:
                    self._remove_orphaned_child_reference(
                        issue["role_id"], issue["orphaned_child"], tenant_id
                    )
                    fixes_applied.append(
                        f"Removed orphaned child reference {issue['orphaned_child']} from {issue['role_id']}"
                    )
                except Exception as e:
                    fixes_applied.append(
                        f"Failed to fix orphaned child reference: {str(e)}"
                    )

            # Fix inconsistent child arrays
            for issue in validation_results["inconsistent_child_arrays"]:
                try:
                    self._sync_parent_child_relationship(
                        issue["parent_role"], issue["child_role"], tenant_id
                    )
                    fixes_applied.append(
                        f"Synced parent-child relationship: {issue['parent_role']} <-> {issue['child_role']}"
                    )
                except Exception as e:
                    fixes_applied.append(f"Failed to sync relationship: {str(e)}")

        result = {
            "result": {
                "validation": validation_results,
                "operation": "validate_hierarchy",
                "timestamp": datetime.now(UTC).isoformat(),
            }
        }

        if fix_issues:
            result["result"]["fixes_applied"] = fixes_applied
            result["result"]["fix_count"] = len(fixes_applied)

        return result

    def _check_circular_dependency_recursive(
        self, role_id: str, role_hierarchy: Dict[str, Dict], visited: Set[str]
    ):
        """Recursively check for circular dependencies."""
        if role_id in visited:
            raise ValueError(f"Circular dependency detected involving role: {role_id}")

        visited.add(role_id)

        if role_id in role_hierarchy:
            parent_roles = role_hierarchy[role_id].get("parent_roles", [])
            for parent_id in parent_roles:
                self._check_circular_dependency_recursive(
                    parent_id, role_hierarchy, visited.copy()
                )

    def _remove_orphaned_child_reference(
        self, parent_role_id: str, orphaned_child_id: str, tenant_id: str
    ):
        """Remove orphaned child reference from parent role."""
        update_query = """
        UPDATE roles
        SET child_roles = (
            SELECT COALESCE(
                json_agg(value),
                '[]'::json
            )
            FROM jsonb_array_elements_text(child_roles) AS value
            WHERE value != $1
        )::jsonb,
            updated_at = $2
        WHERE role_id = $3 AND tenant_id = $4
        """

        self._db_node.execute(
            query=update_query,
            parameters=[
                orphaned_child_id,
                datetime.now(UTC),
                parent_role_id,
                tenant_id,
            ],
        )

    def _sync_parent_child_relationship(
        self, parent_role_id: str, child_role_id: str, tenant_id: str
    ):
        """Ensure parent-child relationship is consistent in both directions."""
        # Add child to parent's child_roles if not present
        add_child_query = """
        UPDATE roles
        SET child_roles = (
            CASE
                WHEN child_roles ? $1 THEN child_roles
                ELSE child_roles || jsonb_build_array($1)
            END
        ),
            updated_at = $2
        WHERE role_id = $3 AND tenant_id = $4
        AND NOT ($1 = ANY(
            SELECT jsonb_array_elements_text(child_roles)
        ))
        """

        self._db_node.execute(
            query=add_child_query,
            parameters=[child_role_id, datetime.now(UTC), parent_role_id, tenant_id],
        )

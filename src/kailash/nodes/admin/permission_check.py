"""Enterprise permission checking node with real-time RBAC and ABAC evaluation.

This node provides high-performance permission checking capabilities that integrate
both Role-Based Access Control (RBAC) and Attribute-Based Access Control (ABAC)
from Session 065. Designed for real-time permission evaluation in enterprise
applications with comprehensive caching and audit logging.

Features:
- Real-time RBAC and ABAC permission evaluation
- Multi-level permission caching for performance
- Batch permission checking for efficiency
- Permission explanation and debugging
- Conditional permission evaluation
- Integration with user and role management
- Comprehensive audit logging
- Multi-tenant permission isolation
"""

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

from kailash.access_control import (
    AccessControlManager,
    AccessDecision,
    NodePermission,
    PermissionEffect,
    PermissionRule,
    UserContext,
    WorkflowPermission,
)
from kailash.access_control_abac import (
    AttributeCondition,
    AttributeEvaluator,
    AttributeExpression,
    AttributeOperator,
    LogicalOperator,
)
from kailash.nodes.base import Node, NodeParameter, register_node
from kailash.nodes.data import SQLDatabaseNode
from kailash.sdk_exceptions import NodeExecutionError, NodeValidationError

from .schema_manager import AdminSchemaManager


class PermissionCheckOperation(Enum):
    """Supported permission check operations."""

    CHECK_PERMISSION = "check_permission"
    BATCH_CHECK = "batch_check"
    CHECK_NODE_ACCESS = "check_node_access"
    CHECK_WORKFLOW_ACCESS = "check_workflow_access"
    GET_USER_PERMISSIONS = "get_user_permissions"
    EXPLAIN_PERMISSION = "explain_permission"
    VALIDATE_CONDITIONS = "validate_conditions"
    CHECK_HIERARCHICAL = "check_hierarchical"
    BULK_USER_CHECK = "bulk_user_check"
    CLEAR_CACHE = "clear_cache"


class CacheLevel(Enum):
    """Permission cache levels."""

    NONE = "none"  # No caching
    USER = "user"  # Cache per user
    ROLE = "role"  # Cache per role
    PERMISSION = "permission"  # Cache per permission
    FULL = "full"  # Full caching


@dataclass
class PermissionCheckResult:
    """Result of a permission check operation."""

    allowed: bool
    reason: str
    applied_rules: List[str]
    user_id: str
    resource_id: str
    permission: str
    evaluation_time_ms: float
    cached: bool
    cache_hit: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "allowed": self.allowed,
            "reason": self.reason,
            "applied_rules": self.applied_rules,
            "user_id": self.user_id,
            "resource_id": self.resource_id,
            "permission": self.permission,
            "evaluation_time_ms": self.evaluation_time_ms,
            "cached": self.cached,
            "cache_hit": self.cache_hit,
        }


@dataclass
class PermissionExplanation:
    """Detailed explanation of permission evaluation."""

    permission_granted: bool
    rbac_result: bool
    abac_result: bool
    role_permissions: List[str]
    inherited_permissions: List[str]
    attribute_conditions: List[Dict[str, Any]]
    failed_conditions: List[Dict[str, Any]]
    decision_path: List[str]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "permission_granted": self.permission_granted,
            "rbac_result": self.rbac_result,
            "abac_result": self.abac_result,
            "role_permissions": self.role_permissions,
            "inherited_permissions": self.inherited_permissions,
            "attribute_conditions": self.attribute_conditions,
            "failed_conditions": self.failed_conditions,
            "decision_path": self.decision_path,
        }


@register_node()
class PermissionCheckNode(Node):
    """Enterprise permission checking node with RBAC/ABAC integration.

    This node provides comprehensive permission checking capabilities including:
    - Real-time RBAC and ABAC evaluation
    - Multi-level caching for performance
    - Batch permission checking
    - Permission explanation and debugging
    - Integration with user and role management
    - Multi-tenant permission isolation

    Parameters:
        operation: Type of permission check operation
        user_id: User ID for permission check
        user_ids: List of user IDs for bulk operations
        resource_id: Resource being accessed
        resource_ids: List of resources for batch checking
        permission: Permission being checked
        permissions: List of permissions for batch checking
        context: Additional context for ABAC evaluation
        cache_level: Level of caching to use
        cache_ttl: Cache time-to-live in seconds
        explain: Whether to provide detailed explanation
        tenant_id: Tenant isolation

    Example:
        >>> # Single permission check with caching
        >>> node = PermissionCheckNode(
        ...     operation="check_permission",
        ...     user_id="user123",
        ...     resource_id="sensitive_data",
        ...     permission="read",
        ...     cache_level="user",
        ...     cache_ttl=300,
        ...     explain=True
        ... )
        >>> result = node.execute()
        >>> allowed = result["check"]["allowed"]
        >>> explanation = result["explanation"]

        >>> # Batch permission checking
        >>> node = PermissionCheckNode(
        ...     operation="batch_check",
        ...     user_id="user123",
        ...     resource_ids=["data1", "data2", "data3"],
        ...     permissions=["read", "write", "delete"],
        ...     cache_level="full"
        ... )
        >>> result = node.execute()
        >>> results = result["batch_results"]

        >>> # Bulk user permission check
        >>> node = PermissionCheckNode(
        ...     operation="bulk_user_check",
        ...     user_ids=["user1", "user2", "user3"],
        ...     resource_id="workflow_execute",
        ...     permission="execute"
        ... )
        >>> result = node.execute()
        >>> access_matrix = result["access_matrix"]
    """

    def __init__(self, **config):
        super().__init__(**config)
        self._db_node = None
        self._access_manager = None
        self._attribute_evaluator = None
        self._permission_cache = {}
        self._cache_timestamps = {}
        self._schema_manager = None
        self.logger = logging.getLogger(__name__)

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Define parameters for permission checking operations."""
        return {
            param.name: param
            for param in [
                # Operation type
                NodeParameter(
                    name="operation",
                    type=str,
                    required=True,
                    description="Permission check operation to perform",
                    choices=[op.value for op in PermissionCheckOperation],
                ),
                # User identification
                NodeParameter(
                    name="user_id",
                    type=str,
                    required=False,
                    description="User ID for permission check",
                ),
                NodeParameter(
                    name="user_ids",
                    type=list,
                    required=False,
                    description="List of user IDs for bulk operations",
                ),
                # Resource identification
                NodeParameter(
                    name="resource_id",
                    type=str,
                    required=False,
                    description="Resource being accessed",
                ),
                NodeParameter(
                    name="resource_ids",
                    type=list,
                    required=False,
                    description="List of resources for batch checking",
                ),
                # Permission identification
                NodeParameter(
                    name="permission",
                    type=str,
                    required=False,
                    description="Permission being checked",
                ),
                NodeParameter(
                    name="permissions",
                    type=list,
                    required=False,
                    description="List of permissions for batch checking",
                ),
                # Context for ABAC
                NodeParameter(
                    name="context",
                    type=dict,
                    required=False,
                    description="Additional context for ABAC evaluation",
                ),
                # Caching configuration
                NodeParameter(
                    name="cache_level",
                    type=str,
                    required=False,
                    default="user",
                    choices=[level.value for level in CacheLevel],
                    description="Level of caching to use",
                ),
                NodeParameter(
                    name="cache_ttl",
                    type=int,
                    required=False,
                    default=300,
                    description="Cache time-to-live in seconds",
                ),
                # Output options
                NodeParameter(
                    name="explain",
                    type=bool,
                    required=False,
                    default=False,
                    description="Whether to provide detailed explanation",
                ),
                NodeParameter(
                    name="include_timing",
                    type=bool,
                    required=False,
                    default=True,
                    description="Include timing information in results",
                ),
                NodeParameter(
                    name="audit",
                    type=bool,
                    required=False,
                    default=False,
                    description="Enable audit logging for this operation",
                ),
                # Multi-tenancy
                NodeParameter(
                    name="tenant_id",
                    type=str,
                    required=False,
                    description="Tenant ID for multi-tenant isolation",
                ),
                # Database configuration
                NodeParameter(
                    name="database_config",
                    type=dict,
                    required=False,
                    description="Database connection configuration",
                ),
                # Validation options
                NodeParameter(
                    name="strict_validation",
                    type=bool,
                    required=False,
                    default=True,
                    description="Enable strict validation of inputs",
                ),
                # Additional validation options
                NodeParameter(
                    name="conditions",
                    type=list,
                    required=False,
                    description="List of ABAC conditions to validate",
                ),
                NodeParameter(
                    name="validate_syntax",
                    type=bool,
                    required=False,
                    default=True,
                    description="Validate condition syntax",
                ),
                NodeParameter(
                    name="test_evaluation",
                    type=bool,
                    required=False,
                    default=True,
                    description="Test condition evaluation with provided context",
                ),
                NodeParameter(
                    name="permission_type",
                    type=str,
                    required=False,
                    default="all",
                    choices=["all", "direct", "inherited"],
                    description="Type of permissions to return",
                ),
                NodeParameter(
                    name="check_inheritance",
                    type=bool,
                    required=False,
                    default=True,
                    description="Check hierarchical resource inheritance",
                ),
                NodeParameter(
                    name="include_rules",
                    type=bool,
                    required=False,
                    default=True,
                    description="Include rule details in explanation",
                ),
                NodeParameter(
                    name="include_hierarchy",
                    type=bool,
                    required=False,
                    default=True,
                    description="Include role hierarchy breakdown",
                ),
            ]
        }

    def run(self, **inputs) -> Dict[str, Any]:
        """Execute permission check operation."""
        try:
            operation = PermissionCheckOperation(inputs["operation"])

            # Initialize dependencies
            self._init_dependencies(inputs)

            # Route to appropriate operation
            if operation == PermissionCheckOperation.CHECK_PERMISSION:
                return self._check_permission(inputs)
            elif operation == PermissionCheckOperation.BATCH_CHECK:
                return self._batch_check(inputs)
            elif operation == PermissionCheckOperation.CHECK_NODE_ACCESS:
                return self._check_node_access(inputs)
            elif operation == PermissionCheckOperation.CHECK_WORKFLOW_ACCESS:
                return self._check_workflow_access(inputs)
            elif operation == PermissionCheckOperation.GET_USER_PERMISSIONS:
                return self._get_user_permissions(inputs)
            elif operation == PermissionCheckOperation.EXPLAIN_PERMISSION:
                return self._explain_permission(inputs)
            elif operation == PermissionCheckOperation.VALIDATE_CONDITIONS:
                return self._validate_conditions(inputs)
            elif operation == PermissionCheckOperation.CHECK_HIERARCHICAL:
                return self._check_hierarchical(inputs)
            elif operation == PermissionCheckOperation.BULK_USER_CHECK:
                return self._bulk_user_check(inputs)
            elif operation == PermissionCheckOperation.CLEAR_CACHE:
                return self._clear_cache(inputs)
            else:
                raise NodeExecutionError(f"Unknown operation: {operation}")

        except Exception as e:
            raise NodeExecutionError(f"Permission check operation failed: {str(e)}")

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
        self._db_node = SQLDatabaseNode(name="permission_check_db", **db_config)

        # Initialize schema manager and ensure schema exists
        if not self._schema_manager:
            self._schema_manager = AdminSchemaManager(db_config)

            # Validate schema exists, create if needed
            try:
                validation = self._schema_manager.validate_schema()
                if not validation["is_valid"]:
                    self.logger.info("Creating unified admin schema...")
                    self._schema_manager.create_full_schema(drop_existing=False)
                    self.logger.info("Unified admin schema created successfully")
            except Exception as e:
                self.logger.warning(f"Schema validation/creation failed: {e}")

        # Initialize enhanced access manager
        self._access_manager = AccessControlManager(strategy="abac")
        self._attribute_evaluator = AttributeEvaluator()

    def _check_permission(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Check a single permission with caching and explanation."""
        user_id = inputs["user_id"]
        resource_id = inputs["resource_id"]
        permission = inputs["permission"]
        tenant_id = inputs.get("tenant_id", "default")
        context = inputs.get("context", {})
        cache_level = CacheLevel(inputs.get("cache_level", "user"))
        cache_ttl = inputs.get("cache_ttl", 300)
        explain = inputs.get("explain", False)
        include_timing = inputs.get("include_timing", True)
        audit = inputs.get("audit", False)

        start_time = datetime.now(UTC) if include_timing else None

        # Check cache first
        cache_key = self._generate_cache_key(user_id, resource_id, permission, context)
        cached_result = (
            self._get_from_cache(cache_key, cache_ttl)
            if cache_level != CacheLevel.NONE
            else None
        )

        if cached_result:
            cached_result["cache_hit"] = True
            if include_timing:
                cached_result["evaluation_time_ms"] = 0.1  # Minimal cache lookup time

            result = {
                "result": {
                    "check": cached_result,
                    "operation": "check_permission",
                    "timestamp": datetime.now(UTC).isoformat(),
                }
            }

            if explain:
                result["result"]["explanation"] = cached_result.get("explanation", {})

            return result

        # Get user context
        user_context = self._get_user_context(user_id, tenant_id)
        if not user_context:
            raise NodeValidationError(f"User not found: {user_id}")

        # Perform RBAC check
        rbac_result = self._check_rbac_permission(user_context, resource_id, permission)

        # Perform ABAC check if needed
        abac_result = True  # Default to allow if no ABAC rules
        if context:
            abac_result = self._check_abac_permission(
                user_context, resource_id, permission, context
            )

        # Combine results
        allowed = rbac_result and abac_result

        # Build explanation if requested
        explanation = None
        if explain:
            explanation = self._build_permission_explanation(
                user_context, resource_id, permission, context, rbac_result, abac_result
            )

        # Calculate timing
        evaluation_time_ms = 0.0
        if include_timing and start_time:
            evaluation_time_ms = (datetime.now(UTC) - start_time).total_seconds() * 1000

        # Build result
        check_result = PermissionCheckResult(
            allowed=allowed,
            reason="Permission granted" if allowed else "Permission denied",
            applied_rules=[],  # Would be populated with actual rule IDs
            user_id=user_id,
            resource_id=resource_id,
            permission=permission,
            evaluation_time_ms=evaluation_time_ms,
            cached=False,
            cache_hit=False,
        )

        # Cache result if caching enabled
        if cache_level != CacheLevel.NONE:
            cache_data = check_result.to_dict()
            if explanation:
                cache_data["explanation"] = explanation.to_dict()
            self._set_cache(cache_key, cache_data, cache_ttl)

        # Log to audit trail if enabled
        if audit:
            self._create_audit_log(
                user_id=user_id,
                action="permission_check",
                resource_type="resource",
                resource_id=resource_id,
                details={
                    "permission": permission,
                    "allowed": allowed,
                    "context": context,
                    "rbac_result": rbac_result,
                    "abac_result": abac_result,
                },
                success=allowed,
                tenant_id=tenant_id,
            )

        result = {
            "result": {
                "check": check_result.to_dict(),
                "operation": "check_permission",
                "timestamp": datetime.now(UTC).isoformat(),
            }
        }

        if explain and explanation:
            result["result"]["explanation"] = explanation.to_dict()

        return result

    def _batch_check(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Check multiple permissions for a user efficiently."""
        user_id = inputs["user_id"]
        resource_ids = inputs.get("resource_ids", [inputs.get("resource_id")])
        permissions = inputs.get("permissions", [inputs.get("permission")])
        tenant_id = inputs.get("tenant_id", "default")
        context = inputs.get("context", {})

        if not resource_ids or not permissions:
            raise NodeValidationError(
                "resource_ids and permissions must be provided for batch check"
            )

        # Get user context once for efficiency
        user_context = self._get_user_context(user_id, tenant_id)
        if not user_context:
            raise NodeValidationError(f"User not found: {user_id}")

        batch_results = []
        stats = {"allowed": 0, "denied": 0, "total": 0}

        # Check each resource-permission combination
        for resource_id in resource_ids:
            for permission in permissions:
                try:
                    # Use single check method for consistency
                    check_inputs = {
                        "operation": "check_permission",
                        "user_id": user_id,
                        "resource_id": resource_id,
                        "permission": permission,
                        "context": context,
                        "tenant_id": tenant_id,
                        "cache_level": inputs.get("cache_level", "user"),
                        "cache_ttl": inputs.get("cache_ttl", 300),
                        "explain": False,  # Skip explanation for batch operations
                        "include_timing": False,
                    }

                    result = self._check_permission(check_inputs)
                    check_data = result["result"]["check"]

                    batch_results.append(
                        {
                            "resource_id": resource_id,
                            "permission": permission,
                            "allowed": check_data["allowed"],
                            "reason": check_data["reason"],
                        }
                    )

                    if check_data["allowed"]:
                        stats["allowed"] += 1
                    else:
                        stats["denied"] += 1
                    stats["total"] += 1

                except Exception as e:
                    batch_results.append(
                        {
                            "resource_id": resource_id,
                            "permission": permission,
                            "allowed": False,
                            "reason": f"Error: {str(e)}",
                        }
                    )
                    stats["denied"] += 1
                    stats["total"] += 1

        return {
            "result": {
                "batch_results": batch_results,
                "stats": stats,
                "user_id": user_id,
                "operation": "batch_check",
                "timestamp": datetime.now(UTC).isoformat(),
            }
        }

    def _bulk_user_check(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Check permission for multiple users against a resource."""
        user_ids = inputs["user_ids"]
        resource_id = inputs["resource_id"]
        permission = inputs["permission"]
        tenant_id = inputs.get("tenant_id", "default")
        context = inputs.get("context", {})

        if not isinstance(user_ids, list):
            raise NodeValidationError("user_ids must be a list for bulk operations")

        access_matrix = []
        stats = {"allowed": 0, "denied": 0, "total": 0}

        for user_id in user_ids:
            try:
                # Use single check method for consistency
                check_inputs = {
                    "operation": "check_permission",
                    "user_id": user_id,
                    "resource_id": resource_id,
                    "permission": permission,
                    "context": context,
                    "tenant_id": tenant_id,
                    "cache_level": inputs.get("cache_level", "user"),
                    "cache_ttl": inputs.get("cache_ttl", 300),
                    "explain": False,
                    "include_timing": False,
                }

                result = self._check_permission(check_inputs)
                check_data = result["result"]["check"]

                access_matrix.append(
                    {
                        "user_id": user_id,
                        "allowed": check_data["allowed"],
                        "reason": check_data["reason"],
                        "cache_hit": check_data.get("cache_hit", False),
                    }
                )

                if check_data["allowed"]:
                    stats["allowed"] += 1
                else:
                    stats["denied"] += 1
                stats["total"] += 1

            except Exception as e:
                access_matrix.append(
                    {
                        "user_id": user_id,
                        "allowed": False,
                        "reason": f"Error: {str(e)}",
                        "cache_hit": False,
                    }
                )
                stats["denied"] += 1
                stats["total"] += 1

        return {
            "result": {
                "access_matrix": access_matrix,
                "stats": stats,
                "resource_id": resource_id,
                "permission": permission,
                "operation": "bulk_user_check",
                "timestamp": datetime.now(UTC).isoformat(),
            }
        }

    def _get_user_context(self, user_id: str, tenant_id: str) -> Optional[UserContext]:
        """Get user context for permission evaluation with strict tenant isolation."""
        # Query user data and assigned roles from unified admin schema
        user_query = """
        SELECT user_id, email, attributes, status, tenant_id
        FROM users
        WHERE user_id = $1 AND tenant_id = $2 AND status = 'active'
        """

        # Get assigned roles from user_role_assignments table with strict tenant isolation
        roles_query = """
        SELECT role_id
        FROM user_role_assignments
        WHERE user_id = $1 AND tenant_id = $2 AND is_active = true
        """

        try:
            # Get user data - strict tenant check
            user_result = self._db_node.execute(
                query=user_query, parameters=[user_id, tenant_id], result_format="dict"
            )

            user_rows = user_result.get("data", [])
            if not user_rows:
                # User not found in this tenant - strict tenant isolation
                self.logger.debug(f"User {user_id} not found in tenant {tenant_id}")
                return None

            user_data = user_rows[0]

            # Verify tenant isolation - ensure user belongs to the requested tenant
            if user_data.get("tenant_id") != tenant_id:
                self.logger.warning(
                    f"Tenant isolation violation: User {user_id} belongs to {user_data.get('tenant_id')} but permission check requested for {tenant_id}"
                )
                return None

            # Get assigned roles - also with strict tenant isolation
            roles_result = self._db_node.execute(
                query=roles_query, parameters=[user_id, tenant_id], result_format="dict"
            )

            role_rows = roles_result.get("data", [])
            assigned_roles = [row["role_id"] for row in role_rows]

            # Log for debugging tenant isolation
            self.logger.debug(
                f"User {user_id} in tenant {tenant_id} has roles: {assigned_roles}"
            )

            return UserContext(
                user_id=user_data["user_id"],
                tenant_id=user_data["tenant_id"],
                email=user_data["email"],
                roles=assigned_roles,
                attributes=user_data.get("attributes", {}),
            )
        except Exception as e:
            # Log the error and return None to indicate user not found
            self.logger.warning(
                f"Failed to get user context for {user_id} in tenant {tenant_id}: {e}"
            )
            return None

    def _check_rbac_permission(
        self, user_context: UserContext, resource_id: str, permission: str
    ) -> bool:
        """Check RBAC permission using role-based access."""
        # Get user's effective permissions from roles
        user_permissions = self._get_user_effective_permissions(user_context)

        # Check if user has the required permission
        required_permission = f"{resource_id}:{permission}"

        # Check for exact match or wildcard permissions
        if required_permission in user_permissions:
            return True

        # Check for wildcard permissions
        wildcard_permission = f"{resource_id}:*"
        if wildcard_permission in user_permissions:
            return True

        # Check for global permissions
        global_permission = f"*:{permission}"
        if global_permission in user_permissions:
            return True

        return False

    def _check_abac_permission(
        self,
        user_context: UserContext,
        resource_id: str,
        permission: str,
        context: Dict[str, Any],
    ) -> bool:
        """Check ABAC permission using attribute-based access."""
        # Use the enhanced access control manager for ABAC evaluation
        try:
            # Convert permission string to NodePermission if possible
            node_permission = NodePermission.EXECUTE  # Default
            if permission.lower() in ["read", "view"]:
                node_permission = NodePermission.READ_OUTPUT  # Map view to read_output
            elif permission.lower() in ["write", "edit", "update"]:
                node_permission = NodePermission.WRITE_INPUT  # Map edit to write_input
            elif permission.lower() in ["execute", "run"]:
                node_permission = NodePermission.EXECUTE
            elif permission.lower() in ["delete", "remove"]:
                node_permission = NodePermission.DELETE

            # Check access using the enhanced access control manager
            decision = self._access_manager.check_node_access(
                user=user_context,
                resource_id=resource_id,
                permission=node_permission,
                context=context,
            )

            return decision.allowed

        except Exception as e:
            # If ABAC evaluation fails, default to deny
            return False

    def _get_user_effective_permissions(self, user_context: UserContext) -> Set[str]:
        """Get all effective permissions for a user including inherited permissions."""
        permissions = set()

        # Get permissions from each role
        for role in user_context.roles:
            role_permissions = self._get_role_permissions(role, user_context.tenant_id)
            permissions.update(role_permissions)

        return permissions

    def _get_role_permissions(self, role_id: str, tenant_id: str) -> Set[str]:
        """Get permissions for a specific role including inherited permissions with strict tenant isolation."""
        # Query role and its hierarchy with strict tenant boundaries
        query = """
        WITH RECURSIVE role_hierarchy AS (
            SELECT role_id, permissions, parent_roles, tenant_id
            FROM roles
            WHERE role_id = $1 AND tenant_id = $2 AND is_active = true

            UNION ALL

            SELECT r.role_id, r.permissions, r.parent_roles, r.tenant_id
            FROM roles r
            JOIN role_hierarchy rh ON r.role_id = ANY(
                SELECT jsonb_array_elements_text(rh.parent_roles)
            )
            WHERE r.tenant_id = $3 AND r.is_active = true
        )
        SELECT DISTINCT unnest(
            CASE
                WHEN jsonb_typeof(permissions) = 'array'
                THEN ARRAY(SELECT jsonb_array_elements_text(permissions))
                WHEN permissions IS NOT NULL AND permissions::text != 'null'
                THEN ARRAY[permissions::text]
                ELSE ARRAY[]::text[]
            END
        ) as permission
        FROM role_hierarchy
        WHERE tenant_id = $4
        """

        try:
            result = self._db_node.execute(
                query=query,
                parameters=[role_id, tenant_id, tenant_id, tenant_id],
                result_format="dict",
            )
            permission_rows = result.get("data", [])

            permissions = {
                row["permission"] for row in permission_rows if row["permission"]
            }
            self.logger.debug(
                f"Role {role_id} in tenant {tenant_id} has permissions: {permissions}"
            )

            return permissions
        except Exception as e:
            self.logger.warning(
                f"Failed to get permissions for role {role_id} in tenant {tenant_id}: {e}"
            )
            return set()

    def _build_permission_explanation(
        self,
        user_context: UserContext,
        resource_id: str,
        permission: str,
        context: Dict[str, Any],
        rbac_result: bool,
        abac_result: bool,
    ) -> PermissionExplanation:
        """Build detailed explanation of permission evaluation."""
        # Get role permissions
        role_permissions = []
        inherited_permissions = []

        for role in user_context.roles:
            perms = self._get_role_permissions(role, user_context.tenant_id)
            role_permissions.extend(list(perms))

        # Build decision path
        decision_path = []
        decision_path.append(f"User: {user_context.user_id}")
        decision_path.append(f"Roles: {', '.join(user_context.roles)}")
        decision_path.append(f"RBAC Result: {'ALLOW' if rbac_result else 'DENY'}")
        decision_path.append(f"ABAC Result: {'ALLOW' if abac_result else 'DENY'}")
        decision_path.append(
            f"Final Decision: {'ALLOW' if rbac_result and abac_result else 'DENY'}"
        )

        return PermissionExplanation(
            permission_granted=rbac_result and abac_result,
            rbac_result=rbac_result,
            abac_result=abac_result,
            role_permissions=role_permissions,
            inherited_permissions=inherited_permissions,
            attribute_conditions=[],  # Would be populated with actual conditions
            failed_conditions=[],  # Would be populated with failed conditions
            decision_path=decision_path,
        )

    # Caching utilities
    def _generate_cache_key(
        self, user_id: str, resource_id: str, permission: str, context: Dict[str, Any]
    ) -> str:
        """Generate cache key for permission check."""
        # Create a hash of the context for consistent caching
        context_str = json.dumps(context, sort_keys=True) if context else ""
        cache_data = f"{user_id}:{resource_id}:{permission}:{context_str}"
        return hashlib.sha256(cache_data.encode()).hexdigest()

    def _get_from_cache(
        self, cache_key: str, cache_ttl: int
    ) -> Optional[Dict[str, Any]]:
        """Get cached permission result if still valid."""
        if cache_key not in self._permission_cache:
            return None

        # Check if cache entry is still valid
        cache_time = self._cache_timestamps.get(cache_key)
        if not cache_time:
            return None

        if (datetime.now(UTC) - cache_time).total_seconds() > cache_ttl:
            # Cache expired, remove entry
            self._permission_cache.pop(cache_key, None)
            self._cache_timestamps.pop(cache_key, None)
            return None

        return self._permission_cache[cache_key]

    def _set_cache(self, cache_key: str, result: Dict[str, Any], cache_ttl: int):
        """Set permission result in cache."""
        self._permission_cache[cache_key] = result
        self._cache_timestamps[cache_key] = datetime.now(UTC)

    def _clear_cache(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Clear permission cache."""
        cache_size_before = len(self._permission_cache)
        self._permission_cache.clear()
        self._cache_timestamps.clear()

        return {
            "result": {
                "cache_cleared": True,
                "entries_removed": cache_size_before,
                "operation": "clear_cache",
                "timestamp": datetime.now(UTC).isoformat(),
            }
        }

    # Additional operations would follow similar patterns
    def _check_node_access(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Check access to a specific node type."""
        user_id = inputs["user_id"]
        node_type = inputs["resource_id"]  # node_type is passed as resource_id
        permission = inputs.get("permission", "execute")  # Default to execute
        tenant_id = inputs.get("tenant_id", "default")
        context = inputs.get("context", {})

        # Get user context
        user_context = self._get_user_context(user_id, tenant_id)
        if not user_context:
            raise NodeValidationError(f"User not found: {user_id}")

        # Map permission string to NodePermission enum
        permission_mapping = {
            "view": NodePermission.READ_OUTPUT,  # Map view to read_output
            "edit": NodePermission.WRITE_INPUT,  # Map edit to write_input
            "execute": NodePermission.EXECUTE,
            "delete": NodePermission.SKIP,  # Map delete to skip (no direct delete permission)
        }

        node_permission = permission_mapping.get(
            permission.lower(), NodePermission.EXECUTE
        )

        start_time = datetime.now(UTC)

        # Use the access control manager for node access check
        try:
            decision = self._access_manager.check_node_access(
                user=user_context,
                resource_id=node_type,
                permission=node_permission,
                context=context,
            )

            evaluation_time_ms = (datetime.now(UTC) - start_time).total_seconds() * 1000

            return {
                "result": {
                    "access_check": {
                        "allowed": decision.allowed,
                        "reason": decision.reason,
                        "user_id": user_id,
                        "node_type": node_type,
                        "permission": permission,
                        "evaluation_time_ms": evaluation_time_ms,
                        "decision_id": decision.decision_id,
                    },
                    "operation": "check_node_access",
                    "timestamp": datetime.now(UTC).isoformat(),
                }
            }

        except Exception as e:
            return {
                "result": {
                    "access_check": {
                        "allowed": False,
                        "reason": f"Access check failed: {str(e)}",
                        "user_id": user_id,
                        "node_type": node_type,
                        "permission": permission,
                        "evaluation_time_ms": (
                            datetime.now(UTC) - start_time
                        ).total_seconds()
                        * 1000,
                        "error": True,
                    },
                    "operation": "check_node_access",
                    "timestamp": datetime.now(UTC).isoformat(),
                }
            }

    def _check_workflow_access(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Check access to workflow operations."""
        user_id = inputs["user_id"]
        workflow_id = inputs["resource_id"]  # workflow_id is passed as resource_id
        permission = inputs.get("permission", "execute")  # execute, view, edit, delete
        tenant_id = inputs.get("tenant_id", "default")
        context = inputs.get("context", {})

        # Get user context
        user_context = self._get_user_context(user_id, tenant_id)
        if not user_context:
            raise NodeValidationError(f"User not found: {user_id}")

        # Map permission string to WorkflowPermission enum
        permission_mapping = {
            "view": WorkflowPermission.VIEW,
            "execute": WorkflowPermission.EXECUTE,
            "edit": WorkflowPermission.MODIFY,  # EDIT mapped to MODIFY
            "delete": WorkflowPermission.DELETE,
            "deploy": WorkflowPermission.DEPLOY,
            "share": WorkflowPermission.SHARE,
        }

        workflow_permission = permission_mapping.get(
            permission.lower(), WorkflowPermission.EXECUTE
        )

        start_time = datetime.now(UTC)

        # Use the access control manager for workflow access check
        try:
            decision = self._access_manager.check_workflow_access(
                user=user_context,
                workflow_id=workflow_id,
                permission=workflow_permission,
                context=context,
            )

            evaluation_time_ms = (datetime.now(UTC) - start_time).total_seconds() * 1000

            return {
                "result": {
                    "access_check": {
                        "allowed": decision.allowed,
                        "reason": decision.reason,
                        "user_id": user_id,
                        "workflow_id": workflow_id,
                        "permission": permission,
                        "evaluation_time_ms": evaluation_time_ms,
                        "decision_id": decision.decision_id,
                        "applied_rules": getattr(decision, "applied_rules", []),
                    },
                    "operation": "check_workflow_access",
                    "timestamp": datetime.now(UTC).isoformat(),
                }
            }

        except Exception as e:
            return {
                "result": {
                    "access_check": {
                        "allowed": False,
                        "reason": f"Workflow access check failed: {str(e)}",
                        "user_id": user_id,
                        "workflow_id": workflow_id,
                        "permission": permission,
                        "evaluation_time_ms": (
                            datetime.now(UTC) - start_time
                        ).total_seconds()
                        * 1000,
                        "error": True,
                    },
                    "operation": "check_workflow_access",
                    "timestamp": datetime.now(UTC).isoformat(),
                }
            }

    def _get_user_permissions(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Get all permissions for a user."""
        user_id = inputs["user_id"]
        tenant_id = inputs.get("tenant_id", "default")
        include_inherited = inputs.get("include_inherited", True)
        permission_type = inputs.get("permission_type", "all")  # all, direct, inherited

        # Get user context
        user_context = self._get_user_context(user_id, tenant_id)
        if not user_context:
            raise NodeValidationError(f"User not found: {user_id}")

        start_time = datetime.now(UTC)

        # Get all effective permissions
        all_permissions = self._get_user_effective_permissions(user_context)

        # Get direct permissions from roles
        direct_permissions = set()
        role_permissions_breakdown = {}

        for role in user_context.roles:
            role_perms = self._get_role_direct_permissions(role, tenant_id)
            direct_permissions.update(role_perms)
            role_permissions_breakdown[role] = list(role_perms)

        # Calculate inherited permissions
        inherited_permissions = (
            all_permissions - direct_permissions if include_inherited else set()
        )

        # Filter based on permission_type
        result_permissions = set()
        if permission_type == "all":
            result_permissions = all_permissions
        elif permission_type == "direct":
            result_permissions = direct_permissions
        elif permission_type == "inherited":
            result_permissions = inherited_permissions

        # Categorize permissions by resource type
        categorized_permissions = {
            "workflow": [],
            "node": [],
            "resource": [],
            "admin": [],
            "other": [],
        }

        for perm in result_permissions:
            if perm.startswith("workflow:"):
                categorized_permissions["workflow"].append(perm)
            elif perm.startswith("node:"):
                categorized_permissions["node"].append(perm)
            elif perm.startswith("resource:"):
                categorized_permissions["resource"].append(perm)
            elif perm.startswith("admin:"):
                categorized_permissions["admin"].append(perm)
            else:
                categorized_permissions["other"].append(perm)

        evaluation_time_ms = (datetime.now(UTC) - start_time).total_seconds() * 1000

        return {
            "result": {
                "user_permissions": {
                    "user_id": user_id,
                    "permissions": list(result_permissions),
                    "categorized_permissions": categorized_permissions,
                    "role_breakdown": role_permissions_breakdown,
                    "permission_counts": {
                        "total": len(all_permissions),
                        "direct": len(direct_permissions),
                        "inherited": len(inherited_permissions),
                        "returned": len(result_permissions),
                    },
                    "evaluation_time_ms": evaluation_time_ms,
                },
                "options": {
                    "include_inherited": include_inherited,
                    "permission_type": permission_type,
                },
                "operation": "get_user_permissions",
                "timestamp": datetime.now(UTC).isoformat(),
            }
        }

    def _get_role_direct_permissions(self, role_id: str, tenant_id: str) -> Set[str]:
        """Get direct permissions for a role (no inheritance) with proper format handling."""
        query = """
        SELECT permissions
        FROM roles
        WHERE role_id = $1 AND tenant_id = $2 AND is_active = true
        """

        try:
            result = self._db_node.execute(
                query=query, parameters=[role_id, tenant_id], result_format="dict"
            )
            role_rows = result.get("data", [])
            role_data = role_rows[0] if role_rows else None

            if not role_data:
                self.logger.debug(f"Role {role_id} not found in tenant {tenant_id}")
                return set()

            permissions_data = role_data.get("permissions", [])

            # Handle different permission storage formats
            if isinstance(permissions_data, list):
                permissions = set(permissions_data)
            elif isinstance(permissions_data, str):
                try:
                    # Try to parse as JSON array
                    import json

                    parsed = json.loads(permissions_data)
                    permissions = (
                        set(parsed) if isinstance(parsed, list) else {permissions_data}
                    )
                except (json.JSONDecodeError, TypeError):
                    # Treat as single permission string
                    permissions = {permissions_data} if permissions_data else set()
            else:
                permissions = set()

            self.logger.debug(
                f"Role {role_id} direct permissions in tenant {tenant_id}: {permissions}"
            )
            return permissions

        except Exception as e:
            self.logger.warning(
                f"Failed to get direct permissions for role {role_id} in tenant {tenant_id}: {e}"
            )
            return set()

    def _explain_permission(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Provide detailed explanation of permission logic."""
        user_id = inputs["user_id"]
        resource_id = inputs["resource_id"]
        permission = inputs["permission"]
        tenant_id = inputs.get("tenant_id", "default")
        context = inputs.get("context", {})
        include_rules = inputs.get("include_rules", True)
        include_hierarchy = inputs.get("include_hierarchy", True)

        # Get user context
        user_context = self._get_user_context(user_id, tenant_id)
        if not user_context:
            raise NodeValidationError(f"User not found: {user_id}")

        start_time = datetime.now(UTC)

        # Perform detailed permission check with explanation
        rbac_result = self._check_rbac_permission(user_context, resource_id, permission)
        abac_result = self._check_abac_permission(
            user_context, resource_id, permission, context
        )
        final_result = rbac_result and abac_result

        # Build comprehensive explanation
        explanation = {
            "permission_granted": final_result,
            "evaluation_steps": [],
            "rbac_analysis": {},
            "abac_analysis": {},
            "decision_factors": [],
        }

        # RBAC Analysis
        user_permissions = self._get_user_effective_permissions(user_context)
        required_permission = f"{resource_id}:{permission}"
        wildcard_resource = f"{resource_id}:*"
        wildcard_permission = f"*:{permission}"
        global_wildcard = "*:*"

        rbac_matches = []
        if required_permission in user_permissions:
            rbac_matches.append({"type": "exact", "permission": required_permission})
        if wildcard_resource in user_permissions:
            rbac_matches.append(
                {"type": "resource_wildcard", "permission": wildcard_resource}
            )
        if wildcard_permission in user_permissions:
            rbac_matches.append(
                {"type": "permission_wildcard", "permission": wildcard_permission}
            )
        if global_wildcard in user_permissions:
            rbac_matches.append(
                {"type": "global_wildcard", "permission": global_wildcard}
            )

        explanation["rbac_analysis"] = {
            "result": rbac_result,
            "required_permission": required_permission,
            "matching_permissions": rbac_matches,
            "user_roles": user_context.roles,
            "total_permissions": len(user_permissions),
        }

        # ABAC Analysis
        explanation["abac_analysis"] = {
            "result": abac_result,
            "context_provided": context,
            "user_attributes": user_context.attributes,
            "evaluation_method": "access_control_manager",
        }

        # Role hierarchy breakdown if requested
        if include_hierarchy:
            role_hierarchy_breakdown = {}
            for role in user_context.roles:
                direct_perms = self._get_role_direct_permissions(role, tenant_id)
                inherited_perms = (
                    self._get_role_permissions(role, tenant_id) - direct_perms
                )

                role_hierarchy_breakdown[role] = {
                    "direct_permissions": list(direct_perms),
                    "inherited_permissions": list(inherited_perms),
                    "has_required_permission": required_permission
                    in (direct_perms | inherited_perms),
                }

            explanation["role_hierarchy"] = role_hierarchy_breakdown

        # Decision factors
        if rbac_result:
            explanation["decision_factors"].append(
                "RBAC: User has required permission through role assignment"
            )
        else:
            explanation["decision_factors"].append(
                "RBAC: User lacks required permission"
            )

        if context:
            if abac_result:
                explanation["decision_factors"].append(
                    "ABAC: Context attributes satisfy policy conditions"
                )
            else:
                explanation["decision_factors"].append(
                    "ABAC: Context attributes do not satisfy policy conditions"
                )
        else:
            explanation["decision_factors"].append(
                "ABAC: No context provided, defaulting to allow"
            )

        explanation["decision_factors"].append(
            f"Final Decision: {'ALLOW' if final_result else 'DENY'}"
        )

        # Evaluation steps
        explanation["evaluation_steps"] = [
            f"1. Retrieved user context for {user_id}",
            f"2. Evaluated RBAC permissions: {'PASS' if rbac_result else 'FAIL'}",
            f"3. Evaluated ABAC conditions: {'PASS' if abac_result else 'FAIL'}",
            f"4. Combined results: {'ALLOW' if final_result else 'DENY'}",
        ]

        evaluation_time_ms = (datetime.now(UTC) - start_time).total_seconds() * 1000

        return {
            "result": {
                "explanation": explanation,
                "summary": {
                    "permission_granted": final_result,
                    "user_id": user_id,
                    "resource_id": resource_id,
                    "permission": permission,
                    "evaluation_time_ms": evaluation_time_ms,
                },
                "operation": "explain_permission",
                "timestamp": datetime.now(UTC).isoformat(),
            }
        }

    def _validate_conditions(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Validate ABAC conditions and rules."""
        conditions = inputs.get("conditions", [])
        context = inputs.get("context", {})
        user_id = inputs.get("user_id")
        tenant_id = inputs.get("tenant_id", "default")
        validate_syntax = inputs.get("validate_syntax", True)
        test_evaluation = inputs.get("test_evaluation", True)

        start_time = datetime.now(UTC)
        validation_results = {
            "valid_conditions": [],
            "invalid_conditions": [],
            "syntax_errors": [],
            "evaluation_errors": [],
            "total_conditions": len(conditions),
            "valid_count": 0,
            "invalid_count": 0,
        }

        # Get user context for testing if user_id provided
        user_context = None
        if user_id:
            user_context = self._get_user_context(user_id, tenant_id)

        for i, condition in enumerate(conditions):
            condition_result = {
                "index": i,
                "condition": condition,
                "valid": True,
                "errors": [],
            }

            # Validate syntax if requested
            if validate_syntax:
                try:
                    # Basic structure validation
                    if not isinstance(condition, dict):
                        condition_result["errors"].append(
                            "Condition must be a dictionary"
                        )
                        condition_result["valid"] = False
                    else:
                        required_fields = ["attribute", "operator", "value"]
                        for field in required_fields:
                            if field not in condition:
                                condition_result["errors"].append(
                                    f"Missing required field: {field}"
                                )
                                condition_result["valid"] = False

                        # Validate operator
                        valid_operators = [
                            "eq",
                            "ne",
                            "lt",
                            "le",
                            "gt",
                            "ge",
                            "in",
                            "not_in",
                            "contains",
                            "regex",
                        ]
                        if (
                            "operator" in condition
                            and condition["operator"] not in valid_operators
                        ):
                            condition_result["errors"].append(
                                f"Invalid operator: {condition['operator']}. Valid operators: {valid_operators}"
                            )
                            condition_result["valid"] = False

                except Exception as e:
                    condition_result["errors"].append(
                        f"Syntax validation error: {str(e)}"
                    )
                    condition_result["valid"] = False

            # Test evaluation if requested and syntax is valid
            if test_evaluation and condition_result["valid"] and context:
                try:
                    # Create an AttributeCondition for testing
                    attr_condition = AttributeCondition(
                        attribute=condition["attribute"],
                        operator=AttributeOperator(condition["operator"]),
                        value=condition["value"],
                    )

                    # Test evaluation with provided context
                    test_context = context.copy()
                    if user_context:
                        test_context.update(user_context.attributes)

                    # Use the attribute evaluator to test
                    result = self._attribute_evaluator.evaluate_condition(
                        attr_condition, test_context
                    )
                    condition_result["evaluation_result"] = result
                    condition_result["test_context"] = test_context

                except Exception as e:
                    condition_result["errors"].append(f"Evaluation error: {str(e)}")
                    condition_result["valid"] = False
                    validation_results["evaluation_errors"].append(
                        {"condition_index": i, "error": str(e)}
                    )

            # Categorize result
            if condition_result["valid"]:
                validation_results["valid_conditions"].append(condition_result)
                validation_results["valid_count"] += 1
            else:
                validation_results["invalid_conditions"].append(condition_result)
                validation_results["invalid_count"] += 1

                if condition_result["errors"]:
                    validation_results["syntax_errors"].extend(
                        [
                            {"condition_index": i, "error": error}
                            for error in condition_result["errors"]
                        ]
                    )

        evaluation_time_ms = (datetime.now(UTC) - start_time).total_seconds() * 1000

        return {
            "result": {
                "validation": validation_results,
                "summary": {
                    "all_valid": validation_results["invalid_count"] == 0,
                    "success_rate": validation_results["valid_count"]
                    / max(validation_results["total_conditions"], 1)
                    * 100,
                    "evaluation_time_ms": evaluation_time_ms,
                },
                "options": {
                    "validate_syntax": validate_syntax,
                    "test_evaluation": test_evaluation,
                    "context_provided": bool(context),
                    "user_context_used": user_context is not None,
                },
                "operation": "validate_conditions",
                "timestamp": datetime.now(UTC).isoformat(),
            }
        }

    def _check_hierarchical(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Check permissions with hierarchical resource access."""
        user_id = inputs["user_id"]
        resource_path = inputs["resource_id"]  # e.g., "org/team/project/workflow"
        permission = inputs["permission"]
        tenant_id = inputs.get("tenant_id", "default")
        context = inputs.get("context", {})
        check_inheritance = inputs.get("check_inheritance", True)

        # Get user context
        user_context = self._get_user_context(user_id, tenant_id)
        if not user_context:
            raise NodeValidationError(f"User not found: {user_id}")

        start_time = datetime.now(UTC)

        # Parse resource hierarchy
        resource_parts = resource_path.split("/")
        hierarchical_checks = []

        # Check permission at each level if inheritance is enabled
        if check_inheritance:
            # Check from most specific to most general
            for i in range(len(resource_parts), 0, -1):
                partial_path = "/".join(resource_parts[:i])

                # Check exact permission
                exact_check = self._check_rbac_permission(
                    user_context, partial_path, permission
                )

                # Check wildcard permission at this level
                wildcard_check = self._check_rbac_permission(
                    user_context, partial_path, "*"
                )

                hierarchical_checks.append(
                    {
                        "resource_level": partial_path,
                        "depth": i,
                        "exact_permission": exact_check,
                        "wildcard_permission": wildcard_check,
                        "grants_access": exact_check or wildcard_check,
                    }
                )

                # If we found access at this level, we can stop (inheritance works)
                if exact_check or wildcard_check:
                    break
        else:
            # Only check the exact resource path
            exact_check = self._check_rbac_permission(
                user_context, resource_path, permission
            )
            wildcard_check = self._check_rbac_permission(
                user_context, resource_path, "*"
            )

            hierarchical_checks.append(
                {
                    "resource_level": resource_path,
                    "depth": len(resource_parts),
                    "exact_permission": exact_check,
                    "wildcard_permission": wildcard_check,
                    "grants_access": exact_check or wildcard_check,
                }
            )

        # Determine if access is granted
        access_granted = any(check["grants_access"] for check in hierarchical_checks)

        # Find the granting level
        granting_level = None
        for check in hierarchical_checks:
            if check["grants_access"]:
                granting_level = check["resource_level"]
                break

        # Perform ABAC check if context provided
        abac_result = True
        if context:
            abac_result = self._check_abac_permission(
                user_context, resource_path, permission, context
            )

        final_result = access_granted and abac_result

        evaluation_time_ms = (datetime.now(UTC) - start_time).total_seconds() * 1000

        return {
            "result": {
                "hierarchical_check": {
                    "allowed": final_result,
                    "rbac_result": access_granted,
                    "abac_result": abac_result,
                    "user_id": user_id,
                    "resource_path": resource_path,
                    "permission": permission,
                    "granting_level": granting_level,
                    "inheritance_used": check_inheritance
                    and granting_level != resource_path,
                    "hierarchy_checks": hierarchical_checks,
                    "evaluation_time_ms": evaluation_time_ms,
                },
                "options": {
                    "check_inheritance": check_inheritance,
                    "context_provided": bool(context),
                },
                "operation": "check_hierarchical",
                "timestamp": datetime.now(UTC).isoformat(),
            }
        }

    def _create_audit_log(
        self,
        user_id: str,
        action: str,
        resource_type: str,
        resource_id: str,
        details: Dict[str, Any],
        success: bool,
        tenant_id: str,
    ):
        """Create an audit log entry for the permission check."""
        try:
            audit_query = """
            INSERT INTO admin_audit_log (
                user_id, action, resource_type, resource_id,
                operation, context, success, tenant_id, created_at
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            """

            self._db_node.execute(
                query=audit_query,
                parameters=[
                    user_id,
                    action,
                    resource_type,
                    resource_id,
                    "permission_check",
                    json.dumps(details),
                    success,
                    tenant_id,
                    datetime.now(UTC),
                ],
            )
        except Exception as e:
            self.logger.warning(f"Failed to create audit log: {e}")
            # Don't fail the permission check if audit logging fails

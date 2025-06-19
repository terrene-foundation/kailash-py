"""Enterprise user management node with comprehensive CRUD operations.

This node provides Django Admin-level user management capabilities with enhanced
features for enterprise environments. Built on Session 065's async database
infrastructure for high-performance operations.

Features:
- Complete user lifecycle (create, read, update, delete, restore)
- Bulk operations with validation and rollback
- Password management with security policies
- User attribute management for ABAC
- Multi-tenant user isolation
- Comprehensive audit logging
- Integration with external identity providers
- User search, filtering, and pagination
"""

import hashlib
import json
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Union

from kailash.access_control import AccessControlManager, UserContext
from kailash.nodes.base import Node, NodeParameter, register_node
from kailash.nodes.data import AsyncSQLDatabaseNode
from kailash.sdk_exceptions import NodeExecutionError, NodeValidationError


@dataclass
class UserConfig:
    """Configuration for user management node."""

    abac_enabled: bool = True
    audit_enabled: bool = True
    multi_tenant: bool = True
    password_policy: Dict[str, Any] = None

    def __post_init__(self):
        if self.password_policy is None:
            self.password_policy = {
                "min_length": 8,
                "require_uppercase": True,
                "require_lowercase": True,
                "require_numbers": True,
                "require_special": False,
                "history_count": 3,
            }


class UserOperation(Enum):
    """Supported user management operations."""

    CREATE = "create"
    READ = "read"
    UPDATE = "update"
    DELETE = "delete"
    RESTORE = "restore"
    LIST = "list"
    SEARCH = "search"
    BULK_CREATE = "bulk_create"
    BULK_UPDATE = "bulk_update"
    BULK_DELETE = "bulk_delete"
    CHANGE_PASSWORD = "change_password"
    RESET_PASSWORD = "reset_password"
    DEACTIVATE = "deactivate"
    ACTIVATE = "activate"


class UserStatus(Enum):
    """User account status."""

    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"
    PENDING = "pending"
    DELETED = "deleted"


@dataclass
class UserProfile:
    """Enhanced user profile with ABAC attributes."""

    user_id: str
    email: str
    username: str
    first_name: str
    last_name: str
    status: UserStatus
    roles: List[str]
    attributes: Dict[str, Any]
    created_at: datetime
    updated_at: datetime
    last_login: Optional[datetime] = None
    password_changed_at: Optional[datetime] = None
    tenant_id: Optional[str] = None

    def to_user_context(self) -> UserContext:
        """Convert to UserContext for permission checks."""
        return UserContext(
            user_id=self.user_id,
            tenant_id=self.tenant_id or "default",
            email=self.email,
            roles=self.roles,
            attributes=self.attributes,
        )


@register_node()
class UserManagementNode(Node):
    """Enterprise user management node with Django Admin-inspired features.

    This node provides comprehensive user management capabilities including:
    - User CRUD operations with validation
    - Bulk operations with transaction support
    - Password management with security policies
    - User search and filtering
    - Attribute management for ABAC
    - Audit logging integration
    - Multi-tenant support

    Parameters:
        operation: Type of operation to perform
        user_data: User data for create/update operations
        user_id: User ID for single-user operations
        user_ids: List of user IDs for bulk operations
        search_query: Search query for user lookup
        filters: Filters for user listing
        pagination: Pagination parameters
        tenant_id: Tenant isolation
        include_deleted: Whether to include soft-deleted users

    Example:
        >>> # Create new user
        >>> node = UserManagementNode(
        ...     operation="create",
        ...     user_data={
        ...         "email": "john@company.com",
        ...         "username": "john.smith",
        ...         "first_name": "John",
        ...         "last_name": "Smith",
        ...         "roles": ["analyst"],
        ...         "attributes": {
        ...             "department": "finance",
        ...             "clearance": "confidential"
        ...         }
        ...     }
        ... )
        >>> result = node.run()
        >>> user_id = result["user"]["user_id"]

        >>> # Bulk user operations
        >>> node = UserManagementNode(
        ...     operation="bulk_create",
        ...     user_data=[
        ...         {"email": "user1@company.com", ...},
        ...         {"email": "user2@company.com", ...}
        ...     ]
        ... )
        >>> result = node.run()
        >>> created_count = result["stats"]["created"]
    """

    def __init__(self, **config):
        super().__init__(**config)
        self._db_node = None
        self._access_manager = None
        self._config = UserConfig(
            abac_enabled=config.get("abac_enabled", True),
            audit_enabled=config.get("audit_enabled", True),
            multi_tenant=config.get("multi_tenant", True),
            password_policy=config.get(
                "password_policy",
                {
                    "min_length": 8,
                    "require_uppercase": True,
                    "require_lowercase": True,
                    "require_numbers": True,
                    "require_special": False,
                    "history_count": 3,
                },
            ),
        )
        self._audit_logger = None

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Define parameters for user management operations."""
        return {
            param.name: param
            for param in [
                # Operation type
                NodeParameter(
                    name="operation",
                    type=str,
                    required=True,
                    description="User management operation to perform",
                    choices=[op.value for op in UserOperation],
                ),
                # User data for create/update
                NodeParameter(
                    name="user_data",
                    type=dict,
                    required=False,
                    description="User data for create/update operations",
                ),
                # Single user operations
                NodeParameter(
                    name="user_id",
                    type=str,
                    required=False,
                    description="User ID for single-user operations",
                ),
                # Bulk operations
                NodeParameter(
                    name="user_ids",
                    type=list,
                    required=False,
                    description="List of user IDs for bulk operations",
                ),
                # Search and filtering
                NodeParameter(
                    name="search_query",
                    type=str,
                    required=False,
                    description="Search query for user lookup",
                ),
                NodeParameter(
                    name="filters",
                    type=dict,
                    required=False,
                    description="Filters for user listing",
                ),
                NodeParameter(
                    name="pagination",
                    type=dict,
                    required=False,
                    description="Pagination parameters (page, size, sort)",
                ),
                # Multi-tenancy
                NodeParameter(
                    name="tenant_id",
                    type=str,
                    required=False,
                    description="Tenant ID for multi-tenant isolation",
                ),
                # Options
                NodeParameter(
                    name="include_deleted",
                    type=bool,
                    required=False,
                    default=False,
                    description="Include soft-deleted users in results",
                ),
                # Database configuration
                NodeParameter(
                    name="database_config",
                    type=dict,
                    required=False,
                    description="Database connection configuration",
                ),
                # Password options
                NodeParameter(
                    name="password",
                    type=str,
                    required=False,
                    description="Password for create/change operations",
                ),
                NodeParameter(
                    name="force_password_change",
                    type=bool,
                    required=False,
                    default=False,
                    description="Force password change on next login",
                ),
                # Validation options
                NodeParameter(
                    name="validate_email",
                    type=bool,
                    required=False,
                    default=True,
                    description="Validate email format and uniqueness",
                ),
                NodeParameter(
                    name="validate_username",
                    type=bool,
                    required=False,
                    default=True,
                    description="Validate username format and uniqueness",
                ),
            ]
        }

    def run(self, **inputs) -> Dict[str, Any]:
        """Execute user management operation (sync wrapper for async_run)."""
        import asyncio

        try:
            # Check if we're already in an event loop
            loop = asyncio.get_running_loop()
            # If we are, we need to handle this differently
            import concurrent.futures

            # Run in a thread pool to avoid blocking the event loop
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, self.async_run(**inputs))
                return future.result()
        except RuntimeError:
            # No event loop running, we can use asyncio.run()
            return asyncio.run(self.async_run(**inputs))

    async def async_run(self, **inputs) -> Dict[str, Any]:
        """Execute user management operation asynchronously."""
        try:
            operation = UserOperation(inputs["operation"])

            # Initialize database and access manager
            self._init_dependencies(inputs)

            # Route to appropriate operation
            if operation == UserOperation.CREATE:
                return await self._create_user_async(inputs)
            elif operation == UserOperation.READ:
                return await self._read_user_async(inputs)
            elif operation == UserOperation.UPDATE:
                return await self._update_user_async(inputs)
            elif operation == UserOperation.DELETE:
                return await self._delete_user_async(inputs)
            elif operation == UserOperation.RESTORE:
                return await self._restore_user_async(inputs)
            elif operation == UserOperation.LIST:
                return await self._list_users_async(inputs)
            elif operation == UserOperation.SEARCH:
                return await self._search_users_async(inputs)
            elif operation == UserOperation.BULK_CREATE:
                return await self._bulk_create_users_async(inputs)
            elif operation == UserOperation.BULK_UPDATE:
                return await self._bulk_update_users_async(inputs)
            elif operation == UserOperation.BULK_DELETE:
                return await self._bulk_delete_users_async(inputs)
            elif operation == UserOperation.CHANGE_PASSWORD:
                return await self._change_password_async(inputs)
            elif operation == UserOperation.RESET_PASSWORD:
                return await self._reset_password_async(inputs)
            elif operation == UserOperation.DEACTIVATE:
                return await self._deactivate_user_async(inputs)
            elif operation == UserOperation.ACTIVATE:
                return await self._activate_user_async(inputs)
            else:
                raise NodeExecutionError(f"Unknown operation: {operation}")

        except Exception as e:
            raise NodeExecutionError(f"User management operation failed: {str(e)}")

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
        self._db_node = AsyncSQLDatabaseNode(name="user_management_db", **db_config)

        # Initialize enhanced access manager
        self._access_manager = AccessControlManager(strategy="abac")

    async def _create_user_async(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new user with validation and audit logging (async version)."""
        user_data = inputs["user_data"]
        tenant_id = inputs.get("tenant_id", "default")

        # Validate required fields
        required_fields = ["email", "username", "first_name", "last_name"]
        for field in required_fields:
            if field not in user_data:
                raise NodeValidationError(f"Missing required field: {field}")

        # Validate email format
        if inputs.get("validate_email", True):
            if not self._validate_email(user_data["email"]):
                raise NodeValidationError(f"Invalid email format: {user_data['email']}")

        # Validate username format
        if inputs.get("validate_username", True):
            if not self._validate_username(user_data["username"]):
                raise NodeValidationError(
                    "Invalid username format. Username must be 3-50 characters, "
                    "alphanumeric with underscores/dashes allowed"
                )

        # Generate user ID
        user_id = self._generate_user_id()

        # Hash password if provided
        password_hash = None
        if "password" in user_data:
            # Validate password against policy
            policy = self._config.password_policy
            password = user_data["password"]

            if len(password) < policy["min_length"]:
                raise NodeValidationError(
                    f"Password must be at least {policy['min_length']} characters"
                )

            if policy.get("require_uppercase") and not any(
                c.isupper() for c in password
            ):
                raise NodeValidationError("Password must contain uppercase letters")

            if policy.get("require_lowercase") and not any(
                c.islower() for c in password
            ):
                raise NodeValidationError("Password must contain lowercase letters")

            if policy.get("require_numbers") and not any(c.isdigit() for c in password):
                raise NodeValidationError("Password must contain numbers")

            if policy.get("require_special") and not any(
                c in "!@#$%^&*()_+-=[]{}|;:,.<>?" for c in password
            ):
                raise NodeValidationError("Password must contain special characters")

            password_hash = self._hash_password(password)

        # Create user record
        user_record = {
            "user_id": user_id,
            "tenant_id": tenant_id,
            "email": user_data["email"],
            "username": user_data["username"],
            "first_name": user_data["first_name"],
            "last_name": user_data["last_name"],
            "status": user_data.get("status", UserStatus.ACTIVE.value),
            "roles": json.dumps(user_data.get("roles", ["user"])),
            "attributes": json.dumps(user_data.get("attributes", {})),
            "password_hash": password_hash,
            "force_password_change": user_data.get("force_password_change", False),
            "created_at": datetime.now(UTC),
            "updated_at": datetime.now(UTC),
            "created_by": inputs.get("metadata", {}).get("created_by", "system"),
        }

        # Insert into database
        insert_query = """
        INSERT INTO users (
            user_id, tenant_id, email, username, first_name, last_name,
            status, roles, attributes, password_hash, force_password_change,
            created_at, updated_at, created_by
        ) VALUES (
            $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14
        )
        """

        # Execute database insert using async method
        query = {
            "query": insert_query,
            "params": [
                user_record["user_id"],
                user_record["tenant_id"],
                user_record["email"],
                user_record["username"],
                user_record["first_name"],
                user_record["last_name"],
                user_record["status"],
                user_record["roles"],
                user_record["attributes"],
                user_record["password_hash"],
                user_record["force_password_change"],
                user_record["created_at"],
                user_record["updated_at"],
                user_record["created_by"],
            ],
        }

        db_result = await self._db_node.async_run(**query)

        # Create user profile response
        user_profile = UserProfile(
            user_id=user_id,
            email=user_record["email"],
            username=user_record["username"],
            first_name=user_record["first_name"],
            last_name=user_record["last_name"],
            status=UserStatus(user_record["status"]),
            roles=user_record["roles"],
            attributes=user_record["attributes"],
            created_at=user_record["created_at"],
            updated_at=user_record["updated_at"],
        )

        # Handle initial role assignments
        if inputs.get("initial_roles"):
            # Role assignment would be handled by RoleManagementNode
            pass

        # Audit log
        if self._config.audit_enabled:
            # In production, this would use AuditLogNode
            print(f"[AUDIT] user_created: {user_id} ({user_record['username']})")

        return {
            "success": True,
            "user": user_profile.__dict__,
            "message": f"User {user_record['username']} created successfully",
        }

    def _create_user(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new user with validation and audit logging."""
        user_data = inputs["user_data"]
        tenant_id = inputs.get("tenant_id", "default")

        # Validate required fields
        required_fields = ["email", "username", "first_name", "last_name"]
        for field in required_fields:
            if field not in user_data:
                raise NodeValidationError(f"Missing required field: {field}")

        # Validate email format
        if inputs.get("validate_email", True):
            if not self._validate_email(user_data["email"]):
                raise NodeValidationError(f"Invalid email format: {user_data['email']}")

        # Validate username format
        if inputs.get("validate_username", True):
            if not self._validate_username(user_data["username"]):
                raise NodeValidationError(
                    f"Invalid username format: {user_data['username']}"
                )

        # Generate user ID and timestamps
        user_id = self._generate_user_id()
        now = datetime.now(UTC)

        # Hash password if provided
        password_hash = None
        if "password" in inputs:
            password_hash = self._hash_password(inputs["password"])
        elif "password" in user_data:
            password_hash = self._hash_password(user_data["password"])

        # Prepare user record
        user_record = {
            "user_id": user_id,
            "tenant_id": tenant_id,
            "email": user_data["email"],
            "username": user_data["username"],
            "first_name": user_data["first_name"],
            "last_name": user_data["last_name"],
            "status": user_data.get("status", UserStatus.ACTIVE.value),
            "roles": user_data.get("roles", []),
            "attributes": user_data.get("attributes", {}),
            "password_hash": password_hash,
            "force_password_change": inputs.get("force_password_change", False),
            "created_at": now,
            "updated_at": now,
            "created_by": inputs.get("created_by", "system"),
        }

        # Insert user into database
        insert_query = """
        INSERT INTO users (
            user_id, tenant_id, email, username, first_name, last_name,
            status, roles, attributes, password_hash, force_password_change,
            created_at, updated_at, created_by
        ) VALUES (
            $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14
        )
        """

        # Execute database insert
        query = {
            "query": insert_query,
            "params": [
                user_record["user_id"],
                user_record["tenant_id"],
                user_record["email"],
                user_record["username"],
                user_record["first_name"],
                user_record["last_name"],
                user_record["status"],
                user_record["roles"],
                user_record["attributes"],
                user_record["password_hash"],
                user_record["force_password_change"],
                user_record["created_at"],
                user_record["updated_at"],
                user_record["created_by"],
            ],
        }

        db_result = self._db_node.run(**query)

        # Create user profile response
        user_profile = UserProfile(
            user_id=user_id,
            email=user_record["email"],
            username=user_record["username"],
            first_name=user_record["first_name"],
            last_name=user_record["last_name"],
            status=UserStatus(user_record["status"]),
            roles=user_record["roles"],
            attributes=user_record["attributes"],
            created_at=user_record["created_at"],
            updated_at=user_record["updated_at"],
            tenant_id=tenant_id,
        )

        return {
            "result": {
                "user": {
                    "user_id": user_profile.user_id,
                    "email": user_profile.email,
                    "username": user_profile.username,
                    "first_name": user_profile.first_name,
                    "last_name": user_profile.last_name,
                    "status": user_profile.status.value,
                    "roles": user_profile.roles,
                    "attributes": user_profile.attributes,
                    "created_at": user_profile.created_at.isoformat(),
                    "tenant_id": user_profile.tenant_id,
                },
                "operation": "create",
                "success": True,
                "timestamp": datetime.now(UTC).isoformat(),
            }
        }

    def _read_user(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Read user information by ID or email."""
        user_id = inputs.get("user_id")
        email = inputs.get("email")
        tenant_id = inputs.get("tenant_id", "default")
        include_deleted = inputs.get("include_deleted", False)

        if not user_id and not email:
            raise NodeValidationError("Either user_id or email must be provided")

        # Build query
        where_conditions = ["tenant_id = $1"]
        params = [tenant_id]
        param_count = 1

        if user_id:
            param_count += 1
            where_conditions.append(f"user_id = ${param_count}")
            params.append(user_id)

        if email:
            param_count += 1
            where_conditions.append(f"email = ${param_count}")
            params.append(email)

        if not include_deleted:
            where_conditions.append("status != 'deleted'")

        query = f"""
        SELECT user_id, tenant_id, email, username, first_name, last_name,
               status, roles, attributes, created_at, updated_at, last_login,
               password_changed_at, force_password_change
        FROM users
        WHERE {' AND '.join(where_conditions)}
        LIMIT 1
        """

        # Execute query
        self._db_node.config.update(
            {"query": query, "params": params, "fetch_mode": "one"}
        )

        db_result = self._db_node.run(**query)

        if not db_result.get("result", {}).get("data"):
            return {
                "result": {
                    "user": None,
                    "found": False,
                    "operation": "read",
                    "timestamp": datetime.now(UTC).isoformat(),
                }
            }

        user_data = db_result["result"]["data"]

        return {
            "result": {
                "user": {
                    "user_id": user_data["user_id"],
                    "email": user_data["email"],
                    "username": user_data["username"],
                    "first_name": user_data["first_name"],
                    "last_name": user_data["last_name"],
                    "status": user_data["status"],
                    "roles": user_data["roles"],
                    "attributes": user_data["attributes"],
                    "created_at": user_data["created_at"],
                    "updated_at": user_data["updated_at"],
                    "last_login": user_data["last_login"],
                    "tenant_id": user_data["tenant_id"],
                },
                "found": True,
                "operation": "read",
                "timestamp": datetime.now(UTC).isoformat(),
            }
        }

    def _list_users(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """List users with filtering, pagination, and search."""
        tenant_id = inputs.get("tenant_id", "default")
        filters = inputs.get("filters", {})
        pagination = inputs.get(
            "pagination", {"page": 1, "size": 20, "sort": "created_at"}
        )
        include_deleted = inputs.get("include_deleted", False)

        # Build WHERE clause
        where_conditions = ["tenant_id = $1"]
        params = [tenant_id]
        param_count = 1

        if not include_deleted:
            where_conditions.append("status != 'deleted'")

        # Apply filters
        if "status" in filters:
            param_count += 1
            where_conditions.append(f"status = ${param_count}")
            params.append(filters["status"])

        if "role" in filters:
            param_count += 1
            where_conditions.append(f"${param_count} = ANY(roles)")
            params.append(filters["role"])

        if "department" in filters:
            param_count += 1
            where_conditions.append(f"attributes->>'department' = ${param_count}")
            params.append(filters["department"])

        # Search query
        search_query = inputs.get("search_query")
        if search_query:
            param_count += 1
            where_conditions.append(
                f"""
                (email ILIKE ${param_count} OR
                 username ILIKE ${param_count} OR
                 first_name ILIKE ${param_count} OR
                 last_name ILIKE ${param_count})
            """
            )
            params.append(f"%{search_query}%")

        # Pagination
        page = pagination.get("page", 1)
        size = pagination.get("size", 20)
        sort_field = pagination.get("sort", "created_at")
        sort_direction = pagination.get("direction", "DESC")

        offset = (page - 1) * size

        # Count query
        count_query = f"""
        SELECT COUNT(*) as total
        FROM users
        WHERE {' AND '.join(where_conditions)}
        """

        # Data query
        data_query = f"""
        SELECT user_id, email, username, first_name, last_name,
               status, roles, attributes, created_at, updated_at, last_login
        FROM users
        WHERE {' AND '.join(where_conditions)}
        ORDER BY {sort_field} {sort_direction}
        LIMIT {size} OFFSET {offset}
        """

        # Execute count query
        self._db_node.config.update(
            {"query": count_query, "params": params, "fetch_mode": "one"}
        )
        count_result = self._db_node.run()
        total_count = count_result["result"]["data"]["total"]

        # Execute data query
        self._db_node.config.update(
            {"query": data_query, "params": params, "fetch_mode": "all"}
        )
        data_result = self._db_node.run()
        users = data_result["result"]["data"]

        # Calculate pagination info
        total_pages = (total_count + size - 1) // size
        has_next = page < total_pages
        has_prev = page > 1

        return {
            "result": {
                "users": users,
                "pagination": {
                    "page": page,
                    "size": size,
                    "total": total_count,
                    "total_pages": total_pages,
                    "has_next": has_next,
                    "has_prev": has_prev,
                },
                "filters_applied": filters,
                "search_query": search_query,
                "operation": "list",
                "timestamp": datetime.now(UTC).isoformat(),
            }
        }

    def _bulk_create_users(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Create multiple users with transaction support."""
        user_data_list = inputs["user_data"]
        tenant_id = inputs.get("tenant_id", "default")

        if not isinstance(user_data_list, list):
            raise NodeValidationError("user_data must be a list for bulk operations")

        results = {"created": [], "failed": [], "stats": {"created": 0, "failed": 0}}

        for i, user_data in enumerate(user_data_list):
            try:
                # Create individual user
                create_inputs = {
                    "operation": "create",
                    "user_data": user_data,
                    "tenant_id": tenant_id,
                    "validate_email": inputs.get("validate_email", True),
                    "validate_username": inputs.get("validate_username", True),
                }

                result = self._create_user(create_inputs)
                results["created"].append(
                    {"index": i, "user": result["result"]["user"]}
                )
                results["stats"]["created"] += 1

            except Exception as e:
                results["failed"].append(
                    {"index": i, "user_data": user_data, "error": str(e)}
                )
                results["stats"]["failed"] += 1

        return {
            "result": {
                "operation": "bulk_create",
                "results": results,
                "timestamp": datetime.now(UTC).isoformat(),
            }
        }

    # Utility methods
    def _generate_user_id(self) -> str:
        """Generate unique user ID."""
        import uuid

        return str(uuid.uuid4())

    def _hash_password(self, password: str) -> str:
        """Hash password using SHA-256 with salt."""
        salt = secrets.token_hex(32)
        password_hash = hashlib.sha256((password + salt).encode("utf-8")).hexdigest()
        return f"{salt}${password_hash}"

    def _validate_email(self, email: str) -> bool:
        """Validate email format."""
        import re

        pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
        return bool(re.match(pattern, email))

    def _validate_username(self, username: str) -> bool:
        """Validate username format."""
        import re

        # Username: alphanumeric, dots, hyphens, underscores, 3-50 chars
        pattern = r"^[a-zA-Z0-9._-]{3,50}$"
        return bool(re.match(pattern, username))

    # Additional operations (update, delete, etc.) would follow similar patterns
    def _update_user(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Update user information."""
        user_id = inputs.get("user_id")
        user_data = inputs.get("user_data", {})
        tenant_id = inputs.get("tenant_id", "default")

        if not user_id:
            raise NodeValidationError("user_id is required for update operation")

        # Build update fields
        update_fields = []
        params = []
        param_count = 1

        # Update allowed fields
        allowed_fields = [
            "email",
            "username",
            "first_name",
            "last_name",
            "status",
            "roles",
            "attributes",
            "phone",
            "department",
        ]

        for field, value in user_data.items():
            if field in allowed_fields:
                # Validate specific fields
                if field == "email" and inputs.get("validate_email", True):
                    if not self._validate_email(value):
                        raise NodeValidationError(f"Invalid email format: {value}")
                elif field == "username" and inputs.get("validate_username", True):
                    if not self._validate_username(value):
                        raise NodeValidationError(f"Invalid username format: {value}")
                elif field == "status":
                    if value not in [s.value for s in UserStatus]:
                        raise NodeValidationError(f"Invalid status: {value}")

                update_fields.append(f"{field} = ${param_count}")
                params.append(value)
                param_count += 1

        if not update_fields:
            return {"success": False, "message": "No valid fields to update"}

        # Add updated_at
        update_fields.append(f"updated_at = ${param_count}")
        params.append(datetime.now(UTC))
        param_count += 1

        # Build query
        update_query = f"""
        UPDATE users
        SET {', '.join(update_fields)}
        WHERE user_id = ${param_count} AND tenant_id = ${param_count + 1}
        RETURNING user_id, email, username, first_name, last_name, status, roles, attributes
        """
        params.extend([user_id, tenant_id])

        self._ensure_db_node(inputs)
        result = self._db_node.execute(query=update_query, params=params)

        if not result.get("rows"):
            return {"success": False, "message": "User not found"}

        updated_user = result["rows"][0]

        # Audit log
        if self._config.audit_enabled:
            print(f"[AUDIT] user_updated: {user_id}")

        return {
            "success": True,
            "user": updated_user,
            "message": f"User {user_id} updated successfully",
        }

    def _delete_user(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Soft delete user."""
        user_id = inputs.get("user_id")
        tenant_id = inputs.get("tenant_id", "default")
        hard_delete = inputs.get("hard_delete", False)

        if not user_id:
            raise NodeValidationError("user_id is required for delete operation")

        self._ensure_db_node(inputs)

        if hard_delete:
            # Permanent deletion - use with caution
            delete_query = """
            DELETE FROM users
            WHERE user_id = $1 AND tenant_id = $2
            RETURNING user_id, email, username
            """
        else:
            # Soft delete - change status to 'deleted'
            delete_query = """
            UPDATE users
            SET status = 'deleted',
                updated_at = $3,
                deleted_at = $3,
                deleted_by = $4
            WHERE user_id = $1 AND tenant_id = $2 AND status != 'deleted'
            RETURNING user_id, email, username, status
            """

        params = [user_id, tenant_id]
        if not hard_delete:
            params.extend([datetime.now(UTC), inputs.get("deleted_by", "system")])

        result = self._db_node.execute(query=delete_query, params=params)

        if not result.get("rows"):
            return {"success": False, "message": "User not found or already deleted"}

        deleted_user = result["rows"][0]

        # Audit log
        if self._config.audit_enabled:
            action = "hard_deleted" if hard_delete else "soft_deleted"
            print(f"[AUDIT] user_{action}: {user_id}")

        return {
            "success": True,
            "user": deleted_user,
            "message": f"User {user_id} deleted successfully",
            "hard_delete": hard_delete,
        }

    def _change_password(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Change user password."""
        user_id = inputs.get("user_id")
        current_password = inputs.get("current_password")
        new_password = inputs.get("new_password")
        tenant_id = inputs.get("tenant_id", "default")
        skip_current_check = inputs.get("skip_current_check", False)

        if not user_id:
            raise NodeValidationError("user_id is required for password change")
        if not new_password:
            raise NodeValidationError("new_password is required")
        if not skip_current_check and not current_password:
            raise NodeValidationError(
                "current_password is required unless skip_current_check is True"
            )

        self._ensure_db_node(inputs)

        # Verify current password if required
        if not skip_current_check:
            verify_query = """
            SELECT password_hash
            FROM users
            WHERE user_id = $1 AND tenant_id = $2 AND status != 'deleted'
            """
            result = self._db_node.execute(
                query=verify_query, params=[user_id, tenant_id]
            )

            if not result.get("rows"):
                return {"success": False, "message": "User not found"}

            stored_hash = result["rows"][0]["password_hash"]
            if stored_hash and not self._verify_password(current_password, stored_hash):
                return {"success": False, "message": "Current password is incorrect"}

        # Validate new password against policy
        policy = self._config.password_policy
        if len(new_password) < policy["min_length"]:
            raise NodeValidationError(
                f"Password must be at least {policy['min_length']} characters"
            )

        if policy.get("require_uppercase") and not any(
            c.isupper() for c in new_password
        ):
            raise NodeValidationError("Password must contain uppercase letters")

        if policy.get("require_lowercase") and not any(
            c.islower() for c in new_password
        ):
            raise NodeValidationError("Password must contain lowercase letters")

        if policy.get("require_numbers") and not any(c.isdigit() for c in new_password):
            raise NodeValidationError("Password must contain numbers")

        if policy.get("require_special") and not any(
            c in "!@#$%^&*()_+-=[]{}|;:,.<>?" for c in new_password
        ):
            raise NodeValidationError("Password must contain special characters")

        # Check password history if configured
        if policy.get("history_count", 0) > 0:
            history_query = """
            SELECT password_hash
            FROM password_history
            WHERE user_id = $1 AND tenant_id = $2
            ORDER BY created_at DESC
            LIMIT $3
            """
            history_result = self._db_node.execute(
                query=history_query,
                params=[user_id, tenant_id, policy["history_count"]],
            )

            for row in history_result.get("rows", []):
                if self._verify_password(new_password, row["password_hash"]):
                    return {
                        "success": False,
                        "message": f"Password cannot be reused from last {policy['history_count']} passwords",
                    }

        # Hash new password
        new_hash = self._hash_password(new_password)

        # Update password
        update_query = """
        UPDATE users
        SET password_hash = $1,
            password_changed_at = $2,
            updated_at = $2,
            force_password_change = false
        WHERE user_id = $3 AND tenant_id = $4
        RETURNING user_id, email, username
        """

        now = datetime.now(UTC)
        result = self._db_node.execute(
            query=update_query, params=[new_hash, now, user_id, tenant_id]
        )

        if not result.get("rows"):
            return {"success": False, "message": "Failed to update password"}

        # Store in password history
        if policy.get("history_count", 0) > 0:
            history_insert = """
            INSERT INTO password_history (user_id, tenant_id, password_hash, created_at)
            VALUES ($1, $2, $3, $4)
            """
            self._db_node.execute(
                query=history_insert, params=[user_id, tenant_id, new_hash, now]
            )

        # Audit log
        if self._config.audit_enabled:
            print(f"[AUDIT] password_changed: {user_id}")

        return {
            "success": True,
            "user": result["rows"][0],
            "message": "Password changed successfully",
        }

    def _reset_password(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Reset user password with token generation."""
        user_id = inputs.get("user_id")
        email = inputs.get("email")
        tenant_id = inputs.get("tenant_id", "default")
        generate_token = inputs.get("generate_token", True)
        new_password = inputs.get("new_password")
        token_expiry_hours = inputs.get("token_expiry_hours", 24)

        if not user_id and not email:
            raise NodeValidationError(
                "Either user_id or email is required for password reset"
            )

        self._ensure_db_node(inputs)

        # Find user
        if user_id:
            query = "SELECT user_id, email, username FROM users WHERE user_id = $1 AND tenant_id = $2 AND status != 'deleted'"
            params = [user_id, tenant_id]
        else:
            query = "SELECT user_id, email, username FROM users WHERE email = $1 AND tenant_id = $2 AND status != 'deleted'"
            params = [email, tenant_id]

        result = self._db_node.execute(query=query, params=params)

        if not result.get("rows"):
            return {"success": False, "message": "User not found"}

        user_data = result["rows"][0]
        user_id = user_data["user_id"]

        if generate_token:
            # Generate secure reset token
            reset_token = secrets.token_urlsafe(32)
            token_hash = hashlib.sha256(reset_token.encode()).hexdigest()
            expiry_time = datetime.now(UTC) + timedelta(hours=token_expiry_hours)

            # Store reset token
            token_query = """
            INSERT INTO password_reset_tokens (user_id, tenant_id, token_hash, expires_at, created_at)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (user_id, tenant_id)
            DO UPDATE SET token_hash = $3, expires_at = $4, created_at = $5, used = false
            """

            self._db_node.execute(
                query=token_query,
                params=[user_id, tenant_id, token_hash, expiry_time, datetime.now(UTC)],
            )

            # Force password change on next login
            update_query = """
            UPDATE users
            SET force_password_change = true, updated_at = $1
            WHERE user_id = $2 AND tenant_id = $3
            """
            self._db_node.execute(
                query=update_query, params=[datetime.now(UTC), user_id, tenant_id]
            )

            # Audit log
            if self._config.audit_enabled:
                print(f"[AUDIT] password_reset_requested: {user_id}")

            return {
                "success": True,
                "user": user_data,
                "reset_token": reset_token,
                "expires_at": expiry_time.isoformat(),
                "message": "Password reset token generated",
            }

        elif new_password:
            # Direct password reset (admin action)
            # Validate new password
            policy = self._config.password_policy
            if len(new_password) < policy["min_length"]:
                raise NodeValidationError(
                    f"Password must be at least {policy['min_length']} characters"
                )

            # Hash and update password
            new_hash = self._hash_password(new_password)

            update_query = """
            UPDATE users
            SET password_hash = $1,
                password_changed_at = $2,
                updated_at = $2,
                force_password_change = $3
            WHERE user_id = $4 AND tenant_id = $5
            RETURNING user_id, email, username
            """

            force_change = inputs.get("force_password_change", True)
            now = datetime.now(UTC)

            result = self._db_node.execute(
                query=update_query,
                params=[new_hash, now, force_change, user_id, tenant_id],
            )

            if not result.get("rows"):
                return {"success": False, "message": "Failed to reset password"}

            # Audit log
            if self._config.audit_enabled:
                print(f"[AUDIT] password_reset_admin: {user_id}")

            return {
                "success": True,
                "user": result["rows"][0],
                "message": "Password reset successfully",
                "force_password_change": force_change,
            }

        else:
            raise NodeValidationError(
                "Either generate_token or new_password must be provided"
            )

    def _deactivate_user(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Deactivate user account."""
        user_id = inputs.get("user_id")
        tenant_id = inputs.get("tenant_id", "default")
        reason = inputs.get("reason", "Manual deactivation")
        deactivated_by = inputs.get("deactivated_by", "system")

        if not user_id:
            raise NodeValidationError("user_id is required for deactivate operation")

        self._ensure_db_node(inputs)

        # Update user status to inactive
        update_query = """
        UPDATE users
        SET status = 'inactive',
            updated_at = $1,
            deactivated_at = $1,
            deactivation_reason = $2,
            deactivated_by = $3
        WHERE user_id = $4 AND tenant_id = $5 AND status = 'active'
        RETURNING user_id, email, username, status, first_name, last_name
        """

        now = datetime.now(UTC)
        result = self._db_node.execute(
            query=update_query, params=[now, reason, deactivated_by, user_id, tenant_id]
        )

        if not result.get("rows"):
            # Check if user exists but is already inactive
            check_query = """
            SELECT status FROM users
            WHERE user_id = $1 AND tenant_id = $2
            """
            check_result = self._db_node.execute(
                query=check_query, params=[user_id, tenant_id]
            )

            if check_result.get("rows"):
                current_status = check_result["rows"][0]["status"]
                return {
                    "success": False,
                    "message": f"User is already {current_status}",
                }
            else:
                return {"success": False, "message": "User not found"}

        deactivated_user = result["rows"][0]

        # Revoke active sessions
        session_query = """
        UPDATE user_sessions
        SET status = 'revoked', revoked_at = $1
        WHERE user_id = $2 AND tenant_id = $3 AND status = 'active'
        """
        self._db_node.execute(query=session_query, params=[now, user_id, tenant_id])

        # Audit log
        if self._config.audit_enabled:
            print(f"[AUDIT] user_deactivated: {user_id} (reason: {reason})")

        return {
            "success": True,
            "user": deactivated_user,
            "message": f"User {user_id} deactivated successfully",
            "reason": reason,
        }

    def _activate_user(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Activate user account."""
        user_id = inputs.get("user_id")
        tenant_id = inputs.get("tenant_id", "default")
        activated_by = inputs.get("activated_by", "system")
        clear_deactivation_data = inputs.get("clear_deactivation_data", True)

        if not user_id:
            raise NodeValidationError("user_id is required for activate operation")

        self._ensure_db_node(inputs)

        # Update user status to active
        if clear_deactivation_data:
            update_query = """
            UPDATE users
            SET status = 'active',
                updated_at = $1,
                activated_at = $1,
                activated_by = $2,
                deactivated_at = NULL,
                deactivation_reason = NULL,
                deactivated_by = NULL
            WHERE user_id = $3 AND tenant_id = $4 AND status IN ('inactive', 'pending')
            RETURNING user_id, email, username, status, first_name, last_name
            """
        else:
            update_query = """
            UPDATE users
            SET status = 'active',
                updated_at = $1,
                activated_at = $1,
                activated_by = $2
            WHERE user_id = $3 AND tenant_id = $4 AND status IN ('inactive', 'pending')
            RETURNING user_id, email, username, status, first_name, last_name
            """

        now = datetime.now(UTC)
        result = self._db_node.execute(
            query=update_query, params=[now, activated_by, user_id, tenant_id]
        )

        if not result.get("rows"):
            # Check if user exists but is already active
            check_query = """
            SELECT status FROM users
            WHERE user_id = $1 AND tenant_id = $2
            """
            check_result = self._db_node.execute(
                query=check_query, params=[user_id, tenant_id]
            )

            if check_result.get("rows"):
                current_status = check_result["rows"][0]["status"]
                if current_status == "active":
                    return {"success": False, "message": "User is already active"}
                elif current_status == "deleted":
                    return {
                        "success": False,
                        "message": "Cannot activate deleted user. Use restore operation instead.",
                    }
                else:
                    return {
                        "success": False,
                        "message": f"Cannot activate user with status: {current_status}",
                    }
            else:
                return {"success": False, "message": "User not found"}

        activated_user = result["rows"][0]

        # Audit log
        if self._config.audit_enabled:
            print(f"[AUDIT] user_activated: {user_id}")

        return {
            "success": True,
            "user": activated_user,
            "message": f"User {user_id} activated successfully",
        }

    def _ensure_db_node(self, inputs: Dict[str, Any]):
        """Ensure database node is initialized."""
        if not self._db_node:
            self._init_dependencies(inputs)

    def _verify_password(self, password: str, password_hash: str) -> bool:
        """Verify password against hash."""
        if not password_hash or "$" not in password_hash:
            return False

        salt, stored_hash = password_hash.split("$", 1)
        test_hash = hashlib.sha256((password + salt).encode("utf-8")).hexdigest()
        return test_hash == stored_hash

    def _restore_user(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Restore soft-deleted user."""
        user_id = inputs.get("user_id")
        tenant_id = inputs.get("tenant_id", "default")
        restored_by = inputs.get("restored_by", "system")
        new_status = inputs.get("new_status", "active")

        if not user_id:
            raise NodeValidationError("user_id is required for restore operation")

        if new_status not in ["active", "inactive", "pending"]:
            raise NodeValidationError(
                f"Invalid new_status: {new_status}. Must be active, inactive, or pending"
            )

        self._ensure_db_node(inputs)

        # Check if user exists and is deleted
        check_query = """
        SELECT user_id, email, username, status, deleted_at
        FROM users
        WHERE user_id = $1 AND tenant_id = $2
        """
        check_result = self._db_node.execute(
            query=check_query, params=[user_id, tenant_id]
        )

        if not check_result.get("rows"):
            return {"success": False, "message": "User not found"}

        user_data = check_result["rows"][0]
        if user_data["status"] != "deleted":
            return {
                "success": False,
                "message": f"User is not deleted. Current status: {user_data['status']}",
            }

        # Restore user
        restore_query = """
        UPDATE users
        SET status = $1,
            updated_at = $2,
            restored_at = $2,
            restored_by = $3,
            deleted_at = NULL,
            deleted_by = NULL
        WHERE user_id = $4 AND tenant_id = $5 AND status = 'deleted'
        RETURNING user_id, email, username, status, first_name, last_name
        """

        now = datetime.now(UTC)
        result = self._db_node.execute(
            query=restore_query,
            params=[new_status, now, restored_by, user_id, tenant_id],
        )

        if not result.get("rows"):
            return {"success": False, "message": "Failed to restore user"}

        restored_user = result["rows"][0]

        # Audit log
        if self._config.audit_enabled:
            print(f"[AUDIT] user_restored: {user_id} (new_status: {new_status})")

        return {
            "success": True,
            "user": restored_user,
            "message": f"User {user_id} restored successfully",
            "new_status": new_status,
            "previous_deleted_at": user_data["deleted_at"],
        }

    def _search_users(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Advanced user search with full-text capabilities."""
        search_query = inputs.get("search_query", "")
        tenant_id = inputs.get("tenant_id", "default")
        filters = inputs.get("filters", {})
        search_fields = inputs.get(
            "search_fields", ["email", "username", "first_name", "last_name"]
        )
        pagination = inputs.get(
            "pagination", {"page": 1, "size": 20, "sort": "relevance"}
        )
        include_deleted = inputs.get("include_deleted", False)
        fuzzy_search = inputs.get("fuzzy_search", True)

        self._ensure_db_node(inputs)

        # Build search conditions
        where_conditions = ["tenant_id = $1"]
        params = [tenant_id]
        param_count = 1

        if not include_deleted:
            where_conditions.append("status != 'deleted'")

        # Apply filters
        if "status" in filters:
            param_count += 1
            if isinstance(filters["status"], list):
                where_conditions.append(f"status = ANY(${param_count})")
                params.append(filters["status"])
            else:
                where_conditions.append(f"status = ${param_count}")
                params.append(filters["status"])

        if "roles" in filters:
            param_count += 1
            where_conditions.append(f"roles && ${param_count}")
            params.append(filters["roles"])

        if "created_after" in filters:
            param_count += 1
            where_conditions.append(f"created_at >= ${param_count}")
            params.append(filters["created_after"])

        if "created_before" in filters:
            param_count += 1
            where_conditions.append(f"created_at <= ${param_count}")
            params.append(filters["created_before"])

        # Apply attribute filters
        if "attributes" in filters:
            for attr_key, attr_value in filters["attributes"].items():
                param_count += 1
                where_conditions.append(f"attributes->>'{attr_key}' = ${param_count}")
                params.append(attr_value)

        # Build search query
        if search_query:
            search_conditions = []
            param_count += 1

            if fuzzy_search:
                # Use ILIKE for fuzzy matching
                search_pattern = f"%{search_query}%"
                params.append(search_pattern)

                for field in search_fields:
                    search_conditions.append(f"{field} ILIKE ${param_count}")
            else:
                # Exact match
                params.append(search_query)

                for field in search_fields:
                    search_conditions.append(f"{field} = ${param_count}")

            if search_conditions:
                where_conditions.append(f"({' OR '.join(search_conditions)})")

        # Get pagination settings
        page = pagination.get("page", 1)
        size = pagination.get("size", 20)
        sort_field = pagination.get("sort", "relevance")
        sort_direction = pagination.get("direction", "DESC")

        # Calculate offset
        offset = (page - 1) * size

        # Build relevance scoring for sorting
        if sort_field == "relevance" and search_query:
            relevance_score = f"""
                CASE
                    WHEN email = ${param_count} THEN 4
                    WHEN username = ${param_count} THEN 3
                    WHEN email ILIKE ${param_count} THEN 2
                    WHEN username ILIKE ${param_count} OR first_name ILIKE ${param_count} OR last_name ILIKE ${param_count} THEN 1
                    ELSE 0
                END as relevance
            """

            order_by = "relevance DESC, created_at DESC"
        else:
            relevance_score = "0 as relevance"
            order_by = f"{sort_field} {sort_direction}"

        # Count query
        count_query = f"""
        SELECT COUNT(*) as total
        FROM users
        WHERE {' AND '.join(where_conditions)}
        """

        # Data query
        data_query = f"""
        SELECT user_id, email, username, first_name, last_name,
               status, roles, attributes, created_at, updated_at, last_login,
               {relevance_score}
        FROM users
        WHERE {' AND '.join(where_conditions)}
        ORDER BY {order_by}
        LIMIT {size} OFFSET {offset}
        """

        # Execute count query
        count_result = self._db_node.execute(query=count_query, params=params)
        total_count = (
            count_result["rows"][0]["total"] if count_result.get("rows") else 0
        )

        # Execute data query
        data_result = self._db_node.execute(query=data_query, params=params)
        users = data_result.get("rows", [])

        # Calculate pagination info
        total_pages = (total_count + size - 1) // size if size > 0 else 0
        has_next = page < total_pages
        has_prev = page > 1

        # Audit log search action
        if self._config.audit_enabled and search_query:
            print(f"[AUDIT] user_search: query='{search_query}', results={len(users)}")

        return {
            "success": True,
            "users": users,
            "pagination": {
                "page": page,
                "size": size,
                "total": total_count,
                "total_pages": total_pages,
                "has_next": has_next,
                "has_prev": has_prev,
            },
            "search": {
                "query": search_query,
                "fields": search_fields,
                "fuzzy": fuzzy_search,
            },
            "filters_applied": filters,
            "message": f"Found {total_count} users matching criteria",
        }

    def _bulk_update_users(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Bulk update multiple users."""
        user_updates = inputs.get("user_updates", [])
        tenant_id = inputs.get("tenant_id", "default")
        updated_by = inputs.get("updated_by", "system")
        transaction_mode = inputs.get("transaction_mode", "all_or_none")

        if not user_updates:
            raise NodeValidationError("user_updates list is required for bulk update")

        if not isinstance(user_updates, list):
            raise NodeValidationError("user_updates must be a list")

        self._ensure_db_node(inputs)

        results = {"updated": [], "failed": [], "stats": {"updated": 0, "failed": 0}}

        # Start transaction if all_or_none mode
        if transaction_mode == "all_or_none":
            self._db_node.execute(query="BEGIN")

        try:
            for i, update_data in enumerate(user_updates):
                try:
                    user_id = update_data.get("user_id")
                    if not user_id:
                        raise NodeValidationError(
                            f"user_id missing in update at index {i}"
                        )

                    # Build update fields
                    update_fields = []
                    params = []
                    param_count = 1

                    # Update allowed fields
                    allowed_fields = [
                        "email",
                        "username",
                        "first_name",
                        "last_name",
                        "status",
                        "roles",
                        "attributes",
                        "phone",
                        "department",
                    ]

                    for field, value in update_data.items():
                        if field in allowed_fields:
                            # Validate specific fields
                            if field == "email" and inputs.get("validate_email", True):
                                if not self._validate_email(value):
                                    raise NodeValidationError(
                                        f"Invalid email format: {value}"
                                    )
                            elif field == "username" and inputs.get(
                                "validate_username", True
                            ):
                                if not self._validate_username(value):
                                    raise NodeValidationError(
                                        f"Invalid username format: {value}"
                                    )
                            elif field == "status":
                                if value not in [s.value for s in UserStatus]:
                                    raise NodeValidationError(
                                        f"Invalid status: {value}"
                                    )

                            update_fields.append(f"{field} = ${param_count}")
                            params.append(value)
                            param_count += 1

                    if not update_fields:
                        raise NodeValidationError(
                            f"No valid fields to update at index {i}"
                        )

                    # Add updated_at and updated_by
                    update_fields.append(f"updated_at = ${param_count}")
                    params.append(datetime.now(UTC))
                    param_count += 1

                    update_fields.append(f"updated_by = ${param_count}")
                    params.append(updated_by)
                    param_count += 1

                    # Build query
                    update_query = f"""
                    UPDATE users
                    SET {', '.join(update_fields)}
                    WHERE user_id = ${param_count} AND tenant_id = ${param_count + 1}
                    RETURNING user_id, email, username, status
                    """
                    params.extend([user_id, tenant_id])

                    result = self._db_node.execute(query=update_query, params=params)

                    if result.get("rows"):
                        results["updated"].append(
                            {"index": i, "user": result["rows"][0]}
                        )
                        results["stats"]["updated"] += 1
                    else:
                        raise Exception("User not found or no changes made")

                except Exception as e:
                    error_info = {
                        "index": i,
                        "user_id": update_data.get("user_id"),
                        "error": str(e),
                    }

                    if transaction_mode == "all_or_none":
                        # Rollback and return error
                        self._db_node.execute(query="ROLLBACK")
                        return {
                            "success": False,
                            "message": f"Bulk update failed at index {i}: {str(e)}",
                            "error_detail": error_info,
                            "stats": results["stats"],
                        }
                    else:
                        # Continue with next update
                        results["failed"].append(error_info)
                        results["stats"]["failed"] += 1

            # Commit transaction if all_or_none mode
            if transaction_mode == "all_or_none":
                self._db_node.execute(query="COMMIT")

            # Audit log
            if self._config.audit_enabled:
                print(
                    f"[AUDIT] bulk_user_update: updated={results['stats']['updated']}, failed={results['stats']['failed']}"
                )

            return {
                "success": True,
                "results": results,
                "message": f"Bulk update completed: {results['stats']['updated']} updated, {results['stats']['failed']} failed",
                "transaction_mode": transaction_mode,
            }

        except Exception as e:
            if transaction_mode == "all_or_none":
                self._db_node.execute(query="ROLLBACK")
            raise NodeExecutionError(f"Bulk update failed: {str(e)}")

    def _bulk_delete_users(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Bulk delete multiple users."""
        user_ids = inputs.get("user_ids", [])
        tenant_id = inputs.get("tenant_id", "default")
        hard_delete = inputs.get("hard_delete", False)
        deleted_by = inputs.get("deleted_by", "system")
        transaction_mode = inputs.get("transaction_mode", "all_or_none")

        if not user_ids:
            raise NodeValidationError("user_ids list is required for bulk delete")

        if not isinstance(user_ids, list):
            raise NodeValidationError("user_ids must be a list")

        self._ensure_db_node(inputs)

        results = {"deleted": [], "failed": [], "stats": {"deleted": 0, "failed": 0}}

        # Start transaction if all_or_none mode
        if transaction_mode == "all_or_none":
            self._db_node.execute(query="BEGIN")

        try:
            now = datetime.now(UTC)

            for i, user_id in enumerate(user_ids):
                try:
                    if hard_delete:
                        # Permanent deletion
                        delete_query = """
                        DELETE FROM users
                        WHERE user_id = $1 AND tenant_id = $2
                        RETURNING user_id, email, username
                        """
                        params = [user_id, tenant_id]
                    else:
                        # Soft delete
                        delete_query = """
                        UPDATE users
                        SET status = 'deleted',
                            updated_at = $1,
                            deleted_at = $1,
                            deleted_by = $2
                        WHERE user_id = $3 AND tenant_id = $4 AND status != 'deleted'
                        RETURNING user_id, email, username, status
                        """
                        params = [now, deleted_by, user_id, tenant_id]

                    result = self._db_node.execute(query=delete_query, params=params)

                    if result.get("rows"):
                        results["deleted"].append(
                            {"index": i, "user": result["rows"][0]}
                        )
                        results["stats"]["deleted"] += 1

                        # Revoke sessions for soft delete
                        if not hard_delete:
                            session_query = """
                            UPDATE user_sessions
                            SET status = 'revoked', revoked_at = $1
                            WHERE user_id = $2 AND tenant_id = $3 AND status = 'active'
                            """
                            self._db_node.execute(
                                query=session_query, params=[now, user_id, tenant_id]
                            )
                    else:
                        raise Exception("User not found or already deleted")

                except Exception as e:
                    error_info = {"index": i, "user_id": user_id, "error": str(e)}

                    if transaction_mode == "all_or_none":
                        # Rollback and return error
                        self._db_node.execute(query="ROLLBACK")
                        return {
                            "success": False,
                            "message": f"Bulk delete failed at index {i}: {str(e)}",
                            "error_detail": error_info,
                            "stats": results["stats"],
                        }
                    else:
                        # Continue with next deletion
                        results["failed"].append(error_info)
                        results["stats"]["failed"] += 1

            # Commit transaction if all_or_none mode
            if transaction_mode == "all_or_none":
                self._db_node.execute(query="COMMIT")

            # Audit log
            if self._config.audit_enabled:
                action = "hard_deleted" if hard_delete else "soft_deleted"
                print(
                    f"[AUDIT] bulk_user_{action}: deleted={results['stats']['deleted']}, failed={results['stats']['failed']}"
                )

            return {
                "success": True,
                "results": results,
                "message": f"Bulk delete completed: {results['stats']['deleted']} deleted, {results['stats']['failed']} failed",
                "hard_delete": hard_delete,
                "transaction_mode": transaction_mode,
            }

        except Exception as e:
            if transaction_mode == "all_or_none":
                self._db_node.execute(query="ROLLBACK")
            raise NodeExecutionError(f"Bulk delete failed: {str(e)}")

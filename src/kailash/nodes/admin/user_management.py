"""Enterprise user management node with complete user lifecycle support.

This node provides comprehensive user management capabilities for the unified admin system,
including user creation, update, deletion, and lifecycle management. Integrates seamlessly
with RoleManagementNode and PermissionCheckNode for complete RBAC/ABAC functionality.

Features:
- Complete user lifecycle management (CRUD operations)
- JSONB-based role and attribute management
- Multi-tenant user isolation
- User authentication and session management
- Bulk user operations for enterprise scenarios
- User profile and metadata management
- Integration with external identity providers
- Comprehensive audit logging
- User status and lifecycle tracking
"""

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Union
from uuid import uuid4

import bcrypt

from kailash.nodes.base import Node, NodeParameter, register_node
from kailash.nodes.data import SQLDatabaseNode
from kailash.sdk_exceptions import NodeExecutionError, NodeValidationError

from .schema_manager import AdminSchemaManager


def hash_password(password: str) -> str:
    """Hash password using bcrypt with salt."""
    if not password:
        return ""
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
    return hashed.decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    """Verify password against bcrypt hash."""
    if not password or not hashed:
        return False
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


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


class UserOperation(Enum):
    """Supported user management operations."""

    CREATE_USER = "create_user"
    UPDATE_USER = "update_user"
    DELETE_USER = "delete_user"
    GET_USER = "get_user"
    LIST_USERS = "list_users"
    ACTIVATE_USER = "activate_user"
    DEACTIVATE_USER = "deactivate_user"
    SET_PASSWORD = "set_password"
    UPDATE_PROFILE = "update_profile"
    BULK_CREATE = "bulk_create"
    BULK_UPDATE = "bulk_update"
    BULK_DELETE = "bulk_delete"
    GET_USER_ROLES = "get_user_roles"
    GET_USER_PERMISSIONS = "get_user_permissions"
    SEARCH_USERS = "search_users"
    EXPORT_USERS = "export_users"
    GENERATE_RESET_TOKEN = "generate_reset_token"
    RESET_PASSWORD = "reset_password"
    AUTHENTICATE = "authenticate"


class UserStatus(Enum):
    """User status values."""

    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"
    PENDING = "pending"
    DELETED = "deleted"


@dataclass
class User:
    """Complete user definition with all attributes."""

    user_id: str
    email: str
    username: Optional[str]
    first_name: Optional[str]
    last_name: Optional[str]
    display_name: Optional[str]
    roles: List[str]
    attributes: Dict[str, Any]
    status: UserStatus
    tenant_id: str
    external_auth_id: Optional[str] = None
    auth_provider: str = "local"
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    last_login_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""

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

        return {
            "user_id": self.user_id,
            "email": self.email,
            "username": self.username,
            "first_name": self.first_name,
            "last_name": self.last_name,
            "display_name": self.display_name,
            "roles": self.roles,
            "attributes": self.attributes,
            "status": self.status.value,
            "tenant_id": self.tenant_id,
            "external_auth_id": self.external_auth_id,
            "auth_provider": self.auth_provider,
            "created_at": format_datetime(self.created_at),
            "updated_at": format_datetime(self.updated_at),
            "last_login_at": format_datetime(self.last_login_at),
        }


@register_node()
class UserManagementNode(Node):
    """Enterprise user management node with complete lifecycle support.

    This node provides comprehensive user management capabilities including:
    - Complete user CRUD operations
    - JSONB-based role and attribute management
    - Multi-tenant user isolation
    - User profile and metadata management
    - Bulk operations for enterprise scenarios
    - Integration with authentication systems
    - Comprehensive audit logging

    Parameters:
        operation: Type of user management operation
        user_id: User ID for single user operations
        user_data: User data for create/update operations
        users_data: List of user data for bulk operations
        email: Email address for user lookup
        username: Username for user lookup
        tenant_id: Tenant isolation
        status: User status filter
        search_query: Search query for user search
        limit: Result limit for list operations
        offset: Result offset for pagination
        include_deleted: Whether to include deleted users
        export_format: Format for user export

    Example:
        >>> # Create a new user
        >>> node = UserManagementNode(
        ...     operation="create_user",
        ...     user_data={
        ...         "email": "john.doe@company.com",
        ...         "username": "johndoe",
        ...         "first_name": "John",
        ...         "last_name": "Doe",
        ...         "roles": ["employee", "developer"],
        ...         "attributes": {"department": "engineering", "level": "senior"}
        ...     },
        ...     tenant_id="company"
        ... )
        >>> result = node.execute()
        >>> user_id = result["user"]["user_id"]

        >>> # Update user profile
        >>> node = UserManagementNode(
        ...     operation="update_profile",
        ...     user_id="user123",
        ...     user_data={
        ...         "display_name": "John D. Smith",
        ...         "attributes": {"department": "engineering", "level": "lead"}
        ...     },
        ...     tenant_id="company"
        ... )
        >>> result = node.execute()

        >>> # Bulk create users
        >>> node = UserManagementNode(
        ...     operation="bulk_create",
        ...     users_data=[
        ...         {"email": "user1@company.com", "roles": ["employee"]},
        ...         {"email": "user2@company.com", "roles": ["manager"]},
        ...     ],
        ...     tenant_id="company"
        ... )
        >>> result = node.execute()
        >>> created_count = result["bulk_result"]["created_count"]
    """

    def __init__(self, **config):
        super().__init__(**config)
        self._db_node = None
        self._schema_manager = None
        self.logger = logging.getLogger(__name__)

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
                # User identification
                NodeParameter(
                    name="user_id",
                    type=str,
                    required=False,
                    description="User ID for single user operations",
                ),
                NodeParameter(
                    name="email",
                    type=str,
                    required=False,
                    description="Email address for user lookup",
                ),
                NodeParameter(
                    name="username",
                    type=str,
                    required=False,
                    description="Username for user lookup",
                ),
                # User data
                NodeParameter(
                    name="user_data",
                    type=dict,
                    required=False,
                    description="User data for create/update operations",
                ),
                NodeParameter(
                    name="users_data",
                    type=list,
                    required=False,
                    description="List of user data for bulk operations",
                ),
                NodeParameter(
                    name="user_ids",
                    type=list,
                    required=False,
                    description="List of user IDs for bulk delete operations",
                ),
                # Filtering and search
                NodeParameter(
                    name="status",
                    type=str,
                    required=False,
                    choices=[status.value for status in UserStatus],
                    description="User status filter",
                ),
                NodeParameter(
                    name="search_query",
                    type=str,
                    required=False,
                    description="Search query for user search",
                ),
                # Pagination
                NodeParameter(
                    name="limit",
                    type=int,
                    required=False,
                    default=50,
                    description="Result limit for list operations",
                ),
                NodeParameter(
                    name="offset",
                    type=int,
                    required=False,
                    default=0,
                    description="Result offset for pagination",
                ),
                # Options
                NodeParameter(
                    name="include_deleted",
                    type=bool,
                    required=False,
                    default=False,
                    description="Whether to include deleted users",
                ),
                NodeParameter(
                    name="export_format",
                    type=str,
                    required=False,
                    default="json",
                    choices=["json", "csv"],
                    description="Format for user export",
                ),
                # Password reset parameters
                NodeParameter(
                    name="token",
                    type=str,
                    required=False,
                    description="Password reset token",
                ),
                NodeParameter(
                    name="new_password",
                    type=str,
                    required=False,
                    description="New password for reset",
                ),
                NodeParameter(
                    name="password",
                    type=str,
                    required=False,
                    description="Password for authentication",
                ),
                # Security
                NodeParameter(
                    name="password_hash",
                    type=str,
                    required=False,
                    description="Password hash for user creation/update",
                ),
                # Multi-tenancy
                NodeParameter(
                    name="tenant_id",
                    type=str,
                    required=True,
                    description="Tenant ID for multi-tenant isolation",
                ),
                # Database configuration
                NodeParameter(
                    name="database_config",
                    type=dict,
                    required=True,
                    description="Database connection configuration",
                ),
            ]
        }

    def run(self, **inputs) -> Dict[str, Any]:
        """Execute user management operation."""
        try:
            operation = UserOperation(inputs["operation"])

            # Initialize dependencies
            self._init_dependencies(inputs)

            # Route to appropriate operation
            if operation == UserOperation.CREATE_USER:
                return self._create_user(inputs)
            elif operation == UserOperation.UPDATE_USER:
                return self._update_user(inputs)
            elif operation == UserOperation.DELETE_USER:
                return self._delete_user(inputs)
            elif operation == UserOperation.GET_USER:
                return self._get_user(inputs)
            elif operation == UserOperation.LIST_USERS:
                return self._list_users(inputs)
            elif operation == UserOperation.ACTIVATE_USER:
                return self._activate_user(inputs)
            elif operation == UserOperation.DEACTIVATE_USER:
                return self._deactivate_user(inputs)
            elif operation == UserOperation.SET_PASSWORD:
                return self._set_password(inputs)
            elif operation == UserOperation.UPDATE_PROFILE:
                return self._update_profile(inputs)
            elif operation == UserOperation.BULK_CREATE:
                return self._bulk_create(inputs)
            elif operation == UserOperation.BULK_UPDATE:
                return self._bulk_update(inputs)
            elif operation == UserOperation.BULK_DELETE:
                return self._bulk_delete(inputs)
            elif operation == UserOperation.GET_USER_ROLES:
                return self._get_user_roles(inputs)
            elif operation == UserOperation.GET_USER_PERMISSIONS:
                return self._get_user_permissions(inputs)
            elif operation == UserOperation.SEARCH_USERS:
                return self._search_users(inputs)
            elif operation == UserOperation.EXPORT_USERS:
                return self._export_users(inputs)
            elif operation == UserOperation.GENERATE_RESET_TOKEN:
                return self._generate_reset_token(inputs)
            elif operation == UserOperation.RESET_PASSWORD:
                return self._reset_password(inputs)
            elif operation == UserOperation.AUTHENTICATE:
                return self._authenticate(inputs)
            else:
                raise NodeExecutionError(f"Unknown operation: {operation}")

        except Exception as e:
            raise NodeExecutionError(f"User management operation failed: {str(e)}")

    def _init_dependencies(self, inputs: Dict[str, Any]):
        """Initialize database and schema manager dependencies."""
        # Skip initialization if already initialized (for testing)
        if hasattr(self, "_db_node") and self._db_node is not None:
            return

        db_config = inputs["database_config"]

        # Initialize database node
        self._db_node = SQLDatabaseNode(name="user_management_db", **db_config)

        # Initialize schema manager and ensure schema exists
        if not self._schema_manager:
            self._schema_manager = AdminSchemaManager(db_config)

            # Validate schema exists, create if needed
            try:
                validation = self._schema_manager.validate_schema()
                if not validation["is_valid"]:
                    self.logger.info(
                        "Creating unified admin schema for user management..."
                    )
                    self._schema_manager.create_full_schema(drop_existing=False)
                    self.logger.info("Unified admin schema created successfully")
            except Exception as e:
                self.logger.warning(f"Schema validation/creation failed: {e}")

    def _create_user(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new user."""
        user_data = inputs["user_data"]
        tenant_id = inputs["tenant_id"]

        # Validate required fields
        if "email" not in user_data:
            raise NodeValidationError("Email is required for user creation")

        # Generate user ID if not provided
        user_id = user_data.get("user_id", str(uuid4()))

        # Prepare user data with defaults
        user = User(
            user_id=user_id,
            email=user_data["email"],
            username=user_data.get("username"),
            first_name=user_data.get("first_name"),
            last_name=user_data.get("last_name"),
            display_name=user_data.get("display_name"),
            roles=user_data.get("roles", []),
            attributes=user_data.get("attributes", {}),
            status=UserStatus(user_data.get("status", "active")),
            tenant_id=tenant_id,
            external_auth_id=user_data.get("external_auth_id"),
            auth_provider=user_data.get("auth_provider", "local"),
        )

        # Insert user into database with conflict resolution
        insert_query = """
        INSERT INTO users (
            user_id, email, username, password_hash, first_name, last_name,
            display_name, roles, attributes, status, tenant_id,
            external_auth_id, auth_provider
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
        ON CONFLICT (user_id) DO UPDATE SET
            email = EXCLUDED.email,
            username = EXCLUDED.username,
            first_name = EXCLUDED.first_name,
            last_name = EXCLUDED.last_name,
            display_name = EXCLUDED.display_name,
            roles = EXCLUDED.roles,
            attributes = EXCLUDED.attributes,
            status = EXCLUDED.status,
            external_auth_id = EXCLUDED.external_auth_id,
            auth_provider = EXCLUDED.auth_provider,
            updated_at = CURRENT_TIMESTAMP
        """

        try:
            self._db_node.execute(
                query=insert_query,
                parameters=[
                    user.user_id,
                    user.email,
                    user.username,
                    hash_password(inputs.get("password", "")),
                    user.first_name,
                    user.last_name,
                    user.display_name,
                    json.dumps(user.roles),
                    json.dumps(user.attributes),
                    user.status.value,
                    user.tenant_id,
                    user.external_auth_id,
                    user.auth_provider,
                ],
            )

            # Return the user data that was successfully inserted
            # Add timestamps that would be set by the database
            user_dict = user.to_dict()
            user_dict["created_at"] = datetime.now(UTC).isoformat()
            user_dict["updated_at"] = datetime.now(UTC).isoformat()

            return {
                "result": {
                    "user": user_dict,
                    "operation": "create_user",
                    "timestamp": datetime.now(UTC).isoformat(),
                }
            }

        except Exception as e:
            if "duplicate key" in str(e).lower():
                raise NodeValidationError(
                    f"User with email {user.email} already exists"
                )
            raise NodeExecutionError(f"Failed to create user: {str(e)}")

    def _get_user_by_id(self, user_id: str, tenant_id: str) -> User:
        """Get user by ID and tenant."""
        query = """
        SELECT user_id, email, username, first_name, last_name, display_name,
               roles, attributes, status, tenant_id, external_auth_id, auth_provider,
               created_at, updated_at, last_login_at
        FROM users
        WHERE user_id = $1 AND tenant_id = $2
        """

        result = self._db_node.execute(
            query=query, parameters=[user_id, tenant_id], result_format="dict"
        )

        user_rows = result.get("data", [])
        if not user_rows:
            raise NodeValidationError(f"User not found: {user_id}")

        user_data = user_rows[0]
        return User(
            user_id=user_data["user_id"],
            email=user_data["email"],
            username=user_data["username"],
            first_name=user_data["first_name"],
            last_name=user_data["last_name"],
            display_name=user_data["display_name"],
            roles=user_data.get("roles", []),
            attributes=user_data.get("attributes", {}),
            status=UserStatus(user_data["status"]),
            tenant_id=user_data["tenant_id"],
            external_auth_id=user_data["external_auth_id"],
            auth_provider=user_data["auth_provider"],
            created_at=parse_datetime(user_data.get("created_at")),
            updated_at=parse_datetime(user_data.get("updated_at")),
            last_login_at=parse_datetime(user_data.get("last_login_at")),
        )

    def _get_user(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Get a single user by ID, email, or username."""
        tenant_id = inputs["tenant_id"]
        user_id = inputs.get("user_id")
        email = inputs.get("email")
        username = inputs.get("username")

        if not any([user_id, email, username]):
            raise NodeValidationError("Must provide user_id, email, or username")

        # Build query based on available identifiers
        if user_id:
            user = self._get_user_by_id(user_id, tenant_id)
        elif email:
            user = self._get_user_by_email(email, tenant_id)
        else:
            user = self._get_user_by_username(username, tenant_id)

        return {
            "result": {
                "user": user.to_dict(),
                "operation": "get_user",
                "timestamp": datetime.now(UTC).isoformat(),
            }
        }

    def _get_user_by_email(self, email: str, tenant_id: str) -> User:
        """Get user by email and tenant."""
        query = """
        SELECT user_id, email, username, first_name, last_name, display_name,
               roles, attributes, status, tenant_id, external_auth_id, auth_provider,
               created_at, updated_at, last_login_at
        FROM users
        WHERE email = $1 AND tenant_id = $2
        """

        result = self._db_node.execute(
            query=query, parameters=[email, tenant_id], result_format="dict"
        )

        user_rows = result.get("data", [])
        if not user_rows:
            raise NodeValidationError(f"User not found with email: {email}")

        user_data = user_rows[0]
        return User(
            user_id=user_data["user_id"],
            email=user_data["email"],
            username=user_data["username"],
            first_name=user_data["first_name"],
            last_name=user_data["last_name"],
            display_name=user_data["display_name"],
            roles=user_data.get("roles", []),
            attributes=user_data.get("attributes", {}),
            status=UserStatus(user_data["status"]),
            tenant_id=user_data["tenant_id"],
            external_auth_id=user_data["external_auth_id"],
            auth_provider=user_data["auth_provider"],
            created_at=parse_datetime(user_data.get("created_at")),
            updated_at=parse_datetime(user_data.get("updated_at")),
            last_login_at=parse_datetime(user_data.get("last_login_at")),
        )

    def _get_user_by_username(self, username: str, tenant_id: str) -> User:
        """Get user by username and tenant."""
        query = """
        SELECT user_id, email, username, first_name, last_name, display_name,
               roles, attributes, status, tenant_id, external_auth_id, auth_provider,
               created_at, updated_at, last_login_at
        FROM users
        WHERE username = $1 AND tenant_id = $2
        """

        result = self._db_node.execute(
            query=query, parameters=[username, tenant_id], result_format="dict"
        )

        user_rows = result.get("data", [])
        if not user_rows:
            raise NodeValidationError(f"User not found with username: {username}")

        user_data = user_rows[0]
        return User(
            user_id=user_data["user_id"],
            email=user_data["email"],
            username=user_data["username"],
            first_name=user_data["first_name"],
            last_name=user_data["last_name"],
            display_name=user_data["display_name"],
            roles=user_data.get("roles", []),
            attributes=user_data.get("attributes", {}),
            status=UserStatus(user_data["status"]),
            tenant_id=user_data["tenant_id"],
            external_auth_id=user_data["external_auth_id"],
            auth_provider=user_data["auth_provider"],
            created_at=parse_datetime(user_data.get("created_at")),
            updated_at=parse_datetime(user_data.get("updated_at")),
            last_login_at=parse_datetime(user_data.get("last_login_at")),
        )

    def _update_user(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Update an existing user."""
        user_id = inputs["user_id"]
        user_data = inputs["user_data"]
        tenant_id = inputs["tenant_id"]

        # Get existing user
        existing_user = self._get_user_by_id(user_id, tenant_id)

        # Build update query dynamically based on provided fields
        update_fields = []
        parameters = []
        param_index = 1

        updatable_fields = [
            "email",
            "username",
            "first_name",
            "last_name",
            "display_name",
            "status",
            "external_auth_id",
            "auth_provider",
        ]

        for field in updatable_fields:
            if field in user_data:
                update_fields.append(f"{field} = ${param_index}")
                parameters.append(user_data[field])
                param_index += 1

        # Handle JSONB fields separately
        if "roles" in user_data:
            update_fields.append(f"roles = ${param_index}")
            parameters.append(json.dumps(user_data["roles"]))
            param_index += 1

        if "attributes" in user_data:
            update_fields.append(f"attributes = ${param_index}")
            parameters.append(json.dumps(user_data["attributes"]))
            param_index += 1

        if "password_hash" in inputs:
            update_fields.append(f"password_hash = ${param_index}")
            parameters.append(inputs["password_hash"])
            param_index += 1

        if not update_fields:
            raise NodeValidationError("No valid fields provided for update")

        # Always update the updated_at timestamp
        update_fields.append("updated_at = CURRENT_TIMESTAMP")

        # Add WHERE clause parameters
        parameters.extend([user_id, tenant_id])

        update_query = f"""
        UPDATE users
        SET {', '.join(update_fields)}
        WHERE user_id = ${param_index} AND tenant_id = ${param_index + 1}
        """

        try:
            self._db_node.execute(query=update_query, parameters=parameters)

            # Get updated user
            updated_user = self._get_user_by_id(user_id, tenant_id)

            return {
                "result": {
                    "user": updated_user.to_dict(),
                    "operation": "update_user",
                    "timestamp": datetime.now(UTC).isoformat(),
                }
            }

        except Exception as e:
            raise NodeExecutionError(f"Failed to update user: {str(e)}")

    def _delete_user(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Delete (or soft-delete) a user."""
        user_id = inputs["user_id"]
        tenant_id = inputs["tenant_id"]
        hard_delete = inputs.get("hard_delete", False)

        # Get existing user to return in response
        existing_user = self._get_user_by_id(user_id, tenant_id)

        if hard_delete:
            # Hard delete - remove from database
            delete_query = "DELETE FROM users WHERE user_id = $1 AND tenant_id = $2"
        else:
            # Soft delete - mark as deleted
            delete_query = """
            UPDATE users
            SET status = 'deleted', updated_at = CURRENT_TIMESTAMP
            WHERE user_id = $1 AND tenant_id = $2
            """

        try:
            self._db_node.execute(query=delete_query, parameters=[user_id, tenant_id])

            return {
                "result": {
                    "deleted_user": existing_user.to_dict(),
                    "hard_delete": hard_delete,
                    "operation": "delete_user",
                    "timestamp": datetime.now(UTC).isoformat(),
                }
            }

        except Exception as e:
            raise NodeExecutionError(f"Failed to delete user: {str(e)}")

    def _list_users(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """List users with filtering and pagination."""
        tenant_id = inputs["tenant_id"]
        status = inputs.get("status")
        limit = inputs.get("limit", 50)
        offset = inputs.get("offset", 0)
        include_deleted = inputs.get("include_deleted", False)

        # Build query with filters
        where_conditions = ["tenant_id = $1"]
        parameters = [tenant_id]
        param_index = 2

        if status:
            where_conditions.append(f"status = ${param_index}")
            parameters.append(status)
            param_index += 1
        elif not include_deleted:
            where_conditions.append(f"status != ${param_index}")
            parameters.append("deleted")
            param_index += 1

        # Add pagination
        parameters.extend([limit, offset])

        list_query = f"""
        SELECT user_id, email, username, first_name, last_name, display_name,
               roles, attributes, status, tenant_id, external_auth_id, auth_provider,
               created_at, updated_at, last_login_at
        FROM users
        WHERE {' AND '.join(where_conditions)}
        ORDER BY created_at DESC
        LIMIT ${param_index} OFFSET ${param_index + 1}
        """

        count_query = f"""
        SELECT COUNT(*) as total_count
        FROM users
        WHERE {' AND '.join(where_conditions)}
        """

        try:
            # Get users
            result = self._db_node.execute(
                query=list_query, parameters=parameters, result_format="dict"
            )

            # Get total count
            count_result = self._db_node.execute(
                query=count_query, parameters=parameters[:-2], result_format="dict"
            )

            users = []
            for user_data in result.get("data", []):
                user = User(
                    user_id=user_data["user_id"],
                    email=user_data["email"],
                    username=user_data["username"],
                    first_name=user_data["first_name"],
                    last_name=user_data["last_name"],
                    display_name=user_data["display_name"],
                    roles=user_data.get("roles", []),
                    attributes=user_data.get("attributes", {}),
                    status=UserStatus(user_data["status"]),
                    tenant_id=user_data["tenant_id"],
                    external_auth_id=user_data["external_auth_id"],
                    auth_provider=user_data["auth_provider"],
                    created_at=user_data.get("created_at"),
                    updated_at=user_data.get("updated_at"),
                    last_login_at=user_data.get("last_login_at"),
                )
                users.append(user.to_dict())

            total_count = count_result.get("data", [{}])[0].get("total_count", 0)

            return {
                "result": {
                    "users": users,
                    "pagination": {
                        "total_count": total_count,
                        "limit": limit,
                        "offset": offset,
                        "has_more": offset + limit < total_count,
                    },
                    "filters": {
                        "status": status,
                        "include_deleted": include_deleted,
                    },
                    "operation": "list_users",
                    "timestamp": datetime.now(UTC).isoformat(),
                }
            }

        except Exception as e:
            raise NodeExecutionError(f"Failed to list users: {str(e)}")

    def _activate_user(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Activate a user."""
        return self._change_user_status(inputs, UserStatus.ACTIVE, "activate_user")

    def _deactivate_user(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Deactivate a user."""
        return self._change_user_status(inputs, UserStatus.INACTIVE, "deactivate_user")

    def _change_user_status(
        self, inputs: Dict[str, Any], new_status: UserStatus, operation: str
    ) -> Dict[str, Any]:
        """Helper method to change user status."""
        user_id = inputs["user_id"]
        tenant_id = inputs["tenant_id"]

        update_query = """
        UPDATE users
        SET status = $1, updated_at = CURRENT_TIMESTAMP
        WHERE user_id = $2 AND tenant_id = $3
        """

        try:
            self._db_node.execute(
                query=update_query, parameters=[new_status.value, user_id, tenant_id]
            )

            # Get updated user
            updated_user = self._get_user_by_id(user_id, tenant_id)

            return {
                "result": {
                    "user": updated_user.to_dict(),
                    "operation": operation,
                    "timestamp": datetime.now(UTC).isoformat(),
                }
            }

        except Exception as e:
            raise NodeExecutionError(f"Failed to {operation}: {str(e)}")

    def _set_password(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Set user password hash."""
        user_id = inputs["user_id"]
        tenant_id = inputs["tenant_id"]
        password = inputs.get("password", "")
        password_hash = hash_password(password)

        update_query = """
        UPDATE users
        SET password_hash = $1, updated_at = CURRENT_TIMESTAMP
        WHERE user_id = $2 AND tenant_id = $3
        """

        try:
            self._db_node.execute(
                query=update_query, parameters=[password_hash, user_id, tenant_id]
            )

            return {
                "result": {
                    "user_id": user_id,
                    "password_updated": True,
                    "operation": "set_password",
                    "timestamp": datetime.now(UTC).isoformat(),
                }
            }

        except Exception as e:
            raise NodeExecutionError(f"Failed to set password: {str(e)}")

    def _update_profile(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Update user profile fields."""
        # This is essentially the same as update_user but with a different operation name
        result = self._update_user(inputs)
        result["result"]["operation"] = "update_profile"
        return result

    def _bulk_create(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Create multiple users in bulk."""
        users_data = inputs["users_data"]
        tenant_id = inputs["tenant_id"]

        if not isinstance(users_data, list):
            raise NodeValidationError("users_data must be a list")

        created_users = []
        failed_users = []

        for i, user_data in enumerate(users_data):
            try:
                # Create each user individually for better error handling
                # Extract password from user_data if present
                user_data_copy = user_data.copy()
                password = user_data_copy.pop("password", "")
                create_inputs = {
                    "operation": "create_user",
                    "user_data": user_data_copy,
                    "password": password,
                    "tenant_id": tenant_id,
                    "database_config": inputs["database_config"],
                }

                result = self._create_user(create_inputs)
                created_users.append(result["result"]["user"])

            except Exception as e:
                failed_users.append(
                    {
                        "index": i,
                        "user_data": user_data,
                        "error": str(e),
                    }
                )

        return {
            "result": {
                "bulk_result": {
                    "created_count": len(created_users),
                    "failed_count": len(failed_users),
                    "total_count": len(users_data),
                    "created_users": created_users,
                    "failed_users": failed_users,
                },
                "operation": "bulk_create",
                "timestamp": datetime.now(UTC).isoformat(),
            }
        }

    def _bulk_update(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Update multiple users in bulk."""
        users_data = inputs["users_data"]
        tenant_id = inputs["tenant_id"]

        if not isinstance(users_data, list):
            raise NodeValidationError("users_data must be a list")

        updated_users = []
        failed_users = []

        for i, user_data in enumerate(users_data):
            try:
                if "user_id" not in user_data:
                    raise NodeValidationError("user_id is required for bulk update")

                update_inputs = {
                    "operation": "update_user",
                    "user_id": user_data.pop("user_id"),
                    "user_data": user_data,
                    "tenant_id": tenant_id,
                    "database_config": inputs["database_config"],
                }

                result = self._update_user(update_inputs)
                updated_users.append(result["result"]["user"])

            except Exception as e:
                failed_users.append(
                    {
                        "index": i,
                        "user_data": user_data,
                        "error": str(e),
                    }
                )

        return {
            "result": {
                "bulk_result": {
                    "updated_count": len(updated_users),
                    "failed_count": len(failed_users),
                    "total_count": len(users_data),
                    "updated_users": updated_users,
                    "failed_users": failed_users,
                },
                "operation": "bulk_update",
                "timestamp": datetime.now(UTC).isoformat(),
            }
        }

    def _bulk_delete(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Delete multiple users in bulk."""
        user_ids = inputs.get("user_ids", [])
        tenant_id = inputs["tenant_id"]
        hard_delete = inputs.get("hard_delete", False)

        if not isinstance(user_ids, list):
            raise NodeValidationError("user_ids must be a list")

        deleted_users = []
        failed_users = []

        for user_id in user_ids:
            try:
                delete_inputs = {
                    "operation": "delete_user",
                    "user_id": user_id,
                    "tenant_id": tenant_id,
                    "hard_delete": hard_delete,
                    "database_config": inputs["database_config"],
                }

                result = self._delete_user(delete_inputs)
                deleted_users.append(result["result"]["deleted_user"])

            except Exception as e:
                failed_users.append(
                    {
                        "user_id": user_id,
                        "error": str(e),
                    }
                )

        return {
            "result": {
                "bulk_result": {
                    "deleted_count": len(deleted_users),
                    "failed_count": len(failed_users),
                    "total_count": len(user_ids),
                    "deleted_users": deleted_users,
                    "failed_users": failed_users,
                    "hard_delete": hard_delete,
                },
                "operation": "bulk_delete",
                "timestamp": datetime.now(UTC).isoformat(),
            }
        }

    def _get_user_roles(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Get roles assigned to a user."""
        user_id = inputs["user_id"]
        tenant_id = inputs["tenant_id"]

        # Get user with roles
        user = self._get_user_by_id(user_id, tenant_id)

        # Get detailed role information
        if user.roles:
            placeholders = ",".join([f"${i+1}" for i in range(len(user.roles))])
            role_query = f"""
            SELECT role_id, name, description, permissions, parent_roles, attributes
            FROM roles
            WHERE role_id IN ({placeholders}) AND tenant_id = ${len(user.roles) + 1}
            """

            result = self._db_node.execute(
                query=role_query,
                parameters=user.roles + [tenant_id],
                result_format="dict",
            )
            role_details = result.get("data", [])
        else:
            role_details = []

        return {
            "result": {
                "user_id": user_id,
                "roles": user.roles,
                "role_details": role_details,
                "operation": "get_user_roles",
                "timestamp": datetime.now(UTC).isoformat(),
            }
        }

    def _get_user_permissions(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Get effective permissions for a user."""
        user_id = inputs["user_id"]
        tenant_id = inputs["tenant_id"]

        # This would integrate with PermissionCheckNode to get effective permissions
        # For now, return a basic implementation
        user = self._get_user_by_id(user_id, tenant_id)

        return {
            "result": {
                "user_id": user_id,
                "roles": user.roles,
                "attributes": user.attributes,
                "operation": "get_user_permissions",
                "note": "Use PermissionCheckNode.get_user_permissions for complete permission evaluation",
                "timestamp": datetime.now(UTC).isoformat(),
            }
        }

    def _search_users(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Search users by query."""
        search_query = inputs["search_query"]
        tenant_id = inputs["tenant_id"]
        limit = inputs.get("limit", 50)
        offset = inputs.get("offset", 0)

        # Simple text search across email, username, first_name, last_name
        query = """
        SELECT user_id, email, username, first_name, last_name, display_name,
               roles, attributes, status, tenant_id, external_auth_id, auth_provider,
               created_at, updated_at, last_login_at
        FROM users
        WHERE tenant_id = $1 AND status != 'deleted' AND (
            email ILIKE $2 OR
            username ILIKE $2 OR
            first_name ILIKE $2 OR
            last_name ILIKE $2 OR
            display_name ILIKE $2
        )
        ORDER BY created_at DESC
        LIMIT $3 OFFSET $4
        """

        search_pattern = f"%{search_query}%"

        try:
            result = self._db_node.execute(
                query=query,
                parameters=[tenant_id, search_pattern, limit, offset],
                result_format="dict",
            )

            users = []
            for user_data in result.get("data", []):
                user = User(
                    user_id=user_data["user_id"],
                    email=user_data["email"],
                    username=user_data["username"],
                    first_name=user_data["first_name"],
                    last_name=user_data["last_name"],
                    display_name=user_data["display_name"],
                    roles=user_data.get("roles", []),
                    attributes=user_data.get("attributes", {}),
                    status=UserStatus(user_data["status"]),
                    tenant_id=user_data["tenant_id"],
                    external_auth_id=user_data["external_auth_id"],
                    auth_provider=user_data["auth_provider"],
                    created_at=user_data.get("created_at"),
                    updated_at=user_data.get("updated_at"),
                    last_login_at=user_data.get("last_login_at"),
                )
                users.append(user.to_dict())

            return {
                "result": {
                    "users": users,
                    "search_query": search_query,
                    "count": len(users),
                    "pagination": {
                        "limit": limit,
                        "offset": offset,
                    },
                    "operation": "search_users",
                    "timestamp": datetime.now(UTC).isoformat(),
                }
            }

        except Exception as e:
            raise NodeExecutionError(f"Failed to search users: {str(e)}")

    def _export_users(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Export users in specified format."""
        tenant_id = inputs["tenant_id"]
        export_format = inputs.get("export_format", "json")
        include_deleted = inputs.get("include_deleted", False)

        # Get all users for export
        list_inputs = {
            **inputs,
            "operation": "list_users",
            "limit": 10000,  # Large limit for export
            "offset": 0,
            "include_deleted": include_deleted,
        }

        result = self._list_users(list_inputs)
        users = result["result"]["users"]

        if export_format == "json":
            export_data = {
                "users": users,
                "export_metadata": {
                    "tenant_id": tenant_id,
                    "export_time": datetime.now(UTC).isoformat(),
                    "total_users": len(users),
                    "include_deleted": include_deleted,
                },
            }
        elif export_format == "csv":
            # Convert to CSV format (simplified)
            csv_headers = [
                "user_id",
                "email",
                "username",
                "first_name",
                "last_name",
                "status",
                "roles",
                "created_at",
            ]
            csv_rows = []
            for user in users:
                csv_rows.append(
                    [
                        user.get("user_id", ""),
                        user.get("email", ""),
                        user.get("username", ""),
                        user.get("first_name", ""),
                        user.get("last_name", ""),
                        user.get("status", ""),
                        ",".join(user.get("roles", [])),
                        user.get("created_at", ""),
                    ]
                )

            export_data = {
                "format": "csv",
                "headers": csv_headers,
                "rows": csv_rows,
                "export_metadata": {
                    "tenant_id": tenant_id,
                    "export_time": datetime.now(UTC).isoformat(),
                    "total_users": len(users),
                    "include_deleted": include_deleted,
                },
            }
        else:
            raise NodeValidationError(f"Unsupported export format: {export_format}")

        return {
            "result": {
                "export_data": export_data,
                "operation": "export_users",
                "timestamp": datetime.now(UTC).isoformat(),
            }
        }

    def _generate_reset_token(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Generate a password reset token for a user."""
        user_id = inputs["user_id"]
        tenant_id = inputs["tenant_id"]

        # Generate a secure reset token
        token = str(uuid4())
        expires_at = datetime.now(UTC) + timedelta(hours=1)

        # Store token in database (using user_sessions table)
        store_token_query = """
        INSERT INTO user_sessions (
            session_id, user_id, tenant_id,
            session_token_hash, expires_at, created_at,
            last_accessed, ip_address, user_agent
        ) VALUES (
            :session_id, :user_id, :tenant_id,
            :token_hash, :expires_at, :created_at,
            :last_accessed, :ip_address, :user_agent
        )
        """

        result = self._db_node.execute(
            operation="execute",
            query=store_token_query,
            parameters={
                "session_id": token,
                "user_id": user_id,
                "tenant_id": tenant_id,
                "token_hash": hashlib.sha256(f"reset_{token}".encode()).hexdigest(),
                "expires_at": expires_at,
                "created_at": datetime.now(UTC),
                "last_accessed": datetime.now(UTC),
                "ip_address": "127.0.0.1",
                "user_agent": "password_reset_token",
            },
        )

        return {
            "token": token,
            "expires_at": expires_at.isoformat(),
            "user_id": user_id,
        }

    def _reset_password(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Reset user password using a valid token."""
        token = inputs["token"]
        new_password = inputs["new_password"]
        tenant_id = inputs["tenant_id"]

        # Verify token and get user_id
        verify_query = """
        SELECT user_id FROM user_sessions
        WHERE session_id = :token
        AND tenant_id = :tenant_id
        AND user_agent = 'password_reset_token'
        AND expires_at > CURRENT_TIMESTAMP
        """

        result = self._db_node.execute(
            operation="query",
            query=verify_query,
            parameters={"token": token, "tenant_id": tenant_id},
        )

        if not result.get("data", []):
            raise NodeExecutionError("Invalid or expired reset token")

        user_id = result["data"][0]["user_id"]

        # Update password
        password_hash = hash_password(new_password)
        update_query = """
        UPDATE users
        SET password_hash = :password_hash,
            updated_at = CURRENT_TIMESTAMP
        WHERE user_id = :user_id
        AND tenant_id = :tenant_id
        """

        update_result = self._db_node.execute(
            operation="execute",
            query=update_query,
            parameters={
                "password_hash": password_hash,
                "user_id": user_id,
                "tenant_id": tenant_id,
            },
        )

        # Delete the used token
        delete_token_query = """
        DELETE FROM user_sessions
        WHERE session_id = :token
        """

        self._db_node.execute(
            operation="execute", query=delete_token_query, parameters={"token": token}
        )

        return {
            "success": True,
            "user_id": user_id,
            "message": "Password reset successfully",
        }

    def _authenticate(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Authenticate a user with username/email and password."""
        username = inputs.get("username")
        email = inputs.get("email")
        password = inputs["password"]
        tenant_id = inputs["tenant_id"]

        # Build query based on provided credentials
        if username:
            auth_query = """
            SELECT user_id, password_hash, status
            FROM users
            WHERE username = :username
            AND tenant_id = :tenant_id
            """
            params = {"username": username, "tenant_id": tenant_id}
        elif email:
            auth_query = """
            SELECT user_id, password_hash, status
            FROM users
            WHERE email = :email
            AND tenant_id = :tenant_id
            """
            params = {"email": email, "tenant_id": tenant_id}
        else:
            raise NodeValidationError("Either username or email must be provided")

        result = self._db_node.execute(
            operation="query", query=auth_query, parameters=params
        )

        if not result.get("data", []):
            return {"authenticated": False, "message": "User not found"}

        user_data = result["data"][0]
        stored_hash = user_data["password_hash"]

        if not verify_password(password, stored_hash):
            return {"authenticated": False, "message": "Invalid password"}

        if user_data["status"] != "active":
            return {
                "authenticated": False,
                "message": f"User account is {user_data['status']}",
            }

        # Update last login
        update_login_query = """
        UPDATE users
        SET last_login_at = CURRENT_TIMESTAMP
        WHERE user_id = :user_id
        """

        self._db_node.execute(
            operation="execute",
            query=update_login_query,
            parameters={"user_id": user_data["user_id"]},
        )

        return {
            "authenticated": True,
            "user_id": user_data["user_id"],
            "message": "Authentication successful",
        }

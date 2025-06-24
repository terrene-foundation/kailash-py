# User Management API Reference

## UserManagementNode

### Overview
The `UserManagementNode` provides comprehensive user lifecycle management with enterprise features.

```python
from kailash.nodes.admin import UserManagementNode

user_manager = UserManagementNode()
```

### Operations

#### create_user
Create a new user account.

**Parameters:**
- `operation` (str): "create_user"
- `tenant_id` (str): Tenant identifier for multi-tenancy
- `database_config` (dict): Database connection configuration
- `user_data` (dict): User information
  - `email` (str): User email address
  - `username` (str): Unique username
  - `first_name` (str, optional): First name
  - `last_name` (str, optional): Last name
  - `attributes` (dict, optional): Custom attributes
- `password` (str): Plain text password (will be hashed)
- `password_hash` (str, optional): Pre-hashed password

**Returns:**
```python
{
    "result": {
        "user": {
            "user_id": "uuid",
            "email": "user@example.com",
            "username": "username",
            "status": "active",
            "created_at": "2024-01-01T00:00:00Z"
        },
        "operation": "create_user",
        "timestamp": "2024-01-01T00:00:00Z"
    }
}
```

**Example:**
```python
result = user_manager.execute(
    operation="create_user",
    tenant_id="my_app",
    database_config=db_config,
    user_data={
        "email": "john@example.com",
        "username": "john_doe",
        "first_name": "John",
        "last_name": "Doe",
        "attributes": {
            "department": "Engineering",
            "employee_id": "EMP001"
        }
    },
    password="SecurePass123!"
)
```

#### update_user
Update an existing user's information.

**Parameters:**
- `operation` (str): "update_user"
- `tenant_id` (str): Tenant identifier
- `database_config` (dict): Database configuration
- `user_id` (str): User UUID to update
- `user_data` (dict): Fields to update

**Returns:**
```python
{
    "result": {
        "user": {...},  # Updated user object
        "operation": "update_user",
        "timestamp": "2024-01-01T00:00:00Z"
    }
}
```

#### delete_user
Soft delete a user (sets status to 'deleted').

**Parameters:**
- `operation` (str): "delete_user"
- `tenant_id` (str): Tenant identifier
- `database_config` (dict): Database configuration
- `user_id` (str): User UUID to delete
- `hard_delete` (bool, optional): If True, permanently delete

**Returns:**
```python
{
    "result": {
        "deleted_user": {...},
        "operation": "delete_user",
        "timestamp": "2024-01-01T00:00:00Z"
    }
}
```

#### get_user
Retrieve a user by ID.

**Parameters:**
- `operation` (str): "get_user"
- `tenant_id` (str): Tenant identifier
- `database_config` (dict): Database configuration
- `user_id` (str): User UUID

**Returns:**
```python
{
    "result": {
        "user": {
            "user_id": "uuid",
            "email": "user@example.com",
            "username": "username",
            "first_name": "John",
            "last_name": "Doe",
            "status": "active",
            "roles": [],
            "attributes": {},
            "created_at": "2024-01-01T00:00:00Z",
            "updated_at": "2024-01-01T00:00:00Z"
        }
    }
}
```

#### list_users
List users with optional filtering and pagination.

**Parameters:**
- `operation` (str): "list_users"
- `tenant_id` (str): Tenant identifier
- `database_config` (dict): Database configuration
- `filters` (dict, optional): Filter criteria
  - `status` (str): "active", "inactive", "suspended", "pending", "deleted"
  - `created_after` (str): ISO date string
  - `created_before` (str): ISO date string
- `limit` (int, optional): Maximum results (default: 50)
- `offset` (int, optional): Skip results (default: 0)
- `include_deleted` (bool, optional): Include soft-deleted users

**Returns:**
```python
{
    "result": {
        "users": [...],  # List of user objects
        "total": 100,
        "limit": 50,
        "offset": 0
    }
}
```

#### authenticate
Authenticate a user with username/email and password.

**Parameters:**
- `operation` (str): "authenticate"
- `tenant_id` (str): Tenant identifier
- `database_config` (dict): Database configuration
- `username` (str, optional): Username to authenticate
- `email` (str, optional): Email to authenticate (if username not provided)
- `password` (str): Plain text password

**Returns:**
```python
{
    "authenticated": true,
    "user_id": "uuid",
    "message": "Authentication successful"
}
# Or if failed:
{
    "authenticated": false,
    "message": "Invalid password"
}
```

#### generate_reset_token
Generate a password reset token for a user.

**Parameters:**
- `operation` (str): "generate_reset_token"
- `tenant_id` (str): Tenant identifier
- `database_config` (dict): Database configuration
- `user_id` (str): User UUID

**Returns:**
```python
{
    "token": "reset-token-uuid",
    "expires_at": "2024-01-01T01:00:00Z",
    "user_id": "user-uuid"
}
```

#### reset_password
Reset user password using a valid token.

**Parameters:**
- `operation` (str): "reset_password"
- `tenant_id` (str): Tenant identifier
- `database_config` (dict): Database configuration
- `token` (str): Reset token
- `new_password` (str): New password

**Returns:**
```python
{
    "success": true,
    "user_id": "uuid",
    "message": "Password reset successfully"
}
```

#### bulk_create
Create multiple users in a single operation.

**Parameters:**
- `operation` (str): "bulk_create"
- `tenant_id` (str): Tenant identifier
- `database_config` (dict): Database configuration
- `users_data` (list): List of user dictionaries
  - Each dict should contain: email, username, password_hash, attributes

**Returns:**
```python
{
    "result": {
        "bulk_result": {
            "created_count": 95,
            "failed_count": 5,
            "total_count": 100,
            "created_users": [...],
            "failed_users": [...]
        }
    }
}
```

#### bulk_update
Update multiple users in a single operation.

**Parameters:**
- `operation` (str): "bulk_update"
- `tenant_id` (str): Tenant identifier
- `database_config` (dict): Database configuration
- `users_data` (list): List of update dictionaries
  - Each dict must contain `user_id` and fields to update

**Returns:**
```python
{
    "result": {
        "bulk_result": {
            "updated_count": 50,
            "failed_count": 0,
            "total_count": 50
        }
    }
}
```

#### bulk_delete
Delete multiple users in a single operation.

**Parameters:**
- `operation` (str): "bulk_delete"
- `tenant_id` (str): Tenant identifier
- `database_config` (dict): Database configuration
- `user_ids` (list): List of user UUIDs to delete
- `hard_delete` (bool, optional): Permanently delete if True

**Returns:**
```python
{
    "result": {
        "bulk_result": {
            "deleted_count": 10,
            "failed_count": 0,
            "total_count": 10
        }
    }
}
```

#### search_users
Search users by various criteria.

**Parameters:**
- `operation` (str): "search_users"
- `tenant_id` (str): Tenant identifier
- `database_config` (dict): Database configuration
- `search_query` (str): Search term
- `search_fields` (list, optional): Fields to search in
- `limit` (int, optional): Maximum results

**Returns:**
```python
{
    "result": {
        "users": [...],
        "total_matches": 25,
        "search_query": "john"
    }
}
```

#### export_users
Export user data in various formats.

**Parameters:**
- `operation` (str): "export_users"
- `tenant_id` (str): Tenant identifier
- `database_config` (dict): Database configuration
- `export_format` (str): "json" or "csv"
- `filters` (dict, optional): Filter criteria
- `include_deleted` (bool, optional): Include deleted users

**Returns:**
```python
# For JSON format:
{
    "result": {
        "export_data": {
            "users": [...],
            "export_metadata": {
                "total_users": 100,
                "export_time": "2024-01-01T00:00:00Z"
            }
        }
    }
}

# For CSV format:
{
    "result": {
        "export_data": {
            "format": "csv",
            "headers": ["user_id", "email", "username", ...],
            "rows": [[...], [...], ...]
        }
    }
}
```

## RoleManagementNode

### Overview
The `RoleManagementNode` handles role-based access control (RBAC).

```python
from kailash.nodes.admin import RoleManagementNode

role_manager = RoleManagementNode()
```

### Operations

#### create_role
Create a new role with permissions.

**Parameters:**
- `operation` (str): "create_role"
- `tenant_id` (str): Tenant identifier
- `database_config` (dict): Database configuration
- `role_data` (dict):
  - `name` (str): Role name
  - `description` (str, optional): Role description
  - `permissions` (list): List of permission strings
  - `attributes` (dict, optional): Custom attributes

**Returns:**
```python
{
    "result": {
        "role": {
            "role_id": "uuid",
            "name": "admin",
            "description": "Administrator role",
            "permissions": ["users.*", "system.*"],
            "created_at": "2024-01-01T00:00:00Z"
        }
    }
}
```

#### update_role
Update an existing role.

**Parameters:**
- `operation` (str): "update_role"
- `tenant_id` (str): Tenant identifier
- `database_config` (dict): Database configuration
- `role_id` (str): Role UUID
- `role_data` (dict): Fields to update

#### delete_role
Delete a role.

**Parameters:**
- `operation` (str): "delete_role"
- `tenant_id` (str): Tenant identifier
- `database_config` (dict): Database configuration
- `role_id` (str): Role UUID

#### assign_user
Assign a role to a user.

**Parameters:**
- `operation` (str): "assign_user"
- `tenant_id` (str): Tenant identifier
- `database_config` (dict): Database configuration
- `user_id` (str): User UUID
- `role_id` (str): Role UUID

#### get_user_roles
Get all roles assigned to a user.

**Parameters:**
- `operation` (str): "get_user_roles"
- `tenant_id` (str): Tenant identifier
- `database_config` (dict): Database configuration
- `user_id` (str): User UUID

**Returns:**
```python
{
    "result": {
        "roles": [
            {
                "role_id": "uuid",
                "name": "admin",
                "permissions": ["users.*", "system.*"],
                "assigned_at": "2024-01-01T00:00:00Z"
            }
        ]
    }
}
```

## PermissionCheckNode

### Overview
The `PermissionCheckNode` verifies user permissions.

```python
from kailash.nodes.admin import PermissionCheckNode

permission_checker = PermissionCheckNode()
```

### Operations

#### check_permission
Check if a user has a specific permission.

**Parameters:**
- `operation` (str): "check_permission"
- `tenant_id` (str): Tenant identifier
- `database_config` (dict): Database configuration
- `user_id` (str): User UUID
- `permission` (str): Permission to check
- `resource_id` (str, optional): Resource ID for resource-specific checks

**Returns:**
```python
{
    "has_permission": true,
    "permission": "users.create",
    "user_id": "uuid",
    "source": "role:admin"
}
```

## Error Handling

All operations may raise the following exceptions:

- `NodeValidationError`: Invalid parameters provided
- `NodeExecutionError`: Operation failed during execution
- `DatabaseError`: Database connection or query failed

**Example:**
```python
try:
    result = user_manager.execute(
        operation="create_user",
        tenant_id="my_app",
        database_config=db_config,
        user_data={"email": "invalid-email"},  # Missing required fields
        password="pass"
    )
except NodeValidationError as e:
    print(f"Validation error: {e}")
except NodeExecutionError as e:
    print(f"Execution error: {e}")
```

## Performance Tips

1. **Use Bulk Operations**: For multiple users, use bulk_create/update/delete
2. **Pagination**: Always paginate when listing users
3. **Indexing**: Ensure database indexes on email, username, tenant_id
4. **Caching**: Permission results are cached automatically
5. **Connection Pooling**: Reuse database connections

## Security Best Practices

1. **Always Hash Passwords**: Never store plain text passwords
2. **Use Strong Passwords**: Enforce password policies
3. **Token Expiration**: Reset tokens expire in 1 hour
4. **Multi-Tenancy**: Always specify tenant_id
5. **Audit Logging**: All operations are logged
6. **Rate Limiting**: Implement at API layer
7. **SSL/TLS**: Use encrypted connections

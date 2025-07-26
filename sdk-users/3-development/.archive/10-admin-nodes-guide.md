# Admin Nodes Developer Guide

The Kailash SDK provides a comprehensive set of admin nodes for building enterprise-grade user management systems. These nodes handle user lifecycle, role-based access control (RBAC), and permission management with full multi-tenant support.

## Overview

The admin node system consists of three core components:

1. **UserManagementNode** - Complete user lifecycle management
2. **RoleManagementNode** - Hierarchical role management with inheritance
3. **PermissionCheckNode** - High-performance permission evaluation with caching

## Quick Start

### Basic User Management

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.admin import UserManagementNode

# Create user management node
user_node = UserManagementNode(
    database_config={
        "connection_string": "postgresql://user:pass@localhost/db",
        "database_type": "postgresql"
    }
)

# Create a new user (use execute() method)
result = user_node.execute(
    operation="create_user",
    user_data={
        "email": "john.doe@example.com",
        "username": "johndoe",
        "first_name": "John",
        "last_name": "Doe",
        "password": "SecurePassword123!",
        "roles": ["viewer", "contributor"]
    },
    tenant_id="tenant_001"
)

user_id = result["result"]["user"]["user_id"]

# Note: For production use, execute nodes through the runtime:
# runtime = LocalRuntime()
# result = runtime.execute_node(user_node, {...})
```

### Role Management

```python
from kailash.nodes.admin import RoleManagementNode

# Create role management node
role_node = RoleManagementNode(database_config=db_config)

# Create a role with inheritance
result = role_node.execute(
    operation="create_role",
    role_data={
        "name": "editor",
        "description": "Content editor with publishing rights",
        "permissions": ["content:write", "content:publish"],
        "parent_roles": ["contributor"]  # Inherits from contributor
    },
    tenant_id="tenant_001"
)
```

### Permission Checking

```python
from kailash.nodes.admin import PermissionCheckNode

# Create permission check node with Redis caching
perm_node = PermissionCheckNode(
    database_config=db_config,
    cache_backend="redis",
    cache_config={
        "host": "localhost",
        "port": 6379,
        "ttl": 300
    }
)

# Check permission
result = perm_node.execute(
    operation="check_permission",
    user_id=user_id,
    resource_id="document_123",
    permission="edit",
    tenant_id="tenant_001"
)

if result["result"]["check"]["allowed"]:
    print("User has permission")
else:
    print(f"Access denied: {result['result']['check']['reason']}")
```

## User Management Operations

### Available Operations

| Operation | Description | Required Fields |
|-----------|-------------|-----------------|
| `create_user` | Create a new user | email, password |
| `update_user` | Update user details | user_id, user_data |
| `delete_user` | Delete user (soft/hard) | user_id |
| `get_user` | Get user by ID | user_id |
| `list_users` | List users with pagination | - |
| `activate_user` | Activate user account | user_id |
| `deactivate_user` | Deactivate user account | user_id |
| `set_password` | Set user password hash | user_id, password_hash |
| `bulk_create` | Create multiple users | users_data |
| `bulk_update` | Update multiple users | users_data |
| `bulk_delete` | Delete multiple users | user_ids |
| `get_user_roles` | Get roles for a user | user_id |
| `get_user_permissions` | Get effective permissions | user_id |

### User Lifecycle

```python
# 1. Create user (starts as active by default)
user = user_node.execute(
    operation="create_user",
    user_data={
        "email": "new.user@example.com",
        "username": "newuser",
        "password": "InitialPass123!",
        "status": "pending"  # Optional: start as pending
    },
    tenant_id="tenant_001"
)

# 2. Activate user
activated = user_node.execute(
    operation="activate_user",
    user_id=user["result"]["user"]["user_id"],
    tenant_id="tenant_001"
)

# 3. Update user profile
updated = user_node.execute(
    operation="update_profile",
    user_id=user["result"]["user"]["user_id"],
    user_data={
        "first_name": "Jane",
        "last_name": "Smith",
        "attributes": {
            "department": "Engineering",
            "employee_id": "EMP001"
        }
    },
    tenant_id="tenant_001"
)

# 4. Deactivate user
deactivated = user_node.execute(
    operation="deactivate_user",
    user_id=user["result"]["user"]["user_id"],
    tenant_id="tenant_001"
)

# 5. Delete user (soft delete by default)
deleted = user_node.execute(
    operation="delete_user",
    user_id=user["result"]["user"]["user_id"],
    hard_delete=False,  # Set True for permanent deletion
    tenant_id="tenant_001"
)
```

### Bulk Operations

```python
# Bulk create users
bulk_result = user_node.execute(
    operation="bulk_create",
    users_data=[
        {
            "email": "user1@example.com",
            "username": "user1",
            "password": "Pass123!",
            "roles": ["viewer"]
        },
        {
            "email": "user2@example.com",
            "username": "user2",
            "password": "Pass456!",
            "roles": ["contributor"]
        }
    ],
    tenant_id="tenant_001"
)

print(f"Created {bulk_result['result']['bulk_result']['created_count']} users")
print(f"Failed {bulk_result['result']['bulk_result']['failed_count']} users")
```

## Role Management

### Role Hierarchy

Roles support inheritance through parent-child relationships:

```python
# Create base roles
viewer = role_node.execute(
    operation="create_role",
    role_data={
        "name": "viewer",
        "description": "Basic read-only access",
        "permissions": ["content:read", "profile:read"]
    },
    tenant_id="tenant_001"
)

# Create role that inherits from viewer
editor = role_node.execute(
    operation="create_role",
    role_data={
        "name": "editor",
        "description": "Can edit content",
        "permissions": ["content:write", "content:edit"],
        "parent_roles": ["viewer"]  # Inherits viewer permissions
    },
    tenant_id="tenant_001"
)

# Create admin role with multiple parents
admin = role_node.execute(
    operation="create_role",
    role_data={
        "name": "admin",
        "description": "Full administrative access",
        "permissions": ["users:manage", "roles:manage", "system:configure"],
        "parent_roles": ["editor", "moderator"]
    },
    tenant_id="tenant_001"
)
```

### User-Role Assignment

```python
# Assign role to user
assignment = role_node.execute(
    operation="assign_user",
    user_id=user_id,
    role_id="editor",
    tenant_id="tenant_001"
)

# Assign with expiration
temp_assignment = role_node.execute(
    operation="assign_user",
    user_id=user_id,
    role_id="admin",
    expires_at="2024-12-31T23:59:59Z",
    tenant_id="tenant_001"
)

# Get user's roles
user_roles = role_node.execute(
    operation="get_user_roles",
    user_id=user_id,
    tenant_id="tenant_001"
)

# Get users with a specific role
role_users = role_node.execute(
    operation="get_role_users",
    role_id="editor",
    tenant_id="tenant_001"
)
```

## Permission System

### Permission Format

Permissions follow the format `resource:action`:

- `content:read` - Read content
- `content:write` - Write content
- `users:manage` - Manage users
- `*:read` - Read any resource
- `content:*` - Any action on content
- `*:*` - Global admin permission

### Permission Checking

```python
# Simple permission check
check = perm_node.execute(
    operation="check_permission",
    user_id=user_id,
    resource_id="document_123",
    permission="edit",
    tenant_id="tenant_001"
)

# Batch permission checking
batch_check = perm_node.execute(
    operation="batch_check",
    user_id=user_id,
    checks=[
        {"resource_id": "doc_1", "permissions": ["read", "write"]},
        {"resource_id": "doc_2", "permissions": ["read", "delete"]},
        {"resource_id": "users", "permissions": ["read", "manage"]}
    ],
    tenant_id="tenant_001"
)

# Check with context (for ABAC)
contextual_check = perm_node.execute(
    operation="check_permission",
    user_id=user_id,
    resource_id="sensitive_doc",
    permission="read",
    context={
        "time_of_day": "14:30",
        "ip_address": "192.168.1.100",
        "department": "finance"
    },
    tenant_id="tenant_001"
)
```

### Caching Strategy

The permission system supports multiple caching backends:

```python
# Memory cache (default)
perm_node = PermissionCheckNode(
    database_config=db_config,
    cache_backend="memory",
    cache_ttl=300  # 5 minutes
)

# Redis cache (recommended for production)
perm_node = PermissionCheckNode(
    database_config=db_config,
    cache_backend="redis",
    cache_config={
        "host": "localhost",
        "port": 6379,
        "db": 0,
        "ttl": 600  # 10 minutes
    }
)

# No cache
perm_node = PermissionCheckNode(
    database_config=db_config,
    cache_backend="none"
)
```

## Integration Patterns

### Workflow Integration

```python
from kailash.workflow_builder import WorkflowBuilder

# Build user onboarding workflow
builder = WorkflowBuilder()

# Add nodes
builder.add_node("UserManagementNode", "create_user", database_config=db_config)
builder.add_node("RoleManagementNode", "assign_role", database_config=db_config)
builder.add_node("EmailNode", "send_welcome")

# Connect nodes
builder.add_connection("create_user", "assign_role", "result.user.user_id", "user_id")
builder.add_connection("create_user", "send_welcome", "result.user.email", "to_email")

# Build and run
workflow = builder.build()
result = runtime.execute(workflow.build(), {
    "operation": "create_user",
    "user_data": {
        "email": "newuser@example.com",
        "password": "Welcome123!",
        "first_name": "New",
        "last_name": "User"
    },
    "role_id": "viewer",
    "tenant_id": "tenant_001",
    "email_template": "welcome_new_user"
})
```

### Middleware Integration

```python
from kailash.api.middleware import create_gateway

# Create gateway with admin endpoints
app = create_gateway(
    port=8000,
    routes=[
        {
            "path": "/api/users",
            "node": "UserManagementNode",
            "config": {"database_config": db_config}
        },
        {
            "path": "/api/roles",
            "node": "RoleManagementNode",
            "config": {"database_config": db_config}
        },
        {
            "path": "/api/permissions/check",
            "node": "PermissionCheckNode",
            "config": {
                "database_config": db_config,
                "cache_backend": "redis",
                "cache_config": redis_config
            }
        }
    ]
)
```

## Best Practices

### 1. Always Use Tenant Isolation

```python
# Always specify tenant_id for multi-tenant systems
result = user_node.execute(
    operation="list_users",
    tenant_id=request.tenant_id  # From request context
)
```

### 2. Handle Errors Gracefully

```python
from kailash.sdk_exceptions import NodeValidationError, NodeExecutionError

try:
    result = user_node.execute(
        operation="create_user",
        user_data=user_data,
        tenant_id=tenant_id
    )
except NodeValidationError as e:
    # Handle validation errors (e.g., duplicate email)
    print(f"Validation error: {e}")
except NodeExecutionError as e:
    # Handle execution errors (e.g., database issues)
    print(f"Execution error: {e}")
```

### 3. Use Bulk Operations for Performance

```python
# Instead of multiple individual operations
for user_data in users_list:
    user_node.execute(operation="create_user", user_data=user_data)

# Use bulk operations
result = user_node.execute(
    operation="bulk_create",
    users_data=users_list,
    tenant_id=tenant_id
)
```

### 4. Implement Proper Password Policies

```python
import re

def validate_password(password):
    """Validate password meets security requirements."""
    if len(password) < 12:
        raise ValueError("Password must be at least 12 characters")
    if not re.search(r"[A-Z]", password):
        raise ValueError("Password must contain uppercase letter")
    if not re.search(r"[a-z]", password):
        raise ValueError("Password must contain lowercase letter")
    if not re.search(r"\d", password):
        raise ValueError("Password must contain number")
    if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", password):
        raise ValueError("Password must contain special character")
    return True

# Validate before creating user
validate_password(user_data["password"])
```

### 5. Use Caching Wisely

```python
# Cache permission checks for performance
perm_node = PermissionCheckNode(
    database_config=db_config,
    cache_backend="redis",
    cache_config={"host": "localhost", "port": 6379, "ttl": 300}
)

# Clear cache when permissions change
perm_node.execute(
    operation="clear_cache",
    user_id=user_id,  # Clear specific user
    tenant_id=tenant_id
)
```

## Security Considerations

1. **Password Storage**: Passwords are automatically hashed using secure algorithms
2. **Multi-tenant Isolation**: All operations are isolated by tenant_id
3. **Audit Logging**: All admin operations can be audited
4. **Permission Caching**: Cache invalidation on permission changes
5. **Role Hierarchy Validation**: Prevents circular dependencies

## Troubleshooting

### Common Issues

1. **User Not Found**
   ```python
   # Ensure user exists and tenant_id matches
   user = user_node.execute(
       operation="get_user",
       user_id=user_id,
       tenant_id=correct_tenant_id
   )
   ```

2. **Permission Denied**
   ```python
   # Check effective permissions
   perms = role_node.execute(
       operation="get_effective_permissions",
       role_id=user_role,
       tenant_id=tenant_id
   )
   ```

3. **Database Schema Issues**
   ```python
   # Initialize schema before first use
   from kailash.nodes.admin import AdminSchemaManager

   schema_manager = AdminSchemaManager(database_config=db_config)
   schema_manager.initialize_schema()
   ```

## Performance Tips

1. **Use Connection Pooling**: Configure your database connection with pooling
2. **Enable Caching**: Use Redis for production permission caching
3. **Batch Operations**: Use bulk operations for multiple users
4. **Index Optimization**: Ensure proper database indexes on user_id, tenant_id
5. **Async Operations**: Use async runtime for concurrent operations

## Production Testing Framework

### Integration Tests with Docker

The admin nodes include comprehensive integration tests using real Docker infrastructure:

```python
from tests.integration.test_admin_nodes_production_ready import TestAdminNodesProductionIntegration

# Real services used:
# - PostgreSQL on port 5433 for data persistence
# - Redis on port 6380 for permission caching
# - Ollama on port 11435 for AI-generated test data

# Run production-ready tests
pytest tests/integration/test_admin_nodes_production_ready.py -v
```

### AI-Generated Test Data

Tests use Ollama to generate realistic enterprise data:

```python
# Generate realistic user profiles
users_data = await self.generate_realistic_user_data(llm_agent, count=20)

# Generate enterprise scenarios
scenario = llm_agent.execute(
    prompt="Generate realistic enterprise onboarding scenario...",
    model="llama3.2:latest"
)
```

### Performance Validation

- **Cache Performance**: Redis caching provides 50%+ speed improvement
- **Bulk Operations**: 20 users created in <10 seconds
- **Concurrent Access**: Multi-tenant isolation verified
- **Load Testing**: Permission checks under concurrent load

### Enterprise Compliance

- **GDPR Compliance**: Data export and audit trails
- **Multi-tenant Isolation**: Complete tenant separation
- **Role Hierarchy**: Complex RBAC with inheritance
- **Audit Logging**: Full permission check audit trails

### Running Production Tests

```bash
# Ensure Docker services are running
docker-compose up -d

# Run all admin integration tests
pytest tests/integration/test_admin_nodes_production_ready.py -v

# Run specific enterprise scenarios
pytest tests/integration/test_admin_nodes_production_ready.py::TestAdminNodesProductionIntegration::test_real_world_enterprise_scenario -v

# Run performance tests
pytest tests/integration/test_admin_nodes_production_ready.py::TestAdminNodesProductionIntegration::test_performance_under_load -v
```

## Next Steps

- Run production integration tests: `pytest tests/integration/test_admin_nodes_production_ready.py -v`
- Explore the [Permission System Architecture](../architecture/permission-system.md)
- Learn about [Multi-tenant Design](../architecture/multi-tenant.md)
- See [Admin API Examples](../examples/admin-api/)

# Admin Nodes Quick Reference

## Node Setup

```python
from kailash.nodes.admin import UserManagementNode, RoleManagementNode, PermissionCheckNode

db_config = {
    "connection_string": "postgresql://user:pass@localhost/db",
    "database_type": "postgresql"
}

user_node = UserManagementNode(database_config=db_config)
role_node = RoleManagementNode(database_config=db_config)
perm_node = PermissionCheckNode(
    database_config=db_config,
    cache_backend="redis",
    cache_config={"host": "localhost", "port": 6379}
)
```

## User Operations

```python
# Create user
user = user_node.run(
    operation="create_user",
    user_data={
        "email": "user@example.com",
        "username": "username",
        "password": "SecurePass123!",
        "first_name": "John",
        "last_name": "Doe",
        "roles": ["viewer"]
    },
    tenant_id="tenant_001"
)

# Update user
updated = user_node.run(
    operation="update_user",
    user_id="user_123",
    user_data={"roles": ["editor", "viewer"]},
    tenant_id="tenant_001"
)

# List users
users = user_node.run(
    operation="list_users",
    limit=50,
    offset=0,
    tenant_id="tenant_001"
)

# Delete user
deleted = user_node.run(
    operation="delete_user",
    user_id="user_123",
    hard_delete=False,
    tenant_id="tenant_001"
)

# Bulk operations
bulk_result = user_node.run(
    operation="bulk_create",
    users_data=[{...}, {...}],
    tenant_id="tenant_001"
)
```

## Role Operations

```python
# Create role
role = role_node.run(
    operation="create_role",
    role_data={
        "name": "editor",
        "description": "Content editor",
        "permissions": ["content:read", "content:write"],
        "parent_roles": ["viewer"]
    },
    tenant_id="tenant_001"
)

# Assign role
assignment = role_node.run(
    operation="assign_user",
    user_id="user_123",
    role_id="editor",
    tenant_id="tenant_001"
)

# Get user roles
roles = role_node.run(
    operation="get_user_roles",
    user_id="user_123",
    tenant_id="tenant_001"
)

# Add permission
updated_role = role_node.run(
    operation="add_permission",
    role_id="editor",
    permission="content:publish",
    tenant_id="tenant_001"
)
```

## Permission Checks

```python
# Single check
check = perm_node.run(
    operation="check_permission",
    user_id="user_123",
    resource_id="document_456",
    permission="edit",
    tenant_id="tenant_001"
)

# Batch check
batch = perm_node.run(
    operation="batch_check",
    user_id="user_123",
    checks=[
        {"resource_id": "doc1", "permissions": ["read", "write"]},
        {"resource_id": "doc2", "permissions": ["delete"]}
    ],
    tenant_id="tenant_001"
)

# Clear cache
perm_node.run(
    operation="clear_cache",
    user_id="user_123",
    tenant_id="tenant_001"
)
```

## Permission Format

- `resource:action` - Specific permission
- `*:action` - Action on any resource
- `resource:*` - Any action on resource
- `*:*` - Global admin

## Common Patterns

### User Onboarding
```python
# 1. Create user
# 2. Assign default role
# 3. Send welcome email
# 4. Log audit event
```

### Role Hierarchy
```python
viewer → contributor → editor → admin
```

### Error Handling
```python
try:
    result = node.run(...)
except NodeValidationError:
    # Invalid input
except NodeExecutionError:
    # Runtime error
```

## Required Fields

| Operation | Required Fields |
|-----------|----------------|
| create_user | email, password |
| update_user | user_id, user_data |
| create_role | name, description |
| check_permission | user_id, resource_id, permission |

## Production Testing

### Integration Tests with Docker

```bash
# Run production-ready integration tests
pytest tests/integration/test_admin_nodes_production_ready.py -v

# Run complete E2E workflow tests
pytest tests/e2e/test_admin_nodes_complete_workflow.py -v
```

### AI-Generated Test Data

```python
# Generate realistic enterprise users with Ollama
from kailash.nodes.ai import LLMAgentNode

llm_agent = LLMAgentNode(agent_config={
    "provider": "ollama",
    "model": "llama3.2:latest",
    "base_url": "http://localhost:11435"
})

# Generate realistic user profiles
users_data = await generate_realistic_user_data(llm_agent, count=20)
```

### Docker Services Required

- **PostgreSQL**: Port 5433 (data persistence)
- **Redis**: Port 6380 (permission caching)
- **Ollama**: Port 11435 (AI test data generation)

### Performance Benchmarks

- **Cache Performance**: 50%+ speed improvement with Redis
- **Bulk Operations**: 20 users in <10 seconds
- **Permission Checks**: <100ms with cache hits
- **Multi-tenant**: Complete isolation verified

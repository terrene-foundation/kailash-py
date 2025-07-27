# Admin Nodes Quick Reference

## Node Setup

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

# Create workflow with admin nodes
workflow = WorkflowBuilder()
workflow.add_node("UserManagementNode", "user_mgmt", {
    "database_config": {
        "connection_string": "postgresql://user:pass@localhost/db",
        "database_type": "postgresql"
    }
})
workflow.add_node("RoleManagementNode", "role_mgmt", {
    "database_config": {
        "connection_string": "postgresql://user:pass@localhost/db",
        "database_type": "postgresql"
    }
})
workflow.add_node("PermissionCheckNode", "perm_check", {
    "database_config": {
        "connection_string": "postgresql://user:pass@localhost/db",
        "database_type": "postgresql"
    },
    "cache_backend": "redis",
    "cache_config": {"host": "localhost", "port": 6379}
})

runtime = LocalRuntime()
```

## User Operations

```python
# Create user
user, run_id = runtime.execute(workflow.build(), parameters={
    "user_mgmt": {
        "operation": "create_user",
        "user_data": {
            "email": "user@example.com",
            "username": "username",
            "password": "SecurePass123!",
            "first_name": "John",
            "last_name": "Doe",
            "roles": ["viewer"]
        },
        "tenant_id": "tenant_001"
    }
})

# Update user
updated, run_id = runtime.execute(workflow.build(), parameters={
    "user_mgmt": {
        "operation": "update_user",
        "user_id": "user_123",
        "user_data": {"roles": ["editor", "viewer"]},
        "tenant_id": "tenant_001"
    }
})

# List users
users, run_id = runtime.execute(workflow.build(), parameters={
    "user_mgmt": {
        "operation": "list_users",
        "limit": 50,
        "offset": 0,
        "tenant_id": "tenant_001"
    }
})

# Delete user
deleted, run_id = runtime.execute(workflow.build(), parameters={
    "user_mgmt": {
        "operation": "delete_user",
        "user_id": "user_123",
        "hard_delete": False,
        "tenant_id": "tenant_001"
    }
})

# Bulk operations
bulk_result, run_id = runtime.execute(workflow.build(), parameters={
    "user_mgmt": {
        "operation": "bulk_create",
        "users_data": [{...}, {...}],
        "tenant_id": "tenant_001"
    }
})
```

## Role Operations

```python
# Create role
role, run_id = runtime.execute(workflow.build(), parameters={
    "role_mgmt": {
        "operation": "create_role",
        "role_data": {
            "name": "editor",
            "description": "Content editor",
            "permissions": ["content:read", "content:write"],
            "parent_roles": ["viewer"]
        },
        "tenant_id": "tenant_001"
    }
})

# Assign role
assignment, run_id = runtime.execute(workflow.build(), parameters={
    "role_mgmt": {
        "operation": "assign_user",
        "user_id": "user_123",
        "role_id": "editor",
        "tenant_id": "tenant_001"
    }
})

# Get user roles
roles, run_id = runtime.execute(workflow.build(), parameters={
    "role_mgmt": {
        "operation": "get_user_roles",
        "user_id": "user_123",
        "tenant_id": "tenant_001"
    }
})

# Add permission
updated_role, run_id = runtime.execute(workflow.build(), parameters={
    "role_mgmt": {
        "operation": "add_permission",
        "role_id": "editor",
        "permission": "content:publish",
        "tenant_id": "tenant_001"
    }
})
```

## Permission Checks

```python
# Single check
check, run_id = runtime.execute(workflow.build(), parameters={
    "perm_check": {
        "operation": "check_permission",
        "user_id": "user_123",
        "resource_id": "document_456",
        "permission": "edit",
        "tenant_id": "tenant_001"
    }
})

# Batch check
batch, run_id = runtime.execute(workflow.build(), parameters={
    "perm_check": {
        "operation": "batch_check",
        "user_id": "user_123",
        "checks": [
            {"resource_id": "doc1", "permissions": ["read", "write"]},
            {"resource_id": "doc2", "permissions": ["delete"]}
        ],
        "tenant_id": "tenant_001"
    }
})

# Clear cache
runtime.execute(workflow.build(), parameters={
    "perm_check": {
        "operation": "clear_cache",
        "user_id": "user_123",
        "tenant_id": "tenant_001"
    }
})
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
    result, run_id = runtime.execute(workflow.build(), parameters={...})
except Exception as e:
    # Handle error
    print(f"Error: {e}")
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
workflow = WorkflowBuilder()
workflow.add_node("LLMAgentNode", "llm_agent", {
    "agent_config": {
        "provider": "ollama",
        "model": "llama3.2:latest",
        "base_url": "http://localhost:11435"
    }
})

runtime = LocalRuntime()

# Generate realistic user profiles using workflow
# Implementation would use the LLM to generate user data
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

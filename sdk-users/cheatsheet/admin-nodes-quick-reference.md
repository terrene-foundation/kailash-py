# Admin Nodes - Quick Reference

**Status**: ✅ Production Ready | ✅ Complete Implementation | ✅ Enterprise Grade

## Quick Setup

```python
from kailash.nodes.admin.role_management import RoleManagementNode
from kailash.nodes.admin.permission_check import PermissionCheckNode

# Initialize nodes
role_node = RoleManagementNode()
permission_node = PermissionCheckNode()
```

## RoleManagementNode - 15 Operations

### Role CRUD

```python
# Create role
role_node.run(
    operation="create_role",
    role_data={
        "name": "Data Analyst",
        "description": "Can read and analyze data",
        "permissions": ["data:read", "reports:view"],
        "parent_roles": ["base_user"],  # Optional hierarchy
        "attributes": {"department": "analytics"}
    },
    tenant_id="company_a"
)

# Update role
role_node.run(
    operation="update_role",
    role_id="data_analyst",
    role_data={"permissions": ["data:read", "data:write", "reports:view"]}
)

# Delete role
role_node.run(
    operation="delete_role",
    role_id="old_role",
    force=True  # Override dependency checks
)

# Get role details
role_node.run(
    operation="get_role",
    role_id="data_analyst",
    include_inherited=True,
    include_users=True
)

# List roles with pagination
role_node.run(
    operation="list_roles",
    filters={"role_type": "custom", "is_active": True},
    search_query="analyst",
    limit=20,
    offset=0
)
```

### User Assignment

```python
# Assign single user
role_node.run(
    operation="assign_user",
    user_id="alice",
    role_id="data_analyst"
)

# Bulk assign multiple users
role_node.run(
    operation="bulk_assign",
    role_id="data_analyst",
    user_ids=["alice", "bob", "charlie"]
)

# Unassign user
role_node.run(
    operation="unassign_user",
    user_id="alice",
    role_id="data_analyst"
)

# Bulk unassign
role_node.run(
    operation="bulk_unassign",
    role_id="data_analyst",
    user_ids=["alice", "bob"]
)
```

### Permission Management

```python
# Add permission to role
role_node.run(
    operation="add_permission",
    role_id="data_analyst",
    permission="data:export"
)

# Remove permission from role
role_node.run(
    operation="remove_permission",
    role_id="data_analyst",
    permission="data:delete"
)

# Get effective permissions (with inheritance)
role_node.run(
    operation="get_effective_permissions",
    role_id="senior_analyst",
    include_inherited=True
)
```

### User & Role Queries

```python
# Get all roles for a user
role_node.run(
    operation="get_user_roles",
    user_id="alice",
    include_inherited=True
)

# Get all users for a role
role_node.run(
    operation="get_role_users",
    role_id="data_analyst",
    include_user_details=True
)
```

### Hierarchy Management

```python
# Validate role hierarchy
role_node.run(
    operation="validate_hierarchy",
    fix_issues=True  # Auto-fix detected issues
)
```

## PermissionCheckNode - 10 Operations

### Basic Permission Checking

```python
# Single permission check
permission_node.run(
    operation="check_permission",
    user_id="alice",
    resource_id="financial_data",
    permission="read",
    context={"location": "office", "time": "business_hours"},
    cache_level="user",
    explain=True
)

# Batch check multiple permissions
permission_node.run(
    operation="batch_check",
    user_id="alice",
    resource_ids=["data1", "data2", "data3"],
    permissions=["read", "write"]
)

# Bulk user check (multiple users, one permission)
permission_node.run(
    operation="bulk_user_check",
    user_ids=["alice", "bob", "charlie"],
    resource_id="workflow_execute",
    permission="execute"
)
```

### Specialized Checks

```python
# Node access check
permission_node.run(
    operation="check_node_access",
    user_id="alice",
    resource_id="PythonCodeNode",
    permission="execute"
)

# Workflow access check
permission_node.run(
    operation="check_workflow_access",
    user_id="alice",
    resource_id="data_processing_workflow",
    permission="deploy"
)

# Hierarchical resource check
permission_node.run(
    operation="check_hierarchical",
    user_id="alice",
    resource_id="company/analytics/team/project/workflow",
    permission="execute",
    check_inheritance=True
)
```

### User Permissions & Debugging

```python
# Get all user permissions
permission_node.run(
    operation="get_user_permissions",
    user_id="alice",
    permission_type="all",  # all, direct, inherited
    include_inherited=True
)

# Detailed permission explanation
permission_node.run(
    operation="explain_permission",
    user_id="alice",
    resource_id="sensitive_data",
    permission="read",
    include_hierarchy=True
)

# Validate ABAC conditions
permission_node.run(
    operation="validate_conditions",
    conditions=[
        {"attribute": "department", "operator": "eq", "value": "analytics"},
        {"attribute": "clearance", "operator": "ge", "value": "confidential"}
    ],
    context={"department": "analytics", "clearance": "secret"},
    test_evaluation=True
)
```

### Cache Management

```python
# Clear permission cache
permission_node.run(operation="clear_cache")
```

## Common Patterns

### Complete RBAC Setup

```python
# 1. Create role hierarchy
role_node.run(
    operation="create_role",
    role_data={
        "name": "Base Employee",
        "permissions": ["profile:read", "directory:view"]
    }
)

role_node.run(
    operation="create_role",
    role_data={
        "name": "Data Analyst",
        "parent_roles": ["base_employee"],
        "permissions": ["data:read", "reports:view"]
    }
)

# 2. Assign users
role_node.run(
    operation="bulk_assign",
    role_id="data_analyst",
    user_ids=["alice", "bob", "charlie"]
)

# 3. Check access
permission_node.run(
    operation="check_permission",
    user_id="alice",
    resource_id="data",
    permission="read"
)
```

### Access Control Gate

```python
def check_access(user_id, resource, permission, context=None):
    result = permission_node.run(
        operation="check_permission",
        user_id=user_id,
        resource_id=resource,
        permission=permission,
        context=context or {},
        cache_level="user"
    )
    return result["result"]["check"]["allowed"]

# Usage
if not check_access("user123", "sensitive_data", "read"):
    raise PermissionError("Access denied")
```

### Performance Monitoring

```python
# Check with timing
result = permission_node.run(
    operation="check_permission",
    user_id="alice",
    resource_id="test",
    permission="read",
    include_timing=True
)

check = result["result"]["check"]
print(f"Evaluation time: {check['evaluation_time_ms']}ms")
print(f"Cache hit: {check.get('cache_hit', False)}")
```

## Error Handling

```python
from kailash.sdk_exceptions import NodeExecutionError, NodeValidationError

try:
    result = role_node.run(
        operation="create_role",
        role_data={"name": "Invalid Role"}  # Missing description
    )
except NodeExecutionError as e:
    if "Missing required field" in str(e):
        print("Validation error: Missing required fields")
    else:
        print(f"Execution error: {e}")
```

## Cache Levels

- `none`: No caching
- `user`: Cache per user (default)
- `role`: Cache per role
- `permission`: Cache per permission
- `full`: Maximum caching

## Database Configuration

```python
db_config = {
    "database_type": "postgresql",
    "host": "localhost",
    "port": 5432,
    "database": "kailash_admin",
    "user": "admin",
    "password": "password"
}

role_node = RoleManagementNode(database_config=db_config)
permission_node = PermissionCheckNode(database_config=db_config)
```

## Production Tips

### Security
- Use principle of least privilege
- Regular access reviews with `get_role_users`
- Validate hierarchy with `validate_hierarchy`
- Monitor with `explain_permission`

### Performance
- Use appropriate cache levels
- Batch operations for bulk changes
- Monitor evaluation times
- Clear cache after role changes

### Multi-tenancy
- Always specify `tenant_id`
- Roles are isolated per tenant
- Users can have different roles per tenant

---

**Ready for Production**: Enterprise-grade RBAC with complete audit trails, multi-tenant isolation, and high-performance caching.

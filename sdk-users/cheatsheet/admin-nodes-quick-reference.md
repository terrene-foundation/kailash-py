# Admin Nodes - Quick Reference

**Status**: ✅ Production Ready | ✅ Complete Implementation | ✅ Enterprise Grade

## Quick Setup

```python
from kailash.nodes.admin import RoleManagementNode, PermissionCheckNode, UserManagementNode

# Initialize nodes with operation and config
role_node = RoleManagementNode(
    operation="create_role",
    tenant_id="your_tenant",
    database_config={
        "connection_string": "postgresql://user:pass@localhost:5432/db",
        "database_type": "postgresql"
    }
)
```

## RoleManagementNode - 15 Operations

### Role CRUD

```python
# Create role
result = role_node.execute(  # Use .execute() not .run()
    role_data={
        "name": "Data Analyst",  # ID will be "data_analyst"
        "description": "Can read and analyze data",
        "permissions": ["data:read", "reports:view"],
        "parent_roles": ["base_user"],  # Optional hierarchy
        "attributes": {"department": "analytics"},
        "role_type": "custom"  # "system" or "custom"
    },
    tenant_id="company_a"
)

# Role ID is generated from name
role_id = result["result"]["role"]["role_id"]  # "data_analyst"

# Update role
role_node.execute(
    operation="update_role",
    role_id="data_analyst",
    role_data={"permissions": ["data:read", "data:write", "reports:view"]}
)

# Delete role
role_node.execute(
    operation="delete_role",
    role_id="old_role",
    force=True  # Override dependency checks
)

# Get role details
role_node.execute(
    operation="get_role",
    role_id="data_analyst",
    include_inherited=True,
    include_users=True
)

# List roles with pagination
role_node.execute(
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
role_node.execute(
    operation="assign_user",
    user_id="alice",
    role_id="data_analyst"
)

# Bulk assign multiple users
role_node.execute(
    operation="bulk_assign",
    role_id="data_analyst",
    user_ids=["alice", "bob", "charlie"]
)

# Unassign user
role_node.execute(
    operation="unassign_user",
    user_id="alice",
    role_id="data_analyst"
)

# Bulk unassign
role_node.execute(
    operation="bulk_unassign",
    role_id="data_analyst",
    user_ids=["alice", "bob"]
)
```

### Permission Management

```python
# Add permission to role
role_node.execute(
    operation="add_permission",
    role_id="data_analyst",
    permission="data:export"
)

# Remove permission from role
role_node.execute(
    operation="remove_permission",
    role_id="data_analyst",
    permission="data:delete"
)

# Get effective permissions (with inheritance)
role_node.execute(
    operation="get_effective_permissions",
    role_id="senior_analyst",
    include_inherited=True
)
```

### User & Role Queries

```python
# Get all roles for a user
role_node.execute(
    operation="get_user_roles",
    user_id="alice",
    include_inherited=True
)

# Get all users for a role
role_node.execute(
    operation="get_role_users",
    role_id="data_analyst",
    include_user_details=True
)
```

### Hierarchy Management

```python
# Validate role hierarchy
role_node.execute(
    operation="validate_hierarchy",
    fix_issues=True  # Auto-fix detected issues
)
```

## PermissionCheckNode - 10 Operations

### Basic Permission Checking

```python
# Single permission check
result = permission_node.execute(
    operation="check_permission",
    user_id="alice",
    resource_id="financial_data",
    permission="read",  # Can be "read" or "resource:read" format
    context={"location": "office", "time": "business_hours"},
    cache_level="user",
    explain=True
)

# IMPORTANT: Permission result has nested structure
if result.get("result", {}).get("check", {}).get("allowed", False):
    print("Access granted")
else:
    print("Access denied")

# Batch check multiple permissions
permission_node.execute(
    operation="batch_check",
    user_id="alice",
    resource_ids=["data1", "data2", "data3"],
    permissions=["read", "write"]
)

# Bulk user check (multiple users, one permission)
permission_node.execute(
    operation="bulk_user_check",
    user_ids=["alice", "bob", "charlie"],
    resource_id="workflow_execute",
    permission="execute"
)
```

### Specialized Checks

```python
# Node access check
permission_node.execute(
    operation="check_node_access",
    user_id="alice",
    resource_id="PythonCodeNode",
    permission="execute"
)

# Workflow access check
permission_node.execute(
    operation="check_workflow_access",
    user_id="alice",
    resource_id="data_processing_workflow",
    permission="deploy"
)

# Hierarchical resource check
permission_node.execute(
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
permission_node.execute(
    operation="get_user_permissions",
    user_id="alice",
    permission_type="all",  # all, direct, inherited
    include_inherited=True
)

# Detailed permission explanation
permission_node.execute(
    operation="explain_permission",
    user_id="alice",
    resource_id="sensitive_data",
    permission="read",
    include_hierarchy=True
)

# Validate ABAC conditions
permission_node.execute(
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
permission_node.execute(operation="clear_cache")
```

## Common Patterns

### Complete RBAC Setup

```python
# 1. Create role hierarchy
role_node.execute(
    operation="create_role",
    role_data={
        "name": "Base Employee",
        "permissions": ["profile:read", "directory:view"]
    }
)

role_node.execute(
    operation="create_role",
    role_data={
        "name": "Data Analyst",
        "parent_roles": ["base_employee"],
        "permissions": ["data:read", "reports:view"]
    }
)

# 2. Assign users
role_node.execute(
    operation="bulk_assign",
    role_id="data_analyst",
    user_ids=["alice", "bob", "charlie"]
)

# 3. Check access
permission_node.execute(
    operation="check_permission",
    user_id="alice",
    resource_id="data",
    permission="read"
)
```

### Access Control Gate

```python
def check_access(user_id, resource, permission, context=None, tenant_id="default"):
    # Initialize node for the operation
    permission_node = PermissionCheckNode(
        operation="check_permission",
        tenant_id=tenant_id,
        database_config=db_config
    )

    result = permission_node.execute(
        user_id=user_id,
        resource_id=resource,
        permission=permission,
        context=context or {},
        cache_level="user",
        tenant_id=tenant_id
    )

    # Note the nested structure: result.check.allowed
    return result.get("result", {}).get("check", {}).get("allowed", False)

# Usage
if not check_access("user123", "sensitive_data", "read"):
    raise PermissionError("Access denied")
```

### Performance Monitoring

```python
# Check with timing
result = permission_node.execute(
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
    result = role_node.execute(
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

## Common Gotchas (from E2E Testing)

### Permission Check Result Structure
```python
# ❌ WRONG:
if result["result"]["allowed"]:

# ✅ CORRECT:
if result["result"]["check"]["allowed"]:
```

### Role ID Generation
```python
# Role names are converted to IDs automatically
"Senior Engineer" -> "senior_engineer"
"VP of Sales" -> "vp_of_sales"
```

### Direct Node Execution vs Workflows
```python
# For database operations, prefer direct execution
# to avoid transaction isolation issues
role_node = RoleManagementNode(...)
role_node.execute(...)  # Direct execution

# NOT through workflows for simple operations
```

### User Status for Permissions
```python
# Always set status when creating users
user_data = {
    "email": "user@example.com",
    "status": "active"  # Required for permission checks
}
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

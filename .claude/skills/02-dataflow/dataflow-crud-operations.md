---
name: dataflow-crud-operations
description: "Use 9 auto-generated DataFlow nodes for CRUD operations. Use when DataFlow CRUD, generated nodes, UserCreateNode, UserReadNode, create read update delete, basic operations, or single record operations."
---

# DataFlow CRUD Operations

Use the 9 automatically generated workflow nodes for Create, Read, Update, Delete, and List operations on DataFlow models.

> **Skill Metadata**
> Category: `dataflow`
> Priority: `HIGH`
> SDK Version: `0.9.25+ / DataFlow 0.6.0`
> Related Skills: [`dataflow-models`](#), [`dataflow-queries`](#), [`dataflow-bulk-operations`](#), [`workflow-quickstart`](#)
> Related Subagents: `dataflow-specialist` (complex operations, troubleshooting)

## Quick Reference

- **9 Generated Nodes**: Create, Read, Update, Delete, List, BulkCreate, BulkUpdate, BulkDelete, BulkUpsert
- **Naming Pattern**: `{Model}{Operation}Node` (e.g., `UserCreateNode`)
- **Performance**: <1ms for single operations
- **String IDs**: Fully supported (v0.4.0+)

## Core Pattern

```python
from dataflow import DataFlow
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

db = DataFlow()

@db.model
class User:
    name: str
    email: str
    active: bool = True

# Automatically generates 9 nodes:
# UserCreateNode, UserReadNode, UserUpdateNode, UserDeleteNode, UserListNode,
# UserBulkCreateNode, UserBulkUpdateNode, UserBulkDeleteNode, UserBulkUpsertNode

workflow = WorkflowBuilder()

# CREATE - Single record
workflow.add_node("UserCreateNode", "create_user", {
    "name": "Alice",
    "email": "alice@example.com"
})

# READ - Single record by ID
workflow.add_node("UserReadNode", "read_user", {
    "id": 1
})

# UPDATE - Single record
workflow.add_node("UserUpdateNode", "update_user", {
    "id": 1,
    "updates": {"active": False}
})

# DELETE - Single record
workflow.add_node("UserDeleteNode", "delete_user", {
    "id": 1
})

# LIST - Query with filters
workflow.add_node("UserListNode", "list_users", {
    "filter": {"active": True},
    "limit": 10
})

runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
```

## Common Use Cases

- **User Registration**: Create user account with validation
- **Profile Lookup**: Read user by ID or email
- **Account Updates**: Update user profile fields
- **Account Deletion**: Soft or hard delete users
- **User Search**: List users with filters and pagination

## Generated Nodes Reference

### Basic CRUD Nodes (5)

| Node | Purpose | Performance | Parameters |
|------|---------|-------------|------------|
| `{Model}CreateNode` | Insert single record | <1ms | All model fields |
| `{Model}ReadNode` | Select by ID | <1ms | `id` or `conditions` |
| `{Model}UpdateNode` | Update single record | <1ms | `id`, `updates` |
| `{Model}DeleteNode` | Delete single record | <1ms | `id`, `soft_delete` |
| `{Model}ListNode` | Query with filters | <10ms | `filter`, `limit`, `order_by` |

### Bulk Operation Nodes (4)

| Node | Purpose | Performance | Parameters |
|------|---------|-------------|------------|
| `{Model}BulkCreateNode` | Insert multiple records | 1000+/sec | `data`, `batch_size` |
| `{Model}BulkUpdateNode` | Update multiple records | 5000+/sec | `filter`, `updates` |
| `{Model}BulkDeleteNode` | Delete multiple records | 10000+/sec | `filter`, `soft_delete` |
| `{Model}BulkUpsertNode` | Insert or update | 3000+/sec | `data`, `unique_fields` |

## Key Parameters / Options

### CreateNode Parameters

```python
workflow.add_node("UserCreateNode", "create", {
    # Required: Model fields
    "name": "John Doe",
    "email": "john@example.com",

    # Optional: Control behavior
    "return_id": True,  # Return created ID (default: True)
    "validate": True    # Validate before insert (default: True)
})
```

### ReadNode Parameters

```python
# Option 1: By ID (simple)
workflow.add_node("UserReadNode", "read", {
    "id": 123
})

# Option 2: By conditions (flexible)
workflow.add_node("UserReadNode", "read", {
    "conditions": {"email": "john@example.com"},
    "raise_on_not_found": True  # Error if not found
})

# Option 3: String IDs (v0.4.0+)
workflow.add_node("SessionReadNode", "read_session", {
    "id": "session-uuid-string"  # String IDs preserved
})
```

### UpdateNode Parameters

```python
workflow.add_node("UserUpdateNode", "update", {
    # Target record
    "id": 123,
    # OR
    "conditions": {"email": "john@example.com"},

    # Updates to apply
    "updates": {
        "active": False,
        "updated_at": datetime.now()
    },

    # Options
    "return_updated": True,  # Return updated record
    "validate": True         # Validate before update
})
```

### DeleteNode Parameters

```python
workflow.add_node("UserDeleteNode", "delete", {
    # Target record
    "id": 123,

    # Soft delete (preserve data)
    "soft_delete": True,  # Sets deleted_at, doesn't remove

    # Hard delete (permanent)
    "hard_delete": False  # Permanently removes
})
```

### ListNode Parameters

```python
workflow.add_node("UserListNode", "list", {
    # Filters (MongoDB-style)
    "filter": {
        "active": True,
        "age": {"$gt": 18}
    },

    # Sorting
    "order_by": ["-created_at"],  # Descending by created_at

    # Pagination
    "limit": 10,
    "offset": 0,

    # Field selection
    "fields": ["id", "name", "email"],  # Only return these fields

    # Count only
    "count_only": False  # Set True to just count matches
})
```

## Common Mistakes

### Mistake 1: Missing .build() Call

```python
# Wrong - missing .build()
workflow.add_node("UserCreateNode", "create", {...})
results, run_id = runtime.execute(workflow)  # ERROR
```

**Fix: Always Call .build()**

```python
# Correct
workflow.add_node("UserCreateNode", "create", {...})
results, run_id = runtime.execute(workflow.build())
```

### Mistake 2: Using Template Syntax for Parameters

```python
# Wrong - ${} conflicts with PostgreSQL
workflow.add_node("OrderCreateNode", "create", {
    "customer_id": "${create_customer.id}"  # FAILS
})
```

**Fix: Use Workflow Connections**

```python
# Correct - use connections for dynamic values
workflow.add_node("OrderCreateNode", "create", {
    "total": 100.0
})
workflow.add_connection("create_customer", "id", "create", "customer_id")
```

### Mistake 3: Wrong Result Access Pattern

```python
# Wrong - incorrect result structure
user_id = results["create_user"]["id"]  # FAILS
```

**Fix: Access Through result Key**

```python
# Correct - results have 'result' wrapper
user_data = results["create_user"]["result"]
user_id = user_data["id"]
```

## Related Patterns

- **For model definition**: See [`dataflow-models`](#)
- **For query filters**: See [`dataflow-queries`](#)
- **For bulk operations**: See [`dataflow-bulk-operations`](#)
- **For result access**: See [`dataflow-result-access`](#)
- **For Nexus integration**: See [`dataflow-nexus-integration`](#)

## When to Escalate to Subagent

Use `dataflow-specialist` subagent when:
- Designing complex multi-step CRUD workflows
- Implementing custom validation logic
- Troubleshooting node execution errors
- Optimizing query performance
- Setting up advanced filtering patterns
- Working with relationships between models

## Documentation References

### Primary Sources
- **README**: [`sdk-users/apps/dataflow/README.md`](../../../../sdk-users/apps/dataflow/README.md#L304-L381)
- **DataFlow CLAUDE**: [`sdk-users/apps/dataflow/CLAUDE.md`](../../../../sdk-users/apps/dataflow/CLAUDE.md#L83-L234)
- **Node API**: [`sdk-users/apps/dataflow/docs/api/nodes.md`](../../../../sdk-users/apps/dataflow/docs/api/nodes.md)

### Related Documentation
- **Query Patterns**: [`sdk-users/apps/dataflow/docs/development/query-patterns.md`](../../../../sdk-users/apps/dataflow/docs/development/query-patterns.md)
- **CRUD Guide**: [`sdk-users/apps/dataflow/docs/development/crud.md`](../../../../sdk-users/apps/dataflow/docs/development/crud.md)
- **Workflow Nodes**: [`sdk-users/apps/dataflow/docs/workflows/nodes.md`](../../../../sdk-users/apps/dataflow/docs/workflows/nodes.md)

### Specialist Reference
- **DataFlow Specialist**: [`.claude/skills/dataflow-specialist.md`](../../dataflow-specialist.md#L211-L224)

## Examples

### Example 1: Complete User CRUD Workflow

```python
from dataflow import DataFlow
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

db = DataFlow()

@db.model
class User:
    name: str
    email: str
    active: bool = True

workflow = WorkflowBuilder()

# Create user
workflow.add_node("UserCreateNode", "create", {
    "name": "Alice",
    "email": "alice@example.com"
})

# Read created user
workflow.add_node("UserReadNode", "read", {})
workflow.add_connection("create", "id", "read", "id")

# Update user
workflow.add_node("UserUpdateNode", "update", {
    "updates": {"active": False}
})
workflow.add_connection("read", "id", "update", "id")

# List all inactive users
workflow.add_node("UserListNode", "list_inactive", {
    "filter": {"active": False}
})

runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())

# Access results
created_user = results["create"]["result"]
print(f"Created user: {created_user['name']}")

inactive_users = results["list_inactive"]["result"]
print(f"Found {len(inactive_users)} inactive users")
```

### Example 2: String ID Operations (v0.4.0+)

```python
@db.model
class SsoSession:
    id: str
    user_id: str
    state: str = 'active'

workflow = WorkflowBuilder()

# Create with string ID
session_id = "session-80706348-0456-468b-8851-329a756a3a93"
workflow.add_node("SsoSessionCreateNode", "create_session", {
    "id": session_id,  # String ID preserved
    "user_id": "user-123",
    "state": "active"
})

# Read by string ID
workflow.add_node("SsoSessionReadNode", "read_session", {
    "id": session_id  # No conversion needed
})

# Update by string ID
workflow.add_node("SsoSessionUpdateNode", "update_session", {
    "id": session_id,
    "updates": {"state": "expired"}
})

runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
```

### Example 3: Soft Delete Pattern

```python
@db.model
class Customer:
    name: str
    email: str

    __dataflow__ = {
        'soft_delete': True  # Enable soft deletes
    }

workflow = WorkflowBuilder()

# Soft delete (preserves data)
workflow.add_node("CustomerDeleteNode", "soft_delete_customer", {
    "id": 123,
    "soft_delete": True  # Sets deleted_at timestamp
})

# List active customers (excludes soft-deleted)
workflow.add_node("CustomerListNode", "active_customers", {
    "filter": {"active": True}
    # Soft-deleted records automatically excluded
})

# List including soft-deleted
workflow.add_node("CustomerListNode", "all_customers", {
    "filter": {},
    "include_deleted": True  # Include soft-deleted records
})
```

## Troubleshooting

| Issue | Cause | Solution |
|-------|-------|----------|
| `Node 'UserCreateNode' not found` | Model not defined with @db.model | Add @db.model decorator to class |
| `KeyError: 'id'` in results | Wrong result access pattern | Use `results["node"]["result"]["id"]` |
| `ValidationError: Missing required field` | Field without default | Provide value or add default to model |
| `IntegrityError: duplicate key` | Unique constraint violation | Check for existing record before creating |
| `NotFoundError: Record not found` | Invalid ID or deleted record | Verify ID exists and isn't soft-deleted |

## Quick Tips

- String IDs fully supported (v0.4.0+) - no conversion needed
- Use connections for dynamic parameters, NOT template syntax
- Access results via `results["node"]["result"]` pattern
- Soft deletes preserve data with `deleted_at` timestamp
- ListNode excludes soft-deleted by default
- Use `count_only=True` for pagination counts
- ReadNode can use ID or conditions
- UpdateNode returns updated record if `return_updated=True`

## Version Notes

- **v0.4.0+**: String ID support - preserved throughout operations
- **v0.4.0+**: DateTime serialization fixed - use native datetime objects
- **v0.4.0+**: Workflow connection parameter order fixed
- **v0.9.25+**: Multi-instance isolation - separate contexts

## Keywords for Auto-Trigger

<!-- Trigger Keywords: DataFlow CRUD, generated nodes, UserCreateNode, UserReadNode, UserUpdateNode, UserDeleteNode, UserListNode, create read update delete, basic operations, single record, DataFlow operations, database operations, CRUD patterns, node operations -->

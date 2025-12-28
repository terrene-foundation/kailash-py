---
name: dataflow-express
description: "High-performance direct node invocation for DataFlow operations. Use when asking 'ExpressDataFlow', 'db.express', 'direct node invocation', 'fast CRUD', 'simple database operations', 'skip workflow overhead', or 'high-performance DataFlow'."
---

# ExpressDataFlow - High-Performance Direct Node Invocation

High-performance wrapper providing ~23x faster execution by bypassing workflow overhead for simple database operations.

> **Skill Metadata**
> Category: `dataflow`
> Priority: `HIGH`
> Related Skills: [`dataflow-quickstart`](dataflow-quickstart.md), [`dataflow-crud-operations`](dataflow-crud-operations.md), [`dataflow-bulk-operations`](dataflow-bulk-operations.md)
> Related Subagents: `dataflow-specialist` (enterprise features)

## Quick Reference

- **Access**: `db.express.<operation>()` after `await db.initialize()`
- **Performance**: ~23x faster than workflow-based operations
- **Operations**: create, read, update, delete, list, count, bulk_create, bulk_update, bulk_delete, bulk_upsert
- **Best For**: Simple CRUD operations, high-throughput scenarios
- **NOT For**: Multi-node workflows, conditional execution, transactions

## 30-Second Quick Start

```python
from dataflow import DataFlow

db = DataFlow("postgresql://user:password@localhost/mydb")

@db.model
class User:
    id: str
    name: str
    email: str
    active: bool = True

# Initialize before using express
await db.initialize()

# Direct node invocation - ~23x faster than workflows
user = await db.express.create("User", {
    "id": "user-001",
    "name": "Alice",
    "email": "alice@example.com"
})

# Read
user = await db.express.read("User", "user-001")

# Update
updated = await db.express.update("User", {"id": "user-001"}, {"name": "Alice Updated"})

# Delete
success = await db.express.delete("User", "user-001")

# List with filter
users = await db.express.list("User", filter={"active": True})

# Count
total = await db.express.count("User")
```

## Complete API Reference

### CRUD Operations

```python
# Create
result = await db.express.create("ModelName", {
    "id": "record-001",
    "field1": "value1",
    "field2": "value2"
})
# Returns: {"id": "record-001", "field1": "value1", "field2": "value2", ...}

# Read
result = await db.express.read("ModelName", "record-001")
result = await db.express.read("ModelName", "record-001", raise_on_not_found=True)
# Returns: dict or None

# Update
result = await db.express.update(
    "ModelName",
    filter={"id": "record-001"},  # Find record
    fields={"field1": "new_value"}  # Update fields
)
# Returns: {"id": "record-001", "field1": "new_value", ...}

# Delete
success = await db.express.delete("ModelName", "record-001")
# Returns: True or False

# List
results = await db.express.list("ModelName", filter={"active": True}, limit=100, offset=0)
# Returns: [{"id": "...", ...}, ...]

# Count
total = await db.express.count("ModelName", filter={"active": True})
# Returns: int
```

### Bulk Operations

```python
# Bulk Create
records = [
    {"id": "1", "name": "Alice"},
    {"id": "2", "name": "Bob"},
    {"id": "3", "name": "Charlie"}
]
created = await db.express.bulk_create("ModelName", records)
# Returns: [{"id": "1", ...}, {"id": "2", ...}, {"id": "3", ...}]

# Bulk Update
result = await db.express.bulk_update(
    "ModelName",
    filter={"active": True},
    data={"active": False}
)
# Returns: {"success": True, "updated": 5}

# Bulk Delete
success = await db.express.bulk_delete("ModelName", ["id-1", "id-2", "id-3"])
# Returns: True or False

# Bulk Upsert
result = await db.express.bulk_upsert(
    "ModelName",
    records=[{"id": "1", "name": "Alice"}, {"id": "4", "name": "Diana"}],
    conflict_on=["id"]
)
# Returns: {"success": True, "upserted": 2, "created": 1, "updated": 1}
```

## Performance Comparison

| Operation | Workflow Time | Express Time | Speedup |
|-----------|--------------|--------------|---------|
| Create | 2.3ms | 0.1ms | **23x** |
| Read | 2.1ms | 0.09ms | **23x** |
| Update | 2.4ms | 0.11ms | **22x** |
| Delete | 2.2ms | 0.1ms | **22x** |
| List | 2.5ms | 0.12ms | **21x** |
| Bulk Create (100) | 25ms | 1.2ms | **21x** |

## When to Use ExpressDataFlow

### Use ExpressDataFlow

- Simple CRUD operations without workflow complexity
- High-throughput applications needing maximum performance
- Cleaner code for straightforward database operations
- Single-node operations

### Use Traditional Workflows Instead

- Multi-node operations with data flow between nodes
- Conditional execution or branching logic
- Transaction management across operations
- Cycle execution patterns
- Error recovery and retry logic

## Common Patterns

### Pattern 1: User Registration

```python
async def register_user(email: str, name: str) -> dict:
    import uuid

    # Check if user exists
    existing = await db.express.list("User", filter={"email": email}, limit=1)
    if existing:
        return {"error": "Email already registered", "user": existing[0]}

    # Create new user
    user = await db.express.create("User", {
        "id": str(uuid.uuid4()),
        "email": email,
        "name": name,
        "active": True
    })
    return {"success": True, "user": user}
```

### Pattern 2: Paginated API

```python
async def get_users_paginated(page: int = 1, per_page: int = 20) -> dict:
    offset = (page - 1) * per_page

    total = await db.express.count("User")
    users = await db.express.list("User", limit=per_page, offset=offset)

    return {
        "data": users,
        "page": page,
        "per_page": per_page,
        "total": total,
        "total_pages": (total + per_page - 1) // per_page
    }
```

### Pattern 3: Batch Import

```python
async def import_users(csv_data: list[dict]) -> dict:
    import uuid

    records = [
        {"id": str(uuid.uuid4()), "name": row["name"], "email": row["email"]}
        for row in csv_data
    ]

    result = await db.express.bulk_upsert(
        "User", records=records, conflict_on=["email"]
    )

    return {
        "imported": result.get("upserted", 0),
        "created": result.get("created", 0),
        "updated": result.get("updated", 0)
    }
```

## Troubleshooting

### "Model not found: ModelName"

Use exact class name (case-sensitive):

```python
@db.model
class UserAccount:
    id: str

# WRONG
await db.express.create("useraccount", {...})

# CORRECT
await db.express.create("UserAccount", {...})
```

### "DataFlow not initialized"

Always initialize before using express:

```python
db = DataFlow("postgresql://...")

@db.model
class User:
    id: str

# REQUIRED
await db.initialize()

# Now express works
await db.express.create("User", {...})
```

### Empty list returned

If using custom `__tablename__`, ensure you're on v0.9.8+:

```python
@db.model
class User:
    id: str
    __tablename__ = "custom_users"

# Fixed in v0.9.8 - uses correct table name
users = await db.express.list("User")
```

## Related Documentation

- **User Guide**: `sdk-users/apps/dataflow/guides/express-dataflow.md`
- **CRUD Operations**: `dataflow-crud-operations.md`
- **Bulk Operations**: `dataflow-bulk-operations.md`
- **Performance Guide**: `dataflow-performance.md`

## Version History

- **v0.9.8**: Initial ExpressDataFlow release with full CRUD and bulk operations

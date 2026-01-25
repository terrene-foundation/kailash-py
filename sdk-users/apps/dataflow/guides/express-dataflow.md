# ExpressDataFlow Guide - High-Performance Direct Node Invocation

## Table of Contents
1. [What is ExpressDataFlow?](#what-is-expressdataflow)
2. [Basic Usage](#basic-usage)
3. [CRUD Operations](#crud-operations)
4. [Bulk Operations](#bulk-operations)
5. [Query Operations](#query-operations)
6. [Performance Comparison](#performance-comparison)
7. [Parameter Reference](#parameter-reference)
8. [Common Patterns](#common-patterns)
9. [Troubleshooting](#troubleshooting)
10. [Best Practices](#best-practices)

## What is ExpressDataFlow?

**ExpressDataFlow** provides high-performance direct node invocation for DataFlow operations, bypassing workflow overhead for simple database operations. It offers approximately **23x faster execution** compared to workflow-based operations while maintaining the same safety guarantees.

### Key Features

- **Direct node invocation**: Skip workflow construction for simple operations
- **~23x performance improvement**: Benchmarked against workflow-based approach
- **Same node behavior**: Uses identical generated nodes under the hood
- **Async-first**: All operations are async for modern Python applications
- **Type-safe**: Returns consistent result formats

### When to Use ExpressDataFlow

**Use ExpressDataFlow when you want to**:
- Perform simple CRUD operations without workflow complexity
- Maximize performance for high-throughput applications
- Write cleaner code for straightforward database operations
- Avoid workflow boilerplate for single-node operations

**Don't use ExpressDataFlow when**:
- You need multi-node workflows with connections
- You need conditional execution or branching logic
- You need transaction management across multiple operations
- You need workflow features like cycles or error recovery

## Basic Usage

### Initialization

ExpressDataFlow is automatically available on any DataFlow instance:

```python
from dataflow import DataFlow

# Initialize DataFlow
db = DataFlow("postgresql://user:password@localhost/mydb")

@db.model
class User:
    id: str
    name: str
    email: str
    active: bool = True

# Initialize (required before using express)
await db.initialize()

# ExpressDataFlow is available via db.express
result = await db.express.create("User", {
    "id": "user-001",
    "name": "Alice",
    "email": "alice@example.com"
})
```

### Understanding the API

ExpressDataFlow methods follow a consistent pattern:

```python
# Pattern: await db.express.<operation>("<ModelName>", <parameters>)

# Create
result = await db.express.create("User", {"id": "1", "name": "Alice"})

# Read
result = await db.express.read("User", "user-001")

# Update
result = await db.express.update("User", {"id": "user-001"}, {"name": "Alice Updated"})

# Delete
result = await db.express.delete("User", "user-001")

# List
results = await db.express.list("User", filter={"active": True})
```

## CRUD Operations

### Create

Create a single record:

```python
# Basic create
user = await db.express.create("User", {
    "id": "user-001",
    "name": "Alice Smith",
    "email": "alice@example.com",
    "active": True
})

print(f"Created user: {user['id']}")
# Output: Created user: user-001

# Create with defaults (active defaults to True)
user = await db.express.create("User", {
    "id": "user-002",
    "name": "Bob Jones",
    "email": "bob@example.com"
})
```

**Return Structure**:
```python
{
    "id": "user-001",
    "name": "Alice Smith",
    "email": "alice@example.com",
    "active": True
}
```

### Read

Read a single record by ID:

```python
# Read by ID
user = await db.express.read("User", "user-001")

if user:
    print(f"Found: {user['name']}")
else:
    print("User not found")

# Read with raise_on_not_found (raises exception if not found)
try:
    user = await db.express.read("User", "non-existent", raise_on_not_found=True)
except Exception as e:
    print(f"User not found: {e}")
```

**Return Structure**:
```python
# Found
{
    "id": "user-001",
    "name": "Alice Smith",
    "email": "alice@example.com",
    "active": True
}

# Not found
None
```

### Update

Update an existing record:

```python
# Update by filter
updated = await db.express.update(
    "User",
    filter={"id": "user-001"},  # Filter to find record
    fields={"name": "Alice Johnson", "active": False}  # Fields to update
)

print(f"Updated: {updated['name']}")
# Output: Updated: Alice Johnson

# Update returns the full updated record
print(updated)
# {
#     "id": "user-001",
#     "name": "Alice Johnson",
#     "email": "alice@example.com",
#     "active": False
# }
```

**Return Structure**:
```python
{
    "id": "user-001",
    "name": "Alice Johnson",
    "email": "alice@example.com",
    "active": False
}
```

### Delete

Delete a single record by ID:

```python
# Delete by ID
success = await db.express.delete("User", "user-001")

if success:
    print("User deleted successfully")
else:
    print("User not found or delete failed")
```

**Return Structure**:
```python
True  # Success
False  # Not found or failed
```

## Bulk Operations

### Bulk Create

Create multiple records in a single operation:

```python
# Bulk create
users = [
    {"id": "user-001", "name": "Alice", "email": "alice@example.com"},
    {"id": "user-002", "name": "Bob", "email": "bob@example.com"},
    {"id": "user-003", "name": "Charlie", "email": "charlie@example.com"},
]

created = await db.express.bulk_create("User", users)

print(f"Created {len(created)} users")
# Output: Created 3 users

# Each created record is returned
for user in created:
    print(f"  - {user['id']}: {user['name']}")
```

**Return Structure**:
```python
[
    {"id": "user-001", "name": "Alice", "email": "alice@example.com", "active": True},
    {"id": "user-002", "name": "Bob", "email": "bob@example.com", "active": True},
    {"id": "user-003", "name": "Charlie", "email": "charlie@example.com", "active": True}
]
```

### Bulk Update

Update multiple records matching a filter:

```python
# Bulk update by filter
result = await db.express.bulk_update(
    "User",
    filter={"active": True},  # Match all active users
    data={"active": False}    # Set all to inactive
)

print(f"Updated {result['updated']} records")

# Bulk update returns operation metadata
print(result)
# {"success": True, "updated": 5}
```

**Return Structure**:
```python
{
    "success": True,
    "updated": 5  # Number of records updated
}
```

### Bulk Delete

Delete multiple records by IDs:

```python
# Bulk delete by IDs
result = await db.express.bulk_delete("User", ["user-001", "user-002", "user-003"])

if result:
    print("Bulk delete successful")
else:
    print("Bulk delete failed")
```

**Return Structure**:
```python
True  # Success
False  # Failed
```

### Bulk Upsert

Insert or update records atomically:

```python
# Bulk upsert - insert if not exists, update if exists
records = [
    {"id": "user-001", "name": "Alice Updated", "email": "alice@new.com"},
    {"id": "user-004", "name": "Diana", "email": "diana@example.com"},  # New
]

result = await db.express.bulk_upsert(
    "User",
    records=records,
    conflict_on=["id"]  # Conflict detection field
)

print(f"Upserted: {result['upserted']} records")
print(f"Created: {result['created']}, Updated: {result['updated']}")
```

**Return Structure**:
```python
{
    "success": True,
    "upserted": 2,
    "created": 1,
    "updated": 1
}
```

## Query Operations

### List

Query records with filtering, pagination, and sorting:

```python
# Basic list - all records
all_users = await db.express.list("User")
print(f"Total users: {len(all_users)}")

# List with filter
active_users = await db.express.list("User", filter={"active": True})

# List with pagination
page1 = await db.express.list("User", limit=10, offset=0)
page2 = await db.express.list("User", limit=10, offset=10)

# List with sorting (when supported by underlying node)
sorted_users = await db.express.list("User", filter={}, limit=100, offset=0)
```

**Return Structure**:
```python
[
    {"id": "user-001", "name": "Alice", "email": "alice@example.com", "active": True},
    {"id": "user-002", "name": "Bob", "email": "bob@example.com", "active": True},
    # ... more records
]
```

### Count

Count records matching a filter:

```python
# Count all records
total = await db.express.count("User")
print(f"Total users: {total}")

# Count with filter
active_count = await db.express.count("User", filter={"active": True})
print(f"Active users: {active_count}")
```

**Return Structure**:
```python
42  # Integer count
```

## Performance Comparison

ExpressDataFlow provides significant performance improvements over workflow-based operations:

### Benchmark Results

| Operation | Workflow Time | Express Time | Speedup |
|-----------|--------------|--------------|---------|
| Create | 2.3ms | 0.1ms | **23x** |
| Read | 2.1ms | 0.09ms | **23x** |
| Update | 2.4ms | 0.11ms | **22x** |
| Delete | 2.2ms | 0.1ms | **22x** |
| List | 2.5ms | 0.12ms | **21x** |
| Bulk Create (100) | 25ms | 1.2ms | **21x** |

### Why Express is Faster

1. **No workflow construction**: Skips WorkflowBuilder overhead
2. **No runtime initialization**: Direct node execution
3. **No connection validation**: Single-node operations don't need validation
4. **Minimal overhead**: Direct async_run() call on nodes

### When to Use Workflows Instead

Use traditional workflows when you need:
- Multi-node operations with data flow
- Conditional execution or branching
- Transaction management across operations
- Error recovery and retry logic
- Cycle execution patterns

## Parameter Reference

### Common Parameters

| Method | Parameters | Description |
|--------|------------|-------------|
| `create` | `model_name: str`, `data: dict` | Create single record |
| `read` | `model_name: str`, `id: str`, `raise_on_not_found: bool = False` | Read by ID |
| `update` | `model_name: str`, `filter: dict`, `fields: dict` | Update matching records |
| `delete` | `model_name: str`, `id: str` | Delete by ID |
| `list` | `model_name: str`, `filter: dict = {}`, `limit: int = 100`, `offset: int = 0` | Query records |
| `count` | `model_name: str`, `filter: dict = {}` | Count records |
| `bulk_create` | `model_name: str`, `records: list[dict]` | Create multiple records |
| `bulk_update` | `model_name: str`, `filter: dict`, `data: dict` | Update multiple records |
| `bulk_delete` | `model_name: str`, `ids: list[str]` | Delete by IDs |
| `bulk_upsert` | `model_name: str`, `records: list[dict]`, `conflict_on: list[str]` | Upsert multiple |

### Model Name Resolution

ExpressDataFlow uses the class name as the model name:

```python
@db.model
class UserAccount:
    id: str
    name: str

# Use class name as model_name
await db.express.create("UserAccount", {...})

# With custom __tablename__, still use class name
@db.model
class User:
    id: str
    name: str
    __tablename__ = "custom_users_table"

# Model name is "User", not "custom_users_table"
await db.express.create("User", {...})
```

## Common Patterns

### Pattern 1: User Registration

```python
async def register_user(email: str, name: str) -> dict:
    """Register a new user with idempotency check."""
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
    """Get paginated user list with total count."""
    offset = (page - 1) * per_page

    # Get total count
    total = await db.express.count("User")

    # Get page of results
    users = await db.express.list("User", limit=per_page, offset=offset)

    return {
        "data": users,
        "page": page,
        "per_page": per_page,
        "total": total,
        "total_pages": (total + per_page - 1) // per_page
    }
```

### Pattern 3: Soft Delete

```python
async def soft_delete_user(user_id: str) -> bool:
    """Soft delete a user by setting active=False."""
    result = await db.express.update(
        "User",
        filter={"id": user_id},
        fields={"active": False}
    )
    return result is not None
```

### Pattern 4: Batch Import

```python
async def import_users_from_csv(csv_data: list[dict]) -> dict:
    """Bulk import users with conflict handling."""
    # Prepare records with generated IDs
    import uuid

    records = [
        {
            "id": str(uuid.uuid4()),
            "name": row["name"],
            "email": row["email"],
            "active": True
        }
        for row in csv_data
    ]

    # Use bulk_upsert for idempotent import
    result = await db.express.bulk_upsert(
        "User",
        records=records,
        conflict_on=["email"]  # Update if email exists
    )

    return {
        "imported": result.get("upserted", 0),
        "created": result.get("created", 0),
        "updated": result.get("updated", 0)
    }
```

### Pattern 5: Search with Filters

```python
async def search_users(
    name_contains: str = None,
    is_active: bool = None,
    limit: int = 50
) -> list[dict]:
    """Search users with multiple filter criteria."""
    filter_dict = {}

    if is_active is not None:
        filter_dict["active"] = is_active

    # Note: Complex filters depend on underlying node support
    users = await db.express.list("User", filter=filter_dict, limit=limit)

    # Client-side filtering for name if needed
    if name_contains:
        users = [u for u in users if name_contains.lower() in u["name"].lower()]

    return users
```

## Troubleshooting

### Error: "Model not found: ModelName"

**Cause**: Model name doesn't match registered model.

**Solution**: Use exact class name (case-sensitive):

```python
@db.model
class UserAccount:
    id: str
    name: str

# WRONG
await db.express.create("useraccount", {...})  # Case mismatch
await db.express.create("User", {...})  # Wrong name

# CORRECT
await db.express.create("UserAccount", {...})  # Exact match
```

### Error: "DataFlow not initialized"

**Cause**: Called express methods before `db.initialize()`.

**Solution**: Always initialize before using express:

```python
db = DataFlow("postgresql://...")

@db.model
class User:
    id: str
    name: str

# WRONG - not initialized
user = await db.express.create("User", {...})  # Error!

# CORRECT
await db.initialize()  # Initialize first
user = await db.express.create("User", {...})  # Works
```

### Error: "Node not found: ModelNameCreateNode"

**Cause**: Model not properly registered or initialized.

**Solution**: Ensure model is decorated and DataFlow is initialized:

```python
# WRONG - model not decorated
class User:
    id: str
    name: str

# CORRECT - decorated with @db.model
@db.model
class User:
    id: str
    name: str

await db.initialize()
```

### Error: Empty list returned when records exist

**Cause**: Table name mismatch with custom `__tablename__`.

**Solution**: This was fixed in v0.10.6. Ensure you're using the latest version:

```python
# Works correctly in v0.10.6+
@db.model
class User:
    id: str
    name: str
    __tablename__ = "custom_users"

await db.initialize()

# Both create and list use correct table
await db.express.create("User", {"id": "1", "name": "Alice"})
users = await db.express.list("User")  # Returns records correctly
```

### Error: bulk_delete returns count instead of boolean

**Cause**: Version prior to v0.10.6.

**Solution**: Upgrade to v0.10.6+ where return type is consistent:

```python
# v0.10.6+ returns boolean
result = await db.express.bulk_delete("User", ["id-1", "id-2"])
# result is True or False
```

## Best Practices

### 1. Always Initialize Before Use

```python
db = DataFlow("postgresql://...")

@db.model
class User:
    id: str
    name: str

# BEST PRACTICE: Initialize in application startup
async def startup():
    await db.initialize()

# Then use express throughout application
async def create_user(data: dict):
    return await db.express.create("User", data)
```

### 2. Use Type Hints for Clarity

```python
async def get_user(user_id: str) -> dict | None:
    """Get user by ID with proper type hints."""
    return await db.express.read("User", user_id)

async def list_active_users() -> list[dict]:
    """List all active users."""
    return await db.express.list("User", filter={"active": True})
```

### 3. Handle Not Found Cases

```python
async def get_user_or_404(user_id: str) -> dict:
    """Get user or raise HTTP 404."""
    user = await db.express.read("User", user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user

# Or use raise_on_not_found
async def get_user_strict(user_id: str) -> dict:
    """Get user with automatic exception on not found."""
    return await db.express.read("User", user_id, raise_on_not_found=True)
```

### 4. Use Bulk Operations for Multiple Records

```python
# BAD - Individual creates are slower
for user_data in users_list:
    await db.express.create("User", user_data)

# GOOD - Bulk create is much faster
await db.express.bulk_create("User", users_list)
```

### 5. Use Workflows for Complex Operations

```python
# Express for simple CRUD
user = await db.express.create("User", {...})

# Workflows for complex multi-step operations
workflow = WorkflowBuilder()
workflow.add_node("UserCreateNode", "create_user", {...})
workflow.add_node("EmailSendNode", "send_welcome", {...})
workflow.add_connection("create_user", "id", "send_welcome", "user_id")
# ... execute workflow
```

## Related Documentation

- **DataFlow Getting Started**: `sdk-users/apps/dataflow/docs/getting-started/quickstart.md`
- **Node Reference**: `sdk-users/apps/dataflow/docs/reference/nodes.md`
- **Bulk Operations Guide**: `sdk-users/apps/dataflow/docs/development/bulk-operations.md`
- **UpsertNode Guide**: `sdk-users/apps/dataflow/guides/upsert-node.md`
- **Error Handling Guide**: `sdk-users/apps/dataflow/guides/error-handling.md`

## Version History

- **v0.10.6**: Added ExpressDataFlow with all CRUD and bulk operations
- **v0.10.6**: Fixed custom `__tablename__` support for list operations
- **v0.10.6**: Fixed bulk_delete return type consistency

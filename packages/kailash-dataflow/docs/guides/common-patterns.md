# DataFlow Common Patterns

## What Is This

This guide covers best practices, anti-patterns, and common workflow patterns for DataFlow. Use these patterns to write maintainable, performant, and correct DataFlow code.

## Model Definition Patterns

### Primary Key Pattern

**Best Practice**: Always use `id` with type annotation.

```python
# ✅ CORRECT
@db.model
class User:
    id: str  # Required, string type
    name: str

# ❌ WRONG - Different primary key name
@db.model
class User:
    user_id: str  # Causes VAL-001 error
    name: str
```

**Why**: DataFlow requires `id` as the primary key field name for all models.

**Reference**: See [Primary Keys Guide](primary-keys.md)

---

### Flat Fields Pattern

**Best Practice**: Use primitive types and foreign key fields only.

```python
# ✅ CORRECT - Flat fields with foreign key
@db.model
class User:
    id: str
    name: str
    organization_id: str  # Foreign key reference

@db.model
class Organization:
    id: str
    name: str

# ❌ WRONG - Nested object
class Address:
    street: str
    city: str

@db.model
class User:
    id: str
    name: str
    address: Address  # Not supported
```

**Why**: DataFlow requires flat fields for SQL database compatibility.

**Reference**: See [Flat Fields Guide](flat-fields.md)

---

### Auto-Managed Fields Pattern

**Best Practice**: Never define `created_at` or `updated_at` in models.

```python
# ✅ CORRECT - Omit auto-managed fields
@db.model
class User:
    id: str
    name: str
    email: str
    # created_at, updated_at added automatically

# ❌ WRONG - Manual timestamp fields
@db.model
class User:
    id: str
    name: str
    created_at: datetime  # Causes VAL-005 error
    updated_at: datetime  # Causes VAL-005 error
```

**Why**: DataFlow automatically manages `created_at` and `updated_at` timestamps at the database level.

**Reference**: See [Auto-Managed Fields Guide](auto-managed-fields.md)

---

### Supported Field Types

**Best Practice**: Use only supported primitive types.

```python
# ✅ CORRECT - Supported types
@db.model
class Product:
    id: str           # String
    name: str         # String
    price: float      # Float
    quantity: int     # Integer
    is_active: bool   # Boolean
    metadata: dict    # JSON object
    tags: list        # JSON array
    launched_at: datetime  # Datetime (if manually managed)

# ❌ WRONG - Custom classes
class Money:
    amount: float
    currency: str

@db.model
class Product:
    id: str
    price: Money  # Not supported
```

**Supported Types**:
- `str` - String/VARCHAR
- `int` - Integer
- `float` - Float/Decimal
- `bool` - Boolean
- `datetime` - Datetime/Timestamp
- `dict` - JSON object
- `list` - JSON array

**Reference**: See [Flat Fields Guide](flat-fields.md)

---

## Workflow Construction Patterns

### Builder Pattern

**Best Practice**: Always use `workflow.build()` before execution.

```python
# ✅ CORRECT
workflow = WorkflowBuilder()
workflow.add_node("UserCreateNode", "create", {...})
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())  # .build() required

# ❌ WRONG - Missing .build()
workflow = WorkflowBuilder()
workflow.add_node("UserCreateNode", "create", {...})
results, run_id = runtime.execute(workflow)  # TypeError
```

**Why**: `workflow.build()` finalizes the workflow and returns an executable object.

---

### Node Naming Pattern

**Best Practice**: Use `ModelOperationNode` format.

```python
# ✅ CORRECT - ModelOperationNode format
workflow.add_node("UserCreateNode", "create_user", {...})
workflow.add_node("UserListNode", "list_users", {...})

# ❌ WRONG - Missing "Node" suffix
workflow.add_node("UserCreate", "create", {...})  # Node not found
```

**Why**: DataFlow generates nodes with `ModelOperationNode` naming pattern (v0.6.0+).

---

### Parameter Pattern for CREATE

**Best Practice**: Pass flat fields directly.

```python
# ✅ CORRECT - Flat fields
workflow.add_node("UserCreateNode", "create", {
    "id": "user-123",
    "name": "Alice",
    "email": "alice@example.com"
})

# ❌ WRONG - Nested structure
workflow.add_node("UserCreateNode", "create", {
    "filter": {"id": "user-123"},  # Wrong for CREATE
    "fields": {"name": "Alice"}
})
```

**Why**: CreateNode expects flat fields, not filter/fields structure.

---

### Parameter Pattern for UPDATE

**Best Practice**: Use `filter` + `fields` structure.

```python
# ✅ CORRECT - filter/fields structure
workflow.add_node("UserUpdateNode", "update", {
    "filter": {"id": "user-123"},
    "fields": {"name": "Alice Updated"}
})

# ❌ WRONG - Flat fields
workflow.add_node("UserUpdateNode", "update", {
    "id": "user-123",
    "name": "Alice Updated"  # Wrong for UPDATE
})
```

**Why**: UpdateNode requires filter to identify records and fields to update.

---

### Parameter Pattern for LIST

**Best Practice**: Use `filters`, `limit`, `offset`, `order_by`.

```python
# ✅ CORRECT - Full LIST parameters
workflow.add_node("UserListNode", "list", {
    "filters": {"is_active": True},
    "limit": 20,
    "offset": 0,
    "order_by": "-created_at"  # Descending
})

# ✅ CORRECT - Minimal (all records)
workflow.add_node("UserListNode", "list", {
    "filters": {}
})
```

**Why**: ListNode supports flexible querying with filtering, pagination, and ordering.

---

## Common Workflow Patterns

### Pattern 1: Simple CRUD

**Create, Read, Update, Delete** in sequence.

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime import LocalRuntime
import uuid

workflow = WorkflowBuilder()

# CREATE
workflow.add_node("UserCreateNode", "create", {
    "id": str(uuid.uuid4()),
    "name": "Alice",
    "email": "alice@example.com"
})

# READ (depends on CREATE via result reference)
workflow.add_node("UserReadNode", "read", {
    "id": "$create.id"  # Reference CREATE result
})

# UPDATE (depends on READ)
workflow.add_node("UserUpdateNode", "update", {
    "filter": {"id": "$read.id"},
    "fields": {"name": "Alice Updated"}
})

# DELETE (depends on UPDATE)
workflow.add_node("UserDeleteNode", "delete", {
    "id": "$update.id"
})

runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
```

**Use Case**: Sequential CRUD operations where each step depends on previous results.

---

### Pattern 2: Pagination

**List records with offset/limit**.

```python
def list_users_paginated(db, page: int, per_page: int):
    """List users with pagination."""
    offset = (page - 1) * per_page

    workflow = WorkflowBuilder()
    workflow.add_node("UserListNode", "list", {
        "filters": {},
        "limit": per_page,
        "offset": offset,
        "order_by": "-created_at"
    })

    runtime = LocalRuntime()
    results, _ = runtime.execute(workflow.build())
    return results["list"]

# Get page 2 (records 21-40)
users = list_users_paginated(db, page=2, per_page=20)
```

**Use Case**: API endpoints, UI tables with pagination.

---

### Pattern 3: Filtering

**Filter records by multiple conditions**.

```python
def get_active_users(db, organization_id: str):
    """Get active users in organization."""
    workflow = WorkflowBuilder()
    workflow.add_node("UserListNode", "list", {
        "filters": {
            "organization_id": organization_id,
            "is_active": True
        },
        "order_by": "-created_at"
    })

    runtime = LocalRuntime()
    results, _ = runtime.execute(workflow.build())
    return results["list"]
```

**Supported Filter Operators**:
- Exact match: `{"age": 30}`
- Greater than: `{"age__gte": 18}`
- Less than: `{"age__lt": 65}`
- Contains: `{"name__icontains": "alice"}`
- NULL check: `{"organization_id__isnull": True}`

---

### Pattern 4: Bulk Operations

**Create multiple records efficiently**.

```python
def create_bulk_users(db, user_data: list):
    """Create multiple users in bulk."""
    workflow = WorkflowBuilder()
    workflow.add_node("UserBulkCreateNode", "bulk_create", {
        "records": user_data
    })

    runtime = LocalRuntime()
    results, _ = runtime.execute(workflow.build())
    return results["bulk_create"]

# Create 100 users
users = [
    {"id": f"user-{i}", "name": f"User {i}", "email": f"user{i}@example.com"}
    for i in range(100)
]
created = create_bulk_users(db, users)
```

**Use Case**: Data imports, seeding, batch processing.

---

### Pattern 5: Upsert

**Insert or update based on unique field**.

```python
def sync_user(db, email: str, name: str):
    """Create user if not exists, otherwise update."""
    workflow = WorkflowBuilder()
    workflow.add_node("UserUpsertNode", "upsert", {
        "where": {"email": email},
        "conflict_on": ["email"],  # Unique field
        "update": {"name": name},
        "create": {
            "id": str(uuid.uuid4()),
            "email": email,
            "name": name
        }
    })

    runtime = LocalRuntime()
    results, _ = runtime.execute(workflow.build())
    user = results["upsert"]["record"]

    if results["upsert"]["created"]:
        print(f"Created new user: {email}")
    else:
        print(f"Updated existing user: {email}")

    return user
```

**Use Case**: Idempotent API requests, data synchronization.

---

### Pattern 6: Foreign Key Relationships

**Query related records**.

```python
def get_user_with_organization(db, user_id: str):
    """Get user and their organization."""
    workflow = WorkflowBuilder()

    # Get user
    workflow.add_node("UserReadNode", "get_user", {
        "id": user_id
    })

    # Get organization (depends on user)
    workflow.add_node("OrganizationReadNode", "get_org", {
        "id": "$get_user.organization_id"  # Foreign key reference
    })

    runtime = LocalRuntime()
    results, _ = runtime.execute(workflow.build())

    return {
        "user": results["get_user"],
        "organization": results["get_org"]
    }
```

**Use Case**: Joins, relationship loading.

---

### Pattern 7: Many-to-Many Relationships

**Use junction table**.

```python
@db.model
class User:
    id: str
    name: str

@db.model
class Role:
    id: str
    name: str

@db.model
class UserRole:  # Junction table
    id: str
    user_id: str  # Foreign key to User
    role_id: str  # Foreign key to Role

def get_user_roles(db, user_id: str):
    """Get all roles for a user."""
    workflow = WorkflowBuilder()

    # Get user-role mappings
    workflow.add_node("UserRoleListNode", "get_mappings", {
        "filters": {"user_id": user_id}
    })

    # Get role details (requires iteration or PythonCodeNode)
    workflow.add_node("PythonCodeNode", "get_roles", {
        "code": """
role_ids = [m['role_id'] for m in mappings]
# Fetch roles by IDs (simplified)
return role_ids
        """,
        "inputs": {"mappings": "$get_mappings"}
    })

    runtime = LocalRuntime()
    results, _ = runtime.execute(workflow.build())
    return results["get_roles"]
```

**Use Case**: Many-to-many relationships, complex queries.

---

### Pattern 8: Conditional Workflow

**Use SwitchNode for branching**.

```python
def process_user_by_status(db, user_id: str):
    """Process user based on status."""
    workflow = WorkflowBuilder()

    # Get user
    workflow.add_node("UserReadNode", "get_user", {"id": user_id})

    # Check status
    workflow.add_node("PythonCodeNode", "check_status", {
        "code": "return user['status'] == 'active'",
        "inputs": {"user": "$get_user"}
    })

    # Branch based on status
    workflow.add_node("SwitchNode", "branch", {
        "condition": "$check_status",
        "true_output": "$get_user",
        "false_output": "$get_user"
    })

    # Active user processing
    workflow.add_node("PythonCodeNode", "process_active", {
        "code": "return {'processed': True, 'type': 'active'}",
        "inputs": {"user": "$branch.true_output"}
    })

    # Inactive user processing
    workflow.add_node("PythonCodeNode", "process_inactive", {
        "code": "return {'processed': True, 'type': 'inactive'}",
        "inputs": {"user": "$branch.false_output"}
    })

    runtime = LocalRuntime(conditional_execution="skip_branches")
    results, _ = runtime.execute(workflow.build())
    return results
```

**Use Case**: Conditional logic, state machines, branching workflows.

---

## Performance Optimization Patterns

### Pattern 1: Use Bulk Operations

**Best Practice**: Batch INSERT/UPDATE/DELETE for better performance.

```python
# ❌ SLOW - 100 individual INSERTs
for i in range(100):
    workflow = WorkflowBuilder()
    workflow.add_node("UserCreateNode", "create", {
        "id": f"user-{i}",
        "name": f"User {i}"
    })
    runtime.execute(workflow.build())

# ✅ FAST - 1 bulk INSERT
workflow = WorkflowBuilder()
workflow.add_node("UserBulkCreateNode", "bulk_create", {
    "records": [
        {"id": f"user-{i}", "name": f"User {i}"}
        for i in range(100)
    ]
})
runtime.execute(workflow.build())
```

**Performance**: 10-100x faster for bulk operations.

---

### Pattern 2: Use Pagination

**Best Practice**: Always use `limit` and `offset` for large datasets.

```python
# ❌ WRONG - Load all records
workflow.add_node("UserListNode", "list", {
    "filters": {}  # No limit - loads everything
})

# ✅ CORRECT - Paginate results
workflow.add_node("UserListNode", "list", {
    "filters": {},
    "limit": 100,
    "offset": 0
})
```

**Performance**: Prevents memory exhaustion on large tables.

---

### Pattern 3: Schema Cache

**Best Practice**: Schema cache is enabled by default (v0.7.3+).

```python
# ✅ CORRECT - Schema cache enabled (default)
db = DataFlow("postgresql://...")

# First operation: Cache miss (~1500ms)
workflow.add_node("UserCreateNode", "create", {...})
runtime.execute(workflow.build())  # Creates table if needed

# Subsequent operations: Cache hit (~1ms)
workflow.add_node("UserCreateNode", "create", {...})
runtime.execute(workflow.build())  # 99% faster (no migration check)
```

**Performance**: 91-99% faster for multi-operation workflows.

---

### Pattern 4: Reuse Runtime

**Best Practice**: Create runtime once, reuse for multiple workflows.

```python
# ❌ SLOW - Create runtime per workflow
for i in range(100):
    workflow = WorkflowBuilder()
    workflow.add_node("UserCreateNode", "create", {...})
    runtime = LocalRuntime()  # New runtime each time
    runtime.execute(workflow.build())

# ✅ FAST - Reuse runtime
runtime = LocalRuntime()  # Create once
for i in range(100):
    workflow = WorkflowBuilder()
    workflow.add_node("UserCreateNode", "create", {...})
    runtime.execute(workflow.build())  # Reuse
```

**Performance**: Eliminates runtime initialization overhead.

---

### Pattern 5: Use AsyncLocalRuntime for Concurrency

**Best Practice**: Use `AsyncLocalRuntime` for parallel operations.

```python
# ✅ CORRECT - Async for concurrent workflows
from kailash.runtime import AsyncLocalRuntime

async def create_users_concurrent(db, user_data: list):
    runtime = AsyncLocalRuntime()

    tasks = []
    for user in user_data:
        workflow = WorkflowBuilder()
        workflow.add_node("UserCreateNode", "create", user)
        tasks.append(runtime.execute_workflow_async(workflow.build(), inputs={}))

    results = await asyncio.gather(*tasks)
    return results

# Run concurrently
asyncio.run(create_users_concurrent(db, users))
```

**Performance**: 10-100x faster for I/O-bound operations.

---

## Error Handling Patterns

### Pattern 1: Validate Before Workflow Execution

**Best Practice**: Validate inputs before creating workflows.

```python
def create_user_safe(db, data: dict):
    """Create user with validation."""
    # ✅ CORRECT - Validate first
    if "id" not in data:
        raise ValueError("Field 'id' is required")
    if "email" not in data:
        raise ValueError("Field 'email' is required")

    # Execute workflow
    workflow = WorkflowBuilder()
    workflow.add_node("UserCreateNode", "create", data)
    runtime = LocalRuntime()
    results, _ = runtime.execute(workflow.build())
    return results["create"]
```

**Why**: Catch validation errors before expensive workflow execution.

---

### Pattern 2: Handle NULL Results

**Best Practice**: Always check for None from ReadNode.

```python
def get_user_safe(db, user_id: str):
    """Get user with error handling."""
    workflow = WorkflowBuilder()
    workflow.add_node("UserReadNode", "read", {"id": user_id})
    runtime = LocalRuntime()
    results, _ = runtime.execute(workflow.build())

    user = results.get("read")
    if user is None:
        raise ValueError(f"User {user_id} not found")

    return user
```

**Why**: ReadNode returns None for non-existent records.

---

### Pattern 3: Use try/except for Workflow Errors

**Best Practice**: Wrap workflow execution in try/except.

```python
def create_user_with_retry(db, data: dict, max_retries: int = 3):
    """Create user with retry logic."""
    for attempt in range(max_retries):
        try:
            workflow = WorkflowBuilder()
            workflow.add_node("UserCreateNode", "create", data)
            runtime = LocalRuntime()
            results, _ = runtime.execute(workflow.build())
            return results["create"]
        except Exception as e:
            if attempt < max_retries - 1:
                print(f"Attempt {attempt + 1} failed: {e}. Retrying...")
            else:
                raise
```

**Why**: Handle transient database errors with retries.

---

## Testing Patterns

### Pattern 1: Use In-Memory Database

**Best Practice**: Use `:memory:` for fast tests.

```python
def test_user_creation():
    """Test user creation."""
    # ✅ CORRECT - In-memory database
    db = DataFlow(":memory:")

    @db.model
    class User:
        id: str
        name: str

    # Test workflow
    workflow = WorkflowBuilder()
    workflow.add_node("UserCreateNode", "create", {
        "id": "user-1",
        "name": "Alice"
    })

    runtime = LocalRuntime()
    results, _ = runtime.execute(workflow.build())

    assert results["create"]["id"] == "user-1"
    assert results["create"]["name"] == "Alice"
```

**Performance**: 100x faster than PostgreSQL/MySQL for tests.

---

### Pattern 2: Test with Real Database

**Best Practice**: Use real database for integration tests.

```python
import pytest
from dataflow import DataFlow

@pytest.fixture
def db():
    """Real database fixture."""
    db = DataFlow("postgresql://localhost/test_db")
    yield db
    # Cleanup after test
    # DROP TABLE ... (or use existing_schema_mode)

def test_user_workflow_integration(db):
    """Integration test with real database."""
    @db.model
    class User:
        id: str
        name: str

    # Test workflow with real database
    workflow = WorkflowBuilder()
    workflow.add_node("UserCreateNode", "create", {
        "id": "user-1",
        "name": "Alice"
    })

    runtime = LocalRuntime()
    results, _ = runtime.execute(workflow.build())

    # Verify in database
    workflow2 = WorkflowBuilder()
    workflow2.add_node("UserReadNode", "read", {"id": "user-1"})
    results2, _ = runtime.execute(workflow2.build())

    assert results2["read"]["name"] == "Alice"
```

**Why**: Catch real-world database issues (constraints, triggers, etc.).

---

### Pattern 3: NO MOCKING Policy

**Best Practice**: Never mock DataFlow or database in integration tests.

```python
# ❌ WRONG - Mocking DataFlow
from unittest.mock import Mock

def test_user_creation_wrong():
    db = Mock(spec=DataFlow)  # Don't mock!
    db.get_models.return_value = {"User": Mock()}
    # This doesn't test real behavior

# ✅ CORRECT - Real DataFlow
def test_user_creation_correct():
    db = DataFlow(":memory:")  # Real instance

    @db.model
    class User:
        id: str
        name: str

    # Test with real DataFlow
    workflow = WorkflowBuilder()
    workflow.add_node("UserCreateNode", "create", {...})
    runtime = LocalRuntime()
    results, _ = runtime.execute(workflow.build())
```

**Why**: Mocking hides real bugs. Always use real infrastructure.

---

## Anti-Patterns to Avoid

### Anti-Pattern 1: Manual ID Generation in Models

```python
# ❌ WRONG - Auto-generating IDs in model
@db.model
class User:
    id: str = str(uuid.uuid4())  # Don't do this!
    name: str

# ✅ CORRECT - Generate IDs when creating
workflow.add_node("UserCreateNode", "create", {
    "id": str(uuid.uuid4()),  # Generate here
    "name": "Alice"
})
```

**Why**: IDs should be generated at creation time, not model definition time.

---

### Anti-Pattern 2: Mixing CREATE and UPDATE Patterns

```python
# ❌ WRONG - Using UpdateNode pattern for CREATE
workflow.add_node("UserCreateNode", "create", {
    "filter": {"id": "user-123"},  # Wrong for CREATE
    "fields": {"name": "Alice"}
})

# ✅ CORRECT - Use flat fields for CREATE
workflow.add_node("UserCreateNode", "create", {
    "id": "user-123",
    "name": "Alice"
})
```

**Why**: CreateNode expects flat fields, UpdateNode expects filter/fields.

---

### Anti-Pattern 3: Ignoring Schema Cache

```python
# ❌ WRONG - Disabling schema cache unnecessarily
db = DataFlow("postgresql://...", schema_cache_enabled=False)

# ✅ CORRECT - Use default (cache enabled)
db = DataFlow("postgresql://...")
```

**Why**: Schema cache provides 91-99% performance improvement.

---

### Anti-Pattern 4: Loading All Records Without Pagination

```python
# ❌ WRONG - Loading everything
workflow.add_node("UserListNode", "list", {"filters": {}})

# ✅ CORRECT - Use pagination
workflow.add_node("UserListNode", "list", {
    "filters": {},
    "limit": 100,
    "offset": 0
})
```

**Why**: Loading all records causes memory exhaustion on large tables.

---

### Anti-Pattern 5: Creating Runtime Per Workflow

```python
# ❌ WRONG - New runtime each time
for i in range(100):
    workflow = WorkflowBuilder()
    workflow.add_node("UserCreateNode", "create", {...})
    runtime = LocalRuntime()  # Inefficient
    runtime.execute(workflow.build())

# ✅ CORRECT - Reuse runtime
runtime = LocalRuntime()
for i in range(100):
    workflow = WorkflowBuilder()
    workflow.add_node("UserCreateNode", "create", {...})
    runtime.execute(workflow.build())
```

**Why**: Runtime initialization has overhead. Reuse for better performance.

---

## Related Guides

- [Primary Keys](primary-keys.md) - The `id` field requirement
- [Auto-Managed Fields](auto-managed-fields.md) - Timestamp handling
- [Flat Fields Pattern](flat-fields.md) - No nested objects
- [Error Cheat Sheet](cheat-sheet-errors.md) - Quick error reference
- [Migration from SQLAlchemy](from-sqlalchemy.md) - SQLAlchemy conversion
- [Migration from Django ORM](from-django-orm.md) - Django conversion

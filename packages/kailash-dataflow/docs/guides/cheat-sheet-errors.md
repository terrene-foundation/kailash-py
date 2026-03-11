# DataFlow Error Cheat Sheet

Quick reference for common DataFlow errors and their solutions.

## Model Definition Errors

### Error: Primary key not named `id`

**Symptom**:
```
ValidationError: Field 'id' is required but 'user_id' was provided
```

**Cause**: Primary key field not named `id`

**Fix**:
```python
# ❌ WRONG
@db.model
class User:
    user_id: str  # Wrong name

# ✅ CORRECT
@db.model
class User:
    id: str  # Must be named 'id'
```

**Reference**: See [Primary Keys Guide](primary-keys.md)

---

### Error: Including auto-managed fields

**Symptom**:
```
ValidationError: Fields 'created_at', 'updated_at' are auto-managed and cannot be manually set
```

**Cause**: Including `created_at` or `updated_at` in CREATE/UPDATE operations

**Fix**:
```python
# ❌ WRONG
workflow.add_node("UserCreateNode", "create", {
    "id": "user-123",
    "name": "Alice",
    "created_at": "2025-10-30T12:00:00"  # Remove this
})

# ✅ CORRECT
workflow.add_node("UserCreateNode", "create", {
    "id": "user-123",
    "name": "Alice"
    # Omit created_at, updated_at
})
```

**Reference**: See [Auto-Managed Fields Guide](auto-managed-fields.md)

---

### Error: Nested objects in model

**Symptom**:
```
TypeError: Field 'address' has unsupported type 'Address'
```

**Cause**: Using nested objects or custom classes as field types

**Fix**:
```python
# ❌ WRONG
@db.model
class User:
    id: str
    address: Address  # Nested object not supported

# ✅ CORRECT - Option 1: Flatten
@db.model
class User:
    id: str
    address_street: str
    address_city: str

# ✅ CORRECT - Option 2: Separate table
@db.model
class Address:
    id: str
    user_id: str
    street: str
    city: str
```

**Reference**: See [Flat Fields Guide](flat-fields.md)

---

## Workflow Execution Errors

### Error: Forgot to call `.build()`

**Symptom**:
```
TypeError: execute() missing required positional argument 'workflow'
```

**Cause**: Forgetting to call `.build()` on WorkflowBuilder

**Fix**:
```python
# ❌ WRONG
workflow = WorkflowBuilder()
workflow.add_node("UserCreateNode", "create", {...})
results, _ = runtime.execute(workflow)  # Missing .build()

# ✅ CORRECT
workflow = WorkflowBuilder()
workflow.add_node("UserCreateNode", "create", {...})
results, _ = runtime.execute(workflow.build())  # .build() required
```

---

### Error: Wrong node naming

**Symptom**:
```
KeyError: 'UserCreate' node not found
```

**Cause**: Incorrect node name format

**Fix**:
```python
# ❌ WRONG - Missing "Node" suffix
workflow.add_node("UserCreate", "create", {...})

# ✅ CORRECT - ModelOperationNode format
workflow.add_node("UserCreateNode", "create", {...})
```

---

### Error: CreateNode vs UpdateNode parameter confusion

**Symptom**:
```
ValidationError: CREATE operations expect flat fields, not filter/fields structure
```

**Cause**: Using UpdateNode parameter pattern for CreateNode

**Fix**:
```python
# ❌ WRONG - UpdateNode pattern on CreateNode
workflow.add_node("UserCreateNode", "create", {
    "filter": {"id": "user-123"},  # Wrong for CREATE
    "fields": {"name": "Alice"}
})

# ✅ CORRECT - Flat fields for CREATE
workflow.add_node("UserCreateNode", "create", {
    "id": "user-123",
    "name": "Alice"
})

# ✅ CORRECT - filter/fields for UPDATE
workflow.add_node("UserUpdateNode", "update", {
    "filter": {"id": "user-123"},
    "fields": {"name": "Alice Updated"}
})
```

---

## Connection Errors

### Error: Database connection failure

**Symptom**:
```
OperationalError: could not connect to server
```

**Cause**: Invalid database URL or server not running

**Fix**:
```python
# Check connection string format
# PostgreSQL
db = DataFlow("postgresql://user:password@localhost:5432/dbname")

# MySQL
db = DataFlow("mysql://user:password@localhost:3306/dbname")

# SQLite
db = DataFlow("sqlite:///path/to/database.db")

# Verify server is running
# PostgreSQL: sudo service postgresql status
# MySQL: sudo service mysql status
```

---

### Error: String ID type mismatch

**Symptom**:
```
TypeError: expected string but got integer
```

**Cause**: Passing integer when model expects string ID

**Fix**:
```python
# ❌ WRONG - Integer ID when model expects string
workflow.add_node("UserReadNode", "read", {
    "id": 123  # Wrong type
})

# ✅ CORRECT - String ID
workflow.add_node("UserReadNode", "read", {
    "id": "user-123"  # Correct type
})
```

---

## Query Errors

### Error: Empty results when record exists

**Symptom**: `results["list"]` returns `[]` even though records exist

**Cause**: Filter field name mismatch or wrong filter syntax

**Fix**:
```python
# ❌ WRONG - Typo in field name
workflow.add_node("UserListNode", "list", {
    "filters": {"is_activ": True}  # Typo: is_activ vs is_active
})

# ✅ CORRECT - Exact field name
workflow.add_node("UserListNode", "list", {
    "filters": {"is_active": True}
})
```

---

### Error: NULL vs empty string confusion

**Symptom**: Filter returns unexpected results

**Cause**: Confusing NULL with empty string

**Fix**:
```python
# Find records with NULL value
workflow.add_node("UserListNode", "list", {
    "filters": {"organization_id__isnull": True}
})

# Find records with empty string
workflow.add_node("UserListNode", "list", {
    "filters": {"organization_id": ""}
})
```

---

## Migration Errors

### Error: Table already exists

**Symptom**:
```
ProgrammingError: relation "users" already exists
```

**Cause**: Running migration when table already exists

**Fix**:
```python
# Use existing_schema_mode for existing tables
db = DataFlow(url, existing_schema_mode=True)

# Or drop table first (WARNING: data loss)
# DROP TABLE users;
```

---

### Error: Column type mismatch

**Symptom**:
```
DataError: invalid input syntax for type integer
```

**Cause**: Database column type doesn't match model field type

**Fix**:
```sql
-- Check column type
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_name = 'users';

-- Fix type mismatch
ALTER TABLE users ALTER COLUMN age TYPE integer USING age::integer;
```

---

## Runtime Errors

### Error: Timeout on workflow execution

**Symptom**:
```
TimeoutError: Workflow execution exceeded 120 seconds
```

**Cause**: Long-running query or cycle

**Fix**:
```python
# Increase timeout
runtime = LocalRuntime(timeout=300)  # 5 minutes

# Or use AsyncLocalRuntime for better concurrency
from kailash.runtime import AsyncLocalRuntime
runtime = AsyncLocalRuntime()
results, _ = await runtime.execute_workflow_async(workflow.build(), inputs={})
```

---

### Error: Memory error on large dataset

**Symptom**:
```
MemoryError: Unable to allocate memory
```

**Cause**: Loading too many records at once

**Fix**:
```python
# ❌ WRONG - Loading everything
workflow.add_node("UserListNode", "list", {
    "filters": {}  # No limit - loads all records
})

# ✅ CORRECT - Use pagination
workflow.add_node("UserListNode", "list", {
    "filters": {},
    "limit": 1000,
    "offset": 0
})

# Process in batches
for offset in range(0, 100000, 1000):
    workflow = WorkflowBuilder()
    workflow.add_node("UserListNode", "list", {
        "filters": {},
        "limit": 1000,
        "offset": offset
    })
    results, _ = runtime.execute(workflow.build())
    process_batch(results["list"])
```

---

## Quick Reference

| Error | Common Cause | Quick Fix |
|-------|-------------|-----------|
| `id required` | Wrong primary key name | Use `id: str`, not `user_id: str` |
| `auto-managed` | Manual timestamps | Omit `created_at`, `updated_at` |
| `unsupported type` | Nested objects | Use flat fields or foreign keys |
| `missing .build()` | Workflow not built | Call `workflow.build()` |
| `node not found` | Wrong node name | Use `ModelOperationNode` format |
| `connection failed` | Bad URL | Check connection string format |
| `type mismatch` | Wrong ID type | Use string IDs: `"user-123"` |
| `empty results` | Filter typo | Check exact field names |
| `timeout` | Long query | Increase timeout or use async |
| `memory error` | Too many records | Use pagination with limit/offset |

## Related Guides

- [Primary Keys](primary-keys.md) - The `id` field requirement
- [Auto-Managed Fields](auto-managed-fields.md) - Timestamp handling
- [Flat Fields Pattern](flat-fields.md) - No nested objects
- [Migration from SQLAlchemy](from-sqlalchemy.md) - ORM conversion
- [Migration from Django ORM](from-django-orm.md) - Django conversion
- [Common Patterns](common-patterns.md) - Best practices

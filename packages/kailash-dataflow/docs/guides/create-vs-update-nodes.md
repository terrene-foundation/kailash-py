# CreateNode vs UpdateNode: Complete Comparison Guide

## What Is This

**THE #1 source of DataFlow errors**: Developers apply CreateNode parameter patterns to UpdateNode (or vice versa), causing 1-2 hours of debugging.

This guide provides a **side-by-side comparison** of CreateNode and UpdateNode parameter structures, common mistakes, and how to fix them.

## When to Use

- **Before writing workflows**: Understand which pattern to use
- **When debugging "missing parameter" errors**: Check if you're using the wrong pattern
- **When migrating from ORMs**: Learn DataFlow's explicit parameter structure

---

## Quick Reference Table

| Aspect | CreateNode | UpdateNode |
|--------|-----------|------------|
| **Parameter Structure** | **Flat fields** | **Nested: filter + fields** |
| **Primary Key** | **Required in data** | **Required in filter** |
| **Field Format** | `{"id": "...", "name": "..."}` | `{"filter": {...}, "fields": {...}}` |
| **Common Error** | Missing `id` field | Flat fields instead of nested |
| **Return Value** | Created record | Updated record |
| **Typical Use** | Insert new record | Modify existing record |

---

## The Critical Difference

### CreateNode: Flat Field Structure

CreateNode uses **flat fields** - all fields at the top level:

```python
# ✅ CORRECT - CreateNode pattern
workflow.add_node("UserCreateNode", "create_user", {
    "id": "user-123",           # Top level
    "name": "Alice",            # Top level
    "email": "alice@example.com", # Top level
    "organization_id": "org-456"  # Top level
})
```

### UpdateNode: Nested filter + fields Structure

UpdateNode uses **nested structure** - `filter` identifies the record, `fields` contains updates:

```python
# ✅ CORRECT - UpdateNode pattern
workflow.add_node("UserUpdateNode", "update_user", {
    "filter": {                 # Nested: which record to update
        "id": "user-123"
    },
    "fields": {                 # Nested: what to update
        "name": "Alice Updated",
        "email": "alice.new@example.com"
    }
})
```

---

## Why They're Different

**CreateNode**: Creating a new record requires ALL fields (including `id`). No ambiguity - you're inserting exactly one record.

**UpdateNode**: Updating requires TWO pieces of information:
1. **Which record(s)** to update (`filter`)
2. **What fields** to change (`fields`)

This separation is explicit to prevent accidental bulk updates and make update intent clear.

---

## Side-by-Side Comparison

### Example: User Management

#### CREATE Operation

```python
from dataflow import DataFlow
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime import LocalRuntime

db = DataFlow(":memory:")

@db.model
class User:
    id: str
    name: str
    email: str
    organization_id: str

# ✅ CORRECT CreateNode pattern
workflow = WorkflowBuilder()
workflow.add_node("UserCreateNode", "create_user", {
    "id": "user-123",                  # Required: Primary key
    "name": "Alice",                   # Required: All fields
    "email": "alice@example.com",
    "organization_id": "org-456"
})

runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())

created_user = results["create_user"]
# Returns: {"id": "user-123", "name": "Alice", "email": "alice@example.com", ...}
```

#### UPDATE Operation

```python
# ✅ CORRECT UpdateNode pattern
workflow = WorkflowBuilder()
workflow.add_node("UserUpdateNode", "update_user", {
    "filter": {                        # Which record to update
        "id": "user-123"
    },
    "fields": {                        # What to change
        "name": "Alice Smith",
        "email": "alice.smith@example.com"
    }
    # Note: organization_id NOT included - not updating it
})

runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())

updated_user = results["update_user"]
# Returns: {"id": "user-123", "name": "Alice Smith", "email": "alice.smith@example.com", ...}
```

---

## Common Mistake #1: Flat Fields in UpdateNode

### ❌ WRONG - Using CreateNode pattern in UpdateNode

```python
# ❌ WRONG - Flat fields in UpdateNode
workflow.add_node("UserUpdateNode", "update_user", {
    "id": "user-123",           # ERROR: Not in 'filter' structure
    "name": "Alice Updated"     # ERROR: Not in 'fields' structure
})

# Error: "UPDATE request must contain 'filter' and 'fields'"
```

### ✅ CORRECT Fix

```python
# ✅ CORRECT - Nested filter + fields
workflow.add_node("UserUpdateNode", "update_user", {
    "filter": {"id": "user-123"},       # Identify record
    "fields": {"name": "Alice Updated"}  # Update fields
})
```

---

## Common Mistake #2: Nested Structure in CreateNode

### ❌ WRONG - Using UpdateNode pattern in CreateNode

```python
# ❌ WRONG - Nested structure in CreateNode
workflow.add_node("UserCreateNode", "create_user", {
    "filter": {"id": "user-123"},      # ERROR: No 'filter' in CREATE
    "fields": {                         # ERROR: No 'fields' in CREATE
        "name": "Alice",
        "email": "alice@example.com"
    }
})

# Error: "Field 'name' is required for CREATE operations"
```

### ✅ CORRECT Fix

```python
# ✅ CORRECT - Flat fields
workflow.add_node("UserCreateNode", "create_user", {
    "id": "user-123",                  # Flat, not nested
    "name": "Alice",                   # Flat, not nested
    "email": "alice@example.com"       # Flat, not nested
})
```

---

## Common Mistake #3: Missing Primary Key

### ❌ WRONG - No `id` in CreateNode

```python
# ❌ WRONG - Missing required 'id' field
workflow.add_node("UserCreateNode", "create_user", {
    "name": "Alice",
    "email": "alice@example.com"
    # ERROR: Missing 'id' field
})

# Error: "Field 'id' is required for CREATE operations"
```

### ✅ CORRECT Fix

```python
import uuid

# ✅ CORRECT - Always provide 'id'
workflow.add_node("UserCreateNode", "create_user", {
    "id": str(uuid.uuid4()),          # Generate UUID for id
    "name": "Alice",
    "email": "alice@example.com"
})
```

**Why**: DataFlow doesn't auto-generate IDs - you must provide them. See [Primary Keys Guide](primary-keys.md).

---

## Common Mistake #4: Including `id` in UpdateNode fields

### ❌ WRONG - Trying to update primary key

```python
# ❌ WRONG - Primary key in 'fields'
workflow.add_node("UserUpdateNode", "update_user", {
    "filter": {"id": "user-123"},
    "fields": {
        "id": "user-456",              # ERROR: Can't change primary key
        "name": "Alice Updated"
    }
})

# Error: "Cannot update primary key 'id'"
```

### ✅ CORRECT Fix

```python
# ✅ CORRECT - Primary key only in 'filter'
workflow.add_node("UserUpdateNode", "update_user", {
    "filter": {"id": "user-123"},      # Identify record
    "fields": {
        "name": "Alice Updated"         # Update non-key fields only
    }
})
```

**Note**: To change a primary key, DELETE the old record and CREATE a new one.

---

## Complete Workflow Example

### Full CRUD Workflow

```python
from dataflow import DataFlow
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime import LocalRuntime
import uuid

db = DataFlow(":memory:")

@db.model
class User:
    id: str
    name: str
    email: str
    organization_id: str

workflow = WorkflowBuilder()

# 1. CREATE - Flat fields
workflow.add_node("UserCreateNode", "create_user", {
    "id": str(uuid.uuid4()),
    "name": "Alice",
    "email": "alice@example.com",
    "organization_id": "org-123"
})

# 2. READ - Single field (id)
workflow.add_node("UserReadNode", "read_user", {
    "id": "{{create_user.id}}"  # Connection from CREATE result
})

# 3. UPDATE - Nested filter + fields
workflow.add_node("UserUpdateNode", "update_user", {
    "filter": {"id": "{{create_user.id}}"},
    "fields": {
        "name": "Alice Smith",
        "email": "alice.smith@example.com"
    }
})

# 4. LIST - Filters structure
workflow.add_node("UserListNode", "list_users", {
    "filters": {"organization_id": "org-123"},
    "limit": 10,
    "offset": 0
})

# 5. DELETE - Single field (id)
workflow.add_node("UserDeleteNode", "delete_user", {
    "id": "{{create_user.id}}"
})

runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())

print(f"Created: {results['create_user']}")
print(f"Read: {results['read_user']}")
print(f"Updated: {results['update_user']}")
print(f"Listed: {results['list_users']}")
print(f"Deleted: {results['delete_user']}")
```

---

## Parameter Structure Reference

### CreateNode Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `id` | str | **YES** | Primary key (you generate) |
| `<field_name>` | Any | **YES** | All model fields at top level |

**Example**:
```python
{
    "id": "user-123",
    "name": "Alice",
    "email": "alice@example.com",
    "organization_id": "org-456",
    "is_active": True
}
```

### UpdateNode Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `filter` | dict | **YES** | Which record(s) to update |
| `filter.id` | str | **YES** | Primary key to match |
| `fields` | dict | **YES** | Fields to update |

**Example**:
```python
{
    "filter": {
        "id": "user-123"
    },
    "fields": {
        "name": "Alice Updated",
        "is_active": False
    }
}
```

---

## Filtering in UpdateNode

### Update by Primary Key (Most Common)

```python
# ✅ Update single record by id
workflow.add_node("UserUpdateNode", "update_user", {
    "filter": {"id": "user-123"},
    "fields": {"name": "Alice Updated"}
})
```

### Update by Other Fields (Bulk Update)

```python
# ⚠️ WARNING: Updates ALL matching records
workflow.add_node("UserUpdateNode", "update_users_bulk", {
    "filter": {"organization_id": "org-123", "is_active": False},
    "fields": {"is_active": True}
})
# Updates ALL inactive users in org-123
```

**Best Practice**: Always use `id` in filter for single-record updates to avoid accidental bulk updates.

---

## Comparison with SQL

### CreateNode ≈ INSERT

```sql
-- SQL INSERT
INSERT INTO users (id, name, email, organization_id)
VALUES ('user-123', 'Alice', 'alice@example.com', 'org-456');

-- DataFlow CreateNode (equivalent)
{
    "id": "user-123",
    "name": "Alice",
    "email": "alice@example.com",
    "organization_id": "org-456"
}
```

### UpdateNode ≈ UPDATE WHERE

```sql
-- SQL UPDATE
UPDATE users
SET name = 'Alice Updated', email = 'alice.new@example.com'
WHERE id = 'user-123';

-- DataFlow UpdateNode (equivalent)
{
    "filter": {"id": "user-123"},
    "fields": {
        "name": "Alice Updated",
        "email": "alice.new@example.com"
    }
}
```

---

## Comparison with ORMs

### SQLAlchemy Pattern

```python
# SQLAlchemy CREATE (add + commit)
user = User(id="user-123", name="Alice", email="alice@example.com")
session.add(user)
session.commit()

# DataFlow CreateNode (equivalent)
workflow.add_node("UserCreateNode", "create", {
    "id": "user-123",
    "name": "Alice",
    "email": "alice@example.com"
})
```

```python
# SQLAlchemy UPDATE (query + modify + commit)
user = session.query(User).filter_by(id="user-123").first()
user.name = "Alice Updated"
session.commit()

# DataFlow UpdateNode (equivalent)
workflow.add_node("UserUpdateNode", "update", {
    "filter": {"id": "user-123"},
    "fields": {"name": "Alice Updated"}
})
```

### Django ORM Pattern

```python
# Django CREATE
User.objects.create(id="user-123", name="Alice", email="alice@example.com")

# DataFlow CreateNode (equivalent)
workflow.add_node("UserCreateNode", "create", {
    "id": "user-123",
    "name": "Alice",
    "email": "alice@example.com"
})
```

```python
# Django UPDATE
User.objects.filter(id="user-123").update(name="Alice Updated")

# DataFlow UpdateNode (equivalent)
workflow.add_node("UserUpdateNode", "update", {
    "filter": {"id": "user-123"},
    "fields": {"name": "Alice Updated"}
})
```

---

## Bulk Operations

### BulkCreateNode: List of Flat Fields

```python
# ✅ CORRECT - List of flat field dicts
workflow.add_node("UserBulkCreateNode", "bulk_create_users", {
    "records": [
        {"id": "user-1", "name": "Alice", "email": "alice@example.com"},
        {"id": "user-2", "name": "Bob", "email": "bob@example.com"},
        {"id": "user-3", "name": "Charlie", "email": "charlie@example.com"}
    ]
})
```

### BulkUpdateNode: List of filter + fields

```python
# ✅ CORRECT - List of filter/fields dicts
workflow.add_node("UserBulkUpdateNode", "bulk_update_users", {
    "records": [
        {
            "filter": {"id": "user-1"},
            "fields": {"name": "Alice Updated"}
        },
        {
            "filter": {"id": "user-2"},
            "fields": {"name": "Bob Updated"}
        }
    ]
})
```

**Pattern**: BulkCreateNode = list of CreateNode params, BulkUpdateNode = list of UpdateNode params.

---

## Connections Between Nodes

### CREATE → UPDATE Pattern

```python
# 1. CREATE returns record with id
workflow.add_node("UserCreateNode", "create", {
    "id": "user-123",
    "name": "Alice",
    "email": "alice@example.com"
})

# 2. UPDATE uses id from CREATE result
workflow.add_node("UserUpdateNode", "update", {
    "filter": {"id": "{{create.id}}"},  # Connection from CREATE
    "fields": {"name": "Alice Updated"}
})

# Connection automatically established via {{create.id}}
```

### READ → UPDATE Pattern

```python
# 1. READ returns record
workflow.add_node("UserReadNode", "read", {
    "id": "user-123"
})

# 2. UPDATE modifies fields
workflow.add_node("UserUpdateNode", "update", {
    "filter": {"id": "{{read.id}}"},   # Connection from READ
    "fields": {"name": "{{read.name}} (verified)"}
})
```

---

## Troubleshooting

### Error: "UPDATE request must contain 'filter' and 'fields'"

**Cause**: Using flat field structure in UpdateNode

**Fix**:
```python
# ❌ WRONG
{"id": "user-123", "name": "Alice"}

# ✅ CORRECT
{"filter": {"id": "user-123"}, "fields": {"name": "Alice"}}
```

### Error: "Field 'id' is required for CREATE operations"

**Cause**: Missing `id` field in CreateNode

**Fix**:
```python
import uuid

# ❌ WRONG
{"name": "Alice", "email": "alice@example.com"}

# ✅ CORRECT
{"id": str(uuid.uuid4()), "name": "Alice", "email": "alice@example.com"}
```

### Error: "Cannot update primary key 'id'"

**Cause**: Including `id` in UpdateNode `fields`

**Fix**:
```python
# ❌ WRONG
{"filter": {"id": "user-123"}, "fields": {"id": "user-456", "name": "Alice"}}

# ✅ CORRECT
{"filter": {"id": "user-123"}, "fields": {"name": "Alice"}}
```

### Error: "Extra field 'filter' in CREATE"

**Cause**: Using UpdateNode pattern in CreateNode

**Fix**:
```python
# ❌ WRONG
{"filter": {...}, "fields": {...}}

# ✅ CORRECT
{"id": "user-123", "name": "Alice", ...}
```

---

## Best Practices

### 1. Always Use `id` in UpdateNode Filter

```python
# ✅ BEST PRACTICE - Explicit id filter
workflow.add_node("UserUpdateNode", "update", {
    "filter": {"id": "user-123"},     # Prevents accidental bulk updates
    "fields": {"name": "Alice"}
})

# ⚠️ RISKY - May update multiple records
workflow.add_node("UserUpdateNode", "update", {
    "filter": {"organization_id": "org-123"},  # Updates ALL users in org
    "fields": {"is_active": False}
})
```

### 2. Generate UUIDs for CreateNode

```python
import uuid

# ✅ BEST PRACTICE - Use UUIDs
workflow.add_node("UserCreateNode", "create", {
    "id": str(uuid.uuid4()),          # Guaranteed unique
    "name": "Alice"
})
```

### 3. Update Only Changed Fields

```python
# ✅ BEST PRACTICE - Update only what changed
workflow.add_node("UserUpdateNode", "update", {
    "filter": {"id": "user-123"},
    "fields": {"name": "Alice Updated"}  # Only updating name
})

# ❌ INEFFICIENT - Updating all fields
workflow.add_node("UserUpdateNode", "update", {
    "filter": {"id": "user-123"},
    "fields": {
        "name": "Alice Updated",
        "email": "alice@example.com",     # Unchanged - wasteful
        "organization_id": "org-123"       # Unchanged - wasteful
    }
})
```

### 4. Use Descriptive Node IDs

```python
# ✅ BEST PRACTICE - Clear node IDs
workflow.add_node("UserCreateNode", "create_new_user", {...})
workflow.add_node("UserUpdateNode", "update_user_profile", {...})

# ❌ UNCLEAR - Generic IDs
workflow.add_node("UserCreateNode", "node1", {...})
workflow.add_node("UserUpdateNode", "node2", {...})
```

---

## Quick Decision Tree

**Q: Are you creating a NEW record?**
→ YES: Use **CreateNode** with **flat fields** + **id** required

**Q: Are you modifying an EXISTING record?**
→ YES: Use **UpdateNode** with **filter + fields** structure

**Q: Updating multiple records at once?**
→ YES: Use **BulkUpdateNode** with list of **filter + fields**

**Q: Creating multiple records at once?**
→ YES: Use **BulkCreateNode** with list of **flat fields**

---

## Related Guides

- [Primary Keys Guide](primary-keys.md) - Why `id` is required and how to use it
- [Auto-Managed Fields Guide](auto-managed-fields.md) - Don't include `created_at`, `updated_at`
- [Common Patterns Guide](common-patterns.md) - Best practices for CRUD workflows
- [Error Cheat Sheet](cheat-sheet-errors.md) - Quick fixes for common errors
- [FAQ](../FAQ.md) - Questions 9-12 cover CreateNode vs UpdateNode

---

## Summary

| Operation | Node | Parameter Structure | Primary Key |
|-----------|------|---------------------|-------------|
| **Create** | CreateNode | **Flat fields** | `id` in top-level data |
| **Update** | UpdateNode | **filter + fields** | `id` in filter |
| **Bulk Create** | BulkCreateNode | List of flat fields | `id` in each record |
| **Bulk Update** | BulkUpdateNode | List of filter + fields | `id` in each filter |

**Remember**: CreateNode = flat, UpdateNode = nested. Getting this right eliminates 70%+ of DataFlow errors.

# DataFlow Common Mistakes & Troubleshooting

This guide covers the most common mistakes developers make with DataFlow and how to fix them quickly. Following these patterns can reduce debugging time from 4+ hours to less than 10 minutes.

## 🚨 #1 MOST COMMON MISTAKE: Auto-Managed Timestamp Fields (DF-104)

**This error occurs in almost EVERY new DataFlow project!**

### Error Message
```
DatabaseError: multiple assignments to same column "updated_at"
```

### The Problem
DataFlow automatically manages `created_at` and `updated_at` fields. When you manually set these fields AND DataFlow also sets them, PostgreSQL throws a "multiple assignments" error.

### Wrong Code (Every New Project Makes This Mistake)

```python
# ❌ WRONG - Manually setting updated_at in update method
async def update(self, id: str, data: dict) -> dict:
    now = datetime.now(UTC).isoformat()
    data["updated_at"] = now  # ❌ CAUSES DF-104!

    workflow = WorkflowBuilder()
    workflow.add_node("ModelUpdateNode", "update", {
        "filter": {"id": id},
        "fields": data,  # Error: multiple assignments to updated_at
    })
```

### Correct Code

```python
# ✅ CORRECT - Let DataFlow handle timestamps
async def update(self, id: str, data: dict) -> dict:
    # NOTE: Do NOT set updated_at - DataFlow manages it automatically
    # Strip any auto-managed fields if present
    data.pop("updated_at", None)
    data.pop("created_at", None)

    workflow = WorkflowBuilder()
    workflow.add_node("ModelUpdateNode", "update", {
        "filter": {"id": id},
        "fields": data,  # DataFlow sets updated_at automatically
    })
```

### Auto-Managed Fields (NEVER Include)

| Field | When Set | Impact of Manual Setting |
|-------|----------|--------------------------|
| `created_at` | Automatically on record creation | DF-104 error |
| `updated_at` | Automatically on every update | DF-104 error |

### Affected Operations
- ❌ CreateNode - Never include `created_at`
- ❌ UpdateNode - Never include `updated_at` or `created_at`
- ❌ BulkCreateNode - Never include `created_at`
- ❌ BulkUpdateNode - Never include `updated_at` or `created_at`

### Why This Happens
Developers instinctively add timestamp management because that's how other frameworks work:
- Django ORM requires `auto_now=True` configuration
- SQLAlchemy requires `onupdate=datetime.utcnow`
- Raw SQL requires explicit UPDATE SET

**DataFlow is different**: It automatically handles timestamps with NO configuration needed.

---

## ⚠️ Critical Bug Fix Alert (v0.6.2-v0.6.3)

### Filter Operators Bug (FIXED in v0.6.2)

**Symptom:**
```python
# Expected: Returns 2 users (active only)
# Actual (v0.6.1 and earlier): Returns ALL 3 users
workflow.add_node("UserListNode", "query", {
    "filter": {"status": {"$ne": "inactive"}}
})
```

**Cause:** Python truthiness bug - `if filter_dict:` treated empty dict `{}` as False

**Fix:** Upgrade to v0.6.2+
```bash
pip install --upgrade kailash-dataflow>=0.6.3
```

**Affected Operators:** $ne, $nin, $in, $not, and all comparison operators were broken in v0.6.1 and earlier.

**Affected Versions:**
- ❌ v0.5.4 - v0.6.1: Broken
- ✅ v0.6.2+: All operators work correctly

---

## Table of Contents

0. [🚨 #1 MOST COMMON: Auto-Managed Timestamp Fields (DF-104)](#-1-most-common-mistake-auto-managed-timestamp-fields-df-104) - **READ FIRST!**
1. [CreateNode: Wrapping Fields in 'data'](#error-1-createnode-wrapping-fields-in-data)
2. [UpdateNode: Using CreateNode Pattern](#error-2-updatenode-using-createnode-pattern)
3. [UpdateNode: Missing Filter Parameter](#error-3-updatenode-missing-filter-parameter)
4. [UpdateNode: Empty Filter (Updates ALL Records)](#error-4-updatenode-empty-filter)
5. [Auto-Managed Fields: Manual Override Attempts](#error-5-auto-managed-fields)
6. [Wrong Node Naming Pattern](#error-6-wrong-node-naming-pattern)
7. [Missing db_instance Parameters](#error-7-missing-db-instance-parameters)

---

## Error 1: CreateNode Wrapping Fields in 'data'

### Symptom

```
ValidationError: Node 'create_user' missing required inputs: ['email', 'name', 'age', ...]
```

### Cause

You nested parameters under `data` or `fields` instead of providing them flat. DataFlow treats `"data"` as a **field name**, not a wrapper.

### Wrong Code

```python
# ❌ WRONG - 'data' is treated as a field name
workflow.add_node("UserCreateNode", "create", {
    "data": {  # This creates a FIELD named "data"
        "name": "Alice",
        "email": "alice@example.com"
    }
})
```

### Correct Code

```python
# ✅ CORRECT - Fields at top level
workflow.add_node("UserCreateNode", "create", {
    "name": "Alice",            # Individual field 1
    "email": "alice@example.com"  # Individual field 2
})
```

### Explanation

CreateNode expects **FLAT individual field parameters at the top level**, NOT nested under 'data', 'fields', or any other wrapper. Each model field becomes a direct parameter to the node.

### See Also

- [CRUD Operations Guide - CreateNode](./crud.md#create-operations)
- [Parameter Patterns Reference](./crud.md#critical-createnode-vs-updatenode-pattern-differences)

---

## Error 2: UpdateNode Using CreateNode Pattern

### Symptom

```
DatabaseError: column "user_id" of relation "users" does not exist
```

OR

```
NodeValidationError: UpdateNode requires 'filter' and 'fields' parameters
```

### Cause

You used individual field parameters (like CreateNode) instead of the nested `filter` + `fields` structure required by UpdateNode.

### Wrong Code

```python
# ❌ WRONG - Flat fields (CreateNode pattern)
workflow.add_node("UserUpdateNode", "update", {
    "id": 1,          # This looks like CreateNode!
    "name": "Alice Updated",
    "age": 31
})
```

### Correct Code

```python
# ✅ CORRECT - Nested filter + fields
workflow.add_node("UserUpdateNode", "update", {
    "filter": {"id": 1},  # Which record(s) to update
    "fields": {            # What to change
        "name": "Alice Updated",
        "age": 31
    }
})
```

### Explanation

**UpdateNode uses a COMPLETELY DIFFERENT pattern than CreateNode.**

- **CreateNode**: Flat fields (you're creating a NEW record)
- **UpdateNode**: Nested `filter` + `fields` (you need to specify WHICH records to update AND WHAT to change)

This is the **#1 source of debugging time** for new DataFlow developers.

### See Also

- [CRUD Operations Guide - UpdateNode](./crud.md#update-operations)
- [Parameter Pattern Comparison](./crud.md#quick-comparison-table)

---

## Error 3: UpdateNode Missing Filter Parameter

### Symptom

```
ValidationError: UpdateNode missing 'filter' parameter
```

OR

```
SafetyWarning: Empty filter will update ALL records in table
```

### Cause

You omitted the `filter` parameter entirely, or provided an empty filter `{}`.

### Wrong Code

```python
# ❌ WRONG - Missing filter parameter
workflow.add_node("UserUpdateNode", "update", {
    "fields": {"name": "Alice"}  # Where's the filter?
})
```

### Correct Code

```python
# ✅ CORRECT - Always provide filter
workflow.add_node("UserUpdateNode", "update", {
    "filter": {"id": 1},  # Which record(s)
    "fields": {"name": "Alice"}
})
```

### Safety Warning

⚠️ **CRITICAL**: Missing or empty filters will update **ALL records** in the table!

```python
# ⚠️ DANGEROUS - Updates EVERY record in table
workflow.add_node("UserUpdateNode", "update", {
    "filter": {},  # Empty filter = ALL records!
    "fields": {"status": "deleted"}
})
```

If you truly need to update all records, use `BulkUpdateNode` with explicit confirmation:

```python
# ✅ CORRECT - Explicit bulk update
workflow.add_node("UserBulkUpdateNode", "update_all", {
    "filter": {},  # Intentionally ALL records
    "fields": {"status": "verified"},
    "confirm_all": True  # Explicit confirmation required
})
```

### See Also

- [Update Operations - Safety](./crud.md#conditional-updates)

---

## Error 4: UpdateNode Empty Filter

### Symptom

```
SafetyWarning: Empty filter will update ALL records. Set 'confirm_all=True' to proceed.
```

### Cause

Provided an empty `filter: {}` which matches ALL records.

### Wrong Code

```python
# ⚠️ DANGEROUS - Updates every record
workflow.add_node("UserUpdateNode", "update", {
    "filter": {},  # This matches EVERYTHING
    "fields": {"active": False}
})
```

### Correct Code

```python
# ✅ Option 1: Specific filter
workflow.add_node("UserUpdateNode", "update", {
    "filter": {"id": 1},  # Only this record
    "fields": {"active": False}
})

# ✅ Option 2: Multiple conditions
workflow.add_node("UserUpdateNode", "update", {
    "filter": {"active": True, "age": {"$gt": 65}},
    "fields": {"status": "retired"}
})

# ✅ Option 3: Bulk update with confirmation
workflow.add_node("UserBulkUpdateNode", "update_all", {
    "filter": {},  # Intentionally ALL
    "fields": {"verified": True},
    "confirm_all": True  # Required for empty filter
})
```

### Explanation

Empty filters are **almost always a mistake**. DataFlow requires explicit confirmation to prevent accidentally updating all records.

---

## Error 5: Auto-Managed Fields

### Symptom

```
DatabaseError: multiple assignments to same column "updated_at"
```

OR

```
FieldConflictError: Field 'created_at' is auto-managed by DataFlow
```

### Cause

You manually set `created_at` or `updated_at` in your parameters, but DataFlow manages these automatically.

### Wrong Code

```python
# ❌ WRONG - Manually setting auto-managed fields
from datetime import datetime

workflow.add_node("UserUpdateNode", "update", {
    "filter": {"id": 1},
    "fields": {
        "name": "Alice",
        "updated_at": datetime.now()  # Don't do this!
    }
})
```

### Correct Code

```python
# ✅ CORRECT - Let DataFlow handle updated_at
workflow.add_node("UserUpdateNode", "update", {
    "filter": {"id": 1},
    "fields": {
        "name": "Alice"
        # updated_at is set automatically
    }
})
```

### Auto-Managed Fields List

DataFlow automatically manages these fields:

- `created_at`: Set once on record creation
- `updated_at`: Updated on every modification

**Do NOT include them in CreateNode or UpdateNode parameters.**

### Explanation

DataFlow ensures these timestamp fields are always accurate by managing them automatically. Manual overrides cause database conflicts.

---

## Error 6: Wrong Node Naming Pattern

### Symptom

```
NodeNotFoundError: Node 'User_Create' not found in registry
```

### Cause

Used old naming pattern (`Model_Operation`) instead of current pattern (`ModelOperationNode`).

### Wrong Code

```python
# ❌ WRONG - Old naming pattern (DataFlow <0.6.0)
workflow.add_node("User_Create", "create", {...})
workflow.add_node("User_List", "list", {...})
```

### Correct Code

```python
# ✅ CORRECT - Current naming pattern (DataFlow 0.6.0+)
workflow.add_node("UserCreateNode", "create", {...})
workflow.add_node("UserListNode", "list", {...})
```

### Naming Pattern Reference

| Operation | Node Name Pattern | Example |
|-----------|------------------|---------|
| Create | `{Model}CreateNode` | `UserCreateNode` |
| Read | `{Model}ReadNode` | `UserReadNode` |
| Update | `{Model}UpdateNode` | `UserUpdateNode` |
| Delete | `{Model}DeleteNode` | `UserDeleteNode` |
| List | `{Model}ListNode` | `UserListNode` |
| Bulk Create | `{Model}BulkCreateNode` | `UserBulkCreateNode` |
| Bulk Update | `{Model}BulkUpdateNode` | `UserBulkUpdateNode` |
| Bulk Delete | `{Model}BulkDeleteNode` | `UserBulkDeleteNode` |
| Bulk Upsert | `{Model}BulkUpsertNode` | `UserBulkUpsertNode` |

### Migration Guide

DataFlow 0.6.0 changed naming from `Model_Operation` to `ModelOperationNode` for consistency.

**Better Error Message Coming**: Future versions will suggest the correct node name:

```
NodeNotFoundError: Node 'User_Create' not found.
Did you mean 'UserCreateNode'? (DataFlow 0.6.0+ uses ModelOperationNode pattern)
```

---

## Error 7: Missing db_instance Parameters

### Symptom

```
ValidationError: Required parameters missing: db_instance, model_name
```

### Cause

Omitted required `db_instance` and `model_name` parameters when using DataFlow nodes outside standard workflows.

### Wrong Code

```python
# ❌ WRONG - Missing required parameters
workflow.add_node("UserCreateNode", "create", {
    "name": "Alice",
    "email": "alice@example.com"
    # Missing db_instance and model_name!
})
```

### Correct Code

```python
# ✅ CORRECT - Include db_instance and model_name
workflow.add_node("UserCreateNode", "create", {
    "db_instance": "my_db",  # DataFlow instance name
    "model_name": "User",    # Model class name
    "name": "Alice",
    "email": "alice@example.com"
})
```

### When This Happens

This typically occurs when:
- Using DataFlow nodes in custom workflows
- Working with multiple DataFlow instances
- Manual node instantiation (advanced use cases)

For standard DataFlow usage with the `@db.model` decorator, these parameters are usually handled automatically.

---

## Quick Troubleshooting Checklist

When you encounter an error, check:

- [ ] **CreateNode**: Are fields flat (not nested under 'data')?
- [ ] **UpdateNode**: Does it have `filter` AND `fields` (not flat fields)?
- [ ] **UpdateNode**: Is the filter non-empty (not `{}`)?
- [ ] **Auto-managed fields**: Did you remove `created_at`/`updated_at`?
- [ ] **Node names**: Using `ModelOperationNode` pattern (not `Model_Operation`)?
- [ ] **Workflow build**: Called `.build()` before `runtime.execute()`?
- [ ] **Connections**: Using connections (not template syntax `${}`)?

---

## Pattern Comparison Reference

### CreateNode vs UpdateNode

```python
# ==========================================
# CRITICAL: Different Patterns
# ==========================================

# CreateNode: FLAT Individual Fields
workflow.add_node("UserCreateNode", "create", {
    "name": "Alice",      # ← Field 1
    "email": "...",       # ← Field 2
    "age": 30             # ← Field 3
})

# UpdateNode: NESTED filter + fields
workflow.add_node("UserUpdateNode", "update", {
    "filter": {"id": 1},  # ← Which records
    "fields": {            # ← What to change
        "name": "Alice Updated",
        "age": 31
    }
})
```

---

## See Also

- [CRUD Operations Guide](./crud.md)
- [Parameter Patterns](./crud.md#critical-createnode-vs-updatenode-pattern-differences)
- [Bulk Operations](./bulk-operations.md)
- [Query Patterns](./query-patterns.md)

---

**Last Updated**: Phase 1 Implementation (v0.6.1)
**Time Savings**: Following these patterns reduces debugging from 4+ hours to <10 minutes

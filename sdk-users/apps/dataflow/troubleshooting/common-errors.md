# DataFlow Common Errors - Quick Reference

Quick-reference troubleshooting guide for the most common DataFlow errors. For comprehensive error handling documentation, see [error-handling.md](../guides/error-handling.md).

---

## 🚨 #1 MOST COMMON ERROR: DF-104 Auto-Managed Fields

**This error occurs in almost EVERY new DataFlow project!**

```
DatabaseError: multiple assignments to same column "updated_at"
```

**Problem**: You're manually setting `created_at` or `updated_at`, but DataFlow manages these automatically.

**Quick Fix**: Remove all manual timestamp assignments:
```python
# ❌ WRONG
data["updated_at"] = datetime.now()  # Remove this line!

# ✅ CORRECT
data.pop("updated_at", None)  # Strip auto-managed fields
data.pop("created_at", None)
```

**See**: [Gotchas Guide - Auto-Managed Fields](../docs/development/gotchas.md#-1-most-common-mistake-auto-managed-timestamp-fields-df-104)

---

## 📋 Error Code Format

DataFlow error codes follow the pattern `DF-XYY`:
- **DF**: DataFlow prefix
- **X**: Category (1=Parameter, 2=Connection, 3=Migration, 4=Configuration, 5=Runtime, 6=Model, 7=Node, 8=Workflow, 9=Validation)
- **YY**: Specific error within category

---

## 🔥 Top 20 Most Common Errors

### Parameter Errors (DF-101 to DF-110)

| Error Code | What It Means | Quick Fix |
|------------|---------------|-----------|
| **DF-101** | Missing required parameter | Add connection or provide parameter directly in node config |
| **DF-102** | Parameter type mismatch | Pass dict not string; ensure type matches expectation |
| **DF-104** | Auto-managed field conflict | Remove `created_at`/`updated_at` from data |
| **DF-105** | Missing primary key 'id' | Always include `id` field in create operations |
| **DF-106** | Wrong primary key name | Use `id` not `user_id` or `model_id` |
| **DF-107** | UpdateNode pattern mismatch | Use `{"filter": {...}, "fields": {...}}` not flat fields |
| **DF-108** | List vs single value mismatch | CreateNode expects dict, BulkCreateNode expects list |

---

### Connection Errors (DF-201 to DF-210)

| Error Code | What It Means | Quick Fix |
|------------|---------------|-----------|
| **DF-201** | Invalid connection | Verify source and target nodes exist before connecting |
| **DF-202** | Missing source output | Check source node produces the output parameter |
| **DF-205** | Dot notation invalid | Connect full result and handle null checks in code |

---

### Migration Errors (DF-301 to DF-308)

| Error Code | What It Means | Quick Fix |
|------------|---------------|-----------|
| **DF-301** | Migration failure | Enable `auto_migrate=True` or check database permissions |
| **DF-302** | Schema mismatch | Enable `auto_migrate=True` to sync schema changes |
| **DF-304** | Table already exists | Use `existing_schema_mode=True` for existing databases |

---

### Runtime Errors (DF-501 to DF-508)

| Error Code | What It Means | Quick Fix |
|------------|---------------|-----------|
| **DF-501** | Sync method in async context | Use `create_tables_async()` not `create_tables()` in FastAPI/pytest |
| **DF-502** | Database operation failed | Check constraints, foreign keys, and data validity |
| **DF-504** | Query execution failed | Enable `debug=True` to see detailed error messages |

---

### Workflow Errors (DF-801 to DF-805)

| Error Code | What It Means | Quick Fix |
|------------|---------------|-----------|
| **DF-803** | Missing workflow build | Always call `.build()`: `runtime.execute(workflow.build())` |
| **DF-804** | Disconnected workflow nodes | Add connections between all nodes or provide data directly |

---

### Validation Errors (DF-901 to DF-910)

| Error Code | What It Means | Quick Fix |
|------------|---------------|-----------|
| **DF-901** | CreateNode requires flat fields | Use `{"id": "123", "name": "Alice"}` not nested structure |
| **DF-902** | UpdateNode requires filter + fields | Use `{"filter": {...}, "fields": {...}}` structure |
| **DF-905** | Primary key in UpdateNode fields | Only put `id` in `filter`, not in `fields` |
| **DF-906** | BulkCreateNode requires list | Pass `[{...}, {...}]` not single dict |

---

## 🔧 Common Error Patterns

### Pattern 1: Wrong Node Pattern (DF-901, DF-902, DF-107)

**Issue**: Mixing CreateNode and UpdateNode parameter patterns.

**Error Indicators**:
- "CreateNode requires flat fields"
- "UpdateNode requires filter + fields"
- "UpdateNode pattern mismatch"

**Before** ❌:
```python
# CreateNode with nested structure (WRONG)
workflow.add_node("UserCreateNode", "create", {
    "filter": {"id": "user-123"},
    "fields": {"name": "Alice"}
})

# UpdateNode with flat structure (WRONG)
workflow.add_node("UserUpdateNode", "update", {
    "id": "user-123",
    "name": "Alice"
})
```

**After** ✅:
```python
# CreateNode: Flat fields
workflow.add_node("UserCreateNode", "create", {
    "id": "user-123",
    "name": "Alice",
    "email": "alice@example.com"
})

# UpdateNode: filter + fields
workflow.add_node("UserUpdateNode", "update", {
    "filter": {"id": "user-123"},
    "fields": {"name": "Alice Updated"}
})
```

---

### Pattern 2: Auto-Managed Fields (DF-104)

**Issue**: Including `created_at` or `updated_at` fields manually.

**Error Indicators**:
- "Auto-managed field conflict"
- "created_at provided but auto-managed"

**Before** ❌:
```python
from datetime import datetime

workflow.add_node("UserCreateNode", "create", {
    "id": "user-123",
    "name": "Alice",
    "created_at": datetime.now(),  # ❌ Remove this
    "updated_at": datetime.now()   # ❌ Remove this
})
```

**After** ✅:
```python
workflow.add_node("UserCreateNode", "create", {
    "id": "user-123",
    "name": "Alice",
    "email": "alice@example.com"
    # created_at and updated_at added automatically
})
```

---

### Pattern 3: Primary Key Naming (DF-106)

**Issue**: Using `user_id`, `model_id`, or other names instead of `id`.

**Error Indicators**:
- "Wrong primary key name"
- "Primary key must be 'id'"

**Before** ❌:
```python
@db.model
class User:
    user_id: str  # ❌ Wrong!
    name: str
```

**After** ✅:
```python
@db.model
class User:
    id: str  # ✅ Required name
    name: str
```

---

### Pattern 4: Missing .build() (DF-803)

**Issue**: Forgetting to call `.build()` before executing workflow.

**Error Indicators**:
- "Missing workflow build"
- "Passing WorkflowBuilder directly to runtime"

**Before** ❌:
```python
workflow = WorkflowBuilder()
workflow.add_node("UserCreateNode", "create", {})
runtime.execute(workflow)  # ❌ Missing .build()
```

**After** ✅:
```python
workflow = WorkflowBuilder()
workflow.add_node("UserCreateNode", "create", {})
runtime.execute(workflow.build())  # ✅ .build() required
```

---

### Pattern 5: BulkNode vs Single Node (DF-108, DF-906)

**Issue**: Using wrong data structure for bulk operations.

**Error Indicators**:
- "Expected list, got dict"
- "BulkCreateNode requires list"

**Before** ❌:
```python
# BulkCreateNode with single dict (WRONG)
workflow.add_node("UserBulkCreateNode", "bulk", {
    "records": {"id": "user-1", "name": "Alice"}  # ❌ Should be list
})

# CreateNode with list (WRONG)
workflow.add_node("UserCreateNode", "create", {
    "data": [{"id": "user-1", "name": "Alice"}]  # ❌ Should be dict
})
```

**After** ✅:
```python
# CreateNode: Single dict
workflow.add_node("UserCreateNode", "create", {
    "id": "user-1",
    "name": "Alice"
})

# BulkCreateNode: List of dicts
workflow.add_node("UserBulkCreateNode", "bulk", {
    "records": [
        {"id": "user-1", "name": "Alice"},
        {"id": "user-2", "name": "Bob"}
    ]
})
```

---

### Pattern 6: Sync Methods in Async Context (DF-501)

**Issue**: Calling sync methods (`create_tables()`, `close()`) from async functions.

**Error Indicators**:
- "Sync Method in Async Context"
- "Use create_tables_async() instead"
- "DF-501"

**Before** ❌:
```python
# In FastAPI or pytest-asyncio
@app.on_event("startup")
async def startup():
    db.create_tables()  # ❌ RuntimeError: DF-501

@pytest.fixture
async def db_fixture():
    db = DataFlow(":memory:")
    db.create_tables()  # ❌ RuntimeError: DF-501
    yield db
    db.close()  # ❌ Also fails!
```

**After** ✅:
```python
# Use async methods in async contexts
@app.on_event("startup")
async def startup():
    await db.create_tables_async()  # ✅ Works

# FastAPI lifespan pattern (recommended)
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.create_tables_async()
    yield
    await db.close_async()

app = FastAPI(lifespan=lifespan)

# pytest async fixtures
@pytest.fixture
async def db_fixture():
    db = DataFlow(":memory:")
    @db.model
    class User:
        id: str
        name: str
    await db.create_tables_async()
    yield db
    await db.close_async()
```

**Async Methods (v0.10.7+):**
| Sync Method | Async Method |
|-------------|--------------|
| `create_tables()` | `create_tables_async()` |
| `close()` | `close_async()` |
| `_ensure_migration_tables()` | `_ensure_migration_tables_async()` |

---

### Pattern 7: Missing Connection (DF-101)

**Issue**: Required parameter not provided and no connection established.

**Error Indicators**:
- "Missing required parameter: 'data'"
- "Parameter 'data' not found"

**Before** ❌:
```python
workflow = WorkflowBuilder()
workflow.add_node("InputNode", "input", {})
workflow.add_node("UserCreateNode", "create", {})  # ❌ No data!

runtime = LocalRuntime()
results, _ = runtime.execute(workflow.build())
```

**After** ✅:
```python
# Option 1: Add connection
workflow = WorkflowBuilder()
workflow.add_node("InputNode", "input", {})
workflow.add_node("UserCreateNode", "create", {})
workflow.add_connection("input", "data", "create", "data")  # ✅ Connect

# Option 2: Provide data directly
workflow = WorkflowBuilder()
workflow.add_node("UserCreateNode", "create", {
    "id": "user-123",
    "name": "Alice",
    "email": "alice@example.com"
})
```

---

### Pattern 8: Type Mismatch (DF-102)

**Issue**: Passing wrong type to parameter.

**Error Indicators**:
- "Expected dict, got str"
- "Parameter type mismatch"

**Before** ❌:
```python
# Passing string instead of dict
workflow.add_node("UserCreateNode", "create", {
    "data": "Alice"  # ❌ String, not dict
})

# Passing list to single-operation node
workflow.add_node("UserCreateNode", "create", {
    "data": [{"id": "user-1", "name": "Alice"}]  # ❌ List, not dict
})
```

**After** ✅:
```python
# Pass dict to CreateNode
workflow.add_node("UserCreateNode", "create", {
    "id": "user-123",
    "name": "Alice",
    "email": "alice@example.com"
})

# Pass list to BulkCreateNode
workflow.add_node("UserBulkCreateNode", "bulk", {
    "records": [
        {"id": "user-1", "name": "Alice"},
        {"id": "user-2", "name": "Bob"}
    ]
})
```

---

## 🎯 Quick Diagnosis Table

Use this table to quickly identify error categories:

| Symptom | Error Code Range | Common Causes |
|---------|------------------|---------------|
| "Missing parameter 'data'" | DF-101 | No connection, empty input, missing parameter |
| "Expected dict, got str" | DF-102 | Wrong parameter type |
| "created_at provided" | DF-104 | Including auto-managed fields |
| "Primary key 'id' required" | DF-105, DF-106 | Missing `id` field or wrong name |
| "UpdateNode requires filter" | DF-107, DF-902 | Using CreateNode pattern for UpdateNode |
| "Expected list" | DF-108, DF-906 | Wrong bulk operation data structure |
| "Connection invalid" | DF-201 | Node doesn't exist or wrong parameter name |
| "Migration failed" | DF-301 | Database permissions or `auto_migrate=False` |
| "Schema mismatch" | DF-302 | Model changed but schema not updated |
| "Sync Method in Async Context" | DF-501 | Use `create_tables_async()` in FastAPI/pytest |
| "Missing .build()" | DF-803 | Forgot to call `.build()` on workflow |

---

## 🔍 Error Reading Workflow

When you encounter an error, follow these steps:

### Step 1: Identify Error Code
```
❌ DataFlow Error [DF-107]
```
Error code tells you the category (1 = Parameter) and specific error (07 = UpdateNode pattern).

### Step 2: Check Context
```
📍 Context:
  node_id: update
  node_type: UserUpdateNode
```
Shows exactly which node failed and its type.

### Step 3: Match to Pattern
Look up error code in this guide to find the pattern and solution.

### Step 4: Apply Fix
Use the "After ✅" example code, adapting to your use case.

### Step 5: Verify
Run workflow again to confirm fix worked.

---

## 💡 Prevention Checklist

Avoid common errors by following these rules:

### Model Definition
- [ ] Primary key field named `id` (not `user_id`, `model_id`, etc.)
- [ ] Type annotations on all fields
- [ ] No `created_at` or `updated_at` fields (auto-managed)

### Node Usage
- [ ] CreateNode uses flat fields: `{"id": "123", "name": "Alice"}`
- [ ] UpdateNode uses filter + fields: `{"filter": {...}, "fields": {...}}`
- [ ] BulkCreateNode receives list: `{"records": [{...}, {...}]}`
- [ ] Always call `.build()`: `runtime.execute(workflow.build())`

### Connections
- [ ] Nodes added before connections
- [ ] Source output parameter exists
- [ ] Target input parameter exists
- [ ] Connection parameter names match node definitions

### Configuration
- [ ] `auto_migrate=True` for development
- [ ] `existing_schema_mode=True` for existing databases
- [ ] Database URL correct and accessible
- [ ] Proper database permissions (CREATE TABLE, ALTER TABLE)

---

## 📚 Additional Resources

### Comprehensive Guides
- **Error Handling Guide**: [guides/error-handling.md](../guides/error-handling.md)
- **CreateNode vs UpdateNode**: [guides/create-vs-update-nodes.md](../guides/create-vs-update-nodes.md)
- **Top 10 Errors**: [troubleshooting/top-10-errors.md](./top-10-errors.md)

### DataFlow Documentation
- **DataFlow CLAUDE.md**: [../../CLAUDE.md](../../CLAUDE.md)
- **Core Concepts**: [../../README.md](../../README.md)
- **API Reference**: [../../api-reference.md](../../api-reference.md)

### Error Catalog
- **Complete Error Definitions**: `apps/kailash-dataflow/src/dataflow/core/error_catalog.yaml`
- **60+ error patterns** with causes and solutions
- **All error codes** from DF-101 to DF-910

---

## 🎓 Error Code Categories

Quick reference for error code ranges:

| Category | Code Range | Count | Examples |
|----------|------------|-------|----------|
| **Parameter Errors** | DF-101 to DF-110 | 10 | Missing parameter, type mismatch, auto-managed fields |
| **Connection Errors** | DF-201 to DF-210 | 10 | Invalid connection, missing output, dot notation |
| **Migration Errors** | DF-301 to DF-308 | 8 | Migration failure, schema mismatch, constraints |
| **Configuration Errors** | DF-401 to DF-408 | 8 | Invalid config, database connection, SSL |
| **Runtime Errors** | DF-501 to DF-508 | 8 | Execution failure, timeout, resource exhaustion |
| **Model Errors** | DF-601 to DF-606 | 6 | Invalid model, duplicate name, unsupported type |
| **Node Errors** | DF-701 to DF-705 | 5 | Node not found, generation failed, validation |
| **Workflow Errors** | DF-801 to DF-805 | 5 | Invalid structure, missing .build(), disconnected |
| **Validation Errors** | DF-901 to DF-910 | 10 | CreateNode pattern, UpdateNode pattern, filters |

---

## 🚨 Critical Rules

**Never do these**:
- ❌ Use `user_id` or `model_id` as primary key (must be `id`)
- ❌ Include `created_at` or `updated_at` manually (auto-managed)
- ❌ Use CreateNode pattern for UpdateNode (wrong structure)
- ❌ Forget `.build()` call (workflow execution fails)
- ❌ Pass list to CreateNode or dict to BulkCreateNode (type mismatch)

**Always do these**:
- ✅ Primary key field named `id`
- ✅ CreateNode uses flat fields
- ✅ UpdateNode uses filter + fields
- ✅ Call `.build()` before execution
- ✅ Match data structure to node type (dict vs list)

---

## 🛠️ Debug Mode

Enable debug mode for detailed error messages during development:

```python
from kailash.runtime import LocalRuntime

# Enable debug mode for detailed errors
runtime = LocalRuntime(debug=True)

try:
    results, run_id = runtime.execute(workflow.build())
except Exception as e:
    print(f"Error details: {e}")
    # Full stack trace and context provided
```

---

## Summary

This quick reference covers the 20 most common DataFlow errors with:
- **Error codes** for quick identification
- **What it means** descriptions
- **Quick fixes** for immediate solutions
- **Before/After examples** showing correct patterns
- **Prevention checklist** to avoid errors
- **Links to comprehensive guides** for detailed explanations

**Time Saved**: 5-30 minutes per error with this quick-reference format.

For comprehensive error handling documentation, see [error-handling.md](../guides/error-handling.md).

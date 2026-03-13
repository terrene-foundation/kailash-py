# Bug Report: DataFlow Connection String Parameter Mismatch

**Date**: 2025-11-17
**Issue**: OrchestrationStateManager uses SQLite instead of PostgreSQL
**Root Cause**: Parameter name mismatch between OrchestrationStateManager and DataFlow.__init__
**Severity**: HIGH (causes all database operations to use wrong database)
**Status**: FIXED

---

## Problem Summary

**Symptom**: OrchestrationStateManager integration tests were using SQLite `:memory:` database instead of the PostgreSQL connection string provided via POSTGRES_URL environment variable.

**Evidence**:
- Stack traces showed `aiosqlite` being used instead of `asyncpg`
- Warning: "No database URL configured. Using SQLite :memory: database"
- Tests created PostgreSQL URL correctly: `postgresql://test_user:test_password@172.18.0.12:5432/kailash_test`
- DataFlow instance was initialized with this URL, but nodes still used SQLite

---

## Root Cause Analysis

### The Bug

**File**: `src/kaizen/orchestration/state_manager.py:179-184`

```python
# BEFORE (WRONG):
self.db = DataFlow(
    connection_string=connection_string,  # ❌ WRONG parameter name
    auto_migrate=True,
    enable_caching=enable_caching,
    enable_metrics=enable_metrics,
)
```

**Problem**: DataFlow.__init__() does NOT accept `connection_string` parameter.

**DataFlow.__init__ signature** (from `packages/kailash-dataflow/src/dataflow/core/engine.py:60`):

```python
def __init__(
    self,
    database_url: Optional[str] = None,  # ✅ Correct parameter name
    config: Optional[DataFlowConfig] = None,
    pool_size: Optional[int] = None,
    # ... other parameters
    **kwargs,  # ⚠️ connection_string goes here and is IGNORED
):
```

### What Happened

1. **OrchestrationStateManager** calls `DataFlow(connection_string="postgresql://...")`
2. DataFlow.__init__ doesn't have a `connection_string` parameter
3. The value goes into `**kwargs` and is **silently ignored**
4. `self.config.database.url` is set to `None` (default)
5. When nodes execute, they fall back to `:memory:` SQLite (line 1165 in nodes.py)

### Connection String Resolution in DataFlow Nodes

**File**: `packages/kailash-dataflow/src/dataflow/core/nodes.py:1162-1166`

```python
# Get connection string - prioritize parameter over instance config
connection_string = kwargs.get("database_url")
if not connection_string:
    connection_string = (
        self.dataflow_instance.config.database.url or ":memory:"
    )
```

Since `self.dataflow_instance.config.database.url` was `None`, it fell back to `:memory:`.

---

## The Fix

**File**: `src/kaizen/orchestration/state_manager.py:179-184`

```python
# AFTER (CORRECT):
self.db = DataFlow(
    database_url=connection_string,  # ✅ FIXED: Correct parameter name
    auto_migrate=True,
    enable_caching=enable_caching,
    enable_metrics=enable_metrics,
)
```

**Result**:
- `config.database.url` is now correctly set to the PostgreSQL connection string
- All DataFlow nodes use PostgreSQL instead of SQLite
- Integration tests now properly test against real PostgreSQL

---

## Key Learnings

### 1. **db_instance Parameter is NOT Functional**

The `db_instance` parameter documented in DataFlow nodes is **not currently implemented**:

```python
# This parameter exists in documentation but does NOTHING:
workflow.add_node("UserCreateNode", "create", {
    "db_instance": "my_db",  # ❌ Not used for connection resolution
    "model_name": "User",
    # ...
})
```

**Current behavior**: Nodes resolve connection strings via:
1. Node's `database_url` parameter (if provided)
2. `self.dataflow_instance.config.database.url` (from closure)
3. `:memory:` SQLite (fallback)

There is **NO global registry** of DataFlow instances by name.

### 2. **No Global DataFlow Instance Registry**

DataFlow v0.7.16 does NOT have a global instance registry. The `db_instance` parameter appears to be intended for future multi-instance support but is not implemented.

### 3. **Parameter Validation Warnings Are Important**

The warning was present but easy to miss:

```
WARNING: Workflow parameters ['db_instance', 'model_name'] not declared in get_parameters() - will be ignored by SDK
```

This warning correctly indicated that `db_instance` wasn't being used.

### 4. **Silent Failures from kwargs**

Python's `**kwargs` pattern can silently accept wrong parameter names:

```python
def __init__(self, database_url: str = None, **kwargs):
    # connection_string goes into kwargs and disappears!
    pass

# No error raised:
DataFlow(connection_string="postgresql://...")
```

This makes parameter name mismatches hard to detect.

---

## Testing Strategy

### Verification Test

```python
import os
from dotenv import load_dotenv
from dataflow import DataFlow

load_dotenv()
postgres_url = os.getenv("POSTGRES_URL")

# Test 1: Wrong parameter (reproduces bug)
db_wrong = DataFlow(connection_string=postgres_url, auto_migrate=False)
assert db_wrong.config.database.url is None  # FAIL: None (uses SQLite)

# Test 2: Correct parameter (fix verified)
db_correct = DataFlow(database_url=postgres_url, auto_migrate=False)
assert db_correct.config.database.url == postgres_url  # PASS!
```

### Integration Test

Run existing OrchestrationStateManager tests:

```bash
POSTGRES_URL="postgresql://test_user:test_password@172.18.0.12:5432/kailash_test" \
pytest tests/integration/orchestration/test_state_manager_integration.py -xvs
```

**Expected**: Tests now use PostgreSQL (check for `asyncpg` in stack traces, not `aiosqlite`)

---

## Related Code Locations

1. **OrchestrationStateManager.__init__**
   `

2. **DataFlow.__init__**
   `packages/kailash-dataflow/src/dataflow/core/engine.py:60-95`

3. **DataFlow node connection resolution**
   `packages/kailash-dataflow/src/dataflow/core/nodes.py:1162-1166`

4. **Integration test fixture**
   `

---

## Prevention

### Code Review Checklist

- [ ] Verify parameter names match function signatures
- [ ] Don't rely on `**kwargs` to catch typos
- [ ] Test configuration objects to ensure values are set
- [ ] Check for "Using SQLite :memory:" warnings in logs

### Recommended DataFlow Improvements

1. **Deprecate kwargs for critical parameters**:
   ```python
   def __init__(self, database_url: str, ...):  # Remove Optional
       if database_url is None:
           raise ValueError("database_url is required")
   ```

2. **Add parameter validation**:
   ```python
   ALLOWED_KWARGS = {'batch_size', 'cache_max_size', ...}
   unknown = set(kwargs.keys()) - ALLOWED_KWARGS
   if unknown:
       raise TypeError(f"Unknown parameters: {unknown}")
   ```

3. **Implement db_instance registry** (if needed):
   ```python
   _INSTANCE_REGISTRY: Dict[str, DataFlow] = {}

   def register_instance(name: str, instance: DataFlow):
       _INSTANCE_REGISTRY[name] = instance
   ```

---

## Fix Validation

**Before fix**:
```bash
WARNING: No database URL configured. Using SQLite :memory: database.
WARNING: CREATE TestModel - Generated SQL: INSERT INTO test_models (id, name) VALUES (?, ?)
# Uses SQLite syntax (?) instead of PostgreSQL ($1, $2)
```

**After fix**:
```bash
INFO: Using PostgreSQL database: postgresql://test_user:***@172.18.0.12:5432/kailash_test
WARNING: CREATE TestModel - Generated SQL: INSERT INTO test_models (id, name) VALUES ($1, $2)
# Uses PostgreSQL syntax ($1, $2)
```

---

## Impact

**Before**: ALL OrchestrationStateManager operations used SQLite, making integration tests invalid.

**After**: OrchestrationStateManager correctly uses PostgreSQL as configured.

**Affected Components**:
- OrchestrationStateManager (all 3 models: WorkflowState, AgentExecutionRecord, WorkflowCheckpoint)
- Integration tests for orchestration
- Production deployments using PostgreSQL

---

## Conclusion

A simple parameter name mismatch (`connection_string` vs `database_url`) caused all database operations to silently fall back to SQLite. The fix is a one-line change but has significant impact on test validity and production correctness.

**Key Takeaway**: Parameter names matter. Python's `**kwargs` pattern can hide errors. Always verify configuration objects after initialization.

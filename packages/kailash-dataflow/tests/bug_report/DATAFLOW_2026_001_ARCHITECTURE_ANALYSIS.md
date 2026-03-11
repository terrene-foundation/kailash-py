# DataFlow Architecture Analysis: DATAFLOW-2026-001

**Date**: 2026-01-06
**Status**: FIXES IMPLEMENTED

## Resolution Summary

| Issue                     | Status       | Action Taken                                          |
| ------------------------- | ------------ | ----------------------------------------------------- |
| `skip_registry` parameter | **RESOLVED** | Removed from codebase and all documentation           |
| DDL mutable defaults      | **FIXED**    | Added JSON serialization for list/dict defaults       |
| Generic type mapping      | **FIXED**    | Added `get_origin()` check for `List[T]`, `Dict[K,V]` |
| Unknown kwargs            | **FIXED**    | Added validation with informative warnings            |

---

---

## 1. DataFlow Architecture Overview

### Model Registration Flow

When `@db.model` decorator is applied, the following operations occur:

```
@db.model
    │
    ├─► (1) Register in self._models (always)         ← FAST: Dict assignment
    │
    ├─► (2) Generate CRUD nodes                       ← FAST: Class generation
    │       └─► _generate_crud_nodes()
    │       └─► _generate_bulk_nodes()
    │
    └─► (3) Persist to ModelRegistry (conditional)    ← SLOW: Workflow execution
            └─► IF enable_model_persistence=True:
                    └─► self._model_registry.register_model()
                            └─► LocalRuntime().execute(workflow.build())
                                    └─► SQL INSERT to dataflow_model_registry
```

**Key Insight**: Step (3) is what causes the 5-10 second delay per model.

### ModelRegistry Architecture

**Location**: `src/dataflow/core/model_registry.py`

The ModelRegistry provides:

- **Persistent storage** of model definitions across restarts
- **Multi-application sharing** of models
- **Version tracking** and checksum validation
- **Model discovery** from the database

**The Cost**: Each `register_model()` call (line 520-521):

```python
init_runtime = LocalRuntime()
results, _ = init_runtime.execute(workflow.build())
```

This executes a full workflow with database INSERT - synchronously, one per model.

---

## 2. The Nexus Integration Problem

### Why Nexus Needs Fast Startup

1. **Docker/K8s health checks** timeout after 30-60 seconds
2. **Rolling deployments** need fast pod readiness
3. **Developer iteration** slowed by long startup times
4. **Auto-scaling** needs quick instance spin-up

### Two Separate Issues

| Issue                          | Cause                                                                            | Solution                 |
| ------------------------------ | -------------------------------------------------------------------------------- | ------------------------ |
| **Infinite Blocking**          | Nexus `auto_discovery=True` imports DataFlow models which trigger sync workflows | `auto_discovery=False`   |
| **Slow Startup (5-10s/model)** | `ModelRegistry.register_model()` executes sync workflows                         | Skip registry operations |

---

## 3. The `skip_registry` Parameter

### Intended Purpose (From Documentation)

From `.claude/skills/03-nexus/nexus-dataflow-integration.md:18`:

> "DataFlow: Set `skip_registry=True` and `enable_model_persistence=False` for fast startup"

**Intended behavior**: Skip the ModelRegistry operations that cause slow startup.

### Actual Implementation: NOT FOUND

**grep search in `src/dataflow/`**: `skip_registry` - No matches

**DataFlow.**init**() signature** (engine.py:67-105):

```python
def __init__(
    self,
    database_url: Optional[str] = None,
    # ... 27 explicit parameters ...
    enable_model_persistence: bool = True,  # ← THIS exists
    # skip_registry is NOT HERE
    **kwargs,  # ← skip_registry goes here and is ignored
):
```

### What Happens When You Pass `skip_registry=True`

```python
>>> db = DataFlow('sqlite:///:memory:', skip_registry=True)
>>> db._init_kwargs
{'skip_registry': True}  # ← Captured but NEVER used
>>> db._models
{'User': {...}}  # ← Models ARE registered anyway
```

The parameter is silently ignored because:

1. It's not in the explicit parameter list
2. It goes into `**kwargs`
3. It's stored in `_init_kwargs` but never read

---

## 4. Documentation vs Implementation Gaps

### Parameters Documented But NOT Implemented

| Parameter              | Documented In           | Status                |
| ---------------------- | ----------------------- | --------------------- |
| `skip_registry`        | 30+ files               | NOT IMPLEMENTED       |
| `skip_migration`       | Nexus integration guide | NOT IMPLEMENTED       |
| `enable_metrics`       | Nexus integration guide | NOT IMPLEMENTED       |
| `connection_pool_size` | Nexus integration guide | Should be `pool_size` |

### Parameters That Actually Work

| Parameter                  | Default | Purpose                          | Works? |
| -------------------------- | ------- | -------------------------------- | ------ |
| `enable_model_persistence` | `True`  | Skip ModelRegistry DB operations | YES    |
| `auto_migrate`             | `True`  | Skip automatic table creation    | YES    |
| `existing_schema_mode`     | `False` | Skip schema validation           | YES    |
| `migration_enabled`        | `True`  | Skip migration system init       | YES    |
| `enable_caching`           | `None`  | Alias for `cache_enabled`        | YES    |

---

## 5. Related: ADR-002 `skip_registry`

**Important Clarification**: ADR-002 mentions `skip_registry` in a DIFFERENT context.

ADR-002 discusses `skip_registry` as a **CRUD node parameter** for handling duplicate records (conflict resolution), NOT as a DataFlow initialization parameter.

```
ADR-002 context:     "skip_registry" → "conflict_resolution" (CRUD operations)
Bug report context:  "skip_registry" → Skip ModelRegistry (initialization)
```

These are two different uses of the same name, causing additional confusion.

---

## 6. Root Cause Summary

### Issue 1: `skip_registry` Silent Failure

**Root Cause**: Parameter was documented but never implemented in `DataFlow.__init__()`.

**The Gap**:

- Documentation says: Use `skip_registry=True` for fast startup
- Code does: Nothing - parameter is silently ignored
- User expects: ModelRegistry operations skipped
- Actual behavior: ModelRegistry operations still run (if `enable_model_persistence=True`)

**Why it "seems to work"**: Users often pair `skip_registry=True` with `enable_model_persistence=False`, and the latter actually works.

### Issue 2: DDL Mutable Defaults

**Root Cause**: `_get_sql_column_definition()` at line 3478 doesn't handle `list`/`dict` types:

```python
else:
    definition_parts.append(f"DEFAULT {default_value}")  # BUG
```

### Issue 3: Generic Type Mapping

**Root Cause**: `_python_type_to_sql_type()` checks for bare `list`/`dict` but not `typing.List[T]`/`typing.Dict[K,V]`:

```python
type_mappings = {
    "postgresql": {
        list: "JSONB",  # Works
        dict: "JSONB",  # Works
        # List[str] → NOT HANDLED → falls through to TEXT
    }
}
```

---

## 7. Correct Fast Startup Configuration

### What Actually Works

```python
from nexus import Nexus
from dataflow import DataFlow

# Nexus: Prevent infinite blocking
app = Nexus(
    api_port=8000,
    auto_discovery=False,  # CRITICAL
)

# DataFlow: Fast startup (actual working parameters)
db = DataFlow(
    database_url=os.environ["DATABASE_URL"],
    enable_model_persistence=False,  # WORKS: Skips ModelRegistry
    auto_migrate=False,              # WORKS: Skips table creation
    # skip_registry=True,            # DOESN'T WORK: Silently ignored
)
```

### What You Keep vs Lose

| With Fast Config                  | Status |
| --------------------------------- | ------ |
| CRUD nodes (11 per model)         | KEEP   |
| Connection pooling                | KEEP   |
| Query caching                     | KEEP   |
| Express API                       | KEEP   |
| Model persistence across restarts | LOSE   |
| Automatic migrations              | LOSE   |
| Cross-app model sharing           | LOSE   |

---

## 8. Recommended Fixes

### Option A: Implement `skip_registry` (Preferred)

Add the parameter and make it an alias:

```python
def __init__(
    self,
    # ...existing params...
    skip_registry: bool = False,  # NEW: Alias for enable_model_persistence=False
    # ...
):
    # Handle skip_registry as alias
    if skip_registry:
        import warnings
        warnings.warn(
            "skip_registry is deprecated, use enable_model_persistence=False instead",
            DeprecationWarning,
            stacklevel=2
        )
        enable_model_persistence = False

    self._enable_model_persistence = enable_model_persistence
```

### Option B: Add Unknown Kwargs Validation

```python
def __init__(self, ..., **kwargs):
    KNOWN_KWARGS = {'batch_size', 'schema_cache_enabled', ...}
    unknown = set(kwargs.keys()) - KNOWN_KWARGS
    if unknown:
        import warnings
        warnings.warn(
            f"DF-CFG-001: Unknown parameters passed to DataFlow: {unknown}. "
            f"These parameters have no effect and will be ignored. "
            f"Did you mean 'enable_model_persistence' instead of 'skip_registry'?",
            UserWarning,
            stacklevel=2
        )
```

### Option C: Update Documentation

Remove all references to `skip_registry` and update to use `enable_model_persistence=False`.

---

## 9. Files to Modify

### For Issue 1 Fix

| File                                                    | Action                                             |
| ------------------------------------------------------- | -------------------------------------------------- |
| `src/dataflow/core/engine.py`                           | Add `skip_registry` parameter or kwargs validation |
| `.claude/skills/03-nexus/nexus-dataflow-integration.md` | Update to use `enable_model_persistence`           |
| `.claude/skills/02-dataflow/*.md`                       | Update all references                              |
| 30+ other documentation files                           | Bulk update                                        |

### For Issue 2 Fix (DDL)

| File                                      | Lines     | Action                                            |
| ----------------------------------------- | --------- | ------------------------------------------------- |
| `src/dataflow/core/engine.py`             | 3381-3436 | Handle `get_origin()` for generic types           |
| `src/dataflow/core/engine.py`             | 3464-3478 | Handle list/dict defaults with JSON serialization |
| `src/dataflow/database/multi_database.py` | 246-253   | Same default value handling                       |

---

## 10. Test Plan

```python
# Test 1: skip_registry warning
def test_skip_registry_warns():
    with warnings.catch_warnings(record=True) as w:
        db = DataFlow('sqlite:///:memory:', skip_registry=True)
        assert len(w) == 1
        assert 'skip_registry' in str(w[0].message)

# Test 2: skip_registry behaves like enable_model_persistence=False
def test_skip_registry_behavior():
    db = DataFlow('sqlite:///:memory:', skip_registry=True)
    assert db._enable_model_persistence == False

# Test 3: DDL for List[str] produces valid SQL
def test_list_default_ddl():
    db = DataFlow('sqlite:///:memory:')
    @db.model
    class Test:
        id: str
        tags: List[str] = []
    ddl = db._generate_create_table_sql('Test', 'postgresql')
    assert "DEFAULT '[]'::jsonb" in ddl
```

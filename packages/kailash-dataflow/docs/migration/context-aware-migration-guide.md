# Migration Guide: Context-Aware Architecture (Phase 5)

**Date**: 2026-02-09
**Affected Versions**: Pre-Phase 5 -> Phase 5+
**Migration Difficulty**: EASY (100% backward compatible, all features are additive)

---

## Overview

Phase 5 introduces the Context-Aware Architecture for DataFlow, adding three new
capabilities to the existing framework:

1. **TypeAwareFieldProcessor** (TODO-153): Centralized type validation for model
   fields with safe conversions and explicit bool/int separation.
2. **DataFlowWorkflowBinder** (TODO-154): A higher-level workflow composition API
   accessible directly from the DataFlow instance.
3. **TenantContextSwitch** (TODO-155): Runtime tenant context switching with sync
   and async context managers and automatic restoration.

All three features are **purely additive**. Existing code continues to work without
modification. There are no breaking changes and no deprecations. You can adopt these
features incrementally at your own pace.

---

## Do You Need to Migrate?

### No Immediate Action Required

Your existing code will continue to work without any changes. Phase 5 adds new APIs
alongside the existing ones. The original `WorkflowBuilder` pattern, the `@db.model`
decorator, and all CRUD/bulk operations remain unchanged.

### When Should You Adopt?

Consider adopting Phase 5 features when:

- You want **simpler workflow composition** without manually resolving node type names
  (use `db.create_workflow()` and `db.add_node()`)
- You need **multi-tenant isolation** with safe context switching
  (use `db.tenant_context`)
- You want **type-safe field validation** that catches type mismatches early
  (TypeAwareFieldProcessor is used internally by DataFlow nodes)

---

## What Changed

### 1. Type-Aware Field Processing (TODO-153)

**What it does**: The `TypeAwareFieldProcessor` validates field values against model
type annotations before database operations. It runs automatically inside DataFlow
nodes.

**Key behaviors**:

- Non-strict by default: performs safe, lossless conversions (e.g., UUID strings to
  UUID objects, ISO strings to datetime)
- Strict mode available: rejects any type mismatch without conversion
- `bool` values are explicitly rejected for `int` fields (Python treats `bool` as a
  subclass of `int`, but DataFlow distinguishes them)
- Automatically skips `created_at` and `updated_at` (auto-managed fields)

**Impact on existing code**: None. The processor is integrated internally. If your
existing code passes correct types, nothing changes. If your code was passing incorrect
types that happened to work due to Python's type coercion, you may now see `TypeError`
exceptions with clear messages indicating what went wrong.

**Before (implicit, potentially unsafe)**:

```python
# This would silently succeed even if 'age' is defined as int
workflow.add_node("UserCreateNode", "create_user", {
    "name": "Alice",
    "age": True,  # bool passed to int field
})
```

**After (explicit validation)**:

```python
# Now raises TypeError: "expected int, got bool. Booleans are not integers in DataFlow."
# Fix: pass an actual integer
workflow.add_node("UserCreateNode", "create_user", {
    "name": "Alice",
    "age": 30,  # correct int value
})
```

### 2. Workflow Binding API (TODO-154)

**What it does**: Adds `create_workflow()`, `add_node()`, `execute_workflow()`, and
`get_available_nodes()` directly to the `DataFlow` instance, providing a higher-level
alternative to the raw `WorkflowBuilder`.

**Impact on existing code**: None. The existing `WorkflowBuilder` pattern continues to
work exactly as before. The new API is an optional convenience layer.

**Before (raw WorkflowBuilder)**:

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime import LocalRuntime

db = DataFlow("sqlite:///app.db")

@db.model
class User:
    name: str
    email: str

# You must know the generated node type name
workflow = WorkflowBuilder()
workflow.add_node("UserCreateNode", "create_user", {
    "name": "Alice",
    "email": "alice@example.com",
})

runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
```

**After (workflow binding API)**:

```python
from dataflow import DataFlow

db = DataFlow("sqlite:///app.db")

@db.model
class User:
    name: str
    email: str

# Model name + operation, no need to know node type names
workflow = db.create_workflow("user_setup")
db.add_node(workflow, "User", "Create", "create_user", {
    "name": "Alice",
    "email": "alice@example.com",
})

results, run_id = db.execute_workflow(workflow)
```

**Key differences**:
| Aspect | WorkflowBuilder | Workflow Binding API |
|---|---|---|
| Node type | Must know `"UserCreateNode"` | Use model name + operation: `"User"`, `"Create"` |
| Validation | No model validation | Validates model exists and operation is valid |
| Error messages | Generic | DataFlow-context-aware |
| Runtime | Must create explicitly | Auto-creates `LocalRuntime` if not provided |
| Discovery | N/A | `db.get_available_nodes()` lists all models/operations |

### 3. Tenant Context Switching (TODO-155)

**What it does**: Adds a `tenant_context` property to `DataFlow` that provides sync
and async context managers for switching between tenant contexts at runtime.

**Impact on existing code**: None. If you are not using multi-tenant features, this
capability is present but dormant. If you are already using `set_tenant_context()`,
you can optionally migrate to the new context-manager-based API for safer context
handling.

**Before (manual tenant setting)**:

```python
db = DataFlow("postgresql://...", multi_tenant=True)

# Manual - no automatic restoration on error
db.set_tenant_context("tenant-a")
# ... operations ...
db.set_tenant_context("tenant-b")
# If an error occurred above, tenant-b may have stale state
```

**After (context manager with automatic restoration)**:

```python
from dataflow import DataFlow

db = DataFlow("postgresql://...", multi_tenant=True)

# Register tenants
db.tenant_context.register_tenant("tenant-a", "Acme Corp")
db.tenant_context.register_tenant("tenant-b", "Globex Inc")

# Context manager guarantees restoration
with db.tenant_context.switch("tenant-a"):
    # All operations here are in tenant-a context
    workflow = db.create_workflow("tenant_ops")
    db.add_node(workflow, "User", "Create", "create_user", {"name": "Alice"})
    results, _ = db.execute_workflow(workflow)
# Automatically restored to previous context, even if an exception occurred
```

---

## Compatibility Guarantees

### What Stays the Same

- `from dataflow import DataFlow` import remains unchanged
- `@db.model` decorator works exactly as before
- All 11 auto-generated nodes per model are unchanged
- `WorkflowBuilder` + `LocalRuntime` pattern works as before
- `runtime.execute(workflow.build())` execution pattern unchanged
- All existing parameter formats (flat for Create, filter+fields for Update) unchanged
- Express API (`db.express.create()`, etc.) unchanged

### What Is New (Additive Only)

- `db.create_workflow()` - create workflow with DataFlow context
- `db.add_node()` - add nodes using model name + operation name
- `db.execute_workflow()` - execute with auto-created runtime
- `db.get_available_nodes()` - discover available models and operations
- `db.tenant_context` - tenant context switching interface
- `TypeAwareFieldProcessor` - available for direct use if needed
- `TenantContextSwitch`, `TenantInfo`, `get_current_tenant_id` - public exports

### No Deprecations

None of the existing APIs are deprecated. Phase 5 features are provided as optional,
higher-level alternatives.

---

## Step-by-Step Migration

### Step 1: Upgrade DataFlow

```bash
pip install --upgrade kailash-dataflow
```

### Step 2: Verify Existing Code

Run your existing test suite. Everything should pass without changes:

```bash
pytest tests/
```

### Step 3: Adopt Workflow Binding (Optional)

Replace raw `WorkflowBuilder` usage with the new API where it improves readability.
Start with simple single-model workflows:

```python
# Old pattern
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime import LocalRuntime

workflow = WorkflowBuilder()
workflow.add_node("UserCreateNode", "create_user", {"name": "Alice"})
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())

# New pattern
workflow = db.create_workflow("create_user_flow")
db.add_node(workflow, "User", "Create", "create_user", {"name": "Alice"})
results, run_id = db.execute_workflow(workflow)
```

### Step 4: Adopt Tenant Context Switching (Optional)

If you use multi-tenant features, migrate from manual tenant setting to context
managers:

```python
# Old pattern
db.set_tenant_context("tenant-a")
try:
    # operations
    pass
finally:
    db.set_tenant_context(None)  # manual cleanup

# New pattern
db.tenant_context.register_tenant("tenant-a", "Acme Corp")
with db.tenant_context.switch("tenant-a"):
    # operations - automatic cleanup
    pass
```

### Step 5: Review Type Validation Messages

If any of your existing code was relying on implicit type coercion (e.g., passing
`True` where an `int` was expected), you may see new `TypeError` messages. Fix these
by passing the correct types.

---

## New Imports Reference

All Phase 5 features are available from the top-level `dataflow` package:

```python
# Primary entry point (unchanged)
from dataflow import DataFlow

# Phase 5 additions (optional direct imports)
from dataflow import TypeAwareFieldProcessor    # TODO-153
from dataflow import DataFlowWorkflowBinder     # TODO-154
from dataflow import TenantContextSwitch        # TODO-155
from dataflow import TenantInfo                 # TODO-155
from dataflow import get_current_tenant_id      # TODO-155
```

Most users will only need `from dataflow import DataFlow`, since the workflow binding
and tenant context features are accessed through the `DataFlow` instance methods
(`db.create_workflow()`, `db.tenant_context`, etc.).

---

## FAQ

**Q: Will my existing tests break?**
A: No. All Phase 5 features are additive. Existing tests will pass unchanged.

**Q: Do I need to use the new workflow binding API?**
A: No. The raw `WorkflowBuilder` + `LocalRuntime` pattern continues to work. Use the
new API when it improves code clarity.

**Q: Is the TypeAwareFieldProcessor applied automatically?**
A: Yes, internally by DataFlow nodes. You do not need to call it directly unless you
want to validate fields outside of a workflow.

**Q: Can I mix the old and new APIs?**
A: Yes. You can use `db.create_workflow()` for some workflows and `WorkflowBuilder()`
for others within the same application.

**Q: Does tenant context switching require multi_tenant=True?**
A: The `tenant_context` property is always available on the `DataFlow` instance. You
can register and switch tenants regardless of the `multi_tenant` configuration flag.
The flag controls data isolation behavior at the database level.

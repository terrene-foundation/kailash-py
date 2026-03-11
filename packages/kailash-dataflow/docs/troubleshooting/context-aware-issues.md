# Troubleshooting: Context-Aware Architecture Issues

Common issues and solutions for DataFlow's Context-Aware features (Phase 5):
TypeAwareFieldProcessor, DataFlowWorkflowBinder, and TenantContextSwitch.

---

## Table of Contents

- [Workflow Binding Issues](#workflow-binding-issues)
  - [Model 'X' is not registered](#model-x-is-not-registered)
  - [Invalid operation 'X' for model 'Y'](#invalid-operation-x-for-model-y)
  - [Node 'X' not found](#node-x-not-found)
  - [Workflow execution returns empty results](#workflow-execution-returns-empty-results)
- [Tenant Context Issues](#tenant-context-issues)
  - [Tenant 'X' is not registered](#tenant-x-is-not-registered)
  - [Tenant 'X' is not active](#tenant-x-is-not-active)
  - [No tenant context is active](#no-tenant-context-is-active)
  - [Context not restored after exception](#context-not-restored-after-exception)
  - [Tenant 'X' is already registered](#tenant-x-is-already-registered)
  - [Cannot unregister tenant while active](#cannot-unregister-tenant-while-active)
- [Type Processing Issues](#type-processing-issues)
  - [Expected int, got bool](#expected-int-got-bool)
  - [Expected valid UUID string](#expected-valid-uuid-string)
  - [Expected ISO datetime string](#expected-iso-datetime-string)
  - [Type error in record N of bulk operation](#type-error-in-record-n-of-bulk-operation)
- [Cross-Instance Confusion](#cross-instance-confusion)
- [Async Context Issues](#async-context-issues)

---

## Workflow Binding Issues

### Model 'X' is not registered

**Error message**:

```
ValueError: Model 'Invoice' is not registered with this DataFlow instance.
Available models: ['User', 'Order']. Ensure @db.model is applied to Invoice
before creating workflows.
```

**Cause**: You are trying to use `db.add_node()` with a model name that has not been
registered using `@db.model`.

**Solutions**:

1. Ensure the model class has the `@db.model` decorator:

```python
db = DataFlow("sqlite:///app.db")

@db.model
class Invoice:    # This registers "Invoice" with DataFlow
    amount: float
    customer_id: int
```

2. Ensure the decorator runs before you call `db.add_node()`. Python decorators
   execute at class definition time, so the `@db.model` class must be defined before
   creating workflows:

```python
# WRONG: workflow created before model is defined
workflow = db.create_workflow("ops")

@db.model
class Invoice:
    amount: float

db.add_node(workflow, "Invoice", "Create", "create", {"amount": 100})  # Error!

# CORRECT: model defined first
@db.model
class Invoice:
    amount: float

workflow = db.create_workflow("ops")
db.add_node(workflow, "Invoice", "Create", "create", {"amount": 100})  # Works
```

3. Check for typos in the model name. The name is case-sensitive and must match the
   class name exactly:

```python
# WRONG
db.add_node(workflow, "invoice", "Create", ...)  # lowercase
db.add_node(workflow, "Invoices", "Create", ...)  # plural

# CORRECT
db.add_node(workflow, "Invoice", "Create", ...)  # exact class name
```

4. Verify available models:

```python
available = db.get_available_nodes()
print(list(available.keys()))  # ['User', 'Order', ...]
```

---

### Invalid operation 'X' for model 'Y'

**Error message**:

```
ValueError: Invalid operation 'Archive' for model 'User'.
Available operations: ['Create', 'Read', 'Update', 'Delete', 'List', 'Upsert',
'Count', 'BulkCreate', 'BulkUpdate', 'BulkDelete', 'BulkUpsert']
```

**Cause**: The operation name does not match one of the 11 supported DataFlow
operations.

**Solution**: Use one of the supported operation names. The full list is:

| Operation    | Description                             |
| ------------ | --------------------------------------- |
| `Create`     | Create a single record                  |
| `Read`       | Read a single record by ID              |
| `Update`     | Update records matching a filter        |
| `Delete`     | Delete records matching a filter        |
| `List`       | List all records (with optional filter) |
| `Upsert`     | Create or update based on filter        |
| `Count`      | Count records (with optional filter)    |
| `BulkCreate` | Create multiple records                 |
| `BulkUpdate` | Update multiple records                 |
| `BulkDelete` | Delete multiple records                 |
| `BulkUpsert` | Upsert multiple records                 |

Common mistakes:

```python
# WRONG: lowercase
db.add_node(workflow, "User", "create", ...)

# WRONG: past tense
db.add_node(workflow, "User", "Created", ...)

# WRONG: custom operation name
db.add_node(workflow, "User", "Archive", ...)

# CORRECT: exact PascalCase operation name
db.add_node(workflow, "User", "Create", ...)
```

---

### Node 'X' not found

**Error message**:

```
ValueError: Node 'UserCreateNode' not found. Model 'User' may not have generated
nodes yet. Ensure @db.model is applied first.
```

**Cause**: The model is registered in the models dict but its auto-generated nodes
have not been created. This can happen if model registration was interrupted or if
there was an error during node generation.

**Solution**:

1. Check that `@db.model` completed without errors:

```python
@db.model
class User:
    name: str
    email: str

# Verify nodes were generated
print(db.get_available_nodes("User"))
# Should print: {'User': ['Create', 'Read', 'Update', ...]}
```

2. If using dynamic model registration, ensure the DataFlow instance has been
   properly initialized:

```python
db = DataFlow("sqlite:///app.db")
# If using async initialization, ensure initialize() was called
# await db.initialize()
```

---

### Workflow execution returns empty results

**Cause**: The workflow was created but no nodes were added to it.

**Solution**: Verify that `db.add_node()` was called before `db.execute_workflow()`:

```python
workflow = db.create_workflow("my_flow")

# Verify nodes are added
db.add_node(workflow, "User", "List", "list_users", {})

# Check workflow has nodes before executing
print(f"Workflow has {len(workflow.nodes)} nodes")

results, run_id = db.execute_workflow(workflow)
```

---

## Tenant Context Issues

### Tenant 'X' is not registered

**Error message**:

```
ValueError: Tenant 'acme' is not registered. Available tenants: ['globex'].
Use register_tenant() to register this tenant first.
```

**Cause**: You are trying to switch to a tenant that has not been registered with
`register_tenant()`.

**Solution**: Register the tenant before switching:

```python
ctx = db.tenant_context

# Register first
ctx.register_tenant("acme", "Acme Corporation")

# Then switch
with ctx.switch("acme"):
    # operations
    pass
```

Check for typos in tenant IDs:

```python
# List all registered tenants
for tenant in ctx.list_tenants():
    print(f"  {tenant.tenant_id}: {tenant.name}")
```

---

### Tenant 'X' is not active

**Error message**:

```
ValueError: Tenant 'acme' is not active.
Use activate_tenant() to reactivate it.
```

**Cause**: The tenant was deactivated using `deactivate_tenant()`. Deactivated tenants
cannot be switched to.

**Solution**: Reactivate the tenant if appropriate:

```python
ctx = db.tenant_context

# Check status
print(ctx.is_tenant_active("acme"))  # False

# Reactivate
ctx.activate_tenant("acme")

# Now switching works
with ctx.switch("acme"):
    pass
```

If the deactivation was intentional (e.g., suspended customer), do not reactivate
without proper authorization.

---

### No tenant context is active

**Error message**:

```
RuntimeError: No tenant context is active.
Use 'with db.tenant_context.switch(tenant_id):' to set a tenant context.
```

**Cause**: Code called `require_tenant()` outside of a `switch()` or `aswitch()`
context manager block.

**Solution**: Wrap the operation in a tenant context:

```python
ctx = db.tenant_context

# WRONG: calling require_tenant() without context
tenant_id = ctx.require_tenant()  # RuntimeError!

# CORRECT: set context first
with ctx.switch("acme"):
    tenant_id = ctx.require_tenant()  # Returns "acme"
    # proceed with tenant-scoped operations
```

If the code is called from a service layer, ensure the caller provides the context:

```python
# In service layer
def create_user(db, name, email):
    db.tenant_context.require_tenant()  # Validates caller set context
    workflow = db.create_workflow("create_user")
    db.add_node(workflow, "User", "Create", "create", {"name": name, "email": email})
    return db.execute_workflow(workflow)

# In caller
with db.tenant_context.switch("acme"):
    create_user(db, "Alice", "alice@acme.com")
```

---

### Context not restored after exception

**Symptom**: After an exception inside a `switch()` block, the tenant context seems
to be stuck or incorrect.

**Cause**: This should not happen if you are using context managers (`with` /
`async with`). If it does happen, you may be setting context manually instead of using
context managers.

**Solution**: Always use context managers for tenant switching:

```python
# CORRECT: context manager handles cleanup automatically
try:
    with ctx.switch("acme"):
        raise ValueError("something went wrong")
except ValueError:
    pass

# Context is properly restored to None
print(ctx.get_current_tenant())  # None

# INCORRECT: manual context setting has no automatic cleanup
# Do not do this:
# from dataflow.core.tenant_context import _current_tenant
# _current_tenant.set("acme")  # No automatic cleanup!
```

If you suspect a context leak, check the stats:

```python
stats = ctx.get_stats()
print(f"Active switches: {stats['active_switches']}")
# Should be 0 when outside all context managers
```

---

### Tenant 'X' is already registered

**Error message**:

```
ValueError: Tenant 'acme' is already registered
```

**Cause**: You are calling `register_tenant()` with a tenant ID that is already
registered.

**Solution**: Check if the tenant is registered before registering:

```python
ctx = db.tenant_context

if not ctx.is_tenant_registered("acme"):
    ctx.register_tenant("acme", "Acme Corporation")
```

Or handle the error:

```python
try:
    ctx.register_tenant("acme", "Acme Corporation")
except ValueError:
    pass  # Already registered, continue
```

---

### Cannot unregister tenant while active

**Error message**:

```
ValueError: Cannot unregister tenant 'acme' while it is the active context
```

**Cause**: You are trying to unregister a tenant that is currently set as the active
tenant context.

**Solution**: Exit the tenant context before unregistering:

```python
# WRONG: unregistering while inside switch block
with ctx.switch("acme"):
    ctx.unregister_tenant("acme")  # Error!

# CORRECT: unregister after exiting context
with ctx.switch("acme"):
    # operations
    pass

ctx.unregister_tenant("acme")  # Works - no active context
```

---

## Type Processing Issues

### Expected int, got bool

**Error message**:

```
TypeError: Model User, field 'age': expected int, got bool.
Booleans are not integers in DataFlow.
```

**Cause**: You passed a `bool` value (`True` or `False`) to a field annotated as
`int`. While Python treats `bool` as a subclass of `int`, DataFlow explicitly
distinguishes them to prevent subtle bugs.

**Solution**: Pass an actual `int` value:

```python
# WRONG
db.add_node(workflow, "User", "Create", "create", {
    "age": True,  # bool, not int
})

# CORRECT
db.add_node(workflow, "User", "Create", "create", {
    "age": 1,  # or any integer value
})
```

---

### Expected valid UUID string

**Error message**:

```
TypeError: Model Event, field 'id': expected valid UUID string, got 'not-a-uuid'
```

**Cause**: You passed a string to a `UUID` field, but the string is not a valid UUID
format.

**Solution**: Pass a valid UUID string or `UUID` object:

```python
from uuid import UUID, uuid4

# CORRECT: valid UUID string (auto-converted)
db.add_node(workflow, "Event", "Create", "create", {
    "id": "550e8400-e29b-41d4-a716-446655440000",
})

# CORRECT: UUID object
db.add_node(workflow, "Event", "Create", "create", {
    "id": uuid4(),
})

# WRONG: not a UUID format
db.add_node(workflow, "Event", "Create", "create", {
    "id": "event-123",  # TypeError
})
```

---

### Expected ISO datetime string

**Error message**:

```
TypeError: Model Event, field 'started_at': expected ISO datetime string,
got 'March 15, 2026'
```

**Cause**: You passed a string to a `datetime` field, but the string is not in ISO
8601 format.

**Solution**: Use ISO format strings or `datetime` objects:

```python
from datetime import datetime

# CORRECT: ISO format string (auto-converted)
db.add_node(workflow, "Event", "Create", "create", {
    "started_at": "2026-03-15T10:00:00",
})

# CORRECT: ISO format with timezone
db.add_node(workflow, "Event", "Create", "create", {
    "started_at": "2026-03-15T10:00:00Z",  # Z is converted to +00:00
})

# CORRECT: datetime object
db.add_node(workflow, "Event", "Create", "create", {
    "started_at": datetime(2026, 3, 15, 10, 0, 0),
})

# WRONG: non-ISO format
db.add_node(workflow, "Event", "Create", "create", {
    "started_at": "March 15, 2026",  # TypeError
})
```

---

### Type error in record N of bulk operation

**Error message**:

```
TypeError: Type error in record 2 of bulk_create:
Type error in bulk_create operation on User:
Model User, field 'age': expected int, got bool.
```

**Cause**: One of the records in a bulk operation has a type mismatch. The error
message indicates which record (0-indexed) contains the problem.

**Solution**: Fix the type in the indicated record:

```python
# The error says "record 2" (0-indexed, so the third record)
db.add_node(workflow, "User", "BulkCreate", "bulk_create", {
    "records": [
        {"name": "Alice", "age": 30},   # record 0: OK
        {"name": "Bob", "age": 25},     # record 1: OK
        {"name": "Charlie", "age": True},  # record 2: ERROR - bool not int
    ],
})

# Fix:
db.add_node(workflow, "User", "BulkCreate", "bulk_create", {
    "records": [
        {"name": "Alice", "age": 30},
        {"name": "Bob", "age": 25},
        {"name": "Charlie", "age": 28},  # Fixed: actual int
    ],
})
```

---

## Cross-Instance Confusion

**Symptom**: Operations seem to affect the wrong data, or you get "model not
registered" errors even though you registered the model.

**Cause**: You have multiple `DataFlow` instances and are mixing them up. Each
instance has its own model registry, node registry, workflow binder, and tenant
context switch.

**Solution**: Ensure you use the same `DataFlow` instance throughout a workflow:

```python
db_primary = DataFlow("sqlite:///primary.db")
db_analytics = DataFlow("sqlite:///analytics.db")

@db_primary.model
class User:
    name: str

@db_analytics.model
class Report:
    title: str

# WRONG: using db_analytics to create a User workflow
# db_analytics.add_node(workflow, "User", "Create", ...)  # Error: User not in analytics

# CORRECT: use the instance where the model is registered
workflow = db_primary.create_workflow("user_ops")
db_primary.add_node(workflow, "User", "Create", "create", {"name": "Alice"})
results, _ = db_primary.execute_workflow(workflow)
```

To check which models are available on which instance:

```python
print("Primary models:", list(db_primary.get_available_nodes().keys()))
print("Analytics models:", list(db_analytics.get_available_nodes().keys()))
```

---

## Async Context Issues

### Tenant context leaking between async tasks

**Symptom**: One async task's tenant context appears in another task.

**Cause**: This should not happen because `contextvars` provides per-task isolation.
If you see this, you may be sharing context across tasks manually.

**Solution**: Always use `aswitch()` within the task that needs the context:

```python
import asyncio

ctx = db.tenant_context

async def task_a():
    async with ctx.aswitch("acme"):
        # This context is isolated to task_a
        await asyncio.sleep(1)
        print(ctx.get_current_tenant())  # "acme"

async def task_b():
    async with ctx.aswitch("globex"):
        # This context is isolated to task_b
        await asyncio.sleep(1)
        print(ctx.get_current_tenant())  # "globex"

# Both run concurrently with isolated contexts
await asyncio.gather(task_a(), task_b())
```

### Using sync `switch()` in async code

**Symptom**: Context switching works but does not propagate to awaited coroutines.

**Cause**: While `switch()` uses `contextvars` (which propagates to async), you should
prefer `aswitch()` in async code for consistency and clarity.

**Solution**: Use `aswitch()` in async code:

```python
# In async functions, use aswitch
async def async_operation():
    async with ctx.aswitch("acme"):
        await do_async_work()

# In sync functions, use switch
def sync_operation():
    with ctx.switch("acme"):
        do_sync_work()
```

---

## Getting Help

If your issue is not listed here:

1. Check the error message carefully -- DataFlow provides context-rich error messages
   with suggestions for resolution.
2. Use `db.get_available_nodes()` to verify which models and operations are available.
3. Use `db.tenant_context.get_stats()` to check tenant context state.
4. Enable debug logging to see internal operations:

```python
import logging
logging.getLogger("dataflow").setLevel(logging.DEBUG)
```

This will output debug messages from `dataflow.workflow_binding` and
`dataflow.tenant_context` loggers, showing workflow creation, node resolution,
and context switches as they happen.

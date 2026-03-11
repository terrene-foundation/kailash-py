# Multi-Tenant Examples

Practical examples demonstrating DataFlow's tenant context switching API introduced in
TODO-155. This API provides sync and async context managers for safely switching
between tenant contexts with automatic restoration.

---

## Table of Contents

- [Setup](#setup)
- [Registering and Managing Tenants](#registering-and-managing-tenants)
- [Sync Context Switching](#sync-context-switching)
- [Async Context Switching](#async-context-switching)
- [Nested Context Switches](#nested-context-switches)
- [Tenant Lifecycle Management](#tenant-lifecycle-management)
- [Statistics and Monitoring](#statistics-and-monitoring)
- [Requiring Tenant Context](#requiring-tenant-context)
- [Security Best Practices](#security-best-practices)
- [Global Tenant Access](#global-tenant-access)

---

## Setup

All examples assume the following setup:

```python
from dataflow import DataFlow

db = DataFlow("postgresql://localhost/myapp", multi_tenant=True)

@db.model
class User:
    name: str
    email: str
    active: bool = True

@db.model
class Document:
    title: str
    content: str
    owner_id: int
```

---

## Registering and Managing Tenants

Before switching to a tenant context, you must register the tenant. Registration
stores tenant metadata and validates the tenant ID.

### Register a Tenant

```python
ctx = db.tenant_context

# Basic registration
tenant_a = ctx.register_tenant("acme", "Acme Corporation")
print(tenant_a.tenant_id)   # "acme"
print(tenant_a.name)        # "Acme Corporation"
print(tenant_a.active)      # True

# Registration with metadata
tenant_b = ctx.register_tenant("globex", "Globex Inc", metadata={
    "plan": "enterprise",
    "region": "us-west-2",
    "max_users": 500,
})
print(tenant_b.metadata["plan"])  # "enterprise"
```

### List Registered Tenants

```python
tenants = ctx.list_tenants()
for tenant in tenants:
    print(f"{tenant.tenant_id}: {tenant.name} (active={tenant.active})")
```

### Check Tenant Status

```python
print(ctx.is_tenant_registered("acme"))   # True
print(ctx.is_tenant_registered("unknown"))  # False

print(ctx.is_tenant_active("acme"))    # True
```

### Get Tenant Info

```python
tenant = ctx.get_tenant("acme")
if tenant:
    print(f"Name: {tenant.name}")
    print(f"Active: {tenant.active}")
    print(f"Created: {tenant.created_at}")
    print(f"Metadata: {tenant.metadata}")
```

### Unregister a Tenant

```python
# Can only unregister a tenant that is not currently active in context
ctx.unregister_tenant("globex")
```

---

## Sync Context Switching

Use `ctx.switch()` for synchronous code. The context manager guarantees that the
previous tenant context is restored when the block exits, even if an exception occurs.

### Basic Switch

```python
ctx = db.tenant_context

with ctx.switch("acme") as tenant_info:
    print(f"Operating as: {tenant_info.name}")  # "Acme Corporation"

    # All DataFlow operations are now in the "acme" context
    workflow = db.create_workflow("acme_ops")
    db.add_node(workflow, "User", "Create", "create_user", {
        "name": "Alice",
        "email": "alice@acme.com",
    })
    results, _ = db.execute_workflow(workflow)
    print(f"Created user: {results['create_user']}")

# Context is automatically restored here
print(ctx.get_current_tenant())  # None (or previous tenant)
```

### Multiple Sequential Switches

```python
ctx = db.tenant_context

# Process each tenant in sequence
for tenant_id in ["acme", "globex"]:
    with ctx.switch(tenant_id) as tenant_info:
        workflow = db.create_workflow(f"{tenant_id}_count")
        db.add_node(workflow, "User", "Count", "count_users", {})
        results, _ = db.execute_workflow(workflow)
        print(f"{tenant_info.name}: {results['count_users']} users")
```

### Exception Safety

The context manager guarantees restoration even on errors:

```python
ctx = db.tenant_context

try:
    with ctx.switch("acme"):
        # This will raise, but context is still restored
        workflow = db.create_workflow("failing_op")
        db.add_node(workflow, "User", "Read", "read_user", {"id": -1})
        results, _ = db.execute_workflow(workflow)
except Exception as e:
    print(f"Error: {e}")

# Context is properly restored despite the exception
print(ctx.get_current_tenant())  # None
```

---

## Async Context Switching

Use `ctx.aswitch()` for asynchronous code. It has identical semantics to `switch()`
but works with `async with` and `await`.

### Basic Async Switch

```python
import asyncio

ctx = db.tenant_context

async def process_tenant_data():
    async with ctx.aswitch("acme") as tenant_info:
        print(f"Async operating as: {tenant_info.name}")

        # Perform async operations within tenant context
        workflow = db.create_workflow("async_ops")
        db.add_node(workflow, "User", "List", "list_users", {})
        results, _ = db.execute_workflow(workflow)
        return results["list_users"]

users = asyncio.run(process_tenant_data())
```

### Concurrent Tenant Processing

The `contextvars` module ensures each async task maintains its own tenant context:

```python
import asyncio

ctx = db.tenant_context

async def count_users_for_tenant(tenant_id):
    async with ctx.aswitch(tenant_id) as tenant_info:
        workflow = db.create_workflow(f"count_{tenant_id}")
        db.add_node(workflow, "User", "Count", "count_users", {})
        results, _ = db.execute_workflow(workflow)
        return tenant_info.name, results["count_users"]

async def main():
    # Run concurrently - each task has its own context
    tasks = [
        count_users_for_tenant("acme"),
        count_users_for_tenant("globex"),
    ]
    results = await asyncio.gather(*tasks)
    for name, count in results:
        print(f"{name}: {count} users")

asyncio.run(main())
```

---

## Nested Context Switches

You can nest context switches. Each level maintains its own previous context and
restores it properly when exiting.

```python
ctx = db.tenant_context

print(ctx.get_current_tenant())  # None

with ctx.switch("acme"):
    print(ctx.get_current_tenant())  # "acme"

    # Nested switch to a different tenant
    with ctx.switch("globex"):
        print(ctx.get_current_tenant())  # "globex"

        # Operations here run in "globex" context
        workflow = db.create_workflow("globex_nested")
        db.add_node(workflow, "User", "Count", "count", {})
        results, _ = db.execute_workflow(workflow)

    # Back to "acme" after inner context exits
    print(ctx.get_current_tenant())  # "acme"

# Back to None after outer context exits
print(ctx.get_current_tenant())  # None
```

### Nested Async Switches

```python
async def nested_async_example():
    ctx = db.tenant_context

    async with ctx.aswitch("acme"):
        print(ctx.get_current_tenant())  # "acme"

        async with ctx.aswitch("globex"):
            print(ctx.get_current_tenant())  # "globex"

        print(ctx.get_current_tenant())  # "acme" (restored)

    print(ctx.get_current_tenant())  # None (restored)
```

---

## Tenant Lifecycle Management

Tenants follow a lifecycle: register, activate/deactivate, unregister.

### Full Lifecycle Example

```python
ctx = db.tenant_context

# 1. Register
tenant = ctx.register_tenant("acme", "Acme Corporation", metadata={
    "plan": "enterprise",
})
print(f"Registered: {tenant.tenant_id}, active={tenant.active}")
# Output: Registered: acme, active=True

# 2. Use the tenant
with ctx.switch("acme"):
    workflow = db.create_workflow("setup")
    db.add_node(workflow, "User", "Create", "create_admin", {
        "name": "Admin",
        "email": "admin@acme.com",
    })
    db.execute_workflow(workflow)

# 3. Deactivate (temporarily disable access)
ctx.deactivate_tenant("acme")
print(f"Active: {ctx.is_tenant_active('acme')}")
# Output: Active: False

# 4. Attempting to switch to deactivated tenant raises ValueError
try:
    with ctx.switch("acme"):
        pass
except ValueError as e:
    print(e)
    # "Tenant 'acme' is not active. Use activate_tenant() to reactivate it."

# 5. Reactivate
ctx.activate_tenant("acme")
print(f"Active: {ctx.is_tenant_active('acme')}")
# Output: Active: True

# 6. Use again after reactivation
with ctx.switch("acme"):
    workflow = db.create_workflow("after_reactivation")
    db.add_node(workflow, "User", "Count", "count", {})
    results, _ = db.execute_workflow(workflow)
    print(f"Users: {results['count']}")

# 7. Unregister (removes tenant entirely)
# Note: cannot unregister while tenant is the active context
ctx.unregister_tenant("acme")
print(f"Registered: {ctx.is_tenant_registered('acme')}")
# Output: Registered: False
```

---

## Statistics and Monitoring

Track context switching activity using `get_stats()`.

```python
ctx = db.tenant_context

# Register tenants
ctx.register_tenant("acme", "Acme Corporation")
ctx.register_tenant("globex", "Globex Inc")
ctx.deactivate_tenant("globex")

# Perform some switches
with ctx.switch("acme"):
    pass

# Check stats
stats = ctx.get_stats()
print(f"Total tenants:    {stats['total_tenants']}")     # 2
print(f"Active tenants:   {stats['active_tenants']}")    # 1
print(f"Total switches:   {stats['total_switches']}")    # 1
print(f"Active switches:  {stats['active_switches']}")   # 0
print(f"Current tenant:   {stats['current_tenant']}")    # None
```

### Monitoring During Execution

```python
with ctx.switch("acme"):
    stats = ctx.get_stats()
    print(f"Active switches: {stats['active_switches']}")  # 1
    print(f"Current tenant:  {stats['current_tenant']}")   # "acme"

    with ctx.switch("acme"):  # Same tenant, still counted
        stats = ctx.get_stats()
        print(f"Active switches: {stats['active_switches']}")  # 2
        print(f"Total switches:  {stats['total_switches']}")   # 3 (cumulative)
```

---

## Requiring Tenant Context

Use `require_tenant()` to enforce that an operation runs within a tenant context. This
is useful for middleware, service layers, or any code that must not run without tenant
isolation.

```python
ctx = db.tenant_context

def create_user_for_tenant(name, email):
    """Create a user, requiring an active tenant context."""
    # This will raise RuntimeError if no tenant context is set
    tenant_id = ctx.require_tenant()
    print(f"Creating user for tenant: {tenant_id}")

    workflow = db.create_workflow("create_user")
    db.add_node(workflow, "User", "Create", "create_user", {
        "name": name,
        "email": email,
    })
    return db.execute_workflow(workflow)

# Without context -- raises RuntimeError
try:
    create_user_for_tenant("Alice", "alice@example.com")
except RuntimeError as e:
    print(e)
    # "No tenant context is active.
    #  Use 'with db.tenant_context.switch(tenant_id):' to set a tenant context."

# With context -- works
with ctx.switch("acme"):
    results, run_id = create_user_for_tenant("Alice", "alice@acme.com")
    print(f"Created: {results['create_user']}")
```

---

## Security Best Practices

### Always Use Context Managers

Never set tenant context manually outside a context manager. The context manager
ensures automatic cleanup:

```python
# CORRECT: Context manager handles cleanup
with ctx.switch("acme"):
    do_work()

# INCORRECT: Manual context management risks leaking state
# _current_tenant.set("acme")  -- Do not do this
# do_work()
# _current_tenant.set(None)    -- May not run on exception
```

### Validate Tenant Before Operations

Use `require_tenant()` in service functions that must operate within a tenant:

```python
def sensitive_operation():
    tenant_id = ctx.require_tenant()
    # Proceed knowing we have a valid, active tenant context
```

### Deactivate Instead of Delete

When a tenant should be temporarily blocked, deactivate rather than unregister. This
preserves the tenant record and prevents accidental data loss:

```python
# Temporary suspension
ctx.deactivate_tenant("suspended_tenant")

# Later reactivation
ctx.activate_tenant("suspended_tenant")
```

### Check Tenant Activity in Middleware

For web applications, validate tenant context in request middleware:

```python
def tenant_middleware(request):
    tenant_id = extract_tenant_from_request(request)

    if not ctx.is_tenant_registered(tenant_id):
        raise PermissionError(f"Unknown tenant: {tenant_id}")

    if not ctx.is_tenant_active(tenant_id):
        raise PermissionError(f"Tenant is suspended: {tenant_id}")

    with ctx.switch(tenant_id):
        return handle_request(request)
```

### Isolate DataFlow Instances

Each `DataFlow` instance has its own `TenantContextSwitch`. If you use multiple
instances, each maintains independent tenant registrations:

```python
db_primary = DataFlow("postgresql://primary/myapp", multi_tenant=True)
db_analytics = DataFlow("postgresql://analytics/reports", multi_tenant=True)

# Each has its own tenant registry
db_primary.tenant_context.register_tenant("acme", "Acme Corp")
db_analytics.tenant_context.register_tenant("acme", "Acme Corp")

# Switching on one does not affect the other
with db_primary.tenant_context.switch("acme"):
    print(db_primary.tenant_context.get_current_tenant())   # "acme"
    print(db_analytics.tenant_context.get_current_tenant())  # None
```

Note: The `get_current_tenant()` reads from a shared `ContextVar`, so the current
tenant ID is shared per-context (thread or async task), not per DataFlow instance.
If you need fully independent tenant tracking per instance, manage tenant IDs at
the application level.

---

## Global Tenant Access

For code that needs to check the current tenant without a `TenantContextSwitch`
instance, use the module-level helper:

```python
from dataflow import get_current_tenant_id

def log_operation(operation_name):
    tenant_id = get_current_tenant_id()
    if tenant_id:
        print(f"[{tenant_id}] {operation_name}")
    else:
        print(f"[no tenant] {operation_name}")

# Usage
with ctx.switch("acme"):
    log_operation("create_user")  # "[acme] create_user"

log_operation("system_task")  # "[no tenant] system_task"
```

This is particularly useful in logging, auditing, or utility functions that do not
have direct access to the DataFlow instance.

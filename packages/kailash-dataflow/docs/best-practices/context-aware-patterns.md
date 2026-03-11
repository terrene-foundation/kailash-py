# Best Practices: Context-Aware Patterns

Guidelines for effectively using DataFlow's Context-Aware Architecture features
introduced in Phase 5: TypeAwareFieldProcessor, DataFlowWorkflowBinder, and
TenantContextSwitch.

---

## Table of Contents

- [Workflow Binding vs Direct WorkflowBuilder](#workflow-binding-vs-direct-workflowbuilder)
- [Multi-Tenant Architecture Patterns](#multi-tenant-architecture-patterns)
- [Type Processing Best Practices](#type-processing-best-practices)
- [Performance Considerations](#performance-considerations)
- [Error Handling Patterns](#error-handling-patterns)
- [Testing Patterns](#testing-patterns)

---

## Workflow Binding vs Direct WorkflowBuilder

### When to Use Workflow Binding (`db.create_workflow()`)

Use the workflow binding API when:

- You are building workflows that operate exclusively on DataFlow models
- You want model and operation validation at workflow construction time
- You prefer the clarity of `"User", "Create"` over `"UserCreateNode"`
- You want automatic runtime creation and do not need custom runtime configuration
- You want to discover available nodes programmatically with `get_available_nodes()`

```python
# Good: Simple DataFlow-only workflow
workflow = db.create_workflow("user_ops")
db.add_node(workflow, "User", "Create", "create_user", {"name": "Alice"})
results, run_id = db.execute_workflow(workflow)
```

### When to Use Raw WorkflowBuilder

Use the raw `WorkflowBuilder` when:

- Your workflow includes non-DataFlow nodes (PythonCode, API calls, logic nodes)
- You need fine-grained runtime configuration (debug mode, cycle execution, etc.)
- You need to use `AsyncLocalRuntime` with specific parameters
- You are composing workflows across multiple frameworks (DataFlow + Nexus + Kaizen)

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime import LocalRuntime

# Good: Mixed workflow with custom and DataFlow nodes
workflow = WorkflowBuilder()
workflow.add_node("UserListNode", "list_users", {})
workflow.add_node("PythonCode", "filter_active", {
    "code": "result = [u for u in inputs['users'] if u.get('active')]",
}, {"list_users": "users"})

runtime = LocalRuntime(debug=True)
results, run_id = runtime.execute(workflow.build())
```

### Mixing Both

You can start with the binding API and add raw nodes when needed. Since
`db.create_workflow()` returns a standard `WorkflowBuilder`, both approaches
are compatible:

```python
workflow = db.create_workflow("mixed")

# Binding API for DataFlow nodes
db.add_node(workflow, "User", "List", "list_users", {})

# Raw API for custom processing
workflow.add_node("PythonCode", "transform", {
    "code": "result = len(inputs.get('data', []))",
}, {"list_users": "data"})

# Execute with custom runtime
from kailash.runtime import LocalRuntime
runtime = LocalRuntime(debug=True)
results, run_id = runtime.execute(workflow.build())
```

---

## Multi-Tenant Architecture Patterns

### Pattern 1: Request-Scoped Tenancy

For web applications, switch tenant context per request:

```python
def handle_request(request):
    tenant_id = request.headers.get("X-Tenant-ID")

    if not db.tenant_context.is_tenant_registered(tenant_id):
        return {"error": "Unknown tenant"}, 403

    if not db.tenant_context.is_tenant_active(tenant_id):
        return {"error": "Tenant suspended"}, 403

    with db.tenant_context.switch(tenant_id):
        return process_request(request)
```

### Pattern 2: Background Job Tenancy

For background tasks, pass tenant context explicitly:

```python
async def process_batch_job(tenant_id, job_data):
    async with db.tenant_context.aswitch(tenant_id):
        for item in job_data:
            workflow = db.create_workflow("process_item")
            db.add_node(workflow, "Order", "Create", "create_order", item)
            db.execute_workflow(workflow)
```

### Pattern 3: Cross-Tenant Operations

When an operation needs to touch multiple tenants (e.g., aggregation, reporting),
switch contexts sequentially:

```python
def generate_cross_tenant_report(tenant_ids):
    report = {}
    for tenant_id in tenant_ids:
        with db.tenant_context.switch(tenant_id):
            workflow = db.create_workflow(f"report_{tenant_id}")
            db.add_node(workflow, "Order", "Count", "count_orders", {})
            results, _ = db.execute_workflow(workflow)
            report[tenant_id] = results["count_orders"]
    return report
```

### Pattern 4: Tenant Registration at Startup

Register all known tenants when the application starts:

```python
def initialize_app():
    db = DataFlow("postgresql://localhost/myapp", multi_tenant=True)

    # Register tenants from configuration or database
    tenants_config = load_tenants_from_config()
    for t in tenants_config:
        db.tenant_context.register_tenant(
            t["id"],
            t["name"],
            metadata=t.get("metadata", {}),
        )
        if not t.get("active", True):
            db.tenant_context.deactivate_tenant(t["id"])

    return db
```

### Pattern 5: Service Layer with Required Context

Enforce tenant context at the service layer:

```python
class UserService:
    def __init__(self, db):
        self.db = db

    def create_user(self, name, email):
        # Enforces that a tenant context is active
        tenant_id = self.db.tenant_context.require_tenant()

        workflow = self.db.create_workflow("create_user")
        self.db.add_node(workflow, "User", "Create", "create_user", {
            "name": name,
            "email": email,
        })
        results, _ = self.db.execute_workflow(workflow)
        return results["create_user"]
```

---

## Type Processing Best Practices

### Let the Processor Work Automatically

The `TypeAwareFieldProcessor` runs inside DataFlow nodes. You do not need to call it
directly for normal operations. Just pass correctly typed values:

```python
@db.model
class Product:
    name: str
    price: float
    quantity: int
    id: str  # String primary key

# Good: correct types
workflow = db.create_workflow("create_product")
db.add_node(workflow, "Product", "Create", "create", {
    "id": "prod-001",
    "name": "Widget",
    "price": 29.99,
    "quantity": 10,
})
```

### Use Non-Strict Mode (Default)

Non-strict mode provides helpful automatic conversions:

```python
from uuid import UUID
from datetime import datetime

@db.model
class Event:
    id: UUID
    name: str
    started_at: datetime

# Non-strict: strings are auto-converted to UUID and datetime
db.add_node(workflow, "Event", "Create", "create_event", {
    "id": "550e8400-e29b-41d4-a716-446655440000",  # str -> UUID
    "name": "Launch Party",
    "started_at": "2026-03-15T10:00:00",            # str -> datetime
})
```

### Enable Strict Mode for Critical Data

When data integrity is paramount (financial records, audit logs), use strict mode
with the `TypeAwareFieldProcessor` directly:

```python
from dataflow import TypeAwareFieldProcessor

processor = TypeAwareFieldProcessor(
    model_fields={
        "amount": {"type": float, "required": True},
        "currency": {"type": str, "required": True},
    },
    model_name="Transaction",
)

# Strict mode: no conversions, exact types required
validated = processor.process_record(
    {"amount": 100.50, "currency": "USD"},
    operation="create",
    strict=True,
)
```

### Watch for Bool-to-Int Issues

DataFlow explicitly rejects `bool` values for `int` fields, unlike standard Python:

```python
# Python: isinstance(True, int) -> True
# DataFlow: raises TypeError

# BAD: passing bool where int is expected
db.add_node(workflow, "User", "Create", "create", {
    "name": "Alice",
    "age": True,  # TypeError: expected int, got bool
})

# GOOD: pass the correct type
db.add_node(workflow, "User", "Create", "create", {
    "name": "Alice",
    "age": 30,
})
```

---

## Performance Considerations

### Workflow Creation Overhead

`db.create_workflow()` has minimal overhead compared to raw `WorkflowBuilder()`. The
additional cost is:

- One dict lookup to track the workflow internally
- A UUID generation for auto-generated workflow IDs (skipped if you provide an ID)

For high-frequency operations, provide explicit workflow IDs to avoid UUID generation:

```python
# Slightly faster: explicit ID, no UUID generation
workflow = db.create_workflow("batch_import")
```

### Node Resolution Cost

`db.add_node()` validates the model and operation on each call. This involves:

- Two dict lookups (model registry + node registry)
- One string concatenation for the node type

This is negligible for typical workflows. For extremely hot paths with hundreds of
nodes per workflow, use the raw `WorkflowBuilder` to bypass validation:

```python
# For very high-frequency, many-node workflows
from kailash.workflow.builder import WorkflowBuilder

workflow = WorkflowBuilder()
for i in range(1000):
    workflow.add_node("UserCreateNode", f"create_{i}", {"name": f"user_{i}"})
```

### Tenant Context Switching Cost

Context switching uses Python's `contextvars` module, which is O(1) for get/set
operations. The overhead per switch is:

- One `ContextVar.set()` call
- One dict lookup (tenant registry)
- Counter increments (stats tracking)

This is suitable for per-request switching in web applications with thousands of
requests per second.

### Memory Considerations

- Each `DataFlowWorkflowBinder` tracks created workflows in `_workflows` dict.
  For long-running applications that create many one-off workflows, consider
  that these references are retained.
- Each `TenantContextSwitch` stores `TenantInfo` objects. Memory usage scales
  linearly with the number of registered tenants.

---

## Error Handling Patterns

### Catch Specific Exceptions

```python
# Model/operation validation errors
try:
    db.add_node(workflow, "Unknown", "Create", "node_id", {})
except ValueError as e:
    # Model not registered or invalid operation
    handle_validation_error(e)

# Type validation errors
try:
    db.add_node(workflow, "User", "Create", "node_id", {
        "age": True,  # bool for int field
    })
except TypeError as e:
    # Type mismatch caught by TypeAwareFieldProcessor
    handle_type_error(e)

# Tenant context errors
try:
    db.tenant_context.switch("unknown")
except ValueError as e:
    # Tenant not registered or not active
    handle_tenant_error(e)

# Missing tenant context
try:
    db.tenant_context.require_tenant()
except RuntimeError as e:
    # No active tenant context
    handle_missing_context(e)
```

### Structured Error Handling in Production

```python
import logging

logger = logging.getLogger("app")

def execute_tenant_workflow(db, tenant_id, workflow_fn):
    """Execute a workflow within a tenant context with structured error handling."""
    ctx = db.tenant_context

    if not ctx.is_tenant_registered(tenant_id):
        logger.error("Tenant %s not registered", tenant_id)
        raise ValueError(f"Unknown tenant: {tenant_id}")

    if not ctx.is_tenant_active(tenant_id):
        logger.warning("Attempted switch to inactive tenant %s", tenant_id)
        raise ValueError(f"Tenant suspended: {tenant_id}")

    with ctx.switch(tenant_id):
        try:
            return workflow_fn(db)
        except TypeError as e:
            logger.error("Type validation failed for tenant %s: %s", tenant_id, e)
            raise
        except Exception as e:
            logger.error("Workflow failed for tenant %s: %s", tenant_id, e)
            raise
```

---

## Testing Patterns

DataFlow testing follows the 3-tier strategy. Here is how to test Context-Aware
features at each tier.

### Tier 1: Unit Tests (Mocking Allowed)

Test type processor logic, tenant registration, and workflow construction in
isolation:

```python
import pytest
from dataflow import TypeAwareFieldProcessor, TenantContextSwitch

class TestTypeProcessor:
    def test_bool_rejected_for_int_field(self):
        processor = TypeAwareFieldProcessor(
            {"age": {"type": int, "required": True}},
            model_name="User",
        )
        with pytest.raises(TypeError, match="expected int, got bool"):
            processor.validate_field("age", True)

    def test_uuid_string_converted(self):
        from uuid import UUID
        processor = TypeAwareFieldProcessor(
            {"id": {"type": UUID, "required": True}},
            model_name="Event",
        )
        result = processor.validate_field("id", "550e8400-e29b-41d4-a716-446655440000")
        assert isinstance(result, UUID)
```

### Tier 2: Integration Tests (NO MOCKING)

Test workflow binding and tenant switching with a real database:

```python
import pytest
from dataflow import DataFlow

@pytest.fixture
def db():
    db = DataFlow("sqlite:///:memory:")

    @db.model
    class User:
        name: str
        email: str

    return db

def test_workflow_binding_creates_user(db):
    workflow = db.create_workflow("test_create")
    db.add_node(workflow, "User", "Create", "create_user", {
        "name": "Test User",
        "email": "test@example.com",
    })
    results, run_id = db.execute_workflow(workflow)

    assert results["create_user"] is not None
    assert run_id is not None

def test_tenant_context_isolation(db):
    ctx = db.tenant_context
    ctx.register_tenant("tenant-a", "Tenant A")
    ctx.register_tenant("tenant-b", "Tenant B")

    with ctx.switch("tenant-a"):
        assert ctx.get_current_tenant() == "tenant-a"

        with ctx.switch("tenant-b"):
            assert ctx.get_current_tenant() == "tenant-b"

        assert ctx.get_current_tenant() == "tenant-a"

    assert ctx.get_current_tenant() is None
```

### Tier 3: End-to-End Tests (NO MOCKING)

Test full user journeys with real databases:

```python
import pytest
from dataflow import DataFlow

@pytest.fixture
def production_db():
    # Use real PostgreSQL for E2E tests
    db = DataFlow("postgresql://test:test@localhost/test_e2e")

    @db.model
    class User:
        name: str
        email: str

    @db.model
    class Order:
        user_id: int
        product: str

    return db

def test_multi_tenant_order_flow(production_db):
    db = production_db
    ctx = db.tenant_context

    ctx.register_tenant("acme", "Acme Corp")
    ctx.register_tenant("globex", "Globex Inc")

    # Create user in tenant-a
    with ctx.switch("acme"):
        workflow = db.create_workflow("create_user")
        db.add_node(workflow, "User", "Create", "create_user", {
            "name": "Alice",
            "email": "alice@acme.com",
        })
        results, _ = db.execute_workflow(workflow)
        assert results["create_user"] is not None

    # Verify stats
    stats = ctx.get_stats()
    assert stats["total_switches"] >= 1
    assert stats["current_tenant"] is None
```

### Test Checklist

For comprehensive coverage of Context-Aware features, ensure you test:

- [ ] Model validation errors (unregistered model, invalid operation)
- [ ] Type validation (correct types, safe conversions, strict mode, bool/int)
- [ ] Tenant registration (success, duplicate, invalid ID)
- [ ] Tenant switching (sync, async, nested, exception safety)
- [ ] Tenant lifecycle (register, deactivate, activate, unregister)
- [ ] Context restoration after exceptions
- [ ] `require_tenant()` with and without active context
- [ ] `get_available_nodes()` with and without model filter
- [ ] Cross-model workflows with multiple DataFlow nodes
- [ ] Mixed workflows (DataFlow nodes + raw nodes)

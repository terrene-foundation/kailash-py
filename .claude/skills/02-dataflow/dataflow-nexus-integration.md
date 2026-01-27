---
name: dataflow-nexus-integration
description: "Integrate DataFlow with Nexus for multi-channel APIs. Use when DataFlow Nexus, Nexus blocking, Nexus integration, or prevent blocking startup."
---

# DataFlow + Nexus Integration

Configuration patterns for integrating DataFlow with Nexus for multi-channel APIs.

> **Skill Metadata**
> Category: `dataflow`
> Priority: `CRITICAL`
> Related Skills: [`nexus-quickstart`](#), [`dataflow-models`](#)
> Related Subagents: `dataflow-specialist`, `nexus-specialist`

> **Version Info**: DataFlow v0.10.15, Nexus v1.1.3

## Quick Reference

- **DataFlow v0.10.15**: `auto_migrate=True` (default) works in Docker/FastAPI via SyncDDLExecutor
- **Nexus v1.1.3**: Use `auto_discovery=False` to prevent blocking during startup
- **Integration**: DataFlow nodes must be manually registered as workflows with Nexus

## Core Pattern

```python
from dataflow import DataFlow
from nexus import Nexus
from kailash.workflow.builder import WorkflowBuilder

# Step 1: Initialize DataFlow
db = DataFlow(
    database_url="postgresql://user:pass@localhost/db",
    auto_migrate=True,  # DEFAULT - works in Docker/FastAPI via SyncDDLExecutor
)

# Step 2: Define models
@db.model
class Product:
    name: str
    price: float
    active: bool = True

# Step 3: Create Nexus platform
app = Nexus(
    api_port=8000,
    mcp_port=3001,
    auto_discovery=False,  # CRITICAL: Prevents blocking during startup
)

# Step 4: Register DataFlow workflows with Nexus
# DataFlow auto-generates 11 nodes per model - register them as workflows
workflow = WorkflowBuilder()
workflow.add_node("ProductCreateNode", "create", {
    "name": "${input.name}",
    "price": "${input.price}"
})
app.register("create_product", workflow.build())

# Step 5: Start the platform
app.start()  # Blocks until Ctrl+C
```

## Nexus Constructor Parameters (v1.1.3)

```python
app = Nexus(
    api_port=8000,              # REST API port (default: 8000)
    mcp_port=3001,              # MCP server port (default: 3001)
    enable_auth=None,           # Authentication (auto-enabled in production)
    enable_monitoring=False,    # Metrics collection
    rate_limit=100,             # Requests per minute (None to disable)
    auto_discovery=False,       # Workflow auto-discovery (keep False!)
    enable_http_transport=False,# HTTP transport for MCP
    enable_sse_transport=False, # SSE transport for MCP
    enable_discovery=False,     # MCP service discovery
    enable_durability=True,     # Durability/caching
)
```

**NOTE**: The following parameters do NOT exist in Nexus v1.1.3:
- `title`
- `enable_api`, `enable_cli`, `enable_mcp`
- `dataflow_config`
- `auth_config`

## DataFlow Configuration (v0.10.15)

```python
db = DataFlow(
    database_url="postgresql://...",
    auto_migrate=True,       # DEFAULT - works in Docker/FastAPI
    pool_size=3,             # Reduced: PgBouncer handles pooling
    pool_max_overflow=2,
    monitoring=True,
    slow_query_threshold=100,
)
```

**Valid Parameters**:
- `existing_schema_mode` and `enable_model_persistence` still exist and are functional
- **Deprecated**: `skip_registry`, `skip_migration`, `connection_pool_size`, `enable_metrics`

## Common Mistakes

### Mistake 1: Using auto_discovery=True

```python
# WRONG - auto_discovery=True causes blocking
app = Nexus(auto_discovery=True)  # BLOCKS! Scans filesystem
```

**Fix:**
```python
# CORRECT
app = Nexus(auto_discovery=False)
```

### Mistake 2: Expecting dataflow_config Parameter

```python
# WRONG - dataflow_config does NOT exist in Nexus v1.1.3!
app = Nexus(
    dataflow_config={"integration": db}  # THIS WILL FAIL
)
```

**Fix: Register workflows manually:**
```python
# CORRECT - Manual workflow registration
app = Nexus(auto_discovery=False)

workflow = WorkflowBuilder()
workflow.add_node("ProductListNode", "list", {"filter": "${input.filter}"})
app.register("list_products", workflow.build())
```

## Related Patterns

- **For Nexus basics**: See [`nexus-quickstart`](#)
- **For DataFlow models**: See [`dataflow-models`](#)

## When to Escalate to Subagent

Use `dataflow-specialist` or `nexus-specialist` when:
- Complex workflow registration patterns
- Performance optimization needed
- Multi-database integration
- Custom endpoint generation logic

## Example: Complete Setup

```python
from dataflow import DataFlow
from nexus import Nexus
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime import LocalRuntime

# Initialize DataFlow
db = DataFlow(
    database_url="postgresql://user:pass@localhost/ecommerce",
    auto_migrate=True,
)

# Define models
@db.model
class Product:
    sku: str
    name: str
    price: float
    stock: int
    active: bool = True

# Create Nexus platform
app = Nexus(
    api_port=8000,
    mcp_port=3001,
    auto_discovery=False,
    enable_auth=True,
    rate_limit=100,
)

# Register product operations as workflows
for node_name in ["ProductCreateNode", "ProductListNode", "ProductReadNode"]:
    workflow = WorkflowBuilder()
    workflow.add_node(node_name, "op", {"input": "${input}"})
    app.register(node_name.lower(), workflow.build())

# Start platform
app.start()
```

## Troubleshooting

| Issue | Cause | Solution |
|-------|-------|----------|
| Nexus hangs on startup | `auto_discovery=True` | Set `auto_discovery=False` |
| Workflow not found | Not registered | Use `app.register(name, workflow)` |
| DataFlow tables not created | `auto_migrate=False` | Use `auto_migrate=True` (default) |

## Quick Tips

- Use `auto_migrate=True` (default) - works in Docker/FastAPI via SyncDDLExecutor
- ALWAYS use `auto_discovery=False` in Nexus to prevent blocking
- Register DataFlow workflows manually with `app.register()`
- Test startup time - should be <2 seconds

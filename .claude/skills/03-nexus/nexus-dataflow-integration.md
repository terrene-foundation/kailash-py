---
skill: nexus-dataflow-integration
description: CRITICAL DataFlow + Nexus integration patterns with blocking fix configuration (auto_discovery=False, auto_migrate=True default)
priority: CRITICAL
tags: [nexus, dataflow, integration, blocking-fix, performance]
---

# Nexus DataFlow Integration

CRITICAL: Proper configuration to prevent blocking on startup.

> **DataFlow v0.11.0**: The parameters `enable_model_persistence`, `skip_migration`, and `existing_schema_mode` have been **removed**. The only critical Nexus-side setting is `auto_discovery=False`. DataFlow's `auto_migrate=True` (default) now works correctly in Docker/FastAPI via SyncDDLExecutor.

## The Problem

Without proper configuration, Nexus + DataFlow causes:

1. **Infinite blocking** during initialization (when `auto_discovery=True`)

## The Solution

```python
from nexus import Nexus
from dataflow import DataFlow

# Step 1: Create Nexus with auto_discovery=False
app = Nexus(
    api_port=8000,
    mcp_port=3001,
    auto_discovery=False  # CRITICAL: Prevents blocking
)

# Step 2: Create DataFlow (defaults work fine in v0.11.0)
db = DataFlow(
    database_url="postgresql://user:pass@host:port/db",
    auto_migrate=True,  # Default - works in Docker/FastAPI via SyncDDLExecutor
)

# Step 3: Register models
@db.model
class User:
    id: str
    email: str
    name: str

# Step 4: Register workflows manually
workflow = WorkflowBuilder()
workflow.add_node("UserCreateNode", "create", {"email": "{{email}}"})
app.register("create_user", workflow.build())

# Step 5: Start
app.start()
```

## Why This Configuration

### `auto_discovery=False` (Nexus)

- Prevents scanning filesystem for workflows
- Avoids re-importing Python modules
- Eliminates infinite blocking issue
- **When to use**: Always when integrating with DataFlow

### `auto_migrate=True` (DataFlow v0.11.0 Default)

- Uses SyncDDLExecutor for synchronous DDL operations
- No event loop issues in Docker/FastAPI
- Automatic schema creation and updates
- **This is the default** -- no special configuration needed

## Complete Working Example

```python
from nexus import Nexus
from dataflow import DataFlow
from kailash.workflow.builder import WorkflowBuilder

# Fast initialization
app = Nexus(
    api_port=8000,
    mcp_port=3001,
    auto_discovery=False  # CRITICAL
)

db = DataFlow(
    database_url="postgresql://localhost:5432/mydb",
)

# Define models
@db.model
class Contact:
    id: str
    name: str
    email: str
    company: str

@db.model
class Company:
    id: str
    name: str
    industry: str

# Create workflow using DataFlow nodes
def create_contact_workflow():
    workflow = WorkflowBuilder()

    # Use DataFlow's auto-generated nodes
    workflow.add_node("ContactCreateNode", "create", {
        "name": "{{name}}",
        "email": "{{email}}",
        "company": "{{company}}"
    })

    return workflow.build()

# Register workflow
app.register("create_contact", create_contact_workflow())

# Start
app.start()
```

## What You Get

With `auto_discovery=False` + DataFlow defaults:

- All CRUD operations (11 nodes per model)
- Connection pooling, caching, metrics
- All Nexus channels (API, CLI, MCP)
- Automatic schema migration via SyncDDLExecutor
- Fast startup

## What You Lose

With `auto_discovery=False`:

- Auto-discovery of workflows (must register manually)

## Using DataFlow Nodes

```python
# DataFlow auto-generates 11 nodes per model:
# CRUD: Create, Read, Update, Delete, List, Upsert, Count
# Bulk: BulkCreate, BulkUpdate, BulkDelete, BulkUpsert

workflow = WorkflowBuilder()

# Create node
workflow.add_node("ContactCreateNode", "create", {
    "name": "{{name}}",
    "email": "{{email}}"
})

# Search node
workflow.add_node("ContactListNode", "search", {
    "filter": {"company": "{{company}}"},
    "limit": 10
})

# Connect nodes
workflow.add_connection("create", "result", "search", "input")

app.register("contact_workflow", workflow.build())
```

## API Usage

```bash
# Create contact via Nexus API
curl -X POST http://localhost:8000/workflows/create_contact/execute \
  -H "Content-Type: application/json" \
  -d '{
    "inputs": {
      "name": "John Doe",
      "email": "john@example.com",
      "company": "Acme Corp"
    }
  }'
```

## Production Pattern

```python
import os

def create_production_app():
    app = Nexus(
        api_port=int(os.getenv("API_PORT", "8000")),
        mcp_port=int(os.getenv("MCP_PORT", "3001")),
        auto_discovery=False,
        enable_auth=True,
        enable_monitoring=True
    )

    db = DataFlow(
        database_url=os.getenv("DATABASE_URL"),
    )

    # Register models
    from .models import Contact, Company  # Import after DataFlow creation

    # Register workflows
    register_workflows(app, db)

    return app

app = create_production_app()
```

## Common Issues

### Blocking on Start

```python
# Must disable auto_discovery
app = Nexus(auto_discovery=False)
```

### Workflows Not Found

```python
# Register manually since auto_discovery is off
app.register("workflow-name", workflow.build())
```

### Schema Not Created

```python
# Ensure auto_migrate=True (default in v0.11.0)
db = DataFlow(
    database_url="postgresql://...",
    auto_migrate=True,  # This is the default
)
```

## Testing Strategy

```python
import pytest
import time

def test_nexus_dataflow_integration():
    # Test fast startup
    start_time = time.time()

    app = Nexus(auto_discovery=False)
    db = DataFlow("sqlite:///:memory:")

    @db.model
    class TestModel:
        id: str
        name: str

    startup_time = time.time() - start_time
    assert startup_time < 2.0, f"Startup too slow: {startup_time}s"

    # Test workflow execution
    workflow = WorkflowBuilder()
    workflow.add_node("TestModelCreateNode", "create", {"name": "test"})
    app.register("test", workflow.build())
```

## Key Takeaways

- **CRITICAL**: Use `auto_discovery=False` with DataFlow
- DataFlow v0.11.0: `auto_migrate=True` (default) works everywhere including Docker/FastAPI
- The parameters `enable_model_persistence`, `skip_migration`, and `existing_schema_mode` have been removed
- All CRUD operations work with default DataFlow config
- Manual workflow registration required with `auto_discovery=False`

## Related Documentation

- [Main Integration Guide](../../sdk-users/guides/dataflow-nexus-integration.md)
- [Blocking Issue Analysis](../../sdk-users/apps/dataflow/docs/integration/nexus-blocking-issue-analysis.md)
- [Working Examples](../../sdk-users/apps/nexus/examples/dataflow-integration/)

## Related Skills

- [nexus-quickstart](#) - Basic Nexus setup
- [dataflow-quickstart](#) - Basic DataFlow setup
- [nexus-production-deployment](#) - Production patterns
- [nexus-troubleshooting](#) - Fix integration issues

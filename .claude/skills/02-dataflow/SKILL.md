---
name: dataflow
description: "Kailash DataFlow - zero-config data operations framework with automatic model-to-node generation and Data Fabric Engine. Use when asking about 'database operations', 'DataFlow', 'database models', 'CRUD operations', 'bulk operations', 'database queries', 'database migrations', 'multi-tenancy', 'multi-instance', 'database transactions', 'PostgreSQL', 'MySQL', 'SQLite', 'MongoDB', 'pgvector', 'vector search', 'document database', 'RAG', 'semantic search', 'existing database', 'database performance', 'database deployment', 'database testing', 'TDD with databases', 'external data sources', 'data products', 'db.source', 'db.product', 'db.start', 'fabric engine', 'source adapters', 'REST source', 'webhooks', or 'data fabric'. DataFlow is NOT an ORM - it generates 11 workflow nodes per SQL model, 8 nodes for MongoDB, and 3 nodes for vector operations."
---

# Kailash DataFlow - Zero-Config Database Framework

DataFlow is a zero-config database framework built on Kailash Core SDK that automatically generates workflow nodes from database models.

## Overview

- **Automatic Node Generation**: 11 nodes per model (@db.model decorator)
- **Multi-Database Support**: PostgreSQL, MySQL, SQLite (SQL) + MongoDB (Document) + pgvector (Vector Search)
- **Enterprise Features**: Multi-tenancy, multi-instance isolation, transactions
- **Zero Configuration**: String IDs preserved, deferred schema operations
- **Developer Experience**: Enhanced errors (DF-XXX codes), strict mode validation, debug agent, CLI tools

## Quick Start

### Express API (Recommended for Simple CRUD)

```python
from dataflow import DataFlow

# Zero-config initialization
db = DataFlow("sqlite:///app.db", auto_migrate=True)

@db.model
class User:
    name: str
    email: str
    active: bool = True

await db.initialize()

# Async Express (default) — 23x faster than workflow primitives
result = await db.express.create("User", {"name": "Alice", "email": "alice@example.com"})
user = await db.express.read("User", str(result["id"]))
users = await db.express.list("User", {"active": True})
count = await db.express.count("User")
await db.express.update("User", str(result["id"]), {"name": "Bob"})
await db.express.delete("User", str(result["id"]))

# Sync Express (CLI scripts, non-async contexts)
result = db.express_sync.create("User", {"name": "Alice", "email": "alice@example.com"})
users = db.express_sync.list("User", {"active": True})
```

### Workflow API (For Multi-Step Operations)

Use WorkflowBuilder only when you need multiple nodes with data flow between them.

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

# Multi-node workflow with connections
workflow = WorkflowBuilder()
workflow.add_node("UserCreateNode", "create_user", {
    "name": "John", "email": "john@example.com"
})

# Execute with context manager (recommended for resource cleanup)
with LocalRuntime() as runtime:
    results, run_id = runtime.execute(workflow.build())
    user_id = results["create_user"]  # Access by node_id
```

## Generated Nodes (11 per model)

Each `@db.model` class generates:

1. `{Model}CreateNode` - Create single record
2. `{Model}ReadNode` - Read by ID
3. `{Model}UpdateNode` - Update record
4. `{Model}DeleteNode` - Delete record
5. `{Model}ListNode` - List with filters
6. `{Model}UpsertNode` - Insert or update (atomic)
7. `{Model}CountNode` - Efficient COUNT(\*) queries
8. `{Model}BulkCreateNode` - Bulk insert
9. `{Model}BulkUpdateNode` - Bulk update
10. `{Model}BulkDeleteNode` - Bulk delete
11. `{Model}BulkUpsertNode` - Bulk upsert

## Critical Rules

- ✅ String IDs preserved (no UUID conversion)
- ✅ Deferred schema operations (safe for Docker/FastAPI)
- ✅ Multi-instance isolation (one DataFlow per database)
- ✅ Result access: `results["node_id"]` (keyed by node_id, value is the node output)
- ❌ NEVER use truthiness checks on filter/data parameters (empty dict `{}` is falsy)
- ❌ ALWAYS use key existence checks: `if "filter" in kwargs` instead of `if kwargs.get("filter")`
- ❌ NEVER use direct SQL when DataFlow nodes exist
- ❌ NEVER use SQLAlchemy/Django ORM alongside DataFlow

## Reference Documentation

### Getting Started

- **[dataflow-quickstart](dataflow-quickstart.md)** - Quick start guide
- **[dataflow-installation](dataflow-installation.md)** - Installation and setup
- **[dataflow-models](dataflow-models.md)** - Defining models with @db.model
- **[dataflow-connection-config](dataflow-connection-config.md)** - Database connection

### Core Operations

- **[dataflow-crud-operations](dataflow-crud-operations.md)** - Create, Read, Update, Delete
- **[dataflow-queries](dataflow-queries.md)** - Query patterns and filtering
- **[dataflow-aggregation](dataflow-aggregation.md)** - SQL aggregation queries (COUNT/SUM/AVG/MIN/MAX GROUP BY)
- **[dataflow-bulk-operations](dataflow-bulk-operations.md)** - Batch operations
- **[dataflow-transactions](dataflow-transactions.md)** - Transaction management
- **[dataflow-connection-isolation](dataflow-connection-isolation.md)** - ⚠️ CRITICAL: ACID guarantees

### Advanced Features

### Data Fabric Engine

- **[dataflow-fabric-engine](dataflow-fabric-engine.md)** - External data sources (`db.source()`), derived products (`@db.product()`), fabric runtime (`db.start()`), 5 source adapters, webhooks, SSRF protection, observability

### Enterprise Features

- **[dataflow-derived-models](dataflow-derived-models.md)** - Application-layer materialized views (`@db.derived_model`)
- **[dataflow-file-import](dataflow-file-import.md)** - File ingestion (CSV/Excel/Parquet/JSON) + `db.express.import_file()`
- **[dataflow-validation-dsl](dataflow-validation-dsl.md)** - Declarative validation (`__validation__` dict)
- **[dataflow-express-cache](dataflow-express-cache.md)** - Model-scoped Express caching with TTL
- **[dataflow-read-replicas](dataflow-read-replicas.md)** - Read/write splitting with `read_url`
- **[dataflow-retention](dataflow-retention.md)** - Data retention (archive/delete/partition policies)
- **[dataflow-events](dataflow-events.md)** - Write event emission + Core SDK EventBus integration

### Advanced Features

- **[dataflow-multi-instance](dataflow-multi-instance.md)** - Multiple database instances
- **[dataflow-multi-tenancy](dataflow-multi-tenancy.md)** - Multi-tenant architectures
- **[dataflow-existing-database](dataflow-existing-database.md)** - Working with existing databases
- **[dataflow-migrations-quick](dataflow-migrations-quick.md)** - Database migrations
- **[dataflow-custom-nodes](dataflow-custom-nodes.md)** - Custom database nodes
- **[dataflow-sqlite-concurrency](dataflow-sqlite-concurrency.md)** - SQLite connection pooling, WAL mode, read/write splitting, memory DB URI patterns

### Developer Experience Tools

- **[dataflow-strict-mode](dataflow-strict-mode.md)** - Build-time validation (4-layer, OFF/WARN/STRICT)
- **[dataflow-debug-agent](dataflow-debug-agent.md)** - Intelligent error analysis (5-stage pipeline)
- **ErrorEnhancer** - Automatic error enhancement (40+ DF-XXX codes)
- **Inspector API** - Self-service debugging (18 introspection methods)
- **CLI Tools** - dataflow-validate, dataflow-analyze, dataflow-debug (5 commands)

### Connection Pool & Monitoring

- **[dataflow-connection-config](dataflow-connection-config.md)** - Pool auto-scaling, env vars, override scenarios
- **[dataflow-monitoring](dataflow-monitoring.md)** - Pool utilization, leak detection, health checks, diagnostics

### ML Integration

- **[dataflow-ml-integration](dataflow-ml-integration.md)** - kailash-ml FeatureStore integration (ConnectionManager, point-in-time queries, polars interop)

### Troubleshooting

- **[dataflow-gotchas](dataflow-gotchas.md)** - Common pitfalls

## Database Support Matrix

| Database   | Type     | Nodes/Model | Driver    |
| ---------- | -------- | ----------- | --------- |
| PostgreSQL | SQL      | 11          | asyncpg   |
| MySQL      | SQL      | 11          | aiomysql  |
| SQLite     | SQL      | 11          | aiosqlite |
| MongoDB    | Document | 8           | Motor     |
| pgvector   | Vector   | 3           | pgvector  |

**Not an ORM**: DataFlow generates workflow nodes, not ORM models. Uses string-based result access and integrates with Kailash's workflow execution model.

## Integration Patterns

### With Nexus (Multi-Channel)

```python
from dataflow import DataFlow
from nexus import Nexus
from kailash.workflow.builder import WorkflowBuilder

db = DataFlow("sqlite:///app.db", auto_migrate=True)
@db.model
class User:
    id: str
    name: str

# Build a workflow using generated nodes, then register with Nexus
workflow = WorkflowBuilder()
workflow.add_node("UserCreateNode", "create_user", {"name": "Alice"})

app = Nexus()
app.register("create_user", workflow.build())
app.start()
```

### With Core SDK (Custom Workflows)

```python
from dataflow import DataFlow
from kailash.workflow.builder import WorkflowBuilder

db = DataFlow("sqlite:///app.db", auto_migrate=True)
# Use db-generated nodes in custom workflows
workflow = WorkflowBuilder()
workflow.add_node("UserCreateNode", "user1", {"name": "Alice", "email": "alice@example.com"})
```

## When to Use This Skill

Use DataFlow when you need to:

- Perform database operations in workflows
- Generate CRUD APIs automatically (with Nexus)
- Implement multi-tenant systems
- Work with existing databases
- Build database-first applications
- Handle bulk data operations

## Related Skills

- **[01-core-sdk](../01-core-sdk/SKILL.md)** - Core workflow patterns (canonical node pattern)
- **[03-nexus](../03-nexus/SKILL.md)** - Multi-channel deployment
- **[04-kaizen](../04-kaizen/SKILL.md)** - AI agent integration
- **[17-gold-standards](../17-gold-standards/SKILL.md)** - Best practices

## Support

For DataFlow-specific questions, invoke:

- `dataflow-specialist` - DataFlow implementation and patterns
- `testing-specialist` - DataFlow testing strategies (NO MOCKING policy)
- `framework-advisor` - Choose between Core SDK and DataFlow

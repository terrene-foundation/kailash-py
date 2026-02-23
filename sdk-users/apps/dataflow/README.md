# Kailash DataFlow - Workflow-Native Database Framework

**Version: 0.12.1** | Built on [Kailash Core SDK](https://github.com/terrene-foundation/kailash-py) | `pip install kailash-dataflow`

DataFlow is a **workflow-native database framework** that automatically generates 11 workflow nodes per model using the `@db.model` decorator. DataFlow is not an ORM -- it is designed for enterprise applications where database operations participate in larger workflow pipelines with built-in multi-tenancy, transaction coordination, and caching.

```python
from dataflow import DataFlow
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

db = DataFlow()

@db.model
class User:
    name: str
    email: str
    active: bool = True

# @db.model generates 11 nodes automatically:
# UserCreateNode, UserReadNode, UserUpdateNode, UserDeleteNode,
# UserListNode, UserUpsertNode, UserCountNode,
# UserBulkCreateNode, UserBulkUpdateNode, UserBulkDeleteNode, UserBulkUpsertNode

workflow = WorkflowBuilder()
workflow.add_node("UserCreateNode", "create_user", {
    "name": "Alice",
    "email": "alice@example.com"
})

runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
```

## Installation

```bash
pip install kailash-dataflow
```

```python
from dataflow import DataFlow
```

## Database Support

DataFlow supports three databases with 100% feature parity:

| Database       | Driver                     | Best For                                   |
| -------------- | -------------------------- | ------------------------------------------ |
| **PostgreSQL** | asyncpg                    | Production, PostGIS, complex analytics     |
| **MySQL**      | aiomysql                   | Web hosting, existing MySQL infrastructure |
| **SQLite**     | aiosqlite + custom pooling | Development, testing, mobile, edge         |

```python
# PostgreSQL
db = DataFlow("postgresql://user:password@localhost:5432/mydb")

# MySQL
db = DataFlow("mysql://user:password@localhost:3306/mydb")

# SQLite (file-based)
db = DataFlow("sqlite:///path/to/database.db")

# SQLite (in-memory, for testing)
db = DataFlow(":memory:")

# Zero-config (defaults to SQLite)
db = DataFlow()
```

All databases receive the same 11 generated nodes per model, the same query operators, and the same enterprise features.

## Part of the Kailash Ecosystem

DataFlow is one of three frameworks built on the [Kailash Core SDK](https://github.com/terrene-foundation/kailash-py), each addressing a different layer of application development:

| Framework                                                       | Purpose                              | Install                        |
| --------------------------------------------------------------- | ------------------------------------ | ------------------------------ |
| **DataFlow** (this)                                             | Workflow-native database operations  | `pip install kailash-dataflow` |
| **[Nexus](https://github.com/terrene-foundation/kailash-nexus)**   | Multi-channel platform (API/CLI/MCP) | `pip install kailash-nexus`    |
| **[Kaizen](https://github.com/terrene-foundation/kailash-kaizen)** | AI agent framework with trust        | `pip install kailash-kaizen`   |

All three frameworks share the same workflow execution model: `runtime.execute(workflow.build())`. DataFlow nodes integrate directly into Nexus-deployed workflows and Kaizen agent pipelines.

**CARE/EATP Trust Framework**: The Kailash platform includes a cross-cutting trust layer (Context, Action, Reasoning, Evidence) that propagates trust context through workflow execution. When DataFlow operations run inside a trust-enabled workflow, the `RuntimeTrustContext` tracks human origin, delegation chains, and constraint propagation automatically. Trust verification operates in three modes -- disabled (default, backward compatible), permissive (log violations), and enforcing (block on violations). This is part of the Core SDK's `kailash.runtime.trust` module and requires no DataFlow-specific configuration.

## Generated Node Types (11 per model)

Every `@db.model` class generates these node types:

### CRUD Nodes

```python
# Create a single record (FLAT parameters)
workflow.add_node("UserCreateNode", "create", {
    "name": "Alice",
    "email": "alice@example.com",
    "active": True
})

# Read a single record by ID
workflow.add_node("UserReadNode", "read", {
    "id": 123
})

# Update a record (filter + fields pattern)
workflow.add_node("UserUpdateNode", "update", {
    "filter": {"id": 123},
    "fields": {"name": "Alice Smith"}
})

# Delete a record
workflow.add_node("UserDeleteNode", "delete", {
    "filter": {"id": 123}
})

# List with MongoDB-style filters
workflow.add_node("UserListNode", "list", {
    "filter": {
        "active": True,
        "age": {"$gt": 18},
        "department": {"$in": ["eng", "sales"]}
    },
    "order_by": ["-created_at"],
    "limit": 10
})

# Upsert (insert or update)
workflow.add_node("UserUpsertNode", "upsert", {
    "email": "alice@example.com",
    "name": "Alice Updated",
    "match_fields": ["email"]
})

# Count records matching filter
workflow.add_node("UserCountNode", "count", {
    "filter": {"active": True}
})
```

### Bulk Operations

```python
# Bulk create
workflow.add_node("UserBulkCreateNode", "bulk_create", {
    "data": [
        {"name": "Alice", "email": "alice@example.com"},
        {"name": "Bob", "email": "bob@example.com"}
    ],
    "batch_size": 1000
})

# Bulk update
workflow.add_node("UserBulkUpdateNode", "bulk_update", {
    "filter": {"department": "engineering"},
    "fields": {"active": True}
})

# Bulk delete
workflow.add_node("UserBulkDeleteNode", "bulk_delete", {
    "filter": {"status": "inactive"}
})

# Bulk upsert
workflow.add_node("UserBulkUpsertNode", "bulk_upsert", {
    "data": [
        {"email": "alice@example.com", "name": "Alice Updated"},
        {"email": "new@example.com", "name": "New User"}
    ],
    "match_fields": ["email"]
})
```

## Critical Gotchas

These are the most common sources of confusion. Read them before writing DataFlow code.

### 1. Primary key MUST be named `id`

```python
# WRONG
@db.model
class User:
    user_id: str  # DataFlow will not recognize this as a primary key

# CORRECT
@db.model
class User:
    id: str
    name: str
```

### 2. NEVER manually set `created_at` or `updated_at`

DataFlow auto-manages timestamp fields. As of v0.10.6, manually setting them produces a warning and the values are auto-stripped.

```python
# WRONG (will produce warning)
workflow.add_node("UserCreateNode", "create", {
    "name": "Alice",
    "created_at": datetime.now()  # Auto-stripped with warning
})

# CORRECT
workflow.add_node("UserCreateNode", "create", {
    "name": "Alice"
    # Timestamps managed automatically
})
```

### 3. CreateNode uses FLAT params; UpdateNode uses filter + fields

```python
# CreateNode -- flat parameters
workflow.add_node("UserCreateNode", "create", {
    "name": "Alice",
    "email": "alice@example.com"
})

# UpdateNode -- filter + fields
workflow.add_node("UserUpdateNode", "update", {
    "filter": {"id": 123},
    "fields": {"name": "Alice Smith"}
})
```

### 4. `soft_delete` only affects DELETE operations

Setting `soft_delete: True` in the model config makes DeleteNode set `deleted_at` instead of removing the row. It does NOT auto-filter list/read queries. You must filter manually:

```python
workflow.add_node("UserListNode", "active_users", {
    "filter": {"deleted_at": {"$null": True}}
})
```

### 5. Result key varies by node type

- **ListNode**: `result["records"]`
- **CountNode**: `result["count"]`
- **ReadNode**: Direct record dict

## Dynamic Schema Discovery

Connect to existing databases without `@db.model` decorators:

```python
db = DataFlow(
    database_url="postgresql://user:pass@localhost/existing_db",
    auto_migrate=False  # Do not create or modify tables
)

# Discover and register existing tables
schema = db.discover_schema(use_real_inspection=True)
result = db.register_schema_as_models(tables=["users", "orders"])

# Use generated nodes immediately
workflow = WorkflowBuilder()
user_nodes = result["generated_nodes"]["users"]

workflow.add_node(user_nodes["list"], "get_users", {
    "filter": {"active": True},
    "limit": 10
})

runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
```

## Multi-Tenancy

DataFlow provides auto-wired multi-tenancy through `QueryInterceptor`, which injects tenant filtering at 8 SQL execution points automatically:

```python
@db.model
class Order:
    customer_id: int
    total: float
    status: str = "pending"
    __dataflow__ = {
        "multi_tenant": True,   # Adds tenant_id field
        "soft_delete": True,    # Adds deleted_at field
        "audit_log": True       # Tracks all changes
    }

workflow.add_node("OrderCreateNode", "create", {
    "customer_id": 123,
    "total": 250.00,
    "tenant_id": "tenant_abc"  # Automatic isolation
})
```

## Async Transaction Nodes

Transaction nodes are `AsyncNode` subclasses that use `async_run()`:

```python
from kailash.runtime import AsyncLocalRuntime

runtime = AsyncLocalRuntime()
results, run_id = await runtime.execute_workflow_async(workflow.build(), inputs={})
```

## Enterprise Migration System

DataFlow includes an enterprise-grade migration system with 8 specialized engines:

- **Risk Assessment Engine**: Multi-dimensional risk scoring before schema changes
- **Mitigation Strategy Engine**: Automated risk reduction recommendations
- **Foreign Key Analyzer**: FK-aware operations with referential integrity protection
- **Table Rename Analyzer**: Safe table renaming with dependency tracking
- **Staging Environment Manager**: Production-like testing environments
- **Migration Lock Manager**: Distributed locking for concurrent migration prevention
- **Validation Checkpoint Manager**: Multi-stage validation with rollback
- **Schema State Manager**: Schema evolution tracking with snapshots

## Developer Experience

### ErrorEnhancer (v0.8.0+)

60+ enhanced errors with DF-XXX codes, root cause analysis, and actionable solutions. Integrated automatically -- no setup needed.

### Inspector API

30+ inspection methods for workflow debugging: connection analysis, parameter tracing, execution order, and validation reports.

### Build-Time Validation

10+ validation checks at model registration time. Modes: OFF, WARN (default), STRICT.

### CLI Tools

```bash
dataflow-validate my_workflow.py    # Validate workflow structure
dataflow-analyze my_workflow.py     # Workflow metrics and complexity
dataflow-debug my_workflow.py       # Interactive debugging
dataflow-perf my_workflow.py        # Performance profiling
```

## Production Deployment

### Docker/FastAPI

As of v0.10.15, `auto_migrate=True` works in Docker and FastAPI contexts via `SyncDDLExecutor`:

```python
from kailash.runtime import AsyncLocalRuntime

runtime = AsyncLocalRuntime(execution_timeout=60)
results, run_id = await runtime.execute_workflow_async(workflow.build(), inputs={})
```

### Connection Pooling

```python
db = DataFlow(
    "postgresql://user:password@localhost:5432/mydb",
    pool_size=25,
    max_overflow=50,
    pool_recycle=3600,
    pool_pre_ping=True
)
```

### Centralized Logging (v0.10.12+)

```python
import logging
from dataflow import DataFlow, LoggingConfig

db = DataFlow("postgresql://...", log_config=LoggingConfig.production())
```

### Environment Variables

```bash
DATAFLOW_DATABASE_URL="postgresql://..."
DATAFLOW_LOG_LEVEL="WARNING"
DATAFLOW_POOL_SIZE="25"
DATAFLOW_EXECUTION_TIMEOUT="60"
```

## Migration from Raw SQL / ORM

```python
# Before: Raw SQL
cursor.execute("SELECT * FROM users WHERE age > %s", (18,))

# After: DataFlow
workflow = WorkflowBuilder()
workflow.add_node("UserListNode", "adults", {
    "filter": {"age": {"$gt": 18}}
})
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
```

## Documentation

- [DataFlow CLAUDE.md](CLAUDE.md) -- Complete function access guide (2,900+ lines)
- [User Guide](docs/USER_GUIDE.md)
- [Quick Start Guide](docs/quickstart.md)
- [Query Patterns](docs/query-patterns.md)
- [Multi-Tenant Architecture](docs/multi-tenant.md)
- [Production Deployment](docs/deployment.md)
- [Migration System](docs/migration-system.md)

## Testing

```bash
# Unit tests
python -m pytest tests/unit/ -v

# Integration tests (real database, no mocking)
python -m pytest tests/integration/ -v

# E2E tests
python -m pytest tests/e2e/ -v
```

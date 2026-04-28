---
name: dataflow-express
description: "High-performance direct node invocation for DataFlow operations. Use when asking 'ExpressDataFlow', 'db.express', 'direct node invocation', 'fast CRUD', 'simple database operations', 'skip workflow overhead', or 'high-performance DataFlow'."
---

# ExpressDataFlow - High-Performance Direct Node Invocation

High-performance wrapper providing ~23x faster execution by bypassing workflow overhead for simple database operations.

> **Skill Metadata**
> Category: `dataflow`
> Priority: `HIGH`
> Related Skills: [`dataflow-quickstart`](dataflow-quickstart.md), [`dataflow-crud-operations`](dataflow-crud-operations.md), [`dataflow-bulk-operations`](dataflow-bulk-operations.md)
> Related Subagents: `dataflow-specialist` (enterprise features)

## Quick Reference

- **Async**: `db.express.<operation>()` after `await db.initialize()`
- **Sync**: `db.express_sync.<operation>()` — for CLI scripts, sync handlers, non-async contexts
- **Performance**: ~23x faster than workflow-based operations
- **Operations**: create, read, find_one, update, delete, list, count, upsert, bulk_create, bulk_delete
- **Best For**: Simple CRUD operations, high-throughput scenarios, API endpoints
- **NOT For**: Multi-node workflows, conditional execution, transactions

## Performance Comparison

| Operation         | Workflow Time | Express Time | Speedup |
| ----------------- | ------------- | ------------ | ------- |
| Create            | 2.3ms         | 0.1ms        | **23x** |
| Read              | 2.1ms         | 0.09ms       | **23x** |
| Update            | 2.4ms         | 0.11ms       | **22x** |
| Delete            | 2.2ms         | 0.1ms        | **22x** |
| List              | 2.5ms         | 0.12ms       | **21x** |
| Bulk Create (100) | 25ms          | 1.2ms        | **21x** |

## When to Use ExpressDataFlow

### Use ExpressDataFlow

- Simple CRUD operations without workflow complexity
- High-throughput applications needing maximum performance
- Single-node operations

### Use Traditional Workflows Instead

- Multi-node operations with data flow between nodes
- Conditional execution or branching logic
- Transaction management across operations
- Error recovery and retry logic

## Sync Express API (`db.express_sync`)

For non-async contexts (CLI scripts, sync Nexus handlers, pytest without asyncio):

```python
from dataflow import DataFlow

db = DataFlow("sqlite:///app.db", auto_migrate=True)

# Sync CRUD — same API as async Express, no await needed
result = db.express_sync.create("User", {"name": "Alice", "email": "alice@example.com"})
user = db.express_sync.read("User", str(result["id"]))
users = db.express_sync.list("User", {"active": True})
count = db.express_sync.count("User")
db.express_sync.update("User", str(result["id"]), {"name": "Bob"})
db.express_sync.delete("User", str(result["id"]))
```

**How it works**: `SyncExpress` maintains a persistent event loop in a daemon thread. Coroutines are submitted via `asyncio.run_coroutine_threadsafe()`, preserving database connections across calls.

**When to use**: CLI tools, migration scripts, sync test fixtures, any context where `async/await` is not available.

## SQLite Timestamp Behavior

`create()` on SQLite automatically reads back auto-generated fields (`created_at`, `updated_at`) via a follow-up query. This matches PostgreSQL behavior where `RETURNING` clause provides these fields directly.

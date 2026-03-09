---
name: asyncsql-advanced
description: "Advanced AsyncSQL patterns for complex queries. Use when asking 'async SQL', 'AsyncSQL patterns', 'async queries', 'SQL workflows', or 'async database'."
---

# Asyncsql Advanced

Asyncsql Advanced for database operations and query management.

> **Skill Metadata**
> Category: `database`
> Priority: `HIGH`
> SDK Version: `0.9.25+`

## Quick Reference

- **Primary Use**: Asyncsql Advanced
- **Category**: database
- **Priority**: HIGH
- **Trigger Keywords**: async SQL, AsyncSQL patterns, async queries, SQL workflows

## Core Pattern

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

# Asyncsql Advanced implementation
workflow = WorkflowBuilder()

# See source documentation for specific node types and parameters

runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
```

## Common Use Cases

- **Health Monitoring & Pool Management**: Automatic health checks, dynamic pool resizing, connection monitoring for production databases
- **Advanced Type Handling**: Custom type serializers for UUID, Decimal, numpy arrays, binary data with PostgreSQL-specific support
- **Batch Operations**: High-performance bulk inserts using execute_many_async, COPY, or UNNEST for 10K+ rows
- **Streaming Large Results**: Memory-efficient streaming with async iterators and cursor-based pagination for massive datasets
- **Query Timeout & Cancellation**: Granular timeout control at connection, command, pool, and network levels with cancellable operations

## External Pool Injection (Multi-Worker)

### Why

In multi-worker deployments (Gunicorn + FastAPI, 8 workers), each worker creates its own connection pool. With the default `max_pool_size=30`, that's **240 connections** exhausting the database. External pool injection lets you control pool sizing at the application level and share a single pool across all nodes in a worker.

### Pattern

```python
import asyncpg
from kailash.nodes.data.async_sql import AsyncSQLDatabaseNode

# Create ONE pool at app startup (shared across all nodes)
pool = await asyncpg.create_pool(
    os.environ["DATABASE_URL"],
    min_size=5, max_size=20
)

# Inject into nodes — SDK borrows, does NOT close
node = AsyncSQLDatabaseNode(
    name="query_users",
    database_type="postgresql",
    query="SELECT * FROM users WHERE active = $1",
    params=[True],
    external_pool=pool,
)

result = await node.execute_async()
await node.cleanup()  # Safe — pool stays open

# Caller closes pool at app shutdown
await pool.close()
```

### Ownership Rules

| Rule                                   | Behavior                            |
| -------------------------------------- | ----------------------------------- |
| SDK borrows the pool                   | Caller retains ownership            |
| `cleanup()` marks adapter disconnected | Does NOT close the pool             |
| `to_dict()` raises                     | External pools cannot be serialized |
| Retry fails fast on dead pool          | No reconnect attempts               |
| Pool type must match `database_type`   | Validated at init                   |

### Supported Pool Types

| Database   | Pool Type              |
| ---------- | ---------------------- |
| PostgreSQL | `asyncpg.Pool`         |
| MySQL      | `aiomysql.Pool`        |
| SQLite     | `aiosqlite.Connection` |

### Anti-Patterns

| Anti-Pattern                                 | Consequence                        |
| -------------------------------------------- | ---------------------------------- |
| Creating a new pool per request              | Connection exhaustion              |
| Closing the pool before all nodes are done   | Nodes fail mid-query               |
| Serializing nodes with external pools        | `to_dict()` raises error           |
| Using `external_pool` with `share_pool=True` | SDK forces `share_pool` to `False` |

## Related Patterns

- **For fundamentals**: See `workflow-quickstart` in `06-cheatsheets/`
- **For patterns**: See `workflow-patterns-library` in `06-cheatsheets/`
- **For parameters**: See `param-passing-quick` in `06-cheatsheets/`

## When to Escalate to Subagent

Use specialized subagents when:

- **pattern-expert**: Complex patterns, multi-node workflows
- **sdk-navigator**: Error resolution, parameter issues
- **testing-specialist**: Comprehensive testing strategies

## Quick Tips

- 💡 **Use Connection Pooling**: Enable `share_pool=True` for production to reuse connections (note: forced to `False` when using `external_pool` — the external pool itself handles sharing)
- 💡 **Implement Health Checks**: Enable automatic health monitoring with enable_health_checks=True (uses pool-level command_timeout)
- 💡 **Stream Large Datasets**: Use stream_query() with batch_size instead of loading entire result sets into memory
- 💡 **Set Pool-Level Timeout**: Configure command_timeout at node creation (default: 60s) - applies to ALL queries including health checks
- 💡 **Batch Insert Optimization**: For 10K+ rows, use execute_many_async (general), COPY (PostgreSQL fastest), or UNNEST (PostgreSQL arrays)
- 💡 **pytest-asyncio Compatibility**: AsyncSQLDatabaseNode automatically detects pytest environments and adjusts pool key generation for compatibility with function-scoped fixtures
- 💡 **External Pool for Multi-Worker**: Use `external_pool=pool` to inject a shared pool in Gunicorn/FastAPI deployments — prevents connection exhaustion

## Keywords for Auto-Trigger

<!-- Trigger Keywords: async SQL, AsyncSQL patterns, async queries, SQL workflows -->

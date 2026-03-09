---
name: error-connection-exhaustion
description: "Database connection pool exhaustion troubleshooting. Use when seeing 'too many connections', 'connection pool exhausted', or database OOM in multi-worker deployments."
---

# Error: Connection Pool Exhaustion

Database connection pool exhaustion in multi-worker deployments.

> **Skill Metadata**
> Category: `cross-cutting` (error-resolution)
> Priority: `HIGH` (Production stability issue)
> SDK Version: `0.9.0+` (AsyncSQLDatabaseNode)
> Related Skills: [`asyncsql-advanced`](../../06-cheatsheets/asyncsql-advanced.md), [`production-deployment-guide`](../../07-development-guides/production-deployment-guide.md)
> Related Subagents: `dataflow-specialist`, `nexus-specialist`

## The Problem

**Symptoms**:

- Database rejects connections
- "too many connections" error
- "connection pool exhausted" error
- Database process OOM
- Intermittent connection failures under load

**Common in**: Gunicorn + FastAPI multi-worker deployments.

## Root Cause

Each worker creates its own `AsyncSQLDatabaseNode` connection pool. With 8 workers x 30 max_pool_size = 240 connections, exceeding most database limits (typically 100-200).

```
Worker 1: AsyncSQLDatabaseNode → pool (30 connections)
Worker 2: AsyncSQLDatabaseNode → pool (30 connections)
Worker 3: AsyncSQLDatabaseNode → pool (30 connections)
...
Worker 8: AsyncSQLDatabaseNode → pool (30 connections)
─────────────────────────────────────────────────────
Total: 240 connections (DB limit: 100-200) ← BOOM
```

## Quick Fix

### ❌ WRONG: Each Node Creates Its Own Pool

```python
@app.get("/users")
async def get_users():
    from kailash.nodes.data.async_sql import AsyncSQLDatabaseNode
    # Each request/worker creates its own pool!
    node = AsyncSQLDatabaseNode(
        name="get_users",
        database_type="postgresql",
        query="SELECT * FROM users",
        connection_string=os.environ["DATABASE_URL"],
        max_pool_size=30,  # × 8 workers = 240 connections!
    )
    result = await node.execute_async()
    return result["result"]["data"]
```

### ✅ FIX: External Pool Injection

Instead of letting each node create its own pool, create ONE pool at app startup and inject it:

```python
import asyncpg
from contextlib import asynccontextmanager
from fastapi import FastAPI

@asynccontextmanager
async def lifespan(app: FastAPI):
    # ONE pool for the entire worker
    app.state.pool = await asyncpg.create_pool(
        os.environ["DATABASE_URL"],
        min_size=2, max_size=10,
    )
    yield
    await app.state.pool.close()

app = FastAPI(lifespan=lifespan)

@app.get("/users")
async def get_users():
    from kailash.nodes.data.async_sql import AsyncSQLDatabaseNode
    node = AsyncSQLDatabaseNode(
        name="get_users",
        database_type="postgresql",
        query="SELECT * FROM users",
        external_pool=app.state.pool,
    )
    try:
        result = await node.execute_async()
        return result["result"]["data"]
    finally:
        await node.cleanup()
```

## Why This Works

1. **One pool per worker**: `lifespan` creates a single pool per Gunicorn worker
2. **Controlled connections**: 8 workers x 10 max_size = 80 connections (within DB limits)
3. **Pool reuse**: All nodes in a worker share the same pool
4. **Clean shutdown**: Pool closes gracefully on worker shutdown

## Prevention Checklist

- [ ] Use `external_pool` parameter in multi-worker deployments
- [ ] Set `max_pool_size` based on: DB max connections / number of workers
- [ ] Monitor connection count with `SELECT count(*) FROM pg_stat_activity`
- [ ] Use `pool._closed` check before query execution for health monitoring

## Sizing Guide

| Workers | DB Max Connections | max_size per Worker |
| ------- | ------------------ | ------------------- |
| 2       | 100                | 40                  |
| 4       | 100                | 20                  |
| 8       | 100                | 10                  |
| 8       | 200                | 20                  |
| 16      | 200                | 10                  |

**Formula**: `max_size = DB_max_connections / num_workers - buffer`

Leave a buffer of ~20% for admin connections and migrations.

## Related Patterns

- **Async SQL patterns**: [`asyncsql-advanced`](../../06-cheatsheets/asyncsql-advanced.md) for full external pool patterns
- **Production deployment**: [`production-deployment-guide`](../../07-development-guides/production-deployment-guide.md) for multi-worker deployment
- **Nexus basics**: [`nexus-quickstart`](../../03-nexus/nexus-quickstart.md)

## When to Escalate to Subagent

Use `dataflow-specialist` subagent when:

- Connection exhaustion persists after applying external pool
- Need connection pooling across multiple databases
- Complex multi-tenancy with separate pools per tenant
- Production deployment with PgBouncer or connection proxy setup

## Quick Tips

- 💡 **Critical setting**: Always use `external_pool` in multi-worker deployments
- 💡 **Formula**: max_pool_size = DB max connections / number of workers
- 💡 **Monitor**: `SELECT count(*) FROM pg_stat_activity` to track live connections
- 💡 **Cleanup**: Always call `await node.cleanup()` in a `finally` block

<!-- Trigger Keywords: too many connections, connection pool exhausted, database OOM, connection exhaustion, pool exhaustion, max connections, asyncpg pool, external pool, multi-worker connections, Gunicorn connections, worker pool, database connection limit -->

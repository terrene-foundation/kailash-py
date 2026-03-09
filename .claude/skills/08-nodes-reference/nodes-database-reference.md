---
name: nodes-database-reference
description: "Database nodes reference (AsyncSQL, MySQL, PostgreSQL, Connection Pool). Use when asking 'database node', 'SQL node', 'AsyncSQL', 'connection pool', or 'query routing'."
---

# Database Nodes Reference

Complete reference for database operations and connection management.

> **Skill Metadata**
> Category: `nodes`
> Priority: `HIGH`
> SDK Version: `0.9.25+`
> Related Skills: [`nodes-data-reference`](nodes-data-reference.md), [`nodes-quick-index`](nodes-quick-index.md)
> Related Subagents: `pattern-expert` (database workflows)

## Quick Reference

```python
from kailash.nodes.data import (
    AsyncSQLDatabaseNode,  # ⭐⭐⭐ Production recommended
    WorkflowConnectionPool,  # ⭐⭐ Connection pooling
    QueryRouterNode,  # ⭐⭐⭐ Intelligent routing
    SQLDatabaseNode,  # Simple queries
    OptimisticLockingNode  # ⭐⭐ Concurrency control
)
```

## Production Database Node

### AsyncSQLDatabaseNode ⭐ (Recommended)

```python
from kailash.workflow.builder import WorkflowBuilder

workflow = WorkflowBuilder()

# Production-grade async SQL with transactions
workflow.add_node("AsyncSQLDatabaseNode", "db", {
    "database_type": "postgresql",
    "host": "${DB_HOST}",
    "database": "${DB_NAME}",
    "user": "${DB_USER}",
    "password": "${DB_PASSWORD}",
    "transaction_mode": "auto"  # auto, manual, or none
})

# Execute query
workflow.add_node("AsyncSQLDatabaseNode", "query", {
    "query": "SELECT * FROM users WHERE active = :active",
    "params": {"active": True},
    "fetch_mode": "all"
})
```

### External Pool Injection

```python
import asyncpg
from kailash.nodes.data.async_sql import AsyncSQLDatabaseNode

# For multi-worker deployments (Gunicorn + FastAPI)
# Create ONE pool, share across all AsyncSQLDatabaseNode instances
pool = await asyncpg.create_pool(dsn, min_size=5, max_size=20)

node = AsyncSQLDatabaseNode(
    name="db_query",
    database_type="postgresql",
    query="SELECT * FROM users",
    external_pool=pool,  # SDK borrows, does NOT close
)

result = await node.execute_async()
await node.cleanup()  # Pool stays alive
await pool.close()    # Caller closes at shutdown
```

**Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `external_pool` | `asyncpg.Pool` / `aiomysql.Pool` / `aiosqlite.Connection` | Pre-created pool to inject. Constructor-only, not serializable. |

**Constraints:**

- Pool type must match `database_type` (validated at init)
- `share_pool` is forced to `False` when `external_pool` is set
- `to_dict()` raises `NodeExecutionError` (pools can't be serialized)
- Retry fails fast on dead pool errors (SDK can't reconnect)

## Connection Pooling

### WorkflowConnectionPool ⭐

```python
from kailash.nodes.data import WorkflowConnectionPool

# Create connection pool
pool = WorkflowConnectionPool(
    name="main_pool",
    database_type="postgresql",
    host="localhost",
    database="myapp",
    min_connections=5,
    max_connections=20,
    adaptive_sizing=True,
    enable_query_routing=True
)

# Initialize pool
workflow.add_node("WorkflowConnectionPool", "pool_init", {
    "operation": "initialize"
})
```

## Query Routing

### QueryRouterNode ⭐

```python
from kailash.nodes.data import QueryRouterNode

# Intelligent query routing with caching
workflow.add_node("QueryRouterNode", "router", {
    "name": "query_router",
    "connection_pool": "smart_pool",
    "enable_read_write_split": True,
    "cache_size": 2000,
    "pattern_learning": True
})
```

## Simple SQL Node

### SQLDatabaseNode

```python
workflow.add_node("SQLDatabaseNode", "simple_query", {
    "connection_string": "${DATABASE_URL}",
    "query": "SELECT * FROM users WHERE id = :user_id",
    "parameters": {"user_id": 123},
    "operation": "fetch_one"
})
```

## Concurrency Control

### OptimisticLockingNode ⭐

```python
from kailash.nodes.data import OptimisticLockingNode

# Version-based concurrency control
lock_manager = OptimisticLockingNode(
    version_field="version",
    max_retries=3,
    default_conflict_resolution="retry"
)

workflow.add_node("OptimisticLockingNode", "lock", {
    "action": "update_with_version",
    "table_name": "users",
    "record_id": 123,
    "update_data": {"name": "John Updated"},
    "expected_version": 5
})
```

## Related Skills

- **Data Nodes**: [`nodes-data-reference`](nodes-data-reference.md)
- **Node Index**: [`nodes-quick-index`](nodes-quick-index.md)

## Documentation

<!-- Trigger Keywords: database node, SQL node, AsyncSQL, connection pool, query routing, AsyncSQLDatabaseNode, WorkflowConnectionPool, QueryRouterNode -->

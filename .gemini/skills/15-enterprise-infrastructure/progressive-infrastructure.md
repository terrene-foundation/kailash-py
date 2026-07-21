# Progressive Infrastructure

You are an expert in the Kailash progressive infrastructure model. Guide users through scaling from Level 0 (SQLite, single process) to Level 2 (multi-worker with shared database and task queue) using environment variables alone -- no code changes required.

> For full implementation details, see `docs/enterprise-infrastructure/` and the source at the StoreFactory module.

## Progressive Infrastructure Model

```
Level 0  pip install kailash
         In-process, SQLite, single worker
         Zero configuration required

Level 1  KAILASH_DATABASE_URL=postgresql://...
         Shared state across restarts
         All stores persist to PostgreSQL/MySQL

Level 2  KAILASH_QUEUE_URL=redis://...  (or postgresql://...)
         Multi-worker via Redis/PG-backed queue
         Worker registry with heartbeat monitoring
```

Each level is additive. Level 0 code runs unchanged at Level 2. The user's workflow code (`WorkflowBuilder`, `add_node`, `connect`, `build`, `execute`) is identical at all levels.

## Environment Variable Reference

| Variable               | Purpose                                                                | Priority    | Default         |
| ---------------------- | ---------------------------------------------------------------------- | ----------- | --------------- |
| `KAILASH_DATABASE_URL` | Infrastructure stores (event, checkpoint, DLQ, execution, idempotency) | 1 (highest) | None (Level 0)  |
| `DATABASE_URL`         | Fallback for `KAILASH_DATABASE_URL`                                    | 2           | None            |
| `KAILASH_QUEUE_URL`    | Task queue broker (Redis or SQL)                                       | N/A         | None (no queue) |

Resolution logic lives in `kailash/db/registry.py`:

```python
from kailash.db.registry import resolve_database_url, resolve_queue_url

db_url = resolve_database_url()    # KAILASH_DATABASE_URL -> DATABASE_URL -> None
queue_url = resolve_queue_url()    # KAILASH_QUEUE_URL -> None
```

**Separation principle**: `KAILASH_DATABASE_URL` is for Kailash internal infrastructure stores. `DATABASE_URL` may already be used by DataFlow for user data. `KAILASH_DATABASE_URL` takes priority so users with both DataFlow and infrastructure can point them at different databases.

## StoreFactory Singleton Pattern

The `StoreFactory` is the central entry point for creating infrastructure store backends. It auto-detects the infrastructure level from environment variables.

```python
from kailash.infrastructure.factory import StoreFactory

# Singleton access (recommended)
factory = StoreFactory.get_default()
await factory.initialize()

# Create stores (Level 0 returns SQLite/in-memory defaults)
event_store = await factory.create_event_store()
checkpoint_store = await factory.create_checkpoint_store()
dlq = await factory.create_dlq()
exec_store = await factory.create_execution_store()
idem_store = await factory.create_idempotency_store()  # None at Level 0

# Cleanup
await factory.close()
```

### Level Detection

```python
factory = StoreFactory.get_default()

if factory.is_level0:
    # No KAILASH_DATABASE_URL set -- SQLite/in-memory defaults
    pass
else:
    # Level 1+: database_url is set, ConnectionManager is shared
    print(factory.database_url)
```

### Store Backend Mapping

| Store Method                 | Level 0 Return            | Level 1+ Return       |
| ---------------------------- | ------------------------- | --------------------- |
| `create_event_store()`       | `SqliteEventStoreBackend` | `DBEventStoreBackend` |
| `create_checkpoint_store()`  | `DiskStorage`             | `DBCheckpointStore`   |
| `create_dlq()`               | `PersistentDLQ` (SQLite)  | `DBDeadLetterQueue`   |
| `create_execution_store()`   | `InMemoryExecutionStore`  | `DBExecutionStore`    |
| `create_idempotency_store()` | `None`                    | `DBIdempotencyStore`  |

### Explicit URL Override

```python
# Override auto-detection with an explicit URL
factory = StoreFactory(database_url="postgresql://user:pass@localhost/kailash")
await factory.initialize()
```

### Testing with StoreFactory

```python
import pytest
from kailash.infrastructure.factory import StoreFactory

@pytest.fixture(autouse=True)
async def reset_factory():
    """Reset StoreFactory singleton between tests."""
    yield
    old = StoreFactory._instance
    if old is not None and old._conn is not None:
        await old.close()
    StoreFactory.reset()
```

## Schema Versioning

Infrastructure tables are versioned via a `kailash_meta` table:

```sql
CREATE TABLE IF NOT EXISTS kailash_meta (
    key TEXT PRIMARY KEY,
    value TEXT
);
-- Stores: schema_version = "1"
```

### Version Checking

- On `StoreFactory.initialize()`, the factory stamps the schema version
- If the database version is **newer** than the running code version, initialization fails fast with a clear error
- If the database version is **older**, future migration runners in `kailash/db/migration.py` will handle upgrades

```python
from kailash.db.migration import check_schema_version, stamp_schema_version, SCHEMA_VERSION

version = await check_schema_version(conn)  # int or None
if version is None:
    await stamp_schema_version(conn)  # Creates kailash_meta and stamps SCHEMA_VERSION
```

### Downgrade Protection

```python
# If database has schema_version=2 but code has SCHEMA_VERSION=1:
# RuntimeError: Database schema version 2 is newer than code version 1.
#               Upgrade kailash to a newer version.
```

## Lazy Import Pattern

All Level 0 imports are lazy (inside factory methods) so the factory module has no dependency on `aiosqlite`, `asyncpg`, or any optional driver:

```python
# From StoreFactory.create_event_store()
async def create_event_store(self) -> Any:
    await self.initialize()
    if self._conn is None:
        # Level 0: lazy import of SQLite backend
        from kailash.middleware.gateway.event_store_sqlite import (
            SqliteEventStoreBackend,
        )
        return SqliteEventStoreBackend()

    # Level 1+: lazy import of DB backend
    from kailash.infrastructure.event_store import DBEventStoreBackend
    return DBEventStoreBackend(self._conn)
```

**Rule**: Never import `aiosqlite`, `asyncpg`, or `aiomysql` at module top level. Always import inside the method that uses them. This allows `pip install kailash` (without database extras) to work at Level 0.

## Infrastructure Table Inventory

All tables are created idempotently via `CREATE TABLE IF NOT EXISTS`:

| Table                     | Module                 | Purpose                     |
| ------------------------- | ---------------------- | --------------------------- |
| `kailash_meta`            | `factory.py`           | Schema version tracking     |
| `kailash_events`          | `event_store.py`       | Append-only event log       |
| `kailash_checkpoints`     | `checkpoint_store.py`  | Workflow checkpoint data    |
| `kailash_dlq`             | `dlq.py`               | Dead letter queue entries   |
| `kailash_executions`      | `execution_store.py`   | Workflow execution metadata |
| `kailash_idempotency`     | `idempotency_store.py` | Idempotency keys with TTL   |
| `kailash_task_queue`      | `task_queue.py`        | SQL-backed task queue       |
| `kailash_worker_registry` | `worker_registry.py`   | Worker heartbeat tracking   |

## Level Migration Guide

### Level 0 to Level 1

1. Install Kailash: `pip install kailash` (includes PostgreSQL and MySQL drivers)
2. Set environment variable: `KAILASH_DATABASE_URL=postgresql://user:pass@localhost/kailash`
3. No code changes required. StoreFactory auto-detects and uses DB backends.

### Level 1 to Level 2

1. Choose queue broker:
   - Redis: `pip install redis` + set `KAILASH_QUEUE_URL=redis://localhost:6379/0`
   - SQL queue: set `KAILASH_QUEUE_URL=postgresql://user:pass@localhost/kailash`
2. Use `create_task_queue()` to get the queue backend.
3. Start workers with `SQLWorkerRegistry` for heartbeat monitoring.

## When to Engage

- User asks about "Level 0", "Level 1", "Level 2", "progressive infrastructure"
- User asks about "KAILASH_DATABASE_URL", "DATABASE_URL", "KAILASH_QUEUE_URL"
- User asks about "store factory", "StoreFactory"
- User asks about "schema versioning", "kailash_meta"
- User wants to scale from SQLite to PostgreSQL
- User asks what infrastructure tables Kailash creates

# Store Backends Reference

Kailash SDK uses five store backends for infrastructure state. At Level 0, these use local SQLite or in-memory storage. At Level 1+, they all share a single `ConnectionManager` connected to PostgreSQL, MySQL, or SQLite via `KAILASH_DATABASE_URL`.

## StoreFactory

The `StoreFactory` is the single entry point for creating all store backends. It reads `KAILASH_DATABASE_URL` (falling back to `DATABASE_URL`) and returns the appropriate tier of backend.

```python
from kailash.infrastructure import StoreFactory

# Auto-detect from environment
factory = StoreFactory()

# Or pass an explicit URL
factory = StoreFactory(database_url="postgresql://user:pass@localhost:5432/kailash")

# Create stores
event_store   = await factory.create_event_store()
checkpoint    = await factory.create_checkpoint_store()
dlq           = await factory.create_dlq()
exec_store    = await factory.create_execution_store()
idempotency   = await factory.create_idempotency_store()  # None at Level 0

# Cleanup
await factory.close()
```

### Singleton Access

For applications that need a shared factory instance:

```python
factory = StoreFactory.get_default()   # Returns same instance on repeated calls
# ... use stores ...
StoreFactory.reset()                    # Discard singleton (for testing)
```

### Properties

| Property       | Type            | Description                             |
| -------------- | --------------- | --------------------------------------- |
| `is_level0`    | `bool`          | `True` if no database URL is configured |
| `database_url` | `str` or `None` | The resolved database URL               |

## ConnectionManager

At Level 1+, all stores share a single `ConnectionManager` that handles:

- Async connection pooling (asyncpg for PostgreSQL, aiomysql for MySQL, aiosqlite for SQLite)
- Dialect-aware placeholder translation (`?` canonical → `$1` for PG, `%s` for MySQL)
- Transaction support via `async with conn.transaction() as tx:`

```python
from kailash.db.connection import ConnectionManager

conn = ConnectionManager("postgresql://user:pass@localhost:5432/kailash")
await conn.initialize()

# Queries use canonical ? placeholders -- auto-translated per dialect
await conn.execute("INSERT INTO my_table (id, name) VALUES (?, ?)", "1", "test")
rows = await conn.fetch("SELECT * FROM my_table WHERE id = ?", "1")

# Transactions
async with conn.transaction() as tx:
    await tx.execute("INSERT INTO my_table (id, name) VALUES (?, ?)", "2", "foo")
    row = await tx.fetchone("SELECT * FROM my_table WHERE id = ?", "2")

await conn.close()
```

## Schema Versioning

All infrastructure tables are version-tracked via a `kailash_meta` table:

```sql
CREATE TABLE IF NOT EXISTS kailash_meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
```

| Key              | Value | Purpose                                         |
| ---------------- | ----- | ----------------------------------------------- |
| `schema_version` | `"1"` | Current schema version of infrastructure tables |

On initialization, `StoreFactory` checks the stored schema version against the running code. If the database schema is **newer** than the code, initialization fails with a clear error message (downgrade protection). If the schema is older, future migrations will be applied automatically.

## Store 1: EventStore

Append-only event log with per-stream sequencing. Used by the durable request pipeline for event sourcing.

### Table: `kailash_events`

| Column       | Type    | Constraints | Notes                      |
| ------------ | ------- | ----------- | -------------------------- |
| `id`         | INTEGER | PRIMARY KEY | Auto-increment             |
| `stream_key` | TEXT    | NOT NULL    | Stream identifier          |
| `sequence`   | INTEGER | NOT NULL    | Per-stream sequence number |
| `event_type` | TEXT    | NOT NULL    | Event type tag             |
| `data`       | TEXT    | NOT NULL    | JSON-serialized event dict |
| `timestamp`  | TEXT    | NOT NULL    | ISO-8601 UTC               |

**Unique constraint**: `UNIQUE(stream_key, sequence)`

**Indexes**:

- `idx_kailash_events_stream` on `(stream_key)` -- fast stream lookups
- `idx_kailash_events_timestamp` on `(timestamp)` -- timestamp-based pruning

### Level 0 Default

`SqliteEventStoreBackend` -- file-based SQLite with WAL mode. Ships with the core SDK.

### API

```python
# Append events to a stream
await event_store.append("events:request-123", [
    {"type": "started", "data": {"workflow_id": "wf-1"}},
    {"type": "completed", "data": {"result": "ok"}},
])

# Get all events for a stream
events = await event_store.get("events:request-123")

# Get events after a specific sequence number
new_events = await event_store.get_after("events:request-123", after_sequence=5)

# Delete old events
deleted = await event_store.delete_before("2026-01-01T00:00:00+00:00")

# Count events in a stream
count = await event_store.count("events:request-123")

# List all stream keys
keys = await event_store.stream_keys()
```

## Store 2: CheckpointStore

Binary checkpoint storage for workflow state capture and restore. Supports compressed data detection.

### Table: `kailash_checkpoints`

| Column        | Type       | Constraints        | Notes                       |
| ------------- | ---------- | ------------------ | --------------------------- |
| `key`         | TEXT       | PRIMARY KEY        | Checkpoint identifier       |
| `data`        | BLOB/BYTEA | NOT NULL           | Raw binary data             |
| `size_bytes`  | INTEGER    | NOT NULL           | Data size in bytes          |
| `compressed`  | BOOLEAN    | NOT NULL DEFAULT 0 | Gzip-detected flag          |
| `created_at`  | TEXT       | NOT NULL           | ISO-8601 UTC                |
| `accessed_at` | TEXT       | NOT NULL           | ISO-8601 UTC (LRU tracking) |

**Note**: The `data` column uses `BYTEA` on PostgreSQL and `BLOB` on MySQL/SQLite, auto-selected by the dialect.

### Level 0 Default

`DiskStorage` -- file-based storage in the local filesystem.

### API

```python
# Save a checkpoint
await checkpoint.save("cp:workflow-123:step-5", b'{"state": "running"}')

# Load a checkpoint (updates accessed_at)
data = await checkpoint.load("cp:workflow-123:step-5")

# Delete a checkpoint
await checkpoint.delete("cp:workflow-123:step-5")

# List checkpoints by prefix
keys = await checkpoint.list_keys("cp:workflow-123:")
```

## Store 3: Dead Letter Queue (DLQ)

Failed workflow items with exponential backoff retry. Items that exceed max retries are moved to permanent failure.

### Table: `kailash_dlq`

| Column          | Type    | Constraints                | Notes                                              |
| --------------- | ------- | -------------------------- | -------------------------------------------------- |
| `id`            | TEXT    | PRIMARY KEY                | UUID                                               |
| `workflow_id`   | TEXT    | NOT NULL                   | Failed workflow identifier                         |
| `error`         | TEXT    | NOT NULL                   | Error message or traceback                         |
| `payload`       | TEXT    | NOT NULL                   | JSON-serialized original payload                   |
| `created_at`    | TEXT    | NOT NULL                   | ISO-8601 UTC                                       |
| `retry_count`   | INTEGER | NOT NULL DEFAULT 0         | Attempts so far                                    |
| `max_retries`   | INTEGER | NOT NULL DEFAULT 3         | Maximum retry attempts                             |
| `next_retry_at` | TEXT    |                            | ISO-8601 UTC, null if not retryable                |
| `status`        | TEXT    | NOT NULL DEFAULT 'pending' | pending / retrying / succeeded / permanent_failure |

**Indexes**:

- `idx_kailash_dlq_status` on `(status)` -- filter by state
- `idx_kailash_dlq_next_retry` on `(next_retry_at)` -- find ready items
- `idx_kailash_dlq_created` on `(created_at)` -- age-based queries

### Level 0 Default

`PersistentDLQ` -- SQLite-backed with exponential backoff. Ships with the core SDK.

### Retry Backoff Formula

```
delay = base_delay * 2^retry_count + jitter
jitter = random(0, 0.25 * delay)
```

Default base delay is 60 seconds. Retry intervals: ~60s, ~120s, ~240s, ...

### API

```python
# Enqueue a failed item
item_id = await dlq.enqueue(
    workflow_id="wf-123",
    error="ConnectionTimeout: database unavailable",
    payload={"input": "data"},
    max_retries=3,
)

# Get items ready for retry
ready = await dlq.dequeue_ready()

# Process a retry
await dlq.mark_retrying(item_id)
try:
    # ... retry the workflow ...
    await dlq.mark_success(item_id)
except Exception:
    await dlq.mark_failure(item_id)  # Increments retry_count, schedules next retry

# Get statistics
stats = await dlq.get_stats()
# {"pending": 2, "retrying": 1, "succeeded": 5, "permanent_failure": 0, "total": 8}
```

## Store 4: ExecutionStore

Tracks workflow execution metadata: run ID, status, parameters, results, timing, and worker assignment.

### Table: `kailash_executions`

| Column          | Type | Constraints                | Notes                        |
| --------------- | ---- | -------------------------- | ---------------------------- |
| `run_id`        | TEXT | PRIMARY KEY                | Unique execution identifier  |
| `workflow_id`   | TEXT |                            | Workflow being executed      |
| `status`        | TEXT | NOT NULL DEFAULT 'pending' | pending / completed / failed |
| `parameters`    | TEXT |                            | JSON-serialized parameters   |
| `result`        | TEXT |                            | JSON-serialized results      |
| `error`         | TEXT |                            | Error message on failure     |
| `started_at`    | TEXT |                            | ISO-8601 UTC                 |
| `completed_at`  | TEXT |                            | ISO-8601 UTC                 |
| `worker_id`     | TEXT |                            | Worker that processed this   |
| `metadata_json` | TEXT |                            | JSON-serialized metadata     |

**Indexes**:

- `idx_executions_status` on `(status)` -- filter by state
- `idx_executions_workflow` on `(workflow_id)` -- filter by workflow
- `idx_executions_started` on `(started_at)` -- time-range queries

### Level 0 Default

`InMemoryExecutionStore` -- OrderedDict with LRU eviction at 10,000 entries. Data is lost on process restart.

### API

```python
# Record execution start
await exec_store.record_start(
    run_id="run-abc-123",
    workflow_id="my-workflow",
    parameters={"input": "data"},
    worker_id="worker-1",
)

# Record completion
await exec_store.record_completion(
    run_id="run-abc-123",
    results={"output": "processed"},
)

# Record failure
await exec_store.record_failure(
    run_id="run-abc-123",
    error="ValueError: invalid input format",
)

# Query executions
execution = await exec_store.get_execution("run-abc-123")
recent = await exec_store.list_executions(status="completed", limit=50)
by_workflow = await exec_store.list_executions(workflow_id="my-workflow")
```

## Store 5: IdempotencyStore

Persistent storage for idempotency keys with TTL-based expiry. Enables exactly-once execution semantics at the API and workflow level.

### Table: `kailash_idempotency`

| Column            | Type    | Constraints  | Notes                                      |
| ----------------- | ------- | ------------ | ------------------------------------------ |
| `idempotency_key` | TEXT    | PRIMARY KEY  | Unique request/execution key               |
| `fingerprint`     | TEXT    | NOT NULL     | Request fingerprint for conflict detection |
| `response_data`   | TEXT    | NOT NULL     | JSON-serialized response                   |
| `status_code`     | INTEGER | NOT NULL     | HTTP status code (0 = claim in progress)   |
| `headers`         | TEXT    | DEFAULT '{}' | JSON-serialized response headers           |
| `created_at`      | TEXT    | NOT NULL     | ISO-8601 UTC                               |
| `expires_at`      | TEXT    | NOT NULL     | ISO-8601 UTC (TTL boundary)                |

**Indexes**:

- `idx_idempotency_expires` on `(expires_at)` -- TTL cleanup

### Level 0 Default

`None` -- idempotency is not available at Level 0 (requires persistent database).

### Claim-Store Pattern

The idempotency store uses an atomic claim-then-store pattern:

1. `try_claim(key, fingerprint)` -- atomically insert a placeholder row. Returns `True` if claimed, `False` if key already exists.
2. Execute the request/workflow.
3. `store_result(key, response_data, status_code, headers)` -- update the placeholder with actual results.
4. On failure: `release_claim(key)` -- delete the placeholder so the key can be retried.

### API

```python
# Check for cached result
cached = await idempotency.get("req-123")
if cached is not None:
    return cached["response_data"]

# Claim the key
claimed = await idempotency.try_claim("req-123", fingerprint="sha256:abc")
if not claimed:
    # Another worker is processing this key
    raise ConcurrentRequestError("Key in use")

try:
    result = process_request()
    await idempotency.store_result("req-123", result, status_code=200, headers={})
except Exception:
    await idempotency.release_claim("req-123")
    raise

# Cleanup expired entries
await idempotency.cleanup()
```

## Complete Infrastructure Table Summary

| Table                 | Store             | Level 0 Default | Level 1+ Backend     |
| --------------------- | ----------------- | --------------- | -------------------- |
| `kailash_events`      | EventStore        | SQLite file     | DB (PG/MySQL/SQLite) |
| `kailash_checkpoints` | CheckpointStore   | Disk files      | DB (PG/MySQL/SQLite) |
| `kailash_dlq`         | DLQ               | SQLite file     | DB (PG/MySQL/SQLite) |
| `kailash_executions`  | ExecutionStore    | In-memory dict  | DB (PG/MySQL/SQLite) |
| `kailash_idempotency` | IdempotencyStore  | Not available   | DB (PG/MySQL/SQLite) |
| `kailash_meta`        | Schema versioning | Not applicable  | DB (PG/MySQL/SQLite) |
| `kailash_task_queue`  | SQLTaskQueue      | Not available   | DB (Level 2 only)    |

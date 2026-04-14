# Kailash Infrastructure — Stores, Task Queue, Workers, Factories

Parent domain: Infrastructure (split from `infrastructure.md` per specs-authority Rule 8)
Scope: Store abstractions (checkpoint/event/execution/idempotency/DLQ), idempotent executor, SQL task queue, worker registry, queue factory, store factory

Sibling file: `infra-sql.md` (dialect system, connection management, URL resolution, credential handling, schema migration, execution pipeline, progressive infrastructure model, concurrency invariants, error handling)

Source modules:

- `src/kailash/infrastructure/` -- store backends, task queue, worker registry, store factory

---

## Store Abstractions

All store backends follow the same lifecycle pattern:

1. Receive a `ConnectionManager` in their constructor.
2. `initialize()` creates the backing table(s) and indices with `CREATE TABLE IF NOT EXISTS`. Safe to call multiple times.
3. `close()` releases any resources held by the backend. Does NOT close the ConnectionManager -- it is owned by the caller and may be shared with other stores.

All stores use the `kailash_` table prefix to avoid collisions with application tables.

### CheckpointStore

Module: `kailash.infrastructure.checkpoint_store`
Class: `DBCheckpointStore`
Table: `kailash_checkpoints`

**Purpose:** Persist workflow checkpoint state for pause/resume and crash recovery. Stores binary data (potentially compressed) keyed by a string identifier.

**Schema:**

| Column           | Type       | Constraint              |
| ---------------- | ---------- | ----------------------- |
| `checkpoint_key` | TEXT       | PRIMARY KEY             |
| `data`           | BLOB/BYTEA | NOT NULL                |
| `size_bytes`     | INTEGER    | NOT NULL                |
| `compressed`     | BOOLEAN    | NOT NULL DEFAULT 0      |
| `created_at`     | TEXT       | NOT NULL (ISO-8601 UTC) |
| `accessed_at`    | TEXT       | NOT NULL (ISO-8601 UTC) |

Column types use dialect helpers: `text_column(indexed=True)` for the PK, `blob_type()` for data, `boolean_default(False)` for compressed.

**Methods:**

| Method                         | Behavior                                                                                                                           |
| ------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------- |
| `save(key, data)`              | Upsert binary data. Auto-detects gzip compression via magic bytes `\x1f\x8b`. Uses `dialect.upsert()` for atomic insert-or-update. |
| `load(key) -> Optional[bytes]` | Load binary data by key. Updates `accessed_at` on successful read. Returns `None` if key not found.                                |
| `delete(key)`                  | Delete a checkpoint. No-op if key does not exist.                                                                                  |
| `list_keys(prefix) -> [str]`   | List checkpoint keys matching a prefix. Uses `LIKE` with `!` as escape character. Returns keys in alphabetical order.              |

**LIKE pattern escaping:** The `list_keys` method escapes `!`, `%`, and `_` in the prefix before appending `%` for the LIKE pattern. This prevents unintended wildcard matches when the prefix contains SQL LIKE metacharacters.

### EventStore

Module: `kailash.infrastructure.event_store`
Class: `DBEventStoreBackend` (aliased as `EventStoreBackend`)
Table: `kailash_events`

**Purpose:** Immutable, append-only event audit log. Events are organized into named streams with monotonically increasing sequence numbers within each stream.

**Schema:**

| Column       | Type    | Constraint                                          |
| ------------ | ------- | --------------------------------------------------- |
| `id`         | INTEGER | PRIMARY KEY (auto-increment via `auto_id_column()`) |
| `stream_key` | TEXT    | NOT NULL, indexed                                   |
| `sequence`   | INTEGER | NOT NULL                                            |
| `event_type` | TEXT    | NOT NULL                                            |
| `data`       | TEXT    | NOT NULL (JSON-serialized event dict)               |
| `timestamp`  | TEXT    | NOT NULL (ISO-8601 UTC), indexed                    |
| UNIQUE       |         | `(stream_key, sequence)`                            |

**Indices:** `idx_kailash_events_stream` on `stream_key`, `idx_kailash_events_timestamp` on `timestamp`.

**Methods:**

| Method                                | Behavior                                                                                                                                                                                                                                             |
| ------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `append(key, events)`                 | Append a list of event dicts to a stream. Determines the next sequence number atomically within a transaction. Each event is stored as a separate row with `json.dumps(event)`. Extracts `event.get("type", "unknown")` for the `event_type` column. |
| `get(key) -> [dict]`                  | Retrieve all events for a stream, ordered by sequence. Deserializes JSON.                                                                                                                                                                            |
| `get_after(key, after_seq) -> [dict]` | Retrieve events with sequence > `after_seq`. For incremental consumption.                                                                                                                                                                            |
| `delete_before(timestamp) -> int`     | Delete events older than the given ISO-8601 timestamp. Returns count of deleted events. Runs within a transaction.                                                                                                                                   |
| `count(key) -> int`                   | Count events in a stream.                                                                                                                                                                                                                            |
| `stream_keys() -> [str]`              | Return all distinct stream keys, sorted alphabetically.                                                                                                                                                                                              |

**Concurrency invariant:** The `append` method uses a transaction to atomically read `MAX(sequence)` and insert new rows. This prevents duplicate sequence numbers under concurrent appends to the same stream.

### ExecutionStore

Module: `kailash.infrastructure.execution_store`
Classes: `DBExecutionStore`, `InMemoryExecutionStore`
Table: `kailash_executions`

**Purpose:** Track workflow execution metadata -- run ID, status, parameters, results, timing, and worker assignment. Provides the execution history visible through the SDK's monitoring APIs.

**Schema:**

| Column          | Type | Constraint                            |
| --------------- | ---- | ------------------------------------- |
| `run_id`        | TEXT | PRIMARY KEY                           |
| `workflow_id`   | TEXT | indexed                               |
| `status`        | TEXT | NOT NULL DEFAULT `'pending'`, indexed |
| `parameters`    | TEXT | nullable (JSON)                       |
| `result`        | TEXT | nullable (JSON)                       |
| `error`         | TEXT | nullable                              |
| `started_at`    | TEXT | indexed                               |
| `completed_at`  | TEXT | nullable                              |
| `worker_id`     | TEXT | nullable                              |
| `metadata_json` | TEXT | nullable (JSON)                       |

**Indices:** `idx_executions_status`, `idx_executions_workflow`, `idx_executions_started`.

**Status transitions:** `pending` -> `completed` or `failed`. No intermediate states.

**Methods:**

| Method                                                 | Behavior                                                                                           |
| ------------------------------------------------------ | -------------------------------------------------------------------------------------------------- |
| `record_start(run_id, workflow_id, params, worker_id)` | Insert a new execution record with status `pending`. Parameters are JSON-serialized.               |
| `record_completion(run_id, results)`                   | Update status to `completed`, store JSON-serialized results, set `completed_at`.                   |
| `record_failure(run_id, error)`                        | Update status to `failed`, store error string (truncated to 200 chars in log), set `completed_at`. |
| `get_execution(run_id) -> Optional[dict]`              | Retrieve a single execution record by `run_id`.                                                    |
| `list_executions(status, workflow_id, limit)`          | List executions with optional filters. Ordered by `started_at DESC`. Default limit: 100.           |

**InMemoryExecutionStore:**

Provides the same async interface backed by an `OrderedDict`. Used for Level 0 (no database) deployments and testing.

- Maximum entries: 10,000 (configurable via `max_entries` constructor parameter).
- LRU eviction: when at capacity, the oldest entry is evicted via `popitem(last=False)`.
- No persistence -- all data is lost when the process exits.
- `initialize()` and `close()` are no-ops.

### IdempotencyStore

Module: `kailash.infrastructure.idempotency_store`
Class: `DBIdempotencyStore`
Table: `kailash_idempotency`

**Purpose:** Deduplication of requests using idempotency keys with TTL-based expiry. Implements a claim-then-store pattern for safe concurrent request handling.

**Schema:**

| Column            | Type          | Constraint                       |
| ----------------- | ------------- | -------------------------------- |
| `idempotency_key` | TEXT          | PRIMARY KEY                      |
| `fingerprint`     | TEXT          | NOT NULL                         |
| `response_data`   | TEXT          | NOT NULL (JSON)                  |
| `status_code`     | INTEGER       | NOT NULL                         |
| `headers`         | VARCHAR(4096) | NOT NULL DEFAULT `'{}'` (JSON)   |
| `created_at`      | TEXT          | NOT NULL (ISO-8601 UTC)          |
| `expires_at`      | TEXT          | NOT NULL (ISO-8601 UTC), indexed |

**Index:** `idx_idempotency_expires` on `expires_at`.

**Claim-then-store protocol:**

1. `try_claim(key, fingerprint) -> bool` -- Atomically insert a placeholder row with `status_code=0` and empty response. Returns `True` if the key was successfully claimed (first writer wins). Claims get a 5-minute TTL to allow processing time. Uses `INSERT IGNORE` within a transaction, then verifies the fingerprint matches.
2. Process the request.
3. `store_result(key, response_data, status_code, headers)` -- Update the claimed entry with actual response data.
4. On failure: `release_claim(key)` -- Delete the placeholder, allowing retry.

**Methods:**

| Method                                                                    | Behavior                                                                 |
| ------------------------------------------------------------------------- | ------------------------------------------------------------------------ |
| `get(key) -> Optional[dict]`                                              | Retrieve by key, respecting TTL. Returns `None` if expired or not found. |
| `set(key, fingerprint, response_data, status_code, headers, ttl_seconds)` | Store with TTL. Uses `INSERT IGNORE` -- first writer wins.               |
| `try_claim(key, fingerprint) -> bool`                                     | Atomic claim. See protocol above.                                        |
| `store_result(key, response_data, status_code, headers)`                  | Update a claimed entry with actual data.                                 |
| `release_claim(key)`                                                      | Delete a claimed key, allowing retry.                                    |
| `cleanup(before=None)`                                                    | Delete expired entries. Defaults to current UTC time.                    |

### IdempotentExecutor

Module: `kailash.infrastructure.idempotency`
Class: `IdempotentExecutor`

**Purpose:** Wraps workflow execution with exactly-once semantics using the `DBIdempotencyStore`.

**Constructor:** `IdempotentExecutor(idempotency_store, ttl_seconds=3600)`

**Method:** `execute(runtime, workflow, parameters=None, idempotency_key=None) -> (results, run_id)`

**Behavior:**

1. If `idempotency_key` is `None`, executes without dedup (pass-through to `runtime.execute`).
2. Check for cached result via `store.get(key)`. If found, return cached `(results, run_id)`.
3. Claim the key via `store.try_claim(key, fingerprint)`.
4. If claim fails (another worker claimed), check again for cached result. If still not available, raise `RuntimeError`.
5. Execute the workflow via `runtime.execute(workflow, parameters=parameters or {})`.
6. On success: store result via `store.store_result(key, {results, run_id}, 200, {})`.
7. On failure: release claim via `store.release_claim(key)`, then re-raise.

### Dead Letter Queue (DLQ)

Module: `kailash.infrastructure.dlq`
Class: `DBDeadLetterQueue`
Table: `kailash_dlq`

**Purpose:** Capture failed workflow executions for retry or manual inspection. Implements exponential backoff with jitter for automatic retries.

**Schema:**

| Column          | Type    | Constraint                            |
| --------------- | ------- | ------------------------------------- |
| `id`            | TEXT    | PRIMARY KEY (UUID)                    |
| `workflow_id`   | TEXT    | NOT NULL                              |
| `error`         | TEXT    | NOT NULL                              |
| `payload`       | TEXT    | NOT NULL (JSON or string)             |
| `created_at`    | TEXT    | NOT NULL (ISO-8601 UTC), indexed      |
| `retry_count`   | INTEGER | NOT NULL DEFAULT 0                    |
| `max_retries`   | INTEGER | NOT NULL DEFAULT 3                    |
| `next_retry_at` | TEXT    | nullable (ISO-8601 UTC), indexed      |
| `status`        | TEXT    | NOT NULL DEFAULT `'pending'`, indexed |

**Valid statuses:** `pending`, `retrying`, `succeeded`, `permanent_failure`

**Indices:** `idx_kailash_dlq_status`, `idx_kailash_dlq_next_retry`, `idx_kailash_dlq_created`.

**Constructor:** `DBDeadLetterQueue(conn_manager, base_delay=60.0)`

**Backoff formula:** `delay = base_delay * 2^retry_count`, with additive random jitter up to `JITTER_FACTOR (0.25) * delay`. Example with default base_delay=60s: retry 1 = ~60-75s, retry 2 = ~120-150s, retry 3 = ~240-300s.

**Methods:**

| Method                                                       | Behavior                                                                                                                                                                    |
| ------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `enqueue(workflow_id, error, payload, max_retries=3) -> str` | Add a failed item. Returns the UUID. `next_retry_at` is set to now (immediately eligible). Payload is JSON-serialized unless already a string.                              |
| `dequeue_ready() -> [dict]`                                  | Return items with `status='pending'` and `next_retry_at <= now`, ordered oldest first.                                                                                      |
| `mark_retrying(item_id)`                                     | Transition to `retrying`.                                                                                                                                                   |
| `mark_success(item_id)`                                      | Transition to `succeeded`.                                                                                                                                                  |
| `mark_failure(item_id)`                                      | Increment `retry_count`. If `retry_count >= max_retries`, transition to `permanent_failure`. Otherwise, back to `pending` with new `next_retry_at` via exponential backoff. |
| `get_stats() -> dict`                                        | Return counts by status: `pending`, `retrying`, `succeeded`, `permanent_failure`, `total`.                                                                                  |
| `clear()`                                                    | Delete all items.                                                                                                                                                           |

---

## Task Queue System

Module: `kailash.infrastructure.task_queue`

### SQLTaskMessage

Dataclass representing a task in the queue.

| Field                | Type             | Default      |
| -------------------- | ---------------- | ------------ |
| `task_id`            | `str`            | `""`         |
| `queue_name`         | `str`            | `"default"`  |
| `payload`            | `Dict[str, Any]` | `{}`         |
| `status`             | `str`            | `"pending"`  |
| `created_at`         | `float`          | `0.0` (Unix) |
| `updated_at`         | `float`          | `0.0` (Unix) |
| `attempts`           | `int`            | `0`          |
| `max_attempts`       | `int`            | `3`          |
| `visibility_timeout` | `int`            | `300` (secs) |
| `worker_id`          | `str`            | `""`         |
| `error`              | `str`            | `""`         |

Provides `to_dict()` and `from_dict(data)` for serialization. `from_dict` auto-deserializes JSON strings in the `payload` field.

### SQLTaskQueue

Class: `SQLTaskQueue`
Table: `kailash_task_queue` (configurable)

**Purpose:** Database-backed task queue. SQL alternative to Redis-backed `kailash.runtime.distributed.TaskQueue`. Suitable for Level 2 deployments where a SQL database is already available and Redis is not desired.

**Constructor:** `SQLTaskQueue(conn, table_name="kailash_task_queue", default_visibility_timeout=300)`

- Validates `table_name` via `_validate_identifier` at construction time.
- Does NOT initialize the table -- call `initialize()` separately.

**Table schema:**

| Column               | Type    | Constraint                   |
| -------------------- | ------- | ---------------------------- |
| `task_id`            | TEXT    | PRIMARY KEY                  |
| `queue_name`         | TEXT    | NOT NULL DEFAULT `'default'` |
| `payload`            | TEXT    | NOT NULL (JSON)              |
| `status`             | TEXT    | NOT NULL DEFAULT `'pending'` |
| `created_at`         | REAL    | NOT NULL (Unix timestamp)    |
| `updated_at`         | REAL    | NOT NULL (Unix timestamp)    |
| `attempts`           | INTEGER | NOT NULL DEFAULT 0           |
| `max_attempts`       | INTEGER | NOT NULL DEFAULT 3           |
| `visibility_timeout` | INTEGER | NOT NULL DEFAULT 300         |
| `worker_id`          | TEXT    | NOT NULL DEFAULT `''`        |
| `error`              | TEXT    | NOT NULL DEFAULT `''`        |

**Indices:** `idx_<table>_dequeue` on `(status, created_at)`, `idx_<table>_stale` on `(status, updated_at)`.

**Valid statuses:** `pending`, `processing`, `completed`, `failed`, `dead_lettered`

**Concurrency model:**

- PostgreSQL/MySQL: Uses `FOR UPDATE SKIP LOCKED` to dequeue without contention. Multiple workers can dequeue concurrently -- each skips rows locked by others.
- SQLite: Uses `BEGIN IMMEDIATE` for single-writer safety. Only one transaction can write at a time.

**Methods:**

| Method                                                                                                 | Behavior                                                                                                                                                                           |
| ------------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `initialize()`                                                                                         | Create table and indices. Idempotent.                                                                                                                                              |
| `enqueue(payload, queue_name="default", task_id=None, max_attempts=3, visibility_timeout=None) -> str` | Add a task. Returns the task ID (auto-generated UUID if not provided).                                                                                                             |
| `dequeue(queue_name="default", worker_id="") -> Optional[SQLTaskMessage]`                              | Atomically claim the oldest pending task. Updates status to `processing`, increments `attempts`, records `worker_id`. Returns `None` if queue is empty. Runs within a transaction. |
| `complete(task_id)`                                                                                    | Mark as `completed`.                                                                                                                                                               |
| `fail(task_id, error="")`                                                                              | If `attempts >= max_attempts`, transition to `dead_lettered`. Otherwise, back to `pending` for retry. Clears `worker_id`.                                                          |
| `requeue_stale(queue_name="default") -> int`                                                           | Find tasks stuck in `processing` past their `visibility_timeout` and move them back to `pending` (or `dead_lettered` if max attempts exceeded). Returns count.                     |
| `get_stats(queue_name="default") -> dict`                                                              | Return counts by status.                                                                                                                                                           |
| `purge_completed(queue_name="default", older_than=None) -> int`                                        | Delete completed tasks, optionally filtering by timestamp. Returns count deleted.                                                                                                  |

**Visibility timeout:** When a worker dequeues a task and starts processing, the task enters `processing` status. If the worker crashes without completing or failing the task, `requeue_stale()` (called periodically by supervisors or health monitors) detects tasks that have been in `processing` longer than their `visibility_timeout` and moves them back to `pending`.

---

## Worker Registry

Module: `kailash.infrastructure.worker_registry`
Class: `SQLWorkerRegistry`
Table: `kailash_worker_registry` (configurable)

**Purpose:** Database-backed registry for tracking worker processes that consume tasks from the SQLTaskQueue. Provides heartbeat tracking and dead worker reaping.

**Constructor:** `SQLWorkerRegistry(conn, task_queue, table_name="kailash_worker_registry")`

- `conn`: An initialized ConnectionManager.
- `task_queue`: The SQLTaskQueue instance. Used to requeue tasks when dead workers are reaped (accesses `task_queue._table` directly).
- Validates `table_name` via `_validate_identifier`.

**Table schema:**

| Column          | Type | Constraint                  |
| --------------- | ---- | --------------------------- |
| `worker_id`     | TEXT | PRIMARY KEY                 |
| `queue_name`    | TEXT | NOT NULL                    |
| `status`        | TEXT | NOT NULL DEFAULT `'active'` |
| `last_beat_at`  | REAL | NOT NULL (Unix timestamp)   |
| `started_at`    | REAL | NOT NULL (Unix timestamp)   |
| `current_task`  | TEXT | nullable                    |
| `metadata_json` | TEXT | DEFAULT `'{}'`              |

**Index:** `idx_<table>_status_beat` on `(status, last_beat_at)`.

**Worker lifecycle methods:**

| Method                                 | Behavior                               |
| -------------------------------------- | -------------------------------------- |
| `register(worker_id, queue_name)`      | Insert a new worker as `active`.       |
| `heartbeat(worker_id)`                 | Update `last_beat_at` to current time. |
| `set_current_task(worker_id, task_id)` | Record the task being processed.       |
| `clear_current_task(worker_id)`        | Set `current_task` to NULL.            |
| `deregister(worker_id)`                | Mark as `inactive`.                    |

**Reaping:**

`reap_dead_workers(staleness_seconds, queue_name) -> int`

1. Find all workers with `status='active'` and `last_beat_at < (now - staleness_seconds)` in the target queue.
2. For each stale worker, within a transaction:
   a. Requeue any tasks held by this worker (`status='processing'` with matching `worker_id`) back to `pending`.
   b. Mark the worker as `inactive` and clear its `current_task`.
3. Returns count of reaped workers.

**Query:**

`get_active_workers(queue_name) -> [dict]` -- Return all active workers for a queue, ordered by `started_at`.

---

## Queue Factory

Module: `kailash.infrastructure.queue_factory`

`create_task_queue(queue_url=None) -> Optional[TaskQueue | SQLTaskQueue]`

Auto-detects the queue backend from `KAILASH_QUEUE_URL` or an explicit URL.

**Detection rules:**

| URL scheme                     | Backend                                            | Driver      |
| ------------------------------ | -------------------------------------------------- | ----------- |
| No URL configured              | Returns `None` (Level 0/1)                         | --          |
| `redis://`, `rediss://`        | `kailash.runtime.distributed.TaskQueue`            | `redis`     |
| `postgresql://`, `postgres://` | `SQLTaskQueue` (creates its own ConnectionManager) | `asyncpg`   |
| `mysql://`                     | `SQLTaskQueue` (creates its own ConnectionManager) | `aiomysql`  |
| `sqlite:///`                   | `SQLTaskQueue` (creates its own ConnectionManager) | `aiosqlite` |
| Plain file path                | `SQLTaskQueue` (SQLite)                            | `aiosqlite` |
| Other                          | Raises `ValueError`                                | --          |

All driver imports are lazy inside the factory function.

Note: The queue factory creates its own `ConnectionManager` for SQL-backed queues. This is separate from the `StoreFactory`'s ConnectionManager. If both the queue and the stores use the same database, they will have separate connection pools.

---

## Store Factory

Module: `kailash.infrastructure.factory`
Class: `StoreFactory`

**Purpose:** Single entry point for creating all infrastructure store backends. Auto-detects from `KAILASH_DATABASE_URL` and returns the appropriate backend tier.

**Schema version:** `SCHEMA_VERSION = 1`. Stored in `kailash_meta` table.

**Constructor:** `StoreFactory(database_url=None)`

- If `database_url` is None, auto-detects via `resolve_database_url()`.
- Does NOT create a connection or any stores -- that happens in `initialize()`.

**Singleton pattern:**

- `StoreFactory.get_default()` -- Get or create the default singleton instance.
- `StoreFactory.reset()` -- Discard the singleton (for testing). Caller must `close()` the old instance first.

**Properties:**

- `is_level0: bool` -- True if no database URL is configured.
- `database_url: Optional[str]` -- The resolved URL, or None.

**Lifecycle:**

`initialize()` (idempotent):

1. For Level 0 (no URL): no-op.
2. For Level 1+: Creates a `ConnectionManager`, calls `initialize()` on it, then creates and initializes all five store backends (EventStore, CheckpointStore, DLQ, ExecutionStore, IdempotencyStore), then stamps the schema version in `kailash_meta`.

`close()` -- Closes the ConnectionManager, sets `_initialized = False`. Safe to call multiple times.

**Schema version management:**

The `_stamp_schema_version()` method:

1. Creates `kailash_meta` table if not exists (columns: `key TEXT PRIMARY KEY`, `value TEXT`).
2. Reads existing schema version.
3. If existing version > code version: raises `RuntimeError` (downgrade protection).
4. If no version exists: inserts `SCHEMA_VERSION`.
5. If existing < current: future migration path (currently just stamps).

**Store creation methods:**

Each method calls `initialize()` if not already done. Returns the appropriate backend for the configured level.

| Method                       | Level 0 Backend                        | Level 1+ Backend      |
| ---------------------------- | -------------------------------------- | --------------------- |
| `create_event_store()`       | `SqliteEventStoreBackend` (file-based) | `DBEventStoreBackend` |
| `create_checkpoint_store()`  | `DiskStorage` (file-based)             | `DBCheckpointStore`   |
| `create_dlq()`               | `PersistentDLQ` (SQLite file-based)    | `DBDeadLetterQueue`   |
| `create_execution_store()`   | `InMemoryExecutionStore`               | `DBExecutionStore`    |
| `create_idempotency_store()` | `None` (no persistent idempotency)     | `DBIdempotencyStore`  |

Level 0 imports are lazy (inside factory methods) so the factory module has no dependency on `aiosqlite` or any optional driver at import time.

**Credential safety in logging:** When logging the connection URL after initialization, the factory strips everything before the last `@` to avoid leaking credentials.

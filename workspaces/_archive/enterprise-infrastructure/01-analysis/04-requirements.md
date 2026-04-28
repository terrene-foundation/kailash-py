# Enterprise Infrastructure: Requirements Analysis & Architecture Decisions

**Date**: 2026-03-17
**Author**: requirements-analyst
**Scope**: Multi-database store backends, distributed task queue, idempotency
**Release target**: v1.0.0 (release branch)
**Context**: SDK dependency-slimmed to 4 mandatory deps; all DB drivers are optional extras
**Revision**: v2 -- incorporates supplementary brief `02-multi-database-strategy.md` (SQLAlchemy Core replaces raw psycopg3/asyncpg for infrastructure stores)

---

## 0. Architecture Change Summary

The original brief (`01-project-brief.md`) proposed PostgreSQL-specific backends using psycopg3 (sync) and asyncpg (async). The supplementary brief (`02-multi-database-strategy.md`) overrides this:

**Before:** 3 SQLite backends + 3 PostgreSQL backends = 6 implementations, PG-only for Level 1.

**After:** 3 existing SQLite backends (kept for Level 0 zero-dep) + 3 SQLAlchemy Core backends (new, covering PostgreSQL + MySQL 8.0+ + SQLite via async engine) = 6 total, but each new backend covers 3 databases.

Key impacts:

- **ADR-001 (driver choice):** Superseded. SQLAlchemy's async engine handles dialect selection via URL scheme (`postgresql+asyncpg://`, `mysql+aiomysql://`, `sqlite+aiosqlite://`).
- **ADR-002 (env var naming):** Simplified. `DATABASE_URL` passes directly to `create_async_engine()`. But `KAILASH_STORE_URL` override is still needed for DataFlow collision avoidance.
- **ADR-003 (migrations):** Changes from trust-plane custom pattern to Alembic (SQLAlchemy's native migration tool).
- **All store names:** Rename from `Postgres*` to `SqlAlchemy*`.

The existing `[database]` extra already includes `sqlalchemy>=2.0.0` and `aiosqlite>=0.19.0`. The existing `[postgres]` extra includes `asyncpg>=0.30.0`. The existing `[mysql]` extra includes `aiomysql>=0.2.0`. **No new dependencies are introduced.**

---

## 1. Requirements Matrix

### 1.1 Gap 1: Multi-Database Store Backends for Core Runtime Stores

#### REQ-DB-001: SqlAlchemyEventStoreBackend

| Dimension            | Requirement                                                                                                                                                                                                                                                                                                                                          |
| -------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Functional**       | Implement `EventStoreBackend` protocol (append, get, get_after, delete_before, count, stream_keys, close). Append events atomically per-stream. Maintain per-stream sequence ordering. Support GC via delete_before(). Works on PostgreSQL, MySQL 8.0+, and SQLite.                                                                                  |
| **Non-Functional**   | Append latency <10ms for batch of 100 events (PG/MySQL). Read latency <5ms for single stream (up to 10K events). Must not lose events on process crash (database transaction guarantees). Connection pooling via SQLAlchemy's built-in pool (configurable pool_size, default 5+10 overflow).                                                         |
| **Interface**        | Must implement `EventStoreBackend` protocol from `event_store_backend.py`. Constructor: `SqlAlchemyEventStoreBackend(engine: AsyncEngine)` or `SqlAlchemyEventStoreBackend.from_url(url: str, **engine_kwargs)`. All methods are `async def`. Uses SQLAlchemy Core (Table/Column/select/insert), NOT ORM.                                            |
| **Schema**           | Uses SQLAlchemy `Table` metadata: `kailash_events` table with `event_id` (String PK), `stream_key` (String, indexed), `sequence` (Integer), `event_type` (String), `data` (JSON -- JSONB on PG, JSON on MySQL, TEXT-backed on SQLite), `timestamp` (DateTime with timezone). Composite unique on (stream_key, sequence).                             |
| **Dialect handling** | JSON column type: SQLAlchemy `JSON` auto-compiles to JSONB on PG, JSON on MySQL, stores as TEXT on SQLite. Batch insert: uses `insert().values([...])` which compiles to multi-row VALUES on PG/MySQL and individual inserts on SQLite.                                                                                                              |
| **Testing**          | T1 (unit): Protocol compliance, serialization round-trip. Schema creation with in-memory SQLite engine. T2 (integration): Real PostgreSQL AND real MySQL -- append 1000 events, get by stream, get_after, delete_before, count, stream_keys, concurrent append. T3 (e2e): Full EventStore with SqlAlchemyEventStoreBackend on each database dialect. |

#### REQ-DB-002: SqlAlchemyCheckpointStorage

| Dimension            | Requirement                                                                                                                                                                                                                                                    |
| -------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Functional**       | Implement `StorageBackend` protocol (save, load, delete, list_keys). Store checkpoint data as LargeBinary (BYTEA on PG, LONGBLOB on MySQL, BLOB on SQLite). Support prefix-based key listing. Support GC via retention-based deletion.                         |
| **Non-Functional**   | Save latency <20ms for 1MB checkpoint (PG/MySQL). Load latency <15ms for 1MB checkpoint. Checkpoints up to 50MB.                                                                                                                                               |
| **Interface**        | Must implement `StorageBackend` protocol from `checkpoint_manager.py`. Constructor: `SqlAlchemyCheckpointStorage(engine: AsyncEngine)`. Compatible with `CheckpointManager(disk_storage=SqlAlchemyCheckpointStorage(...))`.                                    |
| **Schema**           | `kailash_checkpoints` table: `key` (String PK), `data` (LargeBinary), `size_bytes` (Integer), `compressed` (Boolean), `created_at` (DateTime), `accessed_at` (DateTime). Index on `created_at` for GC.                                                         |
| **Dialect handling** | LargeBinary: auto-compiles to BYTEA (PG), LONGBLOB (MySQL), BLOB (SQLite). LIKE for prefix queries works across all dialects.                                                                                                                                  |
| **Testing**          | T1: Protocol compliance, round-trip for compressed and uncompressed data, in-memory SQLite. T2: Real PG and MySQL -- save/load 1MB checkpoint, list_keys with prefix, delete, GC. T3: Full CheckpointManager with SqlAlchemyCheckpointStorage as disk_storage. |

#### REQ-DB-003: SqlAlchemyDLQ

| Dimension            | Requirement                                                                                                                                                                                                                                                                                                   |
| -------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Functional**       | Same API as PersistentDLQ: enqueue, dequeue_ready, mark_retrying, mark_success, mark_failure, get_stats, get_all, clear. Exponential backoff with jitter. Bounded capacity (10,000 items with oldest-10% eviction).                                                                                           |
| **Non-Functional**   | Enqueue latency <5ms. Dequeue_ready scan <10ms for 1000 pending items. Must survive process crash. Concurrent enqueue from multiple workers.                                                                                                                                                                  |
| **Interface**        | Same public API as `PersistentDLQ`. Constructor: `SqlAlchemyDLQ(engine: AsyncEngine, base_delay: float = 60.0)`. DLQItem dataclass unchanged.                                                                                                                                                                 |
| **Schema**           | `kailash_dlq` table: `id` (String PK), `workflow_id` (String), `error` (Text), `payload` (Text), `created_at` (DateTime), `retry_count` (Integer), `max_retries` (Integer), `next_retry_at` (DateTime nullable), `status` (String with CHECK constraint). Indexes on `status`, `next_retry_at`, `created_at`. |
| **Dialect handling** | CHECK constraints: compile identically on PG/MySQL/SQLite. DateTime: timezone-aware on PG, fractional seconds on MySQL 8.0+, ISO string on SQLite. Upsert not needed (insert-only with status updates).                                                                                                       |
| **Testing**          | T1: All status transitions, capacity enforcement, backoff calculation, in-memory SQLite. T2: Real PG and MySQL -- enqueue/dequeue cycle, mark transitions, stats accuracy, capacity eviction. T3: Full retry cycle with real timing.                                                                          |

#### REQ-DB-004: Complete DatabaseStateStorage

| Dimension          | Requirement                                                                                                                                                                                                                                                                  |
| ------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Functional**     | Implement `_ensure_table_exists()` to create saga_states table with proper schema. This is the EXISTING asyncpg-based store -- **NOT converted to SQLAlchemy** because it uses asyncpg's `db_pool.acquire()` pattern directly and is already functional except for the stub. |
| **Non-Functional** | Table creation idempotent (IF NOT EXISTS). Must not fail if table already exists.                                                                                                                                                                                            |
| **Interface**      | No API change. `DatabaseStateStorage(db_pool, table_name)` -- existing constructor. Only change: `_ensure_table_exists()` creates the table.                                                                                                                                 |
| **Schema**         | `CREATE TABLE IF NOT EXISTS {table_name} (saga_id TEXT PRIMARY KEY, saga_name TEXT, state TEXT, state_data JSONB NOT NULL, updated_at TIMESTAMPTZ DEFAULT NOW())`. Index on `state`.                                                                                         |
| **Testing**        | T2: Real PG with asyncpg pool -- create table, save/load/delete/list. T3: Full saga execution with persistence across restart.                                                                                                                                               |

**Note:** This store stays on asyncpg because it is already implemented with asyncpg's pool protocol and changing it to SQLAlchemy would break the existing `StorageFactory`. Converting it is a v1.1.0 candidate.

#### REQ-DB-005: SqlAlchemyExecutionStore

| Dimension          | Requirement                                                                                                                                                                                                                                                                                                                                                                        |
| ------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Functional**     | Persist runtime execution metadata (currently `BaseRuntime._execution_metadata` dict). Store: run_id, workflow_id, status, parameters (JSON), result (JSON), error, started_at, completed_at, worker_id, metadata (JSON). Status transitions: pending -> running -> completed/failed. Query by status, workflow_id, time range.                                                    |
| **Non-Functional** | Write latency <5ms. Query latency <10ms for status filter (up to 10K records). Bounded results (default limit 1000).                                                                                                                                                                                                                                                               |
| **Interface**      | New protocol: `ExecutionStore` with methods: `record_start(run_id, workflow_id, parameters)`, `record_completion(run_id, results)`, `record_failure(run_id, error)`, `get_execution(run_id)`, `list_executions(status, workflow_id, limit)`. Constructor: `SqlAlchemyExecutionStore(engine: AsyncEngine)`. Also provide `InMemoryExecutionStore` as default (wraps existing dict). |
| **Testing**        | T1: Protocol compliance for both InMemory and SqlAlchemy backends, in-memory SQLite. T2: Real PG and MySQL -- full lifecycle, queries. T3: Integration with BaseRuntime.                                                                                                                                                                                                           |

#### REQ-DB-006: SqlAlchemyIdempotencyStore

| Dimension            | Requirement                                                                                                                                                                                                                                            |
| -------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Functional**       | Persistent store for idempotency keys. Atomic claim via dialect-appropriate upsert. Store: idempotency_key (PK), fingerprint, response_data (JSON), status_code, headers (JSON), created_at, expires_at. TTL-based expiry. Cleanup of expired records. |
| **Non-Functional**   | Claim latency <3ms (single INSERT). Exactly one claimer wins on conflict. Batched cleanup.                                                                                                                                                             |
| **Interface**        | Implement the `storage_backend` protocol expected by `RequestDeduplicator`: `get(key) -> Optional[dict]`, `set(key, data, ttl) -> None`. Constructor: `SqlAlchemyIdempotencyStore(engine: AsyncEngine)`.                                               |
| **Dialect handling** | Upsert: SQLAlchemy `insert().on_conflict_do_nothing()` on PG/SQLite, `insert().prefix_with('IGNORE')` on MySQL. Or use two-step: `SELECT` then `INSERT` in transaction.                                                                                |
| **Testing**          | T1: Protocol compliance, TTL logic, in-memory SQLite. T2: Real PG and MySQL -- store/retrieve, TTL, concurrent claims, cleanup. T3: Full RequestDeduplicator with persistent backend.                                                                  |

#### REQ-DB-007: Store Auto-Detection and Factory

| Dimension           | Requirement                                                                                                                                                                                                                                                                                                                                              |
| ------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Functional**      | `resolve_store_url()` reads env vars and returns a database URL suitable for `create_async_engine()`. Factory creates the appropriate `AsyncEngine` and store backends. Level 0: no env var = existing SQLite/in-memory backends (no SQLAlchemy import). Level 1: `KAILASH_STORE_URL` or `DATABASE_URL` set = SQLAlchemy engine + SqlAlchemy\* backends. |
| **Non-Functional**  | Level 0 must NOT import sqlalchemy (lazy import). Auto-detection adds <1ms. Clear error if `kailash[database]` not installed when URL is set.                                                                                                                                                                                                            |
| **Interface**       | `resolve_store_url() -> Optional[str]` returns URL or None. `create_store_engine(url: str, **kwargs) -> AsyncEngine` creates the engine. Each store factory: `create_event_store(engine: Optional[AsyncEngine] = None) -> EventStoreBackend`, etc.                                                                                                       |
| **Dialect support** | URL schemes: `postgresql+asyncpg://`, `mysql+aiomysql://`, `sqlite+aiosqlite:///`. Bare `postgresql://` auto-maps to `postgresql+asyncpg://`. Bare `mysql://` auto-maps to `mysql+aiomysql://`.                                                                                                                                                          |
| **Testing**         | T1: URL parsing, scheme mapping, import gating. T2: Engine creation with each dialect. T3: Level 0 -> Level 1 transition with same workflow code.                                                                                                                                                                                                        |

### 1.2 Gap 2: Distributed Task Queue

#### REQ-TQ-001: Fix Worker Deserialization

| Dimension          | Requirement                                                                                                                                                                                                                           |
| ------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Functional**     | Implement `Worker._execute_workflow_sync()` to deserialize workflow from `TaskMessage.workflow_data` and execute via LocalRuntime. Reconstruct WorkflowBuilder nodes and connections from serialized format. Pass parameters through. |
| **Non-Functional** | Must handle all 140+ node types. Validate node type exists before construction. Clear error for unknown types.                                                                                                                        |
| **Interface**      | No API change. `Worker._execute_workflow_sync(runtime, task) -> Dict[str, Any]`. Deserialization is the inverse of `DistributedRuntime._serialize_workflow()`.                                                                        |
| **Testing**        | T1: Serialize/deserialize round-trip for 1/5/20-node workflows with branches. T2: Real Redis -- enqueue/dequeue/execute cycle, verify result matches LocalRuntime. T3: Multi-worker stress test.                                      |

#### REQ-TQ-002: SQL-Backed Task Queue (SKIP LOCKED)

| Dimension            | Requirement                                                                                                                                                                                                                                                                                                                                       |
| -------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Functional**       | Task queue using `SELECT ... FOR UPDATE SKIP LOCKED` on PG and MySQL 8.0+. Degrade to `BEGIN IMMEDIATE` single-writer on SQLite. Enqueue, dequeue with priority, ack, nack, visibility timeout, stale recovery, queue metrics.                                                                                                                    |
| **Non-Functional**   | Dequeue <10ms under moderate contention (10 workers, PG/MySQL). 500 enqueue/s, 100 dequeue/s per worker. No task loss on crash. Configurable poll interval (default 1s).                                                                                                                                                                          |
| **Interface**        | `SqlAlchemyTaskQueue` with same method signatures as `TaskQueue`: `enqueue(task)`, `dequeue(timeout)`, `ack(task)`, `nack(task)`, `store_result(result)`, `get_result(task_id)`, `queue_length()`, `processing_length()`, `recover_stale_tasks(threshold)`. Constructor: `SqlAlchemyTaskQueue(engine: AsyncEngine, queue_name: str = "default")`. |
| **Dialect handling** | `with_for_update(skip_locked=True)` compiles to correct SQL on PG/MySQL. On SQLite: use advisory locking or serialize dequeue via single connection.                                                                                                                                                                                              |
| **Testing**          | T1: Task state machine, in-memory SQLite. T2: Real PG and MySQL -- concurrent dequeue from 5 connections, ack/nack, stale recovery, dead-letter. T3: Full DistributedRuntime + Worker using SqlAlchemyTaskQueue.                                                                                                                                  |

### 1.3 Gap 3: Exactly-Once Execution with Idempotency Keys

#### REQ-ID-001: Execution-Level Idempotent Executor

| Dimension          | Requirement                                                                                                                                                                 |
| ------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Functional**     | `IdempotentExecutor` wraps workflow execution. Atomic claim of idempotency key before executing. Cached result return on duplicate. Release claim on failure (allow retry). |
| **Non-Functional** | Claim is single round-trip (<3ms on PG/MySQL). No double-execution. Released claims immediately available.                                                                  |
| **Interface**      | `IdempotentExecutor(store: SqlAlchemyIdempotencyStore, runtime: BaseRuntime)`. Method: `execute(workflow, parameters, idempotency_key) -> Tuple[Dict, str]`.                |
| **Testing**        | T1: Claim/release state machine. T2: Real PG -- two concurrent executors, same key, only one executes. T3: Full end-to-end with DurableGateway.                             |

#### REQ-ID-002: Persistent Deduplicator Backend

| Dimension          | Requirement                                                                                                                                                  |
| ------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Functional**     | Implement `storage_backend` protocol for `RequestDeduplicator`: `get(key)`, `set(key, data, ttl)`. Store via SqlAlchemyIdempotencyStore. Background cleanup. |
| **Non-Functional** | Get <3ms, Set <5ms. Batched cleanup (1000 per cycle).                                                                                                        |
| **Interface**      | Same `get()`/`set()` protocol as `RequestDeduplicator` expects.                                                                                              |
| **Testing**        | T1: round-trip, TTL. T2: Real PG/MySQL -- store, retrieve, TTL expiry. T3: Full dedup survives restart.                                                      |

---

## 2. Architecture Decision Records

### ADR-001: Database Abstraction Layer (Supersedes PG Driver Choice)

#### Status

**Accepted** -- per supplementary brief `02-multi-database-strategy.md`.

#### Context

The original brief proposed psycopg3 for sync stores and asyncpg for async stores. The kailash-rs team uses sqlx's `Any` driver for multi-database portability. The Python equivalent is SQLAlchemy Core.

The SDK already has `sqlalchemy>=2.0.0` in the `[database]` optional extra. asyncpg is in `[postgres]`. aiomysql is in `[mysql]`. aiosqlite is in `[database]`.

Building PostgreSQL-only backends would:

1. Lock infrastructure stores to one database vendor.
2. Require two different PG driver integrations (psycopg3 sync + asyncpg async).
3. Ignore MySQL 8.0+ which supports SKIP LOCKED, JSON, and upserts.
4. Mean the Level 0 SQLite code shares zero implementation with Level 1 PG code.

#### Decision

**Use SQLAlchemy Core (async engine) for all new infrastructure store backends.**

- `create_async_engine(url)` handles dialect selection via URL scheme.
- Tables defined via `sqlalchemy.Table` + `MetaData` (not ORM).
- All store methods are `async def`, using `async with engine.begin() as conn`.
- Dialect-specific optimizations (JSONB on PG, SKIP LOCKED) handled by SQLAlchemy's compiler.
- Existing raw SQLite backends (SqliteEventStoreBackend, PersistentDLQ, DiskStorage) remain as the Level 0 zero-dependency defaults.

#### Consequences

**Positive:**

- One implementation covers PostgreSQL + MySQL 8.0+ + SQLite.
- No new dependencies (SQLAlchemy, asyncpg, aiomysql, aiosqlite all already optional extras).
- Level 0 SQLite backends unchanged (no SQLAlchemy import at Level 0).
- Aligns with kailash-rs's multi-database approach.
- SQLAlchemy handles connection pooling, dialect compilation, type mapping.

**Negative:**

- SQLAlchemy Core is more verbose than raw psycopg3 for simple queries.
- The trust-plane's psycopg3 pattern (773 lines, battle-tested) cannot be directly reused -- new pattern needed.
- Testing matrix expands: every store must be tested on PG + MySQL + SQLite.
- SKIP LOCKED behavior differs on SQLite (no real SKIP LOCKED -- must degrade to single-writer).

**Impact on existing code:**

- `DatabaseStateStorage` (saga) stays on asyncpg. Converting it to SQLAlchemy is a v1.1.0 candidate.
- trust-plane's `PostgresTrustPlaneStore` stays on psycopg3. It is in a separate package with its own lifecycle.
- DataFlow's `PostgreSQLAdapter` stays on asyncpg.

#### Alternatives Considered

**Option A: psycopg3 (sync) + asyncpg (async), PG-only.**

- The original brief's proposal.
- Pro: Production pattern exists in trust-plane.
- Con: PG-only, two drivers, no MySQL.
- Rejected by supplementary brief.

**Option B: psycopg3 for everything (sync + async via psycopg.AsyncConnection).**

- Pro: Single PG driver.
- Con: Still PG-only. No MySQL.
- Rejected by supplementary brief.

**Option C: SQLAlchemy ORM.**

- Pro: Higher-level API, less code.
- Con: ORM adds overhead, complexity, and learning curve for simple stores. Core is sufficient.
- Rejected: Over-abstraction.

---

### ADR-002: Store Auto-Detection Strategy

#### Status

**Accepted**

#### Context

The progressive infrastructure model requires auto-detection of storage backends from environment variables. The user sets a URL; all stores switch to the target database. The question is which env var(s) to use.

SQLAlchemy's `create_async_engine(url)` accepts a standard database URL. The format is `dialect+driver://user:pass@host/db`. This simplifies detection -- the URL fully encodes the backend choice.

Competing concerns:

- `DATABASE_URL` is the de facto standard (Heroku, Railway, Render, Django).
- DataFlow already reads `DATABASE_URL` for its own PostgreSQL connection.
- Users may want DataFlow on one database and runtime stores on another.

#### Decision

**Use `KAILASH_STORE_URL` as the primary env var, with `DATABASE_URL` as fallback.**

Resolution order:

1. `KAILASH_STORE_URL` -- if set, use it. Explicit, unambiguous.
2. `DATABASE_URL` -- if set and `KAILASH_STORE_URL` is not, use it.
3. Neither set -- return None (Level 0: existing SQLite/in-memory backends, no SQLAlchemy).

```python
def resolve_store_url() -> Optional[str]:
    """Resolve the store database URL from environment.

    Priority: KAILASH_STORE_URL > DATABASE_URL > None (Level 0 default).

    Returns a SQLAlchemy-compatible async URL. Bare 'postgresql://' and
    'mysql://' schemes are auto-mapped to their async driver variants.
    """
    url = os.environ.get("KAILASH_STORE_URL") or os.environ.get("DATABASE_URL")
    if not url:
        return None

    # Auto-map bare schemes to async driver variants
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    elif url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif url.startswith("mysql://"):
        url = url.replace("mysql://", "mysql+aiomysql://", 1)
    elif url.startswith("sqlite:///"):
        url = url.replace("sqlite:///", "sqlite+aiosqlite:///", 1)

    return url
```

Per-store overrides via constructor remain available for advanced users.

#### Consequences

**Positive:**

- `KAILASH_STORE_URL` avoids collision with DataFlow's `DATABASE_URL` usage.
- `DATABASE_URL` fallback covers the 80% case (single database).
- Auto-mapping of bare schemes removes friction (users do not need to know about `+asyncpg`).
- Clear precedence: explicit > convention > default.

**Negative:**

- Two env vars to document (but fallback is standard).
- Auto-mapping hides the driver choice -- may confuse users debugging connection issues.

#### Alternatives Considered

**Option A: `DATABASE_URL` only.** Rejected: collision with DataFlow.
**Option B: Per-store env vars.** Rejected: complexity explosion.
**Option C: `KAILASH_STORE_URL` only, no fallback.** Rejected: unnecessary friction.

---

### ADR-003: Schema Migration Strategy

#### Status

**Accepted** (with nuance)

#### Context

Every SQLAlchemy-backed store needs schema management. The supplementary brief recommends Alembic. However, Alembic's standard workflow (generate migration files, run `alembic upgrade head`) is designed for application developers, not library consumers.

Key constraints:

- The SDK is a library, not a service. Users embed it in their applications.
- Users should not need to run a separate CLI command to set up their database.
- Multiple SDK versions may connect concurrently during rolling deploys.
- The `[database]` extra includes SQLAlchemy but NOT Alembic. Adding Alembic is a new dependency.

#### Decision

**Hybrid approach: SQLAlchemy `metadata.create_all()` for initial schema + programmatic Alembic for future migrations.**

**For v1.0.0:**

- Use `metadata.create_all(engine)` on first connection. This is idempotent (`checkfirst=True` by default) and requires zero configuration.
- Store a schema version in a `kailash_meta` table (single row: `{"schema_version": 1}`).
- If the database schema version is newer than the code, raise `SchemaTooNewError`.

**For v1.1.0+ (when migrations are needed):**

- Add Alembic as an optional dependency in a `[migrations]` extra.
- Ship migration scripts embedded in the package (`kailash/infrastructure/migrations/`).
- Programmatic migration via `alembic.command.upgrade(config, "head")` called from `initialize()`.
- Users who prefer manual control can run `kailash db upgrade` CLI command.
- Users WITHOUT Alembic installed get a clear error: "Schema v2 detected but Alembic not installed. Run `pip install kailash[migrations]` or `kailash db upgrade`."

**Why not Alembic now (v1.0.0):**

- v1.0.0 ships schema version 1. No migrations exist. `create_all()` handles everything.
- Adding Alembic now adds a dependency for zero benefit (no migrations to run).
- The schema version table ensures v1.1.0 can detect the v1.0.0 schema and migrate forward.

```python
SCHEMA_VERSION = 1

async def initialize_stores(engine: AsyncEngine) -> None:
    """Create all store tables and verify schema version.

    Idempotent. Safe to call multiple times and from multiple processes.
    """
    async with engine.begin() as conn:
        await conn.run_sync(metadata.create_all)

        # Check/set schema version
        result = await conn.execute(
            select(kailash_meta.c.value).where(kailash_meta.c.key == "schema_version")
        )
        row = result.first()

        if row is None:
            # Fresh database -- stamp with current version
            await conn.execute(
                kailash_meta.insert().values(key="schema_version", value=str(SCHEMA_VERSION))
            )
        elif int(row[0]) > SCHEMA_VERSION:
            raise SchemaTooNewError(db_version=int(row[0]), code_version=SCHEMA_VERSION)
        elif int(row[0]) < SCHEMA_VERSION:
            # Future: run migrations here
            raise SchemaMigrationRequired(
                db_version=int(row[0]), code_version=SCHEMA_VERSION
            )
```

#### Consequences

**Positive:**

- Zero-config for v1.0.0: `create_all()` just works.
- No new dependency for v1.0.0.
- Schema version table is planted for future Alembic integration.
- Rolling deploy safe: `SchemaTooNewError` prevents downgraded code from corrupting.

**Negative:**

- v1.0.0 cannot ALTER TABLE. If a schema mistake ships, it requires a manual fix or waiting for v1.1.0 with Alembic.
- Deferred Alembic integration means v1.1.0 has more work.

**Constraints for v1.0.0 schema design:**

- Schema must be correct on first try. Review carefully.
- All columns must have sensible defaults (for forward compatibility).
- No columns that might need renaming. Use generic names.
- JSON columns for extensibility (future fields go in the JSON blob, not new columns).

#### Alternatives Considered

**Option A: Trust-plane custom migration (meta table + sequential functions).**

- Pro: Battle-tested in trust-plane. No dependency.
- Con: Cannot leverage SQLAlchemy's migration infrastructure. Duplicates Alembic's purpose.
- Rejected: If we are using SQLAlchemy, use SQLAlchemy's migration tool when needed.

**Option B: Alembic from day one.**

- Pro: Future-proof.
- Con: New dependency for zero benefit in v1.0.0 (no migrations exist).
- Rejected for v1.0.0: YAGNI. Ship it with v1.1.0 when migrations are actually needed.

**Option C: No schema versioning.**

- Pro: Simplest.
- Con: No forward migration path.
- Rejected: Too limiting.

---

## 3. Non-Functional Requirements

### Performance Requirements

| Metric                           | Target (PG/MySQL)  | Target (SQLite)     | Measurement                 |
| -------------------------------- | ------------------ | ------------------- | --------------------------- |
| EventStore append (100 events)   | <10ms              | <20ms               | Integration test with timer |
| EventStore read (1K events)      | <5ms               | <10ms               | Integration test with timer |
| Checkpoint save (1MB)            | <20ms              | <30ms               | Integration test with timer |
| Checkpoint load (1MB)            | <15ms              | <20ms               | Integration test with timer |
| DLQ enqueue                      | <5ms               | <5ms                | Integration test with timer |
| Idempotency claim                | <3ms               | <5ms                | Integration test with timer |
| Task queue dequeue (SKIP LOCKED) | <10ms (10 workers) | N/A (single-writer) | Contention test             |
| Auto-detection overhead          | <1ms               | <1ms                | Unit test with timer        |
| Level 0 startup (no SQLAlchemy)  | 0ms additional     | 0ms additional      | Must not import sqlalchemy  |

### Durability Requirements

| Guarantee                 | PG/MySQL               | SQLite            |
| ------------------------- | ---------------------- | ----------------- |
| Events survive crash      | Transaction commit     | WAL mode + commit |
| Checkpoints survive crash | Transaction commit     | WAL mode + commit |
| DLQ items survive crash   | Transaction commit     | WAL mode + commit |
| Idempotency claims atomic | INSERT ... ON CONFLICT | INSERT OR IGNORE  |
| Task queue dequeue atomic | FOR UPDATE SKIP LOCKED | BEGIN IMMEDIATE   |

### Security Requirements

| Requirement                   | Implementation                                   |
| ----------------------------- | ------------------------------------------------ |
| Connection string not in logs | URL sanitization strips passwords before logging |
| Parameterized queries only    | SQLAlchemy Core uses bound parameters by default |
| Connection pooling            | SQLAlchemy's built-in pool (configurable)        |
| Input validation              | All IDs validated before use in queries          |
| No raw SQL strings            | All queries via SQLAlchemy expression language   |

### Scalability Requirements

| Dimension                          | Target                                                          |
| ---------------------------------- | --------------------------------------------------------------- |
| Concurrent connections             | Configurable via SQLAlchemy pool_size (default 5 + 10 overflow) |
| Max events per stream              | No practical limit (database table size)                        |
| Max checkpoint size                | 50MB (database BLOB/BYTEA limit)                                |
| Max DLQ items                      | 10,000 (bounded with eviction)                                  |
| Max task queue depth               | No practical limit (indexed status queries)                     |
| Max concurrent workers (SQL queue) | 50+ on PG/MySQL (SKIP LOCKED); 1 on SQLite                      |

---

## 4. Scope for v1.0.0 vs v1.1.0

### Critical Analysis

The full scope spans 3 gaps, 11 requirement IDs, and 18 TODOs. v1.0.0 is on a release branch. The question is: what is the **minimum credible scope** that lets v1.0.0 claim "progressive infrastructure"?

### v1.0.0 MUST Ship (Level 0 -> Level 1: Single Env Var to Database)

| ID         | Item                             | Effort    | Justification                                                                                          |
| ---------- | -------------------------------- | --------- | ------------------------------------------------------------------------------------------------------ |
| **DB-001** | SqlAlchemyEventStoreBackend      | 2-3d      | Audit trail foundation. Events lost on restart without DB backend.                                     |
| **DB-002** | SqlAlchemyCheckpointStorage      | 1-2d      | Workflow recovery across restarts.                                                                     |
| **DB-003** | SqlAlchemyDLQ                    | 1-2d      | Production retry logic. Port from SQLite DLQ structure.                                                |
| **DB-004** | Complete DatabaseStateStorage    | 0.5d      | Trivial fix (one CREATE TABLE). Unblocks saga users.                                                   |
| **DB-007** | Store auto-detection + factory   | 1-2d      | `KAILASH_STORE_URL` wiring. Without this, backends exist but are unusable without manual construction. |
| **SCHEMA** | Schema versioning (kailash_meta) | 0.5d      | Plants schema version for future migrations.                                                           |
| **TEST**   | Integration tests (PG + SQLite)  | 3-4d      | Prove it works. docker-compose with PG 16. SQLAlchemy SQLite for fast CI.                              |
|            | **Subtotal**                     | **9-14d** |                                                                                                        |

### v1.0.0 SHOULD Ship (If Time Permits)

| ID          | Item                       | Effort   | Justification                                                                       |
| ----------- | -------------------------- | -------- | ----------------------------------------------------------------------------------- |
| **DB-005**  | SqlAlchemyExecutionStore   | 2-3d     | Useful but `_execution_metadata` dict works for single-process.                     |
| **DB-006**  | SqlAlchemyIdempotencyStore | 1-2d     | Foundation for exactly-once, but dedup works in-memory.                             |
| **TEST-MY** | MySQL integration tests    | 1-2d     | Validates multi-database claim. Can ship as PG+SQLite only and add MySQL in v1.0.1. |
|             | **Subtotal**               | **4-7d** |                                                                                     |

### v1.1.0 (Deferred -- Level 2 Features + Polish)

| ID         | Item                                       | Effort     | Justification                                   |
| ---------- | ------------------------------------------ | ---------- | ----------------------------------------------- |
| **TQ-001** | Fix Worker deserialization                 | 2-3d       | Level 2 (multi-worker). Not needed for Level 1. |
| **TQ-002** | SQL-backed task queue (SKIP LOCKED)        | 3-5d       | Level 2 feature.                                |
| **ID-001** | IdempotentExecutor                         | 2-3d       | Cross-worker concern.                           |
| **ID-002** | Persistent dedup backend                   | 1d         | Enhancement over in-memory.                     |
| **MIG**    | Alembic migration integration              | 2-3d       | Needed when schema v2 ships.                    |
| **SAGA**   | Convert DatabaseStateStorage to SQLAlchemy | 2d         | Consistency with other stores.                  |
| **INT**    | Redis + task queue integration tests       | 2-3d       | Level 2 test coverage.                          |
|            | **Subtotal**                               | **14-20d** |                                                 |

### v1.0.0 Scope Summary

```
v1.0.0 MUST (9-14 days):
  Level 0 -> Level 1: "Set KAILASH_STORE_URL and all stores persist to your database"
  - 3 SQLAlchemy store backends (EventStore, Checkpoint, DLQ) covering PG + SQLite
  - 1 asyncpg fix (DatabaseStateStorage._ensure_table_exists)
  - Store auto-detection from KAILASH_STORE_URL / DATABASE_URL
  - Schema versioning (kailash_meta table)
  - Integration tests against real PostgreSQL

v1.0.0 SHOULD (+4-7 days):
  - ExecutionStore, IdempotencyStore
  - MySQL integration tests

v1.1.0 DEFERRED (14-20 days):
  Level 2: "Distribute work across workers via SQL or Redis task queue"
  - Worker deserialization, SQL task queue, idempotent executor
  - Alembic migration framework
  - Convert saga storage to SQLAlchemy
```

### Decision Rationale

The MUST scope delivers: **a user goes from SQLite to PostgreSQL (or MySQL) by setting one env var, without changing code.** This is Level 1 of progressive infrastructure. It is the minimum credible claim.

Level 2 (multi-worker) is materially different: distributed coordination, task serialization, cross-worker idempotency. Shipping it half-baked is worse than shipping a clean Level 1 and declaring Level 2 for v1.1.0.

MySQL validation can ship in v1.0.1 if time is tight for v1.0.0. The SQLAlchemy abstraction guarantees MySQL will work -- the risk is low-level dialect differences in edge cases, not fundamental incompatibility.

---

## 5. Risk Assessment

### High Probability, High Impact (Critical)

1. **SQLAlchemy import at Level 0 breaks zero-dep startup**
   - Risk: If auto-detection code imports sqlalchemy at module level, `import kailash` fails without `kailash[database]`.
   - Mitigation: All SQLAlchemy imports MUST be lazy (inside factory functions, guarded by try/except). Unit test: `import kailash` succeeds with only 4 core deps.
   - Prevention: CI "minimal deps" test job.

2. **DATABASE_URL collision with DataFlow**
   - Risk: DataFlow and core stores both read `DATABASE_URL`, creating tables in DataFlow's database.
   - Mitigation: `KAILASH_STORE_URL` takes precedence. Warn if both are set and differ.
   - Prevention: ADR-002 establishes precedence.

3. **SQLAlchemy JSON type inconsistency across dialects**
   - Risk: JSON column stores JSONB on PG (binary, queryable), JSON on MySQL (text, queryable), TEXT on SQLite (no query). Store code assumes JSON query operators that do not exist on SQLite.
   - Mitigation: Store code must NOT use dialect-specific JSON operators in queries. Use Python-side filtering for JSON contents. Store full objects, query by indexed columns only.
   - Prevention: All stores tested on SQLite (catches dialect leaks immediately).

### Medium Probability, High Impact (Monitor)

4. **SQLAlchemy async engine event loop conflicts**
   - Risk: `create_async_engine()` requires an event loop. Sync runtimes (LocalRuntime) may not have one.
   - Mitigation: Use `asyncio.run()` in sync entry points. Or: provide sync wrapper that creates an event loop. Or: defer engine creation to first async call.
   - Prevention: Test both sync and async runtime paths with SQLAlchemy stores.

5. **Schema v1 design mistake in v1.0.0**
   - Risk: v1.0.0 ships a schema that needs ALTER TABLE in v1.1.0, but Alembic is not yet integrated.
   - Mitigation: Use JSON columns liberally (extensible without schema change). Keep indexed columns to the minimum. Review schema carefully before release.
   - Prevention: Peer review of all CREATE TABLE statements.

6. **Connection pool exhaustion**
   - Risk: Default pool_size (5+10 overflow) too small for high-throughput applications.
   - Mitigation: Configurable via engine kwargs. Document recommended settings.
   - Prevention: Integration tests with concurrent connections.

### Medium Probability, Medium Impact (Address)

7. **MySQL dialect differences in datetime handling**
   - Risk: MySQL's DATETIME precision defaults to seconds (not microseconds). Ordering by timestamp may produce ties.
   - Mitigation: Use `DateTime(fsp=6)` on MySQL for microsecond precision. SQLAlchemy `DateTime` with `timezone=True` handles this.
   - Prevention: Integration tests verify timestamp ordering on MySQL.

8. **aiosqlite performance under concurrent writes**
   - Risk: SQLite via aiosqlite serializes writes. Under concurrent access, contention is high.
   - Mitigation: This matches existing SQLite behavior (WAL mode, single writer). The SQLAlchemy SQLite path is not designed for multi-worker -- that is what PG/MySQL is for.
   - Prevention: Document that SQLite SQLAlchemy path is for Level 0/development, not production multi-worker.

### Low Probability, High Impact (Accept)

9. **SQLAlchemy 3.0 breaking changes**
   - Risk: SQLAlchemy 3.0 may change async engine API.
   - Mitigation: Pin `sqlalchemy>=2.0.0,<3.0.0` in extras.
   - Prevention: Version pinning.

---

## 6. Integration with Existing SDK

### Reusable Components

| Component                    | Source                   | Target Use                                          |
| ---------------------------- | ------------------------ | --------------------------------------------------- |
| `StorageBackend` protocol    | `checkpoint_manager.py`  | SqlAlchemyCheckpointStorage implements this         |
| `EventStoreBackend` protocol | `event_store_backend.py` | SqlAlchemyEventStoreBackend implements this         |
| `DLQItem` dataclass          | `dlq.py`                 | Shared between PersistentDLQ and SqlAlchemyDLQ      |
| `RequestFingerprinter`       | `deduplicator.py`        | Used by IdempotencyStore for fingerprint generation |
| `TaskMessage` / `TaskResult` | `distributed.py`         | Used by SqlAlchemyTaskQueue (same serialization)    |
| `PoolConfig` dataclass       | `database_config.py`     | Can inform SQLAlchemy pool settings                 |

### Components Needing Modification

| Component                                     | Modification                                                                                 |
| --------------------------------------------- | -------------------------------------------------------------------------------------------- |
| `EventStore.__init__`                         | Add auto-detection: if `resolve_store_url()` returns URL, create SqlAlchemyEventStoreBackend |
| `CheckpointManager.__init__`                  | Add optional `store_url` parameter for auto-detection                                        |
| `BaseRuntime.__init__`                        | Add optional `execution_store` parameter                                                     |
| `pyproject.toml` `[database]` extra           | Already includes sqlalchemy + aiosqlite. No change needed.                                   |
| `DatabaseStateStorage._ensure_table_exists()` | Add CREATE TABLE IF NOT EXISTS SQL                                                           |

### Components That Must Not Change

| Component                               | Reason                                       |
| --------------------------------------- | -------------------------------------------- |
| `SqliteEventStoreBackend`               | Level 0 zero-dep default. Untouched.         |
| `PersistentDLQ` (SQLite)                | Level 0 zero-dep default. Untouched.         |
| `DiskStorage` / `MemoryStorage`         | Level 0 defaults. Untouched.                 |
| `InMemoryStateStorage`                  | Level 0 saga default. Untouched.             |
| `PostgresTrustPlaneStore` (trust-plane) | Separate package, psycopg3. Not our concern. |
| DataFlow `PostgreSQLAdapter`            | Separate package, asyncpg. Not our concern.  |
| All 1000+ existing tests                | Must pass unchanged at Level 0.              |

---

## 7. Implementation Roadmap

### Phase 1: Foundation (Days 1-3)

1. **ADR decisions finalized** (this document, reviewed by human).
2. **Store infrastructure module** (`src/kailash/infrastructure/`):
   - `store_factory.py`: `resolve_store_url()`, `create_store_engine()`, per-store factory functions.
   - `schema.py`: SQLAlchemy `MetaData` + all `Table` definitions (kailash_events, kailash_checkpoints, kailash_dlq, kailash_meta).
   - `base.py`: Shared helpers (URL sanitization, schema version check).
3. **docker-compose.yml** for integration tests (PG 16 + Redis 7).
4. **Schema review**: All Table definitions reviewed before any code is written.

### Phase 2: Core Stores (Days 3-8)

5. **SqlAlchemyEventStoreBackend** -- implements EventStoreBackend protocol via SQLAlchemy Core.
6. **SqlAlchemyCheckpointStorage** -- implements StorageBackend protocol.
7. **SqlAlchemyDLQ** -- port of PersistentDLQ logic to SQLAlchemy.
8. **Complete DatabaseStateStorage** -- single CREATE TABLE IF NOT EXISTS.
9. **Auto-detection wiring** -- EventStore, CheckpointManager gain store_url awareness.
10. **Schema versioning** -- kailash_meta table with version stamp.

### Phase 3: Integration Tests (Days 8-12)

11. **SQLAlchemy SQLite tests** -- fast, run in CI without docker.
12. **PostgreSQL integration tests** -- real PG via docker-compose.
13. **End-to-end test**: Level 0 workflow -> set KAILASH_STORE_URL -> same workflow -> verify data in database.
14. **CI configuration** for PG integration tests.

### Phase 4: Polish (Days 12-14)

15. **Error messages** -- clear guidance when `kailash[database]` not installed.
16. **CHANGELOG** entry for v1.0.0.
17. **Level 0/1 progressive infrastructure verification** -- manual walkthrough.

---

## 8. Success Criteria

### v1.0.0 Release Gate

- [ ] `pip install kailash && python workflow.py` works with zero env vars (Level 0 unchanged)
- [ ] `pip install kailash[database,postgres] && KAILASH_STORE_URL=postgresql://... python workflow.py` persists all state to PG
- [ ] `pip install kailash[database] && KAILASH_STORE_URL=sqlite+aiosqlite:///kailash.db python workflow.py` persists all state to SQLite via SQLAlchemy
- [ ] All 1000+ existing tests pass unchanged (Level 0 regression)
- [ ] 3 SQLAlchemy store backends + 1 asyncpg fix implemented and tested
- [ ] Store auto-detection works with KAILASH_STORE_URL and DATABASE_URL fallback
- [ ] SQLAlchemy is NOT imported when KAILASH_STORE_URL is not set (Level 0 lazy import)
- [ ] No new mandatory dependencies added
- [ ] Schema version table planted in all databases (future migration path)
- [ ] Connection strings never appear in logs or error messages
- [ ] All queries use SQLAlchemy bound parameters (no string interpolation)
- [ ] Integration tests pass on PostgreSQL 16 with real database

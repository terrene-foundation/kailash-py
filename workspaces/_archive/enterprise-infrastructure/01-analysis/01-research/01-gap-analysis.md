# Enterprise Infrastructure Gap Analysis: kailash-py

> This workspace was created by the kailash-rs team for the kailash-py dev team to action.

**Date**: 2026-03-17
**Scope**: PostgreSQL persistence, distributed task queue, idempotency
**Baseline**: kailash-py v1.0.0 (includes v0.13.0 production-readiness features)

---

## 1. Inventory: What Python Already Has vs What's Missing

### 1.1 Store-by-Store Assessment

| Store | Purpose | SQLite/File Backend | PG Backend | Gap |
|-------|---------|-------------------|------------|-----|
| **EventStore** | Append-only event log with projections | `SqliteEventStoreBackend` (WAL mode) | None | Need `PostgresEventStoreBackend` |
| **CheckpointManager** | Tiered checkpoint storage | `DiskStorage` (file-backed, gzip) + `MemoryStorage` (LRU) | None | Need `PostgresCheckpointStorage` |
| **PersistentDLQ** | Dead letter queue with retry | SQLite-backed, `PersistentDLQ` class | None | Need `PostgresDLQ` or adapter |
| **SagaStateStorage** | Saga state persistence | `InMemoryStateStorage` | `DatabaseStateStorage` (asyncpg) -- **exists but incomplete** | Complete table creation in `_ensure_table_exists()` |
| **SagaStateStorage** | Saga state persistence | -- | `RedisStateStorage` -- **fully implemented** | None (Redis path complete) |
| **ExecutionMetadata** | Runtime execution tracking | In-memory dict (`BaseRuntime._execution_metadata`) | None | Need `PostgresExecutionStore` |
| **SearchAttributes** | Cross-execution queries | SQLite EAV table (shipped v0.13.0) | None | Need PG-backed search attributes |
| **Deduplicator** | Idempotency key store | In-memory LRU (`OrderedDict`) | None | Need `PostgresIdempotencyStore` |
| **SchedulerJobStore** | APScheduler job persistence | Default (SQLAlchemy/memory) | None | APScheduler has built-in PG support via SQLAlchemy |

### 1.2 Existing PostgreSQL Implementations (Reference Patterns)

**trust-plane `PostgresTrustPlaneStore`** (`packages/trust-plane/src/trustplane/store/postgres.py`):
- Uses **psycopg 3** (sync) with `psycopg_pool.ConnectionPool`
- JSONB columns for all record data
- Schema versioning with `meta` table and migration framework
- `_safe_connection()` context manager wrapping pool errors into domain exceptions
- Parameterized queries throughout (no string interpolation)
- `ON CONFLICT ... DO UPDATE` for upserts
- Status indexes for filtered queries
- Connection string sanitization in error messages
- **773 lines, production-quality, fully tested (e2e with real PostgreSQL)**

**Kaizen `PostgresTrustStore`** (`packages/kailash-kaizen/src/kaizen/trust/store.py`):
- Uses **DataFlow** (which uses asyncpg under the hood)
- Auto-generates 11 CRUD nodes per model
- LRU cache with TTL for reads
- Async interface via `AsyncLocalRuntime`

**DataFlow `PostgreSQLAdapter`** (`packages/kailash-dataflow/src/dataflow/adapters/postgresql.py`):
- Uses **asyncpg** directly
- Connection pool with reset callback (rolls back leaked transactions)
- Full async interface

**Saga `DatabaseStateStorage`** (`src/kailash/nodes/transaction/saga_state_storage.py`):
- Uses **asyncpg** via generic `db_pool`
- JSONB upsert for state storage
- `_ensure_table_exists()` is a **no-op stub** -- table creation deferred to "external migrations"
- `StorageFactory.create_storage("database", db_pool=pool)` -- factory pattern exists

### 1.3 Task Queue Assessment

**Existing `DistributedRuntime`** (`src/kailash/runtime/distributed.py`):
- `TaskQueue`: Redis BRPOPLPUSH for reliable delivery
- `TaskMessage`: JSON serialization with visibility timeout, max attempts
- `Worker`: Configurable concurrency, heartbeat, dead worker detection, stale task recovery
- `DistributedRuntime`: Extends `BaseRuntime`, enqueues instead of executing
- **Critical gap**: `Worker._execute_workflow_sync()` raises `NotImplementedError`

**Existing Redis usage**:
- `RedisStateStorage` for sagas (sync/async client auto-detection)
- Distributed circuit breaker via Redis with Lua scripts (shipped v0.13.0)
- `kailash[distributed]` optional dependency: `redis>=6.2.0`

### 1.4 Idempotency Assessment

**Existing `RequestDeduplicator`** (`src/kailash/middleware/gateway/deduplicator.py`):
- `RequestFingerprinter`: SHA-256 of normalized request components
- `RequestDeduplicator`: LRU cache (`OrderedDict`) with TTL
- Idempotency key validation (same key must map to same request)
- `storage_backend` parameter (optional, for persistent storage)
- `_check_storage()` / `_store_response()` -- calls backend `get()`/`set()` methods
- **No persistent backend implementation shipped**

**Existing `DurableRequest`** (`src/kailash/middleware/gateway/durable_request.py`):
- `RequestMetadata.idempotency_key` field exists
- Used in validation checkpoint but **not enforced for deduplication**
- No link between DurableRequest and RequestDeduplicator

---

## 2. PostgreSQL Backend Implementation Plan

### 2.1 Design Principles

1. **Follow trust-plane pattern**: psycopg3 for sync stores, asyncpg for async stores
2. **JSONB for flexibility**: Store complex data as JSONB, extract indexed fields as columns
3. **Schema versioning**: Every PG store gets a `meta` table with `schema_version`
4. **Auto-detection**: `DATABASE_URL` env var triggers PG backend; absence means SQLite
5. **Optional dependency**: PG backends require `psycopg[binary]>=3.0` and `psycopg_pool` (for sync) or `asyncpg>=0.30.0` (for async)

### 2.2 PostgresEventStoreBackend

**Implements**: `EventStoreBackend` protocol (already defined in `event_store_backend.py`)

**Schema**:
```sql
CREATE TABLE IF NOT EXISTS kailash_events (
    event_id     TEXT PRIMARY KEY,
    request_id   TEXT NOT NULL,
    event_type   TEXT NOT NULL,
    sequence_num INTEGER NOT NULL,
    data         JSONB NOT NULL,
    metadata     JSONB DEFAULT '{}',
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_events_request_id ON kailash_events (request_id, sequence_num);
CREATE INDEX idx_events_type ON kailash_events (event_type);
CREATE INDEX idx_events_created ON kailash_events (created_at);
```

**Methods**:
- `append(key, events)` -- batch INSERT with `ON CONFLICT DO NOTHING`
- `get(key)` -- SELECT by request_id ordered by sequence_num
- `get_range(key, start_seq, end_seq)` -- bounded query

**Effort**: 2-3 days (schema + implementation + tests)

### 2.3 PostgresCheckpointStorage

**Implements**: `StorageBackend` protocol (defined in `checkpoint_manager.py`)

**Schema**:
```sql
CREATE TABLE IF NOT EXISTS kailash_checkpoints (
    key         TEXT PRIMARY KEY,
    data        BYTEA NOT NULL,
    size_bytes  INTEGER NOT NULL,
    compressed  BOOLEAN DEFAULT FALSE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    accessed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_checkpoints_created ON kailash_checkpoints (created_at);
```

**Methods**:
- `save(key, data)` -- UPSERT with BYTEA storage
- `load(key)` -- SELECT + update `accessed_at`
- `delete(key)` -- DELETE by key
- `list_keys(prefix)` -- SELECT key WHERE key LIKE prefix%
- `gc(retention)` -- DELETE WHERE created_at < threshold

**Effort**: 1-2 days (straightforward key-value pattern)

### 2.4 PostgresDLQ

**Two approaches**:

**Option A**: Adapt `PersistentDLQ` to accept a connection pool instead of a file path. The existing SQLite schema maps directly to PostgreSQL. Replace `sqlite3` calls with psycopg3 equivalents.

**Option B**: Create a new class that implements the same interface using the trust-plane pattern (psycopg3 pool, JSONB, parameterized queries).

**Recommendation**: Option A (adapter) -- the existing `PersistentDLQ` is well-structured with clean SQL. The conversion is mechanical.

**Schema** (same as SQLite, ported):
```sql
CREATE TABLE IF NOT EXISTS kailash_dlq (
    id           TEXT PRIMARY KEY,
    workflow_id  TEXT NOT NULL,
    error        TEXT NOT NULL,
    payload      TEXT NOT NULL,
    created_at   TEXT NOT NULL,
    retry_count  INTEGER DEFAULT 0,
    max_retries  INTEGER DEFAULT 3,
    next_retry_at TEXT,
    status       TEXT DEFAULT 'pending'
);
CREATE INDEX idx_dlq_status ON kailash_dlq (status);
CREATE INDEX idx_dlq_next_retry ON kailash_dlq (next_retry_at) WHERE status = 'pending';
```

**Effort**: 1-2 days

### 2.5 Complete DatabaseStateStorage

The saga `DatabaseStateStorage` already exists with asyncpg queries. The only gap is `_ensure_table_exists()` which is a no-op.

**Fix**: Add the CREATE TABLE statement:
```sql
CREATE TABLE IF NOT EXISTS saga_states (
    saga_id    TEXT PRIMARY KEY,
    state_data JSONB NOT NULL,
    status     TEXT,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_saga_status ON saga_states (status);
```

**Effort**: 0.5 days (trivial fix + tests)

### 2.6 PostgresExecutionStore

**New class** for persisting runtime execution metadata (currently an in-memory dict in `BaseRuntime`).

**Schema**:
```sql
CREATE TABLE IF NOT EXISTS kailash_executions (
    run_id       TEXT PRIMARY KEY,
    workflow_id  TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'pending',
    parameters   JSONB DEFAULT '{}',
    result       JSONB,
    error        TEXT,
    started_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    worker_id    TEXT,
    metadata     JSONB DEFAULT '{}'
);
CREATE INDEX idx_executions_status ON kailash_executions (status);
CREATE INDEX idx_executions_workflow ON kailash_executions (workflow_id);
CREATE INDEX idx_executions_started ON kailash_executions (started_at);
```

**Effort**: 2-3 days (new store + runtime integration)

### 2.7 PostgresIdempotencyStore

**Schema**:
```sql
CREATE TABLE IF NOT EXISTS kailash_idempotency (
    idempotency_key TEXT PRIMARY KEY,
    fingerprint     TEXT NOT NULL,
    response_data   JSONB NOT NULL,
    status_code     INTEGER NOT NULL,
    headers         JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at      TIMESTAMPTZ NOT NULL
);
CREATE INDEX idx_idempotency_expires ON kailash_idempotency (expires_at);
```

**Operations**:
- `check(key, fingerprint)` -- SELECT with expiry check
- `store(key, fingerprint, response, ttl)` -- INSERT ON CONFLICT DO NOTHING (atomic)
- `cleanup()` -- DELETE WHERE expires_at < NOW()

**Effort**: 1-2 days

### 2.8 Auto-Detection Wiring

Add a `StoreFactory` or extend existing store constructors to auto-detect the backend:

```python
import os

def resolve_backend():
    """Determine storage backend from DATABASE_URL."""
    url = os.environ.get("DATABASE_URL", "")
    if url.startswith("postgresql://") or url.startswith("postgres://"):
        return "postgresql"
    return "sqlite"  # default
```

Each store's constructor should accept an optional `backend` parameter. When not provided, use `resolve_backend()`. This enables Level 0 (no env var = SQLite) and Level 1 (DATABASE_URL = PG) with zero code changes.

**Effort**: 1 day (wiring across all stores)

---

## 3. Distributed Task Queue Recommendation

### 3.1 Library Comparison

| Criterion | Custom (current) | Celery | Dramatiq | ARQ | PG SKIP LOCKED |
|-----------|-----------------|--------|----------|-----|----------------|
| **Broker** | Redis only | Redis, RabbitMQ, SQS | Redis, RabbitMQ | Redis only | PostgreSQL |
| **Dependencies** | redis | celery, kombu, billiard, vine | dramatiq | arq | psycopg3 (already have) |
| **Async native** | Partial (run_in_executor) | No (uses prefork/gevent) | No (threads) | Yes (native asyncio) | Yes (with async driver) |
| **Maturity** | v0.13.0 | 15+ years, industry standard | 7+ years | 5+ years | Pattern, not library |
| **Learning curve** | Zero (already written) | High (complex config) | Low | Low | Low |
| **Monitoring** | Manual (heartbeat, Redis keys) | Flower dashboard | Built-in | Minimal | SQL queries |
| **Workflow serialization** | JSON (incomplete) | pickle/JSON | pickle/JSON | JSON | JSON |
| **Reliability** | BRPOPLPUSH, dead-letter, heartbeat | Mature ack/nack, result backend | Middleware pipeline | Reliable delivery | SKIP LOCKED (battle-tested PG pattern) |

### 3.2 Recommendation: Two-Track Approach

**Track A (immediate)**: Fix the existing custom Redis implementation.
- Implement `Worker._execute_workflow_sync()` with proper workflow deserialization
- The infrastructure is already there (TaskQueue, Worker, DistributedRuntime, heartbeat, dead-letter)
- This unblocks Level 2 for Redis users immediately
- **Effort**: 2-3 days

**Track B (Level 1 users)**: Add PostgreSQL-backed task queue using `SELECT ... FOR UPDATE SKIP LOCKED`.
- No new dependencies (uses existing psycopg3 / asyncpg)
- Users who already have PostgreSQL (Level 1) get multi-worker without adding Redis
- Pattern is well-documented and used by Django-Postgres, Procrastinate, and PGMQ

```sql
-- Task queue table
CREATE TABLE IF NOT EXISTS kailash_task_queue (
    task_id          TEXT PRIMARY KEY,
    queue_name       TEXT NOT NULL DEFAULT 'default',
    workflow_data    JSONB NOT NULL,
    parameters       JSONB DEFAULT '{}',
    status           TEXT NOT NULL DEFAULT 'pending',
    priority         INTEGER DEFAULT 0,
    visibility_timeout INTEGER DEFAULT 300,
    attempts         INTEGER DEFAULT 0,
    max_attempts     INTEGER DEFAULT 3,
    scheduled_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at       TIMESTAMPTZ,
    completed_at     TIMESTAMPTZ,
    worker_id        TEXT,
    result           JSONB,
    error            TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_taskq_dequeue ON kailash_task_queue (queue_name, status, scheduled_at, priority)
    WHERE status = 'pending';
CREATE INDEX idx_taskq_worker ON kailash_task_queue (worker_id, status)
    WHERE status = 'processing';
```

Dequeue query (atomic, skip-locked):
```sql
UPDATE kailash_task_queue
SET status = 'processing', started_at = NOW(), worker_id = $1, attempts = attempts + 1
WHERE task_id = (
    SELECT task_id FROM kailash_task_queue
    WHERE queue_name = $2 AND status = 'pending' AND scheduled_at <= NOW()
    ORDER BY priority DESC, scheduled_at ASC
    LIMIT 1
    FOR UPDATE SKIP LOCKED
)
RETURNING *;
```

**Effort**: 3-5 days

**Track C (optional, future)**: Celery/Dramatiq adapter for enterprises that already use those systems.
- Provide a `CeleryRuntime` or `DramatiqRuntime` that wraps the existing `DistributedRuntime` interface
- Not a priority -- the custom + PG queue covers 90% of use cases
- **Effort**: 3-5 days per adapter (deferred)

### 3.3 Why NOT Celery/Dramatiq as Primary

1. **Dependency weight**: Celery pulls in kombu, billiard, vine, amqp -- heavy for a library that ships with 4 mandatory deps
2. **Configuration complexity**: Celery's settings surface area is enormous; contradicts the "single env var" philosophy
3. **Async mismatch**: Both Celery and Dramatiq use process/thread-based concurrency, not asyncio. The kailash runtime is async-native
4. **Vendor lock-in**: Making Celery the primary task backend would tie kailash to Celery's release cycle and deprecation policy
5. **Existing code**: The current Redis implementation already handles reliable delivery, dead-letter, heartbeat -- finishing it is less work than integrating Celery

---

## 4. Idempotency Pattern for Python

### 4.1 Architecture

Three layers of dedup:

```
Layer 1: HTTP Deduplication (existing RequestDeduplicator)
         Catches duplicate HTTP requests at the gateway

Layer 2: Execution Deduplication (new)
         Prevents duplicate workflow executions across workers
         Uses PostgreSQL idempotency table with atomic INSERT

Layer 3: Node-Level Idempotency (optional, future)
         Individual nodes can declare idempotency requirements
         Useful for payment processing, external API calls
```

### 4.2 Execution-Level Idempotency

```python
class IdempotentExecutor:
    """Wraps workflow execution with idempotency guarantees.

    Before executing a workflow, checks if the idempotency key has
    already been used. If so, returns the cached result. If not,
    executes the workflow and stores the result atomically.

    Uses INSERT ... ON CONFLICT DO NOTHING for atomic dedup:
    - Two workers racing with the same key: only one INSERT succeeds
    - The loser retries the SELECT and gets the winner's result
    """

    async def execute(self, workflow, parameters, idempotency_key):
        # 1. Try to claim the key (atomic)
        claimed = await self.store.try_claim(idempotency_key, fingerprint)
        if not claimed:
            # Key already used -- return cached result
            return await self.store.get_result(idempotency_key)

        try:
            # 2. Execute the workflow
            result = await self.runtime.execute(workflow, parameters)
            # 3. Store the result
            await self.store.store_result(idempotency_key, result)
            return result
        except Exception:
            # 4. Release the claim on failure (allow retry)
            await self.store.release_claim(idempotency_key)
            raise
```

### 4.3 Persistent Deduplicator Backend

Wire the existing `RequestDeduplicator.storage_backend` to a PostgreSQL implementation:

```python
class PostgresDeduplicatorBackend:
    """Persistent backend for RequestDeduplicator.

    Implements the get()/set() protocol expected by
    RequestDeduplicator._check_storage() and _store_response().
    """

    async def get(self, key: str) -> Optional[dict]:
        """Retrieve cached response by fingerprint key."""
        ...

    async def set(self, key: str, data: dict, ttl: int) -> None:
        """Store response with TTL."""
        ...
```

### 4.4 Integration Points

- `DurableRequest.metadata.idempotency_key` already carries the key through the request lifecycle
- `RequestDeduplicator` already has the `storage_backend` hook
- The `DurableGateway` should wire these together: check dedup before creating DurableRequest, store result after completion

**Effort**: 2-3 days (execution-level idempotency + persistent dedup backend + gateway wiring)

---

## 5. Effort Summary

| Feature | Effort | Priority | Dependencies |
|---------|--------|----------|-------------|
| **PostgresEventStoreBackend** | 2-3 days | P1 | psycopg3 |
| **PostgresCheckpointStorage** | 1-2 days | P1 | psycopg3 |
| **PostgresDLQ** | 1-2 days | P1 | psycopg3 |
| **Complete DatabaseStateStorage** | 0.5 days | P1 | asyncpg (existing) |
| **PostgresExecutionStore** | 2-3 days | P1 | psycopg3 |
| **PostgresIdempotencyStore** | 1-2 days | P1 | psycopg3 |
| **Auto-detection wiring** | 1 day | P1 | None |
| **Fix Worker deserialization** | 2-3 days | P2 | redis (existing) |
| **PG-backed task queue (SKIP LOCKED)** | 3-5 days | P2 | psycopg3 |
| **Execution-level idempotency** | 2-3 days | P2 | PG idempotency store |
| **Persistent dedup backend** | 1 day | P2 | PG store |
| **Gateway integration** | 1 day | P2 | All above |
| **Integration tests (real PG)** | 3-5 days | P1 | docker-compose PG |
| **Integration tests (real Redis)** | 1-2 days | P2 | docker-compose Redis |
| | | | |
| **Total P1 (PG stores)** | **12-18 days** | | |
| **Total P2 (queue + idempotency)** | **10-15 days** | | |
| **Grand total** | **22-33 days** | | |

---

## 6. Implementation Order

### Phase 1: PostgreSQL Stores (Level 1 enablement) -- 12-18 days

1. **PostgresEventStoreBackend** -- Highest value; event store is the audit trail foundation
2. **PostgresCheckpointStorage** -- Required for durable execution across restarts
3. **PostgresDLQ** -- Mechanical port from SQLite pattern
4. **Complete DatabaseStateStorage** -- Trivial fix, unblocks saga users on PG
5. **PostgresExecutionStore** -- New store, enables execution queries across restarts
6. **PostgresIdempotencyStore** -- Foundation for exactly-once execution
7. **Auto-detection wiring** -- Ties it all together with `DATABASE_URL`
8. **Integration tests** -- Real PostgreSQL via docker-compose

### Phase 2: Task Queue + Idempotency (Level 2 enablement) -- 10-15 days

9. **Fix Worker._execute_workflow_sync()** -- Unblocks existing Redis users immediately
10. **PG-backed task queue** -- Enables multi-worker for PG-only users (no Redis required)
11. **Execution-level idempotency** -- Exactly-once via `IdempotentExecutor`
12. **Persistent dedup backend** -- Wire `RequestDeduplicator` to PG
13. **Gateway integration** -- End-to-end: dedup -> execute -> store result
14. **Integration tests** -- Real Redis + real PG task queue

---

## 7. Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| psycopg3 vs asyncpg split creates maintenance burden | Medium | Medium | Standardize on psycopg3 for new stores (supports async mode); use asyncpg only where DataFlow requires it |
| PG SKIP LOCKED queue performs poorly under high contention | Low | High | Benchmark at 100+ workers; fall back to Redis if needed; PG advisory locks as alternative |
| Auto-detection from DATABASE_URL conflicts with DataFlow's own DB detection | Medium | Medium | Use separate env var (KAILASH_STORE_URL) or namespace (DATABASE_URL for DataFlow, KAILASH_DATABASE_URL for stores) |
| Schema migrations across versions | Medium | High | Follow trust-plane pattern: meta table with version, sequential migration functions |
| Idempotency key collision (SHA-256 fingerprint) | Very Low | High | Use full idempotency key as primary key, not hash; fingerprint only for dedup without explicit key |

---

## 8. Testing Strategy

All new PostgreSQL stores must be tested against real PostgreSQL (no mocking, per project rules).

**docker-compose for tests**:
```yaml
services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: kailash_test
      POSTGRES_USER: kailash
      POSTGRES_PASSWORD: test
    ports:
      - "5432:5432"
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
```

**Test tiers**:
- **Tier 1 (unit)**: Interface compliance, serialization, error handling -- can use SQLite or mocks
- **Tier 2 (integration)**: Real PostgreSQL, real Redis -- `pytest -m integration`
- **Tier 3 (e2e)**: Full Level 1 and Level 2 scenarios with multiple workers -- `pytest -m e2e`

**Existing patterns to follow**:
- `packages/trust-plane/tests/e2e/store/test_postgres_store.py` -- real PG tests for trust-plane
- `packages/kailash-dataflow/tests/integration/core_engine/test_sync_ddl_postgresql.py` -- real PG tests for DataFlow

---

## Appendix A: File Inventory

### Existing files to modify

| File | Change |
|------|--------|
| `src/kailash/runtime/distributed.py` | Implement `Worker._execute_workflow_sync()` |
| `src/kailash/nodes/transaction/saga_state_storage.py` | Complete `DatabaseStateStorage._ensure_table_exists()` |
| `src/kailash/middleware/gateway/deduplicator.py` | Wire persistent storage backend |
| `src/kailash/middleware/gateway/durable_gateway.py` | Integrate idempotency with dedup |
| `src/kailash/runtime/base.py` | Add execution store integration |

### New files to create

| File | Purpose |
|------|---------|
| `src/kailash/middleware/gateway/event_store_postgres.py` | PG EventStore backend |
| `src/kailash/middleware/gateway/checkpoint_postgres.py` | PG CheckpointManager backend |
| `src/kailash/middleware/gateway/deduplicator_postgres.py` | PG dedup backend |
| `src/kailash/workflow/dlq_postgres.py` | PG DLQ (or adapt existing) |
| `src/kailash/runtime/execution_store.py` | Execution store protocol + PG impl |
| `src/kailash/runtime/idempotency.py` | IdempotentExecutor |
| `src/kailash/runtime/task_queue_postgres.py` | PG SKIP LOCKED task queue |
| `src/kailash/runtime/store_factory.py` | Auto-detection / factory |
| `tests/integration/stores/test_postgres_event_store.py` | Integration tests |
| `tests/integration/stores/test_postgres_checkpoint.py` | Integration tests |
| `tests/integration/stores/test_postgres_dlq.py` | Integration tests |
| `tests/integration/stores/test_postgres_execution.py` | Integration tests |
| `tests/integration/stores/test_postgres_idempotency.py` | Integration tests |
| `tests/integration/runtime/test_pg_task_queue.py` | Integration tests |
| `tests/integration/runtime/test_worker_deserialization.py` | Integration tests |

### Existing PostgreSQL references (patterns to follow)

| File | Pattern |
|------|---------|
| `packages/trust-plane/src/trustplane/store/postgres.py` | psycopg3, pool, JSONB, schema versioning, migrations |
| `packages/kailash-kaizen/src/kaizen/trust/store.py` | DataFlow-backed async PG store |
| `packages/kailash-kaizen/src/kaizen/governance/storage.py` | DataFlow-backed CRUD |
| `packages/kailash-dataflow/src/dataflow/adapters/postgresql.py` | asyncpg adapter with pool reset |
| `src/kailash/workflow/dlq.py` | SQLite DLQ (port target) |
| `src/kailash/middleware/gateway/event_store_sqlite.py` | SQLite EventStore (port target) |

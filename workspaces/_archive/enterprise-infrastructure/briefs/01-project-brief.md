# Enterprise Infrastructure Brief: kailash-py

> This workspace was created by the kailash-rs team for the kailash-py dev team to action.

**Date**: 2026-03-17
**Scope**: Progressive infrastructure -- zero to enterprise, no replatforming
**Depends on**: v0.13.0 production readiness (shipped), v1.0.0 stable API (shipped)

---

## Vision

A kailash-py user should be able to start with `pip install kailash` and a SQLite database, then scale to a multi-worker PostgreSQL-backed deployment by changing environment variables -- never rewriting application code, never replatforming.

This is the **progressive infrastructure** model:

```
Level 0  pip install kailash
         In-process, SQLite, single worker
         Zero configuration required

Level 1  DATABASE_URL=postgresql://...
         Shared state across restarts
         All stores persist to PostgreSQL

Level 2  TASK_QUEUE=redis://...  (or TASK_QUEUE=postgresql://...)
         Multi-worker via Redis/PG-backed queue
         Celery, Dramatiq, or built-in task queue

Level 3  KAILASH_CLUSTER=true
         Coordinated workers, leader election
         Distributed locks, global ordering
```

Each level is additive. Level 0 code runs unchanged at Level 3.

---

## What v0.13.0 / v1.0.0 Already Delivered

The production-readiness workspace (v0.13.0) closed most of the critical MUST-FIX gaps. The following are **shipped and working**:

| ID | Feature | Status |
|----|---------|--------|
| M1/M2 | Real saga execution via NodeExecutor (no more simulated results) | Shipped |
| M3 | Real 2PC participant transport (LocalNodeTransport + HttpTransport) | Shipped |
| M4/M5 | Workflow checkpoint state capture/restore via ExecutionTracker | Shipped |
| M6 | DurableRequest._create_workflow with schema validation | Shipped |
| M7 | Prometheus /metrics endpoint on all server classes | Shipped |
| S1 | SQLite EventStore backend with WAL mode | Shipped |
| S2 | Workflow signals and queries (SignalChannel + QueryRegistry) | Shipped |
| S3 | Built-in workflow scheduler via APScheduler | Shipped |
| S4 | Persistent dead letter queue with exponential backoff (SQLite) | Shipped |
| S5 | Distributed circuit breaker via Redis with Lua atomic transitions | Shipped |
| S6 | OpenTelemetry tracing with graceful degradation | Shipped |
| S7 | Coordinated graceful shutdown via ShutdownCoordinator | Shipped |
| S8 | Workflow versioning with semver registry | Shipped |
| S9 | Multi-worker task queue architecture (Redis-backed) | Shipped |
| N1-N7 | Continue-as-new, live dashboard, K8s manifests, quotas, pause/resume | Shipped |

**What this means**: The SDK has durability primitives, a distributed runtime with Redis-backed task queue, checkpointing, and event sourcing. But everything above Level 0 assumes Redis for task distribution and SQLite for local persistence. There is no PostgreSQL path for the core runtime stores.

---

## Three Gaps to Close

### Gap 1: PostgreSQL-Backed Persistence for Core Runtime Stores

**Current state**:

| Store | SQLite Backend | PostgreSQL Backend | Notes |
|-------|---------------|-------------------|-------|
| EventStore | `SqliteEventStoreBackend` (shipped v0.13.0) | None | Append-only event log with projections |
| CheckpointManager | `DiskStorage` (file-backed) | None | Tiered: memory -> disk -> cloud |
| DLQ (PersistentDLQ) | `PersistentDLQ` (SQLite, shipped v0.13.0) | None | Exponential backoff retry |
| SagaStateStorage | `InMemoryStateStorage` | `DatabaseStateStorage` (asyncpg, exists) | Factory pattern, `_ensure_table_exists` is a no-op |
| SagaStateStorage | -- | `RedisStateStorage` (exists) | Fully implemented with TTL |
| Trust-plane store | `SqliteTrustPlaneStore` | `PostgresTrustPlaneStore` (exists, psycopg3) | Fully implemented, schema versioning, migrations |
| Kaizen TrustStore | `InMemoryTrustStore` | `PostgresTrustStore` (exists, DataFlow-backed) | Uses DataFlow for auto-generated nodes |
| Kaizen GovernanceStorage | -- | `ExternalAgentApprovalStorage` (exists, DataFlow) | Full CRUD via DataFlow |
| Kaizen MemoryStorage | `SQLiteStorage` | None | `PersistenceBackend` protocol exists |
| Execution store | In-memory (`_execution_metadata` dict) | None | BaseRuntime stores metadata in a dict |
| Search attributes | SQLite (shipped v0.13.0) | None | Typed EAV table |

**What exists**: trust-plane has a production-quality `PostgresTrustPlaneStore` using psycopg3 with connection pooling, JSONB columns, schema versioning, and indexed queries. Kaizen has a DataFlow-backed `PostgresTrustStore` using asyncpg. The saga `DatabaseStateStorage` exists but its table creation is stubbed.

**What's missing**: PostgreSQL backends for EventStore, CheckpointManager, DLQ, ExecutionStore, MemoryStorage, and SearchAttributes. The existing `DatabaseStateStorage` needs its schema initialization completed.

**Design principle**: Follow the trust-plane pattern (psycopg3, JSONB, schema versioning) for synchronous stores, and the DataFlow pattern (asyncpg, generated nodes) for async stores. All stores must auto-detect the backend from `DATABASE_URL` -- if it starts with `postgresql://`, use the PG backend; otherwise fall back to SQLite.

### Gap 2: Distributed Task Queue

**Current state**: The `DistributedRuntime` in `src/kailash/runtime/distributed.py` implements a Redis-backed task queue with:
- `TaskQueue` using BRPOPLPUSH for reliable delivery
- `Worker` with configurable concurrency, heartbeat monitoring, dead worker detection
- `DistributedRuntime` extending `BaseRuntime` to enqueue instead of execute locally

**Critical limitation**: `Worker._execute_workflow_sync()` raises `NotImplementedError` -- workflow deserialization is not implemented. The worker can dequeue tasks but cannot execute them. Additionally, the entire distributed system is Redis-only.

**Options for Python**:

| Library | Broker | Maturity | Fit |
|---------|--------|----------|-----|
| **Celery** | Redis, RabbitMQ, SQS | Battle-tested (15+ years) | Heavy, complex config, but de facto standard |
| **Dramatiq** | Redis, RabbitMQ | Mature (7+ years) | Lighter than Celery, modern API, good defaults |
| **ARQ** | Redis only | Moderate (5+ years) | Async-native, lightweight, minimal |
| **Custom (current)** | Redis | v0.13.0 | Already implemented, needs deserialization fix |
| **PG-backed (pgqueue/SKIP LOCKED)** | PostgreSQL | Emerging | Zero new deps, uses existing DB connection |

**Recommendation**: Fix the existing custom Redis-based implementation first (it already has reliable delivery, dead-letter, heartbeat). Add PostgreSQL-backed queue as a second option using `SELECT ... FOR UPDATE SKIP LOCKED` pattern -- this lets Level 1 users (PostgreSQL but no Redis) distribute work without adding Redis. Reserve Celery/Dramatiq integration for users who already have those in their stack.

### Gap 3: Exactly-Once Execution with Idempotency Keys

**Current state**: The `RequestDeduplicator` in `src/kailash/middleware/gateway/deduplicator.py` provides:
- Request fingerprinting (SHA-256 of method + path + query + body)
- Idempotency key support (validates same key = same request)
- LRU in-memory cache with TTL (1 hour default, 10K max)
- Optional persistent storage backend (protocol defined, no implementation shipped)

**What's missing**:
1. **No persistent deduplication store** -- idempotency keys are lost on restart
2. **No database-level idempotency** -- even with deduplication, two workers could process the same request concurrently
3. **No execution-level exactly-once** -- the deduplicator operates at the HTTP layer, not the workflow execution layer

**Required**:
- PostgreSQL-backed idempotency store with `INSERT ... ON CONFLICT` for atomic dedup
- Workflow execution wrapper that checks `idempotency_key` before executing and stores the result atomically
- TTL-based cleanup of old idempotency records

---

## Progressive Configuration Model

```python
# Level 0: Zero config (default)
from kailash.runtime import LocalRuntime
runtime = LocalRuntime()  # SQLite stores, in-process

# Level 1: Add DATABASE_URL (auto-detected)
# Set DATABASE_URL=postgresql://user:pass@localhost/kailash
runtime = LocalRuntime()  # Auto-detects PG, uses PG stores

# Level 2: Add TASK_QUEUE
# Set TASK_QUEUE=redis://localhost:6379/0
# OR TASK_QUEUE=postgresql://user:pass@localhost/kailash
from kailash.runtime import DistributedRuntime
runtime = DistributedRuntime()  # Auto-detects queue backend

# Level 3: Add KAILASH_CLUSTER=true
# Enables leader election, distributed locks, global ordering
runtime = DistributedRuntime()  # Cluster-aware coordination
```

The user's workflow code (`WorkflowBuilder`, `add_node`, `connect`, `build`, `execute`) is identical at all levels.

---

## Success Criteria

1. **Level 0 unchanged**: `pip install kailash && python my_workflow.py` works with zero env vars
2. **Level 1 single env var**: Adding `DATABASE_URL=postgresql://...` switches all stores to PG without code changes
3. **Level 2 single env var**: Adding `TASK_QUEUE=redis://...` enables multi-worker without code changes
4. **No new mandatory dependencies**: PostgreSQL support via existing `asyncpg` optional dep; Redis via existing `redis` optional dep
5. **Existing tests pass**: All 1,000+ tests continue to pass at Level 0
6. **Integration tests at each level**: Real PostgreSQL tests at Level 1, real Redis tests at Level 2

---

## Related Files

Core durability (shipped v0.13.0):
- `src/kailash/middleware/gateway/durable_request.py` -- DurableRequest with checkpointing
- `src/kailash/middleware/gateway/event_store.py` -- EventStore with projections
- `src/kailash/middleware/gateway/event_store_sqlite.py` -- SQLite backend
- `src/kailash/middleware/gateway/checkpoint_manager.py` -- Tiered storage
- `src/kailash/middleware/gateway/deduplicator.py` -- Request deduplication
- `src/kailash/workflow/dlq.py` -- Persistent DLQ (SQLite)
- `src/kailash/runtime/distributed.py` -- Redis-backed task queue + worker

Existing PostgreSQL patterns to follow:
- `packages/trust-plane/src/trustplane/store/postgres.py` -- Best reference (psycopg3, pooling, JSONB, migrations)
- `packages/kailash-kaizen/src/kaizen/trust/store.py` -- DataFlow-backed PG store
- `packages/kailash-kaizen/src/kaizen/governance/storage.py` -- DataFlow-backed approval storage
- `packages/kailash-dataflow/src/dataflow/adapters/postgresql.py` -- asyncpg adapter

Saga storage (already has PG support):
- `src/kailash/nodes/transaction/saga_state_storage.py` -- DatabaseStateStorage (asyncpg, needs table init)

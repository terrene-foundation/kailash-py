# DataFlow Reuse Analysis

## What Fabric Can Reuse from DataFlow

DataFlow (250 files, 139K LOC) provides several subsystems that the fabric engine can import directly rather than reimplementing.

### 1. Caching Infrastructure (HIGH reuse)

**DataFlow cache subsystem**: 7 files in `dataflow/cache/`

- `memory_cache.py` — LRU cache with TTL, asyncio-safe, thread-safe
- `redis_manager.py` — Async Redis adapter with pub/sub support
- `auto_detection.py` — Automatically selects Redis or in-memory
- `key_generator.py` — Deterministic cache key generation
- `invalidation.py` — Model-aware cache invalidation on writes

**Fabric usage**: Import DataFlow's cache layer directly. Fabric adds:

- Product-level cache keys (not just model-level)
- Atomic swap semantics (DataFlow writes directly; fabric swaps on pipeline success)
- Content hash comparison before write

**Effort saved**: ~1,500 LOC of caching infrastructure.

### 2. Database Adapters (HIGH reuse)

**DataFlow adapters**: PostgreSQL, MySQL, SQLite, MongoDB

- Connection pooling
- Dialect-specific SQL
- Feature detection
- Type mapping
- Transaction support

**Fabric usage**: `DbSource` wraps DataFlow adapters. Source registration creates a DataFlow instance internally. Express API available for CRUD operations.

**Effort saved**: ~3,000 LOC of database connectivity.

### 3. Express API (MEDIUM reuse)

**DataFlow Express**: Direct node invocation for CRUD (23x faster than workflows)

- `create()`, `read()`, `list()`, `update()`, `delete()`, `upsert()`, `count()`
- Sync and async variants
- Built-in caching

**Fabric usage**: When a fabric product queries a database source, it uses Express API internally.

### 4. Connection Pool Management (MEDIUM reuse)

**DataFlow pool utils**: `pool_utils.py`, `pool_validator.py`, `pool_monitor.py`

- Auto-sizing based on `max_connections`
- Startup validation
- Utilization monitoring

**Fabric usage**: Database sources inherit DataFlow's pool management.

### 5. Multi-Tenancy (LOW reuse for now)

**DataFlow multi-tenant**: `multi_tenant.py`

- Tenant-aware query routing
- Data isolation

**Fabric usage**: Future consideration. Fabric products could be tenant-scoped.

---

## What Fabric CANNOT Reuse from DataFlow

### 1. Source Adapters for Non-Database Sources

DataFlow has no REST API, file system, Excel, cloud storage, or streaming adapters. These are net-new for the fabric engine.

### 2. Pipeline Orchestration

DataFlow's pipeline is "model → node → workflow → runtime." Fabric needs "source → fetch → transform → cache." Different abstraction.

### 3. Data Product Concept

DataFlow has models (database tables) and nodes (operations). Fabric needs products (materialized views over heterogeneous sources).

### 4. Pre-Warming

DataFlow caches lazily (on first query). Fabric needs eager pre-warming on startup.

### 5. Content Hash Comparison

DataFlow's cache uses TTL. Fabric needs content hash comparison to determine if data actually changed.

### 6. Circuit Breaker / Backpressure

DataFlow doesn't have these — they're needed for unreliable external sources (APIs, cloud storage).

---

## Dependency Relationship

```
kailash-fabric imports from:
├── dataflow.cache.memory_cache      → InMemoryCache
├── dataflow.cache.redis_manager     → RedisManager
├── dataflow.cache.auto_detection    → detect_cache_backend
├── dataflow.cache.key_generator     → generate_cache_key
├── dataflow.features.express        → ExpressAPI (for DB sources)
├── dataflow.core.engine             → DataFlow (for DB source initialization)
└── dataflow.adapters.*              → Database adapters (via DataFlow)

kailash-fabric imports from kailash-nexus:
├── nexus.core                       → Nexus (for endpoint serving)
└── nexus.handlers                   → handler registration

kailash-fabric implements NEW:
├── fabric.sources.rest              → REST API adapter
├── fabric.sources.file              → File system adapter
├── fabric.sources.excel             → Excel/CSV adapter
├── fabric.sources.cloud             → S3/GCS/Azure adapter
├── fabric.sources.stream            → Kafka/WebSocket/SSE adapter
├── fabric.products.*                → Data product definitions
├── fabric.pipeline.*                → Pipeline runner, backpressure, circuit breaker
├── fabric.cache.warming             → Pre-warming logic
├── fabric.cache.invalidation        → Hybrid invalidation (CDC/poll/watch)
└── fabric.serving.*                 → Auto-generated endpoints
```

## Estimated New Code

| Component                 | Files   | LOC (est.)       | Complexity           |
| ------------------------- | ------- | ---------------- | -------------------- |
| Source adapters (6 types) | 8       | 2,000-3,000      | Medium               |
| Pipeline runner           | 4       | 800-1,200        | Medium               |
| Cache management          | 3       | 500-800          | Low (wraps DataFlow) |
| Product definitions       | 3       | 400-600          | Low                  |
| Endpoint serving          | 2       | 300-500          | Low (wraps Nexus)    |
| Engine orchestrator       | 1       | 500-800          | Medium               |
| Observability             | 2       | 300-500          | Low                  |
| **Total**                 | **~23** | **~5,000-7,400** | —                    |

This is a lean package — 5-7K LOC for the core engine, leveraging ~4,500 LOC from DataFlow and Nexus.

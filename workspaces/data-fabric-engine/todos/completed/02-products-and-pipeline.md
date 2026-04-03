# Milestone 2: Products & Pipeline — The Core Engine

These todos build the product abstraction and pipeline execution.

---

## TODO-09: Build product registration decorator

**Layer**: 6 (core engine)
**File**: `packages/kailash-dataflow/src/dataflow/fabric/products.py`

Add `DataFlow.product(name, mode, depends_on, staleness, schedule, multi_tenant, auth, rate_limit, write_debounce, cache_miss)` decorator (doc 10, lines 73-118):

- Validate `depends_on` references exist in `_models` or `_sources` (required for materialized/parameterized, optional for virtual)
- Store `ProductRegistration` in `self._products`
- Auto-generate `ProductInvokeNode` wrapper for workflow composability (doc layer-redteam F2)
- Validate `schedule` is valid cron expression if provided

Parameters from convergence docs:
- `mode`: "materialized" | "parameterized" | "virtual"
- `staleness`: StalenessPolicy
- `schedule`: Optional cron string
- `multi_tenant`: bool
- `auth`: Optional dict with `roles` or `public`
- `rate_limit`: RateLimit
- `write_debounce`: timedelta (default 1s)
- `cache_miss`: "timeout" | "async_202" | "inline" (default "timeout", 2s)

**Test**: Tier 1 — registration, depends_on validation, mode validation, ProductInvokeNode generation.

---

## TODO-10: Build FabricContext and PipelineScopedExpress

**Layer**: 6-7
**File**: `packages/kailash-dataflow/src/dataflow/fabric/context.py`

Implement `FabricContext` (doc 08, lines 236-264):
- `express: DataFlowExpress` — same object as `db.express`
- `source(name) -> SourceHandle` — wraps registered source adapter
- `product(name) -> Any` — read cached result of another product
- `tenant_id: Optional[str]` — set from request context for multi-tenant products

Implement `PipelineContext(FabricContext)` (doc layer-redteam F4):
- `PipelineScopedExpress` wrapper that deduplicates reads within a single pipeline run
- Cache key: `f"{operation}:{model}:{json.dumps(filter, sort_keys=True)}"`
- Only caches reads (list, read, count), not writes

Implement `SourceHandle` (doc 08, lines 269-315 + doc 04, lines 140-147):
- Wraps a `BaseSourceAdapter` with user-friendly interface
- `fetch()`, `fetch_all()`, `fetch_pages()`, `read()`, `list()`, `write()`
- `last_successful_data()`, `name`, `source_type`, `healthy`, `last_change_detected`

Implement `FabricContext.for_testing()` (doc 08, lines 320-345):
- Accept `express_data` dict and `source_data` dict
- Return a testable context with pre-loaded data, no real connections

**Test**: Tier 1 — context creation, source handle delegation, PipelineScopedExpress dedup, for_testing().

---

## TODO-11: Build PipelineExecutor

**Layer**: 10 (FabricRuntime)
**File**: `packages/kailash-dataflow/src/dataflow/fabric/pipeline.py`

Implement `PipelineExecutor` (doc 12, lines 249-345):

- Execution semaphore: `asyncio.Semaphore(max_concurrent)` (default 3)
- DB connection budget: separate semaphore for pipeline DB access (20% of pool — doc layer-redteam F5)
- Debounce: Redis sorted set (doc 02-competitor, lines 200-242). Fallback to in-memory timers in dev mode.
- Debounce consumer: background task polling sorted set every 500ms

Pipeline execution flow:
1. Build `PipelineContext` with `PipelineScopedExpress`
2. Execute product function with context
3. Serialize result with MessagePack (doc 02-competitor, lines 58-86)
4. Check result size (max 10MB default — doc runtime-redteam RT-6)
5. Content hash (SHA-256 of msgpack bytes)
6. Compare with existing hash in Redis
7. If different: atomic write via Lua script (doc runtime-redteam RT-4)
8. Store trace in bounded deque (maxlen=20)
9. Broadcast SSE event (product_updated)

Parameterized products on cache miss (doc runtime-redteam RT-3):
- `timeout` (default): execute inline, return 504 if exceeds 2s
- `async_202`: return 202, execute in background
- `inline`: execute inline, no timeout

**Test**: Tier 2 — test with real Redis + SQLite. Pipeline execution, cache write, content hash dedup, debounce, size limit.

---

## TODO-12: Build ChangeDetector (poll loops)

**Layer**: 10 (FabricRuntime)
**File**: `packages/kailash-dataflow/src/dataflow/fabric/change_detector.py`

Implement supervised poll loops (doc 12, lines 142-186 + doc runtime-redteam RT-1):

- One supervised asyncio task per source (NOT TaskGroup)
- Each task: `detect_change()` → enqueue affected products → sleep
- Crash isolation: one poll loop crash does NOT kill siblings
- Auto-restart on failure with 5s delay
- Circuit breaker integration: if threshold exceeded, source state → "paused"
- Use `datetime.now(timezone.utc)` (not deprecated `utcnow()`)

File watchers: start watchdog observer on `FileSourceAdapter.connect()`. Bridge callback to async via `run_coroutine_threadsafe()`.

**Test**: Tier 2 — test poll loop with a real file that changes. Verify pipeline triggers on change.

---

## TODO-13: Build LeaderElector

**Layer**: 10 (FabricRuntime)
**File**: `packages/kailash-dataflow/src/dataflow/fabric/leader.py`

Implement leader election (doc 04, lines 155-181):

- Redis backend: `SETNX` with TTL (default 30s). Heartbeat every 10s renews TTL.
- PostgreSQL backend: `pg_advisory_lock` (non-blocking try).
- Auto-detect: Redis if `redis_url` configured, else PostgreSQL.
- On leader death: followers detect expired TTL, compete for lock.
- All workers serve endpoints. Only leader runs background tasks (polls, pipelines, scheduler).

**Test**: Tier 2 — test with real Redis. Verify leader acquisition, heartbeat renewal, failover on leader death.

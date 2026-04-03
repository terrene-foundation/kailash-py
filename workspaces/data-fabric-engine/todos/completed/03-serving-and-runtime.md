# Milestone 3: Serving & Runtime — What Users See

These todos build the serving layer and the fabric runtime lifecycle.

---

## TODO-14: Build FabricServingLayer (endpoint auto-generation)

**Layer**: 9-10
**File**: `packages/kailash-dataflow/src/dataflow/fabric/serving.py`

Auto-generate REST endpoints from registered products (doc 12, lines 349-484):

For each product, register:
- `GET /fabric/{product_name}` — serve cached data

Response headers (doc 04, lines 12-49 — AUTHORITATIVE, not body envelope):
- `X-Fabric-Freshness`: fresh | stale | cold
- `X-Fabric-Age`: seconds since cached
- `X-Fabric-Cached-At`: ISO timestamp
- `X-Fabric-Pipeline-Ms`: pipeline duration
- `X-Fabric-Mode`: materialized | parameterized | virtual
- `X-Fabric-Consistency`: eventual (for multi-source products)

Response body: **clean JSON** — exactly what the product function returned. No envelope.

Cold product: 202 Accepted with `Retry-After: 5` header.
Stale product: 200 with `X-Fabric-Freshness: stale`.

Parameterized products: parse query parameters, coerce types from function signature, build cache key from canonical serialized params.

Auth (doc 04, lines 55-81): inherit Nexus middleware. Per-product `auth.roles` check.
Rate limiting (doc 04, lines 87-105): per-product, per-client. Cardinality limit for parameterized.

**Test**: Tier 2 — test endpoint registration with real Nexus instance. Verify headers, response shapes, auth enforcement, rate limiting.

---

## TODO-15: Build write pass-through endpoints

**Layer**: 9-10
**File**: `packages/kailash-dataflow/src/dataflow/fabric/serving.py` (extend)

For each writable source/model (when `enable_writes=True`):
- `POST /fabric/{target}/write` — write pass-through (doc 04, lines 289-290: POST-only with operation in body)

Write flow:
1. Validate request (`operation`, `data` fields)
2. Route to correct adapter: model name → Express API, source name → source adapter
3. Execute write
4. On success: enqueue debounced pipeline refresh for all products with target in `depends_on`
5. Return write result with headers: `X-Fabric-Write-Target`, `X-Fabric-Products-Refreshing`

Write rate limiting: default 100/min per client (doc 01-redteam B4).

**Test**: Tier 2 — test write to real SQLite model, verify product refresh triggers, verify rate limiting.

---

## TODO-16: Build webhook receiver

**Layer**: 10
**File**: `packages/kailash-dataflow/src/dataflow/fabric/webhooks.py`

Implement webhook endpoints for push-based sources (doc 09, lines 132-149):

- Register `POST /webhooks/{source_name}` for sources with `WebhookConfig`
- HMAC signature validation using `hmac.compare_digest()` (constant-time)
- Timestamp validation: reject payloads older than 5 minutes (doc 01-redteam H1)
- Nonce tracking: reject duplicate delivery IDs
- On all workers (not just leader): write webhook event to Redis list, leader consumes (doc runtime-redteam RT-2)

**Test**: Tier 2 — test with real HTTP requests. Verify signature validation, timestamp rejection, nonce dedup, pipeline trigger.

---

## TODO-17: Build FabricRuntime orchestrator

**Layer**: 10
**File**: `packages/kailash-dataflow/src/dataflow/fabric/runtime.py`

Implement `FabricRuntime` — the main orchestrator started by `db.start()` (doc 12):

Startup sequence (doc 10, lines 128-165):
1. `await dataflow.initialize()` — ensure DB connected
2. Connect all registered sources (parallel). Fail-fast or skip-and-warn.
3. Elect leader
4. Pre-warm all materialized products (leader only, unless `dev_mode`)
5. Start change detection poll loops (leader only)
6. Register fabric endpoints (all workers)

Supervised task management (doc runtime-redteam RT-1):
- List of `asyncio.Task`, not TaskGroup
- `_supervised()` wrapper: restart on crash, 5s delay, log exception
- Bounded pipeline queue: `asyncio.Queue(maxsize=100)`, coalesce on full

`db.start()` method on DataFlow (doc 10, lines 125-165):
- Parameters: `fail_fast`, `dev_mode`, `nexus`, `coordination`, `host` (default 127.0.0.1), `port`, `enable_writes`, `tenant_extractor`
- Option A (zero-config): creates internal Nexus, binds localhost
- Option B (production): attaches to existing Nexus with auth middleware

`db.stop()` shutdown (doc 04, lines 297-312):
1. Stop accepting webhook deliveries
2. Wait for in-flight pipelines (timeout 30s)
3. Cancel all supervised tasks
4. Release leader lock
5. Disconnect sources
6. Flush metrics

**Test**: Tier 2 — test full lifecycle: start with real sources, verify pre-warming, verify shutdown.

---

## TODO-18: Wire DataFlow event bus for write notifications

**Layer**: 6
**File**: `packages/kailash-dataflow/src/dataflow/fabric/runtime.py` (extend)

Subscribe to DataFlow's existing `DataFlowEventMixin` event bus (doc runtime-redteam RT-8):

```python
self._dataflow.on("model.created", self._on_model_write)
self._dataflow.on("model.updated", self._on_model_write)
self._dataflow.on("model.deleted", self._on_model_write)
self._dataflow.on("model.bulk_created", self._on_model_write)
self._dataflow.on("model.bulk_deleted", self._on_model_write)
```

When a model write event fires, identify all products with that model in `depends_on` and enqueue debounced pipeline refresh.

No Express refactoring needed — hook into existing event system.

**Test**: Tier 2 — test with real Express write → verify event fires → verify product refresh enqueued.

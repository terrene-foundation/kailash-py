# Milestone 4: Observability — Health, Metrics, Traces, SSE

---

## TODO-19: Build health endpoint

**Layer**: 10
**File**: `packages/kailash-dataflow/src/dataflow/fabric/health.py`

Implement `GET /fabric/_health` (doc 09, lines 662-714):

Response shape:
- `status`: healthy | degraded | unhealthy
- `uptime_seconds`
- `sources`: per-source health, latency, last_success, circuit_breaker state
- `products`: per-product freshness, age, last_refresh, refresh_count
- `cache`: backend type, hit_rate, entries, memory_mb
- `pipelines`: total_runs, successful, failed, avg_duration_ms

Requires admin auth by default (doc 04, lines 78-80).

**Test**: Tier 2 — test with real sources registered. Verify response shape, admin auth enforcement.

---

## TODO-20: Build trace endpoint

**Layer**: 10
**File**: `packages/kailash-dataflow/src/dataflow/fabric/health.py` (extend)

Implement `GET /fabric/_trace/{product}` (doc 09, lines 757-814):

Response: last 20 runs (bounded deque) with:
- `run_id`, `triggered_by`, `started_at`, `duration_ms`, `status`
- Per-step: source, action, records, duration_ms, status, from_cache
- `cache_action`: swap | skip
- `content_changed`: bool

Trace stored in `PipelineExecutor._traces` (bounded `deque(maxlen=20)`).
Error messages sanitized — no connection strings, credentials, or full stack traces (doc 01-redteam C4).

**Test**: Tier 1 — test trace storage, deque bounds, error sanitization.

---

## TODO-21: Build Prometheus metrics

**Layer**: 10
**File**: `packages/kailash-dataflow/src/dataflow/fabric/metrics.py`

Implement metrics (doc 09, lines 731-752):

Source metrics:
- `fabric_source_health{source}` (gauge)
- `fabric_source_check_duration_seconds{source}` (histogram)
- `fabric_source_consecutive_failures{source}` (gauge)

Pipeline metrics:
- `fabric_pipeline_duration_seconds{product}` (histogram)
- `fabric_pipeline_runs_total{product,status}` (counter)

Cache metrics:
- `fabric_cache_hit_total{product}` (counter)
- `fabric_cache_miss_total{product}` (counter)
- `fabric_product_age_seconds{product}` (gauge)

Serving metrics:
- `fabric_request_duration_seconds{product}` (histogram)
- `fabric_request_total{product,freshness}` (counter)

Use `prometheus_client` if available, otherwise no-op metrics. Extend existing DataFlow health endpoint.

**Test**: Tier 1 — test metric registration and increment. No external Prometheus needed.

---

## TODO-22: Build structured logging

**Layer**: 10
**File**: integrated into all fabric modules

Structured log format (doc 09, lines 720-727):

```
[timestamp] [fabric.pipeline] INFO  product=dashboard trigger=source_change source=crm
[timestamp] [fabric.source]   INFO  source=crm action=fetch endpoint=deals records=142 duration_ms=230
[timestamp] [fabric.cache]    INFO  product=dashboard action=swap content_changed=true duration_ms=12
```

Use `logging.getLogger("dataflow.fabric.*")` hierarchy. Key-value structured fields. No credential leakage in log output.

**Test**: Tier 1 — verify log format, verify no credentials leak.

---

## TODO-23: Build SSE endpoint for real-time push

**Layer**: 10
**File**: `packages/kailash-dataflow/src/dataflow/fabric/sse.py`

Implement `GET /fabric/_events` (doc 02-competitor, lines 1-50):

SSE endpoint that pushes:
- `product_updated`: when pipeline completes and cache is swapped
- `source_health`: when source health changes (healthy → unhealthy or vice versa)

Event format:
```
event: product_updated
data: {"product": "dashboard", "cached_at": "2026-04-03T10:00:00Z"}
```

SSE over HTTP/2 (standard HTTP, no WebSocket). Auto-reconnection via browser `EventSource` API. Connection management: track connected clients, broadcast to all.

**Test**: Tier 2 — test with real HTTP client. Verify events pushed on cache swap.

---

## TODO-24: Build batch product read endpoint

**Layer**: 10
**File**: `packages/kailash-dataflow/src/dataflow/fabric/serving.py` (extend)

Implement `GET /fabric/_batch?products=a,b,c` (doc 02-competitor, lines 141-174):

- Single Redis `MGET` for all product data keys
- Pipeline `HGETALL` for all metadata keys
- Return combined response with aggregated freshness header
- MessagePack deserialize → JSON serialize for response

Reduces N HTTP requests + N Redis GETs to 1 HTTP request + 1 MGET.

**Test**: Tier 2 — test with multiple cached products. Verify single Redis roundtrip.

---

## TODO-25: Build programmatic fabric status API

**Layer**: 10
**File**: `packages/kailash-dataflow/src/dataflow/fabric/runtime.py` (extend)

Implement `db.fabric.status()`, `db.fabric.source_health(name)`, `db.fabric.product_info(name)`, `db.fabric.last_trace(name)` (doc 09, lines 819-823).

These are the in-process equivalents of the HTTP endpoints — used by developers in code, not by FE.

**Test**: Tier 1 — test API surface returns correct shapes.

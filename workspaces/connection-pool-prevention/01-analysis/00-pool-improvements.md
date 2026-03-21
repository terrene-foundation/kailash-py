# Connection Pool Prevention — Five Improvements

**Date**: 2026-03-20
**Status**: Analysis complete, ready for /todos

---

## PY-1: Pool Auto-Scaling

### Problem

`DatabaseConfig.get_pool_size()` computes pool size from CPU count and environment, but has no awareness of:

- PostgreSQL `max_connections` (the actual server limit)
- Worker count (Uvicorn, Gunicorn, or any ASGI/WSGI multiprocess server)
- Other clients sharing the same database server

The result is that production defaults (`min(50, cpu_count * 4)`) routinely exceed what the database can serve.

### Proposed Solution

`DataFlowConfig` should accept `max_connections="auto"` (and make `"auto"` the new default).

**Auto mode algorithm**:

```python
def _compute_auto_pool_size(self) -> int:
    """Compute pool size from server capacity and deployment topology."""
    # Step 1: Query PostgreSQL for max_connections
    # Uses a temporary connection — does not consume a pool slot
    db_max = self._query_max_connections()  # SHOW max_connections → int

    # Step 2: Detect worker count from environment
    workers = int(
        os.environ.get("UVICORN_WORKERS")
        or os.environ.get("WEB_CONCURRENCY")
        or os.environ.get("GUNICORN_WORKERS")
        or "1"
    )

    # Step 3: Compute safe pool size
    # Reserve 30% for admin/migration/monitoring connections
    available = int(db_max * 0.7)
    pool_size = max(2, available // workers)

    # Step 4: Set max_overflow to 50% of pool_size (bounded)
    max_overflow = max(2, pool_size // 2)

    return pool_size, max_overflow
```

**Fallback**: If `SHOW max_connections` fails (SQLite, permissions, network error), fall back to the current CPU-based calculation with a conservative cap of 10 per worker.

### Files to Modify

| File | Change |
|------|--------|
| `packages/kailash-dataflow/src/dataflow/core/config.py` | Add `max_connections` parameter to `DataFlowConfig.__init__()` accepting `int` or `"auto"`. Add `_compute_auto_pool_size()` method. Change default from CPU-based to `"auto"`. |
| `packages/kailash-dataflow/src/dataflow/core/config.py` | Modify `DatabaseConfig.get_pool_size()` to delegate to auto-scaling when `pool_size is None` and parent config has `max_connections="auto"`. |
| `packages/kailash-dataflow/src/dataflow/core/config.py` | Update `DataFlowConfig.from_env()` to read `DATAFLOW_MAX_CONNECTIONS` env var (accepts integer or `"auto"`). |

### Environment Variables

| Variable | Purpose | Default |
|----------|---------|---------|
| `DATAFLOW_MAX_CONNECTIONS` | Override auto-detection or set explicit limit | `"auto"` |
| `UVICORN_WORKERS` | Detected worker count (Uvicorn) | — |
| `WEB_CONCURRENCY` | Detected worker count (Heroku/generic) | — |
| `GUNICORN_WORKERS` | Detected worker count (Gunicorn) | — |

### Backward Compatibility

- Explicit `pool_size=25` in `DataFlowConfig(pool_size=25)` overrides auto-scaling (existing behavior preserved)
- Explicit `DATAFLOW_POOL_SIZE=25` env var overrides auto-scaling (existing behavior preserved)
- Only when both are unset does `"auto"` engage

---

## PY-2: Pool Utilization Monitor

### Problem

There is zero runtime visibility into pool utilization. `MonitoringConfig` defines `alert_on_connection_exhaustion` and `connection_metrics` flags, but nothing reads them. Users get no warning before exhaustion — the first signal is a `TimeoutError`.

### Proposed Solution

Add a background daemon thread that periodically checks pool utilization and emits structured log events.

**Behavior**:

| Utilization | Action |
|-------------|--------|
| < 70% | Silent (no log output) |
| 70-79% | `INFO` log every 10 seconds with pool stats |
| 80-94% | `WARNING` log every 10 seconds with pool stats |
| >= 95% | `ERROR` log every 5 seconds with pool stats and traceback of longest-held connection |

**Public API**:

```python
# On the DataFlow instance (or engine wrapper)
stats = dataflow.pool_stats()
# Returns:
# {
#     "active": 8,        # connections currently checked out
#     "idle": 12,         # connections available in pool
#     "max": 20,          # pool_size
#     "overflow": 2,      # current overflow connections
#     "max_overflow": 10, # max_overflow setting
#     "utilization": 0.4, # active / (max + max_overflow)
# }
```

**Thread lifecycle**:

- Starts when pool is created (via `DataFlow.connect()` or engine creation)
- Stops cleanly on `DataFlow.disconnect()` or `atexit`
- Daemon thread — does not prevent process exit
- Configurable interval via `DataFlowConfig(pool_monitor_interval_secs=10)`

### Files to Modify

| File | Change |
|------|--------|
| `packages/kailash-dataflow/src/dataflow/core/config.py` | Add `pool_monitor_interval_secs` parameter to `DataFlowConfig`. |
| `packages/kailash-dataflow/src/dataflow/core/pool_monitor.py` | **NEW FILE**. `PoolMonitor` class: daemon thread, log thresholds, `pool_stats()` method. |
| `packages/kailash-dataflow/src/dataflow/core/engine.py` (or equivalent) | Start `PoolMonitor` on engine creation, stop on disposal. Expose `pool_stats()`. |

### Log Format

```
[POOL] utilization=85% active=17 idle=3 max=20 overflow=0 max_overflow=10 — WARNING: approaching pool exhaustion
```

---

## PY-3: Query Cache for Single-Record Reads

### Problem

High-traffic applications repeatedly read the same records (configuration, user profiles, agent definitions). Each read consumes a pool connection for the duration of the query, even when the result has not changed. This amplifies pool pressure unnecessarily.

### Proposed Solution

Add an opt-in `functools.lru_cache`-style in-memory cache for Read node operations.

**Cache semantics**:

- Cache key: `(model_name, primary_key_value)`
- TTL: 60 seconds default, configurable via `DataFlowConfig(read_cache_ttl_secs=60)`
- Auto-invalidation: any Create, Update, or Delete node execution for the same model clears all cache entries for that model
- Max size: 1000 entries default, configurable via `DataFlowConfig(read_cache_max_size=1000)`, LRU eviction

**Opt-in activation**:

```python
# Per-node opt-in
workflow.add_node("ReadAgent", "read_agent", {"id": agent_id, "cache": True})

# Global config (caches all Read nodes)
config = DataFlowConfig(read_cache_enabled=True)
```

**What is NOT cached**:

- List/filter queries (too many permutations, invalidation is impractical)
- Any query with joins or aggregations
- Write operations (obviously)

### Files to Modify

| File | Change |
|------|--------|
| `packages/kailash-dataflow/src/dataflow/core/config.py` | Add `read_cache_enabled`, `read_cache_ttl_secs`, `read_cache_max_size` parameters to `DataFlowConfig`. |
| `packages/kailash-dataflow/src/dataflow/core/read_cache.py` | **NEW FILE**. `ReadCache` class: thread-safe LRU dict with TTL, invalidation by model name. |
| `packages/kailash-dataflow/src/dataflow/nodes/` (Read node) | Check cache before executing query. Populate cache after successful read. |
| `packages/kailash-dataflow/src/dataflow/nodes/` (Create/Update/Delete nodes) | Call `read_cache.invalidate(model_name)` after successful write. |

### Thread Safety

`ReadCache` must be thread-safe (used from multiple ASGI worker threads). Use `threading.Lock` for cache mutations. TTL checks are read-only and do not need locking.

---

## PY-4: Startup Validation

### Problem

The SDK never validates its pool configuration against the database server. A misconfigured pool silently starts, works fine under low load, and then fails catastrophically under production traffic. Users discover the problem in the worst possible moment.

### Proposed Solution

On `DataFlow.connect()`, perform a one-time validation check that compares the configured pool against PostgreSQL's `max_connections`.

**Validation logic**:

```python
def _validate_pool_config(self, engine):
    """Validate pool math against database server limits."""
    if not self._is_postgresql(engine):
        return  # Only validate for PostgreSQL

    db_max = self._query_max_connections(engine)
    workers = self._detect_worker_count()

    total_possible = (self.pool_size + self.max_overflow) * workers

    if total_possible > db_max:
        logger.error(
            "CONNECTION POOL WILL EXHAUST: "
            "pool_size=%d + max_overflow=%d x %d workers = %d connections, "
            "but PostgreSQL max_connections=%d. "
            "Remediation: Set DATAFLOW_MAX_CONNECTIONS=%d or reduce worker count.",
            self.pool_size, self.max_overflow, workers, total_possible, db_max,
            db_max // workers
        )
    elif total_possible > db_max * 0.7:
        logger.warning(
            "CONNECTION POOL NEAR LIMIT: "
            "pool_size=%d + max_overflow=%d x %d workers = %d connections "
            "(%.0f%% of PostgreSQL max_connections=%d). "
            "Consider reducing pool_size or increasing max_connections.",
            self.pool_size, self.max_overflow, workers, total_possible,
            (total_possible / db_max) * 100, db_max
        )
    else:
        logger.info(
            "Connection pool validated: %d/%d possible connections (%.0f%% of limit)",
            total_possible, db_max, (total_possible / db_max) * 100
        )
```

**Output on misconfiguration**:

```
ERROR — CONNECTION POOL WILL EXHAUST: pool_size=50 + max_overflow=100 x 4 workers = 600 connections, but PostgreSQL max_connections=100. Remediation: Set DATAFLOW_MAX_CONNECTIONS=17 or reduce worker count.
```

### Files to Modify

| File | Change |
|------|--------|
| `packages/kailash-dataflow/src/dataflow/core/config.py` | Add `startup_validation` parameter to `DataFlowConfig` (default `True`). |
| `packages/kailash-dataflow/src/dataflow/core/pool_validator.py` | **NEW FILE**. `validate_pool_config(engine, config)` function. Queries `SHOW max_connections`, detects workers, logs result. |
| `packages/kailash-dataflow/src/dataflow/core/engine.py` (or equivalent) | Call `validate_pool_config()` after engine creation during `DataFlow.connect()`. |

### Error Behavior

Validation is **advisory only** — it logs errors and warnings but does not prevent startup. This avoids breaking deployments where users intentionally overcommit (e.g., with PgBouncer in front of PostgreSQL).

Opt-out: `DataFlowConfig(startup_validation=False)` or `DATAFLOW_STARTUP_VALIDATION=false`.

---

## PY-5: Leak Detection

### Problem

Connection leaks (connections checked out but never returned) silently consume pool capacity. Common causes:

- Missing `session.close()` or context manager
- Exceptions that skip cleanup code
- Long-running queries that hold connections indefinitely
- Forgotten cursors in batch processing

The SDK provides no visibility into leaked connections. By the time the pool is exhausted, it is impossible to determine which code path leaked.

### Proposed Solution

Wrap pool checkout with timeout tracking. Log a warning with the checkout traceback when a connection is held longer than a configurable threshold.

**Behavior**:

- On pool checkout: record `(connection_id, checkout_time, traceback)`
- Background monitor (same thread as PY-2) checks held connections every cycle
- If `held_time > leak_detection_timeout_secs`: log WARNING with original checkout traceback
- If `held_time > leak_detection_timeout_secs * 3`: log ERROR (probable leak, not just slow query)

**Configuration**:

```python
config = DataFlowConfig(
    leak_detection_timeout_secs=30,   # WARNING after 30s (default)
    leak_detection_enabled=True,      # enabled by default
)
```

**Log output for a detected leak**:

```
[POOL] WARNING: Connection held for 45.2s (threshold: 30s)
  Checked out at:
    File "app/services/agent_service.py", line 142, in get_agent
      session = db.get_session()
    File "app/api/routes/agents.py", line 38, in read_agent
      agent = agent_service.get_agent(agent_id)
```

### Files to Modify

| File | Change |
|------|--------|
| `packages/kailash-dataflow/src/dataflow/core/config.py` | Add `leak_detection_enabled` (default `True`) and `leak_detection_timeout_secs` (default `30`) to `DataFlowConfig`. |
| `packages/kailash-dataflow/src/dataflow/core/pool_monitor.py` | Extend `PoolMonitor` to track checkout times and tracebacks. Add leak detection to monitoring cycle. |
| `packages/kailash-dataflow/src/dataflow/core/engine.py` (or equivalent) | Hook into SQLAlchemy pool events (`checkout`, `checkin`) to register/deregister connections with the leak detector. |

### SQLAlchemy Integration

```python
from sqlalchemy import event

@event.listens_for(engine, "checkout")
def on_checkout(dbapi_conn, connection_record, connection_proxy):
    connection_record._checkout_time = time.monotonic()
    connection_record._checkout_traceback = traceback.extract_stack()

@event.listens_for(engine, "checkin")
def on_checkin(dbapi_conn, connection_record):
    connection_record._checkout_time = None
    connection_record._checkout_traceback = None
```

---

## Summary Matrix

| ID | Improvement | Priority | Effort | New Files | Modified Files |
|----|------------|----------|--------|-----------|----------------|
| PY-1 | Pool Auto-Scaling | CRITICAL | 2-3 days | 0 | `config.py` |
| PY-2 | Pool Utilization Monitor | HIGH | 1-2 days | 1 (`pool_monitor.py`) | `config.py`, engine |
| PY-3 | Query Cache | MEDIUM | 2-3 days | 1 (`read_cache.py`) | `config.py`, Read/Write nodes |
| PY-4 | Startup Validation | HIGH | 1 day | 1 (`pool_validator.py`) | `config.py`, engine |
| PY-5 | Leak Detection | HIGH | 1-2 days | 0 (extends `pool_monitor.py`) | `config.py`, engine |
| **Total** | | | **7-11 days** | **3 new files** | |

## Recommended Order

1. **PY-4** (Startup Validation) — lowest effort, highest immediate impact. Users get clear error messages today.
2. **PY-1** (Pool Auto-Scaling) — eliminates the root cause. Makes the default correct.
3. **PY-2** (Pool Utilization Monitor) — provides ongoing visibility for production deployments.
4. **PY-5** (Leak Detection) — catches the long-tail of pool exhaustion causes.
5. **PY-3** (Query Cache) — reduces pool pressure for read-heavy workloads. Lower priority because it is a mitigation, not a prevention.

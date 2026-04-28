# Cross-SDK Alignment: kailash-py vs kailash-rs

**Date**: 2026-03-20
**Purpose**: Ensure semantic parity between Python and Rust SDK connection pool improvements
**Reference**: `kailash-rs/workspaces/connection-pool-prevention/01-analysis/00-pool-improvements.md`

---

## Feature Parity Matrix

| Feature                   | RS ID | RS Status    | PY ID | PY Status            | Parity       |
| ------------------------- | ----- | ------------ | ----- | -------------------- | ------------ |
| Pool Auto-Scaling         | RS-1  | Planned (P0) | PY-1  | Planned              | ALIGN NEEDED |
| Pool Utilization Monitor  | RS-2  | Planned (P1) | PY-2  | Planned              | ALIGN NEEDED |
| Query Cache               | RS-3  | Planned (P2) | —     | CUT (existing infra) | DIVERGENCE   |
| Startup Validation        | RS-4  | Planned (P0) | PY-4  | Planned              | ALIGN NEEDED |
| Leak Detection            | RS-5  | Planned (P1) | PY-5  | Planned              | ALIGN NEEDED |
| Lightweight Pool (Health) | RS-6  | Planned (P2) | —     | NOT PLANNED          | DIVERGENCE   |

---

## Alignment Items

### 1. Auto-Scaling API (RS-1 / PY-1)

**RS approach**: `PoolSize` enum with explicit variants:

```rust
pub enum PoolSize {
    Auto,           // Auto-detect from max_connections and workers
    Fixed(u32),     // Fixed per-worker count
    PerWorker(u32), // Explicit per-worker sizing
}
```

**PY current approach**: Implicit — `pool_size=None` means auto, `pool_size=25` means fixed. No enum.

**Alignment decision**: PY should NOT add a `PoolSize` enum. Python idiom is `Optional[int]`:

- `pool_size=None` (default) → auto-scaling (equivalent to `PoolSize::Auto`)
- `pool_size=25` → fixed (equivalent to `PoolSize::Fixed(25)`)
- No PY equivalent for `PerWorker` — Python doesn't need this because worker processes don't share pool instances

**Semantic match**: Same behavior, different API surface. This is acceptable per EATP D6 (independent implementation, matching semantics).

### 2. Auto-Scaling Formula

**RS formula**: `pool_size = (max_connections / workers) * 0.7` (minimum 2)
**PY formula**: `pool_size = max(2, int(db_max * 0.7) // workers)`

**These are mathematically identical.** `(100 / 4) * 0.7 = 17.5` vs `int(100 * 0.7) // 4 = 70 // 4 = 17`. Both produce 17.

**Alignment**: Already aligned. No change needed.

### 3. Environment Variable Names

| Purpose                     | RS Env Var                   | PY Env Var (current plan) | Alignment      |
| --------------------------- | ---------------------------- | ------------------------- | -------------- |
| Worker count (SDK-specific) | `KAILASH_WORKERS`            | `DATAFLOW_WORKER_COUNT`   | MISALIGNED     |
| Worker count (Uvicorn)      | `UVICORN_WORKERS`            | `UVICORN_WORKERS`         | Aligned        |
| Worker count (generic)      | `WEB_CONCURRENCY`            | `WEB_CONCURRENCY`         | Aligned        |
| Worker count (Gunicorn)     | —                            | `GUNICORN_WORKERS`        | PY-only (fine) |
| Worker count (generic)      | `WORKERS`                    | —                         | RS-only (fine) |
| Pool size override          | —                            | `DATAFLOW_POOL_SIZE`      | PY-only        |
| Max connections override    | `KAILASH_DB_MAX_CONNECTIONS` | —                         | RS-only        |

**Alignment decision**:

- PY should ALSO check `KAILASH_WORKERS` (the SDK-wide env var) in addition to `DATAFLOW_WORKER_COUNT`
- Priority order: `DATAFLOW_WORKER_COUNT` > `KAILASH_WORKERS` > `UVICORN_WORKERS` > `WEB_CONCURRENCY` > `GUNICORN_WORKERS`
- This ensures users setting `KAILASH_WORKERS` for the Rust SDK also get correct behavior from PY bindings

### 4. Config Field Names

| Purpose            | RS Field                        | PY Field (current plan)       | Alignment                      |
| ------------------ | ------------------------------- | ----------------------------- | ------------------------------ |
| Pool size          | `pool_size: PoolSize`           | `pool_size: Optional[int]`    | Semantically aligned           |
| Leak threshold     | `leak_detection_threshold_secs` | `leak_detection_timeout_secs` | **MISALIGNED**                 |
| Monitor interval   | (5s hardcoded in RS-2)          | `pool_monitor_interval_secs`  | PY is more configurable (fine) |
| Cache TTL          | `query_cache_ttl_secs`          | (existing `cache_ttl`)        | N/A (PY-3 cut)                 |
| Startup validation | (always on in RS)               | `startup_validation: bool`    | PY is more configurable (fine) |

**Alignment decision**:

- PY should rename `leak_detection_timeout_secs` → `leak_detection_threshold_secs` to match RS
- Both use "threshold" semantically (the point at which a warning fires), not "timeout" (which implies a hard cutoff)

### 5. Pool Stats API

**RS API**:

```rust
runtime.pool_utilization() -> (u32, u32, u32)  // (active, idle, max)
```

**PY API**:

```python
dataflow.pool_stats() -> dict  # {"active", "idle", "max", "overflow", "max_overflow", "utilization"}
```

**Alignment decision**: PY's API is richer (includes overflow and utilization %). RS returns a tuple. These are semantically compatible — PY exposes more detail because SQLAlchemy pools have overflow concepts that sqlx pools don't.

**Python bindings note**: When RS exposes `pool_utilization()` via PyO3, it should return a dict matching PY's `pool_stats()` format (with `overflow=0` and `max_overflow=0` since sqlx doesn't have overflow). This way Python users get a consistent API whether using native PY DataFlow or RS bindings.

### 6. Query Cache (RS-3 vs PY-3 CUT)

**RS approach**: Implementing `QueryCache` with DashMap in the Rust runtime.

**PY approach**: CUT from this workspace because PY already has:

- `dataflow/cache/memory_cache.py` (LRU with TTL)
- `dataflow/cache/redis_manager.py` (Redis backend)
- `dataflow/cache/invalidation.py` (invalidation logic)
- Config: `enable_query_cache`, `cache_ttl`, `cache_max_size`

**Alignment decision**: No action needed for PY. RS is building what PY already has. When RS ships RS-3, it will expose the cache via PyO3 bindings — but PY-native DataFlow already has equivalent functionality. The `cache: True` node parameter should work identically in both.

**TODO**: Verify that PY's existing cache infrastructure supports the `cache: True` node parameter that RS-3 will use. If not, add a todo to wire it up.

### 7. Lightweight Pool (RS-6) — PY Should Adopt

**RS approach**: Separate 2-connection pool for health checks and diagnostics.

**PY approach**: Added as Milestone 10 (lower priority, after core pool prevention).

**RS dev assessment**: "kailash-py health checks compete with the main pool, which is exactly the problem RS-6 solves."

**Alignment decision**: PY should implement this in the same workspace as a lower-priority milestone:

- Create a separate mini-pool (2 connections) for `/health` and `/ready` endpoints
- Wire into existing `HealthMonitor` in `platform/health.py`
- Expose `execute_raw_lightweight(sql)` API on DataFlow instance
- Startup validation (PY-4) should account for lightweight pool connections

### 8. Default Pool Size

**RS default**: Was `25`, changing to `PoolSize::Auto`
**PY default**: Was five competing values (10, 20, `min(50, cpu*4)`), changing to auto-detection

**Alignment**: Both change to auto-detection with the same formula. Aligned.

### 9. Startup Validation Behavior

**RS**: Logs ERROR but does not prevent startup. Always on (no opt-out).
**PY**: Logs ERROR but does not prevent startup. Opt-out via `startup_validation=False`.

**Alignment decision**: PY is more flexible (has opt-out). This is acceptable — PY users may need to disable for specific deployment scenarios. RS can add opt-out later if needed.

### 10. Monitor Implementation Pattern

**RS**: `tokio::spawn` async task with `tokio::time::interval`
**PY**: `threading.Thread(daemon=True)` with `threading.Event` for shutdown

**Alignment**: Different runtime models (async vs sync daemon thread). Both are correct for their platforms. Same behavior, different implementation.

---

## Required Changes to PY Todo List

Based on this alignment analysis, the following amendments are needed:

### Amendment 1: Add `KAILASH_WORKERS` to worker detection (TODO-07)

In `pool_utils.py` `detect_worker_count()`, add `KAILASH_WORKERS` to the env var check order:

```
DATAFLOW_WORKER_COUNT > KAILASH_WORKERS > UVICORN_WORKERS > WEB_CONCURRENCY > GUNICORN_WORKERS
```

### Amendment 2: Rename leak detection config field (TODO-33)

Change `leak_detection_timeout_secs` → `leak_detection_threshold_secs` to match RS naming.

### Amendment 3: Verify existing cache supports `cache: True` node parameter

Add a verification step to confirm that PY's existing cache infrastructure handles the `cache: True` parameter that RS-3 introduces. If not, add a todo to wire it up for API parity.

### Amendment 4: Document PyO3 binding expectations

When RS ships its improvements, the Python bindings will expose:

- `DataFlowConfig(pool_size="auto")` → maps to `PoolSize::Auto`
- `runtime.pool_utilization()` → should return dict matching `pool_stats()` format
- `DataFlowConfig(leak_detection_threshold_secs=30)` → same name as PY native

PY-native DataFlow and RS-via-PyO3 DataFlow should have identical Python API.

---

## Divergence Acceptance

| Divergence                           | Decision | Rationale                                                          |
| ------------------------------------ | -------- | ------------------------------------------------------------------ |
| PY has no `PoolSize` enum            | ACCEPT   | Python idiom is `Optional[int]`, not typed enums for simple config |
| PY has no `PerWorker` variant        | ACCEPT   | Python workers don't share pools                                   |
| PY has richer `pool_stats()`         | ACCEPT   | SQLAlchemy pools have overflow, sqlx doesn't                       |
| PY has `startup_validation` opt-out  | ACCEPT   | More flexible, RS can add later                                    |
| PY cuts RS-3 (Query Cache)           | ACCEPT   | PY already has equivalent infrastructure                           |
| PY adopts RS-6 as Milestone 10       | ADOPT    | RS dev confirms PY health checks compete with main pool            |
| PY uses `DATAFLOW_POOL_SIZE` env var | ACCEPT   | PY-specific override, RS uses `KAILASH_DB_MAX_CONNECTIONS`         |

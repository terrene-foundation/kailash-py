# Revised Improvement Plan

**Date**: 2026-03-20
**Status**: Analysis complete, pending human review
**Supersedes**: `00-pool-improvements.md` (original five-item plan)

---

## Design Principle

Users ALWAYS struggle with connection pooling. The SDK must make it **impossible to do the wrong thing** with default settings. This means:

1. Defaults must be correct without user intervention
2. Wrong configurations must be caught and reported at startup
3. Runtime problems must be visible before they cause outages
4. The configuration surface must be minimal and unambiguous

---

## Changes from Original Plan

| Original                                     | Revised                          | Reason                                                                                          |
| -------------------------------------------- | -------------------------------- | ----------------------------------------------------------------------------------------------- |
| PY-1 through PY-5 as standalone              | PR-0 (prerequisite) added        | Five competing defaults must be unified first                                                   |
| PY-3 (Query Cache) included                  | **CUT**                          | Existing cache infrastructure already covers this; PY-3 would duplicate it with different names |
| PY-4 before PY-1                             | Reversed: PY-1 before PY-4       | PY-4 shares detection logic with PY-1; build the shared module first                            |
| MonitoringConfig left as-is                  | Must be wired or removed         | Dead flags are a `no-stubs.md` violation                                                        |
| asyncpg leak detection via SQLAlchemy events | asyncpg-specific instrumentation | asyncpg has no SQLAlchemy events; PY-5 must wrap `pool.acquire()`/`pool.release()`              |

---

## Implementation Phases

### Phase 0: Consolidate Pool Defaults (PREREQUISITE)

**Goal**: Exactly one code path determines effective pool size.

| Action                                                                | File        |
| --------------------------------------------------------------------- | ----------- |
| Create `DatabaseConfig` with `pool_size=None` when user hasn't set it | `engine.py` |
| Remove hardcoded `pool_size=20` from `DataFlow.__init__`              | `engine.py` |
| Move `DATAFLOW_POOL_SIZE` env var read into `get_pool_size()`         | `config.py` |
| Remove dead `connection_pool_size` from `DataFlowConfig`              | `config.py` |
| Make `DatabaseAdapter` defer to config for pool_size                  | `base.py`   |
| Remove ghost `final_pool_size` code                                   | `engine.py` |

**Test**: Instantiate `DataFlow("postgresql://...")` with no explicit pool_size. Assert the effective pool size matches `DatabaseConfig.get_pool_size()` output.

**Effort**: 0.5 day

### Phase 1: Shared Pool Utilities

**Goal**: Reusable detection logic for PY-1 and PY-4.

**New file**: `packages/kailash-dataflow/src/dataflow/core/pool_utils.py`

| Function                                      | Purpose                                                                                                          |
| --------------------------------------------- | ---------------------------------------------------------------------------------------------------------------- |
| `probe_max_connections(url) -> Optional[int]` | Query PostgreSQL `SHOW max_connections` via temporary connection. Returns `None` on failure. Timeout: 5 seconds. |
| `detect_worker_count() -> int`                | Read `UVICORN_WORKERS` / `WEB_CONCURRENCY` / `GUNICORN_WORKERS` / `DATAFLOW_WORKER_COUNT`. Clamp to >= 1.        |
| `is_postgresql(url) -> bool`                  | Check if URL is PostgreSQL                                                                                       |
| `is_sqlite(url) -> bool`                      | Check if URL is SQLite                                                                                           |

**Edge cases handled**:

- PgBouncer: `SHOW max_connections` returns PgBouncer's limit, which is the correct value for pool sizing (PgBouncer manages the PostgreSQL connection limit)
- MySQL: `SHOW VARIABLES LIKE 'max_connections'` (different syntax)
- Probe failure: return `None`, caller uses fallback
- Worker count env var = 0 or negative: clamp to 1

**Effort**: 0.5 day

### Phase 2: PY-1 — Pool Auto-Scaling

**Goal**: Default pool size is always safe.

Modify `DatabaseConfig.get_pool_size()` to implement auto-scaling when `pool_size is None`:

```python
def get_pool_size(self, environment: Environment) -> int:
    if self.pool_size is not None:
        return self.pool_size  # Explicit always wins

    # Check env var override
    env_val = os.environ.get("DATAFLOW_POOL_SIZE")
    if env_val is not None:
        return int(env_val)

    # Auto-detect from server
    db_max = probe_max_connections(self.get_connection_url(environment))
    workers = detect_worker_count()

    if db_max is not None:
        available = int(db_max * 0.7)  # Reserve 30% for admin/migrations
        return max(2, available // workers)
    else:
        # Fallback: conservative static default
        return min(5, multiprocessing.cpu_count())
```

**Key decisions**:

- `"auto"` is the implicit default (no new parameter needed — just remove the hardcoded overrides from Phase 0)
- 70% reservation (30% for admin/monitoring/migrations)
- Fallback: `min(5, cpu_count)` — conservative, safe for all deployments
- `max_overflow`: `max(2, pool_size // 2)` — bounded, not 2x pool_size

**Backward compatibility**:

- Explicit `pool_size=25` still works (first check in `get_pool_size()`)
- `DATAFLOW_POOL_SIZE=25` still works (second check)
- Only when both are unset does auto-scaling engage

**Effort**: 1.5 days

### Phase 3: PY-4 — Startup Validation

**Goal**: Misconfigured pools are caught before first query.

On `DataFlow.connect()`, call `validate_pool_config()` which uses `pool_utils` to:

1. Query `max_connections` from database
2. Compute `total_possible = (pool_size + max_overflow) * workers`
3. Compare against server limit

| Condition                        | Action                                     |
| -------------------------------- | ------------------------------------------ |
| `total_possible > db_max`        | `ERROR` log with exact remediation command |
| `total_possible > db_max * 0.7`  | `WARNING` log                              |
| `total_possible <= db_max * 0.7` | `INFO` log confirming safe config          |
| Probe fails                      | `WARNING` log, continue startup            |

**Advisory only** — does not block startup. Rationale: blocking would break PgBouncer deployments where intentional overcommit is correct.

**Opt-out**: `DataFlowConfig(startup_validation=False)` or `DATAFLOW_STARTUP_VALIDATION=false`

**Effort**: 0.5 day

### Phase 4: PY-2 — Pool Utilization Monitor

**Goal**: Runtime visibility into pool health.

**New file**: `packages/kailash-dataflow/src/dataflow/core/pool_monitor.py`

`PoolMonitor` class:

- Daemon thread, starts on `DataFlow.connect()`, stops on `disconnect()`
- Reads pool stats via `PoolStatsProvider` protocol (unified across asyncpg, SQLAlchemy, SQLite)
- Threshold-based logging:
  - < 70%: silent
  - 70-79%: INFO every interval
  - 80-94%: WARNING every interval
  - > = 95%: ERROR at 0.5x interval with longest-held connection info
- Interval configurable via `pool_monitor_interval_secs` (default 10)

**Wires up MonitoringConfig flags**:

- `connection_metrics=True` → enables `pool_stats()` collection
- `alert_on_connection_exhaustion=True` → enables ERROR logs at >= 95%

**Public API**: `dataflow.pool_stats()` returns:

```python
{
    "active": 8,
    "idle": 12,
    "max": 20,
    "overflow": 2,
    "max_overflow": 10,
    "utilization": 0.4,
}
```

**Lifecycle**:

- Starts: `DataFlow.connect()`
- Stops: `DataFlow.disconnect()`, `DataFlow.__del__`, or `atexit`
- Uses weak reference to engine to prevent lifecycle coupling
- Exception isolation: per-feature try/except in monitor loop

**Effort**: 1.5 days

### Phase 5: PY-5 — Leak Detection

**Goal**: Identify which code path is holding connections too long.

Extends `PoolMonitor` with connection tracking:

**On checkout**: Record `(connection_id, monotonic_time, traceback_summary)` — limited to 10 frames
**On checkin**: Remove tracking record
**Monitor cycle**: Check held connections against threshold

| Condition                                    | Action                          |
| -------------------------------------------- | ------------------------------- |
| `held_time > leak_detection_timeout_secs`    | WARNING with checkout traceback |
| `held_time > 3x leak_detection_timeout_secs` | ERROR ("probable leak")         |

**Adapter-specific instrumentation**:

- SQLAlchemy: `@event.listens_for(engine, "checkout")` / `"checkin"`
- asyncpg: Wrap `pool.acquire()` / `pool.release()` with tracking callbacks
- SQLite: Wrap `SQLiteEnterpriseAdapter._get_connection()` context manager

**Configuration**:

- `leak_detection_enabled=True` (default)
- `leak_detection_timeout_secs=30` (default)

**Bounded**: Max 10,000 tracked connections (per `infrastructure-sql.md` Rule 7)

**Effort**: 1 day

---

## Summary

| Phase     | Content                        | Effort       | Cumulative |
| --------- | ------------------------------ | ------------ | ---------- |
| 0         | Consolidate pool defaults      | 0.5 day      | 0.5 day    |
| 1         | Shared pool utilities          | 0.5 day      | 1 day      |
| 2         | PY-1: Auto-scaling             | 1.5 days     | 2.5 days   |
| 3         | PY-4: Startup validation       | 0.5 day      | 3 days     |
| 4         | PY-2: Pool utilization monitor | 1.5 days     | 4.5 days   |
| 5         | PY-5: Leak detection           | 1 day        | 5.5 days   |
| **Total** |                                | **5.5 days** |            |

**Cut**: PY-3 (Query Cache) — existing cache infrastructure is sufficient

---

## Risk Register

| ID  | Risk                                                                | Severity | Mitigation                                                                                                                                           |
| --- | ------------------------------------------------------------------- | -------- | ---------------------------------------------------------------------------------------------------------------------------------------------------- |
| R1  | PgBouncer returns PgBouncer's limit, not PostgreSQL's               | MEDIUM   | This is actually correct — pool sizing should respect the connection limit at the point DataFlow connects to, whether that's PostgreSQL or PgBouncer |
| R2  | Worker count undetectable (no env vars set)                         | HIGH     | Default to `workers=1` + conservative fallback `min(5, cpu_count)`. Document `DATAFLOW_WORKER_COUNT` env var for explicit override.                  |
| R3  | asyncpg has no SQLAlchemy events for PY-5                           | HIGH     | Wrap asyncpg `pool.acquire()`/`pool.release()` directly                                                                                              |
| R4  | Traceback capture on every checkout is expensive at high throughput | MEDIUM   | Use `traceback.extract_stack(limit=10)` — lightweight FrameSummary objects, bounded depth                                                            |
| R5  | Monitor daemon thread orphaned in test environments                 | MEDIUM   | Explicit `stop()` method; `DataFlow.close()` must stop monitor; pytest fixture cleanup                                                               |
| R6  | Rolling deployment: workers start at different times                | LOW      | Each worker validates independently — later workers may log warnings that earlier workers didn't. This is correct behavior.                          |

---

## Success Criteria

- [ ] `DataFlow("postgresql://...")` with default settings produces pool_size that cannot exhaust PostgreSQL's default `max_connections=100` with up to 4 workers
- [ ] Startup log confirms pool validation result
- [ ] `pool_stats()` returns real-time utilization
- [ ] Connection held >30s produces WARNING with checkout location
- [ ] Explicit `pool_size=N` overrides all auto behavior
- [ ] All five previous default paths consolidated into one
- [ ] `MonitoringConfig.alert_on_connection_exhaustion` is no longer dead code
- [ ] Zero new dependencies added
- [ ] All existing DataFlow tests pass without modification (backward compatible)

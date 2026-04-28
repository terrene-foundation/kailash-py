# Pre-Existing Codebase Defects

**Date**: 2026-03-20
**Status**: Confirmed by deep-analyst, requirements-analyst, COC expert

These defects MUST be resolved before any new pool feature can work correctly. They are not optional — they make any new pool logic unreliable because the new logic's output gets overwritten by hardcoded defaults downstream.

---

## DEFECT-A: Five Competing Pool Size Defaults

The pool size is determined by **five different code paths** depending on how the user initializes DataFlow. No single path is authoritative.

| #   | Source                                                | Default Value                                     | File        | Line |
| --- | ----------------------------------------------------- | ------------------------------------------------- | ----------- | ---- |
| 1   | `DatabaseConfig.get_pool_size(PRODUCTION)`            | `min(50, cpu_count * 4)`                          | `config.py` | 347  |
| 2   | `DataFlowConfig.__init__` `connection_pool_size`      | `10`                                              | `config.py` | 462  |
| 3   | `DataFlow.__init__` constructing `DatabaseConfig`     | `20`                                              | `engine.py` | ~224 |
| 4   | `DataFlow.__init__` `enable_connection_pooling` block | `int(os.environ.get("DATAFLOW_POOL_SIZE", "10"))` | `engine.py` | ~445 |
| 5   | `DatabaseAdapter.__init__` (base class)               | `10`                                              | `base.py`   | 54   |

### Why This Happened

Classic convention drift. The original design had `DatabaseConfig.get_pool_size(environment)` as the single source of truth. Over time, code was written in contexts where a `DatabaseConfig` or `Environment` wasn't available, so local defaults were invented. Nobody reconciled them.

### Critical Finding

`get_pool_size()` (source #1) is **dead code** in the most common initialization path. When a user does `DataFlow("postgresql://...")`, engine.py line ~224 sets `pool_size=20` on the `DatabaseConfig` it constructs. This means `get_pool_size()` sees `self.pool_size is not None` (it's 20), returns 20, and the CPU-based calculation never runs.

Source #4 is also dead — `final_pool_size` is computed but never stored back into config.

### Impact

Any improvement to `get_pool_size()` (including PY-1 auto-scaling) will be invisible to users because the value gets overwritten before the function is called.

### Resolution

1. `DatabaseConfig` should be created with `pool_size=None` when the user hasn't explicitly set it
2. Remove the hardcoded `20` from engine.py
3. Remove the `DATAFLOW_POOL_SIZE` env var read from engine.py (move to `get_pool_size()`)
4. Remove `connection_pool_size` from `DataFlowConfig` (dead attribute)
5. Make `DatabaseAdapter` defer to config instead of defaulting to `10`
6. After cleanup, exactly ONE method determines effective pool size: `DatabaseConfig.get_pool_size()`

---

## DEFECT-B: MonitoringConfig Dead Flags

`MonitoringConfig` (config.py lines 358-387) defines flags that nothing reads:

| Flag                             | Default        | Consumers |
| -------------------------------- | -------------- | --------- |
| `alert_on_connection_exhaustion` | `True`         | **NONE**  |
| `alert_on_slow_queries`          | `True`         | **NONE**  |
| `alert_on_failed_transactions`   | `True`         | **NONE**  |
| `connection_metrics`             | `True`         | **NONE**  |
| `query_insights`                 | `True`         | **NONE**  |
| `transaction_tracking`           | `True`         | **NONE**  |
| `metrics_export_interval`        | `60`           | **NONE**  |
| `metrics_export_format`          | `"prometheus"` | **NONE**  |

### Why This Is Worse Than Missing Monitoring

A user configuring `MonitoringConfig(alert_on_connection_exhaustion=True)` believes they have exhaustion alerts. They don't. This is **deceptive dead code** — functionally identical to a stub. Under `no-stubs.md` Rule 4 ("If a service is referenced, it must be functional"), this is a BLOCK-level finding.

### Resolution

PY-2 (Pool Utilization Monitor) must wire `alert_on_connection_exhaustion` and `connection_metrics` to real behavior. Any flags that PY-2 doesn't implement should be removed entirely — not left as promises.

---

## DEFECT-C: Redundant Cache Infrastructure

`DataFlowConfig` already has:

- `enable_query_cache: bool`
- `cache_ttl: int`
- `cache_max_size: int` / `_cache_max_size`
- `cache_invalidation_strategy: str`
- `cache_key_prefix: str`
- Redis connection config

DataFlow already has full cache implementations:

- `dataflow/cache/memory_cache.py` — LRU with TTL and model-based invalidation
- `dataflow/cache/redis_manager.py` — Redis cache backend
- `dataflow/cache/async_redis_adapter.py` — Async Redis adapter
- `dataflow/cache/invalidation.py` — Cache invalidation logic
- `dataflow/cache/list_node_integration.py` — List node cache integration

PY-3 (Query Cache) would duplicate all of this with different parameter names (`read_cache_ttl_secs` vs `cache_ttl`, `read_cache_max_size` vs `cache_max_size`, `read_cache_enabled` vs `enable_query_cache`), creating the exact same convention drift that caused DEFECT-A.

### Resolution

PY-3 is **descoped**. If the existing cache isn't being used effectively, that's a documentation/adoption problem, not a missing feature.

---

## DEFECT-D: Three Different Pool Types Without Unified Interface

DataFlow uses three different pool implementations with no common interface:

| Database    | Pool Implementation                   | Stats API                                 |
| ----------- | ------------------------------------- | ----------------------------------------- |
| PostgreSQL  | asyncpg native pool                   | `pool.get_size()`, `pool.get_idle_size()` |
| SQLite      | `SQLiteEnterpriseAdapter` custom pool | `SQLiteConnectionPoolStats` dataclass     |
| Generic SQL | SQLAlchemy `QueuePool`                | `pool.checkedout()`, `pool.checkedin()`   |

PY-2 (Monitor) and PY-5 (Leak Detection) must work across all three. Without a unified `PoolStatsProvider` protocol, the monitor will need adapter-specific code paths.

### Resolution

Create a `PoolStatsProvider` protocol (or ABC) that all three pool types implement, returning a common stats dict. PY-2's monitor consumes this protocol.

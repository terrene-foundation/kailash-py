# Risks and Edges — Per-Loop Transaction Pool Migration

## Risk 1: Sync DDL path (`auto_migrate`)

`DataFlow.auto_migrate()` and related sync DDL helpers run in sync context where `asyncio.get_running_loop()` raises. The current implementation uses `_connection_manager._adapter` directly via `async_safe_run`. After Phase 2 removes the retained adapter, the sync path needs a different resolution.

**Mitigation:** sync DDL goes through `async_safe_run(self._connection_manager._sync_ddl_helper(...))` where `_sync_ddl_helper` opens a transient adapter, runs the DDL, closes the adapter. This matches the spirit of the existing `_initialize_database` reachability check — DDL is a one-shot operation, not a hot path; transient connection cost is negligible.

**Residual risk:** any existing caller that holds a reference to `_connection_manager._adapter` and uses it for non-DDL queries will break. Cluster 3 enumerated 4 internal call sites; each must be migrated explicitly. Search command: `grep -rn "_connection_manager\._adapter\|_connection_manager\.\b" packages/kailash-dataflow/src/dataflow/`.

## Risk 2: Pool churn under multi-loop test workloads

Each pytest-asyncio function-scoped test creates its own loop. Under the new model, each loop creates its own transaction pool. With `max_pool_count_per_process=100` default (`src/kailash/nodes/data/async_sql.py::_POOL_DEFAULTS`), a test suite with > 100 distinct loops in flight could hit `PoolExhaustedError`.

**Mitigation:** the DPI-B3 reaper task (`_idle_pool_reaper_loop`, `async_sql.py:2764`) closes idle pools after `idle_timeout=300s` default. In practice, test suites complete each test's loop before the next starts, so loop-pool count tracks "currently active loops" rather than "total loops ever seen." WeakValueDictionary semantics also auto-reap on loop close.

**Residual risk:** very large parallel test suites (>100 simultaneous workers) could exceed the cap. Production DataFlow workloads typically use one loop, so production is unaffected. Test infra can lower `idle_timeout` via `set_pool_defaults(idle_timeout=2)` if needed (already documented at `async_sql.py:2718`).

## Risk 3: DPI-B2 `max_pool_count_per_process` cap shared across surfaces

Bringing async transactions onto `_PROCESS_POOL_REGISTRY` means transaction pools count toward the same cap as Express pools. Today, a single DataFlow with one loop creates one Express pool; under the new model it might create one Express pool AND one transaction pool (if the connection_string happens to differ — e.g., different pool_size kwarg). Practically the connection_string is the same so the pool key is the same.

**Mitigation:** verify `_generate_pool_key` keys yield identical results for Express and Transaction call sites with the same DataFlow config. If they do, the same pool is shared (good — fewer pools, no cap concern). If they don't, document the divergence in `specs/dataflow-cache.md §13.4` and consider unifying the key shape.

**Residual risk:** keys might diverge silently — `_generate_pool_key` includes `pool_size` and `max_pool_size` in the key. If `TransactionManager` uses different sizing than `db.express.*`, separate pools result. Verify during implementation; fix by passing consistent sizing OR using a shared sizing helper.

## Risk 4: Loop closure ordering in pytest-asyncio

When a pytest-asyncio test ends, its loop closes. The reaper task is GC'd on loop close (held by `_REAPER_TASKS[id(loop)]` — strong ref to the task only as long as the loop holds it). The next test creates a new loop; `_ensure_reaper_started` registers a new reaper for the new loop. Sequence:

1. Test A's loop dies. WeakValueDictionary entries for that loop are eligible for GC on next mapping access.
2. Reaper task A is cancelled (loop shutdown semantics).
3. Test B's loop starts. `_ensure_reaper_started` runs, registers reaper B.
4. Test B's first transaction call hits `_PROCESS_POOL_REGISTRY.get(pool_key_B)` — None (different loop_id), creates new pool B.

**Edge case:** if pool A is held by a strong reference somewhere outside the registry (e.g., a finally-block cleanup task), it won't be GC'd. The reaper covers this case (live-but-idle pool reaped after `idle_timeout`).

**Residual risk:** if a test holds a strong reference to a pool object across tests (uncommon but possible), the pool persists until reaper sweep. This is the existing Express path's behavior — not new with this fix.

## Risk 5: Transient `__init__` connection latency

The init-time `SELECT 1` reachability check currently runs against a retained pool, paying `create_pool` cost once. The new transient-connection model pays a single `asyncpg.connect()` + `SELECT 1` + `disconnect()` per `DataFlow.__init__`. Net cost difference is ~5-20 ms (a single TCP+TLS handshake instead of a pool warm-up).

**Mitigation:** init-time cost is one-time; warm-path queries pay zero new cost (pools created lazily on first use, then cached for the loop's lifetime).

**Residual risk:** in environments where DataFlow is repeatedly constructed (some test patterns), the per-init handshake adds up. Mitigation: tests use the existing `_tdd_mode` carve-out (`core/engine.py:1721`) which already skips `initialize_pool`.

## Risk 6: Connection-pool monitoring breakage

`db.get_connection_pool()` (`core/engine.py:3459`) currently returns stats based on `_connection_manager._adapter.connection_pool` (verified via `core/engine.py:9755-9810`). If we remove the retained adapter, this returns nothing.

**Mitigation:** rewire `get_connection_pool()` to walk `_PROCESS_POOL_REGISTRY` for entries matching this DataFlow's `connection_string` and return aggregated stats. The walk pattern already exists at `core/engine.py:9762-9774` (which DOES walk `AsyncSQLDatabaseNode._shared_pools`); extending to `_PROCESS_POOL_REGISTRY` is a small change.

**Residual risk:** stats may surface multiple loop-keyed pools as separate entries; the API today returns one. Decide whether to aggregate (sum across loops) or expose per-loop. Aggregate is closer to current observable behavior.

## Risk 7: Breaking change to internal API

`_connection_manager._adapter` is internal (no spec mention, no `__all__` export, prefix underscore). Per `rules/zero-tolerance.md` Rule 6a, internal APIs do NOT require deprecation cycle — but four internal callers exist and break atomically when removed.

**Mitigation:** Phase 2 removes the field assignment AND migrates all four callers in the same shard. Phase 1 (transaction surface) is the highest-value caller. The other three are sync-DDL helpers that move to the transient-connection helper.

**Residual risk:** downstream consumers (kaizen, pact, ml, align) may have grep'd for `_connection_manager._adapter` as a workaround. Search across `packages/kailash-*/src/` before landing. Cluster 3 only searched `packages/kailash-dataflow/src/`; broaden in implementation.

## Edge: SQLite

`_PROCESS_POOL_REGISTRY` and `_generate_pool_key` are defined in `async_sql.py` for asyncpg/aiomysql/aiosqlite. SQLite pool semantics differ (in-memory `:memory:` DBs don't pool meaningfully). Verify the per-loop key shape works for SQLite — likely yes (SQLite adapter has its own connection model that's loop-agnostic for file-based DBs and loop-bound for `:memory:`).

**Residual risk:** `:memory:` SQLite + multi-loop tests would create separate in-memory DBs per loop, which may break tests that expect data to persist across loops. This is already true for the Express path (which uses the same registry); not new with this fix.

## Edge: read-replica `_read_connection_manager`

`core/engine.py:611-613` shows DataFlow can have a separate `_read_connection_manager` for read replicas. The fix must apply symmetrically — read-replica transactions also need per-loop pools. Verify by tracing whether `TransactionManager` ever resolves to the read replica (probably not — transactions hit primary by definition) but document explicitly.

**Mitigation:** read-replica `ConnectionManager` follows the same Phase 2 migration (transient health check, no retained pool). Reads via `db.express.list/...` already go through `AsyncSQLDatabaseNode` which already uses per-loop pools.

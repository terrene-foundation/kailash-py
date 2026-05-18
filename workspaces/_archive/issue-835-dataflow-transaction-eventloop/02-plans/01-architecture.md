# Architecture Plan — Fix Issue #835

## TL;DR

`db.transactions.begin()` (async surface) currently resolves to a single asyncpg pool created during `_ensure_connected` (lazy, on first DB touch). `_ensure_connected` is a sync method invoked from an async caller's running loop; it bridges to async via `async_safe_run`, which takes the thread-pool path, builds a worker-thread loop, runs `initialize_pool()` on it, then closes the worker loop on return. The pool is bound to that closed worker loop. Every later `db.transactions.begin()` from any loop hits `RuntimeError: Event loop is closed` on `pool.acquire()`. The fix is to delegate transaction-pool resolution to the same per-loop registry pattern (`_PROCESS_POOL_REGISTRY` / `_generate_pool_key()`) that `AsyncSQLDatabaseNode` already uses for `db.express.*`, with the loop-id keyed into the pool cache key. The fail-fast reachability contract from `rules/dataflow-pool.md` Rule 2 is preserved by keeping the `SELECT 1` health check via a transient connection inside `_ensure_connected` (no retained pool).

## Recommended fix — Candidate D (per-loop pool registry for transactions)

### What changes

1. `TransactionManager._get_adapter()` (`packages/kailash-dataflow/src/dataflow/features/transactions.py:387-411`) — REPLACE the dead-code fallback chain with a positive resolution: look up or create a pool keyed on `(connection_string, id(asyncio.get_running_loop()))` via the existing `_PROCESS_POOL_REGISTRY` infrastructure exposed by `kailash.nodes.data.async_sql`.

2. `ConnectionManager.initialize_pool()` (`packages/kailash-dataflow/src/dataflow/utils/connection.py:61-104`) — REPLACE the retained-pool model. The init-time `SELECT 1` reachability check (currently at `connection.py:121` indirectly via `_adapter.execute_query`) is preserved using a transient connection that is opened and closed within the same `async_safe_run` call. No long-lived pool object is retained at `_connection_manager._adapter`.

3. `_connection_manager._adapter` field — DEPRECATE in 2.8.0, REMOVE in 2.9.0 (per `rules/zero-tolerance.md` Rule 6a deprecation cycle). All read sites today are inside dataflow itself; no public-API surface exposes it directly. Per Rule 6a §"Spec §X never documented the parameter, so it's not public surface" carve-out, the field is internal — no external deprecation shim required, but the internal callers that currently read it (cluster-3 enumerated 4 sites) all need migration.

4. `specs/dataflow-cache.md §12` — UPDATE to document the per-loop pool semantics for `db.transactions.begin()` (mirror of §12.7's loop-binding documentation for `transactions_sync`).

### Why this is the optimal fix

**Root-cause vs. symptom (per `/autonomize` directive Rule 2):** The brief's three fixes (A/B/C) all patch surfaces. The root cause is that asyncpg pools are loop-bound and the engine retains a single pool across loops. The fix retires single-pool retention and brings async transactions onto the per-loop registry pattern that `db.express.*` already uses correctly. After the fix, asyncpg pools are NEVER reused across loops anywhere in DataFlow.

**Long-term over short-term (per `/autonomize` Rule 3):**

- Reuses existing tested infrastructure (`_PROCESS_POOL_REGISTRY`, `_idle_pool_reaper_loop`, `_generate_pool_key`) rather than introducing parallel logic.
- Eliminates an entire class of "pool retained across loop boundaries" bugs going forward.
- Aligns the async transaction surface with the documented loop-binding contract (`specs/dataflow-cache.md §12.7`).
- Captures the institutional knowledge as a regression test (Tier 2, real PostgreSQL) for cross-loop transaction usage — closes the gap currently unmissed by `test_issue_707_*` and `test_issue_711_*`.

**Completeness (per `/autonomize` Rule 4):**

- All four affected files updated atomically.
- Spec updated in same PR per `rules/specs-authority.md` MUST Rule 5.
- Cross-SDK companion issue prepared for `kailash-rs` (the brief tagged `cross-sdk`) with the analogous question — does the Rust SDK's transaction primitive have the same pool-loop binding gap? Filed as a separate user-gated issue per `rules/upstream-issue-hygiene.md` after this fix lands.

### Why NOT the brief's three fixes

| Candidate                          | Verdict      | Reason                                                                                                                                                                                                    |
| ---------------------------------- | ------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| A — Re-order `_get_adapter()`      | NO-OP        | `_cached_async_node` branch has no production setter (cluster 3 verified). Dead code re-ordered is still dead.                                                                                            |
| B — Lazy bind in `initialize_pool` | BLOCKED      | Identical to `lazy_connect=True` which is BLOCKED by `rules/dataflow-pool.md` Rule 2 (fail-fast at init).                                                                                                 |
| C — Opt-in `DataFlowExpressSync`   | WRONG TARGET | `SyncExpress` and `SyncTransactionManager` are already lazy. They are NOT involved in the failure mode (the daemon thread never runs in the bug repro because user code never accesses those properties). |

## Implementation outline

### Phase 1 — Replace `TransactionManager._get_adapter()` by reusing `AsyncSQLDatabaseNode._get_adapter()`

REVISED after red-team review (analyst C1+C3, dataflow-specialist C1). The original draft invented a phantom `_build_pool_key_for_dataflow` helper that does not exist; the actual key shape is 5-component (`loop_id|db_type|connection|pool_size|max_pool_size` per `src/kailash/nodes/data/async_sql.py:4148-4171`); and three pool registries (`_shared_pools` + `_PROCESS_POOL_REGISTRY` + `EnterprisePoolManager`) are involved in resolution priority. Inventing a new direct-`_PROCESS_POOL_REGISTRY.get` path would bypass the priority chain and miss the per-key creation lock that exists in `AsyncSQLDatabaseNode._get_adapter()`.

CORRECTION (sub-finding during revision): The `transaction_nodes.py:59` pattern references `dataflow_instance._get_cached_db_node(db_type)`, but `_get_cached_db_node` is NOT DEFINED anywhere in the source tree. `TransactionScopeNode` (which uses `_get_adapter_from_context`) is wired into the engine at `core/engine.py:8590` but the path is broken at runtime — calling it raises `AttributeError`. This is a separate latent bug discovered during plan revision; it does NOT block issue #835 (TransactionScopeNode is a workflow-context node, never reached by `db.transactions.begin()`).

The actual resolution path that DOES work today: `db.express.list/...` resolves nodes via `self._db._nodes[node_name]` (`features/express.py:206-211`). Each model's CRUD node is a `AsyncSQLDatabaseNode` instance configured against the DataFlow's connection. Calling `._get_adapter()` on ANY of them resolves to the same per-loop pool entry because the 5-component key converges (same `db_type`, same `connection`, same `pool_size`/`max_pool_size`, same `loop_id`).

For `TransactionManager`, which has no model context, the corrected plan: construct a dedicated cached `AsyncSQLDatabaseNode` instance ONCE on first `_get_adapter()` call, configured against the DataFlow's connection, and reuse across all subsequent `begin()` calls. Same key shape ⇒ same per-loop pool ⇒ shared with Express path automatically.

```python
# packages/kailash-dataflow/src/dataflow/features/transactions.py:387-411
async def _get_adapter(self) -> Any:
    """Resolve the loop-bound database adapter via a dedicated cached
    AsyncSQLDatabaseNode whose pool-key shape matches the Express path,
    so the per-loop pool is shared.

    The node's own `_get_adapter()` (kailash.nodes.data.async_sql:4173)
    walks the priority chain (shared_pools → runtime pool →
    _PROCESS_POOL_REGISTRY → fallback) using a 5-component key
    `loop_id|db_type|connection|pool_size|max_pool_size` (line 4148-4171).
    Per-key creation lock (`_pool_locks_by_loop`, line 2983) + DPI-B2 cap
    enforcement come for free.

    Pool sharing with Express: `db.express.*` resolves nodes from
    `self._db._nodes[name]` (`features/express.py:206-211`). Each model
    node has the same connection_string + pool_size config, so all share
    one entry per loop in `_PROCESS_POOL_REGISTRY`. The TransactionManager's
    dedicated node uses identical config, joining the same key.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError as e:
        raise RuntimeError(
            "TransactionManager.begin() requires a running event loop. "
            "Call from within an async function or `asyncio.run(...)`."
        ) from e

    if self._cached_db_node is None:
        self._cached_db_node = self._build_db_node()

    adapter = await self._cached_db_node._get_adapter()
    if adapter is None:
        raise RuntimeError(
            "TransactionManager could not resolve a database adapter — "
            "the priority chain returned None. Check DataFlow init logs."
        )
    return adapter

def _build_db_node(self) -> "AsyncSQLDatabaseNode":
    """Build a single AsyncSQLDatabaseNode whose pool-key matches Express."""
    from kailash.nodes.data.async_sql import AsyncSQLDatabaseNode
    cfg = self.dataflow.config
    db_url = cfg.database.url or ""
    if "postgres" in db_url:
        db_type = "postgresql"
    elif "mysql" in db_url:
        db_type = "mysql"
    else:
        db_type = "sqlite"
    # Match the same constructor kwargs Express's CRUD nodes use, so the
    # `_generate_pool_key` output is identical.
    return AsyncSQLDatabaseNode(
        database_type=db_type,
        connection_string=db_url,
        pool_size=cfg.database.pool_size,
        max_pool_size=cfg.database.pool_max_overflow or cfg.database.pool_size * 2,
    )
```

`self._cached_db_node` is a new `Optional[AsyncSQLDatabaseNode]` field on `TransactionManager`, defaulting to `None`. The cached node is constructed once on first transaction, then reused. Per-loop pool resolution still happens INSIDE `_get_adapter()` — the cached node is just the dispatch entry.

**Key-shape verification (must verify at /implement):** the unit test for `_build_db_node()` asserts the constructed node's `_generate_pool_key()` output (with a fixed dummy loop_id) matches the output produced by an arbitrary `db._nodes["<Model>CreateNode"]._generate_pool_key()`. Identical → same registry entry. Different → fix the constructor kwargs to match.

The method becomes `async`. Single caller at `transactions.py:272` (`adapter = self._get_adapter()`) becomes `adapter = await self._get_adapter()`. The fix returns the SAME adapter object that `db.express.*` would resolve for the same loop — same `connection_pool` (asyncpg.Pool), same lifecycle, single source of truth.

**Why this is better than building a new registry path:**

- `AsyncSQLDatabaseNode._get_adapter()` (line 4173-4318 of async_sql.py) is ~150 LOC of priority-chain + lock + cap logic. Reusing means 0 new LOC of registry plumbing in dataflow.
- The 5-component key shape is automatic (the node owns the key generation).
- `EnterprisePoolManager` (priority 0) and `_shared_pools` (priority 1) compatibility is automatic.
- Per-key concurrency lock (`_pool_locks`) is automatic (H3 closed for free).
- DPI-B2 max-pool cap is enforced for free.
- `_PoolWrapper` (transactions.py:441) becomes orphan and is deleted in same PR (per `rules/orphan-detection.md`).

**`_PoolWrapper` deletion (H2 from dataflow-specialist):** The dead `_cached_async_node` branch in `_get_adapter()` referenced `_PoolWrapper`. After this revision, `_get_adapter()` returns adapters with `connection_pool` directly (no wrapping needed). `_PoolWrapper` class + its 1 import are removed in the same PR. Tests importing `_PoolWrapper` (if any) are deleted; `pytest --collect-only -q tests/` re-derives coverage per `rules/agents.md` reviewer mechanical sweeps.

### Phase 2 — Convert retained pool to transient reachability check

REVISED after red-team review (analyst H2). The original draft claimed `initialize_pool()` already runs a `SELECT 1` health check at init; verification of `connection.py:61-104` shows it does NOT — the retained-pool path's reachability proof is `await self._adapter.connect()` (line 88) only. The `SELECT 1` at line 121 lives in a separate `health_check()` method that is NOT called from `__init__` today.

The disposition: KEEP the existing reachability proof shape (`await test_adapter.connect()` succeeds → reachable). Do NOT add a new `SELECT 1` — that would be a behavior expansion outside the bug's blast radius. The change is structural (transient vs retained), not semantic (reachability gate stays exactly as today).

```python
# packages/kailash-dataflow/src/dataflow/utils/connection.py
async def initialize_pool(self) -> Dict[str, Any]:
    """Verify reachability via a transient adapter; no retained pool.

    Per `rules/dataflow-pool.md` Rule 2, `DataFlow.__init__` (via lazy
    `_ensure_connected`) MUST fail-fast on unreachable databases. The
    existing reachability proof is `await adapter.connect()` succeeding;
    this is preserved. The change: the adapter used to prove reachability
    is now transient (opened, then disconnected) — no long-lived pool is
    retained at `_connection_manager._adapter`. Long-lived pools are
    created per-loop at first user-driven async call via
    `AsyncSQLDatabaseNode._get_adapter()` (DPI-B priority chain).
    """
    factory = AdapterFactory()
    # Use pool_size=1 / max_overflow=0 — minimal cost since we discard immediately
    test_adapter = factory.create_adapter(self.config, pool_size=1, max_overflow=0)
    try:
        await test_adapter.connect()  # SAME reachability gate as today
    except Exception:
        # Cleanup-on-connect-failure: typed swallow only, per zero-tolerance Rule 3
        try:
            await test_adapter.disconnect()
        except Exception:
            pass
        raise
    else:
        await test_adapter.disconnect()
    self._initialized = True
    return {"status": "reachable", "pool_size": 0}
```

The `_connection_manager._adapter` field is no longer assigned by `initialize_pool`. Internal callers that read it must migrate. Cluster-3 + analyst red-team enumerated the call sites within `packages/kailash-dataflow/src/dataflow/`:

1. `transactions.py:387-411` (`TransactionManager._get_adapter`) — fix target, Phase 1.
2. `connection.py:121` (`ConnectionManager.health_check`) — the standalone health check; remove or rewire to open a transient adapter on demand.
3. `connection.py:150-158` (`ConnectionManager.get_connection_stats`) — accessed via `db.get_connection_pool()` walk path; rewire to walk `_PROCESS_POOL_REGISTRY` for entries matching this DataFlow's connection string.
4. `connection.py:228-230` (`ConnectionManager.disconnect`) — close path; remove (no retained pool to close).

Cross-package check (analyst H1): `kailash-ml` references its OWN `ConnectionManager` class (different module), not DataFlow's `_connection_manager._adapter`. Verified via `grep -rn "_connection_manager\._adapter" packages/kailash-*/src/` — zero hits outside `packages/kailash-dataflow/`.

### Phase 3 — Tier-2 regression tests

REVISED after red-team review (analyst H4 + H5 + H6). Two missing tests added; conftest mitigation added.

New tests at `packages/kailash-dataflow/tests/regression/test_issue_835_transaction_cross_loop.py`:

1. **`test_transaction_works_in_fresh_asyncio_run`** — `db = DataFlow(...)` constructed in sync context; `asyncio.run(main)` calls `db.transactions.begin()` and asserts no `Event loop is closed`. Real PostgreSQL.
2. **`test_transaction_works_across_pytest_asyncio_loops`** — two pytest-asyncio function-scoped tests, same `db` fixture (module scope). Each test runs `db.transactions.begin()` on its own loop. Both succeed.
3. **`test_transaction_pool_keyed_per_loop`** — assertion: two loops produce two distinct adapter entries via `db._get_cached_db_node(db_type)._get_adapter()`. Each adapter's `connection_pool._loop` is the loop that requested it.
4. **`test_init_fail_fast_on_unreachable_db_unchanged`** — `DataFlow(database_url="postgresql://nope:5432/none")` raises at `__init__` with the existing reachability error message (verifies `dataflow-pool.md` Rule 2 contract preserved).
5. **`test_transaction_pool_reaped_when_loop_closes`** — open a loop, run a transaction, close the loop; assert the pool entry is GC'd from `_PROCESS_POOL_REGISTRY` (WeakValueDictionary).
6. **`test_transaction_first_db_touch_is_transaction`** (added per analyst H4) — `db = DataFlow(...)` then IMMEDIATELY `async with db.transactions.begin()` with NO prior Express call. Exercises the path where `_ensure_connected` AND the transaction `_get_adapter()` race on the same loop. Asserts no exception and connection pinning works.
7. **`test_execute_raw_outside_async_with_raises_runtime_error`** (added per analyst H5) — `tx = None; async with db.transactions.begin() as t: tx = t` then `await tx.execute_raw(...)` AFTER the scope exits. Asserts the typed-delegate guard at `transactions.py:162` still raises `RuntimeError` (zero-tolerance Rule 3a contract preserved through the per-loop migration).
8. **`test_savepoint_nesting_same_loop_pinning`** (added per dataflow-specialist H3) — outer `begin()` + inner `begin()` on the SAME loop both reach the same per-loop pool, and the inner SAVEPOINT pins the OUTER's connection (via `_active_transaction` ContextVar). Asserts atomic outer-commit / inner-rollback semantics survive the migration.

**Test conftest mitigation (analyst H6):** `packages/kailash-dataflow/tests/regression/conftest.py` adds an autouse fixture for the cross-loop test module:

```python
# tests/regression/conftest.py
@pytest.fixture(autouse=True)
def _aggressive_pool_reaper():
    """Lower idle_timeout for cross-loop tests so pool churn doesn't trip
    `max_pool_count_per_process=100` cap under pytest-xdist parallelism."""
    from kailash.nodes.data.async_sql import set_pool_defaults
    prior = set_pool_defaults(idle_timeout=2)  # aggressive reap
    yield
    set_pool_defaults(idle_timeout=prior)  # restore
```

Plus a stress test:

9. **`test_pool_cap_survives_xdist_loops`** (added per analyst H6) — simulate 50 sequential loops creating + closing transactions; assert `len(_PROCESS_POOL_REGISTRY) <= max_pool_count_per_process` throughout (reaper keeps cap below the limit).

All Tier 2 = real PostgreSQL via Testcontainers. NO mocking per `rules/testing.md`.

**Test-count claim:** 9 tests, count not yet verified by command (per `rules/testing.md` "Verified Numerical Claims" — final count produced by `pytest --collect-only -q tests/regression/test_issue_835_*.py | grep -c '::'` at /implement gate, not at /analyze).

### Phase 4 — Spec updates (same PR; describe shipped behavior only)

REVISED after red-team review (analyst M2). Per `rules/spec-accuracy.md` Rule 5: a spec describes behavior already on `main`. Phase 4 lands in the SAME PR as Phases 1+2+3 — atomic — with prose written in present tense describing the post-merge behavior. The PR is structured so spec edits are committed AFTER the code commits inside the same PR (so `git log -p` history shows code-then-spec ordering, even though they merge as one).

`specs/dataflow-cache.md §12.1` — append (post-merge prose):

```markdown
**Loop affinity.** `db.transactions.begin()` resolves a per-loop asyncpg
pool via `AsyncSQLDatabaseNode._get_adapter()`, which routes through the
DPI-B priority chain (`_shared_pools` → runtime pool → `_PROCESS_POOL_REGISTRY`
→ fallback) using a 5-component key
`loop_id|db_type|connection|pool_size|max_pool_size`. Each event loop receives
its own pool; pools are auto-reaped on loop close via WeakValueDictionary
semantics + the per-loop reaper task documented in §13.4. Calling `begin()`
outside a running loop raises `RuntimeError`. This mirrors the loop-binding
semantics already documented in §12.7 for the sync transaction surface, and
aligns async transactions with the per-loop pool model used by `db.express.*`.
```

`specs/dataflow-cache.md §13.4 Pool Lifecycle Contract (DPI-B / issue #697 + #698)` — append:

```markdown
The async transaction surface (§12.1) participates in the priority chain
through the same `AsyncSQLDatabaseNode._get_adapter()` entry point as `db.express.*`.
The legacy `_connection_manager._adapter` retained-pool model is removed in
this version. Tier-2 regression coverage at
`tests/regression/test_issue_835_transaction_cross_loop.py`.
```

Per `rules/specs-authority.md` Rule 5b sibling-re-derivation:

- `dataflow-express.md` §4 (Express Sync): unaffected; `db.express_sync` still owns its daemon-thread loop and uses `_PROCESS_POOL_REGISTRY` lookups keyed on the daemon loop's ID. No edit.
- `dataflow-core.md` §1.4 (lazy connect): unaffected; `_ensure_connected` still bridges via `async_safe_run` for the reachability proof; what changes is that the proof is now transient (Phase 2) and queries go through per-loop pools (Phase 1). No edit needed because §1.4 doesn't pin the retained-pool implementation detail.
- `dataflow-models.md`: unaffected.

**Cross-SDK note (analyst M3):** this PR does NOT inspect kailash-rs. Per `rules/repo-scope-discipline.md`, cross-SDK work happens in the kailash-rs repo. The cross-SDK companion question (does Tokio's sqlx pool have a similar runtime-binding gap?) is captured as a user-gated follow-up in §"Cross-SDK alignment" below.

## Cross-SDK alignment (out of scope this PR; user-gated follow-up)

The brief tags `cross-sdk` because asyncpg pools' loop-binding constraint is a Python-asyncio property, not a Rust property. `kailash-rs` uses a different runtime (Tokio) where the analogous concern is "is the transaction pool tied to the Tokio runtime that constructed the DataFlow?" — likely true by construction in Rust but worth a separate verification in a kailash-rs session. Per `rules/repo-scope-discipline.md`, cross-SDK work happens in the kailash-rs repo, not from here. Per `rules/upstream-issue-hygiene.md` MUST Rule 1, filing the companion issue requires explicit user approval.

## Risks & edges

See `01-analysis/02-risks-and-edges.md`. Highlights:

- **Sync DDL path (`auto_migrate`)** — runs in a sync context with no running loop. Currently uses `_connection_manager._adapter` for query execution. Migration: use `_run_in_thread_pool`-managed loop with the new per-loop registry, OR keep a separate "sync-DDL adapter" path that opens a transient connection per DDL operation.
- **Pool churn under multi-loop load** — every pytest-asyncio test creates its own loop and gets its own pool. With `max_pool_count_per_process=100` (`async_sql.py:_POOL_DEFAULTS`), tests > 100 loop-pools would hit `PoolExhaustedError`. The DPI-B3 reaper closes idle pools so this is bounded in practice; we may need to lower `idle_timeout` from 300s default for test contexts.
- **DPI-B2 `_POOL_DEFAULTS["max_pool_count_per_process"]`** — already governs total pool count across all paths; bringing transactions onto the same registry means transaction pools count toward the cap. May need to bump default cap if production DataFlow workloads churn loops (uncommon — production runs one loop typically).

## Sharding

Per `rules/autonomous-execution.md` § "Per-Session Capacity Budget":

- **Phase 1** (`_get_adapter` rewrite via `_get_cached_db_node(db_type)._get_adapter()` + `_PoolWrapper` deletion) — ~80 LOC load-bearing (smaller than original because reuse displaces invented helper), 3 invariants (db-type detection, async signature, no-loop error path). One shard.
- **Phase 2** (transient reachability proof + remove `_adapter` retention + migrate 4 callers) — ~80 LOC load-bearing, 3 invariants (preserve `connect()`-based reachability gate, no leaked transient connection on connect-failure, callers migrate atomically). One shard.
- **Phase 3** (Tier 2 regression tests + conftest mitigation) — 9 tests + 1 fixture, ~350 LOC mostly fixture boilerplate. One shard (per Rule 2: "boilerplate scales ~5× further").
- **Phase 4** (spec updates) — ~50 LOC in `specs/dataflow-cache.md`. One shard.

Total: 4 shards, well within budget. All four phases land in ONE PR (atomic — splitting Phase 1 from Phase 2 leaves `_adapter` half-removed; splitting Phase 3 from 1+2 ships the fix without coverage; Phase 4 spec update lands with the code per `rules/specs-authority.md` MUST Rule 5).

**One-PR plan: PR-1 = Phases 1 + 2 + 3 + 4.** ~560 LOC total, 9 invariants. Bounded by feedback loop (Tier 2 tests run during implementation). Within shard budget per Rule 3 (executable feedback loops 3-5× multiplier).

## Revision history

- 2026-05-06 — initial draft
- 2026-05-06 — revised after red-team round (analyst + dataflow-specialist):
  - C1+C3 (phantom helper, key-shape mismatch, three pool registries): replaced invented `_build_pool_key_for_dataflow` path with REUSE of `AsyncSQLDatabaseNode._get_adapter()`. Sub-finding: the original "use `_get_cached_db_node`" reference is broken (`_get_cached_db_node` is referenced at `transaction_nodes.py:59` but never defined). Final disposition: `TransactionManager` constructs and caches a dedicated `AsyncSQLDatabaseNode` whose constructor kwargs match Express's per-model nodes, so all share one per-loop pool entry. Per-key creation lock + DPI-B2 cap + 5-component key shape inherited automatically. The `_get_cached_db_node` reference in `transaction_nodes.py` is a separate latent bug, recorded for follow-up.
  - C2 (file-path ambiguity): all `engine.py:NNNN` citations corrected to `core/engine.py:NNNN` across all analysis docs (the 560-line `dataflow/engine.py` and 10443-line `dataflow/core/engine.py` are distinct files).
  - H2 (`SELECT 1` claim): reconciled — `initialize_pool` does NOT run `SELECT 1` today. The reachability gate is `await adapter.connect()` succeeding. Phase 2 preserves this exactly; no new `SELECT 1` introduced.
  - H3 (concurrency lock): closed automatically by reusing `AsyncSQLDatabaseNode._get_adapter()` which has `_pool_locks` keyed on pool-key.
  - H4+H5+H6 (test gaps): added 4 more tests (first-DB-touch-is-transaction, execute_raw-after-scope-exit, savepoint-nesting-pinning, pool-cap-survives-xdist-loops) and an autouse fixture lowering `idle_timeout` for the test module.
  - M2 (spec ordering): Phase 4 lands in same PR but the commit order inside the PR is code-then-spec; spec prose written in present tense describing post-merge behavior.
  - `_PoolWrapper` deletion (dataflow-specialist H2): explicit in Phase 1.
  - Cross-SDK (analyst M3): explicitly out of scope this PR; user-gated follow-up.

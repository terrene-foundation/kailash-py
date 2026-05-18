# Current Architecture — DataFlow Pool & Transaction Surfaces

Verified by three parallel deep-dive agents (cluster 1: two-pool architecture; cluster 2: daemon-thread loop binding; cluster 3: candidate fix feasibility). All file:line citations are against `main` HEAD `29495b67`.

## 1. The four moving parts

### 1.1 `ConnectionManager` (`packages/kailash-dataflow/src/dataflow/utils/connection.py:39-104`)

Owned by `DataFlow` instance. Holds a single optional `_adapter` (line 39). `initialize_pool()` (line 61-104) builds the adapter via `AdapterFactory().create_adapter(...)` (lines 81-86) and `await self._adapter.connect()` (line 88). For PostgreSQL this delegates to `PostgreSQLAdapter.connect()` at `packages/kailash-dataflow/src/dataflow/adapters/postgresql.py:60-82` which calls `asyncpg.create_pool(**params)`. **The asyncpg pool is loop-bound at this `await` point.**

### 1.2 The lazy-connection bridge (`core/engine.py:1094-1280` + `core/engine.py:1719-1724`)

CORRECTION (mid-analysis re-trace; original text said "during `__init__`" — wrong):

`DataFlow.__init__` does NOT touch the database. Per `specs/dataflow-core.md §1.4` and verified at `core/engine.py:1094`, `_ensure_connected()` is the lazy gate — `__init__` stores config only, all DB resources are deferred to first DB-touching operation.

```python
# core/engine.py:1094 — _ensure_connected() runs once on first DB touch
def _ensure_connected(self) -> None:
    if self._connected:
        return
    with self._connect_lock:
        ...
        # 4. Database connection pool initialization
        self._initialize_database()                             # core/engine.py:1261
        ...
        self._connected = True

# core/engine.py:1719 — _initialize_database (sync method, called from sync _ensure_connected)
def _initialize_database(self):
    if not (self._tdd_mode and self._test_context):
        async_safe_run(self._connection_manager.initialize_pool())   # core/engine.py:1724
```

`_ensure_connected` is itself **synchronous**. It is invoked from BOTH sync code paths (DDL helpers) and async code paths (the user awaits `db.express.list(...)` → AsyncSQLDatabaseNode `_pre_invoke` → `_ensure_connected()` is called in the async stack but is not awaited). The bridge is `async_safe_run` (`packages/kailash-dataflow/src/dataflow/core/async_utils.py:121-271`):

- **No running loop** (sync caller, e.g., `db.express_sync.list(...)` from a CLI script): `asyncio.run(coro)` (lines 177-184) — creates an EPHEMERAL loop, runs the coroutine, **CLOSES the loop**. Pool's `_loop` points at the closed ephemeral loop.
- **Loop running** (the typical bug case — async caller awaits `db.express.list(...)` or `db.transactions.begin()`): `_run_in_thread_pool(coro)` (line 195) — creates a NEW loop in a worker thread, runs the coro, **closes that loop at line 248**. Pool's `_loop` points at the closed worker-thread loop.

Either path, the pool created at first DB touch is bound to a loop that no longer exists by the time any subsequent operation needs the pool. The ephemeral/worker loop dies the moment `_initialize_database` returns.

**Why Express works anyway:** `db.express.list` does NOT use this `_connection_manager._adapter` pool. It goes through `AsyncSQLDatabaseNode` which has its OWN per-loop pool registry (`_PROCESS_POOL_REGISTRY`). The first `await db.express.list(...)` triggers `_ensure_connected` (which builds the broken `_adapter`) AND independently creates a per-loop pool in `_PROCESS_POOL_REGISTRY` keyed on the user's running loop. The Express path uses the per-loop entry; `_adapter` is built but unused. Transactions are the only surface that consumes `_adapter` directly, which is why only transactions break.

### 1.3 `TransactionManager` (`packages/kailash-dataflow/src/dataflow/features/transactions.py:196-411`)

Async surface, exposed as `db.transactions`. `_get_adapter()` (line 387-411) resolution order:

1. `self.dataflow._connection_manager._adapter` — the throwaway-loop pool from §1.2. **Always taken in production.**
2. `self.dataflow._adapter`/`_db_adapter`/`adapter` — no production setter exists (cluster 3 verified).
3. `self.dataflow._cached_async_node._pool` (wrapped in `_PoolWrapper`) — `_cached_async_node` has no production setter (cluster 3 verified). Dead branch.

`begin()` (line 242-336) calls `await adapter.connection_pool.acquire()` (line 290) and `release(conn)` (line 336). These schedule callbacks on `pool._loop` — the closed throwaway loop. Result: `RuntimeError: Event loop is closed`.

### 1.4 The Express / Sync surfaces (NOT broken — for contrast)

- **Async Express** (`db.express.list/create/...`, `packages/kailash-dataflow/src/dataflow/features/express.py:75-226`): routes through `self._db._nodes[...]`, the auto-generated CRUD nodes derived from `AsyncSQLDatabaseNode`. Those nodes use `_PROCESS_POOL_REGISTRY` (`src/kailash/nodes/data/async_sql.py:2655-2668`) — a `WeakValueDictionary` keyed per `(connection_string, id(running_loop))`. **Each event loop gets its own pool**, GC'd via `WeakValueDictionary` semantics when the loop closes, plus an explicit `_idle_pool_reaper_loop` task per loop (`async_sql.py:2755-2870`). This is why the bug's repro shows `await db.express.list(...)` works.
- **Sync Express** (`db.express_sync`, `SyncExpress` at `express.py:1871-1917`): owns a private daemon-thread persistent loop (`express.py:1899-1906`); every async call submits via `asyncio.run_coroutine_threadsafe(coro, self._loop)`. The pool is whatever pool the Express call uses — which (via `_PROCESS_POOL_REGISTRY`) is created lazily on the daemon-thread loop on first access. Stable.
- **Sync Transactions** (`db.transactions_sync`, `SyncTransactionManager` at `transactions.py:685-780`): owns a private daemon-thread persistent loop (line 741-747). **Does NOT use the engine pool at all** — `_open_connection_for_url` (line 467-491) opens a fresh `asyncpg.connect()` per `begin()` on its own BG loop and closes it on exit. Stable.

## 2. Why Express works and Transactions doesn't

| Surface                           | Pool source                                   | Loop affinity                         | Cross-loop reuse                              |
| --------------------------------- | --------------------------------------------- | ------------------------------------- | --------------------------------------------- |
| `db.express.list/...` (async)     | `AsyncSQLDatabaseNode._PROCESS_POOL_REGISTRY` | per-loop, `id(running_loop)` keyed    | ✅ creates new pool per loop                  |
| `db.express_sync.list/...`        | Same registry, daemon-thread loop             | one loop (the daemon's)               | ✅ pool tied to daemon's persistent loop      |
| `db.transactions.begin()` (async) | `ConnectionManager._adapter.connection_pool`  | bound to whatever loop ran `__init__` | ❌ pool's loop is closed throwaway            |
| `db.transactions_sync.begin()`    | Fresh `asyncpg.connect()` per `begin()`       | daemon-thread persistent loop         | ✅ no pool reuse — opens connection per begin |

The async transaction surface is the only one that reuses a single pool object across loops — and that pool's loop is dead from the moment `__init__` returns.

## 3. Cross-references in current specs

`specs/dataflow-cache.md`:

- §12.1 (`db.transactions.begin()` async surface): NO mention of which pool it uses or loop-affinity constraints.
- §12.7 (sync surface): explicitly documents "asyncpg connections are loop-bound; sharing the DataFlow pool across the host loop and the BG loop produces `RuntimeError: Future ... attached to a different loop`" — and explains why the sync surface uses fresh connections per `begin()` to avoid this.
- §13.4 "Pool Lifecycle Contract (DPI-B / issue #697 + #698)": pins `_PROCESS_POOL_REGISTRY` semantics for the Express path; silent on `_connection_manager._adapter`.

The spec ALREADY KNOWS the loop-binding constraint exists. The async transaction surface is silently exempt from the protections every other surface enforces.

## 4. Test evidence

- `packages/kailash-dataflow/tests/regression/test_issue_707_transaction_pins_connection.py` and `test_issue_711_transactions_sync.py` exist for `TransactionManager.begin()` / `transactions_sync.begin()`. They assert connection-pinning semantics, not pool-loop affinity. The current bug is invisible to these tests because they happen to run in the same loop that constructed `DataFlow`.
- `tests/regression/test_issue_713_module_import_then_async_ddl.py` (CHANGELOG 2.6.0) verifies that module-scope `db = DataFlow(...)` followed by later `await db.create_tables_async()` works — covers DDL but does NOT exercise transactions in a loop different from `__init__`'s.

No regression coverage exists for the cross-loop transaction case.

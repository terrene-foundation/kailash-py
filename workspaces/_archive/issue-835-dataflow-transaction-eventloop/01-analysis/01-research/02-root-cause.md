# Root Cause — Where The Pool's Loop Comes From

## Trace, end to end

```
User code (typical async caller, e.g., bug repro):
    db = DataFlow(database_url=...)
        ↓ __init__ stores config only; NO db touch (core/engine.py:1094 + specs/dataflow-core.md §1.4)

    asyncio.run(main()):                                     # caller's loop alive
        await db.express.list("Probe", ...)                  # FIRST DB-touching op
            ↓ AsyncSQLDatabaseNode pre-invoke calls _ensure_connected (sync)
        DataFlow._ensure_connected()                         # core/engine.py:1094
            ↓ line 1261:
        DataFlow._initialize_database()                      # core/engine.py:1719-1724
            ↓ line 1724:
        async_safe_run(self._connection_manager.initialize_pool())
            ↓ async_utils.py:121-271 — caller's loop IS running
        _run_in_thread_pool(coro)                            # async_utils.py:195-248
            ├ creates new loop in worker thread             # line 227
            ├ asyncio.set_event_loop(worker_loop)            # line 228
            ├ runs initialize_pool() → asyncpg.create_pool() — pool._loop = worker_loop
            └ worker_loop.close()                            # line 248
            ← returns control to caller's loop with pool._loop already closed.

        ↓ Express path independently:
        AsyncSQLDatabaseNode resolves _PROCESS_POOL_REGISTRY[caller_loop_id]
            ├ cache miss; creates SECOND pool on caller's loop
            └ "express ok" — uses the per-loop pool, NOT _connection_manager._adapter

        ↓ User awaits transaction:
        async with db.transactions.begin() as tx:            # transactions.py:242-336
            ↓
        adapter = self._get_adapter()                        # transactions.py:387-411
            # returns _connection_manager._adapter (the broken one — pool._loop closed)
            ↓
        conn = await adapter.connection_pool.acquire()       # transactions.py:290
            ↓
        asyncpg/pool.py: schedules callbacks on pool._loop  ← worker_loop, closed
            ↓
        pool._loop.call_later(...)                           # asyncio/base_events.py:799
            ↓
        self._check_closed() — RuntimeError("Event loop is closed")
```

## The exact mechanism

`asyncpg.Pool` internally caches the loop it was created on (`pool._loop`). All pool operations (`acquire`, `release`, `close`, internal release-callbacks) schedule asyncio handles on that loop. When `pool._loop` is closed, asyncpg's `_check_closed()` guard raises `RuntimeError: Event loop is closed`.

The bug isn't "wrong loop selected at acquire time" — it's "pool was created on a loop that no longer exists." `_ensure_connected()` is sync, called from inside the user's running loop, and bridges to async via `async_safe_run`. Because the user's loop is RUNNING, `async_safe_run` takes the thread-pool path, builds a worker-thread loop, runs `initialize_pool()` on it, then closes the worker loop on return. The asyncpg pool is permanently bound to that closed worker loop. Subsequent `db.transactions.begin()` calls hit `_check_closed()`.

The sync-CLI variant of the bug uses `asyncio.run()` (no running loop case) — pool bound to the ephemeral asyncio.run loop, which closes when the run returns. Same outcome via a different sub-path.

## Why the brief's framing was wrong

The brief at issue #835 claimed:

> 2. **PostgreSQLAdapter pool** (used by `db.transactions.*`) — created via `dataflow.utils.connection.initialize_pool` running inside the daemon-thread persistent loop that backs `DataFlowExpressSync`. The pool's `_loop` reference is the daemon thread's loop, not the caller's.

**This is structurally false.** Verified by all three deep-dive agents AND a follow-up trace of `_ensure_connected` (`core/engine.py:1094-1280`) that corrected my own first-pass claim that `_initialize_database` runs at `__init__` time. It does not — it runs at first DB touch via the lazy gate. The throwaway loop is the `async_safe_run` worker-thread loop, fired during the user's running loop, NOT a daemon thread loop and NOT an `__init__`-time event:

- `initialize_pool` is invoked from `DataFlow.__init__` via `async_safe_run`, NOT from any daemon-thread loop.
- `SyncExpress` and `SyncTransactionManager` daemon threads are constructed lazily on first access to `db.express_sync` / `db.transactions_sync`. If user code in the bug repro never accesses these properties, **no daemon thread exists**.
- `db.transactions_sync` does NOT use the engine pool at all — it opens a fresh `asyncpg.connect()` per `begin()` on its own BG loop. The brief's "daemon-thread loop owns the pool" attribution applies to neither sync surface.

The brief's symptom (`pool._loop.is_closed() == True`, `RuntimeError: Event loop is closed`) is REAL. The brief's causal model (`pool._loop is daemon's loop`, daemon thread's loop happens to be closed) is wrong. The real causal model: `pool._loop` is the throwaway loop `async_safe_run` used at init time.

This matters because the brief's three proposed fixes (A: re-order `_get_adapter`; B: lazy bind in `initialize_pool`; C: opt-in `DataFlowExpressSync`) all target the wrong surfaces. Cluster 3 confirmed all three are either no-ops, blocked by existing rules, or address the wrong code path. See `03-brief-corrections.md`.

## The structural defect

A single asyncpg pool cached at object-construction time, used across N event loops, **cannot work** — asyncpg pools are loop-bound by design. The Express path solves this with `_PROCESS_POOL_REGISTRY` (`src/kailash/nodes/data/async_sql.py:2655-2670`), a `WeakValueDictionary` keyed per `(connection_string, id(running_loop))` with a per-loop reaper task. **The async transaction path bypasses this registry and uses the broken `_connection_manager._adapter` instead.**

The fix is to bring the async transaction surface into the same per-loop discipline the Express path already enforces. See `02-plans/01-architecture.md`.

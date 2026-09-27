---
type: DISCOVERY
date: 2026-05-15
created_at: 2026-05-15T20:57:22Z
author: agent
project: kailash-py
topic: _Py_Finalize hang root cause — aiosqlite Connection worker threads are non-daemon
phase: implement
tags: [issue-1010, issue-1002, dataflow, aiosqlite, ci-hang, forensics]
issue: 1010
ci_run: https://github.com/terrene-foundation/kailash-py/actions/runs/25884071323/job/76071101330
branch: debug/issue-1010-phase-a-diagnostics
---

## Forest

Issue #1010 Phase A — capture forensic evidence of the post-pytest-summary `_Py_Finalize → wait_for_thread_shutdown` hang that PR #1008 reproduced and blocked Shard 4b's setsid removal.

## Capture method

- Debug branch `debug/issue-1010-phase-a-diagnostics` added a session-scoped pytest fixture in `packages/kailash-dataflow/tests/conftest.py` (env-gated `DATAFLOW_DIAGNOSE_FINALIZE=1`).
- Fixture arms `faulthandler.dump_traceback_later(60, repeat=True)` at session-finish, with output routed to `/tmp/issue-1010-diagnostic.log` (line-buffered, survives SIGKILL).
- CI step runs pytest WITHOUT setsid wrapper, `-s` disables pytest capture, 24-min step timeout.
- `if: always()` print step + upload-artifact step preserve the file across step-cancel.

## Timeline (CI run 25884071323, job 76071101330)

| Wall-clock          | Event                                                                                   |
| ------------------- | --------------------------------------------------------------------------------------- |
| 20:33:15            | Test session start, fixture activates banner                                            |
| 20:34:02            | Session-finish, `dump_traceback_later(60)` armed                                        |
| 20:34:03            | Pytest summary: `3045 passed, 98 skipped, 46 warnings in 54.13s`                        |
| 20:34:03 → 20:57:21 | **~23 min hang in `_Py_Finalize`** — watchdog fires every 60s, ~22 stack dumps captured |
| 20:57:21            | Step hits 24-min step-timeout, job cancelled                                            |
| 20:57:22            | Print step emits captured file to job log                                               |

## Thread enumeration at hang (12 threads total)

Unique thread IDs from faulthandler dump:

| Thread ID        | Stack top                                        | Class                | Daemon?        | Blocks \_shutdown?   |
| ---------------- | ------------------------------------------------ | -------------------- | -------------- | -------------------- |
| `0x...28ba5ab80` | `threading.py:1590 _shutdown`                    | **Main thread**      | n/a            | (it IS the shutdown) |
| `0x...233fff6c0` | `aiosqlite/core.py:59 _connection_worker_thread` | aiosqlite worker     | **NO**         | **YES**              |
| `0x...23dffd6c0` | `aiosqlite/core.py:59 _connection_worker_thread` | aiosqlite worker     | **NO**         | **YES**              |
| `0x...245ffd6c0` | `pool_monitor.py:182 _monitor_loop`              | DataFlow PoolMonitor | YES (line 123) | NO                   |
| `0x...23ffff6c0` | `pool_monitor.py:182 _monitor_loop`              | DataFlow PoolMonitor | YES            | NO                   |
| `0x...271bfd6c0` | `pool_monitor.py:182 _monitor_loop`              | DataFlow PoolMonitor | YES            | NO                   |
| `0x...247fff6c0` | `pool_monitor.py:182 _monitor_loop`              | DataFlow PoolMonitor | YES            | NO                   |
| `0x...26affe6c0` | `pool_monitor.py:182 _monitor_loop`              | DataFlow PoolMonitor | YES            | NO                   |
| `0x...269ffd6c0` | `asyncio/base_events.py:608 run_forever`         | asyncio loop thread  | likely YES     | likely NO            |
| `0x...255ffd6c0` | `asyncio/base_events.py:608 run_forever`         | asyncio loop thread  | likely YES     | likely NO            |
| `0x...256ffe6c0` | `asyncio/base_events.py:608 run_forever`         | asyncio loop thread  | likely YES     | likely NO            |
| `0x...257fff6c0` | `asyncio/base_events.py:608 run_forever`         | asyncio loop thread  | likely YES     | likely NO            |

## Root cause

**aiosqlite `Connection._thread` is constructed without `daemon=True`**:

```python
# .venv/lib/python3.11/site-packages/aiosqlite/core.py:90
self._thread = Thread(target=_connection_worker_thread, args=(self._tx,))
```

When `Thread()` is invoked with no `daemon=` kwarg, Python defaults `daemon=False` (inherited from the creator thread's daemon flag; the creator is the test's main thread which is non-daemon). The worker thread:

1. Sits blocked on `tx.get()` (queue read) at `_connection_worker_thread` line 59
2. Has no way to exit unless someone enqueues `None` or the `Connection.close()` is called explicitly
3. Counts as a live non-daemon thread, so `threading._shutdown()` waits for it indefinitely

## Why Shards 1–3's cleanup doesn't help

Shards 1–3 closed `DataFlow(...)` instances and the `cleanup_dataflow_connection_pools` autouse fixture (conftest.py:929) clears `AsyncSQLDatabaseNode._shared_pools` after each test. But the SQLite branch of that fixture (lines 985–988) handles loop-closed by:

```python
if loop_is_closed:
    # SQLite - can disconnect synchronously
    pass  # Will be cleared from cache below
```

The `pass` is the bug at this layer. Dropping the adapter from the dict releases its Python reference but does NOT close the underlying `aiosqlite.Connection`. The aiosqlite worker thread keeps running forever, waiting for `tx.get()`.

## Connection between dump findings and issue #1010 hypotheses

- **H1** (LocalRuntime `__del__` calls `close()`): not load-bearing for the hang. LocalRuntime's `__del__` deadlock is a real bug per `patterns.md § Async Resource Cleanup`, but it's an orthogonal failure mode. None of the 12 hung threads come from LocalRuntime.
- **H2** (SyncExpress orphan daemon thread): the PoolMonitor threads ARE daemon=True, so they don't block `_shutdown()`. False alarm at the H2 layer — the actual SyncExpress orphan needs separate verification.
- **H3** (`AsyncSQLDatabaseNode._shared_pools` not cleared): the dump confirms the pools-clear pattern is close to the root cause, but goes ONE LAYER deeper: clearing the dict drops adapter references without closing the aiosqlite Connection objects inside. **Phase B fix targets the close path, not the clear path.**

## Recommended Phase B fix (single shard)

Modify `cleanup_dataflow_connection_pools` SQLite branch to synchronously close the aiosqlite Connection BEFORE clearing the cache entry — using a fresh event loop if the per-test loop is closed:

```python
elif hasattr(adapter, "disconnect"):
    if loop_is_closed:
        # SQLite — spin a fresh loop to run async disconnect to completion
        # so the aiosqlite worker thread receives None on its tx queue
        # and exits cleanly.
        cleanup_loop = asyncio.new_event_loop()
        try:
            cleanup_loop.run_until_complete(adapter.disconnect())
        finally:
            cleanup_loop.close()
    else:
        await adapter.disconnect()
```

Sibling fix at the engine layer (Shard 2 invariant 10 territory): `DataFlow.close()` / engine `close()` MUST close cached `AsyncSQLDatabaseNode` instances' adapters, not just the workflow runtime. See `journal/0004-DISCOVERY-asyncsqldatabasenode-del-leak-via-sync-close.md`.

## Acceptance criteria for Phase B

1. After `cleanup_dataflow_connection_pools` runs on a SQLite-using test, `threading.enumerate()` must NOT contain any `_connection_worker_thread` frames.
2. Phase A diagnostic CI step on the post-fix branch MUST exit cleanly within 90s of pytest summary (no `_shutdown()` wait).
3. Production setsid wrapper at `unified-ci.yml:251-289` can then be removed (Shard 4b re-opens).

## Filed against issue

Findings appended to issue #1010 Phase A — the H3 hypothesis is the closest match but needs refinement to target the Connection-close layer rather than the pool-clear layer.

## Forensic artifacts

- CI run job: https://github.com/terrene-foundation/kailash-py/actions/runs/25884071323/job/76071101330
- Diagnostic file artifact: `issue-1010-phase-a-diagnostic` (downloadable via `gh run download 25884071323 -n issue-1010-phase-a-diagnostic`)
- Conftest fixture: `packages/kailash-dataflow/tests/conftest.py` § "Issue #1010 Phase A — \_Py_Finalize forensic capture"
- Debug branch: `debug/issue-1010-phase-a-diagnostics` (never to be merged; revert wiring before any rebase to main)

## For Discussion

1. **Counterfactual**: had Phase A diagnostic wiring shipped without `-s` (pytest capture disable) and the on-disk file route, would the original H3 hypothesis ("`_shared_pools` not cleared") have been close enough? Iteration 1 of Phase A wiring captured 0 diagnostic output because pytest's `--capture=fd` ate every fixture stderr write — that exact failure mode would have left H3 as the canonical theory and led to a fix one layer too high (clearing the dict instead of closing the Connections inside it).
2. **Why did the original `cleanup_dataflow_connection_pools` SQLite branch use `pass # Will be cleared from cache below`?** Reading the comment, the implicit assumption is that dropping the Python reference lets GC + `__del__` close the aiosqlite Connection. aiosqlite's `__del__` does NOT signal the worker thread's tx queue — it only does a synchronous SQLite close of the underlying connection. Did the original author validate against `threading.enumerate()` post-test, or assume reference-drop was sufficient? Evidence: the load-bearing primitive in the comment is `cache.clear()`, which doesn't touch threads at all.
3. **Should we file an upstream aiosqlite issue to default the worker thread to `daemon=True`?** The fix is two characters (`, daemon=True` on `aiosqlite/core.py:90`). aiosqlite ships in many downstream packages; any consumer that fails to call `.close()` leaks a non-daemon thread. Per `rules/upstream-issue-hygiene.md` this is human-gated — but it's a textbook stdlib hygiene improvement.

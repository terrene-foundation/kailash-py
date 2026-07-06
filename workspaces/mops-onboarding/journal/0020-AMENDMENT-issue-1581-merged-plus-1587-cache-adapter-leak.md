# 0020 — AMENDMENT: #1581 merged (PR #1586) + #1587 cache-adapter leak discovered & fixed

**Date:** 2026-07-06 (session 5)
**Type:** AMENDMENT (extends 0019 — merge outcome + adjacent discovery)
**Relates to:** 0019 (#1581 convergence)
**Issues:** #1581 (merged), #1587 (new, cache-adapter leak)
**Status:** #1581 MERGED to main (merge commit `02b1ca89b`); #1587 PR open, CI running; release pending (user holds PyPI timing).

## #1586 (#1581) — CI blocker found and fixed, then merged

On session start, PR #1586 CI showed one real failure (both duplicate runs):
`test_issue_1560_create_retry_node_leak.py::test_retry_site_wraps_async_run_in_cleanup`.

Root cause: the #1560 **source-pin** asserted the throwaway-node `cleanup()` lived
within a fixed 2600-char window from the `PARAM $11 FIX` anchor. #1581 inserted a
~40-line transaction-scope branch **above** the fresh-node path (in-scope retries
now run on the POOLED node, which the pool cleans up), sliding
`await sql_node.cleanup()` to offset 3626 — past the window. The #1560 invariant
itself was **intact**: the throwaway `AsyncSQLDatabaseNode` is created ONLY on the
no-scope path and is still wrapped in `try/finally: cleanup()`.

Fix (commit `b21e54f04`): re-anchor the source-pin on the **fresh-node construction
site** (`sql_node = AsyncSQLDatabaseNode(`) instead of a fixed char window, so a
legitimate scope-branch insertion above it cannot slide the cleanup out of range.
Re-pushed → full matrix (Py3.11–3.14 + DataFlow infra + PACT) green on head
`b21e54f04` → admin-merged (`02b1ca89b`), branch deleted.

## #1587 — pre-existing cache-adapter leak (adjacent discovery, separate bug class)

While running the full infra-free regression gate locally, a DIFFERENT test failed:
`test_dataflow_close_async_closes_cleanly` — `ResourceWarning: AsyncRedisCacheAdapter
not closed` after `close_async()`. Proven **pre-existing on main** (the only engine.py
change in #1581 was the savepoint-node registration; `git diff 1473b23ad HEAD` confirms).

Root cause: `DataFlowExpress.__init__` eagerly auto-detects a cache backend; when Redis
is reachable that is an `AsyncRedisCacheAdapter` owning a `ThreadPoolExecutor`. Neither
`DataFlow.close()` nor `close_async()` tore it down → the executor's worker threads leak
on every documented cleanup path (FastAPI lifespan, async fixture). **Invisible on
`[dev]`-only CI** (no Redis → in-memory fallback → no executor), surfacing only where
Redis is up — which is why #1586 CI stayed green.

Fix (PR #1587, commit `a9895804e`, off main):

- `AsyncRedisCacheAdapter` gains a sync `close()` sibling to `close_async()` (idempotent
  executor shutdown; safe on the blocking path).
- `DataFlowExpress` gains `close()`/`close_async()` closing `_cache_manager`
  (getattr-guarded → in-memory fallback no-ops).
- Both `DataFlow` close paths tear down the async Express instance AND the engine-level
  `_cache_integration` adapter.
- Regression `test_dataflow_close_cache_adapter_leak.py`: **deterministic** (recording
  cache-manager, no Redis dependency) pins the close wiring on both paths — a
  warning-based test would pass vacuously on a `[dev]`-only runner.

## Process incident — errant `git stash pop` (recovered, no loss)

A `git stash push -- <path>` issued from inside `packages/kailash-dataflow/` doubled the
path and failed to create a stash; the follow-up `git stash pop` then applied an
UNRELATED pre-existing 1654-file "release-prep" stash (`stash@{0}`) onto the tree,
polluting ~hundreds of files with 2 merge conflicts. Recovery was lossless: the stash
was **preserved** (the conflicted pop did not drop it), my 4 real files were backed up
to `/tmp`, and `git checkout HEAD -- .` restored the tree to origin/main before
reapplying the 4 files. **Lesson:** never run `git stash` pathspecs from a subdirectory
without absolute/repo-relative paths; verify no pre-existing stash before any `pop`.

## Release scope (next)

- **kailash** 2.45.4 → 2.45.5 — `async_sql.py` (#1580 + #1581).
- **kailash-dataflow** 2.13.20 → 2.13.21 — #1581 (nodes.py/engine.py/transaction_nodes.py)
  - #1587 (async_redis_adapter.py/engine.py/express.py) once #1587 merges.

Re-derive both at `/release`; user holds PyPI timing.

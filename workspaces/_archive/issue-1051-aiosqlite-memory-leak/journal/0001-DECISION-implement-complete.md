# 0001 — DECISION: #1051 /implement complete (multi-round, instrumented)

**Date:** 2026-05-18
**Issue:** #1051 (bug, cross-sdk) — aiosqlite :memory: Connection leak
**Commit:** `3093c5e41` on `fix/issue-1051-aiosqlite-memory-connection-leak`
**Phase:** /implement → /redteam

## Outcome

Leak fully closed: instrumented survivor count **3/4 → 1 → 0** for both
`DataFlow` and `ProtectedDataFlow` `sqlite:///:memory:`. Regression: 3 passed,
0 aiosqlite survivors, 0 warnings (incl. zero DeprecationWarning — test uses
`with LocalRuntime()`). Adjacent #1002/#1010/#1045 SQLite regressions green
(27 passed). Single-path dataflow collection clean (0 errors — the earlier
"5 errors" was a two-path command artifact, proven by deterministic re-run).

## Five coordinated changes (2 source files, 1 new test)

`src/kailash/nodes/data/async_sql.py` (Shard 1 — A+B+C):

- **A** `SQLiteAdapter._get_connection()` reuses one tracked `self._connection`
  for `:memory:`; `disconnect()` awaits-closes it.
- **B** `ProductionSQLiteAdapter.disconnect()` `try/finally: await
super().disconnect()` (was short-circuiting on `_enterprise_pool`).
- **C** `AsyncSQLDatabaseNode._owned_adapters` list; `_create_adapter()`
  appends; `cleanup()` disconnects all (was: only last `self._adapter`).

`packages/kailash-dataflow/src/dataflow/core/engine.py` (Shard 2 — D+E):

- **D** `AsyncSQLConnectionWrapper.execute()` closes the per-execute node in
  a `finally`.
- **E (keystone)** close()/close_async() cached-node teardown resolved
  `getattr(cleanup) or getattr(close)` — the pre-fix `hasattr(node,"close")`
  was always False (node teardown is `cleanup()`; `close` is on
  `EnterpriseConnectionPool`), so the teardown + C's `_owned_adapters`
  disconnect had been a silent no-op since #1002. Stale comment corrected.

## Multi-round process note (capacity-budget honesty)

Original 1-shard estimate (specialist) was wrong — bug was multi-sited
beyond two expert analyses. Took 3 instrumented specialist passes
(`a97b28af3f9ffe822`): pass-1 designed A+B (insufficient, 4-5 leak);
pass-2 designed C+D + 2-shard split (3/4→1); pass-3 found the E keystone
(`close`/`cleanup` name mismatch, 1→0). User-gated at the budget overrun
(chose "one more instrumentation pass"). Bug D's guard had the SAME
name-mismatch defect as E — fixed together. Receipt: this entry + the
3 specialist task transcripts.

## Disposition for /redteam + release

- /redteam: parallel reviewer + security-reviewer (high blast radius —
  core SQLiteAdapter + node lifecycle + engine close paths).
- Release: core `kailash` SDK + `kailash-dataflow` source change → a
  `kailash`/`kailash-dataflow` PyPI release IS warranted (real production
  fix, ships in wheels). Surface release decision to user at release time
  (do NOT auto-publish).
- Cross-SDK: kailash-rs SQLite-teardown dispatch name-mismatch audit —
  user files from a kailash-rs session (repo-scope-discipline).

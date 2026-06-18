# #1051 — Architecture Plan (dataflow-specialist authoritative, reproduce-receipted)

## Root cause (confirmed, reproduced deterministically)

NOT in `engine.py` (issue hypothesis was off). Leak is core SDK
`src/kailash/nodes/data/async_sql.py` `SQLiteAdapter`:

- `_get_connection()` (:1696-1703) creates a **fresh** `aiosqlite.connect()`
  every call. For `:memory:`, every `execute()`/`execute_many()`/
  `begin_transaction()` call (:1773, :1853, :1881) gets a NEW connection,
  used once, **never closed**.
- `disconnect()` (:1705-1709) closes `self._pool` only — which is `None`
  for `:memory:` by design. The untracked per-query connections survive to
  GC → `aiosqlite.Connection.__del__` emits the ResourceWarning.
- The code's OWN intent is one shared persistent `:memory:` connection
  ("Fallback: shared connection for memory databases", transaction paths
  "Don't close shared memory connections"). `self._connection = None`
  (:1590) is the abandoned tracking slot — never assigned. The fix
  _completes the intended design_.

Reproduce receipt: dataflow-specialist task `a97b28af3f9ffe822` — 3 aiosqlite
Connections leak per `DataFlow(:memory:)`+workflow+`close()` under
`-W error::ResourceWarning`. `ProtectedDataFlow` lives at
`dataflow.core.protected_engine.ProtectedDataFlow` (issue's import was wrong).

## Fix (one shard, ~25 LOC, 5 invariants, `async_sql.py` only)

| Change | Location                       | What                                                                                                                                                 |
| ------ | ------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1      | `_get_connection()` :1696-1703 | For `:memory:`: lazily create + cache `self._connection`, reuse it; non-`:memory:` path unchanged (per-query create, caller closes via `async with`) |
| 2      | `disconnect()` :1705-1709      | After pool close, if `self._connection` is not None: `await self._connection.close()`; set `None` (try/finally)                                      |

`engine.py`: **no change** (its `_async_sql_node_cache`/`_memory_connection`
teardown already correct; it calls `node.close()`→`disconnect()` which now
owns the memory conn). Transaction paths: no change (already "don't close
shared memory connections"; `disconnect()` now owns lifecycle). No `__del__`
change (respects `patterns.md` deadlock origin).

Invariants: (1) memory-conn reuse, (2) disconnect closes+nulls it,
(3) non-memory path unchanged, (4) txn paths still don't double-close,
(5) no `__del__` touch.

Incidental: Change 1 also makes all `:memory:` queries on one adapter share
one connection → fixes a correlated `no such table` single-adapter symptom.
Defensible (same design completion, within the 5 invariants); scope stays
"the leak" — not chasing the broader multi-adapter table-visibility issue.

## Tier-2 regression (no mocking)

`packages/kailash-dataflow/tests/regression/test_issue_1051_memory_connection_leak.py`,
`@pytest.mark.regression`. Real `ProtectedDataFlow("sqlite:///:memory:")` +
real `runtime.execute()` + `db.close(); del db; gc.collect()` under
`-W error::ResourceWarning`; structural assertion: zero live
`aiosqlite.core.Connection` in `gc.get_objects()` (probe-driven Rule 3
structural, not lexical). Sibling test for plain `DataFlow`. This is the
assertion #1045's close() regression test deliberately omitted as
out-of-scope (issue AC).

## Cross-SDK (recommendation only — repo-scope-discipline)

File a `cross-sdk` kailash-rs issue post-merge: audit Rust DataFlow SQLite
`:memory:` teardown for the same per-query-leak class. NOT inspected/filed
from this session (user files from a kailash-rs session).

## Human gates

1. Plan (this doc) — real bug, precise small fix, reproduce-receipted →
   proceed under `/autonomize`.
2. Release: core `kailash` SDK change → may warrant a `kailash` release —
   surface to user at release time (do not auto-publish PyPI).
3. kailash-rs cross-ref filing — user's action, surfaced not executed.

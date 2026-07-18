# 0019 — DECISION: #1581 CRUD transaction-awareness — implemented + redteam-CONVERGED

**Date:** 2026-07-06 (session 4)
**Type:** DECISION (implementation + validation outcome)
**Issue:** #1581 — generated DataFlow CRUD nodes not transaction-aware
**Status:** SHIPPED to working tree, redteam-converged (2 consecutive clean rounds). NOT yet PR'd (awaiting user authorization — BUILD-repo shared-state gate).

## What was wrong (#1581)

Generated DataFlow CRUD nodes ran every statement on their own cached
`AsyncSQLDatabaseNode` in `transaction_mode="auto"` (per-statement autocommit).
Inside a `TransactionScopeNode` workflow, a CRUD write committed independently
and **survived a later `TransactionRollbackNode`** — a silent data-integrity
violation. The `transaction_mode="auto"` kwarg at the 10 call sites was INERT
(`async_run` reads it from config at init, never from inputs).

## The fix (single-record CRUD)

- **Core `src/kailash/nodes/data/async_sql.py`** — `_AdapterTransactionScope`
  gained a `.transaction` property (raw txn handle). `AsyncSQLDatabaseNode.async_run`
  reads `inputs.get("transaction")`, threaded through `_execute_with_retry` →
  `_execute_with_transaction` where a new leading `if transaction is not None:`
  borrow-don't-own branch runs `adapter.execute(..., transaction=...)` with NO
  begin/commit/rollback (scope owns lifecycle). Same for the batch path
  (`execute_many_async` → `_execute_many_with_transaction`). Param-threaded, NOT
  instance-state mutation (the cached node is shared across ops — mutating
  `_active_transaction` would leak the scope).
- **DataFlow `packages/kailash-dataflow/src/dataflow/core/nodes.py`** —
  module-level `_run_sql_in_scope(node, sql_node, **kw)` reads `active_transaction`
  off workflow context and injects `scope.transaction`. All 10 CRUD sites
  (create/read/update/delete/list/count/upsert + mysql-precheck + readback)
  routed through it. **Fail-closed:** an active scope with no `.transaction`
  handle raises `NodeExecutionError` (never silent auto-commit). The PG `$11`
  param-type retry fallback fixed: when a scope is active the `$11::integer`
  retry runs on the POOLED node (joins the scope) instead of a fresh non-pooled
  node that escaped it.
- **`engine.py`** — registered the previously-orphaned `TransactionSavepointNode`
  - `TransactionRollbackToSavepointNode` (defined + exported but never
    registered → unreachable by any workflow).
- **`transaction_nodes.py`** — savepoint-name validation `re.match(...$)` →
  `re.fullmatch(...)` (newly load-bearing once the nodes are reachable; `$`
  accepted a trailing newline).

## Scoping questions (answered under /autonomize, with evidence)

1. **Reads join too?** YES — `_run_sql_in_scope` covers LIST/READ/COUNT →
   read-your-writes inside the scope (verified AC3).
2. **PG `$11` retry fresh-node escape?** MUST-handle — fixed (pooled node when
   scope active).
3. **Bulk symmetric plumbing?** Core `execute_many_async(transaction=...)` added;
   the DataFlow bulk path is a SEPARATE shard (see #1585).

## Redteam convergence (2 clean rounds)

- **Round 1** (3 parallel: reviewer + security-reviewer + dataflow-specialist):
  single-record fix VERIFIED correct+complete (no missed sites, no instance
  mutation, borrow-branch correct, connection identity sound, tenant isolation
  preserved). Findings: **HIGH** bulk ops bypass the scope; **LOW×3** (silent
  auto-commit fallback, savepoint regex trailing-newline, engine comment
  over-claim). LOWs fixed in-shard; bulk → #1585.
- **Round 2** (reviewer + dataflow-specialist): ROUND 2 CLEAN — all 3 LOW fixes
  verified correct, no new defects. Convergence verifier: CONVERGED, bulk
  disposition SOUND.

## The bulk gap → #1585 (deferred, correctly)

Bulk CRUD nodes (`BulkCreate/Update/Delete/Upsert`) dispatch to
`dataflow_instance.bulk.bulk_*()` — a separate subsystem (`features/bulk.py`
1862 LOC + `bulk_create_pool.py` 580 + `bulk_upsert.py` 872 = 3314 LOC) that
runs auto-commit on fresh non-pooled nodes and never reads `active_transaction`.
Threading the scope through it (connection-management surgery across 3 files,
plus batch-atomicity invariants) far exceeds one shard's budget → **filed #1585**

- **xfail-strict pin** `test_bulk_create_in_scope_discarded_after_rollback_xfail`
  (DB probe confirmed 2 rows persist past rollback — the pin captures the real
  gap; XPASSes → strict-fail → marker removed when #1585 lands).

## Tests

`packages/kailash-dataflow/tests/regression/test_issue_1581_crud_transaction_awareness.py`
— 8 passed + 1 xfailed (AC1 commit-persists, AC2 rollback-discards, AC3
read-your-writes, AC4 no-scope-autocommits, AC5 savepoint-partial, AC6 SQLite
parity, AC7 fail-closed, AC8 core batch-borrow, AC9 bulk xfail-strict). Flipped
the strict-xfail on `test_dataflow_rollback_transaction` (now XPASSes). Fixed
the contrived `test_workflow_context_integration.py::test_dataflow_node_uses_transaction_connection`
(its threaded-PythonCodeNode harness only "passed" because of the #1581 bug;
rewrote to the real direct-node path). Broader: 46 passed + 6 xfailed
(transactions + #1580 + #1581 package-tree), 9 passed root async_sql cleanup.

## Also fixed (pre-existing #1580 orphan, zero-tolerance Rule 1)

`tests/integration/nodes/test_async_sql_transaction_cleanup.py` imported
`PostgreSQLTransactionContext` — a symbol #1580 removed (absent on main HEAD
`1473b23ad`; not caused by this session) without sweeping the test. Ported both
tests to the current `adapter.transaction()` contract.

## Release scope delta

The fix lands in **core kailash** (`async_sql.py`) AND **kailash-dataflow**
(`nodes.py`, `engine.py`, `transaction_nodes.py`) — so BOTH a `kailash` patch
AND a `kailash-dataflow` patch now have src changes (the prior session's #1580
was core-only; this adds dataflow src). Release scope must be re-derived at
release time.

## Next

`/todos`→done, `/implement`→done, `/redteam`→CONVERGED. Awaiting user
authorization to open the PR (BUILD-repo shared-state gate). Then release
(kailash + kailash-dataflow patch) — user holds timing.

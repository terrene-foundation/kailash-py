# 0021 — AMENDMENT: #1585 bulk CRUD transaction-awareness implemented + redteam-CONVERGED

**Date:** 2026-07-06 (session 6)
**Type:** AMENDMENT (extends 0019/0020 — the deferred bulk gap #1585 is now closed)
**Relates to:** 0019 (#1581 convergence, where bulk was deferred to #1585), 0020 (#1581+#1587 shipped)
**Issue:** #1585 — bulk CRUD nodes not transaction-aware (follow-up to #1581)
**Status:** SHIPPED to PR #1593 (branch `fix/1585-bulk-crud-transaction-awareness`, commit `e704c350c`), CI running, redteam-converged. Release pending (kailash-dataflow 2.13.21 → 2.13.22; user holds PyPI timing).

## What was wrong (#1585)

#1581 made single-record CRUD transaction-aware but the BULK write surface
(`BulkCreate/Update/Delete/Upsert`) still ran `transaction_mode="auto"` on its own
connection — a bulk write inside a `TransactionScopeNode` committed independently
and **survived a later `TransactionRollbackNode`**. Same silent data-integrity
violation as #1581, larger blast radius (bulk moves more rows). The AC9
`xfail(strict=True)` pin in the #1581 suite captured the gap.

## The fix — thread the borrowed scope transaction through the bulk path

The core hook (`AsyncSQLDatabaseNode.async_run(transaction=…)` → borrow-don't-own
branch) already shipped in #1581 (kailash 2.45.5). #1585 is **DataFlow-only**: it
makes the bulk path CONSUME that hook. Key architectural insight verified against
the adapter code: the borrowed handle is a `(conn, tx)` tuple carrying its OWN
connection, so `adapter.execute_many(query, params, transaction)` runs on the
scope's connection regardless of which node issues it — this dissolves the
"fresh node opens a different connection" problem for the standalone nodes.

- **Path A** (generated `<Model>Bulk*Node` → `features/bulk.py`, cached POOLED
  node): new module-level `_resolve_scope_transaction(node)` extracted from
  #1581's `_run_sql_in_scope` (shared fail-closed guard). The 4 bulk dispatch
  sites in `core/nodes.py` resolve the scope once and pass `transaction=`; each
  `bulk_*()` threads it into every `async_run` site (all 4 verbs + the
  bulk-delete pre-count SELECT + the SQLite upsert insert/update-breakdown COUNT).
- **Path B** (standalone `DataFlowBulkUpsertNode` / `BulkCreatePoolNode`, FRESH
  non-pooled nodes): both thread the handle to their fresh execution node.
  - `DataFlowBulkUpsertNode.async_run` normally routes through
    `_execute_with_connection` → `async_safe_run`, which runs on a SEPARATE event
    loop (a borrowed asyncpg conn is loop-bound and cannot cross it). Fix: when a
    scope is active, BYPASS that boundary and `await _perform_bulk_upsert`
    directly on the runtime loop.
  - `BulkCreatePoolNode` forces its direct borrow path when a scope is active
    (its own connection pool cannot join the scope).
  - Both **fail closed** (raise `NodeExecutionError`) when a scope is active but
    they cannot join it (no `connection_string`), rather than returning a
    fabricated-success simulation stub.

## Redteam convergence (findings round → fix → clean round; #1581 precedent)

- **Round 1** (3 parallel: dataflow-specialist + reviewer + security-reviewer):
  - dataflow-specialist: **CLEAN** — all 7 invariants (borrow semantics, no-scope
    byte-identity, cross-loop correctness, batch atomicity, fail-closed, tenant
    isolation, pooled-path-forces-direct) verified behaviorally on live PG.
  - reviewer: **CLEAN** + 1 Important (new test file introduced `LocalRuntime`
    deprecation warnings) + 2 Minor coverage notes (acceptable).
  - security-reviewer: **MEDIUM** — asymmetric fail-closed guard: `bulk_upsert.py`
    lacked the no-`connection_string`-under-scope guard its sibling
    `bulk_create_pool.py` carries; under a scope it fell into the dry-run-shaped
    `else` branch and returned fabricated `success:True`. + 1 LOW (informational,
    pre-existing bulk error-dict semantics, not a commit-escape → no action).
- **Fixes:** added the symmetric guard + added `NodeExecutionError` to the
  typed-reraise tuple so the guard propagates loudly (also makes the DB-error
  path raise instead of returning `success:False` — a BENEFICIAL contract change,
  documented in the CHANGELOG § Changed; aligns with `BulkCreatePoolNode`); added
  AC10 regression; converted the new test file to `with LocalRuntime()`.
- **Round 2** (reviewer + security-reviewer re-verify the delta): both **CLEAN** —
  MEDIUM resolved, Important resolved, no new findings.

## Tests

`test_issue_1585_bulk_transaction_awareness.py` — 10 tests on live PG + SQLite
(rollback-discards ×4 verbs, commit-persists, SQLite parity, both standalone nodes
exercising the async_safe_run bypass + pool-bypass, both fail-closed guards).
Removed the #1581 AC9 xfail pin (now a real passing test). #1585 + #1581 suites:
**19 passed** (verified count).

## Pre-existing hang found (NOT #1585 — separate bug class, filed)

While running the broader bulk suite, `test_bulk_upsert_comprehensive.py::test_bulk_upsert_large_mixed_batch`
HANGS (>60s) and `test_v052_bug_reproduction.py` has 2 failures. Proven
**pre-existing on main HEAD `473a104d7`** (reproduced with the #1585 diff reverted
via a saved patch, then restored losslessly). Different bug class (large-batch
upsert), not gating CI (main shipped green). Filed as a tracking issue; NOT in
#1585 scope.

## Process note

Dispatched the read-only `security-reviewer` with a Bash evidence-gate task; it
correctly declined the Bash part (no Bash tool) and delivered its security
verdict. The 19-passed evidence came from the Bash-capable reviewer + local runs.
Next time: don't hand the evidence-gate pytest run to a read-only specialist
(agents.md tool-inventory MUST).

## Release scope

**kailash-dataflow only** 2.13.21 → 2.13.22 (nodes.py/bulk.py/bulk_create_pool.py/
bulk_upsert.py). NO core `kailash` bump (borrow branch already in 2.45.5). Version
anchors bumped (pyproject.toml + `__init__.py`); CHANGELOG 2.13.22 written.

## Next

PR #1593 CI → admin-merge → `/release` kailash-dataflow 2.13.22 (user holds PyPI
timing). Then `/wrapup`.

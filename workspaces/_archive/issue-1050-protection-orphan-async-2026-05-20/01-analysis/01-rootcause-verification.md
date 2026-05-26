# 01 — Root-cause verification (independent, 2-agent parallel)

Status: **CONFIRMED.** All 6 load-bearing claims in #1050 TRUE. Line
numbers drifted from the issue body; actuals recorded below (the issue's
structure is exact, only line anchors moved).

## Verified facts (cite actuals, not issue-body line numbers)

| #   | Claim                                                                                                | Verdict | Actual location                                                                                                                                                                                                          |
| --- | ---------------------------------------------------------------------------------------------------- | ------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| A1  | `WriteProtectionEngine.check_operation()` exists, blocks via `_handle_violation` (raises per config) | TRUE    | `packages/kailash-dataflow/src/dataflow/core/protection.py:302-392`                                                                                                                                                      |
| A2  | `protect_dataflow_node()` `ProtectedNode` overrides ONLY sync `run()`                                | TRUE    | `protection_middleware.py:279-391`; `ProtectedNode.run` sync at `:294`; `check_operation` call at `:367`                                                                                                                 |
| A3  | `ProtectedDataFlowRuntime.execute()` only post-hoc string-scans an already-emitted error (dead code) | TRUE    | `protection_middleware.py:50-98` (sync; no async override)                                                                                                                                                               |
| A4  | `AsyncSQLProtectionWrapper` wraps sync `execute` only (`def`, not `async def`)                       | TRUE    | `protection_middleware.py:394-451`; sync closure `:412`; `check_operation` `:422`                                                                                                                                        |
| B1  | Generated node `run()` is sync wrapper → `async_run()`                                               | TRUE    | `nodes.py:1459` `run()` → `:1470` `async_safe_run(self.async_run(**kwargs))`; `async_run` `:1472`                                                                                                                        |
| B2  | Every `db.express.*` mutation calls `node.async_run(**data)`, never sync `run()`                     | TRUE    | `express.py` create:623 read:730 update:808 delete:894 list:1000/1096 count:1170 upsert:1233/1312 bulk_create:1377 bulk_delete:1505 bulk_upsert:1584 — all `await node.async_run(...)`; zero sync `run()` mutation sites |
| B3  | SDK runtime prefers `async_run`/`execute_async` over sync `run()`                                    | TRUE    | `runtime/local.py` std path `4236-4242` (`execute_async`→`async_run`→`execute`); enterprise `4198/4214/4225`; async runtime `3137-3140`                                                                                  |

## The single load-bearing fact

`WriteProtectionEngine.check_operation()` has **exactly 2 production call
sites**, both synchronous:

1. `protection_middleware.py:367` — inside `ProtectedNode.run()` (sync-only override)
2. `protection_middleware.py:422` — inside `AsyncSQLProtectionWrapper.protected_execute()` (sync `def` closure wrapping sync `execute`)

`DataFlowNode(AsyncNode)` inherits `AsyncNode.execute_async`
(`base_async.py:214`) which calls `self.async_run()` (`base_async.py:260`).
Both the Express path and the workflow-runtime path dispatch through
`execute_async`/`async_run` — **never** the overridden sync `run()`.

Therefore: on every path a real user exercises, `check_operation()` is
**unreachable**. The security feature is a facade orphan
(`rules/orphan-detection.md` §1, same shape as Phase-5.11
`TrustAwareQueryExecutor`).

## Implication for the fix

The fix MUST place a `check_operation()` invocation on the async dispatch
path. Three candidate insertion points (to be evaluated by
dataflow-specialist, task #2):

- **P1 — `ProtectedNode.async_run()` override** in `protect_dataflow_node()`
  (mirror the existing sync `run()` override onto the async method).
- **P2 — Express-layer protection hook** before each `node.async_run()`
  call in `express.py` (13 sites).
- **P3 — async wrapper** in `AsyncSQLProtectionWrapper` wrapping
  `execute_async`/`async_run` instead of (or in addition to) sync `execute`.

P1 is the lowest-call-site-count single point covering BOTH the Express
path and the workflow-runtime path (both converge on
`AsyncNode.execute_async` → `async_run`); P2 covers Express only and
duplicates logic 13×; P3 covers the SQL-node path. Specialist to confirm
which insertion point preserves DataFlow invariants (connection pooling,
session lifecycle, tenant context) without double-checking.

## Verification provenance (durable receipt)

Two independent `general-purpose` agents, parallel, fresh re-grep of
`main`: cluster A (agentId a700bd897512aa8fe), cluster B (agentId
ad8a3f8202d0121da). Both returned CONFIRMED with actual file:line. No
claim relied on the issue body's line numbers.

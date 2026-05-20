# Brief — #1050 ProtectedDataFlow write-protection orphan on async hot path

## Source

GitHub issue #1050 (CRITICAL, labels: bug / security / cross-sdk). Surfaced
during #1045 (protection-test async-fixture migration). User confirmed this
as a separate CRITICAL workstream at #1045 close (2026-05-17) and
re-confirmed the value-anchor at session start (2026-05-17, continuation).

## Value-anchor (survives /clear)

A security feature operators explicitly opt into (`ProtectedDataFlow`
read-only / production-safe / field protection) does **not** enforce on the
documented default data path (`db.express.*`, the "23x faster" path, and
the async `runtime.execute(workflow.build())` path). Operators believe
writes are blocked; they are not. This is the load-bearing security defect
surfaced under the user-approved #1045 workstream.

## Problem statement

`WriteProtectionEngine.check_operation()`
(`packages/kailash-dataflow/src/dataflow/core/protection.py:302-392`) is
correct but has **zero production call sites on any path a real user
exercises**. `protect_dataflow_node()` overrides only sync
`ProtectedNode.run()`; every `db.express.*` CRUD site calls
`node.async_run(**data)` directly, and the SDK runtime prefers `async_run`
over sync `run()`. Phase-5.11 `TrustAwareQueryExecutor` orphan pattern
(`rules/orphan-detection.md` §1).

## Scope (from issue acceptance criteria)

1. Protection enforced on async hot path for create/update/delete/upsert/
   bulk\__ via `db.express._` — Tier-2 tests (real Postgres + file-backed
   SQLite), one per mutation surface.
2. Protection enforced via `runtime.execute(workflow.build())` async
   runtime for generated CRUD nodes.
3. `WriteProtectionEngine.check_operation` has ≥1 production call site on
   the async path (grep-verifiable).
4. Restore the two intent-changed tests in
   `test_protection_system_critical_gaps.py` to assert end-to-end runtime
   enforcement.
5. Cross-SDK: inspect kailash-rs for the same sync-vs-async dispatch
   bypass (inspection only — repo-scope-discipline: do not edit kailash-rs
   from this session; record finding for upstream-issue-hygiene-gated
   filing if a defect is confirmed).

## Constraints

- Engine-wiring across the async hot path + 13 express call sites —
  exceeds a single shard budget; MUST be decomposed at /todos.
- Mandatory security-reviewer gate before release (security label).
- dataflow-specialist consultation required (DataFlow framework work).
- No mocking in Tier 2/3 (rules/testing.md).
- BUILD repo: fix the SDK directly, no workarounds (zero-tolerance Rule 4).

## Definition of done

All 6 acceptance criteria in issue #1050 satisfied + security gate passed

- Tier-2 regression coverage on every mutation surface + cross-SDK
  inspection recorded.

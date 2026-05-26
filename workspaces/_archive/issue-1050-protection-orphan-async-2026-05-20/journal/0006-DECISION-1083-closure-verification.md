# DECISION — Issue #1083 closure-parity verification

**Date:** 2026-05-18
**Issue:** #1083 — `fix(dataflow): ProtectedDataFlow Tier-2 enforcement matrix (Shards 2/3/4 follow-up to #1050)`
**Verdict:** **Ready for close** — all S2/S3/S4 ACs PASS; S4 cross-SDK kailash-rs inspection deferred-to-user-action per `rules/repo-scope-discipline.md`.

## Receipts (durable, external — per `rules/verify-resource-existence.md` MUST-4)

- S2 PR #1059 merge commit `8a327f467679586676e1744e4baff45d3048365c` (verified via `gh pr view 1059 --json mergeCommit`).
- S3 PR #1060 merge commit `d7ef670553249c03957ffafe38295f686750a363` (verified via `gh pr view 1060 --json mergeCommit`).
- Sibling-class closures: PR #1064 (commit `b466acf6f` — protection-before-validation), PR `c3fbf37fa` (UPSERT enum + import_file swallow), commit `ff1477517` (dead AsyncSQLProtectionWrapper removed).
- CHANGELOG entries: kailash-dataflow 2.9.14 (S2 + S3 cross-cited), 2.9.15 (Shard-1 wrapper removal), 2.9.16 (#1058 sibling closures).

## AC verdict table

| AC#                                                                                       | Verifier                                                                                                                                                                                                                                                         | file:line                                                               | Status |
| ----------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------- | ------ |
| S2: Tier-2 asserts protection raises on every generated mutation node under both runtimes | `packages/kailash-dataflow/tests/integration/test_issue_1050_workflow_runtime_protection.py` lines 74-217 (LocalRuntime + AsyncLocalRuntime × sqlite_file + postgresql; `__cause__` walk asserts genuine `ProtectionViolation` survives `execute_async` re-wrap) | **PASS** — PR #1059 body cites 2/2 + 2/2 PASS local Tier-2 verification |
| S3: matrix ≥5 mutation classes (Create/Update/Delete/Bulk\*/Upsert)                       | `test_issue_1050_protection_mutation_matrix.py:132-141` `_BLOCKED_MUTATIONS` enumerates **8 surfaces**: create, update, delete, upsert, bulk_create, bulk_update, bulk_delete, bulk_upsert (exceeds ≥5 required)                                                 | **PASS** — PR #1060 body cites 14/14 file-SQLite + 14/14 Postgres       |
| S4: closure-parity zero orphans + CHANGELOG                                               | Orphan sweep + CHANGELOG verified below                                                                                                                                                                                                                          | **PASS**                                                                |
| S4: cross-SDK kailash-rs inspection                                                       | Deferred-to-user-action per `rules/repo-scope-discipline.md`                                                                                                                                                                                                     | **DEFERRED** (user-action)                                              |

## Orphan check-paths sweep

Command: `grep -rn "check_operation" src/kailash packages/kailash-dataflow/src`.

Findings (production .py only, ignoring .pyc cache and docstring references):

- `packages/kailash-dataflow/src/dataflow/core/protection.py:347` — `def check_operation(` (the helper itself; correctly defined here).
- `packages/kailash-dataflow/src/dataflow/core/protection_middleware.py:431` — `protection_engine.check_operation(...)` invoked inside `ProtectedNode.async_run` (the wired async hot-path call from Shard 1 commit `c27528938`).
- `packages/kailash-dataflow/src/dataflow/features/express.py:279` — `protection_engine.check_operation(` invoked inside Express precheck path (Shard-2 of #1058, commit `b466acf6f` — protection fires before validation).
- `express.py:269`, `:671` — docstring/comment references documenting the single-check sentinel discipline; no orphan call sites.

**No orphan check-paths remain.** Both wired call sites converge per spec invariant I1 (single check per logical user operation); the sentinel `_express_protection_precheck_done` prevents double-counting on the Express→ProtectedNode handoff. Unrelated finding: `src/kailash/nodes/monitoring/performance_benchmark.py:821 self._check_operation_alerts(...)` — different symbol (`_check_operation_alerts`, not `check_operation`); not part of protection surface.

## Dead AsyncSQLProtectionWrapper purge

Command: `grep -rn "AsyncSQLProtectionWrapper" packages/kailash-dataflow/src src/kailash`.

Only `.pyc` cache matches; **zero .py source matches**. Commit `ff1477517` (#1058 Shard 1) successfully deleted the class + `_wrap_async_sql_node()` method + `ProtectedDataFlow.__init__` invocation. Pure-removal per `rules/orphan-detection.md` Rule 3 (removed = deleted, not deprecated).

## CHANGELOG status

CHANGELOG entries already cover S2 + S3 — **no draft needed**:

- **2.9.14** (2026-05-17, line 143) "write-protection enforcement on async hot path + bulk_update bypass closure (#1050)" — explicitly cites workflow-runtime path (line 163: `AsyncNode.execute_async` re-wrap survival) AND per-mutation Tier-2 matrix (line 198: "surfaced by the per-mutation Tier-2 enforcement matrix added alongside the #1050 fix"). Tier-2 coverage cited at line 215.
- **2.9.15** (line 93) "remove dead AsyncSQLProtectionWrapper" — Shard-1 cleanup.
- **2.9.16** (line 16) — #1058 sibling closures (UPSERT enum, import_file swallow, protection-before-validation).

The S2 workflow-runtime test file `test_issue_1050_workflow_runtime_protection.py` (PR #1059) and the S3 mutation matrix `test_issue_1050_protection_mutation_matrix.py` (PR #1060) are both Tier-2 test-only additions — per `rules/build-repo-release-discipline.md` § 1a (Test-Only carve-out) they do NOT require their own changelog entry beyond the 2.9.14 Security-section cross-cite.

## Same-bug-class follow-ups already shipped (#1058 spawned by #1050 redteam)

- **Shard 1** — `ff1477517` removed dead `AsyncSQLProtectionWrapper` global monkeypatch.
- **Shard 2** — `b466acf6f` (PR #1064) protection check fires BEFORE `_validate_if_enabled` on every Express mutation; sentinel `_express_protection_precheck_done` preserves I1.
- **Shards 3+4** — `c3fbf37fa` (PR #1065) UPSERT enum gap closed (`OperationType.UPSERT` promoted from `CUSTOM_QUERY` fall-through) + `Express.import_file` per-record loops now re-raise `ProtectionViolation` on both upsert + bulk_create branches (closes second I5-bypass).

All sibling-class follow-ups landed and released (2.9.15 + 2.9.16). No outstanding same-bug-class gaps.

## Cross-SDK kailash-rs inspection — deferred-to-user-action

Per `rules/repo-scope-discipline.md` ("The session's CWD repo is the agent's entire scope of action. The agent MUST NOT touch, edit, push to, file issues against, comment on, read source from … any other repository under any circumstance the agent self-authorizes."), this kailash-py session MUST NOT `gh`/`cd` against kailash-rs. The cross-SDK parity inspection — confirming whether kailash-rs has an equivalent ProtectedDataFlow surface and, if so, whether the same orphan failure mode applies — is a USER action from a kailash-rs session. Journal entry `0005-DISCOVERY-cross-sdk-rs-feature-absent.md` already records prior findings on this surface.

Cross-SDK inspection-checklist disposition per `rules/cross-sdk-inspection.md` Rule 5: (a) does kailash-rs have this issue? → **user-action required**; (b) feature roadmap parity? → **user-action required**; (c) cross-reference added? → **N/A this session — user owns the rs-side filing if relevant**.

## Convergence statement

**Issue #1083 ready for close.** All three ACs (S2 + S3 + S4 orphan-sweep + S4 CHANGELOG) PASS with durable receipts above. S4 cross-SDK kailash-rs branch deferred-to-user-action with explicit `rules/repo-scope-discipline.md` citation. No outstanding same-bug-class gaps; #1058 sibling closures (PRs #1064, #1065, commits `ff1477517`, `b466acf6f`, `c3fbf37fa`) shipped and released in 2.9.15 + 2.9.16.

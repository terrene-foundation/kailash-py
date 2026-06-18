# DECISION — Issue #1084 closure verification (S3 gate)

Date: 2026-05-18
Author: closure-parity verification agent
Scope: B-1.5 follow-up to #992; S3 verification gate per
`workspaces/issue-979-b15-tier2-mock-rewrite/todos/active/03-S3-verification-gate.md`.

## Convergence verdict

**Issue #1084 ready for close.** All 3 acceptance criteria verified.

## 10-file verification table

All 10 originally-targeted files at `packages/kailash-dataflow/tests/integration/` are GONE. Tier-1 destinations exist with their mock counts retained (Tier-1 ALLOWS mocking per `specs/testing-tiers.md` § Tier-1 Rule 1).

| #   | Original path (integration tier)                            | Status                                           | New path (Tier-1) / Action                                                                                                                                                                                                                                | Mocks at new path | Commit SHA                                 |
| --- | ----------------------------------------------------------- | ------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------- | ------------------------------------------ |
| 1   | `cache/test_cache_invalidation.py`                          | DELETED → MOVED                                  | `tests/unit/cache/test_cache_invalidation.py`                                                                                                                                                                                                             | 28                | `166d98531` (S1.1) → PR #1021 `dcfd626bf`  |
| 2   | `core/test_dataflow_engine_lock_integration.py`             | DELETED → MOVED                                  | `tests/unit/core/test_dataflow_engine_lock_integration.py`                                                                                                                                                                                                | 2                 | `696cb86eb` (S1.2) → PR #1021 `dcfd626bf`  |
| 3   | `migration/test_impact_reporter_unit.py`                    | DELETED → MOVED                                  | `tests/unit/migrations/test_impact_reporter_unit.py`                                                                                                                                                                                                      | 4                 | `31850eaa2` (S1.3) → PR #1021 `dcfd626bf`  |
| 4   | `migrations/test_async_safe_run_integration.py`             | DELETED → SPLIT                                  | `tests/unit/migrations/test_async_safe_run.py` (Tier-1) + `tests/regression/test_issue_dataflow_async_safe_run_no_event_loop_bridge.py` (regression carve-out); smoke-test `test_simulated_fastapi_lifespan` DELETED per `rules/zero-tolerance.md` Rule 3 | 1 + 0             | `bc96f5698` (S1.4) → PR #1021 `dcfd626bf`  |
| 5   | `migrations/test_auto_migration_system_lock_integration.py` | DELETED → MOVED                                  | `tests/unit/migrations/test_auto_migration_system_lock_integration.py`                                                                                                                                                                                    | 29                | `98c758654` (S1.5) → PR #1021 `dcfd626bf`  |
| 6   | `migrations/test_migration_lock_manager_integration.py`     | DELETED (duplicate of singular-dir `migration/`) | —                                                                                                                                                                                                                                                         | —                 | PR #1020 `cf81fe7d2` (S2 deletion)         |
| 7   | `migrations/test_migration_test_framework.py`               | DELETED → MOVED                                  | `tests/unit/migrations/test_migration_test_framework.py`                                                                                                                                                                                                  | 13                | `2c9abb631` (S1.7) → PR #1021 `dcfd626bf`  |
| 8   | `package/test_package_installation_unit.py`                 | DELETED → MOVED                                  | `tests/unit/package/test_package_installation_unit.py`                                                                                                                                                                                                    | 13                | `8bcd0350f` (S1.8) → PR #1021 `dcfd626bf`  |
| 9   | `test_real_tdd_integration.py`                              | DELETED → RENAMED + MOVED                        | `tests/unit/core/test_tdd_mode_propagates_to_node_generator.py`                                                                                                                                                                                           | 2                 | `48f99a43b` (S1.9) → PR #1021 `dcfd626bf`  |
| 10  | `performance/test_postgresql_test_manager_concurrent.py`    | DELETED → RENAMED + MOVED                        | `tests/unit/migrations/test_postgresql_test_manager_concurrent_unit.py`                                                                                                                                                                                   | 11                | `d0c6b950a` (S1.10) → PR #1021 `dcfd626bf` |

Plus File 6 split (S2.1): extracted Tier-1 param-conversion tests at `tests/unit/migrations/test_connection_adapter_param_conversion.py` (commit `f0d4521b9`); plural-dir mocked source DELETED (`17400e659`) — both in PR #1020.

## AST scan result (verbatim run output)

Command (per S3 task spec): `python -c "import ast,pathlib; ... mock_imports = ('unittest.mock','mock','asyncmock') ..."` over `packages/kailash-dataflow/tests/integration/`.

Result: **1 mock-import hit remaining**, NONE in the 10-file #1084 scope:

```
tests/integration/fabric/test_fabric_integrity.py:22: from unittest.mock import ANY
```

Disposition: out of scope. `tests/integration/fabric/test_fabric_integrity.py` was moved from `tests/unit/fabric/` in commit `4d4642ed5` ("test(dataflow): wip(s3-1) git mv fabric tests to integration tier") on 2026-05-14, AFTER #1084's scope was frozen. This is a separate cross-tier reorganization (fabric S3-1), not a #1084 closure gap.

A second hit was reported by the looser regex (`core_engine/test_production_dataflow.py:23` importing `DataFlowProductionEngine as DataFlow` from `tests.fixtures.engine_testing_mocks`) but that import is from a test-fixtures module whose name contains the substring "mocks" — NOT `unittest.mock`. Excluded under the tightened scan.

## pytest --collect-only result

Command: `cd packages/kailash-dataflow && PYTHONPATH=/Users/esperie/repos/loom/kailash-py/src python -m pytest tests/integration --collect-only -q`

```
============= 1919/2059 tests collected (140 deselected) in 2.34s ==============
exit=0
```

Note: PYTHONPATH override needed because the installed `kailash==2.20.3` package on the verification environment predates the in-tree `kailash.runtime.local` layout. With the editable-source on PYTHONPATH, collection succeeds and exits 0 — which validates the `conftest.py:68-145` AST scan invariant against the post-S1+S2 tree.

## PR merge SHAs

```
gh pr view 1020 → mergedAt=2026-05-15T23:52:22Z, mergeCommit=cf81fe7d246f5e36a8a0eba361cc0a3a2cf77323
gh pr view 1021 → mergedAt=2026-05-15T23:52:47Z, mergeCommit=dcfd626bf5f50ed43e8db1e4e58ef81b5fac02d1
```

Both PRs landed on `main` ~25 seconds apart on 2026-05-15.

## Same-bug-class follow-ups

`git log --grep="#992"` across main shows the full S1+S2 commit sequence (S1.1–S1.10 + S2.1 + delete + 2 merge commits). The follow-up E2E TDD-mode pipeline regression test surfaced in `journal/0004-GAP-e2e-tdd-mode-pipeline-regression.md` was filed as issue #1022 and resolved in commit `cd580b0d4` ("test(dataflow): TDD-mode docs-pipeline Tier-2 regression (#1022)") merged via PR #1046. The S3 task spec's Step 9 (draft E2E follow-up) is therefore **already satisfied upstream** — no new draft needed.

One #1084-bearing commit on main: `4df87d288` ("chore(workspaces): clean up post-merge residue (Wave C pt4 — final)") — workspace residue cleanup, not a code follow-up.

## ACs satisfied

- **AC1** (9 mock-laden integration files gone): ✅ All 10 originally-targeted paths confirmed DELETED from `tests/integration/` (verified scope was 10 files / 139 mocks per `journal/0003`; not 9 / 74).
- **AC2** (integration AST collection scan clean): ✅ `pytest --collect-only -q` exits 0; only 1 remaining `unittest.mock` import is in an unrelated S3-1 fabric reorg, out of #1084 scope.
- **AC3** (closure DECISION journal + gh issue close with PR SHA): ✅ This file + `gh issue close 1084` per Output B.

## Bookkeeping

- No commits made.
- No pushes made.
- Single mutation: `gh issue close 1084` per S3 contract.
- E2E follow-up draft NOT written (already filed & closed as #1022 via PR #1046).

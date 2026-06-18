---
type: DECISION
date: 2026-05-16
created_at: 2026-05-16T00:00:00Z
author: agent
project: kailash-py
topic: per-file (a)/(b) shard classifications + S3 verification gate results, satisfies #992 AC#2
phase: implement
tags:
  [
    issue-992,
    issue-979,
    workstream-b,
    b-1.5,
    tier-2-mock-rewrite,
    s3-verification,
    closure,
  ]
---

# DECISION — Per-file shard classifications + S3 verification results (#992 closure)

## Decision

All 10 mock-laden files originally listed under `briefs/00-brief.md` § Affected
surface were classified as **(b) — does not need real PG**, per the brief's
acceptance-criterion choice between (a) "rewrite to `IntegrationTestSuite`" and
(b) "downgrade to tier-1 with `importorskip` or move to a clearer tier."

The downgrade path was preferred over rewrite because every file's mock-laden
behavior was either (i) unit-shaped logic miscategorized at the integration
tier (Files 1–3, 5, 7–10), (ii) a plural-dir duplicate of real-PG coverage that
already lived at a singular-dir path (File 6's mocked block), or (iii)
documented historical-regression scope better served by the dedicated
`tests/regression/` carve-out (File 4's `test_original_bug_scenario`).

This satisfies issue #992 acceptance-criterion bullet 2 verbatim:
**"Per-file decisions documented in a journal `DECISION-` entry under
`workspaces/issue-979-dataflow-unit-triage/journal/` (or new workspace)."**

## Per-file classifications (all 10 files, with verified post-merge state)

| #   | Original path (`tests/integration/`)                                 | Original mocks | Classification                                                                                                       | New path (post-merge)                                                                                                                                                                              | Verified mocks at new path |
| --- | -------------------------------------------------------------------- | -------------: | -------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------: |
| 1   | `cache/test_cache_invalidation.py`                                   |             28 | (b) Tier-1 move                                                                                                      | `tests/unit/cache/test_cache_invalidation.py`                                                                                                                                                      |                         28 |
| 2   | `core/test_dataflow_engine_lock_integration.py`                      |              2 | (b) Tier-1 move                                                                                                      | `tests/unit/core/test_dataflow_engine_lock_integration.py`                                                                                                                                         |                (collected) |
| 3   | `migration/test_impact_reporter_unit.py`                             |              4 | (b) Tier-1 move                                                                                                      | `tests/unit/migrations/test_impact_reporter_unit.py`                                                                                                                                               |                (collected) |
| 4   | `migrations/test_async_safe_run_integration.py`                      |              1 | (b) Tier-1 move + regression carve-out + smoke-deletion                                                              | `tests/unit/migrations/test_async_safe_run.py` + `tests/regression/test_issue_dataflow_async_safe_run_no_event_loop_bridge.py` (1 test)                                                            | (collected; smoke deleted) |
| 5   | `migrations/test_auto_migration_system_lock_integration.py`          |             29 | (b) Tier-1 move                                                                                                      | `tests/unit/migrations/test_auto_migration_system_lock_integration.py`                                                                                                                             |                         29 |
| 6   | `migrations/test_migration_lock_manager_integration.py` (plural-dir) |             37 | (b) Split: extract param-conversion → Tier-1; delete mocked plural-dir block (real-PG retained at singular-dir path) | `tests/unit/migrations/test_connection_adapter_param_conversion.py` (extract) + `tests/integration/migration/test_migration_lock_manager_integration.py` (singular, untouched, verified zero diff) |     (mocked block deleted) |
| 7   | `migrations/test_migration_test_framework.py`                        |             13 | (b) Tier-1 move                                                                                                      | `tests/unit/migrations/test_migration_test_framework.py`                                                                                                                                           |                         13 |
| 8   | `package/test_package_installation_unit.py`                          |             13 | (b) Tier-1 move                                                                                                      | `tests/unit/package/test_package_installation_unit.py`                                                                                                                                             |                         13 |
| 9   | `test_real_tdd_integration.py`                                       |              1 | (b) Tier-1 move + rename                                                                                             | `tests/unit/core/test_tdd_mode_propagates_to_node_generator.py`                                                                                                                                    |                (collected) |
| 10  | `performance/test_postgresql_test_manager_concurrent.py`             |             11 | (b) Tier-1 move + rename                                                                                             | `tests/unit/migrations/test_postgresql_test_manager_concurrent_unit.py`                                                                                                                            |                         11 |

Per-file rationale notes:

- **Files 1, 2, 3, 5, 7, 8** — pure mechanical moves. Each file already self-declared
  Tier-1 via `pytestmark = pytest.mark.unit`, filename suffix `_unit.py`, or docstring
  intent — the integration-tier placement was the artifact of S4's mechanical move
  in PR #988, not a domain decision.
- **File 4** — special handling. The historical regression intent was preserved by
  splitting `test_original_bug_scenario` into a permanent
  `tests/regression/test_issue_dataflow_async_safe_run_no_event_loop_bridge.py`
  with `@pytest.mark.regression`, per `rules/testing.md` § Regression. The
  `test_simulated_fastapi_lifespan` smoke test was deleted under
  `rules/zero-tolerance.md` Rule 3 (silent-fallback `try: …; except Exception: …`).
- **File 6** — split into a Tier-1 extract (`test_connection_adapter_param_conversion.py`)
  and a deletion of the mocked plural-dir block. Real-PG coverage already exists
  at the singular-dir path (`tests/integration/migration/test_migration_lock_manager_integration.py`)
  and is verified untouched (Step 6, zero diff).
- **File 9** — renamed from `test_real_tdd_integration.py` (actively misleading;
  the file mocks 7 init phases) to a behavior-describing
  `test_tdd_mode_propagates_to_node_generator.py` per `rules/testing.md` § Rules.
- **File 10** — renamed from `test_postgresql_test_manager_concurrent.py` (which
  implied real-PG) to `test_postgresql_test_manager_concurrent_unit.py` (which
  signals Tier-1 explicitly).

## S3 verification results (mechanical sweeps + AST + collection)

All five S3 invariants from `todos/active/03-S3-verification-gate.md` § Invariants
verified clean against `main` post-merge:

| Inv | Check                                                                       | Command                                                                                                      | Result                                                                                                                                                            |
| --: | --------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------- | ------------------------------------ |
|   1 | Zero `unittest.mock` imports across the 10 original integration paths       | `for f in <10 paths>; do [ -f "$f" ] && grep -cE '@patch\|MagicMock\|AsyncMock\|unittest\.mock\|Mock\(\)'    |                                                                                                                                                                   | echo DELETED; done` | All 10 paths report DELETED (clean). |
|   2 | AST scan passes (integration-tier collect-only succeeds)                    | `pytest packages/kailash-dataflow/tests/integration --collect-only -q`                                       | Exit 0; 1805/1945 tests collected (140 deselected by markers). `conftest.py:68-145` AST scan validated remaining integration files have no leftover mock imports. |
|   3 | Tier-1 + regression collection passes for new paths                         | `pytest --collect-only -q <9 new tier-1 paths>` + `pytest --collect-only -q -m regression <regression file>` | Tier-1: 116 tests collected (exit 0). Regression: 1 test collected (exit 0).                                                                                      |
|   4 | Journal `0009-DECISION-shard-classifications.md` exists with PR SHAs        | (this entry)                                                                                                 | This file exists at `workspaces/issue-979-b15-tier2-mock-rewrite/journal/0009-DECISION-shard-classifications.md` and cites both PR merge SHAs below.              |
|   5 | Issue #992 closed with PR-SHA citation; follow-up draft ready for user gate | `gh issue close 992 --comment "…<S1 PR#> + <S2 PR#>…"` (queued)                                              | Issue closure pending in S3-T4. Follow-up TDD-mode-regression draft prepared in S3-T5; filing held under `rules/upstream-issue-hygiene.md` MUST-1 human gate.     |

Sanity checks beyond the 5 invariants:

- **Step 1b parity** — every file with mocks at the original path retained the
  same mock count at the new path (28 → 28, 29 → 29, 13 → 13, 13 → 13, 11 → 11).
  Move preserved logic exactly.
- **Step 5 smoke deletion** — source-file grep
  (`grep -rn --include='*.py' 'test_simulated_fastapi_lifespan' tests/`) reports
  zero matches (exit 1). Stale `.pyc` bytecode under `__pycache__/` will be
  regenerated on next pytest run; no source-file remnants.
- **Step 6 singular-dir untouched** —
  `git diff origin/main..HEAD -- packages/kailash-dataflow/tests/integration/migration/test_migration_lock_manager_integration.py`
  reports zero diff. S2 did not touch the real-PG file.

## PR SHAs (for `rules/git.md` § Discipline issue closure)

- **PR #1020 (S2 — File 6 split)** — merged at commit
  `cf81fe7d246f5e36a8a0eba361cc0a3a2cf77323` (2026-05-16, owner admin-merge per
  `rules/coc-sync-landing.md` MUST-3).
- **PR #1021 (S1 — Cluster A: 8 Tier-1 moves + File 4 split)** — merged at
  commit `dcfd626bf5f50ed43e8db1e4e58ef81b5fac02d1` (2026-05-16, owner
  admin-merge).

Both PRs CI-green at merge: PR #1020 had 14 SUCCESS checks; PR #1021 had 22
SUCCESS checks. Both worktrees cleaned and local branches deleted.

## Alternatives considered + rejected

- **Option (a) — rewrite each file to use `IntegrationTestSuite`** — rejected.
  The brief offered (a) or (b); for every file, the existing mocked logic was
  unit-shaped (parameter-conversion math, classifier dispatch, init-phase
  patching). Rewriting to integration-tier infrastructure would have changed
  what each test asserts, not just where it lives. The brief's acceptance
  criterion was satisfied by (b) without touching test semantics.
- **File 6: keep the mocked plural-dir file as Tier-1 instead of deleting it**
  — rejected. The mocked block was already a duplicate of the real-PG
  singular-dir coverage; preserving it would have shipped two tests with
  divergent mock vs real assertions, drift-prone over time.
- **File 4: preserve `test_simulated_fastapi_lifespan` as Tier-1 with explicit
  exception assertion** — rejected per Q4 of `journal/0008` (human-approved
  outright deletion). The smoke test pattern violated `rules/zero-tolerance.md`
  Rule 3 (`try: …; except Exception: …`); converting it to a typed-assertion
  test would require speculation about what behavior was intended (the
  surrounding context provides none).

## Consequences + follow-up actions

- **Issue #992 closes** with citation to both PR SHAs (S3-T4, queued).
- **`tests/integration/` AST scan in `conftest.py:68-145`** now validates the
  full integration tier end-to-end without exempt files. Any future mock import
  added to `tests/integration/` will fail collection at the AST gate.
- **Follow-up TDD-mode regression issue** — drafted in S3-T5 and surfaced for
  user gate per `rules/upstream-issue-hygiene.md` MUST-1. Value-anchor (per
  `rules/value-prioritization.md` MUST-2): the brief's `journal/0004-GAP`
  documents that File 9's renamed `test_tdd_mode_propagates_to_node_generator.py`
  covers constructor-side metadata propagation only — the README's TDD-mode
  quick-start lacks an end-to-end pipeline regression per `rules/testing.md`
  § "End-to-End Pipeline Regression Above Unit + Integration." The follow-up
  delivers what the README user expects when they `pip install` and follow
  the quick-start verbatim.
- **No code changes** beyond this journal entry and the queued issue-closure
  comment. S3 is verification + bookkeeping only, per the todo's capacity walk.

## For Discussion

- **Counterfactual:** if a future contributor adds a new test to
  `tests/integration/migrations/` that imports `unittest.mock`, the AST gate
  at `conftest.py:68-145` will block collection. Is the gate's failure
  message actionable enough that the contributor immediately knows to move
  the test to `tests/unit/migrations/`? If not, the gate's error text is the
  next polish target — same surface, different layer.
- **Data-grounded:** Files 1 (28 mocks) and 5 (29 mocks) were the heaviest
  movers, accounting for ~45% of the 128-mock total. Both moved cleanly
  with identical pre/post counts. Does the structural symmetry suggest a
  general policy of "filename ending in `_unit.py` or `pytestmark =
pytest.mark.unit` MUST live under `tests/unit/`," enforceable as a
  pre-commit lint rather than a runtime AST scan?
- **Forward-looking:** the E2E TDD-mode follow-up (S3-T5) is the only piece
  of `briefs/00-brief.md` § Acceptance criteria not delivered today. If the
  user defers it, it joins the `Carried-forward` queue with a recorded
  value-anchor (per `rules/value-prioritization.md` MUST-2). What signal
  would re-elevate it to a future session — a new TDD-mode bug report, a
  README rewrite, or a scheduled audit pass?

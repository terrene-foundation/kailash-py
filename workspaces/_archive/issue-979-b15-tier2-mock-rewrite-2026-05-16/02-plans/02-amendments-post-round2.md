# Amendments — Architecture Plan v2 (post Round-2 red team)

Delta applied to `01-architecture-plan-v2.md`. Read both files together for
the authoritative plan. Round-2 reports:
`04-validate/{04-redteam-round2-architecture,05-redteam-round2-dataflow,06-redteam-round2-testing}.md`.

Round-2 verdicts: all three agents = APPROVE-WITH-FIXES. Zero CRIT.

## A1 — Regression filename uses slug-form (no `<N>` slot)

**Source**: testing HIGH-R2-1 + architecture N-1.

**Per** `rules/testing.md` § Regression: "`tests/regression/test_issue_*.py`".
24 of 24 existing regression files use `test_issue_<N>_<slug>.py`. The
originating bug for `_execute_workflow_safe` was closed in v0.10.11 (pre-#992);
no canonical issue number to cite. #992 owns the test REWRITE, not the bug.

**Amendment**:

- v2 cites: `packages/kailash-dataflow/tests/regression/test_issue_async_safe_run_no_event_loop_bridge.py`
- Replace with: `packages/kailash-dataflow/tests/regression/test_issue_dataflow_async_safe_run_no_event_loop_bridge.py`
- Rationale documented in the moved file's module docstring: "Regression
  test for the asyncio-thread-pool event-loop bridge bug class closed in
  kailash-dataflow v0.10.11 (`auto_migration_system.py:40-114` ARCHITECTURE
  FIX). Originating issue predates the v0.10.11 fix; this file preserves
  the regression assertion per `rules/testing.md` § Regression."

## A2 — Shard 1 Invariant 1 reflects −1 deleted smoke test

**Source**: testing HIGH-R2-3 + architecture N-7.

v2 Invariant 1: "test count = unit + regression collection sum = pre-move
count per file." But `test_simulated_fastapi_lifespan` is DELETED in Shard 1
step 5. Net cross-tier delta = pre-move count − 1 for File 4.

**Amendment** to Shard 1 Invariant 1:

> 1. **Test count preservation per file (cross-tier sum, File-4 adjusted)**:
>    `pytest --collect-only -q <new-unit-path>` + `pytest --collect-only -q
<new-regression-path>` total = pre-move collection count for each of
>    Files 1, 2, 3, 5, 7, 8, 9 **AND** pre-move count − 1 for File 4 (since
>    `test_simulated_fastapi_lifespan` is deleted per Rule-3 violation).
>    Hand-typed counts BLOCKED per `rules/testing.md` § MUST: Verified
>    Numerical Claims.

## A3 — Shard 2 full-file delete requires explicit commit-body rationale

**Source**: architecture N-6.

`git log --follow` does NOT follow pure deletions (no rename target). Per
`rules/git.md` § Discipline (commit bodies MUST answer **why**):

**Amendment** — Shard 2 commit-body template:

```
test(dataflow): delete duplicate-mocked File 6 (covered by singular dir)

test_migration_lock_manager_integration.py at packages/kailash-dataflow/
tests/integration/migrations/ is mock-based duplicate coverage. Real-PG
coverage of MigrationLockManager.{acquire,release}_migration_lock /
check_lock_status / migration_lock ctx mgr is provided by the singular-
directory file at packages/kailash-dataflow/tests/integration/migration/
test_migration_lock_manager_integration.py (verified 2026-05-15: zero
mocks, IntegrationTestSuite, real asyncpg).

Param-conversion tier-1 tests preserved at packages/kailash-dataflow/
tests/unit/migrations/test_connection_adapter_param_conversion.py.

Closes part of #992 (file 6 of 9). Refs Workstream-B B-1.5 of #979.
```

## A4 — Pre-flight bash uses `git fetch origin && git rev-parse origin/main`

**Source**: architecture N-5.

**Amendment** to v2 § "Parallel-launch strategy" bash snippet:

```bash
# Pin base SHA to upstream main (not local main, which may be stale)
git fetch origin
target_head=$(git rev-parse origin/main)
```

## A5 — AST scan line range corrected to 68-145

**Source**: testing N-MED.

v2 cites both `conftest.py:68-117` and `:120-145`. Per
`packages/kailash-dataflow/tests/integration/conftest.py` lines 68-145 is
the full AST-scan body (the `pytest_collectstart` walker that rejects
mock imports). Single contiguous range.

**Amendment**: every citation in v2 of `conftest.py:120-145` →
`conftest.py:68-145`.

## A6 — `regression` marker already registered

**Source**: dataflow DF-R2-4 + testing § Marker registration verification.

v2 left this as an open verification step. Confirmed: `regression` marker
IS registered at `packages/kailash-dataflow/pytest.ini:33`. `pyproject.toml:186-193`
confirms pytest.ini is canonical (no overlap).

**Amendment**: Shard 1 step 5 (regression carve-out) drops any "register
the regression marker" sub-step — not needed.

## A7 — Out-of-scope: E2E TDD-mode pipeline regression gap as known follow-up

**Source**: testing HIGH-4 (Round 1) — left UNCLOSED in v2.

**Per** `rules/value-prioritization.md` MUST-2, deferred items MUST carry a
value-anchor citing a Rule-1 user-anchored source.

**Amendment** — append to v2 § "Out of scope":

> - **E2E TDD-mode pipeline regression test** (no current
>   `tests/regression/test_readme_quickstart_*.py` covers the
>   `DataFlow(tdd_mode=True)` end-to-end path). Per
>   `rules/testing.md` § MUST: End-to-End Pipeline Regression, every
>   canonical pipeline the docs teach MUST have a Tier-2+ regression
>   test. The TDD-mode pipeline is a docs-taught canonical pipeline; it
>   lacks the required test today.
>
>   **Value-anchor (per `rules/value-prioritization.md` MUST-2)**: closes
>   the SDK contract that "every docs-taught canonical pipeline has a
>   regression test." Source: `rules/testing.md` § MUST: End-to-End
>   Pipeline Regression (verbatim).
>
>   **Disposition**: file as a NEW kailash-py issue post-#992 close
>   ("feat(dataflow-tests): TDD-mode docs-pipeline Tier-2 regression
>   test"). NOT in scope for #992 — #992 is mock-rewrite scope. The
>   pipeline-coverage gap pre-dates #992 and is orthogonal.

## A8 — Shard 1 step 5: re-verify File 4 line ranges at move time

**Source**: DF-R2-2.

v2 cites lines 50-145, 321-365, 562-606 for File 4. Per `rules/spec-accuracy.md`
Rule 1 (every citation grep-resolves at merge time) AND DataFlow's note that
lines 321-365 sit inside `TestAsyncSafeRunIntegration` (legacy SUT) — the
Shard 1 agent MUST re-grep the file at move time and only move lines that
still target the current SUT.

**Amendment** — replace Shard 1 step 5 sub-bullet "Move helper-existence

- sync-context tests (lines 50-145, 321-365, 562-606)..." with:

> - At move time, the Shard 1 agent MUST re-grep `tests/integration/migrations/test_async_safe_run_integration.py`
>   to enumerate tests targeting:
>   - `dataflow.core.async_utils.async_safe_run` (still exists at line 121 of `async_utils.py`)
>   - `dataflow.core.async_utils.get_execution_context` (still exists at line 80)
>   - sync `_execute_workflow_safe` (current behavior per `auto_migration_system.py:40-114`)
>
>   Tests targeting any of these THREE current SUTs move to
>   `tests/unit/migrations/test_async_safe_run.py`. Tests targeting
>   removed-code paths (the OLD async-loop bridging that no longer
>   exists) are deleted with explicit rationale in the commit body.
>   Hand-cited line ranges from this plan are SUGGESTIONS, not contracts.

## A9 — `test_original_bug_scenario` assertion simplification

**Source**: DF-R2-3.

The existing `test_original_bug_scenario` asserts `"thread" in error_str`
in an `except` arm — but the current sync helper doesn't thread, so the
except branch is dead code. Per `rules/zero-tolerance.md` Rule 6
(implement fully — no dead branches).

**Amendment** — when moving the test to `tests/regression/`:

> Simplify the assertion to retain only the live-path check (e.g.,
> `assert "bug_repro" in results` or whatever the live-path success
> condition is per the current sync `_execute_workflow_safe`). Drop
> the dead `except` arm (`"thread" in error_str` check).
> Per `rules/testing.md` § MUST: Behavioral Regression Tests, the
> assertion must reflect current behavior.

## A10 — Tier-1 extract is NOT duplicate of singular real-PG file (clarification)

**Source**: DF-R2-1.

Singular-dir file `tests/integration/migration/test_migration_lock_manager_integration.py:419-528`
has `TestConnectionAdapterIntegration` with `test_parameter_conversion_with_real_queries`
that targets the SAME SUT (`ConnectionManagerAdapter._convert_parameters`) but
at Tier-2 (real PG). v2's planned Tier-1 extract at
`tests/unit/migrations/test_connection_adapter_param_conversion.py` covers the
same SUT at Tier-1 (pure string algorithm, no infra).

**Both can coexist** — they exercise the same SUT at different tiers:

- Tier-1: pure-string conversion correctness (40+ edge cases from
  `TestConnectionManagerAdapter` + `TestParameterConversionEdgeCases`)
- Tier-2: real-PG round-trip (singular file's narrower set)

**Amendment** — Shard 2 description gets a clarifying note:

> The Tier-1 extract is NOT duplicate of the singular-dir file. The two
> files test the same SUT at different tiers — Tier-1 covers the wide
> set of pure-string edge cases (40+); Tier-2 in the singular file
> covers the narrower real-PG round-trip subset. Both are required per
> `rules/testing.md` § One Direct Test Per Variant (different tier =
> different variant) and the canonical 3-tier strategy.

## A11 — Shard 1 invariant count is 9, not 7 (still within budget)

**Source**: architecture N-2.

v2 says Shard 1 has 7 invariants. Walked list has 9 (the 7 listed + File 4
sub-invariants + File 9 rename sub-invariant). Per `rules/autonomous-execution.md`
MUST-1, ≤10 invariants is the cap; 9 is within budget.

**Amendment**: Shard 1 invariant counter in v2 table header: "9" not "7".

## A12 — Cluster A is "7 moves + 1 split"

**Source**: architecture N-3.

v2 § Shard 1 says "8 Tier-1 moves." More precisely: 7 are pure moves; File 4
is a 1-source → 2-destination split (`tests/unit/migrations/test_async_safe_run.py`

- `tests/regression/test_issue_dataflow_async_safe_run_no_event_loop_bridge.py`).

**Amendment**: Shard 1 description in v2 table header: "7 Tier-1 moves + 1
Tier-1/regression split (File 4)."

## Post-amendment verdict

Round 2 verdicts (APPROVE-WITH-FIXES × 3) become APPROVE × 3 after these
12 amendments land. No Round 3 needed unless new evidence surfaces.

The plan is ready for `/todos` (structural human gate).

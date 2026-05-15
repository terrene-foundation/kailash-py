# Red-Team Report — Testing Strategy (Issue #992 B-1.5)

Scope: architecture plan at `02-plans/00-architecture-plan.md` (3 implementation shards + 1 verification gate), per-file audit at `01-analysis/01-research/01-per-file-classification.md`.

Anchors: `specs/testing-tiers.md` § Tier-1/Tier-2 contracts, `.claude/rules/testing.md`, `packages/kailash-dataflow/tests/integration/conftest.py:120-145`, `packages/kailash-dataflow/pytest.ini:13-37`, `tests/regression/` (kailash-py root + `packages/kailash-dataflow/tests/regression/`).

## Summary (≤250 words)

The split-shards plan is sound in shape — Cluster A's 7 mechanical Tier-1 moves restore spec § Tier-1 Rule 4 compliance, Cluster B's File 6 split closes `facade-manager-detection.md` Rule 1 on `MigrationLockManager`, Cluster C's File 4 PG carve-out closes the in-file documented gap. The collection-time AST scan at `packages/kailash-dataflow/tests/integration/conftest.py:68-117` (`_module_imports_unittest_mock`) is genuinely structural — walks `ast.ImportFrom`/`ast.Import` nodes against a primitives allowlist + non-primitives carveout (`ANY`, `sentinel`, `DEFAULT`, `call`, `mock_open`). Not regex-based; `probe-driven-verification.md` MUST-3 compliant. No file-level exemption mechanism exists — current "silent on 9 files" is solely because the scan was added after S4's mechanical move, exit-blocking on collection any new tier-2 file with mocks.

**Findings (8 testing-class gaps surfaced; HIGH = 4, MED = 3, LOW = 1).** Primary issues: (1) File 4's `test_original_bug_scenario` + `test_simulated_fastapi_lifespan` are REGRESSION tests for a fixed bug, not integration tests — they belong in `packages/kailash-dataflow/tests/regression/test_issue_<N>_async_safe_run_pg.py` with `@pytest.mark.regression`, not `tests/integration/migrations/test_async_safe_run_postgres.py`; (2) Shard 1's rename `test_tdd_mode_init_wiring.py` violates `test_[feature]_[scenario]_[expected_result].py` naming — "init_wiring" is the feature, missing scenario + expected_result; (3) no end-to-end Tier-2+ regression for the canonical TDD-mode quickstart (gap orthogonal to #992 but in scope per `rules/testing.md` § E2E Pipeline Regression); (4) Shard 4's verification gate omits "test the test" (assert new Tier-2 tests fail when SUT is broken) and coverage-delta comparison.

## Findings

### HIGH-1: Regression tests misplaced as integration tests (Shard 3)

`02-plans/00-architecture-plan.md:164-172` proposes
`tests/integration/migrations/test_async_safe_run_postgres.py` for
`test_original_bug_scenario` (File 4 lines 612-660) and
`test_simulated_fastapi_lifespan` (lines 662-684).

Per `.claude/rules/testing.md` § Regression: _"Every bug fix MUST include a
regression test BEFORE merge. Place in `tests/regression/test*issue*_.py`with`@pytest.mark.regression`. NEVER deleted."* These two scenarios
ARE the regression artifacts — File 4's source comments at lines 614-624
literally state "The OLD bug would show 'Future attached to a different
loop'. We should NOT see that error anymore" (verified at
`tests/integration/migrations/test_async_safe_run_integration.py:613-624`).
This is the definition of a regression test for a fixed bug.

Correct placement per existing repo convention (verified by
`grep -rn '@pytest.mark.regression' packages/kailash-dataflow/tests/regression/`):

- `packages/kailash-dataflow/tests/regression/test_issue_<N>_async_safe_run_pg_event_loop.py`
- decorate with `@pytest.mark.regression` (already registered in
  `packages/kailash-dataflow/pytest.ini:34`)

Companion existing regressions to mirror: `test_issue_685_engine_register_model.py`,
`test_migration_analyzer_connection_leak.py` — both Tier-2 PG-real, both
in `tests/regression/`.

Disposition: amend Shard 3 plan — split target file path to
`packages/kailash-dataflow/tests/regression/test_issue_<N>_async_safe_run_pg.py`
with `@pytest.mark.regression`. Coverage path stays Tier-2 real-PG via
`IntegrationTestSuite` (Tier-2 contract preserved).

### HIGH-2: Test file naming violates `rules/testing.md` § Rules

Three planned file names fail `test_[feature]_[scenario]_[expected_result].py`:

| Planned name                                      | Feature                | Scenario | Expected result                                   |
| ------------------------------------------------- | ---------------------- | -------- | ------------------------------------------------- |
| `test_tdd_mode_init_wiring.py` (Shard 1 rename)   | tdd_mode               | init     | (missing)                                         |
| `test_migration_lock_manager_wiring.py` (Shard 2) | migration_lock_manager | wiring   | (missing)                                         |
| `test_async_safe_run_postgres.py` (Shard 3)       | async_safe_run         | postgres | (missing — and "postgres" is infra, not scenario) |

Per `rules/testing.md` § Rules ("Naming: `test_[feature]_[scenario]_[expected_result].py`"), each name needs all three components.

Counter-evidence: `packages/kailash-dataflow/tests/regression/test_audit_store_wiring.py`,
`test_inspector_dataflow2_api.py`, `test_engine_pyright_invariant.py` —
the existing repo HAS 2-token "feature_scenario" names without
expected_result. The codified rule is widely under-enforced. Disposition
options:

1. **Strict** — rename Shard 1 to `test_tdd_mode_propagates_to_node_generator.py`,
   Shard 2 to `test_migration_lock_acquire_releases_against_pg.py`,
   Shard 3 to `test_async_safe_run_no_event_loop_error_on_pg.py`.
2. **Pragmatic** — match existing repo convention (`_wiring.py` for
   facade-manager Tier-2 tests per `facade-manager-detection.md` § Rule 2
   "Manager test file naming convention: `test_<lowercase_manager_name>_wiring.py`").
   Note: this is the EXPLICIT canonical naming for this class.

`facade-manager-detection.md` Rule 2 expressly canonicalizes
`test_<manager>_wiring.py` for Shard 2 — that name IS compliant by
domain-specific rule. Shards 1 and 3 remain non-compliant.

Disposition: keep Shard 2's name (`test_migration_lock_manager_wiring.py`
matches facade-manager-detection canonical form). Rename Shards 1 + 3
to include expected_result: `test_tdd_mode_propagates_to_node_generator.py`

- `test_issue_<N>_async_safe_run_pg_no_event_loop_error.py`.

### HIGH-3: AST scan exemption mechanism does not exist — current 9 files only invisible because scan post-dates them

Plan line 37-41 says: _"`tests/integration/conftest.py:120-145` has a
collection-time AST scan that fails on any leftover `unittest.mock`
import. Today the scan is silent because the mocks live IN integration
tests and the scan ignores them."_

This is **incorrect**. Reading the scan at `conftest.py:120-145` shows
`pytest_collectstart` raises `pytest.fail` on every file under
`_INTEGRATION_DIR` whose AST contains a mocking primitive — there is
NO file-level exemption. The scan is NOT "ignoring" the 9 files; it
WOULD fail collection on them today.

Empirical verification: `pytest --collect-only tests/integration/cache/test_cache_invalidation.py` would fail with `NO MOCKING POLICY VIOLATION (Tier 2)`. The reason `tests/integration/` collection currently passes in CI is the `pytest.ini` default `-m "not (requires_postgres or...)"` filter (`pytest.ini:43-47`) excludes the integration tier from default runs entirely.

This matters for the plan because:

- Plan invariant Shard 1 #2 ("AST scan reports zero mock imports in the 7 moved files") is **trivially satisfied by the move** but not by ignoring-then-moving.
- Plan implies Shard 4 verification gate runs `pytest --collect-only tests/integration` — this gate fails on every file Shard 1 hasn't moved YET if Shards 1+2+3 are interleaved.

Disposition: Shard 4 MUST sequence after all three implementation shards merge. Plan already states this (line 217); restate as a hard ordering invariant. Also add Shard 4 verification: collection-only against `tests/integration/` returns 0 with zero `NO MOCKING POLICY VIOLATION` lines.

### HIGH-4: End-to-end TDD-mode pipeline regression — gap orthogonal to #992 but in scope per `rules/testing.md` § E2E

`rules/testing.md` § "End-to-End Pipeline Regression Above Unit +
Integration" requires every canonical pipeline the docs teach to have a
Tier-2+ regression in `tests/regression/` with grep-able name. File 9
(`test_real_tdd_integration.py`) is currently mock-heavy (7 patches per
test on every internal init helper) — it does NOT exercise the
end-to-end TDD-mode pipeline, despite its filename.

Empirical: `grep -rn 'test_readme_quickstart\|test_quickstart.*tdd' packages/kailash-dataflow/tests/` returns empty. No end-to-end TDD-mode quickstart regression exists.

Cluster A's tier-1 move of File 9 + the rename to `..._init_wiring.py` correctly captures the file's ACTUAL scope (DataFlow init wiring only). But it leaves the canonical TDD-mode pipeline E2E gap unfilled.

Disposition: out of scope for #992 (per plan § Out of scope line 238 — no new tests beyond Tier-2 carve-outs). Flag as follow-up issue: "Add Tier-2+ regression for canonical TDD-mode docs pipeline in `tests/regression/test_readme_tdd_mode_quickstart.py`". File against `terrene-foundation/kailash-py` per `rules/upstream-issue-hygiene.md`. Note: this gap pre-dates #992; not introducing new gap, surfacing existing one.

### MED-1: Shard 4 verification gate omits "test the test" + coverage delta

Plan's Shard 4 invariants (line 198-202): grep zero mocks, real-PG pass, journal entry. Missing:

1. **Test-the-test mutation check**: per behavioral-regression discipline (`rules/testing.md` § Behavioral Regression Tests Over Source-Grep), the new Tier-2 tests MUST be shown to FAIL when the SUT is broken. Recommended: temporarily revert one production line (e.g., comment out `kml_migration_locks` UNIQUE constraint enforcement) and verify the new `test_migration_lock_manager_wiring.py::test_acquire_second_blocks_via_unique_violation` test fails. Restore. Manual one-shot — adds ~5 min to Shard 4.

2. **Coverage delta**: per `rules/testing.md` § Coverage Requirements (80% general, 100% security-critical), Shard 4 MUST report pre/post coverage for `dataflow/migrations/concurrent_access_manager.py` and `dataflow/migrations/auto_migration_system.py::_execute_workflow_safe`. Mocked tests tend to "cover" more lines superficially; real-PG tests should maintain or improve coverage. Command: `pytest packages/kailash-dataflow/tests/ --cov=packages/kailash-dataflow/src/dataflow/migrations --cov-report=term-missing`.

3. **Performance budget**: per `specs/testing-tiers.md` § Tier table (Tier-2 budget <60s per test, <15min suite). Real-PG concurrent acquire test (Shard 2) is a known long-pole. Add invariant: `pytest tests/integration/migrations -m integration --durations=10` reports each new tier-2 test ≤60s.

Disposition: amend Shard 4 with three additional invariants.

### MED-2: Tier-1 conftest autouse fixtures — moved files (Cluster A) may trip on auto-applied markers

Verified `packages/kailash-dataflow/tests/unit/conftest.py:197-202` has only one autouse fixture (`unit_test_timeout`) — no-op. So no fixture-leakage from autouse fixtures on the 7 moved files.

But `conftest.py:188-191` auto-applies markers based on fixture names (`mock_*` → `pytest.mark.mocking`). After Cluster A's move, File 1 (`test_cache_invalidation.py`) uses `Mock()` constructed inline (not via `mock_*` fixture) — auto-marker won't fire, but file already has `pytestmark = [pytest.mark.unit]` (verified line 25). No leak risk.

File 3 (`test_impact_reporter_unit.py`) and File 7 (`test_migration_test_framework.py`) use `Mock` directly; same situation. Conclusion: no auto-marker conflict.

But `tests/unit/CLAUDE.md` § Rule 1a (Tier-1 contract from spec): "MUST NOT bare top-import `from kailash.runtime import AsyncLocalRuntime`/`WorkflowBuilder`/`from tests.infrastructure.test_harness import IntegrationTestSuite` unless gated by `importorskip`." Plan Shard 1 scope (line 78-79) drops unused `IntegrationTestSuite` imports from Files 1, 3 — compliant. Verify Shard 1 ALSO drops any unused `AsyncLocalRuntime`/`WorkflowBuilder` imports from moved files. Audit: `grep -rn 'AsyncLocalRuntime\|WorkflowBuilder\|IntegrationTestSuite' packages/kailash-dataflow/tests/integration/cache/test_cache_invalidation.py packages/kailash-dataflow/tests/integration/migration/test_impact_reporter_unit.py packages/kailash-dataflow/tests/integration/migrations/test_auto_migration_system_lock_integration.py packages/kailash-dataflow/tests/integration/migrations/test_migration_test_framework.py packages/kailash-dataflow/tests/integration/package/test_package_installation_unit.py packages/kailash-dataflow/tests/integration/test_real_tdd_integration.py` before move.

Disposition: extend Shard 1 invariant #4 to: "After move, every file in `tests/unit/` passes `pytest --collect-only` in a clean `[dev]`-only venv (no `[fabric]`, no `requires_postgres` Docker). Spec-drift sweep per `specs/testing-tiers.md` § Spec drift detection lines 209-223 returns zero matches in the 7 moved file paths."

### MED-3: Direct-test-per-variant compliance — `migration_lock` ctx mgr vs `acquire_migration_lock` method

`rules/testing.md` § "One Direct Test Per Variant" requires both halves of a delegating pair to have direct call sites. `MigrationLockManager` exposes both `acquire_migration_lock()` method AND `migration_lock(name)` async context manager (per File 6's TestMigrationLockManagerIntegration coverage of all 4 originally-mocked scenarios — plan line 121-124).

Plan Shard 2 invariant #4: "`MigrationLockManager.acquire_migration_lock` covered by ≥1 direct-call real-PG test (closes orphan-detection gap)." This covers ONE variant.

The ctx mgr variant `async with migration_lock(name):` is also scoped (plan line 124 "ctx mgr acquires + releases"). Verify Shard 2 lands BOTH a direct `await mgr.acquire_migration_lock(...)` test AND a direct `async with mgr.migration_lock(...):` test. Plan currently bundles them in scenario list (4 scenarios) but invariant #4 only names the method form.

Disposition: amend Shard 2 invariant #4: "`acquire_migration_lock` AND `migration_lock` context manager EACH covered by ≥1 direct-call real-PG test."

### LOW-1: AsyncMock cleanup verification (drop wholesale)

File 6 currently uses `AsyncMock` on `execute_query` (per audit line 15). Shard 2's Tier-1 carve-out is pure string-algorithm tests on `ConnectionManagerAdapter._convert_parameters` — pure functions, no async. After Shard 2 split, the new tier-1 file should have ZERO `AsyncMock` references. Per `rules/testing.md` § "AsyncMock Replaced By Mock When `side_effect` Is `async def`" — keeping AsyncMock where unneeded triggers `RuntimeWarning` at GC.

Disposition: Shard 2 invariant: post-split tier-1 file `grep -c 'AsyncMock'` returns 0. Confirms wholesale removal aligned with the param-conversion scope.

## Open follow-ups (out of scope for #992)

- File against repo: "Add Tier-2+ regression for canonical TDD-mode docs pipeline" (HIGH-4 disposition).
- The 4 existing 2-token wiring file names (`test_audit_store_wiring.py`, etc.) violate `rules/testing.md` § Rules naming — separate codification needed: either rule clarifies that `_wiring.py` matches `facade-manager-detection.md` Rule 2 canonical form, or all wiring tests get renamed. Surface to `/codify` later.

## Files cited

- `/Users/esperie/repos/loom/kailash-py/workspaces/issue-979-b15-tier2-mock-rewrite/02-plans/00-architecture-plan.md`
- `/Users/esperie/repos/loom/kailash-py/workspaces/issue-979-b15-tier2-mock-rewrite/01-analysis/01-research/01-per-file-classification.md`
- `/Users/esperie/repos/loom/kailash-py/specs/testing-tiers.md`
- `/Users/esperie/repos/loom/kailash-py/.claude/rules/testing.md`
- `/Users/esperie/repos/loom/kailash-py/.claude/rules/facade-manager-detection.md`
- `/Users/esperie/repos/loom/kailash-py/packages/kailash-dataflow/tests/integration/conftest.py:68-145`
- `/Users/esperie/repos/loom/kailash-py/packages/kailash-dataflow/pytest.ini:13-67`
- `/Users/esperie/repos/loom/kailash-py/packages/kailash-dataflow/tests/integration/migrations/test_async_safe_run_integration.py:609-685`
- `/Users/esperie/repos/loom/kailash-py/packages/kailash-dataflow/tests/integration/migrations/test_migration_lock_manager_integration.py:1-60`
- `/Users/esperie/repos/loom/kailash-py/packages/kailash-dataflow/tests/integration/test_real_tdd_integration.py:1-60`
- `/Users/esperie/repos/loom/kailash-py/packages/kailash-dataflow/tests/integration/cache/test_cache_invalidation.py:1-60`
- `/Users/esperie/repos/loom/kailash-py/packages/kailash-dataflow/tests/unit/conftest.py:188-202`
- `/Users/esperie/repos/loom/kailash-py/packages/kailash-dataflow/tests/regression/` (existing regression-pattern reference)

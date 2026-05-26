# Red-Team Round 2 — Testing Perspective (v2 plan, issue #992 B-1.5)

Scope: `02-plans/01-architecture-plan-v2.md` vs Round-1 findings at `04-validate/03-redteam-testing.md` (4 HIGH).

## Round-1 disposition

- **HIGH-1 (regression placement)** — **CLOSED**. v2 §Shard 1 step 5 moves `test_original_bug_scenario` to `packages/kailash-dataflow/tests/regression/test_issue_async_safe_run_no_event_loop_bridge.py` with `@pytest.mark.regression` (plan lines 92-96).
- **HIGH-2 (naming)** — **CLOSED**. File 9 renamed to `test_tdd_mode_propagates_to_node_generator.py` (plan line 99). Shards 2/3 from v1 dropped.
- **HIGH-3 (AST scan sequencing)** — **CLOSED**. Shard 3 strictly sequenced after Shards 1+2 merge (plan lines 162-170).
- **HIGH-4 (E2E TDD-mode regression gap)** — **LEFT UNCLOSED**. v2 §Open Questions (line 267) says "None"; HIGH-4 was deferred-out-of-scope in Round 1 but v2 omits the follow-up-issue acknowledgement.

## New Round-2 findings

### HIGH-R2-1: regression filename omits issue number (`rules/testing.md` § Regression naming)

`rules/testing.md` § Regression: `tests/regression/test_issue_*.py`. v2 uses `test_issue_async_safe_run_no_event_loop_bridge.py` (no `<N>`). Existing precedent in repo uses both forms (e.g., `test_issue_685_engine_register_model.py` AND `test_audit_store_wiring.py`); the GH-issue this fix originally closed is unknown (v0.10.11 fix, pre-#992). Disposition: rename to `test_issue_dataflow_async_safe_run_no_event_loop_bridge.py` (slug-form preserves grep-ability when issue-N unknown) OR locate the originating GH issue and use its number. Cite in plan.

### HIGH-R2-2: `test_original_bug_scenario` tests dead code

`packages/kailash-dataflow/tests/integration/migrations/test_async_safe_run_integration.py:625-660` directly imports `_execute_workflow_safe` and calls it. Per v2 §Why bullet 2: this function is now sync (`SyncDDLExecutor`). Verified: the test still imports it (line 627). The test exercises the CURRENT sync code path — the assertion "old bug not present" is still valid against the current implementation. **Disposition: KEEP AS-IS** when moving to `tests/regression/`, because the test invokes the live symbol and asserts no `"future attached to a different loop"` in the error string. Not dead code per `rules/testing.md` § Behavioral Regression.

### HIGH-R2-3: test-count math — Shard 1 invariant 1 underspecified

Cross-tier delta: File 4 has 39 test functions across 11 classes (verified `grep -cE "@pytest.mark|def test_"`). Shard 1 splits: helper/sync-context tests (lines 50-145, 321-365, 562-606 — ~3 classes worth) → `tests/unit/`; `test_original_bug_scenario` (1 test) → `tests/regression/`; `test_simulated_fastapi_lifespan` (1 test) → **DELETED**. Net cross-tier sum = pre-move count MINUS 1. Plan invariant 1 (line 106) says "cross-tier sum = pre-move collection count" — **MUST be amended** to "= pre-move count − 1 (deleted smoke test)" OR plan must record the deletion as a separate accounting line. Currently invariant 1 is unverifiable as written.

### MED-R2-1: conftest autouse fixture leakage acceptable

`tests/unit/conftest.py:197-202` `unit_test_timeout` is no-op; `:180-191` auto-applies `pytest.mark.unit` + sqlite*memory/file/mocking markers based on fixture name prefix. Files 1-9 don't use `memory*_`/`file\__`/`mock\_\*` fixtures (they construct Mock() inline). No leakage. **CLOSED**.

### MED-R2-2: regression marker registered

`packages/kailash-dataflow/pytest.ini:33` registers `regression: Regression tests for fixed bugs (permanent, never delete)`. Marker exists; `pyproject.toml` has no competing `[tool.pytest.ini_options]` block (line 186-193 confirms pytest.ini is canonical). **CLOSED**.

### MED-R2-3: AST scan line citation drift

v2 cites `conftest.py:68-117` (plan line 168, 178) AND `conftest.py:120-145` (plan line 114). Verified: lines 68-117 are `_module_imports_unittest_mock()` AST walker; lines 120-145 are `pytest_collectstart` hook. Both are part of the scan but only `pytest_collectstart` raises on hit. Plan should cite the full range `68-145` consistently. Minor.

### MED-R2-4: tier-1 performance budget not validated

Shards 1+2 add ~128 mocked test count to tier-1 (`tests/unit/`). Per `specs/testing-tiers.md` § Tier-1 Contract: <2 min budget. Tier-1 is currently single-machine `pytest --timeout=1`. 128 added tests × ~50ms median (Mock-based) = ~6s — well under budget. Tier-2 becomes faster (fewer tests + faster real-PG suite). **CLOSED — no performance regression risk.**

### LOW-R2-1: HIGH-4 (E2E TDD-mode regression) silently dropped

Round-1 HIGH-4 flagged: no end-to-end TDD-mode Tier-2+ regression exists. v2 omits acknowledgement in §Out-of-scope (line 284-296) OR §Open Questions (line 267). Per `rules/value-prioritization.md` MUST-2 (deferred items carry value-anchors that survive `/clear`), this gap should be recorded with a follow-up issue note: "Filed follow-up: Add Tier-2+ regression for canonical TDD-mode docs pipeline at `tests/regression/test_readme_tdd_mode_quickstart.py`". Disposition: add one line to v2 §Out-of-scope acknowledging HIGH-4 disposition.

## Summary

- **CLOSED**: 3 of 4 Round-1 HIGH (1, 2, 3).
- **LEFT UNCLOSED**: HIGH-4 — needs acknowledgement line in v2.
- **NEW HIGH**: 2 (R2-1 regression-filename `<N>` slot; R2-3 test-count math missing the −1 for deleted smoke test).
- **NEW MED**: 1 advisory (R2-3 line-range citation drift).

v2 is structurally close to ship-ready. Two amendments before Shard 1 launch:

1. Amend invariant 1 to account for the deleted `test_simulated_fastapi_lifespan` (net −1 cross-tier).
2. Either locate the originating issue number for the regression file OR use `test_issue_dataflow_async_safe_run_no_event_loop_bridge.py`.
3. Record HIGH-4 follow-up in §Out-of-scope.

## Files cited

- `/Users/esperie/repos/loom/kailash-py/workspaces/issue-979-b15-tier2-mock-rewrite/02-plans/01-architecture-plan-v2.md`
- `/Users/esperie/repos/loom/kailash-py/workspaces/issue-979-b15-tier2-mock-rewrite/04-validate/03-redteam-testing.md`
- `/Users/esperie/repos/loom/kailash-py/packages/kailash-dataflow/tests/integration/conftest.py:68-145`
- `/Users/esperie/repos/loom/kailash-py/packages/kailash-dataflow/pytest.ini:14-37`
- `/Users/esperie/repos/loom/kailash-py/packages/kailash-dataflow/pyproject.toml:186-193`
- `/Users/esperie/repos/loom/kailash-py/packages/kailash-dataflow/tests/integration/migrations/test_async_safe_run_integration.py:609-685`
- `/Users/esperie/repos/loom/kailash-py/packages/kailash-dataflow/tests/unit/conftest.py:180-202`

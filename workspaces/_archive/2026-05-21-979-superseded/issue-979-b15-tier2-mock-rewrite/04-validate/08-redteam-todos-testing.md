# Red Team — S1/S2/S3 Todos, Testing Angle (≤200 words)

Verdict: **APPROVE with 1 LOW**.

1. **Tier-1 contract (Q1)**: Moved files satisfy `specs/testing-tiers.md` §Tier-1: SQLite/mocks allowed, <1s (pure-Python algos), no PG/Redis. PASS.

2. **Conftest autouse leakage (Q2)**: `tests/unit/conftest.py:197` is a no-op timeout fixture (per `unit/conftest.py:200-205`). No state-mutating autouse. File 9's new path `tests/unit/core/test_tdd_mode_propagates_to_node_generator.py` inherits safely. PASS.

3. **Regression marker (Q3)**: Registered at `packages/kailash-dataflow/pytest.ini:34` — `regression: Regression tests for fixed bugs`. PASS.

4. **Regression collision (Q4)**: `ls tests/regression/` shows 50+ `test_issue_*.py` files; **no clash** with proposed `test_issue_dataflow_async_safe_run_no_event_loop_bridge.py`. PASS.

5. **Test-once protocol (Q5)**: S1 verification uses pre/post `--collect-only` (count comparison, not execution). S3 runs collection ONCE. PASS.

6. **Verified numerical claims (Q6)**: S1 Invariant 1 explicitly mandates verifying command. S2 Invariant 1 same. PASS.

7. **AST scan trigger (Q7)**: `pytest_collectstart` (`tests/integration/conftest.py:120`) FIRES on `--collect-only` — pytest invokes collectors regardless of execute flag. PASS.

8. **AC #4 traceability (Q8)**: 2+1 sessions ≈ "~3 sessions". PASS.

9. **Deliverable verification (Q9)** — **LOW**: S1/S2 worktree-launch blocks lack explicit post-exit `ls`/`Read` step per `worktree-isolation.md` Rule 3. Implicit in orchestrator protocol; recommend adding 1-line "STEP N+1: parent verifies merged files via `git ls-files`" to S1/S2.

10. **Behavioral regression (Q10)**: `test_original_bug_scenario` (lines 613-660) calls `_execute_workflow_safe(workflow)`, asserts on `error_str` content + result dict — BEHAVIORAL, not source-grep. A9 simplification preserves this. PASS.

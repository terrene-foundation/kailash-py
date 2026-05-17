# 0001 — DELIVERY: research_patterns/\* test parity (#821)

**Date:** 2026-05-05
**Branch:** `fix/issue-821-research-patterns-tests`
**PR:** #824 — `Fixes #821`

## What landed

Three Tier-1 unit-test files + `__init__.py` at
`packages/kaizen-agents/tests/unit/research_patterns/`:

- `test_advanced_patterns.py` — 35 tests covering `AdvancedPatternBuilder`,
  `CompositionalPattern`, `HierarchicalPattern`, `AdaptivePattern`,
  `MetaLearningPattern`, plus enum smoke for `PatternStrategy` /
  `AdaptationStrategy` / `LearningStrategy`.
- `test_experimental.py` — 30 tests covering `ExperimentalFeature`
  construction, enable/disable, execute happy + error paths, full
  lifecycle transition table (5 valid + 7 invalid via parametrize), and
  `get_documentation()` markdown shape.
- `test_intelligent_optimizer.py` — 17 tests covering
  `IntelligentOptimizer.__init__` defaults + overrides, `optimize`
  dispatch on `bayesian` / `genetic` / `multi_objective` / unknown,
  RL methods (`select_action`, `update_policy`, `get_policy`), and
  `_dominates` predicate.

**Total: 82 tests, 0.15s wall-clock, 0 failures.**

Commit `2490352a` — 4 files changed, 825 insertions(+).

## Verification commands run

```bash
uv run pytest --collect-only -q packages/kaizen-agents/tests/   # 3,359 tests collected, exit 0
uv run pytest packages/kaizen-agents/tests/unit/research_patterns/ -q  # 82 passed in 0.15s
uv run pre-commit run --files <new files>                        # all hooks pass
```

## Findings during implementation

1. **Brief LOC estimate was high.** Issue #821 stated `~1500 LOC of pattern-builder
logic`. Actual: 347 + 231 + 206 = 784 LOC of source. Did not change the
   shard-budget calculation; surface the correction in PR description.
2. **`Signature` shape required `inputs`/`outputs`.** Naive `class _Stub(Signature): pass`
   raises `ValueError: Either define fields as class attributes or provide
inputs/outputs`. Stub provides minimal `inputs=["query"], outputs=["result"]`
   and overrides `execute(**kwargs) -> dict` to record the call.
3. **Pyright surfaced unused `pytest` import** in `test_intelligent_optimizer.py`
   on first write — removed before commit.
4. **Pre-commit black + isort** auto-formatted on first invocation;
   re-stage + re-run produced clean pass.
5. **Unrelated unit-suite slowness.** Full
   `pytest packages/kaizen-agents/tests/unit/` ran with ~1% CPU at minute
   3+, suggesting a hung/blocking fixture in the existing kaizen-agents
   suite. Killed; no impact on #821 ACs since the new tests are isolated
   to a new directory and pass in 0.15s on their own. Not filed (not in
   #821 scope; would need separate investigation to root-cause).

## Cross-SDK inspection

`rules/cross-sdk-inspection.md` Rule 5 checklist:

- kailash-rs has `crates/kaizen-agents/src/agents/research.rs` — a
  `ResearchAgent` doing LLM-driven multi-step research workflow.
- **Not analogous** to kailash-py's `research_patterns/*`
  (compositional / hierarchical / adaptive / meta-learning pattern
  builders). Different domain.
- No cross-SDK action needed.

## Out of scope (carried forward)

- Issue #822 (Optional/None typing cascade in `kaizen/__init__.py` +
  `core/framework.py` + `core/agents.py`). Multi-shard; needs `/analyze`.
- Pre-existing `uv.lock` modifications in working tree (root +
  `packages/kailash-kaizen/`).
- The kaizen-agents unit-suite slowness observed during regression
  check (not a regression introduced by this PR).

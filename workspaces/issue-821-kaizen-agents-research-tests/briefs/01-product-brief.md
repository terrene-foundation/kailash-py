# Product Brief — Issue #821

## Source

GitHub: terrene-foundation/kailash-py#821 — `test(kaizen-agents): add coverage
for research_patterns/ moved in PR #75`. Filed as a follow-up during issue
#814 (kailash-kaizen 2.18.2). Severity LOW; area/quality.

## Background

PR #75 (commit `801de2bb`, 2026-03-25) moved three modules from
`packages/kailash-kaizen/src/kaizen/research/` to
`packages/kaizen-agents/src/kaizen_agents/research_patterns/`:

- `advanced_patterns.py`
- `experimental.py`
- `intelligent_optimizer.py`

The corresponding test files at
`packages/kailash-kaizen/tests/unit/research/test_*.py` did NOT move — they
remained at the old path importing the deleted source modules. Issue #814
Shard 2 (PR #820) deleted those orphan test files.

`packages/kaizen-agents/` currently has zero unit-test coverage for
`research_patterns/*`. ~1500 LOC of pattern-builder logic with no
automated regression coverage since the move ~6 weeks ago.

## Objective

Re-establish unit-test parity at the new home. Create three test files
under `packages/kaizen-agents/tests/unit/research_patterns/` that exercise
the canonical surface of each moved module.

## Acceptance Criteria (from issue)

- [ ] `tests/unit/research_patterns/test_advanced_patterns.py` exercises
      `AdvancedPatternBuilder`, `CompositionalPattern`, `HierarchicalPattern`,
      `AdaptivePattern`, `MetaLearningPattern` — construction + canonical
      method paths.
- [ ] `tests/unit/research_patterns/test_experimental.py` exercises
      `ExperimentalFeature`.
- [ ] `tests/unit/research_patterns/test_intelligent_optimizer.py` exercises
      `IntelligentOptimizer`.
- [ ] `pytest --collect-only -q packages/kaizen-agents/tests/` exits 0
      across the new test files.

Implicit AC: tests must actually pass, not just collect.

## Constraints

- Tier 1 (unit) tests only. Per `rules/testing.md`, mocks are allowed at
  Tier 1 for downstream framework dependencies; Tiers 2-3 forbid mocking.
- Follow the existing `packages/kaizen-agents/tests/unit/` layout
  conventions; do NOT introduce a new test architecture.
- No commercial references (Foundation Independence).
- No stubs / no `pass # placeholder` / no `raise NotImplementedError` in
  test bodies (`rules/zero-tolerance.md` Rule 2).
- Helper classes use `*Stub` / `*Helper` / `*Fake` suffix — never
  `class Test*` with `__init__` (pytest collection silently drops those).

## Out of scope

- Issue #822 (Optional/None typing cascade) — separate workstream.
- Backfilling Tier 2/3 integration coverage for these modules — only
  Tier 1 unit-level parity is asked for.
- Re-architecting `research_patterns/*` — surface stays as-is.
- Pre-existing `uv.lock` modifications in working tree (root +
  `packages/kailash-kaizen/`) — defer to a separate cleanup batch.

## Tech stack

- Python 3.11+, pytest, kailash-kaizen / kaizen-agents packages.
- No DB, no API — pure unit tests.
- Test runner:
  `uv run pytest packages/kaizen-agents/tests/unit/research_patterns/`.

## Users

- Maintainers of `packages/kaizen-agents/` — protected from regressions
  on `research_patterns/*` after this lands.

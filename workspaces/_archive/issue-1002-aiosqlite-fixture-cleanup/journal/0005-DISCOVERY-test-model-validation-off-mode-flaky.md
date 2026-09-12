# 0005 DISCOVERY — `test_validation_off_mode_no_checks` is test-order-flaky (pre-existing, Shard 3 owns the fix)

Date: 2026-05-14
Phase: /implement Shard 1 (CI inspection)

## Finding

PR #1004 generated two CI runs on the same commits — one push-triggered (`25860260947`) and one pull_request-triggered (`25860280925`). The push run reported `Test DataFlow Unit Suite (Tier 1) FAIL`; the PR run reported the same lane `PASS`. The latest-per-check status (via `gh pr view 1004 --json statusCheckRollup`) shows all 16 checks at SUCCESS on the PR-trigger run.

Failure detail from the push run:

```
FAILED tests/unit/test_model_validation.py::TestValidationModes::test_validation_off_mode_no_checks
  - assert 6 == 0
  + where 6 = len([... <6 WarningMessage objects> ...])
=========== 1 failed, 3044 passed, 98 skipped, 46 warnings in 54.78s ===========
```

The test (`packages/kailash-dataflow/tests/unit/test_model_validation.py:340-360`-ish, per `git show main:`) asserts `len(w) == 0` where `w = warnings.catch_warnings(record=True)`. Surrounding warnings in the run log include 5 `DataFlowValidationWarning` (`[VAL-007]` and `[VAL-008]` from a sibling test model named `Order` with `userName` camelCase field) plus 1 `DeprecationWarning` from the `MLTenantRequiredError` alias.

## Pre-existing verification

`git show main:packages/kailash-dataflow/tests/unit/test_model_validation.py` confirms the test exists on main commit `b553104c` (a 2024-era monorepo refactor) with the identical `assert len(w) == 0` shape. NOT introduced by this branch.

## Root cause (likely)

`warnings.catch_warnings(record=True)` is not thread-safe and is sensitive to GLOBAL warnings-filter state. When sibling tests in the same pytest session emit `DataFlowValidationWarning` via `@model(...)` decorations, they:

1. Mutate the global `warnings.filters` state.
2. Or directly emit warnings that propagate to the `catch_warnings` block of `test_validation_off_mode_no_checks` if both run on the same worker.

The flakiness is test-order-dependent: the test passes when scheduled first (clean warnings state) and fails when scheduled after the `Order/userName` warning-emitting tests.

## Disposition

**Defer to Shard 3 — invariant 12 added.** Shard 3's todo (`03-shard3-tail-cleanup-and-asyncio-mark-hygiene.md`) is the natural home for test-isolation hygiene work. The fix is `monkeypatch.setattr(warnings, "filters", warnings.filters.copy())` at fixture-teardown OR wrapping the test in `warnings.resetwarnings()` at setup.

**Not blocking merge of PR #1004**: the latest-per-check status is all SUCCESS. The push-trigger run is obsolete (PR-trigger run is the canonical CI state per GitHub's mergeability evaluation). Admin-merge per `rules/git.md` § Branch Protection + `rules/coc-sync-landing.md` § 3 is the correct disposition.

Per `rules/zero-tolerance.md` Rule 1a (Scanner-Surface Symmetry): the failure surfaces on push-trigger but not on PR-trigger; same commits, different scheduler outcome — making it a test-isolation flake, NOT a deterministic regression. Rule 1c (pre-existing requires SHA pre-dating session) is satisfied by `b553104c` on main.

## Add to Shard 3 invariants

Shard 3 already covers test-hygiene (asyncio-mark fix). Add invariant 12:

> "12. `test_validation_off_mode_no_checks` no longer flakes on test order. Fix: reset `warnings.filters` state in the test's setup OR use `@pytest.fixture(autouse=True)` to snapshot+restore `warnings.filters` per test. Verify via `pytest -p no:randomly --count=10 tests/unit/test_model_validation.py` — expect 10/10 pass."

This is in-scope for Shard 3 because it's a tier-1 test-hygiene fix, fits the existing ~150 LOC budget, and aligns with the asyncio-mark fix already on the shard.

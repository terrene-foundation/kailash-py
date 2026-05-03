# Sprint S10 Analysis — Trust-Plane Features + CI Green

**Date**: 2026-03-28
**Issues**: #145, #146, #147, #97 (partial), + CI stability
**Status**: Post v2.2.0 release

## Open Issues

| #       | Title                                           | Type     | Severity | Dependencies |
| ------- | ----------------------------------------------- | -------- | -------- | ------------ |
| **145** | BudgetTracker.reserve() accepts over-budget     | BUG      | HIGH     | None         |
| **147** | intersect_constraints missing                   | FEAT     | HIGH     | None         |
| **146** | ShadowEnforcer missing                          | FEAT     | MEDIUM   | #147         |
| **97**  | Cross-SDK naming (S3e remaining)                | REFACTOR | LOW      | Future       |
| **CI**  | Tier 1 still failing (thread/SQLite stragglers) | INFRA    | HIGH     | None         |

## CI Status

CI still has straggler files that create threads or runtimes in `tests/unit/`:

- `test_node_executor.py` — creates runtime
- `test_pause_controller.py::TestThreadSafety` — thread tests
- Possibly more lurking

**Root cause**: The testing specialist sweep missed files outside `tests/unit/runtime/`. Need one final comprehensive sweep across ALL of `tests/unit/`.

## Trust-Plane Analysis

### #145: BudgetTracker (BUG)

`reserve()` bounds check at line 379-380 appears correct: `available = allocated - committed - reserved; if available < microdollars: return False`. However:

- `record()` allows committed to exceed allocated (intentional overspend tracking)
- No per-reservation cap
- Missing clear exhaustion state in check results

**Fix**: Add `record()` overspend callback/warning + regression test. ~0.5 session.

### #147: Envelope Intersection (FEAT)

`intersect_envelopes(a, b)` already exists in `envelopes.py:314-351`. Missing:

1. `intersect_constraints([...])` — variadic reduce wrapper (trivial)
2. `is_tighter_than()` — standalone function wrapping `validate_tightening()` in try/except

**Fix**: ~0.5 session. Most logic already implemented.

### #146: PactShadowEnforcer (FEAT)

New module. EATP-level `ShadowEnforcer` exists in `enforce/shadow.py` but doesn't handle PACT envelopes. Need:

- `PactShadowEnforcer(production_env, candidate_env)`
- `evaluate(action)` → divergence result
- `DivergenceMetrics` tracking

**Fix**: ~1 session. New module, follows existing patterns. Depends on #147.

## Implementation Order

```
CI fix (final sweep) ──────────────────────┐
#145 (BudgetTracker) ──────────────────────┤
#147 (envelope intersection) ──────────────┤──> #146 (ShadowEnforcer)
                                           │
                                           └──> Cross-SDK issues
```

#145 and #147 are independent → parallel. CI fix is independent → parallel with all.

---
type: DECISION
date: 2026-04-25
created_at: 2026-04-25T10:10:04.114Z
author: agent
session_id: c8cb11ec-e2ab-40d5-95ce-947a896a84ec
project: kailash-ml-audit
topic: BudgetTracker threshold-breach callback API closes #603
phase: implement
tags: [trust, budget-tracker, callbacks, cross-sdk-parity, eatp-d6]
source_commit: 1b164d933f7f2aa36e2759808b11843af7a4b44c
---

# DECISION — feat(trust): add BudgetTracker threshold-breach callback API (#603)

## What

Public API additions on `kailash.trust.constraints.BudgetTracker`:

```python
set_threshold_callback(threshold_pct: float,
                       callback: Callable[[BudgetEvent], None]) -> int
unregister_threshold_callback(handle: int) -> bool
```

Fires a one-shot callback when `(committed + reserved) / allocated` first reaches `threshold_pct` after a successful `reserve()` or `record()`. Distinct from the existing `on_threshold()` (hardcoded 80/95/100% marks).

## Contract

- `threshold_pct` in (0.0, 1.0]; non-finite / out-of-range raise `BudgetTrackerError`
- Multiple callbacks per threshold preserved in registration order
- Each `(threshold, handle)` fires AT MOST ONCE per BudgetTracker
- State oscillation does NOT re-fire (one-shot is one-shot)
- Multiple distinct thresholds fire in ascending order on a single mutation
- Thread-safe under existing `self._lock`
- Callbacks dispatched outside the lock (no re-entrancy deadlock)
- Callback failure isolated: WARNING-logged, siblings still fire, exception NEVER propagates to `record()` / `reserve()` caller

## Why

Cross-SDK with kailash-rs#30. The hardcoded 80/95/100% marks suit baseline alerting but cannot express tenant-specific thresholds (a tenant on a small contract may want 50% / 75% notice). The callback API lets governance layer install per-tenant thresholds at runtime without recompiling.

Python permits multiple callbacks per threshold (Rust currently single-shot per tracker). The asymmetry is intentional: Python's GIL + lock-free dispatch makes multi-callback cheap; Rust's borrow-checker would force a `Vec<Box<dyn Fn>>` allocation that wasn't needed for the initial Rust use case. EATP D6 parity is at the SEMANTIC level (one-shot, threshold-pct, error-isolated), not the cardinality level.

## Tests

32 new tests pass; 79 existing budget tests still pass (111 total). Implementation across 3 wip commits + CHANGELOG fragment.

## For Discussion

1. The callback is dispatched OUTSIDE the lock. If a callback re-enters `BudgetTracker.reserve()` (e.g. to reserve a fallback dimension), it acquires the lock again — re-entrant lock acquisition is the documented behavior. Is this defensible, or should the rule be "callbacks MUST NOT mutate the tracker that fired them"? The current implementation permits it; the docs do not.
2. Counterfactual: if Python had stayed at single-shot-per-tracker for parity with Rust, would any actual user have been blocked? `grep BudgetTracker tests/` shows 4 production callsites; all 4 use exactly one threshold. The multi-callback capability is a 0-user feature today.
3. The Rust sibling (#30) is still single-callback. Should we file a kailash-rs follow-up to bring Rust to parity, or leave the cardinality-asymmetry documented and move on?

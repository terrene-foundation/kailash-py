# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
Tier 1 unit tests for BudgetTracker.set_threshold_callback (issue #603).

Covers:
- Happy path: single threshold, single callback, fires once on crossing
- Multiple callbacks at the same threshold preserve registration order
- Multiple distinct thresholds fire in ascending order on a single mutation
- Callback exception isolation: raise in one does not block siblings, does
  not propagate to record()/reserve()
- Once-only firing: state oscillation does not re-fire
- Threshold-pct edge cases: 0.0 rejected, negative rejected, > 1.0 rejected,
  NaN/Inf rejected, exactly 1.0 accepted, 0.999... near-boundary
- Reserve path also fires (not just record)
- Predicate uses committed + reserved (the "claimed" amount)
- Unregister removes from callback list; unregister-after-fire does not
  re-arm (re-registration with new handle gets fresh one-shot)
- BudgetEvent payload carries threshold_pct, committed/reserved/remaining
- Custom-threshold limit shares quota with on_threshold via _max_callbacks
- Allocated == 0 special case: no fires
"""

from __future__ import annotations

import math
import threading
from typing import List

import pytest

from kailash.trust.constraints.budget_tracker import (
    BudgetEvent,
    BudgetTracker,
    BudgetTrackerError,
)


# ---------------------------------------------------------------------------
# Helper: collect events into a list (callable, thread-safe)
# ---------------------------------------------------------------------------


class _Recorder:
    """Thread-safe append-only event recorder for tests."""

    def __init__(self) -> None:
        self.events: List[BudgetEvent] = []
        self._lock = threading.Lock()

    def __call__(self, event: BudgetEvent) -> None:
        with self._lock:
            self.events.append(event)


# ---------------------------------------------------------------------------
# 1. Happy path
# ---------------------------------------------------------------------------


class TestHappyPath:
    def test_callback_fires_once_when_threshold_crossed_via_record(self) -> None:
        tracker = BudgetTracker(allocated_microdollars=10_000_000)
        rec = _Recorder()
        handle = tracker.set_threshold_callback(0.80, rec)
        assert isinstance(handle, int) and handle > 0

        # 70% via record -- below threshold
        assert tracker.reserve(7_000_000) is True
        tracker.record(7_000_000, 7_000_000)
        assert len(rec.events) == 0

        # Push committed to 85% via additional record
        # (reserve 1.5M, then record actual 1.5M -> committed = 8.5M = 85%)
        assert tracker.reserve(1_500_000) is True
        # Reserve already brings claimed to 8.5M, fires.
        assert len(rec.events) == 1
        evt = rec.events[0]
        assert evt.event_type == "custom_threshold"
        assert evt.threshold_pct == pytest.approx(0.80)
        assert evt.allocated_microdollars == 10_000_000
        assert evt.committed_microdollars == 7_000_000
        assert evt.reserved_microdollars == 1_500_000

    def test_callback_fires_via_reserve_path(self) -> None:
        tracker = BudgetTracker(allocated_microdollars=1_000_000)
        rec = _Recorder()
        tracker.set_threshold_callback(0.50, rec)

        assert tracker.reserve(400_000) is True  # 40% -- no fire
        assert len(rec.events) == 0
        assert tracker.reserve(200_000) is True  # 60% -- fires
        assert len(rec.events) == 1

    def test_callback_returns_handle_unique_per_registration(self) -> None:
        tracker = BudgetTracker(allocated_microdollars=1_000_000)
        h1 = tracker.set_threshold_callback(0.5, lambda e: None)
        h2 = tracker.set_threshold_callback(0.5, lambda e: None)
        h3 = tracker.set_threshold_callback(0.7, lambda e: None)
        assert len({h1, h2, h3}) == 3


# ---------------------------------------------------------------------------
# 2. Multiple callbacks per threshold
# ---------------------------------------------------------------------------


class TestMultipleCallbacks:
    def test_registration_order_preserved_within_same_threshold(self) -> None:
        tracker = BudgetTracker(allocated_microdollars=1_000_000)
        order: List[str] = []

        def make_cb(name: str):
            def cb(_evt: BudgetEvent) -> None:
                order.append(name)

            return cb

        tracker.set_threshold_callback(0.50, make_cb("first"))
        tracker.set_threshold_callback(0.50, make_cb("second"))
        tracker.set_threshold_callback(0.50, make_cb("third"))

        assert tracker.reserve(600_000) is True  # 60% -- fires all
        assert order == ["first", "second", "third"]

    def test_multiple_thresholds_fire_in_ascending_order(self) -> None:
        tracker = BudgetTracker(allocated_microdollars=1_000_000)
        order: List[float] = []

        def cb_for(pct: float):
            def cb(evt: BudgetEvent) -> None:
                assert evt.threshold_pct == pytest.approx(pct)
                order.append(pct)

            return cb

        # Register in non-sorted order; firing order must be ascending.
        tracker.set_threshold_callback(0.90, cb_for(0.90))
        tracker.set_threshold_callback(0.50, cb_for(0.50))
        tracker.set_threshold_callback(0.75, cb_for(0.75))

        # One mutation crosses all three at once
        assert tracker.reserve(950_000) is True
        assert order == [0.50, 0.75, 0.90]


# ---------------------------------------------------------------------------
# 3. Once-only firing
# ---------------------------------------------------------------------------


class TestOnceOnly:
    def test_sustained_above_threshold_does_not_re_fire(self) -> None:
        tracker = BudgetTracker(allocated_microdollars=1_000_000)
        rec = _Recorder()
        tracker.set_threshold_callback(0.50, rec)

        assert tracker.reserve(600_000) is True  # 60% -- fires once
        assert len(rec.events) == 1

        # Subsequent mutations still above threshold -- no re-fire
        assert tracker.reserve(100_000) is True  # 70%
        tracker.record(100_000, 100_000)  # commit 100k
        assert tracker.reserve(50_000) is True  # 75%
        assert len(rec.events) == 1

    def test_oscillation_below_and_back_does_not_re_fire(self) -> None:
        tracker = BudgetTracker(allocated_microdollars=1_000_000)
        rec = _Recorder()
        tracker.set_threshold_callback(0.50, rec)

        # Cross via reserve
        assert tracker.reserve(600_000) is True
        assert len(rec.events) == 1

        # Drop below: record actual 0 releases the reservation entirely
        tracker.record(600_000, 0)
        # claimed = 0+0; well below 50%. No re-fire (one-shot is one-shot).
        assert len(rec.events) == 1

        # Cross again -- must NOT re-fire
        assert tracker.reserve(700_000) is True
        assert len(rec.events) == 1


# ---------------------------------------------------------------------------
# 4. Failure isolation
# ---------------------------------------------------------------------------


class TestFailureIsolation:
    def test_callback_exception_does_not_propagate_via_reserve(self) -> None:
        tracker = BudgetTracker(allocated_microdollars=1_000_000)

        def bomb(_evt: BudgetEvent) -> None:
            raise RuntimeError("boom")

        tracker.set_threshold_callback(0.50, bomb)

        # Reserve must succeed despite callback raising.
        assert tracker.reserve(700_000) is True
        # Bookkeeping unaffected
        assert tracker.remaining_microdollars() == 300_000

    def test_callback_exception_does_not_propagate_via_record(self) -> None:
        tracker = BudgetTracker(allocated_microdollars=1_000_000)

        def bomb(_evt: BudgetEvent) -> None:
            raise ValueError("fail")

        tracker.set_threshold_callback(0.50, bomb)

        assert tracker.reserve(400_000) is True  # 40% -- no fire
        # Record an overage that pushes committed to 700k -> 70% -- fires
        tracker.record(400_000, 700_000)
        # No exception propagated; record() returned normally.
        # Bookkeeping reflects the record.
        assert tracker.remaining_microdollars() == 1_000_000 - 700_000

    def test_first_callback_raises_second_still_fires(self) -> None:
        tracker = BudgetTracker(allocated_microdollars=1_000_000)
        order: List[str] = []

        def bomb(_evt: BudgetEvent) -> None:
            order.append("bomb")
            raise RuntimeError("first cb crash")

        def survivor(_evt: BudgetEvent) -> None:
            order.append("survivor")

        tracker.set_threshold_callback(0.50, bomb)
        tracker.set_threshold_callback(0.50, survivor)

        assert tracker.reserve(700_000) is True
        # Both callbacks ran; bomb first (registration order), survivor second.
        assert order == ["bomb", "survivor"]


# ---------------------------------------------------------------------------
# 5. Threshold-pct validation
# ---------------------------------------------------------------------------


class TestThresholdValidation:
    def test_zero_threshold_rejected(self) -> None:
        tracker = BudgetTracker(allocated_microdollars=1_000_000)
        with pytest.raises(BudgetTrackerError):
            tracker.set_threshold_callback(0.0, lambda e: None)

    def test_negative_threshold_rejected(self) -> None:
        tracker = BudgetTracker(allocated_microdollars=1_000_000)
        with pytest.raises(BudgetTrackerError):
            tracker.set_threshold_callback(-0.1, lambda e: None)

    def test_above_one_threshold_rejected(self) -> None:
        tracker = BudgetTracker(allocated_microdollars=1_000_000)
        with pytest.raises(BudgetTrackerError):
            tracker.set_threshold_callback(1.1, lambda e: None)

    def test_nan_threshold_rejected(self) -> None:
        tracker = BudgetTracker(allocated_microdollars=1_000_000)
        with pytest.raises(BudgetTrackerError):
            tracker.set_threshold_callback(math.nan, lambda e: None)

    def test_inf_threshold_rejected(self) -> None:
        tracker = BudgetTracker(allocated_microdollars=1_000_000)
        with pytest.raises(BudgetTrackerError):
            tracker.set_threshold_callback(math.inf, lambda e: None)
        with pytest.raises(BudgetTrackerError):
            tracker.set_threshold_callback(-math.inf, lambda e: None)

    def test_exactly_one_accepted_and_fires_at_full_claim(self) -> None:
        tracker = BudgetTracker(allocated_microdollars=1_000_000)
        rec = _Recorder()
        tracker.set_threshold_callback(1.0, rec)

        assert tracker.reserve(999_999) is True  # 99.9999% -- below 100%
        assert len(rec.events) == 0
        assert tracker.reserve(1) is True  # exactly 100% -- fires
        assert len(rec.events) == 1
        assert rec.events[0].threshold_pct == pytest.approx(1.0)

    def test_threshold_just_above_999_nines_fires_at_exact_match(self) -> None:
        # threshold 0.999_999 against budget 1_000_000 fires at claimed 999_999
        # because 999_999 / 1_000_000 = 0.999_999 >= 0.999_999.
        tracker = BudgetTracker(allocated_microdollars=1_000_000)
        rec = _Recorder()
        tracker.set_threshold_callback(0.999_999, rec)

        assert tracker.reserve(999_998) is True  # 99.9998% -- below
        assert len(rec.events) == 0
        assert tracker.reserve(1) is True  # 99.9999% -- fires
        assert len(rec.events) == 1

    def test_callback_must_be_callable(self) -> None:
        tracker = BudgetTracker(allocated_microdollars=1_000_000)
        with pytest.raises(BudgetTrackerError):
            tracker.set_threshold_callback(0.5, "not_callable")  # type: ignore[arg-type]

    def test_threshold_must_be_number(self) -> None:
        tracker = BudgetTracker(allocated_microdollars=1_000_000)
        with pytest.raises(BudgetTrackerError):
            tracker.set_threshold_callback("0.5", lambda e: None)  # type: ignore[arg-type]
        with pytest.raises(BudgetTrackerError):
            # bool is a subclass of int in Python; explicitly reject it
            # because True/False as threshold is a programming error.
            tracker.set_threshold_callback(True, lambda e: None)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# 6. Predicate uses committed + reserved
# ---------------------------------------------------------------------------


class TestPredicateClaimedAmount:
    def test_predicate_includes_in_flight_reservations(self) -> None:
        tracker = BudgetTracker(allocated_microdollars=1_000_000)
        rec = _Recorder()
        tracker.set_threshold_callback(0.50, rec)

        # Reserve 600k WITHOUT recording: claimed = 600k = 60%, must fire.
        assert tracker.reserve(600_000) is True
        assert len(rec.events) == 1

    def test_predicate_uses_record_path_overage(self) -> None:
        tracker = BudgetTracker(allocated_microdollars=1_000_000)
        rec = _Recorder()
        tracker.set_threshold_callback(0.80, rec)

        assert tracker.reserve(100_000) is True  # 10%
        assert len(rec.events) == 0
        # Record overage: committed jumps to 850k -> 85%
        tracker.record(100_000, 850_000)
        assert len(rec.events) == 1


# ---------------------------------------------------------------------------
# 7. Unregister
# ---------------------------------------------------------------------------


class TestUnregister:
    def test_unregister_before_fire_prevents_callback(self) -> None:
        tracker = BudgetTracker(allocated_microdollars=1_000_000)
        rec = _Recorder()
        handle = tracker.set_threshold_callback(0.50, rec)
        assert tracker.unregister_threshold_callback(handle) is True

        assert tracker.reserve(700_000) is True
        assert len(rec.events) == 0  # unregistered -- never fires

    def test_unregister_unknown_handle_returns_false(self) -> None:
        tracker = BudgetTracker(allocated_microdollars=1_000_000)
        assert tracker.unregister_threshold_callback(99999) is False

    def test_unregister_one_callback_leaves_siblings_intact(self) -> None:
        tracker = BudgetTracker(allocated_microdollars=1_000_000)
        rec1 = _Recorder()
        rec2 = _Recorder()
        h1 = tracker.set_threshold_callback(0.50, rec1)
        _h2 = tracker.set_threshold_callback(0.50, rec2)

        assert tracker.unregister_threshold_callback(h1) is True

        assert tracker.reserve(700_000) is True
        assert len(rec1.events) == 0
        assert len(rec2.events) == 1

    def test_unregister_after_fire_does_not_re_arm_at_same_handle(self) -> None:
        tracker = BudgetTracker(allocated_microdollars=1_000_000)
        rec = _Recorder()
        handle = tracker.set_threshold_callback(0.50, rec)

        # Cross threshold and fire
        assert tracker.reserve(700_000) is True
        assert len(rec.events) == 1

        # Unregister AFTER fire
        assert tracker.unregister_threshold_callback(handle) is True
        # Re-register at SAME threshold -- this gets a NEW handle and
        # therefore a fresh one-shot opportunity. Since predicate is still
        # true, the next reserve/record will fire it on the very next call.
        rec2 = _Recorder()
        new_handle = tracker.set_threshold_callback(0.50, rec2)
        assert new_handle != handle
        # Trigger any reserve to force predicate evaluation.
        assert tracker.reserve(50_000) is True
        # rec2 fires because the new handle has not yet fired.
        assert len(rec2.events) == 1


# ---------------------------------------------------------------------------
# 8. Allocated zero edge case
# ---------------------------------------------------------------------------


class TestAllocatedZero:
    def test_allocated_zero_never_fires(self) -> None:
        tracker = BudgetTracker(allocated_microdollars=0)
        rec = _Recorder()
        tracker.set_threshold_callback(0.50, rec)

        # Zero-amount reserve always succeeds; cannot reserve > 0.
        assert tracker.reserve(0) is True
        # No mutation happened, no fire.
        assert len(rec.events) == 0


# ---------------------------------------------------------------------------
# 9. Limit
# ---------------------------------------------------------------------------


class TestLimit:
    def test_max_callback_limit_enforced(self) -> None:
        tracker = BudgetTracker(allocated_microdollars=1_000_000)
        # Default max is 100; register 100 callbacks at varying thresholds.
        for i in range(100):
            # Use distinct thresholds so each fires at a distinct point;
            # the limit applies to the union across all thresholds.
            tracker.set_threshold_callback(0.001 * (i + 1), lambda e: None)

        with pytest.raises(BudgetTrackerError):
            tracker.set_threshold_callback(0.5, lambda e: None)

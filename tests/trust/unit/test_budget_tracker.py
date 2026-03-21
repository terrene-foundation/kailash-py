# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
Comprehensive unit tests for BudgetTracker primitive.

Tests cover:
- Basic reserve and record operations
- Budget exhaustion and fail-closed behavior
- Concurrent thread safety (20+ threads)
- Snapshot roundtrip serialization
- Saturating arithmetic (no negative remaining)
- Bounded transaction log (maxlen=10000)
- USD conversion helpers
- Non-mutating check()
- to_dict / from_dict serialization for all dataclasses
- Threshold callback firing (80%, 95%, exhausted)
- from_snapshot loses reservations
"""

from __future__ import annotations

import math
import threading
import time as time_mod
from datetime import datetime, timezone
from typing import Any, Dict, List

import pytest

from kailash.trust.constraints.budget_tracker import (
    BudgetCheckResult,
    BudgetEvent,
    BudgetSnapshot,
    BudgetTracker,
    BudgetTrackerError,
    microdollars_to_usd,
    usd_to_microdollars,
)
from kailash.trust.exceptions import TrustError


# ---------------------------------------------------------------------------
# 1. test_basic_reserve_and_record
# ---------------------------------------------------------------------------
class TestBasicReserveAndRecord:
    """Reserve 50M microdollars, record actual 48M, check remaining."""

    def test_reserve_then_record(self) -> None:
        tracker = BudgetTracker(allocated_microdollars=100_000_000)

        # Reserve 50M
        ok = tracker.reserve(50_000_000)
        assert ok is True

        # Remaining should reflect reservation
        remaining = tracker.remaining_microdollars()
        assert remaining == 50_000_000  # 100M - 0 committed - 50M reserved

        # Record: we reserved 50M but only used 48M
        tracker.record(reserved_microdollars=50_000_000, actual_microdollars=48_000_000)

        # After record: committed=48M, reserved=0
        remaining = tracker.remaining_microdollars()
        assert remaining == 52_000_000  # 100M - 48M committed - 0 reserved

    def test_multiple_reserves_then_records(self) -> None:
        tracker = BudgetTracker(allocated_microdollars=100_000_000)

        # Reserve twice
        assert tracker.reserve(30_000_000) is True
        assert tracker.reserve(20_000_000) is True

        # Remaining: 100M - 0 committed - 50M reserved = 50M
        assert tracker.remaining_microdollars() == 50_000_000

        # Record first
        tracker.record(reserved_microdollars=30_000_000, actual_microdollars=25_000_000)
        # Now: committed=25M, reserved=20M, remaining=55M
        assert tracker.remaining_microdollars() == 55_000_000

        # Record second
        tracker.record(reserved_microdollars=20_000_000, actual_microdollars=20_000_000)
        # Now: committed=45M, reserved=0, remaining=55M
        assert tracker.remaining_microdollars() == 55_000_000


# ---------------------------------------------------------------------------
# 2. test_reserve_returns_false_when_exhausted
# ---------------------------------------------------------------------------
class TestReserveExhausted:
    """Allocate 100M, reserve 100M, second reserve returns False."""

    def test_exact_exhaustion(self) -> None:
        tracker = BudgetTracker(allocated_microdollars=100_000_000)

        # First reserve takes all
        assert tracker.reserve(100_000_000) is True

        # Second reserve must fail
        assert tracker.reserve(1) is False

    def test_partial_exhaustion(self) -> None:
        tracker = BudgetTracker(allocated_microdollars=100_000_000)
        assert tracker.reserve(60_000_000) is True
        assert tracker.reserve(40_000_000) is True
        assert tracker.reserve(1) is False

    def test_zero_budget_always_fails(self) -> None:
        tracker = BudgetTracker(allocated_microdollars=0)
        assert tracker.reserve(1) is False

    def test_zero_reserve_succeeds(self) -> None:
        tracker = BudgetTracker(allocated_microdollars=100_000_000)
        assert tracker.reserve(0) is True


# ---------------------------------------------------------------------------
# 3. test_record_adjusts_reserved_vs_actual
# ---------------------------------------------------------------------------
class TestRecordAdjustment:
    """Reserve 50M, record 30M actual, verify committed=30M, reserved=0."""

    def test_record_with_less_actual(self) -> None:
        tracker = BudgetTracker(allocated_microdollars=100_000_000)
        assert tracker.reserve(50_000_000) is True

        tracker.record(reserved_microdollars=50_000_000, actual_microdollars=30_000_000)

        snap = tracker.snapshot()
        assert snap.committed == 30_000_000
        assert snap.allocated == 100_000_000

        # Remaining: 100M - 30M committed - 0 reserved = 70M
        assert tracker.remaining_microdollars() == 70_000_000

    def test_record_with_more_actual_than_reserved(self) -> None:
        """Actual cost exceeded reservation -- committed still tracks actual."""
        tracker = BudgetTracker(allocated_microdollars=100_000_000)
        assert tracker.reserve(30_000_000) is True

        tracker.record(reserved_microdollars=30_000_000, actual_microdollars=50_000_000)

        snap = tracker.snapshot()
        assert snap.committed == 50_000_000
        assert tracker.remaining_microdollars() == 50_000_000


# ---------------------------------------------------------------------------
# 4. test_concurrent_reserve_20_threads
# ---------------------------------------------------------------------------
class TestConcurrent20Threads:
    """20 threads each try to reserve 100K from 1M budget. Exactly 10 succeed."""

    def test_exactly_10_succeed(self) -> None:
        budget = 1_000_000  # 1M microdollars
        reserve_amount = 100_000  # 100K each
        n_threads = 20
        # Expected: budget / reserve_amount = 10 successes

        tracker = BudgetTracker(allocated_microdollars=budget)
        successes: List[bool] = []
        lock = threading.Lock()

        def worker() -> None:
            result = tracker.reserve(reserve_amount)
            with lock:
                successes.append(result)

        threads = [threading.Thread(target=worker) for _ in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(successes) == n_threads
        assert sum(1 for s in successes if s) == 10
        assert sum(1 for s in successes if not s) == 10

        # Zero remaining after successful reservations
        assert tracker.remaining_microdollars() == 0


# ---------------------------------------------------------------------------
# 5. test_concurrent_reserve_stress
# ---------------------------------------------------------------------------
class TestConcurrentStress:
    """50 threads, random amounts, verify remaining never negative."""

    def test_no_negative_remaining(self) -> None:
        import random

        budget = 10_000_000  # 10M
        tracker = BudgetTracker(allocated_microdollars=budget)
        errors: List[str] = []
        lock = threading.Lock()

        def worker(thread_id: int) -> None:
            rng = random.Random(thread_id)
            for _ in range(100):
                amount = rng.randint(1, 500_000)
                tracker.reserve(amount)
                remaining = tracker.remaining_microdollars()
                if remaining < 0:
                    with lock:
                        errors.append(
                            f"Thread {thread_id}: negative remaining {remaining}"
                        )

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(50)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"Found negative remaining: {errors}"
        assert tracker.remaining_microdollars() >= 0


# ---------------------------------------------------------------------------
# 6. test_snapshot_roundtrip
# ---------------------------------------------------------------------------
class TestSnapshotRoundtrip:
    """Snapshot preserves allocated + committed, loses reservations."""

    def test_roundtrip_preserves_state(self) -> None:
        tracker = BudgetTracker(allocated_microdollars=100_000_000)
        tracker.reserve(30_000_000)
        tracker.record(reserved_microdollars=30_000_000, actual_microdollars=25_000_000)

        snap = tracker.snapshot()
        assert snap.allocated == 100_000_000
        assert snap.committed == 25_000_000

        # Roundtrip through dict
        d = snap.to_dict()
        snap2 = BudgetSnapshot.from_dict(d)
        assert snap2.allocated == snap.allocated
        assert snap2.committed == snap.committed

    def test_snapshot_dict_keys(self) -> None:
        snap = BudgetSnapshot(allocated=100, committed=50)
        d = snap.to_dict()
        assert "allocated" in d
        assert "committed" in d
        assert d["allocated"] == 100
        assert d["committed"] == 50


# ---------------------------------------------------------------------------
# 7. test_saturating_arithmetic
# ---------------------------------------------------------------------------
class TestSaturatingArithmetic:
    """Record more than reserved, remaining never negative."""

    def test_committed_exceeds_allocated(self) -> None:
        """Edge case: if committed somehow exceeds allocated, remaining=0."""
        tracker = BudgetTracker(allocated_microdollars=100)
        tracker.reserve(100)
        # Record actual that exceeds allocation
        tracker.record(reserved_microdollars=100, actual_microdollars=200)

        # Remaining must be 0, NOT negative
        assert tracker.remaining_microdollars() == 0

    def test_reserved_exceeds_what_was_set(self) -> None:
        """Record reserved_microdollars greater than internal _reserved -- saturates to 0."""
        tracker = BudgetTracker(allocated_microdollars=100_000)
        tracker.reserve(50_000)
        # Record reserved amount larger than what was actually reserved
        tracker.record(reserved_microdollars=80_000, actual_microdollars=50_000)
        # _reserved should not go negative -- saturates to 0
        assert (
            tracker.remaining_microdollars() == 50_000
        )  # 100K - 50K committed - 0 reserved


# ---------------------------------------------------------------------------
# 8. test_fail_closed_on_negative_input
# ---------------------------------------------------------------------------
class TestFailClosedNegativeInput:
    """reserve(-1) returns False. Negative inputs are denied."""

    def test_negative_reserve(self) -> None:
        tracker = BudgetTracker(allocated_microdollars=100_000_000)
        assert tracker.reserve(-1) is False

    def test_negative_allocation_raises(self) -> None:
        with pytest.raises(BudgetTrackerError) as exc_info:
            BudgetTracker(allocated_microdollars=-1)
        assert (
            "non-negative" in str(exc_info.value).lower()
            or "negative" in str(exc_info.value).lower()
        )

    def test_non_finite_allocation_raises(self) -> None:
        """NaN and Inf are rejected at construction."""
        with pytest.raises((BudgetTrackerError, TypeError, ValueError)):
            BudgetTracker(allocated_microdollars=float("inf"))  # type: ignore[arg-type]

    def test_error_inherits_from_trust_error(self) -> None:
        """BudgetTrackerError must inherit from TrustError."""
        assert issubclass(BudgetTrackerError, TrustError)

    def test_error_has_details(self) -> None:
        """BudgetTrackerError must have a .details dict."""
        err = BudgetTrackerError("test error", details={"key": "value"})
        assert err.details == {"key": "value"}


# ---------------------------------------------------------------------------
# 9. test_bounded_transaction_log
# ---------------------------------------------------------------------------
class TestBoundedTransactionLog:
    """Verify maxlen=10000 on the transaction log."""

    def test_log_does_not_exceed_maxlen(self) -> None:
        tracker = BudgetTracker(
            allocated_microdollars=100_000_000_000
        )  # Very large budget

        # Perform 12000 reserve operations
        for i in range(12_000):
            tracker.reserve(1)

        # Transaction log should be bounded at 10000
        assert len(tracker._transaction_log) <= 10_000

    def test_oldest_entries_evicted(self) -> None:
        tracker = BudgetTracker(allocated_microdollars=100_000_000_000)

        for i in range(10_050):
            tracker.reserve(1)

        # Log should be exactly 10000 (deque maxlen)
        assert len(tracker._transaction_log) == 10_000


# ---------------------------------------------------------------------------
# 10. test_usd_conversion
# ---------------------------------------------------------------------------
class TestUsdConversion:
    """usd_to_microdollars(1.50) == 1_500_000."""

    def test_usd_to_microdollars_basic(self) -> None:
        assert usd_to_microdollars(1.50) == 1_500_000

    def test_usd_to_microdollars_whole(self) -> None:
        assert usd_to_microdollars(1.0) == 1_000_000

    def test_usd_to_microdollars_zero(self) -> None:
        assert usd_to_microdollars(0.0) == 0

    def test_microdollars_to_usd_basic(self) -> None:
        assert microdollars_to_usd(1_500_000) == 1.5

    def test_microdollars_to_usd_zero(self) -> None:
        assert microdollars_to_usd(0) == 0.0

    def test_roundtrip(self) -> None:
        """usd -> microdollars -> usd is lossless for common values."""
        for amount in [0.0, 0.01, 1.0, 1.50, 100.00, 999.99]:
            micro = usd_to_microdollars(amount)
            back = microdollars_to_usd(micro)
            assert (
                abs(back - amount) < 1e-6
            ), f"Roundtrip failed for {amount}: got {back}"


# ---------------------------------------------------------------------------
# 11. test_check_is_nonmutating
# ---------------------------------------------------------------------------
class TestCheckNonMutating:
    """check() doesn't change state."""

    def test_check_does_not_alter_state(self) -> None:
        tracker = BudgetTracker(allocated_microdollars=100_000_000)
        tracker.reserve(30_000_000)

        snap_before = tracker.snapshot()
        remaining_before = tracker.remaining_microdollars()

        # Call check multiple times
        result1 = tracker.check(estimated_microdollars=10_000_000)
        result2 = tracker.check(estimated_microdollars=50_000_000)
        result3 = tracker.check(estimated_microdollars=200_000_000)

        snap_after = tracker.snapshot()
        remaining_after = tracker.remaining_microdollars()

        assert snap_before.allocated == snap_after.allocated
        assert snap_before.committed == snap_after.committed
        assert remaining_before == remaining_after

    def test_check_returns_correct_result(self) -> None:
        tracker = BudgetTracker(allocated_microdollars=100_000_000)
        tracker.reserve(30_000_000)

        # Check for something within remaining (70M available but 30M reserved, so 70M remaining)
        result = tracker.check(estimated_microdollars=50_000_000)
        assert result.allowed is True
        assert result.allocated_microdollars == 100_000_000
        assert result.committed_microdollars == 0
        assert result.reserved_microdollars == 30_000_000
        assert result.remaining_microdollars == 70_000_000

    def test_check_returns_false_when_would_exceed(self) -> None:
        tracker = BudgetTracker(allocated_microdollars=100_000_000)
        tracker.reserve(80_000_000)

        # Only 20M remaining, trying 30M
        result = tracker.check(estimated_microdollars=30_000_000)
        assert result.allowed is False


# ---------------------------------------------------------------------------
# 12. test_to_dict_from_dict
# ---------------------------------------------------------------------------
class TestSerialization:
    """BudgetSnapshot, BudgetCheckResult serialization."""

    def test_budget_snapshot_to_dict(self) -> None:
        snap = BudgetSnapshot(allocated=100_000_000, committed=50_000_000)
        d = snap.to_dict()
        assert d == {"allocated": 100_000_000, "committed": 50_000_000}

    def test_budget_snapshot_from_dict(self) -> None:
        d = {"allocated": 100_000_000, "committed": 50_000_000}
        snap = BudgetSnapshot.from_dict(d)
        assert snap.allocated == 100_000_000
        assert snap.committed == 50_000_000

    def test_budget_snapshot_negative_raises(self) -> None:
        with pytest.raises((ValueError, BudgetTrackerError)):
            BudgetSnapshot(allocated=-1, committed=0)

    def test_budget_snapshot_negative_committed_raises(self) -> None:
        with pytest.raises((ValueError, BudgetTrackerError)):
            BudgetSnapshot(allocated=100, committed=-1)

    def test_budget_check_result_to_dict(self) -> None:
        result = BudgetCheckResult(
            allowed=True,
            remaining_microdollars=50_000_000,
            allocated_microdollars=100_000_000,
            committed_microdollars=30_000_000,
            reserved_microdollars=20_000_000,
        )
        d = result.to_dict()
        assert d["allowed"] is True
        assert d["remaining_microdollars"] == 50_000_000
        assert d["allocated_microdollars"] == 100_000_000
        assert d["committed_microdollars"] == 30_000_000
        assert d["reserved_microdollars"] == 20_000_000

    def test_budget_check_result_from_dict(self) -> None:
        d = {
            "allowed": False,
            "remaining_microdollars": 0,
            "allocated_microdollars": 100,
            "committed_microdollars": 100,
            "reserved_microdollars": 0,
        }
        result = BudgetCheckResult.from_dict(d)
        assert result.allowed is False
        assert result.remaining_microdollars == 0

    def test_budget_event_to_dict(self) -> None:
        ts = datetime(2026, 3, 18, 12, 0, 0, tzinfo=timezone.utc)
        event = BudgetEvent(
            event_type="exhausted",
            remaining_microdollars=0,
            allocated_microdollars=100_000_000,
            timestamp=ts,
        )
        d = event.to_dict()
        assert d["event_type"] == "exhausted"
        assert d["remaining_microdollars"] == 0
        assert d["allocated_microdollars"] == 100_000_000
        assert d["timestamp"] == ts.isoformat()

    def test_budget_event_from_dict(self) -> None:
        ts = datetime(2026, 3, 18, 12, 0, 0, tzinfo=timezone.utc)
        d = {
            "event_type": "threshold_80",
            "remaining_microdollars": 20_000_000,
            "allocated_microdollars": 100_000_000,
            "timestamp": ts.isoformat(),
        }
        event = BudgetEvent.from_dict(d)
        assert event.event_type == "threshold_80"
        assert event.remaining_microdollars == 20_000_000
        assert event.timestamp == ts


# ---------------------------------------------------------------------------
# 13. test_threshold_callbacks
# ---------------------------------------------------------------------------
class TestThresholdCallbacks:
    """Register callback, exhaust budget, verify 'exhausted' event fired."""

    def test_exhausted_event_fires(self) -> None:
        tracker = BudgetTracker(allocated_microdollars=100_000_000)
        events_received: List[BudgetEvent] = []

        tracker.on_threshold(lambda event: events_received.append(event))

        # Reserve and record full budget
        tracker.reserve(100_000_000)
        tracker.record(
            reserved_microdollars=100_000_000, actual_microdollars=100_000_000
        )

        # Should have received an "exhausted" event
        exhausted_events = [e for e in events_received if e.event_type == "exhausted"]
        assert len(exhausted_events) >= 1
        assert exhausted_events[0].remaining_microdollars == 0

    def test_multiple_callbacks(self) -> None:
        tracker = BudgetTracker(allocated_microdollars=100_000_000)
        events_a: List[BudgetEvent] = []
        events_b: List[BudgetEvent] = []

        tracker.on_threshold(lambda e: events_a.append(e))
        tracker.on_threshold(lambda e: events_b.append(e))

        tracker.reserve(100_000_000)
        tracker.record(
            reserved_microdollars=100_000_000, actual_microdollars=100_000_000
        )

        # Both callbacks should have received events
        assert len(events_a) >= 1
        assert len(events_b) >= 1

    def test_callback_exception_does_not_break_tracker(self) -> None:
        """A failing callback must not break the tracker's operation."""
        tracker = BudgetTracker(allocated_microdollars=100_000_000)
        good_events: List[BudgetEvent] = []

        def bad_callback(event: BudgetEvent) -> None:
            raise RuntimeError("callback exploded")

        tracker.on_threshold(bad_callback)
        tracker.on_threshold(lambda e: good_events.append(e))

        # Should not raise even though first callback fails
        tracker.reserve(100_000_000)
        tracker.record(
            reserved_microdollars=100_000_000, actual_microdollars=100_000_000
        )

        # Good callback still received events
        assert len(good_events) >= 1


# ---------------------------------------------------------------------------
# 14. test_threshold_80_percent
# ---------------------------------------------------------------------------
class TestThreshold80Percent:
    """Committed reaches 80%, 'threshold_80' event fires."""

    def test_80_percent_event(self) -> None:
        tracker = BudgetTracker(allocated_microdollars=100_000_000)
        events_received: List[BudgetEvent] = []

        tracker.on_threshold(lambda event: events_received.append(event))

        # Record exactly 80M out of 100M
        tracker.reserve(80_000_000)
        tracker.record(reserved_microdollars=80_000_000, actual_microdollars=80_000_000)

        threshold_80_events = [
            e for e in events_received if e.event_type == "threshold_80"
        ]
        assert len(threshold_80_events) >= 1

    def test_95_percent_event(self) -> None:
        tracker = BudgetTracker(allocated_microdollars=100_000_000)
        events_received: List[BudgetEvent] = []

        tracker.on_threshold(lambda event: events_received.append(event))

        # Record 95M out of 100M
        tracker.reserve(95_000_000)
        tracker.record(reserved_microdollars=95_000_000, actual_microdollars=95_000_000)

        threshold_95_events = [
            e for e in events_received if e.event_type == "threshold_95"
        ]
        assert len(threshold_95_events) >= 1

    def test_below_80_percent_no_event(self) -> None:
        tracker = BudgetTracker(allocated_microdollars=100_000_000)
        events_received: List[BudgetEvent] = []

        tracker.on_threshold(lambda event: events_received.append(event))

        # Record 70M out of 100M (70% -- below threshold)
        tracker.reserve(70_000_000)
        tracker.record(reserved_microdollars=70_000_000, actual_microdollars=70_000_000)

        assert len(events_received) == 0


# ---------------------------------------------------------------------------
# 15. test_from_snapshot_loses_reservations
# ---------------------------------------------------------------------------
class TestFromSnapshotLosesReservations:
    """Snapshot after reserve, restore, verify reservations gone."""

    def test_reservations_lost_on_restore(self) -> None:
        tracker = BudgetTracker(allocated_microdollars=100_000_000)
        tracker.reserve(30_000_000)
        tracker.record(reserved_microdollars=30_000_000, actual_microdollars=20_000_000)
        tracker.reserve(40_000_000)

        # At this point: committed=20M, reserved=40M, remaining=40M
        assert tracker.remaining_microdollars() == 40_000_000

        snap = tracker.snapshot()
        # Snapshot only stores allocated + committed
        assert snap.allocated == 100_000_000
        assert snap.committed == 20_000_000

        # Restore from snapshot
        restored = BudgetTracker.from_snapshot(snap)

        # Restored tracker has no reservations
        assert (
            restored.remaining_microdollars() == 80_000_000
        )  # 100M - 20M committed - 0 reserved

        # Can reserve the full remaining amount
        assert restored.reserve(80_000_000) is True
        assert restored.remaining_microdollars() == 0

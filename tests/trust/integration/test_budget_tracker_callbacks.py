# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
Tier 2 integration tests for BudgetTracker.set_threshold_callback (issue #603).

These tests exercise the threshold-callback API under realistic concurrent
load using real Python ``threading`` primitives (NO mocks per
``rules/testing.md``). The goal is to prove that:

1. Under contention, a custom-threshold callback fires EXACTLY ONCE for a
   given (threshold, handle) -- the lock + fired-handle set must
   serialize the rising-edge correctly.
2. Concurrent reserve()/record() workers cannot starve threshold dispatch.
3. Callback exceptions raised from worker threads do not corrupt budget
   accounting or block siblings.
4. The full reserve -> record cycle preserves the once-only guarantee
   even when the predicate transitions true -> false -> true.
"""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor, wait
from typing import List

import pytest

from kailash.trust.constraints.budget_tracker import (
    BudgetEvent,
    BudgetTracker,
)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


class _Recorder:
    """Thread-safe append-only event recorder."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.events: List[BudgetEvent] = []

    def __call__(self, event: BudgetEvent) -> None:
        with self._lock:
            self.events.append(event)


# ---------------------------------------------------------------------------
# Concurrent contention
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestConcurrentThresholdFiring:
    def test_concurrent_reserves_fire_callback_exactly_once(self) -> None:
        """16 threads racing across the 80% threshold; one fire only."""
        # Budget = 16M; each thread reserves 1M. The 13th successful reserve
        # is the first to push claimed >= 12.8M (80% of 16M).
        tracker = BudgetTracker(allocated_microdollars=16_000_000)
        rec = _Recorder()
        tracker.set_threshold_callback(0.80, rec)

        barrier = threading.Barrier(16)

        def worker() -> bool:
            barrier.wait()
            return tracker.reserve(1_000_000)

        with ThreadPoolExecutor(max_workers=16) as pool:
            futs = [pool.submit(worker) for _ in range(16)]
            wait(futs)
            successes = sum(1 for f in futs if f.result() is True)

        # All 16 reservations of 1M each fit in 16M budget.
        assert successes == 16
        assert tracker.remaining_microdollars() == 0
        # Critical invariant: exactly one fire under contention.
        assert (
            len(rec.events) == 1
        ), f"expected single fire, got {len(rec.events)} events"

    def test_concurrent_reserve_record_oscillation_one_fire(self) -> None:
        """50 threads run reserve+record cycles; threshold fires once."""
        tracker = BudgetTracker(allocated_microdollars=10_000_000)
        rec = _Recorder()
        tracker.set_threshold_callback(0.50, rec)

        # Each cycle reserves 100k, records actual 100k -- net committed
        # increases by 100k per successful cycle. After 50 cycles the
        # committed reaches 5M = 50% threshold, somewhere mid-stream.
        # Concurrent workers will race to the rising edge.

        def worker() -> None:
            for _ in range(10):
                if tracker.reserve(100_000):
                    tracker.record(100_000, 100_000)

        threads = [threading.Thread(target=worker) for _ in range(50)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Total budget consumed: 50 * 10 * 100k = 50M attempted, 10M cap.
        # By the time all join, committed = 10M (full budget) and reserved=0.
        assert tracker.remaining_microdollars() == 0
        # Threshold MUST have fired exactly once despite oscillation pressure.
        assert len(rec.events) == 1, f"expected one fire, got {len(rec.events)} events"
        evt = rec.events[0]
        assert evt.event_type == "custom_threshold"
        assert evt.threshold_pct == pytest.approx(0.50)

    def test_concurrent_callback_exceptions_isolated(self) -> None:
        """A callback that always raises does not corrupt budget state."""
        tracker = BudgetTracker(allocated_microdollars=10_000_000)
        order: List[str] = []
        order_lock = threading.Lock()

        def bomb(_evt: BudgetEvent) -> None:
            with order_lock:
                order.append("bomb")
            raise RuntimeError("intentional")

        def survivor(_evt: BudgetEvent) -> None:
            with order_lock:
                order.append("survivor")

        tracker.set_threshold_callback(0.50, bomb)
        tracker.set_threshold_callback(0.50, survivor)

        # Many threads attempt to reserve -- at least one will cross 50%
        # and trigger callback dispatch. Any callback raising MUST NOT
        # propagate to the worker thread or block the sibling.
        results: List[bool] = []
        results_lock = threading.Lock()

        def worker() -> None:
            ok = tracker.reserve(700_000)
            with results_lock:
                results.append(ok)

        threads = [threading.Thread(target=worker) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # No worker thread crashed.
        assert len(results) == 20
        # bomb + survivor both ran exactly once each (one-shot per handle).
        assert order.count("bomb") == 1
        assert order.count("survivor") == 1
        # Order: bomb fired first because registered first, then survivor.
        # Find the indices.
        bomb_idx = order.index("bomb")
        surv_idx = order.index("survivor")
        assert bomb_idx < surv_idx

    def test_multiple_thresholds_fire_independently_under_contention(
        self,
    ) -> None:
        """Distinct thresholds each fire once under concurrent load."""
        tracker = BudgetTracker(allocated_microdollars=10_000_000)
        rec_50 = _Recorder()
        rec_80 = _Recorder()
        rec_95 = _Recorder()
        tracker.set_threshold_callback(0.50, rec_50)
        tracker.set_threshold_callback(0.80, rec_80)
        tracker.set_threshold_callback(0.95, rec_95)

        # Workers consume the full budget through reserve+record cycles.
        def worker() -> None:
            for _ in range(20):
                if tracker.reserve(50_000):
                    tracker.record(50_000, 50_000)

        threads = [threading.Thread(target=worker) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All three thresholds fired exactly once (rising-edge per handle).
        assert len(rec_50.events) == 1, f"50% expected 1, got {len(rec_50.events)}"
        assert len(rec_80.events) == 1, f"80% expected 1, got {len(rec_80.events)}"
        assert len(rec_95.events) == 1, f"95% expected 1, got {len(rec_95.events)}"


# ---------------------------------------------------------------------------
# End-to-end Grant Moment scenario (Envoy Phase 01 motivation)
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestGrantMomentScenario:
    """Smoke test: caller registers a 'budget warning' handler, gets one event."""

    def test_full_lifecycle_register_consume_get_warning(self) -> None:
        # Budget: $5 = 5_000_000 microdollars
        tracker = BudgetTracker(allocated_microdollars=5_000_000)
        warnings: List[BudgetEvent] = []
        warn_lock = threading.Lock()

        def on_budget_warning(evt: BudgetEvent) -> None:
            with warn_lock:
                warnings.append(evt)

        # Operator wires a Grant Moment trigger at 80% utilization.
        tracker.set_threshold_callback(0.80, on_budget_warning)

        # Simulate a stream of LLM calls. Each "call" reserves 200k
        # ($0.20) then records actual 200k.
        for _i in range(25):
            if tracker.reserve(200_000):
                tracker.record(200_000, 200_000)

        # 25 * 200k = 5M (full budget).
        # Warning fires when committed first reaches 4M (80% of 5M).
        # Verify exactly one warning.
        assert len(warnings) == 1
        evt = warnings[0]
        assert evt.event_type == "custom_threshold"
        assert evt.threshold_pct == pytest.approx(0.80)
        assert evt.allocated_microdollars == 5_000_000
        # At fire time the *claimed* amount (committed + reserved) must be
        # >= 4M (80% of 5M). The predicate fires on `claimed`, not on
        # `committed` alone, so a snapshot might show committed=3.8M and
        # reserved=0.2M (claimed=4.0M) at the rising edge.
        assert evt.committed_microdollars is not None
        assert evt.reserved_microdollars is not None
        claimed = evt.committed_microdollars + evt.reserved_microdollars
        assert claimed >= 4_000_000
        # Final state: budget exhausted
        assert tracker.remaining_microdollars() == 0

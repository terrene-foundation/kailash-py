"""
Tier-2 integration tests for PerformanceTracker timing accuracy.

Moved from tests/unit/test_infrastructure_validation.py because these tests
use time.sleep() + timing assertions that are inherently flaky in CI
due to CPU contention on shared runners.
"""

import time

import pytest

from tests.utils.performance_tracker import PerformanceTracker


class TestPerformanceTracker:
    """Test PerformanceTracker utility for timing and metrics."""

    def test_performance_tracker_timing(self):
        """Performance tracker must accurately measure execution time."""
        tracker = PerformanceTracker("test_operation")

        # Start timing
        tracker.start()

        # Simulate work
        time.sleep(0.1)

        # Stop timing
        elapsed = tracker.stop()

        # Verify timing accuracy (within reasonable margin)
        # Increased upper bound to 0.3s for CI infrastructure variance
        assert 0.05 < elapsed < 0.3
        assert tracker.operation_name == "test_operation"
        assert tracker.start_time is not None
        assert tracker.end_time is not None
        assert tracker.elapsed_time == elapsed

    def test_performance_tracker_context_manager(self):
        """Performance tracker must work as context manager."""
        with PerformanceTracker("context_test") as tracker:
            time.sleep(0.05)

        # Verify context manager tracked timing
        assert tracker.elapsed_time > 0.04
        # Increased upper bound to 0.25s for CI infrastructure variance
        assert tracker.elapsed_time < 0.25
        assert tracker.operation_name == "context_test"

    def test_performance_tracker_metrics_collection(self):
        """Performance tracker must collect metrics properly."""
        tracker = PerformanceTracker("metrics_test")

        # Test basic metrics
        with tracker:
            time.sleep(0.02)

        metrics = tracker.get_metrics()

        assert "operation_name" in metrics
        assert "elapsed_time" in metrics
        assert "start_time" in metrics
        assert "end_time" in metrics
        assert metrics["operation_name"] == "metrics_test"
        assert metrics["elapsed_time"] > 0

    def test_performance_tracker_threshold_validation(self):
        """Performance tracker must validate against thresholds."""
        # Test under threshold
        # Increased threshold to 0.5s for CI infrastructure variance
        # CI runners can have significant timing variance due to CPU contention
        fast_tracker = PerformanceTracker("fast_test", threshold=0.5)
        with fast_tracker:
            time.sleep(0.02)

        assert fast_tracker.is_under_threshold()
        assert not fast_tracker.is_over_threshold()

        # Test over threshold
        slow_tracker = PerformanceTracker("slow_test", threshold=0.01)
        with slow_tracker:
            time.sleep(0.03)

        assert not slow_tracker.is_under_threshold()
        assert slow_tracker.is_over_threshold()

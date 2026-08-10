"""
Enhanced Performance Monitoring Utilities for 3-Tier Testing Strategy

Provides advanced performance monitoring, profiling, and validation tools
for ensuring all tests meet tier-specific performance requirements.
"""

import json
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import ContextManager, Dict, List, Optional, Union

import psutil
import pytest


@dataclass
class PerformanceMeasurement:
    """Single performance measurement with metadata."""

    operation: str
    tier: str
    duration_ms: float
    memory_start_mb: float
    memory_peak_mb: float
    memory_delta_mb: float
    cpu_percent: float
    timestamp: str
    test_name: Optional[str] = None
    passed_threshold: bool = True


class TierPerformanceMonitor:
    """
    Advanced performance monitor enforcing 3-tier testing requirements.

    Tier Limits:
    - Unit (Tier 1): <1000ms, isolated, mocking allowed
    - Integration (Tier 2): <5000ms, real services, NO MOCKING
    - E2E (Tier 3): <10000ms, complete workflows, NO MOCKING
    """

    # Tier performance thresholds (milliseconds)
    TIER_LIMITS = {
        "unit": 1000,  # 1 second - fast unit tests
        "integration": 5000,  # 5 seconds - real service integration
        "e2e": 10000,  # 10 seconds - complete workflows
    }

    # Component-specific limits (milliseconds)
    COMPONENT_LIMITS = {
        "framework_init": 100,
        "agent_creation": 200,
        "signature_creation": 10,
        "workflow_compilation": 200,
        "database_connection": 500,
        "redis_operation": 50,
        "memory_operation": 100,
    }

    def __init__(self):
        self.measurements: List[PerformanceMeasurement] = []
        self.process = psutil.Process()
        self._lock = threading.Lock()

    @contextmanager
    def measure(
        self,
        operation: str,
        tier: str = "unit",
        test_name: Optional[str] = None,
        expected_limit_ms: Optional[float] = None,
    ) -> ContextManager[PerformanceMeasurement]:
        """
        Context manager for measuring operation performance.

        Args:
            operation: Name of the operation being measured
            tier: Test tier (unit/integration/e2e)
            test_name: Optional test name for tracking
            expected_limit_ms: Override default tier limit

        Yields:
            PerformanceMeasurement that gets populated during execution
        """
        # Determine performance limit
        limit_ms = expected_limit_ms or self.TIER_LIMITS.get(tier, 1000)

        # Initialize measurement
        measurement = PerformanceMeasurement(
            operation=operation,
            tier=tier,
            duration_ms=0.0,
            memory_start_mb=0.0,
            memory_peak_mb=0.0,
            memory_delta_mb=0.0,
            cpu_percent=0.0,
            timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
            test_name=test_name,
        )

        # Start monitoring
        start_time = time.perf_counter()
        measurement.memory_start_mb = self.process.memory_info().rss / 1024 / 1024
        cpu_start = self.process.cpu_percent()

        # Track peak memory in background
        peak_memory = [measurement.memory_start_mb]
        monitoring = [True]

        def monitor_memory():
            while monitoring[0]:
                try:
                    current_memory = self.process.memory_info().rss / 1024 / 1024
                    if current_memory > peak_memory[0]:
                        peak_memory[0] = current_memory
                    time.sleep(0.01)  # Check every 10ms
                except:
                    break

        monitor_thread = threading.Thread(target=monitor_memory, daemon=True)
        monitor_thread.start()

        try:
            yield measurement
        finally:
            # Stop monitoring
            monitoring[0] = False
            monitor_thread.join(timeout=0.1)

            # Calculate final metrics
            end_time = time.perf_counter()
            measurement.duration_ms = (end_time - start_time) * 1000
            measurement.memory_peak_mb = peak_memory[0]
            measurement.memory_delta_mb = peak_memory[0] - measurement.memory_start_mb
            measurement.cpu_percent = self.process.cpu_percent() - cpu_start
            measurement.passed_threshold = measurement.duration_ms <= limit_ms

            # Store measurement
            with self._lock:
                self.measurements.append(measurement)

    def assert_tier_performance(self, operation: str, tier: str = "unit") -> None:
        """Assert that the last measurement for an operation meets tier requirements."""
        # Find the most recent measurement for this operation
        matching_measurements = [
            m for m in self.measurements if m.operation == operation and m.tier == tier
        ]

        if not matching_measurements:
            raise ValueError(
                f"No measurements found for operation '{operation}' in tier '{tier}'"
            )

        measurement = matching_measurements[-1]  # Most recent
        limit = self.TIER_LIMITS.get(tier, 1000)

        assert measurement.duration_ms <= limit, (
            f"Tier {tier} operation '{operation}' took {measurement.duration_ms:.2f}ms, "
            f"exceeding {tier} limit of {limit}ms"
        )

    def assert_component_performance(self, operation: str, component: str) -> None:
        """Assert that an operation meets component-specific performance requirements."""
        matching_measurements = [
            m for m in self.measurements if m.operation == operation
        ]

        if not matching_measurements:
            raise ValueError(f"No measurements found for operation '{operation}'")

        measurement = matching_measurements[-1]
        limit = self.COMPONENT_LIMITS.get(component, 1000)

        assert measurement.duration_ms <= limit, (
            f"Component '{component}' operation '{operation}' took {measurement.duration_ms:.2f}ms, "
            f"exceeding component limit of {limit}ms"
        )

    def get_tier_summary(self) -> Dict[str, List[Dict]]:
        """Get performance summary organized by tier."""
        summary = {"unit": [], "integration": [], "e2e": []}

        for measurement in self.measurements:
            if measurement.tier in summary:
                summary[measurement.tier].append(
                    {
                        "operation": measurement.operation,
                        "duration_ms": measurement.duration_ms,
                        "memory_delta_mb": measurement.memory_delta_mb,
                        "within_limit": measurement.passed_threshold,
                        "test_name": measurement.test_name,
                    }
                )

        return summary

    def get_performance_report(self) -> Dict:
        """Generate comprehensive performance report."""
        if not self.measurements:
            return {"error": "No measurements recorded"}

        # Organize by tier
        by_tier = {}
        for tier in ["unit", "integration", "e2e"]:
            tier_measurements = [m for m in self.measurements if m.tier == tier]
            if tier_measurements:
                durations = [m.duration_ms for m in tier_measurements]
                by_tier[tier] = {
                    "count": len(tier_measurements),
                    "avg_duration_ms": sum(durations) / len(durations),
                    "max_duration_ms": max(durations),
                    "min_duration_ms": min(durations),
                    "limit_ms": self.TIER_LIMITS[tier],
                    "passing_rate": sum(
                        1 for m in tier_measurements if m.passed_threshold
                    )
                    / len(tier_measurements),
                    "failures": [
                        {"operation": m.operation, "duration_ms": m.duration_ms}
                        for m in tier_measurements
                        if not m.passed_threshold
                    ],
                }

        # Component analysis
        by_component = {}
        for component, limit in self.COMPONENT_LIMITS.items():
            component_measurements = [
                m
                for m in self.measurements
                if component.replace("_", " ") in m.operation.lower()
            ]
            if component_measurements:
                durations = [m.duration_ms for m in component_measurements]
                by_component[component] = {
                    "count": len(component_measurements),
                    "avg_duration_ms": sum(durations) / len(durations),
                    "limit_ms": limit,
                    "passing_rate": sum(
                        1 for m in component_measurements if m.duration_ms <= limit
                    )
                    / len(component_measurements),
                }

        return {
            "total_measurements": len(self.measurements),
            "overall_passing_rate": sum(
                1 for m in self.measurements if m.passed_threshold
            )
            / len(self.measurements),
            "by_tier": by_tier,
            "by_component": by_component,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        }

    def save_report(self, filepath: Union[str, Path]) -> None:
        """Save performance report to JSON file."""
        report = self.get_performance_report()
        with open(filepath, "w") as f:
            json.dump(report, f, indent=2)

    def reset(self) -> None:
        """Clear all measurements."""
        with self._lock:
            self.measurements.clear()


class MemoryProfiler:
    """Memory usage profiler for detecting memory leaks and excessive usage."""

    def __init__(self):
        self.baseline_mb = None
        self.snapshots = []
        self.process = psutil.Process()

    def take_baseline(self) -> float:
        """Take baseline memory measurement."""
        self.baseline_mb = self.process.memory_info().rss / 1024 / 1024
        return self.baseline_mb

    def take_snapshot(self, label: str) -> Dict:
        """Take memory snapshot with label."""
        current_mb = self.process.memory_info().rss / 1024 / 1024
        snapshot = {
            "label": label,
            "memory_mb": current_mb,
            "delta_from_baseline_mb": current_mb - (self.baseline_mb or 0),
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        self.snapshots.append(snapshot)
        return snapshot

    def assert_memory_limit(self, limit_mb: float, label: str = "current") -> None:
        """Assert that current memory usage is within limit."""
        current_mb = self.process.memory_info().rss / 1024 / 1024
        assert (
            current_mb <= limit_mb
        ), f"Memory usage {current_mb:.1f}MB exceeds limit {limit_mb}MB for {label}"

    def assert_no_memory_leak(self, threshold_mb: float = 10.0) -> None:
        """Assert no significant memory increase from baseline."""
        if self.baseline_mb is None:
            raise ValueError("No baseline set. Call take_baseline() first.")

        current_mb = self.process.memory_info().rss / 1024 / 1024
        increase_mb = current_mb - self.baseline_mb

        assert increase_mb <= threshold_mb, (
            f"Memory leak detected: {increase_mb:.1f}MB increase from baseline "
            f"(threshold: {threshold_mb}MB)"
        )

    def get_memory_report(self) -> Dict:
        """Get memory usage report."""
        current_mb = self.process.memory_info().rss / 1024 / 1024
        return {
            "current_memory_mb": current_mb,
            "baseline_memory_mb": self.baseline_mb,
            "delta_from_baseline_mb": current_mb - (self.baseline_mb or 0),
            "snapshots": self.snapshots,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        }


# Global instances for shared use
global_performance_monitor = TierPerformanceMonitor()
global_memory_profiler = MemoryProfiler()


# Pytest fixtures
@pytest.fixture(scope="function")
def performance_monitor():
    """Per-test performance monitor that resets after each test."""
    monitor = TierPerformanceMonitor()
    yield monitor
    # Optionally save results or assert overall performance


@pytest.fixture(scope="function")
def memory_profiler():
    """Per-test memory profiler."""
    profiler = MemoryProfiler()
    profiler.take_baseline()
    yield profiler
    # Assert no major memory leaks
    try:
        profiler.assert_no_memory_leak(threshold_mb=50.0)
    except AssertionError as e:
        pytest.fail(f"Memory leak detected: {e}")


@pytest.fixture(scope="function")
def tier_validator():
    """Validates that tests are properly categorized and meet tier requirements."""

    class TierValidator:
        def __init__(self):
            self.tier_requirements = {
                "unit": {
                    "max_duration_ms": 1000,
                    "mocking_allowed": True,
                    "requires_infrastructure": False,
                },
                "integration": {
                    "max_duration_ms": 5000,
                    "mocking_allowed": False,  # NO MOCKING in Tier 2
                    "requires_infrastructure": True,
                },
                "e2e": {
                    "max_duration_ms": 10000,
                    "mocking_allowed": False,  # NO MOCKING in Tier 3
                    "requires_infrastructure": True,
                },
            }

        def validate_test_categorization(self, test_item):
            """Validate test is properly categorized with tier markers."""
            tier_markers = [
                marker.name
                for marker in test_item.iter_markers()
                if marker.name in ["unit", "integration", "e2e"]
            ]

            assert len(tier_markers) == 1, (
                f"Test {test_item.name} must have exactly one tier marker (unit/integration/e2e), "
                f"got: {tier_markers}"
            )

            return tier_markers[0]

        def validate_tier_compliance(
            self, tier: str, duration_ms: float, uses_mocks: bool = False
        ):
            """Validate test complies with tier requirements."""
            requirements = self.tier_requirements[tier]

            # Duration check
            assert duration_ms <= requirements["max_duration_ms"], (
                f"Tier {tier} test took {duration_ms:.1f}ms, "
                f"exceeding limit of {requirements['max_duration_ms']}ms"
            )

            # Mocking policy check for Tiers 2 and 3
            if tier in ["integration", "e2e"] and uses_mocks:
                raise AssertionError(
                    f"Tier {tier} test uses mocking, which violates NO MOCKING policy. "
                    f"Use real infrastructure instead."
                )

    return TierValidator()


# Decorators for performance testing
def performance_test(tier: str = "unit", max_duration_ms: Optional[float] = None):
    """
    Decorator for performance testing with automatic tier validation.

    Args:
        tier: Test tier (unit/integration/e2e)
        max_duration_ms: Override default tier limit
    """

    def decorator(test_func):
        def wrapper(*args, **kwargs):
            monitor = TierPerformanceMonitor()
            limit = max_duration_ms or monitor.TIER_LIMITS.get(tier, 1000)

            with monitor.measure(
                operation=test_func.__name__,
                tier=tier,
                test_name=test_func.__name__,
                expected_limit_ms=limit,
            ):
                result = test_func(*args, **kwargs)

            # Assert performance compliance
            monitor.assert_tier_performance(test_func.__name__, tier)

            return result

        return wrapper

    return decorator


# Export main classes and utilities
__all__ = [
    "TierPerformanceMonitor",
    "MemoryProfiler",
    "PerformanceMeasurement",
    "global_performance_monitor",
    "global_memory_profiler",
    "performance_test",
]

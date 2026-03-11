"""
Performance Tracker for Kaizen framework integration testing.

Provides timing and performance measurement utilities for test validation.
Used to ensure test execution meets performance requirements and tracks
regression in framework initialization, agent creation, and workflow execution.

Based on Kailash Core SDK performance tracking with Kaizen-specific metrics.
"""

import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import psutil


@dataclass
class PerformanceMetrics:
    """Performance measurement data structure."""

    operation_name: str
    start_time: float
    end_time: Optional[float]
    elapsed_time_ms: Optional[float]
    memory_start_mb: float
    memory_end_mb: Optional[float]
    memory_delta_mb: Optional[float]
    cpu_percent: Optional[float]
    success: bool = True
    error_message: Optional[str] = None


class PerformanceTracker:
    """Enhanced performance tracking utility for Kaizen framework testing."""

    def __init__(self, operation_name: str, threshold_ms: Optional[float] = None):
        """
        Initialize performance tracker.

        Args:
            operation_name: Name of the operation being tracked
            threshold_ms: Optional performance threshold in milliseconds
        """
        self.operation_name = operation_name
        self.threshold_ms = threshold_ms
        self.metrics: Optional[PerformanceMetrics] = None
        self._cpu_monitor_thread = None
        self._cpu_samples = []
        self._monitor_cpu = False

    def start(self, monitor_cpu: bool = False) -> None:
        """
        Start timing the operation.

        Args:
            monitor_cpu: Whether to monitor CPU usage during operation
        """
        process = psutil.Process()
        memory_info = process.memory_info()

        self.metrics = PerformanceMetrics(
            operation_name=self.operation_name,
            start_time=time.perf_counter(),
            end_time=None,
            elapsed_time_ms=None,
            memory_start_mb=memory_info.rss / 1024 / 1024,
            memory_end_mb=None,
            memory_delta_mb=None,
            cpu_percent=None,
        )

        # Start CPU monitoring if requested
        if monitor_cpu:
            self._start_cpu_monitoring()

    def stop(self) -> float:
        """
        Stop timing and calculate elapsed time.

        Returns:
            Elapsed time in milliseconds
        """
        if self.metrics is None:
            raise ValueError("Timer not started. Call start() first.")

        # Stop CPU monitoring
        self._stop_cpu_monitoring()

        # Capture end metrics
        process = psutil.Process()
        memory_info = process.memory_info()

        self.metrics.end_time = time.perf_counter()
        self.metrics.elapsed_time_ms = (
            self.metrics.end_time - self.metrics.start_time
        ) * 1000
        self.metrics.memory_end_mb = memory_info.rss / 1024 / 1024
        self.metrics.memory_delta_mb = (
            self.metrics.memory_end_mb - self.metrics.memory_start_mb
        )

        # Calculate average CPU usage if monitored
        if self._cpu_samples:
            self.metrics.cpu_percent = sum(self._cpu_samples) / len(self._cpu_samples)

        return self.metrics.elapsed_time_ms

    def _start_cpu_monitoring(self):
        """Start background CPU monitoring."""
        self._monitor_cpu = True
        self._cpu_samples = []
        self._cpu_monitor_thread = threading.Thread(target=self._monitor_cpu_usage)
        self._cpu_monitor_thread.daemon = True
        self._cpu_monitor_thread.start()

    def _stop_cpu_monitoring(self):
        """Stop background CPU monitoring."""
        self._monitor_cpu = False
        if self._cpu_monitor_thread and self._cpu_monitor_thread.is_alive():
            self._cpu_monitor_thread.join(timeout=1.0)

    def _monitor_cpu_usage(self):
        """Background thread function to monitor CPU usage."""
        process = psutil.Process()
        while self._monitor_cpu:
            try:
                cpu_percent = process.cpu_percent(interval=0.1)
                self._cpu_samples.append(cpu_percent)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                break
            time.sleep(0.1)

    def __enter__(self):
        """Context manager entry."""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        if exc_type is not None:
            # Mark as failed if exception occurred
            if self.metrics:
                self.metrics.success = False
                self.metrics.error_message = str(exc_val)
        self.stop()

    def get_metrics(self) -> Dict[str, Any]:
        """
        Get performance metrics.

        Returns:
            Dictionary containing performance metrics
        """
        if self.metrics is None:
            return {"error": "No metrics available - timer not started"}

        return {
            "operation_name": self.metrics.operation_name,
            "elapsed_time_ms": self.metrics.elapsed_time_ms,
            "memory_start_mb": round(self.metrics.memory_start_mb, 2),
            "memory_end_mb": (
                round(self.metrics.memory_end_mb, 2)
                if self.metrics.memory_end_mb
                else None
            ),
            "memory_delta_mb": (
                round(self.metrics.memory_delta_mb, 2)
                if self.metrics.memory_delta_mb
                else None
            ),
            "cpu_percent": (
                round(self.metrics.cpu_percent, 2) if self.metrics.cpu_percent else None
            ),
            "threshold_ms": self.threshold_ms,
            "is_under_threshold": (
                self.is_under_threshold() if self.threshold_ms else None
            ),
            "success": self.metrics.success,
            "error_message": self.metrics.error_message,
        }

    def is_under_threshold(self) -> bool:
        """
        Check if elapsed time is under the threshold.

        Returns:
            True if under threshold, False otherwise
        """
        if self.threshold_ms is None:
            raise ValueError("No threshold set")
        if self.metrics is None or self.metrics.elapsed_time_ms is None:
            raise ValueError("Timer not stopped. Call stop() first.")

        return self.metrics.elapsed_time_ms <= self.threshold_ms

    def assert_performance(
        self, max_time_ms: Optional[float] = None, max_memory_mb: Optional[float] = None
    ):
        """
        Assert performance requirements are met.

        Args:
            max_time_ms: Maximum allowed execution time in milliseconds
            max_memory_mb: Maximum allowed memory usage in MB
        """
        if self.metrics is None or self.metrics.elapsed_time_ms is None:
            raise ValueError("Timer not stopped. Call stop() first.")

        # Check time threshold
        time_limit = max_time_ms or self.threshold_ms
        if time_limit:
            assert self.metrics.elapsed_time_ms <= time_limit, (
                f"Operation '{self.operation_name}' took {self.metrics.elapsed_time_ms:.2f}ms, "
                f"exceeding limit of {time_limit}ms"
            )

        # Check memory threshold
        if max_memory_mb and self.metrics.memory_delta_mb:
            assert self.metrics.memory_delta_mb <= max_memory_mb, (
                f"Operation '{self.operation_name}' used {self.metrics.memory_delta_mb:.2f}MB memory, "
                f"exceeding limit of {max_memory_mb}MB"
            )

        # Check for success
        assert (
            self.metrics.success
        ), f"Operation '{self.operation_name}' failed: {self.metrics.error_message}"


class BenchmarkSuite:
    """Suite for running multiple performance benchmarks."""

    def __init__(self, suite_name: str):
        """
        Initialize benchmark suite.

        Args:
            suite_name: Name of the benchmark suite
        """
        self.suite_name = suite_name
        self.benchmarks: List[PerformanceTracker] = []
        self.suite_start_time: Optional[float] = None
        self.suite_end_time: Optional[float] = None

    def start_suite(self):
        """Start the benchmark suite."""
        self.suite_start_time = time.perf_counter()
        self.benchmarks = []

    def add_benchmark(self, benchmark: PerformanceTracker):
        """Add a completed benchmark to the suite."""
        self.benchmarks.append(benchmark)

    @contextmanager
    def benchmark(self, operation_name: str, threshold_ms: Optional[float] = None):
        """Context manager for running a single benchmark."""
        tracker = PerformanceTracker(operation_name, threshold_ms)
        try:
            yield tracker
        finally:
            self.add_benchmark(tracker)

    def end_suite(self):
        """End the benchmark suite."""
        self.suite_end_time = time.perf_counter()

    def get_suite_summary(self) -> Dict[str, Any]:
        """Get summary of all benchmarks in the suite."""
        if not self.benchmarks:
            return {"error": "No benchmarks recorded"}

        total_time_ms = 0
        total_memory_mb = 0
        failed_count = 0
        benchmark_details = []

        for benchmark in self.benchmarks:
            metrics = benchmark.get_metrics()
            benchmark_details.append(metrics)

            if metrics.get("elapsed_time_ms"):
                total_time_ms += metrics["elapsed_time_ms"]

            if metrics.get("memory_delta_mb") and metrics["memory_delta_mb"] > 0:
                total_memory_mb += metrics["memory_delta_mb"]

            if not metrics.get("success", True):
                failed_count += 1

        suite_duration_ms = None
        if self.suite_start_time and self.suite_end_time:
            suite_duration_ms = (self.suite_end_time - self.suite_start_time) * 1000

        return {
            "suite_name": self.suite_name,
            "suite_duration_ms": suite_duration_ms,
            "benchmark_count": len(self.benchmarks),
            "total_operation_time_ms": round(total_time_ms, 2),
            "total_memory_used_mb": round(total_memory_mb, 2),
            "failed_benchmarks": failed_count,
            "success_rate": (
                (len(self.benchmarks) - failed_count) / len(self.benchmarks)
                if self.benchmarks
                else 0
            ),
            "benchmark_details": benchmark_details,
        }

    def assert_suite_performance(
        self,
        max_total_time_ms: Optional[float] = None,
        max_avg_time_ms: Optional[float] = None,
        max_memory_mb: Optional[float] = None,
        min_success_rate: float = 1.0,
    ):
        """Assert overall suite performance requirements."""
        summary = self.get_suite_summary()

        if max_total_time_ms:
            assert summary["total_operation_time_ms"] <= max_total_time_ms, (
                f"Suite '{self.suite_name}' total time {summary['total_operation_time_ms']:.2f}ms "
                f"exceeds limit of {max_total_time_ms}ms"
            )

        if max_avg_time_ms and summary["benchmark_count"] > 0:
            avg_time = summary["total_operation_time_ms"] / summary["benchmark_count"]
            assert avg_time <= max_avg_time_ms, (
                f"Suite '{self.suite_name}' average time {avg_time:.2f}ms "
                f"exceeds limit of {max_avg_time_ms}ms"
            )

        if max_memory_mb:
            assert summary["total_memory_used_mb"] <= max_memory_mb, (
                f"Suite '{self.suite_name}' memory usage {summary['total_memory_used_mb']:.2f}MB "
                f"exceeds limit of {max_memory_mb}MB"
            )

        assert summary["success_rate"] >= min_success_rate, (
            f"Suite '{self.suite_name}' success rate {summary['success_rate']:.2%} "
            f"below required {min_success_rate:.2%}"
        )


# Performance baseline constants for Kaizen framework
KAIZEN_PERFORMANCE_BASELINES = {
    # Framework initialization
    "framework_init_ms": 200,  # Framework initialization < 200ms
    "framework_init_memory_mb": 10,  # Memory usage < 10MB
    # Agent operations
    "agent_creation_ms": 100,  # Agent creation < 100ms
    "agent_creation_memory_mb": 5,  # Memory per agent < 5MB
    # Workflow operations
    "workflow_compilation_ms": 300,  # Workflow compilation < 300ms
    "workflow_execution_ms": 5000,  # Workflow execution < 5s
    # Signature operations
    "signature_validation_ms": 50,  # Signature validation < 50ms
    "signature_compilation_ms": 200,  # Signature compilation < 200ms
    # Enterprise features
    "audit_trail_generation_ms": 100,  # Audit trail < 100ms
    "memory_persistence_ms": 200,  # Memory operations < 200ms
    "optimization_analysis_ms": 1000,  # Optimization analysis < 1s
}


def performance_tracker(
    operation_name: str, threshold_ms: Optional[float] = None, monitor_cpu: bool = False
) -> PerformanceTracker:
    """
    Factory function to create a PerformanceTracker with default settings.

    Args:
        operation_name: Name of the operation
        threshold_ms: Optional performance threshold in milliseconds
        monitor_cpu: Whether to monitor CPU usage

    Returns:
        PerformanceTracker instance
    """
    tracker = PerformanceTracker(operation_name, threshold_ms)
    if monitor_cpu:
        tracker.start(monitor_cpu=True)
    return tracker


@contextmanager
def measure_performance(
    operation_name: str,
    threshold_ms: Optional[float] = None,
    assert_on_exit: bool = False,
):
    """
    Context manager for measuring performance with optional assertion.

    Args:
        operation_name: Name of the operation
        threshold_ms: Optional performance threshold in milliseconds
        assert_on_exit: Whether to assert performance on exit

    Usage:
        with measure_performance("test_operation", threshold_ms=100, assert_on_exit=True):
            # Code to measure
            pass
    """
    tracker = PerformanceTracker(operation_name, threshold_ms)
    tracker.start()
    try:
        yield tracker
    finally:
        tracker.stop()
        if assert_on_exit and threshold_ms:
            tracker.assert_performance(max_time_ms=threshold_ms)


# Kaizen-specific performance utilities
class KaizenFrameworkBenchmark(BenchmarkSuite):
    """Specialized benchmark suite for Kaizen framework operations."""

    def __init__(self):
        super().__init__("Kaizen Framework Performance")

    async def benchmark_framework_initialization(self) -> PerformanceTracker:
        """Benchmark Kaizen framework initialization."""
        with self.benchmark(
            "framework_initialization",
            KAIZEN_PERFORMANCE_BASELINES["framework_init_ms"],
        ) as tracker:
            from kaizen.core.config import KaizenConfig
            from kaizen.core.framework import Kaizen

            tracker.start(monitor_cpu=True)
            config = KaizenConfig(debug=True, memory_enabled=True)
            kaizen = Kaizen(config=config)
            tracker.stop()

            # Clean up
            kaizen._agents.clear()
            kaizen._signatures.clear()

        return tracker

    async def benchmark_agent_creation(
        self, kaizen, agent_configs: List[Dict]
    ) -> List[PerformanceTracker]:
        """Benchmark agent creation performance."""
        trackers = []

        for i, config in enumerate(agent_configs):
            with self.benchmark(
                f"agent_creation_{i}", KAIZEN_PERFORMANCE_BASELINES["agent_creation_ms"]
            ) as tracker:
                tracker.start()
                kaizen.create_agent(f"test_agent_{i}", config)
                tracker.stop()
                trackers.append(tracker)

        return trackers

    async def benchmark_workflow_execution(
        self, agents: List, runtime
    ) -> List[PerformanceTracker]:
        """Benchmark workflow execution performance."""
        trackers = []

        for i, agent in enumerate(agents):
            with self.benchmark(
                f"workflow_execution_{i}",
                KAIZEN_PERFORMANCE_BASELINES["workflow_execution_ms"],
            ) as tracker:
                tracker.start()
                workflow = agent.compile_workflow()
                results, run_id = runtime.execute(workflow.build())
                tracker.stop()
                trackers.append(tracker)

        return trackers

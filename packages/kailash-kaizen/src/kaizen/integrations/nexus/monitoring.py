"""
Performance monitoring for Kaizen-Nexus integrations.

This module provides performance metrics collection and analysis for
Nexus deployment and execution operations.

Features:
- Deployment time tracking
- API/CLI/MCP latency monitoring
- Session sync performance
- Statistical analysis (mean, median, min, max)
- Performance summary reports

Part of TODO-149 Phase 4: Performance & Testing
"""

import time
from dataclasses import dataclass, field
from statistics import mean, median
from typing import Dict, List


@dataclass
class PerformanceMetrics:
    """
    Track performance metrics for Nexus operations.

    This class collects timing data for various Nexus operations and
    provides statistical analysis for performance monitoring.

    Performance Targets:
    - Multi-channel deployment: <2s
    - API latency: <500ms
    - CLI latency: <500ms
    - MCP latency: <500ms
    - Session sync: <50ms

    Example:
        >>> metrics = PerformanceMetrics()
        >>> start = time.time()
        >>> # ... perform deployment ...
        >>> metrics.record_deployment(time.time() - start)
        >>> summary = metrics.get_summary()
        >>> print(f"Avg deployment: {summary['deployment']['mean']:.3f}s")
    """

    deployment_times: List[float] = field(default_factory=list)
    api_latencies: List[float] = field(default_factory=list)
    cli_latencies: List[float] = field(default_factory=list)
    mcp_latencies: List[float] = field(default_factory=list)
    session_sync_times: List[float] = field(default_factory=list)

    def record_deployment(self, duration: float):
        """
        Record deployment time.

        Args:
            duration: Deployment duration in seconds
        """
        self.deployment_times.append(duration)

    def record_api_latency(self, duration: float):
        """
        Record API response latency.

        Args:
            duration: API response time in seconds
        """
        self.api_latencies.append(duration)

    def record_cli_latency(self, duration: float):
        """
        Record CLI execution latency.

        Args:
            duration: CLI execution time in seconds
        """
        self.cli_latencies.append(duration)

    def record_mcp_latency(self, duration: float):
        """
        Record MCP tool latency.

        Args:
            duration: MCP tool response time in seconds
        """
        self.mcp_latencies.append(duration)

    def record_session_sync(self, duration: float):
        """
        Record session sync time.

        Args:
            duration: Session synchronization time in seconds
        """
        self.session_sync_times.append(duration)

    def get_summary(self) -> Dict[str, Dict[str, float]]:
        """
        Get performance summary statistics.

        Returns:
            Dictionary with stats for each metric category
        """
        return {
            "deployment": self._stats(self.deployment_times),
            "api": self._stats(self.api_latencies),
            "cli": self._stats(self.cli_latencies),
            "mcp": self._stats(self.mcp_latencies),
            "session_sync": self._stats(self.session_sync_times),
        }

    @staticmethod
    def _stats(values: List[float]) -> Dict[str, float]:
        """
        Calculate statistics for a list of values.

        Args:
            values: List of timing values in seconds

        Returns:
            Dictionary with mean, median, min, max, and count
        """
        if not values:
            return {"mean": 0, "median": 0, "min": 0, "max": 0, "count": 0}

        return {
            "mean": mean(values),
            "median": median(values),
            "min": min(values),
            "max": max(values),
            "count": len(values),
        }

    def reset(self):
        """Reset all metrics."""
        self.deployment_times.clear()
        self.api_latencies.clear()
        self.cli_latencies.clear()
        self.mcp_latencies.clear()
        self.session_sync_times.clear()

    def print_summary(self, prefix: str = ""):
        """
        Print performance summary to console.

        Args:
            prefix: Optional prefix for output lines
        """
        summary = self.get_summary()

        print(f"{prefix}=== Performance Summary ===")
        print(f"{prefix}")

        for category, stats in summary.items():
            if stats["count"] == 0:
                continue

            print(f"{prefix}{category.upper()}:")
            print(f"{prefix}  Mean:   {stats['mean']*1000:.1f}ms")
            print(f"{prefix}  Median: {stats['median']*1000:.1f}ms")
            print(f"{prefix}  Min:    {stats['min']*1000:.1f}ms")
            print(f"{prefix}  Max:    {stats['max']*1000:.1f}ms")
            print(f"{prefix}  Count:  {stats['count']}")
            print(f"{prefix}")


class PerformanceMonitor:
    """
    Context manager for performance monitoring.

    This class provides a convenient way to measure operation duration
    and automatically record it in a PerformanceMetrics instance.

    Example:
        >>> metrics = PerformanceMetrics()
        >>> with PerformanceMonitor(metrics, 'deployment'):
        ...     # ... perform deployment ...
        ...     pass
        >>> print(f"Deployment took {metrics.deployment_times[-1]:.3f}s")
    """

    def __init__(self, metrics: PerformanceMetrics, operation: str):
        """
        Initialize performance monitor.

        Args:
            metrics: PerformanceMetrics instance to record to
            operation: Operation type ('deployment', 'api', 'cli', 'mcp', 'session_sync')
        """
        self.metrics = metrics
        self.operation = operation
        self.start_time = None

    def __enter__(self):
        """Start timing."""
        self.start_time = time.time()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Stop timing and record duration."""
        duration = time.time() - self.start_time

        # Record based on operation type
        if self.operation == "deployment":
            self.metrics.record_deployment(duration)
        elif self.operation == "api":
            self.metrics.record_api_latency(duration)
        elif self.operation == "cli":
            self.metrics.record_cli_latency(duration)
        elif self.operation == "mcp":
            self.metrics.record_mcp_latency(duration)
        elif self.operation == "session_sync":
            self.metrics.record_session_sync(duration)

        return False  # Don't suppress exceptions


# Module-level metrics instance
_global_metrics = PerformanceMetrics()


def get_global_metrics() -> PerformanceMetrics:
    """
    Get the module-level performance metrics instance.

    Returns:
        Global PerformanceMetrics instance
    """
    return _global_metrics


def reset_global_metrics():
    """
    Reset the module-level performance metrics.

    Useful for testing or when starting a new measurement period.
    """
    _global_metrics.reset()

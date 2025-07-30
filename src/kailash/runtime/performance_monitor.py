"""Performance monitoring for conditional execution.

This module provides performance tracking and automatic fallback capabilities
for the conditional execution feature.
"""

import logging
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class ExecutionMetrics:
    """Metrics for a single execution."""

    execution_time: float
    node_count: int
    skipped_nodes: int
    memory_usage: Optional[float] = None
    execution_mode: str = "route_data"

    @property
    def nodes_per_second(self) -> float:
        """Calculate execution rate."""
        if self.execution_time > 0:
            return self.node_count / self.execution_time
        return 0.0

    @property
    def skip_ratio(self) -> float:
        """Calculate percentage of nodes skipped."""
        total = self.node_count + self.skipped_nodes
        if total > 0:
            return self.skipped_nodes / total
        return 0.0


class PerformanceMonitor:
    """Monitor performance and make mode switching decisions.

    Tracks execution performance of conditional vs standard execution
    and automatically switches modes based on performance thresholds.
    """

    def __init__(
        self,
        performance_threshold: float = 0.9,  # Switch if conditional is 90% slower
        sample_size: int = 10,
        min_samples: int = 3,
    ):
        """Initialize performance monitor.

        Args:
            performance_threshold: Ratio threshold for switching modes (0.9 = 10% slower triggers switch)
            sample_size: Number of recent executions to track
            min_samples: Minimum samples before making switching decisions
        """
        self.performance_threshold = performance_threshold
        self.sample_size = sample_size
        self.min_samples = min_samples

        # Track metrics for each mode
        self.metrics: Dict[str, deque] = {
            "route_data": deque(maxlen=sample_size),
            "skip_branches": deque(maxlen=sample_size),
        }

        # Performance statistics
        self.mode_performance: Dict[str, float] = {
            "route_data": 0.0,
            "skip_branches": 0.0,
        }

        # Current recommendation
        self.recommended_mode = "route_data"  # Safe default
        self._last_evaluation_time = 0.0
        self._evaluation_interval = 60.0  # Re-evaluate every minute

    def record_execution(self, metrics: ExecutionMetrics) -> None:
        """Record execution metrics.

        Args:
            metrics: Execution metrics to record
        """
        mode = metrics.execution_mode
        if mode in self.metrics:
            self.metrics[mode].append(metrics)
            logger.debug(
                f"Recorded {mode} execution: {metrics.execution_time:.3f}s, "
                f"{metrics.node_count} nodes, {metrics.skipped_nodes} skipped"
            )

    def should_switch_mode(self, current_mode: str) -> Tuple[bool, str, str]:
        """Determine if mode should be switched based on performance.

        Args:
            current_mode: Currently active execution mode

        Returns:
            Tuple of (should_switch, recommended_mode, reason)
        """
        # Check if enough time has passed since last evaluation
        current_time = time.time()
        if current_time - self._last_evaluation_time < self._evaluation_interval:
            return False, current_mode, "Too soon since last evaluation"

        self._last_evaluation_time = current_time

        # Calculate average performance for each mode
        route_data_avg = self._calculate_average_performance("route_data")
        skip_branches_avg = self._calculate_average_performance("skip_branches")

        # Not enough data to make decision
        if route_data_avg is None or skip_branches_avg is None:
            return False, current_mode, "Insufficient performance data"

        # Update performance statistics
        self.mode_performance["route_data"] = route_data_avg
        self.mode_performance["skip_branches"] = skip_branches_avg

        # Determine recommendation based on performance
        if skip_branches_avg < route_data_avg * self.performance_threshold:
            # skip_branches is significantly faster
            self.recommended_mode = "skip_branches"
            if current_mode != "skip_branches":
                reason = (
                    f"skip_branches mode is {(1 - skip_branches_avg/route_data_avg)*100:.1f}% faster "
                    f"({skip_branches_avg:.3f}s vs {route_data_avg:.3f}s)"
                )
                return True, "skip_branches", reason
        else:
            # route_data is faster or difference is negligible
            self.recommended_mode = "route_data"
            if current_mode != "route_data":
                reason = (
                    f"route_data mode is faster or difference negligible "
                    f"({route_data_avg:.3f}s vs {skip_branches_avg:.3f}s)"
                )
                return True, "route_data", reason

        return False, current_mode, "Current mode is optimal"

    def _calculate_average_performance(self, mode: str) -> Optional[float]:
        """Calculate average execution time for a mode.

        Args:
            mode: Execution mode to analyze

        Returns:
            Average execution time per node, or None if insufficient data
        """
        if mode not in self.metrics:
            return None

        metrics_list = list(self.metrics[mode])
        if len(metrics_list) < self.min_samples:
            return None

        # Calculate average time per node
        total_time = sum(m.execution_time for m in metrics_list)
        total_nodes = sum(m.node_count for m in metrics_list)

        if total_nodes > 0:
            return total_time / total_nodes
        return None

    def get_performance_report(self) -> Dict[str, any]:
        """Generate performance report.

        Returns:
            Dictionary with performance statistics
        """
        report = {
            "recommended_mode": self.recommended_mode,
            "mode_performance": self.mode_performance.copy(),
            "sample_counts": {
                mode: len(metrics) for mode, metrics in self.metrics.items()
            },
            "performance_threshold": self.performance_threshold,
        }

        # Add detailed metrics if available
        for mode, metrics_deque in self.metrics.items():
            if metrics_deque:
                metrics_list = list(metrics_deque)
                report[f"{mode}_stats"] = {
                    "avg_execution_time": sum(m.execution_time for m in metrics_list)
                    / len(metrics_list),
                    "avg_nodes": sum(m.node_count for m in metrics_list)
                    / len(metrics_list),
                    "avg_skip_ratio": sum(m.skip_ratio for m in metrics_list)
                    / len(metrics_list),
                    "total_executions": len(metrics_list),
                }

        return report

    def clear_metrics(self, mode: Optional[str] = None) -> None:
        """Clear performance metrics.

        Args:
            mode: Specific mode to clear, or None to clear all
        """
        if mode:
            if mode in self.metrics:
                self.metrics[mode].clear()
        else:
            for m in self.metrics.values():
                m.clear()

        logger.info(f"Cleared performance metrics for: {mode or 'all modes'}")

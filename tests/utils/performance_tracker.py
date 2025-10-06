"""
Performance Tracker for Test Infrastructure

Provides timing and performance measurement utilities for test validation.
Used to ensure test execution meets performance requirements.
"""

import time
from typing import Any, Dict, Optional


class PerformanceTracker:
    """Performance tracking utility for test timing and metrics."""

    def __init__(self, operation_name: str, threshold: Optional[float] = None):
        """
        Initialize performance tracker.

        Args:
            operation_name: Name of the operation being tracked
            threshold: Optional performance threshold in seconds
        """
        self.operation_name = operation_name
        self.threshold = threshold
        self.start_time: Optional[float] = None
        self.end_time: Optional[float] = None
        self.elapsed_time: Optional[float] = None

    def start(self) -> None:
        """Start timing the operation."""
        self.start_time = time.time()
        self.end_time = None
        self.elapsed_time = None

    def stop(self) -> float:
        """
        Stop timing and calculate elapsed time.

        Returns:
            Elapsed time in seconds
        """
        if self.start_time is None:
            raise ValueError("Timer not started. Call start() first.")

        self.end_time = time.time()
        self.elapsed_time = self.end_time - self.start_time
        return self.elapsed_time

    def __enter__(self):
        """Context manager entry."""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.stop()

    def get_metrics(self) -> Dict[str, Any]:
        """
        Get performance metrics.

        Returns:
            Dictionary containing performance metrics
        """
        return {
            "operation_name": self.operation_name,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "elapsed_time": self.elapsed_time,
            "threshold": self.threshold,
            "is_under_threshold": self.is_under_threshold() if self.threshold else None,
            "is_over_threshold": self.is_over_threshold() if self.threshold else None,
        }

    def is_under_threshold(self) -> bool:
        """
        Check if elapsed time is under the threshold.

        Returns:
            True if under threshold, False otherwise

        Raises:
            ValueError: If no threshold set or timer not stopped
        """
        if self.threshold is None:
            raise ValueError("No threshold set")
        if self.elapsed_time is None:
            raise ValueError("Timer not stopped. Call stop() first.")

        return self.elapsed_time <= self.threshold

    def is_over_threshold(self) -> bool:
        """
        Check if elapsed time is over the threshold.

        Returns:
            True if over threshold, False otherwise

        Raises:
            ValueError: If no threshold set or timer not stopped
        """
        if self.threshold is None:
            raise ValueError("No threshold set")
        if self.elapsed_time is None:
            raise ValueError("Timer not stopped. Call stop() first.")

        return self.elapsed_time > self.threshold

    def assert_under_threshold(self, message: Optional[str] = None) -> None:
        """
        Assert that elapsed time is under threshold.

        Args:
            message: Optional custom assertion message

        Raises:
            AssertionError: If over threshold
            ValueError: If no threshold set or timer not stopped
        """
        if not self.is_under_threshold():
            default_message = (
                f"Operation '{self.operation_name}' took {self.elapsed_time:.3f}s, "
                f"exceeding threshold of {self.threshold:.3f}s"
            )
            raise AssertionError(message or default_message)

    def get_formatted_result(self) -> str:
        """
        Get formatted performance result string.

        Returns:
            Formatted string with performance information
        """
        if self.elapsed_time is None:
            return f"Operation '{self.operation_name}' - Not completed"

        result = f"Operation '{self.operation_name}' took {self.elapsed_time:.3f}s"

        if self.threshold is not None:
            status = "✓ PASS" if self.is_under_threshold() else "✗ FAIL"
            result += f" (threshold: {self.threshold:.3f}s) - {status}"

        return result


class PerformanceReport:
    """Aggregate performance reporting for multiple operations."""

    def __init__(self):
        """Initialize performance report."""
        self.trackers: Dict[str, PerformanceTracker] = {}

    def add_tracker(self, tracker: PerformanceTracker) -> None:
        """
        Add a performance tracker to the report.

        Args:
            tracker: PerformanceTracker instance to add
        """
        self.trackers[tracker.operation_name] = tracker

    def get_summary(self) -> Dict[str, Any]:
        """
        Get performance summary for all tracked operations.

        Returns:
            Summary dictionary with aggregate metrics
        """
        if not self.trackers:
            return {"total_operations": 0, "operations": []}

        completed_trackers = [
            tracker
            for tracker in self.trackers.values()
            if tracker.elapsed_time is not None
        ]

        total_time = sum(tracker.elapsed_time for tracker in completed_trackers)
        avg_time = total_time / len(completed_trackers) if completed_trackers else 0

        threshold_checks = [
            tracker for tracker in completed_trackers if tracker.threshold is not None
        ]
        passed_thresholds = sum(
            1 for tracker in threshold_checks if tracker.is_under_threshold()
        )

        return {
            "total_operations": len(self.trackers),
            "completed_operations": len(completed_trackers),
            "total_time": total_time,
            "average_time": avg_time,
            "threshold_checks": len(threshold_checks),
            "passed_thresholds": passed_thresholds,
            "failed_thresholds": len(threshold_checks) - passed_thresholds,
            "operations": [tracker.get_metrics() for tracker in completed_trackers],
        }

    def generate_report(self) -> str:
        """
        Generate formatted performance report.

        Returns:
            Formatted performance report string
        """
        summary = self.get_summary()

        if summary["total_operations"] == 0:
            return "No operations tracked"

        lines = [
            "Performance Report",
            "=" * 50,
            f"Total Operations: {summary['total_operations']}",
            f"Completed Operations: {summary['completed_operations']}",
            f"Total Time: {summary['total_time']:.3f}s",
            f"Average Time: {summary['average_time']:.3f}s",
            "",
        ]

        if summary["threshold_checks"] > 0:
            lines.extend(
                [
                    f"Threshold Checks: {summary['threshold_checks']}",
                    f"Passed: {summary['passed_thresholds']}",
                    f"Failed: {summary['failed_thresholds']}",
                    "",
                ]
            )

        lines.append("Individual Operations:")
        lines.append("-" * 30)

        for operation in summary["operations"]:
            name = operation["operation_name"]
            time_str = f"{operation['elapsed_time']:.3f}s"

            if operation.get("threshold"):
                threshold_str = f"({operation['threshold']:.3f}s threshold)"
                status = "✓" if operation["is_under_threshold"] else "✗"
                lines.append(f"{name}: {time_str} {threshold_str} {status}")
            else:
                lines.append(f"{name}: {time_str}")

        return "\n".join(lines)

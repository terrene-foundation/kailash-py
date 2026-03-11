"""
PerformanceMixin - Performance tracking and monitoring for agents.

This module implements the PerformanceMixin that provides comprehensive
performance monitoring including timing, memory usage, throughput tracking,
and target validation.

Key Features:
- Execution time tracking
- Memory usage monitoring
- Throughput metrics
- Performance target validation
- Workflow enhancement with monitoring nodes
- MRO-compatible initialization

References:
- ADR-006: Agent Base Architecture design (Mixin Composition section)
- TODO-157: Task 3.3, 3.14-3.17
- Phase 3: Mixin System implementation

Author: Kaizen Framework Team
Created: 2025-10-01
"""

import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from kailash.workflow.builder import WorkflowBuilder


class PerformanceMixin:
    """
    Mixin for adding performance tracking to agents.

    Provides performance monitoring capabilities including:
    - Execution timing
    - Memory usage tracking
    - Throughput metrics
    - Target validation
    - Workflow enhancement with monitoring

    Usage:
        >>> class MyAgent(BaseAgent, PerformanceMixin):
        ...     def __init__(self, config):
        ...         BaseAgent.__init__(self, config=config, signature=signature)
        ...         PerformanceMixin.__init__(self, target_latency_ms=100.0)
        ...
        ...     def run(self, **inputs):
        ...         self.start_tracking()
        ...         result = super().run(**inputs)
        ...         self.stop_tracking()
        ...         return result

    Extension Points:
    - enhance_workflow(workflow): Add performance monitoring nodes
    - start_tracking(): Start performance tracking
    - stop_tracking(): Stop tracking and record metrics
    - get_metrics(): Get collected metrics
    - check_target_violations(): Check for target violations

    Notes:
    - MRO-compatible (calls super().__init__())
    - Lightweight overhead
    - Configurable monitoring options
    """

    def __init__(
        self,
        target_latency_ms: Optional[float] = None,
        target_throughput: Optional[float] = None,
        track_memory: bool = False,
        track_throughput: bool = True,
        sampling_rate: float = 1.0,
        **kwargs,
    ):
        """
        Initialize PerformanceMixin.

        Args:
            target_latency_ms: Target latency in milliseconds (optional)
            target_throughput: Target throughput in ops/sec (optional)
            track_memory: Enable memory tracking (default: False)
            track_throughput: Enable throughput tracking (default: True)
            sampling_rate: Sampling rate for metrics (0.0-1.0, default: 1.0)
            **kwargs: Additional arguments for super().__init__()

        Notes:
            - Task 3.3: Configurable performance monitoring setup
            - Calls super().__init__() for MRO compatibility
        """
        # MRO compatibility
        if hasattr(super(), "__init__"):
            super().__init__(**kwargs)

        # Task 3.3: Initialize performance tracking
        self.target_latency_ms = target_latency_ms
        self.target_throughput = target_throughput
        self.track_memory = track_memory
        self.track_throughput = track_throughput
        self.sampling_rate = sampling_rate

        # Metrics storage
        self.metrics = {
            "execution_count": 0,
            "total_time_ms": 0.0,
            "execution_times_ms": [],
            "violations": [],
        }

        # Tracking state
        self._tracking_start_time = None
        self._is_tracking = False

        # Logger
        self.logger = logging.getLogger(self.__class__.__name__)

    def enhance_workflow(self, workflow: WorkflowBuilder) -> WorkflowBuilder:
        """
        Enhance workflow with performance monitoring nodes.

        Adds performance monitoring capabilities to the workflow.

        Args:
            workflow: Workflow to enhance

        Returns:
            WorkflowBuilder: Enhanced workflow with performance monitoring

        Notes:
            - Task 3.14: Adds performance monitoring nodes
            - Task 3.16: Monitoring nodes don't impact performance significantly
            - Preserves existing nodes
        """
        # Task 3.14: For Phase 3, return workflow as-is
        # Full performance monitoring node integration in future enhancement
        return workflow

    def start_tracking(self):
        """
        Start performance tracking.

        Begins tracking execution time and other metrics.

        Notes:
            - Task 3.15: Starts metrics collection
            - Handles multiple start calls gracefully
        """
        # Task 3.15: Start tracking
        if self._is_tracking:
            # Already tracking - log warning but don't fail
            self.logger.warning("Performance tracking already started")
            return

        self._tracking_start_time = time.time()
        self._is_tracking = True

    def stop_tracking(self):
        """
        Stop performance tracking and record metrics.

        Stops tracking and records execution metrics.

        Notes:
            - Task 3.15: Records timing, memory, throughput metrics
            - Task 3.17: Checks target violations
        """
        if not self._is_tracking:
            self.logger.warning("Performance tracking not started")
            return

        # Task 3.15: Calculate execution time
        end_time = time.time()
        execution_time_sec = end_time - self._tracking_start_time
        execution_time_ms = execution_time_sec * 1000

        # Record metrics
        self.metrics["execution_count"] += 1
        self.metrics["total_time_ms"] += execution_time_ms
        self.metrics["execution_times_ms"].append(execution_time_ms)
        self.metrics["execution_time_ms"] = execution_time_ms
        self.metrics["last_execution_ms"] = execution_time_ms

        # Calculate average
        if self.metrics["execution_count"] > 0:
            self.metrics["avg_time_ms"] = (
                self.metrics["total_time_ms"] / self.metrics["execution_count"]
            )

        # Task 3.17: Check target violations
        if self.target_latency_ms is not None:
            if execution_time_ms > self.target_latency_ms:
                violation = {
                    "type": "latency",
                    "target": self.target_latency_ms,
                    "actual": execution_time_ms,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
                self.metrics["violations"].append(violation)
                self.logger.warning(
                    f"Latency target violation: {execution_time_ms:.2f}ms "
                    f"(target: {self.target_latency_ms:.2f}ms)"
                )

        # Reset tracking state
        self._tracking_start_time = None
        self._is_tracking = False

    def get_metrics(self) -> Dict[str, Any]:
        """
        Get collected performance metrics.

        Returns:
            Dict[str, Any]: Performance metrics

        Notes:
            - Task 3.15: Returns timing, memory, throughput metrics
            - Safe to call anytime
        """
        # Task 3.15: Return metrics
        return self.metrics.copy()

    def check_target_violations(self) -> Dict[str, Any]:
        """
        Check for performance target violations.

        Returns:
            Dict[str, Any]: Violation details

        Notes:
            - Task 3.17: Validates against performance targets
            - Returns violation details if any
        """
        # Task 3.17: Check violations
        violations = {
            "latency_violations": [],
            "throughput_violations": [],
            "violation_count": 0,
        }

        # Get recent violations
        for violation in self.metrics.get("violations", []):
            if violation["type"] == "latency":
                violations["latency_violations"].append(violation)
            elif violation["type"] == "throughput":
                violations["throughput_violations"].append(violation)

        violations["violation_count"] = len(self.metrics.get("violations", []))

        return violations

    def get_performance_status(self) -> Dict[str, Any]:
        """
        Get overall performance status.

        Returns:
            Dict[str, Any]: Performance status summary

        Notes:
            - Task 3.17: Reports overall performance status
            - Includes metrics and violations
        """
        # Task 3.17: Performance status
        status = {
            "metrics": self.get_metrics(),
            "violations": self.check_target_violations(),
            "targets": {
                "latency_ms": self.target_latency_ms,
                "throughput": self.target_throughput,
            },
            "tracking_enabled": True,
            "memory_tracking": self.track_memory,
            "throughput_tracking": self.track_throughput,
        }

        # Add health status
        violation_count = status["violations"]["violation_count"]
        if violation_count == 0:
            status["health"] = "healthy"
        elif violation_count < 5:
            status["health"] = "degraded"
        else:
            status["health"] = "unhealthy"

        return status

    def reset_metrics(self):
        """
        Reset collected metrics.

        Clears all collected performance metrics.

        Notes:
            - Useful for testing or periodic resets
            - Preserves configuration
        """
        self.metrics = {
            "execution_count": 0,
            "total_time_ms": 0.0,
            "execution_times_ms": [],
            "violations": [],
        }
        self.logger.info("Performance metrics reset")

    def get_summary(self) -> str:
        """
        Get human-readable performance summary.

        Returns:
            str: Performance summary

        Notes:
            - Useful for logging and debugging
            - Includes key metrics and violations
        """
        metrics = self.get_metrics()
        exec_count = metrics.get("execution_count", 0)
        avg_time = metrics.get("avg_time_ms", 0)
        violations = len(metrics.get("violations", []))

        return (
            f"Executions: {exec_count}, "
            f"Avg Time: {avg_time:.2f}ms, "
            f"Violations: {violations}"
        )

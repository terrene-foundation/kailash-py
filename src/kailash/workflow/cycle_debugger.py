"""
Comprehensive Debugging and Introspection for Cyclic Workflows.

This module provides extensive debugging and introspection capabilities for
cyclic workflows, enabling developers to understand cycle behavior, analyze
performance characteristics, and diagnose issues during both development and
production phases with detailed execution tracking and rich analytics.

Examples:
    Basic debugging setup:

    >>> debugger = CycleDebugger(
    ...     debug_level="detailed",
    ...     enable_profiling=True
    ... )
    >>> # Start cycle debugging
    >>> trace = debugger.start_cycle(
    ...     "optimization_cycle",
    ...     "workflow_1",
    ...     max_iterations=100
    ... )

    Iteration tracking:

    >>> # Track each iteration
    >>> iteration = debugger.start_iteration(trace, input_data)
    >>> # ... cycle execution ...
    >>> debugger.end_iteration(
    ...     trace, iteration, output_data,
    ...     convergence_value=0.05,
    ...     node_executions=["processor", "evaluator"]
    ... )

    Analysis and reporting:

    >>> # Complete cycle
    >>> debugger.end_cycle(
    ...     trace, converged=True,
    ...     termination_reason="convergence",
    ...     convergence_iteration=15
    ... )
    >>> # Generate comprehensive report
    >>> report = debugger.generate_report(trace)
    >>> # Export for external analysis
    >>> debugger.export_trace(trace, "debug_output.json", "json")
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class CycleIteration:
    """
    Represents a single iteration within a cycle execution.

    This class captures all relevant information about a cycle iteration,
    including input/output data, execution time, memory usage, and any
    errors that occurred during execution.

    Attributes:
        iteration_number: The iteration count (starting from 1).
        start_time: When this iteration began execution.
        end_time: When this iteration completed.
        execution_time: Duration in seconds.
        input_data: Input data for this iteration.
        output_data: Output data from this iteration.
        memory_usage_mb: Memory usage in megabytes.
        cpu_usage_percent: CPU usage percentage.
        convergence_value: Convergence metric if available.
        error: Error message if iteration failed.
        node_executions: List of nodes executed in this iteration.
    """

    iteration_number: int
    start_time: datetime
    end_time: datetime | None = None
    execution_time: float | None = None
    input_data: dict[str, Any] = field(default_factory=dict)
    output_data: dict[str, Any] | None = None
    memory_usage_mb: float | None = None
    cpu_usage_percent: float | None = None
    convergence_value: float | None = None
    error: str | None = None
    node_executions: list[str] = field(default_factory=list)

    def complete(
        self, output_data: dict[str, Any], convergence_value: float | None = None
    ):
        """
        Mark iteration as complete with output data.

        Args:
            output_data: The output data from this iteration.
            convergence_value: Convergence metric if available.
        """
        self.end_time = datetime.now()
        self.execution_time = (self.end_time - self.start_time).total_seconds()
        self.output_data = output_data
        self.convergence_value = convergence_value

    def fail(self, error: str):
        """
        Mark iteration as failed with error message.

        Args:
            error: Error message describing the failure.
        """
        self.end_time = datetime.now()
        self.execution_time = (self.end_time - self.start_time).total_seconds()
        self.error = error

    def is_completed(self) -> bool:
        """Check if iteration has completed (successfully or with error).

        Returns:
            True if iteration has completed.
        """
        return self.end_time is not None

    def is_successful(self) -> bool:
        """Check if iteration completed successfully.

        Returns:
            True if iteration completed without error.
        """
        return self.end_time is not None and self.error is None

    def to_dict(self) -> dict[str, Any]:
        """Convert iteration to dictionary for serialization.

        Returns:
            Dictionary representation of the iteration.
        """
        return {
            "iteration_number": self.iteration_number,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "execution_time": self.execution_time,
            "memory_usage_mb": self.memory_usage_mb,
            "cpu_usage_percent": self.cpu_usage_percent,
            "convergence_value": self.convergence_value,
            "error": self.error,
            "node_executions": self.node_executions,
            "input_size": len(str(self.input_data)) if self.input_data else 0,
            "output_size": len(str(self.output_data)) if self.output_data else 0,
        }


@dataclass
class CycleExecutionTrace:
    """
    Complete execution trace for a cycle, containing all iterations and metadata.

    This class provides a comprehensive record of cycle execution, including
    all iterations, overall statistics, convergence analysis, and performance
    metrics. It serves as the primary data structure for cycle debugging.

    Attributes:
        cycle_id: Unique identifier for the cycle.
        workflow_id: Parent workflow identifier.
        start_time: When cycle execution began.
        end_time: When cycle execution completed.
        total_execution_time: Total duration in seconds.
        iterations: All iterations executed.
        converged: Whether cycle converged successfully.
        convergence_iteration: Iteration where convergence occurred.
        termination_reason: Why the cycle terminated.
        max_iterations_configured: Configured iteration limit.
        timeout_configured: Configured timeout limit.
        convergence_condition: Configured convergence condition.
    """

    cycle_id: str
    workflow_id: str
    start_time: datetime
    end_time: datetime | None = None
    total_execution_time: float | None = None
    iterations: list[CycleIteration] = field(default_factory=list)
    converged: bool = False
    convergence_iteration: int | None = None
    termination_reason: str = "unknown"
    max_iterations_configured: int | None = None
    timeout_configured: float | None = None
    convergence_condition: str | None = None
    memory_peak_mb: float | None = None
    cpu_peak_percent: float | None = None

    def add_iteration(self, iteration: CycleIteration):
        """
        Add an iteration to the trace.

        Args:
            iteration: The iteration to add.
        """
        self.iterations.append(iteration)

        # Update peak metrics
        if iteration.memory_usage_mb and (
            not self.memory_peak_mb or iteration.memory_usage_mb > self.memory_peak_mb
        ):
            self.memory_peak_mb = iteration.memory_usage_mb

        if iteration.cpu_usage_percent and (
            not self.cpu_peak_percent
            or iteration.cpu_usage_percent > self.cpu_peak_percent
        ):
            self.cpu_peak_percent = iteration.cpu_usage_percent

    def complete(
        self,
        converged: bool,
        termination_reason: str,
        convergence_iteration: int | None = None,
    ):
        """
        Mark cycle execution as complete.

        Args:
            converged: Whether the cycle converged successfully.
            termination_reason: Why the cycle terminated.
            convergence_iteration: Iteration where convergence occurred.
        """
        self.end_time = datetime.now()
        self.total_execution_time = (self.end_time - self.start_time).total_seconds()
        self.converged = converged
        self.termination_reason = termination_reason
        self.convergence_iteration = convergence_iteration

    def get_statistics(self) -> dict[str, Any]:
        """
        Get comprehensive statistics about the cycle execution.

        Returns:
            Statistics including timing, convergence, and performance metrics.

        Examples:
            >>> stats = trace.get_statistics()
            >>> print(f"Average iteration time: {stats['avg_iteration_time']:.3f}s")
        """
        if not self.iterations:
            return {
                "total_iterations": 0,
                "avg_iteration_time": 0.0,
                "min_iteration_time": 0.0,
                "max_iteration_time": 0.0,
                "convergence_rate": 0.0,
                "efficiency_score": 0.0,
            }

        # Calculate timing statistics
        iteration_times = [
            iter.execution_time
            for iter in self.iterations
            if iter.execution_time is not None
        ]

        stats = {
            "total_iterations": len(self.iterations),
            "successful_iterations": len(
                [iter for iter in self.iterations if iter.is_successful()]
            ),
            "failed_iterations": len(
                [iter for iter in self.iterations if iter.error is not None]
            ),
            "avg_iteration_time": (
                sum(iteration_times) / len(iteration_times) if iteration_times else 0.0
            ),
            "min_iteration_time": min(iteration_times) if iteration_times else 0.0,
            "max_iteration_time": max(iteration_times) if iteration_times else 0.0,
            "total_execution_time": self.total_execution_time or 0.0,
            "converged": self.converged,
            "convergence_iteration": self.convergence_iteration,
            "termination_reason": self.termination_reason,
            "memory_peak_mb": self.memory_peak_mb,
            "cpu_peak_percent": self.cpu_peak_percent,
        }

        # Calculate convergence rate (how quickly it converged relative to max_iterations)
        if (
            self.converged
            and self.convergence_iteration
            and self.max_iterations_configured
        ):
            stats["convergence_rate"] = (
                self.convergence_iteration / self.max_iterations_configured
            )
        else:
            stats["convergence_rate"] = 1.0 if self.converged else 0.0

        # Calculate efficiency score (0-1, higher is better)
        if self.max_iterations_configured and len(self.iterations) > 0:
            iteration_efficiency = 1.0 - (
                len(self.iterations) / self.max_iterations_configured
            )
            time_efficiency = (
                1.0
                if not self.timeout_configured
                else max(
                    0.0,
                    1.0 - (self.total_execution_time or 0) / self.timeout_configured,
                )
            )
            convergence_bonus = 0.2 if self.converged else 0.0
            stats["efficiency_score"] = min(
                1.0,
                iteration_efficiency * 0.5 + time_efficiency * 0.3 + convergence_bonus,
            )
        else:
            stats["efficiency_score"] = 0.5 if self.converged else 0.0

        return stats

    def get_convergence_trend(self) -> list[tuple[int, float | None]]:
        """
        Get convergence values over iterations for trend analysis.

        Returns:
            List[Tuple[int, Optional[float]]]: List of (iteration_number, convergence_value) pairs

        Side Effects:
            None - this is a pure calculation method

        Example:
            >>> trend = trace.get_convergence_trend()
            >>> for iteration, value in trend:
            ...     print(f"Iteration {iteration}: {value}")
        """
        return [
            (iter.iteration_number, iter.convergence_value) for iter in self.iterations
        ]

    def to_dict(self) -> dict[str, Any]:
        """Convert trace to dictionary for serialization."""
        return {
            "cycle_id": self.cycle_id,
            "workflow_id": self.workflow_id,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "total_execution_time": self.total_execution_time,
            "iterations": [iter.to_dict() for iter in self.iterations],
            "converged": self.converged,
            "convergence_iteration": self.convergence_iteration,
            "termination_reason": self.termination_reason,
            "max_iterations_configured": self.max_iterations_configured,
            "timeout_configured": self.timeout_configured,
            "convergence_condition": self.convergence_condition,
            "memory_peak_mb": self.memory_peak_mb,
            "cpu_peak_percent": self.cpu_peak_percent,
            "statistics": self.get_statistics(),
        }


class CycleDebugger:
    """
    Comprehensive debugging tool for cyclic workflow execution.

    This class provides real-time debugging capabilities for cycles, including
    iteration tracking, performance monitoring, convergence analysis, and
    detailed execution tracing. It integrates with the cycle execution system
    to provide insights into cycle behavior and performance.

    Design Philosophy:
        Provides non-intrusive debugging that doesn't affect cycle performance
        in production. Offers multiple levels of debugging detail from basic
        tracking to comprehensive profiling with rich analytics.

    Upstream Dependencies:
        - Used by CyclicWorkflowExecutor when debug mode is enabled
        - Integrates with cycle configuration and execution systems

    Downstream Consumers:
        - Debug reports and analysis tools
        - Performance optimization recommendations
        - Cycle visualization and monitoring dashboards

    Usage Patterns:
        1. Real-time debugging during development
        2. Performance profiling for optimization
        3. Production monitoring for cycle health
        4. Post-execution analysis for troubleshooting

    Example:
        >>> debugger = CycleDebugger(debug_level="detailed")
        >>> trace = debugger.start_cycle("optimization", "workflow_1")
        >>>
        >>> # During cycle execution
        >>> iteration = debugger.start_iteration(trace, input_data)
        >>> debugger.end_iteration(iteration, output_data)
        >>>
        >>> # After cycle completion
        >>> debugger.end_cycle(trace, converged=True, reason="convergence")
        >>> report = debugger.generate_report(trace)
    """

    def __init__(self, debug_level: str = "basic", enable_profiling: bool = False):
        """
        Initialize cycle debugger.

        Args:
            debug_level (str): Level of debugging detail ("basic", "detailed", "verbose")
            enable_profiling (bool): Whether to enable detailed profiling

        Side Effects:
            Configures logging and profiling settings
        """
        self.debug_level = debug_level
        self.enable_profiling = enable_profiling
        self.active_traces: dict[str, CycleExecutionTrace] = {}

        # Configure logging based on debug level
        if debug_level == "verbose":
            logger.setLevel(logging.DEBUG)
        elif debug_level == "detailed":
            logger.setLevel(logging.INFO)
        else:
            logger.setLevel(logging.WARNING)

    def start_cycle(
        self,
        cycle_id: str,
        workflow_id: str,
        max_iterations: int | None = None,
        timeout: float | None = None,
        convergence_condition: str | None = None,
    ) -> CycleExecutionTrace:
        """
        Start debugging a new cycle execution.

        Creates a new execution trace and begins tracking cycle execution
        with all configured debugging features enabled.

        Args:
            cycle_id (str): Unique identifier for the cycle
            workflow_id (str): Parent workflow identifier
            max_iterations (Optional[int]): Configured iteration limit
            timeout (Optional[float]): Configured timeout limit
            convergence_condition (Optional[str]): Convergence condition expression

        Returns:
            CycleExecutionTrace: New trace object for tracking execution

        Side Effects:
            Creates new trace and adds to active_traces
            Logs cycle start event

        Example:
            >>> trace = debugger.start_cycle("opt_cycle", "workflow_1", max_iterations=100)
        """
        trace = CycleExecutionTrace(
            cycle_id=cycle_id,
            workflow_id=workflow_id,
            start_time=datetime.now(),
            max_iterations_configured=max_iterations,
            timeout_configured=timeout,
            convergence_condition=convergence_condition,
        )

        self.active_traces[cycle_id] = trace

        logger.info(
            f"Started debugging cycle '{cycle_id}' in workflow '{workflow_id}' "
            f"with max_iterations={max_iterations}, timeout={timeout}"
        )

        return trace

    def start_iteration(
        self,
        trace: CycleExecutionTrace,
        input_data: dict[str, Any],
        iteration_number: int | None = None,
    ) -> CycleIteration:
        """
        Start debugging a new cycle iteration.

        Creates a new iteration object and begins tracking execution time,
        resource usage, and other iteration-specific metrics.

        Args:
            trace (CycleExecutionTrace): Parent cycle trace
            input_data (Dict[str, Any]): Input data for this iteration
            iteration_number (Optional[int]): Iteration number (auto-calculated if None)

        Returns:
            CycleIteration: New iteration object for tracking

        Side Effects:
            Creates new iteration and adds to trace
            Begins resource monitoring if profiling enabled

        Example:
            >>> iteration = debugger.start_iteration(trace, {"value": 10})
        """
        if iteration_number is None:
            iteration_number = len(trace.iterations) + 1

        iteration = CycleIteration(
            iteration_number=iteration_number,
            start_time=datetime.now(),
            input_data=(
                input_data.copy() if self.debug_level in ["detailed", "verbose"] else {}
            ),
        )

        # Add profiling data if enabled
        if self.enable_profiling:
            try:
                import psutil

                process = psutil.Process()
                iteration.memory_usage_mb = process.memory_info().rss / 1024 / 1024
                iteration.cpu_usage_percent = process.cpu_percent()
            except ImportError:
                logger.warning(
                    "psutil not available for profiling. Install with: pip install psutil"
                )

        if self.debug_level == "verbose":
            logger.debug(
                f"Started iteration {iteration_number} for cycle '{trace.cycle_id}' "
                f"with input keys: {list(input_data.keys())}"
            )

        return iteration

    def end_iteration(
        self,
        trace: CycleExecutionTrace,
        iteration: CycleIteration,
        output_data: dict[str, Any],
        convergence_value: float | None = None,
        node_executions: list[str] | None = None,
    ):
        """
        Complete iteration tracking with output data and metrics.

        Finalizes iteration tracking by recording output data, convergence
        metrics, and final resource usage measurements.

        Args:
            trace (CycleExecutionTrace): Parent cycle trace
            iteration (CycleIteration): Iteration object to complete
            output_data (Dict[str, Any]): Output data from iteration
            convergence_value (Optional[float]): Convergence metric if available
            node_executions (Optional[List[str]]): List of executed nodes

        Side Effects:
            Completes iteration and adds to trace
            Updates peak resource usage in trace
            Logs iteration completion

        Example:
            >>> debugger.end_iteration(trace, iteration, {"result": 20}, convergence_value=0.05)
        """
        iteration.complete(
            output_data.copy() if self.debug_level in ["detailed", "verbose"] else {},
            convergence_value,
        )

        if node_executions:
            iteration.node_executions = node_executions

        # Update profiling data if enabled
        if self.enable_profiling:
            try:
                import psutil

                process = psutil.Process()
                end_memory = process.memory_info().rss / 1024 / 1024
                end_cpu = process.cpu_percent()

                # Use the higher value for this iteration
                iteration.memory_usage_mb = max(
                    iteration.memory_usage_mb or 0, end_memory
                )
                iteration.cpu_usage_percent = max(
                    iteration.cpu_usage_percent or 0, end_cpu
                )
            except ImportError:
                pass  # Already warned during start_iteration

        trace.add_iteration(iteration)

        if self.debug_level in ["detailed", "verbose"]:
            logger.info(
                f"Completed iteration {iteration.iteration_number} for cycle '{trace.cycle_id}' "
                f"in {iteration.execution_time:.3f}s, convergence={convergence_value}"
            )

    def end_cycle(
        self,
        trace: CycleExecutionTrace,
        converged: bool,
        termination_reason: str,
        convergence_iteration: int | None = None,
    ):
        """
        Complete cycle tracking with final results and analysis.

        Finalizes cycle execution tracking and generates comprehensive
        statistics and analysis for the complete cycle execution.

        Args:
            trace (CycleExecutionTrace): Cycle trace to complete
            converged (bool): Whether the cycle converged successfully
            termination_reason (str): Why the cycle terminated
            convergence_iteration (Optional[int]): Iteration where convergence occurred

        Side Effects:
            Completes trace and removes from active_traces
            Logs cycle completion with statistics

        Example:
            >>> debugger.end_cycle(trace, converged=True, termination_reason="convergence", convergence_iteration=15)
        """
        trace.complete(converged, termination_reason, convergence_iteration)

        # Remove from active traces
        if trace.cycle_id in self.active_traces:
            del self.active_traces[trace.cycle_id]

        stats = trace.get_statistics()
        logger.info(
            f"Completed cycle '{trace.cycle_id}' in {trace.total_execution_time:.3f}s "
            f"with {stats['total_iterations']} iterations, "
            f"converged={converged}, efficiency={stats['efficiency_score']:.2f}"
        )

    def generate_report(self, trace: CycleExecutionTrace) -> dict[str, Any]:
        """
        Generate comprehensive debugging report for a cycle execution.

        Creates a detailed report including execution statistics, performance
        analysis, convergence trends, and optimization recommendations based
        on the complete cycle execution trace.

        Args:
            trace (CycleExecutionTrace): Completed cycle trace to analyze

        Returns:
            Dict[str, Any]: Comprehensive debugging report

        Side Effects:
            None - this is a pure analysis method

        Example:
            >>> report = debugger.generate_report(trace)
            >>> print(f"Efficiency score: {report['performance']['efficiency_score']}")
        """
        stats = trace.get_statistics()
        convergence_trend = trace.get_convergence_trend()

        # Analyze convergence pattern
        convergence_analysis = self._analyze_convergence(convergence_trend)

        # Generate optimization recommendations
        recommendations = self._generate_recommendations(trace, stats)

        # Create performance summary
        performance = {
            "efficiency_score": stats["efficiency_score"],
            "avg_iteration_time": stats["avg_iteration_time"],
            "convergence_rate": stats["convergence_rate"],
            "resource_usage": {
                "memory_peak_mb": trace.memory_peak_mb,
                "cpu_peak_percent": trace.cpu_peak_percent,
            },
        }

        report = {
            "cycle_info": {
                "cycle_id": trace.cycle_id,
                "workflow_id": trace.workflow_id,
                "execution_time": trace.total_execution_time,
                "converged": trace.converged,
                "termination_reason": trace.termination_reason,
            },
            "statistics": stats,
            "performance": performance,
            "convergence_analysis": convergence_analysis,
            "recommendations": recommendations,
            "trace_data": trace.to_dict() if self.debug_level == "verbose" else None,
        }

        return report

    def _analyze_convergence(
        self, convergence_trend: list[tuple[int, float | None]]
    ) -> dict[str, Any]:
        """Analyze convergence pattern from trend data."""
        if not convergence_trend or all(
            value is None for _, value in convergence_trend
        ):
            return {"pattern": "no_data", "analysis": "No convergence data available"}

        # Filter out None values
        valid_points = [
            (iter_num, value)
            for iter_num, value in convergence_trend
            if value is not None
        ]

        if len(valid_points) < 2:
            return {
                "pattern": "insufficient_data",
                "analysis": "Insufficient convergence data for analysis",
            }

        # Analyze trend
        values = [value for _, value in valid_points]

        # Check for improvement pattern
        if len(values) >= 3:
            improving_count = sum(
                1 for i in range(1, len(values)) if values[i] < values[i - 1]
            )
            improvement_ratio = improving_count / (len(values) - 1)

            if improvement_ratio > 0.8:
                pattern = "steady_improvement"
                analysis = "Convergence is steadily improving"
            elif improvement_ratio > 0.5:
                pattern = "gradual_improvement"
                analysis = "Convergence is gradually improving with some fluctuation"
            elif improvement_ratio < 0.2:
                pattern = "plateau"
                analysis = "Convergence has plateaued - may need different approach"
            else:
                pattern = "unstable"
                analysis = "Convergence is unstable - check algorithm parameters"
        else:
            pattern = "limited_data"
            analysis = "Limited data for pattern analysis"

        return {
            "pattern": pattern,
            "analysis": analysis,
            "initial_value": values[0] if values else None,
            "final_value": values[-1] if values else None,
            "improvement": values[0] - values[-1] if len(values) >= 2 else None,
            "data_points": len(valid_points),
        }

    def _generate_recommendations(
        self, trace: CycleExecutionTrace, stats: dict[str, Any]
    ) -> list[str]:
        """Generate optimization recommendations based on execution analysis."""
        recommendations = []

        # Efficiency recommendations
        if stats["efficiency_score"] < 0.5:
            recommendations.append(
                "Consider reducing max_iterations or improving convergence condition"
            )

        # Convergence recommendations
        if not trace.converged:
            if stats["total_iterations"] >= (trace.max_iterations_configured or 0):
                recommendations.append(
                    "Cycle reached max_iterations without converging - increase limit or improve algorithm"
                )
            else:
                recommendations.append(
                    "Cycle terminated early - check for errors or timeout issues"
                )

        # Performance recommendations
        if stats["avg_iteration_time"] > 1.0:
            recommendations.append(
                "Average iteration time is high - consider optimizing node performance"
            )

        if trace.memory_peak_mb and trace.memory_peak_mb > 1000:
            recommendations.append(
                "High memory usage detected - consider data streaming or chunking"
            )

        # Convergence pattern recommendations
        convergence_trend = trace.get_convergence_trend()
        convergence_analysis = self._analyze_convergence(convergence_trend)

        if convergence_analysis["pattern"] == "plateau":
            recommendations.append(
                "Convergence plateaued - try different learning rate or algorithm parameters"
            )
        elif convergence_analysis["pattern"] == "unstable":
            recommendations.append(
                "Unstable convergence - reduce learning rate or add regularization"
            )

        # Success recommendations
        if trace.converged and stats["efficiency_score"] > 0.8:
            recommendations.append(
                "Excellent cycle performance - consider using as template for similar workflows"
            )

        return recommendations

    def export_trace(
        self, trace: CycleExecutionTrace, filepath: str, format: str = "json"
    ):
        """
        Export cycle trace to file for external analysis.

        Args:
            trace (CycleExecutionTrace): Trace to export
            filepath (str): Output file path
            format (str): Export format ("json", "csv")

        Side Effects:
            Creates file at specified path with trace data

        Example:
            >>> debugger.export_trace(trace, "cycle_debug.json", "json")
        """
        trace_data = trace.to_dict()

        if format == "json":
            with open(filepath, "w") as f:
                json.dump(trace_data, f, indent=2)
        elif format == "csv":
            import csv

            with open(filepath, "w", newline="") as f:
                writer = csv.writer(f)

                # Write header
                writer.writerow(
                    [
                        "iteration",
                        "execution_time",
                        "memory_mb",
                        "cpu_percent",
                        "convergence",
                        "error",
                    ]
                )

                # Write iteration data
                for iteration in trace.iterations:
                    writer.writerow(
                        [
                            iteration.iteration_number,
                            iteration.execution_time,
                            iteration.memory_usage_mb,
                            iteration.cpu_usage_percent,
                            iteration.convergence_value,
                            iteration.error or "",
                        ]
                    )
        else:
            raise ValueError(f"Unsupported export format: {format}")

        logger.info(f"Exported cycle trace to {filepath} in {format} format")

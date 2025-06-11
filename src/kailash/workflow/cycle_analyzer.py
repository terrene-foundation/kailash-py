"""
Cycle Analysis and Performance Monitoring for Cyclic Workflows.

This module provides comprehensive analysis tools that combine debugging and
profiling capabilities to deliver deep insights into cycle behavior, performance
characteristics, and optimization opportunities. It serves as the primary
analysis interface for understanding and improving cyclic workflow execution.

Examples:
    Comprehensive cycle analysis:

    >>> analyzer = CycleAnalyzer(
    ...     analysis_level="comprehensive",
    ...     output_directory="./analysis_results"
    ... )
    >>> # Start analysis session
    >>> session = analyzer.start_analysis_session("optimization_study")
    >>> # Analyze cycle execution
    >>> trace = analyzer.start_cycle_analysis("opt_cycle", "workflow_1")
    >>> analyzer.track_iteration(trace, input_data, output_data, 0.05)
    >>> analyzer.complete_cycle_analysis(trace, True, "convergence")
    >>> # Generate comprehensive report
    >>> report = analyzer.generate_session_report()
    >>> analyzer.export_analysis_data("analysis_results.json")

    Real-time monitoring:

    >>> # Monitor active cycle
    >>> metrics = analyzer.get_real_time_metrics(trace)
    >>> if metrics['health_score'] < 0.5:
    ...     print("Performance issue detected!")
    ...     print(f"Alerts: {metrics['alerts']}")
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from kailash.workflow.cycle_debugger import CycleDebugger, CycleExecutionTrace
from kailash.workflow.cycle_profiler import CycleProfiler

logger = logging.getLogger(__name__)


class CycleAnalyzer:
    """
    Comprehensive analysis tool combining debugging and profiling capabilities.

    This class provides a unified interface for cycle analysis, combining
    the detailed tracking capabilities of CycleDebugger with the performance
    insights of CycleProfiler to provide comprehensive cycle optimization
    guidance and health monitoring.

    Examples:
        >>> analyzer = CycleAnalyzer(analysis_level="comprehensive")
        >>> # Start analysis
        >>> session = analyzer.start_analysis_session("optimization_study")
        >>> trace = analyzer.start_cycle_analysis("cycle_1", "workflow_1")
        >>> # During execution...
        >>> analyzer.track_iteration(trace, input_data, output_data)
        >>> # Complete analysis
        >>> analyzer.complete_cycle_analysis(trace, converged=True)
        >>> report = analyzer.generate_comprehensive_report(session)
    """

    def __init__(
        self,
        analysis_level: str = "standard",
        enable_profiling: bool = True,
        enable_debugging: bool = True,
        output_directory: str | None = None,
    ):
        """
        Initialize cycle analyzer.

        Args:
            analysis_level: Level of analysis ("basic", "standard", "comprehensive").
            enable_profiling: Whether to enable performance profiling.
            enable_debugging: Whether to enable detailed debugging.
            output_directory: Directory for analysis output files.
        """
        self.analysis_level = analysis_level
        self.enable_profiling = enable_profiling
        self.enable_debugging = enable_debugging

        # Set output directory - use centralized location if not specified
        if output_directory:
            self.output_directory = Path(output_directory)
        else:
            # Use centralized output directory by default
            project_root = Path(__file__).parent.parent.parent.parent
            self.output_directory = project_root / "data" / "outputs" / "cycle_analysis"

        # Initialize components based on configuration
        debug_level = {
            "basic": "basic",
            "standard": "detailed",
            "comprehensive": "verbose",
        }.get(analysis_level, "detailed")

        self.debugger = (
            CycleDebugger(debug_level=debug_level, enable_profiling=enable_profiling)
            if enable_debugging
            else None
        )

        self.profiler = (
            CycleProfiler(enable_advanced_metrics=(analysis_level == "comprehensive"))
            if enable_profiling
            else None
        )

        # Analysis session tracking
        self.current_session: str | None = None
        self.session_traces: list[CycleExecutionTrace] = []
        self.analysis_history: list[dict[str, Any]] = []

        # Create output directory if specified
        if self.output_directory:
            self.output_directory.mkdir(parents=True, exist_ok=True)
            logger.info(f"Analysis output directory: {self.output_directory}")

    def start_analysis_session(self, session_id: str) -> str:
        """
        Start a new analysis session for grouping related cycles.

        Analysis sessions allow grouping multiple cycle executions for
        comparative analysis, trend identification, and comprehensive
        reporting across related workflow executions.

        Args:
            session_id: Unique identifier for the analysis session.

        Returns:
            Session ID for reference.

        Examples:
            >>> session = analyzer.start_analysis_session("optimization_experiment_1")
        """
        self.current_session = session_id
        self.session_traces = []

        logger.info(f"Started analysis session: {session_id}")
        return session_id

    def start_cycle_analysis(
        self,
        cycle_id: str,
        workflow_id: str,
        max_iterations: int | None = None,
        timeout: float | None = None,
        convergence_condition: str | None = None,
    ) -> CycleExecutionTrace | None:
        """
        Start analysis for a new cycle execution.

        Begins comprehensive tracking for a cycle execution, including
        debugging and profiling as configured. Returns a trace object
        for tracking iteration progress.

        Args:
            cycle_id: Unique identifier for the cycle.
            workflow_id: Parent workflow identifier.
            max_iterations: Configured iteration limit.
            timeout: Configured timeout limit.
            convergence_condition: Convergence condition.

        Returns:
            Trace object for tracking, or None if debugging disabled.

        Examples:
            >>> trace = analyzer.start_cycle_analysis("opt_cycle", "workflow_1", max_iterations=100)
        """
        if not self.debugger:
            logger.warning("Debugging not enabled - cannot create trace")
            return None

        trace = self.debugger.start_cycle(
            cycle_id=cycle_id,
            workflow_id=workflow_id,
            max_iterations=max_iterations,
            timeout=timeout,
            convergence_condition=convergence_condition,
        )

        logger.info(
            f"Started cycle analysis for '{cycle_id}' in session '{self.current_session}'"
        )
        return trace

    def track_iteration(
        self,
        trace: CycleExecutionTrace,
        input_data: dict[str, Any],
        output_data: dict[str, Any],
        convergence_value: float | None = None,
        node_executions: list[str] | None = None,
    ):
        """
        Track a single cycle iteration with input/output data.

        Records detailed information about a cycle iteration including
        timing, resource usage, convergence metrics, and execution flow
        for comprehensive analysis.

        Args:
            trace: Active trace object.
            input_data: Input data for the iteration.
            output_data: Output data from the iteration.
            convergence_value: Convergence metric if available.
            node_executions: List of executed nodes.

        Examples:
            >>> analyzer.track_iteration(trace, input_data, output_data, convergence_value=0.05)
        """
        if not self.debugger:
            return

        iteration = self.debugger.start_iteration(trace, input_data)
        self.debugger.end_iteration(
            trace, iteration, output_data, convergence_value, node_executions
        )

        if self.analysis_level == "comprehensive":
            logger.debug(
                f"Tracked iteration {iteration.iteration_number} for cycle '{trace.cycle_id}' "
                f"with convergence={convergence_value}"
            )

    def complete_cycle_analysis(
        self,
        trace: CycleExecutionTrace,
        converged: bool,
        termination_reason: str,
        convergence_iteration: int | None = None,
    ):
        """
        Complete cycle analysis and generate insights.

        Finalizes cycle tracking and performs comprehensive analysis
        including performance metrics, optimization recommendations,
        and comparative insights if multiple cycles are available.

        Args:
            trace: Cycle trace to complete.
            converged: Whether the cycle converged successfully.
            termination_reason: Why the cycle terminated.
            convergence_iteration: Iteration where convergence occurred.

        Examples:
            >>> analyzer.complete_cycle_analysis(trace, converged=True, termination_reason="convergence")
        """
        if not self.debugger:
            return

        # Complete debugging
        self.debugger.end_cycle(
            trace, converged, termination_reason, convergence_iteration
        )

        # Add to profiler for performance analysis
        if self.profiler:
            self.profiler.add_trace(trace)

        # Add to session traces
        self.session_traces.append(trace)

        logger.info(
            f"Completed cycle analysis for '{trace.cycle_id}' - "
            f"converged={converged}, iterations={len(trace.iterations)}"
        )

        # Generate immediate insights for comprehensive analysis
        if self.analysis_level == "comprehensive":
            self._generate_immediate_insights(trace)

    def generate_cycle_report(self, trace: CycleExecutionTrace) -> dict[str, Any]:
        """
        Generate comprehensive report for a single cycle.

        Creates a detailed analysis report for a specific cycle execution
        including debugging information, performance metrics, and
        optimization recommendations.

        Args:
            trace: Completed cycle trace.

        Returns:
            Comprehensive cycle analysis report.

        Examples:
            >>> report = analyzer.generate_cycle_report(trace)
            >>> print(f"Cycle efficiency: {report['performance']['efficiency_score']}")
        """
        report = {
            "analysis_info": {
                "cycle_id": trace.cycle_id,
                "workflow_id": trace.workflow_id,
                "analysis_level": self.analysis_level,
                "session_id": self.current_session,
                "generated_at": datetime.now().isoformat(),
            }
        }

        # Add debugging information
        if self.debugger:
            debug_report = self.debugger.generate_report(trace)
            report["debugging"] = debug_report

        # Add profiling information
        if self.profiler:
            # Create temporary profiler for single trace analysis
            single_profiler = CycleProfiler(
                enable_advanced_metrics=(self.analysis_level == "comprehensive")
            )
            single_profiler.add_trace(trace)

            performance_metrics = single_profiler.analyze_performance()
            recommendations = single_profiler.get_optimization_recommendations(trace)

            report["performance"] = performance_metrics.to_dict()
            report["recommendations"] = recommendations

        # Add analysis-level specific insights
        if self.analysis_level == "comprehensive":
            report["advanced_analysis"] = self._generate_advanced_analysis(trace)

        # Export to file if configured
        if self.output_directory:
            self._export_cycle_report(report, trace.cycle_id)

        return report

    def generate_session_report(self, session_id: str | None = None) -> dict[str, Any]:
        """
        Generate comprehensive report for an analysis session.

        Creates a detailed analysis report covering all cycles in a session,
        including comparative analysis, trend identification, and overall
        optimization recommendations.

        Args:
            session_id: Session to analyze, or current session if None.

        Returns:
            Comprehensive session analysis report.

        Examples:
            >>> report = analyzer.generate_session_report()
            >>> print(f"Best cycle: {report['comparative_analysis']['best_cycle']}")
        """
        target_session = session_id or self.current_session
        traces_to_analyze = self.session_traces if session_id is None else []

        report = {
            "session_info": {
                "session_id": target_session,
                "analysis_level": self.analysis_level,
                "cycles_analyzed": len(traces_to_analyze),
                "generated_at": datetime.now().isoformat(),
            },
            "summary": {
                "total_cycles": len(traces_to_analyze),
                "total_iterations": sum(
                    len(trace.iterations) for trace in traces_to_analyze
                ),
                "convergence_rate": (
                    len([t for t in traces_to_analyze if t.converged])
                    / len(traces_to_analyze)
                    if traces_to_analyze
                    else 0
                ),
                "avg_cycle_time": (
                    sum(t.total_execution_time or 0 for t in traces_to_analyze)
                    / len(traces_to_analyze)
                    if traces_to_analyze
                    else 0
                ),
            },
        }

        if not traces_to_analyze:
            report["warning"] = "No traces available for analysis"
            return report

        # Add profiling analysis
        if self.profiler and traces_to_analyze:
            # Ensure all traces are in profiler
            for trace in traces_to_analyze:
                if trace not in self.profiler.traces:
                    self.profiler.add_trace(trace)

            performance_report = self.profiler.generate_performance_report()
            report["performance_analysis"] = performance_report

        # Add comparative analysis
        if len(traces_to_analyze) >= 2:
            cycle_ids = [trace.cycle_id for trace in traces_to_analyze]
            comparison = (
                self.profiler.compare_cycles(cycle_ids) if self.profiler else {}
            )
            report["comparative_analysis"] = comparison

        # Add session-specific insights
        report["insights"] = self._generate_session_insights(traces_to_analyze)

        # Export to file if configured
        if self.output_directory:
            self._export_session_report(report, target_session)

        return report

    def get_real_time_metrics(self, trace: CycleExecutionTrace) -> dict[str, Any]:
        """
        Get real-time metrics for an active cycle.

        Provides current performance metrics and health indicators
        for a cycle that is currently executing, enabling real-time
        monitoring and early intervention if issues are detected.

        Args:
            trace: Active cycle trace.

        Returns:
            Dict[str, Any]: Real-time metrics and health indicators

        Side Effects:
            None - this is a pure analysis method

        Example:
            >>> metrics = analyzer.get_real_time_metrics(trace)
            >>> if metrics['health_score'] < 0.5:
            ...     print("Cycle performance issue detected!")
        """
        if not trace.iterations:
            return {"status": "no_iterations", "health_score": 0.5}

        recent_iterations = trace.iterations[-5:]  # Last 5 iterations

        # Calculate real-time performance indicators
        avg_recent_time = sum(
            iter.execution_time or 0 for iter in recent_iterations
        ) / len(recent_iterations)

        # Memory trend (if available)
        memory_values = [
            iter.memory_usage_mb for iter in recent_iterations if iter.memory_usage_mb
        ]
        memory_trend = "stable"
        if len(memory_values) >= 2:
            if memory_values[-1] > memory_values[0] * 1.2:
                memory_trend = "increasing"
            elif memory_values[-1] < memory_values[0] * 0.8:
                memory_trend = "decreasing"

        # Convergence trend
        convergence_values = [
            iter.convergence_value
            for iter in recent_iterations
            if iter.convergence_value
        ]
        convergence_trend = "unknown"
        if len(convergence_values) >= 2:
            if convergence_values[-1] < convergence_values[0]:
                convergence_trend = "improving"
            elif convergence_values[-1] > convergence_values[0]:
                convergence_trend = "degrading"
            else:
                convergence_trend = "stable"

        # Health score calculation
        health_score = self._calculate_real_time_health_score(trace, recent_iterations)

        return {
            "status": "active",
            "current_iteration": len(trace.iterations),
            "avg_recent_iteration_time": avg_recent_time,
            "memory_trend": memory_trend,
            "convergence_trend": convergence_trend,
            "health_score": health_score,
            "alerts": self._generate_real_time_alerts(trace, recent_iterations),
        }

    def export_analysis_data(
        self,
        filepath: str | None = None,
        format: str = "json",
        include_traces: bool = True,
    ):
        """
        Export comprehensive analysis data.

        Exports all analysis data including traces, performance metrics,
        and reports for external analysis, archival, or sharing.

        Args:
            filepath (Optional[str]): Output file path, auto-generated if None
            format (str): Export format ("json", "csv")
            include_traces (bool): Whether to include detailed trace data

        Side Effects:
            Creates export file with analysis data

        Example:
            >>> analyzer.export_analysis_data("cycle_analysis.json", include_traces=True)
        """
        if filepath is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filepath = f"cycle_analysis_{self.current_session or 'session'}_{timestamp}.{format}"
            if self.output_directory:
                filepath = str(self.output_directory / filepath)

        export_data = {
            "analysis_metadata": {
                "session_id": self.current_session,
                "analysis_level": self.analysis_level,
                "export_timestamp": datetime.now().isoformat(),
                "cycles_count": len(self.session_traces),
            }
        }

        # Include session report
        if self.session_traces:
            export_data["session_report"] = self.generate_session_report()

        # Include individual cycle reports
        if include_traces:
            export_data["cycle_reports"] = [
                self.generate_cycle_report(trace) for trace in self.session_traces
            ]

        # Include performance history if available
        if self.profiler:
            export_data["performance_history"] = [
                metrics.to_dict() for metrics in self.profiler.performance_history
            ]

        # Export to file
        if format == "json":
            with open(filepath, "w") as f:
                json.dump(export_data, f, indent=2)
        elif format == "csv":
            # For CSV, export summary data only
            import csv

            with open(filepath, "w", newline="") as f:
                writer = csv.writer(f)

                # Write header
                writer.writerow(
                    [
                        "cycle_id",
                        "workflow_id",
                        "iterations",
                        "execution_time",
                        "converged",
                        "efficiency_score",
                    ]
                )

                # Write cycle data
                for trace in self.session_traces:
                    stats = trace.get_statistics()
                    writer.writerow(
                        [
                            trace.cycle_id,
                            trace.workflow_id,
                            len(trace.iterations),
                            trace.total_execution_time,
                            trace.converged,
                            stats.get("efficiency_score", 0.0),
                        ]
                    )
        else:
            raise ValueError(f"Unsupported export format: {format}")

        logger.info(f"Exported analysis data to {filepath} in {format} format")

    def _generate_immediate_insights(self, trace: CycleExecutionTrace):
        """Generate immediate insights for a completed cycle."""
        stats = trace.get_statistics()

        # Log key insights
        if stats["efficiency_score"] > 0.8:
            logger.info(
                f"Excellent performance for cycle '{trace.cycle_id}' - efficiency: {stats['efficiency_score']:.2f}"
            )
        elif stats["efficiency_score"] < 0.3:
            logger.warning(
                f"Poor performance for cycle '{trace.cycle_id}' - efficiency: {stats['efficiency_score']:.2f}"
            )

        if not trace.converged:
            logger.warning(
                f"Cycle '{trace.cycle_id}' failed to converge - reason: {trace.termination_reason}"
            )

        # Check for performance issues
        if stats["avg_iteration_time"] > 1.0:
            logger.warning(
                f"Slow iterations detected for cycle '{trace.cycle_id}' - avg: {stats['avg_iteration_time']:.3f}s"
            )

    def _generate_advanced_analysis(self, trace: CycleExecutionTrace) -> dict[str, Any]:
        """Generate advanced analysis insights for comprehensive mode."""
        convergence_trend = trace.get_convergence_trend()

        # Convergence pattern analysis
        convergence_analysis = {}
        if convergence_trend:
            values = [value for _, value in convergence_trend if value is not None]
            if len(values) >= 3:
                # Calculate convergence velocity
                velocity = (
                    (values[0] - values[-1]) / len(values) if len(values) > 1 else 0
                )
                convergence_analysis = {
                    "convergence_velocity": velocity,
                    "convergence_pattern": (
                        "fast"
                        if velocity > 0.1
                        else "slow" if velocity > 0.01 else "minimal"
                    ),
                    "stability_score": self._calculate_convergence_stability(values),
                }

        # Iteration pattern analysis
        iteration_times = [
            iter.execution_time for iter in trace.iterations if iter.execution_time
        ]
        iteration_analysis = {}
        if iteration_times:
            import statistics

            iteration_analysis = {
                "time_distribution": {
                    "mean": statistics.mean(iteration_times),
                    "median": statistics.median(iteration_times),
                    "mode": (
                        statistics.mode(iteration_times)
                        if len(set(iteration_times)) != len(iteration_times)
                        else None
                    ),
                    "skewness": self._calculate_skewness(iteration_times),
                },
                "performance_trend": self._analyze_performance_trend(iteration_times),
            }

        return {
            "convergence_analysis": convergence_analysis,
            "iteration_analysis": iteration_analysis,
            "resource_efficiency": self._analyze_resource_efficiency(trace),
        }

    def _generate_session_insights(
        self, traces: list[CycleExecutionTrace]
    ) -> dict[str, Any]:
        """Generate insights across multiple cycles in a session."""
        if not traces:
            return {}

        # Find best and worst performing cycles
        cycle_scores = {
            trace.cycle_id: trace.get_statistics()["efficiency_score"]
            for trace in traces
        }
        best_cycle = max(cycle_scores.items(), key=lambda x: x[1])
        worst_cycle = min(cycle_scores.items(), key=lambda x: x[1])

        # Identify patterns
        convergence_rate = len([t for t in traces if t.converged]) / len(traces)
        avg_iterations = sum(len(t.iterations) for t in traces) / len(traces)

        insights = {
            "best_performing_cycle": {"id": best_cycle[0], "score": best_cycle[1]},
            "worst_performing_cycle": {"id": worst_cycle[0], "score": worst_cycle[1]},
            "overall_convergence_rate": convergence_rate,
            "avg_iterations_per_cycle": avg_iterations,
            "performance_consistency": best_cycle[1]
            - worst_cycle[1],  # Lower is more consistent
            "session_quality": (
                "excellent"
                if convergence_rate > 0.9 and cycle_scores[best_cycle[0]] > 0.8
                else "good" if convergence_rate > 0.7 else "needs_improvement"
            ),
        }

        return insights

    def _calculate_real_time_health_score(
        self, trace: CycleExecutionTrace, recent_iterations: list
    ) -> float:
        """Calculate real-time health score for an active cycle."""
        score_components = []

        # Performance component
        if recent_iterations:
            avg_time = sum(
                iter.execution_time or 0 for iter in recent_iterations
            ) / len(recent_iterations)
            time_score = max(
                0.0, 1.0 - min(1.0, avg_time / 2.0)
            )  # Penalty after 2s per iteration
            score_components.append(time_score)

        # Error rate component
        error_count = len([iter for iter in recent_iterations if iter.error])
        error_score = (
            max(0.0, 1.0 - (error_count / len(recent_iterations)))
            if recent_iterations
            else 1.0
        )
        score_components.append(error_score)

        # Memory trend component (if available)
        memory_values = [
            iter.memory_usage_mb for iter in recent_iterations if iter.memory_usage_mb
        ]
        if memory_values and len(memory_values) >= 2:
            memory_growth = (memory_values[-1] - memory_values[0]) / memory_values[0]
            memory_score = max(
                0.0, 1.0 - max(0.0, memory_growth)
            )  # Penalty for memory growth
            score_components.append(memory_score)

        return (
            sum(score_components) / len(score_components) if score_components else 0.5
        )

    def _generate_real_time_alerts(
        self, trace: CycleExecutionTrace, recent_iterations: list
    ) -> list[str]:
        """Generate real-time alerts for potential issues."""
        alerts = []

        # Check for slow iterations
        if recent_iterations:
            avg_time = sum(
                iter.execution_time or 0 for iter in recent_iterations
            ) / len(recent_iterations)
            if avg_time > 2.0:
                alerts.append(f"Slow iterations detected: {avg_time:.2f}s average")

        # Check for errors
        error_count = len([iter for iter in recent_iterations if iter.error])
        if error_count > 0:
            alerts.append(
                f"Errors detected in {error_count}/{len(recent_iterations)} recent iterations"
            )

        # Check for memory growth
        memory_values = [
            iter.memory_usage_mb for iter in recent_iterations if iter.memory_usage_mb
        ]
        if len(memory_values) >= 2:
            memory_growth = (memory_values[-1] - memory_values[0]) / memory_values[0]
            if memory_growth > 0.2:
                alerts.append(
                    f"Memory usage increasing: {memory_growth*100:.1f}% growth"
                )

        # Check for potential non-convergence
        if len(trace.iterations) > (trace.max_iterations_configured or 100) * 0.8:
            alerts.append(
                f"Approaching max iterations: {len(trace.iterations)}/{trace.max_iterations_configured}"
            )

        return alerts

    def _calculate_convergence_stability(self, values: list[float]) -> float:
        """Calculate stability score for convergence values."""
        if len(values) < 2:
            return 1.0

        import statistics

        mean_val = statistics.mean(values)
        if mean_val == 0:
            return 1.0

        stddev = statistics.stdev(values)
        cv = stddev / mean_val  # Coefficient of variation

        # Lower CV means more stable
        return max(0.0, 1.0 - min(1.0, cv))

    def _calculate_skewness(self, data: list[float]) -> float:
        """Calculate skewness of data distribution."""
        if len(data) < 3:
            return 0.0

        import statistics

        mean_val = statistics.mean(data)
        n = len(data)
        variance = sum((x - mean_val) ** 2 for x in data) / n
        if variance == 0:
            return 0.0

        std_dev = variance**0.5
        skewness = sum((x - mean_val) ** 3 for x in data) / (n * std_dev**3)
        return skewness

    def _analyze_performance_trend(self, iteration_times: list[float]) -> str:
        """Analyze performance trend over iterations."""
        if len(iteration_times) < 3:
            return "insufficient_data"

        # Simple trend analysis
        first_half = iteration_times[: len(iteration_times) // 2]
        second_half = iteration_times[len(iteration_times) // 2 :]

        import statistics

        first_avg = statistics.mean(first_half)
        second_avg = statistics.mean(second_half)

        improvement = (first_avg - second_avg) / first_avg

        if improvement > 0.1:
            return "improving"
        elif improvement < -0.1:
            return "degrading"
        else:
            return "stable"

    def _analyze_resource_efficiency(
        self, trace: CycleExecutionTrace
    ) -> dict[str, Any]:
        """Analyze resource usage efficiency."""
        memory_values = [
            iter.memory_usage_mb for iter in trace.iterations if iter.memory_usage_mb
        ]
        cpu_values = [
            iter.cpu_usage_percent
            for iter in trace.iterations
            if iter.cpu_usage_percent
        ]

        efficiency = {}

        if memory_values:
            import statistics

            efficiency["memory_efficiency"] = {
                "peak_usage": max(memory_values),
                "avg_usage": statistics.mean(memory_values),
                "efficiency_score": max(
                    0.0, 1.0 - (max(memory_values) / 2000)
                ),  # Penalty after 2GB
            }

        if cpu_values:
            import statistics

            efficiency["cpu_efficiency"] = {
                "peak_usage": max(cpu_values),
                "avg_usage": statistics.mean(cpu_values),
                "efficiency_score": min(
                    1.0, statistics.mean(cpu_values) / 100
                ),  # Higher CPU usage is better utilization
            }

        return efficiency

    def _export_cycle_report(self, report: dict[str, Any], cycle_id: str):
        """Export cycle report to file."""
        if not self.output_directory:
            return

        filename = (
            f"cycle_report_{cycle_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )
        filepath = self.output_directory / filename

        with open(filepath, "w") as f:
            json.dump(report, f, indent=2)

        logger.debug(f"Exported cycle report to {filepath}")

    def _export_session_report(self, report: dict[str, Any], session_id: str):
        """Export session report to file."""
        if not self.output_directory:
            return

        filename = f"session_report_{session_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        filepath = self.output_directory / filename

        with open(filepath, "w") as f:
            json.dump(report, f, indent=2)

        logger.debug(f"Exported session report to {filepath}")

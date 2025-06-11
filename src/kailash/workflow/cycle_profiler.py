"""
Advanced Performance Profiling and Analysis for Cyclic Workflows.

This module provides comprehensive performance profiling capabilities for cyclic
workflows, including detailed statistical analysis, resource usage monitoring,
bottleneck identification, and automated optimization recommendations based on
execution patterns and performance characteristics.

Examples:
    Basic profiling setup:

    >>> profiler = CycleProfiler(enable_advanced_metrics=True)
    >>> # Add execution traces
    >>> profiler.add_trace(execution_trace)
    >>> # Analyze performance
    >>> metrics = profiler.analyze_performance()
    >>> print(f"Overall efficiency: {metrics.efficiency_score}")

    Comparative analysis:

    >>> # Compare multiple cycles
    >>> comparison = profiler.compare_cycles(["cycle_1", "cycle_2", "cycle_3"])
    >>> print(f"Best cycle: {comparison['best_cycle']}")
    >>> print(f"Performance gaps: {comparison['significant_differences']}")

    Optimization recommendations:

    >>> # Get actionable recommendations
    >>> recommendations = profiler.get_optimization_recommendations()
    >>> for rec in recommendations:
    ...     print(f"{rec['priority']}: {rec['description']}")
    ...     print(f"   Suggestion: {rec['suggestion']}")
    ...     print(f"   Current: {rec['current_value']}")
    ...     print(f"   Target: {rec['target_improvement']}")

    Comprehensive reporting:

    >>> # Generate detailed report
    >>> report = profiler.generate_performance_report()
    >>> # Export for external analysis
    >>> profiler.export_profile_data("performance_analysis.json")
"""

import logging
import statistics
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from kailash.workflow.cycle_debugger import CycleExecutionTrace

logger = logging.getLogger(__name__)


@dataclass
class PerformanceMetrics:
    """
    Comprehensive performance metrics for cycle analysis.

    This class aggregates and analyzes performance data from cycle executions,
    providing detailed insights into timing, resource usage, and efficiency
    characteristics of cyclic workflows.

    Attributes:
        total_cycles: Number of cycles analyzed.
        total_iterations: Total iterations across all cycles.
        avg_cycle_time: Average cycle execution time.
        avg_iteration_time: Average iteration execution time.
        min_iteration_time: Fastest iteration time.
        max_iteration_time: Slowest iteration time.
        iteration_time_stddev: Standard deviation of iteration times.
        memory_stats: Memory usage statistics.
        cpu_stats: CPU usage statistics.
        convergence_stats: Convergence analysis.
        bottlenecks: Identified performance bottlenecks.
        optimization_opportunities: Suggested optimizations.
    """

    total_cycles: int = 0
    total_iterations: int = 0
    avg_cycle_time: float = 0.0
    avg_iteration_time: float = 0.0
    min_iteration_time: float = float("inf")
    max_iteration_time: float = 0.0
    iteration_time_stddev: float = 0.0
    memory_stats: dict[str, float] = field(default_factory=dict)
    cpu_stats: dict[str, float] = field(default_factory=dict)
    convergence_stats: dict[str, Any] = field(default_factory=dict)
    bottlenecks: list[str] = field(default_factory=list)
    optimization_opportunities: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert metrics to dictionary for serialization.

        Returns:
            Dictionary representation of performance metrics.
        """
        return {
            "total_cycles": self.total_cycles,
            "total_iterations": self.total_iterations,
            "timing": {
                "avg_cycle_time": self.avg_cycle_time,
                "avg_iteration_time": self.avg_iteration_time,
                "min_iteration_time": (
                    self.min_iteration_time
                    if self.min_iteration_time != float("inf")
                    else 0.0
                ),
                "max_iteration_time": self.max_iteration_time,
                "iteration_time_stddev": self.iteration_time_stddev,
            },
            "memory_stats": self.memory_stats,
            "cpu_stats": self.cpu_stats,
            "convergence_stats": self.convergence_stats,
            "bottlenecks": self.bottlenecks,
            "optimization_opportunities": self.optimization_opportunities,
        }


class CycleProfiler:
    """
    Advanced profiling and performance analysis for cyclic workflows.

    This class provides comprehensive performance analysis capabilities for
    cycles, including statistical analysis, bottleneck identification,
    comparative analysis across multiple cycles, and detailed optimization
    recommendations based on execution patterns.

    Examples:
        >>> profiler = CycleProfiler()
        >>> profiler.add_trace(execution_trace)
        >>> metrics = profiler.analyze_performance()
        >>> recommendations = profiler.get_optimization_recommendations()
    """

    def __init__(self, enable_advanced_metrics: bool = True):
        """
        Initialize cycle profiler.

        Args:
            enable_advanced_metrics: Whether to enable advanced statistical analysis.
        """
        self.enable_advanced_metrics = enable_advanced_metrics
        self.traces: list[CycleExecutionTrace] = []
        self.performance_history: list[PerformanceMetrics] = []

    def add_trace(self, trace: CycleExecutionTrace):
        """
        Add a cycle execution trace for analysis.

        Args:
            trace: Completed execution trace to analyze.

        Examples:
            >>> profiler.add_trace(execution_trace)
        """
        self.traces.append(trace)
        logger.debug(
            f"Added trace for cycle '{trace.cycle_id}' with {len(trace.iterations)} iterations"
        )

    def analyze_performance(self) -> PerformanceMetrics:
        """
        Perform comprehensive performance analysis on all traces.

        Analyzes all collected traces to generate comprehensive performance
        metrics, identify bottlenecks, and provide optimization recommendations
        based on statistical analysis of execution patterns.

        Returns:
            Comprehensive performance analysis results.

        Examples:
            >>> metrics = profiler.analyze_performance()
            >>> print(f"Average cycle time: {metrics.avg_cycle_time:.3f}s")
        """
        if not self.traces:
            logger.warning("No traces available for performance analysis")
            return PerformanceMetrics()

        # Collect all timing data
        cycle_times = []
        iteration_times = []
        memory_values = []
        cpu_values = []
        convergence_data = []

        for trace in self.traces:
            if trace.total_execution_time:
                cycle_times.append(trace.total_execution_time)

            for iteration in trace.iterations:
                if iteration.execution_time:
                    iteration_times.append(iteration.execution_time)
                if iteration.memory_usage_mb:
                    memory_values.append(iteration.memory_usage_mb)
                if iteration.cpu_usage_percent:
                    cpu_values.append(iteration.cpu_usage_percent)
                if iteration.convergence_value:
                    convergence_data.append(iteration.convergence_value)

        # Calculate basic metrics
        metrics = PerformanceMetrics(
            total_cycles=len(self.traces),
            total_iterations=sum(len(trace.iterations) for trace in self.traces),
        )

        # Timing analysis
        if cycle_times:
            metrics.avg_cycle_time = statistics.mean(cycle_times)

        if iteration_times:
            metrics.avg_iteration_time = statistics.mean(iteration_times)
            metrics.min_iteration_time = min(iteration_times)
            metrics.max_iteration_time = max(iteration_times)
            if len(iteration_times) > 1:
                metrics.iteration_time_stddev = statistics.stdev(iteration_times)

        # Memory analysis
        if memory_values:
            metrics.memory_stats = {
                "avg": statistics.mean(memory_values),
                "min": min(memory_values),
                "max": max(memory_values),
                "stddev": (
                    statistics.stdev(memory_values) if len(memory_values) > 1 else 0.0
                ),
                "median": statistics.median(memory_values),
            }

        # CPU analysis
        if cpu_values:
            metrics.cpu_stats = {
                "avg": statistics.mean(cpu_values),
                "min": min(cpu_values),
                "max": max(cpu_values),
                "stddev": statistics.stdev(cpu_values) if len(cpu_values) > 1 else 0.0,
                "median": statistics.median(cpu_values),
            }

        # Convergence analysis
        if convergence_data:
            metrics.convergence_stats = self._analyze_convergence_performance(
                convergence_data
            )

        # Advanced analysis if enabled
        if self.enable_advanced_metrics:
            metrics.bottlenecks = self._identify_bottlenecks(metrics)
            metrics.optimization_opportunities = self._identify_optimizations(metrics)

        # Store in history
        self.performance_history.append(metrics)

        logger.info(
            f"Analyzed performance for {metrics.total_cycles} cycles, "
            f"{metrics.total_iterations} iterations, "
            f"avg cycle time: {metrics.avg_cycle_time:.3f}s"
        )

        return metrics

    def compare_cycles(self, cycle_ids: list[str]) -> dict[str, Any]:
        """
        Compare performance across multiple specific cycles.

        Provides detailed comparative analysis between specific cycles,
        highlighting performance differences, convergence patterns, and
        relative efficiency metrics.

        Args:
            cycle_ids (List[str]): List of cycle IDs to compare

        Returns:
            Dict[str, Any]: Comparative analysis results

        Side Effects:
            None - this is a pure analysis method

        Example:
            >>> comparison = profiler.compare_cycles(["cycle_1", "cycle_2"])
            >>> print(f"Best performing cycle: {comparison['best_cycle']}")
        """
        relevant_traces = [
            trace for trace in self.traces if trace.cycle_id in cycle_ids
        ]

        if len(relevant_traces) < 2:
            return {"error": "Need at least 2 cycles for comparison"}

        comparison = {
            "cycles_compared": len(relevant_traces),
            "cycle_details": {},
            "performance_ranking": [],
            "significant_differences": [],
        }

        # Analyze each cycle
        for trace in relevant_traces:
            stats = trace.get_statistics()

            comparison["cycle_details"][trace.cycle_id] = {
                "execution_time": trace.total_execution_time,
                "iterations": len(trace.iterations),
                "converged": trace.converged,
                "efficiency_score": stats["efficiency_score"],
                "avg_iteration_time": stats["avg_iteration_time"],
                "convergence_rate": stats["convergence_rate"],
            }

        # Rank by efficiency score
        ranking = sorted(
            comparison["cycle_details"].items(),
            key=lambda x: x[1]["efficiency_score"],
            reverse=True,
        )
        comparison["performance_ranking"] = [cycle_id for cycle_id, _ in ranking]
        comparison["best_cycle"] = ranking[0][0] if ranking else None
        comparison["worst_cycle"] = ranking[-1][0] if ranking else None

        # Identify significant differences
        if len(ranking) >= 2:
            best_score = ranking[0][1]["efficiency_score"]
            worst_score = ranking[-1][1]["efficiency_score"]

            if best_score - worst_score > 0.2:
                comparison["significant_differences"].append(
                    f"Large efficiency gap: {best_score:.2f} vs {worst_score:.2f}"
                )

            # Compare convergence rates
            convergence_rates = [details["convergence_rate"] for _, details in ranking]
            if max(convergence_rates) - min(convergence_rates) > 0.3:
                comparison["significant_differences"].append(
                    "Significant variation in convergence rates"
                )

        return comparison

    def get_optimization_recommendations(
        self, trace: CycleExecutionTrace | None = None
    ) -> list[dict[str, Any]]:
        """
        Generate detailed optimization recommendations.

        Provides specific, actionable optimization recommendations based on
        performance analysis, including parameter tuning suggestions,
        algorithmic improvements, and resource optimization strategies.

        Args:
            trace (Optional[CycleExecutionTrace]): Specific trace to analyze, or None for overall recommendations

        Returns:
            List[Dict[str, Any]]: List of optimization recommendations with details

        Side Effects:
            None - this is a pure analysis method

        Example:
            >>> recommendations = profiler.get_optimization_recommendations()
            >>> for rec in recommendations:
            ...     print(f"{rec['priority']}: {rec['description']}")
        """
        recommendations = []

        if trace:
            traces_to_analyze = [trace]
        else:
            traces_to_analyze = self.traces

        if not traces_to_analyze:
            return recommendations

        # Analyze all traces for patterns
        self.analyze_performance() if not trace else None

        for target_trace in traces_to_analyze:
            stats = target_trace.get_statistics()

            # Efficiency recommendations
            if stats["efficiency_score"] < 0.3:
                recommendations.append(
                    {
                        "priority": "HIGH",
                        "category": "efficiency",
                        "description": "Very low efficiency detected",
                        "suggestion": "Consider reducing max_iterations or improving convergence condition",
                        "cycle_id": target_trace.cycle_id,
                        "current_value": stats["efficiency_score"],
                        "target_improvement": "Increase to > 0.5",
                    }
                )

            # Convergence recommendations
            if not target_trace.converged:
                if stats["total_iterations"] >= (
                    target_trace.max_iterations_configured or 0
                ):
                    recommendations.append(
                        {
                            "priority": "HIGH",
                            "category": "convergence",
                            "description": "Cycle reached max_iterations without converging",
                            "suggestion": "Increase max_iterations or improve algorithm",
                            "cycle_id": target_trace.cycle_id,
                            "current_value": target_trace.max_iterations_configured,
                            "target_improvement": f"Increase to {int((target_trace.max_iterations_configured or 10) * 1.5)}",
                        }
                    )

            # Performance recommendations
            if stats["avg_iteration_time"] > 0.5:
                recommendations.append(
                    {
                        "priority": "MEDIUM",
                        "category": "performance",
                        "description": "High average iteration time",
                        "suggestion": "Optimize node execution or reduce data processing",
                        "cycle_id": target_trace.cycle_id,
                        "current_value": stats["avg_iteration_time"],
                        "target_improvement": "Reduce to < 0.5s per iteration",
                    }
                )

            # Memory recommendations
            if target_trace.memory_peak_mb and target_trace.memory_peak_mb > 1000:
                recommendations.append(
                    {
                        "priority": "MEDIUM",
                        "category": "memory",
                        "description": "High memory usage detected",
                        "suggestion": "Consider data streaming, chunking, or garbage collection",
                        "cycle_id": target_trace.cycle_id,
                        "current_value": target_trace.memory_peak_mb,
                        "target_improvement": "Reduce to < 1000 MB",
                    }
                )

            # Convergence pattern recommendations
            convergence_trend = target_trace.get_convergence_trend()
            if convergence_trend:
                pattern_analysis = self._analyze_convergence_pattern(convergence_trend)
                if pattern_analysis["unstable"]:
                    recommendations.append(
                        {
                            "priority": "HIGH",
                            "category": "stability",
                            "description": "Unstable convergence pattern detected",
                            "suggestion": "Reduce learning rate or add regularization",
                            "cycle_id": target_trace.cycle_id,
                            "current_value": "Unstable",
                            "target_improvement": "Stable convergence",
                        }
                    )

        # Sort by priority
        priority_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
        recommendations.sort(key=lambda x: priority_order.get(x["priority"], 3))

        return recommendations

    def generate_performance_report(self) -> dict[str, Any]:
        """
        Generate comprehensive performance report.

        Creates a detailed performance report including metrics analysis,
        recommendations, trends, and comparative insights across all
        analyzed cycles.

        Returns:
            Dict[str, Any]: Comprehensive performance report

        Side Effects:
            None - this is a pure analysis method

        Example:
            >>> report = profiler.generate_performance_report()
            >>> print(f"Overall score: {report['overall_score']}")
        """
        metrics = self.analyze_performance()

        # Calculate overall performance score
        overall_score = self._calculate_overall_score(metrics)

        # Generate trend analysis if we have history
        trend_analysis = (
            self._analyze_performance_trends()
            if len(self.performance_history) > 1
            else None
        )

        # Get top recommendations
        recommendations = self.get_optimization_recommendations()

        report = {
            "summary": {
                "overall_score": overall_score,
                "total_cycles_analyzed": metrics.total_cycles,
                "total_iterations": metrics.total_iterations,
                "avg_cycle_time": metrics.avg_cycle_time,
                "primary_bottlenecks": metrics.bottlenecks[:3],
            },
            "detailed_metrics": metrics.to_dict(),
            "trend_analysis": trend_analysis,
            "recommendations": recommendations[:10],  # Top 10 recommendations
            "cycle_comparisons": self._get_cycle_comparisons(),
            "generated_at": datetime.now().isoformat(),
        }

        return report

    def export_profile_data(self, filepath: str, format: str = "json"):
        """
        Export profiling data for external analysis.

        Args:
            filepath (str): Output file path
            format (str): Export format ("json", "csv")

        Side Effects:
            Creates file with profiling data

        Example:
            >>> profiler.export_profile_data("profile_analysis.json")
        """
        report = self.generate_performance_report()

        if format == "json":
            import json

            with open(filepath, "w") as f:
                json.dump(report, f, indent=2)
        elif format == "csv":
            import csv

            with open(filepath, "w", newline="") as f:
                writer = csv.writer(f)

                # Write summary data
                writer.writerow(["Metric", "Value"])
                writer.writerow(["Overall Score", report["summary"]["overall_score"]])
                writer.writerow(
                    ["Total Cycles", report["summary"]["total_cycles_analyzed"]]
                )
                writer.writerow(["Avg Cycle Time", report["summary"]["avg_cycle_time"]])
                writer.writerow([])

                # Write detailed metrics
                writer.writerow(["Detailed Metrics"])
                metrics = report["detailed_metrics"]
                for key, value in metrics.items():
                    if isinstance(value, dict):
                        for sub_key, sub_value in value.items():
                            writer.writerow([f"{key}_{sub_key}", sub_value])
                    else:
                        writer.writerow([key, value])
        else:
            raise ValueError(f"Unsupported export format: {format}")

        logger.info(f"Exported profiling data to {filepath} in {format} format")

    def _analyze_convergence_performance(
        self, convergence_data: list[float]
    ) -> dict[str, Any]:
        """Analyze convergence performance characteristics."""
        if not convergence_data:
            return {}

        return {
            "avg_convergence": statistics.mean(convergence_data),
            "min_convergence": min(convergence_data),
            "max_convergence": max(convergence_data),
            "convergence_stddev": (
                statistics.stdev(convergence_data) if len(convergence_data) > 1 else 0.0
            ),
            "convergence_trend": (
                "improving"
                if convergence_data[0] > convergence_data[-1]
                else "degrading"
            ),
            "data_points": len(convergence_data),
        }

    def _analyze_convergence_pattern(
        self, convergence_trend: list[tuple[int, float | None]]
    ) -> dict[str, Any]:
        """Analyze convergence pattern for stability."""
        valid_points = [value for _, value in convergence_trend if value is not None]

        if len(valid_points) < 3:
            return {"unstable": False, "reason": "insufficient_data"}

        # Calculate volatility
        differences = [
            abs(valid_points[i] - valid_points[i - 1])
            for i in range(1, len(valid_points))
        ]
        avg_difference = statistics.mean(differences)
        max_difference = max(differences)

        # Consider unstable if large swings or high volatility
        unstable = max_difference > (2 * avg_difference) and avg_difference > 0.1

        return {
            "unstable": unstable,
            "avg_volatility": avg_difference,
            "max_volatility": max_difference,
            "reason": "high_volatility" if unstable else "stable",
        }

    def _identify_bottlenecks(self, metrics: PerformanceMetrics) -> list[str]:
        """Identify performance bottlenecks from metrics."""
        bottlenecks = []

        # High iteration time variance suggests inconsistent performance
        if metrics.iteration_time_stddev > metrics.avg_iteration_time * 0.5:
            bottlenecks.append(
                "High iteration time variance - inconsistent node performance"
            )

        # Very slow iterations
        if metrics.max_iteration_time > metrics.avg_iteration_time * 3:
            bottlenecks.append(
                "Outlier slow iterations detected - potential resource contention"
            )

        # Memory bottlenecks
        if metrics.memory_stats and metrics.memory_stats.get("max", 0) > 2000:
            bottlenecks.append(
                "High memory usage - potential memory leaks or inefficient data handling"
            )

        # CPU bottlenecks
        if metrics.cpu_stats and metrics.cpu_stats.get("avg", 0) > 80:
            bottlenecks.append("High CPU usage - computationally intensive operations")

        return bottlenecks

    def _identify_optimizations(self, metrics: PerformanceMetrics) -> list[str]:
        """Identify optimization opportunities."""
        optimizations = []

        # Low convergence rate suggests early termination opportunities
        convergence_rate = metrics.convergence_stats.get("avg_convergence")
        if convergence_rate and convergence_rate < 0.5:
            optimizations.append(
                "Add early termination conditions for faster convergence"
            )

        # High memory variance suggests optimization potential
        if metrics.memory_stats and metrics.memory_stats.get("stddev", 0) > 100:
            optimizations.append("Optimize memory usage patterns for consistency")

        # Slow average iteration time
        if metrics.avg_iteration_time > 0.1:
            optimizations.append("Optimize node execution performance")

        return optimizations

    def _calculate_overall_score(self, metrics: PerformanceMetrics) -> float:
        """Calculate overall performance score (0-1, higher is better)."""
        score_components = []

        # Efficiency component (convergence rate)
        if metrics.convergence_stats:
            avg_convergence = metrics.convergence_stats.get("avg_convergence", 0.5)
            score_components.append(min(1.0, avg_convergence))

        # Speed component (based on iteration time)
        if metrics.avg_iteration_time > 0:
            speed_score = max(0.0, 1.0 - min(1.0, metrics.avg_iteration_time / 2.0))
            score_components.append(speed_score)

        # Consistency component (low variance is good)
        if metrics.iteration_time_stddev >= 0:
            consistency_score = max(
                0.0,
                1.0
                - min(
                    1.0,
                    (
                        metrics.iteration_time_stddev / metrics.avg_iteration_time
                        if metrics.avg_iteration_time > 0
                        else 0
                    ),
                ),
            )
            score_components.append(consistency_score)

        # Memory efficiency component
        if metrics.memory_stats:
            max_memory = metrics.memory_stats.get("max", 500)
            memory_score = max(
                0.0, 1.0 - min(1.0, max_memory / 2000)
            )  # Penalty after 2GB
            score_components.append(memory_score)

        return statistics.mean(score_components) if score_components else 0.5

    def _analyze_performance_trends(self) -> dict[str, Any]:
        """Analyze performance trends over time."""
        if len(self.performance_history) < 2:
            return {"trend": "insufficient_data"}

        recent_scores = [
            self._calculate_overall_score(m) for m in self.performance_history[-5:]
        ]

        if len(recent_scores) >= 2:
            trend = "improving" if recent_scores[-1] > recent_scores[0] else "degrading"
            trend_strength = abs(recent_scores[-1] - recent_scores[0])
        else:
            trend = "stable"
            trend_strength = 0.0

        return {
            "trend": trend,
            "trend_strength": trend_strength,
            "recent_scores": recent_scores,
            "performance_history_length": len(self.performance_history),
        }

    def _get_cycle_comparisons(self) -> dict[str, Any]:
        """Get comparative analysis across all cycles."""
        if len(self.traces) < 2:
            return {"comparison": "insufficient_data"}

        cycle_scores = {}
        for trace in self.traces:
            stats = trace.get_statistics()
            cycle_scores[trace.cycle_id] = stats["efficiency_score"]

        best_cycle = max(cycle_scores.items(), key=lambda x: x[1])
        worst_cycle = min(cycle_scores.items(), key=lambda x: x[1])

        return {
            "best_cycle": {"id": best_cycle[0], "score": best_cycle[1]},
            "worst_cycle": {"id": worst_cycle[0], "score": worst_cycle[1]},
            "score_range": best_cycle[1] - worst_cycle[1],
            "total_cycles": len(cycle_scores),
        }

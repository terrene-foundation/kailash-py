"""Performance comparison tools for LocalRuntime migration analysis.

This module provides comprehensive performance analysis capabilities to measure
and compare runtime performance before and after migration, identifying
bottlenecks, improvements, and regression risks.
"""

import asyncio
import json
import statistics
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import psutil
from kailash.runtime.local import LocalRuntime
from kailash.workflow import Workflow
from kailash.workflow.builder import WorkflowBuilder


@dataclass
class PerformanceMetric:
    """Individual performance metric measurement."""

    name: str
    value: float
    unit: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PerformanceBenchmark:
    """Performance benchmark for a specific test case."""

    test_name: str
    configuration: Dict[str, Any]
    metrics: List[PerformanceMetric] = field(default_factory=list)
    execution_time_ms: float = 0.0
    memory_usage_mb: float = 0.0
    cpu_usage_percent: float = 0.0
    success: bool = True
    error_message: Optional[str] = None
    run_timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class ComparisonResult:
    """Results of performance comparison between two benchmarks."""

    metric_name: str
    before_value: float
    after_value: float
    change_absolute: float
    change_percentage: float
    improvement: bool
    significance: str  # "major", "minor", "negligible", "regression"
    unit: str


@dataclass
class PerformanceReport:
    """Comprehensive performance comparison report."""

    before_benchmarks: List[PerformanceBenchmark]
    after_benchmarks: List[PerformanceBenchmark]
    comparisons: List[ComparisonResult] = field(default_factory=list)
    overall_improvement: bool = False
    overall_change_percentage: float = 0.0
    recommendations: List[str] = field(default_factory=list)
    risk_assessment: str = "low"  # low, medium, high
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class PerformanceComparator:
    """Comprehensive performance analysis and comparison tool."""

    def __init__(
        self, sample_size: int = 10, warmup_runs: int = 2, timeout_seconds: int = 300
    ):
        """Initialize the performance comparator.

        Args:
            sample_size: Number of measurements per benchmark
            warmup_runs: Number of warmup runs before measurement
            timeout_seconds: Timeout for individual test runs
        """
        self.sample_size = sample_size
        self.warmup_runs = warmup_runs
        self.timeout_seconds = timeout_seconds

        # Standard test workflows for benchmarking
        self.standard_workflows = self._create_standard_workflows()

        # Performance thresholds for significance assessment
        self.significance_thresholds = {
            "major_improvement": -20.0,  # 20% or more improvement
            "minor_improvement": -5.0,  # 5-20% improvement
            "negligible": 5.0,  # ±5% change
            "minor_regression": 20.0,  # 5-20% regression
            "major_regression": 50.0,  # 20%+ regression
        }

    def benchmark_configuration(
        self,
        config: Dict[str, Any],
        test_workflows: Optional[List[Tuple[str, Workflow]]] = None,
    ) -> List[PerformanceBenchmark]:
        """Benchmark a specific LocalRuntime configuration.

        Args:
            config: LocalRuntime configuration parameters
            test_workflows: Optional custom workflows to test

        Returns:
            List of performance benchmarks for each test case
        """
        test_workflows = test_workflows or self.standard_workflows
        benchmarks = []

        for test_name, workflow in test_workflows:
            benchmark = self._run_benchmark(test_name, config, workflow)
            benchmarks.append(benchmark)

        return benchmarks

    def compare_configurations(
        self,
        before_config: Dict[str, Any],
        after_config: Dict[str, Any],
        test_workflows: Optional[List[Tuple[str, Workflow]]] = None,
    ) -> PerformanceReport:
        """Compare performance between two configurations.

        Args:
            before_config: Original configuration
            after_config: New/migrated configuration
            test_workflows: Optional custom workflows to test

        Returns:
            Comprehensive performance comparison report
        """
        print("Benchmarking original configuration...")
        before_benchmarks = self.benchmark_configuration(before_config, test_workflows)

        print("Benchmarking migrated configuration...")
        after_benchmarks = self.benchmark_configuration(after_config, test_workflows)

        report = PerformanceReport(
            before_benchmarks=before_benchmarks, after_benchmarks=after_benchmarks
        )

        # Generate comparisons
        self._generate_comparisons(report)

        # Assess overall performance
        self._assess_overall_performance(report)

        # Generate recommendations
        self._generate_recommendations(report)

        return report

    def _create_standard_workflows(self) -> List[Tuple[str, Workflow]]:
        """Create standard benchmark workflows."""
        workflows = []

        # Simple linear workflow
        simple_builder = WorkflowBuilder()
        simple_builder.add_node(
            "PythonCodeNode",
            "simple_calc",
            {"code": "result = sum(range(1000))", "output_key": "calculation_result"},
        )
        workflows.append(("simple_linear", simple_builder.build()))

        # Multiple node workflow
        multi_builder = WorkflowBuilder()
        multi_builder.add_node(
            "PythonCodeNode",
            "step1",
            {
                "code": "import time; result = [i**2 for i in range(100)]",
                "output_key": "squares",
            },
        )
        multi_builder.add_node(
            "PythonCodeNode",
            "step2",
            {
                "code": "result = sum(squares)",
                "input_mapping": {"squares": "step1.squares"},
                "output_key": "sum_squares",
            },
        )
        multi_builder.add_node(
            "PythonCodeNode",
            "step3",
            {
                "code": "result = sum_squares / len(squares)",
                "input_mapping": {
                    "sum_squares": "step2.sum_squares",
                    "squares": "step1.squares",
                },
                "output_key": "average",
            },
        )
        workflows.append(("multi_node", multi_builder.build()))

        # Memory intensive workflow
        memory_builder = WorkflowBuilder()
        memory_builder.add_node(
            "PythonCodeNode",
            "memory_test",
            {
                "code": """
import gc
# Create large data structure
large_list = [list(range(1000)) for _ in range(100)]
result = len(large_list)
del large_list
gc.collect()
""",
                "output_key": "memory_result",
            },
        )
        workflows.append(("memory_intensive", memory_builder.build()))

        # Error handling workflow
        error_builder = WorkflowBuilder()
        error_builder.add_node(
            "PythonCodeNode",
            "error_test",
            {
                "code": """
try:
    # Intentional error that gets caught
    x = 1 / 0
except:
    result = "error_handled"
""",
                "output_key": "error_result",
            },
        )
        workflows.append(("error_handling", error_builder.build()))

        return workflows

    def _run_benchmark(
        self, test_name: str, config: Dict[str, Any], workflow: Workflow
    ) -> PerformanceBenchmark:
        """Run benchmark for a specific test case."""
        benchmark = PerformanceBenchmark(
            test_name=test_name, configuration=config.copy()
        )

        try:
            # Create runtime with configuration
            runtime = LocalRuntime(**config)

            # Warmup runs
            for _ in range(self.warmup_runs):
                try:
                    runtime.execute(workflow)
                except Exception:
                    pass  # Ignore warmup errors

            # Measurement runs
            execution_times = []
            memory_usages = []
            cpu_usages = []

            for run in range(self.sample_size):
                # Measure system resources before
                process = psutil.Process()
                memory_before = process.memory_info().rss / 1024 / 1024  # MB
                cpu_before = process.cpu_percent()

                # Execute workflow with timing
                start_time = time.perf_counter()
                try:
                    results, run_id = runtime.execute(workflow)
                    success = True
                    error_msg = None
                except Exception as e:
                    success = False
                    error_msg = str(e)
                    results = None

                end_time = time.perf_counter()
                execution_time = (end_time - start_time) * 1000  # Convert to ms

                # Measure system resources after
                memory_after = process.memory_info().rss / 1024 / 1024  # MB
                cpu_after = process.cpu_percent()

                # Record measurements
                if success:
                    execution_times.append(execution_time)
                    memory_usages.append(memory_after - memory_before)
                    cpu_usages.append(max(0, cpu_after - cpu_before))
                else:
                    benchmark.success = False
                    benchmark.error_message = error_msg
                    break

            # Calculate statistics
            if execution_times:
                benchmark.execution_time_ms = statistics.mean(execution_times)
                benchmark.memory_usage_mb = statistics.mean(memory_usages)
                benchmark.cpu_usage_percent = statistics.mean(cpu_usages)

                # Add detailed metrics
                benchmark.metrics.extend(
                    [
                        PerformanceMetric(
                            "execution_time_mean", benchmark.execution_time_ms, "ms"
                        ),
                        PerformanceMetric(
                            "execution_time_median",
                            statistics.median(execution_times),
                            "ms",
                        ),
                        PerformanceMetric(
                            "execution_time_stddev",
                            (
                                statistics.stdev(execution_times)
                                if len(execution_times) > 1
                                else 0.0
                            ),
                            "ms",
                        ),
                        PerformanceMetric(
                            "memory_usage_mean", benchmark.memory_usage_mb, "mb"
                        ),
                        PerformanceMetric(
                            "cpu_usage_mean", benchmark.cpu_usage_percent, "percent"
                        ),
                    ]
                )

        except Exception as e:
            benchmark.success = False
            benchmark.error_message = str(e)

        return benchmark

    def _generate_comparisons(self, report: PerformanceReport) -> None:
        """Generate performance comparisons between before and after."""
        # Group benchmarks by test name
        before_by_test = {b.test_name: b for b in report.before_benchmarks}
        after_by_test = {b.test_name: b for b in report.after_benchmarks}

        # Compare matching tests
        for test_name in before_by_test.keys():
            if test_name in after_by_test:
                before_bench = before_by_test[test_name]
                after_bench = after_by_test[test_name]

                # Skip failed benchmarks
                if not before_bench.success or not after_bench.success:
                    continue

                # Compare execution time
                report.comparisons.append(
                    self._create_comparison(
                        "execution_time",
                        before_bench.execution_time_ms,
                        after_bench.execution_time_ms,
                        "ms",
                    )
                )

                # Compare memory usage
                report.comparisons.append(
                    self._create_comparison(
                        "memory_usage",
                        before_bench.memory_usage_mb,
                        after_bench.memory_usage_mb,
                        "mb",
                    )
                )

                # Compare CPU usage
                report.comparisons.append(
                    self._create_comparison(
                        "cpu_usage",
                        before_bench.cpu_usage_percent,
                        after_bench.cpu_usage_percent,
                        "percent",
                    )
                )

    def _create_comparison(
        self, metric_name: str, before_value: float, after_value: float, unit: str
    ) -> ComparisonResult:
        """Create a performance comparison result."""
        change_absolute = after_value - before_value
        change_percentage = (
            ((after_value - before_value) / before_value * 100)
            if before_value != 0
            else 0.0
        )

        # Determine if this is an improvement (lower is better for time and resource usage)
        improvement = change_percentage < 0

        # Assess significance
        significance = self._assess_significance(change_percentage)

        return ComparisonResult(
            metric_name=metric_name,
            before_value=before_value,
            after_value=after_value,
            change_absolute=change_absolute,
            change_percentage=change_percentage,
            improvement=improvement,
            significance=significance,
            unit=unit,
        )

    def _assess_significance(self, change_percentage: float) -> str:
        """Assess the significance of a performance change."""
        if change_percentage <= self.significance_thresholds["major_improvement"]:
            return "major_improvement"
        elif change_percentage <= self.significance_thresholds["minor_improvement"]:
            return "minor_improvement"
        elif abs(change_percentage) <= self.significance_thresholds["negligible"]:
            return "negligible"
        elif change_percentage <= self.significance_thresholds["minor_regression"]:
            return "minor_regression"
        else:
            return "major_regression"

    def _assess_overall_performance(self, report: PerformanceReport) -> None:
        """Assess overall performance change."""
        if not report.comparisons:
            return

        # Calculate weighted overall change (execution time has highest weight)
        weights = {"execution_time": 0.5, "memory_usage": 0.3, "cpu_usage": 0.2}

        weighted_changes = []
        for comparison in report.comparisons:
            weight = weights.get(comparison.metric_name, 0.1)
            weighted_changes.append(comparison.change_percentage * weight)

        if weighted_changes:
            report.overall_change_percentage = sum(weighted_changes) / sum(
                weights.values()
            )
            report.overall_improvement = report.overall_change_percentage < 0

        # Assess risk level
        major_regressions = [
            c for c in report.comparisons if c.significance == "major_regression"
        ]
        minor_regressions = [
            c for c in report.comparisons if c.significance == "minor_regression"
        ]

        if major_regressions:
            report.risk_assessment = "high"
        elif len(minor_regressions) > 1:
            report.risk_assessment = "medium"
        else:
            report.risk_assessment = "low"

    def _generate_recommendations(self, report: PerformanceReport) -> None:
        """Generate performance recommendations based on comparison results."""
        recommendations = []

        # Analyze execution time changes
        exec_time_comparisons = [
            c for c in report.comparisons if c.metric_name == "execution_time"
        ]
        if exec_time_comparisons:
            avg_exec_change = sum(
                c.change_percentage for c in exec_time_comparisons
            ) / len(exec_time_comparisons)

            if avg_exec_change > 10:  # More than 10% slower
                recommendations.append(
                    "Execution time has regressed significantly. Consider reviewing workflow complexity "
                    "and optimizing node configurations."
                )
            elif avg_exec_change < -10:  # More than 10% faster
                recommendations.append(
                    "Excellent execution time improvements detected. Migration benefits are clear."
                )

        # Analyze memory usage changes
        memory_comparisons = [
            c for c in report.comparisons if c.metric_name == "memory_usage"
        ]
        if memory_comparisons:
            avg_memory_change = sum(
                c.change_percentage for c in memory_comparisons
            ) / len(memory_comparisons)

            if avg_memory_change > 25:  # More than 25% memory increase
                recommendations.append(
                    "Memory usage has increased significantly. Consider enabling connection pooling "
                    "or reviewing resource_limits configuration."
                )
            elif avg_memory_change < -15:  # More than 15% memory reduction
                recommendations.append(
                    "Memory efficiency improvements detected. Enhanced LocalRuntime is optimizing resource usage."
                )

        # General recommendations based on risk assessment
        if report.risk_assessment == "high":
            recommendations.extend(
                [
                    "High performance risk detected. Consider gradual migration or additional optimization.",
                    "Review enterprise features that might affect performance in your specific use case.",
                    "Consider running extended performance tests with production-like workloads.",
                ]
            )
        elif report.risk_assessment == "medium":
            recommendations.extend(
                [
                    "Medium performance risk. Monitor performance closely after migration.",
                    "Consider performance profiling of specific workflows that showed regression.",
                ]
            )
        else:
            recommendations.append(
                "Low performance risk. Migration appears safe from performance perspective."
            )

        # Configuration-specific recommendations
        failed_benchmarks = [b for b in report.after_benchmarks if not b.success]
        if failed_benchmarks:
            recommendations.append(
                f"Some benchmarks failed ({len(failed_benchmarks)} out of {len(report.after_benchmarks)}). "
                "Review configuration parameters and error messages."
            )

        # Enterprise feature recommendations
        if report.overall_improvement:
            recommendations.append(
                "Performance improvements suggest enhanced LocalRuntime is well-suited for your workloads. "
                "Consider enabling additional enterprise features for further optimization."
            )

        report.recommendations = recommendations

    def generate_performance_report(
        self, report: PerformanceReport, output_format: str = "text"
    ) -> str:
        """Generate a comprehensive performance report.

        Args:
            report: Performance comparison report
            output_format: Report format ("text", "json", "markdown")

        Returns:
            Formatted report string
        """
        if output_format == "json":
            return self._generate_json_report(report)
        elif output_format == "markdown":
            return self._generate_markdown_report(report)
        else:
            return self._generate_text_report(report)

    def _generate_text_report(self, report: PerformanceReport) -> str:
        """Generate text format performance report."""
        lines = []
        lines.append("=" * 60)
        lines.append("LocalRuntime Performance Comparison Report")
        lines.append("=" * 60)
        lines.append("")

        # Executive summary
        lines.append("EXECUTIVE SUMMARY")
        lines.append("-" * 20)
        lines.append(
            f"Overall Performance Change: {report.overall_change_percentage:+.1f}%"
        )
        lines.append(
            f"Overall Assessment: {'IMPROVEMENT' if report.overall_improvement else 'REGRESSION'}"
        )
        lines.append(f"Risk Level: {report.risk_assessment.upper()}")
        lines.append(f"Tests Completed: {len(report.after_benchmarks)} benchmarks")
        lines.append("")

        # Detailed comparisons
        lines.append("PERFORMANCE COMPARISONS")
        lines.append("-" * 25)
        lines.append(
            f"{'Metric':<15} {'Before':<12} {'After':<12} {'Change':<12} {'Status'}"
        )
        lines.append("-" * 65)

        for comparison in report.comparisons:
            status = "↑ BETTER" if comparison.improvement else "↓ WORSE"
            if comparison.significance == "negligible":
                status = "→ SAME"

            lines.append(
                f"{comparison.metric_name:<15} "
                f"{comparison.before_value:<12.2f} "
                f"{comparison.after_value:<12.2f} "
                f"{comparison.change_percentage:+7.1f}% "
                f"{status}"
            )

        lines.append("")

        # Recommendations
        if report.recommendations:
            lines.append("RECOMMENDATIONS")
            lines.append("-" * 18)
            for i, rec in enumerate(report.recommendations, 1):
                lines.append(f"{i}. {rec}")
            lines.append("")

        # Benchmark details
        lines.append("BENCHMARK DETAILS")
        lines.append("-" * 20)

        for benchmark in report.after_benchmarks:
            lines.append(f"Test: {benchmark.test_name}")
            lines.append(f"  Success: {'Yes' if benchmark.success else 'No'}")
            if benchmark.success:
                lines.append(f"  Execution Time: {benchmark.execution_time_ms:.2f} ms")
                lines.append(f"  Memory Usage: {benchmark.memory_usage_mb:.2f} MB")
                lines.append(f"  CPU Usage: {benchmark.cpu_usage_percent:.1f}%")
            else:
                lines.append(f"  Error: {benchmark.error_message}")
            lines.append("")

        return "\n".join(lines)

    def _generate_json_report(self, report: PerformanceReport) -> str:
        """Generate JSON format performance report."""
        data = {
            "summary": {
                "overall_change_percentage": report.overall_change_percentage,
                "overall_improvement": report.overall_improvement,
                "risk_assessment": report.risk_assessment,
                "generated_at": report.generated_at.isoformat(),
            },
            "comparisons": [
                {
                    "metric": c.metric_name,
                    "before_value": c.before_value,
                    "after_value": c.after_value,
                    "change_percentage": c.change_percentage,
                    "improvement": c.improvement,
                    "significance": c.significance,
                    "unit": c.unit,
                }
                for c in report.comparisons
            ],
            "recommendations": report.recommendations,
            "benchmarks": {
                "before": [
                    {
                        "test_name": b.test_name,
                        "success": b.success,
                        "execution_time_ms": b.execution_time_ms,
                        "memory_usage_mb": b.memory_usage_mb,
                        "cpu_usage_percent": b.cpu_usage_percent,
                        "error_message": b.error_message,
                    }
                    for b in report.before_benchmarks
                ],
                "after": [
                    {
                        "test_name": b.test_name,
                        "success": b.success,
                        "execution_time_ms": b.execution_time_ms,
                        "memory_usage_mb": b.memory_usage_mb,
                        "cpu_usage_percent": b.cpu_usage_percent,
                        "error_message": b.error_message,
                    }
                    for b in report.after_benchmarks
                ],
            },
        }

        return json.dumps(data, indent=2)

    def _generate_markdown_report(self, report: PerformanceReport) -> str:
        """Generate markdown format performance report."""
        lines = []
        lines.append("# LocalRuntime Performance Comparison Report")
        lines.append("")

        # Summary table
        lines.append("## Executive Summary")
        lines.append("")
        lines.append("| Metric | Value |")
        lines.append("|--------|-------|")
        lines.append(
            f"| Overall Performance Change | {report.overall_change_percentage:+.1f}% |"
        )
        lines.append(
            f"| Assessment | {'Improvement' if report.overall_improvement else 'Regression'} |"
        )
        lines.append(f"| Risk Level | {report.risk_assessment.title()} |")
        lines.append(f"| Tests Completed | {len(report.after_benchmarks)} |")
        lines.append("")

        # Performance comparisons
        lines.append("## Performance Comparisons")
        lines.append("")
        lines.append("| Metric | Before | After | Change | Status |")
        lines.append("|--------|---------|--------|---------|---------|")

        for comparison in report.comparisons:
            status = "✅ Better" if comparison.improvement else "❌ Worse"
            if comparison.significance == "negligible":
                status = "➡️ Same"

            lines.append(
                f"| {comparison.metric_name} | "
                f"{comparison.before_value:.2f} {comparison.unit} | "
                f"{comparison.after_value:.2f} {comparison.unit} | "
                f"{comparison.change_percentage:+.1f}% | "
                f"{status} |"
            )

        lines.append("")

        # Recommendations
        if report.recommendations:
            lines.append("## Recommendations")
            lines.append("")
            for i, rec in enumerate(report.recommendations, 1):
                lines.append(f"{i}. {rec}")
            lines.append("")

        return "\n".join(lines)

    def save_report(
        self,
        report: PerformanceReport,
        file_path: Union[str, Path],
        format: str = "json",
    ) -> None:
        """Save performance report to file.

        Args:
            report: Performance report to save
            file_path: Output file path
            format: Report format ("text", "json", "markdown")
        """
        content = self.generate_performance_report(report, format)

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)

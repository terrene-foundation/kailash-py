"""Workflow performance report generation.

This module provides comprehensive reporting capabilities for workflow performance
analysis, including detailed metrics, visualizations, and actionable insights.

Design Purpose:
- Generate comprehensive performance reports for workflow executions
- Provide detailed analysis with actionable insights and recommendations
- Support multiple output formats (HTML, PDF, JSON, Markdown)
- Enable automated report generation and scheduling

Upstream Dependencies:
- TaskManager provides execution data and metrics
- PerformanceVisualizer provides chart generation
- MetricsCollector provides detailed performance data
- RealTimeDashboard provides live monitoring capabilities

Downstream Consumers:
- CLI tools use this for generating analysis reports
- Web interfaces display generated reports
- Automated systems schedule and distribute reports
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import numpy as np

from kailash.tracking.manager import TaskManager
from kailash.tracking.models import TaskRun, TaskStatus
from kailash.visualization.performance import PerformanceVisualizer

logger = logging.getLogger(__name__)


class ReportFormat(Enum):
    """Supported report output formats."""

    HTML = "html"
    MARKDOWN = "markdown"
    JSON = "json"
    PDF = "pdf"  # Future enhancement


@dataclass
class ReportConfig:
    """Configuration for report generation.

    Attributes:
        include_charts: Whether to include performance charts
        include_recommendations: Whether to include optimization recommendations
        chart_format: Format for embedded charts ('png', 'svg')
        detail_level: Level of detail ('summary', 'detailed', 'comprehensive')
        compare_historical: Whether to compare with historical runs
        theme: Report theme ('light', 'dark', 'corporate')
    """

    include_charts: bool = True
    include_recommendations: bool = True
    chart_format: str = "png"
    detail_level: str = "detailed"
    compare_historical: bool = True
    theme: str = "corporate"


@dataclass
class PerformanceInsight:
    """Container for performance insights and recommendations.

    Attributes:
        category: Type of insight ('bottleneck', 'optimization', 'warning')
        severity: Severity level ('low', 'medium', 'high', 'critical')
        title: Brief insight title
        description: Detailed description
        recommendation: Actionable recommendation
        metrics: Supporting metrics data
    """

    category: str
    severity: str
    title: str
    description: str
    recommendation: str
    metrics: Dict[str, Any] = field(default_factory=dict)


@dataclass
class WorkflowSummary:
    """Summary statistics for a workflow run.

    Attributes:
        run_id: Workflow run identifier
        workflow_name: Name of the workflow
        total_tasks: Total number of tasks
        completed_tasks: Number of completed tasks
        failed_tasks: Number of failed tasks
        total_duration: Total execution time
        avg_cpu_usage: Average CPU usage across tasks
        peak_memory_usage: Peak memory usage
        total_io_read: Total I/O read in bytes
        total_io_write: Total I/O write in bytes
        throughput: Tasks completed per minute
        efficiency_score: Overall efficiency score (0-100)
    """

    run_id: str
    workflow_name: str
    total_tasks: int = 0
    completed_tasks: int = 0
    failed_tasks: int = 0
    total_duration: float = 0.0
    avg_cpu_usage: float = 0.0
    peak_memory_usage: float = 0.0
    total_io_read: int = 0
    total_io_write: int = 0
    throughput: float = 0.0
    efficiency_score: float = 0.0


class WorkflowPerformanceReporter:
    """Comprehensive workflow performance report generator.

    This class provides detailed performance analysis and reporting capabilities
    for workflow executions, including insights, recommendations, and comparative
    analysis across multiple runs.

    Usage:
        reporter = WorkflowPerformanceReporter(task_manager)
        report = reporter.generate_report(run_id, output_path="report.html")
    """

    def __init__(
        self, task_manager: TaskManager, config: Optional[ReportConfig] = None
    ):
        """Initialize performance reporter.

        Args:
            task_manager: TaskManager instance for data access
            config: Report configuration options
        """
        self.task_manager = task_manager
        self.config = config or ReportConfig()
        self.performance_viz = PerformanceVisualizer(task_manager)
        self.logger = logger

    def generate_report(
        self,
        run_id: str,
        output_path: Optional[Union[str, Path]] = None,
        format: ReportFormat = ReportFormat.HTML,
        compare_runs: Optional[List[str]] = None,
    ) -> Path:
        """Generate comprehensive performance report.

        Args:
            run_id: Workflow run to analyze
            output_path: Path to save report file
            format: Output format for the report
            compare_runs: List of run IDs to compare against

        Returns:
            Path to generated report file
        """
        if output_path is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = (
                Path.cwd()
                / "outputs"
                / f"workflow_report_{run_id[:8]}_{timestamp}.{format.value}"
            )

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Analyze workflow run
        analysis = self._analyze_workflow_run(run_id)

        # Generate insights and recommendations
        insights = self._generate_insights(analysis)

        # Compare with other runs if requested
        comparison_data = None
        if compare_runs:
            comparison_data = self._compare_runs([run_id] + compare_runs)

        # Generate report content based on format
        if format == ReportFormat.HTML:
            content = self._generate_html_report(analysis, insights, comparison_data)
        elif format == ReportFormat.MARKDOWN:
            content = self._generate_markdown_report(
                analysis, insights, comparison_data
            )
        elif format == ReportFormat.JSON:
            content = self._generate_json_report(analysis, insights, comparison_data)
        else:
            raise ValueError(f"Unsupported report format: {format}")

        # Write report file
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(content)

        self.logger.info(f"Generated {format.value.upper()} report: {output_path}")
        return output_path

    def _analyze_workflow_run(self, run_id: str) -> Dict[str, Any]:
        """Perform detailed analysis of a workflow run.

        Args:
            run_id: Run ID to analyze

        Returns:
            Dictionary containing analysis results
        """
        # Get run and task data
        run = self.task_manager.get_run(run_id)
        if not run:
            raise ValueError(f"Run {run_id} not found")

        tasks = self.task_manager.get_run_tasks(run_id)

        # Calculate workflow summary
        summary = self._calculate_workflow_summary(run, tasks)

        # Analyze task performance patterns
        task_analysis = self._analyze_task_performance(tasks)

        # Identify bottlenecks
        bottlenecks = self._identify_bottlenecks(tasks)

        # Resource utilization analysis
        resource_analysis = self._analyze_resource_utilization(tasks)

        # Error analysis
        error_analysis = self._analyze_errors(tasks)

        return {
            "run_info": {
                "run_id": run_id,
                "workflow_name": run.workflow_name,
                "started_at": run.started_at,
                "ended_at": run.ended_at,
                "status": run.status,
                "total_tasks": len(tasks),
            },
            "summary": summary,
            "task_analysis": task_analysis,
            "bottlenecks": bottlenecks,
            "resource_analysis": resource_analysis,
            "error_analysis": error_analysis,
            "charts": (
                self._generate_analysis_charts(run_id, tasks)
                if self.config.include_charts
                else {}
            ),
        }

    def _calculate_workflow_summary(
        self, run: Any, tasks: List[TaskRun]
    ) -> WorkflowSummary:
        """Calculate summary statistics for the workflow run."""
        summary = WorkflowSummary(
            run_id=run.run_id, workflow_name=run.workflow_name, total_tasks=len(tasks)
        )

        # Count task statuses
        summary.completed_tasks = sum(
            1 for t in tasks if t.status == TaskStatus.COMPLETED
        )
        summary.failed_tasks = sum(1 for t in tasks if t.status == TaskStatus.FAILED)

        # Calculate performance metrics for completed tasks
        completed_with_metrics = [
            t for t in tasks if t.status == TaskStatus.COMPLETED and t.metrics
        ]

        if completed_with_metrics:
            # Duration metrics
            durations = [
                t.metrics.duration for t in completed_with_metrics if t.metrics.duration
            ]
            if durations:
                summary.total_duration = sum(durations)

            # CPU metrics
            cpu_values = [
                t.metrics.cpu_usage
                for t in completed_with_metrics
                if t.metrics.cpu_usage
            ]
            if cpu_values:
                summary.avg_cpu_usage = np.mean(cpu_values)

            # Memory metrics
            memory_values = [
                t.metrics.memory_usage_mb
                for t in completed_with_metrics
                if t.metrics.memory_usage_mb
            ]
            if memory_values:
                summary.peak_memory_usage = max(memory_values)

            # I/O metrics
            for task in completed_with_metrics:
                if task.metrics.custom_metrics:
                    custom = task.metrics.custom_metrics
                    summary.total_io_read += custom.get("io_read_bytes", 0)
                    summary.total_io_write += custom.get("io_write_bytes", 0)

            # Calculate throughput (tasks/minute)
            if summary.total_duration > 0:
                summary.throughput = (
                    summary.completed_tasks / summary.total_duration
                ) * 60

            # Calculate efficiency score (0-100)
            success_rate = (
                summary.completed_tasks / summary.total_tasks
                if summary.total_tasks > 0
                else 0
            )
            avg_efficiency = min(
                100, max(0, 100 - summary.avg_cpu_usage)
            )  # Lower CPU = higher efficiency
            memory_efficiency = min(
                100, max(0, 100 - (summary.peak_memory_usage / 1000))
            )  # Normalize memory

            summary.efficiency_score = (
                (success_rate * 50) + (avg_efficiency * 0.3) + (memory_efficiency * 0.2)
            )

        return summary

    def _analyze_task_performance(self, tasks: List[TaskRun]) -> Dict[str, Any]:
        """Analyze performance patterns across tasks."""
        analysis = {
            "by_node_type": {},
            "duration_distribution": {},
            "resource_patterns": {},
            "execution_order": [],
        }

        # Group tasks by node type
        by_type = {}
        for task in tasks:
            if task.node_type not in by_type:
                by_type[task.node_type] = []
            by_type[task.node_type].append(task)

        # Analyze each node type
        for node_type, type_tasks in by_type.items():
            completed = [
                t for t in type_tasks if t.status == TaskStatus.COMPLETED and t.metrics
            ]

            if completed:
                durations = [
                    t.metrics.duration for t in completed if t.metrics.duration
                ]
                cpu_values = [
                    t.metrics.cpu_usage for t in completed if t.metrics.cpu_usage
                ]
                memory_values = [
                    t.metrics.memory_usage_mb
                    for t in completed
                    if t.metrics.memory_usage_mb
                ]

                analysis["by_node_type"][node_type] = {
                    "count": len(type_tasks),
                    "completed": len(completed),
                    "avg_duration": np.mean(durations) if durations else 0,
                    "max_duration": max(durations) if durations else 0,
                    "avg_cpu": np.mean(cpu_values) if cpu_values else 0,
                    "avg_memory": np.mean(memory_values) if memory_values else 0,
                    "success_rate": len(completed) / len(type_tasks) * 100,
                }

        # Execution order analysis
        ordered_tasks = sorted(
            [t for t in tasks if t.started_at], key=lambda t: t.started_at
        )

        analysis["execution_order"] = [
            {
                "node_id": t.node_id,
                "node_type": t.node_type,
                "started_at": t.started_at.isoformat() if t.started_at else None,
                "duration": t.metrics.duration if t.metrics else None,
                "status": t.status,
            }
            for t in ordered_tasks[:20]  # Limit to first 20 for readability
        ]

        return analysis

    def _identify_bottlenecks(self, tasks: List[TaskRun]) -> List[Dict[str, Any]]:
        """Identify performance bottlenecks in the workflow."""
        bottlenecks = []

        completed_tasks = [
            t for t in tasks if t.status == TaskStatus.COMPLETED and t.metrics
        ]

        if len(completed_tasks) < 2:
            return bottlenecks

        # Find duration outliers
        durations = [t.metrics.duration for t in completed_tasks if t.metrics.duration]
        if durations:
            duration_threshold = np.percentile(durations, 90)
            slow_tasks = [
                t
                for t in completed_tasks
                if t.metrics.duration and t.metrics.duration > duration_threshold
            ]

            for task in slow_tasks:
                bottlenecks.append(
                    {
                        "type": "duration",
                        "node_id": task.node_id,
                        "node_type": task.node_type,
                        "value": task.metrics.duration,
                        "threshold": duration_threshold,
                        "severity": (
                            "high"
                            if task.metrics.duration > duration_threshold * 2
                            else "medium"
                        ),
                    }
                )

        # Find memory outliers
        memory_values = [
            t.metrics.memory_usage_mb
            for t in completed_tasks
            if t.metrics.memory_usage_mb
        ]
        if memory_values:
            memory_threshold = np.percentile(memory_values, 90)
            memory_intensive_tasks = [
                t
                for t in completed_tasks
                if t.metrics.memory_usage_mb
                and t.metrics.memory_usage_mb > memory_threshold
            ]

            for task in memory_intensive_tasks:
                bottlenecks.append(
                    {
                        "type": "memory",
                        "node_id": task.node_id,
                        "node_type": task.node_type,
                        "value": task.metrics.memory_usage_mb,
                        "threshold": memory_threshold,
                        "severity": (
                            "high"
                            if task.metrics.memory_usage_mb > memory_threshold * 2
                            else "medium"
                        ),
                    }
                )

        # Find CPU outliers
        cpu_values = [
            t.metrics.cpu_usage for t in completed_tasks if t.metrics.cpu_usage
        ]
        if cpu_values:
            cpu_threshold = np.percentile(cpu_values, 90)
            cpu_intensive_tasks = [
                t
                for t in completed_tasks
                if t.metrics.cpu_usage and t.metrics.cpu_usage > cpu_threshold
            ]

            for task in cpu_intensive_tasks:
                bottlenecks.append(
                    {
                        "type": "cpu",
                        "node_id": task.node_id,
                        "node_type": task.node_type,
                        "value": task.metrics.cpu_usage,
                        "threshold": cpu_threshold,
                        "severity": "high" if task.metrics.cpu_usage > 80 else "medium",
                    }
                )

        return sorted(bottlenecks, key=lambda x: x["value"], reverse=True)

    def _analyze_resource_utilization(self, tasks: List[TaskRun]) -> Dict[str, Any]:
        """Analyze overall resource utilization patterns."""
        analysis = {
            "cpu_distribution": {},
            "memory_distribution": {},
            "io_patterns": {},
            "resource_efficiency": {},
        }

        completed_tasks = [
            t for t in tasks if t.status == TaskStatus.COMPLETED and t.metrics
        ]

        if not completed_tasks:
            return analysis

        # CPU distribution analysis
        cpu_values = [
            t.metrics.cpu_usage for t in completed_tasks if t.metrics.cpu_usage
        ]
        if cpu_values:
            analysis["cpu_distribution"] = {
                "mean": np.mean(cpu_values),
                "median": np.median(cpu_values),
                "std": np.std(cpu_values),
                "min": min(cpu_values),
                "max": max(cpu_values),
                "percentiles": {
                    "25th": np.percentile(cpu_values, 25),
                    "75th": np.percentile(cpu_values, 75),
                    "90th": np.percentile(cpu_values, 90),
                },
            }

        # Memory distribution analysis
        memory_values = [
            t.metrics.memory_usage_mb
            for t in completed_tasks
            if t.metrics.memory_usage_mb
        ]
        if memory_values:
            analysis["memory_distribution"] = {
                "mean": np.mean(memory_values),
                "median": np.median(memory_values),
                "std": np.std(memory_values),
                "min": min(memory_values),
                "max": max(memory_values),
                "total": sum(memory_values),
                "percentiles": {
                    "25th": np.percentile(memory_values, 25),
                    "75th": np.percentile(memory_values, 75),
                    "90th": np.percentile(memory_values, 90),
                },
            }

        # I/O patterns analysis
        io_read_total = 0
        io_write_total = 0
        io_intensive_tasks = 0

        for task in completed_tasks:
            if task.metrics.custom_metrics:
                custom = task.metrics.custom_metrics
                read_bytes = custom.get("io_read_bytes", 0)
                write_bytes = custom.get("io_write_bytes", 0)

                io_read_total += read_bytes
                io_write_total += write_bytes

                if read_bytes > 1024 * 1024 or write_bytes > 1024 * 1024:  # > 1MB
                    io_intensive_tasks += 1

        analysis["io_patterns"] = {
            "total_read_mb": io_read_total / (1024 * 1024),
            "total_write_mb": io_write_total / (1024 * 1024),
            "io_intensive_tasks": io_intensive_tasks,
            "avg_read_per_task_mb": (io_read_total / len(completed_tasks))
            / (1024 * 1024),
            "avg_write_per_task_mb": (io_write_total / len(completed_tasks))
            / (1024 * 1024),
        }

        return analysis

    def _analyze_errors(self, tasks: List[TaskRun]) -> Dict[str, Any]:
        """Analyze error patterns and failure modes."""
        analysis = {
            "error_summary": {},
            "error_by_type": {},
            "error_timeline": [],
            "recovery_suggestions": [],
        }

        failed_tasks = [t for t in tasks if t.status == TaskStatus.FAILED]

        analysis["error_summary"] = {
            "total_errors": len(failed_tasks),
            "error_rate": len(failed_tasks) / len(tasks) * 100 if tasks else 0,
            "critical_failures": len(
                [t for t in failed_tasks if "critical" in (t.error or "").lower()]
            ),
        }

        # Group errors by node type
        error_by_type = {}
        for task in failed_tasks:
            node_type = task.node_type
            if node_type not in error_by_type:
                error_by_type[node_type] = []
            error_by_type[node_type].append(
                {
                    "node_id": task.node_id,
                    "error_message": task.error,
                    "started_at": (
                        task.started_at.isoformat() if task.started_at else None
                    ),
                }
            )

        analysis["error_by_type"] = error_by_type

        # Error timeline
        failed_with_time = [t for t in failed_tasks if t.started_at]
        failed_with_time.sort(key=lambda t: t.started_at)

        analysis["error_timeline"] = [
            {
                "time": t.started_at.isoformat(),
                "node_id": t.node_id,
                "node_type": t.node_type,
                "error": t.error,
            }
            for t in failed_with_time
        ]

        return analysis

    def _generate_insights(self, analysis: Dict[str, Any]) -> List[PerformanceInsight]:
        """Generate actionable insights from analysis results."""
        insights = []

        if not self.config.include_recommendations:
            return insights

        summary = analysis["summary"]
        bottlenecks = analysis["bottlenecks"]
        analysis["resource_analysis"]
        error_analysis = analysis["error_analysis"]

        # Efficiency insights
        if summary.efficiency_score < 70:
            insights.append(
                PerformanceInsight(
                    category="optimization",
                    severity="high",
                    title="Low Overall Efficiency",
                    description=f"Workflow efficiency score is {summary.efficiency_score:.1f}/100, indicating room for improvement.",
                    recommendation="Review task resource usage and consider optimizing high-CPU or memory-intensive operations.",
                    metrics={"efficiency_score": summary.efficiency_score},
                )
            )

        # Bottleneck insights
        duration_bottlenecks = [b for b in bottlenecks if b["type"] == "duration"]
        if duration_bottlenecks:
            slowest = duration_bottlenecks[0]
            insights.append(
                PerformanceInsight(
                    category="bottleneck",
                    severity=slowest["severity"],
                    title="Execution Time Bottleneck",
                    description=f"Task {slowest['node_id']} ({slowest['node_type']}) is taking {slowest['value']:.2f}s, significantly longer than average.",
                    recommendation="Consider optimizing this task or running it in parallel with other operations.",
                    metrics={
                        "duration": slowest["value"],
                        "threshold": slowest["threshold"],
                    },
                )
            )

        # Memory insights
        memory_bottlenecks = [b for b in bottlenecks if b["type"] == "memory"]
        if memory_bottlenecks:
            memory_heavy = memory_bottlenecks[0]
            insights.append(
                PerformanceInsight(
                    category="bottleneck",
                    severity=memory_heavy["severity"],
                    title="High Memory Usage",
                    description=f"Task {memory_heavy['node_id']} is using {memory_heavy['value']:.1f}MB of memory.",
                    recommendation="Consider processing data in chunks or optimizing data structures to reduce memory footprint.",
                    metrics={"memory_mb": memory_heavy["value"]},
                )
            )

        # Error insights
        if error_analysis["error_summary"]["error_rate"] > 10:
            insights.append(
                PerformanceInsight(
                    category="warning",
                    severity="high",
                    title="High Error Rate",
                    description=f"Error rate is {error_analysis['error_summary']['error_rate']:.1f}%, indicating reliability issues.",
                    recommendation="Review error logs and implement better error handling and retry mechanisms.",
                    metrics={
                        "error_rate": error_analysis["error_summary"]["error_rate"]
                    },
                )
            )

        # Success rate insights
        success_rate = (
            (summary.completed_tasks / summary.total_tasks) * 100
            if summary.total_tasks > 0
            else 0
        )
        if success_rate < 95:
            insights.append(
                PerformanceInsight(
                    category="warning",
                    severity="medium",
                    title="Low Success Rate",
                    description=f"Only {success_rate:.1f}% of tasks completed successfully.",
                    recommendation="Investigate failed tasks and improve error handling mechanisms.",
                    metrics={"success_rate": success_rate},
                )
            )

        # Throughput insights
        if summary.throughput < 1:  # Less than 1 task per minute
            insights.append(
                PerformanceInsight(
                    category="optimization",
                    severity="medium",
                    title="Low Throughput",
                    description=f"Workflow throughput is {summary.throughput:.2f} tasks/minute.",
                    recommendation="Consider parallelizing tasks or optimizing slow operations to improve throughput.",
                    metrics={"throughput": summary.throughput},
                )
            )

        return insights

    def _generate_analysis_charts(
        self, run_id: str, tasks: List[TaskRun]
    ) -> Dict[str, str]:
        """Generate analysis charts and return file paths."""
        charts = {}

        try:
            # Use existing performance visualizer
            chart_outputs = self.performance_viz.create_run_performance_summary(run_id)
            charts.update(chart_outputs)
        except Exception as e:
            self.logger.warning(f"Failed to generate charts: {e}")

        return charts

    def _compare_runs(self, run_ids: List[str]) -> Dict[str, Any]:
        """Compare performance across multiple runs."""
        comparison = {"runs": [], "trends": {}, "relative_performance": {}}

        run_summaries = []
        for run_id in run_ids:
            try:
                run = self.task_manager.get_run(run_id)
                tasks = self.task_manager.get_run_tasks(run_id)
                summary = self._calculate_workflow_summary(run, tasks)
                run_summaries.append(summary)
            except Exception as e:
                self.logger.warning(f"Failed to analyze run {run_id}: {e}")

        if len(run_summaries) < 2:
            return comparison

        comparison["runs"] = [
            {
                "run_id": s.run_id,
                "workflow_name": s.workflow_name,
                "total_duration": s.total_duration,
                "efficiency_score": s.efficiency_score,
                "throughput": s.throughput,
                "success_rate": (
                    (s.completed_tasks / s.total_tasks) * 100
                    if s.total_tasks > 0
                    else 0
                ),
            }
            for s in run_summaries
        ]

        # Calculate trends
        baseline = run_summaries[0]
        latest = run_summaries[-1]

        comparison["trends"] = {
            "duration_change": (
                (
                    (latest.total_duration - baseline.total_duration)
                    / baseline.total_duration
                    * 100
                )
                if baseline.total_duration > 0
                else 0
            ),
            "efficiency_change": latest.efficiency_score - baseline.efficiency_score,
            "throughput_change": (
                ((latest.throughput - baseline.throughput) / baseline.throughput * 100)
                if baseline.throughput > 0
                else 0
            ),
        }

        return comparison

    def _generate_html_report(
        self,
        analysis: Dict[str, Any],
        insights: List[PerformanceInsight],
        comparison_data: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Generate HTML report content."""
        run_info = analysis["run_info"]
        summary = analysis["summary"]

        # CSS styles
        css_styles = self._get_report_css()

        # Build HTML sections
        header_section = f"""
        <header class="report-header">
            <h1>🚀 Workflow Performance Report</h1>
            <div class="run-info">
                <div class="info-item">
                    <span class="label">Run ID:</span>
                    <span class="value">{run_info['run_id']}</span>
                </div>
                <div class="info-item">
                    <span class="label">Workflow:</span>
                    <span class="value">{run_info['workflow_name']}</span>
                </div>
                <div class="info-item">
                    <span class="label">Started:</span>
                    <span class="value">{run_info['started_at']}</span>
                </div>
                <div class="info-item">
                    <span class="label">Status:</span>
                    <span class="value status-{run_info['status'].lower()}">{run_info['status']}</span>
                </div>
            </div>
        </header>
        """

        # Executive summary
        summary_section = f"""
        <section class="executive-summary">
            <h2>📊 Executive Summary</h2>
            <div class="summary-grid">
                <div class="summary-card">
                    <div class="metric-value">{summary.total_tasks}</div>
                    <div class="metric-label">Total Tasks</div>
                </div>
                <div class="summary-card">
                    <div class="metric-value">{summary.completed_tasks}</div>
                    <div class="metric-label">Completed</div>
                </div>
                <div class="summary-card">
                    <div class="metric-value">{summary.failed_tasks}</div>
                    <div class="metric-label">Failed</div>
                </div>
                <div class="summary-card">
                    <div class="metric-value">{summary.total_duration:.1f}s</div>
                    <div class="metric-label">Duration</div>
                </div>
                <div class="summary-card">
                    <div class="metric-value">{summary.avg_cpu_usage:.1f}%</div>
                    <div class="metric-label">Avg CPU</div>
                </div>
                <div class="summary-card">
                    <div class="metric-value">{summary.peak_memory_usage:.0f}MB</div>
                    <div class="metric-label">Peak Memory</div>
                </div>
                <div class="summary-card">
                    <div class="metric-value">{summary.throughput:.1f}</div>
                    <div class="metric-label">Tasks/Min</div>
                </div>
                <div class="summary-card">
                    <div class="metric-value efficiency-score">{summary.efficiency_score:.0f}/100</div>
                    <div class="metric-label">Efficiency Score</div>
                </div>
            </div>
        </section>
        """

        # Insights section
        insights_section = ""
        if insights:
            insight_items = ""
            for insight in insights:
                severity_class = f"severity-{insight.severity}"
                category_icon = {
                    "bottleneck": "🔍",
                    "optimization": "⚡",
                    "warning": "⚠️",
                }.get(insight.category, "📋")

                insight_items += f"""
                <div class="insight-item {severity_class}">
                    <div class="insight-header">
                        <span class="insight-icon">{category_icon}</span>
                        <h4>{insight.title}</h4>
                        <span class="severity-badge {severity_class}">{insight.severity}</span>
                    </div>
                    <div class="insight-content">
                        <p class="description">{insight.description}</p>
                        <p class="recommendation"><strong>Recommendation:</strong> {insight.recommendation}</p>
                    </div>
                </div>
                """

            insights_section = f"""
            <section class="insights-section">
                <h2>💡 Performance Insights</h2>
                <div class="insights-container">
                    {insight_items}
                </div>
            </section>
            """

        # Charts section
        charts_section = ""
        if analysis.get("charts"):
            chart_items = ""
            for chart_name, chart_path in analysis["charts"].items():
                chart_items += f"""
                <div class="chart-item">
                    <h4>{chart_name.replace('_', ' ').title()}</h4>
                    <img src="{chart_path}" alt="{chart_name}" class="chart-image">
                </div>
                """

            charts_section = f"""
            <section class="charts-section">
                <h2>📈 Performance Visualizations</h2>
                <div class="charts-grid">
                    {chart_items}
                </div>
            </section>
            """

        # Comparison section
        comparison_section = ""
        if comparison_data and comparison_data.get("runs"):
            comparison_section = self._generate_comparison_html(comparison_data)

        # Combine all sections
        html_content = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Workflow Performance Report</title>
    <style>{css_styles}</style>
</head>
<body>
    <div class="report-container">
        {header_section}
        {summary_section}
        {insights_section}
        {charts_section}
        {comparison_section}

        <footer class="report-footer">
            <p>Generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} by Kailash Workflow Performance Reporter</p>
        </footer>
    </div>
</body>
</html>
        """

        return html_content

    def _generate_markdown_report(
        self,
        analysis: Dict[str, Any],
        insights: List[PerformanceInsight],
        comparison_data: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Generate Markdown report content."""
        run_info = analysis["run_info"]
        summary = analysis["summary"]

        lines = []
        lines.append("# 🚀 Workflow Performance Report")
        lines.append("")
        lines.append(f"**Run ID:** {run_info['run_id']}")
        lines.append(f"**Workflow:** {run_info['workflow_name']}")
        lines.append(f"**Started:** {run_info['started_at']}")
        lines.append(f"**Status:** {run_info['status']}")
        lines.append("")

        # Executive Summary
        lines.append("## 📊 Executive Summary")
        lines.append("")
        lines.append("| Metric | Value |")
        lines.append("|--------|-------|")
        lines.append(f"| Total Tasks | {summary.total_tasks} |")
        lines.append(f"| Completed Tasks | {summary.completed_tasks} |")
        lines.append(f"| Failed Tasks | {summary.failed_tasks} |")
        lines.append(f"| Total Duration | {summary.total_duration:.2f}s |")
        lines.append(f"| Average CPU Usage | {summary.avg_cpu_usage:.1f}% |")
        lines.append(f"| Peak Memory Usage | {summary.peak_memory_usage:.0f}MB |")
        lines.append(f"| Throughput | {summary.throughput:.2f} tasks/min |")
        lines.append(f"| Efficiency Score | {summary.efficiency_score:.0f}/100 |")
        lines.append("")

        # Insights
        if insights:
            lines.append("## 💡 Performance Insights")
            lines.append("")
            for insight in insights:
                icon = {"bottleneck": "🔍", "optimization": "⚡", "warning": "⚠️"}.get(
                    insight.category, "📋"
                )
                lines.append(f"### {icon} {insight.title} ({insight.severity.upper()})")
                lines.append("")
                lines.append(f"**Description:** {insight.description}")
                lines.append("")
                lines.append(f"**Recommendation:** {insight.recommendation}")
                lines.append("")

        # Task Analysis
        task_analysis = analysis.get("task_analysis", {})
        if task_analysis.get("by_node_type"):
            lines.append("## 📋 Task Performance by Node Type")
            lines.append("")
            lines.append(
                "| Node Type | Count | Completed | Avg Duration | Success Rate |"
            )
            lines.append(
                "|-----------|-------|-----------|--------------|--------------|"
            )

            for node_type, stats in task_analysis["by_node_type"].items():
                lines.append(
                    f"| {node_type} | {stats['count']} | {stats['completed']} | "
                    f"{stats['avg_duration']:.2f}s | {stats['success_rate']:.1f}% |"
                )
            lines.append("")

        # Bottlenecks
        bottlenecks = analysis.get("bottlenecks", [])
        if bottlenecks:
            lines.append("## 🔍 Performance Bottlenecks")
            lines.append("")
            for bottleneck in bottlenecks[:5]:  # Top 5 bottlenecks
                lines.append(
                    f"- **{bottleneck['node_id']}** ({bottleneck['node_type']}): "
                    f"{bottleneck['type']} = {bottleneck['value']:.2f} "
                    f"(threshold: {bottleneck['threshold']:.2f}) - {bottleneck['severity']} severity"
                )
            lines.append("")

        # Error Analysis
        error_analysis = analysis.get("error_analysis", {})
        if error_analysis.get("error_summary", {}).get("total_errors", 0) > 0:
            lines.append("## ⚠️ Error Analysis")
            lines.append("")
            error_summary = error_analysis["error_summary"]
            lines.append(f"- **Total Errors:** {error_summary['total_errors']}")
            lines.append(f"- **Error Rate:** {error_summary['error_rate']:.1f}%")
            lines.append(
                f"- **Critical Failures:** {error_summary['critical_failures']}"
            )
            lines.append("")

        # Comparison
        if comparison_data and comparison_data.get("runs"):
            lines.append("## 📈 Performance Comparison")
            lines.append("")
            trends = comparison_data.get("trends", {})
            lines.append("**Trends vs Previous Run:**")
            lines.append(f"- Duration Change: {trends.get('duration_change', 0):.1f}%")
            lines.append(
                f"- Efficiency Change: {trends.get('efficiency_change', 0):.1f} points"
            )
            lines.append(
                f"- Throughput Change: {trends.get('throughput_change', 0):.1f}%"
            )
            lines.append("")

        lines.append("---")
        lines.append(
            f"*Generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} by Kailash Performance Reporter*"
        )

        return "\n".join(lines)

    def _generate_json_report(
        self,
        analysis: Dict[str, Any],
        insights: List[PerformanceInsight],
        comparison_data: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Generate JSON report content."""
        report_data = {
            "metadata": {
                "generated_at": datetime.now().isoformat(),
                "generator": "Kailash Workflow Performance Reporter",
                "version": "1.0",
            },
            "run_info": analysis["run_info"],
            "summary": {
                "total_tasks": analysis["summary"].total_tasks,
                "completed_tasks": analysis["summary"].completed_tasks,
                "failed_tasks": analysis["summary"].failed_tasks,
                "total_duration": analysis["summary"].total_duration,
                "avg_cpu_usage": analysis["summary"].avg_cpu_usage,
                "peak_memory_usage": analysis["summary"].peak_memory_usage,
                "throughput": analysis["summary"].throughput,
                "efficiency_score": analysis["summary"].efficiency_score,
            },
            "insights": [
                {
                    "category": insight.category,
                    "severity": insight.severity,
                    "title": insight.title,
                    "description": insight.description,
                    "recommendation": insight.recommendation,
                    "metrics": insight.metrics,
                }
                for insight in insights
            ],
            "detailed_analysis": {
                "task_analysis": analysis.get("task_analysis", {}),
                "bottlenecks": analysis.get("bottlenecks", []),
                "resource_analysis": analysis.get("resource_analysis", {}),
                "error_analysis": analysis.get("error_analysis", {}),
            },
        }

        if comparison_data:
            report_data["comparison"] = comparison_data

        return json.dumps(report_data, indent=2, default=str)

    def _generate_comparison_html(self, comparison_data: Dict[str, Any]) -> str:
        """Generate HTML for run comparison section."""
        runs = comparison_data.get("runs", [])
        trends = comparison_data.get("trends", {})

        if not runs:
            return ""

        # Build comparison table
        table_rows = ""
        for run in runs:
            table_rows += f"""
            <tr>
                <td>{run['run_id'][:8]}...</td>
                <td>{run['total_duration']:.1f}s</td>
                <td>{run['efficiency_score']:.0f}/100</td>
                <td>{run['throughput']:.2f}</td>
                <td>{run['success_rate']:.1f}%</td>
            </tr>
            """

        # Trend indicators
        duration_trend = "📈" if trends.get("duration_change", 0) > 0 else "📉"
        efficiency_trend = "📈" if trends.get("efficiency_change", 0) > 0 else "📉"
        throughput_trend = "📈" if trends.get("throughput_change", 0) > 0 else "📉"

        return f"""
        <section class="comparison-section">
            <h2>📈 Performance Comparison</h2>

            <div class="trends-summary">
                <h3>Trends vs Previous Run</h3>
                <div class="trends-grid">
                    <div class="trend-item">
                        <span class="trend-icon">{duration_trend}</span>
                        <span class="trend-label">Duration</span>
                        <span class="trend-value">{trends.get('duration_change', 0):+.1f}%</span>
                    </div>
                    <div class="trend-item">
                        <span class="trend-icon">{efficiency_trend}</span>
                        <span class="trend-label">Efficiency</span>
                        <span class="trend-value">{trends.get('efficiency_change', 0):+.1f}</span>
                    </div>
                    <div class="trend-item">
                        <span class="trend-icon">{throughput_trend}</span>
                        <span class="trend-label">Throughput</span>
                        <span class="trend-value">{trends.get('throughput_change', 0):+.1f}%</span>
                    </div>
                </div>
            </div>

            <table class="comparison-table">
                <thead>
                    <tr>
                        <th>Run ID</th>
                        <th>Duration</th>
                        <th>Efficiency</th>
                        <th>Throughput</th>
                        <th>Success Rate</th>
                    </tr>
                </thead>
                <tbody>
                    {table_rows}
                </tbody>
            </table>
        </section>
        """

    def _get_report_css(self) -> str:
        """Get CSS styles for HTML reports."""
        return """
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            line-height: 1.6;
            color: #333;
            background-color: #f8f9fa;
        }

        .report-container {
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
        }

        .report-header {
            background: white;
            padding: 30px;
            border-radius: 12px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            margin-bottom: 30px;
        }

        .report-header h1 {
            color: #2c3e50;
            margin-bottom: 20px;
            font-size: 2.5em;
        }

        .run-info {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
        }

        .info-item {
            display: flex;
            flex-direction: column;
        }

        .info-item .label {
            font-weight: bold;
            color: #7f8c8d;
            font-size: 0.9em;
        }

        .info-item .value {
            font-size: 1.1em;
            color: #2c3e50;
        }

        .status-completed { color: #27ae60; }
        .status-failed { color: #e74c3c; }
        .status-running { color: #3498db; }

        section {
            background: white;
            margin-bottom: 30px;
            padding: 30px;
            border-radius: 12px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }

        section h2 {
            color: #2c3e50;
            margin-bottom: 25px;
            font-size: 1.8em;
            border-bottom: 2px solid #ecf0f1;
            padding-bottom: 10px;
        }

        .summary-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 20px;
        }

        .summary-card {
            text-align: center;
            padding: 20px;
            background: #f8f9fa;
            border-radius: 8px;
            border: 1px solid #ecf0f1;
        }

        .metric-value {
            font-size: 2em;
            font-weight: bold;
            color: #3498db;
            display: block;
        }

        .efficiency-score {
            color: #27ae60;
        }

        .metric-label {
            color: #7f8c8d;
            font-size: 0.9em;
            margin-top: 5px;
        }

        .insights-container {
            display: flex;
            flex-direction: column;
            gap: 20px;
        }

        .insight-item {
            border-left: 4px solid #3498db;
            padding: 20px;
            background: #f8f9fa;
            border-radius: 0 8px 8px 0;
        }

        .insight-item.severity-high {
            border-left-color: #e74c3c;
        }

        .insight-item.severity-medium {
            border-left-color: #f39c12;
        }

        .insight-item.severity-low {
            border-left-color: #27ae60;
        }

        .insight-header {
            display: flex;
            align-items: center;
            gap: 10px;
            margin-bottom: 15px;
        }

        .insight-icon {
            font-size: 1.2em;
        }

        .insight-header h4 {
            flex: 1;
            color: #2c3e50;
            margin: 0;
        }

        .severity-badge {
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 0.8em;
            font-weight: bold;
            text-transform: uppercase;
            color: white;
        }

        .severity-high {
            background: #e74c3c;
        }

        .severity-medium {
            background: #f39c12;
        }

        .severity-low {
            background: #27ae60;
        }

        .description {
            margin-bottom: 10px;
            color: #555;
        }

        .recommendation {
            color: #2c3e50;
        }

        .charts-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
            gap: 20px;
        }

        .chart-item {
            text-align: center;
        }

        .chart-item h4 {
            margin-bottom: 15px;
            color: #2c3e50;
        }

        .chart-image {
            max-width: 100%;
            height: auto;
            border: 1px solid #ecf0f1;
            border-radius: 8px;
        }

        .trends-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 15px;
            margin-bottom: 20px;
        }

        .trend-item {
            text-align: center;
            padding: 15px;
            background: #f8f9fa;
            border-radius: 8px;
        }

        .trend-icon {
            font-size: 1.5em;
            display: block;
            margin-bottom: 5px;
        }

        .trend-label {
            display: block;
            color: #7f8c8d;
            font-size: 0.9em;
        }

        .trend-value {
            font-weight: bold;
            color: #2c3e50;
        }

        .comparison-table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 20px;
        }

        .comparison-table th,
        .comparison-table td {
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #ecf0f1;
        }

        .comparison-table th {
            background: #f8f9fa;
            font-weight: bold;
            color: #2c3e50;
        }

        .report-footer {
            text-align: center;
            color: #7f8c8d;
            font-size: 0.9em;
            padding: 20px;
            border-top: 1px solid #ecf0f1;
        }
        """

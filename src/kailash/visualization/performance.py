"""Performance visualization for task tracking metrics.

This module provides visualization capabilities for performance metrics collected
during workflow execution, integrating with the TaskManager to create comprehensive
performance reports and graphs.

Design Purpose:
- Visualize real-time performance data from task executions
- Support various chart types for different metrics
- Generate both static images and interactive visualizations
- Integrate with existing workflow visualization framework

Upstream Dependencies:
- TaskManager provides task run data with metrics
- MetricsCollector provides performance data format
- WorkflowVisualizer provides base visualization infrastructure

Downstream Consumers:
- Examples use this for performance reporting
- Export utilities include performance visualizations
- Web dashboards can embed generated charts
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import matplotlib.pyplot as plt
import numpy as np

from kailash.tracking.manager import TaskManager
from kailash.tracking.models import TaskRun, TaskStatus

logger = logging.getLogger(__name__)


class PerformanceVisualizer:
    """Creates performance visualizations from task execution metrics.

    This class provides methods to generate various performance charts and
    reports from task execution data collected by the TaskManager.
    """

    def __init__(self, task_manager: TaskManager):
        """Initialize performance visualizer.

        Args:
            task_manager: TaskManager instance with execution data
        """
        self.task_manager = task_manager
        self.logger = logger

    def create_run_performance_summary(
        self, run_id: str, output_dir: Optional[Path] = None
    ) -> Dict[str, Path]:
        """Create comprehensive performance summary for a workflow run.

        Args:
            run_id: Run ID to visualize
            output_dir: Directory to save visualizations

        Returns:
            Dictionary mapping chart names to file paths
        """
        if output_dir is None:
            # Use relative path that works from project root or create in current directory
            output_dir = Path.cwd() / "outputs" / "performance"
        output_dir.mkdir(parents=True, exist_ok=True)

        # Get run data
        run = self.task_manager.get_run(run_id)
        if not run:
            raise ValueError(f"Run {run_id} not found")

        tasks = self.task_manager.get_run_tasks(run_id)
        if not tasks:
            self.logger.warning(f"No tasks found for run {run_id}")
            return {}

        outputs = {}

        # Generate different visualizations
        outputs["execution_timeline"] = self._create_execution_timeline(
            tasks, output_dir / f"timeline_{run_id}.png"
        )

        outputs["resource_usage"] = self._create_resource_usage_chart(
            tasks, output_dir / f"resources_{run_id}.png"
        )

        outputs["performance_comparison"] = self._create_node_performance_comparison(
            tasks, output_dir / f"comparison_{run_id}.png"
        )

        outputs["io_analysis"] = self._create_io_analysis(
            tasks, output_dir / f"io_analysis_{run_id}.png"
        )

        outputs["performance_heatmap"] = self._create_performance_heatmap(
            tasks, output_dir / f"heatmap_{run_id}.png"
        )

        # Generate markdown report
        outputs["report"] = self._create_performance_report(
            run, tasks, output_dir / f"report_{run_id}.md"
        )

        return outputs

    def _create_execution_timeline(
        self, tasks: List[TaskRun], output_path: Path
    ) -> Path:
        """Create Gantt-style execution timeline."""
        fig, ax = plt.subplots(figsize=(12, max(6, len(tasks) * 0.5)))

        # Sort tasks by start time
        tasks_with_times = []
        for task in tasks:
            if task.started_at and task.ended_at:
                tasks_with_times.append(task)

        if not tasks_with_times:
            ax.text(
                0.5,
                0.5,
                "No timing data available",
                ha="center",
                va="center",
                transform=ax.transAxes,
            )
            plt.savefig(output_path)
            plt.close()
            return output_path

        tasks_with_times.sort(key=lambda t: t.started_at)

        # Calculate timeline bounds
        min_time = min(t.started_at for t in tasks_with_times)
        max(t.ended_at for t in tasks_with_times)

        # Create timeline bars
        y_positions = []
        labels = []
        colors = []

        for i, task in enumerate(tasks_with_times):
            start_offset = (task.started_at - min_time).total_seconds()
            duration = (task.ended_at - task.started_at).total_seconds()

            # Color based on status
            color_map = {
                TaskStatus.COMPLETED: "green",
                TaskStatus.FAILED: "red",
                TaskStatus.CANCELLED: "orange",
                TaskStatus.RUNNING: "blue",
            }
            color = color_map.get(task.status, "gray")

            ax.barh(
                i,
                duration,
                left=start_offset,
                height=0.8,
                color=color,
                alpha=0.7,
                edgecolor="black",
                linewidth=1,
            )

            # Add metrics annotations if available
            if task.metrics and task.metrics.cpu_usage:
                ax.text(
                    start_offset + duration / 2,
                    i,
                    f"CPU: {task.metrics.cpu_usage:.1f}%",
                    ha="center",
                    va="center",
                    fontsize=8,
                )

            y_positions.append(i)
            labels.append(f"{task.node_id}\n({task.node_type})")
            colors.append(color)

        ax.set_yticks(y_positions)
        ax.set_yticklabels(labels)
        ax.set_xlabel("Time (seconds)")
        ax.set_title("Task Execution Timeline")
        ax.grid(True, axis="x", alpha=0.3)

        # Add legend
        from matplotlib.patches import Patch

        legend_elements = [
            Patch(facecolor="green", alpha=0.7, label="Completed"),
            Patch(facecolor="red", alpha=0.7, label="Failed"),
            Patch(facecolor="blue", alpha=0.7, label="Running"),
            Patch(facecolor="orange", alpha=0.7, label="Cancelled"),
        ]
        ax.legend(handles=legend_elements, loc="upper right")

        plt.tight_layout()
        plt.savefig(output_path, dpi=150, bbox_inches="tight")
        plt.close()

        return output_path

    def _create_resource_usage_chart(
        self, tasks: List[TaskRun], output_path: Path
    ) -> Path:
        """Create resource usage comparison chart."""
        fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(10, 12))

        # Collect metrics data
        node_names = []
        cpu_usage = []
        memory_usage = []
        memory_delta = []
        durations = []

        for task in tasks:
            if task.metrics:
                node_names.append(f"{task.node_id}\n{task.node_type}")
                cpu_usage.append(task.metrics.cpu_usage or 0)
                memory_usage.append(task.metrics.memory_usage_mb or 0)

                # Get memory delta from custom metrics
                custom = task.metrics.custom_metrics or {}
                memory_delta.append(custom.get("memory_delta_mb", 0))
                durations.append(task.metrics.duration or 0)

        if not node_names:
            for ax in [ax1, ax2, ax3]:
                ax.text(
                    0.5,
                    0.5,
                    "No metrics data available",
                    ha="center",
                    va="center",
                    transform=ax.transAxes,
                )
            plt.savefig(output_path)
            plt.close()
            return output_path

        x = np.arange(len(node_names))

        # CPU usage chart
        bars1 = ax1.bar(x, cpu_usage, color="skyblue", edgecolor="black")
        ax1.set_ylabel("CPU Usage (%)")
        ax1.set_title("CPU Usage by Node")
        ax1.set_xticks(x)
        ax1.set_xticklabels(node_names, rotation=45, ha="right")
        ax1.grid(True, axis="y", alpha=0.3)

        # Add value labels
        for bar, value in zip(bars1, cpu_usage):
            if value > 0:
                ax1.text(
                    bar.get_x() + bar.get_width() / 2,
                    bar.get_height() + 1,
                    f"{value:.1f}%",
                    ha="center",
                    va="bottom",
                    fontsize=8,
                )

        # Memory usage chart
        ax2.bar(x, memory_usage, color="lightgreen", edgecolor="black")
        ax2.bar(
            x,
            memory_delta,
            bottom=memory_usage,
            color="darkgreen",
            alpha=0.5,
            edgecolor="black",
        )
        ax2.set_ylabel("Memory (MB)")
        ax2.set_title("Memory Usage by Node")
        ax2.set_xticks(x)
        ax2.set_xticklabels(node_names, rotation=45, ha="right")
        ax2.grid(True, axis="y", alpha=0.3)
        ax2.legend(["Peak Memory", "Memory Delta"])

        # Duration chart
        bars3 = ax3.bar(x, durations, color="lightcoral", edgecolor="black")
        ax3.set_ylabel("Duration (seconds)")
        ax3.set_title("Execution Time by Node")
        ax3.set_xticks(x)
        ax3.set_xticklabels(node_names, rotation=45, ha="right")
        ax3.grid(True, axis="y", alpha=0.3)

        # Add value labels
        for bar, value in zip(bars3, durations):
            if value > 0:
                ax3.text(
                    bar.get_x() + bar.get_width() / 2,
                    bar.get_height() + 0.01,
                    f"{value:.2f}s",
                    ha="center",
                    va="bottom",
                    fontsize=8,
                )

        plt.suptitle("Resource Usage Analysis", fontsize=14)
        plt.tight_layout()
        plt.savefig(output_path, dpi=150, bbox_inches="tight")
        plt.close()

        return output_path

    def _create_node_performance_comparison(
        self, tasks: List[TaskRun], output_path: Path
    ) -> Path:
        """Create performance comparison radar chart."""
        # Group tasks by node type
        node_type_metrics = {}

        for task in tasks:
            if task.metrics and task.status == TaskStatus.COMPLETED:
                node_type = task.node_type
                if node_type not in node_type_metrics:
                    node_type_metrics[node_type] = {
                        "cpu": [],
                        "memory": [],
                        "duration": [],
                        "io_read": [],
                        "io_write": [],
                    }

                metrics = node_type_metrics[node_type]
                metrics["cpu"].append(task.metrics.cpu_usage or 0)
                metrics["memory"].append(task.metrics.memory_usage_mb or 0)
                metrics["duration"].append(task.metrics.duration or 0)

                custom = task.metrics.custom_metrics or {}
                metrics["io_read"].append(
                    custom.get("io_read_bytes", 0) / 1024 / 1024
                )  # MB
                metrics["io_write"].append(
                    custom.get("io_write_bytes", 0) / 1024 / 1024
                )  # MB

        if not node_type_metrics:
            fig, ax = plt.subplots(figsize=(8, 6))
            ax.text(
                0.5,
                0.5,
                "No performance data available",
                ha="center",
                va="center",
                transform=ax.transAxes,
            )
            plt.savefig(output_path)
            plt.close()
            return output_path

        # Calculate averages
        avg_metrics = {}
        for node_type, metrics in node_type_metrics.items():
            avg_metrics[node_type] = {
                "CPU %": np.mean(metrics["cpu"]) if metrics["cpu"] else 0,
                "Memory MB": np.mean(metrics["memory"]) if metrics["memory"] else 0,
                "Duration s": (
                    np.mean(metrics["duration"]) if metrics["duration"] else 0
                ),
                "I/O Read MB": np.mean(metrics["io_read"]) if metrics["io_read"] else 0,
                "I/O Write MB": (
                    np.mean(metrics["io_write"]) if metrics["io_write"] else 0
                ),
            }

        # Create radar chart
        fig, ax = plt.subplots(figsize=(10, 8), subplot_kw=dict(projection="polar"))

        categories = list(next(iter(avg_metrics.values())).keys())
        num_vars = len(categories)

        angles = np.linspace(0, 2 * np.pi, num_vars, endpoint=False).tolist()
        angles += angles[:1]  # Complete the circle

        colors = plt.cm.tab10(np.linspace(0, 1, len(avg_metrics)))

        for (node_type, metrics), color in zip(avg_metrics.items(), colors):
            values = list(metrics.values())

            # Normalize values to 0-100 scale for better visualization
            max_vals = {
                "CPU %": 100,
                "Memory MB": max(max(m["Memory MB"] for m in avg_metrics.values()), 1),
                "Duration s": max(
                    max(m["Duration s"] for m in avg_metrics.values()), 1
                ),
                "I/O Read MB": max(
                    max(m["I/O Read MB"] for m in avg_metrics.values()), 1
                ),
                "I/O Write MB": max(
                    max(m["I/O Write MB"] for m in avg_metrics.values()), 1
                ),
            }

            normalized_values = []
            for cat, val in zip(categories, values):
                normalized_values.append((val / max_vals[cat]) * 100)

            normalized_values += normalized_values[:1]

            ax.plot(
                angles,
                normalized_values,
                "o-",
                linewidth=2,
                label=node_type,
                color=color,
            )
            ax.fill(angles, normalized_values, alpha=0.25, color=color)

        ax.set_xticks(angles[:-1])
        ax.set_xticklabels(categories)
        ax.set_ylim(0, 100)
        ax.set_ylabel("Relative Performance (0-100)", labelpad=30)
        ax.set_title(
            "Node Type Performance Comparison\n(Normalized to 0-100 scale)", pad=20
        )
        ax.legend(loc="upper right", bbox_to_anchor=(1.3, 1.0))
        ax.grid(True)

        plt.tight_layout()
        plt.savefig(output_path, dpi=150, bbox_inches="tight")
        plt.close()

        return output_path

    def _create_io_analysis(self, tasks: List[TaskRun], output_path: Path) -> Path:
        """Create I/O operations analysis chart."""
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 8))

        # Collect I/O data
        node_names = []
        io_read_bytes = []
        io_write_bytes = []
        io_read_count = []
        io_write_count = []

        for task in tasks:
            if task.metrics and task.metrics.custom_metrics:
                custom = task.metrics.custom_metrics
                if any(
                    custom.get(k, 0) > 0
                    for k in [
                        "io_read_bytes",
                        "io_write_bytes",
                        "io_read_count",
                        "io_write_count",
                    ]
                ):
                    node_names.append(f"{task.node_id}")
                    io_read_bytes.append(
                        custom.get("io_read_bytes", 0) / 1024 / 1024
                    )  # MB
                    io_write_bytes.append(
                        custom.get("io_write_bytes", 0) / 1024 / 1024
                    )  # MB
                    io_read_count.append(custom.get("io_read_count", 0))
                    io_write_count.append(custom.get("io_write_count", 0))

        if not node_names:
            for ax in [ax1, ax2]:
                ax.text(
                    0.5,
                    0.5,
                    "No I/O data available",
                    ha="center",
                    va="center",
                    transform=ax.transAxes,
                )
            plt.savefig(output_path)
            plt.close()
            return output_path

        x = np.arange(len(node_names))
        width = 0.35

        # I/O bytes chart
        ax1.bar(
            x - width / 2,
            io_read_bytes,
            width,
            label="Read",
            color="lightblue",
            edgecolor="black",
        )
        ax1.bar(
            x + width / 2,
            io_write_bytes,
            width,
            label="Write",
            color="lightcoral",
            edgecolor="black",
        )

        ax1.set_ylabel("Data (MB)")
        ax1.set_title("I/O Data Transfer by Node")
        ax1.set_xticks(x)
        ax1.set_xticklabels(node_names, rotation=45, ha="right")
        ax1.legend()
        ax1.grid(True, axis="y", alpha=0.3)

        # I/O operations count chart
        ax2.bar(
            x - width / 2,
            io_read_count,
            width,
            label="Read Ops",
            color="lightblue",
            edgecolor="black",
        )
        ax2.bar(
            x + width / 2,
            io_write_count,
            width,
            label="Write Ops",
            color="lightcoral",
            edgecolor="black",
        )

        ax2.set_ylabel("Operation Count")
        ax2.set_title("I/O Operations Count by Node")
        ax2.set_xticks(x)
        ax2.set_xticklabels(node_names, rotation=45, ha="right")
        ax2.legend()
        ax2.grid(True, axis="y", alpha=0.3)

        plt.suptitle("I/O Operations Analysis", fontsize=14)
        plt.tight_layout()
        plt.savefig(output_path, dpi=150, bbox_inches="tight")
        plt.close()

        return output_path

    def _create_performance_heatmap(
        self, tasks: List[TaskRun], output_path: Path
    ) -> Path:
        """Create performance metrics heatmap."""
        # Prepare data matrix
        metrics_data = []
        node_labels = []

        metric_names = [
            "Duration (s)",
            "CPU %",
            "Memory (MB)",
            "I/O Read (MB)",
            "I/O Write (MB)",
        ]

        for task in tasks:
            if task.metrics:
                node_labels.append(f"{task.node_id}")
                custom = task.metrics.custom_metrics or {}

                row = [
                    task.metrics.duration or 0,
                    task.metrics.cpu_usage or 0,
                    task.metrics.memory_usage_mb or 0,
                    custom.get("io_read_bytes", 0) / 1024 / 1024,
                    custom.get("io_write_bytes", 0) / 1024 / 1024,
                ]
                metrics_data.append(row)

        if not metrics_data:
            fig, ax = plt.subplots(figsize=(8, 6))
            ax.text(
                0.5,
                0.5,
                "No metrics data available",
                ha="center",
                va="center",
                transform=ax.transAxes,
            )
            plt.savefig(output_path)
            plt.close()
            return output_path

        # Convert to numpy array and normalize
        data = np.array(metrics_data).T

        # Normalize each metric to 0-1 scale
        normalized_data = np.zeros_like(data)
        for i in range(data.shape[0]):
            row_max = data[i].max()
            if row_max > 0:
                normalized_data[i] = data[i] / row_max

        # Create heatmap
        fig, ax = plt.subplots(figsize=(max(10, len(node_labels) * 0.8), 8))

        im = ax.imshow(normalized_data, cmap="YlOrRd", aspect="auto")

        # Set ticks and labels
        ax.set_xticks(np.arange(len(node_labels)))
        ax.set_yticks(np.arange(len(metric_names)))
        ax.set_xticklabels(node_labels, rotation=45, ha="right")
        ax.set_yticklabels(metric_names)

        # Add text annotations
        for i in range(len(metric_names)):
            for j in range(len(node_labels)):
                value = data[i, j]
                color = "white" if normalized_data[i, j] > 0.5 else "black"

                # Format based on metric type
                if i == 0:  # Duration
                    text = f"{value:.2f}"
                elif i == 1:  # CPU %
                    text = f"{value:.1f}%"
                elif i in [2, 3, 4]:  # Memory, I/O
                    text = f"{value:.1f}"

                ax.text(j, i, text, ha="center", va="center", color=color, fontsize=8)

        ax.set_title("Performance Metrics Heatmap\n(Normalized by metric type)", pad=20)

        # Add colorbar
        cbar = plt.colorbar(im, ax=ax)
        cbar.set_label("Normalized Value (0-1)", rotation=270, labelpad=20)

        plt.tight_layout()
        plt.savefig(output_path, dpi=150, bbox_inches="tight")
        plt.close()

        return output_path

    def _create_performance_report(
        self, run: Any, tasks: List[TaskRun], output_path: Path
    ) -> Path:
        """Create markdown performance report."""
        lines = []
        lines.append(f"# Performance Report for Run {run.run_id}")
        lines.append(f"\n**Workflow:** {run.workflow_name}")
        lines.append(f"**Started:** {run.started_at}")
        lines.append(f"**Status:** {run.status}")
        lines.append(f"**Total Tasks:** {len(tasks)}")

        # Calculate summary statistics
        completed_tasks = [
            t for t in tasks if t.status == TaskStatus.COMPLETED and t.metrics
        ]

        if completed_tasks:
            total_duration = sum(t.metrics.duration or 0 for t in completed_tasks)
            avg_cpu = np.mean([t.metrics.cpu_usage or 0 for t in completed_tasks])
            max_memory = max((t.metrics.memory_usage_mb or 0) for t in completed_tasks)

            lines.append("\n## Summary Statistics")
            lines.append(f"- **Total Execution Time:** {total_duration:.2f} seconds")
            lines.append(f"- **Average CPU Usage:** {avg_cpu:.1f}%")
            lines.append(f"- **Peak Memory Usage:** {max_memory:.1f} MB")

        # Task details table
        lines.append("\n## Task Performance Details")
        lines.append("| Node ID | Type | Status | Duration (s) | CPU % | Memory (MB) |")
        lines.append("|---------|------|--------|-------------|-------|-------------|")

        for task in tasks:
            duration = (
                f"{task.metrics.duration:.2f}"
                if task.metrics and task.metrics.duration
                else "N/A"
            )
            cpu = (
                f"{task.metrics.cpu_usage:.1f}"
                if task.metrics and task.metrics.cpu_usage
                else "N/A"
            )
            memory = (
                f"{task.metrics.memory_usage_mb:.1f}"
                if task.metrics and task.metrics.memory_usage_mb
                else "N/A"
            )

            lines.append(
                f"| {task.node_id} | {task.node_type} | {task.status} | "
                f"{duration} | {cpu} | {memory} |"
            )

        # Performance insights
        lines.append("\n## Performance Insights")

        if completed_tasks:
            # Find bottlenecks
            slowest = max(completed_tasks, key=lambda t: t.metrics.duration or 0)
            lines.append("\n### Bottlenecks")
            lines.append(
                f"- **Slowest Node:** {slowest.node_id} ({slowest.metrics.duration:.2f}s)"
            )

            highest_cpu = max(completed_tasks, key=lambda t: t.metrics.cpu_usage or 0)
            if highest_cpu.metrics.cpu_usage > 80:
                lines.append(
                    f"- **High CPU Usage:** {highest_cpu.node_id} ({highest_cpu.metrics.cpu_usage:.1f}%)"
                )

            highest_memory = max(
                completed_tasks, key=lambda t: t.metrics.memory_usage_mb or 0
            )
            lines.append(
                f"- **Highest Memory:** {highest_memory.node_id} ({highest_memory.metrics.memory_usage_mb:.1f} MB)"
            )

        # Write report
        with open(output_path, "w") as f:
            f.write("\n".join(lines))

        return output_path

    def compare_runs(
        self, run_ids: List[str], output_path: Optional[Path] = None
    ) -> Path:
        """Compare performance across multiple runs."""
        if output_path is None:
            output_path = Path.cwd() / "outputs" / "performance" / "comparison.png"
        output_path.parent.mkdir(parents=True, exist_ok=True)

        fig, axes = plt.subplots(2, 2, figsize=(15, 12))
        axes = axes.flatten()

        # Collect metrics for each run
        run_metrics = {}
        for run_id in run_ids:
            tasks = self.task_manager.get_run_tasks(run_id)
            completed = [
                t for t in tasks if t.status == TaskStatus.COMPLETED and t.metrics
            ]

            if completed:
                run_metrics[run_id] = {
                    "total_duration": sum(t.metrics.duration or 0 for t in completed),
                    "avg_cpu": np.mean([t.metrics.cpu_usage or 0 for t in completed]),
                    "max_memory": max(
                        (t.metrics.memory_usage_mb or 0) for t in completed
                    ),
                    "task_count": len(completed),
                }

        if not run_metrics:
            for ax in axes:
                ax.text(
                    0.5,
                    0.5,
                    "No metrics data available",
                    ha="center",
                    va="center",
                    transform=ax.transAxes,
                )
            plt.savefig(output_path)
            plt.close()
            return output_path

        # Create comparison charts
        run_labels = list(run_metrics.keys())
        x = np.arange(len(run_labels))

        # Total duration
        durations = [run_metrics[r]["total_duration"] for r in run_labels]
        axes[0].bar(x, durations, color="lightblue", edgecolor="black")
        axes[0].set_ylabel("Total Duration (s)")
        axes[0].set_title("Total Execution Time")
        axes[0].set_xticks(x)
        axes[0].set_xticklabels(run_labels, rotation=45, ha="right")
        axes[0].grid(True, axis="y", alpha=0.3)

        # Average CPU
        cpu_avgs = [run_metrics[r]["avg_cpu"] for r in run_labels]
        axes[1].bar(x, cpu_avgs, color="lightgreen", edgecolor="black")
        axes[1].set_ylabel("Average CPU %")
        axes[1].set_title("Average CPU Usage")
        axes[1].set_xticks(x)
        axes[1].set_xticklabels(run_labels, rotation=45, ha="right")
        axes[1].grid(True, axis="y", alpha=0.3)

        # Max memory
        max_memories = [run_metrics[r]["max_memory"] for r in run_labels]
        axes[2].bar(x, max_memories, color="lightcoral", edgecolor="black")
        axes[2].set_ylabel("Peak Memory (MB)")
        axes[2].set_title("Peak Memory Usage")
        axes[2].set_xticks(x)
        axes[2].set_xticklabels(run_labels, rotation=45, ha="right")
        axes[2].grid(True, axis="y", alpha=0.3)

        # Task efficiency (duration per task)
        efficiencies = [
            run_metrics[r]["total_duration"] / run_metrics[r]["task_count"]
            for r in run_labels
        ]
        axes[3].bar(x, efficiencies, color="lightyellow", edgecolor="black")
        axes[3].set_ylabel("Avg Duration per Task (s)")
        axes[3].set_title("Task Efficiency")
        axes[3].set_xticks(x)
        axes[3].set_xticklabels(run_labels, rotation=45, ha="right")
        axes[3].grid(True, axis="y", alpha=0.3)

        plt.suptitle("Performance Comparison Across Runs", fontsize=16)
        plt.tight_layout()
        plt.savefig(output_path, dpi=150, bbox_inches="tight")
        plt.close()

        return output_path

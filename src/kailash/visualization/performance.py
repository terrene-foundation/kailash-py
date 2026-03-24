"""Performance visualization for task tracking metrics.

Generates Markdown reports with tables and Mermaid charts.
No external dependencies required.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from kailash._math_utils import mean
from kailash.tracking.manager import TaskManager
from kailash.tracking.models import TaskRun, TaskStatus

logger = logging.getLogger(__name__)


class PerformanceVisualizer:
    """Creates performance reports from task execution metrics.

    Generates Markdown with tables and Mermaid bar charts — renders natively
    in GitHub, VS Code, JetBrains, and any Markdown viewer.
    """

    def __init__(self, task_manager: TaskManager):
        self.task_manager = task_manager

    def create_run_performance_summary(
        self, run_id: str, output_dir: Path | None = None
    ) -> dict[str, Path]:
        if output_dir is None:
            project_root = Path(__file__).parent.parent.parent.parent
            output_dir = (
                project_root / "data" / "outputs" / "visualizations" / "performance"
            )
        output_dir.mkdir(parents=True, exist_ok=True)

        run = self.task_manager.get_run(run_id)
        if not run:
            raise ValueError(f"Run {run_id} not found")

        tasks = self.task_manager.get_run_tasks(run_id)
        if not tasks:
            logger.warning(f"No tasks found for run {run_id}")
            return {}

        report_path = output_dir / f"report_{run_id}.md"
        self._create_performance_report(run, tasks, report_path)
        return {"report": report_path}

    def _create_performance_report(
        self, run: Any, tasks: list[TaskRun], output_path: Path
    ) -> Path:
        lines = []
        lines.append(f"# Performance Report — Run `{run.run_id}`\n")
        lines.append(f"**Workflow:** {run.workflow_name}")
        lines.append(f"**Started:** {run.started_at}")
        lines.append(f"**Status:** {run.status}")
        lines.append(f"**Total Tasks:** {len(tasks)}\n")

        completed = [t for t in tasks if t.status == TaskStatus.COMPLETED and t.metrics]

        if completed:
            total_duration = sum(
                (t.metrics.duration or 0) for t in completed if t.metrics is not None
            )
            avg_cpu = mean(
                [(t.metrics.cpu_usage or 0) for t in completed if t.metrics is not None]
            )
            max_memory = max(
                (t.metrics.memory_usage_mb or 0)
                for t in completed
                if t.metrics is not None
            )

            lines.append("## Summary\n")
            lines.append(f"| Metric | Value |")
            lines.append(f"|--------|-------|")
            lines.append(f"| Total Execution Time | {total_duration:.2f}s |")
            lines.append(f"| Average CPU Usage | {avg_cpu:.1f}% |")
            lines.append(f"| Peak Memory Usage | {max_memory:.1f} MB |")
            lines.append("")

        # Execution timeline as Mermaid Gantt
        timed_tasks = [t for t in tasks if t.started_at and t.ended_at]
        if timed_tasks:
            timed_tasks.sort(key=lambda t: t.started_at or datetime.min)
            lines.append("## Execution Timeline\n")
            lines.append("```mermaid")
            lines.append("gantt")
            lines.append("    dateFormat X")
            lines.append("    axisFormat %s")
            lines.append(f"    title Task Execution Timeline")

            started_times = [
                t.started_at for t in timed_tasks if t.started_at is not None
            ]
            min_time = min(started_times) if started_times else datetime.min
            for task in timed_tasks:
                if task.started_at is None or task.ended_at is None:
                    continue
                start_s = int((task.started_at - min_time).total_seconds())
                duration_s = max(
                    1, int((task.ended_at - task.started_at).total_seconds())
                )
                status_tag = (
                    "done,"
                    if task.status == TaskStatus.COMPLETED
                    else (
                        "active,"
                        if task.status == TaskStatus.RUNNING
                        else "crit," if task.status == TaskStatus.FAILED else ""
                    )
                )
                lines.append(
                    f"    {task.node_id} :{status_tag} {start_s}, {duration_s}s"
                )

            lines.append("```\n")

        # Task details table
        lines.append("## Task Details\n")
        lines.append("| Node ID | Type | Status | Duration | CPU % | Memory (MB) |")
        lines.append("|---------|------|--------|----------|-------|-------------|")

        for task in tasks:
            duration = (
                f"{task.metrics.duration:.2f}s"
                if task.metrics and task.metrics.duration
                else "—"
            )
            cpu = (
                f"{task.metrics.cpu_usage:.1f}"
                if task.metrics and task.metrics.cpu_usage
                else "—"
            )
            memory = (
                f"{task.metrics.memory_usage_mb:.1f}"
                if task.metrics and task.metrics.memory_usage_mb
                else "—"
            )
            status_icon = {
                "completed": "✅",
                "failed": "❌",
                "running": "🔄",
                "pending": "⏳",
            }.get(str(task.status.value).lower(), str(task.status.value))
            lines.append(
                f"| {task.node_id} | {task.node_type} | {status_icon} | {duration} | {cpu} | {memory} |"
            )

        # Bottleneck analysis
        metriced = [t for t in completed if t.metrics is not None]
        if metriced:
            lines.append("\n## Bottleneck Analysis\n")
            slowest = max(
                metriced, key=lambda t: (t.metrics.duration if t.metrics else 0) or 0
            )
            if slowest.metrics:
                lines.append(
                    f"- **Slowest node:** `{slowest.node_id}` ({slowest.metrics.duration or 0:.2f}s)"
                )

            highest_cpu = max(
                metriced, key=lambda t: (t.metrics.cpu_usage if t.metrics else 0) or 0
            )
            if (
                highest_cpu.metrics
                and highest_cpu.metrics.cpu_usage
                and highest_cpu.metrics.cpu_usage > 80
            ):
                lines.append(
                    f"- **High CPU:** `{highest_cpu.node_id}` ({highest_cpu.metrics.cpu_usage:.1f}%)"
                )

            highest_mem = max(
                metriced,
                key=lambda t: (t.metrics.memory_usage_mb if t.metrics else 0) or 0,
            )
            if highest_mem.metrics:
                lines.append(
                    f"- **Peak memory:** `{highest_mem.node_id}` ({highest_mem.metrics.memory_usage_mb or 0:.1f} MB)"
                )

        output_path.write_text("\n".join(lines))
        return output_path

    def compare_runs(self, run_ids: list[str], output_path: Path | None = None) -> Path:
        if output_path is None:
            project_root = Path(__file__).parent.parent.parent.parent
            output_path = (
                project_root
                / "data"
                / "outputs"
                / "visualizations"
                / "performance"
                / "comparison.md"
            )
        output_path.parent.mkdir(parents=True, exist_ok=True)

        lines = ["# Run Comparison\n"]
        lines.append("| Run ID | Duration (s) | Avg CPU % | Peak Memory (MB) | Tasks |")
        lines.append("|--------|-------------|-----------|------------------|-------|")

        for run_id in run_ids:
            tasks = self.task_manager.get_run_tasks(run_id)
            completed = [
                t for t in tasks if t.status == TaskStatus.COMPLETED and t.metrics
            ]
            if completed:
                total_dur = sum(
                    (t.metrics.duration or 0)
                    for t in completed
                    if t.metrics is not None
                )
                avg_cpu = mean(
                    [
                        (t.metrics.cpu_usage or 0)
                        for t in completed
                        if t.metrics is not None
                    ]
                )
                max_mem = max(
                    (t.metrics.memory_usage_mb or 0)
                    for t in completed
                    if t.metrics is not None
                )
                lines.append(
                    f"| `{run_id}` | {total_dur:.2f} | {avg_cpu:.1f} | {max_mem:.1f} | {len(completed)} |"
                )
            else:
                lines.append(f"| `{run_id}` | — | — | — | 0 |")

        output_path.write_text("\n".join(lines))
        return output_path

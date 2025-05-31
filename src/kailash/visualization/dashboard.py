"""Real-time dashboard components for workflow monitoring.

This module provides comprehensive dashboard components for real-time monitoring
of workflow execution, performance metrics, and task tracking.

Design Purpose:
- Enable real-time monitoring of workflow execution progress
- Provide interactive visualizations for performance metrics
- Support both live streaming and historical analysis
- Generate embeddable dashboard components for web interfaces

Upstream Dependencies:
- TaskManager provides real-time task execution data
- MetricsCollector provides performance metrics
- PerformanceVisualizer provides static chart generation

Downstream Consumers:
- Web dashboard interfaces embed these components
- CLI tools use dashboard for real-time monitoring
- Export utilities include dashboard snapshots in reports
"""

import json
import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import numpy as np

from kailash.tracking.manager import TaskManager
from kailash.tracking.models import TaskStatus
from kailash.visualization.performance import PerformanceVisualizer

logger = logging.getLogger(__name__)


@dataclass
class DashboardConfig:
    """Configuration for dashboard components.

    Attributes:
        update_interval: Seconds between dashboard updates
        max_history_points: Maximum data points to keep in memory
        auto_refresh: Whether to automatically refresh data
        show_completed: Whether to show completed tasks
        show_failed: Whether to show failed tasks
        theme: Dashboard color theme ('light' or 'dark')
    """

    update_interval: float = 1.0
    max_history_points: int = 100
    auto_refresh: bool = True
    show_completed: bool = True
    show_failed: bool = True
    theme: str = "light"


@dataclass
class LiveMetrics:
    """Container for live performance metrics.

    Attributes:
        timestamp: When metrics were collected
        active_tasks: Number of currently running tasks
        completed_tasks: Number of completed tasks
        failed_tasks: Number of failed tasks
        total_cpu_usage: System-wide CPU usage percentage
        total_memory_usage: System-wide memory usage in MB
        throughput: Tasks completed per minute
        avg_task_duration: Average task execution time
    """

    timestamp: datetime = field(default_factory=datetime.now)
    active_tasks: int = 0
    completed_tasks: int = 0
    failed_tasks: int = 0
    total_cpu_usage: float = 0.0
    total_memory_usage: float = 0.0
    throughput: float = 0.0
    avg_task_duration: float = 0.0


class RealTimeDashboard:
    """Real-time dashboard for workflow monitoring.

    This class provides comprehensive real-time monitoring capabilities
    including live metrics collection, interactive visualizations, and
    status reporting for workflow execution.

    Usage:
        dashboard = RealTimeDashboard(task_manager)
        dashboard.start_monitoring()
        # Dashboard runs in background
        dashboard.generate_live_report("output.html")
        dashboard.stop_monitoring()
    """

    def __init__(
        self, task_manager: TaskManager, config: Optional[DashboardConfig] = None
    ):
        """Initialize real-time dashboard.

        Args:
            task_manager: TaskManager instance for data access
            config: Dashboard configuration options
        """
        self.task_manager = task_manager
        self.config = config or DashboardConfig()
        self.performance_viz = PerformanceVisualizer(task_manager)

        # Live monitoring state
        self._monitoring = False
        self._monitor_thread: Optional[threading.Thread] = None
        self._metrics_history: List[LiveMetrics] = []
        self._current_run_id: Optional[str] = None

        # Event callbacks
        self._status_callbacks: List[callable] = []
        self._metrics_callbacks: List[callable] = []

        self.logger = logger

    def start_monitoring(self, run_id: Optional[str] = None):
        """Start real-time monitoring for a workflow run.

        Args:
            run_id: Specific run to monitor, or None for latest
        """
        if self._monitoring:
            self.logger.warning("Monitoring already active")
            return

        self._current_run_id = run_id
        self._monitoring = True
        self._metrics_history.clear()

        # Start monitoring thread
        self._monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._monitor_thread.start()

        self.logger.info(f"Started monitoring for run: {run_id or 'latest'}")

    def stop_monitoring(self):
        """Stop real-time monitoring."""
        if not self._monitoring:
            return

        self._monitoring = False
        if self._monitor_thread:
            self._monitor_thread.join(timeout=5.0)

        self.logger.info("Stopped monitoring")

    def _monitor_loop(self):
        """Main monitoring loop running in background thread."""
        while self._monitoring:
            try:
                # Collect current metrics
                metrics = self._collect_live_metrics()

                # Update history
                self._metrics_history.append(metrics)
                if len(self._metrics_history) > self.config.max_history_points:
                    self._metrics_history.pop(0)

                # Trigger callbacks
                for callback in self._metrics_callbacks:
                    try:
                        callback(metrics)
                    except Exception as e:
                        self.logger.warning(f"Metrics callback failed: {e}")

                # Check for status changes
                self._check_status_changes()

                time.sleep(self.config.update_interval)

            except Exception as e:
                self.logger.error(f"Monitoring loop error: {e}")
                time.sleep(self.config.update_interval)

    def _collect_live_metrics(self) -> LiveMetrics:
        """Collect current performance metrics."""
        metrics = LiveMetrics()

        try:
            # Get current run tasks
            if self._current_run_id:
                tasks = self.task_manager.get_run_tasks(self._current_run_id)
            else:
                # Get tasks from most recent run
                recent_runs = self.task_manager.list_runs()
                if recent_runs:
                    # Get the most recent run (first in list)
                    tasks = self.task_manager.get_run_tasks(recent_runs[0].run_id)
                else:
                    tasks = []

            # Count task statuses
            metrics.active_tasks = sum(
                1 for t in tasks if t.status == TaskStatus.RUNNING
            )
            metrics.completed_tasks = sum(
                1 for t in tasks if t.status == TaskStatus.COMPLETED
            )
            metrics.failed_tasks = sum(
                1 for t in tasks if t.status == TaskStatus.FAILED
            )

            # Calculate performance metrics
            completed = [
                t for t in tasks if t.status == TaskStatus.COMPLETED and t.metrics
            ]

            if completed:
                # CPU and memory aggregation
                cpu_values = [
                    t.metrics.cpu_usage for t in completed if t.metrics.cpu_usage
                ]
                memory_values = [
                    t.metrics.memory_usage_mb
                    for t in completed
                    if t.metrics.memory_usage_mb
                ]
                duration_values = [
                    t.metrics.duration for t in completed if t.metrics.duration
                ]

                if cpu_values:
                    metrics.total_cpu_usage = np.mean(cpu_values)
                if memory_values:
                    metrics.total_memory_usage = sum(memory_values)
                if duration_values:
                    metrics.avg_task_duration = np.mean(duration_values)

                # Calculate throughput (tasks/minute)
                if len(self._metrics_history) > 1:
                    prev_completed = self._metrics_history[-1].completed_tasks
                    time_diff = (
                        metrics.timestamp - self._metrics_history[-1].timestamp
                    ).total_seconds() / 60
                    if time_diff > 0:
                        metrics.throughput = (
                            metrics.completed_tasks - prev_completed
                        ) / time_diff

        except Exception as e:
            self.logger.warning(f"Failed to collect metrics: {e}")

        return metrics

    def _check_status_changes(self):
        """Check for significant status changes and trigger callbacks."""
        if len(self._metrics_history) < 2:
            return

        current = self._metrics_history[-1]
        previous = self._metrics_history[-2]

        # Check for task completion or failure
        if current.completed_tasks > previous.completed_tasks:
            for callback in self._status_callbacks:
                try:
                    callback(
                        "task_completed",
                        current.completed_tasks - previous.completed_tasks,
                    )
                except Exception as e:
                    self.logger.warning(f"Status callback failed: {e}")

        if current.failed_tasks > previous.failed_tasks:
            for callback in self._status_callbacks:
                try:
                    callback(
                        "task_failed", current.failed_tasks - previous.failed_tasks
                    )
                except Exception as e:
                    self.logger.warning(f"Status callback failed: {e}")

    def add_metrics_callback(self, callback: callable):
        """Add callback for metrics updates.

        Args:
            callback: Function that takes LiveMetrics as argument
        """
        self._metrics_callbacks.append(callback)

    def add_status_callback(self, callback: callable):
        """Add callback for status changes.

        Args:
            callback: Function that takes (event_type, count) as arguments
        """
        self._status_callbacks.append(callback)

    def get_current_metrics(self) -> Optional[LiveMetrics]:
        """Get the most recent metrics."""
        return self._metrics_history[-1] if self._metrics_history else None

    def get_metrics_history(self, minutes: Optional[int] = None) -> List[LiveMetrics]:
        """Get metrics history for specified time period.

        Args:
            minutes: Number of minutes of history to return

        Returns:
            List of metrics within time period
        """
        if minutes is None:
            return self._metrics_history.copy()

        cutoff = datetime.now() - timedelta(minutes=minutes)
        return [m for m in self._metrics_history if m.timestamp >= cutoff]

    def generate_live_report(
        self, output_path: Union[str, Path], include_charts: bool = True
    ) -> Path:
        """Generate comprehensive live dashboard report.

        Args:
            output_path: Path to save HTML dashboard
            include_charts: Whether to include performance charts

        Returns:
            Path to generated dashboard file
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Generate dashboard HTML
        html_content = self._generate_dashboard_html(include_charts)

        with open(output_path, "w") as f:
            f.write(html_content)

        self.logger.info(f"Generated live dashboard: {output_path}")
        return output_path

    def _generate_dashboard_html(self, include_charts: bool = True) -> str:
        """Generate HTML content for dashboard."""
        current_metrics = self.get_current_metrics()
        metrics_history = self.get_metrics_history(minutes=30)  # Last 30 minutes

        # Basic status info
        status_section = self._generate_status_section(current_metrics)

        # Live metrics section
        live_metrics_section = self._generate_live_metrics_section(metrics_history)

        # Charts section (if requested)
        charts_section = ""
        if include_charts and self._current_run_id:
            charts_section = self._generate_charts_section()

        # Task list section
        task_list_section = self._generate_task_list_section()

        # Combine all sections
        html_template = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Real-time Workflow Dashboard</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        {self._get_dashboard_css()}
    </style>
    <script>
        {self._get_dashboard_javascript()}
    </script>
</head>
<body>
    <div class="dashboard-container">
        <header class="dashboard-header">
            <h1>🚀 Workflow Dashboard</h1>
            <div class="status-indicator">
                <span class="{'status-active' if self._monitoring else 'status-inactive'}">
                    {'🟢 Live Monitoring' if self._monitoring else '🔴 Monitoring Stopped'}
                </span>
            </div>
        </header>

        {status_section}
        {live_metrics_section}
        {charts_section}
        {task_list_section}
    </div>
</body>
</html>
        """

        return html_template

    def _generate_status_section(self, metrics: Optional[LiveMetrics]) -> str:
        """Generate status overview section."""
        if not metrics:
            return """
            <section class="status-section">
                <h2>📊 Current Status</h2>
                <div class="status-grid">
                    <div class="status-card">
                        <span class="status-label">No Data Available</span>
                    </div>
                </div>
            </section>
            """

        return f"""
        <section class="status-section">
            <h2>📊 Current Status</h2>
            <div class="status-grid">
                <div class="status-card">
                    <span class="status-value">{metrics.active_tasks}</span>
                    <span class="status-label">Active Tasks</span>
                </div>
                <div class="status-card">
                    <span class="status-value">{metrics.completed_tasks}</span>
                    <span class="status-label">Completed</span>
                </div>
                <div class="status-card">
                    <span class="status-value">{metrics.failed_tasks}</span>
                    <span class="status-label">Failed</span>
                </div>
                <div class="status-card">
                    <span class="status-value">{metrics.throughput:.1f}</span>
                    <span class="status-label">Tasks/Min</span>
                </div>
                <div class="status-card">
                    <span class="status-value">{metrics.total_cpu_usage:.1f}%</span>
                    <span class="status-label">Avg CPU</span>
                </div>
                <div class="status-card">
                    <span class="status-value">{metrics.total_memory_usage:.0f}MB</span>
                    <span class="status-label">Total Memory</span>
                </div>
            </div>
        </section>
        """

    def _generate_live_metrics_section(self, history: List[LiveMetrics]) -> str:
        """Generate live metrics charts section."""
        if not history:
            return """
            <section class="metrics-section">
                <h2>📈 Live Metrics</h2>
                <p>No metrics data available</p>
            </section>
            """

        # Prepare data for charts
        timestamps = [m.timestamp.strftime("%H:%M:%S") for m in history]
        cpu_data = [m.total_cpu_usage for m in history]
        memory_data = [m.total_memory_usage for m in history]
        throughput_data = [m.throughput for m in history]

        return f"""
        <section class="metrics-section">
            <h2>📈 Live Metrics (Last 30 minutes)</h2>
            <div class="charts-grid">
                <div class="chart-container">
                    <h3>CPU Usage</h3>
                    <canvas id="cpuChart"></canvas>
                </div>
                <div class="chart-container">
                    <h3>Memory Usage</h3>
                    <canvas id="memoryChart"></canvas>
                </div>
                <div class="chart-container">
                    <h3>Throughput</h3>
                    <canvas id="throughputChart"></canvas>
                </div>
            </div>
            <script>
                drawLiveCharts({json.dumps(timestamps)}, {json.dumps(cpu_data)},
                              {json.dumps(memory_data)}, {json.dumps(throughput_data)});
            </script>
        </section>
        """

    def _generate_charts_section(self) -> str:
        """Generate performance charts section."""
        if not self._current_run_id:
            return ""

        return f"""
        <section class="charts-section">
            <h2>📊 Performance Analysis</h2>
            <div class="charts-grid">
                <div class="chart-item">
                    <h3>Execution Timeline</h3>
                    <img src="timeline_{self._current_run_id}.png" alt="Timeline" class="chart-image">
                </div>
                <div class="chart-item">
                    <h3>Resource Usage</h3>
                    <img src="resources_{self._current_run_id}.png" alt="Resources" class="chart-image">
                </div>
                <div class="chart-item">
                    <h3>Performance Heatmap</h3>
                    <img src="heatmap_{self._current_run_id}.png" alt="Heatmap" class="chart-image">
                </div>
            </div>
        </section>
        """

    def _generate_task_list_section(self) -> str:
        """Generate task list section."""
        if not self._current_run_id:
            return """
            <section class="tasks-section">
                <h2>📋 Recent Tasks</h2>
                <p>No active workflow</p>
            </section>
            """

        tasks = self.task_manager.get_run_tasks(self._current_run_id)
        recent_tasks = sorted(
            tasks, key=lambda t: t.started_at or datetime.min, reverse=True
        )[:10]

        task_rows = ""
        for task in recent_tasks:
            status_class = {
                TaskStatus.RUNNING: "status-running",
                TaskStatus.COMPLETED: "status-completed",
                TaskStatus.FAILED: "status-failed",
                TaskStatus.PENDING: "status-pending",
            }.get(task.status, "status-unknown")

            duration = ""
            if task.metrics and task.metrics.duration:
                duration = f"{task.metrics.duration:.2f}s"

            task_rows += f"""
            <tr class="{status_class}">
                <td>{task.node_id}</td>
                <td>{task.node_type}</td>
                <td><span class="status-badge {status_class}">{task.status}</span></td>
                <td>{duration}</td>
                <td>{task.started_at.strftime('%H:%M:%S') if task.started_at else 'N/A'}</td>
            </tr>
            """

        return f"""
        <section class="tasks-section">
            <h2>📋 Recent Tasks</h2>
            <table class="tasks-table">
                <thead>
                    <tr>
                        <th>Node ID</th>
                        <th>Type</th>
                        <th>Status</th>
                        <th>Duration</th>
                        <th>Started</th>
                    </tr>
                </thead>
                <tbody>
                    {task_rows}
                </tbody>
            </table>
        </section>
        """

    def _get_dashboard_css(self) -> str:
        """Get CSS styles for dashboard."""
        theme_colors = {
            "light": {
                "bg": "#f8f9fa",
                "card_bg": "#ffffff",
                "text": "#333333",
                "border": "#e9ecef",
                "primary": "#007bff",
                "success": "#28a745",
                "danger": "#dc3545",
                "warning": "#ffc107",
            },
            "dark": {
                "bg": "#121212",
                "card_bg": "#1e1e1e",
                "text": "#ffffff",
                "border": "#333333",
                "primary": "#1976d2",
                "success": "#4caf50",
                "danger": "#f44336",
                "warning": "#ff9800",
            },
        }

        colors = theme_colors[self.config.theme]

        return f"""
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background-color: {colors['bg']};
            color: {colors['text']};
            line-height: 1.6;
        }}

        .dashboard-container {{
            max-width: 1400px;
            margin: 0 auto;
            padding: 20px;
        }}

        .dashboard-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 30px;
            padding: 20px;
            background: {colors['card_bg']};
            border-radius: 8px;
            border: 1px solid {colors['border']};
        }}

        .dashboard-header h1 {{
            color: {colors['primary']};
            font-size: 2em;
        }}

        .status-indicator {{
            font-weight: bold;
        }}

        .status-active {{
            color: {colors['success']};
        }}

        .status-inactive {{
            color: {colors['danger']};
        }}

        section {{
            margin-bottom: 30px;
            padding: 20px;
            background: {colors['card_bg']};
            border-radius: 8px;
            border: 1px solid {colors['border']};
        }}

        section h2 {{
            margin-bottom: 20px;
            color: {colors['primary']};
            font-size: 1.5em;
        }}

        .status-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 15px;
        }}

        .status-card {{
            text-align: center;
            padding: 20px;
            background: {colors['bg']};
            border-radius: 6px;
            border: 1px solid {colors['border']};
        }}

        .status-value {{
            display: block;
            font-size: 2em;
            font-weight: bold;
            color: {colors['primary']};
        }}

        .status-label {{
            display: block;
            font-size: 0.9em;
            color: {colors['text']};
            opacity: 0.8;
        }}

        .charts-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
            gap: 20px;
        }}

        .chart-container, .chart-item {{
            padding: 15px;
            background: {colors['bg']};
            border-radius: 6px;
            border: 1px solid {colors['border']};
        }}

        .chart-container h3, .chart-item h3 {{
            margin-bottom: 10px;
            color: {colors['text']};
        }}

        .chart-image {{
            max-width: 100%;
            height: auto;
            border-radius: 4px;
        }}

        .tasks-table {{
            width: 100%;
            border-collapse: collapse;
        }}

        .tasks-table th,
        .tasks-table td {{
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid {colors['border']};
        }}

        .tasks-table th {{
            background: {colors['bg']};
            font-weight: bold;
        }}

        .status-badge {{
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 0.8em;
            font-weight: bold;
            text-transform: uppercase;
        }}

        .status-running {{
            background: {colors['primary']};
            color: white;
        }}

        .status-completed {{
            background: {colors['success']};
            color: white;
        }}

        .status-failed {{
            background: {colors['danger']};
            color: white;
        }}

        .status-pending {{
            background: {colors['warning']};
            color: black;
        }}

        canvas {{
            max-width: 100%;
            height: 200px;
        }}
        """

    def _get_dashboard_javascript(self) -> str:
        """Get JavaScript for dashboard functionality."""
        return """
        function drawLiveCharts(timestamps, cpuData, memoryData, throughputData) {
            // Simple canvas-based charts (replace with Chart.js or similar for production)
            drawSimpleChart('cpuChart', timestamps, cpuData, 'CPU %', '#007bff');
            drawSimpleChart('memoryChart', timestamps, memoryData, 'Memory MB', '#28a745');
            drawSimpleChart('throughputChart', timestamps, throughputData, 'Tasks/Min', '#ffc107');
        }

        function drawSimpleChart(canvasId, labels, data, label, color) {
            const canvas = document.getElementById(canvasId);
            if (!canvas) return;

            const ctx = canvas.getContext('2d');
            const width = canvas.width = canvas.offsetWidth;
            const height = canvas.height = 200;

            // Clear canvas
            ctx.clearRect(0, 0, width, height);

            if (data.length === 0) {
                ctx.fillStyle = '#666';
                ctx.font = '14px Arial';
                ctx.textAlign = 'center';
                ctx.fillText('No data available', width/2, height/2);
                return;
            }

            // Calculate scales
            const maxValue = Math.max(...data, 1);
            const padding = 40;
            const chartWidth = width - 2 * padding;
            const chartHeight = height - 2 * padding;

            // Draw axes
            ctx.strokeStyle = '#ddd';
            ctx.lineWidth = 1;
            ctx.beginPath();
            ctx.moveTo(padding, padding);
            ctx.lineTo(padding, height - padding);
            ctx.lineTo(width - padding, height - padding);
            ctx.stroke();

            // Draw data line
            if (data.length > 1) {
                ctx.strokeStyle = color;
                ctx.lineWidth = 2;
                ctx.beginPath();

                for (let i = 0; i < data.length; i++) {
                    const x = padding + (i / (data.length - 1)) * chartWidth;
                    const y = height - padding - (data[i] / maxValue) * chartHeight;

                    if (i === 0) {
                        ctx.moveTo(x, y);
                    } else {
                        ctx.lineTo(x, y);
                    }
                }
                ctx.stroke();

                // Draw data points
                ctx.fillStyle = color;
                for (let i = 0; i < data.length; i++) {
                    const x = padding + (i / (data.length - 1)) * chartWidth;
                    const y = height - padding - (data[i] / maxValue) * chartHeight;

                    ctx.beginPath();
                    ctx.arc(x, y, 3, 0, 2 * Math.PI);
                    ctx.fill();
                }
            }

            // Draw labels
            ctx.fillStyle = '#666';
            ctx.font = '12px Arial';
            ctx.textAlign = 'center';
            ctx.fillText(`Max: ${maxValue.toFixed(1)}`, width - 60, padding + 15);
            ctx.fillText('0', padding - 20, height - padding + 5);
        }

        // Auto-refresh functionality
        setInterval(function() {
            if (window.location.hash !== '#no-refresh') {
                window.location.reload();
            }
        }, 30000); // Refresh every 30 seconds
        """


class DashboardExporter:
    """Utility class for exporting dashboard data and reports."""

    def __init__(self, dashboard: RealTimeDashboard):
        """Initialize dashboard exporter.

        Args:
            dashboard: RealTimeDashboard instance
        """
        self.dashboard = dashboard
        self.logger = logger

    def export_metrics_json(self, output_path: Union[str, Path]) -> Path:
        """Export current metrics as JSON.

        Args:
            output_path: Path to save JSON file

        Returns:
            Path to exported file
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Get current data
        current_metrics = self.dashboard.get_current_metrics()
        metrics_history = self.dashboard.get_metrics_history()

        data = {
            "timestamp": datetime.now().isoformat(),
            "current_metrics": (
                self._metrics_to_dict(current_metrics) if current_metrics else None
            ),
            "history": [self._metrics_to_dict(m) for m in metrics_history],
            "config": {
                "update_interval": self.dashboard.config.update_interval,
                "theme": self.dashboard.config.theme,
                "monitoring_active": self.dashboard._monitoring,
            },
        }

        with open(output_path, "w") as f:
            json.dump(data, f, indent=2, default=str)

        self.logger.info(f"Exported metrics to: {output_path}")
        return output_path

    def _metrics_to_dict(self, metrics: LiveMetrics) -> Dict[str, Any]:
        """Convert LiveMetrics to dictionary."""
        return {
            "timestamp": metrics.timestamp.isoformat(),
            "active_tasks": metrics.active_tasks,
            "completed_tasks": metrics.completed_tasks,
            "failed_tasks": metrics.failed_tasks,
            "total_cpu_usage": metrics.total_cpu_usage,
            "total_memory_usage": metrics.total_memory_usage,
            "throughput": metrics.throughput,
            "avg_task_duration": metrics.avg_task_duration,
        }

    def create_dashboard_snapshot(
        self, output_dir: Union[str, Path], include_static_charts: bool = True
    ) -> Dict[str, Path]:
        """Create complete dashboard snapshot with all assets.

        Args:
            output_dir: Directory to save snapshot
            include_static_charts: Whether to generate static charts

        Returns:
            Dictionary mapping asset names to file paths
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        assets = {}

        # Generate live dashboard HTML
        dashboard_path = output_dir / "dashboard.html"
        self.dashboard.generate_live_report(dashboard_path)
        assets["dashboard"] = dashboard_path

        # Export metrics JSON
        metrics_path = output_dir / "metrics.json"
        self.export_metrics_json(metrics_path)
        assets["metrics"] = metrics_path

        # Generate static performance charts if requested
        if include_static_charts and self.dashboard._current_run_id:
            try:
                chart_outputs = (
                    self.dashboard.performance_viz.create_run_performance_summary(
                        self.dashboard._current_run_id, output_dir
                    )
                )
                assets.update(chart_outputs)
            except Exception as e:
                self.logger.warning(f"Failed to generate static charts: {e}")

        self.logger.info(f"Created dashboard snapshot in: {output_dir}")
        return assets

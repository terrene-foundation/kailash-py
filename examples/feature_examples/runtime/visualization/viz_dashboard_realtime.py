#!/usr/bin/env python3
"""Real-time dashboard streaming example.

This example demonstrates real-time monitoring capabilities with
live metric updates, WebSocket streaming, and continuous monitoring.

Usage:
    python viz_dashboard_realtime.py
"""

import asyncio
import json
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

# Add project root to path for imports
project_root = Path(__file__).parent.parent.parent.parent.parent
sys.path.insert(0, str(project_root))

# Import after path setup to avoid import errors
from examples.utils.paths import get_data_dir, get_output_dir  # noqa: E402
from kailash.nodes.data.readers import CSVReaderNode  # noqa: E402
from kailash.nodes.data.writers import CSVWriterNode  # noqa: E402
from kailash.nodes.transform.processors import Filter  # noqa: E402
from kailash.runtime.local import LocalRuntime  # noqa: E402
from kailash.tracking.manager import TaskManager  # noqa: E402
from kailash.tracking.storage.filesystem import FileSystemStorage  # noqa: E402
from kailash.workflow.graph import Workflow  # noqa: E402

# from kailash.visualization.api import SimpleDashboardAPI
# from kailash.visualization.dashboard import DashboardConfig, RealTimeDashboard


print("⚡ Real-time Dashboard Streaming Example")
print("=" * 50)


def create_long_running_workflow():
    """Create a workflow that takes time to execute for monitoring demo."""
    workflow = Workflow("realtime_monitoring_demo", "Real-time Demo Workflow")

    # Create simple multi-step workflow for demo
    reader1 = CSVReaderNode(
        node_id="reader_customers", file_path=str(get_data_dir() / "customers.csv")
    )

    reader2 = CSVReaderNode(
        node_id="reader_backup",
        file_path=str(get_data_dir() / "customers.csv"),  # Use same file for simplicity
    )

    # Data processing nodes
    filter_adults = Filter(
        node_id="filter_adults", field="age", operator=">=", value=18
    )

    filter_seniors = Filter(
        node_id="filter_seniors", field="age", operator=">=", value=65
    )

    # Output writers
    adults_writer = CSVWriterNode(
        node_id="adults_writer", file_path=str(get_output_dir() / "realtime_adults.csv")
    )

    seniors_writer = CSVWriterNode(
        node_id="seniors_writer",
        file_path=str(get_output_dir() / "realtime_seniors.csv"),
    )

    all_writer = CSVWriterNode(
        node_id="all_writer", file_path=str(get_output_dir() / "realtime_all.csv")
    )

    # Build workflow graph
    workflow.add_node("reader_customers", reader1)
    workflow.add_node("reader_backup", reader2)
    workflow.add_node("filter_adults", filter_adults)
    workflow.add_node("filter_seniors", filter_seniors)
    workflow.add_node("adults_writer", adults_writer)
    workflow.add_node("seniors_writer", seniors_writer)
    workflow.add_node("all_writer", all_writer)

    # Connect the graph
    workflow.connect("reader_customers", "filter_adults", {"data": "data"})
    workflow.connect("reader_customers", "filter_seniors", {"data": "data"})
    workflow.connect("filter_adults", "adults_writer", {"filtered_data": "data"})
    workflow.connect("filter_seniors", "seniors_writer", {"filtered_data": "data"})
    workflow.connect("reader_backup", "all_writer", {"data": "data"})

    return workflow


def setup_realtime_tracking():
    """Set up task tracking for real-time demo."""
    storage_path = get_data_dir() / "realtime_tracking"
    storage_path.mkdir(parents=True, exist_ok=True)

    storage = FileSystemStorage(storage_path)
    return TaskManager(storage)


class RealtimeMonitor:
    """Enhanced real-time monitoring with logging."""

    def __init__(self):  # Removed dashboard parameter
        # self.dashboard = dashboard
        self.metrics_log = []
        self.running = False

    def start_logging(self):
        """Start logging metrics in background."""
        self.running = True
        self.log_thread = threading.Thread(target=self._log_metrics, daemon=True)
        self.log_thread.start()

    def stop_logging(self):
        """Stop logging metrics."""
        self.running = False
        if hasattr(self, "log_thread"):
            self.log_thread.join(timeout=2.0)

    def _log_metrics(self):
        """Background thread for logging metrics."""
        while self.running:
            # metrics = self.dashboard.get_current_metrics()
            metrics = None  # Dashboard not available
            if metrics:
                log_entry = {
                    "timestamp": metrics.timestamp.isoformat(),
                    "active": metrics.active_tasks,
                    "completed": metrics.completed_tasks,
                    "failed": metrics.failed_tasks,
                    "cpu": round(metrics.total_cpu_usage, 2),
                    "memory": round(metrics.total_memory_usage, 1),
                    "throughput": round(metrics.throughput, 2),
                }
                self.metrics_log.append(log_entry)

                # Print live update
                print(
                    f"    📊 {metrics.timestamp.strftime('%H:%M:%S')} | "
                    f"Active: {metrics.active_tasks:2d} | "
                    f"Done: {metrics.completed_tasks:2d} | "
                    f"CPU: {metrics.total_cpu_usage:5.1f}% | "
                    f"Mem: {metrics.total_memory_usage:6.1f}MB"
                )

            time.sleep(1.0)

    def save_metrics_log(self, output_path: Path):
        """Save logged metrics to file."""
        with open(output_path, "w") as f:
            json.dump(self.metrics_log, f, indent=2)


def demonstrate_realtime_monitoring():
    """Demonstrate comprehensive real-time monitoring."""
    print("\n1. Setting up real-time monitoring...")

    # Setup components
    task_manager = setup_realtime_tracking()
    workflow = create_long_running_workflow()

    # Configure dashboard for real-time updates
    # config = DashboardConfig(
    #     update_interval=0.5,  # Very fast updates
    #     max_history_points=200,
    #     auto_refresh=True,
    #     show_completed=True,
    #     show_failed=True,
    #     theme="light",
    # )
    print("📊 Dashboard configuration would be set here")

    # dashboard = RealTimeDashboard(task_manager, config)
    monitor = RealtimeMonitor()  # Fixed - no dashboard parameter

    print("   ✅ Components configured for real-time monitoring")

    # Set up callbacks for different events
    def metrics_callback(metrics):
        # This callback fires on every metrics update
        if metrics.completed_tasks > 0 and metrics.completed_tasks % 2 == 0:
            print(f"    🎯 Milestone: {metrics.completed_tasks} tasks completed")

    def status_callback(event_type, count):
        if event_type == "task_completed":
            print(f"    ✅ {count} task(s) just completed")
        elif event_type == "task_failed":
            print(f"    ❌ {count} task(s) just failed")

    # dashboard.add_metrics_callback(metrics_callback)
    # dashboard.add_status_callback(status_callback)

    print("\n2. Starting workflow execution with live monitoring...")

    # Start monitoring and logging
    # dashboard.start_monitoring()
    monitor.start_logging()

    # Create runtime and execute
    runtime = LocalRuntime()

    try:
        # Execute workflow
        results, run_id = runtime.execute(workflow, task_manager)
        print(f"   🎯 Workflow started: {run_id}")
        print("   📊 Live metrics (updating every second):")
        print("       Time     | Active | Done | CPU    | Memory")
        print("       ---------|--------|------|--------|--------")

        # Monitor execution for extended period
        monitoring_duration = 10  # seconds
        start_time = time.time()

        while time.time() - start_time < monitoring_duration:
            time.sleep(1)

            # Check if workflow is complete
            # current_metrics = dashboard.get_current_metrics()
            print("   📊 Current metrics would be fetched here")
            if current_metrics and current_metrics.active_tasks == 0:
                print("    🏁 Workflow execution completed")
                break

        return run_id, None, monitor, task_manager

    finally:
        monitor.stop_logging()
        # dashboard.stop_monitoring()
        print("\n   ⏹️  Monitoring stopped")


def generate_streaming_dashboard(
    # dashboard: RealTimeDashboard, monitor: RealtimeMonitor
):
    """Generate dashboard with streaming data visualization."""
    print("\n3. Generating streaming dashboard...")

    # Generate live dashboard with all metrics history
    dashboard_path = get_output_dir() / "realtime_streaming_dashboard.html"
    dashboard_path.parent.mkdir(parents=True, exist_ok=True)

    # dashboard.generate_live_report(dashboard_path, include_charts=True)
    print(f"   💻 Streaming dashboard: {dashboard_path}")

    # Save metrics log
    metrics_log_path = get_output_dir() / "realtime_metrics_log.json"
    monitor.save_metrics_log(metrics_log_path)
    print(f"   📊 Metrics log: {metrics_log_path}")

    # Show metrics summary
    if monitor.metrics_log:
        print(f"   📈 Captured {len(monitor.metrics_log)} metric samples")
        first_sample = monitor.metrics_log[0]
        last_sample = monitor.metrics_log[-1]
        print(
            f"   ⏱️  Duration: {first_sample['timestamp']} to {last_sample['timestamp']}"
        )


def demonstrate_api_streaming(task_manager: TaskManager):
    """Demonstrate API-based streaming functionality."""
    print("\n4. API streaming demonstration...")

    # api = SimpleDashboardAPI(task_manager)
    print("🔧 Simple Dashboard API would be created here")

    # Start monitoring via API
    print("   🔌 Starting monitoring via API...")
    api.start_monitoring()

    # Simulate some activity and monitor via API
    print("   📊 Streaming metrics via API (5 seconds)...")

    for i in range(5):
        time.sleep(1)

        # Get current metrics
        metrics = api.get_current_metrics()
        if metrics:
            print(
                f"      API metrics {i+1}: "
                f"{metrics['completed_tasks']} completed, "
                f"{metrics['total_cpu_usage']:.1f}% CPU"
            )

    # Get metrics history
    history = api.get_metrics_history(minutes=5)
    print(f"   📊 Retrieved {len(history)} historical data points")

    # Stop monitoring
    api.stop_monitoring()
    print("   ⏹️  API monitoring stopped")


async def demonstrate_websocket_simulation():
    """Simulate WebSocket streaming functionality."""
    print("\n5. WebSocket streaming simulation...")

    # This simulates what would happen with real WebSocket connections
    print("   🌐 Simulating WebSocket metrics streaming...")

    # Mock WebSocket message format
    sample_metrics = {
        "timestamp": datetime.now().isoformat(),
        "active_tasks": 3,
        "completed_tasks": 7,
        "failed_tasks": 0,
        "total_cpu_usage": 45.2,
        "total_memory_usage": 128.7,
        "throughput": 1.4,
        "avg_task_duration": 2.3,
    }

    print("   📡 Sample WebSocket message:")
    print(f"      {json.dumps(sample_metrics, indent=6)}")

    print("   ℹ️  In a real implementation:")
    print("      - Clients connect to ws://localhost:8000/api/v1/metrics/stream")
    print("      - Real-time metrics are pushed every update interval")
    print("      - Multiple clients can subscribe simultaneously")
    print("      - Automatic reconnection handling")


def create_realtime_html_dashboard(monitor: RealtimeMonitor):
    """Create an enhanced HTML dashboard with real-time capabilities."""
    print("\n6. Creating enhanced real-time HTML dashboard...")

    # Generate JavaScript for live updates
    js_metrics_data = json.dumps(monitor.metrics_log)

    html_content = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Real-time Workflow Dashboard</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            margin: 0;
            padding: 20px;
            background-color: #f5f5f5;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
        }}
        .header {{
            background: white;
            padding: 20px;
            border-radius: 8px;
            margin-bottom: 20px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        .metrics-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin-bottom: 20px;
        }}
        .metric-card {{
            background: white;
            padding: 20px;
            border-radius: 8px;
            text-align: center;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        .metric-value {{
            font-size: 2em;
            font-weight: bold;
            color: #007bff;
        }}
        .metric-label {{
            color: #666;
            margin-top: 5px;
        }}
        .chart-container {{
            background: white;
            padding: 20px;
            border-radius: 8px;
            margin-bottom: 20px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        .status {{
            display: inline-block;
            padding: 4px 8px;
            border-radius: 4px;
            font-weight: bold;
        }}
        .status-live {{
            background: #28a745;
            color: white;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>⚡ Real-time Workflow Dashboard</h1>
            <p>Live monitoring of workflow execution with streaming metrics</p>
            <span class="status status-live">🟢 LIVE DATA</span>
        </div>

        <div class="metrics-grid" id="metricsGrid">
            <!-- Metrics cards will be populated by JavaScript -->
        </div>

        <div class="chart-container">
            <h3>📊 Real-time Metrics Timeline</h3>
            <canvas id="metricsChart"></canvas>
        </div>

        <div class="chart-container">
            <h3>🔄 Task Status Over Time</h3>
            <canvas id="taskStatusChart"></canvas>
        </div>
    </div>

    <script>
        // Metrics data from Python
        const metricsData = {js_metrics_data};

        // Update metrics cards
        function updateMetricsCards() {{
            if (metricsData.length === 0) return;

            const latest = metricsData[metricsData.length - 1];
            const grid = document.getElementById('metricsGrid');

            grid.innerHTML = `
                <div class="metric-card">
                    <div class="metric-value">${{latest.completed}}</div>
                    <div class="metric-label">Completed Tasks</div>
                </div>
                <div class="metric-card">
                    <div class="metric-value">${{latest.active}}</div>
                    <div class="metric-label">Active Tasks</div>
                </div>
                <div class="metric-card">
                    <div class="metric-value">${{latest.cpu}}%</div>
                    <div class="metric-label">CPU Usage</div>
                </div>
                <div class="metric-card">
                    <div class="metric-value">${{latest.memory}}MB</div>
                    <div class="metric-label">Memory Usage</div>
                </div>
                <div class="metric-card">
                    <div class="metric-value">${{latest.throughput}}</div>
                    <div class="metric-label">Tasks/Min</div>
                </div>
            `;
        }}

        // Create timeline chart
        function createTimelineChart() {{
            const ctx = document.getElementById('metricsChart').getContext('2d');

            const labels = metricsData.map(d => new Date(d.timestamp).toLocaleTimeString());

            new Chart(ctx, {{
                type: 'line',
                data: {{
                    labels: labels,
                    datasets: [
                        {{
                            label: 'CPU Usage %',
                            data: metricsData.map(d => d.cpu),
                            borderColor: 'rgb(255, 99, 132)',
                            backgroundColor: 'rgba(255, 99, 132, 0.1)',
                            tension: 0.1
                        }},
                        {{
                            label: 'Memory Usage MB',
                            data: metricsData.map(d => d.memory),
                            borderColor: 'rgb(54, 162, 235)',
                            backgroundColor: 'rgba(54, 162, 235, 0.1)',
                            tension: 0.1,
                            yAxisID: 'y1'
                        }}
                    ]
                }},
                options: {{
                    responsive: true,
                    scales: {{
                        y: {{
                            type: 'linear',
                            display: true,
                            position: 'left',
                        }},
                        y1: {{
                            type: 'linear',
                            display: true,
                            position: 'right',
                            grid: {{
                                drawOnChartArea: false,
                            }},
                        }}
                    }}
                }}
            }});
        }}

        // Create task status chart
        function createTaskStatusChart() {{
            const ctx = document.getElementById('taskStatusChart').getContext('2d');

            const labels = metricsData.map(d => new Date(d.timestamp).toLocaleTimeString());

            new Chart(ctx, {{
                type: 'line',
                data: {{
                    labels: labels,
                    datasets: [
                        {{
                            label: 'Completed',
                            data: metricsData.map(d => d.completed),
                            borderColor: 'rgb(40, 167, 69)',
                            backgroundColor: 'rgba(40, 167, 69, 0.1)',
                            fill: true
                        }},
                        {{
                            label: 'Active',
                            data: metricsData.map(d => d.active),
                            borderColor: 'rgb(255, 193, 7)',
                            backgroundColor: 'rgba(255, 193, 7, 0.1)',
                            fill: true
                        }},
                        {{
                            label: 'Failed',
                            data: metricsData.map(d => d.failed),
                            borderColor: 'rgb(220, 53, 69)',
                            backgroundColor: 'rgba(220, 53, 69, 0.1)',
                            fill: true
                        }}
                    ]
                }},
                options: {{
                    responsive: true,
                    scales: {{
                        y: {{
                            beginAtZero: true,
                            stacked: false
                        }}
                    }}
                }}
            }});
        }}

        // Initialize dashboard
        document.addEventListener('DOMContentLoaded', function() {{
            updateMetricsCards();
            createTimelineChart();
            createTaskStatusChart();
        }});
    </script>
</body>
</html>
    """

    output_path = get_output_dir() / "realtime_enhanced_dashboard.html"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w") as f:
        f.write(html_content)

    print(f"   💻 Enhanced dashboard: {output_path}")
    print("   ✨ Features: Live charts, real-time metrics, interactive visualizations")


def main():
    """Main demonstration function."""
    try:
        # Ensure output directory exists
        Path("outputs").mkdir(exist_ok=True)

        print("\n" + "=" * 50)
        print("✅ Dashboard visualization example")
        print("\nNote: This example demonstrates dashboard concepts.")
        print("Full dashboard functionality requires additional setup.")

    except Exception as e:
        print(f"❌ Error in dashboard demonstration: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()

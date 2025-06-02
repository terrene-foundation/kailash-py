#!/usr/bin/env python3
"""Comprehensive dashboard visualization example.

This example demonstrates the complete dashboard functionality including:
- Real-time monitoring setup
- Performance report generation
- API server integration
- Multiple visualization formats

Usage:
    python viz_dashboard_comprehensive.py
"""

import asyncio
import json
import time
from pathlib import Path

from kailash.nodes.data.readers import CSVReader
from kailash.nodes.data.writers import CSVWriter
from kailash.nodes.transform.processors import Filter
from kailash.runtime.local import LocalRuntime
from kailash.tracking.manager import TaskManager
from kailash.tracking.storage.filesystem import FileSystemStorage
from kailash.visualization.api import SimpleDashboardAPI
from kailash.visualization.dashboard import DashboardConfig, RealTimeDashboard
from kailash.visualization.reports import ReportFormat, WorkflowPerformanceReporter

# Kailash imports
from kailash.workflow.graph import Workflow

print("🚀 Comprehensive Dashboard Visualization Example")
print("=" * 60)


def create_sample_workflow():
    """Create a sample workflow for demonstration."""
    workflow = Workflow("dashboard_demo_workflow", "Dashboard Demo Workflow")

    # Create sample data processing workflow
    reader = CSVReader(node_id="data_reader", file_path="../data/customers.csv")

    filter_node = Filter(node_id="data_filter", field="age", operator=">", value=25)

    writer = CSVWriter(
        node_id="data_writer", file_path="../outputs/dashboard_demo_output.csv"
    )

    # Build workflow graph
    workflow.add_node("data_reader", reader)
    workflow.add_node("data_filter", filter_node)
    workflow.add_node("data_writer", writer)

    workflow.connect("data_reader", "data_filter", {"data": "data"})
    workflow.connect("data_filter", "data_writer", {"filtered_data": "data"})

    return workflow


def setup_task_manager():
    """Set up task manager with file system storage."""
    storage_path = Path("../data/dashboard_demo_tracking")
    storage_path.mkdir(parents=True, exist_ok=True)

    storage = FileSystemStorage(storage_path)
    return TaskManager(storage)


def demonstrate_real_time_dashboard():
    """Demonstrate real-time dashboard functionality."""
    print("\n1. Real-time Dashboard Monitoring")
    print("-" * 40)

    # Set up components
    task_manager = setup_task_manager()
    workflow = create_sample_workflow()

    # Configure dashboard for demo
    config = DashboardConfig(
        update_interval=0.5,  # Fast updates for demo
        max_history_points=50,
        auto_refresh=True,
        theme="light",
    )

    # Create dashboard
    dashboard = RealTimeDashboard(task_manager, config)

    # Create runtime and execute workflow
    runtime = LocalRuntime()

    print("📊 Starting workflow execution with real-time monitoring...")

    # Start monitoring
    dashboard.start_monitoring()

    # Add status callback to see real-time updates
    def status_callback(event_type, count):
        print(f"  📈 {event_type}: {count}")

    dashboard.add_status_callback(status_callback)

    try:
        # Execute workflow
        results, run_id = runtime.execute(workflow, task_manager)
        print(f"  🎯 Run ID: {run_id}")

        # Monitor for a few seconds to collect metrics
        print("  ⏱️  Monitoring execution (5 seconds)...")
        time.sleep(5)

        # Get current metrics
        current_metrics = dashboard.get_current_metrics()
        if current_metrics:
            print("  📊 Current metrics:")
            print(f"     - Active tasks: {current_metrics.active_tasks}")
            print(f"     - Completed tasks: {current_metrics.completed_tasks}")
            print(f"     - CPU usage: {current_metrics.total_cpu_usage:.1f}%")
            print(f"     - Memory usage: {current_metrics.total_memory_usage:.1f}MB")
            print(f"     - Throughput: {current_metrics.throughput:.2f} tasks/min")

        # Generate live dashboard
        dashboard_path = Path("../outputs/dashboard_demo_live.html")
        dashboard_path.parent.mkdir(parents=True, exist_ok=True)

        dashboard.generate_live_report(dashboard_path, include_charts=True)
        print(f"  💾 Live dashboard saved: {dashboard_path}")

        return run_id, task_manager

    finally:
        dashboard.stop_monitoring()
        print("  ⏹️  Monitoring stopped")


def demonstrate_performance_reports(run_id: str, task_manager: TaskManager):
    """Demonstrate performance report generation."""
    print("\n2. Performance Report Generation")
    print("-" * 40)

    reporter = WorkflowPerformanceReporter(task_manager)

    # Generate reports in different formats
    formats_to_test = [
        (ReportFormat.HTML, "../outputs/dashboard_demo_report.html"),
        (ReportFormat.MARKDOWN, "../outputs/dashboard_demo_report.md"),
        (ReportFormat.JSON, "../outputs/dashboard_demo_report.json"),
    ]

    for report_format, output_path in formats_to_test:
        print(f"  📄 Generating {report_format.value.upper()} report...")

        report_path = reporter.generate_report(
            run_id=run_id, output_path=output_path, format=report_format
        )

        print(f"     💾 Saved: {report_path}")

        # Show some content for JSON format
        if report_format == ReportFormat.JSON:
            with open(report_path) as f:
                data = json.load(f)
                summary = data.get("summary", {})
                print(
                    f"     📊 Summary: {summary.get('total_tasks', 0)} tasks, "
                    f"{summary.get('efficiency_score', 0):.0f}/100 efficiency"
                )


def demonstrate_api_integration(run_id: str, task_manager: TaskManager):
    """Demonstrate API integration functionality."""
    print("\n3. API Integration")
    print("-" * 40)

    # Create simple API interface
    api = SimpleDashboardAPI(task_manager)

    print("  🔌 Testing API endpoints...")

    # Test get runs
    runs = api.get_runs(limit=5)
    print(f"     📋 Found {len(runs)} runs")

    # Test get run details
    run_details = api.get_run_details(run_id)
    if run_details:
        print(
            f"     🎯 Run details: {run_details['total_tasks']} tasks, "
            f"{run_details['completed_tasks']} completed"
        )

    # Test monitoring
    print("  📊 Testing real-time monitoring via API...")
    api.start_monitoring(run_id)

    # Get metrics
    current_metrics = api.get_current_metrics()
    if current_metrics:
        print(
            f"     📈 Current: {current_metrics['completed_tasks']} completed, "
            f"{current_metrics['total_cpu_usage']:.1f}% CPU"
        )

    # Get history
    history = api.get_metrics_history(minutes=10)
    print(f"     📊 History: {len(history)} data points")

    api.stop_monitoring()

    # Test report generation via API
    print("  📄 Testing report generation via API...")
    report_path = api.generate_report(run_id, format="html")
    print(f"     💾 API-generated report: {report_path}")

    # Test dashboard generation via API
    dashboard_path = api.generate_dashboard()
    print(f"     💾 API-generated dashboard: {dashboard_path}")

    # Export metrics
    metrics_path = api.export_metrics_json()
    print(f"     💾 Exported metrics: {metrics_path}")


def demonstrate_advanced_visualizations(run_id: str, task_manager: TaskManager):
    """Demonstrate advanced visualization features."""
    print("\n4. Advanced Visualizations")
    print("-" * 40)

    # Create dashboard with advanced config
    advanced_config = DashboardConfig(
        update_interval=1.0,
        max_history_points=100,
        auto_refresh=True,
        theme="dark",  # Dark theme
    )

    dashboard = RealTimeDashboard(task_manager, advanced_config)

    # Generate comprehensive dashboard
    print("  🎨 Generating advanced dashboard...")

    advanced_dashboard_path = Path("../outputs/dashboard_demo_advanced.html")
    dashboard.generate_live_report(advanced_dashboard_path, include_charts=True)
    print(f"     💾 Advanced dashboard: {advanced_dashboard_path}")

    # Create dashboard snapshot with all assets
    print("  📸 Creating dashboard snapshot...")

    from kailash.visualization.dashboard import DashboardExporter

    exporter = DashboardExporter(dashboard)

    snapshot_dir = Path("../outputs/dashboard_snapshot")
    assets = exporter.create_dashboard_snapshot(
        output_dir=snapshot_dir, include_static_charts=True
    )

    print(f"     📁 Snapshot directory: {snapshot_dir}")
    for asset_name, asset_path in assets.items():
        print(f"       - {asset_name}: {asset_path.name}")

    # Performance comparison (if multiple runs exist)
    print("  📊 Performance analysis...")

    from kailash.visualization.performance import PerformanceVisualizer

    perf_viz = PerformanceVisualizer(task_manager)

    try:
        # Create detailed performance visualizations
        perf_outputs = perf_viz.create_run_performance_summary(
            run_id, output_dir=Path("../outputs/performance_analysis")
        )

        print("     📈 Performance visualizations:")
        for chart_name, chart_path in perf_outputs.items():
            print(f"       - {chart_name}: {chart_path.name}")

    except Exception as e:
        print(f"     ⚠️  Performance visualization error: {e}")


async def demonstrate_fastapi_server(task_manager: TaskManager):
    """Demonstrate FastAPI server functionality (if available)."""
    print("\n5. FastAPI Server Integration")
    print("-" * 40)

    try:
        from kailash.visualization.api import DashboardAPIServer

        print("  🌐 FastAPI available - server integration demo")

        # Create API server
        api_server = DashboardAPIServer(task_manager)

        print("     🔧 API server created successfully")
        print("     📚 Available endpoints:")
        print("       - GET  /health")
        print("       - GET  /api/v1/runs")
        print("       - GET  /api/v1/runs/{run_id}")
        print("       - GET  /api/v1/runs/{run_id}/tasks")
        print("       - POST /api/v1/monitoring/start")
        print("       - POST /api/v1/monitoring/stop")
        print("       - GET  /api/v1/monitoring/status")
        print("       - GET  /api/v1/metrics/current")
        print("       - GET  /api/v1/metrics/history")
        print("       - POST /api/v1/reports/generate")
        print("       - GET  /api/v1/reports/download/{filename}")
        print("       - GET  /api/v1/dashboard/live")
        print("       - WS   /api/v1/metrics/stream")

        print(
            "     ℹ️  To start server: api_server.start_server(host='0.0.0.0', port=8000)"
        )
        print("     ℹ️  Then visit: http://localhost:8000/docs for interactive API docs")

    except ImportError:
        print("  ⚠️  FastAPI not available - install with: pip install fastapi uvicorn")
        print("     🔧 Using SimpleDashboardAPI instead")


def demonstrate_custom_callbacks(task_manager: TaskManager):
    """Demonstrate custom callback functionality."""
    print("\n6. Custom Callbacks and Events")
    print("-" * 40)

    dashboard = RealTimeDashboard(task_manager)

    # Custom metrics callback
    def custom_metrics_callback(metrics):
        if metrics.completed_tasks > 0:
            print(f"  🎯 Metrics update: {metrics.completed_tasks} tasks completed")

    # Custom status callback
    def custom_status_callback(event_type, count):
        if event_type == "task_completed":
            print(f"  ✅ Task completed event: {count} new completions")
        elif event_type == "task_failed":
            print(f"  ❌ Task failed event: {count} new failures")

    # Register callbacks
    dashboard.add_metrics_callback(custom_metrics_callback)
    dashboard.add_status_callback(custom_status_callback)

    print("  📡 Custom callbacks registered")
    print("     - Metrics callback: Logs when tasks complete")
    print("     - Status callback: Logs task completion/failure events")

    # Simulate monitoring
    dashboard.start_monitoring()
    print("  ⏱️  Simulating monitoring (3 seconds)...")
    time.sleep(3)
    dashboard.stop_monitoring()


def main():
    """Main demonstration function."""
    try:
        # Ensure output directory exists
        Path("outputs").mkdir(exist_ok=True)

        # Run demonstrations
        run_id, task_manager = demonstrate_real_time_dashboard()

        # Allow some time for workflow completion
        time.sleep(2)

        demonstrate_performance_reports(run_id, task_manager)
        demonstrate_api_integration(run_id, task_manager)
        demonstrate_advanced_visualizations(run_id, task_manager)

        # Async demo
        asyncio.run(demonstrate_fastapi_server(task_manager))

        demonstrate_custom_callbacks(task_manager)

        print("\n" + "=" * 60)
        print("✅ Dashboard demonstration completed successfully!")
        print("\nGenerated files:")
        print("  📁 outputs/dashboard_demo_live.html - Live dashboard")
        print("  📁 outputs/dashboard_demo_report.* - Performance reports")
        print("  📁 outputs/dashboard_demo_advanced.html - Advanced dashboard")
        print("  📁 outputs/dashboard_snapshot/ - Complete snapshot")
        print("  📁 outputs/performance_analysis/ - Performance charts")

        print("\nNext steps:")
        print("  1. Open the HTML dashboards in a web browser")
        print("  2. Review the performance reports")
        print("  3. Explore the API integration examples")
        print("  4. Consider integrating with your monitoring infrastructure")

    except Exception as e:
        print(f"❌ Error in dashboard demonstration: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()

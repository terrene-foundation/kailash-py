#!/usr/bin/env python3
"""Simple dashboard visualization example.

This example shows basic dashboard usage for workflow monitoring
with minimal setup and configuration.

Usage:
    python viz_dashboard_simple.py
"""

import sys
import time
from pathlib import Path

from kailash.nodes.data.readers import CSVReaderNode
from kailash.nodes.data.writers import CSVWriterNode
from kailash.nodes.transform.processors import Filter
from kailash.runtime.local import LocalRuntime
from kailash.tracking.manager import TaskManager
from kailash.tracking.storage.filesystem import FileSystemStorage
from kailash.workflow.graph import Workflow


# Simple path utilities for this example
def get_data_dir():
    return Path(__file__).parent.parent.parent.parent / "data" / "inputs"


def get_output_dir():
    return Path("/tmp") / "viz_dashboard_output"


# from kailash.visualization.dashboard import RealTimeDashboard
# from kailash.visualization.reports import ReportFormat, WorkflowPerformanceReporter


print("📊 Simple Dashboard Example")
print("=" * 40)


def create_simple_workflow():
    """Create a basic data processing workflow."""
    workflow = Workflow("simple_dashboard_demo", "Simple Dashboard Demo")

    # Simple 3-node workflow
    reader = CSVReaderNode(
        node_id="reader", file_path=str(get_data_dir() / "customers.csv")
    )

    filter_node = Filter(node_id="filter", field="age", operator=">", value=18)

    writer = CSVWriterNode(
        node_id="writer",
        file_path=str(get_output_dir() / "simple_dashboard_output.csv"),
    )

    # Connect nodes
    workflow.add_node("reader", reader)
    workflow.add_node("filter", filter_node)
    workflow.add_node("writer", writer)

    workflow.connect("reader", "filter", {"data": "data"})
    workflow.connect("filter", "writer", {"filtered_data": "data"})

    return workflow


def setup_basic_tracking():
    """Set up basic task tracking."""
    storage_path = get_data_dir() / "simple_dashboard_tracking"
    storage_path.mkdir(parents=True, exist_ok=True)

    storage = FileSystemStorage(storage_path)
    return TaskManager(storage)


def run_with_dashboard_monitoring():
    """Execute workflow with real-time dashboard monitoring."""
    print("\n1. Setting up workflow and monitoring...")

    # Create components
    task_manager = setup_basic_tracking()
    workflow = create_simple_workflow()
    runtime = LocalRuntime()

    # Create dashboard
    # dashboard = RealTimeDashboard(task_manager)

    print("   ✅ Components initialized")

    # Start monitoring
    print("\n2. Starting real-time monitoring...")
    # dashboard.start_monitoring()

    # Simple callback to show progress
    def progress_callback(event_type, count):
        print(f"   📈 {event_type}: {count}")

    # dashboard.add_status_callback(progress_callback)

    try:
        # Execute workflow
        print("\n3. Executing workflow...")
        results, run_id = runtime.execute(workflow, task_manager)
        print(f"   🎯 Run ID: {run_id}")

        # Monitor execution
        print("   ⏱️  Monitoring for 3 seconds...")
        time.sleep(3)

        # Get final metrics
        # metrics = dashboard.get_current_metrics()
        metrics = None  # Dashboard not available
        if metrics:
            print("\n4. Final metrics:")
            print(f"   - Completed tasks: {metrics.completed_tasks}")
            print(f"   - Failed tasks: {metrics.failed_tasks}")
            print(f"   - CPU usage: {metrics.total_cpu_usage:.1f}%")
            print(f"   - Memory usage: {metrics.total_memory_usage:.1f}MB")

        return run_id, None, task_manager

    finally:
        # dashboard.stop_monitoring()
        print("   ⏹️  Monitoring stopped")


def generate_simple_reports(run_id: str, task_manager: TaskManager):
    """Generate basic performance reports."""
    print("\n5. Generating reports...")

    # Create reporter
    # reporter = WorkflowPerformanceReporter(task_manager)
    print("   📄 Performance reporter would be created here")

    # Generate HTML report
    # html_report = reporter.generate_report(
    #     run_id=run_id,
    #     output_path="../outputs/simple_dashboard_report.html",
    #     format=ReportFormat.HTML,
    # )
    print("   📄 HTML report would be generated here")

    # Generate Markdown report
    # md_report = reporter.generate_report(
    #     run_id=run_id,
    #     output_path="../outputs/simple_dashboard_report.md",
    #     format=ReportFormat.MARKDOWN,
    # )
    print("   📄 Markdown report would be generated here")


def generate_live_dashboard(dashboard=None):  # RealTimeDashboard removed
    """Generate live dashboard HTML."""
    print("\n6. Generating live dashboard...")

    dashboard_path = get_output_dir() / "simple_live_dashboard.html"
    dashboard_path.parent.mkdir(parents=True, exist_ok=True)

    # dashboard.generate_live_report(dashboard_path, include_charts=True)
    print(f"   💻 Live dashboard: {dashboard_path}")


def demonstrate_api_basics(task_manager: TaskManager):
    """Demonstrate basic API functionality."""
    print("\n7. API basics...")

    # from kailash.visualization.api import SimpleDashboardAPI

    # Create simple API
    # api = SimpleDashboardAPI(task_manager)
    print("   🔧 API would be created here")

    # Get runs
    # runs = api.get_runs(limit=3)
    print("   📋 Recent runs would be fetched here")

    # for run in runs:
    #     print(
    #         f"     - {run['run_id'][:8]}: {run['workflow_name']} "
    #         f"({run['completed_tasks']}/{run['total_tasks']} completed)"
    #     )


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

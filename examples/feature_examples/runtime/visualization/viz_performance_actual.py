#!/usr/bin/env python3
"""
Actual Performance Metrics Visualization

This example runs workflows and visualizes the actual collected performance metrics.
"""

import sys
import time
from pathlib import Path
from typing import Any

from examples.utils.paths import get_output_dir

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from kailash.nodes.base import NodeParameter
from kailash.nodes.code.python import PythonCodeNode
from kailash.runtime.local import LocalRuntime
from kailash.tracking.manager import TaskManager
from kailash.tracking.storage.filesystem import FileSystemStorage
from kailash.visualization.performance import PerformanceVisualizer
from kailash.workflow.graph import Workflow
from kailash.workflow.visualization import WorkflowVisualizer


def create_test_workflow():
    """Create a simple test workflow with varied performance characteristics."""

    workflow = Workflow(workflow_id="test_workflow", name="Test Performance Workflow")

    # Node 1: Fast I/O operation
    def read_data(size: int = 50) -> dict[str, Any]:
        """Simulate data reading."""
        data = [{"id": i, "value": i * 10} for i in range(size)]
        time.sleep(0.1)  # I/O delay
        return {"data": data}

    read_schema = {
        "input": {
            "size": NodeParameter(name="size", type=int, default=50, required=False)
        },
        "output": {"data": NodeParameter(name="data", type=list, required=True)},
    }

    data_reader = PythonCodeNode.from_function(
        read_data,
        name="data_reader",
        input_schema=read_schema["input"],
        output_schema=read_schema["output"],
    )

    # Node 2: CPU intensive
    def process_data(data: list) -> dict[str, Any]:
        """CPU intensive processing."""
        result = []
        for item in data:
            # Simulate CPU work
            total = 0
            for i in range(10000):
                total += i * item["value"]
            item["processed"] = total
            result.append(item)
        time.sleep(0.2)
        return {"data": result}

    process_schema = {
        "input": {"data": NodeParameter(name="data", type=list, required=True)},
        "output": {"data": NodeParameter(name="data", type=list, required=True)},
    }

    data_processor = PythonCodeNode.from_function(
        process_data,
        name="data_processor",
        input_schema=process_schema["input"],
        output_schema=process_schema["output"],
    )

    # Node 3: Memory intensive
    def transform_data(data: list) -> dict[str, Any]:
        """Memory intensive transformation."""
        # Create copies
        copies = [data.copy() for _ in range(50)]

        result = []
        for item in data:
            item["transformed"] = True
            item["copies"] = len(copies)
            result.append(item)

        time.sleep(0.15)
        return {"data": result}

    transform_schema = {
        "input": {"data": NodeParameter(name="data", type=list, required=True)},
        "output": {"data": NodeParameter(name="data", type=list, required=True)},
    }

    data_transformer = PythonCodeNode.from_function(
        transform_data,
        name="data_transformer",
        input_schema=transform_schema["input"],
        output_schema=transform_schema["output"],
    )

    # Node 4: Aggregator
    def aggregate_data(data: list) -> dict[str, Any]:
        """Aggregate results."""
        total = sum(item["value"] for item in data)
        count = len(data)
        avg = total / count if count > 0 else 0

        time.sleep(0.05)

        return {"summary": {"total": total, "count": count, "average": avg}}

    aggregate_schema = {
        "input": {"data": NodeParameter(name="data", type=list, required=True)},
        "output": {"summary": NodeParameter(name="summary", type=dict, required=True)},
    }

    data_aggregator = PythonCodeNode.from_function(
        aggregate_data,
        name="data_aggregator",
        input_schema=aggregate_schema["input"],
        output_schema=aggregate_schema["output"],
    )

    # Build workflow
    workflow.add_node("data_reader", data_reader)
    workflow.add_node("data_processor", data_processor)
    workflow.add_node("data_transformer", data_transformer)
    workflow.add_node("data_aggregator", data_aggregator)

    workflow.connect("data_reader", "data_processor", {"data": "data"})
    workflow.connect("data_processor", "data_transformer", {"data": "data"})
    workflow.connect("data_transformer", "data_aggregator", {"data": "data"})

    return workflow


def visualize_performance():
    """Run workflow and visualize actual performance metrics."""

    print("\n=== PERFORMANCE METRICS VISUALIZATION ===\n")

    # Setup
    output_dir = get_output_dir() / "actual_performance"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Clean storage directory
    storage_dir = output_dir / "storage"
    if storage_dir.exists():
        import shutil

        shutil.rmtree(storage_dir)
    storage_dir.mkdir(parents=True, exist_ok=True)

    # Initialize components
    storage = FileSystemStorage(base_path=str(storage_dir))
    task_manager = TaskManager(storage_backend=storage)
    runtime = LocalRuntime(debug=False)

    # Create workflow
    workflow = create_test_workflow()

    # Run 1: Small dataset
    print("1. Running with small dataset (25 items)...")

    start = time.time()
    results1, run1_id = runtime.execute(
        workflow=workflow,
        task_manager=task_manager,
        parameters={"data_reader": {"size": 25}},
    )
    duration1 = time.time() - start

    print(f"   ✓ Completed in {duration1:.2f}s")
    print(f"   Summary: {results1['data_aggregator']['summary']}")

    # Run 2: Large dataset
    print("\n2. Running with large dataset (75 items)...")

    start = time.time()
    results2, run2_id = runtime.execute(
        workflow=workflow,
        task_manager=task_manager,
        parameters={"data_reader": {"size": 75}},
    )
    duration2 = time.time() - start

    print(f"   ✓ Completed in {duration2:.2f}s")
    print(f"   Summary: {results2['data_aggregator']['summary']}")

    # Wait a moment for storage to sync
    time.sleep(0.5)

    print("\n3. Verifying runs created...")
    print(f"   ✓ Run 1 ID: {run1_id}")
    print(f"   ✓ Run 2 ID: {run2_id}")

    # Generate visualizations
    print("\n4. Generating performance visualizations...")

    perf_viz = PerformanceVisualizer(task_manager)

    # Visualizations for Run 1
    viz1_dir = output_dir / "run1_small"
    outputs1 = perf_viz.create_run_performance_summary(run1_id, viz1_dir)

    print("\n   Run 1 visualizations:")
    for viz_type, path in outputs1.items():
        if path.exists():
            print(f"   ✓ {viz_type}: {path.name}")

    # Visualizations for Run 2
    viz2_dir = output_dir / "run2_large"
    outputs2 = perf_viz.create_run_performance_summary(run2_id, viz2_dir)

    print("\n   Run 2 visualizations:")
    for viz_type, path in outputs2.items():
        if path.exists():
            print(f"   ✓ {viz_type}: {path.name}")

    # Run comparison
    comparison_path = output_dir / "run_comparison.png"
    perf_viz.compare_runs([run1_id, run2_id], comparison_path)
    print(f"\n   ✓ Run comparison: {comparison_path.name}")

    # Create dashboard
    print("\n5. Creating performance dashboard...")

    workflow_viz = WorkflowVisualizer(workflow)
    dashboard_dir = output_dir / "dashboard"
    workflow_viz.create_performance_dashboard(
        run_id=run2_id, task_manager=task_manager, output_dir=dashboard_dir
    )

    print(f"   ✓ Dashboard: {dashboard_dir / 'dashboard.html'}")

    # Display metrics summary
    print("\n6. Performance Metrics Summary")
    print("-" * 50)

    tasks1 = task_manager.get_run_tasks(run1_id)
    tasks2 = task_manager.get_run_tasks(run2_id)

    for run_name, tasks in [("Run 1 (25 items)", tasks1), ("Run 2 (75 items)", tasks2)]:
        if tasks:
            print(f"\n{run_name}:")
            print(f"{'Node':<20} {'Duration':<10} {'CPU %':<10} {'Memory MB':<10}")
            print("-" * 50)

            total_duration = 0
            for task in tasks:
                if task.metrics:
                    duration = task.metrics.duration or 0
                    cpu = task.metrics.cpu_usage or 0
                    memory = task.metrics.memory_usage_mb or 0
                    total_duration += duration

                    print(
                        f"{task.node_id:<20} {duration:<10.3f} {cpu:<10.1f} {memory:<10.1f}"
                    )

            print("-" * 50)
            print(f"{'TOTAL':<20} {total_duration:<10.3f}")

    print(f"\n✅ All visualizations saved to: {output_dir.absolute()}")
    print("\nKey files:")
    print(f"  • Timeline charts: {output_dir}/run*/timeline_*.png")
    print(f"  • Resource charts: {output_dir}/run*/resources_*.png")
    print(f"  • Performance heatmaps: {output_dir}/run*/heatmap_*.png")
    print(f"  • Run comparison: {output_dir}/run_comparison.png")
    print(f"  • Dashboard: {output_dir}/dashboard/dashboard.html")


if __name__ == "__main__":
    visualize_performance()

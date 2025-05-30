#!/usr/bin/env python3
"""
Visualization Example

This example demonstrates the visualization capabilities of Kailash SDK.
"""

import sys
from pathlib import Path
from typing import Any, Dict

import matplotlib.pyplot as plt
import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))

from kailash.nodes.code.python import PythonCodeNode
from kailash.nodes.data.readers import CSVReader, JSONReader
from kailash.nodes.data.writers import CSVWriter, JSONWriter
from kailash.tracking.manager import TaskManager
from kailash.tracking.models import TaskStatus
from kailash.workflow.graph import Workflow
from kailash.workflow.visualization import WorkflowVisualizer


def create_sample_workflow():
    """Create a sample workflow for visualization."""

    workflow = Workflow(
        workflow_id="data_processing_pipeline", name="data_processing_pipeline"
    )

    # Create nodes
    csv_reader = CSVReader(file_path="data/customers.csv", headers=True)
    json_reader = JSONReader(file_path="data/transactions.json")

    # Create joiner using PythonCodeNode
    def join_data(customer_data: list, transaction_data: list) -> Dict[str, Any]:
        """Join customer and transaction data."""
        # Simulate join operation
        joined = []
        for customer in customer_data:
            customer_id = customer.get("customer_id")
            customer_transactions = [
                t for t in transaction_data if t.get("customer_id") == customer_id
            ]
            joined.append({**customer, "transactions": customer_transactions})
        return {"data": joined}

    from kailash.nodes.base import NodeParameter

    # Create schemas for joiner
    joiner_input_schema = {
        "customer_data": NodeParameter(name="customer_data", type=list, required=True),
        "transaction_data": NodeParameter(
            name="transaction_data", type=list, required=True
        ),
    }
    joiner_output_schema = {
        "data": NodeParameter(name="data", type=list, required=True)
    }
    data_joiner = PythonCodeNode.from_function(
        join_data,
        name="join_data",
        input_schema=joiner_input_schema,
        output_schema=joiner_output_schema,
    )

    # Create transformer
    def clean_data(data: list) -> Dict[str, Any]:
        """Clean and transform data."""
        cleaned = []
        for record in data:
            # Simulate data cleaning
            cleaned_record = record.copy()
            cleaned_record["cleaned"] = True
            cleaned.append(cleaned_record)
        return {"data": cleaned}

    # Create schemas for transformer
    transformer_input_schema = {
        "data": NodeParameter(name="data", type=list, required=True)
    }
    transformer_output_schema = {
        "data": NodeParameter(name="data", type=list, required=True)
    }
    data_transformer = PythonCodeNode.from_function(
        clean_data,
        name="clean_data",
        input_schema=transformer_input_schema,
        output_schema=transformer_output_schema,
    )

    # Create classifier
    def classify_customers(data: list) -> Dict[str, Any]:
        """Classify customers into segments."""
        classified = []
        for record in data:
            record["segment"] = (
                "high_value" if len(record.get("transactions", [])) > 5 else "low_value"
            )
            classified.append(record)
        return {"data": classified}

    classifier = PythonCodeNode.from_function(
        classify_customers,
        name="classify_customers",
        input_schema=transformer_input_schema,
        output_schema=transformer_output_schema,
    )

    # Create aggregator
    def calculate_metrics(data: list) -> Dict[str, Any]:
        """Calculate aggregate metrics."""
        segments = {}
        for record in data:
            segment = record.get("segment", "unknown")
            if segment not in segments:
                segments[segment] = 0
            segments[segment] += 1
        return {"metrics": segments}

    # Create schemas for aggregator
    aggregator_output_schema = {
        "metrics": NodeParameter(name="metrics", type=dict, required=True)
    }
    aggregator = PythonCodeNode.from_function(
        calculate_metrics,
        name="calculate_metrics",
        input_schema=transformer_input_schema,
        output_schema=aggregator_output_schema,
    )

    csv_writer = CSVWriter(file_path="data/results.csv")
    json_writer = JSONWriter(file_path="data/summary.json", data={})

    # Add nodes to workflow
    workflow.add_node(node_id="csv_reader", node_or_type=csv_reader)
    workflow.add_node(node_id="json_reader", node_or_type=json_reader)
    workflow.add_node(node_id="data_joiner", node_or_type=data_joiner)
    workflow.add_node(node_id="data_transformer", node_or_type=data_transformer)
    workflow.add_node(node_id="classifier", node_or_type=classifier)
    workflow.add_node(node_id="aggregator", node_or_type=aggregator)
    workflow.add_node(node_id="csv_writer", node_or_type=csv_writer)
    workflow.add_node(node_id="json_writer", node_or_type=json_writer)

    # Connect nodes
    workflow.connect("csv_reader", "data_joiner", {"data": "customer_data"})
    workflow.connect("json_reader", "data_joiner", {"data": "transaction_data"})
    workflow.connect("data_joiner", "data_transformer", {"data": "data"})
    workflow.connect("data_transformer", "classifier", {"data": "data"})
    workflow.connect("classifier", "aggregator", {"data": "data"})
    workflow.connect("classifier", "csv_writer", {"data": "data"})
    workflow.connect("aggregator", "json_writer", {"metrics": "data"})

    return workflow


def demonstrate_basic_visualization():
    """Demonstrate basic workflow visualization."""

    print("\n=== Basic Workflow Visualization ===")

    workflow = create_sample_workflow()

    # Create Mermaid visualization
    output_path = "data/basic_workflow.md"
    workflow.save_mermaid_markdown(output_path, title="Data Processing Pipeline")

    print(f"✓ Basic visualization created: {output_path}")

    # Also show the Mermaid diagram
    print("\nMermaid diagram preview:")
    print(workflow.to_mermaid()[:300] + "...")


def demonstrate_custom_visualization():
    """Demonstrate custom visualization using WorkflowVisualizer."""

    print("\n=== Custom Visualization ===")

    workflow = create_sample_workflow()
    visualizer = WorkflowVisualizer(workflow)

    # Import MermaidVisualizer
    from kailash.workflow.mermaid_visualizer import MermaidVisualizer

    # Create custom Mermaid visualizer with custom styles
    custom_styles = {
        "reader": "fill:#2196F3,stroke:#0D47A1,stroke-width:3px,color:#fff",
        "writer": "fill:#4CAF50,stroke:#1B5E20,stroke-width:3px,color:#fff",
        "transform": "fill:#FF9800,stroke:#E65100,stroke-width:3px,color:#fff",
        "logic": "fill:#E91E63,stroke:#880E4F,stroke-width:3px,color:#fff",
        "code": "fill:#9C27B0,stroke:#4A148C,stroke-width:3px,color:#fff",
    }

    mermaid_viz = MermaidVisualizer(
        workflow, direction="LR", node_styles=custom_styles  # Left to right
    )

    # Save with custom title
    output_path = "data/custom_workflow.md"
    mermaid_viz.save_markdown(output_path, title="Enhanced Data Processing Pipeline")

    print(f"✓ Custom visualization created: {output_path}")


def demonstrate_execution_visualization():
    """Demonstrate visualization with execution status."""

    print("\n=== Execution Status Visualization ===")

    workflow = create_sample_workflow()
    task_manager = TaskManager()

    # Create a run
    run_id = task_manager.create_run(workflow_name=workflow.name)

    # Create sample data
    Path("data").mkdir(exist_ok=True)
    with open("data/customers.csv", "w") as f:
        f.write("customer_id,name,value\n")
        f.write("1,Customer A,1000\n")
        f.write("2,Customer B,2000\n")

    with open("data/transactions.json", "w") as f:
        import json

        transactions = [
            {"customer_id": "1", "amount": 100},
            {"customer_id": "1", "amount": 200},
            {"customer_id": "2", "amount": 300},
        ]
        json.dump(transactions, f)

    # Simulate task execution
    from kailash.tracking.models import TaskRun

    # Create tasks for each node
    node_statuses = {
        "csv_reader": TaskStatus.COMPLETED,
        "json_reader": TaskStatus.COMPLETED,
        "data_joiner": TaskStatus.COMPLETED,
        "data_transformer": TaskStatus.RUNNING,
        "classifier": TaskStatus.PENDING,
        "aggregator": TaskStatus.PENDING,
        "csv_writer": TaskStatus.PENDING,
        "json_writer": TaskStatus.PENDING,
    }

    for node_id, status in node_statuses.items():
        task = TaskRun(
            run_id=run_id,
            node_id=node_id,
            node_type=workflow.nodes[node_id].node_type,
            status=status,
        )
        task_manager.save_task(task)

    # Create execution visualization as Mermaid markdown
    visualizer = WorkflowVisualizer(workflow)
    output_path = visualizer.create_execution_graph(run_id, task_manager)

    print(f"✓ Execution visualization created: {output_path}")

    # Also create one with custom output path
    custom_path = "examples/data/outputs/execution_status.md"
    custom_output = visualizer.create_execution_graph(run_id, task_manager, custom_path)
    print(f"✓ Custom execution visualization created: {custom_output}")


def demonstrate_performance_metrics():
    """Demonstrate performance metrics visualization."""

    print("\n=== Performance Metrics Visualization ===")

    # Create synthetic performance data
    node_names = [
        "csv_reader",
        "json_reader",
        "data_joiner",
        "data_transformer",
        "classifier",
    ]
    metrics_data = {
        "execution_time": [0.5, 0.3, 1.2, 0.8, 2.1],
        "memory_usage": [50, 30, 120, 80, 200],
        "cpu_usage": [20, 15, 60, 40, 85],
    }

    # Create performance visualization
    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(10, 10))
    fig.suptitle("Node Performance Metrics", fontsize=16)

    # Execution time
    ax1.bar(node_names, metrics_data["execution_time"], color="skyblue")
    ax1.set_ylabel("Execution Time (s)")
    ax1.set_title("Execution Time by Node")
    ax1.grid(True, alpha=0.3)

    # Memory usage
    ax2.bar(node_names, metrics_data["memory_usage"], color="lightgreen")
    ax2.set_ylabel("Memory Usage (MB)")
    ax2.set_title("Memory Usage by Node")
    ax2.grid(True, alpha=0.3)

    # CPU usage
    ax3.bar(node_names, metrics_data["cpu_usage"], color="lightcoral")
    ax3.set_ylabel("CPU Usage (%)")
    ax3.set_title("CPU Usage by Node")
    ax3.set_xlabel("Node")
    ax3.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig("data/performance_metrics_matplotlib.png", dpi=300, bbox_inches="tight")
    plt.close()

    print(
        "✓ Performance metrics visualization created: data/performance_metrics_matplotlib.png"
    )


def demonstrate_workflow_comparison():
    """Demonstrate comparing multiple workflows visually."""

    print("\n=== Workflow Comparison ===")

    # Create two similar workflows
    workflow1 = create_sample_workflow()
    workflow1.name = "workflow_v1"

    workflow2 = create_sample_workflow()
    workflow2.name = "workflow_v2"

    # Add an extra node to workflow2
    def extra_processor(data: list) -> Dict[str, Any]:
        """Additional processing step."""
        return {"data": data}

    # Import NodeParameter for schemas
    from kailash.nodes.base import NodeParameter

    # Create schemas for extra processor
    extra_processor_input_schema = {
        "data": NodeParameter(name="data", type=list, required=True)
    }
    extra_processor_output_schema = {
        "data": NodeParameter(name="data", type=list, required=True)
    }
    extra_node = PythonCodeNode.from_function(
        extra_processor,
        name="extra_processor",
        input_schema=extra_processor_input_schema,
        output_schema=extra_processor_output_schema,
    )

    # Add the extra node and connect it between classifier and csv_writer
    workflow2.add_node(node_id="extra_processor", node_or_type=extra_node)

    # Note: Since we can't remove edges, we'll recreate the final connection
    # This will create an additional branch rather than replacing the connection
    workflow2.connect("classifier", "extra_processor", {"data": "data"})
    workflow2.connect("extra_processor", "csv_writer", {"data": "data"})

    # Create side-by-side visualization
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(20, 10))

    # Visualize workflow1
    plt.sca(ax1)
    visualizer1 = WorkflowVisualizer(workflow1)
    pos1 = visualizer1._calculate_layout()
    import networkx as nx

    nx.draw(
        workflow1.graph,
        pos1,
        ax=ax1,
        with_labels=True,
        node_color="lightblue",
        node_size=2000,
        font_size=8,
        arrows=True,
    )
    ax1.set_title("Workflow v1", fontsize=14)
    ax1.axis("off")

    # Visualize workflow2
    plt.sca(ax2)
    visualizer2 = WorkflowVisualizer(workflow2)
    pos2 = visualizer2._calculate_layout()
    nx.draw(
        workflow2.graph,
        pos2,
        ax=ax2,
        with_labels=True,
        node_color="lightgreen",
        node_size=2000,
        font_size=8,
        arrows=True,
    )
    ax2.set_title("Workflow v2 (with extra processor)", fontsize=14)
    ax2.axis("off")

    plt.tight_layout()
    plt.savefig("data/workflow_comparison_matplotlib.png", dpi=300, bbox_inches="tight")
    plt.close()

    # Also create Mermaid comparison
    comparison_content = """# Workflow Comparison

This document compares two versions of a data processing workflow.

## Workflow v1 - Original

```mermaid
{}
```

## Workflow v2 - Enhanced with Extra Processor

```mermaid
{}
```

## Changes Summary

- **Added**: `extra_processor` node between `classifier` and `csv_writer`
- **Purpose**: Additional processing step for data enhancement
- **Impact**: Data now goes through an extra transformation before being written to CSV
""".format(
        workflow1.to_mermaid(), workflow2.to_mermaid()
    )

    # Save comparison
    output_path = "data/workflow_comparison.md"
    with open(output_path, "w") as f:
        f.write(comparison_content)

    print(f"✓ Workflow comparison created: {output_path} (and matplotlib version)")


def demonstrate_execution_timeline():
    """Demonstrate execution timeline visualization."""

    print("\n=== Execution Timeline ===")

    # Create timeline data
    timeline_data = [
        {"node": "csv_reader", "start": 0, "duration": 0.5, "status": "completed"},
        {"node": "json_reader", "start": 0, "duration": 0.3, "status": "completed"},
        {"node": "data_joiner", "start": 0.5, "duration": 1.2, "status": "completed"},
        {
            "node": "data_transformer",
            "start": 1.7,
            "duration": 0.8,
            "status": "completed",
        },
        {"node": "classifier", "start": 2.5, "duration": 2.1, "status": "running"},
        {"node": "aggregator", "start": 4.6, "duration": 0.5, "status": "pending"},
        {"node": "csv_writer", "start": 4.6, "duration": 0.3, "status": "pending"},
        {"node": "json_writer", "start": 5.1, "duration": 0.2, "status": "pending"},
    ]

    # Create timeline visualization
    fig, ax = plt.subplots(figsize=(12, 6))

    # Define colors for status
    status_colors = {"completed": "green", "running": "yellow", "pending": "lightgray"}

    # Plot timeline
    for i, task in enumerate(timeline_data):
        color = status_colors[task["status"]]
        ax.barh(
            i,
            task["duration"],
            left=task["start"],
            height=0.8,
            color=color,
            alpha=0.7,
            edgecolor="black",
        )

        # Add node name
        ax.text(
            task["start"] - 0.1, i, task["node"], ha="right", va="center", fontsize=10
        )

    # Customize plot
    ax.set_ylim(-0.5, len(timeline_data) - 0.5)
    ax.set_xlabel("Time (seconds)")
    ax.set_title("Workflow Execution Timeline", fontsize=14)
    ax.grid(True, alpha=0.3, axis="x")
    ax.set_yticks([])

    # Add legend
    from matplotlib.patches import Patch

    legend_elements = [
        Patch(facecolor=color, label=status.title())
        for status, color in status_colors.items()
    ]
    ax.legend(handles=legend_elements, loc="upper right")

    plt.tight_layout()
    plt.savefig("data/execution_timeline_matplotlib.png", dpi=300, bbox_inches="tight")
    plt.close()

    print("✓ Execution timeline created: data/execution_timeline_matplotlib.png")


def demonstrate_resource_heatmap():
    """Demonstrate resource usage heatmap."""

    print("\n=== Resource Usage Heatmap ===")

    # Create resource usage data
    nodes = [
        "csv_reader",
        "json_reader",
        "data_joiner",
        "data_transformer",
        "classifier",
        "aggregator",
    ]
    time_points = list(range(10))  # 10 time points

    # Generate synthetic resource data
    cpu_usage = np.random.rand(len(nodes), len(time_points)) * 100
    memory_usage = np.random.rand(len(nodes), len(time_points)) * 500

    # Create heatmap
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6))

    # CPU usage heatmap
    im1 = ax1.imshow(cpu_usage, cmap="YlOrRd", aspect="auto")
    ax1.set_xticks(range(len(time_points)))
    ax1.set_xticklabels(time_points)
    ax1.set_yticks(range(len(nodes)))
    ax1.set_yticklabels(nodes)
    ax1.set_xlabel("Time")
    ax1.set_ylabel("Node")
    ax1.set_title("CPU Usage (%)")
    plt.colorbar(im1, ax=ax1)

    # Memory usage heatmap
    im2 = ax2.imshow(memory_usage, cmap="YlGnBu", aspect="auto")
    ax2.set_xticks(range(len(time_points)))
    ax2.set_xticklabels(time_points)
    ax2.set_yticks(range(len(nodes)))
    ax2.set_yticklabels(nodes)
    ax2.set_xlabel("Time")
    ax2.set_ylabel("Node")
    ax2.set_title("Memory Usage (MB)")
    plt.colorbar(im2, ax=ax2)

    plt.tight_layout()
    plt.savefig("data/resource_heatmap_matplotlib.png", dpi=300, bbox_inches="tight")
    plt.close()

    print("✓ Resource heatmap created: data/resource_heatmap_matplotlib.png")


def main():
    """Main entry point for visualization examples."""

    print("=== Kailash Visualization Examples ===\n")

    # Create output directory
    Path("data").mkdir(exist_ok=True)

    examples = [
        ("Basic Visualization", demonstrate_basic_visualization),
        ("Custom Visualization", demonstrate_custom_visualization),
        ("Execution Status Visualization", demonstrate_execution_visualization),
        ("Performance Metrics", demonstrate_performance_metrics),
        ("Workflow Comparison", demonstrate_workflow_comparison),
        ("Execution Timeline", demonstrate_execution_timeline),
        ("Resource Heatmap", demonstrate_resource_heatmap),
    ]

    for name, example_func in examples:
        print(f"\n{'='*50}")
        print(f"Running: {name}")
        print("=" * 50)

        try:
            example_func()
        except Exception as e:
            print(f"Example failed: {e}")
            import traceback

            traceback.print_exc()

    print("\n=== All visualization examples completed ===")
    print("\nVisualization files created in the 'data' directory:")
    for file in sorted(Path("data").glob("*.png")):
        print(f"  - {file.name}")

    return 0


if __name__ == "__main__":
    sys.exit(main())

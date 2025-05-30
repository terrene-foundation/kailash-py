#!/usr/bin/env python3
"""
Simplified Workflow Example - Using Standard Nodes Only

This example avoids complex node types and shows how to use the basic
functionality of the Kailash SDK with just the standard nodes.
"""

import sys
from pathlib import Path

import pandas as pd

# Ensure module is in path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from kailash.nodes.data import CSVReader, CSVWriter
from kailash.runtime.local import LocalRuntime

# Import from the Kailash SDK
from kailash.workflow.graph import Workflow
from kailash.workflow.visualization import WorkflowVisualizer

# Setup directories
data_dir = Path("../data")
data_dir.mkdir(exist_ok=True)

output_dir = Path("../data/outputs")
output_dir.mkdir(exist_ok=True)

# Create sample data
sample_data = pd.DataFrame(
    {
        "id": range(1, 101),
        "name": [f"Item {i}" for i in range(1, 101)],
        "value": [i * 10 for i in range(1, 101)],
        "category": ["A", "B", "C", "D"] * 25,
    }
)

# Save sample data
sample_data.to_csv(data_dir / "sample_data.csv", index=False)

print("=== Basic Workflow Example ===")

# Create a workflow
workflow = Workflow(workflow_id="simple_workflow", name="Simple Data Pipeline")

# Create nodes
reader = CSVReader(name="csv_reader", file_path=str(data_dir / "sample_data.csv"))

writer = CSVWriter(name="csv_writer", file_path=str(output_dir / "processed_data.csv"))

# Add nodes to workflow
workflow.add_node(node_id="reader", node_or_type=reader)
workflow.add_node(node_id="writer", node_or_type=writer)

# Connect nodes
workflow.connect("reader", "writer", {"data": "data"})

# Execute workflow
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow)

print(f"Workflow executed successfully with run ID: {run_id}")
print(f"Read {len(sample_data)} records")
print(f"Processed data saved to {output_dir / 'processed_data.csv'}")

# Visualize workflow
try:
    visualizer = WorkflowVisualizer()
    output_path = output_dir / "simple_workflow.png"
    visualizer.visualize(workflow, output_path=str(output_path))
    print(f"Visualization saved to {output_path}")
except Exception as e:
    print(f"Visualization failed: {e}")

print("\n=== Example completed successfully ===")

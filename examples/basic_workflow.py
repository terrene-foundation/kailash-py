#!/usr/bin/env python3
"""
Basic Workflow Example

This example demonstrates how to create a simple workflow that:
1. Reads data from a CSV file
2. Transforms the data using a Python code node
3. Writes the result to a new file
4. Exports the workflow definition

This is a typical ETL (Extract, Transform, Load) pattern.
"""

import sys
from pathlib import Path
from typing import Any, Dict

import pandas as pd

# Add the parent directory to the path to import kailash
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from kailash.nodes.base import NodeParameter
from kailash.nodes.code.python import PythonCodeNode
from kailash.nodes.data.readers import CSVReader
from kailash.nodes.data.writers import CSVWriter
from kailash.runtime.local import LocalRuntime
from kailash.workflow.graph import Workflow
from kailash.workflow.visualization import WorkflowVisualizer


def create_data_transformer():
    """Create a Python node for data transformation."""

    def transform_data(data: list) -> Dict[str, Any]:
        """Transform customer data by adding a tier field."""
        df = pd.DataFrame(data)

        # Calculate customer tier based on purchase total
        if "purchase_total" in df.columns:
            df["purchase_total"] = pd.to_numeric(df["purchase_total"], errors="coerce")
            df["customer_tier"] = pd.cut(
                df["purchase_total"],
                bins=[0, 100, 500, 1000, float("inf")],
                labels=["Bronze", "Silver", "Gold", "Platinum"],
            )

        return {"data": df.to_dict(orient="records")}

    # Define schema
    input_schema = {
        "data": NodeParameter(
            name="data",
            type=list,
            required=True,
            description="List of customer records",
        )
    }

    output_schema = {
        "data": NodeParameter(
            name="data",
            type=list,
            required=True,
            description="Transformed customer records with tier",
        )
    }

    return PythonCodeNode.from_function(
        func=transform_data,
        name="customer_tier_calculator",
        description="Calculate customer tier based on purchase total",
        input_schema=input_schema,
        output_schema=output_schema,
    )


def main():
    """Create and execute a basic data processing workflow."""

    # Create data directory if it doesn't exist
    data_dir = Path("examples/data")
    data_dir.mkdir(exist_ok=True)
    output_dir = data_dir / "outputs"
    output_dir.mkdir(exist_ok=True)

    # Step 1: Create a workflow
    print("Creating workflow...")
    workflow = Workflow(
        workflow_id="basic_customer_processing",
        name="basic_customer_processing",
        description="Simple ETL workflow for customer data",
    )

    # Step 2: Create and add nodes
    print("Creating workflow nodes...")

    # Create input node - reads CSV data
    csv_reader = CSVReader(file_path=str(data_dir / "customers.csv"), headers=True)

    # Create transformation node
    transformer = create_data_transformer()

    # Create output node - writes processed data
    csv_writer = CSVWriter(file_path=str(output_dir / "processed_customers.csv"))

    # Add nodes to workflow
    workflow.add_node(node_id="reader", node_or_type=csv_reader)
    workflow.add_node(node_id="transformer", node_or_type=transformer)
    workflow.add_node(node_id="writer", node_or_type=csv_writer)

    # Step 3: Connect nodes
    print("Connecting nodes...")
    workflow.connect(
        source_node="reader", target_node="transformer", mapping={"data": "data"}
    )
    workflow.connect(
        source_node="transformer", target_node="writer", mapping={"data": "data"}
    )

    # Step 4: Validate workflow
    print("Validating workflow...")
    try:
        workflow.validate()
        print("✓ Workflow validation successful!")
    except Exception as e:
        print(f"✗ Workflow validation failed: {e}")
        return 1

    # Step 5: Visualize workflow (optional)
    print("Creating workflow visualization...")
    try:
        visualizer = WorkflowVisualizer()
        visualizer.visualize(
            workflow, output_path=str(output_dir / "basic_workflow.png")
        )
        print(f"✓ Visualization saved to {output_dir / 'basic_workflow.png'}")
    except Exception as e:
        print(f"Warning: Could not create visualization: {e}")

    # Step 6: Export workflow definition
    print("\nExporting workflow definition...")
    try:
        workflow.export_to_kailash(
            output_path=str(output_dir / "basic_workflow.yaml"), format="yaml"
        )
        print(f"✓ Workflow exported to {output_dir / 'basic_workflow.yaml'}")
    except Exception as e:
        print(f"Warning: Could not export workflow: {e}")

    # Step 7: Run workflow
    print("\nExecuting workflow...")
    try:
        runner = LocalRuntime(debug=True)
        results, run_id = runner.execute(workflow)

        print("✓ Workflow completed successfully!")
        print(f"  Run ID: {run_id}")
        print(f"  Results: {len(results)} nodes executed")

        # Show sample output
        if results:
            print("\nSample output from workflow:")
            for node_id, output in results.items():
                if isinstance(output, dict) and "data" in output:
                    data_count = (
                        len(output["data"]) if isinstance(output["data"], list) else 1
                    )
                    print(f"  {node_id}: {data_count} records processed")
                else:
                    print(f"  {node_id}: {output}")

    except Exception as e:
        print(f"✗ Workflow execution failed: {e}")
        import traceback

        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    # Create sample data if it doesn't exist
    sample_data_file = Path("examples/data/customers.csv")
    if not sample_data_file.exists():
        print("Creating sample customer data...")
        sample_data = pd.DataFrame(
            {
                "customer_id": [1, 2, 3, 4, 5],
                "name": ["Alice", "Bob", "Charlie", "David", "Eve"],
                "email": [
                    "alice@example.com",
                    "bob@example.com",
                    "charlie@example.com",
                    "david@example.com",
                    "eve@example.com",
                ],
                "purchase_total": [150.50, 750.25, 50.75, 1200.00, 450.80],
            }
        )
        sample_data.to_csv(sample_data_file, index=False)
        print(f"Created {sample_data_file}")

    sys.exit(main())

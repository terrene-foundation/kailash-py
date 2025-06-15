#!/usr/bin/env python3
"""
Basic ETL Workflow Pattern

This workflow demonstrates a simple ETL (Extract, Transform, Load) pattern:
1. Reads customer data from a CSV file
2. Transforms the data by calculating customer tiers
3. Writes the enriched data to a new CSV file

Industry: General
Pattern: ETL (Extract, Transform, Load)
Nodes Used: CSVReaderNode, PythonCodeNode, CSVWriterNode
"""

import sys
from pathlib import Path
from typing import Any

import pandas as pd

# Add parent directories to path for imports
project_root = Path(__file__).parent.parent.parent.parent.parent
sys.path.insert(0, str(project_root / "src"))
sys.path.insert(0, str(project_root))

from kailash.nodes.base import NodeParameter
from kailash.nodes.code.python import PythonCodeNode
from kailash.nodes.data.readers import CSVReaderNode
from kailash.nodes.data.writers import CSVWriterNode
from kailash.runtime.local import LocalRuntime
from kailash.workflow.graph import Workflow
from kailash.workflow.visualization import WorkflowVisualizer


def create_data_transformer():
    """Create a Python node for data transformation."""

    def transform_data(data: list) -> list:
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
        elif "tier" in df.columns:
            # If tier already exists, convert to title case
            df["customer_tier"] = df["tier"].str.title()

        # Return the list directly - PythonCodeNode will wrap it as {"result": <return_value>}
        return df.to_dict(orient="records")

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
        "result": NodeParameter(
            name="result",
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
    """Create and execute a basic ETL workflow."""

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
    # Use a temporary file for this example
    import tempfile

    temp_dir = tempfile.mkdtemp()
    input_file = Path(temp_dir) / "customers.csv"

    # Create sample data
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
    sample_data.to_csv(input_file, index=False)
    print(f"Created {input_file}")

    csv_reader = CSVReaderNode(file_path=str(input_file), headers=True)

    # Create transformation node
    transformer = create_data_transformer()

    # Create output node - writes processed data
    output_file = Path(temp_dir) / "processed_customers.csv"
    csv_writer = CSVWriterNode(file_path=str(output_file))

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
        source_node="transformer", target_node="writer", mapping={"result": "data"}
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
        visualizer = WorkflowVisualizer(workflow)
        viz_path = Path(temp_dir) / "basic_workflow.png"
        visualizer.visualize(output_path=str(viz_path))
        print(f"✓ Visualization saved to {viz_path}")
    except Exception as e:
        print(f"Warning: Could not create visualization: {e}")

    # Step 6: Export workflow definition
    print("\nExporting workflow definition...")
    try:
        export_path = Path(temp_dir) / "basic_workflow.yaml"
        workflow.export_to_kailash(output_path=str(export_path), format="yaml")
        print(f"✓ Workflow exported to {export_path}")
    except Exception as e:
        print(f"Warning: Could not export workflow: {e}")

    # Step 7: Run workflow
    print("\nExecuting workflow...")
    try:
        runner = LocalRuntime(debug=True, enable_security=False)
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
    import sys

    sys.exit(main())

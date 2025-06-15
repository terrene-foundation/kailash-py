#!/usr/bin/env python3
"""
CSV Data Filtering Workflow

This workflow demonstrates how to:
1. Read customer data from a CSV file
2. Filter records based on a threshold value
3. Calculate statistics on filtered data
4. Write results to output files

Industry: General
Pattern: Data Processing - Filtering and Analysis
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
from kailash.nodes.data import CSVReaderNode, CSVWriterNode
from kailash.runtime.local import LocalRuntime
from kailash.workflow import Workflow


def main():
    """Create and execute a data filtering workflow."""

    # Setup paths - use temporary directory for testing
    import tempfile

    temp_dir = tempfile.mkdtemp()
    input_file = Path(temp_dir) / "financial_transactions.csv"
    output_dir = Path(temp_dir) / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Create sample data
    print("Creating sample financial transaction data...")
    data = pd.DataFrame(
        {
            "transaction_id": [f"TXN{i:04d}" for i in range(1, 11)],
            "customer": [
                "Alice",
                "Bob",
                "Charlie",
                "David",
                "Eve",
                "Frank",
                "Grace",
                "Henry",
                "Ivy",
                "Jack",
            ],
            "amount": [1500, 800, 2500, 600, 1200, 3000, 450, 1800, 950, 2200],
            "category": [
                "Electronics",
                "Groceries",
                "Travel",
                "Utilities",
                "Shopping",
                "Travel",
                "Food",
                "Electronics",
                "Shopping",
                "Travel",
            ],
            "status": [
                "completed",
                "completed",
                "pending",
                "completed",
                "completed",
                "completed",
                "failed",
                "completed",
                "completed",
                "pending",
            ],
        }
    )
    data.to_csv(input_file, index=False)
    print(f"Created {input_file}")

    # Step 1: Create a workflow
    print("Creating data filtering workflow...")
    workflow = Workflow(
        workflow_id="csv_data_filtering",
        name="CSV Data Filtering Workflow",
        description="Filter and analyze customer transaction data",
    )

    # Step 2: Create CSV reader node
    print("Setting up nodes...")
    csv_reader = CSVReaderNode(file_path=str(input_file), headers=True, delimiter=",")

    # Step 3: Create custom Python node for filtering
    def filter_high_value_customers(
        data: list, column_name: str = "amount", threshold: float = 1000.0
    ) -> dict[str, Any]:
        """Filter customers based on a threshold value."""
        df = pd.DataFrame(data)

        # Convert column to numeric
        df[column_name] = pd.to_numeric(df[column_name], errors="coerce")

        # Filter based on threshold
        filtered_df = df[df[column_name] > threshold]

        # Return with proper result wrapper for PythonCodeNode
        # Convert numpy types to Python native types for JSON serialization
        return {
            "filtered_data": filtered_df.to_dict(orient="records"),
            "count": int(len(filtered_df)),
            "total_value": float(filtered_df[column_name].sum()),
            "average_value": (
                float(filtered_df[column_name].mean()) if len(filtered_df) > 0 else 0.0
            ),
        }

    # Define schemas for the Python node
    filter_node = PythonCodeNode.from_function(
        func=filter_high_value_customers,
        name="high_value_filter",
        description="Filter customers with high claim amounts",
        input_schema={
            "data": NodeParameter(name="data", type=list, required=True),
            "column_name": NodeParameter(
                name="column_name",
                type=str,
                required=False,
                default="amount",
                description="Column to filter on",
            ),
            "threshold": NodeParameter(
                name="threshold",
                type=float,
                required=False,
                default=1000.0,
                description="Minimum value threshold",
            ),
        },
        output_schema={
            "result": NodeParameter(
                name="result",
                type=dict,
                required=True,
                description="Filter results containing filtered_data, count, total_value, and average_value",
            ),
        },
    )

    # Step 4: Create CSV writer node for results
    csv_writer = CSVWriterNode(
        file_path=str(output_dir / "high_value_customers.csv")
        # headers will be auto-detected from the dict keys
    )

    # Step 5: Add nodes to workflow
    print("Adding nodes to workflow...")
    workflow.add_node(node_id="csv_reader", node_or_type=csv_reader)
    workflow.add_node(node_id="filter", node_or_type=filter_node)
    workflow.add_node(node_id="csv_writer", node_or_type=csv_writer)

    # Step 6: Connect the nodes
    print("Connecting workflow nodes...")
    workflow.connect("csv_reader", "filter", {"data": "data"})
    # PythonCodeNode wraps output in 'result', so access the nested filtered_data
    workflow.connect("filter", "csv_writer", {"result.filtered_data": "data"})

    # Step 7: Execute the workflow
    print("\nExecuting workflow...")
    try:
        runner = LocalRuntime(debug=True, enable_security=False)
        results, run_id = runner.execute(workflow)

        # Step 8: Display results
        print("✓ Workflow completed successfully!")
        print(f"  Run ID: {run_id}")

        filter_output = results.get("filter", {}).get("result", {})
        if filter_output:
            print("\nResults:")
            print(f"  Found {filter_output.get('count', 0)} high-value transactions")
            print(f"  Total value: ${filter_output.get('total_value', 0):,.2f}")
            print(f"  Average value: ${filter_output.get('average_value', 0):,.2f}")
        print(f"\nResults saved to: {output_dir / 'high_value_customers.csv'}")

    except Exception as e:
        print(f"✗ Workflow execution failed: {e}")
        import traceback

        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())

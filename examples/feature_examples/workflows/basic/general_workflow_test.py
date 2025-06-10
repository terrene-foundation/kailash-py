"""Example demonstrating a complete workflow with data nodes and custom Python nodes.

This example shows how to:
1. Create a workflow with multiple nodes
2. Connect nodes to create a data pipeline
3. Execute the workflow
4. Access results from individual nodes
5. Save and load workflows
"""

from pathlib import Path
from typing import Any, Dict

import pandas as pd

from examples.utils.paths import get_output_dir
from kailash.nodes.base import NodeParameter
from kailash.nodes.code.python import PythonCodeNode
from kailash.nodes.data.readers import CSVReaderNode
from kailash.nodes.data.writers import CSVWriterNode
from kailash.runtime.local import LocalRuntime
from kailash.workflow.graph import Workflow

# Define paths
sample_directory = Path("../tests/sample_data")
output_directory = get_output_dir()
output_directory.mkdir(exist_ok=True)


def create_filter_node():
    """Create a custom Python node for filtering data."""

    def custom_filter(data: list, column_name: str, threshold: float) -> Dict[str, Any]:
        """Filter data based on threshold and return additional statistics."""
        df = pd.DataFrame(data)

        # Convert column to float for comparison
        df[column_name] = pd.to_numeric(df[column_name], errors="coerce")

        filtered_df = df[df[column_name] > threshold]

        return {
            "filtered_data": filtered_df.to_dict(orient="records"),
            "row_count": len(filtered_df),
        }

    # Define schemas for validation
    input_schema = {
        "data": NodeParameter(
            name="data", type=list, required=True, description="List of data records"
        ),
        "column_name": NodeParameter(
            name="column_name",
            type=str,
            required=True,
            description="Column name to filter on",
        ),
        "threshold": NodeParameter(
            name="threshold",
            type=float,
            required=True,
            description="Threshold value for filtering",
        ),
    }

    output_schema = {
        "filtered_data": NodeParameter(
            name="filtered_data",
            type=list,
            required=True,
            description="Filtered data records",
        ),
        "row_count": NodeParameter(
            name="row_count",
            type=int,
            required=True,
            description="Number of filtered rows",
        ),
    }

    return PythonCodeNode.from_function(
        func=custom_filter,
        name="threshold_filter",
        description="Filter data based on threshold",
        input_schema=input_schema,
        output_schema=output_schema,
    )


def create_summary_node():
    """Create a custom Python node for data summarization."""

    def summarize_data(
        data: list, group_column: str, value_column: str
    ) -> Dict[str, Any]:
        """Summarize data by group."""
        df = pd.DataFrame(data)

        # Convert value column to numeric for calculations
        df[value_column] = pd.to_numeric(df[value_column], errors="coerce")

        # Group and calculate summary statistics
        summary = df.groupby(group_column)[value_column].agg(["sum", "mean", "count"])
        summary_dict = summary.reset_index().to_dict(orient="records")

        # Calculate grand total
        total = df[value_column].sum()

        return {"summary": summary_dict, "total": total}

    # Define schemas
    input_schema = {
        "data": NodeParameter(
            name="data", type=list, required=True, description="List of data records"
        ),
        "group_column": NodeParameter(
            name="group_column",
            type=str,
            required=True,
            description="Column to group by",
        ),
        "value_column": NodeParameter(
            name="value_column",
            type=str,
            required=True,
            description="Column to summarize",
        ),
    }

    output_schema = {
        "summary": NodeParameter(
            name="summary",
            type=list,
            required=True,
            description="Summary statistics by group",
        ),
        "total": NodeParameter(
            name="total", type=float, required=True, description="Grand total"
        ),
    }

    return PythonCodeNode.from_function(
        func=summarize_data,
        name="data_summarizer",
        description="Summarize data by group",
        input_schema=input_schema,
        output_schema=output_schema,
    )


def main():
    """Create and execute a complete workflow."""
    print("=== Data Processing Workflow Example ===\n")

    # Create workflow
    workflow = Workflow(
        workflow_id="customer_data_processing", name="Customer Data Processing"
    )

    # Step 1: Create nodes
    # CSV reader node
    csv_reader = CSVReaderNode(
        file_path=str(sample_directory / "customer_value.csv"),
        headers=True,
        delimiter=",",
    )

    # Filter node
    filter_node = create_filter_node()

    # Summary node
    summary_node = create_summary_node()

    # CSV writer nodes (data will come from connections)
    csv_writer_filtered = CSVWriterNode(
        file_path=str(output_directory / "filtered_customers.csv"),
        delimiter=",",
        headers=None,  # headers will be auto-detected from dict data
    )

    csv_writer_summary = CSVWriterNode(
        file_path=str(output_directory / "customer_summary.csv"),
        delimiter=",",
        headers=None,  # headers will be auto-detected from dict data
    )

    # Step 2: Add nodes to workflow with configurations
    workflow.add_node(node_id="csv_reader", node_or_type=csv_reader)

    # Add filter node with configuration
    workflow.add_node(
        node_id="filter",
        node_or_type=filter_node,
        config={"column_name": "Total Claim Amount", "threshold": 1000.0},
    )

    # Add summary node with configuration
    workflow.add_node(
        node_id="summary",
        node_or_type=summary_node,
        config={"group_column": "Customer", "value_column": "Total Claim Amount"},
    )

    workflow.add_node(
        node_id="filtered_writer",
        node_or_type=csv_writer_filtered,
    )

    workflow.add_node(
        node_id="summary_writer",
        node_or_type=csv_writer_summary,
    )

    # Step 3: Connect nodes in the workflow
    # CSV Reader -> Filter -> CSV Writer (filtered)
    workflow.connect(
        source_node="csv_reader", target_node="filter", mapping={"data": "data"}
    )

    workflow.connect(
        source_node="filter",
        target_node="filtered_writer",
        mapping={"filtered_data": "data"},
    )

    # CSV Reader -> Summary -> CSV Writer (summary)
    workflow.connect(
        source_node="csv_reader", target_node="summary", mapping={"data": "data"}
    )

    workflow.connect(
        source_node="summary", target_node="summary_writer", mapping={"summary": "data"}
    )

    # Step 4: Execute workflow
    runtime = LocalRuntime(debug=True)

    try:
        results, run_id = runtime.execute(workflow)

        print("Workflow execution completed!\n")

        # Display results
        if "filter" in results:
            filter_result = results["filter"]
            print(
                f"Filtered {filter_result.get('row_count', 0)} customers with claims > $1000"
            )
            print(
                f"Filtered data saved to: {output_directory / 'filtered_customers.csv'}"
            )

        if "summary" in results:
            summary_result = results["summary"]
            print(
                f"\nTotal claim amount across all customers: ${summary_result.get('total', 0):,.2f}"
            )
            print(f"Summary data saved to: {output_directory / 'customer_summary.csv'}")

            # Display top customers
            if "summary" in summary_result:
                summary_df = pd.DataFrame(summary_result["summary"])
                if not summary_df.empty:
                    print("\nTop 5 customers by total claims:")
                    top_customers = summary_df.nlargest(5, "sum")[["Customer", "sum"]]
                    for _, row in top_customers.iterrows():
                        print(f"  {row['Customer']}: ${row['sum']:,.2f}")

    except Exception as e:
        print(f"Workflow execution failed: {e}")
        raise

    # Step 5: Export workflow (commented out due to method not existing)
    # workflow_file = output_directory / 'customer_workflow.yaml'
    # workflow.export_to_kailash(str(workflow_file), format="yaml")
    # print(f"\nWorkflow saved to: {workflow_file}")

    # Step 6: Demonstrate loading and re-running
    print("\n=== Loading and Re-running Workflow ===")
    # For now, skip re-loading as it's not implemented
    print("(Workflow loading functionality not yet implemented)")

    # Step 7: Demonstrate direct node execution (outside workflow)
    print("\n=== Direct Node Execution (outside workflow) ===")

    # Read data directly
    csv_reader_direct = CSVReaderNode(
        file_path=str(sample_directory / "customer_value.csv"), headers=True
    )
    csv_result = csv_reader_direct.execute()

    # Filter with different threshold
    filter_direct = create_filter_node()
    direct_result = filter_direct.execute(
        data=csv_result["data"], column_name="Total Claim Amount", threshold=500.0
    )

    print(
        f"Direct execution: Found {direct_result['row_count']} customers with claims > $500"
    )


if __name__ == "__main__":
    # Create sample data if it doesn't exist
    sample_directory = Path("../tests/sample_data")
    sample_directory.mkdir(parents=True, exist_ok=True)

    if not (sample_directory / "customer_value.csv").exists():
        # Create sample customer data
        sample_data = pd.DataFrame(
            {
                "Customer": ["Alice", "Bob", "Charlie", "David", "Eve"] * 3,
                "Total Claim Amount": [1500, 800, 2500, 600, 1200] * 3,
                "Status": ["Active", "Active", "Inactive", "Active", "Active"] * 3,
                "Region": ["North", "South", "East", "West", "North"] * 3,
            }
        )

        sample_data.to_csv(sample_directory / "customer_value.csv", index=False)
        print("Sample data created at data/test/csv/customer_value.csv\n")

    # Run the workflow example
    main()

"""Simple workflow example connecting CSV reader to Python nodes."""

from pathlib import Path
from typing import Any, Dict

import pandas as pd

from kailash.nodes.base import NodeParameter
from kailash.nodes.code.python import PythonCodeNode
from kailash.nodes.data import CSVReaderNode, CSVWriterNode


def main():
    """Simple example of connecting data nodes to Python nodes."""

    # Setup paths
    sample_dir = Path("../tests/sample_data")
    output_dir = Path("../outputs")
    output_dir.mkdir(exist_ok=True)

    print("=== Simple Node Connection Example ===\n")

    # 1. Create and execute CSV reader
    print("Step 1: Reading CSV data...")
    csv_reader = CSVReaderNode(
        file_path=sample_dir / "customer_value.csv", headers=True, delimiter=","
    )

    # Execute the CSV reader
    csv_data = csv_reader.execute()
    print(f"✓ Read {len(csv_data['data'])} records\n")

    # 2. Create custom Python node for filtering
    print("Step 2: Creating filter node...")

    def filter_high_value(data: list, threshold: float) -> Dict[str, Any]:
        """Filter customers with high claim amounts."""
        df = pd.DataFrame(data)

        # Convert to numeric if needed
        if df["Total Claim Amount"].dtype == "object":
            df["Total Claim Amount"] = pd.to_numeric(
                df["Total Claim Amount"], errors="coerce"
            )

        # Filter based on threshold
        filtered = df[df["Total Claim Amount"] > threshold]

        return {
            "filtered_data": filtered.to_dict(orient="records"),
            "count": len(filtered),
            "total_value": filtered["Total Claim Amount"].sum(),
        }

    # Create node with schemas
    filter_node = PythonCodeNode.from_function(
        func=filter_high_value,
        name="high_value_filter",
        description="Filter customers with claims above threshold",
        input_schema={
            "data": NodeParameter(
                name="data",
                type=list,
                required=True,
                description="List of customer records",
            ),
            "threshold": NodeParameter(
                name="threshold",
                type=float,
                required=True,
                description="Minimum claim amount",
            ),
        },
        output_schema={
            "filtered_data": NodeParameter(
                name="filtered_data",
                type=list,
                required=True,
                description="Filtered records",
            ),
            "count": NodeParameter(
                name="count",
                type=int,
                required=True,
                description="Number of filtered records",
            ),
            "total_value": NodeParameter(
                name="total_value",
                type=float,
                required=True,
                description="Total value of filtered claims",
            ),
        },
    )

    # Execute the filter node with CSV data
    filter_result = filter_node.execute(data=csv_data["data"], threshold=1000.0)

    print(f"✓ Filtered to {filter_result['count']} high-value customers")
    print(f"✓ Total value: ${filter_result['total_value']:,.2f}\n")

    # 3. Create summary node
    print("Step 3: Creating summary node...")

    def summarize_by_region(data: list) -> Dict[str, Any]:
        """Summarize data by region."""
        df = pd.DataFrame(data)

        # Group by region
        summary = df.groupby("Region")["Total Claim Amount"].agg(
            ["count", "sum", "mean"]
        )
        summary = summary.round(2).reset_index()

        return {
            "regional_summary": summary.to_dict(orient="records"),
            "top_region": summary.loc[summary["sum"].idxmax(), "Region"],
        }

    summary_output_schema = {
        "regional_summary": NodeParameter(
            name="regional_summary",
            type=list,
            required=True,
            description="Summary data by region",
        ),
        "top_region": NodeParameter(
            name="top_region",
            type=str,
            required=True,
            description="Region with highest total",
        ),
    }

    summary_node = PythonCodeNode.from_function(
        func=summarize_by_region,
        name="regional_summary",
        description="Summarize claims by region",
        output_schema=summary_output_schema,
    )

    # Execute summary with filtered data
    summary_result = summary_node.execute(data=filter_result["filtered_data"])

    print("✓ Created regional summary")
    print(f"✓ Top region: {summary_result['top_region']}\n")

    # 4. Create CSV writer and save results
    print("Step 4: Saving results to CSV...")

    # Save filtered data
    filtered_writer = CSVWriterNode(
        file_path=str(output_dir / "high_value_customers.csv")
        # headers will be auto-detected from the dict keys
    )

    filtered_writer.execute(data=filter_result["filtered_data"])
    print(f"✓ Saved filtered data to {output_dir / 'high_value_customers.csv'}")

    # Save summary
    summary_writer = CSVWriterNode(
        file_path=str(output_dir / "regional_summary.csv")
        # headers will be auto-detected from the dict keys
    )

    summary_writer.execute(data=summary_result["regional_summary"])
    print(f"✓ Saved summary to {output_dir / 'regional_summary.csv'}")

    # 5. Display final summary
    print("\n=== Results Summary ===")
    print(f"Original records: {len(csv_data['data'])}")
    print(f"Filtered records: {filter_result['count']}")
    print(f"Total value: ${filter_result['total_value']:,.2f}")
    print(f"Top region: {summary_result['top_region']}")

    print("\nRegional breakdown:")
    for region in summary_result["regional_summary"]:
        print(
            f"  {region['Region']}: {region['count']} claims, ${region['sum']:,.2f} total"
        )

    # 6. Chain multiple Python nodes
    print("\n\n=== Chaining Multiple Nodes ===")

    # Create another processing node
    def add_risk_score(data: list) -> Dict[str, Any]:
        """Add risk scores to customer data."""
        df = pd.DataFrame(data)

        # Calculate risk score based on claim amount
        df["risk_score"] = pd.cut(
            df["Total Claim Amount"],
            bins=[0, 500, 1500, float("inf")],
            labels=["LOW", "MEDIUM", "HIGH"],
        )

        return {
            "enriched_data": df.to_dict(orient="records"),
            "risk_distribution": df["risk_score"].value_counts().to_dict(),
        }

    risk_output_schema = {
        "enriched_data": NodeParameter(
            name="enriched_data",
            type=list,
            required=True,
            description="Data with risk scores added",
        ),
        "risk_distribution": NodeParameter(
            name="risk_distribution",
            type=dict,
            required=True,
            description="Distribution of risk scores",
        ),
    }

    risk_node = PythonCodeNode.from_function(
        func=add_risk_score,
        name="risk_scorer",
        description="Add risk scores to customer data",
        output_schema=risk_output_schema,
    )

    # Execute risk scoring on filtered data
    risk_result = risk_node.execute(data=filter_result["filtered_data"])

    print("Risk distribution for high-value customers:")
    for risk, count in risk_result["risk_distribution"].items():
        print(f"  {risk}: {count} customers")


if __name__ == "__main__":
    # Ensure sample data exists
    sample_dir = Path("../tests/sample_data")
    if not (sample_dir / "customer_value.csv").exists():
        print("Creating sample data...")

        # Create new sample data
        sample_dir.mkdir(parents=True, exist_ok=True)
        data = pd.DataFrame(
            {
                "Customer": ["Alice", "Bob", "Charlie", "David", "Eve"] * 10,
                "Total Claim Amount": [1500.50, 800.75, 2500.00, 600.25, 1200.80] * 10,
                "Status": ["Active", "Active", "Inactive", "Active", "Active"] * 10,
                "Region": ["North", "South", "East", "West", "North"] * 10,
            }
        )

        data.to_csv(sample_dir / "customer_value.csv", index=False)
        print("Sample data created.\n")

    main()

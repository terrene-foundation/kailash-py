"""Visual workflow example with data nodes and Python nodes."""

from pathlib import Path
from typing import Any, Dict

import pandas as pd

from examples.utils.data_paths import (
    ensure_output_dir_exists,
    get_output_data_path,
    get_test_data_path,
)
from examples.utils.paths import get_output_dir
from kailash.nodes.base import NodeParameter
from kailash.nodes.code.python import PythonCodeNode
from kailash.nodes.data import CSVReaderNode, CSVWriterNode
from kailash.runtime import LocalRuntime
from kailash.workflow import Workflow
from kailash.workflow.visualization import WorkflowVisualizer


def create_data_pipeline():
    """Create a complete data processing pipeline."""

    # Create workflow
    workflow = Workflow(
        workflow_id="customer_data_pipeline",
        name="Customer Data Pipeline",
        description="Process customer claims data through multiple stages",
    )

    # 1. Input: CSV Reader
    csv_reader = CSVReaderNode(
        file_path=str(get_test_data_path("customer_value.csv")),
        headers=True,
        delimiter=",",
    )
    csv_reader.id = "csv_input"  # Set custom ID for clarity

    # 2. Filter: High-value customers
    def filter_high_value(data: list, threshold: float = 1000.0) -> Dict[str, Any]:
        """Filter customers with claims above threshold."""
        df = pd.DataFrame(data)
        filtered = df[df["Total Claim Amount"] > threshold]

        return {
            "filtered_data": filtered.to_dict(orient="records"),
            "count": len(filtered),
            "avg_claim": filtered["Total Claim Amount"].mean(),
        }

    high_value_filter = PythonCodeNode.from_function(
        func=filter_high_value,
        name="HighValueFilter",
        description="Filter customers with high claim amounts",
        input_schema={
            "data": NodeParameter(name="data", type=list, required=True),
            "threshold": NodeParameter(
                name="threshold", type=float, required=False, default=1000.0
            ),
        },
    )
    high_value_filter.id = "high_value_filter"

    # 3. Transform: Add risk score
    def add_risk_score(data: list) -> Dict[str, Any]:
        """Add risk score based on claim amount."""
        df = pd.DataFrame(data)

        # Calculate risk score (simple example)
        df["risk_score"] = df["Total Claim Amount"].apply(
            lambda x: "HIGH" if x > 2000 else "MEDIUM" if x > 1000 else "LOW"
        )

        # Add processing timestamp
        df["processed_at"] = pd.Timestamp.now().isoformat()

        return {
            "enriched_data": df.to_dict(orient="records"),
            "risk_summary": df["risk_score"].value_counts().to_dict(),
        }

    risk_scorer = PythonCodeNode.from_function(
        func=add_risk_score,
        name="RiskScorer",
        description="Add risk scores to customer data",
    )
    risk_scorer.id = "risk_scorer"

    # 4. Aggregate: Summary statistics
    def create_summary(data: list) -> Dict[str, Any]:
        """Create summary statistics by customer."""
        df = pd.DataFrame(data)

        # Group by customer and risk score
        summary = (
            df.groupby(["Customer", "risk_score"])["Total Claim Amount"]
            .agg(["count", "sum", "mean"])
            .reset_index()
        )

        # Overall statistics
        overall_stats = {
            "total_customers": df["Customer"].nunique(),
            "total_claims": len(df),
            "total_amount": df["Total Claim Amount"].sum(),
            "high_risk_count": len(df[df["risk_score"] == "HIGH"]),
        }

        return {
            "summary_data": summary.to_dict(orient="records"),
            "overall_stats": overall_stats,
        }

    summarizer = PythonCodeNode.from_function(
        func=create_summary,
        name="DataSummarizer",
        description="Create summary statistics",
    )
    summarizer.id = "summarizer"

    # 5. Output: CSV Writers
    output_dir = get_output_dir()
    output_dir.mkdir(exist_ok=True)

    enriched_writer = CSVWriterNode(
        file_path=str(output_dir / "enriched_customers.csv"), headers=True
    )
    enriched_writer.id = "enriched_output"

    summary_writer = CSVWriterNode(
        file_path=str(output_dir / "customer_summary.csv"), headers=True
    )
    summary_writer.id = "summary_output"

    # Add all nodes to workflow
    workflow.add_node("csv_input", csv_reader)
    workflow.add_node("high_value_filter", high_value_filter)
    workflow.add_node("risk_scorer", risk_scorer)
    workflow.add_node("summarizer", summarizer)
    workflow.add_node("enriched_output", enriched_writer)
    workflow.add_node("summary_output", summary_writer)

    # Connect nodes
    # CSV -> Filter
    workflow.connect("csv_input", "high_value_filter", mapping={"data": "data"})

    # Filter -> Risk Scorer
    workflow.connect(
        "high_value_filter", "risk_scorer", mapping={"filtered_data": "data"}
    )

    # Risk Scorer -> Enriched Output
    workflow.connect(
        "risk_scorer", "enriched_output", mapping={"enriched_data": "data"}
    )

    # Risk Scorer -> Summarizer
    workflow.connect("risk_scorer", "summarizer", mapping={"enriched_data": "data"})

    # Summarizer -> Summary Output
    workflow.connect("summarizer", "summary_output", mapping={"summary_data": "data"})

    return workflow


def main():
    """Execute the data pipeline and visualize it."""

    # Create sample data if needed
    sample_dir = Path("../tests/sample_data")
    sample_dir.mkdir(parents=True, exist_ok=True)

    if not (sample_dir / "customer_value.csv").exists():
        # Create more complex sample data
        import random

        customers = [
            "Alice",
            "Bob",
            "Charlie",
            "David",
            "Eve",
            "Frank",
            "Grace",
            "Henry",
        ]
        data = []

        for _ in range(50):  # 50 records
            customer = random.choice(customers)
            amount = random.randint(100, 5000)
            status = random.choice(["Active", "Inactive"])
            region = random.choice(["North", "South", "East", "West"])

            data.append(
                {
                    "Customer": customer,
                    "Total Claim Amount": amount,
                    "Status": status,
                    "Region": region,
                }
            )

        df = pd.DataFrame(data)
        df.to_csv(sample_dir / "customer_value.csv", index=False)
        print("Created sample data with 50 records\n")

    # Create the workflow
    workflow = create_data_pipeline()

    # Visualize the workflow
    print("=== Workflow Structure ===")
    visualizer = WorkflowVisualizer(workflow)

    # Save workflow diagram
    output_dir = get_output_dir()
    output_dir.mkdir(exist_ok=True)

    try:
        visualizer.visualize(output_dir / "workflow_diagram.png")
        print(f"Workflow diagram saved to: {output_dir / 'workflow_diagram.png'}")
    except Exception as e:
        print(f"Could not create visual diagram: {e}")

    # Print text representation
    print("\nWorkflow connections:")
    for source, target, mapping in workflow._connections:
        print(f"  {source} -> {target} (mapping: {mapping})")

    # Execute the workflow
    print("\n=== Executing Workflow ===")
    runner = LocalRuntime(debug=True)
    results, run_id = runner.execute(workflow)

    # Display results
    print("\nExecution Results:")

    # Get outputs from each node
    for node_id in ["high_value_filter", "risk_scorer", "summarizer"]:
        output = results.get(node_id, {})
        if output:
            print(f"\n{node_id}:")
            if "count" in output:
                print(f"  Records processed: {output['count']}")
            if "avg_claim" in output:
                print(f"  Average claim: ${output['avg_claim']:,.2f}")
            if "risk_summary" in output:
                print(f"  Risk distribution: {output['risk_summary']}")
            if "overall_stats" in output:
                stats = output["overall_stats"]
                print(f"  Total customers: {stats['total_customers']}")
                print(f"  Total claims: {stats['total_claims']}")
                print(f"  Total amount: ${stats['total_amount']:,.2f}")
                print(f"  High risk claims: {stats['high_risk_count']}")

    print("\nOutput files created:")
    print(f"  - {output_dir / 'enriched_customers.csv'}")
    print(f"  - {output_dir / 'customer_summary.csv'}")

    # Save the workflow for reuse
    workflow_file = output_dir / "customer_pipeline.yaml"
    workflow.save(workflow_file)
    print(f"\nWorkflow saved to: {workflow_file}")

    # Show workflow summary
    print("\n=== Workflow Summary ===")
    print(f"Name: {workflow.name}")
    print(f"Description: {workflow.description}")
    print(f"Nodes: {len(workflow.nodes)}")
    print(f"Connections: {len(workflow._connections)}")

    print("\nNodes in workflow:")
    for node in workflow.nodes.values():
        print(f"  - {node.id}: {node.__class__.__name__}")
        if hasattr(node, "metadata") and node.metadata:
            print(f"    Description: {node.metadata.description}")


if __name__ == "__main__":
    main()

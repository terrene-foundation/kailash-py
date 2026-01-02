#!/usr/bin/env python3
"""
Customer Analytics Workflow - Production Business Solution

A comprehensive customer analysis workflow demonstrating:
1. Multi-source data integration (CSV customer data + JSON transactions)
2. Data validation and cleansing
3. Customer segmentation by value
4. Transaction analysis with segment correlation
5. Comprehensive reporting with multiple output formats

Business Value:
- Customer lifetime value analysis
- Segment-based revenue reporting
- Transaction pattern insights
- Multi-format output for different stakeholders
"""

import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

# Add the parent directory to the path to import kailash
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root / "src"))
sys.path.insert(0, str(project_root))

# Add examples directory to path for utils import
examples_dir = project_root / "examples"
sys.path.insert(0, str(examples_dir))

from kailash.nodes.base import NodeParameter
from kailash.nodes.code.python import PythonCodeNode
from kailash.nodes.data.readers import CSVReaderNode, JSONReaderNode
from kailash.nodes.data.writers import CSVWriterNode, JSONWriterNode
from kailash.runtime.local import LocalRuntime
from kailash.tracking.manager import TaskManager
from kailash.tracking.storage.filesystem import FileSystemStorage
from kailash.workflow.graph import Workflow
from kailash.workflow.visualization import WorkflowVisualizer

from examples.utils.paths import get_data_dir


def create_data_validator():
    """Create a node that validates customer data."""

    def validate_data(data: list) -> dict[str, Any]:
        """Validate customer data for required fields."""
        df = pd.DataFrame(data)

        # Check required columns
        required_columns = ["customer_id", "name", "email", "purchase_total"]
        missing_columns = [col for col in required_columns if col not in df.columns]

        if missing_columns:
            raise ValueError(f"Missing required columns: {missing_columns}")

        # Validate data types
        df["purchase_total"] = pd.to_numeric(df["purchase_total"], errors="coerce")

        # Remove invalid records
        valid_df = df.dropna(subset=required_columns)
        invalid_count = len(df) - len(valid_df)

        return {
            "data": valid_df.to_dict(orient="records"),
            "valid_count": len(valid_df),
            "invalid_count": invalid_count,
        }

    return PythonCodeNode.from_function(
        func=validate_data,
        name="data_validator",
        description="Validate customer data",
    )


def create_customer_segmenter():
    """Create a node that segments customers."""

    def segment_customers(data: list) -> dict[str, Any]:
        """Segment customers by purchase amount."""
        df = pd.DataFrame(data)
        df["purchase_total"] = pd.to_numeric(df["purchase_total"], errors="coerce")

        # Segment customers
        conditions = [
            df["purchase_total"] >= 1000,
            (df["purchase_total"] >= 500) & (df["purchase_total"] < 1000),
            df["purchase_total"] < 500,
        ]
        choices = ["high_value", "medium_value", "low_value"]

        df["segment"] = np.select(conditions, choices, default="unknown")

        # Create segment summaries
        segment_summary = df.groupby("segment")["purchase_total"].agg(
            ["count", "mean", "sum"]
        )

        return {
            "data": df.to_dict(orient="records"),
            "segment_summary": segment_summary.to_dict(orient="index"),
        }

    return PythonCodeNode.from_function(
        func=segment_customers,
        name="customer_segmenter",
        description="Segment customers by value",
    )


def create_transaction_analyzer():
    """Create a node that analyzes transaction data."""

    def analyze_transactions(data: list, customer_data: list) -> dict[str, Any]:
        """Analyze transactions and join with customer data."""
        transactions_df = pd.DataFrame(data)
        customers_df = pd.DataFrame(customer_data)

        # Ensure numeric types and consistent customer_id format
        if "amount" in transactions_df.columns:
            transactions_df["amount"] = pd.to_numeric(
                transactions_df["amount"], errors="coerce"
            )

        # Convert customer_id to consistent type (string)
        transactions_df["customer_id"] = transactions_df["customer_id"].astype(str)
        customers_df["customer_id"] = customers_df["customer_id"].astype(str)

        # Join with customer data
        merged_df = pd.merge(
            transactions_df,
            customers_df[["customer_id", "segment"]],
            on="customer_id",
            how="left",
        )

        # Calculate metrics
        metrics = merged_df.groupby("segment")["amount"].agg(["count", "mean", "sum"])

        return {
            "data": merged_df.to_dict(orient="records"),
            "metrics": metrics.to_dict(orient="index"),
        }

    return PythonCodeNode.from_function(
        func=analyze_transactions,
        name="transaction_analyzer",
        description="Analyze transaction data",
    )


def create_report_generator():
    """Create a node that generates a summary report."""

    def generate_report(
        customer_data: list, transaction_metrics: dict
    ) -> dict[str, Any]:
        """Generate a comprehensive report."""
        df = pd.DataFrame(customer_data)

        # Create report structure
        report = {
            "total_customers": len(df),
            "segments": df["segment"].value_counts().to_dict(),
            "revenue_by_segment": {},
            "transaction_metrics": transaction_metrics,
            "generated_at": pd.Timestamp.now().isoformat(),
        }

        # Calculate revenue by segment
        for segment in df["segment"].unique():
            segment_df = df[df["segment"] == segment]
            report["revenue_by_segment"][segment] = float(
                segment_df["purchase_total"].sum()
            )

        return {"report": report}

    return PythonCodeNode.from_function(
        func=generate_report,
        name="report_generator",
        description="Generate summary report",
    )


def main():
    """Execute the complex workflow with task tracking."""

    # Create directories
    data_dir = get_data_dir()
    output_dir = data_dir / "outputs"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Initialize task manager
    print("Initializing task manager...")
    storage = FileSystemStorage(base_path=str(data_dir / "tasks"))
    task_manager = TaskManager(storage_backend=storage)

    try:
        # Step 1: Create workflow
        print("\nCreating complex workflow...")
        workflow = Workflow(
            workflow_id="complex_customer_analysis",
            name="complex_customer_analysis",
            description="Multi-branch customer analysis workflow",
        )

        # Step 2: Create nodes
        print("Creating workflow nodes...")

        # Data readers
        customer_reader = CSVReaderNode(
            file_path=str(data_dir / "customers_with_purchases.csv"), headers=True
        )

        transaction_reader = JSONReaderNode(
            file_path=str(data_dir / "transactions.json")
        )

        # Processing nodes
        validator = create_data_validator()
        segmenter = create_customer_segmenter()
        analyzer = create_transaction_analyzer()
        reporter = create_report_generator()

        # Output writers
        detailed_writer = CSVWriterNode(
            file_path=str(output_dir / "detailed_analysis.csv")
        )

        segment_writer = CSVWriterNode(
            file_path=str(output_dir / "customer_segments.csv")
        )

        # Note: JSONWriter expects data parameter, but in workflow mode
        # data comes from connections, so we need to fix this usage
        report_writer = JSONWriterNode(
            file_path=str(output_dir / "analysis_report.json"),
            data={},  # Placeholder, will be overridden by workflow
        )

        # Add nodes to workflow
        workflow.add_node(node_id="customer_reader", node_or_type=customer_reader)
        workflow.add_node(node_id="transaction_reader", node_or_type=transaction_reader)
        workflow.add_node(node_id="validator", node_or_type=validator)
        workflow.add_node(node_id="segmenter", node_or_type=segmenter)
        workflow.add_node(node_id="analyzer", node_or_type=analyzer)
        workflow.add_node(node_id="reporter", node_or_type=reporter)
        workflow.add_node(node_id="detailed_writer", node_or_type=detailed_writer)
        workflow.add_node(node_id="segment_writer", node_or_type=segment_writer)
        workflow.add_node(node_id="report_writer", node_or_type=report_writer)

        # Step 3: Connect nodes
        print("Connecting workflow nodes...")

        # Main branch: customer processing
        workflow.connect("customer_reader", "validator", {"data": "data"})
        # Use dot notation to access nested result data
        workflow.connect("validator", "segmenter", {"result.data": "data"})

        # Transaction analysis branch
        workflow.connect("transaction_reader", "analyzer", {"data": "data"})
        workflow.connect("segmenter", "analyzer", {"result.data": "customer_data"})

        # Report generation
        workflow.connect("segmenter", "reporter", {"result.data": "customer_data"})
        workflow.connect(
            "analyzer", "reporter", {"result.metrics": "transaction_metrics"}
        )

        # Output branches
        workflow.connect("segmenter", "segment_writer", {"result.data": "data"})
        workflow.connect("analyzer", "detailed_writer", {"result.data": "data"})
        workflow.connect("reporter", "report_writer", {"result.report": "data"})

        # Step 4: Create workflow run
        print("\nCreating workflow run...")
        run_id = task_manager.create_run(
            workflow_name=workflow.name,
            metadata={
                "description": "Multi-source customer analysis workflow",
                "nodes": len(workflow.nodes),
            },
        )
        print(f"Run created: {run_id}")

        # Step 5: Validate workflow
        print("\nValidating workflow...")
        workflow.validate()
        print("✓ Workflow validation successful!")

        # Step 6: Visualize workflow
        print("\nCreating workflow visualization...")
        try:
            visualizer = WorkflowVisualizer()
            visualizer.visualize(
                workflow, output_path=str(output_dir / "complex_workflow.png")
            )
            print(f"✓ Visualization saved to {output_dir / 'complex_workflow.png'}")
        except Exception as e:
            print(f"Warning: Could not create visualization: {e}")

        # Step 7: Execute workflow
        print("\nExecuting workflow...")
        runner = LocalRuntime(debug=True)
        task_manager.update_run_status(run_id, status="running")

        results, exec_run_id = runner.execute(workflow, task_manager=task_manager)

        # Update task status
        task_manager.update_run_status(run_id, status="completed")

        print("\n✓ Workflow completed successfully!")
        print(f"  Run ID: {exec_run_id}")
        print(f"  Nodes executed: {len(results)}")

        # Show outputs
        print("\nWorkflow outputs:")
        for node_id, output in results.items():
            if isinstance(output, dict):
                print(f"  {node_id}: {list(output.keys())}")
            else:
                print(f"  {node_id}: {type(output).__name__}")

        # Step 8: Export workflow
        print("\nExporting workflow...")
        workflow.export_to_kailash(
            output_path=str(output_dir / "complex_workflow.yaml"), format="yaml"
        )
        print(f"✓ Workflow exported to {output_dir / 'complex_workflow.yaml'}")

    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback

        traceback.print_exc()

        # Update run status if it exists
        if "run_id" in locals():
            task_manager.update_run_status(run_id, status="failed", error=str(e))
        return 1

    return 0


if __name__ == "__main__":
    # Create sample data if needed
    data_dir = get_data_dir()
    data_dir.mkdir(exist_ok=True)

    # Create sample customer data
    customer_file = data_dir / "customers.csv"
    if not customer_file.exists():
        print("Creating sample customer data...")
        customers = pd.DataFrame(
            {
                "customer_id": range(1, 21),
                "name": [f"Customer {i}" for i in range(1, 21)],
                "email": [f"customer{i}@example.com" for i in range(1, 21)],
                "purchase_total": np.random.uniform(100, 2000, 20),
            }
        )
        customers.to_csv(customer_file, index=False)
        print(f"Created {customer_file}")

    # Create sample transaction data
    transaction_file = data_dir / "transactions.json"
    if not transaction_file.exists():
        print("Creating sample transaction data...")
        transactions = []
        for i in range(100):
            transactions.append(
                {
                    "transaction_id": f"TX{i:04d}",
                    "customer_id": np.random.randint(1, 21),
                    "amount": float(np.random.uniform(10, 200)),
                    "date": pd.Timestamp.now().isoformat(),
                }
            )

        import json

        with open(transaction_file, "w") as f:
            json.dump(transactions, f, indent=2)
        print(f"Created {transaction_file}")

    sys.exit(main())

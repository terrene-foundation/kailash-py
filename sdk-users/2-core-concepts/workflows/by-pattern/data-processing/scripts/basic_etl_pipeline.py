#!/usr/bin/env python3
"""
Basic ETL Pipeline using Kailash SDK
=====================================

This script demonstrates a production-ready ETL pipeline that:
1. Reads data from CSV files
2. Transforms and cleanses the data
3. Enriches with additional information
4. Writes to output formats

Key Features:
- Uses native Kailash nodes (no PythonCodeNode needed)
- Proper error handling and validation
- Efficient data processing with FilterNode and DataTransformer
- Production-ready patterns
"""

from kailash import Workflow
from kailash.nodes.data import CSVReaderNode, CSVWriterNode
from kailash.nodes.logic import MergeNode
from kailash.nodes.transform import DataTransformer, FilterNode
from kailash.runtime.local import LocalRuntime


def create_etl_workflow() -> Workflow:
    """Create a production-ready ETL workflow."""
    workflow = Workflow(
        workflow_id="etl_pipeline_001",
        name="basic_etl_pipeline",
        description="ETL pipeline for customer data processing",
    )

    # Data Sources
    customers_reader = CSVReaderNode(
        id="customers_reader", file_path="data/customers.csv"
    )
    workflow.add_node("customers_reader", customers_reader)

    transactions_reader = CSVReaderNode(
        id="transactions_reader", file_path="data/transactions.csv"
    )
    workflow.add_node("transactions_reader", transactions_reader)

    # Data Cleansing - Filter invalid records
    valid_customers = FilterNode(id="valid_customers")
    workflow.add_node("valid_customers", valid_customers)
    workflow.connect("customers_reader", "valid_customers", mapping={"data": "data"})

    # Transform customer data - Add calculated fields
    enriched_customers = DataTransformer(
        id="enriched_customers", transformations=[]  # Will be provided at runtime
    )
    workflow.add_node("enriched_customers", enriched_customers)
    workflow.connect(
        "valid_customers", "enriched_customers", mapping={"filtered_data": "data"}
    )

    # Filter high-value transactions
    high_value_txns = FilterNode(id="high_value_transactions")
    workflow.add_node("high_value_transactions", high_value_txns)
    workflow.connect(
        "transactions_reader", "high_value_transactions", mapping={"data": "data"}
    )

    # Merge customer and transaction data
    merged_data = MergeNode(id="merge_customer_transactions")
    workflow.add_node("merge_customer_transactions", merged_data)
    workflow.connect(
        "enriched_customers", "merge_customer_transactions", mapping={"result": "data1"}
    )
    workflow.connect(
        "high_value_transactions",
        "merge_customer_transactions",
        mapping={"filtered_data": "data2"},
    )

    # Write results
    output_writer = CSVWriterNode(
        id="output_writer", file_path="data/outputs/enriched_customers.csv"
    )
    workflow.add_node("output_writer", output_writer)
    workflow.connect(
        "merge_customer_transactions", "output_writer", mapping={"merged_data": "data"}
    )

    return workflow


def run_etl_pipeline():
    """Execute the ETL pipeline with proper parameters."""
    workflow = create_etl_workflow()
    runtime = LocalRuntime()

    # Define runtime parameters
    parameters = {
        "valid_customers": {"field": "status", "operator": "==", "value": "active"},
        "enriched_customers": {
            "transformations": [
                # Calculate customer lifetime value
                "lambda customer: {**customer, 'lifetime_value': float(customer.get('total_purchases', 0)) * 1.5}",
                # Add customer segment
                "lambda customer: {**customer, 'segment': 'high' if float(customer.get('lifetime_value', 0)) > 1000 else 'standard'}",
            ]
        },
        "high_value_transactions": {
            "field": "amount",
            "operator": ">=",
            "value": 100.0,
        },
        "merge_customer_transactions": {
            "merge_type": "merge_dict",
            "key": "customer_id",
        },
    }

    try:
        print("Starting ETL pipeline...")
        result, run_id = runtime.execute(workflow, parameters=parameters)
        print("ETL pipeline completed successfully!")
        print("Results written to: data/outputs/enriched_customers.csv")
        return result
    except Exception as e:
        print(f"ETL pipeline failed: {str(e)}")
        raise


def main():
    """Main entry point."""
    # Create sample data if it doesn't exist
    import csv
    import os

    os.makedirs("data/outputs", exist_ok=True)

    # Create sample customers.csv
    if not os.path.exists("data/customers.csv"):
        with open("data/customers.csv", "w", newline="") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=[
                    "customer_id",
                    "name",
                    "email",
                    "status",
                    "total_purchases",
                ],
            )
            writer.writeheader()
            writer.writerows(
                [
                    {
                        "customer_id": "C001",
                        "name": "Alice Johnson",
                        "email": "alice@example.com",
                        "status": "active",
                        "total_purchases": "1200",
                    },
                    {
                        "customer_id": "C002",
                        "name": "Bob Smith",
                        "email": "bob@example.com",
                        "status": "inactive",
                        "total_purchases": "800",
                    },
                    {
                        "customer_id": "C003",
                        "name": "Carol White",
                        "email": "carol@example.com",
                        "status": "active",
                        "total_purchases": "500",
                    },
                ]
            )

    # Create sample transactions.csv
    if not os.path.exists("data/transactions.csv"):
        with open("data/transactions.csv", "w", newline="") as f:
            writer = csv.DictWriter(
                f, fieldnames=["transaction_id", "customer_id", "amount", "date"]
            )
            writer.writeheader()
            writer.writerows(
                [
                    {
                        "transaction_id": "T001",
                        "customer_id": "C001",
                        "amount": "250",
                        "date": "2024-01-15",
                    },
                    {
                        "transaction_id": "T002",
                        "customer_id": "C001",
                        "amount": "150",
                        "date": "2024-02-20",
                    },
                    {
                        "transaction_id": "T003",
                        "customer_id": "C003",
                        "amount": "75",
                        "date": "2024-01-10",
                    },
                    {
                        "transaction_id": "T004",
                        "customer_id": "C002",
                        "amount": "200",
                        "date": "2024-02-01",
                    },
                ]
            )

    # Run the ETL pipeline
    run_etl_pipeline()


if __name__ == "__main__":
    main()

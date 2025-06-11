"""
Conditional Workflow Example using SwitchNode and MergeNode.

This example demonstrates how to create a workflow with conditional branching
using the SwitchNode to route data based on conditions and the MergeNode
to combine the results from different branches.
"""

import json
import logging
import os

from examples.utils.paths import get_data_dir, get_output_dir
from kailash.nodes.data.readers import CSVReaderNode, JSONReaderNode
from kailash.nodes.data.writers import JSONWriterNode
from kailash.nodes.logic.operations import MergeNode, SwitchNode
from kailash.nodes.transform.processors import DataTransformer
from kailash.workflow.graph import Workflow

# Configure logging
logging.basicConfig(
    level=logging.DEBUG, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def generate_sample_data():
    """Generate sample data files for the example."""
    # Create data directory if it doesn't exist
    os.makedirs("../outputs", exist_ok=True)

    # Sample transaction data with different status values
    transactions = [
        {"id": "tx001", "amount": 150.0, "status": "completed", "customer_id": "cust1"},
        {"id": "tx002", "amount": 75.25, "status": "pending", "customer_id": "cust2"},
        {"id": "tx003", "amount": 200.0, "status": "failed", "customer_id": "cust3"},
        {"id": "tx004", "amount": 50.0, "status": "completed", "customer_id": "cust4"},
        {"id": "tx005", "amount": 125.75, "status": "pending", "customer_id": "cust5"},
        {"id": "tx006", "amount": 300.0, "status": "completed", "customer_id": "cust1"},
        {"id": "tx007", "amount": 25.50, "status": "failed", "customer_id": "cust2"},
        {"id": "tx008", "amount": 175.0, "status": "pending", "customer_id": "cust3"},
    ]

    # Write to JSON file
    with open(str(get_data_dir() / "transactions.json"), "w") as f:
        json.dump(transactions, f, indent=2)

    # Sample customer data
    customers = [
        {
            "customer_id": "cust1",
            "name": "Alice",
            "email": "alice@example.com",
            "tier": "gold",
        },
        {
            "customer_id": "cust2",
            "name": "Bob",
            "email": "bob@example.com",
            "tier": "silver",
        },
        {
            "customer_id": "cust3",
            "name": "Charlie",
            "email": "charlie@example.com",
            "tier": "bronze",
        },
        {
            "customer_id": "cust4",
            "name": "Diana",
            "email": "diana@example.com",
            "tier": "gold",
        },
        {
            "customer_id": "cust5",
            "name": "Evan",
            "email": "evan@example.com",
            "tier": "silver",
        },
    ]

    # Write to CSV file
    with open(str(get_data_dir() / "customers.csv"), "w") as f:
        f.write("customer_id,name,email,tier\n")
        for customer in customers:
            f.write(
                f"{customer['customer_id']},{customer['name']},{customer['email']},{customer['tier']}\n"
            )

    logger.info("Sample data generated successfully")


def create_conditional_workflow() -> Workflow:
    """
    Create a workflow that processes transactions differently based on their status.

    The workflow:
    1. Reads transaction data from a JSON file
    2. Uses a Switch node to route transactions based on status
    3. Each status branch processes the data differently
    4. A Merge node combines the results
    5. Writes the results to output files

    Returns:
        Workflow: The configured workflow
    """
    workflow = Workflow(
        workflow_id="conditional_transaction_processing",
        name="Conditional Transaction Processing",
        description="Process transactions based on their status",
    )

    # 1. Create nodes
    # Data source nodes
    workflow.add_node(
        "transactions_reader",
        JSONReaderNode(file_path=str(get_data_dir() / "transactions.json")),
    )

    workflow.add_node(
        "customers_reader",
        CSVReaderNode(
            file_path=str(get_data_dir() / "customers.csv", index_column="customer_id")
        ),
    )

    # Switch node to route by transaction status
    workflow.add_node(
        "status_router",
        SwitchNode(
            input_data=None,  # This will be connected later
            condition_field="status",
            cases=["completed", "pending", "failed"],
            case_prefix="case_",
        ),
    )

    # Processing nodes for each branch
    # Completed transactions - calculate fee and mark as processed
    workflow.add_node(
        "completed_processor",
        DataTransformer(
            transformations=[
                "lambda tx: {**tx, 'processing_fee': tx['amount'] * 0.02, 'processed': True}"
            ]
        ),
    )

    # Pending transactions - mark for follow-up
    workflow.add_node(
        "pending_processor",
        DataTransformer(
            transformations=[
                "lambda tx: {**tx, 'follow_up': True, 'follow_up_date': '2025-06-01'}"
            ]
        ),
    )

    # Failed transactions - add error handling
    workflow.add_node(
        "failed_processor",
        DataTransformer(
            transformations=[
                "lambda tx: {**tx, 'error_code': 'E' + tx['id'][-3:], 'retry_count': 0}"
            ]
        ),
    )

    # Output writers for each transaction status
    workflow.add_node(
        "completed_writer",
        JSONWriterNode(file_path=str(get_output_dir() / "completed_transactions.json")),
    )

    workflow.add_node(
        "pending_writer",
        JSONWriterNode(file_path=str(get_output_dir() / "pending_transactions.json")),
    )

    workflow.add_node(
        "failed_writer",
        JSONWriterNode(file_path=str(get_output_dir() / "failed_transactions.json")),
    )

    # Output node for all transactions
    workflow.add_node(
        "results_writer",
        JSONWriterNode(file_path=str(get_output_dir() / "processed_transactions.json")),
    )

    # 2. Connect the nodes
    # Connect data sources
    workflow.connect("transactions_reader", "status_router", {"data": "input_data"})

    # Connect Switch node outputs to respective processors
    workflow.connect("status_router", "completed_processor", {"case_completed": "data"})

    workflow.connect("status_router", "pending_processor", {"case_pending": "data"})

    workflow.connect("status_router", "failed_processor", {"case_failed": "data"})

    # Connect processors to their respective writers
    workflow.connect("completed_processor", "completed_writer", {"result": "data"})

    workflow.connect("pending_processor", "pending_writer", {"result": "data"})

    workflow.connect("failed_processor", "failed_writer", {"result": "data"})

    # Connect the default output to the results writer
    workflow.connect("status_router", "results_writer", {"default": "data"})

    return workflow


def create_multi_condition_workflow() -> Workflow:
    """
    Create a more complex workflow with nested conditions based on both
    transaction status and customer tier.

    Returns:
        Workflow: The configured workflow
    """
    workflow = Workflow(
        name="Multi-Condition Processing",
        description="Process transactions based on status and customer tier",
    )

    # Data source nodes
    workflow.add_node(
        "transactions_reader",
        JSONReaderNode(file_path=str(get_data_dir() / "transactions.json")),
    )

    workflow.add_node(
        "customers_reader",
        CSVReaderNode(
            file_path=str(get_data_dir() / "customers.csv", index_column="customer_id")
        ),
    )

    # Initial customer join node
    workflow.add_node(
        "customer_joiner",
        DataTransformer(
            transformations=[
                "lambda tx, customers_dict: {**tx, 'customer_name': customers_dict.get(tx['customer_id'], {}).get('name', 'Unknown'), 'customer_tier': customers_dict.get(tx['customer_id'], {}).get('tier', 'Unknown')}"
            ]
        ),
    )

    # First level routing - by status
    workflow.add_node(
        "status_router",
        SwitchNode(
            input_data=None,  # This will be connected later
            condition_field="status",
            cases=["completed", "pending", "failed"],
        ),
    )

    # Second level routing - for completed transactions by tier
    workflow.add_node(
        "tier_router",
        SwitchNode(
            input_data=None,  # This will be connected later
            condition_field="customer_tier",
            cases=["gold", "silver", "bronze"],
        ),
    )

    # Tier-specific processing nodes
    workflow.add_node(
        "gold_processor",
        DataTransformer(
            transformations=[
                "lambda tx: {**tx, 'processing_fee': tx['amount'] * 0.01, 'bonus_points': tx['amount'] * 2}"
            ]
        ),
    )

    workflow.add_node(
        "silver_processor",
        DataTransformer(
            transformations=[
                "lambda tx: {**tx, 'processing_fee': tx['amount'] * 0.015, 'bonus_points': tx['amount'] * 1.5}"
            ]
        ),
    )

    workflow.add_node(
        "bronze_processor",
        DataTransformer(
            transformations=[
                "lambda tx: {**tx, 'processing_fee': tx['amount'] * 0.02, 'bonus_points': tx['amount'] * 1.0}"
            ]
        ),
    )

    # Other status processors
    workflow.add_node(
        "pending_processor",
        DataTransformer(
            transformations=[
                "lambda tx: {**tx, 'follow_up': True, 'follow_up_date': '2025-06-01'}"
            ]
        ),
    )

    workflow.add_node(
        "failed_processor",
        DataTransformer(
            transformations=[
                "lambda tx: {**tx, 'error_code': 'E' + tx['id'][-3:], 'retry_count': 0}"
            ]
        ),
    )

    # Merge nodes
    workflow.add_node(
        "tier_merger",
        MergeNode(
            data1=None, data2=None, merge_type="concat"  # These will be connected later
        ),
    )

    workflow.add_node(
        "final_merger",
        MergeNode(
            data1=None, data2=None, merge_type="concat"  # These will be connected later
        ),
    )

    # Output
    workflow.add_node(
        "results_writer",
        JSONWriterNode(
            file_path=str(get_output_dir() / "multi_condition_results.json")
        ),
    )

    # Connect nodes - First connect data sources for joining
    workflow.connect("transactions_reader", "customer_joiner", {"data": "tx"})

    workflow.connect(
        "customers_reader", "customer_joiner", {"data_indexed": "customers_dict"}
    )

    # Connect to first level router
    workflow.connect("customer_joiner", "status_router", {"result": "input_data"})

    # Connect completed transactions to tier router
    workflow.connect("status_router", "tier_router", {"case_completed": "input_data"})

    # Connect other status branches directly to processors
    workflow.connect("status_router", "pending_processor", {"case_pending": "data"})

    workflow.connect("status_router", "failed_processor", {"case_failed": "data"})

    # Connect tier router to tier-specific processors
    workflow.connect("tier_router", "gold_processor", {"case_gold": "data"})

    workflow.connect("tier_router", "silver_processor", {"case_silver": "data"})

    workflow.connect("tier_router", "bronze_processor", {"case_bronze": "data"})

    # Merge tier results
    workflow.connect("gold_processor", "tier_merger", {"result": "data1"})

    workflow.connect("silver_processor", "tier_merger", {"result": "data2"})

    workflow.connect("bronze_processor", "tier_merger", {"result": "data3"})

    # Merge all results
    workflow.connect("tier_merger", "final_merger", {"merged_data": "data1"})

    workflow.connect("pending_processor", "final_merger", {"result": "data2"})

    workflow.connect("failed_processor", "final_merger", {"result": "data3"})

    # Connect to output
    workflow.connect("final_merger", "results_writer", {"merged_data": "data"})

    return workflow


def run_example():
    """Run the conditional workflow example."""
    # Generate sample data
    generate_sample_data()

    # Create and run the simple conditional workflow
    logger.info("Creating simple conditional workflow...")
    workflow = create_conditional_workflow()

    logger.info("Running simple conditional workflow...")
    results, run_id = workflow.run()

    logger.info(f"Simple workflow completed with run_id: {run_id}")
    logger.info("Results available at: ../outputs/processed_transactions.json")
    print(f"Results data: {results}")

    # Check output files
    try:
        output_files = [
            "../outputs/processed_transactions.json",
            "../outputs/completed_transactions.json",
            "../outputs/pending_transactions.json",
            "../outputs/failed_transactions.json",
        ]

        for file_path in output_files:
            try:
                with open(file_path) as f:
                    output = json.load(f)
                    print(f"{file_path} contents: {output}")
            except Exception as e:
                logger.error(f"Failed to read {file_path}: {e}")
    except Exception as e:
        logger.error(f"Error checking output files: {e}")

    # Skipping multi-condition workflow for now - will be fixed later
    # logger.info("Creating multi-condition workflow...")
    # multi_workflow = create_multi_condition_workflow()

    # logger.info("Running multi-condition workflow...")
    # multi_results, multi_run_id = multi_workflow.run()

    # logger.info(f"Multi-condition workflow completed with run_id: {multi_run_id}")
    # logger.info(f"Results available at: ../outputs/multi_condition_results.json")
    # print(f"Multi workflow results data: {multi_results}")


if __name__ == "__main__":
    run_example()

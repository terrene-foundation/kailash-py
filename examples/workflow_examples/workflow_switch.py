"""
Simple Switch Node Example

This example demonstrates the basic functionality of the Switch node to route
data based on conditions.
"""

import json
import logging
import os

from kailash.nodes.data.readers import JSONReader
from kailash.nodes.data.writers import JSONWriter
from kailash.nodes.logic.operations import Switch
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
    with open("../data/transactions.json", "w") as f:
        json.dump(transactions, f, indent=2)

    logger.info("Sample data generated successfully")


def create_simple_switch_workflow() -> Workflow:
    """
    Create a workflow that just routes transactions based on status.

    The workflow:
    1. Reads transaction data from a JSON file
    2. Uses a Switch node to route transactions based on status
    3. Uses a Merge node to combine the results
    4. Writes the results to output files

    Returns:
        Workflow: The configured workflow
    """
    workflow = Workflow(
        workflow_id="simple_switch_example",
        name="Simple Switch Example",
        description="Demonstrate the Switch node functionality",
    )

    # Data source node
    workflow.add_node(
        "transactions_reader", JSONReader(file_path="../data/transactions.json")
    )

    # Switch node to route by transaction status
    workflow.add_node(
        "status_router",
        Switch(
            input_data=None,  # This will be connected later
            condition_field="status",
            cases=["completed", "pending", "failed"],
            case_prefix="case_",
        ),
    )

    # Writer nodes for each status
    workflow.add_node(
        "completed_writer",
        JSONWriter(file_path="../outputs/completed_transactions.json"),
    )

    workflow.add_node(
        "pending_writer",
        JSONWriter(file_path="../outputs/pending_transactions.json"),
    )

    workflow.add_node(
        "failed_writer",
        JSONWriter(file_path="../outputs/failed_transactions.json"),
    )

    # Output node
    workflow.add_node(
        "results_writer",
        JSONWriter(file_path="../outputs/simple_switch_results.json"),
    )

    # Connect the nodes
    workflow.connect("transactions_reader", "status_router", {"data": "input_data"})

    # Connect the Switch node outputs to the respective writers
    workflow.connect("status_router", "completed_writer", {"case_completed": "data"})

    workflow.connect("status_router", "pending_writer", {"case_pending": "data"})

    workflow.connect("status_router", "failed_writer", {"case_failed": "data"})

    # Connect the default output to the results writer
    workflow.connect("status_router", "results_writer", {"default": "data"})

    return workflow


def run_example():
    """Run the simple Switch node example."""
    # Generate sample data
    generate_sample_data()

    # Create and run the workflow
    logger.info("Creating simple switch workflow...")
    workflow = create_simple_switch_workflow()

    logger.info("Running simple switch workflow...")
    results, run_id = workflow.run()

    logger.info(f"Workflow completed with run_id: {run_id}")
    logger.info("Results available at: ../outputs/simple_switch_results.json")
    print(f"Results data: {results}")

    # Check the output files
    try:
        output_files = [
            "../outputs/simple_switch_results.json",
            "../outputs/completed_transactions.json",
            "../outputs/pending_transactions.json",
            "../outputs/failed_transactions.json",
        ]

        for file_path in output_files:
            try:
                with open(file_path, "r") as f:
                    output = json.load(f)
                    print(f"{file_path} contents: {output}")
            except Exception as e:
                logger.error(f"Failed to read {file_path}: {e}")
    except Exception as e:
        logger.error(f"Error checking output files: {e}")


if __name__ == "__main__":
    run_example()

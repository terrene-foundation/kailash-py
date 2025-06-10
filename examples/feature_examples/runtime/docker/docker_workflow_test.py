#!/usr/bin/env python3
"""
Docker Workflow Example for Kailash Python SDK

This example demonstrates how to use the DockerRuntime to execute a workflow
where each node runs in a separate Docker container. This approach provides
isolation, reproducibility, and scalability for workflow execution.

Key concepts demonstrated:
- Creating a workflow with multiple nodes
- Configuring the Docker runtime
- Running nodes in containers
- Passing data between containerized nodes
- Resource constraints for container execution
- Result validation and comparison with local execution
"""

import logging
import sys
from pathlib import Path

# Add the parent directory to the path
sys.path.insert(0, str(Path(__file__).parent.parent.absolute()))

# Import Kailash components
from kailash.nodes.code.python import PythonCodeNode
from kailash.nodes.data.readers import CSVReaderNode
from kailash.nodes.data.writers import CSVWriterNode
from kailash.runtime.docker import DockerRuntime
from kailash.runtime.local import LocalRuntime
from kailash.workflow.graph import Workflow

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def create_sample_data(data_dir):
    """Create sample data for the example."""
    # Create customers.csv
    data_dir.mkdir(exist_ok=True)
    customers_file = data_dir / "customers.csv"

    with open(customers_file, "w") as f:
        f.write("customer_id,name,email,age,purchase_total\n")
        f.write("C001,John Doe,john@example.com,30,1500.00\n")
        f.write("C002,Jane Smith,jane@example.com,25,2200.50\n")
        f.write("C003,Bob Johnson,bob@example.com,42,980.75\n")
        f.write("C004,Alice Brown,alice@example.com,35,3400.25\n")
        f.write("C005,Charlie Davis,charlie@example.com,28,750.00\n")

    return customers_file


def create_workflow(input_file, output_file):
    """Create a sample data processing workflow."""
    workflow = Workflow(name="docker_example_workflow")

    # Create reader node
    reader = CSVReaderNode(name="customer_reader")

    # Create processor nodes
    def clean_data(data):
        """Clean and validate customer data."""
        if not isinstance(data, list):
            return {"error": "Expected list of customer records"}

        for customer in data:
            # Convert age to integer
            if "age" in customer:
                customer["age"] = int(customer["age"])

            # Convert purchase_total to float
            if "purchase_total" in customer:
                customer["purchase_total"] = float(customer["purchase_total"])

            # Add derived fields
            if "age" in customer and "purchase_total" in customer:
                customer["avg_annual_spend"] = round(
                    (
                        customer["purchase_total"] / (customer["age"] - 18)
                        if customer["age"] > 18
                        else customer["purchase_total"]
                    ),
                    2,
                )

        return data

    def segment_customers(data):
        """Segment customers based on spending patterns."""
        if not isinstance(data, list):
            return {"error": "Expected list of customer records"}

        for customer in data:
            if "purchase_total" in customer:
                # Assign segment based on purchase total
                if customer["purchase_total"] > 3000:
                    customer["segment"] = "premium"
                elif customer["purchase_total"] > 1000:
                    customer["segment"] = "standard"
                else:
                    customer["segment"] = "basic"

        return data

    cleaner = PythonCodeNode.from_function(clean_data, name="data_cleaner")

    segmenter = PythonCodeNode.from_function(
        segment_customers, name="customer_segmenter"
    )

    # Create writer node
    writer = CSVWriterNode(name="customer_writer")

    # Add nodes to workflow
    workflow.add_node("reader", reader, {"file_path": input_file})
    workflow.add_node("cleaner", cleaner)
    workflow.add_node("segmenter", segmenter)
    workflow.add_node("writer", writer, {"file_path": output_file})

    # Connect nodes
    workflow.connect("reader", "cleaner", {"data": "result"})
    workflow.connect("cleaner", "segmenter", {"data": "result"})
    workflow.connect("segmenter", "writer", {"data": "result"})

    return workflow


def run_with_docker_runtime(workflow, inputs=None):
    """Run the workflow using the Docker runtime."""
    logger.info("Running workflow with Docker runtime")

    # Define resource limits for nodes
    resource_limits = {
        "reader": {"memory": "256m", "cpu": "0.5"},
        "cleaner": {"memory": "512m", "cpu": "1.0"},
        "segmenter": {"memory": "512m", "cpu": "1.0"},
        "writer": {"memory": "256m", "cpu": "0.5"},
    }

    # Create Docker runtime
    docker_runtime = DockerRuntime(
        base_image="python:3.11-slim",
        network_name="kailash-example-network",
        work_dir="./docker_runtime_work",
    )

    # Execute workflow
    try:
        results, run_id = docker_runtime.execute(
            workflow, inputs=inputs, node_resource_limits=resource_limits
        )

        logger.info(f"Docker runtime execution completed with run ID: {run_id}")
        return results, run_id
    finally:
        # Cleanup Docker resources
        docker_runtime.cleanup()


def run_with_local_runtime(workflow, inputs=None):
    """Run the workflow using the local runtime for comparison."""
    logger.info("Running workflow with local runtime")

    # Create local runtime
    local_runtime = LocalRuntime()

    # Execute workflow
    results, run_id = local_runtime.execute(workflow, inputs=inputs)

    logger.info(f"Local runtime execution completed with run ID: {run_id}")
    return results, run_id


def compare_results(docker_results, local_results):
    """Compare Docker and local execution results."""
    logger.info("Comparing Docker and local execution results")

    all_match = True
    comparison = {}

    # Check each node's results
    for node_id in set(docker_results.keys()) | set(local_results.keys()):
        if node_id not in docker_results:
            logger.warning(f"Node {node_id} missing from Docker results")
            all_match = False
            comparison[node_id] = {
                "match": False,
                "reason": "Missing from Docker results",
            }
            continue

        if node_id not in local_results:
            logger.warning(f"Node {node_id} missing from local results")
            all_match = False
            comparison[node_id] = {
                "match": False,
                "reason": "Missing from local results",
            }
            continue

        # Simple equality check (could be enhanced for deeper comparison)
        if docker_results[node_id] == local_results[node_id]:
            logger.info(f"Results match for node {node_id}")
            comparison[node_id] = {"match": True}
        else:
            logger.warning(f"Results differ for node {node_id}")
            all_match = False
            comparison[node_id] = {
                "match": False,
                "docker": docker_results[node_id],
                "local": local_results[node_id],
            }

    return all_match, comparison


def main():
    """Run the Docker workflow example."""
    # Prepare directories
    example_dir = Path(__file__).parent
    data_dir = example_dir / "data"
    output_dir = data_dir / "outputs"
    output_dir.mkdir(exist_ok=True)

    # Create sample data
    input_file = create_sample_data(data_dir)
    docker_output_file = output_dir / "docker_processed_customers.csv"
    local_output_file = output_dir / "local_processed_customers.csv"

    # Create workflows (separate instances for each runtime)
    docker_workflow = create_workflow(str(input_file), str(docker_output_file))
    local_workflow = create_workflow(str(input_file), str(local_output_file))

    # Run with Docker runtime
    docker_results, docker_run_id = run_with_docker_runtime(docker_workflow)

    # Run with local runtime for comparison
    local_results, local_run_id = run_with_local_runtime(local_workflow)

    # Compare results
    match, comparison = compare_results(docker_results, local_results)

    # Report results
    if match:
        logger.info("✅ Docker and local execution results match!")
    else:
        logger.warning("❌ Docker and local execution results differ")

        # Print comparison details
        print("\nResult comparison:")
        for node_id, details in comparison.items():
            if details.get("match"):
                print(f"  ✓ {node_id}: Results match")
            else:
                print(f"  ✗ {node_id}: Results differ - {details.get('reason', '')}")

    # Check output files
    if docker_output_file.exists() and local_output_file.exists():
        docker_size = docker_output_file.stat().st_size
        local_size = local_output_file.stat().st_size

        print(f"\nDocker output file: {docker_output_file} ({docker_size} bytes)")
        print(f"Local output file: {local_output_file} ({local_size} bytes)")

        if docker_size == local_size:
            print("✅ Output file sizes match")
        else:
            print("❌ Output file sizes differ")

    print("\nExample completed successfully!")


if __name__ == "__main__":
    main()

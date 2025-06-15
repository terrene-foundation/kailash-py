#!/usr/bin/env python3
"""
Docker Node Testing Framework for Kailash Python SDK

This module provides a testing framework to validate that nodes
can run as independent Docker containers within a workflow orchestration.

Key features:
- Automatic Dockerfile generation for each node
- Docker image building with appropriate dependencies
- Container execution with proper input/output mapping
- Node communication over mounted volumes or network interfaces
- Workflow orchestration for testing multi-node pipelines
- Validation of execution results against local runtime
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import pytest

from examples.utils.paths import get_data_dir, get_output_dir

# Add parent directory to path to allow importing the Kailash SDK
sys.path.insert(0, str(Path(__file__).parent.parent.parent.absolute()))

from kailash.nodes.base import Node
from kailash.runtime.local import LocalRuntime
from kailash.workflow.graph import Workflow


class DockerNodeTester:
    """
    Test runner for executing nodes in Docker containers.

    This class provides functionality to:
    1. Generate Dockerfiles for Kailash nodes
    2. Build Docker images for nodes
    3. Run nodes in containers with proper I/O mapping
    4. Validate node execution results
    5. Test multi-node workflows with container orchestration
    """

    def __init__(
        self,
        test_dir: str | None = None,
        base_image: str = "python:3.11-slim",
        network_name: str = "kailash-test-network",
        cleanup: bool = True,
    ):
        """
        Initialize the Docker node tester.

        Args:
            test_dir: Directory for test artifacts. If None, a temp directory is created.
            base_image: Base Docker image to use for node containers.
            network_name: Docker network name for container communication.
            cleanup: Whether to clean up resources after tests.
        """
        self.base_image = base_image
        self.network_name = network_name
        self.cleanup = cleanup

        # Create test directory if not provided
        if test_dir:
            self.test_dir = Path(test_dir)
            self.test_dir.mkdir(parents=True, exist_ok=True)
            self._created_temp_dir = False
        else:
            self.test_dir = Path(tempfile.mkdtemp(prefix="kailash_docker_test_"))
            self._created_temp_dir = True

        # Create subdirectories
        self.docker_dir = self.test_dir / "docker"
        self.data_dir = self.test_dir / "data"
        self.results_dir = self.test_dir / "results"

        for directory in [self.docker_dir, self.data_dir, self.results_dir]:
            directory.mkdir(exist_ok=True)

        # Container tracking
        self.containers = []
        self.images = []

        # Create Docker network
        self._create_network()

    def _create_network(self):
        """Create a Docker network for container communication."""
        try:
            subprocess.execute(
                ["docker", "network", "create", self.network_name],
                check=True,
                capture_output=True,
            )
            print(f"Created Docker network: {self.network_name}")
        except subprocess.CalledProcessError as e:
            if "already exists" not in e.stderr.decode():
                raise RuntimeError(f"Failed to create Docker network: {e}")

    def create_dockerfile_for_node(
        self, node: Node, requirements: list[str] = None
    ) -> Path:
        """
        Generate a Dockerfile for a specific node.

        Args:
            node: The Kailash node to containerize.
            requirements: Additional Python requirements for this node.

        Returns:
            Path to the generated Dockerfile.
        """
        node_dir = self.docker_dir / node.__class__.__name__
        node_dir.mkdir(exist_ok=True)

        dockerfile_path = node_dir / "Dockerfile"
        entrypoint_path = node_dir / "entrypoint.py"
        node_path = node_dir / "node.json"

        # Serialize node configuration
        with open(node_path, "w") as f:
            # Create a simplified representation of the node
            node_data = {
                "class": node.__class__.__name__,
                "module": node.__class__.__module__,
                "name": getattr(node, "name", node.__class__.__name__),
                "parameters": {
                    name: str(param)
                    for name, param in (getattr(node, "get_parameters", dict)().items())
                },
            }
            json.dump(node_data, f, indent=2)

        # Create entrypoint script
        with open(entrypoint_path, "w") as f:
            f.write(
                """#!/usr/bin/env python3
import importlib

# Node execution entrypoint for Docker containers

def main():
    # Load node configuration
    node_config_path = Path("/app/node.json")
    with open(node_config_path, 'r') as f:
        node_data = json.load(f)

    # Load runtime inputs if available
    runtime_inputs_path = Path("/data/inputs/json/inputs.json")
    runtime_inputs = {}
    if runtime_inputs_path.exists():
        with open(runtime_inputs_path, 'r') as f:
            runtime_inputs = json.load(f)

    # Dynamically import and instantiate the node
    module_name = node_data["module"]
    class_name = node_data["class"]

    module = importlib.import_module(module_name)
    node_class = getattr(module, class_name)

    # Create node instance (simplified - would need actual parameter parsing)
    node = node_class(name=node_data["name"])

    # Execute node
    result = node.execute(**runtime_inputs)

    # Save results
    os.makedirs("/data/outputs/json", exist_ok=True)
    with open("/data/outputs/json/result.json", 'w') as f:
        # Handle non-serializable objects
        try:
            json.dump(result, f, indent=2)
        except TypeError:
            # Simplified handling - would need better serialization
            json.dump({"result": str(result)}, f, indent=2)

    print(f"Node {node_data['name']} execution completed")
    return 0

if __name__ == "__main__":
    sys.exit(main())
"""
            )

        # Make entrypoint executable
        os.chmod(entrypoint_path, 0o755)

        # Create Dockerfile
        with open(dockerfile_path, "w") as f:
            f.write(
                f"""FROM {self.base_image}

# Set working directory
WORKDIR /app

# Copy Kailash SDK (would typically use pip install for released versions)
COPY sdk /app/sdk

# Install dependencies
RUN pip install --no-cache-dir -e /app/sdk
"""
            )

            # Add custom requirements if provided
            if requirements:
                f.write("RUN pip install --no-cache-dir \\\n")
                f.write("    " + " \\\n    ".join(requirements) + "\n")

            f.write(
                """
# Copy node configuration and entrypoint
COPY node.json /app/node.json
COPY entrypoint.py /app/entrypoint.py

# Create data directories
RUN mkdir -p /data/inputs/json /data/outputs/json

# Set entrypoint
ENTRYPOINT ["/app/entrypoint.py"]
"""
            )

        # Create a directory for the SDK copy
        sdk_dir = node_dir / "sdk"
        sdk_dir.mkdir(exist_ok=True)

        # Get the source directory (parent of examples)
        src_dir = Path(__file__).parent.parent

        # Copy essential SDK files (simplified for example)
        # In real implementation, would properly package the SDK
        shutil.copytree(src_dir / "src", sdk_dir / "src", dirs_exist_ok=True)

        # Copy setup files
        for setup_file in ["setup.py", "pyproject.toml"]:
            if (src_dir / setup_file).exists():
                shutil.copy(src_dir / setup_file, sdk_dir / setup_file)

        return dockerfile_path

    def build_image_for_node(self, node: Node) -> str:
        """
        Build a Docker image for a node.

        Args:
            node: The node to build an image for.

        Returns:
            The name of the built Docker image.
        """
        node_name = node.__class__.__name__.lower()
        image_name = f"kailash-node-{node_name}:test"

        node_dir = self.docker_dir / node.__class__.__name__

        # Ensure Dockerfile exists
        if not (node_dir / "Dockerfile").exists():
            self.create_dockerfile_for_node(node)

        # Build the Docker image
        try:
            subprocess.execute(
                ["docker", "build", "-t", image_name, "."],
                cwd=node_dir,
                check=True,
                capture_output=True,
            )
            self.images.append(image_name)
            print(f"Built Docker image: {image_name}")
            return image_name
        except subprocess.CalledProcessError as e:
            print(f"Failed to build Docker image: {e}")
            print(f"STDOUT: {e.stdout.decode()}")
            print(f"STDERR: {e.stderr.decode()}")
            raise

    def run_node_container(
        self, node: Node, image_name: str, inputs: dict[str, Any]
    ) -> str:
        """
        Run a node in a Docker container.

        Args:
            node: The node to run.
            image_name: The Docker image to use.
            inputs: The inputs to pass to the node.

        Returns:
            The container ID.
        """
        node_name = node.__class__.__name__.lower()
        container_name = f"kailash-{node_name}-{id(node)}"

        # Prepare input data
        node_data_dir = self.data_dir / node_name
        node_data_dir.mkdir(exist_ok=True)

        input_file = node_data_dir / "inputs.json"
        with open(input_file, "w") as f:
            json.dump(inputs, f, indent=2)

        # Run the container
        try:
            result = subprocess.execute(
                [
                    "docker",
                    "run",
                    "--name",
                    container_name,
                    "--network",
                    self.network_name,
                    "-v",
                    f"{node_data_dir.absolute()}:/data",
                    "-d",  # Detached mode
                    image_name,
                ],
                check=True,
                capture_output=True,
            )
            container_id = result.stdout.decode().strip()
            self.containers.append(container_id)

            print(f"Started container {container_name} with ID: {container_id}")
            return container_id
        except subprocess.CalledProcessError as e:
            print(f"Failed to run container: {e}")
            print(f"STDOUT: {e.stdout.decode()}")
            print(f"STDERR: {e.stderr.decode()}")
            raise

    def wait_for_container(self, container_id: str, timeout: int = 60) -> bool:
        """
        Wait for a container to finish.

        Args:
            container_id: The container ID to wait for.
            timeout: Maximum seconds to wait.

        Returns:
            True if container completed successfully, False otherwise.
        """
        try:
            subprocess.execute(
                ["docker", "wait", container_id],
                check=True,
                timeout=timeout,
                capture_output=True,
            )

            # Check exit code
            result = subprocess.execute(
                ["docker", "inspect", container_id, "--format={{.State.ExitCode}}"],
                check=True,
                capture_output=True,
            )
            exit_code = int(result.stdout.decode().strip())

            return exit_code == 0
        except subprocess.TimeoutExpired:
            print(f"Container {container_id} timed out")
            return False
        except subprocess.CalledProcessError as e:
            print(f"Error waiting for container: {e}")
            return False

    def get_container_logs(self, container_id: str) -> str:
        """Get logs from a container."""
        try:
            result = subprocess.execute(
                ["docker", "logs", container_id], check=True, capture_output=True
            )
            return result.stdout.decode()
        except subprocess.CalledProcessError as e:
            print(f"Error getting container logs: {e}")
            return f"Error: {e}"

    def get_node_result(self, node: Node) -> dict[str, Any]:
        """
        Get the result of a node execution.

        Args:
            node: The node to get results for.

        Returns:
            The node execution result.
        """
        node_name = node.__class__.__name__.lower()
        node_data_dir = self.data_dir / node_name

        result_file = node_data_dir / "output" / "result.json"
        if result_file.exists():
            with open(result_file) as f:
                return json.load(f)
        else:
            return {"error": "No result file found"}

    def test_workflow(
        self, workflow: Workflow, inputs: dict[str, dict[str, Any]]
    ) -> dict[str, Any]:
        """
        Test a workflow by running each node in a separate container.

        Args:
            workflow: The workflow to test.
            inputs: The inputs for each node.

        Returns:
            The workflow execution results.
        """
        # Build images for all nodes
        node_images = {}
        for node_id, node in workflow.nodes.items():
            image_name = self.build_image_for_node(node)
            node_images[node_id] = image_name

        # Get execution order (topological sort)
        execution_order = workflow.get_execution_order()

        # Track results for each node
        node_results = {}

        # Execute nodes in order
        for node_id in execution_order:
            node = workflow.nodes[node_id]
            node_inputs = inputs.get(node_id, {})

            # Add inputs from upstream nodes
            for upstream_id, output_mapping in workflow.connections.get(
                node_id, {}
            ).items():
                if upstream_id in node_results:
                    upstream_result = node_results[upstream_id]
                    for dest_param, src_param in output_mapping.items():
                        if src_param in upstream_result:
                            node_inputs[dest_param] = upstream_result[src_param]

            # Run the node container
            container_id = self.run_node_container(
                node, node_images[node_id], node_inputs
            )

            # Wait for completion
            success = self.wait_for_container(container_id)
            if not success:
                print(f"Node {node_id} failed. Logs:")
                print(self.get_container_logs(container_id))
                raise RuntimeError(f"Node {node_id} execution failed")

            # Get results
            node_results[node_id] = self.get_node_result(node)

        return node_results

    def compare_with_local_execution(
        self, workflow: Workflow, inputs: dict[str, dict[str, Any]]
    ) -> tuple[bool, dict[str, Any]]:
        """
        Compare Docker-based execution with local execution.

        Args:
            workflow: The workflow to test.
            inputs: The inputs for each node.

        Returns:
            Tuple of (is_equal, comparison_results).
        """
        # Run with Docker
        docker_results = self.test_workflow(workflow, inputs)

        # Run locally
        local_runtime = LocalRuntime()
        local_results, _ = local_runtime.execute(workflow, inputs)

        # Compare results (simplified - would need more sophisticated comparison)
        is_equal = True
        comparison = {}

        for node_id in workflow.nodes:
            docker_node_result = docker_results.get(node_id, {})
            local_node_result = local_results.get(node_id, {})

            # Very simple comparison - would need proper deep comparison
            node_equal = docker_node_result == local_node_result
            is_equal = is_equal and node_equal

            comparison[node_id] = {
                "equal": node_equal,
                "docker_result": docker_node_result,
                "local_result": local_node_result,
            }

        return is_equal, comparison

    def cleanup_resources(self):
        """Clean up Docker containers and other resources."""
        if not self.cleanup:
            return

        # Stop and remove containers
        for container_id in self.containers:
            try:
                subprocess.execute(
                    ["docker", "rm", "-f", container_id],
                    check=False,
                    capture_output=True,
                )
            except Exception as e:
                print(f"Error cleaning up container {container_id}: {e}")

        # Remove images
        for image_name in self.images:
            try:
                subprocess.execute(
                    ["docker", "rmi", image_name], check=False, capture_output=True
                )
            except Exception as e:
                print(f"Error cleaning up image {image_name}: {e}")

        # Remove network
        try:
            subprocess.execute(
                ["docker", "network", "rm", self.network_name],
                check=False,
                capture_output=True,
            )
        except Exception as e:
            print(f"Error cleaning up network {self.network_name}: {e}")

        # Remove test directory if we created it
        if self._created_temp_dir and self.test_dir.exists():
            shutil.rmtree(self.test_dir)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.cleanup_resources()


def create_test_workflow():
    """Create a sample workflow for testing."""
    from kailash.nodes.code.python import PythonCodeNode
    from kailash.nodes.data.readers import CSVReaderNode
    from kailash.nodes.data.writers import CSVWriterNode

    workflow = Workflow(workflow_id="docker_test_workflow", name="docker_test_workflow")

    # Create nodes
    reader = CSVReaderNode(
        file_path=str(get_data_dir() / "customers.csv"), headers=True
    )

    def process_data(data):
        """Simple data processing function."""
        if isinstance(data, list):
            for row in data:
                if isinstance(row, dict) and "age" in row:
                    row["age"] = int(row["age"]) + 1
        return {"data": data}

    from kailash.nodes.base import NodeParameter

    input_schema = {"data": NodeParameter(name="data", type=list, required=True)}
    output_schema = {"data": NodeParameter(name="data", type=list, required=True)}

    processor = PythonCodeNode.from_function(
        process_data,
        name="age_incrementer",
        input_schema=input_schema,
        output_schema=output_schema,
    )

    writer = CSVWriterNode(file_path=str(get_output_dir() / "processed_output.csv"))

    # Add nodes to workflow
    workflow.add_node("reader", reader)
    workflow.add_node("processor", processor)
    workflow.add_node("writer", writer)

    # Create connections
    workflow.connect("reader", "processor", {"data": "result"})
    workflow.connect("processor", "writer", {"data": "result"})

    return workflow


def main():
    """Run the Docker node test framework."""
    parser = argparse.ArgumentParser(
        description="Test Kailash nodes in Docker containers"
    )
    parser.add_argument(
        "--keep-resources",
        action="store_true",
        help="Don't clean up Docker resources after testing",
    )
    parser.add_argument(
        "--test-dir", type=str, default=None, help="Directory for test artifacts"
    )
    args = parser.parse_args()

    print("Starting Docker Node Testing Framework")

    # Create test directory if specified
    test_dir = args.test_dir

    with DockerNodeTester(test_dir=test_dir, cleanup=not args.keep_resources) as tester:
        # Create a sample workflow
        workflow = create_test_workflow()

        # Create sample data
        sample_data_file = Path(tester.data_dir) / "sample.csv"
        with open(sample_data_file, "w") as f:
            f.write("name,age,email\n")
            f.write("John Doe,30,john@example.com\n")
            f.write("Jane Smith,25,jane@example.com\n")

        # Define inputs
        inputs = {
            "reader": {"file_path": str(sample_data_file)},
            "writer": {"file_path": str(Path(tester.data_dir) / "output.csv")},
        }

        # Test the workflow
        print("\nTesting workflow with Docker containers...")
        docker_results = tester.test_workflow(workflow, inputs)

        print("\nDocker execution results:")
        for node_id, result in docker_results.items():
            print(f"Node {node_id}: {result}")

        # Compare with local execution
        print("\nComparing with local execution...")
        is_equal, comparison = tester.compare_with_local_execution(workflow, inputs)

        if is_equal:
            print("\n✅ Docker and local execution results match!")
        else:
            print("\n❌ Docker and local execution results differ:")
            for node_id, comp in comparison.items():
                if not comp["equal"]:
                    print(f"  Node {node_id} results differ:")
                    print(f"    Docker: {comp['docker_result']}")
                    print(f"    Local: {comp['local_result']}")

    print("\nDocker Node Testing Framework completed")


if __name__ == "__main__":
    main()

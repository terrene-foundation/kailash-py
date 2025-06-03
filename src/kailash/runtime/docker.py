"""
Docker Runtime for Kailash Python SDK.

This module implements a Docker-based runtime for executing workflows where each
node runs in a separate Docker container. This enables scalable, isolated, and
reproducible workflow execution.

Key features:
- Container isolation for each node
- Resource constraints for execution
- Network communication between nodes
- Volume mounting for data exchange
- Orchestration of workflow execution
- Observability and monitoring
"""

import json
import logging
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from kailash.nodes.base import Node

# BaseRuntime doesn't exist - we'll implement task tracking methods directly
from kailash.sdk_exceptions import NodeConfigurationError, NodeExecutionError
from kailash.tracking.manager import TaskManager
from kailash.workflow.graph import Workflow

logger = logging.getLogger(__name__)


class DockerNodeWrapper:
    """
    Wrapper for running a Kailash node in a Docker container.

    This class handles:
    - Dockerfile generation
    - Image building
    - Container execution
    - I/O mapping
    - Result extraction
    """

    def __init__(
        self,
        node: Node,
        node_id: str,
        base_image: str = "python:3.11-slim",
        work_dir: Optional[Path] = None,
        sdk_path: Optional[Path] = None,
    ):
        """
        Initialize a Docker node wrapper.

        Args:
            node: The Kailash node to containerize.
            node_id: The ID of the node in the workflow.
            base_image: Base Docker image to use.
            work_dir: Working directory for Docker files. If None, a temp dir is created.
            sdk_path: Path to the Kailash SDK source. If None, tries to determine it.
        """
        self.node = node
        self.node_id = node_id
        self.base_image = base_image

        # Create or use work directory
        if work_dir:
            self.work_dir = Path(work_dir)
            self.work_dir.mkdir(parents=True, exist_ok=True)
            self._created_temp_dir = False
        else:
            self.work_dir = Path(tempfile.mkdtemp(prefix=f"kailash_docker_{node_id}_"))
            self._created_temp_dir = True

        # Find SDK path if not provided
        if sdk_path:
            self.sdk_path = Path(sdk_path)
        else:
            # Try to find SDK path from node's module
            module_path = Path(self.node.__class__.__module__.replace(".", "/"))
            if module_path.parts and module_path.parts[0] == "kailash":
                # Find the SDK path by walking up to find the src/kailash directory
                module_file = sys.modules[self.node.__class__.__module__].__file__
                if module_file:
                    file_path = Path(module_file)
                    for parent in file_path.parents:
                        if (parent / "kailash").exists() and "site-packages" not in str(
                            parent
                        ):
                            self.sdk_path = parent.parent
                            break

            if not hasattr(self, "sdk_path"):
                raise NodeConfigurationError(
                    "Could not determine SDK path. Please provide it explicitly."
                )

        # Container properties
        self.image_name = f"kailash-node-{self.node_id.lower()}"
        self.container_name = f"kailash-{self.node_id.lower()}"
        self.container_id = None

        # I/O directories
        self.input_dir = self.work_dir / "input"
        self.output_dir = self.work_dir / "output"
        self.input_dir.mkdir(exist_ok=True)
        self.output_dir.mkdir(exist_ok=True)

    def prepare_dockerfile(self) -> Path:
        """
        Generate a Dockerfile for the node.

        Returns:
            Path to the generated Dockerfile.
        """
        dockerfile_path = self.work_dir / "Dockerfile"
        entrypoint_path = self.work_dir / "entrypoint.py"
        node_config_path = self.work_dir / "node.json"

        # Save node configuration
        with open(node_config_path, "w") as f:
            # Create a serializable representation of the node
            node_data = {
                "class": self.node.__class__.__name__,
                "module": self.node.__class__.__module__,
                "node_id": self.node_id,
                "name": getattr(self.node, "name", self.node.__class__.__name__),
            }

            # Add parameters if available
            if hasattr(self.node, "get_parameters"):
                node_data["parameters"] = {}
                for name, param in self.node.get_parameters().items():
                    node_data["parameters"][name] = {
                        "name": param.name,
                        "type": str(param.type),
                        "required": param.required,
                        "description": param.description,
                    }

            json.dump(node_data, f, indent=2)

        # Create entrypoint script
        with open(entrypoint_path, "w") as f:
            f.write(
                """#!/usr/bin/env python3
import os
import sys
import json
import logging
import importlib
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("kailash_node")

def main():
    \"\"\"Run a Kailash node in a Docker container.\"\"\"
    logger.info("Starting node execution")

    # Load node configuration
    node_config_path = Path("/app/node.json")
    with open(node_config_path, 'r') as f:
        node_data = json.load(f)

    logger.info(f"Loaded configuration for {node_data['class']} node")

    # Load runtime inputs if available
    input_path = Path("/examples/data/input/inputs.json")
    runtime_inputs = {}
    if input_path.exists():
        logger.info(f"Loading inputs from {input_path}")
        with open(input_path, 'r') as f:
            runtime_inputs = json.load(f)

    # Dynamically import the node class
    logger.info(f"Importing {node_data['module']}.{node_data['class']}")
    try:
        module = importlib.import_module(node_data['module'])
        node_class = getattr(module, node_data['class'])
    except (ImportError, AttributeError) as e:
        logger.error(f"Failed to import node class: {e}")
        return 1

    # Create node instance
    logger.info(f"Creating node instance: {node_data['name']}")
    try:
        node = node_class(name=node_data['name'])
    except Exception as e:
        logger.error(f"Failed to create node instance: {e}")
        return 1

    # Execute node
    logger.info(f"Executing node with inputs: {list(runtime_inputs.keys())}")
    try:
        result = node.run(**runtime_inputs)
        logger.info("Node execution completed successfully")
    except Exception as e:
        logger.error(f"Node execution failed: {e}")
        # Save error information
        with open("/examples/data/output/error.json", 'w') as f:
            json.dump({
                "error": str(e),
                "type": e.__class__.__name__
            }, f, indent=2)
        return 1

    # Save results
    logger.info("Saving execution results")
    try:
        result_path = Path("/examples/data/output/result.json")
        with open(result_path, 'w') as f:
            # Handle non-serializable objects with basic conversion
            try:
                json.dump(result, f, indent=2)
            except TypeError:
                logger.warning("Result not directly JSON serializable, converting to string")
                json.dump({"result": str(result)}, f, indent=2)

        logger.info(f"Results saved to {result_path}")
    except Exception as e:
        logger.error(f"Failed to save results: {e}")
        return 1

    logger.info(f"Node {node_data['name']} execution completed")
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

# Install system dependencies if needed
RUN apt-get update && apt-get install -y --no-install-recommends \\
    make build-essential \\
    && apt-get clean \\
    && rm -rf /var/lib/apt/lists/*

# Copy Kailash SDK
COPY sdk /app/sdk

# Install the SDK and its dependencies
RUN pip install --no-cache-dir -e /app/sdk

# Copy node configuration and entrypoint
COPY node.json /app/node.json
COPY entrypoint.py /app/entrypoint.py

# Create data directories
RUN mkdir -p /examples/data/input /examples/data/output

# Set entrypoint
ENTRYPOINT ["/app/entrypoint.py"]
"""
            )

        # Create SDK directory
        sdk_dir = self.work_dir / "sdk"
        sdk_dir.mkdir(exist_ok=True)

        # Copy SDK files
        self._copy_sdk_files(sdk_dir)

        return dockerfile_path

    def _copy_sdk_files(self, sdk_dir: Path):
        """
        Copy SDK files to the Docker build context.

        Args:
            sdk_dir: Destination directory for SDK files.
        """
        # Copy source directory
        if (self.sdk_path / "src").exists():
            import shutil

            # Copy src directory
            src_dir = self.sdk_path / "src"
            shutil.copytree(src_dir, sdk_dir / "src", dirs_exist_ok=True)

            # Copy setup files
            for setup_file in ["setup.py", "pyproject.toml"]:
                if (self.sdk_path / setup_file).exists():
                    shutil.copy(self.sdk_path / setup_file, sdk_dir / setup_file)
        else:
            raise NodeConfigurationError(
                f"SDK source directory not found at {self.sdk_path}/src"
            )

    def build_image(self) -> str:
        """
        Build the Docker image for the node.

        Returns:
            The name of the built Docker image.
        """
        # Ensure Dockerfile exists
        if not (self.work_dir / "Dockerfile").exists():
            self.prepare_dockerfile()

        logger.info(f"Building Docker image for node {self.node_id}")

        try:
            subprocess.run(
                ["docker", "build", "-t", self.image_name, "."],
                cwd=self.work_dir,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            logger.info(f"Successfully built image: {self.image_name}")
            return self.image_name
        except subprocess.CalledProcessError as e:
            error_msg = f"Failed to build Docker image for node {self.node_id}: {e.stderr.decode()}"
            logger.error(error_msg)
            raise RuntimeError(error_msg)

    def prepare_inputs(self, inputs: Dict[str, Any]):
        """
        Prepare inputs for node execution.

        Args:
            inputs: The inputs to pass to the node.
        """
        input_file = self.input_dir / "inputs.json"
        with open(input_file, "w") as f:
            json.dump(inputs, f, indent=2)

    def run_container(
        self,
        network: str = None,
        env_vars: Dict[str, str] = None,
        resource_limits: Dict[str, str] = None,
    ) -> bool:
        """
        Run the node in a Docker container.

        Args:
            network: Docker network to use.
            env_vars: Environment variables to pass to the container.
            resource_limits: Resource limits (memory, CPU) for the container.

        Returns:
            True if container ran successfully.
        """
        logger.info(f"Running node {self.node_id} in Docker container")

        # Build command
        cmd = ["docker", "run", "--rm"]

        # Add container name
        cmd.extend(["--name", self.container_name])

        # Add network if specified
        if network:
            cmd.extend(["--network", network])

        # Add environment variables
        if env_vars:
            for key, value in env_vars.items():
                cmd.extend(["-e", f"{key}={value}"])

        # Add resource limits
        if resource_limits:
            if "memory" in resource_limits:
                cmd.extend(["--memory", resource_limits["memory"]])
            if "cpu" in resource_limits:
                cmd.extend(["--cpus", resource_limits["cpu"]])

        # Add volume mounts for data
        cmd.extend(
            [
                "-v",
                f"{self.input_dir.absolute()}:/examples/data/input",
                "-v",
                f"{self.output_dir.absolute()}:/examples/data/output",
            ]
        )

        # Use the image
        cmd.append(self.image_name)

        try:
            result = subprocess.run(
                cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
            # Result could be used for logging output if needed
            _ = result

            logger.info(f"Container for node {self.node_id} ran successfully")
            return True
        except subprocess.CalledProcessError as e:
            error_msg = f"Container for node {self.node_id} failed: {e.stderr.decode()}"
            logger.error(error_msg)

            # Check if there's an error file
            error_file = self.output_dir / "error.json"
            if error_file.exists():
                with open(error_file, "r") as f:
                    error_data = json.load(f)
                    error_msg = f"Node execution error: {error_data.get('error', 'Unknown error')}"

            raise NodeExecutionError(error_msg)

    def get_results(self) -> Dict[str, Any]:
        """
        Get the results of node execution.

        Returns:
            The node execution results.
        """
        result_file = self.output_dir / "result.json"
        if result_file.exists():
            with open(result_file, "r") as f:
                return json.load(f)

        error_file = self.output_dir / "error.json"
        if error_file.exists():
            with open(error_file, "r") as f:
                error_data = json.load(f)
                raise NodeExecutionError(
                    f"Node {self.node_id} execution failed: {error_data.get('error', 'Unknown error')}"
                )

        return {"error": "No result or error file found"}

    def cleanup(self):
        """Clean up resources created for this node."""
        if self._created_temp_dir and self.work_dir.exists():
            import shutil

            shutil.rmtree(self.work_dir)


class DockerRuntime:
    """
    Docker-based runtime for executing workflows.

    This runtime executes each node in a separate Docker container,
    handling dependencies, data passing, and workflow orchestration.
    """

    def __init__(
        self,
        base_image: str = "python:3.11-slim",
        network_name: str = "kailash-network",
        work_dir: Optional[str] = None,
        sdk_path: Optional[str] = None,
        resource_limits: Optional[Dict[str, str]] = None,
        task_manager: Optional[TaskManager] = None,
    ):
        """
        Initialize the Docker runtime.

        Args:
            base_image: Base Docker image to use for nodes.
            network_name: Docker network name for container communication.
            work_dir: Working directory for Docker files.
            sdk_path: Path to the Kailash SDK source.
            resource_limits: Default resource limits for containers.
            task_manager: Task manager for tracking workflow execution.
        """
        self.task_manager = task_manager

        self.base_image = base_image
        self.network_name = network_name
        self.resource_limits = resource_limits or {}

        # Working directory
        if work_dir:
            self.work_dir = Path(work_dir)
            self.work_dir.mkdir(parents=True, exist_ok=True)
        else:
            self.work_dir = Path(tempfile.mkdtemp(prefix="kailash_docker_runtime_"))

        # SDK path
        if sdk_path:
            self.sdk_path = Path(sdk_path)
        else:
            # Try to find the SDK path
            import kailash

            kailash_path = Path(kailash.__file__).parent

            # Check if we're in a development environment
            if "site-packages" not in str(kailash_path):
                # Development environment - use parent of src
                self.sdk_path = kailash_path.parent.parent
            else:
                # Installed package - use package directory
                self.sdk_path = kailash_path.parent

        # Create Docker network
        self._create_network()

        # Track node wrappers
        self.node_wrappers = {}

    def _create_task_run(self, workflow: Workflow) -> Optional[str]:
        """Create a task run if task manager is available."""
        if self.task_manager:
            return self.task_manager.create_run(workflow.name)
        return None

    def _update_task_status(
        self, run_id: Optional[str], node_id: str, status: str, output: Any = None
    ):
        """Update task status if task manager is available."""
        if self.task_manager and run_id:
            # For now, just update run status - task tracking needs more setup
            if status == "failed":
                error_msg = (
                    output.get("error", "Unknown error") if output else "Unknown error"
                )
                self.task_manager.update_run_status(run_id, "failed", error_msg)

    def _complete_task_run(
        self, run_id: Optional[str], status: str, result: Any = None
    ):
        """Complete task run if task manager is available."""
        if self.task_manager and run_id:
            if status == "completed":
                self.task_manager.update_run_status(run_id, "completed")
            else:
                error_msg = (
                    result.get("error", "Unknown error") if result else "Unknown error"
                )
                self.task_manager.update_run_status(run_id, "failed", error_msg)

    def _create_network(self):
        """Create a Docker network for container communication."""
        try:
            subprocess.run(
                ["docker", "network", "create", self.network_name],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            logger.info(f"Created Docker network: {self.network_name}")
        except subprocess.CalledProcessError as e:
            # Ignore if network already exists
            if "already exists" not in e.stderr.decode():
                error_msg = f"Failed to create Docker network: {e.stderr.decode()}"
                logger.error(error_msg)
                raise RuntimeError(error_msg)

    def execute(
        self,
        workflow: Workflow,
        inputs: Dict[str, Dict[str, Any]] = None,
        node_resource_limits: Dict[str, Dict[str, str]] = None,
    ) -> Tuple[Dict[str, Dict[str, Any]], str]:
        """
        Execute a workflow using Docker containers.

        Args:
            workflow: The workflow to execute.
            inputs: The inputs for each node.
            node_resource_limits: Resource limits for specific nodes.

        Returns:
            Tuple of (execution_results, run_id).
        """
        # Create task run
        run_id = self._create_task_run(workflow)

        # Default inputs
        inputs = inputs or {}
        node_resource_limits = node_resource_limits or {}

        try:
            # Validate workflow
            workflow.validate()

            # Get execution order
            execution_order = workflow.get_execution_order()

            # Track results
            results = {}

            # Prepare all node wrappers and build images
            logger.info("Preparing Docker containers for workflow execution")
            for node_id, node in workflow.nodes.items():
                self.node_wrappers[node_id] = DockerNodeWrapper(
                    node=node,
                    node_id=node_id,
                    base_image=self.base_image,
                    work_dir=self.work_dir / node_id,
                    sdk_path=self.sdk_path,
                )

                # Build image
                self.node_wrappers[node_id].build_image()

            # Execute nodes in order
            logger.info(f"Executing workflow in order: {execution_order}")
            for node_id in execution_order:
                logger.info(f"Executing node: {node_id}")

                # Get node wrapper
                wrapper = self.node_wrappers[node_id]

                # Update task status
                self._update_task_status(run_id, node_id, "running")

                # Get node inputs
                node_inputs = inputs.get(node_id, {}).copy()

                # Add inputs from upstream nodes
                for upstream_id, mapping in workflow.connections.get(
                    node_id, {}
                ).items():
                    if upstream_id in results:
                        for dest_param, src_param in mapping.items():
                            if src_param in results[upstream_id]:
                                node_inputs[dest_param] = results[upstream_id][
                                    src_param
                                ]

                # Prepare inputs
                wrapper.prepare_inputs(node_inputs)

                # Get resource limits for this node
                resource_limits = None
                if node_id in node_resource_limits:
                    resource_limits = node_resource_limits[node_id]
                elif self.resource_limits:
                    resource_limits = self.resource_limits

                # Run the container
                success = wrapper.run_container(
                    network=self.network_name, resource_limits=resource_limits
                )

                # Get results
                if success:
                    results[node_id] = wrapper.get_results()
                    self._update_task_status(
                        run_id, node_id, "completed", results[node_id]
                    )
                else:
                    self._update_task_status(
                        run_id, node_id, "failed", {"error": "Execution failed"}
                    )
                    raise NodeExecutionError(f"Node {node_id} execution failed")

            # Mark run as completed
            self._complete_task_run(run_id, "completed")

            return results, run_id

        except Exception as e:
            # Handle errors
            logger.error(f"Workflow execution failed: {e}")
            self._complete_task_run(run_id, "failed", {"error": str(e)})
            raise

    def cleanup(self):
        """Clean up Docker resources."""
        # Clean up node wrappers
        for wrapper in self.node_wrappers.values():
            wrapper.cleanup()

        # Remove Docker network
        try:
            subprocess.run(
                ["docker", "network", "rm", self.network_name],
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except Exception as e:
            logger.warning(f"Failed to remove Docker network: {e}")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.cleanup()

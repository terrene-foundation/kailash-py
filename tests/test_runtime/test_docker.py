"""
Tests for the Docker runtime implementation.

These tests verify that the Docker runtime can:
1. Create Docker images for nodes
2. Run nodes in containers
3. Execute workflows with containerized nodes
4. Pass data between containers
5. Handle resource constraints and limits
6. Produce results identical to local execution
"""

import os
import sys
import json
import pytest
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

# Import Kailash components
from kailash.nodes.base import Node
from kailash.nodes.transform.processors import PythonCodeNode
from kailash.workflow.graph import Workflow
from kailash.runtime.docker import DockerRuntime, DockerNodeWrapper
from kailash.runtime.local import LocalRuntime
from kailash.sdk_exceptions import RuntimeError, ConfigurationError, NodeExecutionError


class SimpleNode(Node):
    """Simple test node for Docker runtime testing."""
    
    def get_parameters(self):
        """Return node parameters."""
        return {}
    
    def run(self, value=None, **kwargs):
        """Execute the node."""
        return {"result": value * 2 if value is not None else None}


class TestDockerNodeWrapper:
    """Tests for the DockerNodeWrapper class."""
    
    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for testing."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            yield Path(tmp_dir)
    
    @pytest.fixture
    def sdk_path(self):
        """Get the SDK path for testing."""
        return Path(__file__).parent.parent.parent
    
    @pytest.fixture
    def node_wrapper(self, temp_dir, sdk_path):
        """Create a DockerNodeWrapper instance for testing."""
        node = SimpleNode(name="test_node")
        wrapper = DockerNodeWrapper(
            node=node,
            node_id="test_node",
            work_dir=temp_dir,
            sdk_path=sdk_path
        )
        return wrapper
    
    def test_prepare_dockerfile(self, node_wrapper):
        """Test Dockerfile generation."""
        dockerfile_path = node_wrapper.prepare_dockerfile()
        
        # Check that the file was created
        assert dockerfile_path.exists()
        
        # Check Dockerfile content
        with open(dockerfile_path, 'r') as f:
            content = f.read()
            assert "FROM" in content
            assert "WORKDIR /app" in content
            assert "COPY sdk /app/sdk" in content
            assert "ENTRYPOINT" in content
    
    def test_node_configuration(self, node_wrapper):
        """Test node configuration file generation."""
        node_wrapper.prepare_dockerfile()
        
        # Check node configuration
        node_config_path = node_wrapper.work_dir / "node.json"
        assert node_config_path.exists()
        
        with open(node_config_path, 'r') as f:
            config = json.load(f)
            assert config["class"] == "SimpleNode"
            assert config["node_id"] == "test_node"
            assert config["name"] == "test_node"
    
    @patch('subprocess.run')
    def test_build_image(self, mock_run, node_wrapper):
        """Test Docker image building."""
        # Mock subprocess.run
        mock_run.return_value = MagicMock(
            stdout=b"Successfully built image",
            stderr=b""
        )
        
        # Build image
        image_name = node_wrapper.build_image()
        
        # Check that subprocess.run was called correctly
        mock_run.assert_called_once()
        assert "docker" in mock_run.call_args[0][0]
        assert "build" in mock_run.call_args[0][0]
        
        # Check image name
        assert image_name == "kailash-node-test_node"
    
    @patch('subprocess.run')
    def test_run_container(self, mock_run, node_wrapper, temp_dir):
        """Test running a container."""
        # Mock subprocess.run
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=b"Container ID",
            stderr=b""
        )
        
        # Prepare inputs
        inputs = {"value": 5}
        node_wrapper.prepare_inputs(inputs)
        
        # Run container
        success = node_wrapper.run_container(network="test-network")
        
        # Check that subprocess.run was called correctly
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert "docker" in cmd
        assert "run" in cmd
        assert "--network" in cmd
        assert "test-network" in cmd
        
        # Check success
        assert success is True


class TestDockerRuntime:
    """Tests for the DockerRuntime class."""
    
    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for testing."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            yield Path(tmp_dir)
    
    @pytest.fixture
    def workflow(self):
        """Create a test workflow."""
        workflow = Workflow(name="test_workflow")
        
        # Create nodes
        node1 = SimpleNode(name="node1")
        
        def double_value(value):
            return value * 2
        
        node2 = PythonCodeNode.from_function(
            double_value,
            name="node2"
        )
        
        # Add nodes to workflow
        workflow.add_node("node1", node1)
        workflow.add_node("node2", node2)
        
        # Connect nodes
        workflow.connect("node1", "node2", {"value": "result"})
        
        return workflow
    
    @patch('kailash.runtime.docker.DockerNodeWrapper')
    @patch('subprocess.run')
    def test_docker_runtime_init(self, mock_run, mock_wrapper, temp_dir):
        """Test DockerRuntime initialization."""
        # Mock subprocess.run
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=b"Network created",
            stderr=b""
        )
        
        # Create runtime
        runtime = DockerRuntime(
            work_dir=temp_dir,
            network_name="test-network"
        )
        
        # Check network creation
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert "docker" in cmd
        assert "network" in cmd
        assert "create" in cmd
        assert "test-network" in cmd
    
    @patch('kailash.runtime.docker.DockerNodeWrapper')
    def test_execute_workflow(self, mock_wrapper, workflow, temp_dir):
        """Test workflow execution with Docker runtime."""
        # Mock DockerNodeWrapper
        mock_instance = MagicMock()
        mock_instance.build_image.return_value = "test-image"
        mock_instance.run_container.return_value = True
        mock_instance.get_results.return_value = {"result": 10}
        mock_wrapper.return_value = mock_instance
        
        # Create runtime
        runtime = DockerRuntime(
            work_dir=temp_dir,
            network_name="test-network"
        )
        
        # Execute workflow
        inputs = {"node1": {"value": 5}}
        results, run_id = runtime.execute(workflow, inputs=inputs)
        
        # Check results
        assert "node1" in results
        assert "node2" in results
        assert results["node1"]["result"] == 10
        
        # Check node wrapper usage
        assert mock_wrapper.call_count == 2  # Two nodes
        mock_instance.build_image.assert_called()
        mock_instance.prepare_inputs.assert_called()
        mock_instance.run_container.assert_called()
        mock_instance.get_results.assert_called()
    
    @patch('kailash.runtime.docker.DockerNodeWrapper')
    def test_resource_limits(self, mock_wrapper, workflow, temp_dir):
        """Test resource limits for containers."""
        # Mock DockerNodeWrapper
        mock_instance = MagicMock()
        mock_instance.build_image.return_value = "test-image"
        mock_instance.run_container.return_value = True
        mock_instance.get_results.return_value = {"result": 10}
        mock_wrapper.return_value = mock_instance
        
        # Create runtime
        runtime = DockerRuntime(
            work_dir=temp_dir,
            network_name="test-network"
        )
        
        # Define resource limits
        resource_limits = {
            "node1": {
                "memory": "512m",
                "cpu": "1.0"
            },
            "node2": {
                "memory": "1g",
                "cpu": "2.0"
            }
        }
        
        # Execute workflow
        inputs = {"node1": {"value": 5}}
        results, run_id = runtime.execute(
            workflow, 
            inputs=inputs,
            node_resource_limits=resource_limits
        )
        
        # Check resource limits were passed to run_container
        mock_instance.run_container.assert_called()
        # Check that resource_limits is in the call arguments
        # This is a simple check - would be better to check the exact values
        assert mock_instance.run_container.call_args[1]["resource_limits"] is not None
    
    @patch('subprocess.run')
    def test_cleanup(self, mock_run, temp_dir):
        """Test runtime cleanup."""
        # Mock subprocess.run
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=b"",
            stderr=b""
        )
        
        # Create runtime in context manager
        with DockerRuntime(
            work_dir=temp_dir,
            network_name="test-network"
        ) as runtime:
            pass
        
        # Check network removal
        mock_run.assert_called()
        cmd = mock_run.call_args[0][0]
        assert "docker" in cmd
        assert "network" in cmd
        assert "rm" in cmd
        assert "test-network" in cmd


@pytest.mark.skipif(
    os.environ.get("SKIP_DOCKER_TESTS") == "1",
    reason="Docker integration tests are disabled"
)
class TestDockerIntegration:
    """Integration tests for Docker runtime with real Docker."""
    
    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for testing."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            yield Path(tmp_dir)
    
    @pytest.fixture
    def workflow(self):
        """Create a test workflow."""
        workflow = Workflow(name="test_workflow")
        
        # Create a simple Python function node
        def add_one(value):
            return value + 1
        
        node = PythonCodeNode.from_function(
            add_one,
            name="add_one"
        )
        
        # Add node to workflow
        workflow.add_node("add_one", node)
        
        return workflow
    
    def test_docker_execution(self, workflow, temp_dir):
        """Test running a node in Docker."""
        # Skip if Docker is not available
        try:
            import subprocess
            result = subprocess.run(
                ["docker", "version"],
                capture_output=True,
                check=False
            )
            if result.returncode != 0:
                pytest.skip("Docker is not available")
        except (FileNotFoundError, PermissionError):
            pytest.skip("Docker command not found or permission denied")
        
        # Create runtime
        runtime = DockerRuntime(
            work_dir=temp_dir,
            network_name="test-network-integration"
        )
        
        try:
            # Execute workflow
            inputs = {"add_one": {"value": 5}}
            results, run_id = runtime.execute(workflow, inputs=inputs)
            
            # Check results
            assert "add_one" in results
            assert results["add_one"] == 6
        finally:
            # Clean up
            runtime.cleanup()
    
    def test_compare_with_local(self, workflow, temp_dir):
        """Compare Docker execution with local execution."""
        # Skip if Docker is not available
        try:
            import subprocess
            result = subprocess.run(
                ["docker", "version"],
                capture_output=True,
                check=False
            )
            if result.returncode != 0:
                pytest.skip("Docker is not available")
        except (FileNotFoundError, PermissionError):
            pytest.skip("Docker command not found or permission denied")
        
        # Create runtimes
        docker_runtime = DockerRuntime(
            work_dir=temp_dir,
            network_name="test-network-compare"
        )
        local_runtime = LocalRuntime()
        
        try:
            # Execute workflow with Docker
            inputs = {"add_one": {"value": 5}}
            docker_results, _ = docker_runtime.execute(workflow, inputs=inputs)
            
            # Execute workflow locally
            local_results, _ = local_runtime.execute(workflow, inputs=inputs)
            
            # Compare results
            assert docker_results.keys() == local_results.keys()
            assert docker_results["add_one"] == local_results["add_one"]["result"]
        finally:
            # Clean up
            docker_runtime.cleanup()


if __name__ == "__main__":
    pytest.main(["-xvs", __file__])
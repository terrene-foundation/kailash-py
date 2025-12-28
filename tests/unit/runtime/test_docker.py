"""Unit tests for Docker runtime implementation.

Follows the testing policy:
- Unit tests (Tier 1): Fast, isolated, mocking allowed for external Docker calls
- Tests core Docker runtime logic, containerization, and orchestration
"""

import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict
from unittest.mock import MagicMock, Mock, mock_open, patch

import pytest
from kailash.nodes.base import Node, NodeParameter
from kailash.runtime.docker import DockerNodeWrapper, DockerRuntime
from kailash.sdk_exceptions import NodeConfigurationError, NodeExecutionError
from kailash.workflow.graph import Workflow


class MockSimpleNode(Node):
    """Mock node for testing Docker functionality."""

    def __init__(self, name: str = "mock_node"):
        super().__init__(name=name)
        self.execution_count = 0

    def get_parameters(self):
        return {
            "input_data": NodeParameter(
                name="input_data",
                type=str,
                required=True,
                description="Input data for the node",
            ),
            "multiplier": NodeParameter(
                name="multiplier",
                type=int,
                required=False,
                default=2,
                description="Multiplier for processing",
            ),
        }

    def run(self, **inputs):
        self.execution_count += 1
        input_data = inputs.get("input_data", "default")
        multiplier = inputs.get("multiplier", 2)
        return {
            "result": input_data * multiplier,
            "execution_count": self.execution_count,
        }


class TestDockerNodeWrapper:
    """Test DockerNodeWrapper functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.node = MockSimpleNode("test_node")
        self.temp_dir = Path(tempfile.mkdtemp())
        self.mock_sdk_path = self.temp_dir / "mock_sdk"
        self.mock_sdk_path.mkdir()
        (self.mock_sdk_path / "src").mkdir()
        (self.mock_sdk_path / "src" / "kailash").mkdir()

        # Create mock setup.py
        (self.mock_sdk_path / "setup.py").write_text("# Mock setup.py")

    def teardown_method(self):
        """Clean up test fixtures."""
        import shutil

        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)

    def test_wrapper_initialization(self):
        """Test DockerNodeWrapper initialization."""
        wrapper = DockerNodeWrapper(
            node=self.node,
            node_id="test_node",
            work_dir=self.temp_dir / "wrapper_test",
            sdk_path=self.mock_sdk_path,
        )

        assert wrapper.node == self.node
        assert wrapper.node_id == "test_node"
        assert wrapper.base_image == "python:3.11-slim"
        assert wrapper.image_name == "kailash-node-test_node"
        assert wrapper.container_name == "kailash-test_node"
        assert wrapper.work_dir.exists()
        assert wrapper.input_dir.exists()
        assert wrapper.output_dir.exists()

    def test_wrapper_with_temp_dir(self):
        """Test wrapper creates temp directory when none provided."""
        wrapper = DockerNodeWrapper(
            node=self.node, node_id="temp_test", sdk_path=self.mock_sdk_path
        )

        assert wrapper._created_temp_dir is True
        assert wrapper.work_dir.exists()
        assert "kailash_docker_temp_test_" in str(wrapper.work_dir)

    def test_sdk_path_discovery_failure(self):
        """Test SDK path discovery when it can't be found."""
        with pytest.raises(
            NodeConfigurationError, match="Could not determine SDK path"
        ):
            DockerNodeWrapper(
                node=self.node,
                node_id="test_node",
                work_dir=self.temp_dir / "discovery_test",
                # No sdk_path provided
            )

    def test_prepare_dockerfile(self):
        """Test Dockerfile generation."""
        wrapper = DockerNodeWrapper(
            node=self.node,
            node_id="dockerfile_test",
            work_dir=self.temp_dir / "dockerfile_test",
            sdk_path=self.mock_sdk_path,
        )

        dockerfile_path = wrapper.prepare_dockerfile()

        assert dockerfile_path.exists()
        assert (wrapper.work_dir / "entrypoint.py").exists()
        assert (wrapper.work_dir / "node.json").exists()
        assert (wrapper.work_dir / "sdk").exists()

        # Check node.json content
        with open(wrapper.work_dir / "node.json") as f:
            node_data = json.load(f)

        assert node_data["class"] == "MockSimpleNode"
        assert node_data["node_id"] == "dockerfile_test"
        assert "parameters" in node_data
        assert "input_data" in node_data["parameters"]

    def test_dockerfile_content(self):
        """Test generated Dockerfile content."""
        wrapper = DockerNodeWrapper(
            node=self.node,
            node_id="content_test",
            work_dir=self.temp_dir / "content_test",
            sdk_path=self.mock_sdk_path,
        )

        dockerfile_path = wrapper.prepare_dockerfile()
        dockerfile_content = dockerfile_path.read_text()

        assert "FROM python:3.11-slim" in dockerfile_content
        assert "COPY sdk /app/sdk" in dockerfile_content
        assert "pip install --no-cache-dir -e /app/sdk" in dockerfile_content
        assert 'ENTRYPOINT ["/app/entrypoint.py"]' in dockerfile_content

    def test_entrypoint_content(self):
        """Test generated entrypoint.py content."""
        wrapper = DockerNodeWrapper(
            node=self.node,
            node_id="entrypoint_test",
            work_dir=self.temp_dir / "entrypoint_test",
            sdk_path=self.mock_sdk_path,
        )

        wrapper.prepare_dockerfile()
        entrypoint_content = (wrapper.work_dir / "entrypoint.py").read_text()

        assert "import importlib" in entrypoint_content
        assert 'node_config_path = Path("/app/node.json")' in entrypoint_content
        assert "result = node.execute(**runtime_inputs)" in entrypoint_content
        assert 'logger = logging.getLogger("kailash_node")' in entrypoint_content

    def test_copy_sdk_files_missing_src(self):
        """Test SDK file copying when src directory is missing."""
        bad_sdk_path = self.temp_dir / "bad_sdk"
        bad_sdk_path.mkdir()

        wrapper = DockerNodeWrapper(
            node=self.node,
            node_id="bad_sdk_test",
            work_dir=self.temp_dir / "bad_sdk_test",
            sdk_path=bad_sdk_path,
        )

        with pytest.raises(
            NodeConfigurationError, match="SDK source directory not found"
        ):
            wrapper.prepare_dockerfile()

    @patch("subprocess.run")
    def test_build_image_success(self, mock_subprocess):
        """Test successful Docker image building."""
        mock_subprocess.return_value = Mock(returncode=0)

        wrapper = DockerNodeWrapper(
            node=self.node,
            node_id="build_test",
            work_dir=self.temp_dir / "build_test",
            sdk_path=self.mock_sdk_path,
        )

        # Prepare dockerfile first
        wrapper.prepare_dockerfile()

        image_name = wrapper.build_image()

        assert image_name == "kailash-node-build_test"
        mock_subprocess.assert_called_once()
        call_args = mock_subprocess.call_args[0][0]
        assert call_args == ["docker", "build", "-t", "kailash-node-build_test", "."]

    @patch("subprocess.run")
    def test_build_image_failure(self, mock_subprocess):
        """Test Docker image building failure."""
        mock_subprocess.side_effect = subprocess.CalledProcessError(
            1, "docker build", stderr=b"Build failed"
        )

        wrapper = DockerNodeWrapper(
            node=self.node,
            node_id="fail_test",
            work_dir=self.temp_dir / "fail_test",
            sdk_path=self.mock_sdk_path,
        )

        wrapper.prepare_dockerfile()

        with pytest.raises(
            RuntimeError, match="Failed to build Docker image.*Build failed"
        ):
            wrapper.build_image()

    def test_prepare_inputs(self):
        """Test input preparation for container."""
        wrapper = DockerNodeWrapper(
            node=self.node,
            node_id="input_test",
            work_dir=self.temp_dir / "input_test",
            sdk_path=self.mock_sdk_path,
        )

        test_inputs = {"input_data": "test_value", "multiplier": 3}
        wrapper.prepare_inputs(test_inputs)

        input_file = wrapper.input_dir / "inputs.json"
        assert input_file.exists()

        with open(input_file) as f:
            saved_inputs = json.load(f)

        assert saved_inputs == test_inputs

    @patch("subprocess.run")
    def test_run_container_success(self, mock_subprocess):
        """Test successful container execution."""
        mock_subprocess.return_value = Mock(returncode=0)

        wrapper = DockerNodeWrapper(
            node=self.node,
            node_id="run_test",
            work_dir=self.temp_dir / "run_test",
            sdk_path=self.mock_sdk_path,
        )

        success = wrapper.run_container(
            network="test_network",
            env_vars={"TEST_VAR": "test_value"},
            resource_limits={"memory": "1g", "cpu": "0.5"},
        )

        assert success is True
        mock_subprocess.assert_called_once()
        call_args = mock_subprocess.call_args[0][0]

        assert "docker" in call_args
        assert "run" in call_args
        assert "--rm" in call_args
        assert "--network" in call_args
        assert "test_network" in call_args
        assert "-e" in call_args
        assert "TEST_VAR=test_value" in call_args
        assert "--memory" in call_args
        assert "1g" in call_args
        assert "--cpus" in call_args
        assert "0.5" in call_args

    @patch("subprocess.run")
    def test_run_container_failure(self, mock_subprocess):
        """Test container execution failure."""
        mock_subprocess.side_effect = subprocess.CalledProcessError(
            1, "docker run", stderr=b"Container failed"
        )

        wrapper = DockerNodeWrapper(
            node=self.node,
            node_id="fail_run_test",
            work_dir=self.temp_dir / "fail_run_test",
            sdk_path=self.mock_sdk_path,
        )

        with pytest.raises(
            NodeExecutionError, match="Container.*failed.*Container failed"
        ):
            wrapper.run_container()

    def test_get_results_success(self):
        """Test getting results from successful execution."""
        wrapper = DockerNodeWrapper(
            node=self.node,
            node_id="result_test",
            work_dir=self.temp_dir / "result_test",
            sdk_path=self.mock_sdk_path,
        )

        # Create mock result file
        result_data = {"result": "test_output", "status": "success"}
        result_file = wrapper.output_dir / "result.json"
        with open(result_file, "w") as f:
            json.dump(result_data, f)

        results = wrapper.get_results()
        assert results == result_data

    def test_get_results_error(self):
        """Test getting results when execution failed."""
        wrapper = DockerNodeWrapper(
            node=self.node,
            node_id="error_test",
            work_dir=self.temp_dir / "error_test",
            sdk_path=self.mock_sdk_path,
        )

        # Create mock error file
        error_data = {"error": "Execution failed", "type": "RuntimeError"}
        error_file = wrapper.output_dir / "error.json"
        with open(error_file, "w") as f:
            json.dump(error_data, f)

        with pytest.raises(
            NodeExecutionError,
            match="Node error_test execution failed.*Execution failed",
        ):
            wrapper.get_results()

    def test_get_results_no_files(self):
        """Test getting results when no result or error files exist."""
        wrapper = DockerNodeWrapper(
            node=self.node,
            node_id="nofile_test",
            work_dir=self.temp_dir / "nofile_test",
            sdk_path=self.mock_sdk_path,
        )

        results = wrapper.get_results()
        assert results == {"error": "No result or error file found"}

    def test_cleanup(self):
        """Test wrapper cleanup."""
        wrapper = DockerNodeWrapper(
            node=self.node,
            node_id="cleanup_test",
            sdk_path=self.mock_sdk_path,
            # Using temp dir creation
        )

        work_dir = wrapper.work_dir
        assert work_dir.exists()

        wrapper.cleanup()

        # Temp directory should be removed
        assert not work_dir.exists()


class TestDockerRuntime:
    """Test DockerRuntime functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.mock_sdk_path = self.temp_dir / "mock_sdk"
        self.mock_sdk_path.mkdir()
        (self.mock_sdk_path / "src").mkdir()

        # Mock workflow
        self.workflow = Mock(spec=Workflow)
        self.workflow.name = "test_workflow"
        self.workflow.nodes = {
            "node1": MockSimpleNode("node1"),
            "node2": MockSimpleNode("node2"),
        }
        self.workflow.connections = {"node2": {"node1": {"result": "input_data"}}}
        self.workflow.validate = Mock()
        self.workflow.get_execution_order = Mock(return_value=["node1", "node2"])

    def teardown_method(self):
        """Clean up test fixtures."""
        import shutil

        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)

    @patch("subprocess.run")
    def test_runtime_initialization(self, mock_subprocess):
        """Test DockerRuntime initialization."""
        mock_subprocess.return_value = Mock(returncode=0)

        runtime = DockerRuntime(
            base_image="test:latest",
            network_name="test_network",
            work_dir=str(self.temp_dir),
            sdk_path=str(self.mock_sdk_path),
            resource_limits={"memory": "2g"},
        )

        assert runtime.base_image == "test:latest"
        assert runtime.network_name == "test_network"
        assert runtime.resource_limits == {"memory": "2g"}
        assert runtime.work_dir == self.temp_dir
        assert runtime.sdk_path == self.mock_sdk_path

        # Check network creation was called
        mock_subprocess.assert_called_once()
        call_args = mock_subprocess.call_args[0][0]
        assert call_args == ["docker", "network", "create", "test_network"]

    @patch("subprocess.run")
    def test_runtime_network_exists(self, mock_subprocess):
        """Test runtime when Docker network already exists."""
        mock_subprocess.side_effect = subprocess.CalledProcessError(
            1, "docker network create", stderr=b"network already exists"
        )

        # Should not raise error if network already exists
        runtime = DockerRuntime(
            network_name="existing_network",
            work_dir=str(self.temp_dir),
            sdk_path=str(self.mock_sdk_path),
        )

        assert runtime.network_name == "existing_network"

    @patch("subprocess.run")
    def test_runtime_network_create_failure(self, mock_subprocess):
        """Test runtime network creation failure."""
        mock_subprocess.side_effect = subprocess.CalledProcessError(
            1, "docker network create", stderr=b"unknown error"
        )

        with pytest.raises(
            RuntimeError, match="Failed to create Docker network.*unknown error"
        ):
            DockerRuntime(work_dir=str(self.temp_dir), sdk_path=str(self.mock_sdk_path))

    @patch("kailash.runtime.docker.DockerNodeWrapper")
    @patch("subprocess.run")
    def test_execute_workflow_success(self, mock_subprocess, mock_wrapper_class):
        """Test successful workflow execution."""
        # Mock network creation
        mock_subprocess.return_value = Mock(returncode=0)

        # Mock wrapper instances
        mock_wrapper1 = Mock()
        mock_wrapper1.build_image.return_value = "image1"
        mock_wrapper1.run_container.return_value = True
        mock_wrapper1.get_results.return_value = {"result": "output1"}

        mock_wrapper2 = Mock()
        mock_wrapper2.build_image.return_value = "image2"
        mock_wrapper2.run_container.return_value = True
        mock_wrapper2.get_results.return_value = {"result": "output2"}

        mock_wrapper_class.side_effect = [mock_wrapper1, mock_wrapper2]

        runtime = DockerRuntime(
            work_dir=str(self.temp_dir), sdk_path=str(self.mock_sdk_path)
        )

        inputs = {"node1": {"input_data": "test_input"}, "node2": {"multiplier": 3}}

        results, run_id = runtime.execute(self.workflow, inputs)

        # Verify workflow validation
        self.workflow.validate.assert_called_once_with(runtime_parameters=inputs)

        # Verify wrapper creation
        assert mock_wrapper_class.call_count == 2

        # Verify execution
        mock_wrapper1.build_image.assert_called_once()
        mock_wrapper1.run_container.assert_called_once()
        mock_wrapper2.build_image.assert_called_once()
        mock_wrapper2.run_container.assert_called_once()

        # Check results
        assert results == {
            "node1": {"result": "output1"},
            "node2": {"result": "output2"},
        }
        assert run_id is None  # No task manager

    @patch("kailash.runtime.docker.DockerNodeWrapper")
    @patch("subprocess.run")
    def test_execute_with_task_manager(self, mock_subprocess, mock_wrapper_class):
        """Test workflow execution with task manager."""
        # Mock network creation
        mock_subprocess.return_value = Mock(returncode=0)

        # Mock task manager
        mock_task_manager = Mock()
        mock_task_manager.create_run.return_value = "run_123"

        # Mock wrapper
        mock_wrapper = Mock()
        mock_wrapper.build_image.return_value = "image1"
        mock_wrapper.run_container.return_value = True
        mock_wrapper.get_results.return_value = {"result": "output1"}
        mock_wrapper_class.return_value = mock_wrapper

        # Simple workflow with one node
        simple_workflow = Mock(spec=Workflow)
        simple_workflow.name = "simple_test"
        simple_workflow.nodes = {"node1": MockSimpleNode("node1")}
        simple_workflow.connections = {}
        simple_workflow.validate = Mock()
        simple_workflow.get_execution_order = Mock(return_value=["node1"])

        runtime = DockerRuntime(
            work_dir=str(self.temp_dir),
            sdk_path=str(self.mock_sdk_path),
            task_manager=mock_task_manager,
        )

        results, run_id = runtime.execute(simple_workflow)

        # Verify task manager calls
        mock_task_manager.create_run.assert_called_once_with("simple_test")
        mock_task_manager.update_run_status.assert_called_with("run_123", "completed")

        assert run_id == "run_123"

    @patch("kailash.runtime.docker.DockerNodeWrapper")
    @patch("subprocess.run")
    def test_execute_node_failure(self, mock_subprocess, mock_wrapper_class):
        """Test workflow execution with node failure."""
        # Mock network creation
        mock_subprocess.return_value = Mock(returncode=0)

        # Mock wrapper that fails
        mock_wrapper = Mock()
        mock_wrapper.build_image.return_value = "image1"
        mock_wrapper.run_container.return_value = False  # Failure
        mock_wrapper_class.return_value = mock_wrapper

        # Simple workflow with one node
        simple_workflow = Mock(spec=Workflow)
        simple_workflow.name = "fail_test"
        simple_workflow.nodes = {"node1": MockSimpleNode("node1")}
        simple_workflow.connections = {}
        simple_workflow.validate = Mock()
        simple_workflow.get_execution_order = Mock(return_value=["node1"])

        runtime = DockerRuntime(
            work_dir=str(self.temp_dir), sdk_path=str(self.mock_sdk_path)
        )

        with pytest.raises(NodeExecutionError, match="Node node1 execution failed"):
            runtime.execute(simple_workflow)

    @patch("kailash.runtime.docker.DockerNodeWrapper")
    @patch("subprocess.run")
    def test_execute_data_passing(self, mock_subprocess, mock_wrapper_class):
        """Test data passing between nodes in workflow."""
        # Mock network creation
        mock_subprocess.return_value = Mock(returncode=0)

        # Mock wrappers
        mock_wrapper1 = Mock()
        mock_wrapper1.build_image.return_value = "image1"
        mock_wrapper1.run_container.return_value = True
        mock_wrapper1.get_results.return_value = {"result": "upstream_data"}

        mock_wrapper2 = Mock()
        mock_wrapper2.build_image.return_value = "image2"
        mock_wrapper2.run_container.return_value = True
        mock_wrapper2.get_results.return_value = {"result": "downstream_data"}

        mock_wrapper_class.side_effect = [mock_wrapper1, mock_wrapper2]

        runtime = DockerRuntime(
            work_dir=str(self.temp_dir), sdk_path=str(self.mock_sdk_path)
        )

        # Create workflow with correct connection mapping
        # The docker runtime looks for workflow.connections[node_id][upstream_id][dest_param] = src_param
        test_workflow = Mock(spec=Workflow)
        test_workflow.name = "data_passing_test"
        test_workflow.nodes = {
            "node1": MockSimpleNode("node1"),
            "node2": MockSimpleNode("node2"),
        }
        # Correct format: connections[dest_node][src_node][dest_param] = src_param
        test_workflow.connections = {"node2": {"node1": {"input_data": "result"}}}
        test_workflow.validate = Mock()
        test_workflow.get_execution_order = Mock(return_value=["node1", "node2"])

        results, _ = runtime.execute(test_workflow)

        # Verify input preparation was called properly
        # First node gets original inputs
        mock_wrapper1.prepare_inputs.assert_called_once()
        call_args = mock_wrapper1.prepare_inputs.call_args[0][0]
        assert call_args == {}

        # Second node gets data from first node (input_data = result from node1)
        mock_wrapper2.prepare_inputs.assert_called_once()
        call_args = mock_wrapper2.prepare_inputs.call_args[0][0]
        assert call_args == {"input_data": "upstream_data"}

    @patch("subprocess.run")
    def test_cleanup(self, mock_subprocess):
        """Test runtime cleanup."""
        # Mock network creation
        mock_subprocess.return_value = Mock(returncode=0)

        runtime = DockerRuntime(
            network_name="cleanup_test",
            work_dir=str(self.temp_dir),
            sdk_path=str(self.mock_sdk_path),
        )

        # Add mock wrappers
        mock_wrapper1 = Mock()
        mock_wrapper2 = Mock()
        runtime.node_wrappers = {"node1": mock_wrapper1, "node2": mock_wrapper2}

        runtime.cleanup()

        # Verify wrapper cleanup
        mock_wrapper1.cleanup.assert_called_once()
        mock_wrapper2.cleanup.assert_called_once()

        # Verify network removal (called twice - create + remove)
        assert mock_subprocess.call_count == 2
        remove_call = mock_subprocess.call_args_list[1]
        assert remove_call[0][0] == ["docker", "network", "rm", "cleanup_test"]

    @patch("subprocess.run")
    def test_context_manager(self, mock_subprocess):
        """Test DockerRuntime as context manager."""
        mock_subprocess.return_value = Mock(returncode=0)

        with DockerRuntime(
            work_dir=str(self.temp_dir), sdk_path=str(self.mock_sdk_path)
        ) as runtime:
            assert isinstance(runtime, DockerRuntime)

        # Cleanup should be called automatically
        assert mock_subprocess.call_count == 2  # create + remove network


class TestDockerRuntimeIntegration:
    """Integration-style tests for Docker runtime (still unit tests but more comprehensive)."""

    def setup_method(self):
        """Set up integration test fixtures."""
        self.temp_dir = Path(tempfile.mkdtemp())

        # Create more realistic mock SDK structure
        self.mock_sdk_path = self.temp_dir / "sdk"
        self.mock_sdk_path.mkdir()
        (self.mock_sdk_path / "src" / "kailash").mkdir(parents=True)
        (self.mock_sdk_path / "setup.py").write_text("# Mock setup")

        # Create realistic workflow
        from kailash.workflow.builder import WorkflowBuilder

        self.builder = WorkflowBuilder()

        # Don't actually add nodes - just mock the workflow structure
        self.workflow = Mock(spec=Workflow)
        self.workflow.name = "integration_test"
        self.workflow.nodes = {
            "processor": MockSimpleNode("processor"),
            "formatter": MockSimpleNode("formatter"),
        }
        self.workflow.connections = {
            "formatter": {"processor": {"result": "input_data"}}
        }
        self.workflow.validate = Mock()
        self.workflow.get_execution_order = Mock(
            return_value=["processor", "formatter"]
        )

    def teardown_method(self):
        """Clean up integration test fixtures."""
        import shutil

        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)

    @patch("subprocess.run")
    @patch("kailash.runtime.docker.DockerNodeWrapper.run_container")
    @patch("kailash.runtime.docker.DockerNodeWrapper.build_image")
    def test_full_workflow_execution_mock(self, mock_build, mock_run, mock_subprocess):
        """Test full workflow execution with comprehensive mocking."""
        # Mock Docker calls
        mock_subprocess.return_value = Mock(returncode=0)
        mock_build.return_value = "test_image"
        mock_run.return_value = True

        # Create results directory structure and mock results
        runtime = DockerRuntime(
            work_dir=str(self.temp_dir / "runtime"), sdk_path=str(self.mock_sdk_path)
        )

        # Mock get_results to return expected data
        with patch.object(DockerNodeWrapper, "get_results") as mock_get_results:
            mock_get_results.side_effect = [
                {"result": "processed_data"},  # processor result
                {"result": "formatted_data"},  # formatter result
            ]

            inputs = {"processor": {"input_data": "raw_data", "multiplier": 2}}

            results, run_id = runtime.execute(self.workflow, inputs)

            # Verify execution flow
            assert len(runtime.node_wrappers) == 2
            assert "processor" in runtime.node_wrappers
            assert "formatter" in runtime.node_wrappers

            # Verify results
            assert results["processor"]["result"] == "processed_data"
            assert results["formatter"]["result"] == "formatted_data"

            # Verify build was called for both nodes
            assert mock_build.call_count == 2
            assert mock_run.call_count == 2

    @patch("subprocess.run")
    def test_resource_limits_propagation(self, mock_subprocess):
        """Test that resource limits are properly propagated to containers."""
        mock_subprocess.return_value = Mock(returncode=0)

        runtime = DockerRuntime(
            work_dir=str(self.temp_dir / "limits"),
            sdk_path=str(self.mock_sdk_path),
            resource_limits={"memory": "1g", "cpu": "0.5"},
        )

        # Create a single node workflow
        simple_workflow = Mock(spec=Workflow)
        simple_workflow.name = "limits_test"
        simple_workflow.nodes = {"node1": MockSimpleNode("node1")}
        simple_workflow.connections = {}
        simple_workflow.validate = Mock()
        simple_workflow.get_execution_order = Mock(return_value=["node1"])

        with (
            patch.object(DockerNodeWrapper, "build_image"),
            patch.object(DockerNodeWrapper, "run_container") as mock_run,
            patch.object(DockerNodeWrapper, "get_results") as mock_results,
        ):

            mock_run.return_value = True
            mock_results.return_value = {"result": "test"}

            runtime.execute(simple_workflow)

            # Verify resource limits were passed to run_container
            mock_run.assert_called_once()
            call_kwargs = mock_run.call_args[1]
            assert call_kwargs["resource_limits"] == {"memory": "1g", "cpu": "0.5"}

    def test_dockerfile_generation_content(self):
        """Test comprehensive Dockerfile generation."""
        node = MockSimpleNode("comprehensive_test")

        wrapper = DockerNodeWrapper(
            node=node,
            node_id="comprehensive",
            work_dir=self.temp_dir / "comprehensive",
            sdk_path=self.mock_sdk_path,
            base_image="python:3.11-alpine",
        )

        dockerfile_path = wrapper.prepare_dockerfile()
        dockerfile_content = dockerfile_path.read_text()

        # Verify comprehensive Dockerfile content
        expected_lines = [
            "FROM python:3.11-alpine",
            "WORKDIR /app",
            "COPY sdk /app/sdk",
            "RUN pip install --no-cache-dir -e /app/sdk",
            "COPY node.json /app/node.json",
            "COPY entrypoint.py /app/entrypoint.py",
            'ENTRYPOINT ["/app/entrypoint.py"]',
        ]

        for line in expected_lines:
            assert line in dockerfile_content

        # Verify node configuration
        node_config_path = wrapper.work_dir / "node.json"
        with open(node_config_path) as f:
            node_data = json.load(f)

        assert node_data["class"] == "MockSimpleNode"
        assert node_data["module"] == "tests.unit.runtime.test_docker"
        assert "parameters" in node_data
        assert len(node_data["parameters"]) == 2  # input_data and multiplier

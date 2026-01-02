"""Unit tests for WorkflowRunner.

Follows the testing policy:
- Unit tests (Tier 1): Fast, isolated, mocking allowed for external dependencies
- Tests the high-level workflow runner interface and runtime selection
"""

import logging
from unittest.mock import Mock, patch

import pytest
from kailash.nodes.base import Node, NodeParameter
from kailash.runtime.runner import WorkflowRunner
from kailash.tracking import TaskManager
from kailash.workflow.graph import Workflow


class MockNode(Node):
    """Mock node for testing."""

    def __init__(self, name: str = "mock_node", **kwargs):
        super().__init__(name=name, **kwargs)
        self.executed = False
        self.return_value = kwargs.get("return_value", {"result": "success"})

    def get_parameters(self):
        return {
            "input_data": NodeParameter(
                name="input_data",
                type=str,
                required=False,
                description="Input data for the node",
            )
        }

    def execute(self, **inputs):
        self.executed = True
        self.last_inputs = inputs
        return self.return_value


class MockWorkflow(Workflow):
    """Mock workflow for testing."""

    def __init__(self, name="test_workflow"):
        super().__init__(workflow_id=f"test_{name}", name=name)
        self._node_instances = {}

    def validate(self, runtime_parameters=None):
        return True


class TestWorkflowRunnerInitialization:
    """Test WorkflowRunner initialization and configuration."""

    def test_default_initialization(self):
        """Test WorkflowRunner with default configuration."""
        runner = WorkflowRunner()

        assert runner.debug is False
        assert runner.task_manager is not None
        assert runner.logger.name == "kailash.runner"

    def test_custom_initialization(self):
        """Test WorkflowRunner with custom configuration."""
        task_manager = Mock(spec=TaskManager)

        runner = WorkflowRunner(debug=True, task_manager=task_manager)

        assert runner.debug is True
        assert runner.task_manager == task_manager
        assert runner.logger.name == "kailash.runner"

    def test_logging_configuration_debug(self):
        """Test logging configuration in debug mode."""
        with patch("logging.basicConfig") as mock_config:
            WorkflowRunner(debug=True)

            mock_config.assert_called_once()
            call_args = mock_config.call_args
            assert call_args[1]["level"] == logging.DEBUG

    def test_logging_configuration_normal(self):
        """Test logging configuration in normal mode."""
        with patch("logging.basicConfig") as mock_config:
            WorkflowRunner(debug=False)

            mock_config.assert_called_once()
            call_args = mock_config.call_args
            assert call_args[1]["level"] == logging.INFO


class TestWorkflowRunnerExecution:
    """Test workflow execution functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.task_manager = Mock(spec=TaskManager)
        self.runner = WorkflowRunner(debug=True, task_manager=self.task_manager)
        self.workflow = MockWorkflow("test_workflow")

        # Add mock node to workflow
        self.node = MockNode("test_node")
        self.workflow._node_instances = {"test_node": self.node}
        self.workflow.graph.add_node("test_node")

    @patch("kailash.runtime.runner.LocalRuntime")
    def test_run_workflow_success(self, mock_runtime_class):
        """Test successful workflow execution."""
        # Mock runtime
        mock_runtime = Mock()
        mock_runtime.execute.return_value = (
            {"test_node": {"result": "success"}},
            "run_123",
        )
        mock_runtime_class.return_value = mock_runtime

        results, run_id = self.runner.run(self.workflow)

        assert results == {"test_node": {"result": "success"}}
        assert run_id == "run_123"

        # Verify runtime was created with debug flag
        mock_runtime_class.assert_called_once_with(debug=True)

        # Verify runtime.execute was called correctly
        mock_runtime.execute.assert_called_once_with(
            workflow=self.workflow, task_manager=self.task_manager, parameters=None
        )

    @patch("kailash.runtime.runner.LocalRuntime")
    def test_run_workflow_with_parameters(self, mock_runtime_class):
        """Test workflow execution with parameters."""
        # Mock runtime
        mock_runtime = Mock()
        mock_runtime.execute.return_value = (
            {"test_node": {"result": "success"}},
            "run_123",
        )
        mock_runtime_class.return_value = mock_runtime

        parameters = {"test_node": {"input_data": "test_value"}}

        results, run_id = self.runner.run(self.workflow, parameters=parameters)

        assert results == {"test_node": {"result": "success"}}
        assert run_id == "run_123"

        # Verify parameters were passed correctly
        mock_runtime.execute.assert_called_once_with(
            workflow=self.workflow,
            task_manager=self.task_manager,
            parameters=parameters,
        )

    def test_run_workflow_invalid_runtime(self):
        """Test workflow execution with invalid runtime type."""
        with pytest.raises(ValueError, match="Unknown runtime type: invalid"):
            self.runner.run(self.workflow, runtime_type="invalid")

    @patch("kailash.runtime.runner.LocalRuntime")
    def test_run_workflow_execution_failure(self, mock_runtime_class):
        """Test workflow execution failure handling."""
        # Mock runtime that raises exception
        mock_runtime = Mock()
        mock_runtime.execute.side_effect = RuntimeError("Execution failed")
        mock_runtime_class.return_value = mock_runtime

        with pytest.raises(RuntimeError, match="Execution failed"):
            self.runner.run(self.workflow)

    @patch("kailash.runtime.runner.LocalRuntime")
    def test_run_workflow_different_runtime_types(self, mock_runtime_class):
        """Test workflow execution with different runtime types."""
        # Mock runtime
        mock_runtime = Mock()
        mock_runtime.execute.return_value = ({}, "run_123")
        mock_runtime_class.return_value = mock_runtime

        # Test local runtime (default)
        self.runner.run(self.workflow, runtime_type="local")
        mock_runtime_class.assert_called_with(debug=True)

        # Test local runtime (explicit)
        mock_runtime_class.reset_mock()
        self.runner.run(self.workflow, runtime_type="local")
        mock_runtime_class.assert_called_with(debug=True)


class TestWorkflowRunnerValidation:
    """Test workflow validation functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.runner = WorkflowRunner(debug=True)
        self.workflow = MockWorkflow("test_workflow")

    @patch("kailash.runtime.runner.LocalRuntime")
    def test_validate_workflow(self, mock_runtime_class):
        """Test workflow validation."""
        # Mock runtime
        mock_runtime = Mock()
        mock_runtime.validate_workflow.return_value = ["Warning: Node disconnected"]
        mock_runtime_class.return_value = mock_runtime

        warnings = self.runner.validate(self.workflow)

        assert warnings == ["Warning: Node disconnected"]

        # Verify runtime was created with debug flag
        mock_runtime_class.assert_called_once_with(debug=True)

        # Verify validate_workflow was called
        mock_runtime.validate_workflow.assert_called_once_with(self.workflow)

    @patch("kailash.runtime.runner.LocalRuntime")
    def test_validate_workflow_no_warnings(self, mock_runtime_class):
        """Test workflow validation with no warnings."""
        # Mock runtime
        mock_runtime = Mock()
        mock_runtime.validate_workflow.return_value = []
        mock_runtime_class.return_value = mock_runtime

        warnings = self.runner.validate(self.workflow)

        assert warnings == []


class TestWorkflowRunnerTaskManagement:
    """Test task management functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.task_manager = Mock(spec=TaskManager)
        self.runner = WorkflowRunner(debug=True, task_manager=self.task_manager)

    def test_get_run_status(self):
        """Test getting run status."""
        # Mock task manager response
        expected_data = {
            "run_id": "run_123",
            "status": "completed",
            "started_at": "2023-01-01T00:00:00Z",
            "completed_at": "2023-01-01T00:01:00Z",
        }
        mock_summary = Mock()
        mock_summary.model_dump.return_value = expected_data
        self.task_manager.get_run_summary.return_value = mock_summary

        status = self.runner.get_run_status("run_123")

        assert status == expected_data
        self.task_manager.get_run_summary.assert_called_once_with("run_123")
        mock_summary.model_dump.assert_called_once()

    def test_get_run_status_not_found(self):
        """Test getting run status when run is not found."""
        self.task_manager.get_run_summary.return_value = None

        status = self.runner.get_run_status("non_existent")

        assert status == {}
        self.task_manager.get_run_summary.assert_called_once_with("non_existent")

    def test_get_run_history_default(self):
        """Test getting run history with default parameters."""
        # Mock task manager response
        expected_data = [
            {
                "run_id": "run_123",
                "workflow_name": "test_workflow",
                "status": "completed",
            },
            {"run_id": "run_124", "workflow_name": "test_workflow", "status": "failed"},
        ]
        mock_runs = []
        for data in expected_data:
            mock_run = Mock()
            mock_run.model_dump.return_value = data
            mock_runs.append(mock_run)
        self.task_manager.list_runs.return_value = mock_runs

        history = self.runner.get_run_history()

        assert history == expected_data
        self.task_manager.list_runs.assert_called_once_with(
            workflow_name=None, limit=10
        )

    def test_get_run_history_with_filters(self):
        """Test getting run history with filters."""
        # Mock task manager response
        expected_data = [
            {
                "run_id": "run_123",
                "workflow_name": "specific_workflow",
                "status": "completed",
            }
        ]
        mock_runs = []
        for data in expected_data:
            mock_run = Mock()
            mock_run.model_dump.return_value = data
            mock_runs.append(mock_run)
        self.task_manager.list_runs.return_value = mock_runs

        history = self.runner.get_run_history(
            workflow_name="specific_workflow", limit=5
        )

        assert history == expected_data
        self.task_manager.list_runs.assert_called_once_with(
            workflow_name="specific_workflow", limit=5
        )


class TestWorkflowRunnerLogging:
    """Test logging functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.task_manager = Mock(spec=TaskManager)
        self.runner = WorkflowRunner(debug=True, task_manager=self.task_manager)
        self.workflow = MockWorkflow("test_workflow")

    @patch("kailash.runtime.runner.LocalRuntime")
    def test_logging_workflow_start(self, mock_runtime_class):
        """Test logging when workflow starts."""
        # Mock runtime
        mock_runtime = Mock()
        mock_runtime.execute.return_value = ({}, "run_123")
        mock_runtime_class.return_value = mock_runtime

        with patch.object(self.runner.logger, "info") as mock_info:
            self.runner.run(self.workflow)

            # Check that workflow start was logged
            mock_info.assert_any_call("Starting workflow: test_workflow")
            mock_info.assert_any_call("Workflow completed successfully: run_123")

    @patch("kailash.runtime.runner.LocalRuntime")
    def test_logging_workflow_failure(self, mock_runtime_class):
        """Test logging when workflow fails."""
        # Mock runtime that raises exception
        mock_runtime = Mock()
        mock_runtime.execute.side_effect = RuntimeError("Test failure")
        mock_runtime_class.return_value = mock_runtime

        with patch.object(self.runner.logger, "error") as mock_error:
            with pytest.raises(RuntimeError):
                self.runner.run(self.workflow)

            # Check that failure was logged
            mock_error.assert_called_once_with("Workflow failed: Test failure")


class TestWorkflowRunnerIntegration:
    """Test integration scenarios."""

    def setup_method(self):
        """Set up test fixtures."""
        self.runner = WorkflowRunner(debug=False)
        self.workflow = MockWorkflow("integration_test")

    @patch("kailash.runtime.runner.LocalRuntime")
    def test_end_to_end_workflow_execution(self, mock_runtime_class):
        """Test complete workflow execution flow."""
        # Mock runtime
        mock_runtime = Mock()
        mock_runtime.execute.return_value = (
            {"node1": {"result": "data"}, "node2": {"processed": "data"}},
            "run_integration_123",
        )
        mock_runtime_class.return_value = mock_runtime

        # Execute workflow
        results, run_id = self.runner.run(
            self.workflow,
            parameters={"node1": {"input": "test_data"}},
            runtime_type="local",
        )

        # Verify results
        assert "node1" in results
        assert "node2" in results
        assert results["node1"]["result"] == "data"
        assert results["node2"]["processed"] == "data"
        assert run_id == "run_integration_123"

        # Verify runtime configuration
        mock_runtime_class.assert_called_once_with(debug=False)

        # Verify execution call
        mock_runtime.execute.assert_called_once_with(
            workflow=self.workflow,
            task_manager=self.runner.task_manager,
            parameters={"node1": {"input": "test_data"}},
        )

    def test_runner_with_different_configurations(self):
        """Test runner with different initialization configurations."""
        # Test with debug enabled
        debug_runner = WorkflowRunner(debug=True)
        assert debug_runner.debug is True

        # Test with custom task manager
        custom_task_manager = Mock(spec=TaskManager)
        custom_runner = WorkflowRunner(task_manager=custom_task_manager)
        assert custom_runner.task_manager == custom_task_manager

        # Test with both custom settings
        both_runner = WorkflowRunner(debug=True, task_manager=custom_task_manager)
        assert both_runner.debug is True
        assert both_runner.task_manager == custom_task_manager

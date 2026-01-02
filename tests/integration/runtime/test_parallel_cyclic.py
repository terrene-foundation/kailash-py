"""Unit tests for ParallelCyclicRuntime.

Follows the testing policy:
- Unit tests (Tier 1): Fast, isolated, mocking allowed for external dependencies
- Tests the enhanced parallel runtime with cyclic workflow support
"""

import logging
from concurrent.futures import Future
from unittest.mock import Mock, patch

import networkx as nx
import pytest
from kailash.nodes.base import Node, NodeParameter
from kailash.runtime.parallel_cyclic import ParallelCyclicRuntime
from kailash.sdk_exceptions import RuntimeExecutionError, WorkflowExecutionError
from kailash.tracking import TaskManager, TaskStatus
from kailash.workflow.graph import Workflow


class MockNode(Node):
    """Mock node for testing."""

    def __init__(self, name: str = "mock_node", **kwargs):
        super().__init__(name=name, **kwargs)
        self.executed = False
        self.execution_count = 0
        self.return_value = kwargs.get("return_value", {"result": "success"})
        self.should_fail = kwargs.get("should_fail", False)
        self.fail_message = kwargs.get("fail_message", "Mock node failure")
        self.execution_delay = kwargs.get("execution_delay", 0)

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
        self.execution_count += 1
        self.last_inputs = inputs

        # Simulate execution delay for testing parallel execution
        if self.execution_delay > 0:
            import time

            time.sleep(self.execution_delay)

        if self.should_fail:
            raise RuntimeError(self.fail_message)

        return self.return_value


class MockWorkflow(Workflow):
    """Mock workflow for testing."""

    def __init__(self, name="test_workflow", has_cycles=False):
        super().__init__(workflow_id=f"test_{name}", name=name)
        self._has_cycles = has_cycles
        self._validation_error = None
        self._node_instances = {}

    def has_cycles(self):
        return self._has_cycles

    def validate(self, runtime_parameters=None):
        if self._validation_error:
            raise self._validation_error
        return True

    def set_validation_error(self, error):
        self._validation_error = error


class TestParallelCyclicRuntimeInitialization:
    """Test ParallelCyclicRuntime initialization and configuration."""

    def test_default_initialization(self):
        """Test ParallelCyclicRuntime with default configuration."""
        runtime = ParallelCyclicRuntime()

        assert runtime.debug is False
        assert runtime.max_workers == 4
        assert runtime.enable_cycles is True
        assert runtime.enable_async is True
        assert runtime.local_runtime is not None
        assert hasattr(runtime, "cyclic_executor")

    def test_custom_initialization(self):
        """Test ParallelCyclicRuntime with custom configuration."""
        runtime = ParallelCyclicRuntime(
            debug=True, max_workers=8, enable_cycles=False, enable_async=False
        )

        assert runtime.debug is True
        assert runtime.max_workers == 8
        assert runtime.enable_cycles is False
        assert runtime.enable_async is False
        assert runtime.local_runtime is not None
        assert not hasattr(runtime, "cyclic_executor")

    def test_logging_configuration(self):
        """Test logging configuration."""
        # Test debug mode
        runtime_debug = ParallelCyclicRuntime(debug=True)
        assert runtime_debug.logger.level == logging.DEBUG

        # Test normal mode
        runtime_normal = ParallelCyclicRuntime(debug=False)
        assert runtime_normal.logger.level == logging.INFO


class TestParallelCyclicRuntimeExecution:
    """Test workflow execution functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.runtime = ParallelCyclicRuntime(debug=True, max_workers=2)
        self.workflow = MockWorkflow("test_workflow")

        # Create simple workflow with multiple nodes
        self.node1 = MockNode("node1", return_value={"output1": "data1"})
        self.node2 = MockNode("node2", return_value={"output2": "data2"})
        self.node3 = MockNode("node3", return_value={"output3": "data3"})

        self.workflow._node_instances = {
            "node1": self.node1,
            "node2": self.node2,
            "node3": self.node3,
        }

    def test_execute_no_workflow(self):
        """Test execution with no workflow provided."""
        with pytest.raises(RuntimeExecutionError, match="No workflow provided"):
            self.runtime.execute(None)

    def test_execute_workflow_validation_error(self):
        """Test execution with workflow validation error."""
        from kailash.sdk_exceptions import WorkflowValidationError

        self.workflow.set_validation_error(WorkflowValidationError("Invalid workflow"))

        with pytest.raises(
            RuntimeExecutionError, match="Parallel runtime execution failed"
        ):
            self.runtime.execute(self.workflow)

    @patch("kailash.runtime.parallel_cyclic.CyclicWorkflowExecutor")
    def test_execute_cyclic_workflow(self, mock_cyclic_executor_class):
        """Test execution of cyclic workflow."""
        # Set up cyclic workflow
        self.workflow._has_cycles = True

        # Mock cyclic executor
        mock_executor = Mock()
        mock_executor.execute.return_value = ({}, "cycle_run_123")
        mock_cyclic_executor_class.return_value = mock_executor
        self.runtime.cyclic_executor = mock_executor

        results, run_id = self.runtime.execute(self.workflow)

        assert results == {}
        assert run_id == "cycle_run_123"
        mock_executor.execute.assert_called_once()

    @patch("kailash.runtime.parallel_cyclic.CyclicWorkflowExecutor")
    def test_execute_cyclic_workflow_failure(self, mock_cyclic_executor_class):
        """Test execution of cyclic workflow that fails."""
        # Set up cyclic workflow
        self.workflow._has_cycles = True

        # Mock cyclic executor that fails
        mock_executor = Mock()
        mock_executor.execute.side_effect = RuntimeError("Cyclic execution failed")
        mock_cyclic_executor_class.return_value = mock_executor
        self.runtime.cyclic_executor = mock_executor

        with pytest.raises(
            RuntimeExecutionError, match="Cyclic workflow execution failed"
        ):
            self.runtime.execute(self.workflow)

    @patch("kailash.runtime.local.LocalRuntime")
    def test_execute_fallback_to_local_runtime(self, mock_local_runtime_class):
        """Test fallback to local runtime when no parallel opportunities."""
        # Mock local runtime
        mock_local_runtime = Mock()
        mock_local_runtime.execute.return_value = (
            {"node1": {"result": "success"}},
            "run_123",
        )
        mock_local_runtime_class.return_value = mock_local_runtime
        self.runtime.local_runtime = mock_local_runtime

        # Create single node workflow (no parallel opportunities)
        simple_workflow = MockWorkflow("simple_workflow")
        simple_workflow._node_instances = {"node1": self.node1}
        simple_workflow.graph.add_node("node1")

        results, run_id = self.runtime.execute(simple_workflow)

        assert results == {"node1": {"result": "success"}}
        assert run_id == "run_123"
        mock_local_runtime.execute.assert_called_once()


class TestParallelCyclicRuntimeParallelExecution:
    """Test parallel execution functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.runtime = ParallelCyclicRuntime(debug=True, max_workers=2)
        self.workflow = MockWorkflow("parallel_workflow")

        # Create workflow with parallel opportunities
        self.node1 = MockNode("node1", return_value={"output1": "data1"})
        self.node2 = MockNode("node2", return_value={"output2": "data2"})
        self.node3 = MockNode("node3", return_value={"output3": "data3"})

        self.workflow._node_instances = {
            "node1": self.node1,
            "node2": self.node2,
            "node3": self.node3,
        }

        # Set up graph with parallel nodes
        self.workflow.graph.add_node("node1")
        self.workflow.graph.add_node("node2")
        self.workflow.graph.add_node("node3")
        # node1 and node2 can run in parallel, node3 depends on both
        self.workflow.graph.add_edge("node1", "node3", mapping={"output1": "input1"})
        self.workflow.graph.add_edge("node2", "node3", mapping={"output2": "input2"})

    @patch("networkx.topological_sort")
    @patch("kailash.runtime.parallel_cyclic.ThreadPoolExecutor")
    def test_execute_parallel_dag_success(self, mock_executor_class, mock_topo):
        """Test successful parallel DAG execution."""
        mock_topo.return_value = ["node1", "node2", "node3"]

        # Mock ThreadPoolExecutor
        mock_executor = Mock()
        mock_executor_class.return_value.__enter__ = Mock(return_value=mock_executor)
        mock_executor_class.return_value.__exit__ = Mock(return_value=None)

        # Mock futures for parallel execution
        future1 = Mock(spec=Future)
        future1.result.return_value = {"output1": "data1"}
        future2 = Mock(spec=Future)
        future2.result.return_value = {"output2": "data2"}
        future3 = Mock(spec=Future)
        future3.result.return_value = {"output3": "data3"}

        mock_executor.submit.side_effect = [future1, future2, future3]

        # Mock as_completed to return futures in groups
        with patch("kailash.runtime.parallel_cyclic.as_completed") as mock_as_completed:
            mock_as_completed.side_effect = [
                [future1, future2],  # First group (parallel)
                [future3],  # Second group
            ]

            results, run_id = self.runtime.execute(self.workflow)

            assert "node1" in results
            assert "node2" in results
            assert "node3" in results
            assert run_id is not None

    def test_analyze_parallel_groups_simple(self):
        """Test analysis of parallel groups in a simple workflow."""
        # Create a fresh workflow for this test
        simple_workflow = MockWorkflow("simple_workflow")
        simple_workflow.graph.add_node("node1")
        simple_workflow.graph.add_node("node2")

        groups = self.runtime._analyze_parallel_groups(simple_workflow, None)

        # Both nodes should be in the same parallel group
        assert len(groups) == 1
        assert set(groups[0]) == {"node1", "node2"}

    def test_analyze_parallel_groups_sequential(self):
        """Test analysis of sequential workflow."""
        # Create a fresh workflow for this test
        sequential_workflow = MockWorkflow("sequential_workflow")
        sequential_workflow.graph.add_node("node1")
        sequential_workflow.graph.add_node("node2")
        sequential_workflow.graph.add_edge("node1", "node2")

        groups = self.runtime._analyze_parallel_groups(sequential_workflow, None)

        # Should have two sequential groups
        assert len(groups) == 2
        assert groups[0] == ["node1"]
        assert groups[1] == ["node2"]

    def test_analyze_parallel_groups_with_hint(self):
        """Test analysis with parallel nodes hint."""
        # Create a fresh workflow for this test
        hint_workflow = MockWorkflow("hint_workflow")
        hint_workflow.graph.add_node("node1")
        hint_workflow.graph.add_node("node2")
        hint_workflow.graph.add_node("node3")

        # Only node1 and node2 should be parallelized
        parallel_hint = {"node1", "node2"}

        groups = self.runtime._analyze_parallel_groups(hint_workflow, parallel_hint)

        # Should have separate groups based on hint
        assert len(groups) >= 1
        # At least one group should contain the hinted parallel nodes
        parallel_nodes_found = set()
        for group in groups:
            parallel_nodes_found.update(node for node in group if node in parallel_hint)
        assert parallel_nodes_found == parallel_hint

    def test_can_execute_in_parallel_true(self):
        """Test detection of parallel execution opportunities."""
        # Create a fresh workflow with parallel nodes
        parallel_workflow = MockWorkflow("parallel_workflow")
        parallel_workflow.graph.add_node("node1")
        parallel_workflow.graph.add_node("node2")

        can_parallel = self.runtime._can_execute_in_parallel(parallel_workflow)

        assert can_parallel is True

    def test_can_execute_in_parallel_false(self):
        """Test detection when no parallel opportunities exist."""
        # Create a fresh sequential workflow
        sequential_workflow = MockWorkflow("sequential_workflow")
        sequential_workflow.graph.add_node("node1")
        sequential_workflow.graph.add_node("node2")
        sequential_workflow.graph.add_edge("node1", "node2")

        can_parallel = self.runtime._can_execute_in_parallel(sequential_workflow)

        assert can_parallel is False

    def test_can_execute_in_parallel_network_error(self):
        """Test handling of NetworkX errors."""
        # Mock NetworkX to raise an error
        with patch(
            "networkx.topological_sort", side_effect=nx.NetworkXError("Test error")
        ):
            can_parallel = self.runtime._can_execute_in_parallel(self.workflow)

            assert can_parallel is False


class TestParallelCyclicRuntimeNodeExecution:
    """Test individual node execution functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.runtime = ParallelCyclicRuntime(debug=True)
        self.workflow = MockWorkflow("test_workflow")
        self.node = MockNode("test_node", return_value={"result": "success"})
        self.workflow._node_instances = {"test_node": self.node}
        self.workflow.graph.add_node("test_node")

    def test_execute_single_node_success(self):
        """Test successful single node execution."""
        with patch(
            "kailash.tracking.metrics_collector.MetricsCollector"
        ) as mock_collector_class:
            mock_collector = Mock()
            mock_context = Mock()
            mock_context.result.return_value.duration = 0.1
            mock_context.result.return_value.to_task_metrics.return_value = {
                "execution_time": 0.1,
                "memory_usage": 100,
            }
            mock_collector.collect.return_value.__enter__ = Mock(
                return_value=mock_context
            )
            mock_collector.collect.return_value.__exit__ = Mock(return_value=None)
            mock_collector_class.return_value = mock_collector

            result = self.runtime._execute_single_node(
                self.workflow, "test_node", {}, {}, None, None
            )

            assert result == {"result": "success"}
            assert self.node.executed is True

    def test_execute_single_node_not_found(self):
        """Test execution when node is not found."""
        with pytest.raises(
            WorkflowExecutionError, match="Node instance 'missing_node' not found"
        ):
            self.runtime._execute_single_node(
                self.workflow, "missing_node", {}, {}, None, None
            )

    def test_execute_single_node_failure(self):
        """Test single node execution failure."""
        self.node.should_fail = True
        self.node.fail_message = "Test failure"

        with patch("kailash.tracking.metrics_collector.MetricsCollector"):
            with pytest.raises(
                WorkflowExecutionError, match="Node 'test_node' execution failed"
            ):
                self.runtime._execute_single_node(
                    self.workflow, "test_node", {}, {}, None, None
                )

    def test_execute_single_node_with_task_manager(self):
        """Test single node execution with task manager."""
        task_manager = Mock(spec=TaskManager)
        task_manager.create_task.return_value = Mock(task_id="task_123")

        with patch(
            "kailash.tracking.metrics_collector.MetricsCollector"
        ) as mock_collector_class:
            mock_collector = Mock()
            mock_context = Mock()
            mock_context.result.return_value.duration = 0.1
            mock_context.result.return_value.to_task_metrics.return_value = {
                "execution_time": 0.1,
                "memory_usage": 100,
            }
            mock_collector.collect.return_value.__enter__ = Mock(
                return_value=mock_context
            )
            mock_collector.collect.return_value.__exit__ = Mock(return_value=None)
            mock_collector_class.return_value = mock_collector

            result = self.runtime._execute_single_node(
                self.workflow, "test_node", {}, {}, task_manager, "run_123"
            )

            assert result == {"result": "success"}
            task_manager.create_task.assert_called_once()
            task_manager.update_task_status.assert_called()


class TestParallelCyclicRuntimeInputPreparation:
    """Test node input preparation functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.runtime = ParallelCyclicRuntime()
        self.workflow = MockWorkflow("test_workflow")

        # Create connected nodes
        self.node1 = MockNode("node1")
        self.node2 = MockNode("node2")

        self.workflow._node_instances = {"node1": self.node1, "node2": self.node2}

        self.workflow.graph.add_node("node1")
        self.workflow.graph.add_node("node2")
        self.workflow.graph.add_edge("node1", "node2", mapping={"output": "input_data"})

    def test_prepare_node_inputs_basic(self):
        """Test basic input preparation."""
        # Set node config
        self.node2.config = {"default_param": "default_value"}

        inputs = self.runtime._prepare_node_inputs_parallel(
            self.workflow, "node2", self.node2, {}, {"override_param": "override_value"}
        )

        assert inputs["default_param"] == "default_value"
        assert inputs["override_param"] == "override_value"

    def test_prepare_node_inputs_with_connections(self):
        """Test input preparation with node connections."""
        # Set node config
        self.node2.config = {}

        # Previous results from node1
        previous_results = {"node1": {"output": "upstream_data"}}

        inputs = self.runtime._prepare_node_inputs_parallel(
            self.workflow, "node2", self.node2, previous_results, {}
        )

        assert inputs["input_data"] == "upstream_data"

    def test_prepare_node_inputs_failed_source_node(self):
        """Test input preparation when source node failed."""
        # Previous results with failed node
        previous_results = {"node1": {"failed": True, "error": "Node failed"}}

        with pytest.raises(
            WorkflowExecutionError, match="Cannot use outputs from failed node"
        ):
            self.runtime._prepare_node_inputs_parallel(
                self.workflow, "node2", self.node2, previous_results, {}
            )


class TestParallelCyclicRuntimeErrorHandling:
    """Test error handling functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.runtime = ParallelCyclicRuntime()
        self.workflow = MockWorkflow("test_workflow")

    def test_should_stop_on_group_error_with_dependents(self):
        """Test error handling when node has dependents."""
        # Set up workflow with dependent nodes
        self.workflow.graph.add_node("node1")
        self.workflow.graph.add_node("node2")
        self.workflow.graph.add_edge("node1", "node2")

        should_stop = self.runtime._should_stop_on_group_error(
            self.workflow, "node1", ["node1", "other_node"]
        )

        assert should_stop is True

    def test_should_stop_on_group_error_without_dependents(self):
        """Test error handling when node has no dependents."""
        # Set up workflow with isolated node
        self.workflow.graph.add_node("isolated_node")

        should_stop = self.runtime._should_stop_on_group_error(
            self.workflow, "isolated_node", ["isolated_node"]
        )

        assert should_stop is False


class TestParallelCyclicRuntimeIntegration:
    """Test integration scenarios."""

    def setup_method(self):
        """Set up test fixtures."""
        self.runtime = ParallelCyclicRuntime(debug=True, max_workers=2)

    def test_end_to_end_parallel_execution(self):
        """Test complete parallel execution flow."""
        # Create workflow with parallel opportunities
        workflow = MockWorkflow("integration_test")

        # Create nodes with slight delays to test parallel execution
        node1 = MockNode(
            "node1", return_value={"data": "from_node1"}, execution_delay=0.01
        )
        node2 = MockNode(
            "node2", return_value={"data": "from_node2"}, execution_delay=0.01
        )
        node3 = MockNode("node3", return_value={"final": "result"})

        workflow._node_instances = {"node1": node1, "node2": node2, "node3": node3}

        # Set up parallel structure
        workflow.graph.add_node("node1")
        workflow.graph.add_node("node2")
        workflow.graph.add_node("node3")
        workflow.graph.add_edge("node1", "node3", mapping={"data": "input1"})
        workflow.graph.add_edge("node2", "node3", mapping={"data": "input2"})

        with patch("networkx.topological_sort") as mock_topo:
            mock_topo.return_value = ["node1", "node2", "node3"]

            # Mock the complex parallel execution parts for unit test
            with patch.object(self.runtime, "_execute_parallel_dag") as mock_parallel:
                mock_parallel.return_value = (
                    {
                        "node1": {"data": "from_node1"},
                        "node2": {"data": "from_node2"},
                        "node3": {"final": "result"},
                    },
                    "run_integration_123",
                )

                results, run_id = self.runtime.execute(workflow)

                assert "node1" in results
                assert "node2" in results
                assert "node3" in results
                assert run_id == "run_integration_123"

                # Verify parallel execution was attempted
                mock_parallel.assert_called_once()

    def test_runtime_configuration_options(self):
        """Test different runtime configuration options."""
        # Test with cycles disabled
        runtime_no_cycles = ParallelCyclicRuntime(enable_cycles=False)
        assert runtime_no_cycles.enable_cycles is False
        assert not hasattr(runtime_no_cycles, "cyclic_executor")

        # Test with different worker counts
        runtime_many_workers = ParallelCyclicRuntime(max_workers=16)
        assert runtime_many_workers.max_workers == 16

        # Test debug configuration
        runtime_debug = ParallelCyclicRuntime(debug=True)
        assert runtime_debug.debug is True
        assert runtime_debug.logger.level == logging.DEBUG

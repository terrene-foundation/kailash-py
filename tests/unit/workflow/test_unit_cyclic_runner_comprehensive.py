"""Comprehensive tests for CyclicWorkflowExecutor to improve coverage.

This test file focuses on missing coverage areas in cyclic_runner.py:
- Main execute() method with different scenarios
- _execute_with_cycles() method
- _create_execution_plan() method
- _execute_plan() method
- _execute_cycle_group() method
- _execute_node() method with cyclic context
- ExecutionPlan, ExecutionStage, and CycleGroup classes
- Error handling and edge cases
"""

import logging
import uuid
from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock, Mock, patch

import networkx as nx
import pytest
from kailash.nodes.base import Node, NodeParameter
from kailash.sdk_exceptions import WorkflowExecutionError, WorkflowValidationError
from kailash.tracking import TaskManager, TaskStatus
from kailash.workflow.convergence import ConvergenceCondition
from kailash.workflow.cycle_state import CycleState, CycleStateManager
from kailash.workflow.cyclic_runner import (
    CycleGroup,
    CyclicWorkflowExecutor,
    ExecutionPlan,
    ExecutionStage,
    WorkflowState,
)
from kailash.workflow.graph import Workflow
from kailash.workflow.safety import CycleSafetyManager


class MockNode(Node):
    """Mock node for testing."""

    def __init__(self, node_id="mock_node", **kwargs):
        super().__init__()
        self.node_id = node_id
        self.config = kwargs
        self.executed = False
        self.execution_count = 0
        self.return_value = kwargs.get("return_value", {"result": "success"})
        self.should_fail = kwargs.get("should_fail", False)

    def get_parameters(self):
        return {
            "input_data": NodeParameter(
                name="input_data", type=str, required=False, description="Input data"
            )
        }

    def execute(self, **inputs):
        self.executed = True
        self.execution_count += 1
        self.last_inputs = inputs

        if self.should_fail:
            raise RuntimeError("Mock node failure")

        return self.return_value


class TestCyclicWorkflowExecutorBasic:
    """Test basic CyclicWorkflowExecutor functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.safety_manager = Mock(spec=CycleSafetyManager)
        self.executor = CyclicWorkflowExecutor(self.safety_manager)

        # Create a mock workflow
        self.workflow = Mock(spec=Workflow)
        self.workflow.workflow_id = "test_workflow"
        self.workflow.name = "Test Workflow"

    def test_init_default_safety_manager(self):
        """Test initialization with default safety manager."""
        executor = CyclicWorkflowExecutor()

        assert executor.safety_manager is not None
        assert isinstance(executor.safety_manager, CycleSafetyManager)
        assert isinstance(executor.cycle_state_manager, CycleStateManager)

    def test_init_custom_safety_manager(self):
        """Test initialization with custom safety manager."""
        custom_safety = Mock(spec=CycleSafetyManager)
        executor = CyclicWorkflowExecutor(custom_safety)

        assert executor.safety_manager is custom_safety

    def test_execute_validation_error(self):
        """Test execute method with validation error."""
        self.workflow.validate.side_effect = WorkflowValidationError("Invalid workflow")

        with pytest.raises(WorkflowValidationError, match="Invalid workflow"):
            self.executor.execute(self.workflow)

    def test_execute_no_cycles_delegates_to_dag_runner(self):
        """Test execute method with no cycles delegates to DAG runner."""
        self.workflow.validate.return_value = None
        self.workflow.has_cycles.return_value = False

        with patch.object(self.executor.dag_runner, "execute") as mock_execute:
            mock_execute.return_value = {"result": "dag_success"}

            results, run_id = self.executor.execute(self.workflow)

            assert results == {"result": "dag_success"}
            assert run_id is not None
            # Should delegate to DAG runner
            mock_execute.assert_called_once_with(self.workflow, None)

    def test_execute_with_cycles_generates_run_id(self):
        """Test execute method with cycles generates run ID."""
        self.workflow.validate.return_value = None
        self.workflow.has_cycles.return_value = True

        with patch.object(self.executor, "_execute_with_cycles") as mock_execute:
            mock_execute.return_value = {"result": "success"}

            results, run_id = self.executor.execute(self.workflow)

            assert results == {"result": "success"}
            assert run_id is not None
            # Should generate a UUID
            try:
                uuid.UUID(run_id)
            except ValueError:
                pytest.fail("run_id should be a valid UUID")

    def test_execute_with_custom_run_id(self):
        """Test execute method with custom run ID."""
        self.workflow.validate.return_value = None
        self.workflow.has_cycles.return_value = True
        custom_run_id = "custom_run_123"

        with patch.object(self.executor, "_execute_with_cycles") as mock_execute:
            mock_execute.return_value = {"result": "success"}

            results, run_id = self.executor.execute(self.workflow, run_id=custom_run_id)

            assert run_id == custom_run_id

    def test_execute_with_cycles_handles_exception(self):
        """Test execute method handles exceptions during cycle execution."""
        self.workflow.validate.return_value = None
        self.workflow.has_cycles.return_value = True

        with patch.object(self.executor, "_execute_with_cycles") as mock_execute:
            mock_execute.side_effect = RuntimeError("Execution failed")

            with pytest.raises(WorkflowExecutionError, match="Execution failed"):
                self.executor.execute(self.workflow)

    def test_execute_with_cycles_cleans_up_state(self):
        """Test execute method cleans up cycle state after execution."""
        self.workflow.validate.return_value = None
        self.workflow.has_cycles.return_value = True

        # Mock the clear method
        with patch.object(self.executor.cycle_state_manager, "clear") as mock_clear:
            with patch.object(self.executor, "_execute_with_cycles") as mock_execute:
                mock_execute.return_value = {"result": "success"}

                self.executor.execute(self.workflow)

                # Should clean up cycle state
                mock_clear.assert_called_once()

    def test_execute_with_cycles_cleans_up_state_on_exception(self):
        """Test execute method cleans up cycle state even when exception occurs."""
        self.workflow.validate.return_value = None
        self.workflow.has_cycles.return_value = True

        # Mock the clear method
        with patch.object(self.executor.cycle_state_manager, "clear") as mock_clear:
            with patch.object(self.executor, "_execute_with_cycles") as mock_execute:
                mock_execute.side_effect = RuntimeError("Execution failed")

                with pytest.raises(WorkflowExecutionError):
                    self.executor.execute(self.workflow)

                # Should still clean up cycle state
                mock_clear.assert_called_once()


class TestCyclicWorkflowExecutorInternalMethods:
    """Test internal methods of CyclicWorkflowExecutor."""

    def setup_method(self):
        """Set up test fixtures."""
        self.executor = CyclicWorkflowExecutor()

        # Create a mock workflow
        self.workflow = Mock(spec=Workflow)
        self.workflow.workflow_id = "test_workflow"
        self.workflow.name = "Test Workflow"

        # Create a mock graph
        self.graph = Mock(spec=nx.DiGraph)
        self.workflow.graph = self.graph

    def test_filter_none_values_dict(self):
        """Test _filter_none_values method with dictionary."""
        input_dict = {
            "key1": "value1",
            "key2": None,
            "key3": {"nested_key1": "nested_value1", "nested_key2": None},
        }

        result = self.executor._filter_none_values(input_dict)

        expected = {"key1": "value1", "key3": {"nested_key1": "nested_value1"}}
        assert result == expected

    def test_filter_none_values_list(self):
        """Test _filter_none_values method with list."""
        input_list = ["value1", None, "value2", {"key": None, "key2": "value"}]

        result = self.executor._filter_none_values(input_list)

        expected = ["value1", "value2", {"key2": "value"}]
        assert result == expected

    def test_filter_none_values_primitive(self):
        """Test _filter_none_values method with primitive values."""
        assert self.executor._filter_none_values("string") == "string"
        assert self.executor._filter_none_values(123) == 123
        assert self.executor._filter_none_values(True) is True
        assert self.executor._filter_none_values(None) is None

    def test_execute_with_cycles_basic_flow(self):
        """Test _execute_with_cycles method basic flow."""
        # Setup mocks
        self.workflow.separate_dag_and_cycle_edges.return_value = ([], [])
        self.workflow.get_cycle_groups.return_value = {}

        with patch.object(self.executor, "_create_execution_plan") as mock_create_plan:
            mock_plan = Mock()
            mock_create_plan.return_value = mock_plan

            with patch.object(self.executor, "_execute_plan") as mock_execute_plan:
                mock_execute_plan.return_value = {"result": "success"}

                result = self.executor._execute_with_cycles(
                    self.workflow, {"param": "value"}, "test_run"
                )

                assert result == {"result": "success"}
                mock_create_plan.assert_called_once()
                mock_execute_plan.assert_called_once()

    def test_execute_with_cycles_with_summaries(self):
        """Test _execute_with_cycles logs cycle summaries."""
        # Setup mocks
        self.workflow.separate_dag_and_cycle_edges.return_value = ([], [])
        self.workflow.get_cycle_groups.return_value = {}

        # Mock cycle state manager to return summaries
        mock_summaries = {
            "cycle1": {"iterations": 5, "converged": True},
            "cycle2": {"iterations": 3, "converged": False},
        }

        with patch.object(
            self.executor.cycle_state_manager, "get_all_summaries"
        ) as mock_get_summaries:
            mock_get_summaries.return_value = mock_summaries

            with patch.object(
                self.executor, "_create_execution_plan"
            ) as mock_create_plan:
                mock_plan = Mock()
                mock_create_plan.return_value = mock_plan

                with patch.object(self.executor, "_execute_plan") as mock_execute_plan:
                    mock_execute_plan.return_value = {"result": "success"}

                    with patch("kailash.workflow.cyclic_runner.logger") as mock_logger:
                        result = self.executor._execute_with_cycles(
                            self.workflow, {"param": "value"}, "test_run"
                        )

                        # Should log summaries
                        mock_logger.info.assert_any_call(
                            "Cycle cycle1 summary: {'iterations': 5, 'converged': True}"
                        )
                        mock_logger.info.assert_any_call(
                            "Cycle cycle2 summary: {'iterations': 3, 'converged': False}"
                        )


class TestExecutionPlan:
    """Test ExecutionPlan class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.plan = ExecutionPlan()

    def test_init(self):
        """Test ExecutionPlan initialization."""
        assert self.plan.stages == []
        assert self.plan.cycle_groups == {}

    def test_add_cycle_group(self):
        """Test adding a cycle group."""
        nodes = {"node1", "node2"}
        entry_nodes = {"node1"}
        exit_nodes = {"node2"}
        edges = [("node1", "node2", {})]

        self.plan.add_cycle_group(
            cycle_id="cycle1",
            nodes=nodes,
            entry_nodes=entry_nodes,
            exit_nodes=exit_nodes,
            edges=edges,
        )

        assert "cycle1" in self.plan.cycle_groups
        cycle_group = self.plan.cycle_groups["cycle1"]
        assert cycle_group.cycle_id == "cycle1"
        assert cycle_group.nodes == nodes
        assert cycle_group.entry_nodes == entry_nodes
        assert cycle_group.exit_nodes == exit_nodes
        assert cycle_group.edges == edges

    def test_build_stages_dag_only(self):
        """Test build_stages with DAG nodes only."""
        # Create mock workflow and dag_graph
        workflow = Mock(spec=Workflow)
        dag_graph = Mock(spec=nx.DiGraph)

        topo_order = ["node1", "node2", "node3"]

        self.plan.build_stages(topo_order, dag_graph, workflow)

        # Should create 3 DAG stages
        assert len(self.plan.stages) == 3
        for i, stage in enumerate(self.plan.stages):
            assert not stage.is_cycle
            assert stage.nodes == [topo_order[i]]

    def test_build_stages_with_cycles(self):
        """Test build_stages with cycle groups."""
        # Add a cycle group
        cycle_nodes = {"cycle_node1", "cycle_node2"}
        self.plan.add_cycle_group(
            cycle_id="cycle1",
            nodes=cycle_nodes,
            entry_nodes={"cycle_node1"},
            exit_nodes={"cycle_node2"},
            edges=[("cycle_node1", "cycle_node2", {})],
        )

        # Mock workflow graph
        workflow = Mock(spec=Workflow)
        workflow.graph = Mock(spec=nx.DiGraph)
        workflow.graph.predecessors.return_value = []
        workflow.graph.successors.return_value = []

        dag_graph = Mock(spec=nx.DiGraph)

        topo_order = ["dag_node1", "cycle_node1", "dag_node2"]

        self.plan.build_stages(topo_order, dag_graph, workflow)

        # Should create stages for DAG nodes and cycle group
        assert len(self.plan.stages) > 0

        # Check that cycle group was scheduled
        cycle_stages = [s for s in self.plan.stages if s.is_cycle]
        assert len(cycle_stages) == 1
        assert cycle_stages[0].cycle_group.cycle_id == "cycle1"


class TestExecutionStage:
    """Test ExecutionStage class."""

    def test_init_dag_stage(self):
        """Test ExecutionStage initialization for DAG stage."""
        nodes = ["node1", "node2"]
        stage = ExecutionStage(is_cycle=False, nodes=nodes)

        assert not stage.is_cycle
        assert stage.nodes == nodes
        assert stage.cycle_group is None

    def test_init_cycle_stage(self):
        """Test ExecutionStage initialization for cycle stage."""
        cycle_group = Mock(spec=CycleGroup)
        stage = ExecutionStage(is_cycle=True, cycle_group=cycle_group)

        assert stage.is_cycle
        assert stage.nodes == []
        assert stage.cycle_group is cycle_group

    def test_init_defaults(self):
        """Test ExecutionStage initialization with defaults."""
        stage = ExecutionStage(is_cycle=False)

        assert not stage.is_cycle
        assert stage.nodes == []
        assert stage.cycle_group is None


class TestCycleGroup:
    """Test CycleGroup class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.cycle_group = CycleGroup(
            cycle_id="test_cycle",
            nodes={"node1", "node2", "node3"},
            entry_nodes={"node1"},
            exit_nodes={"node3"},
            edges=[("node1", "node2", {}), ("node2", "node3", {})],
        )

    def test_init(self):
        """Test CycleGroup initialization."""
        assert self.cycle_group.cycle_id == "test_cycle"
        assert self.cycle_group.nodes == {"node1", "node2", "node3"}
        assert self.cycle_group.entry_nodes == {"node1"}
        assert self.cycle_group.exit_nodes == {"node3"}
        assert len(self.cycle_group.edges) == 2

    def test_get_execution_order_topological_sort(self):
        """Test get_execution_order with successful topological sort."""
        # Create a mock graph
        full_graph = Mock(spec=nx.DiGraph)
        subgraph = Mock(spec=nx.DiGraph)
        subgraph.copy.return_value = subgraph
        subgraph.has_edge.return_value = True
        # Mock edges method to return empty list (no cycle edges to remove)
        subgraph.edges.return_value = []
        subgraph.remove_edge = Mock()
        full_graph.subgraph.return_value = subgraph

        # Mock nx.topological_sort to succeed
        with patch("kailash.workflow.cyclic_runner.nx.topological_sort") as mock_topo:
            mock_topo.return_value = ["node1", "node2", "node3"]

            order = self.cycle_group.get_execution_order(full_graph)

            assert order == ["node1", "node2", "node3"]

    def test_get_execution_order_fallback(self):
        """Test get_execution_order with fallback when topological sort fails."""
        # Create a mock graph
        full_graph = Mock(spec=nx.DiGraph)
        subgraph = Mock(spec=nx.DiGraph)
        subgraph.copy.return_value = subgraph
        subgraph.has_edge.return_value = True
        # Mock edges method to return empty list
        subgraph.edges.return_value = []
        subgraph.remove_edge = Mock()
        full_graph.subgraph.return_value = subgraph

        # Mock nx.topological_sort to fail
        with patch("kailash.workflow.cyclic_runner.nx.topological_sort") as mock_topo:
            mock_topo.side_effect = nx.NetworkXUnfeasible("No topological sort")

            order = self.cycle_group.get_execution_order(full_graph)

            # Should fall back to entry nodes first, then others
            assert order[0] == "node1"  # Entry node should be first
            assert len(order) == 3
            assert all(node in order for node in ["node1", "node2", "node3"])


class TestWorkflowState:
    """Test WorkflowState class."""

    def test_init(self):
        """Test WorkflowState initialization."""
        state = WorkflowState("test_run_123")

        assert state.run_id == "test_run_123"
        assert state.node_outputs == {}
        assert state.execution_order == []
        assert state.metadata == {}


class TestCyclicWorkflowExecutorAdvanced:
    """Test advanced CyclicWorkflowExecutor functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.executor = CyclicWorkflowExecutor()

        # Create a mock workflow
        self.workflow = Mock(spec=Workflow)
        self.workflow.workflow_id = "test_workflow"
        self.workflow.name = "Test Workflow"
        self.workflow.graph = Mock(spec=nx.DiGraph)

    def test_create_execution_plan_with_dag_only(self):
        """Test _create_execution_plan with DAG edges only."""
        dag_edges = [("node1", "node2", {}), ("node2", "node3", {})]
        cycle_groups = {}

        # Mock networkx functions
        with patch("kailash.workflow.cyclic_runner.nx.DiGraph") as mock_digraph:
            mock_graph = Mock()
            mock_digraph.return_value = mock_graph

            with patch(
                "kailash.workflow.cyclic_runner.nx.topological_sort"
            ) as mock_topo:
                mock_topo.return_value = ["node1", "node2", "node3"]

                plan = self.executor._create_execution_plan(
                    self.workflow, dag_edges, cycle_groups
                )

                assert isinstance(plan, ExecutionPlan)
                mock_graph.add_nodes_from.assert_called_once()
                mock_graph.add_edge.assert_called()

    def test_create_execution_plan_with_cycles(self):
        """Test _create_execution_plan with cycle groups."""
        dag_edges = [("node1", "node2", {})]
        cycle_groups = {"cycle1": [("node2", "node3", {}), ("node3", "node2", {})]}

        # Mock workflow graph methods
        self.workflow.graph.predecessors.return_value = []
        self.workflow.graph.successors.return_value = []

        with patch("kailash.workflow.cyclic_runner.nx.DiGraph") as mock_digraph:
            mock_graph = Mock()
            mock_digraph.return_value = mock_graph

            with patch(
                "kailash.workflow.cyclic_runner.nx.topological_sort"
            ) as mock_topo:
                mock_topo.return_value = ["node1", "node2", "node3"]

                plan = self.executor._create_execution_plan(
                    self.workflow, dag_edges, cycle_groups
                )

                assert isinstance(plan, ExecutionPlan)
                assert "cycle1" in plan.cycle_groups

    def test_create_execution_plan_networkx_unfeasible(self):
        """Test _create_execution_plan when NetworkX detects cycles."""
        dag_edges = [("node1", "node2", {}), ("node2", "node1", {})]  # Cycle in DAG
        cycle_groups = {}

        with patch("kailash.workflow.cyclic_runner.nx.DiGraph") as mock_digraph:
            mock_graph = Mock()
            mock_digraph.return_value = mock_graph

            with patch(
                "kailash.workflow.cyclic_runner.nx.topological_sort"
            ) as mock_topo:
                mock_topo.side_effect = nx.NetworkXUnfeasible("Cycle detected")

                with pytest.raises(
                    WorkflowValidationError,
                    match="DAG portion contains unmarked cycles",
                ):
                    self.executor._create_execution_plan(
                        self.workflow, dag_edges, cycle_groups
                    )

    def test_execute_plan_with_dag_stages(self):
        """Test _execute_plan with DAG stages."""
        # Create execution plan with DAG stages
        plan = ExecutionPlan()
        plan.stages = [
            ExecutionStage(is_cycle=False, nodes=["node1"]),
            ExecutionStage(is_cycle=False, nodes=["node2"]),
        ]

        state = WorkflowState("test_run")

        with patch.object(self.executor, "_execute_dag_portion") as mock_execute_dag:
            mock_execute_dag.return_value = {"node1": {"result": "success"}}

            results = self.executor._execute_plan(self.workflow, plan, state)

            assert results == {"node1": {"result": "success"}}
            assert mock_execute_dag.call_count == 2

    def test_execute_plan_with_cycle_stages(self):
        """Test _execute_plan with cycle stages."""
        # Create execution plan with cycle stage
        cycle_group = Mock(spec=CycleGroup)
        cycle_group.cycle_id = "cycle1"

        plan = ExecutionPlan()
        plan.stages = [ExecutionStage(is_cycle=True, cycle_group=cycle_group)]

        state = WorkflowState("test_run")

        with patch.object(self.executor, "_execute_cycle_group") as mock_execute_cycle:
            mock_execute_cycle.return_value = ({"cycle_result": "success"}, None)

            results = self.executor._execute_plan(self.workflow, plan, state)

            assert results == {"cycle_result": "success"}
            mock_execute_cycle.assert_called_once_with(
                self.workflow, cycle_group, state, None
            )

    def test_execute_plan_mixed_stages(self):
        """Test _execute_plan with mixed DAG and cycle stages."""
        cycle_group = Mock(spec=CycleGroup)
        cycle_group.cycle_id = "cycle1"

        plan = ExecutionPlan()
        plan.stages = [
            ExecutionStage(is_cycle=False, nodes=["node1"]),
            ExecutionStage(is_cycle=True, cycle_group=cycle_group),
            ExecutionStage(is_cycle=False, nodes=["node2"]),
        ]

        state = WorkflowState("test_run")

        with patch.object(self.executor, "_execute_dag_portion") as mock_execute_dag:
            mock_execute_dag.return_value = {"dag_result": "success"}

            with patch.object(
                self.executor, "_execute_cycle_group"
            ) as mock_execute_cycle:
                mock_execute_cycle.return_value = ({"cycle_result": "success"}, None)

                results = self.executor._execute_plan(self.workflow, plan, state)

                expected = {"dag_result": "success", "cycle_result": "success"}
                assert results == expected
                assert mock_execute_dag.call_count == 2
                assert mock_execute_cycle.call_count == 1

    def test_propagate_parameters_basic(self):
        """Test _propagate_parameters method basic functionality."""
        current_params = {"param1": "value1", "param2": "value2"}
        current_results = {"result1": "output1", "result2": "output2"}

        result = self.executor._propagate_parameters(current_params, current_results)

        # Should copy results for next iteration
        assert result["result1"] == "output1"
        assert result["result2"] == "output2"

        # Should preserve params not in results
        assert result["param1"] == "value1"
        assert result["param2"] == "value2"

    def test_propagate_parameters_with_mappings(self):
        """Test _propagate_parameters with cycle configuration mappings."""
        current_params = {"param1": "value1"}
        current_results = {"node_output": "output_value"}
        cycle_config = {"parameter_mappings": {"node_output": "next_param"}}

        result = self.executor._propagate_parameters(
            current_params, current_results, cycle_config
        )

        # Should apply mappings
        assert result["next_param"] == "output_value"
        assert result["node_output"] == "output_value"  # Original also kept
        assert result["param1"] == "value1"

    def test_propagate_parameters_filters_none(self):
        """Test _propagate_parameters filters None values."""
        current_params = {"param1": "value1", "param2": None}
        current_results = {"result1": "output1", "result2": None}

        result = self.executor._propagate_parameters(current_params, current_results)

        # Should filter out None values
        assert "param2" not in result
        assert "result2" not in result
        assert result["param1"] == "value1"
        assert result["result1"] == "output1"


class TestCyclicWorkflowExecutorNodeExecution:
    """Test node execution functionality in CyclicWorkflowExecutor."""

    def setup_method(self):
        """Set up test fixtures."""
        self.executor = CyclicWorkflowExecutor()

        # Create a mock workflow
        self.workflow = Mock(spec=Workflow)
        self.workflow.workflow_id = "test_workflow"
        self.workflow.name = "Test Workflow"
        self.workflow.graph = Mock(spec=nx.DiGraph)

        # Create a mock node
        self.mock_node = Mock(spec=MockNode)
        self.mock_node.config = {"config_param": "config_value"}
        self.mock_node.execute.return_value = {"result": "success"}
        self.workflow.get_node.return_value = self.mock_node

    def test_execute_node_not_found(self):
        """Test _execute_node when node is not found."""
        self.workflow.get_node.return_value = None

        state = WorkflowState("test_run")

        with pytest.raises(WorkflowExecutionError, match="Node not found: nonexistent"):
            self.executor._execute_node(self.workflow, "nonexistent", state)

    def test_execute_node_basic(self):
        """Test _execute_node basic functionality."""
        state = WorkflowState("test_run")

        # Mock graph connections
        self.workflow.graph.in_edges.return_value = []

        result = self.executor._execute_node(self.workflow, "node1", state)

        assert result == {"result": "success"}
        self.mock_node.execute.assert_called_once()

    def test_execute_node_with_inputs_from_connections(self):
        """Test _execute_node with inputs from connections."""
        state = WorkflowState("test_run")
        state.node_outputs["pred_node"] = {"output": "pred_value"}

        # Mock graph connections
        edge_data = {"mapping": {"output": "input_param"}}
        self.workflow.graph.in_edges.return_value = [("pred_node", "node1", edge_data)]

        result = self.executor._execute_node(self.workflow, "node1", state)

        # Should pass mapped input to node
        call_args = self.mock_node.execute.call_args
        assert "input_param" in call_args.kwargs
        assert call_args.kwargs["input_param"] == "pred_value"

    def test_execute_node_with_cycle_state(self):
        """Test _execute_node with cycle state."""
        state = WorkflowState("test_run")
        cycle_state = Mock(spec=CycleState)
        cycle_state.cycle_id = "test_cycle"
        cycle_state.iteration = 2
        cycle_state.elapsed_time = 10.5
        cycle_state.get_node_state.return_value = {"node_state": "value"}

        # Mock graph connections
        self.workflow.graph.in_edges.return_value = []

        result = self.executor._execute_node(
            self.workflow, "node1", state, cycle_state=cycle_state
        )

        # Should include cycle context
        call_args = self.mock_node.execute.call_args
        assert "context" in call_args.kwargs
        context = call_args.kwargs["context"]
        assert "cycle" in context
        assert context["cycle"]["cycle_id"] == "test_cycle"
        assert context["cycle"]["iteration"] == 2

    def test_execute_node_with_task_manager(self):
        """Test _execute_node with task manager."""
        state = WorkflowState("test_run")
        task_manager = Mock(spec=TaskManager)

        # Mock task creation
        mock_task = Mock()
        mock_task.task_id = "task_123"
        task_manager.create_task.return_value = mock_task

        # Mock graph connections
        self.workflow.graph.in_edges.return_value = []

        with patch(
            "kailash.workflow.cyclic_runner.MetricsCollector"
        ) as mock_collector_class:
            mock_collector = Mock()
            mock_collector_class.return_value = mock_collector

            # Mock metrics context manager properly
            mock_metrics_context = Mock()
            mock_metrics_result = Mock()
            mock_metrics_result.to_task_metrics.return_value = {}
            mock_metrics_context.result.return_value = mock_metrics_result

            # Create a proper context manager mock
            mock_collect_context = MagicMock()
            mock_collect_context.__enter__.return_value = mock_metrics_context
            mock_collect_context.__exit__.return_value = None
            mock_collector.collect.return_value = mock_collect_context

            result = self.executor._execute_node(
                self.workflow, "node1", state, task_manager=task_manager
            )

            # Should create and update task
            task_manager.create_task.assert_called_once()
            task_manager.update_task_status.assert_called()

    def test_execute_node_execution_failure(self):
        """Test _execute_node when node execution fails."""
        state = WorkflowState("test_run")

        # Mock node to fail
        self.mock_node.execute.side_effect = RuntimeError("Node execution failed")

        # Mock graph connections
        self.workflow.graph.in_edges.return_value = []

        with pytest.raises(RuntimeError, match="Node execution failed"):
            self.executor._execute_node(self.workflow, "node1", state)

    def test_execute_node_stores_cycle_state(self):
        """Test _execute_node stores cycle state from result."""
        state = WorkflowState("test_run")
        cycle_state = Mock(spec=CycleState)
        cycle_state.iteration = 1
        cycle_state.cycle_id = "test_cycle"
        cycle_state.elapsed_time = 5.0
        cycle_state.get_node_state.return_value = {}

        # Mock node to return cycle state
        self.mock_node.execute.return_value = {
            "result": "success",
            "_cycle_state": {"state_key": "state_value"},
        }

        # Mock graph connections
        self.workflow.graph.in_edges.return_value = []

        result = self.executor._execute_node(
            self.workflow, "node1", state, cycle_state=cycle_state
        )

        # Should store cycle state
        cycle_state.set_node_state.assert_called_once_with(
            "node1", {"state_key": "state_value"}
        )

    def test_execute_node_with_initial_parameters(self):
        """Test _execute_node with initial parameters."""
        state = WorkflowState("test_run")
        state.initial_parameters = {"node1": {"initial_param": "initial_value"}}

        # Mock graph connections
        self.workflow.graph.in_edges.return_value = []

        result = self.executor._execute_node(self.workflow, "node1", state)

        # Should include initial parameters
        call_args = self.mock_node.execute.call_args
        assert "initial_param" in call_args.kwargs
        assert call_args.kwargs["initial_param"] == "initial_value"

    def test_execute_node_with_cycle_edge_inputs(self):
        """Test _execute_node with cycle edge inputs."""
        state = WorkflowState("test_run")
        cycle_state = Mock(spec=CycleState)
        cycle_state.iteration = 2
        cycle_state.cycle_id = "test_cycle"
        cycle_state.elapsed_time = 10.0
        cycle_state.get_node_state.return_value = {}

        # Previous iteration results
        previous_iteration_results = {"pred_node": {"output": "prev_value"}}

        # Mock graph connections with cycle edge
        edge_data = {"mapping": {"output": "input_param"}, "cycle": True}
        self.workflow.graph.in_edges.return_value = [("pred_node", "node1", edge_data)]

        result = self.executor._execute_node(
            self.workflow,
            "node1",
            state,
            cycle_state=cycle_state,
            previous_iteration_results=previous_iteration_results,
        )

        # Should use previous iteration results for cycle edges
        call_args = self.mock_node.execute.call_args
        assert "input_param" in call_args.kwargs
        assert call_args.kwargs["input_param"] == "prev_value"

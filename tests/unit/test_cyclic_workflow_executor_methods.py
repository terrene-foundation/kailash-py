"""Comprehensive tests for CyclicWorkflowExecutor methods added in TODO-111."""

from datetime import UTC, datetime
from unittest.mock import MagicMock, Mock, patch

import pytest
from kailash.sdk_exceptions import WorkflowExecutionError
from kailash.tracking import TaskManager, TaskStatus
from kailash.workflow.cyclic_runner import (
    CycleGroup,
    CyclicWorkflowExecutor,
    WorkflowState,
)
from kailash.workflow.graph import Workflow


class TestExecuteDagPortion:
    """Test _execute_dag_portion method functionality."""

    def test_execute_single_dag_node(self):
        """Test executing a single DAG node."""
        # Setup
        executor = CyclicWorkflowExecutor()
        workflow = Mock(spec=Workflow)
        state = WorkflowState(run_id="test_run")

        # Mock _execute_node method
        with patch.object(executor, "_execute_node") as mock_execute:
            mock_execute.return_value = {"result": "success"}

            # Execute
            results = executor._execute_dag_portion(
                workflow=workflow, dag_nodes=["node1"], state=state, task_manager=None
            )

            # Verify
            assert "node1" in results
            assert results["node1"]["result"] == "success"
            assert "node1" in state.node_outputs
            mock_execute.assert_called_once_with(
                workflow, "node1", state, task_manager=None
            )

    def test_execute_multiple_dag_nodes(self):
        """Test executing multiple DAG nodes in sequence."""
        # Setup
        executor = CyclicWorkflowExecutor()
        workflow = Mock(spec=Workflow)
        state = WorkflowState(run_id="test_run")

        # Mock _execute_node to return different values for different nodes
        def execute_node_side_effect(wf, node_id, state, **kwargs):
            if node_id == "node1":
                return {"value": 10}
            elif node_id == "node2":
                return {"value": 20}
            return {}

        with patch.object(executor, "_execute_node") as mock_execute:
            mock_execute.side_effect = execute_node_side_effect

            # Execute
            results = executor._execute_dag_portion(
                workflow=workflow,
                dag_nodes=["node1", "node2"],
                state=state,
                task_manager=None,
            )

            # Verify
            assert len(results) == 2
            assert results["node1"]["value"] == 10
            assert results["node2"]["value"] == 20
            assert state.node_outputs["node1"]["value"] == 10
            assert state.node_outputs["node2"]["value"] == 20
            assert mock_execute.call_count == 2

    def test_skip_already_executed_nodes(self):
        """Test that already executed nodes are skipped."""
        # Setup
        executor = CyclicWorkflowExecutor()
        workflow = Mock(spec=Workflow)
        state = WorkflowState(run_id="test_run")

        # Pre-populate state with executed node
        state.node_outputs["node1"] = {"already": "executed"}

        # Mock _execute_node
        with patch.object(executor, "_execute_node") as mock_execute:
            mock_execute.return_value = {"result": "new"}

            # Execute
            results = executor._execute_dag_portion(
                workflow=workflow,
                dag_nodes=["node1", "node2"],
                state=state,
                task_manager=None,
            )

            # Verify - node1 should be skipped, only node2 executed
            assert len(results) == 1
            assert "node2" in results
            assert results["node2"]["result"] == "new"
            # _execute_node should only be called for node2
            mock_execute.assert_called_once_with(
                workflow, "node2", state, task_manager=None
            )
            # node1 should still have old value in state
            assert state.node_outputs["node1"]["already"] == "executed"

    def test_with_task_manager(self):
        """Test DAG execution with task manager tracking."""
        # Setup
        executor = CyclicWorkflowExecutor()
        workflow = Mock(spec=Workflow)
        state = WorkflowState(run_id="test_run")
        task_manager = Mock(spec=TaskManager)

        # Mock _execute_node
        with patch.object(executor, "_execute_node") as mock_execute:
            mock_execute.return_value = {"tracked": True}

            # Execute
            results = executor._execute_dag_portion(
                workflow=workflow,
                dag_nodes=["tracked_node"],
                state=state,
                task_manager=task_manager,
            )

            # Verify task manager was passed through
            assert results["tracked_node"]["tracked"] is True
            mock_execute.assert_called_once_with(
                workflow, "tracked_node", state, task_manager=task_manager
            )


class TestExecuteCycleGroups:
    """Test _execute_cycle_groups method functionality."""

    def test_execute_single_cycle_group(self):
        """Test executing a single cycle group."""
        # Setup
        executor = CyclicWorkflowExecutor()
        workflow = Mock(spec=Workflow)
        state = WorkflowState(run_id="test_run")

        # Create cycle group
        cycle_group = CycleGroup(
            cycle_id="cycle1",
            nodes={"node1", "node2"},
            entry_nodes={"node1"},
            exit_nodes={"node2"},
            edges=[("node2", "node1", {"cycle": True})],
        )

        # Mock _execute_cycle_group to return results tuple
        with patch.object(executor, "_execute_cycle_group") as mock_execute:
            mock_execute.return_value = (
                {"node1": {"iter": 1}, "node2": {"iter": 1}},
                None,
            )

            # Execute
            results = executor._execute_cycle_groups(
                workflow=workflow,
                cycle_groups=[cycle_group],
                state=state,
                task_manager=None,
            )

            # Verify
            assert len(results) == 2
            assert results["node1"]["iter"] == 1
            assert results["node2"]["iter"] == 1
            mock_execute.assert_called_once_with(workflow, cycle_group, state, None)

    def test_execute_multiple_cycle_groups(self):
        """Test executing multiple cycle groups."""
        # Setup
        executor = CyclicWorkflowExecutor()
        workflow = Mock(spec=Workflow)
        state = WorkflowState(run_id="test_run")

        # Create cycle groups
        cycle_group1 = CycleGroup(
            cycle_id="cycle1",
            nodes={"node1", "node2"},
            entry_nodes={"node1"},
            exit_nodes={"node2"},
            edges=[("node2", "node1", {"cycle": True})],
        )

        cycle_group2 = CycleGroup(
            cycle_id="cycle2",
            nodes={"node3", "node4"},
            entry_nodes={"node3"},
            exit_nodes={"node4"},
            edges=[("node4", "node3", {"cycle": True})],
        )

        # Mock _execute_cycle_group to return different results as tuples
        with patch.object(executor, "_execute_cycle_group") as mock_execute:
            mock_execute.side_effect = [
                ({"node1": {"cycle": 1}, "node2": {"cycle": 1}}, None),
                ({"node3": {"cycle": 2}, "node4": {"cycle": 2}}, None),
            ]

            # Execute
            results = executor._execute_cycle_groups(
                workflow=workflow,
                cycle_groups=[cycle_group1, cycle_group2],
                state=state,
                task_manager=None,
            )

            # Verify
            assert len(results) == 4
            assert results["node1"]["cycle"] == 1
            assert results["node3"]["cycle"] == 2
            assert mock_execute.call_count == 2

    def test_cycle_group_updates_state(self):
        """Test that cycle group execution updates workflow state."""
        # Setup
        executor = CyclicWorkflowExecutor()
        workflow = Mock(spec=Workflow)
        state = WorkflowState(run_id="test_run")

        # Create cycle group
        cycle_group = CycleGroup(
            cycle_id="cycle1",
            nodes={"node1"},
            entry_nodes={"node1"},
            exit_nodes={"node1"},
            edges=[],
        )

        # Mock _execute_cycle_group
        with patch.object(executor, "_execute_cycle_group") as mock_execute:
            mock_execute.return_value = ({"node1": {"final": "value"}}, None)

            # Execute
            executor._execute_cycle_groups(
                workflow=workflow,
                cycle_groups=[cycle_group],
                state=state,
                task_manager=None,
            )

            # Verify state was passed to cycle execution
            mock_execute.assert_called_once()
            call_args = mock_execute.call_args[0]
            assert call_args[2] is state  # state object passed


class TestPropagateParameters:
    """Test _propagate_parameters method functionality."""

    def test_basic_parameter_propagation(self):
        """Test basic parameter propagation from results."""
        # Setup
        executor = CyclicWorkflowExecutor()
        current_params = {"initial": "value"}
        current_results = {"output": "result", "data": 42}

        # Execute
        next_params = executor._propagate_parameters(
            current_params=current_params,
            current_results=current_results,
            cycle_config=None,
        )

        # Verify - results become next parameters
        assert next_params["output"] == "result"
        assert next_params["data"] == 42
        # Initial params preserved if not overridden
        assert next_params["initial"] == "value"

    def test_parameter_mapping(self):
        """Test parameter propagation with custom mappings."""
        # Setup
        executor = CyclicWorkflowExecutor()
        current_params = {"keep": "this"}
        current_results = {"source1": "value1", "source2": "value2"}
        cycle_config = {
            "parameter_mappings": {"source1": "target1", "source2": "target2"}
        }

        # Execute
        next_params = executor._propagate_parameters(
            current_params=current_params,
            current_results=current_results,
            cycle_config=cycle_config,
        )

        # Verify mappings applied
        assert next_params["target1"] == "value1"
        assert next_params["target2"] == "value2"
        # Original params preserved
        assert next_params["keep"] == "this"
        # Source keys also included (base propagation)
        assert next_params["source1"] == "value1"
        assert next_params["source2"] == "value2"

    def test_none_value_filtering(self):
        """Test that None values are filtered out."""
        # Setup
        executor = CyclicWorkflowExecutor()
        current_params = {"valid": "value"}
        current_results = {
            "good": "data",
            "bad": None,
            "nested": {"inner": None, "valid": "yes"},
        }

        # Execute
        next_params = executor._propagate_parameters(
            current_params=current_params,
            current_results=current_results,
            cycle_config=None,
        )

        # Verify None values filtered
        assert "good" in next_params
        assert "bad" not in next_params
        assert next_params["nested"]["valid"] == "yes"
        assert "inner" not in next_params["nested"]

    def test_empty_results(self):
        """Test propagation with empty results."""
        # Setup
        executor = CyclicWorkflowExecutor()
        current_params = {"param1": "value1", "param2": "value2"}
        current_results = {}

        # Execute
        next_params = executor._propagate_parameters(
            current_params=current_params,
            current_results=current_results,
            cycle_config=None,
        )

        # Verify all original params preserved
        assert next_params["param1"] == "value1"
        assert next_params["param2"] == "value2"
        assert len(next_params) == 2

    def test_override_behavior(self):
        """Test that results override initial parameters."""
        # Setup
        executor = CyclicWorkflowExecutor()
        current_params = {"key": "old_value", "other": "keep"}
        current_results = {"key": "new_value"}

        # Execute
        next_params = executor._propagate_parameters(
            current_params=current_params,
            current_results=current_results,
            cycle_config=None,
        )

        # Verify override
        assert next_params["key"] == "new_value"
        assert next_params["other"] == "keep"


class TestMethodIntegration:
    """Test integration between the new methods."""

    def test_filter_none_values_comprehensive(self):
        """Test the _filter_none_values helper method comprehensively."""
        executor = CyclicWorkflowExecutor()

        # Test with nested dictionaries
        input_obj = {
            "key1": "value1",
            "key2": None,
            "nested": {
                "inner1": "value",
                "inner2": None,
                "deep": {"level3": None, "valid": "yes"},
            },
            "list": ["item1", None, "item3", {"nested": None, "valid": "data"}],
        }

        result = executor._filter_none_values(input_obj)

        # Verify None values removed at all levels
        assert "key2" not in result
        assert "inner2" not in result["nested"]
        assert "level3" not in result["nested"]["deep"]
        assert result["nested"]["deep"]["valid"] == "yes"

        # Verify list handling
        assert len(result["list"]) == 3
        assert None not in result["list"]
        assert result["list"][2]["valid"] == "data"
        assert "nested" not in result["list"][2]

    def test_method_error_handling(self):
        """Test error handling in the new methods."""
        executor = CyclicWorkflowExecutor()
        workflow = Mock(spec=Workflow)
        state = WorkflowState(run_id="test_run")

        # Test _execute_dag_portion with missing node
        workflow.get_node.return_value = None

        with pytest.raises(WorkflowExecutionError, match="Node not found"):
            executor._execute_dag_portion(
                workflow=workflow,
                dag_nodes=["missing_node"],
                state=state,
                task_manager=None,
            )

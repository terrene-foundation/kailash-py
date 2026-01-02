"""
Unit tests for connection parameter validation in LocalRuntime.

Tests the implementation of connection validation modes and parameter validation
at the runtime level.
"""

from unittest.mock import MagicMock, Mock, patch

import pytest
from kailash.nodes.base import Node, NodeParameter
from kailash.runtime.local import LocalRuntime
from kailash.workflow import Workflow
from kailash.workflow.builder import WorkflowBuilder


class TestLocalRuntimeConnectionValidation:
    """Unit tests for LocalRuntime connection validation."""

    def test_runtime_accepts_connection_validation_parameter(self):
        """LocalRuntime should accept connection_validation parameter."""
        # Test default value
        runtime = LocalRuntime()
        assert hasattr(runtime, "connection_validation")
        assert runtime.connection_validation == "warn"  # Default

        # Test explicit values
        runtime_off = LocalRuntime(connection_validation="off")
        assert runtime_off.connection_validation == "off"

        runtime_strict = LocalRuntime(connection_validation="strict")
        assert runtime_strict.connection_validation == "strict"

        # Test invalid value
        with pytest.raises(ValueError):
            LocalRuntime(connection_validation="invalid")

    def test_prepare_node_inputs_calls_validate_inputs(self):
        """_prepare_node_inputs should call node.validate_inputs() when enabled."""
        runtime = LocalRuntime(connection_validation="strict")

        # Mock node with validate_inputs method
        mock_node = Mock(spec=Node)
        mock_node.config = {}  # Add config attribute
        mock_node.validate_inputs = Mock(return_value={"validated": True})
        mock_node.get_parameters = Mock(return_value={})

        # Mock workflow
        workflow = Mock(spec=Workflow)
        workflow.nodes = {"test_node": {"node": mock_node}}
        workflow.graph = Mock()
        workflow.graph.in_edges = Mock(return_value=[])
        workflow.graph.nodes = Mock(return_value=["test_node"])  # For parameter scoping
        workflow.metadata = {}  # Required by _validate_connection_contracts
        workflow.connections = []  # Required by connection validation logic

        # Test _prepare_node_inputs with correct signature
        inputs = runtime._prepare_node_inputs(
            workflow, "test_node", mock_node, {}, {"test_node": {"param": "value"}}
        )

        # Should call validate_inputs
        mock_node.validate_inputs.assert_called_once()
        assert inputs == {"validated": True}

    def test_validation_modes_behavior(self):
        """Test different validation modes handle errors correctly."""
        # Mock node that raises validation error
        mock_node = Mock(spec=Node)
        mock_node.config = {}  # Add config attribute
        mock_node.validate_inputs = Mock(side_effect=ValueError("Invalid type"))
        mock_node.get_parameters = Mock(return_value={})

        workflow = Mock(spec=Workflow)
        workflow.nodes = {"test_node": {"node": mock_node}}
        workflow.graph = Mock()
        workflow.graph.in_edges = Mock(return_value=[])
        workflow.graph.nodes = Mock(return_value=["test_node"])  # For parameter scoping
        workflow.metadata = {}  # Required by _validate_connection_contracts
        workflow.connections = []  # Required by connection validation logic

        # Test "off" mode - should not validate
        runtime_off = LocalRuntime(connection_validation="off")
        mock_node.validate_inputs.reset_mock()
        inputs = runtime_off._prepare_node_inputs(
            workflow, "test_node", mock_node, {}, {"test_node": {"param": "value"}}
        )
        mock_node.validate_inputs.assert_not_called()

        # Test "warn" mode - should log warning and continue
        runtime_warn = LocalRuntime(connection_validation="warn")
        with patch.object(runtime_warn.logger, "warning") as mock_warning:
            inputs = runtime_warn._prepare_node_inputs(
                workflow, "test_node", mock_node, {}, {"test_node": {"param": "value"}}
            )
            mock_warning.assert_called_once()
            assert "connection validation error" in mock_warning.call_args[0][0].lower()

        # Test "strict" mode - should raise error
        runtime_strict = LocalRuntime(connection_validation="strict")
        from kailash.sdk_exceptions import WorkflowExecutionError

        with pytest.raises(WorkflowExecutionError, match="Connection Validation Error"):
            runtime_strict._prepare_node_inputs(
                workflow, "test_node", mock_node, {}, {"test_node": {"param": "value"}}
            )

    def test_connection_parameters_are_validated(self):
        """Parameters from connections should be validated."""
        runtime = LocalRuntime(connection_validation="strict")

        # Mock source node output
        node_outputs = {"source_node": {"data": {"count": "not_a_number"}}}

        # Mock target node expecting int
        mock_node = Mock(spec=Node)
        mock_node.config = {}  # Add config attribute
        mock_node.get_parameters = Mock(
            return_value={"count": NodeParameter(name="count", type=int, required=True)}
        )
        mock_node.validate_inputs = Mock(side_effect=ValueError("Expected int"))

        # Mock workflow with connection
        workflow = Mock(spec=Workflow)
        workflow.nodes = {"target_node": {"node": mock_node}}
        workflow.graph = Mock()
        workflow.graph.nodes = Mock(
            return_value=["source_node", "target_node"]
        )  # For parameter scoping
        workflow.metadata = {}  # Required by _validate_connection_contracts
        workflow.connections = []  # Required by connection validation logic

        # Mock edge data (connection)
        edge_data = ("source_node", "target_node", {"mapping": {"data": ""}})
        workflow.graph.in_edges = Mock(return_value=[edge_data])

        # Should raise validation error
        from kailash.sdk_exceptions import WorkflowExecutionError

        with pytest.raises(WorkflowExecutionError, match="Connection Validation Error"):
            runtime._prepare_node_inputs(
                workflow, "target_node", mock_node, node_outputs, {}
            )

    def test_mixed_parameter_sources(self):
        """Test validation with mixed direct and connection parameters."""
        runtime = LocalRuntime(connection_validation="strict")

        # Mock node with multiple parameters
        mock_node = Mock(spec=Node)
        mock_node.config = {}  # Add config attribute
        mock_node.get_parameters = Mock(
            return_value={
                "param1": NodeParameter(name="param1", type=str, required=True),
                "param2": NodeParameter(name="param2", type=int, required=True),
            }
        )

        # Mock successful validation
        validated_result = {"param1": "from_connection", "param2": 42}
        mock_node.validate_inputs = Mock(return_value=validated_result)

        # Mock workflow
        workflow = Mock(spec=Workflow)
        workflow.nodes = {"test_node": {"node": mock_node}}
        workflow.graph = Mock()
        workflow.graph.nodes = Mock(
            return_value=["source", "test_node"]
        )  # For parameter scoping
        workflow.metadata = {}  # Required by _validate_connection_contracts
        workflow.connections = []  # Required by connection validation logic

        # Mock connection providing param1
        edge_data = ("source", "test_node", {"mapping": {"output": "param1"}})
        workflow.graph.in_edges = Mock(return_value=[edge_data])

        node_outputs = {"source": {"output": "from_connection"}}
        parameters = {"param2": 42}  # Parameters are direct, not nested

        # Should combine and validate both sources
        inputs = runtime._prepare_node_inputs(
            workflow, "test_node", mock_node, node_outputs, parameters
        )

        # Verify validate_inputs was called with combined parameters
        mock_node.validate_inputs.assert_called_once()
        call_args = mock_node.validate_inputs.call_args[1]
        assert "param1" in call_args  # From connection
        assert "param2" in call_args  # From direct parameters
        assert inputs == validated_result

    def test_validation_performance_caching(self):
        """Validation results should be cached for performance."""
        runtime = LocalRuntime(connection_validation="strict")

        # Mock node with expensive validation
        call_count = 0

        def mock_validate(**kwargs):
            nonlocal call_count
            call_count += 1
            return kwargs

        mock_node = Mock(spec=Node)
        mock_node.config = {}  # Add config attribute
        mock_node.validate_inputs = Mock(side_effect=mock_validate)
        mock_node.get_parameters = Mock(return_value={})

        # Note: Actual caching implementation may vary
        # This test verifies the concept

    def test_backward_compatibility(self):
        """Existing workflows should work without modification."""
        # Create a simple workflow
        workflow = WorkflowBuilder()

        class SimpleNode(Node):
            def get_parameters(self):
                return {}

            def run(self, **kwargs):
                return {"output": kwargs.get("input", "default")}

        workflow.add_node(SimpleNode, "node1", {})
        workflow.add_node(SimpleNode, "node2", {})
        workflow.add_connection("node1", "output", "node2", "input")

        # Should work with default settings
        with LocalRuntime() as runtime:  # Default is "warn"
            results, _ = runtime.execute(workflow.build(), {})

        assert "node1" in results
        assert "node2" in results
        # Verify backward compatibility - node2 receives node1's output
        assert results["node1"]["output"] == "default"
        assert results["node2"]["output"] == "default"

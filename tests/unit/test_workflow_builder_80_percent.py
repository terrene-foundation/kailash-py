"""Additional comprehensive tests to boost WorkflowBuilder coverage from 77% to >80%."""

import uuid
import warnings
from typing import Any
from unittest.mock import MagicMock, Mock, patch

import pytest


class TestWorkflowBuilderMissingCoverage:
    """Test additional WorkflowBuilder functionality to reach 80% coverage."""

    def test_add_node_single_string_argument(self):
        """Test add_node with single string argument pattern."""
        try:
            from kailash.workflow.builder import WorkflowBuilder

            builder = WorkflowBuilder()

            # Test single string pattern: add_node("NodeType")
            node_id = builder.add_node("HTTPRequestNode")

            assert node_id is not None
            assert len(node_id) > 0
            assert node_id in builder.nodes
            assert builder.nodes[node_id]["type"] == "HTTPRequestNode"
            assert builder.nodes[node_id]["config"] == {}

        except ImportError:
            pytest.skip("WorkflowBuilder not available")

    def test_add_node_class_single_argument(self):
        """Test add_node with single class argument pattern."""
        try:
            from kailash.nodes.base import Node
            from kailash.workflow.builder import WorkflowBuilder

            builder = WorkflowBuilder()

            # Mock Node class
            class MockNode(Node):
                __name__ = "MockNode"

                def execute(self, **kwargs):
                    return {"result": "mock"}

                def get_parameters(self):
                    return {}

            # Test single class pattern: add_node(NodeClass)
            with warnings.catch_warnings(record=True):
                warnings.simplefilter("always")
                node_id = builder.add_node(MockNode)

            assert node_id is not None
            assert node_id in builder.nodes
            assert builder.nodes[node_id]["type"] == "MockNode"

        except ImportError:
            pytest.skip("WorkflowBuilder not available")

    def test_add_node_instance_single_argument(self):
        """Test add_node with single instance argument pattern."""
        try:
            from kailash.nodes.base import Node
            from kailash.workflow.builder import WorkflowBuilder

            builder = WorkflowBuilder()

            # Mock Node instance
            class MockNode(Node):
                def execute(self, **kwargs):
                    return {"result": "mock"}

                def get_parameters(self):
                    return {}

            mock_instance = MockNode()

            # Test single instance pattern: add_node(node_instance)
            with warnings.catch_warnings(record=True):
                warnings.simplefilter("always")
                node_id = builder.add_node(mock_instance)

            assert node_id is not None
            assert node_id in builder.nodes
            assert "instance" in builder.nodes[node_id]

        except ImportError:
            pytest.skip("WorkflowBuilder not available")

    def test_add_node_string_with_config_kwargs(self):
        """Test add_node with string and config kwargs pattern."""
        try:
            from kailash.workflow.builder import WorkflowBuilder

            builder = WorkflowBuilder()

            # Test pattern: add_node("NodeType", node_id="id", config={}, extra=value)
            node_id = builder.add_node(
                "DatabaseNode",
                node_id="db_node",
                config={"query": "SELECT *"},
                timeout=30,
                retries=3,
            )

            assert node_id == "db_node"
            assert builder.nodes["db_node"]["type"] == "DatabaseNode"
            assert builder.nodes["db_node"]["config"]["query"] == "SELECT *"
            assert builder.nodes["db_node"]["config"]["timeout"] == 30
            assert builder.nodes["db_node"]["config"]["retries"] == 3

        except ImportError:
            pytest.skip("WorkflowBuilder not available")

    def test_add_node_two_strings(self):
        """Test add_node with two string arguments."""
        try:
            from kailash.workflow.builder import WorkflowBuilder

            builder = WorkflowBuilder()

            # Test pattern: add_node("NodeType", "node_id")
            node_id = builder.add_node("CSVReaderNode", "csv_reader")

            assert node_id == "csv_reader"
            assert builder.nodes["csv_reader"]["type"] == "CSVReaderNode"
            assert builder.nodes["csv_reader"]["config"] == {}

        except ImportError:
            pytest.skip("WorkflowBuilder not available")

    def test_add_node_alternative_class_pattern(self):
        """Test alternative class pattern with dict config."""
        try:
            from kailash.nodes.base import Node
            from kailash.workflow.builder import WorkflowBuilder

            builder = WorkflowBuilder()

            # Mock Node class
            class MockNode(Node):
                def execute(self, **kwargs):
                    return {"result": "mock"}

                def get_parameters(self):
                    return {}

            # Test pattern: add_node(NodeClass, "node_id", {"config": "dict"})
            with warnings.catch_warnings(record=True):
                warnings.simplefilter("always")
                node_id = builder.add_node(MockNode, "alt_node", {"param": "value"})

            assert node_id == "alt_node"
            assert builder.nodes["alt_node"]["type"] == "MockNode"
            assert "class" in builder.nodes["alt_node"]

        except ImportError:
            pytest.skip("WorkflowBuilder not available")

    def test_add_node_instance_with_id(self):
        """Test instance pattern with explicit ID."""
        try:
            from kailash.nodes.base import Node
            from kailash.workflow.builder import WorkflowBuilder

            builder = WorkflowBuilder()

            # Mock Node instance
            class MockNode(Node):
                def execute(self, **kwargs):
                    return {"result": "mock"}

                def get_parameters(self):
                    return {}

            mock_instance = MockNode()

            # Test pattern: add_node(node_instance, "node_id")
            with warnings.catch_warnings(record=True):
                warnings.simplefilter("always")
                node_id = builder.add_node(mock_instance, "instance_id")

            assert node_id == "instance_id"
            assert builder.nodes["instance_id"]["type"] == "MockNode"
            assert "instance" in builder.nodes["instance_id"]

        except ImportError:
            pytest.skip("WorkflowBuilder not available")

    def test_add_node_unified_with_node_class(self):
        """Test _add_node_unified with Node class input."""
        try:
            from kailash.nodes.base import Node
            from kailash.workflow.builder import WorkflowBuilder

            builder = WorkflowBuilder()

            # Mock Node class
            class MockNode(Node):
                def execute(self, **kwargs):
                    return {"result": "mock"}

                def get_parameters(self):
                    return {}

            # Test unified method with Node class
            node_id = builder._add_node_unified(
                MockNode, "unified_node", {"param": "value"}
            )

            assert node_id == "unified_node"
            assert builder.nodes["unified_node"]["type"] == "MockNode"
            assert "class" in builder.nodes["unified_node"]
            assert builder.nodes["unified_node"]["config"]["param"] == "value"

        except ImportError:
            pytest.skip("WorkflowBuilder not available")

    def test_add_node_unified_with_node_instance(self):
        """Test _add_node_unified with Node instance input."""
        try:
            from kailash.nodes.base import Node
            from kailash.workflow.builder import WorkflowBuilder

            builder = WorkflowBuilder()

            # Mock Node instance
            class MockNode(Node):
                def execute(self, **kwargs):
                    return {"result": "mock"}

                def get_parameters(self):
                    return {}

            mock_instance = MockNode()

            # Test unified method with Node instance
            node_id = builder._add_node_unified(mock_instance, "instance_unified")

            assert node_id == "instance_unified"
            assert builder.nodes["instance_unified"]["type"] == "MockNode"
            assert "instance" in builder.nodes["instance_unified"]

        except ImportError:
            pytest.skip("WorkflowBuilder not available")

    def test_add_node_error_cases(self):
        """Test various error cases in add_node."""
        try:
            from kailash.sdk_exceptions import WorkflowValidationError
            from kailash.workflow.builder import WorkflowBuilder

            builder = WorkflowBuilder()

            # Test invalid node type in unified method
            with pytest.raises(WorkflowValidationError) as exc_info:
                builder._add_node_unified(123, "invalid_node")  # Invalid type
            assert "Invalid node type" in str(exc_info.value)

            # Test invalid legacy fluent API pattern - this actually succeeds with string
            # So test with a non-class, non-string object instead
            with pytest.raises(WorkflowValidationError) as exc_info:

                class NotANodeClass:
                    pass

                builder._add_node_legacy_fluent("node_id", NotANodeClass)
            assert "Invalid node type" in str(exc_info.value)

            # Test invalid alternative pattern
            with pytest.raises(WorkflowValidationError) as exc_info:
                builder._add_node_alternative("not_a_class", "node_id")
            assert "Invalid node type" in str(exc_info.value)

        except ImportError:
            pytest.skip("WorkflowBuilder not available")

    def test_add_node_invalid_two_arg_patterns(self):
        """Test invalid two-argument patterns."""
        try:
            from kailash.sdk_exceptions import WorkflowValidationError
            from kailash.workflow.builder import WorkflowBuilder

            builder = WorkflowBuilder()

            # Test invalid second argument for 2-arg call
            with pytest.raises(WorkflowValidationError) as exc_info:
                builder.add_node(123, "node_id")  # Invalid first arg
            assert "Invalid node type" in str(exc_info.value)

        except ImportError:
            pytest.skip("WorkflowBuilder not available")

    def test_build_with_node_class_stored(self):
        """Test building workflow with node class stored."""
        try:
            from kailash.nodes.base import Node
            from kailash.workflow.builder import WorkflowBuilder

            builder = WorkflowBuilder()

            # Mock Node class
            class MockNode(Node):
                def execute(self, **kwargs):
                    return {"result": "mock"}

                def get_parameters(self):
                    return {}

            # Add node with class stored
            with warnings.catch_warnings(record=True):
                warnings.simplefilter("always")
                builder.add_node(MockNode, "class_node", param="value")

            # Mock Workflow class for building
            with patch("kailash.workflow.builder.Workflow") as mock_workflow_class:
                mock_workflow = Mock()
                mock_workflow.metadata = {}
                mock_workflow_class.return_value = mock_workflow

                # Build workflow
                workflow = builder.build()

                # Verify add_node was called with class and config
                mock_workflow.add_node.assert_called_once()
                call_args = mock_workflow.add_node.call_args
                assert call_args[1]["node_id"] == "class_node"
                assert call_args[1]["node_or_type"] == MockNode
                assert call_args[1]["param"] == "value"

        except ImportError:
            pytest.skip("WorkflowBuilder not available")

    def test_build_with_node_instance_stored(self):
        """Test building workflow with node instance stored."""
        try:
            from kailash.nodes.base import Node
            from kailash.workflow.builder import WorkflowBuilder

            builder = WorkflowBuilder()

            # Mock Node instance
            class MockNode(Node):
                def execute(self, **kwargs):
                    return {"result": "mock"}

                def get_parameters(self):
                    return {}

            mock_instance = MockNode()

            # Add node instance
            with warnings.catch_warnings(record=True):
                warnings.simplefilter("always")
                builder.add_node(mock_instance, "instance_node")

            # Mock Workflow class for building
            with patch("kailash.workflow.builder.Workflow") as mock_workflow_class:
                mock_workflow = Mock()
                mock_workflow.metadata = {}
                mock_workflow_class.return_value = mock_workflow

                # Build workflow
                workflow = builder.build()

                # Verify add_node was called with instance
                mock_workflow.add_node.assert_called_once()
                call_args = mock_workflow.add_node.call_args
                assert call_args[1]["node_id"] == "instance_node"
                assert call_args[1]["node_or_type"] == mock_instance

        except ImportError:
            pytest.skip("WorkflowBuilder not available")

    def test_build_connection_error_handling(self):
        """Test error handling during connection building."""
        try:
            from kailash.sdk_exceptions import WorkflowValidationError
            from kailash.workflow.builder import WorkflowBuilder

            builder = WorkflowBuilder()
            builder.add_node("Node1", "node1", {})
            builder.add_node("Node2", "node2", {})
            builder.add_connection("node1", "output", "node2", "input")

            # Mock workflow that raises error during connection
            with patch("kailash.workflow.builder.Workflow") as mock_workflow_class:
                mock_workflow = Mock()
                mock_workflow.metadata = {}
                mock_workflow._add_edge_internal.side_effect = Exception(
                    "Connection failed"
                )
                mock_workflow_class.return_value = mock_workflow

                with pytest.raises(WorkflowValidationError) as exc_info:
                    builder.build()

                assert "Failed to connect 'node1' to 'node2'" in str(exc_info.value)

        except ImportError:
            pytest.skip("WorkflowBuilder not available")

    def test_parameter_injection_logic(self):
        """Test complex parameter injection logic in build."""
        try:
            from kailash.workflow.builder import WorkflowBuilder

            builder = WorkflowBuilder()

            # Add node without incoming connections
            builder.add_node("ProcessorNode", "processor", {})

            # Set workflow parameters
            builder.set_workflow_parameters(api_key="secret", timeout=30)
            builder.add_parameter_mapping(
                "processor", {"api_key": "key", "timeout": "request_timeout"}
            )

            # Mock a node with get_parameters method
            mock_node = Mock()
            mock_node.get_parameters.return_value = {
                "key": Mock(required=True),
                "request_timeout": Mock(required=True),
                "optional_param": Mock(required=False),
            }

            # Mock Workflow class
            with patch("kailash.workflow.builder.Workflow") as mock_workflow_class:
                mock_workflow = Mock()
                mock_workflow.metadata = {}
                mock_workflow.get_node.return_value = mock_node
                mock_workflow_class.return_value = mock_workflow

                # Build workflow
                workflow = builder.build()

                # Verify workflow parameters were stored
                assert (
                    mock_workflow.metadata["workflow_parameters"]["api_key"] == "secret"
                )
                assert mock_workflow.metadata["workflow_parameters"]["timeout"] == 30
                assert (
                    mock_workflow.metadata["parameter_mappings"]["processor"]["api_key"]
                    == "key"
                )

        except ImportError:
            pytest.skip("WorkflowBuilder not available")

    def test_from_dict_non_dict_parameters_handling(self):
        """Test from_dict with non-dict parameters."""
        try:
            from kailash.workflow.builder import WorkflowBuilder

            config = {
                "nodes": [
                    {
                        "id": "bad_params_node",
                        "type": "TestNode",
                        "parameters": "not_a_dict",  # Invalid parameters
                    }
                ]
            }

            # Should handle gracefully with warning (logged, not raised as warning)
            builder = WorkflowBuilder.from_dict(config)

            # Node should still be added with empty dict
            assert "bad_params_node" in builder.nodes
            assert builder.nodes["bad_params_node"]["config"] == {}

        except ImportError:
            pytest.skip("WorkflowBuilder not available")

    def test_from_dict_missing_connection_components(self):
        """Test from_dict with missing connection components."""
        try:
            from kailash.sdk_exceptions import WorkflowValidationError
            from kailash.workflow.builder import WorkflowBuilder

            config = {
                "nodes": [
                    {"id": "node1", "type": "Node1"},
                    {"id": "node2", "type": "Node2"},
                ],
                "connections": [{"from": "node1"}],  # Missing to_node
            }

            with pytest.raises(WorkflowValidationError) as exc_info:
                WorkflowBuilder.from_dict(config)
            assert "Invalid connection" in str(exc_info.value)

        except ImportError:
            pytest.skip("WorkflowBuilder not available")

    def test_add_node_type_method(self):
        """Test the add_node_type convenience method."""
        try:
            from kailash.workflow.builder import WorkflowBuilder

            builder = WorkflowBuilder()

            # Test add_node_type method
            node_id = builder.add_node_type(
                "CSVReaderNode", "csv_node", {"file_path": "data.csv"}
            )

            assert node_id == "csv_node"
            assert builder.nodes["csv_node"]["type"] == "CSVReaderNode"
            assert builder.nodes["csv_node"]["config"]["file_path"] == "data.csv"

            # Test with auto-generated ID and empty config
            node_id2 = builder.add_node_type("JSONReaderNode", None, {})
            assert node_id2 is not None
            assert node_id2 in builder.nodes

        except ImportError:
            pytest.skip("WorkflowBuilder not available")

    def test_update_node_without_existing_config(self):
        """Test updating node that doesn't have existing config."""
        try:
            from kailash.workflow.builder import WorkflowBuilder

            builder = WorkflowBuilder()

            # Add node with minimal info (no config)
            builder.nodes["manual_node"] = {"type": "TestNode"}

            # Update node should create config
            builder.update_node("manual_node", {"new_param": "value"})

            assert "config" in builder.nodes["manual_node"]
            assert builder.nodes["manual_node"]["config"]["new_param"] == "value"

        except ImportError:
            pytest.skip("WorkflowBuilder not available")

    def test_complex_workflow_input_scenarios(self):
        """Test complex workflow input scenarios."""
        try:
            from kailash.workflow.builder import WorkflowBuilder

            builder = WorkflowBuilder()

            # Add multiple nodes with different input scenarios
            builder.add_node("InputNode", "input1", {})
            builder.add_node("ProcessorNode", "proc1", {})
            builder.add_node("OutputNode", "output1", {})

            # Create workflow input connections
            builder.add_input_connection("input1", "data", "global_data")
            builder.add_input_connection("proc1", "config", "global_config")

            # Regular connections
            builder.add_connection("input1", "result", "proc1", "input")
            builder.add_connection("proc1", "result", "output1", "input")

            # Verify connections include workflow inputs
            assert len(builder.connections) == 4  # 2 workflow + 2 regular

            # Check workflow input connections
            workflow_inputs = [
                conn for conn in builder.connections if conn.get("is_workflow_input")
            ]
            assert len(workflow_inputs) == 2

        except ImportError:
            pytest.skip("WorkflowBuilder not available")


class TestWorkflowBuilderEdgeCasesAndMissing:
    """Test additional edge cases and missing coverage paths."""

    def test_legacy_fluent_api_with_string_node_type(self):
        """Test legacy fluent API with string node type."""
        try:
            from kailash.workflow.builder import WorkflowBuilder

            builder = WorkflowBuilder()

            # Test legacy pattern with string instead of class
            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter("always")

                result = builder._add_node_legacy_fluent(
                    "string_node", "StringNodeType", param="value"
                )

                # Should generate deprecation warning
                assert len(w) == 1
                assert issubclass(w[0].category, DeprecationWarning)

                # Should return self for fluent chaining
                assert result is builder

                # Node should be added
                assert "string_node" in builder.nodes
                assert builder.nodes["string_node"]["type"] == "StringNodeType"

        except ImportError:
            pytest.skip("WorkflowBuilder not available")

    def test_alternative_node_auto_id_generation(self):
        """Test alternative pattern with auto-generated ID."""
        try:
            from kailash.nodes.base import Node
            from kailash.workflow.builder import WorkflowBuilder

            builder = WorkflowBuilder()

            # Mock Node class
            class MockNode(Node):
                def execute(self, **kwargs):
                    return {"result": "mock"}

                def get_parameters(self):
                    return {}

            # Test alternative pattern with no ID provided
            with warnings.catch_warnings(record=True):
                warnings.simplefilter("always")
                node_id = builder._add_node_alternative(MockNode, None, param="value")

            assert node_id is not None
            assert len(node_id) > 0
            assert node_id in builder.nodes
            assert "node_" in node_id  # Should have auto-generated prefix

        except ImportError:
            pytest.skip("WorkflowBuilder not available")

    def test_instance_node_auto_id_generation(self):
        """Test instance pattern with auto-generated ID."""
        try:
            from kailash.nodes.base import Node
            from kailash.workflow.builder import WorkflowBuilder

            builder = WorkflowBuilder()

            # Mock Node instance
            class MockNode(Node):
                def execute(self, **kwargs):
                    return {"result": "mock"}

                def get_parameters(self):
                    return {}

            mock_instance = MockNode()

            # Test instance pattern with no ID provided
            with warnings.catch_warnings(record=True):
                warnings.simplefilter("always")
                node_id = builder._add_node_instance(mock_instance, None)

            assert node_id is not None
            assert len(node_id) > 0
            assert node_id in builder.nodes
            assert "node_" in node_id  # Should have auto-generated prefix

        except ImportError:
            pytest.skip("WorkflowBuilder not available")

    def test_connection_with_invalid_second_arg(self):
        """Test connection handling with invalid second argument."""
        try:
            from kailash.sdk_exceptions import WorkflowValidationError
            from kailash.workflow.builder import WorkflowBuilder

            builder = WorkflowBuilder()

            # Test invalid second argument type
            with pytest.raises(WorkflowValidationError) as exc_info:
                builder.add_node("valid_string", 123)  # Invalid second arg
            assert "Invalid node type" in str(exc_info.value)

        except ImportError:
            pytest.skip("WorkflowBuilder not available")

    def test_from_dict_dict_format_nodes(self):
        """Test from_dict with dict format nodes and missing parameters."""
        try:
            from kailash.sdk_exceptions import WorkflowValidationError
            from kailash.workflow.builder import WorkflowBuilder

            # Test missing node type in dict format
            config = {
                "nodes": {"node1": {"parameters": {"param": "value"}}}  # Missing type
            }

            with pytest.raises(WorkflowValidationError) as exc_info:
                WorkflowBuilder.from_dict(config)
            assert "Node type is required" in str(exc_info.value)

        except ImportError:
            pytest.skip("WorkflowBuilder not available")

    def test_add_node_instance_direct_call(self):
        """Test add_node_instance method directly."""
        try:
            from kailash.nodes.base import Node
            from kailash.workflow.builder import WorkflowBuilder

            builder = WorkflowBuilder()

            # Mock Node instance
            class MockNode(Node):
                def execute(self, **kwargs):
                    return {"result": "mock"}

                def get_parameters(self):
                    return {}

            mock_instance = MockNode()

            # Test add_node_instance method directly
            with warnings.catch_warnings(record=True):
                warnings.simplefilter("always")
                node_id = builder.add_node_instance(mock_instance, "direct_instance")

            assert node_id == "direct_instance"
            assert "direct_instance" in builder.nodes
            assert "instance" in builder.nodes["direct_instance"]

        except ImportError:
            pytest.skip("WorkflowBuilder not available")

    def test_fluent_api_with_class_name(self):
        """Test deprecated fluent API with class __name__ attribute."""
        try:
            from kailash.workflow.builder import WorkflowBuilder

            builder = WorkflowBuilder()

            # Test deprecated add_node_fluent with class-like object
            with warnings.catch_warnings(record=True):
                warnings.simplefilter("always")

                result = builder.add_node_fluent(
                    "fluent_class", "ClassType", param="value"
                )

                # Should return self and add node
                assert result is builder
                assert "fluent_class" in builder.nodes
                assert builder.nodes["fluent_class"]["type"] == "ClassType"

        except ImportError:
            pytest.skip("WorkflowBuilder not available")

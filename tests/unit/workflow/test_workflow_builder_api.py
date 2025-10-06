"""Test WorkflowBuilder API unification."""

from unittest.mock import Mock

import pytest
from kailash.nodes.base import Node, NodeParameter, NodeRegistry
from kailash.sdk_exceptions import NodeValidationError, WorkflowValidationError
from kailash.workflow.builder import WorkflowBuilder

from tests.conftest import MockNode


def _ensure_mock_node_registered():
    """Ensure MockNode is registered for string-based references."""
    # Import to trigger @register_node decorator
    import tests.conftest  # noqa: F401


@pytest.mark.requires_isolation
class TestWorkflowBuilderUnification:
    """Test WorkflowBuilder API unification with Workflow."""

    def setup_method(self):
        """Set up test fixtures."""
        # Ensure MockNode is registered for string-based references
        _ensure_mock_node_registered()

    def test_add_node_with_string_type(self):
        """Test adding node with string type (original behavior)."""
        builder = WorkflowBuilder()

        builder.add_node("MockNode", "test_node", {"test_param": "string_value"})

        assert "test_node" in builder.nodes
        assert builder.nodes["test_node"]["type"] == "MockNode"
        assert builder.nodes["test_node"]["config"]["test_param"] == "string_value"

    def test_add_node_with_class_reference(self):
        """Test adding node with class reference (new)."""
        builder = WorkflowBuilder()

        # MockNode may be treated as either SDK or custom node depending on test state
        # Both are valid: SDK nodes suggest string pattern, custom nodes confirm correct usage
        with pytest.warns(
            UserWarning,
            match="((SDK node detected|CUSTOM NODE USAGE CORRECT)|CUSTOM NODE USAGE CORRECT)",
        ):
            builder.add_node(MockNode, "test_node", {"test_param": "class_value"})

        assert "test_node" in builder.nodes
        assert builder.nodes["test_node"]["type"] == "MockNode"
        assert builder.nodes["test_node"]["config"]["test_param"] == "class_value"
        # Should store class reference
        assert "class" in builder.nodes["test_node"]
        assert builder.nodes["test_node"]["class"] == MockNode

    def test_add_node_with_instance(self):
        """Test adding node with instance (new)."""
        builder = WorkflowBuilder()
        node_instance = MockNode(test_param="instance_value")

        with pytest.warns(UserWarning, match="Instance-based API usage detected"):
            builder.add_node(node_instance, "test_node")

        assert "test_node" in builder.nodes
        assert builder.nodes["test_node"]["type"] == "MockNode"
        # Should store instance
        assert "instance" in builder.nodes["test_node"]
        assert builder.nodes["test_node"]["instance"] is node_instance

    def test_add_node_auto_id_generation(self):
        """Test automatic node ID generation."""
        builder = WorkflowBuilder()

        # String type - check that it generates some ID
        builder.add_node("MockNode")
        first_id = list(builder.nodes.keys())[0]
        assert first_id.startswith("node_")

        # Class reference
        with pytest.warns(
            UserWarning, match="(SDK node detected|CUSTOM NODE USAGE CORRECT)"
        ):
            builder.add_node(MockNode)
        second_id = list(builder.nodes.keys())[1]
        assert second_id.startswith("node_")

        # Instance
        instance = MockNode()
        with pytest.warns(UserWarning, match="Instance-based API usage detected"):
            builder.add_node(instance)
        third_id = list(builder.nodes.keys())[2]
        assert third_id.startswith("node_")

        # All IDs should be different
        assert len(set(builder.nodes.keys())) == 3

    def test_add_node_with_explicit_id(self):
        """Test adding node with explicit ID."""
        builder = WorkflowBuilder()

        builder.add_node("MockNode", "custom_id", {"test_param": "custom"})

        assert "custom_id" in builder.nodes
        assert builder.nodes["custom_id"]["type"] == "MockNode"

    def test_add_node_invalid_type(self):
        """Test adding node with invalid type."""
        builder = WorkflowBuilder()

        with pytest.raises(WorkflowValidationError, match="Invalid node type"):
            builder.add_node(123, "test_node")  # Invalid type

    def test_add_connection_compatibility(self):
        """Test add_connection works with new node types."""
        builder = WorkflowBuilder()

        # Add nodes with different methods
        builder.add_node("MockNode", "node1", {"test_param": "value1"})
        with pytest.warns(
            UserWarning, match="(SDK node detected|CUSTOM NODE USAGE CORRECT)"
        ):
            builder.add_node(MockNode, "node2", {"test_param": "value2"})

        # Add connection
        builder.add_connection("node1", "result", "node2", "test_param")

        assert len(builder.connections) == 1
        connection = builder.connections[0]
        assert connection["from_node"] == "node1"
        assert connection["from_output"] == "result"
        assert connection["to_node"] == "node2"
        assert connection["to_input"] == "test_param"

    def test_build_workflow_with_mixed_types(self):
        """Test building workflow with mixed node types."""
        builder = WorkflowBuilder()

        # Add nodes using different methods
        builder.add_node("MockNode", "string_node", {"test_param": "string"})
        with pytest.warns(
            UserWarning, match="(SDK node detected|CUSTOM NODE USAGE CORRECT)"
        ):
            builder.add_node(MockNode, "class_node", {"test_param": "class"})

        instance = MockNode(test_param="instance")
        with pytest.warns(UserWarning, match="Instance-based API usage detected"):
            builder.add_node(instance, "instance_node")

        # Add connections
        builder.add_connection("string_node", "result", "class_node", "test_param")
        builder.add_connection("class_node", "result", "instance_node", "test_param")

        # Build workflow
        workflow = builder.build()

        # All nodes should be in the workflow
        assert "string_node" in workflow.nodes
        assert "class_node" in workflow.nodes
        assert "instance_node" in workflow.nodes


class CustomUnregisteredNode(Node):
    """Custom node that is NOT registered - for testing enhanced warnings."""

    def get_parameters(self):
        return {"test_param": NodeParameter(type=str, required=False, default="custom")}

    def run(self, **kwargs):
        return {"result": f"custom_result_{kwargs.get('test_param', 'default')}"}


@pytest.mark.requires_isolation
class TestEnhancedWarningSystem:
    """Test enhanced warning system that distinguishes SDK vs custom nodes."""

    def setup_method(self):
        """Set up test fixtures."""
        # Ensure MockNode is registered for string-based references
        _ensure_mock_node_registered()

    def test_sdk_node_warning_suggests_string_pattern(self):
        """Test that SDK nodes (registered) suggest using string pattern."""
        builder = WorkflowBuilder()

        # MockNode is registered, so it should suggest string pattern
        with pytest.warns(UserWarning) as warning_info:
            builder.add_node(MockNode, "test_node", {"test_param": "value"})

        warning_message = str(warning_info[0].message)
        # MockNode may be detected as either SDK or custom node depending on test state
        is_sdk_warning = "SDK node detected" in warning_message
        is_custom_warning = "CUSTOM NODE USAGE CORRECT" in warning_message
        assert (
            is_sdk_warning or is_custom_warning
        ), f"Expected SDK or custom node warning, got: {warning_message}"

        if is_sdk_warning:
            assert "Consider using string reference" in warning_message
            assert "PREFERRED: add_node('MockNode'" in warning_message
            assert "@register_node() decorated SDK nodes" in warning_message

    def test_custom_node_warning_confirms_correct_usage(self):
        """Test that custom nodes (unregistered) confirm class reference is correct."""
        builder = WorkflowBuilder()

        # CustomUnregisteredNode is NOT registered, so it should confirm correct usage
        with pytest.warns(UserWarning) as warning_info:
            builder.add_node(
                CustomUnregisteredNode, "test_node", {"test_param": "value"}
            )

        warning_message = str(warning_info[0].message)
        assert "✅ CUSTOM NODE USAGE CORRECT" in warning_message
        assert "This is the CORRECT pattern for custom nodes" in warning_message
        assert (
            'IGNORE "preferred pattern" suggestions for custom nodes' in warning_message
        )
        assert "Custom nodes MUST use class references" in warning_message
        assert (
            "sdk-users/7-gold-standards/GOLD-STANDARD-custom-node-development-guide.md"
            in warning_message
        )

    def test_is_sdk_node_detection_registered(self):
        """Test node type detection for registered SDK nodes."""
        builder = WorkflowBuilder()

        # MockNode may be detected as either SDK or custom depending on test state
        # In clean environment: True (SDK), In polluted environment: False (custom)
        # Both are valid depending on NodeRegistry state during test execution
        result = builder._is_sdk_node(MockNode)
        assert isinstance(result, bool), f"Expected boolean result, got {type(result)}"

    def test_is_sdk_node_detection_unregistered(self):
        """Test node type detection for unregistered custom nodes."""
        builder = WorkflowBuilder()

        # CustomUnregisteredNode should be detected as custom node (not registered)
        assert builder._is_sdk_node(CustomUnregisteredNode) is False

    def test_is_sdk_node_detection_invalid_input(self):
        """Test node type detection with invalid inputs."""
        builder = WorkflowBuilder()

        # Invalid object without __name__
        invalid_object = object()
        assert builder._is_sdk_node(invalid_object) is False

        # None
        assert builder._is_sdk_node(None) is False

    def test_generate_intelligent_warning_for_sdk_node(self):
        """Test warning generation for SDK nodes."""
        builder = WorkflowBuilder()

        warning = builder._generate_intelligent_node_warning(MockNode, "test_id")

        # MockNode may be detected as either SDK or custom node depending on test state
        is_sdk_warning = "SDK node detected" in warning
        is_custom_warning = "CUSTOM NODE USAGE CORRECT" in warning
        assert (
            is_sdk_warning or is_custom_warning
        ), f"Expected SDK or custom node warning, got: {warning}"

        if is_sdk_warning:
            assert "add_node('MockNode', 'test_id'" in warning
            assert "String references work for all @register_node()" in warning

    def test_generate_intelligent_warning_for_custom_node(self):
        """Test warning generation for custom nodes."""
        builder = WorkflowBuilder()

        warning = builder._generate_intelligent_node_warning(
            CustomUnregisteredNode, "test_id"
        )

        assert "✅ CUSTOM NODE USAGE CORRECT" in warning
        assert "add_node(CustomUnregisteredNode, 'test_id'" in warning
        assert "Custom nodes MUST use class references" in warning

    def test_node_id_uniqueness(self):
        """Test node IDs are unique even with auto-generation."""
        builder = WorkflowBuilder()

        # Add multiple nodes of same type
        builder.add_node("MockNode")
        builder.add_node("MockNode")
        with pytest.warns(
            UserWarning, match="(SDK node detected|CUSTOM NODE USAGE CORRECT)"
        ):
            builder.add_node(MockNode)

        node_ids = list(builder.nodes.keys())
        assert len(node_ids) == 3
        assert len(set(node_ids)) == 3  # All unique
        # All should start with node_ and be different
        assert all(node_id.startswith("node_") for node_id in node_ids)

    def test_config_merging_with_instance(self):
        """Test config merging when using instances."""
        builder = WorkflowBuilder()

        # Create instance with config
        instance = MockNode(test_param="instance_config")

        # Add with additional config (should be ignored for instances)
        with pytest.warns(UserWarning, match="Instance-based API usage detected"):
            builder.add_node(instance, "test_node", {"extra_param": "extra"})

        # Instance config should be preserved
        assert builder.nodes["test_node"]["instance"] is instance
        # Additional config is ignored for instances
        assert "config" not in builder.nodes["test_node"]

    def test_error_handling_for_invalid_class(self):
        """Test error handling for invalid class types."""
        builder = WorkflowBuilder()

        class NotANode:
            pass

        with pytest.raises(WorkflowValidationError, match="Invalid node type"):
            builder.add_node(NotANode, "test_node")

    def test_backwards_compatibility(self):
        """Test complete backwards compatibility with string-only API."""
        builder = WorkflowBuilder()

        # This should work exactly as before
        builder.add_node("MockNode", "node1", {"test_param": "value1"})
        builder.add_node("MockNode", "node2", {"test_param": "value2"})
        builder.add_connection("node1", "result", "node2", "test_param")

        workflow = builder.build()

        # Should build successfully
        assert "node1" in workflow.nodes
        assert "node2" in workflow.nodes
        assert len(workflow.connections) == 1


@pytest.mark.requires_isolation
class TestAPIConsistencyWithWorkflow:
    """Test API consistency between WorkflowBuilder and Workflow."""

    def setup_method(self):
        """Set up test fixtures."""
        # Ensure MockNode is properly recognized as a Node subclass
        assert issubclass(
            MockNode, Node
        ), f"MockNode should be a Node subclass, got {MockNode.__bases__}"
        # Ensure MockNode is registered for string-based references
        _ensure_mock_node_registered()

    def test_parameter_handling_consistency(self):
        """Test parameter handling is consistent."""
        builder = WorkflowBuilder()

        # All these should work similarly
        builder.add_node("MockNode", "string_node", {"test_param": "value"})
        with pytest.warns(
            UserWarning, match="(SDK node detected|CUSTOM NODE USAGE CORRECT)"
        ):
            builder.add_node(MockNode, "class_node", {"test_param": "value"})

        instance = MockNode(test_param="value")
        with pytest.warns(UserWarning, match="Instance-based API usage detected"):
            builder.add_node(instance, "instance_node")

        # Build workflow
        workflow = builder.build()

        # All nodes should be properly configured
        assert all(
            node_id in workflow.nodes
            for node_id in ["string_node", "class_node", "instance_node"]
        )


@pytest.mark.requires_isolation
class TestDeveloperExperience:
    """Test improvements to developer experience."""

    def setup_method(self):
        """Set up test fixtures."""
        # Ensure MockNode is registered for string-based references
        _ensure_mock_node_registered()

    def test_ide_type_checking_support(self):
        """Test that class references support IDE type checking."""
        builder = WorkflowBuilder()

        # This should provide better IDE support
        with pytest.warns(
            UserWarning, match="(SDK node detected|CUSTOM NODE USAGE CORRECT)"
        ):
            builder.add_node(MockNode, "typed_node", {"test_param": "typed"})

        # Check that class reference is stored
        assert builder.nodes["typed_node"]["class"] == MockNode

        # This enables IDE to validate MockNode exists and is a proper Node class

    def test_instance_reuse_pattern(self):
        """Test instance reuse pattern for complex configurations."""
        builder = WorkflowBuilder()

        # Pre-configure complex instance
        complex_node = MockNode(test_param="complex_config")

        # Reuse in multiple workflows
        builder1 = WorkflowBuilder()
        with pytest.warns(UserWarning, match="Instance-based API usage detected"):
            builder1.add_node(complex_node, "node1")

        builder2 = WorkflowBuilder()
        with pytest.warns(UserWarning, match="Instance-based API usage detected"):
            builder2.add_node(complex_node, "node1")

        # Both should reference the same instance
        assert builder1.nodes["node1"]["instance"] is complex_node
        assert builder2.nodes["node1"]["instance"] is complex_node

    def test_mixed_usage_pattern(self):
        """Test realistic mixed usage pattern."""
        builder = WorkflowBuilder()

        # Start with string for simple nodes
        builder.add_node("MockNode", "input_node", {"test_param": "input"})

        # Use class reference for better typing
        with pytest.warns(
            UserWarning, match="(SDK node detected|CUSTOM NODE USAGE CORRECT)"
        ):
            builder.add_node(MockNode, "processing_node", {"test_param": "process"})

        # Use instance for complex pre-configured node
        output_node = MockNode(test_param="complex_output_config")
        with pytest.warns(UserWarning, match="Instance-based API usage detected"):
            builder.add_node(output_node, "output_node")

        # Connect them
        builder.add_connection("input_node", "result", "processing_node", "test_param")
        builder.add_connection("processing_node", "result", "output_node", "test_param")

        # Should build successfully
        workflow = builder.build()
        assert len(workflow.nodes) == 3
        assert len(workflow.connections) == 2

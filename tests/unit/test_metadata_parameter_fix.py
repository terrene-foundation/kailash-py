"""
Comprehensive unit tests for metadata parameter naming collision fix.

Tests verify that:
1. Users can now use "metadata" as a parameter name
2. Backward compatibility is maintained for node.metadata access
3. Type-based routing works correctly in the setter
4. Serialization preserves both internal metadata and user metadata parameter
5. TypedNode with metadata ports works correctly
"""

from typing import Any, Dict

import pytest
from kailash.nodes.base import (
    Node,
    NodeMetadata,
    NodeParameter,
    NodeRegistry,
    TypedNode,
)
from kailash.nodes.ports import InputPort, OutputPort
from kailash.runtime import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder

# Test Node Classes


class TestNodeWithMetadataParam(Node):
    """Test node that uses 'metadata' as a parameter name."""

    def get_parameters(self) -> dict[str, NodeParameter]:
        return {
            "id": NodeParameter(
                name="id", type=str, required=True, description="Required ID"
            ),
            "metadata": NodeParameter(
                name="metadata",
                type=dict,
                required=False,
                default=None,
                description="User metadata parameter",
            ),
        }

    def run(self, **kwargs) -> dict[str, Any]:
        """Return what was received."""
        return {
            "received_metadata": kwargs.get("metadata"),
            "has_metadata_param": "metadata" in kwargs,
            "node_metadata_name": self.metadata.name,  # Access internal NodeMetadata
        }


class TestNodeWithoutMetadataParam(Node):
    """Test node that does NOT use 'metadata' as parameter."""

    def get_parameters(self) -> dict[str, NodeParameter]:
        return {
            "id": NodeParameter(
                name="id", type=str, required=True, description="Required ID"
            )
        }

    def run(self, **kwargs) -> dict[str, Any]:
        return {"id": kwargs.get("id")}


class TestTypedNodeWithMetadataPort(TypedNode):
    """TypedNode with output port named 'metadata'."""

    # Input ports
    text_input = InputPort[str]("text_input", description="Text to process")

    # Output port named "metadata" (should not conflict with node.metadata)
    metadata = OutputPort[Dict[str, Any]]("metadata", description="Output metadata")

    def run(self, **kwargs) -> Dict[str, Any]:
        text = self.text_input.get()

        # Set the metadata OUTPUT PORT
        result_metadata = {"length": len(text), "text": text}
        self.metadata.set(result_metadata)

        return {
            "metadata": result_metadata,  # Output port value
            "node_internal_metadata": self._node_metadata.name,  # Internal NodeMetadata
        }


# Unit Tests


class TestMetadataParameterFix:
    """Test suite for metadata parameter naming collision fix."""

    @pytest.fixture(autouse=True)
    def register_nodes(self):
        """Register test nodes before each test."""
        NodeRegistry.register(TestNodeWithMetadataParam)
        NodeRegistry.register(TestNodeWithoutMetadataParam)
        NodeRegistry.register(TestTypedNodeWithMetadataPort)
        yield
        # Cleanup
        NodeRegistry.unregister("TestNodeWithMetadataParam")
        NodeRegistry.unregister("TestNodeWithoutMetadataParam")
        NodeRegistry.unregister("TestTypedNodeWithMetadataPort")

    def test_user_metadata_dict_is_passed_to_node(self):
        """Test that user's metadata dict parameter is passed through to node.run()."""
        workflow = WorkflowBuilder()
        workflow.add_node(
            "TestNodeWithMetadataParam",
            "test1",
            {"id": "test-1", "metadata": {"author": "Alice", "tags": ["tech"]}},
        )

        with LocalRuntime() as runtime:
            results, _ = runtime.execute(workflow.build())

        result = results["test1"]
        assert result["has_metadata_param"] is True
        assert result["received_metadata"] == {"author": "Alice", "tags": ["tech"]}

    def test_user_metadata_none_is_passed(self):
        """Test that explicit None for metadata parameter is passed through."""
        workflow = WorkflowBuilder()
        workflow.add_node(
            "TestNodeWithMetadataParam", "test2", {"id": "test-2", "metadata": None}
        )

        with LocalRuntime() as runtime:
            results, _ = runtime.execute(workflow.build())

        result = results["test2"]
        # When user explicitly provides None, it should be passed
        assert result["received_metadata"] is None

    def test_user_metadata_omitted_uses_default(self):
        """Test that omitted metadata parameter is not passed (uses default)."""
        workflow = WorkflowBuilder()
        workflow.add_node(
            "TestNodeWithMetadataParam",
            "test3",
            {
                "id": "test-3"
                # metadata omitted
            },
        )

        with LocalRuntime() as runtime:
            results, _ = runtime.execute(workflow.build())

        result = results["test3"]
        # When user omits parameter, it should not be in kwargs
        assert result["has_metadata_param"] is False
        assert result["received_metadata"] is None

    def test_backward_compat_node_metadata_property(self):
        """Test that node.metadata still returns NodeMetadata object."""
        node = TestNodeWithMetadataParam(id="test", metadata={"user": "data"})

        # Access via property should return NodeMetadata object
        assert isinstance(node.metadata, NodeMetadata)
        assert node.metadata.name == "TestNodeWithMetadataParam"

        # User parameter should be in config
        assert node.config.get("metadata") == {"user": "data"}

    def test_backward_compat_node_metadata_access(self):
        """Test that code accessing node.metadata.name etc still works."""
        node = TestNodeWithMetadataParam(
            name="CustomName", description="Test description", metadata={"user": "data"}
        )

        # These accesses should work via property
        assert node.metadata.name == "CustomName"
        assert node.metadata.description == "Test description"
        assert isinstance(node.metadata, NodeMetadata)

        # User parameter should be separate
        assert node.config.get("metadata") == {"user": "data"}

    def test_property_setter_with_nodemetadata(self):
        """Test that setting node.metadata with NodeMetadata object works."""
        node = TestNodeWithMetadataParam(id="test")

        # Set with NodeMetadata object
        custom_metadata = NodeMetadata(
            name="CustomNode", description="Custom description", version="2.0.0"
        )
        node.metadata = custom_metadata

        # Should route to _node_metadata
        assert node._node_metadata is custom_metadata
        assert node.metadata.name == "CustomNode"
        assert node.metadata.version == "2.0.0"

    def test_property_setter_with_dict(self):
        """Test that setting node.metadata with dict routes to config."""
        node = TestNodeWithMetadataParam(id="test")

        # Set with dict
        node.metadata = {"key": "value"}

        # Should route to config
        assert node.config["metadata"] == {"key": "value"}

        # Internal metadata should still be NodeMetadata
        assert isinstance(node._node_metadata, NodeMetadata)
        assert isinstance(
            node.metadata, NodeMetadata
        )  # Property returns _node_metadata

    def test_property_setter_with_invalid_type(self):
        """Test that setting node.metadata with invalid type raises TypeError."""
        node = TestNodeWithMetadataParam(id="test")

        with pytest.raises(TypeError) as exc_info:
            node.metadata = "invalid_string"

        assert "metadata must be NodeMetadata, dict, or None" in str(exc_info.value)

    def test_serialization_preserves_internal_metadata(self):
        """Test that to_dict() serializes internal NodeMetadata correctly."""
        node = TestNodeWithMetadataParam(
            name="TestNode", description="Test description", metadata={"user": "data"}
        )

        node_dict = node.to_dict()

        # Should serialize internal NodeMetadata
        assert "metadata" in node_dict
        assert node_dict["metadata"]["name"] == "TestNode"
        assert node_dict["metadata"]["description"] == "Test description"

        # User parameter should be in config
        assert node_dict["config"]["metadata"] == {"user": "data"}

    def test_serialization_roundtrip(self):
        """Test that serialization -> deserialization preserves user metadata parameter."""
        # Create node with user metadata
        node1 = TestNodeWithMetadataParam(
            name="OriginalNode", metadata={"user": "data", "tags": ["test"]}
        )

        # Serialize
        node_dict = node1.to_dict()

        # Deserialize - creates new node with same config
        NodeClass = NodeRegistry.get(node_dict["type"])
        node2 = NodeClass(**node_dict["config"])

        # Check that NodeMetadata is created (will have class name as default name)
        assert isinstance(node2.metadata, NodeMetadata)
        assert (
            node2.metadata.name == "TestNodeWithMetadataParam"
        )  # Uses class name by default

        # Check user parameter preserved in config
        assert node2.config.get("metadata") == {"user": "data", "tags": ["test"]}

    def test_typed_node_with_metadata_port(self):
        """Test that TypedNode can have a port named 'metadata' without conflicts."""
        workflow = WorkflowBuilder()
        workflow.add_node(
            "TestTypedNodeWithMetadataPort", "typed_test", {"text_input": "Hello World"}
        )

        with LocalRuntime() as runtime:
            results, _ = runtime.execute(workflow.build())

        result = results["typed_test"]

        # Output port "metadata" should work
        assert result["metadata"]["length"] == 11
        assert result["metadata"]["text"] == "Hello World"

        # Internal NodeMetadata should still be accessible
        assert result["node_internal_metadata"] == "TestTypedNodeWithMetadataPort"

    def test_node_without_metadata_param_unaffected(self):
        """Test that nodes without metadata parameter are unaffected."""
        node = TestNodeWithoutMetadataParam(id="test")

        # Should have internal NodeMetadata
        assert isinstance(node.metadata, NodeMetadata)
        assert node.metadata.name == "TestNodeWithoutMetadataParam"

        # Config should not have metadata
        assert "metadata" not in node.config

    def test_node_init_with_nodemetadata_object(self):
        """Test that passing NodeMetadata object during init works."""
        custom_metadata = NodeMetadata(
            name="CustomNode", description="Custom description"
        )

        node = TestNodeWithMetadataParam(
            id="test", metadata=custom_metadata  # Pass NodeMetadata object
        )

        # Should use the provided NodeMetadata
        assert node.metadata is custom_metadata
        assert node.metadata.name == "CustomNode"

        # Config should NOT have metadata (it's NodeMetadata, not user param)
        assert "metadata" not in node.config

    def test_workflow_execution_with_metadata_parameter(self):
        """E2E test: Full workflow execution with metadata parameter."""
        workflow = WorkflowBuilder()
        workflow.add_node(
            "TestNodeWithMetadataParam",
            "node1",
            {"id": "article-1", "metadata": {"author": "Alice", "category": "tech"}},
        )

        with LocalRuntime() as runtime:
            results, run_id = runtime.execute(workflow.build())

        assert run_id is not None
        assert "node1" in results

        result = results["node1"]
        assert result["received_metadata"] == {"author": "Alice", "category": "tech"}
        assert result["node_metadata_name"] == "TestNodeWithMetadataParam"

    def test_node_config_contains_user_metadata(self):
        """Test that node.config contains user's metadata parameter."""
        node = TestNodeWithMetadataParam(id="test", metadata={"key": "value"})

        # User parameter should be in config
        assert "metadata" in node.config
        assert node.config["metadata"] == {"key": "value"}

        # Internal metadata should be accessible via property
        assert isinstance(node.metadata, NodeMetadata)

    def test_node_config_does_not_contain_nodemetadata_object(self):
        """Test that NodeMetadata object is NOT stored in config."""
        custom_metadata = NodeMetadata(name="CustomNode")

        node = TestNodeWithMetadataParam(id="test", metadata=custom_metadata)

        # NodeMetadata should NOT be in config (it's internal)
        assert "metadata" not in node.config

        # But should be accessible via property
        assert node.metadata is custom_metadata


# Additional edge case tests


class TestMetadataEdgeCases:
    """Test edge cases and boundary conditions."""

    @pytest.fixture(autouse=True)
    def register_nodes(self):
        NodeRegistry.register(TestNodeWithMetadataParam)
        yield
        NodeRegistry.unregister("TestNodeWithMetadataParam")

    def test_both_name_and_user_metadata(self):
        """Test providing both NodeMetadata fields and user metadata dict."""
        node = TestNodeWithMetadataParam(
            name="CustomName",
            description="Custom description",
            metadata={"user": "data"},
        )

        # NodeMetadata fields should be set
        assert node.metadata.name == "CustomName"
        assert node.metadata.description == "Custom description"

        # User metadata should be in config
        assert node.config["metadata"] == {"user": "data"}

    def test_empty_dict_metadata(self):
        """Test that empty dict is passed as user parameter."""
        node = TestNodeWithMetadataParam(id="test", metadata={})

        assert node.config["metadata"] == {}
        assert isinstance(node.metadata, NodeMetadata)

    def test_nested_dict_metadata(self):
        """Test that nested dicts work as user parameters."""
        nested_data = {
            "author": {"name": "Alice", "email": "alice@example.com"},
            "tags": ["tech", "python"],
            "meta": {"version": 1},
        }

        node = TestNodeWithMetadataParam(id="test", metadata=nested_data)

        assert node.config["metadata"] == nested_data

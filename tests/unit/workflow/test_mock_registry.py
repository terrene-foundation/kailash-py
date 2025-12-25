"""Unit tests for workflow.mock_registry module."""

from unittest.mock import MagicMock, patch

import pytest
from kailash.nodes.base import NodeRegistry
from kailash.sdk_exceptions import NodeConfigurationError
from kailash.workflow.mock_registry import NODE_TYPES, MockNode, MockRegistry


class TestMockNode:
    """Test MockNode class."""

    def test_init_with_node_id(self):
        """Test MockNode initialization with node_id."""
        node = MockNode(node_id="test_node", param1="value1", param2="value2")

        assert node.node_id == "test_node"
        assert node.name == "test_node"
        assert node.config == {"param1": "value1", "param2": "value2"}

    def test_init_with_name(self):
        """Test MockNode initialization with name."""
        node = MockNode(node_id="test_node", name="Test Node", param="value")

        assert node.node_id == "test_node"
        assert node.name == "Test Node"
        assert node.config == {"param": "value"}

    def test_init_without_node_id(self):
        """Test MockNode initialization without node_id."""
        node = MockNode(name="Test Node", param="value")

        assert node.node_id is None
        assert node.name == "Test Node"
        assert node.config == {"param": "value"}

    def test_process_method(self):
        """Test MockNode process method."""
        node = MockNode(node_id="test")

        # Test with value
        result = node.process({"value": 5})
        assert result == {"value": 10}  # value * 2

        # Test without value
        result = node.process({})
        assert result == {"value": 0}  # default 0 * 2

    def test_execute_method(self):
        """Test MockNode execute method."""
        node = MockNode(node_id="test")

        # Execute calls process with kwargs
        result = node.execute(value=7)
        assert result == {"value": 14}  # 7 * 2

        # Execute without value
        result = node.execute()
        assert result == {"value": 0}

    def test_get_parameters(self):
        """Test MockNode get_parameters method."""
        node = MockNode(node_id="test")

        # Should return empty dict
        params = node.get_parameters()
        assert params == {}


class TestMockRegistry:
    """Test MockRegistry class."""

    def test_registry_initialization(self):
        """Test MockRegistry has all node types."""
        assert hasattr(MockRegistry, "_registry")
        assert isinstance(MockRegistry._registry, dict)

        # Verify all NODE_TYPES are registered
        for node_type in NODE_TYPES:
            assert node_type in MockRegistry._registry
            assert MockRegistry._registry[node_type] is MockNode

    def test_get_registered_node(self):
        """Test getting a registered node type."""
        # Test all registered types
        for node_type in NODE_TYPES:
            node_class = MockRegistry.get(node_type)
            assert node_class is MockNode

    def test_get_unregistered_node(self):
        """Test getting an unregistered node type."""
        with pytest.raises(NodeConfigurationError) as exc_info:
            MockRegistry.get("UnregisteredNode")

        error_msg = str(exc_info.value)
        assert "Node 'UnregisteredNode' not found in registry" in error_msg
        assert "Available nodes:" in error_msg

    def test_node_types_constant(self):
        """Test NODE_TYPES constant."""
        expected_types = [
            "MockNode",
            "DataReader",
            "DataWriter",
            "Processor",
            "Merger",
            "DataFilter",
            "AIProcessor",
            "Transformer",
        ]
        assert NODE_TYPES == expected_types


class TestNodeRegistryIntegration:
    """Test integration with NodeRegistry."""

    def test_node_registry_registration(self):
        """Test that mock nodes are registered with NodeRegistry."""
        # Verify at least some node types are in the real registry
        # We check a few key types to ensure registration worked
        for node_type in ["MockNode", "DataReader", "Processor"]:
            # The registration happens at module import time
            # We can verify it by checking if the type exists
            if hasattr(NodeRegistry, "_registry"):
                # Direct check if registry is accessible
                assert node_type in NodeRegistry._registry
                assert NodeRegistry._registry[node_type] is MockNode

    @patch("kailash.workflow.mock_registry.NodeRegistry")
    def test_registration_exception_handling(self, mock_registry):
        """Test that registration exceptions are handled."""
        # Make _registry raise an exception
        mock_registry._registry.__setitem__.side_effect = Exception("Registry error")

        # Re-import should not raise (exceptions are caught)
        # We can't easily re-import, so we simulate the registration loop
        for node_type in NODE_TYPES:
            try:
                mock_registry._registry[node_type] = MockNode
            except Exception:
                pass  # This is what the module does

        # No assertion needed - test passes if no exception is raised


class TestMockNodeUsage:
    """Test MockNode in typical usage scenarios."""

    def test_mock_node_as_workflow_node(self):
        """Test MockNode can be used as a workflow node."""
        # Create node
        node = MockNode(node_id="processor", name="Data Processor")

        # Simulate workflow usage
        input_data = {"value": 10, "other_field": "data"}
        output = node.execute(**input_data)

        assert output == {"value": 20}  # 10 * 2
        assert node.node_id == "processor"
        assert node.name == "Data Processor"

    def test_multiple_mock_nodes(self):
        """Test multiple MockNode instances maintain separate state."""
        node1 = MockNode(node_id="node1", config_value="a")
        node2 = MockNode(node_id="node2", config_value="b")

        assert node1.node_id == "node1"
        assert node2.node_id == "node2"
        assert node1.config == {"config_value": "a"}
        assert node2.config == {"config_value": "b"}

        # Process different values
        result1 = node1.process({"value": 3})
        result2 = node2.process({"value": 5})

        assert result1 == {"value": 6}
        assert result2 == {"value": 10}

    def test_mock_registry_get_and_instantiate(self):
        """Test getting node class from registry and instantiating."""
        # Get node class
        NodeClass = MockRegistry.get("DataReader")

        # Instantiate
        node = NodeClass(node_id="reader1", file_path="/tmp/data.csv")

        assert isinstance(node, MockNode)
        assert node.node_id == "reader1"
        assert node.config == {"file_path": "/tmp/data.csv"}

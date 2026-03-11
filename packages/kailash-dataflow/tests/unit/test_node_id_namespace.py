"""
Unit Tests for Node ID Namespace Separation

Tests the Core SDK fix for parameter namespace collision where WorkflowBuilder
previously injected id=node_id, causing conflicts with user data parameters.

Fix (implemented in Core SDK):
- Core SDK uses _node_id=node_id instead of id=node_id
- Node.id property maintains backward compatibility
- User's id parameter is never overwritten

BUG_005 Status: FIXED - Core SDK now injects _node_id, preserving user's 'id' param.
"""

import pytest
from kailash.nodes.base import Node, NodeParameter
from kailash.nodes.base_async import AsyncNode


class TestNodeIdInjection:
    """Test Node _node_id injection uses _node_id instead of id."""

    def test_node_receives_node_id_not_id(self):
        """
        Node.__init__ should accept _node_id kwarg and store it.

        This test verifies the Core SDK fix where _node_id is used
        instead of id to avoid namespace collision.
        """

        class TestNode(Node):
            def get_parameters(self):
                return {}

            def run(self, **kwargs):
                return kwargs

        # Simulate what WorkflowBuilder does: pass _node_id
        node = TestNode(_node_id="my_test_node")

        # CRITICAL ASSERTION: _node_id should be set
        assert hasattr(node, "_node_id"), (
            "Node should have _node_id attribute after injection. "
            "This is missing - Core SDK fix not applied."
        )
        assert (
            node._node_id == "my_test_node"
        ), f"Expected _node_id='my_test_node', got '{node._node_id}'"

        # CRITICAL ASSERTION: id should NOT be injected into config
        assert "id" not in node.config or node.config.get("id") is None, (
            "Node.config should NOT contain 'id' from _node_id injection. "
            f"Found: {node.config.get('id')}. This indicates namespace collision."
        )

    def test_user_id_parameter_not_overwritten(self):
        """
        User's id parameter should not be overwritten by _node_id.

        This is the CRITICAL test that demonstrates the bug and verifies the fix.
        User provides id=123 for their data, _node_id should NOT overwrite it.
        """

        class TestNode(Node):
            def get_parameters(self):
                return {
                    "id": NodeParameter(
                        name="id", type=int, required=True, description="User record ID"
                    )
                }

            def run(self, **kwargs):
                return kwargs

        user_id = 123

        # Simulate WorkflowBuilder: _node_id + user config
        node = TestNode(_node_id="my_node", id=user_id)

        # CRITICAL: User's id should be preserved in config
        assert "id" in node.config, "User's id parameter should be in node.config"
        assert node.config["id"] == user_id, (
            f"User's id should be {user_id}, not '{node.config['id']}'. "
            "This indicates the id was overwritten by node_id."
        )

        # Node identifier should be in _node_id, not id
        assert hasattr(
            node, "_node_id"
        ), "Node should have _node_id attribute for node identifier"
        assert (
            node._node_id == "my_node"
        ), f"Node identifier should be in _node_id, got '{node._node_id}'"

    def test_node_id_property_backward_compatibility(self):
        """
        node.id property should still work for backward compatibility.

        Existing code that accesses node.id should continue to work,
        even though internally we use _node_id.
        """

        class TestNode(Node):
            def get_parameters(self):
                return {}

            def run(self, **kwargs):
                return kwargs

        node = TestNode(_node_id="my_node_id")

        # BACKWARD COMPATIBILITY: node.id should still work
        assert hasattr(
            node, "id"
        ), "Node should have 'id' property for backward compatibility"

        # node.id should return the node identifier
        assert (
            node.id == "my_node_id"
        ), f"node.id should return node identifier 'my_node_id', got '{node.id}'"

        # Internally, _node_id should store the identifier
        assert hasattr(node, "_node_id"), "Node should use _node_id internally"
        assert (
            node._node_id == "my_node_id"
        ), f"_node_id should be 'my_node_id', got '{node._node_id}'"


class TestNodeMetadataUsesNodeId:
    """Test NodeMetadata references correct node identifier."""

    def test_node_metadata_uses_node_id_field(self):
        """
        NodeMetadata should reference _node_id, not id.

        Ensures internal metadata uses the correct node identifier field.
        """

        class TestNode(Node):
            def get_parameters(self):
                return {}

            def run(self, **kwargs):
                return kwargs

        node = TestNode(_node_id="metadata_test_node")

        # Check that metadata exists
        assert hasattr(node, "metadata"), "Node should have metadata attribute"

        # NodeMetadata should use _node_id internally (not id)
        assert hasattr(
            node, "_node_id"
        ), "Node should have _node_id for metadata reference"
        assert node._node_id == "metadata_test_node"

    def test_node_metadata_with_user_id_parameter(self):
        """
        NodeMetadata should work correctly when user provides id parameter.

        This tests that metadata and user parameters coexist without collision.
        """

        class TestNode(Node):
            def get_parameters(self):
                return {
                    "id": NodeParameter(
                        name="id", type=str, required=True, description="User record ID"
                    )
                }

            def run(self, **kwargs):
                return kwargs

        user_id = "user-record-12345"

        node = TestNode(_node_id="node_with_user_id", id=user_id)

        # User's id should be in config
        assert (
            node.config.get("id") == user_id
        ), f"User id should be '{user_id}', got '{node.config.get('id')}'"

        # Node identifier should be separate in _node_id
        assert (
            node._node_id == "node_with_user_id"
        ), f"Node identifier should be 'node_with_user_id', got '{node._node_id}'"

        # Metadata should still work correctly
        assert hasattr(node, "metadata"), "Node should have metadata"


class TestAsyncNodeIdNamespace:
    """Test AsyncNode also uses _node_id (not just base Node)."""

    def test_async_node_uses_node_id_field(self):
        """
        AsyncNode should also use _node_id for node identifier.

        Ensures the fix applies to both sync and async nodes.
        """

        class TestAsyncNode(AsyncNode):
            def get_parameters(self):
                return {}

            async def async_run(self, **kwargs):
                return kwargs

            def run(self, **kwargs):
                return kwargs

        node = TestAsyncNode(_node_id="async_node_id")

        # AsyncNode should use _node_id
        assert hasattr(node, "_node_id"), "AsyncNode should have _node_id attribute"
        assert (
            node._node_id == "async_node_id"
        ), f"AsyncNode _node_id should be 'async_node_id', got '{node._node_id}'"

        # User's id parameter should not be present
        assert (
            "id" not in node.config or node.config.get("id") is None
        ), "AsyncNode config should not have id from injection"

    def test_async_node_with_user_id_parameter(self):
        """
        AsyncNode should preserve user's id parameter.

        Tests that async nodes handle user id parameters correctly.
        """

        class TestAsyncNode(AsyncNode):
            def get_parameters(self):
                return {
                    "id": NodeParameter(
                        name="id", type=int, required=True, description="Record ID"
                    )
                }

            async def async_run(self, **kwargs):
                return kwargs

            def run(self, **kwargs):
                return kwargs

        user_id = 999

        node = TestAsyncNode(_node_id="async_with_id", id=user_id)

        # User's id should be preserved
        assert (
            node.config.get("id") == user_id
        ), f"User id should be {user_id}, got '{node.config.get('id')}'"

        # Node identifier in _node_id
        assert (
            node._node_id == "async_with_id"
        ), f"Node identifier should be 'async_with_id', got '{node._node_id}'"


class TestEdgeCases:
    """Test edge cases for node ID namespace separation."""

    def test_node_without_user_id_parameter(self):
        """
        Node without user id parameter should still work.

        Ensures fix doesn't break nodes that don't use id parameter.
        """

        class SimpleNode(Node):
            def get_parameters(self):
                return {
                    "name": NodeParameter(
                        name="name", type=str, required=True, description="Name field"
                    )
                }

            def run(self, **kwargs):
                return kwargs

        node = SimpleNode(_node_id="simple_node", name="test")

        # Should have _node_id
        assert hasattr(node, "_node_id"), "Node should have _node_id"
        assert node._node_id == "simple_node"

        # Should have user's name parameter
        assert node.config.get("name") == "test"

        # Should NOT have id in config
        assert "id" not in node.config or node.config.get("id") is None

    def test_multiple_nodes_with_different_ids(self):
        """
        Multiple nodes with different user id parameters should not conflict.

        Tests that the fix correctly isolates id parameters across nodes.
        """

        class IdNode(Node):
            def get_parameters(self):
                return {
                    "id": NodeParameter(
                        name="id", type=int, required=True, description="Record ID"
                    )
                }

            def run(self, **kwargs):
                return kwargs

        node1 = IdNode(_node_id="node1", id=100)
        node2 = IdNode(_node_id="node2", id=200)
        node3 = IdNode(_node_id="node3", id=300)

        # Each node should have correct user id
        assert node1.config["id"] == 100
        assert node2.config["id"] == 200
        assert node3.config["id"] == 300

        # Each node should have correct _node_id
        assert node1._node_id == "node1"
        assert node2._node_id == "node2"
        assert node3._node_id == "node3"

    def test_node_id_string_vs_int_types(self):
        """
        Node identifier (string) should not interfere with user id (int).

        Tests type isolation between node identifier and user id parameter.
        """

        class TypedIdNode(Node):
            def get_parameters(self):
                return {
                    "id": NodeParameter(
                        name="id",
                        type=int,
                        required=True,
                        description="Integer record ID",
                    )
                }

            def run(self, **kwargs):
                return kwargs

        user_id_int = 12345
        node_id_str = "string_node_identifier"

        node = TypedIdNode(_node_id=node_id_str, id=user_id_int)

        # User id should be int
        assert isinstance(
            node.config["id"], int
        ), f"User id should be int, got {type(node.config['id'])}"
        assert node.config["id"] == user_id_int

        # Node identifier should be string in _node_id
        assert isinstance(
            node._node_id, str
        ), f"Node identifier should be string, got {type(node._node_id)}"
        assert node._node_id == node_id_str


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])

"""
Tier 1 Unit Tests: UpsertNode Generation

Test that UpsertNode is generated during model registration with correct parameters.
Fast (<1s), isolated, can use mocks, no external dependencies.

Following DataFlow TDD gold standards:
- Test node generation
- Test parameter definitions
- Test naming conventions
- Test node class structure
"""

import pytest

from dataflow import DataFlow


class TestUpsertNodeGeneration:
    """Test UpsertNode is generated correctly during model registration."""

    def test_upsert_node_generated_in_model_registration(self):
        """Verify UpsertNode is generated when model is registered."""
        # Arrange: Create DataFlow instance with in-memory database
        db = DataFlow(":memory:")

        # Act: Register a model
        @db.model
        class User:
            id: str
            email: str
            name: str

        # Assert: UpsertNode should be in generated nodes
        assert "UserUpsertNode" in db._nodes, (
            "UserUpsertNode should be auto-generated when model is registered. "
            f"Available nodes: {list(db._nodes.keys())}"
        )

    def test_upsert_node_naming_convention(self):
        """Verify UpsertNode follows ModelOperationNode naming convention."""
        # Arrange
        db = DataFlow(":memory:")

        # Act
        @db.model
        class Product:
            id: str
            sku: str
            name: str

        # Assert: Node name should be ProductUpsertNode
        assert (
            "ProductUpsertNode" in db._nodes
        ), "UpsertNode should follow ModelOperationNode naming convention"

        # Verify the node class has correct attributes
        node_class = db._nodes["ProductUpsertNode"]
        assert node_class is not None
        assert hasattr(node_class, "__name__")

    def test_upsert_node_has_correct_parameters(self):
        """Verify UpsertNode has where, update, create parameters."""
        # Arrange
        db = DataFlow(":memory:")

        @db.model
        class User:
            id: str
            email: str
            name: str

        # Act: Instantiate the node
        node_class = db._nodes["UserUpsertNode"]
        node = node_class()

        # Get parameters
        params = node.get_parameters()

        # Assert: Should have where, update, create parameters
        assert "where" in params, "UpsertNode should have 'where' parameter for lookup"
        assert (
            "update" in params
        ), "UpsertNode should have 'update' parameter for existing records"
        assert (
            "create" in params
        ), "UpsertNode should have 'create' parameter for new records"

    def test_upsert_node_parameter_types(self):
        """Verify UpsertNode parameters have correct types."""
        # Arrange
        db = DataFlow(":memory:")

        @db.model
        class User:
            id: str
            email: str
            name: str

        # Act
        node_class = db._nodes["UserUpsertNode"]
        node = node_class()
        params = node.get_parameters()

        # Assert: Parameter types should be dict
        assert params["where"].type == dict, "'where' should be dict type"
        assert params["update"].type == dict, "'update' should be dict type"
        assert params["create"].type == dict, "'create' should be dict type"

    def test_upsert_node_parameter_requirements(self):
        """Verify UpsertNode parameter requirements."""
        # Arrange
        db = DataFlow(":memory:")

        @db.model
        class User:
            id: str
            email: str
            name: str

        # Act
        node_class = db._nodes["UserUpsertNode"]
        node = node_class()
        params = node.get_parameters()

        # Assert: where should be required, update/create can be optional
        # (at least one of update or create must be provided, validated at runtime)
        assert params["where"].required is True, "'where' parameter should be required"
        # update and create can be optional but at least one must be provided

    def test_upsert_node_bound_to_correct_dataflow_instance(self):
        """Verify UpsertNode is bound to correct DataFlow instance (multi-instance isolation)."""
        # Arrange: Create two separate DataFlow instances
        db1 = DataFlow(":memory:")
        db2 = DataFlow(":memory:")

        @db1.model
        class User:
            id: str
            name: str

        @db2.model
        class User:  # Same model name, different instance
            id: str
            email: str

        # Act: Instantiate nodes from each instance
        node1_class = db1._nodes["UserUpsertNode"]
        node2_class = db2._nodes["UserUpsertNode"]

        node1 = node1_class()
        node2 = node2_class()

        # Assert: Each node should be bound to its respective DataFlow instance
        assert (
            node1.dataflow_instance is db1
        ), "Node from db1 should be bound to db1 instance"
        assert (
            node2.dataflow_instance is db2
        ), "Node from db2 should be bound to db2 instance"

    def test_upsert_node_count_per_model(self):
        """Verify 11 nodes are generated per model (7 CRUD + 4 bulk)."""
        # Arrange
        db = DataFlow(":memory:")

        # Act
        @db.model
        class User:
            id: str
            name: str

        # Assert: Should have exactly 11 nodes
        expected_nodes = [
            "UserCreateNode",
            "UserReadNode",
            "UserUpdateNode",
            "UserDeleteNode",
            "UserListNode",
            "UserUpsertNode",
            "UserCountNode",
            "UserBulkCreateNode",
            "UserBulkUpdateNode",
            "UserBulkDeleteNode",
            "UserBulkUpsertNode",
        ]

        for node_name in expected_nodes:
            assert node_name in db._nodes, (
                f"{node_name} should be generated. "
                f"Available nodes: {list(db._nodes.keys())}"
            )

        # Count user-related nodes (should be 11: 7 CRUD + 4 Bulk)
        user_nodes = [name for name in db._nodes.keys() if name.startswith("User")]
        assert (
            len(user_nodes) == 11
        ), f"Should have exactly 11 nodes per model (7 CRUD + 4 Bulk), got {len(user_nodes)}: {user_nodes}"

    def test_upsert_node_operation_attribute(self):
        """Verify UpsertNode has correct operation attribute."""
        # Arrange
        db = DataFlow(":memory:")

        @db.model
        class User:
            id: str
            name: str

        # Act
        node_class = db._nodes["UserUpsertNode"]
        node = node_class()

        # Assert: operation should be "upsert"
        assert hasattr(node, "operation"), "Node should have operation attribute"
        assert (
            node.operation == "upsert"
        ), f"Operation should be 'upsert', got '{node.operation}'"

    def test_upsert_node_model_name_attribute(self):
        """Verify UpsertNode has correct model_name attribute."""
        # Arrange
        db = DataFlow(":memory:")

        @db.model
        class Product:
            id: str
            sku: str

        # Act
        node_class = db._nodes["ProductUpsertNode"]
        node = node_class()

        # Assert: model_name should match registered model
        assert hasattr(node, "model_name"), "Node should have model_name attribute"
        assert (
            node.model_name == "Product"
        ), f"model_name should be 'Product', got '{node.model_name}'"

    def test_upsert_node_database_url_parameter(self):
        """Verify UpsertNode has database_url parameter for connection override."""
        # Arrange
        db = DataFlow(":memory:")

        @db.model
        class User:
            id: str
            name: str

        # Act
        node_class = db._nodes["UserUpsertNode"]
        node = node_class()
        params = node.get_parameters()

        # Assert: Should have database_url parameter
        assert (
            "database_url" in params
        ), "UpsertNode should have 'database_url' parameter for connection override"
        assert (
            params["database_url"].required is False
        ), "database_url should be optional (uses instance default if not provided)"

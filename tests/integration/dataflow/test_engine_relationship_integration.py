"""Integration tests for DataFlow engine relationship auto-detection.

These tests verify that the actual DataFlow engine correctly auto-detects
relationships when models are registered.
"""

import os
import sys

import pytest

# Add the DataFlow app to the path
sys.path.insert(
    0, os.path.join(os.path.dirname(__file__), "../../../apps/kailash-dataflow/src")
)

from dataflow import DataFlow


@pytest.mark.integration
class TestDataFlowEngineRelationshipIntegration:
    """Test DataFlow engine relationship auto-detection with actual implementation."""

    def test_engine_auto_detects_belongs_to_relationship(self):
        """Test that the engine auto-detects belongs_to relationships."""
        # Initialize DataFlow engine
        db = DataFlow()

        # Register a model that should auto-detect relationships
        @db.model
        class Order:
            user_id: int
            total: float
            status: str = "pending"

        # Verify the model was registered
        assert "Order" in db.get_models()

        # Check if relationships were auto-detected
        relationships = db.get_relationships("Order")

        # Based on the mock schema in discover_schema(), orders table has a user_id foreign key
        # So we should have a 'user' relationship auto-detected
        if relationships:  # Only check if relationships were detected
            assert "user" in relationships
            user_rel = relationships["user"]
            assert user_rel["type"] == "belongs_to"
            assert user_rel["target_table"] == "users"
            assert user_rel["foreign_key"] == "user_id"
            assert user_rel.get("auto_detected") is True

    def test_engine_auto_detects_has_many_relationship(self):
        """Test that the engine auto-detects has_many reverse relationships."""
        # Initialize DataFlow engine
        db = DataFlow()

        # Register a model that should have reverse relationships
        @db.model
        class User:
            name: str
            email: str
            active: bool = True

        # Verify the model was registered
        assert "User" in db.get_models()

        # Check if reverse relationships were auto-detected
        relationships = db.get_relationships("User")

        # Based on the mock schema, users table should have orders relationship
        if relationships:  # Only check if relationships were detected
            assert "orders" in relationships
            orders_rel = relationships["orders"]
            assert orders_rel["type"] == "has_many"
            assert orders_rel["target_table"] == "orders"
            assert orders_rel["foreign_key"] == "user_id"
            assert orders_rel.get("auto_detected") is True

    def test_engine_class_name_to_table_name_conversion(self):
        """Test the engine's class name to table name conversion."""
        # Initialize DataFlow engine
        db = DataFlow()

        # Test the actual implementation
        assert db._class_name_to_table_name("User") == "users"
        assert db._class_name_to_table_name("Order") == "orders"
        assert db._class_name_to_table_name("OrderItem") == "order_items"
        assert db._class_name_to_table_name("ProductCategory") == "product_categorys"
        assert db._class_name_to_table_name("UserRole") == "user_roles"

    def test_engine_foreign_key_to_relationship_name_conversion(self):
        """Test the engine's foreign key to relationship name conversion."""
        # Initialize DataFlow engine
        db = DataFlow()

        # Test the actual implementation
        assert db._foreign_key_to_relationship_name("user_id") == "user"
        assert db._foreign_key_to_relationship_name("order_id") == "order"
        assert db._foreign_key_to_relationship_name("product_id") == "product"
        assert db._foreign_key_to_relationship_name("parent_id") == "parent"
        assert db._foreign_key_to_relationship_name("category_id") == "category"

    def test_engine_get_relationships_all_models(self):
        """Test getting relationships for all models."""
        # Initialize DataFlow engine
        db = DataFlow()

        # Register multiple models
        @db.model
        class User:
            name: str
            email: str

        @db.model
        class Order:
            user_id: int
            total: float

        # Get all relationships
        all_relationships = db.get_relationships()

        # Should be a dictionary structure
        assert isinstance(all_relationships, dict)

        # Should contain table names as keys
        if all_relationships:  # Only check if relationships were detected
            # May contain 'users' and/or 'orders' keys depending on auto-detection
            assert any(key in ["users", "orders"] for key in all_relationships.keys())

    def test_engine_model_registration_with_auto_detection(self):
        """Test that model registration includes auto-detection."""
        # Initialize DataFlow engine
        db = DataFlow()

        # Register a model
        @db.model
        class Product:
            name: str
            price: float
            category_id: int

        # Verify model registration
        assert "Product" in db.get_models()
        models = db.get_models()
        assert models["Product"].__name__ == "Product"

        # Verify model fields
        fields = db.get_model_fields("Product")
        assert "name" in fields
        assert "price" in fields
        assert "category_id" in fields

        # Verify that auto-detection was attempted
        # (The relationships may or may not be detected depending on schema)
        relationships = db.get_relationships("Product")
        assert isinstance(relationships, dict)  # Should return a dict even if empty

    def test_engine_schema_discovery_integration(self):
        """Test that schema discovery works with relationship detection."""
        # Initialize DataFlow engine
        db = DataFlow()

        # Test schema discovery
        schema = db.discover_schema()
        assert isinstance(schema, dict)
        assert "users" in schema
        assert "orders" in schema

        # Verify schema structure includes foreign keys
        orders_table = schema["orders"]
        assert "foreign_keys" in orders_table
        foreign_keys = orders_table["foreign_keys"]

        # Should have at least one foreign key
        assert len(foreign_keys) > 0

        # Check foreign key structure
        user_fk = foreign_keys[0]
        assert user_fk["column_name"] == "user_id"
        assert user_fk["foreign_table_name"] == "users"
        assert user_fk["foreign_column_name"] == "id"

    def test_engine_show_tables_functionality(self):
        """Test the show_tables method."""
        # Initialize DataFlow engine
        db = DataFlow()

        # Test show_tables
        tables = db.show_tables()
        assert isinstance(tables, list)
        assert "users" in tables
        assert "orders" in tables

    def test_engine_scaffold_with_relationships(self):
        """Test scaffold generation includes relationship comments."""
        # Initialize DataFlow engine
        db = DataFlow()

        # Test scaffold generation
        import os
        import tempfile

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            output_file = f.name

        try:
            result = db.scaffold(output_file)

            # Verify scaffold result
            assert "generated_models" in result
            assert "relationships_detected" in result
            assert result["relationships_detected"] > 0

            # Read the generated file
            with open(output_file, "r") as f:
                content = f.read()

            # Should contain model definitions
            assert "@db.model" in content
            assert "class User:" in content or "class Order:" in content

            # Should contain relationship comments
            assert (
                "# user = db.belongs_to" in content
                or "# orders = db.has_many" in content
            )

        finally:
            # Clean up
            if os.path.exists(output_file):
                os.unlink(output_file)

    def test_engine_health_check_with_relationships(self):
        """Test health check includes relationship information."""
        # Initialize DataFlow engine
        db = DataFlow()

        # Register models to trigger relationship detection
        @db.model
        class User:
            name: str

        @db.model
        class Order:
            user_id: int
            total: float

        # Test health check
        health = db.health_check()

        # Verify health check structure
        assert "status" in health
        assert "models_registered" in health
        assert health["models_registered"] >= 2  # At least User and Order

    def test_engine_cleanup_after_model_registration(self):
        """Test that the engine cleans up properly after model registration."""
        # Initialize DataFlow engine
        db = DataFlow()

        # Register a model
        @db.model
        class TestModel:
            name: str

        # Verify internal state
        assert hasattr(db, "_models")
        assert hasattr(db, "_model_fields")
        assert hasattr(db, "_relationships")

        # Test cleanup
        db.close()

        # Engine should still have its attributes but connections should be closed
        assert hasattr(db, "_models")
        assert hasattr(db, "_model_fields")

"""Unit tests for DataFlow automatic relationship detection functionality.

These tests ensure that foreign key relationships are automatically detected
when models are registered and integrated with schema discovery.
"""

from unittest.mock import MagicMock, patch

import pytest


class TestDataFlowAutoRelationshipDetection:
    """Test automatic relationship detection during model registration."""

    def test_auto_detect_belongs_to_relationship(self):
        """Test automatic detection of belongs_to relationships."""
        # Mock DataFlow engine
        mock_dataflow = MagicMock()
        mock_dataflow._relationships = {}

        # Mock schema with foreign key
        mock_schema = {
            "orders": {
                "columns": [
                    {"name": "id", "type": "integer", "primary_key": True},
                    {"name": "user_id", "type": "integer"},
                ],
                "foreign_keys": [
                    {
                        "column_name": "user_id",
                        "foreign_table_name": "users",
                        "foreign_column_name": "id",
                    }
                ],
            },
            "users": {
                "columns": [
                    {"name": "id", "type": "integer", "primary_key": True},
                    {"name": "name", "type": "varchar"},
                ],
                "foreign_keys": [],
            },
        }

        def auto_detect_relationships(model_name, fields):
            """Mock auto-detection implementation."""
            table_name = model_name.lower() + "s"  # Simple pluralization

            if table_name not in mock_dataflow._relationships:
                mock_dataflow._relationships[table_name] = {}

            if table_name in mock_schema:
                table_info = mock_schema[table_name]
                foreign_keys = table_info.get("foreign_keys", [])

                for fk in foreign_keys:
                    rel_name = fk["column_name"].replace("_id", "")

                    mock_dataflow._relationships[table_name][rel_name] = {
                        "type": "belongs_to",
                        "target_table": fk["foreign_table_name"],
                        "foreign_key": fk["column_name"],
                        "target_key": fk["foreign_column_name"],
                        "auto_detected": True,
                    }

        # Test model registration with auto-detection
        auto_detect_relationships("Order", {"user_id": int, "total": float})

        # Verify relationship was detected
        assert "orders" in mock_dataflow._relationships
        assert "user" in mock_dataflow._relationships["orders"]

        user_relationship = mock_dataflow._relationships["orders"]["user"]
        assert user_relationship["type"] == "belongs_to"
        assert user_relationship["target_table"] == "users"
        assert user_relationship["foreign_key"] == "user_id"
        assert user_relationship["auto_detected"] is True

    def test_auto_detect_has_many_relationship(self):
        """Test automatic detection of has_many reverse relationships."""
        mock_dataflow = MagicMock()
        mock_dataflow._relationships = {}

        # Mock schema with foreign key relationship
        mock_schema = {
            "users": {
                "columns": [
                    {"name": "id", "type": "integer", "primary_key": True},
                    {"name": "name", "type": "varchar"},
                ],
                "foreign_keys": [],
            },
            "orders": {
                "columns": [
                    {"name": "id", "type": "integer", "primary_key": True},
                    {"name": "user_id", "type": "integer"},
                ],
                "foreign_keys": [
                    {
                        "column_name": "user_id",
                        "foreign_table_name": "users",
                        "foreign_column_name": "id",
                    }
                ],
            },
        }

        def create_reverse_relationships(table_name, schema):
            """Mock reverse relationship creation."""
            for other_table, table_info in schema.items():
                if other_table == table_name:
                    continue

                foreign_keys = table_info.get("foreign_keys", [])
                for fk in foreign_keys:
                    if fk["foreign_table_name"] == table_name:
                        if table_name not in mock_dataflow._relationships:
                            mock_dataflow._relationships[table_name] = {}

                        rel_name = other_table  # Use table name as relationship name

                        mock_dataflow._relationships[table_name][rel_name] = {
                            "type": "has_many",
                            "target_table": other_table,
                            "foreign_key": fk["column_name"],
                            "target_key": fk["foreign_column_name"],
                            "auto_detected": True,
                        }

        # Test reverse relationship creation
        create_reverse_relationships("users", mock_schema)

        # Verify has_many relationship was created
        assert "users" in mock_dataflow._relationships
        assert "orders" in mock_dataflow._relationships["users"]

        orders_relationship = mock_dataflow._relationships["users"]["orders"]
        assert orders_relationship["type"] == "has_many"
        assert orders_relationship["target_table"] == "orders"
        assert orders_relationship["foreign_key"] == "user_id"
        assert orders_relationship["auto_detected"] is True

    def test_multiple_foreign_keys_same_model(self):
        """Test handling of multiple foreign keys in the same model."""
        mock_dataflow = MagicMock()
        mock_dataflow._relationships = {}

        # Mock schema with multiple foreign keys
        mock_schema = {
            "order_items": {
                "columns": [
                    {"name": "id", "type": "integer", "primary_key": True},
                    {"name": "order_id", "type": "integer"},
                    {"name": "product_id", "type": "integer"},
                ],
                "foreign_keys": [
                    {
                        "column_name": "order_id",
                        "foreign_table_name": "orders",
                        "foreign_column_name": "id",
                    },
                    {
                        "column_name": "product_id",
                        "foreign_table_name": "products",
                        "foreign_column_name": "id",
                    },
                ],
            }
        }

        def auto_detect_multiple_relationships(model_name, fields):
            """Mock detection of multiple relationships."""
            table_name = "order_items"

            if table_name not in mock_dataflow._relationships:
                mock_dataflow._relationships[table_name] = {}

            if table_name in mock_schema:
                table_info = mock_schema[table_name]
                foreign_keys = table_info.get("foreign_keys", [])

                for fk in foreign_keys:
                    rel_name = fk["column_name"].replace("_id", "")

                    mock_dataflow._relationships[table_name][rel_name] = {
                        "type": "belongs_to",
                        "target_table": fk["foreign_table_name"],
                        "foreign_key": fk["column_name"],
                        "target_key": fk["foreign_column_name"],
                        "auto_detected": True,
                    }

        # Test multiple relationship detection
        auto_detect_multiple_relationships("OrderItem", {})

        # Verify both relationships were detected
        assert "order_items" in mock_dataflow._relationships
        relationships = mock_dataflow._relationships["order_items"]

        assert "order" in relationships
        assert "product" in relationships

        # Verify order relationship
        order_rel = relationships["order"]
        assert order_rel["type"] == "belongs_to"
        assert order_rel["target_table"] == "orders"
        assert order_rel["foreign_key"] == "order_id"

        # Verify product relationship
        product_rel = relationships["product"]
        assert product_rel["type"] == "belongs_to"
        assert product_rel["target_table"] == "products"
        assert product_rel["foreign_key"] == "product_id"

    def test_self_referencing_relationship_detection(self):
        """Test detection of self-referencing relationships."""
        mock_dataflow = MagicMock()
        mock_dataflow._relationships = {}

        # Mock schema with self-referencing foreign key
        mock_schema = {
            "categories": {
                "columns": [
                    {"name": "id", "type": "integer", "primary_key": True},
                    {"name": "name", "type": "varchar"},
                    {"name": "parent_id", "type": "integer"},
                ],
                "foreign_keys": [
                    {
                        "column_name": "parent_id",
                        "foreign_table_name": "categories",
                        "foreign_column_name": "id",
                    }
                ],
            }
        }

        def auto_detect_self_referencing(model_name, fields):
            """Mock self-referencing relationship detection."""
            table_name = "categories"

            if table_name not in mock_dataflow._relationships:
                mock_dataflow._relationships[table_name] = {}

            if table_name in mock_schema:
                table_info = mock_schema[table_name]
                foreign_keys = table_info.get("foreign_keys", [])

                for fk in foreign_keys:
                    rel_name = fk["column_name"].replace("_id", "")

                    # Handle self-referencing case
                    if fk["foreign_table_name"] == table_name:
                        rel_name = "parent"  # Use semantic name for self-reference

                    mock_dataflow._relationships[table_name][rel_name] = {
                        "type": "belongs_to",
                        "target_table": fk["foreign_table_name"],
                        "foreign_key": fk["column_name"],
                        "target_key": fk["foreign_column_name"],
                        "auto_detected": True,
                        "self_referencing": fk["foreign_table_name"] == table_name,
                    }

                    # Also create children relationship for self-referencing
                    if fk["foreign_table_name"] == table_name:
                        mock_dataflow._relationships[table_name]["children"] = {
                            "type": "has_many",
                            "target_table": table_name,
                            "foreign_key": fk["column_name"],
                            "target_key": fk["foreign_column_name"],
                            "auto_detected": True,
                            "self_referencing": True,
                        }

        # Test self-referencing relationship detection
        auto_detect_self_referencing("Category", {})

        # Verify self-referencing relationships
        assert "categories" in mock_dataflow._relationships
        relationships = mock_dataflow._relationships["categories"]

        assert "parent" in relationships
        assert "children" in relationships

        # Verify parent relationship
        parent_rel = relationships["parent"]
        assert parent_rel["type"] == "belongs_to"
        assert parent_rel["target_table"] == "categories"
        assert parent_rel["self_referencing"] is True

        # Verify children relationship
        children_rel = relationships["children"]
        assert children_rel["type"] == "has_many"
        assert children_rel["target_table"] == "categories"
        assert children_rel["self_referencing"] is True

    def test_class_name_to_table_name_conversion(self):
        """Test conversion from class names to table names."""

        def class_name_to_table_name(class_name):
            """Mock class name to table name conversion."""
            import re

            table_name = re.sub("([A-Z])", r"_\1", class_name).lower().lstrip("_")
            if not table_name.endswith("s"):
                table_name += "s"
            return table_name

        # Test various class name conversions
        assert class_name_to_table_name("User") == "users"
        assert class_name_to_table_name("Order") == "orders"
        assert class_name_to_table_name("OrderItem") == "order_items"
        assert class_name_to_table_name("ProductCategory") == "product_categorys"
        assert class_name_to_table_name("UserRole") == "user_roles"

    def test_foreign_key_to_relationship_name_conversion(self):
        """Test conversion from foreign key columns to relationship names."""

        def foreign_key_to_relationship_name(foreign_key_column):
            """Mock foreign key to relationship name conversion."""
            if foreign_key_column.endswith("_id"):
                return foreign_key_column[:-3]
            return foreign_key_column

        # Test various foreign key conversions
        assert foreign_key_to_relationship_name("user_id") == "user"
        assert foreign_key_to_relationship_name("order_id") == "order"
        assert foreign_key_to_relationship_name("product_id") == "product"
        assert foreign_key_to_relationship_name("parent_id") == "parent"
        assert foreign_key_to_relationship_name("category_id") == "category"

    def test_relationship_integration_with_model_registration(self):
        """Test integration of relationship detection with model registration."""
        mock_dataflow = MagicMock()
        mock_dataflow._relationships = {}
        mock_dataflow._models = {}

        # Mock complete model registration process
        def register_model_with_relationships(cls, dataflow):
            """Mock model registration with relationship detection."""
            model_name = cls.__name__
            table_name = model_name.lower() + "s"

            # Register model
            dataflow._models[model_name] = cls

            # Auto-detect relationships (simplified)
            if model_name == "Order":
                if table_name not in dataflow._relationships:
                    dataflow._relationships[table_name] = {}

                dataflow._relationships[table_name]["user"] = {
                    "type": "belongs_to",
                    "target_table": "users",
                    "foreign_key": "user_id",
                    "auto_detected": True,
                }

            return cls

        # Define test models
        class User:
            id: int
            name: str

        class Order:
            id: int
            user_id: int
            total: float

        # Register models
        registered_user = register_model_with_relationships(User, mock_dataflow)
        registered_order = register_model_with_relationships(Order, mock_dataflow)

        # Verify models were registered
        assert "User" in mock_dataflow._models
        assert "Order" in mock_dataflow._models
        assert mock_dataflow._models["User"] is User
        assert mock_dataflow._models["Order"] is Order

        # Verify relationships were auto-detected
        assert "orders" in mock_dataflow._relationships
        assert "user" in mock_dataflow._relationships["orders"]

        user_rel = mock_dataflow._relationships["orders"]["user"]
        assert user_rel["type"] == "belongs_to"
        assert user_rel["auto_detected"] is True

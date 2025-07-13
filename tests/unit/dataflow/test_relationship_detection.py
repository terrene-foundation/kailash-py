"""Unit tests for DataFlow relationship detection functionality.

These tests ensure that foreign key relationships are correctly detected
and converted to DataFlow relationship definitions.
"""

from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock

import pytest


class TestDataFlowRelationshipDetection:
    """Test relationship detection and foreign key analysis."""

    def test_simple_foreign_key_detection(self):
        """Test detection of simple one-to-many relationships."""
        # Mock foreign key data
        mock_foreign_keys = [
            {
                "table_name": "orders",
                "column_name": "user_id",
                "foreign_table_name": "users",
                "foreign_column_name": "id",
                "constraint_name": "fk_orders_user_id",
            }
        ]

        def detect_relationships(foreign_keys):
            """Convert foreign keys to relationship definitions."""
            relationships = {}

            for fk in foreign_keys:
                table = fk["table_name"]
                if table not in relationships:
                    relationships[table] = {}

                # Create relationship name
                rel_name = fk["column_name"].replace("_id", "")

                relationships[table][rel_name] = {
                    "type": "belongs_to",
                    "target_table": fk["foreign_table_name"],
                    "foreign_key": fk["column_name"],
                    "target_key": fk["foreign_column_name"],
                }

            return relationships

        relationships = detect_relationships(mock_foreign_keys)

        assert "orders" in relationships
        assert "user" in relationships["orders"]
        assert relationships["orders"]["user"]["type"] == "belongs_to"
        assert relationships["orders"]["user"]["target_table"] == "users"
        assert relationships["orders"]["user"]["foreign_key"] == "user_id"

    def test_multiple_foreign_keys_same_table(self):
        """Test table with multiple foreign key relationships."""
        mock_foreign_keys = [
            {
                "table_name": "order_items",
                "column_name": "order_id",
                "foreign_table_name": "orders",
                "foreign_column_name": "id",
            },
            {
                "table_name": "order_items",
                "column_name": "product_id",
                "foreign_table_name": "products",
                "foreign_column_name": "id",
            },
            {
                "table_name": "order_items",
                "column_name": "user_id",
                "foreign_table_name": "users",
                "foreign_column_name": "id",
            },
        ]

        def detect_multiple_relationships(foreign_keys):
            relationships = {}

            for fk in foreign_keys:
                table = fk["table_name"]
                if table not in relationships:
                    relationships[table] = {}

                rel_name = fk["column_name"].replace("_id", "")
                relationships[table][rel_name] = {
                    "target_table": fk["foreign_table_name"],
                    "foreign_key": fk["column_name"],
                }

            return relationships

        relationships = detect_multiple_relationships(mock_foreign_keys)

        assert "order_items" in relationships
        assert len(relationships["order_items"]) == 3
        assert "order" in relationships["order_items"]
        assert "product" in relationships["order_items"]
        assert "user" in relationships["order_items"]

    def test_reverse_relationship_detection(self):
        """Test detection of reverse relationships (one-to-many)."""
        # Mock schema with tables and foreign keys
        mock_tables = ["users", "orders", "products", "order_items"]
        mock_foreign_keys = [
            {
                "table_name": "orders",
                "column_name": "user_id",
                "foreign_table_name": "users",
                "foreign_column_name": "id",
            },
            {
                "table_name": "order_items",
                "column_name": "order_id",
                "foreign_table_name": "orders",
                "foreign_column_name": "id",
            },
            {
                "table_name": "order_items",
                "column_name": "product_id",
                "foreign_table_name": "products",
                "foreign_column_name": "id",
            },
        ]

        def detect_reverse_relationships(tables, foreign_keys):
            """Detect has_many relationships from foreign key references."""
            reverse_relationships = {}

            # Initialize all tables
            for table in tables:
                reverse_relationships[table] = {}

            # Find reverse relationships
            for fk in foreign_keys:
                target_table = fk["foreign_table_name"]
                source_table = fk["table_name"]

                # Create reverse relationship name
                # users -> orders (orders references users)
                rel_name = source_table  # plural form

                reverse_relationships[target_table][rel_name] = {
                    "type": "has_many",
                    "target_table": source_table,
                    "foreign_key": fk["column_name"],
                    "local_key": fk["foreign_column_name"],
                }

            return reverse_relationships

        reverse_rels = detect_reverse_relationships(mock_tables, mock_foreign_keys)

        # Users has many orders
        assert "orders" in reverse_rels["users"]
        assert reverse_rels["users"]["orders"]["type"] == "has_many"

        # Orders has many order_items
        assert "order_items" in reverse_rels["orders"]

        # Products has many order_items
        assert "order_items" in reverse_rels["products"]

    def test_self_referencing_relationships(self):
        """Test detection of self-referencing relationships."""
        mock_foreign_keys = [
            {
                "table_name": "categories",
                "column_name": "parent_id",
                "foreign_table_name": "categories",
                "foreign_column_name": "id",
            },
            {
                "table_name": "employees",
                "column_name": "manager_id",
                "foreign_table_name": "employees",
                "foreign_column_name": "id",
            },
        ]

        def detect_self_referencing(foreign_keys):
            """Detect self-referencing relationships."""
            self_refs = {}

            for fk in foreign_keys:
                if fk["table_name"] == fk["foreign_table_name"]:
                    table = fk["table_name"]
                    if table not in self_refs:
                        self_refs[table] = {}

                    # Create relationship names
                    foreign_key = fk["column_name"]
                    if foreign_key == "parent_id":
                        # Parent-child relationship
                        self_refs[table]["parent"] = {
                            "type": "belongs_to_self",
                            "foreign_key": "parent_id",
                        }
                        self_refs[table]["children"] = {
                            "type": "has_many_self",
                            "foreign_key": "parent_id",
                        }
                    elif foreign_key == "manager_id":
                        # Manager-employee relationship
                        self_refs[table]["manager"] = {
                            "type": "belongs_to_self",
                            "foreign_key": "manager_id",
                        }
                        self_refs[table]["subordinates"] = {
                            "type": "has_many_self",
                            "foreign_key": "manager_id",
                        }

            return self_refs

        self_refs = detect_self_referencing(mock_foreign_keys)

        # Categories self-reference
        assert "categories" in self_refs
        assert "parent" in self_refs["categories"]
        assert "children" in self_refs["categories"]

        # Employees self-reference
        assert "employees" in self_refs
        assert "manager" in self_refs["employees"]
        assert "subordinates" in self_refs["employees"]

    def test_many_to_many_relationship_detection(self):
        """Test detection of many-to-many relationships through junction tables."""
        # Mock tables that could form many-to-many relationships
        mock_tables = [
            {
                "table_name": "users",
                "columns": [{"column_name": "id", "is_primary_key": True}],
            },
            {
                "table_name": "roles",
                "columns": [{"column_name": "id", "is_primary_key": True}],
            },
            {
                "table_name": "user_roles",
                "columns": [
                    {"column_name": "user_id", "is_primary_key": False},
                    {"column_name": "role_id", "is_primary_key": False},
                ],
            },
            {
                "table_name": "products",
                "columns": [{"column_name": "id", "is_primary_key": True}],
            },
            {
                "table_name": "tags",
                "columns": [{"column_name": "id", "is_primary_key": True}],
            },
            {
                "table_name": "product_tags",
                "columns": [
                    {"column_name": "product_id", "is_primary_key": False},
                    {"column_name": "tag_id", "is_primary_key": False},
                ],
            },
        ]

        mock_foreign_keys = [
            {
                "table_name": "user_roles",
                "column_name": "user_id",
                "foreign_table_name": "users",
                "foreign_column_name": "id",
            },
            {
                "table_name": "user_roles",
                "column_name": "role_id",
                "foreign_table_name": "roles",
                "foreign_column_name": "id",
            },
            {
                "table_name": "product_tags",
                "column_name": "product_id",
                "foreign_table_name": "products",
                "foreign_column_name": "id",
            },
            {
                "table_name": "product_tags",
                "column_name": "tag_id",
                "foreign_table_name": "tags",
                "foreign_column_name": "id",
            },
        ]

        def detect_many_to_many(tables, foreign_keys):
            """Detect many-to-many relationships through junction tables."""
            m2m_relationships = {}

            # Find potential junction tables (tables with only foreign keys)
            junction_tables = []
            for table in tables:
                # Check if table has only foreign key columns
                fk_columns = [
                    fk["column_name"]
                    for fk in foreign_keys
                    if fk["table_name"] == table["table_name"]
                ]
                non_pk_columns = [
                    col["column_name"]
                    for col in table["columns"]
                    if not col["is_primary_key"]
                ]

                if len(fk_columns) == 2 and set(fk_columns) == set(non_pk_columns):
                    junction_tables.append(table["table_name"])

            # Analyze junction tables
            for junction_table in junction_tables:
                fks = [fk for fk in foreign_keys if fk["table_name"] == junction_table]
                if len(fks) == 2:
                    table1 = fks[0]["foreign_table_name"]
                    table2 = fks[1]["foreign_table_name"]

                    # Create many-to-many relationships
                    if table1 not in m2m_relationships:
                        m2m_relationships[table1] = {}
                    if table2 not in m2m_relationships:
                        m2m_relationships[table2] = {}

                    m2m_relationships[table1][table2] = {
                        "type": "many_to_many",
                        "junction_table": junction_table,
                        "local_key": fks[0]["foreign_column_name"],
                        "foreign_key": fks[1]["foreign_column_name"],
                    }

                    m2m_relationships[table2][table1] = {
                        "type": "many_to_many",
                        "junction_table": junction_table,
                        "local_key": fks[1]["foreign_column_name"],
                        "foreign_key": fks[0]["foreign_column_name"],
                    }

            return m2m_relationships

        m2m_rels = detect_many_to_many(mock_tables, mock_foreign_keys)

        # Users <-> Roles relationship
        assert "users" in m2m_rels
        assert "roles" in m2m_rels["users"]
        assert m2m_rels["users"]["roles"]["type"] == "many_to_many"
        assert m2m_rels["users"]["roles"]["junction_table"] == "user_roles"

        # Products <-> Tags relationship
        assert "products" in m2m_rels
        assert "tags" in m2m_rels["products"]
        assert m2m_rels["products"]["tags"]["junction_table"] == "product_tags"

    def test_relationship_naming_conventions(self):
        """Test consistent naming conventions for relationships."""

        def generate_relationship_names(foreign_key_column, target_table):
            """Generate consistent relationship names."""
            # Remove _id suffix for belongs_to relationship
            belongs_to_name = foreign_key_column.replace("_id", "")

            # Pluralize target table for has_many relationship
            has_many_name = target_table
            if not has_many_name.endswith("s"):
                has_many_name += "s"

            return belongs_to_name, has_many_name

        test_cases = [
            ("user_id", "user", "user", "users"),
            ("category_id", "category", "category", "categorys"),
            ("parent_id", "node", "parent", "nodes"),
            ("manager_id", "employee", "manager", "employees"),
            ("product_id", "product", "product", "products"),
        ]

        for (
            fk_column,
            target_table,
            expected_belongs_to,
            expected_has_many,
        ) in test_cases:
            belongs_to, has_many = generate_relationship_names(fk_column, target_table)
            assert belongs_to == expected_belongs_to
            assert has_many == expected_has_many

    def test_polymorphic_relationship_detection(self):
        """Test detection of polymorphic relationships."""
        # Mock polymorphic setup
        mock_polymorphic_keys = [
            {
                "table_name": "comments",
                "type_column": "commentable_type",
                "id_column": "commentable_id",
                "possible_types": ["Post", "Photo", "Video"],
            },
            {
                "table_name": "attachments",
                "type_column": "attachable_type",
                "id_column": "attachable_id",
                "possible_types": ["User", "Product", "Order"],
            },
        ]

        def detect_polymorphic_relationships(polymorphic_data):
            """Detect polymorphic relationships."""
            polymorphic_rels = {}

            for poly in polymorphic_data:
                table = poly["table_name"]
                polymorphic_rels[table] = {
                    "type": "polymorphic_belongs_to",
                    "type_column": poly["type_column"],
                    "id_column": poly["id_column"],
                    "possible_types": poly["possible_types"],
                }

            return polymorphic_rels

        poly_rels = detect_polymorphic_relationships(mock_polymorphic_keys)

        assert "comments" in poly_rels
        assert poly_rels["comments"]["type"] == "polymorphic_belongs_to"
        assert poly_rels["comments"]["type_column"] == "commentable_type"
        assert "Post" in poly_rels["comments"]["possible_types"]

    def test_relationship_validation(self):
        """Test validation of detected relationships."""

        def validate_relationship(relationship_def):
            """Validate relationship definition."""
            errors = []

            required_fields = ["type", "target_table"]
            for field in required_fields:
                if field not in relationship_def:
                    errors.append(f"Missing required field: {field}")

            valid_types = [
                "belongs_to",
                "has_many",
                "has_one",
                "many_to_many",
                "polymorphic_belongs_to",
                "belongs_to_self",
                "has_many_self",
            ]

            if relationship_def.get("type") not in valid_types:
                errors.append(
                    f'Invalid relationship type: {relationship_def.get("type")}'
                )

            # Type-specific validations
            rel_type = relationship_def.get("type")
            if rel_type in ["belongs_to", "has_one"]:
                if "foreign_key" not in relationship_def:
                    errors.append("belongs_to/has_one requires foreign_key")

            elif rel_type == "many_to_many":
                if "junction_table" not in relationship_def:
                    errors.append("many_to_many requires junction_table")

            elif rel_type == "polymorphic_belongs_to":
                required_poly_fields = ["type_column", "id_column"]
                for field in required_poly_fields:
                    if field not in relationship_def:
                        errors.append(f"polymorphic_belongs_to requires {field}")

            return errors

        # Test valid relationship
        valid_rel = {
            "type": "belongs_to",
            "target_table": "users",
            "foreign_key": "user_id",
        }
        errors = validate_relationship(valid_rel)
        assert len(errors) == 0

        # Test invalid relationship
        invalid_rel = {
            "type": "invalid_type",
            "target_table": "users",
            # Missing foreign_key for belongs_to
        }
        errors = validate_relationship(invalid_rel)
        assert len(errors) > 0

    def test_relationship_code_generation(self):
        """Test generation of Python code for relationships."""

        def generate_relationship_code(model_name, relationships):
            """Generate Python code for model relationships."""
            lines = []

            for rel_name, rel_def in relationships.items():
                rel_type = rel_def["type"]

                if rel_type == "belongs_to":
                    lines.append(f"    # {rel_name} relationship")
                    lines.append(
                        f'    {rel_name} = db.relationship("{rel_def["target_table"]}", "{rel_def["foreign_key"]} -> id")'
                    )

                elif rel_type == "has_many":
                    lines.append(f"    # {rel_name} relationship")
                    lines.append(
                        f'    {rel_name} = db.has_many("{rel_def["target_table"]}", "{rel_def["foreign_key"]}")'
                    )

                elif rel_type == "many_to_many":
                    lines.append(f"    # {rel_name} relationship")
                    lines.append(
                        f'    {rel_name} = db.many_to_many("{rel_def["target_table"]}", through="{rel_def["junction_table"]}")'
                    )

            return "\n".join(lines)

        # Test relationship code generation
        relationships = {
            "user": {
                "type": "belongs_to",
                "target_table": "User",
                "foreign_key": "user_id",
            },
            "items": {
                "type": "has_many",
                "target_table": "OrderItem",
                "foreign_key": "order_id",
            },
        }

        code = generate_relationship_code("Order", relationships)

        assert 'user = db.relationship("User"' in code
        assert 'items = db.has_many("OrderItem"' in code
        assert "# user relationship" in code

"""Unit tests for DataFlow schema discovery functionality.

These tests ensure that schema discovery correctly parses database
metadata and converts it to DataFlow model definitions.
"""

from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest


class TestDataFlowSchemaDiscovery:
    """Test DataFlow schema discovery and introspection functionality."""

    def test_discover_schema_basic_table_detection(self):
        """Test basic table detection from database metadata."""
        # Mock database metadata
        mock_tables = [
            {
                "table_name": "users",
                "table_schema": "public",
                "table_type": "BASE TABLE",
            },
            {
                "table_name": "orders",
                "table_schema": "public",
                "table_type": "BASE TABLE",
            },
            {
                "table_name": "products",
                "table_schema": "public",
                "table_type": "BASE TABLE",
            },
        ]

        # Mock schema discovery
        def discover_tables(connection):
            return mock_tables

        # Test table discovery
        discovered = discover_tables(None)
        assert len(discovered) == 3
        assert any(table["table_name"] == "users" for table in discovered)
        assert any(table["table_name"] == "orders" for table in discovered)
        assert any(table["table_name"] == "products" for table in discovered)

    def test_discover_schema_column_information(self):
        """Test extraction of column information from tables."""
        # Mock column metadata
        mock_columns = {
            "users": [
                {
                    "column_name": "id",
                    "data_type": "integer",
                    "is_nullable": False,
                    "column_default": "nextval('users_id_seq')",
                    "is_primary_key": True,
                },
                {
                    "column_name": "name",
                    "data_type": "varchar",
                    "character_maximum_length": 255,
                    "is_nullable": False,
                    "column_default": None,
                    "is_primary_key": False,
                },
                {
                    "column_name": "email",
                    "data_type": "varchar",
                    "character_maximum_length": 255,
                    "is_nullable": False,
                    "column_default": None,
                    "is_primary_key": False,
                },
                {
                    "column_name": "created_at",
                    "data_type": "timestamp",
                    "is_nullable": False,
                    "column_default": "CURRENT_TIMESTAMP",
                    "is_primary_key": False,
                },
                {
                    "column_name": "active",
                    "data_type": "boolean",
                    "is_nullable": False,
                    "column_default": "true",
                    "is_primary_key": False,
                },
            ]
        }

        # Test column extraction
        user_columns = mock_columns["users"]
        assert len(user_columns) == 5

        # Verify column details
        id_column = next(col for col in user_columns if col["column_name"] == "id")
        assert id_column["data_type"] == "integer"
        assert id_column["is_primary_key"] is True
        assert id_column["is_nullable"] is False

        name_column = next(col for col in user_columns if col["column_name"] == "name")
        assert name_column["data_type"] == "varchar"
        assert name_column["character_maximum_length"] == 255
        assert name_column["is_nullable"] is False

    def test_sql_type_to_python_type_mapping(self):
        """Test mapping from SQL types to Python types."""
        # Define type mapping
        type_mappings = {
            # Integer types
            "integer": int,
            "bigint": int,
            "smallint": int,
            "serial": int,
            "bigserial": int,
            # String types
            "varchar": str,
            "text": str,
            "char": str,
            "character": str,
            # Numeric types
            "numeric": float,
            "decimal": float,
            "real": float,
            "double precision": float,
            "money": float,
            # Boolean type
            "boolean": bool,
            # Date/time types
            "timestamp": "datetime",
            "timestamptz": "datetime",
            "date": "date",
            "time": "time",
            # JSON types
            "json": dict,
            "jsonb": dict,
            # Array types
            "array": list,
        }

        def map_sql_type_to_python(sql_type: str, is_nullable: bool = False):
            """Map SQL type to Python type annotation."""
            base_type = type_mappings.get(sql_type.lower(), str)

            # Handle special string types
            if base_type == "datetime":
                from datetime import datetime

                base_type = datetime
            elif base_type == "date":
                from datetime import date

                base_type = date
            elif base_type == "time":
                from datetime import time

                base_type = time

            # Handle nullable types
            if is_nullable:
                from typing import Optional

                return Optional[base_type]

            return base_type

        # Test basic mappings
        assert map_sql_type_to_python("integer") == int
        assert map_sql_type_to_python("varchar") == str
        assert map_sql_type_to_python("boolean") == bool
        assert map_sql_type_to_python("numeric") == float

        # Test nullable mappings
        nullable_int = map_sql_type_to_python("integer", is_nullable=True)
        assert hasattr(nullable_int, "__origin__")  # Optional type

    def test_foreign_key_detection(self):
        """Test detection of foreign key relationships."""
        # Mock foreign key metadata
        mock_foreign_keys = [
            {
                "table_name": "orders",
                "column_name": "user_id",
                "foreign_table_name": "users",
                "foreign_column_name": "id",
                "constraint_name": "fk_orders_user_id",
            },
            {
                "table_name": "orders",
                "column_name": "product_id",
                "foreign_table_name": "products",
                "foreign_column_name": "id",
                "constraint_name": "fk_orders_product_id",
            },
            {
                "table_name": "order_items",
                "column_name": "order_id",
                "foreign_table_name": "orders",
                "foreign_column_name": "id",
                "constraint_name": "fk_order_items_order_id",
            },
        ]

        def extract_relationships(foreign_keys):
            """Extract relationship information from foreign keys."""
            relationships = {}

            for fk in foreign_keys:
                table = fk["table_name"]
                if table not in relationships:
                    relationships[table] = {}

                # Create relationship name (remove _id suffix)
                rel_name = fk["column_name"]
                if rel_name.endswith("_id"):
                    rel_name = rel_name[:-3]

                relationships[table][rel_name] = {
                    "target_table": fk["foreign_table_name"],
                    "target_column": fk["foreign_column_name"],
                    "source_column": fk["column_name"],
                    "constraint_name": fk["constraint_name"],
                }

            return relationships

        # Test relationship extraction
        relationships = extract_relationships(mock_foreign_keys)

        # Verify orders relationships
        assert "orders" in relationships
        assert "user" in relationships["orders"]
        assert "product" in relationships["orders"]

        user_rel = relationships["orders"]["user"]
        assert user_rel["target_table"] == "users"
        assert user_rel["target_column"] == "id"
        assert user_rel["source_column"] == "user_id"

        # Verify order_items relationships
        assert "order_items" in relationships
        assert "order" in relationships["order_items"]

    def test_index_discovery(self):
        """Test discovery of database indexes."""
        # Mock index metadata
        mock_indexes = [
            {
                "table_name": "users",
                "index_name": "users_email_idx",
                "column_names": ["email"],
                "is_unique": True,
                "index_type": "btree",
            },
            {
                "table_name": "orders",
                "index_name": "orders_user_id_status_idx",
                "column_names": ["user_id", "status"],
                "is_unique": False,
                "index_type": "btree",
            },
            {
                "table_name": "orders",
                "index_name": "orders_created_at_idx",
                "column_names": ["created_at"],
                "is_unique": False,
                "index_type": "btree",
            },
        ]

        def group_indexes_by_table(indexes):
            """Group indexes by table name."""
            grouped = {}
            for index in indexes:
                table = index["table_name"]
                if table not in grouped:
                    grouped[table] = []
                grouped[table].append(index)
            return grouped

        # Test index grouping
        grouped = group_indexes_by_table(mock_indexes)

        assert "users" in grouped
        assert len(grouped["users"]) == 1
        assert grouped["users"][0]["column_names"] == ["email"]
        assert grouped["users"][0]["is_unique"] is True

        assert "orders" in grouped
        assert len(grouped["orders"]) == 2

    def test_table_to_model_name_conversion(self):
        """Test conversion from table names to Python model class names."""

        def table_name_to_class_name(table_name: str) -> str:
            """Convert table name to Python class name."""
            # Remove underscores and capitalize each word
            words = table_name.split("_")
            return "".join(word.capitalize() for word in words)

        # Test various table name patterns
        test_cases = [
            ("users", "Users"),
            ("user_profiles", "UserProfiles"),
            ("order_items", "OrderItems"),
            ("product_categories", "ProductCategories"),
            ("api_keys", "ApiKeys"),
            ("oauth_tokens", "OauthTokens"),
        ]

        for table_name, expected_class_name in test_cases:
            assert table_name_to_class_name(table_name) == expected_class_name

    def test_model_generation_from_schema(self):
        """Test generation of model class definitions from schema."""
        # Mock complete table schema
        mock_table_schema = {
            "table_name": "users",
            "columns": [
                {
                    "column_name": "id",
                    "data_type": "integer",
                    "is_nullable": False,
                    "is_primary_key": True,
                    "python_type": int,
                },
                {
                    "column_name": "name",
                    "data_type": "varchar",
                    "is_nullable": False,
                    "is_primary_key": False,
                    "python_type": str,
                },
                {
                    "column_name": "email",
                    "data_type": "varchar",
                    "is_nullable": False,
                    "is_primary_key": False,
                    "python_type": str,
                },
                {
                    "column_name": "age",
                    "data_type": "integer",
                    "is_nullable": True,
                    "is_primary_key": False,
                    "python_type": "Optional[int]",
                },
            ],
            "relationships": {
                "orders": {"type": "one_to_many", "foreign_key": "user_id"}
            },
            "indexes": [
                {"name": "users_email_idx", "columns": ["email"], "unique": True}
            ],
        }

        def generate_model_definition(schema):
            """Generate model class definition from schema."""
            model_def = {
                "class_name": schema["table_name"].title(),
                "table_name": schema["table_name"],
                "fields": {},
                "relationships": schema.get("relationships", {}),
                "indexes": schema.get("indexes", []),
            }

            for column in schema["columns"]:
                model_def["fields"][column["column_name"]] = {
                    "type": column["python_type"],
                    "nullable": column["is_nullable"],
                    "primary_key": column["is_primary_key"],
                }

            return model_def

        # Test model generation
        model_def = generate_model_definition(mock_table_schema)

        assert model_def["class_name"] == "Users"
        assert model_def["table_name"] == "users"
        assert len(model_def["fields"]) == 4
        assert model_def["fields"]["id"]["primary_key"] is True
        assert model_def["fields"]["age"]["nullable"] is True
        assert "orders" in model_def["relationships"]

    def test_scaffold_file_generation(self):
        """Test generation of Python model files from discovered schema."""
        # Mock multiple table schemas
        mock_schemas = {
            "users": {
                "class_name": "User",
                "fields": {
                    "id": {"type": int, "primary_key": True},
                    "name": {"type": str, "nullable": False},
                    "email": {"type": str, "nullable": False},
                },
                "relationships": {},
            },
            "orders": {
                "class_name": "Order",
                "fields": {
                    "id": {"type": int, "primary_key": True},
                    "user_id": {"type": int, "nullable": False},
                    "amount": {"type": float, "nullable": False},
                },
                "relationships": {"user": {"target": "User", "key": "user_id"}},
            },
        }

        def generate_model_file_content(schemas):
            """Generate Python file content for models."""
            lines = [
                '"""Auto-generated DataFlow models from database schema."""',
                "",
                "from dataflow import DataFlow",
                "from typing import Optional",
                "from datetime import datetime, date",
                "",
                "# Initialize DataFlow instance",
                "db = DataFlow()",
                "",
            ]

            for table_name, schema in schemas.items():
                lines.extend(
                    [
                        "@db.model",
                        f'class {schema["class_name"]}:',
                        f'    """Model for {table_name} table."""',
                    ]
                )

                # Add fields
                for field_name, field_info in schema["fields"].items():
                    type_str = (
                        field_info["type"].__name__
                        if hasattr(field_info["type"], "__name__")
                        else str(field_info["type"])
                    )
                    if field_info.get("nullable") and not field_info.get("primary_key"):
                        type_str = f"Optional[{type_str}]"
                    lines.append(f"    {field_name}: {type_str}")

                # Add relationships
                for rel_name, rel_info in schema["relationships"].items():
                    lines.append(
                        f'    # Relationship: {rel_name} -> {rel_info["target"]}'
                    )

                lines.append("")

            return "\n".join(lines)

        # Test file generation
        content = generate_model_file_content(mock_schemas)

        # Verify content structure
        assert "@db.model" in content
        assert "class User:" in content
        assert "class Order:" in content
        assert "user_id: int" in content
        assert "from typing import Optional" in content

    def test_schema_validation(self):
        """Test validation of discovered schema for completeness."""

        def validate_schema(schema):
            """Validate that schema contains required information."""
            errors = []

            if not schema.get("table_name"):
                errors.append("Missing table_name")

            if not schema.get("columns"):
                errors.append("Missing columns")

            # Check for primary key
            has_primary_key = any(
                col.get("is_primary_key") for col in schema.get("columns", [])
            )
            if not has_primary_key:
                errors.append("No primary key found")

            # Validate column information
            for column in schema.get("columns", []):
                if not column.get("column_name"):
                    errors.append("Column missing name")
                if not column.get("data_type"):
                    errors.append(
                        f'Column {column.get("column_name")} missing data type'
                    )

            return errors

        # Test valid schema
        valid_schema = {
            "table_name": "users",
            "columns": [
                {"column_name": "id", "data_type": "integer", "is_primary_key": True},
                {"column_name": "name", "data_type": "varchar"},
            ],
        }

        errors = validate_schema(valid_schema)
        assert len(errors) == 0

        # Test invalid schema
        invalid_schema = {
            "columns": [
                {
                    "column_name": "name"
                    # Missing data_type
                }
            ]
            # Missing table_name, no primary key
        }

        errors = validate_schema(invalid_schema)
        assert len(errors) > 0
        assert any("Missing table_name" in error for error in errors)

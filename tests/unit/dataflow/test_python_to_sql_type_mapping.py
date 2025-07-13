"""Unit tests for DataFlow Python-to-SQL type mapping functionality.

These tests ensure that Python types are correctly mapped to appropriate SQL types
for different database systems (PostgreSQL, MySQL, SQLite).
"""

import os
import sys
from datetime import datetime
from typing import Optional

import pytest

# Add the DataFlow app to the path
sys.path.insert(
    0, os.path.join(os.path.dirname(__file__), "../../../apps/kailash-dataflow/src")
)

from dataflow import DataFlow


class TestPythonToSQLTypeMapping:
    """Test Python-to-SQL type mapping for multiple databases."""

    def test_basic_python_types_postgresql(self):
        """Test basic Python types map correctly to PostgreSQL types."""
        db = DataFlow()

        # Test basic type mappings
        assert db._python_type_to_sql_type(int, "postgresql") == "INTEGER"
        assert db._python_type_to_sql_type(str, "postgresql") == "VARCHAR(255)"
        assert db._python_type_to_sql_type(bool, "postgresql") == "BOOLEAN"
        assert db._python_type_to_sql_type(float, "postgresql") == "REAL"
        assert db._python_type_to_sql_type(datetime, "postgresql") == "TIMESTAMP"
        assert db._python_type_to_sql_type(dict, "postgresql") == "JSONB"
        assert db._python_type_to_sql_type(list, "postgresql") == "JSONB"
        assert db._python_type_to_sql_type(bytes, "postgresql") == "BYTEA"

    def test_basic_python_types_mysql(self):
        """Test basic Python types map correctly to MySQL types."""
        db = DataFlow()

        # Test basic type mappings
        assert db._python_type_to_sql_type(int, "mysql") == "INT"
        assert db._python_type_to_sql_type(str, "mysql") == "VARCHAR(255)"
        assert db._python_type_to_sql_type(bool, "mysql") == "TINYINT(1)"
        assert db._python_type_to_sql_type(float, "mysql") == "DOUBLE"
        assert db._python_type_to_sql_type(datetime, "mysql") == "DATETIME"
        assert db._python_type_to_sql_type(dict, "mysql") == "JSON"
        assert db._python_type_to_sql_type(list, "mysql") == "JSON"
        assert db._python_type_to_sql_type(bytes, "mysql") == "BLOB"

    def test_basic_python_types_sqlite(self):
        """Test basic Python types map correctly to SQLite types."""
        db = DataFlow()

        # Test basic type mappings
        assert db._python_type_to_sql_type(int, "sqlite") == "INTEGER"
        assert db._python_type_to_sql_type(str, "sqlite") == "TEXT"
        assert (
            db._python_type_to_sql_type(bool, "sqlite") == "INTEGER"
        )  # SQLite doesn't have boolean
        assert db._python_type_to_sql_type(float, "sqlite") == "REAL"
        assert (
            db._python_type_to_sql_type(datetime, "sqlite") == "TEXT"
        )  # SQLite stores as text
        assert db._python_type_to_sql_type(dict, "sqlite") == "TEXT"  # JSON as text
        assert db._python_type_to_sql_type(list, "sqlite") == "TEXT"  # JSON as text
        assert db._python_type_to_sql_type(bytes, "sqlite") == "BLOB"

    def test_optional_types_handling(self):
        """Test that Optional[Type] is handled correctly."""
        db = DataFlow()

        # Test Optional types - should return the same as the base type
        assert db._python_type_to_sql_type(Optional[int], "postgresql") == "INTEGER"
        assert (
            db._python_type_to_sql_type(Optional[str], "postgresql") == "VARCHAR(255)"
        )
        assert db._python_type_to_sql_type(Optional[bool], "postgresql") == "BOOLEAN"
        assert (
            db._python_type_to_sql_type(Optional[datetime], "postgresql") == "TIMESTAMP"
        )

        # Test with different databases
        assert db._python_type_to_sql_type(Optional[bool], "mysql") == "TINYINT(1)"
        assert db._python_type_to_sql_type(Optional[bool], "sqlite") == "INTEGER"

    def test_unknown_types_fallback(self):
        """Test that unknown types fall back to TEXT."""
        db = DataFlow()

        # Custom class should fall back to TEXT
        class CustomClass:
            pass

        assert db._python_type_to_sql_type(CustomClass, "postgresql") == "TEXT"
        assert db._python_type_to_sql_type(CustomClass, "mysql") == "TEXT"
        assert db._python_type_to_sql_type(CustomClass, "sqlite") == "TEXT"

    def test_default_database_type(self):
        """Test that PostgreSQL is used as default database type."""
        db = DataFlow()

        # When no database type is specified, should default to PostgreSQL
        assert db._python_type_to_sql_type(int) == "INTEGER"
        assert db._python_type_to_sql_type(str) == "VARCHAR(255)"
        assert db._python_type_to_sql_type(bool) == "BOOLEAN"

    def test_sql_column_definition_basic(self):
        """Test basic SQL column definition generation."""
        db = DataFlow()

        # Test required field without default
        field_info = {"type": str, "required": True}
        definition = db._get_sql_column_definition("name", field_info, "postgresql")
        assert definition == "name VARCHAR(255) NOT NULL"

        # Test optional field without default
        field_info = {"type": str, "required": False}
        definition = db._get_sql_column_definition(
            "description", field_info, "postgresql"
        )
        assert definition == "description VARCHAR(255)"

    def test_sql_column_definition_with_defaults(self):
        """Test SQL column definition with default values."""
        db = DataFlow()

        # Test string default
        field_info = {"type": str, "required": False, "default": "pending"}
        definition = db._get_sql_column_definition("status", field_info, "postgresql")
        assert definition == "status VARCHAR(255) DEFAULT 'pending'"

        # Test boolean default
        field_info = {"type": bool, "required": False, "default": True}
        definition = db._get_sql_column_definition("active", field_info, "postgresql")
        assert definition == "active BOOLEAN DEFAULT TRUE"

        # Test numeric default
        field_info = {"type": int, "required": False, "default": 0}
        definition = db._get_sql_column_definition("count", field_info, "postgresql")
        assert definition == "count INTEGER DEFAULT 0"

    def test_sql_column_definition_database_specific_defaults(self):
        """Test database-specific default value handling."""
        db = DataFlow()

        # Test boolean defaults across databases
        field_info = {"type": bool, "required": False, "default": True}

        # PostgreSQL
        definition = db._get_sql_column_definition("active", field_info, "postgresql")
        assert definition == "active BOOLEAN DEFAULT TRUE"

        # MySQL
        definition = db._get_sql_column_definition("active", field_info, "mysql")
        assert definition == "active TINYINT(1) DEFAULT 1"

        # SQLite
        definition = db._get_sql_column_definition("active", field_info, "sqlite")
        assert definition == "active INTEGER DEFAULT 1"

    def test_sql_column_definition_optional_types(self):
        """Test SQL column definition with Optional types."""
        db = DataFlow()

        # Test Optional[str] - should not be NOT NULL by default
        field_info = {"type": Optional[str], "required": False}
        definition = db._get_sql_column_definition(
            "description", field_info, "postgresql"
        )
        assert definition == "description VARCHAR(255)"

        # Test Optional[int] with default
        field_info = {"type": Optional[int], "required": False, "default": None}
        definition = db._get_sql_column_definition("age", field_info, "postgresql")
        assert definition == "age INTEGER"

    def test_complex_field_scenarios(self):
        """Test complex field definition scenarios."""
        db = DataFlow()

        # Test datetime field
        field_info = {"type": datetime, "required": True}
        definition = db._get_sql_column_definition(
            "created_at", field_info, "postgresql"
        )
        assert definition == "created_at TIMESTAMP NOT NULL"

        # Test JSON field
        field_info = {"type": dict, "required": False}
        definition = db._get_sql_column_definition("metadata", field_info, "postgresql")
        assert definition == "metadata JSONB"

        # Test list field in different databases
        field_info = {"type": list, "required": True}

        # PostgreSQL - should use JSONB
        definition = db._get_sql_column_definition("tags", field_info, "postgresql")
        assert definition == "tags JSONB NOT NULL"

        # MySQL - should use JSON
        definition = db._get_sql_column_definition("tags", field_info, "mysql")
        assert definition == "tags JSON NOT NULL"

        # SQLite - should use TEXT
        definition = db._get_sql_column_definition("tags", field_info, "sqlite")
        assert definition == "tags TEXT NOT NULL"

    def test_edge_cases_and_error_handling(self):
        """Test edge cases and error handling in type mapping."""
        db = DataFlow()

        # Test None default value
        field_info = {"type": str, "required": False, "default": None}
        definition = db._get_sql_column_definition(
            "nullable_field", field_info, "postgresql"
        )
        assert definition == "nullable_field VARCHAR(255)"

        # Test missing type (should use fallback)
        field_info = {"required": True}
        try:
            definition = db._get_sql_column_definition(
                "test_field", field_info, "postgresql"
            )
            # Should handle missing type gracefully or raise appropriate error
        except KeyError:
            # Expected behavior - missing type should raise error
            pass

    def test_database_type_case_insensitive(self):
        """Test that database type parameter is case insensitive."""
        db = DataFlow()

        # Test different case variations
        assert db._python_type_to_sql_type(int, "POSTGRESQL") == "INTEGER"
        assert db._python_type_to_sql_type(int, "PostgreSQL") == "INTEGER"
        assert db._python_type_to_sql_type(int, "mysql") == "INT"
        assert db._python_type_to_sql_type(int, "MYSQL") == "INT"

    def test_unsupported_database_fallback(self):
        """Test fallback to PostgreSQL for unsupported databases."""
        db = DataFlow()

        # Test with unsupported database - should fall back to PostgreSQL
        assert db._python_type_to_sql_type(int, "oracle") == "INTEGER"
        assert db._python_type_to_sql_type(str, "mssql") == "VARCHAR(255)"
        assert db._python_type_to_sql_type(bool, "unknown") == "BOOLEAN"

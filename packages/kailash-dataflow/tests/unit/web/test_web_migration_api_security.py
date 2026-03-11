"""
Tier 1 Unit Tests for WebMigrationAPI Security

Tests SQL injection prevention and input validation security features.
These tests ensure the WebMigrationAPI properly rejects malicious inputs.

Core Functionalities Tested:
1. Table name SQL injection prevention
2. Column name SQL injection prevention
3. Default value SQL injection prevention
4. Schema name validation
5. Identifier validation
6. Length validation
"""

from unittest.mock import MagicMock, patch

import pytest
from dataflow.web.exceptions import ValidationError
from dataflow.web.migration_api import WebMigrationAPI


class TestSQLInjectionPrevention:
    """Test SQL injection prevention in WebMigrationAPI."""

    @patch("dataflow.web.migration_api.AutoMigrationSystem")
    def test_table_name_sql_injection_semicolon(self, mock_auto_migration):
        """Test that table names with semicolons are rejected."""
        api = WebMigrationAPI("postgresql://user:pass@localhost:5432/db")

        spec = {
            "type": "create_table",
            "table_name": "users; DROP TABLE real_users; --",
            "columns": [{"name": "id", "type": "INTEGER"}],
        }

        with pytest.raises(ValidationError) as exc_info:
            api.create_migration_preview("test", spec)

        assert "Invalid table name" in str(exc_info.value)

    @patch("dataflow.web.migration_api.AutoMigrationSystem")
    def test_table_name_sql_injection_drop(self, mock_auto_migration):
        """Test that table names with DROP keyword are rejected."""
        api = WebMigrationAPI("postgresql://user:pass@localhost:5432/db")

        spec = {
            "type": "create_table",
            "table_name": "DROP",
            "columns": [{"name": "id", "type": "INTEGER"}],
        }

        with pytest.raises(ValidationError) as exc_info:
            api.create_migration_preview("test", spec)

        assert "Invalid table name" in str(exc_info.value)

    @patch("dataflow.web.migration_api.AutoMigrationSystem")
    def test_column_name_sql_injection_quotes(self, mock_auto_migration):
        """Test that column names with quotes are rejected."""
        api = WebMigrationAPI("postgresql://user:pass@localhost:5432/db")

        spec = {
            "type": "create_table",
            "table_name": "users",
            "columns": [{"name": "id'; DROP TABLE users; --", "type": "INTEGER"}],
        }

        with pytest.raises(ValidationError) as exc_info:
            api.create_migration_preview("test", spec)

        assert "Invalid column name" in str(exc_info.value)

    @patch("dataflow.web.migration_api.AutoMigrationSystem")
    def test_column_name_sql_injection_comment(self, mock_auto_migration):
        """Test that column names with comment markers are rejected."""
        api = WebMigrationAPI("postgresql://user:pass@localhost:5432/db")

        spec = {
            "type": "create_table",
            "table_name": "users",
            "columns": [{"name": "id--comment", "type": "INTEGER"}],
        }

        with pytest.raises(ValidationError) as exc_info:
            api.create_migration_preview("test", spec)

        assert "Invalid column name" in str(exc_info.value)

    @patch("dataflow.web.migration_api.AutoMigrationSystem")
    def test_default_value_sql_injection(self, mock_auto_migration):
        """Test that dangerous default values are rejected."""
        api = WebMigrationAPI("postgresql://user:pass@localhost:5432/db")

        spec = {
            "type": "create_table",
            "table_name": "users",
            "columns": [
                {
                    "name": "status",
                    "type": "VARCHAR",
                    "default": "'; DELETE FROM users; --",
                }
            ],
        }

        with pytest.raises(ValidationError) as exc_info:
            api.create_migration_preview("test", spec)

        assert "Invalid default value" in str(exc_info.value)
        assert "dangerous SQL patterns" in str(exc_info.value)

    @patch("dataflow.web.migration_api.AutoMigrationSystem")
    def test_schema_name_sql_injection(self, mock_auto_migration):
        """Test that schema names with SQL injection are rejected."""
        api = WebMigrationAPI("postgresql://user:pass@localhost:5432/db")

        with pytest.raises(ValidationError) as exc_info:
            api.inspect_schema(schema_name="public; DROP SCHEMA public; --")

        assert "Invalid schema name" in str(exc_info.value)


class TestIdentifierValidation:
    """Test identifier validation rules."""

    @patch("dataflow.web.migration_api.AutoMigrationSystem")
    def test_table_name_starts_with_number(self, mock_auto_migration):
        """Test that table names starting with numbers are rejected."""
        api = WebMigrationAPI("postgresql://user:pass@localhost:5432/db")

        spec = {
            "type": "create_table",
            "table_name": "123users",
            "columns": [{"name": "id", "type": "INTEGER"}],
        }

        with pytest.raises(ValidationError) as exc_info:
            api.create_migration_preview("test", spec)

        assert "Invalid table name" in str(exc_info.value)

    @patch("dataflow.web.migration_api.AutoMigrationSystem")
    def test_table_name_with_special_chars(self, mock_auto_migration):
        """Test that table names with special characters are rejected."""
        api = WebMigrationAPI("postgresql://user:pass@localhost:5432/db")

        spec = {
            "type": "create_table",
            "table_name": "user$table",
            "columns": [{"name": "id", "type": "INTEGER"}],
        }

        with pytest.raises(ValidationError) as exc_info:
            api.create_migration_preview("test", spec)

        assert "Invalid table name" in str(exc_info.value)

    @patch("dataflow.web.migration_api.AutoMigrationSystem")
    def test_table_name_too_long(self, mock_auto_migration):
        """Test that table names exceeding 63 characters are rejected."""
        api = WebMigrationAPI("postgresql://user:pass@localhost:5432/db")

        # 64 characters - should be rejected
        long_name = "a" * 64

        spec = {
            "type": "create_table",
            "table_name": long_name,
            "columns": [{"name": "id", "type": "INTEGER"}],
        }

        with pytest.raises(ValidationError) as exc_info:
            api.create_migration_preview("test", spec)

        assert "Invalid table name" in str(exc_info.value)

    @patch("dataflow.web.migration_api.AutoMigrationSystem")
    def test_column_name_with_backticks(self, mock_auto_migration):
        """Test that column names with backticks are rejected."""
        api = WebMigrationAPI("postgresql://user:pass@localhost:5432/db")

        spec = {
            "type": "create_table",
            "table_name": "users",
            "columns": [{"name": "`id`", "type": "INTEGER"}],
        }

        with pytest.raises(ValidationError) as exc_info:
            api.create_migration_preview("test", spec)

        assert "Invalid column name" in str(exc_info.value)

    @patch("dataflow.web.migration_api.AutoMigrationSystem")
    def test_sql_keyword_as_table_name(self, mock_auto_migration):
        """Test that SQL keywords as table names are rejected."""
        api = WebMigrationAPI("postgresql://user:pass@localhost:5432/db")

        sql_keywords = ["SELECT", "INSERT", "UPDATE", "DELETE", "FROM", "WHERE"]

        for keyword in sql_keywords:
            spec = {
                "type": "create_table",
                "table_name": keyword,
                "columns": [{"name": "id", "type": "INTEGER"}],
            }

            with pytest.raises(ValidationError) as exc_info:
                api.create_migration_preview("test", spec)

            assert "Invalid table name" in str(exc_info.value)

    @patch("dataflow.web.migration_api.AutoMigrationSystem")
    def test_valid_identifier_accepted(self, mock_auto_migration):
        """Test that valid identifiers are accepted."""
        mock_system = MagicMock()
        mock_auto_migration.return_value = mock_system

        api = WebMigrationAPI("postgresql://user:pass@localhost:5432/db")

        # Valid identifiers
        valid_names = ["users", "user_table", "_internal", "Table123"]

        for table_name in valid_names:
            spec = {
                "type": "create_table",
                "table_name": table_name,
                "columns": [{"name": "id", "type": "INTEGER"}],
            }

            # Should not raise ValidationError
            try:
                api.create_migration_preview("test", spec)
            except ValidationError:
                pytest.fail(f"Valid identifier '{table_name}' was rejected")


class TestLengthValidation:
    """Test length validation for numeric fields."""

    @patch("dataflow.web.migration_api.AutoMigrationSystem")
    def test_negative_length_rejected(self, mock_auto_migration):
        """Test that negative column lengths are rejected."""
        api = WebMigrationAPI("postgresql://user:pass@localhost:5432/db")

        spec = {
            "type": "create_table",
            "table_name": "users",
            "columns": [{"name": "name", "type": "VARCHAR", "length": -10}],
        }

        with pytest.raises(ValidationError) as exc_info:
            api.create_migration_preview("test", spec)

        assert "Invalid column length" in str(exc_info.value)

    @patch("dataflow.web.migration_api.AutoMigrationSystem")
    def test_zero_length_rejected(self, mock_auto_migration):
        """Test that zero column lengths are rejected."""
        api = WebMigrationAPI("postgresql://user:pass@localhost:5432/db")

        spec = {
            "type": "create_table",
            "table_name": "users",
            "columns": [{"name": "name", "type": "VARCHAR", "length": 0}],
        }

        with pytest.raises(ValidationError) as exc_info:
            api.create_migration_preview("test", spec)

        assert "Invalid column length" in str(exc_info.value)

    @patch("dataflow.web.migration_api.AutoMigrationSystem")
    def test_excessive_length_rejected(self, mock_auto_migration):
        """Test that excessively large column lengths are rejected."""
        api = WebMigrationAPI("postgresql://user:pass@localhost:5432/db")

        spec = {
            "type": "create_table",
            "table_name": "users",
            "columns": [{"name": "name", "type": "VARCHAR", "length": 99999999}],
        }

        with pytest.raises(ValidationError) as exc_info:
            api.create_migration_preview("test", spec)

        assert "Invalid column length" in str(exc_info.value)


class TestDefaultValueValidation:
    """Test default value validation."""

    @patch("dataflow.web.migration_api.AutoMigrationSystem")
    def test_invalid_default_value_type(self, mock_auto_migration):
        """Test that complex default value types are rejected."""
        api = WebMigrationAPI("postgresql://user:pass@localhost:5432/db")

        spec = {
            "type": "create_table",
            "table_name": "users",
            "columns": [
                {"name": "data", "type": "TEXT", "default": {"complex": "object"}}
            ],
        }

        with pytest.raises(ValidationError) as exc_info:
            api.create_migration_preview("test", spec)

        assert "Invalid default value type" in str(exc_info.value)

    @patch("dataflow.web.migration_api.AutoMigrationSystem")
    def test_safe_default_values_accepted(self, mock_auto_migration):
        """Test that safe default values are accepted."""
        mock_system = MagicMock()
        mock_auto_migration.return_value = mock_system

        api = WebMigrationAPI("postgresql://user:pass@localhost:5432/db")

        # Safe default values
        safe_defaults = [
            ("active", str),  # String
            (123, int),  # Integer
            (12.34, float),  # Float
            (True, bool),  # Boolean
            (None, type(None)),  # Null
        ]

        for default_val, expected_type in safe_defaults:
            spec = {
                "type": "create_table",
                "table_name": "users",
                "columns": [{"name": "field", "type": "TEXT", "default": default_val}],
            }

            # Should not raise ValidationError
            try:
                api.create_migration_preview("test", spec)
            except ValidationError:
                pytest.fail(
                    f"Safe default value '{default_val}' ({expected_type.__name__}) was rejected"
                )


class TestMigrationDictSecurity:
    """Test security in _dict_to_migration."""

    @patch("dataflow.web.migration_api.AutoMigrationSystem")
    def test_invalid_table_name_in_migration_dict(self, mock_auto_migration):
        """Test that invalid table names in migration dict are rejected."""
        api = WebMigrationAPI("postgresql://user:pass@localhost:5432/db")

        migration_data = {
            "version": "20240101_120000",
            "operations": [
                {
                    "type": "create_table",
                    "table_name": "users; DROP TABLE accounts; --",
                    "sql": "CREATE TABLE users (id INT);",
                }
            ],
        }

        with pytest.raises(ValueError) as exc_info:
            api.validate_migration(migration_data)

        assert "Invalid table name" in str(exc_info.value)

"""
Tier 1 Unit Tests for WebMigrationAPI
Fast (<1s), isolated tests with mocks for external dependencies

Tests the WebMigrationAPI class that wraps VisualMigrationBuilder and AutoMigrationSystem
for web-based migration management.

Core Functionalities Tested:
1. Schema inspection endpoint
2. Migration preview generation
3. Migration validation
4. Session management for draft migrations
5. JSON serialization of migration definitions
"""

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from dataflow.migrations.auto_migration_system import (
    ColumnDefinition,
    Migration,
    MigrationOperation,
    MigrationType,
    TableDefinition,
)

# Import dependencies that will be mocked
from dataflow.migrations.visual_migration_builder import (
    ColumnBuilder,
    ColumnType,
    TableBuilder,
    VisualMigrationBuilder,
)


class TestWebMigrationAPIInitialization:
    """Test WebMigrationAPI initialization and basic setup."""

    def test_api_initialization_with_connection_string(self):
        """Test API can be initialized with database connection string."""
        from dataflow.web.migration_api import WebMigrationAPI

        connection_string = "postgresql://user:pass@localhost:5432/db"
        api = WebMigrationAPI(connection_string)

        assert api.connection_string == connection_string
        assert api.dialect == "postgresql"
        assert api.active_sessions == {}
        assert api.session_timeout == 3600  # 1 hour default

    def test_api_initialization_with_custom_dialect(self):
        """Test API initialization with custom dialect."""
        from dataflow.web.migration_api import WebMigrationAPI

        connection_string = "mysql://user:pass@localhost:3306/db"
        api = WebMigrationAPI(connection_string, dialect="mysql")

        assert api.dialect == "mysql"

    def test_api_initialization_with_custom_timeout(self):
        """Test API initialization with custom session timeout."""
        from dataflow.web.migration_api import WebMigrationAPI

        connection_string = "postgresql://user:pass@localhost:5432/db"
        api = WebMigrationAPI(connection_string, session_timeout=7200)

        assert api.session_timeout == 7200


class TestSchemaInspectionEndpoint:
    """Test schema inspection functionality."""

    @patch("dataflow.web.migration_api.create_engine")
    def test_inspect_schema_success(self, mock_create_engine):
        """Test successful schema inspection returns structured data."""
        from dataflow.web.migration_api import WebMigrationAPI

        # Mock database connection and schema inspection
        mock_engine = MagicMock()
        mock_create_engine.return_value = mock_engine

        mock_inspector = MagicMock()
        mock_engine.inspector.return_value = mock_inspector

        # Mock table and column data
        mock_inspector.get_table_names.return_value = ["users", "posts"]
        mock_inspector.get_columns.side_effect = [
            [
                {
                    "name": "id",
                    "type": "INTEGER",
                    "nullable": False,
                    "primary_key": True,
                },
                {
                    "name": "email",
                    "type": "VARCHAR(255)",
                    "nullable": False,
                    "unique": True,
                },
                {"name": "created_at", "type": "TIMESTAMP", "nullable": False},
            ],
            [
                {
                    "name": "id",
                    "type": "INTEGER",
                    "nullable": False,
                    "primary_key": True,
                },
                {"name": "title", "type": "VARCHAR(200)", "nullable": False},
                {"name": "content", "type": "TEXT", "nullable": True},
                {"name": "user_id", "type": "INTEGER", "nullable": False},
            ],
        ]

        # Mock additional inspector methods
        mock_inspector.get_pk_constraint.side_effect = [
            {"constrained_columns": ["id"]},  # users table
            {"constrained_columns": ["id"]},  # posts table
        ]
        mock_inspector.get_unique_constraints.return_value = []
        mock_inspector.get_foreign_keys.return_value = []
        mock_inspector.get_indexes.return_value = []

        api = WebMigrationAPI("postgresql://user:pass@localhost:5432/db")
        result = api.inspect_schema()

        assert "tables" in result
        assert len(result["tables"]) == 2
        assert result["tables"]["users"]["columns"]["id"]["type"] == "INTEGER"
        assert result["tables"]["users"]["columns"]["id"]["primary_key"] is True
        assert result["tables"]["posts"]["columns"]["content"]["nullable"] is True

    @patch("dataflow.web.migration_api.create_engine")
    def test_inspect_schema_connection_failure(self, mock_create_engine):
        """Test schema inspection handles connection failures gracefully."""
        from dataflow.web.migration_api import DatabaseConnectionError, WebMigrationAPI

        mock_create_engine.side_effect = Exception("Connection failed")

        api = WebMigrationAPI("postgresql://invalid:connection@localhost:5432/db")

        with pytest.raises(DatabaseConnectionError) as exc_info:
            api.inspect_schema()

        assert "Failed to connect to database" in str(exc_info.value)

    def test_inspect_schema_invalid_parameters(self):
        """Test schema inspection validates input parameters."""
        from dataflow.web.migration_api import ValidationError, WebMigrationAPI

        api = WebMigrationAPI("postgresql://user:pass@localhost:5432/db")

        # Test invalid schema name
        with pytest.raises(ValidationError) as exc_info:
            api.inspect_schema(schema_name="invalid;schema")

        assert "Invalid schema name" in str(exc_info.value)


class TestMigrationPreviewGeneration:
    """Test migration preview generation functionality."""

    @patch("dataflow.web.migration_api.VisualMigrationBuilder")
    def test_create_migration_preview_create_table(self, mock_builder_class):
        """Test migration preview for table creation."""
        from dataflow.web.migration_api import WebMigrationAPI

        # Mock VisualMigrationBuilder
        mock_builder = MagicMock()
        mock_builder_class.return_value = mock_builder

        # Mock table builder and column builder
        mock_table_builder = MagicMock()
        mock_column_builder = MagicMock()
        mock_builder.create_table.return_value = mock_table_builder
        mock_table_builder.add_column.return_value = mock_column_builder

        # Mock migration result
        mock_migration = MagicMock()
        mock_migration.preview.return_value = (
            "CREATE TABLE users (id INTEGER PRIMARY KEY, email VARCHAR(255) NOT NULL);"
        )
        mock_builder.build.return_value = mock_migration

        api = WebMigrationAPI("postgresql://user:pass@localhost:5432/db")

        migration_spec = {
            "type": "create_table",
            "table_name": "users",
            "columns": [
                {"name": "id", "type": "INTEGER", "primary_key": True},
                {"name": "email", "type": "VARCHAR", "length": 255, "nullable": False},
            ],
        }

        result = api.create_migration_preview("test_migration", migration_spec)

        assert "preview" in result
        assert "sql" in result["preview"]
        assert "operations" in result
        assert result["migration_name"] == "test_migration"
        assert "CREATE TABLE users" in result["preview"]["sql"]

    @patch("dataflow.web.migration_api.VisualMigrationBuilder")
    def test_create_migration_preview_add_column(self, mock_builder_class):
        """Test migration preview for adding column."""
        from dataflow.web.migration_api import WebMigrationAPI

        mock_builder = MagicMock()
        mock_builder_class.return_value = mock_builder

        mock_column_builder = MagicMock()
        mock_builder.add_column.return_value = mock_column_builder

        mock_migration = MagicMock()
        mock_migration.preview.return_value = (
            "ALTER TABLE users ADD COLUMN phone VARCHAR(20);"
        )
        mock_builder.build.return_value = mock_migration

        api = WebMigrationAPI("postgresql://user:pass@localhost:5432/db")

        migration_spec = {
            "type": "add_column",
            "table_name": "users",
            "column": {"name": "phone", "type": "VARCHAR", "length": 20},
        }

        result = api.create_migration_preview("add_phone_column", migration_spec)

        assert "ALTER TABLE users ADD COLUMN phone" in result["preview"]["sql"]
        mock_builder.add_column.assert_called_once_with(
            "users", "phone", ColumnType.VARCHAR
        )

    def test_create_migration_preview_invalid_type(self):
        """Test migration preview rejects invalid migration types."""
        from dataflow.web.migration_api import ValidationError, WebMigrationAPI

        api = WebMigrationAPI("postgresql://user:pass@localhost:5432/db")

        migration_spec = {"type": "invalid_operation", "table_name": "users"}

        with pytest.raises(ValidationError) as exc_info:
            api.create_migration_preview("invalid_migration", migration_spec)

        assert "Unsupported migration type" in str(exc_info.value)

    def test_create_migration_preview_missing_required_fields(self):
        """Test migration preview validates required fields."""
        from dataflow.web.migration_api import ValidationError, WebMigrationAPI

        api = WebMigrationAPI("postgresql://user:pass@localhost:5432/db")

        # Missing table_name
        migration_spec = {"type": "create_table"}

        with pytest.raises(ValidationError) as exc_info:
            api.create_migration_preview("incomplete_migration", migration_spec)

        assert "Missing required field" in str(exc_info.value)


class TestMigrationValidation:
    """Test migration validation functionality."""

    @patch("dataflow.web.migration_api.AutoMigrationSystem")
    def test_validate_migration_success(self, mock_auto_migration):
        """Test successful migration validation."""
        from dataflow.web.migration_api import WebMigrationAPI

        # Mock AutoMigrationSystem
        mock_system = MagicMock()
        mock_auto_migration.return_value = mock_system
        mock_system.validate_migration.return_value = {
            "valid": True,
            "warnings": [],
            "risks": ["low"],
        }

        api = WebMigrationAPI("postgresql://user:pass@localhost:5432/db")

        migration_data = {
            "version": "20240101_120000",
            "operations": [
                {
                    "type": "create_table",
                    "table_name": "products",
                    "sql": "CREATE TABLE products (id SERIAL PRIMARY KEY, name VARCHAR(255));",
                }
            ],
        }

        result = api.validate_migration(migration_data)

        assert result["valid"] is True
        assert "warnings" in result
        assert "risks" in result
        mock_system.validate_migration.assert_called_once()

    @patch("dataflow.web.migration_api.AutoMigrationSystem")
    def test_validate_migration_with_warnings(self, mock_auto_migration):
        """Test migration validation with warnings."""
        from dataflow.web.migration_api import WebMigrationAPI

        mock_system = MagicMock()
        mock_auto_migration.return_value = mock_system
        mock_system.validate_migration.return_value = {
            "valid": True,
            "warnings": ["Column 'email' should have UNIQUE constraint"],
            "risks": ["medium"],
        }

        api = WebMigrationAPI("postgresql://user:pass@localhost:5432/db")

        migration_data = {
            "version": "20240101_120000",
            "operations": [
                {
                    "type": "add_column",
                    "table_name": "users",
                    "sql": "ALTER TABLE users ADD COLUMN email VARCHAR(255);",
                }
            ],
        }

        result = api.validate_migration(migration_data)

        assert result["valid"] is True
        assert len(result["warnings"]) == 1
        assert "UNIQUE constraint" in result["warnings"][0]

    @patch("dataflow.web.migration_api.AutoMigrationSystem")
    def test_validate_migration_failure(self, mock_auto_migration):
        """Test migration validation failure."""
        from dataflow.web.migration_api import WebMigrationAPI

        mock_system = MagicMock()
        mock_auto_migration.return_value = mock_system
        mock_system.validate_migration.return_value = {
            "valid": False,
            "errors": ["Cannot drop table 'users' - contains data"],
            "risks": ["high"],
        }

        api = WebMigrationAPI("postgresql://user:pass@localhost:5432/db")

        migration_data = {
            "version": "20240101_120000",
            "operations": [
                {
                    "type": "drop_table",
                    "table_name": "users",
                    "sql": "DROP TABLE users;",
                }
            ],
        }

        result = api.validate_migration(migration_data)

        assert result["valid"] is False
        assert "errors" in result
        assert "contains data" in result["errors"][0]


class TestSessionManagement:
    """Test session management for draft migrations."""

    def test_create_session_success(self):
        """Test successful session creation."""
        from dataflow.web.migration_api import WebMigrationAPI

        api = WebMigrationAPI("postgresql://user:pass@localhost:5432/db")

        session_id = api.create_session("user123")

        assert session_id is not None
        assert len(session_id) == 36  # UUID length
        assert session_id in api.active_sessions
        assert api.active_sessions[session_id]["user_id"] == "user123"
        assert "created_at" in api.active_sessions[session_id]
        assert "draft_migrations" in api.active_sessions[session_id]

    def test_get_session_valid(self):
        """Test retrieving valid session."""
        from dataflow.web.migration_api import WebMigrationAPI

        api = WebMigrationAPI("postgresql://user:pass@localhost:5432/db")
        session_id = api.create_session("user123")

        session = api.get_session(session_id)

        assert session is not None
        assert session["user_id"] == "user123"

    def test_get_session_invalid(self):
        """Test retrieving invalid session."""
        from dataflow.web.migration_api import SessionNotFoundError, WebMigrationAPI

        api = WebMigrationAPI("postgresql://user:pass@localhost:5432/db")

        with pytest.raises(SessionNotFoundError):
            api.get_session("invalid-session-id")

    def test_add_draft_migration_to_session(self):
        """Test adding draft migration to session."""
        from dataflow.web.migration_api import WebMigrationAPI

        api = WebMigrationAPI("postgresql://user:pass@localhost:5432/db")
        session_id = api.create_session("user123")

        migration_draft = {
            "name": "add_user_table",
            "type": "create_table",
            "spec": {"table_name": "users", "columns": []},
        }

        api.add_draft_migration(session_id, migration_draft)

        session = api.get_session(session_id)
        assert len(session["draft_migrations"]) == 1
        assert session["draft_migrations"][0]["name"] == "add_user_table"

    def test_remove_draft_migration_from_session(self):
        """Test removing draft migration from session."""
        from dataflow.web.migration_api import WebMigrationAPI

        api = WebMigrationAPI("postgresql://user:pass@localhost:5432/db")
        session_id = api.create_session("user123")

        migration_draft = {
            "name": "add_user_table",
            "type": "create_table",
            "spec": {"table_name": "users", "columns": []},
        }

        draft_id = api.add_draft_migration(session_id, migration_draft)
        api.remove_draft_migration(session_id, draft_id)

        session = api.get_session(session_id)
        assert len(session["draft_migrations"]) == 0

    def test_session_cleanup_expired(self):
        """Test cleanup of expired sessions."""
        from dataflow.web.migration_api import WebMigrationAPI

        api = WebMigrationAPI("postgresql://test:test@localhost:5432/test")

        # Create multiple sessions with different expiration times
        session1_id = api.create_session("user1")
        session2_id = api.create_session("user2")

        # Manually set last_accessed times for testing (the actual implementation uses last_accessed)
        base_time = datetime.now()
        api.active_sessions[session1_id]["last_accessed"] = base_time - timedelta(
            seconds=3700
        )  # Expired (>3600s)
        api.active_sessions[session2_id]["last_accessed"] = base_time - timedelta(
            seconds=3
        )  # Not expired

        # Run cleanup
        api.cleanup_expired_sessions()

        # Check that only expired session was removed
        assert session1_id not in api.active_sessions
        assert session2_id in api.active_sessions

    def test_close_session(self):
        """Test manually closing session."""
        from dataflow.web.migration_api import WebMigrationAPI

        api = WebMigrationAPI("postgresql://user:pass@localhost:5432/db")
        session_id = api.create_session("user123")

        api.close_session(session_id)

        assert session_id not in api.active_sessions


class TestJSONSerialization:
    """Test JSON serialization of migration definitions."""

    def test_serialize_migration_definition(self):
        """Test serializing migration definition to JSON."""
        from dataflow.web.migration_api import WebMigrationAPI

        api = WebMigrationAPI("postgresql://user:pass@localhost:5432/db")

        migration_data = {
            "version": "20240101_120000",
            "name": "create_users_table",
            "operations": [
                {
                    "type": "create_table",
                    "table_name": "users",
                    "columns": [
                        {"name": "id", "type": "SERIAL", "primary_key": True},
                        {"name": "email", "type": "VARCHAR(255)", "nullable": False},
                    ],
                }
            ],
        }

        json_result = api.serialize_migration(migration_data)

        assert isinstance(json_result, str)
        parsed_data = json.loads(json_result)
        assert parsed_data["name"] == "create_users_table"
        assert len(parsed_data["operations"]) == 1

    def test_deserialize_migration_definition(self):
        """Test deserializing migration definition from JSON."""
        from dataflow.web.migration_api import WebMigrationAPI

        api = WebMigrationAPI("postgresql://user:pass@localhost:5432/db")

        json_data = """
        {
            "version": "20240101_120000",
            "name": "add_phone_column",
            "operations": [
                {
                    "type": "add_column",
                    "table_name": "users",
                    "column": {"name": "phone", "type": "VARCHAR(20)"}
                }
            ]
        }
        """

        migration_data = api.deserialize_migration(json_data)

        assert migration_data["name"] == "add_phone_column"
        assert migration_data["operations"][0]["type"] == "add_column"

    def test_serialize_schema_inspection_result(self):
        """Test serializing schema inspection results."""
        from dataflow.web.migration_api import WebMigrationAPI

        api = WebMigrationAPI("postgresql://user:pass@localhost:5432/db")

        schema_data = {
            "tables": {
                "users": {
                    "columns": {
                        "id": {
                            "type": "INTEGER",
                            "nullable": False,
                            "primary_key": True,
                        },
                        "email": {"type": "VARCHAR(255)", "nullable": False},
                    },
                    "indexes": ["idx_users_email"],
                    "constraints": ["users_pkey"],
                }
            },
            "metadata": {
                "schema_name": "public",
                "inspected_at": "2024-01-01T12:00:00Z",
            },
        }

        json_result = api.serialize_schema_data(schema_data)

        assert isinstance(json_result, str)
        parsed_data = json.loads(json_result)
        assert "tables" in parsed_data
        assert "users" in parsed_data["tables"]

    def test_json_serialization_handles_datetime(self):
        """Test JSON serialization properly handles datetime objects."""
        from dataflow.web.migration_api import WebMigrationAPI

        api = WebMigrationAPI("postgresql://user:pass@localhost:5432/db")

        data_with_datetime = {
            "created_at": datetime.now(),
            "migration_name": "test_migration",
        }

        json_result = api.serialize_migration(data_with_datetime)

        # Should not raise exception and should contain timestamp
        parsed_data = json.loads(json_result)
        assert "created_at" in parsed_data
        assert isinstance(parsed_data["created_at"], str)


class TestErrorHandling:
    """Test comprehensive error handling."""

    def test_database_connection_error_handling(self):
        """Test handling of database connection errors."""
        from dataflow.web.migration_api import DatabaseConnectionError, WebMigrationAPI

        api = WebMigrationAPI("postgresql://invalid:connection@localhost:5432/db")

        with patch("dataflow.web.migration_api.create_engine") as mock_create:
            mock_create.side_effect = Exception("Connection refused")

            with pytest.raises(DatabaseConnectionError):
                api.inspect_schema()

    def test_validation_error_handling(self):
        """Test handling of validation errors."""
        from dataflow.web.migration_api import ValidationError, WebMigrationAPI

        api = WebMigrationAPI("postgresql://user:pass@localhost:5432/db")

        # Invalid migration specification
        invalid_spec = {"type": "create_table"}  # Missing table_name

        with pytest.raises(ValidationError) as exc_info:
            api.create_migration_preview("invalid", invalid_spec)

        assert "Missing required field" in str(exc_info.value)

    def test_session_not_found_error_handling(self):
        """Test handling of session not found errors."""
        from dataflow.web.migration_api import SessionNotFoundError, WebMigrationAPI

        api = WebMigrationAPI("postgresql://user:pass@localhost:5432/db")

        with pytest.raises(SessionNotFoundError):
            api.get_session("nonexistent-session")

    def test_json_serialization_error_handling(self):
        """Test handling of JSON serialization errors."""
        from dataflow.web.migration_api import SerializationError, WebMigrationAPI

        api = WebMigrationAPI("postgresql://user:pass@localhost:5432/db")

        # Object that cannot be serialized
        class NonSerializable:
            pass

        invalid_data = {"object": NonSerializable()}

        with pytest.raises(SerializationError):
            api.serialize_migration(invalid_data)


class TestAPIIntegrationWithMigrationSystem:
    """Test integration with existing migration system components."""

    @patch("dataflow.web.migration_api.VisualMigrationBuilder")
    @patch("dataflow.web.migration_api.AutoMigrationSystem")
    def test_end_to_end_migration_workflow(
        self, mock_auto_migration, mock_builder_class
    ):
        """Test complete workflow from preview to validation."""
        from dataflow.web.migration_api import WebMigrationAPI

        # Setup mocks
        mock_builder = MagicMock()
        mock_builder_class.return_value = mock_builder

        mock_migration = MagicMock()
        mock_migration.preview.return_value = (
            "CREATE TABLE test (id SERIAL PRIMARY KEY);"
        )
        mock_migration.operations = [
            MagicMock(operation_type=MigrationType.CREATE_TABLE, table_name="test")
        ]
        mock_builder.build.return_value = mock_migration

        mock_system = MagicMock()
        mock_auto_migration.return_value = mock_system
        mock_system.validate_migration.return_value = {"valid": True, "warnings": []}

        api = WebMigrationAPI("postgresql://user:pass@localhost:5432/db")

        # Create migration preview
        migration_spec = {
            "type": "create_table",
            "table_name": "test",
            "columns": [{"name": "id", "type": "SERIAL", "primary_key": True}],
        }

        preview_result = api.create_migration_preview("test_migration", migration_spec)

        # Validate migration
        validation_result = api.validate_migration(
            {"version": "20240101_120000", "operations": preview_result["operations"]}
        )

        assert "CREATE TABLE test" in preview_result["preview"]["sql"]
        assert validation_result["valid"] is True
        mock_builder.create_table.assert_called_once_with("test")
        mock_system.validate_migration.assert_called_once()

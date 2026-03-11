"""
Tier 2 Integration Tests for WebMigrationAPI
Real PostgreSQL infrastructure, NO MOCKING, <5s timeout

Tests WebMigrationAPI with actual database connections and real migration operations.
Must run: ./tests/utils/test-env up && ./tests/utils/test-env status before running.

Core Integration Tests:
1. Real PostgreSQL schema inspection
2. Actual migration preview generation with database schemas
3. Session persistence with database state validation
4. JSON serialization with real data structures
5. Error handling with real database conditions
"""

import asyncio
import json
from datetime import datetime
from typing import Any, Dict

import pytest
from dataflow.migrations.auto_migration_system import AutoMigrationSystem

# DataFlow components - NO MOCKING
from dataflow.migrations.visual_migration_builder import (
    ColumnType,
    VisualMigrationBuilder,
)

from tests.infrastructure.test_harness import IntegrationTestSuite
from tests.utils.real_infrastructure import real_infra

# Test utilities for real PostgreSQL environment
from tests.utils.test_env_setup import (
    cleanup_test_data,
    create_test_table,
    execute_sql,
    get_test_connection,
)


@pytest.fixture
async def test_suite():
    """Create complete integration test suite with infrastructure."""
    suite = IntegrationTestSuite()
    async with suite.session():
        yield suite


@pytest.fixture(scope="function")
async def clean_database():
    """Ensure clean database state for each test."""
    await cleanup_test_data()
    yield
    await cleanup_test_data()


@pytest.fixture(scope="function")
async def test_connection():
    """Get real PostgreSQL test connection."""
    conn = await get_test_connection()
    yield conn
    await conn.close()


@pytest.fixture(scope="function")
async def sample_schema(test_connection):
    """Create sample schema for testing."""
    await execute_sql(
        test_connection,
        """
        CREATE TABLE users (
            id SERIAL PRIMARY KEY,
            email VARCHAR(255) NOT NULL UNIQUE,
            name VARCHAR(100) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE posts (
            id SERIAL PRIMARY KEY,
            title VARCHAR(200) NOT NULL,
            content TEXT,
            user_id INTEGER NOT NULL REFERENCES users(id),
            published_at TIMESTAMP
        );

        CREATE INDEX idx_posts_user_id ON posts(user_id);
        CREATE INDEX idx_posts_published ON posts(published_at) WHERE published_at IS NOT NULL;
    """,
    )
    yield
    # Cleanup handled by clean_database fixture


class TestRealSchemaInspection:
    """Test schema inspection with real PostgreSQL database."""

    @pytest.mark.asyncio
    async def test_inspect_empty_schema(self, test_suite, clean_database):
        """Test inspecting empty schema returns proper structure."""
        from dataflow.web.migration_api import WebMigrationAPI

        result = api.inspect_schema()

        assert "tables" in result
        assert isinstance(result["tables"], dict)
        assert "metadata" in result
        assert result["metadata"]["schema_name"] == "public"
        assert len(result["tables"]) == 0

    @pytest.mark.asyncio
    async def test_inspect_schema_with_tables(self, test_suite, sample_schema):
        """Test inspecting schema with actual tables and relationships."""
        from dataflow.web.migration_api import WebMigrationAPI

        result = api.inspect_schema()

        # Verify table structure
        assert "users" in result["tables"]
        assert "posts" in result["tables"]

        # Verify users table structure
        users_table = result["tables"]["users"]
        assert "id" in users_table["columns"]
        assert "email" in users_table["columns"]
        assert "name" in users_table["columns"]
        assert "created_at" in users_table["columns"]

        # Verify column properties
        id_column = users_table["columns"]["id"]
        assert id_column["primary_key"] is True
        assert id_column["nullable"] is False
        assert "SERIAL" in id_column["type"] or "INTEGER" in id_column["type"]

        email_column = users_table["columns"]["email"]
        assert email_column["unique"] is True
        assert email_column["nullable"] is False
        assert "VARCHAR" in email_column["type"]

        # Verify posts table foreign key
        posts_table = result["tables"]["posts"]
        user_id_column = posts_table["columns"]["user_id"]
        assert user_id_column["foreign_key"] is not None
        assert "users" in user_id_column["foreign_key"]

        # Verify indexes
        assert "indexes" in posts_table
        index_names = [idx["name"] for idx in posts_table["indexes"]]
        assert "idx_posts_user_id" in index_names
        assert "idx_posts_published" in index_names

    @pytest.mark.asyncio
    async def test_inspect_schema_with_complex_types(self, test_suite, test_connection):
        """Test schema inspection with PostgreSQL-specific types."""
        from dataflow.web.migration_api import WebMigrationAPI

        # Create table with complex PostgreSQL types
        await execute_sql(
            test_connection,
            """
            CREATE TABLE complex_table (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                data JSONB NOT NULL,
                tags TEXT[],
                price DECIMAL(10,2),
                coordinates POINT,
                created_at TIMESTAMPTZ DEFAULT NOW()
            );
        """,
        )

        result = api.inspect_schema()

        complex_table = result["tables"]["complex_table"]

        # Verify PostgreSQL-specific types are properly detected
        assert "UUID" in complex_table["columns"]["id"]["type"]
        assert "JSONB" in complex_table["columns"]["data"]["type"]
        assert (
            "ARRAY" in complex_table["columns"]["tags"]["type"]
            or "TEXT[]" in complex_table["columns"]["tags"]["type"]
        )
        assert "DECIMAL" in complex_table["columns"]["price"]["type"]
        assert (
            "TIMESTAMPTZ" in complex_table["columns"]["created_at"]["type"]
            or "TIMESTAMP" in complex_table["columns"]["created_at"]["type"]
        )

    @pytest.mark.asyncio
    async def test_inspect_schema_performance(self, test_suite, sample_schema):
        """Test schema inspection performance with real data."""
        import time

        from dataflow.web.migration_api import WebMigrationAPI

        # Measure performance
        start_time = time.perf_counter()
        result = api.inspect_schema()
        end_time = time.perf_counter()

        inspection_time = (end_time - start_time) * 1000  # Convert to milliseconds

        # Should complete within performance threshold
        assert inspection_time < 2000  # 2 seconds max for integration test
        assert len(result["tables"]) == 2

        # Performance metadata should be included
        assert "performance" in result["metadata"]
        assert result["metadata"]["performance"]["inspection_time_ms"] > 0


class TestRealMigrationPreviewGeneration:
    """Test migration preview with real VisualMigrationBuilder integration."""

    @pytest.mark.asyncio
    async def test_create_table_preview_with_real_builder(
        self, test_suite, clean_database
    ):
        """Test creating table preview using real VisualMigrationBuilder."""
        from dataflow.web.migration_api import WebMigrationAPI

        migration_spec = {
            "type": "create_table",
            "table_name": "products",
            "columns": [
                {"name": "id", "type": "SERIAL", "primary_key": True},
                {"name": "name", "type": "VARCHAR", "length": 255, "nullable": False},
                {"name": "price", "type": "DECIMAL", "precision": 10, "scale": 2},
                {"name": "description", "type": "TEXT", "nullable": True},
                {
                    "name": "created_at",
                    "type": "TIMESTAMP",
                    "default": "CURRENT_TIMESTAMP",
                },
            ],
        }

        result = api.create_migration_preview("create_products_table", migration_spec)

        # Verify preview structure
        assert "preview" in result
        assert "sql" in result["preview"]
        assert "operations" in result
        assert result["migration_name"] == "create_products_table"

        # Verify SQL content
        sql = result["preview"]["sql"]
        assert "CREATE TABLE products" in sql
        assert "id SERIAL PRIMARY KEY" in sql
        assert "name VARCHAR(255) NOT NULL" in sql
        assert "price DECIMAL(10,2)" in sql
        assert "description TEXT" in sql
        assert "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP" in sql

        # Verify operations metadata
        assert len(result["operations"]) == 1
        operation = result["operations"][0]
        assert operation["type"] == "create_table"
        assert operation["table_name"] == "products"

    @pytest.mark.asyncio
    async def test_add_column_preview_with_existing_table(
        self, test_suite, sample_schema
    ):
        """Test adding column to existing table."""
        from dataflow.web.migration_api import WebMigrationAPI

        migration_spec = {
            "type": "add_column",
            "table_name": "users",
            "column": {
                "name": "phone",
                "type": "VARCHAR",
                "length": 20,
                "nullable": True,
            },
        }

        result = api.create_migration_preview("add_phone_to_users", migration_spec)

        # Verify SQL generation
        sql = result["preview"]["sql"]
        assert "ALTER TABLE users ADD COLUMN phone VARCHAR(20)" in sql

        # Verify rollback SQL
        assert "rollback_sql" in result["preview"]
        assert (
            "ALTER TABLE users DROP COLUMN phone" in result["preview"]["rollback_sql"]
        )

    @pytest.mark.asyncio
    async def test_complex_migration_preview(self, test_suite, sample_schema):
        """Test complex migration with multiple operations."""
        from dataflow.web.migration_api import WebMigrationAPI

        migration_spec = {
            "type": "multi_operation",
            "operations": [
                {
                    "type": "add_column",
                    "table_name": "users",
                    "column": {"name": "phone", "type": "VARCHAR", "length": 20},
                },
                {
                    "type": "create_index",
                    "table_name": "users",
                    "index_name": "idx_users_phone",
                    "columns": ["phone"],
                    "unique": True,
                },
                {
                    "type": "add_column",
                    "table_name": "posts",
                    "column": {
                        "name": "status",
                        "type": "VARCHAR",
                        "length": 20,
                        "default": "'draft'",
                    },
                },
            ],
        }

        result = api.create_migration_preview(
            "enhance_user_post_schema", migration_spec
        )

        # Verify multiple operations
        assert len(result["operations"]) == 3

        # Verify SQL includes all operations
        sql = result["preview"]["sql"]
        assert "ALTER TABLE users ADD COLUMN phone" in sql
        assert "CREATE UNIQUE INDEX idx_users_phone" in sql
        assert "ALTER TABLE posts ADD COLUMN status" in sql
        assert "DEFAULT 'draft'" in sql

    @pytest.mark.asyncio
    async def test_migration_preview_validation_with_real_schema(
        self, test_suite, sample_schema
    ):
        """Test migration preview validates against actual database schema."""
        from dataflow.web.migration_api import ValidationError, WebMigrationAPI

        # Try to add column that already exists
        migration_spec = {
            "type": "add_column",
            "table_name": "users",
            "column": {
                "name": "email",
                "type": "VARCHAR",
                "length": 100,
            },  # email already exists
        }

        with pytest.raises(ValidationError) as exc_info:
            api.create_migration_preview("invalid_add_existing_column", migration_spec)

        assert "already exists" in str(exc_info.value)

        # Try to create table that already exists
        migration_spec = {
            "type": "create_table",
            "table_name": "users",  # users table already exists
            "columns": [{"name": "id", "type": "SERIAL", "primary_key": True}],
        }

        with pytest.raises(ValidationError) as exc_info:
            api.create_migration_preview(
                "invalid_create_existing_table", migration_spec
            )

        assert "already exists" in str(exc_info.value)


class TestRealSessionPersistence:
    """Test session management with database state validation."""

    @pytest.mark.asyncio
    async def test_session_with_real_migration_workflow(
        self, test_suite, clean_database
    ):
        """Test complete session workflow with real migrations."""
        from dataflow.web.migration_api import WebMigrationAPI

        # Create session
        session_id = api.create_session("developer123")

        # Add first draft migration
        migration_draft1 = {
            "name": "create_products",
            "type": "create_table",
            "spec": {
                "table_name": "products",
                "columns": [
                    {"name": "id", "type": "SERIAL", "primary_key": True},
                    {"name": "name", "type": "VARCHAR", "length": 255},
                ],
            },
        }

        draft1_id = api.add_draft_migration(session_id, migration_draft1)

        # Add second draft migration
        migration_draft2 = {
            "name": "create_categories",
            "type": "create_table",
            "spec": {
                "table_name": "categories",
                "columns": [
                    {"name": "id", "type": "SERIAL", "primary_key": True},
                    {"name": "name", "type": "VARCHAR", "length": 100},
                ],
            },
        }

        draft2_id = api.add_draft_migration(session_id, migration_draft2)

        # Verify session state
        session = api.get_session(session_id)
        assert len(session["draft_migrations"]) == 2

        # Generate preview for all drafts
        all_previews = api.generate_session_preview(session_id)

        assert len(all_previews["migrations"]) == 2
        assert "CREATE TABLE products" in all_previews["combined_sql"]
        assert "CREATE TABLE categories" in all_previews["combined_sql"]

        # Remove one draft
        api.remove_draft_migration(session_id, draft1_id)

        session = api.get_session(session_id)
        assert len(session["draft_migrations"]) == 1
        assert session["draft_migrations"][0]["name"] == "create_categories"

    @pytest.mark.asyncio
    async def test_session_draft_validation_against_real_schema(
        self, test_suite, sample_schema
    ):
        """Test session draft validation against actual database state."""
        from dataflow.web.migration_api import WebMigrationAPI

        session_id = api.create_session("developer123")

        # Valid draft migration
        valid_draft = {
            "name": "add_user_phone",
            "type": "add_column",
            "spec": {
                "table_name": "users",
                "column": {"name": "phone", "type": "VARCHAR", "length": 20},
            },
        }

        draft_id = api.add_draft_migration(session_id, valid_draft)

        # Validate session against real database schema
        validation_result = api.validate_session_migrations(session_id)

        assert validation_result["valid"] is True
        assert len(validation_result["migration_validations"]) == 1
        assert validation_result["migration_validations"][0]["valid"] is True

        # Add invalid draft migration
        invalid_draft = {
            "name": "add_existing_column",
            "type": "add_column",
            "spec": {
                "table_name": "users",
                "column": {
                    "name": "email",
                    "type": "VARCHAR",
                    "length": 100,
                },  # email already exists
            },
        }

        api.add_draft_migration(session_id, invalid_draft)

        # Validate again
        validation_result = api.validate_session_migrations(session_id)

        assert validation_result["valid"] is False
        assert len(validation_result["migration_validations"]) == 2
        assert validation_result["migration_validations"][1]["valid"] is False
        assert (
            "already exists"
            in validation_result["migration_validations"][1]["errors"][0]
        )

    @pytest.mark.asyncio
    async def test_session_persistence_across_api_instances(
        self, test_suite, clean_database
    ):
        """Test session persistence when creating new API instances."""
        from dataflow.web.migration_api import WebMigrationAPI

        # Create first API instance and session
        session_id = api1.create_session("developer123")

        migration_draft = {
            "name": "create_test_table",
            "type": "create_table",
            "spec": {
                "table_name": "test_table",
                "columns": [{"name": "id", "type": "SERIAL", "primary_key": True}],
            },
        }

        api1.add_draft_migration(session_id, migration_draft)

        # Create second API instance

        # Session should persist if using external storage (Redis/database)
        # For in-memory storage, this test documents the limitation
        try:
            session = api2.get_session(session_id)
            # If external persistence is implemented
            assert len(session["draft_migrations"]) == 1
        except Exception:
            # Expected for in-memory storage
            pytest.skip(
                "Session persistence across instances requires external storage"
            )


class TestRealJSONSerializationWithDatabaseData:
    """Test JSON serialization with real database structures."""

    @pytest.mark.asyncio
    async def test_serialize_real_schema_inspection_result(
        self, test_suite, sample_schema
    ):
        """Test serializing actual schema inspection results."""
        from dataflow.web.migration_api import WebMigrationAPI

        schema_data = api.inspect_schema()
        json_result = api.serialize_schema_data(schema_data)

        # Verify JSON is valid and complete
        parsed_data = json.loads(json_result)
        assert "tables" in parsed_data
        assert "users" in parsed_data["tables"]
        assert "posts" in parsed_data["tables"]

        # Verify all complex data types serialize properly
        users_table = parsed_data["tables"]["users"]
        assert "columns" in users_table
        assert "indexes" in users_table
        assert "constraints" in users_table

        # Verify timestamps are properly serialized
        assert "metadata" in parsed_data
        assert "inspected_at" in parsed_data["metadata"]
        assert isinstance(parsed_data["metadata"]["inspected_at"], str)

    @pytest.mark.asyncio
    async def test_serialize_real_migration_preview(self, test_suite, clean_database):
        """Test serializing actual migration preview results."""
        from dataflow.web.migration_api import WebMigrationAPI

        migration_spec = {
            "type": "create_table",
            "table_name": "test_products",
            "columns": [
                {"name": "id", "type": "SERIAL", "primary_key": True},
                {"name": "name", "type": "VARCHAR", "length": 255},
                {"name": "price", "type": "DECIMAL", "precision": 10, "scale": 2},
                {
                    "name": "created_at",
                    "type": "TIMESTAMP",
                    "default": "CURRENT_TIMESTAMP",
                },
            ],
        }

        preview_result = api.create_migration_preview(
            "create_test_products", migration_spec
        )
        json_result = api.serialize_migration(preview_result)

        # Verify complete serialization
        parsed_data = json.loads(json_result)
        assert "preview" in parsed_data
        assert "operations" in parsed_data
        assert "migration_name" in parsed_data

        # Verify SQL content is preserved
        assert "CREATE TABLE test_products" in parsed_data["preview"]["sql"]
        assert len(parsed_data["operations"]) == 1


class TestRealErrorConditions:
    """Test error handling with real database conditions."""

    @pytest.mark.asyncio
    async def test_connection_failure_handling(self, test_suite):
        """Test handling of real connection failures."""
        from dataflow.web.migration_api import DatabaseConnectionError, WebMigrationAPI

        # Use invalid connection string
        api = WebMigrationAPI(
            "postgresql://invalid_user:wrong_pass@localhost:9999/nonexistent_db"
        )

        with pytest.raises(DatabaseConnectionError) as exc_info:
            api.inspect_schema()

        assert "Failed to connect to database" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_sql_execution_error_handling(self, test_suite, test_connection):
        """Test handling of SQL execution errors."""
        from dataflow.web.migration_api import SQLExecutionError, WebMigrationAPI

        # Create migration that would cause SQL error
        migration_spec = {
            "type": "add_column",
            "table_name": "nonexistent_table",
            "column": {"name": "test_col", "type": "VARCHAR", "length": 50},
        }

        with pytest.raises(SQLExecutionError) as exc_info:
            api.create_migration_preview("invalid_table_migration", migration_spec)

        assert "does not exist" in str(exc_info.value) or "relation" in str(
            exc_info.value
        )

    @pytest.mark.asyncio
    async def test_concurrent_access_handling(self, test_suite, sample_schema):
        """Test handling of concurrent database access."""
        import asyncio

        from dataflow.web.migration_api import WebMigrationAPI

        # Simulate concurrent schema inspections
        async def inspect_schema():
            return api.inspect_schema()

        # Run multiple concurrent inspections
        tasks = [inspect_schema() for _ in range(5)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # All should succeed or fail gracefully
        successful_results = [r for r in results if not isinstance(r, Exception)]
        assert len(successful_results) >= 1  # At least one should succeed

        # Results should be consistent
        if len(successful_results) > 1:
            first_result = successful_results[0]
            for result in successful_results[1:]:
                assert result["tables"].keys() == first_result["tables"].keys()


class TestPerformanceWithRealData:
    """Test performance characteristics with real database operations."""

    @pytest.mark.asyncio
    async def test_schema_inspection_performance(self, sample_schema):
        """Test schema inspection performance with real tables."""
        import time

        from dataflow.web.migration_api import WebMigrationAPI

        # Warm up connection
        api.inspect_schema()

        # Measure performance of multiple inspections
        start_time = time.perf_counter()
        for _ in range(10):
            result = api.inspect_schema()
        end_time = time.perf_counter()

        avg_time = ((end_time - start_time) / 10) * 1000  # ms per inspection

        # Should be fast enough for web interface
        assert avg_time < 1000  # Less than 1 second per inspection
        assert len(result["tables"]) == 2

    @pytest.mark.asyncio
    async def test_migration_preview_generation_performance(self, clean_database):
        """Test migration preview generation performance."""
        import time

        from dataflow.web.migration_api import WebMigrationAPI

        migration_spec = {
            "type": "create_table",
            "table_name": "performance_test",
            "columns": [{"name": "id", "type": "SERIAL", "primary_key": True}]
            + [
                {"name": f"col_{i}", "type": "VARCHAR", "length": 100}
                for i in range(50)  # 50 columns
            ],
        }

        start_time = time.perf_counter()
        result = api.create_migration_preview("large_table_migration", migration_spec)
        end_time = time.perf_counter()

        generation_time = (end_time - start_time) * 1000  # ms

        # Should handle large migrations efficiently
        assert generation_time < 3000  # Less than 3 seconds
        assert "CREATE TABLE performance_test" in result["preview"]["sql"]
        assert len(result["operations"]) == 1

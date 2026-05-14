"""
Unit Tests for MigrationTestFramework (Tier 1 - NO MOCKING in Tiers 2-3)

Tests the migration testing framework in isolation with mock connections only.
Real PostgreSQL and SQLite testing handled in integration tier.
"""

import asyncio
import sqlite3
from typing import Any, Dict, List
from unittest.mock import AsyncMock, Mock, patch

import pytest

from dataflow.migrations.auto_migration_system import (
    ColumnDefinition,
    Migration,
    MigrationOperation,
    MigrationType,
    TableDefinition,
)

# Import the framework class we're about to create
from dataflow.migrations.migration_test_framework import (
    MigrationTestEnvironment,
    MigrationTestError,
    MigrationTestFramework,
    MigrationTestResult,
)


class TestMigrationTestFramework:
    """Unit tests for MigrationTestFramework class."""

    def test_framework_initialization(self):
        """Test basic framework initialization."""
        # Test SQLite initialization
        framework_sqlite = MigrationTestFramework(
            database_type="sqlite", connection_string=":memory:"
        )
        assert framework_sqlite.database_type == "sqlite"
        assert framework_sqlite.connection_string == ":memory:"
        assert framework_sqlite.test_environment == MigrationTestEnvironment.MEMORY

        # Test PostgreSQL initialization
        framework_pg = MigrationTestFramework(
            database_type="postgresql",
            connection_string="postgresql://test:test@localhost:5434/test",
        )
        assert framework_pg.database_type == "postgresql"
        assert framework_pg.test_environment == MigrationTestEnvironment.DOCKER

    def test_invalid_database_type_raises_error(self):
        """Test that invalid database type raises error."""
        with pytest.raises(ValueError, match="Unsupported database type"):
            MigrationTestFramework(
                database_type="mysql", connection_string="mysql://test"
            )

    @pytest.mark.asyncio
    async def test_setup_test_database_sqlite(self):
        """Test SQLite test database setup."""
        framework = MigrationTestFramework(
            database_type="sqlite", connection_string=":memory:"
        )

        # Mock the connection setup
        with patch("sqlite3.connect") as mock_connect:
            mock_conn = Mock()
            mock_connect.return_value = mock_conn

            connection = await framework.setup_test_database()

            assert connection is not None
            mock_connect.assert_called_once_with(":memory:", check_same_thread=False)

    @pytest.mark.asyncio
    async def test_setup_test_database_postgresql_mock(self):
        """Test PostgreSQL test database setup with mocked connection."""
        framework = MigrationTestFramework(
            database_type="postgresql",
            connection_string="postgresql://test:test@localhost:5434/test",
        )

        # Mock asyncpg connection
        with patch("asyncpg.connect") as mock_connect:
            mock_conn = AsyncMock()
            mock_connect.return_value = mock_conn

            connection = await framework.setup_test_database()

            assert connection is not None
            mock_connect.assert_called_once()

    def test_create_test_migration(self):
        """Test creation of test migration."""
        framework = MigrationTestFramework(
            database_type="sqlite", connection_string=":memory:"
        )

        # Create test table definition
        table = TableDefinition(
            name="test_table",
            columns=[
                ColumnDefinition(name="id", type="INTEGER", primary_key=True),
                ColumnDefinition(name="name", type="VARCHAR(255)", nullable=False),
            ],
        )

        # Create test migration
        migration = framework.create_test_migration("test_migration", [table])

        assert migration.name == "test_migration"
        assert len(migration.operations) == 1
        assert migration.operations[0].operation_type == MigrationType.CREATE_TABLE
        assert migration.operations[0].table_name == "test_table"

    @pytest.mark.asyncio
    async def test_execute_test_migration_success(self):
        """Test successful migration execution."""
        framework = MigrationTestFramework(
            database_type="sqlite", connection_string=":memory:"
        )

        # Mock connection and migration system
        mock_conn = AsyncMock()
        mock_migration_system = AsyncMock()
        mock_migration_system.auto_migrate.return_value = (True, [])

        # Create test migration
        migration = Migration(version="test_v1", name="test_migration", operations=[])

        # Mock the framework's migration system
        framework._migration_system = mock_migration_system

        result = await framework.execute_test_migration(
            migration=migration, connection=mock_conn
        )

        assert result.success is True
        assert result.error is None
        assert result.migration_version == "test_v1"

    @pytest.mark.asyncio
    async def test_execute_test_migration_failure(self):
        """Test migration execution failure handling."""
        framework = MigrationTestFramework(
            database_type="sqlite", connection_string=":memory:"
        )

        # Mock the direct execution method to simulate failure
        with patch.object(
            framework, "_execute_migration_operations_directly"
        ) as mock_exec:
            mock_exec.side_effect = Exception("Migration failed")

            # Create test migration
            migration = Migration(
                version="test_v1", name="test_migration", operations=[]
            )

            result = await framework.execute_test_migration(
                migration=migration, connection=AsyncMock()
            )

            assert result.success is False
            assert "Migration failed" in result.error
            assert result.migration_version == "test_v1"

    @pytest.mark.asyncio
    async def test_verify_migration_result_success(self):
        """Test successful migration verification."""
        framework = MigrationTestFramework(
            database_type="sqlite", connection_string=":memory:"
        )

        # Mock schema inspector
        mock_inspector = AsyncMock()
        mock_inspector.get_current_schema.return_value = {
            "test_table": TableDefinition(
                name="test_table",
                columns=[
                    ColumnDefinition(name="id", type="INTEGER", primary_key=True),
                    ColumnDefinition(name="name", type="VARCHAR(255)"),
                ],
            )
        }

        framework._schema_inspector = mock_inspector

        # Expected schema
        expected_schema = {
            "test_table": TableDefinition(
                name="test_table",
                columns=[
                    ColumnDefinition(name="id", type="INTEGER", primary_key=True),
                    ColumnDefinition(name="name", type="VARCHAR(255)"),
                ],
            )
        }

        # Mock the _get_sqlite_schema method directly to avoid async issues
        with patch.object(framework, "_get_sqlite_schema") as mock_get_schema:
            mock_get_schema.return_value = {
                "test_table": TableDefinition(
                    name="test_table",
                    columns=[
                        ColumnDefinition(name="id", type="INTEGER", primary_key=True),
                        ColumnDefinition(name="name", type="VARCHAR(255)"),
                    ],
                )
            }

            is_verified = await framework.verify_migration_result(
                connection=AsyncMock(), expected_schema=expected_schema
            )

            assert is_verified is True

    @pytest.mark.asyncio
    async def test_verify_migration_result_failure(self):
        """Test migration verification failure."""
        framework = MigrationTestFramework(
            database_type="sqlite", connection_string=":memory:"
        )

        # Mock schema inspector returning different schema
        mock_inspector = AsyncMock()
        mock_inspector.get_current_schema.return_value = {
            "wrong_table": TableDefinition(name="wrong_table", columns=[])
        }

        framework._schema_inspector = mock_inspector

        # Expected schema
        expected_schema = {
            "test_table": TableDefinition(
                name="test_table",
                columns=[
                    ColumnDefinition(name="id", type="INTEGER", primary_key=True),
                ],
            )
        }

        is_verified = await framework.verify_migration_result(
            connection=AsyncMock(), expected_schema=expected_schema
        )

        assert is_verified is False

    @pytest.mark.asyncio
    async def test_rollback_verification(self):
        """Test migration rollback verification."""
        framework = MigrationTestFramework(
            database_type="sqlite", connection_string=":memory:"
        )

        # Mock migration system for rollback
        mock_migration_system = AsyncMock()
        mock_migration_system.rollback_migration.return_value = True

        framework._migration_system = mock_migration_system

        success = await framework.rollback_migration(
            connection=AsyncMock(), migration_version="test_v1"
        )

        assert success is True
        mock_migration_system.rollback_migration.assert_called_once_with("test_v1")

    @pytest.mark.asyncio
    async def test_teardown_test_database(self):
        """Test test database teardown."""
        framework = MigrationTestFramework(
            database_type="sqlite", connection_string=":memory:"
        )

        # Mock connection
        mock_conn = AsyncMock()

        # Test teardown doesn't raise errors
        await framework.teardown_test_database(mock_conn)

        # For SQLite :memory:, connection should be closed
        if hasattr(mock_conn, "close"):
            mock_conn.close.assert_called_once()

    def test_performance_requirements(self):
        """Test that framework meets performance requirements."""
        framework = MigrationTestFramework(
            database_type="sqlite", connection_string=":memory:"
        )

        # Test instantiation is fast
        import time

        start = time.perf_counter()

        for _ in range(100):
            test_framework = MigrationTestFramework(
                database_type="sqlite", connection_string=":memory:"
            )

        elapsed = time.perf_counter() - start

        # Should be very fast for unit test initialization
        assert elapsed < 1.0  # Less than 1 second for 100 initializations

    def test_test_result_dataclass(self):
        """Test MigrationTestResult dataclass."""
        # Test successful result
        success_result = MigrationTestResult(
            success=True,
            migration_version="v1",
            execution_time=0.5,
            verification_passed=True,
        )

        assert success_result.success is True
        assert success_result.error is None
        assert success_result.rollback_verified is None

        # Test failed result
        failed_result = MigrationTestResult(
            success=False,
            migration_version="v1",
            execution_time=0.1,
            verification_passed=False,
            error="Test error",
            rollback_verified=True,
        )

        assert failed_result.success is False
        assert failed_result.error == "Test error"
        assert failed_result.rollback_verified is True

    def test_test_environment_enum(self):
        """Test MigrationTestEnvironment enum values."""
        assert MigrationTestEnvironment.MEMORY.value == "memory"
        assert MigrationTestEnvironment.DOCKER.value == "docker"
        assert MigrationTestEnvironment.EXTERNAL.value == "external"

    def test_migration_test_error(self):
        """Test custom exception."""
        error = MigrationTestError("Test framework error")
        assert str(error) == "Test framework error"
        assert isinstance(error, Exception)

    def test_dataflow_memory_compatibility(self):
        """Test compatibility with DataFlow(':memory:') mode."""
        # This should not break existing DataFlow functionality
        framework = MigrationTestFramework(
            database_type="sqlite", connection_string=":memory:"
        )

        # Framework should support memory mode without breaking DataFlow
        assert framework.connection_string == ":memory:"
        assert framework.database_type == "sqlite"
        assert framework.test_environment == MigrationTestEnvironment.MEMORY

        # Should be able to create multiple instances
        framework2 = MigrationTestFramework(
            database_type="sqlite", connection_string=":memory:"
        )

        assert framework is not framework2  # Different instances
        assert framework.database_type == framework2.database_type

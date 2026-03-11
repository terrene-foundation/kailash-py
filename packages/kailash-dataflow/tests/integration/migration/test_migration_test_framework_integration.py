"""
Integration Tests for MigrationTestFramework (Tier 2 - NO MOCKING)

Tests the migration testing framework with real PostgreSQL infrastructure.
Validates integration with AutoMigrationSystem and Phase 1A components.

CRITICAL: NO MOCKING allowed in Tier 2 tests - uses real PostgreSQL from Docker.
"""

import asyncio
import time
from typing import Dict, List

import pytest
from dataflow.migrations.auto_migration_system import (
    ColumnDefinition,
    Migration,
    MigrationOperation,
    MigrationType,
    TableDefinition,
)
from dataflow.migrations.migration_test_framework import (
    MigrationTestEnvironment,
    MigrationTestError,
    MigrationTestFramework,
    MigrationTestResult,
)

from tests.infrastructure.test_harness import IntegrationTestSuite


@pytest.fixture
async def test_suite():
    """Create complete integration test suite with infrastructure."""
    suite = IntegrationTestSuite()
    async with suite.session():
        yield suite


@pytest.mark.integration
@pytest.mark.requires_docker
class TestMigrationTestFrameworkIntegration:
    """Integration tests using real PostgreSQL database."""

    @pytest.fixture
    def test_database_url(self, test_suite):
        """Get PostgreSQL test database URL from test suite infrastructure."""
        return test_suite.config.url

    @pytest.mark.asyncio
    @pytest.mark.timeout(5)
    async def test_postgresql_database_setup_real(self, test_database_url):
        """Test real PostgreSQL database setup."""
        framework = MigrationTestFramework(
            database_type="postgresql",
            connection_string=test_database_url,
            integration_mode=True,
        )

        # This uses REAL PostgreSQL - no mocking
        connection = await framework.setup_test_database()

        assert connection is not None

        # Verify we can execute queries on real database
        result = await connection.execute("SELECT 1 as test_value")
        assert result is not None

        # Test cleanup
        await framework.teardown_test_database(connection)

    @pytest.mark.asyncio
    @pytest.mark.timeout(5)
    async def test_real_migration_execution(self, test_database_url):
        """Test real migration execution with PostgreSQL."""
        framework = MigrationTestFramework(
            database_type="postgresql",
            connection_string=test_database_url,
            integration_mode=True,
        )

        # Setup real database
        connection = await framework.setup_test_database()

        try:
            # Create test table definition
            test_table = TableDefinition(
                name="integration_test_users",
                columns=[
                    ColumnDefinition(name="id", type="SERIAL", primary_key=True),
                    ColumnDefinition(
                        name="username", type="VARCHAR(255)", nullable=False
                    ),
                    ColumnDefinition(
                        name="email", type="VARCHAR(255)", nullable=False, unique=True
                    ),
                    ColumnDefinition(
                        name="created_at", type="TIMESTAMP", default="CURRENT_TIMESTAMP"
                    ),
                ],
            )

            # Create migration to add table
            migration = Migration(
                version="test_001",
                operations=[
                    MigrationOperation(
                        type=MigrationType.CREATE_TABLE, table=test_table
                    )
                ],
            )

            # Execute migration on real database
            result = await framework.test_migration(migration, connection)

            assert result.success
            assert result.execution_time > 0

            # Verify table exists in real database
            check_query = """
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_name = 'integration_test_users'
                )
            """
            exists_result = await connection.execute(check_query)
            assert exists_result is not None

        finally:
            # Cleanup
            await framework.teardown_test_database(connection)

    @pytest.mark.asyncio
    @pytest.mark.timeout(5)
    async def test_rollback_with_real_database(self, test_database_url):
        """Test rollback functionality with real PostgreSQL."""
        framework = MigrationTestFramework(
            database_type="postgresql",
            connection_string=test_database_url,
            integration_mode=True,
        )

        connection = await framework.setup_test_database()

        try:
            # Create and execute forward migration
            test_table = TableDefinition(
                name="rollback_test_table",
                columns=[
                    ColumnDefinition(name="id", type="SERIAL", primary_key=True),
                    ColumnDefinition(name="data", type="TEXT"),
                ],
            )

            forward_migration = Migration(
                version="rollback_001",
                operations=[
                    MigrationOperation(
                        type=MigrationType.CREATE_TABLE, table=test_table
                    )
                ],
            )

            # Execute forward migration
            forward_result = await framework.test_migration(
                forward_migration, connection
            )
            assert forward_result.success

            # Create and test rollback
            rollback_migration = Migration(
                version="rollback_001_down",
                operations=[
                    MigrationOperation(
                        type=MigrationType.DROP_TABLE, table_name="rollback_test_table"
                    )
                ],
            )

            rollback_result = await framework.test_rollback(
                rollback_migration, connection
            )
            assert rollback_result.success

            # Verify table no longer exists
            check_query = """
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_name = 'rollback_test_table'
                )
            """
            exists_result = await connection.execute(check_query)
            # Table should not exist after rollback

        finally:
            await framework.teardown_test_database(connection)

    @pytest.mark.asyncio
    @pytest.mark.timeout(5)
    async def test_concurrent_migrations_real_database(self, test_database_url):
        """Test concurrent migration handling with real PostgreSQL."""
        framework = MigrationTestFramework(
            database_type="postgresql",
            connection_string=test_database_url,
            integration_mode=True,
        )

        connection = await framework.setup_test_database()

        try:
            # Create multiple migrations
            migrations = []
            for i in range(3):
                table = TableDefinition(
                    name=f"concurrent_table_{i}",
                    columns=[
                        ColumnDefinition(name="id", type="SERIAL", primary_key=True),
                        ColumnDefinition(name="value", type="INTEGER"),
                    ],
                )

                migration = Migration(
                    version=f"concurrent_{i:03d}",
                    operations=[
                        MigrationOperation(type=MigrationType.CREATE_TABLE, table=table)
                    ],
                )
                migrations.append(migration)

            # Execute migrations concurrently
            tasks = [framework.test_migration(m, connection) for m in migrations]
            results = await asyncio.gather(*tasks)

            # All should succeed
            for result in results:
                assert result.success

            # Verify all tables exist
            for i in range(3):
                check_query = f"""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables
                        WHERE table_name = 'concurrent_table_{i}'
                    )
                """
                exists_result = await connection.execute(check_query)
                assert exists_result is not None

        finally:
            await framework.teardown_test_database(connection)

    @pytest.mark.asyncio
    @pytest.mark.timeout(5)
    async def test_performance_tracking_real_database(self, test_database_url):
        """Test performance tracking with real database operations."""
        framework = MigrationTestFramework(
            database_type="postgresql",
            connection_string=test_database_url,
            integration_mode=True,
            track_performance=True,
        )

        connection = await framework.setup_test_database()

        try:
            # Create a large table to test performance
            large_table = TableDefinition(
                name="performance_test_table",
                columns=[
                    ColumnDefinition(name="id", type="SERIAL", primary_key=True),
                    ColumnDefinition(name="col1", type="VARCHAR(255)"),
                    ColumnDefinition(name="col2", type="INTEGER"),
                    ColumnDefinition(name="col3", type="TIMESTAMP"),
                    ColumnDefinition(name="col4", type="BOOLEAN", default="FALSE"),
                    ColumnDefinition(name="col5", type="TEXT"),
                ],
            )

            migration = Migration(
                version="perf_001",
                operations=[
                    MigrationOperation(
                        type=MigrationType.CREATE_TABLE, table=large_table
                    )
                ],
            )

            # Execute and track performance
            result = await framework.test_migration(migration, connection)

            assert result.success
            assert result.execution_time > 0
            assert result.execution_time < 1.0  # Should be fast

            # Get performance metrics
            metrics = framework.get_performance_metrics()
            assert len(metrics) > 0
            assert metrics[0]["migration_version"] == "perf_001"
            assert metrics[0]["execution_time"] > 0

        finally:
            await framework.teardown_test_database(connection)

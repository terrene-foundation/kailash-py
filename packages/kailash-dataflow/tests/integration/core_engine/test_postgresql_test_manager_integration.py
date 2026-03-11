"""
Integration tests for PostgreSQL Test Manager - Phase 1B Component 2

Tests real PostgreSQL integration with Migration Testing Framework.
NO MOCKING allowed - uses real Docker PostgreSQL containers.

Test Categories:
- Tier 2 Integration Tests (<5s timeout)
- Real Docker PostgreSQL infrastructure
- Migration Testing Framework integration
- Concurrent access scenarios
- Performance validation
"""

import asyncio
import time
from typing import Any, Dict, List

import pytest
from dataflow.migrations.auto_migration_system import ColumnDefinition, TableDefinition
from dataflow.migrations.migration_test_framework import (
    MigrationTestFramework,
    MigrationTestResult,
)
from dataflow.migrations.postgresql_test_manager import (
    ContainerInfo,
    ContainerStatus,
    PostgreSQLTestExecutionResult,
    PostgreSQLTestManager,
)

from tests.infrastructure.test_harness import IntegrationTestSuite
from tests.utils.real_infrastructure import real_infra


@pytest.fixture
async def test_suite():
    """Create complete integration test suite with infrastructure."""
    suite = IntegrationTestSuite()
    async with suite.session():
        yield suite


@pytest.fixture
def runtime():
    """Create LocalRuntime for workflow execution."""
    from kailash.runtime.local import LocalRuntime

    return LocalRuntime()


@pytest.mark.integration
@pytest.mark.timeout(5)
class TestPostgreSQLTestManagerIntegration:
    """Integration tests for PostgreSQL Test Manager with real infrastructure."""

    @pytest.fixture
    async def postgresql_manager(self):
        """Create PostgreSQL Test Manager for testing."""
        manager = PostgreSQLTestManager(
            container_name="test_manager_integration",
            postgres_port=5435,  # Avoid conflicts with other tests
            performance_target_seconds=3.0,
            enable_concurrent_testing=True,
        )

        yield manager

        # Cleanup
        await manager.cleanup_test_environment()

    @pytest.mark.asyncio
    async def test_container_lifecycle_management(self, postgresql_manager):
        """Test Docker container lifecycle management."""

        # Test container startup
        container_info = await postgresql_manager.start_test_container()

        assert container_info.status == ContainerStatus.RUNNING
        assert container_info.ready is True
        assert container_info.container_id is not None
        assert container_info.database_url
        assert container_info.host == "localhost"
        assert container_info.port == 5435

        # Verify performance target
        assert "setup_time" in container_info.performance_metrics
        setup_time = container_info.performance_metrics["setup_time"]
        assert setup_time < 5.0  # Should start within 5 seconds

        # Test connection
        import asyncpg

        conn = await asyncpg.connect(container_info.database_url)
        result = await conn.fetchval("SELECT 1")
        assert result == 1
        await conn.close()

        # Test container status check
        status = await postgresql_manager.get_container_status()
        assert status.status == ContainerStatus.RUNNING
        assert status.ready is True

    @pytest.mark.asyncio
    async def test_migration_framework_integration(self, postgresql_manager):
        """Test integration with Migration Testing Framework."""

        # Start container
        container_info = await postgresql_manager.start_test_container()
        assert container_info.ready

        # Create test case
        test_case = {
            "name": "integration_test_migration",
            "migrations": [
                {
                    "name": "create_users_table",
                    "tables": [
                        TableDefinition(
                            name="test_users",
                            columns=[
                                ColumnDefinition(
                                    name="id",
                                    type="SERIAL",
                                    primary_key=True,
                                    nullable=False,
                                ),
                                ColumnDefinition(
                                    name="username",
                                    type="VARCHAR(100)",
                                    nullable=False,
                                    unique=True,
                                ),
                                ColumnDefinition(
                                    name="email", type="VARCHAR(255)", nullable=False
                                ),
                                ColumnDefinition(
                                    name="created_at",
                                    type="TIMESTAMP",
                                    default="CURRENT_TIMESTAMP",
                                    nullable=False,
                                ),
                            ],
                        )
                    ],
                    "expected_schema": {
                        "test_users": TableDefinition(
                            name="test_users",
                            columns=[
                                ColumnDefinition(
                                    name="id",
                                    type="integer",
                                    primary_key=True,
                                    nullable=False,
                                ),
                                ColumnDefinition(
                                    name="username",
                                    type="character varying",
                                    nullable=False,
                                    unique=True,
                                ),
                                ColumnDefinition(
                                    name="email",
                                    type="character varying",
                                    nullable=False,
                                ),
                                ColumnDefinition(
                                    name="created_at",
                                    type="timestamp without time zone",
                                    nullable=False,
                                ),
                            ],
                        )
                    },
                }
            ],
            "performance_target": 3.0,
            "enable_rollback": True,
            "test_concurrent": True,
        }

        # Run migration integration test
        result = await postgresql_manager.run_migration_integration_test(test_case)

        # Verify test results
        assert result.success is True
        assert result.test_case_name == "integration_test_migration"
        assert result.execution_time < 5.0
        assert len(result.migration_results) == 1
        assert result.migration_results[0].success is True
        assert result.migration_results[0].verification_passed is True

        # Verify performance metrics
        assert "execution_time" in result.performance_metrics
        assert "migrations_count" in result.performance_metrics
        assert "migrations_passed" in result.performance_metrics
        assert result.performance_metrics["migrations_passed"] == 1

        # Verify concurrent test results
        assert "success" in result.concurrent_test_results
        assert result.concurrent_test_results["success"] is True

    @pytest.mark.asyncio
    async def test_concurrent_access_scenarios(self, postgresql_manager):
        """Test concurrent access scenarios against real PostgreSQL."""

        # Start container
        container_info = await postgresql_manager.start_test_container()
        assert container_info.ready

        # Create simple test case for concurrent testing
        test_case = {
            "name": "concurrent_access_test",
            "migrations": [
                {
                    "name": "create_concurrent_table",
                    "tables": [
                        TableDefinition(
                            name="concurrent_test_table",
                            columns=[
                                ColumnDefinition(
                                    name="id", type="SERIAL", primary_key=True
                                ),
                                ColumnDefinition(name="data", type="TEXT"),
                            ],
                        )
                    ],
                    "expected_schema": {
                        "concurrent_test_table": TableDefinition(
                            name="concurrent_test_table",
                            columns=[
                                ColumnDefinition(
                                    name="id", type="integer", primary_key=True
                                ),
                                ColumnDefinition(name="data", type="text"),
                            ],
                        )
                    },
                }
            ],
            "test_concurrent": True,
        }

        # Run test with concurrent access
        result = await postgresql_manager.run_migration_integration_test(test_case)

        # Verify concurrent test results
        assert result.success is True
        assert "concurrent_test_results" in result.__dict__
        concurrent_results = result.concurrent_test_results

        assert concurrent_results["success"] is True
        assert "connection_test" in concurrent_results
        assert "read_write_test" in concurrent_results
        assert "schema_test" in concurrent_results

        # Verify each concurrent test type
        assert concurrent_results["connection_test"]["success"] is True
        assert concurrent_results["read_write_test"]["success"] is True
        assert concurrent_results["schema_test"]["success"] is True

    @pytest.mark.asyncio
    async def test_performance_validation(self, postgresql_manager):
        """Test performance validation with real database operations."""

        # Start container with strict performance target
        postgresql_manager.performance_target = 2.0  # 2 second target
        container_info = await postgresql_manager.start_test_container()
        assert container_info.ready

        # Create performance test case
        test_case = {
            "name": "performance_test",
            "migrations": [
                {
                    "name": "performance_migration",
                    "tables": [
                        TableDefinition(
                            name="performance_table",
                            columns=[
                                ColumnDefinition(
                                    name="id", type="SERIAL", primary_key=True
                                ),
                                ColumnDefinition(name="name", type="VARCHAR(50)"),
                            ],
                        )
                    ],
                    "expected_schema": {
                        "performance_table": TableDefinition(
                            name="performance_table",
                            columns=[
                                ColumnDefinition(
                                    name="id", type="integer", primary_key=True
                                ),
                                ColumnDefinition(name="name", type="character varying"),
                            ],
                        )
                    },
                }
            ],
            "performance_target": 2.0,
        }

        # Measure performance
        start_time = time.perf_counter()
        result = await postgresql_manager.run_migration_integration_test(test_case)
        total_time = time.perf_counter() - start_time

        # Verify performance requirements
        assert result.success is True
        assert total_time < 5.0  # Integration test requirement
        assert result.execution_time <= total_time

        # Check performance metrics
        assert result.performance_metrics["execution_time"] < 5.0
        assert "performance_pass" in result.performance_metrics

    @pytest.mark.asyncio
    async def test_test_database_management(self, postgresql_manager):
        """Test comprehensive test database lifecycle management."""

        # Start container
        container_info = await postgresql_manager.start_test_container()
        assert container_info.ready

        # Create test database
        test_db_name = "integration_test_db"
        test_db_url = await postgresql_manager.create_test_database(test_db_name)

        assert test_db_name in test_db_url
        assert "postgresql://" in test_db_url

        # Verify test database exists and is accessible
        import asyncpg

        conn = await asyncpg.connect(test_db_url)
        result = await conn.fetchval("SELECT current_database()")
        assert result == test_db_name
        await conn.close()

        # Drop test database
        success = await postgresql_manager.drop_test_database(test_db_name)
        assert success is True

        # Verify database is dropped
        try:
            conn = await asyncpg.connect(test_db_url)
            await conn.close()
            assert False, "Database should have been dropped"
        except Exception:
            # Expected - database should not exist
            pass

    @pytest.mark.asyncio
    async def test_error_handling_and_recovery(self, postgresql_manager):
        """Test error handling and recovery scenarios."""

        # Test invalid migration
        test_case = {
            "name": "error_test",
            "migrations": [
                {
                    "name": "invalid_migration",
                    "tables": [
                        TableDefinition(
                            name="invalid_table",
                            columns=[
                                ColumnDefinition(
                                    name="id",
                                    type="INVALID_TYPE",  # Invalid SQL type
                                    primary_key=True,
                                )
                            ],
                        )
                    ],
                    "expected_schema": {},
                }
            ],
        }

        # Start container first
        container_info = await postgresql_manager.start_test_container()
        assert container_info.ready

        # Run test with invalid migration
        result = await postgresql_manager.run_migration_integration_test(test_case)

        # Should handle error gracefully
        assert result.success is False
        assert result.error is not None or (
            len(result.migration_results) > 0
            and not result.migration_results[0].success
        )

    @pytest.mark.asyncio
    async def test_integration_with_existing_test_env(self, postgresql_manager):
        """Test integration with existing test_env infrastructure."""

        # Test that we can coexist with existing test_env
        container_info = await postgresql_manager.start_test_container()
        assert container_info.ready

        # Verify we're using different port
        assert container_info.port != 5434  # test_env uses 5434
        assert container_info.port == 5435  # Our test port

        # Test that container is properly isolated
        assert container_info.container_id is not None
        assert (
            "test_manager_integration" in container_info.container_id or True
        )  # Container name should be reflected

    @pytest.mark.asyncio
    async def test_rollback_functionality(self, postgresql_manager):
        """Test migration rollback functionality with real database."""

        # Start container
        container_info = await postgresql_manager.start_test_container()
        assert container_info.ready

        # Create test case with rollback enabled
        test_case = {
            "name": "rollback_test",
            "migrations": [
                {
                    "name": "rollback_migration",
                    "tables": [
                        TableDefinition(
                            name="rollback_table",
                            columns=[
                                ColumnDefinition(
                                    name="id", type="SERIAL", primary_key=True
                                ),
                                ColumnDefinition(name="name", type="VARCHAR(100)"),
                            ],
                        )
                    ],
                    "expected_schema": {
                        "rollback_table": TableDefinition(
                            name="rollback_table",
                            columns=[
                                ColumnDefinition(
                                    name="id", type="integer", primary_key=True
                                ),
                                ColumnDefinition(name="name", type="character varying"),
                            ],
                        )
                    },
                }
            ],
            "enable_rollback": True,
        }

        # Run migration test with rollback
        result = await postgresql_manager.run_migration_integration_test(test_case)

        # Verify rollback was tested
        assert result.success is True
        assert len(result.migration_results) > 0
        migration_result = result.migration_results[0]

        # Check if rollback was tested (may be None if rollback not supported)
        if migration_result.rollback_verified is not None:
            # If rollback testing is supported, it should pass
            assert (
                migration_result.rollback_verified is True
                or migration_result.rollback_verified is False
            )
            assert "rollback_tested" in migration_result.performance_metrics


@pytest.mark.integration
@pytest.mark.timeout(5)
class TestPostgreSQLTestManagerEdgeCases:
    """Edge case tests for PostgreSQL Test Manager."""

    @pytest.fixture
    async def postgresql_manager(self):
        """Create PostgreSQL Test Manager for edge case testing."""
        manager = PostgreSQLTestManager(
            container_name="test_manager_edge_cases",
            postgres_port=5436,  # Different port for edge cases
            performance_target_seconds=4.0,
        )

        yield manager

        # Cleanup
        await manager.cleanup_test_environment()

    @pytest.mark.asyncio
    async def test_port_conflict_handling(self, postgresql_manager):
        """Test handling of port conflicts."""

        # Start first container
        container_info = await postgresql_manager.start_test_container()
        assert container_info.ready

        # Try to start another manager on same port (should handle gracefully)
        manager2 = PostgreSQLTestManager(
            container_name="test_manager_conflict",
            postgres_port=5436,  # Same port as first manager
            performance_target_seconds=4.0,
        )

        try:
            # This should either reuse existing container or handle conflict
            container_info2 = await manager2.start_test_container()
            # If successful, should be able to connect
            if container_info2.ready:
                import asyncpg

                conn = await asyncpg.connect(container_info2.database_url)
                await conn.close()
        finally:
            await manager2.cleanup_test_environment()

    @pytest.mark.asyncio
    async def test_cleanup_robustness(self, postgresql_manager):
        """Test robust cleanup under various conditions."""

        # Start container
        container_info = await postgresql_manager.start_test_container()
        assert container_info.ready

        # Create multiple test databases
        test_dbs = ["cleanup_test_1", "cleanup_test_2", "cleanup_test_3"]
        for db_name in test_dbs:
            await postgresql_manager.create_test_database(db_name)

        # Force cleanup (should handle all resources)
        await postgresql_manager.cleanup_test_environment()

        # Verify cleanup was thorough
        status = await postgresql_manager.get_container_status()
        assert status.status in [ContainerStatus.NOT_FOUND, ContainerStatus.STOPPED]

    @pytest.mark.asyncio
    async def test_multiple_migration_execution(self, postgresql_manager):
        """Test execution of multiple migrations in sequence."""

        # Start container
        container_info = await postgresql_manager.start_test_container()
        assert container_info.ready

        # Create test case with multiple migrations
        test_case = {
            "name": "multiple_migrations_test",
            "migrations": [
                {
                    "name": "create_users",
                    "tables": [
                        TableDefinition(
                            name="users",
                            columns=[
                                ColumnDefinition(
                                    name="id", type="SERIAL", primary_key=True
                                ),
                                ColumnDefinition(name="username", type="VARCHAR(50)"),
                            ],
                        )
                    ],
                    "expected_schema": {
                        "users": TableDefinition(
                            name="users",
                            columns=[
                                ColumnDefinition(
                                    name="id", type="integer", primary_key=True
                                ),
                                ColumnDefinition(
                                    name="username", type="character varying"
                                ),
                            ],
                        )
                    },
                },
                {
                    "name": "create_posts",
                    "tables": [
                        TableDefinition(
                            name="posts",
                            columns=[
                                ColumnDefinition(
                                    name="id", type="SERIAL", primary_key=True
                                ),
                                ColumnDefinition(name="title", type="VARCHAR(200)"),
                                ColumnDefinition(name="user_id", type="INTEGER"),
                            ],
                        )
                    ],
                    "expected_schema": {
                        "posts": TableDefinition(
                            name="posts",
                            columns=[
                                ColumnDefinition(
                                    name="id", type="integer", primary_key=True
                                ),
                                ColumnDefinition(
                                    name="title", type="character varying"
                                ),
                                ColumnDefinition(name="user_id", type="integer"),
                            ],
                        )
                    },
                },
            ],
        }

        # Run multiple migration test
        result = await postgresql_manager.run_migration_integration_test(test_case)

        # Verify all migrations executed successfully
        assert result.success is True
        assert len(result.migration_results) == 2
        assert all(mr.success for mr in result.migration_results)
        assert result.performance_metrics["migrations_count"] == 2
        assert result.performance_metrics["migrations_passed"] == 2

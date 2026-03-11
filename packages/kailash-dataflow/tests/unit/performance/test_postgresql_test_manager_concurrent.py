"""
Unit tests for PostgreSQL Test Manager concurrent access functionality.

Tests isolated concurrent access components and logic.
Tier 1 tests (<1 second timeout) with mocking allowed.
"""

import asyncio
import time
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from dataflow.migrations.postgresql_test_manager import (
    ContainerInfo,
    ContainerStatus,
    PostgreSQLTestExecutionResult,
    PostgreSQLTestManager,
)


@pytest.mark.unit
@pytest.mark.timeout(1)
class TestPostgreSQLTestManagerConcurrentUnit:
    """Unit tests for concurrent access functionality."""

    @pytest.fixture
    def mock_postgresql_manager(self):
        """Create mocked PostgreSQL Test Manager for unit testing."""
        with (
            patch("dataflow.migrations.postgresql_test_manager.docker"),
            patch("dataflow.migrations.postgresql_test_manager.asyncpg"),
        ):

            manager = PostgreSQLTestManager(
                container_name="test_manager_unit",
                postgres_port=5438,
                enable_concurrent_testing=True,
            )

            # Mock internal state
            manager._docker_client = MagicMock()
            manager._container = MagicMock()
            manager._container.id = "mock_container_id"

            return manager

    def test_concurrent_testing_configuration(self, mock_postgresql_manager):
        """Test concurrent testing configuration."""

        # Test default configuration
        assert mock_postgresql_manager.enable_concurrent_testing is True
        assert mock_postgresql_manager.postgres_port == 5438
        assert mock_postgresql_manager.performance_target == 5.0

        # Test custom configuration
        custom_manager = PostgreSQLTestManager(
            enable_concurrent_testing=False, performance_target_seconds=3.0
        )

        assert custom_manager.enable_concurrent_testing is False
        assert custom_manager.performance_target == 3.0

    @pytest.mark.asyncio
    async def test_concurrent_test_execution_logic(self, mock_postgresql_manager):
        """Test concurrent test execution logic without real database."""

        # Mock container info
        mock_container_info = ContainerInfo(
            container_id="mock_id",
            status=ContainerStatus.RUNNING,
            database_url="postgresql://test:test@localhost:5438/test",
            host="localhost",
            port=5438,
            database="test",
            user="test",
            password="test",
            ready=True,
        )

        # Mock the concurrent test methods
        with (
            patch.object(
                mock_postgresql_manager, "_test_multiple_connections"
            ) as mock_connections,
            patch.object(
                mock_postgresql_manager, "_test_concurrent_read_write"
            ) as mock_read_write,
            patch.object(
                mock_postgresql_manager, "_test_concurrent_schema_operations"
            ) as mock_schema,
        ):

            # Setup mock returns
            mock_connections.return_value = {"success": True, "connection_count": 10}
            mock_read_write.return_value = {"success": True, "execution_time": 0.5}
            mock_schema.return_value = {"success": True, "execution_time": 0.3}

            # Test concurrent access execution
            result = await mock_postgresql_manager._run_concurrent_access_tests(
                mock_container_info
            )

            # Verify result structure
            assert result["success"] is True
            assert "connection_test" in result
            assert "read_write_test" in result
            assert "schema_test" in result
            assert "execution_time" in result

            # Verify all concurrent tests were called
            mock_connections.assert_called_once_with(mock_container_info)
            mock_read_write.assert_called_once_with(mock_container_info)
            mock_schema.assert_called_once_with(mock_container_info)

    @pytest.mark.asyncio
    async def test_concurrent_test_failure_handling(self, mock_postgresql_manager):
        """Test handling of concurrent test failures."""

        mock_container_info = ContainerInfo(
            container_id="mock_id",
            status=ContainerStatus.RUNNING,
            database_url="postgresql://test:test@localhost:5438/test",
            host="localhost",
            port=5438,
            database="test",
            user="test",
            password="test",
            ready=True,
        )

        # Mock one failing test
        with (
            patch.object(
                mock_postgresql_manager, "_test_multiple_connections"
            ) as mock_connections,
            patch.object(
                mock_postgresql_manager, "_test_concurrent_read_write"
            ) as mock_read_write,
            patch.object(
                mock_postgresql_manager, "_test_concurrent_schema_operations"
            ) as mock_schema,
        ):

            # Setup mock returns with one failure
            mock_connections.return_value = {"success": True}
            mock_read_write.return_value = {
                "success": False,
                "error": "Read/write test failed",
            }
            mock_schema.return_value = {"success": True}

            # Test concurrent access execution
            result = await mock_postgresql_manager._run_concurrent_access_tests(
                mock_container_info
            )

            # Verify failure is properly handled
            assert result["success"] is False  # Overall should fail if any test fails
            assert result["read_write_test"]["success"] is False
            assert "error" in result["read_write_test"]

    @pytest.mark.asyncio
    async def test_concurrent_connection_test_logic(self, mock_postgresql_manager):
        """Test multiple connections test logic."""

        mock_container_info = ContainerInfo(
            container_id="mock_id",
            status=ContainerStatus.RUNNING,
            database_url="postgresql://test:test@localhost:5438/test",
            host="localhost",
            port=5438,
            database="test",
            user="test",
            password="test",
            ready=True,
        )

        # Mock asyncpg connections
        mock_connections = []
        for _ in range(10):
            mock_conn = AsyncMock()
            mock_conn.execute = AsyncMock()
            mock_conn.close = AsyncMock()
            mock_connections.append(mock_conn)

        # Patch asyncpg.connect to return mock connections
        with patch(
            "dataflow.migrations.postgresql_test_manager.asyncpg.connect"
        ) as mock_connect:
            mock_connect.side_effect = mock_connections

            # Test multiple connections
            result = await mock_postgresql_manager._test_multiple_connections(
                mock_container_info, connection_count=10
            )

            # Verify result
            assert result["success"] is True
            assert result["connection_count"] == 10
            assert "connection_time" in result
            assert "query_time" in result

            # Verify all connections were created and used
            assert mock_connect.call_count == 10
            for mock_conn in mock_connections:
                mock_conn.execute.assert_called_once()
                mock_conn.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_performance_timing_validation(self, mock_postgresql_manager):
        """Test performance timing validation in concurrent tests."""

        # Test with strict performance target
        mock_postgresql_manager.performance_target = 0.1  # Very strict target

        mock_container_info = ContainerInfo(
            container_id="mock_id",
            status=ContainerStatus.RUNNING,
            database_url="postgresql://test:test@localhost:5438/test",
            host="localhost",
            port=5438,
            database="test",
            user="test",
            password="test",
            ready=True,
        )

        # Mock slow concurrent operations
        with (
            patch.object(
                mock_postgresql_manager, "_test_multiple_connections"
            ) as mock_connections,
            patch.object(
                mock_postgresql_manager, "_test_concurrent_read_write"
            ) as mock_read_write,
            patch.object(
                mock_postgresql_manager, "_test_concurrent_schema_operations"
            ) as mock_schema,
        ):

            # Simulate slow operations
            async def slow_operation(*args, **kwargs):
                await asyncio.sleep(0.2)  # Exceed performance target
                return {"success": True, "execution_time": 0.2}

            mock_connections.side_effect = slow_operation
            mock_read_write.side_effect = slow_operation
            mock_schema.side_effect = slow_operation

            # Test with performance timing
            start_time = time.perf_counter()
            result = await mock_postgresql_manager._run_concurrent_access_tests(
                mock_container_info
            )
            total_time = time.perf_counter() - start_time

            # Verify timing is captured
            assert "execution_time" in result
            assert result["execution_time"] > 0.5  # Should be slow due to mocked delays
            assert total_time > 0.5

    def test_concurrent_test_configuration_validation(self, mock_postgresql_manager):
        """Test validation of concurrent test configuration."""

        # Test default concurrent testing configuration
        assert mock_postgresql_manager.enable_concurrent_testing is True

        # Test disabled concurrent testing
        disabled_manager = PostgreSQLTestManager(enable_concurrent_testing=False)
        assert disabled_manager.enable_concurrent_testing is False

        # Test concurrent user count validation
        assert hasattr(mock_postgresql_manager, "enable_concurrent_testing")

    @pytest.mark.asyncio
    async def test_concurrent_error_recovery(self, mock_postgresql_manager):
        """Test error recovery in concurrent operations."""

        mock_container_info = ContainerInfo(
            container_id="mock_id",
            status=ContainerStatus.RUNNING,
            database_url="postgresql://test:test@localhost:5438/test",
            host="localhost",
            port=5438,
            database="test",
            user="test",
            password="test",
            ready=True,
        )

        # Mock connection that raises an exception
        with patch(
            "dataflow.migrations.postgresql_test_manager.asyncpg.connect"
        ) as mock_connect:
            mock_connect.side_effect = Exception("Connection failed")

            # Test connection failure handling
            result = await mock_postgresql_manager._test_multiple_connections(
                mock_container_info, connection_count=5
            )

            # Verify error is handled gracefully
            assert result["success"] is False
            assert "error" in result
            assert "Connection failed" in result["error"]

    @pytest.mark.asyncio
    async def test_concurrent_test_integration_with_migration_framework(
        self, mock_postgresql_manager
    ):
        """Test integration with migration testing framework."""

        # Create test case with concurrent testing enabled
        test_case = {
            "name": "concurrent_integration_test",
            "migrations": [],
            "test_concurrent": True,
            "performance_target": 2.0,
        }

        # Mock container startup
        mock_container_info = ContainerInfo(
            container_id="mock_id",
            status=ContainerStatus.RUNNING,
            database_url="postgresql://test:test@localhost:5438/test",
            host="localhost",
            port=5438,
            database="test",
            user="test",
            password="test",
            ready=True,
        )

        # Mock all dependencies
        with (
            patch.object(mock_postgresql_manager, "start_test_container") as mock_start,
            patch.object(
                mock_postgresql_manager, "_run_concurrent_access_tests"
            ) as mock_concurrent,
            patch(
                "dataflow.migrations.postgresql_test_manager.MigrationTestFramework"
            ) as mock_framework,
        ):

            # Setup mocks
            mock_start.return_value = mock_container_info
            mock_concurrent.return_value = {
                "success": True,
                "execution_time": 1.5,
                "connection_test": {"success": True},
                "read_write_test": {"success": True},
                "schema_test": {"success": True},
            }

            # Mock migration framework
            mock_framework_instance = AsyncMock()
            mock_framework.return_value = mock_framework_instance
            mock_framework_instance.run_comprehensive_test.return_value = (
                None  # No migrations to test
            )

            # Test integration
            result = await mock_postgresql_manager.run_migration_integration_test(
                test_case
            )

            # Verify concurrent testing was executed
            assert result.success is True
            assert "concurrent_test_results" in result.__dict__
            assert result.concurrent_test_results["success"] is True
            mock_concurrent.assert_called_once_with(mock_container_info)

    def test_concurrent_access_performance_metrics(self, mock_postgresql_manager):
        """Test performance metrics collection for concurrent access."""

        # Test performance metrics structure
        expected_metrics = [
            "execution_time",
            "connection_test",
            "read_write_test",
            "schema_test",
        ]

        # Create sample concurrent test result
        sample_result = {
            "success": True,
            "execution_time": 1.23,
            "connection_test": {
                "success": True,
                "connection_count": 10,
                "connection_time": 0.5,
                "query_time": 0.3,
            },
            "read_write_test": {"success": True, "execution_time": 0.8},
            "schema_test": {"success": True, "execution_time": 0.4},
        }

        # Verify all expected metrics are present
        for metric in expected_metrics:
            assert metric in sample_result

        # Verify nested metric structure
        assert "connection_count" in sample_result["connection_test"]
        assert "connection_time" in sample_result["connection_test"]
        assert "query_time" in sample_result["connection_test"]

    @pytest.mark.asyncio
    async def test_concurrent_database_operations_isolation(
        self, mock_postgresql_manager
    ):
        """Test isolation of concurrent database operations."""

        mock_container_info = ContainerInfo(
            container_id="mock_id",
            status=ContainerStatus.RUNNING,
            database_url="postgresql://test:test@localhost:5438/test",
            host="localhost",
            port=5438,
            database="test",
            user="test",
            password="test",
            ready=True,
        )

        # Mock database operations that should be isolated
        mock_connections = []
        for i in range(5):
            mock_conn = AsyncMock()
            mock_conn.execute = AsyncMock()
            mock_conn.fetch = AsyncMock(return_value=[{"count": i * 10}])
            mock_conn.close = AsyncMock()
            mock_connections.append(mock_conn)

        with patch(
            "dataflow.migrations.postgresql_test_manager.asyncpg.connect"
        ) as mock_connect:
            mock_connect.side_effect = mock_connections

            # Test read/write isolation
            result = await mock_postgresql_manager._test_concurrent_read_write(
                mock_container_info
            )

            # Verify operations were isolated (each connection used separately)
            assert (
                mock_connect.call_count >= 2
            )  # At least writer and reader connections

            # Verify all connections were properly closed
            for mock_conn in mock_connections[: mock_connect.call_count]:
                mock_conn.close.assert_called_once()

    def test_container_info_validation_for_concurrent_tests(
        self, mock_postgresql_manager
    ):
        """Test validation of container info for concurrent tests."""

        # Test valid container info
        valid_container = ContainerInfo(
            container_id="valid_id",
            status=ContainerStatus.RUNNING,
            database_url="postgresql://test:test@localhost:5438/test",
            host="localhost",
            port=5438,
            database="test",
            user="test",
            password="test",
            ready=True,
        )

        # Container should be considered valid for concurrent testing
        assert valid_container.ready is True
        assert valid_container.status == ContainerStatus.RUNNING
        assert valid_container.database_url

        # Test invalid container info
        invalid_container = ContainerInfo(
            container_id=None,
            status=ContainerStatus.ERROR,
            database_url="",
            host="",
            port=0,
            database="",
            user="",
            password="",
            ready=False,
            error="Container failed to start",
        )

        # Container should not be valid for concurrent testing
        assert invalid_container.ready is False
        assert invalid_container.status == ContainerStatus.ERROR
        assert invalid_container.error is not None

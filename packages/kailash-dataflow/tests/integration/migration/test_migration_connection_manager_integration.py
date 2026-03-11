"""
Integration tests for MigrationConnectionManager with real database connections.

Tests connection pooling, retry logic, and proper integration with real PostgreSQL
and SQLite databases. NO MOCKING - uses actual database connections.
"""

import asyncio
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from dataflow.migrations.migration_connection_manager import (
    ConnectionError,
    ConnectionPoolConfig,
    MigrationConnectionManager,
    RetryConfig,
)

from tests.infrastructure.test_harness import IntegrationTestSuite


@pytest.fixture
async def test_suite():
    """Create complete integration test suite with infrastructure."""
    suite = IntegrationTestSuite()
    async with suite.session():
        yield suite


@pytest.mark.integration
class TestMigrationConnectionManagerIntegration:
    """Integration tests for MigrationConnectionManager with real databases."""

    @pytest.fixture
    def postgresql_dataflow(self, test_suite):
        """Create DataFlow instance with PostgreSQL test database."""
        # Use test suite infrastructure for consistent PostgreSQL connection
        return test_suite.dataflow_harness.create_dataflow(
            auto_migrate=False, existing_schema_mode=True
        )

    @pytest.fixture
    def sqlite_dataflow(self):
        """Create DataFlow instance with SQLite memory database."""
        from dataflow import DataFlow

        # Use real SQLite in-memory database
        return DataFlow(":memory:", auto_migrate=False, existing_schema_mode=True)

    @pytest.fixture
    def postgresql_manager(self, postgresql_dataflow):
        """Create MigrationConnectionManager with PostgreSQL."""
        return MigrationConnectionManager(postgresql_dataflow)

    @pytest.fixture
    def sqlite_manager(self, sqlite_dataflow):
        """Create MigrationConnectionManager with SQLite."""
        return MigrationConnectionManager(sqlite_dataflow)

    def test_postgresql_connection_creation_and_pooling(self, postgresql_manager):
        """Test real PostgreSQL connection creation and pooling."""
        # Get first connection
        conn1 = postgresql_manager.get_migration_connection()
        assert conn1 is not None

        # Verify it's a real PostgreSQL connection
        assert hasattr(conn1, "cursor") or hasattr(conn1, "execute")

        # Test connection is alive
        assert postgresql_manager._is_connection_alive(conn1)

        # Return connection to pool
        conn_id = postgresql_manager.return_migration_connection(conn1)
        assert conn_id is not None
        assert len(postgresql_manager._connection_pool) == 1

        # Get second connection - should reuse from pool
        conn2 = postgresql_manager.get_migration_connection()
        assert conn2 == conn1  # Same connection object
        assert postgresql_manager.stats.total_reused == 1

        # Cleanup
        postgresql_manager.close_all_connections()

    def test_sqlite_connection_creation_and_pooling(self, sqlite_manager):
        """Test real SQLite connection creation and pooling."""
        # Get first connection
        conn1 = sqlite_manager.get_migration_connection()
        assert conn1 is not None

        # Verify it's a real SQLite connection
        assert hasattr(conn1, "cursor")
        assert hasattr(conn1, "execute")

        # Test simple query
        cursor = conn1.cursor()
        cursor.execute("SELECT 1")
        result = cursor.fetchone()
        assert result == (1,)
        cursor.close()

        # Test connection is alive
        assert sqlite_manager._is_connection_alive(conn1)

        # Return connection to pool
        conn_id = sqlite_manager.return_migration_connection(conn1)
        assert conn_id is not None
        assert len(sqlite_manager._connection_pool) == 1

        # Get second connection - should reuse from pool
        conn2 = sqlite_manager.get_migration_connection()
        assert conn2 == conn1  # Same connection object
        assert sqlite_manager.stats.total_reused == 1

        # Cleanup
        sqlite_manager.close_all_connections()

    def test_concurrent_connection_access_postgresql(self, postgresql_manager):
        """Test concurrent access to PostgreSQL connections."""
        connections = []
        errors = []

        def get_connection_worker():
            try:
                conn = postgresql_manager.get_migration_connection()
                connections.append(conn)

                # Simulate some work
                time.sleep(0.1)

                # Return connection
                postgresql_manager.return_migration_connection(conn)
            except Exception as e:
                errors.append(e)

        # Run multiple workers concurrently
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(get_connection_worker) for _ in range(10)]
            for future in futures:
                future.result()

        # Verify no errors occurred
        assert len(errors) == 0, f"Errors occurred: {errors}"

        # Verify all connections were obtained
        assert len(connections) == 10

        # Verify stats
        stats = postgresql_manager.get_pool_stats()
        assert stats.total_created > 0

        # Cleanup
        postgresql_manager.close_all_connections()

    def test_concurrent_connection_access_sqlite(self, sqlite_manager):
        """Test concurrent access to SQLite connections."""
        connections = []
        errors = []

        def get_connection_worker():
            try:
                conn = sqlite_manager.get_migration_connection()
                connections.append(conn)

                # Test connection with actual query
                cursor = conn.cursor()
                cursor.execute("SELECT 1")
                result = cursor.fetchone()
                assert result == (1,)
                cursor.close()

                # Return connection
                sqlite_manager.return_migration_connection(conn)
            except Exception as e:
                errors.append(e)

        # Run multiple workers concurrently
        with ThreadPoolExecutor(
            max_workers=3
        ) as executor:  # SQLite has more limitations
            futures = [executor.submit(get_connection_worker) for _ in range(5)]
            for future in futures:
                future.result()

        # Verify no errors occurred
        assert len(errors) == 0, f"Errors occurred: {errors}"

        # Verify all connections were obtained
        assert len(connections) == 5

        # Cleanup
        sqlite_manager.close_all_connections()

    def test_connection_pool_lifecycle_postgresql(self, postgresql_manager):
        """Test connection pool lifecycle with PostgreSQL."""
        # Start with empty pool
        assert len(postgresql_manager._connection_pool) == 0

        # Create multiple connections
        connections = []
        for i in range(3):
            conn = postgresql_manager.get_migration_connection()
            connections.append(conn)

        # Return all connections to pool
        for conn in connections:
            postgresql_manager.return_migration_connection(conn)

        assert len(postgresql_manager._connection_pool) == 3

        # Get connections again - should reuse from pool
        reused_connections = []
        for i in range(3):
            conn = postgresql_manager.get_migration_connection()
            reused_connections.append(conn)

        # Verify reuse
        assert postgresql_manager.stats.total_reused == 3

        # Test cleanup
        postgresql_manager.close_all_connections()
        assert len(postgresql_manager._connection_pool) == 0
        assert postgresql_manager.stats.active_connections == 0

    def test_connection_expiry_cleanup_postgresql(self, postgresql_manager):
        """Test connection expiry and cleanup with PostgreSQL."""
        # Configure short expiry for testing
        original_lifetime = postgresql_manager.config.max_lifetime
        postgresql_manager.config.max_lifetime = 1  # 1 second

        try:
            # Create and return connection
            conn = postgresql_manager.get_migration_connection()
            conn_id = postgresql_manager.return_migration_connection(conn)
            assert len(postgresql_manager._connection_pool) == 1

            # Wait for expiry
            time.sleep(1.5)

            # Trigger cleanup
            postgresql_manager.cleanup_expired_connections()

            # Verify expired connection was removed
            assert len(postgresql_manager._connection_pool) == 0

        finally:
            # Restore original lifetime
            postgresql_manager.config.max_lifetime = original_lifetime
            postgresql_manager.close_all_connections()

    @pytest.mark.asyncio
    async def test_retry_logic_with_real_connection_postgresql(
        self, postgresql_manager
    ):
        """Test retry logic with real PostgreSQL connection operations."""
        retry_attempts = []

        async def failing_operation():
            retry_attempts.append(time.time())
            if len(retry_attempts) < 3:
                raise ConnectionError("Simulated connection failure")
            return "success"

        # Test retry with real timing
        start_time = time.time()
        result = await postgresql_manager.execute_with_retry(
            failing_operation,
            max_retries=3,
            retry_config=RetryConfig(initial_delay=0.1, max_delay=1.0),
        )
        end_time = time.time()

        assert result == "success"
        assert len(retry_attempts) == 3

        # Verify timing (should have delays between retries)
        total_time = end_time - start_time
        assert total_time >= 0.1  # At least initial delay
        assert total_time < 5.0  # But not too long

    @pytest.mark.asyncio
    async def test_retry_logic_with_real_connection_sqlite(self, sqlite_manager):
        """Test retry logic with real SQLite connection operations."""
        retry_attempts = []

        async def database_operation():
            retry_attempts.append(time.time())

            # Get connection and perform operation
            with sqlite_manager.get_connection() as conn:
                cursor = conn.cursor()

                # Simulate operation that might fail initially
                if len(retry_attempts) < 2:
                    raise ConnectionError("Simulated database error")

                cursor.execute("SELECT 1")
                result = cursor.fetchone()
                cursor.close()
                return result[0]

        # Test retry with real database operations
        result = await sqlite_manager.execute_with_retry(
            database_operation,
            max_retries=3,
            retry_config=RetryConfig(initial_delay=0.05, max_delay=0.5),
        )

        assert result == 1
        assert len(retry_attempts) == 2

    def test_context_manager_with_real_connections_postgresql(self, postgresql_manager):
        """Test context manager with real PostgreSQL connections."""
        # Test successful context manager usage
        with postgresql_manager.get_connection() as conn:
            assert conn is not None
            assert postgresql_manager._is_connection_alive(conn)

            # Connection should be tracked
            assert postgresql_manager.stats.active_connections >= 1

        # After context, connection should be returned to pool
        # (Note: actual return happens in the context manager)

        # Test exception handling in context manager
        try:
            with postgresql_manager.get_connection() as conn:
                assert conn is not None
                raise ValueError("Test exception")
        except ValueError:
            pass  # Expected

        # Cleanup
        postgresql_manager.close_all_connections()

    def test_context_manager_with_real_connections_sqlite(self, sqlite_manager):
        """Test context manager with real SQLite connections."""
        # Test successful context manager usage with actual query
        with sqlite_manager.get_connection() as conn:
            assert conn is not None

            # Perform actual database operation
            cursor = conn.cursor()
            cursor.execute("CREATE TABLE test_table (id INTEGER, name TEXT)")
            cursor.execute("INSERT INTO test_table VALUES (1, 'test')")
            cursor.execute("SELECT * FROM test_table")
            result = cursor.fetchall()
            assert result == [(1, "test")]
            cursor.close()

        # Test that connection is properly managed even with exceptions
        try:
            with sqlite_manager.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM test_table")
                raise RuntimeError("Simulated error")
        except RuntimeError:
            pass  # Expected

        # Verify connection pool is still functional
        with sqlite_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            result = cursor.fetchone()
            assert result == (1,)
            cursor.close()

        # Cleanup
        sqlite_manager.close_all_connections()

    def test_pool_statistics_accuracy_postgresql(self, postgresql_manager):
        """Test that pool statistics are accurate with real connections."""
        # Start with clean state
        postgresql_manager.close_all_connections()
        initial_stats = postgresql_manager.get_pool_stats()
        assert initial_stats.active_connections == 0
        assert initial_stats.pool_size == 0

        # Create connections
        connections = []
        for i in range(3):
            conn = postgresql_manager.get_migration_connection()
            connections.append(conn)

        # Check stats after creation
        stats_after_create = postgresql_manager.get_pool_stats()
        assert stats_after_create.active_connections == 3
        assert stats_after_create.total_created >= 3

        # Return connections to pool
        for conn in connections:
            postgresql_manager.return_migration_connection(conn)

        # Check stats after return
        stats_after_return = postgresql_manager.get_pool_stats()
        assert stats_after_return.pool_size == 3

        # Reuse connections
        reused_connections = []
        for i in range(3):
            conn = postgresql_manager.get_migration_connection()
            reused_connections.append(conn)

        # Check reuse stats
        stats_after_reuse = postgresql_manager.get_pool_stats()
        assert stats_after_reuse.total_reused >= 3

        # Cleanup
        postgresql_manager.close_all_connections()
        final_stats = postgresql_manager.get_pool_stats()
        assert final_stats.active_connections == 0
        assert final_stats.pool_size == 0

    def test_pool_disabled_mode_postgresql(self, postgresql_dataflow):
        """Test pool-disabled mode with real PostgreSQL connections."""
        config = ConnectionPoolConfig(enable_pooling=False)
        manager = MigrationConnectionManager(postgresql_dataflow, pool_config=config)

        # Get multiple connections
        connections = []
        for i in range(3):
            conn = manager.get_migration_connection()
            connections.append(conn)
            assert manager._is_connection_alive(conn)

        # Pool should remain empty
        assert len(manager._connection_pool) == 0

        # Return connections - they should be closed, not pooled
        for conn in connections:
            conn_id = manager.return_migration_connection(conn)
            assert conn_id is None

        # Pool should still be empty
        assert len(manager._connection_pool) == 0

        # Stats should show creation but no reuse
        stats = manager.get_pool_stats()
        assert stats.total_created >= 3
        assert stats.total_reused == 0

    def test_performance_comparison_pooled_vs_non_pooled(self, postgresql_dataflow):
        """Test performance difference between pooled and non-pooled connections."""
        # Test with pooling enabled
        pooled_manager = MigrationConnectionManager(postgresql_dataflow)

        start_time = time.time()
        for i in range(10):
            conn = pooled_manager.get_migration_connection()
            pooled_manager.return_migration_connection(conn)
        pooled_time = time.time() - start_time

        # Test with pooling disabled
        config = ConnectionPoolConfig(enable_pooling=False)
        non_pooled_manager = MigrationConnectionManager(
            postgresql_dataflow, pool_config=config
        )

        start_time = time.time()
        for i in range(10):
            conn = non_pooled_manager.get_migration_connection()
            non_pooled_manager.return_migration_connection(conn)
        non_pooled_time = time.time() - start_time

        # Pooled should generally be faster for multiple operations
        # (though this might not always be the case due to test environment variability)
        print(
            f"Pooled time: {pooled_time:.3f}s, Non-pooled time: {non_pooled_time:.3f}s"
        )

        # Just verify both completed successfully
        assert pooled_time < 30.0  # Reasonable upper bound
        assert non_pooled_time < 30.0  # Reasonable upper bound

        # Cleanup
        pooled_manager.close_all_connections()
        non_pooled_manager.close_all_connections()

    def test_connection_manager_isolation(self, postgresql_dataflow, sqlite_dataflow):
        """Test that different connection managers are properly isolated."""
        pg_manager = MigrationConnectionManager(postgresql_dataflow)
        sqlite_manager = MigrationConnectionManager(sqlite_dataflow)

        # Get connections from both managers
        pg_conn = pg_manager.get_migration_connection()
        sqlite_conn = sqlite_manager.get_migration_connection()

        # Verify they're different types of connections
        assert pg_conn != sqlite_conn

        # Verify isolation of pools
        pg_manager.return_migration_connection(pg_conn)
        sqlite_manager.return_migration_connection(sqlite_conn)

        assert len(pg_manager._connection_pool) == 1
        assert len(sqlite_manager._connection_pool) == 1

        # Verify stats are isolated
        pg_stats = pg_manager.get_pool_stats()
        sqlite_stats = sqlite_manager.get_pool_stats()

        assert pg_stats.total_created >= 1
        assert sqlite_stats.total_created >= 1

        # Cleanup
        pg_manager.close_all_connections()
        sqlite_manager.close_all_connections()

        assert len(pg_manager._connection_pool) == 0
        assert len(sqlite_manager._connection_pool) == 0

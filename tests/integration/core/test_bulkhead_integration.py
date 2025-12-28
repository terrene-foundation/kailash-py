"""Integration tests for bulkhead pattern with real Docker services.

Tier 2 tests - Integration testing with real PostgreSQL and Redis services.
All tests use REAL Docker services via docker_config.py - NO MOCKING.
"""

import asyncio
import os
import tempfile

import pytest
from kailash.core.resilience.bulkhead import (
    BulkheadManager,
    BulkheadPartition,
    BulkheadRejectionError,
    PartitionConfig,
    PartitionType,
    execute_with_bulkhead,
    get_bulkhead_manager,
)
from kailash.nodes.data.sql import SQLDatabaseNode

from tests.utils.docker_config import get_postgres_connection_string


@pytest.mark.integration
class TestBulkheadPostgreSQLIntegration:
    """Test bulkhead pattern integration with real PostgreSQL database."""

    @pytest.fixture
    def postgres_connection_string(self):
        """Get PostgreSQL connection string from Docker config."""
        return get_postgres_connection_string("kailash_test")

    @pytest.fixture
    def sql_node(self, postgres_connection_string):
        """Create SQL node with real PostgreSQL connection."""
        return SQLDatabaseNode(connection_string=postgres_connection_string)

    @pytest.fixture
    def bulkhead_manager(self):
        """Create fresh bulkhead manager for testing."""
        return BulkheadManager()

    @pytest.mark.asyncio
    async def test_sql_operations_through_database_partition(
        self, sql_node, bulkhead_manager
    ):
        """Test SQL operations through database partition with real database."""
        # Use the default database partition
        database_partition = bulkhead_manager.get_partition("database")

        # Create a test table and insert data
        create_table_sql = """
        CREATE TEMPORARY TABLE bulkhead_test (
            id SERIAL PRIMARY KEY,
            name VARCHAR(100),
            value INTEGER
        )
        """

        insert_sql = """
        INSERT INTO bulkhead_test (name, value)
        VALUES ('test_item', 42)
        """

        select_sql = "SELECT * FROM bulkhead_test"

        def execute_sql(query):
            return sql_node.execute(query=query)

        # Execute operations through bulkhead
        create_result = await database_partition.execute(execute_sql, create_table_sql)
        assert "data" in create_result  # CREATE TABLE returns data field

        insert_result = await database_partition.execute(execute_sql, insert_sql)
        assert "row_count" in insert_result
        assert insert_result["row_count"] == 1

        select_result = await database_partition.execute(execute_sql, select_sql)
        assert "data" in select_result
        assert len(select_result["data"]) == 1
        assert select_result["data"][0]["name"] == "test_item"
        assert select_result["data"][0]["value"] == 42

        # Check partition metrics
        status = database_partition.get_status()
        assert status["metrics"]["total_operations"] >= 3
        assert status["metrics"]["successful_operations"] >= 3

    @pytest.mark.asyncio
    async def test_concurrent_sql_operations_real_database(
        self, sql_node, bulkhead_manager
    ):
        """Test concurrent SQL operations with real database."""
        database_partition = bulkhead_manager.get_partition("database")

        # Setup test table (not temporary so it's visible to all connections)
        table_name = (
            f"bulkhead_concurrent_test_{id(bulkhead_manager)}"  # Unique table name
        )
        setup_sql = f"""
        CREATE TABLE IF NOT EXISTS {table_name} (
            id SERIAL PRIMARY KEY,
            thread_id VARCHAR(50),
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        DELETE FROM {table_name}  -- Clean any existing data
        """

        def execute_sql(query):
            return sql_node.execute(query=query)

        # Create table first
        await database_partition.execute(execute_sql, setup_sql)

        # Define concurrent operations
        operations = [
            f"INSERT INTO {table_name} (thread_id) VALUES ('thread_{i}')"
            for i in range(5)
        ]

        # Execute all operations concurrently through bulkhead
        tasks = [
            database_partition.execute(execute_sql, operation)
            for operation in operations
        ]

        results = await asyncio.gather(*tasks)

        # Verify all operations succeeded
        assert len(results) == 5
        assert all("row_count" in result for result in results)

        # Verify data was inserted
        count_result = await database_partition.execute(
            execute_sql, f"SELECT COUNT(*) as count FROM {table_name}"
        )
        assert count_result["data"][0]["count"] == 5

        # Cleanup
        await database_partition.execute(execute_sql, f"DROP TABLE {table_name}")

        # Check partition handled all operations
        status = database_partition.get_status()
        assert status["metrics"]["total_operations"] >= 6  # Setup + 5 inserts + count

    @pytest.mark.asyncio
    async def test_sql_error_handling_real_database(self, sql_node, bulkhead_manager):
        """Test SQL error handling through bulkhead with real database."""
        database_partition = bulkhead_manager.get_partition("database")

        def execute_invalid_sql():
            return sql_node.execute(
                query="SELECT * FROM nonexistent_table_bulkhead_test"
            )

        # Should propagate SQL errors through bulkhead
        from kailash.sdk_exceptions import NodeExecutionError

        with pytest.raises(NodeExecutionError):
            await database_partition.execute(execute_invalid_sql)

        # Check that failure was recorded in partition metrics
        status = database_partition.get_status()
        assert status["metrics"]["failed_operations"] >= 1

    @pytest.mark.asyncio
    async def test_database_transaction_isolation_real(
        self, postgres_connection_string, bulkhead_manager
    ):
        """Test database transaction behavior with bulkhead isolation."""
        database_partition = bulkhead_manager.get_partition("database")

        # Create multiple SQL nodes to simulate different connections
        sql_node1 = SQLDatabaseNode(connection_string=postgres_connection_string)
        sql_node2 = SQLDatabaseNode(connection_string=postgres_connection_string)

        # Setup shared table - drop and recreate to ensure clean state
        cleanup_sql = "DROP TABLE IF EXISTS bulkhead_transaction_test"
        setup_sql = """
        CREATE TABLE bulkhead_transaction_test (
            id SERIAL PRIMARY KEY,
            connection_id VARCHAR(20),
            operation_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """

        def execute_sql(sql_node, query):
            return sql_node.execute(query=query)

        # Clean up and create table using first connection
        await database_partition.execute(execute_sql, sql_node1, cleanup_sql)
        await database_partition.execute(execute_sql, sql_node1, setup_sql)

        # Concurrent operations from different connections
        tasks = [
            database_partition.execute(
                execute_sql,
                sql_node1,
                "INSERT INTO bulkhead_transaction_test (connection_id) VALUES ('conn1')",
            ),
            database_partition.execute(
                execute_sql,
                sql_node2,
                "INSERT INTO bulkhead_transaction_test (connection_id) VALUES ('conn2')",
            ),
            database_partition.execute(
                execute_sql,
                sql_node1,
                "SELECT COUNT(*) as count FROM bulkhead_transaction_test",
            ),
        ]

        results = await asyncio.gather(*tasks)

        # All operations should succeed
        assert all("data" in result or "row_count" in result for result in results)

        # Final verification
        final_count = await database_partition.execute(
            execute_sql,
            sql_node1,
            "SELECT COUNT(*) as count FROM bulkhead_transaction_test",
        )
        assert final_count["data"][0]["count"] >= 2

    @pytest.mark.asyncio
    async def test_different_partition_types_real_database(
        self, sql_node, bulkhead_manager
    ):
        """Test different partition types with real database operations."""
        # Setup test table - drop and recreate to ensure clean state
        cleanup_sql = "DROP TABLE IF EXISTS bulkhead_partition_types_test"
        setup_sql = """
        CREATE TABLE bulkhead_partition_types_test (
            id SERIAL PRIMARY KEY,
            partition_type VARCHAR(20),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """

        def execute_sql(query):
            return sql_node.execute(query=query)

        # Setup using database partition
        database_partition = bulkhead_manager.get_partition("database")
        await database_partition.execute(execute_sql, cleanup_sql)
        await database_partition.execute(execute_sql, setup_sql)

        # Test critical partition with important operation
        critical_partition = bulkhead_manager.get_partition("critical")
        critical_result = await critical_partition.execute(
            execute_sql,
            "INSERT INTO bulkhead_partition_types_test (partition_type) VALUES ('critical')",
        )
        assert "row_count" in critical_result

        # Test background partition with less important operation
        background_partition = bulkhead_manager.get_partition("background")
        background_result = await background_partition.execute(
            execute_sql,
            "INSERT INTO bulkhead_partition_types_test (partition_type) VALUES ('background')",
        )
        assert "row_count" in background_result

        # Verify operations completed
        count_result = await database_partition.execute(
            execute_sql, "SELECT COUNT(*) as count FROM bulkhead_partition_types_test"
        )
        assert count_result["data"][0]["count"] == 2

        # Check metrics for different partitions
        critical_status = critical_partition.get_status()
        background_status = background_partition.get_status()

        assert critical_status["metrics"]["total_operations"] >= 1
        assert background_status["metrics"]["total_operations"] >= 1


@pytest.mark.integration
class TestBulkheadResourceIsolationIntegration:
    """Test bulkhead resource isolation with real workloads."""

    @pytest.fixture
    def postgres_connection_string(self):
        """Get PostgreSQL connection string from Docker config."""
        return get_postgres_connection_string("kailash_test")

    @pytest.mark.asyncio
    async def test_partition_isolation_under_load(self, postgres_connection_string):
        """Test that partitions are truly isolated under real load."""
        # Create isolated partitions with strict limits
        config_small = PartitionConfig(
            name="small_isolated",
            partition_type=PartitionType.IO_BOUND,
            max_concurrent_operations=1,
            queue_size=1,
            timeout=10,
            circuit_breaker_enabled=False,
        )

        config_large = PartitionConfig(
            name="large_isolated",
            partition_type=PartitionType.IO_BOUND,
            max_concurrent_operations=5,
            timeout=15,
            circuit_breaker_enabled=False,
        )

        manager = BulkheadManager()
        small_partition = manager.create_partition(config_small)
        large_partition = manager.create_partition(config_large)

        # Create SQL nodes
        sql_node_small = SQLDatabaseNode(connection_string=postgres_connection_string)
        sql_node_large = SQLDatabaseNode(connection_string=postgres_connection_string)

        def slow_query():
            # A query that takes some time but not too long for CI
            return sql_node_small.execute(
                query="SELECT pg_sleep(0.5), 'slow_operation' as result"
            )

        def fast_query():
            return sql_node_large.execute(query="SELECT 'fast_operation' as result")

        # Start slow operation in small partition
        slow_task = asyncio.create_task(small_partition.execute(slow_query))
        await asyncio.sleep(0.1)  # Let it start

        # Large partition should still work immediately
        fast_result = await large_partition.execute(fast_query)
        assert "data" in fast_result
        assert fast_result["data"][0]["result"] == "fast_operation"

        # Wait for slow operation to complete
        slow_result = await slow_task
        assert "data" in slow_result
        assert slow_result["data"][0]["result"] == "slow_operation"

        # Verify metrics show isolation
        small_status = small_partition.get_status()
        large_status = large_partition.get_status()

        assert small_status["metrics"]["total_operations"] >= 1
        assert large_status["metrics"]["total_operations"] >= 1

    @pytest.mark.asyncio
    async def test_circuit_breaker_integration_real_database(
        self, postgres_connection_string
    ):
        """Test circuit breaker integration with real database failures."""
        config = PartitionConfig(
            name="circuit_test",
            partition_type=PartitionType.IO_BOUND,
            max_concurrent_operations=3,
            circuit_breaker_enabled=True,
            timeout=5,
        )

        manager = BulkheadManager()
        partition = manager.create_partition(config)
        sql_node = SQLDatabaseNode(connection_string=postgres_connection_string)

        def failing_query():
            return sql_node.execute(query="SELECT * FROM definitely_nonexistent_table")

        def success_query():
            return sql_node.execute(query="SELECT 'success' as result")

        # Execute successful operation first
        success_result = await partition.execute(success_query)
        assert "data" in success_result

        # Execute some failing operations (should eventually trigger circuit breaker)
        from kailash.sdk_exceptions import NodeExecutionError

        failure_count = 0
        for i in range(3):
            try:
                await partition.execute(failing_query)
            except NodeExecutionError:
                failure_count += 1

        # Circuit breaker should be tracking failures
        status = partition.get_status()
        assert status["metrics"]["failed_operations"] >= failure_count

        # Circuit breaker status should be available
        if status["circuit_breaker"]:
            assert "state" in status["circuit_breaker"]

    @pytest.mark.asyncio
    async def test_global_manager_integration_real_services(
        self, postgres_connection_string
    ):
        """Test global bulkhead manager with real database services."""
        sql_node = SQLDatabaseNode(connection_string=postgres_connection_string)

        def database_operation():
            return sql_node.execute(
                query="SELECT 'global_test' as result, NOW() as timestamp"
            )

        # Use global convenience function
        result = await execute_with_bulkhead("database", database_operation)

        assert "data" in result
        assert result["data"][0]["result"] == "global_test"
        assert "timestamp" in result["data"][0]

        # Check that global manager tracked the operation
        manager = get_bulkhead_manager()
        all_status = manager.get_all_status()

        assert "database" in all_status
        assert all_status["database"]["metrics"]["total_operations"] >= 1


@pytest.mark.integration
class TestBulkheadPerformanceIntegration:
    """Test bulkhead performance characteristics with real services."""

    @pytest.fixture
    def postgres_connection_string(self):
        """Get PostgreSQL connection string from Docker config."""
        return get_postgres_connection_string("kailash_test")

    @pytest.mark.asyncio
    async def test_performance_metrics_real_workload(self, postgres_connection_string):
        """Test performance metrics under real database workload."""
        sql_node = SQLDatabaseNode(connection_string=postgres_connection_string)
        manager = BulkheadManager()
        partition = manager.get_partition("database")

        # Setup test table - drop and recreate to ensure clean state
        cleanup_sql = "DROP TABLE IF EXISTS bulkhead_performance_test"
        setup_sql = """
        CREATE TABLE bulkhead_performance_test (
            id SERIAL PRIMARY KEY,
            data VARCHAR(100),
            value INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """

        def execute_sql(query):
            return sql_node.execute(query=query)

        # Create table
        await partition.execute(execute_sql, cleanup_sql)
        await partition.execute(execute_sql, setup_sql)

        # Execute various complexity operations
        operations = [
            "INSERT INTO bulkhead_performance_test (data, value) VALUES ('test1', 1)",
            "INSERT INTO bulkhead_performance_test (data, value) VALUES ('test2', 2)",
            "SELECT COUNT(*) as count FROM bulkhead_performance_test",
            "SELECT * FROM bulkhead_performance_test WHERE value > 0",
            "SELECT AVG(value) as avg_value FROM bulkhead_performance_test",
        ]

        # Execute operations and measure
        for operation in operations:
            result = await partition.execute(execute_sql, operation)
            assert "data" in result or "row_count" in result

        # Check comprehensive metrics
        status = partition.get_status()
        metrics = status["metrics"]

        assert metrics["total_operations"] >= len(operations) + 1  # +1 for setup
        assert metrics["successful_operations"] >= len(operations) + 1
        assert metrics["avg_execution_time"] > 0
        assert metrics["max_execution_time"] >= metrics["avg_execution_time"]
        assert abs(metrics["success_rate"] - 1.0) < 0.01  # Should be close to 100%

    @pytest.mark.asyncio
    async def test_concurrent_performance_real_load(self, postgres_connection_string):
        """Test performance monitoring under concurrent real database load."""
        sql_node = SQLDatabaseNode(connection_string=postgres_connection_string)
        manager = BulkheadManager()
        partition = manager.get_partition("database")

        # Setup performance test table - drop and recreate to ensure clean state
        cleanup_sql = "DROP TABLE IF EXISTS bulkhead_concurrent_performance"
        setup_sql = """
        CREATE TABLE bulkhead_concurrent_performance (
            id SERIAL PRIMARY KEY,
            worker_id INTEGER,
            operation_id INTEGER,
            execution_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """

        def execute_sql(query):
            return sql_node.execute(query=query)

        # Create table
        await partition.execute(execute_sql, cleanup_sql)
        await partition.execute(execute_sql, setup_sql)

        def concurrent_operation(worker_id, operation_id):
            query = f"""
            INSERT INTO bulkhead_concurrent_performance (worker_id, operation_id)
            VALUES ({worker_id}, {operation_id})
            """
            return sql_node.execute(query=query)

        # Execute many concurrent operations
        tasks = [
            partition.execute(concurrent_operation, worker_id, op_id)
            for worker_id in range(3)
            for op_id in range(5)
        ]

        results = await asyncio.gather(*tasks)

        # All should succeed
        assert len(results) == 15
        assert all("row_count" in result for result in results)

        # Verify data consistency
        count_result = await partition.execute(
            execute_sql, "SELECT COUNT(*) as count FROM bulkhead_concurrent_performance"
        )
        assert count_result["data"][0]["count"] == 15

        # Check performance metrics under load
        status = partition.get_status()
        metrics = status["metrics"]

        assert metrics["total_operations"] >= 16  # Setup + 15 operations + count
        assert metrics["successful_operations"] >= 16
        assert metrics["avg_execution_time"] > 0
        assert metrics["success_rate"] > 0.9  # Should be very high success rate

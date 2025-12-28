"""Integration tests for bulkhead pattern with real database operations."""

import asyncio
import os
import sqlite3
import tempfile
from pathlib import Path

import pytest
from kailash.core.resilience.bulkhead import (
    BulkheadManager,
    BulkheadRejectionError,
    PartitionConfig,
    PartitionType,
    get_bulkhead_manager,
)
from kailash.nodes.data.sql import SQLDatabaseNode
from kailash.sdk_exceptions import NodeExecutionError


class TestBulkheadSQLIntegration:
    """Test bulkhead pattern integration with SQL database operations."""

    @pytest.fixture
    def temp_database(self):
        """Create temporary SQLite database for testing."""
        temp_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        temp_file.close()

        # Initialize database
        conn = sqlite3.connect(temp_file.name)
        conn.execute(
            """
            CREATE TABLE test_users (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT UNIQUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )
        conn.execute(
            """
            CREATE TABLE test_orders (
                id INTEGER PRIMARY KEY,
                user_id INTEGER,
                amount DECIMAL(10,2),
                status TEXT DEFAULT 'pending',
                FOREIGN KEY (user_id) REFERENCES test_users (id)
            )
        """
        )

        # Insert test data
        conn.execute(
            "INSERT INTO test_users (name, email) VALUES (?, ?)",
            ("John Doe", "john@example.com"),
        )
        conn.execute(
            "INSERT INTO test_users (name, email) VALUES (?, ?)",
            ("Jane Smith", "jane@example.com"),
        )
        conn.execute(
            "INSERT INTO test_orders (user_id, amount) VALUES (?, ?)", (1, 99.99)
        )
        conn.commit()
        conn.close()

        yield temp_file.name

        # Cleanup
        if os.path.exists(temp_file.name):
            os.unlink(temp_file.name)

    @pytest.fixture
    def sql_node(self, temp_database):
        """Create SQL node with temporary database."""
        return SQLDatabaseNode(connection_string=f"sqlite:///{temp_database}")

    @pytest.fixture
    def bulkhead_manager(self):
        """Create fresh bulkhead manager for testing."""
        return BulkheadManager()

    @pytest.mark.asyncio
    async def test_sql_operations_with_database_partition(
        self, sql_node, bulkhead_manager
    ):
        """Test SQL operations through database partition."""
        database_partition = bulkhead_manager.get_partition("database")

        # Wrapper function for SQL operations
        async def execute_sql_async(query, params=None):
            # Use asyncio.to_thread to make the sync call async-compatible
            return await asyncio.to_thread(
                sql_node.execute, query=query, parameters=params
            )

        # Test SELECT operation
        result = await database_partition.execute(
            execute_sql_async, "SELECT * FROM test_users"
        )

        # SQLNode returns data directly, no success wrapper
        assert "data" in result
        assert len(result["data"]) == 2
        assert result["data"][0]["name"] in ["John Doe", "Jane Smith"]

        # Check partition metrics
        status = database_partition.get_status()
        assert status["metrics"]["total_operations"] >= 1
        assert status["metrics"]["successful_operations"] >= 1

    @pytest.mark.asyncio
    async def test_concurrent_sql_operations(self, sql_node, bulkhead_manager):
        """Test concurrent SQL operations with isolation."""
        database_partition = bulkhead_manager.get_partition("database")

        async def execute_sql_async(query, params=None):
            return await asyncio.to_thread(
                sql_node.execute, query=query, parameters=params
            )

        # Define various SQL operations
        operations = [
            ("SELECT COUNT(*) as user_count FROM test_users", None),
            ("SELECT * FROM test_users WHERE id = ?", [1]),
            ("SELECT * FROM test_orders WHERE user_id = ?", [1]),
            ("SELECT name FROM test_users ORDER BY name", None),
        ]

        # Execute all operations concurrently
        tasks = [
            database_partition.execute(execute_sql_async, query, params)
            for query, params in operations
        ]

        results = await asyncio.gather(*tasks)

        # Verify all operations succeeded
        assert len(results) == 4
        # All operations should return valid SQL results
        for result in results:
            assert isinstance(result, dict)
            assert len(result) > 0  # Not empty

        # Check specific results
        count_result = results[0]
        assert count_result["data"][0]["user_count"] == 2

        user_result = results[1]
        assert user_result["data"][0]["name"] == "John Doe"

        # Check partition handled all operations
        status = database_partition.get_status()
        assert status["metrics"]["total_operations"] >= 4

    @pytest.mark.asyncio
    async def test_sql_operations_with_different_partitions(
        self, sql_node, bulkhead_manager
    ):
        """Test SQL operations across different partition types."""

        async def execute_sql_async(query, params=None):
            return await asyncio.to_thread(
                sql_node.execute, query=query, parameters=params
            )

        # Use critical partition for important query
        critical_partition = bulkhead_manager.get_partition("critical")
        critical_result = await critical_partition.execute(
            execute_sql_async,
            "SELECT * FROM test_users WHERE email = ?",
            ["john@example.com"],
        )

        # Use background partition for less important query
        background_partition = bulkhead_manager.get_partition("background")
        background_result = await background_partition.execute(
            execute_sql_async, "SELECT COUNT(*) as total FROM test_orders"
        )

        # Both should succeed (check actual SQL results)
        assert "data" in critical_result
        assert "data" in background_result

        # Check metrics for both partitions
        critical_status = critical_partition.get_status()
        background_status = background_partition.get_status()

        assert critical_status["metrics"]["total_operations"] >= 1
        assert background_status["metrics"]["total_operations"] >= 1

    @pytest.mark.asyncio
    async def test_sql_error_handling_with_bulkhead(self, sql_node, bulkhead_manager):
        """Test SQL error handling through bulkhead."""
        database_partition = bulkhead_manager.get_partition("database")

        def execute_invalid_sql():
            return sql_node.execute(query="SELECT * FROM nonexistent_table")

        # Should propagate SQL errors through bulkhead
        with pytest.raises(NodeExecutionError):
            await database_partition.execute(execute_invalid_sql)

        # Check that failure was recorded in partition metrics
        status = database_partition.get_status()
        assert status["metrics"]["failed_operations"] >= 1

    @pytest.mark.asyncio
    @pytest.mark.requires_isolation
    async def test_bulkhead_resource_isolation(self, sql_node):
        """Test resource isolation between partitions."""
        # Create small partitions to test isolation
        config_small = PartitionConfig(
            name="small_db",
            partition_type=PartitionType.IO_BOUND,
            max_concurrent_operations=1,
            queue_size=0,  # No queuing - reject immediately when busy
            timeout=5,
            circuit_breaker_enabled=False,
        )

        config_normal = PartitionConfig(
            name="normal_db",
            partition_type=PartitionType.IO_BOUND,
            max_concurrent_operations=5,
            timeout=10,
            circuit_breaker_enabled=False,
        )

        manager = BulkheadManager()
        small_partition = manager.create_partition(config_small)
        normal_partition = manager.create_partition(config_normal)

        try:

            def slow_query():
                import time

                time.sleep(0.1)  # Simulate slow query (brief delay for testing)
                return sql_node.execute(query="SELECT COUNT(*) FROM test_users")

            def fast_query():
                return sql_node.execute(query="SELECT 1 as test")

            # Start slow operation in small partition
            slow_task = asyncio.create_task(small_partition.execute(slow_query))
            await asyncio.sleep(0.05)  # Let it start and begin execution

            # Small partition should be busy, but normal partition should work
            normal_result = await normal_partition.execute(fast_query)
            # Bulkhead returns raw SQL result, check for actual data
            assert "data" in normal_result  # SQLNode returns {"data": [...]}

            # Small partition should reject additional operations
            with pytest.raises(BulkheadRejectionError):
                await small_partition.execute(fast_query)

            # Wait for slow task to complete
            slow_result = await slow_task
            # Check that slow task completed successfully
            assert "data" in slow_result

        finally:
            # Clean up bulkhead manager
            await manager.shutdown_all()

    @pytest.mark.asyncio
    async def test_sql_transaction_isolation(self, temp_database, bulkhead_manager):
        """Test SQL transaction behavior with bulkhead isolation."""
        database_partition = bulkhead_manager.get_partition("database")

        # Create multiple SQL nodes to simulate different connections
        sql_node1 = SQLDatabaseNode(connection_string=f"sqlite:///{temp_database}")
        sql_node2 = SQLDatabaseNode(connection_string=f"sqlite:///{temp_database}")

        def insert_user(sql_node, name, email):
            return sql_node.execute(
                query="INSERT INTO test_users (name, email) VALUES (?, ?)",
                parameters=[name, email],
            )

        def count_users(sql_node):
            return sql_node.execute(query="SELECT COUNT(*) as count FROM test_users")

        # Concurrent inserts through bulkhead
        tasks = [
            database_partition.execute(
                insert_user, sql_node1, "Alice", "alice@example.com"
            ),
            database_partition.execute(
                insert_user, sql_node2, "Bob", "bob@example.com"
            ),
            database_partition.execute(count_users, sql_node1),
        ]

        results = await asyncio.gather(*tasks)

        # All operations should succeed (check for actual SQL results)
        # Insert operations return affected_rows, SELECT returns data
        for result in results:
            assert isinstance(result, dict)
            # Either has 'data' (SELECT) or 'affected_rows' (INSERT) or other SQL result fields
            assert len(result) > 0  # Not empty

        # Final count should include new users
        final_count = await database_partition.execute(count_users, sql_node1)
        assert final_count["data"][0]["count"] >= 4  # Original 2 + 2 new


class TestBulkheadPerformanceMetrics:
    """Test bulkhead performance metrics and monitoring."""

    @pytest.fixture
    def temp_database(self):
        """Create temporary SQLite database for performance testing."""
        temp_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        temp_file.close()

        conn = sqlite3.connect(temp_file.name)
        conn.execute(
            """
            CREATE TABLE performance_test (
                id INTEGER PRIMARY KEY,
                data TEXT,
                value INTEGER
            )
        """
        )

        # Insert test data
        for i in range(100):
            conn.execute(
                "INSERT INTO performance_test (data, value) VALUES (?, ?)",
                (f"data_{i}", i),
            )
        conn.commit()
        conn.close()

        yield temp_file.name

        if os.path.exists(temp_file.name):
            os.unlink(temp_file.name)

    @pytest.mark.asyncio
    async def test_performance_metrics_tracking(self, temp_database):
        """Test that bulkhead tracks performance metrics correctly."""
        sql_node = SQLDatabaseNode(connection_string=f"sqlite:///{temp_database}")
        manager = BulkheadManager()
        partition = manager.get_partition("database")

        def execute_query(query):
            return sql_node.execute(query=query)

        # Execute several operations with varying complexity
        operations = [
            "SELECT COUNT(*) FROM performance_test",
            "SELECT * FROM performance_test WHERE value < 10",
            "SELECT AVG(value) FROM performance_test",
            "SELECT * FROM performance_test ORDER BY value DESC LIMIT 5",
        ]

        for query in operations:
            await partition.execute(execute_query, query)

        # Check metrics
        status = partition.get_status()
        metrics = status["metrics"]

        assert metrics["total_operations"] == len(operations)
        assert metrics["successful_operations"] == len(operations)
        assert metrics["avg_execution_time"] > 0
        assert metrics["max_execution_time"] >= metrics["avg_execution_time"]
        assert metrics["success_rate"] == 1.0

    @pytest.mark.asyncio
    async def test_concurrent_performance_monitoring(self, temp_database):
        """Test performance monitoring under concurrent load."""
        sql_node = SQLDatabaseNode(connection_string=f"sqlite:///{temp_database}")
        manager = BulkheadManager()
        partition = manager.get_partition("database")

        def execute_query(query_id):
            import time

            start = time.time()
            result = sql_node.execute(
                query="SELECT * FROM performance_test WHERE value = ?",
                parameters=[query_id % 10],
            )
            return result

        # Execute many concurrent operations
        tasks = [partition.execute(execute_query, i) for i in range(20)]

        results = await asyncio.gather(*tasks)

        # All should succeed (check for actual SQL results)
        for result in results:
            assert isinstance(result, dict)
            assert len(result) > 0  # Not empty

        # Check that metrics reflect concurrent execution
        status = partition.get_status()
        metrics = status["metrics"]

        assert metrics["total_operations"] == 20
        assert metrics["successful_operations"] == 20
        assert metrics["avg_execution_time"] > 0


class TestBulkheadGlobalIntegration:
    """Test global bulkhead manager integration."""

    @pytest.fixture
    def temp_database(self):
        """Create temporary SQLite database for testing."""
        temp_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        temp_file.close()

        # Initialize database
        conn = sqlite3.connect(temp_file.name)
        conn.execute(
            """
            CREATE TABLE test_users (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT UNIQUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )
        conn.execute(
            "INSERT INTO test_users (name, email) VALUES (?, ?)",
            ("John Doe", "john@example.com"),
        )
        conn.commit()
        conn.close()

        yield temp_file.name

        # Cleanup
        if os.path.exists(temp_file.name):
            os.unlink(temp_file.name)

    @pytest.fixture
    def sql_node(self, temp_database):
        """Create SQL node with temporary database."""
        return SQLDatabaseNode(connection_string=f"sqlite:///{temp_database}")

    @pytest.mark.asyncio
    async def test_global_manager_integration(self, sql_node):
        """Test using global bulkhead manager for SQL operations."""
        from kailash.core.resilience.bulkhead import execute_with_bulkhead

        def sql_operation():
            return sql_node.execute(query="SELECT 1 as test")

        # Use global convenience function
        result = await execute_with_bulkhead("database", sql_operation)

        # Check actual SQL result
        assert "data" in result
        assert result["data"][0]["test"] == 1

        # Check that global manager tracked the operation
        manager = get_bulkhead_manager()
        status = manager.get_all_status()

        assert "database" in status
        assert status["database"]["metrics"]["total_operations"] >= 1

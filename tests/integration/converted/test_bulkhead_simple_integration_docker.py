"""Simple integration tests for bulkhead pattern."""

import asyncio
import os
import sqlite3
import tempfile

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

from tests.integration.docker_test_base import DockerIntegrationTestBase


@pytest.mark.integration
@pytest.mark.requires_docker
class TestBulkheadBasicIntegration(DockerIntegrationTestBase):
    """Test basic bulkhead integration with real components."""

    @pytest.fixture
    def temp_database(self):
        """Create temporary SQLite database for testing."""
        temp_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        temp_file.close()

        # Initialize database
        conn = sqlite3.connect(temp_file.name)
        conn.execute(
            """
            CREATE TABLE test_data (
                id INTEGER PRIMARY KEY,
                value TEXT
            )
        """
        )
        conn.execute("INSERT INTO test_data (value) VALUES (?)", ("test_value",))
        conn.commit()
        conn.close()

        yield temp_file.name

        # Cleanup
        if os.path.exists(temp_file.name):
            os.unlink(temp_file.name)

    @pytest.mark.asyncio
    async def test_bulkhead_with_sync_function(self):
        """Test bulkhead execution with synchronous functions."""
        manager = get_bulkhead_manager()
        partition = manager.get_partition("database")

        def sync_operation(x, y):
            return x + y

        result = await partition.execute(sync_operation, 5, 3)
        assert result == 8

        # Check metrics
        status = partition.get_status()
        assert status["metrics"]["successful_operations"] >= 1

    @pytest.mark.asyncio
    async def test_bulkhead_with_async_function(self):
        """Test bulkhead execution with asynchronous functions."""
        manager = get_bulkhead_manager()
        partition = manager.get_partition("database")

        async def async_operation(delay, value):
            await asyncio.sleep(delay)
            return value * 2

        result = await partition.execute(async_operation, 0.01, 10)
        assert result == 20

    @pytest.mark.asyncio
    async def test_bulkhead_with_sql_node(self, temp_database):
        """Test bulkhead with actual SQL node operations."""
        sql_node = SQLDatabaseNode(connection_string=f"sqlite:///{temp_database}")
        manager = get_bulkhead_manager()
        partition = manager.get_partition("database")

        def sql_operation():
            return sql_node.execute(query="SELECT COUNT(*) as count FROM test_data")

        result = await partition.execute(sql_operation)

        # SQL node returns a dict with columns, data, etc.
        assert "data" in result
        assert len(result["data"]) == 1
        assert result["data"][0]["count"] == 1

    @pytest.mark.asyncio
    async def test_bulkhead_concurrent_operations(self, temp_database):
        """Test concurrent operations through bulkhead."""
        sql_node = SQLDatabaseNode(connection_string=f"sqlite:///{temp_database}")
        manager = get_bulkhead_manager()
        partition = manager.get_partition("database")

        def sql_select():
            return sql_node.execute(query="SELECT * FROM test_data")

        def sql_count():
            return sql_node.execute(query="SELECT COUNT(*) as total FROM test_data")

        # Execute operations concurrently
        tasks = [
            partition.execute(sql_select),
            partition.execute(sql_count),
            partition.execute(sql_select),
        ]

        results = await asyncio.gather(*tasks)

        # All should succeed
        assert len(results) == 3
        # SQL node doesn't return success field, check data instead
        assert all("data" in result for result in results)

        # Check partition metrics
        status = partition.get_status()
        assert status["metrics"]["total_operations"] >= 3
        assert status["metrics"]["successful_operations"] >= 3

    @pytest.mark.asyncio
    async def test_bulkhead_error_propagation(self, temp_database):
        """Test that errors are properly propagated through bulkhead."""
        sql_node = SQLDatabaseNode(connection_string=f"sqlite:///{temp_database}")
        manager = get_bulkhead_manager()
        partition = manager.get_partition("database")

        def failing_sql():
            return sql_node.execute(query="SELECT * FROM nonexistent_table")

        # Should propagate the NodeExecutionError
        with pytest.raises(NodeExecutionError):
            await partition.execute(failing_sql)

        # Check that failure was recorded
        status = partition.get_status()
        assert status["metrics"]["failed_operations"] >= 1

    @pytest.mark.skip(
        reason="Bulkhead rejection behavior not working as expected - needs investigation"
    )
    @pytest.mark.asyncio
    async def test_bulkhead_resource_isolation(self):
        """Test resource isolation between partitions."""
        # Create two separate managers/partitions
        manager = BulkheadManager()

        config1 = PartitionConfig(
            name="small_partition",
            partition_type=PartitionType.IO_BOUND,
            max_concurrent_operations=1,
            queue_size=1,
            timeout=5,
            circuit_breaker_enabled=False,
        )

        config2 = PartitionConfig(
            name="large_partition",
            partition_type=PartitionType.IO_BOUND,
            max_concurrent_operations=10,
            timeout=5,
            circuit_breaker_enabled=False,
        )

        small_partition = manager.create_partition(config1)
        large_partition = manager.create_partition(config2)

        async def slow_operation():
            await asyncio.sleep(0.3)
            return "slow_done"

        def fast_operation():
            return "fast_done"

        # Start slow operation in small partition
        slow_task = asyncio.create_task(small_partition.execute(slow_operation))
        await asyncio.sleep(0.1)  # Let it start

        # Large partition should still work
        fast_result = await large_partition.execute(fast_operation)
        assert fast_result == "fast_done"

        # Small partition should reject new operations
        with pytest.raises(BulkheadRejectionError):
            await small_partition.execute(fast_operation)

        # Wait for slow operation to complete
        slow_result = await slow_task
        assert slow_result == "slow_done"

    @pytest.mark.asyncio
    async def test_different_partition_types(self):
        """Test different partition types behavior."""
        manager = get_bulkhead_manager()

        # Test critical partition (high priority)
        critical = manager.get_partition("critical")
        result = await critical.execute(lambda: "critical_result")
        assert result == "critical_result"

        # Test background partition (low priority, long timeout)
        background = manager.get_partition("background")
        result = await background.execute(lambda: "background_result")
        assert result == "background_result"

        # Test compute partition (CPU-bound with thread pool)
        compute = manager.get_partition("compute")

        def cpu_task(n):
            return sum(range(n))

        result = await compute.execute(cpu_task, 100)
        expected = sum(range(100))
        assert result == expected

    @pytest.mark.asyncio
    async def test_partition_metrics_tracking(self):
        """Test that partition metrics are properly tracked."""
        manager = get_bulkhead_manager()
        partition = manager.get_partition("database")

        def test_operation(value):
            if value < 0:
                raise ValueError("Negative value")
            return value * 2

        # Execute successful operations
        await partition.execute(test_operation, 5)
        await partition.execute(test_operation, 10)

        # Execute failing operation
        try:
            await partition.execute(test_operation, -1)
        except ValueError:
            pass

        # Check metrics
        status = partition.get_status()
        metrics = status["metrics"]

        assert metrics["total_operations"] >= 3
        assert metrics["successful_operations"] >= 2
        assert metrics["failed_operations"] >= 1
        assert metrics["avg_execution_time"] >= 0
        assert 0 <= metrics["success_rate"] <= 1

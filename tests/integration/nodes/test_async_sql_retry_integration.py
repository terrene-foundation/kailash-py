"""Integration tests for AsyncSQLDatabaseNode retry logic with REAL PostgreSQL."""

import asyncio
import time
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio

from kailash.nodes.data.async_sql import AsyncSQLDatabaseNode, RetryConfig
from kailash.sdk_exceptions import NodeExecutionError
from tests.utils.docker_config import get_postgres_connection_string

# Mark all tests as requiring postgres and as integration tests
pytestmark = [pytest.mark.integration, pytest.mark.requires_postgres]


class TestAsyncSQLRetryIntegration:
    """Test retry functionality with REAL PostgreSQL database."""

    @pytest_asyncio.fixture
    async def setup_database(self):
        """Set up test database."""
        conn_string = get_postgres_connection_string()

        # Create test table
        setup_node = AsyncSQLDatabaseNode(
            name="setup",
            database_type="postgresql",
            connection_string=conn_string,
            allow_admin=True,
        )

        await setup_node.execute_async(query="DROP TABLE IF EXISTS retry_test")
        await setup_node.execute_async(
            query="""
            CREATE TABLE retry_test (
                id SERIAL PRIMARY KEY,
                value VARCHAR(100),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )

        yield conn_string

        # Cleanup
        await setup_node.execute_async(query="DROP TABLE IF EXISTS retry_test")
        await setup_node.cleanup()

    @pytest.mark.asyncio
    async def test_connection_retry_with_wrong_host(self):
        """Test connection retry with wrong host."""
        # Use a non-existent host to simulate connection failure
        node = AsyncSQLDatabaseNode(
            name="test_retry",
            database_type="postgresql",
            host="non.existent.host",
            port=5432,
            database="testdb",
            user="testuser",
            password="testpass",
            max_retries=2,
            retry_delay=0.1,
        )

        start_time = time.time()

        with pytest.raises(
            NodeExecutionError, match="Failed to connect after 2 attempts"
        ):
            await node.execute_async(query="SELECT 1")

        elapsed = time.time() - start_time

        # Should have tried twice with a delay
        assert elapsed >= 0.1  # At least one retry delay
        assert elapsed < 1.0  # But not too long

    @pytest.mark.asyncio
    async def test_query_retry_on_deadlock(self, setup_database):
        """Test retry on simulated deadlock errors."""
        conn_string = setup_database

        node = AsyncSQLDatabaseNode(
            name="test_node",
            database_type="postgresql",
            connection_string=conn_string,
            retry_config={
                "max_retries": 3,
                "initial_delay": 0.1,
                "retryable_errors": ["deadlock", "connection reset"],
            },
        )

        # Insert test data
        await node.execute_async(
            query="INSERT INTO retry_test (value) VALUES (:value)",
            params={"value": "test_value"},
        )

        # Mock execute to simulate deadlock on first attempt
        original_execute = node._adapter.execute
        call_count = 0

        async def mock_execute(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("deadlock detected")
            return await original_execute(*args, **kwargs)

        node._adapter.execute = mock_execute

        # Should succeed after retry
        result = await node.execute_async(
            query="SELECT * FROM retry_test WHERE value = :value",
            params={"value": "test_value"},
        )

        assert len(result["result"]["data"]) == 1
        assert call_count == 2  # First attempt failed, second succeeded

        await node.cleanup()

    @pytest.mark.asyncio
    async def test_transaction_retry_rollback(self, setup_database):
        """Test that failed transactions are properly rolled back during retry."""
        conn_string = setup_database

        node = AsyncSQLDatabaseNode(
            name="test_node",
            database_type="postgresql",
            connection_string=conn_string,
            transaction_mode="auto",
            max_retries=3,
            retry_delay=0.1,
        )

        # Insert initial data
        await node.execute_async(
            query="INSERT INTO retry_test (value) VALUES (:value)",
            params={"value": "initial"},
        )

        # Check initial count
        result = await node.execute_async(
            query="SELECT COUNT(*) as count FROM retry_test"
        )
        initial_count = result["result"]["data"][0]["count"]

        # Mock to fail on constraint violation (non-retryable)
        with patch.object(node._adapter, "execute") as mock_execute:
            mock_execute.side_effect = Exception(
                "duplicate key value violates unique constraint"
            )

            with pytest.raises(NodeExecutionError):
                await node.execute_async(
                    query="INSERT INTO retry_test (value) VALUES (:value)",
                    params={"value": "duplicate"},
                )

        # Verify no data was inserted (transaction rolled back)
        result = await node.execute_async(
            query="SELECT COUNT(*) as count FROM retry_test"
        )
        final_count = result["result"]["data"][0]["count"]

        assert final_count == initial_count

        await node.cleanup()

    @pytest.mark.asyncio
    async def test_pool_reconnection_after_close(self, setup_database):
        """Test automatic reconnection when pool is closed."""
        conn_string = setup_database

        node = AsyncSQLDatabaseNode(
            name="test_node",
            database_type="postgresql",
            connection_string=conn_string,
            max_retries=3,
            retry_delay=0.1,
        )

        # Execute a query to establish connection
        await node.execute_async(
            query="INSERT INTO retry_test (value) VALUES (:value)",
            params={"value": "test1"},
        )

        # Force close the pool
        if node._adapter and hasattr(node._adapter, "_pool"):
            await node._adapter._pool.close()

        # Next query should reconnect automatically
        result = await node.execute_async(
            query="SELECT * FROM retry_test WHERE value = :value",
            params={"value": "test1"},
        )

        assert len(result["result"]["data"]) == 1
        assert result["result"]["data"][0]["value"] == "test1"

        await node.cleanup()

    @pytest.mark.asyncio
    async def test_exponential_backoff_timing(self, setup_database):
        """Test that exponential backoff is applied correctly."""
        conn_string = setup_database

        node = AsyncSQLDatabaseNode(
            name="test_node",
            database_type="postgresql",
            connection_string=conn_string,
            retry_config={
                "max_retries": 3,
                "initial_delay": 0.1,
                "exponential_base": 2.0,
                "jitter": False,  # No jitter for predictable timing
            },
        )

        # Track retry attempts and delays
        retry_times = []
        original_execute = node._adapter.execute

        async def mock_execute(*args, **kwargs):
            retry_times.append(time.time())
            if len(retry_times) < 3:
                raise Exception("connection reset")
            return await original_execute(*args, **kwargs)

        node._adapter.execute = mock_execute

        # Execute query that will retry
        start_time = time.time()
        result = await node.execute_async(query="SELECT 1")

        # Check delays between retries
        assert len(retry_times) == 3

        # First retry after ~0.1s
        first_delay = retry_times[1] - retry_times[0]
        assert 0.09 < first_delay < 0.15

        # Second retry after ~0.2s (0.1 * 2^1)
        second_delay = retry_times[2] - retry_times[1]
        assert 0.18 < second_delay < 0.25

        await node.cleanup()

    @pytest.mark.asyncio
    async def test_non_retryable_errors_fail_immediately(self, setup_database):
        """Test that non-retryable errors fail without retry."""
        conn_string = setup_database

        node = AsyncSQLDatabaseNode(
            name="test_node",
            database_type="postgresql",
            connection_string=conn_string,
            max_retries=3,
        )

        # Try to query non-existent table (non-retryable error)
        call_count = 0
        original_execute = node._adapter.execute

        async def mock_execute(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return await original_execute(*args, **kwargs)

        node._adapter.execute = mock_execute

        with pytest.raises(NodeExecutionError):
            await node.execute_async(query="SELECT * FROM non_existent_table")

        # Should fail immediately without retries
        assert call_count == 1

        await node.cleanup()

    @pytest.mark.asyncio
    async def test_custom_retryable_errors(self, setup_database):
        """Test custom retryable error patterns."""
        conn_string = setup_database

        node = AsyncSQLDatabaseNode(
            name="test_node",
            database_type="postgresql",
            connection_string=conn_string,
            retry_config={
                "max_retries": 3,
                "initial_delay": 0.1,
                "retryable_errors": ["custom_error", "another_error"],
            },
        )

        # Mock to throw custom error
        call_count = 0
        original_execute = node._adapter.execute

        async def mock_execute(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise Exception("This is a custom_error that should retry")
            return await original_execute(*args, **kwargs)

        node._adapter.execute = mock_execute

        # Should retry on custom error
        result = await node.execute_async(query="SELECT 1")
        assert call_count == 3

        # Reset
        call_count = 0

        async def mock_execute_non_retryable(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            raise Exception("This is not a retryable error")

        node._adapter.execute = mock_execute_non_retryable

        # Should not retry on non-matching error
        with pytest.raises(NodeExecutionError):
            await node.execute_async(query="SELECT 1")

        assert call_count == 1

        await node.cleanup()

    @pytest.mark.asyncio
    async def test_concurrent_queries_with_retry(self, setup_database):
        """Test multiple concurrent queries with retry logic."""
        conn_string = setup_database

        # Create multiple nodes
        nodes = []
        for i in range(3):
            node = AsyncSQLDatabaseNode(
                name=f"node_{i}",
                database_type="postgresql",
                connection_string=conn_string,
                max_retries=2,
                retry_delay=0.1,
            )
            nodes.append(node)

        # Simulate intermittent failures
        async def insert_with_retry(node, value):
            # Mock to fail first attempt
            original_execute = node._adapter.execute
            attempts = 0

            async def mock_execute(*args, **kwargs):
                nonlocal attempts
                attempts += 1
                if attempts == 1 and "INSERT" in args[0]:
                    raise Exception("connection reset")
                return await original_execute(*args, **kwargs)

            node._adapter.execute = mock_execute

            result = await node.execute_async(
                query="INSERT INTO retry_test (value) VALUES (:value) RETURNING id",
                params={"value": value},
            )
            return result["result"]["data"][0]["id"], attempts

        # Run concurrent inserts
        tasks = []
        for i, node in enumerate(nodes):
            tasks.append(insert_with_retry(node, f"concurrent_{i}"))

        results = await asyncio.gather(*tasks)

        # All should succeed after retry
        for id, attempts in results:
            assert id is not None
            assert attempts == 2  # First failed, second succeeded

        # Verify all data was inserted
        verify_node = nodes[0]
        result = await verify_node.execute_async(
            query="SELECT COUNT(*) as count FROM retry_test WHERE value LIKE 'concurrent_%'"
        )
        assert result["result"]["data"][0]["count"] == 3

        # Cleanup
        for node in nodes:
            await node.cleanup()

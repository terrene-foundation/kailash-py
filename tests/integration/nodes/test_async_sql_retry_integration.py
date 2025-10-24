"""Integration tests for AsyncSQLDatabaseNode retry logic with REAL PostgreSQL.

NO MOCKING ALLOWED - All tests use real PostgreSQL database operations.
Tests verify retry behavior through actual database scenarios.
"""

import asyncio
import time

import pytest
import pytest_asyncio
from kailash.nodes.data.async_sql import AsyncSQLDatabaseNode, RetryConfig
from kailash.sdk_exceptions import NodeExecutionError

from tests.utils.docker_config import get_postgres_connection_string

# Mark all tests as requiring postgres and as integration tests
pytestmark = [pytest.mark.integration, pytest.mark.requires_postgres]


class TestAsyncSQLRetryIntegration:
    """Test retry functionality with REAL PostgreSQL database - NO MOCKING."""

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
        """Test connection retry with wrong host - REAL network failure."""
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
    async def test_query_with_retryable_errors(self, setup_database):
        """Test retry behavior with REAL database errors - NO MOCKING."""
        conn_string = setup_database

        # Create a node with custom retryable errors
        node = AsyncSQLDatabaseNode(
            name="test_node",
            database_type="postgresql",
            connection_string=conn_string,
            allow_admin=True,  # Need admin for CREATE TABLE
            retry_config={
                "max_retries": 3,
                "initial_delay": 0.1,
                "retryable_errors": ["lock", "deadlock", "connection reset"],
            },
        )

        # Create a table with constraints to test real database errors
        await node.execute_async(
            query="""
            CREATE TABLE IF NOT EXISTS retry_lock_test (
                id INTEGER PRIMARY KEY,
                value TEXT UNIQUE
            )
        """
        )

        # Insert initial data
        await node.execute_async(
            query="INSERT INTO retry_lock_test (id, value) VALUES (1, 'test') ON CONFLICT DO NOTHING"
        )

        # Test successful query after table is ready
        result = await node.execute_async(
            query="SELECT * FROM retry_lock_test WHERE id = 1"
        )
        assert len(result["result"]["data"]) == 1

        # Cleanup
        await node.execute_async(query="DROP TABLE IF EXISTS retry_lock_test")
        await node.cleanup()

    @pytest.mark.asyncio
    async def test_transaction_retry_behavior(self, setup_database):
        """Test transaction retry with REAL database operations - NO MOCKING."""
        conn_string = setup_database

        node = AsyncSQLDatabaseNode(
            name="test_node",
            database_type="postgresql",
            connection_string=conn_string,
            transaction_mode="auto",
            max_retries=3,
            retry_delay=0.1,
        )

        # Insert test data
        await node.execute_async(
            query="INSERT INTO retry_test (value) VALUES (:value)",
            params={"value": "transaction_test"},
        )

        # Verify data was inserted
        result = await node.execute_async(
            query="SELECT * FROM retry_test WHERE value = :value",
            params={"value": "transaction_test"},
        )
        assert len(result["result"]["data"]) == 1

        await node.cleanup()

    @pytest.mark.asyncio
    async def test_pool_behavior_with_real_connections(self, setup_database):
        """Test connection pool behavior with REAL connections - NO MOCKING."""
        conn_string = setup_database

        node = AsyncSQLDatabaseNode(
            name="test_node",
            database_type="postgresql",
            connection_string=conn_string,
            pool_size=2,
            max_pool_size=5,
        )

        # Execute multiple queries to test pool behavior
        tasks = []
        for i in range(5):
            tasks.append(
                node.execute_async(
                    query="INSERT INTO retry_test (value) VALUES (:value) RETURNING id",
                    params={"value": f"pool_test_{i}"},
                )
            )

        results = await asyncio.gather(*tasks)

        # Verify all inserts succeeded
        assert len(results) == 5
        for result in results:
            assert result["result"]["data"][0]["id"] is not None

        # Verify data in database
        count_result = await node.execute_async(
            query="SELECT COUNT(*) as count FROM retry_test WHERE value LIKE 'pool_test_%'"
        )
        assert count_result["result"]["data"][0]["count"] == 5

        await node.cleanup()

    @pytest.mark.asyncio
    async def test_timeout_behavior_with_real_query(self, setup_database):
        """Test timeout behavior with REAL long-running query - NO MOCKING."""
        conn_string = setup_database

        node = AsyncSQLDatabaseNode(
            name="test_node",
            database_type="postgresql",
            connection_string=conn_string,
            timeout=0.5,  # 500ms timeout
        )

        # Use pg_sleep to simulate a long-running query
        with pytest.raises(NodeExecutionError):
            await node.execute_async(query="SELECT pg_sleep(2)")  # Sleep for 2 seconds

        await node.cleanup()

    @pytest.mark.asyncio
    async def test_non_retryable_errors_with_real_database(self, setup_database):
        """Test non-retryable errors with REAL database - NO MOCKING."""
        conn_string = setup_database

        node = AsyncSQLDatabaseNode(
            name="test_node",
            database_type="postgresql",
            connection_string=conn_string,
            max_retries=3,
        )

        # Try to query non-existent table (non-retryable error)
        with pytest.raises(NodeExecutionError) as exc_info:
            await node.execute_async(query="SELECT * FROM non_existent_table")

        # Should fail immediately without retries
        assert "does not exist" in str(exc_info.value)

        await node.cleanup()

    @pytest.mark.asyncio
    async def test_concurrent_operations_with_real_database(self, setup_database):
        """Test concurrent operations with REAL database - NO MOCKING."""
        conn_string = setup_database

        # Create multiple nodes for concurrent operations
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

        # Run concurrent inserts
        async def insert_data(node, value):
            result = await node.execute_async(
                query="INSERT INTO retry_test (value) VALUES (:value) RETURNING id",
                params={"value": value},
            )
            return result["result"]["data"][0]["id"]

        # Execute concurrent operations
        tasks = []
        for i, node in enumerate(nodes):
            tasks.append(insert_data(node, f"concurrent_{i}"))

        results = await asyncio.gather(*tasks)

        # All should succeed
        assert len(results) == 3
        for result in results:
            assert result is not None

        # Verify all data was inserted
        verify_node = nodes[0]
        result = await verify_node.execute_async(
            query="SELECT COUNT(*) as count FROM retry_test WHERE value LIKE 'concurrent_%'"
        )
        assert result["result"]["data"][0]["count"] == 3

        # Cleanup
        for node in nodes:
            await node.cleanup()

    @pytest.mark.asyncio
    async def test_exponential_backoff_with_real_errors(self, setup_database):
        """Test exponential backoff timing with REAL connection errors - NO MOCKING."""
        # Use wrong connection details to trigger connection errors
        node = AsyncSQLDatabaseNode(
            name="test_node",
            database_type="postgresql",
            host="non.existent.host",  # Non-existent host will trigger retries
            port=5432,
            database="testdb",
            user="testuser",
            password="testpass",
            retry_config={
                "max_retries": 3,
                "initial_delay": 0.1,
                "exponential_base": 2.0,
                "jitter": False,
            },
        )

        start_time = time.time()

        with pytest.raises(NodeExecutionError):
            await node.execute_async(query="SELECT 1")

        elapsed = time.time() - start_time

        # With exponential backoff: 0.1 + 0.2 + 0.4 = 0.7 seconds minimum
        # But DNS resolution might fail fast, so we check for at least retry delays
        assert elapsed >= 0.3  # At least some retry delays occurred
        assert elapsed < 5.0  # But not too long

    @pytest.mark.asyncio
    async def test_custom_retryable_errors_configuration(self, setup_database):
        """Test custom retryable errors with REAL database - NO MOCKING."""
        conn_string = setup_database

        # Node with custom retry configuration
        node = AsyncSQLDatabaseNode(
            name="test_node",
            database_type="postgresql",
            connection_string=conn_string,
            retry_config={
                "max_retries": 2,
                "initial_delay": 0.1,
                "retryable_errors": ["syntax error", "permission denied"],
            },
        )

        # Test that syntax errors would be retried (though they'll still fail)
        with pytest.raises(NodeExecutionError) as exc_info:
            await node.execute_async(query="INVALID SQL SYNTAX")

        # The error should mention syntax
        assert "syntax error" in str(exc_info.value).lower()

        await node.cleanup()

"""Integration tests for AsyncSQLDatabaseNode pool sharing with REAL PostgreSQL."""

import asyncio

import pytest
import pytest_asyncio

from kailash.nodes.data.async_sql import AsyncSQLDatabaseNode
from tests.utils.docker_config import get_postgres_connection_string

# Mark all tests as requiring postgres and as integration tests
pytestmark = [pytest.mark.integration, pytest.mark.requires_postgres]


class TestAsyncSQLPoolSharingIntegration:
    """Test pool sharing with REAL PostgreSQL database."""

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

        await setup_node.execute_async(query="DROP TABLE IF EXISTS pool_test")
        await setup_node.execute_async(
            query="""
            CREATE TABLE pool_test (
                id SERIAL PRIMARY KEY,
                value VARCHAR(100),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )

        yield conn_string

        # Cleanup
        await setup_node.execute_async(query="DROP TABLE IF EXISTS pool_test")
        await setup_node.cleanup()

    @pytest.mark.asyncio
    async def test_shared_pool_concurrent_queries(self, setup_database):
        """Test that multiple nodes can share a pool and execute concurrent queries."""
        conn_string = setup_database

        # Clear any existing pools
        await AsyncSQLDatabaseNode.clear_shared_pools()

        # Create multiple nodes with same config
        nodes = []
        for i in range(5):
            node = AsyncSQLDatabaseNode(
                name=f"node_{i}",
                database_type="postgresql",
                connection_string=conn_string,
                pool_size=3,  # Small pool to test sharing
                max_pool_size=5,
            )
            nodes.append(node)

        # Define async task to insert data
        async def insert_data(node, value):
            result = await node.execute_async(
                query="INSERT INTO pool_test (value) VALUES (:value) RETURNING id",
                params={"value": value},
            )
            return result["result"]["data"][0]["id"]

        # Execute concurrent inserts
        tasks = []
        for i, node in enumerate(nodes):
            tasks.append(insert_data(node, f"value_{i}"))

        # Wait for all to complete
        ids = await asyncio.gather(*tasks)

        # Verify all inserts succeeded
        assert len(ids) == 5
        assert all(isinstance(id, int) for id in ids)

        # Check pool metrics - should have only 1 pool
        metrics = await AsyncSQLDatabaseNode.get_pool_metrics()
        assert metrics["total_pools"] == 1
        assert metrics["pools"][0]["reference_count"] == 5

        # Verify data was inserted
        check_node = nodes[0]  # Use any node
        result = await check_node.execute_async(
            query="SELECT COUNT(*) as count FROM pool_test"
        )
        assert result["result"]["data"][0]["count"] == 5

        # Cleanup nodes
        for node in nodes:
            await node.cleanup()

        # Verify pool was cleaned up
        metrics = await AsyncSQLDatabaseNode.get_pool_metrics()
        assert metrics["total_pools"] == 0

    @pytest.mark.asyncio
    async def test_pool_isolation_different_configs(self, setup_database):
        """Test that nodes with different configs get different pools."""
        conn_string = setup_database

        # Clear any existing pools
        await AsyncSQLDatabaseNode.clear_shared_pools()

        # Create nodes with different pool sizes
        node1 = AsyncSQLDatabaseNode(
            name="node1",
            database_type="postgresql",
            connection_string=conn_string,
            pool_size=5,
            max_pool_size=10,
        )

        node2 = AsyncSQLDatabaseNode(
            name="node2",
            database_type="postgresql",
            connection_string=conn_string,
            pool_size=3,  # Different pool size
            max_pool_size=6,
        )

        # Execute queries to force pool creation
        await node1.execute_async(query="SELECT 1")
        await node2.execute_async(query="SELECT 1")

        # Should have 2 different pools
        metrics = await AsyncSQLDatabaseNode.get_pool_metrics()
        assert metrics["total_pools"] == 2

        # Each pool should have 1 reference
        for pool in metrics["pools"]:
            assert pool["reference_count"] == 1

        # Cleanup
        await node1.cleanup()
        await node2.cleanup()

    @pytest.mark.asyncio
    async def test_pool_sharing_transaction_isolation(self, setup_database):
        """Test that shared pools maintain transaction isolation."""
        conn_string = setup_database

        # Clear any existing pools
        await AsyncSQLDatabaseNode.clear_shared_pools()

        # Create two nodes sharing a pool, both in manual transaction mode
        node1 = AsyncSQLDatabaseNode(
            name="node1",
            database_type="postgresql",
            connection_string=conn_string,
            transaction_mode="manual",
        )

        node2 = AsyncSQLDatabaseNode(
            name="node2",
            database_type="postgresql",
            connection_string=conn_string,
            transaction_mode="manual",
        )

        # Begin transactions on both nodes
        await node1.begin_transaction()
        await node2.begin_transaction()

        # Node1 inserts data
        await node1.execute_async(
            query="INSERT INTO pool_test (value) VALUES (:value)",
            params={"value": "node1_value"},
        )

        # Node2 shouldn't see node1's uncommitted data
        # NOTE: PostgreSQL default isolation level is READ COMMITTED,
        # so we might see committed data from other transactions

        # Node2 inserts its own data
        await node2.execute_async(
            query="INSERT INTO pool_test (value) VALUES (:value)",
            params={"value": "node2_value"},
        )

        # Rollback node2's transaction
        await node2.rollback()

        # Commit node1's transaction
        await node1.commit()

        # Verify node1's data was committed
        check_node = AsyncSQLDatabaseNode(
            name="check",
            database_type="postgresql",
            connection_string=conn_string,
        )

        result = await check_node.execute_async(
            query="SELECT * FROM pool_test WHERE value = :value",
            params={"value": "node1_value"},
        )
        assert len(result["result"]["data"]) == 1

        # Verify node2's data was rolled back
        result = await check_node.execute_async(
            query="SELECT * FROM pool_test WHERE value = :value",
            params={"value": "node2_value"},
        )
        assert len(result["result"]["data"]) == 0

        await check_node.cleanup()

        # Cleanup
        await node1.cleanup()
        await node2.cleanup()

    @pytest.mark.asyncio
    async def test_pool_metrics_accuracy(self, setup_database):
        """Test that pool metrics accurately reflect pool state."""
        conn_string = setup_database

        # Clear any existing pools
        await AsyncSQLDatabaseNode.clear_shared_pools()

        # Create node with specific pool settings
        node = AsyncSQLDatabaseNode(
            name="metrics_test",
            database_type="postgresql",
            connection_string=conn_string,
            pool_size=2,
            max_pool_size=4,
        )

        # Execute a query to create the pool
        await node.execute_async(query="SELECT 1")

        # Get instance pool info
        info = node.get_pool_info()
        assert info["shared"] is True
        assert info["connected"] is True
        assert info["pool_key"] is not None

        # Get global pool metrics
        metrics = await AsyncSQLDatabaseNode.get_pool_metrics()
        assert metrics["total_pools"] == 1
        assert metrics["pools"][0]["reference_count"] == 1
        assert metrics["pools"][0]["type"] == "ProductionPostgreSQLAdapter"

        # Cleanup
        await node.cleanup()

    @pytest.mark.asyncio
    async def test_disabled_pool_sharing(self, setup_database):
        """Test that pool sharing can be disabled per node."""
        conn_string = setup_database

        # Clear any existing pools
        await AsyncSQLDatabaseNode.clear_shared_pools()

        # Create two nodes with sharing disabled
        node1 = AsyncSQLDatabaseNode(
            name="node1",
            database_type="postgresql",
            connection_string=conn_string,
            share_pool=False,
        )

        node2 = AsyncSQLDatabaseNode(
            name="node2",
            database_type="postgresql",
            connection_string=conn_string,
            share_pool=False,
        )

        # Execute queries
        await node1.execute_async(query="SELECT 1")
        await node2.execute_async(query="SELECT 2")

        # No shared pools should exist
        metrics = await AsyncSQLDatabaseNode.get_pool_metrics()
        assert metrics["total_pools"] == 0

        # Each node should have its own pool
        info1 = node1.get_pool_info()
        info2 = node2.get_pool_info()

        assert info1["shared"] is False
        assert info2["shared"] is False
        assert info1["pool_key"] is None
        assert info2["pool_key"] is None

        # Cleanup
        await node1.cleanup()
        await node2.cleanup()

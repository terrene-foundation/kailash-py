"""Integration tests for AsyncSQLDatabaseNode batch operations with REAL PostgreSQL."""

import asyncio
from datetime import datetime

import pytest
import pytest_asyncio
from kailash.nodes.data.async_sql import AsyncSQLDatabaseNode
from kailash.sdk_exceptions import NodeExecutionError

from tests.utils.docker_config import get_postgres_connection_string

# Mark all tests as requiring postgres and as integration tests
pytestmark = [pytest.mark.integration, pytest.mark.requires_postgres]


class TestAsyncSQLBatchIntegration:
    """Test batch operations with REAL PostgreSQL database."""

    @pytest_asyncio.fixture
    async def setup_database(self):
        """Set up test database with batch test table."""
        conn_string = get_postgres_connection_string()

        # Create test table
        setup_node = AsyncSQLDatabaseNode(
            name="setup",
            database_type="postgresql",
            connection_string=conn_string,
            allow_admin=True,
        )

        # Drop and recreate test table
        await setup_node.execute_async(query="DROP TABLE IF EXISTS batch_test")
        await setup_node.execute_async(
            query="""
            CREATE TABLE batch_test (
                id SERIAL PRIMARY KEY,
                name VARCHAR(100),
                value INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                batch_id VARCHAR(50)
            )
        """
        )

        yield conn_string

        # Cleanup
        await setup_node.execute_async(query="DROP TABLE IF EXISTS batch_test")
        await setup_node.cleanup()

    @pytest.mark.asyncio
    async def test_basic_batch_insert(self, setup_database):
        """Test basic batch insert operation."""
        conn_string = setup_database

        node = AsyncSQLDatabaseNode(
            name="test_node",
            database_type="postgresql",
            connection_string=conn_string,
        )

        # Prepare batch data
        batch_data = [
            {"name": "Item1", "value": 10, "batch_id": "batch_001"},
            {"name": "Item2", "value": 20, "batch_id": "batch_001"},
            {"name": "Item3", "value": 30, "batch_id": "batch_001"},
            {"name": "Item4", "value": 40, "batch_id": "batch_001"},
            {"name": "Item5", "value": 50, "batch_id": "batch_001"},
        ]

        # Execute batch insert
        result = await node.execute_many_async(
            query="INSERT INTO batch_test (name, value, batch_id) VALUES (:name, :value, :batch_id)",
            params_list=batch_data,
        )

        assert "result" in result
        assert result["result"]["affected_rows"] == 5

        # Verify data was inserted
        check_result = await node.execute_async(
            query="SELECT COUNT(*) as count, SUM(value) as total FROM batch_test WHERE batch_id = :batch_id",
            params={"batch_id": "batch_001"},
        )

        assert check_result["result"]["data"][0]["count"] == 5
        assert check_result["result"]["data"][0]["total"] == 150

        await node.cleanup()

    @pytest.mark.asyncio
    async def test_batch_update_operations(self, setup_database):
        """Test batch update operations."""
        conn_string = setup_database

        node = AsyncSQLDatabaseNode(
            name="test_node",
            database_type="postgresql",
            connection_string=conn_string,
        )

        # Insert initial data
        initial_data = [
            {"name": f"Product{i}", "value": i * 10, "batch_id": "update_test"}
            for i in range(1, 6)
        ]

        await node.execute_many_async(
            query="INSERT INTO batch_test (name, value, batch_id) VALUES (:name, :value, :batch_id)",
            params_list=initial_data,
        )

        # Get inserted IDs
        rows = await node.execute_async(
            query="SELECT id, name FROM batch_test WHERE batch_id = :batch_id ORDER BY value",
            params={"batch_id": "update_test"},
        )

        # Prepare update data
        update_data = [
            {"id": row["id"], "new_value": (i + 1) * 100}
            for i, row in enumerate(rows["result"]["data"])
        ]

        # Execute batch update
        await node.execute_many_async(
            query="UPDATE batch_test SET value = :new_value WHERE id = :id",
            params_list=update_data,
        )

        # Verify updates
        verify_result = await node.execute_async(
            query="SELECT id, value FROM batch_test WHERE batch_id = :batch_id ORDER BY id",
            params={"batch_id": "update_test"},
        )

        # Check that values were updated correctly
        for i, row in enumerate(verify_result["result"]["data"]):
            assert row["value"] == (i + 1) * 100

        await node.cleanup()

    @pytest.mark.asyncio
    async def test_batch_with_auto_transaction(self, setup_database):
        """Test batch operations with auto transaction mode."""
        conn_string = setup_database

        node = AsyncSQLDatabaseNode(
            name="test_node",
            database_type="postgresql",
            connection_string=conn_string,
            transaction_mode="auto",
        )

        # Prepare data with one that will cause error
        batch_data = [
            {"name": "Valid1", "value": 100, "batch_id": "tx_test"},
            {"name": "Valid2", "value": 200, "batch_id": "tx_test"},
            {
                "name": "Valid3",
                "value": None,
                "batch_id": "tx_test",
            },  # This might cause error
        ]

        # First, let's insert valid data
        valid_data = batch_data[:2]
        result = await node.execute_many_async(
            query="INSERT INTO batch_test (name, value, batch_id) VALUES (:name, :value, :batch_id)",
            params_list=valid_data,
        )

        assert "result" in result

        # Verify transaction was committed
        check_result = await node.execute_async(
            query="SELECT COUNT(*) as count FROM batch_test WHERE batch_id = :batch_id",
            params={"batch_id": "tx_test"},
        )

        assert check_result["result"]["data"][0]["count"] == 2

        await node.cleanup()

    @pytest.mark.asyncio
    async def test_batch_with_manual_transaction(self, setup_database):
        """Test batch operations within manual transaction control."""
        conn_string = setup_database

        node = AsyncSQLDatabaseNode(
            name="test_node",
            database_type="postgresql",
            connection_string=conn_string,
            transaction_mode="manual",
        )

        # Begin transaction
        await node.begin_transaction()

        try:
            # First batch insert
            batch1 = [
                {"name": f"Batch1_Item{i}", "value": i * 10, "batch_id": "manual_tx"}
                for i in range(1, 4)
            ]

            await node.execute_many_async(
                query="INSERT INTO batch_test (name, value, batch_id) VALUES (:name, :value, :batch_id)",
                params_list=batch1,
            )

            # Second batch insert
            batch2 = [
                {"name": f"Batch2_Item{i}", "value": i * 20, "batch_id": "manual_tx"}
                for i in range(1, 4)
            ]

            await node.execute_many_async(
                query="INSERT INTO batch_test (name, value, batch_id) VALUES (:name, :value, :batch_id)",
                params_list=batch2,
            )

            # Commit transaction
            await node.commit()

            # Verify all data was committed
            result = await node.execute_async(
                query="SELECT COUNT(*) as count FROM batch_test WHERE batch_id = :batch_id",
                params={"batch_id": "manual_tx"},
            )

            assert result["result"]["data"][0]["count"] == 6

        except Exception:
            await node.rollback()
            raise
        finally:
            await node.cleanup()

    @pytest.mark.asyncio
    async def test_batch_rollback_on_error(self, setup_database):
        """Test batch operations rollback on error."""
        conn_string = setup_database

        node = AsyncSQLDatabaseNode(
            name="test_node",
            database_type="postgresql",
            connection_string=conn_string,
            transaction_mode="manual",
            allow_admin=True,  # Allow admin for constraint creation
        )

        # Begin transaction
        await node.begin_transaction()

        try:
            # Insert some valid data
            valid_batch = [
                {"name": "WillRollback1", "value": 100, "batch_id": "rollback_test"},
                {"name": "WillRollback2", "value": 200, "batch_id": "rollback_test"},
            ]

            await node.execute_many_async(
                query="INSERT INTO batch_test (name, value, batch_id) VALUES (:name, :value, :batch_id)",
                params_list=valid_batch,
            )

            # Now try to insert data that violates constraint
            # First, let's create a unique constraint
            await node.execute_async(
                query="ALTER TABLE batch_test ADD CONSTRAINT unique_name_batch UNIQUE (name, batch_id)"
            )

            # This should fail due to duplicate
            duplicate_batch = [
                {"name": "WillRollback1", "value": 300, "batch_id": "rollback_test"},
            ]

            await node.execute_many_async(
                query="INSERT INTO batch_test (name, value, batch_id) VALUES (:name, :value, :batch_id)",
                params_list=duplicate_batch,
            )

            # Should not reach here
            await node.commit()

        except Exception:
            # Rollback on error
            await node.rollback()

        # Verify nothing was inserted
        result = await node.execute_async(
            query="SELECT COUNT(*) as count FROM batch_test WHERE batch_id = :batch_id",
            params={"batch_id": "rollback_test"},
        )

        assert result["result"]["data"][0]["count"] == 0

        # Clean up constraint
        await node.execute_async(
            query="ALTER TABLE batch_test DROP CONSTRAINT IF EXISTS unique_name_batch"
        )

        await node.cleanup()

    @pytest.mark.asyncio
    async def test_batch_with_different_param_styles(self, setup_database):
        """Test batch operations with different parameter styles."""
        conn_string = setup_database

        node = AsyncSQLDatabaseNode(
            name="test_node",
            database_type="postgresql",
            connection_string=conn_string,
        )

        # Test with tuple parameters
        tuple_batch = [
            ("TupleItem1", 10, "tuple_batch"),
            ("TupleItem2", 20, "tuple_batch"),
            ("TupleItem3", 30, "tuple_batch"),
        ]

        await node.execute_many_async(
            query="INSERT INTO batch_test (name, value, batch_id) VALUES ($1, $2, $3)",
            params_list=tuple_batch,
        )

        # Verify tuple insert
        tuple_result = await node.execute_async(
            query="SELECT COUNT(*) as count FROM batch_test WHERE batch_id = :batch_id",
            params={"batch_id": "tuple_batch"},
        )

        assert tuple_result["result"]["data"][0]["count"] == 3

        await node.cleanup()

    @pytest.mark.asyncio
    async def test_large_batch_performance(self, setup_database):
        """Test performance with large batch operations."""
        conn_string = setup_database

        node = AsyncSQLDatabaseNode(
            name="test_node",
            database_type="postgresql",
            connection_string=conn_string,
        )

        # Create large batch
        large_batch = [
            {"name": f"LargeItem_{i:05d}", "value": i % 1000, "batch_id": "large_batch"}
            for i in range(1000)
        ]

        # Time the batch insert
        import time

        start_time = time.time()

        result = await node.execute_many_async(
            query="INSERT INTO batch_test (name, value, batch_id) VALUES (:name, :value, :batch_id)",
            params_list=large_batch,
        )

        elapsed = time.time() - start_time

        assert "result" in result
        assert result["result"]["affected_rows"] == 1000

        # Verify all data was inserted
        count_result = await node.execute_async(
            query="SELECT COUNT(*) as count FROM batch_test WHERE batch_id = :batch_id",
            params={"batch_id": "large_batch"},
        )

        assert count_result["result"]["data"][0]["count"] == 1000

        # Performance assertion - should complete in reasonable time
        assert elapsed < 5.0  # 1000 rows should insert in less than 5 seconds

        await node.cleanup()

    @pytest.mark.asyncio
    async def test_concurrent_batch_operations(self, setup_database):
        """Test concurrent batch operations."""
        conn_string = setup_database

        # Create multiple nodes for concurrent operations
        nodes = []
        for i in range(3):
            node = AsyncSQLDatabaseNode(
                name=f"concurrent_node_{i}",
                database_type="postgresql",
                connection_string=conn_string,
            )
            nodes.append(node)

        async def batch_insert(node, batch_num):
            """Insert a batch of data."""
            batch_data = [
                {
                    "name": f"Concurrent_B{batch_num}_I{i}",
                    "value": batch_num * 100 + i,
                    "batch_id": f"concurrent_{batch_num}",
                }
                for i in range(50)
            ]

            return await node.execute_many_async(
                query="INSERT INTO batch_test (name, value, batch_id) VALUES (:name, :value, :batch_id)",
                params_list=batch_data,
            )

        # Run concurrent batch operations
        tasks = []
        for i, node in enumerate(nodes):
            tasks.append(batch_insert(node, i))

        results = await asyncio.gather(*tasks)

        # All should succeed
        assert all("result" in r for r in results)
        assert all(r["result"]["affected_rows"] == 50 for r in results)

        # Verify total count
        verify_node = nodes[0]
        total_result = await verify_node.execute_async(
            query="SELECT COUNT(*) as count FROM batch_test WHERE batch_id LIKE 'concurrent_%'"
        )

        assert total_result["result"]["data"][0]["count"] == 150

        # Cleanup
        for node in nodes:
            await node.cleanup()

    @pytest.mark.asyncio
    async def test_batch_operations_with_real_database(self, setup_database):
        """Test batch operations with REAL database operations - NO MOCKING."""
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

        # Execute batch operations using REAL database
        batch_data = [
            {"name": f"BatchItem{i}", "value": i * 10, "batch_id": "real_batch"}
            for i in range(5)
        ]

        result = await node.execute_many_async(
            query="INSERT INTO batch_test (name, value, batch_id) VALUES (:name, :value, :batch_id)",
            params_list=batch_data,
        )

        assert "result" in result
        assert result["result"]["batch_size"] == 5
        assert result["result"]["affected_rows"] == 5

        # Verify data was inserted with REAL query
        check_result = await node.execute_async(
            query="SELECT COUNT(*) as count FROM batch_test WHERE batch_id = :batch_id",
            params={"batch_id": "real_batch"},
        )

        assert check_result["result"]["data"][0]["count"] == 5

        # Verify individual records
        records = await node.execute_async(
            query="SELECT * FROM batch_test WHERE batch_id = :batch_id ORDER BY value",
            params={"batch_id": "real_batch"},
        )

        assert len(records["result"]["data"]) == 5
        for i, record in enumerate(records["result"]["data"]):
            assert record["name"] == f"BatchItem{i}"
            assert record["value"] == i * 10

        await node.cleanup()

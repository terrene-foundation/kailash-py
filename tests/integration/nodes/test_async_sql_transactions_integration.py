"""Integration tests for AsyncSQLDatabaseNode transaction functionality with real PostgreSQL."""

import asyncio
from datetime import datetime

import pytest
import pytest_asyncio

from kailash.nodes.data.async_sql import AsyncSQLDatabaseNode
from kailash.sdk_exceptions import NodeExecutionError
from tests.utils.docker_config import get_postgres_connection_string

# Mark all tests as requiring postgres and as integration tests
pytestmark = [pytest.mark.integration, pytest.mark.requires_postgres]


class TestAsyncSQLTransactionsIntegration:
    """Integration tests for transaction functionality with real PostgreSQL database."""

    @pytest_asyncio.fixture
    async def setup_database(self):
        """Set up test database with sample table."""
        conn_string = get_postgres_connection_string()

        # Create test table
        setup_node = AsyncSQLDatabaseNode(
            name="setup",
            database_type="postgresql",
            connection_string=conn_string,
            allow_admin=True,
        )

        # Drop and recreate table
        await setup_node.execute_async(query="DROP TABLE IF EXISTS transaction_test")
        await setup_node.execute_async(
            query="""
            CREATE TABLE transaction_test (
                id SERIAL PRIMARY KEY,
                name VARCHAR(100),
                value INTEGER,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """
        )

        yield conn_string

        # Cleanup
        await setup_node.execute_async(query="DROP TABLE IF EXISTS transaction_test")
        await setup_node.cleanup()

    @pytest.mark.asyncio
    async def test_auto_transaction_commit_on_success(self, setup_database):
        """Test auto transaction mode commits on successful operations."""
        conn_string = setup_database

        node = AsyncSQLDatabaseNode(
            name="test",
            database_type="postgresql",
            connection_string=conn_string,
            transaction_mode="auto",
        )

        try:
            # Insert data in auto transaction mode
            await node.execute_async(
                query="INSERT INTO transaction_test (name, value) VALUES (:name, :value)",
                params={"name": "test_commit", "value": 100},
            )

            # Verify data was committed by querying from a new connection
            verify_node = AsyncSQLDatabaseNode(
                name="verify",
                database_type="postgresql",
                connection_string=conn_string,
            )

            result = await verify_node.execute_async(
                query="SELECT * FROM transaction_test WHERE name = :name",
                params={"name": "test_commit"},
            )

            assert len(result["result"]["data"]) == 1
            assert result["result"]["data"][0]["name"] == "test_commit"
            assert result["result"]["data"][0]["value"] == 100

            await verify_node.cleanup()

        finally:
            await node.cleanup()

    @pytest.mark.asyncio
    async def test_auto_transaction_rollback_on_error(self, setup_database):
        """Test auto transaction mode rolls back on errors."""
        conn_string = setup_database

        node = AsyncSQLDatabaseNode(
            name="test",
            database_type="postgresql",
            connection_string=conn_string,
            transaction_mode="auto",
        )

        try:
            # First insert some data successfully
            await node.execute_async(
                query="INSERT INTO transaction_test (name, value) VALUES (:name, :value)",
                params={"name": "before_error", "value": 1},
            )

            # Try to execute invalid SQL (should rollback)
            with pytest.raises(NodeExecutionError):
                await node.execute_async(query="INVALID SQL STATEMENT")

            # Verify first insert is still there (different transaction)
            result = await node.execute_async(
                query="SELECT COUNT(*) as count FROM transaction_test WHERE name = :name",
                params={"name": "before_error"},
            )

            assert result["result"]["data"][0]["count"] == 1

        finally:
            await node.cleanup()

    @pytest.mark.asyncio
    async def test_manual_transaction_commit(self, setup_database):
        """Test manual transaction mode with explicit commit."""
        conn_string = setup_database

        node = AsyncSQLDatabaseNode(
            name="test",
            database_type="postgresql",
            connection_string=conn_string,
            transaction_mode="manual",
        )

        try:
            # Begin manual transaction
            await node.begin_transaction()

            # Insert multiple records in same transaction
            await node.execute_async(
                query="INSERT INTO transaction_test (name, value) VALUES (:name, :value)",
                params={"name": "manual_1", "value": 10},
            )

            await node.execute_async(
                query="INSERT INTO transaction_test (name, value) VALUES (:name, :value)",
                params={"name": "manual_2", "value": 20},
            )

            # At this point, data shouldn't be visible from other connections
            verify_node = AsyncSQLDatabaseNode(
                name="verify",
                database_type="postgresql",
                connection_string=conn_string,
            )

            result = await verify_node.execute_async(
                query="SELECT COUNT(*) as count FROM transaction_test WHERE name LIKE :pattern",
                params={"pattern": "manual_%"},
            )

            # Should see 0 records before commit
            assert result["result"]["data"][0]["count"] == 0

            # Commit the transaction
            await node.commit()

            # Now data should be visible
            result = await verify_node.execute_async(
                query="SELECT COUNT(*) as count FROM transaction_test WHERE name LIKE :pattern",
                params={"pattern": "manual_%"},
            )

            assert result["result"]["data"][0]["count"] == 2

            await verify_node.cleanup()

        finally:
            await node.cleanup()

    @pytest.mark.asyncio
    async def test_manual_transaction_rollback(self, setup_database):
        """Test manual transaction mode with explicit rollback."""
        conn_string = setup_database

        node = AsyncSQLDatabaseNode(
            name="test",
            database_type="postgresql",
            connection_string=conn_string,
            transaction_mode="manual",
        )

        try:
            # Begin manual transaction
            await node.begin_transaction()

            # Insert data
            await node.execute_async(
                query="INSERT INTO transaction_test (name, value) VALUES (:name, :value)",
                params={"name": "rollback_test", "value": 999},
            )

            # Rollback instead of commit
            await node.rollback()

            # Verify data was not persisted
            result = await node.execute_async(
                query="SELECT COUNT(*) as count FROM transaction_test WHERE name = :name",
                params={"name": "rollback_test"},
            )

            assert result["result"]["data"][0]["count"] == 0

        finally:
            await node.cleanup()

    @pytest.mark.asyncio
    async def test_none_transaction_mode(self, setup_database):
        """Test none transaction mode executes without explicit transactions."""
        conn_string = setup_database

        node = AsyncSQLDatabaseNode(
            name="test",
            database_type="postgresql",
            connection_string=conn_string,
            transaction_mode="none",
        )

        try:
            # Insert data (should auto-commit immediately)
            await node.execute_async(
                query="INSERT INTO transaction_test (name, value) VALUES (:name, :value)",
                params={"name": "none_mode", "value": 50},
            )

            # Should be immediately visible
            result = await node.execute_async(
                query="SELECT * FROM transaction_test WHERE name = :name",
                params={"name": "none_mode"},
            )

            assert len(result["result"]["data"]) == 1
            assert result["result"]["data"][0]["value"] == 50

        finally:
            await node.cleanup()

    @pytest.mark.asyncio
    async def test_batch_operations_with_auto_transaction(self, setup_database):
        """Test execute_many with auto transaction mode."""
        conn_string = setup_database

        node = AsyncSQLDatabaseNode(
            name="test",
            database_type="postgresql",
            connection_string=conn_string,
            transaction_mode="auto",
        )

        try:
            # Prepare batch data
            params_list = [{"name": f"batch_{i}", "value": i * 10} for i in range(5)]

            # Execute batch operation
            result = await node.execute_many_async(
                query="INSERT INTO transaction_test (name, value) VALUES (:name, :value)",
                params_list=params_list,
            )

            assert result["result"]["affected_rows"] == 5

            # Verify all records were inserted
            verify_result = await node.execute_async(
                query="SELECT COUNT(*) as count FROM transaction_test WHERE name LIKE :pattern",
                params={"pattern": "batch_%"},
            )

            assert verify_result["result"]["data"][0]["count"] == 5

        finally:
            await node.cleanup()

    @pytest.mark.asyncio
    async def test_batch_operations_with_manual_transaction(self, setup_database):
        """Test execute_many within manual transaction."""
        conn_string = setup_database

        node = AsyncSQLDatabaseNode(
            name="test",
            database_type="postgresql",
            connection_string=conn_string,
            transaction_mode="manual",
        )

        try:
            # Begin manual transaction
            await node.begin_transaction()

            # Execute batch operation
            params_list = [{"name": f"manual_batch_{i}", "value": i} for i in range(3)]

            result = await node.execute_many_async(
                query="INSERT INTO transaction_test (name, value) VALUES (:name, :value)",
                params_list=params_list,
            )

            assert result["result"]["affected_rows"] == 3

            # Execute another single operation in same transaction
            await node.execute_async(
                query="INSERT INTO transaction_test (name, value) VALUES (:name, :value)",
                params={"name": "manual_single", "value": 100},
            )

            # Commit all operations
            await node.commit()

            # Verify all data is present
            verify_result = await node.execute_async(
                query="SELECT COUNT(*) as count FROM transaction_test WHERE name LIKE :pattern",
                params={"pattern": "manual_%"},
            )

            assert (
                verify_result["result"]["data"][0]["count"] == 4
            )  # 3 batch + 1 single

        finally:
            await node.cleanup()

    @pytest.mark.asyncio
    async def test_transaction_isolation_levels(self, setup_database):
        """Test transaction isolation with concurrent operations."""
        conn_string = setup_database

        # Create two nodes representing different connections
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

        try:
            # Begin transactions on both nodes
            await node1.begin_transaction()
            await node2.begin_transaction()

            # Insert data in first transaction
            await node1.execute_async(
                query="INSERT INTO transaction_test (name, value) VALUES (:name, :value)",
                params={"name": "isolation_test", "value": 123},
            )

            # Second transaction shouldn't see uncommitted data
            result2 = await node2.execute_async(
                query="SELECT COUNT(*) as count FROM transaction_test WHERE name = :name",
                params={"name": "isolation_test"},
            )

            assert result2["result"]["data"][0]["count"] == 0

            # Commit first transaction
            await node1.commit()

            # Now second transaction should see the data (after commit)
            result2_after = await node2.execute_async(
                query="SELECT COUNT(*) as count FROM transaction_test WHERE name = :name",
                params={"name": "isolation_test"},
            )

            assert result2_after["result"]["data"][0]["count"] == 1

            # Rollback second transaction (no changes to rollback)
            await node2.rollback()

        finally:
            await node1.cleanup()
            await node2.cleanup()

    @pytest.mark.asyncio
    async def test_connection_recovery_with_transactions(self, setup_database):
        """Test transaction behavior during connection recovery."""
        conn_string = setup_database

        node = AsyncSQLDatabaseNode(
            name="test",
            database_type="postgresql",
            connection_string=conn_string,
            transaction_mode="auto",
            max_retries=2,
        )

        try:
            # Insert initial data
            await node.execute_async(
                query="INSERT INTO transaction_test (name, value) VALUES (:name, :value)",
                params={"name": "recovery_test", "value": 1},
            )

            # Force adapter reset to simulate connection loss
            node._adapter = None
            node._connected = False

            # Next operation should recover and work
            await node.execute_async(
                query="INSERT INTO transaction_test (name, value) VALUES (:name, :value)",
                params={"name": "recovery_test_2", "value": 2},
            )

            # Verify both records exist
            result = await node.execute_async(
                query="SELECT COUNT(*) as count FROM transaction_test WHERE name LIKE :pattern",
                params={"pattern": "recovery_test%"},
            )

            assert result["result"]["data"][0]["count"] == 2

        finally:
            await node.cleanup()

    @pytest.mark.asyncio
    async def test_complex_transaction_scenario(self, setup_database):
        """Test complex scenario with mixed transaction operations."""
        conn_string = setup_database

        node = AsyncSQLDatabaseNode(
            name="test",
            database_type="postgresql",
            connection_string=conn_string,
            transaction_mode="manual",
        )

        try:
            # Begin transaction
            await node.begin_transaction()

            # Insert base record
            await node.execute_async(
                query="INSERT INTO transaction_test (name, value) VALUES (:name, :value)",
                params={"name": "complex_base", "value": 1},
            )

            # Update the record
            await node.execute_async(
                query="UPDATE transaction_test SET value = :new_value WHERE name = :name",
                params={"name": "complex_base", "new_value": 10},
            )

            # Insert related records
            batch_params = [
                {"name": "complex_related_1", "value": 100},
                {"name": "complex_related_2", "value": 200},
            ]

            await node.execute_many_async(
                query="INSERT INTO transaction_test (name, value) VALUES (:name, :value)",
                params_list=batch_params,
            )

            # Query within transaction to verify state
            result = await node.execute_async(
                query="SELECT SUM(value) as total FROM transaction_test WHERE name LIKE :pattern",
                params={"pattern": "complex_%"},
            )

            total = result["result"]["data"][0]["total"]
            assert total == 310  # 10 + 100 + 200

            # Commit all operations
            await node.commit()

            # Verify final state
            final_result = await node.execute_async(
                query="SELECT name, value FROM transaction_test WHERE name LIKE :pattern ORDER BY name",
                params={"pattern": "complex_%"},
            )

            data = final_result["result"]["data"]
            assert len(data) == 3
            assert data[0]["name"] == "complex_base" and data[0]["value"] == 10
            assert data[1]["name"] == "complex_related_1" and data[1]["value"] == 100
            assert data[2]["name"] == "complex_related_2" and data[2]["value"] == 200

        finally:
            await node.cleanup()

    @pytest.mark.asyncio
    async def test_transaction_timeout_behavior(self, setup_database):
        """Test transaction behavior with timeouts."""
        conn_string = setup_database

        node = AsyncSQLDatabaseNode(
            name="test",
            database_type="postgresql",
            connection_string=conn_string,
            transaction_mode="manual",
            timeout=1.0,  # Very short timeout for testing
        )

        try:
            await node.begin_transaction()

            # Quick operation should succeed
            await node.execute_async(
                query="INSERT INTO transaction_test (name, value) VALUES (:name, :value)",
                params={"name": "timeout_test", "value": 1},
            )

            await node.commit()

            # Verify operation completed
            result = await node.execute_async(
                query="SELECT COUNT(*) as count FROM transaction_test WHERE name = :name",
                params={"name": "timeout_test"},
            )

            assert result["result"]["data"][0]["count"] == 1

        finally:
            await node.cleanup()


class TestAsyncSQLTransactionErrorHandling:
    """Test error handling scenarios in transaction operations."""

    @pytest_asyncio.fixture
    async def error_setup_database(self):
        """Set up test database for error scenarios."""
        conn_string = get_postgres_connection_string()

        setup_node = AsyncSQLDatabaseNode(
            name="setup",
            database_type="postgresql",
            connection_string=conn_string,
            allow_admin=True,
        )

        # Create table with constraints for error testing
        await setup_node.execute_async(query="DROP TABLE IF EXISTS error_test")
        await setup_node.execute_async(
            query="""
            CREATE TABLE error_test (
                id INTEGER PRIMARY KEY,
                unique_name VARCHAR(50) UNIQUE NOT NULL,
                check_value INTEGER CHECK (check_value > 0)
            )
        """
        )

        yield conn_string

        # Cleanup
        await setup_node.execute_async(query="DROP TABLE IF EXISTS error_test")
        await setup_node.cleanup()

    @pytest.mark.asyncio
    async def test_constraint_violation_rollback(self, error_setup_database):
        """Test rollback on constraint violations."""
        conn_string = error_setup_database

        node = AsyncSQLDatabaseNode(
            name="test",
            database_type="postgresql",
            connection_string=conn_string,
            transaction_mode="auto",
        )

        try:
            # Insert valid record
            await node.execute_async(
                query="INSERT INTO error_test (id, unique_name, check_value) VALUES (:id, :name, :value)",
                params={"id": 1, "name": "valid", "value": 10},
            )

            # Try to insert duplicate (should fail and rollback)
            with pytest.raises(NodeExecutionError):
                await node.execute_async(
                    query="INSERT INTO error_test (id, unique_name, check_value) VALUES (:id, :name, :value)",
                    params={"id": 1, "name": "duplicate", "value": 20},  # Duplicate ID
                )

            # Original record should still exist
            result = await node.execute_async(
                query="SELECT COUNT(*) as count FROM error_test"
            )

            assert result["result"]["data"][0]["count"] == 1

        finally:
            await node.cleanup()

    @pytest.mark.asyncio
    async def test_manual_transaction_error_cleanup(self, error_setup_database):
        """Test proper cleanup when manual transaction encounters errors."""
        conn_string = error_setup_database

        node = AsyncSQLDatabaseNode(
            name="test",
            database_type="postgresql",
            connection_string=conn_string,
            transaction_mode="manual",
        )

        try:
            await node.begin_transaction()

            # Insert valid record
            await node.execute_async(
                query="INSERT INTO error_test (id, unique_name, check_value) VALUES (:id, :name, :value)",
                params={"id": 1, "name": "valid", "value": 10},
            )

            # Execute invalid query (violates check constraint)
            with pytest.raises(NodeExecutionError):
                await node.execute_async(
                    query="INSERT INTO error_test (id, unique_name, check_value) VALUES (:id, :name, :value)",
                    params={
                        "id": 2,
                        "name": "invalid",
                        "value": -5,
                    },  # Violates check constraint
                )

            # Transaction should still be active for manual rollback
            assert node._active_transaction is not None

            # Manually rollback
            await node.rollback()

            # No records should exist (all rolled back)
            result = await node.execute_async(
                query="SELECT COUNT(*) as count FROM error_test"
            )

            assert result["result"]["data"][0]["count"] == 0

        finally:
            await node.cleanup()

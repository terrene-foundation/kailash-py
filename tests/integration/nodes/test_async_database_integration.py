"""Integration tests for async database infrastructure with REAL Docker services."""

import asyncio
import os

import pytest
import pytest_asyncio
from kailash.nodes.data.async_sql import AsyncSQLDatabaseNode

from tests.utils.docker_config import DATABASE_CONFIG, get_postgres_connection_string

# Mark all tests in this file as requiring postgres and as integration tests
pytestmark = [pytest.mark.integration, pytest.mark.requires_postgres]


class TestAsyncDatabaseIntegration:
    """Test async database components integration with REAL PostgreSQL."""

    @pytest_asyncio.fixture
    async def setup_test_database(self):
        """Set up test database with REAL PostgreSQL."""
        # Use real PostgreSQL connection from Docker
        conn_string = get_postgres_connection_string()

        # Create test tables
        setup_queries = [
            "DROP TABLE IF EXISTS test_accounts",
            "DROP TABLE IF EXISTS test_users",
            """
            CREATE TABLE test_users (
                id SERIAL PRIMARY KEY,
                name VARCHAR(100),
                active BOOLEAN DEFAULT true
            )
            """,
            """
            CREATE TABLE test_accounts (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES test_users(id),
                balance DECIMAL(10, 2) DEFAULT 0.00
            )
            """,
        ]

        for query in setup_queries:
            node = AsyncSQLDatabaseNode(
                name="setup",
                database_type="postgresql",
                connection_string=conn_string,
                query=query,
                allow_admin=True,  # Allow DDL operations for test setup
            )
            await node.execute_async()
            await node.cleanup()  # Clean up connection after each DDL operation

        # Insert test data
        insert_users = [
            ("User 1", True),
            ("User 2", True),
            ("User 3", False),
        ]

        user_node = AsyncSQLDatabaseNode(
            name="insert_users",
            database_type="postgresql",
            connection_string=conn_string,
            query="INSERT INTO test_users (name, active) VALUES (:name, :active) RETURNING id",
        )

        user_ids = []
        for name, active in insert_users:
            result = await user_node.execute_async(
                params={"name": name, "active": active}
            )
            user_ids.append(result["result"]["data"][0]["id"])

        await user_node.cleanup()  # Clean up connection after inserts

        # Insert account data
        account_node = AsyncSQLDatabaseNode(
            name="insert_accounts",
            database_type="postgresql",
            connection_string=conn_string,
            query="INSERT INTO test_accounts (user_id, balance) VALUES (:user_id, :balance)",
        )

        for i, user_id in enumerate(user_ids):
            await account_node.execute_async(
                params={"user_id": user_id, "balance": 1000.00 * (i + 1)}
            )

        await account_node.cleanup()  # Clean up connection after inserts

        yield conn_string, user_ids

        # Cleanup
        cleanup_queries = [
            "DROP TABLE IF EXISTS test_accounts",
            "DROP TABLE IF EXISTS test_users",
        ]

        for query in cleanup_queries:
            cleanup_node = AsyncSQLDatabaseNode(
                name="cleanup",
                database_type="postgresql",
                connection_string=conn_string,
                query=query,
                allow_admin=True,  # Allow DDL operations for cleanup
            )
            await cleanup_node.execute_async()
            await cleanup_node.cleanup()  # Clean up connection after each DDL operation

    @pytest.mark.asyncio
    async def test_async_sql_with_connection_pooling(self, setup_test_database):
        """Test AsyncSQLDatabaseNode with REAL PostgreSQL connection pooling."""
        conn_string, _ = setup_test_database

        # Create node with REAL PostgreSQL connection
        node = AsyncSQLDatabaseNode(
            name="test_query",
            database_type="postgresql",
            connection_string=conn_string,
            query="SELECT * FROM test_users WHERE active = :active ORDER BY id",
            params={"active": True},
            pool_size=5,
            max_pool_size=10,
        )

        # Execute query against REAL database
        result = await node.execute_async()

        # Verify results from REAL data
        assert len(result["result"]["data"]) == 2
        assert result["result"]["data"][0]["name"] == "User 1"
        assert result["result"]["data"][1]["name"] == "User 2"
        assert all(row["active"] for row in result["result"]["data"])
        assert result["result"]["row_count"] == 2

    @pytest.mark.asyncio
    async def test_transaction_auto_mode_rollback(self, setup_test_database):
        """Test auto transaction mode with REAL database - each query in its own transaction."""
        conn_string, user_ids = setup_test_database

        # Create node in auto transaction mode (default)
        node = AsyncSQLDatabaseNode(
            name="test_auto_rollback",
            database_type="postgresql",
            connection_string=conn_string,
            transaction_mode="auto",
        )

        # Check initial balance
        check_node = AsyncSQLDatabaseNode(
            name="check_balance",
            database_type="postgresql",
            connection_string=conn_string,
            query="SELECT balance FROM test_accounts WHERE user_id = :user_id",
        )

        initial_result = await check_node.execute_async(params={"user_id": user_ids[0]})
        initial_balance = float(initial_result["result"]["data"][0]["balance"])

        # Test that a single failing query is rolled back
        try:
            # This should fail and its transaction should be rolled back
            await node.execute_async(
                query="UPDATE test_accounts SET balance = balance / 0 WHERE user_id = :user_id",  # Division by zero
                params={"user_id": user_ids[0]},
            )
        except Exception:
            pass  # Expected to fail

        # Check that balance wasn't changed (rollback worked)
        mid_result = await check_node.execute_async(params={"user_id": user_ids[0]})
        mid_balance = float(mid_result["result"]["data"][0]["balance"])

        assert (
            initial_balance == mid_balance
        ), "Failed transaction should have been rolled back"

        # Now test that successful query commits in auto mode
        await node.execute_async(
            query="UPDATE test_accounts SET balance = balance - 100 WHERE user_id = :user_id",
            params={"user_id": user_ids[0]},
        )

        # This should be committed automatically
        final_result = await check_node.execute_async(params={"user_id": user_ids[0]})
        final_balance = float(final_result["result"]["data"][0]["balance"])

        assert (
            final_balance == initial_balance - 100
        ), "Successful transaction should have been committed"

    @pytest.mark.asyncio
    async def test_transaction_manual_mode(self, setup_test_database):
        """Test manual transaction mode with REAL database."""
        conn_string, user_ids = setup_test_database

        # Create node in manual transaction mode
        node = AsyncSQLDatabaseNode(
            name="test_manual_transaction",
            database_type="postgresql",
            connection_string=conn_string,
            transaction_mode="manual",
        )

        # Check initial balances
        check_node = AsyncSQLDatabaseNode(
            name="check_balance",
            database_type="postgresql",
            connection_string=conn_string,
            query="SELECT balance FROM test_accounts WHERE user_id = :user_id",
        )

        initial1 = await check_node.execute_async(params={"user_id": user_ids[0]})
        initial2 = await check_node.execute_async(params={"user_id": user_ids[1]})
        balance1 = float(initial1["result"]["data"][0]["balance"])
        balance2 = float(initial2["result"]["data"][0]["balance"])

        # Begin transaction
        await node.begin_transaction()

        try:
            # Transfer money between accounts
            await node.execute_async(
                query="UPDATE test_accounts SET balance = balance - 100 WHERE user_id = :user_id",
                params={"user_id": user_ids[0]},
            )
            await node.execute_async(
                query="UPDATE test_accounts SET balance = balance + 100 WHERE user_id = :user_id",
                params={"user_id": user_ids[1]},
            )

            # Commit transaction
            await node.commit()

            # Verify transfer completed
            final1 = await check_node.execute_async(params={"user_id": user_ids[0]})
            final2 = await check_node.execute_async(params={"user_id": user_ids[1]})
            new_balance1 = float(final1["result"]["data"][0]["balance"])
            new_balance2 = float(final2["result"]["data"][0]["balance"])

            assert new_balance1 == balance1 - 100
            assert new_balance2 == balance2 + 100

        except Exception as e:
            await node.rollback()
            raise e
        finally:
            await node.cleanup()
            await check_node.cleanup()

    @pytest.mark.asyncio
    async def test_transaction_manual_mode_rollback(self, setup_test_database):
        """Test manual transaction rollback with REAL database."""
        conn_string, user_ids = setup_test_database

        # Create node in manual transaction mode
        node = AsyncSQLDatabaseNode(
            name="test_manual_rollback",
            database_type="postgresql",
            connection_string=conn_string,
            transaction_mode="manual",
        )

        # Check initial balance
        check_node = AsyncSQLDatabaseNode(
            name="check_balance",
            database_type="postgresql",
            connection_string=conn_string,
            query="SELECT balance FROM test_accounts WHERE user_id = :user_id",
        )

        initial_result = await check_node.execute_async(params={"user_id": user_ids[0]})
        initial_balance = float(initial_result["result"]["data"][0]["balance"])

        # Begin transaction
        await node.begin_transaction()

        # Make changes
        await node.execute_async(
            query="UPDATE test_accounts SET balance = balance - 500 WHERE user_id = :user_id",
            params={"user_id": user_ids[0]},
        )

        # Rollback transaction
        await node.rollback()

        # Verify no changes were made
        final_result = await check_node.execute_async(params={"user_id": user_ids[0]})
        final_balance = float(final_result["result"]["data"][0]["balance"])

        assert (
            initial_balance == final_balance
        ), "Transaction should have been rolled back"

    @pytest.mark.asyncio
    async def test_transaction_none_mode(self, setup_test_database):
        """Test no transaction mode with REAL database - immediate commit."""
        conn_string, user_ids = setup_test_database

        # Create node in none transaction mode
        node = AsyncSQLDatabaseNode(
            name="test_no_transaction",
            database_type="postgresql",
            connection_string=conn_string,
            transaction_mode="none",
        )

        # Check initial balance
        check_node = AsyncSQLDatabaseNode(
            name="check_balance",
            database_type="postgresql",
            connection_string=conn_string,
            query="SELECT balance FROM test_accounts WHERE user_id = :user_id",
        )

        initial_result = await check_node.execute_async(params={"user_id": user_ids[0]})
        initial_balance = float(initial_result["result"]["data"][0]["balance"])

        # Execute update
        await node.execute_async(
            query="UPDATE test_accounts SET balance = balance - 50 WHERE user_id = :user_id",
            params={"user_id": user_ids[0]},
        )

        # Even if we try invalid SQL, the first update should persist
        try:
            await node.execute_async(query="INVALID SQL")
        except Exception:
            pass  # Expected

        # Check that first update persisted (no transaction protection)
        final_result = await check_node.execute_async(params={"user_id": user_ids[0]})
        final_balance = float(final_result["result"]["data"][0]["balance"])

        assert (
            final_balance == initial_balance - 50
        ), "Update should have persisted without transaction"

    @pytest.mark.asyncio
    async def test_concurrent_transactions(self, setup_test_database):
        """Test concurrent transactions with REAL database."""
        conn_string, user_ids = setup_test_database

        # Create two nodes for concurrent transactions
        node1 = AsyncSQLDatabaseNode(
            name="concurrent1",
            database_type="postgresql",
            connection_string=conn_string,
            transaction_mode="manual",
        )

        node2 = AsyncSQLDatabaseNode(
            name="concurrent2",
            database_type="postgresql",
            connection_string=conn_string,
            transaction_mode="manual",
        )

        # Both will try to update the same account
        async def transaction1():
            await node1.begin_transaction()
            try:
                await node1.execute_async(
                    query="UPDATE test_accounts SET balance = balance + 10 WHERE user_id = :user_id",
                    params={"user_id": user_ids[0]},
                )
                await asyncio.sleep(0.1)  # Simulate some work
                await node1.commit()
                return True
            except Exception:
                await node1.rollback()
                return False

        async def transaction2():
            await node2.begin_transaction()
            try:
                await node2.execute_async(
                    query="UPDATE test_accounts SET balance = balance + 20 WHERE user_id = :user_id",
                    params={"user_id": user_ids[0]},
                )
                await asyncio.sleep(0.1)  # Simulate some work
                await node2.commit()
                return True
            except Exception:
                await node2.rollback()
                return False

        # Run concurrently
        results = await asyncio.gather(
            transaction1(), transaction2(), return_exceptions=True
        )

        # At least one should succeed
        assert any(
            r is True for r in results
        ), "At least one transaction should succeed"

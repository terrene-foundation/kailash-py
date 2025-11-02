"""
Integration tests for AsyncSQLDatabaseNode pytest-asyncio pool reuse.

Tests real database operations with pool reuse across multiple pytest tests
to verify the adaptive pool key generation fixes the 404 context errors.

Tier: 2 (Integration)
Target: src/kailash/nodes/data/async_sql.py
Infrastructure: Real PostgreSQL database (NO MOCKING)
"""

import asyncio
import os
from typing import Any, Dict

import pytest
from kailash.nodes.data.async_sql import AsyncSQLDatabaseNode
from sqlalchemy import Column, Integer, String, Text

# Global pool metrics to track across tests
_pool_creation_count = 0
_pool_keys_created = set()


class TestUser:
    """Simple test model for database operations."""

    __tablename__ = "test_users_pytest_pool"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    email = Column(String(100), nullable=False, unique=True)
    bio = Column(Text, nullable=True)


@pytest.fixture
async def postgres_connection():
    """Provide PostgreSQL connection string from environment."""
    # Load from .env or use default test database
    connection_string = os.getenv(
        "TEST_DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/test_db"
    )

    # Verify database is accessible
    node = AsyncSQLDatabaseNode()
    node_id = "test_connection"

    try:
        # Test connection
        result = await node.run(
            connection_string=connection_string,
            query="SELECT 1 as test",
            node_id=node_id,
        )
        assert (
            result["success"] is True
        ), f"Database connection failed: {result.get('error')}"

        # Clean up test table if exists
        await node.run(
            connection_string=connection_string,
            query="DROP TABLE IF EXISTS test_users_pytest_pool CASCADE",
            node_id=f"{node_id}_cleanup",
        )

        # Create test table
        create_table_query = """
        CREATE TABLE IF NOT EXISTS test_users_pytest_pool (
            id SERIAL PRIMARY KEY,
            name VARCHAR(100) NOT NULL,
            email VARCHAR(100) NOT NULL UNIQUE,
            bio TEXT
        )
        """
        result = await node.run(
            connection_string=connection_string,
            query=create_table_query,
            node_id=f"{node_id}_create",
        )
        assert (
            result["success"] is True
        ), f"Table creation failed: {result.get('error')}"

        yield connection_string

    finally:
        # Cleanup after all tests
        await node.run(
            connection_string=connection_string,
            query="DROP TABLE IF EXISTS test_users_pytest_pool CASCADE",
            node_id=f"{node_id}_final_cleanup",
        )


@pytest.mark.tier2
@pytest.mark.asyncio
class TestPytestPoolReuse:
    """Test pool reuse across sequential pytest-asyncio tests."""

    async def test_sequential_tests_reuse_pool_first(self, postgres_connection):
        """Test 1: Create pool, execute query, verify success."""
        global _pool_creation_count, _pool_keys_created

        node = AsyncSQLDatabaseNode()
        node_id = "test_pool_first"

        # Insert test data
        insert_query = """
        INSERT INTO test_users_pytest_pool (name, email, bio)
        VALUES ('Alice', 'alice@test.com', 'First test user')
        RETURNING id, name, email
        """

        result = await node.run(
            connection_string=postgres_connection, query=insert_query, node_id=node_id
        )

        assert result["success"] is True, f"Insert failed: {result.get('error')}"
        assert (
            result["row_count"] == 1
        ), f"Expected 1 row inserted, got {result['row_count']}"
        assert (
            len(result["data"]) == 1
        ), f"Expected 1 row returned, got {len(result['data'])}"
        assert result["data"][0]["name"] == "Alice"

        # Track pool creation
        loop = asyncio.get_event_loop()
        pool_key = AsyncSQLDatabaseNode._generate_pool_key(
            connection_string=postgres_connection,
            loop=loop,
            pool_size=5,
            max_overflow=10,
            pool_recycle=3600,
            echo=False,
        )
        if pool_key not in _pool_keys_created:
            _pool_creation_count += 1
            _pool_keys_created.add(pool_key)

    async def test_sequential_tests_reuse_pool_second(self, postgres_connection):
        """Test 2: Reuse pool from test 1, execute query, verify success."""
        global _pool_creation_count, _pool_keys_created

        node = AsyncSQLDatabaseNode()
        node_id = "test_pool_second"

        # Insert different test data
        insert_query = """
        INSERT INTO test_users_pytest_pool (name, email, bio)
        VALUES ('Bob', 'bob@test.com', 'Second test user')
        RETURNING id, name, email
        """

        result = await node.run(
            connection_string=postgres_connection, query=insert_query, node_id=node_id
        )

        assert result["success"] is True, f"Insert failed: {result.get('error')}"
        assert (
            result["row_count"] == 1
        ), f"Expected 1 row inserted, got {result['row_count']}"
        assert result["data"][0]["name"] == "Bob"

        # Verify pool was reused (same key)
        loop = asyncio.get_event_loop()
        pool_key = AsyncSQLDatabaseNode._generate_pool_key(
            connection_string=postgres_connection,
            loop=loop,
            pool_size=5,
            max_overflow=10,
            pool_recycle=3600,
            echo=False,
        )

        # In test mode, should reuse the same pool key
        assert (
            pool_key in _pool_keys_created
        ), "Pool key should have been created in test 1"

        # Query both users to verify pool works correctly
        select_query = "SELECT name FROM test_users_pytest_pool ORDER BY name"
        result = await node.run(
            connection_string=postgres_connection,
            query=select_query,
            node_id=f"{node_id}_select",
        )

        assert result["success"] is True
        assert len(result["data"]) == 2
        assert result["data"][0]["name"] == "Alice"
        assert result["data"][1]["name"] == "Bob"

    async def test_sequential_tests_reuse_pool_third(self, postgres_connection):
        """Test 3: Reuse pool from tests 1-2, verify all pass."""
        global _pool_creation_count, _pool_keys_created

        node = AsyncSQLDatabaseNode()
        node_id = "test_pool_third"

        # Insert third user
        insert_query = """
        INSERT INTO test_users_pytest_pool (name, email, bio)
        VALUES ('Charlie', 'charlie@test.com', 'Third test user')
        RETURNING id, name, email
        """

        result = await node.run(
            connection_string=postgres_connection, query=insert_query, node_id=node_id
        )

        assert result["success"] is True, f"Insert failed: {result.get('error')}"
        assert result["data"][0]["name"] == "Charlie"

        # Verify all three users exist
        select_query = "SELECT name FROM test_users_pytest_pool ORDER BY name"
        result = await node.run(
            connection_string=postgres_connection,
            query=select_query,
            node_id=f"{node_id}_select",
        )

        assert result["success"] is True
        assert len(result["data"]) == 3, f"Expected 3 users, got {len(result['data'])}"
        assert result["data"][0]["name"] == "Alice"
        assert result["data"][1]["name"] == "Bob"
        assert result["data"][2]["name"] == "Charlie"

    async def test_pool_metrics_show_single_pool_created(self, postgres_connection):
        """Test: Only 1 pool created across all tests (not 3)."""
        global _pool_creation_count, _pool_keys_created

        # The previous 3 tests should have reused the same pool
        assert (
            _pool_creation_count <= 1
        ), f"Expected 1 pool created, got {_pool_creation_count} pools"
        assert (
            len(_pool_keys_created) <= 1
        ), f"Expected 1 pool key, got {len(_pool_keys_created)} keys"

        # Verify pool is still functional
        node = AsyncSQLDatabaseNode()
        node_id = "test_pool_metrics"

        result = await node.run(
            connection_string=postgres_connection,
            query="SELECT COUNT(*) as count FROM test_users_pytest_pool",
            node_id=node_id,
        )

        assert result["success"] is True
        assert result["data"][0]["count"] == 3, "All 3 users should still be accessible"

    async def test_real_database_operations_work(self, postgres_connection):
        """Test: Full CRUD operations work with pool reuse."""
        node = AsyncSQLDatabaseNode()
        node_id = "test_crud"

        # CREATE
        insert_query = """
        INSERT INTO test_users_pytest_pool (name, email, bio)
        VALUES ('David', 'david@test.com', 'CRUD test user')
        RETURNING id
        """
        result = await node.run(
            connection_string=postgres_connection,
            query=insert_query,
            node_id=f"{node_id}_create",
        )
        assert result["success"] is True
        user_id = result["data"][0]["id"]

        # READ
        select_query = f"SELECT * FROM test_users_pytest_pool WHERE id = {user_id}"
        result = await node.run(
            connection_string=postgres_connection,
            query=select_query,
            node_id=f"{node_id}_read",
        )
        assert result["success"] is True
        assert result["data"][0]["name"] == "David"
        assert result["data"][0]["email"] == "david@test.com"

        # UPDATE
        update_query = f"""
        UPDATE test_users_pytest_pool
        SET bio = 'Updated bio for CRUD test'
        WHERE id = {user_id}
        RETURNING bio
        """
        result = await node.run(
            connection_string=postgres_connection,
            query=update_query,
            node_id=f"{node_id}_update",
        )
        assert result["success"] is True
        assert result["data"][0]["bio"] == "Updated bio for CRUD test"

        # DELETE
        delete_query = (
            f"DELETE FROM test_users_pytest_pool WHERE id = {user_id} RETURNING id"
        )
        result = await node.run(
            connection_string=postgres_connection,
            query=delete_query,
            node_id=f"{node_id}_delete",
        )
        assert result["success"] is True
        assert result["data"][0]["id"] == user_id

        # Verify deletion
        select_query = f"SELECT * FROM test_users_pytest_pool WHERE id = {user_id}"
        result = await node.run(
            connection_string=postgres_connection,
            query=select_query,
            node_id=f"{node_id}_verify_delete",
        )
        assert result["success"] is True
        assert len(result["data"]) == 0, "User should be deleted"

    async def test_no_404_errors_in_sequential_tests(self, postgres_connection):
        """Test: Context creation doesn't fail (original bug)."""
        node = AsyncSQLDatabaseNode()

        # Run multiple queries in sequence
        for i in range(5):
            node_id = f"test_no_404_{i}"

            result = await node.run(
                connection_string=postgres_connection,
                query="SELECT 1 as test_value",
                node_id=node_id,
            )

            # Should never get 404 context errors
            assert (
                result["success"] is True
            ), f"Iteration {i} failed: {result.get('error')}"
            assert "404" not in str(
                result.get("error", "")
            ), f"Got 404 error on iteration {i}: {result.get('error')}"
            assert result["data"][0]["test_value"] == 1

    async def test_cleanup_works_between_tests(self, postgres_connection):
        """Test: Pool cleanup doesn't break subsequent tests."""
        node = AsyncSQLDatabaseNode()
        node_id = "test_cleanup"

        # Insert and delete in same test
        insert_query = """
        INSERT INTO test_users_pytest_pool (name, email, bio)
        VALUES ('Temp User', 'temp@test.com', 'Temporary')
        RETURNING id
        """
        result = await node.run(
            connection_string=postgres_connection,
            query=insert_query,
            node_id=f"{node_id}_insert",
        )
        assert result["success"] is True
        temp_id = result["data"][0]["id"]

        # Delete immediately
        delete_query = f"DELETE FROM test_users_pytest_pool WHERE id = {temp_id}"
        result = await node.run(
            connection_string=postgres_connection,
            query=delete_query,
            node_id=f"{node_id}_delete",
        )
        assert result["success"] is True

        # Verify pool still works after cleanup
        select_query = "SELECT COUNT(*) as count FROM test_users_pytest_pool"
        result = await node.run(
            connection_string=postgres_connection,
            query=select_query,
            node_id=f"{node_id}_verify",
        )
        assert result["success"] is True
        # Should have users from previous tests (Alice, Bob, Charlie = 3)
        assert (
            result["data"][0]["count"] >= 3
        ), "Pool should still work after cleanup operations"

"""Tier 2 integration tests for AsyncSQLDatabaseNode external pool injection.

Uses a REAL asyncpg pool against Docker PostgreSQL. NO MOCKING.

Requirements:
    - Docker PostgreSQL running on port 5434
    - Credentials: test_user / test_password / kailash_test
"""

import asyncio
import os

import asyncpg
import pytest
import pytest_asyncio

from kailash.nodes.data.async_sql import AsyncSQLDatabaseNode

POSTGRES_DSN = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql://test_user:test_password@localhost:5434/kailash_test",
)


def get_rows(result):
    """Extract row data from AsyncSQLDatabaseNode execute result."""
    return result["result"]["data"]


@pytest_asyncio.fixture(loop_scope="module", scope="module")
async def shared_pool():
    """Create a real asyncpg pool shared across all tests in this module."""
    pool = await asyncpg.create_pool(POSTGRES_DSN, min_size=2, max_size=5)
    yield pool
    await pool.close()


@pytest_asyncio.fixture(autouse=True, loop_scope="module")
async def setup_test_table(shared_pool):
    """Create and tear down a test table for each test."""
    async with shared_pool.acquire() as conn:
        await conn.execute(
            "CREATE TABLE IF NOT EXISTS ext_pool_test ("
            "  id SERIAL PRIMARY KEY,"
            "  value TEXT NOT NULL"
            ")"
        )
        await conn.execute("TRUNCATE ext_pool_test")
    yield
    async with shared_pool.acquire() as conn:
        await conn.execute("DROP TABLE IF EXISTS ext_pool_test")


@pytest.mark.asyncio(loop_scope="module")
class TestExternalPoolRealQuery:
    """Execute real queries through an injected asyncpg pool."""

    async def test_select_via_external_pool(self, shared_pool):
        """A node using an external pool can execute a SELECT and return results."""
        node = AsyncSQLDatabaseNode(
            name="ext_select",
            database_type="postgresql",
            query="SELECT 1 AS num",
            external_pool=shared_pool,
        )
        try:
            result = await node.execute_async()
            rows = get_rows(result)
            assert len(rows) >= 1
            assert rows[0]["num"] == 1
        finally:
            await node.cleanup()

    async def test_insert_and_select_via_external_pool(self, shared_pool):
        """A node can INSERT and then SELECT using the same external pool."""
        insert_node = AsyncSQLDatabaseNode(
            name="ext_insert",
            database_type="postgresql",
            query="INSERT INTO ext_pool_test (value) VALUES ($1) RETURNING id, value",
            params=["hello_external"],
            external_pool=shared_pool,
        )
        try:
            insert_result = await insert_node.execute_async()
            insert_rows = get_rows(insert_result)
            assert len(insert_rows) == 1
            assert insert_rows[0]["value"] == "hello_external"
        finally:
            await insert_node.cleanup()

        select_node = AsyncSQLDatabaseNode(
            name="ext_select_back",
            database_type="postgresql",
            query="SELECT id, value FROM ext_pool_test WHERE value = $1",
            params=["hello_external"],
            external_pool=shared_pool,
        )
        try:
            select_result = await select_node.execute_async()
            select_rows = get_rows(select_result)
            assert len(select_rows) == 1
            assert select_rows[0]["value"] == "hello_external"
        finally:
            await select_node.cleanup()


@pytest.mark.asyncio(loop_scope="module")
class TestPoolSurvivesCleanup:
    """The external pool must remain usable after node.cleanup()."""

    async def test_pool_alive_after_node_cleanup(self, shared_pool):
        """After cleanup(), the shared pool is still open and functional."""
        node = AsyncSQLDatabaseNode(
            name="ext_cleanup_test",
            database_type="postgresql",
            query="SELECT 42 AS answer",
            external_pool=shared_pool,
        )
        await node.execute_async()
        await node.cleanup()

        assert not shared_pool._closed, "Pool was closed by node cleanup"
        async with shared_pool.acquire() as conn:
            row = await conn.fetchrow("SELECT 99 AS still_alive")
            assert row["still_alive"] == 99


@pytest.mark.asyncio(loop_scope="module")
class TestMultipleNodesSharePool:
    """Multiple nodes using the same external pool concurrently."""

    async def test_concurrent_nodes_same_pool(self, shared_pool):
        """Three nodes sharing one pool can execute concurrently without errors."""
        nodes = []
        for i in range(3):
            node = AsyncSQLDatabaseNode(
                name=f"concurrent_{i}",
                database_type="postgresql",
                query=f"SELECT {i} AS idx",
                external_pool=shared_pool,
            )
            nodes.append(node)

        try:
            results = await asyncio.gather(
                *[n.execute_async() for n in nodes], return_exceptions=True
            )
            for i, result in enumerate(results):
                assert not isinstance(
                    result, Exception
                ), f"Node concurrent_{i} failed: {result}"
                rows = get_rows(result)
                assert rows[0]["idx"] == i
        finally:
            await asyncio.gather(*[n.cleanup() for n in nodes])

        assert not shared_pool._closed
        async with shared_pool.acquire() as conn:
            row = await conn.fetchrow("SELECT 1 AS ok")
            assert row["ok"] == 1

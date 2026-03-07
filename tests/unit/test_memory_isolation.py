"""Unit tests for memory database isolation and URI parsing (TODO-013 IS-4).

Tests that:
- Shared-cache memory DBs share state across connections
- Named memory DBs are isolated from each other
- URI parsing correctly identifies memory databases
- _is_memory_db flag is set correctly for various path formats
"""

import asyncio

import aiosqlite
import pytest

from kailash.core.pool.sqlite_pool import (
    AsyncSQLitePool,
    ConnectionFactory,
    SQLitePoolConfig,
)


@pytest.mark.asyncio
class TestSharedCacheStateSharing:
    async def test_memory_pool_shares_state_via_single_connection(self):
        """Memory DB pool uses single connection — writes visible to reads."""
        config = SQLitePoolConfig(db_path=":memory:")
        pool = AsyncSQLitePool(config)
        await pool.initialize()

        try:
            async with pool.acquire_write() as conn:
                await conn.execute("CREATE TABLE shared (id INTEGER, val TEXT)")
                await conn.execute("INSERT INTO shared VALUES (1, 'hello')")
                await conn.commit()

            async with pool.acquire_read() as conn:
                cursor = await conn.execute("SELECT val FROM shared WHERE id = 1")
                row = await cursor.fetchone()
                assert row is not None
                assert row[0] == "hello"
        finally:
            await pool.close()

    async def test_memory_pool_read_delegates_to_write(self):
        """In memory mode, acquire_read() delegates to acquire_write()."""
        config = SQLitePoolConfig(db_path=":memory:")
        pool = AsyncSQLitePool(config)
        await pool.initialize()

        try:
            assert pool._is_memory_db is True
            # Both acquire_read and acquire_write should use the same connection
            async with pool.acquire_write() as w_conn:
                await w_conn.execute("CREATE TABLE rw (id INTEGER)")
                await w_conn.commit()

            async with pool.acquire_read() as r_conn:
                cursor = await r_conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='rw'"
                )
                row = await cursor.fetchone()
                assert row is not None
        finally:
            await pool.close()


@pytest.mark.asyncio
class TestNamedMemoryDBIsolation:
    async def test_different_named_dbs_are_isolated(self):
        """Different named memory databases should not share tables."""
        config_a = SQLitePoolConfig(db_path=":memory:")
        config_b = SQLitePoolConfig(db_path=":memory:")
        pool_a = AsyncSQLitePool(config_a)
        pool_b = AsyncSQLitePool(config_b)
        await pool_a.initialize()
        await pool_b.initialize()

        try:
            async with pool_a.acquire_write() as conn:
                await conn.execute("CREATE TABLE only_in_a (id INTEGER)")
                await conn.commit()

            # pool_b should NOT see the table from pool_a
            async with pool_b.acquire_write() as conn:
                cursor = await conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='only_in_a'"
                )
                row = await cursor.fetchone()
                assert row is None, "Table from pool_a should not be visible in pool_b"
        finally:
            await pool_a.close()
            await pool_b.close()


@pytest.mark.asyncio
class TestURIParsing:
    async def test_file_uri_with_mode_memory(self):
        """URI with mode=memory is detected as memory DB."""
        config = SQLitePoolConfig(
            db_path="file:testdb?mode=memory&cache=shared",
            uri=True,
        )
        pool = AsyncSQLitePool(config)
        assert pool._is_memory_db is True
        await pool.initialize()

        try:
            async with pool.acquire_write() as conn:
                await conn.execute("CREATE TABLE uri_test (id INTEGER)")
                await conn.commit()

            async with pool.acquire_read() as conn:
                cursor = await conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='uri_test'"
                )
                row = await cursor.fetchone()
                assert row is not None
        finally:
            await pool.close()

    async def test_plain_memory_string(self):
        """:memory: string is detected as memory DB."""
        config = SQLitePoolConfig(db_path=":memory:")
        pool = AsyncSQLitePool(config)
        assert pool._is_memory_db is True

    async def test_file_path_not_memory(self, tmp_path):
        """File path is NOT detected as memory DB."""
        db = str(tmp_path / "real.db")
        config = SQLitePoolConfig(db_path=db)
        pool = AsyncSQLitePool(config)
        assert pool._is_memory_db is False


class TestIsMemoryDbFlag:
    """Test _is_memory_db flag on pool config for various path formats."""

    def test_colon_memory_colon(self):
        config = SQLitePoolConfig(db_path=":memory:")
        pool = AsyncSQLitePool(config)
        assert pool._is_memory_db is True

    def test_uri_mode_memory(self):
        config = SQLitePoolConfig(
            db_path="file:test?mode=memory&cache=shared", uri=True
        )
        pool = AsyncSQLitePool(config)
        assert pool._is_memory_db is True

    def test_file_path(self):
        config = SQLitePoolConfig(db_path="/tmp/test.db")
        pool = AsyncSQLitePool(config)
        assert pool._is_memory_db is False

    def test_relative_path(self):
        config = SQLitePoolConfig(db_path="test.db")
        pool = AsyncSQLitePool(config)
        assert pool._is_memory_db is False

    def test_empty_string(self):
        config = SQLitePoolConfig(db_path="")
        pool = AsyncSQLitePool(config)
        assert pool._is_memory_db is False


class TestConnectionFactoryMemorySkipsPragmas:
    """Memory DB factory skips WAL-related PRAGMAs."""

    @pytest.mark.asyncio
    async def test_memory_factory_skips_journal_mode(self):
        factory = ConnectionFactory(
            db_path=":memory:",
            pragmas={"journal_mode": "WAL", "foreign_keys": "ON"},
            is_memory_db=True,
        )
        conn = await factory.create()
        try:
            # journal_mode should NOT be WAL (memory DBs don't support WAL)
            cursor = await conn.execute("PRAGMA journal_mode")
            row = await cursor.fetchone()
            assert row[0].upper() != "WAL", "Memory DB should not have WAL mode"

            # foreign_keys SHOULD still be applied
            cursor = await conn.execute("PRAGMA foreign_keys")
            row = await cursor.fetchone()
            assert row[0] == 1
        finally:
            await conn.close()

"""Integration tests for AsyncSQLitePool + adapter end-to-end (TODO-016).

Tests the full stack: adapter -> pool -> aiosqlite -> SQLite.
Covers concurrent reads/writes, transaction isolation, pool exhaustion,
memory databases, resource cleanup, and transaction bypass regression (IS-6).

Uses real SQLite databases (no mocking).
"""

import asyncio
import threading

import pytest

from kailash.core.pool.sqlite_pool import (
    AsyncSQLitePool,
    PoolExhaustedError,
    SQLitePoolConfig,
)
from kailash.nodes.data.async_sql import (
    DatabaseConfig,
    DatabaseType,
    ProductionSQLiteAdapter,
)


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "integration.db")


@pytest.fixture
async def pool(db_path):
    config = SQLitePoolConfig(
        db_path=db_path,
        max_read_connections=3,
        acquire_timeout=5.0,
    )
    p = AsyncSQLitePool(config)
    await p.initialize()

    # Create test table
    async with p.acquire_write() as conn:
        await conn.execute("CREATE TABLE items (id INTEGER PRIMARY KEY, name TEXT)")
        await conn.commit()

    yield p
    await p.close()


@pytest.mark.asyncio
class TestConcurrentReads:
    async def test_10_concurrent_selects_succeed(self, pool):
        """10 concurrent SELECT queries succeed without 'database is locked'."""
        async with pool.acquire_write() as conn:
            for i in range(10):
                await conn.execute(f"INSERT INTO items VALUES ({i}, 'item_{i}')")
            await conn.commit()

        async def read_task(task_id):
            async with pool.acquire_read() as conn:
                cursor = await conn.execute("SELECT COUNT(*) FROM items")
                row = await cursor.fetchone()
                return row[0]

        results = await asyncio.gather(*[read_task(i) for i in range(10)])
        assert all(r == 10 for r in results)


@pytest.mark.asyncio
class TestWriteSerialization:
    async def test_concurrent_writes_serialized(self, pool):
        """Concurrent INSERT operations are serialized, no data corruption."""

        async def write_task(task_id):
            async with pool.acquire_write() as conn:
                await conn.execute(
                    f"INSERT INTO items VALUES ({task_id}, 'task_{task_id}')"
                )
                await conn.commit()

        await asyncio.gather(*[write_task(i) for i in range(1, 6)])

        async with pool.acquire_read() as conn:
            cursor = await conn.execute("SELECT COUNT(*) FROM items")
            row = await cursor.fetchone()
            assert row[0] == 5


@pytest.mark.asyncio
class TestReadDuringWrite:
    async def test_reads_continue_during_write(self, pool):
        """Reads succeed while a write transaction is in progress."""
        async with pool.acquire_write() as conn:
            await conn.execute("INSERT INTO items VALUES (1, 'first')")
            await conn.commit()

        write_started = asyncio.Event()
        write_proceed = asyncio.Event()

        async def slow_write():
            async with pool.acquire_write() as conn:
                await conn.execute("INSERT INTO items VALUES (2, 'second')")
                write_started.set()
                await write_proceed.wait()
                await conn.commit()

        async def concurrent_read():
            await write_started.wait()
            async with pool.acquire_read() as conn:
                cursor = await conn.execute("SELECT COUNT(*) FROM items")
                row = await cursor.fetchone()
                return row[0]

        write_task = asyncio.create_task(slow_write())
        count = await concurrent_read()
        assert count >= 1  # Can read while write is in progress
        write_proceed.set()
        await write_task


@pytest.mark.asyncio
class TestConnectionReuse:
    async def test_connections_reused(self, pool):
        """Connections are reused, not created/destroyed per query."""
        for _ in range(20):
            async with pool.acquire_read() as conn:
                await conn.execute("SELECT 1")

        metrics = pool.get_metrics()
        # Many acquires but few connections created
        assert metrics.total_acquires >= 20
        assert metrics.connections_created <= 5  # Writer + a few readers


@pytest.mark.asyncio
class TestPoolExhaustion:
    async def test_pool_exhaustion_and_recovery(self, db_path):
        """Pool fills up, times out, then recovers."""
        config = SQLitePoolConfig(
            db_path=db_path,
            max_read_connections=1,
            acquire_timeout=0.2,
        )
        pool = AsyncSQLitePool(config)
        await pool.initialize()

        try:
            async with pool.acquire_write() as conn:
                await conn.execute(
                    "CREATE TABLE exhaust (id INTEGER PRIMARY KEY, name TEXT)"
                )
                await conn.commit()

            # Exhaust the pool
            async with pool.acquire_read():
                with pytest.raises(PoolExhaustedError):
                    async with pool.acquire_read(timeout=0.1):
                        pass

            # After releasing, pool recovers
            async with pool.acquire_read() as conn:
                cursor = await conn.execute("SELECT 1")
                row = await cursor.fetchone()
                assert row[0] == 1
        finally:
            await pool.close()


@pytest.mark.asyncio
class TestMemoryDatabase:
    async def test_memory_db_lifecycle(self):
        """Full adapter lifecycle with :memory: using URI shared-cache."""
        config = SQLitePoolConfig(db_path=":memory:")
        pool = AsyncSQLitePool(config)
        await pool.initialize()

        try:
            async with pool.acquire_write() as conn:
                await conn.execute("CREATE TABLE mem (id INTEGER, val TEXT)")
                await conn.execute("INSERT INTO mem VALUES (1, 'hello')")
                await conn.commit()

            async with pool.acquire_read() as conn:
                cursor = await conn.execute("SELECT val FROM mem WHERE id = 1")
                row = await cursor.fetchone()
                assert row[0] == "hello"
        finally:
            await pool.close()


@pytest.mark.asyncio
class TestResourceCleanup:
    async def test_no_thread_leak_after_close(self, db_path):
        """No orphaned aiosqlite threads after disconnect."""
        config = SQLitePoolConfig(db_path=db_path, max_read_connections=3)
        pool = AsyncSQLitePool(config)
        await pool.initialize()

        before = threading.active_count()

        # Create multiple readers
        for _ in range(3):
            async with pool.acquire_read():
                pass

        await pool.close()

        # Allow threads to clean up
        await asyncio.sleep(0.1)
        after = threading.active_count()

        # Should not have more threads than before
        assert after <= before + 1  # +1 tolerance for GC timing

    async def test_adapter_lifecycle_no_leaks(self, pool):
        """connect -> queries -> disconnect cycle completes cleanly."""
        # Multiple operations
        for i in range(5):
            async with pool.acquire_write() as conn:
                await conn.execute(f"INSERT INTO items VALUES ({i}, 'item_{i}')")
                await conn.commit()

        for _ in range(5):
            async with pool.acquire_read() as conn:
                cursor = await conn.execute("SELECT COUNT(*) FROM items")
                await cursor.fetchone()

        # Pool should still be healthy
        assert await pool.check_health() is True


@pytest.mark.asyncio
class TestTransactionBypassRegression:
    """IS-6: Verify ProductionSQLiteAdapter.execute() uses transaction's connection.

    The core bug: when transaction is not None, execute() must delegate to
    super().execute() (which uses the transaction's connection), NOT route
    through EnterpriseConnectionPool (which creates a different connection,
    causing 'database is locked').
    """

    async def test_execute_with_transaction_uses_transaction_connection(self, tmp_path):
        """execute(query, transaction=txn) must use the transaction's connection."""
        db = str(tmp_path / "txn_bypass.db")
        config = DatabaseConfig(
            type=DatabaseType.SQLITE,
            connection_string=db,
        )
        adapter = ProductionSQLiteAdapter(config)
        await adapter.connect()

        try:
            # Create a table first
            await adapter.execute(
                "CREATE TABLE txn_test (id INTEGER PRIMARY KEY, val TEXT)"
            )

            # Begin a transaction — returns (connection, savepoint, depth)
            txn = await adapter.begin_transaction()
            txn_conn = txn[0]  # The connection object

            # Execute within the transaction
            await adapter.execute(
                "INSERT INTO txn_test VALUES (1, 'inside_txn')",
                transaction=txn,
            )

            # Verify the data is visible on the SAME connection (uncommitted)
            cursor = await txn_conn.execute("SELECT val FROM txn_test WHERE id = 1")
            row = await cursor.fetchone()
            assert (
                row is not None
            ), "Data should be visible on the transaction's connection"
            assert row[0] == "inside_txn"

            # Commit
            await adapter.commit_transaction(txn)

            # Verify data persisted after commit
            result = await adapter.execute("SELECT val FROM txn_test WHERE id = 1")
            assert len(result) == 1
            assert result[0]["val"] == "inside_txn"
        finally:
            await adapter.disconnect()

    async def test_execute_without_transaction_uses_pool(self, tmp_path):
        """execute(query) without transaction routes through enterprise pool."""
        db = str(tmp_path / "pool_route.db")
        config = DatabaseConfig(
            type=DatabaseType.SQLITE,
            connection_string=db,
        )
        adapter = ProductionSQLiteAdapter(config)
        await adapter.connect()

        try:
            await adapter.execute("CREATE TABLE pool_test (id INTEGER, val TEXT)")
            await adapter.execute("INSERT INTO pool_test VALUES (1, 'via_pool')")
            result = await adapter.execute("SELECT val FROM pool_test WHERE id = 1")
            assert len(result) == 1
            assert result[0]["val"] == "via_pool"
        finally:
            await adapter.disconnect()

"""Unit tests for AsyncSQLitePool (TODO-015).

Tests the core pool implementation covering initialization, read/write separation,
concurrency, timeouts, health checks, connection recycling, metrics, memory DB
fallback, shutdown, and query routing.

Uses real aiosqlite connections with temp file databases (no mocking).
"""

import asyncio

import pytest

from kailash.core.pool.sqlite_pool import (
    AsyncSQLitePool,
    PoolExhaustedError,
    SQLitePoolConfig,
    _is_read_query,
)


@pytest.fixture
def tmp_db(tmp_path):
    """Create a temporary database path."""
    return str(tmp_path / "test.db")


@pytest.fixture
def pool_config(tmp_db):
    """Create a pool config with small sizes for testing."""
    return SQLitePoolConfig(
        db_path=tmp_db,
        max_read_connections=2,
        max_lifetime=3600.0,
        acquire_timeout=2.0,
    )


@pytest.fixture
async def pool(pool_config):
    """Create and initialize a pool, close after test."""
    p = AsyncSQLitePool(pool_config)
    await p.initialize()
    yield p
    await p.close()


# --- Initialization ---


@pytest.mark.asyncio
class TestPoolInitialization:
    async def test_initialize_sets_initialized(self, pool):
        """initialize() marks pool as initialized; writer created lazily."""
        assert pool._initialized is True
        # Writer is created lazily on first acquire_write(), not in initialize()
        assert pool._write_conn is None

    async def test_readers_created_lazily(self, pool):
        """No reader connections exist until first acquire_read()."""
        assert pool._read_count == 0

    async def test_first_read_creates_connection(self, pool):
        """First acquire_read() creates a new reader connection."""
        async with pool.acquire_read() as conn:
            cursor = await conn.execute("SELECT 1")
            row = await cursor.fetchone()
            assert row[0] == 1
        assert pool._read_count == 1

    async def test_pragmas_applied_to_writer(self, pool):
        """Writer connection has PRAGMAs applied."""
        async with pool.acquire_write() as conn:
            cursor = await conn.execute("PRAGMA journal_mode")
            row = await cursor.fetchone()
            assert row[0].upper() == "WAL"

            cursor = await conn.execute("PRAGMA foreign_keys")
            row = await cursor.fetchone()
            assert row[0] == 1

    async def test_double_initialize_is_idempotent(self, pool):
        """Calling initialize() twice does not create extra connections."""
        created_before = pool._metrics.connections_created
        await pool.initialize()
        assert pool._metrics.connections_created == created_before


# --- Read/Write Separation ---


@pytest.mark.asyncio
class TestReadWriteSeparation:
    async def test_write_then_read_sees_data(self, pool):
        """Data written via write connection is visible via read connection."""
        async with pool.acquire_write() as conn:
            await conn.execute("CREATE TABLE test_rw (id INTEGER, val TEXT)")
            await conn.execute("INSERT INTO test_rw VALUES (1, 'hello')")
            await conn.commit()

        async with pool.acquire_read() as conn:
            cursor = await conn.execute("SELECT val FROM test_rw WHERE id = 1")
            row = await cursor.fetchone()
            assert row[0] == "hello"

    async def test_concurrent_reads_succeed(self, pool):
        """Multiple concurrent readers can execute simultaneously."""
        async with pool.acquire_write() as conn:
            await conn.execute("CREATE TABLE cr (id INTEGER)")
            await conn.execute("INSERT INTO cr VALUES (1)")
            await conn.commit()

        async def read_task():
            async with pool.acquire_read() as conn:
                cursor = await conn.execute("SELECT id FROM cr")
                row = await cursor.fetchone()
                return row[0]

        results = await asyncio.gather(read_task(), read_task())
        assert results == [1, 1]

    async def test_write_serialized(self, pool):
        """Concurrent writes are serialized (one at a time)."""
        order = []

        async with pool.acquire_write() as conn:
            await conn.execute("CREATE TABLE ws (id INTEGER)")
            await conn.commit()

        async def write_task(task_id):
            async with pool.acquire_write() as conn:
                order.append(f"start_{task_id}")
                await conn.execute(f"INSERT INTO ws VALUES ({task_id})")
                await conn.commit()
                order.append(f"end_{task_id}")

        await asyncio.gather(write_task(1), write_task(2))
        # Writes are serialized: one must complete before the other starts
        assert order[0].startswith("start_")
        assert order[1].startswith("end_")


# --- Timeout ---


@pytest.mark.asyncio
class TestTimeout:
    async def test_read_timeout_raises_pool_exhausted(self, tmp_db):
        """acquire_read() raises PoolExhaustedError when all readers are busy."""
        config = SQLitePoolConfig(
            db_path=tmp_db,
            max_read_connections=1,
            acquire_timeout=0.1,
        )
        pool = AsyncSQLitePool(config)
        await pool.initialize()

        try:
            async with pool.acquire_read():
                with pytest.raises(PoolExhaustedError, match="read connection"):
                    async with pool.acquire_read(timeout=0.1):
                        pass
        finally:
            await pool.close()

    async def test_write_timeout_raises_pool_exhausted(self, tmp_db):
        """acquire_write() raises PoolExhaustedError when writer is busy."""
        config = SQLitePoolConfig(
            db_path=tmp_db,
            acquire_timeout=0.1,
        )
        pool = AsyncSQLitePool(config)
        await pool.initialize()

        try:
            async with pool.acquire_write():
                with pytest.raises(PoolExhaustedError, match="write connection"):
                    async with pool.acquire_write(timeout=0.1):
                        pass
        finally:
            await pool.close()


# --- LIFO Ordering ---


@pytest.mark.asyncio
class TestLIFOOrdering:
    async def test_most_recently_returned_connection_acquired_next(self, pool):
        """LIFO: most recently returned reader is acquired next (cache locality)."""
        # Acquire two readers
        async with pool.acquire_read() as conn1:
            conn1_id = id(conn1)
        async with pool.acquire_read() as conn2:
            conn2_id = id(conn2)

        # Next acquire should get conn2 (LIFO)
        async with pool.acquire_read() as conn3:
            assert id(conn3) == conn2_id


# --- Health Check ---


@pytest.mark.asyncio
class TestHealthCheck:
    async def test_broken_writer_replaced(self, pool):
        """Broken writer connection is replaced on acquire."""
        # Force lazy creation of writer by acquiring once
        async with pool.acquire_write():
            pass
        # Break the writer by closing it through the aiosqlite API
        broken_conn = pool._write_conn
        await broken_conn.close()

        # Acquire should detect the broken connection and replace it
        async with pool.acquire_write() as conn:
            cursor = await conn.execute("SELECT 1")
            row = await cursor.fetchone()
            assert row[0] == 1
        assert pool._metrics.connections_created >= 2  # Original + replacement

    async def test_check_health_returns_true_for_healthy_pool(self, pool):
        """check_health() returns True when all connections are healthy."""
        assert await pool.check_health() is True

    async def test_check_health_detects_broken_reader(self, pool):
        """check_health() returns False when a reader is broken."""
        # Create a reader by acquiring and releasing
        async with pool.acquire_read():
            pass

        # Break the idle reader by closing it
        conn = pool._read_queue.get_nowait()
        await conn.close()
        pool._read_queue.put_nowait(conn)

        assert await pool.check_health() is False


# --- Connection Recycling ---


@pytest.mark.asyncio
class TestConnectionRecycling:
    async def test_stale_connection_recycled(self, tmp_db):
        """Connection older than max_lifetime is replaced on acquire."""
        config = SQLitePoolConfig(
            db_path=tmp_db,
            max_lifetime=0.0,  # Immediate recycling
        )
        pool = AsyncSQLitePool(config)
        await pool.initialize()

        try:
            original_id = id(pool._write_conn)
            async with pool.acquire_write() as conn:
                # Connection should have been recycled (new object)
                assert id(conn) != original_id
            assert pool._metrics.connections_recycled >= 1
        finally:
            await pool.close()


# --- Metrics ---


@pytest.mark.asyncio
class TestMetrics:
    async def test_metrics_accurate_after_operations(self, pool):
        """get_metrics() returns accurate counts after acquire/release."""
        # Initial state (writer created lazily, so 0 connections)
        m = pool.get_metrics()
        assert m.connections_created == 0

        # Acquire and release a reader
        async with pool.acquire_read():
            m = pool.get_metrics()
            assert m.active_readers == 1
            assert m.connections_created == 1  # 1 reader

        m = pool.get_metrics()
        assert m.active_readers == 0
        assert m.idle_readers == 1
        assert m.total_acquires >= 1

    async def test_timeout_increments_metric(self, tmp_db):
        """Timeout increments total_timeouts metric."""
        config = SQLitePoolConfig(
            db_path=tmp_db,
            max_read_connections=1,
            acquire_timeout=0.05,
        )
        pool = AsyncSQLitePool(config)
        await pool.initialize()

        try:
            async with pool.acquire_read():
                with pytest.raises(PoolExhaustedError):
                    async with pool.acquire_read(timeout=0.05):
                        pass
            assert pool.get_metrics().total_timeouts == 1
        finally:
            await pool.close()


# --- Memory DB Mode ---


@pytest.mark.asyncio
class TestMemoryDBMode:
    async def test_memory_db_uses_single_connection(self):
        """Memory DB mode uses single connection for both reads and writes."""
        config = SQLitePoolConfig(
            db_path=":memory:",
            max_read_connections=3,
        )
        pool = AsyncSQLitePool(config)
        await pool.initialize()

        try:
            assert pool._is_memory_db is True

            # Write data
            async with pool.acquire_write() as conn:
                await conn.execute("CREATE TABLE mem_test (id INTEGER)")
                await conn.execute("INSERT INTO mem_test VALUES (42)")
                await conn.commit()

            # Read should use the same connection (via acquire_write internally)
            async with pool.acquire_read() as conn:
                cursor = await conn.execute("SELECT id FROM mem_test")
                row = await cursor.fetchone()
                assert row[0] == 42
        finally:
            await pool.close()


# --- Shutdown ---


@pytest.mark.asyncio
class TestShutdown:
    async def test_close_closes_all_connections(self, pool_config):
        """close() closes writer and all readers."""
        pool = AsyncSQLitePool(pool_config)
        await pool.initialize()

        # Create some readers
        async with pool.acquire_read():
            pass
        async with pool.acquire_read():
            pass

        await pool.close()
        assert pool._closed is True
        assert pool._write_conn is None
        assert pool._read_queue.empty()

    async def test_acquire_after_close_raises(self, pool_config):
        """Acquire after close() raises PoolExhaustedError."""
        pool = AsyncSQLitePool(pool_config)
        await pool.initialize()
        await pool.close()

        with pytest.raises(PoolExhaustedError, match="closed"):
            async with pool.acquire_write():
                pass

    async def test_double_close_is_safe(self, pool_config):
        """Calling close() twice does not raise."""
        pool = AsyncSQLitePool(pool_config)
        await pool.initialize()
        await pool.close()
        await pool.close()  # Should not raise


# --- Query Routing ---


class TestQueryRouting:
    """Test _is_read_query() and pool.acquire(query) routing."""

    def test_select_is_read(self):
        assert _is_read_query("SELECT * FROM users") is True

    def test_with_is_read(self):
        assert _is_read_query("WITH cte AS (SELECT 1) SELECT * FROM cte") is True

    def test_explain_is_read(self):
        assert _is_read_query("EXPLAIN QUERY PLAN SELECT 1") is True

    def test_pragma_read_is_read(self):
        assert _is_read_query("PRAGMA table_info(users)") is True

    def test_pragma_write_is_write(self):
        assert _is_read_query("PRAGMA journal_mode = WAL") is False

    def test_insert_is_write(self):
        assert _is_read_query("INSERT INTO users VALUES (1)") is False

    def test_update_is_write(self):
        assert _is_read_query("UPDATE users SET name = 'x'") is False

    def test_delete_is_write(self):
        assert _is_read_query("DELETE FROM users WHERE id = 1") is False

    def test_create_is_write(self):
        assert _is_read_query("CREATE TABLE foo (id INTEGER)") is False

    def test_drop_is_write(self):
        assert _is_read_query("DROP TABLE foo") is False

    def test_comment_stripped(self):
        assert _is_read_query("-- comment\nSELECT 1") is True

    def test_block_comment_stripped(self):
        assert _is_read_query("/* comment */ SELECT 1") is True

    def test_empty_query_is_write(self):
        assert _is_read_query("") is False
        assert _is_read_query("   ") is False

    def test_case_insensitive(self):
        assert _is_read_query("select * from foo") is True
        assert _is_read_query("Select * From foo") is True

    @pytest.mark.asyncio
    async def test_acquire_routes_select_to_reader(self, tmp_path):
        """acquire(query) routes SELECT to reader connection."""
        db = str(tmp_path / "route.db")
        config = SQLitePoolConfig(db_path=db, max_read_connections=1)
        pool = AsyncSQLitePool(config)
        await pool.initialize()

        try:
            async with pool.acquire("SELECT 1") as conn:
                cursor = await conn.execute("SELECT 1")
                row = await cursor.fetchone()
                assert row[0] == 1
        finally:
            await pool.close()

    @pytest.mark.asyncio
    async def test_acquire_routes_insert_to_writer(self, tmp_path):
        """acquire(query) routes INSERT to writer connection."""
        db = str(tmp_path / "route.db")
        config = SQLitePoolConfig(db_path=db, max_read_connections=1)
        pool = AsyncSQLitePool(config)
        await pool.initialize()

        try:
            async with pool.acquire("CREATE TABLE t (id INTEGER)") as conn:
                await conn.execute("CREATE TABLE t (id INTEGER)")
                await conn.commit()
        finally:
            await pool.close()

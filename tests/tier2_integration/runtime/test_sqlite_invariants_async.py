"""Tier-2 integration tests for SQLite pool concurrency invariants (TODO-024).

Moved from tests/unit/test_sqlite_invariants.py because these tests use real
aiosqlite connections, disk-based SQLite (WAL mode), and concurrent I/O patterns.
Pure static-analysis and query-routing tests remain in the original file.
"""

import asyncio

import pytest

from kailash.core.pool.sqlite_pool import (
    AsyncSQLitePool,
    PoolExhaustedError,
    SQLitePoolConfig,
)


@pytest.mark.asyncio
class TestWALModeActive:
    async def test_file_db_has_wal_mode(self, tmp_path):
        """File-based connections must have WAL journal mode."""
        db = str(tmp_path / "wal_test.db")
        config = SQLitePoolConfig(db_path=db)
        pool = AsyncSQLitePool(config)
        await pool.initialize()

        try:
            async with pool.acquire_write() as conn:
                cursor = await conn.execute("PRAGMA journal_mode")
                row = await cursor.fetchone()
                assert row[0].upper() == "WAL"
        finally:
            await pool.close()

    async def test_default_pragmas_applied(self, tmp_path):
        """All default PRAGMAs are applied to new connections."""
        db = str(tmp_path / "pragma_test.db")
        config = SQLitePoolConfig(db_path=db)
        pool = AsyncSQLitePool(config)
        await pool.initialize()

        try:
            async with pool.acquire_write() as conn:
                cursor = await conn.execute("PRAGMA foreign_keys")
                row = await cursor.fetchone()
                assert row[0] == 1, "foreign_keys should be ON"

                cursor = await conn.execute("PRAGMA busy_timeout")
                row = await cursor.fetchone()
                assert row[0] == 5000, "busy_timeout should be 5000"

                cursor = await conn.execute("PRAGMA synchronous")
                row = await cursor.fetchone()
                assert row[0] == 1, "synchronous should be NORMAL (1)"
        finally:
            await pool.close()


@pytest.mark.asyncio
class TestMemoryIsolation:
    async def test_shared_cache_shares_state(self):
        """:memory: databases share state across connections via URI shared-cache."""
        config = SQLitePoolConfig(db_path=":memory:")
        pool = AsyncSQLitePool(config)
        await pool.initialize()

        try:
            async with pool.acquire_write() as conn:
                await conn.execute("CREATE TABLE inv (id INTEGER, val TEXT)")
                await conn.execute("INSERT INTO inv VALUES (1, 'shared')")
                await conn.commit()

            async with pool.acquire_read() as conn:
                cursor = await conn.execute("SELECT val FROM inv WHERE id = 1")
                row = await cursor.fetchone()
                assert row is not None
                assert row[0] == "shared"
        finally:
            await pool.close()


@pytest.mark.asyncio
class TestBoundedConcurrency:
    async def test_pool_enforces_max_readers(self, tmp_path):
        """Pool raises PoolExhaustedError when max_read_connections exceeded."""
        db = str(tmp_path / "bounded.db")
        config = SQLitePoolConfig(
            db_path=db,
            max_read_connections=2,
            acquire_timeout=0.1,
        )
        pool = AsyncSQLitePool(config)
        await pool.initialize()

        try:
            conns = []
            # Acquire all readers manually via semaphore
            for _ in range(2):
                await pool._read_semaphore.acquire()
                conn = await pool._get_or_create_read_conn()
                conns.append(conn)

            # 3rd acquire should fail
            with pytest.raises(PoolExhaustedError):
                async with pool.acquire_read(timeout=0.1):
                    pass

            # Release readers
            for conn in conns:
                pool._read_queue.put_nowait(conn)
                pool._read_semaphore.release()
        finally:
            await pool.close()


@pytest.mark.asyncio
class TestConcurrencyStress:
    async def test_concurrent_reads_and_writes_no_locked_error(self, tmp_path):
        """10 concurrent reads + 3 concurrent writes -- no 'database is locked'."""
        db = str(tmp_path / "stress.db")
        config = SQLitePoolConfig(db_path=db, max_read_connections=3)
        pool = AsyncSQLitePool(config)
        await pool.initialize()

        try:
            async with pool.acquire_write() as conn:
                await conn.execute(
                    "CREATE TABLE stress (id INTEGER PRIMARY KEY, val INTEGER)"
                )
                await conn.commit()

            errors = []

            async def read_task(task_id):
                try:
                    async with pool.acquire_read() as conn:
                        cursor = await conn.execute("SELECT COUNT(*) FROM stress")
                        await cursor.fetchone()
                except Exception as e:
                    errors.append(f"read_{task_id}: {e}")

            async def write_task(task_id):
                try:
                    async with pool.acquire_write() as conn:
                        await conn.execute(
                            f"INSERT INTO stress VALUES ({task_id}, {task_id * 10})"
                        )
                        await conn.commit()
                except Exception as e:
                    errors.append(f"write_{task_id}: {e}")

            tasks = [read_task(i) for i in range(10)] + [
                write_task(i) for i in range(1, 4)
            ]
            await asyncio.gather(*tasks)

            assert errors == [], f"Errors occurred: {errors}"

            # Verify writes completed
            async with pool.acquire_read() as conn:
                cursor = await conn.execute("SELECT COUNT(*) FROM stress")
                row = await cursor.fetchone()
                assert row[0] == 3
        finally:
            await pool.close()

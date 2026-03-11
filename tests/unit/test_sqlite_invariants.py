"""Regression prevention tests for SQLite concurrency invariants (TODO-024).

Static analysis and infrastructure tests that catch regressions:
1. WAL mode active on file-based connections
2. :memory: databases share state across connections
3. Pool enforces bounded concurrency
4. Query routing correctness
5. No bare aiosqlite.connect() calls outside pool (IS-5)
"""

import asyncio
import re
from pathlib import Path

import pytest

from kailash.core.pool.sqlite_pool import (
    AsyncSQLitePool,
    PoolExhaustedError,
    SQLitePoolConfig,
    _is_read_query,
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
        """10 concurrent reads + 3 concurrent writes — no 'database is locked'."""
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


class TestQueryRoutingInvariants:
    """Verify query routing doesn't regress."""

    @pytest.mark.parametrize(
        "query,expected",
        [
            ("SELECT 1", True),
            ("select * from t", True),
            ("WITH cte AS (SELECT 1) SELECT * FROM cte", True),
            ("EXPLAIN SELECT 1", True),
            ("PRAGMA table_info(t)", True),
            ("PRAGMA journal_mode = WAL", False),
            ("INSERT INTO t VALUES (1)", False),
            ("UPDATE t SET x = 1", False),
            ("DELETE FROM t", False),
            ("CREATE TABLE t (id INT)", False),
            ("DROP TABLE t", False),
            ("ALTER TABLE t ADD COLUMN x INT", False),
            ("BEGIN", False),
            ("COMMIT", False),
            ("ROLLBACK", False),
            ("-- comment\nSELECT 1", True),
            ("/* block */ SELECT 1", True),
            ("", False),
        ],
    )
    def test_query_routing(self, query, expected):
        assert _is_read_query(query) is expected


class TestNoDirectAiosqliteConnect:
    """Static analysis: no bare aiosqlite.connect() outside the pool (IS-5).

    The pool is the single sanctioned entry point for SQLite connections.
    Direct aiosqlite.connect() calls bypass concurrency controls and cause
    'database is locked' errors.
    """

    # Directories that MUST route through the pool
    _SCAN_DIRS = [
        "src/kailash/nodes/data",
        "packages/kailash-dataflow/src/dataflow/adapters",
    ]

    # Files that are ALLOWED to call aiosqlite.connect() directly
    _ALLOWED_FILES = {
        "sqlite_pool.py",  # The pool itself
        "persistent_tiers.py",  # Kaizen memory tiers (standalone DBs)
        "async_sql.py",  # SQLiteAdapter base class (connection factory)
        "async_connection.py",  # Connection utilities
        "sqlite.py",  # DataFlow SQLite adapter (wraps connections)
        "sqlite_enterprise.py",  # DataFlow enterprise adapter (wraps connections)
    }

    # Pattern for bare aiosqlite.connect() calls
    _PATTERN = re.compile(r"aiosqlite\.connect\s*\(")

    def _find_repo_root(self) -> Path:
        """Walk up from this test file to find the repo root."""
        current = Path(__file__).resolve()
        for parent in current.parents:
            if (parent / "src").is_dir() and (parent / "packages").is_dir():
                return parent
        pytest.skip("Cannot locate repo root")

    def test_no_bare_aiosqlite_connect(self):
        """No bare aiosqlite.connect() in adapter/node code outside allowed files."""
        root = self._find_repo_root()
        violations = []

        for scan_dir in self._SCAN_DIRS:
            dir_path = root / scan_dir
            if not dir_path.is_dir():
                continue
            for py_file in dir_path.rglob("*.py"):
                if py_file.name in self._ALLOWED_FILES:
                    continue
                content = py_file.read_text()
                matches = list(self._PATTERN.finditer(content))
                if matches:
                    for m in matches:
                        line_no = content[: m.start()].count("\n") + 1
                        violations.append(f"{py_file.relative_to(root)}:{line_no}")

        assert (
            violations == []
        ), f"Found bare aiosqlite.connect() calls outside pool:\n" + "\n".join(
            f"  - {v}" for v in violations
        )

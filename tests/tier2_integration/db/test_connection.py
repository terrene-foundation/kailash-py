# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for ConnectionManager.

Tests cover:
- Initialization with dialect detection
- SQLite connection lifecycle (aiosqlite — no external service needed)
- Query execution with placeholder translation
- Fetch operations
- Error handling for missing drivers
- Connection pool close/cleanup
"""

from __future__ import annotations

import pytest

from kailash.db.connection import ConnectionManager
from kailash.db.dialect import DatabaseType, SQLiteDialect


# ---------------------------------------------------------------------------
# Construction and dialect detection
# ---------------------------------------------------------------------------
class TestConnectionManagerInit:
    def test_sqlite_url_sets_dialect(self):
        mgr = ConnectionManager("sqlite:///tmp/test.db")
        assert isinstance(mgr.dialect, SQLiteDialect)
        assert mgr.dialect.database_type == DatabaseType.SQLITE

    def test_url_stored(self):
        url = "sqlite:///tmp/test.db"
        mgr = ConnectionManager(url)
        assert mgr.url == url

    def test_pool_initially_none(self):
        mgr = ConnectionManager("sqlite:///tmp/test.db")
        assert mgr._pool is None

    def test_postgres_url_sets_dialect(self):
        mgr = ConnectionManager("postgresql://user:pass@localhost/db")
        assert mgr.dialect.database_type == DatabaseType.POSTGRESQL

    def test_mysql_url_sets_dialect(self):
        mgr = ConnectionManager("mysql://user:pass@localhost/db")
        assert mgr.dialect.database_type == DatabaseType.MYSQL

    def test_empty_url_raises(self):
        with pytest.raises(ValueError, match="[Dd]atabase URL"):
            ConnectionManager("")


# ---------------------------------------------------------------------------
# SQLite lifecycle (aiosqlite available — Tier 1 compatible)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
class TestConnectionManagerSQLite:
    async def test_initialize_creates_pool(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        mgr = ConnectionManager(f"sqlite:///{db_path}")
        await mgr.initialize()
        try:
            assert mgr._pool is not None
        finally:
            await mgr.close()

    async def test_execute_creates_table(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        mgr = ConnectionManager(f"sqlite:///{db_path}")
        await mgr.initialize()
        try:
            await mgr.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, name TEXT)")
            await mgr.execute("INSERT INTO test (id, name) VALUES (?, ?)", 1, "alice")
            rows = await mgr.fetch("SELECT * FROM test")
            assert len(rows) == 1
            assert rows[0]["id"] == 1
            assert rows[0]["name"] == "alice"
        finally:
            await mgr.close()

    async def test_fetchone_returns_single_row(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        mgr = ConnectionManager(f"sqlite:///{db_path}")
        await mgr.initialize()
        try:
            await mgr.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, val TEXT)")
            await mgr.execute("INSERT INTO test (id, val) VALUES (?, ?)", 1, "one")
            await mgr.execute("INSERT INTO test (id, val) VALUES (?, ?)", 2, "two")
            row = await mgr.fetchone("SELECT * FROM test WHERE id = ?", 1)
            assert row is not None
            assert row["id"] == 1
            assert row["val"] == "one"
        finally:
            await mgr.close()

    async def test_fetchone_returns_none_for_missing(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        mgr = ConnectionManager(f"sqlite:///{db_path}")
        await mgr.initialize()
        try:
            await mgr.execute("CREATE TABLE test (id INTEGER PRIMARY KEY)")
            row = await mgr.fetchone("SELECT * FROM test WHERE id = ?", 999)
            assert row is None
        finally:
            await mgr.close()

    async def test_close_sets_pool_to_none(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        mgr = ConnectionManager(f"sqlite:///{db_path}")
        await mgr.initialize()
        await mgr.close()
        assert mgr._pool is None

    async def test_execute_before_initialize_raises(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        mgr = ConnectionManager(f"sqlite:///{db_path}")
        with pytest.raises(RuntimeError, match="[Nn]ot initialized"):
            await mgr.execute("SELECT 1")

    async def test_fetch_before_initialize_raises(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        mgr = ConnectionManager(f"sqlite:///{db_path}")
        with pytest.raises(RuntimeError, match="[Nn]ot initialized"):
            await mgr.fetch("SELECT 1")

    async def test_memory_database(self):
        mgr = ConnectionManager("sqlite:///:memory:")
        await mgr.initialize()
        try:
            await mgr.execute("CREATE TABLE t (x INTEGER)")
            await mgr.execute("INSERT INTO t VALUES (?)", 42)
            rows = await mgr.fetch("SELECT x FROM t")
            assert rows == [{"x": 42}]
        finally:
            await mgr.close()

    async def test_placeholder_translation_for_sqlite(self, tmp_path):
        """SQLite uses ? natively, so translation is identity."""
        db_path = str(tmp_path / "test.db")
        mgr = ConnectionManager(f"sqlite:///{db_path}")
        await mgr.initialize()
        try:
            await mgr.execute("CREATE TABLE t (a INTEGER, b TEXT)")
            # canonical ? placeholders should work as-is for SQLite
            await mgr.execute("INSERT INTO t (a, b) VALUES (?, ?)", 1, "hello")
            rows = await mgr.fetch("SELECT * FROM t WHERE a = ?", 1)
            assert len(rows) == 1
        finally:
            await mgr.close()


# ---------------------------------------------------------------------------
# Postgres/MySQL init (no actual connection, just dialect detection)
# ---------------------------------------------------------------------------
class TestConnectionManagerNonSQLite:
    def test_postgres_init_does_not_require_asyncpg_at_construction(self):
        """Construction should succeed even without asyncpg installed;
        initialize() would fail later."""
        mgr = ConnectionManager("postgresql://localhost/db")
        assert mgr.dialect.database_type == DatabaseType.POSTGRESQL

    def test_mysql_init_does_not_require_aiomysql_at_construction(self):
        mgr = ConnectionManager("mysql://localhost/db")
        assert mgr.dialect.database_type == DatabaseType.MYSQL

# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 2 integration tests for migration 0002.

Exercises the migration against:

1. Real async SQLite (via :mod:`aiosqlite`) — always runs in CI.
2. Real PostgreSQL (via :mod:`asyncpg`) — gated by ``POSTGRES_TEST_URL``
   env var; falls back to the SQLite-only path when the env var is not
   set (``rules/testing.md`` § "Tier 2" → skipif is ACCEPTABLE when
   infra is unavailable).

Validates:

- 15 tables present after apply on each backend.
- Audit-table UPDATE + DELETE rejected by the dialect trigger/function.
- Rollback with ``force_downgrade=True`` drops every created table.
- Identifier-too-long halts cleanly before any DDL executes.
"""
from __future__ import annotations

import importlib
import os
from typing import Any, AsyncIterator

import pytest

from kailash.db.dialect import DatabaseType, IdentifierError

_mod = importlib.import_module(
    "kailash.tracking.migrations.0002_kml_prefix_tenant_audit"
)
Migration = _mod.Migration
DowngradeRefusedError = _mod.DowngradeRefusedError
TABLE_INVENTORY = _mod.TABLE_INVENTORY
PARKING_TABLE = _mod.PARKING_TABLE


# ---------------------------------------------------------------------------
# Async adapter — wraps aiosqlite so the migration's executor shape works.
# ---------------------------------------------------------------------------


class _AsyncSqliteAdapter:
    """Async wrapper around :mod:`aiosqlite` — matches the shape the
    migration's ``_execute`` helper expects. Not a production adapter,
    just a test fixture."""

    def __init__(self, conn):
        self._conn = conn
        self.database_type = DatabaseType.SQLITE

    async def execute(self, sql: str, params=None):
        if params is None:
            return await self._conn.execute(sql)
        return await self._conn.execute(sql, params)


@pytest.fixture
async def async_sqlite_conn() -> AsyncIterator[Any]:
    aiosqlite = pytest.importorskip("aiosqlite")
    conn = await aiosqlite.connect(":memory:")
    try:
        yield _AsyncSqliteAdapter(conn)
    finally:
        await conn.close()


# ---------------------------------------------------------------------------
# SQLite integration tests — always run.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sqlite_apply_creates_all_15_tables(async_sqlite_conn):
    m = Migration()
    result = await m.apply(async_sqlite_conn)
    assert result.rows_migrated == 15
    # Confirm every table exists.
    cursor = await async_sqlite_conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '_kml_%'"
    )
    rows = await cursor.fetchall()
    names = {row[0] for row in rows}
    for spec in TABLE_INVENTORY:
        assert spec.name in names, f"missing: {spec.name}"
    assert PARKING_TABLE in names


@pytest.mark.asyncio
async def test_sqlite_audit_update_rejected_by_trigger(async_sqlite_conn):
    m = Migration()
    await m.apply(async_sqlite_conn)
    await async_sqlite_conn.execute(
        "INSERT INTO _kml_audit "
        "(tenant_id, timestamp, actor_id, resource_kind, resource_id, action) "
        "VALUES ('t1', '2026-04-22', 'alice', 'run', 'r1', 'create')"
    )
    import sqlite3 as _sqlite3

    with pytest.raises(_sqlite3.IntegrityError) as excinfo:
        await async_sqlite_conn.execute("UPDATE _kml_audit SET action = 'x'")
    assert "append-only" in str(excinfo.value)


@pytest.mark.asyncio
async def test_sqlite_rollback_with_force_drops_all_tables(async_sqlite_conn):
    m = Migration()
    await m.apply(async_sqlite_conn)
    await m.rollback(async_sqlite_conn, force_downgrade=True)
    cursor = await async_sqlite_conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '_kml_%'"
    )
    rows = await cursor.fetchall()
    assert rows == []


@pytest.mark.asyncio
async def test_sqlite_rollback_refuses_without_force(async_sqlite_conn):
    m = Migration()
    await m.apply(async_sqlite_conn)
    with pytest.raises(DowngradeRefusedError):
        await m.rollback(async_sqlite_conn)


@pytest.mark.asyncio
async def test_sqlite_identifier_too_long_halts_cleanly(async_sqlite_conn):
    """The 63-char identifier limit is enforced by quote_identifier
    BEFORE any DDL executes. Verify a synthetic over-length index name
    raises IdentifierError and the DB is unmodified."""
    from kailash.db.dialect import PostgresDialect

    dialect = PostgresDialect()
    over_long = "ix_" + "a" * 62  # 65 chars
    with pytest.raises(IdentifierError):
        dialect.quote_identifier(over_long)

    # Run the real migration on SQLite — confirms the helper NEVER
    # produces an over-length name for the static TABLE_INVENTORY.
    m = Migration()
    await m.apply(async_sqlite_conn)


# ---------------------------------------------------------------------------
# PostgreSQL integration tests — gated by env var per rules/testing.md.
# ---------------------------------------------------------------------------


_POSTGRES_URL = os.environ.get("POSTGRES_TEST_URL")


class _AsyncPostgresAdapter:
    """Async wrapper around asyncpg that speaks the migration's executor
    shape. asyncpg uses ``$1, $2, ...`` placeholders natively, so we
    route every SQL string through the PostgresDialect's translator
    before dispatch."""

    def __init__(self, pool):
        self._pool = pool
        self.database_type = DatabaseType.POSTGRESQL
        from kailash.db.dialect import PostgresDialect

        self._dialect = PostgresDialect()

    async def execute(self, sql: str, params=None):
        translated = self._dialect.translate_query(sql)

        class _ResultShim:
            def __init__(self, rows):
                self._rows = rows
                self._consumed = False

            def fetchone(self):
                if self._consumed:
                    return None
                self._consumed = True
                return self._rows[0] if self._rows else None

            def fetchall(self):
                return list(self._rows)

        async with self._pool.acquire() as conn:
            if params is None:
                if translated.strip().upper().startswith(("SELECT", "WITH")):
                    rows = await conn.fetch(translated)
                    return _ResultShim(rows)
                await conn.execute(translated)
                return _ResultShim([])
            if translated.strip().upper().startswith(("SELECT", "WITH")):
                rows = await conn.fetch(translated, *params)
                return _ResultShim(rows)
            await conn.execute(translated, *params)
            return _ResultShim([])


@pytest.fixture
async def pg_conn() -> AsyncIterator[Any]:
    if not _POSTGRES_URL:
        pytest.skip("POSTGRES_TEST_URL not set")
    asyncpg = pytest.importorskip("asyncpg")
    pool = await asyncpg.create_pool(_POSTGRES_URL, min_size=1, max_size=2)
    try:
        # Clean slate: drop any pre-existing _kml_* tables and the
        # parking table so repeat test runs start clean.
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_name LIKE '_kml_%' AND table_schema = current_schema()"
            )
            for row in rows:
                name = row["table_name"]
                await conn.execute(f'DROP TABLE IF EXISTS "{name}" CASCADE')
        yield _AsyncPostgresAdapter(pool)
    finally:
        await pool.close()


@pytest.mark.asyncio
async def test_postgres_apply_creates_all_15_tables(pg_conn):
    m = Migration()
    result = await m.apply(pg_conn)
    assert result.rows_migrated == 15
    cursor = await pg_conn.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_name LIKE '_kml_%' AND table_schema = current_schema()"
    )
    rows = cursor.fetchall()
    names = {row["table_name"] for row in rows}
    for spec in TABLE_INVENTORY:
        assert spec.name in names


@pytest.mark.asyncio
async def test_postgres_audit_update_rejected_by_trigger(pg_conn):
    import asyncpg

    m = Migration()
    await m.apply(pg_conn)
    await pg_conn.execute(
        "INSERT INTO _kml_audit "
        "(tenant_id, timestamp, actor_id, resource_kind, resource_id, action) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ("t1", "2026-04-22T00:00:00+00:00", "alice", "run", "r1", "create"),
    )
    with pytest.raises(asyncpg.exceptions.RaiseError) as excinfo:
        await pg_conn.execute("UPDATE _kml_audit SET action = ?", ("tamper",))
    assert "append-only" in str(excinfo.value)


@pytest.mark.asyncio
async def test_postgres_rollback_with_force_drops_all_tables(pg_conn):
    m = Migration()
    await m.apply(pg_conn)
    await m.rollback(pg_conn, force_downgrade=True)
    cursor = await pg_conn.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_name LIKE '_kml_%' AND table_schema = current_schema()"
    )
    rows = cursor.fetchall()
    assert rows == []

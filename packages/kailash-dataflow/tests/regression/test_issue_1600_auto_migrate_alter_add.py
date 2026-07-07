# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression (issue #1600): auto-migrate ALTER-ADDs a NEW column to an
already-existing table.

DataFlow auto-migrate relied on ``CREATE TABLE IF NOT EXISTS`` (and a
full-schema migration diff that refuses additive migrations on a shared
multi-table DB), so a model that gained a field never got the column added to a
pre-existing table. This exercises the additive column-reconciliation wired into
the ensure/create flow: register a model WITHOUT a field, ``initialize()`` +
create a row, then register a model WITH a new plain ``extra: str`` field
against the SAME table, ``initialize()`` again, and assert the column now exists
AND accepts a value on the PRE-EXISTING table.

Behavioral (NO mocking, real infrastructure): the new column is proven by an
independent RAW read-back on BOTH PostgreSQL (port 5434) and file-backed SQLite.
The pre-existing row is asserted to survive with the new column NULL (additive,
non-destructive).

Run:
    TEST_DATABASE_URL="postgresql://test_user:test_password@localhost:5434/kailash_test" \
      ../../.venv/bin/python -m pytest \
      tests/regression/test_issue_1600_auto_migrate_alter_add.py \
      -p no:xdist -o "addopts=" -q --tb=short
"""

import os
import sqlite3
import uuid

import asyncpg
import pytest

from dataflow import DataFlow

PG_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql://test_user:test_password@localhost:5434/kailash_test",
)


# --------------------------------------------------------------------------
# Raw, dialect-aware read-back helpers (reflect COMMITTED state, bypass DataFlow).
# --------------------------------------------------------------------------
async def _pg_columns(url: str, table: str) -> set:
    conn = await asyncpg.connect(url)
    try:
        rows = await conn.fetch(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = $1 AND table_schema = current_schema()",
            table,
        )
        return {r["column_name"] for r in rows}
    finally:
        await conn.close()


async def _pg_fetch(url: str, table: str, rid: str):
    conn = await asyncpg.connect(url)
    try:
        row = await conn.fetchrow(f'SELECT * FROM "{table}" WHERE id = $1', rid)
        return dict(row) if row is not None else None
    finally:
        await conn.close()


async def _pg_drop(url: str, table: str) -> None:
    conn = await asyncpg.connect(url)
    try:
        await conn.execute(f'DROP TABLE IF EXISTS "{table}" CASCADE')
    finally:
        await conn.close()


def _sqlite_columns(path: str, table: str) -> set:
    conn = sqlite3.connect(path)
    try:
        cur = conn.execute(f'PRAGMA table_info("{table}")')
        return {row[1] for row in cur.fetchall()}
    finally:
        conn.close()


def _sqlite_fetch(path: str, table: str, rid: str):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.execute(f'SELECT * FROM "{table}" WHERE id = ?', (rid,))
        r = cur.fetchone()
        return dict(r) if r is not None else None
    finally:
        conn.close()


@pytest.mark.regression
@pytest.mark.integration
@pytest.mark.parametrize("dialect", ["postgresql", "sqlite"])
async def test_auto_migrate_alter_adds_new_plain_column_to_existing_table(
    dialect, tmp_path
):
    """A plain ``extra: str`` field added to a model whose table already exists
    is ALTER-ADDed to that pre-existing table (dialect-portable), and the column
    accepts a value; the pre-existing row survives with the new column NULL."""
    table = f"i1600_{uuid.uuid4().hex[:8]}"

    if dialect == "postgresql":
        url = PG_URL

        async def columns():
            return await _pg_columns(url, table)

        async def fetch(rid):
            return await _pg_fetch(url, table, rid)

    else:
        sqlite_path = os.path.join(tmp_path, f"i1600_{uuid.uuid4().hex}.db")
        url = f"sqlite:///{sqlite_path}"

        # SQLite readers are sync — wrap so the two branches share one call shape.
        async def columns():
            return _sqlite_columns(sqlite_path, table)

        async def fetch(rid):
            return _sqlite_fetch(sqlite_path, table, rid)

    try:
        # ---- V1: table WITHOUT the `extra` column ----
        db1 = DataFlow(url, auto_migrate=True)

        @db1.model
        class Widget1600V1:
            __tablename__ = table

            id: str
            name: str

        await db1.initialize()
        rid_legacy = f"legacy-{uuid.uuid4().hex[:8]}"
        await db1.express.create(
            "Widget1600V1", {"id": rid_legacy, "name": "legacy-widget"}
        )

        live_v1 = await columns()
        assert "extra" not in live_v1, "precondition: `extra` must not exist yet"
        assert "name" in live_v1
        await db1.express.close_async()

        # ---- V2: SAME table, model now declares `extra: str` ----
        db2 = DataFlow(url, auto_migrate=True)

        @db2.model
        class Widget1600V2:
            __tablename__ = table

            id: str
            name: str
            extra: str

        await db2.initialize()

        # The column must now physically exist on the PRE-EXISTING table.
        live_v2 = await columns()
        assert (
            "extra" in live_v2
        ), "auto-migrate must ALTER-ADD `extra` to the pre-existing table"

        # ...and it must ACCEPT a value (behavioral: write then raw read-back).
        rid_new = f"new-{uuid.uuid4().hex[:8]}"
        await db2.express.create(
            "Widget1600V2",
            {"id": rid_new, "name": "new-widget", "extra": "hello-1600"},
        )
        new_row = await fetch(rid_new)
        assert new_row is not None
        assert new_row["extra"] == "hello-1600", "new column must accept a value"

        # Additive / non-destructive: the pre-existing row survives, `extra` NULL.
        legacy_row = await fetch(rid_legacy)
        assert legacy_row is not None, "pre-existing row must survive the ALTER"
        assert legacy_row["name"] == "legacy-widget"
        assert (
            legacy_row["extra"] is None
        ), "existing rows get NULL for the added column"

        await db2.express.close_async()
    finally:
        if dialect == "postgresql":
            await _pg_drop(url, table)
        # sqlite: tmp_path file is discarded by pytest — no cleanup needed.

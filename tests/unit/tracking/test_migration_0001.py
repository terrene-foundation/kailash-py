# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 1 unit tests for migration 0001 — status vocabulary unification.

Uses real in-process SQLite (via :mod:`sqlite3`) rather than a mocked
connection so the test exercises the actual DDL / UPDATE / SELECT
path. The async adapter wraps ``sqlite3`` so the migration's
``await conn.execute(...)`` form works against the synchronous driver.

Migration 0002's Tier 2 integration tests (W4) will exercise real
PostgreSQL + real async SQLite.
"""
from __future__ import annotations

import importlib
import sqlite3
from typing import Any

import pytest

from kailash.db.dialect import DatabaseType
from kailash.ml.errors import MLError
from kailash.tracking.migrations._base import STATUS_ALIASES_LEGACY, STATUS_ENUM_1_0

# Numbered-migration module cannot be imported via normal attribute
# syntax (``0001_*`` is not a valid Python identifier) — use
# importlib.
_migration_module = importlib.import_module(
    "kailash.tracking.migrations.0001_status_vocabulary_finished"
)
Migration = _migration_module.Migration
DowngradeRefusedError = _migration_module.DowngradeRefusedError


class _SqliteConnAdapter:
    """Async-looking sync wrapper around :class:`sqlite3.Connection`.

    Implements the minimal shape ``MigrationBase.apply`` expects:
    ``.execute(sql)`` returning a cursor, ``.database_type`` providing
    the dialect hint. Not a full async-engine — synchronous calls
    short-circuit the ``if hasattr(result, "__await__")`` branch in
    the migration's helpers so the same code path works against both.
    """

    def __init__(self) -> None:
        self._conn = sqlite3.connect(":memory:")
        self._conn.row_factory = sqlite3.Row
        self.database_type = DatabaseType.SQLITE

    def execute(self, sql: str):
        return self._conn.execute(sql)

    def close(self) -> None:
        self._conn.close()


@pytest.fixture
def conn():
    c = _SqliteConnAdapter()
    c.execute("CREATE TABLE _kml_runs (run_id TEXT PRIMARY KEY, status TEXT NOT NULL)")
    yield c
    c.close()


# --- Enum + literal invariants --------------------------------------


def test_status_enum_1_0_is_four_members():
    assert STATUS_ENUM_1_0 == frozenset({"RUNNING", "FINISHED", "FAILED", "KILLED"})
    assert len(STATUS_ENUM_1_0) == 4


def test_status_aliases_legacy_includes_completed_and_success():
    assert STATUS_ALIASES_LEGACY == frozenset({"COMPLETED", "SUCCESS"})


def test_legacy_aliases_never_overlap_with_1_0_enum():
    assert STATUS_ALIASES_LEGACY.isdisjoint(STATUS_ENUM_1_0)


# --- Apply: happy path ----------------------------------------------


@pytest.mark.asyncio
async def test_apply_rewrites_completed_to_finished(conn):
    conn.execute("INSERT INTO _kml_runs VALUES ('r1', 'COMPLETED')")
    conn.execute("INSERT INTO _kml_runs VALUES ('r2', 'SUCCESS')")
    conn.execute("INSERT INTO _kml_runs VALUES ('r3', 'RUNNING')")

    m = Migration()
    result = await m.apply(conn)

    assert result.rows_migrated == 2
    assert result.direction == "upgrade"
    assert result.was_dry_run is False

    rows = {
        r["run_id"]: r["status"]
        for r in conn.execute("SELECT * FROM _kml_runs").fetchall()
    }
    assert rows["r1"] == "FINISHED"
    assert rows["r2"] == "FINISHED"
    assert rows["r3"] == "RUNNING"  # unchanged


@pytest.mark.asyncio
async def test_apply_preserves_prior_state_in_parking_table(conn):
    conn.execute("INSERT INTO _kml_runs VALUES ('r1', 'COMPLETED')")
    conn.execute("INSERT INTO _kml_runs VALUES ('r2', 'SUCCESS')")

    m = Migration()
    await m.apply(conn)

    parked = conn.execute(
        "SELECT run_id, old_status FROM _kml_migration_0001_prior_status ORDER BY run_id"
    ).fetchall()
    assert [(r["run_id"], r["old_status"]) for r in parked] == [
        ("r1", "COMPLETED"),
        ("r2", "SUCCESS"),
    ]


@pytest.mark.asyncio
async def test_apply_is_idempotent(conn):
    conn.execute("INSERT INTO _kml_runs VALUES ('r1', 'COMPLETED')")
    m = Migration()
    r1 = await m.apply(conn)
    r2 = await m.apply(conn)
    assert r1.rows_migrated == 1
    assert r2.rows_migrated == 0  # second run is a no-op
    assert "already applied" in r2.notes


@pytest.mark.asyncio
async def test_apply_dry_run_counts_without_writing(conn):
    conn.execute("INSERT INTO _kml_runs VALUES ('r1', 'COMPLETED')")
    conn.execute("INSERT INTO _kml_runs VALUES ('r2', 'SUCCESS')")

    m = Migration()
    result = await m.apply(conn, dry_run=True)

    assert result.rows_migrated == 2
    assert result.was_dry_run is True
    # No rewrite should have happened
    rows = {
        r["run_id"]: r["status"]
        for r in conn.execute("SELECT * FROM _kml_runs").fetchall()
    }
    assert rows["r1"] == "COMPLETED"
    assert rows["r2"] == "SUCCESS"


# --- Rollback -------------------------------------------------------


@pytest.mark.asyncio
async def test_rollback_refuses_without_force_flag(conn):
    conn.execute("INSERT INTO _kml_runs VALUES ('r1', 'COMPLETED')")
    m = Migration()
    await m.apply(conn)

    with pytest.raises(DowngradeRefusedError) as exc:
        await m.rollback(conn)
    assert "force_downgrade" in exc.value.reason
    # DowngradeRefusedError is an MLError (cross-cutting) per
    # dataflow-identifier-safety.md Rule 6 layer distinction.
    assert isinstance(exc.value, MLError)


@pytest.mark.asyncio
async def test_rollback_with_force_restores_legacy_aliases(conn):
    conn.execute("INSERT INTO _kml_runs VALUES ('r1', 'COMPLETED')")
    conn.execute("INSERT INTO _kml_runs VALUES ('r2', 'SUCCESS')")
    conn.execute("INSERT INTO _kml_runs VALUES ('r3', 'FINISHED')")  # already 1.0

    m = Migration()
    await m.apply(conn)

    result = await m.rollback(conn, force_downgrade=True)
    assert result.direction == "downgrade"
    assert result.rows_migrated == 2

    rows = {
        r["run_id"]: r["status"]
        for r in conn.execute("SELECT * FROM _kml_runs").fetchall()
    }
    assert rows["r1"] == "COMPLETED"
    assert rows["r2"] == "SUCCESS"
    assert rows["r3"] == "FINISHED"  # was not in parking, stays 1.0


# --- Verify ---------------------------------------------------------


@pytest.mark.asyncio
async def test_verify_false_when_legacy_rows_present(conn):
    conn.execute("INSERT INTO _kml_runs VALUES ('r1', 'COMPLETED')")
    m = Migration()
    assert await m.verify(conn) is False


@pytest.mark.asyncio
async def test_verify_true_when_no_legacy_rows(conn):
    conn.execute("INSERT INTO _kml_runs VALUES ('r1', 'RUNNING')")
    m = Migration()
    assert await m.verify(conn) is True


@pytest.mark.asyncio
async def test_verify_true_after_apply(conn):
    conn.execute("INSERT INTO _kml_runs VALUES ('r1', 'COMPLETED')")
    m = Migration()
    assert await m.verify(conn) is False
    await m.apply(conn)
    assert await m.verify(conn) is True


@pytest.mark.asyncio
async def test_verify_false_when_table_missing_returns_false():
    """If _kml_runs does not exist yet, verify returns False so the
    apply() call still runs once the schema is in place."""
    c = _SqliteConnAdapter()  # no CREATE TABLE
    m = Migration()
    try:
        assert await m.verify(c) is False
    finally:
        c.close()


# --- Class attributes -----------------------------------------------


def test_migration_class_attributes():
    m = Migration()
    assert m.version == "1.0.0"
    assert m.name == "status_vocabulary_finished"

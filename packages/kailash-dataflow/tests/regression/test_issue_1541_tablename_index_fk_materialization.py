# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression tests for issue #1541 — ``auto_migrate`` ignored ``__tablename__``
when generating CREATE INDEX and ADD FOREIGN KEY DDL.

Before #1541, a model with a custom ``__tablename__`` (differing from the
pluralized class-name default) had its CREATE TABLE emitted against the
resolved table (``_generate_create_table_sql`` reads
``model_info["table_name"]``, which honors ``__tablename__``), but its declared
indexes and foreign-key constraints emitted against the DEFAULT pluralized name
(``_generate_indexes_sql`` / ``_generate_foreign_key_constraints_sql`` used
``_class_name_to_table_name(model_name)``). The declared ``CREATE INDEX ... ON
<default_name>`` and ``ALTER TABLE <default_name> ADD CONSTRAINT ...`` targeted a
table that does NOT exist — the DDL was silently WARN-skipped (index/FK
failures continue under legacy semantics), so the index/constraint never
materialized on the real (``__tablename__``) table.

The fix routes both generators through ``_get_table_name(model_name)`` (which
returns ``model_info["table_name"]`` when present, else the class-name default),
matching CREATE TABLE. Both keep the pre-existing ``_validate_id`` /
``_validate_identifier(table_name)`` guards (rules/dataflow-identifier-safety.md
MUST-1) so the resolved value still flows through the identifier allowlist.

Trigger path: ``create_tables_async()`` →  ``_execute_ddl_async`` →
``generate_complete_schema_sql`` → ``_generate_indexes_sql`` +
``_generate_foreign_key_constraints_sql`` — the DataFlow API that emits the
exact index/FK DDL the bug is about (the same generators the
``auto_migrate=True`` init / express-lazy table-creation batch path invokes for
indexes). Assertions query the real catalog (SQLite ``sqlite_master`` /
PostgreSQL ``pg_indexes`` + ``pg_constraint``), NOT source text.

RED→GREEN proven: with the two ``_get_table_name`` swaps reverted to
``_class_name_to_table_name`` in engine.py, the declared index is ABSENT on the
``__tablename__`` table (SQLite: only the ``id`` PK auto-index remains) and the
FK ALTER targets the wrong default name — the tests below fail. Restoring the
fix makes them pass.

Permanent regression tests — NEVER delete (``rules/testing.md`` Regression).
"""

from __future__ import annotations

import shutil
import sqlite3  # out-of-band catalog read only (sqlite_master); #1502 precedent
import tempfile
import uuid

import pytest

from dataflow import DataFlow

# ---------------------------------------------------------------------------
# Model shapes shared by the SQLite + PostgreSQL cases. The custom
# ``__tablename__`` values are deliberately DISTINCT from the pluralized
# class-name default (``issue1541_widgets`` / ``issue1541_categorys``) so a
# generator that ignores ``__tablename__`` targets a non-existent table.
# ---------------------------------------------------------------------------
_WIDGET_TABLE = "issue1541_widget_table"
_CATEGORY_TABLE = "issue1541_category_table"
_INDEX_NAME = "idx_issue1541_widget_sku"


def _register_models(db: DataFlow) -> tuple[str, str]:
    """Register the parent (Category) + child (Widget) models on ``db``.

    Returns (widget_default_name, category_default_name) — the pluralized
    class-name defaults the pre-fix generators wrongly targeted.
    """

    @db.model
    class Issue1541Category:
        id: str
        name: str
        __tablename__ = _CATEGORY_TABLE

    @db.model
    class Issue1541Widget:
        id: str
        category_id: str
        sku: str
        name: str
        __tablename__ = _WIDGET_TABLE
        # At least one declared index, at least one unique.
        __dataflow__ = {
            "indexes": [{"name": _INDEX_NAME, "fields": ["sku"], "unique": True}]
        }

    # Register a belongs_to relationship in the real registry the FK generator
    # reads. ``get_relationships("Issue1541Widget")`` looks up
    # ``_class_name_to_table_name("Issue1541Widget")`` (the DEFAULT name) as the
    # internal dict key — store under the SAME key so the lookup finds it. The
    # ``target_table`` is the parent's resolved (``__tablename__``) table.
    widget_key = db._class_name_to_table_name("Issue1541Widget")
    if not hasattr(db, "_relationships"):
        db._relationships = {}
    db._relationships[widget_key] = {
        "category": {
            "type": "belongs_to",
            "foreign_key": "category_id",
            "target_table": _CATEGORY_TABLE,
            "target_key": "id",
        }
    }
    return (
        widget_key,
        db._class_name_to_table_name("Issue1541Category"),
    )


# ---------------------------------------------------------------------------
# Tier-2: file-backed SQLite (NOT :memory: — DataFlow's migration pool opens
# multiple short-lived connections; :memory: gives each an isolated DB).
# ---------------------------------------------------------------------------
@pytest.mark.regression
@pytest.mark.integration
async def test_sqlite_declared_index_materializes_on_tablename_table():
    """AC1 (SQLite, the core index proof): the declared UNIQUE index lands on
    the ``__tablename__`` table, NOT the pluralized class-name default. Pre-fix
    the ``CREATE INDEX ... ON issue1541_widgets`` targeted a non-existent table
    and was silently skipped, so the index never materialized."""
    tmpdir = tempfile.mkdtemp(prefix="issue1541_sqlite_")
    path = f"{tmpdir}/test.db"
    db = DataFlow(f"sqlite:///{path}", auto_migrate=True)
    widget_default, _ = _register_models(db)

    try:
        # Emit CREATE TABLE + CREATE INDEX (+ FK, no-op on SQLite) DDL.
        await db.create_tables_async()

        # Ground-truth catalog read on a fresh raw connection (committed state,
        # independent of DataFlow's schema cache) — #1502 precedent.
        raw = sqlite3.connect(path)
        try:
            index_rows = raw.execute(
                "SELECT name FROM sqlite_master " "WHERE type='index' AND tbl_name=?",
                (_WIDGET_TABLE,),
            ).fetchall()
            index_names = {r[0] for r in index_rows}

            tables = {
                r[0]
                for r in raw.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
        finally:
            raw.close()

        # The declared index exists ON the __tablename__ table (GREEN). Pre-fix
        # this set lacks _INDEX_NAME → assertion fails (RED).
        assert _INDEX_NAME in index_names, (
            f"declared index {_INDEX_NAME!r} absent on {_WIDGET_TABLE!r}; "
            f"found {index_names} (pre-fix: index targeted the non-existent "
            f"default table {widget_default!r} and was silently skipped)"
        )
        # The real table exists; the pluralized default name never does.
        assert _WIDGET_TABLE in tables, tables
        assert (
            widget_default not in tables
        ), f"default-named table {widget_default!r} should never exist: {tables}"
    finally:
        await db.close_async()
        shutil.rmtree(tmpdir, ignore_errors=True)


@pytest.mark.regression
@pytest.mark.integration
async def test_sqlite_fk_alter_targets_tablename_table():
    """AC2 (FK owning-table resolution, portable): the generated ADD FOREIGN KEY
    ALTER names the ``__tablename__`` table as the owning table, not the
    pluralized default. SQLite cannot ``ALTER TABLE ADD CONSTRAINT`` a foreign
    key, so this asserts the generator output directly (a behavioral call into
    the real ``_generate_foreign_key_constraints_sql``); the PostgreSQL case
    below proves the constraint materializes in the live catalog."""
    tmpdir = tempfile.mkdtemp(prefix="issue1541_sqlite_fk_")
    path = f"{tmpdir}/test.db"
    db = DataFlow(f"sqlite:///{path}", auto_migrate=True)
    widget_default, _ = _register_models(db)

    try:
        fk_sql = db._generate_foreign_key_constraints_sql("Issue1541Widget", "sqlite")
        assert len(fk_sql) == 1, fk_sql
        stmt = fk_sql[0]
        # The owning table of the ALTER is the __tablename__ table (GREEN).
        assert f"ALTER TABLE {_WIDGET_TABLE} " in stmt, stmt
        assert f"REFERENCES {_CATEGORY_TABLE}(" in stmt, stmt
        # Pre-fix the owning table was the pluralized default (RED).
        assert f"ALTER TABLE {widget_default} " not in stmt, stmt
    finally:
        await db.close_async()
        shutil.rmtree(tmpdir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Tier-2: real PostgreSQL (shared infra, port 5434 via IntegrationTestSuite).
# Migration DDL runs on real PG per schema-migration.md Rule 5.
# ---------------------------------------------------------------------------
@pytest.fixture
async def test_suite():
    """Real PostgreSQL integration suite (shared infra, port 5434)."""
    from tests.infrastructure.test_harness import IntegrationTestSuite

    suite = IntegrationTestSuite()
    async with suite.session():
        yield suite


@pytest.mark.regression
@pytest.mark.integration
@pytest.mark.requires_postgres
@pytest.mark.postgresql
async def test_postgres_index_and_fk_materialize_on_tablename_table(test_suite):
    """AC3 (PostgreSQL, authoritative catalog proof): after ``create_tables_async``
    the declared index appears in ``pg_indexes`` for the ``__tablename__`` table
    AND the foreign-key constraint appears in ``pg_constraint`` with the
    ``__tablename__`` table as the constrained relation. Pre-fix both DDL
    statements targeted the non-existent pluralized default and were skipped, so
    neither the index nor the constraint materialized on the real table."""
    db_url = test_suite.config.url

    # Drop leftovers from a prior run (child first — FK dependency).
    async with test_suite.get_connection() as conn:
        await conn.execute(f"DROP TABLE IF EXISTS {_WIDGET_TABLE} CASCADE")
        await conn.execute(f"DROP TABLE IF EXISTS {_CATEGORY_TABLE} CASCADE")

    db = DataFlow(db_url, auto_migrate=True)
    widget_default, _ = _register_models(db)

    try:
        await db.create_tables_async()

        async with test_suite.get_connection() as conn:
            # Index on the __tablename__ table (GREEN); pre-fix: absent.
            idx_rows = await conn.fetch(
                "SELECT indexname FROM pg_indexes WHERE tablename = $1",
                _WIDGET_TABLE,
            )
            idx_names = {r["indexname"] for r in idx_rows}

            # FK constraint whose constrained relation is the __tablename__
            # table (pg_constraint.contype='f'); pre-fix: absent (the ALTER
            # targeted the non-existent default and was skipped).
            fk_rows = await conn.fetch(
                """
                SELECT c.conname, tgt.relname AS target_table
                FROM pg_constraint c
                JOIN pg_class own ON own.oid = c.conrelid
                LEFT JOIN pg_class tgt ON tgt.oid = c.confrelid
                WHERE c.contype = 'f' AND own.relname = $1
                """,
                _WIDGET_TABLE,
            )

            # No index/constraint leaked onto the (never-created) default table.
            default_idx = await conn.fetch(
                "SELECT indexname FROM pg_indexes WHERE tablename = $1",
                widget_default,
            )

        assert _INDEX_NAME in idx_names, (
            f"declared index {_INDEX_NAME!r} absent from pg_indexes for "
            f"{_WIDGET_TABLE!r}; found {idx_names}"
        )
        assert len(fk_rows) >= 1, (
            f"no FK constraint on {_WIDGET_TABLE!r} in pg_constraint "
            f"(pre-fix the ALTER targeted {widget_default!r})"
        )
        assert any(r["target_table"] == _CATEGORY_TABLE for r in fk_rows), (
            f"FK on {_WIDGET_TABLE!r} does not reference {_CATEGORY_TABLE!r}: "
            f"{[dict(r) for r in fk_rows]}"
        )
        assert not default_idx, (
            f"index leaked onto default-named table {widget_default!r}: "
            f"{[r['indexname'] for r in default_idx]}"
        )
    finally:
        async with test_suite.get_connection() as conn:
            await conn.execute(f"DROP TABLE IF EXISTS {_WIDGET_TABLE} CASCADE")
            await conn.execute(f"DROP TABLE IF EXISTS {_CATEGORY_TABLE} CASCADE")
        await db.close_async()

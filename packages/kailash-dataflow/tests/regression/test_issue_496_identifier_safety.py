# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression tests for #496 audit findings — identifier safety in DDL paths.

Audit `workspaces/issues-492-497/04-validate/496-pg-placeholder-audit.md`
surfaced two `dataflow-identifier-safety.md` MUST 1 gaps in the migration
path:

1. ``sync_ddl_executor.SyncDDLExecutor.get_table_columns`` — SQLite branch
   interpolated ``table_name`` raw into ``PRAGMA table_info(...)``.
2. ``DataFlow._generate_migration_sql`` — ``table_name`` / ``column_name``
   / ``new_type`` were interpolated raw into ALTER TABLE ADD/DROP/MODIFY
   COLUMN strings. ``new_type`` originated from migration metadata which
   may be caller-influenced.

Both paths were patched to validate every dynamic identifier through
``kailash.db.dialect._validate_identifier`` before interpolation, plus a
conservative SQL-type pattern allowlist for ``new_type``.
"""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.regression]


# ---------------------------------------------------------------------------
# sync_ddl_executor.get_table_columns SQLite PRAGMA path
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad_identifier",
    [
        "users); DROP TABLE x; --",
        "table with spaces",
        "123_starts_with_digit",
        '" UNION SELECT * FROM secrets --',
    ],
)
def test_sync_ddl_executor_pragma_rejects_invalid_identifiers(tmp_path, bad_identifier):
    """Issue #496 audit gap: PRAGMA table_info({name}) MUST validate name.

    Constructs a SyncDDLExecutor against a file-backed SQLite database so
    the validator runs against the real SQLite branch. The validator is
    expected to raise BEFORE any cursor.execute() call is made, so the
    bogus PRAGMA never reaches the database.
    """
    from dataflow.migrations.sync_ddl_executor import SyncDDLExecutor

    ex = SyncDDLExecutor(f"sqlite:///{tmp_path}/dbg.db")
    assert ex._db_type == "sqlite"
    with pytest.raises(ValueError, match="Invalid SQL identifier"):
        ex.get_table_columns(bad_identifier)


# ---------------------------------------------------------------------------
# engine._generate_migration_sql ALTER TABLE paths
# ---------------------------------------------------------------------------


@pytest.fixture
def df_engine(tmp_path):
    """Real DataFlow engine over file-backed SQLite — no fixtures harness."""
    from dataflow import DataFlow

    db = DataFlow(f"sqlite:///{tmp_path}/dbg.db")
    yield db
    try:
        db.close()
    except Exception:  # nosec: cleanup-only
        pass


class _Op:
    """Minimal stand-in for MigrationOperation."""

    def __init__(self, operation_type: str, **details):
        self.operation_type = operation_type
        self.details = details


@pytest.mark.parametrize("bad_table", ['users"; DROP TABLE x; --', "name with spaces"])
def test_generate_migration_sql_rejects_bad_table_name(df_engine, bad_table):
    op = _Op("ADD_COLUMN", column_name="email")
    with pytest.raises(ValueError, match="Invalid SQL identifier"):
        df_engine._generate_migration_sql(op, bad_table, "postgresql")


def test_generate_migration_sql_rejects_bad_column_name(df_engine):
    op = _Op("DROP_COLUMN", column_name='email"; DROP')
    with pytest.raises(ValueError, match="Invalid SQL identifier"):
        df_engine._generate_migration_sql(op, "users", "postgresql")


def test_generate_migration_sql_rejects_bad_new_type(df_engine):
    op = _Op(
        "MODIFY_COLUMN",
        column_name="email",
        changes={"new_type": "TEXT; DROP TABLE x; --"},
    )
    with pytest.raises(ValueError, match="Invalid SQL type"):
        df_engine._generate_migration_sql(op, "users", "postgresql")


@pytest.mark.parametrize(
    "good_type",
    [
        "VARCHAR(255)",
        "NUMERIC(10,2)",
        "JSONB",
        "INTEGER",
        "BIGINT",
    ],
)
def test_generate_migration_sql_accepts_normal_types(df_engine, good_type):
    """Allowlist regex MUST accept the common SQL type tokens DataFlow emits."""
    op = _Op(
        "MODIFY_COLUMN",
        column_name="email",
        changes={"new_type": good_type},
    )
    sql = df_engine._generate_migration_sql(op, "users", "postgresql")
    assert "ALTER TABLE users" in sql
    assert good_type in sql
    assert "DROP" not in sql

# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression tests for issue #1559 — the legacy ``AutoMigrationSystem`` emitted
Postgres-only DDL on MySQL.

``AutoMigrationSystem._detect_database_type`` never returned ``"mysql"``: a
``mysql://`` URL fell through the ``"://" -> postgresql`` default, so
``self.dialect`` became ``"postgresql"`` even when the caller passed
``dialect="mysql"``. When the enhanced-schema path fell back to this legacy
migration system on MySQL, ``_ensure_migration_table`` emitted Postgres-only DDL
(``TIMESTAMP WITH TIME ZONE``, ``JSONB``, ``USING GIN``, and a partial unique
index ``WHERE status = 'applied'``) → MySQL error 1064, and
``_load_migration_history`` validated with a ``table_schema = 'public'`` filter
that matches nothing on MySQL → a spurious "missing required column" error.

These tests exercise the legacy migration system END-TO-END against the real
MySQL 8.0.46 container (``tests/CLAUDE.md`` Tier-2, NO mocking): the migration
table is created with zero 1064 error and its history loads cleanly.

Permanent regression tests — NEVER delete (``rules/testing.md`` Regression).
"""

from __future__ import annotations

import os
import tempfile
import time

import pytest

from dataflow import DataFlow
from dataflow.migrations.auto_migration_system import AutoMigrationSystem

MYSQL_URL = os.getenv(
    "TEST_MYSQL_URL", "mysql://kailash_test:test_password@localhost:3307/kailash_test"
)


def _raw_conn():
    import pymysql

    return pymysql.connect(
        host="localhost",
        port=3307,
        user="kailash_test",
        password="test_password",
        database="kailash_test",
    )


# ---------------------------------------------------------------------------
# Tier-1: dialect detection + MySQL DDL shape (no DB)
# ---------------------------------------------------------------------------
@pytest.mark.regression
def test_detect_database_type_returns_mysql_for_mysql_urls():
    """AC (root cause): every MySQL URL variant resolves to ``"mysql"`` — before
    #1559 they all fell through to ``"postgresql"``."""
    ams = AutoMigrationSystem.__new__(AutoMigrationSystem)
    for url in (
        "mysql://user:pass@localhost:3306/db",
        "mysql+pymysql://user:pass@localhost:3306/db",
        "mysql+aiomysql://user:pass@localhost:3307/db",
        "MySQL://user:pass@host/db",
    ):
        assert ams._detect_database_type(url) == "mysql", url
    # Sibling dialects unaffected.
    assert ams._detect_database_type("postgresql://u:p@h/d") == "postgresql"
    assert ams._detect_database_type("sqlite:///x.db") == "sqlite"


@pytest.mark.regression
def test_mysql_migration_ddl_has_no_postgres_only_constructs():
    """AC (dialect-portable DDL): the MySQL migration-table DDL MUST be free of the
    Postgres-only constructs that cause MySQL error 1064 (``infrastructure-sql.md``).
    Pins the fix so a future refactor cannot reintroduce them."""
    ams = AutoMigrationSystem.__new__(AutoMigrationSystem)
    ddl = "\n".join(ams._get_mysql_migration_table_statements()).upper()
    assert "TIMESTAMP WITH TIME ZONE" not in ddl
    assert "JSONB" not in ddl
    assert "USING GIN" not in ddl
    # No partial-index predicate (MySQL has no ``WHERE`` on indexes).
    assert "WHERE STATUS" not in ddl
    # No ``CREATE INDEX IF NOT EXISTS`` (unsupported on MySQL) — indexes are inline.
    assert "CREATE INDEX" not in ddl
    # MySQL-valid replacements ARE present.
    assert "DATETIME" in ddl
    assert "JSON" in ddl


# ---------------------------------------------------------------------------
# Tier-2: real MySQL 8.0.46 — legacy migration fallback creates the table
# ---------------------------------------------------------------------------
@pytest.mark.regression
@pytest.mark.integration
async def test_legacy_migration_system_creates_table_on_mysql():
    """AC (end-to-end): the legacy ``AutoMigrationSystem`` provisions its history
    table on real MySQL 8.0.46 with NO 1064 error, and the history loads cleanly.

    Before #1559 ``self.dialect`` was ``"postgresql"`` for a ``mysql://`` URL, so
    ``_ensure_migration_table`` raised 1064 (Postgres DDL) and, had it survived,
    ``_load_migration_history`` raised a spurious missing-column error (``public``
    schema filter matches nothing on MySQL)."""
    conn = _raw_conn()
    conn.cursor().execute("DROP TABLE IF EXISTS dataflow_migrations")
    conn.commit()

    # A parent DataFlow supplies the (sync) runtime the legacy system resolves
    # lazily; auto_migrate=False keeps this test scoped to the legacy path only.
    db = DataFlow(MYSQL_URL, auto_migrate=False)
    migrations_dir = tempfile.mkdtemp(prefix=f"df1559_{int(time.time())}_")
    ams = None

    try:
        ams = AutoMigrationSystem(
            connection_string=MYSQL_URL,
            dialect="mysql",
            migrations_dir=migrations_dir,
            dataflow_instance=db,
        )
        # Regression pin: dialect resolves to mysql (was "postgresql").
        assert ams.dialect == "mysql"
        assert ams.database_type == "mysql"

        # The buggy DDL path — must NOT raise MySQL 1064.
        await ams._ensure_migration_table()
        # The buggy validation path — must NOT raise "missing required column".
        await ams._load_migration_history()

        # Read-back: the history table exists with the MySQL-typed columns.
        cur = _raw_conn().cursor()
        cur.execute(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_name = 'dataflow_migrations' AND table_schema = DATABASE()"
        )
        cols = {name.lower(): dtype.lower() for name, dtype in cur.fetchall()}
        cur.connection.close()

        assert cols, "dataflow_migrations table was not created on MySQL"
        assert cols["applied_at"] == "datetime"  # NOT a Postgres timestamptz
        assert cols["operations"] == "json"  # NOT JSONB
        assert cols["created_at"] == "datetime"
        for required in ("version", "name", "checksum", "status"):
            assert required in cols, required
    finally:
        # AutoMigrationSystem has no close(); release its ConnectionManagerAdapter
        # runtime ref explicitly so it does not emit an Unclosed ResourceWarning.
        if ams is not None and ams._connection_adapter is not None:
            ams._connection_adapter.close()
        conn.cursor().execute("DROP TABLE IF EXISTS dataflow_migrations")
        conn.commit()
        conn.close()
        db.close()

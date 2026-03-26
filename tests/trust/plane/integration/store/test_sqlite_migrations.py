# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Tests for SqliteTrustPlaneStore schema versioning and migrations.

Validates:
- Fresh database receives schema_version = 1 in meta table
- Opening a future-version database raises SchemaTooNewError
- Migration runner applies versions in order
- Failed migration rolls back (database unchanged)
"""

from __future__ import annotations

import sqlite3
from unittest.mock import patch

import pytest

from kailash.trust.plane.exceptions import SchemaMigrationError, SchemaTooNewError
from kailash.trust.plane.store.sqlite import SCHEMA_VERSION, SqliteTrustPlaneStore


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db_path(tmp_path):
    """Return a path for a temporary SQLite database."""
    return tmp_path / "trust.db"


# ---------------------------------------------------------------------------
# Schema version on fresh database
# ---------------------------------------------------------------------------


class TestFreshDatabase:
    def test_fresh_database_has_schema_version(self, db_path):
        """A freshly initialized database must have schema_version = 1 in meta."""
        store = SqliteTrustPlaneStore(db_path)
        store.initialize()

        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT value FROM meta WHERE key = 'schema_version'"
        ).fetchone()
        conn.close()
        store.close()

        assert row is not None
        assert int(row["value"]) == SCHEMA_VERSION

    def test_fresh_database_creates_all_tables(self, db_path):
        """A freshly initialized database must have all expected tables."""
        store = SqliteTrustPlaneStore(db_path)
        store.initialize()

        conn = sqlite3.connect(str(db_path))
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = {row[0] for row in cursor.fetchall()}
        conn.close()
        store.close()

        expected = {
            "meta",
            "decisions",
            "milestones",
            "holds",
            "delegates",
            "reviews",
            "anchors",
            "manifest",
            "delegates_wal",
        }
        assert expected.issubset(tables)


# ---------------------------------------------------------------------------
# Future version rejection
# ---------------------------------------------------------------------------


class TestSchemaTooNew:
    def test_future_version_raises_error(self, db_path):
        """Opening a database with a future schema version must raise SchemaTooNewError."""
        # Create a database and stamp it with a future version
        conn = sqlite3.connect(str(db_path))
        conn.execute(
            "CREATE TABLE IF NOT EXISTS meta "
            "(key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        future_version = SCHEMA_VERSION + 10
        conn.execute(
            "INSERT INTO meta (key, value) VALUES ('schema_version', ?)",
            (str(future_version),),
        )
        conn.commit()
        conn.close()

        store = SqliteTrustPlaneStore(db_path)
        with pytest.raises(SchemaTooNewError) as exc_info:
            store.initialize()

        assert exc_info.value.db_version == future_version
        assert exc_info.value.current_version == SCHEMA_VERSION
        store.close()

    def test_current_version_does_not_raise(self, db_path):
        """Opening a database at current schema version must not raise."""
        store = SqliteTrustPlaneStore(db_path)
        store.initialize()
        store.close()

        # Re-open should work fine
        store2 = SqliteTrustPlaneStore(db_path)
        store2.initialize()
        store2.close()


# ---------------------------------------------------------------------------
# Migration runner
# ---------------------------------------------------------------------------


class TestMigrationRunner:
    def test_migrations_applied_in_order(self, db_path):
        """Migrations must be applied sequentially from old version to current."""
        applied_versions: list[int] = []

        def fake_migrate_v2(conn):
            applied_versions.append(2)

        def fake_migrate_v3(conn):
            applied_versions.append(3)

        fake_migrations = {
            2: fake_migrate_v2,
            3: fake_migrate_v3,
        }

        # Create a v1 database manually
        conn = sqlite3.connect(str(db_path))
        conn.execute(
            "CREATE TABLE IF NOT EXISTS meta "
            "(key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        conn.execute("INSERT INTO meta (key, value) VALUES ('schema_version', '1')")
        conn.commit()
        conn.close()

        store = SqliteTrustPlaneStore(db_path)

        # Patch SCHEMA_VERSION to 3 and MIGRATIONS to our fakes
        with (
            patch("kailash.trust.plane.store.sqlite.SCHEMA_VERSION", 3),
            patch("kailash.trust.plane.store.sqlite.MIGRATIONS", fake_migrations),
        ):
            store.initialize()

        store.close()

        assert applied_versions == [2, 3]

        # Verify final schema version is 3
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT value FROM meta WHERE key = 'schema_version'"
        ).fetchone()
        conn.close()
        assert int(row["value"]) == 3

    def test_failed_migration_rolls_back(self, db_path):
        """A failed migration must roll back; database stays at previous version."""

        def failing_migrate(conn):
            # Do some DDL that should be rolled back
            conn.execute("CREATE TABLE migration_test (id TEXT)")
            raise RuntimeError("Simulated migration failure")

        fake_migrations = {
            2: failing_migrate,
        }

        # Create a v1 database manually
        conn = sqlite3.connect(str(db_path))
        conn.execute(
            "CREATE TABLE IF NOT EXISTS meta "
            "(key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        conn.execute("INSERT INTO meta (key, value) VALUES ('schema_version', '1')")
        conn.commit()
        conn.close()

        store = SqliteTrustPlaneStore(db_path)

        with (
            patch("kailash.trust.plane.store.sqlite.SCHEMA_VERSION", 2),
            patch("kailash.trust.plane.store.sqlite.MIGRATIONS", fake_migrations),
        ):
            with pytest.raises(SchemaMigrationError) as exc_info:
                store.initialize()
            assert exc_info.value.target_version == 2

        store.close()

        # Verify schema version is still 1
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT value FROM meta WHERE key = 'schema_version'"
        ).fetchone()
        assert int(row["value"]) == 1

        # Verify the test table from the failed migration does not exist
        cursor = conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name='migration_test'"
        )
        assert cursor.fetchone() is None
        conn.close()

    def test_partial_migration_series_stops_at_failure(self, db_path):
        """When migration 2 succeeds but 3 fails, version is 2."""
        applied: list[int] = []

        def migrate_v2(conn):
            applied.append(2)

        def migrate_v3_fail(conn):
            raise RuntimeError("v3 failed")

        fake_migrations = {
            2: migrate_v2,
            3: migrate_v3_fail,
        }

        # Create a v1 database
        conn = sqlite3.connect(str(db_path))
        conn.execute(
            "CREATE TABLE IF NOT EXISTS meta "
            "(key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        conn.execute("INSERT INTO meta (key, value) VALUES ('schema_version', '1')")
        conn.commit()
        conn.close()

        store = SqliteTrustPlaneStore(db_path)

        with (
            patch("kailash.trust.plane.store.sqlite.SCHEMA_VERSION", 3),
            patch("kailash.trust.plane.store.sqlite.MIGRATIONS", fake_migrations),
        ):
            with pytest.raises(SchemaMigrationError) as exc_info:
                store.initialize()
            assert exc_info.value.target_version == 3

        store.close()

        assert applied == [2]

        # Version should be 2 (v2 succeeded, v3 rolled back)
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT value FROM meta WHERE key = 'schema_version'"
        ).fetchone()
        conn.close()
        assert int(row["value"]) == 2

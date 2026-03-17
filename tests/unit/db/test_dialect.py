# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for QueryDialect strategy pattern and dialect implementations.

Tests cover:
- DatabaseType enum values
- Placeholder generation for all 3 dialects
- translate_query() canonical ? -> dialect-specific conversion
- upsert() SQL generation for all 3 dialects
- json_column_type() for all 3 dialects
- json_extract() SQL generation for all 3 dialects
- for_update_skip_locked() for all 3 dialects
- timestamp_now() for all 3 dialects
- detect_dialect() URL detection for all schemes
- detect_dialect() error handling for unknown schemes
"""

from __future__ import annotations

import pytest

from kailash.db.dialect import (
    DatabaseType,
    MySQLDialect,
    PostgresDialect,
    QueryDialect,
    SQLiteDialect,
    detect_dialect,
)


# ---------------------------------------------------------------------------
# DatabaseType enum
# ---------------------------------------------------------------------------
class TestDatabaseType:
    def test_postgresql_value(self):
        assert DatabaseType.POSTGRESQL.value == "postgresql"

    def test_mysql_value(self):
        assert DatabaseType.MYSQL.value == "mysql"

    def test_sqlite_value(self):
        assert DatabaseType.SQLITE.value == "sqlite"

    def test_all_members(self):
        assert set(DatabaseType) == {
            DatabaseType.POSTGRESQL,
            DatabaseType.MYSQL,
            DatabaseType.SQLITE,
        }


# ---------------------------------------------------------------------------
# PostgresDialect
# ---------------------------------------------------------------------------
class TestPostgresDialect:
    @pytest.fixture()
    def dialect(self) -> PostgresDialect:
        return PostgresDialect()

    def test_is_query_dialect(self, dialect: PostgresDialect):
        assert isinstance(dialect, QueryDialect)

    def test_database_type(self, dialect: PostgresDialect):
        assert dialect.database_type == DatabaseType.POSTGRESQL

    # -- placeholder --
    def test_placeholder_index_0(self, dialect: PostgresDialect):
        assert dialect.placeholder(0) == "$1"

    def test_placeholder_index_4(self, dialect: PostgresDialect):
        assert dialect.placeholder(4) == "$5"

    def test_placeholder_index_99(self, dialect: PostgresDialect):
        assert dialect.placeholder(99) == "$100"

    # -- translate_query --
    def test_translate_query_single(self, dialect: PostgresDialect):
        result = dialect.translate_query("SELECT * FROM t WHERE id = ?")
        assert result == "SELECT * FROM t WHERE id = $1"

    def test_translate_query_multiple(self, dialect: PostgresDialect):
        result = dialect.translate_query("INSERT INTO t (a, b, c) VALUES (?, ?, ?)")
        assert result == "INSERT INTO t (a, b, c) VALUES ($1, $2, $3)"

    def test_translate_query_no_placeholders(self, dialect: PostgresDialect):
        result = dialect.translate_query("SELECT 1")
        assert result == "SELECT 1"

    def test_translate_query_preserves_question_in_strings(
        self, dialect: PostgresDialect
    ):
        """Placeholders outside of quoted strings should be translated."""
        # This tests basic replacement; string-interior ? handling is
        # a future enhancement -- for now, we translate all ? characters.
        result = dialect.translate_query("SELECT ? WHERE a = ?")
        assert result == "SELECT $1 WHERE a = $2"

    # -- upsert --
    def test_upsert_basic(self, dialect: PostgresDialect):
        sql, param_cols = dialect.upsert(
            table="users",
            columns=["id", "name", "email"],
            conflict_keys=["id"],
        )
        assert "INSERT INTO users" in sql
        assert "ON CONFLICT (id)" in sql
        assert "DO UPDATE SET" in sql
        # update_columns defaults to non-conflict columns
        assert "name" in sql
        assert "email" in sql
        assert param_cols == ["id", "name", "email"]

    def test_upsert_custom_update_columns(self, dialect: PostgresDialect):
        sql, param_cols = dialect.upsert(
            table="users",
            columns=["id", "name", "email"],
            conflict_keys=["id"],
            update_columns=["email"],
        )
        assert "DO UPDATE SET" in sql
        assert "email" in sql
        # name should NOT be in the UPDATE SET clause
        assert "SET name" not in sql
        assert param_cols == ["id", "name", "email"]

    def test_upsert_uses_dialect_placeholders(self, dialect: PostgresDialect):
        sql, _ = dialect.upsert(
            table="t",
            columns=["a", "b"],
            conflict_keys=["a"],
        )
        assert "$1" in sql
        assert "$2" in sql

    def test_upsert_multiple_conflict_keys(self, dialect: PostgresDialect):
        sql, _ = dialect.upsert(
            table="t",
            columns=["a", "b", "c"],
            conflict_keys=["a", "b"],
        )
        assert "ON CONFLICT (a, b)" in sql

    # -- json_column_type --
    def test_json_column_type(self, dialect: PostgresDialect):
        assert dialect.json_column_type() == "JSONB"

    # -- json_extract --
    def test_json_extract(self, dialect: PostgresDialect):
        result = dialect.json_extract("data", "name")
        assert result == "data->>'name'"

    def test_json_extract_different_column(self, dialect: PostgresDialect):
        result = dialect.json_extract("metadata", "version")
        assert result == "metadata->>'version'"

    # -- for_update_skip_locked --
    def test_for_update_skip_locked(self, dialect: PostgresDialect):
        result = dialect.for_update_skip_locked()
        assert result == "FOR UPDATE SKIP LOCKED"

    # -- timestamp_now --
    def test_timestamp_now(self, dialect: PostgresDialect):
        assert dialect.timestamp_now() == "NOW()"


# ---------------------------------------------------------------------------
# MySQLDialect
# ---------------------------------------------------------------------------
class TestMySQLDialect:
    @pytest.fixture()
    def dialect(self) -> MySQLDialect:
        return MySQLDialect()

    def test_is_query_dialect(self, dialect: MySQLDialect):
        assert isinstance(dialect, QueryDialect)

    def test_database_type(self, dialect: MySQLDialect):
        assert dialect.database_type == DatabaseType.MYSQL

    # -- placeholder --
    def test_placeholder_index_0(self, dialect: MySQLDialect):
        assert dialect.placeholder(0) == "%s"

    def test_placeholder_index_9(self, dialect: MySQLDialect):
        assert dialect.placeholder(9) == "%s"

    # -- translate_query --
    def test_translate_query_single(self, dialect: MySQLDialect):
        result = dialect.translate_query("SELECT * FROM t WHERE id = ?")
        assert result == "SELECT * FROM t WHERE id = %s"

    def test_translate_query_multiple(self, dialect: MySQLDialect):
        result = dialect.translate_query("INSERT INTO t (a, b) VALUES (?, ?)")
        assert result == "INSERT INTO t (a, b) VALUES (%s, %s)"

    def test_translate_query_no_placeholders(self, dialect: MySQLDialect):
        result = dialect.translate_query("SELECT 1")
        assert result == "SELECT 1"

    # -- upsert --
    def test_upsert_basic(self, dialect: MySQLDialect):
        sql, param_cols = dialect.upsert(
            table="users",
            columns=["id", "name", "email"],
            conflict_keys=["id"],
        )
        assert "INSERT INTO users" in sql
        assert "ON DUPLICATE KEY UPDATE" in sql
        assert "name" in sql
        assert "email" in sql
        assert param_cols == ["id", "name", "email"]

    def test_upsert_custom_update_columns(self, dialect: MySQLDialect):
        sql, param_cols = dialect.upsert(
            table="users",
            columns=["id", "name", "email"],
            conflict_keys=["id"],
            update_columns=["email"],
        )
        assert "ON DUPLICATE KEY UPDATE" in sql
        assert "email" in sql

    def test_upsert_uses_dialect_placeholders(self, dialect: MySQLDialect):
        sql, _ = dialect.upsert(
            table="t",
            columns=["a", "b"],
            conflict_keys=["a"],
        )
        assert "%s" in sql

    # -- json_column_type --
    def test_json_column_type(self, dialect: MySQLDialect):
        assert dialect.json_column_type() == "JSON"

    # -- json_extract --
    def test_json_extract(self, dialect: MySQLDialect):
        result = dialect.json_extract("data", "name")
        assert result == "JSON_EXTRACT(data, '$.name')"

    def test_json_extract_different_column(self, dialect: MySQLDialect):
        result = dialect.json_extract("metadata", "version")
        assert result == "JSON_EXTRACT(metadata, '$.version')"

    # -- for_update_skip_locked --
    def test_for_update_skip_locked(self, dialect: MySQLDialect):
        result = dialect.for_update_skip_locked()
        assert result == "FOR UPDATE SKIP LOCKED"

    # -- timestamp_now --
    def test_timestamp_now(self, dialect: MySQLDialect):
        assert dialect.timestamp_now() == "NOW()"


# ---------------------------------------------------------------------------
# SQLiteDialect
# ---------------------------------------------------------------------------
class TestSQLiteDialect:
    @pytest.fixture()
    def dialect(self) -> SQLiteDialect:
        return SQLiteDialect()

    def test_is_query_dialect(self, dialect: SQLiteDialect):
        assert isinstance(dialect, QueryDialect)

    def test_database_type(self, dialect: SQLiteDialect):
        assert dialect.database_type == DatabaseType.SQLITE

    # -- placeholder --
    def test_placeholder_index_0(self, dialect: SQLiteDialect):
        assert dialect.placeholder(0) == "?"

    def test_placeholder_index_5(self, dialect: SQLiteDialect):
        assert dialect.placeholder(5) == "?"

    # -- translate_query --
    def test_translate_query_single(self, dialect: SQLiteDialect):
        """SQLite uses ? natively, so translation is identity."""
        result = dialect.translate_query("SELECT * FROM t WHERE id = ?")
        assert result == "SELECT * FROM t WHERE id = ?"

    def test_translate_query_multiple(self, dialect: SQLiteDialect):
        result = dialect.translate_query("INSERT INTO t (a, b) VALUES (?, ?)")
        assert result == "INSERT INTO t (a, b) VALUES (?, ?)"

    # -- upsert --
    def test_upsert_basic(self, dialect: SQLiteDialect):
        sql, param_cols = dialect.upsert(
            table="users",
            columns=["id", "name", "email"],
            conflict_keys=["id"],
        )
        assert "INSERT INTO users" in sql
        assert "ON CONFLICT" in sql
        assert "DO UPDATE SET" in sql
        assert "name" in sql
        assert "email" in sql
        assert param_cols == ["id", "name", "email"]

    def test_upsert_custom_update_columns(self, dialect: SQLiteDialect):
        sql, param_cols = dialect.upsert(
            table="users",
            columns=["id", "name", "email"],
            conflict_keys=["id"],
            update_columns=["email"],
        )
        assert "DO UPDATE SET" in sql
        assert "email" in sql

    def test_upsert_uses_dialect_placeholders(self, dialect: SQLiteDialect):
        sql, _ = dialect.upsert(
            table="t",
            columns=["a", "b"],
            conflict_keys=["a"],
        )
        assert "?" in sql
        # Must NOT contain $1 or %s
        assert "$" not in sql
        assert "%s" not in sql

    # -- json_column_type --
    def test_json_column_type(self, dialect: SQLiteDialect):
        assert dialect.json_column_type() == "TEXT"

    # -- json_extract --
    def test_json_extract(self, dialect: SQLiteDialect):
        result = dialect.json_extract("data", "name")
        assert result == "json_extract(data, '$.name')"

    def test_json_extract_different_column(self, dialect: SQLiteDialect):
        result = dialect.json_extract("metadata", "version")
        assert result == "json_extract(metadata, '$.version')"

    # -- for_update_skip_locked --
    def test_for_update_skip_locked(self, dialect: SQLiteDialect):
        """SQLite does not support SKIP LOCKED; returns empty string."""
        result = dialect.for_update_skip_locked()
        assert result == ""

    # -- timestamp_now --
    def test_timestamp_now(self, dialect: SQLiteDialect):
        assert dialect.timestamp_now() == "datetime('now')"


# ---------------------------------------------------------------------------
# detect_dialect()
# ---------------------------------------------------------------------------
class TestDetectDialect:
    # PostgreSQL URLs
    def test_postgresql_url(self):
        d = detect_dialect("postgresql://user:pass@localhost:5432/db")
        assert isinstance(d, PostgresDialect)
        assert d.database_type == DatabaseType.POSTGRESQL

    def test_postgres_shorthand_url(self):
        d = detect_dialect("postgres://user:pass@localhost/db")
        assert isinstance(d, PostgresDialect)

    def test_postgresql_plus_asyncpg(self):
        d = detect_dialect("postgresql+asyncpg://localhost/db")
        assert isinstance(d, PostgresDialect)

    # MySQL URLs
    def test_mysql_url(self):
        d = detect_dialect("mysql://user:pass@localhost/db")
        assert isinstance(d, MySQLDialect)
        assert d.database_type == DatabaseType.MYSQL

    def test_mysql_plus_aiomysql(self):
        d = detect_dialect("mysql+aiomysql://localhost/db")
        assert isinstance(d, MySQLDialect)

    # SQLite URLs
    def test_sqlite_url(self):
        d = detect_dialect("sqlite:///path/to/db.sqlite3")
        assert isinstance(d, SQLiteDialect)
        assert d.database_type == DatabaseType.SQLITE

    def test_sqlite_memory_url(self):
        d = detect_dialect("sqlite:///:memory:")
        assert isinstance(d, SQLiteDialect)

    def test_file_path(self):
        """A plain file path defaults to SQLite."""
        d = detect_dialect("/tmp/mydb.sqlite3")
        assert isinstance(d, SQLiteDialect)

    def test_relative_path(self):
        d = detect_dialect("./data/local.db")
        assert isinstance(d, SQLiteDialect)

    def test_empty_string_raises(self):
        """Empty URL must raise ValueError, not silently default."""
        with pytest.raises(ValueError, match="[Dd]atabase URL"):
            detect_dialect("")

    def test_unknown_scheme_raises(self):
        """Unknown database scheme must raise ValueError with context."""
        with pytest.raises(ValueError, match="[Uu]nsupported"):
            detect_dialect("oracle://user:pass@host/db")

    def test_none_raises(self):
        """None is not a valid URL."""
        with pytest.raises((TypeError, ValueError)):
            detect_dialect(None)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# QueryDialect is abstract — cannot be instantiated directly
# ---------------------------------------------------------------------------
class TestQueryDialectABC:
    def test_cannot_instantiate_directly(self):
        with pytest.raises(TypeError):
            QueryDialect()  # type: ignore[abstract]

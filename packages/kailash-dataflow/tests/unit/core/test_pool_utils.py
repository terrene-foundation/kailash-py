# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
Unit tests for pool_utils.py — Milestone 1 (TODO-09).

Tests cover:
- detect_worker_count() with various env var combinations
- is_postgresql(), is_sqlite(), is_mysql() URL type detection
- probe_max_connections() behavior for different database types
"""

from __future__ import annotations

import logging
import os
from unittest.mock import MagicMock, patch

import pytest


class TestDetectWorkerCount:
    """Tests for detect_worker_count() — TODO-07."""

    def test_no_env_vars_returns_1(self, monkeypatch):
        """When no worker-related env vars are set, returns 1."""
        from dataflow.core.pool_utils import detect_worker_count

        # Clear all worker env vars
        for var in [
            "DATAFLOW_WORKER_COUNT",
            "KAILASH_WORKERS",
            "UVICORN_WORKERS",
            "WEB_CONCURRENCY",
            "GUNICORN_WORKERS",
        ]:
            monkeypatch.delenv(var, raising=False)

        assert detect_worker_count() == 1

    def test_dataflow_worker_count_takes_precedence(self, monkeypatch):
        """DATAFLOW_WORKER_COUNT is highest priority."""
        from dataflow.core.pool_utils import detect_worker_count

        monkeypatch.setenv("DATAFLOW_WORKER_COUNT", "4")
        monkeypatch.setenv("UVICORN_WORKERS", "8")
        monkeypatch.setenv("WEB_CONCURRENCY", "16")
        assert detect_worker_count() == 4

    def test_kailash_workers_second_priority(self, monkeypatch):
        """KAILASH_WORKERS is second priority (cross-SDK alignment)."""
        from dataflow.core.pool_utils import detect_worker_count

        monkeypatch.delenv("DATAFLOW_WORKER_COUNT", raising=False)
        monkeypatch.setenv("KAILASH_WORKERS", "3")
        monkeypatch.setenv("UVICORN_WORKERS", "8")
        assert detect_worker_count() == 3

    def test_uvicorn_workers(self, monkeypatch):
        """UVICORN_WORKERS is detected."""
        from dataflow.core.pool_utils import detect_worker_count

        for var in [
            "DATAFLOW_WORKER_COUNT",
            "KAILASH_WORKERS",
        ]:
            monkeypatch.delenv(var, raising=False)
        monkeypatch.setenv("UVICORN_WORKERS", "6")
        monkeypatch.delenv("WEB_CONCURRENCY", raising=False)
        monkeypatch.delenv("GUNICORN_WORKERS", raising=False)
        assert detect_worker_count() == 6

    def test_web_concurrency(self, monkeypatch):
        """WEB_CONCURRENCY is detected."""
        from dataflow.core.pool_utils import detect_worker_count

        for var in [
            "DATAFLOW_WORKER_COUNT",
            "KAILASH_WORKERS",
            "UVICORN_WORKERS",
        ]:
            monkeypatch.delenv(var, raising=False)
        monkeypatch.setenv("WEB_CONCURRENCY", "12")
        monkeypatch.delenv("GUNICORN_WORKERS", raising=False)
        assert detect_worker_count() == 12

    def test_gunicorn_workers(self, monkeypatch):
        """GUNICORN_WORKERS is detected as lowest priority."""
        from dataflow.core.pool_utils import detect_worker_count

        for var in [
            "DATAFLOW_WORKER_COUNT",
            "KAILASH_WORKERS",
            "UVICORN_WORKERS",
            "WEB_CONCURRENCY",
        ]:
            monkeypatch.delenv(var, raising=False)
        monkeypatch.setenv("GUNICORN_WORKERS", "2")
        assert detect_worker_count() == 2

    def test_invalid_value_returns_1(self, monkeypatch):
        """Non-numeric values are treated as absent, returns 1."""
        from dataflow.core.pool_utils import detect_worker_count

        for var in [
            "KAILASH_WORKERS",
            "UVICORN_WORKERS",
            "WEB_CONCURRENCY",
            "GUNICORN_WORKERS",
        ]:
            monkeypatch.delenv(var, raising=False)
        monkeypatch.setenv("DATAFLOW_WORKER_COUNT", "abc")
        assert detect_worker_count() == 1

    def test_zero_value_clamped_to_1(self, monkeypatch):
        """Zero is clamped to 1 (at least one worker)."""
        from dataflow.core.pool_utils import detect_worker_count

        for var in [
            "KAILASH_WORKERS",
            "UVICORN_WORKERS",
            "WEB_CONCURRENCY",
            "GUNICORN_WORKERS",
        ]:
            monkeypatch.delenv(var, raising=False)
        monkeypatch.setenv("DATAFLOW_WORKER_COUNT", "0")
        assert detect_worker_count() == 1

    def test_negative_value_clamped_to_1(self, monkeypatch):
        """Negative values are clamped to 1."""
        from dataflow.core.pool_utils import detect_worker_count

        for var in [
            "KAILASH_WORKERS",
            "UVICORN_WORKERS",
            "WEB_CONCURRENCY",
            "GUNICORN_WORKERS",
        ]:
            monkeypatch.delenv(var, raising=False)
        monkeypatch.setenv("DATAFLOW_WORKER_COUNT", "-5")
        assert detect_worker_count() == 1

    def test_empty_string_falls_through(self, monkeypatch):
        """Empty string is treated as absent, falls through to next var."""
        from dataflow.core.pool_utils import detect_worker_count

        monkeypatch.setenv("DATAFLOW_WORKER_COUNT", "")
        monkeypatch.setenv("KAILASH_WORKERS", "5")
        monkeypatch.delenv("UVICORN_WORKERS", raising=False)
        monkeypatch.delenv("WEB_CONCURRENCY", raising=False)
        monkeypatch.delenv("GUNICORN_WORKERS", raising=False)
        assert detect_worker_count() == 5

    def test_float_value_returns_1(self, monkeypatch):
        """Float values like '5.5' are non-integer, returns 1."""
        from dataflow.core.pool_utils import detect_worker_count

        for var in [
            "KAILASH_WORKERS",
            "UVICORN_WORKERS",
            "WEB_CONCURRENCY",
            "GUNICORN_WORKERS",
        ]:
            monkeypatch.delenv(var, raising=False)
        monkeypatch.setenv("DATAFLOW_WORKER_COUNT", "5.5")
        assert detect_worker_count() == 1


class TestIsPostgresql:
    """Tests for is_postgresql() — TODO-08."""

    def test_postgresql_scheme(self):
        from dataflow.core.pool_utils import is_postgresql

        assert is_postgresql("postgresql://user:pass@localhost/db") is True

    def test_postgres_scheme(self):
        from dataflow.core.pool_utils import is_postgresql

        assert is_postgresql("postgres://user:pass@localhost/db") is True

    def test_postgresql_asyncpg_scheme(self):
        from dataflow.core.pool_utils import is_postgresql

        assert is_postgresql("postgresql+asyncpg://user:pass@localhost/db") is True

    def test_postgresql_psycopg2_scheme(self):
        from dataflow.core.pool_utils import is_postgresql

        assert is_postgresql("postgresql+psycopg2://user:pass@localhost/db") is True

    def test_sqlite_is_not_postgresql(self):
        from dataflow.core.pool_utils import is_postgresql

        assert is_postgresql("sqlite:///test.db") is False

    def test_mysql_is_not_postgresql(self):
        from dataflow.core.pool_utils import is_postgresql

        assert is_postgresql("mysql://user:pass@localhost/db") is False

    def test_empty_string(self):
        from dataflow.core.pool_utils import is_postgresql

        assert is_postgresql("") is False

    def test_none_returns_false(self):
        from dataflow.core.pool_utils import is_postgresql

        assert is_postgresql(None) is False


class TestIsSqlite:
    """Tests for is_sqlite() — TODO-08."""

    def test_sqlite_memory(self):
        from dataflow.core.pool_utils import is_sqlite

        assert is_sqlite("sqlite:///:memory:") is True

    def test_sqlite_file(self):
        from dataflow.core.pool_utils import is_sqlite

        assert is_sqlite("sqlite:///path/to/db.sqlite") is True

    def test_sqlite_aiosqlite_scheme(self):
        from dataflow.core.pool_utils import is_sqlite

        assert is_sqlite("sqlite+aiosqlite:///path/to/db") is True

    def test_postgresql_is_not_sqlite(self):
        from dataflow.core.pool_utils import is_sqlite

        assert is_sqlite("postgresql://user:pass@localhost/db") is False

    def test_empty_string(self):
        from dataflow.core.pool_utils import is_sqlite

        assert is_sqlite("") is False

    def test_none_returns_false(self):
        from dataflow.core.pool_utils import is_sqlite

        assert is_sqlite(None) is False


class TestIsMysql:
    """Tests for is_mysql() — TODO-08."""

    def test_mysql_scheme(self):
        from dataflow.core.pool_utils import is_mysql

        assert is_mysql("mysql://user:pass@localhost/db") is True

    def test_mysql_pymysql_scheme(self):
        from dataflow.core.pool_utils import is_mysql

        assert is_mysql("mysql+pymysql://user:pass@localhost/db") is True

    def test_mysql_aiomysql_scheme(self):
        from dataflow.core.pool_utils import is_mysql

        assert is_mysql("mysql+aiomysql://user:pass@localhost/db") is True

    def test_postgresql_is_not_mysql(self):
        from dataflow.core.pool_utils import is_mysql

        assert is_mysql("postgresql://user:pass@localhost/db") is False

    def test_empty_string(self):
        from dataflow.core.pool_utils import is_mysql

        assert is_mysql("") is False

    def test_none_returns_false(self):
        from dataflow.core.pool_utils import is_mysql

        assert is_mysql(None) is False


class TestProbeMaxConnections:
    """Tests for probe_max_connections() — TODO-06."""

    def test_sqlite_returns_none(self):
        """SQLite has no max_connections concept."""
        from dataflow.core.pool_utils import probe_max_connections

        result = probe_max_connections("sqlite:///:memory:")
        assert result is None

    def test_empty_url_returns_none(self):
        """Empty URL returns None."""
        from dataflow.core.pool_utils import probe_max_connections

        result = probe_max_connections("")
        assert result is None

    def test_none_url_returns_none(self):
        """None URL returns None."""
        from dataflow.core.pool_utils import probe_max_connections

        result = probe_max_connections(None)
        assert result is None

    def test_postgresql_success_returns_int(self):
        """Mock a successful PostgreSQL probe returning max_connections."""
        from dataflow.core.pool_utils import probe_max_connections

        # Mock psycopg2 to simulate a successful connection
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = ("100",)
        mock_conn.cursor.return_value = mock_cursor
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)

        mock_psycopg2 = MagicMock()
        mock_psycopg2.connect.return_value = mock_conn

        with patch.dict("sys.modules", {"psycopg2": mock_psycopg2}):
            result = probe_max_connections("postgresql://user:pass@localhost/db")

        assert result == 100

    def test_postgresql_connection_failure_returns_none(self, caplog):
        """Connection failure returns None and logs WARNING."""
        from dataflow.core.pool_utils import probe_max_connections

        mock_psycopg2 = MagicMock()
        mock_psycopg2.connect.side_effect = Exception("Connection refused")

        with patch.dict("sys.modules", {"psycopg2": mock_psycopg2}):
            with caplog.at_level(logging.WARNING):
                result = probe_max_connections("postgresql://user:pass@localhost/db")

        assert result is None
        assert any(
            "probe" in record.message.lower()
            or "max_connections" in record.message.lower()
            for record in caplog.records
        )

    def test_mysql_success_returns_int(self):
        """Mock a successful MySQL probe returning max_connections."""
        from dataflow.core.pool_utils import probe_max_connections

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = ("max_connections", "151")
        mock_conn.cursor.return_value = mock_cursor
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)

        mock_pymysql = MagicMock()
        mock_pymysql.connect.return_value = mock_conn

        with patch.dict("sys.modules", {"pymysql": mock_pymysql}):
            result = probe_max_connections("mysql://user:pass@localhost/db")

        assert result == 151

    def test_no_driver_available_returns_none(self, caplog):
        """When database driver is not installed, returns None."""
        from dataflow.core.pool_utils import probe_max_connections

        # Ensure psycopg2 is not importable
        with patch.dict("sys.modules", {"psycopg2": None}):
            with caplog.at_level(logging.WARNING):
                result = probe_max_connections("postgresql://user:pass@localhost/db")

        assert result is None

    def test_unknown_database_type_returns_none(self):
        """Unknown database URL type returns None."""
        from dataflow.core.pool_utils import probe_max_connections

        result = probe_max_connections("oracle://user:pass@localhost/db")
        assert result is None

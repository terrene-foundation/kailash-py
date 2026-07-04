# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression tests for issue #1547 — MySQL model-registry raised
``ModuleNotFoundError: No module named 'MySQLdb'``.

The model registry executes its DDL/DML through ``SQLDatabaseNode``, which is
SQLAlchemy-SYNC. A bare ``mysql://`` connection URL makes SQLAlchemy default to
the ``mysqldb`` (mysqlclient) driver — which is NOT a DataFlow dependency — so
``auto_migrate`` on MySQL failed to create the ``dataflow_model_registry`` table
with ``ModuleNotFoundError: No module named 'MySQLdb'`` and logged registry
ERRORs. The registry's own sync DDL executor (``SyncDDLExecutor``) already used
``pymysql`` correctly; the fix mirrors it by normalizing every registry
connection URL's MySQL scheme to ``mysql+pymysql://``
(``core/model_registry.py::_ensure_sync_mysql_driver``).

Permanent regression tests — NEVER delete (``rules/testing.md`` Regression).
"""

from __future__ import annotations

import logging
import os
import time

import pytest

from dataflow import DataFlow
from dataflow.core.model_registry import _ensure_sync_mysql_driver

# Real MySQL 8.0 on port 3307 (compose: db kailash_test).
MYSQL_URL = os.getenv(
    "TEST_MYSQL_URL", "mysql://kailash_test:test_password@localhost:3307/kailash_test"
)


def _uid(prefix: str = "u") -> str:
    return f"{prefix}-{int(time.time() * 1_000_000)}"


def _registry_table_exists() -> bool:
    """Ground-truth existence check for ``dataflow_model_registry`` on a fresh
    ``pymysql`` connection (committed state), via information_schema.tables."""
    import pymysql

    conn = pymysql.connect(
        host="localhost",
        port=3307,
        user="kailash_test",
        password="test_password",
        database="kailash_test",
    )
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT COUNT(*) FROM information_schema.tables "
            "WHERE table_schema = DATABASE() "
            "AND table_name = 'dataflow_model_registry'"
        )
        return cur.fetchone()[0] == 1
    finally:
        conn.close()


class _CaptureHandler(logging.Handler):
    """Collect ERROR+ records emitted under the ``dataflow`` logger tree."""

    def __init__(self) -> None:
        super().__init__(level=logging.ERROR)
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


# ---------------------------------------------------------------------------
# Tier-2: real MySQL — auto_migrate creates the registry table cleanly
# ---------------------------------------------------------------------------
@pytest.mark.regression
@pytest.mark.integration
async def test_mysql_auto_migrate_creates_registry_table_no_mysqldb_error():
    """AC: auto_migrate on real MySQL creates ``dataflow_model_registry`` with NO
    ``MySQLdb`` ImportError and NO registry-logger ERROR records; the table
    persists (verified via information_schema.tables on a fresh connection)."""
    dataflow_logger = logging.getLogger("dataflow")
    handler = _CaptureHandler()
    prior_level = dataflow_logger.level
    dataflow_logger.addHandler(handler)
    dataflow_logger.setLevel(logging.ERROR)

    db = DataFlow(MYSQL_URL, auto_migrate=True)
    try:

        @db.model
        class Issue1547Registry:
            id: str
            name: str

        db._ensure_connected()

        messages = "\n".join(h.getMessage() for h in handler.records)
        # No MySQLdb ImportError surfaced anywhere in the dataflow logger tree.
        assert "MySQLdb" not in messages, messages
        # No registry-specific ERROR records.
        registry_errors = [
            h.getMessage()
            for h in handler.records
            if "registry" in (h.name + h.getMessage()).lower()
        ]
        assert registry_errors == [], registry_errors

        # The registry table persists on real MySQL.
        assert _registry_table_exists() is True
    finally:
        dataflow_logger.removeHandler(handler)
        dataflow_logger.setLevel(prior_level)
        db.close()


# ---------------------------------------------------------------------------
# Tier-1: structural pins on the driver-normalization helper (no DB)
# ---------------------------------------------------------------------------
@pytest.mark.regression
def test_ensure_sync_mysql_driver_rewrites_every_mysql_scheme():
    """Every non-pymysql MySQL scheme is pinned to ``mysql+pymysql://`` — bare
    ``mysql://`` (the #1547 trigger), the explicit sync ``mysql+mysqldb://``, and
    the async ``mysql+aiomysql://`` (unusable by the sync SQLDatabaseNode)."""
    assert (
        _ensure_sync_mysql_driver("mysql://u:p@h:3307/db")
        == "mysql+pymysql://u:p@h:3307/db"
    )
    assert (
        _ensure_sync_mysql_driver("mysql+mysqldb://u:p@h/db")
        == "mysql+pymysql://u:p@h/db"
    )
    assert (
        _ensure_sync_mysql_driver("mysql+aiomysql://u:p@h/db")
        == "mysql+pymysql://u:p@h/db"
    )


@pytest.mark.regression
def test_ensure_sync_mysql_driver_is_idempotent_and_noop_off_mysql():
    """Already-pymysql URLs are unchanged; sqlite / postgresql / the in-memory
    shared-cache ``file:`` URI pass through untouched (the ``or`` fallback in
    ``_registry_connection_url`` must keep those backends on their own driver)."""
    already = "mysql+pymysql://u:p@h/db"
    assert _ensure_sync_mysql_driver(already) == already

    for untouched in (
        "sqlite:///dev.db",
        "sqlite:///:memory:",
        "postgresql://u:p@h:5432/db",
        "file:df_mem_123?mode=memory&cache=shared",
    ):
        assert _ensure_sync_mysql_driver(untouched) == untouched


@pytest.mark.regression
def test_ensure_sync_mysql_driver_lowercases_scheme_preserves_userinfo():
    """Security hardening: the SCHEME is lowercased before matching, so mixed-case
    schemes (``MYSQL://``, ``mysql+MySQLdb://``) normalize too — while the
    userinfo/host/path remainder is preserved byte-for-byte (a password may legally
    contain uppercase)."""
    # Mixed-case scheme normalized; uppercase password/host preserved verbatim.
    assert (
        _ensure_sync_mysql_driver("MYSQL://User:PassWORD@Host:3307/DB")
        == "mysql+pymysql://User:PassWORD@Host:3307/DB"
    )
    assert (
        _ensure_sync_mysql_driver("mysql+MySQLdb://u:AbC123@h/db")
        == "mysql+pymysql://u:AbC123@h/db"
    )
    assert (
        _ensure_sync_mysql_driver("MySQL+AioMySQL://u:p@h/db")
        == "mysql+pymysql://u:p@h/db"
    )

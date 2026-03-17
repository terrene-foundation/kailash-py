# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Database dialect abstraction layer for Kailash SDK.

Provides a strategy pattern for cross-database SQL generation (PostgreSQL,
MySQL, SQLite) and an async ConnectionManager for query execution.

Usage::

    from kailash.db import detect_dialect, ConnectionManager, DatabaseType

    dialect = detect_dialect("postgresql://localhost/mydb")
    mgr = ConnectionManager("sqlite:///local.db")
    await mgr.initialize()
    rows = await mgr.fetch("SELECT * FROM users WHERE id = ?", 42)
"""

from __future__ import annotations

from kailash.db.connection import ConnectionManager
from kailash.db.dialect import (
    DatabaseType,
    MySQLDialect,
    PostgresDialect,
    QueryDialect,
    SQLiteDialect,
    detect_dialect,
)
from kailash.db.registry import resolve_database_url, resolve_queue_url

__all__ = [
    "ConnectionManager",
    "DatabaseType",
    "MySQLDialect",
    "PostgresDialect",
    "QueryDialect",
    "SQLiteDialect",
    "detect_dialect",
    "resolve_database_url",
    "resolve_queue_url",
]

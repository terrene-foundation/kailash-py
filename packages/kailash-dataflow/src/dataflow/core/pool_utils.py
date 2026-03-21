# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
Pool utilities for connection pool auto-scaling and diagnostics.

Provides shared detection logic used by:
- DatabaseConfig.get_pool_size() for auto-scaling (PY-1)
- pool_validator.py for startup validation (PY-4)

All database driver imports are lazy to avoid requiring optional dependencies
at import time (per infrastructure-sql.md Rule 8).
"""

from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

__all__ = [
    "detect_worker_count",
    "is_mysql",
    "is_postgresql",
    "is_sqlite",
    "probe_max_connections",
]

# Ordered list of env vars to check for worker count.
# First non-empty, valid value wins.
_WORKER_ENV_VARS = (
    "DATAFLOW_WORKER_COUNT",
    "KAILASH_WORKERS",
    "UVICORN_WORKERS",
    "WEB_CONCURRENCY",
    "GUNICORN_WORKERS",
)

# Connection probe timeout in seconds.
_PROBE_TIMEOUT_SECS = 5


def detect_worker_count() -> int:
    """Detect the number of application worker processes.

    Checks environment variables in priority order:
    DATAFLOW_WORKER_COUNT > KAILASH_WORKERS > UVICORN_WORKERS >
    WEB_CONCURRENCY > GUNICORN_WORKERS.

    Returns:
        Worker count (always >= 1). Returns 1 when no env var is set
        or all values are invalid.
    """
    for var_name in _WORKER_ENV_VARS:
        raw = os.environ.get(var_name, "").strip()
        if not raw:
            continue
        try:
            value = int(raw)
        except ValueError:
            logger.warning(
                "Invalid worker count in %s=%r (expected integer), skipping",
                var_name,
                raw,
            )
            continue
        if value < 1:
            logger.warning(
                "Worker count in %s=%d is less than 1, clamping to 1",
                var_name,
                value,
            )
            return 1
        return value

    return 1


def is_postgresql(url: Optional[str]) -> bool:
    """Check if a database URL is for PostgreSQL.

    Recognizes schemes: postgresql://, postgres://, postgresql+asyncpg://,
    postgresql+psycopg2://, etc.
    """
    if not url:
        return False
    lower = url.lower()
    return (
        lower.startswith("postgresql://")
        or lower.startswith("postgres://")
        or lower.startswith("postgresql+")
    )


def is_sqlite(url: Optional[str]) -> bool:
    """Check if a database URL is for SQLite.

    Recognizes schemes: sqlite://, sqlite+aiosqlite://, etc.
    """
    if not url:
        return False
    return url.lower().startswith("sqlite://") or url.lower().startswith("sqlite+")


def is_mysql(url: Optional[str]) -> bool:
    """Check if a database URL is for MySQL.

    Recognizes schemes: mysql://, mysql+pymysql://, mysql+aiomysql://, etc.
    """
    if not url:
        return False
    return url.lower().startswith("mysql://") or url.lower().startswith("mysql+")


def probe_max_connections(database_url: Optional[str]) -> Optional[int]:
    """Probe a database server to discover its max_connections setting.

    Creates a short-lived standalone connection (NOT from the pool) to
    query the server's maximum allowed connections.

    Args:
        database_url: Database connection URL.

    Returns:
        The server's max_connections as an int, or None if:
        - The URL is None/empty
        - The database type is SQLite (no max_connections concept)
        - The database type is unrecognized
        - The driver is not installed
        - The connection fails
        - The query fails
    """
    if not database_url:
        return None

    if is_sqlite(database_url):
        return None

    if is_postgresql(database_url):
        return _probe_postgresql(database_url)

    if is_mysql(database_url):
        return _probe_mysql(database_url)

    # Do NOT log the full URL — it may contain credentials
    scheme = database_url.split("://")[0] if "://" in database_url else "unknown"
    logger.debug(
        "probe_max_connections: unrecognized database URL scheme '%s', returning None",
        scheme,
    )
    return None


def _probe_postgresql(database_url: str) -> Optional[int]:
    """Probe PostgreSQL for max_connections via SHOW max_connections."""
    try:
        import psycopg2
    except ImportError:
        logger.warning(
            "Cannot probe PostgreSQL max_connections: psycopg2 not installed. "
            "Install with: pip install psycopg2-binary"
        )
        return None

    # Normalize SQLAlchemy-style URLs for psycopg2
    # psycopg2 expects postgresql:// not postgresql+asyncpg://
    conn_url = database_url
    if "+asyncpg" in conn_url or "+psycopg2" in conn_url:
        conn_url = conn_url.split("+")[0] + "://" + conn_url.split("://", 1)[1]

    try:
        with psycopg2.connect(conn_url, connect_timeout=_PROBE_TIMEOUT_SECS) as conn:
            cursor = conn.cursor()
            cursor.execute("SHOW max_connections")
            row = cursor.fetchone()
            if row:
                return int(row[0])
            logger.warning(
                "probe_max_connections: SHOW max_connections returned no rows"
            )
            return None
    except Exception as exc:
        # Log only the exception type at WARNING — str(exc) may contain credentials
        logger.warning(
            "Failed to probe PostgreSQL max_connections: %s",
            type(exc).__name__,
        )
        logger.debug("PostgreSQL probe error details", exc_info=True)
        return None


def _probe_mysql(database_url: str) -> Optional[int]:
    """Probe MySQL for max_connections via SHOW VARIABLES."""
    try:
        import pymysql
    except ImportError:
        logger.warning(
            "Cannot probe MySQL max_connections: pymysql not installed. "
            "Install with: pip install pymysql"
        )
        return None

    # Parse MySQL URL for pymysql connection
    # mysql://user:pass@host:port/dbname
    try:
        from urllib.parse import urlparse

        parsed = urlparse(database_url)
        conn_kwargs = {
            "host": parsed.hostname or "localhost",
            "port": parsed.port or 3306,
            "user": parsed.username or "root",
            "password": parsed.password or "",
            "database": (parsed.path or "/").lstrip("/") or None,
            "connect_timeout": _PROBE_TIMEOUT_SECS,
        }
    except Exception as exc:
        logger.warning("Failed to parse MySQL URL for probe: %s", type(exc).__name__)
        logger.debug("MySQL URL parse error details", exc_info=True)
        return None

    try:
        with pymysql.connect(**conn_kwargs) as conn:
            cursor = conn.cursor()
            cursor.execute("SHOW VARIABLES LIKE 'max_connections'")
            row = cursor.fetchone()
            if row:
                return int(row[1])
            logger.warning(
                "probe_max_connections: SHOW VARIABLES returned no rows for max_connections"
            )
            return None
    except Exception as exc:
        logger.warning("Failed to probe MySQL max_connections: %s", type(exc).__name__)
        logger.debug("MySQL probe error details", exc_info=True)
        return None

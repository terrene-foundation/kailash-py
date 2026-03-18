# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Shared fixtures for Level 1 infrastructure integration tests.

Provides a parameterized ``conn`` fixture that yields a
:class:`~kailash.db.connection.ConnectionManager` for each supported
database dialect: SQLite (in-memory), PostgreSQL, and MySQL.

Database availability is detected at runtime via a lightweight socket
probe.  Unavailable databases are skipped gracefully so that CI
environments without Docker still run the SQLite variant.

Connection URLs default to the docker-compose.test.yml ports and can
be overridden via environment variables:
    TEST_PG_URL    (default: postgresql://test_user:test_password@localhost:5434/kailash_test)
    TEST_MYSQL_URL (default: mysql://kailash_test:test_password@localhost:3307/kailash_test)
"""

from __future__ import annotations

import logging
import os
import socket
from typing import AsyncGenerator
from urllib.parse import urlparse

import pytest

from kailash.db.connection import ConnectionManager

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Database URLs from environment or defaults matching docker-compose.test.yml
# ---------------------------------------------------------------------------
PG_URL = os.environ.get(
    "TEST_PG_URL",
    "postgresql://test_user:test_password@localhost:5434/kailash_test",
)
MYSQL_URL = os.environ.get(
    "TEST_MYSQL_URL",
    "mysql://kailash_test:test_password@localhost:3307/kailash_test",
)
SQLITE_URL = "sqlite:///:memory:"

# All infrastructure tables created by the stores.
INFRASTRUCTURE_TABLES = [
    "kailash_events",
    "kailash_checkpoints",
    "kailash_dlq",
    "kailash_executions",
    "kailash_idempotency",
    "kailash_meta",
]


# ---------------------------------------------------------------------------
# Availability probes
# ---------------------------------------------------------------------------
def _is_tcp_available(host: str, port: int, timeout: float = 2.0) -> bool:
    """Return True if a TCP connection to *host:port* succeeds."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (OSError, ConnectionRefusedError, TimeoutError):
        return False


def _is_pg_available() -> bool:
    parsed = urlparse(PG_URL)
    host = parsed.hostname or "localhost"
    port = parsed.port or 5432
    return _is_tcp_available(host, port)


def _is_mysql_available() -> bool:
    parsed = urlparse(MYSQL_URL)
    host = parsed.hostname or "localhost"
    port = parsed.port or 3306
    return _is_tcp_available(host, port)


# ---------------------------------------------------------------------------
# Parameterized connection fixture
# ---------------------------------------------------------------------------
@pytest.fixture(params=["sqlite", "pg", "mysql"])
async def conn(request: pytest.FixtureRequest) -> AsyncGenerator[ConnectionManager, None]:
    """Yield an initialized ConnectionManager for each dialect.

    The fixture:
    1. Probes TCP to skip unavailable databases.
    2. Initializes the connection pool.
    3. Yields the ConnectionManager.
    4. Drops all infrastructure tables and closes the pool.
    """
    dialect = request.param

    if dialect == "sqlite":
        url = SQLITE_URL
    elif dialect == "pg":
        if not _is_pg_available():
            pytest.skip("PostgreSQL is not available at " + PG_URL)
        url = PG_URL
    elif dialect == "mysql":
        if not _is_mysql_available():
            pytest.skip("MySQL is not available at " + MYSQL_URL)
        url = MYSQL_URL
    else:
        raise ValueError(f"Unknown dialect fixture param: {dialect!r}")

    manager = ConnectionManager(url)
    await manager.initialize()
    logger.info("ConnectionManager initialized for dialect=%s url=%s", dialect, url[:40])

    yield manager

    # Cleanup: drop all infrastructure tables so each test starts clean.
    for table in INFRASTRUCTURE_TABLES:
        try:
            await manager.execute(f"DROP TABLE IF EXISTS {table}")
        except Exception:
            logger.debug("Could not drop table %s during cleanup", table, exc_info=True)

    await manager.close()
    logger.info("ConnectionManager closed for dialect=%s", dialect)


# ---------------------------------------------------------------------------
# Convenience single-dialect fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
async def sqlite_conn() -> AsyncGenerator[ConnectionManager, None]:
    """Yield an in-memory SQLite ConnectionManager (always available)."""
    manager = ConnectionManager(SQLITE_URL)
    await manager.initialize()
    yield manager
    for table in INFRASTRUCTURE_TABLES:
        try:
            await manager.execute(f"DROP TABLE IF EXISTS {table}")
        except Exception:
            pass
    await manager.close()


@pytest.fixture
async def pg_conn() -> AsyncGenerator[ConnectionManager, None]:
    """Yield a PostgreSQL ConnectionManager or skip if unavailable."""
    if not _is_pg_available():
        pytest.skip("PostgreSQL is not available at " + PG_URL)
    manager = ConnectionManager(PG_URL)
    await manager.initialize()
    yield manager
    for table in INFRASTRUCTURE_TABLES:
        try:
            await manager.execute(f"DROP TABLE IF EXISTS {table}")
        except Exception:
            pass
    await manager.close()


@pytest.fixture
async def mysql_conn() -> AsyncGenerator[ConnectionManager, None]:
    """Yield a MySQL ConnectionManager or skip if unavailable."""
    if not _is_mysql_available():
        pytest.skip("MySQL is not available at " + MYSQL_URL)
    manager = ConnectionManager(MYSQL_URL)
    await manager.initialize()
    yield manager
    for table in INFRASTRUCTURE_TABLES:
        try:
            await manager.execute(f"DROP TABLE IF EXISTS {table}")
        except Exception:
            pass
    await manager.close()

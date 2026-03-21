# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
Lightweight connection pool for health checks and diagnostics.

Provides a separate mini-pool (2 connections) dedicated to health checks
and diagnostic queries. This prevents health check endpoints from competing
with the main application pool during high-load scenarios.

When the main pool is at 100% utilization, health checks using the lightweight
pool still succeed — preventing the load balancer from marking the instance
unhealthy during recovery.

Cross-SDK alignment: Equivalent to RS-6 (Lightweight Query Path) in kailash-rs.

Note: For SQLite :memory: databases, the lightweight pool operates on a separate
database instance (inherent to SQLite in-memory semantics). Health check queries
like SELECT 1 still work, but application tables are not visible.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Optional

logger = logging.getLogger(__name__)

__all__ = ["LightweightPool"]

# Fixed size — deliberately small, only for health checks
_LIGHTWEIGHT_POOL_SIZE = 2


class LightweightPool:
    """Separate mini-pool for health checks and diagnostics.

    This pool is NOT monitored by PoolMonitor (it's deliberately small
    and low-traffic). It exists solely to isolate health checks from
    application pool pressure.

    Thread/async safety: All public methods are protected by an asyncio.Lock
    to prevent races between concurrent health checks and shutdown.

    Args:
        database_url: Same database URL as the main pool.
        pool_size: Number of connections. Default: 2. Should not be increased.
    """

    def __init__(
        self,
        database_url: str,
        pool_size: int = _LIGHTWEIGHT_POOL_SIZE,
    ):
        self._database_url = database_url
        self._pool_size = pool_size
        self._pool: Any = None
        self._initialized = False
        self._lock: Optional[asyncio.Lock] = None
        self._init_pid: Optional[int] = None

    @property
    def is_initialized(self) -> bool:
        """Whether the lightweight pool has been initialized."""
        return self._initialized

    def _get_lock(self) -> asyncio.Lock:
        """Get or create the asyncio lock (lazy, event-loop safe)."""
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    def _extract_sqlite_path(self) -> str:
        """Extract the file path from a SQLite URL."""
        url = self._database_url
        # Handle sqlite:///path, sqlite+aiosqlite:///path, etc.
        if ":///" in url:
            return url.split("///", 1)[1] or ":memory:"
        return ":memory:"

    async def initialize(self) -> None:
        """Create the lightweight connection pool."""
        async with self._get_lock():
            if self._initialized:
                return

            from dataflow.core.pool_utils import is_postgresql, is_sqlite

            if is_sqlite(self._database_url):
                # SQLite: use a simple aiosqlite connection
                try:
                    import aiosqlite

                    self._pool = await aiosqlite.connect(self._extract_sqlite_path())
                    self._initialized = True
                    self._init_pid = os.getpid()
                    logger.debug("Lightweight pool initialized (SQLite, 1 connection)")
                except ImportError:
                    logger.warning(
                        "Cannot create lightweight pool: aiosqlite not installed"
                    )
            elif is_postgresql(self._database_url):
                try:
                    import asyncpg

                    # Normalize URL for asyncpg
                    url = self._database_url
                    if url.startswith("postgresql+"):
                        url = "postgresql://" + url.split("://", 1)[1]

                    self._pool = await asyncpg.create_pool(
                        url,
                        min_size=1,
                        max_size=self._pool_size,
                        command_timeout=5,
                    )
                    self._initialized = True
                    self._init_pid = os.getpid()
                    logger.debug(
                        "Lightweight pool initialized (PostgreSQL, %d connections)",
                        self._pool_size,
                    )
                except ImportError:
                    logger.warning(
                        "Cannot create lightweight pool: asyncpg not installed"
                    )
                except Exception as exc:
                    logger.warning(
                        "Failed to create lightweight pool: %s",
                        type(exc).__name__,
                    )
                    logger.debug("Lightweight pool creation error", exc_info=True)
            else:
                logger.debug("Lightweight pool not created (unsupported database type)")

    # Allowlist of SQL queries permitted on the lightweight pool.
    # Only health checks and diagnostic queries should use this pool.
    # SHOW is narrowed to specific commands to prevent information leakage
    # (e.g., SHOW GRANTS, SHOW SLAVE STATUS on MySQL expose sensitive data).
    _ALLOWED_PREFIXES = (
        "SELECT 1",
        "SELECT 'ok'",
        "SHOW MAX_CONNECTIONS",
        "SHOW SERVER_VERSION",
        "SELECT version()",
        "SELECT current_database()",
        "SELECT pg_is_in_recovery()",
    )

    async def execute_raw(self, sql: str) -> Any:
        """Execute a raw SQL query on the lightweight pool.

        Only health check and diagnostic queries are permitted (allowlisted).
        Application queries MUST use the main pool.

        Args:
            sql: SQL query (must match an allowed prefix).

        Returns:
            Query result.

        Raises:
            RuntimeError: If the pool is not initialized.
            ValueError: If the SQL query is not in the allowlist.
        """
        async with self._get_lock():
            # Detect post-fork scenario (Gunicorn pre-fork)
            if self._initialized and self._init_pid != os.getpid():
                logger.debug("Post-fork detected, re-initializing lightweight pool")
                self._pool = None
                self._initialized = False

            if not self._initialized or self._pool is None:
                raise RuntimeError(
                    "Lightweight pool not initialized. Call initialize() first."
                )

            # Security: only allow health check / diagnostic queries
            sql_upper = sql.strip().upper()
            if not any(
                sql_upper.startswith(prefix.upper())
                for prefix in self._ALLOWED_PREFIXES
            ):
                raise ValueError(
                    f"Query not allowed on lightweight pool. "
                    f"Only health check queries are permitted: "
                    f"{', '.join(self._ALLOWED_PREFIXES)}"
                )

            from dataflow.core.pool_utils import is_sqlite

            if is_sqlite(self._database_url):
                cursor = await self._pool.execute(sql)
                return await cursor.fetchall()
            else:
                # asyncpg pool
                async with self._pool.acquire() as conn:
                    return await conn.fetch(sql)

    async def close(self) -> None:
        """Close the lightweight pool."""
        lock = self._get_lock()
        # Use a timeout to avoid hanging if the lock is held by a long query
        try:
            await asyncio.wait_for(lock.acquire(), timeout=5.0)
        except asyncio.TimeoutError:
            # Force close without lock — better than hanging on shutdown
            logger.debug("Lightweight pool close timed out waiting for lock")
            await self._close_pool()
            return
        try:
            await self._close_pool()
        finally:
            lock.release()

    async def _close_pool(self) -> None:
        """Internal pool close with timeout and terminate fallback."""
        if self._pool is not None:
            try:
                if hasattr(self._pool, "close"):
                    result = self._pool.close()
                    if hasattr(result, "__await__"):
                        try:
                            await asyncio.wait_for(result, timeout=5.0)
                        except asyncio.TimeoutError:
                            # asyncpg close() hangs if connections are leaked
                            if hasattr(self._pool, "terminate"):
                                self._pool.terminate()
            except Exception:
                logger.debug("Error closing lightweight pool", exc_info=True)
            self._pool = None
            self._initialized = False
            logger.debug("Lightweight pool closed")

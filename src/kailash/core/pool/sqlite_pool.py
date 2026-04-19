"""Async SQLite connection pool with read/write separation.

Optimized for SQLite's WAL concurrency model:
- One writer connection protected by asyncio.Lock
- Multiple reader connections managed via LIFO queue + semaphore
- Lazy connection creation to minimize thread count
- Health check and max-lifetime recycling
- Memory DB fallback: single-connection mode (WAL unavailable)
"""

import asyncio
import logging
import re
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import AsyncIterator, Optional

import aiosqlite

logger = logging.getLogger(__name__)

# Query routing: read-safe prefixes vs explicit write prefixes.
# Unknown prefixes default to writer (safe: reads work on writer, but
# writes on reader are silently lost).
_READ_PREFIXES = frozenset({"SELECT", "WITH", "EXPLAIN"})
# PRAGMA is handled specially: PRAGMA name (read) vs PRAGMA name = value (write)
_COMMENT_RE = re.compile(r"(--[^\n]*\n|/\*.*?\*/)", re.DOTALL)

# Defense-in-depth validation for PRAGMA interpolation.
# PRAGMA names + values cannot be passed as bound parameters (SQLite grammar),
# so they MUST be validated before f-string interpolation.
# See rules/dataflow-identifier-safety.md (Finding #3, issue #499).
_PRAGMA_NAME_REGEX = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")
# PRAGMA values are keywords (WAL/NORMAL), integers, or -KB cache sizes.
# Disallow quotes, semicolons, parens, spaces — everything that enables SQL injection.
_PRAGMA_VALUE_REGEX = re.compile(r"^-?[a-zA-Z0-9_]+$")


def _validate_pragma(name: str, value: str) -> tuple[str, str]:
    """Validate PRAGMA name + value before interpolation. Raises on invalid input.

    PRAGMA statements don't accept bound parameters, so names/values must be
    interpolated. This validator is the single enforcement point: strict
    allowlist regex, typed error on failure, no raw value echoed in message.
    """
    if not isinstance(name, str) or not _PRAGMA_NAME_REGEX.match(name):
        raise ValueError(
            f"invalid PRAGMA name (fingerprint={hash(str(name)) & 0xFFFF:04x})"
        )
    value_str = str(value)
    if not _PRAGMA_VALUE_REGEX.match(value_str):
        raise ValueError(
            f"invalid PRAGMA value for '{name}' "
            f"(fingerprint={hash(value_str) & 0xFFFF:04x})"
        )
    return name, value_str


class PoolExhaustedError(Exception):
    """Raised when pool cannot provide a connection within timeout."""


@dataclass
class PoolMetrics:
    """Connection pool metrics for monitoring."""

    active_readers: int = 0
    idle_readers: int = 0
    writer_busy: bool = False
    total_acquires: int = 0
    total_timeouts: int = 0
    avg_wait_time_ms: float = 0.0
    connections_created: int = 0
    connections_recycled: int = 0

    # Running totals for avg calculation
    _total_wait_ms: float = 0.0


@dataclass
class SQLitePoolConfig:
    """Configuration for AsyncSQLitePool."""

    db_path: str
    max_read_connections: int = 5
    max_lifetime: float = 3600.0
    acquire_timeout: float = 10.0
    pragmas: dict[str, str] = field(
        default_factory=lambda: {
            "journal_mode": "WAL",
            "busy_timeout": "5000",
            "synchronous": "NORMAL",
            "cache_size": "-65536",
            "foreign_keys": "ON",
        }
    )
    uri: bool = False


class ConnectionFactory:
    """Creates and configures aiosqlite connections."""

    def __init__(
        self,
        db_path: str,
        pragmas: dict[str, str],
        uri: bool = False,
        is_memory_db: bool = False,
    ):
        self._db_path = db_path
        self._pragmas = pragmas
        self._uri = uri
        self._is_memory_db = is_memory_db

    async def create(self) -> aiosqlite.Connection:
        """Create a new configured connection."""
        conn = await aiosqlite.connect(self._db_path, uri=self._uri)
        conn.row_factory = aiosqlite.Row
        for pragma, value in self._pragmas.items():
            if self._is_memory_db and pragma in (
                "journal_mode",
                "wal_autocheckpoint",
                "mmap_size",
            ):
                continue
            safe_name, safe_value = _validate_pragma(pragma, value)
            await conn.execute(f"PRAGMA {safe_name} = {safe_value}")
        return conn


def _is_read_query(query: str) -> bool:
    """Determine if a SQL query is read-only based on its prefix.

    Handles SQL comments, PRAGMA write detection, and defaults to
    writer for unknown prefixes (safe: reads work on writer).
    """
    # Strip SQL comments before classification
    cleaned = _COMMENT_RE.sub("", query).strip()
    if not cleaned:
        return False
    first_word = cleaned.split(None, 1)[0].upper()
    # PRAGMA with assignment (=) is a write operation
    if first_word == "PRAGMA" and "=" in cleaned:
        return False
    # Read-only PRAGMA (no assignment) is safe for reader
    if first_word == "PRAGMA":
        return True
    return first_word in _READ_PREFIXES


class AsyncSQLitePool:
    """Async connection pool with read/write separation for SQLite.

    For file-based databases:
    - One writer connection protected by asyncio.Lock (callers issue BEGIN as needed)
    - Up to N reader connections via LIFO queue + semaphore

    For memory databases (shared-cache URI mode):
    - Single connection for both reads and writes
    - WAL unavailable, so no read/write split
    - Anchor connection kept alive to prevent DB evaporation
    """

    def __init__(self, config: SQLitePoolConfig):
        self._config = config
        self._is_memory_db = (
            config.db_path == ":memory:" or "mode=memory" in config.db_path
        )

        self._factory = ConnectionFactory(
            db_path=config.db_path,
            pragmas=config.pragmas,
            uri=config.uri,
            is_memory_db=self._is_memory_db,
        )

        # Writer state
        self._write_lock = asyncio.Lock()
        self._write_conn: Optional[aiosqlite.Connection] = None

        # Reader state (unused in memory-DB mode)
        self._read_queue: asyncio.LifoQueue[aiosqlite.Connection] = asyncio.LifoQueue(
            maxsize=config.max_read_connections
        )
        self._read_semaphore = asyncio.Semaphore(config.max_read_connections)
        self._read_count = 0

        # Connection lifetime tracking
        self._conn_created_at: dict[int, float] = {}

        # Metrics
        self._metrics = PoolMetrics()
        self._initialized = False
        self._closed = False

    async def initialize(self) -> None:
        """Initialize the pool.

        Writer connection is created lazily on first acquire_write() to
        avoid holding a persistent SQLite writer when multiple pool
        instances target the same database file.
        """
        if self._initialized:
            return

        self._initialized = True
        logger.info(
            f"AsyncSQLitePool initialized: db={self._config.db_path}, "
            f"memory={self._is_memory_db}, max_readers={self._config.max_read_connections}"
        )

    async def close(self) -> None:
        """Close all connections and shut down the pool."""
        if self._closed:
            return

        self._closed = True

        # Close writer
        if self._write_conn is not None:
            try:
                await self._write_conn.close()
            except Exception:
                pass
            self._write_conn = None

        # Drain and close all reader connections
        while not self._read_queue.empty():
            try:
                conn = self._read_queue.get_nowait()
                await conn.close()
            except Exception:
                pass

        self._read_count = 0
        self._conn_created_at.clear()
        logger.info("AsyncSQLitePool closed")

    @asynccontextmanager
    async def acquire_write(
        self, timeout: Optional[float] = None
    ) -> AsyncIterator[aiosqlite.Connection]:
        """Acquire the write connection.

        In memory-DB mode, this returns the single shared connection.
        In file-DB mode, this returns a dedicated writer (callers issue BEGIN as needed).
        """
        if self._closed:
            raise PoolExhaustedError("Pool is closed")
        if not self._initialized:
            await self.initialize()

        timeout = timeout or self._config.acquire_timeout
        start = time.monotonic()

        try:
            await asyncio.wait_for(self._write_lock.acquire(), timeout=timeout)
        except asyncio.TimeoutError:
            self._metrics.total_timeouts += 1
            raise PoolExhaustedError(
                f"Timed out waiting for write connection after {timeout}s"
            )

        # Re-check after acquiring lock — close() may have set _closed
        # while we were waiting for the lock.
        if self._closed:
            self._write_lock.release()
            raise PoolExhaustedError("Pool is closed")

        wait_ms = (time.monotonic() - start) * 1000
        self._metrics.total_acquires += 1
        self._metrics._total_wait_ms += wait_ms
        self._metrics.avg_wait_time_ms = (
            self._metrics._total_wait_ms / self._metrics.total_acquires
        )
        self._metrics.writer_busy = True

        try:
            # Lazy writer creation — avoids holding a persistent connection
            # when the pool is initialized but never used for writes.
            if self._write_conn is None:
                self._write_conn = await self._factory.create()
                self._conn_created_at[id(self._write_conn)] = time.monotonic()
                self._metrics.connections_created += 1

            conn = self._write_conn

            # Recycle if past max lifetime
            conn = await self._recycle_if_stale(conn)
            self._write_conn = conn

            # Health check
            if not await self._health_check(conn):
                await self._close_conn(conn)
                conn = await self._factory.create()
                self._conn_created_at[id(conn)] = time.monotonic()
                self._metrics.connections_created += 1
                self._write_conn = conn

            yield conn
        finally:
            self._metrics.writer_busy = False
            self._write_lock.release()

    @asynccontextmanager
    async def acquire_read(
        self, timeout: Optional[float] = None
    ) -> AsyncIterator[aiosqlite.Connection]:
        """Acquire a read connection.

        In memory-DB mode, this delegates to acquire_write (single connection).
        """
        if self._is_memory_db:
            async with self.acquire_write(timeout=timeout) as conn:
                yield conn
            return

        if self._closed:
            raise PoolExhaustedError("Pool is closed")
        if not self._initialized:
            await self.initialize()

        timeout = timeout or self._config.acquire_timeout
        start = time.monotonic()

        try:
            await asyncio.wait_for(self._read_semaphore.acquire(), timeout=timeout)
        except asyncio.TimeoutError:
            self._metrics.total_timeouts += 1
            raise PoolExhaustedError(
                f"Timed out waiting for read connection after {timeout}s"
            )

        # Re-check after acquiring semaphore — close() may have set _closed
        # while we were waiting.
        if self._closed:
            self._read_semaphore.release()
            raise PoolExhaustedError("Pool is closed")

        wait_ms = (time.monotonic() - start) * 1000
        self._metrics.total_acquires += 1
        self._metrics._total_wait_ms += wait_ms
        self._metrics.avg_wait_time_ms = (
            self._metrics._total_wait_ms / self._metrics.total_acquires
        )
        self._metrics.active_readers += 1

        conn: Optional[aiosqlite.Connection] = None
        try:
            conn = await self._get_or_create_read_conn()

            # Recycle if stale
            conn = await self._recycle_if_stale(conn)

            # Health check
            if not await self._health_check(conn):
                await self._close_conn(conn)
                conn = await self._factory.create()
                self._conn_created_at[id(conn)] = time.monotonic()
                self._metrics.connections_created += 1

            yield conn
        finally:
            self._metrics.active_readers -= 1
            if conn is not None:
                if self._closed:
                    # Pool was closed while we held the connection — close it
                    await self._close_conn(conn)
                    self._read_count -= 1
                else:
                    try:
                        # Roll back any uncommitted state before returning to pool
                        if conn.in_transaction:
                            await conn.rollback()
                        self._read_queue.put_nowait(conn)
                        self._metrics.idle_readers = self._read_queue.qsize()
                    except Exception:
                        # Connection is broken, don't return it
                        await self._close_conn(conn)
                        self._read_count -= 1
            self._read_semaphore.release()

    @asynccontextmanager
    async def acquire(
        self, query: str, timeout: Optional[float] = None
    ) -> AsyncIterator[aiosqlite.Connection]:
        """Auto-route to read or write connection based on query."""
        if _is_read_query(query):
            async with self.acquire_read(timeout=timeout) as conn:
                yield conn
        else:
            async with self.acquire_write(timeout=timeout) as conn:
                yield conn

    async def check_health(self) -> bool:
        """Validate all connections in the pool."""
        healthy = True

        # Check writer
        if self._write_conn is not None:
            if not await self._health_check(self._write_conn):
                logger.warning("Writer connection failed health check")
                healthy = False

        # Check readers
        checked: list[aiosqlite.Connection] = []
        while not self._read_queue.empty():
            try:
                conn = self._read_queue.get_nowait()
                if await self._health_check(conn):
                    checked.append(conn)
                else:
                    logger.warning("Reader connection failed health check")
                    await self._close_conn(conn)
                    self._read_count -= 1
                    healthy = False
            except asyncio.QueueEmpty:
                break

        for conn in checked:
            try:
                self._read_queue.put_nowait(conn)
            except asyncio.QueueFull:
                await self._close_conn(conn)
                self._read_count -= 1

        self._metrics.idle_readers = self._read_queue.qsize()
        return healthy

    def get_metrics(self) -> PoolMetrics:
        """Return current pool metrics."""
        self._metrics.idle_readers = self._read_queue.qsize()
        return self._metrics

    async def _get_or_create_read_conn(self) -> aiosqlite.Connection:
        """Get an idle reader from queue or create a new one."""
        # Try to get from queue first
        try:
            conn = self._read_queue.get_nowait()
            self._metrics.idle_readers = self._read_queue.qsize()
            return conn
        except asyncio.QueueEmpty:
            pass

        # Create new if under limit
        if self._read_count < self._config.max_read_connections:
            conn = await self._factory.create()
            self._conn_created_at[id(conn)] = time.monotonic()
            self._metrics.connections_created += 1
            self._read_count += 1
            return conn

        # Should not happen because semaphore bounds us, but handle gracefully
        raise PoolExhaustedError(
            "Read pool exhausted (should not happen with semaphore)"
        )

    async def _health_check(self, conn: aiosqlite.Connection) -> bool:
        """Check if a connection is healthy via SELECT 1."""
        try:
            cursor = await conn.execute("SELECT 1")
            await cursor.fetchone()
            await cursor.close()
            return True
        except Exception:
            return False

    async def _recycle_if_stale(
        self, conn: aiosqlite.Connection
    ) -> aiosqlite.Connection:
        """Replace connection if it exceeds max lifetime."""
        created_at = self._conn_created_at.get(id(conn))
        if created_at is None:
            return conn

        age = time.monotonic() - created_at
        if age > self._config.max_lifetime:
            logger.debug(
                f"Recycling connection (age={age:.0f}s > max={self._config.max_lifetime}s)"
            )
            await self._close_conn(conn)
            new_conn = await self._factory.create()
            self._conn_created_at[id(new_conn)] = time.monotonic()
            self._metrics.connections_created += 1
            self._metrics.connections_recycled += 1
            return new_conn

        return conn

    async def _close_conn(self, conn: aiosqlite.Connection) -> None:
        """Close a connection and remove its tracking data."""
        self._conn_created_at.pop(id(conn), None)
        try:
            await conn.close()
        except Exception:
            pass

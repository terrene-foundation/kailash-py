"""
Persistent memory tier implementations for warm and cold storage.

This module provides persistent storage implementations with different
performance characteristics and use cases.
"""

import asyncio
import gzip
import hashlib
import json
import logging
import os
import re
import sqlite3
import time
import traceback
import warnings
from typing import Any, Optional

import aiosqlite

from .tiers import MemoryTier

logger = logging.getLogger(__name__)

# Default PRAGMAs for persistent connections
_DEFAULT_PRAGMAS = {
    "journal_mode": "WAL",
    "synchronous": "NORMAL",
    "cache_size": "10000",
    "temp_store": "MEMORY",
    "busy_timeout": "5000",
    "foreign_keys": "ON",
}


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
    # Always coerce value to str before regex — int/bool values are valid.
    value_str = str(value)
    if not _PRAGMA_VALUE_REGEX.match(value_str):
        raise ValueError(
            f"invalid PRAGMA value for '{name}' "
            f"(fingerprint={hash(value_str) & 0xFFFF:04x})"
        )
    return name, value_str


async def _create_async_connection(
    db_path: str,
    pragmas: Optional[dict[str, str]] = None,
) -> aiosqlite.Connection:
    """Create an aiosqlite connection with PRAGMAs applied."""
    conn = await aiosqlite.connect(db_path)
    for pragma, value in (pragmas or _DEFAULT_PRAGMAS).items():
        safe_name, safe_value = _validate_pragma(pragma, value)
        await conn.execute(f"PRAGMA {safe_name}={safe_value}")
    return conn


class WarmMemoryTier(MemoryTier):
    """Fast persistent storage with <10ms access time"""

    _conn: Optional[aiosqlite.Connection] = None
    _closed: bool = False

    def __init__(self, storage_path: Optional[str] = None, max_size_mb: int = 1000):
        super().__init__("warm")
        self.storage_path = storage_path or os.path.join(
            os.getcwd(), ".kaizen", "memory", "warm.db"
        )
        self.max_size_mb = max_size_mb
        self._connection_pool = {}
        self._conn: Optional[aiosqlite.Connection] = None
        self._closed: bool = False
        self._conn_lock = asyncio.Lock()
        self._source_traceback: Optional[traceback.StackSummary] = None
        if __debug__:
            self._source_traceback = traceback.extract_stack()
        self._setup_database()

    def _setup_database(self):
        """Setup SQLite database for warm tier storage"""
        try:
            # Ensure directory exists
            os.makedirs(os.path.dirname(self.storage_path), exist_ok=True)

            # Create database with optimized settings
            conn = sqlite3.connect(self.storage_path, check_same_thread=False)

            # Enable WAL mode for better concurrent access
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA cache_size=10000")
            conn.execute("PRAGMA temp_store=MEMORY")

            # Create table
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS warm_memory (
                    key TEXT PRIMARY KEY,
                    value BLOB,
                    metadata TEXT,
                    ttl INTEGER,
                    created_at REAL,
                    last_accessed REAL,
                    access_count INTEGER DEFAULT 1,
                    value_size INTEGER
                )
            """
            )

            # Create indexes for performance
            conn.execute("CREATE INDEX IF NOT EXISTS idx_ttl ON warm_memory(ttl)")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_last_accessed ON warm_memory(last_accessed)"
            )

            conn.commit()
            conn.close()

        except Exception as e:
            logger.error(f"Failed to setup warm memory database: {e}")
            raise

    async def _get_connection(self) -> aiosqlite.Connection:
        """Get or create the persistent connection."""
        if self._closed:
            raise RuntimeError("WarmMemoryTier is closed")
        if self._conn is not None:
            return self._conn
        async with self._conn_lock:
            if self._closed:
                raise RuntimeError("WarmMemoryTier is closed")
            if self._conn is None:
                self._conn = await _create_async_connection(self.storage_path)
        return self._conn

    async def close(self) -> None:
        """Close the persistent connection."""
        self._closed = True
        if self._conn is not None:
            try:
                await self._conn.close()
            except Exception as e:
                logger.error(f"Error closing WarmMemoryTier connection: {e}")
            finally:
                self._conn = None

    def __del__(self, _warnings=warnings):
        if self._conn is not None and not self._closed:
            msg = (
                f"WarmMemoryTier for {self.storage_path!r} was not closed. "
                "Call await tier.close() before discarding."
            )
            if self._source_traceback:
                msg += "\nCreated at:\n" + "".join(
                    traceback.format_list(self._source_traceback)
                )
            _warnings.warn(msg, ResourceWarning, source=self)

    async def get(self, key: str) -> Optional[Any]:
        """Retrieve data from warm tier with <10ms target"""
        start_time = time.perf_counter()

        try:
            conn = await self._get_connection()

            cursor = await conn.execute(
                """
                SELECT value, ttl, last_accessed
                FROM warm_memory
                WHERE key = ?
            """,
                (key,),
            )

            row = await cursor.fetchone()

            if row is None:
                self._record_miss()
                return None

            value_blob, ttl, _last_accessed = row

            # Check TTL
            if ttl and time.time() > ttl:
                await self.delete(key)
                self._record_miss()
                return None

            # Update access tracking
            current_time = time.time()
            await conn.execute(
                """
                UPDATE warm_memory
                SET last_accessed = ?, access_count = access_count + 1
                WHERE key = ?
            """,
                (current_time, key),
            )
            await conn.commit()

            # Deserialize value — JSON only (pickle removed for RCE safety)
            try:
                if isinstance(value_blob, bytes):
                    value = json.loads(value_blob.decode("utf-8"))
                else:
                    value = json.loads(value_blob)
            except (json.JSONDecodeError, UnicodeDecodeError) as e:
                logger.error(
                    f"Failed to deserialize value for key '{key}': {e}. "
                    "Data may have been stored with pickle (now disabled for security). "
                    "Please re-serialize using JSON."
                )
                self._record_miss()
                return None

            self._record_hit()

            # Log performance if it exceeds target
            elapsed = (time.perf_counter() - start_time) * 1000  # ms
            if elapsed > 10.0:
                logger.warning(
                    f"Warm tier access took {elapsed:.2f}ms, exceeds <10ms target"
                )

            return value

        except Exception as e:
            logger.error(f"Error in WarmMemoryTier.get({key}): {e}")
            self._record_miss()
            return None

    async def put(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Store data in warm tier"""
        try:
            # Serialize value — JSON only (pickle removed for RCE safety)
            value_blob = json.dumps(value, default=str).encode("utf-8")

            value_size = len(value_blob)
            current_time = time.time()
            ttl_timestamp = current_time + ttl if ttl else None

            metadata = json.dumps(
                {
                    "serialization": "json",
                    "compressed": False,
                }
            )

            conn = await self._get_connection()
            await conn.execute(
                """
                INSERT OR REPLACE INTO warm_memory
                (key, value, metadata, ttl, created_at, last_accessed, value_size)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    key,
                    value_blob,
                    metadata,
                    ttl_timestamp,
                    current_time,
                    current_time,
                    value_size,
                ),
            )

            await conn.commit()

            # Check if we need to cleanup due to size limits
            await self._cleanup_if_needed()

            self._record_put()
            return True

        except Exception as e:
            logger.error(f"Error in WarmMemoryTier.put({key}): {e}")
            return False

    async def delete(self, key: str) -> bool:
        """Delete data from warm tier"""
        try:
            conn = await self._get_connection()
            cursor = await conn.execute(
                """
                DELETE FROM warm_memory WHERE key = ?
            """,
                (key,),
            )
            await conn.commit()

            if cursor.rowcount > 0:
                self._record_delete()
                return True
            return False

        except Exception as e:
            logger.error(f"Error in WarmMemoryTier.delete({key}): {e}")
            return False

    async def exists(self, key: str) -> bool:
        """Check if key exists in warm tier"""
        try:
            conn = await self._get_connection()
            cursor = await conn.execute(
                """
                SELECT 1 FROM warm_memory WHERE key = ? AND (ttl IS NULL OR ttl > ?)
            """,
                (key, time.time()),
            )

            row = await cursor.fetchone()
            return row is not None

        except Exception as e:
            logger.error(f"Error in WarmMemoryTier.exists({key}): {e}")
            return False

    async def clear(self) -> bool:
        """Clear all data from warm tier"""
        try:
            conn = await self._get_connection()
            await conn.execute("DELETE FROM warm_memory")
            await conn.commit()
            return True

        except Exception as e:
            logger.error(f"Error in WarmMemoryTier.clear(): {e}")
            return False

    async def size(self) -> int:
        """Get current size of warm tier"""
        try:
            conn = await self._get_connection()
            cursor = await conn.execute(
                """
                SELECT COUNT(*) FROM warm_memory WHERE ttl IS NULL OR ttl > ?
            """,
                (time.time(),),
            )
            row = await cursor.fetchone()
            return row[0] if row else 0

        except Exception as e:
            logger.error(f"Error getting WarmMemoryTier size: {e}")
            return 0

    async def _cleanup_if_needed(self):
        """Cleanup expired items and enforce size limits"""
        try:
            conn = await self._get_connection()
            # Remove expired items
            await conn.execute(
                """
                DELETE FROM warm_memory WHERE ttl IS NOT NULL AND ttl <= ?
            """,
                (time.time(),),
            )

            # Check total size
            cursor = await conn.execute(
                """
                SELECT SUM(value_size) FROM warm_memory
            """
            )
            row = await cursor.fetchone()
            total_size_bytes = row[0] if row and row[0] else 0
            total_size_mb = total_size_bytes / (1024 * 1024)

            # If over limit, remove least recently accessed items
            if total_size_mb > self.max_size_mb:
                await conn.execute(
                    """
                    DELETE FROM warm_memory WHERE key IN (
                        SELECT key FROM warm_memory
                        ORDER BY last_accessed ASC
                        LIMIT (
                            SELECT COUNT(*) FROM warm_memory
                        ) / 10
                    )
                """
                )

            await conn.commit()

        except Exception as e:
            logger.error(f"Error in warm tier cleanup: {e}")


class ColdMemoryTier(MemoryTier):
    """Archival storage with <100ms access time"""

    _conn: Optional[aiosqlite.Connection] = None
    _closed: bool = False

    def __init__(self, storage_path: Optional[str] = None, compression: bool = True):
        super().__init__("cold")
        self.storage_path = storage_path or os.path.join(
            os.getcwd(), ".kaizen", "memory", "cold"
        )
        self.compression = compression
        self._conn: Optional[aiosqlite.Connection] = None
        self._closed: bool = False
        self._conn_lock = asyncio.Lock()
        self._source_traceback: Optional[traceback.StackSummary] = None
        if __debug__:
            self._source_traceback = traceback.extract_stack()
        self._setup_storage()

    def _setup_storage(self):
        """Setup file-based storage for cold tier"""
        try:
            os.makedirs(self.storage_path, exist_ok=True)

            # Create metadata database
            metadata_path = os.path.join(self.storage_path, "metadata.db")
            conn = sqlite3.connect(metadata_path, check_same_thread=False)

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS cold_metadata (
                    key TEXT PRIMARY KEY,
                    filename TEXT,
                    ttl INTEGER,
                    created_at REAL,
                    last_accessed REAL,
                    file_size INTEGER,
                    compressed INTEGER
                )
            """
            )

            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_cold_ttl ON cold_metadata(ttl)"
            )
            conn.commit()
            conn.close()

        except Exception as e:
            logger.error(f"Failed to setup cold memory storage: {e}")
            raise

    @property
    def _metadata_path(self) -> str:
        return os.path.join(self.storage_path, "metadata.db")

    async def _get_connection(self) -> aiosqlite.Connection:
        """Get or create the persistent metadata connection."""
        if self._closed:
            raise RuntimeError("ColdMemoryTier is closed")
        if self._conn is not None:
            return self._conn
        async with self._conn_lock:
            if self._closed:
                raise RuntimeError("ColdMemoryTier is closed")
            if self._conn is None:
                self._conn = await _create_async_connection(self._metadata_path)
        return self._conn

    async def close(self) -> None:
        """Close the persistent metadata connection."""
        self._closed = True
        if self._conn is not None:
            try:
                await self._conn.close()
            except Exception as e:
                logger.error(f"Error closing ColdMemoryTier connection: {e}")
            finally:
                self._conn = None

    def __del__(self, _warnings=warnings):
        if self._conn is not None and not self._closed:
            msg = (
                f"ColdMemoryTier for {self.storage_path!r} was not closed. "
                "Call await tier.close() before discarding."
            )
            if self._source_traceback:
                msg += "\nCreated at:\n" + "".join(
                    traceback.format_list(self._source_traceback)
                )
            _warnings.warn(msg, ResourceWarning, source=self)

    def _get_file_path(self, key: str) -> str:
        """Get file path for key using hash-based directory structure"""
        key_hash = hashlib.md5(key.encode()).hexdigest()
        # Use first 2 chars for subdirectory to avoid too many files in one dir
        subdir = key_hash[:2]
        filename = f"{key_hash}.dat"

        dir_path = os.path.join(self.storage_path, subdir)
        os.makedirs(dir_path, exist_ok=True)

        return os.path.join(dir_path, filename)

    async def get(self, key: str) -> Optional[Any]:
        """Retrieve data from cold tier with <100ms target"""
        start_time = time.perf_counter()

        try:
            conn = await self._get_connection()
            cursor = await conn.execute(
                """
                SELECT filename, ttl, compressed, last_accessed
                FROM cold_metadata
                WHERE key = ?
            """,
                (key,),
            )

            row = await cursor.fetchone()

            if row is None:
                self._record_miss()
                return None

            filename, ttl, compressed, _last_accessed = row

            # Check TTL
            if ttl and time.time() > ttl:
                await self.delete(key)
                self._record_miss()
                return None

            # Read file
            file_path = (
                os.path.join(self.storage_path, filename)
                if filename
                else self._get_file_path(key)
            )

            if not os.path.exists(file_path):
                # File missing, clean up metadata
                await conn.execute("DELETE FROM cold_metadata WHERE key = ?", (key,))
                await conn.commit()
                self._record_miss()
                return None

            # Read and deserialize
            with open(file_path, "rb") as f:
                data = f.read()

            if compressed:
                data = gzip.decompress(data)

            # Deserialize — JSON only (pickle removed for RCE safety)
            try:
                value = json.loads(data.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError) as e:
                logger.error(
                    f"Failed to deserialize cold tier data for key '{key}': {e}. "
                    "Data may have been stored with pickle (now disabled for security). "
                    "Please re-serialize using JSON."
                )
                self._record_miss()
                return None

            # Update access time
            current_time = time.time()
            await conn.execute(
                """
                UPDATE cold_metadata
                SET last_accessed = ?
                WHERE key = ?
            """,
                (current_time, key),
            )
            await conn.commit()

            self._record_hit()

            # Log performance if it exceeds target
            elapsed = (time.perf_counter() - start_time) * 1000  # ms
            if elapsed > 100.0:
                logger.warning(
                    f"Cold tier access took {elapsed:.2f}ms, exceeds <100ms target"
                )

            return value

        except Exception as e:
            logger.error(f"Error in ColdMemoryTier.get({key}): {e}")
            self._record_miss()
            return None

    async def put(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Store data in cold tier"""
        try:
            # Serialize value — JSON only (pickle removed for RCE safety)
            data = json.dumps(value, default=str).encode("utf-8")

            # Compress if enabled
            compressed = False
            if self.compression and len(data) > 1024:  # Only compress larger items
                data = gzip.compress(data)
                compressed = True

            # Write to file
            file_path = self._get_file_path(key)
            with open(file_path, "wb") as f:
                f.write(data)

            # Update metadata
            current_time = time.time()
            ttl_timestamp = current_time + ttl if ttl else None
            filename = os.path.relpath(file_path, self.storage_path)

            conn = await self._get_connection()
            await conn.execute(
                """
                INSERT OR REPLACE INTO cold_metadata
                (key, filename, ttl, created_at, last_accessed, file_size, compressed)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    key,
                    filename,
                    ttl_timestamp,
                    current_time,
                    current_time,
                    len(data),
                    compressed,
                ),
            )

            await conn.commit()

            self._record_put()
            return True

        except Exception as e:
            logger.error(f"Error in ColdMemoryTier.put({key}): {e}")
            return False

    async def delete(self, key: str) -> bool:
        """Delete data from cold tier"""
        try:
            conn = await self._get_connection()
            cursor = await conn.execute(
                """
                SELECT filename FROM cold_metadata WHERE key = ?
            """,
                (key,),
            )

            row = await cursor.fetchone()

            if row:
                filename = row[0]

                # Delete file
                file_path = (
                    os.path.join(self.storage_path, filename)
                    if filename
                    else self._get_file_path(key)
                )
                if os.path.exists(file_path):
                    os.remove(file_path)

                # Delete metadata
                await conn.execute("DELETE FROM cold_metadata WHERE key = ?", (key,))
                await conn.commit()

                self._record_delete()
                return True

            return False

        except Exception as e:
            logger.error(f"Error in ColdMemoryTier.delete({key}): {e}")
            return False

    async def exists(self, key: str) -> bool:
        """Check if key exists in cold tier"""
        try:
            conn = await self._get_connection()
            cursor = await conn.execute(
                """
                SELECT 1 FROM cold_metadata WHERE key = ? AND (ttl IS NULL OR ttl > ?)
            """,
                (key, time.time()),
            )

            row = await cursor.fetchone()
            return row is not None

        except Exception as e:
            logger.error(f"Error in ColdMemoryTier.exists({key}): {e}")
            return False

    async def clear(self) -> bool:
        """Clear all data from cold tier"""
        try:
            conn = await self._get_connection()

            # Get all filenames to delete
            cursor = await conn.execute("SELECT filename FROM cold_metadata")
            filenames = await cursor.fetchall()

            # Delete all files
            for (filename,) in filenames:
                file_path = os.path.join(self.storage_path, filename)
                if os.path.exists(file_path):
                    os.remove(file_path)

            # Clear metadata
            await conn.execute("DELETE FROM cold_metadata")
            await conn.commit()

            return True

        except Exception as e:
            logger.error(f"Error in ColdMemoryTier.clear(): {e}")
            return False

    async def size(self) -> int:
        """Get current size of cold tier"""
        try:
            conn = await self._get_connection()
            cursor = await conn.execute(
                """
                SELECT COUNT(*) FROM cold_metadata WHERE ttl IS NULL OR ttl > ?
            """,
                (time.time(),),
            )
            row = await cursor.fetchone()
            return row[0] if row else 0

        except Exception as e:
            logger.error(f"Error getting ColdMemoryTier size: {e}")
            return 0

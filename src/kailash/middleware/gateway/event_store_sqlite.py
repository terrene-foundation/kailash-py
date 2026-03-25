"""SQLite storage backend for EventStore.

Provides a zero-dependency persistent backend using SQLite with WAL mode.
Reuses the pragma patterns from kailash.tracking.storage.database (SQLiteStorage)
for optimal performance: WAL journal, 64MB cache, memory temp store.

Usage:
    from kailash.middleware.gateway.event_store_sqlite import SqliteEventStoreBackend
    from kailash.middleware.gateway.event_store import EventStore

    backend = SqliteEventStoreBackend("/path/to/events.db")
    store = EventStore(storage_backend=backend)
"""

from __future__ import annotations

import json
import logging
import os
import pathlib
import sqlite3
import stat
import sys
import threading
from datetime import UTC, datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

__all__ = ["SqliteEventStoreBackend"]


class SqliteEventStoreBackend:
    """SQLite-backed event storage for EventStore.

    Implements the EventStoreBackend protocol (append/get/close) with:
    - WAL mode for concurrent read/write access
    - 64MB page cache and memory temp store
    - Per-stream auto-incrementing sequence numbers
    - Thread-safe access via threading.Lock + check_same_thread=False
    - File permissions restricted to 0o600 on POSIX systems
    - GC support via delete_before() for retention enforcement

    Schema:
        events(
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            stream_key  TEXT NOT NULL,
            sequence    INTEGER NOT NULL,
            event_type  TEXT,
            data        TEXT,       -- JSON-serialized event dict
            timestamp   TEXT,       -- ISO 8601
            UNIQUE(stream_key, sequence)
        )
        Index: idx_events_stream_seq ON (stream_key, sequence)
    """

    SCHEMA_VERSION = 1

    def __init__(self, db_path: Optional[str] = None) -> None:
        """Initialize SQLite event store backend.

        Args:
            db_path: Path to SQLite database file.
                     Defaults to ~/.kailash/events/event_store.db
        """
        if db_path is None:
            db_path = os.path.expanduser("~/.kailash/events/event_store.db")

        # Create parent directory
        parent_dir = os.path.dirname(db_path)
        if parent_dir:
            os.makedirs(parent_dir, exist_ok=True)

        self.db_path = db_path
        self._lock = threading.Lock()

        # Set restrictive file permissions on POSIX before opening
        self._set_file_permissions(db_path)

        # Open connection: check_same_thread=False for cross-thread access
        # (guarded by self._lock)
        self._conn: sqlite3.Connection | None = sqlite3.connect(
            db_path, check_same_thread=False
        )

        self._enable_optimizations()
        self._initialize_schema()

    def _get_conn(self) -> sqlite3.Connection:
        """Return the active connection, raising if closed."""
        if self._conn is None:
            raise RuntimeError("SQLiteEventStore connection is closed")
        return self._conn

    def _set_file_permissions(self, db_path: str) -> None:
        """Set restrictive file permissions on POSIX systems.

        Creates the file with 0o600 (owner read/write only) if it does
        not exist. On non-POSIX systems this is a no-op.
        """
        if sys.platform == "win32":
            return

        path_obj = _to_path(db_path)
        if not path_obj.exists():
            path_obj.touch(mode=0o600)
        else:
            os.chmod(db_path, stat.S_IRUSR | stat.S_IWUSR)

    def _enable_optimizations(self) -> None:
        """Enable WAL mode and optimal SQLite pragmas.

        Mirrors the pragma set from kailash.tracking.storage.database.SQLiteStorage.
        """
        cursor = self._get_conn().cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA cache_size=-64000")  # 64 MB
        cursor.execute("PRAGMA temp_store=MEMORY")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA automatic_index=ON")
        self._get_conn().commit()

    def _initialize_schema(self) -> None:
        """Create the events table and indexes if they do not exist."""
        cursor = self._get_conn().cursor()

        # Schema versioning table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_version (
                version     INTEGER PRIMARY KEY,
                upgraded_at TEXT NOT NULL
            )
            """
        )

        cursor.execute(
            "SELECT version FROM schema_version ORDER BY version DESC LIMIT 1"
        )
        row = cursor.fetchone()
        current_version = row[0] if row else 0

        if current_version < self.SCHEMA_VERSION:
            self._create_schema_v1(cursor)
            cursor.execute(
                "INSERT OR REPLACE INTO schema_version (version, upgraded_at) VALUES (?, ?)",
                (self.SCHEMA_VERSION, datetime.now(UTC).isoformat()),
            )

        self._get_conn().commit()

    def _create_schema_v1(self, cursor: sqlite3.Cursor) -> None:
        """Create version 1 schema."""
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS events (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                stream_key  TEXT    NOT NULL,
                sequence    INTEGER NOT NULL,
                event_type  TEXT,
                data        TEXT,
                timestamp   TEXT,
                UNIQUE(stream_key, sequence)
            )
            """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_events_stream_seq
            ON events (stream_key, sequence)
            """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_events_timestamp
            ON events (timestamp)
            """
        )

    # ------------------------------------------------------------------
    # EventStoreBackend protocol
    # ------------------------------------------------------------------

    async def append(self, key: str, events: List[Dict[str, Any]]) -> None:
        """Append events to the stream identified by *key*.

        Events are inserted with auto-incrementing per-stream sequence
        numbers.  Each event dict is stored as a JSON blob in the ``data``
        column. The ``event_type`` and ``timestamp`` fields are also
        extracted and stored as indexed columns for efficient querying.

        Args:
            key: Stream key (e.g. "events:req_abc123").
            events: List of event dicts from RequestEvent.to_dict().
        """
        if not events:
            return

        with self._lock:
            cursor = self._get_conn().cursor()

            # Determine next sequence number for this stream
            cursor.execute(
                "SELECT COALESCE(MAX(sequence), -1) FROM events WHERE stream_key = ?",
                (key,),
            )
            next_seq = cursor.fetchone()[0] + 1

            rows = []
            for i, event in enumerate(events):
                rows.append(
                    (
                        key,
                        next_seq + i,
                        event.get("event_type", ""),
                        json.dumps(event),
                        event.get("timestamp", datetime.now(UTC).isoformat()),
                    )
                )

            cursor.executemany(
                """
                INSERT INTO events (stream_key, sequence, event_type, data, timestamp)
                VALUES (?, ?, ?, ?, ?)
                """,
                rows,
            )
            self._get_conn().commit()

        logger.debug("Appended %d events to stream %s", len(events), key)

    async def get(self, key: str) -> List[Dict[str, Any]]:
        """Retrieve all events for a stream, ordered by sequence.

        Args:
            key: Stream key (e.g. "events:req_abc123").

        Returns:
            List of event dicts, ordered by sequence ascending.
        """
        with self._lock:
            cursor = self._get_conn().cursor()
            cursor.execute(
                "SELECT data FROM events WHERE stream_key = ? ORDER BY sequence",
                (key,),
            )
            rows = cursor.fetchall()

        return [json.loads(row[0]) for row in rows]

    async def get_after(
        self, key: str, after_sequence: int = 0
    ) -> List[Dict[str, Any]]:
        """Retrieve events after a given sequence number.

        Useful for replay-from-offset scenarios.

        Args:
            key: Stream key.
            after_sequence: Return events with sequence > this value.

        Returns:
            List of event dicts ordered by sequence.
        """
        with self._lock:
            cursor = self._get_conn().cursor()
            cursor.execute(
                "SELECT data FROM events WHERE stream_key = ? AND sequence > ? ORDER BY sequence",
                (key, after_sequence),
            )
            rows = cursor.fetchall()

        return [json.loads(row[0]) for row in rows]

    async def delete_before(self, timestamp: str) -> int:
        """Delete events older than the given ISO 8601 timestamp.

        Intended for garbage collection / retention enforcement.

        Args:
            timestamp: ISO 8601 timestamp cutoff. Events with
                       timestamp < this value are deleted.

        Returns:
            Number of deleted rows.
        """
        with self._lock:
            cursor = self._get_conn().cursor()
            cursor.execute(
                "DELETE FROM events WHERE timestamp < ?",
                (timestamp,),
            )
            deleted = cursor.rowcount
            self._get_conn().commit()

        if deleted > 0:
            logger.info("GC: deleted %d events older than %s", deleted, timestamp)

        return deleted

    async def count(self, key: Optional[str] = None) -> int:
        """Count events, optionally filtered by stream key.

        Args:
            key: If provided, count only events in this stream.

        Returns:
            Number of matching events.
        """
        with self._lock:
            cursor = self._get_conn().cursor()
            if key is not None:
                cursor.execute(
                    "SELECT COUNT(*) FROM events WHERE stream_key = ?", (key,)
                )
            else:
                cursor.execute("SELECT COUNT(*) FROM events")
            return cursor.fetchone()[0]

    async def stream_keys(self) -> List[str]:
        """Return all distinct stream keys.

        Returns:
            Sorted list of stream keys.
        """
        with self._lock:
            cursor = self._get_conn().cursor()
            cursor.execute("SELECT DISTINCT stream_key FROM events ORDER BY stream_key")
            return [row[0] for row in cursor.fetchall()]

    async def close(self) -> None:
        """Close the SQLite connection."""
        with self._lock:
            if hasattr(self, "_conn") and self._conn is not None:
                try:
                    self._conn.close()
                except Exception:
                    pass
                self._conn = None

        logger.debug("SqliteEventStoreBackend closed: %s", self.db_path)

    def maintenance(self) -> None:
        """Run ANALYZE and PRAGMA optimize for query planner maintenance."""
        with self._lock:
            if self._conn is None:
                return
            cursor = self._get_conn().cursor()
            cursor.execute("ANALYZE")
            cursor.execute("PRAGMA optimize")
            self._get_conn().commit()

    # ------------------------------------------------------------------
    # Context manager and cleanup
    # ------------------------------------------------------------------

    async def __aenter__(self) -> "SqliteEventStoreBackend":
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> bool:
        await self.close()
        return False

    def __del__(self) -> None:
        try:
            with self._lock:
                if hasattr(self, "_conn") and self._conn is not None:
                    self._conn.close()
                    self._conn = None
        except Exception:
            pass


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _to_path(p: str) -> "pathlib.Path":
    """Convert string to pathlib.Path (lazy import to keep module light)."""
    from pathlib import Path

    return Path(p)

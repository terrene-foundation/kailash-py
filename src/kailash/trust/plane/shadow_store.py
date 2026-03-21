# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""SQLite storage for shadow observation sessions.

Persists shadow sessions and tool calls to a separate ``shadow.db``
database, independent from the main trust.db. This allows shadow
mode to work zero-config without requiring ``attest init``.

Security notes:
- WAL journal mode for concurrent readers.
- All writes wrapped in SQLite transactions (atomic).
- Bounded results via ``limit`` parameters.
"""

from __future__ import annotations

import logging
import os
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from kailash.trust._locking import validate_id
from kailash.trust.plane.shadow import ShadowSession, ShadowToolCall

logger = logging.getLogger(__name__)

__all__ = ["ShadowStore"]

_CREATE_SESSIONS_SQL = """
CREATE TABLE IF NOT EXISTS shadow_sessions (
    session_id TEXT PRIMARY KEY,
    started_at TEXT NOT NULL,
    ended_at   TEXT
)
"""

_CREATE_TOOL_CALLS_SQL = """
CREATE TABLE IF NOT EXISTS shadow_tool_calls (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    action     TEXT NOT NULL,
    resource   TEXT NOT NULL,
    category   TEXT NOT NULL,
    timestamp  TEXT NOT NULL,
    would_be_blocked INTEGER NOT NULL DEFAULT 0,
    would_be_held    INTEGER NOT NULL DEFAULT 0,
    reason     TEXT,
    FOREIGN KEY (session_id) REFERENCES shadow_sessions(session_id)
)
"""

_CREATE_INDEXES_SQL = [
    "CREATE INDEX IF NOT EXISTS idx_shadow_calls_session ON shadow_tool_calls (session_id)",
    "CREATE INDEX IF NOT EXISTS idx_shadow_sessions_started ON shadow_sessions (started_at)",
]


class ShadowStore:
    """SQLite-backed store for shadow observation data.

    Stores sessions and tool calls in a dedicated ``shadow.db`` file,
    separate from the main trust-plane database.

    Example::

        store = ShadowStore("/path/to/.trust-plane/shadow.db")
        store.initialize()
        sid = store.start_session()
        store.record_call(sid, "Read", "/src/main.py", "file_read")
        store.end_session(sid)
        session = store.get_session(sid)
        store.close()
    """

    def __init__(self, db_path: str | Path) -> None:
        """Initialize the shadow store.

        Args:
            db_path: Path to the SQLite database file. Parent
                directories are created on ``initialize()``.
        """
        self._db_path = str(db_path)
        self._conn: Optional[sqlite3.Connection] = None

    def _get_connection(self) -> sqlite3.Connection:
        """Return the SQLite connection, creating it if needed."""
        if self._conn is None:
            self._conn = sqlite3.connect(self._db_path)
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA busy_timeout=5000")
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def initialize(self) -> None:
        """Create the database and tables.

        Safe to call multiple times (idempotent).
        """
        parent = os.path.dirname(self._db_path)
        if parent:
            os.makedirs(parent, exist_ok=True)

        conn = self._get_connection()
        conn.execute(_CREATE_SESSIONS_SQL)
        conn.execute(_CREATE_TOOL_CALLS_SQL)
        for idx_stmt in _CREATE_INDEXES_SQL:
            conn.execute(idx_stmt)
        conn.commit()
        logger.info("Initialized shadow store at %s", self._db_path)

    def close(self) -> None:
        """Close the database connection.

        Safe to call multiple times.
        """
        if self._conn is not None:
            self._conn.close()
            self._conn = None
        logger.debug("ShadowStore closed")

    def start_session(self) -> str:
        """Create a new shadow observation session.

        Returns:
            The session_id of the newly created session.
        """
        session_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        conn = self._get_connection()
        conn.execute(
            "INSERT INTO shadow_sessions (session_id, started_at) VALUES (?, ?)",
            (session_id, now),
        )
        conn.commit()
        logger.info("Started shadow session: %s", session_id)
        return session_id

    def record_call(
        self,
        session_id: str,
        action: str,
        resource: str,
        category: str,
        would_be_blocked: bool = False,
        would_be_held: bool = False,
        reason: Optional[str] = None,
    ) -> None:
        """Record a tool call in a session.

        Args:
            session_id: The session to record in.
            action: The tool/action name.
            resource: The resource acted upon.
            category: The classified category.
            would_be_blocked: Whether this would be blocked.
            would_be_held: Whether this would be held.
            reason: Why it would be blocked/held.

        Raises:
            ValueError: If session_id contains unsafe characters.
        """
        validate_id(session_id)
        now = datetime.now(timezone.utc).isoformat()
        conn = self._get_connection()
        conn.execute(
            "INSERT INTO shadow_tool_calls "
            "(session_id, action, resource, category, timestamp, "
            "would_be_blocked, would_be_held, reason) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                session_id,
                action,
                resource,
                category,
                now,
                1 if would_be_blocked else 0,
                1 if would_be_held else 0,
                reason,
            ),
        )
        conn.commit()

    def end_session(self, session_id: str) -> None:
        """Mark a session as ended.

        Args:
            session_id: The session to end.

        Raises:
            ValueError: If session_id contains unsafe characters.
        """
        validate_id(session_id)
        now = datetime.now(timezone.utc).isoformat()
        conn = self._get_connection()
        conn.execute(
            "UPDATE shadow_sessions SET ended_at = ? WHERE session_id = ?",
            (now, session_id),
        )
        conn.commit()
        logger.info("Ended shadow session: %s", session_id)

    def get_session(self, session_id: str) -> ShadowSession:
        """Retrieve a session with all its tool calls.

        Args:
            session_id: The session to retrieve.

        Returns:
            The ShadowSession with all tool calls loaded.

        Raises:
            ValueError: If session_id contains unsafe characters.
            KeyError: If the session is not found.
        """
        validate_id(session_id)
        conn = self._get_connection()
        row = conn.execute(
            "SELECT session_id, started_at, ended_at FROM shadow_sessions "
            "WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"Shadow session not found: {session_id}")

        tool_calls = self._load_tool_calls(conn, session_id)

        return ShadowSession(
            session_id=row["session_id"],
            started_at=datetime.fromisoformat(row["started_at"]),
            ended_at=(
                datetime.fromisoformat(row["ended_at"]) if row["ended_at"] else None
            ),
            tool_calls=tool_calls,
        )

    def list_sessions(
        self,
        limit: int = 100,
        since: Optional[datetime] = None,
    ) -> list[ShadowSession]:
        """List shadow sessions, ordered by start time descending.

        Args:
            limit: Maximum number of sessions to return.
            since: If provided, only return sessions started after this time.

        Returns:
            List of ShadowSession objects (tool_calls loaded).
        """
        conn = self._get_connection()
        if since is not None:
            cursor = conn.execute(
                "SELECT session_id, started_at, ended_at FROM shadow_sessions "
                "WHERE started_at >= ? ORDER BY started_at DESC LIMIT ?",
                (since.isoformat(), limit),
            )
        else:
            cursor = conn.execute(
                "SELECT session_id, started_at, ended_at FROM shadow_sessions "
                "ORDER BY started_at DESC LIMIT ?",
                (limit,),
            )

        sessions: list[ShadowSession] = []
        for row in cursor.fetchall():
            tool_calls = self._load_tool_calls(conn, row["session_id"])
            sessions.append(
                ShadowSession(
                    session_id=row["session_id"],
                    started_at=datetime.fromisoformat(row["started_at"]),
                    ended_at=(
                        datetime.fromisoformat(row["ended_at"])
                        if row["ended_at"]
                        else None
                    ),
                    tool_calls=tool_calls,
                )
            )
        return sessions

    def cleanup(
        self,
        max_age_days: int = 90,
        max_sessions: int = 10_000,
        max_size_mb: int = 500,
    ) -> int:
        """Remove sessions that exceed retention policy limits.

        Cleanup is atomic — each session is deleted with its tool calls
        in a single transaction. Partial sessions are never left behind.

        Policy is applied in order:
        1. Delete sessions older than ``max_age_days``.
        2. If session count exceeds ``max_sessions``, delete oldest excess.
        3. If database file exceeds ``max_size_mb``, delete oldest sessions
           until under the threshold (or only one session remains).

        Args:
            max_age_days: Delete sessions older than this many days.
                Must be positive.
            max_sessions: Keep at most this many sessions. Must be positive.
            max_size_mb: Trigger cleanup when the SQLite file exceeds
                this many megabytes. Must be positive.

        Returns:
            Total number of sessions removed.

        Raises:
            ValueError: If any parameter is not a positive integer.
        """
        if max_age_days < 1:
            raise ValueError("max_age_days must be >= 1")
        if max_sessions < 1:
            raise ValueError("max_sessions must be >= 1")
        if max_size_mb < 1:
            raise ValueError("max_size_mb must be >= 1")

        conn = self._get_connection()
        total_removed = 0

        # --- Phase 1: age-based cleanup ---
        cutoff = (datetime.now(timezone.utc) - timedelta(days=max_age_days)).isoformat()
        expired_ids = [
            row[0]
            for row in conn.execute(
                "SELECT session_id FROM shadow_sessions WHERE started_at < ?",
                (cutoff,),
            ).fetchall()
        ]
        if expired_ids:
            total_removed += self._delete_sessions(conn, expired_ids)

        # --- Phase 2: count-based cleanup ---
        count_row = conn.execute("SELECT COUNT(*) FROM shadow_sessions").fetchone()
        session_count = count_row[0]
        if session_count > max_sessions:
            excess = session_count - max_sessions
            excess_ids = [
                row[0]
                for row in conn.execute(
                    "SELECT session_id FROM shadow_sessions "
                    "ORDER BY started_at ASC LIMIT ?",
                    (excess,),
                ).fetchall()
            ]
            if excess_ids:
                total_removed += self._delete_sessions(conn, excess_ids)

        # --- Phase 3: size-based cleanup ---
        max_size_bytes = max_size_mb * 1024 * 1024
        if os.path.exists(self._db_path):
            while os.path.getsize(self._db_path) > max_size_bytes:
                # Check remaining session count — keep at least one
                remaining = conn.execute(
                    "SELECT COUNT(*) FROM shadow_sessions"
                ).fetchone()[0]
                if remaining <= 1:
                    break
                # Delete the oldest batch (10% of remaining or at least 1)
                batch_size = max(1, remaining // 10)
                batch_ids = [
                    row[0]
                    for row in conn.execute(
                        "SELECT session_id FROM shadow_sessions "
                        "ORDER BY started_at ASC LIMIT ?",
                        (batch_size,),
                    ).fetchall()
                ]
                if not batch_ids:
                    break
                removed = self._delete_sessions(conn, batch_ids)
                total_removed += removed
                # VACUUM to reclaim space so getsize reflects the deletion
                conn.execute("VACUUM")

        if total_removed > 0:
            logger.info("Shadow cleanup removed %d session(s)", total_removed)
        return total_removed

    def stats(self) -> Dict[str, Any]:
        """Return statistics about the shadow store.

        Returns:
            Dictionary with keys:

            - ``session_count``: Total number of sessions.
            - ``tool_call_count``: Total number of tool calls across all sessions.
            - ``oldest_session``: ISO timestamp of the oldest session, or None.
            - ``newest_session``: ISO timestamp of the newest session, or None.
            - ``disk_usage_bytes``: Size of the SQLite file in bytes.
        """
        conn = self._get_connection()

        count_row = conn.execute("SELECT COUNT(*) FROM shadow_sessions").fetchone()
        session_count = count_row[0]

        call_count_row = conn.execute(
            "SELECT COUNT(*) FROM shadow_tool_calls"
        ).fetchone()
        tool_call_count = call_count_row[0]

        oldest_row = conn.execute(
            "SELECT MIN(started_at) FROM shadow_sessions"
        ).fetchone()
        oldest_session = oldest_row[0] if oldest_row[0] else None

        newest_row = conn.execute(
            "SELECT MAX(started_at) FROM shadow_sessions"
        ).fetchone()
        newest_session = newest_row[0] if newest_row[0] else None

        disk_usage_bytes = 0
        if os.path.exists(self._db_path):
            disk_usage_bytes = os.path.getsize(self._db_path)

        return {
            "session_count": session_count,
            "tool_call_count": tool_call_count,
            "oldest_session": oldest_session,
            "newest_session": newest_session,
            "disk_usage_bytes": disk_usage_bytes,
        }

    def _delete_sessions(self, conn: sqlite3.Connection, session_ids: list[str]) -> int:
        """Atomically delete sessions and their tool calls.

        Args:
            conn: The SQLite connection to use.
            session_ids: List of session IDs to delete.

        Returns:
            Number of sessions actually deleted.
        """
        if not session_ids:
            return 0
        placeholders = ",".join("?" for _ in session_ids)
        conn.execute("BEGIN IMMEDIATE")
        try:
            conn.execute(
                f"DELETE FROM shadow_tool_calls WHERE session_id IN ({placeholders})",
                session_ids,
            )
            cursor = conn.execute(
                f"DELETE FROM shadow_sessions WHERE session_id IN ({placeholders})",
                session_ids,
            )
            deleted = cursor.rowcount
            conn.execute("COMMIT")
            return deleted
        except Exception:
            conn.execute("ROLLBACK")
            raise

    def _load_tool_calls(
        self, conn: sqlite3.Connection, session_id: str
    ) -> list[ShadowToolCall]:
        """Load tool calls for a session."""
        cursor = conn.execute(
            "SELECT action, resource, category, timestamp, "
            "would_be_blocked, would_be_held, reason "
            "FROM shadow_tool_calls WHERE session_id = ? ORDER BY id",
            (session_id,),
        )
        return [
            ShadowToolCall(
                action=row["action"],
                resource=row["resource"],
                category=row["category"],
                timestamp=datetime.fromisoformat(row["timestamp"]),
                would_be_blocked=bool(row["would_be_blocked"]),
                would_be_held=bool(row["would_be_held"]),
                reason=row["reason"],
            )
            for row in cursor.fetchall()
        ]

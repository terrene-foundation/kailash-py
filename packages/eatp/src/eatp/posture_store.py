# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
SQLite-backed persistence for agent posture state.

Provides ``SQLitePostureStore`` which stores the current posture for each
agent and a history of posture transitions in a local SQLite database.

Security properties:
- Path traversal protection on db_path and agent IDs
- Symlink rejection on db_path
- File permissions 0o600 on POSIX
- WAL journal mode for concurrent reads
- All queries use parameterized SQL (``?`` placeholders)
- History queries bounded to max 10,000 rows

Example::

    with SQLitePostureStore("/tmp/eatp/postures.db") as store:
        store.set_posture("agent-001", TrustPosture.SUPERVISED)
        posture = store.get_posture("agent-001")
        history = store.get_history("agent-001", limit=50)
"""

from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
import stat
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from eatp.postures import (
    PostureTransition,
    TransitionResult,
    TrustPosture,
)

logger = logging.getLogger(__name__)

__all__ = [
    "SQLitePostureStore",
    "validate_agent_id",
]

# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

_VALID_ID_RE = re.compile(r"^[a-zA-Z0-9_-]+$")

_MAX_HISTORY_LIMIT = 10_000


def validate_agent_id(agent_id: str) -> None:
    """Validate an agent ID against the allowed pattern.

    Agent IDs must match ``^[a-zA-Z0-9_-]+$`` -- no path traversal
    characters, no null bytes, no dots, no slashes, no spaces.

    Args:
        agent_id: The agent ID to validate.

    Raises:
        ValueError: If the agent_id is empty or contains invalid characters.
    """
    if not agent_id:
        raise ValueError("Invalid agent_id: must not be empty")
    if not _VALID_ID_RE.match(agent_id):
        raise ValueError(
            f"Invalid agent_id '{agent_id}': must match ^[a-zA-Z0-9_-]+$ "
            f"(no path traversal, slashes, dots, spaces, or null bytes)"
        )


def _validate_db_path(db_path: str) -> None:
    """Validate the database path for security issues.

    Rejects paths containing:
    - Null bytes
    - ``..`` path traversal components
    - Symlinks (if the file already exists)

    Args:
        db_path: The filesystem path to validate.

    Raises:
        ValueError: If the path fails validation.
    """
    if "\x00" in db_path:
        raise ValueError(
            f"Invalid db_path: contains null byte. "
            f"Null bytes in file paths are a security risk."
        )

    # Check for path traversal: split on OS separator and check for '..'
    # Also check with forward slashes for cross-platform safety.
    parts = db_path.replace("\\", "/").split("/")
    if ".." in parts:
        raise ValueError(
            f"Invalid db_path '{db_path}': contains path traversal component '..'. "
            f"Database paths must not traverse parent directories."
        )

    # Reject if the path is an existing symlink
    if os.path.islink(db_path):
        raise ValueError(
            f"Invalid db_path '{db_path}': path is a symlink. "
            f"Symlinks are rejected to prevent symlink attacks."
        )


# ---------------------------------------------------------------------------
# SQL DDL
# ---------------------------------------------------------------------------

_CREATE_POSTURES_TABLE = """
CREATE TABLE IF NOT EXISTS postures (
    agent_id TEXT PRIMARY KEY,
    posture TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""

_CREATE_TRANSITIONS_TABLE = """
CREATE TABLE IF NOT EXISTS transitions (
    id INTEGER PRIMARY KEY,
    agent_id TEXT NOT NULL,
    from_posture TEXT NOT NULL,
    to_posture TEXT NOT NULL,
    success INTEGER NOT NULL,
    timestamp TEXT NOT NULL,
    metadata TEXT
)
"""


# ---------------------------------------------------------------------------
# TransitionResult serialization helpers
# ---------------------------------------------------------------------------


def _row_to_transition_result(row: sqlite3.Row) -> TransitionResult:
    """Convert a database row back to a TransitionResult.

    Args:
        row: A sqlite3.Row from the transitions table.

    Returns:
        A reconstructed TransitionResult.
    """
    metadata: Dict[str, Any] = {}
    if row["metadata"] is not None:
        metadata = json.loads(row["metadata"])

    return TransitionResult(
        success=bool(row["success"]),
        from_posture=TrustPosture(row["from_posture"]),
        to_posture=TrustPosture(row["to_posture"]),
        transition_type=_determine_transition_type(
            TrustPosture(row["from_posture"]),
            TrustPosture(row["to_posture"]),
        ),
        reason=metadata.get("_reason", ""),
        blocked_by=metadata.get("_blocked_by"),
        timestamp=datetime.fromisoformat(row["timestamp"]),
        metadata={k: v for k, v in metadata.items() if not k.startswith("_")},
    )


def _determine_transition_type(
    from_posture: TrustPosture,
    to_posture: TrustPosture,
) -> PostureTransition:
    """Determine transition type from posture levels."""
    if to_posture.autonomy_level > from_posture.autonomy_level:
        return PostureTransition.UPGRADE
    elif to_posture.autonomy_level < from_posture.autonomy_level:
        return PostureTransition.DOWNGRADE
    else:
        return PostureTransition.MAINTAIN


# ---------------------------------------------------------------------------
# SQLitePostureStore
# ---------------------------------------------------------------------------


class SQLitePostureStore:
    """SQLite-backed persistence for agent posture state.

    Stores agent postures and transition history in a local SQLite database
    with WAL mode for concurrent read performance.

    Security:
        - Rejects db_path containing ``..``, null bytes, or symlinks
        - Sets file permissions to 0o600 on POSIX systems
        - Validates all agent IDs against ``^[a-zA-Z0-9_-]+$``
        - Uses parameterized SQL for all queries
        - Bounds history queries to max 10,000 rows

    Example::

        with SQLitePostureStore("/tmp/postures.db") as store:
            store.set_posture("agent-001", TrustPosture.SUPERVISED)
            print(store.get_posture("agent-001"))

    Args:
        db_path: Path to the SQLite database file.
    """

    def __init__(self, db_path: str) -> None:
        _validate_db_path(db_path)

        self._db_path = db_path
        self._local = threading.local()
        self._closed = False

        # Create parent directories if needed
        parent = os.path.dirname(db_path)
        if parent:
            os.makedirs(parent, exist_ok=True)

        # Create the database file with restricted permissions on POSIX
        # before connecting (so connect() doesn't create it with defaults)
        if not os.path.exists(db_path):
            # Create with restricted permissions
            fd = os.open(
                db_path,
                os.O_CREAT | os.O_WRONLY,
                stat.S_IRUSR | stat.S_IWUSR,  # 0o600
            )
            os.close(fd)

        # Set permissions even if file existed (may have been created by
        # a previous run with different umask)
        if hasattr(os, "chmod"):
            os.chmod(db_path, stat.S_IRUSR | stat.S_IWUSR)

        # Initialize schema via the calling thread's connection
        conn = self._get_connection()
        conn.execute(_CREATE_POSTURES_TABLE)
        conn.execute(_CREATE_TRANSITIONS_TABLE)
        conn.commit()

        logger.info("SQLitePostureStore initialized at %s", db_path)

    # ------------------------------------------------------------------
    # Internal connection management
    # ------------------------------------------------------------------

    def _get_connection(self) -> sqlite3.Connection:
        """Return a per-thread SQLite connection, creating it if needed."""
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self._db_path)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.row_factory = sqlite3.Row
            self._local.conn = conn
        return conn

    # ------------------------------------------------------------------
    # Posture CRUD
    # ------------------------------------------------------------------

    def get_posture(self, agent_id: str) -> TrustPosture:
        """Get the current posture for an agent.

        Args:
            agent_id: The agent whose posture to retrieve.

        Returns:
            The agent's current TrustPosture, or SUPERVISED if unknown.

        Raises:
            ValueError: If agent_id is invalid.
            RuntimeError: If the store has been closed.
        """
        validate_agent_id(agent_id)
        self._require_open()

        cursor = self._get_connection().execute(
            "SELECT posture FROM postures WHERE agent_id = ?",
            (agent_id,),
        )
        row = cursor.fetchone()
        if row is None:
            return TrustPosture.SUPERVISED

        return TrustPosture(row["posture"])

    def set_posture(self, agent_id: str, posture: TrustPosture) -> None:
        """Set (upsert) the current posture for an agent.

        Args:
            agent_id: The agent whose posture to set.
            posture: The new posture value.

        Raises:
            ValueError: If agent_id is invalid.
            RuntimeError: If the store has been closed.
        """
        validate_agent_id(agent_id)
        self._require_open()

        now = datetime.now(timezone.utc).isoformat()
        conn = self._get_connection()
        conn.execute(
            "INSERT OR REPLACE INTO postures (agent_id, posture, updated_at) "
            "VALUES (?, ?, ?)",
            (agent_id, posture.value, now),
        )
        conn.commit()
        logger.debug("Set posture for agent %s to %s", agent_id, posture.value)

    # ------------------------------------------------------------------
    # Transition history
    # ------------------------------------------------------------------

    def record_transition(
        self,
        result: TransitionResult,
    ) -> None:
        """Record a posture transition in the history.

        Matches the PostureStore protocol. The agent_id is extracted from
        ``result.metadata["agent_id"]``.

        Args:
            result: The TransitionResult to persist.

        Raises:
            ValueError: If the agent_id extracted from result is invalid.
            RuntimeError: If the store has been closed.
        """
        agent_id: str = str(result.metadata.get("agent_id", ""))
        validate_agent_id(agent_id)
        self._require_open()

        # Store reason and blocked_by inside the metadata JSON so we get
        # full round-trip fidelity without adding extra columns.
        enriched_metadata = dict(result.metadata) if result.metadata else {}
        if result.reason:
            enriched_metadata["_reason"] = result.reason
        if result.blocked_by is not None:
            enriched_metadata["_blocked_by"] = result.blocked_by

        metadata_json: Optional[str] = None
        if enriched_metadata:
            metadata_json = json.dumps(enriched_metadata, default=str)

        conn = self._get_connection()
        conn.execute(
            "INSERT INTO transitions "
            "(agent_id, from_posture, to_posture, success, timestamp, metadata) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                agent_id,
                result.from_posture.value,
                result.to_posture.value,
                1 if result.success else 0,
                result.timestamp.isoformat(),
                metadata_json,
            ),
        )
        conn.commit()
        logger.debug("Recorded transition for agent %s", agent_id)

    def get_history(
        self,
        agent_id: str,
        limit: int = 100,
    ) -> List[TransitionResult]:
        """Get posture transition history for an agent.

        Returns transitions in reverse chronological order (newest first).

        Args:
            agent_id: The agent whose history to retrieve.
            limit: Maximum number of transitions to return. Capped at 10,000.

        Returns:
            List of TransitionResult objects, newest first.

        Raises:
            ValueError: If agent_id is invalid.
            RuntimeError: If the store has been closed.
        """
        validate_agent_id(agent_id)
        self._require_open()

        # Bound limit to prevent unbounded queries
        effective_limit = min(limit, _MAX_HISTORY_LIMIT)

        cursor = self._get_connection().execute(
            "SELECT agent_id, from_posture, to_posture, success, timestamp, metadata "
            "FROM transitions WHERE agent_id = ? ORDER BY id DESC LIMIT ?",
            (agent_id, effective_limit),
        )
        rows = cursor.fetchall()
        return [_row_to_transition_result(row) for row in rows]

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Close the calling thread's database connection.

        After calling close(), further operations on this thread will raise
        RuntimeError.
        """
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
            self._local.conn = None
        self._closed = True
        logger.info("SQLitePostureStore closed")

    def __enter__(self) -> SQLitePostureStore:
        """Enter the context manager."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit the context manager, closing the connection."""
        self.close()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _require_open(self) -> None:
        """Raise RuntimeError if the store has been closed."""
        if self._closed:
            raise RuntimeError(
                "SQLitePostureStore is closed. "
                "Cannot perform operations on a closed store."
            )

from __future__ import annotations

# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
SQLite-backed budget store for persisting BudgetTracker state.

Provides crash-safe, concurrent-read persistence for budget snapshots
and transaction logs using a local SQLite database in WAL mode.

Security:
- Path validation: rejects ``..``, null bytes, and symlinks
- File permissions: 0o600 on POSIX (owner read/write only)
- Parameterized SQL: all queries use ``?`` placeholders
- WAL mode: enables concurrent readers without blocking writers
- Tracker ID validation: ``^[a-zA-Z0-9_-]+$`` prevents injection

Tables:
- ``budget_snapshots``: (tracker_id TEXT PK, allocated INT, committed INT, updated_at TEXT)
- ``budget_transactions``: (id INTEGER PK, tracker_id TEXT, event_type TEXT, amount INT, timestamp TEXT)
"""

import logging
import os
import re
import sqlite3
import stat
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from kailash.trust.constraints.budget_tracker import BudgetSnapshot, BudgetTrackerError
from kailash.trust.exceptions import TrustError

logger = logging.getLogger(__name__)

__all__ = [
    "BudgetStore",
    "BudgetStoreError",
    "SQLiteBudgetStore",
]


# ---------------------------------------------------------------------------
# Exception
# ---------------------------------------------------------------------------


class BudgetStoreError(TrustError):
    """Error raised by budget store operations.

    Inherits from TrustError to integrate with the EATP exception hierarchy.
    """

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(message, details=details or {})


# ---------------------------------------------------------------------------
# BudgetStore Protocol
# ---------------------------------------------------------------------------


class BudgetStore:
    """Protocol for budget persistence backends.

    Implementations must provide:
    - ``get_snapshot(tracker_id)`` -> ``Optional[BudgetSnapshot]``
    - ``save_snapshot(tracker_id, snapshot)`` -> ``None``
    - ``get_transaction_log(tracker_id, limit=100)`` -> ``List[Dict]``
    """

    def get_snapshot(self, tracker_id: str) -> Optional[BudgetSnapshot]:
        """Load a previously saved snapshot, or None if not found."""
        raise NotImplementedError

    def save_snapshot(self, tracker_id: str, snapshot: BudgetSnapshot) -> None:
        """Persist a budget snapshot (upsert)."""
        raise NotImplementedError

    def get_transaction_log(
        self, tracker_id: str, limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Return the most recent transaction log entries."""
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

_TRACKER_ID_RE = re.compile(r"^[a-zA-Z0-9_-]+$")


def _validate_tracker_id(tracker_id: str) -> None:
    """Validate a tracker ID against injection and traversal attacks.

    Raises:
        BudgetStoreError: If the ID contains illegal characters.
    """
    if not isinstance(tracker_id, str) or not tracker_id:
        raise BudgetStoreError(
            "tracker_id must be a non-empty string",
            details={"tracker_id": repr(tracker_id)},
        )
    if "\x00" in tracker_id:
        raise BudgetStoreError(
            "tracker_id contains null byte",
            details={"tracker_id": repr(tracker_id)},
        )
    if not _TRACKER_ID_RE.match(tracker_id):
        raise BudgetStoreError(
            f"Invalid tracker_id {tracker_id!r}: must match [a-zA-Z0-9_-]+",
            details={"tracker_id": tracker_id},
        )


def _validate_db_path(db_path: str) -> None:
    """Validate a database file path against traversal and injection attacks.

    Raises:
        BudgetStoreError: If the path contains illegal components.
    """
    if not isinstance(db_path, str) or not db_path:
        raise BudgetStoreError(
            "db_path must be a non-empty string",
            details={"db_path": repr(db_path)},
        )
    if "\x00" in db_path:
        raise BudgetStoreError(
            "db_path contains null byte",
            details={"db_path": repr(db_path)},
        )
    # Check for '..' path traversal components
    # Split on both / and \ to cover all platforms
    parts = re.split(r"[/\\]", db_path)
    if ".." in parts:
        raise BudgetStoreError(
            "db_path contains '..' path traversal component",
            details={"db_path": db_path},
        )
    # Reject symlinks to prevent redirection attacks
    if os.path.islink(db_path):
        raise BudgetStoreError(
            "db_path is a symlink — refusing to follow",
            details={"db_path": db_path},
        )


# ---------------------------------------------------------------------------
# SQL DDL
# ---------------------------------------------------------------------------

_CREATE_SNAPSHOTS_SQL = """
CREATE TABLE IF NOT EXISTS budget_snapshots (
    tracker_id TEXT PRIMARY KEY,
    allocated INTEGER NOT NULL,
    committed INTEGER NOT NULL,
    updated_at TEXT NOT NULL
)
"""

_CREATE_TRANSACTIONS_SQL = """
CREATE TABLE IF NOT EXISTS budget_transactions (
    id INTEGER PRIMARY KEY,
    tracker_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    amount INTEGER NOT NULL,
    timestamp TEXT NOT NULL
)
"""

_CREATE_TRANSACTIONS_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_budget_tx_tracker
    ON budget_transactions (tracker_id, id)
"""


# ---------------------------------------------------------------------------
# SQLiteBudgetStore
# ---------------------------------------------------------------------------


class SQLiteBudgetStore(BudgetStore):
    """SQLite-backed budget store with security hardening.

    Thread safety is achieved through ``threading.local()`` giving each
    thread its own ``sqlite3.Connection``. WAL mode enables concurrent
    readers.

    Example::

        store = SQLiteBudgetStore("/tmp/eatp/budget.db")
        store.initialize()
        store.save_snapshot("agent-1", BudgetSnapshot(allocated=100, committed=50))
        snap = store.get_snapshot("agent-1")
    """

    def __init__(self, db_path: str) -> None:
        """Create a SQLiteBudgetStore.

        Args:
            db_path: Path to the SQLite database file. Must not contain
                ``..`` components or null bytes.

        Raises:
            BudgetStoreError: If the path fails validation.
        """
        _validate_db_path(db_path)
        self._db_path = db_path
        self._initialized = False
        self._closed = False
        self._local = threading.local()
        self._connections: List[sqlite3.Connection] = []
        self._conn_lock = threading.Lock()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _require_initialized(self) -> None:
        """Raise RuntimeError if the store has not been initialized."""
        if not self._initialized:
            raise RuntimeError(
                "SQLiteBudgetStore is not initialized. "
                "Call store.initialize() before performing operations."
            )

    def _get_connection(self) -> sqlite3.Connection:
        """Return a per-thread SQLite connection with WAL mode and Row factory."""
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self._db_path)
            conn.execute("PRAGMA journal_mode=WAL")
            # busy_timeout: when a concurrent writer holds the lock, wait up
            # to 5000 ms instead of returning "database is locked" immediately.
            # Without this, Windows surfaces lock contention as a hard failure
            # under any concurrent write — observed on the Trust Plane CI
            # main-branch run after merge of #474.
            conn.execute("PRAGMA busy_timeout=5000")
            conn.row_factory = sqlite3.Row
            self._local.conn = conn
            with self._conn_lock:
                self._connections.append(conn)
        return conn

    def _set_file_permissions(self) -> None:
        """Set 0o600 permissions on the database file (POSIX only)."""
        if os.name != "nt":
            try:
                os.chmod(self._db_path, stat.S_IRUSR | stat.S_IWUSR)
            except OSError:
                logger.warning("Could not set 0o600 permissions on %s", self._db_path)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def initialize(self) -> None:
        """Create the database directory, tables, indexes, and set permissions.

        Must be called before any other operation.
        """
        parent = os.path.dirname(self._db_path)
        if parent:
            os.makedirs(parent, exist_ok=True)

        conn = self._get_connection()
        conn.execute(_CREATE_SNAPSHOTS_SQL)
        conn.execute(_CREATE_TRANSACTIONS_SQL)
        conn.execute(_CREATE_TRANSACTIONS_INDEX_SQL)
        conn.commit()

        self._set_file_permissions()
        self._initialized = True
        logger.info("SQLiteBudgetStore initialized at %s", self._db_path)

    def close(self) -> None:
        """Close ALL per-thread connections and reset state."""
        with self._conn_lock:
            for conn in self._connections:
                try:
                    conn.close()
                except Exception:
                    logger.warning(
                        "Error closing budget store connection", exc_info=True
                    )
            self._connections.clear()
        self._local.conn = None
        self._initialized = False
        logger.info("SQLiteBudgetStore closed (all connections)")

    # ------------------------------------------------------------------
    # BudgetStore protocol implementation
    # ------------------------------------------------------------------

    def get_snapshot(self, tracker_id: str) -> Optional[BudgetSnapshot]:
        """Load a previously saved snapshot, or ``None`` if not found.

        Args:
            tracker_id: Identifier for the budget tracker.

        Returns:
            BudgetSnapshot if found, else None.

        Raises:
            BudgetStoreError: If tracker_id fails validation.
            RuntimeError: If the store is not initialized.
        """
        self._require_initialized()
        _validate_tracker_id(tracker_id)

        conn = self._get_connection()
        cursor = conn.execute(
            "SELECT allocated, committed FROM budget_snapshots WHERE tracker_id = ?",
            (tracker_id,),
        )
        row = cursor.fetchone()
        if row is None:
            return None

        return BudgetSnapshot(
            allocated=int(row["allocated"]),
            committed=int(row["committed"]),
        )

    def save_snapshot(self, tracker_id: str, snapshot: BudgetSnapshot) -> None:
        """Persist a budget snapshot (upsert).

        Args:
            tracker_id: Identifier for the budget tracker.
            snapshot: The BudgetSnapshot to persist.

        Raises:
            BudgetStoreError: If tracker_id fails validation.
            RuntimeError: If the store is not initialized.
        """
        self._require_initialized()
        _validate_tracker_id(tracker_id)

        now = datetime.now(timezone.utc).isoformat()
        conn = self._get_connection()
        conn.execute(
            """
            INSERT INTO budget_snapshots (tracker_id, allocated, committed, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(tracker_id) DO UPDATE SET
                allocated = excluded.allocated,
                committed = excluded.committed,
                updated_at = excluded.updated_at
            """,
            (tracker_id, snapshot.allocated, snapshot.committed, now),
        )
        conn.commit()
        logger.debug(
            "Saved budget snapshot for %s: allocated=%d, committed=%d",
            tracker_id,
            snapshot.allocated,
            snapshot.committed,
        )

    def get_transaction_log(
        self, tracker_id: str, limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Return the most recent transaction log entries for a tracker.

        Args:
            tracker_id: Identifier for the budget tracker.
            limit: Maximum number of entries to return (default 100).

        Returns:
            List of transaction dicts ordered by ascending ID.

        Raises:
            BudgetStoreError: If tracker_id fails validation.
            RuntimeError: If the store is not initialized.
        """
        self._require_initialized()
        _validate_tracker_id(tracker_id)

        if not isinstance(limit, int) or limit < 1:
            raise BudgetStoreError(
                f"limit must be a positive integer, got {limit!r}",
                details={"limit": str(limit)},
            )
        # Cap to prevent massive result sets (matches PostureStore pattern)
        limit = min(limit, 10_000)

        conn = self._get_connection()
        cursor = conn.execute(
            """
            SELECT id, tracker_id, event_type, amount, timestamp
            FROM budget_transactions
            WHERE tracker_id = ?
            ORDER BY id ASC
            LIMIT ?
            """,
            (tracker_id, limit),
        )
        rows = cursor.fetchall()
        return [
            {
                "id": row["id"],
                "tracker_id": row["tracker_id"],
                "event_type": row["event_type"],
                "amount": row["amount"],
                "timestamp": row["timestamp"],
            }
            for row in rows
        ]

    # ------------------------------------------------------------------
    # Additional helpers
    # ------------------------------------------------------------------

    def log_transaction(
        self,
        tracker_id: str,
        event_type: str,
        amount: int,
    ) -> None:
        """Append a transaction record to the persistent log.

        Args:
            tracker_id: Identifier for the budget tracker.
            event_type: Type of event (e.g., "record", "reserve").
            amount: Amount in microdollars.

        Raises:
            BudgetStoreError: If tracker_id fails validation.
            RuntimeError: If the store is not initialized.
        """
        self._require_initialized()
        _validate_tracker_id(tracker_id)

        now = datetime.now(timezone.utc).isoformat()
        conn = self._get_connection()
        conn.execute(
            """
            INSERT INTO budget_transactions (tracker_id, event_type, amount, timestamp)
            VALUES (?, ?, ?, ?)
            """,
            (tracker_id, event_type, amount, now),
        )
        conn.commit()
        logger.debug(
            "Logged transaction for %s: event=%s, amount=%d",
            tracker_id,
            event_type,
            amount,
        )

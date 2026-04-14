"""Persistent Dead Letter Queue backed by SQLite.

Provides crash-safe storage for failed workflow executions with exponential
backoff retry and bounded capacity. Items survive process restarts and are
queryable by status for monitoring and manual intervention.
"""

import json
import logging
import os
import random
import sqlite3
import stat
import threading
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Dict, List, Optional
from uuid import uuid4

logger = logging.getLogger(__name__)

# Absolute capacity limit -- oldest items are evicted when reached.
MAX_DLQ_ITEMS = 10_000

# Default base delay for exponential backoff (seconds).
DEFAULT_BASE_DELAY = 60.0

# Jitter factor applied to backoff delays (0..JITTER_FACTOR * delay).
JITTER_FACTOR = 0.25


@dataclass
class DLQItem:
    """A single dead-letter queue entry."""

    id: str
    workflow_id: str
    error: str
    payload: str
    created_at: str
    retry_count: int = 0
    max_retries: int = 3
    next_retry_at: Optional[str] = None
    status: str = "pending"

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return asdict(self)

    @classmethod
    def from_row(cls, row: Dict[str, Any]) -> "DLQItem":
        """Construct from a SQLite row dictionary."""
        return cls(
            id=row["id"],
            workflow_id=row["workflow_id"],
            error=row["error"],
            payload=row["payload"],
            created_at=row["created_at"],
            retry_count=row["retry_count"],
            max_retries=row["max_retries"],
            next_retry_at=row["next_retry_at"],
            status=row["status"],
        )


class PersistentDLQ:
    """SQLite-backed dead letter queue with bounded capacity and retry logic.

    Parameters
    ----------
    db_path:
        Filesystem path for the SQLite database.  Parent directories are
        created automatically.  On POSIX, the file is set to ``0o600``.
    base_delay:
        Base delay in seconds for exponential backoff between retries.
    """

    _VALID_STATUSES = frozenset(
        {"pending", "retrying", "succeeded", "permanent_failure"}
    )

    def __init__(
        self,
        db_path: str = "./kailash_dlq.db",
        base_delay: float = DEFAULT_BASE_DELAY,
    ) -> None:
        self._db_path = db_path
        self._base_delay = base_delay
        self._lock = threading.Lock()

        # Ensure parent directory exists.
        parent = os.path.dirname(os.path.abspath(db_path))
        os.makedirs(parent, exist_ok=True)

        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row

        self._enable_pragmas()
        self._initialize_schema()
        self._set_file_permissions()

    # ------------------------------------------------------------------
    # Setup helpers
    # ------------------------------------------------------------------

    def _enable_pragmas(self) -> None:
        cursor = self._conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        self._conn.commit()

    def _initialize_schema(self) -> None:
        # Defense-in-depth per dataflow-identifier-safety.md Rule 5: every
        # hardcoded identifier interpolated into DDL MUST route through the
        # validator at the call site. Hardcoded today; a future refactor that
        # makes the table name configurable must not silently bypass the gate.
        from kailash.db.dialect import _validate_identifier

        for ident in (
            "dlq",
            "idx_dlq_status",
            "idx_dlq_next_retry",
            "idx_dlq_created",
        ):
            _validate_identifier(ident)

        cursor = self._conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS dlq (
                id TEXT PRIMARY KEY,
                workflow_id TEXT NOT NULL,
                error TEXT NOT NULL,
                payload TEXT NOT NULL,
                created_at TEXT NOT NULL,
                retry_count INTEGER NOT NULL DEFAULT 0,
                max_retries INTEGER NOT NULL DEFAULT 3,
                next_retry_at TEXT,
                status TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'retrying', 'succeeded', 'permanent_failure'))
            )
            """
        )
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_dlq_status ON dlq(status)")
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_dlq_next_retry ON dlq(next_retry_at)"
        )
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_dlq_created ON dlq(created_at)")
        self._conn.commit()

    def _set_file_permissions(self) -> None:
        """Restrict database file to owner-only on POSIX systems."""
        if os.name == "posix":
            try:
                db_abs = os.path.abspath(self._db_path)
                os.chmod(db_abs, stat.S_IRUSR | stat.S_IWUSR)
                # WAL and SHM files inherit the same permissions when they exist.
                for suffix in ("-wal", "-shm"):
                    wal_path = db_abs + suffix
                    if os.path.exists(wal_path):
                        os.chmod(wal_path, stat.S_IRUSR | stat.S_IWUSR)
            except OSError:
                logger.warning("Could not set DLQ file permissions to 0o600")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def enqueue(
        self,
        workflow_id: str,
        error: str,
        payload: Any,
        max_retries: int = 3,
    ) -> str:
        """Add a failed item to the dead letter queue.

        Parameters
        ----------
        workflow_id:
            Identifier of the workflow that failed.
        error:
            Error message or traceback.
        payload:
            Arbitrary JSON-serialisable payload describing the failed execution.
        max_retries:
            Maximum number of automatic retry attempts before the item is
            marked ``permanent_failure``.

        Returns
        -------
        str
            The unique id assigned to the new DLQ item.
        """
        item_id = str(uuid4())
        now = datetime.now(UTC).isoformat()
        payload_str = json.dumps(payload) if not isinstance(payload, str) else payload

        with self._lock:
            self._enforce_capacity()
            cursor = self._conn.cursor()
            cursor.execute(
                """
                INSERT INTO dlq (id, workflow_id, error, payload, created_at,
                                 retry_count, max_retries, next_retry_at, status)
                VALUES (?, ?, ?, ?, ?, 0, ?, ?, 'pending')
                """,
                (item_id, workflow_id, error, payload_str, now, max_retries, now),
            )
            self._conn.commit()

        logger.info("DLQ enqueue: id=%s workflow=%s", item_id, workflow_id)
        # Re-apply permissions to WAL/SHM files created by the first write
        self._set_file_permissions()
        return item_id

    def dequeue_ready(self) -> List[DLQItem]:
        """Return items whose ``next_retry_at`` is in the past and status is ``pending``.

        Items are returned in order of ``next_retry_at`` (oldest first).
        """
        now = datetime.now(UTC).isoformat()
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                """
                SELECT * FROM dlq
                WHERE status = 'pending' AND next_retry_at <= ?
                ORDER BY next_retry_at ASC
                """,
                (now,),
            )
            rows = cursor.fetchall()
        return [DLQItem.from_row(dict(row)) for row in rows]

    def mark_retrying(self, item_id: str) -> None:
        """Transition an item to ``retrying`` status."""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                "UPDATE dlq SET status = 'retrying' WHERE id = ?",
                (item_id,),
            )
            self._conn.commit()

    def mark_success(self, item_id: str) -> None:
        """Mark an item as successfully retried.

        The item's status is set to ``succeeded``.
        """
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                "UPDATE dlq SET status = 'succeeded' WHERE id = ?",
                (item_id,),
            )
            self._conn.commit()
        logger.info("DLQ item succeeded: id=%s", item_id)

    def mark_failure(self, item_id: str) -> None:
        """Record a retry failure.

        Increments ``retry_count`` and computes the next backoff delay.  If
        ``retry_count`` reaches ``max_retries`` the item is moved to
        ``permanent_failure``.
        """
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("SELECT * FROM dlq WHERE id = ?", (item_id,))
            row = cursor.fetchone()
            if row is None:
                logger.warning("mark_failure called for unknown DLQ item %s", item_id)
                return

            item = DLQItem.from_row(dict(row))
            new_count = item.retry_count + 1

            if new_count >= item.max_retries:
                cursor.execute(
                    "UPDATE dlq SET retry_count = ?, status = 'permanent_failure' WHERE id = ?",
                    (new_count, item_id),
                )
                logger.warning(
                    "DLQ item permanently failed: id=%s retries=%d",
                    item_id,
                    new_count,
                )
            else:
                next_retry = self._calculate_next_retry(new_count)
                cursor.execute(
                    "UPDATE dlq SET retry_count = ?, next_retry_at = ?, status = 'pending' WHERE id = ?",
                    (new_count, next_retry, item_id),
                )

            self._conn.commit()

    def get_stats(self) -> Dict[str, Any]:
        """Return item counts grouped by status."""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("SELECT status, COUNT(*) FROM dlq GROUP BY status")
            counts = dict(cursor.fetchall())

        # Always include all statuses for predictable output.
        result: Dict[str, Any] = {
            "pending": counts.get("pending", 0),
            "retrying": counts.get("retrying", 0),
            "succeeded": counts.get("succeeded", 0),
            "permanent_failure": counts.get("permanent_failure", 0),
        }
        result["total"] = sum(result.values())
        return result

    def get_all(self) -> List[Dict[str, Any]]:
        """Return all items as dictionaries (for backward-compatible API)."""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("SELECT * FROM dlq ORDER BY created_at DESC")
            rows = cursor.fetchall()
        return [dict(row) for row in rows]

    def clear(self) -> None:
        """Delete all items from the queue."""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("DELETE FROM dlq")
            self._conn.commit()
        logger.info("DLQ cleared")

    def __len__(self) -> int:
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM dlq")
            return cursor.fetchone()[0]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _enforce_capacity(self) -> None:
        """Evict oldest items when at capacity.  Caller must hold ``_lock``."""
        cursor = self._conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM dlq")
        count = cursor.fetchone()[0]
        if count >= MAX_DLQ_ITEMS:
            # Delete oldest 10% to amortise eviction cost.
            to_delete = max(1, MAX_DLQ_ITEMS // 10)
            cursor.execute(
                """
                DELETE FROM dlq WHERE id IN (
                    SELECT id FROM dlq ORDER BY created_at ASC LIMIT ?
                )
                """,
                (to_delete,),
            )
            self._conn.commit()
            logger.info("DLQ capacity enforcement: evicted %d oldest items", to_delete)

    def _calculate_next_retry(self, retry_count: int) -> str:
        """Compute ISO-8601 timestamp for the next retry attempt.

        Uses exponential backoff: ``base_delay * 2^retry_count`` with additive
        random jitter up to ``JITTER_FACTOR * delay``.
        """
        delay = self._base_delay * (2**retry_count)
        jitter = random.uniform(0, JITTER_FACTOR * delay)  # noqa: S311
        next_time = datetime.now(UTC) + timedelta(seconds=delay + jitter)
        return next_time.isoformat()

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Close the underlying database connection."""
        with self._lock:
            if hasattr(self, "_conn"):
                self._conn.close()

    def __enter__(self) -> "PersistentDLQ":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> bool:
        self.close()
        return False

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass

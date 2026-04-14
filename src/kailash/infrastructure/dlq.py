# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Dialect-portable Dead Letter Queue backend using ConnectionManager.

Provides async, dialect-portable DLQ storage following the same interface
as :class:`~kailash.workflow.dlq.PersistentDLQ` but using the
:class:`~kailash.db.connection.ConnectionManager` abstraction instead of
direct ``sqlite3``.

Table: ``kailash_dlq``

Schema::

    id            TEXT PRIMARY KEY
    workflow_id   TEXT NOT NULL
    error         TEXT NOT NULL
    payload       TEXT NOT NULL
    created_at    TEXT NOT NULL          -- ISO-8601 UTC
    retry_count   INTEGER NOT NULL DEFAULT 0
    max_retries   INTEGER NOT NULL DEFAULT 3
    next_retry_at TEXT
    status        TEXT NOT NULL DEFAULT 'pending'
"""

from __future__ import annotations

import json
import logging
import random
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List
from uuid import uuid4

from kailash.db.connection import ConnectionManager

logger = logging.getLogger(__name__)

__all__ = [
    "DBDeadLetterQueue",
]

# Default base delay for exponential backoff (seconds).
DEFAULT_BASE_DELAY = 60.0

# Jitter factor applied to backoff delays.
JITTER_FACTOR = 0.25


class DBDeadLetterQueue:
    """Database-backed dead letter queue.

    Parameters
    ----------
    conn_manager:
        An initialized :class:`ConnectionManager` instance.
    base_delay:
        Base delay in seconds for exponential backoff between retries.
    """

    TABLE_NAME = "kailash_dlq"

    _VALID_STATUSES = frozenset(
        {"pending", "retrying", "succeeded", "permanent_failure"}
    )

    def __init__(
        self,
        conn_manager: ConnectionManager,
        base_delay: float = DEFAULT_BASE_DELAY,
    ) -> None:
        # Defense-in-depth per dataflow-identifier-safety.md Rule 5:
        # `TABLE_NAME` is interpolated into 12+ DML strings on every
        # operation. Validate at construction time so a subclass that
        # overrides `TABLE_NAME` is rejected immediately, not when the
        # first INSERT happens to fire. Validating once in `__init__`
        # is the single enforcement point for every interpolation site.
        from kailash.db.dialect import _validate_identifier

        _validate_identifier(self.TABLE_NAME)
        for suffix in ("status", "next_retry", "created"):
            _validate_identifier(f"idx_{self.TABLE_NAME}_{suffix}")

        self._conn = conn_manager
        self._base_delay = base_delay

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    async def initialize(self) -> None:
        """Create the DLQ table and indices if they do not exist."""
        await self._conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {self.TABLE_NAME} (
                id {self._conn.dialect.text_column(indexed=True)} PRIMARY KEY,
                workflow_id TEXT NOT NULL,
                error TEXT NOT NULL,
                payload TEXT NOT NULL,
                created_at {self._conn.dialect.text_column(indexed=True)} NOT NULL,
                retry_count INTEGER NOT NULL DEFAULT 0,
                max_retries INTEGER NOT NULL DEFAULT 3,
                next_retry_at {self._conn.dialect.text_column(indexed=True)},
                status {self._conn.dialect.text_column(indexed=True)} NOT NULL DEFAULT 'pending'
            )
            """
        )
        await self._conn.create_index(
            f"idx_{self.TABLE_NAME}_status",
            self.TABLE_NAME,
            "status",
        )
        await self._conn.create_index(
            f"idx_{self.TABLE_NAME}_next_retry",
            self.TABLE_NAME,
            "next_retry_at",
        )
        await self._conn.create_index(
            f"idx_{self.TABLE_NAME}_created",
            self.TABLE_NAME,
            "created_at",
        )
        logger.info("DLQ table '%s' initialized", self.TABLE_NAME)

    async def close(self) -> None:
        """Release any resources held by the backend.

        The underlying ConnectionManager is NOT closed here — it is
        owned by the caller and may be shared with other stores.
        """
        logger.debug("DLQ backend closed")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    async def enqueue(
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
            JSON-serializable payload. Strings are stored as-is; other types
            are ``json.dumps``-ed.
        max_retries:
            Maximum number of retry attempts before permanent failure.

        Returns
        -------
        str
            The unique ID assigned to the new DLQ item.
        """
        item_id = str(uuid4())
        now = datetime.now(timezone.utc).isoformat()
        payload_str = json.dumps(payload) if not isinstance(payload, str) else payload

        await self._conn.execute(
            f"INSERT INTO {self.TABLE_NAME} "
            f"(id, workflow_id, error, payload, created_at, "
            f"retry_count, max_retries, next_retry_at, status) "
            f"VALUES (?, ?, ?, ?, ?, 0, ?, ?, 'pending')",
            item_id,
            workflow_id,
            error,
            payload_str,
            now,
            max_retries,
            now,  # next_retry_at = now (immediately eligible)
        )

        logger.info("DLQ enqueue: id=%s workflow=%s", item_id, workflow_id)
        return item_id

    async def dequeue_ready(self) -> List[Dict[str, Any]]:
        """Return items whose ``next_retry_at`` is in the past and status is ``pending``.

        Returns
        -------
        list[dict]
            Items in order of ``next_retry_at`` (oldest first).
        """
        now = datetime.now(timezone.utc).isoformat()
        rows = await self._conn.fetch(
            f"SELECT * FROM {self.TABLE_NAME} "
            f"WHERE status = 'pending' AND next_retry_at <= ? "
            f"ORDER BY next_retry_at ASC",
            now,
        )
        return rows

    async def mark_retrying(self, item_id: str) -> None:
        """Transition an item to ``retrying`` status.

        Parameters
        ----------
        item_id:
            The DLQ item identifier.
        """
        await self._conn.execute(
            f"UPDATE {self.TABLE_NAME} SET status = 'retrying' WHERE id = ?",
            item_id,
        )

    async def mark_success(self, item_id: str) -> None:
        """Mark an item as successfully retried.

        Parameters
        ----------
        item_id:
            The DLQ item identifier.
        """
        await self._conn.execute(
            f"UPDATE {self.TABLE_NAME} SET status = 'succeeded' WHERE id = ?",
            item_id,
        )
        logger.info("DLQ item succeeded: id=%s", item_id)

    async def mark_failure(self, item_id: str) -> None:
        """Record a retry failure.

        Increments ``retry_count``. If ``retry_count`` reaches ``max_retries``,
        the item is moved to ``permanent_failure``. Otherwise it goes back
        to ``pending`` with a new ``next_retry_at`` computed via exponential
        backoff with jitter.

        Parameters
        ----------
        item_id:
            The DLQ item identifier.
        """
        row = await self._conn.fetchone(
            f"SELECT retry_count, max_retries FROM {self.TABLE_NAME} WHERE id = ?",
            item_id,
        )
        if row is None:
            logger.warning("mark_failure called for unknown DLQ item %s", item_id)
            return

        new_count = row["retry_count"] + 1

        if new_count >= row["max_retries"]:
            await self._conn.execute(
                f"UPDATE {self.TABLE_NAME} "
                f"SET retry_count = ?, status = 'permanent_failure' WHERE id = ?",
                new_count,
                item_id,
            )
            logger.warning(
                "DLQ item permanently failed: id=%s retries=%d",
                item_id,
                new_count,
            )
        else:
            next_retry = self._calculate_next_retry(new_count)
            await self._conn.execute(
                f"UPDATE {self.TABLE_NAME} "
                f"SET retry_count = ?, next_retry_at = ?, status = 'pending' "
                f"WHERE id = ?",
                new_count,
                next_retry,
                item_id,
            )

    async def get_stats(self) -> Dict[str, Any]:
        """Return item counts grouped by status.

        Returns
        -------
        dict
            Keys: ``pending``, ``retrying``, ``succeeded``,
            ``permanent_failure``, ``total``.
        """
        rows = await self._conn.fetch(
            f"SELECT status, COUNT(*) AS cnt FROM {self.TABLE_NAME} GROUP BY status"
        )
        counts = {row["status"]: row["cnt"] for row in rows}

        result: Dict[str, Any] = {
            "pending": counts.get("pending", 0),
            "retrying": counts.get("retrying", 0),
            "succeeded": counts.get("succeeded", 0),
            "permanent_failure": counts.get("permanent_failure", 0),
        }
        result["total"] = sum(result.values())
        return result

    async def clear(self) -> None:
        """Delete all items from the queue."""
        await self._conn.execute(f"DELETE FROM {self.TABLE_NAME}")
        logger.info("DLQ cleared")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _calculate_next_retry(self, retry_count: int) -> str:
        """Compute ISO-8601 timestamp for the next retry attempt.

        Uses exponential backoff: ``base_delay * 2^retry_count`` with
        additive random jitter up to ``JITTER_FACTOR * delay``.
        """
        delay = self._base_delay * (2**retry_count)
        jitter = random.uniform(0, JITTER_FACTOR * delay)  # noqa: S311
        next_time = datetime.now(timezone.utc) + timedelta(seconds=delay + jitter)
        return next_time.isoformat()

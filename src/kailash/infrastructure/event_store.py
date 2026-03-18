# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Dialect-portable EventStore backend using ConnectionManager.

Implements the :class:`~kailash.middleware.gateway.event_store_backend.EventStoreBackend`
protocol with SQL storage.  All queries use canonical ``?`` placeholders;
:class:`~kailash.db.connection.ConnectionManager` translates to the target
database dialect automatically.

Table: ``kailash_events``

Schema::

    id          INTEGER PRIMARY KEY
    stream_key  TEXT NOT NULL
    sequence    INTEGER NOT NULL
    event_type  TEXT NOT NULL
    data        TEXT NOT NULL          -- JSON-serialized event dict
    timestamp   TEXT NOT NULL          -- ISO-8601 UTC
    UNIQUE(stream_key, sequence)
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List

from kailash.db.connection import ConnectionManager

logger = logging.getLogger(__name__)

__all__ = [
    "DBEventStoreBackend",
    "EventStoreBackend",
]


class DBEventStoreBackend:
    """Database-backed event store implementing the EventStoreBackend protocol.

    Parameters
    ----------
    conn_manager:
        An initialized :class:`ConnectionManager` instance.
    """

    TABLE_NAME = "kailash_events"

    def __init__(self, conn_manager: ConnectionManager) -> None:
        self._conn = conn_manager

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    async def initialize(self) -> None:
        """Create the events table if it does not exist."""
        await self._conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {self.TABLE_NAME} (
                {self._conn.dialect.auto_id_column()},
                stream_key {self._conn.dialect.text_column(indexed=True)} NOT NULL,
                sequence INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                data TEXT NOT NULL,
                timestamp {self._conn.dialect.text_column(indexed=True)} NOT NULL,
                UNIQUE(stream_key, sequence)
            )
            """
        )
        # Index for fast lookups by stream_key
        await self._conn.create_index(
            f"idx_{self.TABLE_NAME}_stream",
            self.TABLE_NAME,
            "stream_key",
        )
        # Index for timestamp-based pruning
        await self._conn.create_index(
            f"idx_{self.TABLE_NAME}_timestamp",
            self.TABLE_NAME,
            "timestamp",
        )
        logger.info("EventStore table '%s' initialized", self.TABLE_NAME)

    async def close(self) -> None:
        """Release any resources held by the backend.

        The underlying ConnectionManager is NOT closed here — it is
        owned by the caller and may be shared with other stores.
        """
        logger.debug("EventStore backend closed")

    # ------------------------------------------------------------------
    # Protocol: append / get
    # ------------------------------------------------------------------
    async def append(self, key: str, events: List[Dict[str, Any]]) -> None:
        """Append events to a stream identified by *key*.

        Each event dict is stored as a separate row with an auto-incrementing
        sequence number within the stream.

        Parameters
        ----------
        key:
            Stream key (e.g. ``"events:request-123"``).
        events:
            List of event dictionaries.
        """
        if not events:
            return

        now = datetime.now(timezone.utc).isoformat()

        async with self._conn.transaction() as tx:
            # Determine the next sequence number atomically within txn.
            row = await tx.fetchone(
                f"SELECT COALESCE(MAX(sequence), 0) AS max_seq "
                f"FROM {self.TABLE_NAME} WHERE stream_key = ?",
                key,
            )
            next_seq = (row["max_seq"] if row else 0) + 1

            for i, event in enumerate(events):
                event_type = event.get("type", "unknown")
                data_json = json.dumps(event)
                await tx.execute(
                    f"INSERT INTO {self.TABLE_NAME} "
                    f"(stream_key, sequence, event_type, data, timestamp) "
                    f"VALUES (?, ?, ?, ?, ?)",
                    key,
                    next_seq + i,
                    event_type,
                    data_json,
                    now,
                )

        logger.debug(
            "Appended %d event(s) to stream '%s' (seq %d..%d)",
            len(events),
            key,
            next_seq,
            next_seq + len(events) - 1,
        )

    async def get(self, key: str) -> List[Dict[str, Any]]:
        """Retrieve all events for a stream, ordered by sequence.

        Parameters
        ----------
        key:
            Stream key.

        Returns
        -------
        list[dict]
            Event dictionaries in sequence order.
        """
        rows = await self._conn.fetch(
            f"SELECT data FROM {self.TABLE_NAME} "
            f"WHERE stream_key = ? ORDER BY sequence ASC",
            key,
        )
        return [json.loads(row["data"]) for row in rows]

    # ------------------------------------------------------------------
    # Extended API
    # ------------------------------------------------------------------
    async def get_after(self, key: str, after_sequence: int) -> List[Dict[str, Any]]:
        """Retrieve events with sequence strictly greater than *after_sequence*.

        Parameters
        ----------
        key:
            Stream key.
        after_sequence:
            Return only events whose sequence number is > this value.

        Returns
        -------
        list[dict]
            Matching event dictionaries in sequence order.
        """
        rows = await self._conn.fetch(
            f"SELECT data FROM {self.TABLE_NAME} "
            f"WHERE stream_key = ? AND sequence > ? ORDER BY sequence ASC",
            key,
            after_sequence,
        )
        return [json.loads(row["data"]) for row in rows]

    async def delete_before(self, timestamp: str) -> int:
        """Delete events older than the given ISO-8601 *timestamp*.

        Parameters
        ----------
        timestamp:
            ISO-8601 timestamp string. Events with ``timestamp < this`` are
            removed.

        Returns
        -------
        int
            Number of events deleted.
        """
        async with self._conn.transaction() as tx:
            count_row = await tx.fetchone(
                f"SELECT COUNT(*) AS cnt FROM {self.TABLE_NAME} WHERE timestamp < ?",
                timestamp,
            )
            deleted = count_row["cnt"] if count_row else 0

            if deleted > 0:
                await tx.execute(
                    f"DELETE FROM {self.TABLE_NAME} WHERE timestamp < ?",
                    timestamp,
                )

        if deleted > 0:
            logger.info("Deleted %d event(s) older than %s", deleted, timestamp)
        return deleted

    async def count(self, key: str) -> int:
        """Return the number of events in a stream.

        Parameters
        ----------
        key:
            Stream key.

        Returns
        -------
        int
            Event count for the stream.
        """
        row = await self._conn.fetchone(
            f"SELECT COUNT(*) AS cnt FROM {self.TABLE_NAME} WHERE stream_key = ?",
            key,
        )
        return row["cnt"] if row else 0

    async def stream_keys(self) -> List[str]:
        """Return all distinct stream keys.

        Returns
        -------
        list[str]
            Sorted list of unique stream keys.
        """
        rows = await self._conn.fetch(
            f"SELECT DISTINCT stream_key FROM {self.TABLE_NAME} "
            f"ORDER BY stream_key ASC"
        )
        return [row["stream_key"] for row in rows]


# Alias for convenience — lets callers import via the protocol name.
EventStoreBackend = DBEventStoreBackend

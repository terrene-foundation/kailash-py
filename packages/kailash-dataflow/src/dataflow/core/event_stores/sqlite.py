# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""SQLite event store adapter for audit trail persistence.

Uses aiosqlite with WAL mode for concurrent read access.
All queries use parameterized statements.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any, Dict, List, Optional

from dataflow.core.audit_events import DataFlowAuditEvent, DataFlowAuditEventType
from dataflow.core.event_store import EventStoreBackend

logger = logging.getLogger(__name__)

__all__ = ["SQLiteEventStore"]


class SQLiteEventStore(EventStoreBackend):
    """SQLite-backed event store using aiosqlite.

    Stores audit events in a local SQLite database with WAL mode
    enabled for concurrent read access. Suitable for single-process
    deployments and development/testing.

    Args:
        db_path: Path to the SQLite database file. Use ``:memory:``
            for an in-memory database (events will not survive restart).
    """

    def __init__(self, db_path: str = "audit_events.db") -> None:
        self._db_path = db_path
        self._conn: Any = None  # aiosqlite.Connection

    async def initialize(self) -> None:
        """Create the audit_events table and indexes if they don't exist."""
        try:
            import aiosqlite
        except ImportError as exc:
            raise ImportError(
                "aiosqlite is required for SQLite audit persistence. "
                "Install it with: pip install kailash"
            ) from exc

        self._conn = await aiosqlite.connect(self._db_path)

        # Enable WAL mode for concurrent reads
        await self._conn.execute("PRAGMA journal_mode=WAL")
        await self._conn.execute("PRAGMA busy_timeout=5000")
        await self._conn.execute("PRAGMA synchronous=NORMAL")
        await self._conn.execute("PRAGMA foreign_keys=ON")

        await self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS audit_events (
                id TEXT PRIMARY KEY,
                event_type TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                user_id TEXT,
                entity_type TEXT,
                entity_id TEXT,
                changes TEXT,
                metadata TEXT
            )
            """
        )

        # Create indexes for common query patterns
        await self._conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_audit_entity
            ON audit_events (entity_type, entity_id)
            """
        )
        await self._conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_audit_timestamp
            ON audit_events (timestamp)
            """
        )
        await self._conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_audit_user
            ON audit_events (user_id)
            """
        )

        await self._conn.commit()
        logger.info("SQLite audit event store initialized at %s", self._db_path)

    async def append(self, event: DataFlowAuditEvent) -> str:
        """Persist an audit event to SQLite."""
        if self._conn is None:
            raise RuntimeError("Event store not initialized. Call initialize() first.")

        event_id = str(uuid.uuid4())
        timestamp_str = event.timestamp.isoformat()
        entity_id_str = str(event.entity_id) if event.entity_id is not None else None

        await self._conn.execute(
            """
            INSERT INTO audit_events
                (id, event_type, timestamp, user_id, entity_type, entity_id, changes, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                event.event_type.value,
                timestamp_str,
                event.user_id,
                event.entity_type,
                entity_id_str,
                json.dumps(event.changes) if event.changes else "{}",
                json.dumps(event.metadata) if event.metadata else "{}",
            ),
        )
        await self._conn.commit()
        return event_id

    async def query(
        self,
        entity_type: Optional[str] = None,
        entity_id: Optional[str] = None,
        event_type: Optional[DataFlowAuditEventType] = None,
        user_id: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[DataFlowAuditEvent]:
        """Query events with parameterized filters."""
        if self._conn is None:
            raise RuntimeError("Event store not initialized. Call initialize() first.")

        conditions: List[str] = []
        params: List[Any] = []

        if entity_type is not None:
            conditions.append("entity_type = ?")
            params.append(entity_type)

        if entity_id is not None:
            conditions.append("entity_id = ?")
            params.append(str(entity_id))

        if event_type is not None:
            conditions.append("event_type = ?")
            params.append(event_type.value)

        if user_id is not None:
            conditions.append("user_id = ?")
            params.append(user_id)

        if start_time is not None:
            conditions.append("timestamp >= ?")
            params.append(start_time.isoformat())

        if end_time is not None:
            conditions.append("timestamp <= ?")
            params.append(end_time.isoformat())

        where_clause = ""
        if conditions:
            where_clause = "WHERE " + " AND ".join(conditions)

        sql = f"""
            SELECT id, event_type, timestamp, user_id, entity_type,
                   entity_id, changes, metadata
            FROM audit_events
            {where_clause}
            ORDER BY timestamp DESC
            LIMIT ? OFFSET ?
        """
        params.extend([limit, offset])

        cursor = await self._conn.execute(sql, params)
        rows = await cursor.fetchall()

        events: List[DataFlowAuditEvent] = []
        for row in rows:
            event = self._row_to_event(row)
            events.append(event)

        return events

    async def count(
        self,
        entity_type: Optional[str] = None,
        entity_id: Optional[str] = None,
        event_type: Optional[DataFlowAuditEventType] = None,
        user_id: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> int:
        """Count events matching filters."""
        if self._conn is None:
            raise RuntimeError("Event store not initialized. Call initialize() first.")

        conditions: List[str] = []
        params: List[Any] = []

        if entity_type is not None:
            conditions.append("entity_type = ?")
            params.append(entity_type)

        if entity_id is not None:
            conditions.append("entity_id = ?")
            params.append(str(entity_id))

        if event_type is not None:
            conditions.append("event_type = ?")
            params.append(event_type.value)

        if user_id is not None:
            conditions.append("user_id = ?")
            params.append(user_id)

        if start_time is not None:
            conditions.append("timestamp >= ?")
            params.append(start_time.isoformat())

        if end_time is not None:
            conditions.append("timestamp <= ?")
            params.append(end_time.isoformat())

        where_clause = ""
        if conditions:
            where_clause = "WHERE " + " AND ".join(conditions)

        sql = f"SELECT COUNT(*) FROM audit_events {where_clause}"

        cursor = await self._conn.execute(sql, params)
        row = await cursor.fetchone()
        return row[0] if row else 0

    async def close(self) -> None:
        """Close the SQLite connection."""
        if self._conn is not None:
            await self._conn.close()
            self._conn = None
            logger.info("SQLite audit event store closed")

    @staticmethod
    def _row_to_event(row: tuple) -> DataFlowAuditEvent:
        """Convert a database row to a DataFlowAuditEvent."""
        (
            _event_id,
            event_type_str,
            timestamp_str,
            user_id,
            entity_type,
            entity_id,
            changes_json,
            metadata_json,
        ) = row

        # Parse event type
        event_type = DataFlowAuditEventType.READ
        for et in DataFlowAuditEventType:
            if et.value == event_type_str:
                event_type = et
                break

        # Parse timestamp
        timestamp = datetime.fromisoformat(timestamp_str)

        # Parse JSON fields
        changes: Dict[str, Any] = {}
        if changes_json:
            changes = json.loads(changes_json)

        metadata: Dict[str, Any] = {}
        if metadata_json:
            metadata = json.loads(metadata_json)

        return DataFlowAuditEvent(
            event_type=event_type,
            timestamp=timestamp,
            user_id=user_id,
            entity_type=entity_type,
            entity_id=entity_id,
            changes=changes,
            metadata=metadata,
        )

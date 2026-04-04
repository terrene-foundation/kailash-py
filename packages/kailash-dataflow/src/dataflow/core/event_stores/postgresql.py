# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""PostgreSQL event store adapter for audit trail persistence.

Uses asyncpg for async operations with JSONB columns for changes
and metadata. Falls back with a helpful error if asyncpg is not
installed.
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

__all__ = ["PostgreSQLEventStore"]


class PostgreSQLEventStore(EventStoreBackend):
    """PostgreSQL-backed event store using asyncpg.

    Stores audit events with JSONB columns for changes and metadata,
    enabling efficient JSON queries on PostgreSQL. Uses a connection
    pool for concurrent access.

    Args:
        database_url: PostgreSQL connection URL
            (e.g., ``postgresql://user:pass@host/dbname``).
        pool_min_size: Minimum pool connections (default 2).
        pool_max_size: Maximum pool connections (default 10).
    """

    def __init__(
        self,
        database_url: str,
        pool_min_size: int = 2,
        pool_max_size: int = 10,
    ) -> None:
        self._database_url = database_url
        self._pool_min_size = pool_min_size
        self._pool_max_size = pool_max_size
        self._pool: Any = None  # asyncpg.Pool

    async def initialize(self) -> None:
        """Create the audit_events table and indexes on PostgreSQL."""
        try:
            import asyncpg
        except ImportError as exc:
            raise ImportError(
                "asyncpg is required for PostgreSQL audit persistence. "
                "Install it with: pip install asyncpg"
            ) from exc

        self._pool = await asyncpg.create_pool(
            self._database_url,
            min_size=self._pool_min_size,
            max_size=self._pool_max_size,
        )

        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS audit_events (
                    id TEXT PRIMARY KEY,
                    event_type TEXT NOT NULL,
                    timestamp TIMESTAMPTZ NOT NULL,
                    user_id TEXT,
                    entity_type TEXT,
                    entity_id TEXT,
                    changes JSONB DEFAULT '{}'::jsonb,
                    metadata JSONB DEFAULT '{}'::jsonb
                )
                """
            )

            # Create indexes for common query patterns
            await conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_audit_entity
                ON audit_events (entity_type, entity_id)
                """
            )
            await conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_audit_timestamp
                ON audit_events (timestamp)
                """
            )
            await conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_audit_user
                ON audit_events (user_id)
                """
            )

        logger.info("PostgreSQL audit event store initialized")

    async def append(self, event: DataFlowAuditEvent) -> str:
        """Persist an audit event to PostgreSQL."""
        if self._pool is None:
            raise RuntimeError("Event store not initialized. Call initialize() first.")

        event_id = str(uuid.uuid4())
        entity_id_str = str(event.entity_id) if event.entity_id is not None else None
        changes_json = json.dumps(event.changes) if event.changes else "{}"
        metadata_json = json.dumps(event.metadata) if event.metadata else "{}"

        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO audit_events
                    (id, event_type, timestamp, user_id, entity_type,
                     entity_id, changes, metadata)
                VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8::jsonb)
                """,
                event_id,
                event.event_type.value,
                event.timestamp,
                event.user_id,
                event.entity_type,
                entity_id_str,
                changes_json,
                metadata_json,
            )

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
        """Query events with parameterized filters on PostgreSQL."""
        if self._pool is None:
            raise RuntimeError("Event store not initialized. Call initialize() first.")

        conditions: List[str] = []
        params: List[Any] = []
        param_idx = 1

        if entity_type is not None:
            conditions.append(f"entity_type = ${param_idx}")
            params.append(entity_type)
            param_idx += 1

        if entity_id is not None:
            conditions.append(f"entity_id = ${param_idx}")
            params.append(str(entity_id))
            param_idx += 1

        if event_type is not None:
            conditions.append(f"event_type = ${param_idx}")
            params.append(event_type.value)
            param_idx += 1

        if user_id is not None:
            conditions.append(f"user_id = ${param_idx}")
            params.append(user_id)
            param_idx += 1

        if start_time is not None:
            conditions.append(f"timestamp >= ${param_idx}")
            params.append(start_time)
            param_idx += 1

        if end_time is not None:
            conditions.append(f"timestamp <= ${param_idx}")
            params.append(end_time)
            param_idx += 1

        where_clause = ""
        if conditions:
            where_clause = "WHERE " + " AND ".join(conditions)

        sql = f"""
            SELECT id, event_type, timestamp, user_id, entity_type,
                   entity_id, changes, metadata
            FROM audit_events
            {where_clause}
            ORDER BY timestamp DESC
            LIMIT ${param_idx} OFFSET ${param_idx + 1}
        """
        params.extend([limit, offset])

        async with self._pool.acquire() as conn:
            rows = await conn.fetch(sql, *params)

        events: List[DataFlowAuditEvent] = []
        for row in rows:
            event = self._record_to_event(row)
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
        """Count events matching filters on PostgreSQL."""
        if self._pool is None:
            raise RuntimeError("Event store not initialized. Call initialize() first.")

        conditions: List[str] = []
        params: List[Any] = []
        param_idx = 1

        if entity_type is not None:
            conditions.append(f"entity_type = ${param_idx}")
            params.append(entity_type)
            param_idx += 1

        if entity_id is not None:
            conditions.append(f"entity_id = ${param_idx}")
            params.append(str(entity_id))
            param_idx += 1

        if event_type is not None:
            conditions.append(f"event_type = ${param_idx}")
            params.append(event_type.value)
            param_idx += 1

        if user_id is not None:
            conditions.append(f"user_id = ${param_idx}")
            params.append(user_id)
            param_idx += 1

        if start_time is not None:
            conditions.append(f"timestamp >= ${param_idx}")
            params.append(start_time)
            param_idx += 1

        if end_time is not None:
            conditions.append(f"timestamp <= ${param_idx}")
            params.append(end_time)
            param_idx += 1

        where_clause = ""
        if conditions:
            where_clause = "WHERE " + " AND ".join(conditions)

        sql = f"SELECT COUNT(*) FROM audit_events {where_clause}"

        async with self._pool.acquire() as conn:
            result = await conn.fetchval(sql, *params)

        return result or 0

    async def close(self) -> None:
        """Close the connection pool."""
        if self._pool is not None:
            await self._pool.close()
            self._pool = None
            logger.info("PostgreSQL audit event store closed")

    @staticmethod
    def _record_to_event(row: Any) -> DataFlowAuditEvent:
        """Convert an asyncpg Record to a DataFlowAuditEvent."""
        event_type_str = row["event_type"]

        # Parse event type
        event_type = DataFlowAuditEventType.READ
        for et in DataFlowAuditEventType:
            if et.value == event_type_str:
                event_type = et
                break

        # Parse JSON fields — asyncpg returns JSONB as dicts directly
        changes = row["changes"]
        if isinstance(changes, str):
            changes = json.loads(changes)
        metadata = row["metadata"]
        if isinstance(metadata, str):
            metadata = json.loads(metadata)

        return DataFlowAuditEvent(
            event_type=event_type,
            timestamp=row["timestamp"],
            user_id=row["user_id"],
            entity_type=row["entity_type"],
            entity_id=row["entity_id"],
            changes=changes or {},
            metadata=metadata or {},
        )

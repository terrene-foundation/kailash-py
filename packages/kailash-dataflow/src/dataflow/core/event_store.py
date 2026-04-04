# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""EventStoreBackend — abstract base class for audit event persistence.

Defines the contract for persisting and querying DataFlow audit events.
Implementations include SQLite (bundled) and PostgreSQL (optional).
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, List, Optional

from dataflow.core.audit_events import DataFlowAuditEvent, DataFlowAuditEventType

logger = logging.getLogger(__name__)

__all__ = ["EventStoreBackend"]


class EventStoreBackend(ABC):
    """Abstract base class for audit event persistence backends.

    Implementations must handle:
    - Table/index creation on ``initialize()``
    - Event serialization and storage on ``append()``
    - Filtered queries with pagination on ``query()``
    - Counting with the same filter semantics on ``count()``
    - Clean resource teardown on ``close()``
    """

    @abstractmethod
    async def initialize(self) -> None:
        """Create tables and indexes if they do not exist.

        Called automatically during ``DataFlow.start()`` when
        ``audit=True``. Must be idempotent.
        """

    @abstractmethod
    async def append(self, event: DataFlowAuditEvent) -> str:
        """Persist a single audit event.

        Args:
            event: The audit event to store.

        Returns:
            The event ID (UUID string) assigned to the persisted record.
        """

    @abstractmethod
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
        """Query stored events with optional filters.

        All filter parameters are AND-combined. Omitted filters match
        everything.

        Args:
            entity_type: Filter by entity/model type.
            entity_id: Filter by entity/record ID.
            event_type: Filter by audit event type enum.
            user_id: Filter by acting user ID.
            start_time: Include events at or after this timestamp.
            end_time: Include events at or before this timestamp.
            limit: Maximum number of events to return (default 100).
            offset: Number of events to skip for pagination.

        Returns:
            List of matching events ordered by timestamp descending.
        """

    @abstractmethod
    async def count(
        self,
        entity_type: Optional[str] = None,
        entity_id: Optional[str] = None,
        event_type: Optional[DataFlowAuditEventType] = None,
        user_id: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> int:
        """Count events matching the given filters.

        Accepts the same filter parameters as ``query()`` (minus
        pagination).

        Returns:
            Number of matching events.
        """

    @abstractmethod
    async def close(self) -> None:
        """Release connections and clean up resources.

        Must be safe to call multiple times.
        """

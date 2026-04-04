"""DataFlow Audit Integration Module."""

import logging
from datetime import UTC, datetime
from typing import Any, Dict, List, Optional

from .audit_events import DataFlowAuditEvent, DataFlowAuditEventType
from .event_store import EventStoreBackend

logger = logging.getLogger(__name__)


class AuditIntegration:
    """Handles integration of audit functionality with DataFlow operations.

    When constructed with an ``EventStoreBackend``, events are persisted
    to the backend in addition to the in-memory list.  Without a backend,
    the class behaves identically to the original in-memory-only
    implementation (full backward compatibility).
    """

    def __init__(
        self,
        enabled: bool = True,
        backend: Optional[EventStoreBackend] = None,
    ):
        self.enabled = enabled
        self.events: List[DataFlowAuditEvent] = []
        self._backend = backend
        self.webhook_url: Optional[str] = None
        self.db_config: Optional[Dict[str, Any]] = None
        self.log_file: Optional[str] = None
        self.event_filter: Optional[List[DataFlowAuditEventType]] = None
        self.excluded_users: List[str] = []
        self.batch_size: int = 100
        self.flush_interval: int = 300
        self.max_retries: int = 3
        self.retry_delay: float = 1.0
        self.dead_letter_queue: bool = False

    @property
    def backend(self) -> Optional[EventStoreBackend]:
        """Access the persistence backend, if configured."""
        return self._backend

    def log_event(
        self,
        event_type: DataFlowAuditEventType,
        entity_type: Optional[str] = None,
        entity_id: Optional[Any] = None,
        changes: Optional[Dict[str, Any]] = None,
        user_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[DataFlowAuditEvent]:
        """Log an audit event.

        The event is always appended to the in-memory list.  When a
        persistence backend is configured, ``backend.append()`` is
        scheduled but failures are logged rather than raised so that
        audit persistence never blocks the data path.
        """
        if not self.enabled:
            return None

        event = DataFlowAuditEvent(
            event_type=event_type,
            timestamp=datetime.now(UTC),
            user_id=user_id,
            entity_type=entity_type,
            entity_id=entity_id,
            changes=changes,
            metadata=metadata,
        )

        self.events.append(event)

        # Fire-and-forget persist to backend when available.
        # We import asyncio lazily to avoid top-level import cost when
        # no backend is configured.
        if self._backend is not None:
            self._persist_event(event)

        return event

    def _persist_event(self, event: DataFlowAuditEvent) -> None:
        """Best-effort persist to the backend.

        Attempts to schedule an async append on the running event loop.
        If no loop is running, the event is still in the in-memory list
        and will be available via ``get_events()``.
        """
        import asyncio

        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._async_persist(event))
        except RuntimeError:
            # No running event loop — skip async persist.
            # Event is already in self.events.
            logger.debug("No running event loop; audit event stored in-memory only")

    async def _async_persist(self, event: DataFlowAuditEvent) -> None:
        """Async helper to append an event to the backend."""
        try:
            await self._backend.append(event)
        except Exception:
            logger.exception("Failed to persist audit event to backend")

    def get_events(
        self,
        event_type: Optional[DataFlowAuditEventType] = None,
        entity_type: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> List[DataFlowAuditEvent]:
        """Retrieve filtered audit events from the in-memory list."""
        filtered_events = self.events

        if event_type:
            filtered_events = [e for e in filtered_events if e.event_type == event_type]

        if entity_type:
            filtered_events = [
                e for e in filtered_events if e.entity_type == entity_type
            ]

        if start_time:
            filtered_events = [e for e in filtered_events if e.timestamp >= start_time]

        if end_time:
            filtered_events = [e for e in filtered_events if e.timestamp <= end_time]

        return filtered_events

    async def get_trail(
        self,
        entity_type: str,
        entity_id: str,
    ) -> List[DataFlowAuditEvent]:
        """Convenience method: retrieve the full audit trail for an entity.

        Queries the persistence backend when available, otherwise falls
        back to the in-memory event list.

        Args:
            entity_type: Model/entity type name.
            entity_id: The entity's primary key (as string).

        Returns:
            List of events for this entity, newest first.
        """
        if self._backend is not None:
            return await self._backend.query(
                entity_type=entity_type,
                entity_id=entity_id,
            )
        # Fallback to in-memory
        return [
            e
            for e in reversed(self.events)
            if e.entity_type == entity_type and str(e.entity_id) == str(entity_id)
        ]

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
        """Forward a rich query to the persistence backend.

        If no backend is configured, falls back to in-memory filtering
        (with limit/offset applied manually).
        """
        if self._backend is not None:
            return await self._backend.query(
                entity_type=entity_type,
                entity_id=entity_id,
                event_type=event_type,
                user_id=user_id,
                start_time=start_time,
                end_time=end_time,
                limit=limit,
                offset=offset,
            )

        # In-memory fallback with basic filtering
        results = self.get_events(
            event_type=event_type,
            entity_type=entity_type,
            start_time=start_time,
            end_time=end_time,
        )
        # Apply user_id filter
        if user_id is not None:
            results = [e for e in results if e.user_id == user_id]
        # Apply entity_id filter
        if entity_id is not None:
            results = [e for e in results if str(e.entity_id) == str(entity_id)]
        # Apply pagination
        return list(reversed(results))[offset : offset + limit]

    def clear_events(self):
        """Clear all stored events."""
        self.events.clear()

    def configure_webhook(self, webhook_url: str):
        """Configure webhook URL for audit events."""
        self.webhook_url = webhook_url

    def configure_database_logging(self, db_config: Dict[str, Any]):
        """Configure database logging settings."""
        self.db_config = db_config

    def configure_file_logging(self, log_file: str):
        """Configure file logging path."""
        self.log_file = log_file

    def configure_event_filter(self, event_types: List[DataFlowAuditEventType]):
        """Configure which event types to log."""
        self.event_filter = event_types

    def configure_user_filter(self, exclude_users: List[str]):
        """Configure user-based filtering."""
        self.excluded_users = exclude_users

    def configure_batch_processing(self, batch_size: int, flush_interval: int):
        """Configure batch processing settings."""
        self.batch_size = batch_size
        self.flush_interval = flush_interval

    def configure_error_handling(
        self, max_retries: int, retry_delay: float, dead_letter_queue: bool
    ):
        """Configure error handling settings."""
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.dead_letter_queue = dead_letter_queue

    def should_log_event(self, event: DataFlowAuditEvent) -> bool:
        """Check if an event should be logged based on filters."""
        # Check event type filter
        if self.event_filter and event.event_type not in self.event_filter:
            return False

        # Check user filter
        if event.user_id and event.user_id in self.excluded_users:
            return False

        return True

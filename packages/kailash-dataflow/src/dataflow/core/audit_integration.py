"""DataFlow Audit Integration Module."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from .audit_events import DataFlowAuditEvent, DataFlowAuditEventType


class AuditIntegration:
    """Handles integration of audit functionality with DataFlow operations."""

    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self.events: List[DataFlowAuditEvent] = []
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

    def log_event(
        self,
        event_type: DataFlowAuditEventType,
        entity_type: Optional[str] = None,
        entity_id: Optional[Any] = None,
        changes: Optional[Dict[str, Any]] = None,
        user_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[DataFlowAuditEvent]:
        """Log an audit event."""
        if not self.enabled:
            return None

        event = DataFlowAuditEvent(
            event_type=event_type,
            timestamp=datetime.utcnow(),
            user_id=user_id,
            entity_type=entity_type,
            entity_id=entity_id,
            changes=changes,
            metadata=metadata,
        )

        self.events.append(event)
        return event

    def get_events(
        self,
        event_type: Optional[DataFlowAuditEventType] = None,
        entity_type: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> List[DataFlowAuditEvent]:
        """Retrieve filtered audit events."""
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

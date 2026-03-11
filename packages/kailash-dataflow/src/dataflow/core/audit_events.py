"""DataFlow Audit Events Module."""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional


class DataFlowAuditEventType(Enum):
    """Types of audit events in DataFlow."""

    CREATE = "CREATE"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    READ = "READ"
    BULK_CREATE = "BULK_CREATE"
    BULK_UPDATE = "BULK_UPDATE"
    BULK_DELETE = "BULK_DELETE"
    TRANSACTION_START = "TRANSACTION_START"
    TRANSACTION_COMMIT = "TRANSACTION_COMMIT"
    TRANSACTION_ROLLBACK = "TRANSACTION_ROLLBACK"
    SCHEMA_CHANGE = "SCHEMA_CHANGE"
    MIGRATION = "MIGRATION"
    SECURITY_EVENT = "SECURITY_EVENT"
    PERFORMANCE_EVENT = "PERFORMANCE_EVENT"


class DataFlowAuditEvent:
    """Represents an audit event in the DataFlow system."""

    def __init__(
        self,
        event_type: DataFlowAuditEventType,
        timestamp: Optional[datetime] = None,
        user_id: Optional[str] = None,
        entity_type: Optional[str] = None,
        entity_id: Optional[Any] = None,
        changes: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        model_name: Optional[str] = None,  # Accept model_name as alias
        record_id: Optional[Any] = None,  # Accept record_id as alias
    ):
        self.event_type = event_type
        self.timestamp = timestamp or datetime.utcnow()
        self.user_id = user_id
        # Handle both entity_type and model_name
        self.entity_type = entity_type or model_name
        # Handle both entity_id and record_id
        self.entity_id = entity_id or record_id
        self.changes = changes if changes is not None else {}
        self.metadata = metadata or {}

    @property
    def model_name(self) -> Optional[str]:
        """Alias for entity_type for compatibility."""
        return self.entity_type

    @property
    def record_id(self) -> Optional[Any]:
        """Alias for entity_id for compatibility."""
        return self.entity_id

    def to_dict(self) -> Dict[str, Any]:
        """Convert audit event to dictionary."""
        return {
            "event_type": self.event_type.value,
            "timestamp": self.timestamp.isoformat(),
            "user_id": self.user_id,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "changes": self.changes,
            "metadata": self.metadata,
            # Include aliases for compatibility
            "model_name": self.entity_type,
            "record_id": self.entity_id,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DataFlowAuditEvent":
        """Create audit event from dictionary."""
        # Parse event type
        event_type_str = data.get("event_type", "READ")
        # Handle both uppercase and lowercase
        event_type_str = event_type_str.upper() if event_type_str else "READ"
        event_type = DataFlowAuditEventType.READ
        for et in DataFlowAuditEventType:
            if et.value == event_type_str:
                event_type = et
                break

        # Parse timestamp
        timestamp_str = data.get("timestamp")
        if isinstance(timestamp_str, str):
            timestamp = datetime.fromisoformat(timestamp_str)
        else:
            timestamp = timestamp_str or datetime.utcnow()

        return cls(
            event_type=event_type,
            timestamp=timestamp,
            user_id=data.get("user_id"),
            entity_type=data.get("entity_type") or data.get("model_name"),
            entity_id=data.get("entity_id") or data.get("record_id"),
            changes=data.get("changes"),
            metadata=data.get("metadata"),
        )

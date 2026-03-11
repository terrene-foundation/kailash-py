"""DataFlow Audit Trail Manager Module."""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from .audit_events import DataFlowAuditEvent, DataFlowAuditEventType
from .audit_integration import AuditIntegration


class AuditTrailManager:
    """Manages audit trails for DataFlow operations."""

    def __init__(
        self,
        storage_path: Optional[Union[str, Path]] = None,
        retention_days: int = 90,
        max_events: int = 10000,
    ):
        self.storage_path = Path(storage_path) if storage_path else None
        self.retention_days = retention_days
        self.max_events = max_events
        self.integration = AuditIntegration()

    def record_operation(
        self,
        operation_type: str,
        model_name: str,
        record_id: Optional[Any] = None,
        changes: Optional[Dict[str, Any]] = None,
        user_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> DataFlowAuditEvent:
        """Record a database operation in the audit trail."""
        # Map operation type to audit event type (handle both cases)
        op_type_lower = operation_type.lower()
        event_type_map = {
            "create": DataFlowAuditEventType.CREATE,
            "update": DataFlowAuditEventType.UPDATE,
            "delete": DataFlowAuditEventType.DELETE,
            "read": DataFlowAuditEventType.READ,
            "bulk_create": DataFlowAuditEventType.BULK_CREATE,
            "bulk_update": DataFlowAuditEventType.BULK_UPDATE,
            "bulk_delete": DataFlowAuditEventType.BULK_DELETE,
        }

        event_type = event_type_map.get(
            operation_type.lower(), DataFlowAuditEventType.READ
        )

        return self.integration.log_event(
            event_type=event_type,
            entity_type=model_name,
            entity_id=record_id,
            changes=changes,
            user_id=user_id,
            metadata=metadata,
        )

    def get_audit_trail(
        self,
        model_name: Optional[str] = None,
        operation_type: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Retrieve audit trail with filtering options."""
        # Convert operation type to event type
        event_type = None
        if operation_type:
            event_type_map = {
                "create": DataFlowAuditEventType.CREATE,
                "update": DataFlowAuditEventType.UPDATE,
                "delete": DataFlowAuditEventType.DELETE,
                "read": DataFlowAuditEventType.READ,
            }
            event_type = event_type_map.get(operation_type.lower())

        events = self.integration.get_events(
            event_type=event_type,
            entity_type=model_name,
            start_time=start_date,
            end_time=end_date,
        )

        # Convert to dictionaries
        trail = [event.to_dict() for event in events]

        # Apply limit if specified
        if limit:
            trail = trail[:limit]

        return trail

    def export_audit_trail(
        self, output_path: Union[str, Path], format: str = "json"
    ) -> int:
        """Export audit trail to file."""
        trail = self.get_audit_trail()

        output_path = Path(output_path)

        if format == "json":
            with open(output_path, "w") as f:
                json.dump(trail, f, indent=2)
        else:
            raise ValueError(f"Unsupported export format: {format}")

        return len(trail)

    def cleanup_old_events(self) -> int:
        """Remove events older than retention period."""
        if self.retention_days <= 0:
            return 0

        cutoff_date = datetime.utcnow().timestamp() - (
            self.retention_days * 24 * 60 * 60
        )
        initial_count = len(self.integration.events)

        self.integration.events = [
            event
            for event in self.integration.events
            if event.timestamp.timestamp() > cutoff_date
        ]

        return initial_count - len(self.integration.events)

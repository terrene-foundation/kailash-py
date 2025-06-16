"""
AuditLogNode - Centralized audit logging for middleware operations
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict

from kailash.nodes.base import Node, NodeParameter, register_node


@register_node()
class AuditLogNode(Node):
    """Node for structured audit logging with enterprise features."""

    def __init__(
        self,
        name: str,
        log_level: str = "INFO",
        include_timestamp: bool = True,
        output_format: str = "json",
        **kwargs,
    ):
        super().__init__(name=name, **kwargs)
        self.log_level = log_level
        self.include_timestamp = include_timestamp
        self.output_format = output_format
        self.logger = logging.getLogger(f"audit.{name}")

        # Set logger level
        level = getattr(logging, log_level.upper(), logging.INFO)
        self.logger.setLevel(level)

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Define parameters for audit logging."""
        return {
            "event_data": NodeParameter(
                name="event_data",
                type=dict,
                description="Event data to log",
                default=None,
            ),
            "event_type": NodeParameter(
                name="event_type",
                type=str,
                description="Type of event being logged",
                default="info",
            ),
            "user_id": NodeParameter(
                name="user_id",
                type=str,
                description="ID of user associated with event",
                default=None,
            ),
            "message": NodeParameter(
                name="message",
                type=str,
                description="Log message",
                default="",
            ),
        }

    def execute(self, **inputs) -> Dict[str, Any]:
        """Execute audit logging."""
        event_data = inputs.get("event_data", {})
        event_type = inputs.get("event_type", "info")
        user_id = inputs.get("user_id")
        message = inputs.get("message", "")

        # Create audit entry
        audit_entry = {
            "event_type": event_type,
            "message": message,
            "user_id": user_id,
            "data": event_data,
        }

        if self.include_timestamp:
            audit_entry["timestamp"] = datetime.now(timezone.utc).isoformat()

        # Log the event
        if self.output_format == "json":
            log_message = json.dumps(audit_entry)
        else:
            log_message = (
                f"[{event_type}] {message} - User: {user_id} - Data: {event_data}"
            )

        # Use appropriate log level
        if event_type in ["error", "critical"]:
            self.logger.error(log_message)
        elif event_type == "warning":
            self.logger.warning(log_message)
        else:
            self.logger.info(log_message)

        return {
            "audit_entry": audit_entry,
            "logged": True,
            "log_level": event_type,
            "timestamp": audit_entry.get("timestamp"),
        }

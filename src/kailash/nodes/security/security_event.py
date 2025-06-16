"""
SecurityEventNode - Security event processing and monitoring
"""

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from kailash.nodes.base import Node, NodeParameter, register_node


class SeverityLevel(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"


@dataclass
class SecurityEvent:
    event_type: str
    severity: SeverityLevel
    message: str
    user_id: Optional[str] = None
    resource_id: Optional[str] = None
    timestamp: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    source: Optional[str] = None
    session_id: Optional[str] = None
    correlation_id: Optional[str] = None


@register_node()
class SecurityEventNode(Node):
    """Node for security event processing and monitoring."""

    def __init__(
        self,
        name: str,
        alert_threshold: str = "HIGH",
        enable_real_time: bool = True,
        **kwargs,
    ):
        super().__init__(name=name, **kwargs)
        self.alert_threshold = SeverityLevel(alert_threshold)
        self.enable_real_time = enable_real_time
        self.logger = logging.getLogger(f"security.{name}")

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Define parameters for security event processing."""
        return {
            "event_type": NodeParameter(
                name="event_type",
                type=str,
                description="Type of security event",
                default="security_check",
            ),
            "severity": NodeParameter(
                name="severity",
                type=str,
                description="Event severity level",
                default="INFO",
            ),
            "message": NodeParameter(
                name="message",
                type=str,
                description="Security event message",
                default="",
            ),
            "user_id": NodeParameter(
                name="user_id",
                type=str,
                description="User ID associated with event",
                default=None,
            ),
            "metadata": NodeParameter(
                name="metadata",
                type=dict,
                description="Additional event metadata",
                default=None,
            ),
        }

    def execute(self, **inputs) -> Dict[str, Any]:
        """Execute security event processing."""
        event_type = inputs.get("event_type", "security_check")
        severity = SeverityLevel(inputs.get("severity", "INFO"))
        message = inputs.get("message", "")
        user_id = inputs.get("user_id")
        metadata = inputs.get("metadata", {})

        # Create security event
        security_event = SecurityEvent(
            event_type=event_type,
            severity=severity,
            message=message,
            user_id=user_id,
            metadata=metadata,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

        # Log the event
        log_message = f"[{severity.value}] {event_type}: {message}"
        if user_id:
            log_message += f" (User: {user_id})"

        # Use appropriate log level based on severity
        if severity in [SeverityLevel.CRITICAL, SeverityLevel.HIGH]:
            self.logger.error(log_message)
        elif severity == SeverityLevel.MEDIUM:
            self.logger.warning(log_message)
        else:
            self.logger.info(log_message)

        # Check for alerting
        should_alert = severity.value >= self.alert_threshold.value

        return {
            "security_event": {
                "event_type": security_event.event_type,
                "severity": security_event.severity.value,
                "message": security_event.message,
                "user_id": security_event.user_id,
                "timestamp": security_event.timestamp,
                "metadata": security_event.metadata,
            },
            "alert_triggered": should_alert,
            "logged": True,
        }

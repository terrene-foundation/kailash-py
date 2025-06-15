"""
SecurityEventNode - Security event monitoring and alerting
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional

from kailash.nodes.base import Node, NodeParameter, register_node


class SeverityLevel(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"


@dataclass
class SecurityEvent:
    """Represents a security event."""

    event_type: str
    severity: SeverityLevel
    timestamp: datetime
    source: str
    description: str
    details: Dict[str, Any]
    user_id: Optional[str] = None
    ip_address: Optional[str] = None
    session_id: Optional[str] = None
    correlation_id: Optional[str] = None


@register_node()
class SecurityEventNode(Node):
    """Node for security event processing and monitoring."""

    def __init__(
        self,
        name: str,
        severity_threshold: str = "INFO",
        enable_alerting: bool = False,
        **kwargs,
    ):
        super().__init__(name=name, **kwargs)
        self.severity_threshold = SeverityLevel(severity_threshold)
        self.enable_alerting = enable_alerting
        self.logger = logging.getLogger(f"security.{name}")

    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            "event_type": NodeParameter(
                name="event_type",
                type=str,
                required=True,
                description="Type of security event",
            ),
            "severity": NodeParameter(
                name="severity",
                type=str,
                required=True,
                description="Event severity level",
            ),
            "details": NodeParameter(
                name="details",
                type=dict,
                required=False,
                description="Security event details",
            ),
        }

    def process(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Process security event."""

        event_type = inputs.get("event_type")
        severity = SeverityLevel(inputs.get("severity", "INFO"))
        details = inputs.get("details", {})

        security_event = {
            "event_type": event_type,
            "severity": severity.value,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "details": details,
        }

        # Log security event
        self.logger.warning(f"SECURITY: {event_type} [{severity.value}] - {details}")

        # Trigger alerts if needed
        alert_triggered = False
        if self.enable_alerting and self._should_alert(severity):
            alert_triggered = self._trigger_alert(security_event)

        return {
            "event_processed": True,
            "event": security_event,
            "alert_triggered": alert_triggered,
        }

    def _should_alert(self, severity: SeverityLevel) -> bool:
        """Determine if alert should be triggered."""
        severity_order = {
            SeverityLevel.INFO: 0,
            SeverityLevel.LOW: 1,
            SeverityLevel.MEDIUM: 2,
            SeverityLevel.HIGH: 3,
            SeverityLevel.CRITICAL: 4,
        }

        return severity_order[severity] >= severity_order[self.severity_threshold]

    def _trigger_alert(self, event: Dict[str, Any]) -> bool:
        """Trigger security alert (placeholder)."""
        # In production, this would integrate with alerting systems
        self.logger.critical(f"SECURITY ALERT: {event}")
        return True

    def run(self, **kwargs) -> Dict[str, Any]:
        """Alias for process method."""
        return self.process(kwargs)

    def execute(self, **kwargs) -> Dict[str, Any]:
        """Alias for process method."""
        return self.process(kwargs)

    async def async_run(self, **kwargs) -> Dict[str, Any]:
        """Async execution method for enterprise integration."""
        return self.run(**kwargs)

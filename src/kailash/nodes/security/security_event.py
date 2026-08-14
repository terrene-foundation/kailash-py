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
from kailash.utils.secure_logging import sanitize_log_structure, sanitize_log_value


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

    def run(self, **kwargs) -> Dict[str, Any]:
        """Execute the node's logic (Node ABC contract)."""
        return self.execute(**kwargs)

    @staticmethod
    def _coerce_severity(raw: Any) -> SeverityLevel:
        """Resolve a caller-supplied severity, failing CLOSED on an unknown one.

        ``SeverityLevel(raw)`` raised ``ValueError`` for anything that was not
        an exact member name, and that exception propagated out of a SECURITY
        sink: the event was never recorded, and the caller saw a crash instead
        of a log line. A sink that drops the record on a malformed severity is
        the worst of both outcomes.

        Case is normalized first, because callers in this repo pass ``"info"``
        and ``"warning"`` (``middleware/core/workflows.py``). A value that is
        still unrecognized ranks TIGHTEST -- CRITICAL, not INFO -- so a typo
        makes an event LOUDER rather than silently downgrading a real
        CRITICAL to below every alert threshold (``rules/security.md``
        § Enforcement-Surface Parity: unrecognized values rank tightest).
        """
        if isinstance(raw, SeverityLevel):
            return raw
        try:
            return SeverityLevel(str(raw).strip().upper())
        except (ValueError, TypeError, AttributeError):
            logging.getLogger(__name__).warning(
                "Unrecognized security severity %r; treating as CRITICAL",
                sanitize_log_value(raw, 64),
            )
            return SeverityLevel.CRITICAL

    def execute(self, **inputs) -> Dict[str, Any]:
        """Execute security event processing."""
        # SINK-LEVEL SANITIZING (issue #2088).
        #
        # Every caller-controlled field is flattened and bounded HERE, at the
        # choke point every caller passes through, rather than at each of the
        # ~30 call sites. The per-call-site approach was measured to drift: a
        # sweep during #2066's own review found two raw ``user_id`` sites the
        # author's manual enumeration had missed, within a single branch,
        # under active review, by the person who had just written the helper.
        # Nothing structurally prevented call site N+1 from omitting it.
        #
        # ``message`` is sanitized too, not just the identifier fields. The
        # #2066 sweep caught the ``message=`` f-string carrying the same raw
        # value that the ``user_id=`` kwarg beside it had already sanitized --
        # so a fix scoped to identifier fields would reproduce the original
        # defect on the field that actually drifted.
        #
        # ``metadata`` is sanitized recursively because this node returns it
        # and downstream consumers render it; a nested string is a record
        # field exactly as a top-level one is.
        event_type = sanitize_log_value(inputs.get("event_type", "security_check"), 128)
        severity = self._coerce_severity(inputs.get("severity", "INFO"))
        message = sanitize_log_value(inputs.get("message", ""), 512)
        raw_user_id = inputs.get("user_id")
        # Preserve the None/absent distinction: a sanitized ``None`` would be
        # the string "None" and would render "(User: None)" on every anonymous
        # event, and would make the `if user_id:` branch below always true.
        user_id = None if raw_user_id is None else sanitize_log_value(raw_user_id, 128)
        metadata = sanitize_log_structure(inputs.get("metadata", {}))

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

        # Check for alerting (use numeric ordering, not string comparison)
        _severity_rank = {
            SeverityLevel.INFO: 0,
            SeverityLevel.LOW: 1,
            SeverityLevel.MEDIUM: 2,
            SeverityLevel.HIGH: 3,
            SeverityLevel.CRITICAL: 4,
        }
        should_alert = _severity_rank.get(severity, 0) >= _severity_rank.get(
            self.alert_threshold, 0
        )

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

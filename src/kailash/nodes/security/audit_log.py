"""
AuditLogNode - Centralized audit logging for middleware operations
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict

from kailash.nodes.base import Node, NodeParameter, register_node
from kailash.utils.secure_logging import (
    redact_mapping,
    sanitize_log_structure,
    sanitize_log_value,
)


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

    def run(self, **kwargs) -> Dict[str, Any]:
        """Execute the node's logic (Node ABC contract)."""
        return self.execute(**kwargs)

    def execute(self, **inputs) -> Dict[str, Any]:
        """Execute audit logging."""
        # SINK-LEVEL SANITIZING (issue #2088). See the companion comment in
        # ``SecurityEventNode.execute`` for why this lives here rather than at
        # each of the ~30 call sites.
        #
        # This node's exposure is LATENT rather than live: ``output_format``
        # defaults to ``"json"``, and ``json.dumps`` escapes a newline to
        # ``\n``. It goes LIVE the moment a deployment constructs the node
        # with any other format -- the ``else`` branch below interpolates
        # every field into an f-string with no escaping at all, including
        # ``event_data``, whose NESTED strings are rendered by ``str(dict)``.
        # Covering the non-json path is what promotes this from latent to
        # fixed, so ``event_data`` is sanitized recursively rather than only
        # at its top level.
        #
        # REDACTION IS COMPOSED WITH THAT, NOT SUBSTITUTED FOR IT (issue #2167).
        # The two helpers answer different questions and BOTH are needed here:
        # `redact_mapping` decides WHETHER a value may be recorded (by key
        # name), `sanitize_log_structure` decides HOW the survivors render.
        # Swapping one for the other trades a credential leak for a
        # log-injection hole, or the reverse -- `sanitize_log_value`'s own
        # docstring says it plainly: "NOT a redaction step. A short
        # attacker-chosen value survives on purpose."
        #
        # Without the redaction half, a credential up to the 256-char sanitizer
        # bound reached this log BYTE-INTACT. `event_data` is a free-form
        # caller bag and real producers put credentials in it: kaizen's
        # `nodes/auth/sso.py` forwards the raw IdP attribute bag, while the
        # core-SDK sibling for the SAME bag already redacted it -- the SDK
        # disagreeing with itself about whether that bag is credential-bearing.
        # CodeQL flagged the three sinks below as 11503/11504/11505.
        #
        # This is the fix `nodes/auth/_log_hygiene.py` named as belonging
        # "one layer down ... so that EVERY caller in the SDK is covered
        # rather than only this package's". Redact FIRST: the sanitizer then
        # never handles the credential at all.
        event_data = sanitize_log_structure(
            redact_mapping(inputs.get("event_data", {}))
        )
        event_type = sanitize_log_value(inputs.get("event_type", "info"), 128)
        raw_user_id = inputs.get("user_id")
        # Preserve the None/absent distinction rather than recording the
        # string "None" as a user id.
        user_id = None if raw_user_id is None else sanitize_log_value(raw_user_id, 128)
        message = sanitize_log_value(inputs.get("message", ""), 512)

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

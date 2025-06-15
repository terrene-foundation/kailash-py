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
        return {
            "action": NodeParameter(
                name="action",
                type=str,
                required=True,
                description="The action being audited",
            ),
            "user_id": NodeParameter(
                name="user_id",
                type=str,
                required=False,
                description="User performing the action",
            ),
            "details": NodeParameter(
                name="details",
                type=dict,
                required=False,
                description="Additional audit details",
            ),
        }

    def process(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Process audit log entry."""

        audit_entry = {
            "action": inputs.get("action"),
            "user_id": inputs.get("user_id"),
            "details": inputs.get("details", {}),
        }

        if self.include_timestamp:
            audit_entry["timestamp"] = datetime.now(timezone.utc).isoformat()

        # Log the audit entry
        if self.output_format == "json":
            self.logger.info(json.dumps(audit_entry))
        else:
            self.logger.info(f"AUDIT: {audit_entry}")

        return {"audit_logged": True, "entry": audit_entry}

    async def aprocess(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Async version that just calls the sync version."""
        return self.process(inputs)

    def run(self, **kwargs) -> Dict[str, Any]:
        """Alias for process method."""
        return self.process(kwargs)

    def execute(self, **kwargs) -> Dict[str, Any]:
        """Alias for process method."""
        return self.process(kwargs)

    async def async_run(self, **kwargs) -> Dict[str, Any]:
        """Async execution method for enterprise integration."""
        return self.run(**kwargs)

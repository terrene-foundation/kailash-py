"""
Audit hook for PostgreSQL-backed audit trail integration.

Automatically logs all hook events to audit trail for compliance and security monitoring.
"""

import logging
from typing import ClassVar

from ..protocol import BaseHook
from ..types import HookContext, HookEvent, HookResult

logger = logging.getLogger(__name__)


class AuditHook(BaseHook):
    """
    Integrates AuditTrailProvider with hook system for automatic audit logging.

    Features:
    - Automatic audit logging for all hook events
    - PostgreSQL-backed persistence
    - trace_id storage in JSONB metadata
    - Event filtering (optional: log only specific events)
    - Compliance-ready audit trail

    Example:
        >>> from kaizen.security.audit import AuditTrailProvider
        >>> audit_provider = AuditTrailProvider(conn_string="postgresql://...")
        >>> audit_hook = AuditHook(audit_provider)
        >>> hook_manager.register(HookEvent.PRE_TOOL_USE, audit_hook.handle)
    """

    # Define which events this hook handles
    events: ClassVar[list[HookEvent]] = list(HookEvent)  # All events

    def __init__(
        self,
        audit_provider: "AuditTrailProvider",  # type: ignore
        event_filter: list[HookEvent] | None = None,
    ):
        """
        Initialize audit hook.

        Args:
            audit_provider: AuditTrailProvider instance for PostgreSQL logging
            event_filter: Optional list of events to log (None = log all events)
        """
        super().__init__(name="audit_hook")
        self.audit_provider = audit_provider
        self.event_filter = event_filter

    async def handle(self, context: HookContext) -> HookResult:
        """
        Log hook event to audit trail.

        Args:
            context: Hook execution context

        Returns:
            HookResult with audit_event_id
        """
        try:
            # Skip if event not in filter
            if self.event_filter and context.event_type not in self.event_filter:
                return HookResult(
                    success=True, data={"skipped": True, "reason": "event_filter"}
                )

            # Prepare audit metadata
            audit_metadata = {
                "trace_id": context.trace_id,
                "timestamp": context.timestamp,
                "event_type": context.event_type.value,
                "data": context.data,
                "metadata": context.metadata,
            }

            # Determine result from context data
            result = context.data.get("result", "success")
            if context.data.get("error"):
                result = "error"
            elif context.data.get("success") is False:
                result = "failure"

            # Log to audit trail
            event_id = self.audit_provider.log_event(
                user=context.agent_id,
                action=context.event_type.value,
                result=result,
                metadata=audit_metadata,
            )

            return HookResult(success=True, data={"audit_event_id": event_id})

        except Exception as e:
            logger.error(f"AuditHook failed for {context.event_type.value}: {e}")
            return HookResult(success=False, error=str(e))

    async def on_error(self, error: Exception, context: HookContext) -> None:
        """Log errors to stderr"""
        logger.error(f"AuditHook failed for {context.event_type.value}: {error}")

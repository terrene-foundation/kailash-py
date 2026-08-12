"""
Audit trail hook bridging the observability audit subsystem to the hook system.

``AuditTrailManager`` (System 6) provides append-only JSONL audit storage for
compliance (SOC2, GDPR, HIPAA) but is not itself a hook -- nothing connected it
to agent lifecycle events, so ``AgentConfig.enable_audit`` had no way to record
anything. This hook is that connection.

Distinct from :class:`~kaizen.core.autonomy.hooks.builtin.audit_hook.AuditHook`,
which wraps the *security* ``AuditTrailProvider`` (in-memory / PostgreSQL). This
one wraps the *observability* ``AuditTrailManager`` and therefore honours
``AgentConfig.audit_log_path``.

Example:
    >>> from kaizen.core.autonomy.observability.audit import (
    ...     AuditTrailManager,
    ...     FileAuditStorage,
    ... )
    >>> manager = AuditTrailManager(storage=FileAuditStorage(".kaizen/audit.jsonl"))
    >>> hook = AuditTrailHook(audit_manager=manager)
    >>> hook_manager.register_hook(hook)
"""

import logging
from typing import ClassVar, List, Optional

from kaizen.core.autonomy.observability.audit import AuditTrailManager

from .._payload import summarize_payload
from ..protocol import BaseHook
from ..types import HookContext, HookEvent, HookResult

logger = logging.getLogger(__name__)


class AuditTrailHook(BaseHook):
    """
    Records agent lifecycle events to an append-only audit trail.

    Every handled event becomes one ``AuditEntry`` appended to the configured
    storage backend. BOTH payload-bearing fields are reduced to STRUCTURE --
    ``context.data`` to its key names, and ``context.metadata`` through
    ``summarize_payload`` to ``{count, keys}``. Neither contributes values, so
    enabling compliance audit does not itself become a disclosure channel --
    the same split ``LoggingHook`` draws between ``include_data`` and
    ``log_full_payloads``.

    What DOES reach the file verbatim: ``agent_id``, the event name, the
    ``trace_id``, the timestamp, and the success/failure verdict. Those are the
    audit record.

    Attributes:
        events: All hook events (audit trails capture the full lifecycle).
        audit_manager: AuditTrailManager performing the append.
        events_to_audit: Optional filter (None/empty = audit every event).
    """

    events: ClassVar[list[HookEvent]] = list(HookEvent)

    def __init__(
        self,
        audit_manager: AuditTrailManager,
        events_to_audit: Optional[List[HookEvent]] = None,
    ):
        """
        Initialize audit trail hook.

        Args:
            audit_manager: AuditTrailManager for append-only recording.
            events_to_audit: Optional list of events to audit (None = all).
        """
        super().__init__(name="audit_trail_hook")
        self.audit_manager = audit_manager
        self.events_to_audit = events_to_audit or []

    async def handle(self, context: HookContext) -> HookResult:
        """
        Append one audit entry for this event.

        Args:
            context: Hook execution context.

        Returns:
            HookResult recording whether the entry was appended or filtered.
        """
        if self.events_to_audit and context.event_type not in self.events_to_audit:
            return HookResult(
                success=True, data={"audited": False, "reason": "event_filter"}
            )

        # Derive the compliance result from the event payload. An explicit
        # error, or success=False, is a failure; anything else is a success.
        if context.data.get("error"):
            result = "failure"
        elif context.data.get("success") is False:
            result = "failure"
        else:
            result = "success"

        # Record the payload's SHAPE only. Values may carry prompts, retrieved
        # documents and PII; an audit file is retained and shipped widely, so
        # it is the worst place to put them.
        details = {
            "event": context.event_type.value,
            "data_keys": sorted(context.data.keys()),
            "trace_id": context.trace_id,
        }

        # `metadata` gets the SAME reduction as `data`, and for the same
        # reason. It was previously forwarded WHOLE, so every value in it was
        # serialised verbatim into the audit file by `json.dumps(asdict(entry))`
        # -- and it is a documented public kwarg on both `HookManager.trigger`
        # and `BaseAgent.trigger_hook`, whose intended users are exactly the
        # downstream callers most likely to put tenant and principal
        # identifiers in it. `LoggingHook` already treats metadata as
        # payload-class; the asymmetry was the bug.
        #
        # Absent metadata stays `None` rather than becoming an empty summary,
        # so the on-disk shape of an entry from an in-tree caller (none of
        # which populate the kwarg) is unchanged.
        await self.audit_manager.record(
            agent_id=context.agent_id,
            action=context.event_type.value,
            details=details,
            result=result,
            metadata=summarize_payload(context.metadata) if context.metadata else None,
        )

        return HookResult(success=True, data={"audited": True, "result": result})

    async def on_error(self, error: Exception, context: HookContext) -> None:
        """Surface audit-append failures rather than dropping them silently."""
        logger.warning(
            "audit_trail_hook.append_failed event=%s agent_id=%s error=%s error_type=%s",
            context.event_type.value,
            context.agent_id,
            error,
            type(error).__name__,
        )


__all__ = ["AuditTrailHook"]

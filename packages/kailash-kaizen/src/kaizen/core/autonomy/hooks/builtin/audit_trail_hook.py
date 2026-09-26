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
import math
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

    This hook does NOT share the best-effort budget of the other builtins.
    ``HookManager.trigger`` defaults every hook to 0.5s ("SECURITY FIX #10",
    which stops a hook hanging the agent loop); at that budget an append on a
    contended volume is abandoned, and the trail develops holes exactly under
    the load an auditor cares about. A dropped metrics sample is a gap in a
    graph; a dropped audit record is a compliance failure, so this hook
    declares ``timeout_seconds`` and the manager honours it.

    The budget is a DIFFERENT bound, never the absence of one -- an unbounded
    audit append would hand back precisely the agent-loop hang the guard
    exists to prevent, and file IO is the most likely thing to block
    indefinitely (a hard-mounted NFS write is not interruptible). A drop is
    therefore still possible, and is reported loudly by :meth:`on_error`
    rather than swallowed.

    Attributes:
        events: All hook events (audit trails capture the full lifecycle).
        timeout_seconds: Execution budget honoured by ``HookManager``.
        audit_manager: AuditTrailManager performing the append.
        events_to_audit: Optional filter (None/empty = audit every event).
    """

    events: ClassVar[list[HookEvent]] = list(HookEvent)

    #: Budget for one append, in seconds. Chosen to sit clear of the 5.0s
    #: outer bound that ``kaizen.core.agent_loop.run_async_hook`` places on the
    #: WHOLE trigger when hooks are fired from a sync context: that envelope is
    #: shared with every other hook registered for the same event, so a larger
    #: audit budget would eat the headroom they need. 2.0s absorbs the
    #: transient IO stalls that defeat 0.5s while leaving that envelope intact.
    timeout_seconds: ClassVar[float] = 2.0

    def __init__(
        self,
        audit_manager: AuditTrailManager,
        events_to_audit: Optional[List[HookEvent]] = None,
        timeout_seconds: Optional[float] = None,
    ):
        """
        Initialize audit trail hook.

        Args:
            audit_manager: AuditTrailManager for append-only recording.
            events_to_audit: Optional list of events to audit (None = all).
            timeout_seconds: Override for the per-append budget. Must be finite
                and positive -- a deployment on slow shared storage may need
                more, but no value removes the bound.

        Raises:
            ValueError: If ``timeout_seconds`` is not finite and positive.
                Raised rather than quietly falling back, so a bad budget is
                caught where it is configured instead of surfacing later as
                dropped records.
        """
        super().__init__(name="audit_trail_hook")
        if timeout_seconds is not None:
            if (
                isinstance(timeout_seconds, bool)
                or not isinstance(timeout_seconds, (int, float))
                or not math.isfinite(timeout_seconds)
                or timeout_seconds <= 0
            ):
                raise ValueError(
                    "timeout_seconds must be a finite positive number, got "
                    f"{timeout_seconds!r}"
                )
            self.timeout_seconds = float(timeout_seconds)
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
        # `data_keys` goes through the SAME helper as metadata below rather
        # than a hand-rolled `sorted(context.data.keys())`: the helper coerces
        # keys to str before sorting, so a payload mixing key types
        # (`{1: ..., "a": ...}`) summarises instead of raising TypeError and
        # failing the append. Leaving one of the two payload fields on a
        # private implementation is the asymmetry that produced this bug.
        details = {
            "event": context.event_type.value,
            "data_keys": summarize_payload(context.data)["keys"],
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
        """
        Report a LOST audit record loudly and in a form alerting can match.

        Reached for both ways a record fails to land: the append raised, or
        ``HookManager`` cut it off at :attr:`timeout_seconds` and abandoned it.
        Either way the entry is not in storage, so both are logged at ERROR
        under one greppable token, ``audit_record_dropped``, with the event
        name and the reason as structured fields.

        This is the fail-loud half of the contract. An audit trail that drops
        silently is worse than one that fails noisily: a noisy failure is an
        incident someone works, while a silent hole is indistinguishable from
        an event that never happened -- and telling those two apart is the
        entire purpose of the artifact.

        Args:
            error: The failure. A ``TimeoutError`` means the append was
                abandoned at the budget; anything else means it was attempted
                and raised.
            context: Hook context for the event whose record was lost.
        """
        reason = "timeout" if isinstance(error, TimeoutError) else type(error).__name__
        logger.error(
            "audit_trail_hook.audit_record_dropped event=%s agent_id=%s "
            "reason=%s budget_s=%.3f trace_id=%s error_type=%s",
            context.event_type.value,
            context.agent_id,
            reason,
            self.timeout_seconds,
            context.trace_id,
            type(error).__name__,
            extra={
                "audit_event": context.event_type.value,
                "audit_agent_id": context.agent_id,
                "audit_drop_reason": reason,
                "audit_budget_s": self.timeout_seconds,
                "audit_trace_id": context.trace_id,
            },
        )


__all__ = ["AuditTrailHook"]

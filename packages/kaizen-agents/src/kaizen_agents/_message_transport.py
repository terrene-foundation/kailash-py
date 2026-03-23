# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""MessageTransport — bridge between kaizen-agents protocols and SDK MessageRouter.

Wraps the SDK MessageRouter to provide a clean interface for protocols to
send/receive typed messages.  Converts between local L3Message/payload types
(kaizen_agents.types) and SDK MessageEnvelope/payload types
(kaizen.l3.messaging.types) at the boundary.

Conversion strategy follows _sdk_compat.py patterns:
    - Import SDK types with aliases (Sdk prefix)
    - Convert local payloads -> SDK payloads for outbound routing
    - Convert SDK envelopes -> local L3Message for inbound delivery
    - Enums: map by name (both sides share the same member names)
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from kaizen.l3.messaging.dead_letters import DeadLetterStore
from kaizen.l3.messaging.router import MessageRouter
from kaizen.l3.messaging.types import (
    ClarificationPayload as SdkClarificationPayload,
    CompletionPayload as SdkCompletionPayload,
    DelegationPayload as SdkDelegationPayload,
    EscalationPayload as SdkEscalationPayload,
    EscalationSeverity as SdkEscalationSeverity,
    MessageEnvelope as SdkMessageEnvelope,
    Priority as SdkPriority,
    ResourceSnapshot as SdkResourceSnapshot,
    StatusPayload as SdkStatusPayload,
    SystemPayload as SdkSystemPayload,
    SystemSubtype as SdkSystemSubtype,
)

from kaizen_agents.types import (
    ClarificationPayload as LocalClarificationPayload,
    CompletionPayload as LocalCompletionPayload,
    DelegationPayload as LocalDelegationPayload,
    EscalationPayload as LocalEscalationPayload,
    EscalationSeverity as LocalEscalationSeverity,
    L3Message,
    L3MessageType,
    Priority as LocalPriority,
    ResourceSnapshot as LocalResourceSnapshot,
    StatusPayload as LocalStatusPayload,
    SystemPayload as LocalSystemPayload,
    SystemSubtype as LocalSystemSubtype,
)

__all__ = ["MessageTransport"]

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enum mapping tables (by name, same pattern as _sdk_compat.py)
# ---------------------------------------------------------------------------

_PRIORITY_TO_SDK: dict[LocalPriority, SdkPriority] = {
    local: SdkPriority[local.name] for local in LocalPriority
}
_PRIORITY_FROM_SDK: dict[SdkPriority, LocalPriority] = {
    sdk: LocalPriority[sdk.name] for sdk in SdkPriority
}

_ESCALATION_SEVERITY_TO_SDK: dict[LocalEscalationSeverity, SdkEscalationSeverity] = {
    local: SdkEscalationSeverity[local.name] for local in LocalEscalationSeverity
}
_ESCALATION_SEVERITY_FROM_SDK: dict[SdkEscalationSeverity, LocalEscalationSeverity] = {
    sdk: LocalEscalationSeverity[sdk.name] for sdk in SdkEscalationSeverity
}

_SYSTEM_SUBTYPE_TO_SDK: dict[LocalSystemSubtype, SdkSystemSubtype] = {
    local: SdkSystemSubtype[local.name] for local in LocalSystemSubtype
}
_SYSTEM_SUBTYPE_FROM_SDK: dict[SdkSystemSubtype, LocalSystemSubtype] = {
    sdk: LocalSystemSubtype[sdk.name] for sdk in SdkSystemSubtype
}


# ---------------------------------------------------------------------------
# Payload converters: local -> SDK
# ---------------------------------------------------------------------------


def _delegation_to_sdk(local: LocalDelegationPayload) -> SdkDelegationPayload:
    """Convert a local DelegationPayload to SDK DelegationPayload."""
    return SdkDelegationPayload(
        task_description=local.task_description,
        context_snapshot=dict(local.context_snapshot),
        envelope=None,  # Envelope config is not carried in message-level payloads
        deadline=local.deadline,
        priority=_PRIORITY_TO_SDK[local.priority],
    )


def _completion_to_sdk(local: LocalCompletionPayload) -> SdkCompletionPayload:
    """Convert a local CompletionPayload to SDK CompletionPayload."""
    return SdkCompletionPayload(
        result=local.result,
        success=local.success,
        context_updates=dict(local.context_updates),
        resource_consumed=SdkResourceSnapshot(
            financial_spent=local.resource_consumed.financial_spent,
            actions_executed=local.resource_consumed.actions_executed,
            elapsed_seconds=local.resource_consumed.elapsed_seconds,
            messages_sent=local.resource_consumed.messages_sent,
        ),
        error_detail=local.error_detail,
    )


def _clarification_to_sdk(local: LocalClarificationPayload) -> SdkClarificationPayload:
    """Convert a local ClarificationPayload to SDK ClarificationPayload."""
    return SdkClarificationPayload(
        question=local.question,
        blocking=local.blocking,
        is_response=local.is_response,
        options=list(local.options) if local.options is not None else None,
    )


def _escalation_to_sdk(local: LocalEscalationPayload) -> SdkEscalationPayload:
    """Convert a local EscalationPayload to SDK EscalationPayload."""
    return SdkEscalationPayload(
        severity=_ESCALATION_SEVERITY_TO_SDK[local.severity],
        problem_description=local.problem_description,
        attempted_mitigations=list(local.attempted_mitigations),
        suggested_action=local.suggested_action,
        violating_dimension=local.violating_dimension,
    )


# ---------------------------------------------------------------------------
# Payload converters: SDK -> local
# ---------------------------------------------------------------------------


def _resource_snapshot_from_sdk(sdk: SdkResourceSnapshot) -> LocalResourceSnapshot:
    """Convert SDK ResourceSnapshot to local ResourceSnapshot."""
    return LocalResourceSnapshot(
        financial_spent=sdk.financial_spent,
        actions_executed=sdk.actions_executed,
        elapsed_seconds=sdk.elapsed_seconds,
        messages_sent=sdk.messages_sent,
    )


def _delegation_from_sdk(sdk: SdkDelegationPayload) -> LocalDelegationPayload:
    """Convert SDK DelegationPayload to local DelegationPayload."""
    return LocalDelegationPayload(
        task_description=sdk.task_description,
        context_snapshot=dict(sdk.context_snapshot),
        deadline=sdk.deadline,
        priority=_PRIORITY_FROM_SDK[sdk.priority],
    )


def _completion_from_sdk(sdk: SdkCompletionPayload) -> LocalCompletionPayload:
    """Convert SDK CompletionPayload to local CompletionPayload."""
    return LocalCompletionPayload(
        result=sdk.result,
        success=sdk.success,
        context_updates=dict(sdk.context_updates),
        resource_consumed=_resource_snapshot_from_sdk(sdk.resource_consumed),
        error_detail=sdk.error_detail,
    )


def _clarification_from_sdk(sdk: SdkClarificationPayload) -> LocalClarificationPayload:
    """Convert SDK ClarificationPayload to local ClarificationPayload."""
    return LocalClarificationPayload(
        question=sdk.question,
        blocking=sdk.blocking,
        is_response=sdk.is_response,
        options=list(sdk.options) if sdk.options is not None else None,
    )


def _escalation_from_sdk(sdk: SdkEscalationPayload) -> LocalEscalationPayload:
    """Convert SDK EscalationPayload to local EscalationPayload."""
    return LocalEscalationPayload(
        severity=_ESCALATION_SEVERITY_FROM_SDK[sdk.severity],
        problem_description=sdk.problem_description,
        attempted_mitigations=list(sdk.attempted_mitigations),
        suggested_action=sdk.suggested_action,
        violating_dimension=sdk.violating_dimension,
    )


def _status_from_sdk(sdk: SdkStatusPayload) -> LocalStatusPayload:
    """Convert SDK StatusPayload to local StatusPayload."""
    return LocalStatusPayload(
        phase=sdk.phase,
        resource_usage=_resource_snapshot_from_sdk(sdk.resource_usage),
        progress_pct=sdk.progress_pct,
    )


def _system_from_sdk(sdk: SdkSystemPayload) -> LocalSystemPayload:
    """Convert SDK SystemPayload to local SystemPayload."""
    return LocalSystemPayload(
        subtype=_SYSTEM_SUBTYPE_FROM_SDK[sdk.subtype],
        reason=sdk.reason if sdk.reason else None,
        dimension=sdk.dimension if sdk.dimension else None,
        detail=sdk.detail if sdk.detail else None,
        instance_id=sdk.instance_id if sdk.instance_id else None,
    )


# ---------------------------------------------------------------------------
# SDK Envelope -> local L3Message
# ---------------------------------------------------------------------------


def _envelope_to_l3message(envelope: SdkMessageEnvelope) -> L3Message:
    """Convert an SDK MessageEnvelope to a local L3Message.

    Dispatches on the payload type to populate the correct L3Message field
    and set the appropriate message_type discriminator.

    Raises:
        ValueError: If the envelope contains an unrecognised payload type.
    """
    payload = envelope.payload

    # Convert sent_at to timezone-aware datetime if needed
    sent_at = envelope.sent_at
    if sent_at.tzinfo is None:
        sent_at = sent_at.replace(tzinfo=UTC)

    # Convert ttl_seconds (float | None) to timedelta | None
    ttl: timedelta | None = None
    if envelope.ttl_seconds is not None:
        ttl = timedelta(seconds=envelope.ttl_seconds)

    base_kwargs: dict[str, Any] = {
        "message_id": envelope.message_id,
        "from_instance": envelope.from_instance,
        "to_instance": envelope.to_instance,
        "correlation_id": envelope.correlation_id,
        "sent_at": sent_at,
        "ttl": ttl,
    }

    if isinstance(payload, SdkDelegationPayload):
        return L3Message(
            **base_kwargs,
            message_type=L3MessageType.DELEGATION,
            delegation=_delegation_from_sdk(payload),
        )
    elif isinstance(payload, SdkCompletionPayload):
        return L3Message(
            **base_kwargs,
            message_type=L3MessageType.COMPLETION,
            completion=_completion_from_sdk(payload),
        )
    elif isinstance(payload, SdkClarificationPayload):
        return L3Message(
            **base_kwargs,
            message_type=L3MessageType.CLARIFICATION,
            clarification=_clarification_from_sdk(payload),
        )
    elif isinstance(payload, SdkEscalationPayload):
        return L3Message(
            **base_kwargs,
            message_type=L3MessageType.ESCALATION,
            escalation=_escalation_from_sdk(payload),
        )
    elif isinstance(payload, SdkStatusPayload):
        return L3Message(
            **base_kwargs,
            message_type=L3MessageType.STATUS,
            status=_status_from_sdk(payload),
        )
    elif isinstance(payload, SdkSystemPayload):
        return L3Message(
            **base_kwargs,
            message_type=L3MessageType.SYSTEM,
            system=_system_from_sdk(payload),
        )
    else:
        raise ValueError(
            f"Unrecognised SDK payload type: {type(payload).__name__}. "
            f"Cannot convert to local L3Message."
        )


# ---------------------------------------------------------------------------
# MessageTransport
# ---------------------------------------------------------------------------


class MessageTransport:
    """Wraps SDK MessageRouter for protocol-level message exchange.

    Provides typed send methods that convert local payload types to SDK
    MessageEnvelopes, and a receive method that converts SDK envelopes
    back to local L3Messages.

    Args:
        router: The SDK MessageRouter instance to use for routing.
    """

    __slots__ = ("_router",)

    def __init__(self, router: MessageRouter) -> None:
        self._router = router

    # -------------------------------------------------------------------
    # Channel management
    # -------------------------------------------------------------------

    def setup_channel(self, parent_id: str, child_id: str, capacity: int = 100) -> None:
        """Create bidirectional channels between parent and child.

        Args:
            parent_id: Instance ID of the parent agent.
            child_id: Instance ID of the child agent.
            capacity: Maximum number of undelivered messages per direction.
        """
        self._router.create_channel(parent_id, child_id, capacity)
        self._router.create_channel(child_id, parent_id, capacity)
        logger.debug(
            "Bidirectional channels created: %s <-> %s (capacity=%d)",
            parent_id,
            child_id,
            capacity,
        )

    def teardown_channel(self, instance_id: str) -> None:
        """Close all channels for an instance.

        Delegates to SDK router which moves pending messages to dead letters.

        Args:
            instance_id: The instance whose channels should be closed.
        """
        self._router.close_channels_for(instance_id)
        logger.debug("All channels torn down for instance_id=%s", instance_id)

    # -------------------------------------------------------------------
    # Send methods (local payload -> SDK envelope -> route)
    # -------------------------------------------------------------------

    async def send_delegation(
        self,
        from_id: str,
        to_id: str,
        payload: LocalDelegationPayload,
        correlation_id: str | None = None,
        ttl_seconds: float = 300.0,
    ) -> str:
        """Send a delegation message. Returns message_id.

        Args:
            from_id: Sender instance ID.
            to_id: Recipient instance ID.
            payload: Local DelegationPayload.
            correlation_id: Optional correlation ID for request tracking.
            ttl_seconds: Time-to-live in seconds (default 300s).

        Returns:
            The message_id of the sent envelope.

        Raises:
            RoutingError: If the SDK router rejects the message.
        """
        message_id = str(uuid.uuid4())
        sdk_payload = _delegation_to_sdk(payload)
        envelope = SdkMessageEnvelope(
            message_id=message_id,
            from_instance=from_id,
            to_instance=to_id,
            payload=sdk_payload,
            correlation_id=correlation_id,
            sent_at=datetime.now(UTC),
            ttl_seconds=ttl_seconds,
        )
        await self._router.route(envelope)
        logger.debug(
            "Delegation sent: %s -> %s (message_id=%s)",
            from_id,
            to_id,
            message_id,
        )
        return message_id

    async def send_completion(
        self,
        from_id: str,
        to_id: str,
        payload: LocalCompletionPayload,
        correlation_id: str | None = None,
    ) -> str:
        """Send a completion message. Returns message_id.

        Args:
            from_id: Sender instance ID.
            to_id: Recipient instance ID.
            payload: Local CompletionPayload.
            correlation_id: Correlation ID (required by SDK for Completion).

        Returns:
            The message_id of the sent envelope.

        Raises:
            RoutingError: If the SDK router rejects the message.
        """
        message_id = str(uuid.uuid4())
        sdk_payload = _completion_to_sdk(payload)
        envelope = SdkMessageEnvelope(
            message_id=message_id,
            from_instance=from_id,
            to_instance=to_id,
            payload=sdk_payload,
            correlation_id=correlation_id,
            sent_at=datetime.now(UTC),
        )
        await self._router.route(envelope)
        logger.debug(
            "Completion sent: %s -> %s (message_id=%s)",
            from_id,
            to_id,
            message_id,
        )
        return message_id

    async def send_clarification(
        self,
        from_id: str,
        to_id: str,
        payload: LocalClarificationPayload,
        correlation_id: str | None = None,
    ) -> str:
        """Send a clarification message. Returns message_id.

        Args:
            from_id: Sender instance ID.
            to_id: Recipient instance ID.
            payload: Local ClarificationPayload.
            correlation_id: Correlation ID (required for responses).

        Returns:
            The message_id of the sent envelope.

        Raises:
            RoutingError: If the SDK router rejects the message.
        """
        message_id = str(uuid.uuid4())
        sdk_payload = _clarification_to_sdk(payload)
        envelope = SdkMessageEnvelope(
            message_id=message_id,
            from_instance=from_id,
            to_instance=to_id,
            payload=sdk_payload,
            correlation_id=correlation_id,
            sent_at=datetime.now(UTC),
        )
        await self._router.route(envelope)
        logger.debug(
            "Clarification sent: %s -> %s (message_id=%s)",
            from_id,
            to_id,
            message_id,
        )
        return message_id

    async def send_escalation(
        self,
        from_id: str,
        to_id: str,
        payload: LocalEscalationPayload,
        correlation_id: str | None = None,
    ) -> str:
        """Send an escalation message. Returns message_id.

        Args:
            from_id: Sender instance ID.
            to_id: Recipient instance ID.
            payload: Local EscalationPayload.
            correlation_id: Optional correlation ID.

        Returns:
            The message_id of the sent envelope.

        Raises:
            RoutingError: If the SDK router rejects the message.
        """
        message_id = str(uuid.uuid4())
        sdk_payload = _escalation_to_sdk(payload)
        envelope = SdkMessageEnvelope(
            message_id=message_id,
            from_instance=from_id,
            to_instance=to_id,
            payload=sdk_payload,
            correlation_id=correlation_id,
            sent_at=datetime.now(UTC),
        )
        await self._router.route(envelope)
        logger.debug(
            "Escalation sent: %s -> %s (message_id=%s)",
            from_id,
            to_id,
            message_id,
        )
        return message_id

    # -------------------------------------------------------------------
    # Receive method (SDK envelopes -> local L3Messages)
    # -------------------------------------------------------------------

    async def receive_pending(self, instance_id: str) -> list[L3Message]:
        """Get pending messages for an instance.

        Retrieves all pending SDK MessageEnvelopes from the router and
        converts them to local L3Messages.

        Args:
            instance_id: The instance ID to check pending messages for.

        Returns:
            List of local L3Messages. Empty list if no messages pending.
        """
        envelopes = await self._router.pending_for(instance_id)
        messages: list[L3Message] = []
        for envelope in envelopes:
            try:
                msg = _envelope_to_l3message(envelope)
                messages.append(msg)
            except ValueError:
                logger.error(
                    "Failed to convert SDK envelope to L3Message: "
                    "message_id=%s, payload_type=%s",
                    envelope.message_id,
                    type(envelope.payload).__name__ if envelope.payload else "None",
                )
                raise
        return messages

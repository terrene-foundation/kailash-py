# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""MessageRouter — envelope-aware routing layer for L3 inter-agent messaging.

Validates communication constraints before delivering messages to channels.
Per Brief 03 Section 2.5.

Routing validation sequence:
1. TTL check (sent_at + ttl < now -> Expired -> dead letter)
2. Self-message check (from == to -> reject)
3. Correlation ID validation (Completion MUST have correlation_id, etc.)
4. Directionality check (optional, requires lineage_fn)
5. Channel existence check
6. Channel state check (closed?)
7. Deliver to channel (backpressure if full)

Directionality checks require a lineage_fn callback that maps
instance_id -> parent_id (or None for root). When lineage_fn is not
provided, directionality validation is skipped. This keeps M3
independently testable; M4 (AgentFactory integration) wires in the
registry callback.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Callable

from kaizen.l3.messaging.channel import MessageChannel
from kaizen.l3.messaging.dead_letters import DeadLetterReason, DeadLetterStore
from kaizen.l3.messaging.errors import ChannelError, RoutingError
from kaizen.l3.messaging.types import (
    ClarificationPayload,
    CompletionPayload,
    DelegationPayload,
    EscalationPayload,
    MessageEnvelope,
    MessageType,
    StatusPayload,
    SystemPayload,
)

__all__ = ["MessageRouter"]

logger = logging.getLogger(__name__)

# Type for the lineage callback: instance_id -> parent_id (None for root)
LineageFn = Callable[[str], str | None]


class MessageRouter:
    """Envelope-aware routing layer for L3 messages.

    Validates communication constraints (TTL, self-message, directionality,
    correlation_id) before delivering messages to the appropriate channel.

    Args:
        dead_letters: Optional DeadLetterStore. A default is created if not provided.
        lineage_fn: Optional callback that returns the parent_id for a given
            instance_id, or None if the instance is the root. When provided,
            enables directionality enforcement. When absent, directionality
            checks are skipped.
    """

    __slots__ = ("_channels", "_dead_letters", "_lineage_fn")

    def __init__(
        self,
        dead_letters: DeadLetterStore | None = None,
        lineage_fn: LineageFn | None = None,
    ) -> None:
        self._channels: dict[tuple[str, str], MessageChannel] = {}
        self._dead_letters = dead_letters or DeadLetterStore()
        self._lineage_fn = lineage_fn

    @property
    def dead_letters(self) -> DeadLetterStore:
        """The dead letter store for undeliverable messages."""
        return self._dead_letters

    def create_channel(
        self,
        from_id: str,
        to_id: str,
        capacity: int,
    ) -> MessageChannel:
        """Create a unidirectional channel between two instances.

        Args:
            from_id: Instance ID of the sender endpoint.
            to_id: Instance ID of the receiver endpoint.
            capacity: Maximum number of undelivered messages.

        Returns:
            The created MessageChannel.

        Raises:
            RoutingError: If a channel already exists for this (from, to) pair.
        """
        key = (from_id, to_id)
        if key in self._channels:
            raise RoutingError(
                f"Channel from '{from_id}' to '{to_id}' already exists",
                variant="ChannelExists",
                details={"from_instance": from_id, "to_instance": to_id},
            )
        channel = MessageChannel(
            from_instance=from_id,
            to_instance=to_id,
            capacity=capacity,
        )
        self._channels[key] = channel
        logger.debug(
            "Channel created: %s -> %s (capacity=%d, id=%s)",
            from_id,
            to_id,
            capacity,
            channel.channel_id,
        )
        return channel

    async def route(self, envelope: MessageEnvelope) -> None:
        """Validate constraints then deliver to the appropriate channel.

        Routing validation sequence:
        1. TTL check
        2. Self-message check
        3. Correlation ID validation
        4. Directionality check (if lineage_fn provided)
        5. Channel existence check
        6. Channel state check
        7. Deliver

        Args:
            envelope: The message envelope to route.

        Raises:
            RoutingError: If any validation step fails.
        """
        from_inst = envelope.from_instance
        to_inst = envelope.to_instance

        # Step 1: TTL check
        self._check_ttl(envelope)

        # Step 2: Self-message check
        if from_inst == to_inst:
            raise RoutingError.self_message(from_inst)

        # Step 3: Correlation ID validation
        self._check_correlation_id(envelope)

        # Step 4: Directionality check (only if lineage_fn is provided)
        if self._lineage_fn is not None:
            self._check_directionality(envelope)

        # Step 5: Channel existence check
        key = (from_inst, to_inst)
        channel = self._channels.get(key)
        if channel is None:
            raise RoutingError.no_channel(from_inst, to_inst)

        # Step 6: Channel state check
        if channel.is_closed():
            raise RoutingError.channel_closed(channel.channel_id)

        # Step 7: Deliver to channel
        try:
            await channel.send(envelope)
        except ChannelError as exc:
            if exc.variant == "Full":
                raise RoutingError.backpressure(
                    channel.channel_id, channel.capacity
                ) from exc
            raise RoutingError.channel_closed(channel.channel_id) from exc

        logger.debug(
            "Message %s routed: %s -> %s",
            envelope.message_id,
            from_inst,
            to_inst,
        )

    def close_channels_for(self, instance_id: str) -> None:
        """Close all channels to/from the given instance.

        Pending messages in channels targeting this instance are moved
        to the dead letter store with reason CHANNEL_CLOSED.

        Args:
            instance_id: The instance whose channels should be closed.
        """
        for key, channel in self._channels.items():
            from_inst, to_inst = key
            if from_inst == instance_id or to_inst == instance_id:
                # Drain pending messages to dead letters if this channel
                # is targeting the instance being closed
                if to_inst == instance_id:
                    for env in channel.peek_all():
                        self._dead_letters.record(env, DeadLetterReason.CHANNEL_CLOSED)
                channel.close()

        logger.debug("All channels closed for instance_id=%s", instance_id)

    async def pending_for(self, instance_id: str) -> list[MessageEnvelope]:
        """Return all pending messages across all channels targeting this instance.

        Non-blocking, non-draining. Messages remain in their channels.

        Args:
            instance_id: The instance ID to check pending messages for.

        Returns:
            List of pending MessageEnvelopes across all inbound channels.
        """
        result: list[MessageEnvelope] = []
        for key, channel in self._channels.items():
            _, to_inst = key
            if to_inst == instance_id:
                result.extend(channel.peek_all())
        return result

    # -----------------------------------------------------------------------
    # Private validation methods
    # -----------------------------------------------------------------------

    def _check_ttl(self, envelope: MessageEnvelope) -> None:
        """Check if the message has expired based on TTL.

        Args:
            envelope: The message to check.

        Raises:
            RoutingError: If the message has expired (variant=Expired).
        """
        if envelope.ttl_seconds is None:
            return  # No TTL = never expires

        now = datetime.now(UTC)
        age = (now - envelope.sent_at).total_seconds()

        if age > envelope.ttl_seconds:
            self._dead_letters.record(envelope, DeadLetterReason.EXPIRED)
            raise RoutingError.expired(
                message_id=envelope.message_id,
                ttl_seconds=envelope.ttl_seconds,
                age_seconds=age,
            )

    def _check_correlation_id(self, envelope: MessageEnvelope) -> None:
        """Validate correlation_id requirements.

        Rules:
        - CompletionPayload MUST have correlation_id
        - ClarificationPayload with is_response=True MUST have correlation_id

        Args:
            envelope: The message to check.

        Raises:
            RoutingError: If correlation_id is required but missing.
        """
        payload = envelope.payload
        msg_type = envelope.message_type

        if isinstance(payload, CompletionPayload):
            if envelope.correlation_id is None:
                raise RoutingError.correlation_required(
                    message_type=msg_type.value if msg_type else "completion",
                    message_id=envelope.message_id,
                )

        if isinstance(payload, ClarificationPayload) and payload.is_response:
            if envelope.correlation_id is None:
                raise RoutingError.correlation_required(
                    message_type=msg_type.value if msg_type else "clarification",
                    message_id=envelope.message_id,
                )

    def _check_directionality(self, envelope: MessageEnvelope) -> None:
        """Validate message type directionality.

        Rules per Brief 03 Section 3, Invariant 3:
        - Delegation: only parent -> child
        - Status: only child -> parent
        - Completion: only child -> parent
        - Clarification: parent <-> child (bidirectional)
        - Escalation: child -> ancestor (parent, grandparent, etc.)
        - System: any direction

        Args:
            envelope: The message to check.

        Raises:
            RoutingError: If directionality is violated.
        """
        payload = envelope.payload
        from_inst = envelope.from_instance
        to_inst = envelope.to_instance
        msg_type = envelope.message_type

        if isinstance(payload, SystemPayload):
            return  # System messages have no directionality constraint

        if self._lineage_fn is None:
            return  # Cannot check without lineage info

        try:
            to_parent = self._lineage_fn(to_inst)
            from_parent = self._lineage_fn(from_inst)
        except KeyError:
            # If we cannot resolve lineage, skip directionality check
            # (the instance may not be registered yet)
            return

        if isinstance(payload, DelegationPayload):
            # Delegation: sender must be parent of recipient
            if to_parent != from_inst:
                raise RoutingError.directionality_violation(
                    message_type=msg_type.value if msg_type else "delegation",
                    from_instance=from_inst,
                    to_instance=to_inst,
                    detail="Delegation requires sender to be parent of recipient",
                )

        elif isinstance(payload, (StatusPayload, CompletionPayload)):
            # Status/Completion: sender's parent must be recipient
            if from_parent != to_inst:
                type_name = (
                    "status" if isinstance(payload, StatusPayload) else "completion"
                )
                raise RoutingError.directionality_violation(
                    message_type=msg_type.value if msg_type else type_name,
                    from_instance=from_inst,
                    to_instance=to_inst,
                    detail=f"{type_name.capitalize()} requires sender to be child of recipient",
                )

        elif isinstance(payload, ClarificationPayload):
            # Clarification: one must be parent of the other
            is_parent_child = to_parent == from_inst
            is_child_parent = from_parent == to_inst
            if not (is_parent_child or is_child_parent):
                raise RoutingError.directionality_violation(
                    message_type=msg_type.value if msg_type else "clarification",
                    from_instance=from_inst,
                    to_instance=to_inst,
                    detail="Clarification requires a parent-child relationship",
                )

        elif isinstance(payload, EscalationPayload):
            # Escalation: recipient must be an ancestor of sender
            if not self._is_ancestor(to_inst, from_inst):
                raise RoutingError.directionality_violation(
                    message_type=msg_type.value if msg_type else "escalation",
                    from_instance=from_inst,
                    to_instance=to_inst,
                    detail="Escalation requires recipient to be an ancestor of sender",
                )

    def _is_ancestor(self, candidate: str, descendant: str) -> bool:
        """Check if candidate is an ancestor of descendant.

        Walks up the lineage chain from descendant to root, checking
        if candidate appears at any level. Guards against infinite loops
        with a depth limit.

        Args:
            candidate: The instance ID that should be an ancestor.
            descendant: The instance ID that should be a descendant.

        Returns:
            True if candidate is an ancestor of descendant.
        """
        if self._lineage_fn is None:
            return False

        current = descendant
        max_depth = 100  # Guard against infinite loops
        for _ in range(max_depth):
            try:
                parent = self._lineage_fn(current)
            except KeyError:
                return False
            if parent is None:
                return False  # Reached root without finding candidate
            if parent == candidate:
                return True
            current = parent
        logger.warning(
            "Ancestor check depth limit (%d) reached for candidate=%s, descendant=%s",
            max_depth,
            candidate,
            descendant,
        )
        return False

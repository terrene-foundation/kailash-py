# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""L3 messaging error types.

Structured errors with variant tags and .details dicts for channel
and routing operations per Brief 03 Section 2.9.
"""

from __future__ import annotations

import logging
from typing import Any

__all__ = [
    "ChannelError",
    "RoutingError",
]

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# ChannelError
# ---------------------------------------------------------------------------


class ChannelError(Exception):
    """Error during channel operations.

    Variants:
        Closed — channel has been shut down
        Full — channel is at capacity (backpressure)
        Empty — no messages available (non-blocking recv)
    """

    def __init__(
        self,
        message: str,
        *,
        variant: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.variant = variant
        self.details = details or {}
        super().__init__(f"ChannelError({variant}): {message}")

    @classmethod
    def closed(cls, channel_id: str) -> ChannelError:
        return cls(
            f"Channel '{channel_id}' is closed",
            variant="Closed",
            details={"channel_id": channel_id},
        )

    @classmethod
    def full(cls, channel_id: str, capacity: int) -> ChannelError:
        return cls(
            f"Channel '{channel_id}' is full (capacity={capacity})",
            variant="Full",
            details={"channel_id": channel_id, "capacity": capacity},
        )

    @classmethod
    def empty(cls, channel_id: str) -> ChannelError:
        return cls(
            f"Channel '{channel_id}' is empty",
            variant="Empty",
            details={"channel_id": channel_id},
        )


# ---------------------------------------------------------------------------
# RoutingError
# ---------------------------------------------------------------------------


class RoutingError(Exception):
    """Error during message routing.

    Variants:
        Expired — message TTL exceeded before delivery
        SenderNotFound — sender instance ID not in registry
        RecipientNotFound — recipient instance ID not in registry
        RecipientTerminated — recipient in terminal state
        CommunicationBlocked — envelope constraint violation
        DirectionalityViolation — message type not permitted for sender-recipient
        NoChannel — no channel exists between the two instances
        Backpressure — channel at capacity
        ChannelClosed — channel has been shut down
        SelfMessage — sender and recipient are the same
        CorrelationRequired — correlation_id is required but missing
    """

    def __init__(
        self,
        message: str,
        *,
        variant: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.variant = variant
        self.details = details or {}
        super().__init__(f"RoutingError({variant}): {message}")

    @classmethod
    def expired(
        cls, message_id: str, ttl_seconds: float, age_seconds: float
    ) -> RoutingError:
        return cls(
            f"Message '{message_id}' expired: TTL={ttl_seconds}s, age={age_seconds:.2f}s",
            variant="Expired",
            details={
                "message_id": message_id,
                "ttl_seconds": ttl_seconds,
                "age_seconds": age_seconds,
            },
        )

    @classmethod
    def sender_not_found(cls, instance_id: str) -> RoutingError:
        return cls(
            f"Sender '{instance_id}' not found in registry",
            variant="SenderNotFound",
            details={"instance_id": instance_id},
        )

    @classmethod
    def recipient_not_found(cls, instance_id: str) -> RoutingError:
        return cls(
            f"Recipient '{instance_id}' not found in registry",
            variant="RecipientNotFound",
            details={"instance_id": instance_id},
        )

    @classmethod
    def recipient_terminated(cls, instance_id: str, state: str) -> RoutingError:
        return cls(
            f"Recipient '{instance_id}' is in terminal state '{state}'",
            variant="RecipientTerminated",
            details={"instance_id": instance_id, "state": state},
        )

    @classmethod
    def communication_blocked(
        cls, sender: str, recipient: str, detail: str
    ) -> RoutingError:
        return cls(
            f"Communication blocked: sender='{sender}', recipient='{recipient}': {detail}",
            variant="CommunicationBlocked",
            details={"sender": sender, "recipient": recipient, "detail": detail},
        )

    @classmethod
    def directionality_violation(
        cls,
        message_type: str,
        from_instance: str,
        to_instance: str,
        detail: str,
    ) -> RoutingError:
        return cls(
            f"Directionality violation for '{message_type}': "
            f"from='{from_instance}' to='{to_instance}': {detail}",
            variant="DirectionalityViolation",
            details={
                "message_type": message_type,
                "from_instance": from_instance,
                "to_instance": to_instance,
                "detail": detail,
            },
        )

    @classmethod
    def no_channel(cls, from_instance: str, to_instance: str) -> RoutingError:
        return cls(
            f"No channel exists from '{from_instance}' to '{to_instance}'",
            variant="NoChannel",
            details={"from_instance": from_instance, "to_instance": to_instance},
        )

    @classmethod
    def backpressure(cls, channel_id: str, capacity: int) -> RoutingError:
        return cls(
            f"Channel '{channel_id}' at capacity ({capacity}), backpressure applied",
            variant="Backpressure",
            details={"channel_id": channel_id, "capacity": capacity},
        )

    @classmethod
    def channel_closed(cls, channel_id: str) -> RoutingError:
        return cls(
            f"Channel '{channel_id}' is closed",
            variant="ChannelClosed",
            details={"channel_id": channel_id},
        )

    @classmethod
    def self_message(cls, instance_id: str) -> RoutingError:
        return cls(
            f"Self-message not permitted: from='{instance_id}' to='{instance_id}'",
            variant="SelfMessage",
            details={"instance_id": instance_id},
        )

    @classmethod
    def correlation_required(cls, message_type: str, message_id: str) -> RoutingError:
        return cls(
            f"correlation_id is required for '{message_type}' "
            f"message '{message_id}'",
            variant="CorrelationRequired",
            details={"message_type": message_type, "message_id": message_id},
        )

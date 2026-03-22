# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Inter-agent messaging with typed payloads and envelope-aware routing."""

from __future__ import annotations

from kaizen.l3.messaging.channel import MessageChannel
from kaizen.l3.messaging.dead_letters import DeadLetterReason, DeadLetterStore
from kaizen.l3.messaging.errors import ChannelError, RoutingError
from kaizen.l3.messaging.router import MessageRouter
from kaizen.l3.messaging.types import (
    ClarificationPayload,
    CompletionPayload,
    DelegationPayload,
    EscalationPayload,
    EscalationSeverity,
    MessageEnvelope,
    MessageType,
    Priority,
    ResourceSnapshot,
    StatusPayload,
    SystemPayload,
    SystemSubtype,
)

__all__ = [
    # Channel
    "MessageChannel",
    # Dead Letters
    "DeadLetterReason",
    "DeadLetterStore",
    # Errors
    "ChannelError",
    "RoutingError",
    # Router
    "MessageRouter",
    # Types (re-exported for convenience)
    "ClarificationPayload",
    "CompletionPayload",
    "DelegationPayload",
    "EscalationPayload",
    "EscalationSeverity",
    "MessageEnvelope",
    "MessageType",
    "Priority",
    "ResourceSnapshot",
    "StatusPayload",
    "SystemPayload",
    "SystemSubtype",
]

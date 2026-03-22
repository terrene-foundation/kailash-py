# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""DeadLetterStore — bounded ring buffer for undeliverable messages.

Captures messages that could not be delivered, with the reason for failure.
Uses collections.deque(maxlen=max_capacity) for bounded ring-buffer semantics:
oldest entries are evicted automatically when capacity is reached.
"""

from __future__ import annotations

import logging
from collections import deque
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from kaizen.l3.messaging.types import MessageEnvelope

__all__ = [
    "DeadLetterReason",
    "DeadLetterStore",
]

logger = logging.getLogger(__name__)

# Type alias for a dead letter entry: (envelope, reason, timestamp)
DeadLetterEntry = tuple[MessageEnvelope, "DeadLetterReason", datetime]

# Default maximum capacity for the dead letter store
_DEFAULT_MAX_CAPACITY = 10000


# ---------------------------------------------------------------------------
# DeadLetterReason Enum
# ---------------------------------------------------------------------------


class DeadLetterReason(str, Enum):
    """Reason a message was captured as a dead letter.

    Per Brief 03 Section 2.6.
    """

    EXPIRED = "expired"
    RECIPIENT_TERMINATED = "recipient_terminated"
    RECIPIENT_NOT_FOUND = "recipient_not_found"
    SENDER_NOT_FOUND = "sender_not_found"
    COMMUNICATION_BLOCKED = "communication_blocked"
    CHANNEL_CLOSED = "channel_closed"
    CHANNEL_FULL = "channel_full"


# ---------------------------------------------------------------------------
# DeadLetterStore
# ---------------------------------------------------------------------------


class DeadLetterStore:
    """Bounded ring buffer for undeliverable messages.

    Uses collections.deque(maxlen=max_capacity) to automatically evict
    the oldest entries when at capacity. Thread-safe for append operations
    (deque.append is atomic in CPython).

    Args:
        max_capacity: Maximum number of entries to retain. Must be > 0.
    """

    __slots__ = ("_entries", "_max_capacity")

    def __init__(self, max_capacity: int = _DEFAULT_MAX_CAPACITY) -> None:
        if max_capacity <= 0:
            raise ValueError(f"max_capacity must be positive, got {max_capacity}")
        self._max_capacity = max_capacity
        self._entries: deque[DeadLetterEntry] = deque(maxlen=max_capacity)

    def record(
        self,
        envelope: MessageEnvelope,
        reason: DeadLetterReason,
    ) -> None:
        """Record a dead letter entry.

        If at capacity, the oldest entry is evicted automatically
        by the deque's maxlen constraint.

        Args:
            envelope: The undeliverable message envelope.
            reason: Why the message could not be delivered.
        """
        timestamp = datetime.now(UTC)
        self._entries.append((envelope, reason, timestamp))
        logger.debug(
            "Dead letter recorded: message_id=%s, to=%s, reason=%s",
            envelope.message_id,
            envelope.to_instance,
            reason.value,
        )

    def recent(self, limit: int) -> list[DeadLetterEntry]:
        """Return the most recent entries, newest first.

        Args:
            limit: Maximum number of entries to return.

        Returns:
            List of (envelope, reason, timestamp) tuples, newest first.
        """
        # deque stores oldest-first, so reverse for newest-first
        entries = list(reversed(self._entries))
        return entries[:limit]

    def count(self) -> int:
        """Total number of entries currently stored."""
        return len(self._entries)

    def drain_for(self, instance_id: str) -> list[DeadLetterEntry]:
        """Remove and return all dead letters where to_instance matches.

        Args:
            instance_id: The instance ID to drain dead letters for.

        Returns:
            List of (envelope, reason, timestamp) tuples that were removed.
        """
        drained: list[DeadLetterEntry] = []
        remaining: deque[DeadLetterEntry] = deque(maxlen=self._max_capacity)
        for entry in self._entries:
            if entry[0].to_instance == instance_id:
                drained.append(entry)
            else:
                remaining.append(entry)
        self._entries = remaining
        logger.debug(
            "Drained %d dead letters for instance_id=%s",
            len(drained),
            instance_id,
        )
        return drained

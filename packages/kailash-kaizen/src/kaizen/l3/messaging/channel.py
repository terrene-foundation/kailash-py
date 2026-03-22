# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""MessageChannel — bounded async point-to-point communication channel.

Implements a unidirectional, bounded, async channel between two agent
instances. Uses asyncio.PriorityQueue for priority-ordered message
delivery. Higher Priority values are dequeued first.

Per Brief 03 Section 2.4.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any

from kaizen.l3.messaging.errors import ChannelError
from kaizen.l3.messaging.types import (
    DelegationPayload,
    MessageEnvelope,
    Priority,
)

__all__ = ["MessageChannel"]

logger = logging.getLogger(__name__)


def _get_envelope_priority(envelope: MessageEnvelope) -> Priority:
    """Extract priority from an envelope's payload.

    DelegationPayload carries an explicit priority field.
    Other payloads default to Priority.NORMAL.
    """
    if isinstance(envelope.payload, DelegationPayload):
        return envelope.payload.priority
    return Priority.NORMAL


class MessageChannel:
    """Bounded, async, unidirectional, point-to-point channel.

    Uses asyncio.PriorityQueue(maxsize=capacity) for priority ordering.
    Messages with higher Priority value dequeue first. Within the same
    priority level, FIFO ordering is preserved via a sequence counter.

    Priority ordering uses (-priority, sequence_num, envelope) tuples
    in the PriorityQueue so that higher numeric Priority values (CRITICAL=3)
    are dequeued before lower ones (LOW=0).

    Args:
        channel_id: Unique identifier for this channel. Auto-generated if not provided.
        from_instance: Instance ID of the sender endpoint. Must be non-empty.
        to_instance: Instance ID of the receiver endpoint. Must be non-empty.
        capacity: Maximum number of undelivered messages. Must be > 0.
    """

    __slots__ = (
        "_capacity",
        "_channel_id",
        "_closed",
        "_from_instance",
        "_queue",
        "_seq",
        "_to_instance",
    )

    def __init__(
        self,
        from_instance: str,
        to_instance: str,
        capacity: int,
        channel_id: str | None = None,
    ) -> None:
        if not from_instance:
            raise ValueError("from_instance must be a non-empty string")
        if not to_instance:
            raise ValueError("to_instance must be a non-empty string")
        if capacity <= 0:
            raise ValueError(f"capacity must be positive, got {capacity}")

        self._channel_id = channel_id or str(uuid.uuid4())
        self._from_instance = from_instance
        self._to_instance = to_instance
        self._capacity = capacity
        self._closed = False
        self._seq = 0
        # PriorityQueue: items are (-priority, seq, envelope)
        # Negative priority ensures higher Priority values come first
        self._queue: asyncio.PriorityQueue[tuple[int, int, MessageEnvelope]] = (
            asyncio.PriorityQueue(maxsize=capacity)
        )

    @property
    def channel_id(self) -> str:
        """Unique identifier for this channel."""
        return self._channel_id

    @property
    def from_instance(self) -> str:
        """Instance ID of the sender endpoint."""
        return self._from_instance

    @property
    def to_instance(self) -> str:
        """Instance ID of the receiver endpoint."""
        return self._to_instance

    @property
    def capacity(self) -> int:
        """Maximum number of undelivered messages."""
        return self._capacity

    async def send(self, envelope: MessageEnvelope) -> None:
        """Enqueue a message on this channel.

        Raises ChannelError if the channel is closed or at capacity.

        Args:
            envelope: The message envelope to send.

        Raises:
            ChannelError: If channel is closed (variant=Closed)
                or at capacity (variant=Full).
        """
        if self._closed:
            raise ChannelError.closed(self._channel_id)

        priority = _get_envelope_priority(envelope)
        # Negative priority so higher enum values (CRITICAL=3) sort first
        item = (-priority.value, self._seq, envelope)
        self._seq += 1

        try:
            self._queue.put_nowait(item)
        except asyncio.QueueFull:
            raise ChannelError.full(self._channel_id, self._capacity)

        logger.debug(
            "Channel %s: message %s queued (priority=%s, pending=%d)",
            self._channel_id,
            envelope.message_id,
            priority.name,
            self._queue.qsize(),
        )

    async def recv(self) -> MessageEnvelope:
        """Block until a message is available and return it.

        If the channel is closed AND empty, raises ChannelError.
        If the channel is closed but has pending messages, returns
        the next message (drain semantics).

        Returns:
            The next MessageEnvelope in priority order.

        Raises:
            ChannelError: If channel is closed and empty (variant=Closed).
        """
        if self._closed and self._queue.empty():
            raise ChannelError.closed(self._channel_id)

        if self._closed:
            # Drain mode: return pending messages without blocking
            _, _, envelope = self._queue.get_nowait()
            return envelope

        # Normal mode: block until a message is available
        _, _, envelope = await self._queue.get()
        return envelope

    def try_recv(self) -> MessageEnvelope | None:
        """Non-blocking receive.

        Returns the next message if available, None if the queue is empty
        (and the channel is still open).

        Returns:
            The next MessageEnvelope, or None if no message available.

        Raises:
            ChannelError: If channel is closed and empty (variant=Closed).
        """
        if self._closed and self._queue.empty():
            raise ChannelError.closed(self._channel_id)

        if self._queue.empty():
            return None

        _, _, envelope = self._queue.get_nowait()
        return envelope

    def is_closed(self) -> bool:
        """Return True if the channel has been shut down."""
        return self._closed

    def pending_count(self) -> int:
        """Number of messages currently buffered."""
        return self._queue.qsize()

    def close(self) -> None:
        """Close the channel. Prevents new sends; allows draining pending.

        Idempotent: calling close() multiple times is safe.
        """
        if not self._closed:
            logger.debug(
                "Channel %s: closing (pending=%d)",
                self._channel_id,
                self._queue.qsize(),
            )
        self._closed = True

    def peek_all(self) -> list[MessageEnvelope]:
        """Non-destructive peek at all pending messages.

        Returns envelopes in priority order without removing them.
        Used by MessageRouter.pending_for() for non-draining inspection.

        Returns:
            List of all pending MessageEnvelopes in priority order.
        """
        # Access the internal queue data structure
        # PriorityQueue wraps a list that heapq maintains
        items = sorted(self._queue._queue)  # type: ignore[attr-defined]
        return [envelope for _, _, envelope in items]

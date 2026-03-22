# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tests for M3: MessageChannel — bounded async point-to-point channel.

Tests cover:
- Construction and field validation
- send/recv lifecycle
- Priority ordering (higher priority dequeued first)
- Backpressure when full
- Close semantics (no new sends, can drain)
- try_recv non-blocking behavior
- pending_count accuracy
"""

from __future__ import annotations

import asyncio

import pytest

from kaizen.l3.messaging.channel import MessageChannel
from kaizen.l3.messaging.errors import ChannelError
from kaizen.l3.messaging.types import (
    DelegationPayload,
    MessageEnvelope,
    Priority,
    StatusPayload,
    SystemPayload,
    SystemSubtype,
)


def _envelope(
    from_inst: str = "sender",
    to_inst: str = "receiver",
    priority: Priority = Priority.NORMAL,
) -> MessageEnvelope:
    """Helper to create a test envelope with given priority."""
    return MessageEnvelope(
        from_instance=from_inst,
        to_instance=to_inst,
        payload=DelegationPayload(
            task_description="test task",
            priority=priority,
        ),
    )


class TestMessageChannelConstruction:
    """Test channel creation and field initialization."""

    def test_construction_fields(self):
        ch = MessageChannel(
            from_instance="parent-001",
            to_instance="child-001",
            capacity=10,
        )
        assert ch.from_instance == "parent-001"
        assert ch.to_instance == "child-001"
        assert ch.capacity == 10
        assert ch.channel_id  # UUID generated
        assert ch.is_closed() is False
        assert ch.pending_count() == 0

    def test_custom_channel_id(self):
        ch = MessageChannel(
            channel_id="custom-id",
            from_instance="a",
            to_instance="b",
            capacity=5,
        )
        assert ch.channel_id == "custom-id"

    def test_capacity_must_be_positive(self):
        with pytest.raises(ValueError, match="capacity"):
            MessageChannel(from_instance="a", to_instance="b", capacity=0)
        with pytest.raises(ValueError, match="capacity"):
            MessageChannel(from_instance="a", to_instance="b", capacity=-1)

    def test_from_instance_required(self):
        with pytest.raises(ValueError, match="from_instance"):
            MessageChannel(from_instance="", to_instance="b", capacity=5)

    def test_to_instance_required(self):
        with pytest.raises(ValueError, match="to_instance"):
            MessageChannel(from_instance="a", to_instance="", capacity=5)


class TestMessageChannelSendRecv:
    """Test basic send and receive operations."""

    @pytest.mark.asyncio
    async def test_send_and_recv_single_message(self):
        ch = MessageChannel(from_instance="a", to_instance="b", capacity=10)
        env = _envelope()
        await ch.send(env)
        assert ch.pending_count() == 1
        received = await ch.recv()
        assert received.message_id == env.message_id
        assert ch.pending_count() == 0

    @pytest.mark.asyncio
    async def test_send_multiple_recv_fifo_same_priority(self):
        """Messages with same priority are delivered FIFO."""
        ch = MessageChannel(from_instance="a", to_instance="b", capacity=10)
        envs = [_envelope(priority=Priority.NORMAL) for _ in range(3)]
        for e in envs:
            await ch.send(e)
        received = []
        for _ in range(3):
            received.append(await ch.recv())
        assert [r.message_id for r in received] == [e.message_id for e in envs]

    @pytest.mark.asyncio
    async def test_recv_blocks_until_message_available(self):
        """recv() should block until a message is sent."""
        ch = MessageChannel(from_instance="a", to_instance="b", capacity=10)
        received = []

        async def consumer():
            msg = await ch.recv()
            received.append(msg)

        async def producer():
            await asyncio.sleep(0.05)
            await ch.send(_envelope())

        await asyncio.gather(consumer(), producer())
        assert len(received) == 1

    @pytest.mark.asyncio
    async def test_pending_count_reflects_queue_size(self):
        ch = MessageChannel(from_instance="a", to_instance="b", capacity=10)
        assert ch.pending_count() == 0
        await ch.send(_envelope())
        assert ch.pending_count() == 1
        await ch.send(_envelope())
        assert ch.pending_count() == 2
        await ch.recv()
        assert ch.pending_count() == 1


class TestMessageChannelPriorityOrdering:
    """Test that higher-priority messages are dequeued first."""

    @pytest.mark.asyncio
    async def test_higher_priority_dequeued_first(self):
        ch = MessageChannel(from_instance="a", to_instance="b", capacity=10)
        low = _envelope(priority=Priority.LOW)
        normal = _envelope(priority=Priority.NORMAL)
        high = _envelope(priority=Priority.HIGH)
        critical = _envelope(priority=Priority.CRITICAL)

        # Send in arbitrary order
        await ch.send(normal)
        await ch.send(low)
        await ch.send(critical)
        await ch.send(high)

        received = []
        for _ in range(4):
            received.append(await ch.recv())

        # Should be: critical, high, normal, low
        assert received[0].message_id == critical.message_id
        assert received[1].message_id == high.message_id
        assert received[2].message_id == normal.message_id
        assert received[3].message_id == low.message_id

    @pytest.mark.asyncio
    async def test_same_priority_preserves_insertion_order(self):
        """Within the same priority level, FIFO ordering is preserved."""
        ch = MessageChannel(from_instance="a", to_instance="b", capacity=10)
        first = _envelope(priority=Priority.HIGH)
        second = _envelope(priority=Priority.HIGH)
        third = _envelope(priority=Priority.HIGH)

        await ch.send(first)
        await ch.send(second)
        await ch.send(third)

        r1 = await ch.recv()
        r2 = await ch.recv()
        r3 = await ch.recv()

        assert r1.message_id == first.message_id
        assert r2.message_id == second.message_id
        assert r3.message_id == third.message_id


class TestMessageChannelBackpressure:
    """Test behavior when channel is at capacity."""

    @pytest.mark.asyncio
    async def test_send_raises_when_full(self):
        ch = MessageChannel(from_instance="a", to_instance="b", capacity=2)
        await ch.send(_envelope())
        await ch.send(_envelope())
        with pytest.raises(ChannelError, match="[Ff]ull"):
            await ch.send(_envelope())

    @pytest.mark.asyncio
    async def test_send_succeeds_after_drain(self):
        ch = MessageChannel(from_instance="a", to_instance="b", capacity=1)
        await ch.send(_envelope())
        with pytest.raises(ChannelError, match="[Ff]ull"):
            await ch.send(_envelope())
        # Drain one
        await ch.recv()
        # Now should succeed
        await ch.send(_envelope())
        assert ch.pending_count() == 1


class TestMessageChannelCloseSemantics:
    """Test channel close behavior."""

    @pytest.mark.asyncio
    async def test_send_raises_after_close(self):
        ch = MessageChannel(from_instance="a", to_instance="b", capacity=10)
        ch.close()
        assert ch.is_closed() is True
        with pytest.raises(ChannelError, match="[Cc]losed"):
            await ch.send(_envelope())

    @pytest.mark.asyncio
    async def test_recv_drains_pending_after_close(self):
        """After close, pending messages can still be received."""
        ch = MessageChannel(from_instance="a", to_instance="b", capacity=10)
        env = _envelope()
        await ch.send(env)
        ch.close()
        # Should still be able to recv the pending message
        received = await ch.recv()
        assert received.message_id == env.message_id

    @pytest.mark.asyncio
    async def test_recv_raises_when_closed_and_empty(self):
        ch = MessageChannel(from_instance="a", to_instance="b", capacity=10)
        ch.close()
        with pytest.raises(ChannelError, match="[Cc]losed"):
            await ch.recv()

    @pytest.mark.asyncio
    async def test_close_is_idempotent(self):
        ch = MessageChannel(from_instance="a", to_instance="b", capacity=10)
        ch.close()
        ch.close()  # Should not raise
        assert ch.is_closed() is True


class TestMessageChannelTryRecv:
    """Test non-blocking try_recv."""

    @pytest.mark.asyncio
    async def test_try_recv_returns_none_when_empty(self):
        ch = MessageChannel(from_instance="a", to_instance="b", capacity=10)
        result = ch.try_recv()
        assert result is None

    @pytest.mark.asyncio
    async def test_try_recv_returns_message_when_available(self):
        ch = MessageChannel(from_instance="a", to_instance="b", capacity=10)
        env = _envelope()
        await ch.send(env)
        result = ch.try_recv()
        assert result is not None
        assert result.message_id == env.message_id
        assert ch.pending_count() == 0

    @pytest.mark.asyncio
    async def test_try_recv_raises_when_closed_and_empty(self):
        ch = MessageChannel(from_instance="a", to_instance="b", capacity=10)
        ch.close()
        with pytest.raises(ChannelError, match="[Cc]losed"):
            ch.try_recv()

    @pytest.mark.asyncio
    async def test_try_recv_drains_pending_after_close(self):
        ch = MessageChannel(from_instance="a", to_instance="b", capacity=10)
        env = _envelope()
        await ch.send(env)
        ch.close()
        result = ch.try_recv()
        assert result is not None
        assert result.message_id == env.message_id

    @pytest.mark.asyncio
    async def test_try_recv_respects_priority(self):
        ch = MessageChannel(from_instance="a", to_instance="b", capacity=10)
        low = _envelope(priority=Priority.LOW)
        high = _envelope(priority=Priority.HIGH)
        await ch.send(low)
        await ch.send(high)
        result = ch.try_recv()
        assert result is not None
        assert result.message_id == high.message_id

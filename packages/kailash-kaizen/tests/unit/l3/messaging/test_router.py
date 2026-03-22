# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tests for M3: MessageRouter — envelope-aware routing layer.

Tests cover:
- Channel creation and management
- Routing validation: TTL expiry, self-message, channel existence
- Directionality enforcement (Delegation parent->child, Status child->parent, etc.)
- Correlation ID validation (Completion requires correlation_id)
- Dead letter recording on routing failures
- close_channels_for lifecycle
- pending_for retrieval
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest

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
    Priority,
    StatusPayload,
    SystemPayload,
    SystemSubtype,
)


def _delegation_envelope(
    from_inst: str = "parent",
    to_inst: str = "child",
    ttl: float | None = None,
    correlation_id: str | None = None,
) -> MessageEnvelope:
    return MessageEnvelope(
        from_instance=from_inst,
        to_instance=to_inst,
        payload=DelegationPayload(task_description="test"),
        ttl_seconds=ttl,
        correlation_id=correlation_id,
    )


def _status_envelope(
    from_inst: str = "child",
    to_inst: str = "parent",
) -> MessageEnvelope:
    return MessageEnvelope(
        from_instance=from_inst,
        to_instance=to_inst,
        payload=StatusPayload(phase="analyzing"),
    )


def _completion_envelope(
    from_inst: str = "child",
    to_inst: str = "parent",
    correlation_id: str | None = "delegation-msg-id",
) -> MessageEnvelope:
    return MessageEnvelope(
        from_instance=from_inst,
        to_instance=to_inst,
        payload=CompletionPayload(result="done"),
        correlation_id=correlation_id,
    )


def _clarification_envelope(
    from_inst: str = "child",
    to_inst: str = "parent",
    is_response: bool = False,
    correlation_id: str | None = None,
) -> MessageEnvelope:
    return MessageEnvelope(
        from_instance=from_inst,
        to_instance=to_inst,
        payload=ClarificationPayload(
            question="what format?",
            is_response=is_response,
        ),
        correlation_id=correlation_id,
    )


def _escalation_envelope(
    from_inst: str = "child",
    to_inst: str = "parent",
) -> MessageEnvelope:
    return MessageEnvelope(
        from_instance=from_inst,
        to_instance=to_inst,
        payload=EscalationPayload(
            severity=EscalationSeverity.WARNING,
            problem_description="budget alert",
        ),
    )


def _system_envelope(
    from_inst: str = "system",
    to_inst: str = "child",
) -> MessageEnvelope:
    return MessageEnvelope(
        from_instance=from_inst,
        to_instance=to_inst,
        payload=SystemPayload(subtype=SystemSubtype.HEARTBEAT_REQUEST),
    )


class TestMessageRouterConstruction:
    """Test router creation."""

    def test_construction(self):
        router = MessageRouter()
        assert router.dead_letters is not None
        assert router.dead_letters.count() == 0

    def test_custom_dead_letter_store(self):
        dl = DeadLetterStore(max_capacity=5)
        router = MessageRouter(dead_letters=dl)
        assert router.dead_letters is dl


class TestMessageRouterChannelCreation:
    """Test create_channel and channel management."""

    def test_create_channel(self):
        router = MessageRouter()
        ch = router.create_channel("parent", "child", capacity=10)
        assert isinstance(ch, MessageChannel)
        assert ch.from_instance == "parent"
        assert ch.to_instance == "child"

    def test_create_channel_duplicate_raises(self):
        router = MessageRouter()
        router.create_channel("parent", "child", capacity=10)
        with pytest.raises(RoutingError, match="already exists"):
            router.create_channel("parent", "child", capacity=10)

    def test_create_bidirectional_channels(self):
        router = MessageRouter()
        ch1 = router.create_channel("parent", "child", capacity=10)
        ch2 = router.create_channel("child", "parent", capacity=10)
        assert ch1.channel_id != ch2.channel_id


class TestMessageRouterBasicRouting:
    """Test basic message routing through channels."""

    @pytest.mark.asyncio
    async def test_route_delivers_to_channel(self):
        router = MessageRouter()
        router.create_channel("parent", "child", capacity=10)
        env = _delegation_envelope(from_inst="parent", to_inst="child")
        await router.route(env)
        # Message should be in the channel
        pending = await router.pending_for("child")
        assert len(pending) == 1
        assert pending[0].message_id == env.message_id

    @pytest.mark.asyncio
    async def test_route_no_channel_raises(self):
        router = MessageRouter()
        env = _delegation_envelope(from_inst="a", to_inst="b")
        with pytest.raises(RoutingError, match="[Nn]o channel"):
            await router.route(env)

    @pytest.mark.asyncio
    async def test_route_records_dead_letter_on_no_channel(self):
        """When no channel exists, the message goes to dead letters."""
        router = MessageRouter()
        env = _delegation_envelope(from_inst="a", to_inst="b")
        with pytest.raises(RoutingError):
            await router.route(env)
        assert router.dead_letters.count() == 0  # NoChannel doesn't dead-letter


class TestMessageRouterTTLValidation:
    """Test TTL expiry check."""

    @pytest.mark.asyncio
    async def test_expired_message_rejected(self):
        router = MessageRouter()
        router.create_channel("parent", "child", capacity=10)
        # Create an envelope with sent_at in the past and very short TTL
        env = MessageEnvelope(
            from_instance="parent",
            to_instance="child",
            payload=DelegationPayload(task_description="test"),
            sent_at=datetime.now(UTC) - timedelta(seconds=10),
            ttl_seconds=1.0,
        )
        with pytest.raises(RoutingError, match="[Ee]xpired"):
            await router.route(env)

    @pytest.mark.asyncio
    async def test_expired_message_goes_to_dead_letters(self):
        router = MessageRouter()
        router.create_channel("parent", "child", capacity=10)
        env = MessageEnvelope(
            from_instance="parent",
            to_instance="child",
            payload=DelegationPayload(task_description="test"),
            sent_at=datetime.now(UTC) - timedelta(seconds=10),
            ttl_seconds=1.0,
        )
        with pytest.raises(RoutingError):
            await router.route(env)
        assert router.dead_letters.count() == 1

    @pytest.mark.asyncio
    async def test_non_expired_message_delivered(self):
        router = MessageRouter()
        router.create_channel("parent", "child", capacity=10)
        env = _delegation_envelope(from_inst="parent", to_inst="child", ttl=60.0)
        await router.route(env)
        pending = await router.pending_for("child")
        assert len(pending) == 1

    @pytest.mark.asyncio
    async def test_no_ttl_message_never_expires(self):
        router = MessageRouter()
        router.create_channel("parent", "child", capacity=10)
        env = _delegation_envelope(from_inst="parent", to_inst="child", ttl=None)
        await router.route(env)
        pending = await router.pending_for("child")
        assert len(pending) == 1


class TestMessageRouterSelfMessage:
    """Test self-message rejection."""

    @pytest.mark.asyncio
    async def test_self_message_rejected(self):
        router = MessageRouter()
        router.create_channel("agent", "agent", capacity=10)
        env = _delegation_envelope(from_inst="agent", to_inst="agent")
        with pytest.raises(RoutingError, match="[Ss]elf"):
            await router.route(env)


class TestMessageRouterDirectionality:
    """Test message type directionality enforcement.

    The router uses a lineage callback to determine parent-child relationships.
    When no callback is provided, directionality checks are skipped (for M3
    independent testability -- M4 integration will wire in the registry).
    """

    def _make_router_with_lineage(
        self,
        parent_of: dict[str, str | None] | None = None,
    ) -> MessageRouter:
        """Create a router with a lineage callback.

        parent_of maps instance_id -> parent_id (None for root).
        """
        parent_of = parent_of or {}

        def lineage_callback(instance_id: str) -> str | None:
            if instance_id not in parent_of:
                raise KeyError(f"Unknown instance: {instance_id}")
            return parent_of[instance_id]

        return MessageRouter(lineage_fn=lineage_callback)

    @pytest.mark.asyncio
    async def test_delegation_parent_to_child_ok(self):
        router = self._make_router_with_lineage({"parent": None, "child": "parent"})
        router.create_channel("parent", "child", capacity=10)
        env = _delegation_envelope(from_inst="parent", to_inst="child")
        await router.route(env)  # Should not raise

    @pytest.mark.asyncio
    async def test_delegation_child_to_parent_rejected(self):
        router = self._make_router_with_lineage({"parent": None, "child": "parent"})
        router.create_channel("child", "parent", capacity=10)
        env = MessageEnvelope(
            from_instance="child",
            to_instance="parent",
            payload=DelegationPayload(task_description="test"),
        )
        with pytest.raises(RoutingError, match="[Dd]irection"):
            await router.route(env)

    @pytest.mark.asyncio
    async def test_status_child_to_parent_ok(self):
        router = self._make_router_with_lineage({"parent": None, "child": "parent"})
        router.create_channel("child", "parent", capacity=10)
        env = _status_envelope(from_inst="child", to_inst="parent")
        await router.route(env)

    @pytest.mark.asyncio
    async def test_status_parent_to_child_rejected(self):
        router = self._make_router_with_lineage({"parent": None, "child": "parent"})
        router.create_channel("parent", "child", capacity=10)
        env = MessageEnvelope(
            from_instance="parent",
            to_instance="child",
            payload=StatusPayload(phase="working"),
        )
        with pytest.raises(RoutingError, match="[Dd]irection"):
            await router.route(env)

    @pytest.mark.asyncio
    async def test_completion_child_to_parent_ok(self):
        router = self._make_router_with_lineage({"parent": None, "child": "parent"})
        router.create_channel("child", "parent", capacity=10)
        env = _completion_envelope(from_inst="child", to_inst="parent")
        await router.route(env)

    @pytest.mark.asyncio
    async def test_completion_parent_to_child_rejected(self):
        router = self._make_router_with_lineage({"parent": None, "child": "parent"})
        router.create_channel("parent", "child", capacity=10)
        env = MessageEnvelope(
            from_instance="parent",
            to_instance="child",
            payload=CompletionPayload(result="done"),
            correlation_id="some-id",
        )
        with pytest.raises(RoutingError, match="[Dd]irection"):
            await router.route(env)

    @pytest.mark.asyncio
    async def test_clarification_child_to_parent_ok(self):
        router = self._make_router_with_lineage({"parent": None, "child": "parent"})
        router.create_channel("child", "parent", capacity=10)
        env = _clarification_envelope(from_inst="child", to_inst="parent")
        await router.route(env)

    @pytest.mark.asyncio
    async def test_clarification_parent_to_child_ok(self):
        """Clarification is bidirectional (parent answers child's question)."""
        router = self._make_router_with_lineage({"parent": None, "child": "parent"})
        router.create_channel("parent", "child", capacity=10)
        env = _clarification_envelope(
            from_inst="parent",
            to_inst="child",
            is_response=True,
            correlation_id="original-question-id",
        )
        await router.route(env)

    @pytest.mark.asyncio
    async def test_escalation_child_to_parent_ok(self):
        router = self._make_router_with_lineage(
            {"root": None, "parent": "root", "child": "parent"}
        )
        router.create_channel("child", "parent", capacity=10)
        env = _escalation_envelope(from_inst="child", to_inst="parent")
        await router.route(env)

    @pytest.mark.asyncio
    async def test_escalation_child_to_grandparent_ok(self):
        """Escalation can go to any ancestor."""
        router = self._make_router_with_lineage(
            {"root": None, "parent": "root", "child": "parent"}
        )
        router.create_channel("child", "root", capacity=10)
        env = _escalation_envelope(from_inst="child", to_inst="root")
        await router.route(env)

    @pytest.mark.asyncio
    async def test_escalation_parent_to_child_rejected(self):
        router = self._make_router_with_lineage({"parent": None, "child": "parent"})
        router.create_channel("parent", "child", capacity=10)
        env = MessageEnvelope(
            from_instance="parent",
            to_instance="child",
            payload=EscalationPayload(
                severity=EscalationSeverity.WARNING,
                problem_description="test",
            ),
        )
        with pytest.raises(RoutingError, match="[Dd]irection"):
            await router.route(env)

    @pytest.mark.asyncio
    async def test_system_any_direction_ok(self):
        """System messages have no directionality constraint."""
        router = self._make_router_with_lineage(
            {"parent": None, "child": "parent", "system": None}
        )
        router.create_channel("system", "child", capacity=10)
        env = _system_envelope(from_inst="system", to_inst="child")
        await router.route(env)

    @pytest.mark.asyncio
    async def test_no_lineage_fn_skips_directionality_check(self):
        """When no lineage_fn is provided, directionality is not enforced."""
        router = MessageRouter()  # No lineage_fn
        router.create_channel("a", "b", capacity=10)
        # Even delegation from "b" to "a" would be allowed
        env = _delegation_envelope(from_inst="a", to_inst="b")
        await router.route(env)


class TestMessageRouterCorrelationID:
    """Test correlation_id validation rules."""

    @pytest.mark.asyncio
    async def test_completion_requires_correlation_id(self):
        router = MessageRouter()
        router.create_channel("child", "parent", capacity=10)
        env = _completion_envelope(
            from_inst="child", to_inst="parent", correlation_id=None
        )
        with pytest.raises(RoutingError, match="correlation_id"):
            await router.route(env)

    @pytest.mark.asyncio
    async def test_completion_with_correlation_id_ok(self):
        router = MessageRouter()
        router.create_channel("child", "parent", capacity=10)
        env = _completion_envelope(
            from_inst="child", to_inst="parent", correlation_id="delegation-id"
        )
        await router.route(env)

    @pytest.mark.asyncio
    async def test_clarification_response_requires_correlation_id(self):
        router = MessageRouter()
        router.create_channel("parent", "child", capacity=10)
        env = MessageEnvelope(
            from_instance="parent",
            to_instance="child",
            payload=ClarificationPayload(
                question="use JSON",
                is_response=True,
            ),
            correlation_id=None,  # Missing!
        )
        with pytest.raises(RoutingError, match="correlation_id"):
            await router.route(env)

    @pytest.mark.asyncio
    async def test_clarification_question_does_not_require_correlation_id(self):
        router = MessageRouter()
        router.create_channel("child", "parent", capacity=10)
        env = _clarification_envelope(
            from_inst="child", to_inst="parent", is_response=False, correlation_id=None
        )
        await router.route(env)


class TestMessageRouterCloseChannelsFor:
    """Test close_channels_for lifecycle management."""

    @pytest.mark.asyncio
    async def test_closes_all_channels_to_and_from_instance(self):
        router = MessageRouter()
        ch1 = router.create_channel("parent", "child", capacity=10)
        ch2 = router.create_channel("child", "parent", capacity=10)
        router.close_channels_for("child")
        assert ch1.is_closed()
        assert ch2.is_closed()

    @pytest.mark.asyncio
    async def test_pending_messages_moved_to_dead_letters(self):
        router = MessageRouter()
        router.create_channel("parent", "child", capacity=10)
        env = _delegation_envelope(from_inst="parent", to_inst="child")
        await router.route(env)
        router.close_channels_for("child")
        # Pending message should now be in dead letters
        assert router.dead_letters.count() == 1

    @pytest.mark.asyncio
    async def test_new_sends_fail_after_close(self):
        router = MessageRouter()
        router.create_channel("parent", "child", capacity=10)
        router.close_channels_for("child")
        env = _delegation_envelope(from_inst="parent", to_inst="child")
        with pytest.raises(RoutingError):
            await router.route(env)

    @pytest.mark.asyncio
    async def test_close_nonexistent_instance_is_noop(self):
        router = MessageRouter()
        router.close_channels_for("nonexistent")  # Should not raise


class TestMessageRouterPendingFor:
    """Test pending_for retrieval."""

    @pytest.mark.asyncio
    async def test_pending_for_returns_all_pending(self):
        router = MessageRouter()
        router.create_channel("a", "target", capacity=10)
        router.create_channel("b", "target", capacity=10)
        env1 = _delegation_envelope(from_inst="a", to_inst="target")
        env2 = _delegation_envelope(from_inst="b", to_inst="target")
        await router.route(env1)
        await router.route(env2)
        pending = await router.pending_for("target")
        assert len(pending) == 2

    @pytest.mark.asyncio
    async def test_pending_for_is_non_draining(self):
        """pending_for does not remove messages from channels."""
        router = MessageRouter()
        router.create_channel("a", "target", capacity=10)
        await router.route(_delegation_envelope(from_inst="a", to_inst="target"))
        pending1 = await router.pending_for("target")
        pending2 = await router.pending_for("target")
        assert len(pending1) == len(pending2) == 1

    @pytest.mark.asyncio
    async def test_pending_for_empty(self):
        router = MessageRouter()
        pending = await router.pending_for("nobody")
        assert pending == []

    @pytest.mark.asyncio
    async def test_pending_for_only_inbound(self):
        """pending_for returns messages TO the instance, not FROM."""
        router = MessageRouter()
        router.create_channel("target", "other", capacity=10)
        await router.route(_system_envelope(from_inst="target", to_inst="other"))
        pending = await router.pending_for("target")
        assert pending == []


class TestMessageRouterBackpressure:
    """Test channel-full backpressure during routing."""

    @pytest.mark.asyncio
    async def test_route_raises_backpressure_when_channel_full(self):
        router = MessageRouter()
        router.create_channel("a", "b", capacity=1)
        await router.route(_delegation_envelope(from_inst="a", to_inst="b"))
        with pytest.raises(RoutingError, match="[Bb]ackpressure|[Ff]ull"):
            await router.route(_delegation_envelope(from_inst="a", to_inst="b"))

# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""
Unit tests for kaizen_agents._message_transport — SDK MessageRouter bridge.

Tier 1: Unit tests using real SDK MessageRouter (no mocking of SDK primitives).
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from kaizen.l3.messaging.dead_letters import DeadLetterReason, DeadLetterStore
from kaizen.l3.messaging.router import MessageRouter

from kaizen_agents._message_transport import MessageTransport
from kaizen_agents.types import (
    ClarificationPayload,
    CompletionPayload,
    DelegationPayload,
    EscalationPayload,
    EscalationSeverity,
    L3Message,
    L3MessageType,
    Priority,
    ResourceSnapshot,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def dead_letters() -> DeadLetterStore:
    return DeadLetterStore()


@pytest.fixture()
def router(dead_letters: DeadLetterStore) -> MessageRouter:
    return MessageRouter(dead_letters=dead_letters, lineage_fn=None)


@pytest.fixture()
def transport(router: MessageRouter) -> MessageTransport:
    return MessageTransport(router)


# ---------------------------------------------------------------------------
# 1. setup_channel creates bidirectional channels
# ---------------------------------------------------------------------------


class TestSetupChannel:
    """Verify that setup_channel creates channels in both directions."""

    def test_creates_bidirectional_channels(
        self, transport: MessageTransport, router: MessageRouter
    ) -> None:
        """setup_channel must create parent->child and child->parent channels."""
        transport.setup_channel("parent-1", "child-1", capacity=50)

        # Both direction keys should exist in the router's internal channel dict
        assert ("parent-1", "child-1") in router._channels
        assert ("child-1", "parent-1") in router._channels

    def test_channel_capacity_applied(
        self, transport: MessageTransport, router: MessageRouter
    ) -> None:
        """Channels must be created with the requested capacity."""
        transport.setup_channel("p", "c", capacity=42)

        ch_fwd = router._channels[("p", "c")]
        ch_rev = router._channels[("c", "p")]
        assert ch_fwd.capacity == 42
        assert ch_rev.capacity == 42

    def test_default_capacity(self, transport: MessageTransport, router: MessageRouter) -> None:
        """Default capacity should be 100 when not specified."""
        transport.setup_channel("p", "c")

        ch = router._channels[("p", "c")]
        assert ch.capacity == 100


# ---------------------------------------------------------------------------
# 2. send_delegation routes message via SDK router
# ---------------------------------------------------------------------------


class TestSendDelegation:
    """Verify delegation messages are routed through the SDK router."""

    @pytest.mark.asyncio()
    async def test_send_delegation_routes_message(
        self, transport: MessageTransport, router: MessageRouter
    ) -> None:
        transport.setup_channel("parent-1", "child-1")
        payload = DelegationPayload(
            task_description="Analyze data",
            context_snapshot={"key": "value"},
            priority=Priority.HIGH,
        )
        msg_id = await transport.send_delegation("parent-1", "child-1", payload, ttl_seconds=300.0)

        assert isinstance(msg_id, str)
        assert len(msg_id) > 0

        # Message should be pending for child-1
        pending = await router.pending_for("child-1")
        assert len(pending) == 1
        assert pending[0].from_instance == "parent-1"
        assert pending[0].to_instance == "child-1"

    @pytest.mark.asyncio()
    async def test_send_delegation_with_correlation_id(
        self, transport: MessageTransport, router: MessageRouter
    ) -> None:
        transport.setup_channel("parent-1", "child-1")
        payload = DelegationPayload(task_description="Do work")
        msg_id = await transport.send_delegation(
            "parent-1", "child-1", payload, correlation_id="corr-abc"
        )

        pending = await router.pending_for("child-1")
        assert len(pending) == 1
        assert pending[0].correlation_id == "corr-abc"


# ---------------------------------------------------------------------------
# 3. send_completion routes completion via SDK router
# ---------------------------------------------------------------------------


class TestSendCompletion:
    """Verify completion messages are routed through the SDK router."""

    @pytest.mark.asyncio()
    async def test_send_completion_routes_message(
        self, transport: MessageTransport, router: MessageRouter
    ) -> None:
        transport.setup_channel("child-1", "parent-1")
        payload = CompletionPayload(
            result={"output": "done"},
            success=True,
            resource_consumed=ResourceSnapshot(financial_spent=0.5),
        )
        # Completion requires correlation_id per SDK router validation
        msg_id = await transport.send_completion(
            "child-1", "parent-1", payload, correlation_id="corr-123"
        )

        assert isinstance(msg_id, str)

        pending = await router.pending_for("parent-1")
        assert len(pending) == 1
        assert pending[0].from_instance == "child-1"
        assert pending[0].correlation_id == "corr-123"


# ---------------------------------------------------------------------------
# 4. send_clarification routes clarification
# ---------------------------------------------------------------------------


class TestSendClarification:
    """Verify clarification messages are routed through the SDK router."""

    @pytest.mark.asyncio()
    async def test_send_clarification_routes_message(
        self, transport: MessageTransport, router: MessageRouter
    ) -> None:
        transport.setup_channel("child-1", "parent-1")
        payload = ClarificationPayload(
            question="What format?",
            blocking=True,
            options=["JSON", "CSV"],
        )
        msg_id = await transport.send_clarification("child-1", "parent-1", payload)

        assert isinstance(msg_id, str)

        pending = await router.pending_for("parent-1")
        assert len(pending) == 1
        assert pending[0].from_instance == "child-1"

    @pytest.mark.asyncio()
    async def test_send_clarification_response_requires_correlation(
        self, transport: MessageTransport, router: MessageRouter
    ) -> None:
        """A clarification response (is_response=True) requires correlation_id per SDK rules."""
        transport.setup_channel("parent-1", "child-1")
        payload = ClarificationPayload(
            question="Use JSON",
            is_response=True,
        )
        # Should succeed with correlation_id
        msg_id = await transport.send_clarification(
            "parent-1", "child-1", payload, correlation_id="corr-q1"
        )
        assert isinstance(msg_id, str)


# ---------------------------------------------------------------------------
# 5. send_escalation routes escalation
# ---------------------------------------------------------------------------


class TestSendEscalation:
    """Verify escalation messages are routed through the SDK router."""

    @pytest.mark.asyncio()
    async def test_send_escalation_routes_message(
        self, transport: MessageTransport, router: MessageRouter
    ) -> None:
        transport.setup_channel("child-1", "parent-1")
        payload = EscalationPayload(
            severity=EscalationSeverity.BLOCKED,
            problem_description="Cannot access resource",
            attempted_mitigations=["retry", "fallback"],
            suggested_action="Grant access",
            violating_dimension="data_access",
        )
        msg_id = await transport.send_escalation("child-1", "parent-1", payload)

        assert isinstance(msg_id, str)

        pending = await router.pending_for("parent-1")
        assert len(pending) == 1
        assert pending[0].from_instance == "child-1"


# ---------------------------------------------------------------------------
# 6. receive_pending returns converted local L3Messages
# ---------------------------------------------------------------------------


class TestReceivePending:
    """Verify that pending SDK envelopes are converted to local L3Messages."""

    @pytest.mark.asyncio()
    async def test_receive_pending_converts_delegation(self, transport: MessageTransport) -> None:
        transport.setup_channel("parent-1", "child-1")
        payload = DelegationPayload(
            task_description="Analyze data",
            priority=Priority.HIGH,
        )
        await transport.send_delegation("parent-1", "child-1", payload)

        messages = await transport.receive_pending("child-1")
        assert len(messages) == 1
        msg = messages[0]
        assert isinstance(msg, L3Message)
        assert msg.message_type == L3MessageType.DELEGATION
        assert msg.from_instance == "parent-1"
        assert msg.to_instance == "child-1"
        assert msg.delegation is not None
        assert msg.delegation.task_description == "Analyze data"
        assert msg.delegation.priority == Priority.HIGH

    @pytest.mark.asyncio()
    async def test_receive_pending_converts_completion(self, transport: MessageTransport) -> None:
        transport.setup_channel("child-1", "parent-1")
        payload = CompletionPayload(
            result={"answer": 42},
            success=True,
            resource_consumed=ResourceSnapshot(financial_spent=1.5, actions_executed=3),
        )
        await transport.send_completion("child-1", "parent-1", payload, correlation_id="corr-x")

        messages = await transport.receive_pending("parent-1")
        assert len(messages) == 1
        msg = messages[0]
        assert msg.message_type == L3MessageType.COMPLETION
        assert msg.completion is not None
        assert msg.completion.result == {"answer": 42}
        assert msg.completion.success is True
        assert msg.completion.resource_consumed.financial_spent == 1.5
        assert msg.completion.resource_consumed.actions_executed == 3
        assert msg.correlation_id == "corr-x"

    @pytest.mark.asyncio()
    async def test_receive_pending_converts_clarification(
        self, transport: MessageTransport
    ) -> None:
        transport.setup_channel("child-1", "parent-1")
        payload = ClarificationPayload(
            question="Which format?",
            blocking=True,
            options=["A", "B"],
        )
        await transport.send_clarification("child-1", "parent-1", payload)

        messages = await transport.receive_pending("parent-1")
        assert len(messages) == 1
        msg = messages[0]
        assert msg.message_type == L3MessageType.CLARIFICATION
        assert msg.clarification is not None
        assert msg.clarification.question == "Which format?"
        assert msg.clarification.blocking is True
        assert msg.clarification.options == ["A", "B"]

    @pytest.mark.asyncio()
    async def test_receive_pending_converts_escalation(self, transport: MessageTransport) -> None:
        transport.setup_channel("child-1", "parent-1")
        payload = EscalationPayload(
            severity=EscalationSeverity.CRITICAL,
            problem_description="Out of budget",
            violating_dimension="financial",
        )
        await transport.send_escalation("child-1", "parent-1", payload)

        messages = await transport.receive_pending("parent-1")
        assert len(messages) == 1
        msg = messages[0]
        assert msg.message_type == L3MessageType.ESCALATION
        assert msg.escalation is not None
        assert msg.escalation.severity == EscalationSeverity.CRITICAL
        assert msg.escalation.problem_description == "Out of budget"
        assert msg.escalation.violating_dimension == "financial"

    @pytest.mark.asyncio()
    async def test_receive_pending_empty(self, transport: MessageTransport) -> None:
        """No pending messages returns empty list."""
        transport.setup_channel("parent-1", "child-1")
        messages = await transport.receive_pending("child-1")
        assert messages == []

    @pytest.mark.asyncio()
    async def test_receive_pending_multiple_messages(self, transport: MessageTransport) -> None:
        """Multiple pending messages are all returned."""
        transport.setup_channel("parent-1", "child-1")
        for i in range(3):
            payload = DelegationPayload(task_description=f"Task {i}")
            await transport.send_delegation("parent-1", "child-1", payload)

        messages = await transport.receive_pending("child-1")
        assert len(messages) == 3
        descriptions = [m.delegation.task_description for m in messages]
        assert "Task 0" in descriptions
        assert "Task 1" in descriptions
        assert "Task 2" in descriptions


# ---------------------------------------------------------------------------
# 7. teardown_channel closes channels
# ---------------------------------------------------------------------------


class TestTeardownChannel:
    """Verify teardown_channel closes all channels for an instance."""

    @pytest.mark.asyncio()
    async def test_teardown_closes_channels(
        self, transport: MessageTransport, router: MessageRouter
    ) -> None:
        transport.setup_channel("parent-1", "child-1")
        transport.teardown_channel("child-1")

        # Both directions should be closed
        ch_fwd = router._channels[("parent-1", "child-1")]
        ch_rev = router._channels[("child-1", "parent-1")]
        assert ch_fwd.is_closed()
        assert ch_rev.is_closed()

    @pytest.mark.asyncio()
    async def test_teardown_moves_pending_to_dead_letters(
        self,
        transport: MessageTransport,
        router: MessageRouter,
        dead_letters: DeadLetterStore,
    ) -> None:
        """Pending messages should be moved to dead letters on teardown."""
        transport.setup_channel("parent-1", "child-1")
        payload = DelegationPayload(task_description="Will be dead-lettered")
        await transport.send_delegation("parent-1", "child-1", payload)

        transport.teardown_channel("child-1")

        # The pending message should now be in dead letters
        assert dead_letters.count() >= 1
        recent = dead_letters.recent(10)
        assert any(entry[1] == DeadLetterReason.CHANNEL_CLOSED for entry in recent)


# ---------------------------------------------------------------------------
# 8. TTL enforcement: expired message goes to dead letters
# ---------------------------------------------------------------------------


class TestTTLEnforcement:
    """Verify that messages with expired TTL are rejected and dead-lettered."""

    @pytest.mark.asyncio()
    async def test_expired_ttl_raises_and_dead_letters(
        self,
        transport: MessageTransport,
        dead_letters: DeadLetterStore,
    ) -> None:
        """A message with TTL=0 (already expired) should be rejected."""
        transport.setup_channel("parent-1", "child-1")
        payload = DelegationPayload(task_description="Expired task")

        from kaizen.l3.messaging.errors import RoutingError

        with pytest.raises(RoutingError) as exc_info:
            await transport.send_delegation("parent-1", "child-1", payload, ttl_seconds=0.0)

        assert exc_info.value.variant == "Expired"
        assert dead_letters.count() == 1


# ---------------------------------------------------------------------------
# 9. Round-trip: send delegation -> receive -> verify payload integrity
# ---------------------------------------------------------------------------


class TestRoundTrip:
    """End-to-end round-trip verifying payload integrity through send/receive."""

    @pytest.mark.asyncio()
    async def test_delegation_round_trip(self, transport: MessageTransport) -> None:
        """Full round-trip: send delegation, receive as L3Message, verify all fields."""
        transport.setup_channel("orchestrator", "worker-1")

        original = DelegationPayload(
            task_description="Process customer data",
            context_snapshot={"customer_id": "C-100", "batch_size": 50},
            priority=Priority.CRITICAL,
        )
        sent_id = await transport.send_delegation(
            "orchestrator",
            "worker-1",
            original,
            correlation_id="session-42",
            ttl_seconds=600.0,
        )

        messages = await transport.receive_pending("worker-1")
        assert len(messages) == 1

        msg = messages[0]
        assert msg.message_id == sent_id
        assert msg.from_instance == "orchestrator"
        assert msg.to_instance == "worker-1"
        assert msg.message_type == L3MessageType.DELEGATION
        assert msg.correlation_id == "session-42"
        assert msg.delegation is not None
        assert msg.delegation.task_description == "Process customer data"
        assert msg.delegation.context_snapshot == {
            "customer_id": "C-100",
            "batch_size": 50,
        }
        assert msg.delegation.priority == Priority.CRITICAL

    @pytest.mark.asyncio()
    async def test_completion_round_trip(self, transport: MessageTransport) -> None:
        """Full round-trip for completion messages."""
        transport.setup_channel("worker-1", "orchestrator")

        original = CompletionPayload(
            result={"processed": 50, "errors": 0},
            success=True,
            context_updates={"last_batch": "C-100"},
            resource_consumed=ResourceSnapshot(
                financial_spent=2.5,
                actions_executed=50,
                elapsed_seconds=12.3,
                messages_sent=5,
            ),
            error_detail=None,
        )
        sent_id = await transport.send_completion(
            "worker-1",
            "orchestrator",
            original,
            correlation_id="session-42",
        )

        messages = await transport.receive_pending("orchestrator")
        assert len(messages) == 1

        msg = messages[0]
        assert msg.message_id == sent_id
        assert msg.message_type == L3MessageType.COMPLETION
        assert msg.completion is not None
        assert msg.completion.result == {"processed": 50, "errors": 0}
        assert msg.completion.success is True
        assert msg.completion.context_updates == {"last_batch": "C-100"}
        assert msg.completion.resource_consumed.financial_spent == 2.5
        assert msg.completion.resource_consumed.actions_executed == 50
        assert msg.completion.resource_consumed.elapsed_seconds == 12.3
        assert msg.completion.resource_consumed.messages_sent == 5
        assert msg.completion.error_detail is None

    @pytest.mark.asyncio()
    async def test_escalation_round_trip(self, transport: MessageTransport) -> None:
        """Full round-trip for escalation messages."""
        transport.setup_channel("worker-1", "orchestrator")

        original = EscalationPayload(
            severity=EscalationSeverity.BUDGET_ALERT,
            problem_description="Approaching budget limit",
            attempted_mitigations=["reduced batch size", "skipped optional tasks"],
            suggested_action="Increase budget or terminate",
            violating_dimension="financial",
        )
        sent_id = await transport.send_escalation(
            "worker-1", "orchestrator", original, correlation_id="esc-1"
        )

        messages = await transport.receive_pending("orchestrator")
        assert len(messages) == 1

        msg = messages[0]
        assert msg.message_id == sent_id
        assert msg.escalation is not None
        assert msg.escalation.severity == EscalationSeverity.BUDGET_ALERT
        assert msg.escalation.problem_description == "Approaching budget limit"
        assert msg.escalation.attempted_mitigations == [
            "reduced batch size",
            "skipped optional tasks",
        ]
        assert msg.escalation.suggested_action == "Increase budget or terminate"
        assert msg.escalation.violating_dimension == "financial"

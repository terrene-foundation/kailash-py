# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tests for M0-03: MessageType L3 variants (B4)."""

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


class TestMessageType:
    """Test MessageType enum with all 12 variants."""

    def test_l0_l2_variants(self):
        """6 existing L0-L2 variants."""
        assert MessageType.TASK_REQUEST.value == "task_request"
        assert MessageType.TASK_RESPONSE.value == "task_response"
        assert MessageType.STATUS_UPDATE.value == "status_update"
        assert MessageType.CAPABILITY_QUERY.value == "capability_query"
        assert MessageType.CAPABILITY_RESPONSE.value == "capability_response"
        assert MessageType.ERROR.value == "error"

    def test_l3_variants(self):
        """6 new L3 variants (per Brief 03, F-02 fix)."""
        assert MessageType.DELEGATION.value == "delegation"
        assert MessageType.STATUS.value == "status"
        assert MessageType.CLARIFICATION.value == "clarification"
        assert MessageType.COMPLETION.value == "completion"
        assert MessageType.ESCALATION.value == "escalation"
        assert MessageType.SYSTEM.value == "system"

    def test_total_variant_count(self):
        """AC-1: All 12 variants constructable."""
        assert len(MessageType) == 12

    def test_str_backed(self):
        """Enum values are strings (EATP convention)."""
        assert isinstance(MessageType.DELEGATION.value, str)
        assert MessageType.DELEGATION == "delegation"


class TestPriority:
    def test_ordering(self):
        assert Priority.LOW < Priority.NORMAL < Priority.HIGH < Priority.CRITICAL


class TestResourceSnapshot:
    def test_construction_and_serialization(self):
        snap = ResourceSnapshot(financial_spent=50.0, actions_executed=10)
        d = snap.to_dict()
        assert d["financial_spent"] == 50.0
        assert d["actions_executed"] == 10

    def test_from_dict(self):
        snap = ResourceSnapshot.from_dict({"financial_spent": 25.0, "messages_sent": 3})
        assert snap.financial_spent == 25.0
        assert snap.messages_sent == 3


class TestDelegationPayload:
    def test_construction(self):
        p = DelegationPayload(
            task_description="Review code",
            context_snapshot={"project": "kaizen"},
            priority=Priority.HIGH,
        )
        assert p.task_description == "Review code"
        assert p.priority == Priority.HIGH

    def test_to_dict(self):
        p = DelegationPayload(task_description="test")
        d = p.to_dict()
        assert d["type"] == "delegation"
        assert d["task_description"] == "test"
        assert d["priority"] == 1  # NORMAL


class TestStatusPayload:
    def test_construction(self):
        p = StatusPayload(phase="analyzing", progress_pct=0.5)
        d = p.to_dict()
        assert d["type"] == "status"
        assert d["phase"] == "analyzing"
        assert d["progress_pct"] == 0.5


class TestClarificationPayload:
    def test_question(self):
        p = ClarificationPayload(
            question="What format?", blocking=True, is_response=False
        )
        d = p.to_dict()
        assert d["type"] == "clarification"
        assert d["blocking"] is True
        assert d["is_response"] is False

    def test_response(self):
        p = ClarificationPayload(question="Use JSON", is_response=True, blocking=False)
        assert p.is_response is True


class TestCompletionPayload:
    def test_success(self):
        p = CompletionPayload(result={"status": "done"}, success=True)
        d = p.to_dict()
        assert d["type"] == "completion"
        assert d["success"] is True

    def test_failure(self):
        p = CompletionPayload(success=False, error_detail="timeout")
        assert p.error_detail == "timeout"


class TestEscalationPayload:
    def test_construction(self):
        p = EscalationPayload(
            severity=EscalationSeverity.BUDGET_ALERT,
            problem_description="Budget at 90%",
        )
        d = p.to_dict()
        assert d["type"] == "escalation"
        assert d["severity"] == "budget_alert"


class TestSystemPayload:
    def test_termination_notice(self):
        p = SystemPayload(
            subtype=SystemSubtype.TERMINATION_NOTICE,
            reason="parent_terminated",
        )
        d = p.to_dict()
        assert d["type"] == "system"
        assert d["subtype"] == "termination_notice"

    def test_heartbeat(self):
        p = SystemPayload(subtype=SystemSubtype.HEARTBEAT_REQUEST)
        assert p.subtype == SystemSubtype.HEARTBEAT_REQUEST


class TestMessageEnvelope:
    def test_construction_with_delegation(self):
        payload = DelegationPayload(task_description="review")
        env = MessageEnvelope(
            from_instance="parent-001",
            to_instance="child-001",
            payload=payload,
        )
        assert env.message_id  # UUID generated
        assert env.from_instance == "parent-001"
        assert env.message_type == MessageType.DELEGATION

    def test_message_type_inference(self):
        """message_type property infers from payload."""
        assert (
            MessageEnvelope(
                payload=DelegationPayload(task_description="x")
            ).message_type
            == MessageType.DELEGATION
        )
        assert (
            MessageEnvelope(payload=StatusPayload(phase="x")).message_type
            == MessageType.STATUS
        )
        assert (
            MessageEnvelope(payload=ClarificationPayload(question="x")).message_type
            == MessageType.CLARIFICATION
        )
        assert (
            MessageEnvelope(payload=CompletionPayload()).message_type
            == MessageType.COMPLETION
        )
        assert (
            MessageEnvelope(
                payload=EscalationPayload(
                    severity=EscalationSeverity.WARNING, problem_description="x"
                )
            ).message_type
            == MessageType.ESCALATION
        )
        assert (
            MessageEnvelope(
                payload=SystemPayload(subtype=SystemSubtype.HEARTBEAT_REQUEST)
            ).message_type
            == MessageType.SYSTEM
        )

    def test_metadata_field(self):
        """P6: metadata field on message envelope."""
        env = MessageEnvelope(metadata={"trace_id": "abc-123"})
        assert env.metadata["trace_id"] == "abc-123"

    def test_to_dict(self):
        env = MessageEnvelope(
            from_instance="a",
            to_instance="b",
            payload=DelegationPayload(task_description="test"),
            ttl_seconds=60.0,
        )
        d = env.to_dict()
        assert d["from_instance"] == "a"
        assert d["to_instance"] == "b"
        assert d["ttl_seconds"] == 60.0
        assert d["payload"]["type"] == "delegation"

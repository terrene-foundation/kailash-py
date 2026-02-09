"""Unit tests for RuntimeAuditGenerator (CARE-018).

Tests for RuntimeAuditGenerator class and its methods.
These are Tier 1 unit tests - fast, isolated, no external dependencies.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest
from kailash.runtime.trust.context import RuntimeTrustContext, TrustVerificationMode


class TestRuntimeAuditGeneratorInitialization:
    """Test RuntimeAuditGenerator initialization."""

    def test_generator_initialization_defaults(self):
        """Test constructor params stored with defaults."""
        from kailash.runtime.trust.audit import RuntimeAuditGenerator

        generator = RuntimeAuditGenerator()

        assert generator._audit_store is None
        assert generator._enabled is True
        assert generator._log_to_stdout is False
        assert generator._events == []

    def test_generator_initialization_custom_values(self):
        """Test constructor with custom values."""
        from kailash.runtime.trust.audit import RuntimeAuditGenerator

        mock_store = MagicMock()
        generator = RuntimeAuditGenerator(
            audit_store=mock_store,
            enabled=False,
            log_to_stdout=True,
        )

        assert generator._audit_store is mock_store
        assert generator._enabled is False
        assert generator._log_to_stdout is True


class TestRuntimeAuditGeneratorDisabled:
    """Test RuntimeAuditGenerator when disabled."""

    @pytest.mark.asyncio
    async def test_generator_disabled_no_events(self):
        """Test no events recorded when disabled."""
        from kailash.runtime.trust.audit import RuntimeAuditGenerator

        generator = RuntimeAuditGenerator(enabled=False)

        trust_ctx = RuntimeTrustContext(trace_id="disabled-trace")

        await generator.workflow_started(
            run_id="run-1",
            workflow_name="test-wf",
            trust_context=trust_ctx,
        )

        events = generator.get_events()
        assert len(events) == 0


class TestRuntimeAuditGeneratorEnabled:
    """Test RuntimeAuditGenerator when enabled."""

    @pytest.mark.asyncio
    async def test_generator_enabled_records_events(self):
        """Test events recorded when enabled."""
        from kailash.runtime.trust.audit import RuntimeAuditGenerator

        generator = RuntimeAuditGenerator(enabled=True)

        trust_ctx = RuntimeTrustContext(trace_id="enabled-trace")

        await generator.workflow_started(
            run_id="run-1",
            workflow_name="test-wf",
            trust_context=trust_ctx,
        )

        events = generator.get_events()
        assert len(events) == 1


class TestWorkflowStartedEvent:
    """Test workflow_started method."""

    @pytest.mark.asyncio
    async def test_workflow_started_event_type(self):
        """Test correct event type for workflow started."""
        from kailash.runtime.trust.audit import AuditEventType, RuntimeAuditGenerator

        generator = RuntimeAuditGenerator()
        trust_ctx = RuntimeTrustContext(trace_id="wf-start-trace")

        event = await generator.workflow_started(
            run_id="run-1",
            workflow_name="my-workflow",
            trust_context=trust_ctx,
        )

        assert event.event_type == AuditEventType.WORKFLOW_START

    @pytest.mark.asyncio
    async def test_workflow_started_event_fields(self):
        """Test correct fields set for workflow started."""
        from kailash.runtime.trust.audit import RuntimeAuditGenerator

        generator = RuntimeAuditGenerator()
        trust_ctx = RuntimeTrustContext(trace_id="wf-fields-trace")

        event = await generator.workflow_started(
            run_id="run-123",
            workflow_name="test-workflow",
            trust_context=trust_ctx,
        )

        assert event.trace_id == "wf-fields-trace"
        assert event.workflow_id == "run-123"
        assert event.action == "workflow_started"
        assert event.result == "success"
        assert "workflow_name" in event.context
        assert event.context["workflow_name"] == "test-workflow"


class TestWorkflowCompletedEvent:
    """Test workflow_completed method."""

    @pytest.mark.asyncio
    async def test_workflow_completed_event_type(self):
        """Test correct event type for workflow completed."""
        from kailash.runtime.trust.audit import AuditEventType, RuntimeAuditGenerator

        generator = RuntimeAuditGenerator()
        trust_ctx = RuntimeTrustContext(trace_id="wf-complete-trace")

        event = await generator.workflow_completed(
            run_id="run-1",
            duration_ms=1500,
            trust_context=trust_ctx,
        )

        assert event.event_type == AuditEventType.WORKFLOW_END

    @pytest.mark.asyncio
    async def test_workflow_completed_success_result(self):
        """Test success result for completed workflow."""
        from kailash.runtime.trust.audit import RuntimeAuditGenerator

        generator = RuntimeAuditGenerator()
        trust_ctx = RuntimeTrustContext(trace_id="wf-success-trace")

        event = await generator.workflow_completed(
            run_id="run-1",
            duration_ms=1000,
            trust_context=trust_ctx,
        )

        assert event.result == "success"

    @pytest.mark.asyncio
    async def test_workflow_completed_duration_in_context(self):
        """Test duration is included in context."""
        from kailash.runtime.trust.audit import RuntimeAuditGenerator

        generator = RuntimeAuditGenerator()
        trust_ctx = RuntimeTrustContext(trace_id="wf-duration-trace")

        event = await generator.workflow_completed(
            run_id="run-1",
            duration_ms=2500,
            trust_context=trust_ctx,
        )

        assert "duration_ms" in event.context
        assert event.context["duration_ms"] == 2500


class TestWorkflowFailedEvent:
    """Test workflow_failed method."""

    @pytest.mark.asyncio
    async def test_workflow_failed_event_type(self):
        """Test correct event type for workflow failed."""
        from kailash.runtime.trust.audit import AuditEventType, RuntimeAuditGenerator

        generator = RuntimeAuditGenerator()
        trust_ctx = RuntimeTrustContext(trace_id="wf-fail-trace")

        event = await generator.workflow_failed(
            run_id="run-1",
            error="Something went wrong",
            duration_ms=500,
            trust_context=trust_ctx,
        )

        assert event.event_type == AuditEventType.WORKFLOW_ERROR

    @pytest.mark.asyncio
    async def test_workflow_failed_failure_result(self):
        """Test failure result for failed workflow."""
        from kailash.runtime.trust.audit import RuntimeAuditGenerator

        generator = RuntimeAuditGenerator()
        trust_ctx = RuntimeTrustContext(trace_id="wf-failure-trace")

        event = await generator.workflow_failed(
            run_id="run-1",
            error="Test error",
            duration_ms=100,
            trust_context=trust_ctx,
        )

        assert event.result == "failure"

    @pytest.mark.asyncio
    async def test_workflow_failed_error_in_context(self):
        """Test error is included in context."""
        from kailash.runtime.trust.audit import RuntimeAuditGenerator

        generator = RuntimeAuditGenerator()
        trust_ctx = RuntimeTrustContext(trace_id="wf-error-trace")

        event = await generator.workflow_failed(
            run_id="run-1",
            error="Database connection failed",
            duration_ms=200,
            trust_context=trust_ctx,
        )

        assert "error" in event.context
        assert event.context["error"] == "Database connection failed"
        assert "duration_ms" in event.context
        assert event.context["duration_ms"] == 200


class TestNodeExecutedEvent:
    """Test node_executed method."""

    @pytest.mark.asyncio
    async def test_node_executed_event_type(self):
        """Test correct node event type."""
        from kailash.runtime.trust.audit import AuditEventType, RuntimeAuditGenerator

        generator = RuntimeAuditGenerator()
        trust_ctx = RuntimeTrustContext(trace_id="node-exec-trace")

        event = await generator.node_executed(
            run_id="run-1",
            node_id="node-1",
            node_type="HttpRequest",
            duration_ms=150,
            trust_context=trust_ctx,
        )

        assert event.event_type == AuditEventType.NODE_END

    @pytest.mark.asyncio
    async def test_node_executed_fields(self):
        """Test correct fields for node executed."""
        from kailash.runtime.trust.audit import RuntimeAuditGenerator

        generator = RuntimeAuditGenerator()
        trust_ctx = RuntimeTrustContext(trace_id="node-fields-trace")

        event = await generator.node_executed(
            run_id="run-1",
            node_id="my-node",
            node_type="BashCommand",
            duration_ms=300,
            trust_context=trust_ctx,
        )

        assert event.node_id == "my-node"
        assert event.result == "success"
        assert "node_type" in event.context
        assert event.context["node_type"] == "BashCommand"
        assert "duration_ms" in event.context
        assert event.context["duration_ms"] == 300


class TestNodeFailedEvent:
    """Test node_failed method."""

    @pytest.mark.asyncio
    async def test_node_failed_event_type(self):
        """Test node failure event type."""
        from kailash.runtime.trust.audit import AuditEventType, RuntimeAuditGenerator

        generator = RuntimeAuditGenerator()
        trust_ctx = RuntimeTrustContext(trace_id="node-fail-trace")

        event = await generator.node_failed(
            run_id="run-1",
            node_id="node-1",
            node_type="HttpRequest",
            error="Connection timeout",
            duration_ms=5000,
            trust_context=trust_ctx,
        )

        assert event.event_type == AuditEventType.NODE_ERROR

    @pytest.mark.asyncio
    async def test_node_failed_fields(self):
        """Test correct fields for node failed."""
        from kailash.runtime.trust.audit import RuntimeAuditGenerator

        generator = RuntimeAuditGenerator()
        trust_ctx = RuntimeTrustContext(trace_id="node-error-trace")

        event = await generator.node_failed(
            run_id="run-1",
            node_id="error-node",
            node_type="DatabaseQuery",
            error="Query failed",
            duration_ms=1000,
            trust_context=trust_ctx,
        )

        assert event.node_id == "error-node"
        assert event.result == "failure"
        assert "error" in event.context
        assert event.context["error"] == "Query failed"
        assert "node_type" in event.context
        assert event.context["node_type"] == "DatabaseQuery"


class TestTrustVerificationEvent:
    """Test trust_verification_performed method."""

    @pytest.mark.asyncio
    async def test_trust_verification_allowed_event(self):
        """Test verification recorded when allowed."""
        from kailash.runtime.trust.audit import AuditEventType, RuntimeAuditGenerator

        generator = RuntimeAuditGenerator()
        trust_ctx = RuntimeTrustContext(trace_id="verify-allow-trace")

        event = await generator.trust_verification_performed(
            run_id="run-1",
            target="workflow:my-wf",
            allowed=True,
            reason="Access granted",
            trust_context=trust_ctx,
        )

        assert event.event_type == AuditEventType.TRUST_VERIFICATION
        assert event.result == "success"

    @pytest.mark.asyncio
    async def test_trust_denied_event(self):
        """Test denial recorded with TRUST_DENIED type."""
        from kailash.runtime.trust.audit import AuditEventType, RuntimeAuditGenerator

        generator = RuntimeAuditGenerator()
        trust_ctx = RuntimeTrustContext(trace_id="verify-deny-trace")

        event = await generator.trust_verification_performed(
            run_id="run-1",
            target="node:BashCommand:node-1",
            allowed=False,
            reason="Insufficient permissions",
            trust_context=trust_ctx,
        )

        assert event.event_type == AuditEventType.TRUST_DENIED
        assert event.result == "denied"
        assert "reason" in event.context
        assert event.context["reason"] == "Insufficient permissions"


class TestResourceAccessedEvent:
    """Test resource_accessed method."""

    @pytest.mark.asyncio
    async def test_resource_accessed_event(self):
        """Test resource access recorded."""
        from kailash.runtime.trust.audit import AuditEventType, RuntimeAuditGenerator

        generator = RuntimeAuditGenerator()
        trust_ctx = RuntimeTrustContext(trace_id="resource-trace")

        event = await generator.resource_accessed(
            run_id="run-1",
            resource="/data/sensitive-file.txt",
            action="read",
            result="success",
            trust_context=trust_ctx,
        )

        assert event.event_type == AuditEventType.RESOURCE_ACCESS
        assert event.resource == "/data/sensitive-file.txt"
        assert event.action == "read"
        assert event.result == "success"


class TestGetEvents:
    """Test get_events methods."""

    @pytest.mark.asyncio
    async def test_get_events_returns_all(self):
        """Test get_events returns all events."""
        from kailash.runtime.trust.audit import RuntimeAuditGenerator

        generator = RuntimeAuditGenerator()
        trust_ctx = RuntimeTrustContext(trace_id="all-events-trace")

        await generator.workflow_started("run-1", "wf-1", trust_ctx)
        await generator.node_executed("run-1", "node-1", "Test", 100, trust_ctx)
        await generator.workflow_completed("run-1", 500, trust_ctx)

        events = generator.get_events()
        assert len(events) == 3

    @pytest.mark.asyncio
    async def test_get_events_by_type(self):
        """Test get_events_by_type filters by event type."""
        from kailash.runtime.trust.audit import AuditEventType, RuntimeAuditGenerator

        generator = RuntimeAuditGenerator()
        trust_ctx = RuntimeTrustContext(trace_id="by-type-trace")

        await generator.workflow_started("run-1", "wf-1", trust_ctx)
        await generator.node_executed("run-1", "node-1", "Test", 100, trust_ctx)
        await generator.node_executed("run-1", "node-2", "Test", 150, trust_ctx)
        await generator.workflow_completed("run-1", 500, trust_ctx)

        node_events = generator.get_events_by_type(AuditEventType.NODE_END)
        assert len(node_events) == 2

        wf_start_events = generator.get_events_by_type(AuditEventType.WORKFLOW_START)
        assert len(wf_start_events) == 1

    @pytest.mark.asyncio
    async def test_get_events_by_trace(self):
        """Test get_events_by_trace filters by trace_id."""
        from kailash.runtime.trust.audit import RuntimeAuditGenerator

        generator = RuntimeAuditGenerator()

        ctx1 = RuntimeTrustContext(trace_id="trace-alpha")
        ctx2 = RuntimeTrustContext(trace_id="trace-beta")

        await generator.workflow_started("run-1", "wf-1", ctx1)
        await generator.workflow_started("run-2", "wf-2", ctx2)
        await generator.workflow_completed("run-1", 500, ctx1)
        await generator.workflow_completed("run-2", 600, ctx2)

        alpha_events = generator.get_events_by_trace("trace-alpha")
        assert len(alpha_events) == 2
        for event in alpha_events:
            assert event.trace_id == "trace-alpha"

        beta_events = generator.get_events_by_trace("trace-beta")
        assert len(beta_events) == 2


class TestClearEvents:
    """Test clear_events method."""

    @pytest.mark.asyncio
    async def test_clear_events_empties_list(self):
        """Test clear_events empties event list."""
        from kailash.runtime.trust.audit import RuntimeAuditGenerator

        generator = RuntimeAuditGenerator()
        trust_ctx = RuntimeTrustContext(trace_id="clear-trace")

        await generator.workflow_started("run-1", "wf-1", trust_ctx)
        await generator.workflow_completed("run-1", 500, trust_ctx)

        assert len(generator.get_events()) == 2

        generator.clear_events()

        assert len(generator.get_events()) == 0


class TestEventOrdering:
    """Test event ordering."""

    @pytest.mark.asyncio
    async def test_event_ordering_chronological(self):
        """Test events are in chronological order."""
        from kailash.runtime.trust.audit import RuntimeAuditGenerator

        generator = RuntimeAuditGenerator()
        trust_ctx = RuntimeTrustContext(trace_id="order-trace")

        await generator.workflow_started("run-1", "wf-1", trust_ctx)
        await generator.node_executed("run-1", "node-1", "Test", 100, trust_ctx)
        await generator.node_executed("run-1", "node-2", "Test", 200, trust_ctx)
        await generator.workflow_completed("run-1", 500, trust_ctx)

        events = generator.get_events()

        # Verify chronological order by comparing timestamps
        for i in range(len(events) - 1):
            assert events[i].timestamp <= events[i + 1].timestamp


class TestContextExtraction:
    """Test extraction of trust context fields."""

    @pytest.mark.asyncio
    async def test_trace_id_from_context(self):
        """Test trace_id extracted from trust_context."""
        from kailash.runtime.trust.audit import RuntimeAuditGenerator

        generator = RuntimeAuditGenerator()
        trust_ctx = RuntimeTrustContext(trace_id="extracted-trace-id")

        event = await generator.workflow_started("run-1", "wf-1", trust_ctx)

        assert event.trace_id == "extracted-trace-id"

    @pytest.mark.asyncio
    async def test_agent_id_from_delegation_chain(self):
        """Test agent_id from last item in delegation_chain."""
        from kailash.runtime.trust.audit import RuntimeAuditGenerator

        generator = RuntimeAuditGenerator()
        trust_ctx = RuntimeTrustContext(
            trace_id="agent-trace",
            delegation_chain=["agent-1", "agent-2", "agent-3"],
        )

        event = await generator.workflow_started("run-1", "wf-1", trust_ctx)

        # Last agent in chain should be extracted
        assert event.agent_id == "agent-3"

    @pytest.mark.asyncio
    async def test_human_origin_id_extracted(self):
        """Test human_origin_id extracted from trust_context."""
        from kailash.runtime.trust.audit import RuntimeAuditGenerator

        generator = RuntimeAuditGenerator()

        # Create mock human_origin with id attribute
        mock_human_origin = MagicMock()
        mock_human_origin.id = "human-user-123"

        trust_ctx = RuntimeTrustContext(
            trace_id="human-trace",
            human_origin=mock_human_origin,
        )

        event = await generator.workflow_started("run-1", "wf-1", trust_ctx)

        assert event.human_origin_id == "human-user-123"

    @pytest.mark.asyncio
    async def test_human_origin_dict_with_id(self):
        """Test human_origin_id extracted from dict with 'id' key."""
        from kailash.runtime.trust.audit import RuntimeAuditGenerator

        generator = RuntimeAuditGenerator()

        trust_ctx = RuntimeTrustContext(
            trace_id="human-dict-trace",
            human_origin={"id": "dict-human-id", "type": "interactive"},
        )

        event = await generator.workflow_started("run-1", "wf-1", trust_ctx)

        assert event.human_origin_id == "dict-human-id"

    @pytest.mark.asyncio
    async def test_empty_delegation_chain(self):
        """Test agent_id is None when delegation_chain is empty."""
        from kailash.runtime.trust.audit import RuntimeAuditGenerator

        generator = RuntimeAuditGenerator()
        trust_ctx = RuntimeTrustContext(
            trace_id="empty-chain-trace",
            delegation_chain=[],
        )

        event = await generator.workflow_started("run-1", "wf-1", trust_ctx)

        assert event.agent_id is None

    @pytest.mark.asyncio
    async def test_none_human_origin(self):
        """Test human_origin_id is None when human_origin is None."""
        from kailash.runtime.trust.audit import RuntimeAuditGenerator

        generator = RuntimeAuditGenerator()
        trust_ctx = RuntimeTrustContext(
            trace_id="no-human-trace",
            human_origin=None,
        )

        event = await generator.workflow_started("run-1", "wf-1", trust_ctx)

        assert event.human_origin_id is None

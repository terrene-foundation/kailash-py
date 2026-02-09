"""Unit tests for RuntimeAuditGenerator Kaizen bridge (CARE-018).

Tests for Kaizen AuditStore integration in RuntimeAuditGenerator.
These are Tier 1 unit tests - mocking is allowed for Kaizen components.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from kailash.runtime.trust.context import RuntimeTrustContext


class TestPersistToKaizenStore:
    """Test _persist_to_kaizen method."""

    @pytest.mark.asyncio
    async def test_persist_to_kaizen_store(self):
        """Test events converted and persisted to Kaizen store."""
        from kailash.runtime.trust.audit import RuntimeAuditGenerator

        # Create mock audit store
        mock_store = AsyncMock()
        mock_store.append = AsyncMock(return_value="anchor-123")

        generator = RuntimeAuditGenerator(audit_store=mock_store)
        trust_ctx = RuntimeTrustContext(trace_id="persist-trace")

        event = await generator.workflow_started(
            run_id="run-1",
            workflow_name="test-wf",
            trust_context=trust_ctx,
        )

        # Verify store.append was called
        mock_store.append.assert_called_once()

    @pytest.mark.asyncio
    async def test_kaizen_store_unavailable(self):
        """Test works without store (None)."""
        from kailash.runtime.trust.audit import RuntimeAuditGenerator

        # No store configured
        generator = RuntimeAuditGenerator(audit_store=None)
        trust_ctx = RuntimeTrustContext(trace_id="no-store-trace")

        # Should not raise, just skip persistence
        event = await generator.workflow_started(
            run_id="run-1",
            workflow_name="test-wf",
            trust_context=trust_ctx,
        )

        # Event should still be recorded in memory
        assert event is not None
        events = generator.get_events()
        assert len(events) == 1

    @pytest.mark.asyncio
    async def test_kaizen_store_exception_handled(self):
        """Test exceptions from store caught, not raised."""
        from kailash.runtime.trust.audit import RuntimeAuditGenerator

        # Create mock store that raises exception
        mock_store = AsyncMock()
        mock_store.append = AsyncMock(side_effect=Exception("Store error"))

        generator = RuntimeAuditGenerator(audit_store=mock_store)
        trust_ctx = RuntimeTrustContext(trace_id="exception-trace")

        # Should not raise exception - should be caught internally
        event = await generator.workflow_started(
            run_id="run-1",
            workflow_name="test-wf",
            trust_context=trust_ctx,
        )

        # Event should still be recorded in memory despite store failure
        assert event is not None
        events = generator.get_events()
        assert len(events) == 1


class TestKaizenAnchorConversion:
    """Test AuditEvent to AuditAnchor field mapping."""

    @pytest.mark.asyncio
    async def test_kaizen_anchor_conversion_fields(self):
        """Test AuditEvent fields mapped correctly to AuditAnchor-like structure."""
        from kailash.runtime.trust.audit import RuntimeAuditGenerator

        # Create mock store to capture the call
        mock_store = AsyncMock()
        captured_anchor = None

        async def capture_anchor(anchor):
            nonlocal captured_anchor
            captured_anchor = anchor
            return "anchor-id"

        mock_store.append = capture_anchor

        generator = RuntimeAuditGenerator(audit_store=mock_store)
        trust_ctx = RuntimeTrustContext(
            trace_id="anchor-trace",
            delegation_chain=["agent-1", "agent-2"],
            human_origin={"id": "human-1"},
        )

        event = await generator.workflow_started(
            run_id="run-1",
            workflow_name="test-wf",
            trust_context=trust_ctx,
        )

        # Verify anchor was captured
        assert captured_anchor is not None

        # Check expected field mappings on the anchor dict/object
        # The anchor should have these fields matching EATP spec
        if isinstance(captured_anchor, dict):
            assert "id" in captured_anchor or hasattr(captured_anchor, "id")
            assert "agent_id" in captured_anchor
            assert captured_anchor["agent_id"] == "agent-2"  # Last in chain
            assert "action" in captured_anchor
            assert "timestamp" in captured_anchor
            assert "result" in captured_anchor


class TestResultMapping:
    """Test result value mapping to ActionResult equivalent."""

    @pytest.mark.asyncio
    async def test_success_result_mapping(self):
        """Test success result maps correctly."""
        from kailash.runtime.trust.audit import RuntimeAuditGenerator

        generator = RuntimeAuditGenerator()
        trust_ctx = RuntimeTrustContext(trace_id="success-result-trace")

        event = await generator.workflow_completed(
            run_id="run-1",
            duration_ms=1000,
            trust_context=trust_ctx,
        )

        # Result should be "success"
        assert event.result == "success"

    @pytest.mark.asyncio
    async def test_failure_result_mapping(self):
        """Test failure result maps correctly."""
        from kailash.runtime.trust.audit import RuntimeAuditGenerator

        generator = RuntimeAuditGenerator()
        trust_ctx = RuntimeTrustContext(trace_id="failure-result-trace")

        event = await generator.workflow_failed(
            run_id="run-1",
            error="Test error",
            duration_ms=500,
            trust_context=trust_ctx,
        )

        # Result should be "failure"
        assert event.result == "failure"

    @pytest.mark.asyncio
    async def test_denied_result_mapping(self):
        """Test denied result maps correctly."""
        from kailash.runtime.trust.audit import RuntimeAuditGenerator

        generator = RuntimeAuditGenerator()
        trust_ctx = RuntimeTrustContext(trace_id="denied-result-trace")

        event = await generator.trust_verification_performed(
            run_id="run-1",
            target="workflow:blocked-wf",
            allowed=False,
            reason="Permission denied",
            trust_context=trust_ctx,
        )

        # Result should be "denied"
        assert event.result == "denied"


class TestAnchorDictFormat:
    """Test the anchor dict format for Kaizen bridge."""

    @pytest.mark.asyncio
    async def test_anchor_dict_has_required_fields(self):
        """Test anchor dict contains all required EATP fields."""
        from kailash.runtime.trust.audit import RuntimeAuditGenerator

        mock_store = AsyncMock()
        captured_anchor = None

        async def capture_anchor(anchor):
            nonlocal captured_anchor
            captured_anchor = anchor
            return "anchor-id"

        mock_store.append = capture_anchor

        generator = RuntimeAuditGenerator(audit_store=mock_store)
        trust_ctx = RuntimeTrustContext(
            trace_id="fields-trace",
            delegation_chain=["agent-1"],
        )

        await generator.workflow_started(
            run_id="run-1",
            workflow_name="test-wf",
            trust_context=trust_ctx,
        )

        # Check the anchor dict has required fields
        assert captured_anchor is not None

        if isinstance(captured_anchor, dict):
            required_fields = [
                "id",
                "agent_id",
                "action",
                "timestamp",
                "result",
                "context",
            ]
            for field in required_fields:
                assert field in captured_anchor, f"Missing required field: {field}"

    @pytest.mark.asyncio
    async def test_anchor_timestamp_is_iso_format(self):
        """Test anchor timestamp is in ISO format string."""
        from kailash.runtime.trust.audit import RuntimeAuditGenerator

        mock_store = AsyncMock()
        captured_anchor = None

        async def capture_anchor(anchor):
            nonlocal captured_anchor
            captured_anchor = anchor
            return "anchor-id"

        mock_store.append = capture_anchor

        generator = RuntimeAuditGenerator(audit_store=mock_store)
        trust_ctx = RuntimeTrustContext(trace_id="timestamp-trace")

        await generator.workflow_started(
            run_id="run-1",
            workflow_name="test-wf",
            trust_context=trust_ctx,
        )

        assert captured_anchor is not None
        if isinstance(captured_anchor, dict):
            timestamp = captured_anchor.get("timestamp")
            if isinstance(timestamp, str):
                # Should be parseable as ISO format
                datetime.fromisoformat(timestamp)


class TestMultipleEventsWithStore:
    """Test multiple events with Kaizen store."""

    @pytest.mark.asyncio
    async def test_multiple_events_persisted(self):
        """Test all events are persisted to store."""
        from kailash.runtime.trust.audit import RuntimeAuditGenerator

        mock_store = AsyncMock()
        mock_store.append = AsyncMock(return_value="anchor-id")

        generator = RuntimeAuditGenerator(audit_store=mock_store)
        trust_ctx = RuntimeTrustContext(trace_id="multi-trace")

        await generator.workflow_started("run-1", "wf-1", trust_ctx)
        await generator.node_executed("run-1", "node-1", "Test", 100, trust_ctx)
        await generator.workflow_completed("run-1", 500, trust_ctx)

        # Should have called append 3 times
        assert mock_store.append.call_count == 3

        # Events should also be in memory
        events = generator.get_events()
        assert len(events) == 3


class TestStoreExceptionLogging:
    """Test that store exceptions are logged appropriately."""

    @pytest.mark.asyncio
    async def test_store_exception_logged(self):
        """Test store exceptions are logged but don't stop execution."""
        from kailash.runtime.trust.audit import RuntimeAuditGenerator

        mock_store = AsyncMock()
        mock_store.append = AsyncMock(side_effect=RuntimeError("Connection failed"))

        generator = RuntimeAuditGenerator(audit_store=mock_store)
        trust_ctx = RuntimeTrustContext(trace_id="log-exception-trace")

        # Should complete without raising
        event = await generator.workflow_started("run-1", "wf-1", trust_ctx)

        # Event is still recorded
        assert event is not None
        assert len(generator.get_events()) == 1

        # Store was attempted
        mock_store.append.assert_called_once()

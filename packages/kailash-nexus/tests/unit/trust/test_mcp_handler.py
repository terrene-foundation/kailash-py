"""Unit tests for MCP + EATP Integration Handler.

TDD: These tests are written FIRST before the implementation.
Following the 3-tier testing strategy - Tier 1 (Unit Tests).

Tests cover:
1. test_prepare_mcp_call_valid - Valid call creates context with correct fields
2. test_prepare_mcp_call_generates_trace_id - Auto-generates trace_id if not provided
3. test_prepare_mcp_call_inherits_constraints - Constraints from trust_context inherited
4. test_prepare_mcp_call_no_trust_ops - Works without TrustOperations (standalone)
5. test_prepare_mcp_call_with_human_origin - Human origin propagated to context
6. test_verify_mcp_response_valid - Valid response returns True
7. test_verify_mcp_response_records_audit - Audit record created for call
8. test_verify_mcp_response_no_trust_ops - Works without TrustOperations
9. test_call_history_tracks_calls - Multiple calls tracked in history
10. test_call_history_empty_initially - Empty list before any calls
11. test_context_serialization - MCPEATPContext to_dict/from_dict round-trip
12. test_self_call_rejected - Agent calling itself should be rejected
"""

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock

import pytest

# Add src to path for imports
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root / "src"))

from nexus.trust.mcp_handler import MCPEATPContext, MCPEATPHandler

# =============================================================================
# Test Fixtures and Helpers
# =============================================================================


@pytest.fixture
def handler():
    """Create MCPEATPHandler instance without TrustOperations."""
    return MCPEATPHandler()


@pytest.fixture
def handler_with_trust_ops():
    """Create MCPEATPHandler instance with mock TrustOperations."""
    mock_trust_ops = MagicMock()
    mock_trust_ops.create_delegation = AsyncMock(
        return_value=MagicMock(delegation_id="delegation-123")
    )
    mock_trust_ops.audit = AsyncMock()
    return MCPEATPHandler(trust_operations=mock_trust_ops)


@pytest.fixture
def sample_trust_context():
    """Create sample trust context for testing."""
    return {
        "trace_id": "existing-trace-123",
        "constraints": {"max_tokens": 1000, "allowed_tools": ["read", "write"]},
        "human_origin": {"user_id": "user-789", "auth_method": "oauth2"},
    }


# =============================================================================
# Test MCPEATPContext Dataclass
# =============================================================================


class TestMCPEATPContext:
    """Test MCPEATPContext dataclass and serialization."""

    def test_context_creation_with_required_fields(self):
        """Test creating context with required fields."""
        context = MCPEATPContext(
            mcp_session_id="session-123",
            eatp_trace_id="trace-456",
            agent_id="agent-a",
            target_agent_id="agent-b",
        )

        assert context.mcp_session_id == "session-123"
        assert context.eatp_trace_id == "trace-456"
        assert context.agent_id == "agent-a"
        assert context.target_agent_id == "agent-b"
        assert context.human_origin is None
        assert context.delegated_capabilities == []
        assert context.constraints == {}
        assert context.delegation_id is None
        assert isinstance(context.created_at, datetime)

    def test_context_creation_with_all_fields(self):
        """Test creating context with all fields populated."""
        human_origin = {"user_id": "user-123"}
        constraints = {"max_depth": 5}
        created_time = datetime.now(timezone.utc)

        context = MCPEATPContext(
            mcp_session_id="session-123",
            eatp_trace_id="trace-456",
            agent_id="agent-a",
            target_agent_id="agent-b",
            human_origin=human_origin,
            delegated_capabilities=["read", "write"],
            constraints=constraints,
            delegation_id="delegation-789",
            created_at=created_time,
        )

        assert context.human_origin == human_origin
        assert context.delegated_capabilities == ["read", "write"]
        assert context.constraints == constraints
        assert context.delegation_id == "delegation-789"
        assert context.created_at == created_time

    def test_context_serialization_to_dict(self):
        """Test MCPEATPContext.to_dict() method."""
        context = MCPEATPContext(
            mcp_session_id="session-123",
            eatp_trace_id="trace-456",
            agent_id="agent-a",
            target_agent_id="agent-b",
            human_origin={"user_id": "user-123"},
            delegated_capabilities=["read"],
            constraints={"max_tokens": 100},
            delegation_id="delegation-789",
        )

        result = context.to_dict()

        assert isinstance(result, dict)
        assert result["mcp_session_id"] == "session-123"
        assert result["eatp_trace_id"] == "trace-456"
        assert result["agent_id"] == "agent-a"
        assert result["target_agent_id"] == "agent-b"
        assert result["human_origin"] == {"user_id": "user-123"}
        assert result["delegated_capabilities"] == ["read"]
        assert result["constraints"] == {"max_tokens": 100}
        assert result["delegation_id"] == "delegation-789"
        assert "created_at" in result

    def test_context_serialization_from_dict(self):
        """Test MCPEATPContext.from_dict() class method."""
        data = {
            "mcp_session_id": "session-123",
            "eatp_trace_id": "trace-456",
            "agent_id": "agent-a",
            "target_agent_id": "agent-b",
            "human_origin": {"user_id": "user-123"},
            "delegated_capabilities": ["read", "write"],
            "constraints": {"max_tokens": 100},
            "delegation_id": "delegation-789",
            "created_at": "2024-01-15T10:30:00+00:00",
        }

        context = MCPEATPContext.from_dict(data)

        assert context.mcp_session_id == "session-123"
        assert context.eatp_trace_id == "trace-456"
        assert context.agent_id == "agent-a"
        assert context.target_agent_id == "agent-b"
        assert context.human_origin == {"user_id": "user-123"}
        assert context.delegated_capabilities == ["read", "write"]
        assert context.constraints == {"max_tokens": 100}
        assert context.delegation_id == "delegation-789"

    def test_context_serialization_roundtrip(self):
        """Test MCPEATPContext to_dict/from_dict round-trip."""
        original = MCPEATPContext(
            mcp_session_id="session-roundtrip",
            eatp_trace_id="trace-roundtrip",
            agent_id="agent-original",
            target_agent_id="agent-target",
            human_origin={"verified": True},
            delegated_capabilities=["tool_a", "tool_b"],
            constraints={"limit": 50},
            delegation_id="delegation-roundtrip",
        )

        # Round-trip
        serialized = original.to_dict()
        restored = MCPEATPContext.from_dict(serialized)

        assert restored.mcp_session_id == original.mcp_session_id
        assert restored.eatp_trace_id == original.eatp_trace_id
        assert restored.agent_id == original.agent_id
        assert restored.target_agent_id == original.target_agent_id
        assert restored.human_origin == original.human_origin
        assert restored.delegated_capabilities == original.delegated_capabilities
        assert restored.constraints == original.constraints
        assert restored.delegation_id == original.delegation_id


# =============================================================================
# Test MCPEATPHandler - prepare_mcp_call
# =============================================================================


class TestMCPEATPHandlerPrepareMCPCall:
    """Test MCPEATPHandler.prepare_mcp_call() method."""

    @pytest.mark.asyncio
    async def test_prepare_mcp_call_valid(self, handler):
        """Test valid call creates context with correct fields."""
        context = await handler.prepare_mcp_call(
            calling_agent="agent-a",
            target_agent="agent-b",
            tool_name="search_documents",
            mcp_session_id="session-abc-123",
        )

        assert isinstance(context, MCPEATPContext)
        assert context.mcp_session_id == "session-abc-123"
        assert context.agent_id == "agent-a"
        assert context.target_agent_id == "agent-b"
        assert context.eatp_trace_id is not None
        assert len(context.eatp_trace_id) > 0
        assert isinstance(context.created_at, datetime)

    @pytest.mark.asyncio
    async def test_prepare_mcp_call_generates_trace_id(self, handler):
        """Test that trace_id is auto-generated if not provided."""
        context1 = await handler.prepare_mcp_call(
            calling_agent="agent-a",
            target_agent="agent-b",
            tool_name="tool1",
            mcp_session_id="session-1",
        )

        context2 = await handler.prepare_mcp_call(
            calling_agent="agent-a",
            target_agent="agent-b",
            tool_name="tool2",
            mcp_session_id="session-2",
        )

        # Each call should generate a unique trace_id
        assert context1.eatp_trace_id is not None
        assert context2.eatp_trace_id is not None
        assert context1.eatp_trace_id != context2.eatp_trace_id

    @pytest.mark.asyncio
    async def test_prepare_mcp_call_uses_provided_trace_id(
        self, handler, sample_trust_context
    ):
        """Test that provided trace_id from trust_context is used."""
        context = await handler.prepare_mcp_call(
            calling_agent="agent-a",
            target_agent="agent-b",
            tool_name="tool1",
            mcp_session_id="session-1",
            trust_context=sample_trust_context,
        )

        assert context.eatp_trace_id == "existing-trace-123"

    @pytest.mark.asyncio
    async def test_prepare_mcp_call_inherits_constraints(
        self, handler, sample_trust_context
    ):
        """Test constraints from trust_context are inherited."""
        context = await handler.prepare_mcp_call(
            calling_agent="agent-a",
            target_agent="agent-b",
            tool_name="tool1",
            mcp_session_id="session-1",
            trust_context=sample_trust_context,
        )

        assert context.constraints == sample_trust_context["constraints"]
        assert context.constraints["max_tokens"] == 1000
        assert context.constraints["allowed_tools"] == ["read", "write"]

    @pytest.mark.asyncio
    async def test_prepare_mcp_call_no_trust_ops(self, handler):
        """Test prepare_mcp_call works without TrustOperations (standalone)."""
        # handler fixture has no trust_operations
        context = await handler.prepare_mcp_call(
            calling_agent="agent-standalone",
            target_agent="agent-target",
            tool_name="standalone_tool",
            mcp_session_id="session-standalone",
        )

        assert context is not None
        assert context.agent_id == "agent-standalone"
        assert context.target_agent_id == "agent-target"
        # delegation_id should be None when no trust_ops
        assert context.delegation_id is None

    @pytest.mark.asyncio
    async def test_prepare_mcp_call_with_trust_ops_creates_delegation(
        self, handler_with_trust_ops
    ):
        """Test that TrustOperations.create_delegation is called when available."""
        context = await handler_with_trust_ops.prepare_mcp_call(
            calling_agent="agent-a",
            target_agent="agent-b",
            tool_name="secure_tool",
            mcp_session_id="session-secure",
        )

        # delegation_id should be set from trust_ops
        assert context.delegation_id == "delegation-123"

    @pytest.mark.asyncio
    async def test_prepare_mcp_call_with_human_origin(
        self, handler, sample_trust_context
    ):
        """Test human origin is propagated from trust_context to context."""
        context = await handler.prepare_mcp_call(
            calling_agent="agent-a",
            target_agent="agent-b",
            tool_name="tool1",
            mcp_session_id="session-1",
            trust_context=sample_trust_context,
        )

        assert context.human_origin is not None
        assert context.human_origin == sample_trust_context["human_origin"]
        assert context.human_origin["user_id"] == "user-789"
        assert context.human_origin["auth_method"] == "oauth2"

    @pytest.mark.asyncio
    async def test_prepare_mcp_call_self_call_rejected(self, handler):
        """Test that agent calling itself is rejected."""
        with pytest.raises(ValueError) as exc_info:
            await handler.prepare_mcp_call(
                calling_agent="agent-self",
                target_agent="agent-self",  # Same as calling agent
                tool_name="self_tool",
                mcp_session_id="session-self",
            )

        assert "cannot call itself" in str(exc_info.value).lower()


# =============================================================================
# Test MCPEATPHandler - verify_mcp_response
# =============================================================================


class TestMCPEATPHandlerVerifyMCPResponse:
    """Test MCPEATPHandler.verify_mcp_response() method."""

    @pytest.mark.asyncio
    async def test_verify_mcp_response_valid(self, handler):
        """Test valid response returns True."""
        context = MCPEATPContext(
            mcp_session_id="session-verify",
            eatp_trace_id="trace-verify",
            agent_id="agent-a",
            target_agent_id="agent-b",
        )

        response = {"result": "success", "data": {"value": 42}}

        result = await handler.verify_mcp_response(context, response)

        assert result is True

    @pytest.mark.asyncio
    async def test_verify_mcp_response_records_audit(self, handler_with_trust_ops):
        """Test audit record is created for the call."""
        # First, prepare a call to create context
        context = await handler_with_trust_ops.prepare_mcp_call(
            calling_agent="agent-a",
            target_agent="agent-b",
            tool_name="audited_tool",
            mcp_session_id="session-audit",
        )

        response = {"result": "success"}

        # Verify the response
        await handler_with_trust_ops.verify_mcp_response(context, response)

        # Check that audit was called
        handler_with_trust_ops._trust_operations.audit.assert_called()

    @pytest.mark.asyncio
    async def test_verify_mcp_response_no_trust_ops(self, handler):
        """Test verify_mcp_response works without TrustOperations."""
        context = MCPEATPContext(
            mcp_session_id="session-no-ops",
            eatp_trace_id="trace-no-ops",
            agent_id="agent-a",
            target_agent_id="agent-b",
        )

        response = {"result": "ok"}

        # Should not raise, should return True
        result = await handler.verify_mcp_response(context, response)
        assert result is True

    @pytest.mark.asyncio
    async def test_verify_mcp_response_with_error_response(self, handler):
        """Test verify_mcp_response with error in response."""
        context = MCPEATPContext(
            mcp_session_id="session-error",
            eatp_trace_id="trace-error",
            agent_id="agent-a",
            target_agent_id="agent-b",
        )

        response = {"error": "Something went wrong", "code": 500}

        # Error responses should still be valid (verified) but may log warning
        result = await handler.verify_mcp_response(context, response)
        assert result is True  # Response format is valid, even if it contains error


# =============================================================================
# Test MCPEATPHandler - get_call_history
# =============================================================================


class TestMCPEATPHandlerCallHistory:
    """Test MCPEATPHandler.get_call_history() method."""

    @pytest.mark.asyncio
    async def test_call_history_empty_initially(self, handler):
        """Test call history is empty list before any calls."""
        history = handler.get_call_history()

        assert isinstance(history, list)
        assert len(history) == 0

    @pytest.mark.asyncio
    async def test_call_history_tracks_calls(self, handler):
        """Test multiple calls are tracked in history."""
        # Make first call
        context1 = await handler.prepare_mcp_call(
            calling_agent="agent-a",
            target_agent="agent-b",
            tool_name="tool1",
            mcp_session_id="session-1",
        )

        # Make second call
        context2 = await handler.prepare_mcp_call(
            calling_agent="agent-c",
            target_agent="agent-d",
            tool_name="tool2",
            mcp_session_id="session-2",
        )

        # Make third call
        context3 = await handler.prepare_mcp_call(
            calling_agent="agent-e",
            target_agent="agent-f",
            tool_name="tool3",
            mcp_session_id="session-3",
        )

        history = handler.get_call_history()

        assert len(history) == 3
        assert history[0].agent_id == "agent-a"
        assert history[0].target_agent_id == "agent-b"
        assert history[1].agent_id == "agent-c"
        assert history[1].target_agent_id == "agent-d"
        assert history[2].agent_id == "agent-e"
        assert history[2].target_agent_id == "agent-f"

    @pytest.mark.asyncio
    async def test_call_history_returns_copy(self, handler):
        """Test get_call_history returns a copy, not the internal list."""
        await handler.prepare_mcp_call(
            calling_agent="agent-a",
            target_agent="agent-b",
            tool_name="tool1",
            mcp_session_id="session-1",
        )

        history1 = handler.get_call_history()
        history2 = handler.get_call_history()

        # Should be equal but not the same object
        assert history1 == history2
        assert history1 is not history2

        # Modifying returned list should not affect internal state
        history1.clear()
        history3 = handler.get_call_history()
        assert len(history3) == 1


# =============================================================================
# Test MCPEATPHandler - Edge Cases
# =============================================================================


class TestMCPEATPHandlerEdgeCases:
    """Test edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_prepare_mcp_call_empty_strings_rejected(self, handler):
        """Test that empty string agent IDs are rejected."""
        with pytest.raises(ValueError) as exc_info:
            await handler.prepare_mcp_call(
                calling_agent="",
                target_agent="agent-b",
                tool_name="tool1",
                mcp_session_id="session-1",
            )

        assert (
            "calling_agent" in str(exc_info.value).lower()
            or "empty" in str(exc_info.value).lower()
        )

    @pytest.mark.asyncio
    async def test_prepare_mcp_call_empty_target_agent_rejected(self, handler):
        """Test that empty target agent ID is rejected."""
        with pytest.raises(ValueError) as exc_info:
            await handler.prepare_mcp_call(
                calling_agent="agent-a",
                target_agent="",
                tool_name="tool1",
                mcp_session_id="session-1",
            )

        assert (
            "target_agent" in str(exc_info.value).lower()
            or "empty" in str(exc_info.value).lower()
        )

    @pytest.mark.asyncio
    async def test_prepare_mcp_call_empty_tool_name_rejected(self, handler):
        """Test that empty tool name is rejected."""
        with pytest.raises(ValueError) as exc_info:
            await handler.prepare_mcp_call(
                calling_agent="agent-a",
                target_agent="agent-b",
                tool_name="",
                mcp_session_id="session-1",
            )

        assert (
            "tool_name" in str(exc_info.value).lower()
            or "empty" in str(exc_info.value).lower()
        )

    @pytest.mark.asyncio
    async def test_prepare_mcp_call_empty_session_id_rejected(self, handler):
        """Test that empty session ID is rejected."""
        with pytest.raises(ValueError) as exc_info:
            await handler.prepare_mcp_call(
                calling_agent="agent-a",
                target_agent="agent-b",
                tool_name="tool1",
                mcp_session_id="",
            )

        assert (
            "mcp_session_id" in str(exc_info.value).lower()
            or "empty" in str(exc_info.value).lower()
        )

    @pytest.mark.asyncio
    async def test_verify_mcp_response_empty_response(self, handler):
        """Test verify_mcp_response handles empty response dict."""
        context = MCPEATPContext(
            mcp_session_id="session-empty",
            eatp_trace_id="trace-empty",
            agent_id="agent-a",
            target_agent_id="agent-b",
        )

        response = {}

        # Empty response should still be valid
        result = await handler.verify_mcp_response(context, response)
        assert result is True

    @pytest.mark.asyncio
    async def test_handler_with_none_trust_ops_explicitly(self):
        """Test handler created with explicit None trust_operations."""
        handler = MCPEATPHandler(trust_operations=None)

        context = await handler.prepare_mcp_call(
            calling_agent="agent-a",
            target_agent="agent-b",
            tool_name="tool1",
            mcp_session_id="session-1",
        )

        assert context is not None
        assert context.delegation_id is None


# =============================================================================
# Test MCPEATPHandler - Thread Safety (ROUND5-001)
# =============================================================================


class TestMCPHandlerThreadSafety:
    """Test thread-safety of MCPEATPHandler (ROUND5-001).

    These tests verify that concurrent access to prepare_mcp_call and
    get_call_history does not cause race conditions or data loss.
    """

    @pytest.mark.asyncio
    async def test_concurrent_prepare_and_get_history_no_data_loss(self):
        """ROUND5-001: Concurrent prepare_mcp_call and get_call_history causes no data loss.

        Spawns multiple threads calling prepare_mcp_call concurrently,
        then verifies get_call_history returns all entries.
        """
        import asyncio
        import concurrent.futures

        handler = MCPEATPHandler()
        num_calls = 100
        errors = []
        created_contexts = []

        async def make_call(call_id: int):
            """Make a single MCP call."""
            try:
                context = await handler.prepare_mcp_call(
                    calling_agent=f"agent-caller-{call_id}",
                    target_agent=f"agent-target-{call_id}",
                    tool_name=f"tool_{call_id}",
                    mcp_session_id=f"session-{call_id}",
                )
                created_contexts.append(context)
            except Exception as e:
                errors.append(f"call {call_id} error: {e}")

        def read_history_repeatedly(iterations: int):
            """Read history multiple times concurrently with writes."""
            for _ in range(iterations):
                try:
                    # Get history should not fail even during concurrent writes
                    history = handler.get_call_history()
                    # Verify it returns a list
                    assert isinstance(history, list)
                except Exception as e:
                    errors.append(f"read error: {e}")
                import time

                time.sleep(0.001)

        # Run writes and reads concurrently
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            # Start reader threads
            reader_futures = [
                executor.submit(read_history_repeatedly, 50) for _ in range(2)
            ]

            # Run async writes concurrently
            await asyncio.gather(*[make_call(i) for i in range(num_calls)])

            # Wait for readers to complete
            for future in reader_futures:
                future.result(timeout=10.0)

        # No errors should have occurred
        assert errors == [], f"Concurrent operations caused errors: {errors}"

        # All calls should be in history
        history = handler.get_call_history()
        assert len(history) == num_calls, (
            f"Expected {num_calls} entries in history, got {len(history)}. "
            f"Data loss detected!"
        )

        # Verify all created contexts are in history
        history_session_ids = {ctx.mcp_session_id for ctx in history}
        for i in range(num_calls):
            assert (
                f"session-{i}" in history_session_ids
            ), f"session-{i} missing from history"

    def test_get_call_history_returns_copy(self):
        """ROUND5-001: get_call_history returns a copy, not the internal list.

        Verifies that modifications to the returned list do not affect
        the handler's internal state.
        """
        import asyncio

        handler = MCPEATPHandler()

        # Add an entry
        async def add_entry():
            await handler.prepare_mcp_call(
                calling_agent="agent-a",
                target_agent="agent-b",
                tool_name="tool1",
                mcp_session_id="session-copy-test",
            )

        asyncio.run(add_entry())

        # Get history twice
        history1 = handler.get_call_history()
        history2 = handler.get_call_history()

        # Should be equal in content but not same object
        assert len(history1) == 1
        assert len(history2) == 1
        assert (
            history1 is not history2
        ), "get_call_history should return a copy, not the same list object"

        # Modifying returned list should not affect internal state
        history1.clear()
        assert len(history1) == 0

        # Internal state should be unaffected
        history3 = handler.get_call_history()
        assert (
            len(history3) == 1
        ), "Clearing returned list affected internal state - not a copy!"

    def test_handler_has_lock_attribute(self):
        """ROUND5-001: Verify MCPEATPHandler has a threading lock for thread-safety."""
        import threading

        handler = MCPEATPHandler()

        assert hasattr(
            handler, "_lock"
        ), "MCPEATPHandler missing _lock attribute for thread-safety"
        assert isinstance(
            handler._lock, type(threading.Lock())
        ), "_lock should be a threading.Lock instance"

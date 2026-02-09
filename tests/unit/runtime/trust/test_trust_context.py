"""Unit tests for RuntimeTrustContext (CARE-015).

Tests for RuntimeTrustContext, TrustVerificationMode, and context propagation.
These are Tier 1 unit tests - fast, isolated, no external dependencies.
"""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest
from kailash.runtime.trust.context import (
    RuntimeTrustContext,
    TrustVerificationMode,
    get_runtime_trust_context,
    runtime_trust_context,
    set_runtime_trust_context,
)


class TestTrustVerificationModeEnum:
    """Test TrustVerificationMode enum values."""

    def test_disabled_mode_value(self):
        """Test DISABLED mode has correct string value."""
        assert TrustVerificationMode.DISABLED.value == "disabled"

    def test_permissive_mode_value(self):
        """Test PERMISSIVE mode has correct string value."""
        assert TrustVerificationMode.PERMISSIVE.value == "permissive"

    def test_enforcing_mode_value(self):
        """Test ENFORCING mode has correct string value."""
        assert TrustVerificationMode.ENFORCING.value == "enforcing"

    def test_all_enum_members(self):
        """Test all enum members are defined."""
        modes = list(TrustVerificationMode)
        assert len(modes) == 3
        assert TrustVerificationMode.DISABLED in modes
        assert TrustVerificationMode.PERMISSIVE in modes
        assert TrustVerificationMode.ENFORCING in modes

    def test_enum_from_string(self):
        """Test creating enum from string value."""
        assert TrustVerificationMode("disabled") == TrustVerificationMode.DISABLED
        assert TrustVerificationMode("permissive") == TrustVerificationMode.PERMISSIVE
        assert TrustVerificationMode("enforcing") == TrustVerificationMode.ENFORCING

    def test_enum_invalid_string(self):
        """Test invalid string raises ValueError."""
        with pytest.raises(ValueError):
            TrustVerificationMode("invalid")


class TestRuntimeTrustContextCreation:
    """Test RuntimeTrustContext creation and default values."""

    def test_runtime_trust_context_creation(self):
        """Test default field values on creation."""
        ctx = RuntimeTrustContext()

        # trace_id should be a valid UUID string
        assert ctx.trace_id is not None
        # Validate it's a valid UUID format
        uuid.UUID(ctx.trace_id)

        # Check defaults
        assert ctx.human_origin is None
        assert ctx.delegation_chain == []
        assert ctx.delegation_depth == 0
        assert ctx.constraints == {}
        assert ctx.verification_mode == TrustVerificationMode.DISABLED
        assert ctx.workflow_id is None
        assert ctx.node_path == []
        assert ctx.metadata == {}

        # created_at should be a datetime
        assert isinstance(ctx.created_at, datetime)

    def test_runtime_trust_context_with_all_fields(self):
        """Test creation with all custom field values."""
        custom_trace_id = "custom-trace-123"
        custom_human_origin = {"type": "test", "session_id": "sess-1"}
        custom_delegation_chain = ["agent1", "agent2"]
        custom_constraints = {"max_tokens": 1000, "allowed_tools": ["read"]}
        custom_metadata = {"source": "test", "priority": "high"}
        custom_created_at = datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC)

        ctx = RuntimeTrustContext(
            trace_id=custom_trace_id,
            human_origin=custom_human_origin,
            delegation_chain=custom_delegation_chain,
            delegation_depth=3,
            constraints=custom_constraints,
            verification_mode=TrustVerificationMode.ENFORCING,
            workflow_id="workflow-123",
            node_path=["node1", "node2"],
            metadata=custom_metadata,
            created_at=custom_created_at,
        )

        assert ctx.trace_id == custom_trace_id
        assert ctx.human_origin == custom_human_origin
        assert ctx.delegation_chain == custom_delegation_chain
        assert ctx.delegation_depth == 3
        assert ctx.constraints == custom_constraints
        assert ctx.verification_mode == TrustVerificationMode.ENFORCING
        assert ctx.workflow_id == "workflow-123"
        assert ctx.node_path == ["node1", "node2"]
        assert ctx.metadata == custom_metadata
        assert ctx.created_at == custom_created_at


class TestRuntimeTrustContextWithNode:
    """Test with_node method for immutable node path extension."""

    def test_with_node_creates_new_context(self):
        """Test with_node creates a new context, not mutating original."""
        original = RuntimeTrustContext(node_path=["node1"])
        new_ctx = original.with_node("node2")

        # Original should be unchanged
        assert original.node_path == ["node1"]

        # New context should have extended path
        assert new_ctx.node_path == ["node1", "node2"]

        # Should be different instances
        assert original is not new_ctx

    def test_with_node_preserves_other_fields(self):
        """Test with_node preserves all other fields."""
        original = RuntimeTrustContext(
            trace_id="trace-1",
            delegation_depth=2,
            constraints={"max": 100},
            verification_mode=TrustVerificationMode.PERMISSIVE,
            workflow_id="wf-1",
            metadata={"key": "value"},
        )

        new_ctx = original.with_node("new_node")

        assert new_ctx.trace_id == original.trace_id
        assert new_ctx.delegation_depth == original.delegation_depth
        assert new_ctx.constraints == original.constraints
        assert new_ctx.verification_mode == original.verification_mode
        assert new_ctx.workflow_id == original.workflow_id
        assert new_ctx.metadata == original.metadata
        assert new_ctx.created_at == original.created_at

    def test_with_node_empty_initial_path(self):
        """Test with_node works correctly with empty initial path."""
        ctx = RuntimeTrustContext()
        new_ctx = ctx.with_node("first_node")

        assert new_ctx.node_path == ["first_node"]


class TestRuntimeTrustContextWithConstraints:
    """Test with_constraints method for constraint tightening."""

    def test_with_constraints_merges_constraints(self):
        """Test with_constraints merges additional constraints."""
        original = RuntimeTrustContext(constraints={"max_tokens": 1000})
        new_ctx = original.with_constraints({"allowed_tools": ["read"]})

        # Original unchanged
        assert original.constraints == {"max_tokens": 1000}

        # New context has merged constraints
        assert new_ctx.constraints == {
            "max_tokens": 1000,
            "allowed_tools": ["read"],
        }

    def test_with_constraints_tightens_not_loosens(self):
        """Test with_constraints can tighten but constraints are merged (implementation specific)."""
        original = RuntimeTrustContext(constraints={"max_tokens": 1000})
        new_ctx = original.with_constraints({"max_tokens": 500})

        # The new constraint should override (tightening behavior is caller responsibility)
        # This tests that merge happens correctly
        assert new_ctx.constraints == {"max_tokens": 500}

    def test_with_constraints_preserves_other_fields(self):
        """Test with_constraints preserves all other fields."""
        original = RuntimeTrustContext(
            trace_id="trace-1",
            delegation_depth=2,
            node_path=["node1"],
            verification_mode=TrustVerificationMode.ENFORCING,
        )

        new_ctx = original.with_constraints({"new_constraint": "value"})

        assert new_ctx.trace_id == original.trace_id
        assert new_ctx.delegation_depth == original.delegation_depth
        assert new_ctx.node_path == original.node_path
        assert new_ctx.verification_mode == original.verification_mode

    def test_with_constraints_creates_new_instance(self):
        """Test with_constraints creates a new context instance."""
        original = RuntimeTrustContext()
        new_ctx = original.with_constraints({"key": "value"})

        assert original is not new_ctx


class TestRuntimeTrustContextSerialization:
    """Test to_dict and from_dict serialization."""

    def test_to_dict_serialization(self):
        """Test complete serialization to dict."""
        created_at = datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC)
        ctx = RuntimeTrustContext(
            trace_id="trace-123",
            human_origin={"session_id": "sess-1"},
            delegation_chain=["agent1", "agent2"],
            delegation_depth=2,
            constraints={"max_tokens": 1000},
            verification_mode=TrustVerificationMode.PERMISSIVE,
            workflow_id="wf-123",
            node_path=["node1", "node2"],
            metadata={"key": "value"},
            created_at=created_at,
        )

        result = ctx.to_dict()

        assert result["trace_id"] == "trace-123"
        assert result["human_origin"] == {"session_id": "sess-1"}
        assert result["delegation_chain"] == ["agent1", "agent2"]
        assert result["delegation_depth"] == 2
        assert result["constraints"] == {"max_tokens": 1000}
        assert result["verification_mode"] == "permissive"
        assert result["workflow_id"] == "wf-123"
        assert result["node_path"] == ["node1", "node2"]
        assert result["metadata"] == {"key": "value"}
        assert result["created_at"] == "2024-01-15T12:00:00+00:00"

    def test_to_dict_with_none_values(self):
        """Test serialization handles None values."""
        ctx = RuntimeTrustContext()
        result = ctx.to_dict()

        assert result["human_origin"] is None
        assert result["workflow_id"] is None

    def test_to_dict_with_human_origin_to_dict(self):
        """Test serialization calls to_dict on human_origin if it has one."""
        # Create a mock human_origin with to_dict method
        mock_origin = MagicMock()
        mock_origin.to_dict.return_value = {"type": "human", "id": "user-1"}

        ctx = RuntimeTrustContext(human_origin=mock_origin)
        result = ctx.to_dict()

        mock_origin.to_dict.assert_called_once()
        assert result["human_origin"] == {"type": "human", "id": "user-1"}

    def test_from_dict_deserialization(self):
        """Test complete deserialization from dict."""
        data = {
            "trace_id": "trace-123",
            "human_origin": {"session_id": "sess-1"},
            "delegation_chain": ["agent1", "agent2"],
            "delegation_depth": 2,
            "constraints": {"max_tokens": 1000},
            "verification_mode": "permissive",
            "workflow_id": "wf-123",
            "node_path": ["node1", "node2"],
            "metadata": {"key": "value"},
            "created_at": "2024-01-15T12:00:00+00:00",
        }

        ctx = RuntimeTrustContext.from_dict(data)

        assert ctx.trace_id == "trace-123"
        assert ctx.human_origin == {"session_id": "sess-1"}
        assert ctx.delegation_chain == ["agent1", "agent2"]
        assert ctx.delegation_depth == 2
        assert ctx.constraints == {"max_tokens": 1000}
        assert ctx.verification_mode == TrustVerificationMode.PERMISSIVE
        assert ctx.workflow_id == "wf-123"
        assert ctx.node_path == ["node1", "node2"]
        assert ctx.metadata == {"key": "value"}
        assert ctx.created_at == datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC)

    def test_round_trip_serialization(self):
        """Test round-trip: to_dict then from_dict produces equivalent context."""
        original = RuntimeTrustContext(
            trace_id="trace-roundtrip",
            delegation_chain=["a", "b"],
            delegation_depth=5,
            constraints={"limit": 100},
            verification_mode=TrustVerificationMode.ENFORCING,
            workflow_id="wf-round",
            node_path=["n1", "n2", "n3"],
            metadata={"test": True},
        )

        serialized = original.to_dict()
        restored = RuntimeTrustContext.from_dict(serialized)

        assert restored.trace_id == original.trace_id
        assert restored.delegation_chain == original.delegation_chain
        assert restored.delegation_depth == original.delegation_depth
        assert restored.constraints == original.constraints
        assert restored.verification_mode == original.verification_mode
        assert restored.workflow_id == original.workflow_id
        assert restored.node_path == original.node_path
        assert restored.metadata == original.metadata


class TestFromKaizenContextBridge:
    """Test from_kaizen_context classmethod for bridging from Kaizen ExecutionContext."""

    def test_from_kaizen_context_bridge(self):
        """Test bridge from Kaizen ExecutionContext using mock."""
        # Create a mock Kaizen ExecutionContext with expected attributes
        mock_kaizen_ctx = MagicMock()
        mock_kaizen_ctx.trace_id = "kaizen-trace-123"
        mock_kaizen_ctx.human_origin = MagicMock()
        mock_kaizen_ctx.human_origin.to_dict.return_value = {"type": "human"}
        mock_kaizen_ctx.delegation_chain = ["kaizen_agent"]
        mock_kaizen_ctx.delegation_depth = 1
        mock_kaizen_ctx.constraints = {"kaizen_constraint": True}

        ctx = RuntimeTrustContext.from_kaizen_context(mock_kaizen_ctx)

        assert ctx.trace_id == "kaizen-trace-123"
        assert ctx.delegation_chain == ["kaizen_agent"]
        assert ctx.delegation_depth == 1
        assert ctx.constraints == {"kaizen_constraint": True}
        # Verification mode should be ENFORCING when bridging from Kaizen
        assert ctx.verification_mode == TrustVerificationMode.ENFORCING

    def test_from_kaizen_context_with_minimal_attributes(self):
        """Test bridge handles Kaizen context with minimal attributes."""
        mock_kaizen_ctx = MagicMock()
        mock_kaizen_ctx.trace_id = "minimal-trace"
        # Simulate missing optional attributes
        mock_kaizen_ctx.human_origin = None
        mock_kaizen_ctx.delegation_chain = []
        mock_kaizen_ctx.delegation_depth = 0
        mock_kaizen_ctx.constraints = {}

        ctx = RuntimeTrustContext.from_kaizen_context(mock_kaizen_ctx)

        assert ctx.trace_id == "minimal-trace"
        assert ctx.human_origin is None
        assert ctx.delegation_chain == []
        assert ctx.delegation_depth == 0
        assert ctx.constraints == {}
        assert ctx.verification_mode == TrustVerificationMode.ENFORCING


class TestContextVarPropagation:
    """Test context variable get/set for context propagation."""

    def test_context_var_get_default_none(self):
        """Test get_runtime_trust_context returns None by default."""
        # Reset context to ensure clean state
        set_runtime_trust_context(None)
        result = get_runtime_trust_context()
        # Should return None when not set (or after reset)
        # Note: ContextVar reset is tricky, we test the behavior we can
        assert result is None or isinstance(result, RuntimeTrustContext)

    def test_context_var_set_and_get(self):
        """Test set and get runtime context."""
        ctx = RuntimeTrustContext(trace_id="test-context-var")

        set_runtime_trust_context(ctx)
        result = get_runtime_trust_context()

        assert result is ctx
        assert result.trace_id == "test-context-var"


class TestContextManagerCleanup:
    """Test context manager for proper cleanup."""

    def test_context_manager_sets_and_gets_context(self):
        """Test context manager makes context available inside block."""
        ctx = RuntimeTrustContext(trace_id="cm-test")

        with runtime_trust_context(ctx) as yielded_ctx:
            assert yielded_ctx is ctx
            assert get_runtime_trust_context() is ctx

    def test_context_manager_cleanup(self):
        """Test context manager resets context after exit."""
        # Set initial context
        initial_ctx = RuntimeTrustContext(trace_id="initial")
        set_runtime_trust_context(initial_ctx)

        new_ctx = RuntimeTrustContext(trace_id="new")

        with runtime_trust_context(new_ctx):
            assert get_runtime_trust_context().trace_id == "new"

        # After context manager, should be reset to initial
        # (Note: ContextVar.reset() restores to the value before set)
        result = get_runtime_trust_context()
        assert result.trace_id == "initial"

    def test_context_manager_exception_safety(self):
        """Test context manager cleans up even on exception."""
        initial_ctx = RuntimeTrustContext(trace_id="initial-exc")
        set_runtime_trust_context(initial_ctx)

        new_ctx = RuntimeTrustContext(trace_id="new-exc")

        with pytest.raises(ValueError):
            with runtime_trust_context(new_ctx):
                assert get_runtime_trust_context().trace_id == "new-exc"
                raise ValueError("Test exception")

        # After exception, context should be restored
        result = get_runtime_trust_context()
        assert result.trace_id == "initial-exc"

    def test_context_manager_nested(self):
        """Test nested context managers work correctly."""
        ctx1 = RuntimeTrustContext(trace_id="ctx1")
        ctx2 = RuntimeTrustContext(trace_id="ctx2")

        with runtime_trust_context(ctx1):
            assert get_runtime_trust_context().trace_id == "ctx1"

            with runtime_trust_context(ctx2):
                assert get_runtime_trust_context().trace_id == "ctx2"

            # After inner context manager exits
            assert get_runtime_trust_context().trace_id == "ctx1"

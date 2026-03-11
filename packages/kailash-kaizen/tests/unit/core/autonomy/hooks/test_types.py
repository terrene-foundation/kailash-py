"""
Unit tests for hooks system types.

Tests HookEvent, HookPriority, HookContext, and HookResult.
"""

import time

import pytest
from kaizen.core.autonomy.hooks.types import (
    HookContext,
    HookEvent,
    HookPriority,
    HookResult,
)


class TestHookEvent:
    """Test HookEvent enum"""

    def test_all_events_defined(self):
        """Test all 18 hook events are defined (expanded in v0.8.0)"""
        events = list(HookEvent)
        assert len(events) == 18

    def test_tool_lifecycle_events(self):
        """Test tool execution lifecycle events"""
        assert HookEvent.PRE_TOOL_USE.value == "pre_tool_use"
        assert HookEvent.POST_TOOL_USE.value == "post_tool_use"

    def test_agent_lifecycle_events(self):
        """Test agent execution lifecycle events"""
        assert HookEvent.PRE_AGENT_LOOP.value == "pre_agent_loop"
        assert HookEvent.POST_AGENT_LOOP.value == "post_agent_loop"

    def test_specialist_lifecycle_events(self):
        """Test specialist invocation lifecycle events"""
        assert HookEvent.PRE_SPECIALIST_INVOKE.value == "pre_specialist_invoke"
        assert HookEvent.POST_SPECIALIST_INVOKE.value == "post_specialist_invoke"

    def test_permission_lifecycle_events(self):
        """Test permission check lifecycle events"""
        assert HookEvent.PRE_PERMISSION_CHECK.value == "pre_permission_check"
        assert HookEvent.POST_PERMISSION_CHECK.value == "post_permission_check"

    def test_checkpoint_lifecycle_events(self):
        """Test checkpoint save lifecycle events"""
        assert HookEvent.PRE_CHECKPOINT_SAVE.value == "pre_checkpoint_save"
        assert HookEvent.POST_CHECKPOINT_SAVE.value == "post_checkpoint_save"


class TestHookPriority:
    """Test HookPriority enum"""

    def test_all_priorities_defined(self):
        """Test all 4 priority levels are defined"""
        priorities = list(HookPriority)
        assert len(priorities) == 4

    def test_priority_values(self):
        """Test priority values are ordered correctly"""
        assert HookPriority.CRITICAL.value == 0
        assert HookPriority.HIGH.value == 1
        assert HookPriority.NORMAL.value == 2
        assert HookPriority.LOW.value == 3

    def test_priority_ordering(self):
        """Test priorities can be compared"""
        assert HookPriority.CRITICAL.value < HookPriority.HIGH.value
        assert HookPriority.HIGH.value < HookPriority.NORMAL.value
        assert HookPriority.NORMAL.value < HookPriority.LOW.value


class TestHookContext:
    """Test HookContext dataclass"""

    def test_create_context(self):
        """Test creating a basic HookContext"""
        context = HookContext(
            event_type=HookEvent.PRE_TOOL_USE,
            agent_id="test_agent",
            timestamp=1234567890.0,
            data={"tool_name": "search"},
        )

        assert context.event_type == HookEvent.PRE_TOOL_USE
        assert context.agent_id == "test_agent"
        assert context.timestamp == 1234567890.0
        assert context.data == {"tool_name": "search"}
        assert context.metadata == {}

    def test_context_with_metadata(self):
        """Test HookContext with metadata"""
        context = HookContext(
            event_type=HookEvent.POST_TOOL_USE,
            agent_id="test_agent",
            timestamp=1234567890.0,
            data={"result": "success"},
            metadata={"session_id": "abc123"},
        )

        assert context.metadata == {"session_id": "abc123"}

    def test_context_auto_timestamp(self):
        """Test timestamp is auto-set if None"""
        context = HookContext(
            event_type=HookEvent.PRE_AGENT_LOOP,
            agent_id="test_agent",
            timestamp=None,  # type: ignore
            data={},
        )

        # Should be set to current time (within 1 second)
        assert abs(context.timestamp - time.time()) < 1.0


class TestHookResult:
    """Test HookResult dataclass"""

    def test_successful_result(self):
        """Test creating a successful result"""
        result = HookResult(success=True)

        assert result.success is True
        assert result.data is None
        assert result.error is None
        assert result.duration_ms == 0.0

    def test_successful_result_with_data(self):
        """Test successful result with data"""
        result = HookResult(success=True, data={"count": 42})

        assert result.success is True
        assert result.data == {"count": 42}
        assert result.error is None

    def test_failed_result(self):
        """Test creating a failed result"""
        result = HookResult(success=False, error="Something went wrong")

        assert result.success is False
        assert result.error == "Something went wrong"
        assert result.data is None

    def test_failed_result_validation(self):
        """Test failed result requires error message"""
        with pytest.raises(ValueError, match="must include error message"):
            HookResult(success=False)

    def test_result_with_duration(self):
        """Test result with duration"""
        result = HookResult(success=True, duration_ms=123.45)

        assert result.duration_ms == 123.45

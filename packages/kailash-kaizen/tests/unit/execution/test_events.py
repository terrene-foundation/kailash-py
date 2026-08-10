"""
Unit Tests for Execution Events (Tier 1)

Tests the execution event types used for autonomous agent runtime.
Part of TODO-203 Task/Skill Tools implementation.
Extended for TODO-204 Enterprise-App Streaming Integration.

Coverage:
- EventType enum values (22 types including 10 Enterprise-App core)
- ExecutionEvent base class
- Enterprise-App core events: Started, Thinking, Message, ToolUse, ToolResult,
  Progress, Completed, Error
- Subagent events: SubagentSpawn, SubagentComplete
- Skill events: SkillInvoke, SkillComplete
- Cost tracking: CostUpdate
- Serialization
"""

from datetime import datetime, timezone

import pytest

from kaizen.execution.events import (  # Core enum and base; Enterprise-App Core Events (TODO-204); Subagent events (TODO-203); Skill events (TODO-203); Cost tracking
    CompletedEvent,
    CostUpdateEvent,
    ErrorEvent,
    EventType,
    ExecutionEvent,
    MessageEvent,
    ProgressEvent,
    SkillCompleteEvent,
    SkillInvokeEvent,
    StartedEvent,
    SubagentCompleteEvent,
    SubagentSpawnEvent,
    ThinkingEvent,
    ToolResultEvent,
    ToolUseEvent,
)


class TestEventType:
    """Test EventType enum."""

    def test_subagent_lifecycle_events(self):
        """Test subagent lifecycle event types exist."""
        assert EventType.SUBAGENT_SPAWN.value == "subagent_spawn"
        assert EventType.SUBAGENT_COMPLETE.value == "subagent_complete"
        assert EventType.SUBAGENT_ERROR.value == "subagent_error"

    def test_skill_events(self):
        """Test skill event types exist."""
        assert EventType.SKILL_INVOKE.value == "skill_invoke"
        assert EventType.SKILL_COMPLETE.value == "skill_complete"

    def test_cost_tracking_event(self):
        """Test cost tracking event type exists."""
        assert EventType.COST_UPDATE.value == "cost_update"

    def test_execution_milestone_events(self):
        """Test execution milestone event types exist."""
        assert EventType.EXECUTION_START.value == "execution_start"
        assert EventType.EXECUTION_COMPLETE.value == "execution_complete"
        assert EventType.CYCLE_START.value == "cycle_start"
        assert EventType.CYCLE_COMPLETE.value == "cycle_complete"

    def test_tool_events(self):
        """Test tool event types exist."""
        assert EventType.TOOL_START.value == "tool_start"
        assert EventType.TOOL_COMPLETE.value == "tool_complete"
        assert EventType.TOOL_ERROR.value == "tool_error"

    def test_thinking_events(self):
        """Test thinking/reasoning event types exist."""
        assert EventType.THINKING.value == "thinking"
        assert EventType.THOUGHT.value == "thought"


class TestExecutionEvent:
    """Test ExecutionEvent base class."""

    def test_create_with_required_fields(self):
        """Test creating event with required fields."""
        event = ExecutionEvent(
            event_type=EventType.EXECUTION_START,
            session_id="session-123",
        )

        assert event.event_type == EventType.EXECUTION_START
        assert event.session_id == "session-123"
        assert event.timestamp is not None
        assert event.metadata == {}

    def test_timestamp_auto_generated(self):
        """Test timestamp is auto-generated in ISO format."""
        event = ExecutionEvent(
            event_type=EventType.EXECUTION_START,
            session_id="session-123",
        )

        # Should be valid ISO format
        parsed = datetime.fromisoformat(event.timestamp.replace("Z", "+00:00"))
        assert parsed is not None

    def test_custom_metadata(self):
        """Test event with custom metadata."""
        event = ExecutionEvent(
            event_type=EventType.EXECUTION_START,
            session_id="session-123",
            metadata={"key": "value", "count": 42},
        )

        assert event.metadata["key"] == "value"
        assert event.metadata["count"] == 42

    def test_to_dict(self):
        """Test event serialization to dict."""
        event = ExecutionEvent(
            event_type=EventType.EXECUTION_START,
            session_id="session-123",
            metadata={"extra": "data"},
        )

        data = event.to_dict()

        assert data["event_type"] == "execution_start"
        assert data["session_id"] == "session-123"
        assert "timestamp" in data
        assert data["metadata"]["extra"] == "data"


class TestSubagentSpawnEvent:
    """Test SubagentSpawnEvent."""

    def test_default_values(self):
        """Test default values for SubagentSpawnEvent."""
        event = SubagentSpawnEvent(session_id="session-123")

        assert event.event_type == EventType.SUBAGENT_SPAWN
        assert event.subagent_id == ""
        assert event.subagent_name == ""
        assert event.task == ""
        assert event.parent_agent_id == ""
        assert event.trust_chain_id == ""
        assert event.capabilities == []
        assert event.model is None
        assert event.max_turns is None
        assert event.run_in_background is False

    def test_full_initialization(self):
        """Test full initialization of SubagentSpawnEvent."""
        event = SubagentSpawnEvent(
            session_id="session-123",
            subagent_id="subagent-456",
            subagent_name="code-reviewer",
            task="Review the authentication module",
            parent_agent_id="parent-789",
            trust_chain_id="chain-abc",
            capabilities=["Read", "Glob", "Grep"],
            model="sonnet",
            max_turns=10,
            run_in_background=True,
        )

        assert event.subagent_id == "subagent-456"
        assert event.subagent_name == "code-reviewer"
        assert event.task == "Review the authentication module"
        assert event.parent_agent_id == "parent-789"
        assert event.trust_chain_id == "chain-abc"
        assert event.capabilities == ["Read", "Glob", "Grep"]
        assert event.model == "sonnet"
        assert event.max_turns == 10
        assert event.run_in_background is True

    def test_event_type_set_automatically(self):
        """Test event_type is set in __post_init__."""
        event = SubagentSpawnEvent(session_id="session-123")

        # Even with default event_type, it should be overwritten
        assert event.event_type == EventType.SUBAGENT_SPAWN

    def test_to_dict_includes_all_fields(self):
        """Test to_dict includes all SubagentSpawnEvent fields."""
        event = SubagentSpawnEvent(
            session_id="session-123",
            subagent_id="subagent-456",
            subagent_name="code-reviewer",
            task="Review code",
            parent_agent_id="parent-789",
            trust_chain_id="chain-abc",
            capabilities=["Read"],
            model="sonnet",
            max_turns=5,
            run_in_background=True,
        )

        data = event.to_dict()

        assert data["event_type"] == "subagent_spawn"
        assert data["session_id"] == "session-123"
        assert data["subagent_id"] == "subagent-456"
        assert data["subagent_name"] == "code-reviewer"
        assert data["task"] == "Review code"
        assert data["parent_agent_id"] == "parent-789"
        assert data["trust_chain_id"] == "chain-abc"
        assert data["capabilities"] == ["Read"]
        assert data["model"] == "sonnet"
        assert data["max_turns"] == 5
        assert data["run_in_background"] is True


class TestSubagentCompleteEvent:
    """Test SubagentCompleteEvent."""

    def test_default_values(self):
        """Test default values for SubagentCompleteEvent."""
        event = SubagentCompleteEvent(session_id="session-123")

        assert event.event_type == EventType.SUBAGENT_COMPLETE
        assert event.subagent_id == ""
        assert event.parent_agent_id == ""
        assert event.status == "completed"
        assert event.output == ""
        assert event.tokens_used == 0
        assert event.cost_usd == 0.0
        assert event.cycles_used == 0
        assert event.duration_ms == 0
        assert event.error_message is None

    def test_full_initialization(self):
        """Test full initialization of SubagentCompleteEvent."""
        event = SubagentCompleteEvent(
            session_id="session-123",
            subagent_id="subagent-456",
            parent_agent_id="parent-789",
            status="completed",
            output="Review complete: 3 issues found",
            tokens_used=500,
            cost_usd=0.005,
            cycles_used=5,
            duration_ms=3000,
        )

        assert event.subagent_id == "subagent-456"
        assert event.parent_agent_id == "parent-789"
        assert event.status == "completed"
        assert event.output == "Review complete: 3 issues found"
        assert event.tokens_used == 500
        assert event.cost_usd == 0.005
        assert event.cycles_used == 5
        assert event.duration_ms == 3000

    def test_error_status(self):
        """Test error status in SubagentCompleteEvent."""
        event = SubagentCompleteEvent(
            session_id="session-123",
            subagent_id="subagent-456",
            status="error",
            error_message="Execution failed due to timeout",
        )

        assert event.status == "error"
        assert event.error_message == "Execution failed due to timeout"

    def test_to_dict_includes_all_fields(self):
        """Test to_dict includes all SubagentCompleteEvent fields."""
        event = SubagentCompleteEvent(
            session_id="session-123",
            subagent_id="subagent-456",
            parent_agent_id="parent-789",
            status="completed",
            output="Done",
            tokens_used=100,
            cost_usd=0.001,
            cycles_used=2,
            duration_ms=1000,
            error_message=None,
        )

        data = event.to_dict()

        assert data["event_type"] == "subagent_complete"
        assert data["subagent_id"] == "subagent-456"
        assert data["parent_agent_id"] == "parent-789"
        assert data["status"] == "completed"
        assert data["output"] == "Done"
        assert data["tokens_used"] == 100
        assert data["cost_usd"] == 0.001
        assert data["cycles_used"] == 2
        assert data["duration_ms"] == 1000
        assert data["error_message"] is None


class TestSkillInvokeEvent:
    """Test SkillInvokeEvent."""

    def test_default_values(self):
        """Test default values for SkillInvokeEvent."""
        event = SkillInvokeEvent(session_id="session-123")

        assert event.event_type == EventType.SKILL_INVOKE
        assert event.skill_name == ""
        assert event.skill_description == ""
        assert event.agent_id == ""
        assert event.args == {}

    def test_full_initialization(self):
        """Test full initialization of SkillInvokeEvent."""
        event = SkillInvokeEvent(
            session_id="session-123",
            skill_name="python-patterns",
            skill_description="Python design patterns",
            agent_id="agent-456",
            args={"load_additional_files": True},
        )

        assert event.skill_name == "python-patterns"
        assert event.skill_description == "Python design patterns"
        assert event.agent_id == "agent-456"
        assert event.args == {"load_additional_files": True}

    def test_to_dict_includes_all_fields(self):
        """Test to_dict includes all SkillInvokeEvent fields."""
        event = SkillInvokeEvent(
            session_id="session-123",
            skill_name="testing-guide",
            skill_description="Testing best practices",
            agent_id="agent-789",
            args={"option": "value"},
        )

        data = event.to_dict()

        assert data["event_type"] == "skill_invoke"
        assert data["skill_name"] == "testing-guide"
        assert data["skill_description"] == "Testing best practices"
        assert data["agent_id"] == "agent-789"
        assert data["args"] == {"option": "value"}


class TestSkillCompleteEvent:
    """Test SkillCompleteEvent."""

    def test_default_values(self):
        """Test default values for SkillCompleteEvent."""
        event = SkillCompleteEvent(session_id="session-123")

        assert event.event_type == EventType.SKILL_COMPLETE
        assert event.skill_name == ""
        assert event.agent_id == ""
        assert event.success is True
        assert event.content_loaded is False
        assert event.content_size == 0
        assert event.additional_files_count == 0
        assert event.error_message is None

    def test_successful_completion(self):
        """Test successful skill completion."""
        event = SkillCompleteEvent(
            session_id="session-123",
            skill_name="python-patterns",
            agent_id="agent-456",
            success=True,
            content_loaded=True,
            content_size=5000,
            additional_files_count=3,
        )

        assert event.success is True
        assert event.content_loaded is True
        assert event.content_size == 5000
        assert event.additional_files_count == 3
        assert event.error_message is None

    def test_failed_completion(self):
        """Test failed skill completion."""
        event = SkillCompleteEvent(
            session_id="session-123",
            skill_name="unknown-skill",
            agent_id="agent-456",
            success=False,
            error_message="Skill not found",
        )

        assert event.success is False
        assert event.error_message == "Skill not found"

    def test_to_dict_includes_all_fields(self):
        """Test to_dict includes all SkillCompleteEvent fields."""
        event = SkillCompleteEvent(
            session_id="session-123",
            skill_name="testing-guide",
            agent_id="agent-789",
            success=True,
            content_loaded=True,
            content_size=1000,
            additional_files_count=2,
        )

        data = event.to_dict()

        assert data["event_type"] == "skill_complete"
        assert data["skill_name"] == "testing-guide"
        assert data["agent_id"] == "agent-789"
        assert data["success"] is True
        assert data["content_loaded"] is True
        assert data["content_size"] == 1000
        assert data["additional_files_count"] == 2


class TestCostUpdateEvent:
    """Test CostUpdateEvent."""

    def test_default_values(self):
        """Test default values for CostUpdateEvent."""
        event = CostUpdateEvent(session_id="session-123")

        assert event.event_type == EventType.COST_UPDATE
        assert event.agent_id == ""
        assert event.tokens_added == 0
        assert event.cost_added_usd == 0.0
        assert event.total_tokens == 0
        assert event.total_cost_usd == 0.0

    def test_full_initialization(self):
        """Test full initialization of CostUpdateEvent."""
        event = CostUpdateEvent(
            session_id="session-123",
            agent_id="agent-456",
            tokens_added=500,
            cost_added_usd=0.005,
            total_tokens=1500,
            total_cost_usd=0.015,
        )

        assert event.agent_id == "agent-456"
        assert event.tokens_added == 500
        assert event.cost_added_usd == 0.005
        assert event.total_tokens == 1500
        assert event.total_cost_usd == 0.015

    def test_to_dict_includes_all_fields(self):
        """Test to_dict includes all CostUpdateEvent fields."""
        event = CostUpdateEvent(
            session_id="session-123",
            agent_id="subagent-789",
            tokens_added=100,
            cost_added_usd=0.001,
            total_tokens=500,
            total_cost_usd=0.005,
        )

        data = event.to_dict()

        assert data["event_type"] == "cost_update"
        assert data["agent_id"] == "subagent-789"
        assert data["tokens_added"] == 100
        assert data["cost_added_usd"] == 0.001
        assert data["total_tokens"] == 500
        assert data["total_cost_usd"] == 0.005


# ============================================================================
# Enterprise-App Core Event Tests (TODO-204)
# ============================================================================


class TestEnterpriseAppCoreEventTypes:
    """Test Enterprise-App core event types exist."""

    def test_started_event_type(self):
        """Test STARTED event type exists."""
        assert EventType.STARTED.value == "started"

    def test_thinking_event_type(self):
        """Test THINKING event type exists."""
        assert EventType.THINKING.value == "thinking"

    def test_message_event_type(self):
        """Test MESSAGE event type exists."""
        assert EventType.MESSAGE.value == "message"

    def test_tool_use_event_type(self):
        """Test TOOL_USE event type exists."""
        assert EventType.TOOL_USE.value == "tool_use"

    def test_tool_result_event_type(self):
        """Test TOOL_RESULT event type exists."""
        assert EventType.TOOL_RESULT.value == "tool_result"

    def test_progress_event_type(self):
        """Test PROGRESS event type exists."""
        assert EventType.PROGRESS.value == "progress"

    def test_completed_event_type(self):
        """Test COMPLETED event type exists."""
        assert EventType.COMPLETED.value == "completed"

    def test_error_event_type(self):
        """Test ERROR event type exists."""
        assert EventType.ERROR.value == "error"


class TestStartedEvent:
    """Test StartedEvent (Enterprise-App)."""

    def test_default_values(self):
        """Test default values for StartedEvent."""
        event = StartedEvent(session_id="session-123")

        assert event.event_type == EventType.STARTED
        assert event.execution_id == ""
        assert event.agent_id == ""
        assert event.agent_name == ""
        assert event.trust_chain_id == ""

    def test_full_initialization(self):
        """Test full initialization of StartedEvent."""
        event = StartedEvent(
            session_id="session-123",
            execution_id="exec-456",
            agent_id="agent-001",
            agent_name="Financial Analyst",
            trust_chain_id="chain-abc",
        )

        assert event.execution_id == "exec-456"
        assert event.agent_id == "agent-001"
        assert event.agent_name == "Financial Analyst"
        assert event.trust_chain_id == "chain-abc"

    def test_to_dict_includes_all_fields(self):
        """Test to_dict includes all StartedEvent fields."""
        event = StartedEvent(
            session_id="session-123",
            execution_id="exec-456",
            agent_id="agent-001",
            agent_name="Code Reviewer",
            trust_chain_id="chain-xyz",
        )

        data = event.to_dict()

        assert data["event_type"] == "started"
        assert data["execution_id"] == "exec-456"
        assert data["agent_id"] == "agent-001"
        assert data["agent_name"] == "Code Reviewer"
        assert data["trust_chain_id"] == "chain-xyz"


class TestThinkingEvent:
    """Test ThinkingEvent (Enterprise-App)."""

    def test_default_values(self):
        """Test default values for ThinkingEvent."""
        event = ThinkingEvent(session_id="session-123")

        assert event.event_type == EventType.THINKING
        assert event.content == ""
        assert event.execution_id == ""

    def test_full_initialization(self):
        """Test full initialization of ThinkingEvent."""
        event = ThinkingEvent(
            session_id="session-123",
            execution_id="exec-456",
            content="Let me analyze the data structure...",
        )

        assert event.content == "Let me analyze the data structure..."
        assert event.execution_id == "exec-456"

    def test_to_dict_includes_all_fields(self):
        """Test to_dict includes all ThinkingEvent fields."""
        event = ThinkingEvent(
            session_id="session-123",
            execution_id="exec-456",
            content="Analyzing requirements...",
        )

        data = event.to_dict()

        assert data["event_type"] == "thinking"
        assert data["content"] == "Analyzing requirements..."
        assert data["execution_id"] == "exec-456"


class TestMessageEvent:
    """Test MessageEvent (Enterprise-App)."""

    def test_default_values(self):
        """Test default values for MessageEvent."""
        event = MessageEvent(session_id="session-123")

        assert event.event_type == EventType.MESSAGE
        assert event.role == "assistant"
        assert event.content == ""
        assert event.execution_id == ""

    def test_full_initialization(self):
        """Test full initialization of MessageEvent."""
        event = MessageEvent(
            session_id="session-123",
            execution_id="exec-456",
            role="user",
            content="Please analyze this code.",
        )

        assert event.role == "user"
        assert event.content == "Please analyze this code."
        assert event.execution_id == "exec-456"

    def test_assistant_role(self):
        """Test assistant role in MessageEvent."""
        event = MessageEvent(
            session_id="session-123",
            role="assistant",
            content="Based on my analysis...",
        )

        assert event.role == "assistant"

    def test_to_dict_includes_all_fields(self):
        """Test to_dict includes all MessageEvent fields."""
        event = MessageEvent(
            session_id="session-123",
            execution_id="exec-456",
            role="assistant",
            content="Here is my response.",
        )

        data = event.to_dict()

        assert data["event_type"] == "message"
        assert data["role"] == "assistant"
        assert data["content"] == "Here is my response."
        assert data["execution_id"] == "exec-456"


class TestToolUseEvent:
    """Test ToolUseEvent (Enterprise-App)."""

    def test_default_values(self):
        """Test default values for ToolUseEvent."""
        event = ToolUseEvent(session_id="session-123")

        assert event.event_type == EventType.TOOL_USE
        assert event.tool == ""
        assert event.input == {}
        assert event.execution_id == ""
        assert event.tool_call_id == ""

    def test_full_initialization(self):
        """Test full initialization of ToolUseEvent."""
        event = ToolUseEvent(
            session_id="session-123",
            execution_id="exec-456",
            tool="read_file",
            input={"path": "/data/report.txt"},
            tool_call_id="tool-789",
        )

        assert event.tool == "read_file"
        assert event.input == {"path": "/data/report.txt"}
        assert event.tool_call_id == "tool-789"

    def test_to_dict_includes_all_fields(self):
        """Test to_dict includes all ToolUseEvent fields."""
        event = ToolUseEvent(
            session_id="session-123",
            execution_id="exec-456",
            tool="write_file",
            input={"path": "output.txt", "content": "data"},
            tool_call_id="tool-abc",
        )

        data = event.to_dict()

        assert data["event_type"] == "tool_use"
        assert data["tool"] == "write_file"
        assert data["input"] == {"path": "output.txt", "content": "data"}
        assert data["tool_call_id"] == "tool-abc"


class TestToolResultEvent:
    """Test ToolResultEvent (Enterprise-App)."""

    def test_default_values(self):
        """Test default values for ToolResultEvent."""
        event = ToolResultEvent(session_id="session-123")

        assert event.event_type == EventType.TOOL_RESULT
        assert event.tool == ""
        assert event.output is None
        assert event.error is None
        assert event.execution_id == ""
        assert event.tool_call_id == ""
        assert event.duration_ms == 0

    def test_successful_result(self):
        """Test successful tool result."""
        event = ToolResultEvent(
            session_id="session-123",
            execution_id="exec-456",
            tool="read_file",
            output="File contents here...",
            tool_call_id="tool-789",
            duration_ms=150,
        )

        assert event.output == "File contents here..."
        assert event.error is None
        assert event.duration_ms == 150

    def test_error_result(self):
        """Test error tool result."""
        event = ToolResultEvent(
            session_id="session-123",
            execution_id="exec-456",
            tool="read_file",
            error="File not found",
            tool_call_id="tool-789",
        )

        assert event.output is None
        assert event.error == "File not found"

    def test_to_dict_includes_all_fields(self):
        """Test to_dict includes all ToolResultEvent fields."""
        event = ToolResultEvent(
            session_id="session-123",
            execution_id="exec-456",
            tool="bash_command",
            output="Command output",
            tool_call_id="tool-xyz",
            duration_ms=500,
        )

        data = event.to_dict()

        assert data["event_type"] == "tool_result"
        assert data["tool"] == "bash_command"
        assert data["output"] == "Command output"
        assert data["duration_ms"] == 500


class TestProgressEvent:
    """Test ProgressEvent (Enterprise-App)."""

    def test_default_values(self):
        """Test default values for ProgressEvent."""
        event = ProgressEvent(session_id="session-123")

        assert event.event_type == EventType.PROGRESS
        assert event.percentage == 0
        assert event.step == ""
        assert event.details == ""
        assert event.execution_id == ""

    def test_full_initialization(self):
        """Test full initialization of ProgressEvent."""
        event = ProgressEvent(
            session_id="session-123",
            execution_id="exec-456",
            percentage=50,
            step="Analyzing data",
            details="Processing file 5 of 10",
        )

        assert event.percentage == 50
        assert event.step == "Analyzing data"
        assert event.details == "Processing file 5 of 10"

    def test_boundary_percentages(self):
        """Test boundary percentage values."""
        event_start = ProgressEvent(session_id="s1", percentage=0)
        event_end = ProgressEvent(session_id="s2", percentage=100)

        assert event_start.percentage == 0
        assert event_end.percentage == 100

    def test_to_dict_includes_all_fields(self):
        """Test to_dict includes all ProgressEvent fields."""
        event = ProgressEvent(
            session_id="session-123",
            execution_id="exec-456",
            percentage=75,
            step="Finalizing",
            details="Almost done",
        )

        data = event.to_dict()

        assert data["event_type"] == "progress"
        assert data["percentage"] == 75
        assert data["step"] == "Finalizing"
        assert data["details"] == "Almost done"


class TestCompletedEvent:
    """Test CompletedEvent (Enterprise-App)."""

    def test_default_values(self):
        """Test default values for CompletedEvent."""
        event = CompletedEvent(session_id="session-123")

        assert event.event_type == EventType.COMPLETED
        assert event.execution_id == ""
        assert event.total_tokens == 0
        assert event.total_cost_cents == 0
        assert event.total_cost_usd == 0.0
        assert event.duration_ms == 0
        assert event.cycles_used == 0
        assert event.tools_used == 0
        assert event.subagents_spawned == 0

    def test_full_initialization(self):
        """Test full initialization of CompletedEvent."""
        event = CompletedEvent(
            session_id="session-123",
            execution_id="exec-456",
            total_tokens=1500,
            total_cost_cents=45,
            total_cost_usd=0.45,
            duration_ms=5000,
            cycles_used=3,
            tools_used=5,
            subagents_spawned=2,
        )

        assert event.total_tokens == 1500
        assert event.total_cost_cents == 45
        assert event.total_cost_usd == 0.45
        assert event.duration_ms == 5000
        assert event.cycles_used == 3
        assert event.tools_used == 5
        assert event.subagents_spawned == 2

    def test_to_dict_includes_all_fields(self):
        """Test to_dict includes all CompletedEvent fields."""
        event = CompletedEvent(
            session_id="session-123",
            execution_id="exec-456",
            total_tokens=2000,
            total_cost_cents=60,
            total_cost_usd=0.60,
            duration_ms=8000,
        )

        data = event.to_dict()

        assert data["event_type"] == "completed"
        assert data["total_tokens"] == 2000
        assert data["total_cost_cents"] == 60
        assert data["total_cost_usd"] == 0.60
        assert data["duration_ms"] == 8000


class TestErrorEvent:
    """Test ErrorEvent (Enterprise-App)."""

    def test_default_values(self):
        """Test default values for ErrorEvent."""
        event = ErrorEvent(session_id="session-123")

        assert event.event_type == EventType.ERROR
        assert event.execution_id == ""
        assert event.message == ""
        assert event.error_type == ""
        assert event.stack_trace is None
        assert event.recoverable is False

    def test_full_initialization(self):
        """Test full initialization of ErrorEvent."""
        event = ErrorEvent(
            session_id="session-123",
            execution_id="exec-456",
            message="API rate limit exceeded",
            error_type="RateLimitError",
            stack_trace="Traceback...",
            recoverable=True,
        )

        assert event.message == "API rate limit exceeded"
        assert event.error_type == "RateLimitError"
        assert event.stack_trace == "Traceback..."
        assert event.recoverable is True

    def test_non_recoverable_error(self):
        """Test non-recoverable error."""
        event = ErrorEvent(
            session_id="session-123",
            message="Critical failure",
            error_type="FatalError",
            recoverable=False,
        )

        assert event.recoverable is False

    def test_to_dict_includes_all_fields(self):
        """Test to_dict includes all ErrorEvent fields."""
        event = ErrorEvent(
            session_id="session-123",
            execution_id="exec-456",
            message="Connection timeout",
            error_type="TimeoutError",
            recoverable=True,
        )

        data = event.to_dict()

        assert data["event_type"] == "error"
        assert data["message"] == "Connection timeout"
        assert data["error_type"] == "TimeoutError"
        assert data["recoverable"] is True


# ============================================================================
# Serialization Tests (Updated for TODO-204)
# ============================================================================


class TestEventsSerialization:
    """Test events serialization consistency."""

    def test_all_events_have_timestamp(self):
        """Test all event types include timestamp."""
        events = [
            # Enterprise-App events
            StartedEvent(session_id="s1"),
            ThinkingEvent(session_id="s2"),
            MessageEvent(session_id="s3"),
            ToolUseEvent(session_id="s4"),
            ToolResultEvent(session_id="s5"),
            ProgressEvent(session_id="s6"),
            CompletedEvent(session_id="s7"),
            ErrorEvent(session_id="s8"),
            # Original events
            SubagentSpawnEvent(session_id="s9"),
            SubagentCompleteEvent(session_id="s10"),
            SkillInvokeEvent(session_id="s11"),
            SkillCompleteEvent(session_id="s12"),
            CostUpdateEvent(session_id="s13"),
        ]

        for event in events:
            data = event.to_dict()
            assert "timestamp" in data
            assert data["timestamp"] is not None

    def test_all_events_have_session_id(self):
        """Test all event types include session_id."""
        events = [
            # Enterprise-App events
            StartedEvent(session_id="session-1"),
            ThinkingEvent(session_id="session-2"),
            MessageEvent(session_id="session-3"),
            ToolUseEvent(session_id="session-4"),
            ToolResultEvent(session_id="session-5"),
            ProgressEvent(session_id="session-6"),
            CompletedEvent(session_id="session-7"),
            ErrorEvent(session_id="session-8"),
            # Original events
            SubagentSpawnEvent(session_id="session-9"),
            SubagentCompleteEvent(session_id="session-10"),
            SkillInvokeEvent(session_id="session-11"),
            SkillCompleteEvent(session_id="session-12"),
            CostUpdateEvent(session_id="session-13"),
        ]

        for event in events:
            data = event.to_dict()
            assert "session_id" in data

    def test_all_events_have_event_type_as_string(self):
        """Test all event types serialize event_type as string."""
        events = [
            # Enterprise-App events
            StartedEvent(session_id="s1"),
            ThinkingEvent(session_id="s2"),
            MessageEvent(session_id="s3"),
            ToolUseEvent(session_id="s4"),
            ToolResultEvent(session_id="s5"),
            ProgressEvent(session_id="s6"),
            CompletedEvent(session_id="s7"),
            ErrorEvent(session_id="s8"),
            # Original events
            SubagentSpawnEvent(session_id="s9"),
            SubagentCompleteEvent(session_id="s10"),
            SkillInvokeEvent(session_id="s11"),
            SkillCompleteEvent(session_id="s12"),
            CostUpdateEvent(session_id="s13"),
        ]

        for event in events:
            data = event.to_dict()
            assert isinstance(data["event_type"], str)

    def test_enterprise_app_event_type_values(self):
        """Test Enterprise-App event types have correct string values."""
        event_type_mapping = {
            StartedEvent: "started",
            ThinkingEvent: "thinking",
            MessageEvent: "message",
            ToolUseEvent: "tool_use",
            ToolResultEvent: "tool_result",
            ProgressEvent: "progress",
            CompletedEvent: "completed",
            ErrorEvent: "error",
        }

        for event_class, expected_type in event_type_mapping.items():
            event = event_class(session_id="test")
            data = event.to_dict()
            assert (
                data["event_type"] == expected_type
            ), f"{event_class.__name__} has wrong event_type"

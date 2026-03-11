"""
Unit Tests for Session State Models (Tier 1)

Tests the session state dataclasses and enums.
Part of TODO-204 Enterprise-App Streaming Integration.

Coverage:
- SessionStatus enum
- Message dataclass
- ToolInvocation dataclass
- SubagentCall dataclass
- SessionState dataclass
- SessionSummary dataclass
"""

from datetime import datetime, timezone

import pytest

from kaizen.session.state import (
    Message,
    SessionState,
    SessionStatus,
    SessionSummary,
    SubagentCall,
    ToolInvocation,
)


class TestSessionStatus:
    """Test SessionStatus enum."""

    def test_status_values(self):
        """Test all status values exist."""
        assert SessionStatus.ACTIVE.value == "active"
        assert SessionStatus.PAUSED.value == "paused"
        assert SessionStatus.COMPLETED.value == "completed"
        assert SessionStatus.FAILED.value == "failed"
        assert SessionStatus.INTERRUPTED.value == "interrupted"

    def test_status_count(self):
        """Test that we have exactly 5 statuses."""
        assert len(SessionStatus) == 5


class TestMessage:
    """Test Message dataclass."""

    def test_default_values(self):
        """Test default values."""
        msg = Message(role="user", content="Hello")

        assert msg.role == "user"
        assert msg.content == "Hello"
        assert msg.timestamp is not None
        assert msg.metadata == {}

    def test_custom_values(self):
        """Test custom values."""
        ts = datetime.now(timezone.utc).isoformat()
        msg = Message(
            role="assistant",
            content="Response",
            timestamp=ts,
            metadata={"tokens": 50},
        )

        assert msg.role == "assistant"
        assert msg.content == "Response"
        assert msg.timestamp == ts
        assert msg.metadata == {"tokens": 50}

    def test_to_dict(self):
        """Test serialization to dict."""
        msg = Message(
            role="user",
            content="Hello",
        )

        data = msg.to_dict()

        assert data["role"] == "user"
        assert data["content"] == "Hello"
        assert "timestamp" in data

    def test_from_dict(self):
        """Test deserialization from dict."""
        data = {
            "role": "assistant",
            "content": "World",
            "timestamp": "2024-01-01T00:00:00Z",
            "metadata": {"key": "value"},
        }

        msg = Message.from_dict(data)

        assert msg.role == "assistant"
        assert msg.content == "World"
        assert msg.timestamp == "2024-01-01T00:00:00Z"
        assert msg.metadata == {"key": "value"}


class TestToolInvocation:
    """Test ToolInvocation dataclass."""

    def test_default_values(self):
        """Test default values."""
        tool = ToolInvocation(
            tool_name="search",
            tool_call_id="call-123",
            input={"query": "test"},
        )

        assert tool.tool_name == "search"
        assert tool.tool_call_id == "call-123"
        assert tool.input == {"query": "test"}
        assert tool.output is None
        assert tool.error is None
        assert tool.duration_ms == 0
        assert tool.started_at is not None

    def test_successful_invocation(self):
        """Test successful tool invocation."""
        tool = ToolInvocation(
            tool_name="calculator",
            tool_call_id="call-456",
            input={"expression": "2+2"},
            output={"result": 4},
            duration_ms=10,
        )

        assert tool.output == {"result": 4}
        assert tool.error is None
        assert tool.duration_ms == 10

    def test_failed_invocation(self):
        """Test failed tool invocation."""
        tool = ToolInvocation(
            tool_name="http_get",
            tool_call_id="call-789",
            input={"url": "http://invalid"},
            error="Connection failed",
            duration_ms=5000,
        )

        assert tool.output is None
        assert tool.error == "Connection failed"

    def test_to_dict(self):
        """Test serialization."""
        tool = ToolInvocation(
            tool_name="search",
            tool_call_id="call-001",
            input={"q": "test"},
            output={"results": []},
        )

        data = tool.to_dict()

        assert data["tool_name"] == "search"
        assert data["tool_call_id"] == "call-001"
        assert data["input"] == {"q": "test"}
        assert data["output"] == {"results": []}

    def test_from_dict(self):
        """Test deserialization."""
        data = {
            "tool_name": "http_post",
            "tool_call_id": "call-xyz",
            "input": {"url": "http://example.com"},
            "output": {"status": 200},
            "error": None,
            "duration_ms": 150,
            "started_at": "2024-01-01T00:00:00Z",
        }

        tool = ToolInvocation.from_dict(data)

        assert tool.tool_name == "http_post"
        assert tool.duration_ms == 150
        assert tool.tool_call_id == "call-xyz"


class TestSubagentCall:
    """Test SubagentCall dataclass."""

    def test_default_values(self):
        """Test default values."""
        call = SubagentCall(
            subagent_id="sub-agent-001",
            subagent_name="DataAnalyzer",
            task="Analyze data",
            parent_agent_id="parent-001",
            trust_chain_id="chain-abc",
        )

        assert call.subagent_id == "sub-agent-001"
        assert call.subagent_name == "DataAnalyzer"
        assert call.task == "Analyze data"
        assert call.status == "running"
        assert call.output is None
        assert call.duration_ms == 0

    def test_completed_call(self):
        """Test completed subagent call."""
        call = SubagentCall(
            subagent_id="sub-001",
            subagent_name="Summarizer",
            task="Summarize document",
            parent_agent_id="parent-001",
            trust_chain_id="chain-abc",
            status="completed",
            output="Document is about X",
            duration_ms=2500,
        )

        assert call.status == "completed"
        assert call.output == "Document is about X"
        assert call.duration_ms == 2500

    def test_failed_call(self):
        """Test subagent call with error status."""
        call = SubagentCall(
            subagent_id="sub-002",
            subagent_name="Translator",
            task="Translate to French",
            parent_agent_id="parent-001",
            trust_chain_id="chain-abc",
            status="error",
        )

        assert call.status == "error"
        assert call.output is None

    def test_to_dict(self):
        """Test serialization."""
        call = SubagentCall(
            subagent_id="sub-003",
            subagent_name="Validator",
            task="Validate schema",
            parent_agent_id="parent-001",
            trust_chain_id="chain-abc",
            status="completed",
        )

        data = call.to_dict()

        assert data["subagent_id"] == "sub-003"
        assert data["subagent_name"] == "Validator"
        assert data["task"] == "Validate schema"
        assert data["status"] == "completed"

    def test_from_dict(self):
        """Test deserialization."""
        data = {
            "subagent_id": "sub-004",
            "subagent_name": "Extractor",
            "task": "Extract entities",
            "parent_agent_id": "parent-001",
            "trust_chain_id": "chain-xyz",
            "status": "running",
            "output": None,
            "duration_ms": 100,
            "started_at": "2024-01-01T00:00:00Z",
        }

        call = SubagentCall.from_dict(data)

        assert call.subagent_id == "sub-004"
        assert call.status == "running"


class TestSessionState:
    """Test SessionState dataclass."""

    def test_default_values(self):
        """Test default values."""
        state = SessionState(
            session_id="session-123",
            agent_id="agent-001",
            trust_chain_id="chain-abc",
        )

        assert state.session_id == "session-123"
        assert state.agent_id == "agent-001"
        assert state.trust_chain_id == "chain-abc"
        assert state.status == SessionStatus.ACTIVE
        assert state.messages == []
        assert state.tool_invocations == []
        assert state.subagent_calls == []
        assert state.tokens_used == 0
        assert state.cost_usd == 0.0

    def test_add_message(self):
        """Test adding messages."""
        state = SessionState(
            session_id="session-123",
            agent_id="agent-001",
            trust_chain_id="chain-abc",
        )

        msg = Message(role="user", content="Hello")
        state.add_message(msg)

        assert len(state.messages) == 1
        assert state.messages[0].content == "Hello"

    def test_add_tool_invocation(self):
        """Test adding tool invocations."""
        state = SessionState(
            session_id="session-123",
            agent_id="agent-001",
            trust_chain_id="chain-abc",
        )

        tool = ToolInvocation(
            tool_name="search",
            tool_call_id="call-123",
            input={"q": "test"},
        )
        state.add_tool_invocation(tool)

        assert len(state.tool_invocations) == 1
        assert state.tool_invocations[0].tool_name == "search"

    def test_add_subagent_call(self):
        """Test adding subagent calls."""
        state = SessionState(
            session_id="session-123",
            agent_id="agent-001",
            trust_chain_id="chain-abc",
        )

        call = SubagentCall(
            subagent_id="sub-001",
            subagent_name="Helper",
            task="Help",
            parent_agent_id="agent-001",
            trust_chain_id="chain-abc",
        )
        state.add_subagent_call(call)

        assert len(state.subagent_calls) == 1
        assert state.subagent_calls[0].subagent_name == "Helper"

    def test_update_metrics(self):
        """Test updating metrics."""
        state = SessionState(
            session_id="session-123",
            agent_id="agent-001",
            trust_chain_id="chain-abc",
        )

        state.update_metrics(tokens_added=100, cost_added_usd=0.01, cycles_added=1)

        assert state.tokens_used == 100
        assert state.cost_usd == 0.01
        assert state.cycles_used == 1

        # Accumulate
        state.update_metrics(tokens_added=50, cost_added_usd=0.005)

        assert state.tokens_used == 150
        assert state.cost_usd == 0.015

    def test_to_dict(self):
        """Test serialization."""
        state = SessionState(
            session_id="session-123",
            agent_id="agent-001",
            trust_chain_id="chain-abc",
            tokens_used=500,
        )

        data = state.to_dict()

        assert data["session_id"] == "session-123"
        assert data["agent_id"] == "agent-001"
        assert data["trust_chain_id"] == "chain-abc"
        assert data["status"] == "active"
        assert data["tokens_used"] == 500

    def test_from_dict(self):
        """Test deserialization."""
        data = {
            "session_id": "session-456",
            "agent_id": "agent-002",
            "trust_chain_id": "chain-xyz",
            "status": "paused",
            "messages": [],
            "tool_invocations": [],
            "subagent_calls": [],
            "tokens_used": 1000,
            "cost_usd": 0.05,
            "cycles_used": 3,
            "started_at": "2024-01-01T00:00:00Z",
            "metadata": {},
        }

        state = SessionState.from_dict(data)

        assert state.session_id == "session-456"
        assert state.status == SessionStatus.PAUSED
        assert state.tokens_used == 1000

    def test_cost_usd_cents(self):
        """Test cost_usd_cents property."""
        state = SessionState(
            session_id="session-123",
            agent_id="agent-001",
            trust_chain_id="chain-abc",
        )
        state.cost_usd = 0.05

        assert state.cost_usd_cents == 5

    def test_duration_ms(self):
        """Test duration_ms property."""
        state = SessionState(
            session_id="session-123",
            agent_id="agent-001",
            trust_chain_id="chain-abc",
        )

        # Duration should be non-negative
        assert state.duration_ms >= 0


class TestSessionSummary:
    """Test SessionSummary dataclass."""

    def test_from_session_state(self):
        """Test creation from SessionState."""
        state = SessionState(
            session_id="session-789",
            agent_id="agent-003",
            trust_chain_id="chain-123",
            status=SessionStatus.COMPLETED,
            tokens_used=2000,
            cost_usd=0.15,
            cycles_used=5,
        )

        # Add some data
        state.add_message(Message(role="user", content="Hello"))
        state.add_message(Message(role="assistant", content="Hi"))
        state.add_tool_invocation(
            ToolInvocation(
                tool_name="search",
                tool_call_id="call-001",
                input={},
            )
        )

        summary = SessionSummary.from_session_state(state)

        assert summary.session_id == "session-789"
        assert summary.agent_id == "agent-003"
        assert summary.status == SessionStatus.COMPLETED
        assert summary.total_tokens == 2000
        assert summary.total_cost_usd == 0.15
        assert summary.total_messages == 2
        assert summary.total_tool_calls == 1
        assert summary.total_subagent_calls == 0

    def test_from_session_state_with_output(self):
        """Test creation with final output."""
        state = SessionState(
            session_id="session-xyz",
            agent_id="agent-abc",
            trust_chain_id="chain-abc",
            status=SessionStatus.COMPLETED,
        )

        summary = SessionSummary.from_session_state(
            state,
            final_output="Task completed successfully",
        )

        assert summary.final_output == "Task completed successfully"
        assert summary.error_message is None

    def test_from_session_state_with_error(self):
        """Test creation with error message."""
        state = SessionState(
            session_id="session-err",
            agent_id="agent-err",
            trust_chain_id="chain-err",
            status=SessionStatus.FAILED,
        )

        summary = SessionSummary.from_session_state(
            state,
            error_message="Model error occurred",
        )

        assert summary.status == SessionStatus.FAILED
        assert summary.error_message == "Model error occurred"

    def test_to_dict(self):
        """Test serialization."""
        state = SessionState(
            session_id="session-xyz",
            agent_id="agent-abc",
            trust_chain_id="chain-abc",
            status=SessionStatus.FAILED,
            tokens_used=500,
            cost_usd=0.025,
        )
        state.add_message(Message(role="user", content="Test"))

        summary = SessionSummary.from_session_state(
            state,
            error_message="Model error",
        )

        data = summary.to_dict()

        assert data["session_id"] == "session-xyz"
        assert data["status"] == "failed"
        assert data["total_tokens"] == 500
        assert data["total_messages"] == 1
        assert data["error_message"] == "Model error"

    def test_total_cost_cents(self):
        """Test cost conversion."""
        state = SessionState(
            session_id="session-123",
            agent_id="agent-001",
            trust_chain_id="chain-abc",
            status=SessionStatus.COMPLETED,
            cost_usd=0.15,
        )

        summary = SessionSummary.from_session_state(state)

        assert summary.total_cost_cents == 15

"""
Unit Tests for Runtime Context Types (Tier 1)

Tests ExecutionStatus, ToolCallRecord, ExecutionContext, and ExecutionResult.

Coverage:
- Enum values and behavior
- Dataclass creation and validation
- Serialization (to_dict, from_dict)
- Factory methods
- Helper methods
"""

from datetime import datetime

import pytest

from kaizen.runtime.context import (
    ExecutionContext,
    ExecutionResult,
    ExecutionStatus,
    ToolCallRecord,
)


class TestExecutionStatus:
    """Test ExecutionStatus enum."""

    def test_all_statuses_exist(self):
        """Test all expected statuses are defined."""
        assert ExecutionStatus.COMPLETE.value == "complete"
        assert ExecutionStatus.INTERRUPTED.value == "interrupted"
        assert ExecutionStatus.ERROR.value == "error"
        assert ExecutionStatus.MAX_CYCLES.value == "max_cycles"
        assert ExecutionStatus.BUDGET_EXCEEDED.value == "budget_exceeded"
        assert ExecutionStatus.TIMEOUT.value == "timeout"
        assert ExecutionStatus.PENDING.value == "pending"

    def test_status_count(self):
        """Test expected number of statuses."""
        statuses = list(ExecutionStatus)
        assert len(statuses) == 7


class TestToolCallRecord:
    """Test ToolCallRecord dataclass."""

    def test_create_basic_record(self):
        """Test creating a basic tool call record."""
        record = ToolCallRecord(
            name="read_file",
            arguments={"path": "/tmp/file.txt"},
        )

        assert record.name == "read_file"
        assert record.arguments == {"path": "/tmp/file.txt"}
        assert record.status == "pending"
        assert record.result is None
        assert record.timestamp is not None

    def test_create_completed_record(self):
        """Test creating a completed record."""
        record = ToolCallRecord(
            name="bash_command",
            arguments={"command": "ls -la"},
            result="file1.txt\nfile2.txt",
            status="executed",
            duration_ms=150.5,
        )

        assert record.status == "executed"
        assert record.result == "file1.txt\nfile2.txt"
        assert record.duration_ms == 150.5

    def test_create_error_record(self):
        """Test creating an error record."""
        record = ToolCallRecord(
            name="web_fetch",
            arguments={"url": "https://example.com"},
            status="error",
            error="Connection timeout",
        )

        assert record.status == "error"
        assert record.error == "Connection timeout"

    def test_to_dict(self):
        """Test serialization to dictionary."""
        record = ToolCallRecord(
            name="test_tool",
            arguments={"param": "value"},
            result="output",
            status="executed",
            duration_ms=100.0,
        )

        data = record.to_dict()

        assert data["name"] == "test_tool"
        assert data["arguments"] == {"param": "value"}
        assert data["result"] == "output"
        assert data["status"] == "executed"
        assert data["duration_ms"] == 100.0
        assert "timestamp" in data

    def test_from_dict(self):
        """Test deserialization from dictionary."""
        data = {
            "name": "my_tool",
            "arguments": {"a": 1},
            "result": "done",
            "status": "executed",
            "duration_ms": 50.0,
            "timestamp": "2024-01-01T12:00:00",
        }

        record = ToolCallRecord.from_dict(data)

        assert record.name == "my_tool"
        assert record.arguments == {"a": 1}
        assert record.result == "done"
        assert record.status == "executed"
        assert record.duration_ms == 50.0


class TestExecutionContext:
    """Test ExecutionContext dataclass."""

    def test_create_minimal_context(self):
        """Test creating context with minimal required fields."""
        context = ExecutionContext(task="List files")

        assert context.task == "List files"
        assert context.session_id != ""  # Auto-generated
        assert context.tools == []
        assert context.max_cycles == 50
        assert context.permission_mode == "auto"

    def test_create_full_context(self):
        """Test creating context with all fields."""
        context = ExecutionContext(
            task="Process data",
            session_id="test-session-123",
            tools=[{"name": "read_file", "type": "function"}],
            memory_context="Previous context here",
            system_prompt="You are a helpful assistant",
            conversation_history=[{"role": "user", "content": "Hello"}],
            max_cycles=100,
            max_tokens=4096,
            budget_usd=0.50,
            timeout_seconds=300.0,
            permission_mode="confirm_all",
            pre_approved_tools=["read_file", "glob"],
            preferred_model="claude-3-opus",
            preferred_runtime="kaizen_local",
            metadata={"custom": "data"},
        )

        assert context.session_id == "test-session-123"
        assert len(context.tools) == 1
        assert context.max_tokens == 4096
        assert context.budget_usd == 0.50
        assert context.preferred_model == "claude-3-opus"

    def test_has_budget_constraints(self):
        """Test has_budget_constraints method."""
        # No constraints
        context1 = ExecutionContext(task="Test")
        assert context1.has_budget_constraints() is False

        # With token limit
        context2 = ExecutionContext(task="Test", max_tokens=1000)
        assert context2.has_budget_constraints() is True

        # With budget
        context3 = ExecutionContext(task="Test", budget_usd=1.0)
        assert context3.has_budget_constraints() is True

        # With timeout
        context4 = ExecutionContext(task="Test", timeout_seconds=60.0)
        assert context4.has_budget_constraints() is True

    def test_has_tool_requirements(self):
        """Test has_tool_requirements method."""
        # No tools
        context1 = ExecutionContext(task="Test")
        assert context1.has_tool_requirements() is False

        # With tools
        context2 = ExecutionContext(
            task="Test",
            tools=[{"name": "read_file"}],
        )
        assert context2.has_tool_requirements() is True

    def test_requires_capability_from_task(self):
        """Test capability detection from task text."""
        # Vision requirement
        context1 = ExecutionContext(task="Analyze this image")
        assert context1.requires_capability("vision") is True

        # File access requirement
        context2 = ExecutionContext(task="Read the config file")
        assert context2.requires_capability("file_access") is True

        # Web access requirement
        context3 = ExecutionContext(task="Fetch data from URL")
        assert context3.requires_capability("web_access") is True

        # No specific requirement
        context4 = ExecutionContext(task="Tell me a joke")
        assert context4.requires_capability("vision") is False

    def test_to_dict(self):
        """Test serialization."""
        context = ExecutionContext(
            task="Test task",
            session_id="session-1",
            max_cycles=20,
        )

        data = context.to_dict()

        assert data["task"] == "Test task"
        assert data["session_id"] == "session-1"
        assert data["max_cycles"] == 20

    def test_from_dict(self):
        """Test deserialization."""
        data = {
            "task": "Do something",
            "session_id": "abc-123",
            "tools": [{"name": "tool1"}],
            "max_cycles": 30,
        }

        context = ExecutionContext.from_dict(data)

        assert context.task == "Do something"
        assert context.session_id == "abc-123"
        assert len(context.tools) == 1
        assert context.max_cycles == 30


class TestExecutionResult:
    """Test ExecutionResult dataclass."""

    def test_create_successful_result(self):
        """Test creating a successful result."""
        result = ExecutionResult(
            output="Task completed successfully",
            status=ExecutionStatus.COMPLETE,
            tokens_used=500,
            cost_usd=0.015,
            cycles_used=3,
            duration_ms=1500.0,
            runtime_name="kaizen_local",
            model_used="claude-3-sonnet",
            session_id="session-1",
        )

        assert result.is_success is True
        assert result.is_error is False
        assert result.output == "Task completed successfully"
        assert result.tokens_used == 500

    def test_create_error_result(self):
        """Test creating an error result."""
        result = ExecutionResult(
            output="",
            status=ExecutionStatus.ERROR,
            error_message="Connection failed",
            error_type="ConnectionError",
        )

        assert result.is_success is False
        assert result.is_error is True
        assert result.error_message == "Connection failed"

    def test_create_with_tool_calls(self):
        """Test result with tool calls."""
        tool_calls = [
            ToolCallRecord(
                name="read_file",
                arguments={"path": "/tmp/file.txt"},
                result="content",
                status="executed",
            ),
            ToolCallRecord(
                name="write_file",
                arguments={"path": "/tmp/out.txt"},
                status="denied",
            ),
        ]

        result = ExecutionResult(
            output="Done",
            status=ExecutionStatus.COMPLETE,
            tool_calls=tool_calls,
        )

        assert len(result.tool_calls) == 2
        assert len(result.get_successful_tool_calls()) == 1
        assert len(result.get_failed_tool_calls()) == 1

    def test_from_error_factory(self):
        """Test from_error factory method."""
        exc = ValueError("Invalid input")

        result = ExecutionResult.from_error(
            error=exc,
            runtime_name="test_runtime",
            session_id="session-1",
            duration_ms=100.0,
        )

        assert result.is_error is True
        assert result.error_message == "Invalid input"
        assert result.error_type == "ValueError"
        assert result.runtime_name == "test_runtime"

    def test_from_success_factory(self):
        """Test from_success factory method."""
        result = ExecutionResult.from_success(
            output="All done",
            runtime_name="kaizen_local",
            model_used="claude-3",
            tokens_used=100,
        )

        assert result.is_success is True
        assert result.output == "All done"
        assert result.runtime_name == "kaizen_local"
        assert result.tokens_used == 100

    def test_to_dict(self):
        """Test serialization."""
        result = ExecutionResult(
            output="Test output",
            status=ExecutionStatus.COMPLETE,
            tokens_used=200,
            runtime_name="test",
        )

        data = result.to_dict()

        assert data["output"] == "Test output"
        assert data["status"] == "complete"
        assert data["tokens_used"] == 200

    def test_from_dict(self):
        """Test deserialization."""
        data = {
            "output": "Result",
            "status": "complete",
            "tokens_used": 150,
            "runtime_name": "my_runtime",
            "tool_calls": [{"name": "tool1", "arguments": {}, "status": "executed"}],
        }

        result = ExecutionResult.from_dict(data)

        assert result.output == "Result"
        assert result.status == ExecutionStatus.COMPLETE
        assert result.tokens_used == 150
        assert len(result.tool_calls) == 1


class TestExecutionStatusValues:
    """Test different execution status scenarios."""

    def test_all_termination_reasons(self):
        """Test results with different termination reasons."""
        # Normal completion
        r1 = ExecutionResult(output="Done", status=ExecutionStatus.COMPLETE)
        assert r1.is_success is True

        # User interruption
        r2 = ExecutionResult(output="Stopped", status=ExecutionStatus.INTERRUPTED)
        assert r2.is_success is False
        assert r2.is_error is False

        # Max cycles
        r3 = ExecutionResult(output="Partial", status=ExecutionStatus.MAX_CYCLES)
        assert r3.is_success is False

        # Budget exceeded
        r4 = ExecutionResult(output="", status=ExecutionStatus.BUDGET_EXCEEDED)
        assert r4.is_success is False

        # Timeout
        r5 = ExecutionResult(output="", status=ExecutionStatus.TIMEOUT)
        assert r5.is_success is False

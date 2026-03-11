"""
Unit Tests for AgentResult (Tier 1)

Tests the AgentResult dataclass for execution results:
- ToolCallRecord creation and properties
- AgentResult creation and properties
- Convenience accessors
- Serialization
- Factory methods
"""

import pytest

from kaizen.api.result import AgentResult, ResultStatus, ToolCallRecord


class TestResultStatus:
    """Tests for ResultStatus enum."""

    def test_all_statuses_exist(self):
        """Test all statuses exist."""
        assert ResultStatus.SUCCESS
        assert ResultStatus.ERROR
        assert ResultStatus.TIMEOUT
        assert ResultStatus.INTERRUPTED
        assert ResultStatus.PARTIAL
        assert ResultStatus.PENDING

    def test_status_values(self):
        """Test status values."""
        assert ResultStatus.SUCCESS.value == "success"
        assert ResultStatus.ERROR.value == "error"
        assert ResultStatus.TIMEOUT.value == "timeout"


class TestToolCallRecord:
    """Tests for ToolCallRecord dataclass."""

    def test_create_success(self):
        """Test creating a successful tool call record."""
        record = ToolCallRecord(
            name="read",
            arguments={"path": "test.txt"},
            result="file contents",
            duration_ms=50,
        )

        assert record.name == "read"
        assert record.arguments == {"path": "test.txt"}
        assert record.result == "file contents"
        assert record.error is None
        assert record.succeeded is True

    def test_create_failure(self):
        """Test creating a failed tool call record."""
        record = ToolCallRecord(
            name="read",
            arguments={"path": "nonexistent.txt"},
            error="File not found",
            duration_ms=10,
        )

        assert record.name == "read"
        assert record.error == "File not found"
        assert record.succeeded is False

    def test_to_dict(self):
        """Test serialization to dict."""
        record = ToolCallRecord(
            name="write",
            arguments={"path": "out.txt", "content": "data"},
            result=True,
            duration_ms=100,
            cycle=5,
        )

        data = record.to_dict()

        assert data["name"] == "write"
        assert data["arguments"]["path"] == "out.txt"
        assert data["result"] is True
        assert data["duration_ms"] == 100
        assert data["cycle"] == 5
        assert data["succeeded"] is True

    def test_from_dict(self):
        """Test creation from dict."""
        data = {
            "name": "bash",
            "arguments": {"command": "ls"},
            "result": "file1\nfile2",
            "duration_ms": 200,
        }

        record = ToolCallRecord.from_dict(data)

        assert record.name == "bash"
        assert record.result == "file1\nfile2"
        assert record.succeeded is True

    def test_str_representation(self):
        """Test string representation."""
        record = ToolCallRecord(name="read", arguments={"path": "test.txt"})
        s = str(record)
        assert "read" in s
        assert "✓" in s  # Success indicator


class TestAgentResultCreation:
    """Tests for AgentResult creation."""

    def test_create_default(self):
        """Test creating with defaults."""
        result = AgentResult()

        assert result.text == ""
        assert result.status == ResultStatus.SUCCESS
        assert result.tool_calls == []
        assert result.cost == 0.0
        assert result.cycles == 0

    def test_create_full(self):
        """Test creating with all parameters."""
        tool_call = ToolCallRecord(name="read", arguments={}, result="data")
        result = AgentResult(
            text="Response text",
            status=ResultStatus.SUCCESS,
            tool_calls=[tool_call],
            tokens={"input": 100, "output": 50, "total": 150},
            cost=0.005,
            cycles=3,
            turns=2,
            duration_ms=500,
            session_id="sess-123",
            run_id="run-456",
            model_used="gpt-4",
            provider_used="openai",
            metadata={"key": "value"},
        )

        assert result.text == "Response text"
        assert result.status == ResultStatus.SUCCESS
        assert len(result.tool_calls) == 1
        assert result.cost == 0.005
        assert result.cycles == 3
        assert result.session_id == "sess-123"
        assert result.model_used == "gpt-4"


class TestAgentResultProperties:
    """Tests for AgentResult properties."""

    def test_succeeded(self):
        """Test succeeded property."""
        success = AgentResult(status=ResultStatus.SUCCESS)
        error = AgentResult(status=ResultStatus.ERROR)

        assert success.succeeded is True
        assert error.succeeded is False

    def test_failed(self):
        """Test failed property."""
        success = AgentResult(status=ResultStatus.SUCCESS)
        error = AgentResult(status=ResultStatus.ERROR)
        timeout = AgentResult(status=ResultStatus.TIMEOUT)

        assert success.failed is False
        assert error.failed is True
        assert timeout.failed is True

    def test_was_interrupted(self):
        """Test was_interrupted property."""
        normal = AgentResult(status=ResultStatus.SUCCESS)
        interrupted = AgentResult(status=ResultStatus.INTERRUPTED)

        assert normal.was_interrupted is False
        assert interrupted.was_interrupted is True

    def test_token_properties(self):
        """Test token count properties."""
        result = AgentResult(tokens={"input": 100, "output": 50, "total": 150})

        assert result.input_tokens == 100
        assert result.output_tokens == 50
        assert result.total_tokens == 150

    def test_total_tokens_calculated(self):
        """Test total_tokens is calculated if not provided."""
        result = AgentResult(tokens={"input": 100, "output": 50, "total": 0})

        assert result.total_tokens == 150

    def test_duration_seconds(self):
        """Test duration_seconds property."""
        result = AgentResult(duration_ms=1500)

        assert result.duration_seconds == 1.5


class TestAgentResultToolCallHelpers:
    """Tests for tool call helper methods."""

    def test_tool_call_count(self):
        """Test tool_call_count property."""
        result = AgentResult(
            tool_calls=[
                ToolCallRecord(name="read", arguments={}),
                ToolCallRecord(name="write", arguments={}),
                ToolCallRecord(name="read", arguments={}),
            ]
        )

        assert result.tool_call_count == 3

    def test_successful_tool_calls(self):
        """Test successful_tool_calls property."""
        result = AgentResult(
            tool_calls=[
                ToolCallRecord(name="read", arguments={}, result="data"),
                ToolCallRecord(name="write", arguments={}, error="Permission denied"),
                ToolCallRecord(name="glob", arguments={}, result=["file1"]),
            ]
        )

        successful = result.successful_tool_calls
        assert len(successful) == 2
        assert successful[0].name == "read"
        assert successful[1].name == "glob"

    def test_failed_tool_calls(self):
        """Test failed_tool_calls property."""
        result = AgentResult(
            tool_calls=[
                ToolCallRecord(name="read", arguments={}, result="data"),
                ToolCallRecord(name="write", arguments={}, error="Permission denied"),
            ]
        )

        failed = result.failed_tool_calls
        assert len(failed) == 1
        assert failed[0].name == "write"

    def test_get_tool_calls_by_name(self):
        """Test get_tool_calls_by_name method."""
        result = AgentResult(
            tool_calls=[
                ToolCallRecord(name="read", arguments={"path": "a.txt"}),
                ToolCallRecord(name="write", arguments={"path": "b.txt"}),
                ToolCallRecord(name="read", arguments={"path": "c.txt"}),
            ]
        )

        read_calls = result.get_tool_calls_by_name("read")
        assert len(read_calls) == 2
        assert read_calls[0].arguments["path"] == "a.txt"
        assert read_calls[1].arguments["path"] == "c.txt"

    def test_get_last_tool_call(self):
        """Test get_last_tool_call method."""
        result = AgentResult(
            tool_calls=[
                ToolCallRecord(name="read", arguments={}),
                ToolCallRecord(name="write", arguments={}),
            ]
        )

        last = result.get_last_tool_call()
        assert last.name == "write"

    def test_get_last_tool_call_empty(self):
        """Test get_last_tool_call with no tool calls."""
        result = AgentResult()

        last = result.get_last_tool_call()
        assert last is None

    def test_get_tool_results(self):
        """Test get_tool_results method."""
        result = AgentResult(
            tool_calls=[
                ToolCallRecord(name="read", arguments={}, result="data1"),
                ToolCallRecord(name="read", arguments={}, result="data2"),
                ToolCallRecord(name="write", arguments={}, error="failed"),
            ]
        )

        all_results = result.get_tool_results()
        assert len(all_results) == 2
        assert "data1" in all_results
        assert "data2" in all_results

        read_results = result.get_tool_results("read")
        assert len(read_results) == 2


class TestAgentResultSerialization:
    """Tests for serialization."""

    def test_to_dict(self):
        """Test to_dict method."""
        result = AgentResult(
            text="Response",
            status=ResultStatus.SUCCESS,
            tool_calls=[ToolCallRecord(name="read", arguments={})],
            tokens={"input": 100, "output": 50, "total": 150},
            cost=0.01,
            session_id="sess-123",
        )

        data = result.to_dict()

        assert data["text"] == "Response"
        assert data["status"] == "success"
        assert len(data["tool_calls"]) == 1
        assert data["tokens"]["input"] == 100
        assert data["cost"] == 0.01
        assert data["session_id"] == "sess-123"

    def test_from_dict(self):
        """Test from_dict method."""
        data = {
            "text": "Result text",
            "status": "error",
            "error": "Something went wrong",
            "tool_calls": [{"name": "bash", "arguments": {}}],
            "cost": 0.05,
        }

        result = AgentResult.from_dict(data)

        assert result.text == "Result text"
        assert result.status == ResultStatus.ERROR
        assert result.error == "Something went wrong"
        assert len(result.tool_calls) == 1

    def test_to_json(self):
        """Test to_json method."""
        result = AgentResult(text="Test", status=ResultStatus.SUCCESS)

        json_str = result.to_json()

        assert '"text": "Test"' in json_str
        assert '"status": "success"' in json_str

    def test_from_json(self):
        """Test from_json method."""
        json_str = '{"text": "Test", "status": "success", "cost": 0.01}'

        result = AgentResult.from_json(json_str)

        assert result.text == "Test"
        assert result.status == ResultStatus.SUCCESS
        assert result.cost == 0.01

    def test_roundtrip(self):
        """Test roundtrip serialization."""
        original = AgentResult(
            text="Response text",
            status=ResultStatus.SUCCESS,
            tool_calls=[
                ToolCallRecord(
                    name="read", arguments={"path": "test.txt"}, result="data"
                )
            ],
            tokens={"input": 100, "output": 50, "total": 150},
            cost=0.02,
            cycles=5,
            session_id="sess-123",
        )

        data = original.to_dict()
        restored = AgentResult.from_dict(data)

        assert restored.text == original.text
        assert restored.status == original.status
        assert len(restored.tool_calls) == len(original.tool_calls)
        assert restored.cost == original.cost


class TestAgentResultFactoryMethods:
    """Tests for factory methods."""

    def test_success_factory(self):
        """Test success factory method."""
        result = AgentResult.success(
            text="Operation completed",
            cost=0.01,
            session_id="sess-123",
        )

        assert result.text == "Operation completed"
        assert result.status == ResultStatus.SUCCESS
        assert result.succeeded is True
        assert result.completed_at != ""

    def test_error_factory(self):
        """Test error factory method."""
        result = AgentResult.from_error(
            error_message="Something failed",
            error_type="RuntimeError",
        )

        assert result.status == ResultStatus.ERROR
        assert result.error == "Something failed"
        assert result.error_type == "RuntimeError"
        assert result.failed is True

    def test_timeout_factory(self):
        """Test timeout factory method."""
        result = AgentResult.timeout(partial_text="Partial response")

        assert result.status == ResultStatus.TIMEOUT
        assert result.text == "Partial response"
        assert result.error == "Execution timed out"

    def test_interrupted_factory(self):
        """Test interrupted factory method."""
        result = AgentResult.interrupted(partial_text="Partial")

        assert result.status == ResultStatus.INTERRUPTED
        assert result.text == "Partial"
        assert result.was_interrupted is True


class TestAgentResultString:
    """Tests for string representation."""

    def test_str_success(self):
        """Test string representation for success."""
        result = AgentResult(
            text="Response text here",
            status=ResultStatus.SUCCESS,
            tokens={"input": 100, "output": 50, "total": 150},
            cost=0.01,
        )

        s = str(result)

        assert "✓" in s  # Success indicator
        assert "success" in s
        assert "150" in s  # Total tokens
        assert "0.01" in s  # Cost

    def test_str_error(self):
        """Test string representation for error."""
        result = AgentResult(
            status=ResultStatus.ERROR,
            error="Failed",
        )

        s = str(result)

        assert "✗" in s  # Error indicator
        assert "error" in s

    def test_str_truncates_long_text(self):
        """Test string representation truncates long text."""
        result = AgentResult(text="a" * 200)

        s = str(result)

        assert "..." in s
        assert len(s) < 300

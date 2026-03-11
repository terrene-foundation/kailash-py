"""
Unit Tests for Subagent Result Types (Tier 1)

Tests the SubagentResult and SkillResult types used by TaskTool and SkillTool.
Part of TODO-203 Task/Skill Tools implementation.

Coverage:
- SubagentResult creation and properties
- SkillResult creation and properties
- Factory methods (from_success, from_error, from_background)
- Serialization and deserialization
"""

from datetime import datetime, timezone

import pytest

from kaizen.execution.subagent_result import SkillResult, SubagentResult


class TestSubagentResult:
    """Test SubagentResult dataclass."""

    def test_minimal_creation(self):
        """Test creating SubagentResult with minimal fields."""
        result = SubagentResult(
            subagent_id="subagent-123",
            output="Test output",
        )

        assert result.subagent_id == "subagent-123"
        assert result.output == "Test output"
        assert result.status == "completed"

    def test_default_values(self):
        """Test default values are set correctly."""
        result = SubagentResult(
            subagent_id="subagent-123",
            output="Test output",
        )

        assert result.tokens_used == 0
        assert result.cost_usd == 0.0
        assert result.cycles_used == 0
        assert result.duration_ms == 0
        assert result.specialist_name is None
        assert result.model_used is None
        assert result.parent_agent_id is None
        assert result.trust_chain_id is None
        assert result.error_message is None
        assert result.error_type is None
        assert result.output_file is None
        assert result.is_background is False
        assert result.tool_calls == []
        assert result.completed_at is None

    def test_full_initialization(self):
        """Test full initialization with all fields."""
        result = SubagentResult(
            subagent_id="subagent-123",
            output="Review complete",
            status="completed",
            tokens_used=500,
            cost_usd=0.005,
            cycles_used=5,
            duration_ms=3000,
            specialist_name="code-reviewer",
            model_used="sonnet",
            parent_agent_id="parent-456",
            trust_chain_id="chain-789",
            tool_calls=[{"name": "read_file", "args": {"path": "test.py"}}],
        )

        assert result.subagent_id == "subagent-123"
        assert result.output == "Review complete"
        assert result.tokens_used == 500
        assert result.cost_usd == 0.005
        assert result.cycles_used == 5
        assert result.duration_ms == 3000
        assert result.specialist_name == "code-reviewer"
        assert result.model_used == "sonnet"
        assert result.parent_agent_id == "parent-456"
        assert result.trust_chain_id == "chain-789"
        assert len(result.tool_calls) == 1


class TestSubagentResultProperties:
    """Test SubagentResult properties."""

    def test_success_property_completed(self):
        """Test success property returns True for completed status."""
        result = SubagentResult(
            subagent_id="subagent-123",
            output="Done",
            status="completed",
        )

        assert result.success is True

    def test_success_property_error(self):
        """Test success property returns False for error status."""
        result = SubagentResult(
            subagent_id="subagent-123",
            output="",
            status="error",
        )

        assert result.success is False

    def test_success_property_interrupted(self):
        """Test success property returns False for interrupted status."""
        result = SubagentResult(
            subagent_id="subagent-123",
            output="",
            status="interrupted",
        )

        assert result.success is False

    def test_is_running_property_running(self):
        """Test is_running property returns True for running status."""
        result = SubagentResult(
            subagent_id="subagent-123",
            output="",
            status="running",
        )

        assert result.is_running is True

    def test_is_running_property_completed(self):
        """Test is_running property returns False for completed status."""
        result = SubagentResult(
            subagent_id="subagent-123",
            output="Done",
            status="completed",
        )

        assert result.is_running is False


class TestSubagentResultFactoryMethods:
    """Test SubagentResult factory methods."""

    def test_from_success(self):
        """Test from_success factory method."""
        result = SubagentResult.from_success(
            subagent_id="subagent-123",
            output="Review complete: 3 issues found",
            tokens_used=500,
            cost_usd=0.005,
            specialist_name="code-reviewer",
        )

        assert result.subagent_id == "subagent-123"
        assert result.output == "Review complete: 3 issues found"
        assert result.status == "completed"
        assert result.tokens_used == 500
        assert result.cost_usd == 0.005
        assert result.specialist_name == "code-reviewer"
        assert result.completed_at is not None

    def test_from_error(self):
        """Test from_error factory method."""
        result = SubagentResult.from_error(
            subagent_id="subagent-123",
            error_message="Execution timeout",
            error_type="TimeoutError",
            specialist_name="code-reviewer",
        )

        assert result.subagent_id == "subagent-123"
        assert result.output == ""
        assert result.status == "error"
        assert result.error_message == "Execution timeout"
        assert result.error_type == "TimeoutError"
        assert result.specialist_name == "code-reviewer"
        assert result.completed_at is not None

    def test_from_background(self):
        """Test from_background factory method."""
        result = SubagentResult.from_background(
            subagent_id="subagent-123",
            output_file="/tmp/output.txt",
            specialist_name="code-reviewer",
            parent_agent_id="parent-456",
            trust_chain_id="chain-789",
        )

        assert result.subagent_id == "subagent-123"
        assert result.output == ""
        assert result.status == "running"
        assert result.is_background is True
        assert result.output_file == "/tmp/output.txt"
        assert result.specialist_name == "code-reviewer"
        assert result.parent_agent_id == "parent-456"
        assert result.trust_chain_id == "chain-789"


class TestSubagentResultSerialization:
    """Test SubagentResult serialization."""

    def test_to_dict(self):
        """Test to_dict method."""
        result = SubagentResult(
            subagent_id="subagent-123",
            output="Review complete",
            status="completed",
            tokens_used=500,
            cost_usd=0.005,
            cycles_used=5,
            duration_ms=3000,
            specialist_name="code-reviewer",
            model_used="sonnet",
            parent_agent_id="parent-456",
            trust_chain_id="chain-789",
            tool_calls=[{"name": "read_file"}],
        )

        data = result.to_dict()

        assert data["subagent_id"] == "subagent-123"
        assert data["output"] == "Review complete"
        assert data["status"] == "completed"
        assert data["tokens_used"] == 500
        assert data["cost_usd"] == 0.005
        assert data["cycles_used"] == 5
        assert data["duration_ms"] == 3000
        assert data["specialist_name"] == "code-reviewer"
        assert data["model_used"] == "sonnet"
        assert data["parent_agent_id"] == "parent-456"
        assert data["trust_chain_id"] == "chain-789"
        assert data["tool_calls"] == [{"name": "read_file"}]
        assert "started_at" in data

    def test_from_dict(self):
        """Test from_dict method."""
        data = {
            "subagent_id": "subagent-123",
            "output": "Review complete",
            "status": "completed",
            "tokens_used": 500,
            "cost_usd": 0.005,
            "cycles_used": 5,
            "duration_ms": 3000,
            "specialist_name": "code-reviewer",
            "model_used": "sonnet",
            "parent_agent_id": "parent-456",
            "trust_chain_id": "chain-789",
            "error_message": None,
            "error_type": None,
            "output_file": None,
            "is_background": False,
            "tool_calls": [],
            "started_at": "2024-01-01T00:00:00+00:00",
            "completed_at": "2024-01-01T00:01:00+00:00",
        }

        result = SubagentResult.from_dict(data)

        assert result.subagent_id == "subagent-123"
        assert result.output == "Review complete"
        assert result.status == "completed"
        assert result.tokens_used == 500

    def test_round_trip_serialization(self):
        """Test to_dict followed by from_dict preserves data."""
        original = SubagentResult.from_success(
            subagent_id="subagent-123",
            output="Test output",
            tokens_used=100,
            cost_usd=0.001,
        )

        data = original.to_dict()
        restored = SubagentResult.from_dict(data)

        assert restored.subagent_id == original.subagent_id
        assert restored.output == original.output
        assert restored.status == original.status
        assert restored.tokens_used == original.tokens_used


class TestSkillResult:
    """Test SkillResult dataclass."""

    def test_minimal_creation(self):
        """Test creating SkillResult with minimal fields."""
        result = SkillResult(skill_name="python-patterns")

        assert result.skill_name == "python-patterns"
        assert result.content == ""
        assert result.success is True

    def test_default_values(self):
        """Test default values are set correctly."""
        result = SkillResult(skill_name="python-patterns")

        assert result.content == ""
        assert result.success is True
        assert result.description is None
        assert result.location is None
        assert result.source is None
        assert result.additional_files == {}
        assert result.error_message is None

    def test_full_initialization(self):
        """Test full initialization with all fields."""
        result = SkillResult(
            skill_name="python-patterns",
            content="# Python Patterns\n\nUse these patterns...",
            success=True,
            description="Python design patterns",
            location="/skills/python-patterns",
            source="builtin",
            additional_files={"examples.md": "# Examples\n\n..."},
        )

        assert result.skill_name == "python-patterns"
        assert "Python Patterns" in result.content
        assert result.success is True
        assert result.description == "Python design patterns"
        assert result.location == "/skills/python-patterns"
        assert result.source == "builtin"
        assert "examples.md" in result.additional_files


class TestSkillResultProperties:
    """Test SkillResult properties."""

    def test_has_additional_files_true(self):
        """Test has_additional_files returns True when files exist."""
        result = SkillResult(
            skill_name="testing-guide",
            content="Guide content",
            additional_files={"tips.md": "Tips content"},
        )

        assert result.has_additional_files is True

    def test_has_additional_files_false(self):
        """Test has_additional_files returns False when no files."""
        result = SkillResult(
            skill_name="simple-skill",
            content="Simple content",
        )

        assert result.has_additional_files is False


class TestSkillResultFactoryMethods:
    """Test SkillResult factory methods."""

    def test_from_success(self):
        """Test from_success factory method."""
        result = SkillResult.from_success(
            skill_name="python-patterns",
            content="# Python Patterns\n\nUse these patterns...",
            description="Python design patterns",
            location="/skills/python-patterns",
            source="builtin",
            additional_files={"examples.md": "Examples content"},
        )

        assert result.skill_name == "python-patterns"
        assert "Python Patterns" in result.content
        assert result.success is True
        assert result.description == "Python design patterns"
        assert result.additional_files["examples.md"] == "Examples content"

    def test_from_error(self):
        """Test from_error factory method."""
        result = SkillResult.from_error(
            skill_name="unknown-skill",
            error_message="Skill not found in registry",
        )

        assert result.skill_name == "unknown-skill"
        assert result.content == ""
        assert result.success is False
        assert result.error_message == "Skill not found in registry"


class TestSkillResultSerialization:
    """Test SkillResult serialization."""

    def test_to_dict(self):
        """Test to_dict method."""
        result = SkillResult(
            skill_name="python-patterns",
            content="# Python Patterns",
            success=True,
            description="Python design patterns",
            location="/skills/python-patterns",
            source="builtin",
            additional_files={"examples.md": "Examples"},
        )

        data = result.to_dict()

        assert data["skill_name"] == "python-patterns"
        assert data["content"] == "# Python Patterns"
        assert data["success"] is True
        assert data["description"] == "Python design patterns"
        assert data["location"] == "/skills/python-patterns"
        assert data["source"] == "builtin"
        assert data["additional_files"] == {"examples.md": "Examples"}

    def test_to_dict_error_result(self):
        """Test to_dict for error result."""
        result = SkillResult.from_error(
            skill_name="unknown-skill",
            error_message="Skill not found",
        )

        data = result.to_dict()

        assert data["skill_name"] == "unknown-skill"
        assert data["success"] is False
        assert data["error_message"] == "Skill not found"


class TestResultIntegration:
    """Test result types integration scenarios."""

    def test_subagent_result_with_all_statuses(self):
        """Test SubagentResult with all possible statuses."""
        statuses = ["completed", "error", "interrupted", "timeout", "running"]

        for status in statuses:
            result = SubagentResult(
                subagent_id=f"subagent-{status}",
                output="",
                status=status,
            )
            assert result.status == status

    def test_skill_result_content_with_special_characters(self):
        """Test SkillResult handles content with special characters."""
        content = """
# Python Patterns 🐍

```python
def example():
    return "Hello, World! 你好"
```

Special chars: < > & " '
        """

        result = SkillResult(
            skill_name="special-chars",
            content=content,
        )

        assert "🐍" in result.content
        assert "你好" in result.content
        assert "< > & \" '" in result.content

    def test_subagent_result_with_large_output(self):
        """Test SubagentResult handles large output."""
        large_output = "x" * 100000  # 100KB of data

        result = SubagentResult(
            subagent_id="subagent-large",
            output=large_output,
        )

        assert len(result.output) == 100000
        assert result.success is True

    def test_skill_result_with_multiple_additional_files(self):
        """Test SkillResult with multiple additional files."""
        additional_files = {f"file{i}.md": f"Content {i}" for i in range(10)}

        result = SkillResult(
            skill_name="multi-file",
            content="Main content",
            additional_files=additional_files,
        )

        assert len(result.additional_files) == 10
        assert result.has_additional_files is True

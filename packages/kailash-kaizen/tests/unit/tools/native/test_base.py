"""
Unit Tests for Native Tool Base Classes (Tier 1)

Tests all base infrastructure for native tools including NativeToolResult
and BaseTool abstract class.

Coverage:
- NativeToolResult creation and factory methods
- NativeToolResult serialization
- BaseTool abstract interface
- Danger level and approval logic
- Schema generation
"""

from dataclasses import FrozenInstanceError
from unittest.mock import AsyncMock

import pytest

from kaizen.tools.native.base import BaseTool, NativeToolResult
from kaizen.tools.types import DangerLevel, ToolCategory


class TestNativeToolResult:
    """Test NativeToolResult dataclass."""

    def test_create_successful_result(self):
        """Test creating a successful result with output."""
        result = NativeToolResult(
            success=True,
            output="File contents here",
            metadata={"lines": 50, "bytes": 1024},
        )

        assert result.success is True
        assert result.output == "File contents here"
        assert result.error is None
        assert result.metadata == {"lines": 50, "bytes": 1024}

    def test_create_failed_result(self):
        """Test creating a failed result with error."""
        result = NativeToolResult(
            success=False,
            output="",
            error="File not found: /path/to/file.txt",
        )

        assert result.success is False
        assert result.output == ""
        assert result.error == "File not found: /path/to/file.txt"

    def test_create_result_with_complex_output(self):
        """Test result with complex output types."""
        # Dict output
        result1 = NativeToolResult(
            success=True,
            output={"data": [1, 2, 3], "total": 3},
        )
        assert isinstance(result1.output, dict)
        assert result1.output["total"] == 3

        # List output
        result2 = NativeToolResult(
            success=True,
            output=[{"name": "file1.txt"}, {"name": "file2.txt"}],
        )
        assert isinstance(result2.output, list)
        assert len(result2.output) == 2

    def test_from_success_factory(self):
        """Test from_success factory method."""
        result = NativeToolResult.from_success(
            "Operation completed",
            bytes_written=512,
            path="/tmp/file.txt",
        )

        assert result.success is True
        assert result.output == "Operation completed"
        assert result.error is None
        assert result.metadata["bytes_written"] == 512
        assert result.metadata["path"] == "/tmp/file.txt"

    def test_from_error_factory(self):
        """Test from_error factory method."""
        result = NativeToolResult.from_error(
            "Permission denied",
            path="/etc/passwd",
            attempted_operation="write",
        )

        assert result.success is False
        assert result.output == ""
        assert result.error == "Permission denied"
        assert result.metadata["path"] == "/etc/passwd"
        assert result.metadata["attempted_operation"] == "write"

    def test_from_exception_factory(self):
        """Test from_exception factory method."""
        try:
            raise ValueError("Invalid value provided")
        except ValueError as e:
            result = NativeToolResult.from_exception(e)

        assert result.success is False
        assert result.output == ""
        assert result.error == "Invalid value provided"
        assert result.metadata["exception_type"] == "ValueError"

    def test_from_exception_with_different_types(self):
        """Test from_exception with various exception types."""
        # FileNotFoundError
        exc1 = FileNotFoundError("No such file")
        result1 = NativeToolResult.from_exception(exc1)
        assert result1.metadata["exception_type"] == "FileNotFoundError"

        # PermissionError
        exc2 = PermissionError("Access denied")
        result2 = NativeToolResult.from_exception(exc2)
        assert result2.metadata["exception_type"] == "PermissionError"

        # TimeoutError
        exc3 = TimeoutError("Operation timed out")
        result3 = NativeToolResult.from_exception(exc3)
        assert result3.metadata["exception_type"] == "TimeoutError"

    def test_to_dict_serialization(self):
        """Test to_dict produces valid dictionary."""
        result = NativeToolResult(
            success=True,
            output="test output",
            error=None,
            metadata={"key": "value"},
        )

        data = result.to_dict()

        assert isinstance(data, dict)
        assert data["success"] is True
        assert data["output"] == "test output"
        assert data["error"] is None
        assert data["metadata"] == {"key": "value"}

    def test_to_dict_with_error(self):
        """Test to_dict with error result."""
        result = NativeToolResult(
            success=False,
            output="",
            error="Something went wrong",
            metadata={"exit_code": 1},
        )

        data = result.to_dict()

        assert data["success"] is False
        assert data["error"] == "Something went wrong"
        assert data["metadata"]["exit_code"] == 1

    def test_default_metadata_is_empty_dict(self):
        """Test that default metadata is an empty dict."""
        result = NativeToolResult(success=True, output="test")
        assert result.metadata == {}


class TestBaseTool:
    """Test BaseTool abstract base class."""

    def test_cannot_instantiate_abstract_class(self):
        """Test that BaseTool cannot be instantiated directly."""
        with pytest.raises(TypeError):
            BaseTool()

    def test_concrete_tool_requires_name(self):
        """Test that concrete tool must define name."""

        class NoNameTool(BaseTool):
            description = "A tool without name"
            danger_level = DangerLevel.SAFE
            category = ToolCategory.CUSTOM

            async def execute(self, **kwargs):
                return NativeToolResult.from_success("ok")

            def get_schema(self):
                return {"type": "object", "properties": {}}

        with pytest.raises(ValueError, match="must define 'name'"):
            NoNameTool()

    def test_concrete_tool_requires_description(self):
        """Test that concrete tool must define description."""

        class NoDescTool(BaseTool):
            name = "no_desc_tool"
            danger_level = DangerLevel.SAFE
            category = ToolCategory.CUSTOM

            async def execute(self, **kwargs):
                return NativeToolResult.from_success("ok")

            def get_schema(self):
                return {"type": "object", "properties": {}}

        with pytest.raises(ValueError, match="must define 'description'"):
            NoDescTool()

    def test_valid_concrete_tool(self):
        """Test creating a valid concrete tool."""

        class ValidTool(BaseTool):
            name = "valid_tool"
            description = "A valid tool for testing"
            danger_level = DangerLevel.SAFE
            category = ToolCategory.CUSTOM

            async def execute(self, text: str) -> NativeToolResult:
                return NativeToolResult.from_success(text.upper())

            def get_schema(self):
                return {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string", "description": "Input text"},
                    },
                    "required": ["text"],
                }

        tool = ValidTool()

        assert tool.name == "valid_tool"
        assert tool.description == "A valid tool for testing"
        assert tool.danger_level == DangerLevel.SAFE
        assert tool.category == ToolCategory.CUSTOM

    def test_is_safe_for_safe_level(self):
        """Test is_safe returns True for SAFE danger level."""

        class SafeTool(BaseTool):
            name = "safe_tool"
            description = "Safe tool"
            danger_level = DangerLevel.SAFE
            category = ToolCategory.CUSTOM

            async def execute(self, **kwargs):
                return NativeToolResult.from_success("ok")

            def get_schema(self):
                return {"type": "object", "properties": {}}

        tool = SafeTool()
        assert tool.is_safe() is True

    def test_is_safe_for_low_level(self):
        """Test is_safe returns True for LOW danger level."""

        class LowDangerTool(BaseTool):
            name = "low_tool"
            description = "Low danger tool"
            danger_level = DangerLevel.LOW
            category = ToolCategory.CUSTOM

            async def execute(self, **kwargs):
                return NativeToolResult.from_success("ok")

            def get_schema(self):
                return {"type": "object", "properties": {}}

        tool = LowDangerTool()
        assert tool.is_safe() is True

    def test_is_safe_false_for_medium_and_above(self):
        """Test is_safe returns False for MEDIUM and above."""

        class MediumTool(BaseTool):
            name = "medium_tool"
            description = "Medium danger"
            danger_level = DangerLevel.MEDIUM
            category = ToolCategory.CUSTOM

            async def execute(self, **kwargs):
                return NativeToolResult.from_success("ok")

            def get_schema(self):
                return {"type": "object", "properties": {}}

        class HighTool(BaseTool):
            name = "high_tool"
            description = "High danger"
            danger_level = DangerLevel.HIGH
            category = ToolCategory.SYSTEM

            async def execute(self, **kwargs):
                return NativeToolResult.from_success("ok")

            def get_schema(self):
                return {"type": "object", "properties": {}}

        class CriticalTool(BaseTool):
            name = "critical_tool"
            description = "Critical danger"
            danger_level = DangerLevel.CRITICAL
            category = ToolCategory.SYSTEM

            async def execute(self, **kwargs):
                return NativeToolResult.from_success("ok")

            def get_schema(self):
                return {"type": "object", "properties": {}}

        assert MediumTool().is_safe() is False
        assert HighTool().is_safe() is False
        assert CriticalTool().is_safe() is False

    def test_requires_approval_with_default_threshold(self):
        """Test requires_approval with default MEDIUM threshold."""

        class SafeTool(BaseTool):
            name = "safe"
            description = "Safe"
            danger_level = DangerLevel.SAFE
            category = ToolCategory.CUSTOM

            async def execute(self, **kwargs):
                return NativeToolResult.from_success("ok")

            def get_schema(self):
                return {"type": "object", "properties": {}}

        class HighTool(BaseTool):
            name = "high"
            description = "High"
            danger_level = DangerLevel.HIGH
            category = ToolCategory.SYSTEM

            async def execute(self, **kwargs):
                return NativeToolResult.from_success("ok")

            def get_schema(self):
                return {"type": "object", "properties": {}}

        # Default threshold is MEDIUM
        assert SafeTool().requires_approval() is False
        assert HighTool().requires_approval() is True

    def test_requires_approval_with_custom_threshold(self):
        """Test requires_approval with custom threshold."""

        class LowTool(BaseTool):
            name = "low"
            description = "Low"
            danger_level = DangerLevel.LOW
            category = ToolCategory.CUSTOM

            async def execute(self, **kwargs):
                return NativeToolResult.from_success("ok")

            def get_schema(self):
                return {"type": "object", "properties": {}}

        tool = LowTool()

        # With SAFE threshold, LOW requires approval
        assert tool.requires_approval(DangerLevel.SAFE) is True

        # With LOW threshold, LOW requires approval
        assert tool.requires_approval(DangerLevel.LOW) is True

        # With MEDIUM threshold, LOW doesn't require approval
        assert tool.requires_approval(DangerLevel.MEDIUM) is False

    def test_get_full_schema(self):
        """Test get_full_schema returns LLM-compatible format."""

        class TestTool(BaseTool):
            name = "test_tool"
            description = "A test tool"
            danger_level = DangerLevel.SAFE
            category = ToolCategory.DATA

            async def execute(self, input_text: str) -> NativeToolResult:
                return NativeToolResult.from_success(input_text)

            def get_schema(self):
                return {
                    "type": "object",
                    "properties": {
                        "input_text": {
                            "type": "string",
                            "description": "Text to process",
                        },
                    },
                    "required": ["input_text"],
                }

        tool = TestTool()
        schema = tool.get_full_schema()

        assert schema["type"] == "function"
        assert schema["function"]["name"] == "test_tool"
        assert schema["function"]["description"] == "A test tool"
        assert "properties" in schema["function"]["parameters"]
        assert "input_text" in schema["function"]["parameters"]["properties"]

    @pytest.mark.asyncio
    async def test_execute_with_timing(self):
        """Test execute_with_timing adds timing metadata."""

        class SlowTool(BaseTool):
            name = "slow_tool"
            description = "Slow tool"
            danger_level = DangerLevel.SAFE
            category = ToolCategory.CUSTOM

            async def execute(self, **kwargs) -> NativeToolResult:
                import asyncio

                await asyncio.sleep(0.01)  # 10ms delay
                return NativeToolResult.from_success("done")

            def get_schema(self):
                return {"type": "object", "properties": {}}

        tool = SlowTool()
        result = await tool.execute_with_timing()

        assert result.success is True
        assert "execution_time_ms" in result.metadata
        assert result.metadata["execution_time_ms"] >= 10  # At least 10ms

    def test_repr(self):
        """Test __repr__ for tool."""

        class TestTool(BaseTool):
            name = "repr_tool"
            description = "Test repr"
            danger_level = DangerLevel.HIGH
            category = ToolCategory.SYSTEM

            async def execute(self, **kwargs):
                return NativeToolResult.from_success("ok")

            def get_schema(self):
                return {"type": "object", "properties": {}}

        tool = TestTool()
        repr_str = repr(tool)

        assert "TestTool" in repr_str
        assert "repr_tool" in repr_str
        assert "high" in repr_str


class TestDangerLevelOrdering:
    """Test danger level comparison and ordering."""

    def test_danger_levels_in_order(self):
        """Test all danger levels exist in expected order."""
        levels = [
            DangerLevel.SAFE,
            DangerLevel.LOW,
            DangerLevel.MEDIUM,
            DangerLevel.HIGH,
            DangerLevel.CRITICAL,
        ]
        values = [l.value for l in levels]
        assert values == ["safe", "low", "medium", "high", "critical"]

    def test_requires_approval_respects_order(self):
        """Test requires_approval correctly compares danger levels."""

        def make_tool(danger_level):
            class DynamicTool(BaseTool):
                name = f"tool_{danger_level.value}"
                description = f"Tool with {danger_level.value} danger"
                category = ToolCategory.CUSTOM

                async def execute(self, **kwargs):
                    return NativeToolResult.from_success("ok")

                def get_schema(self):
                    return {"type": "object", "properties": {}}

            DynamicTool.danger_level = danger_level
            return DynamicTool()

        # SAFE threshold - only SAFE doesn't require approval
        assert make_tool(DangerLevel.SAFE).requires_approval(DangerLevel.SAFE) is True
        assert make_tool(DangerLevel.LOW).requires_approval(DangerLevel.SAFE) is True

        # HIGH threshold - only HIGH and CRITICAL require approval
        assert make_tool(DangerLevel.SAFE).requires_approval(DangerLevel.HIGH) is False
        assert make_tool(DangerLevel.LOW).requires_approval(DangerLevel.HIGH) is False
        assert (
            make_tool(DangerLevel.MEDIUM).requires_approval(DangerLevel.HIGH) is False
        )
        assert make_tool(DangerLevel.HIGH).requires_approval(DangerLevel.HIGH) is True
        assert (
            make_tool(DangerLevel.CRITICAL).requires_approval(DangerLevel.HIGH) is True
        )

"""
Unit Tests for Tool Type System (Tier 1)

Tests all type definitions, validation logic, and error handling for the
tool calling type system.

Coverage:
- ToolCategory enum
- DangerLevel enum
- ToolParameter validation
- ToolDefinition creation and validation
- ToolResult creation and serialization
"""

import pytest
from kaizen.tools.types import (
    DangerLevel,
    ToolCategory,
    ToolDefinition,
    ToolParameter,
    ToolResult,
)


class TestToolCategory:
    """Test ToolCategory enum."""

    def test_all_categories_exist(self):
        """Test all expected categories are defined."""
        assert ToolCategory.SYSTEM.value == "system"
        assert ToolCategory.NETWORK.value == "network"
        assert ToolCategory.DATA.value == "data"
        assert ToolCategory.AI.value == "ai"
        assert ToolCategory.MCP.value == "mcp"
        assert ToolCategory.CUSTOM.value == "custom"

    def test_category_count(self):
        """Test expected number of categories."""
        categories = list(ToolCategory)
        assert len(categories) == 6


class TestDangerLevel:
    """Test DangerLevel enum."""

    def test_all_danger_levels_exist(self):
        """Test all expected danger levels are defined."""
        assert DangerLevel.SAFE.value == "safe"
        assert DangerLevel.LOW.value == "low"
        assert DangerLevel.MEDIUM.value == "medium"
        assert DangerLevel.HIGH.value == "high"
        assert DangerLevel.CRITICAL.value == "critical"

    def test_danger_level_count(self):
        """Test expected number of danger levels."""
        levels = list(DangerLevel)
        assert len(levels) == 5

    def test_danger_level_ordering(self):
        """Test danger levels are in expected order."""
        levels = [
            DangerLevel.SAFE,
            DangerLevel.LOW,
            DangerLevel.MEDIUM,
            DangerLevel.HIGH,
            DangerLevel.CRITICAL,
        ]
        values = [level.value for level in levels]
        assert values == ["safe", "low", "medium", "high", "critical"]


class TestToolParameter:
    """Test ToolParameter dataclass and validation."""

    def test_create_required_parameter(self):
        """Test creating a required parameter."""
        param = ToolParameter(
            name="file_path", type=str, description="Path to file", required=True
        )

        assert param.name == "file_path"
        assert param.type == str
        assert param.description == "Path to file"
        assert param.required is True
        assert param.default is None
        assert param.validation is None

    def test_create_optional_parameter_with_default(self):
        """Test creating optional parameter with default value."""
        param = ToolParameter(
            name="encoding",
            type=str,
            description="File encoding",
            required=False,
            default="utf-8",
        )

        assert param.name == "encoding"
        assert param.required is False
        assert param.default == "utf-8"

    def test_parameter_with_validation_function(self):
        """Test parameter with custom validation function."""

        def validate_positive(value):
            return value > 0

        param = ToolParameter(
            name="count",
            type=int,
            description="Number of items",
            validation=validate_positive,
        )

        assert param.validation is not None
        # Validation tested in validate() tests below

    def test_validate_correct_type(self):
        """Test validation passes for correct type."""
        param = ToolParameter("name", str, "A name")
        assert param.validate("hello") is True

    def test_validate_wrong_type_raises_typeerror(self):
        """Test validation raises TypeError for wrong type."""
        param = ToolParameter("count", int, "A count")

        with pytest.raises(TypeError, match="expects int, got str"):
            param.validate("not an int")

    def test_validate_with_validation_function_passing(self):
        """Test validation passes when custom validator returns True."""

        def validate_positive(value):
            return value > 0

        param = ToolParameter(
            "count", int, "Positive count", validation=validate_positive
        )

        assert param.validate(5) is True
        assert param.validate(1) is True

    def test_validate_with_validation_function_failing(self):
        """Test validation raises ValueError when custom validator returns False."""

        def validate_positive(value):
            return value > 0

        param = ToolParameter(
            "count", int, "Positive count", validation=validate_positive
        )

        with pytest.raises(ValueError, match="failed validation"):
            param.validate(0)

        with pytest.raises(ValueError, match="failed validation"):
            param.validate(-5)

    def test_validate_different_types(self):
        """Test validation works for different Python types."""
        # String
        str_param = ToolParameter("text", str, "Text")
        assert str_param.validate("hello") is True

        # Int
        int_param = ToolParameter("num", int, "Number")
        assert int_param.validate(42) is True

        # Bool
        bool_param = ToolParameter("flag", bool, "Flag")
        assert bool_param.validate(True) is True

        # Dict
        dict_param = ToolParameter("config", dict, "Config")
        assert dict_param.validate({"key": "value"}) is True

        # List
        list_param = ToolParameter("items", list, "Items")
        assert list_param.validate([1, 2, 3]) is True


class TestToolDefinition:
    """Test ToolDefinition dataclass and methods."""

    def test_create_simple_tool_definition(self):
        """Test creating a simple tool definition."""

        def dummy_executor(text: str) -> dict:
            return {"result": text.upper()}

        tool = ToolDefinition(
            name="uppercase",
            description="Convert to uppercase",
            category=ToolCategory.DATA,
            danger_level=DangerLevel.SAFE,
            parameters=[ToolParameter("text", str, "Input text")],
            returns={"result": "str"},
            executor=dummy_executor,
        )

        assert tool.name == "uppercase"
        assert tool.description == "Convert to uppercase"
        assert tool.category == ToolCategory.DATA
        assert tool.danger_level == DangerLevel.SAFE
        assert len(tool.parameters) == 1
        assert tool.returns == {"result": "str"}
        assert tool.executor is dummy_executor
        assert tool.examples is None

    def test_create_tool_with_multiple_parameters(self):
        """Test creating tool with multiple parameters."""

        def read_file(path: str, encoding: str = "utf-8") -> dict:
            return {"content": "..."}

        tool = ToolDefinition(
            name="read_file",
            description="Read file",
            category=ToolCategory.SYSTEM,
            danger_level=DangerLevel.SAFE,
            parameters=[
                ToolParameter("path", str, "File path", required=True),
                ToolParameter(
                    "encoding", str, "Encoding", required=False, default="utf-8"
                ),
            ],
            returns={"content": "str"},
            executor=read_file,
        )

        assert len(tool.parameters) == 2
        assert tool.parameters[0].name == "path"
        assert tool.parameters[0].required is True
        assert tool.parameters[1].name == "encoding"
        assert tool.parameters[1].required is False

    def test_create_tool_with_examples(self):
        """Test creating tool with example calls."""
        tool = ToolDefinition(
            name="add",
            description="Add numbers",
            category=ToolCategory.DATA,
            danger_level=DangerLevel.SAFE,
            parameters=[
                ToolParameter("a", int, "First number"),
                ToolParameter("b", int, "Second number"),
            ],
            returns={"result": "int"},
            executor=lambda a, b: {"result": a + b},
            examples=[
                {"a": 1, "b": 2, "expected": {"result": 3}},
                {"a": 10, "b": 20, "expected": {"result": 30}},
            ],
        )

        assert len(tool.examples) == 2
        assert tool.examples[0]["expected"]["result"] == 3

    def test_validate_parameters_all_required_present(self):
        """Test parameter validation passes when all required params present."""
        tool = ToolDefinition(
            name="greet",
            description="Greet user",
            category=ToolCategory.CUSTOM,
            danger_level=DangerLevel.SAFE,
            parameters=[ToolParameter("name", str, "User name", required=True)],
            returns={"greeting": "str"},
            executor=lambda name: {"greeting": f"Hello {name}"},
        )

        # Should pass - all required params present
        assert tool.validate_parameters({"name": "Alice"}) is True

    def test_validate_parameters_missing_required_raises_error(self):
        """Test validation raises ValueError when required parameter missing."""
        tool = ToolDefinition(
            name="greet",
            description="Greet user",
            category=ToolCategory.CUSTOM,
            danger_level=DangerLevel.SAFE,
            parameters=[ToolParameter("name", str, "User name", required=True)],
            returns={"greeting": "str"},
            executor=lambda name: {"greeting": f"Hello {name}"},
        )

        with pytest.raises(ValueError, match="Required parameter 'name' missing"):
            tool.validate_parameters({})

    def test_validate_parameters_unknown_parameter_raises_error(self):
        """Test validation raises ValueError for unknown parameters."""
        tool = ToolDefinition(
            name="greet",
            description="Greet user",
            category=ToolCategory.CUSTOM,
            danger_level=DangerLevel.SAFE,
            parameters=[ToolParameter("name", str, "User name")],
            returns={"greeting": "str"},
            executor=lambda name: {"greeting": f"Hello {name}"},
        )

        with pytest.raises(ValueError, match="Unknown parameter 'age'"):
            tool.validate_parameters({"name": "Alice", "age": 30})

    def test_validate_parameters_wrong_type_raises_error(self):
        """Test validation raises TypeError for wrong parameter type."""
        tool = ToolDefinition(
            name="add",
            description="Add numbers",
            category=ToolCategory.DATA,
            danger_level=DangerLevel.SAFE,
            parameters=[
                ToolParameter("a", int, "First number"),
                ToolParameter("b", int, "Second number"),
            ],
            returns={"result": "int"},
            executor=lambda a, b: {"result": a + b},
        )

        with pytest.raises(TypeError, match="expects int, got str"):
            tool.validate_parameters({"a": "not a number", "b": 5})

    def test_validate_parameters_with_optional_params(self):
        """Test validation works with optional parameters."""
        tool = ToolDefinition(
            name="read_file",
            description="Read file",
            category=ToolCategory.SYSTEM,
            danger_level=DangerLevel.SAFE,
            parameters=[
                ToolParameter("path", str, "File path", required=True),
                ToolParameter(
                    "encoding", str, "Encoding", required=False, default="utf-8"
                ),
            ],
            returns={"content": "str"},
            executor=lambda path, encoding="utf-8": {"content": "..."},
        )

        # Without optional param
        assert tool.validate_parameters({"path": "/tmp/file.txt"}) is True

        # With optional param
        assert (
            tool.validate_parameters({"path": "/tmp/file.txt", "encoding": "latin1"})
            is True
        )

    def test_get_approval_message_default(self):
        """Test default approval message generation."""
        tool = ToolDefinition(
            name="bash_command",
            description="Execute bash",
            category=ToolCategory.SYSTEM,
            danger_level=DangerLevel.HIGH,
            parameters=[ToolParameter("command", str, "Command")],
            returns={"stdout": "str"},
            executor=lambda command: {},
        )

        message = tool.get_approval_message({"command": "ls -la"})
        assert "bash_command" in message
        assert "ls -la" in message

    def test_get_approval_message_custom_template(self):
        """Test custom approval message template."""
        tool = ToolDefinition(
            name="bash_command",
            description="Execute bash",
            category=ToolCategory.SYSTEM,
            danger_level=DangerLevel.HIGH,
            parameters=[ToolParameter("command", str, "Command")],
            returns={"stdout": "str"},
            executor=lambda command: {},
            approval_message_template="Execute bash command: '{command}'",
        )

        message = tool.get_approval_message({"command": "ls -la"})
        assert message == "Execute bash command: 'ls -la'"

    def test_get_approval_details_default(self):
        """Test default approval details extraction."""
        tool = ToolDefinition(
            name="delete_file",
            description="Delete file",
            category=ToolCategory.SYSTEM,
            danger_level=DangerLevel.HIGH,
            parameters=[ToolParameter("path", str, "File path")],
            returns={"success": "bool"},
            executor=lambda path: {},
        )

        details = tool.get_approval_details({"path": "/tmp/file.txt"})
        assert details["tool"] == "delete_file"
        assert details["category"] == "system"
        assert details["danger_level"] == "high"
        assert details["parameters"]["path"] == "/tmp/file.txt"

    def test_get_approval_details_custom_extractor(self):
        """Test custom approval details extractor."""

        def extract_details(params):
            return {"file": params["path"], "action": "delete", "reversible": False}

        tool = ToolDefinition(
            name="delete_file",
            description="Delete file",
            category=ToolCategory.SYSTEM,
            danger_level=DangerLevel.HIGH,
            parameters=[ToolParameter("path", str, "File path")],
            returns={"success": "bool"},
            executor=lambda path: {},
            approval_details_extractor=extract_details,
        )

        details = tool.get_approval_details({"path": "/tmp/file.txt"})
        assert details["file"] == "/tmp/file.txt"
        assert details["action"] == "delete"
        assert details["reversible"] is False


class TestToolResult:
    """Test ToolResult dataclass and methods."""

    def test_create_successful_result(self):
        """Test creating successful tool result."""
        result = ToolResult(
            tool_name="uppercase",
            success=True,
            result={"output": "HELLO"},
            execution_time_ms=5.2,
        )

        assert result.tool_name == "uppercase"
        assert result.success is True
        assert result.result == {"output": "HELLO"}
        assert result.error is None
        assert result.execution_time_ms == 5.2
        assert result.approved is None
        assert result.cached is False

    def test_create_failed_result(self):
        """Test creating failed tool result."""
        result = ToolResult(
            tool_name="bash_command",
            success=False,
            error="Command failed",
            error_type="CalledProcessError",
            execution_time_ms=120.5,
            approved=True,
        )

        assert result.tool_name == "bash_command"
        assert result.success is False
        assert result.result is None
        assert result.error == "Command failed"
        assert result.error_type == "CalledProcessError"
        assert result.execution_time_ms == 120.5
        assert result.approved is True

    def test_create_cached_result(self):
        """Test creating cached result."""
        result = ToolResult(
            tool_name="fetch_data",
            success=True,
            result={"data": [1, 2, 3]},
            cached=True,
        )

        assert result.cached is True

    def test_to_dict(self):
        """Test converting result to dictionary."""
        result = ToolResult(
            tool_name="test_tool",
            success=True,
            result={"value": 42},
            execution_time_ms=10.5,
            approved=True,
        )

        data = result.to_dict()
        assert isinstance(data, dict)
        assert data["tool_name"] == "test_tool"
        assert data["success"] is True
        assert data["result"] == {"value": 42}
        assert data["execution_time_ms"] == 10.5
        assert data["approved"] is True
        assert data["cached"] is False

    def test_from_exception_value_error(self):
        """Test creating result from ValueError."""
        exc = ValueError("Invalid parameter")
        result = ToolResult.from_exception(
            tool_name="test_tool", exception=exc, execution_time_ms=1.5, approved=True
        )

        assert result.tool_name == "test_tool"
        assert result.success is False
        assert result.error == "Invalid parameter"
        assert result.error_type == "ValueError"
        assert result.execution_time_ms == 1.5
        assert result.approved is True

    def test_from_exception_runtime_error(self):
        """Test creating result from RuntimeError."""
        exc = RuntimeError("Tool not found")
        result = ToolResult.from_exception(
            tool_name="missing_tool", exception=exc, execution_time_ms=0.1
        )

        assert result.error == "Tool not found"
        assert result.error_type == "RuntimeError"

    def test_from_exception_type_error(self):
        """Test creating result from TypeError."""
        exc = TypeError("Wrong type")
        result = ToolResult.from_exception(
            tool_name="typed_tool", exception=exc, execution_time_ms=2.0
        )

        assert result.error == "Wrong type"
        assert result.error_type == "TypeError"

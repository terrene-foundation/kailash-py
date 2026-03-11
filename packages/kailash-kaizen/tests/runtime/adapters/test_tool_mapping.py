"""
Tests for Tool Mapping Infrastructure

Tests the format conversion between Kaizen's tool format and
external runtime formats (MCP, OpenAI, Gemini).
"""

from typing import Any, Dict, List

import pytest

from kaizen.runtime.adapters.tool_mapping import (
    GeminiToolMapper,
    KaizenTool,
    MappedTool,
    MCPToolMapper,
    OpenAIToolMapper,
    ToolMapper,
    ToolMappingError,
)
from kaizen.runtime.adapters.tool_mapping.base import (
    extract_tool_call,
    format_tool_result,
)

# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def simple_kaizen_tool() -> Dict[str, Any]:
    """Simple tool in Kaizen/OpenAI format."""
    return {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get weather for a location",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {"type": "string", "description": "City name"},
                    "units": {
                        "type": "string",
                        "enum": ["celsius", "fahrenheit"],
                        "description": "Temperature units",
                    },
                },
                "required": ["location"],
            },
        },
    }


@pytest.fixture
def complex_kaizen_tool() -> Dict[str, Any]:
    """Complex tool with nested objects and arrays."""
    return {
        "type": "function",
        "function": {
            "name": "search_documents",
            "description": "Search through indexed documents with filters",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "filters": {
                        "type": "object",
                        "properties": {
                            "date_range": {
                                "type": "object",
                                "properties": {
                                    "start": {"type": "string", "format": "date"},
                                    "end": {"type": "string", "format": "date"},
                                },
                            },
                            "categories": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                        },
                    },
                    "limit": {"type": "integer", "description": "Max results"},
                },
                "required": ["query"],
            },
        },
    }


@pytest.fixture
def flat_format_tool() -> Dict[str, Any]:
    """Tool in flat format (no type wrapper)."""
    return {
        "name": "simple_tool",
        "description": "A simple tool",
        "parameters": {"type": "object", "properties": {"input": {"type": "string"}}},
    }


@pytest.fixture
def kaizen_tools(simple_kaizen_tool, complex_kaizen_tool) -> List[Dict[str, Any]]:
    """List of Kaizen tools."""
    return [simple_kaizen_tool, complex_kaizen_tool]


# =============================================================================
# KaizenTool Tests
# =============================================================================


class TestKaizenTool:
    """Tests for KaizenTool dataclass."""

    def test_from_dict_openai_format(self, simple_kaizen_tool):
        """Test parsing OpenAI format."""
        tool = KaizenTool.from_dict(simple_kaizen_tool)

        assert tool.name == "get_weather"
        assert tool.description == "Get weather for a location"
        assert "properties" in tool.parameters
        assert "location" in tool.parameters["properties"]

    def test_from_dict_flat_format(self, flat_format_tool):
        """Test parsing flat format."""
        tool = KaizenTool.from_dict(flat_format_tool)

        assert tool.name == "simple_tool"
        assert tool.description == "A simple tool"

    def test_to_dict(self, simple_kaizen_tool):
        """Test serialization."""
        tool = KaizenTool.from_dict(simple_kaizen_tool)
        result = tool.to_dict()

        assert result["type"] == "function"
        assert result["function"]["name"] == "get_weather"

    def test_validate_valid_tool(self, simple_kaizen_tool):
        """Test validation of valid tool."""
        tool = KaizenTool.from_dict(simple_kaizen_tool)
        errors = tool.validate()

        assert len(errors) == 0

    def test_validate_missing_name(self):
        """Test validation catches missing name."""
        tool = KaizenTool(name="", description="Test")
        errors = tool.validate()

        assert any("name is required" in e for e in errors)

    def test_validate_missing_description(self):
        """Test validation catches missing description."""
        tool = KaizenTool(name="test", description="")
        errors = tool.validate()

        assert any("description is required" in e for e in errors)

    def test_validate_invalid_parameters_type(self):
        """Test validation catches non-object parameters."""
        tool = KaizenTool(
            name="test", description="Test", parameters={"type": "string"}
        )
        errors = tool.validate()

        assert any("type must be 'object'" in e for e in errors)


# =============================================================================
# MCPToolMapper Tests
# =============================================================================


class TestMCPToolMapper:
    """Tests for MCP format mapper."""

    def test_to_mcp_format_simple(self, simple_kaizen_tool):
        """Test conversion of simple tool to MCP format."""
        mcp_tools = MCPToolMapper.to_runtime_format([simple_kaizen_tool])

        assert len(mcp_tools) == 1
        tool = mcp_tools[0]

        assert tool["name"] == "get_weather"
        assert tool["description"] == "Get weather for a location"
        assert "inputSchema" in tool
        assert tool["inputSchema"]["type"] == "object"
        assert "location" in tool["inputSchema"]["properties"]

    def test_to_mcp_format_complex(self, complex_kaizen_tool):
        """Test conversion of complex nested tool."""
        mcp_tools = MCPToolMapper.to_runtime_format([complex_kaizen_tool])

        assert len(mcp_tools) == 1
        tool = mcp_tools[0]

        assert tool["name"] == "search_documents"
        assert "inputSchema" in tool
        # Check nested structure preserved
        props = tool["inputSchema"]["properties"]
        assert "filters" in props
        assert "categories" in props["filters"]["properties"]

    def test_from_mcp_format(self, simple_kaizen_tool):
        """Test round-trip conversion."""
        mcp_tools = MCPToolMapper.to_runtime_format([simple_kaizen_tool])
        kaizen_tools = MCPToolMapper.from_runtime_format(mcp_tools)

        assert len(kaizen_tools) == 1
        tool = kaizen_tools[0]

        assert tool["type"] == "function"
        assert tool["function"]["name"] == "get_weather"

    def test_reserved_name_skip(self):
        """Test that reserved names are skipped."""
        tool = {
            "type": "function",
            "function": {
                "name": "Read",  # Reserved Claude Code tool
                "description": "Read a file",
                "parameters": {"type": "object", "properties": {}},
            },
        }

        mcp_tools = MCPToolMapper.to_runtime_format([tool], strict=False)
        assert len(mcp_tools) == 0  # Skipped

    def test_reserved_name_strict_raises(self):
        """Test that reserved names raise in strict mode."""
        tool = {
            "type": "function",
            "function": {
                "name": "Bash",
                "description": "Run bash",
                "parameters": {"type": "object", "properties": {}},
            },
        }

        with pytest.raises(ToolMappingError) as exc_info:
            MCPToolMapper.to_runtime_format([tool], strict=True)

        # Check error message mentions the conflict
        assert (
            "native tool" in str(exc_info.value).lower()
            or "conflicts" in str(exc_info.value).lower()
        )

    def test_convenience_methods(self, simple_kaizen_tool):
        """Test convenience aliases."""
        mcp_tools = MCPToolMapper.to_mcp_format([simple_kaizen_tool])
        assert len(mcp_tools) == 1

        back = MCPToolMapper.from_mcp_format(mcp_tools)
        assert len(back) == 1


# =============================================================================
# OpenAIToolMapper Tests
# =============================================================================


class TestOpenAIToolMapper:
    """Tests for OpenAI format mapper."""

    def test_to_openai_format_validation(self, simple_kaizen_tool):
        """Test validation and normalization."""
        openai_tools = OpenAIToolMapper.to_runtime_format([simple_kaizen_tool])

        assert len(openai_tools) == 1
        tool = openai_tools[0]

        assert tool["type"] == "function"
        assert tool["function"]["name"] == "get_weather"
        assert "strict" in tool["function"]

    def test_from_openai_format(self, simple_kaizen_tool):
        """Test round-trip."""
        openai_tools = OpenAIToolMapper.to_runtime_format([simple_kaizen_tool])
        back = OpenAIToolMapper.from_runtime_format(openai_tools)

        assert len(back) == 1
        assert back[0]["function"]["name"] == "get_weather"

    def test_invalid_name_pattern(self):
        """Test validation catches invalid name patterns."""
        tool = {
            "type": "function",
            "function": {
                "name": "invalid name!",  # Spaces and special chars
                "description": "Test",
                "parameters": {"type": "object", "properties": {}},
            },
        }

        # Non-strict mode should skip
        tools = OpenAIToolMapper.to_runtime_format([tool], strict=False)
        assert len(tools) == 0

    def test_strict_mode_validation(self):
        """Test strict mode parameter validation."""
        tool = KaizenTool(
            name="test",
            description="Test",
            parameters={
                "type": "object",
                "properties": {
                    "optional": {"type": "string"}  # Not required, no default
                },
            },
            strict=True,
        )
        errors = OpenAIToolMapper._validate_strict_mode(tool)

        assert any("additionalProperties" in e for e in errors)
        assert any("required" in e for e in errors)

    def test_for_responses_api(self, simple_kaizen_tool):
        """Test Responses API formatting."""
        tools = OpenAIToolMapper.for_responses_api(
            [simple_kaizen_tool], enable_code_interpreter=True, enable_file_search=True
        )

        # Should have function + code_interpreter + file_search
        assert len(tools) == 3
        types = [t.get("type") for t in tools]
        assert "function" in types
        assert "code_interpreter" in types
        assert "file_search" in types

    def test_name_truncation(self):
        """Test long name is truncated."""
        long_name = "a" * 100
        tool = {
            "type": "function",
            "function": {
                "name": long_name,
                "description": "Test",
                "parameters": {"type": "object", "properties": {}},
            },
        }

        # Parse tool
        parsed = KaizenTool.from_dict(tool)
        normalized = OpenAIToolMapper._normalize_tool(parsed)

        assert len(normalized["function"]["name"]) <= 64


# =============================================================================
# GeminiToolMapper Tests
# =============================================================================


class TestGeminiToolMapper:
    """Tests for Gemini format mapper."""

    def test_to_gemini_format_uppercase_types(self, simple_kaizen_tool):
        """Test that types are converted to uppercase."""
        gemini_tools = GeminiToolMapper.to_runtime_format([simple_kaizen_tool])

        assert len(gemini_tools) == 1
        tool = gemini_tools[0]

        # Check uppercase types
        assert tool["parameters"]["type"] == "OBJECT"
        assert tool["parameters"]["properties"]["location"]["type"] == "STRING"

    def test_from_gemini_format_lowercase_types(self, simple_kaizen_tool):
        """Test that types are converted back to lowercase."""
        gemini_tools = GeminiToolMapper.to_runtime_format([simple_kaizen_tool])
        kaizen_tools = GeminiToolMapper.from_runtime_format(gemini_tools)

        assert len(kaizen_tools) == 1
        tool = kaizen_tools[0]

        # Check lowercase types
        params = tool["function"]["parameters"]
        assert params["type"] == "object"
        assert params["properties"]["location"]["type"] == "string"

    def test_nested_conversion(self, complex_kaizen_tool):
        """Test nested schema type conversion."""
        gemini_tools = GeminiToolMapper.to_runtime_format([complex_kaizen_tool])
        tool = gemini_tools[0]

        # Check nested object types
        filters = tool["parameters"]["properties"]["filters"]
        assert filters["type"] == "OBJECT"

        # Check array types
        categories = filters["properties"]["categories"]
        assert categories["type"] == "ARRAY"
        assert categories["items"]["type"] == "STRING"

    def test_round_trip(self, complex_kaizen_tool):
        """Test full round-trip preserves structure."""
        gemini_tools = GeminiToolMapper.to_runtime_format([complex_kaizen_tool])
        back = GeminiToolMapper.from_runtime_format(gemini_tools)

        assert len(back) == 1
        tool = back[0]

        # Check structure preserved
        params = tool["function"]["parameters"]
        assert "filters" in params["properties"]
        assert "categories" in params["properties"]["filters"]["properties"]

    def test_wrap_for_api(self, simple_kaizen_tool):
        """Test API wrapper format."""
        wrapped = GeminiToolMapper.wrap_for_api([simple_kaizen_tool])

        assert "tools" in wrapped
        assert len(wrapped["tools"]) == 1
        assert "function_declarations" in wrapped["tools"][0]
        assert len(wrapped["tools"][0]["function_declarations"]) == 1

    def test_enum_preserved(self, simple_kaizen_tool):
        """Test that enum values are preserved."""
        gemini_tools = GeminiToolMapper.to_runtime_format([simple_kaizen_tool])
        tool = gemini_tools[0]

        units = tool["parameters"]["properties"]["units"]
        assert "enum" in units
        assert "celsius" in units["enum"]
        assert "fahrenheit" in units["enum"]

    def test_convenience_methods(self, simple_kaizen_tool):
        """Test convenience aliases."""
        gemini_tools = GeminiToolMapper.to_gemini_format([simple_kaizen_tool])
        assert len(gemini_tools) == 1

        back = GeminiToolMapper.from_gemini_format(gemini_tools)
        assert len(back) == 1


# =============================================================================
# Helper Function Tests
# =============================================================================


class TestExtractToolCall:
    """Tests for extract_tool_call helper."""

    def test_openai_format(self):
        """Test OpenAI tool call extraction."""
        response = {
            "tool_calls": [
                {
                    "id": "call_123",
                    "function": {
                        "name": "get_weather",
                        "arguments": '{"location": "NYC"}',
                    },
                }
            ]
        }

        result = extract_tool_call(response, "openai")

        assert result is not None
        assert result["id"] == "call_123"
        assert result["name"] == "get_weather"
        assert result["arguments"] == {"location": "NYC"}

    def test_anthropic_format(self):
        """Test Anthropic tool call extraction."""
        response = {
            "content": [
                {"type": "text", "text": "Let me check the weather"},
                {
                    "type": "tool_use",
                    "id": "toolu_123",
                    "name": "get_weather",
                    "input": {"location": "NYC"},
                },
            ]
        }

        result = extract_tool_call(response, "anthropic")

        assert result is not None
        assert result["id"] == "toolu_123"
        assert result["name"] == "get_weather"
        assert result["arguments"] == {"location": "NYC"}

    def test_gemini_format(self):
        """Test Gemini tool call extraction."""
        response = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "functionCall": {
                                    "name": "get_weather",
                                    "args": {"location": "NYC"},
                                }
                            }
                        ]
                    }
                }
            ]
        }

        result = extract_tool_call(response, "gemini")

        assert result is not None
        assert result["name"] == "get_weather"
        assert result["arguments"] == {"location": "NYC"}

    def test_no_tool_call(self):
        """Test when no tool call present."""
        response = {"content": "Just some text"}
        result = extract_tool_call(response, "openai")
        assert result is None


class TestFormatToolResult:
    """Tests for format_tool_result helper."""

    def test_openai_format(self):
        """Test OpenAI result formatting."""
        result = format_tool_result(
            tool_call_id="call_123", result={"temperature": 72}, format_name="openai"
        )

        assert result["role"] == "tool"
        assert result["tool_call_id"] == "call_123"
        assert "72" in result["content"]

    def test_anthropic_format(self):
        """Test Anthropic result formatting."""
        result = format_tool_result(
            tool_call_id="toolu_123",
            result="72°F",
            format_name="anthropic",
            is_error=False,
        )

        assert result["type"] == "tool_result"
        assert result["tool_use_id"] == "toolu_123"
        assert result["is_error"] is False

    def test_gemini_format(self):
        """Test Gemini result formatting."""
        result = format_tool_result(
            tool_call_id="get_weather", result={"temp": 72}, format_name="gemini"
        )

        assert "functionResponse" in result
        assert result["functionResponse"]["name"] == "get_weather"


# =============================================================================
# Error Handling Tests
# =============================================================================


class TestToolMappingError:
    """Tests for ToolMappingError."""

    def test_basic_error(self):
        """Test basic error creation."""
        error = ToolMappingError("Something went wrong")
        assert "Something went wrong" in str(error)

    def test_error_with_tool_name(self):
        """Test error with tool name."""
        error = ToolMappingError("Validation failed", tool_name="my_tool")
        assert "my_tool" in str(error)

    def test_error_with_reason(self):
        """Test error with reason."""
        error = ToolMappingError(
            "Conversion failed",
            tool_name="test",
            source_format="kaizen",
            target_format="mcp",
            reason="Invalid schema",
        )
        assert "Invalid schema" in str(error)
        assert error.source_format == "kaizen"
        assert error.target_format == "mcp"


# =============================================================================
# Integration Tests
# =============================================================================


class TestToolMappingIntegration:
    """Integration tests for complete workflows."""

    def test_full_workflow_mcp(self, kaizen_tools):
        """Test complete MCP workflow."""
        # Convert to MCP
        mcp_tools = MCPToolMapper.to_mcp_format(kaizen_tools)
        assert len(mcp_tools) == 2

        # Convert back
        back = MCPToolMapper.from_mcp_format(mcp_tools)
        assert len(back) == 2

        # Verify structure
        for tool in back:
            assert "type" in tool
            assert "function" in tool

    def test_full_workflow_gemini(self, kaizen_tools):
        """Test complete Gemini workflow."""
        # Convert to Gemini
        gemini_tools = GeminiToolMapper.to_gemini_format(kaizen_tools)
        assert len(gemini_tools) == 2

        # Verify uppercase types
        for tool in gemini_tools:
            assert tool["parameters"]["type"] == "OBJECT"

        # Convert back
        back = GeminiToolMapper.from_gemini_format(gemini_tools)
        assert len(back) == 2

        # Verify lowercase types
        for tool in back:
            assert tool["function"]["parameters"]["type"] == "object"

    def test_mixed_format_tools(self, simple_kaizen_tool, flat_format_tool):
        """Test handling mix of format styles."""
        tools = [simple_kaizen_tool, flat_format_tool]

        # All mappers should handle both formats
        mcp = MCPToolMapper.to_mcp_format(tools)
        assert len(mcp) == 2

        openai = OpenAIToolMapper.to_openai_format(tools)
        assert len(openai) == 2

        gemini = GeminiToolMapper.to_gemini_format(tools)
        assert len(gemini) == 2

    def test_empty_tools_list(self):
        """Test handling empty tools list."""
        assert MCPToolMapper.to_mcp_format([]) == []
        assert OpenAIToolMapper.to_openai_format([]) == []
        assert GeminiToolMapper.to_gemini_format([]) == []

    def test_invalid_tools_skipped_non_strict(self):
        """Test that invalid tools are skipped in non-strict mode."""
        tools = [
            {"invalid": "format"},  # Invalid
            {
                "type": "function",
                "function": {
                    "name": "valid_tool",
                    "description": "Valid",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
        ]

        mcp = MCPToolMapper.to_mcp_format(tools)
        assert len(mcp) == 1
        assert mcp[0]["name"] == "valid_tool"

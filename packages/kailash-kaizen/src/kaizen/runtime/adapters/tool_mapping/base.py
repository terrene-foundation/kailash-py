"""
Base Tool Mapping Infrastructure

Defines the abstract interface and common types for tool format mapping
between Kaizen's internal format and external runtime formats.
"""

import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, Generic, List, Optional, TypeVar

logger = logging.getLogger(__name__)


class ToolMappingError(Exception):
    """Exception raised when tool mapping fails.

    Attributes:
        tool_name: Name of the tool that failed to map
        source_format: Source format name
        target_format: Target format name
        reason: Reason for the failure
    """

    def __init__(
        self,
        message: str,
        tool_name: Optional[str] = None,
        source_format: str = "kaizen",
        target_format: str = "unknown",
        reason: Optional[str] = None,
    ):
        self.tool_name = tool_name
        self.source_format = source_format
        self.target_format = target_format
        self.reason = reason

        full_message = message
        if tool_name:
            full_message = f"[{tool_name}] {message}"
        if reason:
            full_message += f": {reason}"

        super().__init__(full_message)


@dataclass
class KaizenTool:
    """Kaizen tool definition (OpenAI function calling format).

    This is the canonical format used internally by Kaizen for tool definitions.
    It follows the OpenAI function calling schema.

    Attributes:
        name: Unique tool name
        description: Human-readable description
        parameters: JSON Schema for tool parameters
        strict: Whether to enforce strict schema validation
    """

    name: str
    description: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    strict: bool = False

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "KaizenTool":
        """Create KaizenTool from dictionary.

        Handles both flat format and nested function format.

        Args:
            data: Tool definition dictionary

        Returns:
            KaizenTool instance
        """
        # Handle OpenAI nested format: {"type": "function", "function": {...}}
        if "type" in data and data.get("type") == "function" and "function" in data:
            func = data["function"]
            return cls(
                name=func.get("name", ""),
                description=func.get("description", ""),
                parameters=func.get("parameters", {}),
                strict=func.get("strict", False),
            )

        # Handle flat format
        return cls(
            name=data.get("name", ""),
            description=data.get("description", ""),
            parameters=data.get("parameters", {}),
            strict=data.get("strict", False),
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to OpenAI function format dictionary.

        Returns:
            Dictionary in OpenAI function calling format
        """
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
                "strict": self.strict,
            },
        }

    def validate(self) -> List[str]:
        """Validate the tool definition.

        Returns:
            List of validation error messages (empty if valid)
        """
        errors = []

        if not self.name:
            errors.append("Tool name is required")
        elif not self.name.replace("_", "").replace("-", "").isalnum():
            errors.append(f"Tool name '{self.name}' contains invalid characters")

        if not self.description:
            errors.append("Tool description is required")

        if self.parameters:
            if "type" not in self.parameters:
                errors.append("Parameters must have a 'type' field")
            elif self.parameters.get("type") != "object":
                errors.append("Parameters type must be 'object'")

        return errors


# Generic type for mapped tool format
MappedToolType = TypeVar("MappedToolType", bound=Dict[str, Any])


@dataclass
class MappedTool(Generic[MappedToolType]):
    """Result of tool mapping operation.

    Wraps the mapped tool with metadata about the mapping.

    Attributes:
        original: Original KaizenTool
        mapped: Tool in target format
        format_name: Name of target format
        warnings: Any warnings generated during mapping
    """

    original: KaizenTool
    mapped: MappedToolType
    format_name: str
    warnings: List[str] = field(default_factory=list)


class ToolMapper(ABC):
    """Abstract base class for tool format mappers.

    Each external runtime adapter should have a corresponding ToolMapper
    that converts between Kaizen's format and the runtime's expected format.
    """

    # Format name identifier (e.g., "mcp", "openai", "gemini")
    FORMAT_NAME: str = "unknown"

    @classmethod
    @abstractmethod
    def to_runtime_format(
        cls,
        kaizen_tools: List[Dict[str, Any]],
        strict: bool = False,
    ) -> List[Dict[str, Any]]:
        """Convert Kaizen tools to runtime-specific format.

        Args:
            kaizen_tools: List of tools in Kaizen/OpenAI format
            strict: If True, raise on validation errors; if False, skip invalid tools

        Returns:
            List of tools in runtime-specific format

        Raises:
            ToolMappingError: If strict=True and a tool fails validation
        """
        pass

    @classmethod
    @abstractmethod
    def from_runtime_format(
        cls,
        runtime_tools: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Convert runtime-specific tools back to Kaizen format.

        Useful for normalizing tool definitions from external sources.

        Args:
            runtime_tools: List of tools in runtime-specific format

        Returns:
            List of tools in Kaizen/OpenAI format
        """
        pass

    @classmethod
    def validate_tool(cls, tool: KaizenTool) -> List[str]:
        """Validate a tool against format-specific requirements.

        Override in subclasses for format-specific validation.

        Args:
            tool: Tool to validate

        Returns:
            List of validation errors (empty if valid)
        """
        return tool.validate()

    @classmethod
    def _parse_kaizen_tools(
        cls,
        kaizen_tools: List[Dict[str, Any]],
        strict: bool = False,
    ) -> List[KaizenTool]:
        """Parse raw tool dictionaries into KaizenTool objects.

        Args:
            kaizen_tools: List of raw tool dictionaries
            strict: If True, raise on parse errors

        Returns:
            List of KaizenTool objects

        Raises:
            ToolMappingError: If strict=True and parsing fails
        """
        tools = []

        for i, tool_dict in enumerate(kaizen_tools):
            try:
                tool = KaizenTool.from_dict(tool_dict)

                # Validate
                errors = cls.validate_tool(tool)
                if errors:
                    if strict:
                        raise ToolMappingError(
                            f"Validation failed: {'; '.join(errors)}",
                            tool_name=tool.name or f"tool_{i}",
                            source_format="kaizen",
                            target_format=cls.FORMAT_NAME,
                        )
                    logger.warning(f"Skipping invalid tool {tool.name or i}: {errors}")
                    continue

                tools.append(tool)

            except ToolMappingError:
                raise
            except Exception as e:
                if strict:
                    raise ToolMappingError(
                        f"Failed to parse tool at index {i}",
                        source_format="kaizen",
                        target_format=cls.FORMAT_NAME,
                        reason=str(e),
                    )
                logger.warning(f"Skipping unparseable tool at index {i}: {e}")

        return tools

    @classmethod
    def _convert_json_schema_type(
        cls,
        json_schema_type: str,
    ) -> str:
        """Convert JSON Schema type to a normalized type string.

        Args:
            json_schema_type: Type from JSON Schema

        Returns:
            Normalized type string
        """
        # JSON Schema types map directly
        type_map = {
            "string": "string",
            "number": "number",
            "integer": "integer",
            "boolean": "boolean",
            "array": "array",
            "object": "object",
            "null": "null",
        }
        return type_map.get(json_schema_type, "string")


def extract_tool_call(
    response: Dict[str, Any],
    format_name: str = "openai",
) -> Optional[Dict[str, Any]]:
    """Extract tool call from LLM response.

    Handles different response formats from various providers.

    Args:
        response: Raw LLM response
        format_name: Format of the response ("openai", "anthropic", "gemini")

    Returns:
        Normalized tool call dict with 'name' and 'arguments' keys,
        or None if no tool call found
    """
    if format_name == "openai":
        # OpenAI format: {"tool_calls": [{"function": {"name": ..., "arguments": ...}}]}
        tool_calls = response.get("tool_calls", [])
        if tool_calls:
            tc = tool_calls[0]
            func = tc.get("function", {})
            args_str = func.get("arguments", "{}")
            try:
                args = json.loads(args_str) if isinstance(args_str, str) else args_str
            except json.JSONDecodeError:
                args = {}
            return {
                "id": tc.get("id", ""),
                "name": func.get("name", ""),
                "arguments": args,
            }

    elif format_name == "anthropic":
        # Anthropic format: {"content": [{"type": "tool_use", "name": ..., "input": ...}]}
        content = response.get("content", [])
        for block in content:
            if block.get("type") == "tool_use":
                return {
                    "id": block.get("id", ""),
                    "name": block.get("name", ""),
                    "arguments": block.get("input", {}),
                }

    elif format_name == "gemini":
        # Gemini format: {"candidates": [{"content": {"parts": [{"functionCall": {...}}]}}]}
        candidates = response.get("candidates", [])
        if candidates:
            content = candidates[0].get("content", {})
            parts = content.get("parts", [])
            for part in parts:
                if "functionCall" in part:
                    fc = part["functionCall"]
                    return {
                        "id": "",
                        "name": fc.get("name", ""),
                        "arguments": fc.get("args", {}),
                    }

    return None


def format_tool_result(
    tool_call_id: str,
    result: Any,
    format_name: str = "openai",
    is_error: bool = False,
) -> Dict[str, Any]:
    """Format tool result for inclusion in conversation.

    Args:
        tool_call_id: ID of the tool call
        result: Tool execution result
        format_name: Target format
        is_error: Whether the result is an error

    Returns:
        Formatted tool result for conversation
    """
    # Serialize result to string if needed
    if isinstance(result, dict):
        try:
            content = json.dumps(result)
        except (TypeError, ValueError):
            content = str(result)
    else:
        content = str(result)

    if format_name == "openai":
        return {
            "role": "tool",
            "tool_call_id": tool_call_id,
            "content": content,
        }

    elif format_name == "anthropic":
        return {
            "type": "tool_result",
            "tool_use_id": tool_call_id,
            "content": content,
            "is_error": is_error,
        }

    elif format_name == "gemini":
        return {
            "functionResponse": {
                "name": tool_call_id,  # Gemini uses name, not ID
                "response": {"result": content},
            }
        }

    # Default to OpenAI format
    return {
        "role": "tool",
        "tool_call_id": tool_call_id,
        "content": content,
    }

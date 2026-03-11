"""
OpenAI Tool Mapper

Converts Kaizen tool definitions to/from OpenAI function calling format.

Since Kaizen already uses OpenAI format internally, this mapper primarily:
1. Validates tools against OpenAI's requirements
2. Normalizes tool definitions
3. Handles format variations

OpenAI Function Calling Format:
    {
        "type": "function",
        "function": {
            "name": "tool_name",
            "description": "What the tool does",
            "parameters": {
                "type": "object",
                "properties": {...},
                "required": [...]
            },
            "strict": false
        }
    }
"""

import logging
import re
from typing import Any, Dict, List, Optional

from kaizen.runtime.adapters.tool_mapping.base import (
    KaizenTool,
    ToolMapper,
    ToolMappingError,
)

logger = logging.getLogger(__name__)


class OpenAIToolMapper(ToolMapper):
    """Maps and validates tools for OpenAI's function calling API.

    Since Kaizen uses OpenAI format internally, this mapper primarily
    validates and normalizes tool definitions rather than converting formats.

    For OpenAI Codex/Responses API, this handles:
    - Validation of tool schemas
    - Strict mode requirements
    - Parameter normalization

    Example:
        >>> from kaizen.runtime.adapters.tool_mapping import OpenAIToolMapper
        >>>
        >>> kaizen_tools = [...]
        >>> # Validate and normalize
        >>> openai_tools = OpenAIToolMapper.to_runtime_format(kaizen_tools)
    """

    FORMAT_NAME = "openai"

    # OpenAI function name pattern: ^[a-zA-Z0-9_-]+$
    NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")

    # Maximum lengths
    MAX_NAME_LENGTH = 64
    MAX_DESCRIPTION_LENGTH = 1024

    @classmethod
    def to_runtime_format(
        cls,
        kaizen_tools: List[Dict[str, Any]],
        strict: bool = False,
    ) -> List[Dict[str, Any]]:
        """Validate and normalize tools for OpenAI API.

        Args:
            kaizen_tools: List of tools in Kaizen format
            strict: If True, raise on validation errors

        Returns:
            List of validated tools in OpenAI format

        Raises:
            ToolMappingError: If strict=True and validation fails
        """
        # Parse and validate tools
        tools = cls._parse_kaizen_tools(kaizen_tools, strict=strict)

        openai_tools = []
        for tool in tools:
            # Normalize to OpenAI format
            openai_tool = cls._normalize_tool(tool)
            openai_tools.append(openai_tool)

        return openai_tools

    @classmethod
    def from_runtime_format(
        cls,
        runtime_tools: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Convert OpenAI tools to Kaizen format.

        Since formats are identical, this is mostly pass-through with validation.

        Args:
            runtime_tools: List of tools in OpenAI format

        Returns:
            List of tools in Kaizen format
        """
        # Parse and return (same format)
        tools = cls._parse_kaizen_tools(runtime_tools, strict=False)
        return [tool.to_dict() for tool in tools]

    @classmethod
    def _normalize_tool(cls, tool: KaizenTool) -> Dict[str, Any]:
        """Normalize a tool to OpenAI format.

        Args:
            tool: KaizenTool to normalize

        Returns:
            Normalized tool dictionary
        """
        # Build normalized parameters
        parameters = cls._normalize_parameters(tool.parameters)

        return {
            "type": "function",
            "function": {
                "name": tool.name[: cls.MAX_NAME_LENGTH],
                "description": tool.description[: cls.MAX_DESCRIPTION_LENGTH],
                "parameters": parameters,
                "strict": tool.strict,
            },
        }

    @classmethod
    def _normalize_parameters(cls, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize parameters schema for OpenAI.

        Ensures:
        - type is "object"
        - properties exists
        - required is a list
        - additionalProperties is set for strict mode

        Args:
            parameters: Raw parameters schema

        Returns:
            Normalized parameters schema
        """
        if not parameters:
            return {
                "type": "object",
                "properties": {},
            }

        normalized = dict(parameters)

        # Ensure type is object
        if "type" not in normalized:
            normalized["type"] = "object"

        # Ensure properties exists
        if "properties" not in normalized:
            normalized["properties"] = {}

        # Ensure required is a list
        if "required" in normalized and not isinstance(normalized["required"], list):
            normalized["required"] = list(normalized["required"])

        return normalized

    @classmethod
    def validate_tool(cls, tool: KaizenTool) -> List[str]:
        """Validate tool against OpenAI requirements.

        Args:
            tool: Tool to validate

        Returns:
            List of validation errors
        """
        errors = tool.validate()

        # Name format
        if tool.name and not cls.NAME_PATTERN.match(tool.name):
            errors.append(
                f"OpenAI tool names must match pattern {cls.NAME_PATTERN.pattern}"
            )

        # Name length
        if tool.name and len(tool.name) > cls.MAX_NAME_LENGTH:
            errors.append(
                f"OpenAI tool names must be <= {cls.MAX_NAME_LENGTH} characters"
            )

        # Description length
        if tool.description and len(tool.description) > cls.MAX_DESCRIPTION_LENGTH:
            errors.append(
                f"OpenAI tool descriptions must be <= {cls.MAX_DESCRIPTION_LENGTH} characters"
            )

        # Strict mode requirements
        if tool.strict:
            strict_errors = cls._validate_strict_mode(tool)
            errors.extend(strict_errors)

        return errors

    @classmethod
    def _validate_strict_mode(cls, tool: KaizenTool) -> List[str]:
        """Validate tool for OpenAI strict mode.

        Strict mode requires:
        - additionalProperties: false
        - All properties must be required OR have default
        - Specific JSON Schema subset

        Args:
            tool: Tool to validate

        Returns:
            List of strict mode validation errors
        """
        errors = []
        params = tool.parameters

        if not params:
            return errors

        # Check additionalProperties
        if params.get("additionalProperties") is not False:
            errors.append(
                "Strict mode requires 'additionalProperties: false' in parameters"
            )

        # Check that all properties are listed in required
        properties = params.get("properties", {})
        required = set(params.get("required", []))

        for prop_name in properties:
            if prop_name not in required:
                prop_schema = properties[prop_name]
                # Must have default or be required
                if "default" not in prop_schema:
                    errors.append(
                        f"Strict mode: property '{prop_name}' must be required or have default"
                    )

        return errors

    @classmethod
    def for_responses_api(
        cls,
        kaizen_tools: List[Dict[str, Any]],
        enable_code_interpreter: bool = False,
        enable_file_search: bool = False,
    ) -> List[Dict[str, Any]]:
        """Format tools for OpenAI Responses API.

        The Responses API has additional capabilities that can be enabled.

        Args:
            kaizen_tools: Custom function tools
            enable_code_interpreter: Enable Code Interpreter tool
            enable_file_search: Enable file search tool

        Returns:
            List of tools for Responses API
        """
        tools = cls.to_runtime_format(kaizen_tools, strict=False)

        # Add built-in tools if requested
        if enable_code_interpreter:
            tools.append({"type": "code_interpreter"})

        if enable_file_search:
            tools.append({"type": "file_search"})

        return tools

    @classmethod
    def to_openai_format(
        cls,
        kaizen_tools: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Convenience alias for to_runtime_format.

        Args:
            kaizen_tools: List of tools in Kaizen format

        Returns:
            List of tools in OpenAI format
        """
        return cls.to_runtime_format(kaizen_tools, strict=False)

"""
Gemini Tool Mapper

Converts Kaizen tool definitions to Gemini Function Declarations format.

Gemini Function Declaration Format:
    {
        "name": "tool_name",
        "description": "What the tool does",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "param1": {
                    "type": "STRING",
                    "description": "Parameter description"
                }
            },
            "required": ["param1"]
        }
    }

Key differences from OpenAI:
- Type names are UPPERCASE (STRING, NUMBER, BOOLEAN, OBJECT, ARRAY)
- No "type": "function" wrapper
- Uses "OBJECT" instead of "object"
"""

import logging
from typing import Any, Dict, List

from kaizen.runtime.adapters.tool_mapping.base import (
    KaizenTool,
    ToolMapper,
    ToolMappingError,
)

logger = logging.getLogger(__name__)


class GeminiToolMapper(ToolMapper):
    """Maps Kaizen tools to Gemini Function Declarations format.

    Handles the format conversion between OpenAI-style JSON Schema and
    Gemini's function declaration format which uses uppercase type names.

    Example:
        >>> from kaizen.runtime.adapters.tool_mapping import GeminiToolMapper
        >>>
        >>> kaizen_tools = [{
        ...     "type": "function",
        ...     "function": {
        ...         "name": "search",
        ...         "description": "Search documents",
        ...         "parameters": {
        ...             "type": "object",
        ...             "properties": {
        ...                 "query": {"type": "string", "description": "Search query"}
        ...             },
        ...             "required": ["query"]
        ...         }
        ...     }
        ... }]
        >>>
        >>> # Convert to Gemini format
        >>> gemini_tools = GeminiToolMapper.to_runtime_format(kaizen_tools)
        >>> # Result uses OBJECT, STRING instead of object, string
    """

    FORMAT_NAME = "gemini"

    # JSON Schema to Gemini type mapping
    TYPE_MAP = {
        "string": "STRING",
        "number": "NUMBER",
        "integer": "INTEGER",
        "boolean": "BOOLEAN",
        "array": "ARRAY",
        "object": "OBJECT",
    }

    # Reverse mapping
    REVERSE_TYPE_MAP = {v: k for k, v in TYPE_MAP.items()}

    @classmethod
    def to_runtime_format(
        cls,
        kaizen_tools: List[Dict[str, Any]],
        strict: bool = False,
    ) -> List[Dict[str, Any]]:
        """Convert Kaizen tools to Gemini Function Declarations.

        Args:
            kaizen_tools: List of tools in Kaizen/OpenAI format
            strict: If True, raise on validation errors

        Returns:
            List of Gemini Function Declarations

        Raises:
            ToolMappingError: If strict=True and validation fails
        """
        # Parse and validate tools
        tools = cls._parse_kaizen_tools(kaizen_tools, strict=strict)

        gemini_tools = []
        for tool in tools:
            gemini_tool = cls._to_gemini_declaration(tool)
            gemini_tools.append(gemini_tool)

        return gemini_tools

    @classmethod
    def from_runtime_format(
        cls,
        runtime_tools: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Convert Gemini Function Declarations back to Kaizen format.

        Args:
            runtime_tools: List of Gemini Function Declarations

        Returns:
            List of tools in Kaizen/OpenAI format
        """
        kaizen_tools = []

        for gemini_tool in runtime_tools:
            kaizen_tool = cls._from_gemini_declaration(gemini_tool)
            kaizen_tools.append(kaizen_tool)

        return kaizen_tools

    @classmethod
    def _to_gemini_declaration(cls, tool: KaizenTool) -> Dict[str, Any]:
        """Convert a single KaizenTool to Gemini Function Declaration.

        Args:
            tool: KaizenTool to convert

        Returns:
            Gemini Function Declaration
        """
        declaration = {
            "name": tool.name,
            "description": tool.description,
        }

        # Convert parameters with uppercase types
        if tool.parameters:
            declaration["parameters"] = cls._convert_schema_to_gemini(tool.parameters)
        else:
            declaration["parameters"] = {
                "type": "OBJECT",
                "properties": {},
            }

        return declaration

    @classmethod
    def _from_gemini_declaration(cls, gemini_tool: Dict[str, Any]) -> Dict[str, Any]:
        """Convert Gemini Function Declaration to Kaizen format.

        Args:
            gemini_tool: Gemini Function Declaration

        Returns:
            Tool in Kaizen/OpenAI format
        """
        # Extract and convert parameters
        parameters = gemini_tool.get("parameters", {})
        converted_params = cls._convert_schema_from_gemini(parameters)

        return {
            "type": "function",
            "function": {
                "name": gemini_tool.get("name", ""),
                "description": gemini_tool.get("description", ""),
                "parameters": converted_params,
            },
        }

    @classmethod
    def _convert_schema_to_gemini(cls, schema: Dict[str, Any]) -> Dict[str, Any]:
        """Convert JSON Schema to Gemini format (recursive).

        Args:
            schema: JSON Schema object

        Returns:
            Gemini-formatted schema
        """
        if not schema:
            return {}

        result = {}

        # Convert type to uppercase
        if "type" in schema:
            json_type = schema["type"].lower()
            result["type"] = cls.TYPE_MAP.get(json_type, json_type.upper())

        # Copy description
        if "description" in schema:
            result["description"] = schema["description"]

        # Convert properties recursively
        if "properties" in schema:
            result["properties"] = {}
            for prop_name, prop_schema in schema["properties"].items():
                result["properties"][prop_name] = cls._convert_schema_to_gemini(
                    prop_schema
                )

        # Copy required
        if "required" in schema:
            result["required"] = list(schema["required"])

        # Handle array items
        if "items" in schema:
            result["items"] = cls._convert_schema_to_gemini(schema["items"])

        # Copy enum if present
        if "enum" in schema:
            result["enum"] = list(schema["enum"])

        # Copy format if present
        if "format" in schema:
            result["format"] = schema["format"]

        return result

    @classmethod
    def _convert_schema_from_gemini(cls, schema: Dict[str, Any]) -> Dict[str, Any]:
        """Convert Gemini schema back to JSON Schema format (recursive).

        Args:
            schema: Gemini-formatted schema

        Returns:
            JSON Schema object
        """
        if not schema:
            return {}

        result = {}

        # Convert type to lowercase
        if "type" in schema:
            gemini_type = schema["type"]
            result["type"] = cls.REVERSE_TYPE_MAP.get(gemini_type, gemini_type.lower())

        # Copy description
        if "description" in schema:
            result["description"] = schema["description"]

        # Convert properties recursively
        if "properties" in schema:
            result["properties"] = {}
            for prop_name, prop_schema in schema["properties"].items():
                result["properties"][prop_name] = cls._convert_schema_from_gemini(
                    prop_schema
                )

        # Copy required
        if "required" in schema:
            result["required"] = list(schema["required"])

        # Handle array items
        if "items" in schema:
            result["items"] = cls._convert_schema_from_gemini(schema["items"])

        # Copy enum if present
        if "enum" in schema:
            result["enum"] = list(schema["enum"])

        # Copy format if present
        if "format" in schema:
            result["format"] = schema["format"]

        return result

    @classmethod
    def validate_tool(cls, tool: KaizenTool) -> List[str]:
        """Validate tool against Gemini requirements.

        Args:
            tool: Tool to validate

        Returns:
            List of validation errors
        """
        errors = tool.validate()

        # Gemini-specific validations

        # Name must be valid identifier
        if tool.name:
            if not tool.name[0].isalpha() and tool.name[0] != "_":
                errors.append("Gemini tool names must start with letter or underscore")
            if not all(c.isalnum() or c == "_" for c in tool.name):
                errors.append("Gemini tool names must be alphanumeric with underscores")

        return errors

    @classmethod
    def to_gemini_format(
        cls,
        kaizen_tools: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Convenience alias for to_runtime_format.

        Args:
            kaizen_tools: List of tools in Kaizen format

        Returns:
            List of tools in Gemini format
        """
        return cls.to_runtime_format(kaizen_tools, strict=False)

    @classmethod
    def from_gemini_format(
        cls,
        gemini_tools: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Convenience alias for from_runtime_format.

        Args:
            gemini_tools: List of tools in Gemini format

        Returns:
            List of tools in Kaizen format
        """
        return cls.from_runtime_format(gemini_tools)

    @classmethod
    def wrap_for_api(
        cls,
        kaizen_tools: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Wrap tools for Gemini API request.

        Gemini API expects tools in a specific wrapper structure.

        Args:
            kaizen_tools: List of tools in Kaizen format

        Returns:
            Tools wrapped for Gemini API
        """
        function_declarations = cls.to_runtime_format(kaizen_tools)

        return {"tools": [{"function_declarations": function_declarations}]}

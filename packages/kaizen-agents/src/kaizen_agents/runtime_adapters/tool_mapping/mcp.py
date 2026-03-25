"""
MCP (Model Context Protocol) Tool Mapper

Converts Kaizen tool definitions to MCP format for use with Claude Code adapter.

IMPORTANT: Claude Code already has its native tools (Read, Write, Bash, etc.).
This mapper is for EXTENDING Claude Code with ADDITIONAL custom tools via MCP,
not for replacing its native capabilities.

MCP Format Reference: https://spec.modelcontextprotocol.io/

MCP Tool Schema:
    {
        "name": "tool_name",
        "description": "What the tool does",
        "inputSchema": {
            "type": "object",
            "properties": {...},
            "required": [...]
        }
    }
"""

import logging
from typing import Any, Dict, List

from kaizen.runtime.adapters.tool_mapping.base import (
    KaizenTool,
    ToolMapper,
    ToolMappingError,
)

logger = logging.getLogger(__name__)


class MCPToolMapper(ToolMapper):
    """Maps Kaizen tools to MCP (Model Context Protocol) format.

    Use this mapper when you want to expose custom Kaizen tools to Claude Code
    via MCP. Claude Code's native tools (Read, Write, Bash, etc.) are NOT
    affected - they work automatically.

    Example:
        >>> from kaizen.runtime.adapters.tool_mapping import MCPToolMapper
        >>>
        >>> # Define a custom tool
        >>> kaizen_tools = [{
        ...     "type": "function",
        ...     "function": {
        ...         "name": "search_documents",
        ...         "description": "Search through indexed documents",
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
        >>> # Convert to MCP format
        >>> mcp_tools = MCPToolMapper.to_runtime_format(kaizen_tools)
        >>> # Result: [{"name": "search_documents", "description": ..., "inputSchema": ...}]
    """

    FORMAT_NAME = "mcp"

    # MCP reserved tool names (Claude Code native tools)
    RESERVED_NAMES = {
        "Read",
        "Write",
        "Edit",
        "Bash",
        "Glob",
        "Grep",
        "LS",
        "WebFetch",
        "WebSearch",
        "Task",
        "AskFollowUpQuestion",
        "AttemptCompletion",
        "TodoWrite",
        "Skill",
    }

    @classmethod
    def to_runtime_format(
        cls,
        kaizen_tools: List[Dict[str, Any]],
        strict: bool = False,
    ) -> List[Dict[str, Any]]:
        """Convert Kaizen tools to MCP format.

        Args:
            kaizen_tools: List of tools in Kaizen/OpenAI format
            strict: If True, raise on validation errors

        Returns:
            List of tools in MCP format

        Raises:
            ToolMappingError: If strict=True and validation fails
        """
        # Parse and validate tools
        tools = cls._parse_kaizen_tools(kaizen_tools, strict=strict)

        mcp_tools = []
        for tool in tools:
            # Check for reserved names
            if tool.name in cls.RESERVED_NAMES:
                if strict:
                    raise ToolMappingError(
                        f"Tool name '{tool.name}' is reserved (Claude Code native tool)",
                        tool_name=tool.name,
                        source_format="kaizen",
                        target_format="mcp",
                    )
                logger.warning(
                    f"Skipping tool '{tool.name}': reserved name (Claude Code native tool)"
                )
                continue

            # Convert to MCP format
            mcp_tool = cls._to_mcp_tool(tool)
            mcp_tools.append(mcp_tool)

        return mcp_tools

    @classmethod
    def from_runtime_format(
        cls,
        runtime_tools: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Convert MCP tools back to Kaizen/OpenAI format.

        Args:
            runtime_tools: List of tools in MCP format

        Returns:
            List of tools in Kaizen/OpenAI format
        """
        kaizen_tools = []

        for mcp_tool in runtime_tools:
            kaizen_tool = cls._from_mcp_tool(mcp_tool)
            kaizen_tools.append(kaizen_tool)

        return kaizen_tools

    @classmethod
    def _to_mcp_tool(cls, tool: KaizenTool) -> Dict[str, Any]:
        """Convert a single KaizenTool to MCP format.

        Args:
            tool: KaizenTool to convert

        Returns:
            Tool in MCP format
        """
        # MCP uses inputSchema instead of parameters
        mcp_tool = {
            "name": tool.name,
            "description": tool.description,
        }

        # Convert parameters to inputSchema
        if tool.parameters:
            mcp_tool["inputSchema"] = cls._convert_to_input_schema(tool.parameters)
        else:
            # Empty schema for tools with no parameters
            mcp_tool["inputSchema"] = {
                "type": "object",
                "properties": {},
            }

        return mcp_tool

    @classmethod
    def _from_mcp_tool(cls, mcp_tool: Dict[str, Any]) -> Dict[str, Any]:
        """Convert MCP tool back to Kaizen/OpenAI format.

        Args:
            mcp_tool: Tool in MCP format

        Returns:
            Tool in Kaizen/OpenAI format
        """
        # Extract inputSchema
        input_schema = mcp_tool.get("inputSchema", {})

        # Convert to OpenAI function format
        return {
            "type": "function",
            "function": {
                "name": mcp_tool.get("name", ""),
                "description": mcp_tool.get("description", ""),
                "parameters": input_schema,
            },
        }

    @classmethod
    def _convert_to_input_schema(cls, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Convert OpenAI parameters to MCP inputSchema.

        The formats are largely compatible, but MCP has some nuances.

        Args:
            parameters: OpenAI-style parameters

        Returns:
            MCP-style inputSchema
        """
        # MCP inputSchema is largely compatible with JSON Schema (like OpenAI)
        # Main difference is naming convention and some optional fields

        schema = dict(parameters)

        # Ensure type is object
        if "type" not in schema:
            schema["type"] = "object"

        # Ensure properties exists
        if "properties" not in schema:
            schema["properties"] = {}

        return schema

    @classmethod
    def validate_tool(cls, tool: KaizenTool) -> List[str]:
        """Validate tool against MCP requirements.

        Args:
            tool: Tool to validate

        Returns:
            List of validation errors
        """
        errors = tool.validate()

        # MCP-specific validations
        if tool.name in cls.RESERVED_NAMES:
            errors.append(
                f"Tool name '{tool.name}' conflicts with Claude Code native tool"
            )

        # MCP name restrictions (alphanumeric, underscore, hyphen)
        if tool.name and not all(c.isalnum() or c in "_-" for c in tool.name):
            errors.append(
                "MCP tool names must be alphanumeric with underscores/hyphens"
            )

        # MCP description length recommendation
        if tool.description and len(tool.description) > 1024:
            errors.append("MCP tool descriptions should be under 1024 characters")

        return errors

    @classmethod
    def to_mcp_format(
        cls,
        kaizen_tools: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Convenience alias for to_runtime_format.

        Args:
            kaizen_tools: List of tools in Kaizen format

        Returns:
            List of tools in MCP format
        """
        return cls.to_runtime_format(kaizen_tools, strict=False)

    @classmethod
    def from_mcp_format(
        cls,
        mcp_tools: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Convenience alias for from_runtime_format.

        Args:
            mcp_tools: List of tools in MCP format

        Returns:
            List of tools in Kaizen format
        """
        return cls.from_runtime_format(mcp_tools)

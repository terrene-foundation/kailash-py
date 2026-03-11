"""
Tool format converters for MCP and LLM provider integrations.

Provides utilities to convert between MCP tool format and provider-specific formats
(OpenAI function calling, Anthropic tool use).

MCP Format (from BaseAgent.discover_mcp_tools):
    [{
        "name": "mcp__filesystem__read_file",
        "description": "Read a file from the filesystem",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path"}
            },
            "required": ["path"]
        }
    }]

OpenAI Function Calling Format:
    [{
        "type": "function",
        "function": {
            "name": "mcp__filesystem__read_file",
            "description": "Read a file from the filesystem",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path"}
                },
                "required": ["path"]
            }
        }
    }]

Anthropic Tool Use Format:
    [{
        "name": "mcp__filesystem__read_file",
        "description": "Read a file from the filesystem",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path"}
            },
            "required": ["path"]
        }
    }]

Note: LLMAgentNode internally handles provider-specific formatting,
so we use OpenAI function calling format as the standard intermediate format.
"""

from typing import Any, Dict, List


def convert_mcp_to_openai_tools(
    mcp_tools: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Convert MCP tools to OpenAI function calling format.

    This is the standard format used by LLMAgentNode for all providers.
    The node internally converts to provider-specific formats as needed.

    Args:
        mcp_tools: List of tools from BaseAgent.discover_mcp_tools()
            Each tool has: name, description, inputSchema

    Returns:
        List of tools in OpenAI function calling format
        Each tool has: type="function", function={name, description, parameters}

    Example:
        >>> mcp_tools = [
        ...     {
        ...         "name": "mcp__filesystem__read_file",
        ...         "description": "Read a file",
        ...         "inputSchema": {
        ...             "type": "object",
        ...             "properties": {"path": {"type": "string"}},
        ...             "required": ["path"]
        ...         }
        ...     }
        ... ]
        >>> openai_tools = convert_mcp_to_openai_tools(mcp_tools)
        >>> print(openai_tools[0]["type"])
        function
        >>> print(openai_tools[0]["function"]["name"])
        mcp__filesystem__read_file
    """
    openai_tools = []

    for tool in mcp_tools:
        # Extract MCP tool fields
        name = tool.get("name", "unknown_tool")
        description = tool.get("description", "")
        input_schema = tool.get("inputSchema", {})

        # Convert to OpenAI function calling format
        openai_tool = {
            "type": "function",
            "function": {
                "name": name,
                "description": description,
                "parameters": input_schema,  # MCP inputSchema maps to OpenAI parameters
            },
        }

        openai_tools.append(openai_tool)

    return openai_tools


def convert_mcp_to_anthropic_tools(
    mcp_tools: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Convert MCP tools to Anthropic tool use format.

    Anthropic uses a slightly different format than OpenAI:
    - No "type": "function" wrapper
    - Uses "input_schema" instead of "parameters"

    Args:
        mcp_tools: List of tools from BaseAgent.discover_mcp_tools()

    Returns:
        List of tools in Anthropic tool use format

    Example:
        >>> mcp_tools = [
        ...     {
        ...         "name": "mcp__filesystem__read_file",
        ...         "description": "Read a file",
        ...         "inputSchema": {
        ...             "type": "object",
        ...             "properties": {"path": {"type": "string"}},
        ...             "required": ["path"]
        ...         }
        ...     }
        ... ]
        >>> anthropic_tools = convert_mcp_to_anthropic_tools(mcp_tools)
        >>> print(anthropic_tools[0]["name"])
        mcp__filesystem__read_file
        >>> print("input_schema" in anthropic_tools[0])
        True
    """
    anthropic_tools = []

    for tool in mcp_tools:
        # Extract MCP tool fields
        name = tool.get("name", "unknown_tool")
        description = tool.get("description", "")
        input_schema = tool.get("inputSchema", {})

        # Convert to Anthropic tool use format
        anthropic_tool = {
            "name": name,
            "description": description,
            "input_schema": input_schema,  # MCP inputSchema maps to Anthropic input_schema
        }

        anthropic_tools.append(anthropic_tool)

    return anthropic_tools


def get_tools_for_provider(
    mcp_tools: List[Dict[str, Any]], provider: str
) -> List[Dict[str, Any]]:
    """
    Convert MCP tools to the appropriate format for the given LLM provider.

    Handles provider-specific tool formats automatically.

    Args:
        mcp_tools: List of tools from BaseAgent.discover_mcp_tools()
        provider: LLM provider name ("openai", "anthropic", "ollama", etc.)

    Returns:
        List of tools in provider-specific format

    Note:
        LLMAgentNode currently uses OpenAI function calling format as the standard.
        The node internally converts to provider-specific formats as needed.
        This function provides the foundation for future provider-specific handling.

    Example:
        >>> mcp_tools = await agent.discover_mcp_tools()
        >>> openai_tools = get_tools_for_provider(mcp_tools, "openai")
        >>> anthropic_tools = get_tools_for_provider(mcp_tools, "anthropic")
    """
    provider_lower = (provider or "openai").lower()

    # Note: LLMAgentNode currently uses OpenAI format for all providers
    # This provides the foundation for future provider-specific handling
    if provider_lower == "anthropic":
        # Future: Return Anthropic format when LLMAgentNode supports it
        # For now, return OpenAI format which LLMAgentNode expects
        return convert_mcp_to_openai_tools(mcp_tools)
    else:
        # Default to OpenAI function calling format (used by most providers)
        return convert_mcp_to_openai_tools(mcp_tools)

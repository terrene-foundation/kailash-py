"""
Kaizen Tool Types

Type definitions for tool calling system. Tool execution is now handled via
MCP (Model Context Protocol) instead of ToolRegistry/ToolExecutor.

Migration Note:
    ToolRegistry and ToolExecutor have been removed. Use MCP for tool calling:

    Old (ToolRegistry):
        >>> from kaizen.tools import ToolRegistry, ToolExecutor
        >>> registry = ToolRegistry()
        >>> registry.register(name="my_tool", ...)
        >>> executor = ToolExecutor(registry=registry)
        >>> result = await executor.execute("my_tool", params)

    New (MCP):
        >>> from kaizen.core.base_agent import BaseAgent
        >>> # BaseAgent auto-connects to kaizen_builtin MCP server
        >>> agent = BaseAgent(config=config, signature=signature)
        >>> # 12 builtin tools automatically available
        >>> result = await agent.execute_mcp_tool("bash_command", {"command": "ls"})

Core Types:
    - DangerLevel: Tool safety classification (SAFE, LOW, MEDIUM, HIGH, CRITICAL)
    - ToolCategory: Tool categorization (SYSTEM, FILE, API, etc.)
    - ToolParameter: Tool parameter definition
    - ToolDefinition: Complete tool specification
    - ToolResult: Tool execution result

See Also:
    - kaizen.mcp.builtin_server: MCP server with 12 builtin tools
    - kaizen.core.base_agent: BaseAgent with MCP auto-connect
    - docs/integrations/mcp/: MCP integration documentation
"""

from kaizen.tools.types import (
    ApprovalExtractorFunc,
    DangerLevel,
    ToolCategory,
    ToolDefinition,
    ToolExecutorFunc,
    ToolParameter,
    ToolResult,
    ToolValidationFunc,
)

__all__ = [
    # Core types
    "ToolDefinition",
    "ToolParameter",
    "ToolResult",
    "ToolCategory",
    "DangerLevel",
    # Type aliases
    "ToolExecutorFunc",
    "ToolValidationFunc",
    "ApprovalExtractorFunc",
]

"""
Tool Mapping Infrastructure for External Runtime Adapters

Provides format conversion between Kaizen's tool format (OpenAI function calling)
and the formats required by different external runtimes:

- MCP format: For Claude Code adapter
- OpenAI format: For OpenAI Codex adapter (validation + normalization)
- Gemini format: For Gemini CLI adapter

Usage:
    >>> from kaizen.runtime.adapters.tool_mapping import (
    ...     MCPToolMapper,
    ...     OpenAIToolMapper,
    ...     GeminiToolMapper,
    ... )
    >>>
    >>> kaizen_tools = [{"type": "function", "function": {...}}]
    >>> mcp_tools = MCPToolMapper.to_mcp_format(kaizen_tools)
"""

from kaizen.runtime.adapters.tool_mapping.base import (
    KaizenTool,
    MappedTool,
    ToolMapper,
    ToolMappingError,
)
from kaizen.runtime.adapters.tool_mapping.gemini import GeminiToolMapper
from kaizen.runtime.adapters.tool_mapping.mcp import MCPToolMapper
from kaizen.runtime.adapters.tool_mapping.openai import OpenAIToolMapper

__all__ = [
    # Base types
    "ToolMapper",
    "ToolMappingError",
    "KaizenTool",
    "MappedTool",
    # Mappers
    "MCPToolMapper",
    "OpenAIToolMapper",
    "GeminiToolMapper",
]

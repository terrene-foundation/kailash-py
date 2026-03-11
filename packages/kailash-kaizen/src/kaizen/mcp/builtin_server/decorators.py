"""
Custom decorators for MCP tool metadata.

This module provides the @mcp_tool decorator that adds metadata attributes
to tool functions for use by auto_register_tools().
"""

from typing import Any, Callable, Dict, Optional


def mcp_tool(
    name: Optional[str] = None,
    description: Optional[str] = None,
    parameters: Optional[Dict[str, Any]] = None,
):
    """
    Decorator to add MCP metadata to tool functions.

    This decorator adds metadata attributes to functions that will be
    used by KaizenMCPServer.auto_register_tools() for MCP registration.

    Args:
        name: Tool name (defaults to function name)
        description: Tool description (defaults to docstring)
        parameters: MCP parameter schema (JSON Schema format)

    Returns:
        Decorated function with MCP metadata attributes

    Example:
        @mcp_tool(
            name="read_file",
            description="Read file contents",
            parameters={
                "path": {"type": "string", "description": "File path"},
                "encoding": {"type": "string", "description": "Encoding"},
            }
        )
        async def read_file(path: str, encoding: str = "utf-8") -> dict:
            ...
    """

    def decorator(func: Callable) -> Callable:
        # Attach metadata to function
        func._mcp_name = name or func.__name__
        func._mcp_description = (
            description or (func.__doc__ or f"Tool: {func.__name__}").strip()
        )
        func._mcp_parameters = parameters or {}
        func._is_mcp_tool = True

        return func

    return decorator

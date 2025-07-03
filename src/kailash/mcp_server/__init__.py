"""Model Context Protocol (MCP) Service Layer.

This module provides MCP client and server functionality as services for the
Kailash SDK. MCP capabilities are integrated into LLM agents as built-in
features rather than standalone nodes, enabling seamless tool discovery,
resource access, and prompt templating.

Design Philosophy:
    Provides non-intrusive MCP integration that enhances node capabilities
    without changing the core workflow execution model. MCP services operate
    as background capabilities that nodes can leverage transparently.

Key Components:
    - MCPClient: Connects to MCP servers for tool and resource access
    - MCPServer: Main production-ready server with all features
    - MCPServerBase: Abstract base class for custom server implementations

Upstream Dependencies:
    - Official Anthropic MCP Python SDK for protocol implementation
    - FastMCP framework for server creation and management
    - AsyncIO for asynchronous server/client communication

Downstream Consumers:
    - LLMAgentNode for AI model tool integration
    - Workflow nodes requiring external tool access
    - Custom nodes needing MCP server capabilities

Examples:
    Basic MCP client usage:

    >>> from kailash.mcp_server import MCPClient
    >>> client = MCPClient()
    >>> tools = await client.discover_tools(server_config)
    >>> result = await client.call_tool(server_config, "search", {"query": "AI"})

    Simple MCP server creation:

    >>> from kailash.mcp_server import MCPServer
    >>> server = MCPServer("my-tools")
    >>> @server.tool()
    ... def calculate(a: int, b: int) -> int:
    ...     return a + b
    >>> server.run()
"""

from .client import MCPClient

# For backward compatibility
from .server import EnhancedMCPServer, MCPServer, MCPServerBase, SimpleMCPServer

__all__ = [
    "MCPClient",
    "MCPServer",
    "MCPServerBase",
    # Backward compatibility
    "SimpleMCPServer",
    "EnhancedMCPServer",
]

"""
Enterprise MCP (Model Context Protocol) for Kailash Middleware

Consolidates existing Kailash MCP implementations into the middleware layer
with enhanced features for agent-frontend communication.

Features:
- Enhanced MCP server with production capabilities
- MCP client integration with middleware
- Tool discovery and registration
- Real-time MCP event streaming
- AI agent integration patterns
"""

from .client_integration import (
    MCPClientConfig,
    MCPServerConnection,
    MiddlewareMCPClient,
)
from .enhanced_server import (
    MCPResourceNode,
    MCPServerConfig,
    MCPToolNode,
    MiddlewareMCPServer,
)

# Legacy MCP imports removed - all MCP functionality is now in middleware

__all__ = [
    # Middleware MCP components
    "MiddlewareMCPServer",
    "MCPServerConfig",
    "MCPToolNode",
    "MCPResourceNode",
    "MiddlewareMCPClient",
    "MCPClientConfig",
    "MCPServerConnection",
]

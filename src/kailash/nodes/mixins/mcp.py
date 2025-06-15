"""MCP Capability Mixin for Nodes.

This mixin provides MCP (Model Context Protocol) capabilities to any node,
allowing them to discover and use MCP tools without being an LLM agent.
"""

import asyncio
from typing import TYPE_CHECKING, Any

# Avoid circular import
if TYPE_CHECKING:
    from kailash.middleware.mcp import MiddlewareMCPClient as MCPClient


class MCPCapabilityMixin:
    """Mixin to add MCP capabilities to any node.

    This mixin allows non-LLM nodes to interact with MCP servers,
    discover tools, retrieve resources, and execute tool calls.

    Examples:
        >>> from kailash.nodes.base import BaseNode
        >>> from kailash.nodes.mixins.mcp import MCPCapabilityMixin
        >>>
        >>> class DataProcessorWithMCP(BaseNode, MCPCapabilityMixin):
        ...     def run(self, context, **kwargs):
        ...         # Discover available tools
        ...         tools = self.discover_mcp_tools_sync(
        ...             ["http://localhost:8080"]
        ...         )
        ...
        ...         # Call a specific tool
        ...         result = self.call_mcp_tool_sync(
        ...             "http://localhost:8080",
        ...             "process_data",
        ...             {"data": kwargs.get("data")}
        ...         )
        ...
        ...         return {"processed": result}
    """

    def __init__(self, *args, **kwargs):
        """Initialize the mixin."""
        super().__init__(*args, **kwargs)
        self._mcp_client = None

    @property
    def mcp_client(self):
        """Get or create MCP client instance."""
        if self._mcp_client is None:
            # Lazy import to avoid circular dependency
            from kailash.middleware.mcp import MiddlewareMCPClient

            self._mcp_client = MiddlewareMCPClient()
        return self._mcp_client

    async def discover_mcp_tools(
        self, mcp_servers: list[str | dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Discover tools from MCP servers asynchronously.

        Args:
            mcp_servers: List of MCP server configurations

        Returns:
            List of discovered tools in OpenAI function format
        """
        all_tools = []

        for server in mcp_servers:
            try:
                tools = await self.mcp_client.discover_tools(server)
                all_tools.extend(tools)
            except Exception as e:
                # Log error but continue with other servers
                if hasattr(self, "logger"):
                    self.logger.warning(f"Failed to discover tools from {server}: {e}")

        return all_tools

    async def call_mcp_tool(
        self,
        server_config: str | dict[str, Any],
        tool_name: str,
        arguments: dict[str, Any],
    ) -> Any:
        """Call an MCP tool asynchronously.

        Args:
            server_config: MCP server configuration
            tool_name: Name of the tool to call
            arguments: Tool arguments

        Returns:
            Tool execution result
        """
        return await self.mcp_client.call_tool(server_config, tool_name, arguments)

    async def list_mcp_resources(
        self, server_config: str | dict[str, Any]
    ) -> list[dict[str, Any]]:
        """List available resources from an MCP server.

        Args:
            server_config: MCP server configuration

        Returns:
            List of available resources
        """
        return await self.mcp_client.list_resources(server_config)

    async def read_mcp_resource(
        self, server_config: str | dict[str, Any], uri: str
    ) -> Any:
        """Read a resource from an MCP server.

        Args:
            server_config: MCP server configuration
            uri: Resource URI

        Returns:
            Resource content
        """
        return await self.mcp_client.read_resource(server_config, uri)

    # Synchronous wrappers for non-async nodes

    def discover_mcp_tools_sync(
        self, mcp_servers: list[str | dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Synchronous wrapper for discovering MCP tools.

        Args:
            mcp_servers: List of MCP server configurations

        Returns:
            List of discovered tools
        """
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(self.discover_mcp_tools(mcp_servers))
        finally:
            loop.close()

    def call_mcp_tool_sync(
        self,
        server_config: str | dict[str, Any],
        tool_name: str,
        arguments: dict[str, Any],
    ) -> Any:
        """Synchronous wrapper for calling MCP tools.

        Args:
            server_config: MCP server configuration
            tool_name: Name of the tool to call
            arguments: Tool arguments

        Returns:
            Tool execution result
        """
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(
                self.call_mcp_tool(server_config, tool_name, arguments)
            )
        finally:
            loop.close()

    def list_mcp_resources_sync(
        self, server_config: str | dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Synchronous wrapper for listing MCP resources.

        Args:
            server_config: MCP server configuration

        Returns:
            List of available resources
        """
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(self.list_mcp_resources(server_config))
        finally:
            loop.close()

    def read_mcp_resource_sync(
        self, server_config: str | dict[str, Any], uri: str
    ) -> Any:
        """Synchronous wrapper for reading MCP resources.

        Args:
            server_config: MCP server configuration
            uri: Resource URI

        Returns:
            Resource content
        """
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(self.read_mcp_resource(server_config, uri))
        finally:
            loop.close()

    # Helper methods for common patterns

    def get_mcp_parameter_defaults(self) -> dict[str, Any]:
        """Get default MCP-related parameters for nodes.

        Returns:
            Dictionary of MCP parameter defaults
        """
        return {"mcp_servers": [], "mcp_context": [], "auto_discover_tools": False}

    def format_mcp_tools_for_display(self, tools: list[dict[str, Any]]) -> str:
        """Format MCP tools for human-readable display.

        Args:
            tools: List of tools in OpenAI format

        Returns:
            Formatted string representation
        """
        if not tools:
            return "No tools available"

        lines = ["Available MCP Tools:"]
        for tool in tools:
            func = tool.get("function", {})
            name = func.get("name", "unknown")
            desc = func.get("description", "No description")
            lines.append(f"  - {name}: {desc}")

        return "\n".join(lines)

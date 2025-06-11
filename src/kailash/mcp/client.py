"""MCP Client Service using official Anthropic SDK.

This module provides a comprehensive interface to the Model Context Protocol
using the official Anthropic MCP Python SDK. It enables seamless integration
with MCP servers for tool discovery, resource access, and dynamic capability
extension in workflow nodes.

Note:
    This module requires the official Anthropic MCP SDK to be installed.
    Install with: pip install mcp

Examples:
    Basic tool discovery and execution:

    >>> client = MCPClient()
    >>> # Discover available tools
    >>> tools = await client.discover_tools({
    ...     "transport": "stdio",
    ...     "command": "python",
    ...     "args": ["-m", "my_mcp_server"]
    ... })
    >>> # Execute a tool
    >>> result = await client.call_tool(
    ...     server_config,
    ...     "search_knowledge",
    ...     {"query": "workflow optimization"}
    ... )

    Resource access:

    >>> # List available resources
    >>> resources = await client.list_resources(server_config)
    >>> # Read specific resource
    >>> content = await client.read_resource(
    ...     server_config,
    ...     "file:///docs/api.md"
    ... )
"""

import json
import logging
import os
from contextlib import AsyncExitStack
from typing import Any

logger = logging.getLogger(__name__)


class MCPClient:
    """MCP client service using official Anthropic SDK.

    This is a service class that provides MCP functionality to nodes.
    It handles connection management, tool discovery, and tool execution
    using the official MCP Python SDK.

    Examples:
        Used internally by LLMAgentNode:

        >>> client = MCPClient()
        >>> tools = await client.discover_tools("http://localhost:8080")
        >>> result = await client.call_tool(
        ...     "http://localhost:8080",
        ...     "search",
        ...     {"query": "AI applications"}
        ... )
    """

    def __init__(self):
        """Initialize the MCP client."""
        self._sessions = {}  # Cache active sessions
        self._discovered_tools = {}  # Cache discovered tools
        self._discovered_resources = {}  # Cache discovered resources

    async def discover_tools(
        self, server_config: str | dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Discover available tools from an MCP server.

        Args:
            server_config: Either a URL string or server configuration dict.
                For stdio servers, use dict with 'transport', 'command', 'args'.

        Returns:
            List of tool definitions with name, description, and parameters.
            Returns empty list if server unavailable or on error.

        Examples:
            >>> config = {
            ...     "transport": "stdio",
            ...     "command": "python",
            ...     "args": ["-m", "my_server"]
            ... }
            >>> tools = await client.discover_tools(config)
            >>> print([tool["name"] for tool in tools])
        """
        server_key = self._get_server_key(server_config)

        # Return cached tools if available
        if server_key in self._discovered_tools:
            return self._discovered_tools[server_key]

        try:
            # Import MCP SDK
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client

            # Parse server configuration
            if isinstance(server_config, str):
                # URL-based server (not implemented in this example)
                logger.warning(
                    f"URL-based MCP servers not yet supported: {server_config}"
                )
                return []

            # Extract stdio configuration
            transport = server_config.get("transport", "stdio")
            if transport != "stdio":
                logger.warning(
                    f"Only stdio transport currently supported, got: {transport}"
                )
                return []

            command = server_config.get("command", "python")
            args = server_config.get("args", [])
            env = server_config.get("env", {})

            # Merge environment
            server_env = os.environ.copy()
            server_env.update(env)

            # Create server parameters
            server_params = StdioServerParameters(
                command=command, args=args, env=server_env
            )

            # Connect and discover tools
            async with AsyncExitStack() as stack:
                stdio = await stack.enter_async_context(stdio_client(server_params))
                session = await stack.enter_async_context(
                    ClientSession(stdio[0], stdio[1])
                )

                # Initialize session
                await session.initialize()

                # List tools
                result = await session.list_tools()

                tools = []
                for tool in result.tools:
                    tools.append(
                        {
                            "name": tool.name,
                            "description": tool.description,
                            "parameters": tool.inputSchema,
                        }
                    )

                # Cache the tools
                self._discovered_tools[server_key] = tools
                return tools

        except ImportError:
            logger.error("MCP SDK not available. Install with: pip install mcp")
            return []
        except Exception as e:
            logger.error(f"Failed to discover tools: {e}")
            return []

    async def call_tool(
        self,
        server_config: str | dict[str, Any],
        tool_name: str,
        arguments: dict[str, Any],
    ) -> Any:
        """Call a tool on an MCP server.

        Args:
            server_config: Either a URL string or server configuration dict.
            tool_name: Name of the tool to call.
            arguments: Arguments to pass to the tool.

        Returns:
            Dict containing tool execution result. On success, includes
            'success': True and 'content' or 'result'. On error, includes
            'error' with description.

        Examples:
            >>> result = await client.call_tool(
            ...     server_config,
            ...     "search",
            ...     {"query": "python examples"}
            ... )
            >>> if result.get("success"):
            ...     print(result["content"])
        """
        try:
            # Import MCP SDK
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client

            # Parse server configuration
            if isinstance(server_config, str):
                logger.warning(
                    f"URL-based MCP servers not yet supported: {server_config}"
                )
                return {"error": "URL-based servers not supported"}

            # Extract stdio configuration
            transport = server_config.get("transport", "stdio")
            if transport != "stdio":
                logger.warning(
                    f"Only stdio transport currently supported, got: {transport}"
                )
                return {"error": f"Transport {transport} not supported"}

            command = server_config.get("command", "python")
            args = server_config.get("args", [])
            env = server_config.get("env", {})

            # Merge environment
            server_env = os.environ.copy()
            server_env.update(env)

            # Create server parameters
            server_params = StdioServerParameters(
                command=command, args=args, env=server_env
            )

            # Connect and call tool
            async with AsyncExitStack() as stack:
                stdio = await stack.enter_async_context(stdio_client(server_params))
                session = await stack.enter_async_context(
                    ClientSession(stdio[0], stdio[1])
                )

                # Initialize session
                await session.initialize()

                # Call tool
                result = await session.call_tool(name=tool_name, arguments=arguments)

                # Extract content from result
                if hasattr(result, "content"):
                    content = []
                    for item in result.content:
                        if hasattr(item, "text"):
                            content.append(item.text)
                        else:
                            content.append(str(item))
                    return {"success": True, "content": content}
                else:
                    return {"success": True, "result": str(result)}

        except ImportError:
            logger.error("MCP SDK not available. Install with: pip install mcp")
            return {"error": "MCP SDK not available"}
        except Exception as e:
            logger.error(f"Failed to call tool: {e}")
            return {"error": str(e)}

    async def list_resources(
        self, server_config: str | dict[str, Any]
    ) -> list[dict[str, Any]]:
        """List available resources from an MCP server.

        Args:
            server_config: Either a URL string or server configuration dict.

        Returns:
            List of resource definitions with uri, name, description, mimeType.
            Returns empty list if server unavailable or on error.

        Examples:
            >>> resources = await client.list_resources(server_config)
            >>> for resource in resources:
            ...     print(f"Resource: {resource['name']} ({resource['uri']})")
        """
        server_key = self._get_server_key(server_config)

        # Return cached resources if available
        if server_key in self._discovered_resources:
            return self._discovered_resources[server_key]

        try:
            # Import MCP SDK
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client

            # Parse server configuration (similar to discover_tools)
            if isinstance(server_config, str):
                logger.warning(
                    f"URL-based MCP servers not yet supported: {server_config}"
                )
                return []

            # Extract stdio configuration
            transport = server_config.get("transport", "stdio")
            if transport != "stdio":
                logger.warning(
                    f"Only stdio transport currently supported, got: {transport}"
                )
                return []

            command = server_config.get("command", "python")
            args = server_config.get("args", [])
            env = server_config.get("env", {})

            # Merge environment
            server_env = os.environ.copy()
            server_env.update(env)

            # Create server parameters
            server_params = StdioServerParameters(
                command=command, args=args, env=server_env
            )

            # Connect and list resources
            async with AsyncExitStack() as stack:
                stdio = await stack.enter_async_context(stdio_client(server_params))
                session = await stack.enter_async_context(
                    ClientSession(stdio[0], stdio[1])
                )

                # Initialize session
                await session.initialize()

                # List resources
                result = await session.list_resources()

                resources = []
                for resource in result.resources:
                    resources.append(
                        {
                            "uri": resource.uri,
                            "name": resource.name,
                            "description": resource.description,
                            "mimeType": resource.mimeType,
                        }
                    )

                # Cache the resources
                self._discovered_resources[server_key] = resources
                return resources

        except ImportError:
            logger.error("MCP SDK not available. Install with: pip install mcp")
            return []
        except Exception as e:
            logger.error(f"Failed to list resources: {e}")
            return []

    async def read_resource(self, server_config: str | dict[str, Any], uri: str) -> Any:
        """Read a resource from an MCP server.

        Args:
            server_config: Either a URL string or server configuration dict.
            uri: URI of the resource to read.

        Returns:
            Dict containing resource content. On success, includes 'success': True,
            'content', and 'uri'. On error, includes 'error' with description.

        Examples:
            >>> content = await client.read_resource(
            ...     server_config,
            ...     "file:///docs/readme.md"
            ... )
            >>> if content.get("success"):
            ...     print(content["content"])
        """
        try:
            # Import MCP SDK
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client

            # Parse server configuration (similar to call_tool)
            if isinstance(server_config, str):
                logger.warning(
                    f"URL-based MCP servers not yet supported: {server_config}"
                )
                return {"error": "URL-based servers not supported"}

            # Extract stdio configuration
            transport = server_config.get("transport", "stdio")
            if transport != "stdio":
                logger.warning(
                    f"Only stdio transport currently supported, got: {transport}"
                )
                return {"error": f"Transport {transport} not supported"}

            command = server_config.get("command", "python")
            args = server_config.get("args", [])
            env = server_config.get("env", {})

            # Merge environment
            server_env = os.environ.copy()
            server_env.update(env)

            # Create server parameters
            server_params = StdioServerParameters(
                command=command, args=args, env=server_env
            )

            # Connect and read resource
            async with AsyncExitStack() as stack:
                stdio = await stack.enter_async_context(stdio_client(server_params))
                session = await stack.enter_async_context(
                    ClientSession(stdio[0], stdio[1])
                )

                # Initialize session
                await session.initialize()

                # Read resource
                result = await session.read_resource(uri=uri)

                # Extract content
                if hasattr(result, "contents"):
                    content = []
                    for item in result.contents:
                        if hasattr(item, "text"):
                            content.append(item.text)
                        elif hasattr(item, "blob"):
                            content.append({"blob": item.blob})
                        else:
                            content.append(str(item))
                    return {"success": True, "content": content, "uri": uri}
                else:
                    return {"success": True, "result": str(result), "uri": uri}

        except ImportError:
            logger.error("MCP SDK not available. Install with: pip install mcp")
            return {"error": "MCP SDK not available"}
        except Exception as e:
            logger.error(f"Failed to read resource: {e}")
            return {"error": str(e)}

    def _get_server_key(self, server_config: str | dict[str, Any]) -> str:
        """Generate a unique key for caching server data."""
        if isinstance(server_config, str):
            return server_config
        else:
            # Create a key from server config
            return json.dumps(server_config, sort_keys=True)

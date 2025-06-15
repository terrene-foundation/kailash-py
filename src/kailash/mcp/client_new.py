"""
MCP Client - Clean implementation using official Anthropic MCP SDK.

This is NOT a node - it's a utility class used by LLM agents to interact with MCP servers.
"""

import logging
import os
from typing import Any

# Will use official MCP SDK when available
try:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False


class MCPClient:
    """
    Clean MCP client for connecting to Model Context Protocol servers.

    This client is used internally by LLMAgentNode and other components
    that need MCP capabilities. It provides a simple interface over the
    official MCP SDK.

    Examples:
        >>> client = MCPClient()
        >>>
        >>> # Connect to a server
        >>> async with client.connect_stdio("python", ["-m", "my_mcp_server"]) as session:
        ...     # Discover available tools
        ...     tools = await client.discover_tools(session)
        ...
        ...     # Call a tool
        ...     result = await client.call_tool(
        ...         session,
        ...         "search",
        ...         {"query": "AI in healthcare"}
        ...     )
    """

    def __init__(self):
        """Initialize MCP client."""
        self.logger = logging.getLogger(__name__)

    async def connect_stdio(
        self, command: str, args: list[str], env: dict[str, str] | None = None
    ):
        """
        Connect to an MCP server via stdio transport.

        Args:
            command: Command to run the server
            args: Arguments for the command
            env: Environment variables

        Returns:
            Context manager yielding ClientSession

        Raises:
            ImportError: If MCP SDK is not available
            RuntimeError: If connection fails
        """
        if not MCP_AVAILABLE:
            raise ImportError("MCP SDK not available. Install with: pip install mcp")

        # Merge environment
        server_env = os.environ.copy()
        if env:
            server_env.update(env)

        # Create server parameters
        server_params = StdioServerParameters(
            command=command, args=args, env=server_env
        )

        try:
            # Connect to server
            async with stdio_client(server_params) as (read_stream, write_stream):
                async with ClientSession(read_stream, write_stream) as session:
                    # Initialize session
                    await session.initialize()
                    yield session
        except Exception as e:
            self.logger.error(f"Failed to connect to MCP server: {e}")
            raise RuntimeError(f"MCP connection failed: {e}")

    async def discover_tools(self, session: "ClientSession") -> list[dict[str, Any]]:
        """
        Discover available tools from an MCP server.

        Args:
            session: Active MCP client session

        Returns:
            List of tool definitions with name, description, and schema
        """
        try:
            result = await session.list_tools()
            tools = []

            for tool in result.tools:
                tools.append(
                    {
                        "name": tool.name,
                        "description": tool.description,
                        "inputSchema": tool.inputSchema,
                    }
                )

            return tools

        except Exception as e:
            self.logger.error(f"Failed to discover tools: {e}")
            return []

    async def call_tool(
        self, session: "ClientSession", name: str, arguments: dict[str, Any]
    ) -> Any:
        """
        Call a tool on the MCP server.

        Args:
            session: Active MCP client session
            name: Tool name
            arguments: Tool arguments

        Returns:
            Tool execution result
        """
        try:
            result = await session.call_tool(name=name, arguments=arguments)

            # Extract content from result
            if hasattr(result, "content"):
                content = []
                for item in result.content:
                    if hasattr(item, "text"):
                        content.append({"type": "text", "text": item.text})
                    else:
                        content.append(str(item))
                return content
            else:
                return str(result)

        except Exception as e:
            self.logger.error(f"Failed to call tool '{name}': {e}")
            raise

    async def list_resources(self, session: "ClientSession") -> list[dict[str, Any]]:
        """
        List available resources from an MCP server.

        Args:
            session: Active MCP client session

        Returns:
            List of resource definitions
        """
        try:
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

            return resources

        except Exception as e:
            self.logger.error(f"Failed to list resources: {e}")
            return []

    async def read_resource(self, session: "ClientSession", uri: str) -> Any:
        """
        Read a specific resource from an MCP server.

        Args:
            session: Active MCP client session
            uri: Resource URI

        Returns:
            Resource content
        """
        try:
            result = await session.read_resource(uri=uri)

            # Extract content
            if hasattr(result, "contents"):
                content = []
                for item in result.contents:
                    if hasattr(item, "text"):
                        content.append({"type": "text", "text": item.text})
                    elif hasattr(item, "blob"):
                        content.append({"type": "blob", "data": item.blob})
                    else:
                        content.append(str(item))
                return content
            else:
                return str(result)

        except Exception as e:
            self.logger.error(f"Failed to read resource '{uri}': {e}")
            raise

    async def list_prompts(self, session: "ClientSession") -> list[dict[str, Any]]:
        """
        List available prompts from an MCP server.

        Args:
            session: Active MCP client session

        Returns:
            List of prompt definitions
        """
        try:
            result = await session.list_prompts()
            prompts = []

            for prompt in result.prompts:
                prompt_dict = {
                    "name": prompt.name,
                    "description": prompt.description,
                    "arguments": [],
                }

                if hasattr(prompt, "arguments"):
                    for arg in prompt.arguments:
                        prompt_dict["arguments"].append(
                            {
                                "name": arg.name,
                                "description": arg.description,
                                "required": arg.required,
                            }
                        )

                prompts.append(prompt_dict)

            return prompts

        except Exception as e:
            self.logger.error(f"Failed to list prompts: {e}")
            return []

    async def get_prompt(
        self, session: "ClientSession", name: str, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Get a prompt from an MCP server.

        Args:
            session: Active MCP client session
            name: Prompt name
            arguments: Prompt arguments

        Returns:
            Prompt with messages
        """
        try:
            result = await session.get_prompt(name=name, arguments=arguments)

            # Extract messages
            messages = []
            if hasattr(result, "messages"):
                for msg in result.messages:
                    messages.append(
                        {
                            "role": msg.role,
                            "content": (
                                msg.content.text
                                if hasattr(msg.content, "text")
                                else str(msg.content)
                            ),
                        }
                    )

            return {"name": name, "messages": messages, "arguments": arguments}

        except Exception as e:
            self.logger.error(f"Failed to get prompt '{name}': {e}")
            raise


# Convenience functions for LLM agents
async def discover_and_prepare_tools(
    mcp_servers: list[str | dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Discover tools from multiple MCP servers and prepare them for LLM use.

    Args:
        mcp_servers: List of server URLs or configurations

    Returns:
        List of tool definitions ready for LLM function calling
    """
    client = MCPClient()
    all_tools = []

    for server in mcp_servers:
        try:
            # Parse server configuration
            if isinstance(server, str):
                # Simple URL format - not supported in stdio
                continue

            if server.get("transport") == "stdio":
                command = server.get("command", "python")
                args = server.get("args", [])
                env = server.get("env", {})

                async with client.connect_stdio(command, args, env) as session:
                    tools = await client.discover_tools(session)

                    # Tag tools with server info
                    for tool in tools:
                        tool["server"] = server.get("name", "mcp_server")
                        tool["server_config"] = server

                    all_tools.extend(tools)

        except Exception as e:
            logging.warning(f"Failed to discover tools from {server}: {e}")

    return all_tools

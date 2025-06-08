"""
MCP Server - Base class for creating MCP servers using FastMCP.

This provides a clean way to create MCP servers that run as standalone services,
not as workflow nodes.
"""

import asyncio
import logging
import signal
import sys
from typing import Callable, List, Optional

try:
    from mcp.server import Server
    from mcp.server.models import InitializationOptions
    from mcp.types import Resource, TextContent, Tool

    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False


class MCPServer:
    """
    Base class for creating MCP servers.

    This class provides a foundation for building MCP servers that expose
    tools, resources, and prompts. Servers run as standalone processes,
    not as workflow nodes.

    Examples:
        >>> class MyServer(MCPServer):
        ...     def setup(self):
        ...         @self.tool()
        ...         def search(query: str) -> str:
        ...             return f"Searching for: {query}"
        ...
        ...         @self.resource("data://example")
        ...         def get_example():
        ...             return "Example data"
        >>>
        >>> server = MyServer("my-server", port=8080)
        >>> server.run()  # Runs until stopped
    """

    def __init__(self, name: str, port: Optional[int] = None):
        """
        Initialize MCP server.

        Args:
            name: Server name
            port: Port for HTTP transport (None for stdio)
        """
        if not MCP_AVAILABLE:
            raise ImportError("MCP SDK not available. Install with: pip install mcp")

        self.name = name
        self.port = port
        self.logger = logging.getLogger(f"mcp.{name}")

        # Create MCP server
        self.server = Server(name)
        self._setup_done = False
        self._tools = {}
        self._resources = {}
        self._prompts = {}

        # Setup signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals."""
        self.logger.info(f"Received signal {signum}, shutting down...")
        sys.exit(0)

    def setup(self):
        """
        Override this method to setup server tools, resources, and prompts.

        Example:
            def setup(self):
                @self.tool()
                def my_tool(arg: str) -> str:
                    return f"Processed: {arg}"
        """
        pass

    def tool(self, name: Optional[str] = None, description: Optional[str] = None):
        """
        Decorator to register a tool with the MCP server.

        Args:
            name: Tool name (defaults to function name)
            description: Tool description (defaults to docstring)

        Returns:
            Decorator function
        """

        def decorator(func: Callable):
            tool_name = name or func.__name__
            tool_desc = description or (func.__doc__ or "").strip()

            # Register with MCP server
            @self.server.call_tool()
            async def handle_tool_call(name: str, arguments: dict) -> List[TextContent]:
                if name == tool_name:
                    try:
                        # Call the tool function
                        if asyncio.iscoroutinefunction(func):
                            result = await func(**arguments)
                        else:
                            result = func(**arguments)

                        # Convert result to TextContent
                        if isinstance(result, str):
                            return [TextContent(type="text", text=result)]
                        else:
                            import json

                            return [
                                TextContent(
                                    type="text", text=json.dumps(result, indent=2)
                                )
                            ]
                    except Exception as e:
                        error_msg = f"Tool '{tool_name}' failed: {str(e)}"
                        self.logger.error(error_msg, exc_info=True)
                        return [TextContent(type="text", text=f"Error: {error_msg}")]

                raise ValueError(f"Unknown tool: {name}")

            # Store tool metadata
            self._tools[tool_name] = {
                "name": tool_name,
                "description": tool_desc,
                "function": func,
            }

            return func

        return decorator

    def resource(
        self, uri: str, name: Optional[str] = None, description: Optional[str] = None
    ):
        """
        Decorator to register a resource with the MCP server.

        Args:
            uri: Resource URI
            name: Resource name
            description: Resource description

        Returns:
            Decorator function
        """

        def decorator(func: Callable):
            resource_name = name or uri.split("/")[-1]
            resource_desc = description or (func.__doc__ or "").strip()

            # Store resource metadata
            self._resources[uri] = {
                "uri": uri,
                "name": resource_name,
                "description": resource_desc,
                "function": func,
            }

            return func

        return decorator

    def _setup_handlers(self):
        """Setup MCP protocol handlers."""
        if self._setup_done:
            return

        # Call user setup
        self.setup()

        # Register list_tools handler
        @self.server.list_tools()
        async def handle_list_tools() -> List[Tool]:
            tools = []
            for tool_name, tool_info in self._tools.items():
                # Generate input schema from function signature
                import inspect

                sig = inspect.signature(tool_info["function"])

                properties = {}
                required = []

                for param_name, param in sig.parameters.items():
                    if param_name == "self":
                        continue

                    # Determine type
                    param_type = "string"  # Default
                    if param.annotation != inspect.Parameter.empty:
                        if param.annotation is int:
                            param_type = "integer"
                        elif param.annotation is float:
                            param_type = "number"
                        elif param.annotation is bool:
                            param_type = "boolean"
                        elif param.annotation is dict:
                            param_type = "object"
                        elif param.annotation is list:
                            param_type = "array"

                    properties[param_name] = {
                        "type": param_type,
                        "description": f"Parameter {param_name}",
                    }

                    if param.default == inspect.Parameter.empty:
                        required.append(param_name)

                input_schema = {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                }

                tools.append(
                    Tool(
                        name=tool_name,
                        description=tool_info["description"],
                        inputSchema=input_schema,
                    )
                )

            return tools

        # Register list_resources handler
        @self.server.list_resources()
        async def handle_list_resources() -> List[Resource]:
            resources = []
            for uri, resource_info in self._resources.items():
                resources.append(
                    Resource(
                        uri=uri,
                        name=resource_info["name"],
                        description=resource_info["description"],
                        mimeType="text/plain",  # Default, could be customized
                    )
                )
            return resources

        # Register read_resource handler
        @self.server.read_resource()
        async def handle_read_resource(uri: str) -> List[TextContent]:
            if uri in self._resources:
                resource_info = self._resources[uri]
                func = resource_info["function"]

                try:
                    # Call the resource function
                    if asyncio.iscoroutinefunction(func):
                        result = await func()
                    else:
                        result = func()

                    # Convert result to TextContent
                    if isinstance(result, str):
                        return [TextContent(type="text", text=result)]
                    else:
                        import json

                        return [
                            TextContent(type="text", text=json.dumps(result, indent=2))
                        ]
                except Exception as e:
                    error_msg = f"Resource '{uri}' failed: {str(e)}"
                    self.logger.error(error_msg, exc_info=True)
                    return [TextContent(type="text", text=f"Error: {error_msg}")]

            raise ValueError(f"Resource not found: {uri}")

        self._setup_done = True

    def run(self):
        """
        Run the MCP server.

        This method blocks until the server is stopped.
        """
        self._setup_handlers()

        self.logger.info(f"Starting MCP server '{self.name}'")

        if self.port is not None:
            # HTTP/SSE transport
            self.logger.info(f"Server will listen on port {self.port}")
            # Note: Actual HTTP server implementation would go here
            # For now, we'll use stdio as the primary transport

        # Run with stdio transport
        import mcp.server.stdio

        # Configure server options
        init_options = InitializationOptions(
            server_name=self.name,
            server_version="1.0.0",
            capabilities=self.server.get_capabilities(),
        )

        # Run the server
        asyncio.run(
            mcp.server.stdio.stdio_server(self.server.request_handlers, init_options)
        )

    async def arun(self):
        """
        Async version of run().

        Use this if you need to run the server in an existing async context.
        """
        self._setup_handlers()

        self.logger.info(f"Starting MCP server '{self.name}' (async)")

        import mcp.server.stdio

        init_options = InitializationOptions(
            server_name=self.name,
            server_version="1.0.0",
            capabilities=self.server.get_capabilities(),
        )

        await mcp.server.stdio.stdio_server(self.server.request_handlers, init_options)

"""MCP Server Framework using official Anthropic SDK.

This module provides a comprehensive framework for creating MCP servers using
the official FastMCP framework from Anthropic. Servers run as long-lived
services that expose tools, resources, and prompts to MCP clients, enabling
dynamic capability extension for AI workflows.

Note:
    This module requires the FastMCP framework to be installed.
    Install with: pip install 'mcp[server]'

Examples:
    Basic server with tools:

    >>> from kailash.mcp.server import MCPServer
    >>> class MyServer(MCPServer):
    ...     def setup(self):
    ...         @self.add_tool()
    ...         def calculate(a: int, b: int) -> int:
    ...             return a + b
    >>> server = MyServer("calculator", port=8080)
    >>> server.start()

    Quick server creation:

    >>> from kailash.mcp.server import SimpleMCPServer
    >>> server = SimpleMCPServer("my-tools")
    >>> @server.tool()
    ... def search(query: str) -> list:
    ...     return [f"Result for {query}"]
    >>> server.start()
"""

import logging
from abc import ABC, abstractmethod
from collections.abc import Callable

logger = logging.getLogger(__name__)


class MCPServer(ABC):
    """Base class for MCP servers using FastMCP.

    This provides a framework for creating MCP servers that expose
    tools, resources, and prompts via the Model Context Protocol.

    Examples:
        Creating a custom server:

        >>> class MyServer(MCPServer):
        ...     def setup(self):
        ...         @self.add_tool()
        ...         def search(query: str) -> str:
        ...             return f"Results for: {query}"
        ...         @self.add_resource("data://example")
        ...         def get_example():
        ...             return "Example data"
        >>> server = MyServer("my-server", port=8080)
        >>> server.start()  # Runs until stopped
    """

    def __init__(self, name: str, port: int = 8080, host: str = "localhost"):
        """Initialize the MCP server.

        Args:
            name: Name of the server.
            port: Port to listen on (default: 8080).
            host: Host to bind to (default: "localhost").
        """
        self.name = name
        self.port = port
        self.host = host
        self._mcp = None
        self._running = False

    @abstractmethod
    def setup(self):
        """Setup server tools, resources, and prompts.

        This method should be implemented by subclasses to define
        the server's capabilities using decorators.

        Note:
            Use @self.add_tool(), @self.add_resource(uri), and
            @self.add_prompt(name) decorators to register capabilities.
        """

    def add_tool(self):
        """Decorator to add a tool to the server.

        Returns:
            Function decorator for registering tools.

        Examples:
            >>> @server.add_tool()
            ... def calculate(a: int, b: int) -> int:
            ...     '''Add two numbers'''
            ...     return a + b
        """

        def decorator(func: Callable):
            if self._mcp is None:
                self._init_mcp()

            # Use FastMCP's tool decorator
            return self._mcp.tool()(func)

        return decorator

    def add_resource(self, uri: str):
        """Decorator to add a resource to the server.

        Args:
            uri: URI pattern for the resource (supports wildcards).

        Returns:
            Function decorator for registering resources.

        Examples:
            >>> @server.add_resource("file:///data/*")
            ... def get_file(path: str) -> str:
            ...     return f"Content of {path}"
        """

        def decorator(func: Callable):
            if self._mcp is None:
                self._init_mcp()

            # Use FastMCP's resource decorator
            return self._mcp.resource(uri)(func)

        return decorator

    def add_prompt(self, name: str):
        """Decorator to add a prompt template to the server.

        Args:
            name: Name of the prompt.

        Returns:
            Function decorator for registering prompts.

        Examples:
            >>> @server.add_prompt("analyze")
            ... def analyze_prompt(data: str) -> str:
            ...     return f"Please analyze the following data: {data}"
        """

        def decorator(func: Callable):
            if self._mcp is None:
                self._init_mcp()

            # Use FastMCP's prompt decorator
            return self._mcp.prompt(name)(func)

        return decorator

    def _init_mcp(self):
        """Initialize the FastMCP instance."""
        try:
            from mcp.server.fastmcp import FastMCP

            self._mcp = FastMCP(self.name)
        except ImportError:
            logger.error(
                "FastMCP not available. Install with: pip install 'mcp[server]'"
            )
            raise

    def start(self):
        """Start the MCP server.

        This runs the server as a long-lived process until stopped.

        Raises:
            ImportError: If FastMCP is not available.
            Exception: If server fails to start.
        """
        if self._mcp is None:
            self._init_mcp()

        # Run setup to register tools/resources
        self.setup()

        logger.info(f"Starting MCP server '{self.name}' on {self.host}:{self.port}")
        self._running = True

        try:
            # Run the FastMCP server
            logger.info("Running FastMCP server in stdio mode")
            self._mcp.run()
        except Exception as e:
            logger.error(f"Failed to start server: {e}")
            raise
        finally:
            self._running = False

    def stop(self):
        """Stop the MCP server."""
        logger.info(f"Stopping MCP server '{self.name}'")
        self._running = False
        # In a real implementation, we'd need to handle graceful shutdown


class SimpleMCPServer(MCPServer):
    """Simple MCP server for basic use cases.

    This provides an easy way to create MCP servers without subclassing.

    Examples:
        >>> server = SimpleMCPServer("my-server")
        >>> @server.tool()
        ... def add(a: int, b: int) -> int:
        ...     return a + b
        >>> server.start()
    """

    def __init__(self, name: str, port: int = 8080, host: str = "localhost"):
        """Initialize the simple MCP server.

        Args:
            name: Name of the server.
            port: Port to listen on (default: 8080).
            host: Host to bind to (default: "localhost").
        """
        super().__init__(name, port, host)
        self._tools = []
        self._resources = []
        self._prompts = []

    def tool(self):
        """Decorator to add a tool.

        Returns:
            Function decorator for registering tools.
        """

        def decorator(func):
            self._tools.append(func)
            return func

        return decorator

    def resource(self, uri: str):
        """Decorator to add a resource.

        Args:
            uri: URI pattern for the resource.

        Returns:
            Function decorator for registering resources.
        """

        def decorator(func):
            self._resources.append((uri, func))
            return func

        return decorator

    def prompt(self, name: str):
        """Decorator to add a prompt.

        Args:
            name: Name of the prompt.

        Returns:
            Function decorator for registering prompts.
        """

        def decorator(func):
            self._prompts.append((name, func))
            return func

        return decorator

    def setup(self):
        """Setup the server with registered components.

        Registers all tools, resources, and prompts that were decorated
        before calling start().
        """
        # Register all tools
        for tool_func in self._tools:
            self.add_tool()(tool_func)

        # Register all resources
        for uri, resource_func in self._resources:
            self.add_resource(uri)(resource_func)

        # Register all prompts
        for name, prompt_func in self._prompts:
            self.add_prompt(name)(prompt_func)

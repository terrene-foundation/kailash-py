"""
MCP Server Framework with production-ready capabilities.

This module provides both basic and enhanced MCP server implementations using
the official FastMCP framework from Anthropic. Servers run as long-lived
services that expose tools, resources, and prompts to MCP clients.

Basic Usage:
    Abstract base class for custom servers:

    >>> class MyServer(MCPServerBase):
    ...     def setup(self):
    ...         @self.add_tool()
    ...         def calculate(a: int, b: int) -> int:
    ...             return a + b
    >>> server = MyServer("calculator")
    >>> server.start()

Production Usage:
    Main server with all production features:

    >>> from kailash.mcp_server import MCPServer
    >>> server = MCPServer("my-server", enable_cache=True)
    >>> @server.tool(cache_key="search", cache_ttl=600)
    ... def search(query: str) -> dict:
    ...     return {"results": f"Found data for {query}"}
    >>> server.run()
"""

import asyncio
import functools
import logging
from abc import ABC, abstractmethod
from collections.abc import Callable
from pathlib import Path
from typing import Any, Dict, Optional, TypeVar, Union

from .utils import CacheManager, ConfigManager, MetricsCollector, format_response

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


class MCPServerBase(ABC):
    """Base class for MCP servers using FastMCP.

    This provides a framework for creating MCP servers that expose
    tools, resources, and prompts via the Model Context Protocol.

    Examples:
        Creating a custom server:

        >>> class MyServer(MCPServerBase):
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
            from mcp.server import FastMCP

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


class EnhancedMCPServer:
    """
    Production-ready MCP server (available as SimpleMCPServer).

    This is the main concrete MCP server implementation with all production
    features available. Features can be enabled/disabled as needed.

    Features available:
    - Caching with TTL support (enable_cache=True)
    - Metrics collection and monitoring (enable_metrics=True)
    - Response formatting utilities (enable_formatting=True)
    - Hierarchical configuration management
    - Error handling and logging

    Examples:
        Basic usage (recommended):
        >>> from kailash.mcp_server import MCPServer
        >>> server = MCPServer("my-server")
        >>> @server.tool()
        ... def search(query: str) -> dict:
        ...     return {"results": f"Found: {query}"}
        >>> server.run()

        With production features enabled:
        >>> server = MCPServer("my-server", enable_cache=True, enable_metrics=True)
        >>> @server.tool(cache_key="search", cache_ttl=600)
        ... def search(query: str) -> dict:
        ...     return {"results": f"Found: {query}"}
        >>> server.run()
    """

    def __init__(
        self,
        name: str,
        config_file: Optional[Union[str, Path]] = None,
        enable_cache: bool = True,
        cache_ttl: int = 300,
        enable_metrics: bool = True,
        enable_formatting: bool = True,
    ):
        """
        Initialize enhanced MCP server.

        Args:
            name: Server name
            config_file: Optional configuration file path
            enable_cache: Whether to enable caching (default: True)
            cache_ttl: Default cache TTL in seconds (default: 300)
            enable_metrics: Whether to enable metrics collection (default: True)
            enable_formatting: Whether to enable response formatting (default: True)
        """
        self.name = name

        # Initialize configuration
        self.config = ConfigManager(config_file)

        # Set default configuration values
        self.config.update(
            {
                "server": {"name": name, "version": "1.0.0", "transport": "stdio"},
                "cache": {
                    "enabled": enable_cache,
                    "default_ttl": cache_ttl,
                    "max_size": 128,
                },
                "metrics": {
                    "enabled": enable_metrics,
                    "collect_performance": True,
                    "collect_usage": True,
                },
                "formatting": {
                    "enabled": enable_formatting,
                    "default_format": "markdown",
                },
            }
        )

        # Initialize components
        self.cache = CacheManager(
            enabled=self.config.get("cache.enabled", enable_cache),
            default_ttl=self.config.get("cache.default_ttl", cache_ttl),
        )

        self.metrics = MetricsCollector(
            enabled=self.config.get("metrics.enabled", enable_metrics),
            collect_performance=self.config.get("metrics.collect_performance", True),
            collect_usage=self.config.get("metrics.collect_usage", True),
        )

        # FastMCP server instance (initialized lazily)
        self._mcp = None
        self._running = False

        # Tool registry for management
        self._tool_registry: Dict[str, Dict[str, Any]] = {}

    def _init_mcp(self):
        """Initialize FastMCP server."""
        if self._mcp is not None:
            return

        try:
            # Now we can safely import from external mcp.server (no namespace collision)
            from mcp.server import FastMCP

            self._mcp = FastMCP(self.name)
            logger.info(f"Initialized FastMCP server: {self.name}")
        except ImportError as e:
            logger.error(
                f"FastMCP import failed with: {e}. Details: {type(e).__name__}"
            )
            logger.error(
                "FastMCP not available. Install with: pip install 'mcp[server]'"
            )
            raise ImportError(
                "FastMCP not available. Install with: pip install 'mcp[server]'"
            ) from e

    def tool(
        self,
        cache_key: Optional[str] = None,
        cache_ttl: Optional[int] = None,
        format_response: Optional[str] = None,
    ):
        """
        Enhanced tool decorator with optional caching and metrics.

        Args:
            cache_key: Optional cache key for caching results
            cache_ttl: Optional TTL override for this tool
            format_response: Optional response format ("json", "markdown", "table", etc.)

        Returns:
            Decorated function with enhanced capabilities

        Example:
            @server.tool(cache_key="weather", cache_ttl=600, format_response="markdown")
            async def get_weather(city: str) -> dict:
                # Expensive API call - will be cached for 10 minutes
                return await fetch_weather_data(city)
        """

        def decorator(func: F) -> F:
            if self._mcp is None:
                self._init_mcp()

            # Get function name for registration
            tool_name = func.__name__

            # Create enhanced wrapper
            enhanced_func = self._create_enhanced_tool(
                func, tool_name, cache_key, cache_ttl, format_response
            )

            # Register with FastMCP
            mcp_tool = self._mcp.tool()(enhanced_func)

            # Track in registry
            self._tool_registry[tool_name] = {
                "function": mcp_tool,
                "original_function": func,
                "cached": cache_key is not None,
                "cache_key": cache_key,
                "cache_ttl": cache_ttl,
                "format_response": format_response,
            }

            logger.debug(
                f"Registered tool: {tool_name} (cached: {cache_key is not None})"
            )
            return mcp_tool

        return decorator

    def _create_enhanced_tool(
        self,
        func: F,
        tool_name: str,
        cache_key: Optional[str],
        cache_ttl: Optional[int],
        response_format: Optional[str],
    ) -> F:
        """Create enhanced tool function with caching, metrics, and formatting."""

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            # Apply metrics tracking
            start_time = None
            if self.metrics.enabled:
                import time

                start_time = time.time()

            try:
                # Try cache first if enabled
                if cache_key and self.cache.enabled:
                    cache = self.cache.get_cache(cache_key, ttl=cache_ttl)
                    cache_lookup_key = self.cache._create_cache_key(
                        tool_name, args, kwargs
                    )

                    result = cache.get(cache_lookup_key)
                    if result is not None:
                        logger.debug(f"Cache hit for {tool_name}")
                        if self.metrics.enabled:
                            latency = time.time() - start_time
                            self.metrics.track_tool_call(tool_name, latency, True)
                        return self._format_response(result, response_format)

                # Execute function
                result = func(*args, **kwargs)

                # Cache result if enabled
                if cache_key and self.cache.enabled:
                    cache.set(cache_lookup_key, result)
                    logger.debug(f"Cached result for {tool_name}")

                # Track success metrics
                if self.metrics.enabled:
                    latency = time.time() - start_time
                    self.metrics.track_tool_call(tool_name, latency, True)

                return self._format_response(result, response_format)

            except Exception as e:
                # Track error metrics
                if self.metrics.enabled and start_time:
                    latency = time.time() - start_time
                    self.metrics.track_tool_call(
                        tool_name, latency, False, type(e).__name__
                    )

                logger.error(f"Error in tool {tool_name}: {e}")
                raise

        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            # Apply metrics tracking
            start_time = None
            if self.metrics.enabled:
                import time

                start_time = time.time()

            try:
                # Try cache first if enabled
                if cache_key and self.cache.enabled:
                    cache = self.cache.get_cache(cache_key, ttl=cache_ttl)
                    cache_lookup_key = self.cache._create_cache_key(
                        tool_name, args, kwargs
                    )

                    result = cache.get(cache_lookup_key)
                    if result is not None:
                        logger.debug(f"Cache hit for {tool_name}")
                        if self.metrics.enabled:
                            latency = time.time() - start_time
                            self.metrics.track_tool_call(tool_name, latency, True)
                        return self._format_response(result, response_format)

                # Execute function
                result = await func(*args, **kwargs)

                # Cache result if enabled
                if cache_key and self.cache.enabled:
                    cache.set(cache_lookup_key, result)
                    logger.debug(f"Cached result for {tool_name}")

                # Track success metrics
                if self.metrics.enabled:
                    latency = time.time() - start_time
                    self.metrics.track_tool_call(tool_name, latency, True)

                return self._format_response(result, response_format)

            except Exception as e:
                # Track error metrics
                if self.metrics.enabled and start_time:
                    latency = time.time() - start_time
                    self.metrics.track_tool_call(
                        tool_name, latency, False, type(e).__name__
                    )

                logger.error(f"Error in tool {tool_name}: {e}")
                raise

        # Return appropriate wrapper based on function type
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    def _format_response(self, result: Any, response_format: Optional[str]) -> Any:
        """Format response if formatting is enabled."""
        if not self.config.get("formatting.enabled", True) or not response_format:
            return result

        try:
            return format_response(result, response_format)
        except Exception as e:
            logger.warning(f"Failed to format response: {e}")
            return result

    def resource(self, uri: str):
        """
        Add resource with metrics tracking.

        Args:
            uri: Resource URI pattern

        Returns:
            Decorated function
        """

        def decorator(func: F) -> F:
            if self._mcp is None:
                self._init_mcp()

            # Wrap with metrics if enabled
            if self.metrics.enabled:
                func = self.metrics.track_tool(f"resource:{uri}")(func)

            return self._mcp.resource(uri)(func)

        return decorator

    def prompt(self, name: str):
        """
        Add prompt with metrics tracking.

        Args:
            name: Prompt name

        Returns:
            Decorated function
        """

        def decorator(func: F) -> F:
            if self._mcp is None:
                self._init_mcp()

            # Wrap with metrics if enabled
            if self.metrics.enabled:
                func = self.metrics.track_tool(f"prompt:{name}")(func)

            return self._mcp.prompt(name)(func)

        return decorator

    def get_tool_stats(self) -> Dict[str, Any]:
        """Get statistics for all registered tools."""
        stats = {
            "registered_tools": len(self._tool_registry),
            "cached_tools": sum(1 for t in self._tool_registry.values() if t["cached"]),
            "tools": {},
        }

        for tool_name, tool_info in self._tool_registry.items():
            stats["tools"][tool_name] = {
                "cached": tool_info["cached"],
                "cache_key": tool_info.get("cache_key"),
                "format_response": tool_info.get("format_response"),
            }

        return stats

    def get_server_stats(self) -> Dict[str, Any]:
        """Get comprehensive server statistics."""
        stats = {
            "server": {
                "name": self.name,
                "running": self._running,
                "config": self.config.to_dict(),
            },
            "tools": self.get_tool_stats(),
        }

        if self.metrics.enabled:
            stats["metrics"] = self.metrics.export_metrics()

        if self.cache.enabled:
            stats["cache"] = self.cache.stats()

        return stats

    def clear_cache(self, cache_name: Optional[str] = None) -> None:
        """Clear cache(s)."""
        if cache_name:
            cache = self.cache.get_cache(cache_name)
            cache.clear()
            logger.info(f"Cleared cache: {cache_name}")
        else:
            self.cache.clear_all()
            logger.info("Cleared all caches")

    def run(self):
        """Run the MCP server."""
        if self._mcp is None:
            self._init_mcp()

        logger.info(f"Starting enhanced MCP server: {self.name}")
        logger.info(f"Cache enabled: {self.cache.enabled}")
        logger.info(f"Metrics enabled: {self.metrics.enabled}")

        self._running = True

        try:
            self._mcp.run()
        except KeyboardInterrupt:
            logger.info("Server stopped by user")
        except Exception as e:
            logger.error(f"Server error: {e}")
            raise
        finally:
            self._running = False


# Clean public API design:
# - MCPServerBase: Abstract base for custom implementations (e.g., AIRegistryServer)
# - MCPServer: Main concrete server with all production features
# - SimpleMCPServer: Alias for backward compatibility
# - EnhancedMCPServer: Alias for backward compatibility
MCPServer = EnhancedMCPServer
SimpleMCPServer = EnhancedMCPServer

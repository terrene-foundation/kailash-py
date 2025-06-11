"""
Enhanced MCP Server with production-ready capabilities.

This module provides an enhanced MCP server that includes caching, configuration,
metrics, and other production features by default, while maintaining compatibility
with the official Anthropic FastMCP framework.
"""

import asyncio
import functools
import logging
from pathlib import Path
from typing import Any, Callable, Dict, Optional, TypeVar, Union

from .utils import CacheManager, ConfigManager, MetricsCollector, format_response

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


class EnhancedMCPServer:
    """
    Production-ready MCP server with enhanced capabilities.

    Features included by default:
    - Caching with TTL support
    - Hierarchical configuration management
    - Metrics collection and monitoring
    - Response formatting utilities
    - Error handling and logging

    All features can be disabled if not needed.
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
            from mcp.server.fastmcp import FastMCP

            self._mcp = FastMCP(self.name)
            logger.info(f"Initialized FastMCP server: {self.name}")
        except ImportError:
            logger.error(
                "FastMCP not available. Install with: pip install 'mcp[server]'"
            )
            raise

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


# For backward compatibility, make EnhancedMCPServer the default MCPServer
MCPServer = EnhancedMCPServer


class SimpleMCPServer(EnhancedMCPServer):
    """
    Simplified MCP server with minimal configuration.

    This inherits all enhanced capabilities but disables some features
    by default for simpler use cases.
    """

    def __init__(self, name: str, description: str = ""):
        """
        Initialize simple MCP server.

        Args:
            name: Server name
            description: Server description
        """
        # Initialize with some features disabled for simplicity
        super().__init__(
            name=name,
            enable_cache=False,  # Disable cache by default
            enable_metrics=False,  # Disable metrics by default
            enable_formatting=True,  # Keep formatting for better output
        )

        self.description = description

        # Update config for simple use
        self.config.update(
            {"server": {"name": name, "description": description, "version": "1.0.0"}}
        )

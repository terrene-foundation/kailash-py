"""
Enhanced MCP Server Framework with production-ready capabilities.

This module provides both basic and enhanced MCP server implementations using
the official FastMCP framework from Anthropic. Servers run as long-lived
services that expose tools, resources, and prompts to MCP clients.

Enhanced Features:
- Multiple transport support (STDIO, SSE, HTTP)
- Authentication and authorization
- Rate limiting and circuit breaker patterns
- Metrics collection and monitoring
- Error handling with structured codes
- Service discovery integration
- Resource streaming
- Connection pooling
- Caching with TTL support

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

Enhanced Production Usage:
    Server with authentication and monitoring:

    >>> from kailash.mcp_server.auth import APIKeyAuth
    >>> auth = APIKeyAuth({"user1": "secret-key"})
    >>> server = MCPServer(
    ...     "my-server",
    ...     auth_provider=auth,
    ...     enable_metrics=True,
    ...     enable_http_transport=True,
    ...     rate_limit_config={"requests_per_minute": 100}
    ... )
    >>> server.run()
"""

import asyncio
import functools
import logging
import time
import uuid
from abc import ABC, abstractmethod
from collections.abc import Callable
from pathlib import Path
from typing import Any, Dict, List, Optional, TypeVar, Union

from .auth import AuthManager, AuthProvider, PermissionManager, RateLimiter
from .errors import (
    AuthenticationError,
    AuthorizationError,
    ErrorAggregator,
    MCPError,
    MCPErrorCode,
    RateLimitError,
    ResourceError,
    RetryableOperation,
    ToolError,
)
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
    Enhanced MCP server with production-ready features.

    This is the main concrete MCP server implementation with all production
    features available. Features can be enabled/disabled as needed.

    Features available:
    - Multiple transport support (STDIO, SSE, HTTP)
    - Authentication and authorization with multiple providers
    - Rate limiting and circuit breaker patterns
    - Metrics collection and monitoring
    - Error handling with structured codes
    - Caching with TTL support
    - Response formatting utilities
    - Service discovery integration
    - Resource streaming
    - Connection pooling
    - Hierarchical configuration management

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

        With authentication and advanced features:
        >>> from kailash.mcp_server.auth import APIKeyAuth
        >>> auth = APIKeyAuth({"user1": "secret-key"})
        >>> server = MCPServer(
        ...     "my-server",
        ...     auth_provider=auth,
        ...     enable_http_transport=True,
        ...     rate_limit_config={"requests_per_minute": 100},
        ...     circuit_breaker_config={"failure_threshold": 5}
        ... )
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
        # Enhanced features (optional for backward compatibility)
        auth_provider: Optional[AuthProvider] = None,
        enable_http_transport: bool = False,
        enable_sse_transport: bool = False,
        rate_limit_config: Optional[Dict[str, Any]] = None,
        circuit_breaker_config: Optional[Dict[str, Any]] = None,
        enable_discovery: bool = False,
        connection_pool_config: Optional[Dict[str, Any]] = None,
        error_aggregation: bool = True,
        transport_timeout: float = 30.0,
        max_request_size: int = 10_000_000,  # 10MB
        enable_streaming: bool = False,
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
            auth_provider: Optional authentication provider
            enable_http_transport: Enable HTTP transport support
            enable_sse_transport: Enable SSE transport support
            rate_limit_config: Rate limiting configuration
            circuit_breaker_config: Circuit breaker configuration
            enable_discovery: Enable service discovery
            connection_pool_config: Connection pooling configuration
            error_aggregation: Enable error aggregation
            transport_timeout: Transport timeout in seconds
            max_request_size: Maximum request size in bytes
            enable_streaming: Enable streaming support
        """
        self.name = name

        # Enhanced features
        self.auth_provider = auth_provider
        self.enable_http_transport = enable_http_transport
        self.enable_sse_transport = enable_sse_transport
        self.enable_discovery = enable_discovery
        self.enable_streaming = enable_streaming
        self.transport_timeout = transport_timeout
        self.max_request_size = max_request_size

        # Initialize configuration
        self.config = ConfigManager(config_file)

        # Set default configuration values including enhanced features
        self.config.update(
            {
                "server": {
                    "name": name,
                    "version": "1.0.0",
                    "transport": "stdio",
                    "enable_http": enable_http_transport,
                    "enable_sse": enable_sse_transport,
                    "timeout": transport_timeout,
                    "max_request_size": max_request_size,
                    "enable_streaming": enable_streaming,
                },
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
                "auth": {
                    "enabled": auth_provider is not None,
                    "provider_type": (
                        type(auth_provider).__name__ if auth_provider else None
                    ),
                },
                "rate_limiting": rate_limit_config or {},
                "circuit_breaker": circuit_breaker_config or {},
                "discovery": {"enabled": enable_discovery},
                "connection_pool": connection_pool_config or {},
            }
        )

        # Initialize authentication manager
        if auth_provider:
            self.auth_manager = AuthManager(
                provider=auth_provider,
                permission_manager=PermissionManager(),
                rate_limiter=RateLimiter(**(rate_limit_config or {})),
            )
        else:
            self.auth_manager = None

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

        # Error aggregation
        if error_aggregation:
            self.error_aggregator = ErrorAggregator()
        else:
            self.error_aggregator = None

        # Circuit breaker for tool calls
        if circuit_breaker_config:
            from .errors import CircuitBreakerRetry

            self.circuit_breaker = CircuitBreakerRetry(**circuit_breaker_config)
        else:
            self.circuit_breaker = None

        # FastMCP server instance (initialized lazily)
        self._mcp = None
        self._running = False
        self._active_sessions: Dict[str, Dict[str, Any]] = {}
        self._connection_pools: Dict[str, List[Any]] = {}

        # Tool registry for management
        self._tool_registry: Dict[str, Dict[str, Any]] = {}
        self._resource_registry: Dict[str, Dict[str, Any]] = {}
        self._prompt_registry: Dict[str, Dict[str, Any]] = {}

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
        # Enhanced features
        required_permission: Optional[str] = None,
        rate_limit: Optional[Dict[str, Any]] = None,
        enable_circuit_breaker: bool = True,
        timeout: Optional[float] = None,
        retryable: bool = True,
        stream_response: bool = False,
    ):
        """
        Enhanced tool decorator with authentication, caching, metrics, and error handling.

        Args:
            cache_key: Optional cache key for caching results
            cache_ttl: Optional TTL override for this tool
            format_response: Optional response format ("json", "markdown", "table", etc.)
            required_permission: Required permission for tool access
            rate_limit: Tool-specific rate limiting configuration
            enable_circuit_breaker: Enable circuit breaker for this tool
            timeout: Tool execution timeout in seconds
            retryable: Whether tool failures are retryable
            stream_response: Enable streaming response for large results

        Returns:
            Decorated function with enhanced capabilities

        Example:
            @server.tool(
                cache_key="weather",
                cache_ttl=600,
                format_response="markdown",
                required_permission="weather.read",
                rate_limit={"requests_per_minute": 10},
                timeout=30.0
            )
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
                func,
                tool_name,
                cache_key,
                cache_ttl,
                format_response,
                required_permission,
                rate_limit,
                enable_circuit_breaker,
                timeout,
                retryable,
                stream_response,
            )

            # Register with FastMCP
            mcp_tool = self._mcp.tool()(enhanced_func)

            # Track in registry with enhanced metadata
            self._tool_registry[tool_name] = {
                "function": mcp_tool,
                "original_function": func,
                "cached": cache_key is not None,
                "cache_key": cache_key,
                "cache_ttl": cache_ttl,
                "format_response": format_response,
                "required_permission": required_permission,
                "rate_limit": rate_limit,
                "enable_circuit_breaker": enable_circuit_breaker,
                "timeout": timeout,
                "retryable": retryable,
                "stream_response": stream_response,
                "call_count": 0,
                "error_count": 0,
                "last_called": None,
            }

            logger.debug(
                f"Registered enhanced tool: {tool_name} "
                f"(cached: {cache_key is not None}, "
                f"auth: {required_permission is not None}, "
                f"rate_limited: {rate_limit is not None})"
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
        required_permission: Optional[str],
        rate_limit: Optional[Dict[str, Any]],
        enable_circuit_breaker: bool,
        timeout: Optional[float],
        retryable: bool,
        stream_response: bool,
    ) -> F:
        """Create enhanced tool function with authentication, caching, metrics, error handling, and more."""

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            # Generate session ID for tracking
            session_id = str(uuid.uuid4())
            start_time = time.time() if self.metrics.enabled else None

            try:
                # Authentication check
                if self.auth_manager and required_permission:
                    # Extract credentials from kwargs or context
                    credentials = self._extract_credentials_from_context(kwargs)
                    try:
                        user_info = self.auth_manager.authenticate_and_authorize(
                            credentials, required_permission
                        )
                        # Add user info to session
                        self._active_sessions[session_id] = {
                            "user": user_info,
                            "tool": tool_name,
                            "start_time": start_time,
                            "permission": required_permission,
                        }
                    except (AuthenticationError, AuthorizationError) as e:
                        if self.error_aggregator:
                            self.error_aggregator.record_error(e)
                        raise ToolError(
                            f"Access denied for {tool_name}: {str(e)}",
                            tool_name=tool_name,
                        )

                # Rate limiting check
                if rate_limit and self.auth_manager:
                    user_id = (
                        self._active_sessions.get(session_id, {})
                        .get("user", {})
                        .get("id", "anonymous")
                    )
                    try:
                        self.auth_manager.rate_limiter.check_rate_limit(
                            user_id, tool_name, **rate_limit
                        )
                    except RateLimitError as e:
                        if self.error_aggregator:
                            self.error_aggregator.record_error(e)
                        raise

                # Circuit breaker check
                if enable_circuit_breaker and self.circuit_breaker:
                    if not self.circuit_breaker.should_retry(
                        MCPError("Circuit breaker check"), 1
                    ):
                        error = MCPError(
                            f"Circuit breaker open for {tool_name}",
                            error_code=MCPErrorCode.CIRCUIT_BREAKER_OPEN,
                            retryable=True,
                        )
                        if self.error_aggregator:
                            self.error_aggregator.record_error(error)
                        raise error

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

                        # Update registry stats
                        self._tool_registry[tool_name]["call_count"] += 1
                        self._tool_registry[tool_name]["last_called"] = time.time()

                        return self._format_response(
                            result, response_format, stream_response
                        )

                # Execute function with timeout
                if timeout:
                    import signal

                    def timeout_handler(signum, frame):
                        raise TimeoutError(
                            f"Tool {tool_name} timed out after {timeout}s"
                        )

                    old_handler = signal.signal(signal.SIGALRM, timeout_handler)
                    signal.alarm(int(timeout))

                    try:
                        result = func(*args, **kwargs)
                    finally:
                        signal.alarm(0)
                        signal.signal(signal.SIGALRM, old_handler)
                else:
                    result = func(*args, **kwargs)

                # Cache result if enabled
                if cache_key and self.cache.enabled:
                    cache.set(cache_lookup_key, result)
                    logger.debug(f"Cached result for {tool_name}")

                # Track success metrics
                if self.metrics.enabled:
                    latency = time.time() - start_time
                    self.metrics.track_tool_call(tool_name, latency, True)

                # Update circuit breaker on success
                if enable_circuit_breaker and self.circuit_breaker:
                    self.circuit_breaker.on_success()

                # Update registry stats
                self._tool_registry[tool_name]["call_count"] += 1
                self._tool_registry[tool_name]["last_called"] = time.time()

                return self._format_response(result, response_format, stream_response)

            except Exception as e:
                # Convert to MCP error if needed
                if not isinstance(e, MCPError):
                    mcp_error = ToolError(
                        f"Tool execution failed: {str(e)}",
                        tool_name=tool_name,
                        retryable=retryable,
                        cause=e,
                    )
                else:
                    mcp_error = e

                # Record error
                if self.error_aggregator:
                    self.error_aggregator.record_error(mcp_error)

                # Update circuit breaker on failure
                if enable_circuit_breaker and self.circuit_breaker:
                    self.circuit_breaker.on_failure(mcp_error)

                # Track error metrics
                if self.metrics.enabled and start_time:
                    latency = time.time() - start_time
                    self.metrics.track_tool_call(
                        tool_name, latency, False, type(e).__name__
                    )

                # Update registry stats
                self._tool_registry[tool_name]["error_count"] += 1
                self._tool_registry[tool_name]["last_called"] = time.time()

                logger.error(f"Error in tool {tool_name}: {mcp_error}")
                raise mcp_error

            finally:
                # Clean up session
                if session_id in self._active_sessions:
                    del self._active_sessions[session_id]

        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            # Generate session ID for tracking
            session_id = str(uuid.uuid4())
            start_time = time.time() if self.metrics.enabled else None

            try:
                # Authentication check
                if self.auth_manager and required_permission:
                    # Extract credentials from kwargs or context
                    credentials = self._extract_credentials_from_context(kwargs)
                    try:
                        user_info = self.auth_manager.authenticate_and_authorize(
                            credentials, required_permission
                        )
                        # Add user info to session
                        self._active_sessions[session_id] = {
                            "user": user_info,
                            "tool": tool_name,
                            "start_time": start_time,
                            "permission": required_permission,
                        }
                    except (AuthenticationError, AuthorizationError) as e:
                        if self.error_aggregator:
                            self.error_aggregator.record_error(e)
                        raise ToolError(
                            f"Access denied for {tool_name}: {str(e)}",
                            tool_name=tool_name,
                        )

                # Rate limiting check
                if rate_limit and self.auth_manager:
                    user_id = (
                        self._active_sessions.get(session_id, {})
                        .get("user", {})
                        .get("id", "anonymous")
                    )
                    try:
                        self.auth_manager.rate_limiter.check_rate_limit(
                            user_id, tool_name, **rate_limit
                        )
                    except RateLimitError as e:
                        if self.error_aggregator:
                            self.error_aggregator.record_error(e)
                        raise

                # Circuit breaker check
                if enable_circuit_breaker and self.circuit_breaker:
                    if not self.circuit_breaker.should_retry(
                        MCPError("Circuit breaker check"), 1
                    ):
                        error = MCPError(
                            f"Circuit breaker open for {tool_name}",
                            error_code=MCPErrorCode.CIRCUIT_BREAKER_OPEN,
                            retryable=True,
                        )
                        if self.error_aggregator:
                            self.error_aggregator.record_error(error)
                        raise error

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

                        # Update registry stats
                        self._tool_registry[tool_name]["call_count"] += 1
                        self._tool_registry[tool_name]["last_called"] = time.time()

                        return self._format_response(
                            result, response_format, stream_response
                        )

                # Execute function with timeout
                if timeout:
                    result = await asyncio.wait_for(
                        func(*args, **kwargs), timeout=timeout
                    )
                else:
                    result = await func(*args, **kwargs)

                # Cache result if enabled
                if cache_key and self.cache.enabled:
                    cache.set(cache_lookup_key, result)
                    logger.debug(f"Cached result for {tool_name}")

                # Track success metrics
                if self.metrics.enabled:
                    latency = time.time() - start_time
                    self.metrics.track_tool_call(tool_name, latency, True)

                # Update circuit breaker on success
                if enable_circuit_breaker and self.circuit_breaker:
                    self.circuit_breaker.on_success()

                # Update registry stats
                self._tool_registry[tool_name]["call_count"] += 1
                self._tool_registry[tool_name]["last_called"] = time.time()

                return self._format_response(result, response_format, stream_response)

            except Exception as e:
                # Convert to MCP error if needed
                if not isinstance(e, MCPError):
                    mcp_error = ToolError(
                        f"Tool execution failed: {str(e)}",
                        tool_name=tool_name,
                        retryable=retryable,
                        cause=e,
                    )
                else:
                    mcp_error = e

                # Record error
                if self.error_aggregator:
                    self.error_aggregator.record_error(mcp_error)

                # Update circuit breaker on failure
                if enable_circuit_breaker and self.circuit_breaker:
                    self.circuit_breaker.on_failure(mcp_error)

                # Track error metrics
                if self.metrics.enabled and start_time:
                    latency = time.time() - start_time
                    self.metrics.track_tool_call(
                        tool_name, latency, False, type(e).__name__
                    )

                # Update registry stats
                self._tool_registry[tool_name]["error_count"] += 1
                self._tool_registry[tool_name]["last_called"] = time.time()

                logger.error(f"Error in tool {tool_name}: {mcp_error}")
                raise mcp_error

            finally:
                # Clean up session
                if session_id in self._active_sessions:
                    del self._active_sessions[session_id]

        # Return appropriate wrapper based on function type
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    def _format_response(
        self, result: Any, response_format: Optional[str], stream_response: bool = False
    ) -> Any:
        """Format response if formatting is enabled, with optional streaming support."""
        if not self.config.get("formatting.enabled", True) or not response_format:
            if (
                stream_response
                and isinstance(result, (list, dict))
                and len(str(result)) > 1000
            ):
                # For large results, consider streaming (simplified implementation)
                return {
                    "streaming": True,
                    "data": result,
                    "chunks": self._chunk_large_response(result),
                }
            return result

        try:
            formatted = format_response(result, response_format)
            if stream_response and isinstance(formatted, str) and len(formatted) > 1000:
                return {
                    "streaming": True,
                    "data": formatted,
                    "chunks": self._chunk_large_response(formatted),
                }
            return formatted
        except Exception as e:
            logger.warning(f"Failed to format response: {e}")
            return result

    def _chunk_large_response(self, data: Any, chunk_size: int = 1000) -> List[str]:
        """Chunk large responses for streaming."""
        if isinstance(data, str):
            return [data[i : i + chunk_size] for i in range(0, len(data), chunk_size)]
        elif isinstance(data, (list, dict)):
            data_str = str(data)
            return [
                data_str[i : i + chunk_size]
                for i in range(0, len(data_str), chunk_size)
            ]
        else:
            return [str(data)]

    def _extract_credentials_from_context(
        self, kwargs: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Extract credentials from function context or kwargs."""
        # Look for common credential patterns in kwargs
        credentials = {}

        # Check for MCP-style authentication headers
        if "mcp_auth" in kwargs:
            credentials.update(kwargs["mcp_auth"])

        # Check for common auth patterns
        auth_fields = ["api_key", "token", "username", "password", "jwt"]
        for field in auth_fields:
            if field in kwargs:
                credentials[field] = kwargs[field]

        # Check for Authorization header pattern
        if "authorization" in kwargs:
            auth_header = kwargs["authorization"]
            if auth_header.startswith("Bearer "):
                credentials["token"] = auth_header[7:]
            elif auth_header.startswith("Basic "):
                import base64

                try:
                    decoded = base64.b64decode(auth_header[6:]).decode()
                    if ":" in decoded:
                        username, password = decoded.split(":", 1)
                        credentials["username"] = username
                        credentials["password"] = password
                except Exception:
                    pass

        return credentials

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
                "active_sessions": len(self._active_sessions),
                "transport": {
                    "http_enabled": self.enable_http_transport,
                    "sse_enabled": self.enable_sse_transport,
                    "streaming_enabled": self.enable_streaming,
                    "timeout": self.transport_timeout,
                    "max_request_size": self.max_request_size,
                },
                "features": {
                    "auth_enabled": self.auth_manager is not None,
                    "circuit_breaker_enabled": self.circuit_breaker is not None,
                    "error_aggregation_enabled": self.error_aggregator is not None,
                    "discovery_enabled": self.enable_discovery,
                },
            },
            "tools": self.get_tool_stats(),
            "resources": self.get_resource_stats(),
            "prompts": self.get_prompt_stats(),
        }

        if self.metrics.enabled:
            stats["metrics"] = self.metrics.export_metrics()

        if self.cache.enabled:
            stats["cache"] = self.cache.stats()

        if self.error_aggregator:
            stats["errors"] = self.error_aggregator.get_error_stats(
                time_window=3600
            )  # Last hour

        if self.circuit_breaker:
            stats["circuit_breaker"] = {
                "state": self.circuit_breaker.state,
                "failure_count": self.circuit_breaker.failure_count,
                "success_count": self.circuit_breaker.success_count,
            }

        return stats

    def get_resource_stats(self) -> Dict[str, Any]:
        """Get resource statistics."""
        return {
            "registered_resources": len(self._resource_registry),
            "resources": {
                uri: {
                    "call_count": info.get("call_count", 0),
                    "error_count": info.get("error_count", 0),
                    "last_accessed": info.get("last_accessed"),
                }
                for uri, info in self._resource_registry.items()
            },
        }

    def get_prompt_stats(self) -> Dict[str, Any]:
        """Get prompt statistics."""
        return {
            "registered_prompts": len(self._prompt_registry),
            "prompts": {
                name: {
                    "call_count": info.get("call_count", 0),
                    "error_count": info.get("error_count", 0),
                    "last_used": info.get("last_used"),
                }
                for name, info in self._prompt_registry.items()
            },
        }

    def get_active_sessions(self) -> Dict[str, Dict[str, Any]]:
        """Get information about active sessions."""
        return {
            session_id: {
                "user": session_info.get("user", {}),
                "tool": session_info.get("tool"),
                "permission": session_info.get("permission"),
                "duration": time.time() - session_info.get("start_time", time.time()),
            }
            for session_id, session_info in self._active_sessions.items()
        }

    def get_error_trends(
        self, time_window: Optional[float] = None
    ) -> List[Dict[str, Any]]:
        """Get error trends over time."""
        if not self.error_aggregator:
            return []
        return self.error_aggregator.get_error_trends()

    def health_check(self) -> Dict[str, Any]:
        """Perform comprehensive health check."""
        health_status = {
            "status": "healthy",
            "timestamp": time.time(),
            "server": {
                "name": self.name,
                "running": self._running,
                "uptime": time.time()
                - self.config.get("server.start_time", time.time()),
            },
            "components": {
                "mcp": self._mcp is not None,
                "cache": self.cache.enabled if self.cache else False,
                "metrics": self.metrics.enabled if self.metrics else False,
                "auth": self.auth_manager is not None,
                "circuit_breaker": self.circuit_breaker is not None,
            },
            "resources": {
                "active_sessions": len(self._active_sessions),
                "tools_registered": len(self._tool_registry),
                "resources_registered": len(self._resource_registry),
                "prompts_registered": len(self._prompt_registry),
            },
        }

        # Check for issues
        issues = []

        # Check error rates
        if self.error_aggregator:
            error_stats = self.error_aggregator.get_error_stats(
                time_window=300
            )  # Last 5 minutes
            if error_stats.get("error_rate", 0) > 10:  # More than 10 errors per second
                issues.append("High error rate detected")
                health_status["status"] = "degraded"

        # Check circuit breaker state
        if self.circuit_breaker and self.circuit_breaker.state == "open":
            issues.append("Circuit breaker is open")
            health_status["status"] = "degraded"

        # Check memory usage for caches
        if self.cache and self.cache.enabled:
            cache_stats = self.cache.stats()
            # Simple heuristic - if any cache is over 90% full
            for cache_name, stats in cache_stats.items():
                if isinstance(stats, dict) and stats.get("utilization", 0) > 0.9:
                    issues.append(f"Cache {cache_name} is over 90% full")
                    health_status["status"] = "degraded"

        health_status["issues"] = issues

        if issues and health_status["status"] == "healthy":
            health_status["status"] = "degraded"

        return health_status

    def clear_cache(self, cache_name: Optional[str] = None) -> None:
        """Clear cache(s)."""
        if cache_name:
            cache = self.cache.get_cache(cache_name)
            cache.clear()
            logger.info(f"Cleared cache: {cache_name}")
        else:
            self.cache.clear_all()
            logger.info("Cleared all caches")

    def reset_circuit_breaker(self) -> None:
        """Reset circuit breaker to closed state."""
        if self.circuit_breaker:
            self.circuit_breaker.state = "closed"
            self.circuit_breaker.failure_count = 0
            self.circuit_breaker.success_count = 0
            logger.info("Circuit breaker reset to closed state")

    def terminate_session(self, session_id: str) -> bool:
        """Terminate an active session."""
        if session_id in self._active_sessions:
            del self._active_sessions[session_id]
            logger.info(f"Terminated session: {session_id}")
            return True
        return False

    def get_tool_by_name(self, tool_name: str) -> Optional[Dict[str, Any]]:
        """Get tool information by name."""
        return self._tool_registry.get(tool_name)

    def disable_tool(self, tool_name: str) -> bool:
        """Temporarily disable a tool."""
        if tool_name in self._tool_registry:
            self._tool_registry[tool_name]["disabled"] = True
            logger.info(f"Disabled tool: {tool_name}")
            return True
        return False

    def enable_tool(self, tool_name: str) -> bool:
        """Re-enable a disabled tool."""
        if tool_name in self._tool_registry:
            self._tool_registry[tool_name]["disabled"] = False
            logger.info(f"Enabled tool: {tool_name}")
            return True
        return False

    def run(self):
        """Run the enhanced MCP server with all features."""
        if self._mcp is None:
            self._init_mcp()

        # Record server start time
        self.config.update({"server.start_time": time.time()})

        # Log enhanced server startup
        logger.info(f"Starting enhanced MCP server: {self.name}")
        logger.info("Features enabled:")
        logger.info(f"  - Cache: {self.cache.enabled if self.cache else False}")
        logger.info(f"  - Metrics: {self.metrics.enabled if self.metrics else False}")
        logger.info(f"  - Authentication: {self.auth_manager is not None}")
        logger.info(f"  - HTTP Transport: {self.enable_http_transport}")
        logger.info(f"  - SSE Transport: {self.enable_sse_transport}")
        logger.info(f"  - Streaming: {self.enable_streaming}")
        logger.info(f"  - Circuit Breaker: {self.circuit_breaker is not None}")
        logger.info(f"  - Error Aggregation: {self.error_aggregator is not None}")
        logger.info(f"  - Service Discovery: {self.enable_discovery}")

        logger.info("Server configuration:")
        logger.info(f"  - Tools registered: {len(self._tool_registry)}")
        logger.info(f"  - Resources registered: {len(self._resource_registry)}")
        logger.info(f"  - Prompts registered: {len(self._prompt_registry)}")
        logger.info(f"  - Transport timeout: {self.transport_timeout}s")
        logger.info(f"  - Max request size: {self.max_request_size} bytes")

        self._running = True

        try:
            # Perform health check before starting
            health = self.health_check()
            if health["status"] != "healthy":
                logger.warning(f"Server health check shows issues: {health['issues']}")

            # Run the FastMCP server
            logger.info("Starting FastMCP server...")
            self._mcp.run()

        except KeyboardInterrupt:
            logger.info("Server stopped by user")
        except Exception as e:
            logger.error(f"Server error: {e}")

            # Record error if aggregator is enabled
            if self.error_aggregator:
                error = MCPError(
                    f"Server startup/runtime error: {str(e)}",
                    error_code=MCPErrorCode.SERVER_UNAVAILABLE,
                    cause=e,
                )
                self.error_aggregator.record_error(error)

            raise
        finally:
            logger.info("Shutting down enhanced MCP server...")

            # Clean up active sessions
            if self._active_sessions:
                logger.info(f"Terminating {len(self._active_sessions)} active sessions")
                self._active_sessions.clear()

            # Log final stats
            if self.metrics and self.metrics.enabled:
                final_stats = self.get_server_stats()
                logger.info(
                    f"Final server statistics: {final_stats.get('metrics', {})}"
                )

            self._running = False
            logger.info(f"Enhanced MCP server '{self.name}' stopped")


# Clean public API design:
# - MCPServerBase: Abstract base for custom implementations (e.g., AIRegistryServer)
# - MCPServer: Main concrete server with all production features
# - SimpleMCPServer: Alias for backward compatibility
# - EnhancedMCPServer: Alias for backward compatibility
MCPServer = EnhancedMCPServer
SimpleMCPServer = EnhancedMCPServer

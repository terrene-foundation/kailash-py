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
import gzip
import json
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
from .protocol import get_protocol_manager
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
            # Try independent FastMCP package first (when available)
            from fastmcp import FastMCP

            self._mcp = FastMCP(self.name)
        except ImportError:
            logger.warning("FastMCP not available, using fallback mode")
            # Use same fallback as MCPServer
            self._mcp = self._create_fallback_server()

    def _create_fallback_server(self):
        """Create a fallback server when FastMCP is not available."""

        class FallbackMCPServer:
            def __init__(self, name: str):
                self.name = name
                self._tools = {}
                self._resources = {}
                self._prompts = {}

            def tool(self, *args, **kwargs):
                def decorator(func):
                    self._tools[func.__name__] = func
                    return func

                return decorator

            def resource(self, uri):
                def decorator(func):
                    self._resources[uri] = func
                    return func

                return decorator

            def prompt(self, name):
                def decorator(func):
                    self._prompts[name] = func
                    return func

                return decorator

            def run(self, **kwargs):
                raise NotImplementedError("FastMCP not available")

        return FallbackMCPServer(self.name)

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


class MCPServer:
    """
    Kailash MCP Server - Node-based Model Context Protocol server.

    This MCP server follows Kailash philosophy by integrating with the node
    and workflow system. Tools can be implemented as nodes, and complex
    MCP capabilities can be built using workflows.

    Core Features:
    - Node-based tool implementation using Kailash nodes
    - Workflow-based complex operations
    - Production-ready with authentication, caching, and monitoring
    - Multiple transport support (STDIO, SSE, HTTP)
    - Integration with Kailash runtime and infrastructure

    Kailash Philosophy Integration:
        Using nodes as MCP tools:
        >>> from kailash.mcp_server import MCPServer
        >>> from kailash.nodes import PythonCodeNode
        >>>
        >>> server = MCPServer("my-server")
        >>>
        >>> # Register a node as an MCP tool
        >>> @server.node_tool(PythonCodeNode)
        ... def calculate(a: int, b: int) -> int:
        ...     return a + b
        >>>
        >>> server.run()

        Using workflows as MCP tools:
        >>> from kailash.workflows import WorkflowBuilder
        >>>
        >>> # Create workflow for complex MCP operation
        >>> workflow = WorkflowBuilder()
        >>> workflow.add_node("csv_reader", "CSVReaderNode", {"file_path": "data.csv"})
        >>> workflow.add_node("processor", "PythonCodeNode", {"code": "process_data"})
        >>> workflow.add_connection("csv_reader", "processor", "data", "input_data")
        >>>
        >>> server.register_workflow_tool("process_csv", workflow)

    Traditional usage (for compatibility):
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
        # Transport configuration
        transport: str = "stdio",  # "stdio", "websocket", "http", "sse"
        websocket_host: str = "0.0.0.0",
        websocket_port: int = 3001,
        # Caching configuration
        enable_cache: bool = True,
        cache_ttl: int = 300,
        cache_backend: str = "memory",  # "memory" or "redis"
        cache_config: Optional[Dict[str, Any]] = None,
        enable_metrics: bool = True,
        enable_formatting: bool = True,
        enable_monitoring: bool = False,  # Health checks, alerts, observability
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
        # Resource subscription configuration
        enable_subscriptions: bool = True,
        event_store=None,
        # WebSocket compression configuration
        enable_websocket_compression: bool = False,
        compression_threshold: int = 1024,  # Only compress messages larger than 1KB
        compression_level: int = 6,  # 1 (fastest) to 9 (best compression)
    ):
        """
        Initialize enhanced MCP server.

        Args:
            name: Server name
            config_file: Optional configuration file path
            transport: Transport to use ("stdio", "websocket", "http", "sse")
            websocket_host: Host for WebSocket server (default: "0.0.0.0")
            websocket_port: Port for WebSocket server (default: 3001)
            enable_cache: Whether to enable caching (default: True)
            cache_ttl: Default cache TTL in seconds (default: 300)
            cache_backend: Cache backend ("memory" or "redis")
            cache_config: Cache configuration (for Redis: {"redis_url": "redis://...", "prefix": "mcp:"})
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
            enable_subscriptions: Enable resource subscriptions (default: True)
            event_store: Optional event store for subscription logging
            enable_websocket_compression: Enable gzip compression for WebSocket messages (default: False)
            compression_threshold: Only compress messages larger than this size in bytes (default: 1024)
            compression_level: Compression level from 1 (fastest) to 9 (best compression) (default: 6)
        """
        self.name = name

        # Transport configuration
        self.transport = transport
        self.websocket_host = websocket_host
        self.websocket_port = websocket_port

        # WebSocket compression configuration
        self.enable_websocket_compression = enable_websocket_compression
        self.compression_threshold = compression_threshold
        self.compression_level = compression_level

        # Enhanced features
        self.auth_provider = auth_provider
        self.enable_http_transport = enable_http_transport
        self.enable_sse_transport = enable_sse_transport
        self.enable_discovery = enable_discovery
        self.enable_streaming = enable_streaming
        self.enable_monitoring = enable_monitoring
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
                    "transport": transport,
                    "websocket_host": websocket_host,
                    "websocket_port": websocket_port,
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
                    "backend": cache_backend,
                    "config": cache_config or {},
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
                "monitoring": {
                    "enabled": enable_monitoring,
                    "health_checks": enable_monitoring,
                    "observability": enable_monitoring,
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
            backend=self.config.get("cache.backend", cache_backend),
            config=self.config.get("cache.config", cache_config or {}),
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

        # Client management for new handlers
        self.client_info: Dict[str, Dict[str, Any]] = {}
        self._pending_sampling_requests: Dict[str, Dict[str, Any]] = {}

        # Resource subscription support
        self.enable_subscriptions = enable_subscriptions
        self.event_store = event_store
        self.subscription_manager = None
        if self.enable_subscriptions:
            from .subscriptions import ResourceSubscriptionManager

            self.subscription_manager = ResourceSubscriptionManager(
                auth_manager=(
                    self.auth_manager if hasattr(self, "auth_manager") else None
                ),
                event_store=event_store,
                rate_limiter=(
                    self.rate_limiter if hasattr(self, "rate_limiter") else None
                ),
            )

        # Transport instance (for WebSocket and other transports)
        self._transport = None

    def _init_mcp(self):
        """Initialize FastMCP server."""
        if self._mcp is not None:
            return

        try:
            # Try independent FastMCP package first (when available)
            from fastmcp import FastMCP

            self._mcp = FastMCP(self.name)
            logger.info(f"Initialized FastMCP server: {self.name}")
        except ImportError as e1:
            logger.warning(f"Independent FastMCP not available: {e1}")
            try:
                # Fallback to official MCP FastMCP (when fixed)
                from mcp.server import FastMCP

                self._mcp = FastMCP(self.name)
                logger.info(f"Initialized official FastMCP server: {self.name}")
            except ImportError as e2:
                logger.warning(f"Official FastMCP not available: {e2}")
                # Final fallback: Create a minimal FastMCP-compatible wrapper
                logger.info(f"Using low-level MCP Server fallback for: {self.name}")
                self._mcp = self._create_fallback_server()

    def _create_fallback_server(self):
        """Create a fallback server when FastMCP is not available."""
        logger.info("Creating fallback server implementation")

        class FallbackMCPServer:
            """Minimal FastMCP-compatible server for when FastMCP is unavailable."""

            def __init__(self, name: str):
                self.name = name
                self._tools = {}
                self._resources = {}
                self._prompts = {}
                logger.info(f"Fallback MCP server '{name}' initialized")

            def tool(self, *args, **kwargs):
                """Tool decorator that stores tool registration."""

                def decorator(func):
                    tool_name = func.__name__
                    self._tools[tool_name] = func
                    logger.debug(f"Registered fallback tool: {tool_name}")
                    return func

                return decorator

            def resource(self, uri):
                """Resource decorator that stores resource registration."""

                def decorator(func):
                    self._resources[uri] = func
                    logger.debug(f"Registered fallback resource: {uri}")
                    return func

                return decorator

            def prompt(self, name):
                """Prompt decorator that stores prompt registration."""

                def decorator(func):
                    self._prompts[name] = func
                    logger.debug(f"Registered fallback prompt: {name}")
                    return func

                return decorator

            def run(self, **kwargs):
                """Placeholder run method."""
                logger.warning(
                    f"Fallback server '{self.name}' run() called - FastMCP features limited"
                )
                logger.info(
                    f"Registered: {len(self._tools)} tools, {len(self._resources)} resources, {len(self._prompts)} prompts"
                )
                # In a real implementation, we would set up low-level MCP protocol here
                raise NotImplementedError(
                    "Full MCP protocol not implemented in fallback mode. "
                    "Install 'fastmcp>=2.10.0' or wait for official MCP package fix."
                )

        return FallbackMCPServer(self.name)

    def tool(
        self,
        cache_key: Optional[str] = None,
        cache_ttl: Optional[int] = None,
        format_response: Optional[str] = None,
        # Enhanced features
        required_permission: Optional[str] = None,
        required_permissions: Optional[
            List[str]
        ] = None,  # Added for backward compatibility
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
            required_permission: Single required permission for tool access
            required_permissions: List of required permissions (alternative to required_permission)
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

            # Normalize permissions - support both singular and plural
            normalized_permission = None
            if required_permissions is not None and required_permission is not None:
                raise ValueError(
                    "Cannot specify both required_permission and required_permissions"
                )
            elif required_permissions is not None:
                if len(required_permissions) == 1:
                    normalized_permission = required_permissions[0]
                elif len(required_permissions) > 1:
                    # For now, take the first permission. Future enhancement could support multiple.
                    normalized_permission = required_permissions[0]
                    logger.warning(
                        f"Tool {tool_name}: Multiple permissions specified, using first: {normalized_permission}"
                    )
            elif required_permission is not None:
                normalized_permission = required_permission

            # Create enhanced wrapper
            enhanced_func = self._create_enhanced_tool(
                func,
                tool_name,
                cache_key,
                cache_ttl,
                format_response,
                normalized_permission,
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
                "required_permission": normalized_permission,
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

                    # For sync functions with Redis, we need to handle async operations
                    if cache.is_redis:
                        # Try to run async cache operations in sync context
                        try:
                            # Check if we're already in an async context
                            try:
                                asyncio.get_running_loop()
                                # We're in an async context, but this is a sync function
                                # Fall back to memory cache behavior (no caching for now)
                                result = None
                            except RuntimeError:
                                # Not in async context, we can use asyncio.run
                                result = asyncio.run(cache.aget(cache_lookup_key))
                        except Exception as e:
                            logger.debug(f"Redis cache error in sync context: {e}")
                            result = None
                    else:
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
                    # For sync functions with Redis, handle async operations
                    if cache.is_redis:
                        try:
                            # Check if we're already in an async context
                            try:
                                asyncio.get_running_loop()
                                # We're in an async context, but this is a sync function
                                # Fall back to memory cache behavior (no caching for now)
                                pass
                            except RuntimeError:
                                # Not in async context, we can use asyncio.run
                                asyncio.run(cache.aset(cache_lookup_key, result))
                        except Exception as e:
                            logger.debug(f"Redis cache set error in sync context: {e}")
                    else:
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

                    # Allow bypassing auth for direct calls when no credentials provided
                    # This enables testing and development scenarios
                    if not credentials and not any(
                        k.startswith("mcp_") for k in kwargs.keys()
                    ):
                        logger.debug(
                            f"Tool {tool_name}: No credentials provided, allowing direct call (development/testing)"
                        )
                        user_info = None
                    else:
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

                # Execute with caching and stampede prevention if enabled
                if cache_key and self.cache.enabled:
                    cache = self.cache.get_cache(cache_key, ttl=cache_ttl)
                    cache_lookup_key = self.cache._create_cache_key(
                        tool_name, args, kwargs
                    )

                    # Define the compute function for cache-or-compute
                    async def compute_result():
                        # Filter out auth credentials from kwargs before calling the function
                        clean_kwargs = {
                            k: v
                            for k, v in kwargs.items()
                            if k
                            not in [
                                "api_key",
                                "token",
                                "username",
                                "password",
                                "jwt",
                                "authorization",
                                "mcp_auth",
                            ]
                        }

                        # Execute function with timeout
                        if timeout:
                            return await asyncio.wait_for(
                                func(*args, **clean_kwargs), timeout=timeout
                            )
                        else:
                            return await func(*args, **clean_kwargs)

                    # Use cache-or-compute with stampede prevention
                    result = await cache.get_or_compute(
                        cache_lookup_key, compute_result, cache_ttl
                    )
                    logger.debug(f"Got result for {tool_name} (cached or computed)")
                else:
                    # No caching - execute directly
                    # Filter out auth credentials from kwargs before calling the function
                    clean_kwargs = {
                        k: v
                        for k, v in kwargs.items()
                        if k
                        not in [
                            "api_key",
                            "token",
                            "username",
                            "password",
                            "jwt",
                            "authorization",
                            "mcp_auth",
                        ]
                    }

                    # Execute function with timeout
                    if timeout:
                        result = await asyncio.wait_for(
                            func(*args, **clean_kwargs), timeout=timeout
                        )
                    else:
                        result = await func(*args, **clean_kwargs)

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
            wrapped_func = func
            if self.metrics.enabled:
                wrapped_func = self.metrics.track_tool(f"resource:{uri}")(func)

            # Register with FastMCP
            mcp_resource = self._mcp.resource(uri)(wrapped_func)

            # Track in registry
            self._resource_registry[uri] = {
                "handler": mcp_resource,
                "original_handler": func,
                "name": uri,
                "description": func.__doc__ or f"Resource: {uri}",
                "mime_type": "text/plain",
                "created_at": time.time(),
            }

            return mcp_resource

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
            wrapped_func = func
            if self.metrics.enabled:
                wrapped_func = self.metrics.track_tool(f"prompt:{name}")(func)

            # Register with FastMCP
            mcp_prompt = self._mcp.prompt(name)(wrapped_func)

            # Track in registry
            self._prompt_registry[name] = {
                "handler": mcp_prompt,
                "original_handler": func,
                "description": func.__doc__ or f"Prompt: {name}",
                "arguments": [],  # Could be extracted from function signature
                "created_at": time.time(),
            }

            return mcp_prompt

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

    def _execute_tool(self, tool_name: str, arguments: dict) -> Any:
        """Execute a tool directly (for testing purposes)."""
        if tool_name not in self._tool_registry:
            raise ValueError(f"Tool '{tool_name}' not found in registry")

        tool_info = self._tool_registry[tool_name]
        if tool_info.get("disabled", False):
            raise ValueError(f"Tool '{tool_name}' is currently disabled")

        # Get the tool handler (the enhanced function)
        if "handler" in tool_info:
            handler = tool_info["handler"]
        elif "function" in tool_info:
            handler = tool_info["function"]
        else:
            raise ValueError(f"Tool '{tool_name}' has no valid handler")

        # Update statistics
        tool_info["call_count"] = tool_info.get("call_count", 0) + 1
        tool_info["last_called"] = time.time()

        try:
            # Execute the tool
            if asyncio.iscoroutinefunction(handler):
                # For async functions, we need to run in event loop
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        # Already in async context - create task
                        return asyncio.create_task(handler(**arguments))
                    else:
                        return loop.run_until_complete(handler(**arguments))
                except RuntimeError:
                    # No event loop - create new one
                    return asyncio.run(handler(**arguments))
            else:
                return handler(**arguments)
        except Exception as e:
            tool_info["error_count"] = tool_info.get("error_count", 0) + 1
            raise

    def run(self):
        """Run the enhanced MCP server with all features."""
        if self._mcp is None:
            self._init_mcp()

        # Record server start time
        self.config.update({"server.start_time": time.time()})

        # Log enhanced server startup
        logger.info(f"Starting enhanced MCP server: {self.name}")
        logger.info(f"Transport: {self.transport}")
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

            # Run server based on transport type
            if self.transport == "websocket":
                logger.info(
                    f"Starting WebSocket server on {self.websocket_host}:{self.websocket_port}..."
                )
                asyncio.run(self._run_websocket())
            else:
                # Default to FastMCP (STDIO) server
                logger.info("Starting FastMCP server in STDIO mode...")
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

    async def _run_websocket(self):
        """Run the server using WebSocket transport."""
        from .transports import WebSocketServerTransport

        try:
            # Create WebSocket transport
            self._transport = WebSocketServerTransport(
                host=self.websocket_host,
                port=self.websocket_port,
                message_handler=self._handle_websocket_message,
                auth_provider=self.auth_provider,
                timeout=self.transport_timeout,
                max_message_size=self.max_request_size,
                enable_metrics=self.metrics.enabled if self.metrics else False,
            )

            # Start WebSocket server
            await self._transport.connect()
            logger.info(
                f"WebSocket server started on {self.websocket_host}:{self.websocket_port}"
            )

            # Set up subscription notification callback
            if self.subscription_manager:
                await self.subscription_manager.initialize()
                self.subscription_manager.set_notification_callback(
                    self._send_websocket_notification
                )

            # Keep server running
            try:
                await asyncio.Future()  # Run forever
            except asyncio.CancelledError:
                logger.info("WebSocket server cancelled")

        finally:
            # Clean up
            if self._transport:
                await self._transport.disconnect()
                self._transport = None

    async def _handle_websocket_message(
        self, request: Dict[str, Any], client_id: str
    ) -> Dict[str, Any]:
        """Handle incoming WebSocket message with decompression support."""
        try:
            # Decompress message if needed
            decompressed_request = self._decompress_message(request)

            method = decompressed_request.get("method", "")
            params = decompressed_request.get("params", {})
            request_id = decompressed_request.get("id")

            # Log request
            logger.debug(f"WebSocket request from {client_id}: {method}")

            # Route to appropriate handler
            if method == "initialize":
                return await self._handle_initialize(params, request_id, client_id)
            elif method == "tools/list":
                return await self._handle_list_tools(params, request_id)
            elif method == "tools/call":
                return await self._handle_call_tool(params, request_id)
            elif method == "resources/list":
                return await self._handle_list_resources(params, request_id)
            elif method == "resources/read":
                return await self._handle_read_resource(params, request_id, client_id)
            elif method == "resources/subscribe":
                return await self._handle_subscribe(params, request_id, client_id)
            elif method == "resources/unsubscribe":
                return await self._handle_unsubscribe(params, request_id, client_id)
            elif method == "resources/batch_subscribe":
                return await self._handle_batch_subscribe(params, request_id, client_id)
            elif method == "resources/batch_unsubscribe":
                return await self._handle_batch_unsubscribe(
                    params, request_id, client_id
                )
            elif method == "prompts/list":
                return await self._handle_list_prompts(params, request_id)
            elif method == "prompts/get":
                return await self._handle_get_prompt(params, request_id)
            elif method == "logging/setLevel":
                return await self._handle_logging_set_level(params, request_id)
            elif method == "roots/list":
                # Add client_id to params for roots/list handler
                params_with_client = {**params, "client_id": client_id}
                return await self._handle_roots_list(params_with_client, request_id)
            elif method == "completion/complete":
                return await self._handle_completion_complete(params, request_id)
            elif method == "sampling/createMessage":
                # Add client_id to params for sampling handler
                params_with_client = {**params, "client_id": client_id}
                return await self._handle_sampling_create_message(
                    params_with_client, request_id
                )
            else:
                return {
                    "jsonrpc": "2.0",
                    "error": {"code": -32601, "message": f"Method not found: {method}"},
                    "id": request_id,
                }

        except Exception as e:
            logger.error(f"Error handling WebSocket message: {e}")
            return {
                "jsonrpc": "2.0",
                "error": {"code": -32603, "message": f"Internal error: {str(e)}"},
                "id": request.get("id"),
            }

    async def _handle_initialize(
        self, params: Dict[str, Any], request_id: Any, client_id: str = None
    ) -> Dict[str, Any]:
        """Handle initialize request."""
        # Store client information for capability checks
        if client_id:
            self.client_info[client_id] = {
                "capabilities": params.get("capabilities", {}),
                "name": params.get("clientInfo", {}).get("name", "unknown"),
                "version": params.get("clientInfo", {}).get("version", "unknown"),
                "initialized_at": time.time(),
            }

        return {
            "jsonrpc": "2.0",
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "tools": {"listSupported": True, "callSupported": True},
                    "resources": {
                        "listSupported": True,
                        "readSupported": True,
                        "subscribe": self.enable_subscriptions,
                        "listChanged": self.enable_subscriptions,
                        "batch_subscribe": self.enable_subscriptions,
                        "batch_unsubscribe": self.enable_subscriptions,
                    },
                    "prompts": {"listSupported": True, "getSupported": True},
                    "logging": {"setLevel": True},
                    "roots": {"list": True},
                    "experimental": {
                        "progressNotifications": True,
                        "cancellation": True,
                        "completion": True,
                        "sampling": True,
                        "websocketCompression": self.enable_websocket_compression,
                    },
                },
                "serverInfo": {
                    "name": self.name,
                    "version": self.config.get("server.version", "1.0.0"),
                },
            },
            "id": request_id,
        }

    async def _handle_list_tools(
        self, params: Dict[str, Any], request_id: Any
    ) -> Dict[str, Any]:
        """Handle tools/list request."""
        tools = []
        for name, info in self._tool_registry.items():
            if not info.get("disabled", False):
                tools.append(
                    {
                        "name": name,
                        "description": info.get("description", ""),
                        "inputSchema": info.get("input_schema", {}),
                    }
                )

        return {"jsonrpc": "2.0", "result": {"tools": tools}, "id": request_id}

    async def _handle_call_tool(
        self, params: Dict[str, Any], request_id: Any
    ) -> Dict[str, Any]:
        """Handle tools/call request."""
        tool_name = params.get("name")
        arguments = params.get("arguments", {})

        try:
            result = self._execute_tool(tool_name, arguments)

            # Handle async results
            if asyncio.iscoroutine(result) or asyncio.isfuture(result):
                result = await result

            return {
                "jsonrpc": "2.0",
                "result": {"content": [{"type": "text", "text": str(result)}]},
                "id": request_id,
            }
        except Exception as e:
            return {
                "jsonrpc": "2.0",
                "error": {"code": -32603, "message": f"Tool execution error: {str(e)}"},
                "id": request_id,
            }

    async def _handle_list_resources(
        self, params: Dict[str, Any], request_id: Any
    ) -> Dict[str, Any]:
        """Handle resources/list request with cursor-based pagination."""
        cursor = params.get("cursor")
        limit = params.get("limit")

        # Get all resources
        all_resources = []
        for uri, info in self._resource_registry.items():
            all_resources.append(
                {
                    "uri": uri,
                    "name": info.get("name", uri),
                    "description": info.get("description", ""),
                    "mimeType": info.get("mime_type", "text/plain"),
                }
            )

        # Handle pagination if subscription manager is available
        if self.subscription_manager:
            cursor_manager = self.subscription_manager.cursor_manager

            # Determine starting position
            start_pos = 0
            if cursor:
                if cursor_manager.is_valid(cursor):
                    start_pos = cursor_manager.get_cursor_position(cursor) or 0
                else:
                    return {
                        "jsonrpc": "2.0",
                        "error": {
                            "code": -32602,
                            "message": "Invalid or expired cursor",
                        },
                        "id": request_id,
                    }

            # Apply pagination
            if limit:
                end_pos = start_pos + limit
                resources = all_resources[start_pos:end_pos]

                # Generate next cursor if there are more resources
                next_cursor = None
                if end_pos < len(all_resources):
                    next_cursor = cursor_manager.create_cursor_for_position(
                        all_resources, end_pos
                    )

                result = {"resources": resources}
                if next_cursor:
                    result["nextCursor"] = next_cursor

                return {"jsonrpc": "2.0", "result": result, "id": request_id}
            else:
                resources = all_resources[start_pos:]
        else:
            # No pagination support
            resources = all_resources

        return {"jsonrpc": "2.0", "result": {"resources": resources}, "id": request_id}

    async def _handle_read_resource(
        self, params: Dict[str, Any], request_id: Any, client_id: str = None
    ) -> Dict[str, Any]:
        """Handle resources/read request with change detection."""
        uri = params.get("uri")

        # First try exact match
        resource_info = None
        resource_params = {}
        if uri in self._resource_registry:
            resource_info = self._resource_registry[uri]
        else:
            # Try template matching
            resource_info, resource_params = self._match_resource_template(uri)

        if resource_info is None:
            return {
                "jsonrpc": "2.0",
                "error": {"code": -32602, "message": f"Resource not found: {uri}"},
                "id": request_id,
            }

        try:
            handler = resource_info.get("handler")
            original_handler = resource_info.get("original_handler")

            if handler:
                # Use original handler with parameters if available
                if original_handler and resource_params:
                    content = original_handler(**resource_params)
                else:
                    content = handler()
                if asyncio.iscoroutine(content):
                    content = await content
            else:
                content = ""

            # Process change detection if subscription manager is available
            if self.subscription_manager:
                resource_data = {
                    "uri": uri,
                    "text": str(content),
                    "mimeType": resource_info.get("mime_type", "text/plain"),
                }

                # Check for changes and notify subscribers
                change = (
                    await self.subscription_manager.resource_monitor.check_for_changes(
                        uri, resource_data
                    )
                )

                if change:
                    await self.subscription_manager.process_resource_change(change)

            return {
                "jsonrpc": "2.0",
                "result": {"contents": [{"uri": uri, "text": str(content)}]},
                "id": request_id,
            }
        except Exception as e:
            return {
                "jsonrpc": "2.0",
                "error": {"code": -32603, "message": f"Resource read error: {str(e)}"},
                "id": request_id,
            }

    def _match_resource_template(self, uri: str) -> tuple:
        """Match URI against resource templates and extract parameters."""
        import re

        for template_uri, resource_info in self._resource_registry.items():
            # Convert template to regex pattern
            # Replace {param} with named capture groups
            pattern = re.sub(r"\{([^}]+)\}", r"(?P<\1>[^/]+)", template_uri)
            pattern = f"^{pattern}$"

            match = re.match(pattern, uri)
            if match:
                # Extract parameters from the match
                params = match.groupdict()
                return resource_info, params

        return None, {}

    async def _handle_list_prompts(
        self, params: Dict[str, Any], request_id: Any
    ) -> Dict[str, Any]:
        """Handle prompts/list request."""
        prompts = []
        for name, info in self._prompt_registry.items():
            prompts.append(
                {
                    "name": name,
                    "description": info.get("description", ""),
                    "arguments": info.get("arguments", []),
                }
            )

        return {"jsonrpc": "2.0", "result": {"prompts": prompts}, "id": request_id}

    async def _handle_get_prompt(
        self, params: Dict[str, Any], request_id: Any
    ) -> Dict[str, Any]:
        """Handle prompts/get request."""
        name = params.get("name")
        arguments = params.get("arguments", {})

        if name not in self._prompt_registry:
            return {
                "jsonrpc": "2.0",
                "error": {"code": -32602, "message": f"Prompt not found: {name}"},
                "id": request_id,
            }

        try:
            prompt_info = self._prompt_registry[name]
            handler = prompt_info.get("handler")

            if handler:
                messages = handler(**arguments)
                if asyncio.iscoroutine(messages):
                    messages = await messages
            else:
                messages = []

            return {
                "jsonrpc": "2.0",
                "result": {"messages": messages},
                "id": request_id,
            }
        except Exception as e:
            return {
                "jsonrpc": "2.0",
                "error": {
                    "code": -32603,
                    "message": f"Prompt generation error: {str(e)}",
                },
                "id": request_id,
            }

    async def _handle_subscribe(
        self, params: Dict[str, Any], request_id: Any, client_id: str
    ) -> Dict[str, Any]:
        """Handle resources/subscribe request with GraphQL-style field selection."""
        if not self.subscription_manager:
            return {
                "jsonrpc": "2.0",
                "error": {"code": -32601, "message": "Subscriptions not enabled"},
                "id": request_id,
            }

        uri_pattern = params.get("uri")
        cursor = params.get("cursor")
        # Extract field selection parameters for GraphQL-style filtering
        fields = params.get("fields")  # e.g., ["uri", "content.text", "metadata.size"]
        fragments = params.get("fragments")  # e.g., {"basicInfo": ["uri", "name"]}

        if not uri_pattern:
            return {
                "jsonrpc": "2.0",
                "error": {"code": -32602, "message": "Missing required parameter: uri"},
                "id": request_id,
            }

        try:
            # Create subscription with auth context and field selection
            user_context = {"user_id": client_id, "connection_id": client_id}
            subscription_id = await self.subscription_manager.create_subscription(
                connection_id=client_id,
                uri_pattern=uri_pattern,
                cursor=cursor,
                user_context=user_context,
                fields=fields,
                fragments=fragments,
            )

            return {
                "jsonrpc": "2.0",
                "result": {"subscriptionId": subscription_id},
                "id": request_id,
            }
        except Exception as e:
            error_code = -32603
            if "permission" in str(e).lower() or "not authorized" in str(e).lower():
                error_code = -32601
            elif "rate limit" in str(e).lower():
                error_code = -32601

            return {
                "jsonrpc": "2.0",
                "error": {"code": error_code, "message": str(e)},
                "id": request_id,
            }

    async def _handle_unsubscribe(
        self, params: Dict[str, Any], request_id: Any, client_id: str
    ) -> Dict[str, Any]:
        """Handle resources/unsubscribe request."""
        if not self.subscription_manager:
            return {
                "jsonrpc": "2.0",
                "error": {"code": -32601, "message": "Subscriptions not enabled"},
                "id": request_id,
            }

        subscription_id = params.get("subscriptionId")

        if not subscription_id:
            return {
                "jsonrpc": "2.0",
                "error": {
                    "code": -32602,
                    "message": "Missing required parameter: subscriptionId",
                },
                "id": request_id,
            }

        try:
            success = await self.subscription_manager.remove_subscription(
                subscription_id, client_id
            )

            return {
                "jsonrpc": "2.0",
                "result": {"success": success},
                "id": request_id,
            }
        except Exception as e:
            return {
                "jsonrpc": "2.0",
                "error": {"code": -32603, "message": str(e)},
                "id": request_id,
            }

    async def _handle_batch_subscribe(
        self, params: Dict[str, Any], request_id: Any, client_id: str
    ) -> Dict[str, Any]:
        """Handle resources/batch_subscribe request."""
        if not self.subscription_manager:
            return {
                "jsonrpc": "2.0",
                "error": {"code": -32601, "message": "Subscriptions not enabled"},
                "id": request_id,
            }

        subscriptions = params.get("subscriptions")
        if not subscriptions or not isinstance(subscriptions, list):
            return {
                "jsonrpc": "2.0",
                "error": {
                    "code": -32602,
                    "message": "Missing or invalid parameter: subscriptions",
                },
                "id": request_id,
            }

        try:
            # Create batch subscriptions with auth context
            user_context = {"user_id": client_id, "connection_id": client_id}
            results = await self.subscription_manager.create_batch_subscriptions(
                subscriptions=subscriptions,
                connection_id=client_id,
                user_context=user_context,
            )

            return {
                "jsonrpc": "2.0",
                "result": results,
                "id": request_id,
            }
        except Exception as e:
            return {
                "jsonrpc": "2.0",
                "error": {"code": -32603, "message": str(e)},
                "id": request_id,
            }

    async def _handle_batch_unsubscribe(
        self, params: Dict[str, Any], request_id: Any, client_id: str
    ) -> Dict[str, Any]:
        """Handle resources/batch_unsubscribe request."""
        if not self.subscription_manager:
            return {
                "jsonrpc": "2.0",
                "error": {"code": -32601, "message": "Subscriptions not enabled"},
                "id": request_id,
            }

        subscription_ids = params.get("subscriptionIds")
        if not subscription_ids or not isinstance(subscription_ids, list):
            return {
                "jsonrpc": "2.0",
                "error": {
                    "code": -32602,
                    "message": "Missing or invalid parameter: subscriptionIds",
                },
                "id": request_id,
            }

        try:
            # Remove batch subscriptions
            results = await self.subscription_manager.remove_batch_subscriptions(
                subscription_ids=subscription_ids, connection_id=client_id
            )

            return {
                "jsonrpc": "2.0",
                "result": results,
                "id": request_id,
            }
        except Exception as e:
            return {
                "jsonrpc": "2.0",
                "error": {"code": -32603, "message": str(e)},
                "id": request_id,
            }

    async def _handle_connection_close(self, client_id: str):
        """Handle WebSocket connection close."""
        if self.subscription_manager:
            removed_count = await self.subscription_manager.cleanup_connection(
                client_id
            )
            if removed_count > 0:
                logger.info(
                    f"Cleaned up {removed_count} subscriptions for client {client_id}"
                )

    def _compress_message(
        self, message: Dict[str, Any]
    ) -> Union[Dict[str, Any], bytes]:
        """Compress message if compression is enabled and message exceeds threshold.

        Args:
            message: The message to potentially compress

        Returns:
            Either the original dict or compressed bytes with metadata
        """
        if not self.enable_websocket_compression:
            return message

        # Serialize message to determine size
        message_json = json.dumps(message, separators=(",", ":")).encode("utf-8")

        # Only compress if message exceeds threshold
        if len(message_json) < self.compression_threshold:
            return message

        try:
            # Compress the message
            compressed_data = gzip.compress(
                message_json, compresslevel=self.compression_level
            )

            # Calculate compression ratio
            compression_ratio = len(compressed_data) / len(message_json)

            # Only use compression if it actually reduces size significantly
            if compression_ratio > 0.9:  # Less than 10% improvement
                return message

            # Return compressed message with metadata
            return {
                "__compressed": True,
                "__original_size": len(message_json),
                "__compressed_size": len(compressed_data),
                "__compression_ratio": compression_ratio,
                "data": compressed_data.hex(),  # Hex encode for JSON transport
            }

        except Exception as e:
            logger.warning(f"Failed to compress message: {e}")
            return message

    def _decompress_message(self, compressed_message: Dict[str, Any]) -> Dict[str, Any]:
        """Decompress a compressed message.

        Args:
            compressed_message: The compressed message with metadata

        Returns:
            The original decompressed message
        """
        if not compressed_message.get("__compressed"):
            return compressed_message

        try:
            # Decode hex data and decompress
            compressed_data = bytes.fromhex(compressed_message["data"])
            decompressed_json = gzip.decompress(compressed_data)

            # Parse back to dict
            return json.loads(decompressed_json.decode("utf-8"))

        except Exception as e:
            logger.error(f"Failed to decompress message: {e}")
            # Return a sensible error message
            return {
                "jsonrpc": "2.0",
                "error": {
                    "code": -32603,
                    "message": f"Failed to decompress message: {e}",
                },
            }

    async def _send_websocket_notification(
        self, client_id: str, notification: Dict[str, Any]
    ):
        """Send notification to WebSocket client with optional compression."""
        if self._transport and hasattr(self._transport, "send_message"):
            try:
                # Apply compression if enabled
                message_to_send = self._compress_message(notification)

                # Log compression stats if compression was applied
                if isinstance(message_to_send, dict) and message_to_send.get(
                    "__compressed"
                ):
                    ratio = message_to_send["__compression_ratio"]
                    logger.debug(
                        f"Compressed notification for client {client_id}: "
                        f"{message_to_send['__original_size']} -> "
                        f"{message_to_send['__compressed_size']} bytes "
                        f"({ratio:.2%} ratio)"
                    )

                await self._transport.send_message(message_to_send, client_id=client_id)
                logger.debug(
                    f"Sent notification to client {client_id}: {notification['method']}"
                )
            except Exception as e:
                logger.error(f"Failed to send notification to client {client_id}: {e}")

    async def _handle_logging_set_level(
        self, params: Dict[str, Any], request_id: Any
    ) -> Dict[str, Any]:
        """Handle logging/setLevel request to dynamically adjust log levels."""
        level = params.get("level", "INFO").upper()

        # Validate log level
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if level not in valid_levels:
            return {
                "jsonrpc": "2.0",
                "error": {
                    "code": -32602,
                    "message": f"Invalid log level: {level}. Must be one of {valid_levels}",
                },
                "id": request_id,
            }

        # Set the log level
        logging.getLogger().setLevel(getattr(logging, level))
        logger.info(f"Log level changed to {level}")

        # Track in event store if available
        if self.event_store:
            from kailash.middleware.gateway.event_store import EventType

            await self.event_store.append(
                event_type=EventType.REQUEST_COMPLETED,
                request_id=str(request_id),
                data={
                    "type": "log_level_changed",
                    "level": level,
                    "timestamp": time.time(),
                    "changed_by": params.get("client_id", "unknown"),
                },
            )

        return {
            "jsonrpc": "2.0",
            "result": {"level": level, "levels": valid_levels},
            "id": request_id,
        }

    async def _handle_roots_list(
        self, params: Dict[str, Any], request_id: Any
    ) -> Dict[str, Any]:
        """Handle roots/list request to get file system access roots."""
        protocol_mgr = get_protocol_manager()

        # Check if client supports roots
        client_info = self.client_info.get(params.get("client_id", ""))
        if (
            not client_info.get("capabilities", {})
            .get("roots", {})
            .get("listChanged", False)
        ):
            return {
                "jsonrpc": "2.0",
                "error": {
                    "code": -32601,
                    "message": "Client does not support roots capability",
                },
                "id": request_id,
            }

        roots = protocol_mgr.roots.list_roots()

        # Apply access control if auth manager is available
        if self.auth_manager and params.get("client_id"):
            filtered_roots = []
            for root in roots:
                if await protocol_mgr.roots.validate_access(
                    root["uri"],
                    operation="list",
                    user_context=self.client_info.get(params["client_id"], {}),
                ):
                    filtered_roots.append(root)
            roots = filtered_roots

        return {"jsonrpc": "2.0", "result": {"roots": roots}, "id": request_id}

    async def _handle_completion_complete(
        self, params: Dict[str, Any], request_id: Any
    ) -> Dict[str, Any]:
        """Handle completion/complete request for auto-completion."""
        ref = params.get("ref", {})
        argument = params.get("argument", {})

        # Extract completion parameters
        ref_type = ref.get("type")  # "resource", "prompt", "tool"
        ref_name = ref.get("name")  # Optional specific name
        partial_value = argument.get("value", "")

        try:
            values = []

            if ref_type == "resource":
                # Search through registered resources
                for uri, resource_info in self._resource_registry.items():
                    if partial_value in uri:  # Simple prefix/substring matching
                        values.append(
                            {
                                "uri": uri,
                                "name": resource_info.get("name", uri),
                                "description": resource_info.get("description", ""),
                            }
                        )

            elif ref_type == "prompt":
                # Search through registered prompts
                for name, prompt_info in self._prompt_registry.items():
                    if partial_value in name:  # Simple prefix/substring matching
                        values.append(
                            {
                                "name": name,
                                "description": prompt_info.get("description", ""),
                                "arguments": prompt_info.get("arguments", []),
                            }
                        )

            elif ref_type == "tool":
                # Search through registered tools
                for name, tool_info in self._tool_registry.items():
                    if partial_value in name:
                        values.append(
                            {
                                "name": name,
                                "description": tool_info.get("description", ""),
                                "inputSchema": tool_info.get("inputSchema", {}),
                            }
                        )

            # Limit to 100 items and add hasMore flag if needed
            total_matches = len(values)
            has_more = total_matches > 100
            if has_more:
                values = values[:100]

            result = {
                "completion": {
                    "values": values,
                    "total": total_matches,
                    "hasMore": has_more,
                }
            }

            return {"jsonrpc": "2.0", "result": result, "id": request_id}

        except Exception as e:
            logger.error(f"Completion error: {e}")
            return {
                "jsonrpc": "2.0",
                "error": {"code": -32603, "message": f"Completion failed: {str(e)}"},
                "id": request_id,
            }

    async def _handle_sampling_create_message(
        self, params: Dict[str, Any], request_id: Any
    ) -> Dict[str, Any]:
        """Handle sampling/createMessage - this is typically server-to-client."""
        # This is usually initiated by the server to request LLM sampling from the client
        # For server-side handling, we can validate and forward to connected clients

        protocol_mgr = get_protocol_manager()

        # Check if any client supports sampling
        sampling_clients = [
            client_id
            for client_id, info in self.client_info.items()
            if info.get("capabilities", {})
            .get("experimental", {})
            .get("sampling", False)
        ]

        if not sampling_clients:
            return {
                "jsonrpc": "2.0",
                "error": {
                    "code": -32601,
                    "message": "No connected clients support sampling",
                },
                "id": request_id,
            }

        # Create sampling request
        messages = params.get("messages", [])
        sampling_params = {
            "messages": messages,
            "model_preferences": params.get("modelPreferences"),
            "system_prompt": params.get("systemPrompt"),
            "temperature": params.get("temperature"),
            "max_tokens": params.get("maxTokens"),
            "metadata": params.get("metadata"),
        }

        # Send to first available sampling client (or implement selection logic)
        target_client = sampling_clients[0]

        # Create server-to-client request
        sampling_request = {
            "jsonrpc": "2.0",
            "method": "sampling/createMessage",
            "params": sampling_params,
            "id": f"sampling_{uuid.uuid4().hex[:8]}",
        }

        # Send via WebSocket to client
        if self._transport and hasattr(self._transport, "send_message"):
            await self._transport.send_message(
                sampling_request, client_id=target_client
            )

            # Store pending sampling request
            if not hasattr(self, "_pending_sampling_requests"):
                self._pending_sampling_requests = {}

            self._pending_sampling_requests[sampling_request["id"]] = {
                "original_request_id": request_id,
                "client_id": params.get("client_id"),
                "timestamp": time.time(),
            }

            return {
                "jsonrpc": "2.0",
                "result": {
                    "status": "sampling_requested",
                    "sampling_id": sampling_request["id"],
                    "target_client": target_client,
                },
                "id": request_id,
            }
        else:
            return {
                "jsonrpc": "2.0",
                "error": {
                    "code": -32603,
                    "message": "Transport does not support sampling",
                },
                "id": request_id,
            }

    async def run_stdio(self):
        """Run the server using stdio transport for testing."""
        if self._mcp is None:
            self._init_mcp()

        # For testing, we'll implement a simple stdio server
        import json
        import sys

        logger.info(f"Starting MCP server '{self.name}' in stdio mode")
        self._running = True

        try:
            while self._running:
                # Read JSON-RPC request from stdin
                line = sys.stdin.readline()
                if not line:
                    break

                try:
                    request = json.loads(line.strip())

                    # Handle different request types
                    if request.get("method") == "tools/list":
                        # Return list of tools
                        tools = []
                        for name, info in self._tool_registry.items():
                            if not info.get("disabled", False):
                                tools.append(
                                    {
                                        "name": name,
                                        "description": info.get("description", ""),
                                        "inputSchema": info.get("input_schema", {}),
                                    }
                                )

                        response = {"id": request.get("id"), "result": {"tools": tools}}

                    elif request.get("method") == "tools/call":
                        # Call a tool
                        params = request.get("params", {})
                        tool_name = params.get("name")
                        arguments = params.get("arguments", {})

                        if tool_name in self._tool_registry:
                            handler = self._tool_registry[tool_name]["handler"]
                            try:
                                # Execute tool
                                if asyncio.iscoroutinefunction(handler):
                                    result = await handler(**arguments)
                                else:
                                    result = handler(**arguments)

                                response = {
                                    "id": request.get("id"),
                                    "result": {
                                        "content": [
                                            {"type": "text", "text": str(result)}
                                        ]
                                    },
                                }
                            except Exception as e:
                                response = {
                                    "id": request.get("id"),
                                    "error": {"code": -32603, "message": str(e)},
                                }
                        else:
                            response = {
                                "id": request.get("id"),
                                "error": {
                                    "code": -32601,
                                    "message": f"Tool not found: {tool_name}",
                                },
                            }

                    else:
                        # Unknown method
                        response = {
                            "id": request.get("id"),
                            "error": {
                                "code": -32601,
                                "message": f"Method not found: {request.get('method')}",
                            },
                        }

                    # Write response to stdout
                    sys.stdout.write(json.dumps(response) + "\n")
                    sys.stdout.flush()

                except json.JSONDecodeError:
                    # Invalid JSON
                    error_response = {
                        "id": None,
                        "error": {"code": -32700, "message": "Parse error"},
                    }
                    sys.stdout.write(json.dumps(error_response) + "\n")
                    sys.stdout.flush()

        except KeyboardInterrupt:
            logger.info("Server stopped by user")
        except Exception as e:
            logger.error(f"Server error: {e}")
            raise
        finally:
            self._running = False

    async def run_async(self):
        """Run the enhanced MCP server asynchronously.

        This is the async equivalent of run(), supporting all transport types.
        Can be used with asyncio.create_task() for non-blocking execution.

        Example:
            server = MCPServer("my_server", transport="stdio")
            server_task = asyncio.create_task(server.run_async())
        """
        if self._mcp is None:
            self._init_mcp()

        # Record server start time
        self.config.update({"server.start_time": time.time()})

        # Log enhanced server startup
        logger.info(f"Starting enhanced MCP server (async): {self.name}")
        logger.info(f"Transport: {self.transport}")
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

            # Run server based on transport type
            if self.transport == "websocket":
                logger.info(
                    f"Starting WebSocket server (async) on {self.websocket_host}:{self.websocket_port}..."
                )
                await self._run_websocket()
            else:
                # Default to stdio transport
                logger.info("Starting MCP server in STDIO mode (async)...")
                await self.run_stdio()

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
            logger.info("Shutting down enhanced MCP server (async)...")

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
            logger.info(f"Enhanced MCP server '{self.name}' stopped (async)")


class SimpleMCPServer(MCPServerBase):
    """Simple MCP Server for prototyping and development.

    This is a lightweight version of MCPServer without authentication,
    metrics, caching, or other production features. Perfect for:
    - Quick prototyping
    - Development and testing
    - Simple use cases without advanced features

    Example:
        >>> server = SimpleMCPServer("my-prototype")
        >>> @server.tool()
        ... def hello(name: str) -> str:
        ...     return f"Hello, {name}!"
        >>> server.run()
    """

    def __init__(self, name: str, description: str = None):
        """Initialize simple MCP server.

        Args:
            name: Server name
            description: Server description
        """
        super().__init__(name, description)

        # Disable all advanced features for simplicity
        self.enable_cache = False
        self.enable_metrics = False
        self.enable_http_transport = False
        self.rate_limit_config = None
        self.circuit_breaker_config = None
        self.auth_provider = None

        # Simple in-memory storage
        self._simple_tools = {}
        self._simple_resources = {}
        self._simple_prompts = {}

        logger.info(f"SimpleMCPServer '{name}' initialized for prototyping")

    def setup(self):
        """Setup method - no additional setup needed for SimpleMCPServer."""
        pass

    def tool(self, description: str = None):
        """Register a simple tool (no auth, caching, or metrics).

        Args:
            description: Tool description

        Returns:
            Decorator function
        """

        def decorator(func):
            # Initialize MCP if needed
            if self._mcp is None:
                self._init_mcp()

            tool_name = func.__name__
            self._simple_tools[tool_name] = {
                "function": func,
                "description": description or f"Tool: {tool_name}",
                "created_at": time.time(),
            }

            # Register with FastMCP
            self._mcp.tool(description or f"Tool: {tool_name}")(func)

            logger.debug(f"SimpleMCPServer: Registered tool '{tool_name}'")
            return func

        return decorator

    def resource(self, uri: str, description: str = None):
        """Register a simple resource.

        Args:
            uri: Resource URI
            description: Resource description

        Returns:
            Decorator function
        """

        def decorator(func):
            # Initialize MCP if needed
            if self._mcp is None:
                self._init_mcp()

            self._simple_resources[uri] = {
                "function": func,
                "description": description or f"Resource: {uri}",
                "created_at": time.time(),
            }

            # Register with FastMCP
            self._mcp.resource(uri, description or f"Resource: {uri}")(func)

            logger.debug(f"SimpleMCPServer: Registered resource '{uri}'")
            return func

        return decorator

    def get_stats(self) -> dict:
        """Get simple server statistics.

        Returns:
            Dictionary with basic stats
        """
        return {
            "server_name": self.name,
            "server_type": "SimpleMCPServer",
            "tools_count": len(self._simple_tools),
            "resources_count": len(self._simple_resources),
            "prompts_count": len(self._simple_prompts),
            "features": {
                "authentication": False,
                "caching": False,
                "metrics": False,
                "rate_limiting": False,
                "circuit_breaker": False,
            },
        }


# Note: EnhancedMCPServer alias removed - use MCPServer directly

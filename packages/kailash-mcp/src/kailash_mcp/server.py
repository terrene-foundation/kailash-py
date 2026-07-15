# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
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

    >>> from kailash_mcp import MCPServer
    >>> server = MCPServer("my-server", enable_cache=True)
    >>> @server.tool(cache_key="search", cache_ttl=600)
    ... def search(query: str) -> dict:
    ...     return {"results": f"Found data for {query}"}
    >>> server.run()

Enhanced Production Usage:
    Server with authentication and monitoring:

    >>> from kailash_mcp.auth.providers import APIKeyAuth
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
import base64
import functools
import gzip
import json
import logging
import re
import time
import uuid
from abc import ABC, abstractmethod
from collections import deque
from collections.abc import Callable
from pathlib import Path
from typing import Any, Dict, List, Optional, TypeVar, Union
from urllib.parse import urlparse

from kailash_mcp.advanced.features import (
    ElicitationSystem,
    StructuredTool,
    ToolAnnotation,
)
from kailash_mcp.auth.providers import (
    AuthManager,
    AuthProvider,
    PermissionManager,
    RateLimiter,
)
from kailash_mcp.errors import (
    AuthenticationError,
    AuthorizationError,
    ErrorAggregator,
    MCPError,
    MCPErrorCode,
    RateLimitError,
    ResourceError,
    RetryableOperation,
    ToolError,
    ValidationError,
)
from kailash_mcp.protocol.protocol import ToolResult, get_protocol_manager
from kailash_mcp.utils import (
    CacheManager,
    ConfigManager,
    MetricsCollector,
    format_response,
)

logger = logging.getLogger(__name__)


# Supported MCP protocol-handshake revisions, newest first. The server
# negotiates genuinely (MCP base-protocol lifecycle): on ``initialize`` it
# echoes the client's requested version when supported, else returns the
# newest supported version. A hardcoded/echoed fixed version string is
# non-compliant.
SUPPORTED_PROTOCOL_VERSIONS = (
    "2025-11-25",
    "2025-06-18",
    "2025-03-26",
    "2024-11-05",
)
LATEST_PROTOCOL_VERSION = SUPPORTED_PROTOCOL_VERSIONS[0]


def negotiate_protocol_version(requested: Any) -> str:
    """Negotiate the response ``protocolVersion`` for an ``initialize`` request.

    Echoes the client's requested version when the server supports it;
    otherwise returns the newest supported version (never a hardcoded fixed
    string). ``requested`` is the client-sent ``params["protocolVersion"]``
    (or ``None`` when absent).
    """
    if isinstance(requested, str) and requested in SUPPORTED_PROTOCOL_VERSIONS:
        return requested
    return LATEST_PROTOCOL_VERSION


# Server-chosen page size for opaque-cursor list pagination (spec 2025-11-25).
# The server picks the page size itself: a client does NOT need to send a
# ``limit`` to receive a ``nextCursor``. Cursors are opaque to clients; an
# invalid/expired cursor is answered with a ``-32602`` error.
_DEFAULT_PAGE_SIZE = 100

# MCP logging severity ladder (logging/setLevel + notifications/message,
# spec 2025-11-25), ordered least→most severe. The rank gates emission: a
# message below a client's set minimum level is suppressed.
_MCP_LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
_MCP_LOG_LEVEL_RANK = {lvl: idx for idx, lvl in enumerate(_MCP_LOG_LEVELS)}

# Content-redaction patterns for notifications/message ``data`` (security.md —
# no secrets/PII on an observable surface). A sensitive object KEY has its whole
# value replaced; every string is scanned for secret/PII token shapes.
_SECRET_KEY_PATTERN = re.compile(
    r"(pass(word|wd)?|secret|token|api[_-]?key|apikey|authorization|"
    r"access[_-]?token|refresh[_-]?token|client[_-]?secret|private[_-]?key|"
    r"credential|ssn|session[_-]?id)",
    re.IGNORECASE,
)
# scheme://user:PASS@host — replace the userinfo (user:pass) span, KEEP the
# scheme and host so the log line stays legible. Handled first (before the
# token-shape patterns below) so the retained host does not re-trigger a match.
_URL_USERINFO_PATTERN = re.compile(r"([A-Za-z][A-Za-z0-9+.\-]*://)[^\s:/@]+:[^\s/@]+@")
_SECRET_VALUE_PATTERNS = (
    re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"),  # email
    re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),  # US SSN
    re.compile(r"\b(?:sk|pk|rk)-[A-Za-z0-9_\-]{12,}\b"),  # provider API keys
    re.compile(r"\bBearer\s+[A-Za-z0-9._\-]{8,}\b", re.IGNORECASE),  # bearer
    re.compile(r"\beyJ[A-Za-z0-9._\-]{10,}\b"),  # JWT (eyJ… header)
    re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),  # AWS access key id
    # AWS secret access key: 40-char base64 that INCLUDES a `/` or `+` (which
    # excludes hex digests like a 40-char SHA-1, so a git SHA is not redacted).
    re.compile(r"\b(?=[A-Za-z0-9/+]{40}\b)[A-Za-z0-9]*[/+][A-Za-z0-9/+]*\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{16,}\b"),  # GitHub token
    re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b"),  # Google API key
    re.compile(r"\bxox[baprs]-[0-9A-Za-z\-]{10,}\b"),  # Slack token
)

_REDACTED = "[REDACTED]"


def _completion_rank(candidate: str, partial: str) -> int:
    """Relevance rank for a completion candidate (lower = more relevant).

    ``0`` exact match, ``1`` prefix match (``startswith``), ``2`` substring
    match. Case-insensitive. Used to order completion/complete candidates so the
    100-item cap keeps the most relevant matches (spec 2025-11-25).
    """
    cand = candidate.lower()
    part = partial.lower()
    if cand == part:
        return 0
    if cand.startswith(part):
        return 1
    return 2


def _redact_log_string(text: str) -> str:
    """Scrub secret/PII token shapes from a single string."""
    # Userinfo first: keep scheme + host, redact the user:pass span so a
    # credential embedded in a connection string does not leak, and the
    # retained host does not re-trigger a token-shape match below.
    text = _URL_USERINFO_PATTERN.sub(r"\1" + _REDACTED + "@", text)
    for pattern in _SECRET_VALUE_PATTERNS:
        text = pattern.sub(_REDACTED, text)
    return text


def _redact_log_data(value: Any) -> Any:
    """Recursively scrub secrets/PII from a ``notifications/message`` payload.

    A sensitive object KEY (``password`` / ``api_key`` / ``token`` / …) has its
    whole value replaced with ``[REDACTED]``; every string value AND every
    string KEY is additionally scanned for secret/PII token shapes (AWS/GitHub/
    Google/Slack keys, provider API keys, bearer tokens, JWTs, URL-userinfo
    credentials, emails, SSNs). Scanning KEYS too closes the gap where a secret
    lives in the key position (e.g. ``{"AKIA…": "…"}``) — a value-only scrubber
    would ship it to the notifications wire. Non-container scalars pass through
    unchanged. Applied to the emitted ``data`` before it leaves the server
    (security.md § Redactor Contract — no secrets/PII on an observable surface).
    """
    if isinstance(value, dict):
        redacted: Dict[Any, Any] = {}
        for key, val in value.items():
            # Scrub secret/PII token shapes embedded in the KEY string itself.
            out_key = _redact_log_string(key) if isinstance(key, str) else key
            if isinstance(key, str) and _SECRET_KEY_PATTERN.search(key):
                redacted[out_key] = _REDACTED
            else:
                redacted[out_key] = _redact_log_data(val)
        return redacted
    if isinstance(value, (list, tuple)):
        return [_redact_log_data(item) for item in value]
    if isinstance(value, str):
        return _redact_log_string(value)
    return value


# MCP content-block discriminators a tool may return directly (tools/call
# result.content items). A tool handler returning one of these — or a list of
# them, or a ``ToolResult`` — is passed through verbatim rather than
# str()-wrapped (spec 2025-11-25 tool result content).
_CONTENT_BLOCK_TYPES = frozenset(
    {"text", "image", "audio", "resource", "resource_link"}
)

# MIME types treated as text for resources/read. Anything else (or raw bytes)
# is emitted as a base64 ``blob`` rather than a corrupting ``text`` field.
_TEXT_MIME_TYPES = frozenset(
    {
        "application/json",
        "application/xml",
        "application/javascript",
        "application/ecmascript",
        "application/x-yaml",
        "application/yaml",
        "application/sql",
    }
)


def _is_text_mime(mime_type: Optional[str]) -> bool:
    """Return True when ``mime_type`` denotes text-serialisable content.

    Text when the type is ``text/*``, a known textual application type, or a
    structured-suffix type (``+json`` / ``+xml``). Everything else (images,
    audio, ``application/octet-stream``, …) is binary and MUST be base64
    ``blob``-encoded so raw bytes are not corrupted by ``str()``.
    """
    if not mime_type or not isinstance(mime_type, str):
        return True
    mime = mime_type.split(";", 1)[0].strip().lower()
    if mime.startswith("text/"):
        return True
    if mime.endswith("+json") or mime.endswith("+xml"):
        return True
    return mime in _TEXT_MIME_TYPES


def _annotations_to_mcp(annotations: Any) -> Optional[Dict[str, Any]]:
    """Map a registered tool annotation to MCP ``tools/list`` hint fields.

    Accepts a :class:`ToolAnnotation` or a raw dict of MCP hints. The emitted
    hints (``readOnlyHint`` / ``destructiveHint`` / ``idempotentHint``) are
    ADVISORY ONLY — see ``_handle_list_tools`` for the authorization invariant.
    """
    if annotations is None:
        return None
    if isinstance(annotations, ToolAnnotation):
        return {
            "readOnlyHint": annotations.is_read_only,
            "destructiveHint": annotations.is_destructive,
            "idempotentHint": annotations.is_idempotent,
        }
    if isinstance(annotations, dict):
        return dict(annotations)
    return None


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
        self._mcp: Any = None
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
        >>> from kailash_mcp import MCPServer
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
        >>> from kailash_mcp.auth.providers import APIKeyAuth
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
        websocket_host: str = "127.0.0.1",
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
            from kailash_mcp.errors import CircuitBreakerRetry

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

        # Per-session (client_id) request ids already used. JSON-RPC request
        # ids MUST NOT be reused within a session (spec 2025-11-25); a
        # duplicate id is rejected with an Invalid Request error. BOTH maps are
        # BOUNDED to avoid a remote OOM/DoS: the per-session id set is capped
        # (FIFO eviction via the order deque, _MAX_SEEN_REQUEST_IDS) so a
        # client streaming unique ids cannot grow it without bound, and both
        # are popped on disconnect (_on_ws_disconnect) so churned connections
        # do not leak.
        self._session_seen_ids: Dict[str, set] = {}
        self._session_seen_order: Dict[str, deque] = {}

        # Resource subscription support
        self.enable_subscriptions = enable_subscriptions
        self.event_store = event_store
        self.subscription_manager = None
        if self.enable_subscriptions:
            from kailash_mcp.advanced.subscriptions import ResourceSubscriptionManager

            self.subscription_manager = ResourceSubscriptionManager(
                auth_manager=(
                    self.auth_manager if hasattr(self, "auth_manager") else None
                ),
                event_store=event_store,
                rate_limiter=getattr(self, "rate_limiter", None),
            )

        # Opaque-cursor pagination store (spec 2025-11-25). Server-owned so
        # tools/list, prompts/list, resources/list AND resources/templates/list
        # all page through ONE cursor scheme. Reuse the subscription manager's
        # instance when subscriptions are enabled so a cursor issued by one
        # list method validates through the same store.
        if self.subscription_manager is not None:
            self._cursor_manager = self.subscription_manager.cursor_manager
        else:
            from kailash_mcp.advanced.subscriptions import CursorManager

            self._cursor_manager = CursorManager()

        # MCP logging levels (logging/setLevel + notifications/message,
        # spec 2025-11-25). Per-client minimum level gates notifications/message
        # emission — a message below a client's set level is suppressed. Clients
        # that never call setLevel fall back to ``_log_level_default``.
        self._client_log_levels: Dict[str, str] = {}
        self._log_level_default = "INFO"

        # Transport instance (for WebSocket and other transports)
        self._transport = None

        # ElicitationSystem — server-to-client interactive-input subsystem
        # (MCP 2025-06-18 elicitation/create). Constructed without a bound
        # send-callable; the send-half is bound via `_bind_elicitation_transport`
        # when the transport is established. Exposed as a public attribute
        # so tools can call `server.elicitation_system.request_input(...)`.
        # This is the production call site required by
        # rules/orphan-detection.md §1 for the ElicitationSystem manager.
        self.elicitation_system: ElicitationSystem = ElicitationSystem()

    def _bind_elicitation_transport(self) -> None:
        """Bind the active transport's send-callable to the elicitation system.

        Called from transport-startup paths (`_run_websocket` etc.) once
        `self._transport` has been established. Idempotent — safe to call
        multiple times if the transport reconnects.
        """
        if self._transport is None:
            return
        send_message = getattr(self._transport, "send_message", None)
        if send_message is None or not callable(send_message):
            logger.warning(
                "elicitation.transport.unavailable",
                extra={"transport_type": type(self._transport).__name__},
            )
            return
        self.elicitation_system.bind_transport(send_message)
        logger.info(
            "elicitation.transport.bound",
            extra={"transport_type": type(self._transport).__name__},
        )

    async def _route_server_initiated_response(
        self, request_id: Any, message: Dict[str, Any]
    ) -> bool:
        """Route an inbound JSON-RPC response to its originating pending request.

        Server-initiated JSON-RPC requests (elicitation/create today;
        sampling/createMessage in the future) expect a matching response
        from the client. This method inspects `self.elicitation_system._pending_requests`
        and other pending-request registries, routing the response to the
        appropriate subsystem.

        Args:
            request_id: `id` field of the inbound response.
            message: Full inbound message dict (with `result` or `error`).

        Returns:
            True when a matching pending request existed and was resolved.
            False when no pending request matched — caller should fall
            through to the regular request dispatch.
        """
        rid = str(request_id)

        # Check pending elicitation requests
        if rid in self.elicitation_system._pending_requests:
            if "error" in message:
                # Treat as cancellation with the error message as reason
                err = message.get("error", {})
                reason = (
                    err.get("message", "client error")
                    if isinstance(err, dict)
                    else "client error"
                )
                await self.elicitation_system.cancel_request(rid, reason=reason)
                return True
            result = message.get("result", {})
            # MCP 2025-06-18 ElicitResult: { action: "accept"|"decline"|"cancel", content?: {...} }
            if isinstance(result, dict):
                action = result.get("action", "accept")
                if action == "accept":
                    content = result.get("content")
                    # If no content envelope, fall back to treating the whole
                    # result as the payload (older client shape).
                    payload = content if content is not None else result
                    await self.elicitation_system.provide_input(rid, payload)
                    return True
                # decline / cancel
                await self.elicitation_system.cancel_request(
                    rid, reason=f"client action={action}"
                )
                return True
            # Non-dict result — deliver as-is
            await self.elicitation_system.provide_input(rid, result)
            return True

        return False

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
        output_schema: Optional[Dict[str, Any]] = None,
        annotations: Optional[Any] = None,
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
            output_schema: Optional JSON Schema. When set, ``tools/list`` advertises
                it as ``outputSchema`` and ``tools/call`` validates the result,
                emitting ``structuredContent`` alongside a text fallback.
            annotations: Optional :class:`ToolAnnotation` (or MCP-hint dict)
                advertised in ``tools/list``. ADVISORY ONLY — never gates access.

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
            mcp_tool = self._mcp.tool()(enhanced_func)  # type: ignore[union-attr]

            # Wire advanced/features.StructuredTool for output-schema validation.
            # Its ``output_validator`` (a SchemaValidator) is reused on every
            # tools/call to validate the result before emitting structuredContent.
            structured_tool = (
                StructuredTool(output_schema=output_schema) if output_schema else None
            )

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
                "output_schema": output_schema,
                "structured_tool": structured_tool,
                "annotations": annotations,
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
            return mcp_tool  # type: ignore[reportReturnType]

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
                        self.auth_manager.rate_limiter.check_rate_limit(  # type: ignore[reportOptionalMemberAccess]
                            user_id,
                            tool_name,
                            **rate_limit,  # type: ignore[reportCallIssue]
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
                cache = None
                cache_lookup_key = None
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
                        if self.metrics.enabled and start_time is not None:
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
                    if cache.is_redis:  # type: ignore[reportOptionalMemberAccess]
                        try:
                            # Check if we're already in an async context
                            try:
                                asyncio.get_running_loop()
                                # We're in an async context, but this is a sync function
                                # Fall back to memory cache behavior (no caching for now)
                                pass
                            except RuntimeError:
                                # Not in async context, we can use asyncio.run
                                asyncio.run(cache.aset(cache_lookup_key, result))  # type: ignore[reportOptionalMemberAccess, reportArgumentType]
                        except Exception as e:
                            logger.debug(f"Redis cache set error in sync context: {e}")
                    else:
                        cache.set(cache_lookup_key, result)  # type: ignore[reportOptionalMemberAccess, reportArgumentType]
                    logger.debug(f"Cached result for {tool_name}")

                # Track success metrics
                if self.metrics.enabled and start_time is not None:
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
                            # Async dispatch context (WebSocket): use the
                            # async-aware path so an async auth_provider (e.g.
                            # ResourceServer, whose authenticate() is a
                            # coroutine) is actually awaited. The sync path
                            # would leave the coroutine un-awaited and crash
                            # with an AttributeError -> 500 instead of a clean
                            # fail-closed AuthorizationError. Sync providers
                            # work unchanged through this path.
                            user_info = await self.auth_manager.authenticate_and_authorize_async(
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
                        self.auth_manager.rate_limiter.check_rate_limit(  # type: ignore[reportOptionalMemberAccess]
                            user_id,
                            tool_name,
                            **rate_limit,  # type: ignore[reportCallIssue]
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
                if self.metrics.enabled and start_time is not None:
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
            return async_wrapper  # type: ignore[return-value]
        else:
            return sync_wrapper  # type: ignore[return-value]

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

    def resource(self, uri: str, mime_type: str = "text/plain"):
        """
        Add resource with metrics tracking.

        Args:
            uri: Resource URI pattern
            mime_type: MIME type of the resource content. A non-text type (or a
                handler returning raw bytes) causes resources/read to emit a
                base64 ``blob`` rather than a ``text`` field (spec 2025-11-25).

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
            mcp_resource = self._mcp.resource(uri)(wrapped_func)  # type: ignore[reportOptionalMemberAccess]

            # Track in registry
            self._resource_registry[uri] = {
                "handler": mcp_resource,
                "original_handler": func,
                "name": uri,
                "description": func.__doc__ or f"Resource: {uri}",
                "mime_type": mime_type,
                "created_at": time.time(),
            }

            return mcp_resource  # type: ignore[return-value]

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
            mcp_prompt = self._mcp.prompt(name)(wrapped_func)  # type: ignore[reportOptionalMemberAccess]

            # Track in registry
            self._prompt_registry[name] = {
                "handler": mcp_prompt,
                "original_handler": func,
                "description": func.__doc__ or f"Prompt: {name}",
                "arguments": [],  # Could be extracted from function signature
                "created_at": time.time(),
            }

            return mcp_prompt  # type: ignore[return-value]

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
                self._mcp.run()  # type: ignore[reportOptionalMemberAccess]

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
        from kailash_mcp.transports.transports import WebSocketServerTransport

        try:
            # Create WebSocket transport
            self._transport = WebSocketServerTransport(
                host=self.websocket_host,
                port=self.websocket_port,
                message_handler=self._handle_websocket_message,  # type: ignore[reportArgumentType]
                disconnect_handler=self._on_ws_disconnect,
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

            # Bind the transport's send-callable to the elicitation system
            # so tools that call `server.elicitation_system.request_input(...)`
            # can actually dispatch elicitation/create requests through the
            # active client transport.
            self._bind_elicitation_transport()

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

    # Cap on the per-session request-id reuse-tracking set. Bounds memory so a
    # client streaming unique ids cannot grow the set without limit; reuse is
    # still detected within this most-recent-N window.
    _MAX_SEEN_REQUEST_IDS = 4096

    def _mark_request_id_seen(self, client_id: str, request_id: Any) -> bool:
        """Record ``request_id`` for ``client_id`` and report prior use.

        Returns True if the id was ALREADY used in this session (the caller
        rejects it as an Invalid Request). Otherwise records it — bounded to
        ``_MAX_SEEN_REQUEST_IDS`` via FIFO eviction — and returns False.
        Non-hashable ids (a JSON array id) cannot be set members and pass
        through untracked (return False) rather than erroring.
        """
        try:
            hash(request_id)
        except TypeError:
            return False
        seen = self._session_seen_ids.setdefault(client_id, set())
        if request_id in seen:
            return True
        order = self._session_seen_order.setdefault(client_id, deque())
        seen.add(request_id)
        order.append(request_id)
        if len(order) > self._MAX_SEEN_REQUEST_IDS:
            evicted = order.popleft()
            seen.discard(evicted)
        return False

    def _on_ws_disconnect(self, client_id: str) -> None:
        """Release all per-connection server state when a client disconnects.

        Wired as the WebSocket transport's disconnect handler. Without this the
        server-side maps (`_session_seen_ids` / `_session_seen_order` /
        `client_info`) grow one entry per connection forever — a remote OOM
        vector on a public server, since the transport only clears its OWN
        client maps on disconnect.
        """
        self._session_seen_ids.pop(client_id, None)
        self._session_seen_order.pop(client_id, None)
        self.client_info.pop(client_id, None)

    async def _handle_websocket_message(
        self, request: Dict[str, Any], client_id: str
    ) -> Optional[Dict[str, Any]]:
        """Handle incoming WebSocket message with decompression support.

        Returns ``None`` as a no-send sentinel (notification / ping-as-
        notification / already-routed response); the transport skips the send.
        Mirrors ``kailash.trust.mcp.server`` lifecycle handling:

        * A NOTIFICATION (absent ``id``) runs its handler for side effects and
          sends NOTHING — never a ``-32601`` body.
        * ``ping`` returns an empty ``{}`` result (base-protocol utility).
        * A request whose ``id`` was already used in this session is rejected
          with an Invalid Request error (ids MUST be unique per session).
        """
        try:
            # Decompress message if needed
            decompressed_request = self._decompress_message(request)

            method = decompressed_request.get("method", "")
            params = decompressed_request.get("params", {})
            request_id = decompressed_request.get("id")

            # Log request
            logger.debug(f"WebSocket request from {client_id}: {method}")

            # Route inbound JSON-RPC responses (no `method` field, have `id`
            # and either `result` or `error`) to any pending server-initiated
            # request. This covers elicitation/create responses per MCP
            # 2025-06-18 and is the production call site required by
            # rules/orphan-detection.md §1 for ElicitationSystem.
            if (
                not method
                and request_id is not None
                and (
                    "result" in decompressed_request or "error" in decompressed_request
                )
            ):
                handled = await self._route_server_initiated_response(
                    request_id, decompressed_request
                )
                if handled:
                    # Response routed to originating pending request; no
                    # further handler response needed (this is the client
                    # replying to US, not a client-initiated request).
                    return None

            # ``ping`` (base-protocol utility): a request-form ping gets an
            # empty result; a notification-form ping (no id) sends nothing.
            if method == "ping":
                if request_id is None:
                    return None
                return {"jsonrpc": "2.0", "result": {}, "id": request_id}

            # NOTIFICATION (absent id): run the handler for its side effects and
            # send NOTHING — never a -32601 body, even for an unknown method.
            if request_id is None:
                if method:
                    try:
                        await self._dispatch_ws_method(method, params, None, client_id)
                    except Exception as exc:  # notifications expect no response
                        logger.warning(
                            "ws.notification.error method=%s error=%s", method, exc
                        )
                return None

            # Per-session request-id reuse: an id already used in this session
            # is an Invalid Request (spec 2025-11-25). Tracking is bounded (see
            # _mark_request_id_seen); non-hashable ids pass through untracked.
            if self._mark_request_id_seen(client_id, request_id):
                return {
                    "jsonrpc": "2.0",
                    "error": {
                        "code": -32600,
                        "message": (
                            f"Request id already used in this session: {request_id!r}"
                        ),
                    },
                    "id": request_id,
                }

            return await self._dispatch_ws_method(method, params, request_id, client_id)

        except Exception as e:
            logger.error(f"Error handling WebSocket message: {e}")
            # A notification (absent id) never receives a response, even on
            # internal error.
            if request.get("id") is None:
                return None
            return {
                "jsonrpc": "2.0",
                "error": {"code": -32603, "message": f"Internal error: {str(e)}"},
                "id": request.get("id"),
            }

    async def _dispatch_ws_method(
        self,
        method: str,
        params: Dict[str, Any],
        request_id: Any,
        client_id: str,
    ) -> Dict[str, Any]:
        """Route a WebSocket JSON-RPC method to its handler."""
        if method == "initialize":
            return await self._handle_initialize(params, request_id, client_id)
        elif method == "tools/list":
            return await self._handle_list_tools(params, request_id)
        elif method == "tools/call":
            return await self._handle_call_tool(params, request_id)
        elif method == "resources/list":
            return await self._handle_list_resources(params, request_id)
        elif method == "resources/templates/list":
            return await self._handle_list_resource_templates(params, request_id)
        elif method == "resources/read":
            return await self._handle_read_resource(params, request_id, client_id)
        elif method == "resources/subscribe":
            return await self._handle_subscribe(params, request_id, client_id)
        elif method == "resources/unsubscribe":
            return await self._handle_unsubscribe(params, request_id, client_id)
        elif method == "resources/batch_subscribe":
            return await self._handle_batch_subscribe(params, request_id, client_id)
        elif method == "resources/batch_unsubscribe":
            return await self._handle_batch_unsubscribe(params, request_id, client_id)
        elif method == "prompts/list":
            return await self._handle_list_prompts(params, request_id)
        elif method == "prompts/get":
            return await self._handle_get_prompt(params, request_id)
        elif method == "logging/setLevel":
            # Merge client_id so the level is tracked per-session for
            # notifications/message gating (spec 2025-11-25).
            params_with_client = {**params, "client_id": client_id}
            return await self._handle_logging_set_level(params_with_client, request_id)
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

    async def _handle_initialize(
        self,
        params: Dict[str, Any],
        request_id: Any,
        client_id: str = None,  # type: ignore[reportArgumentType]
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
                "protocolVersion": negotiate_protocol_version(
                    params.get("protocolVersion")
                ),
                "capabilities": {
                    "tools": {"listSupported": True, "callSupported": True},
                    "resources": {
                        "listSupported": True,
                        "readSupported": True,
                        "subscribe": self.enable_subscriptions,
                        "listChanged": self.enable_subscriptions,
                        "batch_subscribe": self.enable_subscriptions,
                        "batch_unsubscribe": self.enable_subscriptions,
                        # resources/templates/list is served (spec 2025-11-25).
                        "resourceTemplates": {"listSupported": True},
                    },
                    "prompts": {"listSupported": True, "getSupported": True},
                    "logging": {"setLevel": True},
                    "roots": {"list": True},
                    # Spec-2025-11-25 top-level completions capability. The
                    # experimental.completion alias below is retained for
                    # backward compatibility with older clients.
                    "completions": {},
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
                tool_desc: Dict[str, Any] = {
                    "name": name,
                    "description": info.get("description", ""),
                    "inputSchema": info.get("input_schema", {}),
                }
                # Advertise outputSchema when the tool declared one so clients
                # can validate structuredContent (spec 2025-11-25).
                output_schema = info.get("output_schema")
                if output_schema:
                    tool_desc["outputSchema"] = output_schema
                # Tool annotations (readOnlyHint / destructiveHint / …) are
                # ADVISORY metadata for client UX. INVARIANT: they MUST NEVER
                # gate authorization — access control is enforced solely by the
                # auth/permission manager (see _create_enhanced_tool), never by
                # these client-supplied-trust hints. Do not read them in any
                # dispatch/authorization path.
                mcp_annotations = _annotations_to_mcp(info.get("annotations"))
                if mcp_annotations:
                    tool_desc["annotations"] = mcp_annotations
                tools.append(tool_desc)

        page, next_cursor, error = self._paginate(
            tools, params.get("cursor"), request_id
        )
        if error is not None:
            return error
        result: Dict[str, Any] = {"tools": page}
        if next_cursor:
            result["nextCursor"] = next_cursor
        return {"jsonrpc": "2.0", "result": result, "id": request_id}

    def _paginate(
        self, all_items: List[Any], cursor: Any, request_id: Any
    ) -> "tuple[Optional[List[Any]], Optional[str], Optional[Dict[str, Any]]]":
        """Server-chosen opaque-cursor pagination (spec 2025-11-25).

        Returns ``(page, next_cursor, error)``. ``error`` is a ``-32602``
        JSON-RPC envelope when ``cursor`` is present but invalid/expired (clients
        treat cursors as opaque); otherwise ``None`` and ``page`` carries this
        page's items. The server picks the page size (``_DEFAULT_PAGE_SIZE``) —
        a client does NOT need to send a ``limit`` to receive a ``nextCursor``.
        """
        start = 0
        if cursor is not None:
            # A cursor is an OPAQUE STRING (spec 2025-11-25). A non-string
            # cursor (int, list, dict, ...) is a malformed param — return the
            # -32602 envelope rather than letting an unhashable/typed value
            # raise an unhandled TypeError deep in the cursor manager. Mirrors
            # the invalid-string-cursor branch below.
            if not isinstance(cursor, str):
                return (
                    None,
                    None,
                    {
                        "jsonrpc": "2.0",
                        "error": {
                            "code": -32602,
                            "message": "Invalid or expired cursor",
                        },
                        "id": request_id,
                    },
                )
            if not self._cursor_manager.is_valid(cursor):
                return (
                    None,
                    None,
                    {
                        "jsonrpc": "2.0",
                        "error": {
                            "code": -32602,
                            "message": "Invalid or expired cursor",
                        },
                        "id": request_id,
                    },
                )
            start = self._cursor_manager.get_cursor_position(cursor) or 0

        end = start + _DEFAULT_PAGE_SIZE
        page = all_items[start:end]
        next_cursor = None
        if end < len(all_items):
            next_cursor = self._cursor_manager.create_cursor_for_position(
                all_items, end
            )
        return page, next_cursor, None

    async def _handle_call_tool(
        self, params: Dict[str, Any], request_id: Any
    ) -> Dict[str, Any]:
        """Handle tools/call request.

        Spec 2025-11-25 distinguishes two error classes:

        * PROTOCOL errors (missing/invalid tool name, unknown tool, malformed
          ``arguments`` shape) -> JSON-RPC error object (``-32602``).
        * TOOL EXECUTION failures (the tool body raised) -> a normal result
          with ``isError: true`` and the error text carried in ``content``,
          so the calling LLM can observe and react to the failure. Mirrors
          ``kailash.trust.mcp.server`` isError handling.
        """
        tool_name = params.get("name")
        arguments = params.get("arguments", {})

        # --- PROTOCOL validation -> JSON-RPC errors -------------------------
        if not tool_name or not isinstance(tool_name, str):
            return self._jsonrpc_error(
                request_id,
                MCPErrorCode.INVALID_PARAMS,
                "Missing or invalid tool name in tools/call params",
            )
        if tool_name not in self._tool_registry or self._tool_registry[tool_name].get(
            "disabled", False
        ):
            return self._jsonrpc_error(
                request_id,
                MCPErrorCode.INVALID_PARAMS,
                f"Unknown tool: {tool_name}",
            )
        if not isinstance(arguments, dict):
            return self._jsonrpc_error(
                request_id,
                MCPErrorCode.INVALID_PARAMS,
                "arguments must be an object",
            )

        tool_info = self._tool_registry[tool_name]

        # --- EXECUTION failure -> isError-in-result -------------------------
        try:
            result = self._execute_tool(tool_name, arguments)
            if asyncio.iscoroutine(result) or asyncio.isfuture(result):
                result = await result
        except Exception as e:  # tool body raised -> report as tool result
            logger.warning("tool.call.error tool=%s error=%s", tool_name, e)
            return {
                "jsonrpc": "2.0",
                "result": {
                    "content": [
                        {"type": "text", "text": f"Tool execution error: {str(e)}"}
                    ],
                    "isError": True,
                },
                "id": request_id,
            }

        # --- Shape the successful result ------------------------------------
        content, is_error, structured = self._build_tool_result(result, tool_info)
        result_obj: Dict[str, Any] = {"content": content}
        if structured is not None:
            result_obj["structuredContent"] = structured
        if is_error:
            result_obj["isError"] = True
        return {"jsonrpc": "2.0", "result": result_obj, "id": request_id}

    def _jsonrpc_error(
        self, request_id: Any, code: Any, message: str
    ) -> Dict[str, Any]:
        """Build a JSON-RPC error envelope (PROTOCOL failures only)."""
        code_value = code.value if isinstance(code, MCPErrorCode) else code
        return {
            "jsonrpc": "2.0",
            "error": {"code": code_value, "message": message},
            "id": request_id,
        }

    def _build_tool_result(
        self, result: Any, tool_info: Dict[str, Any]
    ) -> "tuple[List[Dict[str, Any]], bool, Optional[Any]]":
        """Normalise a tool return value into ``(content, is_error, structured)``.

        * ``ToolResult`` (protocol.protocol) -> its ``content`` + ``isError``,
          wiring ``ToolResult.image()`` / ``.resource()`` passthrough.
        * A content-block list, or a single content-block dict (text / image /
          audio / resource / resource_link) -> passed through verbatim.
        * A tool with a registered ``outputSchema`` -> validate; on success emit
          ``structuredContent`` + a text fallback, on failure isError-in-result.
        * Any other scalar / string / dict -> a single ``text`` block.
        """
        # 1. ToolResult passthrough (image / resource / explicit isError).
        if isinstance(result, ToolResult):
            payload = result.to_dict()
            return payload["content"], bool(payload.get("isError", False)), None

        # 2. A pre-built content-block list -> passthrough.
        if (
            isinstance(result, list)
            and result
            and all(
                isinstance(item, dict) and item.get("type") in _CONTENT_BLOCK_TYPES
                for item in result
            )
        ):
            return result, False, None

        # 3. A single content-block dict -> wrap in a list, passthrough.
        if isinstance(result, dict) and result.get("type") in _CONTENT_BLOCK_TYPES:
            return [result], False, None

        # 4. Output-schema validation via StructuredTool.output_validator.
        structured_tool = tool_info.get("structured_tool")
        if structured_tool is not None and structured_tool.output_validator is not None:
            try:
                structured_tool.output_validator.validate(result)
            except ValidationError as e:  # validation failure -> isError result
                return (
                    [
                        {
                            "type": "text",
                            "text": f"Output validation failed: {str(e)}",
                        }
                    ],
                    True,
                    None,
                )
            text_fallback = json.dumps(result, default=str)
            return [{"type": "text", "text": text_fallback}], False, result

        # 5. Plain scalar / string / unstructured dict -> text block.
        return [{"type": "text", "text": str(result)}], False, None

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
                    result["nextCursor"] = next_cursor  # type: ignore[reportArgumentType]

                return {"jsonrpc": "2.0", "result": result, "id": request_id}
            else:
                resources = all_resources[start_pos:]
        else:
            # No pagination support
            resources = all_resources

        return {"jsonrpc": "2.0", "result": {"resources": resources}, "id": request_id}

    async def _handle_read_resource(
        self,
        params: Dict[str, Any],
        request_id: Any,
        client_id: str = None,  # type: ignore[reportArgumentType]
    ) -> Dict[str, Any]:
        """Handle resources/read request with change detection.

        Spec 2025-11-25 resources/read fidelity:

        * The ``uri`` param is RFC-3986 validated (scheme + no whitespace)
          BEFORE registry lookup; a malformed URI is a distinct ``-32602``
          "invalid URI" (not a generic not-found).
        * Binary content (raw bytes, or a non-text ``mimeType``) is
          base64-encoded into a ``blob`` — never str()-corrupted into ``text``.
          ``text`` and ``blob`` are mutually exclusive per content item.
        * The registered/derived ``mimeType`` is echoed on returned contents.
        """
        uri = params.get("uri")

        # RFC 3986 validation FIRST — a malformed URI is a distinct -32602,
        # not a generic not-found (which would mask the real client error).
        if not self._is_valid_resource_uri(uri):
            return {
                "jsonrpc": "2.0",
                "error": {"code": -32602, "message": f"Invalid URI: {uri!r}"},
                "id": request_id,
            }

        # First try exact match
        resource_info = None
        resource_params = {}
        if uri in self._resource_registry:
            resource_info = self._resource_registry[uri]  # type: ignore[reportArgumentType]
        else:
            # Try template matching
            resource_info, resource_params = self._match_resource_template(uri)  # type: ignore[reportArgumentType]

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

            mime_type = resource_info.get("mime_type", "text/plain")

            # Process change detection if subscription manager is available
            if self.subscription_manager:
                resource_data = {
                    "uri": uri,
                    "text": str(content),
                    "mimeType": mime_type,
                }

                # Check for changes and notify subscribers
                change = (
                    await self.subscription_manager.resource_monitor.check_for_changes(
                        uri,
                        resource_data,  # type: ignore[reportArgumentType]
                    )
                )

                if change:
                    await self.subscription_manager.process_resource_change(change)

            content_item = self._build_resource_content(uri, content, mime_type)
            return {
                "jsonrpc": "2.0",
                "result": {"contents": [content_item]},
                "id": request_id,
            }
        except Exception as e:
            return {
                "jsonrpc": "2.0",
                "error": {"code": -32603, "message": f"Resource read error: {str(e)}"},
                "id": request_id,
            }

    @staticmethod
    def _is_valid_resource_uri(uri: Any) -> bool:
        """RFC-3986 validate a resources/read ``uri`` param.

        Requires a non-empty string carrying a scheme and no whitespace /
        control characters. A malformed URI is rejected here so it can be
        reported as a distinct ``-32602`` before registry lookup.
        """
        if not uri or not isinstance(uri, str):
            return False
        if any(ch.isspace() or ord(ch) < 0x20 for ch in uri):
            return False
        try:
            parsed = urlparse(uri)
        except (ValueError, TypeError):
            return False
        return bool(parsed.scheme)

    def _build_resource_content(
        self, uri: str, content: Any, mime_type: str
    ) -> Dict[str, Any]:
        """Build a single resources/read content item.

        Binary content (raw bytes, or a non-text ``mimeType``) is base64
        ``blob``-encoded (mirroring advanced/features.BinaryResourceHandler);
        text content is emitted as ``text``. ``text`` and ``blob`` are mutually
        exclusive per item; ``mimeType`` is always echoed.
        """
        is_binary = isinstance(content, (bytes, bytearray)) or not _is_text_mime(
            mime_type
        )
        if is_binary:
            if isinstance(content, (bytes, bytearray)):
                raw = bytes(content)
            else:
                raw = str(content).encode("utf-8")
            blob = base64.b64encode(raw).decode("ascii")
            return {"uri": uri, "mimeType": mime_type, "blob": blob}
        return {"uri": uri, "mimeType": mime_type, "text": str(content)}

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
        """Handle prompts/list request with cursor-based pagination."""
        prompts = []
        for name, info in self._prompt_registry.items():
            prompts.append(
                {
                    "name": name,
                    "description": info.get("description", ""),
                    "arguments": info.get("arguments", []),
                }
            )

        page, next_cursor, error = self._paginate(
            prompts, params.get("cursor"), request_id
        )
        if error is not None:
            return error
        result: Dict[str, Any] = {"prompts": page}
        if next_cursor:
            result["nextCursor"] = next_cursor
        return {"jsonrpc": "2.0", "result": result, "id": request_id}

    async def _handle_list_resource_templates(
        self, params: Dict[str, Any], request_id: Any
    ) -> Dict[str, Any]:
        """Handle resources/templates/list with cursor-based pagination.

        A registered resource whose URI carries a ``{placeholder}`` is a
        template (the shape ``_match_resource_template`` expands); it is
        advertised here via its ``uriTemplate`` (spec 2025-11-25). Concrete
        (placeholder-free) resources stay in resources/list. Pagination reuses
        the shared opaque-cursor scheme — an invalid cursor -> ``-32602``.
        """
        templates = []
        for uri, info in self._resource_registry.items():
            if "{" in uri and "}" in uri:
                templates.append(
                    {
                        "uriTemplate": uri,
                        "name": info.get("name", uri),
                        "description": info.get("description", ""),
                        "mimeType": info.get("mime_type", "text/plain"),
                    }
                )

        page, next_cursor, error = self._paginate(
            templates, params.get("cursor"), request_id
        )
        if error is not None:
            return error
        result: Dict[str, Any] = {"resourceTemplates": page}
        if next_cursor:
            result["nextCursor"] = next_cursor
        return {"jsonrpc": "2.0", "result": result, "id": request_id}

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
            prompt_info = self._prompt_registry[name]  # type: ignore[reportArgumentType]
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

                await self._transport.send_message(message_to_send, client_id=client_id)  # type: ignore[reportArgumentType]
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
        valid_levels = list(_MCP_LOG_LEVELS)
        if level not in valid_levels:
            return {
                "jsonrpc": "2.0",
                "error": {
                    "code": -32602,
                    "message": f"Invalid log level: {level}. Must be one of {valid_levels}",
                },
                "id": request_id,
            }

        # Record the per-session minimum level so notifications/message emission
        # is gated per client (spec 2025-11-25); a message below this level is
        # suppressed for this client. Absent a real client_id, update the
        # server-wide default.
        client_id = params.get("client_id")
        if client_id and client_id != "unknown":
            self._client_log_levels[client_id] = level
        else:
            self._log_level_default = level

        # Set the process log level too (existing behaviour).
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

    async def send_log_message(
        self,
        level: str,
        data: Any,
        *,
        logger_name: Optional[str] = None,
        client_id: Optional[str] = None,
    ) -> int:
        """Emit an MCP ``notifications/message`` to connected clients.

        The server-to-client logging path required by spec 2025-11-25:
        ``logging/setLevel`` only sets a level; THIS is how the server actually
        pushes a log record. Emission is GATED by the per-client minimum level
        set via ``logging/setLevel`` (falling back to ``_log_level_default``) —
        a message BELOW a client's level is suppressed for that client. The
        ``data`` payload is scrubbed of secrets/PII (``_redact_log_data``,
        security.md) before send.

        Args:
            level: severity (one of ``_MCP_LOG_LEVELS``); case-insensitive.
            data: the log payload (dict/str/scalar); redacted before send.
            logger_name: optional ``logger`` field on the notification.
            client_id: when given, target ONLY that client (still level-gated);
                otherwise every initialized client.

        Returns:
            The number of clients the notification was actually sent to.
        """
        norm = str(level).upper()
        msg_rank = _MCP_LOG_LEVEL_RANK.get(norm)
        if msg_rank is None:
            raise ValueError(
                f"Invalid log level: {level}. Must be one of {list(_MCP_LOG_LEVELS)}"
            )

        params: Dict[str, Any] = {"level": norm, "data": _redact_log_data(data)}
        if logger_name is not None:
            params["logger"] = logger_name
        notification = {
            "jsonrpc": "2.0",
            "method": "notifications/message",
            "params": params,
        }

        if client_id is not None:
            targets = [client_id]
        else:
            targets = list(self.client_info.keys())

        sent = 0
        for target in targets:
            effective = self._client_log_levels.get(target, self._log_level_default)
            # Suppress messages below this client's configured minimum level.
            if msg_rank < _MCP_LOG_LEVEL_RANK.get(effective, 0):
                continue
            await self._send_websocket_notification(target, notification)
            sent += 1
        return sent

    async def _handle_roots_list(
        self, params: Dict[str, Any], request_id: Any
    ) -> Dict[str, Any]:
        """Handle roots/list request to get file system access roots."""
        protocol_mgr = get_protocol_manager()

        # Check if client supports roots
        client_info = self.client_info.get(params.get("client_id", ""))
        if (
            not client_info.get("capabilities", {})  # type: ignore[reportOptionalMemberAccess]
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
                    user_context=self.client_info.get(params["client_id"], {}),  # type: ignore[reportCallIssue]
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
            # Collect (match_key, value) so candidates can be relevance-ranked
            # BEFORE the 100-item cap, so the cap keeps the TOP matches rather
            # than an arbitrary registry-order slice (spec 2025-11-25).
            collected: List["tuple[str, Dict[str, Any]]"] = []

            if ref_type == "resource":
                # Search through registered resources
                for uri, resource_info in self._resource_registry.items():
                    if partial_value in uri:  # substring candidate
                        collected.append(
                            (
                                uri,
                                {
                                    "uri": uri,
                                    "name": resource_info.get("name", uri),
                                    "description": resource_info.get("description", ""),
                                },
                            )
                        )

            elif ref_type == "prompt":
                # Search through registered prompts
                for name, prompt_info in self._prompt_registry.items():
                    if partial_value in name:  # substring candidate
                        collected.append(
                            (
                                name,
                                {
                                    "name": name,
                                    "description": prompt_info.get("description", ""),
                                    "arguments": prompt_info.get("arguments", []),
                                },
                            )
                        )

            elif ref_type == "tool":
                # Search through registered tools
                for name, tool_info in self._tool_registry.items():
                    if partial_value in name:
                        collected.append(
                            (
                                name,
                                {
                                    "name": name,
                                    "description": tool_info.get("description", ""),
                                    "inputSchema": tool_info.get("inputSchema", {}),
                                },
                            )
                        )

            # Relevance-rank: exact match first, then prefix, then substring
            # (stable within a rank). Ranking precedes the cap so the top-100
            # are the most relevant candidates, not a registry-order prefix.
            collected.sort(key=lambda pair: _completion_rank(pair[0], partial_value))

            # Limit to 100 items and add hasMore flag if needed
            total_matches = len(collected)
            has_more = total_matches > 100
            values = [value for _, value in collected[:100]]

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

    def __init__(self, name: str, description: str = None):  # type: ignore[reportArgumentType]
        """Initialize simple MCP server.

        Args:
            name: Server name
            description: Server description
        """
        super().__init__(name, description)  # type: ignore[reportArgumentType]

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

    def tool(self, description: str = None):  # type: ignore[reportArgumentType]
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

    def resource(self, uri: str, description: str = None):  # type: ignore[reportArgumentType]
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

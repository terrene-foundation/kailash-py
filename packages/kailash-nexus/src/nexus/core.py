"""Core implementation of zero-configuration Nexus.

This module provides the main Nexus class for workflow orchestration
that implements true zero-configuration workflow orchestration.
"""

import asyncio
import json
import logging
import os
import threading
import warnings
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import (
    Any,
    Callable,
    Dict,
    List,
    Optional,
    Protocol,
    Tuple,
    runtime_checkable,
)

from kailash.runtime import AsyncLocalRuntime
from kailash.servers.gateway import create_gateway
from kailash.workflow import Workflow
from kailash.workflow.builder import WorkflowBuilder
from nexus.background import BackgroundService
from nexus.events import EventBus, NexusEvent, NexusEventType
from nexus.registry import HandlerDef, HandlerParam, HandlerRegistry
from nexus.transports.base import Transport
from nexus.transports.http import HTTPTransport
from nexus.transports.mcp import MCPTransport

# Import from SDK - remove path manipulation since we're a separate package


# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class NexusConfig:
    """Configuration object for Nexus components."""

    def __init__(self):
        self.strategy = None
        self.interval = 30
        self.cors_enabled = True
        self.docs_enabled = True


@dataclass
class MiddlewareInfo:
    """Information about registered middleware."""

    middleware_class: type
    kwargs: Dict[str, Any]
    added_at: datetime

    @property
    def name(self) -> str:
        """Return the middleware class name."""
        return self.middleware_class.__name__


@dataclass
class RouterInfo:
    """Information about included routers."""

    router: Any  # APIRouter - forward ref to avoid import at module level
    prefix: str
    tags: List[str]
    added_at: datetime

    @property
    def routes(self) -> List[str]:
        """Get all route paths in this router."""
        return [route.path for route in self.router.routes]


@dataclass
class MountInfo:
    """Information about a mounted sub-application.

    Records a sub-application mounted at a path prefix. The subapp may be
    another ``Nexus`` instance (composition) or any ASGI-compatible app
    (e.g., FastAPI, Starlette).

    Attributes:
        path: URL prefix where the subapp is mounted (e.g. ``/api/v2``).
        subapp: The mounted application (``Nexus`` or ASGI app).
        name: Optional name (forwarded to Starlette's mount).
        added_at: Timestamp when the mount was registered.
    """

    path: str
    subapp: Any
    name: Optional[str]
    added_at: datetime


@runtime_checkable
class NexusPluginProtocol(Protocol):
    """Protocol for Nexus plugins.

    Plugins provide a composable way to add functionality to Nexus.
    They can register middleware, routers, and respond to lifecycle events.

    Required:
        name: Unique plugin name (property).
        install(app): Called during add_plugin() to configure the plugin.

    Optional:
        on_startup(): Called when Nexus starts.
        on_shutdown(): Called when Nexus stops.
    """

    @property
    def name(self) -> str:
        """Unique plugin name."""
        ...

    def install(self, app: "Nexus") -> None:
        """Install the plugin into a Nexus application."""
        ...


class Nexus:
    """Zero-configuration workflow orchestration platform.

    Like FastAPI, provides a clear instance with optional enterprise features
    configurable at construction time or via attributes.
    """

    def __init__(
        self,
        api_port: int = 8000,
        mcp_port: int = 3001,
        enable_auth: Optional[bool] = None,
        enable_monitoring: bool = False,
        rate_limit: Optional[int] = 100,
        auto_discovery: bool = False,
        enable_http_transport: bool = False,
        enable_sse_transport: bool = False,
        enable_discovery: bool = False,
        rate_limit_config: Optional[Dict[str, Any]] = None,
        enable_durability: bool = True,  # Disable for testing to prevent caching issues
        # Gateway configuration
        server_type: str = "enterprise",  # "enterprise", "durable", "basic"
        max_workers: Optional[int] = None,  # None = auto-detect
        # Preset System
        preset: Optional[str] = None,
        # CORS Configuration
        cors_origins: Optional[List[str]] = None,
        cors_allow_methods: Optional[List[str]] = None,
        cors_allow_headers: Optional[List[str]] = None,
        cors_allow_credentials: bool = False,
        cors_expose_headers: Optional[List[str]] = None,
        cors_max_age: int = 600,
        # Shared runtime injection (M3-001)
        runtime=None,
    ):
        """Initialize Nexus with optional enterprise features.

        Args:
            api_port: Port for API server (default: 8000)
            mcp_port: Port for MCP server (default: 3001)
            enable_auth: Enable authentication (default: False in dev, required in production)
            enable_monitoring: Enable monitoring (default: False)
            rate_limit: Requests per minute limit (default: 100, set None to disable)
            auto_discovery: Auto-discover workflows (default: False, prevents blocking)
            enable_http_transport: Enable HTTP transport for MCP (default: False)
            enable_sse_transport: Enable SSE transport for MCP (default: False)
            enable_discovery: Enable MCP service discovery (default: False)
            rate_limit_config: Advanced rate limiting configuration (default: None)
            enable_durability: Enable durability/caching (default: True, set False for tests)
            server_type: Gateway server type. "enterprise" (full features),
                "durable" (checkpointing only), or "basic" (minimal). Override
                via NEXUS_SERVER_TYPE env var.
            max_workers: Maximum thread pool workers for the gateway. None = auto-detect
                (min(4, cpu_count)). Override via NEXUS_MAX_WORKERS env var.
            cors_origins: Allowed origins for CORS. Defaults to ["*"] in development,
                must be explicitly set in production.
            cors_allow_methods: Allowed HTTP methods. Defaults to ["*"].
            cors_allow_headers: Allowed request headers. Defaults to ["*"].
            cors_allow_credentials: Allow cookies/auth headers. Defaults to False.
                Set to True only with explicit origins (not wildcard).
            cors_expose_headers: Headers exposed to browser. Defaults to None.
            cors_max_age: Preflight cache duration in seconds. Defaults to 600.
            runtime: Optional shared AsyncLocalRuntime. If provided, the Nexus
                instance acquires a reference (caller retains ownership). If None,
                Nexus creates and owns its own runtime.

        Security Notes:
            - rate_limit defaults to 100 req/min to prevent DoS attacks
            - auto_discovery defaults to False to prevent blocking and security risks
            - Set NEXUS_ENV=production to enforce authentication requirements
        """
        # Configuration
        self._api_port = api_port
        self._mcp_port = mcp_port
        self._auto_discovery_enabled = auto_discovery
        self._enable_http_transport = enable_http_transport
        self._enable_sse_transport = enable_sse_transport
        self._enable_discovery = enable_discovery
        self._enable_durability = enable_durability
        self._server_type = os.getenv("NEXUS_SERVER_TYPE", server_type)
        _valid_server_types = {"enterprise", "durable", "basic"}
        if self._server_type not in _valid_server_types:
            raise ValueError(
                f"Invalid server_type '{self._server_type}'. "
                f"Must be one of: {sorted(_valid_server_types)}"
            )
        if "NEXUS_MAX_WORKERS" in os.environ:
            try:
                self._max_workers = int(os.environ["NEXUS_MAX_WORKERS"])
            except ValueError:
                raise ValueError(
                    f"NEXUS_MAX_WORKERS must be a positive integer, "
                    f"got '{os.environ['NEXUS_MAX_WORKERS']}'"
                )
        else:
            self._max_workers = max_workers
        if self._max_workers is not None and self._max_workers < 1:
            raise ValueError(f"max_workers must be >= 1, got {self._max_workers}")
        self.rate_limit_config = rate_limit_config or {}
        self.name = "nexus"  # Platform name for MCP server

        # P0-5: Input validation configuration
        self._max_input_size = 10 * 1024 * 1024  # 10MB default

        # P0-1: Environment-aware authentication (SECURITY)
        nexus_env = os.getenv("NEXUS_ENV", "development").lower()

        # Auto-enable auth in production unless explicitly disabled
        if nexus_env == "production":
            if enable_auth is False:
                # Explicit override - warn but respect user choice
                logger.critical(
                    "\n" + "=" * 80 + "\n"
                    "⚠️  SECURITY WARNING: Authentication DISABLED in production environment!\n"
                    "=" * 80 + "\n"
                    "APIs are accessible to anyone on the network.\n"
                    "This was explicitly disabled with enable_auth=False.\n"
                    "=" * 80
                )
                self._enable_auth = False
            else:
                # Auto-enable in production (None or True)
                self._enable_auth = True
                if enable_auth is None:
                    logger.info(
                        "🔐 Authentication auto-enabled for production environment"
                    )
                else:
                    logger.info("✅ Authentication: ENABLED")
        else:
            # Development mode - respect parameter
            self._enable_auth = enable_auth if enable_auth is not None else False
            if self._enable_auth:
                logger.info("✅ Authentication: ENABLED (development mode)")
            else:
                logger.info("⚠️  Authentication: DISABLED (development mode)")

        self._enable_monitoring = enable_monitoring

        # P0-2: Rate limiting warning (SECURITY)
        if rate_limit is None:
            logger.warning(
                "⚠️  SECURITY WARNING: Rate limiting is DISABLED!\n"
                "   This allows unlimited requests and may lead to DoS attacks.\n"
                "   Set rate_limit=N (requests per minute) to protect your endpoints."
            )
        else:
            logger.info(f"🛡️  Rate limiting: {rate_limit} requests/minute")

        # Internal state — EventBus + HandlerRegistry centralize event/handler storage
        self._event_bus = EventBus(capacity=256)
        self._registry = HandlerRegistry(event_bus=self._event_bus)
        self._background_services: List[BackgroundService] = []
        self._transports: List[Transport] = []
        # Class-based WebSocket message-handler registry (issue #448).
        # Lazily populated by @app.websocket() decorator / app.register_websocket().
        # Attached to the WebSocket transport when it's constructed.
        from nexus.websocket_handlers import (  # noqa: E501 — local import to avoid cycle at import time
            MessageHandlerRegistry,
        )

        self._ws_message_handlers: MessageHandlerRegistry = MessageHandlerRegistry()
        self._ws_transport = None  # lazily built by _ensure_ws_transport()
        self._running = False

        # Middleware management (introspection-only — actual apply delegates to HTTPTransport)
        self._middleware_queue: List[Tuple[type, Dict[str, Any]]] = []
        self._middleware_stack: List[MiddlewareInfo] = []

        # Router management (introspection-only — actual apply delegates to HTTPTransport)
        self._router_queue: List[Tuple[Any, Dict[str, Any]]] = []
        self._routers: List[RouterInfo] = []

        # Sub-app mount management (introspection + queue for pre-gateway mounts)
        self._mount_queue: List[Tuple[str, Any, Optional[str]]] = []
        self._mounts: List[MountInfo] = []

        # Plugin management
        self._plugins: Dict[str, Any] = {}
        self._startup_hooks: List[Callable[[], None]] = []
        self._shutdown_hooks: List[Callable[[], None]] = []

        # CORS configuration
        self._cors_origins = cors_origins
        self._cors_allow_methods = cors_allow_methods
        self._cors_allow_headers = cors_allow_headers
        self._cors_allow_credentials = cors_allow_credentials
        self._cors_expose_headers = cors_expose_headers
        self._cors_max_age = cors_max_age
        self._cors_middleware_applied = False

        # Validate CORS origins (production rejects wildcard)
        if cors_origins is not None:
            self._validate_cors_origins(cors_origins)

        # Preset system
        self._active_preset = preset
        self._nexus_config = None  # Built lazily when preset is applied

        # Configuration objects for fine-tuning
        self.auth = NexusConfig()
        self.monitoring = NexusConfig()
        self.api = NexusConfig()
        self.mcp = NexusConfig()

        # Apply enterprise options (store rate_limit for endpoint decorator)
        self._rate_limit = rate_limit
        if enable_auth:
            self._auth_enabled = True
        if enable_monitoring:
            self._monitoring_enabled = True

        # Create HTTPTransport (wraps the enterprise gateway)
        self._http_transport = HTTPTransport(
            port=api_port,
            cors_origins=cors_origins,
            cors_allow_methods=cors_allow_methods,
            cors_allow_headers=cors_allow_headers,
            cors_allow_credentials=cors_allow_credentials,
            cors_expose_headers=cors_expose_headers,
            cors_max_age=cors_max_age,
            enable_auth=self._enable_auth,
            enable_monitoring=enable_monitoring,
            enable_durability=enable_durability,
            rate_limit=rate_limit,
        )
        self._transports.append(self._http_transport)

        # Server-level shared runtime — MUST be created BEFORE gateway so the
        # gateway can share it instead of creating its own pool (fixes #211).
        if runtime is not None:
            self.runtime = runtime.acquire()
            self._owns_runtime = False
        else:
            self.runtime = AsyncLocalRuntime()
            self._owns_runtime = True

        # Create gateway eagerly (existing behavior — needed before start()).
        # Gateway receives self.runtime to avoid creating a duplicate pool.
        self._initialize_gateway()

        # Apply preset if specified (after gateway, so middleware/plugins can be applied)
        if preset:
            from nexus.presets import NexusConfig as _PresetConfig
            from nexus.presets import apply_preset

            self._nexus_config = _PresetConfig(
                cors_origins=self._cors_origins or ["*"],
                cors_allow_methods=self._cors_allow_methods or ["*"],
                cors_allow_headers=self._cors_allow_headers or ["*"],
                cors_allow_credentials=self._cors_allow_credentials,
                environment=os.getenv("NEXUS_ENV", "development"),
            )
            apply_preset(self, preset, self._nexus_config)

        # Initialize revolutionary capabilities
        self._initialize_revolutionary_capabilities()

        # Initialize MCP server
        self._initialize_mcp_server()

        logger.info("Nexus initialized with revolutionary workflow-native architecture")

    # ------------------------------------------------------------------
    # Backward-compatible properties — delegate to HandlerRegistry
    # ------------------------------------------------------------------

    @property
    def _workflows(self) -> Dict[str, Any]:
        """Backward-compatible access to workflows dict."""
        return self._registry._workflows

    @_workflows.setter
    def _workflows(self, value: Dict[str, Any]) -> None:
        """Backward-compatible setter for workflows dict (used by tests)."""
        self._registry._workflows = value

    @property
    def _handler_registry(self) -> Dict[str, Dict[str, Any]]:
        """Backward-compatible access to handler registry dict."""
        return self._registry._handler_funcs

    @_handler_registry.setter
    def _handler_registry(self, value: Dict[str, Dict[str, Any]]) -> None:
        """Backward-compatible setter for handler registry dict (used by tests)."""
        self._registry._handler_funcs = value

    @property
    def _gateway(self):
        """Backward-compatible access to the enterprise gateway.

        .. deprecated::
            Use ``app.fastapi_app`` for the FastAPI app or
            ``app._http_transport`` for the HTTPTransport instance.
        """
        warnings.warn(
            "Nexus._gateway is deprecated. Use app.fastapi_app for the FastAPI app, "
            "or app._http_transport for the HTTPTransport instance.",
            DeprecationWarning,
            stacklevel=2,
        )
        if hasattr(self, "_http_transport"):
            return self._http_transport.gateway
        return None

    @_gateway.setter
    def _gateway(self, value):
        """Backward-compatible setter for the enterprise gateway.

        .. deprecated::
            Assign to ``app._http_transport._gateway`` instead.
        """
        if hasattr(self, "_http_transport"):
            self._http_transport._gateway = value
        # If no _http_transport yet (e.g., __new__ without __init__),
        # just silently drop the set — the real gateway lives on HTTPTransport.

    @property
    def fastapi_app(self):
        """The underlying FastAPI app (replaces _gateway.app access).

        Returns None if the gateway hasn't been created yet.
        """
        return self._http_transport.app

    # ------------------------------------------------------------------
    # Transport management
    # ------------------------------------------------------------------

    def add_transport(self, transport: Transport) -> "Nexus":
        """Register a transport for lifecycle management.

        The transport will be started with the HandlerRegistry when
        Nexus.start() is called, and stopped when Nexus.stop() is called.

        Args:
            transport: A Transport implementation.

        Returns:
            self (for chaining).
        """
        self._transports.append(transport)
        # Auto-wire class-based WebSocket message handlers (issue #448):
        # if the transport is a WebSocketTransport that has no message
        # handler registry of its own, point it at this Nexus's registry
        # so @app.websocket() decorators are visible to the transport.
        try:
            from nexus.transports.websocket import (  # local import avoids cycle
                WebSocketTransport,
            )

            if (
                isinstance(transport, WebSocketTransport)
                and transport._message_handlers is None
            ):
                transport._message_handlers = self._ws_message_handlers
                self._ws_transport = transport
        except Exception:  # noqa: BLE001 — best-effort wiring
            logger.debug("ws.transport.auto_wire_failed", exc_info=True)
        logger.info(f"Transport registered: {transport.name}")
        return self

    # ------------------------------------------------------------------
    # Class-based WebSocket message handlers (issue #448)
    # ------------------------------------------------------------------

    def websocket(self, path: str):
        """Register a class-based WebSocket message handler on ``path``.

        Use as a class decorator. The decorated class MUST subclass
        :class:`nexus.websocket_handlers.MessageHandler` and override
        the lifecycle hooks it cares about (``on_connect``,
        ``on_message``, ``on_disconnect``, ``on_event``).

        Example::

            from nexus import Nexus
            from nexus.websocket_handlers import MessageHandler

            app = Nexus()

            @app.websocket("/events")
            class EventStream(MessageHandler):
                async def on_connect(self, conn):
                    conn.state.subscriptions = set()

                async def on_message(self, conn, msg):
                    if msg.get("action") == "subscribe":
                        conn.state.subscriptions.add(msg["topic"])

                async def on_event(self, event):
                    for c in self.connections:
                        if event["topic"] in c.state.subscriptions:
                            await c.send_json(event)

        Args:
            path: URL path for the WebSocket endpoint (e.g. ``"/events"``).
                Must start with ``/``. Cannot collide with an existing
                class-based handler path.

        Returns:
            A decorator that registers the class and returns it
            unchanged so normal inheritance/introspection still works.
        """

        def _decorator(cls):
            self.register_websocket(path, cls)
            return cls

        return _decorator

    def register_websocket(self, path: str, handler_cls) -> Any:
        """Imperative form of :meth:`websocket`.

        Useful when the handler class is defined elsewhere and you
        want to register it conditionally. Returns the instantiated
        handler so the caller can wire external publishers.
        """
        return self._ws_message_handlers.register(path, handler_cls)

    async def websocket_broadcast(self, path: str, event: Any) -> None:
        """Fire ``on_event`` on the handler registered at ``path``.

        This is the canonical entry point for server-originated
        fanout — call it from a DataFlow change stream, a message
        queue consumer, or any other publisher.

        Raises:
            KeyError: if no class-based handler is registered at
                ``path``.
        """
        await self._ws_message_handlers.broadcast_event(path, event)

    @property
    def websocket_handlers(self):
        """Read-only access to the class-based message handler registry."""
        return self._ws_message_handlers

    # ------------------------------------------------------------------
    # Background service management
    # ------------------------------------------------------------------

    def add_background_service(self, service: BackgroundService) -> "Nexus":
        """Register a background service for lifecycle management.

        The service will be started when Nexus.start() is called and
        stopped when Nexus.stop() is called.

        Args:
            service: A BackgroundService implementation.

        Returns:
            self (for chaining).
        """
        self._background_services.append(service)
        logger.info(f"Background service registered: {service.name}")
        return self

    def _initialize_gateway(self):
        """Initialize the underlying SDK enterprise gateway via HTTPTransport."""
        # Ensure HTTPTransport exists (for Nexus.__new__() without __init__)
        if not hasattr(self, "_http_transport"):
            self._http_transport = HTTPTransport(
                port=getattr(self, "_api_port", 8000),
                enable_durability=getattr(self, "_enable_durability", True),
            )
            if not hasattr(self, "_transports"):
                self._transports = []
            self._transports.append(self._http_transport)

        # Build CORS configuration from constructor params + environment defaults
        cors_config = self._build_cors_config()

        try:
            # Auto-detect max_workers if not explicitly set
            max_workers = self._max_workers
            if max_workers is None:
                cpu_count = os.cpu_count() or 4
                max_workers = min(4, cpu_count)

            # Create gateway using module-level create_gateway (patchable by tests)
            # Pass self.runtime to share a single AsyncLocalRuntime (fixes #211
            # dual-runtime bug where gateway created its own pool independently).
            gateway = create_gateway(
                title="Kailash Nexus - Zero-Config Workflow Platform",
                server_type=self._server_type,
                enable_durability=self._enable_durability,
                enable_resource_management=True,
                enable_async_execution=True,
                enable_health_checks=True,
                cors_origins=None,  # Nexus handles CORS natively
                max_workers=max_workers,
                runtime=getattr(self, "runtime", None),
            )
            # Store in HTTPTransport
            self._http_transport._gateway = gateway
            logger.info("Enterprise gateway initialized successfully")

            # Apply full CORS middleware with all options
            if cors_config["allow_origins"]:
                from starlette.middleware.cors import CORSMiddleware

                self._http_transport.add_middleware(
                    CORSMiddleware,
                    allow_origins=cors_config["allow_origins"],
                    allow_methods=cors_config["allow_methods"],
                    allow_headers=cors_config["allow_headers"],
                    allow_credentials=cors_config["allow_credentials"],
                    expose_headers=cors_config["expose_headers"],
                    max_age=cors_config["max_age"],
                )
                self._cors_middleware_applied = True

            # Apply any middleware that was queued before gateway was ready.
            for middleware_class, kwargs in self._middleware_queue:
                self._http_transport.add_middleware(middleware_class, **kwargs)
                logger.info(f"Applied queued middleware: {middleware_class.__name__}")
            self._middleware_queue.clear()

            # Apply any routers that were queued before gateway was ready.
            for router, router_kwargs in self._router_queue:
                self._http_transport.include_router(router, **router_kwargs)
                prefix = router_kwargs.get("prefix", "/")
                logger.info(f"Applied queued router: {prefix}")
            self._router_queue.clear()

            # Apply any sub-app mounts that were queued before gateway was ready.
            # Guarded via hasattr because Nexus.__new__() without __init__() is
            # used in some test setups that don't initialize the mount queue.
            if hasattr(self, "_mount_queue"):
                for mount_path, subapp, mount_name in self._mount_queue:
                    asgi_app = self._resolve_mount_subapp(subapp)
                    self._http_transport.mount(mount_path, asgi_app, name=mount_name)
                    logger.info(f"Applied queued mount: {mount_path}")
                self._mount_queue.clear()

        except Exception as e:
            logger.error(f"Failed to initialize enterprise gateway: {e}")
            raise RuntimeError(f"Nexus requires enterprise gateway: {e}")

    def _initialize_revolutionary_capabilities(self):
        """Initialize revolutionary capabilities that differentiate Nexus from traditional frameworks."""
        # Initialize essential capability components
        self._session_manager = None  # Cross-channel session sync
        self._execution_contexts = {}  # Workflow execution tracking

        # Performance tracking for revolutionary targets (bounded to prevent OOM)
        from collections import deque

        self._performance_metrics = {
            "workflow_registration_time": deque(maxlen=10000),
            "cross_channel_sync_time": deque(maxlen=10000),
            "failure_recovery_time": deque(maxlen=10000),
            "session_sync_latency": deque(maxlen=10000),
        }

        # Multi-channel orchestration state
        self._channel_registry = {
            "api": {"routes": {}, "status": "pending"},
            "cli": {"commands": {}, "status": "pending"},
            "mcp": {"tools": {}, "status": "pending"},
        }

        logger.info("Revolutionary capabilities initialized")

    def _initialize_mcp_server(self):
        """Initialize MCP server for AI agent integration.

        Uses the Core SDK's MCPServer + MCPChannel for full protocol support.
        The old Nexus-specific MCP server has been removed in favour of the
        unified ``kailash-platform`` MCP server (``kailash_mcp.platform_server``).
        """
        if not self._enable_http_transport:
            # Without HTTP transport, MCP is not available
            self._mcp_server = None
            self._mcp_channel = None
            logger.info(
                "HTTP transport disabled; MCP server not started. "
                "Use kailash-mcp for MCP access."
            )
            return

        try:
            # Import Core SDK's comprehensive MCP implementation for HTTP+WebSocket mode
            from kailash_mcp import MCPServer
            from kailash_mcp.auth.providers import APIKeyAuth

            from kailash.channels import ChannelConfig, ChannelType, MCPChannel

            # Create production-ready MCP server using Core SDK
            self._mcp_server = self._create_sdk_mcp_server()

            # Create MCP channel for workflow management
            self._mcp_channel = self._setup_mcp_channel()
            logger.info("Full MCP protocol support enabled (tools, resources, prompts)")

            logger.info(f"Production MCP server initialized on port {self._mcp_port}")

        except ImportError as e:
            # Core SDK MCP not available -- direct users to kailash-mcp
            logger.warning(
                "Core SDK MCP not available (%s). " "Use kailash-mcp for MCP access.",
                e,
            )
            self._mcp_server = None
            self._mcp_channel = None

    def _register_default_mcp_resources(self):
        """Register default MCP resources (system, docs, config, help)."""
        import json

        # System info resource
        async def system_info_handler(uri: str):
            info = {
                "platform": "Kailash Nexus",
                "version": getattr(self, "_version", "1.0.0"),
                "workflows": list(self._workflows.keys()),
                "api_port": self._api_port,
                "mcp_port": self._mcp_port,
            }
            return {
                "content": json.dumps(info, indent=2),
                "mimeType": "application/json",
            }

        self._mcp_server._resources["system://nexus/info"] = system_info_handler

        # Workflow resource handler (detailed)
        async def workflow_detail_handler(uri: str):
            # Extract workflow name from URI (workflow://name)
            workflow_name = uri.split("://")[1] if "://" in uri else uri
            if workflow_name not in self._workflows:
                return {
                    "content": json.dumps(
                        {"error": f"Workflow not found: {workflow_name}"}
                    ),
                    "mimeType": "application/json",
                }

            workflow = self._workflows[workflow_name]
            workflow_info = {
                "name": workflow_name,
                "type": "workflow",
                "nodes": [
                    {"id": node_id, "type": str(type(node).__name__)}
                    for node_id, node in workflow.nodes.items()
                ],
                "schema": {
                    "inputs": (
                        getattr(workflow.metadata, "parameters", {})
                        if hasattr(workflow, "metadata") and workflow.metadata
                        else {}
                    ),
                    "outputs": {},
                },
            }
            return {
                "content": json.dumps(workflow_info, indent=2),
                "mimeType": "application/json",
            }

        # Register workflow:// pattern (wildcard)
        self._mcp_server._resources["workflow://*"] = workflow_detail_handler

        # Documentation resource
        async def docs_handler(uri: str):
            docs_content = """# Nexus Quick Start Guide

Welcome to Kailash Nexus! This guide will help you get started.

## Overview
Nexus is a multi-channel platform that exposes workflows via:
- REST API
- CLI commands
- MCP protocol

## Quick Start
1. Register workflows using `app.register(name, workflow)`
2. Access via API at `/workflows/{name}`
3. Access via CLI with `nexus run {name}`
4. Access via MCP protocol as tools

For more information, visit the documentation.
"""
            return {"content": docs_content, "mimeType": "text/markdown"}

        self._mcp_server._resources["docs://quickstart"] = docs_handler

        # Configuration resource
        async def config_handler(uri: str):
            config = {
                "name": "Kailash Nexus",
                "api_port": self._api_port,
                "mcp_port": self._mcp_port,
                "features": {
                    "api": True,
                    "cli": True,
                    "mcp": True,
                    "monitoring": self._enable_monitoring,
                    "auth": self._enable_auth,
                },
            }
            return {
                "content": json.dumps(config, indent=2),
                "mimeType": "application/json",
            }

        self._mcp_server._resources["config://platform"] = config_handler

        # Help resource
        async def help_handler(uri: str):
            help_content = """# Getting Started with Nexus

## Available Workflows
"""
            for workflow_name in self._workflows.keys():
                help_content += f"- **{workflow_name}**: Workflow tool\n"

            help_content += """
## Resource URIs
- `system://nexus/info` - System information
- `workflow://<name>` - Workflow definitions
- `docs://quickstart` - Quick start guide
- `config://platform` - Platform configuration
- `help://getting-started` - This help resource

## Need Help?
Check the documentation or explore available resources.
"""
            return {"content": help_content, "mimeType": "text/markdown"}

        self._mcp_server._resources["help://getting-started"] = help_handler

    def _create_mock_mcp_server(self):
        """Create a simple mock MCP server for testing."""

        class MockMCPServer:
            def __init__(self):
                self._tools = {}
                self._resources = {}
                self._prompts = {}

            def tool(self, name=None, **kwargs):
                def decorator(func):
                    tool_name = name or func.__name__
                    self._tools[tool_name] = func
                    return func

                return decorator

            def resource(self, pattern):
                def decorator(func):
                    self._resources[pattern] = func
                    return func

                return decorator

        return MockMCPServer()

    def _create_sdk_mcp_server(self):
        """Create production-ready MCP server using Core SDK.

        This replaces the simple MCP server with the Core SDK's comprehensive
        implementation that includes authentication, caching, metrics, and
        full protocol support (tools, resources, prompts).
        """
        from kailash_mcp import MCPServer
        from kailash_mcp.auth.providers import APIKeyAuth

        # Configure authentication if enabled
        auth_provider = None
        if self._enable_auth:
            # Use API Key auth as default
            # In production, you'd load these from environment or config
            api_keys = self._get_api_keys()
            if api_keys:
                # APIKeyAuth expects a list of keys when using simple format
                auth_provider = APIKeyAuth(list(api_keys.values()))

        # Create enhanced MCP server with all enterprise features
        server = MCPServer(
            name=f"{self.name}-mcp",
            enable_cache=True,
            enable_metrics=True,
            auth_provider=auth_provider,
            enable_http_transport=self._enable_http_transport,
            enable_sse_transport=self._enable_sse_transport,
            rate_limit_config=self.rate_limit_config,
            circuit_breaker_config={"failure_threshold": 5},
            enable_discovery=self._enable_discovery,
            enable_streaming=True,
        )

        # Register default system information as a resource
        @server.resource("system://nexus/info")
        async def get_system_info() -> Dict[str, Any]:
            """Provide Nexus system information."""
            return {
                "uri": "system://nexus/info",
                "mimeType": "application/json",
                "content": json.dumps(
                    {
                        "platform": "Kailash Nexus",
                        "version": "1.0.0",
                        "workflows": list(self._workflows.keys()),
                        "capabilities": ["tools", "resources", "prompts"],
                        "transports": self._get_enabled_transports(),
                    },
                    indent=2,
                ),
            }

        return server

    def _setup_mcp_channel(self):
        """Set up MCP channel for workflow management.

        The MCPChannel automatically exposes workflows as MCP tools and
        manages the protocol implementation details.
        """
        from kailash.channels import ChannelConfig, ChannelType, MCPChannel

        # Create channel configuration
        config = ChannelConfig(
            name=f"{self.name}-mcp-channel",
            channel_type=ChannelType.MCP,
            host="0.0.0.0",
            port=self._mcp_port,
            enable_sessions=True,
            enable_auth=self._enable_auth,
            extra_config={
                "server_name": f"{self.name}-mcp",
                "description": f"MCP channel for {self.name} platform",
                "enable_resources": True,
                "enable_prompts": True,
            },
        )

        # Create MCP channel with our enhanced server
        mcp_channel = MCPChannel(config, mcp_server=self._mcp_server)

        # The channel will automatically register workflows as tools
        # when we call register() method

        return mcp_channel

    def _register_workflow_as_mcp_tool(self, name: str, workflow):
        """Register a workflow as an MCP tool dynamically.

        This is used when MCPChannel is not available (WebSocket-only mode).
        We manually register the workflow as a tool with the Core SDK's MCPServer.

        Uses self.runtime (server-level shared runtime) instead of creating
        a new AsyncLocalRuntime per invocation (M3-001 fix).
        """
        # Capture self.runtime in closure — all tool invocations share it
        shared_runtime = self.runtime

        async def workflow_tool(**params):
            """Execute workflow with given parameters."""
            execution_result = await shared_runtime.execute_workflow_async(
                workflow, inputs=params
            )
            if isinstance(execution_result, tuple):
                results, run_id = execution_result
            else:
                results = execution_result.get("results", execution_result)
                run_id = execution_result.get("run_id", None)
            return {
                "results": results,
                "run_id": run_id,
            }

        # Register as tool with the MCPServer
        # The @tool decorator syntax won't work dynamically, so we use internal registration
        if hasattr(self._mcp_server, "_tools"):
            self._mcp_server._tools[name] = workflow_tool
            logger.info(f"Workflow '{name}' registered as MCP tool (WebSocket mode)")
        else:
            logger.warning(
                f"Could not register workflow '{name}' as MCP tool - _tools attribute missing"
            )

    def _get_api_keys(self) -> Dict[str, str]:
        """Get API keys for authentication.

        In production, load from environment or secure config.
        """
        import os

        # Example: Load from environment variables
        api_keys = {}

        # Check for NEXUS_API_KEY_* environment variables
        for key, value in os.environ.items():
            if key.startswith("NEXUS_API_KEY_"):
                user_id = key.replace("NEXUS_API_KEY_", "").lower()
                api_keys[user_id] = value

        # Default test key if none provided (development only)
        if not api_keys and not os.environ.get("NEXUS_PRODUCTION"):
            api_keys["test_user"] = "test-api-key-12345"

        return api_keys

    def _get_enabled_transports(self) -> List[str]:
        """Get list of enabled MCP transports."""
        transports = ["websocket"]  # Always enabled

        if self._enable_http_transport:
            transports.append("http")

        if self._enable_sse_transport:
            transports.append("sse")

        return transports

    def register(
        self,
        name: str,
        workflow: Workflow,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        """Register a workflow to be available on all channels.

        Zero-config registration: Single registration → Multi-channel exposure (API, CLI, MCP)
        Leverages the enterprise gateway's built-in multi-channel support.

        Args:
            name: Workflow identifier
            workflow: Workflow instance or WorkflowBuilder
            metadata: Optional structured metadata (version, author, tags, description, etc.)
        """
        import time

        registration_start = time.time()

        # Handle WorkflowBuilder
        if hasattr(workflow, "build"):
            workflow = workflow.build()

        # Store internally via HandlerRegistry FIRST so metadata
        # validation (JSON-serializable, size cap) runs before we touch
        # the workflow object. If validation fails, the caller's
        # workflow is left untouched and the ValueError surfaces
        # cleanly — no half-mutated state to clean up.
        self._registry.register_workflow(name, workflow, metadata=metadata)

        # Merge caller-supplied metadata into the Workflow object itself
        # so downstream consumers that read workflow.metadata (MCP
        # workflow:// resource, OpenAPI schema derivation, etc.) see the
        # supplied fields without a second lookup. Caller values take
        # precedence over existing keys. We assign a NEW dict rather
        # than mutating in place: the same Workflow instance may be
        # registered under multiple names (shared builder output), and
        # in-place mutation would leak metadata across registrations.
        if metadata and hasattr(workflow, "metadata"):
            existing = workflow.metadata if workflow.metadata else {}
            workflow.metadata = {**existing, **metadata}

        # Validate PythonCodeNode sandbox issues at registration time
        self._validate_workflow_sandbox(name, workflow)

        # Register with enterprise gateway - this automatically exposes on all channels
        if self._http_transport.gateway:
            try:
                self._http_transport.register_workflow(name, workflow)
                logger.info(f"Workflow '{name}' registered with enterprise gateway")
            except Exception as e:
                logger.error(f"Failed to register workflow '{name}': {e}")
                raise

        # Register with MCP channel for full protocol support
        if hasattr(self, "_mcp_channel") and self._mcp_channel:
            # MCPChannel automatically exposes workflow as tool
            self._mcp_channel.register_workflow(name, workflow)
            logger.info(f"Workflow '{name}' registered with enhanced MCP channel")
        elif hasattr(self, "_mcp_server") and self._mcp_server:
            # Register workflow as MCP tool when using WebSocket wrapper
            # Core SDK MCPServer uses decorators, so we register dynamically
            if hasattr(self._mcp_server, "register_workflow"):
                # Simple MCP server has register_workflow method
                self._mcp_server.register_workflow(name, workflow)
            else:
                # Core SDK MCPServer - register as tool manually
                self._register_workflow_as_mcp_tool(name, workflow)

        # Track performance metric
        registration_time = time.time() - registration_start
        self._performance_metrics["workflow_registration_time"].append(
            registration_time
        )

        # Enhanced registration logging with full endpoint URLs
        base_url = f"http://localhost:{self._api_port}"
        logger.info(
            f"✅ Workflow '{name}' registered successfully!\n"
            f"   📡 API Endpoints:\n"
            f"      • POST   {base_url}/workflows/{name}/execute\n"
            f"      • GET    {base_url}/workflows/{name}/workflow/info\n"
            f"      • GET    {base_url}/workflows/{name}/health\n"
            f"   🤖 MCP Tool: workflow_{name}\n"
            f"   💻 CLI Command: nexus execute {name}\n"
            f"   ⏱️  Registration time: {registration_time:.3f}s"
        )

    # Multi-channel registration is handled automatically by the enterprise gateway
    # No need for custom channel registry - the gateway provides this natively

    def register_endpoint(
        self,
        path: str,
        methods: List[str],
        handler: Callable,
        **fastapi_kwargs: Any,
    ) -> None:
        """Programmatically register a custom HTTP endpoint.

        Unlike :meth:`endpoint` (a decorator that requires the gateway
        to be running), this method works **before** ``start()`` by
        queueing the registration on the underlying
        :class:`HTTPTransport`. Once the transport's gateway comes up,
        all queued endpoints are applied. After ``start()``, calls
        register immediately.

        This is the canonical hook used by DataFlow's fabric runtime
        (Phase 5.8) to expose product/health/SSE/webhook handlers when
        Nexus is passed as the platform process.

        Args:
            path: URL path with optional FastAPI path parameters
                (e.g., ``"/fabric/{product_name}"``).
            methods: HTTP verbs to register (``["GET"]``, ``["POST"]``,
                etc.). At least one method is required.
            handler: An async or sync callable matching FastAPI's
                signature conventions. Path parameters become
                positional kwargs; query parameters and body fields
                are resolved by FastAPI dependency injection.
            **fastapi_kwargs: Forwarded to FastAPI's ``add_api_route``
                (e.g., ``status_code``, ``response_model``, ``tags``,
                ``summary``).

        Raises:
            RuntimeError: If the HTTP transport has not been initialised
                (e.g., ``Nexus`` was constructed without HTTP support).
            ValueError: If ``methods`` is empty.

        Example:
            >>> async def health() -> dict:
            ...     return {"ok": True}
            >>> nexus.register_endpoint("/_health", ["GET"], health)
        """
        if not methods:
            raise ValueError("register_endpoint requires at least one HTTP method")
        if not hasattr(self, "_http_transport") or self._http_transport is None:
            raise RuntimeError(
                "Nexus HTTP transport is not initialised; cannot register endpoint"
            )
        self._http_transport.register_endpoint(path, methods, handler, **fastapi_kwargs)
        logger.info(
            "nexus.endpoint.registered",
            extra={"path": path, "methods": methods},
        )

    def endpoint(
        self,
        path: str,
        methods: Optional[List[str]] = None,
        rate_limit: Optional[int] = None,
        **fastapi_kwargs,
    ):
        """Decorator to register custom REST endpoint (API-only).

        This endpoint is API-channel only (not available in CLI or MCP).
        For multi-channel access, use register() method instead.

        Args:
            path: URL path pattern (e.g., "/api/conversations/{conversation_id}")
            methods: HTTP methods (default: ["GET"])
            rate_limit: Requests per minute limit (default: 100, None=unlimited)
            **fastapi_kwargs: Additional FastAPI route parameters
                - status_code: int - HTTP status code for successful response
                - response_model: Type - Pydantic model for response validation
                - tags: List[str] - OpenAPI tags for grouping
                - summary: str - Short description for OpenAPI
                - description: str - Long description for OpenAPI

        Returns:
            Decorator function that registers the endpoint

        Example:
            >>> @app.endpoint("/api/conversations/{conversation_id}",
            ...               methods=["GET"], rate_limit=50)
            >>> async def get_conversation(conversation_id: str):
            ...     return {"id": conversation_id}

        Raises:
            RuntimeError: If gateway not initialized
            ValueError: If invalid HTTP method provided
        """
        if methods is None:
            methods = ["GET"]

        # Use global rate limit config or endpoint-specific limit
        if rate_limit is None:
            # Check if global rate limit is configured
            rate_limit = self.rate_limit_config.get("default_rate_limit", 100)

        def decorator(func):
            # Validate gateway initialized
            if self._http_transport.gateway is None:
                raise RuntimeError(
                    "Gateway not initialized. Cannot register endpoints before gateway is ready."
                )

            # SECURITY: Add rate limiting wrapper
            import time
            from collections import defaultdict
            from functools import wraps
            from typing import Dict as TypingDict

            # Simple in-memory rate limiter (per client IP)
            request_counts: TypingDict[str, TypingDict[str, int]] = defaultdict(
                lambda: defaultdict(int)
            )
            rate_limit_window = 60  # 1 minute window

            @wraps(func)
            async def rate_limited_func(*args, **kwargs):
                from fastapi import HTTPException, Request

                # Extract FastAPI Request object (not Pydantic models)
                request = None

                # Check kwargs first
                if "request" in kwargs:
                    arg = kwargs["request"]
                    if isinstance(arg, Request):
                        request = arg

                # If not found in kwargs, check args
                if request is None:
                    for arg in args:
                        if isinstance(arg, Request):
                            request = arg
                            break

                # Only apply rate limiting if we have a real FastAPI Request object
                if (
                    request is not None
                    and isinstance(request, Request)
                    and rate_limit > 0
                ):
                    # Get client IP
                    client_ip = request.client.host if request.client else "unknown"
                    current_minute = int(time.time() // rate_limit_window)

                    # Check rate limit
                    if request_counts[client_ip][current_minute] >= rate_limit:
                        raise HTTPException(
                            status_code=429,
                            detail=f"Rate limit exceeded. Maximum {rate_limit} requests per minute.",
                        )

                    # Increment counter
                    request_counts[client_ip][current_minute] += 1

                    # Cleanup old entries (prevent memory leak)
                    old_minutes = [
                        m
                        for m in request_counts[client_ip].keys()
                        if m < current_minute - 5
                    ]
                    for old_minute in old_minutes:
                        del request_counts[client_ip][old_minute]

                # Call original function
                return await func(*args, **kwargs)

            # Use rate-limited wrapper
            wrapped_func = rate_limited_func

            # Get FastAPI app from HTTPTransport
            fastapi_app = self._http_transport.app

            # Register route for each method
            for method in methods:
                method_lower = method.lower()

                # Validate HTTP method
                valid_methods = [
                    "get",
                    "post",
                    "put",
                    "delete",
                    "patch",
                    "head",
                    "options",
                ]
                if method_lower not in valid_methods:
                    raise ValueError(f"Unsupported HTTP method: {method}")

                # Register route with FastAPI
                route_func = getattr(fastapi_app, method_lower)
                route_func(path, **fastapi_kwargs)(wrapped_func)

            # Log registration
            methods_str = ", ".join(methods)
            rate_limit_str = f", rate_limit={rate_limit}/min" if rate_limit > 0 else ""
            logger.info(
                f"✅ Custom endpoint registered: {methods_str} {path} (API-only{rate_limit_str})"
            )

            return wrapped_func

        return decorator

    # =========================================================================
    # Public Middleware API (WS01 - TODO-300A)
    # =========================================================================

    def add_middleware(
        self,
        middleware_class: type,
        **kwargs: Any,
    ) -> "Nexus":
        """Add middleware to the Nexus application.

        Middleware executes in LIFO order (last added = outermost = runs first
        on request). This follows Starlette's onion model where middleware wraps
        inner middleware. Can be called before or after start() - if the gateway
        is not ready, middleware is queued and applied during initialization.

        Args:
            middleware_class: A valid ASGI/Starlette middleware class.
                Must be a class (not instance) that accepts ``app`` as first
                argument.
            **kwargs: Arguments passed to the middleware constructor.

        Returns:
            self (for method chaining)

        Raises:
            TypeError: If middleware_class is not a valid middleware type.

        Example:
            >>> from starlette.middleware.cors import CORSMiddleware
            >>> app = Nexus()
            >>> app.add_middleware(
            ...     CORSMiddleware,
            ...     allow_origins=["http://localhost:3000"],
            ...     allow_methods=["*"],
            ...     allow_headers=["*"],
            ... )
        """
        # Validate
        if not isinstance(middleware_class, type):
            raise TypeError(
                f"middleware_class must be a class, got {type(middleware_class).__name__}. "
                f"Pass the class itself (e.g., CORSMiddleware), not an instance."
            )

        # Warn on duplicate middleware class (non-blocking per spec)
        for existing in self._middleware_stack:
            if existing.middleware_class is middleware_class:
                logger.warning(
                    f"Duplicate middleware: {middleware_class.__name__} has already been added. "
                    f"Adding it again may cause unexpected behavior."
                )
                break

        # Store for introspection
        info = MiddlewareInfo(
            middleware_class=middleware_class,
            kwargs=kwargs,
            added_at=datetime.now(UTC),
        )
        self._middleware_stack.append(info)

        # Apply or queue via HTTPTransport
        if hasattr(self, "_http_transport"):
            self._http_transport.add_middleware(middleware_class, **kwargs)
            if self._http_transport.gateway is not None:
                logger.info(f"Added middleware: {middleware_class.__name__}")
            else:
                # Also maintain Nexus-level queue for backward compatibility
                self._middleware_queue.append((middleware_class, kwargs))
                logger.debug(
                    f"Queued middleware: {middleware_class.__name__} (gateway not ready)"
                )
        else:
            # Fallback for __new__-constructed instances (no __init__)
            self._middleware_queue.append((middleware_class, kwargs))
            logger.debug(
                f"Queued middleware: {middleware_class.__name__} (transport not ready)"
            )

        return self  # Enable chaining

    @property
    def middleware(self) -> List[MiddlewareInfo]:
        """List of registered middleware in application order."""
        return self._middleware_stack.copy()

    def use_middleware(self, func: Callable) -> Callable:
        """Decorator to register a function as HTTP middleware.

        Provides a FastAPI-style ``@app.middleware("http")`` equivalent for
        Nexus. The decorated function receives ``(request, call_next)`` and
        must return a ``Response``. Internally wraps the function in a
        Starlette :class:`~starlette.middleware.base.BaseHTTPMiddleware`
        subclass and delegates to :meth:`add_middleware`.

        The ``use_middleware`` name is used (instead of ``middleware``) to
        avoid colliding with the :attr:`middleware` introspection property
        that returns the registered middleware list.

        Args:
            func: An async function with signature
                ``async def mw(request: Request, call_next) -> Response``.
                Synchronous functions are rejected because the underlying
                ``BaseHTTPMiddleware.dispatch`` contract requires an
                awaitable — running a sync function on the event loop
                would block all concurrent requests.

        Returns:
            The original function (unmodified) so the decorator can be
            stacked or the function still called directly in tests.

        Raises:
            TypeError: If *func* is not callable, is a class (use
                :meth:`add_middleware` for class-based middleware), or
                is a synchronous function.

        Example:
            >>> @app.use_middleware
            ... async def timing_middleware(request, call_next):
            ...     import time
            ...     t0 = time.monotonic()
            ...     response = await call_next(request)
            ...     response.headers["X-Process-Time"] = str(
            ...         time.monotonic() - t0
            ...     )
            ...     return response
        """
        # Validate: reject non-callable
        if not callable(func):
            raise TypeError(
                f"use_middleware expects an async function, got "
                f"{type(func).__name__}"
            )

        # Validate: reject classes — use add_middleware for those
        if isinstance(func, type):
            raise TypeError(
                "use_middleware expects a function, got a class. "
                "Use add_middleware() to register a middleware class."
            )

        # Validate: reject sync functions — BaseHTTPMiddleware.dispatch
        # must return an awaitable. A sync function would block the event
        # loop and surface as a "coroutine expected" error at request time.
        if not asyncio.iscoroutinefunction(func):
            func_name = getattr(func, "__name__", repr(func))
            raise TypeError(
                f"use_middleware expects an async function, got sync "
                f"function {func_name!r}. Define with "
                f"'async def {func_name}(request, call_next): ...'"
            )

        from starlette.middleware.base import BaseHTTPMiddleware

        # Build a middleware class that captures the user function.
        # Each decorated function gets its own class so add_middleware's
        # duplicate-class detection works correctly (two decorated
        # functions produce two distinct classes).
        class _FuncMiddleware(BaseHTTPMiddleware):
            async def dispatch(self, request, call_next):  # noqa: N805
                return await func(request, call_next)

        # Preserve the original function name for logging / introspection.
        _FuncMiddleware.__name__ = f"FuncMiddleware[{func.__name__}]"
        _FuncMiddleware.__qualname__ = _FuncMiddleware.__name__

        logger.info(
            "nexus.use_middleware.registered",
            extra={"func": func.__name__},
        )
        self.add_middleware(_FuncMiddleware)
        return func

    # =========================================================================
    # Public Router API (WS01 - TODO-300B)
    # =========================================================================

    def include_router(
        self,
        router: Any,
        prefix: str = "",
        tags: Optional[List[str]] = None,
        dependencies: Optional[List[Any]] = None,
        **kwargs: Any,
    ) -> "Nexus":
        """Include a FastAPI router in the Nexus application.

        Routers provide a way to organize endpoints into logical groups.
        Can be called before or after start() - if the gateway is not ready,
        the router is queued and included during initialization.

        Args:
            router: A FastAPI APIRouter instance.
            prefix: URL prefix for all routes in this router
                (e.g., ``"/api/users"``).
            tags: OpenAPI tags for all routes (for documentation grouping).
            dependencies: Dependencies to apply to all routes in this router.
            **kwargs: Additional arguments passed to FastAPI's
                ``include_router()``.

        Returns:
            self (for method chaining)

        Raises:
            TypeError: If router is not an APIRouter instance.

        Example:
            >>> from fastapi import APIRouter
            >>>
            >>> user_router = APIRouter()
            >>> @user_router.get("/{user_id}")
            >>> async def get_user(user_id: str):
            ...     return {"user_id": user_id}
            >>>
            >>> app = Nexus()
            >>> app.include_router(
            ...     user_router, prefix="/api/users", tags=["Users"]
            ... )
        """
        from fastapi import APIRouter as _APIRouter

        # Validate
        if not isinstance(router, _APIRouter):
            raise TypeError(
                f"router must be a FastAPI APIRouter, got {type(router).__name__}"
            )

        # Warn on potential route conflicts (non-blocking)
        if prefix and self._has_route_conflict(prefix):
            logger.warning(
                f"Router prefix '{prefix}' may conflict with existing routes"
            )

        # Build kwargs dict for FastAPI
        router_kwargs: Dict[str, Any] = {
            "prefix": prefix,
            "tags": tags or [],
            "dependencies": dependencies or [],
            **kwargs,
        }

        # Store for introspection
        info = RouterInfo(
            router=router,
            prefix=prefix,
            tags=tags or [],
            added_at=datetime.now(UTC),
        )
        self._routers.append(info)

        # Apply or queue via HTTPTransport
        if hasattr(self, "_http_transport"):
            self._http_transport.include_router(router, **router_kwargs)
            if self._http_transport.gateway is not None:
                logger.info(f"Included router with prefix: {prefix or '/'}")
            else:
                self._router_queue.append((router, router_kwargs))
                logger.debug(f"Queued router: {prefix or '/'} (gateway not ready)")
        else:
            self._router_queue.append((router, router_kwargs))
            logger.debug(f"Queued router: {prefix or '/'} (transport not ready)")

        return self  # Enable chaining

    def mount(
        self,
        path: str,
        subapp: Any,
        name: Optional[str] = None,
    ) -> "Nexus":
        """Mount a sub-application at a URL path prefix.

        Composes another application (another ``Nexus`` instance or any
        ASGI app) under the parent at the given path. Requests whose URL
        starts with ``path`` are routed into the sub-application with the
        ``path`` prefix stripped before dispatch. The sub-application
        retains its own middleware, authentication, and routing stack —
        all of which apply to mounted requests.

        Composition is recursive: a mounted ``Nexus`` may itself ``mount``
        additional sub-applications at any depth.

        The mount is applied to the live FastAPI app if the gateway is
        ready, otherwise queued and applied during gateway initialization.

        Args:
            path: URL prefix where the sub-application is exposed
                (e.g., ``"/api/v2"``). MUST be non-empty and MUST start
                with ``"/"``. A trailing slash is stripped for
                consistency with Starlette's mount semantics.
            subapp: The sub-application to mount. Either a ``Nexus``
                instance (composition) or any ASGI-compatible app
                (FastAPI, Starlette, or bare ASGI callable).
            name: Optional name for the mount (forwarded to Starlette
                for URL reversal / introspection).

        Returns:
            self (for chaining).

        Raises:
            TypeError: If ``path`` is not a string or ``subapp`` is
                ``None``.
            ValueError: If ``path`` is empty, does not start with ``"/"``,
                or is already mounted.

        Example:
            >>> parent = Nexus(api_port=8000)
            >>> child = Nexus(api_port=8001)
            >>>
            >>> @child.handler("ping")
            ... async def ping() -> dict:
            ...     return {"pong": True}
            ...
            >>> parent.mount("/api/v2", child)
            >>> # Requests to /api/v2/workflows/ping/execute dispatch into
            >>> # the child Nexus, with "/api/v2" stripped before routing.
        """
        # Type / value validation
        if not isinstance(path, str):
            raise TypeError(f"path must be str, got {type(path).__name__}")
        if subapp is None:
            raise TypeError("subapp must not be None")
        if not path:
            raise ValueError("path must be non-empty (e.g. '/api/v2')")
        if not path.startswith("/"):
            raise ValueError(f"path must start with '/', got {path!r}")

        # Normalize: strip a single trailing slash so "/api/" -> "/api"
        # (Starlette's Mount treats "/api/" and "/api" equivalently for
        # dispatch but introspection becomes confusing if both coexist).
        if len(path) > 1 and path.endswith("/"):
            path = path.rstrip("/")

        # Initialize tracking state if caller used Nexus.__new__() without
        # running __init__ (test shim pattern).
        if not hasattr(self, "_mounts"):
            self._mounts = []
        if not hasattr(self, "_mount_queue"):
            self._mount_queue = []

        # Reject duplicate mount paths (same rationale as duplicate handlers)
        for existing in self._mounts:
            if existing.path == path:
                raise ValueError(
                    f"path {path!r} is already mounted; unmount first or "
                    f"choose a different prefix"
                )

        # Record for introspection
        info = MountInfo(
            path=path,
            subapp=subapp,
            name=name,
            added_at=datetime.now(UTC),
        )
        self._mounts.append(info)

        # Apply or queue
        if (
            hasattr(self, "_http_transport")
            and self._http_transport.gateway is not None
        ):
            asgi_app = self._resolve_mount_subapp(subapp)
            self._http_transport.mount(path, asgi_app, name=name)
            logger.info(f"Mounted sub-application at {path}")
        else:
            self._mount_queue.append((path, subapp, name))
            logger.debug(f"Queued mount at {path} (gateway not ready)")

        return self

    def _resolve_mount_subapp(self, subapp: Any) -> Any:
        """Resolve a mount target to a concrete ASGI app.

        - If ``subapp`` is a ``Nexus`` instance, return its underlying
          FastAPI app (``fastapi_app``). The child Nexus's own
          middleware / routers / handlers are attached to that FastAPI
          app, so mounting it gives the caller the child's full stack.
        - Otherwise, return ``subapp`` as-is (assumed ASGI-compatible).

        Args:
            subapp: The mount target.

        Returns:
            An ASGI application callable.

        Raises:
            RuntimeError: If ``subapp`` is a Nexus whose FastAPI app is
                not yet initialized.
        """
        if isinstance(subapp, Nexus):
            child_app = subapp.fastapi_app
            if child_app is None:
                raise RuntimeError(
                    "Cannot mount child Nexus: its FastAPI app is not "
                    "yet initialized. Ensure the child was fully "
                    "constructed before calling mount()."
                )
            return child_app
        return subapp

    def _has_route_conflict(self, prefix: str) -> bool:
        """Check if router prefix may conflict with existing routes.

        Args:
            prefix: Router prefix to check.

        Returns:
            True if potential conflict detected, False otherwise.
        """
        for router_info in self._routers:
            if router_info.prefix == prefix:
                return True

        if hasattr(self, "_http_transport") and self._http_transport.app is not None:
            for route in self._http_transport.app.routes:
                if hasattr(route, "path") and route.path.startswith(prefix):
                    return True

        return False

    @property
    def routers(self) -> List[RouterInfo]:
        """List of included routers."""
        return self._routers.copy()

    # =========================================================================
    # Public Plugin API (WS01 - TODO-300C)
    # =========================================================================

    def add_plugin(
        self,
        plugin: Any,
    ) -> "Nexus":
        """Install a plugin into the Nexus application.

        Plugins are a composable way to add cross-cutting functionality.
        The plugin's ``install()`` method is called immediately, and lifecycle
        hooks (``on_startup``, ``on_shutdown``) are registered for later
        invocation.

        Args:
            plugin: An object implementing the NexusPluginProtocol.
                Must have a ``name`` property and an ``install(app)`` method.

        Returns:
            self (for method chaining)

        Raises:
            TypeError: If plugin does not implement required methods.
            ValueError: If a plugin with the same name is already installed.

        Example:
            >>> class MyPlugin:
            ...     @property
            ...     def name(self): return "my-plugin"
            ...     def install(self, app): pass
            ...     def on_startup(self): print("started")
            ...     def on_shutdown(self): print("stopped")
            >>>
            >>> app = Nexus()
            >>> app.add_plugin(MyPlugin())
        """
        # Validate plugin protocol
        if not hasattr(plugin, "name") or not hasattr(plugin, "install"):
            raise TypeError(
                f"Plugin must implement NexusPluginProtocol "
                f"(requires 'name' and 'install'). "
                f"Got: {type(plugin).__name__}"
            )

        # Check for duplicate
        plugin_name = plugin.name
        if plugin_name in self._plugins:
            raise ValueError(f"Plugin '{plugin_name}' is already installed")

        # Store plugin
        self._plugins[plugin_name] = plugin

        # Call install immediately
        logger.info(f"Installing plugin: {plugin_name}")
        plugin.install(self)

        # Register lifecycle hooks if present
        if hasattr(plugin, "on_startup") and callable(plugin.on_startup):
            self._startup_hooks.append(plugin.on_startup)

        if hasattr(plugin, "on_shutdown") and callable(plugin.on_shutdown):
            self._shutdown_hooks.append(plugin.on_shutdown)

        logger.info(f"Plugin installed: {plugin_name}")
        return self

    def _run_async_hook(self, hook) -> None:
        """Run an async hook, handling both running and non-running event loops."""
        import asyncio

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop is not None and loop.is_running():
            # Inside a running event loop (e.g., FastAPI/uvicorn) -
            # schedule as a task so it runs in the current loop
            task = loop.create_task(hook())

            def _hook_done_callback(t):
                exc = t.exception()
                if exc:
                    logger.error("Async lifecycle hook %s failed: %s", hook, exc)

            task.add_done_callback(_hook_done_callback)
        else:
            # No running event loop - safe to use asyncio.run()
            asyncio.run(hook())

    def _call_startup_hooks(self) -> None:
        """Call all registered startup hooks.

        Errors are logged but do not prevent other hooks from running.
        """
        import asyncio

        for hook in self._startup_hooks:
            try:
                if asyncio.iscoroutinefunction(hook):
                    self._run_async_hook(hook)
                else:
                    hook()
            except Exception as e:
                logger.error(f"Startup hook failed: {e}")

    def _call_shutdown_hooks(self) -> None:
        """Call all registered shutdown hooks in reverse order.

        Errors are logged but do not prevent other hooks from running.
        Hooks run in reverse registration order (last installed runs first).
        """
        import asyncio

        for hook in reversed(self._shutdown_hooks):
            try:
                if asyncio.iscoroutinefunction(hook):
                    self._run_async_hook(hook)
                else:
                    hook()
            except Exception as e:
                logger.error(f"Shutdown hook failed: {e}")

    @property
    def plugins(self) -> Dict[str, Any]:
        """Dictionary of installed plugins by name."""
        return self._plugins.copy()

    # =========================================================================
    # CORS Configuration API (WS01 - TODO-300E)
    # =========================================================================

    def _get_cors_defaults(self) -> Dict[str, Any]:
        """Get environment-aware CORS defaults.

        Returns:
            CORS configuration dict with sensible defaults based on NEXUS_ENV.
        """
        nexus_env = os.getenv("NEXUS_ENV", "development").lower()

        if nexus_env == "production":
            # Production: No origins allowed by default - must be explicit
            return {
                "allow_origins": [],
                "allow_methods": ["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
                "allow_headers": ["Authorization", "Content-Type", "X-Request-ID"],
                "allow_credentials": True,
                "expose_headers": ["X-Request-ID"],
                "max_age": 600,
            }
        else:
            # Development/staging: Permissive defaults
            return {
                "allow_origins": ["*"],
                "allow_methods": ["*"],
                "allow_headers": ["*"],
                "allow_credentials": True,
                "expose_headers": [],
                "max_age": 600,
            }

    def _build_cors_config(self) -> Dict[str, Any]:
        """Build CORS configuration from constructor parameters and defaults."""
        defaults = self._get_cors_defaults()

        return {
            "allow_origins": (
                self._cors_origins
                if self._cors_origins is not None
                else defaults["allow_origins"]
            ),
            "allow_methods": (
                self._cors_allow_methods
                if self._cors_allow_methods is not None
                else defaults["allow_methods"]
            ),
            "allow_headers": (
                self._cors_allow_headers
                if self._cors_allow_headers is not None
                else defaults["allow_headers"]
            ),
            "allow_credentials": self._cors_allow_credentials,
            "expose_headers": (
                self._cors_expose_headers
                if self._cors_expose_headers is not None
                else defaults["expose_headers"]
            ),
            "max_age": self._cors_max_age,
        }

    def _validate_cors_origins(self, origins: List[str]) -> None:
        """Validate CORS origins configuration.

        Args:
            origins: List of origin strings to validate.

        Raises:
            ValueError: If configuration is insecure for production.
        """
        nexus_env = os.getenv("NEXUS_ENV", "development").lower()

        if nexus_env == "production" and "*" in origins:
            raise ValueError(
                "CORS allow_origins=['*'] is not allowed in production. "
                "Specify explicit origins: cors_origins=['https://app.example.com']"
            )

        # Validate origin format
        for origin in origins:
            if origin != "*" and not origin.startswith(("http://", "https://")):
                logger.warning(
                    f"CORS origin '{origin}' may be invalid. "
                    f"Origins should be full URLs like 'https://example.com'"
                )

    def _validate_cors_security(self, cors_config: Dict[str, Any]) -> None:
        """Warn about insecure CORS configurations.

        Specifically warns when allow_credentials=True with allow_origins=["*"],
        which browsers reject (credentials require explicit origins).
        """
        origins = cors_config.get("allow_origins", [])
        credentials = cors_config.get("allow_credentials", False)

        if credentials and "*" in origins:
            logger.warning(
                "CORS security warning: allow_credentials=True with allow_origins=['*'] "
                "is rejected by browsers. Credentials require explicit origin URLs. "
                "Either set specific origins or disable credentials."
            )

    def _apply_cors_middleware(self) -> None:
        """Apply or update CORS middleware on the gateway."""
        from starlette.middleware.cors import CORSMiddleware

        cors_config = self._build_cors_config()

        # Validate security implications
        self._validate_cors_security(cors_config)

        # Warn if reconfiguring after initial application
        if self._cors_middleware_applied:
            logger.warning(
                "Reconfiguring CORS after gateway initialization. "
                "For best results, configure CORS before calling start()."
            )

        # Add CORS middleware via HTTPTransport
        self._http_transport.add_middleware(
            CORSMiddleware,
            allow_origins=cors_config["allow_origins"],
            allow_methods=cors_config["allow_methods"],
            allow_headers=cors_config["allow_headers"],
            allow_credentials=cors_config["allow_credentials"],
            expose_headers=cors_config["expose_headers"],
            max_age=cors_config["max_age"],
        )

        self._cors_middleware_applied = True

    def configure_cors(
        self,
        allow_origins: Optional[List[str]] = None,
        allow_methods: Optional[List[str]] = None,
        allow_headers: Optional[List[str]] = None,
        allow_credentials: Optional[bool] = None,
        expose_headers: Optional[List[str]] = None,
        max_age: Optional[int] = None,
    ) -> "Nexus":
        """Configure CORS middleware programmatically.

        This method can be called before or after start(). If called after
        the gateway is initialized, it will reconfigure the CORS middleware.

        Args:
            allow_origins: Allowed origins. If None, keeps current setting.
            allow_methods: Allowed methods. If None, keeps current setting.
            allow_headers: Allowed headers. If None, keeps current setting.
            allow_credentials: Allow credentials. If None, keeps current setting.
            expose_headers: Exposed headers. If None, keeps current setting.
            max_age: Preflight cache duration. If None, keeps current setting.

        Returns:
            self (for method chaining)

        Raises:
            ValueError: If called in production with allow_origins=["*"].
        """
        if allow_origins is not None:
            self._validate_cors_origins(allow_origins)
            self._cors_origins = allow_origins

        if allow_methods is not None:
            self._cors_allow_methods = allow_methods

        if allow_headers is not None:
            self._cors_allow_headers = allow_headers

        if allow_credentials is not None:
            self._cors_allow_credentials = allow_credentials

        if expose_headers is not None:
            self._cors_expose_headers = expose_headers

        if max_age is not None:
            self._cors_max_age = max_age

        # Validate security implications
        self._validate_cors_security(self._build_cors_config())

        # Apply if gateway already initialized
        if self._http_transport.gateway is not None:
            self._apply_cors_middleware()

        logger.info(f"CORS configured: origins={self._cors_origins}")
        return self

    @property
    def cors_config(self) -> Dict[str, Any]:
        """Current CORS configuration."""
        return self._build_cors_config()

    def is_origin_allowed(self, origin: str) -> bool:
        """Check if an origin is allowed by current CORS configuration.

        Args:
            origin: Origin URL to check (e.g., "https://app.example.com")

        Returns:
            True if origin is allowed, False otherwise.
        """
        origins = self._cors_origins or self._get_cors_defaults()["allow_origins"]

        if "*" in origins:
            return True

        return origin in origins

    # =========================================================================
    # Preset System API (WS01 - TODO-300D)
    # =========================================================================

    @property
    def active_preset(self) -> Optional[str]:
        """Name of the active preset, if any."""
        return getattr(self, "_active_preset", None)

    @property
    def preset_config(self) -> Optional[Any]:
        """Configuration used for the active preset."""
        return getattr(self, "_nexus_config", None)

    def describe_preset(self) -> Dict[str, Any]:
        """Get detailed information about the active preset.

        Returns:
            Dictionary with preset name, description, middleware, and plugins.
        """
        if not self.active_preset:
            return {"preset": None, "middleware": [], "plugins": []}

        from nexus.presets import PRESETS

        preset = PRESETS.get(self.active_preset)
        description = preset.description if preset else ""

        result: Dict[str, Any] = {
            "preset": self.active_preset,
            "description": description,
            "middleware": [m.name for m in self._middleware_stack],
            "plugins": list(self._plugins.keys()),
        }

        if self._nexus_config is not None:
            result["config"] = {
                "cors_origins": self._nexus_config.cors_origins,
                "rate_limit": self._nexus_config.rate_limit,
                "tenant_header": self._nexus_config.tenant_header,
                "audit_enabled": self._nexus_config.audit_enabled,
            }

        return result

    # =========================================================================
    # Handler API
    # =========================================================================

    def handler(
        self,
        name: str,
        description: str = "",
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        guard: Any = None,
    ):
        """Decorator to register an async function as a multi-channel workflow.

        This provides first-class handler support, bypassing the PythonCodeNode
        sandbox. The decorated function's signature is inspected to derive
        workflow parameters automatically.

        The handler is exposed on all channels (API, CLI, MCP) just like
        workflows registered via register().

        Args:
            name: Workflow name for registration.
            description: Optional description for the workflow.
            tags: Optional tags for categorization.
            metadata: Optional structured metadata (version, author, tags, etc.).
            guard: Optional AuthGuard for per-handler RBAC. The guard's
                ``check(user, request_context)`` is called before the handler
                executes. Requires NexusAuthPlugin (JWT middleware sets
                ``request.state.user``).

        Returns:
            Decorator function.

        Example:
            >>> from nexus.auth.guards import AuthGuard
            >>> @app.handler("greet", description="Greet a user")
            ... async def greet(name: str, greeting: str = "Hello") -> dict:
            ...     return {"message": f"{greeting}, {name}!"}
            ...
            ... @app.handler("admin.reset", guard=AuthGuard.RequireRole("admin"))
            ... async def reset_cache() -> dict:
            ...     return {"status": "cleared"}
        """

        def decorator(func):
            self.register_handler(
                name,
                func,
                description=description,
                tags=tags,
                metadata=metadata,
                guard=guard,
            )
            return func

        return decorator

    def register_handler(
        self,
        name: str,
        handler_func,
        description: str = "",
        tags: Optional[List[str]] = None,
        input_mapping: Optional[Dict[str, str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        guard: Any = None,
    ):
        """Register an async/sync function as a multi-channel workflow.

        Non-decorator equivalent of @app.handler(). Builds a HandlerNode
        workflow from the function and delegates to self.register() for
        multi-channel exposure.

        Args:
            name: Workflow name for registration.
            handler_func: The async or sync function to register.
            description: Optional description.
            tags: Optional tags for categorization.
            input_mapping: Optional mapping of workflow input names to handler
                parameter names. If None, identity mapping is used.
            metadata: Optional structured metadata (version, author, tags, etc.).
            guard: Optional AuthGuard for per-handler RBAC enforcement.

        Raises:
            TypeError: If handler_func is not callable.
            ValueError: If name is empty or already registered as a handler.
        """
        if not callable(handler_func):
            raise TypeError(
                f"handler_func must be callable, got {type(handler_func).__name__}"
            )

        # Validate name for dangerous characters (defense-in-depth)
        from nexus.validation import validate_workflow_name

        validate_workflow_name(name)

        from kailash.nodes.handler import make_handler_workflow

        workflow = make_handler_workflow(
            handler_func, node_id="handler", input_mapping=input_mapping
        )

        # Delegate handler storage to HandlerRegistry (includes duplicate check)
        self._registry.register_handler(
            name,
            handler_func,
            description=description or getattr(handler_func, "__doc__", "") or "",
            tags=tags,
            metadata=metadata,
            workflow=workflow,
            guard=guard,
        )

        # Delegate to register() for multi-channel exposure
        self.register(name, workflow, metadata=metadata)

        logger.info(f"Handler '{name}' registered (function: {handler_func.__name__})")

    def _validate_workflow_sandbox(self, name: str, workflow: Workflow):
        """Check for PythonCodeNode/AsyncPythonCodeNode with blocked imports.

        Emits logger.warning() (not exceptions) when sandbox-restricted
        imports are detected, with an actionable message suggesting
        @app.handler() as an alternative.

        This runs at registration time to give early feedback.

        Args:
            name: Workflow name for logging.
            workflow: The workflow to validate.
        """
        import ast

        try:
            from kailash.nodes.code.common import ALLOWED_ASYNC_MODULES, ALLOWED_MODULES
        except ImportError:
            return

        # Build map of node_id -> actual instance (if available)
        node_instances = {}
        if hasattr(workflow, "_node_instances"):
            node_instances = workflow._node_instances

        # Also check workflow.nodes for type info
        if not hasattr(workflow, "nodes") and not node_instances:
            return

        # Iterate over known nodes
        nodes_to_check = {}
        if hasattr(workflow, "nodes"):
            for node_id, node_info in workflow.nodes.items():
                node_type_name = (
                    getattr(node_info, "node_type", None) or type(node_info).__name__
                )
                if node_type_name in ("PythonCodeNode", "AsyncPythonCodeNode"):
                    # Get the actual instance if available
                    instance = node_instances.get(node_id)
                    nodes_to_check[node_id] = (node_type_name, instance)

        # Also check _node_instances directly for instances not in workflow.nodes
        for node_id, instance in node_instances.items():
            if node_id not in nodes_to_check:
                node_type_name = type(instance).__name__
                if node_type_name in ("PythonCodeNode", "AsyncPythonCodeNode"):
                    nodes_to_check[node_id] = (node_type_name, instance)

        for node_id, (node_type_name, instance) in nodes_to_check.items():
            code = getattr(instance, "code", None) if instance else None
            if not code:
                continue

            # Determine which allowed list to use
            if node_type_name == "AsyncPythonCodeNode":
                allowed = ALLOWED_ASYNC_MODULES
            else:
                allowed = ALLOWED_MODULES

            # Parse and check imports
            try:
                tree = ast.parse(code)
            except SyntaxError as e:
                logger.warning(
                    f"Workflow '{name}': {node_type_name} node '{node_id}' has "
                    f"syntax error in code: {e}. "
                    f"Consider using @app.handler() for complex logic."
                )
                continue

            for ast_node in ast.walk(tree):
                blocked_modules = []
                if isinstance(ast_node, ast.Import):
                    for alias in ast_node.names:
                        root = alias.name.split(".")[0]
                        if root not in allowed:
                            blocked_modules.append(alias.name)
                elif isinstance(ast_node, ast.ImportFrom):
                    if ast_node.module:
                        root = ast_node.module.split(".")[0]
                        if root not in allowed:
                            blocked_modules.append(ast_node.module)

                for module in blocked_modules:
                    logger.warning(
                        f"Workflow '{name}': {node_type_name} node '{node_id}' "
                        f"imports '{module}' which is not in the sandbox "
                        f"allowlist. This will fail at execution time. "
                        f"Consider using @app.handler() to bypass the sandbox."
                    )

    # ------------------------------------------------------------------
    # NTR-020: DataFlow integration
    # ------------------------------------------------------------------

    def integrate_dataflow(self, db) -> "Nexus":
        """Connect DataFlow events to the Nexus EventBus.

        After calling this, DataFlow model writes (create, update, delete,
        upsert, and their bulk variants) automatically emit events to the
        Nexus EventBus.  Use ``@app.on_event()`` to handle them.

        The bridge subscribes to the Core SDK ``InMemoryEventBus`` for
        each registered model and translates ``DomainEvent`` instances
        into ``NexusEvent`` instances.  Two separate event systems are
        connected -- they are NOT merged.

        Args:
            db: A DataFlow instance with registered models.

        Returns:
            self (for chaining).

        Example::

            app = Nexus()
            db = DataFlow("sqlite:///app.db")

            @db.model
            class User:
                id: int
                name: str

            app.integrate_dataflow(db)

            @app.on_event("dataflow.User.create")
            async def on_user_created(event):
                print(f"New user: {event.data['payload']}")
        """
        from nexus.bridges.dataflow import DataFlowEventBridge

        bridge = DataFlowEventBridge()
        bridge.install(self._event_bus, db)
        return self

    # ------------------------------------------------------------------
    # Phase 2 Feature APIs — event, scheduled, emit, run_in_background
    # ------------------------------------------------------------------

    def on_event(self, event_type: str):
        """Decorator to register an event-driven handler.

        The handler is invoked when an event matching event_type is
        published to the EventBus. Supports exact match and wildcard
        patterns (e.g., "dataflow.*").

        Args:
            event_type: Event type string to listen for.

        Example:
            @app.on_event("user.created")
            async def on_user_created(event):
                print(f"User created: {event.data}")
        """

        def decorator(func):
            self._registry.register_handler(
                name=f"event_{event_type}_{func.__name__}",
                func=func,
                description=f"Event handler for {event_type}",
                metadata={"event_type": event_type, "channel": "event"},
            )
            return func

        return decorator

    def scheduled(self, interval: str, *, cron: Optional[str] = None):
        """Decorator to register a scheduled handler.

        The handler runs periodically at the specified interval or cron
        expression. Uses asyncio.create_task (not FastAPI BackgroundTasks).

        Args:
            interval: Human-readable interval ("30s", "5m", "2h", "1d").
            cron: Optional cron expression (requires croniter).

        Example:
            @app.scheduled("5m")
            async def cleanup():
                await remove_expired_sessions()
        """

        def decorator(func):
            self._registry.register_handler(
                name=f"scheduled_{func.__name__}",
                func=func,
                description=f"Scheduled handler ({interval})",
                metadata={
                    "interval": interval,
                    "cron": cron,
                    "channel": "scheduler",
                    "interval_seconds": self._parse_interval(interval),
                },
            )
            return func

        return decorator

    def emit(self, event_type: str, data: dict = None) -> None:
        """Emit a custom event to the EventBus.

        Non-blocking. The event is delivered to all subscribers
        including @app.on_event() handlers (once the EventTransport
        is implemented).

        Args:
            event_type: Event type string.
            data: Optional event data dict.
        """
        event = NexusEvent(
            event_type=NexusEventType.CUSTOM,
            data={"type": event_type, **(data or {})},
        )
        self._event_bus.publish(event)

    def run_in_background(self, coro) -> asyncio.Task:
        """Run a coroutine as a background task.

        Uses asyncio.create_task() -- truly concurrent and decoupled from
        any HTTP request lifecycle. Task errors are logged, not propagated.

        Args:
            coro: An awaitable coroutine.

        Returns:
            The asyncio.Task (can be cancelled via task.cancel()).
        """

        async def _safe_wrapper():
            try:
                await coro
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"Background task failed: {e}", exc_info=True)

        task = asyncio.create_task(_safe_wrapper())
        return task

    @staticmethod
    def _parse_interval(interval: str) -> int:
        """Parse interval string to seconds.

        Args:
            interval: Human-readable interval ("30s", "5m", "2h", "1d").

        Returns:
            Interval in seconds.

        Raises:
            ValueError: If interval format is invalid.
        """
        units = {"s": 1, "m": 60, "h": 3600, "d": 86400}
        if not interval:
            raise ValueError("Empty interval string")
        unit = interval[-1].lower()
        if unit not in units:
            raise ValueError(f"Invalid interval unit '{unit}'. Use s, m, h, or d.")
        try:
            value = int(interval[:-1])
        except ValueError:
            raise ValueError(f"Invalid interval value: {interval}")
        if value <= 0:
            raise ValueError(f"Interval must be positive: {interval}")
        return value * units[unit]

    async def _execute_workflow(
        self, workflow_name: str, inputs: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute a registered workflow with given inputs.

        Helper method for custom endpoints to call workflows internally.
        Includes input validation and sanitization for security.

        Args:
            workflow_name: Name of registered workflow
            inputs: Input data for workflow

        Returns:
            Workflow execution results

        Raises:
            HTTPException: If workflow not found, input invalid, or execution fails
        """
        from fastapi import HTTPException

        from nexus.validation import validate_workflow_inputs, validate_workflow_name

        # P0-5: Validate workflow name (prevent path traversal)
        try:
            validate_workflow_name(workflow_name)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid workflow name.")

        # Check workflow exists
        if workflow_name not in self._workflows:
            raise HTTPException(
                status_code=404, detail=f"Workflow '{workflow_name}' not found"
            )

        # P0-5: Validate inputs using unified validator (size, dangerous keys, etc.)
        try:
            # Use default max size or custom if configured
            max_size = getattr(self, "_max_input_size", 10 * 1024 * 1024)
            inputs = validate_workflow_inputs(inputs, max_size=max_size)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid workflow inputs.")

        # Execute workflow via gateway
        try:
            # Get the workflow
            workflow = self._workflows[workflow_name]

            # Execute using runtime (consistent with SDK patterns)
            from kailash.runtime import get_runtime

            runtime = get_runtime("async")
            execution_result = await runtime.execute_workflow_async(workflow, inputs)
            if isinstance(execution_result, tuple):
                results, run_id = execution_result
            else:
                results = execution_result
                run_id = None

            return results
        except HTTPException:
            # Re-raise HTTP exceptions as-is
            raise
        except Exception as e:
            logger.error(f"Workflow execution failed for '{workflow_name}': {e}")
            raise HTTPException(status_code=500, detail="Workflow execution failed")

    def _run_gateway(self):
        """Run gateway in thread with error handling."""
        try:
            self._http_transport.run_blocking(host="0.0.0.0")
        except Exception as e:
            logger.warning(
                f"Gateway channel error: {e}. Continuing with other channels."
            )

    def _run_mcp_server(self):
        """Run MCP server in thread."""
        try:
            import asyncio

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            # Use MCP channel if available (full protocol support)
            if hasattr(self, "_mcp_channel") and self._mcp_channel:
                loop.run_until_complete(self._mcp_channel.start())
            elif hasattr(self, "_mcp_server") and self._mcp_server:
                # Core SDK MCPServer -- start if it has start()
                if hasattr(self._mcp_server, "start"):
                    loop.run_until_complete(self._mcp_server.start())
                else:
                    logger.warning("MCP server has no start() method, skipping")
            else:
                logger.info("No MCP server configured. Use kailash-mcp for MCP access.")
                return

            loop.run_forever()
        except Exception as e:
            logger.warning(f"MCP server error: {e}. Continuing with other channels.")

    def start(self):
        """Start the Nexus platform using the enterprise gateway.

        Zero-configuration startup that leverages the SDK's enterprise server
        with built-in multi-channel support (API, CLI, MCP).

        This method blocks until the server is stopped (Ctrl+C or .stop() call).
        """
        if self._running:
            logger.warning("Nexus is already running")
            return

        if not self._http_transport.gateway:
            raise RuntimeError("Enterprise gateway not initialized")

        logger.info("🚀 Starting Kailash Nexus - Zero-Config Workflow Platform")

        # Auto-discover workflows if enabled
        if self._auto_discovery_enabled:
            logger.info("🔍 Auto-discovering workflows...")
            self._auto_discover_workflows()

        # Start MCP server in background thread
        if hasattr(self, "_mcp_server"):
            self._mcp_thread = threading.Thread(
                target=self._run_mcp_server, daemon=True
            )
            self._mcp_thread.start()

        self._running = True

        # Call plugin startup hooks
        self._call_startup_hooks()

        # Log successful startup
        self._log_startup_success()

        # Run gateway in main thread (blocking) via HTTPTransport
        logger.info("Press Ctrl+C to stop the server")
        try:
            self._http_transport.run_blocking(host="0.0.0.0")
        except KeyboardInterrupt:
            logger.info("\n⏹️  Shutting down Nexus...")
            self.stop()
            logger.info("✅ Nexus stopped successfully")
        except Exception as e:
            logger.error(f"Gateway error: {e}")
            self.stop()
            raise RuntimeError(f"Nexus failed: {e}")

    def _log_startup_success(self):
        """Log successful startup with enterprise capabilities."""
        logger.info("✅ Nexus Platform Started Successfully!")
        logger.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        logger.info("🏗️  ENTERPRISE ARCHITECTURE ACTIVE:")
        logger.info("   📡 API Server: REST + WebSocket + OpenAPI docs")
        logger.info("   💻 CLI Interface: Interactive commands")
        logger.info("   🤖 MCP Protocol: AI agent tools")
        logger.info("   🔄 Multi-Channel: Unified workflow access")
        logger.info("")
        logger.info("📊 PLATFORM STATUS:")
        logger.info(f"   Workflows: {len(self._workflows)} registered")
        logger.info(f"   API Port: {self._api_port}")
        logger.info("   Server Type: Enterprise (production-ready)")
        logger.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    def close(self):
        """Release MCP servers and the shared runtime.

        Closes child servers first (they hold acquired references to the
        runtime), then releases the Nexus-level runtime reference.
        Idempotent: safe to call multiple times.
        """
        # Close MCP servers first — they hold acquired runtime refs
        for attr in ("_mcp_server", "_ws_server"):
            server = getattr(self, attr, None)
            if server is not None and hasattr(server, "close"):
                try:
                    server.close()
                except Exception:
                    pass

        # Release or close the runtime itself
        if hasattr(self, "runtime") and self.runtime is not None:
            self.runtime.release()
            self.runtime = None

    def __del__(self, _warnings=warnings):
        if getattr(self, "runtime", None) is not None:
            _warnings.warn(
                f"Unclosed {self.__class__.__name__}. Call close() explicitly.",
                ResourceWarning,
                source=self,
            )
            try:
                self.close()
            except Exception:
                pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def stop(self):
        """Stop the Nexus server gracefully."""
        if not self._running:
            self.close()
            return

        logger.info("Stopping Nexus...")

        # Call plugin shutdown hooks (reverse order)
        self._call_shutdown_hooks()

        # Gateway cleanup is handled automatically by FastAPI's lifespan context manager
        # The lifespan shuts down the executor when uvicorn stops
        # No explicit .stop() method exists on EnterpriseWorkflowServer
        if self._http_transport.gateway:
            logger.debug("Gateway shutdown handled by FastAPI lifespan")

        # Stop MCP channel/server if running
        if hasattr(self, "_mcp_channel") and self._mcp_channel:
            try:
                # MCP channel needs to be stopped in its event loop
                import asyncio

                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(self._mcp_channel.stop())
                loop.close()
            except Exception as e:
                logger.warning(
                    f"Error stopping MCP channel during shutdown: {type(e).__name__}: {e}"
                )
        elif hasattr(self, "_ws_server") and self._ws_server:
            try:
                # Stop WebSocket server
                import asyncio

                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(self._ws_server.stop())
                loop.close()
            except Exception as e:
                logger.warning(
                    f"Error stopping WebSocket server during shutdown: {type(e).__name__}: {e}"
                )
        elif hasattr(self, "_mcp_server"):
            try:
                # Fallback: stop simple server
                import asyncio

                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                if hasattr(self._mcp_server, "stop"):
                    loop.run_until_complete(self._mcp_server.stop())
                loop.close()
            except Exception as e:
                logger.warning(
                    f"Error stopping MCP server during shutdown: {type(e).__name__}: {e}"
                )

        self._running = False

        # Release shared runtime (M3-001)
        self.close()

        logger.info("Nexus stopped")

    def _auto_discover_workflows(self):
        """Auto-discover workflows in the current directory."""
        from .discovery import discover_workflows

        logger.info("Auto-discovering workflows...")
        discovered = discover_workflows()

        for name, workflow in discovered.items():
            if name not in self._workflows:
                self.register(name, workflow)
                logger.info(f"Auto-registered workflow: {name}")

    def health_check(self) -> Dict[str, Any]:
        """Get health status of the Nexus platform."""
        base_status = {
            "status": "healthy" if self._running else "stopped",
            "platform_type": "zero-config-workflow",
            "server_type": "enterprise",
            "workflows": len(self._workflows),
            "api_port": self._api_port,
            "enterprise_features": {
                "durability": True,
                "resource_management": True,
                "async_execution": True,
                "multi_channel": True,
                "health_monitoring": True,
            },
            "version": "nexus-v1.0",
        }

        # Add enterprise gateway health if available
        gw = self._http_transport.gateway
        if gw and hasattr(gw, "health_check"):
            try:
                gateway_health = gw.health_check()
                base_status["gateway_health"] = gateway_health
            except Exception:
                logger.exception("Gateway health check failed")
                base_status["gateway_health"] = {"status": "error"}

        # Add HTTP transport health
        base_status["http_transport"] = self._http_transport.health_check()

        # Add background service health if any are registered
        if self._background_services:
            background_health = {}
            for svc in self._background_services:
                try:
                    background_health[svc.name] = svc.is_healthy()
                except Exception:
                    background_health[svc.name] = False
            base_status["background_services"] = background_health

        return base_status

    # Progressive enhancement methods

    def enable_auth(self):
        """Enable authentication using SDK's enterprise auth capabilities."""
        gw = self._http_transport.gateway
        if gw and hasattr(gw, "enable_auth"):
            try:
                gw.enable_auth()
                logger.info("Authentication enabled via enterprise gateway")
            except Exception as e:
                logger.error(f"Failed to enable authentication: {e}")
        return self.use_plugin("auth")  # Fallback to plugin

    def enable_monitoring(self):
        """Enable monitoring using SDK's enterprise monitoring capabilities."""
        gw = self._http_transport.gateway
        if gw and hasattr(gw, "enable_monitoring"):
            try:
                gw.enable_monitoring()
                logger.info("Monitoring enabled via enterprise gateway")
            except Exception as e:
                logger.error(f"Failed to enable monitoring: {e}")
        return self.use_plugin("monitoring")  # Fallback to plugin

    def use_plugin(self, plugin_name: str):
        """Load and apply a plugin for additional features."""
        from .plugins import get_plugin_registry

        registry = get_plugin_registry()
        registry.apply(plugin_name, self)
        return self  # For chaining

    # Revolutionary Capabilities Implementation

    def create_session(self, session_id: str = None, channel: str = "api") -> str:
        """Create cross-channel synchronized session (Revolutionary Capability #3).

        Args:
            session_id: Optional session ID (auto-generated if None)
            channel: Channel creating the session

        Returns:
            Session ID for cross-channel use
        """
        import time
        import uuid

        if not session_id:
            session_id = str(uuid.uuid4())

        sync_start = time.time()

        # Initialize session manager if needed
        if not self._session_manager:
            from .channels import create_session_manager

            self._session_manager = create_session_manager()

        # Create session with cross-channel capability
        session = self._session_manager.create_session(session_id, channel)

        # Track sync performance (target: <50ms)
        sync_time = time.time() - sync_start
        self._performance_metrics["session_sync_latency"].append(sync_time)

        logger.info(
            f"Cross-channel session created: {session_id} by {channel} ({sync_time:.3f}s)"
        )
        return session_id

    def sync_session(self, session_id: str, channel: str) -> dict:
        """Sync session across channels (Revolutionary Capability #3).

        Args:
            session_id: Session to sync
            channel: Channel requesting sync

        Returns:
            Session data accessible across all channels
        """
        import time

        sync_start = time.time()

        if not self._session_manager:
            return {"error": "Session manager not initialized"}

        session_data = self._session_manager.sync_session(session_id, channel)

        # Track sync performance (target: <50ms)
        sync_time = time.time() - sync_start
        self._performance_metrics["cross_channel_sync_time"].append(sync_time)

        if session_data:
            logger.info(
                f"Session synced: {session_id} for {channel} ({sync_time:.3f}s)"
            )
            return session_data
        else:
            logger.warning(f"Session sync failed: {session_id} for {channel}")
            return {"error": "Session not found"}

    def broadcast_event(self, event_type: str, data: dict, session_id: str = None):
        """Broadcast an event via the EventBus.

        Events are stored in a bounded history (256 most recent) and
        dispatched to any active subscribers.

        Args:
            event_type: Type of event (WORKFLOW_STARTED, COMPLETED, etc.)
            data: Event data
            session_id: Optional session to associate event with

        Returns:
            Event dict (legacy format for backward compatibility)

        Example:
            >>> event = app.broadcast_event("WORKFLOW_STARTED", {
            ...     "workflow": "data_pipeline",
            ...     "execution_id": "run_123"
            ... })
        """
        if session_id:
            data = {**data, "session_id": session_id}
        event = NexusEvent(
            event_type=NexusEventType.CUSTOM,
            data={"type": event_type, **data, "session_id": session_id},
        )
        self._event_bus.publish(event)

        # Return legacy dict format for backward compatibility
        return {
            "id": f"evt_{int(event.timestamp.timestamp() * 1000)}",
            "type": event_type,
            "timestamp": event.timestamp.isoformat(),
            "data": data,
            "session_id": session_id,
        }

    def get_events(
        self, session_id: str = None, event_type: str = None, limit: int = None
    ) -> List[dict]:
        """Retrieve recent events from the EventBus history.

        Returns at most the 256 most recent events (bounded buffer).

        Args:
            session_id: Filter by session ID
            event_type: Filter by event type
            limit: Maximum number of events to return (most recent first)

        Returns:
            List of matching events

        Example:
            >>> # Get all events
            >>> events = app.get_events()

            >>> # Get events for specific session
            >>> session_events = app.get_events(session_id="session_123")

            >>> # Get specific event type
            >>> workflow_events = app.get_events(event_type="WORKFLOW_COMPLETED")

            >>> # Get last 10 events
            >>> recent_events = app.get_events(limit=10)
        """
        return self._event_bus.get_history(
            session_id=session_id, event_type=event_type, limit=limit
        )

    def get_performance_metrics(self) -> dict:
        """Get revolutionary performance metrics for validation.

        Returns:
            Performance metrics showing competitive advantages
        """
        metrics = {}

        for metric_name, values in self._performance_metrics.items():
            if values:
                metrics[metric_name] = {
                    "average": sum(values) / len(values),
                    "latest": values[-1],
                    "count": len(values),
                    "target_met": self._check_performance_target(
                        metric_name, values[-1]
                    ),
                }
            else:
                metrics[metric_name] = {
                    "average": 0,
                    "latest": 0,
                    "count": 0,
                    "target_met": True,
                }

        return metrics

    def _check_performance_target(self, metric_name: str, value: float) -> bool:
        """Check if performance value meets revolutionary targets."""
        targets = {
            "workflow_registration_time": 1.0,  # <1 second
            "cross_channel_sync_time": 0.05,  # <50ms
            "failure_recovery_time": 5.0,  # <5 seconds
            "session_sync_latency": 0.05,  # <50ms
        }

        target = targets.get(metric_name, float("inf"))
        return value < target

    def get_channel_status(self) -> dict:
        """Get status of all channels for revolutionary validation.

        Returns:
            Channel status showing multi-channel orchestration
        """
        status = {}

        for channel, data in self._channel_registry.items():
            status[channel] = {
                "status": data["status"],
                "registered_workflows": len(
                    data.get("routes", data.get("commands", data.get("tools", {})))
                ),
                "capability": self._get_channel_capability(channel),
            }

        return status

    def _get_channel_capability(self, channel: str) -> str:
        """Get channel-specific capability description."""
        capabilities = {
            "api": "REST endpoints + WebSocket streaming + OpenAPI docs",
            "cli": "Interactive commands + auto-completion + progress updates",
            "mcp": "AI agent tools + resource discovery + real MCP execution",
        }
        return capabilities.get(channel, "Unknown capability")


# Legacy function for backwards compatibility
def create_nexus(**kwargs) -> Nexus:
    """Legacy function - use Nexus() directly instead.

    This function is deprecated. Use:
        app = Nexus(enable_auth=True, api_port=8000)
    Instead of:
        app = create_nexus(enable_auth=True, api_port=8000)
    """
    import warnings

    warnings.warn(
        "create_nexus() is deprecated. Use Nexus() directly: app = Nexus()",
        DeprecationWarning,
        stacklevel=2,
    )
    return Nexus(**kwargs)

"""Multi-workflow API gateway for managing multiple Kailash workflows.

This module provides a unified API server that can host multiple workflows
with dynamic routing, MCP integration, and centralized management.

Design Philosophy:
    The gateway acts as a single entry point for all workflow executions,
    providing unified authentication, monitoring, and resource management.
    It supports both embedded workflows (running in-process) and proxied
    workflows (running in separate processes).

Example:
    >>> # Basic usage with multiple workflows
    >>> from kailash.api import WorkflowAPIGateway
    >>> from kailash.workflow import Workflow

    >>> # Create workflows
    >>> sales_workflow = Workflow("sales_pipeline")
    >>> analytics_workflow = Workflow("analytics_pipeline")

    >>> # Create gateway
    >>> gateway = WorkflowAPIGateway(
    ...     title="Company API Gateway",
    ...     description="Unified API for all workflows"
    ... )

    >>> # Register workflows
    >>> gateway.register_workflow("sales", sales_workflow)
    >>> gateway.register_workflow("analytics", analytics_workflow)

    >>> # Start server
    >>> gateway.execute(port=8000)  # doctest: +SKIP

    >>> # With MCP integration
    >>> from kailash.api.mcp_integration import MCPIntegration

    >>> # Add MCP server
    >>> mcp = MCPIntegration("tools_server")
    >>> gateway.register_mcp_server("tools", mcp)

    >>> # With proxied workflows
    >>> # Proxy registration is FAIL-CLOSED since issue #2025: it raises
    >>> # unless an authentication control and an explicit path allowlist
    >>> # are supplied. `allowed_methods` defaults to ["GET"].
    >>> from kailash.middleware.auth import MiddlewareAuthManager
    >>> gateway = WorkflowAPIGateway(
    ...     auth_manager=MiddlewareAuthManager(secret_key=...),
    ... )
    >>> gateway.proxy_workflow(
    ...     "ml_pipeline",
    ...     "http://ml-service:8080",
    ...     health_check="/health",
    ...     allowed_paths=["predict", "status"],
    ... )
"""

import asyncio
import json
import logging
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from typing import Any, Callable

# `httpx`, `fastapi`, and `starlette` are OPTIONAL dependencies under the
# `server` extra (pyproject.toml:55-67), not in slim-core dependencies. Per
# `rules/dependencies.md` § "Declared = Imported" / "BLOCKED Anti-Patterns",
# optional-extra imports MUST raise loudly with an actionable error message
# naming the extra — bare `ModuleNotFoundError` leaves a clean-install user
# with no signal that `kailash[server]` is the correct install. Bundled into
# one try/except since the entire gateway module is server-extra-only;
# failure to import any one of them makes WorkflowAPIGateway unusable.
# `pydantic` is in slim-core dependencies (pyproject.toml:25) so it stays
# unguarded.
try:
    import httpx
    from fastapi import Depends, FastAPI
    from starlette.middleware.cors import CORSMiddleware
    from starlette.requests import Request
    from starlette.responses import Response, StreamingResponse
    from starlette.websockets import WebSocket
except ImportError as exc:  # pragma: no cover — covered by structural invariant test
    raise ImportError(
        "kailash.api.gateway requires server dependencies (httpx, fastapi, "
        "starlette). Install with: pip install 'kailash[server]'"
    ) from exc

from pydantic import BaseModel, Field

from ..runtime.local import LocalRuntime
from ..utils.http_errors import safe_http_detail
from ..utils.lifespan import (
    drive_router_lifespan_shutdown,
    drive_router_lifespan_startup,
)
from ..utils.proxy_guard import PROXY_CREDENTIAL_HEADERS as _PROXY_CREDENTIAL_HEADERS
from ..utils.proxy_guard import (
    PROXY_HOP_BY_HOP_HEADERS,
    PROXY_SAFE_RESPONSE_HEADERS,
    SAFE_FORWARD_PATH_RE,
    PathPattern,
    compile_path_allowlist,
    normalize_allowed_methods,
    path_matches_allowlist,
    reject_unsafe_proxy_path,
    resolve_proxy_auth_dependency,
)
from ..utils.server_auth import (
    install_server_auth_middleware,
    resolve_server_auth,
)
from ..workflow import Workflow
from .workflow_api import WorkflowAPI

logger = logging.getLogger(__name__)


class WorkflowRegistration(BaseModel):
    """Registration details for a workflow."""

    model_config = {"arbitrary_types_allowed": True}

    name: str
    type: str = Field(description="embedded or proxied")
    workflow: Workflow | None = None
    proxy_url: str | None = None
    health_check: str | None = None
    description: str | None = None
    version: str = "1.0.0"
    tags: list[str] = Field(default_factory=list)


class WorkflowAPIGateway:
    """Unified API gateway for multiple Kailash workflows.

    This gateway provides:
    - Dynamic workflow registration
    - Unified routing with prefix-based paths
    - MCP server integration
    - Health monitoring
    - Resource management
    - WebSocket support for real-time updates

    Attributes:
        app: FastAPI application instance
        workflows: Registry of all registered workflows
        executor: Thread pool for synchronous execution
        mcp_servers: Registry of MCP servers
    """

    def __init__(
        self,
        title: str = "Kailash Workflow Gateway",
        description: str = "Unified API for Kailash workflows",
        version: str = "1.0.0",
        max_workers: int = 10,
        cors_origins: list[str] | None = None,
        auth_manager: Any = None,
        # Server-wide authentication (#2072). NAMED, never **kwargs -- see the
        # WorkflowServer counterpart for why. This gateway is an INDEPENDENT
        # surface with the same defect, so per security.md § Enforcement-Surface
        # Parity it learns the gate in the SAME change, through the SAME shared
        # implementation (kailash.utils.server_auth).
        require_auth: bool = True,
        auth_config: Any = None,
        external_auth_reason: str | None = None,
        auth_exempt_paths: list[str] | None = None,
    ):
        """Initialize the API gateway.

        Args:
            title: API title for documentation
            description: API description
            version: API version
            max_workers: Maximum thread pool workers
            cors_origins: Allowed CORS origins
            auth_manager: Optional authentication manager used to protect
                routes that require it. Must expose
                ``get_current_user_dependency()`` returning a FastAPI
                dependency;
                :class:`kailash.middleware.auth.MiddlewareAuthManager` is the
                shipped implementation. :meth:`proxy_workflow` refuses to
                register a route unless this (or a per-registration
                ``auth_dependency``) is present -- see issue #2025 and
                :mod:`kailash.utils.proxy_guard`. Can also be supplied after
                construction via :meth:`set_auth_manager`.

                NOTE: ``auth_manager`` does NOT satisfy ``require_auth`` -- it
                supplies a FastAPI ``Depends``, which does not run for routes
                inside a mounted sub-application (#2072).
            require_auth: Whether every request must be authenticated.
                **Defaults to ``True`` (fail-closed); BREAKING.** Construction
                raises
                :class:`~kailash.utils.server_auth.ServerAuthNotConfiguredError`
                when no credential source is configured. See
                :mod:`kailash.utils.server_auth`.
            auth_config: Explicit ``JWTConfig`` (or field ``dict``).
            external_auth_reason: Non-empty string declaring that an ASGI
                middleware outside this gateway authenticates every request.
            auth_exempt_paths: Extra paths exempt from authentication.
        """
        # Resolve authentication FIRST (#2072), before the ThreadPoolExecutor
        # below is allocated -- a raise afterwards would leak its threads.
        self._auth_config = resolve_server_auth(
            require_auth=require_auth,
            auth_config=auth_config,
            external_auth_reason=external_auth_reason,
            extra_exempt_paths=auth_exempt_paths,
            server_label=f"{type(self).__name__}(title={title!r})",
        )

        self.workflows: dict[str, WorkflowRegistration] = {}
        self.mcp_servers: dict[str, Any] = {}

        # Authentication wiring for proxy routes (issue #2025). This gateway is
        # an INDEPENDENT surface from kailash.servers.WorkflowServer with the
        # same defect, so it learns the same gate through the same shared
        # guard module (security.md, Enforcement-Surface Parity).
        self._auth_manager: Any = auth_manager
        self._external_auth_reason: str | None = (
            external_auth_reason.strip()
            if external_auth_reason and external_auth_reason.strip()
            else None
        )
        # Per-workflow API wrappers, tracked so their runtimes are released on
        # shutdown/close() (issue #1285 — each WorkflowAPI builds its own
        # AsyncLocalRuntime that otherwise leaks at GC).
        self._workflow_apis: dict[str, "WorkflowAPI"] = {}
        self.executor = ThreadPoolExecutor(max_workers=max_workers)

        # Proxy HTTP client (created lazily on first proxied request)
        self._proxy_client: httpx.AsyncClient | None = None

        # WebSocket subscription queues: workflow_name -> set of asyncio.Queue
        self._ws_subscriptions: dict[str, set[asyncio.Queue]] = defaultdict(set)

        # Round-robin counters for proxy backends
        self._proxy_round_robin: dict[str, int] = {}

        # Create FastAPI app with lifespan
        @asynccontextmanager
        async def lifespan(app: FastAPI):
            # Startup
            logger.info(f"Starting {title} v{version}")
            # S2 (#712): drive router.on_startup hooks (e.g. consumer
            # @app.on_event("startup")). Custom lifespan replaces Starlette's
            # _DefaultLifespan; without this iteration consumer hooks
            # silently drop (the #500 bug class).
            await drive_router_lifespan_startup(app)
            yield
            # Shutdown
            logger.info("Shutting down gateway")
            await drive_router_lifespan_shutdown(app)
            if self._proxy_client:
                await self._proxy_client.aclose()
            self._close_workflow_apis()
            self.executor.shutdown(wait=True)

        self.app = FastAPI(
            title=title, description=description, version=version, lifespan=lifespan
        )

        # Install authentication BEFORE CORS (#2072). Starlette's
        # add_middleware() PREPENDS, so the LAST layer added is the OUTERMOST
        # one; auth added after CORS would sit inside it and 401 cross-origin
        # preflight OPTIONS before CORS could answer (the PR #2054 ordering
        # bug). Middleware and not a Depends, because register_workflow
        # app.mount()s a sub-application that route dependencies never reach.
        if self._auth_config is not None:
            install_server_auth_middleware(self.app, self._auth_config)

        # Add CORS middleware
        if cors_origins:
            # Credentials are allowed ONLY when the origins are named
            # explicitly. With `allow_origins=["*"]` plus
            # `allow_credentials=True`, any web page can drive this gateway --
            # including the now-authenticated proxy routes -- using the
            # victim's cookies, which turns cookie auth into a cross-origin
            # invocable surface. WorkflowServer already guarded this; the two
            # surfaces disagreeing on it is the same drift class as the
            # credential-stripping and redirect-policy divergences #2025 fixed.
            allow_creds = "*" not in cors_origins
            self.app.add_middleware(
                CORSMiddleware,
                allow_origins=cors_origins,
                allow_credentials=allow_creds,
                allow_methods=["*"],
                allow_headers=["*"],
            )

        # Register root endpoints
        self._register_root_endpoints()

    async def _get_proxy_client(self) -> httpx.AsyncClient:
        """Get or create the shared async HTTP client for proxying."""
        if self._proxy_client is None or self._proxy_client.is_closed:
            # follow_redirects is stated EXPLICITLY rather than inherited.
            # httpx happens to default it to False today, but the invariant
            # this proxy depends on must not rest on a library default that
            # can change under us -- and the sibling surface uses aiohttp,
            # which defaults the same knob to True. Every control the proxy
            # route enforces (auth gate, path allowlist, traversal rejection,
            # charset barrier) applies to hop 1 only, so a followed redirect
            # is an authority pivot past all of them.
            self._proxy_client = httpx.AsyncClient(timeout=30.0, follow_redirects=False)
        return self._proxy_client

    async def _check_proxy_health(self, reg: WorkflowRegistration) -> str:
        """Check health of a proxied workflow backend via HTTP GET.

        Args:
            reg: Workflow registration with proxy_url and health_check path

        Returns:
            "healthy", "unhealthy", or "unreachable"
        """
        if not reg.proxy_url:
            return "unknown"

        health_path = reg.health_check or "/health"
        url = reg.proxy_url.rstrip("/") + health_path

        try:
            client = await self._get_proxy_client()
            resp = await client.get(url, timeout=5.0)
            if resp.status_code == 200:
                return "healthy"
            return "unhealthy"
        except Exception as exc:
            logger.warning(f"Proxy health check failed for {reg.name}: {exc}")
            return "unreachable"

    async def _check_mcp_health(self, name: str, server: Any) -> str:
        """Check health of an MCP server.

        If the server object exposes a ping() or health() coroutine, call it.
        Otherwise return 'unknown'.
        """
        try:
            if hasattr(server, "ping"):
                result = server.ping()
                if asyncio.iscoroutine(result):
                    result = await result
                return "healthy" if result else "unhealthy"
            if hasattr(server, "health"):
                result = server.health()
                if asyncio.iscoroutine(result):
                    result = await result
                return "healthy" if result else "unhealthy"
        except Exception as exc:
            logger.warning(f"MCP health check failed for {name}: {exc}")
            return "unhealthy"
        return "unknown"

    def _close_workflow_apis(self) -> None:
        """Release per-workflow API runtimes (issue #1285). Idempotent."""
        for name, workflow_api in getattr(self, "_workflow_apis", {}).items():
            try:
                workflow_api.close()
            except Exception as exc:  # pragma: no cover - teardown best-effort
                logger.debug(
                    "Error closing WorkflowAPI for '%s': %s: %s",
                    name,
                    type(exc).__name__,
                    exc,
                )
        self._workflow_apis = {}

    def close(self) -> None:
        """Synchronously release per-workflow API runtimes (issue #1285).

        The async lifespan shutdown also performs this release; ``close()`` is
        the teardown path for a gateway constructed but never served.
        """
        self._close_workflow_apis()

    def _register_root_endpoints(self):
        """Register gateway-level endpoints."""

        @self.app.get("/")
        async def root():
            """Gateway information."""
            return {
                "name": self.app.title,
                "version": self.app.version,
                "workflows": list(self.workflows.keys()),
                "mcp_servers": list(self.mcp_servers.keys()),
            }

        @self.app.get("/workflows")
        async def list_workflows():
            """List all registered workflows."""
            return {
                name: {
                    "type": reg.type,
                    "description": reg.description,
                    "version": reg.version,
                    "tags": reg.tags,
                    "endpoints": self._get_workflow_endpoints(name),
                }
                for name, reg in self.workflows.items()
            }

        @self.app.get("/health")
        async def health_check():
            """Gateway health check with real backend probing."""
            health_status = {"status": "healthy", "workflows": {}, "mcp_servers": {}}

            # Check workflow health
            for name, reg in self.workflows.items():
                if reg.type == "embedded":
                    health_status["workflows"][name] = "healthy"
                else:
                    health_status["workflows"][name] = await self._check_proxy_health(
                        reg
                    )

            # Check MCP server health
            for name, server in self.mcp_servers.items():
                health_status["mcp_servers"][name] = await self._check_mcp_health(
                    name, server
                )

            # Overall status degrades if any component is unhealthy
            all_wf = list(health_status["workflows"].values())
            all_mcp = list(health_status["mcp_servers"].values())
            if "unhealthy" in all_wf or "unreachable" in all_wf:
                health_status["status"] = "degraded"
            if "unhealthy" in all_mcp:
                health_status["status"] = "degraded"

            return health_status

        @self.app.websocket("/ws")
        async def websocket_endpoint(websocket: WebSocket):
            """WebSocket for real-time workflow event updates via SSE-like push."""
            await websocket.accept()
            queue: asyncio.Queue = asyncio.Queue()
            subscribed_workflows: set[str] = set()

            async def _sender():
                """Push events from queue to websocket."""
                try:
                    while True:
                        event = await queue.get()
                        await websocket.send_json(event)
                except asyncio.CancelledError:
                    pass

            sender_task = asyncio.create_task(_sender())

            try:
                while True:
                    data = await websocket.receive_json()
                    msg_type = data.get("type")

                    if msg_type == "subscribe":
                        wf_name = data.get("workflow")
                        if wf_name and wf_name in self.workflows:
                            self._ws_subscriptions[wf_name].add(queue)
                            subscribed_workflows.add(wf_name)
                            await websocket.send_json(
                                {
                                    "type": "subscribed",
                                    "workflow": wf_name,
                                    "message": f"Subscribed to {wf_name}",
                                }
                            )
                        else:
                            await websocket.send_json(
                                {
                                    "type": "error",
                                    "message": f"Workflow '{wf_name}' not found",
                                }
                            )

                    elif msg_type == "unsubscribe":
                        wf_name = data.get("workflow")
                        if wf_name in subscribed_workflows:
                            self._ws_subscriptions[wf_name].discard(queue)
                            subscribed_workflows.discard(wf_name)
                            await websocket.send_json(
                                {
                                    "type": "unsubscribed",
                                    "workflow": wf_name,
                                }
                            )
                    else:
                        await websocket.send_json(
                            {"type": "ack", "message": "Message received"}
                        )

            except Exception as e:
                logger.error(f"WebSocket error: {e}")
            finally:
                sender_task.cancel()
                for wf_name in subscribed_workflows:
                    self._ws_subscriptions[wf_name].discard(queue)
                try:
                    await websocket.close()
                except Exception as exc:
                    # Cleanup path -- the peer has usually already gone away,
                    # so a failure here is expected and must not mask the
                    # original error. Logged rather than swallowed silently
                    # so a close that fails for an UNexpected reason is still
                    # visible (zero-tolerance.md Rule 3).
                    logger.debug(
                        "Error closing gateway WebSocket: %s: %s",
                        type(exc).__name__,
                        exc,
                    )

        # ---------- MCP tool REST endpoints ----------
        @self.app.get("/mcp/tools")
        async def list_mcp_tools():
            """List all tools from all registered MCP servers."""
            all_tools = {}
            for name, server in self.mcp_servers.items():
                if hasattr(server, "list_tools"):
                    try:
                        tools = server.list_tools()
                        if asyncio.iscoroutine(tools):
                            tools = await tools
                        all_tools[name] = tools
                    except Exception as exc:
                        # This dict IS the response body -- it is returned
                        # directly below. An MCP server's connection failure
                        # routinely names its transport endpoint or auth
                        # header, so the raw text cannot go to the caller.
                        all_tools[name] = {
                            "error": safe_http_detail(
                                exc,
                                logger=logger,
                                context=f"list tools for MCP server {name!r}",
                            )
                        }
                else:
                    all_tools[name] = {"error": "Server does not support list_tools"}
            return all_tools

        @self.app.post("/mcp/{server_name}/tools/{tool_name}")
        async def call_mcp_tool(server_name: str, tool_name: str, request: Request):
            """Execute an MCP tool via REST.

            Body should contain the tool arguments as JSON.
            """
            if server_name not in self.mcp_servers:
                return Response(
                    content=f'{{"error": "MCP server \'{server_name}\' not found"}}',
                    status_code=404,
                    media_type="application/json",
                )

            server = self.mcp_servers[server_name]
            body = await request.json()

            if hasattr(server, "call_tool"):
                try:
                    result = server.call_tool(tool_name, body)
                    if asyncio.iscoroutine(result):
                        result = await result
                    return {"success": True, "result": result}
                except Exception as exc:
                    logger.error(
                        f"MCP tool '{tool_name}' on server '{server_name}' failed: {exc}"
                    )
                    return Response(
                        content='{"error": "Tool execution failed"}',
                        status_code=500,
                        media_type="application/json",
                    )
            return Response(
                content='{"error": "Server does not support call_tool"}',
                status_code=501,
                media_type="application/json",
            )

    def register_workflow(
        self,
        name: str,
        workflow: Workflow,
        description: str | None = None,
        version: str = "1.0.0",
        tags: list[str] | None = None,
        **kwargs,
    ):
        """Register an embedded workflow.

        Args:
            name: Unique workflow identifier
            workflow: Workflow instance
            description: Workflow description
            version: Workflow version
            tags: Workflow tags for organization
            **kwargs: Additional WorkflowAPI parameters
        """
        if name in self.workflows:
            raise ValueError(f"Workflow '{name}' already registered")

        # Create WorkflowAPI wrapper
        workflow_api = WorkflowAPI(
            workflow=workflow,
            app_name=f"{name} Workflow API",
            version=version,
            description=description or f"Workflow: {name}",
        )
        # Track it so its runtime is released on shutdown/close() (issue #1285).
        self._workflow_apis[name] = workflow_api

        # Mount the workflow app as a sub-application
        self.app.mount(f"/{name}", workflow_api.app)

        # Register workflow
        self.workflows[name] = WorkflowRegistration(
            name=name,
            type="embedded",
            workflow=workflow,
            description=description or workflow.name,
            version=version,
            tags=tags or [],
        )

        logger.info(f"Registered embedded workflow: {name}")

    def set_auth_manager(self, auth_manager: Any) -> None:
        """Attach an authentication manager to this gateway.

        Mirrors :meth:`kailash.servers.WorkflowServer.set_auth_manager` --
        both surfaces consume the same shared guard (issue #2025). The manager
        must expose ``get_current_user_dependency()``;
        :class:`kailash.middleware.auth.MiddlewareAuthManager` is the shipped
        implementation.

        Call this **before** :meth:`proxy_workflow`; FastAPI resolves route
        dependencies at registration time, so routes already registered are
        unaffected.

        Args:
            auth_manager: The authentication manager.

        Raises:
            ValueError: If ``auth_manager`` is None -- clearing it would
                silently widen every subsequent registration.
        """
        if auth_manager is None:
            raise ValueError(
                "set_auth_manager(None) is not allowed. Construct the gateway "
                "without auth_manager= if it should have no authentication "
                "manager; clearing one after the fact would silently widen "
                "every subsequent proxy registration (issue #2025)."
            )
        self._auth_manager = auth_manager
        logger.info(
            "gateway.auth_manager_set",
            extra={"auth_manager": type(auth_manager).__name__},
        )

    def declare_external_auth(self, reason: str) -> None:
        """Record that an external ASGI middleware authenticates this app.

        Mirrors :meth:`kailash.servers.WorkflowServer.declare_external_auth`.
        This is an explicit, logged acknowledgement that proxy routes carry no
        route-level authentication -- it installs nothing and verifies nothing.

        Args:
            reason: Non-empty description of what authenticates the app.

        Raises:
            ValueError: If ``reason`` is empty or blank.
        """
        if not reason or not reason.strip():
            raise ValueError(
                "declare_external_auth() requires a non-empty reason naming "
                "the middleware that authenticates this app. It is an "
                "acknowledgement that proxy routes carry no route-level "
                "authentication (issue #2025), and an unexplained "
                "acknowledgement is indistinguishable from a mistake."
            )
        self._external_auth_reason = reason.strip()
        logger.warning(
            "gateway.external_auth_declared",
            extra={"reason": self._external_auth_reason},
        )

    def proxy_workflow(
        self,
        name: str,
        proxy_url: str,
        health_check: str = "/health",
        description: str | None = None,
        version: str = "1.0.0",
        tags: list[str] | None = None,
        *,
        allowed_paths: list[PathPattern] | None = None,
        allowed_methods: list[str] | None = None,
        auth_dependency: Callable[..., Any] | None = None,
        forward_credentials: bool = False,
    ):
        """Register a proxied workflow with real request forwarding.

        Incoming requests to /{name}/{path} will be forwarded to
        proxy_url/{path} using round-robin if multiple backends are
        configured (comma-separated in proxy_url).

        Registration is fail-closed (issue #2025): it raises unless the caller
        supplies an authentication control **and** an explicit path allowlist.
        This is the same gate, from the same shared module, that
        :meth:`kailash.servers.WorkflowServer.proxy_workflow` enforces --
        ``security.md`` § Enforcement-Surface Parity requires every
        independent surface with this shape to learn it together.

        Args:
            name: Unique workflow identifier
            proxy_url: URL(s) of the workflow service (comma-separated for multi-backend)
            health_check: Health check endpoint path
            description: Workflow description
            version: Workflow version
            tags: Workflow tags
            allowed_paths: **Required.** Paths beneath ``/{name}/`` that may be
                forwarded. ``"status"`` exactly, ``"api/*"`` as a prefix at any
                depth, ``"*"`` for every path (the pre-#2025 behaviour, now
                explicit), or a compiled ``re.Pattern`` matched with
                ``fullmatch``. A non-matching path gets 404.
            allowed_methods: HTTP methods to forward. Defaults to ``["GET"]``;
                the route is registered only for the methods named here, so
                anything else gets 405. Previously all seven verbs were
                forwarded, including HEAD and OPTIONS.
            auth_dependency: FastAPI dependency protecting the route. When
                omitted, the gateway's ``auth_manager`` supplies one.
            forward_credentials: When False (the default) the caller's
                ``Authorization``, ``Cookie``, ``X-API-Key``,
                ``X-Auth-Token`` and ``Proxy-Authorization`` headers are
                STRIPPED before forwarding. This gateway previously forwarded
                all of them -- it excluded only ``host`` and
                ``content-length`` -- so a caller's credentials were handed to
                whichever round-robin backend was selected. Set True only when
                the backend is trusted and genuinely needs to re-authorize the
                original caller.

        Raises:
            ProxyAuthNotConfiguredError: No authentication control is
                configured for the route.
            ValueError: ``name`` is already registered, or ``allowed_paths`` /
                ``allowed_methods`` is missing or invalid.
        """
        if name in self.workflows:
            raise ValueError(f"Workflow '{name}' already registered")

        # Fail-closed registration guards, BEFORE the workflow is recorded and
        # BEFORE the route is added, so a refused registration leaves no
        # half-registered proxy behind.
        route_auth_dependency = resolve_proxy_auth_dependency(
            name=name,
            surface="WorkflowAPIGateway",
            auth_dependency=auth_dependency,
            auth_manager=self._auth_manager,
            external_auth_reason=self._external_auth_reason,
        )
        path_allowlist = compile_path_allowlist(allowed_paths, name=name)
        methods = normalize_allowed_methods(allowed_methods, name=name)

        # Support multiple backends via comma-separated URLs
        backends = [u.strip() for u in proxy_url.split(",") if u.strip()]
        primary_url = backends[0]

        self.workflows[name] = WorkflowRegistration(
            name=name,
            type="proxied",
            proxy_url=primary_url,
            health_check=health_check,
            description=description,
            version=version,
            tags=tags or [],
        )

        # Store all backends for round-robin
        self._proxy_round_robin[name] = 0

        route_kwargs: dict[str, Any] = {}
        if route_auth_dependency is not None:
            route_kwargs["dependencies"] = [Depends(route_auth_dependency)]

        # Register the forwarding route, constrained to the allowlisted methods
        @self.app.api_route(
            f"/{name}/{{path:path}}",
            methods=methods,
            **route_kwargs,
        )
        async def _proxy_handler(path: str, request: Request):
            """Forward request to backend using round-robin.

            `name`, `backends` and `path_allowlist` are captured from the
            enclosing scope, NOT passed as default arguments. FastAPI treats a
            non-path parameter carrying a plain default as a QUERY parameter,
            so the previous `backends=backends` idiom let a caller redirect
            the forward with `?backends=http://attacker/` -- SSRF. Each
            `proxy_workflow` call has its own scope, so direct capture is
            correct and the late-binding hazard the idiom guards against does
            not apply.
            """
            # Refuse traversal before the target URL is built (issue #2025),
            # rather than relying on the HTTP client's URL normalization.
            unsafe_reason = reject_unsafe_proxy_path(path)
            if unsafe_reason is not None:
                logger.warning(
                    "gateway.proxy.path_rejected",
                    extra={"workflow": name, "reason": unsafe_reason},
                )
                return Response(
                    content=json.dumps(
                        {"error": f"Invalid proxy path: {unsafe_reason}"}
                    ),
                    status_code=400,
                    media_type="application/json",
                )

            if not path_matches_allowlist(path, path_allowlist):
                logger.warning(
                    "gateway.proxy.path_not_allowed", extra={"workflow": name}
                )
                return Response(
                    content=json.dumps({"error": "Not found"}),
                    status_code=404,
                    media_type="application/json",
                )

            # Positive charset barrier. The target URL is built from the
            # MATCHED GROUP, never the raw path parameter, so no byte outside
            # the allowlist can reach the wire whatever the client does with
            # re-encoding.
            safe_path_match = SAFE_FORWARD_PATH_RE.fullmatch(path)
            if safe_path_match is None:
                logger.warning(
                    "gateway.proxy.path_charset_rejected", extra={"workflow": name}
                )
                return Response(
                    content=json.dumps(
                        {
                            "error": "Invalid proxy path: contains a character "
                            "that may not be forwarded"
                        }
                    ),
                    status_code=400,
                    media_type="application/json",
                )
            # `path` is used directly below, NOT `safe_path_match.group(0)`.
            # For a SUCCESSFUL fullmatch those are the same string, so the
            # extraction never sanitized anything -- the safety is entirely in
            # the REJECTION above. Written as an extraction it invited a later
            # `fullmatch` -> `match` edit that looks equivalent and silently
            # forwards a TRUNCATED path ('a b' -> 'a') instead of refusing it.

            idx = self._proxy_round_robin.get(name, 0)
            backend = backends[idx % len(backends)]
            self._proxy_round_robin[name] = idx + 1

            target_url = f"{backend.rstrip('/')}/{path}"

            # Forward headers, stripping the caller's credentials unless the
            # registration explicitly opted in. Before issue #2025 this filter
            # excluded only host/content-length, so Authorization, Cookie and
            # every API-key header were handed to whichever round-robin
            # backend was selected.
            _excluded_headers = {"host", "content-length"}
            _excluded_headers |= PROXY_HOP_BY_HOP_HEADERS
            if not forward_credentials:
                _excluded_headers |= _PROXY_CREDENTIAL_HEADERS
            headers = {
                k: v
                for k, v in request.headers.items()
                if k.lower() not in _excluded_headers
            }

            body = await request.body()

            try:
                client = await self._get_proxy_client()
                resp = await client.request(
                    method=request.method,
                    url=target_url,
                    headers=headers,
                    content=body,
                    # multi_items() preserves repeated keys (?tag=a&tag=b);
                    # dict() silently kept only the last (issue #2025).
                    params=list(request.query_params.multi_items()),
                )
                filtered_headers = {
                    k: v
                    for k, v in resp.headers.items()
                    if k.lower() in PROXY_SAFE_RESPONSE_HEADERS
                }
                return Response(
                    content=resp.content,
                    status_code=resp.status_code,
                    headers=filtered_headers,
                    media_type=resp.headers.get("content-type"),
                )
            except httpx.RequestError as exc:
                # Log the workflow and the registered backend -- both fixed at
                # registration -- not `target_url`, which embeds the caller's
                # path. Interpolating that put caller-controlled text into the
                # log stream (py/log-injection); a forged newline there can
                # fabricate whole log entries for anything reading the file.
                logger.error(
                    "Proxy request for workflow %s to backend %s failed: %s: %s",
                    name,
                    backend,
                    type(exc).__name__,
                    exc,
                )
                return Response(
                    content='{"error": "Backend unreachable"}',
                    status_code=502,
                    media_type="application/json",
                )

        logger.info(f"Registered proxied workflow: {name} -> {proxy_url}")

    def register_mcp_server(self, name: str, mcp_server: Any):
        """Register an MCP server and expose its tools as REST endpoints.

        Args:
            name: Unique MCP server identifier
            mcp_server: MCP server instance (must support list_tools/call_tool)
        """
        if name in self.mcp_servers:
            raise ValueError(f"MCP server '{name}' already registered")

        self.mcp_servers[name] = mcp_server

        logger.info(f"Registered MCP server: {name}")

    async def publish_workflow_event(self, workflow_name: str, event: dict[str, Any]):
        """Publish an event to all WebSocket subscribers of a workflow.

        Args:
            workflow_name: Name of the workflow that produced the event
            event: Event data dict to send
        """
        subscribers = self._ws_subscriptions.get(workflow_name, set())
        dead_queues = set()
        for queue in subscribers:
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                dead_queues.add(queue)
        for dq in dead_queues:
            subscribers.discard(dq)

    def _get_workflow_endpoints(self, name: str) -> list[str]:
        """Get endpoints for a workflow."""
        reg = self.workflows.get(name)
        if not reg:
            return []

        base_endpoints = [
            f"/{name}/execute",
            f"/{name}/workflow/info",
            f"/{name}/health",
        ]

        if reg.type == "embedded":
            base_endpoints.append(f"/{name}/docs")

        return base_endpoints

    def run(
        self, host: str = "127.0.0.1", port: int = 8000, reload: bool = False, **kwargs
    ):
        """Run the gateway server.

        Args:
            host: Host to bind to
            port: Port to bind to
            reload: Enable auto-reload
            **kwargs: Additional uvicorn parameters
        """
        import uvicorn

        uvicorn.run(self.app, host=host, port=port, reload=reload, **kwargs)


class WorkflowOrchestrator:
    """Advanced orchestrator for complex workflow scenarios.

    Provides:
    - Workflow chaining and dependencies
    - Conditional routing between workflows
    - Parallel workflow execution
    - Transaction management
    - Event-driven triggers
    """

    def __init__(self, gateway: WorkflowAPIGateway):
        """Initialize orchestrator with a gateway."""
        self.gateway = gateway
        self.chains: dict[str, list[str]] = {}
        self.dependencies: dict[str, list[str]] = {}

    def create_chain(self, name: str, workflow_sequence: list[str]):
        """Create a workflow chain.

        Args:
            name: Chain identifier
            workflow_sequence: Ordered list of workflow names
        """
        # Validate all workflows exist
        for workflow in workflow_sequence:
            if workflow not in self.gateway.workflows:
                raise ValueError(f"Workflow '{workflow}' not registered")

        self.chains[name] = workflow_sequence

    async def execute_chain(
        self, chain_name: str, initial_input: dict[str, Any]
    ) -> dict[str, Any]:
        """Execute a workflow chain.

        Each workflow in the chain receives the output of the previous one
        as its input parameters. Proxied workflows are called via HTTP POST,
        while embedded workflows are executed in-process via LocalRuntime.

        Args:
            chain_name: Chain to execute
            initial_input: Input for first workflow

        Returns:
            Final output from the chain
        """
        if chain_name not in self.chains:
            raise ValueError(f"Chain '{chain_name}' not found")

        result = initial_input

        # Context-managed so the runtime's resources are released even if a
        # hop raises. The bare `LocalRuntime()` here leaked on every call and
        # emitted a DeprecationWarning that becomes an error in v0.12.0.
        with LocalRuntime() as runtime:
            for workflow_name in self.chains[chain_name]:
                reg = self.gateway.workflows[workflow_name]

                if reg.type == "embedded" and reg.workflow is not None:
                    # Execute embedded workflow in-process
                    # Bind BOTH shapes. On the FIRST hop `result` IS the caller's
                    # `initial_input`, so this is a caller-facing entry point with
                    # one arguments slot and the structural rule in
                    # `kailash/workflow/input_envelope.py` says it binds -- passing
                    # it raw left a workflow reading `parameters.get(...)` raising
                    # NameError here while running on every channel.
                    #
                    # Later hops carry the PREVIOUS workflow's flattened node
                    # outputs rather than caller data, and they bind too, on
                    # purpose: one workflow in a chain must not see a different
                    # input contract depending on its position. The envelope does
                    # not accumulate across hops -- `result` is rebuilt from
                    # `wf_results` each iteration, so the key is re-derived, never
                    # nested.
                    from kailash.workflow.input_envelope import bind_parameter_envelope

                    wf_results, _run_id = runtime.execute(
                        reg.workflow, parameters=bind_parameter_envelope(result)
                    )
                    # Flatten results: use all node outputs as next input
                    result = {}
                    for _node_id, node_output in wf_results.items():
                        if isinstance(node_output, dict):
                            result.update(node_output)
                        else:
                            result[_node_id] = node_output

                elif reg.type == "proxied" and reg.proxy_url:
                    # Forward to proxied backend via HTTP POST
                    client = await self.gateway._get_proxy_client()
                    url = f"{reg.proxy_url.rstrip('/')}/execute"
                    resp = await client.post(url, json=result, timeout=60.0)
                    resp.raise_for_status()
                    result = resp.json()

                else:
                    raise ValueError(
                        f"Workflow '{workflow_name}' is not executable "
                        f"(type={reg.type}, workflow={reg.workflow is not None})"
                    )

        return result

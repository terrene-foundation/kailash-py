"""Basic workflow server implementation.

This module provides WorkflowServer - a renamed and improved version of
WorkflowAPIGateway with clearer naming and better organization.
"""

import logging
import time
from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from typing import Any, Awaitable, Callable, Optional

from fastapi import FastAPI
from pydantic import BaseModel, Field
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.websockets import WebSocket

from ..api.workflow_api import WorkflowAPI
from ..runtime.shutdown import ShutdownCoordinator
from ..workflow import Workflow
from .connection_metrics_router import (
    ConnectionMetricsProvider,
    create_connection_metrics_router,
)

logger = logging.getLogger(__name__)

_RATE_LIMIT_MAX_REQUESTS = 100  # per window
_RATE_LIMIT_WINDOW_SECONDS = 60


class _SignalQueryRateLimiter:
    """Simple in-memory rate limiter: max requests per workflow_id per minute."""

    _MAX_KEYS = 10000

    def __init__(
        self,
        max_requests: int = _RATE_LIMIT_MAX_REQUESTS,
        window_seconds: float = _RATE_LIMIT_WINDOW_SECONDS,
    ) -> None:
        self._max = max_requests
        self._window = window_seconds
        self._timestamps: dict = defaultdict(lambda: deque())
        self._last_cleanup = time.monotonic()

    def is_allowed(self, key: str) -> bool:
        """Return True if the request is within the rate limit."""
        now = time.monotonic()
        window_start = now - self._window
        dq = self._timestamps[key]
        while dq and dq[0] < window_start:
            dq.popleft()
        if len(dq) >= self._max:
            return False
        dq.append(now)
        if now - self._last_cleanup > 60.0 or len(self._timestamps) > self._MAX_KEYS:
            stale = [k for k, d in self._timestamps.items() if not d]
            for k in stale:
                del self._timestamps[k]
            self._last_cleanup = now
        return True


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


class WorkflowServer:
    """Basic workflow server for hosting multiple Kailash workflows.

    This server provides:
    - Multi-workflow hosting with dynamic registration
    - REST API endpoints for workflow execution
    - WebSocket support for real-time updates
    - MCP server integration
    - Health monitoring
    - CORS support

    This is the base server class. For production deployments, consider
    using EnterpriseWorkflowServer which includes durability, security,
    and monitoring features.

    Attributes:
        app: FastAPI application instance
        workflows: Registry of all registered workflows
        executor: Thread pool for synchronous execution
        mcp_servers: Registry of MCP servers
    """

    def __init__(
        self,
        title: str = "Kailash Workflow Server",
        description: str = "Multi-workflow hosting server",
        version: str = "1.0.0",
        max_workers: int = 10,
        cors_origins: list[str] | None = None,
        runtime: Any = None,
        startup_hook: Optional[Callable[[], Awaitable[None]]] = None,
        shutdown_hook: Optional[Callable[[], Awaitable[None]]] = None,
        **kwargs,
    ):
        """Initialize the workflow server.

        Args:
            title: Server title for documentation
            description: Server description
            version: Server version
            max_workers: Maximum thread pool workers
            cors_origins: Allowed CORS origins
            runtime: Optional LocalRuntime instance for signal/query support
            startup_hook: Optional async callback awaited inside the FastAPI
                lifespan, after `router._startup()` fires, BEFORE the server
                starts accepting requests. Tasks created here run inside
                uvicorn's loop and survive for the server's lifetime.
            shutdown_hook: Optional async callback awaited inside the FastAPI
                lifespan AFTER the server has stopped accepting requests but
                BEFORE `router._shutdown()` and ShutdownCoordinator run.
                Exceptions are swallowed and logged at WARN; they never
                prevent router/coordinator cleanup.
        """
        self.workflows: dict[str, WorkflowRegistration] = {}
        self.mcp_servers: dict[str, Any] = {}
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.runtime = runtime
        self._rate_limiter = _SignalQueryRateLimiter()

        # Coordinated shutdown via ShutdownCoordinator
        self.shutdown_coordinator = ShutdownCoordinator(
            timeout=kwargs.pop("shutdown_timeout", 30.0)
        )
        # Register server's own executor shutdown at priority 0 (stop accepting)
        self.shutdown_coordinator.register(
            "executor", lambda: self.executor.shutdown(wait=True), priority=0
        )

        # Create FastAPI app with lifespan.
        #
        # Historical bug #500: passing ANY custom `lifespan` to FastAPI()
        # replaces Starlette's `_DefaultLifespan`, which was the only code
        # that iterated `router.on_startup` / `router.on_shutdown`. A custom
        # lifespan that does not explicitly invoke `app.router._startup()`
        # silently drops every user-registered router-level hook.
        #
        # Historical bug #501: Nexus plugin startup hooks were invoked
        # *before* uvicorn booted via `asyncio.run(hook())`, which created a
        # throwaway event loop, ran the hook (which often scheduled
        # long-lived background tasks via `asyncio.create_task(...)`), and
        # then closed the loop — cancelling every task the hook had just
        # created. Running plugin hooks inside the FastAPI lifespan places
        # them on uvicorn's loop, where any task they schedule survives for
        # the server's lifetime.
        #
        # Both halves converge on the same fix: route all startup hooks
        # through this lifespan context. See workspaces/issues-500-501.
        @asynccontextmanager
        async def lifespan(app: FastAPI):
            # Startup — honor FastAPI's documented pattern (#500).
            # Starlette's public Router.startup() coroutine iterates
            # every handler registered via `router.on_startup.append(...)`
            # — exactly the set that the default `_DefaultLifespan` used
            # to iterate before we replaced it.
            logger.info(f"Starting {title} v{version}")
            await app.router.startup()
            # Run injected Nexus plugin startup hooks inside uvicorn's loop
            # so any background tasks they spawn survive (#501).
            if startup_hook is not None:
                await startup_hook()
            try:
                yield
            finally:
                # Shutdown — symmetric to startup, but every step is
                # best-effort so one failing cleanup cannot block the next.
                logger.info("Shutting down workflow server via ShutdownCoordinator")
                if shutdown_hook is not None:
                    try:
                        await shutdown_hook()
                    except Exception:
                        # Cleanup path — log and continue so router.shutdown
                        # and ShutdownCoordinator still run. Same carve-out
                        # as zero-tolerance.md Rule 3.
                        logger.warning(
                            "Shutdown hook raised during lifespan teardown",
                            exc_info=True,
                        )
                try:
                    await app.router.shutdown()
                except Exception:
                    logger.warning(
                        "router.shutdown raised during lifespan teardown",
                        exc_info=True,
                    )
                await self.shutdown_coordinator.shutdown()

        self.app = FastAPI(
            title=title, description=description, version=version, lifespan=lifespan
        )

        # Add CORS middleware
        if cors_origins:
            # Only allow credentials when origins are explicitly specified (not wildcard)
            allow_creds = "*" not in cors_origins
            self.app.add_middleware(
                CORSMiddleware,
                allow_origins=cors_origins,
                allow_credentials=allow_creds,
                allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
                allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
            )

        # Connection metrics
        self._connection_metrics_provider = ConnectionMetricsProvider()
        self._connection_metrics_router = create_connection_metrics_router(
            self._connection_metrics_provider,
        )
        self.app.include_router(self._connection_metrics_router, prefix="/connections")

        # Live dashboard endpoint
        self._register_dashboard_endpoint()

        # Register root endpoints
        self._register_root_endpoints()

        # Signal/query endpoints for running workflows
        self._register_signal_query_endpoints()

    def _register_dashboard_endpoint(self):
        """Register a ``/dashboard`` endpoint serving the WebSocket live dashboard."""
        from starlette.responses import HTMLResponse

        from ..visualization.live_dashboard import LiveDashboard

        @self.app.get("/dashboard", response_class=HTMLResponse)
        async def live_dashboard():
            """Serve the WebSocket-powered live monitoring dashboard."""
            dash = LiveDashboard()
            return HTMLResponse(
                content=dash.render(),
                headers={
                    "Content-Security-Policy": (
                        "default-src 'self'; "
                        "script-src 'unsafe-inline'; "
                        "style-src 'unsafe-inline'; "
                        "connect-src 'self' ws: wss:"
                    )
                },
            )

    def _register_root_endpoints(self):
        """Register server-level endpoints."""

        @self.app.get("/")
        async def root():
            """Server information."""
            return {
                "name": self.app.title,
                "version": self.app.version,
                "workflows": list(self.workflows.keys()),
                "mcp_servers": list(self.mcp_servers.keys()),
                "type": "workflow_server",
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
            """Server health check."""
            health_status = {
                "status": "healthy",
                "server_type": "workflow_server",
                "workflows": {},
                "mcp_servers": {},
            }

            # Check workflow health
            for name, reg in self.workflows.items():
                if reg.type == "embedded":
                    health_status["workflows"][name] = "healthy"
                elif reg.type == "proxied" and reg.proxy_url:
                    # Check proxy health by hitting the remote health endpoint
                    try:
                        import aiohttp

                        url = f"{reg.proxy_url.rstrip('/')}{reg.health_check}"
                        timeout = aiohttp.ClientTimeout(total=5)
                        async with aiohttp.ClientSession(timeout=timeout) as session:
                            async with session.get(url) as resp:
                                if resp.status == 200:
                                    health_status["workflows"][name] = "healthy"
                                else:
                                    health_status["workflows"][name] = "degraded"
                    except Exception as e:
                        logger.warning(f"Proxy health check failed for {name}: {e}")
                        health_status["workflows"][name] = "unhealthy"
                else:
                    health_status["workflows"][name] = "unknown"

            # Check MCP server health
            for name, server in self.mcp_servers.items():
                try:
                    if hasattr(server, "health_check"):
                        mcp_health = await server.health_check()
                        health_status["mcp_servers"][name] = (
                            "healthy" if mcp_health else "unhealthy"
                        )
                    elif hasattr(server, "is_running"):
                        health_status["mcp_servers"][name] = (
                            "healthy" if server.is_running else "stopped"
                        )
                    else:
                        health_status["mcp_servers"][name] = "healthy"
                except Exception as e:
                    logger.warning(f"MCP health check failed for {name}: {e}")
                    health_status["mcp_servers"][name] = "unhealthy"

            return health_status

        @self.app.get("/metrics")
        async def prometheus_metrics():
            """Prometheus metrics endpoint with connection pool metrics."""
            from starlette.responses import Response

            from ..monitoring.metrics import get_metrics_registry

            registry = get_metrics_registry()
            content = registry.export_metrics(format="prometheus")

            # Merge connection pool metrics into Prometheus output
            try:
                pool_data = await self._connection_metrics_provider.collect()
                conn_lines = self._connection_metrics_provider.get_prometheus_lines(
                    pool_data
                )
                if conn_lines:
                    content = content.rstrip("\n") + "\n" + "\n".join(conn_lines) + "\n"
            except Exception as e:
                logger.warning("Failed to collect connection metrics: %s", e)

            return Response(
                content=content,
                media_type="text/plain; version=0.0.4; charset=utf-8",
            )

        @self.app.websocket("/ws")
        async def websocket_endpoint(websocket: WebSocket):
            """WebSocket for real-time updates."""
            await websocket.accept()
            try:
                while True:
                    # Basic WebSocket echo - subclasses can override
                    data = await websocket.receive_text()
                    await websocket.send_text(f"Echo: {data}")
            except Exception as e:
                logger.error(f"WebSocket error: {e}")
            finally:
                await websocket.close()

    def _register_signal_query_endpoints(self):
        """Register signal and query REST endpoints.

        These endpoints enable external HTTP clients to send signals to
        and query the state of running workflows via the runtime's
        signal/query system.
        """

        @self.app.post("/workflows/{workflow_id}/signals/{signal_name}")
        async def send_signal(workflow_id: str, signal_name: str, request: Request):
            """Send a signal to a running workflow.

            The request body (JSON) is delivered as the signal data payload.
            An empty body sends None as the data.

            Args:
                workflow_id: The run_id or workflow_id of the target workflow.
                signal_name: Name of the signal to send.

            Returns:
                JSON confirmation with signal details.

            Raises:
                404: If no runtime is configured or no active workflow found.
            """
            from starlette.responses import JSONResponse

            if not self._rate_limiter.is_allowed(workflow_id):
                return JSONResponse(
                    status_code=429,
                    content={"error": "Rate limit exceeded"},
                )

            if self.runtime is None:
                return JSONResponse(
                    status_code=404,
                    content={
                        "error": "No runtime configured on this server. "
                        "Pass a LocalRuntime instance to WorkflowServer(runtime=...)."
                    },
                )

            try:
                body = await request.json()
            except Exception:
                body = None

            try:
                self.runtime.signal(workflow_id, signal_name, body)
                return {
                    "status": "signal_sent",
                    "workflow_id": workflow_id,
                    "signal_name": signal_name,
                }
            except KeyError as e:
                logger.error("Signal error for workflow %s: %s", workflow_id, e)
                return JSONResponse(
                    status_code=404,
                    content={"error": "Workflow not found"},
                )

        @self.app.get("/workflows/{workflow_id}/queries/{query_name}")
        async def execute_query(workflow_id: str, query_name: str, request: Request):
            """Execute a query on a running workflow.

            Query parameters from the URL are passed as keyword arguments
            to the registered query handler.

            Args:
                workflow_id: The run_id or workflow_id of the target workflow.
                query_name: Name of the query to execute.

            Returns:
                JSON result from the query handler.

            Raises:
                404: If no runtime configured, no active workflow, or no handler.
            """
            from starlette.responses import JSONResponse

            if not self._rate_limiter.is_allowed(workflow_id):
                return JSONResponse(
                    status_code=429,
                    content={"error": "Rate limit exceeded"},
                )

            if self.runtime is None:
                return JSONResponse(
                    status_code=404,
                    content={
                        "error": "No runtime configured on this server. "
                        "Pass a LocalRuntime instance to WorkflowServer(runtime=...)."
                    },
                )

            # Convert query params to kwargs (exclude path params)
            kwargs = dict(request.query_params)

            try:
                result = await self.runtime.query(workflow_id, query_name, **kwargs)
                return {"status": "ok", "query_name": query_name, "result": result}
            except KeyError as e:
                logger.error("Query error for workflow %s: %s", workflow_id, e)
                return JSONResponse(
                    status_code=404,
                    content={"error": "Workflow or query not found"},
                )

    def register_workflow(
        self,
        name: str,
        workflow: Workflow,
        description: str | None = None,
        tags: list[str] | None = None,
    ):
        """Register a workflow with the server.

        Args:
            name: Unique workflow identifier
            workflow: Workflow instance to register
            description: Optional workflow description
            tags: Optional tags for categorization
        """
        if name in self.workflows:
            raise ValueError(f"Workflow '{name}' already registered")

        # Create workflow registration
        registration = WorkflowRegistration(
            name=name,
            type="embedded",
            workflow=workflow,
            description=description or f"Workflow: {name}",
            tags=tags or [],
        )

        self.workflows[name] = registration

        # Create workflow API wrapper
        workflow_api = WorkflowAPI(workflow)

        # Register workflow endpoints with prefix
        prefix = f"/workflows/{name}"
        self.app.mount(prefix, workflow_api.app)

        logger.info(f"Registered workflow '{name}' at {prefix}")

    def register_mcp_server(self, name: str, mcp_server: Any):
        """Register an MCP server with the workflow server.

        Args:
            name: Unique MCP server identifier
            mcp_server: MCP server instance
        """
        if name in self.mcp_servers:
            raise ValueError(f"MCP server '{name}' already registered")

        self.mcp_servers[name] = mcp_server

        # Mount MCP server endpoints
        mcp_prefix = f"/mcp/{name}"
        if hasattr(mcp_server, "app"):
            self.app.mount(mcp_prefix, mcp_server.app)
        elif hasattr(mcp_server, "get_app"):
            self.app.mount(mcp_prefix, mcp_server.get_app())

        logger.info(f"Registered MCP server '{name}' at {mcp_prefix}")

    def proxy_workflow(
        self,
        name: str,
        proxy_url: str,
        health_check: str = "/health",
        description: str | None = None,
        tags: list[str] | None = None,
    ):
        """Register a proxied workflow running on another server.

        Args:
            name: Unique workflow identifier
            proxy_url: Base URL of the proxied workflow
            health_check: Health check endpoint path
            description: Optional workflow description
            tags: Optional tags for categorization
        """
        if name in self.workflows:
            raise ValueError(f"Workflow '{name}' already registered")

        # Create proxied workflow registration
        registration = WorkflowRegistration(
            name=name,
            type="proxied",
            proxy_url=proxy_url,
            health_check=health_check,
            description=description or f"Proxied workflow: {name}",
            tags=tags or [],
        )

        self.workflows[name] = registration

        # Create proxy endpoints that forward requests to the remote server
        @self.app.api_route(
            f"/workflows/{name}/{{path:path}}",
            methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
        )
        async def proxy_handler(request: Request, path: str, _url=proxy_url):
            """Forward requests to proxied workflow server."""
            import aiohttp

            target_url = f"{_url.rstrip('/')}/{path}"
            timeout = aiohttp.ClientTimeout(total=30)

            async with aiohttp.ClientSession(timeout=timeout) as session:
                # Forward headers, excluding host and sensitive headers
                _sensitive_headers = frozenset(
                    {
                        "host",
                        "content-length",
                        "authorization",
                        "cookie",
                        "x-api-key",
                        "x-auth-token",
                        "proxy-authorization",
                        "set-cookie",
                    }
                )
                headers = {
                    k: v
                    for k, v in request.headers.items()
                    if k.lower() not in _sensitive_headers
                }

                body = (
                    await request.body()
                    if request.method in ("POST", "PUT", "PATCH")
                    else None
                )

                async with session.request(
                    request.method,
                    target_url,
                    headers=headers,
                    data=body,
                    params=dict(request.query_params),
                ) as resp:
                    content = await resp.read()
                    from starlette.responses import Response as StarletteResponse

                    _allowed_response_headers = frozenset(
                        {
                            "content-type",
                            "content-length",
                            "cache-control",
                            "etag",
                            "last-modified",
                            "content-encoding",
                        }
                    )
                    safe_headers = {
                        k: v
                        for k, v in resp.headers.items()
                        if k.lower() in _allowed_response_headers
                    }
                    return StarletteResponse(
                        content=content,
                        status_code=resp.status,
                        headers=safe_headers,
                    )

        logger.info(f"Registered proxied workflow '{name}' -> {proxy_url}")

    def _get_workflow_endpoints(self, name: str) -> list[str]:
        """Get available endpoints for a workflow."""
        base = f"/workflows/{name}"
        return [
            f"{base}/execute",
            f"{base}/status",
            f"{base}/schema",
            f"{base}/docs",
        ]

    def run(self, host: str = "127.0.0.1", port: int = 8000, **kwargs):
        """Run the workflow server.

        Args:
            host: Host address to bind to
            port: Port to listen on
            **kwargs: Additional arguments passed to uvicorn
        """
        import uvicorn

        uvicorn.run(self.app, host=host, port=port, **kwargs)

    def execute(self, **kwargs):
        """Execute the server (alias for run)."""
        self.run(**kwargs)

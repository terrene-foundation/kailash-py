"""Basic workflow server implementation.

This module provides WorkflowServer - a renamed and improved version of
WorkflowAPIGateway with clearer naming and better organization.
"""

import asyncio
import logging
import time
from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from typing import Any, Awaitable, Callable, Optional

# `fastapi` and `starlette` are OPTIONAL dependencies under the `server` extra.
# Per `rules/dependencies.md` § "Declared = Imported": optional-extra imports
# MUST raise loudly with an actionable error naming the extra.
try:
    from fastapi import Depends, FastAPI
    from starlette.middleware.cors import CORSMiddleware
    from starlette.requests import Request
    from starlette.responses import Response as StarletteResponse
    from starlette.websockets import WebSocket
except ImportError as exc:  # pragma: no cover — covered by structural invariant test
    raise ImportError(
        "kailash.servers.workflow_server requires server dependencies (fastapi, "
        "starlette). Install with: pip install 'kailash[server]'"
    ) from exc

from pydantic import BaseModel, Field

from ..api.workflow_api import WorkflowAPI
from ..runtime.shutdown import ShutdownCoordinator
from ..utils.lifespan import (
    drive_router_lifespan_shutdown,
    drive_router_lifespan_startup,
)
from ..utils.proxy_guard import (
    PROXY_CREDENTIAL_HEADERS,
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
        startup_hook_timeout: Optional[float] = None,
        auth_manager: Any = None,
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
            startup_hook: Optional async callback awaited inside the FastAPI
                lifespan, after `router._startup()` fires, BEFORE the server
                starts accepting requests. Tasks created here run inside
                uvicorn's loop and survive for the server's lifetime.
            shutdown_hook: Optional async callback awaited inside the FastAPI
                lifespan AFTER the server has stopped accepting requests but
                BEFORE `router._shutdown()` and ShutdownCoordinator run.
                Exceptions are swallowed and logged at WARN; they never
                prevent router/coordinator cleanup.
            startup_hook_timeout: Optional seconds to wait for ``startup_hook``
                before timing out and raising. ``None`` (the default) means
                wait indefinitely — matches historical behavior. Set this to
                a finite value (e.g. 30.0) when a slow or hung plugin
                ``on_startup`` must not pin the FastAPI lifespan forever and
                prevent uvicorn from accepting connections. On timeout, the
                lifespan's shutdown branch still runs so partial startup
                state is torn down.

                Cancel-cleanup contract (sec M-N2 / round-2 red-team): on
                timeout, ``asyncio.wait_for`` cancels the hook's coroutine.
                If the hook had already acquired resources (DB connections,
                spawned tasks, opened files) before the cancellation, those
                resources are NOT automatically released by the framework.
                The framework's cleanup obligation is limited to invoking
                ``shutdown_hook`` in the lifespan's ``finally:`` block, so
                plugin authors MUST:

                1. Register a ``shutdown_hook`` that is idempotent and
                   safe against partial-init state — every resource the
                   ``startup_hook`` could have acquired before cancellation
                   MUST be safe to release in ``shutdown_hook`` even if the
                   ``startup_hook`` never reached the paired acquisition.
                2. Handle ``asyncio.CancelledError`` inside ``startup_hook``
                   itself if the hook spawns tasks via
                   ``asyncio.create_task`` that cannot be cancelled via the
                   parent coroutine's cancellation. The hook MUST cancel
                   and await its own spawned tasks on cancellation, or
                   register them with the ``shutdown_hook`` for teardown.
                3. NOT swallow ``CancelledError`` — after cleaning up,
                   re-raise so ``wait_for`` sees the cancellation complete.
        """
        self.workflows: dict[str, WorkflowRegistration] = {}
        self.mcp_servers: dict[str, Any] = {}
        # Per-workflow API wrappers, tracked so their runtimes are released on
        # close() (issue #1285 — each WorkflowAPI builds its own AsyncLocalRuntime).
        self._workflow_apis: dict[str, "WorkflowAPI"] = {}
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.runtime = runtime
        self._rate_limiter = _SignalQueryRateLimiter()

        # Authentication wiring for proxy routes (issue #2025). `set_auth_manager`
        # is also the name `nexus.plugins` probed for on this gateway and never
        # found (#2013) -- it now exists and does something.
        self._auth_manager: Any = auth_manager
        self._external_auth_reason: Optional[str] = None

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
            #
            # Security (sec H1 / round-1 red-team): the `try:` MUST wrap
            # `router.startup()` and `startup_hook()` too. If either raises
            # before the `yield`, the `finally:` block still runs, so every
            # resource registered with ShutdownCoordinator (ThreadPoolExecutor
            # + any plugin-registered cleanups) is torn down. A `try:` that
            # only wrapped `yield` leaked the coordinator on partial-startup
            # crashes and any Nexus plugin whose on_startup ran earlier in
            # the hook chain saw its paired on_shutdown silently skipped.
            logger.info(
                "workflow_server.lifespan.startup",
                extra={"title": title, "version": version},
            )
            try:
                # Drive `router.on_startup` via the shared helper rather than
                # calling a dispatch method. FastAPI has shipped both
                # `.startup()` (older) and `._startup()` (newer) over the
                # years and upgrades flip which one exists; the on_startup
                # list itself is the only stable surface. Issue #531: nexus
                # 2.1.0 shipped with `app.router.startup()` which crashed
                # production FastAPI builds that only expose `_startup`.
                # Driving the list directly matches what `_DefaultLifespan`
                # does internally and survives FastAPI/Starlette version
                # churn. The helper (kailash.utils.lifespan) is the single
                # source of truth used by every Kailash FastAPI surface that
                # sets `lifespan=` so the cross-version invariant lives in
                # one place — see #712 for the discoverability + multi-site
                # context.
                await drive_router_lifespan_startup(app)
                # Run injected Nexus plugin startup hooks inside uvicorn's
                # loop so any background tasks they spawn survive (#501).
                if startup_hook is not None:
                    if startup_hook_timeout is not None:
                        # sec M2: bound the wait so a hung plugin cannot pin
                        # uvicorn's lifespan forever. On timeout the except
                        # branch re-raises after the finally: has run the
                        # full teardown path.
                        try:
                            await asyncio.wait_for(
                                startup_hook(), timeout=startup_hook_timeout
                            )
                        except asyncio.TimeoutError:
                            logger.error(
                                "workflow_server.startup_hook.timeout",
                                extra={
                                    "timeout_seconds": startup_hook_timeout,
                                },
                            )
                            raise
                    else:
                        await startup_hook()
                yield
            finally:
                # Shutdown — symmetric to startup, but every step is
                # best-effort so one failing cleanup cannot block the next.
                # This path runs on BOTH normal shutdown AND aborted startup.
                logger.info("workflow_server.lifespan.shutdown")
                if shutdown_hook is not None:
                    try:
                        await shutdown_hook()
                    except Exception:
                        # Cleanup path — log and continue so router.shutdown
                        # and ShutdownCoordinator still run. Same carve-out
                        # as zero-tolerance.md Rule 3.
                        logger.warning(
                            "workflow_server.lifespan.shutdown_hook_failed",
                            exc_info=True,
                        )
                try:
                    # Paired with the on_startup iteration above — see #531.
                    # propagate_errors=False because shutdown is best-effort
                    # cleanup: one failing on_shutdown handler MUST NOT block
                    # the ShutdownCoordinator below from running. The helper
                    # already emits a structured WARN per failing handler
                    # (observability.md Rule 7), and the ASGI server is
                    # already tearing down — re-raising here would only mask
                    # the real shutdown chain.
                    await drive_router_lifespan_shutdown(app, propagate_errors=False)
                except Exception:
                    logger.warning(
                        "workflow_server.lifespan.router_shutdown_failed",
                        exc_info=True,
                    )
                try:
                    await self.shutdown_coordinator.shutdown()
                except Exception:
                    logger.warning(
                        "workflow_server.lifespan.coordinator_shutdown_failed",
                        exc_info=True,
                    )
                logger.info("workflow_server.lifespan.shutdown_complete")

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

            from ..monitoring.metrics import render_prometheus_exposition

            # Unified exposition (#1708): custom registry + prometheus_client
            # default registry (OTel meters + asyncsql/ML) + connection-pool lines.
            conn_lines = None
            try:
                pool_data = await self._connection_metrics_provider.collect()
                conn_lines = self._connection_metrics_provider.get_prometheus_lines(
                    pool_data
                )
            except Exception as e:
                logger.warning("Failed to collect connection metrics: %s", e)

            content = render_prometheus_exposition(extra_lines=conn_lines)

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

    def close(self) -> None:
        """Release per-workflow API runtimes (issue #1285).

        Each ``register_workflow`` builds a ``WorkflowAPI`` that owns its own
        ``AsyncLocalRuntime``; without this teardown those runtimes leak and emit
        ``ResourceWarning: Unclosed AsyncLocalRuntime`` at GC. Idempotent.
        """
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

    def set_auth_manager(self, auth_manager: Any) -> None:
        """Attach an authentication manager to this server.

        The manager must expose ``get_current_user_dependency()`` returning a
        FastAPI dependency that raises ``HTTPException(401)`` for
        unauthenticated callers;
        :class:`kailash.middleware.auth.MiddlewareAuthManager` is the shipped
        implementation. :meth:`proxy_workflow` consumes it to protect proxy
        routes (issue #2025).

        Routes already registered are unaffected -- FastAPI resolves route
        dependencies at registration time, so call this **before**
        :meth:`proxy_workflow`.

        Args:
            auth_manager: The authentication manager.

        Raises:
            ValueError: If ``auth_manager`` is None. Clearing authentication is
                not expressible through this method, because a caller that
                cleared it would silently widen every subsequent registration.
        """
        if auth_manager is None:
            raise ValueError(
                "set_auth_manager(None) is not allowed. Construct the server "
                "without auth_manager= if it should have no authentication "
                "manager; clearing one after the fact would silently widen "
                "every subsequent proxy registration (issue #2025)."
            )
        self._auth_manager = auth_manager
        logger.info(
            "workflow_server.auth_manager_set",
            extra={"auth_manager": type(auth_manager).__name__},
        )

    def declare_external_auth(self, reason: str) -> None:
        """Record that an external ASGI middleware authenticates this app.

        :meth:`proxy_workflow` fails closed when no authentication is
        configured (issue #2025). That gate can only see route-level
        dependencies, so a deployment whose requests are authenticated by an
        ASGI middleware installed outside this class -- for example
        ``nexus.auth.jwt.JWTMiddleware``, which ``Nexus(enable_auth=True)``
        installs on this server's ``app`` (#2013 / PR #2054) -- would
        otherwise be unable to register a proxy at all.

        This is an explicit, logged acknowledgement, not an install: it
        attaches no dependency and verifies nothing. Every proxy registration
        made under it logs a WARNING naming the route.

        Args:
            reason: Non-empty description of what authenticates the app,
                recorded in the log line so an operator reading it can check
                the claim.

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
            "workflow_server.external_auth_declared",
            extra={"reason": self._external_auth_reason},
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
        # Track it so its runtime is released on close() (issue #1285).
        self._workflow_apis[name] = workflow_api

        # Register workflow endpoints with prefix
        prefix = f"/workflows/{name}"
        self.app.mount(prefix, workflow_api.app)

        logger.info(f"Registered workflow '{name}' at {prefix}")

    def deregister_workflow(self, name: str) -> bool:
        """Remove a previously registered workflow from the server.

        Reverses :meth:`register_workflow`: drops the registration, releases
        the per-workflow ``WorkflowAPI`` runtime (issue #1285), and unmounts
        the ``/workflows/{name}`` sub-application so the name is free to be
        re-registered. This is what makes an idempotent redeploy possible —
        without it, a second ``register_workflow(name, ...)`` raises
        ``ValueError: Workflow '{name}' already registered``.

        Args:
            name: Workflow identifier to remove.

        Returns:
            True if a workflow was removed, False if none was registered
            under ``name`` (idempotent no-op).
        """
        if name not in self.workflows:
            return False

        del self.workflows[name]

        # Release the per-workflow API runtime so its AsyncLocalRuntime is
        # closed rather than leaked (mirrors close(), issue #1285).
        workflow_api = getattr(self, "_workflow_apis", {}).pop(name, None)
        if workflow_api is not None:
            try:
                workflow_api.close()
            except Exception as exc:  # pragma: no cover - teardown best-effort
                logger.debug(
                    "Error closing WorkflowAPI for '%s': %s: %s",
                    name,
                    type(exc).__name__,
                    exc,
                )

        # Unmount the sub-application mounted at /workflows/{name}. Starlette
        # keys a Mount by its (trailing-slash-stripped) path, so match the
        # exact prefix to avoid removing sibling workflow mounts.
        prefix = f"/workflows/{name}"
        self.app.router.routes = [
            route
            for route in self.app.router.routes
            if getattr(route, "path", None) != prefix
        ]

        logger.info(f"Deregistered workflow '{name}' from {prefix}")
        return True

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
        *,
        allowed_paths: list[PathPattern] | None = None,
        allowed_methods: list[str] | None = None,
        auth_dependency: Callable[..., Any] | None = None,
        forward_credentials: bool = False,
    ):
        """Register a proxied workflow running on another server.

        The registered route forwards requests to ``proxy_url``. Because that
        publishes the backend through this server, registration is fail-closed
        (issue #2025): it raises unless the caller supplies an authentication
        control **and** an explicit path allowlist.

        Args:
            name: Unique workflow identifier
            proxy_url: Base URL of the proxied workflow
            health_check: Health check endpoint path
            description: Optional workflow description
            tags: Optional tags for categorization
            allowed_paths: **Required.** Paths beneath ``/workflows/{name}/``
                that may be forwarded. Strings match the path with the leading
                ``/`` stripped: ``"status"`` exactly, ``"api/*"`` as a prefix
                at any depth, ``"*"`` for every path (the pre-#2025 behaviour,
                now explicit). Compiled ``re.Pattern`` entries are matched with
                ``fullmatch``. A request whose path matches nothing gets 404 --
                it is not a path this proxy serves. See
                :func:`kailash.utils.proxy_guard.compile_path_allowlist`.
            allowed_methods: HTTP methods to forward. Defaults to ``["GET"]``;
                any other verb gets 405 from the router because the route is
                registered only for the methods named here.
            auth_dependency: FastAPI dependency protecting the route. When
                omitted, the server's ``auth_manager`` supplies one. When
                neither is available and
                :meth:`declare_external_auth` was not called,
                :class:`~kailash.utils.proxy_guard.ProxyAuthNotConfiguredError`
                is raised.
            forward_credentials: When False (the default) the caller's
                ``Authorization``, ``Cookie``, ``X-API-Key``,
                ``X-Auth-Token`` and ``Proxy-Authorization`` headers are
                STRIPPED before forwarding -- the behaviour this server has
                always had. Set True when the backend is trusted and needs to
                re-authorize the original caller; #2025 noted that stripping
                unconditionally left the backend unable to re-authorize, and
                this is the documented way to allow it.

        Raises:
            ProxyAuthNotConfiguredError: No authentication control is
                configured for the route.
            ValueError: ``name`` is already registered, or ``allowed_paths`` /
                ``allowed_methods`` is missing or invalid.
        """
        if name in self.workflows:
            raise ValueError(f"Workflow '{name}' already registered")

        # Fail-closed registration guards. These run BEFORE the workflow is
        # recorded and BEFORE the route is added, so a refused registration
        # leaves no half-registered proxy behind.
        route_auth_dependency = resolve_proxy_auth_dependency(
            name=name,
            surface="WorkflowServer",
            auth_dependency=auth_dependency,
            auth_manager=self._auth_manager,
            external_auth_reason=self._external_auth_reason,
        )
        path_allowlist = compile_path_allowlist(allowed_paths, name=name)
        methods = normalize_allowed_methods(
            allowed_methods,
            name=name,
            supported=("GET", "POST", "PUT", "DELETE", "PATCH"),
        )

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

        route_kwargs: dict[str, Any] = {}
        if route_auth_dependency is not None:
            route_kwargs["dependencies"] = [Depends(route_auth_dependency)]

        # Create proxy endpoints that forward requests to the remote server
        @self.app.api_route(
            f"/workflows/{name}/{{path:path}}",
            methods=methods,
            **route_kwargs,
        )
        async def proxy_handler(request: Request, path: str):
            """Forward requests to proxied workflow server.

            `proxy_url` and `path_allowlist` are captured from the enclosing
            scope, NOT passed as default arguments. FastAPI inspects the
            handler signature and treats any non-path parameter carrying a
            plain default as a QUERY parameter, so the previous
            `_url=proxy_url` idiom let a caller override the destination with
            `?_url=http://attacker/` -- full SSRF. Each `proxy_workflow` call
            has its own scope, so direct capture is correct here and the
            late-binding hazard the default-argument idiom guards against
            does not apply.
            """
            import aiohttp
            from starlette.responses import JSONResponse

            # Refuse traversal before the target URL is built, rather than
            # relying on yarl's normalization (issue #2025).
            unsafe_reason = reject_unsafe_proxy_path(path)
            if unsafe_reason is not None:
                logger.warning(
                    "workflow_server.proxy.path_rejected",
                    extra={"workflow": name, "reason": unsafe_reason},
                )
                return JSONResponse(
                    status_code=400,
                    content={"error": f"Invalid proxy path: {unsafe_reason}"},
                )

            if not path_matches_allowlist(path, path_allowlist):
                logger.warning(
                    "workflow_server.proxy.path_not_allowed",
                    extra={"workflow": name},
                )
                return JSONResponse(
                    status_code=404,
                    content={"error": "Not found"},
                )

            # Positive charset barrier. The target URL is built from the
            # MATCHED GROUP, never from the raw path parameter, so no byte
            # outside the allowlist can reach the wire whatever the HTTP
            # client does with re-encoding. This is what closes the
            # request-line-injection question #2025 recorded as UNVERIFIED,
            # and it is the sanitizer CodeQL's py/partial-ssrf query asks for.
            safe_path_match = SAFE_FORWARD_PATH_RE.fullmatch(path)
            if safe_path_match is None:
                logger.warning(
                    "workflow_server.proxy.path_charset_rejected",
                    extra={"workflow": name},
                )
                return JSONResponse(
                    status_code=400,
                    content={
                        "error": "Invalid proxy path: contains a character that "
                        "may not be forwarded"
                    },
                )
            # Use `path` itself, not `safe_path_match.group(0)`. For a
            # SUCCESSFUL fullmatch those are the same string by definition, so
            # the extraction never sanitized anything -- the safety comes
            # entirely from the REJECTION above. Writing it as an extraction
            # invited a later `fullmatch` -> `match` edit that looks equivalent
            # and silently forwards a TRUNCATED path ('a b' -> 'a') instead of
            # refusing it.

            target_url = f"{proxy_url.rstrip('/')}/{path}"
            timeout = aiohttp.ClientTimeout(total=30)

            async with aiohttp.ClientSession(timeout=timeout) as session:
                # Forward headers, excluding hop-by-hop headers and -- unless
                # the registration opted in -- the caller's credentials. The
                # credential set is shared with WorkflowAPIGateway so the two
                # proxy surfaces cannot drift (security.md, Enforcement-Surface
                # Parity); before #2025 they disagreed in opposite directions.
                _excluded_headers = {"host", "content-length"}
                _excluded_headers |= PROXY_HOP_BY_HOP_HEADERS
                if not forward_credentials:
                    _excluded_headers |= PROXY_CREDENTIAL_HEADERS
                headers = {
                    k: v
                    for k, v in request.headers.items()
                    if k.lower() not in _excluded_headers
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
                    # multi_items() preserves repeated keys (?tag=a&tag=b);
                    # dict() silently kept only the last (issue #2025).
                    params=list(request.query_params.multi_items()),
                    # EXPLICIT, and load-bearing. aiohttp defaults this to
                    # True. Every control this route enforces -- the auth
                    # gate, the path allowlist, traversal rejection, the
                    # charset barrier -- applies to hop 1 only, so following a
                    # redirect hands the caller an authority pivot on hop 2:
                    # a backend with any open redirect (an SSO `?next=` bounce
                    # is ubiquitous, and query strings are forwarded verbatim)
                    # makes the proxy fetch an arbitrary host and return the
                    # body as if it were the backend's. `location` is not in
                    # the response allowlist, so the caller cannot even see
                    # that it happened. Measured before this line existed:
                    # a fully-hardened registration fetched cloud-metadata.
                    allow_redirects=False,
                ) as resp:
                    content = await resp.read()
                    safe_headers = {
                        k: v
                        for k, v in resp.headers.items()
                        if k.lower() in PROXY_SAFE_RESPONSE_HEADERS
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

# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple

from nexus.registry import HandlerDef, HandlerRegistry
from nexus.transports.base import Transport

logger = logging.getLogger(__name__)

__all__ = ["HTTPTransport"]


@dataclass
class _MiddlewareEntry:
    """Queued middleware to be applied when the gateway is ready."""

    middleware_class: type
    kwargs: Dict[str, Any]


@dataclass
class _RouterEntry:
    """Queued router to be included when the gateway is ready."""

    router: Any
    kwargs: Dict[str, Any]


class HTTPTransport(Transport):
    """HTTP transport backed by FastAPI via the Core SDK gateway.

    Encapsulates all FastAPI/Starlette coupling. Creates the enterprise
    gateway, applies middleware, registers routes, and runs uvicorn.

    Args:
        port: HTTP server port (default 8000).
        cors_origins: CORS allowed origins.
        cors_allow_methods: CORS allowed methods.
        cors_allow_headers: CORS allowed headers.
        cors_allow_credentials: CORS allow credentials.
        cors_expose_headers: CORS exposed headers.
        cors_max_age: CORS preflight cache duration.
        enable_auth: Enable authentication.
        enable_monitoring: Enable monitoring.
        enable_durability: Enable durability features.
        rate_limit: Default rate limit (requests/min). Coerced through
            ``nexus.core._coerce_rate_limit`` -- see :meth:`__init__`.
        runtime: Shared AsyncLocalRuntime.

    Raises:
        ValueError: If ``rate_limit`` is a bool, a non-integral float, a
            negative int, or any non-int type. See :meth:`__init__`.
    """

    def __init__(
        self,
        *,
        port: int = 8000,
        cors_origins: Optional[List[str]] = None,
        cors_allow_methods: Optional[List[str]] = None,
        cors_allow_headers: Optional[List[str]] = None,
        cors_allow_credentials: bool = False,
        cors_expose_headers: Optional[List[str]] = None,
        cors_max_age: int = 600,
        enable_auth: bool = False,
        enable_monitoring: bool = False,
        enable_durability: bool = True,
        rate_limit: Optional[int] = 100,
        runtime=None,
    ):
        """Construct the transport.

        ``rate_limit`` is COERCED, because this is the FIFTH surface that
        writes ``_rate_limit`` and it was the last one still writing raw. The
        other four -- ``Nexus(rate_limit=...)``, the
        ``rate_limit_config['default_rate_limit']`` fallback, the
        ``endpoint(rate_limit=...)`` kwarg, and ``RateLimitPlugin.apply`` --
        all route through ``_coerce_rate_limit``.

        The attribute name here is the SAME one the enforced path reads, and
        ``sse.py::_rate_limit_exceeded`` reaches it by ``getattr`` duck-typing
        (``getattr(nexus, "_rate_limit", None)``), guarded only by the
        ``Optional[int]`` ANNOTATION -- which does not execute. Any value
        failing ``> 0`` is read there as "no limit configured", so
        ``HTTPTransport(rate_limit=-5)`` yields ``-5 <= 0 -> return False``:
        silently unlimited, the exact fail-OPEN shape the other four surfaces
        were changed to eliminate.

        Whether some current caller happens never to read this attribute is a
        REACHABILITY argument, not a safety one, and reachability arguments
        against this defect class have already gone stale twice on this
        surface. Coercing at the write is what makes the invariant hold
        independently of who reads it.

        Imported function-locally because ``nexus.core`` imports THIS module at
        module scope (``core.py``: ``from nexus.transports.http import
        HTTPTransport``); a module-level import here would be a cycle. Same
        shared helper as the other four surfaces -- NOT a per-adapter copy.
        """
        from nexus.core import _coerce_rate_limit

        self._port = port
        self._cors_config = {
            "origins": cors_origins,
            "allow_methods": cors_allow_methods,
            "allow_headers": cors_allow_headers,
            "allow_credentials": cors_allow_credentials,
            "expose_headers": cors_expose_headers,
            "max_age": cors_max_age,
        }
        self._enable_auth = enable_auth
        self._enable_monitoring = enable_monitoring
        self._enable_durability = enable_durability
        self._rate_limit = _coerce_rate_limit(
            rate_limit, "HTTPTransport(rate_limit=...)"
        )
        self._runtime = runtime

        self._gateway = None
        self._running = False
        self._middleware_queue: List[_MiddlewareEntry] = []
        self._router_queue: List[_RouterEntry] = []
        self._endpoint_queue: List[Tuple[str, List[str], Callable, Dict]] = []

    @property
    def name(self) -> str:
        return "http"

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def app(self):
        """The underlying FastAPI application.

        Returns None if the gateway hasn't been created yet.
        """
        if self._gateway is not None:
            return self._gateway.app
        return None

    @property
    def port(self) -> int:
        """The HTTP port."""
        return self._port

    @property
    def gateway(self):
        """The underlying Core SDK gateway object.

        Used by Nexus internals that need direct gateway access
        (e.g., register_workflow, enable_auth, enable_monitoring).
        """
        return self._gateway

    def create_gateway(self, **gateway_kwargs) -> None:
        """Create the enterprise gateway eagerly (called during Nexus.__init__).

        This allows the gateway to exist before start() so that
        middleware, routers, and endpoints can be applied immediately.

        Args:
            **gateway_kwargs: Arguments forwarded to create_gateway().
        """
        from kailash.servers.gateway import create_gateway

        self._gateway = create_gateway(**gateway_kwargs)

    async def start(self, registry: HandlerRegistry) -> None:
        """Apply queued middleware/routers/endpoints. Register handlers.

        Note: The gateway is created earlier via create_gateway().
        start() applies anything queued and registers handlers.
        """
        if self._running:
            return

        if self._gateway is None:
            # If gateway wasn't pre-created, create it now
            from kailash.servers.gateway import create_gateway
            from nexus.auth_bootstrap import core_gateway_auth_kwargs

            self._gateway = create_gateway(
                enable_durability=self._enable_durability,
                # Resolved through the SAME helper as the primary construction
                # path in nexus/core.py, from the SAME flag this transport was
                # constructed with, so the two paths cannot disagree about who
                # authenticates this app (#2072). Passing a fixed
                # `external_auth_reason` here would declare an external gate on
                # a transport built with enable_auth=False, where nothing
                # installs one.
                **core_gateway_auth_kwargs(self._enable_auth),
            )
            self._apply_cors()

        # Install the NexusError -> HTTP exception handler so handlers that
        # raise typed errors get the documented status + JSON body (errors.py
        # advertises this; it was never wired). Idempotent.
        self._install_exception_handlers()

        # Apply queued middleware (LIFO order preserved by Starlette)
        for entry in self._middleware_queue:
            self._gateway.app.add_middleware(entry.middleware_class, **entry.kwargs)
            logger.info(f"Applied queued middleware: {entry.middleware_class.__name__}")
        self._middleware_queue.clear()

        # Include queued routers
        for entry in self._router_queue:
            self._gateway.app.include_router(entry.router, **entry.kwargs)
        self._router_queue.clear()

        # Register queued endpoints
        for path, methods, func, kwargs in self._endpoint_queue:
            self._register_endpoint_internal(path, methods, func, **kwargs)
        self._endpoint_queue.clear()

        # Register all workflows from registry.
        #
        # The gateway is built once at construction, so Nexus.register() has
        # ALREADY eagerly registered it with each workflow before start() runs
        # (the documented ``register(wf); start()`` flow). Re-registering the
        # same name raises ``ValueError: '<name>' already registered``. Skip
        # names the gateway already knows rather than catching-and-logging the
        # collision at ERROR — a false "Failed to register" on the happy path
        # (a redeploy re-uses this same gateway, so already-present is normal,
        # not a failure). ``register_workflow`` is still the sole registration
        # path; the pre-check just avoids driving it into its duplicate guard.
        for wf_name, workflow in registry.list_workflows().items():
            if wf_name in self._registered_workflow_names():
                logger.debug(
                    f"Workflow '{wf_name}' already registered with HTTP gateway; "
                    f"skipping"
                )
                continue
            try:
                self._gateway.register_workflow(wf_name, workflow)
            except Exception as e:
                logger.error(f"Failed to register workflow '{wf_name}' with HTTP: {e}")

        # Register handler workflows (same idempotency contract as above).
        for handler_def in registry.list_handlers():
            wf = registry._handler_funcs.get(handler_def.name, {}).get("workflow")
            if wf is not None:
                if handler_def.name in self._registered_workflow_names():
                    logger.debug(
                        f"Handler '{handler_def.name}' already registered with HTTP "
                        f"gateway; skipping"
                    )
                    continue
                try:
                    self._gateway.register_workflow(handler_def.name, wf)
                except Exception as e:
                    logger.error(
                        f"Failed to register handler '{handler_def.name}' with HTTP: {e}"
                    )

        self._running = True
        logger.info(f"HTTPTransport started on port {self._port}")

    def _registered_workflow_names(self) -> frozenset:
        """Names the enterprise gateway already has a workflow registered under.

        The gateway (``EnterpriseWorkflowServer``) tracks registrations in a
        name-keyed ``workflows`` dict. Reading it is the pre-check that lets
        :meth:`start` skip re-registering a workflow ``Nexus.register()``
        already installed, rather than driving ``register_workflow`` into its
        duplicate-name ``ValueError`` guard. Defensive: an unexpected gateway
        without a mapping ``workflows`` attribute yields an empty set (the loop
        then falls back to the try/except register path unchanged).
        """
        workflows = getattr(self._gateway, "workflows", None)
        if isinstance(workflows, dict):
            return frozenset(workflows.keys())
        return frozenset()

    def _install_exception_handlers(self) -> None:
        """Install the NexusError -> HTTP exception handler on the gateway app.

        Fulfills the contract documented in ``nexus/errors.py``: typed
        ``NexusError`` subclasses raised from any handler are translated to
        their declared ``status_code`` with the canonical
        ``{"error": <error_code>, "detail": <message>}`` body. For 5xx errors
        the raw detail is logged server-side and NOT leaked to the client
        (per the HTTP status convention). Idempotent — safe to call repeatedly.
        """
        if getattr(self, "_exc_handlers_installed", False):
            return
        if self._gateway is None:
            return

        from fastapi.responses import JSONResponse
        from starlette.requests import Request

        from nexus.errors import NexusError

        async def _handle_nexus_error(request: Request, exc: Exception) -> JSONResponse:
            # Registered for NexusError only; narrow for the type checker.
            if not isinstance(exc, NexusError):
                raise exc
            if exc.status_code >= 500:
                logger.error(
                    "NexusError %s on %s: %s",
                    type(exc).__name__,
                    getattr(request, "url", "<unknown>"),
                    exc.detail,
                    extra={"context": exc.context},
                )
                return JSONResponse(
                    status_code=exc.status_code,
                    content={
                        "error": exc.error_code,
                        "detail": "internal server error",
                    },
                )
            return JSONResponse(
                status_code=exc.status_code,
                content=exc.to_response_dict(),
            )

        self._gateway.app.add_exception_handler(NexusError, _handle_nexus_error)
        self._exc_handlers_installed = True
        logger.info("Installed NexusError -> HTTP exception handler")

    async def stop(self) -> None:
        """Stop the HTTP transport."""
        self._running = False
        logger.info("HTTPTransport stopped")

    def run_blocking(self, host: str = "0.0.0.0") -> None:
        """Run the gateway in blocking mode (for main thread).

        This is called by Nexus.start() to block on the HTTP server.
        """
        if self._gateway is None:
            raise RuntimeError("HTTPTransport not started -- call start() first")
        self._gateway.run(host=host, port=self._port)

    def add_middleware(self, middleware_class: type, **kwargs) -> None:
        """Add middleware. Queued if gateway not ready, applied immediately otherwise."""
        if self._gateway is not None:
            self._gateway.app.add_middleware(middleware_class, **kwargs)
        else:
            self._middleware_queue.append(_MiddlewareEntry(middleware_class, kwargs))

    def include_router(self, router, **kwargs) -> None:
        """Include a FastAPI router. Queued if gateway not ready."""
        if self._gateway is not None:
            self._gateway.app.include_router(router, **kwargs)
        else:
            self._router_queue.append(_RouterEntry(router, kwargs))

    def mount(self, path: str, app: Any, name: Optional[str] = None) -> None:
        """Mount an ASGI sub-application at a URL path prefix.

        Delegates to FastAPI's ``app.mount()`` which uses Starlette's
        Mount route. Starlette handles path prefix stripping and lets
        the sub-app dispatch its own full middleware/routing stack.

        If the gateway is not yet created, the caller is expected to
        queue the mount (see ``Nexus.mount``) — this method only applies
        immediately.

        Args:
            path: URL prefix for the sub-application.
            app: An ASGI-compatible application.
            name: Optional name (forwarded to Starlette).

        Raises:
            RuntimeError: If the gateway has not been created.
        """
        if self._gateway is None:
            raise RuntimeError(
                "HTTPTransport.mount called before gateway creation; "
                "mounts must be queued via Nexus.mount() pre-start."
            )
        self._gateway.app.mount(path, app, name=name)

    def register_endpoint(
        self, path: str, methods: List[str], func: Callable, **kwargs
    ) -> None:
        """Register a custom endpoint. Queued if gateway not ready."""
        if self._gateway is not None:
            self._register_endpoint_internal(path, methods, func, **kwargs)
        else:
            self._endpoint_queue.append((path, methods, func, kwargs))

    def register_workflow(self, name: str, workflow) -> None:
        """Register a workflow with the HTTP gateway."""
        if self._gateway is not None:
            self._gateway.register_workflow(name, workflow)

    def on_handler_registered(self, handler_def: HandlerDef) -> None:
        """Hot-register a handler with the running HTTP gateway."""
        if self._running and self._gateway is not None:
            wf = handler_def.metadata.get("workflow")
            if wf is not None:
                try:
                    self._gateway.register_workflow(handler_def.name, wf)
                except Exception as e:
                    logger.warning(
                        f"Failed to hot-register handler '{handler_def.name}': {e}"
                    )

    def health_check(self) -> Dict[str, Any]:
        """HTTP transport health status."""
        return {
            "transport": "http",
            "running": self._running,
            "port": self._port,
            "gateway": self._gateway is not None,
        }

    def _apply_cors(self) -> None:
        """Apply CORS middleware to the FastAPI app."""
        origins = self._cors_config.get("origins")
        if origins is None:
            return
        if self._gateway is None:
            raise RuntimeError("_apply_cors called before gateway creation")
        from starlette.middleware.cors import CORSMiddleware

        self._gateway.app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_methods=self._cors_config.get("allow_methods") or ["*"],
            allow_headers=self._cors_config.get("allow_headers") or ["*"],
            allow_credentials=self._cors_config.get("allow_credentials", False),
            expose_headers=self._cors_config.get("expose_headers") or [],
            max_age=self._cors_config.get("max_age", 600),
        )

    def _register_endpoint_internal(
        self, path: str, methods: List[str], func: Callable, **kwargs
    ) -> None:
        """Register endpoint routes on the live FastAPI app."""
        if self._gateway is None:
            raise RuntimeError(
                "_register_endpoint_internal called before gateway creation"
            )
        fastapi_app = self._gateway.app
        for method in methods:
            route_func = getattr(fastapi_app, method.lower())
            route_func(path, **kwargs)(func)

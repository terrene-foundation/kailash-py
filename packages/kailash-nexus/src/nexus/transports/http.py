# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import logging
from dataclasses import dataclass, field
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
        rate_limit: Default rate limit (requests/min).
        runtime: Shared AsyncLocalRuntime.
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
        self._rate_limit = rate_limit
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

            self._gateway = create_gateway(
                enable_durability=self._enable_durability,
            )
            self._apply_cors()

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

        # Register all workflows from registry
        for wf_name, workflow in registry.list_workflows().items():
            try:
                self._gateway.register_workflow(wf_name, workflow)
            except Exception as e:
                logger.error(f"Failed to register workflow '{wf_name}' with HTTP: {e}")

        # Register handler workflows
        for handler_def in registry.list_handlers():
            wf = registry._handler_funcs.get(handler_def.name, {}).get("workflow")
            if wf is not None:
                try:
                    self._gateway.register_workflow(handler_def.name, wf)
                except Exception as e:
                    logger.error(
                        f"Failed to register handler '{handler_def.name}' with HTTP: {e}"
                    )

        self._running = True
        logger.info(f"HTTPTransport started on port {self._port}")

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
        fastapi_app = self._gateway.app
        for method in methods:
            route_func = getattr(fastapi_app, method.lower())
            route_func(path, **kwargs)(func)

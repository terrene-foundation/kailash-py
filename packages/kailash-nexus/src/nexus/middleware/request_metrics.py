# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Per-request HTTP metrics middleware for Nexus.

Records ``nexus_http_requests_total`` (Counter) and
``nexus_http_request_duration_seconds`` (Histogram) — labelled by
``method`` / ``route`` (matched template) / ``status`` — for every HTTP
request. The metrics surface on the existing Prometheus ``/metrics`` endpoint
(``register_metrics_endpoint``) because they live in the default registry.

This is a PURE-ASGI middleware (matching ``SecurityHeadersMiddleware``), NOT a
Starlette ``BaseHTTPMiddleware`` — the latter breaks streaming responses and
background tasks. ``prometheus_client`` is an OPTIONAL dependency; when it is
absent the middleware is a cheap pass-through.

Usage:
    from nexus.middleware.request_metrics import RequestMetricsMiddleware

    app.add_middleware(RequestMetricsMiddleware)

Wire it LAST in a preset chain (outermost) so it measures TOTAL request
latency including every other middleware.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict

logger = logging.getLogger(__name__)

__all__ = ["RequestMetricsMiddleware"]


def _route_label(scope: Dict[str, Any]) -> str:
    """Return a bounded-cardinality route label for the request.

    Starlette/FastAPI populate ``scope["route"]`` once routing has run. By the
    time this middleware's instrumentation executes (it wraps OUTERMOST, so its
    ``finally`` runs after the inner app — including the router — completes),
    the matched route is available. We return the route TEMPLATE
    (``/users/{id}``), never the concrete path (``/users/123``), to bound
    Prometheus label cardinality and prevent a cardinality explosion / DoS via
    path scanning. When no route matched, the ``"__unmatched__"`` sentinel is
    used so unmatched traffic collapses to a single label.
    """
    route = scope.get("route")
    if route is not None:
        tmpl = getattr(route, "path_format", None) or getattr(route, "path", None)
        if tmpl:
            return tmpl
    return "__unmatched__"


class RequestMetricsMiddleware:
    """ASGI middleware recording per-request HTTP metrics.

    Compatible with Starlette's ``add_middleware()`` pattern.
    """

    def __init__(
        self,
        app: Any,
        *,
        exclude_paths: Any = ("/metrics", "/healthz", "/readyz", "/startup"),
    ) -> None:
        """Initialize the middleware.

        Args:
            app: The ASGI application to wrap.
            exclude_paths: Exact request paths to skip (no metric recorded).
                Defaults to the metrics + Kubernetes-probe endpoints so the
                scrape path and health checks do not pollute the route labels.
        """
        self.app = app
        self._exclude = set(exclude_paths)

        # Detect prometheus availability ONCE. When absent the middleware is a
        # cheap pass-through; the warning names the install extra so operators
        # know how to enable metrics.
        try:
            import prometheus_client  # noqa: F401

            self._enabled = True
        except ImportError:
            self._enabled = False
            logger.warning(
                "prometheus_client is not installed; RequestMetricsMiddleware "
                "is a no-op pass-through. Install it with: "
                "pip install kailash-nexus[metrics]"
            )

    async def __call__(self, scope: Dict[str, Any], receive: Any, send: Any) -> None:
        """ASGI interface."""
        if scope["type"] != "http" or not self._enabled:
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if path in self._exclude:
            await self.app(scope, receive, send)
            return

        method = scope.get("method", "UNKNOWN")
        # Default to 500 so an unhandled exception (which never emits an
        # http.response.start) is recorded as a server error.
        status_box = {"status": 500}

        async def send_wrapper(message: Dict[str, Any]) -> None:
            if message["type"] == "http.response.start":
                status_box["status"] = message["status"]
            await send(message)

        start = time.perf_counter()
        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            duration = time.perf_counter() - start
            route = _route_label(scope)
            # Lazy import inside finally avoids an import cycle at module load
            # (metrics.py has no dependency on this module, but this keeps the
            # ASGI hot-path import resolved only after prometheus is confirmed).
            from nexus.metrics import observe_http_request

            observe_http_request(method, route, status_box["status"], duration)

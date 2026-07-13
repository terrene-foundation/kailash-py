# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Per-request HTTP metrics middleware for Nexus.

Records ``nexus_http_requests_total`` (Counter) and
``nexus_http_request_duration_seconds`` (Histogram) — labelled by
``method`` / ``route`` (matched template) / ``status`` — for every HTTP
request. The metrics surface on the existing Prometheus ``/metrics`` endpoint
(``register_metrics_endpoint``) because they live in the default registry.

Both label axes are bounded-cardinality: ``route`` is the matched route
TEMPLATE (never the concrete path — see ``_route_label`` below), and
``method`` is allowlisted to the standard HTTP verbs (never the raw,
client-controlled method token — see ``nexus.metrics._method_label``, the
single choke point both Prometheus instruments share via
``observe_http_request``). This middleware passes the raw
``scope["method"]`` through unmodified; the bound is applied downstream so
both instruments inherit it from one place.

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
import re
import time
from typing import Any, Dict

logger = logging.getLogger(__name__)

__all__ = ["RequestMetricsMiddleware"]

# Core-gateway entry points registered via ``kailash.servers.workflow_server``
# (``WorkflowServer.register_workflow`` / ``register_mcp_server``) mount a
# FRESH per-item FastAPI sub-app at a LITERAL path — ``/workflows/<name>`` or
# ``/mcp/<name>`` — where ``<name>`` is the registered workflow/server's own
# name, not a route template. Starlette's ``Mount.matches()`` does NOT set
# ``scope["route"]``; only the mounted sub-app's OWN router does, once it
# matches one of ITS routes (``/execute``, ``/health``, ``/status/{id}``,
# ...). Left as-is, ``scope["route"].path_format`` alone collapses every
# registered workflow's ``/execute`` call to the SAME label — worse, a
# per-workflow ``/health`` sub-route collides with the top-level gateway's
# OWN ``/health`` liveness probe in the SAME Prometheus series. These regexes
# recognize the two known per-item Mount prefixes so the label can be
# re-templated (``/workflows/{name}``) instead of left as the literal,
# per-registration path.
_WORKFLOW_MOUNT_RE = re.compile(r"^/workflows/[^/]+$")
_MCP_MOUNT_RE = re.compile(r"^/mcp/[^/]+$")


def _templated_mount_prefix(root_path: str) -> str:
    """Collapse a per-item Mount's literal ``root_path`` to a bounded template.

    Returns the original ``root_path`` unchanged when it does not match a
    known per-item mount shape (e.g. a static sub-app mounted once via
    ``Nexus.mount()`` — already bounded because it is operator-registered,
    not request-driven).
    """
    if _WORKFLOW_MOUNT_RE.match(root_path):
        return "/workflows/{name}"
    if _MCP_MOUNT_RE.match(root_path):
        return "/mcp/{name}"
    return root_path


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

    Requests dispatched THROUGH a Mount (core-gateway per-workflow /
    per-MCP-server sub-apps registered by ``WorkflowServer.register_workflow``
    / ``register_mcp_server``) carry the Mount's matched prefix in
    ``scope["root_path"]``. That prefix is re-templated via
    :func:`_templated_mount_prefix` and prepended to the sub-app's own
    matched route template, so ``/workflows/my_wf/execute`` and
    ``/workflows/other_wf/execute`` both aggregate under
    ``/workflows/{name}/execute`` instead of colliding with unrelated
    top-level routes (e.g. the gateway's own ``/health`` probe) under a bare
    ``/execute`` / ``/health`` label.
    """
    root_path = scope.get("root_path") or ""
    templated_root = _templated_mount_prefix(root_path) if root_path else ""

    route = scope.get("route")
    if route is not None:
        tmpl = getattr(route, "path_format", None) or getattr(route, "path", None)
        if tmpl:
            if templated_root:
                # Avoid a doubled slash when the inner template is "/" (the
                # sub-app's own root route).
                return templated_root + tmpl if tmpl != "/" else templated_root + "/"
            return tmpl

    # No FastAPI route matched (e.g. a plain-ASGI or non-FastAPI mounted
    # sub-app) — fall back to the templated mount prefix alone so the
    # request is still attributed instead of collapsing to "__unmatched__".
    if templated_root:
        return templated_root

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

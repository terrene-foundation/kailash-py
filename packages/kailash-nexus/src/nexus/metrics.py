# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Prometheus /metrics endpoint for Nexus.

Exposes internal performance deques from ``core.py`` as scrapeable
Prometheus metrics.  ``prometheus_client`` is an **optional** dependency
— install via ``pip install kailash-nexus[metrics]``.

Usage::

    from nexus import Nexus
    from nexus.metrics import register_metrics_endpoint

    app = Nexus()
    register_metrics_endpoint(app)
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from nexus.core import Nexus

logger = logging.getLogger(__name__)

__all__ = ["register_metrics_endpoint", "observe_http_request"]

# ---------------------------------------------------------------------------
# Lazy import helper
# ---------------------------------------------------------------------------

_MISSING_MSG = (
    "prometheus_client is required for the /metrics endpoint. "
    "Install it with: pip install kailash-nexus[metrics]"
)

# ---------------------------------------------------------------------------
# Method-label cardinality bound (#1708 HIGH — symmetric to route templating)
# ---------------------------------------------------------------------------

# RFC 7230 defines the HTTP method as an arbitrary `token` -- there is no
# protocol-level bound on its value, and ASGI servers forward whatever byte
# sequence the client sent (including non-standard tokens) verbatim in
# ``scope["method"]``. Left unbounded, a client sending a fresh method token
# per request (e.g. ``-X <random>``) mints a brand-new
# ``(method, route, status)`` Prometheus series on every single call -- the
# EXACT path-scanning cardinality-DoS the route TEMPLATE already defends
# against (see ``nexus/middleware/request_metrics.py::_route_label``), just
# on the orthogonal method axis. It fires even against unmatched/405 routes,
# before any auth check runs. This allowlist collapses every non-standard
# method token to the ``"_other"`` sentinel so the method label is bounded
# to a fixed, small cardinality regardless of client input.
_ALLOWED_HTTP_METHODS = frozenset(
    {
        "GET",
        "POST",
        "PUT",
        "PATCH",
        "DELETE",
        "HEAD",
        "OPTIONS",
        "TRACE",
        "CONNECT",
    }
)
_OTHER_METHOD_LABEL = "_other"


def _method_label(method: str) -> str:
    """Return a bounded-cardinality HTTP method label.

    Case-normalizes to upper-case and checks against the standard HTTP verb
    allowlist (RFC 7230 §3.1.1's ``token`` grammar permits ARBITRARY method
    strings, but only the 9 registered methods above are attributed by
    name). Any other value -- a malformed token, a client-injected random
    string, or the middleware's ``"UNKNOWN"`` fallback -- collapses to the
    ``"_other"`` sentinel, exactly mirroring how an unmatched route
    collapses to ``"__unmatched__"``.
    """
    normalized = method.upper()
    if normalized in _ALLOWED_HTTP_METHODS:
        return normalized
    return _OTHER_METHOD_LABEL


def _require_prometheus_client():
    """Lazily import prometheus_client, raising a helpful error if absent."""
    try:
        import prometheus_client  # noqa: F811
    except ImportError as exc:
        raise ImportError(_MISSING_MSG) from exc
    return prometheus_client


# ---------------------------------------------------------------------------
# Metric objects (created once, lazily)
# ---------------------------------------------------------------------------

_metrics_initialized = False

_workflow_registration_hist = None
_cross_channel_sync_hist = None
_failure_recovery_hist = None
_session_sync_latency_hist = None
_active_sessions_gauge = None
_registered_workflows_gauge = None

# Per-request HTTP metrics — created lazily + independently of the deque-synced
# metrics above so the request middleware can record without a registered
# /metrics endpoint (it still surfaces on /metrics because both use the
# prometheus DEFAULT registry).
_request_metrics_initialized = False
_http_requests_total = None
_http_request_duration_hist = None


def _init_request_metrics():
    """Create the per-request HTTP Prometheus metric objects on first use."""
    global _request_metrics_initialized  # noqa: PLW0603
    global _http_requests_total, _http_request_duration_hist  # noqa: PLW0603
    if _request_metrics_initialized:
        return

    pc = _require_prometheus_client()

    _http_requests_total = pc.Counter(
        "nexus_http_requests_total",
        "Total HTTP requests processed by Nexus",
        ["method", "route", "status"],
    )
    _http_request_duration_hist = pc.Histogram(
        "nexus_http_request_duration_seconds",
        "HTTP request latency in seconds by method/route/status",
        ["method", "route", "status"],
        buckets=(
            0.005,
            0.01,
            0.025,
            0.05,
            0.1,
            0.25,
            0.5,
            1.0,
            2.5,
            5.0,
            10.0,
        ),
    )

    _request_metrics_initialized = True


def observe_http_request(
    method: str, route: str, status: int, duration_seconds: float
) -> None:
    """Record one HTTP request into the per-request Nexus metrics.

    Increments ``nexus_http_requests_total`` and observes
    ``nexus_http_request_duration_seconds`` under the
    ``(method, route, status)`` label set. Called by
    :class:`~nexus.middleware.request_metrics.RequestMetricsMiddleware`.

    Args:
        method: HTTP method (e.g. ``"GET"``). Case-normalized and bounded to
            the standard HTTP verb allowlist before use as a label value —
            any other token (a malformed method, a client-injected random
            string) collapses to the ``"_other"`` sentinel. This mirrors the
            ``route`` bound below: the label is a member of a small, fixed
            set, never the raw client-controlled token, to bound
            cardinality. Applied here (not at the middleware call site) so
            BOTH instruments inherit the bound from one choke point.
        route: Matched route template (e.g. ``"/users/{id}"``), or the
            ``"__unmatched__"`` sentinel when no route matched — the label
            is the template, never the concrete path, to bound cardinality.
        status: HTTP status code.
        duration_seconds: Wall-clock request duration in seconds.

    Raises:
        ImportError: If ``prometheus_client`` is not installed.
    """
    _init_request_metrics()
    # _init_request_metrics() guarantees both objects are non-None; the assert
    # makes that explicit for static analysis of the lazy-init globals.
    assert _http_requests_total is not None  # noqa: S101
    assert _http_request_duration_hist is not None  # noqa: S101
    method_label = _method_label(method)
    status_label = str(status)
    _http_requests_total.labels(
        method=method_label, route=route, status=status_label
    ).inc()
    _http_request_duration_hist.labels(
        method=method_label, route=route, status=status_label
    ).observe(duration_seconds)


def _init_metrics():
    """Create Prometheus metric objects on first use."""
    global _metrics_initialized  # noqa: PLW0603
    global _workflow_registration_hist, _cross_channel_sync_hist  # noqa: PLW0603
    global _failure_recovery_hist, _session_sync_latency_hist  # noqa: PLW0603
    global _active_sessions_gauge, _registered_workflows_gauge  # noqa: PLW0603
    if _metrics_initialized:
        return

    pc = _require_prometheus_client()

    _workflow_registration_hist = pc.Histogram(
        "nexus_workflow_registration_seconds",
        "Time to register a workflow with Nexus",
        buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5),
    )
    _cross_channel_sync_hist = pc.Histogram(
        "nexus_cross_channel_sync_seconds",
        "Time to synchronise state across channels",
        buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25),
    )
    _failure_recovery_hist = pc.Histogram(
        "nexus_failure_recovery_seconds",
        "Time to recover from a workflow failure",
        buckets=(0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
    )
    _session_sync_latency_hist = pc.Histogram(
        "nexus_session_sync_latency_seconds",
        "Latency of session synchronisation",
        buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25),
    )
    _active_sessions_gauge = pc.Gauge(
        "nexus_active_sessions",
        "Number of currently active Nexus sessions",
    )
    _registered_workflows_gauge = pc.Gauge(
        "nexus_registered_workflows",
        "Number of workflows registered with Nexus",
    )

    _metrics_initialized = True


# ---------------------------------------------------------------------------
# Sync deques → Prometheus
# ---------------------------------------------------------------------------


def _sync_from_nexus(nexus: Nexus) -> None:
    """Read live deques from a Nexus instance and observe into histograms.

    This is called on every ``/metrics`` scrape so Prometheus always sees
    the latest values.  Deque values that have already been observed are
    tracked via a simple counter per metric so each value is observed
    exactly once.
    """
    _init_metrics()
    # _init_metrics() guarantees the metric objects are non-None; the asserts
    # make that explicit for static analysis of the lazy-init globals.
    assert _registered_workflows_gauge is not None  # noqa: S101
    assert _active_sessions_gauge is not None  # noqa: S101

    perf = getattr(nexus, "_performance_metrics", {})

    # Map internal deque names → Histogram objects
    histogram_map = {
        "workflow_registration_time": _workflow_registration_hist,
        "cross_channel_sync_time": _cross_channel_sync_hist,
        "failure_recovery_time": _failure_recovery_hist,
        "session_sync_latency": _session_sync_latency_hist,
    }

    # Each Nexus instance keeps a private offset dict so repeated scrapes
    # don't double-count observations.
    offsets = getattr(nexus, "_prom_offsets", None)
    if offsets is None:
        offsets = {k: 0 for k in histogram_map}
        nexus._prom_offsets = offsets  # type: ignore[attr-defined]

    for deque_name, hist in histogram_map.items():
        deque_obj = perf.get(deque_name)
        if deque_obj is None or hist is None:
            continue
        values = list(deque_obj)
        start = offsets.get(deque_name, 0)
        for v in values[start:]:
            hist.observe(v)
        offsets[deque_name] = len(values)

    # Gauges — snapshot of current state
    registry = getattr(nexus, "_registry", None)
    if registry is not None:
        wfs = registry.list_workflows()
        _registered_workflows_gauge.set(len(wfs))
    else:
        _registered_workflows_gauge.set(0)

    session_mgr = getattr(nexus, "_session_manager", None)
    if session_mgr is not None and hasattr(session_mgr, "active_sessions"):
        _active_sessions_gauge.set(session_mgr.active_sessions)
    else:
        _active_sessions_gauge.set(0)


# ---------------------------------------------------------------------------
# Endpoint registration
# ---------------------------------------------------------------------------


def register_metrics_endpoint(nexus: Nexus) -> None:
    """Register a ``GET /metrics`` endpoint on the Nexus HTTP transport.

    If the Core SDK gateway already registered a ``/metrics`` route, it is
    replaced so that Prometheus receives proper ``prometheus_client`` output
    that includes both Nexus-specific and any other collectors in the
    default registry.

    Args:
        nexus: A :class:`~nexus.core.Nexus` instance.

    Raises:
        ImportError: If ``prometheus_client`` is not installed.
    """
    pc = _require_prometheus_client()
    _init_metrics()

    async def metrics_handler():
        """Prometheus scrape handler."""
        from starlette.responses import Response

        _sync_from_nexus(nexus)
        body = pc.generate_latest()
        return Response(
            content=body,
            media_type="text/plain; version=0.0.4; charset=utf-8",
        )

    # Try to register on the FastAPI app directly so we can replace the
    # gateway's existing /metrics route.
    fastapi_app = getattr(nexus, "fastapi_app", None)
    if fastapi_app is None:
        http = getattr(nexus, "_http_transport", None)
        if http is not None:
            gw = getattr(http, "gateway", None)
            if gw is not None:
                fastapi_app = getattr(gw, "app", None)

    if fastapi_app is not None:
        # Remove any existing /metrics GET route registered by the gateway
        fastapi_app.routes[:] = [
            r
            for r in fastapi_app.routes
            if not (
                hasattr(r, "path")
                and r.path == "/metrics"
                and hasattr(r, "methods")
                and "GET" in r.methods
            )
        ]
        fastapi_app.get("/metrics")(metrics_handler)
        logger.info("Registered /metrics endpoint (Prometheus, replaced gateway route)")
    else:
        # Fallback: register via HTTPTransport queue
        http = getattr(nexus, "_http_transport", None)
        if http is not None:
            http.register_endpoint("/metrics", ["GET"], metrics_handler)
            logger.info("Registered /metrics endpoint (Prometheus)")
        else:
            logger.warning(
                "No HTTP transport found on Nexus instance — "
                "/metrics endpoint not registered"
            )

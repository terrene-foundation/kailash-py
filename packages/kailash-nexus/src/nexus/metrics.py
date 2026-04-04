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

__all__ = ["register_metrics_endpoint"]

# ---------------------------------------------------------------------------
# Lazy import helper
# ---------------------------------------------------------------------------

_MISSING_MSG = (
    "prometheus_client is required for the /metrics endpoint. "
    "Install it with: pip install kailash-nexus[metrics]"
)


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
        if deque_obj is None:
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
            gw = getattr(http, "_gateway", None)
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

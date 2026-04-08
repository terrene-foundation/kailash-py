# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""
Fabric Prometheus metrics (Phase 5.12).

Owns the process-wide ``FabricMetrics`` singleton that collects every
fabric counter, gauge, and histogram. The singleton is the single source
of truth for all subsystems (pipeline, cache, leader, webhook, serving),
which dispatch through ``get_fabric_metrics()`` instead of holding their
own metric handles.

Why a singleton:
- ``prometheus_client`` uses a process-wide registry. Constructing a
  second :class:`FabricMetrics` would attempt to re-register the same
  metric names and raise. The singleton avoids that by construction.
- All fabric subsystems must agree on the same Counter/Gauge/Histogram
  instances so a single ``/fabric/metrics`` scrape returns coherent
  values across pipeline + cache + leader + webhook.
- Tests use :func:`reset_fabric_metrics` to clear the registry between
  cases (the prometheus_client process-wide registry is shared, so
  tests must explicitly tear down).

Optional dependency:
``prometheus-client>=0.20`` is declared in the ``fabric`` extra (see
``pyproject.toml``). When the package is installed, FabricMetrics
registers real counters; when missing, every metric is a loud no-op
that logs a single startup warning so operators see why ``/fabric/
metrics`` is empty. Silent degradation to ``None`` is BLOCKED per
``rules/dependencies.md`` § Optional Extras with Loud Failure.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

__all__ = [
    "FabricMetrics",
    "get_fabric_metrics",
    "reset_fabric_metrics",
]


class _NoOpMetric:
    """No-op metric used when prometheus_client is not installed.

    Methods accept the same arguments as the real Counter / Gauge /
    Histogram so caller code never needs to branch. The first time
    :class:`FabricMetrics` is constructed without prometheus_client a
    single WARN is logged so operators are notified — there is no
    silent degradation to ``None``.
    """

    def labels(self, **kwargs: Any) -> "_NoOpMetric":
        return self

    def observe(self, value: float) -> None:
        pass

    def inc(self, amount: float = 1) -> None:
        pass

    def dec(self, amount: float = 1) -> None:
        pass

    def set(self, value: float) -> None:
        pass


_NOOP = _NoOpMetric()


class FabricMetrics:
    """Prometheus metrics for the fabric engine.

    Instantiated via :func:`get_fabric_metrics` (singleton). Direct
    construction is allowed for tests but the constructor is idempotent
    only if you also call :func:`reset_fabric_metrics` between
    instantiations — otherwise prometheus_client will raise on
    duplicate registration.

    Metric families (13 total, per the redteam observability plan):

    Counters:
    - ``fabric_pipeline_runs_total{product, status}``
    - ``fabric_cache_hit_total{product}``
    - ``fabric_cache_miss_total{product}``
    - ``fabric_cache_errors_total{backend, operation}``
    - ``fabric_request_total{product, freshness}``
    - ``fabric_webhook_received_total{source, accepted}``

    Gauges:
    - ``fabric_source_health{source}``
    - ``fabric_source_consecutive_failures{source}``
    - ``fabric_product_age_seconds{product}``
    - ``fabric_cache_degraded{backend}``
    - ``fabric_leader_status{instance}``

    Histograms:
    - ``fabric_pipeline_duration_seconds{product}``
    - ``fabric_request_duration_seconds{product}``
    - ``fabric_source_check_duration_seconds{source}``
    """

    def __init__(self) -> None:
        self._enabled = False
        try:
            from prometheus_client import (
                CONTENT_TYPE_LATEST,
                CollectorRegistry,
                Counter,
                Gauge,
                Histogram,
                generate_latest,
            )
        except ImportError:
            logger.warning(
                "fabric.metrics.prometheus_client_missing: "
                "prometheus-client is not installed. Fabric metrics will "
                "use no-op counters and the /fabric/metrics endpoint will "
                "return an explanatory message. Install the fabric extra "
                "to enable metrics: pip install 'kailash-dataflow[fabric]'.",
            )
            self._registry: Any = None
            self._content_type: str = "text/plain; version=0.0.4; charset=utf-8"
            self._generate_latest = None
            # Assign all metric handles to the no-op so callers never branch.
            self.source_health = _NOOP
            self.source_check_duration = _NOOP
            self.source_consecutive_failures = _NOOP
            self.pipeline_duration = _NOOP
            self.pipeline_runs_total = _NOOP
            self.cache_hit_total = _NOOP
            self.cache_miss_total = _NOOP
            self.cache_errors_total = _NOOP
            self.cache_degraded = _NOOP
            self.product_age_seconds = _NOOP
            self.request_duration = _NOOP
            self.request_total = _NOOP
            self.webhook_received_total = _NOOP
            self.leader_status = _NOOP
            return

        self._enabled = True
        # Use a fresh registry so tests can reset cleanly without colliding
        # with the global prometheus_client default registry.
        self._registry = CollectorRegistry()
        self._content_type = CONTENT_TYPE_LATEST
        self._generate_latest = generate_latest

        # Source metrics
        self.source_health = Gauge(
            "fabric_source_health",
            "Source health status (1=healthy, 0=unhealthy)",
            ["source"],
            registry=self._registry,
        )
        self.source_check_duration = Histogram(
            "fabric_source_check_duration_seconds",
            "Source change detection duration",
            ["source"],
            registry=self._registry,
        )
        self.source_consecutive_failures = Gauge(
            "fabric_source_consecutive_failures",
            "Consecutive source failures",
            ["source"],
            registry=self._registry,
        )

        # Pipeline metrics
        self.pipeline_duration = Histogram(
            "fabric_pipeline_duration_seconds",
            "Pipeline execution duration",
            ["product"],
            registry=self._registry,
        )
        self.pipeline_runs_total = Counter(
            "fabric_pipeline_runs_total",
            "Total pipeline runs",
            ["product", "status"],
            registry=self._registry,
        )

        # Cache metrics
        self.cache_hit_total = Counter(
            "fabric_cache_hit_total",
            "Cache hits",
            ["product"],
            registry=self._registry,
        )
        self.cache_miss_total = Counter(
            "fabric_cache_miss_total",
            "Cache misses",
            ["product"],
            registry=self._registry,
        )
        self.cache_errors_total = Counter(
            "fabric_cache_errors_total",
            "Cache backend errors",
            ["backend", "operation"],
            registry=self._registry,
        )
        self.cache_degraded = Gauge(
            "fabric_cache_degraded",
            "Cache backend in degraded mode (0=healthy, 1=degraded)",
            ["backend"],
            registry=self._registry,
        )
        self.product_age_seconds = Gauge(
            "fabric_product_age_seconds",
            "Product cache age in seconds",
            ["product"],
            registry=self._registry,
        )

        # Serving metrics
        self.request_duration = Histogram(
            "fabric_request_duration_seconds",
            "Request handling duration",
            ["product"],
            registry=self._registry,
        )
        self.request_total = Counter(
            "fabric_request_total",
            "Total requests",
            ["product", "freshness"],
            registry=self._registry,
        )

        # Webhook metrics
        self.webhook_received_total = Counter(
            "fabric_webhook_received_total",
            "Webhooks received",
            ["source", "accepted"],
            registry=self._registry,
        )

        # Leader metrics
        self.leader_status = Gauge(
            "fabric_leader_status",
            "Leader election status (1=leader, 0=follower)",
            ["instance"],
            registry=self._registry,
        )

        logger.debug("fabric.metrics.registered", extra={"families": 13})

    @property
    def enabled(self) -> bool:
        return self._enabled

    # ------------------------------------------------------------------
    # Recorder methods (used by every fabric subsystem)
    # ------------------------------------------------------------------

    def record_source_check(
        self, source: str, duration_s: float, healthy: bool
    ) -> None:
        """Record a source change detection check."""
        self.source_check_duration.labels(source=source).observe(duration_s)
        self.source_health.labels(source=source).set(1.0 if healthy else 0.0)

    def record_source_failure(self, source: str, failure_count: int) -> None:
        """Record source consecutive failures."""
        self.source_consecutive_failures.labels(source=source).set(failure_count)

    def record_pipeline_run(
        self, product: str, duration_s: float, success: bool
    ) -> None:
        """Record a pipeline execution."""
        self.pipeline_duration.labels(product=product).observe(duration_s)
        status = "success" if success else "failure"
        self.pipeline_runs_total.labels(product=product, status=status).inc()

    def record_cache_hit(self, product: str) -> None:
        self.cache_hit_total.labels(product=product).inc()

    def record_cache_miss(self, product: str) -> None:
        self.cache_miss_total.labels(product=product).inc()

    def record_cache_error(self, backend: str, operation: str) -> None:
        """Record a cache backend operational error."""
        self.cache_errors_total.labels(backend=backend, operation=operation).inc()

    def record_cache_degraded(self, backend: str, value: int) -> None:
        """Flip ``fabric_cache_degraded{backend}`` to 0 or 1.

        ``value`` MUST be 0 or 1; any other value is coerced to bool.
        """
        normalized = 1.0 if value else 0.0
        self.cache_degraded.labels(backend=backend).set(normalized)

    def record_product_age(self, product: str, age_seconds: float) -> None:
        self.product_age_seconds.labels(product=product).set(age_seconds)

    def record_request(self, product: str, duration_s: float, freshness: str) -> None:
        """Record a serving request."""
        self.request_duration.labels(product=product).observe(duration_s)
        self.request_total.labels(product=product, freshness=freshness).inc()

    def record_webhook(self, source: str, accepted: bool) -> None:
        """Record an inbound webhook."""
        self.webhook_received_total.labels(
            source=source, accepted="true" if accepted else "false"
        ).inc()

    def record_leader_status(self, instance: str, is_leader: bool) -> None:
        """Set the leader gauge for the given instance."""
        self.leader_status.labels(instance=instance).set(1.0 if is_leader else 0.0)

    # ------------------------------------------------------------------
    # /fabric/metrics endpoint
    # ------------------------------------------------------------------

    def render_exposition(self) -> bytes:
        """Render the registry in Prometheus text exposition format.

        When prometheus_client is not installed, returns a plaintext
        explanation so the endpoint never 500s and operators can see
        why metrics are empty without grepping logs.
        """
        if not self._enabled or self._generate_latest is None:
            return (
                b"# fabric metrics disabled: prometheus-client is not installed.\n"
                b"# Install with: pip install 'kailash-dataflow[fabric]'\n"
            )
        return bytes(self._generate_latest(self._registry))

    @property
    def content_type(self) -> str:
        """Content-Type header value for the /fabric/metrics endpoint."""
        return self._content_type

    def get_metrics_route(self) -> Dict[str, Any]:
        """Build the Nexus route dict for ``GET /fabric/metrics``.

        Returns a fabric-style route dict (the same shape used by
        :class:`FabricServingLayer.get_routes`) so the runtime can pass
        it through ``register_route_dicts``. The handler always returns
        a dict with ``_status``, ``_body``, and ``_headers`` so the
        nexus adapter renders it as a raw response (Prometheus
        exposition is text, not JSON).
        """
        metrics = self

        async def handler(request: Any = None) -> Dict[str, Any]:
            body = metrics.render_exposition()
            return {
                "_status": 200,
                "_body": body,
                "_headers": {"content-type": metrics.content_type},
            }

        handler.__name__ = "fabric_metrics"
        return {
            "method": "GET",
            "path": "/fabric/metrics",
            "handler": handler,
            "metadata": {"type": "metrics"},
        }


# ---------------------------------------------------------------------------
# Process-wide singleton
# ---------------------------------------------------------------------------


_FABRIC_METRICS_SINGLETON: Optional[FabricMetrics] = None


def get_fabric_metrics() -> FabricMetrics:
    """Return the process-wide :class:`FabricMetrics` singleton.

    Lazily constructs the instance on first access. Every fabric
    subsystem MUST go through this function so they share counters
    against a single registry — multiple instances would either
    fragment the data or raise on duplicate metric registration.
    """
    global _FABRIC_METRICS_SINGLETON
    if _FABRIC_METRICS_SINGLETON is None:
        _FABRIC_METRICS_SINGLETON = FabricMetrics()
    return _FABRIC_METRICS_SINGLETON


def reset_fabric_metrics() -> None:
    """Discard the singleton so the next ``get_fabric_metrics`` rebuilds it.

    Tests use this between cases to clear the prometheus_client
    registry. Production code SHOULD NOT call this — re-registering
    metrics during a request flight loses all in-flight observations
    and confuses /fabric/metrics scrapers.
    """
    global _FABRIC_METRICS_SINGLETON
    _FABRIC_METRICS_SINGLETON = None

# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""
Fabric Prometheus metrics (TODO-21).

Uses prometheus_client if available, otherwise no-op metrics. All metric
names use the ``fabric_`` prefix to avoid collisions with existing DataFlow
metrics.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

__all__ = ["FabricMetrics"]


class _NoOpMetric:
    """No-op metric when prometheus_client is not installed."""

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

    If prometheus_client is installed, registers real metrics.
    Otherwise, all operations are silent no-ops.
    """

    def __init__(self) -> None:
        self._enabled = False
        try:
            from prometheus_client import Counter, Gauge, Histogram

            self._enabled = True

            # Source metrics
            self.source_health = Gauge(
                "fabric_source_health",
                "Source health status (1=healthy, 0=unhealthy)",
                ["source"],
            )
            self.source_check_duration = Histogram(
                "fabric_source_check_duration_seconds",
                "Source change detection duration",
                ["source"],
            )
            self.source_consecutive_failures = Gauge(
                "fabric_source_consecutive_failures",
                "Consecutive source failures",
                ["source"],
            )

            # Pipeline metrics
            self.pipeline_duration = Histogram(
                "fabric_pipeline_duration_seconds",
                "Pipeline execution duration",
                ["product"],
            )
            self.pipeline_runs_total = Counter(
                "fabric_pipeline_runs_total",
                "Total pipeline runs",
                ["product", "status"],
            )

            # Cache metrics
            self.cache_hit_total = Counter(
                "fabric_cache_hit_total",
                "Cache hits",
                ["product"],
            )
            self.cache_miss_total = Counter(
                "fabric_cache_miss_total",
                "Cache misses",
                ["product"],
            )
            self.product_age_seconds = Gauge(
                "fabric_product_age_seconds",
                "Product cache age in seconds",
                ["product"],
            )

            # Serving metrics
            self.request_duration = Histogram(
                "fabric_request_duration_seconds",
                "Request handling duration",
                ["product"],
            )
            self.request_total = Counter(
                "fabric_request_total",
                "Total requests",
                ["product", "freshness"],
            )

            logger.debug("Fabric Prometheus metrics registered")

        except ImportError:
            # No prometheus_client — use no-ops
            self.source_health = _NOOP
            self.source_check_duration = _NOOP
            self.source_consecutive_failures = _NOOP
            self.pipeline_duration = _NOOP
            self.pipeline_runs_total = _NOOP
            self.cache_hit_total = _NOOP
            self.cache_miss_total = _NOOP
            self.product_age_seconds = _NOOP
            self.request_duration = _NOOP
            self.request_total = _NOOP
            logger.debug("prometheus_client not installed — fabric metrics disabled")

    @property
    def enabled(self) -> bool:
        return self._enabled

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

    def record_product_age(self, product: str, age_seconds: float) -> None:
        self.product_age_seconds.labels(product=product).set(age_seconds)

    def record_request(self, product: str, duration_s: float, freshness: str) -> None:
        """Record a serving request."""
        self.request_duration.labels(product=product).observe(duration_s)
        self.request_total.labels(product=product, freshness=freshness).inc()

# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""ML-lifecycle observability — Prometheus + OpenTelemetry (kailash 2.9.0, spec §6).

Three standard counters:

  - ``kailash_ml_train_duration_seconds`` (Histogram)
    Labels: engine_name, model_name, tenant_id_bucket
  - ``kailash_ml_inference_latency_ms`` (Histogram)
    Labels: model_name, version, tenant_id_bucket
  - ``kailash_ml_drift_alerts_total`` (Counter)
    Labels: feature_name, severity, tenant_id_bucket

Bounded-cardinality discipline (per ``rules/tenant-isolation.md`` §4):
``tenant_id_bucket`` uses top-N + ``"_other"`` bucketing so the
metric cardinality never grows unbounded. The default top-N is 100;
override with ``KAILASH_ML_METRICS_TOP_TENANTS=<N>``.

OTel bridge: when ``opentelemetry-api`` is installed, the same metrics
are exposed via the OTel SDK using identical names + labels. Operators
running a Prom+OTel stack see the same series in both surfaces.

No-op fallback (per ``rules/zero-tolerance.md`` § "No Stubs — Fake
metrics"): when ``prometheus_client`` is NOT installed, the counters
become no-ops AND:

  1. A loud WARN logs at import time: ``"prometheus_client not
     installed; kailash_ml metrics are silent. Install
     kailash[observability] to enable."``
  2. ``metrics_endpoint_body()`` returns an explanatory string instead
     of the Prometheus wire format, so the ``/metrics`` endpoint body
     itself tells the operator what to install.

The fake-metrics pattern from DataFlow 2.0 Phase 5.12 is explicitly
disallowed — every counter method either records real data or is
accompanied by a loud WARN.
"""

from __future__ import annotations

import logging
import os
import threading
from collections import Counter as _CollectionsCounter
from typing import Any, Optional

logger = logging.getLogger(__name__)

__all__ = [
    "record_train_duration",
    "record_inference_latency",
    "record_drift_alert",
    "metrics_endpoint_body",
    "PROMETHEUS_AVAILABLE",
    "OTEL_AVAILABLE",
    "TOP_TENANTS_DEFAULT",
]


TOP_TENANTS_DEFAULT = 100


# ---------------------------------------------------------------------------
# Bounded-cardinality tenant bucketing
# ---------------------------------------------------------------------------


class _TenantBucketer:
    """Thread-safe top-N-by-traffic tenant bucket tracker.

    Per ``rules/tenant-isolation.md`` §4: tenant_id-as-label MUST be
    bounded. This tracker admits the top-N tenants (by lifetime
    observation count) and buckets the rest as ``"_other"``. The
    admission decision is monotonic within a process — once a tenant
    is admitted it stays admitted; promotions of newcomers past the
    cutoff happen only when an unseen tenant has more observations
    than the currently-lowest-observed admitted tenant (so the policy
    is not a pure FIFO/LRU; it is "top-N by cumulative count").

    Thread-safe: a lock guards admission + the counts dict.
    """

    def __init__(self, top_n: int) -> None:
        if not isinstance(top_n, int) or top_n <= 0:
            raise ValueError(f"top_n must be positive int, got {top_n!r}")
        self._top_n = top_n
        self._counts: _CollectionsCounter[str] = _CollectionsCounter()
        self._admitted: set[str] = set()
        self._lock = threading.Lock()

    def bucket(self, tenant_id: str) -> str:
        if not isinstance(tenant_id, str) or tenant_id == "":
            raise ValueError(
                "tenant_id must be non-empty str (rules/tenant-isolation.md §2)"
            )
        with self._lock:
            self._counts[tenant_id] += 1
            if tenant_id in self._admitted:
                return tenant_id
            if len(self._admitted) < self._top_n:
                self._admitted.add(tenant_id)
                return tenant_id
            # Admission competition: if the new tenant's count exceeds
            # the lowest admitted tenant's count, promote it.
            admitted_counts = {t: self._counts[t] for t in self._admitted}
            lowest_tenant = min(admitted_counts, key=admitted_counts.get)
            if self._counts[tenant_id] > admitted_counts[lowest_tenant]:
                self._admitted.remove(lowest_tenant)
                self._admitted.add(tenant_id)
                return tenant_id
            return "_other"

    def reset_for_tests(self) -> None:
        """Reset the bucket admission state — tests only."""
        with self._lock:
            self._counts.clear()
            self._admitted.clear()


def _top_n_from_env() -> int:
    raw = os.environ.get("KAILASH_ML_METRICS_TOP_TENANTS")
    if raw is None or raw == "":
        return TOP_TENANTS_DEFAULT
    try:
        val = int(raw)
    except ValueError:
        logger.warning(
            "ml_metrics.bad_env_top_n",
            extra={"raw": raw, "fallback": TOP_TENANTS_DEFAULT},
        )
        return TOP_TENANTS_DEFAULT
    if val <= 0:
        logger.warning(
            "ml_metrics.bad_env_top_n",
            extra={"raw": raw, "fallback": TOP_TENANTS_DEFAULT},
        )
        return TOP_TENANTS_DEFAULT
    return val


_bucketer = _TenantBucketer(top_n=_top_n_from_env())


def _bucket_tenant(tenant_id: str) -> str:
    """Public bucket delegate — used by workflow.nodes.ml for log labels."""
    return _bucketer.bucket(tenant_id)


def _reset_bucketer_for_tests(top_n: Optional[int] = None) -> None:
    """Test-only: reset the module-global bucketer."""
    global _bucketer
    _bucketer = _TenantBucketer(top_n=top_n or _top_n_from_env())


# ---------------------------------------------------------------------------
# Prometheus / OTel wiring
# ---------------------------------------------------------------------------


try:
    from prometheus_client import Counter, Histogram

    PROMETHEUS_AVAILABLE = True
except ImportError:  # pragma: no cover — loud warn covered by test
    PROMETHEUS_AVAILABLE = False
    logger.warning(
        "ml_metrics.prometheus_missing",
        extra={
            "source": "kailash.observability.ml",
            "fix": "pip install kailash[observability]",
        },
    )
    # Emit a visible startup warning to stderr too, since log config may
    # not yet be initialised when observability is first imported.
    import warnings as _warnings

    _warnings.warn(
        "prometheus_client not installed; kailash_ml metrics are silent. "
        "Install kailash[observability] to enable.",
        UserWarning,
        stacklevel=2,
    )


try:
    from opentelemetry import metrics as _otel_metrics  # type: ignore[import]

    OTEL_AVAILABLE = True
except ImportError:  # pragma: no cover
    OTEL_AVAILABLE = False


# Training duration — Histogram
_TRAIN_BUCKETS = (1, 5, 30, 60, 300, 900, 1800, 3600, 7200, 14400)
_INFER_BUCKETS = (1, 5, 10, 25, 50, 100, 250, 500, 1000, 2500)

if PROMETHEUS_AVAILABLE:
    _train_duration = Histogram(
        "kailash_ml_train_duration_seconds",
        "Training duration per engine, per tier (bounded-cardinality tenant label)",
        labelnames=["engine_name", "model_name", "tenant_id_bucket"],
        buckets=_TRAIN_BUCKETS,
    )
    _inference_latency = Histogram(
        "kailash_ml_inference_latency_ms",
        "Inference latency per model, per version (bounded-cardinality tenant label)",
        labelnames=["model_name", "version", "tenant_id_bucket"],
        buckets=_INFER_BUCKETS,
    )
    _drift_alerts = Counter(
        "kailash_ml_drift_alerts_total",
        "Drift alerts by feature and severity (bounded-cardinality tenant label)",
        labelnames=["feature_name", "severity", "tenant_id_bucket"],
    )
else:
    _train_duration = None
    _inference_latency = None
    _drift_alerts = None


# OpenTelemetry instruments — lazily created via the OTel meter provider
# at first recording when OTEL_AVAILABLE. If OTel is not installed, these
# remain None and only the Prometheus path records.
_otel_train: Any = None
_otel_infer: Any = None
_otel_drift: Any = None


def _otel_instruments() -> None:
    """Lazily initialise OTel instruments at first recording."""
    global _otel_train, _otel_infer, _otel_drift
    if not OTEL_AVAILABLE:
        return
    if _otel_train is not None:
        return
    meter = _otel_metrics.get_meter("kailash.observability.ml")
    _otel_train = meter.create_histogram(
        name="kailash_ml_train_duration_seconds",
        unit="s",
        description="Training duration per engine, per tier",
    )
    _otel_infer = meter.create_histogram(
        name="kailash_ml_inference_latency_ms",
        unit="ms",
        description="Inference latency per model, per version",
    )
    _otel_drift = meter.create_counter(
        name="kailash_ml_drift_alerts_total",
        description="Drift alerts by feature and severity",
    )


# ---------------------------------------------------------------------------
# Public recording API
# ---------------------------------------------------------------------------


def record_train_duration(
    *, engine_name: str, model_name: str, tenant_id: str, duration_s: float
) -> None:
    """Record a training duration in seconds.

    Emits to both Prometheus (if installed) and OTel (if installed).
    ``tenant_id`` is bucketed via the top-N bounded-cardinality tracker
    before landing as a metric label (per ``rules/tenant-isolation.md`` §4).
    """
    if not isinstance(duration_s, (int, float)) or isinstance(duration_s, bool):
        raise TypeError(f"duration_s must be numeric, got {type(duration_s).__name__}")
    if duration_s < 0:
        raise ValueError(f"duration_s must be non-negative, got {duration_s}")
    bucket = _bucket_tenant(tenant_id)
    if PROMETHEUS_AVAILABLE:
        _train_duration.labels(
            engine_name=engine_name,
            model_name=model_name,
            tenant_id_bucket=bucket,
        ).observe(float(duration_s))
    if OTEL_AVAILABLE:
        _otel_instruments()
        _otel_train.record(
            float(duration_s),
            attributes={
                "engine_name": engine_name,
                "model_name": model_name,
                "tenant_id_bucket": bucket,
            },
        )
    logger.debug(
        "ml_metric.train_duration",
        extra={
            "engine_name": engine_name,
            "model_name": model_name,
            "tenant_id_bucket": bucket,
            "duration_s": float(duration_s),
        },
    )


def record_inference_latency(
    *, model_name: str, version: str, tenant_id: str, latency_ms: float
) -> None:
    """Record an inference latency in milliseconds."""
    if not isinstance(latency_ms, (int, float)) or isinstance(latency_ms, bool):
        raise TypeError(f"latency_ms must be numeric, got {type(latency_ms).__name__}")
    if latency_ms < 0:
        raise ValueError(f"latency_ms must be non-negative, got {latency_ms}")
    bucket = _bucket_tenant(tenant_id)
    if PROMETHEUS_AVAILABLE:
        _inference_latency.labels(
            model_name=model_name,
            version=str(version),
            tenant_id_bucket=bucket,
        ).observe(float(latency_ms))
    if OTEL_AVAILABLE:
        _otel_instruments()
        _otel_infer.record(
            float(latency_ms),
            attributes={
                "model_name": model_name,
                "version": str(version),
                "tenant_id_bucket": bucket,
            },
        )
    logger.debug(
        "ml_metric.inference_latency",
        extra={
            "model_name": model_name,
            "version": str(version),
            "tenant_id_bucket": bucket,
            "latency_ms": float(latency_ms),
        },
    )


def record_drift_alert(
    *, feature_name: str, severity: str, tenant_id: str, count: int = 1
) -> None:
    """Record a drift alert.

    ``severity`` is typically one of ``"low"``, ``"medium"``, ``"high"``,
    ``"critical"`` — the observability layer does not enforce the
    vocabulary so drift monitors can use whatever severity lattice
    their policy supports.
    """
    if not isinstance(count, int) or isinstance(count, bool) or count < 1:
        raise ValueError(f"count must be positive int, got {count!r}")
    bucket = _bucket_tenant(tenant_id)
    if PROMETHEUS_AVAILABLE:
        _drift_alerts.labels(
            feature_name=feature_name,
            severity=severity,
            tenant_id_bucket=bucket,
        ).inc(count)
    if OTEL_AVAILABLE:
        _otel_instruments()
        _otel_drift.add(
            count,
            attributes={
                "feature_name": feature_name,
                "severity": severity,
                "tenant_id_bucket": bucket,
            },
        )
    logger.debug(
        "ml_metric.drift_alert",
        extra={
            "feature_name": feature_name,
            "severity": severity,
            "tenant_id_bucket": bucket,
            "count": count,
        },
    )


def metrics_endpoint_body() -> str:
    """Return the body content for a ``/metrics`` endpoint.

    When ``prometheus_client`` is installed, returns the standard
    ``generate_latest()`` exposition. When it is NOT installed, returns
    a loud explanatory body so the operator sees the missing-extra hint
    directly on the endpoint (not only in logs).
    """
    if not PROMETHEUS_AVAILABLE:
        return (
            "# kailash_ml metrics are not available.\n"
            "# prometheus_client is not installed.\n"
            "# Install kailash[observability] to enable.\n"
        )
    from prometheus_client import generate_latest  # type: ignore[import]

    return generate_latest().decode("utf-8")

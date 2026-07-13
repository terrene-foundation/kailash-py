# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""
DataFlow per-query RED latency histogram (#1708 Wave 3).

Owns the process-wide :class:`DataFlowQueryMetrics` singleton -- the
real bucketed-histogram counterpart to the OTel-span-attribute-only
instrumentation in ``kailash.runtime.instrumentation.dataflow`` (audit
dim 2/3: "DB general query = OTel span attr only"). That span
attribute (``db.duration_s``) records one number per query on one
trace; it is never aggregated, never exported as ``le``-bucketed
data, and cannot answer "what is p95 query latency for the ``list``
operation on ``Order``?" without a full trace backend.

This module mirrors ``dataflow.fabric.metrics.FabricMetrics`` --  the
pattern the #1708 audit cited as the CORRECT reference
implementation:

- A fresh ``CollectorRegistry`` (NOT the ``prometheus_client`` global
  registry) so tests can reset cleanly between cases.
- Loud no-op degradation when ``prometheus_client`` is not installed
  (it lives behind the ``fabric`` extra, so ``dataflow_query_duration_
  seconds`` is silent -- not a crash -- on a bare ``pip install
  kailash-dataflow``).
- A single process-wide singleton every call site dispatches through,
  never holding its own metric handles.

Wired into the REAL query execution path
(``dataflow.features.express.DataFlowExpress._execute_with_timing``),
which every ``db.express`` CRUD call
(create/read/update/delete/list/find_one/count/upsert/upsert_advanced/
bulk_create/bulk_update/bulk_delete/bulk_upsert) already routes
through for elapsed-time bookkeeping -- ``db.express`` is the
framework-mandated default CRUD path (~23x faster than
``WorkflowBuilder``; see ``rules/patterns.md`` /
``framework-first.md``), so this is the general DataFlow query
execution hot path, not a side path a subset of callers happen to
use.

Bounded labels (per ``rules/observability.md`` § "Explicit second-
scale buckets" + ``rules/tenant-isolation.md`` § "Metric Labels Carry
Tenant_id (Bounded)" -- the same bounded-cardinality discipline
applied to the ``operation`` / ``model`` dimensions instead of
``tenant_id``):

- ``operation`` -- a FIXED, finite enum of DataFlow CRUD verbs
  (see :data:`_KNOWN_OPERATIONS`). Anything outside the enum
  collapses to ``"_other"`` so this dimension can never grow.
- ``model`` -- top-N-by-first-seen bucketing (default cap 100,
  overridable via the ``model_cardinality_cap`` constructor arg).
  Once the cap is reached, every additional distinct model name
  collapses to ``"_other"`` so an application with many (or
  adversarially-supplied) model names cannot blow up Prometheus
  label cardinality.

Explicit second-scale buckets (G1 learning from #1708 Wave 1: default
``prometheus_client`` buckets bottom out at 5ms, but
``db.express`` operations run in the 0.1-0.3ms range per the
``ExpressDataFlow`` module docstring -- with default buckets, every
single observation would land in the same lowest bucket, making
p95/p99 meaningless). See :data:`_BUCKETS`.
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Optional, Set

logger = logging.getLogger(__name__)

__all__ = [
    "DataFlowQueryMetrics",
    "get_dataflow_query_metrics",
    "reset_dataflow_query_metrics",
]


# ---------------------------------------------------------------------------
# Bounded-label constants
# ---------------------------------------------------------------------------

# The finite set of DataFlow Express CRUD verbs. Every
# ``DataFlowExpress`` public method routes its operation name through
# ``_execute_with_timing`` using exactly one of these strings (see
# ``dataflow.features.express``). Anything else (a future operation
# added without updating this enum, or a malformed caller) buckets to
# ``_OPERATION_OVERFLOW`` rather than creating a new label value.
_KNOWN_OPERATIONS = frozenset(
    {
        "create",
        "read",
        "update",
        "delete",
        "list",
        "find_one",
        "count",
        "upsert",
        "upsert_advanced",
        "bulk_create",
        "bulk_update",
        "bulk_delete",
        "bulk_upsert",
    }
)
_OPERATION_OVERFLOW = "_other"
_MODEL_OVERFLOW = "_other"
_MODEL_UNKNOWN = "_unknown"
_MODEL_CARDINALITY_CAP_DEFAULT = 100

# Explicit second-scale histogram buckets, tuned for DataFlow query
# latency (sub-millisecond Express hits through multi-second bulk
# operations). MUST be declared explicitly -- see module docstring.
_BUCKETS = (
    0.0005,
    0.001,
    0.0025,
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
)


class _NoOpHistogram:
    """No-op histogram used when ``prometheus_client`` is not installed.

    Mirrors ``dataflow.fabric.metrics._NoOpMetric`` so
    :class:`DataFlowQueryMetrics` callers never need to branch on
    whether the real dependency is present.
    """

    def labels(self, **kwargs: Any) -> "_NoOpHistogram":
        return self

    def observe(self, value: float) -> None:
        pass


_NOOP = _NoOpHistogram()


class _ModelBucketer:
    """Thread-safe bounded-cardinality tracker for the ``model`` label.

    First-N-distinct-models-seen (within one process lifetime) are
    admitted verbatim; every model name beyond the cap collapses to
    ``"_other"``. This is the same "top-N + _other" bounded-label
    discipline ``rules/tenant-isolation.md`` § 4 mandates for
    ``tenant_id`` labels, applied here to ``model``.
    """

    def __init__(self, cap: int = _MODEL_CARDINALITY_CAP_DEFAULT) -> None:
        self._cap = cap
        self._admitted: Set[str] = set()
        self._lock = threading.Lock()

    def bucket(self, model: str) -> str:
        with self._lock:
            if model in self._admitted:
                return model
            if len(self._admitted) < self._cap:
                self._admitted.add(model)
                return model
            return _MODEL_OVERFLOW


class DataFlowQueryMetrics:
    """Prometheus RED-duration histogram for the DataFlow query path.

    Instantiated via :func:`get_dataflow_query_metrics` (singleton).
    Direct construction is allowed for tests but is only idempotent if
    paired with :func:`reset_dataflow_query_metrics` between
    instantiations -- otherwise ``prometheus_client`` raises on
    duplicate registration (same contract as
    ``dataflow.fabric.metrics.FabricMetrics``).

    Histogram:
    - ``dataflow_query_duration_seconds{operation, model}``
    """

    def __init__(
        self, model_cardinality_cap: int = _MODEL_CARDINALITY_CAP_DEFAULT
    ) -> None:
        self._enabled = False
        self._model_bucketer = _ModelBucketer(cap=model_cardinality_cap)

        try:
            from prometheus_client import (
                CONTENT_TYPE_LATEST,
                CollectorRegistry,
                Histogram,
                generate_latest,
            )
        except ImportError:
            logger.warning(
                "dataflow.observability.query_metrics.prometheus_client_missing: "
                "prometheus-client is not installed. dataflow_query_duration_seconds "
                "will use a no-op histogram and produce no scrape output. Install "
                "the fabric extra to enable metrics: "
                "pip install 'kailash-dataflow[fabric]'.",
            )
            self._registry: Any = None
            self._content_type: str = "text/plain; version=0.0.4; charset=utf-8"
            self._generate_latest = None
            self.query_duration = _NOOP
            return

        self._enabled = True
        # Fresh registry (not the prometheus_client default/global one) --
        # see module docstring + FabricMetrics precedent: tests reset
        # cleanly and this metric never collides with whatever registry
        # the host application's own /metrics endpoint scrapes from.
        self._registry = CollectorRegistry()
        self._content_type = CONTENT_TYPE_LATEST
        self._generate_latest = generate_latest

        self.query_duration = Histogram(
            "dataflow_query_duration_seconds",
            "DataFlow query execution duration in seconds, by operation and model",
            ["operation", "model"],
            buckets=_BUCKETS,
            registry=self._registry,
        )

        logger.debug("dataflow.observability.query_metrics.registered")

    @property
    def enabled(self) -> bool:
        return self._enabled

    @staticmethod
    def _bound_operation(operation: str) -> str:
        return operation if operation in _KNOWN_OPERATIONS else _OPERATION_OVERFLOW

    def record_query(self, operation: str, model: str, duration_s: float) -> None:
        """Record one query's wall-clock duration.

        Called from the real DataFlow query-execution hot path
        (``dataflow.features.express.DataFlowExpress.
        _execute_with_timing``) on EVERY ``db.express`` CRUD call --
        success or failure, since ``_execute_with_timing`` records
        timing from a ``finally`` block.

        Args:
            operation: One of :data:`_KNOWN_OPERATIONS`; any other
                value is bounded to ``"_other"``.
            model: The DataFlow model name; bounded to the first
                ``model_cardinality_cap`` distinct values seen, with
                overflow bucketed to ``"_other"``.
            duration_s: Wall-clock duration in seconds.
        """
        op = self._bound_operation(operation)
        mdl = self._model_bucketer.bucket(model) if model else _MODEL_UNKNOWN
        self.query_duration.labels(operation=op, model=mdl).observe(duration_s)

    # ------------------------------------------------------------------
    # Scrape / reader surface
    # ------------------------------------------------------------------

    def render_exposition(self) -> bytes:
        """Render the registry in Prometheus text exposition format.

        When ``prometheus_client`` is not installed, returns a
        plaintext explanation so a caller scraping this surface never
        gets an empty 200 with no indication why.
        """
        if not self._enabled or self._generate_latest is None:
            return (
                b"# dataflow query metrics disabled: prometheus-client is not installed.\n"
                b"# Install with: pip install 'kailash-dataflow[fabric]'\n"
            )
        return bytes(self._generate_latest(self._registry))

    @property
    def content_type(self) -> str:
        """Content-Type header value for a ``/metrics``-style scrape."""
        return self._content_type


# ---------------------------------------------------------------------------
# Process-wide singleton
# ---------------------------------------------------------------------------


_DATAFLOW_QUERY_METRICS_SINGLETON: Optional[DataFlowQueryMetrics] = None
_SINGLETON_LOCK = threading.Lock()


def get_dataflow_query_metrics() -> DataFlowQueryMetrics:
    """Return the process-wide :class:`DataFlowQueryMetrics` singleton.

    Lazily constructs the instance on first access. Every DataFlow
    query-execution call site MUST go through this function so they
    share one Histogram against one registry -- multiple instances
    would either fragment the data or raise on duplicate metric
    registration (same contract as
    ``dataflow.fabric.metrics.get_fabric_metrics``).
    """
    global _DATAFLOW_QUERY_METRICS_SINGLETON
    if _DATAFLOW_QUERY_METRICS_SINGLETON is None:
        with _SINGLETON_LOCK:
            if _DATAFLOW_QUERY_METRICS_SINGLETON is None:
                _DATAFLOW_QUERY_METRICS_SINGLETON = DataFlowQueryMetrics()
    return _DATAFLOW_QUERY_METRICS_SINGLETON


def reset_dataflow_query_metrics() -> None:
    """Discard the singleton so the next call rebuilds it.

    Tests use this between cases to clear the ``prometheus_client``
    registry. Production code SHOULD NOT call this.
    """
    global _DATAFLOW_QUERY_METRICS_SINGLETON
    with _SINGLETON_LOCK:
        _DATAFLOW_QUERY_METRICS_SINGLETON = None

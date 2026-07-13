# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Prometheus-compatible metrics bridge for Kailash runtime.

Exposes workflow and node execution metrics as OTel metric instruments.  When a
Prometheus exporter is configured these appear as standard Prometheus
counters and histograms:

- ``kailash_workflow_executions_total``    -- Counter of workflow runs.
- ``kailash_workflow_duration_seconds``    -- Histogram of workflow durations.
- ``kailash_node_execution_duration_seconds`` -- Histogram of per-node durations.

History-store audit-log counters (issue #876):

- ``kailash_history_store_record_event_dropped_total`` -- Counter of
  audit-log writes skipped (typed MissingRunIdError observed by the
  runtime subscriber-error handler).
- ``kailash_history_store_payload_decode_failed_total`` -- Counter of
  ``get_run_events`` payload-decode failures.
- ``kailash_history_store_per_tenant_cap_evicted_total`` -- Counter of
  per-tenant-cap eviction sweeps (sum of evicted rows).
- ``kailash_history_store_retention_swept_total`` -- Counter of
  retention sweep deletions (sum of deleted rows).

All instruments degrade gracefully when ``opentelemetry-api`` is not installed.
Included in the base install (``pip install kailash``).
"""

from __future__ import annotations

import logging
import re
import threading
from typing import Any, Optional

logger = logging.getLogger(__name__)

__all__ = ["MetricsBridge", "get_metrics_bridge", "sanitize_workflow_name"]

# Lazy OTel metrics import.
_OTEL_METRICS_AVAILABLE = False
_metrics_mod: Any = None

try:
    from opentelemetry import metrics as _otel_metrics_module

    _metrics_mod = _otel_metrics_module
    _OTEL_METRICS_AVAILABLE = True
except ImportError:
    pass

# Second-scale explicit bucket boundaries for the workflow-duration histogram
# (issue #1708 W1f). OTel's DEFAULT histogram buckets are millisecond-scale
# (tuned for HTTP request latency: 0, 5, 10, 25 ... 10000) and are useless for
# workflow executions that commonly run from tens of milliseconds to several
# minutes -- every real workflow duration lands in the single top overflow
# bucket, so p95/p99 queries return meaningless results. These boundaries are
# supplied as ``explicit_bucket_boundaries_advisory`` at instrument-creation
# time, which the OTel SDK's default histogram aggregation honors directly
# (no separate View registration required).
WORKFLOW_DURATION_BUCKETS_SECONDS: tuple[float, ...] = (
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
    30.0,
    60.0,
    120.0,
    300.0,
    600.0,
)

# ``WorkflowBuilder.build()`` defaults an unnamed workflow's ``name`` to
# ``f"Workflow-{workflow_id[:8]}"`` -- an 8-hex-char fragment of a fresh
# ``uuid4()`` minted on *every* ``.build()`` call (see
# ``kailash.workflow.builder.WorkflowBuilder.build``). Recording that value
# verbatim as a metric label/attribute is the SAME unbounded-cardinality bomb
# issue #1708 (Wave 1d) fixed for the raw ``workflow_id``: a long-lived
# Prometheus/OTel scrape target would mint a brand-new time series on every
# execution for any caller that does not explicitly name their workflow.
_AUTO_GENERATED_WORKFLOW_NAME_RE = re.compile(r"^Workflow-[0-9a-fA-F]{8}$")

# Bounded sentinel substituted for auto-generated / missing workflow names.
_UNNAMED_WORKFLOW_LABEL = "unnamed_workflow"


def sanitize_workflow_name(workflow_name: Optional[str]) -> str:
    """Collapse an auto-generated per-build workflow name to a bounded sentinel.

    Explicitly-named workflows (``WorkflowBuilder(name="orders")`` or
    ``.build(name="orders")``) pass through unchanged -- those names are
    bounded by the caller's own naming discipline. Unnamed workflows,
    whose ``name`` defaults to ``f"Workflow-{workflow_id[:8]}"``, collapse
    to a single stable label so the RED metrics stay bounded regardless of
    how many anonymous workflows execute (issue #1708 W1f).

    Args:
        workflow_name: The raw ``workflow.name`` value (or ``None``).

    Returns:
        A bounded label value safe to use as a metric attribute.
    """
    if not workflow_name or _AUTO_GENERATED_WORKFLOW_NAME_RE.match(workflow_name):
        return _UNNAMED_WORKFLOW_LABEL
    return workflow_name


class MetricsBridge:
    """Prometheus-compatible metrics instruments backed by OTel.

    All recording methods are safe no-ops when ``opentelemetry`` is absent.

    Attributes:
        enabled: Whether OTel metrics API is available.
    """

    def __init__(self, meter_name: str = "kailash") -> None:
        self._lock = threading.Lock()
        self._enabled = _OTEL_METRICS_AVAILABLE

        self._workflow_counter: Any = None
        self._workflow_duration: Any = None
        self._node_duration: Any = None
        # History-store audit-log counters (issue #876 C-1 + C-2b).
        self._history_store_dropped: Any = None
        self._history_store_payload_decode_failed: Any = None
        self._history_store_per_tenant_cap_evicted: Any = None
        self._history_store_retention_swept: Any = None
        # Best-effort in-memory cumulative counter mirror.  Tests assert
        # against this; when OTel is unavailable the OTel instruments
        # are no-ops but the in-memory counts still increment so the
        # callsite + handler wiring is observable.  Keyed by counter
        # name (matches the OTel instrument name).  Issue #876 C-2b.
        self._cumulative: dict[str, int] = {}

        if self._enabled and _metrics_mod is not None:
            meter = _metrics_mod.get_meter(meter_name)
            self._workflow_counter = meter.create_counter(
                name="kailash_workflow_executions_total",
                description="Total number of workflow executions",
                unit="1",
            )
            self._workflow_duration = meter.create_histogram(
                name="kailash_workflow_duration_seconds",
                description="Duration of workflow executions in seconds",
                unit="s",
                explicit_bucket_boundaries_advisory=WORKFLOW_DURATION_BUCKETS_SECONDS,
            )
            self._node_duration = meter.create_histogram(
                name="kailash_node_execution_duration_seconds",
                description="Duration of individual node executions in seconds",
                unit="s",
            )
            # Issue #876 — history-store audit-log counters.
            self._history_store_dropped = meter.create_counter(
                name="kailash_history_store_record_event_dropped_total",
                description=(
                    "Audit-log writes skipped because the event had no "
                    "run_id partition key (typed MissingRunIdError observed "
                    "by the runtime subscriber-error handler)."
                ),
                unit="1",
            )
            self._history_store_payload_decode_failed = meter.create_counter(
                name="kailash_history_store_payload_decode_failed_total",
                description=(
                    "get_run_events reads where the persisted payload_json "
                    "column failed to decode back into a dict."
                ),
                unit="1",
            )
            self._history_store_per_tenant_cap_evicted = meter.create_counter(
                name="kailash_history_store_per_tenant_cap_evicted_total",
                description=(
                    "Per-tenant retention-cap evictions (sum of evicted rows)."
                ),
                unit="1",
            )
            self._history_store_retention_swept = meter.create_counter(
                name="kailash_history_store_retention_swept_total",
                description=("Retention-sweep deletions (sum of expired rows pruned)."),
                unit="1",
            )

    @property
    def enabled(self) -> bool:
        """True when OTel metrics API is available."""
        return self._enabled

    # ------------------------------------------------------------------
    # Recording methods
    # ------------------------------------------------------------------

    def record_workflow_start(
        self,
        workflow_name: str,
        tenant_id: str = "",
    ) -> None:
        """Increment the workflow execution counter.

        Args:
            workflow_name: Human-readable workflow identifier.
            tenant_id:     Optional tenant label.
        """
        if not self._enabled or self._workflow_counter is None:
            return
        attrs: dict[str, str] = {"workflow.name": workflow_name}
        if tenant_id:
            attrs["tenant.id"] = tenant_id
        self._workflow_counter.add(1, attributes=attrs)

    def record_workflow_duration(
        self,
        workflow_name: str,
        duration_s: float,
        status: str = "ok",
        tenant_id: str = "",
    ) -> None:
        """Record a workflow execution duration in the histogram.

        Args:
            workflow_name: Human-readable workflow identifier.
            duration_s:    Elapsed time in seconds.
            status:        ``"ok"`` or ``"error"``.
            tenant_id:     Optional tenant label.
        """
        if not self._enabled or self._workflow_duration is None:
            return
        attrs: dict[str, str] = {
            "workflow.name": workflow_name,
            "status": status,
        }
        if tenant_id:
            attrs["tenant.id"] = tenant_id
        self._workflow_duration.record(duration_s, attributes=attrs)

    def record_workflow_execution(
        self,
        workflow_name: str,
        duration_s: float,
        success: bool,
    ) -> None:
        """Record the canonical workflow RED triple for one execution.

        Called once per :meth:`~kailash.runtime.local.LocalRuntime.execute`
        (and the async
        :meth:`~kailash.runtime.async_local.AsyncLocalRuntime.execute_workflow_async`)
        invocation -- on BOTH the success path and the exception path, so
        errors are always rate + duration recorded, never dropped (issue
        #1708 W1f).

        Increments ``kailash_workflow_executions_total`` with bounded
        ``{workflow.name, success}`` attributes (Rate + Errors) and records
        ``duration_s`` into ``kailash_workflow_duration_seconds`` with a
        bounded ``{workflow.name}`` attribute (Duration).

        ``workflow_name`` is sanitized through :func:`sanitize_workflow_name`
        before being used as an attribute value -- it is NEVER the per-build
        ``workflow_id`` UUID (issue #1708 W1d fixed that exact cardinality
        bomb on the orphaned enterprise adapter; this is the same bounded-
        label invariant enforced at the canonical hot-path wiring).

        Args:
            workflow_name: Human-readable workflow identifier (``workflow.name``,
                not ``workflow_id``).
            duration_s: Wall-clock duration of the execute() call, in seconds.
            success: ``True`` when the workflow completed without raising;
                ``False`` on any exception path.
        """
        if not self._enabled:
            return
        bounded_name = sanitize_workflow_name(workflow_name)
        if self._workflow_counter is not None:
            self._workflow_counter.add(
                1,
                attributes={
                    "workflow.name": bounded_name,
                    "success": "true" if success else "false",
                },
            )
        if self._workflow_duration is not None:
            self._workflow_duration.record(
                duration_s,
                attributes={"workflow.name": bounded_name},
            )

    def record_node_duration(
        self,
        node_id: str,
        node_type: str,
        duration_s: float,
        status: str = "ok",
    ) -> None:
        """Record a node execution duration in the histogram.

        Args:
            node_id:    The node identifier.
            node_type:  Class name / type label of the node.
            duration_s: Elapsed time in seconds.
            status:     ``"ok"`` or ``"error"``.
        """
        if not self._enabled or self._node_duration is None:
            return
        self._node_duration.record(
            duration_s,
            attributes={
                "node.id": node_id,
                "node.type": node_type,
                "status": status,
            },
        )

    # ------------------------------------------------------------------
    # History-store audit-log counters (issue #876)
    # ------------------------------------------------------------------

    def record_history_store_dropped(self, count: int = 1) -> None:
        """Increment ``kailash_history_store_record_event_dropped_total``.

        Called by the runtime subscriber-error handler when it observes
        a typed :class:`~kailash.sdk_exceptions.MissingRunIdError` from
        :meth:`WorkflowHistoryStore.record_event`. Issue #876 C-2b.
        """
        with self._lock:
            self._cumulative["kailash_history_store_record_event_dropped_total"] = (
                self._cumulative.get(
                    "kailash_history_store_record_event_dropped_total", 0
                )
                + count
            )
        if self._enabled and self._history_store_dropped is not None:
            self._history_store_dropped.add(count)

    def record_history_store_payload_decode_failed(self, count: int = 1) -> None:
        """Increment ``kailash_history_store_payload_decode_failed_total``.

        Called from :meth:`WorkflowHistoryStore.get_run_events` when
        a persisted ``payload_json`` row fails to decode. Issue #876 C-1.
        """
        with self._lock:
            self._cumulative["kailash_history_store_payload_decode_failed_total"] = (
                self._cumulative.get(
                    "kailash_history_store_payload_decode_failed_total", 0
                )
                + count
            )
        if self._enabled and self._history_store_payload_decode_failed is not None:
            self._history_store_payload_decode_failed.add(count)

    def record_history_store_per_tenant_cap_evicted(self, count: int) -> None:
        """Increment ``kailash_history_store_per_tenant_cap_evicted_total``.

        ``count`` is the number of rows evicted in this sweep (sum, not
        per-call). Called from :meth:`_enforce_per_tenant_cap` when
        ≥1 row is evicted. Issue #876 C-1.
        """
        with self._lock:
            self._cumulative["kailash_history_store_per_tenant_cap_evicted_total"] = (
                self._cumulative.get(
                    "kailash_history_store_per_tenant_cap_evicted_total", 0
                )
                + count
            )
        if self._enabled and self._history_store_per_tenant_cap_evicted is not None:
            self._history_store_per_tenant_cap_evicted.add(count)

    def record_history_store_retention_swept(self, count: int) -> None:
        """Increment ``kailash_history_store_retention_swept_total``.

        ``count`` is the number of rows pruned in this sweep. Called
        from :meth:`delete_runs_older_than` when ≥1 row is deleted.
        Issue #876 C-1.
        """
        with self._lock:
            self._cumulative["kailash_history_store_retention_swept_total"] = (
                self._cumulative.get("kailash_history_store_retention_swept_total", 0)
                + count
            )
        if self._enabled and self._history_store_retention_swept is not None:
            self._history_store_retention_swept.add(count)

    # ------------------------------------------------------------------
    # Counter inspection (test surface)
    # ------------------------------------------------------------------

    def cumulative_count(self, counter_name: str) -> int:
        """Return the cumulative in-memory count for *counter_name*.

        Used by tests to assert that a code path incremented a counter.
        Returns ``0`` if the counter has never been incremented.
        """
        with self._lock:
            return self._cumulative.get(counter_name, 0)


# ------------------------------------------------------------------
# Module-level singleton
# ------------------------------------------------------------------

_global_bridge: Optional[MetricsBridge] = None
_global_bridge_lock = threading.Lock()


def get_metrics_bridge() -> MetricsBridge:
    """Return the module-level ``MetricsBridge`` singleton (thread-safe)."""
    global _global_bridge
    if _global_bridge is None:
        with _global_bridge_lock:
            if _global_bridge is None:
                _global_bridge = MetricsBridge()
    return _global_bridge

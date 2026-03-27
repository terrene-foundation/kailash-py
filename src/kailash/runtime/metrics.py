# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Prometheus-compatible metrics bridge for Kailash runtime.

Exposes workflow and node execution metrics as OTel metric instruments.  When a
Prometheus exporter is configured these appear as standard Prometheus
counters and histograms:

- ``kailash_workflow_executions_total``    -- Counter of workflow runs.
- ``kailash_workflow_duration_seconds``    -- Histogram of workflow durations.
- ``kailash_node_execution_duration_seconds`` -- Histogram of per-node durations.

All instruments degrade gracefully when ``opentelemetry-api`` is not installed.
Install with: ``pip install kailash[otel]``
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Optional

logger = logging.getLogger(__name__)

__all__ = ["MetricsBridge", "get_metrics_bridge"]

# Lazy OTel metrics import.
_OTEL_METRICS_AVAILABLE = False
_metrics_mod: Any = None

try:
    from opentelemetry import metrics as _otel_metrics_module

    _metrics_mod = _otel_metrics_module
    _OTEL_METRICS_AVAILABLE = True
except ImportError:
    pass


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
            )
            self._node_duration = meter.create_histogram(
                name="kailash_node_execution_duration_seconds",
                description="Duration of individual node executions in seconds",
                unit="s",
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

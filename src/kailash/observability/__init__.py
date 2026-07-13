# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Cross-cutting observability primitives.

Subpackages:
  - ``kailash.observability.alerts`` — reference adapters (Slack, generic
    webhook) for routing :class:`~kailash.runtime.lifecycle_events.TaskEvent`
    and :class:`~kailash.runtime.lifecycle_events.JobEvent` payloads to
    external alerters from registered runtime / scheduler hooks (issue #914).
  - ``kailash.observability.ml`` — ML-lifecycle metrics (training duration,
    inference latency, drift alerts) with bounded-cardinality tenant
    labels, OpenTelemetry bridge, and Prometheus fallback.
  - ``kailash.observability.otlp`` — process-global OTLP + Prometheus bootstrap
    (:func:`configure_observability`) that wires the SDK's OpenTelemetry
    instruments to a Prometheus ``/metrics`` scrape and/or an OTLP collector,
    with ``service.name`` / ``service.version`` resource attributes (issue #1708).
"""

from kailash.observability.otlp import (
    ObservabilityHandle,
    configure_observability,
    get_observability_handle,
    shutdown_observability,
)

__all__ = [
    "ObservabilityHandle",
    "configure_observability",
    "get_observability_handle",
    "shutdown_observability",
]

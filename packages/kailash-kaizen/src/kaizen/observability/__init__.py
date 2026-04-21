# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Agent-run observability adapters for Kaizen.

Public surface (the facade path required by ``rules/orphan-detection.md`` §1)::

    from kaizen.observability import (
        AgentDiagnostics,
        AgentDiagnosticsReport,
        TraceExporter,
        TraceExportError,
        JsonlSink,
        NoOpSink,
        CallableSink,
        SinkCallable,
        compute_fingerprint,
        jsonl_exporter,
        callable_exporter,
    )

``AgentDiagnostics`` is the context-managed Diagnostic Protocol adapter
that captures :class:`kailash.diagnostics.protocols.TraceEvent` records
emitted during an agent run and produces a rollup :meth:`report`
summary. ``TraceExporter`` is the single-filter-point sink adapter;
every trace event MUST route through it to pick up the cross-SDK
fingerprint (kailash-rs#468 / v3.17.1+).

See ``specs/kaizen-observability.md`` for:

    * Cross-SDK fingerprint contract (byte-identical with Rust).
    * Third-party vendor policy (no Langfuse / LangSmith / vendor SDK
      imports per ``rules/independence.md`` — users pass their own
      :class:`CallableSink`).
    * Classification discipline for
      :class:`~kailash.diagnostics.protocols.TraceEvent.payload` (emitter
      MUST hash classified PKs per
      ``rules/event-payload-classification.md`` §2).
    * Tier 2 wiring test at
      ``tests/integration/observability/test_agent_diagnostics_wiring.py``.

Cross-SDK Protocol reference: ``src/kailash/diagnostics/protocols.py``
(PR#0 of issue #567). Cross-SDK Rust parity issue:
``kailash-rs#468`` / v3.17.1+.
"""

from __future__ import annotations

from kaizen.observability.agent_diagnostics import (
    AgentDiagnostics,
    AgentDiagnosticsReport,
)
from kaizen.observability.trace_exporter import (
    CallableSink,
    JsonlSink,
    NoOpSink,
    SinkCallable,
    TraceExporter,
    TraceExportError,
    callable_exporter,
    compute_fingerprint,
    jsonl_exporter,
)

__all__ = [
    "AgentDiagnostics",
    "AgentDiagnosticsReport",
    "CallableSink",
    "JsonlSink",
    "NoOpSink",
    "SinkCallable",
    "TraceExporter",
    "TraceExportError",
    "callable_exporter",
    "compute_fingerprint",
    "jsonl_exporter",
]

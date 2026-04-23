# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
#
# Portions of this module were originally contributed from MLFP
# (Apache-2.0) and re-authored for the Kailash ecosystem. See
# ``specs/kaizen-observability.md`` § "Attribution" for the full
# donation history (kailash-py issue #567, PR#6 of 7).
"""AgentDiagnostics — context-managed Diagnostic session for agent runs.

``AgentDiagnostics`` is the Kaizen adapter that satisfies the
:class:`kailash.diagnostics.protocols.Diagnostic` Protocol for an
agent execution. Inside a ``with`` block, the session:

    * Records every :class:`TraceEvent` emitted by the wrapped agent
      (via a :class:`~kaizen.observability.trace_exporter.TraceExporter`).
    * Computes latency + cost rollups grouped by ``event_type``.
    * Produces a :meth:`report` summary that the caller can surface in
      dashboards or diff against prior sessions.

Usage shape::

    from kaizen.observability import AgentDiagnostics, TraceExporter
    from kaizen_agents import Delegate

    with AgentDiagnostics(run_id="task-42") as diag:
        agent = Delegate(
            model=os.environ["OPENAI_PROD_MODEL"],
            trace_exporter=diag.exporter,
        )
        result = agent.run("analyze revenue trend")

    summary = diag.report()
    # {"event_counts": {"agent.run.start": 1, ...},
    #  "total_cost_microdollars": 17_500,
    #  "duration_ms_p50": 420.0, "duration_ms_p95": 880.0,
    #  "error_rate": 0.0, ...}

Signature-free by design: this class does NOT make LLM decisions. It
is a data-shaped aggregator that routes TraceEvents to an exporter
and computes pure-math rollups on the captured stream. That keeps it
outside ``rules/agent-reasoning.md`` scope (which applies to code
that decides what an agent should _think_ or _do_).

Related:

  - ``rules/orphan-detection.md`` §1 + `§2 — the Tier 2 wiring test
    proves :class:`~kaizen.core.base_agent.BaseAgent` actually invokes
    ``diag.exporter.export()`` on the hot path.
  - ``rules/facade-manager-detection.md`` §1 — this class is
    re-exported from ``kaizen.observability`` and the wiring test file
    name follows ``test_<lowercase_manager_name>_wiring.py``.
"""

from __future__ import annotations

import logging
import math
import statistics
import uuid
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from types import TracebackType
from typing import Any, Optional

from kailash.diagnostics.protocols import TraceEvent, TraceEventStatus, TraceEventType

from kaizen.ml._tracker_bridge import emit_metric, resolve_active_tracker
from kaizen.observability.trace_exporter import TraceExporter, _hash_tenant_id

logger = logging.getLogger(__name__)

__all__ = [
    "AgentDiagnostics",
    "AgentDiagnosticsReport",
]


# ---------------------------------------------------------------------------
# Captured event — a bounded-history view of one TraceEvent
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _CapturedEvent:
    """Lightweight per-event record retained in the session buffer.

    Only the fields needed for :meth:`AgentDiagnostics.report` rollups
    are kept — the full ``TraceEvent`` has already been forwarded to
    the exporter's sink, so we do not duplicate payloads in memory.
    """

    event_id: str
    event_type: TraceEventType
    timestamp: datetime
    cost_microdollars: int
    duration_ms: Optional[float]
    status: Optional[TraceEventStatus]


# ---------------------------------------------------------------------------
# Report — the public summary shape
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AgentDiagnosticsReport:
    """Public summary of an :class:`AgentDiagnostics` session.

    Returned by :meth:`AgentDiagnostics.report`. Purely numeric — safe
    for display in dashboards and for diff against prior runs.

    Attributes:
        run_id: Correlation identifier of the session.
        event_count: Total events captured.
        event_counts: Count per ``event_type`` (enum ``.value`` keys).
        total_cost_microdollars: Sum of ``cost_microdollars`` across
            all captured events.
        duration_ms_p50: Median observed ``duration_ms`` across events
            that reported it (``None`` when zero events had a duration).
        duration_ms_p95: 95th-percentile observed ``duration_ms`` (same
            ``None`` rule).
        error_rate: Fraction of events whose ``status`` is
            :attr:`TraceEventStatus.ERROR`. ``0.0`` when no events have
            a populated status.
        errored_exports: Number of sink failures recorded by the
            underlying :class:`TraceExporter`.
    """

    run_id: str
    event_count: int
    event_counts: dict[str, int]
    total_cost_microdollars: int
    duration_ms_p50: Optional[float]
    duration_ms_p95: Optional[float]
    error_rate: float
    errored_exports: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "event_count": self.event_count,
            "event_counts": dict(self.event_counts),
            "total_cost_microdollars": self.total_cost_microdollars,
            "duration_ms_p50": self.duration_ms_p50,
            "duration_ms_p95": self.duration_ms_p95,
            "error_rate": self.error_rate,
            "errored_exports": self.errored_exports,
        }


# ---------------------------------------------------------------------------
# AgentDiagnostics
# ---------------------------------------------------------------------------


class AgentDiagnostics:
    """Context-managed diagnostic session for a Kaizen agent run.

    Satisfies :class:`kailash.diagnostics.protocols.Diagnostic` at
    runtime (``isinstance(diag, Diagnostic) is True``). Wraps a
    :class:`TraceExporter` so every captured event is ALSO routed to
    the configured sink (the session's rollups are complementary to
    the durable export, not a replacement).

    Args:
        exporter: Pre-built :class:`TraceExporter`. When ``None``, a
            no-op exporter is constructed (tests and dev scenarios).
        run_id: Correlation identifier. Auto-generated when ``None``.
        tenant_id: Optional tenant scope forwarded to the exporter and
            stamped onto every structured log line.
        tracker: Optional ambient ``km.track()`` run handle (typed as
            ``Optional[ExperimentRun]`` per
            ``specs/kaizen-ml-integration.md §2.1``). When supplied, or
            when a run is ambient via
            :func:`kailash_ml.tracking.get_current_run`, every captured
            TraceEvent auto-emits ``agent.*`` metrics to the tracker
            per spec §3.1 — NO opt-in flag.
        max_history: Bounded FIFO buffer for per-event rollup data.
            Events beyond this count are evicted; the exporter still
            receives every event regardless.

    Raises:
        ValueError: If ``max_history < 1``.
    """

    _DEFAULT_MAX_HISTORY: int = 10_000

    def __init__(
        self,
        *,
        exporter: Optional[TraceExporter] = None,
        run_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        tracker: Optional[Any] = None,
        max_history: int = _DEFAULT_MAX_HISTORY,
    ) -> None:
        if max_history < 1:
            raise ValueError(
                f"AgentDiagnostics.max_history must be >= 1, got {max_history}"
            )

        self.run_id: str = run_id if run_id is not None else uuid.uuid4().hex
        self._tenant_id = tenant_id
        self._tracker = tracker  # lazy — resolved at every record() per spec §2.2
        self._max_history = max_history

        self._exporter: TraceExporter = (
            exporter
            if exporter is not None
            else TraceExporter(run_id=self.run_id, tenant_id=tenant_id)
        )

        self._events: deque[_CapturedEvent] = deque(maxlen=max_history)

        logger.info(
            "kaizen.observability.agent_diagnostics.init",
            extra={
                "agent_diag_run_id": self.run_id,
                "agent_diag_tenant_hash": _hash_tenant_id(tenant_id),
                "agent_diag_max_history": max_history,
                "agent_diag_exporter_sink": type(
                    self._exporter._sink  # noqa: SLF001 — stable public shape
                ).__name__,
                "mode": "real",
            },
        )

    # ── Context manager (Diagnostic Protocol) ───────────────────────

    def __enter__(self) -> "AgentDiagnostics":
        return self

    def __exit__(
        self,
        exc_type: Optional[type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[TracebackType],
    ) -> Optional[bool]:
        logger.info(
            "kaizen.observability.agent_diagnostics.exit",
            extra={
                "agent_diag_run_id": self.run_id,
                "agent_diag_tenant_hash": _hash_tenant_id(self._tenant_id),
                "agent_diag_event_count": len(self._events),
                "agent_diag_exported": self._exporter.exported_count,
                "agent_diag_errored": self._exporter.errored_count,
                "mode": "real",
            },
        )
        return None  # never suppress caller exceptions

    # ── Accessors ───────────────────────────────────────────────────

    @property
    def exporter(self) -> TraceExporter:
        """The underlying :class:`TraceExporter`.

        Callers pass this to their agent / delegate so every trace
        event lands in both the session rollup AND the durable sink.
        """
        return self._exporter

    @property
    def event_count(self) -> int:
        return len(self._events)

    # ── Core capture path ──────────────────────────────────────────

    def record(self, event: TraceEvent) -> str:
        """Record ``event`` — export it AND retain rollup data.

        Returns the cross-SDK fingerprint stamped by the exporter.
        Callers MAY also call :meth:`TraceExporter.export` directly;
        this wrapper is a convenience for code paths that want both
        sink-side and in-session rollup tracking.

        Per ``specs/kaizen-ml-integration.md §3.1`` item 2: when an
        ambient ``km.track()`` run is active (or an explicit tracker
        was passed at construction), this method auto-emits ``agent.*``
        metrics to the tracker — NO opt-in flag.
        """
        fingerprint = self._exporter.export(event)
        self._capture(event)
        self._auto_emit(event)
        return fingerprint

    async def record_async(self, event: TraceEvent) -> str:
        """Async counterpart of :meth:`record`."""
        fingerprint = await self._exporter.export_async(event)
        self._capture(event)
        self._auto_emit(event)
        return fingerprint

    def _auto_emit(self, event: TraceEvent) -> None:
        """Route captured metrics to an ambient ``km.track()`` run.

        Spec §3.2 locks metric prefixes for agent diagnostics at
        ``agent.*``. Spec §3.1 mandates auto-emission whenever an
        ambient tracker is present. This method is the single emission
        point so every captured event feeds the same contract.
        """
        tracker = resolve_active_tracker(self._tracker)
        if tracker is None:
            return
        emit_metric(tracker, "agent.cost_microdollars", event.cost_microdollars)
        if event.duration_ms is not None:
            emit_metric(tracker, "agent.duration_ms", float(event.duration_ms))
        if event.prompt_tokens is not None:
            emit_metric(tracker, "agent.prompt_tokens", float(event.prompt_tokens))
        if event.completion_tokens is not None:
            emit_metric(
                tracker, "agent.completion_tokens", float(event.completion_tokens)
            )
        # One counter metric per event type (spec §3.2 — bounded cardinality
        # via the TraceEventType enum, per ``rules/tenant-isolation.md §4``).
        emit_metric(tracker, f"agent.events.{event.event_type.value}", 1.0)
        emit_metric(tracker, "agent.turns", 1.0)

    def _capture(self, event: TraceEvent) -> None:
        self._events.append(
            _CapturedEvent(
                event_id=event.event_id,
                event_type=event.event_type,
                timestamp=event.timestamp,
                cost_microdollars=event.cost_microdollars,
                duration_ms=event.duration_ms,
                status=event.status,
            )
        )

    # ── Reporting (Diagnostic Protocol) ────────────────────────────

    def report(self) -> dict[str, Any]:
        """Compute a rollup summary of the captured events.

        Returns a dict-shape (matching ``rules/eatp.md`` ``to_dict()``
        discipline) so downstream consumers can serialize it directly.
        The :class:`AgentDiagnosticsReport` dataclass is available via
        :meth:`report_dataclass` for typed access.
        """
        return self.report_dataclass().to_dict()

    def report_dataclass(self) -> AgentDiagnosticsReport:
        """Return the rollup summary as a frozen dataclass."""
        events = list(self._events)
        event_count = len(events)

        counts: dict[str, int] = {}
        total_cost = 0
        durations: list[float] = []
        statuses_seen: list[TraceEventStatus] = []

        for ev in events:
            counts[ev.event_type.value] = counts.get(ev.event_type.value, 0) + 1
            total_cost += ev.cost_microdollars
            if ev.duration_ms is not None and math.isfinite(ev.duration_ms):
                durations.append(float(ev.duration_ms))
            if ev.status is not None:
                statuses_seen.append(ev.status)

        p50 = _percentile(durations, 50)
        p95 = _percentile(durations, 95)

        if statuses_seen:
            error_rate = sum(
                1 for s in statuses_seen if s == TraceEventStatus.ERROR
            ) / len(statuses_seen)
        else:
            error_rate = 0.0

        return AgentDiagnosticsReport(
            run_id=self.run_id,
            event_count=event_count,
            event_counts=counts,
            total_cost_microdollars=total_cost,
            duration_ms_p50=p50,
            duration_ms_p95=p95,
            error_rate=error_rate,
            errored_exports=self._exporter.errored_count,
        )


# ---------------------------------------------------------------------------
# Helpers — pure math, no LLM reasoning
# ---------------------------------------------------------------------------


def _percentile(values: list[float], pct: float) -> Optional[float]:
    """Return the ``pct``-th percentile of ``values`` or ``None`` if empty.

    Uses the ``nearest-rank`` method via :func:`statistics.quantiles`.
    Single-value cases return the value directly to avoid the quantile
    helper's empty-cuts behaviour.
    """
    if not values:
        return None
    if len(values) == 1:
        return values[0]
    # quantiles(n=100) yields 99 cut-points; indices [0..98] correspond
    # to the 1st..99th percentiles.
    cuts = statistics.quantiles(values, n=100, method="inclusive")
    idx = min(max(int(pct) - 1, 0), len(cuts) - 1)
    return cuts[idx]

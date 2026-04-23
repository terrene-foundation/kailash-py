# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 2 — auto-emission from ``AgentDiagnostics.record()`` into tracker.

Closes MLFP-dev gap 4 (regression per W32 todo).

Spec ``kaizen-ml-integration.md §3.1 item 2`` mandates that EVERY
``record_*`` / ``track_*`` method auto-emits to the ambient tracker.
This test uses a deterministic protocol-satisfying tracker adapter
(``rules/testing.md §Tier 2 Exception``) to prove end-to-end flow:

    AgentDiagnostics.record(event)
        → _auto_emit(event)
        → resolve_active_tracker(self._tracker) → StubTracker
        → StubTracker.log_metric("agent.turns", 1.0, step=None)

No mocks — ``StubTracker`` is a real implementation of the tracker
Protocol (``log_metric`` / ``log_param`` / ``log_artifact``) whose
output is deterministic by design.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

import pytest

from kailash.diagnostics.protocols import (
    TraceEvent,
    TraceEventStatus,
    TraceEventType,
)


class _DeterministicTracker:
    """Real tracker-Protocol implementation — NOT a mock.

    Satisfies the duck-typed tracker contract the bridge uses
    (``log_metric`` / ``log_param`` / ``log_artifact``). Output is
    deterministic by design; per ``rules/testing.md §Tier 2 Exception``
    this is a Tier 2-legal test double because it's a real class with
    the Protocol-required methods and correct signatures.
    """

    def __init__(self) -> None:
        self.metrics: list[tuple[str, float, Optional[int]]] = []
        self.params: list[tuple[str, Any]] = []
        self.artifacts: list[tuple[str, Optional[str]]] = []

    def log_metric(self, key: str, value: float, step: Optional[int] = None) -> None:
        self.metrics.append((key, value, step))

    def log_param(self, key: str, value: Any) -> None:
        self.params.append((key, value))

    def log_artifact(self, path: str, artifact_path: Optional[str] = None) -> None:
        self.artifacts.append((path, artifact_path))

    def metric_keys(self) -> set[str]:
        return {k for k, _, _ in self.metrics}


@pytest.mark.integration
def test_agent_diagnostics_record_emits_to_explicit_tracker() -> None:
    """``AgentDiagnostics(tracker=explicit)`` → metrics flow to explicit tracker."""
    from kaizen.observability.agent_diagnostics import AgentDiagnostics

    tracker = _DeterministicTracker()
    diag = AgentDiagnostics(tracker=tracker, run_id=f"t-{uuid.uuid4().hex[:8]}")

    event = TraceEvent(
        event_id=uuid.uuid4().hex,
        event_type=TraceEventType.AGENT_STEP,
        timestamp=datetime.now(timezone.utc),
        run_id=diag.run_id,
        agent_id="agent-under-test",
        cost_microdollars=1500,
        duration_ms=42.0,
        prompt_tokens=10,
        completion_tokens=20,
        status=TraceEventStatus.OK,
    )
    diag.record(event)

    # Spec §3.2 — key prefix locked at ``agent.*``.
    keys = tracker.metric_keys()
    assert "agent.cost_microdollars" in keys
    assert "agent.duration_ms" in keys
    assert "agent.prompt_tokens" in keys
    assert "agent.completion_tokens" in keys
    assert "agent.turns" in keys
    assert "agent.events.agent.step" in keys

    # Scalar values match the event.
    cost_entries = [m for m in tracker.metrics if m[0] == "agent.cost_microdollars"]
    assert cost_entries == [("agent.cost_microdollars", 1500.0, None)]


@pytest.mark.integration
def test_agent_diagnostics_record_no_tracker_is_silent() -> None:
    """Spec §3.4 — no tracker, no crash, no emission."""
    from kaizen.observability.agent_diagnostics import AgentDiagnostics

    diag = AgentDiagnostics(run_id="no-tracker-run")
    event = TraceEvent(
        event_id=uuid.uuid4().hex,
        event_type=TraceEventType.AGENT_RUN_START,
        timestamp=datetime.now(timezone.utc),
        run_id=diag.run_id,
        agent_id="agent-under-test",
        cost_microdollars=0,
        status=TraceEventStatus.OK,
    )
    diag.record(event)  # must not raise


@pytest.mark.integration
def test_agent_diagnostics_record_auto_emit_ignores_non_finite_duration() -> None:
    """``emit_metric`` gates non-finite values (spec §3.4 — silent skip)."""
    from kaizen.observability.agent_diagnostics import AgentDiagnostics

    tracker = _DeterministicTracker()
    diag = AgentDiagnostics(tracker=tracker, run_id="nan-duration")
    event = TraceEvent(
        event_id=uuid.uuid4().hex,
        event_type=TraceEventType.AGENT_STEP,
        timestamp=datetime.now(timezone.utc),
        run_id=diag.run_id,
        agent_id="agent-under-test",
        cost_microdollars=100,
        duration_ms=float("nan"),
        status=TraceEventStatus.OK,
    )
    diag.record(event)

    duration_entries = [m for m in tracker.metrics if m[0] == "agent.duration_ms"]
    assert duration_entries == []  # NaN duration dropped at finite-gate
    # But cost still flows (finite) — proves the gate is per-metric, not per-event.
    cost_entries = [m for m in tracker.metrics if m[0] == "agent.cost_microdollars"]
    assert cost_entries == [("agent.cost_microdollars", 100.0, None)]


@pytest.mark.integration
def test_agent_diagnostics_record_async_also_auto_emits() -> None:
    """Parity: ``record_async`` (coroutine) emits identically to ``record``."""
    import asyncio

    from kaizen.observability.agent_diagnostics import AgentDiagnostics

    tracker = _DeterministicTracker()
    diag = AgentDiagnostics(tracker=tracker, run_id="async-run")
    event = TraceEvent(
        event_id=uuid.uuid4().hex,
        event_type=TraceEventType.TOOL_CALL_END,
        timestamp=datetime.now(timezone.utc),
        run_id=diag.run_id,
        agent_id="agent-under-test",
        cost_microdollars=42,
        status=TraceEventStatus.OK,
    )
    asyncio.run(diag.record_async(event))

    keys = tracker.metric_keys()
    assert "agent.cost_microdollars" in keys
    assert "agent.events.tool.call.end" in keys

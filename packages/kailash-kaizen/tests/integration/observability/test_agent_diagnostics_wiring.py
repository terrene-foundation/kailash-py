# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 2 wiring test for AgentDiagnostics / TraceExporter.

Closes ``rules/orphan-detection.md`` §1 for ``kaizen.observability``:
proves that a real :class:`~kaizen.core.base_agent.BaseAgent` run
actually invokes the attached :class:`TraceExporter` on the hot path,
not just in isolated unit tests (which would only prove the exporter
can accept events — not that the framework calls it).

File name follows ``rules/facade-manager-detection.md`` §2 convention
(``test_<lowercase_manager_name>_wiring.py``) so missing wiring is
grep-able across the test tree.

Real infrastructure — uses the mock LLM provider (tier 2 isolates
from external APIs while exercising the full BaseAgent loop).
"""
from __future__ import annotations

import pytest

from kailash.diagnostics.protocols import (
    TraceEvent,
    TraceEventStatus,
    TraceEventType,
    compute_trace_event_fingerprint,
)

from kaizen.observability import (
    AgentDiagnostics,
    CallableSink,
    TraceExporter,
    compute_fingerprint,
)


pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


class _CapturingSink:
    """Callable sink that records every (event, fingerprint) pair.

    Lives inside the test so third-party vendor coupling never creeps
    into the kaizen.observability package itself
    (``rules/independence.md``).
    """

    def __init__(self) -> None:
        self.captured: list[tuple[TraceEvent, str]] = []

    def __call__(self, event: TraceEvent, fingerprint: str) -> None:
        self.captured.append((event, fingerprint))


# ---------------------------------------------------------------------------
# Tier 2: real BaseAgent run emits TraceEvents through attached exporter
# ---------------------------------------------------------------------------


def _make_agent():
    """Construct a minimal real BaseAgent routed through the mock provider.

    ``llm_provider="mock"`` is the explicit test-provider contract per
    the kaizen skill — it runs the full AgentLoop without external API
    calls.
    """
    from dataclasses import dataclass

    from kaizen.core.base_agent import BaseAgent
    from kaizen.signatures import InputField, OutputField, Signature

    class _ObservabilityTestSignature(Signature):
        query: str = InputField(description="Test query")
        response: str = OutputField(description="Agent response")

    @dataclass
    class _ObservabilityTestConfig:
        llm_provider: str = "mock"
        model: str = "mock-test"

    class _ObservabilityTestAgent(BaseAgent):
        def __init__(self, config):
            super().__init__(
                config=config,
                signature=_ObservabilityTestSignature(),
                mcp_servers=[],  # disable MCP auto-discovery in tests
            )

    return _ObservabilityTestAgent(config=_ObservabilityTestConfig())


def test_agent_run_invokes_trace_exporter_on_hot_path():
    """Real BaseAgent run MUST emit agent.run.start + agent.run.end.

    This is the orphan-detection Rule 1 evidence: proves
    ``attach_trace_exporter`` + ``AgentLoop`` emission actually fire
    when a user runs the agent. A passing isolated-exporter unit test
    would NOT prove this.
    """
    agent = _make_agent()
    sink = _CapturingSink()
    exporter = TraceExporter(sink=CallableSink(sink), run_id="wiring-test")

    agent.attach_trace_exporter(exporter)
    assert agent.trace_exporter is exporter, "facade property drifted"

    # Run the agent — strategy failure is acceptable; the wiring test
    # only asserts that start + end events fire regardless.
    try:
        agent.run(query="what is the capital of France?")
    except Exception:  # noqa: BLE001 — mock provider path may raise
        pass

    # Start MUST have fired before any strategy outcome.
    start_events = [
        ev
        for ev, _fp in sink.captured
        if ev.event_type == TraceEventType.AGENT_RUN_START
    ]
    end_events = [
        ev for ev, _fp in sink.captured if ev.event_type == TraceEventType.AGENT_RUN_END
    ]
    assert start_events, (
        "AgentLoop.run_sync did not emit agent.run.start — "
        "orphan-detection Rule 1 failure: exporter is not wired into the hot path"
    )
    assert end_events, (
        "AgentLoop.run_sync did not emit agent.run.end — "
        "trace stream is unterminated"
    )

    # Start and end share a run_id.
    assert (
        start_events[0].run_id == end_events[0].run_id
    ), "run_id drift between start and end events — correlation broken"

    # End event carries parent_event_id = start event's event_id.
    assert (
        end_events[0].parent_event_id == start_events[0].event_id
    ), "parent_event_id drift — span hierarchy broken"

    # Each event has a non-empty cross-SDK fingerprint; each stamped
    # fingerprint matches the canonical helper on re-computation.
    for event, fp in sink.captured:
        assert len(fp) == 64, f"fingerprint length drift: {fp!r}"
        assert all(c in "0123456789abcdef" for c in fp), f"fingerprint not hex: {fp!r}"
        recomputed = compute_trace_event_fingerprint(event)
        assert (
            fp == recomputed
        ), f"exporter's fingerprint {fp} != recomputed {recomputed}"


def test_agent_diagnostics_session_captures_rollup():
    """AgentDiagnostics session MUST record rollup stats across events.

    Closes facade-manager-detection Rule 1: the manager is imported
    through ``kaizen.observability`` (the facade path), constructed
    against a real BaseAgent, and its externally-observable effect
    (non-zero event_count, non-empty event_counts) is asserted.
    """
    agent = _make_agent()
    sink = _CapturingSink()

    with AgentDiagnostics(
        exporter=TraceExporter(sink=CallableSink(sink), run_id="diag-wiring")
    ) as diag:
        agent.attach_trace_exporter(diag.exporter)
        try:
            agent.run(query="hello")
        except Exception:  # noqa: BLE001
            pass

        # Manually record a judge verdict event to exercise the
        # diagnostic's own capture path in addition to the AgentLoop
        # emissions routed via the shared exporter.
        import uuid
        from datetime import datetime, timezone

        diag.record(
            TraceEvent(
                event_id=f"evt-{uuid.uuid4().hex[:12]}",
                event_type=TraceEventType.JUDGE_VERDICT,
                timestamp=datetime.now(timezone.utc),
                run_id=diag.run_id,
                agent_id=agent.agent_id,
                cost_microdollars=1500,
                duration_ms=42.0,
                status=TraceEventStatus.OK,
            )
        )

    report = diag.report()
    assert (
        report["event_count"] >= 1
    ), "AgentDiagnostics captured zero events — rollup path broken"
    assert (
        "judge.verdict" in report["event_counts"]
    ), f"judge.verdict missing from event_counts: {report['event_counts']}"
    assert (
        report["total_cost_microdollars"] >= 1500
    ), f"cost rollup dropped cost_microdollars: {report}"
    # Cross-SDK invariant: microdollars is int, not float.
    assert isinstance(report["total_cost_microdollars"], int)


def test_detached_exporter_no_events_captured():
    """Setting exporter=None MUST short-circuit — no emission overhead."""
    agent = _make_agent()
    sink = _CapturingSink()
    exporter = TraceExporter(sink=CallableSink(sink))

    agent.attach_trace_exporter(exporter)
    agent.attach_trace_exporter(None)

    try:
        agent.run(query="silence")
    except Exception:  # noqa: BLE001
        pass

    assert (
        sink.captured == []
    ), "detached exporter still received events — short-circuit broken"


def test_fingerprint_helper_reexport_matches_canonical():
    """``kaizen.observability.compute_fingerprint`` MUST be identical to
    ``kailash.diagnostics.protocols.compute_trace_event_fingerprint``.

    The re-export is convenience-only; the canonical contract lives
    in the protocol module (kailash-rs#468). Drift would silently
    break cross-SDK forensic correlation.
    """
    from datetime import datetime, timezone

    ev = TraceEvent(
        event_id="ev-reexport",
        event_type=TraceEventType.AGENT_STEP,
        timestamp=datetime(2026, 4, 21, 12, 0, 0, tzinfo=timezone.utc),
        run_id="run-reexport",
        agent_id="agent-reexport",
        cost_microdollars=42,
    )
    assert compute_fingerprint(ev) == compute_trace_event_fingerprint(ev)

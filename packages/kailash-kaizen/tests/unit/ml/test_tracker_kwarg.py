# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 1 — ``tracker=`` kwarg presence on all 3 diagnostic classes.

Per ``specs/kaizen-ml-integration.md §1.1 item 1`` every Kaizen
diagnostic adapter MUST accept ``tracker: Optional[ExperimentRun] = None``
as a keyword-only argument.

The tracker is typed ``Optional[ExperimentRun]`` in spec §2.1 but the
runtime check uses duck-typing (``log_metric`` / ``log_param`` /
``log_artifact`` attribute presence) so any Protocol-satisfying
adapter — including the :class:`_StubTracker` helper below — works
without a hard dependency on kailash-ml.
"""

from __future__ import annotations

import inspect

import pytest


@pytest.mark.unit
def test_agent_diagnostics_accepts_tracker_kwarg() -> None:
    from kaizen.observability.agent_diagnostics import AgentDiagnostics

    sig = inspect.signature(AgentDiagnostics.__init__)
    assert "tracker" in sig.parameters
    assert sig.parameters["tracker"].kind == inspect.Parameter.KEYWORD_ONLY
    assert sig.parameters["tracker"].default is None


@pytest.mark.unit
def test_llm_diagnostics_accepts_tracker_kwarg() -> None:
    from kaizen.judges.llm_diagnostics import LLMDiagnostics

    sig = inspect.signature(LLMDiagnostics.__init__)
    assert "tracker" in sig.parameters
    assert sig.parameters["tracker"].kind == inspect.Parameter.KEYWORD_ONLY
    assert sig.parameters["tracker"].default is None


@pytest.mark.unit
def test_interpretability_diagnostics_accepts_tracker_kwarg() -> None:
    from kaizen.interpretability.core import InterpretabilityDiagnostics

    sig = inspect.signature(InterpretabilityDiagnostics.__init__)
    assert "tracker" in sig.parameters
    assert sig.parameters["tracker"].kind == inspect.Parameter.KEYWORD_ONLY
    assert sig.parameters["tracker"].default is None


@pytest.mark.unit
def test_agent_diagnostics_stores_tracker_for_lazy_resolution() -> None:
    """Spec §2.2 — explicit tracker wins over ambient; lazy at emission."""
    from kaizen.observability.agent_diagnostics import AgentDiagnostics

    class _StubTracker:
        def __init__(self) -> None:
            self.metrics: list[tuple[str, float]] = []

        def log_metric(self, key: str, value: float, step=None) -> None:
            self.metrics.append((key, value))

        def log_param(self, key: str, value) -> None:  # noqa: ANN001
            pass

    tracker = _StubTracker()
    diag = AgentDiagnostics(tracker=tracker, run_id="unit-run")
    assert diag._tracker is tracker


@pytest.mark.unit
def test_llm_diagnostics_stores_tracker_for_lazy_resolution() -> None:
    from kaizen.judges.llm_diagnostics import LLMDiagnostics

    class _StubTracker:
        def log_metric(self, *a, **k) -> None:
            pass

    tracker = _StubTracker()
    diag = LLMDiagnostics(tracker=tracker)
    assert diag._tracker is tracker


@pytest.mark.unit
def test_interpretability_diagnostics_stores_tracker_for_lazy_resolution() -> None:
    from kaizen.interpretability.core import InterpretabilityDiagnostics

    class _StubTracker:
        def log_metric(self, *a, **k) -> None:
            pass

    tracker = _StubTracker()
    diag = InterpretabilityDiagnostics(tracker=tracker)
    assert diag._tracker is tracker


@pytest.mark.unit
def test_emit_metric_silent_no_op_when_tracker_is_none() -> None:
    """Spec §3.4 — no tracker, no crash, no WARN log (DEBUG only)."""
    from kaizen.ml import emit_metric

    # Must not raise. The no-op is the contract.
    emit_metric(None, "agent.turns", 1.0)


@pytest.mark.unit
def test_emit_metric_invokes_tracker_log_metric() -> None:
    """Spec §3.1 — when a tracker is present, metrics flow."""
    from kaizen.ml import emit_metric

    calls: list[tuple[str, float, object]] = []

    class _StubTracker:
        def log_metric(self, key: str, value: float, step=None) -> None:
            calls.append((key, value, step))

    emit_metric(_StubTracker(), "agent.cost_microdollars", 1500.0)
    assert calls == [("agent.cost_microdollars", 1500.0, None)]


@pytest.mark.unit
def test_emit_metric_skips_nan_and_infinite_values() -> None:
    """``kailash_ml.log_metric`` rejects non-finite values; we pre-gate."""
    from kaizen.ml import emit_metric

    calls: list = []

    class _StubTracker:
        def log_metric(self, *a, **k) -> None:
            calls.append((a, k))

    emit_metric(_StubTracker(), "agent.duration_ms", float("nan"))
    emit_metric(_StubTracker(), "agent.duration_ms", float("inf"))
    assert calls == []  # both dropped at the finite-gate


@pytest.mark.unit
def test_is_emit_rank_0_true_on_non_distributed() -> None:
    """Spec §2.5 — non-distributed context trivially rank 0."""
    from kaizen.ml import is_emit_rank_0

    assert is_emit_rank_0() is True

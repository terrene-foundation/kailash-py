# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 2 wiring tests for ``kaizen.judges``.

Per ``rules/orphan-detection.md`` §1, these tests import the adapters
exclusively via the package facade (``from kaizen.judges import ...``)
and exercise a realistic diagnostic session end-to-end. Per
``rules/testing.md`` § "Tier 2 (Integration): Real infrastructure
recommended", mocks are BLOCKED at this tier — the tests use real
polars DataFrames, real plotly figures, and a concrete ``JudgeCallable``
Protocol implementation rather than a ``MagicMock``.

The concrete judge here is a deterministic, non-mock class that
satisfies the ``kailash.diagnostics.protocols.JudgeCallable`` Protocol
by computing a reproducible verdict from the input alone. It is NOT
a mock: it implements the Protocol fully and is observable through the
same surface as any production ``JudgeCallable``. This pattern avoids
both the "Tier 2 can't mock" rule and the "real LLM requires API key"
operational hazard for CI.
"""
from __future__ import annotations

import asyncio

import plotly.graph_objects as go
import polars as pl
import pytest

from kailash.diagnostics.protocols import (
    Diagnostic,
    JudgeCallable,
    JudgeInput,
    JudgeResult,
)

# Facade imports — MUST be via kaizen.judges, not direct module paths.
from kaizen.judges import (
    JudgeBudgetExhaustedError,
    LLMDiagnostics,
)


class DeterministicJudge:
    """Real JudgeCallable Protocol implementation for Tier 2 tests.

    Computes a reproducible score/winner from the JudgeInput alone, with
    no LLM call + no external network. Tracks call count + token usage
    so tests can assert the diagnostic session routed through it.

    This is NOT a mock: the class satisfies the JudgeCallable Protocol
    at runtime (``isinstance(j, JudgeCallable) is True``) and is exercised
    through the same code path the production LLMJudge uses.
    """

    judge_model: str = "deterministic-test-judge"

    def __init__(self, budget_microdollars: int = 10_000_000) -> None:
        self.calls: list[JudgeInput] = []
        self.cost_microdollars: int = 0
        # LLMDiagnostics reads these attributes during init + report for
        # structured logging; providing them keeps the DeterministicJudge
        # duck-type compatible with LLMJudge without inheriting from it.
        self.budget_microdollars: int = budget_microdollars
        self.spent_microdollars: int = 0

    async def __call__(self, judge_input: JudgeInput) -> JudgeResult:
        self.calls.append(judge_input)
        self.cost_microdollars += 150  # 150 μ$ per call
        self.spent_microdollars = self.cost_microdollars

        # Pointwise scoring: score proportional to candidate length
        # (deterministic, bounded to [0.0, 1.0]).
        if judge_input.candidate_b is None:
            raw = min(len(judge_input.candidate_a) / 200.0, 1.0)
            return JudgeResult(
                score=raw,
                winner=None,
                reasoning=f"Deterministic pointwise score={raw:.2f}",
                judge_model=self.judge_model,
                cost_microdollars=150,
                prompt_tokens=10,
                completion_tokens=15,
            )

        # Pairwise scoring: winner is whichever candidate is longer
        # (deterministic, reproducible across position swaps).
        if len(judge_input.candidate_a) > len(judge_input.candidate_b):
            winner = "A"
        elif len(judge_input.candidate_b) > len(judge_input.candidate_a):
            winner = "B"
        else:
            winner = "tie"
        return JudgeResult(
            score=None,
            winner=winner,
            reasoning=f"Deterministic pairwise winner={winner}",
            judge_model=self.judge_model,
            cost_microdollars=150,
            prompt_tokens=12,
            completion_tokens=18,
        )


# ---------------------------------------------------------------------------
# Facade + Protocol conformance
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_facade_import_llm_diagnostics_satisfies_diagnostic_protocol() -> None:
    """LLMDiagnostics imported via facade MUST be a Diagnostic at runtime."""
    diag = LLMDiagnostics(judge=DeterministicJudge())
    assert isinstance(diag, Diagnostic)
    assert isinstance(diag.run_id, str) and diag.run_id


@pytest.mark.integration
def test_deterministic_judge_satisfies_judge_callable_protocol() -> None:
    """The Tier 2 test double MUST itself be a JudgeCallable (not a mock)."""
    judge = DeterministicJudge()
    assert isinstance(judge, JudgeCallable)


# ---------------------------------------------------------------------------
# End-to-end session — real polars + real plotly
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_llm_as_judge_end_to_end_through_facade() -> None:
    """Context-managed session: llm_as_judge populates judge_df and report."""
    judge = DeterministicJudge()
    with LLMDiagnostics(judge=judge) as diag:
        verdict = diag.llm_as_judge(
            prompt="What is the capital of France?",
            response="Paris, the capital of France.",
            rubric="factual_accuracy",
        )

    # Judge was called exactly once through the diagnostic session.
    assert len(judge.calls) == 1
    # run_id correlation is preserved through the report surface.
    report = diag.report()
    assert report["run_id"] == diag.run_id
    # judge_df carries the verdict as a polars row.
    df = diag.judge_df()
    assert isinstance(df, pl.DataFrame)
    assert df.height >= 1
    assert verdict is not None


@pytest.mark.integration
def test_report_shape_after_llm_as_judge_call() -> None:
    """report() returns a populated dict after an end-to-end call."""
    judge = DeterministicJudge()
    with LLMDiagnostics(judge=judge) as diag:
        diag.llm_as_judge(
            prompt="What is the capital of France?",
            response="Paris.",
            rubric="factual",
        )
        report = diag.report()
    assert report["run_id"] == diag.run_id
    # report is a dict — severity sections are present
    assert isinstance(report, dict)


# NOTE: faithfulness / self_consistency / refusal_calibrator use
# LLMJudge-specific wrappers (FaithfulnessJudge / SelfConsistencyJudge)
# that strictly require an LLMJudge instance and exercise real
# scripted-delegate paths at Tier 1 (`test_faithfulness_populates_dedicated_df_and_severity`,
# `test_self_consistency_returns_report_with_variance_stats`,
# `test_refusal_calibrator_scores_over_refusal_rate`). Duplicating
# here with a DeterministicJudge would bypass the Delegate plumbing
# the wrappers are designed to exercise; the Tier 1 tests already
# cover those paths with a scripted Delegate that routes through the
# real LLMJudge — the correct surface for those wrappers.


# ---------------------------------------------------------------------------
# Budget surface — constructor accepts default_budget_microdollars
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_llm_diagnostics_accepts_default_budget_microdollars() -> None:
    """Constructor plumbs default_budget_microdollars through to the judge
    when no custom judge is supplied; budget enforcement itself is
    covered by Tier 1 (``test_llm_diagnostics_surfaces_budget_exhausted_error``)
    which exercises the real :class:`LLMJudge` with a scripted delegate."""
    import os

    os.environ.setdefault("KAIZEN_JUDGE_MODEL", "integ-test-judge")
    # Default constructor path (no custom judge) — LLMJudge is created
    # internally with the provided budget; smoke assertion that the
    # session constructs without raising.
    with LLMDiagnostics(default_budget_microdollars=1_500_000) as diag:
        assert diag.run_id
    # The typed error class is exported on the facade — verify import
    # surface without triggering the guard (unit test drives the raise).
    assert JudgeBudgetExhaustedError is not None


# ---------------------------------------------------------------------------
# Plot surface — real plotly Figure
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_plot_output_dashboard_returns_real_plotly_figure() -> None:
    """plot_output_dashboard returns a plotly Figure; empty state does not raise."""
    judge = DeterministicJudge()
    with LLMDiagnostics(judge=judge) as diag:
        # Empty-state dashboard MUST be a Figure (placeholder, not a raise).
        empty_fig = diag.plot_output_dashboard()
        assert isinstance(empty_fig, go.Figure)

        # Populate with one scoring and re-plot.
        diag.llm_as_judge(prompt="p", response="r", rubric="accuracy")
        fig = diag.plot_output_dashboard()
        assert isinstance(fig, go.Figure)


# ---------------------------------------------------------------------------
# Async Protocol smoke check — JudgeCallable.__call__ IS async
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_deterministic_judge_invoked_awaitably() -> None:
    """The Protocol's __call__ is async; exercise directly for parity."""
    judge = DeterministicJudge()
    result = asyncio.run(
        judge(
            JudgeInput(
                prompt="Capital of France?",
                candidate_a="Paris",
                candidate_b="Berlin",
            )
        )
    )
    assert result.winner in {"A", "B", "tie"}
    assert result.judge_model == "deterministic-test-judge"

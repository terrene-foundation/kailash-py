# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 1 — Position-swap bias mitigation, scoring, budget enforcement.

Covers ``specs/kaizen-judges.md`` § "Position-swap bias mitigation",
§ "LLMJudge.__call__" budget enforcement, and the deterministic
helper math for ``_clamp_unit`` / ``_resolve_winner``. Uses a scripted
in-process delegate (NOT a Mock — a deterministic Python class
satisfying the Delegate duck-type) so each test runs in <1s with no
network.
"""
from __future__ import annotations

import asyncio
from typing import Any

import pytest

from kailash.diagnostics.protocols import JudgeInput
from kaizen.judges import JudgeBudgetExhaustedError, LLMJudge
from kaizen.judges._judge import _clamp_unit, _resolve_winner


class _ScriptedDelegate:
    """Deterministic Delegate stand-in for Tier 1 testing.

    This is NOT a mock — it's a deterministic Python class with a real
    ``run_structured`` implementation that returns scripted responses.
    The real production ``Delegate`` exposes the same surface; the
    LLMJudge can drive either one without code changes.

    Per ``rules/testing.md`` Tier 1 — mocks are allowed, but the
    structural-adapter form is preferred since it survives refactors
    that change which Delegate method LLMJudge calls.
    """

    def __init__(
        self,
        *,
        responses: list[dict[str, Any]],
        cost_microdollars_per_call: int = 1_000,
    ) -> None:
        self.responses = list(responses)  # popped left-to-right
        self.cost_per_call = cost_microdollars_per_call
        self.calls: list[dict[str, Any]] = []

    def run_structured(
        self, *, signature: Any, inputs: dict[str, Any]
    ) -> dict[str, Any]:
        """Return the next scripted response in dict-shape.

        LLMJudge accepts ``{"fields": {...}, "prompt_tokens": int, ...}``
        OR a bare dict of fields. We use the explicit-fields shape so the
        cost can flow through to the judge's spent counter.
        """
        self.calls.append({"signature": signature, "inputs": inputs})
        if not self.responses:
            raise RuntimeError("scripted delegate has no responses left")
        next_fields = self.responses.pop(0)
        return {
            "fields": next_fields,
            "prompt_tokens": 5,
            "completion_tokens": 7,
            "cost_microdollars": self.cost_per_call,
        }


# ---------------------------------------------------------------------------
# Test 1 — Pointwise scoring through scripted delegate
# ---------------------------------------------------------------------------


def test_pointwise_scoring_returns_clamped_score_from_signature() -> None:
    """Pointwise mode: candidate_b is None; LLMJudge returns the
    clamped score field plus reasoning, with cost_microdollars routed
    from the delegate response.

    Spec § "LLMJudge.__call__" — pointwise dispatch.
    """
    delegate = _ScriptedDelegate(
        responses=[{"score": 0.82, "reasoning": "Direct factual match."}],
        cost_microdollars_per_call=2_000,
    )
    judge = LLMJudge(
        judge_model="test-model-pointwise",
        budget_microdollars=1_000_000,
        delegate=delegate,
    )
    result = asyncio.run(
        judge(
            JudgeInput(
                prompt="What is the capital of France?",
                candidate_a="Paris.",
                rubric="factual_accuracy",
            )
        )
    )
    assert result.score == pytest.approx(0.82)
    assert result.winner is None
    assert result.cost_microdollars == 2_000
    assert "factual" in (result.reasoning or "")
    assert len(delegate.calls) == 1


# ---------------------------------------------------------------------------
# Test 2 — Pairwise mode runs two delegate calls (forward + swap)
# ---------------------------------------------------------------------------


def test_pairwise_scoring_runs_position_swap_with_two_delegate_calls() -> None:
    """Spec § "Position-swap bias mitigation" — pairwise runs the
    delegate twice (A-vs-B then B-vs-A) and aggregates the swapped
    score back into original-A coordinates.

    Two scripted responses both prefer the FIRST position with score
    0.7. Forward says "A wins"; swap (with A=originalB, B=originalA)
    also says "A wins" — meaning original B is preferred. The aggregate
    pref_a = 0.5*(0.7 + (1 - 0.7)) = 0.5 — a tie.
    """
    delegate = _ScriptedDelegate(
        responses=[
            # Forward: prefers position-A (= original A) with 0.7.
            {"winner": "A", "score_a": 0.7, "reasoning": "fwd: A more concise"},
            # Swap: prefers position-A (= original B) with 0.7.
            {"winner": "A", "score_a": 0.7, "reasoning": "swap: pos-A more concise"},
        ],
    )
    judge = LLMJudge(
        judge_model="test-model-pairwise",
        budget_microdollars=1_000_000,
        delegate=delegate,
    )
    result = asyncio.run(
        judge(
            JudgeInput(
                prompt="Which is better?",
                candidate_a="Short answer.",
                candidate_b="Longer, more detailed answer.",
                rubric="conciseness",
            )
        )
    )
    # Two delegate calls (forward + swap) — bias mitigation contract.
    assert len(delegate.calls) == 2
    # pref_a = mean(0.7, 1-0.7) = 0.5 → tie band
    assert result.score == pytest.approx(0.5)
    # Cost is summed from the two calls.
    assert result.cost_microdollars == 2_000


# ---------------------------------------------------------------------------
# Test 3 — Pairwise: both passes prefer original A → winner="A"
# ---------------------------------------------------------------------------


def test_pairwise_consistent_preference_for_a_returns_winner_a() -> None:
    """When forward pref-for-A = 0.9 AND swap pref-for-A (after remap) =
    1 - 0.1 = 0.9, the aggregate pref_a = 0.9 > 0.55 → winner='A'.

    Spec § "Position-swap bias mitigation" — both orderings prefer the
    same original candidate → return that winner.
    """
    delegate = _ScriptedDelegate(
        responses=[
            # Forward: pos-A (= original A) wins with 0.9.
            {"winner": "A", "score_a": 0.9, "reasoning": "fwd: A clearly better"},
            # Swap: pos-A (= original B) loses with 0.1 → original A
            # preference = 1 - 0.1 = 0.9.
            {"winner": "B", "score_a": 0.1, "reasoning": "swap: pos-B (origA) better"},
        ],
    )
    judge = LLMJudge(
        judge_model="test-model-consistent-a",
        budget_microdollars=1_000_000,
        delegate=delegate,
    )
    result = asyncio.run(
        judge(
            JudgeInput(
                prompt="Compare.",
                candidate_a="Excellent answer.",
                candidate_b="Poor answer.",
                rubric="quality",
            )
        )
    )
    assert result.winner == "A"
    assert result.score == pytest.approx(0.9)


# ---------------------------------------------------------------------------
# Test 4 — Budget exhaustion raises typed error, NOT partial result
# ---------------------------------------------------------------------------


def test_budget_exhausted_raises_typed_error_no_partial_result() -> None:
    """Spec § "LLMJudge.__call__" budget enforcement + § "Security
    threats / Cost blow-up" — a budget exhausted mid-eval MUST surface
    as ``JudgeBudgetExhaustedError`` rather than a partial-populated
    JudgeResult. ``rules/zero-tolerance.md`` Rule 3 BLOCKS silent
    partial success.

    Strategy: budget=500 μ$, each call costs 1000 μ$. First call
    succeeds and increments spent to 1000 (over cap). Second call's
    pre-check trips the guard.
    """
    delegate = _ScriptedDelegate(
        responses=[
            {"score": 0.5, "reasoning": "first call"},
            {"score": 0.5, "reasoning": "should not be reached"},
        ],
        cost_microdollars_per_call=1_000,
    )
    judge = LLMJudge(
        judge_model="test-model-budget",
        budget_microdollars=500,
        delegate=delegate,
    )
    inp = JudgeInput(prompt="p", candidate_a="a", rubric="r")

    # First call — succeeds, but spent (1000) now exceeds cap (500).
    asyncio.run(judge(inp))
    assert judge.spent_microdollars == 1_000

    # Second call — guard fires before delegate is invoked.
    with pytest.raises(JudgeBudgetExhaustedError) as excinfo:
        asyncio.run(judge(inp))
    err = excinfo.value
    assert err.spent_microdollars == 1_000
    assert err.budget_microdollars == 500
    assert err.judge_model == "test-model-budget"
    # Only ONE delegate call ever happened — the second was blocked at the guard.
    assert len(delegate.calls) == 1


# ---------------------------------------------------------------------------
# Test 5 — Empty prompt rejected with ValueError
# ---------------------------------------------------------------------------


def test_call_rejects_empty_prompt_with_value_error() -> None:
    """Spec § "LLMJudge.__call__" Raises — ``prompt`` and
    ``candidate_a`` MUST be non-empty. Validating at the boundary
    keeps the LLM call from spending budget on a malformed input.
    """
    delegate = _ScriptedDelegate(responses=[])
    judge = LLMJudge(
        judge_model="test-model-empty-prompt",
        budget_microdollars=1_000_000,
        delegate=delegate,
    )
    with pytest.raises(ValueError, match=r"prompt must be non-empty"):
        asyncio.run(judge(JudgeInput(prompt="", candidate_a="x", rubric="r")))
    # Delegate was NEVER invoked — input validation gates first.
    assert delegate.calls == []


# ---------------------------------------------------------------------------
# Test 6 — _clamp_unit clamps NaN / out-of-range to defaults
# ---------------------------------------------------------------------------


def test_clamp_unit_handles_nan_and_out_of_range_deterministically() -> None:
    """Spec § "_clamp_unit" — deterministic output formatting helper
    permitted by ``rules/agent-reasoning.md`` exception #3.

    Contract:
      * ``NaN`` → default (0.0)
      * ``"abc"`` → default
      * Score in [0, 1] passes through
      * Score in [1, 10] (some judges produce 0..10) is normalised /10
      * Score above 10 is clamped to 1.0
      * Negative scores clamped to 0.0
    """
    assert _clamp_unit(0.5) == pytest.approx(0.5)
    assert _clamp_unit(0.0) == pytest.approx(0.0)
    assert _clamp_unit(1.0) == pytest.approx(1.0)
    # 0..10 scale normalisation
    assert _clamp_unit(7.0) == pytest.approx(0.7)
    # Extreme over-range clamps to 1.0
    assert _clamp_unit(50.0) == pytest.approx(1.0)
    # Negative clamps to 0.0
    assert _clamp_unit(-2.5) == pytest.approx(0.0)
    # NaN → default
    assert _clamp_unit(float("nan")) == pytest.approx(0.0)
    # Non-numeric → default
    assert _clamp_unit("not-a-number") == pytest.approx(0.0)
    assert _clamp_unit(None) == pytest.approx(0.0)
    # Custom default honoured
    assert _clamp_unit("bad", default=0.5) == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# Test 7 — _resolve_winner deterministic tie-band semantics
# ---------------------------------------------------------------------------


def test_resolve_winner_deterministic_tie_band_and_agreement_handling() -> None:
    """Spec § "Position-swap bias mitigation" — tie-break is
    deterministic, no randomness, no position preference.

    Contract:
      * pref_a > 0.55 → "A"
      * pref_a < 0.45 → "B"
      * In tie band [0.45, 0.55]:
          - if forward + swap (after remap) agree on a winner → that winner
          - otherwise → "tie"
    """
    # Outside tie band → numeric verdict wins regardless of LLM strings.
    assert _resolve_winner(pref_a=0.9, winner_fwd="B", winner_swap="A") == "A"
    assert _resolve_winner(pref_a=0.1, winner_fwd="A", winner_swap="B") == "B"

    # In tie band — forward "A" + swap "B" remaps to "A" → consensus "A".
    assert _resolve_winner(pref_a=0.5, winner_fwd="A", winner_swap="B") == "A"

    # In tie band — forward "A" + swap "A" remaps to "B" → disagreement → "tie".
    assert _resolve_winner(pref_a=0.5, winner_fwd="A", winner_swap="A") == "tie"

    # In tie band — both "tie" → "tie" (no agreement).
    assert _resolve_winner(pref_a=0.5, winner_fwd="tie", winner_swap="tie") == "tie"


# ---------------------------------------------------------------------------
# Test 8 — Budget=0 cap with non-zero call cost trips the guard preemptively
# ---------------------------------------------------------------------------


def test_zero_budget_does_not_trip_guard_first_call_only() -> None:
    """Spec § "_guard_budget" — guard checks ``cap > 0 and spent >= cap``.

    A cap of zero is interpreted as "unbounded" (no guard fires); the
    cost tracker still records spend but the typed error is reserved
    for explicit positive caps that have been exhausted. This protects
    diagnostic-mode constructions where a Diagnostic session sets the
    cap to None / 0 to mean "no limit".
    """
    delegate = _ScriptedDelegate(
        responses=[
            {"score": 0.5, "reasoning": "first"},
            {"score": 0.6, "reasoning": "second"},
            {"score": 0.7, "reasoning": "third"},
        ],
        cost_microdollars_per_call=1_000,
    )
    judge = LLMJudge(
        judge_model="test-model-zero-budget",
        budget_microdollars=0,  # interpreted as unbounded
        delegate=delegate,
    )
    inp = JudgeInput(prompt="p", candidate_a="a", rubric="r")
    # All three calls succeed despite cap=0 because guard treats it as unbounded.
    asyncio.run(judge(inp))
    asyncio.run(judge(inp))
    asyncio.run(judge(inp))
    assert len(delegate.calls) == 3
    assert judge.spent_microdollars == 3_000

# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 1 — Error taxonomy, classification redaction, wrapper validation.

Covers ``specs/kaizen-judges.md`` § "Security threats" (typed errors,
sensitive-payload redaction), § "FaithfulnessJudge" / "SelfConsistencyJudge"
/ "RefusalCalibrator" wrapper invariants, and the ``LLMDiagnostics``
context-manager surface.
"""
from __future__ import annotations

import asyncio
from typing import Any

import pytest

from kailash.diagnostics.protocols import (
    Diagnostic,
    JudgeCallable,
    JudgeInput,
    JudgeResult,
)
from kaizen.judges import (
    FaithfulnessJudge,
    JudgeBudgetExhaustedError,
    LLMDiagnostics,
    LLMJudge,
    RefusalCalibrator,
    SelfConsistencyJudge,
    SelfConsistencyReport,
)
from kaizen.judges._judge import fingerprint_for_log


# ---------------------------------------------------------------------------
# Helper — deterministic Tier-1 delegate (NOT a mock)
# ---------------------------------------------------------------------------


class _ScriptedDelegate:
    """Same shape as the bias-mitigation file's helper; duplicated here
    to keep each test file self-contained per testing.md isolation rule.
    """

    def __init__(
        self,
        *,
        responses: list[dict[str, Any]],
        cost_microdollars_per_call: int = 1_000,
    ) -> None:
        self.responses = list(responses)
        self.cost_per_call = cost_microdollars_per_call
        self.calls: list[dict[str, Any]] = []

    def run_structured(
        self, *, signature: Any, inputs: dict[str, Any]
    ) -> dict[str, Any]:
        self.calls.append({"signature": signature, "inputs": inputs})
        next_fields = self.responses.pop(0)
        return {
            "fields": next_fields,
            "prompt_tokens": 5,
            "completion_tokens": 7,
            "cost_microdollars": self.cost_per_call,
        }


# ---------------------------------------------------------------------------
# Test 1 — TypeError on wrong JudgeInput type
# ---------------------------------------------------------------------------


def test_call_rejects_non_judge_input_with_typeerror() -> None:
    """Spec § "LLMJudge.__call__" Raises — a wire-boundary type guard.

    Passing a dict that LOOKS like a JudgeInput must be rejected
    loudly; silently accepting it would mask schema drift between the
    Protocol and adapters.
    """
    delegate = _ScriptedDelegate(responses=[])
    judge = LLMJudge(
        judge_model="test-model-typecheck",
        budget_microdollars=1_000_000,
        delegate=delegate,
    )
    bogus_input = {"prompt": "p", "candidate_a": "a"}  # dict, not JudgeInput
    with pytest.raises(TypeError, match=r"expects a JudgeInput instance"):
        asyncio.run(judge(bogus_input))  # type: ignore[arg-type]
    assert delegate.calls == []


# ---------------------------------------------------------------------------
# Test 2 — Empty candidate_a rejected
# ---------------------------------------------------------------------------


def test_call_rejects_empty_candidate_a_with_value_error() -> None:
    """Spec § "LLMJudge.__call__" Raises — candidate_a cannot be empty."""
    delegate = _ScriptedDelegate(responses=[])
    judge = LLMJudge(
        judge_model="test-model-empty-cand",
        budget_microdollars=1_000_000,
        delegate=delegate,
    )
    with pytest.raises(ValueError, match=r"candidate_a must be non-empty"):
        asyncio.run(judge(JudgeInput(prompt="p", candidate_a="", rubric="r")))


# ---------------------------------------------------------------------------
# Test 3 — sensitive=True path: fingerprint helper produces 8-hex sha256
# ---------------------------------------------------------------------------


def test_fingerprint_for_log_returns_sha256_8hex_for_sensitive_payloads() -> None:
    """Spec § "Security threats / Sensitive payload leakage" — when
    sensitive=True, candidate bodies MUST NOT appear in logs;
    8-hex SHA-256 fingerprints replace them.

    Cross-SDK contract — same prefix shape as
    ``rules/event-payload-classification.md`` MUST Rule 2.
    """
    fp = fingerprint_for_log("alice@example.com")
    assert fp.startswith("sha256:")
    # 8 hex chars after the prefix
    hex_part = fp.split(":", 1)[1]
    assert len(hex_part) == 8
    assert all(c in "0123456789abcdef" for c in hex_part)
    # Determinism — same input → same fingerprint
    assert fingerprint_for_log("alice@example.com") == fp
    # Different input → different fingerprint (with overwhelming probability)
    assert fingerprint_for_log("bob@example.com") != fp


# ---------------------------------------------------------------------------
# Test 4 — sensitive=True does NOT crash; constructor flag is plumbed
# ---------------------------------------------------------------------------


def test_llm_judge_accepts_sensitive_flag_without_error() -> None:
    """Spec § "Security threats" — sensitive flag enables redaction
    without changing the public surface (still a JudgeCallable).
    """
    delegate = _ScriptedDelegate(
        responses=[{"score": 0.8, "reasoning": "ok"}],
        cost_microdollars_per_call=500,
    )
    judge = LLMJudge(
        judge_model="test-model-sensitive",
        budget_microdollars=1_000_000,
        sensitive=True,
        delegate=delegate,
    )
    # Protocol conformance preserved.
    assert isinstance(judge, JudgeCallable)
    # Scoring still works end-to-end with sensitive payloads.
    result = asyncio.run(
        judge(
            JudgeInput(
                prompt="What is the user's SSN?",
                candidate_a="alice@example.com",  # PII
                rubric="privacy_appropriate",
            )
        )
    )
    assert result.score == pytest.approx(0.8)


# ---------------------------------------------------------------------------
# Test 5 — FaithfulnessJudge requires LLMJudge (strict typing)
# ---------------------------------------------------------------------------


def test_faithfulness_judge_rejects_non_llm_judge_with_typeerror() -> None:
    """Spec § "FaithfulnessJudge" — strict typing: requires LLMJudge,
    NOT any JudgeCallable. The wrapper reads ``budget_microdollars`` /
    ``spent_microdollars`` attributes that only LLMJudge guarantees.
    """

    class _NotAnLLMJudge:
        async def __call__(self, judge_input: JudgeInput) -> JudgeResult:
            raise NotImplementedError

    with pytest.raises(TypeError, match=r"requires an LLMJudge"):
        FaithfulnessJudge(_NotAnLLMJudge())  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Test 6 — FaithfulnessJudge overrides rubric to the bound value
# ---------------------------------------------------------------------------


def test_faithfulness_judge_overrides_rubric_to_grounding_contract() -> None:
    """Spec § "FaithfulnessJudge" — fixed rubric
    ``"faithfulness,grounded_in_context,no_fabrication"`` regardless of
    what the caller supplied. This is the wrapper's whole purpose: a
    rubric-bound JudgeCallable.
    """
    delegate = _ScriptedDelegate(
        responses=[{"score": 0.95, "reasoning": "well-grounded"}],
        cost_microdollars_per_call=500,
    )
    base = LLMJudge(
        judge_model="test-model-faithfulness",
        budget_microdollars=1_000_000,
        delegate=delegate,
    )
    wrapper = FaithfulnessJudge(base)
    assert wrapper.judge is base

    # Caller passes an unrelated rubric — the wrapper MUST override.
    result = asyncio.run(
        wrapper(
            JudgeInput(
                prompt="Summarise the document.",
                candidate_a="The doc says X.",
                reference="Document content: X.",
                rubric="caller_supplied_rubric_to_be_overridden",
            )
        )
    )
    assert result.score == pytest.approx(0.95)
    # The forwarded inputs MUST carry the bound rubric, not the caller's.
    assert (
        delegate.calls[0]["inputs"]["rubric"] == FaithfulnessJudge.FAITHFULNESS_RUBRIC
    )


# ---------------------------------------------------------------------------
# Test 7 — SelfConsistencyJudge requires n_samples >= 2
# ---------------------------------------------------------------------------


def test_self_consistency_judge_rejects_n_samples_below_two() -> None:
    """Spec § "SelfConsistencyJudge" — variance estimation requires
    at least 2 samples; n=1 would silently produce ``stdev=0`` with no
    statistical meaning.
    """
    delegate = _ScriptedDelegate(responses=[])
    base = LLMJudge(
        judge_model="test-model-sc-validation",
        budget_microdollars=1_000_000,
        delegate=delegate,
    )
    with pytest.raises(ValueError, match=r"n_samples must be >= 2"):
        SelfConsistencyJudge(base, n_samples=1)
    with pytest.raises(ValueError, match=r"n_samples must be >= 2"):
        SelfConsistencyJudge(base, n_samples=0)


# ---------------------------------------------------------------------------
# Test 8 — SelfConsistencyJudge.evaluate aggregates mean + stdev
# ---------------------------------------------------------------------------


def test_self_consistency_judge_evaluate_aggregates_mean_and_stdev() -> None:
    """Spec § "SelfConsistencyJudge" — runs n independent scorings
    through ONE shared CostTracker, returns ``SelfConsistencyReport``
    with mean, stdev, n_samples, total_cost_microdollars, per_sample.

    The shared budget contract is what makes this primitive useful:
    diagnostic users care about TOTAL cost across the sweep, not
    per-sample.
    """
    delegate = _ScriptedDelegate(
        responses=[
            {"score": 0.6, "reasoning": "sample 1"},
            {"score": 0.8, "reasoning": "sample 2"},
            {"score": 0.7, "reasoning": "sample 3"},
        ],
        cost_microdollars_per_call=500,
    )
    base = LLMJudge(
        judge_model="test-model-sc-aggregate",
        budget_microdollars=10_000_000,
        delegate=delegate,
    )
    sc = SelfConsistencyJudge(base, n_samples=3)
    report = asyncio.run(
        sc.evaluate(JudgeInput(prompt="p", candidate_a="a", rubric="r"))
    )
    assert isinstance(report, SelfConsistencyReport)
    assert report.n_samples == 3
    assert report.mean_score == pytest.approx((0.6 + 0.8 + 0.7) / 3.0)
    # Sample stdev > 0 because the three scores differ.
    assert report.stdev_score > 0.0
    # Cost summed across the sweep.
    assert report.total_cost_microdollars == 1_500
    # Per-sample traces preserved for forensic inspection.
    assert len(report.per_sample) == 3
    # Frozen dataclass — mutation BLOCKED.
    with pytest.raises((AttributeError, Exception)):
        report.mean_score = 0.0  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Bonus — RefusalCalibrator strict typing
# ---------------------------------------------------------------------------


def test_refusal_calibrator_rejects_non_llm_judge_with_typeerror() -> None:
    """Spec § "RefusalCalibrator" — same strict typing as
    FaithfulnessJudge; requires LLMJudge for budget attribute access.
    """

    class _NotAnLLMJudge:
        async def __call__(self, judge_input: JudgeInput) -> JudgeResult:
            raise NotImplementedError

    with pytest.raises(TypeError, match=r"requires an LLMJudge"):
        RefusalCalibrator(_NotAnLLMJudge())  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Bonus — LLMDiagnostics conforms to Diagnostic Protocol at runtime
# ---------------------------------------------------------------------------


def test_llm_diagnostics_construction_satisfies_diagnostic_protocol(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Spec § "LLMDiagnostics" Protocol conformance — at runtime
    ``isinstance(diag, Diagnostic)`` must hold and ``diag.run_id`` must
    be a non-empty string.
    """
    # Pin a model env var so the auto-constructed internal LLMJudge
    # (when the user passes no ``judge=...``) can resolve a model.
    monkeypatch.setenv("KAIZEN_JUDGE_MODEL", "test-model-diag-init")
    diag = LLMDiagnostics(default_budget_microdollars=1_000_000)
    assert isinstance(diag, Diagnostic)
    assert isinstance(diag.run_id, str) and diag.run_id


# ---------------------------------------------------------------------------
# Bonus — LLMDiagnostics __exit__ does NOT swallow JudgeBudgetExhaustedError
# ---------------------------------------------------------------------------


def test_llm_diagnostics_exit_returns_none_does_not_swallow_exceptions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Spec § "LLMDiagnostics" — ``__exit__`` MUST return None (no
    exception suppression). A non-None / truthy return would silently
    swallow JudgeBudgetExhaustedError and similar typed errors,
    defeating ``rules/zero-tolerance.md`` Rule 3.

    Tier 1 contract: drive ``__exit__`` directly with a synthetic
    exception (no need to invoke ``llm_as_judge`` which lazy-loads
    polars/plotly and pushes the test past the <1s cap).
    """
    monkeypatch.setenv("KAIZEN_JUDGE_MODEL", "test-model-diag-exit")
    judge = LLMJudge(
        judge_model="test-model-diag-exit",
        budget_microdollars=1_000_000,
        delegate=_ScriptedDelegate(responses=[]),
    )
    diag = LLMDiagnostics(judge=judge)
    diag.__enter__()
    # Simulate a typed error escaping the with-block; __exit__ MUST
    # return None (not True), which keeps Python re-raising.
    err = JudgeBudgetExhaustedError(
        spent_microdollars=1_000,
        budget_microdollars=500,
        judge_model="test-model-diag-exit",
    )
    swallowed = diag.__exit__(type(err), err, None)
    # None or False → exception is re-raised by the with-statement.
    assert not swallowed

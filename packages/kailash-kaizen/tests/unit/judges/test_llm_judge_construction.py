# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 1 — LLMJudge construction, signature, protocol conformance.

Covers ``specs/kaizen-judges.md`` § 11 invariants for the
construction surface: protocol conformance, env-sourced model
resolution, integer-microdollar budget guards, run_id semantics.
"""
from __future__ import annotations

import os
import re

import pytest
from kailash.diagnostics.protocols import JudgeCallable

from kaizen.judges import JudgeBudgetExhaustedError, LLMJudge, resolve_judge_model

# ---------------------------------------------------------------------------
# Test 1 — Protocol conformance at runtime
# ---------------------------------------------------------------------------


def test_llm_judge_construction_satisfies_judge_callable_protocol() -> None:
    """``isinstance(LLMJudge(...), JudgeCallable)`` MUST hold at runtime.

    Spec § "Invariants" #1 — the Protocol is ``@runtime_checkable``, so
    downstream adapters can wire any LLMJudge into a Diagnostic without
    inheritance.
    """
    judge = LLMJudge(judge_model="test-model-construction", budget_microdollars=1)
    assert isinstance(judge, JudgeCallable)


# ---------------------------------------------------------------------------
# Test 2 — Budget MUST be a non-negative int (bool BLOCKED)
# ---------------------------------------------------------------------------


def test_llm_judge_construction_rejects_bool_budget_with_typeerror() -> None:
    """Spec § "Invariants" #2 — ``bool`` is BLOCKED for budget_microdollars.

    ``isinstance(True, int)`` is ``True`` in Python, but the LLMJudge
    constructor MUST reject it because conflating boolean with budget
    sentinel would let ``budget_microdollars=True`` silently mean ``1``.
    """
    with pytest.raises(TypeError, match=r"budget_microdollars must be int"):
        LLMJudge(judge_model="test-model-bool", budget_microdollars=True)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Test 3 — Negative budget rejected with ValueError
# ---------------------------------------------------------------------------


def test_llm_judge_construction_rejects_negative_budget_with_value_error() -> None:
    """Spec § "Invariants" #2 — negative microdollar caps are nonsense.

    A negative cap would mean the very first call exhausts the budget,
    which is a configuration error users want loud, not silent.
    """
    with pytest.raises(ValueError, match=r"budget_microdollars must be >= 0"):
        LLMJudge(judge_model="test-model-neg", budget_microdollars=-1)


# ---------------------------------------------------------------------------
# Test 4 — Empty run_id rejected
# ---------------------------------------------------------------------------


def test_llm_judge_construction_rejects_empty_run_id_with_value_error() -> None:
    """Spec § "Invariants" #3 — caller-supplied run_id MUST be non-empty.

    An empty ``run_id`` would break log-correlation grep ("run_id=" with
    no value), so the constructor refuses it loudly.
    """
    with pytest.raises(ValueError, match=r"run_id must be a non-empty string"):
        LLMJudge(
            judge_model="test-model-empty-run-id",
            budget_microdollars=1,
            run_id="",
        )


# ---------------------------------------------------------------------------
# Test 5 — Auto-generated run_id is hex UUID4 string
# ---------------------------------------------------------------------------


def test_llm_judge_construction_generates_hex_run_id_when_omitted() -> None:
    """Spec § "Invariants" #3 — when caller omits run_id, framework
    fills with a 32-char UUID4 hex (``uuid.uuid4().hex``)."""
    judge = LLMJudge(judge_model="test-model-uuid", budget_microdollars=1)
    assert isinstance(judge.run_id, str)
    assert re.fullmatch(r"[0-9a-f]{32}", judge.run_id)


# ---------------------------------------------------------------------------
# Test 6 — Properties expose the duck-type surface LLMDiagnostics needs
# ---------------------------------------------------------------------------


def test_llm_judge_properties_expose_budget_spent_and_model_attributes() -> None:
    """Spec § "Attributes (duck-type surface for LLMDiagnostics)" — the
    Diagnostic wrapper reads these three properties; they MUST be wired
    on the public surface in the documented shapes."""
    judge = LLMJudge(judge_model="test-model-props", budget_microdollars=2_000_000)
    assert judge.budget_microdollars == 2_000_000
    assert judge.spent_microdollars == 0
    assert judge.judge_model == "test-model-props"
    # remaining_microdollars derived (budget - spent)
    assert judge.remaining_microdollars == 2_000_000


# ---------------------------------------------------------------------------
# Test 7 — Env-sourced model resolution per rules/env-models.md
# ---------------------------------------------------------------------------


def test_resolve_judge_model_uses_kaizen_judge_model_env_var(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Spec § "Invariants" #4 — model resolution priority puts
    ``KAIZEN_JUDGE_MODEL`` first in the chain.

    Per ``rules/env-models.md``, hardcoded model strings are BLOCKED;
    the resolver MUST read from env. This test mutates env via
    ``monkeypatch`` (test-scope) and proves the resolver reads it.
    """
    # Clear all judge-model env vars so KAIZEN_JUDGE_MODEL wins
    # unambiguously regardless of the host's .env.
    for key in (
        "KAIZEN_JUDGE_MODEL",
        "OPENAI_JUDGE_MODEL",
        "OPENAI_PROD_MODEL",
        "DEFAULT_LLM_MODEL",
    ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("KAIZEN_JUDGE_MODEL", "kaizen-test-model-priority")

    assert resolve_judge_model() == "kaizen-test-model-priority"


# ---------------------------------------------------------------------------
# Test 8 — Resolver raises when no env var is set (BLOCKED hardcoded default)
# ---------------------------------------------------------------------------


def test_resolve_judge_model_raises_runtime_error_when_no_env_var_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Spec § "Invariants" #4 — hardcoding a default model is BLOCKED.

    When NO env var resolves and no explicit arg is given, the resolver
    MUST raise ``RuntimeError`` rather than fall back to ``"gpt-4"`` or
    similar — that fallback would silently lock production to a stale
    provider.
    """
    for key in (
        "KAIZEN_JUDGE_MODEL",
        "OPENAI_JUDGE_MODEL",
        "OPENAI_PROD_MODEL",
        "DEFAULT_LLM_MODEL",
    ):
        monkeypatch.delenv(key, raising=False)

    with pytest.raises(RuntimeError, match=r"could not resolve a judge model"):
        resolve_judge_model()


# ---------------------------------------------------------------------------
# Verify the BudgetExhausted error symbol is the canonical one used at
# guard time. (Construction-time sanity; full raise behaviour is covered
# in the budget-enforcement test file.)
# ---------------------------------------------------------------------------


def test_judge_budget_exhausted_error_is_runtime_error_subclass() -> None:
    """Error taxonomy invariant: ``JudgeBudgetExhaustedError`` is a
    ``RuntimeError`` subclass, so ``except RuntimeError`` catches it
    AND ``except JudgeBudgetExhaustedError`` discriminates it.

    Spec § "Security threats / Cost blow-up" mandates a typed error;
    rules/zero-tolerance.md Rule 3 BLOCKS partial-success payloads.
    """
    assert issubclass(JudgeBudgetExhaustedError, RuntimeError)
    err = JudgeBudgetExhaustedError(
        spent_microdollars=10,
        budget_microdollars=5,
        judge_model="test-model-error",
    )
    assert err.spent_microdollars == 10
    assert err.budget_microdollars == 5
    assert err.judge_model == "test-model-error"
    # Message MUST mention budget exhaustion + the model name (operator-readable).
    assert "budget exhausted" in str(err)
    assert "test-model-error" in str(err)

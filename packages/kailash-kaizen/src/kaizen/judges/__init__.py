# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""LLM-as-judge diagnostics for kailash-kaizen.

This package hosts the Kaizen-side concrete implementations of the
cross-SDK judge + diagnostic protocols:

    * :class:`LLMJudge` — implements
      :class:`kailash.diagnostics.protocols.JudgeCallable` (async
      ``__call__`` accepting :class:`JudgeInput`, returning
      :class:`JudgeResult`). Wraps a
      :class:`kaizen_agents.Delegate` with Signature-structured
      scoring, position-swap bias mitigation, and typed budget
      enforcement via :class:`JudgeBudgetExhaustedError`.
    * :class:`FaithfulnessJudge` — rubric-bound wrapper for RAG
      grounding scoring (delegates to ``LLMJudge``).
    * :class:`SelfConsistencyJudge` — runs ``n`` independent scorings
      through one shared :class:`kaizen.cost.CostTracker` and returns
      a :class:`SelfConsistencyReport` with variance statistics.
    * :class:`RefusalCalibrator` — scores over- / under-refusal rates
      against benign + harmful prompt sets.
    * :class:`LLMDiagnostics` — context-managed Diagnostic session
      that satisfies :class:`kailash.diagnostics.protocols.Diagnostic`
      and aggregates the four axes above into one ``report()`` dict
      with severity banding + polars DataFrames + a plotly dashboard.

Public surface (the facade-import path required by
``rules/orphan-detection.md`` §1)::

    from kaizen.judges import (
        LLMJudge,
        LLMDiagnostics,
        FaithfulnessJudge,
        SelfConsistencyJudge,
        RefusalCalibrator,
        SelfConsistencyReport,
        JudgeBudgetExhaustedError,
    )

    with LLMDiagnostics() as diag:
        verdict = diag.llm_as_judge(
            prompt="What is the capital of France?",
            response="Paris, the capital of France.",
            rubric="factual_accuracy",
        )
        findings = diag.report()

The ``plot_output_dashboard()`` method and downstream plotly access
require ``pip install kailash-kaizen[judges]``. ``report()`` and
every ``*_df()`` accessor work on the base install.

Algorithmic metrics (ROUGE / BLEU / BERTScore) deliberately DO NOT
live in this namespace — they belong under :mod:`kaizen.evaluation`
because they share no LLM / cost / budget surface with the judge
primitives. See ``specs/kaizen-evaluation.md`` for the split.

Cross-SDK Protocol reference:
``src/kailash/diagnostics/protocols.py`` (PR#0 of issue #567).
"""
from __future__ import annotations

from kaizen.judges._judge import (
    JudgeBudgetExhaustedError,
    LLMJudge,
    resolve_judge_model,
)
from kaizen.judges._wrappers import (
    FaithfulnessJudge,
    RefusalCalibrator,
    SelfConsistencyJudge,
    SelfConsistencyReport,
)
from kaizen.judges.llm_diagnostics import LLMDiagnostics

__all__ = [
    "LLMJudge",
    "LLMDiagnostics",
    "FaithfulnessJudge",
    "SelfConsistencyJudge",
    "SelfConsistencyReport",
    "RefusalCalibrator",
    "JudgeBudgetExhaustedError",
    "resolve_judge_model",
]

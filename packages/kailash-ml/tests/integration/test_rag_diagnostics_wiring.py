# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 2 wiring tests for RAGDiagnostics.

Per `rules/orphan-detection.md` §1 + `rules/facade-manager-detection.md`
Rule 2, this file imports RAGDiagnostics through the
``kailash_ml.diagnostics`` facade (NOT the concrete module path) and
drives a realistic multi-query evaluation with a real (in-process)
JudgeCallable implementation so we assert externally-observable
effects rather than mocked internals.

The file also asserts Protocol conformance at runtime — the whole
point of the PR is for `isinstance(rag, Diagnostic)` to hold, so a
plain unit test of the class in isolation would prove the class-shape
contract but NOT the Protocol-conformance contract that downstream
consumers rely on.
"""
from __future__ import annotations

from typing import Any

import pytest

from kailash.diagnostics.protocols import (  # noqa: E402
    Diagnostic,
    JudgeCallable,
    JudgeInput,
    JudgeResult,
)

# Import through the facade — NOT `from kailash_ml.diagnostics.rag import ...`
# per rules/orphan-detection.md §1 (downstream consumers see the public
# attribute, so the wiring test MUST exercise the same surface).
from kailash_ml.diagnostics import RAGDiagnostics  # noqa: E402


# ---------------------------------------------------------------------------
# Test fixtures — in-process JudgeCallable implementations
# ---------------------------------------------------------------------------


class _ScriptedJudge:
    """JudgeCallable that returns pre-scripted scores by index.

    Conforms to kailash.diagnostics.protocols.JudgeCallable; used in
    place of a network LLM to keep Tier 2 tests deterministic while
    exercising the real Protocol dispatch path.
    """

    def __init__(self, scores: list[float]) -> None:
        self._scores = list(scores)
        self._idx = 0
        self.call_count = 0
        self.last_input: JudgeInput | None = None

    async def __call__(self, judge_input: JudgeInput) -> JudgeResult:
        self.last_input = judge_input
        score = self._scores[self._idx % len(self._scores)]
        self._idx += 1
        self.call_count += 1
        return JudgeResult(
            score=score,
            winner=None,
            reasoning=f"scripted judge, score={score}",
            judge_model="test-scripted-judge",
            cost_microdollars=100,
            prompt_tokens=10,
            completion_tokens=10,
        )


# ---------------------------------------------------------------------------
# Protocol conformance — load-bearing test
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_rag_diagnostics_satisfies_diagnostic_protocol() -> None:
    """RAGDiagnostics satisfies the cross-SDK Diagnostic Protocol.

    This is the load-bearing structural test for the PR: if this
    fails, downstream consumers cannot rely on
    `isinstance(rag, Diagnostic)` for type-safe Protocol dispatch.
    """
    rag = RAGDiagnostics()
    assert isinstance(rag, Diagnostic)
    assert isinstance(rag.run_id, str) and len(rag.run_id) > 0


@pytest.mark.integration
def test_rag_diagnostics_explicit_run_id_is_honored() -> None:
    """User-supplied run_id is preserved for cross-system correlation."""
    rag = RAGDiagnostics(run_id="my-rag-session-42")
    assert rag.run_id == "my-rag-session-42"
    assert isinstance(rag, Diagnostic)


@pytest.mark.integration
def test_rag_diagnostics_scripted_judge_conforms_to_judge_callable() -> None:
    """The scripted judge fixture conforms to JudgeCallable at runtime."""
    judge = _ScriptedJudge(scores=[0.5])
    assert isinstance(judge, JudgeCallable)


# ---------------------------------------------------------------------------
# End-to-end evaluate() with real JudgeCallable
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_evaluate_end_to_end_with_judge() -> None:
    """Real evaluate() call routes through the JudgeCallable Protocol.

    Three queries with mixed retrieval quality, scripted judge returning
    varying faithfulness scores. Assert externally-observable output:
    DataFrame shape, metric values, judge call count, run_id propagation.
    """
    judge = _ScriptedJudge(scores=[0.9, 0.7, 0.4])
    with RAGDiagnostics(judge=judge, run_id="eval-e2e-1") as rag:
        assert isinstance(rag, Diagnostic)
        df = rag.evaluate(
            queries=[
                "What is photosynthesis?",
                "How do plants grow?",
                "What is the capital of Mars?",  # nonsensical query
            ],
            retrieved_contexts=[
                ["Photosynthesis converts light into chemical energy."],
                ["Plants grow by absorbing water and nutrients."],
                ["Mars has no capital; it is an uninhabited planet."],
            ],
            answers=[
                "Photosynthesis converts light into energy.",
                "Plants grow via water absorption.",
                "Mars has no capital.",
            ],
            retrieved_ids=[["doc_photo"], ["doc_plants"], ["doc_mars"]],
            ground_truth_ids=[["doc_photo"], ["doc_plants"], ["doc_mars"]],
            k=1,
        )

    # DataFrame shape and content.
    assert df.height == 3
    assert set(df.columns) >= {
        "idx",
        "recall_at_k",
        "precision_at_k",
        "context_utilisation",
        "faithfulness",
        "mode",
    }
    # All three queries had perfect retrieval (retrieved == relevant).
    assert all(r == 1.0 for r in df["recall_at_k"].to_list())
    # Faithfulness scores come from the scripted judge.
    faith = df["faithfulness"].to_list()
    assert faith == [0.9, 0.7, 0.4]
    # All rows were scored through the judge path.
    assert all(m == "judge" for m in df["mode"].to_list())
    # Judge was invoked exactly once per query.
    assert judge.call_count == 3


@pytest.mark.integration
def test_evaluate_without_judge_falls_back_to_metrics_only() -> None:
    """Without a judge, evaluate operates in metrics-only mode (no LLM calls)."""
    with RAGDiagnostics() as rag:
        df = rag.evaluate(
            queries=["Test query"],
            retrieved_contexts=[["Matching context with shared tokens."]],
            answers=["Matching context with shared tokens."],
            retrieved_ids=[["doc_1"]],
            ground_truth_ids=[["doc_1"]],
            k=1,
        )
    assert df["mode"][0] == "metrics_only"
    # Recall = 1.0 (retrieved doc == ground truth).
    assert df["recall_at_k"][0] == 1.0


# ---------------------------------------------------------------------------
# Report end-to-end — run_id propagation, severity contract
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_report_propagates_run_id_from_constructor() -> None:
    """The run_id passed to __init__ appears in report()['run_id']."""
    rag = RAGDiagnostics(run_id="cross-system-correlation-id")
    report = rag.report()
    assert report["run_id"] == "cross-system-correlation-id"


@pytest.mark.integration
def test_report_after_evaluation_populates_severities() -> None:
    """After evaluate(), report() returns populated severities (not UNKNOWN)."""
    judge = _ScriptedJudge(scores=[0.85])
    rag = RAGDiagnostics(judge=judge)
    rag.evaluate(
        queries=["q"],
        retrieved_contexts=[["relevant context"]],
        answers=["matching answer"],
        retrieved_ids=[["doc_1"]],
        ground_truth_ids=[["doc_1"]],
    )
    report = rag.report()
    # Retrieval is HEALTHY (recall = 1.0).
    assert report["retrieval"]["severity"] == "HEALTHY"
    # Faithfulness driven by scripted judge at 0.85.
    assert report["faithfulness"]["severity"] == "HEALTHY"
    # Evaluations captured.
    assert report["evaluations"] == 1


@pytest.mark.integration
def test_report_empty_session_returns_unknown_without_raising() -> None:
    """An empty session's report() is well-formed with UNKNOWN severities."""
    rag = RAGDiagnostics()
    report = rag.report()
    assert report["evaluations"] == 0
    assert report["retriever_comparisons"] == 0
    assert report["retrieval"]["severity"] == "UNKNOWN"
    assert report["faithfulness"]["severity"] == "UNKNOWN"


# ---------------------------------------------------------------------------
# compare_retrievers end-to-end
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_compare_retrievers_produces_non_empty_leaderboard() -> None:
    """Real compare_retrievers() call returns a polars leaderboard sorted by MRR."""

    def perfect(q: str, k: int) -> list[tuple[str, str, float]]:
        return [("doc_target", "perfect hit", 0.99)][:k]

    def irrelevant(q: str, k: int) -> list[tuple[str, str, float]]:
        return [("doc_other", "wrong doc", 0.5)][:k]

    def partial(q: str, k: int) -> list[tuple[str, str, float]]:
        return [
            ("doc_noise", "noise", 0.6),
            ("doc_target", "hit at rank 2", 0.4),
        ][:k]

    eval_set = [{"query": "Find target", "relevant_ids": ["doc_target"]}]
    with RAGDiagnostics() as rag:
        board = rag.compare_retrievers(
            retrievers={
                "perfect": perfect,
                "irrelevant": irrelevant,
                "partial": partial,
            },
            eval_set=eval_set,
            k=2,
        )
        assert board.height == 3
        # MRR ordering: perfect=1.0 > partial=0.5 > irrelevant=0.0.
        names = board["retriever"].to_list()
        assert names[0] == "perfect"
        assert names[-1] == "irrelevant"
        # leaderboard_df() captures the aggregate row.
        assert rag.leaderboard_df().height == 3


@pytest.mark.integration
def test_compare_retrievers_report_top_retriever() -> None:
    """After compare_retrievers(), report() surfaces the top retriever name."""

    def winner(q: str, k: int) -> list[tuple[str, str, float]]:
        return [("doc_42", "hit", 0.9)][:k]

    rag = RAGDiagnostics()
    rag.compare_retrievers(
        retrievers={"winner": winner},
        eval_set=[{"query": "q", "relevant_ids": ["doc_42"]}],
        k=1,
    )
    report = rag.report()
    assert report["retriever_leaderboard"]["severity"] == "HEALTHY"
    assert report["retriever_leaderboard"]["top"] == "winner"


# ---------------------------------------------------------------------------
# Sensitive mode — query bodies redacted in metrics_df
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_sensitive_mode_redacts_query_preview() -> None:
    """sensitive=True replaces query_preview with '<redacted>' in metrics_df."""
    with RAGDiagnostics(sensitive=True) as rag:
        rag.evaluate(
            queries=["This query contains a PII email: alice@example.com"],
            retrieved_contexts=[["context"]],
            answers=["answer"],
            retrieved_ids=[["doc_1"]],
            ground_truth_ids=[["doc_1"]],
        )
    df = rag.metrics_df()
    assert df["query_preview"][0] == "<redacted>"
    # Ensure the raw PII does not appear anywhere in the DataFrame's repr.
    assert "alice@example.com" not in repr(df.row(0, named=True))


# ---------------------------------------------------------------------------
# __exit__ cleanup contract
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_context_manager_exit_returns_none() -> None:
    """__exit__ returns None (doesn't suppress exceptions per Protocol)."""
    rag = RAGDiagnostics()
    result = rag.__exit__(None, None, None)
    assert result is None


@pytest.mark.integration
def test_context_manager_does_not_swallow_exceptions() -> None:
    """Exceptions raised inside the `with` block propagate out."""
    with pytest.raises(RuntimeError, match="test-error"):
        with RAGDiagnostics():
            raise RuntimeError("test-error")

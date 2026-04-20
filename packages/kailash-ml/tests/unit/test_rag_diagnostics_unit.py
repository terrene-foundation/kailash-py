# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 1 unit tests for RAGDiagnostics — fast, no I/O, no network.

Covers input validation, run_id semantics, IR-metric math on known-answer
fixtures, extras-gating loud-fail contract for plotly + ragas, and the
empty-state contract on report() + metrics_df() + leaderboard_df().
Integration-style tests (facade import, Protocol conformance against a
real JudgeCallable) live in tests/integration/test_rag_diagnostics_wiring.py.
"""
from __future__ import annotations

from typing import Any

import pytest

from kailash.diagnostics.protocols import JudgeInput, JudgeResult
from kailash_ml.diagnostics import RAGDiagnostics
from kailash_ml.diagnostics import rag as rag_mod


# ---------------------------------------------------------------------------
# __init__ validation
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_init_rejects_empty_run_id() -> None:
    """An empty-string run_id is rejected; user-supplied IDs MUST have content."""
    with pytest.raises(ValueError, match="run_id"):
        RAGDiagnostics(run_id="")


@pytest.mark.unit
def test_init_rejects_zero_max_history() -> None:
    """max_history MUST be >= 1 (bounded-memory contract)."""
    with pytest.raises(ValueError, match="max_history must be >= 1"):
        RAGDiagnostics(max_history=0)


@pytest.mark.unit
def test_init_rejects_zero_max_leaderboard_history() -> None:
    """max_leaderboard_history MUST be >= 1."""
    with pytest.raises(ValueError, match="max_leaderboard_history must be >= 1"):
        RAGDiagnostics(max_leaderboard_history=0)


@pytest.mark.unit
def test_init_rejects_non_judge_callable() -> None:
    """judge MUST conform to the JudgeCallable Protocol."""

    class NotAJudge:
        pass

    with pytest.raises(TypeError, match="JudgeCallable"):
        RAGDiagnostics(judge=NotAJudge())  # type: ignore[arg-type]


@pytest.mark.unit
def test_init_accepts_no_judge() -> None:
    """judge=None is permitted — falls back to metrics_only mode."""
    rag = RAGDiagnostics()
    assert rag._judge is None  # type: ignore[attr-defined]


@pytest.mark.unit
def test_init_accepts_explicit_run_id() -> None:
    """Explicit run_id kwarg is honored verbatim."""
    rag = RAGDiagnostics(run_id="rag-session-42")
    assert rag.run_id == "rag-session-42"


@pytest.mark.unit
def test_init_generates_unique_run_ids() -> None:
    """Two separately-constructed sessions get distinct auto-generated IDs."""
    a = RAGDiagnostics()
    b = RAGDiagnostics()
    assert a.run_id != b.run_id


# ---------------------------------------------------------------------------
# Protocol conformance — runtime-checkable
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_rag_satisfies_diagnostic_protocol_runtime_check() -> None:
    """RAGDiagnostics MUST satisfy the cross-SDK Diagnostic Protocol.

    The Protocol is @runtime_checkable, so isinstance() IS the
    structural check — if this test fails, downstream Protocol dispatch
    breaks.
    """
    from kailash.diagnostics.protocols import Diagnostic

    rag = RAGDiagnostics()
    assert isinstance(rag, Diagnostic)


# ---------------------------------------------------------------------------
# evaluate() input validation
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_evaluate_rejects_empty_queries() -> None:
    """evaluate MUST refuse zero-length input."""
    rag = RAGDiagnostics()
    with pytest.raises(ValueError, match="non-empty"):
        rag.evaluate(queries=[], retrieved_contexts=[], answers=[])


@pytest.mark.unit
def test_evaluate_rejects_mismatched_lengths() -> None:
    """evaluate MUST refuse mismatched queries/contexts/answers lengths."""
    rag = RAGDiagnostics()
    with pytest.raises(ValueError, match="same length"):
        rag.evaluate(
            queries=["q1", "q2"],
            retrieved_contexts=[["c1"]],
            answers=["a1", "a2"],
        )


@pytest.mark.unit
def test_evaluate_rejects_k_below_one() -> None:
    """evaluate's k MUST be >= 1."""
    rag = RAGDiagnostics()
    with pytest.raises(ValueError, match="k must be >= 1"):
        rag.evaluate(
            queries=["q"],
            retrieved_contexts=[["c"]],
            answers=["a"],
            k=0,
        )


@pytest.mark.unit
def test_evaluate_rejects_mismatched_ground_truth_length() -> None:
    """ground_truth_ids MUST match queries length when provided."""
    rag = RAGDiagnostics()
    with pytest.raises(ValueError, match="ground_truth_ids"):
        rag.evaluate(
            queries=["q1", "q2"],
            retrieved_contexts=[["c1"], ["c2"]],
            answers=["a1", "a2"],
            ground_truth_ids=[["t1"]],  # wrong length
        )


# ---------------------------------------------------------------------------
# IR-metric math — known-answer fixtures
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_recall_at_k_all_relevant_retrieved() -> None:
    """recall@k = 1.0 when all relevant docs appear in top-k."""
    rag = RAGDiagnostics()
    assert rag.recall_at_k(["a", "b", "c"], ["a", "b"], k=3) == 1.0


@pytest.mark.unit
def test_recall_at_k_half_relevant() -> None:
    """recall@k = 0.5 when half of the relevant set is retrieved."""
    rag = RAGDiagnostics()
    assert rag.recall_at_k(["a", "x", "y"], ["a", "b"], k=3) == 0.5


@pytest.mark.unit
def test_recall_at_k_zero_on_empty_relevant() -> None:
    """recall@k = 0.0 when no ground-truth docs are labelled."""
    rag = RAGDiagnostics()
    assert rag.recall_at_k(["a", "b"], [], k=2) == 0.0


@pytest.mark.unit
def test_precision_at_k_one_hit() -> None:
    """precision@k = 1/3 when one of three top-k is relevant."""
    rag = RAGDiagnostics()
    assert rag.precision_at_k(["a", "x", "y"], ["a", "b"], k=3) == pytest.approx(1 / 3)


@pytest.mark.unit
def test_reciprocal_rank_first_position() -> None:
    """RR = 1.0 when the first retrieved doc is relevant."""
    rag = RAGDiagnostics()
    assert rag.reciprocal_rank(["a", "x"], ["a"]) == 1.0


@pytest.mark.unit
def test_reciprocal_rank_second_position() -> None:
    """RR = 0.5 when the relevant doc is in position 2."""
    rag = RAGDiagnostics()
    assert rag.reciprocal_rank(["x", "a"], ["a"]) == 0.5


@pytest.mark.unit
def test_reciprocal_rank_missing_is_zero() -> None:
    """RR = 0.0 when no relevant doc is retrieved."""
    rag = RAGDiagnostics()
    assert rag.reciprocal_rank(["x", "y"], ["a"]) == 0.0


@pytest.mark.unit
def test_ndcg_at_k_perfect_ranking() -> None:
    """nDCG@k = 1.0 when the top-k matches the relevant set in order."""
    rag = RAGDiagnostics()
    # Two relevant docs in top-2 positions — ideal ordering.
    assert rag.ndcg_at_k(["a", "b", "x"], ["a", "b"], k=3) == pytest.approx(1.0)


@pytest.mark.unit
def test_ndcg_at_k_zero_on_empty_relevant() -> None:
    """nDCG@k = 0.0 when no ground-truth docs are labelled."""
    rag = RAGDiagnostics()
    assert rag.ndcg_at_k(["a", "b"], [], k=2) == 0.0


# ---------------------------------------------------------------------------
# Evaluate end-to-end (metrics-only mode — no judge, no ragas)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_evaluate_metrics_only_mode_records_recall(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without a judge or ragas, evaluate captures IR metrics correctly."""
    # Force ragas_unavailable path for determinism.
    monkeypatch.setattr(rag_mod, "_try_ragas_evaluate", lambda **_: None)
    rag = RAGDiagnostics()
    df = rag.evaluate(
        queries=["What is photosynthesis?"],
        retrieved_contexts=[["Photosynthesis converts light into energy."]],
        answers=["Photosynthesis converts light."],
        retrieved_ids=[["doc_42"]],
        ground_truth_ids=[["doc_42"]],
        k=1,
    )
    assert df.height == 1
    assert df["recall_at_k"][0] == 1.0
    assert df["precision_at_k"][0] == 1.0
    assert df["mode"][0] == "metrics_only"
    # Session log captured the entry.
    assert rag.metrics_df().height == 1


@pytest.mark.unit
def test_evaluate_metrics_only_mode_zero_recall_on_wrong_retrieval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Recall=0.0 when retrieved IDs do not overlap with ground truth."""
    monkeypatch.setattr(rag_mod, "_try_ragas_evaluate", lambda **_: None)
    rag = RAGDiagnostics()
    df = rag.evaluate(
        queries=["Query?"],
        retrieved_contexts=[["Irrelevant content."]],
        answers=["Answer."],
        retrieved_ids=[["doc_99"]],
        ground_truth_ids=[["doc_42"]],
        k=1,
    )
    assert df["recall_at_k"][0] == 0.0


# ---------------------------------------------------------------------------
# Bounded memory — deque(maxlen=N) eviction
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_metrics_df_honors_max_history_bound(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Older entries are evicted FIFO once max_history is reached."""
    monkeypatch.setattr(rag_mod, "_try_ragas_evaluate", lambda **_: None)
    rag = RAGDiagnostics(max_history=3)
    for i in range(5):
        rag.evaluate(
            queries=[f"q{i}"],
            retrieved_contexts=[[f"c{i}"]],
            answers=[f"a{i}"],
            retrieved_ids=[[f"doc_{i}"]],
            ground_truth_ids=[[f"doc_{i}"]],
        )
    # Only the last 3 entries survive.
    assert rag.metrics_df().height == 3


# ---------------------------------------------------------------------------
# compare_retrievers input validation
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_compare_retrievers_rejects_empty_retrievers_dict() -> None:
    rag = RAGDiagnostics()
    with pytest.raises(ValueError, match="retrievers dict"):
        rag.compare_retrievers(
            retrievers={},
            eval_set=[{"query": "q", "relevant_ids": ["a"]}],
        )


@pytest.mark.unit
def test_compare_retrievers_rejects_empty_eval_set() -> None:
    rag = RAGDiagnostics()
    with pytest.raises(ValueError, match="eval_set"):
        rag.compare_retrievers(
            retrievers={"x": lambda _q, _k: []},
            eval_set=[],
        )


@pytest.mark.unit
def test_compare_retrievers_builds_leaderboard() -> None:
    """compare_retrievers produces a polars DataFrame sorted by MRR."""
    rag = RAGDiagnostics()

    def good(q: str, k: int) -> list:  # type: ignore[type-arg]
        return [("doc_42", "correct", 0.9), ("doc_99", "wrong", 0.1)][:k]

    def bad(q: str, k: int) -> list:  # type: ignore[type-arg]
        return [("doc_99", "wrong", 0.9), ("doc_42", "correct", 0.1)][:k]

    eval_set = [{"query": "q", "relevant_ids": ["doc_42"]}]
    board = rag.compare_retrievers(
        retrievers={"good": good, "bad": bad},
        eval_set=eval_set,
        k=2,
    )
    assert board.height == 2
    # "good" retriever at position 1 → MRR=1.0, outranks "bad" at MRR=0.5.
    assert board["retriever"][0] == "good"
    assert board["mrr"][0] == 1.0
    assert rag.leaderboard_df().height == 2


# ---------------------------------------------------------------------------
# Report — empty state + populated state
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_report_on_empty_session_returns_unknown_findings() -> None:
    """A fresh session's report is well-formed with UNKNOWN severities."""
    rag = RAGDiagnostics()
    report = rag.report()
    assert report["evaluations"] == 0
    assert report["retriever_comparisons"] == 0
    assert report["retrieval"]["severity"] == "UNKNOWN"
    assert report["faithfulness"]["severity"] == "UNKNOWN"
    assert report["context_utilisation"]["severity"] == "UNKNOWN"
    assert report["retriever_leaderboard"]["severity"] == "UNKNOWN"
    assert report["run_id"] == rag.run_id


@pytest.mark.unit
def test_report_severity_critical_on_low_recall(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CRITICAL severity when recall@k < 0.3."""
    monkeypatch.setattr(rag_mod, "_try_ragas_evaluate", lambda **_: None)
    rag = RAGDiagnostics()
    # All retrieved IDs miss ground truth → recall = 0.
    for i in range(3):
        rag.evaluate(
            queries=[f"q{i}"],
            retrieved_contexts=[[f"c{i}"]],
            answers=[f"a{i}"],
            retrieved_ids=[[f"wrong_{i}"]],
            ground_truth_ids=[[f"right_{i}"]],
        )
    report = rag.report()
    assert report["retrieval"]["severity"] == "CRITICAL"
    assert "Recall@k severely low" in report["retrieval"]["message"]


# ---------------------------------------------------------------------------
# metrics_df + leaderboard_df — empty-state schema contract
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_empty_metrics_df_returns_zero_height_with_schema() -> None:
    """metrics_df on a fresh session returns empty polars DataFrame with schema."""
    rag = RAGDiagnostics()
    df = rag.metrics_df()
    assert df.height == 0
    assert set(df.columns) == {
        "query_preview",
        "recall_at_k",
        "precision_at_k",
        "context_utilisation",
        "faithfulness",
        "k",
        "mode",
    }


@pytest.mark.unit
def test_empty_leaderboard_df_returns_zero_height_with_schema() -> None:
    """leaderboard_df on a fresh session returns empty polars DataFrame."""
    rag = RAGDiagnostics()
    df = rag.leaderboard_df()
    assert df.height == 0
    assert set(df.columns) == {
        "retriever",
        "recall_at_k",
        "precision_at_k",
        "mrr",
        "ndcg_at_k",
        "n",
        "k",
    }


# ---------------------------------------------------------------------------
# Plotly extras-gating — plot_*() raises ImportError naming [dl]
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_plot_recall_curve_raises_loudly_when_plotly_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """plot_recall_curve raises ImportError naming [dl] when plotly absent."""
    rag = RAGDiagnostics()

    def _no_plotly() -> None:
        raise ImportError(
            "Plotting methods require plotly. Install the deep-learning extras: "
            "pip install kailash-ml[dl]"
        )

    monkeypatch.setattr(rag_mod, "_require_plotly", _no_plotly)
    with pytest.raises(ImportError, match=r"kailash-ml\[dl\]"):
        rag.plot_recall_curve()


@pytest.mark.unit
def test_plot_faithfulness_scatter_raises_loudly_when_plotly_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rag = RAGDiagnostics()
    monkeypatch.setattr(
        rag_mod,
        "_require_plotly",
        lambda: (_ for _ in ()).throw(
            ImportError(
                "Plotting methods require plotly. Install the deep-learning "
                "extras: pip install kailash-ml[dl]"
            )
        ),
    )
    with pytest.raises(ImportError, match=r"kailash-ml\[dl\]"):
        rag.plot_faithfulness_scatter()


@pytest.mark.unit
def test_plot_retriever_leaderboard_raises_loudly_when_plotly_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rag = RAGDiagnostics()
    monkeypatch.setattr(
        rag_mod,
        "_require_plotly",
        lambda: (_ for _ in ()).throw(
            ImportError(
                "Plotting methods require plotly. Install the deep-learning "
                "extras: pip install kailash-ml[dl]"
            )
        ),
    )
    with pytest.raises(ImportError, match=r"kailash-ml\[dl\]"):
        rag.plot_retriever_leaderboard()


@pytest.mark.unit
def test_plot_rag_dashboard_raises_loudly_when_plotly_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rag = RAGDiagnostics()
    monkeypatch.setattr(
        rag_mod,
        "_require_plotly",
        lambda: (_ for _ in ()).throw(
            ImportError(
                "Plotting methods require plotly. Install the deep-learning "
                "extras: pip install kailash-ml[dl]"
            )
        ),
    )
    with pytest.raises(ImportError, match=r"kailash-ml\[dl\]"):
        rag.plot_rag_dashboard()


# ---------------------------------------------------------------------------
# ragas / trulens extras-gating — public methods raise ImportError naming [rag]
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_ragas_scores_raises_when_ragas_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ragas_scores raises ImportError naming [rag] when ragas is absent."""
    monkeypatch.setattr(rag_mod, "_try_ragas_evaluate", lambda **_: None)
    rag = RAGDiagnostics()
    with pytest.raises(ImportError, match=r"kailash-ml\[rag\]"):
        rag.ragas_scores(
            queries=["q"],
            retrieved_contexts=[["c"]],
            answers=["a"],
        )


@pytest.mark.unit
def test_trulens_scores_raises_when_trulens_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """trulens_scores raises ImportError naming [rag] when trulens is absent."""
    monkeypatch.setattr(rag_mod, "_try_trulens_evaluate", lambda **_: None)
    rag = RAGDiagnostics()
    with pytest.raises(ImportError, match=r"kailash-ml\[rag\]"):
        rag.trulens_scores(
            queries=["q"],
            retrieved_contexts=[["c"]],
            answers=["a"],
        )


@pytest.mark.unit
def test_trulens_scores_rejects_mismatched_lengths() -> None:
    """trulens_scores validates input lengths before dispatching."""
    rag = RAGDiagnostics()
    with pytest.raises(ValueError, match="same length"):
        rag.trulens_scores(
            queries=["q1", "q2"],
            retrieved_contexts=[["c"]],
            answers=["a1", "a2"],
        )


# ---------------------------------------------------------------------------
# Context utilisation heuristic — deterministic
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_context_utilisation_fully_grounded_answer() -> None:
    """Utilisation = 1.0 when every meaningful answer token is in context."""
    rag = RAGDiagnostics()
    answer = "photosynthesis converts light energy"
    contexts = ["photosynthesis converts light into chemical energy"]
    util = rag.context_utilisation(answer=answer, contexts=contexts)
    assert util == 1.0


@pytest.mark.unit
def test_context_utilisation_ungrounded_answer() -> None:
    """Utilisation < 1.0 when answer contains tokens absent from context."""
    rag = RAGDiagnostics()
    answer = "quantum entanglement mystical phenomenon"
    contexts = ["photosynthesis converts light"]
    util = rag.context_utilisation(answer=answer, contexts=contexts)
    assert util < 1.0


@pytest.mark.unit
def test_context_utilisation_empty_answer() -> None:
    """Utilisation = 0.0 for an empty answer (no tokens to score)."""
    rag = RAGDiagnostics()
    assert rag.context_utilisation(answer="", contexts=["anything"]) == 0.0


# ---------------------------------------------------------------------------
# JudgeCallable integration path — mocked judge
# ---------------------------------------------------------------------------


class _FakeJudge:
    """Minimal JudgeCallable that returns a deterministic score.

    Conforms to kailash.diagnostics.protocols.JudgeCallable at runtime.
    """

    def __init__(self, score: float) -> None:
        self._score = score
        self.calls: list[JudgeInput] = []

    async def __call__(self, judge_input: JudgeInput) -> JudgeResult:
        self.calls.append(judge_input)
        return JudgeResult(
            score=self._score,
            winner=None,
            reasoning="fake judge",
            judge_model="fake-judge-v1",
            cost_microdollars=0,
            prompt_tokens=0,
            completion_tokens=0,
        )


@pytest.mark.unit
def test_evaluate_routes_through_judge_callable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With a judge configured, evaluate dispatches through JudgeCallable."""
    monkeypatch.setattr(rag_mod, "_try_ragas_evaluate", lambda **_: None)
    judge = _FakeJudge(score=0.85)
    rag = RAGDiagnostics(judge=judge)
    df = rag.evaluate(
        queries=["What is X?"],
        retrieved_contexts=[["X is a thing."]],
        answers=["X is a thing."],
        retrieved_ids=[["doc_42"]],
        ground_truth_ids=[["doc_42"]],
    )
    assert df["faithfulness"][0] == 0.85
    assert df["mode"][0] == "judge"
    assert len(judge.calls) == 1


@pytest.mark.unit
def test_evaluate_falls_back_to_heuristic_on_judge_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Judge exceptions fall back to deterministic heuristic with mode=judge_error."""
    monkeypatch.setattr(rag_mod, "_try_ragas_evaluate", lambda **_: None)

    class _BrokenJudge:
        async def __call__(self, judge_input: JudgeInput) -> JudgeResult:
            raise RuntimeError("judge backend exploded")

    rag = RAGDiagnostics(judge=_BrokenJudge())
    df = rag.evaluate(
        queries=["q"],
        retrieved_contexts=[["c"]],
        answers=["answer tokens"],
        retrieved_ids=[["doc_1"]],
        ground_truth_ids=[["doc_1"]],
    )
    assert df["mode"][0] == "judge_error"
    # Heuristic fallback produces a numeric score in [0, 1].
    score = float(df["faithfulness"][0])
    assert 0.0 <= score <= 1.0

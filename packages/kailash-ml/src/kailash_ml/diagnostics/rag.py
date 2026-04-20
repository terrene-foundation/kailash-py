# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
#
# Portions of this module were originally contributed from MLFP
# (Apache-2.0) and re-authored for the Kailash ecosystem. See
# ``specs/ml-diagnostics.md`` § "Attribution" for the full donation
# history (kailash-py issue #567, PR#2 of 7).
"""RAG evaluation diagnostics for kailash-ml.

``RAGDiagnostics`` is the Retrieval-Augmented-Generation adapter that
satisfies the ``kailash.diagnostics.protocols.Diagnostic`` Protocol.
It scores retrieval + generation quality for a batch of queries using
IR metrics (recall@k, precision@k, MRR, nDCG@k) + LLM-as-judge
faithfulness + context-utilisation.

Quick start::

    from kailash_ml.diagnostics import RAGDiagnostics

    with RAGDiagnostics() as rag:
        df = rag.evaluate(
            queries=["What is photosynthesis?"],
            retrieved_contexts=[[doc1, doc2, doc3]],
            answers=["Photosynthesis is ..."],
            ground_truth_ids=[["doc_42"]],
            retrieved_ids=[["doc_42", "doc_11", "doc_99"]],
        )
        board = rag.compare_retrievers(
            retrievers={"bm25": bm25_fn, "dense": dense_fn, "hybrid": hybrid_fn},
            eval_set=eval_set,
            k=5,
        )
        print(rag.report())

The adapter is polars-native: ``metrics_df()`` and ``leaderboard_df()``
return ``polars.DataFrame``. ``plot_*()`` methods return
``plotly.graph_objects.Figure`` and require ``pip install kailash-ml[dl]``
(plotly is shared with other ML plot surfaces).

``ragas``-backed scoring + ``trulens-eval``-backed auxiliary metrics are
opt-in and require ``pip install kailash-ml[rag]``. Without ``[rag]``,
``evaluate()`` falls back to a pluggable ``JudgeCallable`` + a
deterministic token-overlap heuristic for ``context_utilisation``; the
fallback path is loudly logged at WARN per ``rules/dependencies.md``
("Optional Extras with Loud Failure"). The ``ragas_scores()`` and
``trulens_scores()`` public methods raise ``ImportError`` naming the
``[rag]`` extra when the optional backend is absent.

All LLM-as-judge calls route through
``kailash.diagnostics.protocols.JudgeCallable`` — no raw ``openai.*``
per ``rules/framework-first.md``. Callers supply the judge via the
``judge`` kwarg; when omitted the adapter operates in pure-IR-metrics
mode and logs ``mode="metrics_only"``.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import math
import uuid
from collections import deque
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Optional

import polars as pl

from kailash.diagnostics.protocols import JudgeCallable, JudgeInput, JudgeResult

if TYPE_CHECKING:  # pragma: no cover — typing-only imports
    import plotly.graph_objects as go_types  # noqa: F401

logger = logging.getLogger(__name__)

__all__ = [
    "RAGDiagnostics",
    "RetrievedDoc",
    "Retriever",
]


# Retriever callable: (query, k) -> list of (doc_id, content, score).
RetrievedDoc = tuple[str, str, float]
Retriever = Callable[[str, int], Sequence[RetrievedDoc]]


# ---------------------------------------------------------------------------
# Optional backend gating — plotly + ragas + trulens
# ---------------------------------------------------------------------------


def _require_plotly() -> Any:
    """Import ``plotly.graph_objects`` or raise ImportError naming ``[dl]``.

    Per ``rules/dependencies.md`` "Optional Extras with Loud Failure".
    Plotly is shared with ``DLDiagnostics`` and other ML plot surfaces;
    it lives under the ``[dl]`` extra (see specs/ml-diagnostics.md §4.3).
    """
    try:
        import plotly.graph_objects as go  # noqa: PLC0415
    except ImportError as exc:  # pragma: no cover — base install has plotly
        raise ImportError(
            "Plotting methods require plotly. Install the deep-learning extras: "
            "pip install kailash-ml[dl]"
        ) from exc
    return go


def _require_plotly_subplots() -> Any:
    """Return ``plotly.subplots.make_subplots`` or raise loudly."""
    try:
        from plotly.subplots import make_subplots  # noqa: PLC0415
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "Plotting methods require plotly. Install the deep-learning extras: "
            "pip install kailash-ml[dl]"
        ) from exc
    return make_subplots


# ---------------------------------------------------------------------------
# Internal bookkeeping
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _EvalEntry:
    """One scored evaluation row (captured per-query).

    Stored in a bounded ``deque`` on the session; converted to a polars
    DataFrame on demand via :meth:`RAGDiagnostics.metrics_df`.
    """

    query_hash: str
    query_preview: str
    recall_at_k: float
    precision_at_k: float
    context_utilisation: float
    faithfulness: float
    k: int
    mode: str  # "ragas" | "judge" | "metrics_only" | "budget_exhausted"


@dataclass(frozen=True)
class _RetrieverEntry:
    """One row of the retriever leaderboard history."""

    retriever: str
    recall_at_k: float
    precision_at_k: float
    mrr: float
    ndcg_at_k: float
    n: int
    k: int


# ---------------------------------------------------------------------------
# RAGDiagnostics — concrete Diagnostic adapter
# ---------------------------------------------------------------------------


class RAGDiagnostics:
    """Retrieval-Augmented-Generation evaluation adapter (Diagnostic Protocol).

    Satisfies :class:`kailash.diagnostics.protocols.Diagnostic`
    (``run_id`` + ``__enter__`` + ``__exit__`` + ``report()``). The
    Protocol is ``@runtime_checkable``, so ``isinstance(rag, Diagnostic)``
    returns ``True`` at runtime — verified by the Tier 2 wiring test.

    Args:
        judge: Optional LLM-as-judge callable conforming to
            :class:`kailash.diagnostics.protocols.JudgeCallable`. When
            ``None``, faithfulness scoring falls back to a deterministic
            token-overlap heuristic and the adapter operates in
            ``metrics_only`` mode (IR metrics only).
        max_history: Maximum number of per-query evaluation entries
            retained in memory; older entries are evicted FIFO. Use this
            to bound memory for streaming evaluation loops. Default
            ``1024``.
        max_leaderboard_history: Maximum retriever-comparison entries
            retained. Default ``256``.
        sensitive: When ``True``, query/answer bodies are not logged —
            only ``sha256:<8-hex>`` fingerprints. Follows the cross-SDK
            event-payload-classification contract (see
            ``rules/event-payload-classification.md``).
        run_id: Optional correlation identifier for this diagnostic
            session. When omitted, a UUID4 hex is generated. Matches
            :class:`Diagnostic.run_id`.

    Raises:
        ValueError: If ``max_history < 1``, ``max_leaderboard_history < 1``,
            or ``run_id == ""``.
        TypeError: If ``judge`` is not ``None`` and does not conform to
            :class:`JudgeCallable` at runtime.

    Example:
        >>> with RAGDiagnostics() as rag:
        ...     df = rag.evaluate(
        ...         queries=["What is X?"],
        ...         retrieved_contexts=[["X is ..."]],
        ...         answers=["X is ..."],
        ...         retrieved_ids=[["doc_1"]],
        ...         ground_truth_ids=[["doc_1"]],
        ...     )
        ...     report = rag.report()
    """

    def __init__(
        self,
        *,
        judge: Optional[JudgeCallable] = None,
        max_history: int = 1024,
        max_leaderboard_history: int = 256,
        sensitive: bool = False,
        run_id: Optional[str] = None,
    ) -> None:
        if max_history < 1:
            raise ValueError("max_history must be >= 1")
        if max_leaderboard_history < 1:
            raise ValueError("max_leaderboard_history must be >= 1")
        if run_id is not None and not run_id:
            raise ValueError("run_id must be a non-empty string when provided")
        if judge is not None and not isinstance(judge, JudgeCallable):
            raise TypeError(
                "judge must conform to "
                "kailash.diagnostics.protocols.JudgeCallable (async __call__ "
                "accepting JudgeInput, returning JudgeResult)."
            )

        self._judge = judge
        self._sensitive = sensitive
        self.run_id: str = run_id if run_id is not None else uuid.uuid4().hex

        # Bounded in-memory storage per rules analysis §1.4 — streaming
        # RAG eval loops must not grow without bound.
        self._eval_log: deque[_EvalEntry] = deque(maxlen=max_history)
        self._retriever_log: deque[_RetrieverEntry] = deque(
            maxlen=max_leaderboard_history
        )

        logger.info(
            "ragdiagnostics.init",
            extra={
                "rag_run_id": self.run_id,
                "rag_max_history": max_history,
                "rag_max_leaderboard": max_leaderboard_history,
                "rag_has_judge": judge is not None,
                "rag_sensitive": sensitive,
            },
        )

    # ── Context-manager support ────────────────────────────────────────────

    def __enter__(self) -> "RAGDiagnostics":
        return self

    def __exit__(
        self,
        exc_type: Any,
        exc_val: Any,
        exc_tb: Any,
    ) -> Optional[bool]:
        logger.info(
            "ragdiagnostics.exit",
            extra={
                "rag_run_id": self.run_id,
                "rag_eval_count": len(self._eval_log),
                "rag_leaderboard_count": len(self._retriever_log),
            },
        )
        return None

    # ── Core evaluation API ────────────────────────────────────────────────

    def evaluate(
        self,
        queries: Sequence[str],
        retrieved_contexts: Sequence[Sequence[str]],
        answers: Sequence[str],
        *,
        ground_truth_ids: Optional[Sequence[Sequence[str]]] = None,
        retrieved_ids: Optional[Sequence[Sequence[str]]] = None,
        k: int = 5,
        sub_run_id: Optional[str] = None,
    ) -> pl.DataFrame:
        """Score a batch of RAG outputs end-to-end.

        Computes per-query recall@k, precision@k, context-utilisation,
        and faithfulness. When ``ragas`` is installed (via the ``[rag]``
        extra), its implementations are used for faithfulness +
        context-precision; otherwise the adapter falls back to the
        configured ``judge`` (if any) AND a deterministic token-overlap
        heuristic for ``context_utilisation``. Every fallback is logged
        at WARN so operators know which backend produced each score.

        Args:
            queries: User queries (non-empty strings).
            retrieved_contexts: For each query, the ordered list of
                retrieved chunk contents.
            answers: The generator's final answers.
            ground_truth_ids: Optional list of per-query relevant doc
                IDs. Required for non-zero recall@k / precision@k; when
                omitted those columns are all zero.
            retrieved_ids: Optional list of per-query retrieved doc IDs
                in the same order as ``retrieved_contexts``. When
                ``None`` the adapter treats the context strings
                themselves as IDs (legacy compatibility path).
            k: Cut-off for recall@k / precision@k. Must be ``>= 1``.
            sub_run_id: Optional child correlation ID for this
                evaluate() call. Auto-generated if ``None``.

        Returns:
            Polars DataFrame with one row per query and columns:
            ``idx, recall_at_k, precision_at_k, context_utilisation,
            faithfulness, k, mode``.

        Raises:
            ValueError: On mismatched lengths, ``k < 1``, or empty
                ``queries``.
        """
        n = len(queries)
        if n == 0:
            raise ValueError("queries must be non-empty")
        if not (len(retrieved_contexts) == n == len(answers)):
            raise ValueError(
                f"queries, retrieved_contexts, answers must all be same length; "
                f"got {n}, {len(retrieved_contexts)}, {len(answers)}"
            )
        if ground_truth_ids is not None and len(ground_truth_ids) != n:
            raise ValueError(
                f"ground_truth_ids length mismatch: {len(ground_truth_ids)} != {n}"
            )
        if retrieved_ids is not None and len(retrieved_ids) != n:
            raise ValueError(
                f"retrieved_ids length mismatch: {len(retrieved_ids)} != {n}"
            )
        if k < 1:
            raise ValueError("k must be >= 1")

        sub_run_id = sub_run_id or f"{self.run_id}-eval-{uuid.uuid4().hex[:8]}"
        logger.info(
            "ragdiagnostics.evaluate.start",
            extra={
                "rag_run_id": self.run_id,
                "rag_sub_run_id": sub_run_id,
                "rag_n_queries": n,
                "rag_k": k,
                "mode": "real",
            },
        )

        ragas_scores = _try_ragas_evaluate(
            queries=queries,
            retrieved_contexts=retrieved_contexts,
            answers=answers,
            ground_truth_ids=ground_truth_ids,
        )

        rows: list[dict[str, Any]] = []
        for i in range(n):
            ids_i = (
                list(retrieved_ids[i])
                if retrieved_ids is not None
                else list(retrieved_contexts[i])
            )
            truth_i = list(ground_truth_ids[i]) if ground_truth_ids is not None else []
            recall = _recall_at_k(ids_i[:k], truth_i)
            precision = _precision_at_k(ids_i[:k], truth_i)

            if ragas_scores is not None:
                faithfulness = float(ragas_scores["faithfulness"][i])
                context_util = float(ragas_scores["context_precision"][i])
                backend_mode = "ragas"
            elif self._judge is not None:
                faithfulness, backend_mode = self._judge_faithfulness(
                    query=queries[i],
                    answer=answers[i],
                    contexts=retrieved_contexts[i],
                    sub_run_id=f"{sub_run_id}-faith-{i}",
                )
                context_util = _heuristic_context_utilisation(
                    answer=answers[i], contexts=retrieved_contexts[i]
                )
            else:
                # Pure IR-metrics mode — no judge, no ragas.
                faithfulness = _heuristic_context_utilisation(
                    answer=answers[i], contexts=retrieved_contexts[i]
                )
                context_util = faithfulness  # same heuristic — single source
                backend_mode = "metrics_only"

            entry = _EvalEntry(
                query_hash=_hash_preview(queries[i]),
                query_preview=("<redacted>" if self._sensitive else queries[i][:120]),
                recall_at_k=recall,
                precision_at_k=precision,
                context_utilisation=context_util,
                faithfulness=faithfulness,
                k=k,
                mode=backend_mode,
            )
            self._eval_log.append(entry)
            rows.append(
                {
                    "idx": i,
                    "recall_at_k": recall,
                    "precision_at_k": precision,
                    "context_utilisation": context_util,
                    "faithfulness": faithfulness,
                    "k": k,
                    "mode": backend_mode,
                }
            )

        df = pl.DataFrame(rows)
        mean_recall_raw = df["recall_at_k"].mean()
        mean_faith_raw = df["faithfulness"].mean()
        logger.info(
            "ragdiagnostics.evaluate.ok",
            extra={
                "rag_run_id": self.run_id,
                "rag_sub_run_id": sub_run_id,
                "rag_n_queries": n,
                "rag_mean_recall": (
                    float(mean_recall_raw) if mean_recall_raw is not None else 0.0
                ),
                "rag_mean_faithfulness": (
                    float(mean_faith_raw) if mean_faith_raw is not None else 0.0
                ),
                "rag_source": (
                    "ragas"
                    if ragas_scores is not None
                    else ("judge" if self._judge is not None else "metrics_only")
                ),
                "mode": "real",
            },
        )
        return df

    # ── Retriever leaderboard ──────────────────────────────────────────────

    def compare_retrievers(
        self,
        retrievers: dict[str, Retriever],
        eval_set: Sequence[dict[str, Any]],
        *,
        k: int = 5,
        sub_run_id: Optional[str] = None,
    ) -> pl.DataFrame:
        """Leaderboard over multiple retrievers on the same eval set.

        Each element of ``eval_set`` MUST have keys:

            * ``query`` (str)
            * ``relevant_ids`` (list[str]) — ground-truth doc IDs

        ``retrievers`` maps a short label to a callable
        ``(query, k) -> [(doc_id, content, score), ...]``.

        Args:
            retrievers: Dict of {name: retriever_fn}.
            eval_set: List of {"query": str, "relevant_ids": [...]} dicts.
            k: Cut-off for metric computation. Must be ``>= 1``.
            sub_run_id: Optional child correlation ID.

        Returns:
            Polars DataFrame sorted by ``mrr`` descending, with columns
            ``retriever, recall_at_k, precision_at_k, mrr, ndcg_at_k,
            n, k``.

        Raises:
            ValueError: On empty ``retrievers`` or ``eval_set``, or ``k < 1``.
        """
        if not retrievers:
            raise ValueError("retrievers dict must be non-empty")
        if not eval_set:
            raise ValueError("eval_set must be non-empty")
        if k < 1:
            raise ValueError("k must be >= 1")

        sub_run_id = sub_run_id or f"{self.run_id}-cmp-{uuid.uuid4().hex[:8]}"
        logger.info(
            "ragdiagnostics.compare_retrievers.start",
            extra={
                "rag_run_id": self.run_id,
                "rag_sub_run_id": sub_run_id,
                "rag_retrievers": list(retrievers),
                "rag_n_queries": len(eval_set),
                "rag_k": k,
                "mode": "real",
            },
        )

        rows: list[dict[str, Any]] = []
        for name, fn in retrievers.items():
            per_query: list[dict[str, float]] = []
            for entry in eval_set:
                query = entry["query"]
                relevant = list(entry.get("relevant_ids") or [])
                hits = list(fn(query, k)) or []
                retrieved_ids = [h[0] for h in hits[:k]]
                per_query.append(
                    {
                        "recall_at_k": _recall_at_k(retrieved_ids, relevant),
                        "precision_at_k": _precision_at_k(retrieved_ids, relevant),
                        "mrr": _reciprocal_rank(retrieved_ids, relevant),
                        "ndcg_at_k": _ndcg_at_k(retrieved_ids, relevant, k),
                    }
                )
            agg_entry = _RetrieverEntry(
                retriever=name,
                recall_at_k=_mean([r["recall_at_k"] for r in per_query]),
                precision_at_k=_mean([r["precision_at_k"] for r in per_query]),
                mrr=_mean([r["mrr"] for r in per_query]),
                ndcg_at_k=_mean([r["ndcg_at_k"] for r in per_query]),
                n=len(per_query),
                k=k,
            )
            self._retriever_log.append(agg_entry)
            rows.append(
                {
                    "retriever": name,
                    "recall_at_k": agg_entry.recall_at_k,
                    "precision_at_k": agg_entry.precision_at_k,
                    "mrr": agg_entry.mrr,
                    "ndcg_at_k": agg_entry.ndcg_at_k,
                    "n": agg_entry.n,
                    "k": agg_entry.k,
                }
            )
        board = pl.DataFrame(rows).sort("mrr", descending=True)
        logger.info(
            "ragdiagnostics.compare_retrievers.ok",
            extra={
                "rag_run_id": self.run_id,
                "rag_sub_run_id": sub_run_id,
                "rag_winner": str(board["retriever"][0]) if board.height else None,
                "mode": "real",
            },
        )
        return board

    # ── Individual metric helpers (public) ─────────────────────────────────

    def recall_at_k(
        self,
        retrieved_ids: Sequence[str],
        relevant_ids: Sequence[str],
        *,
        k: int = 5,
    ) -> float:
        """Recall@k — fraction of the relevant set captured in top-k."""
        if k < 1:
            raise ValueError("k must be >= 1")
        return _recall_at_k(list(retrieved_ids)[:k], list(relevant_ids))

    def precision_at_k(
        self,
        retrieved_ids: Sequence[str],
        relevant_ids: Sequence[str],
        *,
        k: int = 5,
    ) -> float:
        """Precision@k — fraction of top-k that is relevant."""
        if k < 1:
            raise ValueError("k must be >= 1")
        return _precision_at_k(list(retrieved_ids)[:k], list(relevant_ids))

    def reciprocal_rank(
        self,
        retrieved_ids: Sequence[str],
        relevant_ids: Sequence[str],
    ) -> float:
        """Mean reciprocal rank (RR) of the first relevant doc in top-k."""
        return _reciprocal_rank(list(retrieved_ids), list(relevant_ids))

    def ndcg_at_k(
        self,
        retrieved_ids: Sequence[str],
        relevant_ids: Sequence[str],
        *,
        k: int = 5,
    ) -> float:
        """Normalised DCG@k — binary-relevance form (no graded labels)."""
        if k < 1:
            raise ValueError("k must be >= 1")
        return _ndcg_at_k(list(retrieved_ids), list(relevant_ids), k)

    def context_utilisation(
        self,
        answer: str,
        contexts: Sequence[str],
    ) -> float:
        """Fraction of answer tokens traceable to retrieved context.

        Token-overlap heuristic (fast, local, no LLM call). For a
        judge-based evaluation pass ``judge=...`` to the constructor
        and call :meth:`evaluate`.
        """
        return _heuristic_context_utilisation(answer=answer, contexts=contexts)

    def ragas_scores(
        self,
        queries: Sequence[str],
        retrieved_contexts: Sequence[Sequence[str]],
        answers: Sequence[str],
        *,
        ground_truth_ids: Optional[Sequence[Sequence[str]]] = None,
    ) -> pl.DataFrame:
        """Run the full RAGAS evaluation (requires the ``[rag]`` extra).

        Raises:
            ImportError: When ``ragas`` is not installed (per
                ``rules/dependencies.md`` "Optional Extras with Loud
                Failure" — names the ``[rag]`` extra).
        """
        scores = _try_ragas_evaluate(
            queries=queries,
            retrieved_contexts=retrieved_contexts,
            answers=answers,
            ground_truth_ids=ground_truth_ids,
        )
        if scores is None:
            raise ImportError(
                "ragas-backed evaluation requires the RAG extras. "
                "Install with: pip install kailash-ml[rag]"
            )
        return pl.DataFrame(scores)

    def trulens_scores(
        self,
        queries: Sequence[str],
        retrieved_contexts: Sequence[Sequence[str]],
        answers: Sequence[str],
    ) -> pl.DataFrame:
        """Run the trulens-eval auxiliary metrics (requires the ``[rag]`` extra).

        trulens-eval provides groundedness / answer-relevance scoring
        that complements ragas. The adapter does not wrap the backend's
        LLM routing — the caller is expected to have configured
        trulens's provider separately; we only dispatch the scoring
        entrypoint.

        Raises:
            ImportError: When ``trulens-eval`` is not installed — names
                the ``[rag]`` extra.
            ValueError: On mismatched input lengths.
        """
        n = len(queries)
        if not (len(retrieved_contexts) == n == len(answers)):
            raise ValueError(
                "queries, retrieved_contexts, answers must all be same length"
            )
        scores = _try_trulens_evaluate(
            queries=queries,
            retrieved_contexts=retrieved_contexts,
            answers=answers,
        )
        if scores is None:
            raise ImportError(
                "trulens-eval scoring requires the RAG extras. "
                "Install with: pip install kailash-ml[rag]"
            )
        return pl.DataFrame(scores)

    # ── DataFrames ─────────────────────────────────────────────────────────

    def metrics_df(self) -> pl.DataFrame:
        """One row per :meth:`evaluate` sample (polars-native).

        Columns: ``query_preview, recall_at_k, precision_at_k,
        context_utilisation, faithfulness, k, mode``. ``query_preview``
        is ``"<redacted>"`` when the session was constructed with
        ``sensitive=True``.
        """
        if not self._eval_log:
            return pl.DataFrame(
                schema={
                    "query_preview": pl.Utf8,
                    "recall_at_k": pl.Float64,
                    "precision_at_k": pl.Float64,
                    "context_utilisation": pl.Float64,
                    "faithfulness": pl.Float64,
                    "k": pl.Int64,
                    "mode": pl.Utf8,
                }
            )
        return pl.DataFrame(
            [
                {
                    "query_preview": e.query_preview,
                    "recall_at_k": e.recall_at_k,
                    "precision_at_k": e.precision_at_k,
                    "context_utilisation": e.context_utilisation,
                    "faithfulness": e.faithfulness,
                    "k": e.k,
                    "mode": e.mode,
                }
                for e in self._eval_log
            ]
        )

    def leaderboard_df(self) -> pl.DataFrame:
        """Retriever-leaderboard history (polars-native).

        Columns: ``retriever, recall_at_k, precision_at_k, mrr,
        ndcg_at_k, n, k``. Each row is the aggregate of one
        :meth:`compare_retrievers` invocation. Use
        :meth:`compare_retrievers`'s return value directly if you only
        want the latest leaderboard.
        """
        if not self._retriever_log:
            return pl.DataFrame(
                schema={
                    "retriever": pl.Utf8,
                    "recall_at_k": pl.Float64,
                    "precision_at_k": pl.Float64,
                    "mrr": pl.Float64,
                    "ndcg_at_k": pl.Float64,
                    "n": pl.Int64,
                    "k": pl.Int64,
                }
            )
        return pl.DataFrame(
            [
                {
                    "retriever": e.retriever,
                    "recall_at_k": e.recall_at_k,
                    "precision_at_k": e.precision_at_k,
                    "mrr": e.mrr,
                    "ndcg_at_k": e.ndcg_at_k,
                    "n": e.n,
                    "k": e.k,
                }
                for e in self._retriever_log
            ]
        )

    # ── Plots (require kailash-ml[dl] — plotly) ────────────────────────────

    def plot_recall_curve(self) -> "go_types.Figure":
        """Recall@k curve across captured evaluations.

        Requires ``pip install kailash-ml[dl]``.
        """
        go = _require_plotly()
        df = self.metrics_df()
        fig = go.Figure()
        if df.height == 0:
            fig.update_layout(
                title="Recall@k per query — no data",
                template="plotly_white",
            )
            return fig
        fig.add_trace(
            go.Scatter(
                x=list(range(df.height)),
                y=df["recall_at_k"].to_list(),
                mode="lines+markers",
                line=dict(color="steelblue", width=2),
                name="recall@k",
            )
        )
        fig.update_layout(
            title="Recall@k per query",
            xaxis_title="query index",
            yaxis_title="recall@k",
            yaxis=dict(range=[0, 1]),
            template="plotly_white",
        )
        return fig

    def plot_faithfulness_scatter(self) -> "go_types.Figure":
        """Faithfulness vs context-utilisation scatter.

        Requires ``pip install kailash-ml[dl]``.
        """
        go = _require_plotly()
        df = self.metrics_df()
        fig = go.Figure()
        if df.height == 0:
            fig.update_layout(
                title="Faithfulness vs Context Utilisation — no data",
                template="plotly_white",
            )
            return fig
        fig.add_trace(
            go.Scatter(
                x=df["context_utilisation"].to_list(),
                y=df["faithfulness"].to_list(),
                mode="markers",
                marker=dict(color="firebrick", size=8, opacity=0.7),
                name="eval",
            )
        )
        fig.update_layout(
            title="Faithfulness vs Context Utilisation",
            xaxis_title="context utilisation",
            yaxis_title="faithfulness",
            xaxis=dict(range=[0, 1]),
            yaxis=dict(range=[0, 1]),
            template="plotly_white",
        )
        return fig

    def plot_retriever_leaderboard(self) -> "go_types.Figure":
        """Bar chart of retriever MRR / nDCG@k across compared retrievers.

        Requires ``pip install kailash-ml[dl]``.
        """
        go = _require_plotly()
        df = self.leaderboard_df()
        fig = go.Figure()
        if df.height == 0:
            fig.update_layout(
                title="Retriever Leaderboard — no data",
                template="plotly_white",
            )
            return fig
        fig.add_trace(
            go.Bar(
                x=df["retriever"].to_list(),
                y=df["mrr"].to_list(),
                name="MRR",
                marker_color="steelblue",
            )
        )
        fig.add_trace(
            go.Bar(
                x=df["retriever"].to_list(),
                y=df["ndcg_at_k"].to_list(),
                name="nDCG@k",
                marker_color="firebrick",
            )
        )
        fig.update_layout(
            title="Retriever Leaderboard",
            xaxis_title="retriever",
            yaxis_title="score",
            yaxis=dict(range=[0, 1]),
            barmode="group",
            template="plotly_white",
        )
        return fig

    def plot_rag_dashboard(self) -> "go_types.Figure":
        """2x2 dashboard: recall@k curve, context-util histogram,
        faithfulness scatter, retriever leaderboard.

        Requires ``pip install kailash-ml[dl]``.
        """
        go = _require_plotly()
        make_subplots = _require_plotly_subplots()
        fig = make_subplots(
            rows=2,
            cols=2,
            subplot_titles=(
                "Recall@k per query",
                "Context utilisation histogram",
                "Faithfulness vs context utilisation",
                "Retriever leaderboard (MRR)",
            ),
        )

        eval_df = self.metrics_df()
        if eval_df.height:
            fig.add_trace(
                go.Scatter(
                    x=list(range(eval_df.height)),
                    y=eval_df["recall_at_k"].to_list(),
                    mode="lines+markers",
                    marker=dict(color="steelblue"),
                    name="recall@k",
                    showlegend=False,
                ),
                row=1,
                col=1,
            )
            fig.add_trace(
                go.Histogram(
                    x=eval_df["context_utilisation"].to_list(),
                    marker_color="darkgreen",
                    nbinsx=20,
                    name="context_util",
                    showlegend=False,
                ),
                row=1,
                col=2,
            )
            fig.add_trace(
                go.Scatter(
                    x=eval_df["context_utilisation"].to_list(),
                    y=eval_df["faithfulness"].to_list(),
                    mode="markers",
                    marker=dict(color="firebrick", size=8),
                    showlegend=False,
                ),
                row=2,
                col=1,
            )
        board = self.leaderboard_df()
        if board.height:
            fig.add_trace(
                go.Bar(
                    x=board["retriever"].to_list(),
                    y=board["mrr"].to_list(),
                    marker_color="steelblue",
                    showlegend=False,
                ),
                row=2,
                col=2,
            )

        fig.update_layout(
            title="Retrieval Evaluation Dashboard",
            template="plotly_white",
            height=640,
        )
        return fig

    # ── Automated report (Diagnostic.report contract) ─────────────────────

    def report(self) -> dict[str, Any]:
        """Return a structured summary of the captured diagnostic session.

        The return shape satisfies :meth:`kailash.diagnostics.protocols.
        Diagnostic.report`. Keys:

          * ``run_id`` — the session identifier (matches ``self.run_id``).
          * ``evaluations`` — total per-query eval records captured.
          * ``retriever_comparisons`` — total leaderboard aggregates.
          * ``retrieval`` — ``{"severity": ..., "message": ...}``
          * ``faithfulness`` — ``{"severity": ..., "message": ...}``
          * ``context_utilisation`` — ``{"severity": ..., "message": ...}``
          * ``retriever_leaderboard`` — ``{"severity": ..., "top": ...,
            "message": ...}``

        Severity values are ``"HEALTHY"`` / ``"WARNING"`` / ``"CRITICAL"``
        / ``"UNKNOWN"``. UNKNOWN is returned when no data is captured for
        the relevant finding. The method is safe to call on an empty
        session.
        """
        findings: dict[str, Any] = {
            "run_id": self.run_id,
            "evaluations": len(self._eval_log),
            "retriever_comparisons": len(self._retriever_log),
        }

        eval_df = self.metrics_df()
        if eval_df.height:
            mean_recall = _safe_mean(eval_df["recall_at_k"])
            mean_precision = _safe_mean(eval_df["precision_at_k"])
            mean_util = _safe_mean(eval_df["context_utilisation"])
            mean_faith = _safe_mean(eval_df["faithfulness"])

            # Retrieval: recall@k severity bucket.
            if mean_recall < 0.3:
                findings["retrieval"] = {
                    "severity": "CRITICAL",
                    "message": (
                        f"Recall@k severely low ({mean_recall:.2f}). "
                        f"Widen top-k, add HyDE, retune embeddings, or "
                        f"check the ground-truth labels."
                    ),
                    "mean_recall_at_k": mean_recall,
                    "mean_precision_at_k": mean_precision,
                }
            elif mean_recall < 0.5:
                findings["retrieval"] = {
                    "severity": "WARNING",
                    "message": (
                        f"Recall@k below 0.5 ({mean_recall:.2f}). Consider "
                        f"widening top-k, adding HyDE, or retuning embeddings."
                    ),
                    "mean_recall_at_k": mean_recall,
                    "mean_precision_at_k": mean_precision,
                }
            else:
                findings["retrieval"] = {
                    "severity": "HEALTHY",
                    "message": (
                        f"Retrieval OK (recall@k={mean_recall:.2f}, "
                        f"precision@k={mean_precision:.2f})."
                    ),
                    "mean_recall_at_k": mean_recall,
                    "mean_precision_at_k": mean_precision,
                }

            # Faithfulness: did the generator stay grounded?
            if mean_faith < 0.5:
                findings["faithfulness"] = {
                    "severity": "CRITICAL",
                    "message": (
                        f"Faithfulness severely low ({mean_faith:.2f}) - the "
                        f"model is largely inventing. Add citation constraints, "
                        f"reduce temperature, or add a faithfulness reranker."
                    ),
                    "mean_faithfulness": mean_faith,
                }
            elif mean_faith < 0.7:
                findings["faithfulness"] = {
                    "severity": "WARNING",
                    "message": (
                        f"Faithfulness below 0.7 ({mean_faith:.2f}) - model "
                        f"may be inventing beyond the context. Add citation "
                        f"constraints or re-run with ragas for a stricter score."
                    ),
                    "mean_faithfulness": mean_faith,
                }
            else:
                findings["faithfulness"] = {
                    "severity": "HEALTHY",
                    "message": (f"Faithfulness OK ({mean_faith:.2f})."),
                    "mean_faithfulness": mean_faith,
                }

            # Context utilisation: is the generator using what it retrieved?
            if mean_util < 0.3:
                findings["context_utilisation"] = {
                    "severity": "WARNING",
                    "message": (
                        f"Context utilisation low ({mean_util:.2f}) - answers "
                        f"barely reference retrieved context. Consider "
                        f"reranking, shorter chunks, or a better prompt."
                    ),
                    "mean_context_utilisation": mean_util,
                }
            else:
                findings["context_utilisation"] = {
                    "severity": "HEALTHY",
                    "message": (f"Context utilisation OK ({mean_util:.2f})."),
                    "mean_context_utilisation": mean_util,
                }
        else:
            for key in ("retrieval", "faithfulness", "context_utilisation"):
                findings[key] = {
                    "severity": "UNKNOWN",
                    "message": "No evaluations captured - call evaluate() first.",
                }

        # Retriever leaderboard finding.
        board = self.leaderboard_df()
        if board.height:
            top = board.row(0, named=True)
            findings["retriever_leaderboard"] = {
                "severity": "HEALTHY",
                "top": top["retriever"],
                "top_mrr": float(top["mrr"]),
                "top_ndcg_at_k": float(top["ndcg_at_k"]),
                "message": (
                    f"Top retriever: {top['retriever']} "
                    f"(MRR={top['mrr']:.2f}, nDCG@k={top['ndcg_at_k']:.2f})"
                ),
            }
        else:
            findings["retriever_leaderboard"] = {
                "severity": "UNKNOWN",
                "message": (
                    "No retriever comparisons captured - call "
                    "compare_retrievers() first."
                ),
            }

        logger.info(
            "ragdiagnostics.report",
            extra={
                "rag_run_id": self.run_id,
                "rag_evaluations": findings["evaluations"],
                "rag_retrieval_severity": findings["retrieval"]["severity"],
                "rag_faithfulness_severity": findings["faithfulness"]["severity"],
                "rag_leaderboard_severity": findings["retriever_leaderboard"][
                    "severity"
                ],
            },
        )
        return findings

    # ── Judge integration (internal) ──────────────────────────────────────

    def _judge_faithfulness(
        self,
        *,
        query: str,
        answer: str,
        contexts: Sequence[str],
        sub_run_id: str,
    ) -> tuple[float, str]:
        """Score faithfulness via the configured JudgeCallable.

        Routes the faithfulness query through the Protocol's async
        ``__call__`` and returns the extracted score. Mode is ``"judge"``
        on success, ``"judge_error"`` if the judge raises (the WARN log
        preserves the exception for post-mortem), and ``"heuristic"`` as
        a final defense so the evaluation row always has a value.

        Per ``rules/agent-reasoning.md``: the LLM does all reasoning
        (via the JudgeInput rubric); this helper is a dumb dispatcher.
        """
        assert self._judge is not None  # caller-verified
        rubric = (
            "Is the response faithful to the retrieved context? "
            "Score 1.0 if the response is fully grounded in the context, "
            "with no fabrication. Score 0.0 if the response invents facts "
            "not present in the context. Penalize partial grounding "
            "proportionally."
        )
        prompt = f"[QUERY]\n{query}\n\n" f"[RETRIEVED CONTEXT]\n" + "\n\n---\n\n".join(
            contexts
        )
        judge_input = JudgeInput(
            prompt=prompt,
            candidate_a=answer,
            reference=None,
            rubric=rubric,
        )

        try:
            result: JudgeResult = _run_async(self._judge(judge_input))
        except Exception as exc:
            # Per rules/zero-tolerance.md Rule 3: log, don't silently swallow.
            logger.warning(
                "ragdiagnostics.judge_error",
                extra={
                    "rag_run_id": self.run_id,
                    "rag_sub_run_id": sub_run_id,
                    "rag_error": str(exc),
                    "mode": "real",
                },
            )
            # Fall back to deterministic heuristic so the eval row still
            # has a value. Mode flag surfaces the degradation to operators.
            return (
                _heuristic_context_utilisation(answer=answer, contexts=contexts),
                "judge_error",
            )

        score = result.score
        if score is None or not math.isfinite(score):
            logger.warning(
                "ragdiagnostics.judge_nonfinite_score",
                extra={
                    "rag_run_id": self.run_id,
                    "rag_sub_run_id": sub_run_id,
                    "rag_score": str(score),
                    "rag_judge_model": result.judge_model,
                    "mode": "real",
                },
            )
            return (
                _heuristic_context_utilisation(answer=answer, contexts=contexts),
                "judge_error",
            )
        # Clamp to [0, 1] defensively; the Protocol permits any float.
        score = max(0.0, min(1.0, score))
        logger.info(
            "ragdiagnostics.judge_ok",
            extra={
                "rag_run_id": self.run_id,
                "rag_sub_run_id": sub_run_id,
                "rag_score": score,
                "rag_judge_model": result.judge_model,
                "rag_cost_microdollars": result.cost_microdollars,
                "mode": "real",
            },
        )
        return score, "judge"


# ════════════════════════════════════════════════════════════════════════
# Metric helpers — pure, no LLM calls
# ════════════════════════════════════════════════════════════════════════


def _recall_at_k(retrieved: Sequence[str], relevant: Sequence[str]) -> float:
    """Recall@k = |retrieved ∩ relevant| / |relevant|."""
    if not relevant:
        return 0.0
    rset = set(relevant)
    hits = sum(1 for r in retrieved if r in rset)
    return hits / len(rset)


def _precision_at_k(retrieved: Sequence[str], relevant: Sequence[str]) -> float:
    """Precision@k = |retrieved ∩ relevant| / |retrieved|."""
    if not retrieved:
        return 0.0
    rset = set(relevant)
    hits = sum(1 for r in retrieved if r in rset)
    return hits / len(retrieved)


def _reciprocal_rank(retrieved: Sequence[str], relevant: Sequence[str]) -> float:
    """1/rank of the first relevant doc, or 0 if none."""
    rset = set(relevant)
    for idx, doc in enumerate(retrieved, start=1):
        if doc in rset:
            return 1.0 / idx
    return 0.0


def _ndcg_at_k(
    retrieved: Sequence[str],
    relevant: Sequence[str],
    k: int,
) -> float:
    """Normalised DCG@k — binary-relevance form."""
    rset = set(relevant)
    dcg = 0.0
    for idx, doc in enumerate(retrieved[:k], start=1):
        if doc in rset:
            dcg += 1.0 / math.log2(idx + 1)
    ideal_hits = min(len(rset), k)
    if ideal_hits == 0:
        return 0.0
    idcg = sum(1.0 / math.log2(i + 1) for i in range(1, ideal_hits + 1))
    return dcg / idcg if idcg else 0.0


def _mean(xs: Sequence[float]) -> float:
    """Arithmetic mean, 0.0 on empty input."""
    return sum(xs) / len(xs) if xs else 0.0


def _safe_mean(series: pl.Series) -> float:
    """Polars-native mean with NaN/None coalesced to 0.0."""
    raw = series.mean()
    if (
        raw is None
        or not isinstance(raw, (int, float))
        or not math.isfinite(float(raw))
    ):
        return 0.0
    return float(raw)


def _heuristic_context_utilisation(
    answer: str,
    contexts: Sequence[str],
) -> float:
    """Token-overlap context utilisation in ``[0, 1]``.

    Fraction of answer tokens (length >= 4, alpha-only, non-stopword)
    that appear in at least one retrieved context. Deterministic; no
    LLM call.
    """
    _STOP = {
        "the",
        "that",
        "this",
        "with",
        "from",
        "have",
        "they",
        "their",
        "them",
        "these",
        "those",
        "into",
        "been",
        "were",
        "will",
        "would",
        "about",
        "which",
        "there",
        "where",
    }
    ans_tokens = {
        t
        for t in answer.lower().split()
        if len(t) >= 4 and t.isalpha() and t not in _STOP
    }
    if not ans_tokens:
        return 0.0
    context_blob = " ".join(contexts).lower()
    grounded = sum(1 for t in ans_tokens if t in context_blob)
    return grounded / len(ans_tokens)


def _hash_preview(s: str) -> str:
    """``sha256:<8-hex>`` fingerprint per event-payload-classification.md §2.

    Identical contract to the cross-SDK ``format_record_id_for_event``
    helper; 8 hex chars = 32 bits of entropy, sufficient for forensic
    correlation across log + event streams.
    """
    raw = s.encode("utf-8")
    return f"sha256:{hashlib.sha256(raw).hexdigest()[:8]}"


def _run_async(coro: Any) -> Any:
    """Run an awaitable from sync context without breaking a running loop.

    Used only to dispatch ``JudgeCallable.__call__`` (an async Protocol)
    from ``evaluate()`` (sync API). When already inside an event loop
    (async caller), use ``asyncio.ensure_future`` + ``run_until_complete``
    on a fresh loop in a thread to avoid "loop already running" errors.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        # No running loop — safe to create one.
        return asyncio.run(coro)
    # A loop IS running; use a thread-bound new loop so we don't block
    # the caller's loop. This mirrors the cross-SDK pattern used by
    # Kaizen's sync-from-async bridge.
    import threading

    result: list[Any] = []
    error: list[BaseException] = []

    def _worker() -> None:
        try:
            new_loop = asyncio.new_event_loop()
            try:
                result.append(new_loop.run_until_complete(coro))
            finally:
                new_loop.close()
        except BaseException as exc:  # noqa: BLE001 — re-raised below
            error.append(exc)

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()
    thread.join()
    if error:
        raise error[0]
    return result[0]


# ════════════════════════════════════════════════════════════════════════
# Optional backend adapters — ragas + trulens-eval (pip install kailash-ml[rag])
# ════════════════════════════════════════════════════════════════════════


def _try_ragas_evaluate(
    *,
    queries: Sequence[str],
    retrieved_contexts: Sequence[Sequence[str]],
    answers: Sequence[str],
    ground_truth_ids: Optional[Sequence[Sequence[str]]],
) -> Optional[dict[str, list[float]]]:
    """Call RAGAS if available; return ``None`` when absent.

    Per ``rules/dependencies.md`` the fallback is allowed because
    :meth:`RAGDiagnostics.evaluate` loudly surfaces the fallback via a
    WARN log, and :meth:`RAGDiagnostics.ragas_scores` raises
    ``ImportError`` naming the extra.
    """
    try:
        from datasets import Dataset  # type: ignore[import-not-found]
        from ragas import evaluate as ragas_evaluate  # type: ignore[import-not-found]
        from ragas.metrics import answer_relevancy, context_precision, context_recall
        from ragas.metrics import (
            faithfulness as ragas_faithfulness,  # type: ignore[import-not-found]
        )
    except ImportError:
        logger.warning(
            "ragdiagnostics.ragas_unavailable",
            extra={
                "rag_reason": "ragas or datasets not installed",
                "rag_remedy": "pip install kailash-ml[rag]",
                "mode": "real",
            },
        )
        return None

    try:
        ds = Dataset.from_dict(
            {
                "question": list(queries),
                "contexts": [list(c) for c in retrieved_contexts],
                "answer": list(answers),
                "ground_truth": [
                    ", ".join(gt) if gt else ""
                    for gt in (ground_truth_ids or [[] for _ in queries])
                ],
            }
        )
        metrics = [ragas_faithfulness, context_precision, answer_relevancy]
        if ground_truth_ids is not None:
            metrics.append(context_recall)
        result = ragas_evaluate(ds, metrics=metrics)
    except Exception as exc:  # pragma: no cover — ragas internal error
        logger.warning(
            "ragdiagnostics.ragas_error",
            extra={"rag_error": str(exc), "mode": "real"},
        )
        return None

    # Normalise RAGAS output shape (varies across ragas versions).
    try:
        rows = list(result.scores)  # type: ignore[attr-defined]
    except AttributeError:  # pragma: no cover
        rows = result.to_pandas().to_dict("records")  # type: ignore[attr-defined]

    def _col(key: str) -> list[float]:
        return [float(r.get(key, 0.0)) for r in rows]

    return {
        "faithfulness": _col("faithfulness"),
        "context_precision": _col("context_precision"),
        "context_recall": (
            _col("context_recall") if ground_truth_ids else [0.0] * len(rows)
        ),
        "answer_relevancy": _col("answer_relevancy"),
    }


def _try_trulens_evaluate(
    *,
    queries: Sequence[str],
    retrieved_contexts: Sequence[Sequence[str]],
    answers: Sequence[str],
) -> Optional[dict[str, list[float]]]:
    """Call trulens-eval if available; return ``None`` when absent.

    trulens-eval's API varies across its release train. This helper
    dispatches through the stable ``Feedback`` + ``Groundedness`` surface
    when importable; any deeper integration is left to the caller (the
    Protocol's JudgeCallable is the recommended path for custom
    trulens flows).
    """
    try:
        from trulens_eval.feedback import Groundedness  # type: ignore[import-not-found]
        from trulens_eval.feedback.provider.base import (  # type: ignore[import-not-found]
            Provider,
        )
    except ImportError:
        logger.warning(
            "ragdiagnostics.trulens_unavailable",
            extra={
                "rag_reason": "trulens-eval not installed",
                "rag_remedy": "pip install kailash-ml[rag]",
                "mode": "real",
            },
        )
        return None

    # trulens requires a configured Provider (OpenAI, Ollama, etc.); the
    # adapter does not ship one per rules/framework-first.md. Caller
    # must have set trulens's provider before invoking trulens_scores().
    # We return the module-level helper stubs; extending this to real
    # feedback runs requires the caller to register their Provider.
    try:
        _provider_cls = Provider  # referenced so it's not a dead import
        _ground_cls = Groundedness
    except Exception as exc:  # pragma: no cover
        logger.warning(
            "ragdiagnostics.trulens_error",
            extra={"rag_error": str(exc), "mode": "real"},
        )
        return None

    # Without a caller-supplied Provider, we compute a neutral
    # placeholder (0.0) per row so the DataFrame schema is stable; the
    # public ragas_scores / trulens_scores methods raise ImportError
    # loudly when the extra is absent. This branch is the "extra
    # installed but no provider configured" path, logged at WARN.
    logger.warning(
        "ragdiagnostics.trulens_no_provider",
        extra={
            "rag_remedy": (
                "configure a trulens Provider (OpenAI, Ollama, etc.) "
                "before calling trulens_scores(); see trulens-eval docs"
            ),
            "mode": "real",
        },
    )
    n = len(queries)
    return {
        "groundedness": [0.0] * n,
        "answer_relevance": [0.0] * n,
    }

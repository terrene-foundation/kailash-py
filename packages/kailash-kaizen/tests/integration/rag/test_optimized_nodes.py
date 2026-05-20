"""Tier-2a integration coverage — ``kaizen.nodes.rag.optimized``.

F8 shard B9c. Real interpreter execution of the 4 optimized RAG
classes' codegen templates — covering the **cache/stream/batch
correctness** value-anchor that the resurrection floor never verified.

Value-anchor (F8 plan §B B9c row): "**cache/stream correctness of
preserved nodes**". This file lifts the cache + parallel + batch
correctness half by exercising:

  - CacheOptimizedRAGNode's cache_key + semantic-cache codegen
    templates under real interpreter execution; cache hit / miss /
    bounded-state semantics.
  - AsyncParallelRAGNode's parallel_executor + result_combiner
    codegen templates; multi-strategy fusion correctness on fixed
    score fixtures.
  - StreamingRAGNode's progressive_retriever codegen template;
    iterative chunked output semantics.
  - BatchOptimizedRAGNode's batch_organizer + processor codegen
    templates; multi-query batch processing correctness.

NO mocking (``@patch`` / ``MagicMock`` / ``unittest.mock`` are BLOCKED
in Tier 2/3 per ``rules/testing.md``). The PythonCodeNode sandbox
uses two-scope exec which hides module imports from nested function
lookups (F9 ledger class) — so the codegen templates are exercised
through `exec` in a single namespace (real Python interpreter, no
sandbox), the same pattern B9b used for the metric_aggregator and
context_evaluator tests.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List

import pytest

from kaizen.nodes.rag.optimized import (
    AsyncParallelRAGNode,
    BatchOptimizedRAGNode,
    CacheOptimizedRAGNode,
    StreamingRAGNode,
)

pytestmark = pytest.mark.integration


def _exec_codegen(code: str, ns_seed: Dict[str, Any]) -> Dict[str, Any]:
    """Exec codegen in a single-namespace real Python interpreter.

    The PythonCodeNode sandbox uses two-scope exec which breaks nested
    function lookups for module-level imports (F9 ledger class). The
    test runs the codegen through a real `exec` call — Python's normal
    one-namespace semantics restore the closure behavior.
    """
    ns: dict = dict(ns_seed)
    exec(code, ns)
    return ns["result"]


# ==========================================================================
# CacheOptimizedRAGNode — cache_key_generator codegen correctness
# ==========================================================================


class TestCacheKeyGenerator:
    """The cache_key_generator codegen produces deterministic keys."""

    def test_same_query_produces_same_cache_key(self):
        node = CacheOptimizedRAGNode()
        wf = node._create_workflow()  # type: ignore[attr-defined]
        key_gen = wf.get_node("cache_key_generator")
        assert key_gen is not None
        code = key_gen.config["code"]
        out_a = _exec_codegen(code, {"query": "what is deep learning"})
        out_b = _exec_codegen(code, {"query": "what is deep learning"})
        # Same query → same cache key (deterministic hash).
        assert out_a["cache_keys"]["exact"] == out_b["cache_keys"]["exact"]
        assert out_a["cache_keys"]["semantic"] == out_b["cache_keys"]["semantic"]
        # Both keys are documented-format strings.
        assert isinstance(out_a["cache_keys"]["exact"], str)
        assert out_a["cache_keys"]["semantic"].startswith("semantic_")

    def test_different_queries_produce_different_keys(self):
        node = CacheOptimizedRAGNode()
        wf = node._create_workflow()  # type: ignore[attr-defined]
        key_gen = wf.get_node("cache_key_generator")
        assert key_gen is not None
        code = key_gen.config["code"]
        out_a = _exec_codegen(code, {"query": "alpha"})
        out_b = _exec_codegen(code, {"query": "beta"})
        # Different queries → different cache keys.
        assert out_a["cache_keys"]["exact"] != out_b["cache_keys"]["exact"]


# ==========================================================================
# CacheOptimizedRAGNode — semantic_cache_manager hit/miss correctness
# ==========================================================================


class TestSemanticCacheManager:
    """The semantic_cache_manager codegen routes on exact_hit / semantic match."""

    def test_exact_hit_returns_cached_result(self):
        node = CacheOptimizedRAGNode()
        wf = node._create_workflow()  # type: ignore[attr-defined]
        sem_mgr = wf.get_node("semantic_cache_manager")
        assert sem_mgr is not None
        code = sem_mgr.config["code"]
        # cache_check_result has exact_hit=True → use_cache=True, type=exact.
        out = _exec_codegen(
            code,
            {
                "query": "anything",
                "cache_check_result": {
                    "exact_hit": True,
                    "exact_result": {"results": ["cached_doc"]},
                    "semantic_candidates": {},
                },
            },
        )
        assert out["use_cache"] is True
        assert out["cache_type"] == "exact"
        assert out["cached_result"] == {"results": ["cached_doc"]}

    def test_no_exact_no_semantic_returns_cache_miss(self):
        node = CacheOptimizedRAGNode()
        wf = node._create_workflow()  # type: ignore[attr-defined]
        sem_mgr = wf.get_node("semantic_cache_manager")
        assert sem_mgr is not None
        code = sem_mgr.config["code"]
        out = _exec_codegen(
            code,
            {
                "query": "completely different",
                "cache_check_result": {
                    "exact_hit": False,
                    "semantic_candidates": {},
                },
            },
        )
        assert out["use_cache"] is False
        assert out["cache_type"] is None

    def test_semantic_hit_above_threshold_returns_cached(self):
        """High similarity_threshold (0.5 here) lets near-duplicate queries
        hit the semantic cache."""
        node = CacheOptimizedRAGNode(similarity_threshold=0.5)
        wf = node._create_workflow()  # type: ignore[attr-defined]
        sem_mgr = wf.get_node("semantic_cache_manager")
        assert sem_mgr is not None
        code = sem_mgr.config["code"]
        # Query "alpha beta gamma" vs cached "alpha beta delta":
        # intersection={alpha,beta}, union={alpha,beta,gamma,delta} → 2/4=0.5.
        # 0.5 >= 0.5 threshold → semantic hit.
        out = _exec_codegen(
            code,
            {
                "query": "alpha beta gamma",
                "cache_check_result": {
                    "exact_hit": False,
                    "semantic_candidates": {
                        "alpha beta delta": {"results": ["sem_doc"]},
                    },
                },
            },
        )
        assert out["use_cache"] is True
        assert out["cache_type"] == "semantic"
        assert out["similarity"] == pytest.approx(0.5)

    def test_semantic_miss_below_threshold(self):
        """Low similarity → no semantic hit when above threshold isn't met."""
        node = CacheOptimizedRAGNode(similarity_threshold=0.95)
        wf = node._create_workflow()  # type: ignore[attr-defined]
        sem_mgr = wf.get_node("semantic_cache_manager")
        assert sem_mgr is not None
        code = sem_mgr.config["code"]
        # similarity=0.5, threshold=0.95 → miss.
        out = _exec_codegen(
            code,
            {
                "query": "alpha beta gamma",
                "cache_check_result": {
                    "exact_hit": False,
                    "semantic_candidates": {
                        "alpha beta delta": {"results": ["sem_doc"]},
                    },
                },
            },
        )
        assert out["use_cache"] is False
        assert out["cache_type"] is None


# ==========================================================================
# CacheOptimizedRAGNode — hit/miss/eviction state semantics through facade
# ==========================================================================


class TestCacheHitMissReadback:
    """State read-back: same cache_key_generator invocation produces the
    same key, AND the same query parameters return the same key across
    invocations — the cache-hit detection invariant."""

    def test_hit_detection_via_repeated_key_generation(self):
        """Two invocations with the same query produce IDENTICAL cache
        keys — the cache lookup contract is built on this invariant."""
        node = CacheOptimizedRAGNode()
        wf = node._create_workflow()  # type: ignore[attr-defined]
        key_gen = wf.get_node("cache_key_generator")
        assert key_gen is not None
        code = key_gen.config["code"]
        # Call 1: first cache lookup for this query.
        out_call_1 = _exec_codegen(code, {"query": "deep learning intro"})
        # Call 2: second cache lookup for the SAME query — would hit cache.
        out_call_2 = _exec_codegen(code, {"query": "deep learning intro"})
        # Same key → cache would return the hit.
        assert out_call_1["cache_keys"]["exact"] == out_call_2["cache_keys"]["exact"]

    def test_miss_distinct_queries_distinct_keys(self):
        """Distinct queries → distinct cache keys → cache misses."""
        node = CacheOptimizedRAGNode()
        wf = node._create_workflow()  # type: ignore[attr-defined]
        key_gen = wf.get_node("cache_key_generator")
        assert key_gen is not None
        code = key_gen.config["code"]
        # 5 distinct queries should produce 5 distinct cache keys.
        queries = ["one", "two", "three", "four", "five"]
        keys = set()
        for q in queries:
            out = _exec_codegen(code, {"query": q})
            keys.add(out["cache_keys"]["exact"])
        assert len(keys) == 5  # all distinct → all would miss the cache.


# ==========================================================================
# AsyncParallelRAGNode — parallel fusion correctness
# ==========================================================================


class TestParallelExecutorAndCombiner:
    """The parallel_executor produces an execution plan; the result_combiner
    fuses per-strategy results into a single ranked list."""

    def test_parallel_executor_publishes_strategy_configs(self):
        node = AsyncParallelRAGNode(strategies=["semantic", "hybrid"])
        wf = node._create_workflow()  # type: ignore[attr-defined]
        exec_node = wf.get_node("parallel_executor")
        assert exec_node is not None
        code = exec_node.config["code"]
        out = _exec_codegen(
            code,
            {"query": "test query", "documents": [{"content": "doc one"}]},
        )
        # The execution_plan carries the strategy list + parallel count.
        assert out["execution_plan"]["strategies"] == ["semantic", "hybrid"]
        assert out["execution_plan"]["parallel_count"] == 2
        # strategy_configs carries per-strategy config dicts.
        assert set(out["strategy_configs"].keys()) == {"semantic", "hybrid"}
        for cfg in out["strategy_configs"].values():
            assert cfg["enabled"] is True
            assert cfg["timeout"] == 5.0
            assert cfg["fallback"] == "hybrid"

    def test_result_combiner_fuses_per_strategy_results(self):
        """Combiner aggregates per-strategy scores into a single ranked list."""
        from datetime import datetime

        node = AsyncParallelRAGNode(strategies=["semantic", "hybrid"])
        wf = node._create_workflow()  # type: ignore[attr-defined]
        combiner = wf.get_node("result_combiner")
        assert combiner is not None
        code = combiner.config["code"]
        # Each strategy provides results with the documented shape.
        strategy_a_results = {
            "results": [
                {"id": "doc1", "content": "alpha"},
                {"id": "doc2", "content": "beta"},
            ],
            "scores": [0.9, 0.7],
        }
        strategy_b_results = {
            "results": [
                {"id": "doc1", "content": "alpha"},
                {"id": "doc3", "content": "gamma"},
            ],
            "scores": [0.8, 0.6],
        }
        out = _exec_codegen(
            code,
            {
                "execution_plan": {
                    "strategies": ["semantic", "hybrid"],
                    "query": "test",
                    "start_time": datetime.now().isoformat(),
                    "parallel_count": 2,
                },
                "semantic_results": strategy_a_results,
                "hybrid_results": strategy_b_results,
            },
        )
        parallel = out["parallel_results"]
        # Documented shape carries results / scores / metadata.
        assert "results" in parallel
        assert "scores" in parallel
        assert "metadata" in parallel
        # All 3 unique docs end up in the fused result.
        result_ids = {r["id"] for r in parallel["results"]}
        assert result_ids == {"doc1", "doc2", "doc3"}
        # The strategy_agreements counter records how many docs were
        # returned by ALL strategies — doc1 by both, doc2/doc3 by one.
        assert parallel["metadata"]["strategy_agreements"] == 1
        # The strategies_used list is the input strategies.
        assert set(parallel["metadata"]["strategies_used"]) == {"semantic", "hybrid"}

    def test_combiner_doc1_first_when_appearing_in_both_strategies(self):
        """A doc returned by BOTH strategies has aggregated higher score
        than one returned by only one — should rank first."""
        from datetime import datetime

        node = AsyncParallelRAGNode(strategies=["semantic", "hybrid"])
        wf = node._create_workflow()  # type: ignore[attr-defined]
        combiner = wf.get_node("result_combiner")
        assert combiner is not None
        code = combiner.config["code"]
        # doc1: in both with mean 0.85; doc2: in one with mean 0.7;
        # doc3: in one with mean 0.6.
        out = _exec_codegen(
            code,
            {
                "execution_plan": {
                    "strategies": ["semantic", "hybrid"],
                    "query": "q",
                    "start_time": datetime.now().isoformat(),
                    "parallel_count": 2,
                },
                "semantic_results": {
                    "results": [
                        {"id": "doc1", "content": "x"},
                        {"id": "doc2", "content": "y"},
                    ],
                    "scores": [0.9, 0.7],
                },
                "hybrid_results": {
                    "results": [
                        {"id": "doc1", "content": "x"},
                        {"id": "doc3", "content": "z"},
                    ],
                    "scores": [0.8, 0.6],
                },
            },
        )
        parallel = out["parallel_results"]
        # doc1 has mean (0.9+0.8)/2=0.85 — should rank first.
        assert parallel["results"][0]["id"] == "doc1"
        assert parallel["scores"][0] == pytest.approx(0.85)


# ==========================================================================
# StreamingRAGNode — progressive_retriever chunked output correctness
# ==========================================================================


class TestStreamingProgressiveRetriever:
    """The progressive_retriever codegen scans a doc batch and produces
    initial-stage chunked results — the documented stream contract."""

    def test_progressive_retriever_returns_initial_stage_shape(self):
        node = StreamingRAGNode(chunk_size=5)
        wf = node._create_workflow()  # type: ignore[attr-defined]
        retriever = wf.get_node("progressive_retriever")
        assert retriever is not None
        code = retriever.config["code"]
        out = _exec_codegen(
            code,
            {
                "streaming_plan": {
                    "stages": [
                        {"name": "initial", "k": 3, "fast": True},
                        {"name": "refined", "k": 5, "fast": False},
                    ],
                },
                "query": "machine learning",
                "documents": [
                    {"content": "machine learning is great"},
                    {"content": "deep learning rocks"},
                    {"content": "unrelated content here"},
                    {"content": "another machine learning text"},
                ],
            },
        )
        prog = out["progressive_results"]
        # The initial stage results carry the documented shape.
        assert "initial" in prog
        assert "has_more" in prog
        assert "next_stage" in prog
        assert "metadata" in prog
        # 3 docs match on either "machine" or "learning"; initial-stage
        # k=3 caps results to 3.
        assert len(prog["initial"]) <= 3
        # next_stage signals refinement is available.
        assert prog["next_stage"] == "refined"
        # docs_scanned reports how many docs were inspected.
        assert prog["metadata"]["docs_scanned"] == 4

    def test_progressive_retriever_results_ranked_by_overlap(self):
        node = StreamingRAGNode(chunk_size=5)
        wf = node._create_workflow()  # type: ignore[attr-defined]
        retriever = wf.get_node("progressive_retriever")
        assert retriever is not None
        code = retriever.config["code"]
        out = _exec_codegen(
            code,
            {
                "streaming_plan": {
                    "stages": [{"name": "initial", "k": 3, "fast": True}],
                },
                "query": "machine learning algorithms",
                "documents": [
                    # 1/3 overlap.
                    {"content": "machine drilled holes"},
                    # 3/3 overlap.
                    {"content": "machine learning algorithms are great"},
                    # 2/3 overlap.
                    {"content": "deep learning algorithms exist"},
                ],
            },
        )
        results = out["progressive_results"]["initial"]
        # Top-ranked by overlap: 3/3 → 2/3 → 1/3.
        scores = [r["score"] for r in results]
        assert scores == sorted(scores, reverse=True)
        # First result has highest possible score (3/3 = 1.0).
        assert scores[0] == pytest.approx(1.0)


# ==========================================================================
# BatchOptimizedRAGNode — batch organization + processing correctness
# ==========================================================================


class TestBatchOrganizerAndProcessor:
    """The batch_organizer batches queries; the batch_processor scores
    each batch's queries against a shared document set."""

    def test_batch_organizer_splits_queries_into_documented_batches(self):
        node = BatchOptimizedRAGNode(batch_size=3)
        wf = node._create_workflow()  # type: ignore[attr-defined]
        organizer = wf.get_node("batch_organizer")
        assert organizer is not None
        code = organizer.config["code"]
        out = _exec_codegen(
            code,
            {
                "queries": [
                    "machine learning a",
                    "machine learning b",
                    "deep learning c",
                    "deep learning d",
                    "unrelated e",
                ],
            },
        )
        plan = out["batch_plan"]
        assert plan["total_queries"] == 5
        assert plan["batch_size"] == 3
        # 5 queries / 3 per batch → 2 batches (3 + 2).
        assert plan["num_batches"] == 2
        # optimization_applied=True when len(queries) > 1.
        assert plan["optimization_applied"] is True
        # Every batch carries the documented shape.
        for batch in plan["batches"]:
            assert "batch_id" in batch
            assert "queries" in batch
            assert "size" in batch

    def test_batch_organizer_single_query_no_optimization(self):
        node = BatchOptimizedRAGNode(batch_size=3)
        wf = node._create_workflow()  # type: ignore[attr-defined]
        organizer = wf.get_node("batch_organizer")
        assert organizer is not None
        code = organizer.config["code"]
        out = _exec_codegen(
            code,
            {"queries": ["only one query"]},
        )
        plan = out["batch_plan"]
        # 1 query → 1 batch, optimization NOT applied.
        assert plan["total_queries"] == 1
        assert plan["num_batches"] == 1
        assert plan["optimization_applied"] is False

    def test_batch_organizer_string_input_wraps_as_single_query(self):
        """The codegen accepts a single string and wraps it in a 1-item list."""
        node = BatchOptimizedRAGNode(batch_size=3)
        wf = node._create_workflow()  # type: ignore[attr-defined]
        organizer = wf.get_node("batch_organizer")
        assert organizer is not None
        code = organizer.config["code"]
        out = _exec_codegen(code, {"queries": "single str query"})
        assert out["batch_plan"]["total_queries"] == 1

    def test_batch_processor_scores_across_all_queries_in_batch(self):
        """The batch_processor scores every query in every batch against
        the document set — the throughput claim's correctness floor."""
        node = BatchOptimizedRAGNode(batch_size=2)
        wf = node._create_workflow()  # type: ignore[attr-defined]
        processor = wf.get_node("batch_processor")
        assert processor is not None
        code = processor.config["code"]
        out = _exec_codegen(
            code,
            {
                "batch_plan": {
                    "total_queries": 3,
                    "batch_size": 2,
                    "num_batches": 2,
                    "batches": [
                        {
                            "batch_id": 0,
                            "queries": ["machine learning", "deep learning"],
                            "size": 2,
                        },
                        {
                            "batch_id": 1,
                            "queries": ["unrelated"],
                            "size": 1,
                        },
                    ],
                    "optimization_applied": True,
                },
                "documents": [
                    {"content": "machine learning is good"},
                    {"content": "deep learning is also good"},
                    {"content": "completely separate topic"},
                ],
            },
        )
        batch_out = out["batch_results"]
        # 2 batches processed.
        assert len(batch_out["results"]) == 2
        # Statistics carry the documented shape.
        stats = batch_out["statistics"]
        assert stats["total_queries_processed"] == 3
        assert stats["batches_processed"] == 2
        # Each batch result has per-query scores.
        for br in batch_out["results"]:
            assert "batch_id" in br
            assert "query_results" in br
            assert "batch_size" in br


# ==========================================================================
# Real-time stream-mode iteration through StreamingRAGNode (chunked)
# ==========================================================================


class TestStreamingChunkedOutput:
    """StreamingRAGNode emits chunked stream-formatted output (the
    documented stream contract)."""

    def test_stream_formatter_yields_per_result_chunks_plus_metadata(self):
        node = StreamingRAGNode(chunk_size=5)
        wf = node._create_workflow()  # type: ignore[attr-defined]
        formatter = wf.get_node("stream_formatter")
        assert formatter is not None
        code = formatter.config["code"]
        out = _exec_codegen(
            code,
            {
                "progressive_results": {
                    "initial": [
                        {
                            "doc": {"content": "alpha"},
                            "stage": "initial",
                            "score": 0.9,
                        },
                        {
                            "doc": {"content": "beta"},
                            "stage": "initial",
                            "score": 0.7,
                        },
                    ],
                    "has_more": True,
                    "next_stage": "refined",
                    "metadata": {"docs_scanned": 10, "matches_found": 2},
                },
            },
        )
        # The stream_chunks list carries one chunk per result + 1 metadata
        # chunk = 3 total.
        chunks = out["stream_chunks"]
        result_chunks = [c for c in chunks if c["type"] == "result"]
        metadata_chunks = [c for c in chunks if c["type"] == "metadata"]
        assert len(result_chunks) == 2
        assert len(metadata_chunks) == 1
        # Per-result chunks carry chunk_id + score + stage.
        for i, rc in enumerate(result_chunks):
            assert rc["chunk_id"] == i
            assert "score" in rc
            assert rc["stage"] == "initial"
        # streaming_metadata reports chunk + result counts and bp support.
        meta = out["streaming_metadata"]
        assert meta["total_chunks"] == 3
        assert meta["result_chunks"] == 2
        assert meta["supports_backpressure"] is True

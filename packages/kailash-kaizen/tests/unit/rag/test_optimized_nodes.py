"""Tier 1 unit coverage — ``kaizen.nodes.rag.optimized``.

F8 shard B9c + Wave-3 S1 ``from_function`` migration. The 4 classes under
test (CacheOptimizedRAGNode, AsyncParallelRAGNode, StreamingRAGNode,
BatchOptimizedRAGNode) cover the cache / parallel / streaming / batch
optimization surface of the RAG package.

Wave-3 S1 migrated the Cache + AsyncParallel nodes from brittle f-string /
``"code"``-string ``PythonCodeNode`` codegen to ``PythonCodeNode.from_function``
wrapping real module-level functions (#1117 publish-nothing / #1123 f-string
brace-escape / #1118 import-trap root-cause fix). Wave-3 S2 completes the
migration for the Streaming + Batch nodes (same pattern); their graph-shape
assertions now check the from_function shape + flat ``result`` wiring, and each
new module-level function has a direct-call test below.

Tier 1 scope:

- Construction with default + custom kwargs across all 4 classes —
  including the A3-triage R3-L2 regression: ``CacheOptimizedRAGNode()``
  MUST NOT raise NameError on missing 'CacheNode' registry entry now
  that the registering import lands at optimized.py module scope.
- The inner workflow GRAPH SHAPE produced by each ``_create_workflow``
  method (graphs are documented-shape claims).
- One DIRECT-CALL test per new module-level function (Cache + AsyncParallel):
  valid input → correct dict; empty/None/edge input → HONEST default.
- Strategy-list interpolation invariants for AsyncParallelRAGNode.
- chunk_size / batch_size baked into the (still-codegen) Streaming/Batch
  templates at builder time.
"""

from __future__ import annotations

import pytest
from kailash.workflow.graph import Workflow

from kaizen.nodes.rag.optimized import (
    AsyncParallelRAGNode,
    BatchOptimizedRAGNode,
    CacheOptimizedRAGNode,
    StreamingRAGNode,
    _aggregate_cache_result,
    _build_execution_plan,
    _build_streaming_plan,
    _combine_strategy_results,
    _decide_cache_use,
    _format_batch_results,
    _format_stream_chunks,
    _generate_cache_keys,
    _make_result_combiner,
    _organize_batches,
    _process_batches,
    _progressive_retrieve,
)

pytestmark = pytest.mark.unit


def _build(node) -> Workflow:
    """Call ``node._create_workflow()`` past the ``@register_node`` Node-type erasure."""
    return node._create_workflow()  # type: ignore[attr-defined]


# ==========================================================================
# Construction floor — all four classes
# ==========================================================================


class TestAllFourConstruct:
    def test_cache_optimized_constructs_default(self):
        """B9c A3 R3-L2 regression: kailash.nodes.cache registering import
        MUST be in place at optimized.py module scope; otherwise this
        construction would raise NameError on missing 'CacheNode' entry
        in the node registry."""
        node = CacheOptimizedRAGNode()
        assert node is not None
        assert node.metadata.name == "cache_optimized_rag"
        assert node.cache_ttl == 3600  # type: ignore[attr-defined]
        assert node.similarity_threshold == 0.95  # type: ignore[attr-defined]

    def test_cache_optimized_constructs_with_custom_kwargs(self):
        node = CacheOptimizedRAGNode(
            name="custom_cache",
            cache_ttl=60,
            similarity_threshold=0.5,
        )
        assert node.metadata.name == "custom_cache"
        assert node.cache_ttl == 60  # type: ignore[attr-defined]
        assert node.similarity_threshold == 0.5  # type: ignore[attr-defined]

    def test_async_parallel_constructs_default(self):
        node = AsyncParallelRAGNode()
        assert node is not None
        assert node.metadata.name == "async_parallel_rag"
        assert node.strategies == ["semantic", "sparse", "hybrid"]  # type: ignore[attr-defined]

    def test_async_parallel_constructs_with_custom_strategies(self):
        node = AsyncParallelRAGNode(
            name="custom_parallel", strategies=["semantic", "hybrid"]
        )
        assert node.metadata.name == "custom_parallel"
        assert node.strategies == ["semantic", "hybrid"]  # type: ignore[attr-defined]

    def test_async_parallel_none_strategies_falls_back_to_default(self):
        """B9c Optional[List[str]] regression: None default resolves to
        the documented 3-strategy list, not a TypeError."""
        node = AsyncParallelRAGNode(strategies=None)
        assert node.strategies == ["semantic", "sparse", "hybrid"]  # type: ignore[attr-defined]

    def test_streaming_constructs_default(self):
        node = StreamingRAGNode()
        assert node is not None
        assert node.metadata.name == "streaming_rag"
        assert node.chunk_size == 100  # type: ignore[attr-defined]

    def test_streaming_constructs_with_custom_chunk_size(self):
        node = StreamingRAGNode(name="custom_stream", chunk_size=10)
        assert node.metadata.name == "custom_stream"
        assert node.chunk_size == 10  # type: ignore[attr-defined]

    def test_batch_optimized_constructs_default(self):
        node = BatchOptimizedRAGNode()
        assert node is not None
        assert node.metadata.name == "batch_optimized_rag"
        assert node.batch_size == 32  # type: ignore[attr-defined]

    def test_batch_optimized_constructs_with_custom_batch_size(self):
        node = BatchOptimizedRAGNode(name="custom_batch", batch_size=4)
        assert node.metadata.name == "custom_batch"
        assert node.batch_size == 4  # type: ignore[attr-defined]


# ==========================================================================
# Direct-call tests — _generate_cache_keys (cache_key_generator fn)
# ==========================================================================


class TestGenerateCacheKeys:
    """Direct-call coverage for the lifted cache-key generator function."""

    def test_same_query_produces_same_keys(self):
        out_a = _generate_cache_keys("what is deep learning")
        out_b = _generate_cache_keys("what is deep learning")
        assert out_a["cache_keys"]["exact"] == out_b["cache_keys"]["exact"]
        assert out_a["cache_keys"]["semantic"] == out_b["cache_keys"]["semantic"]

    def test_different_queries_produce_different_keys(self):
        out_a = _generate_cache_keys("alpha")
        out_b = _generate_cache_keys("beta")
        assert out_a["cache_keys"]["exact"] != out_b["cache_keys"]["exact"]

    def test_key_format_is_documented_shape(self):
        out = _generate_cache_keys("query")
        assert isinstance(out["cache_keys"]["exact"], str)
        assert out["cache_keys"]["semantic"].startswith("semantic_")

    def test_none_query_yields_honest_deterministic_default(self):
        """A None query coerces to '' — a stable, deterministic key, not a
        fabricated value or a crash."""
        out_a = _generate_cache_keys(None)
        out_b = _generate_cache_keys("")
        # None and "" hash to the same (empty-string) key — honest default.
        assert out_a["cache_keys"]["exact"] == out_b["cache_keys"]["exact"]
        assert isinstance(out_a["cache_keys"]["exact"], str)


# ==========================================================================
# Direct-call tests — _decide_cache_use (semantic_cache_manager fn)
# ==========================================================================


class TestDecideCacheUse:
    """Direct-call coverage for the lifted cache-decision function."""

    def test_exact_hit_returns_cached_value(self):
        out = _decide_cache_use(
            cache_hit=True,
            cache_value={"results": ["cached_doc"]},
            query="anything",
        )
        assert out["use_cache"] is True
        assert out["cache_type"] == "exact"
        assert out["cached_result"] == {"results": ["cached_doc"]}

    def test_miss_returns_no_cache(self):
        out = _decide_cache_use(
            cache_hit=False, cache_value=None, query="completely different"
        )
        assert out["use_cache"] is False
        assert out["cache_type"] is None

    def test_falsy_hit_routes_to_miss(self):
        """A falsy ``cache_hit`` (CacheNode's miss signal) routes to a miss
        regardless of any stale ``cache_value``."""
        out = _decide_cache_use(cache_hit=0, cache_value={"stale": True}, query="q")
        assert out["use_cache"] is False
        assert out["cache_type"] is None

    def test_semantic_branch_dormant_without_candidate_store(self):
        """No candidate store is wired (hardcoded {}), so a non-hit always
        routes to a miss — an honest exact-match cache, not a fabricated
        semantic hit."""
        out = _decide_cache_use(
            cache_hit=False,
            cache_value=None,
            query="alpha beta gamma",
            similarity_threshold=0.5,
        )
        assert out["use_cache"] is False
        assert out["cache_type"] is None

    def test_none_inputs_yield_honest_miss(self):
        """All-None inputs → honest miss default, never a crash or fabrication."""
        out = _decide_cache_use()
        assert out["use_cache"] is False
        assert out["cache_type"] is None


# ==========================================================================
# Direct-call tests — _aggregate_cache_result (result_aggregator fn)
# ==========================================================================


class TestAggregateCacheResult:
    """Direct-call coverage for the lifted result-aggregator function."""

    def test_cache_hit_aggregates_cached_results(self):
        out = _aggregate_cache_result(
            cache_decision={
                "use_cache": True,
                "cache_type": "exact",
                "cached_result": {"results": ["d1"], "scores": [0.9]},
            }
        )
        opt = out["optimized_results"]
        assert opt["results"] == ["d1"]
        assert opt["scores"] == [0.9]
        assert opt["metadata"]["source"] == "cache"
        assert opt["performance"]["cache_hit"] is True
        assert opt["performance"]["response_time"] == "fast"

    def test_cache_miss_aggregates_fresh_results(self):
        out = _aggregate_cache_result(
            cache_decision={"use_cache": False, "cache_type": None},
            fresh_results={"results": ["fresh1"], "scores": [0.5]},
        )
        opt = out["optimized_results"]
        assert opt["results"] == ["fresh1"]
        assert opt["metadata"]["source"] == "fresh"
        assert opt["performance"]["cache_hit"] is False
        assert opt["performance"]["response_time"] == "normal"

    def test_none_decision_and_none_fresh_yield_honest_empty(self):
        """Missing decision + missing fresh_results (cache hit skips the
        rag_processor) → empty results list, never fabricated documents."""
        out = _aggregate_cache_result(cache_decision=None, fresh_results=None)
        opt = out["optimized_results"]
        assert opt["results"] == []
        assert opt["scores"] == []
        assert opt["performance"]["cache_hit"] is False


# ==========================================================================
# Direct-call tests — _build_execution_plan (parallel_executor fn)
# ==========================================================================


class TestBuildExecutionPlan:
    """Direct-call coverage for the lifted parallel-executor function."""

    def test_plan_carries_strategies_and_count(self):
        out = _build_execution_plan(
            query="test query",
            strategies=["semantic", "hybrid"],
        )
        assert out["execution_plan"]["strategies"] == ["semantic", "hybrid"]
        assert out["execution_plan"]["parallel_count"] == 2
        assert out["execution_plan"]["query"] == "test query"

    def test_strategy_configs_per_strategy(self):
        out = _build_execution_plan(query="q", strategies=["semantic", "hybrid"])
        assert set(out["strategy_configs"].keys()) == {"semantic", "hybrid"}
        for cfg in out["strategy_configs"].values():
            assert cfg["enabled"] is True
            assert cfg["timeout"] == 5.0
            assert cfg["fallback"] == "hybrid"

    def test_empty_strategies_yields_honest_empty_plan(self):
        """No strategies → empty plan, never fabricated strategies."""
        out = _build_execution_plan(query="q", strategies=None)
        assert out["execution_plan"]["strategies"] == []
        assert out["execution_plan"]["parallel_count"] == 0
        assert out["strategy_configs"] == {}


# ==========================================================================
# Direct-call tests — _combine_strategy_results + _make_result_combiner
# ==========================================================================


class TestCombineStrategyResults:
    """Direct-call coverage for the lifted result-combiner core + factory."""

    def test_fuses_per_strategy_results(self):
        out = _combine_strategy_results(
            execution_plan={"start_time": None},
            strategies=["semantic", "hybrid"],
            strategy_results={
                "semantic": {
                    "results": [
                        {"id": "doc1", "content": "a"},
                        {"id": "doc2", "content": "b"},
                    ],
                    "scores": [0.9, 0.7],
                },
                "hybrid": {
                    "results": [
                        {"id": "doc1", "content": "a"},
                        {"id": "doc3", "content": "c"},
                    ],
                    "scores": [0.8, 0.6],
                },
            },
        )
        parallel = out["parallel_results"]
        assert {r["id"] for r in parallel["results"]} == {"doc1", "doc2", "doc3"}
        # doc1 returned by both strategies → strategy_agreements == 1.
        assert parallel["metadata"]["strategy_agreements"] == 1
        assert set(parallel["metadata"]["strategies_used"]) == {"semantic", "hybrid"}

    def test_doc_in_both_strategies_ranks_first(self):
        out = _combine_strategy_results(
            execution_plan={"start_time": None},
            strategies=["semantic", "hybrid"],
            strategy_results={
                "semantic": {
                    "results": [
                        {"id": "doc1", "content": "x"},
                        {"id": "doc2", "content": "y"},
                    ],
                    "scores": [0.9, 0.7],
                },
                "hybrid": {
                    "results": [
                        {"id": "doc1", "content": "x"},
                        {"id": "doc3", "content": "z"},
                    ],
                    "scores": [0.8, 0.6],
                },
            },
        )
        parallel = out["parallel_results"]
        # doc1 mean (0.9+0.8)/2 = 0.85 → ranks first.
        assert parallel["results"][0]["id"] == "doc1"
        assert parallel["scores"][0] == pytest.approx(0.85)

    def test_empty_results_yield_honest_empty_fusion(self):
        """No strategy results → empty fused output, never fabricated docs."""
        out = _combine_strategy_results(
            execution_plan=None, strategies=["semantic"], strategy_results={}
        )
        parallel = out["parallel_results"]
        assert parallel["results"] == []
        assert parallel["scores"] == []
        assert parallel["metadata"]["strategies_used"] == []

    def test_unparseable_start_time_yields_zero_total_time(self):
        """A malformed execution_plan start_time → 0.0 total time, never a crash."""
        out = _combine_strategy_results(
            execution_plan={"start_time": "not-a-timestamp"},
            strategies=["semantic"],
            strategy_results={
                "semantic": {"results": [{"id": "d", "content": "c"}], "scores": [0.5]}
            },
        )
        assert out["parallel_results"]["metadata"]["total_execution_time"] == 0.0

    def test_factory_declares_one_input_per_strategy(self):
        """The factory synthesises a signature with execution_plan + one
        <strategy>_results param per declared strategy."""
        import inspect as _inspect

        fn = _make_result_combiner(["semantic", "sparse"])
        params = list(_inspect.signature(fn).parameters)
        assert params == ["execution_plan", "semantic_results", "sparse_results"]

    def test_factory_deduplicates_repeated_strategy(self):
        """A repeated strategy name must NOT produce a duplicate parameter
        (an invalid signature)."""
        import inspect as _inspect

        fn = _make_result_combiner(["semantic", "semantic"])
        params = list(_inspect.signature(fn).parameters)
        assert params == ["execution_plan", "semantic_results"]

    def test_factory_combiner_routes_to_core(self):
        """The factory-built combiner accepts the wired inputs and fuses them."""
        fn = _make_result_combiner(["semantic"])
        out = fn(
            execution_plan={"start_time": None},
            semantic_results={
                "results": [{"id": "d1", "content": "c"}],
                "scores": [0.9],
            },
        )
        assert out["parallel_results"]["results"][0]["id"] == "d1"


# ==========================================================================
# Direct-call tests — _build_streaming_plan (stream_controller fn)
# ==========================================================================


class TestBuildStreamingPlan:
    """Direct-call coverage for the lifted streaming-plan builder."""

    def test_plan_carries_chunk_size_and_stages(self):
        out = _build_streaming_plan(chunk_size=50)
        plan = out["streaming_plan"]
        assert plan["chunk_size"] == 50
        assert plan["strategy"] == "progressive"
        assert [s["name"] for s in plan["stages"]] == [
            "initial",
            "refined",
            "complete",
        ]

    def test_default_chunk_size_matches_constructor_default(self):
        out = _build_streaming_plan()
        assert out["streaming_plan"]["chunk_size"] == 100


# ==========================================================================
# Direct-call tests — _progressive_retrieve (progressive_retriever fn)
# ==========================================================================


class TestProgressiveRetrieve:
    """Direct-call coverage for the lifted progressive-retrieval function."""

    def test_keyword_overlap_produces_initial_results(self):
        out = _progressive_retrieve(
            streaming_plan={"stages": [{"name": "initial", "k": 3}]},
            query="deep learning",
            documents=[
                {"id": "d1", "content": "deep learning models"},
                {"id": "d2", "content": "unrelated topic"},
                {"id": "d3", "content": "learning fast"},
            ],
        )
        prog = out["progressive_results"]
        matched = {r["doc"]["id"] for r in prog["initial"]}
        assert matched == {"d1", "d3"}  # d2 has no overlap
        assert prog["metadata"]["matches_found"] == 2
        assert prog["next_stage"] == "refined"

    def test_results_capped_at_initial_stage_k(self):
        out = _progressive_retrieve(
            streaming_plan={"stages": [{"name": "initial", "k": 1}]},
            query="alpha",
            documents=[
                {"id": "d1", "content": "alpha"},
                {"id": "d2", "content": "alpha"},
            ],
        )
        assert len(out["progressive_results"]["initial"]) == 1

    def test_none_inputs_yield_honest_empty_default(self):
        """All-None inputs → empty initial results, honest fallback k, never a
        crash or fabricated documents."""
        out = _progressive_retrieve()
        prog = out["progressive_results"]
        assert prog["initial"] == []
        assert prog["metadata"]["matches_found"] == 0
        assert prog["has_more"] is False

    def test_missing_plan_falls_back_to_default_k(self):
        """A missing streaming_plan → default initial k of 3, never a crash."""
        out = _progressive_retrieve(
            streaming_plan=None,
            query="a b c d",
            documents=[{"id": str(i), "content": "a b c d"} for i in range(5)],
        )
        assert len(out["progressive_results"]["initial"]) == 3


# ==========================================================================
# Direct-call tests — _format_stream_chunks (stream_formatter fn)
# ==========================================================================


class TestFormatStreamChunks:
    """Direct-call coverage for the lifted stream-formatter function."""

    def test_results_plus_metadata_chunk(self):
        out = _format_stream_chunks(
            progressive_results={
                "initial": [
                    {"doc": {"id": "d1"}, "score": 0.9, "stage": "initial"},
                ],
                "metadata": {"docs_scanned": 1},
                "has_more": False,
                "next_stage": "refined",
            }
        )
        chunks = out["stream_chunks"]
        # 1 result chunk + 1 metadata chunk.
        assert len(chunks) == 2
        assert chunks[0]["type"] == "result"
        assert chunks[0]["content"] == {"id": "d1"}
        assert chunks[-1]["type"] == "metadata"
        assert out["streaming_metadata"]["result_chunks"] == 1
        assert out["streaming_metadata"]["supports_backpressure"] is True

    def test_none_input_yields_metadata_only(self):
        """A missing progressive_results → only the metadata chunk, never a
        fabricated result chunk."""
        out = _format_stream_chunks(progressive_results=None)
        chunks = out["stream_chunks"]
        assert len(chunks) == 1
        assert chunks[0]["type"] == "metadata"
        assert out["streaming_metadata"]["result_chunks"] == 0


# ==========================================================================
# Direct-call tests — _organize_batches (batch_organizer fn)
# ==========================================================================


class TestOrganizeBatches:
    """Direct-call coverage for the lifted batch-organizer function."""

    def test_batches_respect_batch_size(self):
        out = _organize_batches(queries=["q1", "q2", "q3"], batch_size=2)
        plan = out["batch_plan"]
        assert plan["total_queries"] == 3
        assert plan["batch_size"] == 2
        # 3 queries / batch_size 2 → 2 batches.
        assert plan["num_batches"] == 2
        assert plan["optimization_applied"] is True

    def test_single_string_query_coerced_to_list(self):
        out = _organize_batches(queries="solo", batch_size=4)
        plan = out["batch_plan"]
        assert plan["total_queries"] == 1
        # Single query → optimization NOT applied (len <= 1).
        assert plan["optimization_applied"] is False

    def test_none_queries_yield_honest_empty_plan(self):
        """No queries → empty plan, never fabricated queries."""
        out = _organize_batches(queries=None, batch_size=4)
        plan = out["batch_plan"]
        assert plan["total_queries"] == 0
        assert plan["num_batches"] == 0
        assert plan["batches"] == []


# ==========================================================================
# Direct-call tests — _process_batches (batch_processor fn)
# ==========================================================================


class TestProcessBatches:
    """Direct-call coverage for the lifted batch-processor function."""

    def test_scores_documents_per_query(self):
        plan = _organize_batches(queries=["alpha beta"], batch_size=4)["batch_plan"]
        out = _process_batches(
            batch_plan=plan,
            documents=[
                {"id": "d1", "content": "alpha beta gamma"},
                {"id": "d2", "content": "delta"},
            ],
        )
        res = out["batch_results"]
        assert res["statistics"]["total_queries_processed"] == 1
        assert res["statistics"]["batches_processed"] == 1
        # One batch, one query → one query_results entry of doc-score tuples.
        assert len(res["results"][0]["query_results"]) == 1

    def test_none_inputs_yield_honest_empty_results(self):
        """Missing batch_plan + documents → empty results, zero-query stats,
        never fabricated documents or scores."""
        out = _process_batches(batch_plan=None, documents=None)
        res = out["batch_results"]
        assert res["results"] == []
        assert res["statistics"]["total_queries_processed"] == 0
        assert res["statistics"]["avg_results_per_query"] == 0.0


# ==========================================================================
# Direct-call tests — _format_batch_results (result_formatter fn)
# ==========================================================================


class TestFormatBatchResults:
    """Direct-call coverage for the lifted result-formatter function."""

    def test_maps_scores_back_to_per_query_documents(self):
        documents = [
            {"id": "d1", "content": "alpha beta"},
            {"id": "d2", "content": "gamma"},
        ]
        plan = _organize_batches(queries=["alpha"], batch_size=4)["batch_plan"]
        batch_results = _process_batches(batch_plan=plan, documents=documents)[
            "batch_results"
        ]
        out = _format_batch_results(
            batch_results=batch_results,
            batch_plan=plan,
            documents=documents,
        )
        final = out["final_batch_results"]
        assert "alpha" in final["query_results"]
        # d1 overlaps "alpha"; d2 does not → only positive-score docs emitted.
        assert final["query_results"]["alpha"]["results"] == [
            {"id": "d1", "content": "alpha beta"}
        ]
        assert final["processing_order"] == ["alpha"]

    def test_none_inputs_yield_honest_empty_map(self):
        """Missing inputs → empty per-query map, never fabricated documents."""
        out = _format_batch_results(batch_results=None, batch_plan=None, documents=None)
        final = out["final_batch_results"]
        assert final["query_results"] == {}
        assert final["processing_order"] == []


# ==========================================================================
# CacheOptimizedRAGNode — graph shape + cache wiring
# ==========================================================================


class TestCacheOptimizedGraphShape:
    """The cache-optimized workflow wires 6 nodes including 2 CacheNode sites."""

    def test_graph_has_six_nodes(self):
        wf = _build(CacheOptimizedRAGNode())
        assert set(wf.nodes.keys()) == {
            "cache_key_generator",
            "cache_checker",
            "semantic_cache_manager",
            "rag_processor",
            "cache_updater",
            "result_aggregator",
        }

    def test_cache_checker_and_cache_updater_are_cache_nodes(self):
        """Both cache_checker + cache_updater are typed CacheNode (the
        type registered by the kailash.nodes.cache import)."""
        wf = _build(CacheOptimizedRAGNode())
        cache_checker = wf.get_node("cache_checker")
        cache_updater = wf.get_node("cache_updater")
        assert cache_checker is not None
        assert cache_updater is not None
        assert cache_checker.config.get("operation") == "get"
        assert cache_updater.config.get("operation") == "set"

    def test_cache_ttl_baked_into_cache_node_configs(self):
        wf = _build(CacheOptimizedRAGNode(cache_ttl=42))
        assert wf.get_node("cache_checker").config.get("ttl") == 42  # type: ignore[union-attr]
        assert wf.get_node("cache_updater").config.get("ttl") == 42  # type: ignore[union-attr]

    def test_cache_key_generator_is_from_function_node(self):
        """Post-migration: cache_key_generator wraps a real function (no
        codegen ``code`` string with logic)."""
        wf = _build(CacheOptimizedRAGNode())
        key_gen = wf.get_node("cache_key_generator")
        assert key_gen is not None
        assert key_gen.config.get("function") is not None

    def test_result_aggregator_is_final_sink(self):
        wf = _build(CacheOptimizedRAGNode())
        outbound = [c for c in wf.connections if c.source_node == "result_aggregator"]
        assert outbound == []

    def test_cache_decision_wiring_reads_result_port(self):
        """The skip-gate reads the nested ``result.use_cache`` port and the
        aggregator reads the flat ``result`` port — the from_function shape."""
        wf = _build(CacheOptimizedRAGNode())
        skip_edges = [
            c
            for c in wf.connections
            if c.source_node == "semantic_cache_manager"
            and c.target_node == "rag_processor"
        ]
        assert len(skip_edges) == 1
        assert skip_edges[0].source_output == "result.use_cache"


# ==========================================================================
# AsyncParallelRAGNode — graph shape + strategy fan-out
# ==========================================================================


class TestAsyncParallelGraphShape:
    """The parallel workflow wires one strategy node per declared strategy."""

    def test_default_graph_has_executor_three_strategies_combiner(self):
        wf = _build(AsyncParallelRAGNode())
        expected = {
            "parallel_executor",
            "semantic_rag",
            "sparse_rag",
            "hybrid_rag",
            "result_combiner",
        }
        assert set(wf.nodes.keys()) == expected

    def test_custom_strategies_drive_strategy_nodes(self):
        wf = _build(AsyncParallelRAGNode(strategies=["semantic"]))
        assert set(wf.nodes.keys()) == {
            "parallel_executor",
            "semantic_rag",
            "result_combiner",
        }

    def test_unknown_strategy_falls_back_to_semantic_node_type(self):
        """An unknown strategy name still produces a strategy node (defaulting
        to SemanticRAGNode under the hood)."""
        wf = _build(AsyncParallelRAGNode(strategies=["unknown_strategy"]))
        assert "unknown_strategy_rag" in wf.nodes
        node = wf.get_node("unknown_strategy_rag")
        assert node is not None
        assert node.config.get("config", {}).get("retrieval_k") == 5

    def test_executor_connects_to_combiner_via_result_port(self):
        """Post-migration: the executor publishes on the flat ``result`` port,
        so the combiner edge reads ``result.execution_plan`` (the latent
        #1117 nested-port defect, now closed)."""
        wf = _build(AsyncParallelRAGNode(strategies=["semantic"]))
        executor_to_combiner = [
            c
            for c in wf.connections
            if c.source_node == "parallel_executor"
            and c.target_node == "result_combiner"
        ]
        assert len(executor_to_combiner) == 1
        assert executor_to_combiner[0].source_output == "result.execution_plan"

    def test_each_strategy_node_connects_to_combiner(self):
        wf = _build(AsyncParallelRAGNode(strategies=["semantic", "hybrid"]))
        targets_into_combiner = {
            c.source_node for c in wf.connections if c.target_node == "result_combiner"
        }
        assert {"semantic_rag", "hybrid_rag", "parallel_executor"}.issubset(
            targets_into_combiner
        )

    def test_strategy_results_wired_to_per_strategy_inputs(self):
        """Each <strategy>_rag node wires to the combiner's <strategy>_results
        input — the declared inputs the from_function factory synthesised."""
        wf = _build(AsyncParallelRAGNode(strategies=["semantic", "hybrid"]))
        combiner_inputs = {
            c.target_input for c in wf.connections if c.target_node == "result_combiner"
        }
        assert {"semantic_results", "hybrid_results"}.issubset(combiner_inputs)

    def test_combiner_is_final_sink(self):
        wf = _build(AsyncParallelRAGNode())
        outbound = [c for c in wf.connections if c.source_node == "result_combiner"]
        assert outbound == []

    def test_parallel_executor_is_from_function_node(self):
        """Post-migration: parallel_executor wraps a real function."""
        wf = _build(AsyncParallelRAGNode())
        executor = wf.get_node("parallel_executor")
        assert executor is not None
        assert executor.config.get("function") is not None


# ==========================================================================
# StreamingRAGNode — graph shape (S2: migrated to from_function)
# ==========================================================================


class TestOptimizedStreamingGraphShape:
    """The streaming workflow wires 3 from_function nodes (S2 migration)."""

    def test_graph_has_three_nodes(self):
        wf = _build(StreamingRAGNode())
        assert set(wf.nodes.keys()) == {
            "stream_controller",
            "progressive_retriever",
            "stream_formatter",
        }

    def test_stream_controller_feeds_progressive_retriever_via_result_port(self):
        """Post-migration: the controller publishes on the flat ``result`` port,
        so the retriever edge reads ``result.streaming_plan`` (the latent #1117
        nested-port defect, now closed)."""
        wf = _build(StreamingRAGNode())
        edges = [
            c
            for c in wf.connections
            if c.source_node == "stream_controller"
            and c.target_node == "progressive_retriever"
        ]
        assert len(edges) == 1
        assert edges[0].source_output == "result.streaming_plan"

    def test_progressive_retriever_feeds_stream_formatter_via_result_port(self):
        wf = _build(StreamingRAGNode())
        edges = [
            c
            for c in wf.connections
            if c.source_node == "progressive_retriever"
            and c.target_node == "stream_formatter"
        ]
        assert len(edges) == 1
        assert edges[0].source_output == "result.progressive_results"

    def test_stream_controller_is_from_function_node(self):
        """Post-migration: stream_controller wraps a real function (no codegen
        ``code`` string with logic)."""
        wf = _build(StreamingRAGNode(chunk_size=7))
        controller = wf.get_node("stream_controller")
        assert controller is not None
        assert controller.config.get("function") is not None
        # No codegen logic string: from_function leaves `code` unset.
        assert controller.config.get("code") is None

    def test_chunk_size_baked_into_controller_via_closure(self):
        """The build-time ``chunk_size`` is bound through the closure: the
        controller's published plan carries it (no codegen string to grep)."""
        from kaizen.nodes.rag.optimized import _build_streaming_plan

        out = _build_streaming_plan(chunk_size=7)
        assert out["streaming_plan"]["chunk_size"] == 7

    def test_stream_formatter_is_final_sink(self):
        wf = _build(StreamingRAGNode())
        outbound = [c for c in wf.connections if c.source_node == "stream_formatter"]
        assert outbound == []


# ==========================================================================
# BatchOptimizedRAGNode — graph shape (S2: migrated to from_function)
# ==========================================================================


class TestBatchOptimizedGraphShape:
    """The batch workflow wires 3 from_function nodes (S2 migration)."""

    def test_graph_has_three_nodes(self):
        wf = _build(BatchOptimizedRAGNode())
        assert set(wf.nodes.keys()) == {
            "batch_organizer",
            "batch_processor",
            "result_formatter",
        }

    def test_organizer_feeds_processor_and_formatter_via_result_port(self):
        """Post-migration: the organizer publishes on the flat ``result`` port,
        so both downstream edges read ``result.batch_plan`` (the latent #1117
        nested-port defect, now closed)."""
        wf = _build(BatchOptimizedRAGNode())
        organizer_edges = [
            c for c in wf.connections if c.source_node == "batch_organizer"
        ]
        targets = {c.target_node for c in organizer_edges}
        assert {"batch_processor", "result_formatter"}.issubset(targets)
        assert all(c.source_output == "result.batch_plan" for c in organizer_edges)

    def test_processor_feeds_formatter_via_result_port(self):
        wf = _build(BatchOptimizedRAGNode())
        edges = [
            c
            for c in wf.connections
            if c.source_node == "batch_processor"
            and c.target_node == "result_formatter"
        ]
        assert len(edges) == 1
        assert edges[0].source_output == "result.batch_results"

    def test_batch_organizer_is_from_function_node(self):
        """Post-migration: batch_organizer wraps a real function (no codegen
        ``code`` string with logic)."""
        wf = _build(BatchOptimizedRAGNode(batch_size=8))
        organizer = wf.get_node("batch_organizer")
        assert organizer is not None
        assert organizer.config.get("function") is not None
        # No codegen logic string: from_function leaves `code` unset.
        assert organizer.config.get("code") is None

    def test_batch_size_baked_into_organizer_via_closure(self):
        """The build-time ``batch_size`` is bound through the closure: the
        organizer's published plan carries it (no codegen string to grep)."""
        from kaizen.nodes.rag.optimized import _organize_batches

        out = _organize_batches(queries=["a", "b", "c"], batch_size=8)
        assert out["batch_plan"]["batch_size"] == 8

    def test_result_formatter_is_final_sink(self):
        wf = _build(BatchOptimizedRAGNode())
        outbound = [c for c in wf.connections if c.source_node == "result_formatter"]
        assert outbound == []


# ==========================================================================
# Module-level __all__ contract
# ==========================================================================


def test_module_all_exports_four_classes():
    """The module exports exactly the 4 documented classes."""
    from kaizen.nodes.rag import optimized

    assert set(optimized.__all__) == {
        "CacheOptimizedRAGNode",
        "AsyncParallelRAGNode",
        "StreamingRAGNode",
        "BatchOptimizedRAGNode",
    }

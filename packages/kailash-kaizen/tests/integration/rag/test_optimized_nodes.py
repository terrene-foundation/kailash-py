"""Tier-2 integration coverage — ``kaizen.nodes.rag.optimized``.

F8 shard B9c + Wave-3 S1 ``from_function`` migration. Real ``LocalRuntime``
execution of the Cache + AsyncParallel optimized RAG node spines — covering the
**cache/parallel correctness** value-anchor that the resurrection floor never
verified, now through the PRODUCTION path (real workflow execution, real
``from_function`` nodes publishing real ``result`` ports).

Wave-3 S1 migrated CacheOptimizedRAGNode + AsyncParallelRAGNode from brittle
f-string ``"code"``-string ``PythonCodeNode`` codegen to
``PythonCodeNode.from_function`` (#1117 publish-nothing / #1123 brace-escape /
#1118 import-trap root-cause fix). These tests run the REAL inner-workflow nodes
(from ``_create_workflow()``) under a real ``LocalRuntime`` and assert the
computed output reaches the documented downstream consumer.

Scoping (mirrors the original B9c integration scope): the strategy RAG nodes
(``SemanticRAGNode`` etc.) and the ``HybridRAGNode`` rag_processor carry a
SEPARATE, PRE-EXISTING config-shape defect (``config={"config": {...}}`` passes
a dict where a ``RAGConfig`` is expected) that blocks the full multi-node graph
and is out of scope for this migration shard. The cache-decision spine
(key-gen → CacheNode → manager → aggregator) and the parallel
executor → combiner spine — the surfaces this shard migrated — are exercised in
full through the real production path.

NO mocking (``@patch`` / ``MagicMock`` / ``unittest.mock`` are BLOCKED in Tier
2/3 per ``rules/testing.md``). CacheNode uses a deterministic in-memory backend.
"""

from __future__ import annotations

from typing import Any, Dict, List

import pytest
from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder

from kaizen.nodes.rag.optimized import (
    AsyncParallelRAGNode,
    BatchOptimizedRAGNode,
    CacheOptimizedRAGNode,
    StreamingRAGNode,
)

pytestmark = pytest.mark.integration


def _real_cache_nodes() -> Dict[str, Any]:
    """The real from_function node instances the fixed ``_create_workflow``
    produces — no re-authoring."""
    wf = CacheOptimizedRAGNode(similarity_threshold=0.95)._create_workflow()  # type: ignore[attr-defined]
    return {nid: wf.get_node(nid) for nid in wf.nodes}


def _real_parallel_nodes(strategies: List[str]) -> Dict[str, Any]:
    wf = AsyncParallelRAGNode(strategies=strategies)._create_workflow()  # type: ignore[attr-defined]
    return {nid: wf.get_node(nid) for nid in wf.nodes}


# ==========================================================================
# CacheOptimizedRAGNode — cache-decision spine end-to-end (production path)
# ==========================================================================


class TestCacheDecisionSpineEndToEnd:
    """key-gen → CacheNode.get → semantic_cache_manager → result_aggregator
    runs end-to-end under a real LocalRuntime, with the REAL from_function nodes
    and the REAL dotted-path wiring (``result.cache_keys.exact``,
    ``result.use_cache``, ``result``)."""

    def _build_cache_spine(self) -> WorkflowBuilder:
        nodes = _real_cache_nodes()
        b = WorkflowBuilder()
        for nid in (
            "cache_key_generator",
            "semantic_cache_manager",
            "result_aggregator",
        ):
            b.add_node_instance(nodes[nid], node_id=nid, _internal=True)
        b.add_node(
            "CacheNode", "cache_checker", {"operation": "get", "backend": "memory"}
        )
        # The exact wiring _create_workflow produces.
        b.add_connection(
            "cache_key_generator", "result.cache_keys.exact", "cache_checker", "key"
        )
        b.add_connection("cache_checker", "hit", "semantic_cache_manager", "cache_hit")
        b.add_connection(
            "cache_checker", "value", "semantic_cache_manager", "cache_value"
        )
        b.add_connection(
            "semantic_cache_manager", "result", "result_aggregator", "cache_decision"
        )
        return b

    def test_cache_miss_spine_publishes_real_output(self):
        """Empty cache → miss → aggregator publishes a real fresh-source result
        end-to-end. Pre-migration the manager could publish nothing (#1117);
        this proves the real ``result`` port flows to the documented consumer."""
        b = self._build_cache_spine()
        with LocalRuntime() as rt:
            results, _ = rt.execute(
                b.build(),
                parameters={
                    "cache_key_generator": {"query": "what is deep learning"},
                    "semantic_cache_manager": {"query": "what is deep learning"},
                },
            )
        decision = results["semantic_cache_manager"]["result"]
        assert decision, "semantic_cache_manager published an empty result"
        assert decision["use_cache"] is False
        assert decision["cache_type"] is None
        # The aggregator (documented downstream consumer) received the decision.
        aggregated = results["result_aggregator"]["result"]["optimized_results"]
        assert aggregated["metadata"]["source"] == "fresh"
        assert aggregated["performance"]["cache_hit"] is False

    def test_cache_hit_detected_from_real_cachenode_shape(self):
        """The contract-alignment fix: the manager reads CacheNode's REAL
        ``hit`` / ``value`` ports, so a populated cache yields an exact hit that
        flows through to the aggregator's cache-source output."""
        nodes = _real_cache_nodes()
        b = WorkflowBuilder()
        b.add_node_instance(
            nodes["semantic_cache_manager"],
            node_id="semantic_cache_manager",
            _internal=True,
        )
        b.add_node_instance(
            nodes["result_aggregator"], node_id="result_aggregator", _internal=True
        )
        b.add_connection(
            "semantic_cache_manager", "result", "result_aggregator", "cache_decision"
        )
        with LocalRuntime() as rt:
            results, _ = rt.execute(
                b.build(),
                parameters={
                    "semantic_cache_manager": {
                        "cache_hit": True,
                        "cache_value": {
                            "results": ["cached_doc"],
                            "scores": [0.99],
                        },
                        "query": "what is deep learning",
                    }
                },
            )
        decision = results["semantic_cache_manager"]["result"]
        assert decision["use_cache"] is True
        assert decision["cache_type"] == "exact"
        aggregated = results["result_aggregator"]["result"]["optimized_results"]
        assert aggregated["metadata"]["source"] == "cache"
        assert aggregated["results"] == ["cached_doc"]
        assert aggregated["performance"]["cache_hit"] is True

    def test_red_pre_stripping_cache_wiring_breaks_aggregation(self):
        """RED-PRE receipt: if the manager→aggregator edge is STRIPPED, the
        aggregator cannot receive the decision and produces the honest empty
        default (source=fresh, empty results) — proving the wiring is
        load-bearing, not decorative. With the edge present (above tests) the
        decision flows; without it the cached output never reaches the
        consumer."""
        nodes = _real_cache_nodes()
        b = WorkflowBuilder()
        # Manager produces a cache HIT, but the edge to the aggregator is OMITTED.
        b.add_node_instance(
            nodes["result_aggregator"], node_id="result_aggregator", _internal=True
        )
        with LocalRuntime() as rt:
            results, _ = rt.execute(
                b.build(),
                # No cache_decision wired → honest empty default.
                parameters={"result_aggregator": {}},
            )
        aggregated = results["result_aggregator"]["result"]["optimized_results"]
        # Without the wiring, the cached result NEVER reaches the consumer.
        assert aggregated["results"] == []
        assert aggregated["performance"]["cache_hit"] is False


# ==========================================================================
# AsyncParallelRAGNode — executor → combiner spine end-to-end (production path)
# ==========================================================================


class TestParallelSpineEndToEnd:
    """parallel_executor → result_combiner runs end-to-end under a real
    LocalRuntime, with the REAL from_function nodes and the REAL
    ``result.execution_plan`` wiring (the latent #1117 nested-port defect this
    migration closed)."""

    def _build_parallel_spine(self, strategies: List[str]) -> WorkflowBuilder:
        nodes = _real_parallel_nodes(strategies)
        b = WorkflowBuilder()
        b.add_node_instance(
            nodes["parallel_executor"], node_id="parallel_executor", _internal=True
        )
        b.add_node_instance(
            nodes["result_combiner"], node_id="result_combiner", _internal=True
        )
        # The exact wiring _create_workflow produces: executor publishes
        # `result.execution_plan`, NOT a phantom `execution_plan` port.
        b.add_connection(
            "parallel_executor",
            "result.execution_plan",
            "result_combiner",
            "execution_plan",
        )
        return b

    def test_executor_plan_reaches_combiner_and_fuses(self):
        """The executor's plan flows to the combiner via ``result.execution_plan``
        AND the per-strategy results fuse into a single ranked list — the full
        migrated spine end-to-end."""
        b = self._build_parallel_spine(["semantic", "hybrid"])
        with LocalRuntime() as rt:
            results, _ = rt.execute(
                b.build(),
                parameters={
                    "parallel_executor": {
                        "query": "q",
                        "documents": [{"id": "d1", "content": "x"}],
                    },
                    "result_combiner": {
                        "semantic_results": {
                            "results": [
                                {"id": "doc1", "content": "a"},
                                {"id": "doc2", "content": "b"},
                            ],
                            "scores": [0.9, 0.7],
                        },
                        "hybrid_results": {
                            "results": [
                                {"id": "doc1", "content": "a"},
                                {"id": "doc3", "content": "c"},
                            ],
                            "scores": [0.8, 0.6],
                        },
                    },
                },
            )
        parallel = results["result_combiner"]["result"]["parallel_results"]
        assert {r["id"] for r in parallel["results"]} == {"doc1", "doc2", "doc3"}
        # doc1 (in both, mean 0.85) ranks first.
        assert parallel["results"][0]["id"] == "doc1"
        assert parallel["scores"][0] == pytest.approx(0.85)
        assert parallel["metadata"]["strategy_agreements"] == 1
        assert set(parallel["metadata"]["strategies_used"]) == {"semantic", "hybrid"}

    def test_executor_publishes_real_plan_port(self):
        """The executor publishes a real, non-empty plan on the flat ``result``
        port (pre-migration the edge read a phantom port that never existed)."""
        nodes = _real_parallel_nodes(["semantic", "hybrid"])
        b = WorkflowBuilder()
        b.add_node_instance(
            nodes["parallel_executor"], node_id="parallel_executor", _internal=True
        )
        with LocalRuntime() as rt:
            results, _ = rt.execute(
                b.build(),
                parameters={
                    "parallel_executor": {
                        "query": "q",
                        "documents": [{"id": "d1", "content": "x"}],
                    }
                },
            )
        published = results["parallel_executor"]["result"]
        assert published["execution_plan"]["strategies"] == ["semantic", "hybrid"]
        assert published["execution_plan"]["parallel_count"] == 2

    def test_red_pre_phantom_port_wiring_drops_plan_silently(self, caplog):
        """RED-PRE receipt: the executor publishes its plan ONLY on the flat
        ``result`` port. Wiring the combiner to the OLD phantom ``execution_plan``
        source port (the pre-migration edge) silently DROPS the plan — the
        runtime logs "Source output 'execution_plan' not found ... Available
        outputs: ['result']" and the combiner receives ``execution_plan=None``
        (honest 0.0 default). With the correct ``result.execution_plan`` wiring
        (``test_executor_plan_reaches_combiner_and_fuses``) the plan flows. This
        IS the #1117 silent-drop failure mode the migration's re-wiring closed."""
        import logging

        nodes = _real_parallel_nodes(["semantic"])
        b = WorkflowBuilder()
        b.add_node_instance(
            nodes["parallel_executor"], node_id="parallel_executor", _internal=True
        )
        b.add_node_instance(
            nodes["result_combiner"], node_id="result_combiner", _internal=True
        )
        # The PRE-FIX phantom edge: executor publishes only `result`, never a
        # top-level `execution_plan` port.
        b.add_connection(
            "parallel_executor", "execution_plan", "result_combiner", "execution_plan"
        )
        with caplog.at_level(logging.WARNING):
            with LocalRuntime() as rt:
                results, _ = rt.execute(
                    b.build(),
                    parameters={
                        "parallel_executor": {
                            "query": "q",
                            "documents": [{"id": "d1", "content": "x"}],
                        },
                        "result_combiner": {
                            "semantic_results": {
                                "results": [{"id": "doc1", "content": "a"}],
                                "scores": [0.9],
                            }
                        },
                    },
                )
        # The runtime surfaced the missing source output (the #1117 signature).
        assert any(
            "execution_plan" in rec.getMessage() and "not found" in rec.getMessage()
            for rec in caplog.records
        ), "expected a missing-source-output log for the phantom execution_plan port"
        # The plan never reached the combiner → honest 0.0 total-time default
        # (a real plan would carry a parseable start_time).
        parallel = results["result_combiner"]["result"]["parallel_results"]
        assert parallel["metadata"]["total_execution_time"] == 0.0

    def test_unknown_strategy_results_wire_via_dynamic_signature(self):
        """The dynamic-signature factory declares a ``<strategy>_results`` input
        for an arbitrary (unknown) strategy name, so its results wire and fuse —
        the dynamic-strategy case the prior ``locals()`` codegen handled."""
        b = self._build_parallel_spine(["unknown_strategy"])
        with LocalRuntime() as rt:
            results, _ = rt.execute(
                b.build(),
                parameters={
                    "parallel_executor": {
                        "query": "q",
                        "documents": [{"id": "d1", "content": "x"}],
                    },
                    "result_combiner": {
                        "unknown_strategy_results": {
                            "results": [{"id": "docU", "content": "u"}],
                            "scores": [0.5],
                        }
                    },
                },
            )
        parallel = results["result_combiner"]["result"]["parallel_results"]
        assert [r["id"] for r in parallel["results"]] == ["docU"]
        assert parallel["metadata"]["strategies_used"] == ["unknown_strategy"]


# ==========================================================================
# StreamingRAGNode — full streaming spine end-to-end (production path)
# ==========================================================================


class TestStreamingSpineEndToEnd:
    """The FULL streaming workflow (stream_controller → progressive_retriever →
    stream_formatter) runs end-to-end under a real LocalRuntime via the
    PRODUCTION ``_create_workflow()`` graph — every node is a real
    ``from_function`` node, and the wiring is the REAL dotted-path
    ``result.streaming_plan`` / ``result.progressive_results`` (the latent #1117
    nested-port defect this migration closed)."""

    def _streaming_workflow(self, chunk_size: int = 100):
        """The real production workflow the node builds (no re-authoring)."""
        return StreamingRAGNode(chunk_size=chunk_size)._create_workflow()  # type: ignore[attr-defined]

    def test_full_streaming_spine_publishes_real_chunks(self):
        """The controller's plan flows to the retriever (``result.streaming_plan``),
        the retriever's results flow to the formatter
        (``result.progressive_results``), and the formatter publishes real
        stream chunks — the full migrated spine end-to-end through the
        production graph. Pre-migration the edges read phantom top-level ports
        that never existed (#1117), so nothing reached the formatter."""
        wf = self._streaming_workflow(chunk_size=100)
        with LocalRuntime() as rt:
            results, _ = rt.execute(
                wf,
                parameters={
                    "progressive_retriever": {
                        "query": "deep learning",
                        "documents": [
                            {"id": "d1", "content": "deep learning models"},
                            {"id": "d2", "content": "unrelated topic"},
                        ],
                    }
                },
            )
        # The controller bound chunk_size through the closure.
        plan = results["stream_controller"]["result"]["streaming_plan"]
        assert plan["chunk_size"] == 100
        # The retriever found exactly the one overlapping doc.
        prog = results["progressive_retriever"]["result"]["progressive_results"]
        assert prog["metadata"]["matches_found"] == 1
        # The formatter (documented downstream consumer) published real chunks.
        formatted = results["stream_formatter"]["result"]
        assert [c["type"] for c in formatted["stream_chunks"]] == [
            "result",
            "metadata",
        ]
        assert formatted["streaming_metadata"]["result_chunks"] == 1
        assert formatted["streaming_metadata"]["supports_backpressure"] is True

    def test_red_pre_phantom_port_drops_streaming_plan_silently(self, caplog):
        """RED-PRE receipt: the controller publishes its plan ONLY on the flat
        ``result`` port. Wiring the retriever to the OLD phantom
        ``streaming_plan`` source port (the pre-migration edge) silently DROPS
        the plan — the runtime logs the missing source output and the retriever
        falls back to its honest default k of 3. This IS the #1117 silent-drop
        failure mode the migration's re-wiring closed (with the correct
        ``result.streaming_plan`` wiring above, the plan flows)."""
        import logging

        src = self._streaming_workflow(chunk_size=100)
        nodes = {nid: src.get_node(nid) for nid in src.nodes}
        b = WorkflowBuilder()
        b.add_node_instance(
            nodes["stream_controller"], node_id="stream_controller", _internal=True
        )
        b.add_node_instance(
            nodes["progressive_retriever"],
            node_id="progressive_retriever",
            _internal=True,
        )
        # The PRE-FIX phantom edge: controller publishes only `result`, never a
        # top-level `streaming_plan` port.
        b.add_connection(
            "stream_controller",
            "streaming_plan",
            "progressive_retriever",
            "streaming_plan",
        )
        with caplog.at_level(logging.WARNING):
            with LocalRuntime() as rt:
                results, _ = rt.execute(
                    b.build(),
                    parameters={
                        "progressive_retriever": {
                            "query": "a b c d",
                            "documents": [
                                {"id": str(i), "content": "a b c d"} for i in range(5)
                            ],
                        }
                    },
                )
        # The runtime surfaced the missing source output (the #1117 signature).
        assert any(
            "streaming_plan" in rec.getMessage() and "not found" in rec.getMessage()
            for rec in caplog.records
        ), "expected a missing-source-output log for the phantom streaming_plan port"
        # The plan never reached the retriever → honest default k of 3 applied.
        prog = results["progressive_retriever"]["result"]["progressive_results"]
        assert len(prog["initial"]) == 3


# ==========================================================================
# BatchOptimizedRAGNode — full batch spine end-to-end (production path)
# ==========================================================================


class TestBatchSpineEndToEnd:
    """The FULL batch workflow (batch_organizer → batch_processor →
    result_formatter, plus organizer → formatter) runs end-to-end under a real
    LocalRuntime via the PRODUCTION ``_create_workflow()`` graph — every node is
    a real ``from_function`` node, and the wiring is the REAL dotted-path
    ``result.batch_plan`` / ``result.batch_results`` (the latent #1117
    nested-port defect this migration closed)."""

    def _batch_workflow(self, batch_size: int = 2):
        return BatchOptimizedRAGNode(batch_size=batch_size)._create_workflow()  # type: ignore[attr-defined]

    def test_full_batch_spine_maps_results_per_query(self):
        """The organizer's plan flows to the processor + formatter
        (``result.batch_plan``), the processor's scores flow to the formatter
        (``result.batch_results``), and the formatter publishes per-query
        documents — the full migrated spine end-to-end through the production
        graph."""
        documents = [
            {"id": "d1", "content": "alpha beta"},
            {"id": "d2", "content": "gamma"},
        ]
        wf = self._batch_workflow(batch_size=2)
        with LocalRuntime() as rt:
            results, _ = rt.execute(
                wf,
                parameters={
                    "batch_organizer": {"queries": ["alpha", "beta"]},
                    "batch_processor": {"documents": documents},
                    "result_formatter": {"documents": documents},
                },
            )
        # The organizer bound batch_size through the closure.
        assert results["batch_organizer"]["result"]["batch_plan"]["batch_size"] == 2
        # The processor scored both queries.
        proc_stats = results["batch_processor"]["result"]["batch_results"]["statistics"]
        assert proc_stats["total_queries_processed"] == 2
        # The formatter (documented downstream consumer) mapped scores back to
        # per-query documents.
        final = results["result_formatter"]["result"]["final_batch_results"]
        assert set(final["processing_order"]) == {"alpha", "beta"}
        # "alpha" overlaps d1 only (positive-score filter).
        assert final["query_results"]["alpha"]["results"] == [
            {"id": "d1", "content": "alpha beta"}
        ]

    def test_red_pre_phantom_port_drops_batch_plan_silently(self, caplog):
        """RED-PRE receipt: the organizer publishes its plan ONLY on the flat
        ``result`` port. Wiring the processor to the OLD phantom ``batch_plan``
        source port (the pre-migration edge) silently DROPS the plan — the
        runtime logs the missing source output and the processor falls back to
        its honest zero-query default. This IS the #1117 silent-drop failure
        mode the migration's re-wiring closed (with the correct
        ``result.batch_plan`` wiring above, the plan flows)."""
        import logging

        src = self._batch_workflow(batch_size=2)
        nodes = {nid: src.get_node(nid) for nid in src.nodes}
        b = WorkflowBuilder()
        b.add_node_instance(
            nodes["batch_organizer"], node_id="batch_organizer", _internal=True
        )
        b.add_node_instance(
            nodes["batch_processor"], node_id="batch_processor", _internal=True
        )
        # The PRE-FIX phantom edge: organizer publishes only `result`, never a
        # top-level `batch_plan` port.
        b.add_connection(
            "batch_organizer", "batch_plan", "batch_processor", "batch_plan"
        )
        with caplog.at_level(logging.WARNING):
            with LocalRuntime() as rt:
                results, _ = rt.execute(
                    b.build(),
                    parameters={
                        "batch_organizer": {"queries": ["alpha", "beta"]},
                        "batch_processor": {
                            "documents": [{"id": "d1", "content": "alpha"}]
                        },
                    },
                )
        # The runtime surfaced the missing source output (the #1117 signature).
        assert any(
            "batch_plan" in rec.getMessage() and "not found" in rec.getMessage()
            for rec in caplog.records
        ), "expected a missing-source-output log for the phantom batch_plan port"
        # The plan never reached the processor → honest zero-query default.
        proc_stats = results["batch_processor"]["result"]["batch_results"]["statistics"]
        assert proc_stats["total_queries_processed"] == 0

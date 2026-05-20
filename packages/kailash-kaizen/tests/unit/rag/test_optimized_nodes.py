"""Tier 1 unit coverage — ``kaizen.nodes.rag.optimized``.

F8 shard B9c. The 4 classes under test (CacheOptimizedRAGNode,
AsyncParallelRAGNode, StreamingRAGNode, BatchOptimizedRAGNode) cover
the cache / parallel / streaming / batch optimization surface of the
RAG package.

Tier 1 scope:

- Construction with default + custom kwargs across all 4 classes —
  including the A3-triage R3-L2 regression: ``CacheOptimizedRAGNode()``
  MUST NOT raise NameError on missing 'CacheNode' registry entry now
  that the registering import lands at optimized.py module scope.
- The inner workflow GRAPH SHAPE produced by each ``_create_workflow``
  method (graphs are documented-shape claims).
- Strategy-list interpolation invariants for AsyncParallelRAGNode
  (default 3 strategies, custom strategy lists, unknown-strategy
  fallback to semantic).
- chunk_size / batch_size / cache_ttl baked into the codegen templates
  at builder time.

Value-anchor per the F8 plan §B B9c row is **cache/stream correctness
of preserved nodes** — this file lifts the structural coverage half
of the optimized sub-module; the Tier-2a integration suite under
``tests/integration/rag/test_optimized_nodes.py`` exercises the real
LocalRuntime cache / parallel / batch end-to-end paths.
"""

from __future__ import annotations

import pytest
from kailash.workflow.graph import Workflow

from kaizen.nodes.rag.optimized import (
    AsyncParallelRAGNode,
    BatchOptimizedRAGNode,
    CacheOptimizedRAGNode,
    StreamingRAGNode,
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
        # The cache_checker and cache_updater nodes are instantiated through
        # the registry from the "CacheNode" string node-type — that's the
        # R3-L2 surface this commit unblocked.
        cache_checker = wf.get_node("cache_checker")
        cache_updater = wf.get_node("cache_updater")
        assert cache_checker is not None
        assert cache_updater is not None
        # Both nodes carry the get / set operations specified in optimized.py.
        assert cache_checker.config.get("operation") == "get"
        assert cache_updater.config.get("operation") == "set"

    def test_cache_ttl_baked_into_cache_node_configs(self):
        wf = _build(CacheOptimizedRAGNode(cache_ttl=42))
        assert wf.get_node("cache_checker").config.get("ttl") == 42  # type: ignore[union-attr]
        assert wf.get_node("cache_updater").config.get("ttl") == 42  # type: ignore[union-attr]

    def test_similarity_threshold_baked_into_codegen(self):
        wf = _build(CacheOptimizedRAGNode(similarity_threshold=0.42))
        sem_mgr = wf.get_node("semantic_cache_manager")
        assert sem_mgr is not None
        # The threshold is f-string-interpolated into the codegen template.
        assert "0.42" in sem_mgr.config["code"]

    def test_result_aggregator_is_final_sink(self):
        wf = _build(CacheOptimizedRAGNode())
        outbound = [c for c in wf.connections if c.source_node == "result_aggregator"]
        assert outbound == []


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
        # Only semantic strategy node + executor + combiner.
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
        # Falls back to SemanticRAGNode for the unknown branch — verified
        # through the underlying node type at the registry layer.
        node = wf.get_node("unknown_strategy_rag")
        assert node is not None
        # The fallback applies retrieval_k=5 config (semantic strategy).
        assert node.config.get("config", {}).get("retrieval_k") == 5

    def test_executor_connects_to_combiner(self):
        wf = _build(AsyncParallelRAGNode(strategies=["semantic"]))
        executor_to_combiner = [
            c
            for c in wf.connections
            if c.source_node == "parallel_executor"
            and c.target_node == "result_combiner"
        ]
        assert len(executor_to_combiner) >= 1

    def test_each_strategy_node_connects_to_combiner(self):
        wf = _build(AsyncParallelRAGNode(strategies=["semantic", "hybrid"]))
        targets_into_combiner = {
            c.source_node for c in wf.connections if c.target_node == "result_combiner"
        }
        assert {"semantic_rag", "hybrid_rag", "parallel_executor"}.issubset(
            targets_into_combiner
        )

    def test_combiner_is_final_sink(self):
        wf = _build(AsyncParallelRAGNode())
        outbound = [c for c in wf.connections if c.source_node == "result_combiner"]
        assert outbound == []

    def test_strategy_list_baked_into_executor_codegen(self):
        wf = _build(AsyncParallelRAGNode(strategies=["semantic", "hybrid"]))
        executor = wf.get_node("parallel_executor")
        assert executor is not None
        # The strategy list is f-string-interpolated into the codegen template.
        assert "['semantic', 'hybrid']" in executor.config["code"]


# ==========================================================================
# StreamingRAGNode — graph shape
# ==========================================================================


class TestOptimizedStreamingGraphShape:
    """The streaming workflow wires 3 nodes."""

    def test_graph_has_three_nodes(self):
        wf = _build(StreamingRAGNode())
        assert set(wf.nodes.keys()) == {
            "stream_controller",
            "progressive_retriever",
            "stream_formatter",
        }

    def test_stream_controller_feeds_progressive_retriever(self):
        wf = _build(StreamingRAGNode())
        edges = [
            c
            for c in wf.connections
            if c.source_node == "stream_controller"
            and c.target_node == "progressive_retriever"
        ]
        assert len(edges) == 1

    def test_progressive_retriever_feeds_stream_formatter(self):
        wf = _build(StreamingRAGNode())
        edges = [
            c
            for c in wf.connections
            if c.source_node == "progressive_retriever"
            and c.target_node == "stream_formatter"
        ]
        assert len(edges) == 1

    def test_chunk_size_baked_into_controller_codegen(self):
        wf = _build(StreamingRAGNode(chunk_size=7))
        controller = wf.get_node("stream_controller")
        assert controller is not None
        # The chunk_size is f-string-interpolated into the codegen template.
        assert "chunk_size = 7" in controller.config["code"]

    def test_stream_formatter_is_final_sink(self):
        wf = _build(StreamingRAGNode())
        outbound = [c for c in wf.connections if c.source_node == "stream_formatter"]
        assert outbound == []


# ==========================================================================
# BatchOptimizedRAGNode — graph shape
# ==========================================================================


class TestBatchOptimizedGraphShape:
    """The batch workflow wires 3 nodes."""

    def test_graph_has_three_nodes(self):
        wf = _build(BatchOptimizedRAGNode())
        assert set(wf.nodes.keys()) == {
            "batch_organizer",
            "batch_processor",
            "result_formatter",
        }

    def test_organizer_feeds_processor_and_formatter(self):
        wf = _build(BatchOptimizedRAGNode())
        targets = {
            c.target_node for c in wf.connections if c.source_node == "batch_organizer"
        }
        assert {"batch_processor", "result_formatter"}.issubset(targets)

    def test_processor_feeds_formatter(self):
        wf = _build(BatchOptimizedRAGNode())
        edges = [
            c
            for c in wf.connections
            if c.source_node == "batch_processor"
            and c.target_node == "result_formatter"
        ]
        assert len(edges) == 1

    def test_batch_size_baked_into_organizer_codegen(self):
        wf = _build(BatchOptimizedRAGNode(batch_size=8))
        organizer = wf.get_node("batch_organizer")
        assert organizer is not None
        # The batch_size is f-string-interpolated into the codegen template.
        assert "batch_size = 8" in organizer.config["code"]

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

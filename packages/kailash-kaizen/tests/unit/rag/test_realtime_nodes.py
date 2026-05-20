"""Tier 1 unit coverage — ``kaizen.nodes.rag.realtime``.

F8 shard B9c. The 3 classes under test (RealtimeRAGNode,
RealtimeStreamingRAGNode, IncrementalIndexNode) cover the live-data /
streaming / incremental-index surface of the RAG package.

Tier 1 scope:

- Construction with default + custom kwargs across all 3 classes.
- ``get_parameters()`` contracts for the 2 ``Node``-subclass classes.
- The inner workflow GRAPH SHAPE produced by
  ``RealtimeRAGNode._create_workflow`` (4-node fan-in pipeline).
- The deterministic ``run()`` paths on RealtimeStreamingRAGNode (first
  chunk synchronous return shape) and IncrementalIndexNode (add /
  remove / update / search operations against an in-memory index).
- The ``stream()`` async-iterator contract on RealtimeStreamingRAGNode
  (start → chunk* → complete shape, chunk_idx-initialization edge case
  on the max_chunks=0 path).

Value-anchor per the F8 plan §B B9c row is **cache/stream correctness
of preserved nodes** — this file lifts the stream-correctness half of
the realtime sub-module; the Tier-2a integration suite under
``tests/integration/rag/test_realtime_nodes.py`` exercises the real
LocalRuntime path.
"""

from __future__ import annotations

import asyncio
from collections import deque
from typing import Any, Dict, List

import pytest
from kailash.workflow.graph import Workflow

from kaizen.nodes.rag.realtime import (
    IncrementalIndexNode,
    RealtimeRAGNode,
    RealtimeStreamingRAGNode,
)

pytestmark = pytest.mark.unit


def _build(node: RealtimeRAGNode) -> Workflow:
    """Call ``node._create_workflow()`` past the ``@register_node`` Node-type erasure.

    Mirrors the B7/B8/B9a/B9b ``_build`` precedent: ``@register_node()`` erases
    the concrete subclass to ``Node`` for static checkers, so
    ``_create_workflow`` becomes invisible to pyright. The single
    suppression lets every call site stay clean.
    """
    return node._create_workflow()  # type: ignore[attr-defined]


# ==========================================================================
# Construction floor — all three classes
# ==========================================================================


class TestAllThreeConstruct:
    def test_realtime_rag_constructs_default(self):
        node = RealtimeRAGNode()
        assert node is not None
        assert node.metadata.name == "realtime_rag"
        assert node.update_interval == 10.0  # type: ignore[attr-defined]
        assert node.relevance_decay_rate == 0.95  # type: ignore[attr-defined]
        assert node.max_buffer_size == 1000  # type: ignore[attr-defined]

    def test_realtime_rag_constructs_with_custom_kwargs(self):
        node = RealtimeRAGNode(
            name="custom_realtime",
            update_interval=5.0,
            relevance_decay_rate=0.8,
            max_buffer_size=100,
        )
        assert node.metadata.name == "custom_realtime"
        assert node.update_interval == 5.0  # type: ignore[attr-defined]
        assert node.relevance_decay_rate == 0.8  # type: ignore[attr-defined]
        assert node.max_buffer_size == 100  # type: ignore[attr-defined]

    def test_realtime_rag_document_buffer_is_bounded_deque(self):
        node = RealtimeRAGNode(max_buffer_size=3)
        buf = node.document_buffer  # type: ignore[attr-defined]
        assert isinstance(buf, deque)
        assert buf.maxlen == 3

    def test_realtime_streaming_constructs_default(self):
        node = RealtimeStreamingRAGNode()
        assert node is not None
        assert node.metadata.name == "streaming_rag"
        assert node.chunk_size == 50  # type: ignore[attr-defined]
        assert node.chunk_interval == 100  # type: ignore[attr-defined]

    def test_realtime_streaming_constructs_with_custom_kwargs(self):
        node = RealtimeStreamingRAGNode(
            name="custom_stream",
            chunk_size=10,
            chunk_interval=50,
        )
        assert node.metadata.name == "custom_stream"
        assert node.chunk_size == 10  # type: ignore[attr-defined]
        assert node.chunk_interval == 50  # type: ignore[attr-defined]

    def test_incremental_index_constructs_default(self):
        node = IncrementalIndexNode()
        assert node is not None
        assert node.metadata.name == "incremental_index"
        assert node.index_type == "hybrid"  # type: ignore[attr-defined]
        assert node.merge_strategy == "immediate"  # type: ignore[attr-defined]
        assert node.index == {}  # type: ignore[attr-defined]
        assert node.document_store == {}  # type: ignore[attr-defined]

    def test_incremental_index_constructs_with_custom_kwargs(self):
        node = IncrementalIndexNode(
            name="custom_index",
            index_type="inverted",
            merge_strategy="batched",
        )
        assert node.metadata.name == "custom_index"
        assert node.index_type == "inverted"  # type: ignore[attr-defined]
        assert node.merge_strategy == "batched"  # type: ignore[attr-defined]


# ==========================================================================
# get_parameters() contracts — Node-subclass classes
# ==========================================================================


class TestRealtimeStreamingParameters:
    def test_required_parameters(self):
        params = RealtimeStreamingRAGNode().get_parameters()
        assert params["query"].required is True
        assert params["query"].type is str
        assert params["documents"].required is True
        assert params["documents"].type is list

    def test_optional_parameters_with_defaults(self):
        params = RealtimeStreamingRAGNode().get_parameters()
        assert params["name"].required is False
        assert params["chunk_size"].required is False
        assert params["chunk_size"].default == 50
        assert params["chunk_interval"].required is False
        assert params["chunk_interval"].default == 100
        assert params["max_chunks"].required is False
        assert params["max_chunks"].default == 10

    def test_get_parameters_returns_all_documented_keys(self):
        params = RealtimeStreamingRAGNode().get_parameters()
        assert set(params.keys()) == {
            "name",
            "chunk_size",
            "chunk_interval",
            "query",
            "documents",
            "max_chunks",
        }


class TestIncrementalIndexParameters:
    def test_required_parameters(self):
        params = IncrementalIndexNode().get_parameters()
        assert params["operation"].required is True
        assert params["operation"].type is str

    def test_optional_parameters_with_defaults(self):
        params = IncrementalIndexNode().get_parameters()
        assert params["name"].required is False
        assert params["index_type"].required is False
        assert params["index_type"].default == "hybrid"
        assert params["merge_strategy"].required is False
        assert params["merge_strategy"].default == "immediate"
        assert params["documents"].required is False
        assert params["documents"].type is list
        assert params["document_ids"].required is False
        assert params["query"].required is False


# ==========================================================================
# RealtimeRAGNode — inner workflow graph shape
# ==========================================================================


class TestRealtimeRAGGraphShape:
    """The 4-node fan-in pipeline shape."""

    def test_graph_has_four_nodes(self):
        wf = _build(RealtimeRAGNode())
        assert set(wf.nodes.keys()) == {
            "live_monitor",
            "incremental_indexer",
            "time_aware_retriever",
            "stream_formatter",
        }

    def test_live_monitor_feeds_indexer(self):
        wf = _build(RealtimeRAGNode())
        edges = [
            c
            for c in wf.connections
            if c.source_node == "live_monitor"
            and c.target_node == "incremental_indexer"
        ]
        assert len(edges) == 1

    def test_indexer_fans_out_to_retriever_and_formatter(self):
        wf = _build(RealtimeRAGNode())
        targets = {
            c.target_node
            for c in wf.connections
            if c.source_node == "incremental_indexer"
        }
        assert {"time_aware_retriever", "stream_formatter"}.issubset(targets)

    def test_stream_formatter_is_final_sink(self):
        wf = _build(RealtimeRAGNode())
        outbound = [c for c in wf.connections if c.source_node == "stream_formatter"]
        assert outbound == []

    def test_max_buffer_size_baked_into_indexer_template(self):
        wf = _build(RealtimeRAGNode(max_buffer_size=42))
        indexer = wf.get_node("incremental_indexer")
        assert indexer is not None
        # The f-string template interpolates {self.max_buffer_size} into the
        # generated code at builder time.
        assert "max_size=42" in indexer.config["code"]

    def test_relevance_decay_rate_baked_into_retriever_template(self):
        wf = _build(RealtimeRAGNode(relevance_decay_rate=0.8))
        retriever = wf.get_node("time_aware_retriever")
        assert retriever is not None
        assert "decay_rate=0.8" in retriever.config["code"]


# ==========================================================================
# RealtimeStreamingRAGNode.run() — synchronous first-chunk return
# ==========================================================================


class TestRealtimeStreamingRun:
    """The synchronous run() returns the first chunk for compatibility."""

    def test_run_returns_documented_shape(self):
        node = RealtimeStreamingRAGNode(chunk_size=3)
        out = node.run(
            query="machine learning",
            documents=[
                {"content": "machine learning is great"},
                {"content": "deep learning uses neural networks"},
                {"content": "unrelated content"},
            ],
        )
        assert out["streaming_enabled"] is True
        assert "first_chunk" in out
        assert "use_stream_method" in out

    def test_run_first_chunk_picks_overlapping_documents(self):
        node = RealtimeStreamingRAGNode(chunk_size=10)
        out = node.run(
            query="machine learning",
            documents=[
                {"content": "machine learning is great"},
                {"content": "deep learning uses neural networks"},
                {"content": "unrelated content here"},
            ],
        )
        # First chunk only contains docs with score > 0 (overlap with query).
        assert len(out["first_chunk"]) == 2
        for entry in out["first_chunk"]:
            assert "document" in entry
            assert "score" in entry
            assert entry["score"] > 0

    def test_run_empty_query_yields_empty_first_chunk(self):
        node = RealtimeStreamingRAGNode()
        out = node.run(query="", documents=[{"content": "anything"}])
        # With no query words, every score is 0; nothing makes the cut.
        assert out["first_chunk"] == []

    def test_run_respects_chunk_size_limit(self):
        node = RealtimeStreamingRAGNode(chunk_size=2)
        out = node.run(
            query="x",
            documents=[
                {"content": "x"},
                {"content": "x"},
                {"content": "x"},
                {"content": "x"},
            ],
        )
        # chunk_size=2 → the first chunk scans 2 docs only.
        assert len(out["first_chunk"]) <= 2


# ==========================================================================
# RealtimeStreamingRAGNode.stream() — async iterator contract
# ==========================================================================


def _drain_stream(node: RealtimeStreamingRAGNode, **kwargs) -> List[Dict[str, Any]]:
    """Drain the async iterator synchronously via a fresh loop."""

    async def _collect() -> List[Dict[str, Any]]:
        acc: List[Dict[str, Any]] = []
        async for chunk in node.stream(**kwargs):  # type: ignore[attr-defined]
            acc.append(chunk)
        return acc

    return asyncio.run(_collect())


class TestRealtimeStreamingStream:
    """The async stream() emits start → chunk* → complete with documented shape."""

    def test_stream_emits_start_chunk_complete_sequence(self):
        node = RealtimeStreamingRAGNode(chunk_size=2, chunk_interval=0)
        chunks = _drain_stream(
            node,
            query="machine learning",
            documents=[
                {"content": "machine learning rocks"},
                {"content": "deep learning is similar"},
                {"content": "unrelated"},
            ],
            max_chunks=5,
        )
        # First is start, last is complete.
        assert chunks[0]["type"] == "start"
        assert chunks[-1]["type"] == "complete"
        # Middle chunks are type=chunk.
        for c in chunks[1:-1]:
            assert c["type"] == "chunk"

    def test_stream_start_carries_query_and_estimated_results(self):
        node = RealtimeStreamingRAGNode(chunk_size=2, chunk_interval=0)
        chunks = _drain_stream(
            node,
            query="ml",
            documents=[{"content": "ml is here"}],
            max_chunks=3,
        )
        start = chunks[0]
        assert start["query"] == "ml"
        # estimated_results = min(len(documents), max_chunks * chunk_size)
        assert start["estimated_results"] == 1  # min(1, 3*2) == 1

    def test_stream_chunk_carries_results_progress_and_chunk_id(self):
        node = RealtimeStreamingRAGNode(chunk_size=2, chunk_interval=0)
        chunks = _drain_stream(
            node,
            query="ml",
            documents=[
                {"content": "ml one"},
                {"content": "ml two"},
                {"content": "ml three"},
            ],
            max_chunks=3,
        )
        mid_chunks = [c for c in chunks if c["type"] == "chunk"]
        assert len(mid_chunks) >= 1
        first_chunk = mid_chunks[0]
        assert first_chunk["chunk_id"] == 0
        assert "results" in first_chunk
        assert "progress" in first_chunk
        # Every result entry has document + score + position fields.
        for r in first_chunk["results"]:
            assert "document" in r
            assert "score" in r
            assert "position" in r

    def test_stream_complete_carries_total_results_and_chunks_sent(self):
        node = RealtimeStreamingRAGNode(chunk_size=2, chunk_interval=0)
        chunks = _drain_stream(
            node,
            query="ml",
            documents=[
                {"content": "ml a"},
                {"content": "ml b"},
                {"content": "ml c"},
            ],
            max_chunks=5,
        )
        complete = chunks[-1]
        assert complete["type"] == "complete"
        assert "total_results" in complete
        assert complete["total_results"] == 3
        assert "chunks_sent" in complete
        assert "processing_time" in complete

    def test_stream_max_chunks_zero_no_chunk_iteration(self):
        """B9c regression: chunk_idx=0 init when max_chunks=0 prevents UnboundLocalError."""
        node = RealtimeStreamingRAGNode(chunk_size=2, chunk_interval=0)
        chunks = _drain_stream(
            node,
            query="ml",
            documents=[{"content": "ml here"}],
            max_chunks=0,
        )
        # Only start + complete; no chunk-type yields.
        types = [c["type"] for c in chunks]
        assert "chunk" not in types
        # Complete still emits; processing_time = chunk_idx (0) * interval = 0.
        assert chunks[-1]["type"] == "complete"
        assert chunks[-1]["processing_time"] == 0

    def test_stream_no_matching_documents_breaks_early(self):
        node = RealtimeStreamingRAGNode(chunk_size=2, chunk_interval=0)
        chunks = _drain_stream(
            node,
            query="zzz",
            documents=[
                {"content": "no overlap"},
                {"content": "still no overlap"},
            ],
            max_chunks=5,
        )
        # No chunks emitted (scored_docs is empty after filtering).
        types = [c["type"] for c in chunks]
        assert types.count("chunk") == 0
        assert chunks[-1]["type"] == "complete"


# ==========================================================================
# IncrementalIndexNode.run() — operation dispatch + state mutations
# ==========================================================================


class TestIncrementalIndexRun:
    """Each operation mutates the index/document_store + returns documented shape."""

    def test_run_unknown_operation_returns_error(self):
        node = IncrementalIndexNode()
        out = node.run(operation="bogus_op")
        assert "error" in out
        assert "Unknown operation" in out["error"]

    def test_run_add_inserts_documents_into_store(self):
        node = IncrementalIndexNode()
        out = node.run(
            operation="add",
            documents=[
                {"id": "doc1", "content": "hello world"},
                {"id": "doc2", "content": "world foo"},
            ],
        )
        assert out["operation"] == "add"
        assert out["documents_added"] == 2
        assert out["total_documents"] == 2
        assert node.document_store["doc1"]["content"] == "hello world"  # type: ignore[attr-defined]
        assert node.document_store["doc2"]["content"] == "world foo"  # type: ignore[attr-defined]
        # Inverted index has "world" → both docs.
        assert node.index["world"] == {"doc1", "doc2"}  # type: ignore[attr-defined]

    def test_run_add_auto_assigns_id_if_missing(self):
        node = IncrementalIndexNode()
        out = node.run(
            operation="add",
            documents=[{"content": "no id here"}],
        )
        assert out["documents_added"] == 1
        # The id was generated from hash(content).
        ids = list(node.document_store.keys())  # type: ignore[attr-defined]
        assert len(ids) == 1
        # Hash-based ids are numeric (str of hash int).
        assert ids[0].lstrip("-").isdigit()

    def test_run_remove_documents_drops_from_store_and_index(self):
        node = IncrementalIndexNode()
        node.run(
            operation="add",
            documents=[
                {"id": "doc1", "content": "alpha beta"},
                {"id": "doc2", "content": "alpha gamma"},
            ],
        )
        out = node.run(operation="remove", document_ids=["doc1"])
        assert out["operation"] == "remove"
        assert out["documents_removed"] == 1
        assert out["total_documents"] == 1
        # doc1 gone, doc2 stays.
        assert "doc1" not in node.document_store  # type: ignore[attr-defined]
        assert "doc2" in node.document_store  # type: ignore[attr-defined]
        # "beta" was unique to doc1 — index term dropped entirely.
        assert "beta" not in node.index  # type: ignore[attr-defined]
        # "alpha" was shared — still tracks doc2.
        assert node.index["alpha"] == {"doc2"}  # type: ignore[attr-defined]

    def test_run_remove_nonexistent_id_is_noop(self):
        node = IncrementalIndexNode()
        node.run(
            operation="add",
            documents=[{"id": "doc1", "content": "alpha"}],
        )
        out = node.run(operation="remove", document_ids=["does_not_exist"])
        assert out["documents_removed"] == 0
        assert out["total_documents"] == 1

    def test_run_update_replaces_existing_document(self):
        node = IncrementalIndexNode()
        node.run(
            operation="add",
            documents=[{"id": "doc1", "content": "original text"}],
        )
        out = node.run(
            operation="update",
            documents=[{"id": "doc1", "content": "new text"}],
        )
        assert out["operation"] == "update"
        assert out["documents_updated"] == 1
        # Document still has 1 entry; content replaced.
        assert node.document_store["doc1"]["content"] == "new text"  # type: ignore[attr-defined]
        # Old terms gone; new terms present.
        assert "original" not in node.index  # type: ignore[attr-defined]
        assert "new" in node.index  # type: ignore[attr-defined]

    def test_run_search_returns_matching_documents(self):
        node = IncrementalIndexNode()
        node.run(
            operation="add",
            documents=[
                {"id": "doc1", "content": "machine learning algorithms"},
                {"id": "doc2", "content": "deep learning networks"},
                {"id": "doc3", "content": "unrelated topic"},
            ],
        )
        out = node.run(operation="search", query="learning")
        assert out["operation"] == "search"
        assert out["query"] == "learning"
        # Both doc1 + doc2 match on "learning".
        assert out["total_matches"] == 2
        result_ids = {r.get("id") for r in out["results"]}
        assert result_ids == {"doc1", "doc2"}

    def test_run_search_no_matches_returns_empty(self):
        node = IncrementalIndexNode()
        node.run(
            operation="add",
            documents=[{"id": "doc1", "content": "alpha"}],
        )
        out = node.run(operation="search", query="zzz")
        assert out["results"] == []
        assert out["total_matches"] == 0

    def test_run_search_caps_results_at_ten(self):
        node = IncrementalIndexNode()
        # Add 15 documents all containing "x".
        node.run(
            operation="add",
            documents=[{"id": f"doc{i}", "content": "x"} for i in range(15)],
        )
        out = node.run(operation="search", query="x")
        # results list is capped at 10 per the documented contract.
        assert len(out["results"]) == 10
        # total_matches reports the full 15 matches.
        assert out["total_matches"] == 15


# ==========================================================================
# Module-level __all__ contract
# ==========================================================================


def test_module_all_exports_three_classes():
    """The module exports exactly the 3 documented classes."""
    from kaizen.nodes.rag import realtime

    assert set(realtime.__all__) == {
        "RealtimeRAGNode",
        "RealtimeStreamingRAGNode",
        "IncrementalIndexNode",
    }

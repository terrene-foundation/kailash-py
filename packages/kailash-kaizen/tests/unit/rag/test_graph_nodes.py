"""Tier-1 unit coverage for the 3 ``kaizen.nodes.rag.graph`` nodes.

F8 shard B2. The value-anchor (verbatim from the workstream brief): "the RAG
capability the user chose to preserve is provably correct, not merely
importable." GraphRAG is the first user-named capability.

``graph.py`` ships three nodes:

- ``GraphBuilderNode`` — builds a real ``networkx`` knowledge graph from
  documents. ``run()`` is the direct, deterministic code path.
- ``GraphQueryNode`` — queries a graph (path / pattern / aggregate query
  types). ``run()`` is the direct, deterministic code path.
- ``GraphRAGNode`` — a ``WorkflowNode``; its behavior is a sub-workflow built
  by ``_create_workflow()``. Construction + workflow shape are covered here;
  the LLM-backed sub-workflow nodes are not exercised (no LLM key in ``[rag]``).

``networkx`` IS the shipped infrastructure — there is nothing to mock. These
tests exercise the real graph-construction / query core. One test per
documented behavior; assertions are structural (node/edge counts, query
result shapes, score ordering, typed raises).
"""

from __future__ import annotations

import networkx as nx
import pytest

from kaizen.nodes.rag.graph import GraphBuilderNode, GraphQueryNode, GraphRAGNode

pytestmark = pytest.mark.unit


# A document whose content contains the sentinel word "transformer" — the
# GraphBuilderNode's simplified entity extraction adds the transformer/attention
# subgraph for any such document (graph.py L598-601).
_TRANSFORMER_DOC = {"id": "d1", "content": "the transformer architecture"}
_PLAIN_DOC = {"id": "d2", "content": "a plain document with no entities"}


# ===========================================================================
# GraphBuilderNode
# ===========================================================================
class TestGraphBuilderNode:
    """``GraphBuilderNode.run()`` — knowledge-graph construction."""

    def test_get_parameters_declares_documents_required(self):
        params = GraphBuilderNode().get_parameters()
        assert params["documents"].required is True
        assert params["documents"].type is list
        # existing_graph / entity_types are optional update inputs.
        assert params["existing_graph"].required is False
        assert params["entity_types"].required is False

    def test_golden_path_builds_transformer_subgraph(self):
        """A transformer document yields the documented transformer/attention
        subgraph: 2 entity nodes + 1 ``uses`` edge."""
        result = GraphBuilderNode().run(documents=[_TRANSFORMER_DOC])
        assert sorted(result.keys()) == [
            "build_metadata",
            "entity_map",
            "graph",
            "statistics",
        ]
        stats = result["statistics"]
        assert stats["total_nodes"] == 2
        assert stats["total_edges"] == 1
        assert stats["components"] == 1
        # The serialized graph round-trips into a real networkx MultiDiGraph.
        G = nx.node_link_graph(result["graph"])
        assert {n for n in G.nodes()} == {"transformer", "attention"}
        assert G.has_edge("transformer", "attention")

    def test_output_graph_is_node_link_serializable(self):
        """``graph`` is a node-link dict — JSON-shaped, round-trippable."""
        result = GraphBuilderNode().run(documents=[_TRANSFORMER_DOC])
        graph = result["graph"]
        assert isinstance(graph, dict)
        assert graph["multigraph"] is True
        assert graph["directed"] is True

    def test_build_metadata_reflects_constructor_config(self):
        node = GraphBuilderNode(merge_similar_entities=False, track_temporal=True)
        result = node.run(documents=[_TRANSFORMER_DOC])
        meta = result["build_metadata"]
        assert meta["documents_processed"] == 1
        assert meta["merge_applied"] is False
        assert meta["temporal_tracking"] is True

    def test_empty_documents_yields_empty_graph(self):
        """Edge case: empty ``documents`` list — an empty graph, zero stats,
        no crash."""
        result = GraphBuilderNode().run(documents=[])
        stats = result["statistics"]
        assert stats["total_nodes"] == 0
        assert stats["total_edges"] == 0
        assert stats["density"] == 0
        assert stats["components"] == 0
        assert result["build_metadata"]["documents_processed"] == 0

    def test_missing_documents_kwarg_defaults_to_empty(self):
        """``run()`` with no ``documents`` kwarg degrades to an empty graph."""
        result = GraphBuilderNode().run()
        assert result["statistics"]["total_nodes"] == 0

    def test_plain_document_adds_no_entities(self):
        """A document without the transformer sentinel produces no nodes — the
        simplified extractor only recognises the sentinel."""
        result = GraphBuilderNode().run(documents=[_PLAIN_DOC])
        assert result["statistics"]["total_nodes"] == 0

    def test_multiple_transformer_docs_merge_into_one_subgraph(self):
        """Two transformer documents share the same node ids — the graph has
        2 nodes total, not 4 (nodes keyed by name)."""
        result = GraphBuilderNode().run(
            documents=[
                {"id": "d1", "content": "transformer one"},
                {"id": "d2", "content": "transformer two"},
            ]
        )
        assert result["statistics"]["total_nodes"] == 2

    def test_document_missing_content_key_does_not_crash(self):
        """Edge case: a doc dict missing the ``content`` key entirely — the
        ``""`` default applies, no entities, no crash."""
        result = GraphBuilderNode().run(documents=[{"id": "no-content"}])
        assert result["statistics"]["total_nodes"] == 0

    def test_document_with_none_content_does_not_crash(self):
        """Edge case (B1 None-content class): a doc with ``content`` present
        but ``None``. The ``""`` default does NOT apply to a present-None key;
        the scoring path must coerce None to ``""`` rather than crash."""
        result = GraphBuilderNode().run(documents=[{"id": "n", "content": None}])
        assert result["statistics"]["total_nodes"] == 0
        assert result["build_metadata"]["documents_processed"] == 1

    def test_none_content_mixed_with_good_doc(self):
        """A None-content doc must not poison a well-formed sibling: the
        transformer doc still builds its subgraph."""
        result = GraphBuilderNode().run(
            documents=[{"id": "n", "content": None}, _TRANSFORMER_DOC]
        )
        assert result["statistics"]["total_nodes"] == 2

    def test_malformed_non_dict_document_does_not_crash(self):
        """Edge case: a non-dict element in ``documents``. The node skips
        malformed entries rather than crashing on ``str.get``."""
        result = GraphBuilderNode().run(documents=["not a dict", _TRANSFORMER_DOC])
        assert result["statistics"]["total_nodes"] == 2
        assert result["build_metadata"]["documents_processed"] == 2

    def test_unicode_content_does_not_crash(self):
        """Unicode document content is handled — no entities here, but no
        crash on non-ASCII text."""
        result = GraphBuilderNode().run(
            documents=[{"id": "u1", "content": "le café au lait — 日本語"}]
        )
        assert result["statistics"]["total_nodes"] == 0

    def test_existing_graph_is_extended_not_replaced(self):
        """When ``existing_graph`` is passed, the node updates it: a prior
        graph plus a new transformer doc keeps the prior nodes."""
        base = GraphBuilderNode().run(documents=[_TRANSFORMER_DOC])["graph"]
        result = GraphBuilderNode().run(
            documents=[{"id": "d3", "content": "another transformer"}],
            existing_graph=base,
        )
        # Still 2 nodes (same entity names), graph reconstructed from base.
        assert result["statistics"]["total_nodes"] == 2


# ===========================================================================
# GraphQueryNode
# ===========================================================================
def _build_graph() -> dict:
    """A small real graph: transformer --uses--> attention."""
    return GraphBuilderNode().run(documents=[_TRANSFORMER_DOC])["graph"]


class TestGraphQueryNode:
    """``GraphQueryNode.run()`` — path / pattern / aggregate query types."""

    def test_get_parameters_declares_required_inputs(self):
        params = GraphQueryNode().get_parameters()
        assert params["graph"].required is True
        assert params["query_type"].required is True
        assert params["query_params"].required is True

    def test_path_query_finds_connection(self):
        """A ``path`` query between connected entities returns the path with
        its length and edge list."""
        result = GraphQueryNode().run(
            graph=_build_graph(),
            query_type="path",
            query_params={
                "source_entity": "transformer",
                "target_entity": "attention",
                "max_length": 3,
            },
        )
        assert len(result["paths"]) == 1
        path = result["paths"][0]
        assert path["path"] == ["transformer", "attention"]
        assert path["length"] == 1
        assert path["edges"] == [("transformer", "attention")]

    def test_path_query_missing_endpoint_returns_no_paths(self):
        """A ``path`` query whose source/target is absent from the graph
        returns an empty ``paths`` list — not a crash."""
        result = GraphQueryNode().run(
            graph=_build_graph(),
            query_type="path",
            query_params={
                "source_entity": "nonexistent",
                "target_entity": "attention",
            },
        )
        assert result["paths"] == []

    def test_pattern_query_filters_by_node_type(self):
        """A ``pattern`` query with a ``node_type`` returns only matching
        nodes, with attributes and degree."""
        result = GraphQueryNode().run(
            graph=_build_graph(),
            query_type="pattern",
            query_params={"pattern": {"node_type": "technology"}},
        )
        assert len(result["matches"]) == 1
        match = result["matches"][0]
        assert match["entity"] == "transformer"
        assert match["attributes"]["type"] == "technology"
        assert match["degree"] == 1

    def test_pattern_query_no_type_returns_all_nodes(self):
        """A ``pattern`` query with no ``node_type`` returns every node."""
        result = GraphQueryNode().run(
            graph=_build_graph(),
            query_type="pattern",
            query_params={"pattern": {}},
        )
        assert {m["entity"] for m in result["matches"]} == {
            "transformer",
            "attention",
        }

    def test_aggregate_query_returns_graph_statistics(self):
        """An ``aggregate`` query returns node/edge counts, density, average
        degree, and clustering coefficient over the real graph."""
        result = GraphQueryNode().run(
            graph=_build_graph(),
            query_type="aggregate",
            query_params={},
        )
        agg = result["aggregations"]
        assert agg["node_count"] == 2
        assert agg["edge_count"] == 1
        assert 0.0 <= agg["density"] <= 1.0
        assert agg["avg_degree"] >= 0.0
        # clustering_coefficient must compute over the multigraph without
        # raising NetworkXNotImplemented.
        assert 0.0 <= agg["clustering_coefficient"] <= 1.0

    def test_aggregate_query_on_empty_graph(self):
        """``aggregate`` over an empty graph returns zeroed stats — no
        divide-by-zero, no clustering crash."""
        empty = GraphBuilderNode().run(documents=[])["graph"]
        result = GraphQueryNode().run(
            graph=empty, query_type="aggregate", query_params={}
        )
        agg = result["aggregations"]
        assert agg["node_count"] == 0
        assert agg["edge_count"] == 0
        assert agg["avg_degree"] == 0
        assert agg["clustering_coefficient"] == 0

    def test_unknown_query_type_returns_empty_result_shape(self):
        """An unrecognised ``query_type`` returns the base result shape with
        empty matches/paths/aggregations — no crash, no exception."""
        result = GraphQueryNode().run(
            graph=_build_graph(),
            query_type="nonsense",
            query_params={},
        )
        assert result["matches"] == []
        assert result["paths"] == []
        assert result["aggregations"] == {}
        assert result["query_type"] == "nonsense"

    def test_path_query_default_max_length(self):
        """``max_length`` defaults to 3 when omitted from query_params."""
        result = GraphQueryNode().run(
            graph=_build_graph(),
            query_type="path",
            query_params={
                "source_entity": "transformer",
                "target_entity": "attention",
            },
        )
        assert len(result["paths"]) == 1

    def test_query_result_echoes_query_params(self):
        """The result echoes the query_type and query_params it was given."""
        params = {"source_entity": "transformer", "target_entity": "attention"}
        result = GraphQueryNode().run(
            graph=_build_graph(), query_type="path", query_params=params
        )
        assert result["query_type"] == "path"
        assert result["query_params"] == params


# ===========================================================================
# GraphRAGNode — WorkflowNode; construction + workflow-shape coverage
# ===========================================================================
class TestGraphRAGNode:
    """``GraphRAGNode`` is a ``WorkflowNode``. Its ``run()`` executes a
    sub-workflow built by ``_create_workflow()``. The sub-workflow's
    ``LLMAgentNode`` steps need an LLM key (absent from ``[rag]``), so these
    tests cover construction and the deterministic ``_create_workflow()``
    graph SHAPE, not end-to-end execution."""

    def test_constructs_with_defaults(self):
        # type: ignore[attr-defined] on the constructor-attr reads below — the
        # @register_node decorator erases the concrete GraphRAGNode type to
        # base Node, which does not declare entity_types/max_hops/etc. The
        # attributes exist at runtime (set in __init__); the static erasure is
        # a known Core SDK decorator gap (out of B2 scope).
        node = GraphRAGNode()
        assert node.entity_types == [  # type: ignore[attr-defined]
            "person",
            "organization",
            "concept",
            "technology",
        ]
        assert node.relationship_types == [  # type: ignore[attr-defined]
            "relates_to",
            "influences",
            "uses",
            "created_by",
        ]
        assert node.max_hops == 2  # type: ignore[attr-defined]
        assert node.community_algorithm == "louvain"  # type: ignore[attr-defined]
        assert node.use_global_summary is True  # type: ignore[attr-defined]

    def test_constructs_with_custom_config(self):
        # type: ignore[attr-defined] — see test_constructs_with_defaults.
        node = GraphRAGNode(
            entity_types=["gene", "protein"],
            relationship_types=["binds"],
            max_hops=5,
            use_global_summary=False,
        )
        assert node.entity_types == ["gene", "protein"]  # type: ignore[attr-defined]
        assert node.relationship_types == ["binds"]  # type: ignore[attr-defined]
        assert node.max_hops == 5  # type: ignore[attr-defined]
        assert node.use_global_summary is False  # type: ignore[attr-defined]

    def test_create_workflow_builds_expected_nodes_with_summary(self):
        """``_create_workflow()`` with ``use_global_summary=True`` builds the
        full 6-node graph RAG pipeline."""
        # type: ignore[attr-defined] — the @register_node decorator erases the
        # concrete subclass type to base Node, which does not declare the
        # per-node _create_workflow helper. The method exists at runtime; the
        # static erasure is a known Core SDK decorator gap (out of B2 scope).
        wf = GraphRAGNode(use_global_summary=True)._create_workflow()  # type: ignore[attr-defined]
        node_ids = set(wf.nodes.keys())
        assert node_ids == {
            "entity_extractor",
            "graph_builder",
            "query_processor",
            "graph_retriever",
            "summary_generator",
            "result_synthesizer",
        }

    def test_create_workflow_omits_summary_node_when_disabled(self):
        """With ``use_global_summary=False`` the ``summary_generator`` node is
        absent — a 5-node pipeline."""
        wf = GraphRAGNode(use_global_summary=False)._create_workflow()  # type: ignore[attr-defined]
        node_ids = set(wf.nodes.keys())
        assert "summary_generator" not in node_ids
        assert len(node_ids) == 5

    def test_create_workflow_entity_types_flow_into_extractor_prompt(self):
        """Custom ``entity_types`` appear in the entity_extractor's system
        prompt — the constructor config reaches the generated workflow."""
        wf = GraphRAGNode(
            entity_types=["gene", "protein"]
        )._create_workflow()  # type: ignore[attr-defined]
        prompt = wf.nodes["entity_extractor"].config["system_prompt"]
        assert "gene" in prompt
        assert "protein" in prompt

    def test_create_workflow_max_hops_flows_into_retriever_code(self):
        """``max_hops`` is interpolated into the graph_retriever code
        template — the BFS depth bound reaches the generated code."""
        wf = GraphRAGNode(max_hops=7)._create_workflow()  # type: ignore[attr-defined]
        code = wf.nodes["graph_retriever"].config["code"]
        assert "depth >= 7" in code

    def test_get_parameters_exposes_workflow_inputs(self):
        """As a WorkflowNode, GraphRAGNode exposes the sub-workflow's input
        parameters via get_parameters()."""
        params = GraphRAGNode().get_parameters()
        assert isinstance(params, dict)
        # The sub-workflow's leaf inputs are exposed as node parameters.
        assert len(params) > 0

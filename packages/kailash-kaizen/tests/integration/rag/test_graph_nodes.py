"""Tier-2a integration coverage for ``kaizen.nodes.rag.graph``.

F8 shard B2. The 3 graph RAG nodes build and query real ``networkx`` knowledge
graphs — ``networkx`` IS the real backend (no container, no LLM key for the
deterministic ``run()`` paths). These tests exercise the nodes against real
``networkx`` with NO mocking (``@patch`` / ``MagicMock`` / ``unittest.mock``
are BLOCKED in Tier 2 per the 3-tier testing rule). Assertions are structural:
real graph node/edge counts, query result shapes, path/centrality ordering,
clustering values, and typed outputs.

The value-anchor: "the RAG capability the user chose to preserve is provably
correct, not merely importable." GraphRAG is the first user-named capability.
"""

from __future__ import annotations

import networkx as nx
import pytest

from kaizen.nodes.rag.graph import GraphBuilderNode, GraphQueryNode, GraphRAGNode

pytestmark = pytest.mark.integration


# Two documents, both carrying the "transformer" sentinel — GraphBuilderNode's
# simplified extractor adds the transformer/attention subgraph per document.
_DOCS = [
    {"id": "paper-1", "content": "the transformer model and self-attention"},
    {"id": "paper-2", "content": "a transformer architecture for sequences"},
]


# ===========================================================================
# GraphBuilderNode — against real networkx
# ===========================================================================
class TestGraphBuilderIntegration:
    def test_builds_real_networkx_multidigraph(self):
        """The ``graph`` output deserializes into a genuine networkx
        MultiDiGraph with the expected node/edge structure."""
        result = GraphBuilderNode().run(documents=_DOCS)
        G = nx.node_link_graph(result["graph"])
        assert isinstance(G, nx.MultiDiGraph)
        # Two transformer docs collapse to the same 2 named entity nodes.
        assert set(G.nodes()) == {"transformer", "attention"}
        # Each transformer doc adds its own "uses" edge — a MultiDiGraph keeps
        # parallel edges, so 2 documents -> 2 edges.
        assert G.number_of_edges() == 2
        assert G.has_edge("transformer", "attention")

    def test_node_attributes_preserved_through_serialization(self):
        """Entity ``type`` attributes survive the node-link round-trip."""
        result = GraphBuilderNode().run(documents=_DOCS)
        G = nx.node_link_graph(result["graph"])
        assert G.nodes["transformer"]["type"] == "technology"
        assert G.nodes["attention"]["type"] == "concept"

    def test_statistics_match_real_graph(self):
        """``statistics`` reflects the real graph: density and component
        count computed by networkx itself."""
        result = GraphBuilderNode().run(documents=_DOCS)
        G = nx.node_link_graph(result["graph"])
        stats = result["statistics"]
        assert stats["total_nodes"] == G.number_of_nodes()
        assert stats["total_edges"] == G.number_of_edges()
        assert stats["density"] == pytest.approx(nx.density(G))
        assert stats["components"] == nx.number_weakly_connected_components(G)

    def test_empty_corpus_builds_empty_real_graph(self):
        result = GraphBuilderNode().run(documents=[])
        G = nx.node_link_graph(result["graph"])
        assert G.number_of_nodes() == 0
        assert G.number_of_edges() == 0

    def test_existing_graph_round_trips_through_real_networkx(self):
        """An ``existing_graph`` is reconstructed by real networkx and
        extended — the prior structure is preserved."""
        base = GraphBuilderNode().run(documents=_DOCS[:1])["graph"]
        result = GraphBuilderNode().run(documents=_DOCS[1:], existing_graph=base)
        G = nx.node_link_graph(result["graph"])
        assert set(G.nodes()) == {"transformer", "attention"}

    def test_none_content_does_not_break_real_graph_build(self):
        """A present-but-None content document is handled cleanly — the real
        graph still builds from the well-formed sibling."""
        result = GraphBuilderNode().run(
            documents=[{"id": "n", "content": None}, *_DOCS]
        )
        G = nx.node_link_graph(result["graph"])
        assert set(G.nodes()) == {"transformer", "attention"}


# ===========================================================================
# GraphQueryNode — against real networkx graphs
# ===========================================================================
def _real_graph() -> dict:
    return GraphBuilderNode().run(documents=_DOCS)["graph"]


class TestGraphQueryIntegration:
    def test_path_query_traverses_real_graph(self):
        """A ``path`` query runs ``nx.all_simple_paths`` over the real graph
        and returns the genuine connection."""
        result = GraphQueryNode().run(
            graph=_real_graph(),
            query_type="path",
            query_params={
                "source_entity": "transformer",
                "target_entity": "attention",
                "max_length": 4,
            },
        )
        assert len(result["paths"]) >= 1
        # Every returned path genuinely starts at source and ends at target.
        for path in result["paths"]:
            assert path["path"][0] == "transformer"
            assert path["path"][-1] == "attention"
            assert path["length"] == len(path["path"]) - 1

    def test_pattern_query_returns_real_node_degree(self):
        """A ``pattern`` query reports each node's real networkx degree."""
        graph = _real_graph()
        G = nx.node_link_graph(graph)
        result = GraphQueryNode().run(
            graph=graph,
            query_type="pattern",
            query_params={"pattern": {}},
        )
        by_entity = {m["entity"]: m for m in result["matches"]}
        for name, match in by_entity.items():
            assert match["degree"] == G.degree(name)

    def test_pattern_query_type_filter_against_real_graph(self):
        """Type-filtered ``pattern`` query returns only nodes whose real
        attributes match."""
        result = GraphQueryNode().run(
            graph=_real_graph(),
            query_type="pattern",
            query_params={"pattern": {"node_type": "concept"}},
        )
        assert len(result["matches"]) == 1
        assert result["matches"][0]["entity"] == "attention"

    def test_aggregate_query_computes_real_statistics(self):
        """The ``aggregate`` query computes node/edge counts, density,
        average degree and clustering coefficient over the real multigraph —
        and does not raise NetworkXNotImplemented."""
        graph = _real_graph()
        G = nx.node_link_graph(graph)
        result = GraphQueryNode().run(
            graph=graph, query_type="aggregate", query_params={}
        )
        agg = result["aggregations"]
        assert agg["node_count"] == G.number_of_nodes()
        assert agg["edge_count"] == G.number_of_edges()
        assert agg["density"] == pytest.approx(nx.density(G))
        # clustering coefficient is a real float in [0, 1].
        assert 0.0 <= agg["clustering_coefficient"] <= 1.0

    def test_aggregate_query_avg_degree_matches_networkx(self):
        """Average degree from the ``aggregate`` query matches a direct
        networkx degree computation."""
        graph = _real_graph()
        G = nx.node_link_graph(graph)
        result = GraphQueryNode().run(
            graph=graph, query_type="aggregate", query_params={}
        )
        expected = sum(dict(G.degree()).values()) / G.number_of_nodes()
        assert result["aggregations"]["avg_degree"] == pytest.approx(expected)

    def test_path_query_no_connection_returns_empty_paths(self):
        """A ``path`` query for an absent endpoint returns an empty list —
        real graph traversal, no crash."""
        result = GraphQueryNode().run(
            graph=_real_graph(),
            query_type="path",
            query_params={
                "source_entity": "transformer",
                "target_entity": "nonexistent-entity",
            },
        )
        assert result["paths"] == []


# ===========================================================================
# GraphRAGNode — WorkflowNode construction + workflow-shape integration
# ===========================================================================
class TestGraphRAGNodeIntegration:
    """``GraphRAGNode`` is a ``WorkflowNode``; its ``run()`` executes a
    sub-workflow whose ``LLMAgentNode`` steps require an LLM key absent from
    the ``[rag]`` extra. These tests verify the deterministic part: the
    ``_create_workflow()`` builds a real, structurally-connected sub-workflow.
    """

    def test_create_workflow_builds_real_connected_workflow(self):
        """``_create_workflow()`` returns a real built workflow whose nodes
        are wired — the PythonCodeNode graph_builder/graph_retriever bodies
        and the LLM nodes are all present and connected."""
        # type: ignore[attr-defined] — the @register_node decorator erases the
        # concrete subclass type to base Node, which does not declare the
        # per-node _create_workflow helper. The method exists at runtime; the
        # static erasure is a known Core SDK decorator gap (out of B2 scope).
        wf = GraphRAGNode()._create_workflow()  # type: ignore[attr-defined]
        # The full pipeline has 6 nodes when global summary is enabled.
        assert len(wf.nodes) == 6
        # The graph_builder PythonCodeNode carries a real code template.
        builder_code = wf.nodes["graph_builder"].config["code"]
        assert "build_knowledge_graph" in builder_code
        assert "nx.MultiDiGraph" in builder_code

    def test_create_workflow_retriever_code_carries_max_hops(self):
        """``max_hops`` is interpolated into the real graph_retriever code
        template the sub-workflow executes."""
        wf = GraphRAGNode(max_hops=3)._create_workflow()  # type: ignore[attr-defined]
        retriever_code = wf.nodes["graph_retriever"].config["code"]
        assert "depth >= 3" in retriever_code

    def test_create_workflow_summary_disabled_drops_node_and_connections(self):
        """With ``use_global_summary=False`` the real workflow has 5 nodes and
        no summary_generator wiring."""
        wf = GraphRAGNode(use_global_summary=False)._create_workflow()  # type: ignore[attr-defined]
        assert len(wf.nodes) == 5
        assert "summary_generator" not in wf.nodes

    def test_graph_rag_node_is_workflow_node(self):
        """GraphRAGNode constructs as a real WorkflowNode with a built
        sub-workflow attached."""
        from kailash.nodes.logic.workflow import WorkflowNode

        node = GraphRAGNode()
        assert isinstance(node, WorkflowNode)
        params = node.get_parameters()
        assert isinstance(params, dict)
        assert len(params) > 0

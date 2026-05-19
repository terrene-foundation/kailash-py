"""Regression: two latent ``kaizen.nodes.rag.graph`` run()-path defects.

F8 shard B2 surfaced both defects via behavioral coverage of the graph RAG
nodes. Both are ``run()``-path-only — the ``_create_workflow()`` codegen
templates carry neither pattern (verified per the B1 two-path lesson).

Defect 1 — None-content crash (same class as B1's similarity-node defect).
  ``GraphBuilderNode.run()`` extracted document text via
  ``doc.get("content", "")``. The ``""`` default applies ONLY to a MISSING
  key; a document ``{"content": None}`` returned ``None`` and the subsequent
  ``content.split()`` / ``content.lower()`` raised ``AttributeError``. A
  non-dict document element also crashed on ``str.get``.
  Fix: ``content = doc.get("content") or ""`` plus an ``isinstance(doc, dict)``
  skip for malformed entries.

Defect 2 — aggregate query multigraph crash.
  ``GraphQueryNode.run()``'s ``aggregate`` query type computed
  ``nx.average_clustering(G.to_undirected())``. ``GraphBuilderNode`` produces
  a ``MultiDiGraph``; its node-link round-trip is also a multigraph, and
  ``average_clustering`` raises ``NetworkXNotImplemented`` for multigraph
  types. The documented ``aggregate`` query type never worked end-to-end.
  Fix: ``nx.average_clustering(nx.Graph(G.to_undirected()))``.

Behavioral tests: they call ``run()`` and assert success / typed outputs —
not source-grep.
"""

from __future__ import annotations

import pytest

from kaizen.nodes.rag.graph import GraphBuilderNode, GraphQueryNode

pytestmark = pytest.mark.regression


# ---------------------------------------------------------------------------
# Defect 1 — GraphBuilderNode None-content / malformed-document crash
# ---------------------------------------------------------------------------
def test_graph_builder_none_content_does_not_crash():
    """A document with ``content`` present-but-None must not crash run()."""
    result = GraphBuilderNode().run(documents=[{"id": "n", "content": None}])
    assert result["statistics"]["total_nodes"] == 0
    assert result["build_metadata"]["documents_processed"] == 1


def test_graph_builder_none_content_does_not_poison_sibling():
    """A None-content doc must not block a well-formed transformer doc from
    building its subgraph."""
    result = GraphBuilderNode().run(
        documents=[
            {"id": "n", "content": None},
            {"id": "good", "content": "the transformer model"},
        ]
    )
    assert result["statistics"]["total_nodes"] == 2


def test_graph_builder_malformed_non_dict_document_does_not_crash():
    """A non-dict element in ``documents`` is skipped, not crashed on."""
    result = GraphBuilderNode().run(
        documents=["not a dict", {"id": "g", "content": "transformer here"}]
    )
    assert result["statistics"]["total_nodes"] == 2
    assert result["build_metadata"]["documents_processed"] == 2


# ---------------------------------------------------------------------------
# Defect 2 — GraphQueryNode aggregate-query multigraph crash
# ---------------------------------------------------------------------------
def test_graph_query_aggregate_does_not_crash_on_multigraph():
    """The ``aggregate`` query type must compute the clustering coefficient
    over a real GraphBuilderNode-produced MultiDiGraph without raising
    NetworkXNotImplemented."""
    graph = GraphBuilderNode().run(
        documents=[{"id": "d1", "content": "transformer uses attention"}]
    )["graph"]
    result = GraphQueryNode().run(graph=graph, query_type="aggregate", query_params={})
    agg = result["aggregations"]
    assert agg["node_count"] == 2
    assert agg["edge_count"] == 1
    assert 0.0 <= agg["clustering_coefficient"] <= 1.0


def test_graph_query_aggregate_empty_graph_returns_zeroed_stats():
    """``aggregate`` over an empty graph returns zeroed stats — no
    divide-by-zero, no clustering crash."""
    empty = GraphBuilderNode().run(documents=[])["graph"]
    result = GraphQueryNode().run(graph=empty, query_type="aggregate", query_params={})
    agg = result["aggregations"]
    assert agg["node_count"] == 0
    assert agg["clustering_coefficient"] == 0

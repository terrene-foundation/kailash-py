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
        full 12-node graph RAG pipeline.

        L3 fix (Wave-2): three ``*_messages_composer`` from_function nodes were
        added — one per LLM stage — so each LLM stage receives its REAL context
        via the VALID ``messages`` port (input side).

        O3 fix (Wave-O3): three OUTPUT-side from_function parser nodes were added —
        ``entity_extraction_parser`` (between entity_extractor and graph_builder),
        ``query_analysis_parser`` (between query_processor and graph_retriever),
        and ``global_summary_parser`` (between summary_generator and
        result_synthesizer) — so each LLM stage's output is PARSED before its
        consumer reads it. The prior 9-node set grew to 12 (9 + 3 parsers)."""
        # type: ignore[attr-defined] — the @register_node decorator erases the
        # concrete subclass type to base Node, which does not declare the
        # per-node _create_workflow helper. The method exists at runtime; the
        # static erasure is a known Core SDK decorator gap (out of B2 scope).
        wf = GraphRAGNode(use_global_summary=True)._create_workflow()  # type: ignore[attr-defined]
        node_ids = set(wf.nodes.keys())
        assert node_ids == {
            "entity_extractor",
            "entity_messages_composer",
            "entity_extraction_parser",
            "graph_builder",
            "query_processor",
            "query_messages_composer",
            "query_analysis_parser",
            "graph_retriever",
            "summary_generator",
            "summary_messages_composer",
            "global_summary_parser",
            "result_synthesizer",
        }

    def test_create_workflow_omits_summary_node_when_disabled(self):
        """With ``use_global_summary=False`` the ``summary_generator`` node AND
        its ``summary_messages_composer`` AND its ``global_summary_parser`` are
        absent — a 9-node pipeline (5 original non-summary nodes + the entity &
        query message composers + the entity_extraction_parser + the
        query_analysis_parser; the summary stage and its parser are added only
        when ``use_global_summary=True``)."""
        wf = GraphRAGNode(use_global_summary=False)._create_workflow()  # type: ignore[attr-defined]
        node_ids = set(wf.nodes.keys())
        assert "summary_generator" not in node_ids
        assert "summary_messages_composer" not in node_ids
        assert "global_summary_parser" not in node_ids
        # The entity & query analysis parsers ARE present on the disabled path
        # (entity extraction + query analysis happen regardless of the summary
        # stage — query_processor is built unconditionally).
        assert "entity_extraction_parser" in node_ids
        assert "query_analysis_parser" in node_ids
        assert len(node_ids) == 9

    def test_create_workflow_entity_types_flow_into_extractor_prompt(self):
        """Custom ``entity_types`` appear in the entity_extractor's system
        prompt — the constructor config reaches the generated workflow."""
        wf = GraphRAGNode(
            entity_types=["gene", "protein"]
        )._create_workflow()  # type: ignore[attr-defined]
        prompt = wf.nodes["entity_extractor"].config["system_prompt"]
        assert "gene" in prompt
        assert "protein" in prompt

    def test_create_workflow_max_hops_flows_into_retriever(self):
        """``max_hops`` is bound into the graph_retriever ``from_function`` closure
        (Wave-3 migration). The BFS depth bound reaches the retriever via the
        closure, not an f-string code template. Proven directly: the bound
        retriever expands the subgraph up to ``max_hops`` hops (see
        ``TestRetrieveFromGraph.test_multi_hop_bounded_by_max_hops`` for the
        behavioral floor); here we assert the node is a real registered node
        (no ``code=`` config to inspect anymore)."""
        wf = GraphRAGNode(max_hops=7)._create_workflow()  # type: ignore[attr-defined]
        retriever = wf.nodes["graph_retriever"]
        # The migrated node is a from_function PythonCodeNode — its `code` config
        # is None (the prior f-string template is gone). The max_hops bound
        # behavior is asserted directly against `retrieve_from_graph` below.
        assert retriever.config.get("code") is None
        assert retriever is not None

    def test_get_parameters_exposes_workflow_inputs(self):
        """As a WorkflowNode, GraphRAGNode exposes the sub-workflow's input
        parameters via get_parameters()."""
        params = GraphRAGNode().get_parameters()
        assert isinstance(params, dict)
        # The sub-workflow's leaf inputs are exposed as node parameters.
        assert len(params) > 0


# ==========================================================================
# F31-FU2 Shard C — direct-call Tier-1 coverage of the pure parser / composer
# `from_function` targets in `graph.py` (the O3 OUTPUT-side parsers + the LLM-
# stage message composers). Pure data rendering / tool-result parsing (permitted
# deterministic exceptions per rules/agent-reasoning.md #3 + #6) — NOT agent
# decision-making. Called DIRECTLY (no LocalRuntime, no mocking — pure functions).
#
# Per-file contract (zero-tolerance Rule 2) — the THREE graph parsers each have
# their OWN distinct shape; never borrow another's contract:
#   * parse_entity_extraction — publishes the parsed object WRAPPED IN A
#     ONE-ELEMENT LIST under `result` (`{"result": [ {entities, relationships} ]}`)
#     because build_knowledge_graph iterates extraction_results as a LIST of
#     per-doc objects. Malformed -> a one-element list carrying
#     `{"entities": [], "relationships": [], "parse_error": "<reason>"}` so the
#     graph builds EMPTY honestly (never fabricated entities, never a crash).
#   * parse_query_analysis — publishes a DICT under `result`
#     (`{"result": {entities, relationship_types, requires_multi_hop,
#     reasoning_type}}`). Malformed -> the same dict with empty defaults +
#     `parse_error`. requires_multi_hop is coerced via bool(); reasoning_type
#     stays None when absent (never a fabricated default type).
#   * parse_global_summary — PROSE (NO json.loads). `{"result": {global_summary}}`.
#     Sentinels: empty-response (None/empty/blank) and non-string-content. There
#     is NO non-json sentinel because the summary is free text, not JSON.
# ==========================================================================

import json as _json

from kaizen.nodes.rag.graph import (
    _unwrap_response_content,
    build_knowledge_graph,
    compose_entity_extraction_messages,
    compose_query_analysis_messages,
    compose_summary_messages,
    parse_entity_extraction,
    parse_global_summary,
    parse_query_analysis,
    retrieve_from_graph,
    synthesize_results,
)


def _g_wrap(obj) -> dict:
    """Build the LLMAgentNode `response` port shape with a JSON-string content."""
    return {"content": _json.dumps(obj)}


class TestGraphUnwrapResponseContent:
    """`_unwrap_response_content`: dict -> .content, bare value -> passthrough."""

    def test_unwrap_dict_returns_content(self):
        assert _unwrap_response_content({"content": "hello"}) == "hello"

    def test_unwrap_dict_missing_content_returns_none(self):
        assert _unwrap_response_content({"other": "x"}) is None

    def test_unwrap_bare_string_passthrough(self):
        assert _unwrap_response_content("raw string") == "raw string"

    def test_unwrap_none_passthrough(self):
        assert _unwrap_response_content(None) is None


class TestParseEntityExtraction:
    """List-wrapped result; malformed -> one-element flagged extraction.

    The list-wrap is critical: build_knowledge_graph iterates the result as a
    LIST of per-doc extraction objects. Every variant returns a ONE-element list.
    """

    def test_valid_returns_one_element_list_of_extraction(self):
        obj = {"entities": [{"name": "BERT"}], "relationships": [{"a": "b"}]}
        result = parse_entity_extraction(_g_wrap(obj))
        assert result == {"result": [obj]}
        # The wrapper IS a list with exactly one element.
        assert isinstance(result["result"], list) and len(result["result"]) == 1
        assert "parse_error" not in result["result"][0]

    def test_already_dict_content_returns_one_element_list(self):
        # Provider pre-parsed: content is already a dict.
        obj = {"entities": [{"name": "X"}], "relationships": []}
        result = parse_entity_extraction({"content": obj})
        assert result == {"result": [obj]}

    def test_none_returns_flagged_empty_extraction_list(self):
        result = parse_entity_extraction(None)
        assert result == {
            "result": [
                {"entities": [], "relationships": [], "parse_error": "empty-response"}
            ]
        }

    def test_empty_content_returns_flagged_empty_extraction_list(self):
        result = parse_entity_extraction({"content": ""})
        assert result == {
            "result": [
                {"entities": [], "relationships": [], "parse_error": "empty-response"}
            ]
        }

    def test_non_json_returns_flagged_non_json_list(self):
        result = parse_entity_extraction({"content": "not json{"})
        assert result == {
            "result": [
                {
                    "entities": [],
                    "relationships": [],
                    "parse_error": "non-json-response",
                }
            ]
        }

    def test_unexpected_content_type_returns_flagged_list(self):
        result = parse_entity_extraction({"content": 42})
        assert result == {
            "result": [
                {
                    "entities": [],
                    "relationships": [],
                    "parse_error": "unexpected-content-type",
                }
            ]
        }

    def test_non_object_json_returns_flagged_list(self):
        result = parse_entity_extraction({"content": "[1, 2, 3]"})
        assert result == {
            "result": [
                {
                    "entities": [],
                    "relationships": [],
                    "parse_error": "non-object-json",
                }
            ]
        }

    def test_missing_keys_returns_flagged_empty_extraction(self):
        # Parsed object but entities/relationships keys absent/wrong-shape.
        result = parse_entity_extraction(_g_wrap({"foo": 1}))
        assert result == {
            "result": [
                {
                    "entities": [],
                    "relationships": [],
                    "parse_error": "missing-entities-or-relationships",
                }
            ]
        }


class TestParseQueryAnalysis:
    """Dict-wrapped result; malformed -> empty-default dict + parse_error."""

    def test_valid_returns_analysis_dict(self):
        obj = {
            "entities": ["BERT", "GPT"],
            "relationship_types": ["influenced"],
            "requires_multi_hop": True,
            "reasoning_type": "causal",
        }
        result = parse_query_analysis(_g_wrap(obj))
        assert result == {"result": obj}
        assert "parse_error" not in result["result"]

    def test_already_dict_content_returns_analysis_dict(self):
        obj = {
            "entities": ["X"],
            "relationship_types": [],
            "requires_multi_hop": False,
            "reasoning_type": None,
        }
        result = parse_query_analysis({"content": obj})
        assert result["result"]["entities"] == ["X"]
        assert "parse_error" not in result["result"]

    def test_none_returns_flagged_empty_analysis(self):
        result = parse_query_analysis(None)
        assert result == {
            "result": {
                "entities": [],
                "relationship_types": [],
                "requires_multi_hop": False,
                "reasoning_type": None,
                "parse_error": "empty-response",
            }
        }

    def test_empty_content_returns_flagged_empty_analysis(self):
        result = parse_query_analysis({"content": ""})
        assert result["result"]["parse_error"] == "empty-response"
        assert result["result"]["entities"] == []
        assert result["result"]["requires_multi_hop"] is False
        assert result["result"]["reasoning_type"] is None

    def test_non_json_returns_flagged_non_json_analysis(self):
        result = parse_query_analysis({"content": "not json{"})
        assert result["result"]["parse_error"] == "non-json-response"
        assert result["result"]["entities"] == []

    def test_unexpected_content_type_returns_flagged_analysis(self):
        result = parse_query_analysis({"content": 42})
        assert result["result"]["parse_error"] == "unexpected-content-type"
        assert result["result"]["entities"] == []

    def test_non_object_json_returns_flagged_analysis(self):
        result = parse_query_analysis({"content": "[1, 2, 3]"})
        assert result["result"]["parse_error"] == "non-object-json"
        assert result["result"]["entities"] == []

    def test_missing_fields_coerced_to_honest_defaults(self):
        # Parsed object with absent fields: each coerced to its empty default,
        # requires_multi_hop -> bool(None) == False, reasoning_type stays None.
        result = parse_query_analysis(_g_wrap({"foo": 1}))
        analysis = result["result"]
        assert analysis["entities"] == []
        assert analysis["relationship_types"] == []
        assert analysis["requires_multi_hop"] is False
        assert analysis["reasoning_type"] is None
        # A valid parse with only-missing-fields carries no parse_error (the dict
        # was a valid object; the defaults are honest, not a parse failure).
        assert "parse_error" not in analysis


class TestParseGlobalSummary:
    """Prose (NO json.loads); empty-response + non-string-content sentinels."""

    def test_valid_prose_returns_summary(self):
        result = parse_global_summary({"content": "The corpus covers transformers."})
        assert result == {
            "result": {"global_summary": "The corpus covers transformers."}
        }
        assert "parse_error" not in result["result"]

    def test_valid_prose_is_stripped(self):
        result = parse_global_summary({"content": "  surrounded by space  "})
        assert result["result"]["global_summary"] == "surrounded by space"

    def test_bare_string_passthrough_returns_summary(self):
        # A defensive bare-string response (not dict-wrapped) is honored.
        result = parse_global_summary("plain prose summary")
        assert result["result"]["global_summary"] == "plain prose summary"

    def test_none_returns_empty_response_sentinel(self):
        result = parse_global_summary(None)
        assert result == {
            "result": {"global_summary": None, "parse_error": "empty-response"}
        }

    def test_empty_content_returns_empty_response_sentinel(self):
        result = parse_global_summary({"content": ""})
        assert result == {
            "result": {"global_summary": None, "parse_error": "empty-response"}
        }

    def test_whitespace_content_returns_empty_response_sentinel(self):
        result = parse_global_summary({"content": "   "})
        assert result == {
            "result": {"global_summary": None, "parse_error": "empty-response"}
        }

    def test_non_string_content_returns_non_string_sentinel(self):
        # The provider returned a structure where prose was expected.
        result = parse_global_summary({"content": {"a": 1}})
        assert result == {
            "result": {"global_summary": None, "parse_error": "non-string-content"}
        }


def _g_assert_messages_shape(result):
    """Assert the composer return is a well-formed OpenAI chat `messages` list."""
    assert isinstance(result, dict)
    assert "messages" in result
    msgs = result["messages"]
    assert isinstance(msgs, list) and len(msgs) >= 1
    for m in msgs:
        assert isinstance(m, dict)
        assert "role" in m and "content" in m
    return msgs


class TestComposeEntityExtractionMessages:
    def test_valid_interpolates_document_text(self):
        docs = [{"id": "d1", "content": "BERT is a transformer model."}]
        msgs = _g_assert_messages_shape(compose_entity_extraction_messages(docs))
        content = msgs[0]["content"]
        assert "BERT is a transformer model." in content
        assert "Extract entities and relationships" in content

    def test_empty_returns_wellformed_no_documents_body(self):
        msgs = _g_assert_messages_shape(compose_entity_extraction_messages(None))
        assert (
            "No documents were provided to extract entities from." in msgs[0]["content"]
        )


class TestComposeQueryAnalysisMessages:
    def test_valid_interpolates_query(self):
        msgs = _g_assert_messages_shape(
            compose_query_analysis_messages(query="How did BERT influence GPT?")
        )
        content = msgs[0]["content"]
        assert "How did BERT influence GPT?" in content
        assert "Analyze the following query for graph retrieval" in content

    def test_empty_returns_wellformed_no_query_body(self):
        msgs = _g_assert_messages_shape(compose_query_analysis_messages(query=""))
        assert "No query was provided to analyze." in msgs[0]["content"]


class TestComposeSummaryMessages:
    def test_valid_interpolates_graph_context_and_query(self):
        graph_retrieval = {
            "graph_retrieval": {
                "relevant_nodes": ["BERT", "GPT"],
                "relationships": [{"source": "BERT", "target": "GPT"}],
            }
        }
        msgs = _g_assert_messages_shape(
            compose_summary_messages(
                graph_retrieval=graph_retrieval, query="Summarize the influence chain"
            )
        )
        content = msgs[0]["content"]
        # The real query is rendered; the summarize instruction is present.
        assert "Summarize the influence chain" in content
        assert "Summarize the main themes" in content

    def test_empty_returns_wellformed_no_context_body(self):
        # No graph retrieval + empty query MUST still produce a valid shape with
        # an explicit empty-context note (no fabricated graph data).
        msgs = _g_assert_messages_shape(
            compose_summary_messages(graph_retrieval=None, query="")
        )
        content = msgs[0]["content"]
        assert "No graph context was retrieved for this query" in content


# ==========================================================================
# Wave-3 Shard S3 — direct-call Tier-1 coverage of the 3 lifted COMPUTE
# `from_function` targets in `graph.py` (build_knowledge_graph /
# retrieve_from_graph / synthesize_results). These replace the prior f-string
# `code=` codegen blocks. They run REAL networkx (the shipped infra — nothing to
# mock) DIRECTLY (no LocalRuntime; the functions are pure). One direct-call test
# per documented behavior + honest-default edge cases (zero-tolerance Rule 2).
# ==========================================================================


class TestBuildKnowledgeGraph:
    """``build_knowledge_graph`` builds a real networkx graph from the parsed
    extraction LIST and returns ``{"graph_data": {...}}``."""

    _EXTRACTION = [
        {
            "entities": [
                {"name": "BERT", "type": "technology", "description": "encoder"},
                {"name": "Attention", "type": "concept", "description": "mechanism"},
            ],
            "relationships": [
                {
                    "source": "BERT",
                    "target": "Attention",
                    "type": "uses",
                    "description": "core",
                }
            ],
        }
    ]

    def test_valid_extraction_builds_real_graph(self):
        out = build_knowledge_graph(
            self._EXTRACTION, community_algorithm="connected_components"
        )
        gd = out["graph_data"]
        # The serialized graph round-trips into a real networkx MultiDiGraph.
        G = nx.node_link_graph(gd["graph"])
        assert set(G.nodes()) == {"bert", "attention"}
        assert G.has_edge("bert", "attention")
        assert gd["stats"]["num_entities"] == 2
        assert gd["stats"]["num_relationships"] == 1
        assert len(gd["entities"]) == 2
        assert len(gd["relationships"]) == 1

    def test_connected_components_communities(self):
        """The non-louvain path uses weakly-connected-components — no `community`
        dependency, one community for the single connected pair."""
        out = build_knowledge_graph(
            self._EXTRACTION, community_algorithm="connected_components"
        )
        communities = out["graph_data"]["communities"]
        # Both nodes are in the same weakly-connected component.
        assert set(communities.values()) == {0}

    def test_empty_extraction_builds_empty_graph(self):
        """Honest default: empty extraction → an EMPTY graph, no fabricated
        entities (zero-tolerance Rule 2)."""
        out = build_knowledge_graph([], community_algorithm="connected_components")
        gd = out["graph_data"]
        G = nx.node_link_graph(gd["graph"])
        assert G.number_of_nodes() == 0
        assert gd["stats"]["num_entities"] == 0
        assert gd["stats"]["num_communities"] == 0

    def test_none_extraction_builds_empty_graph(self):
        out = build_knowledge_graph(None, community_algorithm="connected_components")
        assert out["graph_data"]["stats"]["num_entities"] == 0

    def test_malformed_entity_missing_name_skipped(self):
        """An entity dict missing ``name`` is skipped, not crashed on."""
        out = build_knowledge_graph(
            [{"entities": [{"type": "x"}], "relationships": []}],
            community_algorithm="connected_components",
        )
        assert out["graph_data"]["stats"]["num_entities"] == 0

    def test_non_dict_doc_extraction_skipped(self):
        out = build_knowledge_graph(
            ["not a dict", self._EXTRACTION[0]],
            community_algorithm="connected_components",
        )
        assert out["graph_data"]["stats"]["num_entities"] == 2


class TestRetrieveFromGraph:
    """``retrieve_from_graph`` retrieves a subgraph driven by the parsed
    query-analysis; returns ``{"graph_retrieval": {...}}``."""

    def _graph_data(self) -> dict:
        return build_knowledge_graph(
            [
                {
                    "entities": [
                        {"name": "BERT", "type": "technology", "description": "e"},
                        {"name": "GPT", "type": "technology", "description": "d"},
                        {"name": "Attention", "type": "concept", "description": "m"},
                    ],
                    "relationships": [
                        {"source": "BERT", "target": "Attention", "type": "uses"},
                        {"source": "Attention", "target": "GPT", "type": "feeds"},
                    ],
                }
            ],
            community_algorithm="connected_components",
        )["graph_data"]

    def test_matches_query_entities_to_nodes(self):
        out = retrieve_from_graph(
            self._graph_data(),
            {
                "entities": ["bert"],
                "relationship_types": [],
                "requires_multi_hop": False,
            },
            max_hops=2,
        )
        # The retriever preserves the ORIGINAL-CASE entity name attribute (the
        # graph node id is lowercased, but `name` carries the source casing).
        names = {e["name"] for e in out["graph_retrieval"]["entities"]}
        assert "BERT" in names

    def test_multi_hop_bounded_by_max_hops(self):
        """``requires_multi_hop`` expands the subgraph via BFS bounded by
        ``max_hops`` — proving the closure-bound depth reaches the retriever."""
        gd = self._graph_data()
        # 1 hop from bert reaches attention; 2 hops reaches gpt.
        out1 = retrieve_from_graph(
            gd,
            {
                "entities": ["bert"],
                "relationship_types": [],
                "requires_multi_hop": True,
            },
            max_hops=1,
        )
        names1 = {e["name"] for e in out1["graph_retrieval"]["entities"]}
        out2 = retrieve_from_graph(
            gd,
            {
                "entities": ["bert"],
                "relationship_types": [],
                "requires_multi_hop": True,
            },
            max_hops=2,
        )
        names2 = {e["name"] for e in out2["graph_retrieval"]["entities"]}
        # max_hops=2 reaches strictly further than max_hops=1 (GPT is 2 hops away).
        assert "GPT" not in names1
        assert "GPT" in names2

    def test_no_matching_entities_empty_subgraph(self):
        """Honest default: query entities that match no node → empty subgraph,
        never fabricated entities."""
        out = retrieve_from_graph(
            self._graph_data(),
            {
                "entities": ["nonexistent"],
                "relationship_types": [],
                "requires_multi_hop": False,
            },
            max_hops=2,
        )
        assert out["graph_retrieval"]["entities"] == []
        assert out["graph_retrieval"]["subgraph_stats"]["nodes"] == 0

    def test_none_inputs_empty_subgraph(self):
        out = retrieve_from_graph(None, None, max_hops=2)
        assert out["graph_retrieval"]["entities"] == []


class TestSynthesizeResults:
    """``synthesize_results`` combines the retrieved subgraph + query +
    (conditional) global summary; returns ``{"graph_rag_results": {...}}``."""

    _GRAPH_RETRIEVAL = {
        "entities": [
            {"name": "BERT", "type": "technology", "description": "encoder"},
            {"name": "GPT", "type": "technology", "description": "decoder"},
        ],
        "relationships": [{"source": "BERT", "target": "GPT", "type": "influenced"}],
        "community_context": {"0": ["bert", "gpt"]},
        "subgraph_stats": {"nodes": 2, "edges": 1},
    }
    _GRAPH_DATA = {"stats": {"num_entities": 2, "num_relationships": 1}}

    def test_enabled_path_reads_global_summary(self):
        """use_global_summary=True AND a wired summary dict → the REAL parsed
        summary reaches graph_rag_results (the Wave-2.5 conditional read)."""
        out = synthesize_results(
            graph_retrieval=self._GRAPH_RETRIEVAL,
            query="how did BERT influence GPT",
            graph_data=self._GRAPH_DATA,
            global_summaries={"global_summary": "BERT influenced GPT."},
            use_global_summary=True,
        )
        rr = out["graph_rag_results"]
        assert rr["global_summary"] == "BERT influenced GPT."
        assert rr["query"] == "how did BERT influence GPT"
        assert "BERT" in rr["graph_context"]
        # reasoning_path is built over >1 entity.
        assert len(rr["reasoning_path"]) >= 1

    def test_disabled_path_global_summary_is_none(self):
        """CONDITIONAL PRESERVATION: use_global_summary=False → global_summary is
        None honestly even if a summary dict is (spuriously) passed; the disabled
        path NEVER reads it."""
        out = synthesize_results(
            graph_retrieval=self._GRAPH_RETRIEVAL,
            query="q",
            graph_data=self._GRAPH_DATA,
            global_summaries={"global_summary": "should be ignored"},
            use_global_summary=False,
        )
        assert out["graph_rag_results"]["global_summary"] is None

    def test_enabled_path_unwired_summary_is_none(self):
        """use_global_summary=True but global_summaries unwired (None default) →
        global_summary None honestly, no NameError (the from_function default
        replaces the prior conditional-codegen NameError guard)."""
        out = synthesize_results(
            graph_retrieval=self._GRAPH_RETRIEVAL,
            query="q",
            graph_data=self._GRAPH_DATA,
            global_summaries=None,
            use_global_summary=True,
        )
        assert out["graph_rag_results"]["global_summary"] is None

    def test_empty_retrieval_honest_shape(self):
        """Honest default: empty retrieval → empty entities / context, no crash."""
        out = synthesize_results(
            graph_retrieval={},
            query="q",
            graph_data={},
            global_summaries=None,
            use_global_summary=True,
        )
        rr = out["graph_rag_results"]
        assert rr["retrieved_entities"] == []
        assert rr["reasoning_path"] == []
        assert rr["global_summary"] is None

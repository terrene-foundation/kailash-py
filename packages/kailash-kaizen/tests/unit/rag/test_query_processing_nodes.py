"""Tier 1 unit coverage — ``kaizen.nodes.rag.query_processing``.

F8 shard B8. The 6 ``Node`` subclasses covered are the pre-retrieval half
of every preserved RAG pipeline — query expansion, decomposition, rewriting,
intent classification, multi-hop planning, and the adaptive processor that
composes them.

Tier 1 scope: construction with default + custom kwargs, ``get_parameters()``
contracts, the deterministic ``run()`` heuristics each class ships, and the
inner workflow GRAPH SHAPE produced by each ``_create_workflow``. The LLM-using
classes (Expansion / Decomposition / Rewriting / IntentClassifier) are
exercised at the workflow-construction surface only — no live LLM calls.
End-to-end execution against real LLMs is out of scope for Tier 1.

The 4 LLM-using nodes embed ``LLMAgentNode`` instances in their inner workflow
graphs; this file asserts on the wired ``system_prompt`` / ``model`` config the
graph carries — NOT on raw LLM-call output content.
"""

from __future__ import annotations

import pytest
from kailash.workflow.graph import Workflow

from kaizen.nodes.rag.query_processing import (
    AdaptiveQueryProcessorNode,
    MultiHopQueryPlannerNode,
    QueryDecompositionNode,
    QueryExpansionNode,
    QueryIntentClassifierNode,
    QueryRewritingNode,
)

pytestmark = pytest.mark.unit


def _node(workflow: Workflow, node_id: str):
    """Narrow ``Workflow.get_node`` (``Node | None``) to a concrete Node.

    Every ``_create_workflow`` under test always emits the named node; the
    assert turns the static ``| None`` into a concrete type for the checker
    and fails loudly if a builder stops emitting it.
    """
    found = workflow.get_node(node_id)
    assert found is not None, node_id
    return found


def _build(node) -> Workflow:
    """Call ``node._create_workflow()`` past the ``@register_node`` Node-type erasure.

    Mirrors the B7 ``_wf`` precedent (`tests/unit/rag/test_workflows_nodes.py`):
    ``@register_node()`` erases the concrete subclass to ``Node`` for static
    checkers, so ``_create_workflow`` becomes invisible. The single
    suppression here lets every call site stay clean.
    """
    return node._create_workflow()  # type: ignore[attr-defined]


_ALL_CLASSES = [
    QueryExpansionNode,
    QueryDecompositionNode,
    QueryRewritingNode,
    QueryIntentClassifierNode,
    MultiHopQueryPlannerNode,
    AdaptiveQueryProcessorNode,
]


# ==========================================================================
# Cross-class construction + parameter contracts
# ==========================================================================


class TestAllNodesConstruct:
    """Each of the 6 nodes constructs with no args and exposes ``query``."""

    @pytest.mark.parametrize("cls", _ALL_CLASSES)
    def test_constructs_default(self, cls):
        node = cls()
        assert node is not None
        # Each node's default name (carried on the base-Node metadata)
        # follows the documented convention.
        assert isinstance(node.metadata.name, str)
        assert node.metadata.name  # non-empty

    @pytest.mark.parametrize("cls", _ALL_CLASSES)
    def test_get_parameters_declares_query_required(self, cls):
        """`query` is the canonical required input for every node."""
        params = cls().get_parameters()
        assert "query" in params
        assert params["query"].required is True
        assert params["query"].type is str

    @pytest.mark.parametrize("cls", _ALL_CLASSES)
    def test_get_parameters_name_is_optional(self, cls):
        """`name` is an overridable, non-required identifier on every node."""
        params = cls().get_parameters()
        assert "name" in params
        assert params["name"].required is False


# ==========================================================================
# QueryExpansionNode — has constructor kwargs (expansion_method, num_expansions)
# ==========================================================================


class TestQueryExpansionNode:
    def test_constructs_with_custom_kwargs(self):
        node = QueryExpansionNode(
            name="custom_expander",
            expansion_method="wordnet",
            num_expansions=3,
        )
        assert node.metadata.name == "custom_expander"
        # @register_node erases QueryExpansionNode→Node for static checkers;
        # `expansion_method` / `num_expansions` are real instance attrs (A3).
        assert node.expansion_method == "wordnet"  # type: ignore[attr-defined]
        assert node.num_expansions == 3  # type: ignore[attr-defined]

    def test_parameter_defaults_match_init_defaults(self):
        params = QueryExpansionNode().get_parameters()
        assert params["expansion_method"].default == "llm"
        assert params["num_expansions"].default == 5

    def test_run_returns_documented_shape(self):
        """`run` returns the documented keys for a non-empty query."""
        out = QueryExpansionNode().run(query="ML optimization")
        assert set(out.keys()) >= {
            "original",
            "expansions",
            "keywords",
            "concepts",
            "all_terms",
        }
        assert out["original"] == "ML optimization"
        assert isinstance(out["expansions"], list)
        assert isinstance(out["all_terms"], list)

    def test_run_honors_num_expansions_truncation(self):
        """`num_expansions` truncates the deterministic expansion list."""
        out = QueryExpansionNode(num_expansions=2).run(query="ML optimization")
        assert len(out["expansions"]) == 2

    def test_run_empty_query_returns_empty_lists(self):
        out = QueryExpansionNode().run(query="")
        assert out["original"] == ""
        assert out["expansions"] == []
        assert out["keywords"] == []

    def test_create_workflow_graph_shape(self):
        """The inner workflow wires llm_expander → expansion_parser →
        expansion_processor (O4 output-side parse)."""
        wf = _build(QueryExpansionNode())
        # L3 messages-composer fix: an `expansion_messages_composer` node renders
        # the real query into the llm_expander `messages` port. O4 output-side
        # fix: an `expansion_parser` node unwraps the LLM `response.content` +
        # json.loads before the processor reads it.
        assert set(wf.nodes.keys()) == {
            "expansion_messages_composer",
            "llm_expander",
            "expansion_parser",
            "expansion_processor",
        }
        # O4: the direct llm_expander -> expansion_processor edge is REMOVED;
        # the response now routes THROUGH the parser.
        assert not [
            c
            for c in wf.connections
            if c.source_node == "llm_expander"
            and c.target_node == "expansion_processor"
        ]
        # llm_expander.response -> expansion_parser.response.
        parse_in = [
            c
            for c in wf.connections
            if c.source_node == "llm_expander" and c.target_node == "expansion_parser"
        ]
        assert len(parse_in) == 1
        assert parse_in[0].source_output == "response"
        assert parse_in[0].target_input == "response"
        # expansion_parser.result -> expansion_processor.expansion_response.
        parse_out = [
            c
            for c in wf.connections
            if c.source_node == "expansion_parser"
            and c.target_node == "expansion_processor"
        ]
        assert len(parse_out) == 1
        assert parse_out[0].source_output == "result"
        assert parse_out[0].target_input == "expansion_response"
        # The composer feeds the VALID `messages` port (result.messages).
        msg_edge = [
            c
            for c in wf.connections
            if c.source_node == "expansion_messages_composer"
            and c.target_node == "llm_expander"
        ]
        assert len(msg_edge) == 1
        assert msg_edge[0].source_output == "result.messages"
        assert msg_edge[0].target_input == "messages"

    def test_create_workflow_llm_expander_has_system_prompt(self):
        """The LLM expander carries a non-empty system_prompt + has the
        model field (F9 #1126: model resolves from env per env-models.md;
        the field is present even when env vars are unset)."""
        wf = _build(QueryExpansionNode())
        llm = _node(wf, "llm_expander")
        prompt = llm.config.get("system_prompt", "")
        assert "query expansion" in prompt.lower()
        # The `model` key MUST be present in the config (env-default may be None).
        assert "model" in llm.config

    def test_create_workflow_num_expansions_baked_into_prompt(self):
        """`num_expansions` flows into the LLM system_prompt text."""
        wf = _build(QueryExpansionNode(num_expansions=7))
        llm = _node(wf, "llm_expander")
        assert "7" in llm.config["system_prompt"]


# ==========================================================================
# QueryDecompositionNode
# ==========================================================================


class TestQueryDecompositionNode:
    def test_constructs_with_custom_name(self):
        node = QueryDecompositionNode(name="custom_decomp")
        assert node.metadata.name == "custom_decomp"

    def test_run_decomposes_and_query(self):
        """A query containing ' and ' decomposes into multiple sub-questions."""
        out = QueryDecompositionNode().run(query="What is BERT and how does it work")
        assert "sub_questions" in out
        assert len(out["sub_questions"]) >= 2
        assert out["composition_strategy"] == "sequential"

    def test_run_decomposes_comparative_query(self):
        out = QueryDecompositionNode().run(
            query="Compare transformers vs CNNs for vision"
        )
        assert len(out["sub_questions"]) == 3

    def test_run_single_query_when_no_pattern_match(self):
        out = QueryDecompositionNode().run(query="What is gradient descent")
        assert out["sub_questions"] == ["What is gradient descent"]
        assert out["total_questions"] == 1

    def test_run_execution_order_matches_sub_questions(self):
        out = QueryDecompositionNode().run(query="A and B and C")
        assert out["execution_order"] == list(range(len(out["sub_questions"])))

    def test_create_workflow_graph_shape(self):
        """Decomposition wires query_decomposer → decomposition_parser →
        dependency_resolver (O4 output-side parse)."""
        wf = _build(QueryDecompositionNode())
        # L3 messages-composer fix: a `decomposition_messages_composer` node
        # renders the real query into the query_decomposer `messages` port. O4
        # output-side fix: a `decomposition_parser` node unwraps the LLM
        # `response.content` + json.loads before the resolver reads it.
        assert set(wf.nodes.keys()) == {
            "decomposition_messages_composer",
            "query_decomposer",
            "decomposition_parser",
            "dependency_resolver",
        }
        # O4: the direct query_decomposer -> dependency_resolver edge is REMOVED.
        assert not [
            c
            for c in wf.connections
            if c.source_node == "query_decomposer"
            and c.target_node == "dependency_resolver"
        ]
        parse_in = [
            c
            for c in wf.connections
            if c.source_node == "query_decomposer"
            and c.target_node == "decomposition_parser"
        ]
        assert len(parse_in) == 1
        assert parse_in[0].source_output == "response"
        assert parse_in[0].target_input == "response"
        parse_out = [
            c
            for c in wf.connections
            if c.source_node == "decomposition_parser"
            and c.target_node == "dependency_resolver"
        ]
        assert len(parse_out) == 1
        assert parse_out[0].source_output == "result"
        assert parse_out[0].target_input == "decomposition_result"
        msg_edge = [
            c
            for c in wf.connections
            if c.source_node == "decomposition_messages_composer"
            and c.target_node == "query_decomposer"
        ]
        assert len(msg_edge) == 1
        assert msg_edge[0].source_output == "result.messages"
        assert msg_edge[0].target_input == "messages"

    def test_create_workflow_decomposer_prompt_is_topical(self):
        wf = _build(QueryDecompositionNode())
        llm = _node(wf, "query_decomposer")
        prompt = llm.config.get("system_prompt", "")
        assert "decomposition" in prompt.lower()
        # F9 #1126: model resolves from env per env-models.md; field
        # present even when env vars are unset.
        assert "model" in llm.config


# ==========================================================================
# QueryRewritingNode
# ==========================================================================


class TestQueryRewritingNode:
    def test_constructs_with_custom_name(self):
        node = QueryRewritingNode(name="custom_rewriter")
        assert node.metadata.name == "custom_rewriter"

    def test_run_corrects_documented_typos(self):
        """The deterministic corrector hits ``trian`` / ``nueral`` / ``netwrk``."""
        out = QueryRewritingNode().run(query="how to trian nueral netwrk wit keras")
        assert "versions" in out
        assert "corrected" in out["versions"]
        assert "spelling_errors" in out["issues_found"]
        # The correction substitutes the documented typos.
        corrected = out["versions"]["corrected"]
        assert "neural" in corrected
        assert "network" in corrected

    def test_run_generates_five_variants(self):
        out = QueryRewritingNode().run(query="how to trian nueral netwrk")
        # The documented variants: corrected, clarified, contextualized,
        # simplified, technical.
        assert set(out["versions"].keys()) == {
            "corrected",
            "clarified",
            "contextualized",
            "simplified",
            "technical",
        }

    def test_run_short_query_flagged_too_short(self):
        out = QueryRewritingNode().run(query="ML")
        assert "too_short" in out["issues_found"]

    def test_run_empty_query_returns_no_versions(self):
        out = QueryRewritingNode().run(query="")
        assert out["versions"] == {}
        assert out["recommended"] == ""

    def test_create_workflow_graph_shape(self):
        """analyzer → analysis_parser → {rewrite_composer, combiner};
        rewriter → rewrite_parser → combiner (O4 output-side parse)."""
        wf = _build(QueryRewritingNode())
        # L3 messages-composer fix: two composer nodes render the real query (+
        # upstream analysis) into the two LLM stages' `messages` ports. O4
        # output-side fix: an `analysis_parser` + `rewrite_parser` unwrap each
        # LLM `response.content` + json.loads; the parsed analysis is fanned to
        # BOTH the rewrite composer AND the combiner.
        assert set(wf.nodes.keys()) == {
            "analysis_messages_composer",
            "rewrite_messages_composer",
            "query_analyzer",
            "query_rewriter",
            "analysis_parser",
            "rewrite_parser",
            "result_combiner",
        }
        sources = [(c.source_node, c.target_node) for c in wf.connections]
        # The phantom analyzer->rewriter direct edge is GONE.
        assert ("query_analyzer", "query_rewriter") not in sources
        # O4: the raw analyzer/rewriter -> consumer edges are REMOVED; the
        # responses route THROUGH the parsers.
        assert ("query_analyzer", "result_combiner") not in sources
        assert ("query_analyzer", "rewrite_messages_composer") not in sources
        assert ("query_rewriter", "result_combiner") not in sources
        # Analyzer.response -> analysis_parser; rewriter.response -> rewrite_parser.
        assert ("query_analyzer", "analysis_parser") in sources
        assert ("query_rewriter", "rewrite_parser") in sources
        # Parsed analysis fans to BOTH the rewrite composer AND the combiner.
        assert ("analysis_parser", "rewrite_messages_composer") in sources
        assert ("analysis_parser", "result_combiner") in sources
        # Parsed rewrites reach the combiner.
        assert ("rewrite_parser", "result_combiner") in sources
        # Parser edges carry result -> target_input.
        ap_to_combiner = [
            c
            for c in wf.connections
            if c.source_node == "analysis_parser" and c.target_node == "result_combiner"
        ]
        assert len(ap_to_combiner) == 1
        assert ap_to_combiner[0].source_output == "result"
        assert ap_to_combiner[0].target_input == "analysis_result"
        rp_to_combiner = [
            c
            for c in wf.connections
            if c.source_node == "rewrite_parser" and c.target_node == "result_combiner"
        ]
        assert len(rp_to_combiner) == 1
        assert rp_to_combiner[0].source_output == "result"
        assert rp_to_combiner[0].target_input == "rewrite_result"
        ap_to_composer = [
            c
            for c in wf.connections
            if c.source_node == "analysis_parser"
            and c.target_node == "rewrite_messages_composer"
        ]
        assert len(ap_to_composer) == 1
        assert ap_to_composer[0].source_output == "result"
        assert ap_to_composer[0].target_input == "analysis"
        # Each LLM stage receives its `messages` from its composer.
        analyzer_msg = [
            c
            for c in wf.connections
            if c.source_node == "analysis_messages_composer"
            and c.target_node == "query_analyzer"
        ]
        assert len(analyzer_msg) == 1
        assert analyzer_msg[0].source_output == "result.messages"
        assert analyzer_msg[0].target_input == "messages"
        rewriter_msg = [
            c
            for c in wf.connections
            if c.source_node == "rewrite_messages_composer"
            and c.target_node == "query_rewriter"
        ]
        assert len(rewriter_msg) == 1
        assert rewriter_msg[0].source_output == "result.messages"
        assert rewriter_msg[0].target_input == "messages"

    def test_create_workflow_analyzer_and_rewriter_are_distinct_llms(self):
        """Both LLM nodes carry distinct, topical system_prompts."""
        wf = _build(QueryRewritingNode())
        analyzer = _node(wf, "query_analyzer")
        rewriter = _node(wf, "query_rewriter")
        analyzer_prompt = analyzer.config.get("system_prompt", "")
        rewriter_prompt = rewriter.config.get("system_prompt", "")
        assert "issues" in analyzer_prompt.lower()
        assert "rewrite" in rewriter_prompt.lower()
        assert analyzer_prompt != rewriter_prompt


# ==========================================================================
# QueryIntentClassifierNode — deterministic 5-axis classifier
# ==========================================================================


class TestQueryIntentClassifierNode:
    @pytest.mark.parametrize(
        "query, expected_type",
        [
            ("What is BERT", "factual"),
            ("How does gradient descent work", "analytical"),
            ("Compare CNN vs RNN", "comparative"),
            ("List relevant papers please", "exploratory"),
            ("Implement gradient descent in Python", "procedural"),
        ],
    )
    def test_query_type_classification(self, query, expected_type):
        out = QueryIntentClassifierNode().run(query=query)
        assert out["query_type"] == expected_type

    @pytest.mark.parametrize(
        "query, expected_domain",
        [
            ("Show me Python code for sorting", "technical"),
            ("Q3 sales forecast for the business", "business"),
            ("Latest research paper on transformers", "academic"),
            ("What is happiness", "general"),
        ],
    )
    def test_domain_classification(self, query, expected_domain):
        out = QueryIntentClassifierNode().run(query=query)
        assert out["domain"] == expected_domain

    @pytest.mark.parametrize(
        "query, expected_complexity",
        [
            ("What is X", "simple"),
            ("How does gradient descent work in Python", "moderate"),
            (
                "Explain why transformer architectures outperform "
                "convolutional neural networks for NLP tasks today",
                "complex",
            ),
        ],
    )
    def test_complexity_classification(self, query, expected_complexity):
        out = QueryIntentClassifierNode().run(query=query)
        assert out["complexity"] == expected_complexity

    def test_recommended_strategy_set(self):
        """Every classification returns a recommended_strategy + confidence."""
        out = QueryIntentClassifierNode().run(query="What is BERT")
        assert out["recommended_strategy"] in {
            "sparse",
            "hybrid",
            "semantic",
            "hierarchical",
            "multi_vector",
            "self_correcting",
        }
        assert 0.0 < out["confidence"] <= 1.0

    def test_requirements_detect_examples_signal(self):
        out = QueryIntentClassifierNode().run(query="Show me an example")
        assert "needs_examples" in out["requirements"]

    def test_requirements_detect_recency_signal(self):
        out = QueryIntentClassifierNode().run(
            query="What are the latest research findings"
        )
        assert "needs_recent" in out["requirements"]

    def test_create_workflow_graph_shape(self):
        """intent_classifier → intent_parser → strategy_mapper (O4 parse)."""
        wf = _build(QueryIntentClassifierNode())
        # L3 messages-composer fix: an `intent_messages_composer` node renders
        # the real query into the intent_classifier `messages` port. O4
        # output-side fix: an `intent_parser` node unwraps the LLM
        # `response.content` + json.loads before the strategy_mapper reads it.
        assert set(wf.nodes.keys()) == {
            "intent_messages_composer",
            "intent_classifier",
            "intent_parser",
            "strategy_mapper",
        }
        # O4: the direct intent_classifier -> strategy_mapper edge is REMOVED.
        assert not [
            c
            for c in wf.connections
            if c.source_node == "intent_classifier"
            and c.target_node == "strategy_mapper"
        ]
        parse_in = [
            c
            for c in wf.connections
            if c.source_node == "intent_classifier" and c.target_node == "intent_parser"
        ]
        assert len(parse_in) == 1
        assert parse_in[0].source_output == "response"
        assert parse_in[0].target_input == "response"
        parse_out = [
            c
            for c in wf.connections
            if c.source_node == "intent_parser" and c.target_node == "strategy_mapper"
        ]
        assert len(parse_out) == 1
        assert parse_out[0].source_output == "result"
        assert parse_out[0].target_input == "intent_classification"
        msg_edge = [
            c
            for c in wf.connections
            if c.source_node == "intent_messages_composer"
            and c.target_node == "intent_classifier"
        ]
        assert len(msg_edge) == 1
        assert msg_edge[0].source_output == "result.messages"
        assert msg_edge[0].target_input == "messages"

    def test_create_workflow_classifier_prompt_describes_taxonomy(self):
        wf = _build(QueryIntentClassifierNode())
        llm = _node(wf, "intent_classifier")
        prompt = llm.config.get("system_prompt", "")
        # The 5 documented query-type labels appear in the prompt taxonomy.
        for label in (
            "factual",
            "analytical",
            "comparative",
            "exploratory",
            "procedural",
        ):
            assert label in prompt


# ==========================================================================
# MultiHopQueryPlannerNode — deterministic hop builder
# ==========================================================================


class TestMultiHopQueryPlannerNode:
    def test_constructs_with_custom_name(self):
        node = MultiHopQueryPlannerNode(name="custom_planner")
        assert node.metadata.name == "custom_planner"

    def test_run_influence_query_produces_three_hops(self):
        """An ``influence`` query yields the documented 3-hop chain."""
        out = MultiHopQueryPlannerNode().run(query="How has BERT influenced modern NLP")
        # 3 hops, the third depending on the first two.
        assert out["total_hops"] == 3
        # Final hop depends on the prior hops by hop_number.
        third = out["batches"][-1][0] if out["batches"][-1] else None
        # Each batch only contains hops whose dependencies are processed.
        assert third is not None
        assert sorted(third.get("depends_on", [])) == [1, 2]

    def test_run_impact_query_also_multi_hop(self):
        out = MultiHopQueryPlannerNode().run(query="What is the impact of transformers")
        assert out["total_hops"] == 3

    def test_run_simple_query_one_hop(self):
        out = MultiHopQueryPlannerNode().run(query="What is BERT")
        assert out["total_hops"] == 1
        assert out["parallel_opportunities"] == 0

    def test_run_batches_are_dependency_correct(self):
        """No hop appears in a batch before all its deps are processed."""
        out = MultiHopQueryPlannerNode().run(query="How has BERT influenced NLP")
        processed: set[int] = set()
        for batch in out["batches"]:
            for hop in batch:
                deps = set(hop.get("depends_on", []))
                assert deps.issubset(
                    processed
                ), f"hop {hop['hop_number']} depends on {deps - processed}"
            for hop in batch:
                processed.add(hop["hop_number"])

    def test_create_workflow_graph_shape(self):
        """hop_planner → hop_plan_parser → execution_planner (O4 parse)."""
        wf = _build(MultiHopQueryPlannerNode())
        # L3 messages-composer fix: a `hop_plan_messages_composer` node renders
        # the real query into the hop_planner `messages` port. O4 output-side
        # fix: a `hop_plan_parser` node unwraps the LLM `response.content` +
        # json.loads before the execution_planner reads it.
        assert set(wf.nodes.keys()) == {
            "hop_plan_messages_composer",
            "hop_planner",
            "hop_plan_parser",
            "execution_planner",
        }
        # O4: the direct hop_planner -> execution_planner edge is REMOVED.
        assert not [
            c
            for c in wf.connections
            if c.source_node == "hop_planner" and c.target_node == "execution_planner"
        ]
        parse_in = [
            c
            for c in wf.connections
            if c.source_node == "hop_planner" and c.target_node == "hop_plan_parser"
        ]
        assert len(parse_in) == 1
        assert parse_in[0].source_output == "response"
        assert parse_in[0].target_input == "response"
        parse_out = [
            c
            for c in wf.connections
            if c.source_node == "hop_plan_parser"
            and c.target_node == "execution_planner"
        ]
        assert len(parse_out) == 1
        assert parse_out[0].source_output == "result"
        assert parse_out[0].target_input == "hop_plan_result"
        msg_edge = [
            c
            for c in wf.connections
            if c.source_node == "hop_plan_messages_composer"
            and c.target_node == "hop_planner"
        ]
        assert len(msg_edge) == 1
        assert msg_edge[0].source_output == "result.messages"
        assert msg_edge[0].target_input == "messages"

    def test_create_workflow_hop_planner_prompt_topical(self):
        wf = _build(MultiHopQueryPlannerNode())
        llm = _node(wf, "hop_planner")
        prompt = llm.config.get("system_prompt", "")
        assert "multi-hop" in prompt.lower()


# ==========================================================================
# AdaptiveQueryProcessorNode — composes the other 5 via the inner workflow
# ==========================================================================


class TestAdaptiveQueryProcessorNode:
    def test_constructs_with_custom_name(self):
        node = AdaptiveQueryProcessorNode(name="custom_adaptive")
        assert node.metadata.name == "custom_adaptive"

    def test_run_returns_documented_shape(self):
        out = AdaptiveQueryProcessorNode().run(query="Compare X and Y")
        assert set(out.keys()) >= {
            "original_query",
            "processing_steps",
            "processed_query",
            "processing_plan",
            "expected_improvement",
        }

    def test_run_comparative_query_triggers_decompose(self):
        out = AdaptiveQueryProcessorNode().run(query="Compare X vs Y")
        assert "decompose" in out["processing_steps"]

    def test_run_influence_query_triggers_multi_hop(self):
        out = AdaptiveQueryProcessorNode().run(query="How has BERT influenced NLP")
        assert "multi_hop" in out["processing_steps"]

    def test_run_short_query_triggers_expand(self):
        out = AdaptiveQueryProcessorNode().run(query="ML")
        assert "expand" in out["processing_steps"]

    def test_run_plain_query_falls_back_to_analyze(self):
        """A query matching none of the heuristics defaults to analyze.

        The query MUST avoid: any 'u' / '2' / 'wit' / 'trian' substring (the
        rewrite trigger uses ``char in query`` against single letters AND
        substrings), 'compare' / 'vs' (decompose trigger), 'influence' /
        'impact' (multi-hop trigger), AND it MUST be >=4 words (else expand
        triggers). ``overview of transformer models`` satisfies all three.
        """
        out = AdaptiveQueryProcessorNode().run(query="overview of transformer models")
        assert out["processing_steps"] == ["analyze"]

    def test_create_workflow_embeds_intent_classifier(self):
        """The adaptive inner workflow uses QueryIntentClassifierNode."""
        wf = _build(AdaptiveQueryProcessorNode())
        assert "intent_analyzer" in wf.nodes
        assert "adaptive_processor" in wf.nodes

    def test_create_workflow_wires_routing_decision(self):
        """The intent analyzer's routing_decision flows to the adaptive processor."""
        wf = _build(AdaptiveQueryProcessorNode())
        edges = [
            c
            for c in wf.connections
            if c.source_node == "intent_analyzer"
            and c.target_node == "adaptive_processor"
        ]
        assert len(edges) == 1
        assert edges[0].source_output == "routing_decision"
        assert edges[0].target_input == "routing_decision"


# ==========================================================================
# Module-level __all__ contract
# ==========================================================================


def test_module_all_exports_six_classes():
    """The module exports exactly the 6 documented classes."""
    from kaizen.nodes.rag import query_processing as qp

    assert set(qp.__all__) == {
        "QueryExpansionNode",
        "QueryDecompositionNode",
        "QueryRewritingNode",
        "QueryIntentClassifierNode",
        "MultiHopQueryPlannerNode",
        "AdaptiveQueryProcessorNode",
    }


# ==========================================================================
# F31-FU2 Shard A — direct-call Tier-1 coverage of the pure parser / composer
# `from_function` targets (module-level functions wired into the inner
# workflows via `PythonCodeNode.from_function`). These are pure data
# rendering / tool-result parsing (the permitted deterministic exceptions per
# rules/agent-reasoning.md #3 + #6) — NOT agent decision-making. Called
# DIRECTLY (no LocalRuntime, no mocking — they are pure functions).
#
# Contract per testing.md "One Direct Test Per Variant": every parser asserts
# VALID / EMPTY / MALFORMED(non-json, non-object, unexpected-type) /
# ALREADY-DICT; every composer asserts VALID + EMPTY. zero-tolerance Rule 2:
# the EMPTY / MALFORMED sentinels assert HONEST empty defaults + the exact
# parse_error reason string — never a fabricated non-empty value.
# ==========================================================================

import json

from kaizen.nodes.rag.query_processing import (
    _adaptive_process,
    _combine_rewrites,
    _loads_response_object,
    _map_strategy,
    _plan_execution,
    _process_expansions,
    _resolve_dependencies,
    _unwrap_response_content,
    compose_analysis_messages,
    compose_decomposition_messages,
    compose_expansion_messages,
    compose_hop_plan_messages,
    compose_intent_messages,
    compose_rewrite_messages,
    parse_analysis_response,
    parse_decomposition_response,
    parse_expansion_response,
    parse_hop_plan_response,
    parse_intent_response,
    parse_rewrite_response,
)


def _wrap(obj) -> dict:
    """Build the LLMAgentNode `response` port shape with a JSON-string content."""
    return {"content": json.dumps(obj)}


class TestUnwrapResponseContent:
    """`_unwrap_response_content`: dict -> .content, bare value -> passthrough."""

    def test_unwrap_dict_returns_content(self):
        assert _unwrap_response_content({"content": "hello"}) == "hello"

    def test_unwrap_dict_missing_content_returns_none(self):
        # A dict without a "content" key -> .get("content") -> None.
        assert _unwrap_response_content({"other": "x"}) is None

    def test_unwrap_bare_string_passthrough(self):
        assert _unwrap_response_content("raw string") == "raw string"

    def test_unwrap_none_passthrough(self):
        assert _unwrap_response_content(None) is None


class TestLoadsResponseObject:
    """`_loads_response_object`: dict on valid, exact reason strings on malformed."""

    def test_valid_json_object_returns_dict(self):
        obj = {"expansions": ["a", "b"]}
        result = _loads_response_object(_wrap(obj))
        assert result == obj

    def test_already_dict_content_returns_dict(self):
        # Provider pre-parsed: content is already a dict.
        obj = {"hops": [1, 2]}
        result = _loads_response_object({"content": obj})
        assert result == obj

    def test_none_response_returns_empty_response(self):
        assert _loads_response_object(None) == "empty-response"

    def test_empty_string_content_returns_empty_response(self):
        assert _loads_response_object({"content": ""}) == "empty-response"

    def test_whitespace_content_returns_empty_response(self):
        assert _loads_response_object({"content": "   "}) == "empty-response"

    def test_non_json_content_returns_non_json_response(self):
        assert _loads_response_object({"content": "not json{"}) == "non-json-response"

    def test_json_array_returns_non_object_json(self):
        assert _loads_response_object({"content": "[1,2,3]"}) == "non-object-json"

    def test_json_scalar_returns_non_object_json(self):
        # Valid JSON that is not an object (a number).
        assert _loads_response_object({"content": "42"}) == "non-object-json"

    def test_non_str_non_dict_content_returns_unexpected_content_type(self):
        # content is an int (not str, not dict) -> unexpected-content-type.
        assert _loads_response_object({"content": 42}) == "unexpected-content-type"


# --------------------------------------------------------------------------
# Parsers — one direct test per variant (VALID / EMPTY / MALFORMED / DICT).
# --------------------------------------------------------------------------


class TestParseExpansionResponse:
    def test_parse_expansion_valid_returns_fields(self):
        obj = {
            "expansions": ["ml optimization", "model tuning"],
            "keywords": ["ml", "optimization"],
            "concepts": ["machine_learning"],
        }
        result = parse_expansion_response(_wrap(obj))
        assert result["expansions"] == obj["expansions"]
        assert result["keywords"] == obj["keywords"]
        assert result["concepts"] == obj["concepts"]
        assert "parse_error" not in result

    def test_parse_expansion_already_dict_returns_fields(self):
        obj = {"expansions": ["x"], "keywords": [], "concepts": []}
        result = parse_expansion_response({"content": obj})
        assert result["expansions"] == ["x"]
        assert "parse_error" not in result

    def test_parse_expansion_none_returns_empty_sentinel(self):
        result = parse_expansion_response(None)
        assert result["parse_error"] == "empty-response"
        # Honest empty default — NEVER a fabricated expansion (zero-tolerance R2).
        assert result["expansions"] == []
        assert result["keywords"] == []
        assert result["concepts"] == []

    def test_parse_expansion_empty_content_returns_empty_sentinel(self):
        result = parse_expansion_response({"content": ""})
        assert result["parse_error"] == "empty-response"
        assert result["expansions"] == []

    def test_parse_expansion_non_json_returns_non_json_sentinel(self):
        result = parse_expansion_response({"content": "not json{"})
        assert result["parse_error"] == "non-json-response"
        assert result["expansions"] == []
        assert result["keywords"] == []
        assert result["concepts"] == []

    def test_parse_expansion_array_returns_non_object_sentinel(self):
        result = parse_expansion_response({"content": "[1,2,3]"})
        assert result["parse_error"] == "non-object-json"
        assert result["expansions"] == []

    def test_parse_expansion_bad_content_type_returns_unexpected_sentinel(self):
        result = parse_expansion_response({"content": 42})
        assert result["parse_error"] == "unexpected-content-type"
        assert result["expansions"] == []


class TestParseDecompositionResponse:
    def test_parse_decomposition_valid_returns_fields(self):
        obj = {
            "sub_questions": [{"question": "What is X?"}],
            "composition_strategy": "parallel",
        }
        result = parse_decomposition_response(_wrap(obj))
        assert result["sub_questions"] == obj["sub_questions"]
        assert result["composition_strategy"] == "parallel"
        assert "parse_error" not in result

    def test_parse_decomposition_already_dict_returns_fields(self):
        obj = {"sub_questions": [{"question": "Q"}]}
        result = parse_decomposition_response({"content": obj})
        assert result["sub_questions"] == obj["sub_questions"]
        # Documented default when composition_strategy absent.
        assert result["composition_strategy"] == "sequential"
        assert "parse_error" not in result

    def test_parse_decomposition_none_returns_empty_sentinel(self):
        result = parse_decomposition_response(None)
        assert result["parse_error"] == "empty-response"
        assert result["sub_questions"] == []

    def test_parse_decomposition_empty_content_returns_empty_sentinel(self):
        result = parse_decomposition_response({"content": ""})
        assert result["parse_error"] == "empty-response"
        assert result["sub_questions"] == []

    def test_parse_decomposition_non_json_returns_non_json_sentinel(self):
        result = parse_decomposition_response({"content": "not json{"})
        assert result["parse_error"] == "non-json-response"
        assert result["sub_questions"] == []

    def test_parse_decomposition_array_returns_non_object_sentinel(self):
        result = parse_decomposition_response({"content": "[1,2,3]"})
        assert result["parse_error"] == "non-object-json"
        assert result["sub_questions"] == []

    def test_parse_decomposition_bad_content_type_returns_unexpected_sentinel(self):
        result = parse_decomposition_response({"content": 42})
        assert result["parse_error"] == "unexpected-content-type"
        assert result["sub_questions"] == []


class TestParseAnalysisResponse:
    def test_parse_analysis_valid_returns_fields(self):
        obj = {
            "issues": ["spelling_errors", "too_short"],
            "suggestions": {"spelling": "corrected"},
        }
        result = parse_analysis_response(_wrap(obj))
        assert result["issues"] == obj["issues"]
        assert result["suggestions"] == obj["suggestions"]
        assert "parse_error" not in result

    def test_parse_analysis_already_dict_returns_fields(self):
        obj = {"issues": ["x"]}
        result = parse_analysis_response({"content": obj})
        assert result["issues"] == ["x"]
        assert result["suggestions"] == {}  # documented default
        assert "parse_error" not in result

    def test_parse_analysis_none_returns_empty_sentinel(self):
        result = parse_analysis_response(None)
        assert result["parse_error"] == "empty-response"
        assert result["issues"] == []

    def test_parse_analysis_empty_content_returns_empty_sentinel(self):
        result = parse_analysis_response({"content": ""})
        assert result["parse_error"] == "empty-response"
        assert result["issues"] == []

    def test_parse_analysis_non_json_returns_non_json_sentinel(self):
        result = parse_analysis_response({"content": "not json{"})
        assert result["parse_error"] == "non-json-response"
        assert result["issues"] == []

    def test_parse_analysis_array_returns_non_object_sentinel(self):
        result = parse_analysis_response({"content": "[1,2,3]"})
        assert result["parse_error"] == "non-object-json"
        assert result["issues"] == []

    def test_parse_analysis_bad_content_type_returns_unexpected_sentinel(self):
        result = parse_analysis_response({"content": 42})
        assert result["parse_error"] == "unexpected-content-type"
        assert result["issues"] == []


class TestParseRewriteResponse:
    def test_parse_rewrite_valid_returns_fields(self):
        obj = {
            "rewrites": {"corrected": "fixed query", "clarified": "clearer query"},
            "recommended": "fixed query",
        }
        result = parse_rewrite_response(_wrap(obj))
        assert result["rewrites"] == obj["rewrites"]
        assert result["recommended"] == "fixed query"
        assert "parse_error" not in result

    def test_parse_rewrite_already_dict_returns_fields(self):
        obj = {"rewrites": {"corrected": "x"}}
        result = parse_rewrite_response({"content": obj})
        assert result["rewrites"] == {"corrected": "x"}
        assert result["recommended"] == ""  # documented default
        assert "parse_error" not in result

    def test_parse_rewrite_none_returns_empty_sentinel(self):
        result = parse_rewrite_response(None)
        assert result["parse_error"] == "empty-response"
        assert result["rewrites"] == {}

    def test_parse_rewrite_empty_content_returns_empty_sentinel(self):
        result = parse_rewrite_response({"content": ""})
        assert result["parse_error"] == "empty-response"
        assert result["rewrites"] == {}

    def test_parse_rewrite_non_json_returns_non_json_sentinel(self):
        result = parse_rewrite_response({"content": "not json{"})
        assert result["parse_error"] == "non-json-response"
        assert result["rewrites"] == {}

    def test_parse_rewrite_array_returns_non_object_sentinel(self):
        result = parse_rewrite_response({"content": "[1,2,3]"})
        assert result["parse_error"] == "non-object-json"
        assert result["rewrites"] == {}

    def test_parse_rewrite_bad_content_type_returns_unexpected_sentinel(self):
        result = parse_rewrite_response({"content": 42})
        assert result["parse_error"] == "unexpected-content-type"
        assert result["rewrites"] == {}


class TestParseIntentResponse:
    def test_parse_intent_valid_returns_fields(self):
        obj = {
            "query_type": "procedural",
            "domain": "technical",
            "complexity": "moderate",
            "requirements": ["needs_examples"],
            "suggested_strategy": "semantic",
        }
        result = parse_intent_response(_wrap(obj))
        assert result["query_type"] == "procedural"
        assert result["domain"] == "technical"
        assert result["complexity"] == "moderate"
        assert result["requirements"] == ["needs_examples"]
        assert result["suggested_strategy"] == "semantic"
        assert "parse_error" not in result

    def test_parse_intent_already_dict_returns_fields(self):
        obj = {"query_type": "factual"}
        result = parse_intent_response({"content": obj})
        assert result["query_type"] == "factual"
        assert result["requirements"] == []  # documented default
        assert "parse_error" not in result

    def test_parse_intent_none_returns_empty_sentinel(self):
        result = parse_intent_response(None)
        assert result["parse_error"] == "empty-response"
        # Honest None query_type — never a fabricated classification.
        assert result["query_type"] is None

    def test_parse_intent_empty_content_returns_empty_sentinel(self):
        result = parse_intent_response({"content": ""})
        assert result["parse_error"] == "empty-response"
        assert result["query_type"] is None

    def test_parse_intent_non_json_returns_non_json_sentinel(self):
        result = parse_intent_response({"content": "not json{"})
        assert result["parse_error"] == "non-json-response"
        assert result["query_type"] is None

    def test_parse_intent_array_returns_non_object_sentinel(self):
        result = parse_intent_response({"content": "[1,2,3]"})
        assert result["parse_error"] == "non-object-json"
        assert result["query_type"] is None

    def test_parse_intent_bad_content_type_returns_unexpected_sentinel(self):
        result = parse_intent_response({"content": 42})
        assert result["parse_error"] == "unexpected-content-type"
        assert result["query_type"] is None


class TestParseHopPlanResponse:
    def test_parse_hop_plan_valid_returns_fields(self):
        obj = {
            "hops": [{"query": "What is BERT?"}, {"query": "What came after?"}],
            "combination_strategy": "synthesize",
            "total_hops": 2,
        }
        result = parse_hop_plan_response(_wrap(obj))
        assert result["hops"] == obj["hops"]
        assert result["combination_strategy"] == "synthesize"
        assert result["total_hops"] == 2
        assert "parse_error" not in result

    def test_parse_hop_plan_already_dict_returns_fields(self):
        obj = {"hops": [{"query": "Q"}]}
        result = parse_hop_plan_response({"content": obj})
        assert result["hops"] == obj["hops"]
        assert result["combination_strategy"] == "sequential"  # documented default
        assert result["total_hops"] is None  # documented default
        assert "parse_error" not in result

    def test_parse_hop_plan_none_returns_empty_sentinel(self):
        result = parse_hop_plan_response(None)
        assert result["parse_error"] == "empty-response"
        assert result["hops"] == []

    def test_parse_hop_plan_empty_content_returns_empty_sentinel(self):
        result = parse_hop_plan_response({"content": ""})
        assert result["parse_error"] == "empty-response"
        assert result["hops"] == []

    def test_parse_hop_plan_non_json_returns_non_json_sentinel(self):
        result = parse_hop_plan_response({"content": "not json{"})
        assert result["parse_error"] == "non-json-response"
        assert result["hops"] == []

    def test_parse_hop_plan_array_returns_non_object_sentinel(self):
        result = parse_hop_plan_response({"content": "[1,2,3]"})
        assert result["parse_error"] == "non-object-json"
        assert result["hops"] == []

    def test_parse_hop_plan_bad_content_type_returns_unexpected_sentinel(self):
        result = parse_hop_plan_response({"content": 42})
        assert result["parse_error"] == "unexpected-content-type"
        assert result["hops"] == []


# --------------------------------------------------------------------------
# Composers — one direct test per variant (VALID interpolation + EMPTY).
# Each returns a well-formed {"messages": [{"role","content"}, ...]} shape.
# --------------------------------------------------------------------------


def _assert_messages_shape(result):
    """Assert the composer return is a well-formed OpenAI chat `messages` list."""
    assert isinstance(result, dict)
    assert "messages" in result
    msgs = result["messages"]
    assert isinstance(msgs, list) and len(msgs) >= 1
    for m in msgs:
        assert isinstance(m, dict)
        assert "role" in m and "content" in m
    return msgs


class TestComposeExpansionMessages:
    def test_compose_expansion_valid_interpolates_query(self):
        msgs = _assert_messages_shape(
            compose_expansion_messages(query="ML optimization")
        )
        assert "ML optimization" in msgs[0]["content"]

    def test_compose_expansion_empty_returns_wellformed(self):
        msgs = _assert_messages_shape(compose_expansion_messages(query=""))
        # Honest no-query content — structurally valid, no crash.
        assert "No query" in msgs[0]["content"]


class TestComposeDecompositionMessages:
    def test_compose_decomposition_valid_interpolates_query(self):
        msgs = _assert_messages_shape(
            compose_decomposition_messages(query="Compare A and B")
        )
        assert "Compare A and B" in msgs[0]["content"]

    def test_compose_decomposition_empty_returns_wellformed(self):
        msgs = _assert_messages_shape(compose_decomposition_messages(query=""))
        assert "No query" in msgs[0]["content"]


class TestComposeAnalysisMessages:
    def test_compose_analysis_valid_interpolates_query(self):
        msgs = _assert_messages_shape(
            compose_analysis_messages(query="how 2 trian nueral netwrk")
        )
        assert "how 2 trian nueral netwrk" in msgs[0]["content"]

    def test_compose_analysis_empty_returns_wellformed(self):
        msgs = _assert_messages_shape(compose_analysis_messages(query=""))
        assert "No query" in msgs[0]["content"]


class TestComposeRewriteMessages:
    def test_compose_rewrite_valid_interpolates_query_and_analysis(self):
        analysis = {
            "issues": ["spelling_errors"],
            "suggestions": {"spelling": "corrected"},
        }
        msgs = _assert_messages_shape(
            compose_rewrite_messages(query="trian nueral netwrk", analysis=analysis)
        )
        content = msgs[0]["content"]
        assert "trian nueral netwrk" in content
        # The real parsed analysis is rendered into the rewriter's messages.
        assert "spelling_errors" in content

    def test_compose_rewrite_empty_query_none_analysis_returns_wellformed(self):
        # query="" (default-None analysis) MUST still produce a valid shape.
        msgs = _assert_messages_shape(compose_rewrite_messages(query="", analysis=None))
        # The composer renders an explicit "(empty)" placeholder for the query.
        assert "(empty)" in msgs[0]["content"]


class TestComposeIntentMessages:
    def test_compose_intent_valid_interpolates_query(self):
        msgs = _assert_messages_shape(
            compose_intent_messages(query="Show me Python code")
        )
        assert "Show me Python code" in msgs[0]["content"]

    def test_compose_intent_empty_returns_wellformed(self):
        msgs = _assert_messages_shape(compose_intent_messages(query=""))
        assert "No query" in msgs[0]["content"]


class TestComposeHopPlanMessages:
    def test_compose_hop_plan_valid_interpolates_query(self):
        msgs = _assert_messages_shape(
            compose_hop_plan_messages(query="How has BERT influenced NLP?")
        )
        assert "How has BERT influenced NLP?" in msgs[0]["content"]

    def test_compose_hop_plan_empty_returns_wellformed(self):
        msgs = _assert_messages_shape(compose_hop_plan_messages(query=""))
        assert "No query" in msgs[0]["content"]


# ==========================================================================
# COMPUTE-processor functions (#1117/#1123/#1118 from_function migration).
#
# Direct unit tests for the 6 module-level processor functions lifted from the
# inline `code=` codegen blocks (`_process_expansions`, `_resolve_dependencies`,
# `_combine_rewrites`, `_map_strategy`, `_plan_execution`, `_adaptive_process`).
# Each is wired into its node's inner workflow via
# `PythonCodeNode.from_function`; the node publishes the function's `return`
# dict on the flat `result` port. These tests exercise the function directly
# (valid input -> documented dict; empty/None/malformed -> HONEST default,
# never a fabricated value — zero-tolerance Rule 2).
# ==========================================================================


class TestProcessExpansions:
    """`_process_expansions`: parsed expansion dict + query -> expanded_query."""

    def test_valid_combines_and_dedups_terms(self):
        out = _process_expansions(
            query="ml optimization",
            expansion_response={
                "expansions": ["ml tuning", "neural net optimization"],
                "keywords": ["ml", "optimization"],
                "concepts": ["machine_learning"],
            },
        )
        expanded = out["expanded_query"]
        assert expanded["original"] == "ml optimization"
        assert expanded["expansions"] == ["ml tuning", "neural net optimization"]
        assert expanded["keywords"] == ["ml", "optimization"]
        assert expanded["concepts"] == ["machine_learning"]
        # all_terms = {query} | expansions | keywords; dedup is set-based.
        assert set(expanded["all_terms"]) == {
            "ml optimization",
            "ml tuning",
            "neural net optimization",
            "ml",
            "optimization",
        }
        # expansion_count is unique-term-count minus the original query.
        assert expanded["expansion_count"] == len(set(expanded["all_terms"])) - 1

    def test_none_response_yields_honest_empty(self):
        # Missing parsed dict (parser empty-sentinel) → empty lists, never
        # fabricated expansions. Only the original query survives in all_terms.
        out = _process_expansions(query="the query", expansion_response=None)
        expanded = out["expanded_query"]
        assert expanded["expansions"] == []
        assert expanded["keywords"] == []
        assert expanded["concepts"] == []
        assert expanded["all_terms"] == ["the query"]
        assert expanded["expansion_count"] == 0

    def test_empty_query_and_empty_response(self):
        out = _process_expansions(query="", expansion_response={})
        expanded = out["expanded_query"]
        # Empty query is still the lone all_terms entry; no fabrication.
        assert expanded["all_terms"] == [""]
        assert expanded["expansions"] == []


class TestResolveDependencies:
    """`_resolve_dependencies`: parsed decomposition dict -> execution_plan."""

    def test_valid_topological_sort_over_depends_on(self):
        # hop 0 has no deps, hop 1 depends on hop 0 (the `depends_on` field the
        # decomposer system_prompt advertises — F25 Shard E).
        out = _resolve_dependencies(
            decomposition_result={
                "sub_questions": [
                    {"question": "What is BERT?", "depends_on": []},
                    {"question": "How does it train?", "depends_on": [0]},
                ],
                "composition_strategy": "sequential",
            }
        )
        plan = out["execution_plan"]
        assert plan["total_questions"] == 2
        # Execution order MUST be a valid permutation of the 2 indices.
        assert set(plan["execution_order"]) == {0, 1}
        assert plan["composition_strategy"] == "sequential"

    def test_none_yields_honest_empty_plan(self):
        out = _resolve_dependencies(decomposition_result=None)
        plan = out["execution_plan"]
        assert plan["sub_questions"] == []
        assert plan["execution_order"] == []
        assert plan["total_questions"] == 0
        # Default composition strategy, never fabricated sub-questions.
        assert plan["composition_strategy"] == "sequential"

    def test_bare_string_subquestions_no_deps(self):
        # A sub-question that is a bare string (not a dict) has no depends_on;
        # the resolver must not crash and treats it as dependency-free.
        out = _resolve_dependencies(
            decomposition_result={"sub_questions": ["q1", "q2"]}
        )
        plan = out["execution_plan"]
        assert plan["total_questions"] == 2
        assert set(plan["execution_order"]) == {0, 1}


class TestCombineRewrites:
    """`_combine_rewrites`: query + analysis dict + rewrite dict -> output."""

    def test_valid_merges_versions_and_surfaces_issues(self):
        out = _combine_rewrites(
            query="trian nueral netwrk",
            analysis_result={"issues": ["spelling_errors"], "suggestions": {}},
            rewrite_result={
                "rewrites": {
                    "corrected": "train neural network",
                    "clarified": "how to train a neural network",
                },
                "recommended": "how to train a neural network",
            },
        )
        rewritten = out["rewritten_queries"]
        assert rewritten["original"] == "trian nueral netwrk"
        assert rewritten["issues_found"] == ["spelling_errors"]
        assert rewritten["recommended"] == "how to train a neural network"
        # all_unique_versions = original + rewrite values, dedup preserving order.
        assert rewritten["all_unique_versions"][0] == "trian nueral netwrk"
        assert "train neural network" in rewritten["all_unique_versions"]
        assert (
            rewritten["improvement_count"] == len(rewritten["all_unique_versions"]) - 1
        )

    def test_none_parsed_dicts_yield_only_original(self):
        # Missing parsed dicts → no issues, only the original query, recommended
        # falls back to the original. Never a fabricated rewrite.
        out = _combine_rewrites(
            query="the query", analysis_result=None, rewrite_result=None
        )
        rewritten = out["rewritten_queries"]
        assert rewritten["issues_found"] == []
        assert rewritten["versions"] == {}
        assert rewritten["recommended"] == "the query"
        assert rewritten["all_unique_versions"] == ["the query"]
        assert rewritten["improvement_count"] == 0


class TestMapStrategy:
    """`_map_strategy`: parsed intent dict -> routing_decision."""

    def test_valid_maps_and_adjusts_for_requirements(self):
        out = _map_strategy(
            intent_classification={
                "query_type": "procedural",
                "domain": "technical",
                "complexity": "moderate",
                "requirements": ["needs_examples"],
            }
        )
        routing = out["routing_decision"]
        # (procedural, moderate) → "semantic"; needs_examples keeps it semantic.
        assert routing["recommended_strategy"] == "semantic"
        assert routing["intent_analysis"]["query_type"] == "procedural"
        # The (query_type, complexity) pair IS in the strategy_map → 0.85.
        assert routing["confidence"] == 0.85

    def test_needs_authoritative_upgrades_to_self_correcting(self):
        out = _map_strategy(
            intent_classification={
                "query_type": "factual",
                "complexity": "simple",
                "requirements": ["needs_authoritative"],
            }
        )
        # (factual, simple) → "sparse" base, then needs_authoritative →
        # "self_correcting" (the requirement-aware adjustment).
        assert out["routing_decision"]["recommended_strategy"] == "self_correcting"

    def test_none_falls_to_documented_defaults(self):
        # Parser None-sentinel (query_type=None) → factual/simple defaults; the
        # pair is in strategy_map → "sparse". Never fabricated classification.
        out = _map_strategy(intent_classification=None)
        routing = out["routing_decision"]
        assert routing["recommended_strategy"] == "sparse"
        # (factual, simple) IS in strategy_map → confidence 0.85.
        assert routing["confidence"] == 0.85

    def test_unmapped_pair_yields_hybrid_low_confidence(self):
        # An (query_type, complexity) pair NOT in strategy_map → "hybrid" + 0.6.
        out = _map_strategy(
            intent_classification={"query_type": "factual", "complexity": "complex"}
        )
        routing = out["routing_decision"]
        assert routing["recommended_strategy"] == "hybrid"
        assert routing["confidence"] == 0.6


class TestPlanExecution:
    """`_plan_execution`: parsed hop-plan dict -> multi_hop_plan."""

    def test_valid_builds_sequential_batches_honoring_deps(self):
        out = _plan_execution(
            hop_plan_result={
                "hops": [
                    {"hop_number": 1, "depends_on": []},
                    {"hop_number": 2, "depends_on": [1]},
                ],
                "combination_strategy": "sequential",
            }
        )
        plan = out["multi_hop_plan"]
        assert plan["total_hops"] == 2
        # hop_2 depends on hop_1 → 2 sequential batches, 0 parallel.
        assert len(plan["batches"]) == 2
        assert plan["parallel_opportunities"] == 0
        assert plan["combination_strategy"] == "sequential"

    def test_parallel_hops_share_a_batch(self):
        out = _plan_execution(
            hop_plan_result={
                "hops": [
                    {"hop_number": 1, "depends_on": []},
                    {"hop_number": 2, "depends_on": []},
                ]
            }
        )
        plan = out["multi_hop_plan"]
        # Two dependency-free hops → one batch holding both → 1 parallel opp.
        assert len(plan["batches"]) == 1
        assert plan["parallel_opportunities"] == 1

    def test_none_yields_zero_hop_zero_batch_plan(self):
        out = _plan_execution(hop_plan_result=None)
        plan = out["multi_hop_plan"]
        assert plan["total_hops"] == 0
        assert plan["batches"] == []
        assert plan["parallel_opportunities"] == 0
        # Default combination strategy, never fabricated hops.
        assert plan["combination_strategy"] == "sequential"


class TestAdaptiveProcess:
    """`_adaptive_process`: query + nested routing_decision -> adaptive_plan."""

    def test_valid_comparative_appends_multi_hop(self):
        # The wired value is the classifier's full run() dict, which nests the
        # routing_decision under the same key.
        out = _adaptive_process(
            query="compare X vs Y",
            routing_decision={
                "routing_decision": {
                    "intent_analysis": {
                        "query_type": "comparative",
                        "complexity": "moderate",
                    },
                    "recommended_strategy": "multi_vector",
                }
            },
        )
        plan = out["adaptive_plan"]
        assert plan["original_query"] == "compare X vs Y"
        # Always rewrite; comparative → multi_hop.
        assert "rewrite" in plan["processing_steps"]
        assert "multi_hop" in plan["processing_steps"]
        assert plan["recommended_strategy"] == "multi_vector"

    def test_complex_appends_decompose(self):
        out = _adaptive_process(
            query="deep analysis",
            routing_decision={
                "routing_decision": {
                    "intent_analysis": {
                        "query_type": "analytical",
                        "complexity": "complex",
                    }
                }
            },
        )
        steps = out["adaptive_plan"]["processing_steps"]
        # analytical → expand; complex → decompose; analytical+complex → multi_hop.
        assert "expand" in steps
        assert "decompose" in steps
        assert "multi_hop" in steps

    def test_none_yields_factual_simple_defaults(self):
        # Missing routing_decision → factual/simple defaults + single rewrite
        # step. Never fabricated intent.
        out = _adaptive_process(query="the query", routing_decision=None)
        plan = out["adaptive_plan"]
        assert plan["processing_steps"] == ["rewrite"]
        assert plan["recommended_strategy"] == "hybrid"
        assert plan["intent"] == {}

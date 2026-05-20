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
        """The inner workflow wires llm_expander → expansion_processor."""
        wf = _build(QueryExpansionNode())
        assert set(wf.nodes.keys()) == {"llm_expander", "expansion_processor"}
        edge = [
            c
            for c in wf.connections
            if c.source_node == "llm_expander"
            and c.target_node == "expansion_processor"
        ]
        assert len(edge) == 1
        assert edge[0].source_output == "response"
        assert edge[0].target_input == "expansion_response"

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
        """Decomposition wires query_decomposer → dependency_resolver."""
        wf = _build(QueryDecompositionNode())
        assert set(wf.nodes.keys()) == {
            "query_decomposer",
            "dependency_resolver",
        }
        edges = [
            c
            for c in wf.connections
            if c.source_node == "query_decomposer"
            and c.target_node == "dependency_resolver"
        ]
        assert len(edges) == 1
        assert edges[0].source_output == "response"
        assert edges[0].target_input == "decomposition_result"

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
        """analyzer → rewriter + analyzer → combiner + rewriter → combiner."""
        wf = _build(QueryRewritingNode())
        assert set(wf.nodes.keys()) == {
            "query_analyzer",
            "query_rewriter",
            "result_combiner",
        }
        # Three connections wire the fan-in: analyzer feeds both rewriter
        # (as ``analysis``) and combiner (as ``analysis_result``); rewriter
        # feeds combiner (as ``rewrite_result``).
        sources = [(c.source_node, c.target_node) for c in wf.connections]
        assert ("query_analyzer", "query_rewriter") in sources
        assert ("query_analyzer", "result_combiner") in sources
        assert ("query_rewriter", "result_combiner") in sources

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
        """intent_classifier (LLM) → strategy_mapper (PythonCodeNode)."""
        wf = _build(QueryIntentClassifierNode())
        assert set(wf.nodes.keys()) == {"intent_classifier", "strategy_mapper"}
        edges = [
            c
            for c in wf.connections
            if c.source_node == "intent_classifier"
            and c.target_node == "strategy_mapper"
        ]
        assert len(edges) == 1
        assert edges[0].target_input == "intent_classification"

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
        """hop_planner (LLM) → execution_planner (PythonCodeNode)."""
        wf = _build(MultiHopQueryPlannerNode())
        assert set(wf.nodes.keys()) == {"hop_planner", "execution_planner"}
        edges = [
            c
            for c in wf.connections
            if c.source_node == "hop_planner" and c.target_node == "execution_planner"
        ]
        assert len(edges) == 1
        assert edges[0].target_input == "hop_plan_result"

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

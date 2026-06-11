"""Tier 1 unit coverage — ``kaizen.nodes.rag.workflows`` + ``strategies``.

F8 shard B7. The 8 classes covered are the documented RAG Quick Start
surface: 4 ``WorkflowNode`` subclasses in ``workflows.py``
(Simple/Advanced/Adaptive/RAGPipeline) and 4 ``Node`` subclasses in
``strategies.py`` (Semantic/Statistical/Hybrid/Hierarchical), plus the
``create_*_rag_workflow`` module builders and the ``RAGConfig`` dataclass.

Tier 1 scope: construction, ``get_parameters()`` contracts, and the inner
workflow GRAPH SHAPE produced by each ``_create_workflow`` / builder. End-to-end
execution through ``LocalRuntime`` is Tier 2 (``tests/integration/rag/``).

The chunker registering import lives in ``strategies.py`` (the R3-L2 fix), so
importing the modules under test is sufficient — no test-side registration.
"""

from __future__ import annotations

import pytest
from kailash.nodes.base import Node
from kailash.nodes.logic.workflow import WorkflowNode
from kailash.workflow.graph import Workflow

from kaizen.nodes.rag.strategies import (
    HierarchicalRAGNode,
    HybridRAGNode,
    RAGConfig,
    SemanticRAGNode,
    StatisticalRAGNode,
    create_hierarchical_rag_workflow,
    create_hybrid_rag_workflow,
    create_semantic_rag_workflow,
    create_statistical_rag_workflow,
)
from kaizen.nodes.rag.workflows import (
    AdaptiveRAGWorkflowNode,
    AdvancedRAGWorkflowNode,
    RAGPipelineWorkflowNode,
    SimpleRAGWorkflowNode,
)

pytestmark = pytest.mark.unit


def _wf(node: WorkflowNode) -> Workflow:
    """Narrow ``WorkflowNode.workflow`` (typed ``Workflow | None``) to ``Workflow``.

    Every builder / pipeline under test always supplies a workflow, so the
    ``None`` branch is unreachable; the assert turns the static ``| None`` into
    a concrete type for the checker and fails loudly if the invariant breaks.
    """
    # type: ignore[attr-defined] — @register_node erases WorkflowNode→Node for
    # static checkers; `.workflow` is a real WorkflowNode property (A3).
    wf = node.workflow  # type: ignore[attr-defined]
    assert wf is not None
    return wf


def _node(workflow: Workflow, node_id: str) -> Node:
    """Narrow ``Workflow.get_node`` (typed ``Node | None``) to ``Node``.

    The node ids passed by these tests are always present in the graph under
    test; the assert fails loudly if a builder stops emitting the node.
    """
    found = workflow.get_node(node_id)
    assert found is not None, node_id
    return found


# ==========================================================================
# RAGConfig — the configuration dataclass contract
# ==========================================================================


class TestRAGConfig:
    def test_defaults(self):
        """RAGConfig ships documented defaults the builders read."""
        c = RAGConfig()
        assert c.chunk_size == 1000
        assert c.chunk_overlap == 200
        assert c.embedding_model == "text-embedding-3-small"
        assert c.embedding_provider == "openai"
        assert c.vector_db_provider == "postgresql"
        assert c.retrieval_k == 5
        assert c.similarity_threshold == 0.7

    def test_override(self):
        """Every field is overridable via the dataclass constructor."""
        c = RAGConfig(chunk_size=512, retrieval_k=10, similarity_threshold=0.9)
        assert c.chunk_size == 512
        assert c.retrieval_k == 10
        assert c.similarity_threshold == 0.9

    def test_builders_consume_config_chunk_size(self):
        """The chunk_size flows into the chunker node config (not ignored)."""
        wf = _wf(create_semantic_rag_workflow(RAGConfig(chunk_size=777)))
        chunker = _node(wf, "semantic_chunker")
        assert chunker.config.get("chunk_size") == 777


# ==========================================================================
# strategies.py — create_*_rag_workflow module builders
# ==========================================================================


class TestStrategyWorkflowBuilders:
    """Each builder returns a real WorkflowNode wrapping a populated graph."""

    @pytest.mark.parametrize(
        "builder, expected_nodes",
        [
            (
                create_semantic_rag_workflow,
                {"semantic_chunker", "embedder", "vector_db", "retriever"},
            ),
            (
                create_statistical_rag_workflow,
                {
                    "statistical_chunker",
                    "embedder",
                    "keyword_extractor",
                    "vector_db",
                    "retriever",
                },
            ),
            (
                create_hierarchical_rag_workflow,
                {
                    "hierarchical_chunker",
                    "embedder",
                    "level_processor",
                    "doc_vector_db",
                    "section_vector_db",
                    "para_vector_db",
                    "hierarchical_retriever",
                },
            ),
        ],
    )
    def test_builder_graph_shape(self, builder, expected_nodes):
        node = builder(RAGConfig())
        assert isinstance(node, WorkflowNode)
        assert isinstance(node.workflow, Workflow)  # type: ignore[attr-defined]
        assert set(_wf(node).nodes.keys()) == expected_nodes

    def test_semantic_builder_wires_chunker_to_embedder(self):
        """The pipeline connects chunker chunks → embedder texts."""
        wf = _wf(create_semantic_rag_workflow(RAGConfig()))
        edge = [
            c
            for c in wf.connections
            if c.source_node == "semantic_chunker" and c.target_node == "embedder"
        ]
        assert len(edge) == 1
        assert edge[0].source_output == "chunks"
        assert edge[0].target_input == "texts"

    def test_hybrid_builder_default_fusion_method(self):
        """create_hybrid_rag_workflow defaults to RRF fusion.

        The `result_fusion` node is wired via ``PythonCodeNode.from_function``
        with the default ``fusion_method`` bound into the closure; executing it
        publishes the bound value on the flat ``result`` port (its prior
        ``config["code"]`` string is gone — assert behavior, not source text).
        """
        wf = _wf(create_hybrid_rag_workflow(RAGConfig()))
        node = _node(wf, "result_fusion")
        out = node.execute(semantic_results={}, statistical_results={})
        assert out["result"]["fused_results"]["fusion_method"] == "rrf"

    def test_hybrid_builder_honors_fusion_method_arg(self):
        """The fusion_method arg is consumed — bound into the closure.

        It flows into the `result_fusion` from_function node's output; a
        Rule-3c silent-drop would leave the bound value stale. Behavior-asserted
        by executing the production node (the source string no longer exists).
        """
        wf = _wf(create_hybrid_rag_workflow(RAGConfig(), fusion_method="linear"))
        node = _node(wf, "result_fusion")
        out = node.execute(semantic_results={}, statistical_results={})
        assert out["result"]["fused_results"]["fusion_method"] == "linear"

    def test_hybrid_builder_graph_has_two_subworkflows_plus_fusion(self):
        wf = _wf(create_hybrid_rag_workflow(RAGConfig()))
        assert set(wf.nodes.keys()) == {
            "semantic_rag",
            "statistical_rag",
            "result_fusion",
        }


# ==========================================================================
# strategies.py — the 4 Node-subclass RAG strategies
# ==========================================================================

_STRATEGY_NODE_CLASSES = [
    SemanticRAGNode,
    StatisticalRAGNode,
    HybridRAGNode,
    HierarchicalRAGNode,
]


class TestStrategyNodes:
    @pytest.mark.parametrize("cls", _STRATEGY_NODE_CLASSES)
    def test_constructs_default(self, cls):
        node = cls()
        assert node is not None
        assert isinstance(node.rag_config, RAGConfig)

    @pytest.mark.parametrize("cls", _STRATEGY_NODE_CLASSES)
    def test_constructs_with_custom_config(self, cls):
        cfg = RAGConfig(chunk_size=256)
        node = cls(config=cfg)
        assert node.rag_config.chunk_size == 256

    @pytest.mark.parametrize("cls", _STRATEGY_NODE_CLASSES)
    def test_get_parameters_declares_documents_required(self, cls):
        """`documents` is the required input for every strategy node."""
        params = cls().get_parameters()
        assert "documents" in params
        assert params["documents"].required is True

    @pytest.mark.parametrize("cls", _STRATEGY_NODE_CLASSES)
    def test_get_parameters_declares_query_and_operation(self, cls):
        params = cls().get_parameters()
        assert "query" in params
        assert "operation" in params
        assert params["operation"].default == "index"

    def test_hybrid_node_declares_fusion_method_param(self):
        """HybridRAGNode adds a fusion_method parameter (the others do not)."""
        params = HybridRAGNode().get_parameters()
        assert "fusion_method" in params
        assert params["fusion_method"].default == "rrf"

    def test_hybrid_node_binds_fusion_method(self):
        assert HybridRAGNode(fusion_method="weighted").fusion_method == "weighted"  # type: ignore[attr-defined]

    @pytest.mark.parametrize("cls", _STRATEGY_NODE_CLASSES)
    def test_workflow_node_lazy_until_run(self, cls):
        """The wrapped WorkflowNode is built lazily on first run(), not __init__."""
        assert cls().workflow_node is None


# ==========================================================================
# workflows.py — the 4 WorkflowNode-subclass pipelines
# ==========================================================================

_WORKFLOW_NODE_CLASSES = [
    SimpleRAGWorkflowNode,
    AdvancedRAGWorkflowNode,
    AdaptiveRAGWorkflowNode,
    RAGPipelineWorkflowNode,
]


class TestWorkflowNodes:
    @pytest.mark.parametrize("cls", _WORKFLOW_NODE_CLASSES)
    def test_constructs_default(self, cls):
        node = cls()
        assert isinstance(node, WorkflowNode)
        assert isinstance(node.workflow, Workflow)  # type: ignore[attr-defined]

    @pytest.mark.parametrize("cls", _WORKFLOW_NODE_CLASSES)
    def test_constructs_with_custom_config(self, cls):
        node = cls(config=RAGConfig(chunk_size=333))
        assert node.rag_config.chunk_size == 333

    @pytest.mark.parametrize("cls", _WORKFLOW_NODE_CLASSES)
    def test_inner_workflow_is_non_empty(self, cls):
        """Every pipeline's inner graph has nodes (no empty-Workflow stub)."""
        assert len(_wf(cls()).nodes) > 0

    def test_simple_workflow_graph_shape(self):
        """SimpleRAGWorkflowNode wraps the semantic builder's 4-node graph."""
        wf = _wf(SimpleRAGWorkflowNode())
        assert set(wf.nodes.keys()) == {
            "semantic_chunker",
            "embedder",
            "vector_db",
            "retriever",
        }

    def test_advanced_workflow_has_router_and_four_pipelines(self):
        """AdvancedRAGWorkflowNode: analyzer → router → 4 strategy pipelines."""
        wf = _wf(AdvancedRAGWorkflowNode())
        assert "strategy_router" in wf.nodes
        assert "quality_analyzer" in wf.nodes
        for pipeline in (
            "semantic_rag_pipeline",
            "statistical_rag_pipeline",
            "hybrid_rag_pipeline",
            "hierarchical_rag_pipeline",
        ):
            assert pipeline in wf.nodes

    def test_adaptive_workflow_has_llm_analyzer(self):
        """AdaptiveRAGWorkflowNode wires an LLMAgentNode strategy analyzer."""
        wf = _wf(AdaptiveRAGWorkflowNode())
        assert "rag_strategy_analyzer" in wf.nodes
        assert "strategy_executor" in wf.nodes

    def test_adaptive_workflow_llm_model_default_env_loaded(self):
        """F9 #1126: llm_model defaults to env (OPENAI_PROD_MODEL /
        DEFAULT_LLM_MODEL); resolves to None when neither is set per
        rules/env-models.md."""
        import os as _os

        expected = _os.environ.get(
            "OPENAI_PROD_MODEL", _os.environ.get("DEFAULT_LLM_MODEL")
        )
        node = AdaptiveRAGWorkflowNode()
        assert node.llm_model == expected  # type: ignore[attr-defined]

    def test_rag_pipeline_default_strategy_bound(self):
        """RAGPipelineWorkflowNode binds default_strategy (default hybrid)."""
        assert RAGPipelineWorkflowNode().default_strategy == "hybrid"  # type: ignore[attr-defined]
        assert (
            RAGPipelineWorkflowNode(default_strategy="semantic").default_strategy  # type: ignore[attr-defined]
            == "semantic"
        )

    def test_rag_pipeline_graph_has_dispatcher_and_strategies(self):
        wf = _wf(RAGPipelineWorkflowNode())
        assert "strategy_dispatcher" in wf.nodes
        for strat in (
            "semantic_strategy",
            "statistical_strategy",
            "hybrid_strategy",
            "hierarchical_strategy",
        ):
            assert strat in wf.nodes

    @pytest.mark.parametrize(
        "cls, router_id",
        [
            (AdvancedRAGWorkflowNode, "strategy_router"),
            (AdaptiveRAGWorkflowNode, "strategy_executor"),
            (RAGPipelineWorkflowNode, "strategy_dispatcher"),
        ],
    )
    def test_router_uses_multi_case_switch(self, cls, router_id):
        """Every router is a multi-case SwitchNode (the R3-L3 cases= config)."""
        router = _node(_wf(cls()), router_id)
        assert router.config.get("cases") == [
            "semantic",
            "statistical",
            "hybrid",
            "hierarchical",
        ]

    @pytest.mark.parametrize(
        "cls, router_id",
        [
            (AdvancedRAGWorkflowNode, "strategy_router"),
            (AdaptiveRAGWorkflowNode, "strategy_executor"),
            (RAGPipelineWorkflowNode, "strategy_dispatcher"),
        ],
    )
    def test_router_edges_use_case_output_ports(self, cls, router_id):
        """Router→pipeline edges use case_<value> source ports (R3-L3 fix)."""
        wf = _wf(cls())
        edges = [c for c in wf.connections if c.source_node == router_id]
        assert len(edges) == 4
        for edge in edges:
            assert edge.source_output.startswith("case_")
            assert edge.target_input == "input"


# ==========================================================================
# F31-FU2 Shard C — direct-call Tier-1 coverage of the pure parser / composer
# `from_function` targets in `workflows.py` (the O2 strategy-decision parser +
# the strategy-analyzer message composer). Pure data rendering / tool-result
# parsing (permitted deterministic exceptions per rules/agent-reasoning.md
# #3 + #6) — NOT agent decision-making. Called DIRECTLY (no LocalRuntime, no
# mocking — pure functions).
#
# Per-file contract (zero-tolerance Rule 2): `parse_strategy_decision` returns
# the strategy-decision dict DIRECTLY (NOT wrapped in a `result` key). It ships
# 5 typed parse-error sentinels — empty-response / non-json-response /
# unexpected-content-type / non-object-json / missing-strategy — each setting
# `recommended_strategy: None` so the downstream SwitchNode fails CLOSED on the
# None strategy (no fabricated default like "semantic"). The VALID case surfaces
# the genuine strategy + reasoning/confidence/fallback metadata. An already-dict
# `content` (provider pre-parsed) is honored.
# ==========================================================================

import json as _json

from kaizen.nodes.rag.workflows import (
    _unwrap_response_content,
    compose_strategy_analyzer_messages,
    parse_strategy_decision,
)


def _ws_wrap(obj) -> dict:
    """Build the LLMAgentNode `response` port shape with a JSON-string content."""
    return {"content": _json.dumps(obj)}


class TestWorkflowsUnwrapResponseContent:
    """`_unwrap_response_content`: dict -> .content, bare value -> passthrough."""

    def test_unwrap_dict_returns_content(self):
        assert _unwrap_response_content({"content": "hello"}) == "hello"

    def test_unwrap_dict_missing_content_returns_none(self):
        assert _unwrap_response_content({"other": "x"}) is None

    def test_unwrap_bare_string_passthrough(self):
        assert _unwrap_response_content("raw string") == "raw string"

    def test_unwrap_none_passthrough(self):
        assert _unwrap_response_content(None) is None


class TestParseStrategyDecision:
    """`parse_strategy_decision`: VALID + 5 typed sentinels + already-dict.

    Returns the decision dict DIRECTLY (no `result` wrapper). Every malformed
    case sets `recommended_strategy: None` so the SwitchNode fails closed —
    never a fabricated strategy (zero-tolerance Rule 2).
    """

    def test_valid_returns_strategy_and_metadata(self):
        obj = {
            "recommended_strategy": "semantic",
            "reasoning": "dense corpus",
            "confidence": 0.9,
            "fallback_strategy": "hybrid",
        }
        result = parse_strategy_decision(_ws_wrap(obj))
        assert result["recommended_strategy"] == "semantic"
        assert result["reasoning"] == "dense corpus"
        assert result["confidence"] == 0.9
        assert result["fallback_strategy"] == "hybrid"
        assert "parse_error" not in result

    def test_already_dict_content_returns_strategy(self):
        # Provider pre-parsed: content is already a dict.
        result = parse_strategy_decision(
            {"content": {"recommended_strategy": "hybrid"}}
        )
        assert result["recommended_strategy"] == "hybrid"
        # Absent rationale fields default to None (documented), not fabricated.
        assert result["reasoning"] is None
        assert result["confidence"] is None
        assert result["fallback_strategy"] is None
        assert "parse_error" not in result

    def test_none_returns_empty_response_sentinel(self):
        result = parse_strategy_decision(None)
        assert result["parse_error"] == "empty-response"
        # Honest None strategy — the SwitchNode fails closed (zero-tolerance R2).
        assert result["recommended_strategy"] is None

    def test_empty_content_returns_empty_response_sentinel(self):
        result = parse_strategy_decision({"content": ""})
        assert result["parse_error"] == "empty-response"
        assert result["recommended_strategy"] is None

    def test_whitespace_content_returns_empty_response_sentinel(self):
        result = parse_strategy_decision({"content": "   "})
        assert result["parse_error"] == "empty-response"
        assert result["recommended_strategy"] is None

    def test_non_json_returns_non_json_sentinel(self):
        result = parse_strategy_decision({"content": "not json{"})
        assert result["parse_error"] == "non-json-response"
        assert result["recommended_strategy"] is None

    def test_unexpected_content_type_returns_unexpected_sentinel(self):
        # content is an int (not str, not dict).
        result = parse_strategy_decision({"content": 42})
        assert result["parse_error"] == "unexpected-content-type"
        assert result["recommended_strategy"] is None

    def test_non_object_json_returns_non_object_sentinel(self):
        # Valid JSON that is not an object (an array).
        result = parse_strategy_decision({"content": "[1, 2, 3]"})
        assert result["parse_error"] == "non-object-json"
        assert result["recommended_strategy"] is None

    def test_missing_strategy_field_returns_missing_strategy_sentinel(self):
        # Parsed JSON object but the load-bearing recommended_strategy is absent.
        result = parse_strategy_decision(_ws_wrap({"reasoning": "r"}))
        assert result["parse_error"] == "missing-strategy"
        assert result["recommended_strategy"] is None

    def test_blank_strategy_field_returns_missing_strategy_sentinel(self):
        # A present-but-blank strategy string is treated as missing (fails closed).
        result = parse_strategy_decision(_ws_wrap({"recommended_strategy": "   "}))
        assert result["parse_error"] == "missing-strategy"
        assert result["recommended_strategy"] is None


def _ws_assert_messages_shape(result):
    """Assert the composer return is a well-formed OpenAI chat `messages` list."""
    assert isinstance(result, dict)
    assert "messages" in result
    msgs = result["messages"]
    assert isinstance(msgs, list) and len(msgs) >= 1
    for m in msgs:
        assert isinstance(m, dict)
        assert "role" in m and "content" in m
    return msgs


class TestComposeStrategyAnalyzerMessages:
    def test_valid_interpolates_corpus_characteristics_and_query(self):
        msgs = _ws_assert_messages_shape(
            compose_strategy_analyzer_messages(
                query="Compare BERT and GPT",
                document_count=12,
                avg_length=2048,
                has_structure=True,
                is_technical=True,
                content_types=["markdown", "code"],
            )
        )
        content = msgs[0]["content"]
        # The REAL document characteristics + query are rendered into the prompt.
        assert "Compare BERT and GPT" in content
        assert "12" in content
        assert "2048" in content
        assert "markdown" in content and "code" in content

    def test_empty_returns_wellformed_with_none_query_placeholder(self):
        # All-default call (empty query, zero counts) MUST produce a valid shape.
        msgs = _ws_assert_messages_shape(compose_strategy_analyzer_messages())
        content = msgs[0]["content"]
        # The composer renders an explicit "(none)" placeholder for the query
        # and "none detected" for content types.
        assert "(none)" in content
        assert "none detected" in content


# ==========================================================================
# Wave 3 Shard S5a — direct-call Tier-1 coverage of the COMPUTE-stage
# `from_function` targets lifted from the prior PythonCodeNode `"code"` strings
# (#1117/#1123/#1118 root-cause fix). Each function is called DIRECTLY (pure
# function, no LocalRuntime, no mocking) and is behavior-equivalent to the
# codegen body it replaced. One direct test per new module fn.
# ==========================================================================

from kaizen.nodes.rag.workflows import (  # noqa: E402
    _aggregate_adaptive_results,
    _analyze_documents,
    _analyze_for_llm,
    _format_pipeline_results,
    _make_config_processor,
    _validate_rag_results,
)

# A mixed corpus mirroring the integration fixture: structured + technical +
# a present-but-None-content dict + a non-dict element the body must survive.
_S5A_CORPUS = [
    {"content": "## Section 1\nNeural network optimization with gradient descent."},
    {"content": "def train(model): return model.fit()  # code function class api"},
    {"content": None},
    "not-a-dict-element",
]


class TestAnalyzeDocuments:
    """`_analyze_documents` (AdvancedRAGWorkflowNode quality_analyzer)."""

    def test_filters_non_dict_and_picks_strategy(self):
        out = _analyze_documents(_S5A_CORPUS)
        analysis = out["analysis"]
        # 3 dict docs survive (content:None dict included); the str is dropped.
        assert analysis["total_docs"] == 3
        assert analysis["is_technical"] is True
        assert analysis["recommended_strategy"] in {
            "semantic",
            "statistical",
            "hybrid",
            "hierarchical",
        }
        # The filtered documents are echoed for the downstream validator.
        assert out["documents"] == [d for d in _S5A_CORPUS if isinstance(d, dict)]

    def test_empty_corpus_defaults(self):
        out = _analyze_documents(None)
        assert out["analysis"]["total_docs"] == 0
        assert out["analysis"]["avg_length"] == 0
        # Empty corpus falls through to the default strategy.
        assert out["analysis"]["recommended_strategy"] == "semantic"


class TestValidateRagResults:
    """`_validate_rag_results` (AdvancedRAGWorkflowNode quality_validator)."""

    def test_passing_results_compute_quality_score(self):
        out = _validate_rag_results(
            rag_results={"documents": [1, 2, 3, 4, 5], "scores": [0.8, 0.9]},
            analysis={"recommended_strategy": "hybrid"},
        )
        v = out["validation"]
        assert v["results_count"] == 5
        # avg_score 0.85 * (5/5) = 0.85 > 0.5 -> passed.
        assert v["passed"] is True
        assert out["strategy_used"] == "hybrid"
        assert out["final_status"] == "passed"

    def test_honest_defaults_on_missing_inputs(self):
        # An unwired upstream branch arrives None — honest defaults, no crash.
        out = _validate_rag_results(rag_results=None, analysis=None)
        assert out["validation"]["results_count"] == 0
        assert out["validation"]["passed"] is False
        assert out["strategy_used"] is None
        assert out["final_status"] == "needs_improvement"

    def test_present_but_none_scores_does_not_crash(self):
        # A present-but-None `scores` key must not raise (sum(None) guard).
        out = _validate_rag_results(
            rag_results={"documents": [1], "scores": None}, analysis={}
        )
        assert out["validation"]["avg_score"] == 0


class TestAnalyzeForLlm:
    """`_analyze_for_llm` (AdaptiveRAGWorkflowNode document_preprocessor)."""

    def test_publishes_flat_characteristics(self):
        out = _analyze_for_llm(_S5A_CORPUS, query="optimize neural nets")
        # Flat dict (no wrapper) — the composer reads result.<key> directly.
        assert out["document_count"] == 3
        assert out["is_technical"] is True
        assert "structured" in out["content_types"]
        assert out["query"] == "optimize neural nets"

    def test_empty_corpus_defaults_echo_query(self):
        out = _analyze_for_llm([], query="q")
        assert out["document_count"] == 0
        assert out["content_types"] == []
        assert out["query"] == "q"


class TestAggregateAdaptiveResults:
    """`_aggregate_adaptive_results` (AdaptiveRAGWorkflowNode results_aggregator)."""

    def test_surfaces_parsed_decision_and_characteristics(self):
        out = _aggregate_adaptive_results(
            rag_results={"docs": []},
            llm_decision={
                "recommended_strategy": "hybrid",
                "reasoning": "mixed",
                "confidence": 0.82,
                "fallback_strategy": "semantic",
            },
            preprocessed_data={
                "document_count": 3,
                "avg_length": 100,
                "content_types": ["technical"],
            },
        )
        assert out["strategy_used"] == "hybrid"
        assert out["llm_reasoning"] == "mixed"
        assert out["confidence"] == 0.82
        assert out["document_analysis"]["count"] == 3
        assert out["adaptive_metadata"]["fallback_available"] == "semantic"
        assert out["adaptive_metadata"]["strategy_selection_method"] == "llm_analysis"

    def test_honest_defaults_on_missing_decision(self):
        # A parse-error decision (recommended_strategy None) + unwired branch.
        out = _aggregate_adaptive_results(
            rag_results=None, llm_decision=None, preprocessed_data=None
        )
        assert out["strategy_used"] is None
        assert out["document_analysis"]["count"] is None
        assert out["adaptive_metadata"]["fallback_available"] is None


class TestMakeConfigProcessor:
    """`_make_config_processor` closure factory (RAGPipelineWorkflowNode)."""

    def test_binds_build_time_config_and_publishes_flat_dict(self):
        fn = _make_config_processor(
            default_strategy="hybrid",
            chunk_size=512,
            chunk_overlap=64,
            embedding_model="text-embedding-3-small",
            retrieval_k=7,
        )
        # The factory names the function so from_function/registry sees it.
        assert fn.__name__ == "config_processor"
        out = fn(documents=[{"content": "x"}], query="", strategy="")
        # `strategy` is a TOP-LEVEL key (the SwitchNode condition_field reads it).
        assert out["strategy"] == "hybrid"  # falls back to bound default
        assert out["chunk_size"] == 512
        assert out["chunk_overlap"] == 64
        assert out["embedding_model"] == "text-embedding-3-small"
        assert out["retrieval_k"] == 7
        assert out["query"] == ""

    def test_runtime_strategy_overrides_default(self):
        fn = _make_config_processor(
            default_strategy="hybrid",
            chunk_size=1000,
            chunk_overlap=200,
            embedding_model="m",
            retrieval_k=5,
        )
        out = fn(documents=[], query="q", strategy="semantic")
        assert out["strategy"] == "semantic"  # runtime input wins
        assert out["query"] == "q"


class TestFormatPipelineResults:
    """`_format_pipeline_results` (RAGPipelineWorkflowNode results_formatter)."""

    def test_formats_with_config_strategy(self):
        out = _format_pipeline_results(
            strategy_results={"docs": [1]},
            processed_config={"strategy": "semantic"},
        )
        assert out["strategy_used"] == "semantic"
        assert out["pipeline_type"] == "configurable"
        assert out["success"] is True

    def test_honest_defaults_on_missing_inputs(self):
        out = _format_pipeline_results(strategy_results=None, processed_config=None)
        assert out["strategy_used"] is None
        assert out["success"] is False
        assert out["configuration"] == {}


# ==========================================================================
# Wave 3 Shard S5b — direct-call Tier-1 coverage of the COMPUTE-stage
# `from_function` targets lifted from the prior PythonCodeNode `"code"` strings
# in strategies.py (#1117 publish-nothing / #1123 brace-escape / #1118
# import-trap root-cause fix). Each function is called DIRECTLY (pure function,
# no LocalRuntime, no mocking) and is behavior-equivalent to the codegen body it
# replaced. One direct test per new module fn.
# ==========================================================================

from kaizen.nodes.rag.strategies import (  # noqa: E402
    _extract_keywords,
    _make_result_fusion,
    _process_levels,
)

# A mixed corpus: technical + structured + a present-but-None-content dict + a
# non-dict element the body must survive (mirrors the integration fixture).
_S5B_CHUNKS = [
    {"content": "def train(model): return model.fit()  # gradient optimization api"},
    {"content": "## Section 1\nNeural network architecture overview."},
    {"content": None},
    "not-a-dict-element",
]


class TestExtractKeywords:
    """`_extract_keywords` (StatisticalRAG keyword_extractor)."""

    def test_filters_non_dict_and_extracts_tokens(self):
        out = _extract_keywords(_S5B_CHUNKS)
        keywords = out["keywords"]
        # 3 dict chunks survive the isinstance filter (the content:None dict is a
        # valid dict — empty string after `or ""`); the str element is dropped.
        assert len(keywords) == 3
        # the technical chunk yields real 3+-letter tokens, stop-words removed.
        assert any(len(kw) > 0 for kw in keywords)
        # `the` is a stop-word — never present in any extracted list.
        assert all("the" not in kw for kw in keywords)

    def test_present_but_none_content_does_not_crash(self):
        # A present-but-None `content` coerces to "" — no `.lower()` crash.
        out = _extract_keywords([{"content": None}])
        assert out["keywords"] == [[]]

    def test_empty_corpus_returns_empty(self):
        assert _extract_keywords(None) == {"keywords": []}


class TestMakeResultFusion:
    """`_make_result_fusion` closure factory (HybridRAG result_fusion)."""

    def test_default_method_bound_into_closure(self):
        fn = _make_result_fusion(fusion_method="rrf")
        out = fn(semantic_results={}, statistical_results={})
        assert out["fused_results"]["fusion_method"] == "rrf"

    def test_custom_method_bound_into_closure(self):
        # Rule-3c: the build-time arg is consumed, not silently dropped.
        fn = _make_result_fusion(fusion_method="linear")
        out = fn(semantic_results={}, statistical_results={})
        assert out["fused_results"]["fusion_method"] == "linear"

    def test_fuses_and_ranks_overlapping_docs(self):
        fn = _make_result_fusion(fusion_method="rrf")
        out = fn(
            semantic_results={"results": [{"id": "d1"}, {"id": "d2"}]},
            statistical_results={"results": [{"id": "d1"}, {"id": "d3"}]},
        )
        fused = out["fused_results"]
        # d1 appears in both → fused from two sources, top-ranked.
        assert fused["documents"][0]["id"] == "d1"
        assert len(fused["documents"]) == 3

    def test_present_but_none_inputs_do_not_crash(self):
        # Unwired upstream branches arrive None — isinstance guard, no crash.
        fn = _make_result_fusion(fusion_method="rrf")
        out = fn(semantic_results=None, statistical_results=None)
        assert out["fused_results"]["documents"] == []


class TestProcessLevels:
    """`_process_levels` (HierarchicalRAG level_processor)."""

    def test_buckets_chunks_by_hierarchy_level(self):
        out = _process_levels(
            [
                {"content": "doc", "hierarchy_level": "document"},
                {"content": "sec", "hierarchy_level": "section"},
                {"content": None},
                "not-a-dict",
            ]
        )
        level_chunks = out["level_chunks"]
        assert len(level_chunks["document"]) == 1
        assert len(level_chunks["section"]) == 1
        assert len(level_chunks["paragraph"]) == 0
        assert out["levels"] == ["document", "section", "paragraph"]

    def test_empty_corpus_returns_empty_buckets(self):
        out = _process_levels(None)
        assert out["level_chunks"] == {
            "document": [],
            "section": [],
            "paragraph": [],
        }

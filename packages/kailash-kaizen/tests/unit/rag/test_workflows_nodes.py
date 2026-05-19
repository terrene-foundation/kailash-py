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
        """create_hybrid_rag_workflow defaults to RRF fusion in the codegen."""
        wf = _wf(create_hybrid_rag_workflow(RAGConfig()))
        fusion_code = _node(wf, "result_fusion").config["code"]
        assert '"fusion_method": "rrf"' in fusion_code

    def test_hybrid_builder_honors_fusion_method_arg(self):
        """The fusion_method arg is consumed — baked into the fusion codegen.

        It flows into the `result_fusion` PythonCodeNode's output field; a
        Rule-3c silent-drop would leave the codegen with a stale literal.
        """
        wf = _wf(create_hybrid_rag_workflow(RAGConfig(), fusion_method="linear"))
        fusion_code = _node(wf, "result_fusion").config["code"]
        assert '"fusion_method": "linear"' in fusion_code

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

    def test_adaptive_workflow_llm_model_default(self):
        """The llm_model arg is bound (default gpt-4-class identifier)."""
        node = AdaptiveRAGWorkflowNode()
        assert node.llm_model  # type: ignore[attr-defined]

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

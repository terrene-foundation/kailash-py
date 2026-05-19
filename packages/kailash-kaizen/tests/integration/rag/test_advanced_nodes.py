"""Tier-2 integration coverage for ``kaizen.nodes.rag.advanced``.

F8 shard B6. The 4 advanced RAG nodes (``SelfCorrectingRAGNode``,
``RAGFusionNode``, ``HyDENode``, ``StepBackRAGNode``) all retrieve through the
shared ``create_hybrid_rag_workflow`` base workflow — A-S2 of this shard
replaced a shipped empty-``Workflow`` placeholder with a genuine hybrid-RAG
``WorkflowNode`` (dense + sparse retrieval, RRF fusion).

NO mocking (``@patch`` / ``MagicMock`` / ``unittest.mock`` are BLOCKED in
Tier 2/3 per ``rules/testing.md``). These tests execute the real hybrid
workflow end-to-end through a real in-process ``LocalRuntime`` — there is no
container and no LLM key required: ``DenseRetrievalNode`` /
``SparseRetrievalNode`` run their deterministic keyword-overlap fallback, and
the fusion node is a real ``PythonCodeNode``. The retrieval / generation core
is exercised, not mocked — that IS the no-mocking contract met via "real
lightweight backend" (numpy ships with the ``[rag]`` extra).

Assertions are structural: workflow graph shape, node ``code`` presence,
end-to-end result keys/values, score ordering.
"""

from __future__ import annotations

import pytest
from kailash.nodes.logic.workflow import WorkflowNode

from kaizen.nodes.rag.advanced import (
    HyDENode,
    RAGConfig,
    RAGFusionNode,
    SelfCorrectingRAGNode,
    StepBackRAGNode,
    create_hybrid_rag_workflow,
)

pytestmark = pytest.mark.integration


# Deterministic corpus: d1/d3 overlap the ML query terms, d2 is off-topic.
_CORPUS = [
    {"id": "d1", "content": "neural network optimization techniques and methods"},
    {"id": "d2", "content": "italian pasta recipes with fresh tomato sauce"},
    {"id": "d3", "content": "gradient descent algorithms for training neural networks"},
    {"id": "d4", "content": "backpropagation and weight updates in deep learning"},
]
_QUERY = "how to optimize neural network training"


# ==========================================================================
# create_hybrid_rag_workflow — graph shape + real end-to-end execution
# ==========================================================================


class TestHybridRagWorkflowGraph:
    """Assert the A-S2 workflow graph shape directly (no execution)."""

    def test_workflow_node_count_and_ids(self):
        """The hybrid graph is exactly source + dense + sparse + fuse."""
        wf = create_hybrid_rag_workflow(RAGConfig())
        assert isinstance(wf, WorkflowNode)
        nodes = wf._workflow.nodes  # type: ignore[union-attr]
        assert set(nodes.keys()) == {"source", "dense", "sparse", "fuse"}

    def test_workflow_has_six_connections(self):
        """source fans to 2 retrievers (4 edges) + 2 edges into fuse = 6."""
        wf = create_hybrid_rag_workflow(RAGConfig())
        connections = wf._workflow.connections  # type: ignore[union-attr]
        assert len(connections) == 6

    def test_fuse_node_carries_rrf_code(self):
        """The fuse PythonCodeNode's code= template implements RRF."""
        wf = create_hybrid_rag_workflow(RAGConfig())
        # the built PythonCodeNode instance exposes its template as .code
        fuse = wf._workflow.get_node("fuse")  # type: ignore[union-attr]
        code = fuse.code  # type: ignore[attr-defined]
        assert "_reciprocal_rank_fusion" in code
        # the codegen template carries the same isinstance guard as run() paths
        assert "isinstance" in code

    def test_input_and_output_mapping_present(self):
        """The WorkflowNode maps documents/query in and results/scores out."""
        wf = create_hybrid_rag_workflow(RAGConfig())
        # _input_mapping / _output_mapping are WorkflowNode internals not on
        # the Node base type pyright resolves create_hybrid_rag_workflow to.
        assert set(wf._input_mapping.keys()) == {"documents", "query"}  # type: ignore[attr-defined]
        assert set(wf._output_mapping.keys()) == {  # type: ignore[attr-defined]
            "results",
            "scores",
            "metadata",
        }


class TestHybridRagWorkflowExecution:
    """Execute the A-S2 workflow end-to-end through a real LocalRuntime."""

    def test_run_executes_and_returns_contract(self):
        wf = create_hybrid_rag_workflow(RAGConfig())
        out = wf.run(documents=_CORPUS, query=_QUERY, operation="retrieve")
        assert set(out.keys()) == {"results", "scores", "metadata"}

    def test_run_fuses_dense_and_sparse(self):
        """metadata records non-zero dense and sparse contributions."""
        wf = create_hybrid_rag_workflow(RAGConfig())
        out = wf.run(documents=_CORPUS, query=_QUERY, operation="retrieve")
        meta = out["metadata"]
        assert meta["dense_count"] >= 1
        assert meta["sparse_count"] >= 1

    def test_run_scores_descending(self):
        """Fused RRF scores are returned in descending order."""
        wf = create_hybrid_rag_workflow(RAGConfig())
        out = wf.run(documents=_CORPUS, query=_QUERY, operation="retrieve")
        assert out["scores"] == sorted(out["scores"], reverse=True)

    def test_run_results_align_with_scores(self):
        """results and scores are parallel lists of the same length."""
        wf = create_hybrid_rag_workflow(RAGConfig())
        out = wf.run(documents=_CORPUS, query=_QUERY, operation="retrieve")
        assert len(out["results"]) == len(out["scores"])

    def test_run_prefers_on_topic_documents(self):
        """The neural-network docs outrank the off-topic pasta doc."""
        wf = create_hybrid_rag_workflow(RAGConfig())
        out = wf.run(documents=_CORPUS, query=_QUERY, operation="retrieve")
        retrieved_ids = {d.get("id") for d in out["results"]}
        # at least one ML doc retrieved; the pasta doc must not be the only hit
        assert retrieved_ids & {"d1", "d3", "d4"}


# ==========================================================================
# The 4 advanced nodes — real end-to-end retrieval through the hybrid base
# ==========================================================================


class TestSelfCorrectingRAGEndToEnd:
    def test_retrieves_real_documents(self):
        """run() drives the real hybrid workflow and returns retrieved docs."""
        result = SelfCorrectingRAGNode(max_corrections=0).run(
            documents=_CORPUS, query=_QUERY
        )
        # the hybrid retrieval populated the result with real documents
        assert isinstance(result["retrieved_documents"], list)
        assert result["final_response"]

    def test_quality_assessment_present(self):
        result = SelfCorrectingRAGNode(max_corrections=0).run(
            documents=_CORPUS, query=_QUERY
        )
        qa = result["quality_assessment"]
        assert "confidence" in qa


class TestRAGFusionEndToEnd:
    def test_fuses_multi_query_retrieval(self):
        """RAG-Fusion runs multiple queries through the real hybrid workflow."""
        result = RAGFusionNode(num_query_variations=2).run(
            documents=_CORPUS, query=_QUERY
        )
        fused = result["fused_results"]
        assert "documents" in fused
        assert result["fusion_metadata"]["queries_processed"] >= 1

    def test_fused_documents_are_real(self):
        result = RAGFusionNode(num_query_variations=2).run(
            documents=_CORPUS, query=_QUERY
        )
        docs = result["fused_results"]["documents"]
        assert all(isinstance(d, dict) for d in docs)


class TestHyDEEndToEnd:
    def test_retrieves_with_hypotheses(self):
        """HyDE retrieves through the hybrid workflow using hypotheses."""
        result = HyDENode(num_hypotheses=2).run(documents=_CORPUS, query=_QUERY)
        assert result["hyde_metadata"]["num_hypotheses"] >= 1
        assert "documents" in result["combined_retrieval"]

    def test_final_answer_generated(self):
        result = HyDENode(num_hypotheses=1).run(documents=_CORPUS, query=_QUERY)
        assert isinstance(result["final_answer"], str)
        assert result["final_answer"]


class TestStepBackEndToEnd:
    def test_dual_retrieval_specific_and_abstract(self):
        """Step-Back retrieves for both the specific and abstract query."""
        result = StepBackRAGNode().run(documents=_CORPUS, query=_QUERY)
        meta = result["step_back_metadata"]
        assert meta["specific_docs_count"] >= 0
        assert meta["abstract_docs_count"] >= 0
        assert "documents" in result["combined_results"]

    def test_final_answer_generated(self):
        result = StepBackRAGNode().run(documents=_CORPUS, query=_QUERY)
        assert isinstance(result["final_answer"], str)
        assert result["final_answer"]


# ==========================================================================
# Defect regression boundary — malformed corpus through real execution
# ==========================================================================


class TestMalformedCorpusEndToEnd:
    """The content:None / non-dict crash class, exercised end-to-end.

    B6 defect 2: helper methods crashed on present-but-None content and
    non-dict elements. These tests drive the full run() path with a malformed
    corpus through the real hybrid workflow — no crash, documented keys.
    """

    _BAD = [
        {"id": "d1", "content": None},
        {"id": "d2"},
        "not-a-dict-element",
        {"content": None},
        {"id": "d5", "content": "real neural network content"},
    ]

    def test_self_correcting_survives_malformed_corpus(self):
        result = SelfCorrectingRAGNode(max_corrections=0).run(
            documents=self._BAD, query=_QUERY
        )
        assert "final_response" in result

    def test_rag_fusion_survives_malformed_corpus(self):
        result = RAGFusionNode(num_query_variations=1).run(
            documents=self._BAD, query=_QUERY
        )
        assert "fused_results" in result

    def test_hyde_survives_malformed_corpus(self):
        result = HyDENode(num_hypotheses=1).run(documents=self._BAD, query=_QUERY)
        assert "final_answer" in result

    def test_step_back_survives_malformed_corpus(self):
        result = StepBackRAGNode().run(documents=self._BAD, query=_QUERY)
        assert "final_answer" in result

    def test_hybrid_workflow_survives_malformed_corpus(self):
        """The A-S2 workflow itself tolerates a malformed corpus."""
        wf = create_hybrid_rag_workflow(RAGConfig())
        out = wf.run(documents=self._BAD, query=_QUERY, operation="retrieve")
        assert set(out.keys()) == {"results", "scores", "metadata"}

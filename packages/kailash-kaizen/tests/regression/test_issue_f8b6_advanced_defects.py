"""Regression: latent ``kaizen.nodes.rag.advanced`` defects + the A-S2 stub.

F8 shard B6 surfaced, via behavioral coverage of the 4 advanced RAG nodes:

A-S2 — create_hybrid_rag_workflow shipped placeholder.
  The function returned ``Workflow(name="hybrid_rag_fallback", nodes=[],
  connections=[])`` and imported it from ``kaizen.workflow.graph`` — a module
  that does not exist, so the placeholder ``ImportError``'d the moment any of
  the 4 advanced nodes called it via ``_initialize_components()``. It is a
  shipped ``zero-tolerance.md`` Rule 2 stub ("return a simple mock workflow").
  Fix: a genuine hybrid-RAG WorkflowNode — dense (DenseRetrievalNode) + sparse
  (SparseRetrievalNode) retrieval fused with Reciprocal Rank Fusion.

Defect 1 — all 4 advanced nodes crashed on every run().
  ``_initialize_components()`` builds an LLMAgentNode named ``f"{self.name}
  ..."``. ``kailash.nodes.base.Node.__init__`` stores constructor kwargs in
  ``self.config`` and never sets ``self.name``; the f-string raised
  ``AttributeError: object has no attribute 'name'`` before any retrieval ran.
  Since _initialize_components() is the FIRST statement of every run(), all
  four nodes were fully broken. Fix: bind ``self.name`` in each __init__.

Defect 2 — content:None / non-dict crash class (10 helper sites).
  ``doc.get("content", "")`` returns ``None`` for a present-but-None key (the
  ``""`` default fires ONLY for a MISSING key); a following slice / .lower()
  then raised ``TypeError``. And ``doc.get("id", doc.get("content","")[:50])``
  evaluates the slice default EAGERLY — it crashed even when ``id`` was
  present. A non-dict element (documents is arbitrary upstream input) raised
  ``AttributeError`` on ``.get`` / ``.copy``. Fix: ``_doc_content`` /
  ``_doc_dedup_key`` helpers + ``isinstance(doc, dict)`` guards; the fuse
  codegen template carries the same guards (the B1-B5 two-path lesson).

These tests fail against the pre-B6 advanced.py and pass against the fix.
Assertions are behavioral: call the function, assert it returns / does not
raise — never source-grep.
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

pytestmark = pytest.mark.regression


_CORPUS = [
    {"id": "d1", "content": "neural network optimization"},
    {"id": "d2", "content": "gradient descent for neural networks"},
]
# content:None (present-but-None), missing content, non-dict element.
_MALFORMED = [
    {"id": "d1", "content": None},
    {"id": "d2"},
    "not-a-dict-element",
    {"content": None},
]


# ==========================================================================
# A-S2 — create_hybrid_rag_workflow is a real workflow, not a placeholder
# ==========================================================================


class TestAS2HybridWorkflowImplemented:
    def test_returns_workflow_node_not_empty_workflow(self):
        """A-S2: the factory returns a real WorkflowNode (was empty Workflow)."""
        wf = create_hybrid_rag_workflow(RAGConfig())
        assert isinstance(wf, WorkflowNode)

    def test_workflow_is_not_empty(self):
        """The pre-B6 placeholder shipped nodes=[]; the real one carries the
        full retrieval pipeline (source + dense + sparse + fuse + the three
        from_function projector nodes the post-migration output_mapping needs)."""
        wf = create_hybrid_rag_workflow(RAGConfig())
        node_ids = set(wf._workflow.nodes.keys())  # type: ignore[union-attr]
        assert {"source", "dense", "sparse", "fuse"} <= node_ids

    def test_workflow_runs_and_returns_consumed_contract(self):
        """The pre-B6 placeholder ImportError'd; the real one executes."""
        wf = create_hybrid_rag_workflow(RAGConfig())
        out = wf.run(documents=_CORPUS, query="optimize neural networks")
        assert set(out.keys()) == {"results", "scores", "metadata"}


# ==========================================================================
# Defect 1 — self.name AttributeError on every advanced-node run()
# ==========================================================================


class TestDefect1NodeNameBound:
    """All 4 nodes must expose self.name (referenced in _initialize_components)."""

    @pytest.mark.parametrize(
        "cls",
        [SelfCorrectingRAGNode, RAGFusionNode, HyDENode, StepBackRAGNode],
    )
    def test_node_has_name_attribute(self, cls):
        assert hasattr(cls(), "name")

    @pytest.mark.parametrize(
        "cls",
        [SelfCorrectingRAGNode, RAGFusionNode, HyDENode, StepBackRAGNode],
    )
    def test_custom_name_is_bound(self, cls):
        assert cls(name="custom_rag").name == "custom_rag"

    def test_self_correcting_run_does_not_attributeerror(self):
        """run() reached the verifier-naming f-string and would AttributeError."""
        result = SelfCorrectingRAGNode(max_corrections=0).run(
            documents=_CORPUS, query="optimize neural networks"
        )
        assert "final_response" in result

    def test_rag_fusion_run_does_not_attributeerror(self):
        result = RAGFusionNode(num_query_variations=1).run(
            documents=_CORPUS, query="optimize neural networks"
        )
        assert "fused_results" in result

    def test_hyde_run_does_not_attributeerror(self):
        result = HyDENode(num_hypotheses=1).run(
            documents=_CORPUS, query="optimize neural networks"
        )
        assert "final_answer" in result

    def test_step_back_run_does_not_attributeerror(self):
        result = StepBackRAGNode().run(
            documents=_CORPUS, query="optimize neural networks"
        )
        assert "final_answer" in result


# ==========================================================================
# Defect 2 — content:None / non-dict crash class across 4 nodes' helpers
# ==========================================================================


class TestDefect2NoneContentAndNonDict:
    """Malformed documents must not crash any advanced-node run() path."""

    def test_self_correcting_run_survives_malformed_corpus(self):
        result = SelfCorrectingRAGNode(max_corrections=0).run(
            documents=_MALFORMED, query="optimize neural networks"
        )
        assert "final_response" in result

    def test_rag_fusion_run_survives_malformed_corpus(self):
        result = RAGFusionNode(num_query_variations=1).run(
            documents=_MALFORMED, query="optimize neural networks"
        )
        assert "fused_results" in result

    def test_hyde_run_survives_malformed_corpus(self):
        result = HyDENode(num_hypotheses=1).run(
            documents=_MALFORMED, query="optimize neural networks"
        )
        assert "final_answer" in result

    def test_step_back_run_survives_malformed_corpus(self):
        result = StepBackRAGNode().run(
            documents=_MALFORMED, query="optimize neural networks"
        )
        assert "final_answer" in result

    def test_self_correcting_generate_response_none_content(self):
        """_generate_response: doc.get('content','')[:500] crashed on None."""
        node = SelfCorrectingRAGNode()
        out = node._generate_response("q", [{"id": "d1", "content": None}])  # type: ignore[attr-defined]
        assert isinstance(out, str)

    def test_rag_fusion_rrf_none_content_and_non_dict(self):
        """_reciprocal_rank_fusion: eager id/content default + non-dict crash."""
        node = RAGFusionNode()
        bad = [{"id": "d1", "content": None}, "not-a-dict"]
        out = node._reciprocal_rank_fusion([{"results": bad}])  # type: ignore[attr-defined]
        assert "documents" in out

    def test_hyde_combine_hypothesis_results_none_content(self):
        """_combine_hypothesis_results: doc['hyde_sources']= crashed on non-dict."""
        node = HyDENode()
        bad = [{"id": "d1", "content": None}, "not-a-dict"]
        out = node._combine_hypothesis_results(  # type: ignore[attr-defined]
            [{"retrieval_result": {"results": bad, "scores": [1.0, 2.0]}}]
        )
        assert "documents" in out

    def test_step_back_combine_results_non_dict(self):
        """_combine_step_back_results: doc.copy() crashed on a non-dict element."""
        node = StepBackRAGNode()
        bad = [{"id": "d1", "content": None}, "not-a-dict"]
        out = node._combine_step_back_results(  # type: ignore[attr-defined]
            {"results": bad, "scores": [1.0, 2.0]},
            {"results": [], "scores": []},
            "specific",
            "abstract",
        )
        assert "documents" in out

    def test_hybrid_workflow_fuse_template_guards_non_dict(self):
        """The fuse codegen template (second path) carries the isinstance guard.

        B1-B5 lesson 2: a defect spanning a run()/helper path AND a code=
        codegen template must be fixed on both. The fuse PythonCodeNode runs
        RRF over retrieved docs; a malformed corpus reaching it must not crash
        the workflow execution.
        """
        wf = create_hybrid_rag_workflow(RAGConfig())
        out = wf.run(documents=_MALFORMED, query="optimize neural networks")
        assert set(out.keys()) == {"results", "scores", "metadata"}


# ==========================================================================
# Substance — _refine_documents honors verification `issues`, not only
# `suggestions`. The self-correction loop computed verification issues and
# then discarded them; refinement now responds to what the verifier found.
# ==========================================================================

_TEN_DOCS = [{"id": f"d{i}", "content": f"document {i}"} for i in range(10)]


class TestRefineDocumentsHonorsIssues:
    """SelfCorrectingRAGNode._refine_documents acts on verification feedback."""

    def test_relevance_issue_trims_document_set(self):
        """A relevance/noise issue (no filter suggestion) trims the set.

        Pre-B6: _refine_documents read only `suggestions`; a verification that
        reported a relevance issue but gave no "filter" suggestion left the
        document set unchanged — shallower self-correction than advertised.
        """
        node = SelfCorrectingRAGNode()
        verification = {
            "issues": ["several irrelevant documents were retrieved"],
            "suggestions": [],  # no "filter" advice — only the issue drives it
        }
        refined = node._refine_documents(_TEN_DOCS, verification)  # type: ignore[attr-defined]
        assert len(refined) < len(_TEN_DOCS)
        assert len(refined) == 8  # top 80% by retrieval rank

    def test_coverage_issue_preserves_full_set(self):
        """A coverage issue means the set is too narrow — keep all docs."""
        node = SelfCorrectingRAGNode()
        verification = {
            "issues": ["retrieved context is incomplete; key facts missing"],
            "suggestions": ["filter the documents"],  # loose filter advice
        }
        refined = node._refine_documents(_TEN_DOCS, verification)  # type: ignore[attr-defined]
        # a coverage issue overrides a loose filter suggestion — trimming a
        # too-narrow set would make the next correction attempt worse
        assert len(refined) == len(_TEN_DOCS)

    def test_no_actionable_feedback_returns_unchanged(self):
        node = SelfCorrectingRAGNode()
        verification = {"issues": ["minor phrasing nitpick"], "suggestions": []}
        refined = node._refine_documents(_TEN_DOCS, verification)  # type: ignore[attr-defined]
        assert refined == _TEN_DOCS

    def test_filter_suggestion_still_trims(self):
        """An explicit filter suggestion still trims (suggestions path intact)."""
        node = SelfCorrectingRAGNode()
        verification = {"issues": [], "suggestions": ["filter low-quality docs"]}
        refined = node._refine_documents(_TEN_DOCS, verification)  # type: ignore[attr-defined]
        assert len(refined) == 8

    def test_refine_documents_signature_has_no_query_param(self):
        """The spurious unused `query` parameter was removed."""
        import inspect

        # @register_node erases the concrete type; the helper is real.
        sig = inspect.signature(SelfCorrectingRAGNode._refine_documents)  # type: ignore[attr-defined]
        params = [p for p in sig.parameters if p != "self"]
        assert params == ["documents", "verification"]

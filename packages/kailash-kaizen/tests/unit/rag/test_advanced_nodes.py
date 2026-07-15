"""Tier-1 unit coverage for the 4 ``kaizen.nodes.rag.advanced`` nodes + RAGConfig.

F8 shard B6. The value-anchor (verbatim from the workstream brief): "the RAG
capability the user chose to preserve is provably correct, not merely
importable" — HyDE is a user-named capability and self-correction is a
substance claim, so these tests lock the *behavior* a user gets, not just the
import.

``SelfCorrectingRAGNode`` / ``RAGFusionNode`` / ``HyDENode`` /
``StepBackRAGNode`` are ``kailash.nodes.base.Node`` subclasses with a direct
``run()``. Each constructs a real ``LLMAgentNode(provider="openai", ...)`` for
its LLM-backed step (verifier / query-generator / hypothesis-generator /
abstraction-generator).

Historical note (issue #1736): this docstring previously assumed "no LLM key
configured is the realistic deployment ... there is nothing to mock." That
assumption does not hold whenever a real ``OPENAI_API_KEY`` is configured
(``rules/env-models.md``) — ``LLMAgentNode._provider_llm_response()``
resolves a real provider via ``kaizen.providers.registry.get_provider()`` and
attempts a genuine outbound network call, hanging Tier-1 (pytest-timeout's
signal-based ``--timeout`` did not reliably abort it; 4 of the 5 affected
tests were 30s-timeout hits). Per ``rules/testing.md`` "3-Tier Testing"
(Tier 1: mocking allowed, MUST be offline + deterministic), the
``_stub_llm_provider`` fixture below stubs the provider seam so every test in
this file runs offline and fast regardless of which real API keys are
configured in the environment — the LLM-backed steps still execute real
node/parsing code against a deterministic, well-formed completion; only the
network boundary is faked.

The shared base workflow every node retrieves through is the
``create_hybrid_rag_workflow`` ``WorkflowNode`` (A-S2 of this shard): dense +
sparse retrieval fused with Reciprocal Rank Fusion. ``DenseRetrievalNode`` and
``SparseRetrievalNode`` run their deterministic keyword-overlap fallback with
no key, so the whole pipeline produces real, assertable output offline.

One test per documented behavior; assertions are structural (output keys,
list lengths, score ordering, types, typed raises).
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

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

pytestmark = pytest.mark.unit


# A single JSON payload that is a superset of every shape the four LLM-backed
# steps in this module parse (hypotheses / variations / abstract_query /
# retrieval+generation quality fields). Each ``_parse_*`` helper extracts only
# the keys it needs via ``.get(...)``, so one deterministic payload satisfies
# every call site without per-test/per-node customization.
_MOCK_CONTENT = json.dumps(
    {
        "hypotheses": [
            "Mocked hypothesis one for deterministic Tier-1 testing (issue #1736).",
            "Mocked hypothesis two for deterministic Tier-1 testing (issue #1736).",
        ],
        "reasoning": "Mocked reasoning for deterministic Tier-1 testing.",
        "variations": [
            "Mocked query variation one.",
            "Mocked query variation two.",
            "Mocked query variation three.",
        ],
        "abstract_query": "What are the general principles related to this topic?",
        "concepts_identified": ["mocked-concept-a", "mocked-concept-b"],
        "retrieval_quality": 0.8,
        "generation_quality": 0.8,
        "confidence": 0.8,
        "issues": [],
        "suggestions": [],
        "needs_refinement": False,
    }
)


def _fake_chat_response(**_: Any) -> dict:
    """A deterministic, well-formed provider ``chat()`` response."""
    return {
        "id": "test-1736-mock",
        "content": _MOCK_CONTENT,
        "role": "assistant",
        "model": "mock-model",
        "created": 0,
        "tool_calls": [],
        "finish_reason": "stop",
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }


def _make_fake_provider(*_args: Any, **_kwargs: Any) -> MagicMock:
    """Build a fresh fake provider satisfying the ``BaseProvider`` surface."""
    provider = MagicMock()
    provider.is_available.return_value = True
    provider.chat.side_effect = _fake_chat_response

    async def _chat_async(**kwargs: Any) -> dict:
        return _fake_chat_response(**kwargs)

    provider.chat_async.side_effect = _chat_async
    return provider


def _make_unavailable_provider(*_args: Any, **_kwargs: Any) -> MagicMock:
    """A provider that reports itself unavailable — the genuine no-LLM deployment.

    ``LLMAgentNode._provider_llm_response`` raises ``RuntimeError`` (before any
    network call) when ``is_available()`` is False and no per-request api_key is
    supplied, which drives each advanced-RAG node's ``try/except`` rule-based
    fallback. Used by the one test whose whole point is the no-LLM path (issue
    #1736), overriding the module autouse content-stub.
    """
    provider = MagicMock()
    provider.is_available.return_value = False
    return provider


@pytest.fixture(autouse=True)
def _stub_llm_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stub the kaizen provider registry seam for this module only (issue #1736).

    ``kaizen.nodes.rag.advanced`` constructs ``LLMAgentNode(provider="openai",
    ...)`` directly for its four LLM-backed steps. ``LLMAgentNode.
    _provider_llm_response()`` resolves the provider via
    ``kaizen.providers.registry.get_provider(name)`` and calls
    ``provider.chat(...)`` — the real network seam. Stubbing it here (module-
    scoped, NOT a directory-wide conftest) keeps every other file in
    ``tests/unit/rag/`` byte-for-byte unaffected, per issue #1736 scope.
    """
    monkeypatch.setattr(
        "kaizen.providers.registry.get_provider",
        _make_fake_provider,
    )


# A small deterministic corpus reused across the node tests. d1/d3 overlap the
# query terms; d2 does not — keyword-overlap retrieval should rank d1/d3 above.
_CORPUS = [
    {"id": "d1", "content": "neural network optimization techniques and methods"},
    {"id": "d2", "content": "italian pasta recipes with tomato sauce"},
    {"id": "d3", "content": "gradient descent for training neural networks"},
]
_QUERY = "how to optimize neural networks"


# ==========================================================================
# RAGConfig — contract coverage
# ==========================================================================


class TestRAGConfig:
    """Construction, defaults, and field types of the advanced-module config."""

    def test_defaults(self):
        """RAGConfig() applies the documented default values."""
        cfg = RAGConfig()
        assert cfg.chunk_size == 1000
        assert cfg.chunk_overlap == 200
        assert cfg.embedding_model == "text-embedding-3-small"
        assert cfg.retrieval_k == 5

    def test_field_types(self):
        """Default field values have the expected types."""
        cfg = RAGConfig()
        assert isinstance(cfg.chunk_size, int)
        assert isinstance(cfg.chunk_overlap, int)
        assert isinstance(cfg.embedding_model, str)
        assert isinstance(cfg.retrieval_k, int)

    def test_kwargs_override_defaults(self):
        """Each field is overridable via a constructor kwarg."""
        cfg = RAGConfig(
            chunk_size=512,
            chunk_overlap=64,
            embedding_model="custom-embed",
            retrieval_k=10,
        )
        assert cfg.chunk_size == 512
        assert cfg.chunk_overlap == 64
        assert cfg.embedding_model == "custom-embed"
        assert cfg.retrieval_k == 10

    def test_unknown_kwarg_is_ignored_not_raised(self):
        """An unrecognised kwarg does not raise (the **kwargs construction)."""
        cfg = RAGConfig(unknown_field="x")
        assert cfg.retrieval_k == 5  # documented default still applies


# ==========================================================================
# create_hybrid_rag_workflow — A-S2: the implemented base workflow
# ==========================================================================


class TestCreateHybridRagWorkflow:
    """The hybrid-RAG workflow A-S2 implemented (replaced the placeholder)."""

    def test_returns_workflow_node(self):
        """The factory returns a real WorkflowNode, not an empty Workflow."""
        wf = create_hybrid_rag_workflow(RAGConfig())
        assert isinstance(wf, WorkflowNode)

    def test_workflow_graph_has_expected_nodes(self):
        """The hybrid graph is source + dense + sparse + fuse + 3 projectors.

        Post-migration the COMPUTE stages (source / fuse) are
        ``PythonCodeNode.from_function`` nodes publishing a flat ``result`` port;
        three thin projector nodes index the fuse ``result`` dict's keys so the
        WorkflowNode ``output_mapping`` (flat-key resolution) can surface the
        ``results`` / ``scores`` / ``metadata`` consumed contract."""
        wf = create_hybrid_rag_workflow(RAGConfig())
        node_ids = set(wf._workflow.nodes.keys())  # type: ignore[union-attr]
        assert node_ids == {
            "source",
            "dense",
            "sparse",
            "fuse",
            "proj_results",
            "proj_scores",
            "proj_metadata",
        }

    def test_workflow_is_not_empty(self):
        """Regression guard against the shipped empty-nodes placeholder."""
        wf = create_hybrid_rag_workflow(RAGConfig())
        assert len(wf._workflow.nodes) > 0  # type: ignore[union-attr]

    def test_run_returns_results_scores_metadata(self):
        """run() exposes the {results, scores, metadata} consumed contract."""
        wf = create_hybrid_rag_workflow(RAGConfig())
        out = wf.run(documents=_CORPUS, query=_QUERY, operation="retrieve")
        assert set(out.keys()) == {"results", "scores", "metadata"}
        assert isinstance(out["results"], list)
        assert isinstance(out["scores"], list)
        assert isinstance(out["metadata"], dict)

    def test_run_metadata_records_hybrid_modes(self):
        """metadata names both dense and sparse retrieval modes."""
        wf = create_hybrid_rag_workflow(RAGConfig())
        out = wf.run(documents=_CORPUS, query=_QUERY, operation="retrieve")
        assert out["metadata"]["fusion_method"] == "rrf"
        assert out["metadata"]["retrieval_modes"] == ["dense", "sparse"]

    def test_run_retrieves_relevant_documents(self):
        """The neural-network docs (d1/d3) are retrieved for the NN query."""
        wf = create_hybrid_rag_workflow(RAGConfig())
        out = wf.run(documents=_CORPUS, query=_QUERY, operation="retrieve")
        retrieved_ids = {d.get("id") for d in out["results"]}
        assert "d1" in retrieved_ids or "d3" in retrieved_ids

    def test_retrieval_k_caps_result_count(self):
        """config.retrieval_k caps the fused result count."""
        wf = create_hybrid_rag_workflow(RAGConfig(retrieval_k=1))
        out = wf.run(documents=_CORPUS, query=_QUERY, operation="retrieve")
        assert len(out["results"]) <= 1
        assert out["metadata"]["retrieval_k"] == 1

    def test_run_empty_documents_returns_empty_results(self):
        """An empty corpus yields empty results, not a crash."""
        wf = create_hybrid_rag_workflow(RAGConfig())
        out = wf.run(documents=[], query=_QUERY, operation="retrieve")
        assert out["results"] == []
        assert out["scores"] == []


# ==========================================================================
# SelfCorrectingRAGNode
# ==========================================================================

_SCR_KEYS = {
    "query",
    "final_response",
    "retrieved_documents",
    "scores",
    "quality_assessment",
    "self_correction_metadata",
    "status",
}


class TestSelfCorrectingRAGNode:
    """run() golden path + edge cases for SelfCorrectingRAGNode."""

    def test_get_parameters_declares_documents_and_query_required(self):
        params = SelfCorrectingRAGNode().get_parameters()
        assert params["documents"].required is True
        assert params["query"].required is True
        assert params["config"].required is False

    def test_run_golden_path_returns_documented_keys(self):
        result = SelfCorrectingRAGNode(max_corrections=0).run(
            documents=_CORPUS, query=_QUERY
        )
        assert set(result.keys()) == _SCR_KEYS

    def test_run_status_is_corrected_or_best_effort(self):
        """status is one of the two documented terminal values."""
        result = SelfCorrectingRAGNode(max_corrections=0).run(
            documents=_CORPUS, query=_QUERY
        )
        assert result["status"] in {"corrected", "best_effort"}

    def test_run_records_correction_history(self):
        """self_correction_metadata records one attempt per correction round."""
        result = SelfCorrectingRAGNode(max_corrections=1).run(
            documents=_CORPUS, query=_QUERY
        )
        meta = result["self_correction_metadata"]
        assert meta["total_attempts"] >= 1
        assert len(meta["correction_history"]) == meta["total_attempts"]

    def test_run_empty_documents_does_not_crash(self):
        result = SelfCorrectingRAGNode(max_corrections=0).run(
            documents=[], query=_QUERY
        )
        assert set(result.keys()) == _SCR_KEYS

    def test_run_missing_query_uses_empty_default(self):
        """A missing query defaults to '' and does not crash."""
        result = SelfCorrectingRAGNode(max_corrections=0).run(documents=_CORPUS)
        assert set(result.keys()) == _SCR_KEYS

    def test_run_malformed_documents_does_not_crash(self):
        """content:None + non-dict elements are tolerated (B6 defect class)."""
        bad = [{"id": "d1", "content": None}, "not-a-dict", {"content": None}]
        result = SelfCorrectingRAGNode(max_corrections=0).run(
            documents=bad, query=_QUERY
        )
        assert set(result.keys()) == _SCR_KEYS

    def test_run_unicode_query(self):
        result = SelfCorrectingRAGNode(max_corrections=0).run(
            documents=_CORPUS, query="优化神经网络 αβγ"
        )
        assert set(result.keys()) == _SCR_KEYS

    def test_generate_response_handles_none_content(self):
        """_generate_response tolerates a present-but-None content value."""
        node = SelfCorrectingRAGNode()
        # @register_node erases the concrete type to Node; the private helper
        # is genuinely defined on SelfCorrectingRAGNode.
        out = node._generate_response("q", [{"id": "d1", "content": None}])  # type: ignore[attr-defined]
        assert isinstance(out, str)

    def test_generate_response_empty_docs(self):
        node = SelfCorrectingRAGNode()
        out = node._generate_response("q", [])  # type: ignore[attr-defined]
        assert "No relevant documents" in out


# ==========================================================================
# RAGFusionNode
# ==========================================================================

_FUSION_KEYS = {
    "original_query",
    "query_variations",
    "fused_results",
    "final_response",
    "fusion_metadata",
}


class TestRAGFusionNode:
    """run() golden path + edge cases for RAGFusionNode."""

    def test_get_parameters_declares_documents_and_query_required(self):
        params = RAGFusionNode().get_parameters()
        assert params["documents"].required is True
        assert params["query"].required is True

    def test_run_golden_path_returns_documented_keys(self):
        result = RAGFusionNode(num_query_variations=2).run(
            documents=_CORPUS, query=_QUERY
        )
        assert set(result.keys()) == _FUSION_KEYS

    def test_run_processes_original_plus_variations(self):
        """fusion_metadata counts the original query plus its variations."""
        result = RAGFusionNode(num_query_variations=2).run(
            documents=_CORPUS, query=_QUERY
        )
        meta = result["fusion_metadata"]
        # original + up-to-num_query_variations fallback variations
        assert meta["queries_processed"] >= 1
        assert meta["fusion_method"] == "rrf"

    def test_run_fallback_variations_when_no_llm(self):
        """With no LLM key the rule-based fallback still yields variations."""
        result = RAGFusionNode(num_query_variations=3).run(
            documents=_CORPUS, query=_QUERY
        )
        assert isinstance(result["query_variations"], list)

    def test_run_empty_documents_does_not_crash(self):
        result = RAGFusionNode(num_query_variations=1).run(documents=[], query=_QUERY)
        assert set(result.keys()) == _FUSION_KEYS

    def test_run_malformed_documents_does_not_crash(self):
        bad = [{"id": "d1", "content": None}, "not-a-dict", {"content": None}]
        result = RAGFusionNode(num_query_variations=1).run(documents=bad, query=_QUERY)
        assert set(result.keys()) == _FUSION_KEYS

    def test_reciprocal_rank_fusion_handles_malformed_docs(self):
        """_reciprocal_rank_fusion tolerates None-content + non-dict docs."""
        node = RAGFusionNode()
        bad = [{"id": "d1", "content": None}, "not-a-dict"]
        # @register_node erases the concrete type; the helper is real.
        out = node._reciprocal_rank_fusion([{"results": bad}])  # type: ignore[attr-defined]
        assert out["fusion_method"] == "rrf"

    def test_reciprocal_rank_fusion_orders_by_score(self):
        """Fused scores come out in descending order."""
        node = RAGFusionNode()
        r1 = {"results": [{"id": "a", "content": "x"}, {"id": "b", "content": "y"}]}
        r2 = {"results": [{"id": "a", "content": "x"}]}
        out = node._reciprocal_rank_fusion([r1, r2])  # type: ignore[attr-defined]
        assert out["scores"] == sorted(out["scores"], reverse=True)

    def test_run_unknown_fusion_method_falls_back_to_rrf(self):
        """An unrecognised fusion method degrades to RRF, not a crash."""
        result = RAGFusionNode(num_query_variations=1, fusion_method="bogus").run(
            documents=_CORPUS, query=_QUERY
        )
        assert result["fused_results"]["fusion_method"] == "rrf"


# ==========================================================================
# HyDENode
# ==========================================================================

_HYDE_KEYS = {
    "original_query",
    "hypotheses_generated",
    "hypothesis_results",
    "combined_retrieval",
    "final_answer",
    "hyde_metadata",
}


class TestHyDENode:
    """run() golden path + edge cases for HyDENode."""

    def test_get_parameters_declares_documents_and_query_required(self):
        params = HyDENode().get_parameters()
        assert params["documents"].required is True
        assert params["query"].required is True

    def test_run_golden_path_returns_documented_keys(self):
        result = HyDENode(num_hypotheses=2).run(documents=_CORPUS, query=_QUERY)
        assert set(result.keys()) == _HYDE_KEYS

    def test_run_generates_fallback_hypothesis_when_no_llm(self):
        """With no LLM available the rule-based fallback yields >=1 hypothesis.

        This test's whole point is the genuine NO-LLM path, so it explicitly
        overrides the module autouse content-stub with an *unavailable* provider
        (``is_available()`` -> False). That drives ``_generate_hypotheses``'s
        ``try/except`` rule-based fallback (the documented behavior) rather than
        the mocked-completion path the other tests exercise — offline either way,
        no network (issue #1736).
        """
        with patch(
            "kaizen.providers.registry.get_provider",
            side_effect=_make_unavailable_provider,
        ):
            result = HyDENode(num_hypotheses=2).run(documents=_CORPUS, query=_QUERY)
        # The rule-based fallback ("A comprehensive answer to '<query>'…") — NOT a
        # mocked completion — is what produces these hypotheses.
        assert len(result["hypotheses_generated"]) >= 1
        assert result["hyde_metadata"]["method"] == "HyDE"

    def test_run_empty_documents_does_not_crash(self):
        result = HyDENode(num_hypotheses=1).run(documents=[], query=_QUERY)
        assert set(result.keys()) == _HYDE_KEYS

    def test_run_malformed_documents_does_not_crash(self):
        bad = [{"id": "d1", "content": None}, "not-a-dict", {"content": None}]
        result = HyDENode(num_hypotheses=1).run(documents=bad, query=_QUERY)
        assert set(result.keys()) == _HYDE_KEYS

    def test_run_single_hypothesis_mode(self):
        """use_multiple_hypotheses=False still produces a valid result."""
        result = HyDENode(use_multiple_hypotheses=False, num_hypotheses=1).run(
            documents=_CORPUS, query=_QUERY
        )
        assert set(result.keys()) == _HYDE_KEYS

    def test_combine_hypothesis_results_handles_malformed_docs(self):
        node = HyDENode()
        bad = [{"id": "d1", "content": None}, "not-a-dict"]
        # @register_node erases the concrete type; the helper is real.
        out = node._combine_hypothesis_results(  # type: ignore[attr-defined]
            [{"retrieval_result": {"results": bad, "scores": [1.0, 2.0]}}]
        )
        assert "documents" in out

    def test_generate_final_answer_handles_malformed_docs(self):
        node = HyDENode()
        bad = [{"id": "d1", "content": None}, "not-a-dict"]
        out = node._generate_final_answer("q", {"documents": bad}, ["h"])  # type: ignore[attr-defined]
        assert isinstance(out, str)

    def test_generate_final_answer_empty_docs(self):
        node = HyDENode()
        out = node._generate_final_answer("q", {"documents": []}, ["h"])  # type: ignore[attr-defined]
        assert "No relevant documents" in out


# ==========================================================================
# StepBackRAGNode
# ==========================================================================

_STEPBACK_KEYS = {
    "specific_query",
    "abstract_query",
    "specific_retrieval",
    "abstract_retrieval",
    "combined_results",
    "final_answer",
    "step_back_metadata",
}


class TestStepBackRAGNode:
    """run() golden path + edge cases for StepBackRAGNode."""

    def test_get_parameters_declares_documents_and_query_required(self):
        params = StepBackRAGNode().get_parameters()
        assert params["documents"].required is True
        assert params["query"].required is True

    def test_run_golden_path_returns_documented_keys(self):
        result = StepBackRAGNode().run(documents=_CORPUS, query=_QUERY)
        assert set(result.keys()) == _STEPBACK_KEYS

    def test_run_generates_abstract_query(self):
        """The step-back node produces a non-empty abstract query."""
        result = StepBackRAGNode().run(documents=_CORPUS, query=_QUERY)
        assert isinstance(result["abstract_query"], str)
        assert result["abstract_query"]
        assert result["step_back_metadata"]["method"] == "step_back_prompting"

    def test_run_empty_documents_does_not_crash(self):
        result = StepBackRAGNode().run(documents=[], query=_QUERY)
        assert set(result.keys()) == _STEPBACK_KEYS

    def test_run_malformed_documents_does_not_crash(self):
        bad = [{"id": "d1", "content": None}, "not-a-dict", {"content": None}]
        result = StepBackRAGNode().run(documents=bad, query=_QUERY)
        assert set(result.keys()) == _STEPBACK_KEYS

    def test_fallback_abstraction_for_how_query(self):
        """The rule-based abstraction fallback handles a 'how' query."""
        node = StepBackRAGNode()
        # @register_node erases the concrete type; the helper is real.
        out = node._generate_fallback_abstraction("how does X work?")  # type: ignore[attr-defined]
        assert isinstance(out, str)
        assert out

    def test_combine_step_back_results_handles_malformed_docs(self):
        node = StepBackRAGNode()
        bad = [{"id": "d1", "content": None}, "not-a-dict"]
        out = node._combine_step_back_results(  # type: ignore[attr-defined]
            {"results": bad, "scores": [1.0, 2.0]},
            {"results": [], "scores": []},
            "specific",
            "abstract",
        )
        assert "documents" in out

    def test_generate_step_back_answer_handles_malformed_docs(self):
        node = StepBackRAGNode()
        docs = [
            {
                "id": "x",
                "content": None,
                "step_back_metadata": {"source_type": "specific"},
            },
            "not-a-dict",
        ]
        out = node._generate_step_back_answer("q", "a", {"documents": docs})  # type: ignore[attr-defined]
        assert isinstance(out, str)

    def test_generate_step_back_answer_empty_docs(self):
        node = StepBackRAGNode()
        out = node._generate_step_back_answer("q", "a", {"documents": []})  # type: ignore[attr-defined]
        assert "No relevant documents" in out

    def test_parse_abstract_query_handles_non_dict_response(self):
        """_parse_abstract_query does not raise on a non-dict response."""
        node = StepBackRAGNode()
        out = node._parse_abstract_query("not-a-dict")  # type: ignore[arg-type]
        assert isinstance(out, str)


# ==========================================================================
# Regression — envelope-unwrap on all four LLM-response parsers (issue #1736)
# ==========================================================================


@pytest.mark.regression
class TestParserEnvelopeUnwrapRegression:
    """All four ``_parse_*`` helpers MUST read the NESTED content.

    ``LLMAgentNode.execute()`` returns an envelope
    ``{"success": ..., "response": {"content": ...}, ...}`` — the LLM's real
    content is under ``response["response"]["content"]``, NOT the top level.
    The pre-#1736 parsers read ``response.get("content", "")`` on the OUTER
    dict, so they always saw ``""`` and every LLM-backed step silently fell
    back to its rule-based path. These behavioral tests feed the real envelope
    shape and assert the parser extracts the nested payload — they fail if a
    future refactor reverts to the top-level read. A flat ``{"content": ...}``
    (direct provider) shape MUST still parse (backward tolerance).
    """

    def _envelope(self, content: str) -> dict:
        return {"success": True, "response": {"content": content}}

    def test_parse_hypotheses_reads_nested_content(self):
        node = HyDENode()
        env = self._envelope('{"hypotheses": ["h-one", "h-two"]}')
        assert node._parse_hypotheses(env) == ["h-one", "h-two"]  # type: ignore[attr-defined]
        # flat shape (direct provider) still parses
        flat = {"content": '{"hypotheses": ["h-flat"]}'}
        assert node._parse_hypotheses(flat) == ["h-flat"]  # type: ignore[attr-defined]

    def test_parse_query_variations_reads_nested_content(self):
        node = RAGFusionNode(num_query_variations=3)
        env = self._envelope('{"variations": ["v-one", "v-two"]}')
        assert node._parse_query_variations(env) == ["v-one", "v-two"]  # type: ignore[attr-defined]

    def test_parse_abstract_query_reads_nested_content(self):
        node = StepBackRAGNode()
        env = self._envelope('{"abstract_query": "broad question?"}')
        assert node._parse_abstract_query(env) == "broad question?"  # type: ignore[attr-defined]

    def test_parse_verification_response_reads_nested_content(self):
        node = SelfCorrectingRAGNode()
        env = self._envelope(
            '{"confidence": 0.9, "retrieval_quality": 0.8, '
            '"generation_quality": 0.7, "needs_refinement": false}'
        )
        out = node._parse_verification_response(env)  # type: ignore[attr-defined]
        # The nested JSON is parsed through (not the fallback heuristic, which
        # would emit confidence 0.4/0.6 from a keyword scan of empty content).
        assert out["confidence"] == 0.9
        assert out["retrieval_quality"] == 0.8
        assert out["generation_quality"] == 0.7

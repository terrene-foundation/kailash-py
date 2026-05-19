"""Tier-2a integration coverage for ``kaizen.nodes.rag.similarity``.

F8 shard B1. The 7 similarity nodes' shipped default code path is deterministic
``numpy``/keyword compute — ``numpy`` IS the real backend (no container, no LLM
key). These tests exercise the nodes against real ``numpy`` with NO mocking
(``@patch`` / ``MagicMock`` / ``unittest.mock`` are BLOCKED in Tier 2 per the
3-tier testing rule). Assertions are structural: result keys, score
ranges/ordering, list lengths, typed-error raises, and — for the error path —
the ``logger.error`` observability contract.

The value-anchor: "the RAG capability the user chose to preserve is provably
correct, not merely importable."
"""

from __future__ import annotations

import logging

import numpy as np
import pytest

from kaizen.nodes.rag.similarity import (
    ColBERTRetrievalNode,
    CrossEncoderRerankNode,
    DenseRetrievalNode,
    HybridFusionNode,
    MultiVectorRetrievalNode,
    PropositionBasedRetrievalNode,
    SparseRetrievalNode,
)

pytestmark = pytest.mark.integration


# A larger, realistic corpus than the unit tests use.
CORPUS = [
    {
        "content": "neural networks learn hierarchical feature representations",
        "id": "c1",
    },
    {"content": "gradient descent optimizes the loss function iteratively", "id": "c2"},
    {
        "content": "transformers use attention to model long range dependencies",
        "id": "c3",
    },
    {"content": "the recipe calls for two cups of flour and one egg", "id": "c4"},
    {
        "content": "attention is the core mechanism behind modern language models",
        "id": "c5",
    },
]


# ==========================================================================
# Dense / Sparse / ColBERT / MultiVector — real numpy scoring
# ==========================================================================


class TestDenseRetrievalIntegration:
    def test_real_numpy_keyword_scoring_ranks_relevant_first(self):
        node = DenseRetrievalNode()
        result = node.run(query="attention language models", documents=CORPUS, k=5)
        # The cooking doc has zero overlap and MUST be excluded.
        assert "c4" not in {r["id"] for r in result["results"]}
        # c5 ("attention ... language models") overlaps most heavily.
        assert result["results"][0]["id"] == "c5"
        assert result["scores"][0] == max(result["scores"])

    def test_score_values_are_real_floats_in_unit_range(self):
        node = DenseRetrievalNode()
        result = node.run(query="neural networks", documents=CORPUS, k=5)
        for score in result["scores"]:
            assert isinstance(score, float)
            assert 0.0 <= score <= 1.0

    def test_total_results_matches_result_list_length(self):
        node = DenseRetrievalNode()
        result = node.run(query="attention", documents=CORPUS, k=5)
        assert (
            result["total_results"] == len(result["results"]) == len(result["scores"])
        )


class TestSparseRetrievalIntegration:
    def test_bm25_idf_uses_real_numpy_log(self):
        # The BM25 IDF term routes through np.log — assert a real numeric score.
        node = SparseRetrievalNode()
        result = node.run(query="attention", documents=CORPUS, k=5)
        assert result["total_results"] >= 1
        for score in result["scores"]:
            assert np.isfinite(score)
            assert score >= 0.0

    def test_rarer_term_outscores_common_term(self):
        # BM25 IDF rewards term rarity. "flour" is unique to c4; "attention"
        # appears in c3 and c5. A query for the unique term must surface c4.
        node = SparseRetrievalNode()
        result = node.run(query="flour", documents=CORPUS, k=5)
        assert result["results"][0]["id"] == "c4"

    def test_descending_score_order(self):
        node = SparseRetrievalNode()
        result = node.run(query="attention language models", documents=CORPUS, k=5)
        assert result["scores"] == sorted(result["scores"], reverse=True)


class TestColBERTRetrievalIntegration:
    def test_maxsim_average_in_unit_range(self):
        node = ColBERTRetrievalNode()
        result = node.run(query="attention mechanism", documents=CORPUS, k=5)
        assert result["total_results"] >= 1
        for score in result["scores"]:
            assert 0.0 <= score <= 1.0

    def test_exact_token_match_scores_above_partial(self):
        node = ColBERTRetrievalNode()
        exact = [{"content": "attention mechanism", "id": "exact"}]
        partial = [{"content": "attentive mechanisms", "id": "partial"}]
        exact_score = node.run(query="attention mechanism", documents=exact, k=1)[
            "scores"
        ][0]
        partial_score = node.run(query="attention mechanism", documents=partial, k=1)[
            "scores"
        ][0]
        assert exact_score >= partial_score


class TestMultiVectorRetrievalIntegration:
    def test_weighted_combination_descending(self):
        node = MultiVectorRetrievalNode()
        result = node.run(query="attention language models", documents=CORPUS, k=5)
        assert result["scores"] == sorted(result["scores"], reverse=True)
        assert all(s >= 0.0 for s in result["scores"])

    def test_excludes_non_overlapping_documents(self):
        node = MultiVectorRetrievalNode()
        result = node.run(query="neural networks", documents=CORPUS, k=5)
        assert "c4" not in {r["id"] for r in result["results"]}


# ==========================================================================
# CrossEncoderRerank — two-stage pipeline against real Dense output
# ==========================================================================


class TestCrossEncoderRerankIntegration:
    def test_reranks_real_dense_retrieval_output(self):
        # Stage 1: real Dense retrieval. Stage 2: real cross-encoder rerank.
        dense = DenseRetrievalNode().run(
            query="attention models", documents=CORPUS, k=5
        )
        reranked = CrossEncoderRerankNode().run(
            query="attention models", initial_results=dense, k=5
        )
        assert reranked["retrieval_method"] == "cross_encoder_rerank"
        assert reranked["total_results"] == len(reranked["results"])
        assert reranked["scores"] == sorted(reranked["scores"], reverse=True)
        for score in reranked["scores"]:
            assert 0.0 <= score <= 1.0

    def test_reranked_count_equals_stage_one_size(self):
        dense = DenseRetrievalNode().run(
            query="attention models", documents=CORPUS, k=5
        )
        reranked = CrossEncoderRerankNode().run(
            query="attention models", initial_results=dense, k=2
        )
        assert reranked["reranked_count"] == dense["total_results"]
        assert reranked["total_results"] == 2


# ==========================================================================
# HybridFusion — fuses real Dense + real Sparse output
# ==========================================================================


class TestHybridFusionIntegration:
    def test_rrf_fuses_real_dense_and_sparse_output(self):
        query = "attention language models"
        dense = DenseRetrievalNode().run(query=query, documents=CORPUS, k=5)
        sparse = SparseRetrievalNode().run(query=query, documents=CORPUS, k=5)
        fused = HybridFusionNode().run(retrieval_results=[dense, sparse], k=5)
        assert fused["fusion_method"] == "rrf"
        assert fused["input_count"] == 2
        assert fused["scores"] == sorted(fused["scores"], reverse=True)
        assert all(s > 0.0 for s in fused["scores"])

    def test_weighted_fusion_normalizes_with_real_numpy(self):
        query = "attention language models"
        dense = DenseRetrievalNode().run(query=query, documents=CORPUS, k=5)
        sparse = SparseRetrievalNode().run(query=query, documents=CORPUS, k=5)
        fused = HybridFusionNode().run(
            retrieval_results=[dense, sparse], fusion_method="weighted", k=5
        )
        assert fused["fusion_method"] == "weighted"
        assert fused["scores"] == sorted(fused["scores"], reverse=True)

    def test_fused_result_count_bounded_by_unique_inputs(self):
        query = "attention"
        dense = DenseRetrievalNode().run(query=query, documents=CORPUS, k=5)
        sparse = SparseRetrievalNode().run(query=query, documents=CORPUS, k=5)
        unique_ids = {r["id"] for r in dense["results"]} | {
            r["id"] for r in sparse["results"]
        }
        fused = HybridFusionNode().run(retrieval_results=[dense, sparse], k=99)
        assert fused["total_results"] <= len(unique_ids)


# ==========================================================================
# PropositionBased — sentence extraction against the real corpus
# ==========================================================================


class TestPropositionBasedRetrievalIntegration:
    DOCS = [
        {
            "content": "Attention is the core mechanism behind language models. "
            "Transformers stack many attention layers.",
            "id": "doc-a",
        },
        {
            "content": "Gradient descent minimizes the loss. "
            "The learning rate controls the step size.",
            "id": "doc-b",
        },
    ]

    def test_extracts_and_matches_the_relevant_proposition(self):
        node = PropositionBasedRetrievalNode()
        result = node.run(query="attention language models", documents=self.DOCS, k=5)
        assert result["total_results"] == 1
        assert result["results"][0]["id"] == "doc-a"
        assert len(result["matched_propositions"]) == 1
        assert "attention" in result["matched_propositions"][0].lower()

    def test_scores_descending_and_in_unit_range(self):
        node = PropositionBasedRetrievalNode()
        result = node.run(
            query="gradient descent learning rate", documents=self.DOCS, k=5
        )
        assert result["scores"] == sorted(result["scores"], reverse=True)
        assert all(0.0 <= s <= 1.0 for s in result["scores"])


# ==========================================================================
# Error-path observability — logger.error IS the observable contract
# ==========================================================================


class TestErrorPathObservability:
    """The success path of these nodes has no fallback-WARN log (the keyword
    path is the only path, not a degraded fallback). The error path's
    ``logger.error`` IS the observable contract — a non-dict document forces
    the genuine error branch, and the log line MUST fire.
    """

    def test_dense_logs_error_on_unhandleable_input(self, caplog):
        node = DenseRetrievalNode()
        with caplog.at_level(logging.ERROR, logger="kaizen.nodes.rag.similarity"):
            # A bare string is not a dict — `doc.get` raises AttributeError,
            # which the broad except catches and logs.
            result = node.run(query="attention", documents=["not-a-dict"], k=5)
        assert result["results"] == []
        assert "error" in result
        assert any("Dense retrieval failed" in rec.message for rec in caplog.records)

    def test_sparse_logs_error_on_unhandleable_input(self, caplog):
        node = SparseRetrievalNode()
        with caplog.at_level(logging.ERROR, logger="kaizen.nodes.rag.similarity"):
            result = node.run(query="attention", documents=["not-a-dict"], k=5)
        assert "error" in result
        assert any("Sparse retrieval failed" in rec.message for rec in caplog.records)

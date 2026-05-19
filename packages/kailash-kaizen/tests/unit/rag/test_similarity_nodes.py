"""Tier-1 unit coverage for the 7 ``kaizen.nodes.rag.similarity`` nodes.

F8 shard B1. The value-anchor (verbatim from the workstream brief): "the RAG
capability the user chose to preserve is provably correct, not merely
importable."

The shipped default code path of every node in ``similarity.py`` is
deterministic numpy/keyword compute — there is NO LLM key and NO vector store
in the ``[rag]`` extra, and none of these 7 nodes hard-requires one. Each
``run()`` degrades to a real rule-based scoring path. These tests exercise that
real path: no mocking of the retrieval/scoring core (there is nothing to mock).

One test per documented behavior; assertions are structural (output keys,
score ranges/ordering, list lengths, typed raises).
"""

from __future__ import annotations

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

pytestmark = pytest.mark.unit


# --------------------------------------------------------------------------
# Shared corpora
# --------------------------------------------------------------------------

CORPUS = [
    {
        "content": "machine learning models train on data",
        "id": "d1",
        "metadata": {"src": "a"},
    },
    {"content": "cooking pasta requires boiling water", "id": "d2"},
    {"content": "data science applies machine learning methods", "id": "d3"},
]


# ==========================================================================
# DenseRetrievalNode
# ==========================================================================


class TestDenseRetrievalNode:
    def test_golden_path_returns_contract_keys(self):
        node = DenseRetrievalNode()
        result = node.run(query="machine learning", documents=CORPUS, k=5)
        assert set(result) >= {
            "results",
            "scores",
            "retrieval_method",
            "total_results",
        }
        assert result["retrieval_method"] == "dense"
        assert result["total_results"] == len(result["results"])

    def test_only_keyword_overlapping_docs_returned(self):
        # "cooking pasta" has zero overlap with the query — it MUST be dropped.
        node = DenseRetrievalNode()
        result = node.run(query="machine learning", documents=CORPUS, k=5)
        ids = {r["id"] for r in result["results"]}
        assert ids == {"d1", "d3"}
        assert "d2" not in ids

    def test_scores_normalized_and_descending(self):
        node = DenseRetrievalNode()
        result = node.run(query="machine learning data", documents=CORPUS, k=5)
        scores = result["scores"]
        assert all(0.0 <= s <= 1.0 for s in scores)
        assert scores == sorted(scores, reverse=True)

    def test_result_carries_metadata_and_similarity_type(self):
        node = DenseRetrievalNode()
        result = node.run(query="machine learning", documents=CORPUS, k=5)
        top = result["results"][0]
        assert top["similarity_type"] == "dense"
        assert "metadata" in top and "id" in top and "content" in top

    def test_empty_documents_returns_empty_result(self):
        node = DenseRetrievalNode()
        result = node.run(query="anything", documents=[], k=5)
        assert result["results"] == []
        assert result["scores"] == []
        assert result["total_results"] == 0

    def test_empty_query_returns_empty_result(self):
        node = DenseRetrievalNode()
        result = node.run(query="", documents=CORPUS, k=5)
        assert result["results"] == []
        assert result["total_results"] == 0

    def test_malformed_doc_missing_content_skipped_cleanly(self):
        node = DenseRetrievalNode()
        result = node.run(query="machine learning", documents=[{"id": "x"}], k=5)
        assert "error" not in result
        assert result["results"] == []

    def test_none_content_does_not_crash(self):
        # Regression: `doc.get("content", "")` returns None when the key is
        # present with a None value; `.lower()` then raised AttributeError,
        # swallowed into an `error` key. See test_issue_f8b1_*.
        node = DenseRetrievalNode()
        result = node.run(
            query="machine learning",
            documents=[{"content": None, "id": "n"}, CORPUS[0]],
            k=5,
        )
        assert "error" not in result
        assert {r["id"] for r in result["results"]} == {"d1"}

    def test_k_larger_than_corpus_returns_all_matches(self):
        node = DenseRetrievalNode()
        result = node.run(query="machine learning data", documents=CORPUS, k=99)
        assert result["total_results"] == 2  # d1 + d3 overlap; d2 does not

    def test_k_truncates_to_top_k(self):
        node = DenseRetrievalNode()
        result = node.run(query="machine learning data", documents=CORPUS, k=1)
        assert result["total_results"] == 1

    def test_unicode_query_and_documents(self):
        node = DenseRetrievalNode()
        docs = [{"content": "le café résumé naïve", "id": "u1"}]
        result = node.run(query="café résumé", documents=docs, k=5)
        assert result["total_results"] == 1
        assert result["scores"][0] > 0.0


# ==========================================================================
# SparseRetrievalNode (BM25)
# ==========================================================================


class TestSparseRetrievalNode:
    def test_golden_path_bm25_scoring(self):
        node = SparseRetrievalNode()
        result = node.run(query="machine learning", documents=CORPUS, k=5)
        assert result["retrieval_method"] == "sparse"
        assert result["total_results"] == len(result["results"])
        # BM25 scores are non-negative; descending sorted.
        assert all(s >= 0.0 for s in result["scores"])
        assert result["scores"] == sorted(result["scores"], reverse=True)

    def test_bm25_constants_present(self):
        # k1 / b are public instance attributes set after super().__init__()
        # (not part of the validated config bag). Read via vars() because the
        # @register_node() decorator erases the concrete subclass type from
        # the static analyzer's view, so direct attribute access on the
        # constructor result resolves to base Node.
        attrs = vars(SparseRetrievalNode())
        assert attrs["k1"] == 1.2
        assert attrs["b"] == 0.75

    def test_only_term_matching_docs_returned(self):
        node = SparseRetrievalNode()
        result = node.run(query="machine learning", documents=CORPUS, k=5)
        ids = {r["id"] for r in result["results"]}
        assert ids == {"d1", "d3"}

    def test_similarity_type_is_sparse(self):
        node = SparseRetrievalNode()
        result = node.run(query="machine learning", documents=CORPUS, k=5)
        assert all(r["similarity_type"] == "sparse" for r in result["results"])

    def test_empty_inputs_return_empty(self):
        node = SparseRetrievalNode()
        assert node.run(query="", documents=CORPUS, k=5)["results"] == []
        assert node.run(query="x", documents=[], k=5)["results"] == []

    def test_single_doc_avg_length_no_division_error(self):
        node = SparseRetrievalNode()
        result = node.run(
            query="alpha", documents=[{"content": "alpha alpha", "id": "s"}], k=5
        )
        assert "error" not in result
        assert result["total_results"] == 1

    def test_none_content_does_not_crash(self):
        node = SparseRetrievalNode()
        result = node.run(
            query="machine learning",
            documents=[{"content": None, "id": "n"}, CORPUS[0]],
            k=5,
        )
        assert "error" not in result
        assert {r["id"] for r in result["results"]} == {"d1"}

    def test_k_truncates(self):
        node = SparseRetrievalNode()
        result = node.run(query="machine learning data", documents=CORPUS, k=1)
        assert result["total_results"] == 1


# ==========================================================================
# ColBERTRetrievalNode (late interaction)
# ==========================================================================


class TestColBERTRetrievalNode:
    def test_golden_path_late_interaction(self):
        node = ColBERTRetrievalNode()
        result = node.run(query="machine learning", documents=CORPUS, k=5)
        assert result["retrieval_method"] == "colbert"
        assert all(
            r["similarity_type"] == "late_interaction" for r in result["results"]
        )

    def test_scores_in_unit_range(self):
        # MaxSim score is averaged over query tokens -> [0, 1].
        node = ColBERTRetrievalNode()
        result = node.run(query="machine learning", documents=CORPUS, k=5)
        assert all(0.0 <= s <= 1.0 for s in result["scores"])
        assert result["scores"] == sorted(result["scores"], reverse=True)

    def test_substring_token_match_partial_score(self):
        # ColBERT's fallback gives 0.5 for substring token matches.
        node = ColBERTRetrievalNode()
        docs = [{"content": "learnings about machinery", "id": "c1"}]
        result = node.run(query="learn machine", documents=docs, k=5)
        assert result["total_results"] == 1
        assert 0.0 < result["scores"][0] <= 1.0

    def test_empty_inputs(self):
        node = ColBERTRetrievalNode()
        assert node.run(query="", documents=CORPUS, k=5)["results"] == []
        assert node.run(query="x", documents=[], k=5)["results"] == []

    def test_whitespace_only_query_returns_empty(self):
        node = ColBERTRetrievalNode()
        result = node.run(query="   ", documents=CORPUS, k=5)
        assert result["results"] == []

    def test_none_content_does_not_crash(self):
        node = ColBERTRetrievalNode()
        result = node.run(
            query="machine learning",
            documents=[{"content": None, "id": "n"}, CORPUS[0]],
            k=5,
        )
        assert "error" not in result
        assert {r["id"] for r in result["results"]} == {"d1"}


# ==========================================================================
# MultiVectorRetrievalNode
# ==========================================================================


class TestMultiVectorRetrievalNode:
    def test_golden_path_weighted_fusion(self):
        node = MultiVectorRetrievalNode()
        result = node.run(query="machine learning", documents=CORPUS, k=5)
        assert result["retrieval_method"] == "multi_vector"
        assert all(r["similarity_type"] == "multi_vector" for r in result["results"])

    def test_combined_score_is_non_negative_and_descending(self):
        node = MultiVectorRetrievalNode()
        result = node.run(query="machine learning data", documents=CORPUS, k=5)
        assert all(s >= 0.0 for s in result["scores"])
        assert result["scores"] == sorted(result["scores"], reverse=True)

    def test_non_overlapping_doc_dropped(self):
        node = MultiVectorRetrievalNode()
        result = node.run(query="machine learning", documents=CORPUS, k=5)
        assert {r["id"] for r in result["results"]} == {"d1", "d3"}

    def test_empty_inputs(self):
        node = MultiVectorRetrievalNode()
        assert node.run(query="", documents=CORPUS, k=5)["results"] == []
        assert node.run(query="x", documents=[], k=5)["results"] == []

    def test_none_content_does_not_crash(self):
        node = MultiVectorRetrievalNode()
        result = node.run(
            query="machine learning",
            documents=[{"content": None, "id": "n"}, CORPUS[0]],
            k=5,
        )
        assert "error" not in result
        assert {r["id"] for r in result["results"]} == {"d1"}

    def test_long_document_summary_window(self):
        # The node uses the first 200 chars as a "summary" representation.
        node = MultiVectorRetrievalNode()
        long_doc = {"content": "machine " + "x " * 300, "id": "long"}
        result = node.run(query="machine", documents=[long_doc], k=5)
        assert result["total_results"] == 1


# ==========================================================================
# CrossEncoderRerankNode
# ==========================================================================


class TestCrossEncoderRerankNode:
    def test_golden_path_rerank(self):
        node = CrossEncoderRerankNode()
        initial = {"results": CORPUS, "scores": [0.9, 0.1, 0.5]}
        result = node.run(query="machine learning", initial_results=initial, k=5)
        assert result["retrieval_method"] == "cross_encoder_rerank"
        assert result["total_results"] == len(result["results"])
        assert "reranked_count" in result

    def test_rerank_score_blends_initial_coverage_precision(self):
        # rerank_score = 0.4*initial + 0.3*coverage + 0.3*precision -> [0, 1].
        node = CrossEncoderRerankNode()
        initial = {"results": CORPUS, "scores": [0.9, 0.1, 0.5]}
        result = node.run(query="machine learning", initial_results=initial, k=5)
        assert all(0.0 <= s <= 1.0 for s in result["scores"])
        assert result["scores"] == sorted(result["scores"], reverse=True)

    def test_empty_initial_results_returns_empty(self):
        node = CrossEncoderRerankNode()
        result = node.run(query="x", initial_results={}, k=5)
        assert result["results"] == []
        assert result["scores"] == []

    def test_empty_query_returns_empty(self):
        node = CrossEncoderRerankNode()
        initial = {"results": CORPUS, "scores": [0.9, 0.1, 0.5]}
        result = node.run(query="", initial_results=initial, k=5)
        assert result["results"] == []

    def test_missing_initial_scores_defaults_to_zero(self):
        # initial_results with no "scores" -> initial_score component is 0.
        node = CrossEncoderRerankNode()
        initial = {"results": CORPUS}
        result = node.run(query="machine learning", initial_results=initial, k=5)
        assert "error" not in result
        assert result["total_results"] == 3

    def test_k_truncates_reranked_output(self):
        node = CrossEncoderRerankNode()
        initial = {"results": CORPUS, "scores": [0.9, 0.1, 0.5]}
        result = node.run(query="machine learning data", initial_results=initial, k=1)
        assert result["total_results"] == 1
        assert result["reranked_count"] == 3  # all 3 reranked, top-1 returned

    def test_none_content_does_not_crash(self):
        node = CrossEncoderRerankNode()
        initial = {"results": [{"content": None, "id": "n"}], "scores": [0.5]}
        result = node.run(query="machine learning", initial_results=initial, k=5)
        assert "error" not in result


# ==========================================================================
# HybridFusionNode
# ==========================================================================


def _result_set(docs, scores):
    return {"results": docs, "scores": scores}


class TestHybridFusionNode:
    def test_default_fusion_method_is_rrf(self):
        # fusion_method / weights are passed to super().__init__() and so live
        # in the validated config bag — the real public contract. Asserting
        # via node.config[...] both verifies the contract and avoids the
        # static-analyzer subclass erasure from the @register_node() decorator.
        node = HybridFusionNode()
        assert node.config["fusion_method"] == "rrf"

    def test_default_weights(self):
        node = HybridFusionNode()
        assert node.config["weights"] == {"dense": 0.7, "sparse": 0.3}

    def test_custom_weights_preserved(self):
        node = HybridFusionNode(weights={"a": 0.4, "b": 0.6})
        assert node.config["weights"] == {"a": 0.4, "b": 0.6}

    def test_rrf_golden_path(self):
        node = HybridFusionNode()
        rsets = [
            _result_set(CORPUS[:2], [0.9, 0.3]),
            _result_set(CORPUS[1:], [0.7, 0.4]),
        ]
        result = node.run(retrieval_results=rsets, k=5)
        assert result["fusion_method"] == "rrf"
        assert result["input_count"] == 2
        assert result["total_results"] == len(result["results"])
        # RRF scores are positive and descending.
        assert all(s > 0.0 for s in result["scores"])
        assert result["scores"] == sorted(result["scores"], reverse=True)

    def test_rrf_boosts_doc_in_multiple_lists(self):
        # d2 appears in both result sets -> RRF accumulates its rank score.
        node = HybridFusionNode()
        rsets = [
            _result_set(CORPUS[:2], [0.9, 0.3]),
            _result_set(CORPUS[1:], [0.7, 0.4]),
        ]
        result = node.run(retrieval_results=rsets, k=5)
        assert result["results"][0]["id"] == "d2"

    def test_weighted_fusion_path(self):
        node = HybridFusionNode()
        rsets = [
            _result_set(CORPUS[:2], [0.9, 0.3]),
            _result_set(CORPUS[1:], [0.7, 0.4]),
        ]
        result = node.run(retrieval_results=rsets, fusion_method="weighted", k=5)
        assert result["fusion_method"] == "weighted"
        assert result["scores"] == sorted(result["scores"], reverse=True)

    def test_empty_retrieval_results(self):
        node = HybridFusionNode()
        result = node.run(retrieval_results=[], k=5)
        assert result["results"] == []
        assert result["scores"] == []

    def test_k_truncates_fused_output(self):
        node = HybridFusionNode()
        rsets = [_result_set(CORPUS, [0.9, 0.5, 0.3])]
        result = node.run(retrieval_results=rsets, k=2)
        assert result["total_results"] == 2

    def test_run_time_fusion_method_overrides_constructor(self):
        node = HybridFusionNode(fusion_method="rrf")
        rsets = [_result_set(CORPUS, [0.9, 0.5, 0.3])]
        result = node.run(retrieval_results=rsets, fusion_method="weighted", k=5)
        assert result["fusion_method"] == "weighted"


# ==========================================================================
# PropositionBasedRetrievalNode
# ==========================================================================


class TestPropositionBasedRetrievalNode:
    SENTENCED = [
        {
            "content": "Machine learning is a field of study. "
            "It uses statistical methods to learn patterns.",
            "id": "p1",
        },
        {
            "content": "Cooking pasta needs boiling water. Salt improves flavor.",
            "id": "p2",
        },
    ]

    def test_golden_path_proposition_retrieval(self):
        node = PropositionBasedRetrievalNode()
        result = node.run(query="machine learning", documents=self.SENTENCED, k=5)
        assert result["retrieval_method"] == "proposition"
        assert "matched_propositions" in result
        assert all(r["similarity_type"] == "proposition" for r in result["results"])

    def test_matched_propositions_aligned_with_results(self):
        node = PropositionBasedRetrievalNode()
        result = node.run(query="machine learning", documents=self.SENTENCED, k=5)
        assert len(result["matched_propositions"]) == len(result["results"])

    def test_best_proposition_is_the_overlapping_sentence(self):
        node = PropositionBasedRetrievalNode()
        result = node.run(query="machine learning", documents=self.SENTENCED, k=5)
        assert result["total_results"] == 1  # only p1 overlaps
        assert "machine learning" in result["matched_propositions"][0].lower()

    def test_scores_normalized_and_descending(self):
        node = PropositionBasedRetrievalNode()
        result = node.run(
            query="machine learning statistical", documents=self.SENTENCED, k=5
        )
        assert all(0.0 <= s <= 1.0 for s in result["scores"])
        assert result["scores"] == sorted(result["scores"], reverse=True)

    def test_empty_inputs(self):
        node = PropositionBasedRetrievalNode()
        assert node.run(query="", documents=self.SENTENCED, k=5)["results"] == []
        assert node.run(query="x", documents=[], k=5)["results"] == []

    def test_short_sentences_below_threshold_ignored(self):
        # Propositions require a stripped length > 20 chars.
        node = PropositionBasedRetrievalNode()
        docs = [{"content": "ML good. AI fun.", "id": "short"}]
        result = node.run(query="ML AI", documents=docs, k=5)
        assert result["results"] == []

    def test_none_content_does_not_crash(self):
        node = PropositionBasedRetrievalNode()
        result = node.run(
            query="machine learning",
            documents=[{"content": None, "id": "n"}, self.SENTENCED[0]],
            k=5,
        )
        assert "error" not in result
        assert {r["id"] for r in result["results"]} == {"p1"}

    def test_unicode_propositions(self):
        node = PropositionBasedRetrievalNode()
        docs = [
            {
                "content": "Le café au lait est délicieux le matin. "
                "Un résumé concis aide la lecture.",
                "id": "u1",
            }
        ]
        result = node.run(query="café résumé", documents=docs, k=5)
        assert result["total_results"] == 1
        assert result["scores"][0] > 0.0

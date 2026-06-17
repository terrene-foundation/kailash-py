"""Tests for data retrieval nodes."""

import pytest

from kailash.nodes.data.retrieval import HybridRetrieverNode, RelevanceScorerNode


class TestRelevanceScorerNode:
    """Test the RelevanceScorerNode."""

    def test_bm25_scoring_ranks_matching_chunk_first(self):
        """BM25 lexical scoring ranks the query-matching chunk first."""
        chunks = [
            {
                "content": "Quantum mechanics describes entanglement of particles",
                "chunk_id": "physics",
            },
            {
                "content": "A recipe for chocolate cake with butter and sugar",
                "chunk_id": "baking",
            },
            {
                "content": "Distributed databases use sharding and replication for scaling",
                "chunk_id": "databases",
            },
        ]
        query = "database sharding replication scaling"

        node = RelevanceScorerNode(similarity_method="bm25", top_k=3)
        result = node.execute(chunks=chunks, query=query)

        ranked = result["relevant_chunks"]
        # The database chunk strongly matches the query and MUST rank first.
        assert ranked[0]["chunk_id"] == "databases"
        # Scores must be REAL — not the old constant 0.5, and must differ
        # across chunks (proving per-chunk lexical computation).
        scores = [c["relevance_score"] for c in ranked]
        assert ranked[0]["relevance_score"] > 0.0
        assert all(s != 0.5 for s in scores)
        assert len(set(scores)) > 1
        # Non-matching chunks have no query-term overlap -> zero score.
        non_matching = {
            c["chunk_id"]: c["relevance_score"]
            for c in ranked
            if c["chunk_id"] in ("physics", "baking")
        }
        assert all(score == 0.0 for score in non_matching.values())

    def test_tfidf_scoring_ranks_matching_chunk_first(self):
        """TF-IDF cosine scoring ranks the query-matching chunk first."""
        chunks = [
            {
                "content": "Quantum mechanics describes entanglement of particles",
                "chunk_id": "physics",
            },
            {
                "content": "A recipe for chocolate cake with butter and sugar",
                "chunk_id": "baking",
            },
            {
                "content": "Distributed databases use sharding and replication for scaling",
                "chunk_id": "databases",
            },
        ]
        query = "database sharding replication scaling"

        node = RelevanceScorerNode(similarity_method="tfidf", top_k=3)
        result = node.execute(chunks=chunks, query=query)

        ranked = result["relevant_chunks"]
        assert ranked[0]["chunk_id"] == "databases"
        scores = [c["relevance_score"] for c in ranked]
        assert ranked[0]["relevance_score"] > 0.0
        # TF-IDF cosine similarity is bounded in [0, 1].
        assert all(0.0 <= s <= 1.0 for s in scores)
        assert all(s != 0.5 for s in scores)
        assert len(set(scores)) > 1

    def test_bm25_requires_query_text(self):
        """BM25 must fail loud (ValueError) when no query text is available."""
        chunks = [{"content": "some content", "chunk_id": "c1"}]
        node = RelevanceScorerNode(similarity_method="bm25")
        # run() surfaces the raw ValueError (execute() wraps it).
        with pytest.raises(
            ValueError, match="bm25/tfidf scoring requires a 'query' text input"
        ):
            node.run(chunks=chunks, similarity_method="bm25")

    def test_tfidf_requires_query_text(self):
        """TF-IDF must fail loud (ValueError) when no query text is available."""
        chunks = [{"content": "some content", "chunk_id": "c1"}]
        node = RelevanceScorerNode(similarity_method="tfidf")
        with pytest.raises(
            ValueError, match="bm25/tfidf scoring requires a 'query' text input"
        ):
            node.run(chunks=chunks, similarity_method="tfidf")

    def test_fallback_uses_real_query_text(self):
        """No-embeddings fallback keyword-matches against the REAL query text."""
        chunks = [
            {"content": "Machine learning algorithms", "chunk_id": "chunk_1"},
            {"content": "Dog training techniques", "chunk_id": "chunk_2"},
            {"content": "Learning from data", "chunk_id": "chunk_3"},
        ]

        node = RelevanceScorerNode(top_k=3)
        # No embeddings, but a real query naming "machine learning" terms.
        result = node.execute(chunks=chunks, query="machine learning")

        scored = {
            c["chunk_id"]: c["relevance_score"] for c in result["relevant_chunks"]
        }
        # chunk_1 has both query terms -> full overlap (1.0).
        assert scored["chunk_1"] == pytest.approx(1.0)
        # chunk_2 (dog) shares no query term -> 0.0.
        assert scored.get("chunk_2", 0.0) == pytest.approx(0.0)
        # chunk_3 has only "learning" -> partial overlap (0.5).
        assert scored["chunk_3"] == pytest.approx(0.5)

    def test_fallback_no_signal_returns_zero(self):
        """With neither embeddings nor query text, scores are an honest 0.0."""
        chunks = [
            {"content": "Machine learning algorithms", "chunk_id": "chunk_1"},
            {"content": "Dog training techniques", "chunk_id": "chunk_2"},
        ]

        node = RelevanceScorerNode(top_k=2)
        result = node.execute(chunks=chunks)  # no embeddings, no query text

        # No scoring signal -> 0.0 for every chunk (never a fabricated query).
        for chunk in result["relevant_chunks"]:
            assert chunk["relevance_score"] == 0.0

    def test_cosine_similarity_scoring(self):
        """Test cosine similarity scoring with embeddings."""
        chunks = [
            {"content": "Machine learning is powerful", "chunk_id": "chunk_1"},
            {"content": "Dogs are loyal pets", "chunk_id": "chunk_2"},
            {"content": "AI algorithms process data", "chunk_id": "chunk_3"},
        ]

        # Mock embeddings - similar for ML/AI content, different for dogs
        query_embedding = [{"embedding": [0.8, 0.2, 0.1]}]
        chunk_embeddings = [
            {"embedding": [0.7, 0.3, 0.2]},  # Similar to query (ML)
            {"embedding": [0.1, 0.8, 0.9]},  # Different from query (dogs)
            {"embedding": [0.75, 0.25, 0.15]},  # Very similar to query (AI)
        ]

        node = RelevanceScorerNode(similarity_method="cosine", top_k=2)
        result = node.execute(
            chunks=chunks,
            query_embedding=query_embedding,
            chunk_embeddings=chunk_embeddings,
        )

        assert "relevant_chunks" in result
        assert len(result["relevant_chunks"]) == 2

        # Check that chunks are sorted by relevance
        scores = [chunk["relevance_score"] for chunk in result["relevant_chunks"]]
        assert scores[0] >= scores[1]  # First should have higher score

        # AI chunk should be most relevant
        assert result["relevant_chunks"][0]["chunk_id"] == "chunk_3"

    def test_fallback_text_matching(self):
        """Test fallback to text matching when no embeddings provided."""
        chunks = [
            {"content": "Machine learning algorithms", "chunk_id": "chunk_1"},
            {"content": "Dog training techniques", "chunk_id": "chunk_2"},
            {"content": "Learning from data", "chunk_id": "chunk_3"},
        ]

        node = RelevanceScorerNode(top_k=2)
        result = node.execute(chunks=chunks)  # No embeddings provided

        assert "relevant_chunks" in result
        assert len(result["relevant_chunks"]) <= 2

        # Should contain relevance scores
        for chunk in result["relevant_chunks"]:
            assert "relevance_score" in chunk

    def test_empty_inputs(self):
        """Test handling of empty inputs."""
        node = RelevanceScorerNode(top_k=3)
        result = node.execute(chunks=[])

        assert "relevant_chunks" in result
        assert result["relevant_chunks"] == []


class TestHybridRetrieverNode:
    """Test the HybridRetrieverNode."""

    def test_rrf_fusion_strategy(self):
        """Test Reciprocal Rank Fusion strategy."""
        # Sample retrieval results
        dense_results = [
            {
                "id": "doc1",
                "content": "AI and machine learning",
                "similarity_score": 0.9,
            },
            {
                "id": "doc2",
                "content": "Natural language processing",
                "similarity_score": 0.8,
            },
            {
                "id": "doc3",
                "content": "Computer vision systems",
                "similarity_score": 0.7,
            },
        ]

        sparse_results = [
            {
                "id": "doc2",
                "content": "Natural language processing",
                "similarity_score": 0.85,
            },
            {"id": "doc4", "content": "Data science methods", "similarity_score": 0.75},
            {
                "id": "doc1",
                "content": "AI and machine learning",
                "similarity_score": 0.65,
            },
        ]

        node = HybridRetrieverNode(fusion_strategy="rrf", top_k=3, rrf_k=60)
        result = node.execute(
            query="machine learning applications",
            dense_results=dense_results,
            sparse_results=sparse_results,
        )

        assert "hybrid_results" in result
        assert "fusion_method" in result
        assert result["fusion_method"] == "rrf"
        assert "dense_count" in result
        assert "sparse_count" in result
        assert "fused_count" in result

        # Should have fused results
        assert len(result["hybrid_results"]) <= 3

        # Check that results have hybrid scores and ranks
        for i, doc in enumerate(result["hybrid_results"]):
            assert "hybrid_score" in doc
            assert "fusion_method" in doc
            assert "rank" in doc
            assert doc["rank"] == i + 1

    def test_linear_fusion_strategy(self):
        """Test linear combination fusion strategy."""
        dense_results = [
            {"id": "doc1", "content": "Machine learning", "similarity_score": 0.9},
            {"id": "doc2", "content": "Deep learning", "similarity_score": 0.8},
        ]

        sparse_results = [
            {"id": "doc1", "content": "Machine learning", "similarity_score": 0.7},
            {"id": "doc3", "content": "AI systems", "similarity_score": 0.6},
        ]

        node = HybridRetrieverNode(
            fusion_strategy="linear", dense_weight=0.7, sparse_weight=0.3, top_k=2
        )
        result = node.execute(
            query="ML techniques",
            dense_results=dense_results,
            sparse_results=sparse_results,
        )

        assert result["fusion_method"] == "linear"
        assert len(result["hybrid_results"]) <= 2

        # doc1 should score highest (appears in both with good scores)
        assert result["hybrid_results"][0]["id"] == "doc1"

    def test_weighted_fusion_strategy(self):
        """Test weighted fusion with rank-based scoring."""
        dense_results = [
            {"id": "doc1", "content": "First result", "similarity_score": 0.9},
            {"id": "doc2", "content": "Second result", "similarity_score": 0.8},
        ]

        sparse_results = [
            {"id": "doc3", "content": "Third result", "similarity_score": 0.85},
            {"id": "doc1", "content": "First result", "similarity_score": 0.75},
        ]

        node = HybridRetrieverNode(
            fusion_strategy="weighted", dense_weight=0.6, sparse_weight=0.4, top_k=3
        )
        result = node.execute(
            query="test query",
            dense_results=dense_results,
            sparse_results=sparse_results,
        )

        assert result["fusion_method"] == "weighted"
        assert len(result["hybrid_results"]) <= 3

    def test_empty_results_handling(self):
        """Test handling of empty result sets."""
        node = HybridRetrieverNode(fusion_strategy="rrf", top_k=5)

        # Test completely empty results
        result = node.execute(query="test", dense_results=[], sparse_results=[])
        print(f"Empty results: {result}")
        assert result["hybrid_results"] == []
        assert result["dense_count"] == 0
        assert result["sparse_count"] == 0

        # Test one empty set
        dense_results = [{"id": "doc1", "content": "test", "similarity_score": 0.8}]
        result = node.execute(
            query="test", dense_results=dense_results, sparse_results=[]
        )
        assert len(result["hybrid_results"]) == 1
        assert result["dense_count"] == 1
        assert result["sparse_count"] == 0

    def test_result_normalization(self):
        """Test normalization of input results with different field names."""
        # Results with different field names
        dense_results = [
            {
                "chunk_id": "chunk1",
                "text": "content1",
                "score": 0.9,
            },  # Different field names
        ]
        sparse_results = [
            {
                "id": "doc2",
                "content": "content2",
                "similarity_score": 0.8,
            },  # Standard names
        ]

        node = HybridRetrieverNode(fusion_strategy="rrf", top_k=2)
        result = node.execute(
            query="test", dense_results=dense_results, sparse_results=sparse_results
        )

        # Should handle different field names gracefully
        assert len(result["hybrid_results"]) == 2

        # Check that normalization worked
        for doc in result["hybrid_results"]:
            assert "id" in doc
            assert "content" in doc
            assert "similarity_score" in doc

    def test_parameter_validation(self):
        """Test parameter variations and edge cases."""
        dense_results = [{"id": "doc1", "content": "test", "similarity_score": 0.8}]
        sparse_results = [{"id": "doc2", "content": "test2", "similarity_score": 0.7}]

        # Test different parameter combinations
        node = HybridRetrieverNode(
            fusion_strategy="rrf",
            top_k=1,
            rrf_k=30,  # Different k value
            normalize_scores=False,
        )
        result = node.execute(
            query="test",
            dense_results=dense_results,
            sparse_results=sparse_results,
            fusion_strategy="linear",  # Override in run
            top_k=2,  # Override in run
        )

        # Should use runtime parameters
        assert result["fusion_method"] == "linear"
        assert len(result["hybrid_results"]) <= 2

    def test_unsupported_fusion_strategy(self):
        """Test fallback to RRF for unsupported strategies."""
        dense_results = [{"id": "doc1", "content": "test", "similarity_score": 0.8}]
        sparse_results = [{"id": "doc2", "content": "test2", "similarity_score": 0.7}]

        node = HybridRetrieverNode(fusion_strategy="invalid_strategy", top_k=2)
        result = node.execute(
            query="test", dense_results=dense_results, sparse_results=sparse_results
        )

        # Should fallback to RRF
        assert (
            result["fusion_method"] == "invalid_strategy"
        )  # Reports what was requested
        assert len(result["hybrid_results"]) <= 2


@pytest.mark.regression
class TestRelevanceScorerLexicalRegression:
    """Regression guards: BM25/TF-IDF must return REAL lexical scores.

    Guards against the prior defect where ``_bm25_scoring`` and
    ``_tfidf_scoring`` returned a constant ``relevance_score: 0.5`` for every
    chunk, and the no-embeddings fallback used a hardcoded query string.
    """

    # Distinct content per chunk; the query terms strongly match exactly one.
    _CHUNKS = [
        {
            "content": "Photosynthesis converts sunlight into chemical energy in plants",
            "chunk_id": "biology",
        },
        {
            "content": "The stock market closed higher on strong earnings reports",
            "chunk_id": "finance",
        },
        {
            "content": "Reinforcement learning trains agents via reward signals and policy gradients",
            "chunk_id": "ml",
        },
    ]
    _QUERY = "reinforcement learning agents reward policy"

    @pytest.mark.parametrize("method", ["bm25", "tfidf"])
    def test_lexical_scoring_is_real_not_constant(self, method):
        """The matching chunk ranks first with non-constant, differing scores."""
        node = RelevanceScorerNode(similarity_method=method, top_k=3)
        result = node.execute(chunks=self._CHUNKS, query=self._QUERY)

        ranked = result["relevant_chunks"]
        # The ML chunk is the only one whose terms match the query.
        assert ranked[0]["chunk_id"] == "ml"

        scores = [c["relevance_score"] for c in ranked]
        # The matching chunk has a positive real score.
        assert ranked[0]["relevance_score"] > 0.0
        # Proves real computation, not the old constant-0.5 stub:
        assert all(s != 0.5 for s in scores), f"{method} returned a 0.5 score: {scores}"
        # Scores differ across chunks (the stub made them all identical).
        assert len(set(scores)) > 1, f"{method} scores are all equal: {scores}"

    @pytest.mark.parametrize("method", ["bm25", "tfidf"])
    def test_lexical_scoring_never_uniform_half(self, method):
        """Guard: bm25/tfidf must never return a uniform 0.5 for all chunks."""
        node = RelevanceScorerNode(similarity_method=method, top_k=3)
        result = node.execute(chunks=self._CHUNKS, query=self._QUERY)

        scores = [c["relevance_score"] for c in result["relevant_chunks"]]
        uniform_half = len(scores) > 0 and all(s == 0.5 for s in scores)
        assert (
            not uniform_half
        ), f"{method} regressed to the constant-0.5 stub: {scores}"

    @pytest.mark.parametrize("method", ["bm25", "tfidf"])
    def test_lexical_scoring_requires_query(self, method):
        """bm25/tfidf must raise a clear ValueError with no query text."""
        node = RelevanceScorerNode(similarity_method=method)
        with pytest.raises(
            ValueError, match="bm25/tfidf scoring requires a 'query' text input"
        ):
            node.run(chunks=self._CHUNKS, similarity_method=method)

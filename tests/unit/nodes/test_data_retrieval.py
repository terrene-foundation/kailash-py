"""Tests for data retrieval nodes."""

import pytest
from kailash.nodes.data.retrieval import HybridRetrieverNode, RelevanceScorerNode


class TestRelevanceScorerNode:
    """Test the RelevanceScorerNode."""

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

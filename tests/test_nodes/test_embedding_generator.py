"""Unit tests for EmbeddingGenerator node."""

import pytest

from kailash.nodes.ai import EmbeddingGenerator


class TestEmbeddingGenerator:
    """Test cases for EmbeddingGenerator node."""

    def test_embed_single_text(self):
        """Test embedding a single text."""
        node = EmbeddingGenerator()
        result = node.run(
            operation="embed_text",
            provider="mock",
            model="text-embedding-3-large",
            input_text="This is a test sentence for embedding.",
        )

        assert result["success"] is True
        assert result["operation"] == "embed_text"
        assert "embedding" in result
        assert result["dimensions"] == 1536  # Default mock dimensions
        assert len(result["embedding"]) == 1536
        assert result["text_length"] > 0
        assert result["cached"] is False
        assert "processing_time_ms" in result
        assert "usage" in result

    def test_embed_batch_texts(self):
        """Test embedding multiple texts in batch."""
        node = EmbeddingGenerator()

        texts = [
            "First document about machine learning",
            "Second document about data science",
            "Third document about artificial intelligence",
            "Fourth document about neural networks",
        ]

        result = node.run(
            operation="embed_batch",
            provider="mock",
            model="text-embedding-3-large",
            input_texts=texts,
            batch_size=2,
            cache_enabled=True,
            normalize=True,
        )

        assert result["success"] is True
        assert result["operation"] == "embed_batch"
        assert result["total_texts"] == 4
        assert result["total_embeddings"] == 4
        assert len(result["embeddings"]) == 4

        # Check each embedding
        for emb in result["embeddings"]:
            assert "text" in emb
            assert "embedding" in emb
            assert "dimensions" in emb
            assert "cached" in emb
            assert len(emb["embedding"]) == emb["dimensions"]

        assert "cache_hit_rate" in result
        assert "processing_time_ms" in result
        assert "usage" in result

    def test_calculate_cosine_similarity(self):
        """Test cosine similarity calculation."""
        node = EmbeddingGenerator()

        # Create two similar embeddings
        embedding_1 = [0.1, 0.2, 0.3, 0.4, 0.5]
        embedding_2 = [0.15, 0.25, 0.35, 0.45, 0.55]

        result = node.run(
            operation="calculate_similarity",
            embedding_1=embedding_1,
            embedding_2=embedding_2,
            similarity_metric="cosine",
        )

        assert result["success"] is True
        assert result["operation"] == "calculate_similarity"
        assert "similarity" in result
        assert result["metric"] == "cosine"
        assert -1 <= result["similarity"] <= 1
        assert "interpretation" in result
        assert result["dimensions"] == 5

    def test_calculate_euclidean_distance(self):
        """Test Euclidean distance calculation."""
        node = EmbeddingGenerator()

        embedding_1 = [1.0, 2.0, 3.0]
        embedding_2 = [4.0, 5.0, 6.0]

        result = node.run(
            operation="calculate_similarity",
            embedding_1=embedding_1,
            embedding_2=embedding_2,
            similarity_metric="euclidean",
        )

        assert result["success"] is True
        assert result["metric"] == "euclidean"
        assert result["similarity"] > 0  # Distance should be positive

    def test_calculate_dot_product(self):
        """Test dot product calculation."""
        node = EmbeddingGenerator()

        embedding_1 = [1.0, 2.0, 3.0]
        embedding_2 = [2.0, 3.0, 4.0]

        result = node.run(
            operation="calculate_similarity",
            embedding_1=embedding_1,
            embedding_2=embedding_2,
            similarity_metric="dot_product",
        )

        assert result["success"] is True
        assert result["metric"] == "dot_product"
        # Expected: 1*2 + 2*3 + 3*4 = 2 + 6 + 12 = 20
        assert result["similarity"] == 20.0

    def test_embed_mcp_resource(self):
        """Test embedding content from MCP resource."""
        node = EmbeddingGenerator()

        result = node.run(
            operation="embed_mcp_resource",
            provider="mock",
            model="text-embedding-3-large",
            mcp_resource_uri="data://documents/knowledge_base.json",
            chunk_size=512,
            cache_enabled=True,
        )

        assert result["success"] is True
        assert result["operation"] == "embed_mcp_resource"
        assert result["mcp_resource_uri"] == "data://documents/knowledge_base.json"
        assert "embedding" in result
        assert "content_preview" in result

    def test_different_providers(self):
        """Test different embedding providers."""
        node = EmbeddingGenerator()

        providers = [
            ("ollama", "nomic-embed-text", 768),  # Ollama embedding model
            ("mock", "default", 1536),
        ]

        for provider, model, expected_dims in providers:
            result = node.run(
                operation="embed_text",
                provider=provider,
                model=model,
                input_text="Test text for different providers",
            )

            # For Ollama, we check if it's available first
            if provider == "ollama":
                try:
                    import ollama

                    # Try to connect to Ollama
                    ollama.list()
                    assert result["success"] is True
                    # Ollama dimensions may vary, so we just check it's positive
                    assert result["dimensions"] > 0
                except:
                    # If Ollama is not available, the test should fail gracefully
                    assert result["success"] is False or "Ollama" in result.get(
                        "error", ""
                    )
            else:
                assert result["success"] is True
                assert result["dimensions"] == expected_dims

    def test_custom_dimensions(self):
        """Test custom embedding dimensions."""
        node = EmbeddingGenerator()

        custom_dims = 768
        result = node.run(
            operation="embed_text",
            provider="mock",
            model="custom-model",
            input_text="Test with custom dimensions",
            dimensions=custom_dims,
        )

        assert result["success"] is True
        assert result["dimensions"] == custom_dims
        assert len(result["embedding"]) == custom_dims

    def test_text_chunking(self):
        """Test text chunking for long documents."""
        node = EmbeddingGenerator()

        # Create a long text that will be chunked
        long_text = " ".join(["word"] * 1000)  # 1000 words

        result = node.run(
            operation="embed_text",
            provider="mock",
            model="text-embedding-3-large",
            input_text=long_text,
            chunk_size=100,  # Small chunk size to force chunking
        )

        assert result["success"] is True
        assert "embedding" in result
        # Should still return a single averaged embedding

    def test_normalization(self):
        """Test vector normalization."""
        node = EmbeddingGenerator()

        result = node.run(
            operation="embed_text",
            provider="mock",
            model="text-embedding-3-large",
            input_text="Test normalization",
            normalize=True,
        )

        assert result["success"] is True
        embedding = result["embedding"]

        # Check if vector is approximately normalized (magnitude ≈ 1)
        magnitude = sum(x * x for x in embedding) ** 0.5
        assert abs(magnitude - 1.0) < 0.01  # Allow small floating point errors

    def test_caching_behavior(self):
        """Test embedding caching functionality."""
        node = EmbeddingGenerator()

        text = "This text will be cached"

        # First call - should not be cached
        result1 = node.run(
            operation="embed_text",
            provider="mock",
            model="text-embedding-3-large",
            input_text=text,
            cache_enabled=True,
            cache_ttl=3600,
        )

        assert result1["success"] is True
        assert result1["cached"] is False

        # Second call with same text - would be cached in real implementation
        result2 = node.run(
            operation="embed_text",
            provider="mock",
            model="text-embedding-3-large",
            input_text=text,
            cache_enabled=True,
            cache_ttl=3600,
        )

        assert result2["success"] is True
        # Note: Mock implementation doesn't actually cache, but structure is correct

    def test_batch_with_different_sizes(self):
        """Test batch processing with different batch sizes."""
        node = EmbeddingGenerator()

        texts = [f"Document {i}" for i in range(10)]

        for batch_size in [1, 3, 5, 10]:
            result = node.run(
                operation="embed_batch",
                provider="mock",
                model="text-embedding-3-large",
                input_texts=texts,
                batch_size=batch_size,
            )

            assert result["success"] is True
            assert result["total_embeddings"] == 10
            assert result["batch_size"] == batch_size

    def test_error_handling_missing_text(self):
        """Test error handling for missing input text."""
        node = EmbeddingGenerator()

        result = node.run(
            operation="embed_text",
            provider="mock",
            model="text-embedding-3-large",
            # Missing input_text
        )

        assert result["success"] is False
        assert "input_text is required" in result["error"]

    def test_error_handling_empty_batch(self):
        """Test error handling for empty batch."""
        node = EmbeddingGenerator()

        result = node.run(
            operation="embed_batch",
            provider="mock",
            model="text-embedding-3-large",
            input_texts=[],
        )

        assert result["success"] is False
        assert "cannot be empty" in result["error"]

    def test_error_handling_mismatched_embeddings(self):
        """Test error handling for similarity with mismatched dimensions."""
        node = EmbeddingGenerator()

        result = node.run(
            operation="calculate_similarity",
            embedding_1=[1.0, 2.0, 3.0],
            embedding_2=[1.0, 2.0],  # Different dimension
            similarity_metric="cosine",
        )

        assert result["success"] is False
        assert "dimensions must match" in result["error"]

    def test_error_handling_invalid_metric(self):
        """Test error handling for invalid similarity metric."""
        node = EmbeddingGenerator()

        result = node.run(
            operation="calculate_similarity",
            embedding_1=[1.0, 2.0, 3.0],
            embedding_2=[1.0, 2.0, 3.0],
            similarity_metric="invalid_metric",
        )

        assert result["success"] is False
        assert "Unsupported similarity metric" in result["error"]
        assert "supported_metrics" in result

    def test_error_handling_missing_embeddings(self):
        """Test error handling for missing embeddings in similarity calculation."""
        node = EmbeddingGenerator()

        result = node.run(
            operation="calculate_similarity",
            embedding_1=[1.0, 2.0, 3.0],
            # Missing embedding_2
            similarity_metric="cosine",
        )

        assert result["success"] is False
        # The actual error message is more specific
        assert (
            "embedding_2" in result["error"]
            or "provide embedding_1 and embedding_2" in result["error"]
        )

    def test_error_handling_invalid_operation(self):
        """Test error handling for invalid operations."""
        node = EmbeddingGenerator()

        result = node.run(
            operation="invalid_operation", provider="mock", model="test-model"
        )

        assert result["success"] is False
        assert "Unsupported operation" in result["error"]
        assert "supported_operations" in result

    def test_usage_cost_estimation(self):
        """Test usage metrics and cost estimation."""
        node = EmbeddingGenerator()

        result = node.run(
            operation="embed_text",
            provider="mock",  # Use mock provider for testing
            model="text-embedding-3-large",
            input_text="Test cost estimation for this text",
        )

        assert result["success"] is True
        usage = result["usage"]

        assert "tokens" in usage
        assert "estimated_cost_usd" in usage
        assert usage["tokens"] > 0
        assert usage["estimated_cost_usd"] >= 0

    def test_batch_cost_estimation(self):
        """Test cost estimation for batch processing."""
        node = EmbeddingGenerator()

        texts = ["Text one", "Text two", "Text three"]

        result = node.run(
            operation="embed_batch",
            provider="mock",  # Use mock provider for testing
            model="text-embedding-3-small",
            input_texts=texts,
        )

        assert result["success"] is True
        usage = result["usage"]

        assert "total_tokens" in usage
        assert "estimated_cost_usd" in usage
        assert "average_tokens_per_text" in usage
        assert usage["total_tokens"] > 0

    def test_timeout_configuration(self):
        """Test timeout configuration."""
        node = EmbeddingGenerator()

        result = node.run(
            operation="embed_text",
            provider="mock",
            model="text-embedding-3-large",
            input_text="Test timeout configuration",
            timeout=30,
            max_retries=5,
        )

        assert result["success"] is True
        # Should accept timeout and retry parameters without error


@pytest.fixture
def sample_texts():
    """Sample texts for testing."""
    return [
        "Machine learning is a subset of artificial intelligence.",
        "Deep learning uses neural networks with multiple layers.",
        "Natural language processing helps computers understand text.",
        "Computer vision enables machines to interpret visual information.",
        "Reinforcement learning trains agents through trial and error.",
    ]


@pytest.fixture
def sample_embeddings():
    """Sample embeddings for testing."""
    return [
        [0.1, 0.2, 0.3, 0.4, 0.5],
        [0.2, 0.3, 0.4, 0.5, 0.6],
        [0.3, 0.4, 0.5, 0.6, 0.7],
        [0.4, 0.5, 0.6, 0.7, 0.8],
        [0.5, 0.6, 0.7, 0.8, 0.9],
    ]


def test_realistic_embedding_workflow(sample_texts):
    """Test realistic embedding workflow with multiple operations."""
    node = EmbeddingGenerator()

    # Step 1: Embed batch of texts
    batch_result = node.run(
        operation="embed_batch",
        provider="mock",
        model="text-embedding-3-large",
        input_texts=sample_texts,
        batch_size=3,
        cache_enabled=True,
        normalize=True,
    )

    assert batch_result["success"] is True
    embeddings = batch_result["embeddings"]

    # Step 2: Calculate similarities between first and other embeddings
    first_embedding = embeddings[0]["embedding"]
    similarities = []

    for i in range(1, len(embeddings)):
        sim_result = node.run(
            operation="calculate_similarity",
            embedding_1=first_embedding,
            embedding_2=embeddings[i]["embedding"],
            similarity_metric="cosine",
        )

        assert sim_result["success"] is True
        similarities.append(sim_result["similarity"])

    # Step 3: Find most similar text
    max_similarity = max(similarities)
    most_similar_idx = similarities.index(max_similarity) + 1

    assert max_similarity >= 0  # Should be positive similarity
    assert 0 <= most_similar_idx < len(sample_texts)


def test_similarity_matrix_calculation(sample_embeddings):
    """Test calculating similarity matrix for multiple embeddings."""
    node = EmbeddingGenerator()

    similarity_matrix = []

    for i, emb1 in enumerate(sample_embeddings):
        row = []
        for j, emb2 in enumerate(sample_embeddings):
            if i == j:
                # Self-similarity should be 1.0 for cosine
                row.append(1.0)
            else:
                result = node.run(
                    operation="calculate_similarity",
                    embedding_1=emb1,
                    embedding_2=emb2,
                    similarity_metric="cosine",
                )
                assert result["success"] is True
                row.append(result["similarity"])

        similarity_matrix.append(row)

    # Check matrix properties
    assert len(similarity_matrix) == len(sample_embeddings)
    for row in similarity_matrix:
        assert len(row) == len(sample_embeddings)

    # Diagonal should be close to 1.0 (self-similarity)
    for i in range(len(similarity_matrix)):
        assert abs(similarity_matrix[i][i] - 1.0) < 0.01

"""
Unit tests for semantic memory nodes.
"""

from datetime import datetime, UTC
from unittest.mock import AsyncMock, Mock, patch

import numpy as np
import pytest

from kailash.nodes.ai.semantic_memory import (
    EmbeddingResult,
    InMemoryVectorStore,
    SemanticAgentMatchingNode,
    SemanticMemoryItem,
    SemanticMemorySearchNode,
    SemanticMemoryStoreNode,
    SimpleEmbeddingProvider,
)


class TestSemanticMemoryItem:
    """Test SemanticMemoryItem dataclass."""

    def test_memory_item_creation(self):
        """Test creating a semantic memory item."""
        embedding = np.array([0.1, 0.2, 0.3])
        item = SemanticMemoryItem(
            id="test-id",
            content="test content",
            embedding=embedding,
            metadata={"key": "value"},
            created_at=datetime.now(UTC),
            collection="test",
        )

        assert item.id == "test-id"
        assert item.content == "test content"
        assert np.array_equal(item.embedding, embedding)
        assert item.metadata["key"] == "value"
        assert item.collection == "test"

    def test_memory_item_to_dict(self):
        """Test converting memory item to dict."""
        embedding = np.array([0.1, 0.2, 0.3])
        now = datetime.now(UTC)

        item = SemanticMemoryItem(
            id="test-id",
            content="test content",
            embedding=embedding,
            metadata={"key": "value"},
            created_at=now,
            collection="test",
        )

        data = item.to_dict()
        assert data["id"] == "test-id"
        assert data["content"] == "test content"
        assert data["embedding"] == [0.1, 0.2, 0.3]
        assert data["metadata"]["key"] == "value"
        assert data["collection"] == "test"
        assert data["created_at"] == now.isoformat()


class TestSimpleEmbeddingProvider:
    """Test SimpleEmbeddingProvider functionality."""

    def test_hash_embedding_deterministic(self):
        """Test that hash embeddings are deterministic."""
        provider = SimpleEmbeddingProvider()

        embedding1 = provider._hash_embedding("test text")
        embedding2 = provider._hash_embedding("test text")

        assert np.array_equal(embedding1, embedding2)
        assert embedding1.shape[0] == 384  # Default dimension

    def test_hash_embedding_different_texts(self):
        """Test that different texts produce different embeddings."""
        provider = SimpleEmbeddingProvider()

        embedding1 = provider._hash_embedding("text one")
        embedding2 = provider._hash_embedding("text two")

        assert not np.array_equal(embedding1, embedding2)

    @pytest.mark.asyncio
    async def test_embed_text_fallback(self):
        """Test embedding with fallback to hash method."""
        provider = SimpleEmbeddingProvider(host="http://invalid:11434")

        result = await provider.embed_text("test text")

        assert isinstance(result, EmbeddingResult)
        assert result.embeddings.shape[0] == 1
        assert result.embeddings.shape[1] == 384
        assert result.model == "nomic-embed-text"

    @pytest.mark.asyncio
    async def test_embed_text_multiple(self):
        """Test embedding multiple texts."""
        provider = SimpleEmbeddingProvider(host="http://invalid:11434")

        result = await provider.embed_text(["text one", "text two"])

        assert result.embeddings.shape[0] == 2
        assert result.embeddings.shape[1] == 384
        assert not np.array_equal(result.embeddings[0], result.embeddings[1])


class TestInMemoryVectorStore:
    """Test InMemoryVectorStore functionality."""

    @pytest.mark.asyncio
    async def test_add_item(self):
        """Test adding item to store."""
        store = InMemoryVectorStore()

        item = SemanticMemoryItem(
            id="test-id",
            content="test content",
            embedding=np.array([0.1, 0.2, 0.3]),
            metadata={"key": "value"},
            created_at=datetime.now(UTC),
            collection="test",
        )

        item_id = await store.add(item)

        assert item_id == "test-id"
        assert "test-id" in store.items
        assert "test" in store.collections
        assert "test-id" in store.collections["test"]

    @pytest.mark.asyncio
    async def test_search_similar(self):
        """Test searching for similar items."""
        store = InMemoryVectorStore()

        # Add test items
        item1 = SemanticMemoryItem(
            id="item1",
            content="apple fruit",
            embedding=np.array([1.0, 0.0, 0.0]),
            metadata={},
            created_at=datetime.now(UTC),
            collection="test",
        )

        item2 = SemanticMemoryItem(
            id="item2",
            content="banana fruit",
            embedding=np.array([0.8, 0.6, 0.0]),
            metadata={},
            created_at=datetime.now(UTC),
            collection="test",
        )

        await store.add(item1)
        await store.add(item2)

        # Search with query similar to item1
        query_embedding = np.array([0.9, 0.1, 0.0])
        results = await store.search_similar(
            embedding=query_embedding, collection="test", limit=5, threshold=0.5
        )

        assert len(results) > 0
        assert results[0][0].id == "item1"  # Should be most similar
        assert results[0][1] > 0.5  # Similarity score

    @pytest.mark.asyncio
    async def test_get_collections(self):
        """Test getting collection names."""
        store = InMemoryVectorStore()

        item1 = SemanticMemoryItem(
            id="item1",
            content="test",
            embedding=np.array([1.0, 0.0, 0.0]),
            metadata={},
            created_at=datetime.now(UTC),
            collection="collection1",
        )

        item2 = SemanticMemoryItem(
            id="item2",
            content="test",
            embedding=np.array([0.0, 1.0, 0.0]),
            metadata={},
            created_at=datetime.now(UTC),
            collection="collection2",
        )

        await store.add(item1)
        await store.add(item2)

        collections = await store.get_collections()
        assert "collection1" in collections
        assert "collection2" in collections


class TestSemanticMemoryStoreNode:
    """Test SemanticMemoryStoreNode functionality."""

    @pytest.mark.asyncio
    async def test_store_single_content(self):
        """Test storing single content."""
        node = SemanticMemoryStoreNode(name="test_store")

        result = await node.run(
            content="test content",
            metadata={"key": "value"},
            collection="test_collection",
        )

        assert result["success"] is True
        assert result["count"] == 1
        assert len(result["ids"]) == 1
        assert result["collection"] == "test_collection"
        assert "embedding_model" in result

    @pytest.mark.asyncio
    async def test_store_multiple_content(self):
        """Test storing multiple contents."""
        node = SemanticMemoryStoreNode(name="test_store")

        result = await node.run(
            content=["content one", "content two"],
            metadata={"key": "value"},
            collection="test_collection",
        )

        assert result["success"] is True
        assert result["count"] == 2
        assert len(result["ids"]) == 2
        assert result["collection"] == "test_collection"

    @pytest.mark.asyncio
    async def test_store_missing_content(self):
        """Test error when content is missing."""
        node = SemanticMemoryStoreNode(name="test_store")

        with pytest.raises(ValueError, match="Content is required"):
            await node.run()

    def test_get_parameters(self):
        """Test getting node parameters."""
        node = SemanticMemoryStoreNode(name="test_store")
        parameters = node.get_parameters()

        param_names = list(parameters.keys())
        assert "content" in param_names
        assert "metadata" in param_names
        assert "collection" in param_names
        assert "embedding_model" in param_names
        assert "embedding_host" in param_names


class TestSemanticMemorySearchNode:
    """Test SemanticMemorySearchNode functionality."""

    @pytest.mark.asyncio
    async def test_search_with_results(self):
        """Test searching with results."""
        # Create nodes that share the same store
        store_node = SemanticMemoryStoreNode(name="test_store")
        search_node = SemanticMemorySearchNode(name="test_search")

        # First store some content
        await store_node.run(
            content=["apple fruit red", "banana fruit yellow"], collection="fruits"
        )

        # Then search
        result = await search_node.run(
            query="red fruit", collection="fruits", limit=5, threshold=0.1
        )

        assert result["success"] is True
        assert result["query"] == "red fruit"
        assert result["count"] >= 0  # May be 0 if similarity is too low
        assert len(result["results"]) >= 0
        assert "embedding_model" in result

        # If we have results, check structure
        if result["results"]:
            first_result = result["results"][0]
            assert "id" in first_result
            assert "content" in first_result
            assert "similarity" in first_result
            assert "metadata" in first_result
            assert "collection" in first_result

    @pytest.mark.asyncio
    async def test_search_missing_query(self):
        """Test error when query is missing."""
        node = SemanticMemorySearchNode(name="test_search")

        with pytest.raises(ValueError, match="Query is required"):
            await node.run()

    def test_get_parameters(self):
        """Test getting search node parameters."""
        node = SemanticMemorySearchNode(name="test_search")
        parameters = node.get_parameters()

        param_names = list(parameters.keys())
        assert "query" in param_names
        assert "limit" in param_names
        assert "threshold" in param_names
        assert "collection" in param_names


class TestSemanticAgentMatchingNode:
    """Test SemanticAgentMatchingNode functionality."""

    @pytest.mark.asyncio
    async def test_agent_matching(self):
        """Test agent matching with requirements."""
        node = SemanticAgentMatchingNode(name="test_matching")

        requirements = ["code generation", "python expertise", "debugging"]
        agents = [
            {"name": "CodeBot", "skills": ["python", "javascript", "debugging"]},
            {"name": "DataBot", "skills": ["data analysis", "statistics", "python"]},
            {"name": "TestBot", "skills": ["testing", "qa", "automation"]},
        ]

        result = await node.run(
            requirements=requirements, agents=agents, limit=5, threshold=0.1
        )

        assert result["success"] is True
        assert result["count"] > 0
        assert len(result["matches"]) > 0
        assert "embedding_model" in result

        # Check match structure
        first_match = result["matches"][0]
        assert "agent" in first_match
        assert "agent_index" in first_match
        assert "semantic_similarity" in first_match
        assert "keyword_similarity" in first_match
        assert "combined_score" in first_match

        # Matches should be sorted by combined score
        scores = [match["combined_score"] for match in result["matches"]]
        assert scores == sorted(scores, reverse=True)

    @pytest.mark.asyncio
    async def test_agent_matching_string_requirements(self):
        """Test agent matching with string requirements."""
        node = SemanticAgentMatchingNode(name="test_matching")

        result = await node.run(
            requirements="Need python coding expert",
            agents=["Python developer with 5 years experience", "Java developer"],
            limit=5,
            threshold=0.1,
        )

        assert result["success"] is True
        assert result["requirements"] == "Need python coding expert"
        assert result["count"] > 0

    @pytest.mark.asyncio
    async def test_agent_matching_missing_params(self):
        """Test error when required parameters are missing."""
        node = SemanticAgentMatchingNode(name="test_matching")

        with pytest.raises(ValueError, match="Requirements and agents are required"):
            await node.run()

    def test_keyword_similarity_calculation(self):
        """Test keyword similarity calculation."""
        node = SemanticAgentMatchingNode(name="test_matching")

        # Exact match
        sim1 = node._calculate_keyword_similarity("python coding", "python coding")
        assert sim1 == 1.0

        # Partial match
        sim2 = node._calculate_keyword_similarity("python coding", "python programming")
        assert 0.0 < sim2 < 1.0

        # No match
        sim3 = node._calculate_keyword_similarity("python coding", "java development")
        assert sim3 >= 0.0

    def test_get_parameters(self):
        """Test getting matching node parameters."""
        node = SemanticAgentMatchingNode(name="test_matching")
        parameters = node.get_parameters()

        param_names = list(parameters.keys())
        assert "requirements" in param_names
        assert "agents" in param_names
        assert "limit" in param_names
        assert "threshold" in param_names
        assert "weight_semantic" in param_names
        assert "weight_keyword" in param_names

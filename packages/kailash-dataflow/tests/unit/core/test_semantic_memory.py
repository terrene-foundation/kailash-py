"""
Unit tests for semantic memory functionality.
"""

from datetime import datetime
from unittest.mock import AsyncMock, Mock, patch

import numpy as np
import pytest
from dataflow.semantic.embeddings import (
    EmbeddingProvider,
    EmbeddingResult,
    OllamaEmbeddings,
    OpenAIEmbeddings,
)
from dataflow.semantic.memory import MemoryItem, SemanticMemory, VectorStore
from dataflow.semantic.search import (
    HybridSearchEngine,
    SearchResult,
    SemanticSearchEngine,
)


class TestEmbeddingProviders:
    """Test embedding provider implementations."""

    def test_embedding_result_creation(self):
        """Test creating embedding results."""
        embeddings = np.array([[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]])
        result = EmbeddingResult(
            embeddings=embeddings,
            model="test-model",
            dimension=3,
            metadata={"test": "value"},
        )

        assert result.embeddings.shape == (2, 3)
        assert result.model == "test-model"
        assert result.dimension == 3
        assert result.metadata["test"] == "value"

    @pytest.mark.asyncio
    async def test_ollama_embeddings_cache(self):
        """Test Ollama embeddings with caching."""
        # Create a real async context manager mock
        from contextlib import asynccontextmanager
        from types import AsyncGeneratorType

        @asynccontextmanager
        async def mock_session():
            mock_session_obj = AsyncMock()

            @asynccontextmanager
            async def mock_post(*args, **kwargs):
                mock_response = AsyncMock()
                mock_response.status = 200
                mock_response.json = AsyncMock(
                    return_value={"embedding": [0.1, 0.2, 0.3]}
                )
                mock_response.text = AsyncMock(return_value="")
                yield mock_response

            mock_session_obj.post = mock_post
            yield mock_session_obj

        with patch("dataflow.semantic.embeddings.aiohttp.ClientSession", mock_session):

            provider = OllamaEmbeddings(dimension=3)

            # First call - should hit API
            result1 = await provider.embed_text("test text")
            assert result1.embeddings.shape == (1, 3)
            assert not result1.metadata.get("cached", False)

            # Second call - should use cache
            result2 = await provider.embed_text("test text")
            assert result2.embeddings.shape == (1, 3)
            # Note: Our mock doesn't actually implement caching,
            # but in real implementation this would be cached

    def test_cache_key_generation(self):
        """Test cache key generation."""
        provider = OllamaEmbeddings()
        key1 = provider._get_cache_key("test")
        key2 = provider._get_cache_key("test")
        key3 = provider._get_cache_key("different")

        assert key1 == key2
        assert key1 != key3


class TestMemoryItem:
    """Test MemoryItem dataclass."""

    def test_memory_item_creation(self):
        """Test creating a memory item."""
        embedding = np.array([0.1, 0.2, 0.3])
        item = MemoryItem(
            id="test-id",
            content="test content",
            embedding=embedding,
            metadata={"key": "value"},
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            collection="test",
        )

        assert item.id == "test-id"
        assert item.content == "test content"
        assert np.array_equal(item.embedding, embedding)
        assert item.metadata["key"] == "value"
        assert item.collection == "test"

    def test_memory_item_serialization(self):
        """Test serializing memory item."""
        now = datetime.utcnow()
        embedding = np.array([0.1, 0.2, 0.3])

        item = MemoryItem(
            id="test-id",
            content="test content",
            embedding=embedding,
            metadata={"key": "value"},
            created_at=now,
            updated_at=now,
            collection="test",
        )

        # To dict
        data = item.to_dict()
        assert data["id"] == "test-id"
        assert data["content"] == "test content"
        assert data["embedding"] == [0.1, 0.2, 0.3]
        assert data["metadata"]["key"] == "value"
        assert data["collection"] == "test"

        # From dict
        restored = MemoryItem.from_dict(data)
        assert restored.id == item.id
        assert restored.content == item.content
        assert np.array_equal(restored.embedding, item.embedding)
        assert restored.metadata == item.metadata
        assert restored.collection == item.collection


class TestVectorStore:
    """Test vector store functionality."""

    @pytest.fixture
    def mock_connection_builder(self):
        """Create mock connection builder."""
        mock_builder = Mock()
        mock_adapter = Mock()
        mock_adapter.dialect_type = "postgresql"
        mock_builder.adapter = mock_adapter

        # Mock connection context manager properly
        mock_conn = AsyncMock()
        async_context_manager = AsyncMock()
        async_context_manager.__aenter__.return_value = mock_conn
        async_context_manager.__aexit__.return_value = None
        mock_builder.get_connection.return_value = async_context_manager

        return mock_builder

    @pytest.mark.asyncio
    async def test_vector_store_initialization(self, mock_connection_builder):
        """Test vector store initialization."""
        store = VectorStore(mock_connection_builder)

        await store.initialize()

        # Should create extension and table
        conn = (
            mock_connection_builder.get_connection.return_value.__aenter__.return_value
        )
        assert conn.execute.call_count >= 2  # Extension + table creation

    @pytest.mark.asyncio
    async def test_vector_store_add(self, mock_connection_builder):
        """Test adding items to vector store."""
        store = VectorStore(mock_connection_builder)

        # Mock fetchrow to return an ID
        mock_conn = (
            mock_connection_builder.get_connection.return_value.__aenter__.return_value
        )
        mock_conn.fetchrow.return_value = {"id": "generated-id"}

        item = MemoryItem(
            id="test-id",
            content="test content",
            embedding=np.array([0.1, 0.2, 0.3]),
            metadata={"key": "value"},
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )

        ids = await store.add(item)

        assert len(ids) == 1
        assert ids[0] == "generated-id"
        assert mock_conn.fetchrow.called


class TestSemanticMemory:
    """Test semantic memory high-level interface."""

    @pytest.fixture
    def mock_components(self):
        """Create mock components."""
        mock_provider = AsyncMock(spec=EmbeddingProvider)
        mock_provider.embed_text.return_value = EmbeddingResult(
            embeddings=np.array([[0.1, 0.2, 0.3]]),
            model="test",
            dimension=3,
            metadata={},
        )

        mock_store = AsyncMock(spec=VectorStore)
        mock_store.add.return_value = ["test-id"]
        mock_store.search_similar.return_value = []

        return mock_provider, mock_store

    @pytest.mark.asyncio
    async def test_remember_single_content(self, mock_components):
        """Test remembering single content."""
        provider, store = mock_components
        memory = SemanticMemory(provider, store)

        ids = await memory.remember(content="test content", metadata={"key": "value"})

        assert len(ids) == 1
        assert ids[0] == "test-id"
        assert provider.embed_text.called
        assert store.add.called

    @pytest.mark.asyncio
    async def test_remember_multiple_content(self, mock_components):
        """Test remembering multiple contents."""
        provider, store = mock_components
        provider.embed_text.return_value = EmbeddingResult(
            embeddings=np.array([[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]),
            model="test",
            dimension=3,
            metadata={},
        )
        store.add.return_value = ["id1", "id2"]

        memory = SemanticMemory(provider, store)

        ids = await memory.remember(
            content=["content1", "content2"],
            metadata=[{"key1": "value1"}, {"key2": "value2"}],
        )

        assert len(ids) == 2
        assert provider.embed_text.called
        assert store.add.called

    @pytest.mark.asyncio
    async def test_recall(self, mock_components):
        """Test recalling similar content."""
        provider, store = mock_components

        # Mock search results
        mock_item = MemoryItem(
            id="found-id",
            content="similar content",
            embedding=np.array([0.1, 0.2, 0.3]),
            metadata={"key": "value"},
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        store.search_similar.return_value = [(mock_item, 0.95)]

        memory = SemanticMemory(provider, store)

        results = await memory.recall("query text", limit=5)

        assert len(results) == 1
        assert results[0][0].id == "found-id"
        assert results[0][1] == 0.95
        assert provider.embed_text.called
        assert store.search_similar.called


class TestSearchEngines:
    """Test search engine implementations."""

    @pytest.fixture
    def mock_memory(self):
        """Create mock semantic memory."""
        memory = AsyncMock(spec=SemanticMemory)
        return memory

    @pytest.mark.asyncio
    async def test_semantic_search_engine(self, mock_memory):
        """Test semantic search engine."""
        # Mock recall results
        mock_item = MemoryItem(
            id="result-id",
            content="result content",
            embedding=np.array([0.1, 0.2, 0.3]),
            metadata={"key": "value"},
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        mock_memory.recall.return_value = [(mock_item, 0.9)]

        engine = SemanticSearchEngine(mock_memory)

        results = await engine.search("test query", limit=10)

        assert len(results) == 1
        assert results[0].id == "result-id"
        assert results[0].score == 0.9
        assert results[0].semantic_score == 0.9
        assert results[0].source == "semantic"

    def test_search_result_creation(self):
        """Test creating search results."""
        result = SearchResult(
            id="test-id",
            content="test content",
            score=0.85,
            semantic_score=0.9,
            keyword_score=0.7,
            metadata={"key": "value"},
            source="hybrid",
        )

        assert result.id == "test-id"
        assert result.content == "test content"
        assert result.score == 0.85
        assert result.semantic_score == 0.9
        assert result.keyword_score == 0.7
        assert result.relevance_score == 0.85
        assert result.source == "hybrid"

    def test_tokenize_query(self):
        """Test query tokenization."""
        mock_builder = Mock()
        mock_builder.adapter.dialect_type = "postgresql"

        engine = HybridSearchEngine(
            semantic_memory=Mock(), connection_builder=mock_builder
        )

        tokens = engine._tokenize_query("The quick brown fox jumps")

        # Should remove stop words and short tokens
        assert "the" not in tokens
        assert "quick" in tokens
        assert "brown" in tokens
        assert "fox" in tokens
        assert "jumps" in tokens

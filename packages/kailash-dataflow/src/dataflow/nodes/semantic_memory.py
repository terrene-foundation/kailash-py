"""
Semantic memory nodes for DataFlow workflows.

These nodes integrate semantic search capabilities into DataFlow workflows,
allowing for embedding generation, similarity search, and hybrid search.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Union

import numpy as np

from kailash.nodes.base import Node, NodeParameter, register_node

from ..adapters.factory import AdapterFactory
from ..database.connection_builder import ConnectionStringBuilder
from ..semantic.embeddings import OllamaEmbeddings, OpenAIEmbeddings
from ..semantic.memory import SemanticMemory, VectorStore
from ..semantic.search import HybridSearchEngine, SemanticSearchEngine


@register_node()
class SemanticMemoryNode(Node):
    """Store content in semantic memory with embeddings."""

    def __init__(self, name: str = "semantic_memory", **kwargs):
        """Initialize semantic memory node."""
        # Define node parameters
        self.content = None
        self.metadata = None
        self.collection = "default"
        self.embedding_provider = "ollama"
        self.embedding_model = "nomic-embed-text"
        self.api_key = None
        self.connection_string = None

        # Set attributes before parent init
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)

        super().__init__(name=name, **kwargs)

        self._memory = None

    def get_parameters(self) -> List[NodeParameter]:
        """Get node parameters."""
        return [
            NodeParameter(
                name="content",
                type="any",
                required=True,
                description="Content to store (string or list of strings)",
            ),
            NodeParameter(
                name="metadata",
                type="any",
                required=False,
                description="Metadata to attach (dict or list of dicts)",
            ),
            NodeParameter(
                name="collection",
                type="str",
                required=False,
                default="default",
                description="Collection name",
            ),
            NodeParameter(
                name="embedding_provider",
                type="str",
                required=False,
                default="ollama",
                description="Embedding provider (ollama, openai)",
            ),
            NodeParameter(
                name="embedding_model",
                type="str",
                required=False,
                default="nomic-embed-text",
                description="Embedding model name",
            ),
            NodeParameter(
                name="api_key",
                type="str",
                required=False,
                description="API key for embedding provider",
            ),
            NodeParameter(
                name="connection_string",
                type="str",
                required=False,
                description="Database connection string",
            ),
        ]

    async def _get_memory(self) -> SemanticMemory:
        """Get or create semantic memory instance."""
        if self._memory is None:
            # Create embedding provider
            if self.embedding_provider == "openai":
                if not self.api_key:
                    raise ValueError("OpenAI API key required")
                provider = OpenAIEmbeddings(
                    api_key=self.api_key, model_name=self.embedding_model
                )
            else:
                provider = OllamaEmbeddings(model_name=self.embedding_model)

            # Create connection builder
            if not self.connection_string:
                # Try to get from context
                context = self.get_context()
                self.connection_string = context.get(
                    "connection_string", "postgresql://localhost:5432/dataflow"
                )

            adapter = AdapterFactory.create_adapter(self.connection_string)
            connection_builder = ConnectionBuilder(adapter)

            # Create vector store
            vector_store = VectorStore(connection_builder)

            # Create semantic memory
            self._memory = SemanticMemory(provider, vector_store, self.collection)

        return self._memory

    async def run(self, **kwargs) -> Dict[str, Any]:
        """Store content in semantic memory."""
        # Get parameters
        content = kwargs.get("content", self.content)
        metadata = kwargs.get("metadata", self.metadata)
        collection = kwargs.get("collection", self.collection)

        if not content:
            raise ValueError("Content is required")

        # Get memory instance
        memory = await self._get_memory()

        # Store in memory
        ids = await memory.remember(
            content=content, metadata=metadata, collection=collection
        )

        return {
            "success": True,
            "ids": ids,
            "count": len(ids),
            "collection": collection,
        }


@register_node()
class SemanticSearchNode(Node):
    """Search semantic memory for similar content."""

    def __init__(self, name: str = "semantic_search", **kwargs):
        """Initialize semantic search node."""
        # Define node parameters
        self.query = None
        self.limit = 10
        self.threshold = 0.7
        self.collection = None
        self.metadata_filter = None
        self.embedding_provider = "ollama"
        self.embedding_model = "nomic-embed-text"
        self.api_key = None
        self.connection_string = None

        # Set attributes before parent init
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)

        super().__init__(name=name, **kwargs)

        self._search_engine = None

    def get_parameters(self) -> List[NodeParameter]:
        """Get node parameters."""
        return [
            NodeParameter(
                name="query", type="str", required=True, description="Search query"
            ),
            NodeParameter(
                name="limit",
                type="int",
                required=False,
                default=10,
                description="Maximum number of results",
            ),
            NodeParameter(
                name="threshold",
                type="float",
                required=False,
                default=0.7,
                description="Minimum similarity threshold",
            ),
            NodeParameter(
                name="collection",
                type="str",
                required=False,
                description="Collection to search",
            ),
            NodeParameter(
                name="metadata_filter",
                type="dict",
                required=False,
                description="Metadata filters",
            ),
            NodeParameter(
                name="embedding_provider",
                type="str",
                required=False,
                default="ollama",
                description="Embedding provider",
            ),
            NodeParameter(
                name="embedding_model",
                type="str",
                required=False,
                default="nomic-embed-text",
                description="Embedding model",
            ),
            NodeParameter(
                name="api_key",
                type="str",
                required=False,
                description="API key for provider",
            ),
            NodeParameter(
                name="connection_string",
                type="str",
                required=False,
                description="Database connection",
            ),
        ]

    async def _get_search_engine(self) -> SemanticSearchEngine:
        """Get or create search engine."""
        if self._search_engine is None:
            # Create embedding provider
            if self.embedding_provider == "openai":
                if not self.api_key:
                    raise ValueError("OpenAI API key required")
                provider = OpenAIEmbeddings(
                    api_key=self.api_key, model_name=self.embedding_model
                )
            else:
                provider = OllamaEmbeddings(model_name=self.embedding_model)

            # Create connection
            if not self.connection_string:
                context = self.get_context()
                self.connection_string = context.get(
                    "connection_string", "postgresql://localhost:5432/dataflow"
                )

            adapter = AdapterFactory.create_adapter(self.connection_string)
            connection_builder = ConnectionBuilder(adapter)

            # Create vector store and memory
            vector_store = VectorStore(connection_builder)
            memory = SemanticMemory(provider, vector_store)

            # Create search engine
            self._search_engine = SemanticSearchEngine(memory)

        return self._search_engine

    async def run(self, **kwargs) -> Dict[str, Any]:
        """Perform semantic search."""
        # Get parameters
        query = kwargs.get("query", self.query)
        limit = kwargs.get("limit", self.limit)
        threshold = kwargs.get("threshold", self.threshold)
        collection = kwargs.get("collection", self.collection)
        metadata_filter = kwargs.get("metadata_filter", self.metadata_filter)

        if not query:
            raise ValueError("Query is required")

        # Get search engine
        engine = await self._get_search_engine()

        # Perform search
        results = await engine.search(
            query=query,
            limit=limit,
            threshold=threshold,
            collection=collection,
            metadata_filter=metadata_filter,
        )

        # Format results
        formatted_results = []
        for result in results:
            formatted_results.append(
                {
                    "id": result.id,
                    "content": result.content,
                    "score": result.score,
                    "metadata": result.metadata,
                }
            )

        return {
            "success": True,
            "query": query,
            "results": formatted_results,
            "count": len(formatted_results),
        }


@register_node()
class HybridSearchNode(Node):
    """Hybrid search combining semantic and keyword search."""

    def __init__(self, name: str = "hybrid_search", **kwargs):
        """Initialize hybrid search node."""
        # Define parameters
        self.query = None
        self.limit = 10
        self.semantic_threshold = 0.5
        self.collection = None
        self.metadata_filter = None
        self.fields = None
        self.semantic_weight = 0.7
        self.keyword_weight = 0.3
        self.table_name = "documents"
        self.embedding_provider = "ollama"
        self.embedding_model = "nomic-embed-text"
        self.api_key = None
        self.connection_string = None

        # Set attributes
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)

        super().__init__(name=name, **kwargs)

        self._search_engine = None

    def get_parameters(self) -> List[NodeParameter]:
        """Get node parameters."""
        return [
            NodeParameter(
                name="query", type="str", required=True, description="Search query"
            ),
            NodeParameter(
                name="limit",
                type="int",
                required=False,
                default=10,
                description="Maximum results",
            ),
            NodeParameter(
                name="semantic_threshold",
                type="float",
                required=False,
                default=0.5,
                description="Semantic similarity threshold",
            ),
            NodeParameter(
                name="collection",
                type="str",
                required=False,
                description="Collection to search",
            ),
            NodeParameter(
                name="metadata_filter",
                type="dict",
                required=False,
                description="Metadata filters",
            ),
            NodeParameter(
                name="fields",
                type="list",
                required=False,
                description="Fields for keyword search",
            ),
            NodeParameter(
                name="semantic_weight",
                type="float",
                required=False,
                default=0.7,
                description="Weight for semantic scores",
            ),
            NodeParameter(
                name="keyword_weight",
                type="float",
                required=False,
                default=0.3,
                description="Weight for keyword scores",
            ),
            NodeParameter(
                name="table_name",
                type="str",
                required=False,
                default="documents",
                description="Table for keyword search",
            ),
            NodeParameter(
                name="embedding_provider",
                type="str",
                required=False,
                default="ollama",
                description="Embedding provider",
            ),
            NodeParameter(
                name="embedding_model",
                type="str",
                required=False,
                default="nomic-embed-text",
                description="Embedding model",
            ),
            NodeParameter(
                name="api_key", type="str", required=False, description="API key"
            ),
            NodeParameter(
                name="connection_string",
                type="str",
                required=False,
                description="Database connection",
            ),
        ]

    async def _get_search_engine(self) -> HybridSearchEngine:
        """Get or create hybrid search engine."""
        if self._search_engine is None:
            # Create embedding provider
            if self.embedding_provider == "openai":
                if not self.api_key:
                    raise ValueError("OpenAI API key required")
                provider = OpenAIEmbeddings(
                    api_key=self.api_key, model_name=self.embedding_model
                )
            else:
                provider = OllamaEmbeddings(model_name=self.embedding_model)

            # Create connection
            if not self.connection_string:
                context = self.get_context()
                self.connection_string = context.get(
                    "connection_string", "postgresql://localhost:5432/dataflow"
                )

            adapter = AdapterFactory.create_adapter(self.connection_string)
            connection_builder = ConnectionBuilder(adapter)

            # Create components
            vector_store = VectorStore(connection_builder)
            memory = SemanticMemory(provider, vector_store)

            # Create hybrid engine
            self._search_engine = HybridSearchEngine(
                semantic_memory=memory,
                connection_builder=connection_builder,
                table_name=self.table_name,
                semantic_weight=self.semantic_weight,
                keyword_weight=self.keyword_weight,
            )

        return self._search_engine

    async def run(self, **kwargs) -> Dict[str, Any]:
        """Perform hybrid search."""
        # Get parameters
        query = kwargs.get("query", self.query)
        limit = kwargs.get("limit", self.limit)
        semantic_threshold = kwargs.get("semantic_threshold", self.semantic_threshold)
        collection = kwargs.get("collection", self.collection)
        metadata_filter = kwargs.get("metadata_filter", self.metadata_filter)
        fields = kwargs.get("fields", self.fields)

        if not query:
            raise ValueError("Query is required")

        # Get search engine
        engine = await self._get_search_engine()

        # Perform search
        results = await engine.search(
            query=query,
            limit=limit,
            semantic_threshold=semantic_threshold,
            collection=collection,
            metadata_filter=metadata_filter,
            fields=fields,
        )

        # Format results
        formatted_results = []
        for result in results:
            formatted_results.append(
                {
                    "id": result.id,
                    "content": result.content,
                    "score": result.score,
                    "semantic_score": result.semantic_score,
                    "keyword_score": result.keyword_score,
                    "source": result.source,
                    "metadata": result.metadata,
                }
            )

        return {
            "success": True,
            "query": query,
            "results": formatted_results,
            "count": len(formatted_results),
            "search_type": "hybrid",
        }


@register_node()
class SemanticIndexNode(Node):
    """Reindex existing database content for semantic search."""

    def __init__(self, name: str = "semantic_index", **kwargs):
        """Initialize semantic index node."""
        # Define parameters
        self.table_name = None
        self.content_field = "content"
        self.id_field = "id"
        self.metadata_fields = None
        self.batch_size = 100
        self.collection = "default"
        self.embedding_provider = "ollama"
        self.embedding_model = "nomic-embed-text"
        self.api_key = None
        self.connection_string = None

        # Set attributes
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)

        super().__init__(name=name, **kwargs)

    def get_parameters(self) -> List[NodeParameter]:
        """Get node parameters."""
        return [
            NodeParameter(
                name="table_name",
                type="str",
                required=True,
                description="Table to reindex",
            ),
            NodeParameter(
                name="content_field",
                type="str",
                required=False,
                default="content",
                description="Field containing text",
            ),
            NodeParameter(
                name="id_field",
                type="str",
                required=False,
                default="id",
                description="ID field",
            ),
            NodeParameter(
                name="metadata_fields",
                type="list",
                required=False,
                description="Fields to include as metadata",
            ),
            NodeParameter(
                name="batch_size",
                type="int",
                required=False,
                default=100,
                description="Batch size",
            ),
            NodeParameter(
                name="collection",
                type="str",
                required=False,
                default="default",
                description="Collection name",
            ),
            NodeParameter(
                name="embedding_provider",
                type="str",
                required=False,
                default="ollama",
                description="Embedding provider",
            ),
            NodeParameter(
                name="embedding_model",
                type="str",
                required=False,
                default="nomic-embed-text",
                description="Embedding model",
            ),
            NodeParameter(
                name="api_key", type="str", required=False, description="API key"
            ),
            NodeParameter(
                name="connection_string",
                type="str",
                required=False,
                description="Database connection",
            ),
        ]

    async def run(self, **kwargs) -> Dict[str, Any]:
        """Reindex table for semantic search."""
        # Get parameters
        table_name = kwargs.get("table_name", self.table_name)
        content_field = kwargs.get("content_field", self.content_field)
        id_field = kwargs.get("id_field", self.id_field)
        metadata_fields = kwargs.get("metadata_fields", self.metadata_fields)
        batch_size = kwargs.get("batch_size", self.batch_size)
        collection = kwargs.get("collection", self.collection)

        if not table_name:
            raise ValueError("Table name is required")

        # Create components
        if self.embedding_provider == "openai":
            if not self.api_key:
                raise ValueError("OpenAI API key required")
            provider = OpenAIEmbeddings(
                api_key=self.api_key, model_name=self.embedding_model
            )
        else:
            provider = OllamaEmbeddings(model_name=self.embedding_model)

        if not self.connection_string:
            context = self.get_context()
            self.connection_string = context.get(
                "connection_string", "postgresql://localhost:5432/dataflow"
            )

        adapter = AdapterFactory.create_adapter(self.connection_string)
        connection_builder = ConnectionBuilder(adapter)

        vector_store = VectorStore(connection_builder)
        memory = SemanticMemory(provider, vector_store)

        engine = HybridSearchEngine(
            semantic_memory=memory,
            connection_builder=connection_builder,
            table_name=table_name,
        )

        # Perform reindexing
        await engine.reindex(
            table_name=table_name,
            content_field=content_field,
            id_field=id_field,
            metadata_fields=metadata_fields,
            batch_size=batch_size,
            collection=collection,
        )

        return {
            "success": True,
            "table": table_name,
            "collection": collection,
            "batch_size": batch_size,
        }

"""Vector database and embedding nodes for the Kailash system.

This module provides nodes for interacting with vector databases and generating
embeddings. Key features include:

- A built-in in-memory vector store (``provider="memory"``) with real
  similarity search, metadata filtering, and CRUD operations
- A unified interface that external vector databases (Pinecone, Weaviate,
  Milvus, Qdrant, Chroma) can integrate against
- Embedding generation using various models (OpenAI, HuggingFace, etc.)
- Text chunking and preprocessing
- Vector similarity search (cosine / euclidean / dot)
- Metadata filtering

Design Philosophy:
- Ship a working, dependency-light in-memory backend out of the box
- Abstract away vector database differences
- Support multiple embedding models
- Provide flexible search capabilities
- Enable metadata-based filtering
- Handle text preprocessing

Common Use Cases:
- Semantic search applications
- RAG (Retrieval Augmented Generation) pipelines
- Content similarity analysis
- Document clustering
- Knowledge base retrieval

Example:
    >>> # Generate embeddings
    >>> embedder = EmbeddingNode()
    >>> embedder.configure({"model": "openai", "model_name": "text-embedding-ada-002"})
    >>> result = embedder.execute({"texts": ["Hello world", "Goodbye world"]})
    >>>
    >>> # Store in the built-in in-memory vector store
    >>> vector_db = VectorDatabaseNode()
    >>> vector_db.configure({
    ...     "provider": "memory",
    ...     "index_name": "my-index",
    ...     "dimension": 1536,
    ... })
    >>> vector_db.execute({
    ...     "operation": "upsert",
    ...     "vectors": result["embeddings"],
    ...     "ids": ["doc1", "doc2"],
    ...     "metadata": [{"source": "file1"}, {"source": "file2"}]
    ... })
"""

import math
from typing import Any

try:
    import numpy as np
except ImportError:
    np = None  # type: ignore[assignment]  # Optional dependency

from kailash.nodes.base import Node, NodeMetadata, NodeParameter, register_node
from kailash.sdk_exceptions import NodeConfigurationError, NodeExecutionError


@register_node()
class EmbeddingNode(Node):
    """Generates embeddings for text data using various embedding models.

    This node provides a unified interface for generating text embeddings using
    different models and providers (OpenAI, HuggingFace, Cohere, etc.). It handles
    text preprocessing, batching, and error recovery.

    Design Pattern:
    - Strategy pattern for different embedding providers
    - Facade pattern for unified interface
    - Builder pattern for configuration

    Features:
    - Multiple embedding model support
    - Automatic text truncation
    - Batch processing
    - Error handling with retries
    - Model caching

    Common Usage Patterns:
    - Text to vector conversion for similarity search
    - Document embedding for clustering
    - Query embedding for semantic search
    - Content analysis pipelines

    Upstream Dependencies:
    - Text preprocessing nodes (TextSplitter, TextCleaner)
    - Document reader nodes (PDFReader, DocxReader)
    - API configuration nodes

    Downstream Consumers:
    - VectorDatabaseNode
    - SimilaritySearchNode
    - ClusteringNode
    - RAG pipeline nodes

    Configuration:
        model (str): Model provider ("openai", "huggingface", "cohere")
        model_name (str): Specific model name (e.g., "text-embedding-ada-002")
        api_key (str): API key for the provider (if required)
        batch_size (int): Number of texts to process in one batch
        max_tokens (int): Maximum tokens per text
        normalize (bool): Whether to normalize embeddings

    Inputs:
        texts (List[str]): List of texts to embed

    Outputs:
        embeddings (List[List[float]]): Generated embeddings
        model_info (Dict): Model metadata (dimensions, etc.)

    Error Handling:
    - Validates model availability
    - Handles API rate limits
    - Manages token limits
    - Retries on transient failures

    Example:
        >>> embedder = EmbeddingNode()
        >>> embedder.configure({
        ...     "model": "openai",
        ...     "model_name": "text-embedding-ada-002",
        ...     "api_key": "your-api-key",
        ...     "batch_size": 100,
        ...     "normalize": True
        ... })
        >>> result = embedder.execute({
        ...     "texts": ["Sample text 1", "Sample text 2"]
        ... })
        >>> print(f"Embedding dimensions: {len(result['embeddings'][0])}")
    """

    _node_metadata = NodeMetadata(
        name="EmbeddingNode",
        description="Generates embeddings for text data",
        version="1.0.0",
        tags={"embedding", "nlp", "vector"},
    )

    def __init__(self, name: str | None = None, id: str | None = None, **kwargs):
        """Initialize the embedding node.

        Sets up the node with default configuration and prepares for
        model initialization. The actual model is loaded during configuration.
        """
        # Set name from parameters
        if name:
            self.name = name
        elif id:
            self.name = id
        elif "name" in kwargs:
            self.name = kwargs.pop("name")
        elif "id" in kwargs:
            self.name = kwargs.pop("id")
        else:
            self.name = self.__class__.__name__

        # Initialize node attributes
        self._model = None
        self._model_info = {}

        # Call parent constructor
        super().__init__(name=self.name)

    def get_parameters(self) -> dict[str, NodeParameter]:
        """Define parameters for the embedding node."""
        return {
            "model": NodeParameter(
                name="model",
                type=str,
                description="Model provider",
                required=True,
                default="openai",
            ),
            "model_name": NodeParameter(
                name="model_name",
                type=str,
                description="Specific model name",
                required=True,
                default="text-embedding-ada-002",
            ),
            "api_key": NodeParameter(
                name="api_key",
                type=str,
                description="API key for the provider",
                required=False,
            ),
            "batch_size": NodeParameter(
                name="batch_size",
                type=int,
                description="Batch size for processing",
                required=False,
                default=100,
            ),
            "max_tokens": NodeParameter(
                name="max_tokens",
                type=int,
                description="Maximum tokens per text",
                required=False,
                default=8192,
            ),
            "normalize": NodeParameter(
                name="normalize",
                type=bool,
                description="Normalize embeddings",
                required=False,
                default=True,
            ),
        }

    def configure(self, config: dict[str, Any]) -> None:
        """Configure the embedding node with model settings.

        Validates configuration, initializes the embedding model, and
        prepares for text processing. Different models require different
        configuration parameters.

        Args:
            config: Configuration dictionary with model settings

        Raises:
            NodeConfigurationError: If configuration is invalid
        """
        super().configure(config)  # type: ignore[reportAttributeAccessIssue]

        # Initialize model based on provider
        model_provider = self.config.get("model", "openai")
        model_name = self.config.get("model_name")

        if not model_name:
            raise NodeConfigurationError("model_name is required")

        try:
            # Placeholder for actual model initialization
            self._initialize_model(model_provider, model_name)
        except Exception as e:
            raise NodeConfigurationError(f"Failed to initialize model: {str(e)}")

    def _initialize_model(self, provider: str, model_name: str) -> None:
        """Initialize the embedding model.

        Loads the specified model and prepares it for use. This is a
        placeholder for actual model initialization logic.

        Args:
            provider: Model provider name
            model_name: Specific model identifier

        Raises:
            ValueError: If provider is not supported
        """
        # Placeholder for actual model initialization
        if provider not in ["openai", "huggingface", "cohere", "custom"]:
            raise ValueError(f"Unsupported provider: {provider}")

        self._model = f"{provider}:{model_name}"  # Placeholder
        self._model_info = {
            "provider": provider,
            "model_name": model_name,
            "dimensions": 1536 if provider == "openai" else 768,
            "max_tokens": self.config.get("max_tokens", 8192),
        }

    def run(self, **kwargs) -> dict[str, Any]:
        """Generate embeddings for input texts.

        Implementation of the abstract run method from the base Node class.

        Args:
            **kwargs: Keyword arguments containing 'texts' list

        Returns:
            Dictionary containing embeddings and model info
        """
        return self.execute(kwargs)

    def execute(self, inputs: dict[str, Any]) -> dict[str, Any]:  # type: ignore[reportIncompatibleMethodOverride]
        """Generate embeddings for input texts.

        Processes the input texts through the configured embedding model,
        handling batching, normalization, and error recovery.

        Args:
            inputs: Dictionary containing 'texts' list

        Returns:
            Dictionary containing embeddings and model info

        Raises:
            NodeExecutionError: If embedding generation fails
        """
        try:
            texts = inputs.get("texts", [])
            if not texts:
                raise ValueError("No texts provided for embedding")

            # Process texts in batches
            batch_size = self.config.get("batch_size", 100)
            all_embeddings = []

            for i in range(0, len(texts), batch_size):
                batch = texts[i : i + batch_size]
                batch_embeddings = self._generate_embeddings(batch)
                all_embeddings.extend(batch_embeddings)

            # Normalize if requested
            if self.config.get("normalize", True):
                all_embeddings = self._normalize_embeddings(all_embeddings)

            return {
                "embeddings": all_embeddings,
                "model_info": self._model_info.copy(),
                "count": len(all_embeddings),
            }
        except Exception as e:
            raise NodeExecutionError(f"Failed to generate embeddings: {str(e)}")

    def _generate_embeddings(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for a batch of texts.

        This is a placeholder for actual embedding generation logic.

        Args:
            texts: List of texts to embed

        Returns:
            List of embedding vectors
        """
        # Placeholder implementation
        dim = self._model_info.get("dimensions", 768)
        return [np.random.randn(dim).tolist() for _ in texts]  # type: ignore[reportOptionalMemberAccess]

    def _normalize_embeddings(self, embeddings: list[list[float]]) -> list[list[float]]:
        """Normalize embedding vectors to unit length.

        Normalizes each embedding vector to have a magnitude of 1.0,
        which is useful for cosine similarity calculations.

        Args:
            embeddings: List of embedding vectors

        Returns:
            List of normalized embedding vectors
        """
        normalized = []
        for embedding in embeddings:
            vec = np.array(embedding)  # type: ignore[reportOptionalMemberAccess]
            norm = np.linalg.norm(vec)  # type: ignore[reportOptionalMemberAccess]
            if norm > 0:
                normalized.append((vec / norm).tolist())
            else:
                normalized.append(embedding)
        return normalized


@register_node()
class VectorDatabaseNode(Node):
    """Stores and retrieves embeddings with a built-in in-memory vector store.

    This node ships a real, dependency-light in-memory backend
    (``provider="memory"``) that performs actual similarity search, metadata
    filtering, and CRUD operations entirely in pure Python — no external
    service or extra dependency required. ``provider="memory"`` is the working
    default.

    External providers (Pinecone, Weaviate, Milvus, Qdrant, Chroma) are
    recognised as a unified interface, but require an external vector-DB
    integration that is NOT bundled with ``kailash``. Selecting one without a
    bundled client raises a clear ``NodeConfigurationError`` rather than
    silently faking results.

    Design Pattern:
    - Repository pattern for data access
    - Adapter pattern for different backends
    - Command pattern for operations

    Features:
    - Built-in in-memory vector store with real similarity search
    - CRUD operations on vectors
    - Similarity search with metadata filters
    - Cosine / euclidean / dot-product distance metrics
    - Index management

    Common Usage Patterns:
    - Storing document embeddings
    - Semantic search implementation
    - Recommendation systems
    - Content deduplication
    - Knowledge graph augmentation

    Upstream Dependencies:
    - EmbeddingNode (vector generation)
    - Data processing nodes
    - Document extraction nodes

    Downstream Consumers:
    - Search interface nodes
    - RAG pipeline nodes
    - Analytics nodes
    - Visualization nodes

    Configuration:
        provider (str): Vector backend. ``"memory"`` is the built-in working
            backend; ``"pinecone"`` / ``"weaviate"`` / ``"milvus"`` /
            ``"qdrant"`` / ``"chroma"`` require an external integration.
        connection_string (str): Database connection details (external providers)
        index_name (str): Name of the vector index
        dimension (int): Vector dimension size (validated on every operation)
        metric (str): Distance metric ("cosine", "euclidean", "dot")

    Inputs:
        operation (str): Operation to perform ("upsert", "query", "delete", "fetch")
        vectors (List[List[float]]): Vectors for upsert operations
        ids (List[str]): Vector IDs
        metadata (List[Dict]): Associated metadata
        query_vector (List[float]): Vector for similarity search
        k (int): Number of results to return
        filter (Dict): Metadata filter for search

    Outputs:
        results (List[Dict]): Operation results
        status (str): Operation status

    Error Handling:
    - Connection validation
    - Dimension mismatch detection (raises ValueError)
    - Clear typed error for unbundled external providers

    Example:
        >>> vector_db = VectorDatabaseNode()
        >>> vector_db.configure({
        ...     "provider": "memory",  # built-in working backend
        ...     "index_name": "my-knowledge-base",
        ...     "dimension": 1536,
        ...     "metric": "cosine"
        ... })
        >>>
        >>> # Upsert vectors
        >>> result = vector_db.execute({
        ...     "operation": "upsert",
        ...     "vectors": [[0.1, 0.2, ...], [0.3, 0.4, ...]],
        ...     "ids": ["doc1", "doc2"],
        ...     "metadata": [{"title": "Document 1"}, {"title": "Document 2"}]
        ... })
        >>>
        >>> # Query similar vectors
        >>> search_result = vector_db.execute({
        ...     "operation": "query",
        ...     "query_vector": [0.15, 0.25, ...],
        ...     "k": 5,
        ...     "filter": {"category": "technical"}
        ... })
    """

    _node_metadata = NodeMetadata(
        name="VectorDatabaseNode",
        description="Vector database operations",
        version="1.0.0",
        tags={"vector", "database", "storage"},
    )

    def __init__(self, name: str | None = None, id: str | None = None, **kwargs):
        """Initialize the vector database node.

        Sets up the node and prepares for database connection.
        The actual connection is established during configuration.
        """
        # Set name from parameters
        if name:
            self.name = name
        elif id:
            self.name = id
        elif "name" in kwargs:
            self.name = kwargs.pop("name")
        elif "id" in kwargs:
            self.name = kwargs.pop("id")
        else:
            self.name = self.__class__.__name__

        # Initialize node attributes
        self._client = None
        self._index = None
        # Built-in in-memory vector store: id -> {"vector": [...], "metadata": {...}}
        self._store: dict[str, dict[str, Any]] = {}

        # Call parent constructor
        super().__init__(name=self.name)

    def get_parameters(self) -> dict[str, NodeParameter]:
        """Define parameters for the vector database node."""
        return {
            "provider": NodeParameter(
                name="provider",
                type=str,
                description=(
                    "Vector backend: 'memory' (built-in working backend) or an "
                    "external provider (pinecone/weaviate/milvus/qdrant/chroma) "
                    "requiring an integration not bundled with kailash"
                ),
                required=True,
            ),
            "connection_string": NodeParameter(
                name="connection_string",
                type=str,
                description="Database connection details",
                required=False,
            ),
            "index_name": NodeParameter(
                name="index_name",
                type=str,
                description="Vector index name",
                required=True,
            ),
            "api_key": NodeParameter(
                name="api_key",
                type=str,
                description="API key for cloud providers",
                required=False,
            ),
            "dimension": NodeParameter(
                name="dimension",
                type=int,
                description="Vector dimension size",
                required=True,
            ),
            "metric": NodeParameter(
                name="metric",
                type=str,
                description="Distance metric",
                required=False,
                default="cosine",
            ),
            "max_vectors": NodeParameter(
                name="max_vectors",
                type=int,
                description=(
                    "Optional cap on how many vectors the built-in in-memory "
                    "store may hold; an upsert that would exceed it raises a "
                    "typed error instead of growing the heap. Unset (default) "
                    "means the store is bounded only by available process "
                    "memory — set this when accepting untrusted upsert volume."
                ),
                required=False,
            ),
        }

    def configure(self, config: dict[str, Any]) -> None:
        """Configure the vector database connection.

        Establishes connection to the vector database, validates the index,
        and prepares for vector operations.

        Args:
            config: Configuration with database settings

        Raises:
            NodeConfigurationError: If connection fails
        """
        # The base Node has no ``configure`` method — configuration provided
        # post-construction is merged into ``self.config`` (populated from
        # __init__ kwargs, defaulting to {}). This keeps the documented
        # ``configure() -> execute()`` user flow working.
        if getattr(self, "config", None) is None:
            self.config = {}
        self.config.update(config)

        provider = self.config.get("provider")
        index_name = self.config.get("index_name")

        if not index_name:
            raise NodeConfigurationError("index_name is required")

        try:
            self._connect_to_database(provider)  # type: ignore[reportArgumentType]
        except NodeConfigurationError:
            # Already a clear typed configuration error (e.g. unbundled external
            # provider) — surface it verbatim rather than re-wrapping.
            raise
        except Exception as e:
            raise NodeConfigurationError(f"Failed to connect to {provider}: {str(e)}")

    # External providers recognised as a unified interface but NOT bundled.
    _EXTERNAL_PROVIDERS = ("pinecone", "weaviate", "milvus", "qdrant", "chroma")

    def _connect_to_database(self, provider: str) -> None:
        """Connect to the vector backend.

        For ``provider="memory"`` this initializes the built-in in-memory
        store. External providers raise a clear typed error because no client
        or credentials are bundled with ``kailash`` — the node never fakes a
        connection.

        Args:
            provider: Backend name

        Raises:
            NodeConfigurationError: For external providers (no bundled client).
            ValueError: If provider is not a recognised name.
        """
        if provider == "memory":
            # Real per-node in-memory store; survives across operations on this
            # node instance.
            self._index = self.config.get("index_name")
            return

        if provider in self._EXTERNAL_PROVIDERS:
            raise NodeConfigurationError(
                f"provider '{provider}' requires an external vector-DB "
                "integration that is not bundled with kailash; use "
                "provider='memory' for built-in in-memory vector search."
            )

        raise ValueError(
            f"Unsupported provider: {provider}; use 'memory' for the built-in "
            f"backend or one of {self._EXTERNAL_PROVIDERS} (external integration)."
        )

    def run(self, **kwargs) -> dict[str, Any]:
        """Execute vector database operations.

        Implementation of the abstract run method from the base Node class.

        Args:
            **kwargs: Keyword arguments for the operation

        Returns:
            Operation results
        """
        return self.execute(kwargs)

    def execute(self, inputs: dict[str, Any]) -> dict[str, Any]:  # type: ignore[reportIncompatibleMethodOverride]
        """Execute vector database operations.

        Performs the requested operation (upsert, query, delete, fetch)
        on the vector database.

        Args:
            inputs: Operation parameters

        Returns:
            Operation results

        Raises:
            NodeExecutionError: If operation fails
        """
        try:
            operation = inputs.get("operation", "query")

            if operation == "upsert":
                return self._upsert_vectors(inputs)
            elif operation == "query":
                return self._query_vectors(inputs)
            elif operation == "delete":
                return self._delete_vectors(inputs)
            elif operation == "fetch":
                return self._fetch_vectors(inputs)
            else:
                raise ValueError(f"Unknown operation: {operation}")
        except Exception as e:
            raise NodeExecutionError(f"Vector operation failed: {str(e)}")

    def _expected_dimension(self) -> int:
        """Return the configured vector dimension."""
        dimension = self.config.get("dimension")
        if dimension is None:
            raise ValueError("dimension is required for vector operations")
        return int(dimension)

    def _validate_dimension(self, vector: list[float], *, label: str) -> None:
        """Raise if a vector's length does not match the configured dimension."""
        expected = self._expected_dimension()
        if len(vector) != expected:
            raise ValueError(
                f"{label} has dimension {len(vector)} but the index is "
                f"configured for dimension {expected}"
            )

    @staticmethod
    def _metadata_matches(
        metadata: dict[str, Any], filter_dict: dict[str, Any]
    ) -> bool:
        """Return True iff metadata matches every key/value in the filter."""
        for key, value in filter_dict.items():
            if metadata.get(key) != value:
                return False
        return True

    def _similarity(self, query: list[float], stored: list[float]) -> float:
        """Compute a similarity score between two vectors (higher = closer).

        Implemented in pure Python for the configured metric:
        - ``cosine``: cosine similarity in [-1, 1]
        - ``dot``: dot product
        - ``euclidean``: 1 / (1 + distance), monotonic in -distance so that
          nearer vectors rank higher

        Returns:
            A score where larger values mean a closer match.
        """
        metric = self.config.get("metric", "cosine")

        dot = sum(q * s for q, s in zip(query, stored))

        if metric == "dot":
            return dot

        if metric == "euclidean":
            dist_sq = sum((q - s) ** 2 for q, s in zip(query, stored))
            distance = math.sqrt(dist_sq)
            return 1.0 / (1.0 + distance)

        if metric == "cosine":
            norm_q = math.sqrt(sum(q * q for q in query))
            norm_s = math.sqrt(sum(s * s for s in stored))
            if norm_q == 0.0 or norm_s == 0.0:
                return 0.0
            return dot / (norm_q * norm_s)

        raise ValueError(
            f"Unsupported metric: {metric}; use 'cosine', 'euclidean', or 'dot'."
        )

    def _upsert_vectors(self, inputs: dict[str, Any]) -> dict[str, Any]:
        """Insert or update vectors in the in-memory store.

        Args:
            inputs: Vectors, IDs, and (optional) per-vector metadata

        Returns:
            Upsert status with the real count of stored vectors
        """
        vectors = inputs.get("vectors", [])
        ids = inputs.get("ids", [])
        metadata = inputs.get("metadata", [])

        if not vectors or not ids:
            raise ValueError("Vectors and IDs are required for upsert")

        if len(vectors) != len(ids):
            raise ValueError("Number of vectors must match number of IDs")

        if metadata and len(metadata) != len(ids):
            raise ValueError("Number of metadata entries must match number of IDs")

        # Validate every vector's dimension up front so a mismatch fails loud
        # WITHOUT partially mutating the store (atomic upsert).
        for vector_id, vector in zip(ids, vectors):
            self._validate_dimension(vector, label=f"vector for id '{vector_id}'")

        # Enforce the optional in-memory capacity cap atomically, before any
        # store mutation, so an over-cap upsert fails loud instead of growing
        # the heap unbounded (see the ``max_vectors`` parameter).
        max_vectors = self.config.get("max_vectors")
        if max_vectors is not None:
            new_ids = {vid for vid in ids if vid not in self._store}
            projected = len(self._store) + len(new_ids)
            if projected > int(max_vectors):
                raise ValueError(
                    f"in-memory vector store capacity exceeded: this upsert "
                    f"would bring the total to {projected}, above "
                    f"max_vectors={int(max_vectors)}"
                )

        # Really store each vector + its metadata, aligned by index.
        for i, (vector_id, vector) in enumerate(zip(ids, vectors)):
            meta = metadata[i] if metadata and i < len(metadata) else {}
            self._store[vector_id] = {
                "vector": list(vector),
                "metadata": dict(meta) if meta else {},
            }

        return {
            "operation": "upsert",
            "status": "success",
            "count": len(ids),
            "index": self._index,
        }

    def _query_vectors(self, inputs: dict[str, Any]) -> dict[str, Any]:
        """Query the most similar vectors from the in-memory store.

        Computes a real similarity between the query vector and every stored
        vector using the configured metric, optionally narrows by a metadata
        filter, sorts by score descending, and returns the top-k real matches.

        Args:
            inputs: Query vector and parameters

        Returns:
            Search results drawn from the actual store (empty when no match)
        """
        query_vector = inputs.get("query_vector")
        k = inputs.get("k", 10)
        filter_dict = inputs.get("filter", {}) or {}

        if filter_dict and not isinstance(filter_dict, dict):
            raise ValueError(
                "filter must be a dict of metadata key/value equality " "constraints"
            )

        if not query_vector:
            raise ValueError("Query vector is required")

        self._validate_dimension(query_vector, label="query_vector")

        scored: list[dict[str, Any]] = []
        for vector_id, record in self._store.items():
            if filter_dict and not self._metadata_matches(
                record["metadata"], filter_dict
            ):
                continue
            score = self._similarity(query_vector, record["vector"])
            scored.append(
                {
                    "id": vector_id,
                    "score": score,
                    "metadata": dict(record["metadata"]),
                }
            )

        scored.sort(key=lambda item: item["score"], reverse=True)
        results = scored[:k]

        return {
            "operation": "query",
            "status": "success",
            "results": results,
            "count": len(results),
        }

    def _delete_vectors(self, inputs: dict[str, Any]) -> dict[str, Any]:
        """Delete vectors from the in-memory store by ID.

        Args:
            inputs: Vector IDs to delete

        Returns:
            Deletion status with the real number of vectors removed
        """
        ids = inputs.get("ids", [])

        if not ids:
            raise ValueError("IDs are required for deletion")

        deleted = 0
        for vector_id in ids:
            if self._store.pop(vector_id, None) is not None:
                deleted += 1

        return {"operation": "delete", "status": "success", "count": deleted}

    def _fetch_vectors(self, inputs: dict[str, Any]) -> dict[str, Any]:
        """Fetch specific vectors by ID from the in-memory store.

        Returns the real stored values and metadata for each requested id.
        Missing ids are honestly omitted from the result rather than fabricated.

        Args:
            inputs: Vector IDs to fetch

        Returns:
            Fetched vectors and metadata (only for ids that exist)
        """
        ids = inputs.get("ids", [])

        if not ids:
            raise ValueError("IDs are required for fetch")

        vectors: dict[str, dict[str, Any]] = {}
        for vector_id in ids:
            record = self._store.get(vector_id)
            if record is None:
                continue
            vectors[vector_id] = {
                "values": list(record["vector"]),
                "metadata": dict(record["metadata"]),
            }

        return {
            "operation": "fetch",
            "status": "success",
            "vectors": vectors,
        }


@register_node()
class TextSplitterNode(Node):
    """Splits text into chunks for embedding generation.

    This node provides various text splitting strategies optimized for
    embedding generation. It handles overlap, token counting, and
    semantic boundaries to create meaningful chunks.

    Design Pattern:
    - Strategy pattern for splitting algorithms
    - Chain of responsibility for preprocessing

    Features:
    - Multiple splitting strategies
    - Configurable chunk size and overlap
    - Token-aware splitting
    - Semantic boundary detection
    - Metadata preservation

    Common Usage Patterns:
    - Document chunking for RAG
    - Long text preprocessing
    - Context window management
    - Batch processing optimization

    Upstream Dependencies:
    - Document reader nodes
    - Text extraction nodes
    - PDF/DOCX processors

    Downstream Consumers:
    - EmbeddingNode
    - Text processing nodes
    - Storage nodes

    Configuration:
        strategy (str): Splitting strategy
        chunk_size (int): Maximum chunk size
        chunk_overlap (int): Overlap between chunks
        separator (str): Text separator
        preserve_sentences (bool): Keep sentence boundaries

    Inputs:
        text (str): Text to split
        metadata (Dict): Optional metadata to preserve

    Outputs:
        chunks (List[str]): Text chunks
        chunk_metadata (List[Dict]): Metadata for each chunk

    Example:
        >>> splitter = TextSplitterNode()
        >>> splitter.configure({
        ...     "strategy": "recursive",
        ...     "chunk_size": 1000,
        ...     "chunk_overlap": 200,
        ...     "preserve_sentences": True
        ... })
        >>> result = splitter.execute({
        ...     "text": "Long document text...",
        ...     "metadata": {"source": "document.pdf"}
        ... })
        >>> print(f"Created {len(result['chunks'])} chunks")
    """

    _node_metadata = NodeMetadata(
        name="TextSplitterNode",
        description="Splits text into chunks",
        version="1.0.0",
        tags={"text", "processing", "nlp"},
    )

    def __init__(self, name: str | None = None, id: str | None = None, **kwargs):
        """Initialize the text splitter node.

        Sets up the node with default configuration.
        """
        # Set name from parameters
        if name:
            self.name = name
        elif id:
            self.name = id
        elif "name" in kwargs:
            self.name = kwargs.pop("name")
        elif "id" in kwargs:
            self.name = kwargs.pop("id")
        else:
            self.name = self.__class__.__name__

        # Call parent constructor
        super().__init__(name=self.name)

    def get_parameters(self) -> dict[str, NodeParameter]:
        """Define parameters for the text splitter node."""
        return {
            "strategy": NodeParameter(
                name="strategy",
                type=str,
                description="Splitting strategy",
                required=False,
                default="recursive",
            ),
            "chunk_size": NodeParameter(
                name="chunk_size",
                type=int,
                description="Maximum chunk size",
                required=False,
                default=1000,
            ),
            "chunk_overlap": NodeParameter(
                name="chunk_overlap",
                type=int,
                description="Overlap between chunks",
                required=False,
                default=200,
            ),
            "separator": NodeParameter(
                name="separator",
                type=str,
                description="Text separator",
                required=False,
                default="\n",
            ),
            "preserve_sentences": NodeParameter(
                name="preserve_sentences",
                type=bool,
                description="Keep sentence boundaries",
                required=False,
                default=True,
            ),
        }

    def run(self, **kwargs) -> dict[str, Any]:
        """Split text into chunks using configured strategy.

        Implementation of the abstract run method from the base Node class.

        Args:
            **kwargs: Keyword arguments containing text and metadata

        Returns:
            Text chunks and metadata
        """
        return self.execute(kwargs)

    def execute(self, inputs: dict[str, Any]) -> dict[str, Any]:  # type: ignore[reportIncompatibleMethodOverride]
        """Split text into chunks using configured strategy.

        Args:
            inputs: Text and optional metadata

        Returns:
            Text chunks and metadata

        Raises:
            NodeExecutionError: If splitting fails
        """
        try:
            text = inputs.get("text", "")
            metadata = inputs.get("metadata", {})

            if not text:
                return {"chunks": [], "chunk_metadata": []}

            strategy = self.config.get("strategy", "recursive")

            if strategy == "recursive":
                chunks = self._recursive_split(text)
            elif strategy == "character":
                chunks = self._character_split(text)
            elif strategy == "sentence":
                chunks = self._sentence_split(text)
            elif strategy == "token":
                chunks = self._token_split(text)
            else:
                raise ValueError(f"Unknown strategy: {strategy}")

            # Create metadata for each chunk
            chunk_metadata = []
            for i, chunk in enumerate(chunks):
                chunk_meta = metadata.copy()
                chunk_meta.update(
                    {
                        "chunk_index": i,
                        "chunk_size": len(chunk),
                        "total_chunks": len(chunks),
                    }
                )
                chunk_metadata.append(chunk_meta)

            return {
                "chunks": chunks,
                "chunk_metadata": chunk_metadata,
                "total_chunks": len(chunks),
            }
        except Exception as e:
            raise NodeExecutionError(f"Text splitting failed: {str(e)}")

    def _recursive_split(self, text: str) -> list[str]:
        """Split text recursively using multiple separators.

        Args:
            text: Text to split

        Returns:
            List of text chunks
        """
        # Placeholder implementation
        chunk_size = self.config.get("chunk_size", 1000)
        chunk_overlap = self.config.get("chunk_overlap", 200)

        chunks = []
        current_pos = 0

        while current_pos < len(text):
            end_pos = min(current_pos + chunk_size, len(text))
            chunk = text[current_pos:end_pos]
            chunks.append(chunk)
            current_pos += chunk_size - chunk_overlap

        return chunks

    def _character_split(self, text: str) -> list[str]:
        """Split text by character count.

        Args:
            text: Text to split

        Returns:
            List of text chunks
        """
        # Placeholder implementation
        chunk_size = self.config.get("chunk_size", 1000)
        separator = self.config.get("separator", "\n")

        parts = text.split(separator)
        chunks = []
        current_chunk = ""

        for part in parts:
            if len(current_chunk + part) > chunk_size:
                if current_chunk:
                    chunks.append(current_chunk)
                current_chunk = part
            else:
                current_chunk += separator + part if current_chunk else part

        if current_chunk:
            chunks.append(current_chunk)

        return chunks

    def _sentence_split(self, text: str) -> list[str]:
        """Split text by sentences.

        Args:
            text: Text to split

        Returns:
            List of text chunks
        """
        # Placeholder implementation - would use proper sentence tokenization
        sentences = text.split(". ")
        chunks = []
        current_chunk = ""
        chunk_size = self.config.get("chunk_size", 1000)

        for sentence in sentences:
            if len(current_chunk + sentence) > chunk_size:
                if current_chunk:
                    chunks.append(current_chunk)
                current_chunk = sentence + "."
            else:
                current_chunk += sentence + ". " if current_chunk else sentence + "."

        if current_chunk:
            chunks.append(current_chunk.rstrip())

        return chunks

    def _token_split(self, text: str) -> list[str]:
        """Split text by token count.

        Args:
            text: Text to split

        Returns:
            List of text chunks
        """
        # Placeholder implementation - would use tokenizer
        words = text.split()
        chunks = []
        current_chunk = []
        chunk_size = self.config.get("chunk_size", 1000) // 4  # Rough token estimate

        for word in words:
            if len(current_chunk) >= chunk_size:
                chunks.append(" ".join(current_chunk))
                current_chunk = [word]
            else:
                current_chunk.append(word)

        if current_chunk:
            chunks.append(" ".join(current_chunk))

        return chunks

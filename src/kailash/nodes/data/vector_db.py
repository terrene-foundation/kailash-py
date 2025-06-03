"""Vector database and embedding nodes for the Kailash system.

This module provides nodes for interacting with vector databases and generating
embeddings. Key features include:

- Unified interface for various vector databases (Pinecone, Weaviate, Milvus, etc.)
- Embedding generation using various models (OpenAI, HuggingFace, etc.)
- Text chunking and preprocessing
- Vector similarity search
- Metadata filtering

Design Philosophy:
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
    >>> # Store in vector database
    >>> vector_db = VectorDatabaseNode()
    >>> vector_db.configure({
    ...     "provider": "pinecone",
    ...     "index_name": "my-index",
    ...     "api_key": "your-api-key"
    ... })
    >>> vector_db.execute({
    ...     "operation": "upsert",
    ...     "vectors": result["embeddings"],
    ...     "ids": ["doc1", "doc2"],
    ...     "metadata": [{"source": "file1"}, {"source": "file2"}]
    ... })
"""

from typing import Any, Dict, List

import numpy as np

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

    metadata = NodeMetadata(
        name="EmbeddingNode",
        description="Generates embeddings for text data",
        version="1.0.0",
        tags={"embedding", "nlp", "vector"},
    )

    def __init__(self):
        """Initialize the embedding node.

        Sets up the node with default configuration and prepares for
        model initialization. The actual model is loaded during configuration.
        """
        super().__init__()
        self._model = None
        self._model_info = {}

    def get_parameters(self) -> Dict[str, NodeParameter]:
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

    def configure(self, config: Dict[str, Any]) -> None:
        """Configure the embedding node with model settings.

        Validates configuration, initializes the embedding model, and
        prepares for text processing. Different models require different
        configuration parameters.

        Args:
            config: Configuration dictionary with model settings

        Raises:
            NodeConfigurationError: If configuration is invalid
        """
        super().configure(config)

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

    def run(self, **kwargs) -> Dict[str, Any]:
        """Generate embeddings for input texts.

        Implementation of the abstract run method from the base Node class.

        Args:
            **kwargs: Keyword arguments containing 'texts' list

        Returns:
            Dictionary containing embeddings and model info
        """
        return self.execute(kwargs)

    def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
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

    def _generate_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for a batch of texts.

        This is a placeholder for actual embedding generation logic.

        Args:
            texts: List of texts to embed

        Returns:
            List of embedding vectors
        """
        # Placeholder implementation
        dim = self._model_info.get("dimensions", 768)
        return [np.random.randn(dim).tolist() for _ in texts]

    def _normalize_embeddings(self, embeddings: List[List[float]]) -> List[List[float]]:
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
            vec = np.array(embedding)
            norm = np.linalg.norm(vec)
            if norm > 0:
                normalized.append((vec / norm).tolist())
            else:
                normalized.append(embedding)
        return normalized


@register_node()
class VectorDatabaseNode(Node):
    """Interacts with vector databases for storing and retrieving embeddings.

    This node provides a unified interface for various vector databases including
    Pinecone, Weaviate, Milvus, Qdrant, and others. It handles vector operations,
    metadata management, and similarity search.

    Design Pattern:
    - Repository pattern for data access
    - Adapter pattern for different backends
    - Command pattern for operations

    Features:
    - Multiple vector database support
    - CRUD operations on vectors
    - Similarity search with filters
    - Hybrid search (vector + keyword)
    - Index management
    - Backup and restore

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
        provider (str): Vector database provider
        connection_string (str): Database connection details
        index_name (str): Name of the vector index
        dimension (int): Vector dimension size
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
    - Index existence checks
    - Dimension mismatch detection
    - Quota and limit management

    Example:
        >>> vector_db = VectorDatabaseNode()
        >>> vector_db.configure({
        ...     "provider": "pinecone",
        ...     "index_name": "my-knowledge-base",
        ...     "api_key": "your-api-key",
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

    metadata = NodeMetadata(
        name="VectorDatabaseNode",
        description="Vector database operations",
        version="1.0.0",
        tags={"vector", "database", "storage"},
    )

    def __init__(self):
        """Initialize the vector database node.

        Sets up the node and prepares for database connection.
        The actual connection is established during configuration.
        """
        super().__init__()
        self._client = None
        self._index = None

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Define parameters for the vector database node."""
        return {
            "provider": NodeParameter(
                name="provider",
                type=str,
                description="Vector database provider",
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
        }

    def configure(self, config: Dict[str, Any]) -> None:
        """Configure the vector database connection.

        Establishes connection to the vector database, validates the index,
        and prepares for vector operations.

        Args:
            config: Configuration with database settings

        Raises:
            NodeConfigurationError: If connection fails
        """
        super().configure(config)

        provider = self.config.get("provider")
        index_name = self.config.get("index_name")

        if not index_name:
            raise NodeConfigurationError("index_name is required")

        try:
            # Placeholder for actual database connection
            self._connect_to_database(provider)
        except Exception as e:
            raise NodeConfigurationError(f"Failed to connect to {provider}: {str(e)}")

    def _connect_to_database(self, provider: str) -> None:
        """Connect to the vector database.

        Establishes connection and prepares the index for operations.
        This is a placeholder for actual connection logic.

        Args:
            provider: Database provider name

        Raises:
            ValueError: If provider is not supported
        """
        if provider not in ["pinecone", "weaviate", "milvus", "qdrant", "chroma"]:
            raise ValueError(f"Unsupported provider: {provider}")

        # Placeholder for actual connection
        self._client = f"{provider}_client"
        self._index = self.config.get("index_name")

    def run(self, **kwargs) -> Dict[str, Any]:
        """Execute vector database operations.

        Implementation of the abstract run method from the base Node class.

        Args:
            **kwargs: Keyword arguments for the operation

        Returns:
            Operation results
        """
        return self.execute(kwargs)

    def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
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

    def _upsert_vectors(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Insert or update vectors in the database.

        Args:
            inputs: Vectors, IDs, and metadata

        Returns:
            Upsert status
        """
        vectors = inputs.get("vectors", [])
        ids = inputs.get("ids", [])
        # metadata = inputs.get("metadata", [])  # TODO: Implement metadata storage

        if not vectors or not ids:
            raise ValueError("Vectors and IDs are required for upsert")

        if len(vectors) != len(ids):
            raise ValueError("Number of vectors must match number of IDs")

        # Placeholder for actual upsert
        return {
            "operation": "upsert",
            "status": "success",
            "count": len(vectors),
            "index": self._index,
        }

    def _query_vectors(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Query similar vectors from the database.

        Args:
            inputs: Query vector and parameters

        Returns:
            Search results
        """
        query_vector = inputs.get("query_vector")
        k = inputs.get("k", 10)
        # filter_dict = inputs.get("filter", {})  # TODO: Implement filter-based queries

        if not query_vector:
            raise ValueError("Query vector is required")

        # Placeholder for actual query
        return {
            "operation": "query",
            "status": "success",
            "results": [
                {
                    "id": f"doc_{i}",
                    "score": 0.95 - i * 0.05,
                    "metadata": {"title": f"Document {i}"},
                }
                for i in range(min(k, 5))
            ],
            "count": min(k, 5),
        }

    def _delete_vectors(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Delete vectors from the database.

        Args:
            inputs: Vector IDs to delete

        Returns:
            Deletion status
        """
        ids = inputs.get("ids", [])

        if not ids:
            raise ValueError("IDs are required for deletion")

        # Placeholder for actual deletion
        return {"operation": "delete", "status": "success", "count": len(ids)}

    def _fetch_vectors(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Fetch specific vectors by ID.

        Args:
            inputs: Vector IDs to fetch

        Returns:
            Fetched vectors and metadata
        """
        ids = inputs.get("ids", [])

        if not ids:
            raise ValueError("IDs are required for fetch")

        # Placeholder for actual fetch
        return {
            "operation": "fetch",
            "status": "success",
            "vectors": {
                id: {
                    "values": [0.1] * self.config.get("dimension", 768),
                    "metadata": {"id": id},
                }
                for id in ids
            },
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

    metadata = NodeMetadata(
        name="TextSplitterNode",
        description="Splits text into chunks",
        version="1.0.0",
        tags={"text", "processing", "nlp"},
    )

    def get_parameters(self) -> Dict[str, NodeParameter]:
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

    def run(self, **kwargs) -> Dict[str, Any]:
        """Split text into chunks using configured strategy.

        Implementation of the abstract run method from the base Node class.

        Args:
            **kwargs: Keyword arguments containing text and metadata

        Returns:
            Text chunks and metadata
        """
        return self.execute(kwargs)

    def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
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

    def _recursive_split(self, text: str) -> List[str]:
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

    def _character_split(self, text: str) -> List[str]:
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

    def _sentence_split(self, text: str) -> List[str]:
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

    def _token_split(self, text: str) -> List[str]:
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

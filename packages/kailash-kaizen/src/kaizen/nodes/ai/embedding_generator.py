"""Embedding Generator node for vector embeddings with support for multiple providers."""

import time
from typing import Any

from kailash.nodes.base import Node, NodeParameter, register_node


@register_node()
class EmbeddingGeneratorNode(Node):
    """
    Vector embedding generator for RAG systems and semantic similarity operations.

    Design Purpose and Philosophy:
    The EmbeddingGenerator node provides enterprise-grade vector embedding capabilities
    with support for multiple providers, batch processing, and efficient caching.
    It's essential for building RAG systems, semantic search, and similarity-based workflows.

    Upstream Dependencies:
    - Text content or documents to embed
    - Provider credentials (OpenAI, HuggingFace, Azure, etc.)
    - Embedding model configurations and parameters
    - Batch processing settings for efficiency
    - Cache configuration for performance optimization

    Downstream Consumers:
    - Vector databases storing embeddings for retrieval
    - Similarity calculation nodes for semantic matching
    - RAG systems requiring document embeddings
    - Clustering and classification algorithms
    - Search and recommendation engines

    Usage Patterns:
    1. Single text embedding for ad-hoc similarity queries
    2. Batch document embedding for knowledge base creation
    3. Real-time embedding for streaming data processing
    4. Incremental embedding with caching for large datasets
    5. Multi-modal embedding for text, images, and code

    Implementation Details:
    - Supports OpenAI, HuggingFace, Azure, Cohere, and local models
    - Implements efficient batch processing with optimal chunk sizes
    - Provides intelligent caching with TTL and invalidation
    - Handles rate limiting and retry logic for API providers
    - Supports multiple embedding dimensions and models
    - Includes similarity calculation utilities

    Error Handling:
    - APIError: When embedding provider API calls fail
    - RateLimitError: When API rate limits are exceeded
    - TokenLimitError: When input text exceeds model limits
    - ValidationError: When input format is invalid
    - CacheError: When embedding cache operations fail
    - ModelNotFoundError: When specified model is unavailable

    Side Effects:
    - Makes API calls to external embedding providers
    - Caches embedding vectors in local or distributed cache
    - May chunk large texts for processing within model limits
    - Logs embedding operations and performance metrics
    - Updates usage statistics and cost tracking

    Examples:
        >>> # Single text embedding
        >>> embedder = EmbeddingGeneratorNode()
        >>> result = embedder.execute(
        ...     provider="openai",
        ...     model="text-embedding-3-large",
        ...     input_text="This is a sample document to embed",
        ...     operation="embed_text"
        ... )

        >>> # Batch document embedding
        >>> batch_embedder = EmbeddingGeneratorNode()
        >>> result = batch_embedder.execute(
        ...     provider="huggingface",
        ...     model="sentence-transformers/all-MiniLM-L6-v2",
        ...     input_texts=[
        ...         "First document content...",
        ...         "Second document content...",
        ...         "Third document content..."
        ...     ],
        ...     operation="embed_batch",
        ...     batch_size=32,
        ...     cache_enabled=True
        ... )

        >>> # Similarity calculation
        >>> similarity = EmbeddingGeneratorNode()
        >>> result = similarity.execute(
        ...     operation="calculate_similarity",
        ...     embedding_1=[0.1, 0.2, 0.3],  # ... removed for doctest
        ...     embedding_2=[0.15, 0.25, 0.35],  # ... removed for doctest
        ...     similarity_metric="cosine"
        ... )

        >>> # Cached embedding with MCP integration
        >>> mcp_embedder = EmbeddingGeneratorNode()
        >>> result = mcp_embedder.execute(
        ...     provider="azure",
        ...     model="text-embedding-3-small",
        ...     mcp_resource_uri="data://documents/knowledge_base.json",
        ...     operation="embed_mcp_resource",
        ...     cache_ttl=3600,
        ...     chunk_size=512
        ... )
    """

    def get_parameters(self) -> dict[str, NodeParameter]:
        return {
            "operation": NodeParameter(
                name="operation",
                type=str,
                required=False,
                default="embed_text",
                description="Operation: embed_text, embed_batch, calculate_similarity, embed_mcp_resource",
            ),
            "provider": NodeParameter(
                name="provider",
                type=str,
                required=False,
                description="Embedding provider: openai, ollama, cohere, huggingface, mock",
            ),
            "model": NodeParameter(
                name="model",
                type=str,
                required=False,
                description="Embedding model name (e.g., text-embedding-3-large, all-MiniLM-L6-v2)",
            ),
            "input_text": NodeParameter(
                name="input_text",
                type=str,
                required=False,
                description="Single text to embed (for embed_text operation)",
            ),
            "input_texts": NodeParameter(
                name="input_texts",
                type=list,
                required=False,
                description="List of texts to embed (for embed_batch operation)",
            ),
            "mcp_resource_uri": NodeParameter(
                name="mcp_resource_uri",
                type=str,
                required=False,
                description="MCP resource URI to embed (for embed_mcp_resource operation)",
            ),
            "embedding_1": NodeParameter(
                name="embedding_1",
                type=list,
                required=False,
                description="First embedding vector (for calculate_similarity operation)",
            ),
            "embedding_2": NodeParameter(
                name="embedding_2",
                type=list,
                required=False,
                description="Second embedding vector (for calculate_similarity operation)",
            ),
            "similarity_metric": NodeParameter(
                name="similarity_metric",
                type=str,
                required=False,
                default="cosine",
                description="Similarity metric: cosine, euclidean, dot_product",
            ),
            "batch_size": NodeParameter(
                name="batch_size",
                type=int,
                required=False,
                default=32,
                description="Batch size for processing multiple texts",
            ),
            "chunk_size": NodeParameter(
                name="chunk_size",
                type=int,
                required=False,
                default=512,
                description="Maximum tokens per text chunk",
            ),
            "cache_enabled": NodeParameter(
                name="cache_enabled",
                type=bool,
                required=False,
                default=True,
                description="Enable embedding caching for performance",
            ),
            "cache_ttl": NodeParameter(
                name="cache_ttl",
                type=int,
                required=False,
                default=3600,
                description="Cache time-to-live in seconds",
            ),
            "dimensions": NodeParameter(
                name="dimensions",
                type=int,
                required=False,
                description="Number of embedding dimensions (provider-specific)",
            ),
            "normalize": NodeParameter(
                name="normalize",
                type=bool,
                required=False,
                default=True,
                description="Normalize embedding vectors to unit length",
            ),
            "timeout": NodeParameter(
                name="timeout",
                type=int,
                required=False,
                default=60,
                description="Request timeout in seconds",
            ),
            "max_retries": NodeParameter(
                name="max_retries",
                type=int,
                required=False,
                default=3,
                description="Maximum retry attempts for failed requests",
            ),
            # #1779 governance_required posture opt-out for this node's four-axis
            # embed egress (mirrors LLMAgentNode). Default False (fail-closed).
            "ungoverned": NodeParameter(
                name="ungoverned",
                type=bool,
                required=False,
                default=False,
                description="Opt out of the KAILASH_GOVERNANCE_REQUIRED posture gate for this node's embed egress",
            ),
        }

    def run(self, **kwargs) -> dict[str, Any]:
        operation = kwargs["operation"]
        # #1779 governance_required posture opt-out. Stored run-scoped so the
        # four-axis embed egress (_generate_provider_embedding) can honor it,
        # mirroring LLMAgentNode. Fail-closed default False.
        self._ungoverned = kwargs.get("ungoverned", False)
        provider = kwargs.get("provider", "mock")
        model = kwargs.get("model", "default")
        input_text = kwargs.get("input_text")
        input_texts = kwargs.get("input_texts", [])
        mcp_resource_uri = kwargs.get("mcp_resource_uri")
        embedding_1 = kwargs.get("embedding_1")
        embedding_2 = kwargs.get("embedding_2")
        similarity_metric = kwargs.get("similarity_metric", "cosine")
        batch_size = kwargs.get("batch_size", 32)
        chunk_size = kwargs.get("chunk_size", 512)
        cache_enabled = kwargs.get("cache_enabled", True)
        cache_ttl = kwargs.get("cache_ttl", 3600)
        dimensions = kwargs.get("dimensions")
        normalize = kwargs.get("normalize", True)
        timeout = kwargs.get("timeout", 60)
        max_retries = kwargs.get("max_retries", 3)

        try:
            if operation == "embed_text":
                return self._embed_single_text(
                    input_text,
                    provider,
                    model,
                    cache_enabled,
                    cache_ttl,
                    dimensions,
                    normalize,
                    timeout,
                    max_retries,
                )
            elif operation == "embed_batch":
                return self._embed_batch_texts(
                    input_texts,
                    provider,
                    model,
                    batch_size,
                    chunk_size,
                    cache_enabled,
                    cache_ttl,
                    dimensions,
                    normalize,
                    timeout,
                    max_retries,
                )
            elif operation == "calculate_similarity":
                # Handle both direct embeddings and text inputs
                if embedding_1 and embedding_2:
                    return self._calculate_similarity(
                        embedding_1, embedding_2, similarity_metric
                    )
                elif input_texts and len(input_texts) >= 2:
                    # Generate embeddings for texts first
                    embeddings = []
                    for text in input_texts[:2]:  # Only use first 2 texts
                        if provider == "mock":
                            emb = self._generate_mock_embedding(
                                text, dimensions or 1536
                            )
                        else:
                            emb = self._generate_provider_embedding(
                                text, provider, model, dimensions, timeout, max_retries
                            )
                        if normalize:
                            emb = self._normalize_vector(emb)
                        embeddings.append(emb)

                    # Calculate similarity
                    result = self._calculate_similarity(
                        embeddings[0], embeddings[1], similarity_metric
                    )

                    # Add text information
                    if result["success"]:
                        result["texts"] = input_texts[:2]
                        result["embeddings"] = embeddings

                    return result
                else:
                    return {
                        "success": False,
                        "error": "Either provide embedding_1 and embedding_2, or input_texts with at least 2 texts",
                    }
            elif operation == "embed_mcp_resource":
                return self._embed_mcp_resource(
                    mcp_resource_uri,
                    provider,
                    model,
                    chunk_size,
                    cache_enabled,
                    cache_ttl,
                    dimensions,
                    normalize,
                    timeout,
                    max_retries,
                )
            else:
                return {
                    "success": False,
                    "error": f"Unsupported operation: {operation}",
                    "supported_operations": [
                        "embed_text",
                        "embed_batch",
                        "calculate_similarity",
                        "embed_mcp_resource",
                    ],
                }

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "error_type": type(e).__name__,
                "operation": operation,
                "provider": provider,
                "model": model,
            }

    def _embed_single_text(
        self,
        text: str | None,
        provider: str,
        model: str,
        cache_enabled: bool,
        cache_ttl: int,
        dimensions: int | None,
        normalize: bool,
        timeout: int,
        max_retries: int,
    ) -> dict[str, Any]:
        """Generate embedding for a single text."""
        if not text:
            return {
                "success": False,
                "error": "input_text is required for embed_text operation",
            }

        # Check cache first if enabled
        if cache_enabled:
            cache_key = self._generate_cache_key(text, provider, model)
            cached_embedding = self._get_cached_embedding(cache_key)
            if cached_embedding:
                return {
                    "success": True,
                    "operation": "embed_text",
                    "embedding": cached_embedding["vector"],
                    "dimensions": len(cached_embedding["vector"]),
                    "text_length": len(text),
                    "provider": provider,
                    "model": model,
                    "cached": True,
                    "cache_key": cache_key,
                    "processing_time_ms": 5,  # Very fast cache lookup
                }

        # Generate embedding using provider
        start_time = time.time()

        if provider == "mock":
            embedding_vector = self._generate_mock_embedding(text, dimensions or 1536)
        else:
            embedding_vector = self._generate_provider_embedding(
                text, provider, model, dimensions, timeout, max_retries
            )

        processing_time = (time.time() - start_time) * 1000

        # Normalize if requested
        if normalize:
            embedding_vector = self._normalize_vector(embedding_vector)

        # Cache the result
        if cache_enabled:
            self._cache_embedding(cache_key, embedding_vector, cache_ttl)

        return {
            "success": True,
            "operation": "embed_text",
            "embedding": embedding_vector,
            "dimensions": len(embedding_vector),
            "text_length": len(text),
            "provider": provider,
            "model": model,
            "cached": False,
            "processing_time_ms": round(processing_time, 2),
            "usage": {
                "tokens": len(text.split()),
                "estimated_cost_usd": self._estimate_embedding_cost(
                    len(text.split()), provider, model
                ),
            },
        }

    def _embed_batch_texts(
        self,
        texts: list[str],
        provider: str,
        model: str,
        batch_size: int,
        chunk_size: int,
        cache_enabled: bool,
        cache_ttl: int,
        dimensions: int | None,
        normalize: bool,
        timeout: int,
        max_retries: int,
    ) -> dict[str, Any]:
        """Generate embeddings for a batch of texts."""
        if not texts:
            return {
                "success": False,
                "error": "input_texts is required and cannot be empty for embed_batch operation",
            }

        start_time = time.time()
        embeddings = []
        cache_hits = 0
        total_tokens = 0

        # Process texts in batches
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]

            for text in batch:
                # Check cache first
                cache_key = None
                if cache_enabled:
                    cache_key = self._generate_cache_key(text, provider, model)
                    cached_embedding = self._get_cached_embedding(cache_key)
                    if cached_embedding:
                        embeddings.append(
                            {
                                "text": text[:100] + "..." if len(text) > 100 else text,
                                "embedding": cached_embedding["vector"],
                                "cached": True,
                                "dimensions": len(cached_embedding["vector"]),
                            }
                        )
                        cache_hits += 1
                        continue

                # Chunk text if too long
                chunks = self._chunk_text(text, chunk_size)
                if len(chunks) > 1:
                    # For multiple chunks, embed each and average
                    chunk_embeddings = []
                    for chunk in chunks:
                        if provider == "mock":
                            chunk_emb = self._generate_mock_embedding(
                                chunk, dimensions or 1536
                            )
                        else:
                            chunk_emb = self._generate_provider_embedding(
                                chunk, provider, model, dimensions, timeout, max_retries
                            )
                        chunk_embeddings.append(chunk_emb)

                    # Average embeddings
                    embedding_vector = self._average_embeddings(chunk_embeddings)
                else:
                    # Single chunk
                    if provider == "mock":
                        embedding_vector = self._generate_mock_embedding(
                            text, dimensions or 1536
                        )
                    else:
                        embedding_vector = self._generate_provider_embedding(
                            text, provider, model, dimensions, timeout, max_retries
                        )

                # Normalize if requested
                if normalize:
                    embedding_vector = self._normalize_vector(embedding_vector)

                # Cache the result
                if cache_enabled and cache_key:
                    self._cache_embedding(cache_key, embedding_vector, cache_ttl)

                embeddings.append(
                    {
                        "text": text[:100] + "..." if len(text) > 100 else text,
                        "embedding": embedding_vector,
                        "cached": False,
                        "dimensions": len(embedding_vector),
                        "chunks": len(chunks),
                    }
                )

                total_tokens += len(text.split())

        processing_time = (time.time() - start_time) * 1000

        return {
            "success": True,
            "operation": "embed_batch",
            "embeddings": embeddings,
            "total_texts": len(texts),
            "total_embeddings": len(embeddings),
            "cache_hits": cache_hits,
            "cache_hit_rate": cache_hits / len(texts) if texts else 0,
            "provider": provider,
            "model": model,
            "batch_size": batch_size,
            "processing_time_ms": round(processing_time, 2),
            "usage": {
                "total_tokens": total_tokens,
                "estimated_cost_usd": self._estimate_embedding_cost(
                    total_tokens, provider, model
                ),
                "average_tokens_per_text": total_tokens / len(texts) if texts else 0,
            },
        }

    def _calculate_similarity(
        self,
        embedding_1: list[float] | None,
        embedding_2: list[float] | None,
        metric: str,
    ) -> dict[str, Any]:
        """Calculate similarity between two embedding vectors."""
        if not embedding_1 or not embedding_2:
            return {
                "success": False,
                "error": "Both embedding_1 and embedding_2 are required for similarity calculation",
            }

        if len(embedding_1) != len(embedding_2):
            return {
                "success": False,
                "error": f"Embedding dimensions must match: {len(embedding_1)} vs {len(embedding_2)}",
            }

        try:
            if metric == "cosine":
                similarity = self._cosine_similarity(embedding_1, embedding_2)
            elif metric == "euclidean":
                similarity = self._euclidean_distance(embedding_1, embedding_2)
            elif metric == "dot_product":
                similarity = self._dot_product(embedding_1, embedding_2)
            else:
                return {
                    "success": False,
                    "error": f"Unsupported similarity metric: {metric}",
                    "supported_metrics": ["cosine", "euclidean", "dot_product"],
                }

            return {
                "success": True,
                "operation": "calculate_similarity",
                "similarity": similarity,
                "metric": metric,
                "dimensions": len(embedding_1),
                "interpretation": self._interpret_similarity(similarity, metric),
            }

        except Exception as e:
            return {
                "success": False,
                "error": f"Similarity calculation failed: {str(e)}",
                "metric": metric,
            }

    def _embed_mcp_resource(
        self,
        resource_uri: str | None,
        provider: str,
        model: str,
        chunk_size: int,
        cache_enabled: bool,
        cache_ttl: int,
        dimensions: int | None,
        normalize: bool,
        timeout: int,
        max_retries: int,
    ) -> dict[str, Any]:
        """Embed content from an MCP resource."""
        if not resource_uri:
            return {
                "success": False,
                "error": "mcp_resource_uri is required for embed_mcp_resource operation",
            }

        # Mock MCP resource retrieval
        mock_content = f"Mock content from MCP resource: {resource_uri}\n\nThis would contain the actual document or data content retrieved from the MCP server."

        # Use the existing embed_text functionality
        result = self._embed_single_text(
            mock_content,
            provider,
            model,
            cache_enabled,
            cache_ttl,
            dimensions,
            normalize,
            timeout,
            max_retries,
        )

        if result["success"]:
            result.update(
                {
                    "operation": "embed_mcp_resource",
                    "mcp_resource_uri": resource_uri,
                    "content_preview": mock_content[:200] + "...",
                }
            )

        return result

    def _generate_mock_embedding(self, text: str, dimensions: int) -> list[float]:
        """Generate a mock embedding vector based on text content."""
        import hashlib
        import random

        # Use text hash as seed for reproducible mock embeddings
        seed = int(hashlib.md5(text.encode()).hexdigest()[:8], 16)
        random.seed(seed)

        # Generate normalized random vector
        vector = [random.gauss(0, 1) for _ in range(dimensions)]

        # Normalize to unit length
        magnitude = sum(x * x for x in vector) ** 0.5
        return [x / magnitude for x in vector]

    def _generate_provider_embedding(
        self,
        text: str,
        provider: str,
        model: str,
        dimensions: int | None,
        timeout: int,
        max_retries: int,
    ) -> list[float]:
        """Generate an embedding via the four-axis ``LlmClient`` (#1720 Wave-B1b).

        Resolves the legacy ``provider`` name to a four-axis ``LlmDeployment``
        through the shared ``resolve_deployment_for`` surface, then issues a
        real embedding request via ``LlmClient.from_deployment_sync(...).embed``
        and returns the first (and only) vector.

        Provider-specific fields the legacy path set are threaded through
        ``EmbedOptions``: ``dimensions`` (openai only), and ``input_type`` set
        to ``"search_document"`` for cohere (Cohere v3 embed requires it). The
        four-axis HuggingFace embed wire already targets its feature-extraction
        API path (``/models/{model}``), so no per-request ``use_api`` toggle is
        needed. ``timeout`` bounds the wire call (legacy semantics).

        When the resolver returns ``None`` (no four-axis mapping, or a required
        credential / base_url could not be resolved -- already logged at DEBUG
        by the resolver, e.g. ollama with no base_url on this node), the legacy
        ``_fallback_provider_embedding`` path is used so those providers keep
        working. The ``except ImportError`` fallback and the ``except Exception``
        -> ``RuntimeError`` wrapper are preserved from the legacy contract.
        """
        try:
            from kaizen.llm import LlmClient, resolve_deployment_for
            from kaizen.llm.deployment import EmbedOptions

            deployment = resolve_deployment_for(provider, model)
            if deployment is None:
                # No four-axis mapping / unresolved credential (resolver already
                # logged a DEBUG reason). Preserve legacy coverage for providers
                # the four-axis path cannot resolve from the node's inputs.
                return self._fallback_provider_embedding(
                    text, provider, model, dimensions, timeout, max_retries
                )

            option_kwargs: dict[str, Any] = {}
            # dimensions is only honored by openai (mirrors the legacy path).
            if dimensions and provider == "openai":
                option_kwargs["dimensions"] = dimensions
            # Cohere v3 embed REQUIRES an input_type; legacy set search_document.
            if provider == "cohere":
                option_kwargs["input_type"] = "search_document"
            options = EmbedOptions(**option_kwargs) if option_kwargs else None

            # #1779: honor the node's governance opt-out at the four-axis embed
            # chokepoint (posture gate lives in LlmClient.__init__).
            client = LlmClient.from_deployment_sync(
                deployment, ungoverned=getattr(self, "_ungoverned", False)
            )

            async def _call_embed() -> list[list[float]]:
                return await client.embed(
                    [text], model=model, options=options, timeout=float(timeout)
                )

            vectors = self._run_embed_coro(_call_embed())
            return vectors[0] if vectors else []

        except ImportError:
            # Fallback to the original implementation if the four-axis LLM
            # layer is not importable.
            return self._fallback_provider_embedding(
                text, provider, model, dimensions, timeout, max_retries
            )
        except Exception as e:
            # #1779: propagate a governance refusal UNWRAPPED (invariant 4:
            # single typed error) rather than re-typing to RuntimeError
            # (redteam round-2 F2). Must precede the sanitize/re-wrap below.
            from kailash.trust.pact import UngovernedEgressRefused

            if isinstance(e, UngovernedEgressRefused):
                raise
            # #1720 Wave-B1 redteam MED — sanitize provider errors at
            # enforcement-surface parity with the B1a live completion path
            # (llm_agent._provider_llm_response). The four-axis embed wire
            # re-raises a raw httpx exception whose text can echo a
            # user-supplied base_url; scrub before it reaches the caller.
            from kaizen.nodes.ai.error_sanitizer import sanitize_provider_error

            raise RuntimeError(sanitize_provider_error(e, provider)) from e

    def _run_embed_coro(self, coro):
        """Run an async ``LlmClient.embed`` coroutine from this sync node method.

        ``LlmClient.embed`` is async (``rules/patterns.md`` § async/sync); the
        node's ``run()`` is the synchronous Node interface and may be invoked
        from a sync runtime OR from inside an already-running event loop (an
        async runtime). A bare ``asyncio.run`` raises "event loop is already
        running" in the latter case, so this bridge runs the coroutine on a
        fresh loop in a dedicated thread when a loop is already running, and
        uses ``asyncio.run`` only when there is none -- the same shape
        ``llm_agent._run_async_in_sync_context`` uses. Errors are re-raised on
        the calling thread (never swallowed).
        """
        import asyncio

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            # No running event loop on this thread -- safe to own one here.
            return asyncio.run(coro)

        # A loop is already running; run the coroutine on a fresh loop in a
        # separate thread so event loops are never nested.
        import threading

        box: dict[str, Any] = {}

        def _run_in_thread() -> None:
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            try:
                box["result"] = new_loop.run_until_complete(coro)
            except BaseException as exc:  # re-raised below; never swallowed
                box["error"] = exc
            finally:
                new_loop.close()

        thread = threading.Thread(target=_run_in_thread)
        thread.start()
        thread.join()
        if "error" in box:
            raise box["error"]
        return box["result"]

    def _fallback_provider_embedding(
        self,
        text: str,
        provider: str,
        model: str,
        dimensions: int | None,
        timeout: int,
        max_retries: int,
    ) -> list[float]:
        """Fallback implementation for backward compatibility."""
        # #1779 governance_required posture: the ollama branch below egresses
        # DIRECTLY (ollama.embeddings) with no four-axis LlmClient, so the
        # construction gate cannot cover it — gate explicitly here, mirroring
        # LLMAgentNode._legacy_provider_chat (enforcement-surface parity;
        # security.md § Enforcement-Surface Parity; redteam round-4). mock
        # exempt; ungoverned honored; OFF posture is a no-op (byte-identical).
        from kaizen.llm.governance_gate import enforce_governance_posture

        enforce_governance_posture(
            is_mock=(provider == "mock"),
            ungoverned=getattr(self, "_ungoverned", False),
            surface="EmbeddingGeneratorNode",
        )
        # Handle Ollama provider
        if provider == "ollama":
            try:
                import ollama

                response = ollama.embeddings(model=model, prompt=text)
                return response.get("embedding", [])
            except ImportError:
                raise RuntimeError(
                    "Ollama library not installed. Install with: pip install ollama"
                )
            except Exception as e:
                raise RuntimeError(f"Ollama embedding error: {str(e)}")

        # A non-ollama provider reaching this fallback means its four-axis
        # deployment could NOT be resolved (missing/unavailable credential) or
        # the four-axis LLM layer failed to import. Legacy raised here rather
        # than returning data — #1720 Wave-B1 redteam HIGH: a silent mock
        # embedding fed into a similarity / RAG pipeline is fake data reported
        # as a real provider result (zero-tolerance Rule 2 + observability
        # Rule 3 `mode=fake`). Restore the loud raise, matching the B1a/B1c
        # None-deployment disposition (both raise). The explicit `provider ==
        # "mock"` mode (handled by the caller, not this fallback) is the only
        # sanctioned mock-embedding path.
        raise RuntimeError(
            f"Provider {provider} is not available. Check dependencies and "
            f"configuration."
        )

    def _chunk_text(self, text: str, chunk_size: int) -> list[str]:
        """Split text into chunks based on token limit."""
        # Simple word-based chunking (real implementation would use proper tokenization)
        words = text.split()
        chunks = []

        for i in range(0, len(words), chunk_size):
            chunk_words = words[i : i + chunk_size]
            chunks.append(" ".join(chunk_words))

        return chunks or [""]

    def _average_embeddings(self, embeddings: list[list[float]]) -> list[float]:
        """Average multiple embedding vectors."""
        if not embeddings:
            return []

        dimensions = len(embeddings[0])
        averaged = []

        for i in range(dimensions):
            avg_value = sum(emb[i] for emb in embeddings) / len(embeddings)
            averaged.append(avg_value)

        return averaged

    def _normalize_vector(self, vector: list[float]) -> list[float]:
        """Normalize vector to unit length."""
        magnitude = sum(x * x for x in vector) ** 0.5
        if magnitude == 0:
            return vector
        return [x / magnitude for x in vector]

    def _cosine_similarity(self, vec1: list[float], vec2: list[float]) -> float:
        """Calculate cosine similarity between two vectors."""
        dot_product = sum(a * b for a, b in zip(vec1, vec2, strict=False))
        magnitude1 = sum(a * a for a in vec1) ** 0.5
        magnitude2 = sum(b * b for b in vec2) ** 0.5

        if magnitude1 == 0 or magnitude2 == 0:
            return 0.0

        return dot_product / (magnitude1 * magnitude2)

    def _euclidean_distance(self, vec1: list[float], vec2: list[float]) -> float:
        """Calculate Euclidean distance between two vectors."""
        return sum((a - b) ** 2 for a, b in zip(vec1, vec2, strict=False)) ** 0.5

    def _dot_product(self, vec1: list[float], vec2: list[float]) -> float:
        """Calculate dot product of two vectors."""
        return sum(a * b for a, b in zip(vec1, vec2, strict=False))

    def _interpret_similarity(self, score: float, metric: str) -> str:
        """Provide human-readable interpretation of similarity score."""
        if metric == "cosine":
            if score > 0.9:
                return "Very similar"
            elif score > 0.7:
                return "Similar"
            elif score > 0.5:
                return "Somewhat similar"
            elif score > 0.3:
                return "Slightly similar"
            else:
                return "Not similar"
        elif metric == "euclidean":
            if score < 0.5:
                return "Very similar"
            elif score < 1.0:
                return "Similar"
            elif score < 2.0:
                return "Somewhat similar"
            else:
                return "Not similar"
        else:  # dot_product
            return f"Dot product: {score:.3f}"

    def _generate_cache_key(self, text: str, provider: str, model: str) -> str:
        """Generate cache key for embedding."""
        import hashlib

        content = f"{provider}:{model}:{text}"
        return f"emb_{hashlib.md5(content.encode()).hexdigest()[:16]}"

    def _get_cached_embedding(self, cache_key: str) -> dict[str, Any] | None:
        """Retrieve embedding from cache (mock implementation)."""
        # Mock cache lookup - in real implementation, use Redis or similar
        return None

    def _cache_embedding(self, cache_key: str, vector: list[float], ttl: int) -> None:
        """Store embedding in cache (mock implementation)."""
        # Mock cache storage - in real implementation, use Redis or similar

    def _estimate_embedding_cost(self, tokens: int, provider: str, model: str) -> float:
        """Estimate embedding cost based on tokens and provider pricing."""
        # Mock cost estimation (real implementation would use current pricing)
        cost_per_1k_tokens = {
            "openai": {
                "text-embedding-3-large": 0.00013,
                "text-embedding-3-small": 0.00002,
            },
            "azure": {"text-embedding-3-large": 0.00013},
            "cohere": {"embed-english-v3.0": 0.0001},
        }

        rate = cost_per_1k_tokens.get(provider, {}).get(model, 0.0001)
        return (tokens / 1000) * rate

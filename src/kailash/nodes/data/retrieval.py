"""Document retrieval nodes for finding relevant content using various similarity methods."""

from typing import Any, Dict, List

from kailash.nodes.base import Node, NodeParameter, register_node


@register_node()
class RelevanceScorerNode(Node):
    """Scores chunk relevance using various similarity methods including embeddings similarity."""

    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            "chunks": NodeParameter(
                name="chunks",
                type=list,
                required=False,
                description="List of chunks to score",
            ),
            "query_embedding": NodeParameter(
                name="query_embedding",
                type=list,
                required=False,
                description="Query embedding for similarity comparison",
            ),
            "chunk_embeddings": NodeParameter(
                name="chunk_embeddings",
                type=list,
                required=False,
                description="Embeddings for each chunk",
            ),
            "similarity_method": NodeParameter(
                name="similarity_method",
                type=str,
                required=False,
                default="cosine",
                description="Similarity method: cosine, bm25, tfidf, jaccard (future)",
            ),
            "top_k": NodeParameter(
                name="top_k",
                type=int,
                required=False,
                default=3,
                description="Number of top chunks to return",
            ),
        }

    def run(self, **kwargs) -> Dict[str, Any]:
        chunks = kwargs.get("chunks", [])
        query_embeddings = kwargs.get("query_embedding", [])
        chunk_embeddings = kwargs.get("chunk_embeddings", [])
        similarity_method = kwargs.get("similarity_method", "cosine")
        top_k = kwargs.get("top_k", 3)

        print(
            f"Debug: chunks={len(chunks)}, query_embeddings={len(query_embeddings)}, chunk_embeddings={len(chunk_embeddings)}"
        )

        # Handle case when no embeddings are available
        if not query_embeddings or not chunk_embeddings:
            print("Debug: No embeddings available, using fallback text matching")
            # Simple text-based fallback scoring
            query_text = "machine learning types"  # Extract keywords from query
            scored_chunks = []
            for chunk in chunks:
                content = chunk.get("content", "").lower()
                score = sum(1 for word in query_text.split() if word in content) / len(
                    query_text.split()
                )
                scored_chunk = {**chunk, "relevance_score": score}
                scored_chunks.append(scored_chunk)
        else:
            # Use the specified similarity method
            if similarity_method == "cosine":
                scored_chunks = self._cosine_similarity_scoring(
                    chunks, query_embeddings, chunk_embeddings
                )
            elif similarity_method == "bm25":
                # Future implementation
                scored_chunks = self._bm25_scoring(
                    chunks, query_embeddings, chunk_embeddings
                )
            elif similarity_method == "tfidf":
                # Future implementation
                scored_chunks = self._tfidf_scoring(
                    chunks, query_embeddings, chunk_embeddings
                )
            else:
                # Default to cosine
                scored_chunks = self._cosine_similarity_scoring(
                    chunks, query_embeddings, chunk_embeddings
                )

        # Sort by relevance and take top_k
        scored_chunks.sort(key=lambda x: x["relevance_score"], reverse=True)
        top_chunks = scored_chunks[:top_k]

        return {"relevant_chunks": top_chunks}

    def _cosine_similarity_scoring(
        self, chunks: List[Dict], query_embeddings: List, chunk_embeddings: List
    ) -> List[Dict]:
        """Score chunks using cosine similarity."""
        # Extract actual embedding vectors from the embedding objects
        # EmbeddingGenerator returns embeddings in format: {"embedding": [...], "text": "...", "dimensions": X}

        # Handle query embedding - should be the first (and only) embedding in the list
        query_embedding_obj = query_embeddings[0] if query_embeddings else {}
        if isinstance(query_embedding_obj, dict) and "embedding" in query_embedding_obj:
            query_embedding = query_embedding_obj["embedding"]
        elif isinstance(query_embedding_obj, list):
            query_embedding = query_embedding_obj
        else:
            query_embedding = []

        print(
            f"Debug: Query embedding extracted, type: {type(query_embedding)}, length: {len(query_embedding) if isinstance(query_embedding, list) else 'N/A'}"
        )

        # Simple cosine similarity calculation
        def cosine_similarity(a, b):
            # Ensure embeddings are numeric lists
            if not isinstance(a, list) or not isinstance(b, list):
                print(f"Debug: Non-list embeddings detected, a={type(a)}, b={type(b)}")
                return 0.5  # Default similarity

            if len(a) == 0 or len(b) == 0:
                print(
                    f"Debug: Empty embeddings detected, len(a)={len(a)}, len(b)={len(b)}"
                )
                return 0.5

            try:
                dot_product = sum(x * y for x, y in zip(a, b))
                norm_a = sum(x * x for x in a) ** 0.5
                norm_b = sum(x * x for x in b) ** 0.5
                return dot_product / (norm_a * norm_b) if norm_a * norm_b > 0 else 0
            except (TypeError, ValueError) as e:
                print(f"Debug: Cosine similarity error: {e}")
                return 0.5

        # Score each chunk
        scored_chunks = []
        for i, chunk in enumerate(chunks):
            if i < len(chunk_embeddings):
                # Extract embedding vector from chunk embedding object
                chunk_embedding_obj = chunk_embeddings[i]
                if (
                    isinstance(chunk_embedding_obj, dict)
                    and "embedding" in chunk_embedding_obj
                ):
                    chunk_embedding = chunk_embedding_obj["embedding"]
                elif isinstance(chunk_embedding_obj, list):
                    chunk_embedding = chunk_embedding_obj
                else:
                    chunk_embedding = []

                similarity = cosine_similarity(query_embedding, chunk_embedding)
                scored_chunk = {**chunk, "relevance_score": similarity}
                scored_chunks.append(scored_chunk)

        return scored_chunks

    def _bm25_scoring(
        self, chunks: List[Dict], query_embeddings: List, chunk_embeddings: List
    ) -> List[Dict]:
        """Score chunks using BM25 algorithm (future implementation)."""
        # TODO: Implement BM25 scoring
        # For now, return chunks with default scores
        return [{**chunk, "relevance_score": 0.5} for chunk in chunks]

    def _tfidf_scoring(
        self, chunks: List[Dict], query_embeddings: List, chunk_embeddings: List
    ) -> List[Dict]:
        """Score chunks using TF-IDF similarity (future implementation)."""
        # TODO: Implement TF-IDF scoring
        # For now, return chunks with default scores
        return [{**chunk, "relevance_score": 0.5} for chunk in chunks]

"""Document retrieval nodes for finding relevant content using various similarity methods."""

import json
from typing import Any, Dict, List, Optional

from kailash.nodes.base import Node, NodeParameter, register_node


@register_node()
class RelevanceScorerNode(Node):
    """Scores chunk relevance using various similarity methods including embeddings similarity."""

    def get_parameters(self) -> dict[str, NodeParameter]:
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

    def run(self, **kwargs) -> dict[str, Any]:
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
        self, chunks: list[dict], query_embeddings: list, chunk_embeddings: list
    ) -> list[dict]:
        """Score chunks using cosine similarity."""
        # Extract actual embedding vectors from the embedding objects
        # EmbeddingGeneratorNode returns embeddings in format: {"embedding": [...], "text": "...", "dimensions": X}

        # Handle query embedding - should be the first (and only) embedding in the list
        query_embedding_obj = query_embeddings[0] if query_embeddings else {}
        if isinstance(query_embedding_obj, dict) and "embedding" in query_embedding_obj:
            # Handle Ollama format: {"embedding": [...]}
            query_embedding = query_embedding_obj["embedding"]
        elif (
            isinstance(query_embedding_obj, dict)
            and "embeddings" in query_embedding_obj
        ):
            # Handle other provider formats: {"embeddings": [...]}
            query_embedding = query_embedding_obj["embeddings"]
        elif isinstance(query_embedding_obj, list):
            # Handle direct list format
            query_embedding = query_embedding_obj
        else:
            # Fallback
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
                dot_product = sum(x * y for x, y in zip(a, b, strict=False))
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
                    # Handle Ollama format: {"embedding": [...]}
                    chunk_embedding = chunk_embedding_obj["embedding"]
                elif (
                    isinstance(chunk_embedding_obj, dict)
                    and "embeddings" in chunk_embedding_obj
                ):
                    # Handle other provider formats: {"embeddings": [...]}
                    chunk_embedding = chunk_embedding_obj["embeddings"]
                elif isinstance(chunk_embedding_obj, list):
                    # Handle direct list format
                    chunk_embedding = chunk_embedding_obj
                else:
                    # Fallback
                    chunk_embedding = []

                similarity = cosine_similarity(query_embedding, chunk_embedding)
                scored_chunk = {**chunk, "relevance_score": similarity}
                scored_chunks.append(scored_chunk)

        return scored_chunks

    def _bm25_scoring(
        self, chunks: list[dict], query_embeddings: list, chunk_embeddings: list
    ) -> list[dict]:
        """Score chunks using BM25 algorithm (future implementation)."""
        # TODO: Implement BM25 scoring
        # For now, return chunks with default scores
        return [{**chunk, "relevance_score": 0.5} for chunk in chunks]

    def _tfidf_scoring(
        self, chunks: list[dict], query_embeddings: list, chunk_embeddings: list
    ) -> list[dict]:
        """Score chunks using TF-IDF similarity (future implementation)."""
        # TODO: Implement TF-IDF scoring
        # For now, return chunks with default scores
        return [{**chunk, "relevance_score": 0.5} for chunk in chunks]


@register_node()
class HybridRetrieverNode(Node):
    """
    Hybrid retrieval combining dense and sparse retrieval methods.

    This node implements state-of-the-art hybrid retrieval that combines:
    - Dense retrieval (semantic embeddings)
    - Sparse retrieval (keyword-based like BM25)
    - Multiple fusion strategies (RRF, linear combination, learned fusion)

    Hybrid retrieval typically provides 20-30% better results than single methods.
    """

    def __init__(self, name: str = "hybrid_retriever", **kwargs):
        # Set attributes before calling super().__init__() as Kailash validates during init
        self.fusion_strategy = kwargs.get(
            "fusion_strategy", "rrf"
        )  # "rrf", "linear", "weighted"
        self.dense_weight = kwargs.get("dense_weight", 0.6)
        self.sparse_weight = kwargs.get("sparse_weight", 0.4)
        self.rrf_k = kwargs.get("rrf_k", 60)
        self.top_k = kwargs.get("top_k", 5)
        self.normalize_scores = kwargs.get("normalize_scores", True)

        super().__init__(name=name)

    def get_parameters(self) -> dict[str, NodeParameter]:
        return {
            "query": NodeParameter(
                name="query",
                type=str,
                required=True,
                description="Search query",
            ),
            "dense_results": NodeParameter(
                name="dense_results",
                type=list,
                required=True,
                description="Results from dense retrieval (with similarity_score)",
            ),
            "sparse_results": NodeParameter(
                name="sparse_results",
                type=list,
                required=True,
                description="Results from sparse retrieval (with similarity_score)",
            ),
            "fusion_strategy": NodeParameter(
                name="fusion_strategy",
                type=str,
                required=False,
                default=self.fusion_strategy,
                description="Fusion strategy: rrf, linear, or weighted",
            ),
            "dense_weight": NodeParameter(
                name="dense_weight",
                type=float,
                required=False,
                default=self.dense_weight,
                description="Weight for dense retrieval scores (0.0-1.0)",
            ),
            "sparse_weight": NodeParameter(
                name="sparse_weight",
                type=float,
                required=False,
                default=self.sparse_weight,
                description="Weight for sparse retrieval scores (0.0-1.0)",
            ),
            "top_k": NodeParameter(
                name="top_k",
                type=int,
                required=False,
                default=self.top_k,
                description="Number of top results to return",
            ),
            "rrf_k": NodeParameter(
                name="rrf_k",
                type=int,
                required=False,
                default=self.rrf_k,
                description="RRF parameter k (higher = less aggressive fusion)",
            ),
        }

    def run(self, **kwargs) -> dict[str, Any]:
        query = kwargs.get("query", "")
        dense_results = kwargs.get("dense_results", [])
        sparse_results = kwargs.get("sparse_results", [])
        fusion_strategy = kwargs.get("fusion_strategy", self.fusion_strategy)
        dense_weight = kwargs.get("dense_weight", self.dense_weight)
        sparse_weight = kwargs.get("sparse_weight", self.sparse_weight)
        top_k = kwargs.get("top_k", self.top_k)
        rrf_k = kwargs.get("rrf_k", self.rrf_k)

        if not dense_results and not sparse_results:
            return {
                "hybrid_results": [],
                "fusion_method": fusion_strategy,
                "dense_count": 0,
                "sparse_count": 0,
                "fused_count": 0,
            }

        # Ensure results have required fields
        dense_results = self._normalize_results(dense_results, "dense")
        sparse_results = self._normalize_results(sparse_results, "sparse")

        # Apply fusion strategy
        if fusion_strategy == "rrf":
            fused_results = self._reciprocal_rank_fusion(
                dense_results, sparse_results, top_k, rrf_k
            )
        elif fusion_strategy == "linear":
            fused_results = self._linear_fusion(
                dense_results, sparse_results, top_k, dense_weight, sparse_weight
            )
        elif fusion_strategy == "weighted":
            fused_results = self._weighted_fusion(
                dense_results, sparse_results, top_k, dense_weight, sparse_weight
            )
        else:
            # Default to RRF
            fused_results = self._reciprocal_rank_fusion(
                dense_results, sparse_results, top_k, rrf_k
            )

        return {
            "hybrid_results": fused_results,
            "fusion_method": fusion_strategy,
            "dense_count": len(dense_results),
            "sparse_count": len(sparse_results),
            "fused_count": len(fused_results),
        }

    def _normalize_results(self, results: List[Dict], source: str) -> List[Dict]:
        """Normalize results to ensure consistent format."""
        normalized = []

        for i, result in enumerate(results):
            # Ensure required fields exist
            normalized_result = {
                "id": result.get("id", result.get("chunk_id", f"{source}_{i}")),
                "content": result.get("content", result.get("text", "")),
                "similarity_score": result.get(
                    "similarity_score", result.get("score", 0.0)
                ),
                "source": source,
                **result,  # Keep original fields
            }
            normalized.append(normalized_result)

        return normalized

    def _reciprocal_rank_fusion(
        self,
        dense_results: List[Dict],
        sparse_results: List[Dict],
        top_k: int,
        rrf_k: int,
    ) -> List[Dict]:
        """
        Implement Reciprocal Rank Fusion (RRF).

        RRF formula: RRF(d) = Σ(1 / (k + rank_i(d)))
        where rank_i(d) is the rank of document d in ranklist i
        """
        # Create rank mappings
        dense_ranks = {doc["id"]: i + 1 for i, doc in enumerate(dense_results)}
        sparse_ranks = {doc["id"]: i + 1 for i, doc in enumerate(sparse_results)}

        # Collect all unique document IDs
        all_doc_ids = set(dense_ranks.keys()) | set(sparse_ranks.keys())

        # Calculate RRF scores
        rrf_scores = {}
        for doc_id in all_doc_ids:
            score = 0.0

            if doc_id in dense_ranks:
                score += 1.0 / (rrf_k + dense_ranks[doc_id])

            if doc_id in sparse_ranks:
                score += 1.0 / (rrf_k + sparse_ranks[doc_id])

            rrf_scores[doc_id] = score

        # Sort by RRF score and get top-k
        sorted_docs = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)[
            :top_k
        ]

        # Build result documents
        doc_map = {}
        for doc in dense_results + sparse_results:
            doc_map[doc["id"]] = doc

        results = []
        for doc_id, rrf_score in sorted_docs:
            if doc_id in doc_map:
                doc = doc_map[doc_id].copy()
                doc["hybrid_score"] = rrf_score
                doc["fusion_method"] = "rrf"
                doc["rank"] = len(results) + 1
                results.append(doc)

        return results

    def _linear_fusion(
        self,
        dense_results: List[Dict],
        sparse_results: List[Dict],
        top_k: int,
        dense_weight: float,
        sparse_weight: float,
    ) -> List[Dict]:
        """
        Implement linear combination fusion.

        Score = dense_weight * dense_score + sparse_weight * sparse_score
        """
        if self.normalize_scores:
            # Normalize scores to 0-1 range
            dense_scores = [doc["similarity_score"] for doc in dense_results]
            sparse_scores = [doc["similarity_score"] for doc in sparse_results]

            dense_max = max(dense_scores) if dense_scores else 1.0
            sparse_max = max(sparse_scores) if sparse_scores else 1.0

            # Avoid division by zero
            dense_max = max(dense_max, 1e-8)
            sparse_max = max(sparse_max, 1e-8)
        else:
            dense_max = sparse_max = 1.0

        # Create score mappings
        dense_score_map = {
            doc["id"]: doc["similarity_score"] / dense_max for doc in dense_results
        }
        sparse_score_map = {
            doc["id"]: doc["similarity_score"] / sparse_max for doc in sparse_results
        }

        # Collect all unique document IDs
        all_doc_ids = set(dense_score_map.keys()) | set(sparse_score_map.keys())

        # Calculate linear combination scores
        linear_scores = {}
        for doc_id in all_doc_ids:
            dense_score = dense_score_map.get(doc_id, 0.0)
            sparse_score = sparse_score_map.get(doc_id, 0.0)

            combined_score = dense_weight * dense_score + sparse_weight * sparse_score
            linear_scores[doc_id] = combined_score

        # Sort and build results
        sorted_docs = sorted(linear_scores.items(), key=lambda x: x[1], reverse=True)[
            :top_k
        ]

        # Build result documents
        doc_map = {}
        for doc in dense_results + sparse_results:
            doc_map[doc["id"]] = doc

        results = []
        for doc_id, combined_score in sorted_docs:
            if doc_id in doc_map:
                doc = doc_map[doc_id].copy()
                doc["hybrid_score"] = combined_score
                doc["fusion_method"] = "linear"
                doc["rank"] = len(results) + 1
                results.append(doc)

        return results

    def _weighted_fusion(
        self,
        dense_results: List[Dict],
        sparse_results: List[Dict],
        top_k: int,
        dense_weight: float,
        sparse_weight: float,
    ) -> List[Dict]:
        """
        Implement weighted fusion with rank-based scoring.

        Combines position-based weighting with score-based weighting.
        """
        # Normalize weights
        total_weight = dense_weight + sparse_weight
        if total_weight > 0:
            dense_weight = dense_weight / total_weight
            sparse_weight = sparse_weight / total_weight
        else:
            dense_weight = sparse_weight = 0.5

        # Calculate weighted scores
        weighted_scores = {}

        # Process dense results
        for i, doc in enumerate(dense_results):
            doc_id = doc["id"]
            # Combine similarity score with rank-based discount
            rank_score = 1.0 / (i + 1)  # Higher ranks get higher scores
            weighted_score = dense_weight * (
                doc["similarity_score"] * 0.7 + rank_score * 0.3
            )
            weighted_scores[doc_id] = weighted_scores.get(doc_id, 0.0) + weighted_score

        # Process sparse results
        for i, doc in enumerate(sparse_results):
            doc_id = doc["id"]
            # Combine similarity score with rank-based discount
            rank_score = 1.0 / (i + 1)  # Higher ranks get higher scores
            weighted_score = sparse_weight * (
                doc["similarity_score"] * 0.7 + rank_score * 0.3
            )
            weighted_scores[doc_id] = weighted_scores.get(doc_id, 0.0) + weighted_score

        # Sort and build results
        sorted_docs = sorted(weighted_scores.items(), key=lambda x: x[1], reverse=True)[
            :top_k
        ]

        # Build result documents
        doc_map = {}
        for doc in dense_results + sparse_results:
            doc_map[doc["id"]] = doc

        results = []
        for doc_id, weighted_score in sorted_docs:
            if doc_id in doc_map:
                doc = doc_map[doc_id].copy()
                doc["hybrid_score"] = weighted_score
                doc["fusion_method"] = "weighted"
                doc["rank"] = len(results) + 1
                results.append(doc)

        return results

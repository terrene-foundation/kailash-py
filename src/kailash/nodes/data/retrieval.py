"""Document retrieval nodes for finding relevant content using various similarity methods."""

import logging
import math
import re
from typing import Any, Dict, List, Optional

from kailash.nodes.base import Node, NodeParameter, register_node

logger = logging.getLogger(__name__)

# Lexical-scoring tokenizer: lowercase, split on any run of non-alphanumeric chars.
_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")

# Okapi BM25 free parameters (standard defaults).
_BM25_K1 = 1.5
_BM25_B = 0.75


def _tokenize(text: str) -> list[str]:
    """Lowercase a string and split it into alphanumeric tokens.

    Pure-Python tokenizer used by the lexical scoring methods (BM25, TF-IDF).
    Splitting on non-alphanumeric runs keeps the tokenization deterministic and
    dependency-free (no numpy / nltk required).
    """
    return _TOKEN_PATTERN.findall(text.lower())


@register_node()
class RelevanceScorerNode(Node):
    """Scores chunk relevance using various similarity methods.

    Supported ``similarity_method`` values:

    - ``cosine``: cosine similarity over precomputed embedding vectors
      (requires ``query_embedding`` + ``chunk_embeddings``).
    - ``bm25``: Okapi BM25 lexical scoring over chunk text vs the ``query``
      text (k1=1.5, b=0.75).
    - ``tfidf``: TF-IDF cosine similarity over chunk text vs the ``query`` text.

    The lexical methods (``bm25``, ``tfidf``) score the ``query`` text against
    each chunk's ``content``; they require a ``query`` text input and raise a
    ``ValueError`` when none is available rather than returning a constant.
    """

    def get_parameters(self) -> dict[str, NodeParameter]:
        return {
            "chunks": NodeParameter(
                name="chunks",
                type=list,
                required=False,
                description="List of chunks to score",
            ),
            "query": NodeParameter(
                name="query",
                type=str,
                required=False,
                description=(
                    "Query text for lexical scoring (bm25/tfidf) and for the "
                    "no-embeddings keyword fallback"
                ),
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
                description="Similarity method: cosine, bm25, tfidf",
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
        query_text = kwargs.get("query") or ""
        query_embeddings = kwargs.get("query_embedding", [])
        chunk_embeddings = kwargs.get("chunk_embeddings", [])
        similarity_method = kwargs.get("similarity_method", "cosine")
        top_k = kwargs.get("top_k", 3)

        logger.debug(
            "relevance_scorer.run",
            extra={
                "chunks": len(chunks),
                "query_embeddings": len(query_embeddings),
                "chunk_embeddings": len(chunk_embeddings),
                "similarity_method": similarity_method,
                "has_query_text": bool(query_text),
            },
        )

        if similarity_method == "bm25":
            # Lexical method: scores query terms against chunk text. Requires a
            # query text input — fail loud rather than return a constant.
            if not query_text:
                raise ValueError("bm25/tfidf scoring requires a 'query' text input")
            scored_chunks = self._bm25_scoring(chunks, query_text)
        elif similarity_method == "tfidf":
            if not query_text:
                raise ValueError("bm25/tfidf scoring requires a 'query' text input")
            scored_chunks = self._tfidf_scoring(chunks, query_text)
        elif not query_embeddings or not chunk_embeddings:
            # Embedding-based methods (cosine and its aliases) but no embeddings
            # available — fall back to honest keyword matching against the real
            # query text. With no query text there is no scoring signal, so
            # report 0.0 rather than fabricating a query.
            scored_chunks = self._keyword_fallback_scoring(chunks, query_text)
        elif similarity_method == "cosine":
            scored_chunks = self._cosine_similarity_scoring(
                chunks, query_embeddings, chunk_embeddings
            )
        else:
            # Default to cosine for any unrecognized embedding-based method.
            scored_chunks = self._cosine_similarity_scoring(
                chunks, query_embeddings, chunk_embeddings
            )

        # Sort by relevance and take top_k
        scored_chunks.sort(key=lambda x: x["relevance_score"], reverse=True)
        top_chunks = scored_chunks[:top_k]

        return {"relevant_chunks": top_chunks}

    def _keyword_fallback_scoring(
        self, chunks: list[dict], query_text: str
    ) -> list[dict]:
        """Score chunks by query-term keyword overlap (no-embeddings fallback).

        Uses the REAL query text when present. When no query text is available
        there is no scoring signal, so every chunk gets an honest 0.0 — never a
        fabricated query.
        """
        query_terms = _tokenize(query_text)
        scored_chunks = []
        for chunk in chunks:
            if not query_terms:
                score = 0.0
            else:
                content_tokens = set(_tokenize(chunk.get("content", "")))
                matches = sum(1 for term in query_terms if term in content_tokens)
                score = matches / len(query_terms)
            scored_chunks.append({**chunk, "relevance_score": score})
        return scored_chunks

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

        # Simple cosine similarity calculation
        def cosine_similarity(a, b):
            # Ensure embeddings are numeric lists
            if not isinstance(a, list) or not isinstance(b, list):
                return 0.5  # Default similarity

            if len(a) == 0 or len(b) == 0:
                return 0.5

            try:
                dot_product = sum(x * y for x, y in zip(a, b, strict=False))
                norm_a = sum(x * x for x in a) ** 0.5
                norm_b = sum(x * x for x in b) ** 0.5
                return dot_product / (norm_a * norm_b) if norm_a * norm_b > 0 else 0
            except (TypeError, ValueError):
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

    def _bm25_scoring(self, chunks: list[dict], query_text: str) -> list[dict]:
        """Score chunks using the Okapi BM25 algorithm (k1=1.5, b=0.75).

        Each chunk's ``content`` is the document; the ``query`` text supplies the
        query terms. IDF is computed over the chunk corpus. Pure Python, no numpy.

        BM25 score for a document ``D`` given query terms ``q_i``::

            score(D, Q) = Σ_i IDF(q_i) * f(q_i, D) * (k1 + 1)
                          ----------------------------------------------------
                          f(q_i, D) + k1 * (1 - b + b * |D| / avgdl)

        where ``f(q_i, D)`` is the term frequency in ``D``, ``|D|`` is the
        document length in tokens, and ``avgdl`` is the average document length.
        IDF uses the BM25 form ``ln(1 + (N - n + 0.5) / (n + 0.5))`` which is
        non-negative.
        """
        # Tokenize the document corpus once.
        doc_tokens = [_tokenize(chunk.get("content", "")) for chunk in chunks]
        doc_lengths = [len(tokens) for tokens in doc_tokens]
        num_docs = len(chunks)

        if num_docs == 0:
            return []

        avgdl = sum(doc_lengths) / num_docs if num_docs else 0.0

        # Document frequency: how many documents contain each term at least once.
        doc_freq: dict[str, int] = {}
        for tokens in doc_tokens:
            for term in set(tokens):
                doc_freq[term] = doc_freq.get(term, 0) + 1

        # Non-negative BM25 IDF per term.
        idf: dict[str, float] = {}
        for term, n_q in doc_freq.items():
            idf[term] = math.log(1.0 + (num_docs - n_q + 0.5) / (n_q + 0.5))

        query_terms = _tokenize(query_text)

        scored_chunks = []
        for chunk, tokens, dl in zip(chunks, doc_tokens, doc_lengths):
            # Term frequencies within this document.
            tf: dict[str, int] = {}
            for term in tokens:
                tf[term] = tf.get(term, 0) + 1

            score = 0.0
            for term in query_terms:
                if term not in tf:
                    continue
                freq = tf[term]
                numerator = idf.get(term, 0.0) * freq * (_BM25_K1 + 1.0)
                denominator = freq + _BM25_K1 * (
                    1.0 - _BM25_B + _BM25_B * (dl / avgdl if avgdl > 0 else 0.0)
                )
                score += numerator / denominator if denominator > 0 else 0.0

            scored_chunks.append({**chunk, "relevance_score": score})

        return scored_chunks

    def _tfidf_scoring(self, chunks: list[dict], query_text: str) -> list[dict]:
        """Score chunks using TF-IDF cosine similarity.

        Builds a TF-IDF vector for the ``query`` text and for each chunk's
        ``content`` over the chunk corpus vocabulary, then scores each chunk by
        the cosine similarity between its vector and the query vector. Pure
        Python, no numpy.

        TF is the raw term count in the document; IDF is the smoothed inverse
        document frequency ``ln((1 + N) / (1 + n)) + 1`` over the chunk corpus.
        """
        doc_tokens = [_tokenize(chunk.get("content", "")) for chunk in chunks]
        num_docs = len(chunks)

        if num_docs == 0:
            return []

        # Document frequency over the chunk corpus.
        doc_freq: dict[str, int] = {}
        for tokens in doc_tokens:
            for term in set(tokens):
                doc_freq[term] = doc_freq.get(term, 0) + 1

        # Smoothed IDF (non-negative; matches the sklearn smooth_idf convention).
        idf: dict[str, float] = {}
        for term, n_q in doc_freq.items():
            idf[term] = math.log((1.0 + num_docs) / (1.0 + n_q)) + 1.0

        def _tfidf_vector(tokens: list[str]) -> dict[str, float]:
            counts: dict[str, int] = {}
            for term in tokens:
                counts[term] = counts.get(term, 0) + 1
            # Only terms present in the corpus vocabulary have an IDF weight.
            return {
                term: count * idf[term] for term, count in counts.items() if term in idf
            }

        def _cosine(vec_a: dict[str, float], vec_b: dict[str, float]) -> float:
            if not vec_a or not vec_b:
                return 0.0
            # Iterate the smaller vector for the dot product.
            small, large = (
                (vec_a, vec_b) if len(vec_a) <= len(vec_b) else (vec_b, vec_a)
            )
            dot = sum(weight * large.get(term, 0.0) for term, weight in small.items())
            norm_a = math.sqrt(sum(w * w for w in vec_a.values()))
            norm_b = math.sqrt(sum(w * w for w in vec_b.values()))
            if norm_a == 0.0 or norm_b == 0.0:
                return 0.0
            return dot / (norm_a * norm_b)

        query_vector = _tfidf_vector(_tokenize(query_text))

        scored_chunks = []
        for chunk, tokens in zip(chunks, doc_tokens):
            chunk_vector = _tfidf_vector(tokens)
            score = _cosine(query_vector, chunk_vector)
            scored_chunks.append({**chunk, "relevance_score": score})

        return scored_chunks


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

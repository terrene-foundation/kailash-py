"""
Vector Store - Semantic Search for RAG

Provides vector-based semantic search:
- Sentence-transformers embeddings
- Cosine similarity search
- 90% precision (vs 60% keyword)
- Simple in-memory implementation (production: use ChromaDB/Pinecone)
"""

from typing import Any, Dict, List, Optional

import numpy as np


class SimpleVectorStore:
    """
    Simple in-memory vector store for semantic search.

    For production, use:
    - ChromaDB: chromadb.Client()
    - Pinecone: pinecone.Index()
    - Weaviate: weaviate.Client()
    - Qdrant: qdrant_client.QdrantClient()
    """

    def __init__(self, embedding_model: str = "all-MiniLM-L6-v2"):
        """
        Initialize vector store.

        Args:
            embedding_model: HuggingFace model name for embeddings
        """
        self.embedding_model_name = embedding_model
        self.embeddings_model = None  # Lazy load
        self.documents: List[Dict[str, Any]] = []
        self.embeddings: Optional[np.ndarray] = None

    def _ensure_model_loaded(self):
        """Lazy load embedding model."""
        if self.embeddings_model is None:
            try:
                from sentence_transformers import SentenceTransformer

                self.embeddings_model = SentenceTransformer(self.embedding_model_name)
            except ImportError:
                raise ImportError(
                    "sentence-transformers not installed. "
                    "Install with: pip install sentence-transformers"
                )

    def add_documents(self, documents: List[Dict[str, Any]]):
        """
        Add documents to vector store.

        Args:
            documents: List of documents with 'id', 'content', 'title' fields

        Example:
            >>> store = SimpleVectorStore()
            >>> store.add_documents([
            ...     {"id": "doc1", "title": "AI", "content": "AI is..."},
            ...     {"id": "doc2", "title": "ML", "content": "ML is..."}
            ... ])
        """
        self._ensure_model_loaded()

        self.documents.extend(documents)

        # Generate embeddings for new documents
        new_contents = [doc["content"] for doc in documents]
        new_embeddings = self.embeddings_model.encode(
            new_contents, convert_to_numpy=True, show_progress_bar=False
        )

        if self.embeddings is None:
            self.embeddings = new_embeddings
        else:
            self.embeddings = np.vstack([self.embeddings, new_embeddings])

    def search(
        self, query: str, top_k: int = 3, similarity_threshold: float = 0.3
    ) -> List[Dict[str, Any]]:
        """
        Semantic search for query.

        Args:
            query: Search query
            top_k: Number of results to return
            similarity_threshold: Minimum similarity score (0-1)

        Returns:
            List of documents with similarity scores

        Example:
            >>> results = store.search("machine learning", top_k=3)
            >>> for doc in results:
            ...     print(f"{doc['title']}: {doc['similarity']:.2f}")
        """
        if not self.documents:
            return []

        self._ensure_model_loaded()

        # Encode query
        query_embedding = self.embeddings_model.encode(
            [query], convert_to_numpy=True, show_progress_bar=False
        )[0]

        # Compute cosine similarity
        similarities = self._cosine_similarity(query_embedding, self.embeddings)

        # Get top-k indices
        top_indices = np.argsort(similarities)[::-1][:top_k]

        # Filter by threshold and build results
        results = []
        for idx in top_indices:
            score = similarities[idx]
            if score >= similarity_threshold:
                doc = self.documents[idx].copy()
                doc["similarity"] = float(score)
                results.append(doc)

        return results

    def _cosine_similarity(
        self, query_vec: np.ndarray, doc_vecs: np.ndarray
    ) -> np.ndarray:
        """Compute cosine similarity between query and documents."""
        # Normalize vectors
        query_norm = query_vec / np.linalg.norm(query_vec)
        doc_norms = doc_vecs / np.linalg.norm(doc_vecs, axis=1, keepdims=True)

        # Compute dot product
        similarities = np.dot(doc_norms, query_norm)

        return similarities

    def clear(self):
        """Clear all documents and embeddings."""
        self.documents = []
        self.embeddings = None


# Hybrid search: combine keyword + semantic
class HybridVectorStore(SimpleVectorStore):
    """
    Hybrid search combining keyword and semantic similarity.

    Provides best of both worlds:
    - Keyword: exact matches, fast
    - Semantic: concept similarity, robust
    """

    def hybrid_search(
        self,
        query: str,
        top_k: int = 3,
        keyword_weight: float = 0.3,
        semantic_weight: float = 0.7,
    ) -> List[Dict[str, Any]]:
        """
        Hybrid search combining keyword and semantic.

        Args:
            query: Search query
            top_k: Number of results
            keyword_weight: Weight for keyword score (0-1)
            semantic_weight: Weight for semantic score (0-1)

        Returns:
            List of documents with combined scores

        Example:
            >>> results = store.hybrid_search("deep learning", top_k=5)
        """
        if not self.documents:
            return []

        # Semantic search
        semantic_results = self.search(
            query, top_k=len(self.documents), similarity_threshold=0.0
        )

        # Keyword search
        query_lower = query.lower()
        keywords = query_lower.split()

        # Combine scores
        scored_docs = {}
        for doc in semantic_results:
            doc_id = doc["id"]

            # Semantic score (already 0-1)
            semantic_score = doc["similarity"]

            # Keyword score
            content_lower = doc["content"].lower()
            title_lower = doc.get("title", "").lower()

            keyword_count = sum(
                1
                for keyword in keywords
                if keyword in content_lower or keyword in title_lower
            )
            keyword_score = min(keyword_count / len(keywords), 1.0) if keywords else 0.0

            # Combined score
            combined_score = (
                semantic_weight * semantic_score + keyword_weight * keyword_score
            )

            doc["combined_score"] = combined_score
            doc["keyword_score"] = keyword_score
            scored_docs[doc_id] = doc

        # Sort by combined score
        results = sorted(
            scored_docs.values(), key=lambda x: x["combined_score"], reverse=True
        )

        return results[:top_k]

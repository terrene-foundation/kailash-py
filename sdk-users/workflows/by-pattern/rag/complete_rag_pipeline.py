#!/usr/bin/env python3
"""
Complete RAG Pipeline Example

Demonstrates a production-ready RAG system using the new advanced nodes:
- SemanticChunkerNode for intelligent document chunking
- HybridRetrieverNode for state-of-the-art retrieval
- Complete integration with embeddings and scoring

This example shows real-world usage patterns and best practices.
"""

import json
from pathlib import Path
from typing import Any, Dict, List

from kailash.nodes.data.retrieval import HybridRetrieverNode, RelevanceScorerNode

# Import the new advanced RAG nodes
from kailash.nodes.transform.chunkers import SemanticChunkerNode, StatisticalChunkerNode


class AdvancedRAGPipeline:
    """Production-ready RAG pipeline using advanced Kailash nodes."""

    def __init__(self, config: Dict[str, Any] = None):
        """Initialize the RAG pipeline with configuration."""
        self.config = config or self._get_default_config()

        # Initialize chunking nodes
        self.semantic_chunker = SemanticChunkerNode(
            chunk_size=self.config["chunking"]["semantic"]["chunk_size"],
            similarity_threshold=self.config["chunking"]["semantic"][
                "similarity_threshold"
            ],
            chunk_overlap=self.config["chunking"]["semantic"]["overlap"],
            window_size=self.config["chunking"]["semantic"]["window_size"],
        )

        self.statistical_chunker = StatisticalChunkerNode(
            chunk_size=self.config["chunking"]["statistical"]["chunk_size"],
            variance_threshold=self.config["chunking"]["statistical"][
                "variance_threshold"
            ],
            min_sentences_per_chunk=self.config["chunking"]["statistical"][
                "min_sentences"
            ],
            max_sentences_per_chunk=self.config["chunking"]["statistical"][
                "max_sentences"
            ],
        )

        # Initialize retrieval nodes
        self.hybrid_retriever = HybridRetrieverNode(
            fusion_strategy=self.config["retrieval"]["fusion_strategy"],
            dense_weight=self.config["retrieval"]["dense_weight"],
            sparse_weight=self.config["retrieval"]["sparse_weight"],
            top_k=self.config["retrieval"]["top_k"],
            rrf_k=self.config["retrieval"]["rrf_k"],
        )

        self.relevance_scorer = RelevanceScorerNode(
            similarity_method=self.config["scoring"]["similarity_method"],
            top_k=self.config["scoring"]["top_k"],
        )

        # Storage for processed documents
        self.document_chunks = []
        self.chunk_embeddings = []

    def _get_default_config(self) -> Dict[str, Any]:
        """Get default configuration for the RAG pipeline."""
        return {
            "chunking": {
                "semantic": {
                    "chunk_size": 1000,
                    "similarity_threshold": 0.75,
                    "overlap": 100,
                    "window_size": 3,
                },
                "statistical": {
                    "chunk_size": 800,
                    "variance_threshold": 0.5,
                    "min_sentences": 3,
                    "max_sentences": 15,
                },
            },
            "retrieval": {
                "fusion_strategy": "rrf",
                "dense_weight": 0.6,
                "sparse_weight": 0.4,
                "top_k": 5,
                "rrf_k": 60,
            },
            "scoring": {"similarity_method": "cosine", "top_k": 3},
        }

    def process_documents(
        self, documents: List[Dict[str, Any]], chunking_method: str = "semantic"
    ) -> Dict[str, Any]:
        """
        Process documents into chunks using advanced chunking.

        Args:
            documents: List of documents with 'content', 'id', and optional metadata
            chunking_method: "semantic" or "statistical"

        Returns:
            Dictionary with processing results and statistics
        """
        print(
            f"📄 Processing {len(documents)} documents with {chunking_method} chunking..."
        )

        all_chunks = []
        processing_stats = {
            "total_documents": len(documents),
            "total_chunks": 0,
            "avg_chunk_size": 0,
            "chunking_method": chunking_method,
            "documents_processed": [],
        }

        for doc in documents:
            doc_id = doc.get("id", f"doc_{len(all_chunks)}")
            content = doc.get("content", "")
            metadata = doc.get("metadata", {})

            # Add document metadata
            chunk_metadata = {
                "document_id": doc_id,
                "document_title": doc.get("title", ""),
                "processing_timestamp": self._get_timestamp(),
                **metadata,
            }

            # Choose chunking method
            if chunking_method == "semantic":
                # For semantic chunking, we'd normally use real embeddings
                # Here we simulate the process
                result = self.semantic_chunker.execute(
                    text=content, metadata=chunk_metadata
                )
            elif chunking_method == "statistical":
                result = self.statistical_chunker.execute(
                    text=content, metadata=chunk_metadata
                )
            else:
                raise ValueError(f"Unknown chunking method: {chunking_method}")

            doc_chunks = result["chunks"]
            all_chunks.extend(doc_chunks)

            # Update statistics
            doc_stats = {
                "document_id": doc_id,
                "original_length": len(content),
                "chunks_created": len(doc_chunks),
                "avg_chunk_length": (
                    sum(len(c["content"]) for c in doc_chunks) / len(doc_chunks)
                    if doc_chunks
                    else 0
                ),
            }
            processing_stats["documents_processed"].append(doc_stats)

            print(f"   ✅ {doc_id}: {len(doc_chunks)} chunks created")

        # Calculate overall statistics
        processing_stats["total_chunks"] = len(all_chunks)
        if all_chunks:
            processing_stats["avg_chunk_size"] = sum(
                len(c["content"]) for c in all_chunks
            ) / len(all_chunks)

        # Store chunks for retrieval
        self.document_chunks = all_chunks

        print(
            f"   📊 Total: {len(all_chunks)} chunks, avg size: {processing_stats['avg_chunk_size']:.0f} chars"
        )

        return {"chunks": all_chunks, "statistics": processing_stats}

    def simulate_retrieval_results(
        self, query: str, chunks: List[Dict]
    ) -> Dict[str, List[Dict]]:
        """
        Simulate dense and sparse retrieval results.
        In production, these would come from actual retrieval systems.
        """
        # Simulate dense retrieval (semantic similarity)
        # In practice, this would use vector similarity search
        dense_results = []
        for i, chunk in enumerate(chunks[:8]):  # Take top 8 for dense
            # Simulate similarity score based on keyword overlap
            query_words = set(query.lower().split())
            chunk_words = set(chunk["content"].lower().split())
            overlap = len(query_words & chunk_words)

            dense_score = min(0.5 + (overlap * 0.15), 1.0)

            dense_chunk = {
                "id": chunk["chunk_id"],
                "content": chunk["content"],
                "similarity_score": dense_score,
                "retrieval_method": "dense_semantic",
                **{k: v for k, v in chunk.items() if k not in ["chunk_id", "content"]},
            }
            dense_results.append(dense_chunk)

        # Sort by dense score
        dense_results.sort(key=lambda x: x["similarity_score"], reverse=True)
        dense_results = dense_results[:6]  # Top 6 dense results

        # Simulate sparse retrieval (keyword matching)
        sparse_results = []
        query_keywords = query.lower().split()

        for chunk in chunks:
            keyword_score = 0
            content_lower = chunk["content"].lower()

            for keyword in query_keywords:
                if keyword in content_lower:
                    # Score based on frequency and position
                    freq = content_lower.count(keyword)
                    keyword_score += freq * 0.2

            if keyword_score > 0:
                sparse_chunk = {
                    "id": chunk["chunk_id"],
                    "content": chunk["content"],
                    "similarity_score": min(keyword_score, 1.0),
                    "retrieval_method": "sparse_keyword",
                    **{
                        k: v
                        for k, v in chunk.items()
                        if k not in ["chunk_id", "content"]
                    },
                }
                sparse_results.append(sparse_chunk)

        # Sort by sparse score
        sparse_results.sort(key=lambda x: x["similarity_score"], reverse=True)
        sparse_results = sparse_results[:6]  # Top 6 sparse results

        return {"dense_results": dense_results, "sparse_results": sparse_results}

    def perform_hybrid_retrieval(
        self, query: str, dense_results: List[Dict], sparse_results: List[Dict]
    ) -> Dict[str, Any]:
        """Perform hybrid retrieval using the HybridRetrieverNode."""
        print(f"🔍 Performing hybrid retrieval for: '{query}'")
        print(
            f"   📊 Input: {len(dense_results)} dense + {len(sparse_results)} sparse results"
        )

        # Test different fusion strategies
        strategies = ["rrf", "linear", "weighted"]
        results = {}

        for strategy in strategies:
            print(f"   🔄 Testing {strategy.upper()} fusion...")

            result = self.hybrid_retriever.execute(
                query=query,
                dense_results=dense_results,
                sparse_results=sparse_results,
                fusion_strategy=strategy,
                top_k=self.config["retrieval"]["top_k"],
            )

            results[strategy] = result

            hybrid_results = result["hybrid_results"]
            print(f"      ✅ {strategy.upper()}: {len(hybrid_results)} results")

            if hybrid_results:
                top_result = hybrid_results[0]
                print(
                    f"      🥇 Top result: {top_result['id']} (score: {top_result.get('hybrid_score', 'N/A'):.4f})"
                )

        return results

    def perform_final_scoring(self, chunks: List[Dict], query: str) -> List[Dict]:
        """Perform final relevance scoring and ranking."""
        print("🎯 Performing final relevance scoring...")

        # Simulate embeddings for scoring
        # In production, these would be real embeddings
        query_embedding = [{"embedding": self._simulate_embedding(query)}]
        chunk_embeddings = [
            {"embedding": self._simulate_embedding(chunk["content"])}
            for chunk in chunks
        ]

        result = self.relevance_scorer.execute(
            chunks=chunks,
            query_embedding=query_embedding,
            chunk_embeddings=chunk_embeddings,
        )

        final_results = result["relevant_chunks"]
        print(f"   ✅ Final scoring: {len(final_results)} ranked results")

        return final_results

    def run_complete_pipeline(
        self,
        documents: List[Dict[str, Any]],
        query: str,
        chunking_method: str = "semantic",
    ) -> Dict[str, Any]:
        """
        Run the complete RAG pipeline from documents to final results.

        Args:
            documents: Input documents to process
            query: Search query
            chunking_method: "semantic" or "statistical"

        Returns:
            Complete pipeline results with all intermediate steps
        """
        print("\n🚀 Running Complete RAG Pipeline")
        print(f"   📝 Query: '{query}'")
        print(f"   📄 Documents: {len(documents)}")
        print(f"   🔧 Chunking: {chunking_method}")
        print("=" * 60)

        # Step 1: Document Processing and Chunking
        chunking_result = self.process_documents(documents, chunking_method)
        chunks = chunking_result["chunks"]

        # Step 2: Simulate Retrieval
        print("\n🔍 Step 2: Simulating Dense and Sparse Retrieval")
        retrieval_simulation = self.simulate_retrieval_results(query, chunks)
        dense_results = retrieval_simulation["dense_results"]
        sparse_results = retrieval_simulation["sparse_results"]

        # Step 3: Hybrid Fusion
        print("\n🔄 Step 3: Hybrid Retrieval Fusion")
        fusion_results = self.perform_hybrid_retrieval(
            query, dense_results, sparse_results
        )

        # Use RRF results for final scoring
        best_fusion = fusion_results["rrf"]["hybrid_results"]

        # Step 4: Final Scoring
        print("\n🎯 Step 4: Final Relevance Scoring")
        final_results = self.perform_final_scoring(best_fusion, query)

        # Compile complete results
        pipeline_result = {
            "query": query,
            "chunking_method": chunking_method,
            "chunking_stats": chunking_result["statistics"],
            "retrieval_stats": {
                "dense_count": len(dense_results),
                "sparse_count": len(sparse_results),
                "fusion_methods_tested": list(fusion_results.keys()),
            },
            "final_results": final_results,
            "pipeline_config": self.config,
        }

        # Print final summary
        print("\n📋 Pipeline Summary:")
        print(f"   📊 Documents processed: {len(documents)}")
        print(f"   🧩 Chunks created: {len(chunks)}")
        print(f"   🔍 Dense results: {len(dense_results)}")
        print(f"   🔍 Sparse results: {len(sparse_results)}")
        print(f"   🎯 Final results: {len(final_results)}")

        return pipeline_result

    def _simulate_embedding(self, text: str) -> List[float]:
        """Simulate embedding generation for demonstration."""
        # Simple hash-based embedding simulation
        import hashlib

        # Create a simple deterministic "embedding" based on text content
        text_hash = hashlib.md5(text.lower().encode()).hexdigest()

        # Convert to floating point vector
        embedding = []
        for i in range(0, min(len(text_hash), 10), 2):
            val = int(text_hash[i : i + 2], 16) / 255.0
            embedding.append(val)

        # Pad to fixed size
        while len(embedding) < 5:
            embedding.append(0.0)

        return embedding[:5]

    def _get_timestamp(self) -> str:
        """Get current timestamp."""
        from datetime import datetime

        return datetime.now().isoformat()


def create_sample_documents() -> List[Dict[str, Any]]:
    """Create sample documents for testing."""
    return [
        {
            "id": "ai_overview",
            "title": "Introduction to Artificial Intelligence",
            "content": """
            Artificial Intelligence (AI) is a branch of computer science that aims to create
            intelligent machines capable of performing tasks that typically require human
            intelligence. These tasks include learning, reasoning, problem-solving, perception,
            and language understanding.

            Machine learning is a subset of AI that focuses on algorithms that can learn from
            data without being explicitly programmed. Deep learning, a subset of machine learning,
            uses artificial neural networks with multiple layers to model and understand complex
            patterns in data.

            Common applications of AI include natural language processing, computer vision,
            robotics, and autonomous systems. The field has seen rapid advancement in recent
            years, particularly in areas like large language models and generative AI.
            """,
            "metadata": {
                "category": "overview",
                "complexity": "beginner",
                "domain": "artificial_intelligence",
            },
        },
        {
            "id": "ml_algorithms",
            "title": "Machine Learning Algorithms",
            "content": """
            Machine learning algorithms can be broadly categorized into three types: supervised
            learning, unsupervised learning, and reinforcement learning.

            Supervised learning algorithms learn from labeled training data to make predictions
            on new, unseen data. Examples include linear regression, decision trees, random forests,
            and support vector machines. These algorithms are used for classification and regression tasks.

            Unsupervised learning algorithms work with unlabeled data to discover hidden patterns
            or structures. Clustering algorithms like K-means group similar data points together,
            while dimensionality reduction techniques like PCA help visualize high-dimensional data.

            Reinforcement learning involves an agent learning to make decisions through interaction
            with an environment, receiving rewards or penalties for its actions. This approach is
            used in game playing, robotics, and autonomous systems.
            """,
            "metadata": {
                "category": "algorithms",
                "complexity": "intermediate",
                "domain": "machine_learning",
            },
        },
        {
            "id": "deep_learning",
            "title": "Deep Learning and Neural Networks",
            "content": """
            Deep learning is a specialized subset of machine learning that uses artificial neural
            networks with multiple layers (hence "deep") to learn complex patterns in data. These
            networks are inspired by the structure and function of the human brain.

            Convolutional Neural Networks (CNNs) are particularly effective for image processing
            tasks. They use convolutional layers to detect features like edges, shapes, and textures
            in images. CNNs have revolutionized computer vision applications.

            Recurrent Neural Networks (RNNs) and their variants like LSTM and GRU are designed
            for sequential data processing. They maintain memory of previous inputs, making them
            ideal for natural language processing, time series analysis, and speech recognition.

            Transformer architectures, introduced in the "Attention is All You Need" paper, have
            become the foundation for modern language models like GPT and BERT. They use self-attention
            mechanisms to process sequences in parallel, leading to significant improvements in efficiency
            and performance.
            """,
            "metadata": {
                "category": "deep_learning",
                "complexity": "advanced",
                "domain": "neural_networks",
            },
        },
        {
            "id": "nlp_applications",
            "title": "Natural Language Processing Applications",
            "content": """
            Natural Language Processing (NLP) is a field of AI that focuses on the interaction
            between computers and human language. It combines computational linguistics with
            machine learning and deep learning to help computers understand, interpret, and
            generate human language.

            Modern NLP applications include chatbots and virtual assistants that can engage in
            natural conversations with users. Language translation services use neural machine
            translation to convert text between different languages with high accuracy.

            Sentiment analysis tools can determine the emotional tone of text, making them valuable
            for social media monitoring and customer feedback analysis. Text summarization systems
            can automatically generate concise summaries of long documents.

            Large language models like GPT, BERT, and their variants have achieved remarkable
            performance on a wide range of NLP tasks. These models are pre-trained on vast amounts
            of text data and can be fine-tuned for specific applications.
            """,
            "metadata": {
                "category": "applications",
                "complexity": "intermediate",
                "domain": "natural_language_processing",
            },
        },
    ]


def main():
    """Run the complete RAG pipeline example."""
    print("🚀 Advanced RAG Pipeline with Kailash SDK")
    print("=" * 60)

    # Create sample documents
    documents = create_sample_documents()

    # Initialize pipeline with custom configuration
    config = {
        "chunking": {
            "semantic": {
                "chunk_size": 600,
                "similarity_threshold": 0.7,
                "overlap": 80,
                "window_size": 2,
            },
            "statistical": {
                "chunk_size": 500,
                "variance_threshold": 0.4,
                "min_sentences": 2,
                "max_sentences": 10,
            },
        },
        "retrieval": {
            "fusion_strategy": "rrf",
            "dense_weight": 0.65,
            "sparse_weight": 0.35,
            "top_k": 4,
            "rrf_k": 50,
        },
        "scoring": {"similarity_method": "cosine", "top_k": 3},
    }

    pipeline = AdvancedRAGPipeline(config)

    # Test queries
    test_queries = [
        "What are neural networks and deep learning?",
        "How do machine learning algorithms work?",
        "What are the applications of natural language processing?",
    ]

    # Run pipeline for each query
    for i, query in enumerate(test_queries):
        print(f"\n{'='*60}")
        print(f"🔍 TEST {i+1}: {query}")
        print(f"{'='*60}")

        # Test both chunking methods
        for method in ["semantic", "statistical"]:
            print(f"\n📋 Using {method.upper()} chunking:")
            print("-" * 40)

            result = pipeline.run_complete_pipeline(
                documents=documents, query=query, chunking_method=method
            )

            # Display final results
            print(f"\n🎯 Final Results for '{query}':")
            for j, chunk in enumerate(result["final_results"]):
                content_preview = (
                    chunk["content"][:100] + "..."
                    if len(chunk["content"]) > 100
                    else chunk["content"]
                )
                score = chunk.get("relevance_score", "N/A")
                print(
                    f"   {j+1}. Score: {score:.4f if isinstance(score, float) else score}"
                )
                print(f"      Content: {content_preview}")
                print(f"      Source: {chunk.get('document_id', 'Unknown')}")

            print()

    print("✅ Advanced RAG Pipeline demonstration completed!")
    print("\nThis example showcases:")
    print("  🧩 Semantic and Statistical chunking strategies")
    print("  🔄 Hybrid retrieval with multiple fusion methods")
    print("  🎯 Advanced relevance scoring and ranking")
    print("  📊 Comprehensive pipeline statistics")
    print("  ⚙️  Configurable parameters for production use")


if __name__ == "__main__":
    main()

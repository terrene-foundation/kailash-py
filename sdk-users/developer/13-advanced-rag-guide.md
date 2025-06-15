# Advanced RAG Implementation Guide

## Overview

This guide provides comprehensive instructions for implementing production-ready Retrieval-Augmented Generation (RAG) systems using Kailash SDK's advanced nodes: `SemanticChunkerNode`, `StatisticalChunkerNode`, and `HybridRetrieverNode`.

**🎯 For Enterprise RAG:** The SDK also includes a complete RAG ecosystem with 40+ specialized nodes at `from kailash.nodes.rag import *`. See [20-comprehensive-rag-guide.md](20-comprehensive-rag-guide.md) for the full enterprise toolkit.

## Quick Start

### Basic RAG Pipeline

```python
from kailash.nodes.transform.chunkers import SemanticChunkerNode
from kailash.nodes.data.retrieval import HybridRetrieverNode, RelevanceScorerNode
from kailash.nodes.ai.embedding_generator import EmbeddingGeneratorNode

# 1. Initialize components
embedder = EmbeddingGeneratorNode(provider="ollama", model="nomic-embed-text")
chunker = SemanticChunkerNode(chunk_size=1000, similarity_threshold=0.75)
retriever = HybridRetrieverNode(fusion_strategy="rrf", top_k=5)
scorer = RelevanceScorerNode(top_k=3)

# 2. Process documents
document = "Your document content here..."
chunking_result = chunker.run(text=document)
chunks = chunking_result["chunks"]

# 3. Simulate retrieval (replace with your actual retrieval system)
query = "What is machine learning?"
dense_results = your_vector_search(query, top_k=10)
sparse_results = your_keyword_search(query, top_k=10)

# 4. Perform hybrid retrieval
hybrid_result = retriever.run(
    query=query,
    dense_results=dense_results,
    sparse_results=sparse_results
)

# 5. Final ranking
final_results = scorer.run(
    chunks=hybrid_result["hybrid_results"],
    query_embedding=embedder.run(input_texts=[query])["embeddings"],
    chunk_embeddings=chunk_embeddings
)
```

## Choosing the Right Chunking Strategy

### Decision Matrix

| Document Type | Content Structure | Recommended Strategy | Key Parameters |
|---------------|-------------------|---------------------|----------------|
| **Technical Manuals** | Highly structured | Statistical | `variance_threshold=0.6`, `window_size=3` |
| **Research Papers** | Section-based | Statistical | `variance_threshold=0.7`, `min_sentences=4` |
| **Narrative Text** | Flowing topics | Semantic | `similarity_threshold=0.75`, `chunk_size=800` |
| **News Articles** | Topic-focused | Semantic | `similarity_threshold=0.8`, `overlap=100` |
| **Legal Documents** | Clause-based | Statistical | `variance_threshold=0.8`, `max_sentences=10` |
| **General Content** | Mixed | Semantic | Default parameters |

### Testing Both Strategies

```python
def evaluate_chunking_strategies(document: str, test_queries: List[str]):
    """Always test both strategies before committing."""
    
    semantic_chunker = SemanticChunkerNode(chunk_size=1000, similarity_threshold=0.75)
    statistical_chunker = StatisticalChunkerNode(chunk_size=1000, variance_threshold=0.5)
    
    semantic_result = semantic_chunker.run(text=document)
    statistical_result = statistical_chunker.run(text=document)
    
    # Evaluate quality with your specific use case
    semantic_quality = evaluate_retrieval_quality(semantic_result["chunks"], test_queries)
    statistical_quality = evaluate_retrieval_quality(statistical_result["chunks"], test_queries)
    
    if semantic_quality > statistical_quality:
        return "semantic", semantic_result["chunks"]
    else:
        return "statistical", statistical_result["chunks"]
```

## Production RAG Pipeline

### Complete Implementation

```python
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from kailash.nodes.transform.chunkers import SemanticChunkerNode, StatisticalChunkerNode
from kailash.nodes.data.retrieval import HybridRetrieverNode, RelevanceScorerNode

@dataclass
class RAGConfig:
    """Configuration for RAG pipeline."""
    # Chunking settings
    chunking_strategy: str = "semantic"  # "semantic" or "statistical"
    chunk_size: int = 1000
    chunk_overlap: int = 100
    similarity_threshold: float = 0.75
    variance_threshold: float = 0.5
    
    # Retrieval settings
    fusion_strategy: str = "rrf"  # "rrf", "linear", "weighted"
    dense_weight: float = 0.6
    sparse_weight: float = 0.4
    retrieval_top_k: int = 10
    
    # Final scoring
    final_top_k: int = 5
    similarity_method: str = "cosine"

class ProductionRAGPipeline:
    """Production-ready RAG pipeline with comprehensive error handling."""
    
    def __init__(self, config: RAGConfig = None):
        self.config = config or RAGConfig()
        self._init_components()
        self.document_chunks = []
        self.chunk_embeddings = []
    
    def _init_components(self):
        """Initialize all pipeline components."""
        # Chunking nodes
        if self.config.chunking_strategy == "semantic":
            self.chunker = SemanticChunkerNode(
                chunk_size=self.config.chunk_size,
                similarity_threshold=self.config.similarity_threshold,
                chunk_overlap=self.config.chunk_overlap
            )
        else:
            self.chunker = StatisticalChunkerNode(
                chunk_size=self.config.chunk_size,
                variance_threshold=self.config.variance_threshold
            )
        
        # Retrieval components
        self.hybrid_retriever = HybridRetrieverNode(
            fusion_strategy=self.config.fusion_strategy,
            dense_weight=self.config.dense_weight,
            sparse_weight=self.config.sparse_weight,
            top_k=self.config.retrieval_top_k
        )
        
        self.relevance_scorer = RelevanceScorerNode(
            similarity_method=self.config.similarity_method,
            top_k=self.config.final_top_k
        )
    
    def ingest_documents(self, documents: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Ingest and process documents into chunks."""
        all_chunks = []
        processing_stats = {
            "total_documents": len(documents),
            "successful_documents": 0,
            "failed_documents": 0,
            "total_chunks": 0,
            "chunking_strategy": self.config.chunking_strategy
        }
        
        for doc in documents:
            try:
                doc_id = doc.get("id", f"doc_{len(all_chunks)}")
                content = doc.get("content", "")
                metadata = doc.get("metadata", {})
                
                # Add document metadata
                chunk_metadata = {
                    "document_id": doc_id,
                    "document_title": doc.get("title", ""),
                    **metadata
                }
                
                # Chunk the document
                result = self.chunker.run(text=content, metadata=chunk_metadata)
                doc_chunks = result["chunks"]
                all_chunks.extend(doc_chunks)
                processing_stats["successful_documents"] += 1
                
            except Exception as e:
                print(f"Failed to process document {doc.get('id', 'unknown')}: {e}")
                processing_stats["failed_documents"] += 1
        
        processing_stats["total_chunks"] = len(all_chunks)
        self.document_chunks = all_chunks
        
        return {"chunks": all_chunks, "statistics": processing_stats}
    
    def search(self, query: str, 
              dense_results: List[Dict] = None,
              sparse_results: List[Dict] = None) -> Dict[str, Any]:
        """Perform hybrid search and ranking."""
        
        # If no external retrieval results provided, simulate them
        if dense_results is None or sparse_results is None:
            dense_results, sparse_results = self._simulate_retrieval(query)
        
        # Perform hybrid retrieval
        hybrid_result = self.hybrid_retriever.run(
            query=query,
            dense_results=dense_results,
            sparse_results=sparse_results
        )
        
        # Final relevance scoring
        result_chunks = hybrid_result["hybrid_results"]
        if result_chunks:
            # In production, use real embeddings
            query_emb = [{"embedding": self._simulate_embedding(query)}]
            chunk_embeddings = [{"embedding": self._simulate_embedding(chunk["content"])} 
                               for chunk in result_chunks]
            
            final_result = self.relevance_scorer.run(
                chunks=result_chunks,
                query_embedding=query_emb,
                chunk_embeddings=chunk_embeddings
            )
            final_chunks = final_result["relevant_chunks"]
        else:
            final_chunks = []
        
        return {
            "query": query,
            "final_results": final_chunks,
            "hybrid_results": result_chunks,
            "fusion_method": hybrid_result["fusion_method"],
            "search_metadata": {
                "dense_count": len(dense_results),
                "sparse_count": len(sparse_results),
                "hybrid_count": len(result_chunks),
                "final_count": len(final_chunks)
            }
        }
    
    def _simulate_retrieval(self, query: str) -> tuple:
        """Simulate dense and sparse retrieval for demonstration."""
        query_words = set(query.lower().split())
        dense_results = []
        sparse_results = []
        
        for chunk in self.document_chunks[:20]:  # Limit for simulation
            content_words = set(chunk["content"].lower().split())
            overlap = len(query_words & content_words)
            
            # Simulate dense scoring (semantic similarity)
            dense_score = min(0.5 + (overlap * 0.1), 1.0)
            if dense_score > 0.6:
                dense_results.append({
                    "id": chunk["chunk_id"],
                    "content": chunk["content"],
                    "similarity_score": dense_score,
                    **{k: v for k, v in chunk.items() if k not in ["chunk_id", "content"]}
                })
            
            # Simulate sparse scoring (keyword matching)
            if overlap > 0:
                sparse_score = min(overlap * 0.2, 1.0)
                sparse_results.append({
                    "id": chunk["chunk_id"],
                    "content": chunk["content"],
                    "similarity_score": sparse_score,
                    **{k: v for k, v in chunk.items() if k not in ["chunk_id", "content"]}
                })
        
        # Sort and limit results
        dense_results.sort(key=lambda x: x["similarity_score"], reverse=True)
        sparse_results.sort(key=lambda x: x["similarity_score"], reverse=True)
        
        return dense_results[:10], sparse_results[:10]
    
    def _simulate_embedding(self, text: str) -> List[float]:
        """Simulate embedding generation for demonstration."""
        import hashlib
        text_hash = hashlib.md5(text.lower().encode()).hexdigest()
        embedding = []
        for i in range(0, min(len(text_hash), 10), 2):
            val = int(text_hash[i:i+2], 16) / 255.0
            embedding.append(val)
        while len(embedding) < 5:
            embedding.append(0.0)
        return embedding[:5]
```

## Performance Optimization

### Caching Strategies

```python
import functools
from typing import Dict, Any

class CachedRAGPipeline:
    def __init__(self):
        self.embedding_cache = {}
        self.chunk_cache = {}
    
    @functools.lru_cache(maxsize=1000)
    def get_cached_embeddings(self, text: str) -> str:
        """Cache embeddings by text hash for reuse."""
        import hashlib
        text_hash = hashlib.md5(text.encode()).hexdigest()
        
        if text_hash not in self.embedding_cache:
            embedder = EmbeddingGeneratorNode()
            result = embedder.run(input_texts=[text])
            self.embedding_cache[text_hash] = result["embeddings"][0]
        
        return self.embedding_cache[text_hash]
```

### Batch Processing

```python
def efficient_batch_processing(documents: List[Dict], batch_size: int = 50):
    """Process documents in optimal batch sizes."""
    chunker = SemanticChunkerNode()
    embedder = EmbeddingGeneratorNode()
    
    all_chunks = []
    
    for i in range(0, len(documents), batch_size):
        batch = documents[i:i + batch_size]
        batch_chunks = []
        batch_texts = []
        
        for doc in batch:
            result = chunker.run(text=doc["content"])
            chunks = result["chunks"]
            batch_chunks.extend(chunks)
            batch_texts.extend([chunk["content"] for chunk in chunks])
        
        # Batch embedding generation
        if batch_texts:
            embedding_result = embedder.run(
                operation="embed_batch",
                input_texts=batch_texts
            )
            
            # Associate embeddings with chunks
            for j, chunk in enumerate(batch_chunks):
                if j < len(embedding_result["embeddings"]):
                    chunk["embedding"] = embedding_result["embeddings"][j]
        
        all_chunks.extend(batch_chunks)
        print(f"Processed batch {i//batch_size + 1}: {len(batch_chunks)} chunks")
    
    return all_chunks
```

## Best Practices

### 1. Choose Strategy Based on Content Type

```python
# ✅ GOOD: Content-aware chunking
def smart_chunker(text: str, content_type: str):
    """Adapt parameters to content type."""
    if content_type == "technical":
        chunker = StatisticalChunkerNode(
            chunk_size=800,
            variance_threshold=0.6,
            max_sentences_per_chunk=10
        )
    elif content_type == "narrative":
        chunker = SemanticChunkerNode(
            chunk_size=1200,
            similarity_threshold=0.75,
            chunk_overlap=150
        )
    else:  # general content
        chunker = SemanticChunkerNode()  # Default parameters
    
    return chunker.run(text=text)
```

### 2. Systematic Parameter Tuning

```python
def systematic_parameter_tuning(documents: List[str], queries: List[str]):
    """Systematic approach to parameter optimization."""
    chunk_sizes = [500, 750, 1000, 1250, 1500]
    similarity_thresholds = [0.6, 0.7, 0.75, 0.8, 0.85]
    
    best_score = 0
    best_params = {}
    
    for chunk_size in chunk_sizes:
        for threshold in similarity_thresholds:
            chunker = SemanticChunkerNode(
                chunk_size=chunk_size,
                similarity_threshold=threshold
            )
            
            # Test on subset for speed
            test_docs = documents[:10]
            test_queries = queries[:5]
            
            score = evaluate_configuration(chunker, test_docs, test_queries)
            
            if score > best_score:
                best_score = score
                best_params = {
                    "chunk_size": chunk_size,
                    "similarity_threshold": threshold
                }
    
    return best_params, best_score
```

### 3. Quality Assurance

```python
def quality_assurance_pipeline(chunks: List[Dict]) -> Dict[str, Any]:
    """Comprehensive quality checks for chunked content."""
    qa_results = {
        "total_chunks": len(chunks),
        "quality_issues": [],
        "warnings": [],
        "statistics": {}
    }
    
    if not chunks:
        qa_results["quality_issues"].append("No chunks generated")
        return qa_results
    
    # Check chunk size distribution
    chunk_sizes = [len(chunk["content"]) for chunk in chunks]
    avg_size = sum(chunk_sizes) / len(chunk_sizes)
    size_variance = sum((size - avg_size) ** 2 for size in chunk_sizes) / len(chunk_sizes)
    
    qa_results["statistics"]["avg_chunk_size"] = avg_size
    qa_results["statistics"]["size_variance"] = size_variance
    
    # Issue: Extreme size variance
    if size_variance > avg_size:
        qa_results["quality_issues"].append(
            f"High size variance ({size_variance:.0f}) indicates inconsistent chunking"
        )
    
    # Check for empty or very short chunks
    short_chunks = [chunk for chunk in chunks if len(chunk["content"]) < 50]
    if short_chunks:
        qa_results["warnings"].append(f"{len(short_chunks)} chunks are very short (<50 chars)")
    
    return qa_results
```

## Common Patterns

### Multi-Strategy Comparison

```python
def compare_chunking_strategies(document: str, query: str):
    """Compare different chunking strategies for the same document."""
    
    strategies = {
        "semantic_balanced": SemanticChunkerNode(
            chunk_size=800, 
            similarity_threshold=0.75
        ),
        "semantic_fine": SemanticChunkerNode(
            chunk_size=400, 
            similarity_threshold=0.8
        ),
        "statistical_structured": StatisticalChunkerNode(
            chunk_size=800, 
            variance_threshold=0.6
        ),
        "statistical_sensitive": StatisticalChunkerNode(
            chunk_size=600, 
            variance_threshold=0.4
        )
    }
    
    results = {}
    
    for name, chunker in strategies.items():
        result = chunker.run(text=document)
        chunks = result["chunks"]
        relevance_scores = simulate_retrieval_quality(chunks, query)
        
        results[name] = {
            "chunk_count": len(chunks),
            "avg_chunk_size": sum(len(c["content"]) for c in chunks) / len(chunks),
            "avg_relevance": sum(relevance_scores) / len(relevance_scores)
        }
    
    # Find best strategy
    best_strategy = max(results.keys(), key=lambda k: results[k]["avg_relevance"])
    
    return results, best_strategy
```

### Adaptive Chunking

```python
class AdaptiveChunker:
    """Automatically choose chunking strategy based on document characteristics."""
    
    def __init__(self):
        self.semantic_chunker = SemanticChunkerNode()
        self.statistical_chunker = StatisticalChunkerNode()
    
    def analyze_document_structure(self, text: str) -> Dict[str, float]:
        """Analyze document to determine best chunking strategy."""
        sentences = text.split('. ')
        
        # Calculate metrics
        avg_sentence_length = sum(len(s) for s in sentences) / len(sentences)
        sentence_length_variance = self._calculate_variance([len(s) for s in sentences])
        
        # Simple heuristics
        structure_score = 1.0 if sentence_length_variance > 500 else 0.0
        narrative_score = 1.0 if avg_sentence_length > 100 else 0.0
        
        return {
            "structure_score": structure_score,
            "narrative_score": narrative_score,
            "avg_sentence_length": avg_sentence_length,
            "sentence_variance": sentence_length_variance
        }
    
    def chunk_adaptively(self, text: str, metadata: Dict = None) -> Dict[str, Any]:
        """Choose and apply the best chunking strategy."""
        analysis = self.analyze_document_structure(text)
        
        if analysis["structure_score"] > 0.5:
            # Structured document - use statistical chunking
            strategy = "statistical"
            result = self.statistical_chunker.run(text=text, metadata=metadata)
        else:
            # Narrative document - use semantic chunking
            strategy = "semantic"
            result = self.semantic_chunker.run(text=text, metadata=metadata)
        
        result["chosen_strategy"] = strategy
        result["document_analysis"] = analysis
        
        return result
```

## Common Pitfalls to Avoid

### ❌ Don't: Use Fixed-Size Chunking

```python
# ❌ AVOID: Simple character-based splitting
def bad_chunking(text: str, chunk_size: int = 1000):
    """This breaks sentences and loses context."""
    return [text[i:i+chunk_size] for i in range(0, len(text), chunk_size)]

# ✅ INSTEAD: Use intelligent chunking
from kailash.nodes.transform.chunkers import SemanticChunkerNode

chunker = SemanticChunkerNode(chunk_size=1000, preserve_sentences=True)
result = chunker.run(text=text)
```

### ❌ Don't: Ignore Content Type

```python
from kailash.nodes.transform.chunkers import SemanticChunkerNode, StatisticalChunkerNode

# ❌ BAD: One-size-fits-all approach
def bad_universal_chunker(text: str):
    """Using same parameters for all content types."""
    chunker = SemanticChunkerNode(chunk_size=1000, similarity_threshold=0.75)
    return chunker.run(text=text)

# ✅ GOOD: Content-aware chunking
def smart_chunker(text: str, content_type: str):
    if content_type == "technical":
        chunker = StatisticalChunkerNode(variance_threshold=0.6)
    else:
        chunker = SemanticChunkerNode(similarity_threshold=0.75)
    return chunker.run(text=text)
```

### ❌ Don't: Tune Parameters in Isolation

```python
from kailash.nodes.transform.chunkers import SemanticChunkerNode
from kailash.nodes.data.retrieval import HybridRetrieverNode

# ❌ BAD: Tuning without considering downstream impact
chunker = SemanticChunkerNode(chunk_size=5000)  # Too large for retrieval
retriever = HybridRetrieverNode(top_k=3)        # Too few for large chunks

# ✅ GOOD: Consider the entire pipeline
if chunk_size > 1500:
    retrieval_top_k = 8  # More results for larger chunks
else:
    retrieval_top_k = 5  # Standard for smaller chunks
```

## Summary

This guide provides a complete foundation for implementing production-ready RAG systems with advanced chunking and retrieval capabilities. Start with the basic patterns and gradually adopt the advanced techniques as your system matures.

### Key Takeaways

1. **Choose the right chunking strategy** based on your content type
2. **Test both semantic and statistical** approaches systematically  
3. **Use hybrid retrieval** for best performance (20-30% improvement)
4. **Implement quality assurance** and monitoring from day one
5. **Optimize for your specific use case** through systematic parameter tuning

For complete examples and advanced patterns, see the [RAG Workflows](../workflows/by-pattern/rag/) directory.
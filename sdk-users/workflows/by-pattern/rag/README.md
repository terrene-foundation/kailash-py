# RAG (Retrieval-Augmented Generation) Workflows

This directory contains complete RAG workflow examples using Kailash SDK's advanced chunking and retrieval nodes.

## Available Workflows

### 1. Complete RAG Pipeline (`complete_rag_pipeline.py`)
- **Purpose**: Production-ready RAG system with all advanced features
- **Features**:
  - Semantic and statistical chunking strategies
  - Hybrid retrieval with multiple fusion methods (RRF, Linear, Weighted)
  - Advanced relevance scoring and ranking
  - Comprehensive configuration management
  - Performance monitoring and statistics
- **Use Cases**: Enterprise search, document Q&A, knowledge base systems

### 2. Hierarchical RAG Workflow (`hierarchical_rag_workflow.py`)
- **Purpose**: Multi-level document processing and retrieval
- **Features**: Document hierarchy management, nested chunking strategies
- **Use Cases**: Complex document structures, technical manuals

## Quick Start

### Basic Usage

```python
from complete_rag_pipeline import AdvancedRAGPipeline, create_sample_documents

# 1. Create pipeline
pipeline = AdvancedRAGPipeline()

# 2. Prepare documents
documents = create_sample_documents()

# 3. Run complete pipeline
result = pipeline.run_complete_pipeline(
    documents=documents,
    query="What are neural networks?",
    chunking_method="semantic"
)

# 4. Get results
final_results = result["final_results"]
for chunk in final_results:
    print(f"Score: {chunk['relevance_score']:.4f}")
    print(f"Content: {chunk['content'][:100]}...")

```

### Advanced Configuration

```python
# Custom configuration for specific use cases
config = {
    "chunking": {
        "semantic": {
            "chunk_size": 600,
            "similarity_threshold": 0.7,
            "overlap": 80,
            "window_size": 2
        }
    },
    "retrieval": {
        "fusion_strategy": "rrf",
        "top_k": 4,
        "rrf_k": 50
    }
}

pipeline = AdvancedRAGPipeline(config)

```

## Node Overview

### Advanced Chunking Nodes

1. **SemanticChunkerNode**
   - Uses embedding similarity for natural topic boundaries
   - Best for narrative content and flowing documents
   - Parameters: `chunk_size`, `similarity_threshold`, `chunk_overlap`

2. **StatisticalChunkerNode**
   - Uses embedding variance analysis for boundary detection
   - Best for technical documents and structured content
   - Parameters: `chunk_size`, `variance_threshold`, `min/max_sentences`

### Advanced Retrieval Nodes

1. **HybridRetrieverNode**
   - Combines dense (semantic) and sparse (keyword) retrieval
   - Multiple fusion strategies: RRF, Linear, Weighted
   - 20-30% better performance than single methods

2. **RelevanceScorerNode**
   - Advanced relevance scoring with embeddings
   - Supports multiple similarity methods
   - Final ranking and result refinement

## Performance Comparison

| Method | Precision | Recall | Speed | Best For |
|--------|-----------|--------|-------|----------|
| Semantic Only | High | Medium | Medium | Conceptual queries |
| Keyword Only | Medium | High | Fast | Exact term matching |
| **Hybrid (RRF)** | **Highest** | **Highest** | **Medium** | **Production systems** |

## Best Practices

### 1. Strategy Selection
- **Technical docs**: Use StatisticalChunkerNode with `variance_threshold=0.6`
- **General content**: Use SemanticChunkerNode with `similarity_threshold=0.75`
- **Always test both**: Run comparison on your specific content

### 2. Retrieval Optimization
- **Start with RRF**: Most robust fusion strategy
- **Tune for your domain**: Adjust weights based on content type
- **Monitor performance**: Track retrieval quality metrics

### 3. Production Deployment
- **Implement caching**: Cache embeddings and chunk results
- **Batch processing**: Process documents in batches for efficiency
- **Error handling**: Graceful degradation and fallback strategies

## Examples by Use Case

### Enterprise Search
```python
# Configuration optimized for enterprise documents
enterprise_config = {
    "chunking": {
        "semantic": {"chunk_size": 1200, "similarity_threshold": 0.8}
    },
    "retrieval": {
        "fusion_strategy": "rrf",
        "top_k": 8
    }
}

```

### Customer Support
```python
# Configuration for FAQ and support documents
support_config = {
    "chunking": {
        "semantic": {"chunk_size": 600, "chunk_overlap": 100}
    },
    "retrieval": {
        "fusion_strategy": "linear",
        "dense_weight": 0.7,
        "sparse_weight": 0.3
    }
}

```

### Technical Documentation
```python
# Configuration for technical manuals and guides
technical_config = {
    "chunking": {
        "statistical": {
            "chunk_size": 800,
            "variance_threshold": 0.6,
            "max_sentences_per_chunk": 10
        }
    }
}

```

## Testing Your Implementation

### Quality Validation
```python
# Test chunk quality
from complete_rag_pipeline import AdvancedRAGPipeline

pipeline = AdvancedRAGPipeline()
documents = your_documents
test_queries = ["query1", "query2", "query3"]

# Compare strategies
semantic_result = pipeline.process_documents(documents, "semantic")
statistical_result = pipeline.process_documents(documents, "statistical")

# Evaluate which works better for your content

```

### Performance Testing
```python
import time

start_time = time.time()
result = pipeline.run_complete_pipeline(
    documents=large_document_set,
    query="test query"
)
processing_time = time.time() - start_time

print(f"Processed {len(large_document_set)} documents in {processing_time:.2f}s")
print(f"Created {len(result['final_results'])} final results")

```

## Related Documentation

- [Advanced RAG Guide](../../developer/13-advanced-rag-guide.md) - Complete implementation guide
- [RAG Best Practices](../../developer/14-rag-best-practices.md) - Production best practices
- [Transform Nodes](../../nodes/06-transform-nodes.md) - Chunking node documentation
- [Data Nodes](../../nodes/03-data-nodes.md) - Retrieval node documentation

## Support

For questions and support:
1. Check the troubleshooting section in the best practices guide
2. Review the comprehensive examples in this directory
3. Consult the node-specific documentation for detailed parameters

# Comprehensive RAG Toolkit Guide

*Build state-of-the-art Retrieval Augmented Generation systems with Kailash SDK*

## Prerequisites

- Completed [Fundamentals](01-fundamentals.md) - Core SDK concepts
- Completed [Workflows](02-workflows.md) - Basic workflow patterns
- Understanding of embeddings and vector search
- LLM API access (OpenAI, Anthropic, or local)

## Quick Start

The Kailash SDK provides 40+ specialized RAG nodes covering every aspect of modern RAG systems:

```python
from kailash.nodes.rag import (
    AdaptiveRAGWorkflowNode,
    RAGStrategyRouterNode,
    AsyncParallelRAGNode,
    SemanticRAGNode,
    HybridRAGNode
)
from kailash.workflow.builder import WorkflowBuilder

# Method 1: Fully Adaptive RAG (Recommended)
adaptive_rag = AdaptiveRAGWorkflowNode(
    name="smart_rag",
    llm_model="gpt-4"
)

result = await adaptive_rag.run(
    documents=documents,
    query="How to optimize neural network training?"
)

# Method 2: Build Custom RAG Workflow
workflow = WorkflowBuilder()

# Add RAG components
workflow.add_node("SemanticRAGNode", "semantic_rag", {
    "chunk_size": 512,
    "chunk_overlap": 50,
    "embedding_model": "text-embedding-3-small"
})

# Method 3: Parallel RAG Strategies
parallel_rag = AsyncParallelRAGNode(
    name="parallel_rag",
    strategies=["semantic", "sparse", "hybrid"]
)
```

## Core RAG Strategies

### 1. Semantic RAG

Best for conceptual understanding and narrative content:

```python
from kailash.nodes.rag import SemanticRAGNode, RAGConfig

config = RAGConfig(
    chunk_size=512,
    chunk_overlap=50,
    retrieval_k=5,
    embedding_model="text-embedding-3-small"
)

semantic_rag = SemanticRAGNode(
    name="semantic_rag",
    config=config
)

# Index documents
result = await semantic_rag.run(
    documents=documents,
    operation="index"
)

# Retrieve relevant chunks
results = await semantic_rag.run(
    query="What is machine learning?",
    operation="retrieve"
)
```

### 2. Hybrid RAG

Combines semantic and statistical approaches:

```python
from kailash.nodes.rag import HybridRAGNode

hybrid_rag = HybridRAGNode(
    name="hybrid_rag",
    semantic_weight=0.7,
    statistical_weight=0.3
)

# Automatically balances both approaches
results = await hybrid_rag.run(
    documents=mixed_content,
    query="How to implement OAuth2 authentication?"
)
```

### 3. Hierarchical RAG

Multi-level document processing for complex documents:

```python
from kailash.nodes.rag import HierarchicalRAGNode

hierarchical_rag = HierarchicalRAGNode(
    name="hierarchical_rag",
    levels=["document", "section", "paragraph"],
    aggregation_method="weighted"
)

# Process structured documents
results = await hierarchical_rag.run(
    documents=structured_docs,
    query="Explain the authentication flow"
)
```

## Building RAG Workflows

### Basic RAG Pipeline

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.nodes.ai import EmbeddingGeneratorNode
from kailash.nodes.data import VectorDatabaseNode

workflow = WorkflowBuilder()

# 1. Document Processing
workflow.add_node("PythonCodeNode", "doc_processor", {
    "code": """
# Process and chunk documents
chunks = []
for doc in documents:
    text = doc.get('text', '')
    source = doc.get('source', 'unknown')

    # Simple chunking by character count
    chunk_size = 500
    overlap = 50

    for i in range(0, len(text), chunk_size - overlap):
        chunk = {
            'text': text[i:i + chunk_size],
            'source': source,
            'index': i // (chunk_size - overlap)
        }
        chunks.append(chunk)

result = {'chunks': chunks}
"""
})

# 2. Generate Embeddings
workflow.add_node("EmbeddingGeneratorNode", "embedder", {
    "model": "text-embedding-ada-002"
})

# 3. Store in Vector Database
workflow.add_node("VectorDatabaseNode", "vector_store", {
    "operation": "upsert",
    "collection": "documents"
})

# 4. Query Processing
workflow.add_node("PythonCodeNode", "query_processor", {
    "code": """
# Enhance query with context
enhanced_query = {
    'original': query,
    'expanded': query + " explain in detail",
    'keywords': query.lower().split()
}
result = {'processed_query': enhanced_query}
"""
})

# 5. Similarity Search
workflow.add_node("VectorDatabaseNode", "retriever", {
    "operation": "search",
    "collection": "documents",
    "top_k": 5
})

# 6. Generate Response
workflow.add_node("LLMAgentNode", "generator", {
    "model": "gpt-4",
    "prompt": """
Based on the following context, answer the query.

Context:
{context}

Query: {query}

Answer:
"""
})

# Connect the pipeline
workflow.add_connection("doc_processor", "result.chunks", "embedder", "texts")
workflow.add_connection("embedder", "result.embeddings", "vector_store", "vectors")
workflow.add_connection("query_processor", "result.processed_query", "retriever", "query")
workflow.add_connection("retriever", "result.matches", "generator", "context")
```

### Advanced RAG with Reranking

```python
# Add reranking for better results
workflow.add_node("PythonCodeNode", "reranker", {
    "code": """
# Rerank retrieved chunks based on relevance
from typing import List, Dict

def calculate_relevance_score(chunk: Dict, query: str) -> float:
    # Simple keyword matching (replace with advanced scoring)
    text = chunk.get('text', '').lower()
    query_terms = query.lower().split()

    score = 0.0
    for term in query_terms:
        if term in text:
            score += text.count(term) / len(text.split())

    return score

# Score and sort chunks
scored_chunks = []
for chunk in retrieved_chunks:
    score = calculate_relevance_score(chunk, query)
    scored_chunks.append({
        'chunk': chunk,
        'score': score,
        'original_rank': retrieved_chunks.index(chunk)
    })

# Sort by score
scored_chunks.sort(key=lambda x: x['score'], reverse=True)

# Return top reranked chunks
result = {
    'reranked_chunks': [item['chunk'] for item in scored_chunks[:5]],
    'scores': [item['score'] for item in scored_chunks[:5]]
}
"""
})

# Insert reranker between retriever and generator
workflow.add_connection("retriever", "result.matches", "reranker", "retrieved_chunks")
workflow.add_connection("reranker", "result.reranked_chunks", "generator", "context")
```

## Query Processing Techniques

### Query Expansion

```python
workflow.add_node("PythonCodeNode", "query_expander", {
    "code": """
# Expand query with synonyms and related terms
expansions = {
    "ML": ["machine learning", "artificial intelligence", "AI"],
    "API": ["application programming interface", "endpoint", "service"],
    "auth": ["authentication", "authorization", "security"]
}

expanded_terms = [query]
for term, synonyms in expansions.items():
    if term.lower() in query.lower():
        expanded_terms.extend(synonyms)

result = {
    'original_query': query,
    'expanded_queries': list(set(expanded_terms))
}
"""
})
```

### Multi-Query Generation

```python
workflow.add_node("LLMAgentNode", "query_generator", {
    "model": "gpt-3.5-turbo",
    "prompt": """
Generate 3 different versions of this query to improve retrieval:

Original query: {query}

1. A more specific version:
2. A broader version:
3. A related question:

Output as JSON array.
""",
    "response_format": "json"
})
```

## Performance Optimization

### Async Parallel Processing

```python
from kailash.nodes.rag import AsyncParallelRAGNode

# Process multiple strategies in parallel
parallel_rag = AsyncParallelRAGNode(
    name="parallel_rag",
    strategies=["semantic", "sparse", "hybrid"],
    aggregation_method="weighted_vote"
)

# Execute all strategies concurrently
results = await parallel_rag.run(
    documents=documents,
    query=query,
    weights={"semantic": 0.5, "sparse": 0.3, "hybrid": 0.2}
)
```

### Caching for Repeated Queries

```python
workflow.add_node("PythonCodeNode", "cache_checker", {
    "code": """
import hashlib
import json

# Create cache key from query
cache_key = hashlib.md5(query.encode()).hexdigest()

# Check cache (would connect to Redis in production)
cached_result = cache.get(cache_key) if 'cache' in globals() else None

if cached_result:
    result = {
        'cached': True,
        'response': cached_result
    }
else:
    result = {
        'cached': False,
        'cache_key': cache_key
    }
"""
})
```

## Evaluation and Monitoring

### RAG Quality Metrics

```python
workflow.add_node("PythonCodeNode", "quality_evaluator", {
    "code": """
# Evaluate RAG response quality
def evaluate_response(response, context_chunks, query):
    metrics = {
        'response_length': len(response),
        'context_coverage': 0.0,
        'query_relevance': 0.0,
        'coherence_score': 0.0
    }

    # Context coverage: how much context was used
    response_lower = response.lower()
    used_chunks = 0
    for chunk in context_chunks:
        chunk_text = chunk.get('text', '').lower()
        # Check if key phrases from chunk appear in response
        if any(phrase in response_lower for phrase in chunk_text.split()[:10]):
            used_chunks += 1

    metrics['context_coverage'] = used_chunks / len(context_chunks) if context_chunks else 0

    # Query relevance: does response address the query
    query_terms = query.lower().split()
    mentioned_terms = sum(1 for term in query_terms if term in response_lower)
    metrics['query_relevance'] = mentioned_terms / len(query_terms) if query_terms else 0

    # Simple coherence check (response should be properly formatted)
    metrics['coherence_score'] = 1.0 if len(response.split('.')) > 1 else 0.5

    metrics['overall_score'] = (
        metrics['context_coverage'] * 0.3 +
        metrics['query_relevance'] * 0.5 +
        metrics['coherence_score'] * 0.2
    )

    return metrics

metrics = evaluate_response(response, context_chunks, query)
result = {'quality_metrics': metrics}
"""
})
```

## Complete RAG Example

Here's a complete, production-ready RAG workflow:

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.rag import SemanticRAGNode
from kailash.nodes.ai import EmbeddingGeneratorNode, LLMAgentNode

def create_rag_workflow():
    """Create a complete RAG workflow."""
    workflow = WorkflowBuilder()

    # 1. Document indexing branch
    workflow.add_node("PythonCodeNode", "doc_chunker", {
        "code": """
chunks = []
for doc_id, doc in enumerate(documents):
    text = doc.get('text', '')
    metadata = doc.get('metadata', {})

    # Chunk with overlap
    chunk_size = 500
    overlap = 50

    for i in range(0, len(text), chunk_size - overlap):
        chunk = {
            'id': f"{doc_id}_{i}",
            'text': text[i:i + chunk_size],
            'metadata': metadata,
            'doc_id': doc_id,
            'chunk_index': i // (chunk_size - overlap)
        }
        chunks.append(chunk)

result = {'chunks': chunks}
"""
    })

    # 2. Generate embeddings
    workflow.add_node("EmbeddingGeneratorNode", "embedder", {
        "model": "text-embedding-ada-002",
        "batch_size": 100
    })

    # 3. Query processing branch
    workflow.add_node("PythonCodeNode", "query_enhancer", {
        "code": """
# Enhance query for better retrieval
enhanced = {
    'original': query,
    'normalized': query.lower().strip(),
    'expanded': f"{query} (explain, describe, elaborate)",
}
result = {'enhanced_query': enhanced}
"""
    })

    # 4. Retrieval
    workflow.add_node("SemanticRAGNode", "retriever", {
        "operation": "retrieve",
        "top_k": 10,
        "similarity_threshold": 0.7
    })

    # 5. Rerank results
    workflow.add_node("PythonCodeNode", "reranker", {
        "code": """
# Rerank based on multiple factors
import math

def score_chunk(chunk, query_data):
    score = chunk.get('similarity_score', 0.0)

    # Boost recent documents
    if 'timestamp' in chunk.get('metadata', {}):
        # Implement recency boost
        score *= 1.1

    # Boost if query terms appear
    text_lower = chunk['text'].lower()
    query_terms = query_data['normalized'].split()
    term_matches = sum(1 for term in query_terms if term in text_lower)
    score *= (1 + term_matches * 0.1)

    return min(score, 1.0)  # Cap at 1.0

reranked = []
for chunk in retrieved_chunks:
    chunk['final_score'] = score_chunk(chunk, query_data)
    reranked.append(chunk)

reranked.sort(key=lambda x: x['final_score'], reverse=True)
result = {'reranked_chunks': reranked[:5]}
"""
    })

    # 6. Generate response
    workflow.add_node("LLMAgentNode", "response_generator", {
        "model": "gpt-4",
        "temperature": 0.7,
        "prompt": """You are a helpful assistant. Answer the question based on the provided context.

Context:
{context}

Question: {query}

Instructions:
1. Answer based only on the provided context
2. If the context doesn't contain the answer, say so
3. Be concise but complete
4. Cite which part of the context supports your answer

Answer:"""
    })

    # 7. Response validation
    workflow.add_node("PythonCodeNode", "response_validator", {
        "code": """
# Validate and enhance response
validation = {
    'has_answer': len(response) > 50,
    'cites_context': any(phrase in response.lower() for phrase in ['based on', 'according to', 'the context']),
    'addresses_query': any(term in response.lower() for term in query.lower().split())
}

final_response = {
    'answer': response,
    'validation': validation,
    'confidence': sum(validation.values()) / len(validation),
    'sources': [chunk['metadata'].get('source', 'Unknown') for chunk in context_chunks[:3]]
}

result = {'final_response': final_response}
"""
    })

    # Connect the workflow
    workflow.add_connection("doc_chunker", "result.chunks", "embedder", "texts")
    workflow.add_connection("query_enhancer", "result.enhanced_query", "retriever", "query_data")
    workflow.add_connection("embedder", "result", "retriever", "indexed_chunks")
    workflow.add_connection("retriever", "result.matches", "reranker", "retrieved_chunks")
    workflow.add_connection("query_enhancer", "result.enhanced_query", "reranker", "query_data")
    workflow.add_connection("reranker", "result.reranked_chunks", "response_generator", "context")
    workflow.add_connection("query_enhancer", "result.enhanced_query.original", "response_generator", "query")
    workflow.add_connection("response_generator", "result", "response_validator", "response")
    workflow.add_connection("reranker", "result.reranked_chunks", "response_validator", "context_chunks")
    workflow.add_connection("query_enhancer", "result.enhanced_query.original", "response_validator", "query")

    return workflow

# Use the workflow
runtime = LocalRuntime()
workflow = create_rag_workflow()

# Index documents
index_results, _ = runtime.execute(
    workflow.build(),
    parameters={
        "doc_chunker": {"documents": your_documents}
    }
)

# Query
query_results, _ = runtime.execute(
    workflow.build(),
    parameters={
        "query_enhancer": {"query": "What is machine learning?"}
    }
)

print(query_results["response_validator"]["result"]["final_response"])
```

## Best Practices

1. **Chunking Strategy**
   - Use overlapping chunks to preserve context
   - Adjust chunk size based on your content type
   - Include metadata with each chunk

2. **Embedding Models**
   - Choose models based on your domain
   - Consider multilingual models for diverse content
   - Cache embeddings to reduce API costs

3. **Retrieval Optimization**
   - Use hybrid search for best results
   - Implement reranking for quality improvement
   - Set appropriate similarity thresholds

4. **Response Generation**
   - Provide clear instructions in prompts
   - Validate responses for quality
   - Include source attribution

5. **Performance**
   - Use async operations for scalability
   - Implement caching for common queries
   - Batch operations when possible

6. **Monitoring**
   - Track retrieval quality metrics
   - Monitor response times
   - Log failed queries for improvement

## Related Guides

**Prerequisites:**
- [Fundamentals](01-fundamentals.md) - Core concepts
- [Workflows](02-workflows.md) - Building workflows

**Advanced Topics:**
- [Async Workflows](08-async-workflow-builder.md) - Async RAG
- [Production](04-production.md) - Deploying RAG systems

---

**Build powerful RAG systems that combine the best of retrieval and generation for accurate, contextual responses!**

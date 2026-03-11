# pgvector Quickstart Guide

Complete guide to vector similarity search in DataFlow using PostgreSQL with pgvector extension.

## Overview

PostgreSQLVectorAdapter extends DataFlow with semantic similarity search capabilities, enabling:
- **RAG (Retrieval-Augmented Generation)** for AI applications
- **Semantic search** based on meaning, not just keywords
- **Document similarity** matching
- **Hybrid search** combining vector and full-text search
- **40-60% cost savings** vs dedicated vector databases

## Prerequisites

### 1. Install pgvector Extension

```bash
# Ubuntu/Debian
sudo apt-get install postgresql-16-pgvector

# macOS (Homebrew)
brew install pgvector

# Or compile from source
git clone --branch v0.7.0 https://github.com/pgvector/pgvector.git
cd pgvector
make
sudo make install
```

### 2. Enable Extension in Database

```sql
-- Connect to your PostgreSQL database
psql -U postgres -d your_database

-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Verify installation
SELECT * FROM pg_extension WHERE extname = 'vector';
```

## Quick Start

### Step 1: Install DataFlow with Vector Support

```bash
pip install kailash-dataflow
```

### Step 2: Create Vector Adapter

```python
from dataflow import DataFlow
from dataflow.adapters import PostgreSQLVectorAdapter

# Create PostgreSQLVectorAdapter
adapter = PostgreSQLVectorAdapter(
    "postgresql://user:password@localhost:5432/vectordb",
    vector_dimensions=1536,  # OpenAI text-embedding-3-small
    default_distance="cosine"  # cosine, l2, or ip
)

# Create DataFlow with vector adapter
db = DataFlow(adapter=adapter)

# Connect and initialize
await db.initialize()
```

### Step 3: Define Model with Vector Column

```python
from dataflow import DataFlow

@db.model
class Document:
    id: str
    title: str
    content: str
    category: str
    embedding: list[float]  # Vector column (1536 dimensions)
```

### Step 4: Add Vector Column to Existing Table

```python
# Add vector column to table
await adapter.create_vector_column(
    "documents",
    column_name="embedding",
    dimensions=1536
)
```

### Step 5: Create Vector Index for Performance

```python
# Create IVFFlat index (good performance)
await adapter.create_vector_index(
    "documents",
    column_name="embedding",
    index_type="ivfflat",
    distance="cosine",
    lists=100  # Typically sqrt(total_rows)
)

# Or create HNSW index (better performance, requires pgvector 0.5.0+)
await adapter.create_vector_index(
    "documents",
    column_name="embedding",
    index_type="hnsw",
    distance="cosine",
    m=16,  # Max connections per layer
    ef_construction=64  # Build time accuracy
)
```

## Using Vector Search

### Basic Semantic Search

```python
from dataflow.nodes.vector_nodes import VectorSearchNode
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime import AsyncLocalRuntime

# Get query embedding from AI model
query = "machine learning tutorials"
query_embedding = await embedding_model.embed(query)  # Returns 1536-dim vector

# Create workflow
workflow = WorkflowBuilder()
workflow.add_node("VectorSearchNode", "search", {
    "table_name": "documents",
    "query_vector": query_embedding,
    "k": 5,  # Return top 5 results
    "distance": "cosine",
    "return_distance": True
})

# Execute
runtime = AsyncLocalRuntime()
results = await runtime.execute_workflow_async(workflow.build())

# Access results
documents = results["search"]["results"]
for doc in documents:
    print(f"{doc['title']}: distance={doc['distance']}")
```

### Search with Filters

```python
# Search only in specific category
workflow.add_node("VectorSearchNode", "search", {
    "table_name": "documents",
    "query_vector": query_embedding,
    "k": 10,
    "filter_conditions": "category = 'tech' AND published = true",
    "distance": "cosine"
})
```

### Different Distance Metrics

```python
# Cosine similarity (default, best for normalized vectors)
distance="cosine"  # Range: 0 (identical) to 2 (opposite)

# L2 distance (Euclidean distance)
distance="l2"  # Range: 0 (identical) to infinity

# Inner product (for non-normalized vectors)
distance="ip"  # Range: -infinity to +infinity
```

## Hybrid Search (Vector + Text)

Combine semantic similarity with PostgreSQL full-text search for best of both worlds:

```python
from dataflow.nodes.vector_nodes import HybridSearchNode

# Create full-text index first
await db.execute_query("""
    CREATE INDEX documents_content_fts
    ON documents
    USING gin(to_tsvector('english', content))
""")

# Hybrid search
workflow.add_node("HybridSearchNode", "search", {
    "table_name": "documents",
    "query_vector": query_embedding,
    "text_query": "machine learning",  # Text search term
    "k": 10,
    "vector_weight": 0.7,  # 70% weight to vector similarity
    "text_weight": 0.3,    # 30% weight to text relevance
    "text_column": "content"
})
```

## Integration with AI Frameworks

### Using with Kaizen (AI Agent Framework)

```python
from kaizen import EmbeddingAgent
from dataflow import DataFlow
from dataflow.adapters import PostgreSQLVectorAdapter

# Initialize embedding agent
embedding_agent = EmbeddingAgent(
    model="text-embedding-3-small",  # OpenAI
    dimensions=1536
)

# Initialize DataFlow with vector support
adapter = PostgreSQLVectorAdapter("postgresql://localhost/vectordb")
db = DataFlow(adapter=adapter)

@db.model
class KnowledgeBase:
    id: str
    topic: str
    content: str
    embedding: list[float]

await db.initialize()

# Embedding workflow
async def semantic_search(query: str, k: int = 5):
    # Generate query embedding
    query_vector = await embedding_agent.embed(query)

    # Search knowledge base
    workflow = WorkflowBuilder()
    workflow.add_node("VectorSearchNode", "search", {
        "table_name": "knowledge_base",
        "query_vector": query_vector,
        "k": k,
        "distance": "cosine"
    })

    runtime = AsyncLocalRuntime()
    results = await runtime.execute_workflow_async(workflow.build())
    return results["search"]["results"]

# Use in RAG pipeline
results = await semantic_search("How do I implement authentication?", k=3)
context = "\n".join([r["content"] for r in results])
# Pass context to LLM for generation
```

### Batch Embedding and Indexing

```python
from dataflow.nodes.bulk_create import BulkCreateNode

# Batch embed documents
documents = [
    {"id": "1", "title": "Doc 1", "content": "..."},
    {"id": "2", "title": "Doc 2", "content": "..."},
    # ... 1000 more
]

# Generate embeddings
for doc in documents:
    doc["embedding"] = await embedding_agent.embed(doc["content"])

# Bulk insert with vectors
workflow = WorkflowBuilder()
workflow.add_node("DocumentBulkCreateNode", "insert", {
    "data": documents
})

results = await runtime.execute_workflow_async(workflow.build())
print(f"Inserted {results['insert']['inserted']} documents")

# Create index after bulk insert
await adapter.create_vector_index(
    "documents",
    index_type="ivfflat",
    lists=int(len(documents) ** 0.5)  # sqrt(rows)
)
```

## Performance Optimization

### Index Selection

```python
# IVFFlat: Good for most use cases
- Build time: Fast
- Query time: Good
- Memory: Efficient
- Best for: 10K - 1M vectors

await adapter.create_vector_index(
    "documents",
    index_type="ivfflat",
    lists=100  # sqrt(total_rows), adjust based on data size
)

# HNSW: Better recall, slower build
- Build time: Slower
- Query time: Faster
- Memory: Higher
- Best for: High-precision requirements

await adapter.create_vector_index(
    "documents",
    index_type="hnsw",
    m=16,  # Higher m = better recall, more memory
    ef_construction=64  # Higher = better recall, slower build
)
```

### Connection Pooling

```python
# Configure connection pool for high throughput
adapter = PostgreSQLVectorAdapter(
    "postgresql://localhost/vectordb",
    pool_size=20,  # Max concurrent connections
    max_overflow=30  # Additional connections when needed
)
```

### Monitoring Vector Performance

```python
# Get vector column statistics
stats = await adapter.get_vector_stats("documents", "embedding")

print(f"Total vectors: {stats['total_vectors']}")
print(f"Non-null vectors: {stats['non_null_vectors']}")
print(f"Dimensions: {stats['dimensions']}")
```

## Common Patterns

### RAG (Retrieval-Augmented Generation)

```python
async def rag_pipeline(query: str, llm_client):
    """Complete RAG pipeline with vector search."""
    # 1. Generate query embedding
    query_vector = await embedding_agent.embed(query)

    # 2. Retrieve relevant documents
    workflow = WorkflowBuilder()
    workflow.add_node("VectorSearchNode", "search", {
        "table_name": "knowledge_base",
        "query_vector": query_vector,
        "k": 5,
        "distance": "cosine"
    })

    results = await runtime.execute_workflow_async(workflow.build())
    documents = results["search"]["results"]

    # 3. Build context
    context = "\n\n".join([
        f"Document {i+1}:\n{doc['content']}"
        for i, doc in enumerate(documents)
    ])

    # 4. Generate response with context
    prompt = f"""Use the following context to answer the question:

Context:
{context}

Question: {query}

Answer:"""

    response = await llm_client.generate(prompt)
    return response, documents
```

### Semantic Document Deduplication

```python
async def find_duplicates(threshold: float = 0.1):
    """Find similar documents using vector search."""
    # Get all documents
    all_docs = await db.execute_query("SELECT id, embedding FROM documents")

    duplicates = []
    for doc in all_docs:
        # Search for similar documents
        similar = await adapter.vector_search(
            "documents",
            doc["embedding"],
            k=5,
            distance="cosine"
        )

        # Check if any are below threshold (very similar)
        for match in similar:
            if match["id"] != doc["id"] and match["distance"] < threshold:
                duplicates.append((doc["id"], match["id"], match["distance"]))

    return duplicates
```

### Multi-language Search

```python
# Use multilingual embeddings for cross-language search
embedding_agent = EmbeddingAgent(
    model="multilingual-e5-large"  # Supports 100+ languages
)

# Documents in different languages
documents = [
    {"content": "Machine learning tutorial", "lang": "en"},
    {"content": "Tutorial de aprendizaje automático", "lang": "es"},
    {"content": "機械学習のチュートリアル", "lang": "ja"},
]

# Embed and store
for doc in documents:
    doc["embedding"] = await embedding_agent.embed(doc["content"])

# Search works across languages
query_vector = await embedding_agent.embed("How to learn AI?")  # English
# Will match relevant documents in all languages
```

## Troubleshooting

### pgvector Extension Not Available

```python
# Check if pgvector is installed
try:
    await adapter.ensure_pgvector_extension()
except RuntimeError as e:
    print(f"pgvector not available: {e}")
    # Install pgvector (see Prerequisites)
```

### Slow Vector Searches

```python
# 1. Create an index
await adapter.create_vector_index("documents", index_type="ivfflat")

# 2. Tune index parameters
# For IVFFlat: increase lists for more accuracy (slower)
# For HNSW: increase m and ef_construction

# 3. Use appropriate distance metric
# Cosine: Best for normalized vectors (most embedding models)
# L2: Best for non-normalized vectors
```

### Out of Memory Errors

```python
# 1. Reduce vector dimensions (if model supports it)
adapter = PostgreSQLVectorAdapter(
    connection_string,
    vector_dimensions=768  # Instead of 1536
)

# 2. Use IVFFlat instead of HNSW
# 3. Batch process large datasets
# 4. Increase PostgreSQL memory limits
```

## Best Practices

1. **Always create an index** for tables with >1000 vectors
2. **Use normalized embeddings** with cosine distance
3. **Batch insert** large datasets for better performance
4. **Monitor index size** and rebuild periodically
5. **Use connection pooling** for production workloads
6. **Choose appropriate k value** (typically 3-10 for RAG)
7. **Consider hybrid search** for better recall
8. **Version your embedding models** (track which model was used)

## Next Steps

- **Performance Tuning**: See `pgvector-performance-tuning.md`
- **Production Deployment**: See `pgvector-production-deployment.md`
- **Cost Comparison**: See `pgvector-vs-dedicated-vectordb.md`
- **Advanced Patterns**: See `pgvector-advanced-patterns.md`

## Resources

- [pgvector GitHub](https://github.com/pgvector/pgvector)
- [PostgreSQL Documentation](https://www.postgresql.org/docs/)
- [OpenAI Embeddings](https://platform.openai.com/docs/guides/embeddings)
- [DataFlow Documentation](../README.md)

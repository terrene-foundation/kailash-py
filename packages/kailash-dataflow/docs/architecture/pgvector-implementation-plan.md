# pgvector Implementation Plan - PostgreSQLVectorAdapter

## Overview

Implement PostgreSQL vector similarity search using the pgvector extension, enabling RAG (Retrieval-Augmented Generation) and semantic search capabilities in DataFlow.

## Objectives

1. Extend PostgreSQLAdapter with vector search capabilities
2. Create 3 new vector-specific workflow nodes
3. Integrate seamlessly with Kaizen AI framework
4. Maintain 100% backward compatibility
5. Achieve 40-60% cost savings vs dedicated vector DBs

## Architecture

### PostgreSQLVectorAdapter (Extends PostgreSQLAdapter)

```python
from dataflow.adapters.postgresql import PostgreSQLAdapter

class PostgreSQLVectorAdapter(PostgreSQLAdapter):
    """PostgreSQL with pgvector extension for vector similarity search."""

    def __init__(self, connection_string: str, **kwargs):
        super().__init__(connection_string, **kwargs)
        self.vector_dimensions = kwargs.get("vector_dimensions", 1536)  # OpenAI default
        self.default_distance = kwargs.get("default_distance", "cosine")

    def supports_feature(self, feature: str) -> bool:
        """Enhanced feature detection including vector operations."""
        if feature == "vector_search":
            return True
        if feature == "vector_index":
            return True
        if feature == "hybrid_search":  # vector + filter
            return True
        return super().supports_feature(feature)

    async def ensure_pgvector_extension(self) -> None:
        """Ensure pgvector extension is installed."""
        query = "CREATE EXTENSION IF NOT EXISTS vector"
        await self.execute_query(query)

    async def create_vector_column(
        self, table_name: str, column_name: str = "embedding",
        dimensions: int = None
    ) -> None:
        """Add vector column to existing table."""
        dims = dimensions or self.vector_dimensions
        query = f"ALTER TABLE {table_name} ADD COLUMN IF NOT EXISTS {column_name} vector({dims})"
        await self.execute_query(query)

    async def create_vector_index(
        self,
        table_name: str,
        column_name: str = "embedding",
        index_type: str = "ivfflat",
        distance: str = "cosine",
        lists: int = 100
    ) -> None:
        """
        Create vector index for fast similarity search.

        Args:
            table_name: Table name
            column_name: Vector column name
            index_type: "ivfflat" (good) or "hnsw" (better, pgvector 0.5.0+)
            distance: "cosine", "l2", or "ip" (inner product)
            lists: Number of IVF lists (for ivfflat), typically sqrt(rows)
        """
        distance_ops = {
            "cosine": "vector_cosine_ops",
            "l2": "vector_l2_ops",
            "ip": "vector_ip_ops"
        }

        ops = distance_ops.get(distance, "vector_cosine_ops")
        index_name = f"{table_name}_{column_name}_{index_type}_idx"

        if index_type == "ivfflat":
            query = f"""
            CREATE INDEX IF NOT EXISTS {index_name}
            ON {table_name} USING ivfflat ({column_name} {ops})
            WITH (lists = {lists})
            """
        elif index_type == "hnsw":
            # HNSW is better but requires pgvector 0.5.0+
            m = kwargs.get("m", 16)  # Max connections per layer
            ef_construction = kwargs.get("ef_construction", 64)  # Build time accuracy
            query = f"""
            CREATE INDEX IF NOT EXISTS {index_name}
            ON {table_name} USING hnsw ({column_name} {ops})
            WITH (m = {m}, ef_construction = {ef_construction})
            """
        else:
            raise ValueError(f"Unknown index type: {index_type}")

        await self.execute_query(query)

    async def vector_search(
        self,
        table_name: str,
        query_vector: list[float],
        k: int = 10,
        column_name: str = "embedding",
        distance: str = "cosine",
        filter_conditions: str = None,
        return_distance: bool = True
    ) -> list[dict]:
        """
        Semantic similarity search.

        Args:
            table_name: Table to search
            query_vector: Query embedding vector
            k: Number of results to return
            column_name: Vector column name
            distance: Distance metric ("cosine", "l2", "ip")
            filter_conditions: Optional WHERE clause (e.g., "category = 'tech'")
            return_distance: Include distance in results

        Returns:
            List of matching records with optional distance scores
        """
        distance_ops = {
            "cosine": "<=>",
            "l2": "<->",
            "ip": "<#>"
        }

        op = distance_ops.get(distance, "<=>")

        # Convert Python list to PostgreSQL array format
        vector_str = f"'[{','.join(map(str, query_vector))}]'"

        distance_select = f", {column_name} {op} {vector_str}::vector AS distance" if return_distance else ""
        where_clause = f"WHERE {filter_conditions}" if filter_conditions else ""

        query = f"""
        SELECT *{distance_select}
        FROM {table_name}
        {where_clause}
        ORDER BY {column_name} {op} {vector_str}::vector
        LIMIT {k}
        """

        return await self.execute_query(query)

    async def hybrid_search(
        self,
        table_name: str,
        query_vector: list[float],
        text_query: str = None,
        k: int = 10,
        vector_weight: float = 0.7,
        text_weight: float = 0.3,
        column_name: str = "embedding",
        text_column: str = "content"
    ) -> list[dict]:
        """
        Hybrid search combining vector similarity and full-text search.

        Uses RRF (Reciprocal Rank Fusion) to combine results.
        """
        # Vector search results
        vector_results = await self.vector_search(
            table_name, query_vector, k=k*2, column_name=column_name
        )

        if not text_query:
            return vector_results[:k]

        # Full-text search results
        text_query_sql = f"""
        SELECT *, ts_rank(to_tsvector('english', {text_column}),
                         to_tsquery('english', '{text_query}')) AS text_score
        FROM {table_name}
        WHERE to_tsvector('english', {text_column}) @@ to_tsquery('english', '{text_query}')
        ORDER BY text_score DESC
        LIMIT {k*2}
        """
        text_results = await self.execute_query(text_query_sql)

        # Combine using RRF
        combined_scores = {}
        for rank, result in enumerate(vector_results, 1):
            id_val = result.get('id')
            combined_scores[id_val] = vector_weight / (60 + rank)

        for rank, result in enumerate(text_results, 1):
            id_val = result.get('id')
            if id_val in combined_scores:
                combined_scores[id_val] += text_weight / (60 + rank)
            else:
                combined_scores[id_val] = text_weight / (60 + rank)

        # Get top k by combined score
        top_ids = sorted(combined_scores.items(), key=lambda x: x[1], reverse=True)[:k]

        # Fetch full records
        id_list = ','.join([f"'{id_val}'" for id_val, _ in top_ids])
        final_query = f"SELECT * FROM {table_name} WHERE id IN ({id_list})"

        return await self.execute_query(final_query)
```

## New Workflow Nodes

### 1. VectorSearchNode

```python
class VectorSearchNode(AsyncNode):
    """Semantic similarity search using vector embeddings."""

    parameters = {
        "table_name": NodeParameter(str, required=True),
        "query_vector": NodeParameter(list, required=True),
        "k": NodeParameter(int, default=10),
        "column_name": NodeParameter(str, default="embedding"),
        "distance": NodeParameter(str, default="cosine"),
        "filter_conditions": NodeParameter(str, default=None),
        "return_distance": NodeParameter(bool, default=True),
    }

    async def async_run(self):
        adapter = self.dataflow_instance.adapter

        if not isinstance(adapter, PostgreSQLVectorAdapter):
            raise ValueError("VectorSearch requires PostgreSQLVectorAdapter")

        results = await adapter.vector_search(
            table_name=self.table_name,
            query_vector=self.query_vector,
            k=self.k,
            column_name=self.column_name,
            distance=self.distance,
            filter_conditions=self.filter_conditions,
            return_distance=self.return_distance
        )

        return {"results": results, "count": len(results)}
```

### 2. CreateVectorIndexNode

```python
class CreateVectorIndexNode(AsyncNode):
    """Create vector index for fast similarity search."""

    parameters = {
        "table_name": NodeParameter(str, required=True),
        "column_name": NodeParameter(str, default="embedding"),
        "index_type": NodeParameter(str, default="ivfflat"),
        "distance": NodeParameter(str, default="cosine"),
        "lists": NodeParameter(int, default=100),
    }

    async def async_run(self):
        adapter = self.dataflow_instance.adapter

        if not isinstance(adapter, PostgreSQLVectorAdapter):
            raise ValueError("CreateVectorIndex requires PostgreSQLVectorAdapter")

        await adapter.create_vector_index(
            table_name=self.table_name,
            column_name=self.column_name,
            index_type=self.index_type,
            distance=self.distance,
            lists=self.lists
        )

        return {"success": True, "index_created": True}
```

### 3. HybridSearchNode

```python
class HybridSearchNode(AsyncNode):
    """Hybrid search combining vector similarity and full-text search."""

    parameters = {
        "table_name": NodeParameter(str, required=True),
        "query_vector": NodeParameter(list, required=True),
        "text_query": NodeParameter(str, default=None),
        "k": NodeParameter(int, default=10),
        "vector_weight": NodeParameter(float, default=0.7),
        "text_weight": NodeParameter(float, default=0.3),
        "column_name": NodeParameter(str, default="embedding"),
        "text_column": NodeParameter(str, default="content"),
    }

    async def async_run(self):
        adapter = self.dataflow_instance.adapter

        if not isinstance(adapter, PostgreSQLVectorAdapter):
            raise ValueError("HybridSearch requires PostgreSQLVectorAdapter")

        results = await adapter.hybrid_search(
            table_name=self.table_name,
            query_vector=self.query_vector,
            text_query=self.text_query,
            k=self.k,
            vector_weight=self.vector_weight,
            text_weight=self.text_weight,
            column_name=self.column_name,
            text_column=self.text_column
        )

        return {"results": results, "count": len(results)}
```

## Integration with Kaizen (AI Framework)

```python
from dataflow import DataFlow
from dataflow.adapters.postgresql_vector import PostgreSQLVectorAdapter
from kaizen import EmbeddingAgent
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime import AsyncLocalRuntime

# Initialize DataFlow with vector support
adapter = PostgreSQLVectorAdapter("postgresql://localhost/vectordb")
db = DataFlow(adapter=adapter)

# Define model with vector column
@db.model
class Document:
    id: str
    title: str
    content: str
    embedding: list[float]  # Auto-detected as vector column

# Initialize AI agent for embeddings
embedding_agent = EmbeddingAgent(model="text-embedding-3-small")

# Create workflow
workflow = WorkflowBuilder()

# Generate embedding
query = "machine learning tutorials"
query_embedding = await embedding_agent.embed(query)

# Semantic search
workflow.add_node("VectorSearchNode", "search", {
    "table_name": "Document",
    "query_vector": query_embedding,
    "k": 5,
    "filter_conditions": "category = 'tech'"
})

# Execute
runtime = AsyncLocalRuntime()
results = await runtime.execute_workflow_async(workflow.build())

# Access results
documents = results["search"]["results"]
for doc in documents:
    print(f"{doc['title']}: distance={doc['distance']}")
```

## Testing Strategy

### Unit Tests (Tier 1)
- PostgreSQLVectorAdapter initialization
- supports_feature() method
- Vector column creation
- Vector index creation
- Vector search query generation
- Parameter validation

### Integration Tests (Tier 2) - Real PostgreSQL + pgvector
- Install pgvector extension
- Create vector columns
- Create vector indexes (ivfflat, hnsw)
- Similarity search with various distance metrics
- Hybrid search (vector + full-text)
- Filter conditions with vector search
- Large-scale performance (100K+ vectors)

### End-to-End Tests (Tier 3) - Complete RAG Workflow
- Document ingestion with embeddings
- Semantic search workflow
- Integration with Kaizen EmbeddingAgent
- Multi-tenant vector isolation
- Performance benchmarks vs dedicated vector DBs

## Performance Targets

- **Query Latency**: <50ms for 100K vectors
- **Index Build Time**: <5 minutes for 1M vectors
- **Memory Efficiency**: <2GB for 1M vectors (1536 dimensions)
- **Throughput**: >100 QPS for semantic search

## Documentation

- pgvector-quickstart.md
- pgvector-rag-integration.md
- pgvector-vs-dedicated-vectordb.md
- pgvector-performance-tuning.md

## Timeline

- **Week 2, Day 1-2**: PostgreSQLVectorAdapter implementation
- **Week 2, Day 3-4**: 3 new vector nodes + unit tests
- **Week 2, Day 5**: Integration tests with real pgvector
- **Week 3, Day 1-2**: E2E tests + Kaizen integration
- **Week 3, Day 3-4**: Performance benchmarks
- **Week 3, Day 5**: Documentation + examples

**Total:** 2 weeks

## Success Criteria

✅ PostgreSQLVectorAdapter extends PostgreSQLAdapter
✅ 3 new vector nodes (VectorSearch, CreateVectorIndex, HybridSearch)
✅ 100% test coverage (unit + integration + E2E)
✅ Query latency <50ms for 100K vectors
✅ Seamless Kaizen integration
✅ Comprehensive documentation

---

**Status:** Ready to implement
**Risk:** LOW (extends proven PostgreSQL adapter)
**Value:** HIGHEST (enables RAG/AI applications)

"""
Complete RAG (Retrieval-Augmented Generation) Example using pgvector.

This example demonstrates:
1. Setting up DataFlow with PostgreSQLVectorAdapter
2. Creating a knowledge base with vector embeddings
3. Performing semantic search
4. Building a complete RAG pipeline

Prerequisites:
- PostgreSQL with pgvector extension installed
- OpenAI API key (or use any embedding model)
"""

import asyncio

from dataflow import DataFlow
from dataflow.adapters import PostgreSQLVectorAdapter
from dataflow.nodes.vector_nodes import (
    CreateVectorIndexNode,
    HybridSearchNode,
    VectorSearchNode,
)

from kailash.runtime import AsyncLocalRuntime
from kailash.workflow.builder import WorkflowBuilder


# Mock embedding function (replace with real embedding model)
async def get_embedding(text: str) -> list[float]:
    """
    Generate embedding for text.

    In production, use:
    - OpenAI: openai.embeddings.create(model="text-embedding-3-small", input=text)
    - Kaizen: await embedding_agent.embed(text)
    - Sentence Transformers: model.encode(text)
    """
    # Mock embedding (1536 dimensions, all 0.5 for demo)
    # In real use, this would be actual embeddings from an AI model
    import hashlib

    # Create a simple hash-based embedding for demo
    hash_value = int(hashlib.md5(text.encode()).hexdigest(), 16)
    base_value = (hash_value % 1000) / 1000.0
    return [base_value] * 1536


async def setup_knowledge_base():
    """Step 1: Set up DataFlow with pgvector and create knowledge base."""
    print("=" * 60)
    print("Step 1: Setting up Knowledge Base")
    print("=" * 60)

    # Create PostgreSQLVectorAdapter
    adapter = PostgreSQLVectorAdapter(
        "postgresql://user:password@localhost:5432/vectordb",
        vector_dimensions=1536,
        default_distance="cosine",
    )

    # Create DataFlow instance
    db = DataFlow(adapter=adapter)
    await db.initialize()

    # Define knowledge base model
    @db.model
    class KnowledgeBase:
        id: str
        topic: str
        content: str
        category: str
        embedding: list[float]

    print("✓ Knowledge base model created")

    # Sample knowledge base documents
    documents = [
        {
            "id": "doc1",
            "topic": "Authentication Best Practices",
            "content": "Use JWT tokens for stateless authentication. Always hash passwords with bcrypt. Implement refresh tokens for better security.",
            "category": "security",
        },
        {
            "id": "doc2",
            "topic": "Database Optimization",
            "content": "Create indexes on frequently queried columns. Use connection pooling. Implement query caching for better performance.",
            "category": "performance",
        },
        {
            "id": "doc3",
            "topic": "API Design",
            "content": "Follow REST principles. Use proper HTTP methods. Implement versioning for APIs. Document with OpenAPI/Swagger.",
            "category": "architecture",
        },
        {
            "id": "doc4",
            "topic": "Error Handling",
            "content": "Return meaningful error messages. Use proper HTTP status codes. Log errors for debugging. Implement global error handlers.",
            "category": "best-practices",
        },
        {
            "id": "doc5",
            "topic": "Testing Strategies",
            "content": "Write unit tests for business logic. Integration tests for APIs. Use mocking for external dependencies. Maintain high code coverage.",
            "category": "quality",
        },
    ]

    # Generate embeddings for all documents
    print("\n📝 Generating embeddings for documents...")
    for doc in documents:
        doc["embedding"] = await get_embedding(doc["content"])

    # Bulk insert documents with embeddings
    from dataflow.nodes.bulk_create import BulkCreateNode

    workflow = WorkflowBuilder()
    workflow.add_node("KnowledgeBaseBulkCreateNode", "insert", {"data": documents})

    runtime = AsyncLocalRuntime()
    results = await runtime.execute_workflow_async(workflow.build())

    print(f"✓ Inserted {results['insert']['inserted']} documents")

    return db, adapter


async def create_vector_index(db, adapter):
    """Step 2: Create vector index for fast similarity search."""
    print("\n" + "=" * 60)
    print("Step 2: Creating Vector Index")
    print("=" * 60)

    # Create IVFFlat index
    await adapter.create_vector_index(
        "knowledge_base",
        column_name="embedding",
        index_type="ivfflat",
        distance="cosine",
        lists=10,  # Small for demo, use sqrt(total_rows) in production
    )

    print("✓ IVFFlat vector index created on knowledge_base.embedding")

    # Alternative: Create HNSW index (better performance, requires pgvector 0.5.0+)
    # await adapter.create_vector_index(
    #     "knowledge_base",
    #     index_type="hnsw",
    #     distance="cosine",
    #     m=16,
    #     ef_construction=64
    # )


async def semantic_search_example(db):
    """Step 3: Perform semantic search."""
    print("\n" + "=" * 60)
    print("Step 3: Semantic Search Example")
    print("=" * 60)

    # User query
    query = "How do I secure my authentication system?"
    print(f"\n🔍 Query: '{query}'")

    # Generate query embedding
    query_embedding = await get_embedding(query)

    # Create search workflow
    workflow = WorkflowBuilder()
    workflow.add_node(
        "VectorSearchNode",
        "search",
        {
            "table_name": "knowledge_base",
            "query_vector": query_embedding,
            "k": 3,  # Return top 3 results
            "distance": "cosine",
            "return_distance": True,
        },
    )

    runtime = AsyncLocalRuntime()
    results = await runtime.execute_workflow_async(workflow.build())

    # Display results
    print(f"\n📋 Found {results['search']['count']} relevant documents:\n")
    for i, doc in enumerate(results["search"]["results"], 1):
        print(f"{i}. {doc['topic']}")
        print(f"   Category: {doc['category']}")
        print(f"   Distance: {doc['distance']:.4f}")
        print(f"   Content: {doc['content'][:80]}...")
        print()

    return results["search"]["results"]


async def filtered_search_example(db):
    """Step 4: Search with filters."""
    print("\n" + "=" * 60)
    print("Step 4: Filtered Search Example")
    print("=" * 60)

    query = "How to improve application performance?"
    print(f"\n🔍 Query: '{query}'")
    print("📁 Filter: category = 'performance'")

    query_embedding = await get_embedding(query)

    workflow = WorkflowBuilder()
    workflow.add_node(
        "VectorSearchNode",
        "search",
        {
            "table_name": "knowledge_base",
            "query_vector": query_embedding,
            "k": 5,
            "filter_conditions": "category = 'performance'",
            "distance": "cosine",
        },
    )

    runtime = AsyncLocalRuntime()
    results = await runtime.execute_workflow_async(workflow.build())

    print(f"\n📋 Found {results['search']['count']} results in 'performance' category:")
    for doc in results["search"]["results"]:
        print(f"  - {doc['topic']}")


async def hybrid_search_example(db, adapter):
    """Step 5: Hybrid search (vector + full-text)."""
    print("\n" + "=" * 60)
    print("Step 5: Hybrid Search Example")
    print("=" * 60)

    # Create full-text index first
    try:
        async with adapter._pool.acquire() as conn:
            await conn.execute(
                """
                CREATE INDEX IF NOT EXISTS knowledge_base_content_fts
                ON knowledge_base
                USING gin(to_tsvector('english', content))
            """
            )
        print("✓ Full-text search index created")
    except Exception as e:
        print(f"⚠️  Full-text index creation: {e}")

    query = "API testing strategies"
    text_search = "testing"
    print(f"\n🔍 Semantic Query: '{query}'")
    print(f"📝 Text Search: '{text_search}'")

    query_embedding = await get_embedding(query)

    workflow = WorkflowBuilder()
    workflow.add_node(
        "HybridSearchNode",
        "search",
        {
            "table_name": "knowledge_base",
            "query_vector": query_embedding,
            "text_query": text_search,
            "k": 3,
            "vector_weight": 0.7,
            "text_weight": 0.3,
            "text_column": "content",
        },
    )

    runtime = AsyncLocalRuntime()
    results = await runtime.execute_workflow_async(workflow.build())

    print(f"\n📋 Hybrid search found {results['search']['count']} results:")
    print(f"   Search type: {results['search']['search_type']}")
    for doc in results["search"]["results"]:
        print(f"  - {doc['topic']}")


async def rag_pipeline_example(db):
    """Step 6: Complete RAG pipeline."""
    print("\n" + "=" * 60)
    print("Step 6: Complete RAG Pipeline")
    print("=" * 60)

    user_question = "What are the best practices for API authentication?"
    print(f"\n❓ User Question: '{user_question}'")

    # 1. Retrieve relevant context
    query_embedding = await get_embedding(user_question)

    workflow = WorkflowBuilder()
    workflow.add_node(
        "VectorSearchNode",
        "search",
        {
            "table_name": "knowledge_base",
            "query_vector": query_embedding,
            "k": 3,
            "distance": "cosine",
        },
    )

    runtime = AsyncLocalRuntime()
    results = await runtime.execute_workflow_async(workflow.build())

    # 2. Build context from retrieved documents
    context_docs = results["search"]["results"]
    context = "\n\n".join(
        [f"Document {i+1}:\n{doc['content']}" for i, doc in enumerate(context_docs)]
    )

    print("\n📚 Retrieved Context:")
    print("-" * 60)
    print(context)
    print("-" * 60)

    # 3. Generate prompt for LLM
    prompt = f"""Use the following context to answer the question.

Context:
{context}

Question: {user_question}

Answer:"""

    print("\n🤖 LLM Prompt:")
    print("-" * 60)
    print(prompt)
    print("-" * 60)

    # 4. In production, call LLM here
    print("\n💡 In production, call your LLM (OpenAI, Claude, etc.) with this prompt")
    print("   Example:")
    print("   response = await openai.chat.completions.create(")
    print("       model='gpt-4',")
    print("       messages=[{'role': 'user', 'content': prompt}]")
    print("   )")


async def main():
    """Run complete pgvector RAG example."""
    print("\n" + "=" * 60)
    print("pgvector RAG Example - Complete Demonstration")
    print("=" * 60)

    try:
        # Step 1: Setup
        db, adapter = await setup_knowledge_base()

        # Step 2: Create index
        await create_vector_index(db, adapter)

        # Step 3: Semantic search
        await semantic_search_example(db)

        # Step 4: Filtered search
        await filtered_search_example(db)

        # Step 5: Hybrid search
        await hybrid_search_example(db, adapter)

        # Step 6: Complete RAG pipeline
        await rag_pipeline_example(db)

        print("\n" + "=" * 60)
        print("✅ Example Complete!")
        print("=" * 60)
        print("\nNext Steps:")
        print("1. Replace mock embeddings with real AI model (OpenAI, Kaizen, etc.)")
        print("2. Connect to your PostgreSQL database")
        print("3. Scale up with more documents")
        print("4. Integrate with your LLM for complete RAG")
        print("5. See docs/guides/pgvector-quickstart.md for more examples")

        # Cleanup
        await adapter.disconnect()

    except Exception as e:
        print(f"\n❌ Error: {e}")
        print("\nMake sure:")
        print("1. PostgreSQL is running")
        print("2. pgvector extension is installed")
        print("3. Database credentials are correct")
        raise


if __name__ == "__main__":
    # Run the example
    asyncio.run(main())

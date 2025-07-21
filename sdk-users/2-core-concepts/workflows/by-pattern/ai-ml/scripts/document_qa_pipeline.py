#!/usr/bin/env python3
"""
Document Q&A Pipeline with Kailash SDK
=====================================

This script demonstrates a document Q&A workflow that:
1. Loads documents from CSV/text sources
2. Chunks documents intelligently
3. Generates embeddings for similarity search
4. Finds relevant chunks for queries
5. Uses LLM to generate answers

Key Features:
- Uses native Kailash nodes throughout
- Implements RAG (Retrieval Augmented Generation)
- Handles document chunking and embedding
- Production-ready patterns
"""

from kailash import Workflow
from kailash.nodes.ai import EmbeddingGeneratorNode, LLMAgentNode
from kailash.nodes.data import DocumentSourceNode, QuerySourceNode, RelevanceScorerNode
from kailash.nodes.transform import DataTransformer, HierarchicalChunkerNode
from kailash.runtime.local import LocalRuntime


def create_qa_workflow() -> Workflow:
    """Create a document Q&A workflow."""
    workflow = Workflow(
        workflow_id="doc_qa_001",
        name="document_qa_pipeline",
        description="RAG-based document Q&A system",
    )

    # Document source
    doc_source = DocumentSourceNode(id="doc_source")
    workflow.add_node("doc_source", doc_source)

    # Query source
    query_source = QuerySourceNode(id="query_source")
    workflow.add_node("query_source", query_source)

    # Chunk documents
    chunker = HierarchicalChunkerNode(id="doc_chunker")
    workflow.add_node("doc_chunker", chunker)
    workflow.connect("doc_source", "doc_chunker", mapping={"documents": "documents"})

    # Generate embeddings for chunks
    chunk_embedder = EmbeddingGeneratorNode(
        id="chunk_embedder", model="text-embedding-3-small", dimensions=1536
    )
    workflow.add_node("chunk_embedder", chunk_embedder)
    workflow.connect("doc_chunker", "chunk_embedder", mapping={"chunks": "texts"})

    # Generate embedding for query
    query_embedder = EmbeddingGeneratorNode(
        id="query_embedder", model="text-embedding-3-small", dimensions=1536
    )
    workflow.add_node("query_embedder", query_embedder)
    workflow.connect("query_source", "query_embedder", mapping={"query": "texts"})

    # Find relevant chunks
    relevance_scorer = RelevanceScorerNode(id="relevance_scorer")
    workflow.add_node("relevance_scorer", relevance_scorer)
    workflow.connect("doc_chunker", "relevance_scorer", mapping={"chunks": "chunks"})
    workflow.connect(
        "query_embedder", "relevance_scorer", mapping={"embeddings": "query_embedding"}
    )
    workflow.connect(
        "chunk_embedder", "relevance_scorer", mapping={"embeddings": "chunk_embeddings"}
    )

    # Generate answer using LLM
    answer_generator = LLMAgentNode(
        id="answer_generator",
        model="gpt-3.5-turbo",
        system_prompt="You are a helpful assistant. Answer questions based on the provided context. If you cannot answer based on the context, say so.",
    )
    workflow.add_node("answer_generator", answer_generator)
    workflow.connect(
        "relevance_scorer", "answer_generator", mapping={"relevant_chunks": "context"}
    )
    workflow.connect("query_source", "answer_generator", mapping={"query": "question"})

    return workflow


def run_qa_pipeline(query: str = "What are the main types of machine learning?"):
    """Run the Q&A pipeline."""
    workflow = create_qa_workflow()
    runtime = LocalRuntime()

    parameters = {
        "query_source": {"query": query},
        "doc_chunker": {
            "chunk_size": 500,
            "chunk_overlap": 50,
            "chunking_strategy": "sentence",  # sentence, paragraph, or fixed
            "preserve_structure": True,
        },
        "chunk_embedder": {
            # texts will come from chunker output
        },
        "query_embedder": {
            # texts will come from query source, but we need to format as list
            "texts": [query]
        },
        "relevance_scorer": {
            "similarity_method": "cosine",
            "top_k": 3,
            "score_threshold": 0.5,
        },
        "answer_generator": {
            "prompt": """Question: {{question}}

Context:
{% for chunk in context %}
- {{ chunk.content }}
{% endfor %}

Please provide a comprehensive answer based on the context above.""",
            "temperature": 0.7,
            "max_tokens": 500,
        },
    }

    try:
        print(f"Processing query: {query}")
        result, run_id = runtime.execute(workflow, parameters=parameters)

        # Extract answer
        answer = result.get("answer_generator", {}).get(
            "response", "No answer generated"
        )
        print(f"\n=== Answer ===\n{answer}\n")

        return result
    except Exception as e:
        print(f"Q&A pipeline failed: {str(e)}")
        raise


def create_simple_qa_workflow() -> Workflow:
    """Create a simplified Q&A workflow for testing."""
    workflow = Workflow(
        workflow_id="simple_qa_001",
        name="simple_qa_pipeline",
        description="Simplified Q&A for testing",
    )

    # For demo: Create sample documents
    doc_transformer = DataTransformer(
        id="doc_creator",
        transformations=[
            """
result = [
    {
        "id": "doc1",
        "title": "Introduction to Machine Learning",
        "content": "Machine learning is a subset of artificial intelligence that enables computers to learn from data. There are three main types of machine learning: supervised learning (learning from labeled data), unsupervised learning (finding patterns in unlabeled data), and reinforcement learning (learning through interaction with an environment)."
    },
    {
        "id": "doc2",
        "title": "Deep Learning Fundamentals",
        "content": "Deep learning uses artificial neural networks with multiple layers. Popular architectures include CNNs for image processing, RNNs for sequences, and transformers for natural language processing. Deep learning has achieved breakthrough results in computer vision and NLP."
    }
]
"""
        ],
    )
    workflow.add_node("doc_creator", doc_transformer)

    # Simple chunker using DataTransformer
    chunker = DataTransformer(
        id="simple_chunker",
        transformations=[
            """
# Simple sentence-based chunking
chunks = []
chunk_id = 0
for doc in data:
    sentences = doc['content'].split('. ')
    for i in range(0, len(sentences), 2):  # Group 2 sentences
        chunk_text = '. '.join(sentences[i:i+2])
        if chunk_text:
            chunks.append({
                'id': f"chunk_{chunk_id}",
                'doc_id': doc['id'],
                'content': chunk_text,
                'doc_title': doc['title']
            })
            chunk_id += 1
result = chunks
"""
        ],
    )
    workflow.add_node("simple_chunker", chunker)
    workflow.connect("doc_creator", "simple_chunker", mapping={"result": "data"})

    # Context assembler
    context_builder = DataTransformer(
        id="context_builder",
        transformations=[
            """
# Build context from chunks
context_text = "Here is the relevant information:\\n\\n"
for chunk in data:
    context_text += f"From '{chunk['doc_title']}':\\n{chunk['content']}\\n\\n"
result = {"context": context_text, "chunks": data}
"""
        ],
    )
    workflow.add_node("context_builder", context_builder)
    workflow.connect("simple_chunker", "context_builder", mapping={"result": "data"})

    return workflow


def run_simple_qa():
    """Run simplified Q&A without embeddings."""
    workflow = create_simple_qa_workflow()
    runtime = LocalRuntime()

    parameters = {"doc_creator": {}, "simple_chunker": {}, "context_builder": {}}

    try:
        print("Running simple Q&A pipeline...")
        result, run_id = runtime.execute(workflow, parameters=parameters)

        # Get context
        context = (
            result.get("context_builder", {})
            .get("result", {})
            .get("context", "No context")
        )
        print(f"\n=== Context Built ===\n{context}\n")

        print(
            "Note: In production, add LLMAgentNode to generate answers from this context"
        )

        return result
    except Exception as e:
        print(f"Simple Q&A failed: {str(e)}")
        raise


def main():
    """Main entry point."""
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "simple":
        # Run simple version without embeddings/LLM
        run_simple_qa()
    else:
        # Note: Full version requires API keys for embeddings and LLM
        print("Full Q&A pipeline requires OpenAI API key")
        print("Run with 'simple' argument for simplified demo:")
        print("  python document_qa_pipeline.py simple")

        # For demo, run simple version
        run_simple_qa()


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Simple Hierarchical RAG Workflow Example

This example demonstrates a complete hierarchical Retrieval-Augmented Generation
workflow using the correct architecture pattern: Data Source → Processing → Output.

The workflow implements a multi-level document processing pipeline:
1. Document Reading - Load text documents
2. Hierarchical Chunking - Split into semantic chunks
3. Embedding Generation - Create vector embeddings
4. Query Processing - Process user query
5. Relevance Retrieval - Find relevant chunks
6. Answer Generation - Generate final response

Architecture: Uses autonomous data source nodes and proper node connections
without relying on external input injection.
"""

from kailash.nodes.ai.embedding_generator import EmbeddingGeneratorNode
from kailash.nodes.ai.llm_agent import LLMAgentNode
from kailash.nodes.data.retrieval import RelevanceScorerNode
from kailash.nodes.data.sources import DocumentSourceNode, QuerySourceNode
from kailash.nodes.transform.chunkers import HierarchicalChunkerNode
from kailash.nodes.transform.formatters import (
    ChunkTextExtractorNode,
    ContextFormatterNode,
    QueryTextWrapperNode,
)
from kailash.workflow import Workflow


def create_hierarchical_rag_workflow():
    """Create and configure the hierarchical RAG workflow."""

    # Create workflow
    workflow = Workflow(
        workflow_id="hierarchical_rag_example",
        name="Hierarchical RAG Workflow",
        description="Simple hierarchical RAG workflow using LLMAgentNode and EmbeddingGeneratorNode with Ollama",
        version="1.0.0",
    )

    # Create nodes
    doc_source = DocumentSourceNode()
    chunker = HierarchicalChunkerNode()
    query_source = QuerySourceNode()

    # Create embedding generators with proper Ollama configuration
    chunk_embedder = EmbeddingGeneratorNode(
        provider="ollama",
        model="nomic-embed-text",
        api_key="not-needed",
        operation="embed_batch",
    )

    query_embedder = EmbeddingGeneratorNode(
        provider="ollama",
        model="nomic-embed-text",
        api_key="not-needed",
        operation="embed_batch",
    )

    # Create text processing nodes
    chunk_text_extractor = ChunkTextExtractorNode()
    query_text_wrapper = QueryTextWrapperNode()

    # Create other processing nodes
    relevance_scorer = RelevanceScorerNode()
    context_formatter = ContextFormatterNode()

    # Create LLM agent for final answer generation
    llm_agent = LLMAgentNode(
        provider="ollama",
        model="llama3.2",
        api_key="not-needed",
        temperature=0.7,
        max_tokens=500,
    )

    # Add nodes to workflow
    workflow.add_node("doc_source", doc_source)
    workflow.add_node("chunker", chunker)
    workflow.add_node("query_source", query_source)
    workflow.add_node("chunk_text_extractor", chunk_text_extractor)
    workflow.add_node("query_text_wrapper", query_text_wrapper)
    workflow.add_node("chunk_embedder", chunk_embedder)
    workflow.add_node("query_embedder", query_embedder)
    workflow.add_node("relevance_scorer", relevance_scorer)
    workflow.add_node("context_formatter", context_formatter)
    workflow.add_node("llm_agent", llm_agent)

    # Connect the workflow
    # Document processing pipeline
    workflow.connect("doc_source", "chunker", {"documents": "documents"})
    workflow.connect("chunker", "chunk_text_extractor", {"chunks": "chunks"})
    workflow.connect(
        "chunk_text_extractor", "chunk_embedder", {"input_texts": "input_texts"}
    )

    # Query processing pipeline
    workflow.connect("query_source", "query_text_wrapper", {"query": "query"})
    workflow.connect(
        "query_text_wrapper", "query_embedder", {"input_texts": "input_texts"}
    )

    # Relevance scoring (needs chunks, query embedding, and chunk embeddings)
    workflow.connect("chunker", "relevance_scorer", {"chunks": "chunks"})
    workflow.connect(
        "query_embedder", "relevance_scorer", {"embeddings": "query_embedding"}
    )
    workflow.connect(
        "chunk_embedder", "relevance_scorer", {"embeddings": "chunk_embeddings"}
    )

    # Context formatting
    workflow.connect(
        "relevance_scorer", "context_formatter", {"relevant_chunks": "relevant_chunks"}
    )
    workflow.connect("query_source", "context_formatter", {"query": "query"})

    # Final answer generation
    workflow.connect("context_formatter", "llm_agent", {"messages": "messages"})

    return workflow


def main():
    """Run the hierarchical RAG workflow example."""
    print("🚀 Starting Hierarchical RAG Workflow Example")
    print("=" * 50)

    try:
        # Create workflow
        workflow = create_hierarchical_rag_workflow()

        print("📋 Workflow created with nodes:")
        for node_id in workflow.graph.nodes():
            print(f"  - {node_id}")

        print("\n🔗 Node connections:")
        for source, target, data in workflow.graph.edges(data=True):
            print(f"  {source} → {target}: {data}")

        # Execute workflow
        print("\n⚡ Executing workflow...")
        results, run_id = workflow.execute()

        print("\n📊 Workflow Results:")
        print("-" * 30)

        # Display key results
        for node_id, result in results.items():
            if node_id == "context_formatter":
                print("\n📝 Context Generated:")
                print(result.get("context", "No context"))

            elif node_id == "llm_agent":
                print("\n🤖 Final Answer:")
                print(result.get("response", "No response"))

            elif node_id == "relevance_scorer":
                chunks = result.get("relevant_chunks", [])
                print(f"\n🎯 Top Relevant Chunks ({len(chunks)}):")
                for chunk in chunks[:3]:
                    print(
                        f"  - {chunk['document_title']}: {chunk['relevance_score']:.3f}"
                    )

        print("\n✅ Hierarchical RAG workflow completed successfully!")

        # Export Mermaid diagram
        print("\n🎨 Mermaid Diagram:")

        # Save diagram to file
        workflow.save_mermaid_markdown(
            "../data/hierarchical_rag_workflow.md", title="Hierarchical RAG Workflow"
        )
        print("📄 Diagram saved to: ../data/hierarchical_rag_workflow.md")

    except Exception as e:
        print(f"\n❌ Error running workflow: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()

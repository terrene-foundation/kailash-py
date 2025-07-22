#!/usr/bin/env python3
"""
Intelligent Document Processing with Kailash SDK
===============================================

This script demonstrates an AI-powered document processing workflow that:
1. Ingests documents from multiple sources
2. Extracts and chunks content intelligently
3. Generates embeddings for semantic search
4. Processes queries with RAG (Retrieval Augmented Generation)
5. Provides structured outputs with citations

Key Features:
- Uses native AI nodes (LLMAgentNode, EmbeddingGeneratorNode)
- Implements hierarchical document processing
- Supports multiple document formats
- Production-ready error handling
"""

from kailash import Workflow
from kailash.nodes.ai import EmbeddingGeneratorNode, LLMAgentNode
from kailash.nodes.data import CSVReaderNode, DocumentSourceNode, RelevanceScorerNode
from kailash.nodes.logic import MergeNode
from kailash.nodes.transform import FilterNode, HierarchicalChunkerNode
from kailash.runtime.local import LocalRuntime


def create_document_processor_workflow() -> Workflow:
    """Create an intelligent document processing workflow."""
    workflow = Workflow(
        workflow_id="intelligent_doc_processor", name="intelligent_doc_processor"
    )

    # Document ingestion
    doc_source = DocumentSourceNode(name="document_source")
    workflow.add_node("document_source", doc_source)

    # Intelligent chunking
    chunker = HierarchicalChunkerNode(name="document_chunker")
    workflow.add_node("document_chunker", chunker)
    workflow.connect(
        "document_source", "document_chunker", mapping={"documents": "documents"}
    )

    # Generate embeddings for chunks
    chunk_embedder = EmbeddingGeneratorNode(
        name="chunk_embedder", model="text-embedding-3-small"
    )
    workflow.add_node("chunk_embedder", chunk_embedder)
    workflow.connect("document_chunker", "chunk_embedder", mapping={"chunks": "texts"})

    # Query processing - get query embedding
    query_embedder = EmbeddingGeneratorNode(
        name="query_embedder", model="text-embedding-3-small"
    )
    workflow.add_node("query_embedder", query_embedder)

    # Relevance scoring
    relevance_scorer = RelevanceScorerNode(name="relevance_scorer")
    workflow.add_node("relevance_scorer", relevance_scorer)
    workflow.connect(
        "document_chunker", "relevance_scorer", mapping={"chunks": "chunks"}
    )
    workflow.connect(
        "query_embedder",
        "relevance_scorer",
        mapping={"embeddings": "query_embedding"},
    )
    workflow.connect(
        "chunk_embedder",
        "relevance_scorer",
        mapping={"embeddings": "chunk_embeddings"},
    )

    # Context assembly for LLM
    context_assembler = LLMAgentNode(
        name="context_assembler",
        model="gpt-4",
        system_prompt="You are a helpful assistant that assembles context from document chunks.",
    )
    workflow.add_node("context_assembler", context_assembler)
    workflow.connect(
        "relevance_scorer",
        "context_assembler",
        mapping={"relevant_chunks": "context"},
    )

    # Final answer generation
    answer_generator = LLMAgentNode(
        name="answer_generator",
        model="gpt-4",
        system_prompt="You are an expert assistant. Answer questions based on the provided context. Always cite your sources.",
    )
    workflow.add_node("answer_generator", answer_generator)
    workflow.connect(
        "context_assembler",
        "answer_generator",
        mapping={"response": "enriched_context"},
    )

    # Structured output formatter
    output_formatter = LLMAgentNode(
        name="output_formatter",
        model="gpt-3.5-turbo",
        system_prompt="Format the answer as structured JSON with fields: answer, confidence, citations, key_points",
    )
    workflow.add_node("output_formatter", output_formatter)
    workflow.connect(
        "answer_generator", "output_formatter", mapping={"response": "raw_answer"}
    )

    return workflow


def run_document_processor(
    query: str = "What are the main types of machine learning?",
):
    """Execute the document processing workflow."""
    workflow = create_document_processor_workflow()
    runtime = LocalRuntime()

    # Define runtime parameters
    parameters = {
        "document_source": {"sample_documents": True},  # Use built-in samples
        "document_chunker": {
            "chunk_size": 500,
            "chunk_overlap": 50,
            "chunking_strategy": "semantic",
            "preserve_structure": True,
        },
        "query_embedder": {"texts": [query]},
        "relevance_scorer": {"similarity_method": "cosine", "top_k": 5},
        "context_assembler": {
            "prompt": f"""
Given these relevant document chunks, create a comprehensive context for answering the question: "{query}"

Chunks:
{{context}}

Create a well-organized context that:
1. Identifies the most relevant information
2. Maintains logical flow
3. Preserves important details and relationships
"""
        },
        "answer_generator": {
            "prompt": f"""
Question: {query}

Context:
{{enriched_context}}

Please provide a comprehensive answer that:
1. Directly addresses the question
2. Uses information from the context
3. Includes specific citations
4. Identifies any limitations or gaps
"""
        },
        "output_formatter": {
            "prompt": """
Format this answer as a JSON object:

{{raw_answer}}

Required JSON structure:
{
    "answer": "The main answer text",
    "confidence": 0.95,
    "citations": ["source1", "source2"],
    "key_points": ["point1", "point2"],
    "limitations": ["any caveats or gaps"]
}
"""
        },
    }

    try:
        print(f"Processing query: {query}")
        result, run_id = runtime.execute(workflow, parameters=parameters)

        # Extract formatted answer
        formatted_output = result.get("output_formatter", {}).get("response", {})
        print("\n=== Answer ===")
        print(formatted_output)

        return result
    except Exception as e:
        print(f"Document processing failed: {str(e)}")
        raise


def create_customer_support_workflow() -> Workflow:
    """Create a customer support document processor."""
    workflow = Workflow(
        workflow_id="customer_support_processor", name="customer_support_processor"
    )

    # Load customer data
    customer_data = CSVReaderNode(
        name="customer_loader", file_path="data/customers.csv"
    )
    workflow.add_node("customer_loader", customer_data)

    # Load support tickets
    ticket_source = DocumentSourceNode(name="ticket_source")
    workflow.add_node("ticket_source", ticket_source)

    # Filter relevant customers
    customer_filter = FilterNode(name="active_customers")
    workflow.add_node("active_customers", customer_filter)
    workflow.connect("customer_loader", "active_customers", mapping={"data": "data"})

    # Analyze ticket sentiment
    sentiment_analyzer = LLMAgentNode(
        name="sentiment_analyzer",
        model="gpt-3.5-turbo",
        system_prompt="Analyze customer support ticket sentiment. Classify as: positive, neutral, negative, critical",
    )
    workflow.add_node("sentiment_analyzer", sentiment_analyzer)
    workflow.connect(
        "ticket_source", "sentiment_analyzer", mapping={"documents": "tickets"}
    )

    # Generate personalized responses
    response_generator = LLMAgentNode(
        name="response_generator",
        model="gpt-4",
        system_prompt="Generate helpful, empathetic customer support responses",
    )
    workflow.add_node("response_generator", response_generator)

    # Merge customer context
    context_merger = MergeNode(name="context_merger")
    workflow.add_node("context_merger", context_merger)
    workflow.connect(
        "active_customers",
        "context_merger",
        mapping={"filtered_data": "customer_data"},
    )
    workflow.connect(
        "sentiment_analyzer",
        "context_merger",
        mapping={"response": "ticket_analysis"},
    )

    # Connect merged context to response generator
    workflow.connect(
        "context_merger", "response_generator", mapping={"merged_data": "context"}
    )

    return workflow


def main():
    """Main entry point."""
    import sys

    # Check command line arguments
    if len(sys.argv) > 1 and sys.argv[1] == "support":
        print("Running customer support workflow...")
        create_customer_support_workflow()
        # Would run with appropriate parameters
    else:
        # Default: Run document Q&A
        queries = [
            "What are the main types of machine learning?",
            "How do neural networks learn?",
            "What is natural language processing used for?",
        ]

        for query in queries:
            print(f"\n{'='*60}")
            run_document_processor(query)
            print(f"{'='*60}\n")


if __name__ == "__main__":
    main()

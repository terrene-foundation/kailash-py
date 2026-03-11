"""
Basic RAG Workflow with Document Extraction

Demonstrates:
1. Document extraction with RAG chunking
2. Chunk-based semantic search (simulated)
3. Question answering over document chunks
4. Cost optimization with free Ollama provider

This example shows how to extract documents and prepare them for RAG workflows.
"""

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

from kaizen.agents.multi_modal.document_extraction_agent import (
    DocumentExtractionAgent,
    DocumentExtractionConfig,
)


@dataclass
class BasicRAGConfig:
    """Configuration for basic RAG workflow."""

    # Document extraction settings
    provider: str = "ollama_vision"  # Use free local provider
    chunk_size: int = 512  # Smaller chunks for better retrieval
    extract_tables: bool = True

    # LLM settings for Q&A
    llm_provider: str = "ollama"
    model: str = "llama2"


class BasicRAGWorkflow:
    """
    Basic RAG workflow demonstrating document extraction and Q&A.

    Pipeline:
    1. Extract document → Get text and chunks
    2. Store chunks → Simulated vector store
    3. Query → Retrieve relevant chunks
    4. Answer → Generate answer from chunks
    """

    def __init__(self, config: BasicRAGConfig):
        """Initialize RAG workflow."""
        self.config = config
        self.chunks: List[Dict[str, Any]] = []  # In-memory chunk store

        # Create document extraction agent
        agent_config = DocumentExtractionConfig(
            llm_provider=config.llm_provider,
            model=config.model,
            provider=config.provider,
            chunk_for_rag=True,
            chunk_size=config.chunk_size,
        )

        self.doc_agent = DocumentExtractionAgent(config=agent_config)

        print("✅ RAG workflow initialized")
        print(f"   Provider: {config.provider} ($0.00 per document)")
        print(f"   Chunk size: {config.chunk_size} tokens")

    def ingest_document(self, file_path: str) -> Dict[str, Any]:
        """
        Ingest document and prepare chunks for RAG.

        Args:
            file_path: Path to document file

        Returns:
            Dict with extraction results and chunk count
        """
        print(f"\n📄 Ingesting document: {Path(file_path).name}")

        # Extract with RAG chunking
        result = self.doc_agent.extract(
            file_path=file_path,
            extract_tables=self.config.extract_tables,
            chunk_for_rag=True,
            chunk_size=self.config.chunk_size,
        )

        # Store chunks in memory (in production, use a vector database)
        self.chunks.extend(result["chunks"])

        print(f"   ✓ Extracted {len(result['text'])} characters")
        print(f"   ✓ Generated {len(result['chunks'])} chunks")
        print(f"   ✓ Provider: {result['provider']}")
        print(f"   ✓ Cost: ${result['cost']:.3f}")

        return {
            "file_path": file_path,
            "text_length": len(result["text"]),
            "num_chunks": len(result["chunks"]),
            "provider": result["provider"],
            "cost": result["cost"],
        }

    def retrieve_chunks(self, query: str, top_k: int = 3) -> List[Dict[str, Any]]:
        """
        Retrieve most relevant chunks for query.

        Args:
            query: User query
            top_k: Number of chunks to retrieve

        Returns:
            List of relevant chunks

        Note:
            This is a simple keyword-based retrieval for demonstration.
            In production, use semantic embeddings with a vector database.
        """
        print(f"\n🔍 Retrieving chunks for query: '{query}'")

        # Simple keyword-based scoring (for demonstration)
        query_words = set(query.lower().split())
        scored_chunks = []

        for chunk in self.chunks:
            chunk_text = chunk.get("text", "").lower()
            # Count matching words
            matches = sum(1 for word in query_words if word in chunk_text)
            score = matches / len(query_words) if query_words else 0

            scored_chunks.append(
                {
                    "chunk": chunk,
                    "score": score,
                }
            )

        # Sort by score and take top_k
        scored_chunks.sort(key=lambda x: x["score"], reverse=True)
        top_chunks = [item["chunk"] for item in scored_chunks[:top_k]]

        print(f"   ✓ Retrieved {len(top_chunks)} relevant chunks")
        for i, chunk in enumerate(top_chunks, 1):
            print(
                f"   {i}. Page {chunk.get('page', 'N/A')}: {chunk.get('text', '')[:50]}..."
            )

        return top_chunks

    def answer_question(self, question: str, top_k: int = 3) -> str:
        """
        Answer question using RAG.

        Args:
            question: User question
            top_k: Number of chunks to retrieve

        Returns:
            Answer based on retrieved chunks
        """
        print(f"\n❓ Question: {question}")

        # Retrieve relevant chunks
        relevant_chunks = self.retrieve_chunks(question, top_k=top_k)

        if not relevant_chunks:
            return "I don't have enough information to answer this question."

        # Combine chunks into context
        context = "\n\n".join(
            [
                f"[Source: Page {chunk.get('page', 'N/A')}]\n{chunk.get('text', '')}"
                for chunk in relevant_chunks
            ]
        )

        # In production, use LLM to generate answer
        # For now, return the context
        print("\n💡 Answer context prepared:")
        print(f"   Sources: {len(relevant_chunks)} chunks")
        print(f"   Context length: {len(context)} characters")

        # Simulated answer (in production, send to LLM)
        answer = f"Based on the document, here's what I found:\n\n{context[:500]}..."

        return answer

    def get_stats(self) -> Dict[str, Any]:
        """Get workflow statistics."""
        return {
            "total_chunks": len(self.chunks),
            "chunk_size": self.config.chunk_size,
            "provider": self.config.provider,
            "cost_per_document": 0.00,  # Ollama is free
        }


def create_sample_document() -> str:
    """Create a sample document for testing."""
    content = """# Company Report 2025

## Executive Summary

Our company achieved record growth in 2025, with revenue increasing by 45% to $50 million.
Key highlights include:
- New product launches in Q1 and Q3
- Expansion into 5 new markets
- Customer base grew to 10,000 active users

## Financial Performance

Total revenue: $50,000,000
Operating expenses: $35,000,000
Net profit: $15,000,000
Profit margin: 30%

## Product Development

We launched two major products this year:
1. CloudSync Platform - Released in March 2025
2. DataViz Analytics - Released in September 2025

Both products received positive customer feedback and contributed significantly to revenue growth.

## Market Expansion

Entered new markets in:
- Europe (Germany, France, UK)
- Asia (Japan, Singapore)

Each market showed strong initial traction with local partnerships.

## Customer Growth

Started the year with 5,000 customers, ended with 10,000 customers.
Customer retention rate: 95%
Average customer lifetime value: $5,000

## Future Outlook

For 2026, we plan to:
- Launch 3 new products
- Expand to 10 additional markets
- Double our engineering team
- Achieve $100M in annual revenue
"""

    # Save to temp file
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as tmp:
        tmp.write(content)
        return tmp.name


def main():
    """Example usage of basic RAG workflow."""

    print("=" * 70)
    print("🚀 BASIC RAG WORKFLOW DEMO")
    print("=" * 70)

    # Create sample document
    print("\n📝 Creating sample company report...")
    doc_path = create_sample_document()
    print(f"   ✓ Document created: {doc_path}")

    # Initialize workflow
    config = BasicRAGConfig(
        provider="ollama_vision",  # Free local provider
        chunk_size=512,
        extract_tables=True,
    )

    workflow = BasicRAGWorkflow(config)

    # Ingest document
    print("\n" + "=" * 70)
    print("📥 DOCUMENT INGESTION")
    print("=" * 70)

    result = workflow.ingest_document(doc_path)

    # Ask questions
    print("\n" + "=" * 70)
    print("💬 QUESTION ANSWERING")
    print("=" * 70)

    questions = [
        "What was the total revenue in 2025?",
        "Which products were launched this year?",
        "What are the plans for 2026?",
    ]

    for question in questions:
        answer = workflow.answer_question(question, top_k=2)
        print("\n✅ Answer retrieved")
        print("-" * 70)

    # Show stats
    print("\n" + "=" * 70)
    print("📊 WORKFLOW STATISTICS")
    print("=" * 70)

    stats = workflow.get_stats()
    print(f"Total chunks stored: {stats['total_chunks']}")
    print(f"Chunk size: {stats['chunk_size']} tokens")
    print(f"Provider: {stats['provider']}")
    print(f"Cost per document: ${stats['cost_per_document']:.2f}")

    print("\n✨ Basic RAG workflow demo complete!")
    print("\n💡 Next steps:")
    print("   - Run advanced_rag.py for multi-document RAG")
    print("   - Run workflow_integration.py for Core SDK integration")

    # Cleanup
    os.unlink(doc_path)


if __name__ == "__main__":
    main()

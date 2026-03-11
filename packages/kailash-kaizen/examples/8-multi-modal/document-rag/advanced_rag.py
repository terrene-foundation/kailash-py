"""
Advanced Multi-Document RAG with Cost Optimization

Demonstrates:
1. Multi-document ingestion with batch processing
2. Cost-aware provider selection
3. Advanced chunk retrieval with metadata filtering
4. Source attribution in answers
5. Budget constraint enforcement

This example shows production-ready RAG patterns with cost optimization.
"""

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from kaizen.agents.multi_modal.document_extraction_agent import (
    DocumentExtractionAgent,
    DocumentExtractionConfig,
)


@dataclass
class AdvancedRAGConfig:
    """Configuration for advanced RAG workflow."""

    # Cost optimization
    prefer_free: bool = True  # Prefer Ollama over paid providers
    max_cost_per_document: float = 0.01  # Budget constraint

    # Extraction settings
    chunk_size: int = 512
    chunk_overlap: int = 50
    extract_tables: bool = True

    # Provider fallback chain
    primary_provider: str = "ollama_vision"  # Free
    fallback_provider: str = "openai_vision"  # Paid fallback


class DocumentStore:
    """
    Simple document store with metadata filtering.

    In production, replace with a vector database like:
    - Pinecone
    - Weaviate
    - ChromaDB
    - Qdrant
    """

    def __init__(self):
        self.chunks: List[Dict[str, Any]] = []
        self.documents: Dict[str, Dict[str, Any]] = {}

    def add_document(
        self, doc_id: str, metadata: Dict[str, Any], chunks: List[Dict[str, Any]]
    ):
        """Add document with chunks."""
        # Store document metadata
        self.documents[doc_id] = metadata

        # Add chunks with document reference
        for chunk in chunks:
            chunk["doc_id"] = doc_id
            chunk["doc_name"] = metadata.get("name", "Unknown")
            self.chunks.append(chunk)

    def search(
        self,
        query: str,
        top_k: int = 5,
        filter_by_doc: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Search for relevant chunks.

        Args:
            query: Search query
            top_k: Number of results
            filter_by_doc: Optional document ID filter

        Returns:
            List of relevant chunks with scores
        """
        # Filter chunks by document if specified
        search_chunks = self.chunks
        if filter_by_doc:
            search_chunks = [c for c in self.chunks if c.get("doc_id") == filter_by_doc]

        # Simple keyword-based scoring (in production, use embeddings)
        query_words = set(query.lower().split())
        scored_chunks = []

        for chunk in search_chunks:
            chunk_text = chunk.get("text", "").lower()
            # Count matching words
            matches = sum(1 for word in query_words if word in chunk_text)
            score = matches / len(query_words) if query_words else 0

            if score > 0:  # Only include chunks with some relevance
                scored_chunks.append(
                    {
                        "chunk": chunk,
                        "score": score,
                    }
                )

        # Sort by score and take top_k
        scored_chunks.sort(key=lambda x: x["score"], reverse=True)

        return [item["chunk"] for item in scored_chunks[:top_k]]

    def get_stats(self) -> Dict[str, Any]:
        """Get store statistics."""
        return {
            "total_documents": len(self.documents),
            "total_chunks": len(self.chunks),
            "documents": list(self.documents.keys()),
        }


class AdvancedRAGWorkflow:
    """
    Advanced RAG workflow with multi-document support and cost optimization.
    """

    def __init__(self, config: AdvancedRAGConfig):
        """Initialize advanced RAG workflow."""
        self.config = config
        self.store = DocumentStore()
        self.total_cost = 0.0

        # Create document extraction agent with cost-aware provider
        agent_config = DocumentExtractionConfig(
            provider=config.primary_provider,
            chunk_for_rag=True,
            chunk_size=config.chunk_size,
        )

        self.doc_agent = DocumentExtractionAgent(config=agent_config)

        print("✅ Advanced RAG workflow initialized")
        print(f"   Primary provider: {config.primary_provider}")
        print(f"   Max cost per document: ${config.max_cost_per_document:.3f}")
        print(f"   Chunk size: {config.chunk_size} tokens")

    def ingest_document(
        self,
        file_path: str,
        doc_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Ingest single document into RAG system.

        Args:
            file_path: Path to document
            doc_id: Optional document ID (defaults to filename)
            metadata: Optional document metadata

        Returns:
            Dict with ingestion results
        """
        doc_id = doc_id or Path(file_path).stem
        metadata = metadata or {}
        metadata["name"] = Path(file_path).name
        metadata["path"] = file_path

        print(f"\n📄 Ingesting: {metadata['name']}")

        # Estimate cost before extraction
        cost_estimate = self.doc_agent.estimate_cost(file_path)
        print(f"   💰 Estimated cost: ${cost_estimate:.3f}")

        # Check budget constraint
        if cost_estimate > self.config.max_cost_per_document:
            if self.config.prefer_free:
                print("   ⚠️  Cost exceeds budget, using free provider...")
                # Switch to Ollama (free)
                self.doc_agent.config.provider = "ollama_vision"
            else:
                raise ValueError(
                    f"Cost ${cost_estimate:.3f} exceeds budget ${self.config.max_cost_per_document:.3f}"
                )

        # Extract document
        result = self.doc_agent.extract(
            file_path=file_path,
            extract_tables=self.config.extract_tables,
            chunk_for_rag=True,
            chunk_size=self.config.chunk_size,
        )

        # Add to document store
        self.store.add_document(doc_id, metadata, result["chunks"])

        # Track cost
        self.total_cost += result["cost"]

        print(f"   ✓ Extracted {len(result['text'])} characters")
        print(f"   ✓ Generated {len(result['chunks'])} chunks")
        print(f"   ✓ Provider: {result['provider']}")
        print(f"   ✓ Actual cost: ${result['cost']:.3f}")

        return {
            "doc_id": doc_id,
            "num_chunks": len(result["chunks"]),
            "provider": result["provider"],
            "cost": result["cost"],
        }

    def ingest_batch(
        self,
        file_paths: List[str],
        metadata_list: Optional[List[Dict[str, Any]]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Batch ingest multiple documents.

        Args:
            file_paths: List of document paths
            metadata_list: Optional list of metadata dicts

        Returns:
            List of ingestion results
        """
        print(f"\n📚 Batch ingesting {len(file_paths)} documents...")

        metadata_list = metadata_list or [{}] * len(file_paths)
        results = []

        for file_path, metadata in zip(file_paths, metadata_list):
            result = self.ingest_document(file_path, metadata=metadata)
            results.append(result)

        print("\n✅ Batch ingestion complete")
        print(f"   Total documents: {len(results)}")
        print(f"   Total cost: ${self.total_cost:.3f}")

        return results

    def query(
        self,
        question: str,
        top_k: int = 5,
        filter_by_doc: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Query the RAG system.

        Args:
            question: User question
            top_k: Number of chunks to retrieve
            filter_by_doc: Optional document ID to search within

        Returns:
            Dict with answer and sources
        """
        print(f"\n❓ Query: {question}")

        if filter_by_doc:
            print(f"   🔍 Filtering by document: {filter_by_doc}")

        # Retrieve relevant chunks
        relevant_chunks = self.store.search(
            query=question,
            top_k=top_k,
            filter_by_doc=filter_by_doc,
        )

        if not relevant_chunks:
            return {
                "question": question,
                "answer": "I don't have enough information to answer this question.",
                "sources": [],
            }

        print(f"   ✓ Retrieved {len(relevant_chunks)} relevant chunks")

        # Group chunks by document for source attribution
        sources = []
        context_parts = []

        for chunk in relevant_chunks:
            source = {
                "doc_id": chunk.get("doc_id"),
                "doc_name": chunk.get("doc_name"),
                "page": chunk.get("page", "N/A"),
                "text": chunk.get("text", "")[:100] + "...",
            }
            sources.append(source)

            # Build context for answer generation
            context_parts.append(
                f"[Source: {chunk.get('doc_name')} - Page {chunk.get('page', 'N/A')}]\n"
                f"{chunk.get('text', '')}"
            )

        context = "\n\n".join(context_parts)

        # In production, send to LLM for answer generation
        # For demonstration, return context
        answer = f"Based on {len(relevant_chunks)} sources, here's what I found:\n\n{context[:500]}..."

        print(f"   ✓ Answer generated from {len(sources)} sources")

        return {
            "question": question,
            "answer": answer,
            "sources": sources,
            "num_sources": len(sources),
        }

    def get_stats(self) -> Dict[str, Any]:
        """Get comprehensive workflow statistics."""
        store_stats = self.store.get_stats()

        return {
            "total_documents": store_stats["total_documents"],
            "total_chunks": store_stats["total_chunks"],
            "total_cost": self.total_cost,
            "avg_cost_per_document": (
                self.total_cost / store_stats["total_documents"]
                if store_stats["total_documents"] > 0
                else 0
            ),
            "documents": store_stats["documents"],
        }


def create_sample_documents() -> List[str]:
    """Create sample documents for testing."""

    # Document 1: Product Specifications
    doc1_content = """# Product Specifications - CloudSync Platform

## Overview
CloudSync Platform is our flagship product for cloud data synchronization.

## Features
- Real-time sync across devices
- End-to-end encryption
- Support for 50+ file types
- Automatic conflict resolution
- 99.99% uptime SLA

## Pricing
- Basic Plan: $9.99/month (100 GB storage)
- Pro Plan: $19.99/month (1 TB storage)
- Enterprise Plan: Custom pricing (unlimited storage)

## Technical Requirements
- Operating System: Windows 10+, macOS 11+, Linux
- Minimum RAM: 4 GB
- Network: Broadband internet connection
"""

    # Document 2: Customer Testimonials
    doc2_content = """# Customer Testimonials - CloudSync Platform

## Enterprise Customers

### Acme Corporation
"CloudSync has transformed our workflow. We can now collaborate seamlessly across 15 offices worldwide."
- John Smith, CTO

### Global Tech Inc.
"The automatic conflict resolution feature saved us countless hours. Highly recommended!"
- Sarah Johnson, Head of Operations

## Small Business Customers

### Design Studio Pro
"As a small design agency, CloudSync's Pro Plan gives us enterprise-level features at an affordable price."
- Michael Chen, Founder

### Consulting Group LLC
"The real-time sync is incredibly fast. We switched from competitors and haven't looked back."
- Emily Rodriguez, Managing Partner

## Overall Satisfaction
- Average rating: 4.8/5 stars
- Would recommend to others: 96%
- Renewal rate: 94%
"""

    # Document 3: Security & Compliance
    doc3_content = """# Security & Compliance - CloudSync Platform

## Security Measures
- AES-256 encryption at rest
- TLS 1.3 encryption in transit
- Two-factor authentication (2FA)
- Single sign-on (SSO) support
- Regular security audits

## Compliance Certifications
- SOC 2 Type II certified
- GDPR compliant
- HIPAA compliant (Enterprise plan)
- ISO 27001 certified

## Data Privacy
- Data residency options available
- No third-party data sharing
- User-controlled data deletion
- Transparent data handling policies

## Incident Response
- 24/7 security monitoring
- Average response time: 15 minutes
- Incident notification within 1 hour
- Detailed post-incident reports
"""

    # Save to temp files
    temp_files = []
    for i, content in enumerate([doc1_content, doc2_content, doc3_content], 1):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as tmp:
            tmp.write(content)
            temp_files.append(tmp.name)

    return temp_files


def main():
    """Example usage of advanced multi-document RAG."""

    print("=" * 80)
    print("🚀 ADVANCED MULTI-DOCUMENT RAG DEMO")
    print("=" * 80)

    # Create sample documents
    print("\n📝 Creating sample product documentation...")
    doc_paths = create_sample_documents()
    print(f"   ✓ Created {len(doc_paths)} documents")

    # Initialize workflow
    config = AdvancedRAGConfig(
        prefer_free=True,
        max_cost_per_document=0.01,
        chunk_size=512,
        extract_tables=True,
        primary_provider="ollama_vision",
    )

    workflow = AdvancedRAGWorkflow(config)

    # Batch ingest documents
    print("\n" + "=" * 80)
    print("📥 BATCH DOCUMENT INGESTION")
    print("=" * 80)

    metadata_list = [
        {"category": "product", "version": "1.0"},
        {"category": "testimonials", "source": "customer_feedback"},
        {"category": "security", "classification": "public"},
    ]

    results = workflow.ingest_batch(doc_paths, metadata_list)

    # Query across all documents
    print("\n" + "=" * 80)
    print("💬 CROSS-DOCUMENT QUERIES")
    print("=" * 80)

    questions = [
        "What are the pricing plans for CloudSync?",
        "What do customers say about CloudSync?",
        "Is CloudSync GDPR compliant?",
        "What are the technical requirements?",
    ]

    for question in questions:
        result = workflow.query(question, top_k=3)
        print("\n" + "-" * 80)
        print(f"Sources used: {result['num_sources']}")
        for i, source in enumerate(result["sources"], 1):
            print(f"   {i}. {source['doc_name']} (Page {source['page']})")

    # Query specific document
    print("\n" + "=" * 80)
    print("🎯 DOCUMENT-SPECIFIC QUERY")
    print("=" * 80)

    # Get document IDs from store
    stats = workflow.get_stats()
    if stats["documents"]:
        specific_doc = stats["documents"][0]
        result = workflow.query(
            "Tell me about the features",
            top_k=2,
            filter_by_doc=specific_doc,
        )
        print(f"\n   Searched only in: {specific_doc}")
        print(f"   Sources: {result['num_sources']}")

    # Show comprehensive stats
    print("\n" + "=" * 80)
    print("📊 COMPREHENSIVE STATISTICS")
    print("=" * 80)

    stats = workflow.get_stats()
    print(f"Total documents ingested: {stats['total_documents']}")
    print(f"Total chunks generated: {stats['total_chunks']}")
    print(f"Total cost: ${stats['total_cost']:.3f}")
    print(f"Average cost per document: ${stats['avg_cost_per_document']:.3f}")
    print(
        f"Average chunks per document: {stats['total_chunks'] / stats['total_documents']:.1f}"
    )

    print("\n💡 Cost Optimization:")
    if stats["total_cost"] == 0:
        print("   ✅ Used 100% free provider (Ollama)")
        print("   ✅ Saved ~$0.05-0.20 vs. paid providers")
    else:
        print(f"   💰 Actual cost: ${stats['total_cost']:.3f}")

    print("\n✨ Advanced RAG workflow demo complete!")
    print("\n🔗 Next steps:")
    print("   - Integrate with vector database (ChromaDB, Pinecone)")
    print("   - Add semantic embeddings for better retrieval")
    print("   - Connect LLM for answer generation")
    print("   - Run workflow_integration.py for Core SDK patterns")

    # Cleanup
    for path in doc_paths:
        os.unlink(path)


if __name__ == "__main__":
    main()

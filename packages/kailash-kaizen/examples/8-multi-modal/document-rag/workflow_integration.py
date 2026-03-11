"""
Document Extraction + Core SDK Workflow Integration

Demonstrates:
1. Integrating DocumentExtractionAgent with Kailash Core SDK workflows
2. Building document processing pipelines
3. Combining document extraction with other workflow nodes
4. Async workflow execution patterns

This example shows how to use document extraction in production workflows.
"""

import asyncio
import os
import tempfile
from pathlib import Path
from typing import Any, Dict

from kaizen.agents.multi_modal.document_extraction_agent import (
    DocumentExtractionAgent,
    DocumentExtractionConfig,
)

from kailash.runtime import AsyncLocalRuntime


def create_sample_invoice() -> str:
    """Create a sample invoice document."""
    content = """INVOICE #INV-2025-001

Date: January 15, 2025
Due Date: February 15, 2025

Bill To:
Acme Corporation
123 Business St
San Francisco, CA 94105

Items:
- Software License (Annual)     $5,000.00
- Support Services              $1,500.00
- Training Sessions             $2,000.00

Subtotal:                        $8,500.00
Tax (8.5%):                        $722.50
-------------------------------------------
TOTAL:                           $9,222.50

Payment Terms: Net 30
Payment Methods: Wire Transfer, Check

Bank Details:
Account: 1234567890
Routing: 987654321
"""

    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as tmp:
        tmp.write(content)
        return tmp.name


class DocumentWorkflowIntegration:
    """
    Document extraction integrated with Core SDK workflows.

    Pattern:
    Document → Extract → Transform → Store → Process
    """

    def __init__(self):
        """Initialize workflow integration."""
        # Create document extraction agent
        config = DocumentExtractionConfig(
            provider="ollama_vision",  # Free local provider
            chunk_for_rag=True,
            chunk_size=512,
        )

        self.doc_agent = DocumentExtractionAgent(config=config)
        self.runtime = AsyncLocalRuntime()

        print("✅ Workflow integration initialized")
        print("   Provider: ollama_vision (free)")
        print("   Runtime: AsyncLocalRuntime")

    async def pattern_1_simple_extraction(self, file_path: str) -> Dict[str, Any]:
        """
        Pattern 1: Simple document extraction in workflow.

        Workflow: Extract → Return
        """
        print("\n" + "=" * 70)
        print("📋 PATTERN 1: Simple Extraction")
        print("=" * 70)

        # Extract document
        print(f"\n📄 Extracting: {Path(file_path).name}")
        result = self.doc_agent.extract(
            file_path=file_path,
            extract_tables=False,
            chunk_for_rag=False,
        )

        print(f"   ✓ Extracted {len(result['text'])} characters")
        print(f"   ✓ Provider: {result['provider']}")
        print(f"   ✓ Cost: ${result['cost']:.3f}")

        return result

    async def pattern_2_extract_and_chunk(self, file_path: str) -> Dict[str, Any]:
        """
        Pattern 2: Extract document and prepare RAG chunks.

        Workflow: Extract → Chunk → Store (simulated)
        """
        print("\n" + "=" * 70)
        print("📋 PATTERN 2: Extract + Chunk for RAG")
        print("=" * 70)

        # Extract with RAG chunking
        print(f"\n📄 Processing: {Path(file_path).name}")
        result = self.doc_agent.extract(
            file_path=file_path,
            extract_tables=True,
            chunk_for_rag=True,
            chunk_size=512,
        )

        print(f"   ✓ Extracted {len(result['text'])} characters")
        print(f"   ✓ Generated {len(result['chunks'])} chunks")
        print(f"   ✓ Tables found: {len(result.get('tables', []))}")

        # In production, store chunks in vector database
        # For demonstration, show chunk structure
        if result["chunks"]:
            sample_chunk = result["chunks"][0]
            print("\n   Sample chunk structure:")
            print(f"   - text: {sample_chunk.get('text', '')[:50]}...")
            print(f"   - page: {sample_chunk.get('page', 'N/A')}")
            print(f"   - chunk_id: {sample_chunk.get('chunk_id', 'N/A')}")

        return result

    async def pattern_3_batch_processing(self, file_paths: list) -> Dict[str, Any]:
        """
        Pattern 3: Batch document processing with concurrency.

        Workflow: [Extract Doc1, Extract Doc2, ...] → Aggregate
        """
        print("\n" + "=" * 70)
        print("📋 PATTERN 3: Batch Processing with Concurrency")
        print("=" * 70)

        print(f"\n📚 Processing {len(file_paths)} documents concurrently...")

        # Create extraction tasks
        tasks = []
        for file_path in file_paths:
            task = asyncio.create_task(self._extract_async(file_path))
            tasks.append(task)

        # Run concurrently
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Aggregate results
        total_cost = sum(r.get("cost", 0) for r in results if isinstance(r, dict))
        total_chunks = sum(
            len(r.get("chunks", [])) for r in results if isinstance(r, dict)
        )
        success_count = sum(1 for r in results if isinstance(r, dict))

        print("\n✅ Batch processing complete:")
        print(f"   Successful: {success_count}/{len(file_paths)}")
        print(f"   Total chunks: {total_chunks}")
        print(f"   Total cost: ${total_cost:.3f}")

        return {
            "results": results,
            "total_cost": total_cost,
            "total_chunks": total_chunks,
            "success_count": success_count,
        }

    async def _extract_async(self, file_path: str) -> Dict[str, Any]:
        """Helper method for async extraction."""
        print(f"   📄 Extracting: {Path(file_path).name}")
        result = self.doc_agent.extract(
            file_path=file_path,
            extract_tables=True,
            chunk_for_rag=True,
            chunk_size=512,
        )
        print(
            f"   ✓ Done: {Path(file_path).name} ({len(result.get('chunks', []))} chunks)"
        )
        return result

    async def pattern_4_workflow_pipeline(self, file_path: str) -> Dict[str, Any]:
        """
        Pattern 4: Full workflow pipeline integration.

        Workflow:
        Extract → Parse Entities → Validate → Store → Notify
        """
        print("\n" + "=" * 70)
        print("📋 PATTERN 4: Full Workflow Pipeline")
        print("=" * 70)

        # Step 1: Extract
        print(f"\n📄 Step 1: Extracting {Path(file_path).name}...")
        extraction_result = self.doc_agent.extract(
            file_path=file_path,
            extract_tables=True,
            chunk_for_rag=False,
        )
        print(f"   ✓ Extracted {len(extraction_result['text'])} characters")

        # Step 2: Parse entities (simulated)
        print("\n🔍 Step 2: Parsing entities...")
        entities = self._parse_entities(extraction_result["text"])
        print(f"   ✓ Found {len(entities)} entities")

        # Step 3: Validate (simulated)
        print("\n✅ Step 3: Validating data...")
        validation = self._validate_document(entities)
        print(f"   ✓ Validation: {validation['status']}")

        # Step 4: Store (simulated)
        print("\n💾 Step 4: Storing results...")
        storage_result = self._store_document(extraction_result, entities)
        print(f"   ✓ Stored with ID: {storage_result['doc_id']}")

        # Step 5: Notify (simulated)
        print("\n📧 Step 5: Sending notifications...")
        notification = self._send_notification(storage_result)
        print(f"   ✓ Notification sent: {notification['status']}")

        return {
            "extraction": extraction_result,
            "entities": entities,
            "validation": validation,
            "storage": storage_result,
            "notification": notification,
        }

    def _parse_entities(self, text: str) -> Dict[str, Any]:
        """Simulate entity parsing."""
        # In production, use NER or LLM for entity extraction
        entities = {
            "invoice_number": "INV-2025-001" if "INV-2025-001" in text else None,
            "date": "January 15, 2025" if "January 15, 2025" in text else None,
            "total": "$9,222.50" if "$9,222.50" in text else None,
            "company": "Acme Corporation" if "Acme Corporation" in text else None,
        }
        return {k: v for k, v in entities.items() if v is not None}

    def _validate_document(self, entities: Dict[str, Any]) -> Dict[str, str]:
        """Simulate document validation."""
        # In production, implement business logic validation
        required_fields = ["invoice_number", "date", "total"]
        missing = [f for f in required_fields if f not in entities]

        return {
            "status": "valid" if not missing else "invalid",
            "missing_fields": missing,
        }

    def _store_document(
        self, extraction: Dict[str, Any], entities: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Simulate document storage."""
        # In production, store in database
        return {
            "doc_id": "doc_12345",
            "stored_at": "2025-01-15T10:30:00Z",
            "provider": extraction["provider"],
        }

    def _send_notification(self, storage: Dict[str, Any]) -> Dict[str, str]:
        """Simulate notification."""
        # In production, send email/webhook
        return {
            "status": "sent",
            "recipients": ["admin@company.com"],
        }


async def main():
    """Run all workflow integration patterns."""

    print("=" * 70)
    print("🚀 DOCUMENT EXTRACTION + CORE SDK WORKFLOW INTEGRATION")
    print("=" * 70)

    # Create sample documents
    print("\n📝 Creating sample documents...")
    invoice_path = create_sample_invoice()
    print(f"   ✓ Sample invoice: {invoice_path}")

    # Initialize integration
    integration = DocumentWorkflowIntegration()

    # Pattern 1: Simple extraction
    await integration.pattern_1_simple_extraction(invoice_path)

    # Pattern 2: Extract and chunk for RAG
    await integration.pattern_2_extract_and_chunk(invoice_path)

    # Pattern 3: Batch processing (simulate multiple docs)
    doc_paths = [invoice_path]  # In production, multiple documents
    await integration.pattern_3_batch_processing(doc_paths)

    # Pattern 4: Full workflow pipeline
    await integration.pattern_4_workflow_pipeline(invoice_path)

    print("\n" + "=" * 70)
    print("✨ All workflow patterns complete!")
    print("=" * 70)

    print("\n💡 Key Patterns Demonstrated:")
    print("   1. Simple extraction in workflow")
    print("   2. RAG chunking preparation")
    print("   3. Concurrent batch processing")
    print("   4. Full pipeline integration")

    print("\n🔗 Production Integration:")
    print("   - Combine with Kailash Core SDK nodes")
    print("   - Use AsyncLocalRuntime for async workflows")
    print("   - Integrate with databases (DataFlow)")
    print("   - Deploy via Nexus (API/CLI/MCP)")

    print("\n📚 Related Examples:")
    print("   - examples/1-single-agent/ - Agent patterns")
    print("   - examples/2-multi-agent/ - Coordination patterns")
    print("   - examples/5-mcp-integration/ - MCP integration")

    # Cleanup
    os.unlink(invoice_path)


if __name__ == "__main__":
    asyncio.run(main())

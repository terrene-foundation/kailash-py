"""
Quickstart: Zero-Cost Document Extraction

The fastest way to start extracting documents with zero API costs.
Uses Ollama (free, local).
"""

import tempfile

from kaizen.agents.multi_modal.document_extraction_agent import (
    DocumentExtractionAgent,
    DocumentExtractionConfig,
)


def main():
    """Quickstart with zero cost."""
    print("=" * 70)
    print("Quickstart: Zero-Cost Document Extraction")
    print("=" * 70)

    # Step 1: Configure (zero-config, uses free Ollama)
    print("\nStep 1: Configure agent (free provider)")
    config = DocumentExtractionConfig(
        provider="ollama_vision",  # FREE local provider
    )
    agent = DocumentExtractionAgent(config=config)
    print("  ✅ Agent configured with Ollama (free)")

    # Step 2: Create sample document
    print("\nStep 2: Create sample document")
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as tmp:
        tmp.write("Invoice #123\nTotal: $500.00\nDate: 2025-01-15")
        doc_path = tmp.name
    print(f"  ✅ Document: {doc_path}")

    # Step 3: Extract
    print("\nStep 3: Extract document")
    result = agent.extract(
        file_path=doc_path,
        extract_tables=False,
        chunk_for_rag=False,
    )
    print(f"  ✅ Extracted {len(result['text'])} characters")
    print(f"  ✅ Cost: ${result['cost']:.2f} (FREE!)")
    print(f"  ✅ Provider: {result['provider']}")

    # Step 4: Access results
    print("\nStep 4: Access results")
    print(f"  Text: {result['text'][:60]}...")
    print(f"  Markdown: {result['markdown'][:60]}...")

    import os

    os.unlink(doc_path)

    print("\n" + "=" * 70)
    print("Done! Extract unlimited documents at zero cost with Ollama")
    print("=" * 70)

    print("\nNext steps:")
    print("  - advanced_rag.py: Multi-document RAG workflows")
    print("  - cost_estimation_demo.py: Compare all providers")
    print("  - batch_processing_demo.py: Process many documents")


if __name__ == "__main__":
    main()

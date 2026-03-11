"""
VisionAgent with Document Extraction Demo

Demonstrates:
1. Enabling document extraction in VisionAgent (opt-in)
2. Switching between image analysis and document extraction
3. Cost estimation for documents
4. Using both vision and document capabilities

This example shows how to use VisionAgent's enhanced document extraction features.
"""

import os
import tempfile

from kaizen.agents.multi_modal.vision_agent import VisionAgent, VisionAgentConfig


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
"""

    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as tmp:
        tmp.write(content)
        return tmp.name


def demonstrate_vision_only():
    """Demonstrate standard VisionAgent usage (vision only)."""

    print("=" * 80)
    print("👁️  VISION-ONLY MODE (Standard VisionAgent)")
    print("=" * 80)

    # Standard configuration (no document extraction)
    config = VisionAgentConfig(
        llm_provider="ollama",
        model="llava:13b",
    )

    agent = VisionAgent(config=config)

    print("\n✅ VisionAgent initialized (vision-only mode)")
    print("   Features: Image analysis, OCR, Visual Q&A")
    print("   Document extraction: Disabled (default)")

    # Note: Would need actual image for vision analysis
    print("\n💡 Vision capabilities:")
    print("   - agent.analyze(image='photo.jpg', question='What is this?')")
    print("   - agent.describe(image='photo.jpg')")
    print("   - agent.extract_text(image='document_scan.jpg')")
    print("   - agent.batch_analyze(images=[...])")


def demonstrate_document_extraction_error():
    """Demonstrate error when trying to use document extraction without enabling."""

    print("\n" + "=" * 80)
    print("⚠️  ATTEMPTING DOCUMENT EXTRACTION WITHOUT ENABLING")
    print("=" * 80)

    # Vision-only config
    config = VisionAgentConfig()
    agent = VisionAgent(config=config)

    invoice_path = create_sample_invoice()

    print("\n❌ Attempting: agent.extract_document('invoice.txt')")

    try:
        agent.extract_document(invoice_path)
        print("   Unexpected: Should have raised RuntimeError")
    except RuntimeError as e:
        print(f"   ✅ Expected error: {str(e)}")
        print("\n💡 To enable document extraction:")
        print("   config = VisionAgentConfig(")
        print("       enable_document_extraction=True,")
        print("       landing_ai_api_key=os.getenv('LANDING_AI_API_KEY'),")
        print("   )")

    os.unlink(invoice_path)


def demonstrate_document_extraction_enabled():
    """Demonstrate VisionAgent with document extraction enabled."""

    print("\n" + "=" * 80)
    print("📄 DOCUMENT EXTRACTION MODE (Enhanced VisionAgent)")
    print("=" * 80)

    # Enable document extraction (opt-in)
    config = VisionAgentConfig(
        llm_provider="ollama",
        model="llava:13b",
        enable_document_extraction=True,  # OPT-IN
        landing_ai_api_key=os.getenv("LANDING_AI_API_KEY"),
        openai_api_key=os.getenv("OPENAI_API_KEY"),
    )

    agent = VisionAgent(config=config)

    print("\n✅ VisionAgent initialized (document extraction enabled)")
    print("   Features: Image analysis + Document extraction")
    print("   Providers: Landing AI, OpenAI, Ollama")

    # Create sample invoice
    invoice_path = create_sample_invoice()

    # Cost estimation
    print("\n💰 Estimating extraction cost...")
    cost_estimates = agent.estimate_document_cost(invoice_path, provider="auto")

    print(f"   Landing AI: ${cost_estimates['landing_ai']:.3f}")
    print(f"   OpenAI Vision: ${cost_estimates['openai_vision']:.3f}")
    print(f"   Ollama: ${cost_estimates['ollama_vision']:.3f} (FREE)")

    # Extract document (basic)
    print("\n📄 Extracting document (basic mode)...")
    result_basic = agent.extract_document(
        file_path=invoice_path,
        extract_tables=False,
        chunk_for_rag=False,
    )

    print(f"   ✅ Extracted {len(result_basic['text'])} characters")
    print(f"   Provider: {result_basic['provider']}")
    print(f"   Cost: ${result_basic['cost']:.3f}")
    print(f"   Text preview: {result_basic['text'][:100]}...")

    # Extract document (with RAG chunking)
    print("\n📄 Extracting document (RAG mode)...")
    result_rag = agent.extract_document(
        file_path=invoice_path,
        extract_tables=True,
        chunk_for_rag=True,
        chunk_size=256,
    )

    print(f"   ✅ Generated {len(result_rag['chunks'])} chunks")
    print("   Chunk size: 256 tokens")
    print(f"   Cost: ${result_rag['cost']:.3f}")

    # Show chunk structure
    if result_rag["chunks"]:
        sample_chunk = result_rag["chunks"][0]
        print("\n   Sample chunk:")
        print(f"   - Text: {sample_chunk.get('text', '')[:60]}...")
        print(f"   - Page: {sample_chunk.get('page', 'N/A')}")
        print(f"   - Chunk ID: {sample_chunk.get('chunk_id', 'N/A')}")

    os.unlink(invoice_path)


def demonstrate_dual_capability():
    """Demonstrate using both vision and document capabilities."""

    print("\n" + "=" * 80)
    print("🎯 DUAL CAPABILITY DEMO (Vision + Documents)")
    print("=" * 80)

    # Enable both capabilities
    config = VisionAgentConfig(
        llm_provider="ollama",
        model="llava:13b",
        enable_document_extraction=True,
        landing_ai_api_key=os.getenv("LANDING_AI_API_KEY"),
    )

    agent = VisionAgent(config=config)

    print("\n✅ VisionAgent with dual capabilities:")
    print("   1. Vision: Image analysis, OCR, Visual Q&A")
    print("   2. Documents: Extract, chunk, RAG-ready")

    # Demonstrate document extraction
    invoice_path = create_sample_invoice()

    print("\n📄 Task 1: Extract invoice text")
    result = agent.extract_document(invoice_path, extract_tables=True)
    print(f"   ✅ Extracted invoice: {len(result['text'])} characters")

    print("\n💡 Task 2: Analyze invoice image (would use agent.analyze())")
    print("   - agent.analyze(image='invoice_scan.jpg', question='What is the total?')")
    print("   - Uses vision model (llava:13b) for image understanding")

    print("\n💡 Task 3: Extract text from scanned document (OCR)")
    print("   - agent.extract_text(image='scanned_contract.jpg')")
    print("   - Uses vision model for OCR on images")

    print("\n💡 Best Practices:")
    print("   - Use vision (analyze, extract_text) for images/scans")
    print("   - Use document extraction (extract_document) for native PDFs/DOCX")
    print("   - Enable document extraction only if needed (opt-in)")
    print("   - Choose provider based on accuracy/cost needs")

    os.unlink(invoice_path)


def demonstrate_configuration_patterns():
    """Demonstrate different configuration patterns."""

    print("\n" + "=" * 80)
    print("⚙️  CONFIGURATION PATTERNS")
    print("=" * 80)

    # Pattern 1: Vision-only (default)
    print("\n1️⃣  Vision-Only (Default)")
    print("   config = VisionAgentConfig()")
    print("   - Standard VisionAgent behavior")
    print("   - Image analysis, OCR, Visual Q&A")
    print("   - No document extraction")

    # Pattern 2: Free document extraction
    print("\n2️⃣  Free Document Extraction (Ollama)")
    print("   config = VisionAgentConfig(")
    print("       enable_document_extraction=True,")
    print("       # No API keys = defaults to Ollama (free)")
    print("   )")
    print("   - Vision + Document extraction")
    print("   - Uses Ollama (free, local)")
    print("   - 85% accuracy (acceptable for most use cases)")

    # Pattern 3: Paid providers for accuracy
    print("\n3️⃣  High-Accuracy Document Extraction")
    print("   config = VisionAgentConfig(")
    print("       enable_document_extraction=True,")
    print("       landing_ai_api_key=os.getenv('LANDING_AI_API_KEY'),")
    print("   )")
    print("   - Vision + Document extraction")
    print("   - Uses Landing AI (98% accuracy, $0.015/page)")
    print("   - Bounding boxes for spatial coordinates")

    # Pattern 4: Multi-provider with fallback
    print("\n4️⃣  Multi-Provider with Fallback")
    print("   config = VisionAgentConfig(")
    print("       enable_document_extraction=True,")
    print("       landing_ai_api_key=os.getenv('LANDING_AI_API_KEY'),")
    print("       openai_api_key=os.getenv('OPENAI_API_KEY'),")
    print("   )")
    print("   - Vision + Document extraction")
    print("   - Automatic provider selection")
    print("   - Fallback chain: Landing AI → OpenAI → Ollama")


def main():
    """Run all VisionAgent document extraction demonstrations."""

    print("=" * 80)
    print("🚀 VISIONAGENT DOCUMENT EXTRACTION DEMO")
    print("=" * 80)

    # Part 1: Vision-only mode
    demonstrate_vision_only()

    # Part 2: Error without enabling
    demonstrate_document_extraction_error()

    # Part 3: Document extraction enabled
    demonstrate_document_extraction_enabled()

    # Part 4: Dual capability
    demonstrate_dual_capability()

    # Part 5: Configuration patterns
    demonstrate_configuration_patterns()

    print("\n" + "=" * 80)
    print("✨ VISIONAGENT DOCUMENT EXTRACTION DEMO COMPLETE")
    print("=" * 80)

    print("\n💡 Key Takeaways:")
    print("   1. Document extraction is opt-in (enable_document_extraction=True)")
    print("   2. Zero breaking changes to existing VisionAgent code")
    print("   3. Can use both vision and document capabilities together")
    print("   4. Free option available (Ollama) for unlimited use")
    print("   5. Cost estimation before extraction")

    print("\n📚 Related Examples:")
    print("   - multimodal_agent_document_demo.py: MultiModalAgent auto-detection")
    print("   - cost_estimation_demo.py: Cost estimation patterns")
    print("   - basic_rag.py: RAG workflows with documents")


if __name__ == "__main__":
    main()

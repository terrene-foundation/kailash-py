"""
MultiModalAgent with Document Auto-Detection Demo

Demonstrates:
1. Automatic document detection by file extension
2. Unified analyze() method for all modalities
3. Optional LLM-based Q&A over documents
4. Cost tracking across modalities
5. Switching between vision, audio, and documents seamlessly

This example shows MultiModalAgent's enhanced document detection capabilities.
"""

import os
import tempfile
from pathlib import Path

from kaizen.agents.multi_modal.multi_modal_agent import (
    MultiModalAgent,
    MultiModalConfig,
)
from kaizen.signatures import InputField, OutputField, Signature
from kaizen.signatures.multi_modal import MultiModalSignature


class UnifiedAnalysisSignature(MultiModalSignature, Signature):
    """Signature for unified multi-modal analysis."""

    # Inputs (can be any modality)
    input_data: str = InputField(description="Input data (image/audio/document path)")
    prompt: str = InputField(description="Optional question or instruction", default="")

    # Outputs
    result: str = OutputField(description="Analysis result")
    modality: str = OutputField(description="Detected modality")
    confidence: float = OutputField(description="Confidence score", default=0.0)


def create_sample_document() -> str:
    """Create a sample document."""
    content = """# Product Roadmap 2025

## Q1 Objectives
- Launch mobile app (iOS + Android)
- Release v2.0 API
- Expand to 3 new markets

## Q2 Objectives
- AI-powered recommendations
- Enterprise tier features
- Real-time analytics dashboard

## Q3 Objectives
- Multi-language support (5 languages)
- Advanced security features
- Partner integration platform

## Q4 Objectives
- Year-end feature freeze
- Performance optimizations
- Platform scalability improvements

## Key Metrics
- Target users: 100,000
- Revenue goal: $10M ARR
- Customer satisfaction: >4.5/5
"""

    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as tmp:
        tmp.write(content)
        return tmp.name


def demonstrate_auto_detection():
    """Demonstrate automatic modality detection."""

    print("=" * 80)
    print("🎯 AUTOMATIC MODALITY DETECTION")
    print("=" * 80)

    # Enable document extraction
    config = MultiModalConfig(
        llm_provider="ollama",
        model="llama2",
        prefer_local=True,
        enable_document_extraction=True,  # Enable document detection
        landing_ai_api_key=os.getenv("LANDING_AI_API_KEY"),
    )

    agent = MultiModalAgent(
        config=config,
        signature=UnifiedAnalysisSignature(),
    )

    print("\n✅ MultiModalAgent initialized with auto-detection")
    print("   Modalities: Vision, Audio, Documents, Text")

    # Test different file extensions
    test_cases = [
        {"file": "document.pdf", "detected": "Document (PDF)"},
        {"file": "report.docx", "detected": "Document (DOCX)"},
        {"file": "notes.txt", "detected": "Document (TXT)"},
        {"file": "readme.md", "detected": "Document (Markdown)"},
        {"file": "photo.jpg", "detected": "Image (JPEG)"},
        {"file": "image.png", "detected": "Image (PNG)"},
        {"file": "audio.mp3", "detected": "Audio (MP3)"},
        {"file": "voice.wav", "detected": "Audio (WAV)"},
    ]

    print("\n📋 File Extension → Modality Detection:")
    print("-" * 80)

    for case in test_cases:
        print(f"   {case['file']:<20} → {case['detected']}")

    print("\n💡 Auto-detection logic:")
    print("   1. Check file extension")
    print("   2. Route to appropriate processor:")
    print("      - .pdf, .docx, .txt, .md → Document extraction")
    print("      - .jpg, .png, .webp → Vision processing")
    print("      - .mp3, .wav, .m4a → Audio transcription")


def demonstrate_document_processing():
    """Demonstrate document processing with MultiModalAgent."""

    print("\n" + "=" * 80)
    print("📄 DOCUMENT PROCESSING")
    print("=" * 80)

    # Create config with document extraction enabled
    config = MultiModalConfig(
        llm_provider="ollama",
        model="llama2",
        enable_document_extraction=True,
        landing_ai_api_key=os.getenv("LANDING_AI_API_KEY"),
    )

    agent = MultiModalAgent(
        config=config,
        signature=UnifiedAnalysisSignature(),
    )

    # Create sample document
    doc_path = create_sample_document()

    # Case 1: Basic extraction (no prompt)
    print("\n📝 Case 1: Basic Document Extraction (no prompt)")
    print("-" * 80)

    result_basic = agent.analyze(
        input_data=doc_path,  # Auto-detected as document
    )

    print("   ✅ Document extracted")
    print(f"   Text length: {len(result_basic['text'])} characters")
    print(f"   Provider: {result_basic['provider']}")
    print(f"   Cost: ${result_basic['cost']:.3f}")
    print(f"   Preview: {result_basic['text'][:100]}...")

    # Case 2: With prompt for Q&A
    print("\n📝 Case 2: Document Extraction with Q&A")
    print("-" * 80)

    result_qa = agent.analyze(
        input_data=doc_path,
        prompt="What are the Q1 objectives?",  # LLM will answer this
    )

    print("   ✅ Document extracted + LLM answer generated")
    print(f"   Question: {result_qa.get('question', 'N/A')}")
    print(f"   Text length: {len(result_qa['text'])} characters")
    print(f"   Has LLM answer: {('llm_answer' in result_qa)}")

    if "llm_answer" in result_qa:
        print(f"   LLM Answer preview: {str(result_qa['llm_answer'])[:100]}...")

    os.unlink(doc_path)


def demonstrate_unified_api():
    """Demonstrate unified analyze() API for all modalities."""

    print("\n" + "=" * 80)
    print("🎨 UNIFIED API ACROSS MODALITIES")
    print("=" * 80)

    config = MultiModalConfig(
        enable_document_extraction=True,
        landing_ai_api_key=os.getenv("LANDING_AI_API_KEY"),
    )

    agent = MultiModalAgent(
        config=config,
        signature=UnifiedAnalysisSignature(),
    )

    print("\n✅ Same analyze() method works for all modalities:")

    # Document example
    print("\n📄 Documents:")
    print("   result = agent.analyze(")
    print("       input_data='report.pdf',")
    print("       prompt='Summarize key findings'")
    print("   )")
    print("   → Auto-detects document, extracts text, generates answer")

    # Image example (hypothetical)
    print("\n🖼️  Images:")
    print("   result = agent.analyze(")
    print("       input_data='photo.jpg',")
    print("       prompt='What objects are visible?'")
    print("   )")
    print("   → Auto-detects image, uses vision model")

    # Audio example (hypothetical)
    print("\n🎵 Audio:")
    print("   result = agent.analyze(")
    print("       input_data='meeting.mp3',")
    print("       prompt='Transcribe this audio'")
    print("   )")
    print("   → Auto-detects audio, transcribes with Whisper")

    # Text example
    print("\n📝 Text:")
    print("   result = agent.analyze(")
    print("       input_data='What is machine learning?',")
    print("   )")
    print("   → Processes as text query")


def demonstrate_cost_tracking():
    """Demonstrate cost tracking across modalities."""

    print("\n" + "=" * 80)
    print("💰 COST TRACKING ACROSS MODALITIES")
    print("=" * 80)

    config = MultiModalConfig(
        enable_document_extraction=True,
        enable_cost_tracking=True,  # Enable cost tracking
        budget_limit=1.0,
        warn_on_openai_usage=True,
        landing_ai_api_key=os.getenv("LANDING_AI_API_KEY"),
    )

    agent = MultiModalAgent(
        config=config,
        signature=UnifiedAnalysisSignature(),
    )

    print("\n✅ Cost tracking enabled")
    print("   Budget limit: $1.00")
    print("   Provider warnings: Enabled")

    # Process document
    doc_path = create_sample_document()

    print(f"\n📄 Processing document: {Path(doc_path).name}")
    result = agent.analyze(input_data=doc_path)

    print(f"   Cost: ${result['cost']:.3f}")
    print(f"   Provider: {result['provider']}")

    # Get cost summary
    summary = agent.get_cost_summary()

    if summary["enabled"]:
        print("\n📊 Cost Summary:")
        print(f"   Total calls: {summary['stats']['total_calls']}")
        print(f"   Total cost: ${summary['stats']['total_cost']:.3f}")

        if "budget" in summary:
            print(f"   Budget used: {summary['budget']['percentage']:.1f}%")
            print(f"   Budget remaining: ${summary['budget']['remaining']:.3f}")

        if "savings" in summary:
            print("\n💰 Cost Optimization:")
            print(f"   Actual cost: ${summary['savings']['actual_cost']:.3f}")
            print(
                f"   OpenAI equivalent: ${summary['savings']['openai_equivalent']:.3f}"
            )
            print(f"   Savings: ${summary['savings']['saved']:.3f}")

    os.unlink(doc_path)


def demonstrate_configuration_patterns():
    """Demonstrate configuration patterns."""

    print("\n" + "=" * 80)
    print("⚙️  CONFIGURATION PATTERNS")
    print("=" * 80)

    # Pattern 1: Vision + Audio only (no documents)
    print("\n1️⃣  Vision + Audio Only (Default)")
    print("   config = MultiModalConfig()")
    print("   - Standard multi-modal processing")
    print("   - Images and audio supported")
    print("   - No document extraction")

    # Pattern 2: All modalities with free provider
    print("\n2️⃣  All Modalities (Free Provider)")
    print("   config = MultiModalConfig(")
    print("       enable_document_extraction=True,")
    print("       # No API keys = uses Ollama (free)")
    print("   )")
    print("   - Vision, Audio, Documents supported")
    print("   - Uses Ollama for document extraction")
    print("   - 85% accuracy, unlimited free use")

    # Pattern 3: All modalities with cost tracking
    print("\n3️⃣  All Modalities with Cost Tracking")
    print("   config = MultiModalConfig(")
    print("       enable_document_extraction=True,")
    print("       enable_cost_tracking=True,")
    print("       budget_limit=10.0,")
    print("       landing_ai_api_key=os.getenv('LANDING_AI_API_KEY'),")
    print("   )")
    print("   - All modalities + cost tracking")
    print("   - Budget constraints enforced")
    print("   - Automatic cost warnings")


def main():
    """Run all MultiModalAgent document demonstrations."""

    print("=" * 80)
    print("🚀 MULTIMODALAGENT DOCUMENT AUTO-DETECTION DEMO")
    print("=" * 80)

    # Part 1: Auto-detection
    demonstrate_auto_detection()

    # Part 2: Document processing
    demonstrate_document_processing()

    # Part 3: Unified API
    demonstrate_unified_API()

    # Part 4: Cost tracking
    demonstrate_cost_tracking()

    # Part 5: Configuration patterns
    demonstrate_configuration_patterns()

    print("\n" + "=" * 80)
    print("✨ MULTIMODALAGENT DOCUMENT DEMO COMPLETE")
    print("=" * 80)

    print("\n💡 Key Takeaways:")
    print("   1. Documents auto-detected by file extension")
    print("   2. Same analyze() method for all modalities")
    print("   3. Optional LLM-based Q&A over documents")
    print("   4. Cost tracking across all modalities")
    print("   5. Zero breaking changes to existing code")

    print("\n📚 Related Examples:")
    print("   - vision_agent_document_demo.py: VisionAgent enhancement")
    print("   - cost_estimation_demo.py: Cost estimation patterns")
    print("   - advanced_rag.py: Multi-document RAG workflows")


if __name__ == "__main__":
    main()

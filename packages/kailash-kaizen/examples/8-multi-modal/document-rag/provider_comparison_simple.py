"""
Simple Provider Comparison

Quick demonstration of comparing all 3 providers side-by-side.
"""

import os
import tempfile

from kaizen.agents.multi_modal.document_extraction_agent import (
    DocumentExtractionAgent,
    DocumentExtractionConfig,
)


def main():
    """Compare all providers."""
    # Create test document
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as tmp:
        tmp.write("Sample invoice: Total $1,234.56")
        doc_path = tmp.name

    print("=" * 70)
    print("Provider Comparison")
    print("=" * 70)

    # Test each provider
    providers = ["landing_ai", "openai_vision", "ollama_vision"]

    for provider_name in providers:
        try:
            config = DocumentExtractionConfig(
                provider=provider_name,
                landing_ai_key=os.getenv("LANDING_AI_API_KEY"),
                openai_key=os.getenv("OPENAI_API_KEY"),
            )
            agent = DocumentExtractionAgent(config=config)

            if not agent.provider.is_available():
                print(f"\n{provider_name}: NOT AVAILABLE")
                continue

            result = agent.extract(doc_path, extract_tables=False, chunk_for_rag=False)

            print(f"\n{provider_name}:")
            print(f"  Text: {len(result['text'])} chars")
            print(f"  Cost: ${result['cost']:.3f}")
            print(f"  Time: {result['processing_time']:.2f}s")

        except Exception as e:
            print(f"\n{provider_name}: ERROR - {str(e)}")

    os.unlink(doc_path)
    print("\n" + "=" * 70)
    print("Recommendation: Use Ollama (free) for development/testing")
    print("=" * 70)


if __name__ == "__main__":
    main()

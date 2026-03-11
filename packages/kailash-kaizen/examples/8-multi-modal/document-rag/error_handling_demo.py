"""
Error Handling Patterns

Demonstrates robust error handling in document extraction.
"""

from kaizen.agents.multi_modal.document_extraction_agent import (
    DocumentExtractionAgent,
    DocumentExtractionConfig,
)


def main():
    """Demonstrate error handling patterns."""
    print("=" * 70)
    print("Error Handling Patterns")
    print("=" * 70)

    config = DocumentExtractionConfig(provider="ollama_vision")
    agent = DocumentExtractionAgent(config=config)

    # Case 1: File not found
    print("\n1. Handling missing files:")
    try:
        result = agent.extract("nonexistent.pdf")
        print("  ERROR: Should have raised exception")
    except FileNotFoundError as e:
        print(f"  ✅ Caught: {type(e).__name__}")

    # Case 2: Invalid file type
    print("\n2. Handling invalid file types:")
    try:
        result = agent.extract("test.xyz")  # Unsupported extension
        print("  ERROR: Should have raised exception")
    except ValueError as e:
        print(f"  ✅ Caught: {type(e).__name__}")

    # Case 3: Provider unavailable
    print("\n3. Handling unavailable provider:")
    try:
        bad_config = DocumentExtractionConfig(provider="landing_ai")  # No API key
        bad_agent = DocumentExtractionAgent(config=bad_config)
        # Should fail if provider not available
        if not bad_agent.provider.is_available():
            print("  ✅ Provider unavailable detected")
    except Exception as e:
        print(f"  ✅ Caught: {type(e).__name__}")

    # Case 4: Best practice - graceful fallback
    print("\n4. Best Practice - Graceful Fallback:")
    print("  def extract_with_fallback(file_path):")
    print("      providers = ['landing_ai', 'openai_vision', 'ollama_vision']")
    print("      for provider in providers:")
    print("          try:")
    print("              result = agent.extract(file_path, provider=provider)")
    print("              return result")
    print("          except:")
    print("              continue  # Try next provider")
    print("      raise RuntimeError('All providers failed')")

    print("\n" + "=" * 70)
    print("Always handle FileNotFoundError, ValueError, and RuntimeError")
    print("=" * 70)


if __name__ == "__main__":
    main()

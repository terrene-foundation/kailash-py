"""Demonstration of LLMAgent with multiple provider support."""

import os
import sys

# Add the src directory to Python path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from kailash.nodes.ai import LLMAgent
from kailash.nodes.ai.ai_providers import PROVIDERS, get_provider


def main():
    """Demonstrate the clean provider architecture."""
    print("🤖 LLMAgent Provider Architecture Demo")
    print("=" * 50)

    # Show available providers
    print("\n📋 Available LLM Providers:")
    for provider_name in PROVIDERS:
        try:
            provider = get_provider(provider_name)
            available = provider.is_available()
            status = "✅ Available" if available else "❌ Not available"
            print(f"   - {provider_name}: {status}")
        except Exception as e:
            print(f"   - {provider_name}: ❌ Error - {e}")

    print("\n" + "-" * 50)

    # Test message
    test_message = "What are the benefits of modular software architecture?"

    # 1. Mock Provider (always available)
    print("\n1. Mock Provider:")
    mock_result = LLMAgent().run(
        provider="mock",
        model="mock-model",
        messages=[{"role": "user", "content": test_message}],
    )

    if mock_result["success"]:
        print(f"   Response: {mock_result['response']['content'][:100]}...")
        print(f"   Provider: {mock_result['metadata']['provider']}")

    # 2. Ollama Provider (if available)
    print("\n2. Ollama Provider:")
    try:
        provider = get_provider("ollama")
        if provider.is_available():
            ollama_result = LLMAgent().run(
                provider="ollama",
                model="llama3.1:8b-instruct-q8_0",
                messages=[{"role": "user", "content": test_message}],
                generation_config={"temperature": 0.7, "max_tokens": 200},
            )

            if ollama_result["success"]:
                print(f"   Response: {ollama_result['response']['content'][:150]}...")
                print(f"   Model: {ollama_result['response']['model']}")
                print(f"   Tokens: {ollama_result['usage']['total_tokens']}")
            else:
                print(f"   Error: {ollama_result.get('error')}")
        else:
            print(
                "   ❌ Ollama not available. Install and start Ollama to use this provider."
            )
    except Exception as e:
        print(f"   Error: {e}")

    # 3. OpenAI Provider (if API key is set)
    print("\n3. OpenAI Provider:")
    if os.getenv("OPENAI_API_KEY"):
        try:
            openai_result = LLMAgent().run(
                provider="openai",
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": test_message}],
                generation_config={"temperature": 0.7, "max_tokens": 200},
            )

            if openai_result["success"]:
                print(f"   Response: {openai_result['response']['content'][:150]}...")
                print(f"   Model: {openai_result['response']['model']}")
                print(f"   Tokens: {openai_result['usage']['total_tokens']}")
                print(f"   Cost: ${openai_result['usage']['estimated_cost_usd']:.6f}")
        except Exception as e:
            print(f"   Error: {e}")
    else:
        print("   ❌ OpenAI API key not set. Set OPENAI_API_KEY environment variable.")

    # 4. Anthropic Provider (if API key is set)
    print("\n4. Anthropic Provider:")
    if os.getenv("ANTHROPIC_API_KEY"):
        try:
            anthropic_result = LLMAgent().run(
                provider="anthropic",
                model="claude-3-haiku-20240307",
                messages=[{"role": "user", "content": test_message}],
                system_prompt="You are a software architecture expert.",
                generation_config={"temperature": 0.7, "max_tokens": 200},
            )

            if anthropic_result["success"]:
                print(
                    f"   Response: {anthropic_result['response']['content'][:150]}..."
                )
                print(f"   Model: {anthropic_result['response']['model']}")
                print(f"   Tokens: {anthropic_result['usage']['total_tokens']}")
        except Exception as e:
            print(f"   Error: {e}")
    else:
        print(
            "   ❌ Anthropic API key not set. Set ANTHROPIC_API_KEY environment variable."
        )

    # Show how to add a custom provider
    print("\n5. Adding Custom Providers:")
    print("   To add a new provider:")
    print("   1. Create a class inheriting from LLMProvider in ai_providers.py")
    print("   2. Implement is_available() and chat() methods")
    print("   3. Add to PROVIDERS registry")
    print("   4. Use with: LLMAgent().run(provider='your_provider', ...)")

    print("\n" + "=" * 50)
    print("🎯 Architecture Benefits:")
    print("   ✅ Clean separation of concerns")
    print("   ✅ Easy to add new providers")
    print("   ✅ No provider-specific code in LLMAgent")
    print("   ✅ Each provider manages its own dependencies")
    print("   ✅ Consistent interface across all providers")
    print("   ✅ Graceful fallbacks when providers unavailable")


if __name__ == "__main__":
    main()

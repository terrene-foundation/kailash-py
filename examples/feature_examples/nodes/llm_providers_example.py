"""Demonstration of LLMAgentNode with multiple provider support."""

import os
import sys

# Add the src directory to Python path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.ai.ai_providers import PROVIDERS, get_provider


def main():
    """Demonstrate the clean provider architecture."""
    print("🤖 LLMAgentNode Provider Architecture Demo")
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
    mock_result = LLMAgentNode().run(
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
            ollama_result = LLMAgentNode().run(
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
            # Show both old and new parameter usage
            print("   Testing with new parameter (recommended):")
            openai_result = LLMAgentNode().run(
                provider="openai",
                model="o4-mini",  # Using newer model
                messages=[{"role": "user", "content": test_message}],
                # generation_config={"temperature": 1, "max_completion_tokens": 200, "top_p": 1},
            )
            if openai_result["success"]:
                print(f"   Response: {openai_result['response']['content'][:150]}...")
                print(f"   Model: {openai_result['response']['model']}")
                print(f"   Tokens: {openai_result['usage']['total_tokens']}")
                print(f"   Cost: ${openai_result['usage']['estimated_cost_usd']:.6f}")

            # Also demonstrate old parameter (will show deprecation warning)
            print("\n   Testing with old parameter (deprecated):")
            old_style_result = LLMAgentNode().run(
                provider="openai",
                model="gpt-4o-mini",  # Vision-capable model that supports new param
                messages=[{"role": "user", "content": "What is 2+2?"}],
                generation_config={"temperature": 0, "max_tokens": 50},  # Old parameter
            )
            if old_style_result["success"]:
                print(f"   Response: {old_style_result['response']['content']}")
                print("   ⚠️  Check console for deprecation warning!")

        except Exception as e:
            print(f"   Error: {e}")
    else:
        print("   ❌ OpenAI API key not set. Set OPENAI_API_KEY environment variable.")

    # 4. Anthropic Provider (if API key is set)
    print("\n4. Anthropic Provider:")
    if os.getenv("ANTHROPIC_API_KEY"):
        try:
            anthropic_result = LLMAgentNode().run(
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
    print("   4. Use with: LLMAgentNode().run(provider='your_provider', ...)")

    # 6. Vision Capabilities Demo
    print("\n6. Vision Capabilities (NEW!):")
    print("   All providers now support vision/image inputs!")
    print("\n   Example - Analyzing an image:")
    print("   vision_result = LLMAgentNode().run(")
    print('       provider="openai",')
    print('       model="gpt-4o-mini",')
    print("       messages=[{")
    print('           "role": "user",')
    print('           "content": [')
    print('               {"type": "text", "text": "What\'s in this image?"},')
    print('               {"type": "image", "path": "photo.jpg"}')
    print("           ]")
    print("       }]")
    print("   )")
    print("\n   ✅ Backward compatible - existing text-only code still works")
    print("   ✅ Supports file paths and base64 images")
    print("   ✅ Multi-image support")
    print("   ✅ Automatic format conversion per provider")

    print("\n" + "=" * 50)
    print("🎯 Architecture Benefits:")
    print("   ✅ Clean separation of concerns")
    print("   ✅ Easy to add new providers")
    print("   ✅ No provider-specific code in LLMAgentNode")
    print("   ✅ Each provider manages its own dependencies")
    print("   ✅ Consistent interface across all providers")
    print("   ✅ Graceful fallbacks when providers unavailable")
    print("   ✅ Vision support with lazy loading (NEW!)")


if __name__ == "__main__":
    main()

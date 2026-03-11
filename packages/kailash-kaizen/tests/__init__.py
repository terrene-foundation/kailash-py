"""
Test package for Kaizen framework.

MockProvider patching is handled in root conftest.py.
"""

# Verify root conftest.py patch was applied (for debugging)
try:
    from kailash.nodes.ai.ai_providers import PROVIDERS

    # Get provider from registry (how it's actually used)
    MockProviderClass = PROVIDERS.get("mock")
    if MockProviderClass:
        result = MockProviderClass().chat(
            [{"role": "user", "content": '```json\n{"test": "value"}\n```'}]
        )
        content = result.get("content", "")
        # Check if we got JSON response (KaizenMockProvider should return JSON string)
        if '{"test": "value"}' in content or '"test"' in content:
            pass  # Root conftest patch is working
        else:
            print(
                f"ERROR: Root conftest.py MockProvider patch not applied! Got: {content[:100]}"
            )
    else:
        print("ERROR: No 'mock' provider in PROVIDERS registry!")
except Exception as e:
    print(f"ERROR: MockProvider check failed: {e}")

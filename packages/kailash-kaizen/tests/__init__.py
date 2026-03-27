"""
Test package for Kaizen framework.

MockProvider patching is handled in root conftest.py.
"""

# Verify root conftest.py patch was applied (for debugging)
try:
    try:
        from kaizen.nodes.ai.ai_providers import PROVIDERS
    except ImportError:
        from kailash.nodes.ai.ai_providers import PROVIDERS

    MockProviderClass = PROVIDERS.get("mock")
    if MockProviderClass:
        result = MockProviderClass().chat(
            [{"role": "user", "content": '```json\n{"test": "value"}\n```'}]
        )
        content = result.get("content", "")
        if '{"test": "value"}' in content or '"test"' in content:
            pass  # Root conftest patch is working
except (ImportError, AttributeError, Exception):
    pass  # AI provider modules not available in this context

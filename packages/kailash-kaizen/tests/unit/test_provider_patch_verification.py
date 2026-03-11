"""Test to verify provider during actual pytest run."""

import os

import pytest


@pytest.mark.skipif(
    os.environ.get("KAIZEN_ALLOW_MOCK_PROVIDERS") == "true",
    reason="Mock provider verification not applicable when using real providers",
)
def test_verify_provider_class():
    """Verify that get_provider('mock') returns KaizenMockProvider during test."""
    from kaizen.nodes.ai.ai_providers import PROVIDERS, get_provider

    # Check registry
    print(f"\nPROVIDERS['mock']: {PROVIDERS['mock']}")
    print(f"PROVIDERS['mock'] module: {PROVIDERS['mock'].__module__}")

    # Check get_provider
    provider = get_provider("mock")
    print(f"\nget_provider('mock') returned: {provider.__class__}")
    print(f"Provider module: {provider.__class__.__module__}")

    # Verify it's KaizenMockProvider
    assert (
        "kaizen" in provider.__class__.__module__.lower()
        or "Kaizen" in provider.__class__.__name__
    )

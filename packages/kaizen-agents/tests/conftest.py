"""
Test configuration for kaizen-agents package.

Provides shared fixtures for the agent engine tests migrated from kailash-kaizen.
"""

import os
import sys

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass  # python-dotenv not installed — env vars from shell

# Check if we should use real providers (for E2E/integration tests)
use_real_providers = os.getenv("USE_REAL_PROVIDERS", "").lower() == "true"

if not use_real_providers:
    try:
        import kaizen.nodes.ai.ai_providers as ai_providers_module

        from tests.utils.kaizen_mock_provider import KaizenMockProvider

        ai_providers_module.PROVIDERS["mock"] = KaizenMockProvider
        ai_providers_module.MockProvider = KaizenMockProvider
    except (ImportError, AttributeError):
        pass  # AI provider modules not available

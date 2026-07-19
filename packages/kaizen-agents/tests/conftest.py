"""
Test configuration for kaizen-agents package.

Provides shared fixtures for the agent engine tests migrated from kailash-kaizen.
"""

import os
from pathlib import Path

from kailash.testing.env_cost_guard import install_cost_guard, scrub_provider_secrets

# LLM cost-guard: a bare `pytest` (no KAIZEN_ALLOW_REAL_LLM=1) must make ZERO
# billed LLM calls. kaizen-agents declares its own pytest rootdir, so the
# repo-root conftest guard never fires here. install_cost_guard loads .env with
# provider secret keys withheld, monkeypatches dotenv.load_dotenv so any
# module-scope / nested-conftest load_dotenv self-scrubs, and actively removes
# any secret already present. Model names + non-secret vars still load.
install_cost_guard(Path(__file__).resolve().parents[3] / ".env")


def pytest_collection_finish(session):
    """Backstop: after every module (and its module-scope load_dotenv) is
    imported, remove any provider secret re-injected during collection."""
    scrub_provider_secrets()


# Unit-tier deterministic model default (issue-822 pattern): supervisor /
# governance tests construct agents that resolve the model from the
# environment (kaizen.errors.EnvModelMissing otherwise). No kaizen-agents
# test asserts the missing-var path; tests that need a specific model
# override per-test. setdefault preserves any operator/.env value.
os.environ.setdefault("KAIZEN_DEFAULT_MODEL", "gpt-4o-mini")

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

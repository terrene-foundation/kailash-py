# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
Conftest for tier_2 integration tests.

Loads .env (with the LLM cost-guard) before any test execution and adds the
integration test directory to sys.path so that `import models` works from test
files.
"""

import sys
from pathlib import Path

from kailash.testing.env_cost_guard import install_cost_guard, scrub_provider_secrets

# .env is the single source of truth for model names, DB URLs, and non-secret
# config. install_cost_guard withholds provider secret keys on a bare
# `pytest tests/tier_2/integration`, monkeypatches dotenv.load_dotenv so the
# module-scope load_dotenv() calls in sibling test modules self-scrub, and
# actively removes any secret already present — provider secrets load only with
# KAIZEN_ALLOW_REAL_LLM=1 (mirrors the repo-root conftest guard).
install_cost_guard(Path(__file__).resolve().parents[3] / ".env")


def pytest_collection_finish(session):
    """Backstop: remove any provider secret re-injected during collection."""
    scrub_provider_secrets()


# Add this directory to sys.path so `import models` resolves correctly
_this_dir = str(Path(__file__).parent)
if _this_dir not in sys.path:
    sys.path.insert(0, _this_dir)

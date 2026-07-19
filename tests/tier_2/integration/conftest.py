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

from kailash.testing.env_cost_guard import load_env_cost_guarded

# .env is the single source of truth for model names, DB URLs, and non-secret
# config. Load it through the shared cost-guard so a bare
# `pytest tests/tier_2/integration` cannot re-inject a provider secret key and
# make a billed LLM call — provider secrets load only with
# KAIZEN_ALLOW_REAL_LLM=1 (mirrors the repo-root conftest guard).
load_env_cost_guarded(Path(__file__).resolve().parents[3] / ".env")

# Add this directory to sys.path so `import models` resolves correctly
_this_dir = str(Path(__file__).parent)
if _this_dir not in sys.path:
    sys.path.insert(0, _this_dir)

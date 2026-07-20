# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Regression: the kaizen-agents pytest rootdir withholds provider secrets.

kaizen-agents declares its own pytest rootdir, so the repo-root conftest guard
never fires for `pytest packages/kaizen-agents`. This durable test pins the
package-root conftest cost-guard so a future regression (guard removed / rootdir
moved) fails loudly instead of silently carrying a provider credential into the
session (issue #1845/#1848).
"""

import os


def test_kaizen_agents_rootdir_scrubs_provider_secrets():
    if os.environ.get("KAIZEN_ALLOW_REAL_LLM") == "1":
        return  # opt-in on: real-LLM tests intentionally carry credentials
    for name in (
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "GOOGLE_API_KEY",
        "AWS_BEARER_TOKEN_BEDROCK",
        "DEEPSEEK_API_KEY",
    ):
        assert os.environ.get(name) is None, (
            f"{name} leaked into the kaizen-agents pytest session — the rootdir "
            f"cost-guard (packages/kaizen-agents/conftest.py) is not firing"
        )

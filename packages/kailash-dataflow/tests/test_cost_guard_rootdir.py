# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Regression: the kailash-dataflow pytest rootdir withholds provider secrets.

``DataFlow.from_brief()`` constructs a ``BaseAgent`` and calls ``agent.run(...)``
— a real billed LLM call whose Tier-2 gate checks only the model-name var, not
the API key. So a bare ``pytest packages/kailash-dataflow`` MUST NOT carry a
provider credential in ``os.environ`` (issue #1845). This durable test pins the
dataflow rootdir conftest guard so a future regression (guard removed / rootdir
moved) fails loudly instead of silently billing.
"""

import os


def test_dataflow_rootdir_scrubs_provider_secrets():
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
            f"{name} leaked into the kailash-dataflow pytest session — the rootdir "
            f"cost-guard (packages/kailash-dataflow/conftest.py) is not firing"
        )

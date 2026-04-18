# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Tier 2 wiring test: LlmClient.from_deployment + OpenAI preset.

Per `rules/facade-manager-detection.md` §2, the wiring file exists at its
canonical path so absence is grep-able. Session 1 ships only the structural
abstraction — the `complete()` send path raises NotImplementedError until S3.
This test skips with a clear marker so the file can be enabled verbatim when
S3 lands.
"""

from __future__ import annotations

import os

import pytest

from kaizen.llm import LlmClient, LlmDeployment


@pytest.mark.integration
async def test_llmclient_from_deployment_openai_wiring() -> None:
    """End-to-end: LlmClient.from_deployment(LlmDeployment.openai(...)) completes a real one-token request."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        pytest.skip("OPENAI_API_KEY not set; wiring test requires live credential")
    pytest.skip(
        "S1 client send-path stubbed; wiring test enabled in session 3 (S3). "
        "See LlmClient.complete() NotImplementedError."
    )
    # When S3 lands, the body below is the enabled test:
    # deployment = LlmDeployment.openai(api_key, model="gpt-4o-mini")
    # client = LlmClient.from_deployment(deployment)
    # response = await client.complete(
    #     messages=[{"role": "user", "content": "Say 'ok'"}],
    #     max_tokens=1,
    # )
    # assert response is not None


@pytest.mark.integration
def test_llmclient_from_deployment_constructs_client() -> None:
    """Structural wiring: the client holds the deployment correctly."""
    deployment = LlmDeployment.openai("sk-test-structural-only")
    client = LlmClient.from_deployment(deployment)
    assert client.deployment is deployment
    assert client.deployment.wire.name == "OpenAiChat"

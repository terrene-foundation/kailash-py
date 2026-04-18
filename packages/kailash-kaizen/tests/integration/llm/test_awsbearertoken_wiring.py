# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Tier 2 wiring test for `AwsBearerToken` (#498 S4a).

Per `rules/facade-manager-detection.md` § 2, the wiring file lives at its
canonical path so absence is grep-able. `AwsBearerToken` is the manager-
shape class for Bedrock bearer auth; this test exercises the end-to-end
path from `LlmDeployment.bedrock_claude(...)` construction through to
the installed auth strategy.

The live-completion path (a real Bedrock POST) is gated on
`AWS_BEARER_TOKEN_BEDROCK` being set. Without the env var the live call
is skipped and we exercise only the structural wiring (construction +
header shape). The `LlmClient.complete()` implementation lands in S3 of
the S3/S4 sequence; until then this test verifies the wiring is correct
and ready to flip on.
"""

from __future__ import annotations

import os

import pytest

from kaizen.llm import LlmClient, LlmDeployment
from kaizen.llm.auth.aws import AwsBearerToken


@pytest.mark.integration
def test_llmclient_from_deployment_bedrock_claude_wires_auth_strategy() -> None:
    """Structural wiring: the client holds the deployment, and the deployment's
    auth is an `AwsBearerToken` with `auth_strategy_kind=='aws_bearer_token'`.
    """
    token = os.environ.get("AWS_BEARER_TOKEN_BEDROCK", "test-structural-only")
    deployment = LlmDeployment.bedrock_claude(
        token, region="us-east-1", model="claude-sonnet-4-6"
    )
    client = LlmClient.from_deployment(deployment)
    assert client.deployment is deployment
    assert isinstance(client.deployment.auth, AwsBearerToken)
    assert client.deployment.auth.auth_strategy_kind() == "aws_bearer_token"
    # Endpoint host reflects the validated region.
    assert "us-east-1" in str(client.deployment.endpoint.base_url)
    assert client.deployment.wire.name == "AnthropicMessages"


@pytest.mark.integration
def test_awsbearertoken_apply_installs_authorization_header_end_to_end() -> None:
    """End-to-end: applying the auth strategy from a real deployment to a
    real request dict installs `Authorization: Bearer <token>`.
    """
    token = os.environ.get("AWS_BEARER_TOKEN_BEDROCK", "test-structural-only")
    deployment = LlmDeployment.bedrock_claude(
        token, region="us-east-1", model="claude-sonnet-4-6"
    )
    req: dict = {"headers": {}}
    deployment.auth.apply(req)
    assert req["headers"]["Authorization"] == f"Bearer {token}"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_llmclient_from_deployment_bedrock_claude_live_completion() -> None:
    """Live Bedrock completion -- skipped without real credentials.

    When S3 lands `LlmClient.complete()`, this test will exercise a real
    one-token completion against Bedrock.
    """
    token = os.environ.get("AWS_BEARER_TOKEN_BEDROCK")
    if not token:
        pytest.skip("AWS_BEARER_TOKEN_BEDROCK not set; live wiring requires real token")
    pytest.skip(
        "LlmClient.complete() wire-send path is implemented in session 3 (S3); "
        "this test flips on when complete() lands."
    )

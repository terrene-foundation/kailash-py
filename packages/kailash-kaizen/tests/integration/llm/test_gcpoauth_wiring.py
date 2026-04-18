# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Tier 2 wiring test for `GcpOauth` (#498 S5).

Per `rules/facade-manager-detection.md` §2, the wiring file lives at
its canonical path so absence is grep-able. `GcpOauth` is the
manager-shape class for Vertex auth; this test exercises the end-to-end
path from `LlmDeployment.vertex_claude(...)` / `vertex_gemini(...)`
construction through to the installed auth strategy.

The live token-fetch path is gated on `GOOGLE_APPLICATION_CREDENTIALS`
being set. Without the env var, the live fetch is skipped and we
exercise only the structural wiring (construction + auth instance
type + endpoint shape). The `LlmClient.complete()` send-path lands in a
later session; until then this test verifies the wiring is correct and
ready to flip on.
"""

from __future__ import annotations

import os

import pytest

from kaizen.llm import LlmClient, LlmDeployment
from kaizen.llm.auth.gcp import GcpOauth


def _placeholder_service_account_dict() -> dict:
    """Minimal service-account shape for structural tests.

    Has the right fields for google-auth's parser to accept it but the
    private key is a stub -- it cannot mint a real token. Used for
    structural-only wiring assertions; the live test path uses the real
    `GOOGLE_APPLICATION_CREDENTIALS` env var instead.
    """
    return {
        "type": "service_account",
        "project_id": "structural-test",
        "private_key_id": "structural",
        "private_key": (
            "-----BEGIN PRIVATE KEY-----\nSTRUCTURAL\n-----END PRIVATE KEY-----"
        ),
        "client_email": "structural@example.iam.gserviceaccount.com",
        "client_id": "structural",
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
        "client_x509_cert_url": "https://x.example",
    }


@pytest.mark.integration
def test_llmclient_from_deployment_vertex_claude_wires_auth_strategy() -> None:
    """Structural wiring: client holds the deployment, the deployment's
    auth is a `GcpOauth` with `auth_strategy_kind == "gcp_oauth"`.
    """
    deployment = LlmDeployment.vertex_claude(
        _placeholder_service_account_dict(),
        project="structural-test-1234",
        region="us-central1",
        model="claude-sonnet-4-6",
    )
    client = LlmClient.from_deployment(deployment)
    assert client.deployment is deployment
    assert isinstance(client.deployment.auth, GcpOauth)
    assert client.deployment.auth.auth_strategy_kind() == "gcp_oauth"
    # Endpoint host reflects the validated region.
    assert "us-central1-aiplatform.googleapis.com" in str(
        client.deployment.endpoint.base_url
    )
    assert client.deployment.wire.name == "AnthropicMessages"


@pytest.mark.integration
def test_llmclient_from_deployment_vertex_gemini_wires_auth_strategy() -> None:
    """Structural wiring: same shape as vertex_claude but Gemini wire."""
    deployment = LlmDeployment.vertex_gemini(
        _placeholder_service_account_dict(),
        project="structural-test-1234",
        region="europe-west4",
        model="gemini-1.5-pro",
    )
    client = LlmClient.from_deployment(deployment)
    assert isinstance(client.deployment.auth, GcpOauth)
    assert client.deployment.auth.auth_strategy_kind() == "gcp_oauth"
    assert "europe-west4-aiplatform.googleapis.com" in str(
        client.deployment.endpoint.base_url
    )
    assert client.deployment.wire.name == "VertexGenerateContent"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_gcpoauth_token_fetch_against_real_credentials() -> None:
    """Live token fetch -- skipped without real GOOGLE_APPLICATION_CREDENTIALS.

    When the env var points at a valid service-account JSON file, this
    test mints a real OAuth2 access token via google-auth and verifies
    the cached token is non-empty. This is the only test in the suite
    that exercises the real google-auth provider chain.
    """
    creds_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if not creds_path or not os.path.exists(creds_path):
        pytest.skip(
            "GOOGLE_APPLICATION_CREDENTIALS not set or file missing; "
            "live token fetch requires a real service-account JSON"
        )
    auth = GcpOauth.from_env()
    cached = await auth.refresh()
    assert cached.token.get_secret_value()  # non-empty
    assert cached.expiry_epoch > 0
    assert auth.refresh_count == 1


@pytest.mark.integration
@pytest.mark.asyncio
async def test_llmclient_from_deployment_vertex_claude_live_completion() -> None:
    """Live Vertex completion -- skipped without real credentials.

    When `LlmClient.complete()` lands in a later session, this test
    will exercise a real one-token completion against Vertex.
    """
    creds_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    project = os.environ.get("VERTEX_PROJECT")
    if not creds_path or not project:
        pytest.skip(
            "GOOGLE_APPLICATION_CREDENTIALS + VERTEX_PROJECT not set; "
            "live wiring requires real credentials"
        )
    pytest.skip(
        "LlmClient.complete() wire-send path lands in a later session; "
        "this test flips on when complete() lands."
    )

# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Tier 2 wiring test: LlmClient managed-mode HTTP transport pooling (#1388).

Sibling of `test_llmclient_embed_wiring.py`. Exercises the opt-in pooled
lifecycle end-to-end: under `async with`, two sequential `embed()` calls REUSE
ONE `LlmHttpClient` (asserted by object identity), the persistent transport is
open mid-scope, and closed after the scope exits.

The object-identity / pooling assertions run against the SSRF connect-time
rejection path — no credential, no network egress: enter the managed scope, call
`embed()` against `https://localhost/...`. The URL-safety guard passes that at
deployment construction (it cannot resolve the hostname to know it is loopback),
so `embed()` reaches the HTTP layer; the `SafeDnsResolver` then rejects the
`127.0.0.1` resolution at connect time inside the transport, raising
`EndpointError` before any TCP SYN leaves the box. The test asserts the
persistent client is (a) the SAME object across two such attempts and (b) NOT
closed mid-scope (per-call errors must not close the instance-owned transport).
The real-network path is gated on `OPENAI_API_KEY` like the existing embed test.

NOTE on host choice: a literal private/metadata IP (e.g. `169.254.169.254`) is
rejected by the URL-safety guard at deployment CONSTRUCTION, so `embed()` is
never reached and the pooling assertion never runs. A loopback HOSTNAME
(`localhost`) passes construction and defers the rejection to the connect-time
resolver inside `embed()` — which is exactly the path that exercises the pooled
transport.

Per `rules/testing.md` Tier 2 policy: real infrastructure, NO mocking of the
wire layer. The SSRF guard fires against a real DNS/IP check, not a mock.
"""

from __future__ import annotations

import os

import pytest

from kaizen.llm import LlmClient
from kaizen.llm.deployment import LlmDeployment
from kaizen.llm.errors import EndpointError

_EMBED_MODEL = "text-embedding-3-small"


# ---------------------------------------------------------------------------
# Pooling via the SSRF-rejection path — always runs, no credential needed
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_managed_embed_reuses_one_http_client_across_calls() -> None:
    """Under `async with`, two embed() calls reuse ONE LlmHttpClient.

    Uses the connect-time SSRF-rejection path (`https://localhost/...` resolves
    to loopback) so no real embedding credential and no network egress is
    required. Each embed() reaches the HTTP layer and raises EndpointError when
    `SafeDnsResolver` rejects `127.0.0.1` at connect; the assertions prove the
    INSTANCE-pooled transport (a) is the same object across both calls and (b)
    survives the per-call error (NOT closed), so it can be reused — exactly the
    pooling contract #1388 adds.
    """
    # docker_model_runner accepts a caller-provided base_url + uses the
    # OpenAiChat wire (the embed() dispatch key). A loopback HOSTNAME passes the
    # construction-time URL-safety guard (the guard cannot resolve the hostname's
    # IP) and defers rejection to the connect-time resolver inside embed().
    deployment = LlmDeployment.docker_model_runner(
        base_url="https://localhost/engines",
        model=_EMBED_MODEL,
    )

    async with LlmClient.from_deployment(deployment) as client:
        # __aenter__ eagerly pooled the transport.
        assert client._http_client is not None
        first_transport = client._http_client
        assert first_transport.is_closed is False

        # Call 1 — SSRF guard rejects at connect time.
        with pytest.raises(EndpointError):
            await client.embed(["ssrf attempt 1"], model=_EMBED_MODEL)

        # The instance-owned transport survives the per-call error: same object,
        # still open (NOT closed by the error path — owns_client is False).
        assert client._http_client is first_transport
        assert client._http_client.is_closed is False

        # Call 2 — reuses the SAME transport object.
        with pytest.raises(EndpointError):
            await client.embed(["ssrf attempt 2"], model=_EMBED_MODEL)

        assert client._http_client is first_transport
        assert client._http_client.is_closed is False

    # After the managed scope: transport closed + reference dropped.
    assert first_transport.is_closed is True
    assert client._http_client is None


# ---------------------------------------------------------------------------
# Pooling via the real OpenAI path — gated on OPENAI_API_KEY
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_managed_embed_reuses_http_client_real_openai() -> None:
    """Real OpenAI: two managed embed() calls reuse one pooled transport.

    Confirms the pooling contract on the success path (not just SSRF rejection):
    the same LlmHttpClient object serves both real embedding requests and is
    closed only after the managed scope exits.
    """
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key or not api_key.startswith("sk-"):
        pytest.skip(
            "OPENAI_API_KEY missing or placeholder; real-network pooling test "
            "requires a real credential"
        )
    model = os.environ.get("OPENAI_EMBEDDING_MODEL", _EMBED_MODEL)

    deployment = LlmDeployment.openai(api_key=api_key, model=model)
    async with LlmClient.from_deployment(deployment) as client:
        pooled = client._http_client
        assert pooled is not None
        assert pooled.is_closed is False

        v1 = await client.embed(["hello"], model=model)
        assert client._http_client is pooled  # reused, not reconstructed
        assert pooled.is_closed is False

        v2 = await client.embed(["world"], model=model)
        assert client._http_client is pooled  # still the same transport
        assert pooled.is_closed is False

        assert len(v1) == 1 and len(v2) == 1
        assert len(v1[0]) > 0 and len(v2[0]) > 0

    assert pooled.is_closed is True
    assert client._http_client is None

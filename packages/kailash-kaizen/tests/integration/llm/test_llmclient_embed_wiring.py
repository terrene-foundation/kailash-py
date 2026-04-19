# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Tier 2 wiring test: LlmClient.embed() end-to-end (#462).

Per `rules/facade-manager-detection.md` §2, this file exists at its canonical
path so absence is grep-able. Exercises the full `LlmClient.from_deployment()
→ .embed()` path: payload build → LlmHttpClient (SSRF guard) → real HTTP →
parse → typed return.

* OpenAI — real API if `OPENAI_API_KEY` is set; otherwise skipped.
* Ollama — real local server if `OLLAMA_BASE_URL` is set AND reachable;
  otherwise skipped.
* SSRF — always runs; does NOT require external infrastructure. Exercises
  the EndpointError path by pointing embed() at the AWS metadata service
  (169.254.169.254) and asserting the SSRF guard rejects DNS resolution
  before the TCP SYN fires.

Per `rules/testing.md` Tier 2 policy: real infrastructure recommended, NO
mocking of the wire layer.
"""

from __future__ import annotations

import os

import httpx
import pytest

from kaizen.llm import LlmClient
from kaizen.llm.deployment import LlmDeployment
from kaizen.llm.errors import EndpointError


# ---------------------------------------------------------------------------
# Real OpenAI
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_llmclient_embed_openai_real() -> None:
    """End-to-end: LlmClient.embed() returns a real vector from OpenAI."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        pytest.skip(
            "OPENAI_API_KEY not set; real OpenAI wiring test requires credential"
        )
    model = os.environ.get("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")

    deployment = LlmDeployment.openai(api_key=api_key, model=model)
    client = LlmClient.from_deployment(deployment)

    vectors = await client.embed(["hello", "world"], model=model)
    assert isinstance(vectors, list)
    assert len(vectors) == 2
    # text-embedding-3-small defaults to 1536 dims; text-embedding-3-large to 3072.
    # Accept either (operator may override via env).
    assert len(vectors[0]) in (
        1536,
        3072,
        768,
    ), f"unexpected vector dim for model={model}: {len(vectors[0])}"
    assert all(isinstance(v, float) for v in vectors[0])


# ---------------------------------------------------------------------------
# Real Ollama (optional; skipped if no local server)
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_llmclient_embed_ollama_real() -> None:
    """End-to-end: LlmClient.embed() against a local Ollama server.

    Requires `OLLAMA_BASE_URL` set (e.g. `http://localhost:11434`) AND a
    locally-pulled embedding model (e.g. `ollama pull nomic-embed-text`).
    Skipped otherwise — this is a localhost-only path and not every dev
    environment runs Ollama.
    """
    base_url = os.environ.get("OLLAMA_BASE_URL")
    if not base_url:
        pytest.skip("OLLAMA_BASE_URL not set; Ollama wiring test requires local server")
    model = os.environ.get("OLLAMA_EMBEDDING_MODEL", "nomic-embed-text")

    # Probe reachability before constructing the deployment to produce a
    # clear skip message rather than a late EndpointError.
    try:
        async with httpx.AsyncClient(timeout=2.0) as probe:
            await probe.get(base_url.rstrip("/") + "/api/tags")
    except (httpx.ConnectError, httpx.TimeoutException):
        pytest.skip(f"Ollama at {base_url} not reachable; skipping")

    deployment = LlmDeployment.ollama(base_url=base_url, model=model)
    client = LlmClient.from_deployment(deployment)

    vectors = await client.embed(["hello", "world"], model=model)
    assert isinstance(vectors, list)
    assert len(vectors) == 2
    assert len(vectors[0]) > 0
    assert all(isinstance(v, float) for v in vectors[0])


# ---------------------------------------------------------------------------
# SSRF regression — always runs, no external infra needed
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_llmclient_embed_rejects_aws_metadata_endpoint() -> None:
    """SSRF guard: embed() refuses to connect to the AWS metadata service.

    169.254.169.254 is the IMDS endpoint; any LLM base_url pointing there
    MUST be rejected — either at deployment construction (by
    `url_safety.check_url`) or at HTTP connect time (by `SafeDnsResolver`
    on LlmHttpClient's transport). The test asserts `EndpointError`
    (the common base) so it survives changes to where validation fires.
    """
    # docker_model_runner accepts a caller-provided base_url + uses the
    # OpenAiChat wire (dispatch key for embed()).
    try:
        deployment = LlmDeployment.docker_model_runner(
            base_url="http://169.254.169.254/engines",
            model="text-embedding-3-small",
        )
    except EndpointError:
        # Construction-time rejection is the strictest defense — OK.
        return
    client = LlmClient.from_deployment(deployment)

    with pytest.raises(EndpointError):
        await client.embed(["ssrf test"], model="text-embedding-3-small")


# ---------------------------------------------------------------------------
# Structural: embed() is wired on the LlmClient public surface
# ---------------------------------------------------------------------------


def test_llmclient_embed_is_coroutine_method() -> None:
    """Guards against accidental signature regression on the public surface."""
    import inspect

    assert hasattr(LlmClient, "embed")
    assert inspect.iscoroutinefunction(LlmClient.embed)

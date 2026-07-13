# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""End-to-end wire tests for `LlmClient.complete()` / `stream()` (#1717).

These exercise the FULL send-path (auth header injection → URL → body
serialization → HTTP round-trip → status taxonomy → response parse) against a
respx-mocked backend, so the completion facade is not shipped untested. The
broader per-provider respx matrix is a separate test pass; this file pins the
load-bearing behaviours that the pure-helper tests cannot reach:

* auth header actually installed on the wire,
* the platform-Anthropic body transform reaches the socket for Bedrock,
* error status → typed error,
* a REAL streaming send yields incremental parsed chunks.

A no-op resolver subclass is injected so the SSRF DNS guard does not perform a
real lookup against the mock host (the guard itself is covered by its own
tests); everything else is the production path.
"""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from kaizen.llm import LlmClient
from kaizen.llm.errors import ProviderError, RateLimited
from kaizen.llm.http_client import LlmHttpClient, SafeDnsResolver
from kaizen.llm.presets import bedrock_claude_preset, openai_preset


class _AllowAllResolver(SafeDnsResolver):
    """SafeDnsResolver that skips the real DNS lookup (test-only)."""

    __slots__ = ()

    def check_host(self, host: str) -> None:  # noqa: D401 - test stub resolver
        return None


def _client(dep):
    http = LlmHttpClient(deployment_preset=dep.wire.name, resolver=_AllowAllResolver())
    return LlmClient.from_deployment(dep), http


@pytest.mark.asyncio
@respx.mock
async def test_complete_openai_happy_path_installs_auth_and_parses() -> None:
    route = respx.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "pong"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 2, "completion_tokens": 1},
                "model": "gpt-4o",
            },
        )
    )
    dep = openai_preset("sk-secret", "gpt-4o")
    client, http = _client(dep)
    try:
        result = await client.complete(
            [{"role": "user", "content": "ping"}], http_client=http, max_tokens=16
        )
    finally:
        await http.aclose()
    assert result["text"] == "pong"
    assert result["stop_reason"] == "stop"
    sent = route.calls.last.request
    assert sent.headers["authorization"] == "Bearer sk-secret"
    body = json.loads(sent.content)
    assert body["model"] == "gpt-4o"
    assert body["messages"] == [{"role": "user", "content": "ping"}]


@pytest.mark.asyncio
@respx.mock
async def test_complete_bedrock_claude_sends_transformed_body_on_wire() -> None:
    dep = bedrock_claude_preset("tok", "us-east-1", "claude-sonnet-4-6")
    # Build the exact URL respx must match from the deployment itself.
    client, http = _client(dep)
    req = client._build_completion_request(
        [{"role": "user", "content": "hi"}],
        model=None,
        temperature=0.5,
        top_p=None,
        max_tokens=32,
        stop=None,
        user=None,
        stream=False,
    )
    _, url = client._build_completion_payload_and_url(req, stream=False)
    route = respx.post(url).mock(
        return_value=httpx.Response(
            200,
            json={
                "content": [{"type": "text", "text": "ok"}],
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 5, "output_tokens": 1},
                "model": "claude-sonnet-4-6",
            },
        )
    )
    try:
        result = await client.complete(
            [{"role": "user", "content": "hi"}],
            http_client=http,
            temperature=0.5,
            max_tokens=32,
        )
    finally:
        await http.aclose()
    assert result["text"] == "ok"
    sent = route.calls.last.request
    assert sent.headers["authorization"] == "Bearer tok"
    body = json.loads(sent.content)
    # Platform transform reached the wire: no `model`, anthropic_version present.
    assert "model" not in body
    assert body["anthropic_version"] == "bedrock-2023-05-31"


@pytest.mark.asyncio
@respx.mock
async def test_complete_maps_429_to_ratelimited() -> None:
    respx.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=httpx.Response(429, headers={"retry-after": "3"}, json={})
    )
    dep = openai_preset("sk-x", "gpt-4o")
    client, http = _client(dep)
    try:
        with pytest.raises(RateLimited):
            await client.complete([{"role": "user", "content": "hi"}], http_client=http)
    finally:
        await http.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_complete_maps_500_to_provider_error() -> None:
    respx.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=httpx.Response(500, text="upstream boom")
    )
    dep = openai_preset("sk-x", "gpt-4o")
    client, http = _client(dep)
    try:
        with pytest.raises(ProviderError):
            await client.complete([{"role": "user", "content": "hi"}], http_client=http)
    finally:
        await http.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_stream_openai_yields_incremental_chunks() -> None:
    sse = (
        'data: {"choices": [{"delta": {"content": "he"}}]}\n\n'
        'data: {"choices": [{"delta": {"content": "llo"}}]}\n\n'
        "data: [DONE]\n\n"
    )
    respx.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=httpx.Response(
            200, headers={"content-type": "text/event-stream"}, content=sse
        )
    )
    dep = openai_preset("sk-x", "gpt-4o")
    client, http = _client(dep)
    chunks = []
    try:
        async for chunk in client.stream(
            [{"role": "user", "content": "hi"}], http_client=http
        ):
            chunks.append(chunk["text"])
    finally:
        await http.aclose()
    assert chunks == ["he", "llo"]

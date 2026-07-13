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
import time

import httpx
import pytest
import respx
from pydantic import SecretStr

from kaizen.llm import LlmClient
from kaizen.llm.auth.gcp import CachedToken
from kaizen.llm.errors import ProviderError, RateLimited
from kaizen.llm.http_client import LlmHttpClient, SafeDnsResolver
from kaizen.llm.presets import (
    bedrock_claude_preset,
    openai_preset,
    vertex_claude_preset,
    vertex_gemini_preset,
)


class _AllowAllResolver(SafeDnsResolver):
    """SafeDnsResolver that skips the real DNS lookup (test-only)."""

    __slots__ = ()

    def check_host(self, host: str) -> None:  # noqa: D401 - test stub resolver
        return None


def _client(dep):
    http = LlmHttpClient(deployment_preset=dep.wire.name, resolver=_AllowAllResolver())
    return LlmClient.from_deployment(dep), http


def _fake_sa() -> dict:
    """Minimal service-account dict — never used for a real google-auth call.

    Every Vertex test below pre-seeds the deployment's ``GcpOauth`` token cache
    (``_seed_gcp_token``) so ``apply_async`` takes the fast-path cache read and
    ``_build_credentials`` / the google-auth refresh never runs. The dict only
    has to satisfy ``GcpOauth.__init__``'s "non-empty, not external_account"
    shape check.
    """
    return {
        "type": "service_account",
        "project_id": "my-test-project",
        "private_key_id": "k",
        "private_key": "-----BEGIN PRIVATE KEY-----\nX\n-----END PRIVATE KEY-----",
        "client_email": "sa@my-test-project.iam.gserviceaccount.com",
        "client_id": "i",
        "token_uri": "https://oauth2.googleapis.com/token",
    }


def _seed_gcp_token(dep, token: str = "faketoken") -> None:
    """Pre-seed the deployment's GcpOauth cache with a known, non-expired token.

    This is the token-faking seam: `apply_async` calls `_ensure_token()`, whose
    fast-path returns the cached token WITHOUT acquiring the refresh lock or
    calling google-auth when the cache is populated and unexpired. `expiry` is
    now + 3600s so `is_expired()` (60s lead window) reports False. The header
    installed on the wire is therefore `Bearer <token>` with zero real GCP IO.
    """
    dep.auth._cached_token = CachedToken(
        token=SecretStr(token),
        expiry_epoch=time.time() + 3600.0,
    )


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


# ---------------------------------------------------------------------------
# Vertex-Claude / Vertex-Gemini wire round-trips (#1717 AC #1, #2, #3)
#
# These are the HEADLINE acceptance criteria: they prove the FULL send-path
# for the platform-hosted providers reaches the socket with the right verb,
# the right transformed body, and the GcpOauth bearer header installed. The
# token is faked by pre-seeding the deployment's GcpOauth cache
# (`_seed_gcp_token`) so no real google-auth call fires.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@respx.mock
async def test_complete_vertex_claude_wire_rawpredict_bearer_stripped_body() -> None:
    """AC #1 (headline): Vertex-Claude complete() reaches the wire correctly.

    Constructs the deployment via the PUBLIC `vertex_claude_preset(...)` path
    with a fake SA dict + a pre-seeded GcpOauth token, then intercepts the
    outbound request and pins the on-wire verb, body transform, and auth header.
    """
    dep = vertex_claude_preset(
        _fake_sa(),
        "my-proj-1234",
        "us-central1",
        "claude-opus-4-8",
    )
    _seed_gcp_token(dep, "faketoken")
    client, http = _client(dep)
    # Build the exact URL respx must match from the deployment itself (the
    # resolved model is `claude-opus-4-8@latest`, so the on-wire path carries
    # the `@latest` suffix — build it rather than hardcode it).
    req = client._build_completion_request(
        [{"role": "user", "content": "hi"}],
        model=None,
        temperature=None,
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
                "content": [{"type": "text", "text": "vertex-ok"}],
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 3, "output_tokens": 2},
                "model": "claude-opus-4-8@latest",
            },
        )
    )
    try:
        result = await client.complete(
            [{"role": "user", "content": "hi"}], http_client=http, max_tokens=32
        )
    finally:
        await http.aclose()

    sent = route.calls.last.request
    sent_url = str(sent.url)
    # (1) Vertex-Claude verb: the URL path ends with the `:rawPredict` verb.
    assert sent_url.endswith(":rawPredict")
    # (2) Anthropic publisher + resolved model live in the URL path (model is
    #     URL-carried on Vertex, resolved to `claude-opus-4-8@latest`).
    assert "/publishers/anthropic/models/claude-opus-4-8" in sent_url
    # (3) Platform-Anthropic body transform reached the socket.
    body = json.loads(sent.content)
    assert body["anthropic_version"] == "vertex-2023-10-16"
    assert "model" not in body
    # (4) GcpOauth bearer header installed on the wire.
    assert sent.headers["authorization"] == "Bearer faketoken"
    # (5) Response parses to the normalized `{text, ...}` shape.
    assert result["text"] == "vertex-ok"
    assert result["stop_reason"] == "end_turn"


@pytest.mark.asyncio
@respx.mock
async def test_complete_vertex_gemini_wire_generatecontent_bearer() -> None:
    """AC #2: Vertex-Gemini complete() reaches the wire with the right verb/body.

    Gemini uses the `VertexGenerateContent` wire (NOT AnthropicMessages), so
    NO anthropic transform runs: the body carries `contents` + `generationConfig`
    and the model is URL-carried, never in the body.
    """
    dep = vertex_gemini_preset(
        _fake_sa(),
        "my-proj-1234",
        "us-central1",
        "gemini-2.0-flash",
    )
    _seed_gcp_token(dep, "faketoken")
    client, http = _client(dep)
    req = client._build_completion_request(
        [{"role": "user", "content": "hi"}],
        model=None,
        temperature=0.5,
        top_p=None,
        max_tokens=48,
        stop=None,
        user=None,
        stream=False,
    )
    _, url = client._build_completion_payload_and_url(req, stream=False)
    route = respx.post(url).mock(
        return_value=httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "content": {"parts": [{"text": "gemini-ok"}]},
                        "finishReason": "STOP",
                    }
                ],
                "usageMetadata": {
                    "promptTokenCount": 4,
                    "candidatesTokenCount": 2,
                },
                "modelVersion": "gemini-2.0-flash",
            },
        )
    )
    try:
        result = await client.complete(
            [{"role": "user", "content": "hi"}],
            http_client=http,
            temperature=0.5,
            max_tokens=48,
        )
    finally:
        await http.aclose()

    sent = route.calls.last.request
    sent_url = str(sent.url)
    assert sent_url.endswith(":generateContent")
    assert "/publishers/google/models/gemini-2.0-flash" in sent_url
    # Gemini body shape: model is URL-carried, body carries contents +
    # generationConfig (no `model` key, no anthropic_version).
    body = json.loads(sent.content)
    assert "model" not in body
    assert "anthropic_version" not in body
    assert body["contents"] == [{"role": "user", "parts": [{"text": "hi"}]}]
    assert body["generationConfig"]["temperature"] == 0.5
    assert body["generationConfig"]["maxOutputTokens"] == 48
    assert sent.headers["authorization"] == "Bearer faketoken"
    assert result["text"] == "gemini-ok"


@pytest.mark.asyncio
@respx.mock
async def test_stream_vertex_claude_uses_streamrawpredict_verb() -> None:
    """AC #3: streaming over Vertex-Claude uses the `:streamRawPredict` verb.

    Drives the REAL `LlmClient.stream(...)` send-path (httpx `client.stream`
    over the SSRF-safe transport) and asserts the intercepted request URL ends
    with the STREAMING verb, distinct from the non-streaming `:rawPredict`.
    """
    dep = vertex_claude_preset(
        _fake_sa(),
        "my-proj-1234",
        "us-central1",
        "claude-opus-4-8",
    )
    _seed_gcp_token(dep, "faketoken")
    client, http = _client(dep)
    req = client._build_completion_request(
        [{"role": "user", "content": "hi"}],
        model=None,
        temperature=None,
        top_p=None,
        max_tokens=32,
        stop=None,
        user=None,
        stream=True,
    )
    _, stream_url = client._build_completion_payload_and_url(req, stream=True)
    # Builder-level guard: the streaming route resolves to the STREAM verb.
    assert stream_url.endswith(":streamRawPredict")

    sse = 'data: {"content": [{"type": "text", "text": "hi"}]}\n\n' "data: [DONE]\n\n"
    route = respx.post(stream_url).mock(
        return_value=httpx.Response(
            200, headers={"content-type": "text/event-stream"}, content=sse
        )
    )
    chunks = []
    try:
        async for chunk in client.stream(
            [{"role": "user", "content": "hi"}], http_client=http, max_tokens=32
        ):
            chunks.append(chunk["text"])
    finally:
        await http.aclose()

    sent = route.calls.last.request
    sent_url = str(sent.url)
    # The intercepted wire URL uses the STREAMING verb, not the unary verb.
    assert sent_url.endswith(":streamRawPredict")
    assert not sent_url.endswith(":rawPredict")
    assert sent.headers["authorization"] == "Bearer faketoken"
    assert chunks == ["hi"]

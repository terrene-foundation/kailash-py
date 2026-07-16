# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Per-request `api_key=` BYOK override tests (#1720 Wave-1b).

Covers the `LlmClient.complete()` / `stream()` / `_prepare_auth_headers`
per-request credential override:

* `CompletionRequest` carries NO `api_key` field (cross-SDK byte pre-image
  contract) — the override threads through kwargs into the auth-header step.
* `ApiKeyBearer`-family deployments (Authorization: Bearer / X-Api-Key /
  X-Goog-Api-Key) install the override via the SAME header mechanism the
  deployment's static credential uses.
* Deployments whose auth strategy is NOT `ApiKeyBearer` (AwsBearerToken,
  GcpOauth, ...) raise `UnsupportedApiKeyOverride` — fail-closed, never a
  silent fallback to the deployment's own credential.
* The raw key is NEVER logged, at any log level.
* `complete()` / `stream()` (both the real streaming send AND the
  `streaming.enabled=False` buffered fallback) forward `api_key` unchanged.
* Byte-neutral: `complete()`/`_prepare_auth_headers()` without `api_key` are
  unaffected by the new kwarg's existence.

All assertions are behavioral (call the function, inspect real headers on
the wire via respx, or call `_prepare_auth_headers` directly) per
`rules/testing.md` — no source-grep.
"""

from __future__ import annotations

import json
import logging

import httpx
import pytest
import respx

from kaizen.llm import LlmClient
from kaizen.llm.auth.aws import AwsBearerToken
from kaizen.llm.auth.bearer import ApiKeyHeaderKind
from kaizen.llm.client import UnsupportedApiKeyOverride
from kaizen.llm.deployment import CompletionRequest, StreamingConfig
from kaizen.llm.http_client import LlmHttpClient, SafeDnsResolver
from kaizen.llm.presets import (
    anthropic_preset,
    bedrock_claude_preset,
    google_preset,
    openai_preset,
    vertex_claude_preset,
)

_BYOK_KEY = "sk-byok-caller-supplied-secret-9f8e7d6c"
_DEPLOYMENT_KEY = "sk-deployment-static-secret-1a2b3c4d"


class _AllowAllResolver(SafeDnsResolver):
    """SafeDnsResolver that skips the real DNS lookup (test-only)."""

    __slots__ = ()

    def check_host(self, host: str) -> None:  # noqa: D401 - test stub resolver
        return None


def _client(dep):
    http = LlmHttpClient(deployment_preset=dep.wire.name, resolver=_AllowAllResolver())
    return LlmClient.from_deployment(dep), http


def _fake_sa() -> dict:
    return {
        "type": "service_account",
        "project_id": "my-test-project",
        "private_key_id": "k",
        "private_key": "-----BEGIN PRIVATE KEY-----\nX\n-----END PRIVATE KEY-----",
        "client_email": "sa@my-test-project.iam.gserviceaccount.com",
        "client_id": "i",
        "token_uri": "https://oauth2.googleapis.com/token",
    }


# ---------------------------------------------------------------------------
# CompletionRequest carries no api_key field
# ---------------------------------------------------------------------------


def test_completion_request_has_no_api_key_field() -> None:
    assert "api_key" not in CompletionRequest.model_fields


def test_completion_request_rejects_api_key_kwarg() -> None:
    with pytest.raises(Exception):
        CompletionRequest(
            model="gpt-4o",
            messages=[{"role": "user", "content": "hi"}],
            api_key=_BYOK_KEY,  # type: ignore[call-arg]
        )


# ---------------------------------------------------------------------------
# _prepare_auth_headers — ApiKeyBearer-family override installs correctly
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_prepare_auth_headers_overrides_openai_bearer() -> None:
    dep = openai_preset(_DEPLOYMENT_KEY, "gpt-4o")
    client, http = _client(dep)
    try:
        headers, auth_kind = await client._prepare_auth_headers(
            "https://api.openai.com/v1/chat/completions",
            b"{}",
            stream=False,
            api_key=_BYOK_KEY,
        )
    finally:
        await http.aclose()
    assert headers["Authorization"] == f"Bearer {_BYOK_KEY}"
    assert _DEPLOYMENT_KEY not in headers["Authorization"]
    assert auth_kind == "api_key"


@pytest.mark.asyncio
async def test_prepare_auth_headers_overrides_anthropic_x_api_key() -> None:
    dep = anthropic_preset(_DEPLOYMENT_KEY, "claude-3-5-sonnet-20241022")
    client, http = _client(dep)
    try:
        headers, _ = await client._prepare_auth_headers(
            "https://api.anthropic.com/v1/messages",
            b"{}",
            stream=False,
            api_key=_BYOK_KEY,
        )
    finally:
        await http.aclose()
    assert headers["X-Api-Key"] == _BYOK_KEY
    assert headers.get("Authorization") is None
    # required_headers (anthropic-version) still merge in alongside the
    # override — the override only touches the credential header.
    assert headers["anthropic-version"] == "2023-06-01"


@pytest.mark.asyncio
async def test_prepare_auth_headers_overrides_google_x_goog_api_key() -> None:
    dep = google_preset(_DEPLOYMENT_KEY, "gemini-2.0-flash")
    client, http = _client(dep)
    try:
        headers, _ = await client._prepare_auth_headers(
            "https://generativelanguage.googleapis.com/v1beta/models/x:generateContent",
            b"{}",
            stream=False,
            api_key=_BYOK_KEY,
        )
    finally:
        await http.aclose()
    assert headers["X-Goog-Api-Key"] == _BYOK_KEY


@pytest.mark.asyncio
async def test_prepare_auth_headers_without_override_uses_deployment_credential() -> (
    None
):
    """Byte-neutral: omitting `api_key` behaves exactly as before this shard."""
    dep = openai_preset(_DEPLOYMENT_KEY, "gpt-4o")
    client, http = _client(dep)
    try:
        headers_default, kind_default = await client._prepare_auth_headers(
            "https://api.openai.com/v1/chat/completions", b"{}", stream=False
        )
        headers_explicit_none, kind_explicit_none = await client._prepare_auth_headers(
            "https://api.openai.com/v1/chat/completions",
            b"{}",
            stream=False,
            api_key=None,
        )
    finally:
        await http.aclose()
    assert headers_default == {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {_DEPLOYMENT_KEY}",
    }
    assert headers_default == headers_explicit_none
    assert kind_default == kind_explicit_none == "api_key"


# ---------------------------------------------------------------------------
# Non-ApiKeyBearer deployments reject the override (fail-closed)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_prepare_auth_headers_rejects_override_for_aws_bearer_token() -> None:
    dep = bedrock_claude_preset(_DEPLOYMENT_KEY, "us-east-1", "claude-sonnet-4-6")
    assert isinstance(dep.auth, AwsBearerToken)
    client, http = _client(dep)
    try:
        with pytest.raises(UnsupportedApiKeyOverride) as exc_info:
            await client._prepare_auth_headers(
                "https://bedrock-runtime.us-east-1.amazonaws.com/model/x/invoke",
                b"{}",
                stream=False,
                api_key=_BYOK_KEY,
            )
    finally:
        await http.aclose()
    assert exc_info.value.auth_strategy_kind == "aws_bearer_token"
    # The raw key must not leak into the exception message either.
    assert _BYOK_KEY not in str(exc_info.value)


@pytest.mark.asyncio
async def test_prepare_auth_headers_rejects_override_for_gcp_oauth_without_refresh(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """UnsupportedApiKeyOverride fires BEFORE the deployment's own auth runs,
    so a rejected BYOK override never triggers a live GCP OAuth refresh for a
    credential that would then be discarded.

    `GcpOauth` is a `__slots__` class, so the spy is installed at the CLASS
    level (an unbound function assigned to the class is called as a bound
    method for any instance) rather than on `dep.auth` directly.
    """
    dep = vertex_claude_preset(
        _fake_sa(), "my-proj-1234", "us-central1", "claude-3-5-sonnet"
    )
    client, http = _client(dep)

    calls = {"n": 0}

    async def spy(self, request):  # noqa: ANN001 - test spy, mirrors bound method
        calls["n"] += 1
        return request

    monkeypatch.setattr(type(dep.auth), "apply_async", spy)

    try:
        with pytest.raises(UnsupportedApiKeyOverride) as exc_info:
            await client._prepare_auth_headers(
                "https://us-central1-aiplatform.googleapis.com/v1/x:rawPredict",
                b"{}",
                stream=False,
                api_key=_BYOK_KEY,
            )
    finally:
        await http.aclose()
    assert exc_info.value.auth_strategy_kind == "gcp_oauth"
    assert calls["n"] == 0  # never attempted a token refresh


# ---------------------------------------------------------------------------
# Raw key is NEVER logged
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_byok_key_never_appears_in_logs(caplog: pytest.LogCaptureFixture) -> None:
    dep = openai_preset(_DEPLOYMENT_KEY, "gpt-4o")
    client, http = _client(dep)
    caplog.set_level(logging.DEBUG)
    try:
        headers, _ = await client._prepare_auth_headers(
            "https://api.openai.com/v1/chat/completions",
            b"{}",
            stream=False,
            api_key=_BYOK_KEY,
        )
    finally:
        await http.aclose()
    # Sanity: the header really does carry the override (proves the test
    # exercised the live-key path, not a no-op).
    assert _BYOK_KEY in headers["Authorization"]
    for record in caplog.records:
        assert _BYOK_KEY not in record.getMessage()
        assert _BYOK_KEY not in repr(record.args)
        for value in getattr(record, "__dict__", {}).values():
            assert _BYOK_KEY not in repr(value)


@pytest.mark.asyncio
@respx.mock
async def test_byok_key_never_logged_through_full_complete_call(
    caplog: pytest.LogCaptureFixture,
) -> None:
    respx.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "pong"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1},
                "model": "gpt-4o",
            },
        )
    )
    dep = openai_preset(_DEPLOYMENT_KEY, "gpt-4o")
    client, http = _client(dep)
    caplog.set_level(logging.DEBUG)
    try:
        result = await client.complete(
            [{"role": "user", "content": "ping"}],
            http_client=http,
            max_tokens=16,
            api_key=_BYOK_KEY,
        )
    finally:
        await http.aclose()
    assert result["text"] == "pong"
    for record in caplog.records:
        assert _BYOK_KEY not in record.getMessage()
        assert _BYOK_KEY not in repr(record.args)


# ---------------------------------------------------------------------------
# complete() / stream() thread api_key through the full send path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@respx.mock
async def test_complete_installs_byok_override_on_the_wire() -> None:
    route = respx.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "pong"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1},
                "model": "gpt-4o",
            },
        )
    )
    dep = openai_preset(_DEPLOYMENT_KEY, "gpt-4o")
    client, http = _client(dep)
    try:
        result = await client.complete(
            [{"role": "user", "content": "ping"}],
            http_client=http,
            max_tokens=16,
            api_key=_BYOK_KEY,
        )
    finally:
        await http.aclose()
    assert result["text"] == "pong"
    sent = route.calls.last.request
    assert sent.headers["authorization"] == f"Bearer {_BYOK_KEY}"


@pytest.mark.asyncio
@respx.mock
async def test_complete_without_api_key_is_byte_neutral_on_the_wire() -> None:
    """Regression: complete() without `api_key=` still installs the
    deployment's own static credential, unchanged by this shard."""
    route = respx.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "pong"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1},
                "model": "gpt-4o",
            },
        )
    )
    dep = openai_preset(_DEPLOYMENT_KEY, "gpt-4o")
    client, http = _client(dep)
    try:
        await client.complete(
            [{"role": "user", "content": "ping"}], http_client=http, max_tokens=16
        )
    finally:
        await http.aclose()
    sent = route.calls.last.request
    assert sent.headers["authorization"] == f"Bearer {_DEPLOYMENT_KEY}"


@pytest.mark.asyncio
@respx.mock
async def test_stream_installs_byok_override_on_the_real_streaming_send() -> None:
    dep = openai_preset(_DEPLOYMENT_KEY, "gpt-4o")
    client, http = _client(dep)
    sse = 'data: {"choices": [{"delta": {"content": "hi"}}]}\n\n' "data: [DONE]\n\n"
    route = respx.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=httpx.Response(
            200, headers={"content-type": "text/event-stream"}, content=sse
        )
    )
    chunks = []
    try:
        async for chunk in client.stream(
            [{"role": "user", "content": "ping"}],
            http_client=http,
            max_tokens=16,
            api_key=_BYOK_KEY,
        ):
            chunks.append(chunk["text"])
    finally:
        await http.aclose()
    assert chunks == ["hi"]
    sent = route.calls.last.request
    assert sent.headers["authorization"] == f"Bearer {_BYOK_KEY}"


@pytest.mark.asyncio
@respx.mock
async def test_stream_installs_byok_override_on_buffered_fallback() -> None:
    """When `streaming.enabled=False`, `stream()` falls back to a buffered
    `complete()` call — `api_key` MUST still reach the wire on that path."""
    dep = openai_preset(_DEPLOYMENT_KEY, "gpt-4o").model_copy(
        update={"streaming": StreamingConfig(enabled=False)}
    )
    client, http = _client(dep)
    route = respx.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "pong"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1},
                "model": "gpt-4o",
            },
        )
    )
    chunks = []
    try:
        async for chunk in client.stream(
            [{"role": "user", "content": "ping"}],
            http_client=http,
            max_tokens=16,
            api_key=_BYOK_KEY,
        ):
            chunks.append(chunk["text"])
    finally:
        await http.aclose()
    assert chunks == ["pong"]
    sent = route.calls.last.request
    assert sent.headers["authorization"] == f"Bearer {_BYOK_KEY}"


@pytest.mark.asyncio
@respx.mock
async def test_complete_raises_unsupported_override_before_any_http_call() -> None:
    """A deployment whose auth cannot accept a bearer override raises before
    any request is sent — no partial/leaked send."""
    dep = bedrock_claude_preset(_DEPLOYMENT_KEY, "us-east-1", "claude-sonnet-4-6")
    client, http = _client(dep)
    route = respx.post(
        "https://bedrock-runtime.us-east-1.amazonaws.com/model/"
        "us.anthropic.claude-sonnet-4-6-v1%3A0/invoke"
    ).mock(return_value=httpx.Response(200, json={}))
    try:
        with pytest.raises(UnsupportedApiKeyOverride):
            await client.complete(
                [{"role": "user", "content": "ping"}],
                http_client=http,
                max_tokens=16,
                api_key=_BYOK_KEY,
            )
    finally:
        await http.aclose()
    assert route.call_count == 0


def test_apikeybearer_header_kind_enum_matches_supported_kinds() -> None:
    """Documentation-pin: the three header kinds this shard supports."""
    assert {k.value for k in ApiKeyHeaderKind} == {
        "Authorization_Bearer",
        "X_Api_Key",
        "X_Goog_Api_Key",
    }

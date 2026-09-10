# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""#2215 — ``StreamingConfig.include_usage`` must reach the wire as ``stream_options``.

Before the fix ``include_usage`` was declared (``deployment.py:329``) and read
by NOTHING: ``grep -rn include_usage`` returned exactly ONE hit — its own
declaration — and ``grep -rln stream_options`` returned no matches at all. So
``LlmClient.stream()`` emitted no ``stream_options`` and an OpenAI-wire provider
returned NO ``usage`` block on a streamed response, with no supported way to ask
for one: a streamed call was unbillable.

These assert on the CONSTRUCTED REQUEST PAYLOAD rather than a live call, which
pins the exact field deterministically and needs no credential.

BOTH POLES are asserted for every axis, because a test that only checks the
field is PRESENT cannot distinguish this fix from one that hardcodes
``stream_options`` always-on — which would be a behaviour change nobody asked
for, and would 400 on a non-streaming request:

* ``include_usage=True``  + streaming     -> present
* ``include_usage=False`` + streaming     -> ABSENT
* ``include_usage=True``  + NON-streaming -> ABSENT
* non-OpenAI wire (Google) + streaming    -> ABSENT (not an OpenAI field)
"""

from __future__ import annotations

from kaizen.llm import LlmClient
from kaizen.llm.deployment import CompletionRequest, StreamingConfig
from kaizen.llm.presets import google_preset, openai_preset
from kaizen.llm.wire_protocols import openai_chat


def _req(*, stream: bool) -> CompletionRequest:
    return CompletionRequest(
        model="test-model",
        messages=[{"role": "user", "content": "hi"}],
        stream=stream,
    )


# ---------------------------------------------------------------------------
# Shaper level — the two halves of the guard, independently.
# ---------------------------------------------------------------------------


def test_shaper_emits_stream_options_when_streaming_and_include_usage():
    payload = openai_chat.build_request_payload(_req(stream=True), include_usage=True)
    assert payload["stream"] is True
    assert payload["stream_options"] == {"include_usage": True}


def test_shaper_omits_stream_options_when_include_usage_false():
    """Opposite pole: the caller opted OUT, so nothing is emitted."""
    payload = openai_chat.build_request_payload(_req(stream=True), include_usage=False)
    assert payload["stream"] is True
    assert "stream_options" not in payload


def test_shaper_omits_stream_options_on_non_streaming_request():
    """Opposite pole: ``stream_options`` is meaningless off the streaming path.

    OpenAI rejects it on a buffered request, so ``include_usage=True`` alone
    must NOT be sufficient to emit it.
    """
    payload = openai_chat.build_request_payload(_req(stream=False), include_usage=True)
    assert "stream" not in payload
    assert "stream_options" not in payload


def test_shaper_default_is_no_stream_options():
    """An unpassed ``include_usage`` keeps the body byte-identical to pre-#2215."""
    payload = openai_chat.build_request_payload(_req(stream=True))
    assert "stream_options" not in payload


# ---------------------------------------------------------------------------
# Client level — the deployment's StreamingConfig actually reaches the shaper.
# ---------------------------------------------------------------------------


def _openai_client(*, include_usage: bool) -> LlmClient:
    dep = openai_preset(api_key="sk-test-not-a-real-key", model="test-model")
    dep = dep.model_copy(
        update={"streaming": StreamingConfig(enabled=True, include_usage=include_usage)}
    )
    return LlmClient.from_deployment(dep, ungoverned=True)


def test_client_streaming_payload_carries_stream_options_by_default():
    """``StreamingConfig.include_usage`` defaults True, so the default is ON."""
    client = _openai_client(include_usage=True)
    payload, _url = client._build_completion_payload_and_url(
        _req(stream=True), stream=True
    )
    assert payload["stream_options"] == {"include_usage": True}


def test_client_streaming_payload_omits_stream_options_when_opted_out():
    client = _openai_client(include_usage=False)
    payload, _url = client._build_completion_payload_and_url(
        _req(stream=True), stream=True
    )
    assert "stream_options" not in payload


def test_client_buffered_payload_never_carries_stream_options():
    """The buffered ``complete()`` body is unchanged on an include_usage deployment."""
    client = _openai_client(include_usage=True)
    payload, _url = client._build_completion_payload_and_url(
        _req(stream=False), stream=False
    )
    assert "stream_options" not in payload


def test_non_openai_wire_never_emits_stream_options():
    """Wire-scoping pole: ``stream_options`` is an OpenAI-protocol field.

    Emitting it on Gemini's ``generateContent`` body would be an invalid
    request, so the client must gate the kwarg on the OpenAI wire.
    """
    dep = google_preset(api_key="not-a-real-key", model="test-gemini-model")
    assert dep.streaming.include_usage is True  # same config, different wire
    client = LlmClient.from_deployment(dep, ungoverned=True)
    request = CompletionRequest(
        model="test-gemini-model",
        messages=[{"role": "user", "content": "hi"}],
        stream=True,
    )
    payload, _url = client._build_completion_payload_and_url(request, stream=True)
    assert "stream_options" not in payload

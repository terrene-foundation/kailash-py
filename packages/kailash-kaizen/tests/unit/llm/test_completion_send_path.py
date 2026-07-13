# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the four-axis completion send-path (#1717).

Covers the PURE (no-HTTP) surface of `LlmClient.complete()` / `stream()`:

* Per-wire URL building (OpenAI / Anthropic-direct / Google-direct /
  Vertex-Claude / Vertex-Gemini / Bedrock-Claude / Bedrock-invoke).
* The platform-Anthropic body transform (strip `model`, inject
  `anthropic_version`) GATED on `completion_routing`, incl. the
  direct-Anthropic byte-invariant.
* NEW-A per-model temperature floor (claude-opus-4-8 omits temperature=0).
* NEW-B Vertex region us/eu/global host + path-location derivation.
* NEW-C provider-string aliases (vertex-anthropic / vertex-gemini / etc.).
* openai_chat + bedrock_invoke shapers.
* `_parse_stream_line` SSE / JSONL framing.

Wire behaviour (respx round-trips) is exercised by a separate test pass; here
we assert the deterministic shaper / transform / URL / alias logic.
"""

from __future__ import annotations

import pytest

from kaizen.llm import LlmClient
from kaizen.llm.client import _parse_stream_line
from kaizen.llm.deployment import CompletionRequest, WireProtocol
from kaizen.llm.presets import (
    anthropic_preset,
    bedrock_claude_preset,
    bedrock_llama_preset,
    get_preset,
    google_preset,
    openai_preset,
    vertex_claude_preset,
    vertex_gemini_preset,
)
from kaizen.llm.wire_protocols import (
    anthropic_messages,
    bedrock_invoke,
    openai_chat,
)


def _sa() -> dict:
    return {
        "type": "service_account",
        "project_id": "my-test-project",
        "private_key_id": "k",
        "private_key": "-----BEGIN PRIVATE KEY-----\nX\n-----END PRIVATE KEY-----",
        "client_email": "sa@my-test-project.iam.gserviceaccount.com",
        "client_id": "i",
        "token_uri": "https://oauth2.googleapis.com/token",
    }


def _req(
    model: str,
    *,
    temperature=None,
    max_tokens=64,
    stream=False,
    messages=None,
) -> CompletionRequest:
    return CompletionRequest(
        model=model,
        messages=messages or [{"role": "user", "content": "hi"}],
        temperature=temperature,
        max_tokens=max_tokens,
        stream=stream,
    )


def _payload_and_url(dep, req, *, stream=False):
    client = LlmClient.from_deployment(dep)
    return client._build_completion_payload_and_url(req, stream=stream)


# ---------------------------------------------------------------------------
# URL building — per wire
# ---------------------------------------------------------------------------


def test_openai_completion_url_and_body() -> None:
    dep = openai_preset("sk-x", "gpt-4o")
    payload, url = _payload_and_url(dep, _req("gpt-4o"))
    assert url == "https://api.openai.com/v1/chat/completions"
    assert payload["model"] == "gpt-4o"
    assert payload["messages"] == [{"role": "user", "content": "hi"}]


def test_anthropic_direct_url() -> None:
    dep = anthropic_preset("sk-ant", "claude-3-5-sonnet-20241022")
    _, url = _payload_and_url(dep, _req("claude-3-5-sonnet-20241022"))
    assert url == "https://api.anthropic.com/v1/messages"


def test_google_direct_url_carries_model_and_verb() -> None:
    dep = google_preset("k", "gemini-2.0-flash")
    _, url = _payload_and_url(dep, _req("gemini-2.0-flash"))
    assert url == (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        "gemini-2.0-flash:generateContent"
    )
    _, surl = _payload_and_url(dep, _req("gemini-2.0-flash", stream=True), stream=True)
    assert surl.endswith(":streamGenerateContent")


def test_vertex_claude_url_appends_rawpredict_verb() -> None:
    dep = vertex_claude_preset(
        _sa(), "my-proj-1234", "us-central1", "claude-3-5-sonnet"
    )
    _, url = _payload_and_url(dep, _req(dep.default_model))
    assert url.endswith(":rawPredict")
    assert "/publishers/anthropic/models/" in url
    _, surl = _payload_and_url(dep, _req(dep.default_model, stream=True), stream=True)
    assert surl.endswith(":streamRawPredict")


def test_vertex_gemini_url_appends_generatecontent_verb() -> None:
    dep = vertex_gemini_preset(_sa(), "my-proj-1234", "us-central1", "gemini-2.0-flash")
    _, url = _payload_and_url(dep, _req(dep.default_model))
    assert url.endswith(":generateContent")
    assert "/publishers/google/models/" in url


def test_bedrock_claude_url_forms_model_invoke_path() -> None:
    dep = bedrock_claude_preset("tok", "us-east-1", "claude-sonnet-4-6")
    _, url = _payload_and_url(dep, _req(dep.default_model))
    assert url.startswith("https://bedrock-runtime.us-east-1.amazonaws.com/model/")
    assert url.endswith("/invoke")
    _, surl = _payload_and_url(dep, _req(dep.default_model, stream=True), stream=True)
    assert surl.endswith("/invoke-with-response-stream")


def test_bedrock_llama_invoke_url_and_native_body() -> None:
    dep = bedrock_llama_preset("tok", "us-east-1", "llama-3.1-8b")
    payload, url = _payload_and_url(dep, _req(dep.default_model))
    assert url.endswith("/invoke")
    # Llama native body shape (prompt + max_gen_len), NOT anthropic messages.
    assert "prompt" in payload and "max_gen_len" in payload
    assert "messages" not in payload


# ---------------------------------------------------------------------------
# Platform-Anthropic body transform
# ---------------------------------------------------------------------------


def test_anthropic_direct_body_keeps_model_no_version() -> None:
    dep = anthropic_preset("sk-ant", "claude-3-5-sonnet-20241022")
    payload, _ = _payload_and_url(
        dep, _req("claude-3-5-sonnet-20241022", temperature=0.7)
    )
    assert payload["model"] == "claude-3-5-sonnet-20241022"
    assert "anthropic_version" not in payload


def test_direct_anthropic_body_byte_invariant() -> None:
    """The completion path must not alter direct-Anthropic body vs the raw shaper."""
    dep = anthropic_preset("sk-ant", "claude-3-5-sonnet-20241022")
    req = _req("claude-3-5-sonnet-20241022", temperature=0.7, max_tokens=128)
    via_path, _ = _payload_and_url(dep, req)
    raw = anthropic_messages.build_request_payload(req)
    assert via_path == raw


def test_vertex_claude_body_strips_model_injects_version() -> None:
    dep = vertex_claude_preset(
        _sa(), "my-proj-1234", "us-central1", "claude-3-5-sonnet"
    )
    payload, _ = _payload_and_url(dep, _req(dep.default_model, temperature=0.4))
    assert "model" not in payload
    assert payload["anthropic_version"] == "vertex-2023-10-16"


def test_bedrock_claude_body_strips_model_injects_version() -> None:
    dep = bedrock_claude_preset("tok", "us-east-1", "claude-sonnet-4-6")
    payload, _ = _payload_and_url(dep, _req(dep.default_model, temperature=0.4))
    assert "model" not in payload
    assert payload["anthropic_version"] == "bedrock-2023-05-31"


# ---------------------------------------------------------------------------
# NEW-A — per-model temperature floor
# ---------------------------------------------------------------------------


def test_opus_4_8_omits_temperature_zero() -> None:
    payload = anthropic_messages.build_request_payload(
        _req("claude-opus-4-8", temperature=0.0)
    )
    assert "temperature" not in payload


def test_opus_4_8_versioned_id_also_omits_temperature_zero() -> None:
    payload = anthropic_messages.build_request_payload(
        _req("claude-opus-4-8@latest", temperature=0.0)
    )
    assert "temperature" not in payload


def test_opus_4_8_keeps_temperature_at_or_above_floor() -> None:
    payload = anthropic_messages.build_request_payload(
        _req("claude-opus-4-8", temperature=1.0)
    )
    assert payload["temperature"] == 1.0


def test_non_opus_model_keeps_temperature_zero() -> None:
    payload = anthropic_messages.build_request_payload(
        _req("claude-3-5-sonnet-20241022", temperature=0.0)
    )
    assert payload["temperature"] == 0.0


# ---------------------------------------------------------------------------
# NEW-B — Vertex region us / eu / global
# ---------------------------------------------------------------------------


def test_vertex_global_region_uses_regionless_host() -> None:
    dep = vertex_gemini_preset(_sa(), "my-proj-1234", "global", "gemini-2.0-flash")
    assert str(dep.endpoint.base_url).startswith("https://aiplatform.googleapis.com")
    assert "/locations/global/" in dep.endpoint.path_prefix


def test_vertex_eu_region_passes_through_with_concrete_host() -> None:
    dep = vertex_gemini_preset(_sa(), "my-proj-1234", "eu", "gemini-2.0-flash")
    # eu → concrete host europe-west3 (NOT europe-west1), location stays `eu`.
    assert "europe-west3-aiplatform" in str(dep.endpoint.base_url)
    assert "europe-west1" not in str(dep.endpoint.base_url)
    assert "/locations/eu/" in dep.endpoint.path_prefix


def test_vertex_us_region_passes_through_with_concrete_host() -> None:
    dep = vertex_gemini_preset(_sa(), "my-proj-1234", "us", "gemini-2.0-flash")
    assert "us-central1-aiplatform" in str(dep.endpoint.base_url)
    assert "/locations/us/" in dep.endpoint.path_prefix


def test_vertex_concrete_region_unchanged() -> None:
    dep = vertex_gemini_preset(
        _sa(), "my-proj-1234", "europe-west4", "gemini-2.0-flash"
    )
    assert "europe-west4-aiplatform" in str(dep.endpoint.base_url)
    assert "/locations/europe-west4/" in dep.endpoint.path_prefix


def test_vertex_bogus_region_rejected() -> None:
    with pytest.raises(ValueError):
        vertex_gemini_preset(_sa(), "my-proj-1234", "not a region", "gemini-2.0-flash")


# ---------------------------------------------------------------------------
# NEW-C — provider-string aliases
# ---------------------------------------------------------------------------


def test_vertex_anthropic_alias_resolves_to_vertex_claude() -> None:
    assert get_preset("vertex-anthropic") is get_preset("vertex_claude")


def test_vertex_gemini_and_google_aliases_resolve() -> None:
    assert get_preset("vertex-gemini") is get_preset("vertex_gemini")
    assert get_preset("vertex-google") is get_preset("vertex_gemini")


def test_unknown_alias_still_raises() -> None:
    with pytest.raises(ValueError):
        get_preset("vertex-nonsense")


# ---------------------------------------------------------------------------
# openai_chat + bedrock_invoke shapers
# ---------------------------------------------------------------------------


def test_openai_chat_shaper_optional_fields_omitted() -> None:
    payload = openai_chat.build_request_payload(_req("gpt-4o", temperature=None))
    assert payload == {
        "model": "gpt-4o",
        "messages": [{"role": "user", "content": "hi"}],
        "max_tokens": 64,
    }


def test_openai_chat_parse_response_message_and_delta() -> None:
    non_stream = {
        "choices": [{"message": {"content": "hello"}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 3, "completion_tokens": 1, "total_tokens": 4},
        "model": "gpt-4o",
    }
    parsed = openai_chat.parse_response(non_stream)
    assert parsed["text"] == "hello"
    assert parsed["stop_reason"] == "stop"
    assert parsed["usage"]["input_tokens"] == 3
    delta = {"choices": [{"delta": {"content": "he"}}]}
    assert openai_chat.parse_response(delta)["text"] == "he"


def test_bedrock_invoke_titan_body_and_parse() -> None:
    payload = bedrock_invoke.build_request_payload(
        _req("amazon.titan-text-express-v1", temperature=0.5)
    )
    assert "inputText" in payload
    assert payload["textGenerationConfig"]["temperature"] == 0.5
    parsed = bedrock_invoke.parse_response(
        {"results": [{"outputText": "yo", "completionReason": "FINISH"}]}
    )
    assert parsed["text"] == "yo"
    assert parsed["stop_reason"] == "FINISH"


def test_bedrock_invoke_unknown_family_raises() -> None:
    with pytest.raises(ValueError):
        bedrock_invoke.build_request_payload(_req("acme.unknown-model"))


# ---------------------------------------------------------------------------
# _parse_stream_line — SSE / JSONL framing
# ---------------------------------------------------------------------------


def test_parse_stream_line_sse_data_prefix() -> None:
    chunk = _parse_stream_line(
        'data: {"choices": [{"delta": {"content": "hi"}}]}', openai_chat
    )
    assert chunk is not None and chunk["text"] == "hi"


def test_parse_stream_line_skips_done_and_blanks() -> None:
    assert _parse_stream_line("data: [DONE]", openai_chat) is None
    assert _parse_stream_line("", openai_chat) is None
    assert _parse_stream_line("   ", openai_chat) is None
    assert _parse_stream_line(": keep-alive comment", openai_chat) is None


def test_parse_stream_line_bare_jsonl_for_ollama_shape() -> None:
    from kaizen.llm.wire_protocols import ollama_native

    chunk = _parse_stream_line(
        '{"message": {"content": "tok"}, "done": false}', ollama_native
    )
    assert chunk is not None and chunk["text"] == "tok"


# ---------------------------------------------------------------------------
# Dispatch coverage + guardrails
# ---------------------------------------------------------------------------


def test_complete_dispatch_covers_every_preset_wire() -> None:
    from kaizen.llm.client import _COMPLETE_DISPATCH

    # Every wire that a preset can emit MUST be routable.
    preset_wires = {
        WireProtocol.OpenAiChat,
        WireProtocol.AnthropicMessages,
        WireProtocol.GoogleGenerateContent,
        WireProtocol.VertexGenerateContent,
        WireProtocol.BedrockInvoke,
        WireProtocol.CohereGenerate,
        WireProtocol.MistralChat,
        WireProtocol.OllamaNative,
        WireProtocol.HuggingFaceInference,
    }
    assert preset_wires <= set(_COMPLETE_DISPATCH)


@pytest.mark.asyncio
async def test_complete_requires_deployment() -> None:
    with pytest.raises(ValueError):
        await LlmClient().complete([{"role": "user", "content": "hi"}])

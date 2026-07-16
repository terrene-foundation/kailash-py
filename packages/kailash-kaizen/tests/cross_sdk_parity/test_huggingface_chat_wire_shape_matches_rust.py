# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Cross-SDK parity: HuggingFace chat-schema on-wire request shape (#1720 F3).

Per specs/kaizen-llm-deployments.md § Cross-SDK Parity, a fixed HuggingFace
chat deployment MUST produce byte-equivalent on-wire URL + body on both
kailash-py and the Rust SDK (EATP D6: independent implementation, matching
semantics).

This pins the load-bearing HuggingFace chat-schema wire invariants the Rust
adapter's per-preset routing must also enforce once its sibling preset lands:

* the route is the HF router's OpenAI-compatible ``/v1/chat/completions``
  endpoint (model in the BODY, not the URL path — unlike the classic
  ``/models/{model}`` text-generation route);
* the body is the OpenAI chat shape (``model`` + ``messages`` +
  ``tools`` + ``tool_choice``), with the conservative TGI ``tool_choice``
  default of ``"auto"`` (NOT the OpenAI-family ``"required"`` default);
* the classic ``huggingface`` preset is UNCHANGED (byte-neutral): its route
  stays ``/hf-inference/models/{model}`` and its body stays
  ``{inputs, parameters}`` with NO tool surface.

The assertions read the exact payload dict + URL string the send-path
serializes (via ``_build_completion_payload_and_url``), so they ARE the
on-wire shape — no live HF call is made (deterministic pure-function output).

CROSS-SDK STATUS: the Rust SDK does NOT yet expose an HF chat-schema-routing
preset. No Rust reference fixture exists for the HF chat body, so this file
pins the four-axis chat-body byte-vector as the PARITY ANCHOR — the Rust
sibling MUST reproduce these exact bytes when it lands. The Rust sibling is a
PENDING cross-repo issue (rules/cross-sdk-inspection.md Rule 1); this session
does NOT self-file it — the orchestrator surfaces the cross-repo filing for
user authorization.
"""

from __future__ import annotations

from kaizen.llm import LlmClient
from kaizen.llm.presets import huggingface_chat_preset, huggingface_preset

_HF_CHAT_MODEL = "meta-llama/Llama-3.1-8B-Instruct"
_HF_CLASSIC_MODEL = "gpt2"
_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Look up the weather",
            "parameters": {
                "type": "object",
                "properties": {"city": {"type": "string"}},
            },
        },
    }
]


def _chat_request(*, stream: bool):
    dep = huggingface_chat_preset(api_key="hf_test_key", model=_HF_CHAT_MODEL)
    client = LlmClient.from_deployment(dep)
    req = client._build_completion_request(
        [{"role": "user", "content": "weather in Paris?"}],
        model=None,
        temperature=None,
        top_p=None,
        max_tokens=32,
        stop=None,
        user=None,
        stream=stream,
        tools=_TOOLS,
        tool_choice=None,
    )
    return client, req


def test_hf_chat_unary_wire_shape_is_parity_anchor() -> None:
    """PARITY ANCHOR — the exact unary HF chat body + route the Rust sibling
    MUST reproduce byte-for-byte when it lands."""
    client, req = _chat_request(stream=False)
    payload, url = client._build_completion_payload_and_url(req, stream=False)

    # Axis 1 (route): OpenAI-compatible chat endpoint, model NOT in the path.
    assert url == "https://router.huggingface.co/v1/chat/completions"
    assert _HF_CHAT_MODEL not in url

    # Axes 2-4 (body): the four-axis chat-body byte-vector.
    assert payload == {
        "model": _HF_CHAT_MODEL,
        "messages": [{"role": "user", "content": "weather in Paris?"}],
        "max_tokens": 32,
        "tools": _TOOLS,
        "tool_choice": "auto",
    }


def test_hf_chat_streaming_route_and_stream_flag_are_parity_anchor() -> None:
    """PARITY ANCHOR — the streaming HF chat request routes to the same chat
    endpoint and sets the OpenAI ``stream: true`` body flag."""
    client, req = _chat_request(stream=True)
    payload, url = client._build_completion_payload_and_url(req, stream=True)

    assert url == "https://router.huggingface.co/v1/chat/completions"
    assert payload["stream"] is True
    assert payload["tools"] == _TOOLS
    assert payload["tool_choice"] == "auto"


def test_hf_classic_preset_stays_byte_neutral() -> None:
    """The classic ``huggingface`` preset MUST be unchanged by F3: model-in-path
    route + ``{inputs, parameters}`` body with NO tool surface."""
    dep = huggingface_preset(api_key="hf_test_key", model=_HF_CLASSIC_MODEL)
    client = LlmClient.from_deployment(dep)
    req = client._build_completion_request(
        [{"role": "user", "content": "weather in Paris?"}],
        model=None,
        temperature=None,
        top_p=None,
        max_tokens=32,
        stop=None,
        user=None,
        stream=False,
        tools=_TOOLS,
        tool_choice=None,
    )
    payload, url = client._build_completion_payload_and_url(req, stream=False)

    assert url == (
        f"https://router.huggingface.co/hf-inference/models/{_HF_CLASSIC_MODEL}"
    )
    assert set(payload.keys()) <= {"inputs", "parameters"}
    assert "tools" not in payload
    assert "tool_choice" not in payload

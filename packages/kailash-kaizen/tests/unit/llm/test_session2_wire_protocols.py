# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Session 2 (S3) — wire protocol shaper tests.

Covers every shaper introduced in this session:

  * ``anthropic_messages``
  * ``google_generate_content``
  * ``cohere_generate``
  * ``mistral_chat``
  * ``ollama_native``
  * ``huggingface_inference``

One happy-path + one round-trip-through-parser + one negative (wrong-type
input) test per module. Each shaper is a facade on the public
``kaizen.llm.wire_protocols`` package, so each test imports via the package
to satisfy the orphan-detection contract ("test through the facade").
"""

from __future__ import annotations

import pytest

from kaizen.llm.deployment import CompletionRequest
from kaizen.llm.wire_protocols import (
    anthropic_messages,
    cohere_generate,
    google_generate_content,
    huggingface_inference,
    mistral_chat,
    ollama_native,
)


def _sample_request(**overrides) -> CompletionRequest:
    base = dict(
        model="test-model",
        messages=[
            {"role": "system", "content": "be helpful"},
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"},
            {"role": "user", "content": "how are you"},
        ],
        temperature=0.7,
        max_tokens=100,
        stream=False,
    )
    base.update(overrides)
    return CompletionRequest(**base)


# ---------------------------------------------------------------------------
# Anthropic
# ---------------------------------------------------------------------------


def test_anthropic_payload_extracts_system_to_top_level() -> None:
    payload = anthropic_messages.build_request_payload(_sample_request())
    assert payload["system"] == "be helpful"
    assert payload["max_tokens"] == 100
    # System message must NOT appear in the messages array (Anthropic
    # rejects role=system in messages).
    assert all(m.get("role") != "system" for m in payload["messages"])


def test_anthropic_payload_fills_default_max_tokens_when_unset() -> None:
    payload = anthropic_messages.build_request_payload(_sample_request(max_tokens=None))
    assert payload["max_tokens"] == 4096  # _DEFAULT_MAX_TOKENS


def test_anthropic_parse_response_concatenates_text_blocks() -> None:
    raw = {
        "content": [
            {"type": "text", "text": "Hello "},
            {"type": "text", "text": "world"},
        ],
        "usage": {"input_tokens": 10, "output_tokens": 2},
        "stop_reason": "end_turn",
        "model": "claude-3-5-sonnet-20241022",
    }
    parsed = anthropic_messages.parse_response(raw)
    assert parsed["text"] == "Hello world"
    assert parsed["usage"]["input_tokens"] == 10
    assert parsed["stop_reason"] == "end_turn"


def test_anthropic_payload_rejects_non_request_input() -> None:
    with pytest.raises(TypeError):
        anthropic_messages.build_request_payload({"not": "a request"})  # type: ignore[arg-type]


def test_anthropic_parse_rejects_non_dict() -> None:
    with pytest.raises(TypeError):
        anthropic_messages.parse_response("string, not dict")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Google GenerateContent
# ---------------------------------------------------------------------------


def test_google_payload_uses_contents_and_system_instruction() -> None:
    payload = google_generate_content.build_request_payload(_sample_request())
    assert "contents" in payload
    assert payload["systemInstruction"]["parts"][0]["text"] == "be helpful"
    assert payload["generationConfig"]["maxOutputTokens"] == 100
    # Role mapping: assistant -> model; user stays user.
    roles = [turn["role"] for turn in payload["contents"]]
    assert "model" in roles  # assistant turn mapped through


def test_google_parse_response_extracts_first_candidate_text() -> None:
    raw = {
        "candidates": [
            {
                "content": {"parts": [{"text": "hi"}, {"text": " there"}]},
                "finishReason": "STOP",
            }
        ],
        "usageMetadata": {
            "promptTokenCount": 5,
            "candidatesTokenCount": 2,
            "totalTokenCount": 7,
        },
        "modelVersion": "gemini-2.0-flash",
    }
    parsed = google_generate_content.parse_response(raw)
    assert parsed["text"] == "hi there"
    assert parsed["usage"]["input_tokens"] == 5
    assert parsed["stop_reason"] == "STOP"


def test_google_payload_rejects_non_request() -> None:
    with pytest.raises(TypeError):
        google_generate_content.build_request_payload(None)  # type: ignore[arg-type]


def test_google_parse_rejects_non_dict() -> None:
    with pytest.raises(TypeError):
        google_generate_content.parse_response(["list", "not", "dict"])  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Cohere
# ---------------------------------------------------------------------------


def test_cohere_payload_uses_message_and_chat_history() -> None:
    payload = cohere_generate.build_request_payload(_sample_request())
    # Trailing user message becomes the `message` field.
    assert payload["message"] == "how are you"
    # Preamble holds system prompt.
    assert payload["preamble"] == "be helpful"
    # chat_history carries prior turns in uppercase role form.
    assert payload["chat_history"][0]["role"] == "USER"
    assert payload["chat_history"][1]["role"] == "CHATBOT"


def test_cohere_payload_requires_trailing_user_message() -> None:
    req = CompletionRequest(
        model="command-r-plus",
        messages=[{"role": "assistant", "content": "hi"}],
    )
    with pytest.raises(ValueError, match=r"trailing user"):
        cohere_generate.build_request_payload(req)


def test_cohere_parse_response_text_and_usage() -> None:
    raw = {
        "text": "ok",
        "meta": {"billed_units": {"input_tokens": 3, "output_tokens": 1}},
        "finish_reason": "COMPLETE",
        "model": "command-r-plus",
    }
    parsed = cohere_generate.parse_response(raw)
    assert parsed["text"] == "ok"
    assert parsed["usage"]["input_tokens"] == 3
    assert parsed["stop_reason"] == "COMPLETE"


def test_cohere_payload_rejects_non_request() -> None:
    with pytest.raises(TypeError):
        cohere_generate.build_request_payload(42)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Mistral
# ---------------------------------------------------------------------------


def test_mistral_payload_matches_openai_chat_shape() -> None:
    payload = mistral_chat.build_request_payload(_sample_request())
    assert payload["model"] == "test-model"
    assert len(payload["messages"]) == 4
    assert payload["temperature"] == 0.7
    assert payload["max_tokens"] == 100


def test_mistral_parse_response_text_and_usage() -> None:
    raw = {
        "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 3, "completion_tokens": 1, "total_tokens": 4},
        "model": "mistral-large-latest",
    }
    parsed = mistral_chat.parse_response(raw)
    assert parsed["text"] == "ok"
    assert parsed["usage"]["total_tokens"] == 4
    assert parsed["stop_reason"] == "stop"


def test_mistral_payload_rejects_non_request() -> None:
    with pytest.raises(TypeError):
        mistral_chat.build_request_payload("not a request")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Ollama
# ---------------------------------------------------------------------------


def test_ollama_payload_maps_max_tokens_to_num_predict() -> None:
    payload = ollama_native.build_request_payload(_sample_request())
    assert payload["model"] == "test-model"
    assert payload["options"]["num_predict"] == 100
    assert payload["options"]["temperature"] == 0.7
    assert payload["stream"] is False


def test_ollama_parse_response_reads_message_content() -> None:
    raw = {
        "message": {"role": "assistant", "content": "hi there"},
        "done": True,
        "done_reason": "stop",
        "eval_count": 3,
        "prompt_eval_count": 5,
        "model": "llama3.1:8b",
    }
    parsed = ollama_native.parse_response(raw)
    assert parsed["text"] == "hi there"
    assert parsed["usage"]["input_tokens"] == 5
    assert parsed["usage"]["output_tokens"] == 3
    assert parsed["done"] is True


def test_ollama_payload_rejects_non_request() -> None:
    with pytest.raises(TypeError):
        ollama_native.build_request_payload(None)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# HuggingFace Inference
# ---------------------------------------------------------------------------


def test_huggingface_classic_payload_flattens_messages_to_prompt() -> None:
    payload = huggingface_inference.build_request_payload(_sample_request())
    # Classic shape: {inputs: ..., parameters: ...} — no `messages` key.
    assert "inputs" in payload
    assert "messages" not in payload
    assert payload["parameters"]["max_new_tokens"] == 100


def test_huggingface_chat_schema_uses_openai_shape() -> None:
    payload = huggingface_inference.build_request_payload(
        _sample_request(), use_chat_schema=True
    )
    assert "messages" in payload
    assert payload["model"] == "test-model"
    assert payload["max_tokens"] == 100


def test_huggingface_parse_response_list_form() -> None:
    raw = [{"generated_text": "hello"}, {"generated_text": " world"}]
    parsed = huggingface_inference.parse_response(raw)
    assert parsed["text"] == "hello world"


def test_huggingface_parse_response_chat_form() -> None:
    raw = {
        "choices": [{"message": {"content": "chat response"}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 3, "total_tokens": 13},
        "model": "tgi-router",
    }
    parsed = huggingface_inference.parse_response(raw)
    assert parsed["text"] == "chat response"
    assert parsed["stop_reason"] == "stop"


def test_huggingface_parse_response_rejects_unknown_shape() -> None:
    with pytest.raises(ValueError):
        huggingface_inference.parse_response({"unexpected": "shape"})


def test_huggingface_payload_rejects_non_request() -> None:
    with pytest.raises(TypeError):
        huggingface_inference.build_request_payload(object())  # type: ignore[arg-type]

# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Wire protocol shapers for every supported LLM deployment (#498 Session 2).

A "wire protocol" is the on-the-wire request/response schema a provider
speaks. Each module in this package owns exactly one provider family's wire
shape:

  * ``anthropic_messages`` — Anthropic ``/v1/messages`` (AnthropicMessages)
  * ``google_generate_content`` — Google Gemini ``/v1beta/models/{model}:generateContent``
  * ``cohere_generate`` — Cohere ``/v1/chat``
  * ``mistral_chat`` — Mistral ``/v1/chat/completions``
  * ``ollama_native`` — Ollama ``/api/chat``
  * ``huggingface_inference`` — HuggingFace Inference API ``/models/{model}``

Every shaper exposes the same two functions:

  * ``build_request_payload(request: CompletionRequest) -> dict`` — produce the
    provider-specific request body.
  * ``parse_response(payload: dict) -> dict`` — extract a normalized
    ``{"text", "usage"}`` view from a provider response.

Both functions are pure (no I/O). The actual HTTP sender lives in
``LlmHttpClient`` (Session 3 / S4c); these shapers are consumed by the
client's serialize / deserialize hooks.

Cross-SDK parity: every function's output for a fixed input is
byte-identical to its Rust counterpart (see
``tests/cross_sdk_parity/test_wire_payload_matches_rust.py`` in Session 9).
"""

from __future__ import annotations

from kaizen.llm.wire_protocols import (
    anthropic_messages,
    cohere_generate,
    google_generate_content,
    huggingface_inference,
    mistral_chat,
    ollama_native,
)

__all__ = [
    "anthropic_messages",
    "cohere_generate",
    "google_generate_content",
    "huggingface_inference",
    "mistral_chat",
    "ollama_native",
]

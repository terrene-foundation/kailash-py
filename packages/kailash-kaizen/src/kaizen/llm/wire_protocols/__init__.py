# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Wire protocol shapers for every supported LLM deployment (#498 Session 2, #462).

A "wire protocol" is the on-the-wire request/response schema a provider
speaks. Each module in this package owns exactly one provider family's wire
shape:

  * ``anthropic_messages`` — Anthropic ``/v1/messages`` (AnthropicMessages)
  * ``google_generate_content`` — Google Gemini ``/v1beta/models/{model}:generateContent``
  * ``cohere_generate`` — Cohere ``/v1/chat``
  * ``mistral_chat`` — Mistral ``/v1/chat/completions``
  * ``ollama_native`` — Ollama ``/api/chat``
  * ``huggingface_inference`` — HuggingFace Inference API ``/models/{model}``

Chat shapers expose:

  * ``build_request_payload(request: CompletionRequest) -> dict``
  * ``parse_response(payload: dict) -> dict``

Embedding shapers (introduced in #462) expose:

  * ``openai_embeddings`` — OpenAI ``/v1/embeddings`` (POST)
  * ``ollama_embeddings`` — Ollama ``/api/embed`` (POST)

with signatures:

  * ``build_request_payload(texts: list[str], model: str, options: EmbedOptions | None) -> dict``
  * ``parse_response(payload: dict) -> {"vectors", "model", "usage"}``

All functions are pure (no I/O). The actual HTTP sender lives in
``LlmHttpClient``; these shapers are consumed by ``LlmClient.embed()``
and (future) ``LlmClient.complete()``.

Cross-SDK parity: every function's output for a fixed input is
byte-identical to its Rust counterpart.
"""

from __future__ import annotations

from kaizen.llm.wire_protocols import (
    anthropic_messages,
    cohere_generate,
    google_generate_content,
    huggingface_inference,
    mistral_chat,
    ollama_embeddings,
    ollama_native,
    openai_embeddings,
)

__all__ = [
    "anthropic_messages",
    "cohere_generate",
    "google_generate_content",
    "huggingface_inference",
    "mistral_chat",
    "ollama_embeddings",
    "ollama_native",
    "openai_embeddings",
]

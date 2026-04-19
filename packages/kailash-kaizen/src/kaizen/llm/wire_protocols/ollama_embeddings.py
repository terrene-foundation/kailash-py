# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Ollama Embeddings wire protocol shaper (#462).

Shapes the on-the-wire request/response for Ollama's ``POST /api/embed``
endpoint (the newer multi-text variant; the legacy ``/api/embeddings``
accepted only a single ``prompt`` string and is deprecated upstream).

Request schema:

    POST /api/embed
    {
      "model":   "nomic-embed-text",
      "input":   ["text a", "text b"] | "text a",   # list OR single str
      "options": {...}                              # optional, not used here
    }

Response schema:

    {
      "model": "nomic-embed-text",
      "embeddings": [[0.1, ...], [0.2, ...]],
      "total_duration": ...,
      "load_duration": ...,
      "prompt_eval_count": ...
    }

Always sends ``input`` as a list even for single-text calls — the newer
Ollama server accepts both but the list form is the forward-compatible
path, and it lets the caller treat the response uniformly.

Ollama has no authentication (``StaticNone`` strategy) and no per-request
``dimensions`` knob (the model's dimension is fixed at training time);
``EmbedOptions.dimensions`` is silently ignored for this wire so callers
don't get an opaque 400 — this is the documented Ollama contract, not
a Kaizen invention.

Cross-SDK parity: this shaper's output for a fixed input is byte-identical
to the kailash-rs Ollama embeddings payload builder (#393).
"""

from __future__ import annotations

from typing import Any, Dict, List

from kaizen.llm.deployment import EmbedOptions
from kaizen.llm.errors import InvalidResponse


def build_request_payload(
    texts: List[str],
    model: str,
    options: EmbedOptions | None = None,
) -> Dict[str, Any]:
    """Build the ``/api/embed`` request body for Ollama.

    * Rejects ``texts=[]`` with ``ValueError`` at the shaper boundary.
    * Rejects non-string elements in ``texts``.
    * ``EmbedOptions.dimensions`` is accepted (for API symmetry with
      OpenAI) but NOT sent to Ollama — Ollama's embedding dimension is
      fixed at the model level. Callers who must bound dimension should
      pick a smaller model.
    """
    if not isinstance(texts, list):
        raise TypeError(
            f"build_request_payload expects texts: list[str]; got {type(texts).__name__}"
        )
    if not texts:
        raise ValueError(
            "build_request_payload requires at least one text; got empty list"
        )
    for idx, t in enumerate(texts):
        if not isinstance(t, str):
            raise TypeError(
                f"texts[{idx}] must be str; got {type(t).__name__}"
            )
    if not isinstance(model, str) or not model:
        raise ValueError(
            "build_request_payload requires a non-empty model string — "
            "read from os.environ['OLLAMA_EMBEDDING_MODEL'] per rules/env-models.md"
        )

    if options is not None and not isinstance(options, EmbedOptions):
        raise TypeError(
            f"options must be EmbedOptions; got {type(options).__name__}"
        )

    payload: Dict[str, Any] = {
        "model": model,
        # Always send the list form — forward-compatible with every
        # Ollama version that supports /api/embed.
        "input": list(texts),
    }
    return payload


def parse_response(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Extract ``{vectors, model, usage}`` from an Ollama embeddings response.

    Raises ``InvalidResponse`` with a stable ``reason`` when the payload
    shape violates the documented contract.
    """
    if not isinstance(payload, dict):
        raise TypeError(
            f"parse_response expects a dict payload; got {type(payload).__name__}"
        )
    embeddings = payload.get("embeddings")
    if not isinstance(embeddings, list):
        raise InvalidResponse(
            "ollama_embeddings: missing or non-list 'embeddings'"
        )
    vectors: List[List[float]] = []
    for item in embeddings:
        if not isinstance(item, list):
            raise InvalidResponse(
                "ollama_embeddings: 'embeddings' entry is not a list"
            )
        for v in item:
            if not isinstance(v, (int, float)) or isinstance(v, bool):
                raise InvalidResponse(
                    "ollama_embeddings: vector contains non-numeric value"
                )
        vectors.append([float(v) for v in item])
    return {
        "vectors": vectors,
        "model": payload.get("model"),
        "usage": {
            "input_tokens": payload.get("prompt_eval_count"),
            "total_tokens": payload.get("prompt_eval_count"),
        },
    }


__all__ = ["build_request_payload", "parse_response"]

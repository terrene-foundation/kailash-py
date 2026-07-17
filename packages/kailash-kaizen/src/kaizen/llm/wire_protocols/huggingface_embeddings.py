# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""HuggingFace Embeddings wire protocol shaper (#1720 Wave-1b EMBED-REMAINDER).

Shapes the on-the-wire request/response for HuggingFace's feature-extraction
Inference endpoint, ``POST /models/{model}`` -- the SAME URL shape
``huggingface_inference.py``'s classic text-generation schema uses (the
model is in the URL path, NOT the body); the request/response CONTENT
differs because the task is embeddings, not generation.

Request schema (HF feature-extraction batch form):

    POST /models/{model}
    {"inputs": ["text a", "text b"]}

Always sends ``inputs`` as a list, even for a single-text call -- mirrors
``ollama_embeddings.py``'s "always send the list form" precedent for
forward-compatible, uniformly-shaped caller code.

Response schema (feature-extraction; the shape varies by whether the
hosted model has a built-in pooling layer):

* **Pooled models** (most sentence-embedding models) return one vector per
  input text directly: ``[[0.1, ...], [0.2, ...]]`` (batch x hidden_dim).
* **Unpooled models** (raw transformer output, no pooling head) return
  per-token vectors: ``[[[0.1, ...], [0.2, ...], ...], ...]`` (batch x
  tokens x hidden_dim) -- ``parse_response`` UNWRAPS this by mean-pooling
  across the token axis into a single sentence vector per input text, so
  callers get a uniform ``list[list[float]]`` regardless of which shape the
  hosted model emits.

Unit-normalization (``EmbedOptions.normalize``) is NOT applied here. As of
#1720 Wave-B1b it is applied UNIFORMLY, client-side, for EVERY embed wire by
``LlmClient.embed`` (a single L2-norm implementation, ``_l2_normalize_vector``)
rather than per-shaper -- HF's classic serverless feature-extraction endpoint
has no documented request-level ``normalize`` parameter (unlike the newer
Text-Embeddings-Inference ``/embed`` server, which this shaper does NOT
target), so it is done client-side, but at the shared dispatch layer rather
than in this shaper (the former HuggingFace-only copy was removed so there is
ONE normalize implementation and no double-normalize). ``parse_response`` here
accepts ``options`` only for dispatch-signature symmetry with every other
embed shaper and validates its type; it does NOT consume ``normalize``.

Cross-SDK parity: this shaper's output for a fixed input is intended to be
byte-identical to the kailash-rs HuggingFace embeddings payload builder.
Per `rules/cross-sdk-inspection.md` Rule 4, at least one deterministic
byte-shape pin test is committed in the Tier-1 suite
(``tests/unit/llm/test_embed_remainder_shapers.py``); full sibling-SDK
byte-vector pinning against the Rust SDK's ACTUAL output is NOT landed as
of this shard -- flagged as a follow-up cross-SDK lockstep item.
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
    """Build the HuggingFace feature-extraction request body.

    Mirrors ``openai_embeddings.build_request_payload``'s rejection
    contract exactly:

    * Rejects ``texts=[]`` with ``ValueError`` at the shaper boundary.
    * Rejects non-string elements in ``texts``.

    ``model`` is validated (non-empty) but NOT written into the body --
    HuggingFace's classic Inference API carries the model in the URL path
    (``/models/{model}``), not the request JSON, matching
    ``huggingface_inference.py``'s existing text-generation schema.
    ``options`` is accepted for API symmetry with every other embedding
    shaper but this endpoint has no request-level knob any current
    ``EmbedOptions`` field maps to (``dimensions``/``user`` are OpenAI-only
    concepts here; ``input_type`` is Cohere-only; ``normalize`` is applied
    UNIFORMLY client-side in ``LlmClient.embed``, not requested from the
    server) -- so ``options`` is validated-and-ignored, not silently
    mis-typed through.
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
            raise TypeError(f"texts[{idx}] must be str; got {type(t).__name__}")
    if not isinstance(model, str) or not model:
        raise ValueError(
            "build_request_payload requires a non-empty model string — "
            "read from os.environ['HUGGINGFACE_EMBEDDING_MODEL'] per "
            "rules/env-models.md"
        )
    if options is not None and not isinstance(options, EmbedOptions):
        raise TypeError(f"options must be EmbedOptions; got {type(options).__name__}")

    return {"inputs": list(texts)}


def _validate_numeric_row(row: List[Any], vector_index: int) -> List[float]:
    """Validate a flat list of numbers, rejecting bool (a subclass of int)."""
    if not row:
        raise InvalidResponse(
            f"huggingface_embeddings: vectors[{vector_index}] is empty"
        )
    for v in row:
        if not isinstance(v, (int, float)) or isinstance(v, bool):
            raise InvalidResponse(
                f"huggingface_embeddings: vectors[{vector_index}] contains "
                "non-numeric value"
            )
    return [float(v) for v in row]


def _unwrap_entry(entry: Any, vector_index: int) -> List[float]:
    """Unwrap one response entry into a single sentence-embedding vector.

    Handles both documented feature-extraction shapes:

    * ``list[float]`` -- already a single pooled vector, used as-is.
    * ``list[list[float]]`` -- per-token vectors (batch x tokens x
      hidden_dim); mean-pooled across the token axis into one vector.
    """
    if not isinstance(entry, list):
        raise InvalidResponse(
            f"huggingface_embeddings: vectors[{vector_index}] is not a list"
        )
    if not entry:
        raise InvalidResponse(
            f"huggingface_embeddings: vectors[{vector_index}] is empty"
        )
    if isinstance(entry[0], list):
        # Unpooled (token-level) response -- mean-pool across tokens.
        token_vectors: List[List[float]] = []
        for tvec in entry:
            if not isinstance(tvec, list):
                raise InvalidResponse(
                    f"huggingface_embeddings: vectors[{vector_index}] has "
                    "inconsistent nesting (mixed token/non-token entries)"
                )
            token_vectors.append(_validate_numeric_row(tvec, vector_index))
        dim = len(token_vectors[0])
        pooled = [0.0] * dim
        for tvec in token_vectors:
            if len(tvec) != dim:
                raise InvalidResponse(
                    f"huggingface_embeddings: vectors[{vector_index}] token "
                    "vectors have mismatched dimensions"
                )
            for i, v in enumerate(tvec):
                pooled[i] += v
        n = len(token_vectors)
        return [x / n for x in pooled]
    return _validate_numeric_row(entry, vector_index)


def parse_response(
    payload: Any,
    options: EmbedOptions | None = None,
) -> Dict[str, Any]:
    """Extract ``{vectors, model, usage}`` from a HuggingFace feature-extraction
    response.

    ``payload`` MUST be a JSON array (one entry per input text) -- the
    classic feature-extraction endpoint returns a bare array, not an
    object, so this shaper (unlike ``cohere_embeddings`` /
    ``openai_embeddings``) type-checks for ``list`` at the top level.
    Raises ``InvalidResponse`` with a stable ``reason`` when the payload
    shape violates the documented contract.

    ``options`` is an OPTIONAL keyword argument accepted ONLY for
    dispatch-signature symmetry with every other embed shaper; its type is
    validated but no field is consumed here. ``EmbedOptions.normalize`` is
    applied UNIFORMLY, client-side, by ``LlmClient.embed`` for EVERY wire
    (#1720 Wave-B1b), NOT in this shaper -- the former HuggingFace-only
    normalize was removed so there is one normalize implementation and no
    double-normalize. Neither ``model`` nor ``usage`` token counts are present
    on this endpoint's response, matching the ``None`` conventions already
    established by ``huggingface_inference.parse_response``'s text-generation
    list-response branch.
    """
    if options is not None and not isinstance(options, EmbedOptions):
        raise TypeError(f"options must be EmbedOptions; got {type(options).__name__}")
    if not isinstance(payload, list):
        raise InvalidResponse(
            "huggingface_embeddings: expected a JSON array of vectors "
            f"(feature-extraction response); got {type(payload).__name__}"
        )

    vectors: List[List[float]] = [
        _unwrap_entry(entry, idx) for idx, entry in enumerate(payload)
    ]

    return {
        "vectors": vectors,
        "model": None,
        # Embed-contract usage shape ({input_tokens, total_tokens}) matches
        # openai_embeddings / ollama_embeddings / cohere_embeddings -- NOT
        # the chat-shaper {input_tokens, output_tokens} shape (embeddings
        # have no "output" token count to bill separately).
        "usage": {"input_tokens": None, "total_tokens": None},
    }


__all__ = ["build_request_payload", "parse_response"]

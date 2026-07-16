# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Cohere Embeddings wire protocol shaper (#1720 Wave-1b EMBED-REMAINDER).

Shapes the on-the-wire request/response for Cohere's ``POST /v1/embed``
endpoint. Consumed by ``LlmClient.embed(...)`` via its Cohere dispatch path
(``WireProtocol.CohereGenerate`` -- Cohere speaks one wire family across both
chat AND embeddings; ``cohere_generate.py`` owns the ``/v1/chat`` shape, this
module owns ``/v1/embed``).

Request schema (Cohere v1 documented contract):

* ``model`` (str)   -- required; e.g. ``"embed-english-v3.0"``.
* ``texts`` (list of str)  -- required; one or more strings to embed. The
  helper rejects empty lists at ``build_request_payload`` time to give a
  typed error at the shaper boundary rather than a 400 from Cohere.
* ``input_type`` (str, optional) -- REQUIRED by Cohere embed v3 models
  (``search_document`` | ``search_query`` | ``classification`` |
  ``clustering``); omitted for legacy (v2 and earlier) models that do not
  accept it. Sourced from ``EmbedOptions.input_type`` -- emitted only when
  the caller sets it, so a v2-model caller who never sets ``input_type``
  gets a payload Cohere's v2 models accept unchanged.
* ``truncate`` is deliberately NOT exposed here: ``EmbedOptions`` carries no
  field for it (only ``dimensions`` / ``user`` / ``input_type`` /
  ``normalize`` are cross-provider-shared today per #1720 Wave-1a) and
  Cohere's server-side default (``END``) is a reasonable behavior for every
  caller who does not opt in. Supporting it would mean growing the shared
  ``EmbedOptions`` shape without a driving cross-SDK use case -- a follow-up
  concern, not this shard's.

Cohere's ``/v1/embed`` endpoint does NOT accept ``dimensions`` (vector size
is fixed per model, unlike OpenAI's ``text-embedding-3-*`` family) or
``user`` (no per-request caller-identifier concept on this endpoint) --
both ``EmbedOptions`` fields are silently NOT emitted for this wire,
matching Ollama's documented-contract-not-Kaizen-invention precedent in
``ollama_embeddings.py``.

Response schema (Cohere v1 documented contract):

    {
      "id": "...",
      "texts": ["hello", "world"],
      "embeddings": [[0.1, ...], [0.2, ...]],
      "meta": {
        "api_version": {"version": "1"},
        "billed_units": {"input_tokens": 10}
      },
      "response_type": "embeddings_floats"
    }

``parse_response`` extracts the normalized ``{vectors, model, usage}`` view.
Unlike OpenAI's ``data[].index``-ordered array, Cohere's ``embeddings`` list
is returned in REQUEST order with no per-item index -- no sort is applied
(same contract as ``ollama_embeddings.py``).

Cross-SDK parity: this shaper's output for a fixed input is intended to be
byte-identical to the kailash-rs Cohere embeddings payload builder. Per
`rules/cross-sdk-inspection.md` Rule 4, at least one deterministic
byte-shape pin test is committed in the Tier-1 suite
(``tests/unit/llm/test_embed_remainder_shapers.py``); full sibling-SDK
byte-vector pinning against the Rust SDK's ACTUAL output is NOT landed as
of this shard (Wave-1b EMBED-REMAINDER) -- flagged as a follow-up cross-SDK
lockstep item, not a blocking gap for this shard's scope.
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
    """Build the ``/v1/embed`` request body for Cohere.

    Mirrors ``openai_embeddings.build_request_payload``'s rejection
    contract exactly:

    * Rejects ``texts=[]`` with ``ValueError`` at the shaper boundary so
      the caller gets a typed error before the HTTP round-trip.
    * Rejects non-string elements in ``texts`` so a caller passing, e.g.,
      ``[b"bytes"]`` fails with a shape error rather than a 400 echoing
      the raw bytes.
    * ``input_type`` is only written to the payload when the caller
      actually set ``options.input_type`` -- callers targeting a v2 model
      that rejects the field do NOT get a silent addition.
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
            "read from os.environ['COHERE_EMBEDDING_MODEL'] per rules/env-models.md"
        )

    payload: Dict[str, Any] = {
        "model": model,
        "texts": list(texts),
    }
    if options is not None:
        if not isinstance(options, EmbedOptions):
            raise TypeError(
                f"options must be EmbedOptions; got {type(options).__name__}"
            )
        if options.input_type is not None:
            payload["input_type"] = options.input_type
    return payload


def parse_response(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Extract ``{vectors, model, usage}`` from a Cohere ``/v1/embed`` response.

    Raises ``InvalidResponse`` with a stable ``reason`` when the payload
    shape violates the documented contract. ``embeddings`` is returned in
    request order (no per-item index field on this endpoint), so no sort
    is applied -- unlike ``openai_embeddings.parse_response``.
    """
    if not isinstance(payload, dict):
        raise TypeError(
            f"parse_response expects a dict payload; got {type(payload).__name__}"
        )
    embeddings = payload.get("embeddings")
    if not isinstance(embeddings, list):
        raise InvalidResponse("cohere_embeddings: missing or non-list 'embeddings'")

    vectors: List[List[float]] = []
    for item in embeddings:
        if not isinstance(item, list):
            raise InvalidResponse("cohere_embeddings: 'embeddings' entry is not a list")
        for v in item:
            if not isinstance(v, (int, float)) or isinstance(v, bool):
                raise InvalidResponse(
                    "cohere_embeddings: 'embeddings' entry contains non-numeric value"
                )
        vectors.append([float(v) for v in item])

    meta = payload.get("meta") or {}
    billed_units = meta.get("billed_units", {}) if isinstance(meta, dict) else {}
    input_tokens = (
        billed_units.get("input_tokens") if isinstance(billed_units, dict) else None
    )
    return {
        "vectors": vectors,
        "model": payload.get("model"),
        "usage": {
            "input_tokens": input_tokens,
            # Cohere's embed endpoint reports one billed-units figure
            # (input_tokens) -- there is no separate embedding "output" to
            # bill, so total_tokens mirrors input_tokens (same convention
            # as ollama_embeddings.parse_response's single-count usage).
            "total_tokens": input_tokens,
        },
    }


__all__ = ["build_request_payload", "parse_response"]

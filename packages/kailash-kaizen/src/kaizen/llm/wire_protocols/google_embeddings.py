# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Google Gemini Embeddings wire protocol shaper (#1818).

Shapes the on-the-wire request/response for Gemini's
``POST /v1beta/models/{model}:batchEmbedContents`` endpoint. Consumed by
``LlmClient.embed(...)`` via its Google dispatch path
(``WireProtocol.GoogleGenerateContent`` — Gemini speaks one wire family
across both chat AND embeddings; ``google_generate_content.py`` owns the
``:generateContent`` chat shape, this module owns ``:batchEmbedContents``).
This is the embed half of the Google migration target for #1720 — the
four-axis path previously had a Google CHAT wire but NO Google EMBED wire
(the known 2.36.0 CHANGELOG delta).

The BATCH endpoint (``:batchEmbedContents``) is used unconditionally rather
than the single-text ``:embedContent`` so a caller passing one OR many texts
routes through ONE shaper + ONE dispatch entry — the same "always send the
list" contract every other embed wire (``openai_embeddings`` ``input``,
``cohere_embeddings`` ``texts``) already honors. The model travels in the URL
path (``/models/{model}:batchEmbedContents``, substituted by
``LlmClient._build_embed_url``), mirroring HuggingFace's feature-extraction
route; each per-text ``requests[]`` entry ALSO carries a ``model`` field of the
form ``models/{model}`` as the Gemini batch contract requires.

Request schema (Gemini v1beta documented contract):

    {
      "requests": [
        {
          "model": "models/text-embedding-004",
          "content": {"parts": [{"text": "hello"}]}
        },
        ...
      ]
    }

* ``model`` (str, per request) — required; the ``models/``-prefixed model id.
  ``build_request_payload`` prepends ``models/`` when the caller-supplied
  model does not already carry it, so ``text-embedding-004`` and
  ``models/text-embedding-004`` both produce the documented body shape.
* ``content.parts[].text`` (str) — one text per ``requests[]`` entry.
* ``outputDimensionality`` (int, optional) — Gemini's per-request output
  vector truncation (``text-embedding-004`` supports it). Sourced from
  ``EmbedOptions.dimensions`` and emitted ONLY when the caller sets it, so a
  caller relying on the model default gets a byte-identical body (the same
  emit-only-when-set discipline ``openai_embeddings`` applies to
  ``dimensions``/``user`` and ``cohere_embeddings`` to ``input_type``).
  ``EmbedOptions.user`` / ``input_type`` carry no Gemini-embed analogue and
  are silently NOT emitted (the documented-contract-not-Kaizen-invention
  precedent from ``ollama_embeddings`` / ``cohere_embeddings``).

Response schema (Gemini v1beta documented contract):

    {
      "embeddings": [
        {"values": [0.013, -0.02, ...]},
        {"values": [0.041,  0.11, ...]}
      ]
    }

``parse_response`` extracts the normalized ``{vectors, model, usage}`` view.
Gemini's ``embeddings`` list is returned in REQUEST order with no per-item
index (same contract as ``cohere_embeddings`` / ``ollama_embeddings``), so no
sort is applied. The ``:batchEmbedContents`` response carries no token/usage
metadata, so ``usage`` reports ``None`` for both figures (the same honest
absent-usage shape ``huggingface_embeddings`` returns).

Cross-SDK parity: this shaper's output for a fixed input is intended to be
byte-identical to the kailash-rs Google embeddings payload builder. Per
`rules/cross-sdk-inspection.md` Rule 4, at least one deterministic byte-shape
pin test is committed in the Tier-1 suite
(``tests/unit/llm/test_embed_remainder_shapers.py``); full sibling-SDK
byte-vector pinning against the Rust SDK's ACTUAL output is a follow-up
cross-SDK lockstep item, not a blocking gap for this shard's scope.
"""

from __future__ import annotations

from typing import Any, Dict, List

from kaizen.llm.deployment import EmbedOptions
from kaizen.llm.errors import InvalidResponse


def _model_field(model: str) -> str:
    """Return the ``models/``-prefixed model id Gemini's batch body requires.

    Gemini's ``:batchEmbedContents`` contract wants each per-text request's
    ``model`` field as ``models/{id}`` (e.g. ``models/text-embedding-004``),
    while the URL path already carries the bare id. Accept both a bare id and
    an already-prefixed one so the caller's env-sourced model string works
    unchanged either way.
    """
    return model if model.startswith("models/") else f"models/{model}"


def build_request_payload(
    texts: List[str],
    model: str,
    options: EmbedOptions | None = None,
) -> Dict[str, Any]:
    """Build the ``:batchEmbedContents`` request body for Gemini.

    Mirrors ``cohere_embeddings.build_request_payload``'s rejection contract
    exactly:

    * Rejects ``texts=[]`` with ``ValueError`` at the shaper boundary so the
      caller gets a typed error before the HTTP round-trip.
    * Rejects non-string elements in ``texts`` so a caller passing, e.g.,
      ``[b"bytes"]`` fails with a shape error rather than a 400 echoing the
      raw bytes.
    * ``outputDimensionality`` is only written to a request when the caller
      actually set ``options.dimensions`` — a caller relying on the model's
      native dimension gets no silent addition.
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
            "read from os.environ['GOOGLE_EMBEDDING_MODEL'] per rules/env-models.md"
        )

    output_dimensionality: int | None = None
    if options is not None:
        if not isinstance(options, EmbedOptions):
            raise TypeError(
                f"options must be EmbedOptions; got {type(options).__name__}"
            )
        output_dimensionality = options.dimensions

    model_field = _model_field(model)
    requests: List[Dict[str, Any]] = []
    for t in texts:
        request: Dict[str, Any] = {
            "model": model_field,
            "content": {"parts": [{"text": t}]},
        }
        if output_dimensionality is not None:
            request["outputDimensionality"] = output_dimensionality
        requests.append(request)
    return {"requests": requests}


def parse_response(payload: Dict[str, Any], options: Any = None) -> Dict[str, Any]:
    """Extract ``{vectors, model, usage}`` from a Gemini ``:batchEmbedContents`` response.

    Raises ``InvalidResponse`` with a stable ``reason`` when the payload shape
    violates the documented contract. ``embeddings`` is returned in request
    order (no per-item index field on this endpoint), so no sort is applied —
    same contract as ``cohere_embeddings.parse_response``.

    ``options`` is accepted for dispatch symmetry with every embed shaper (the
    shared ``LlmClient.embed`` call site threads it uniformly, #1720 Wave-A
    parity) and is intentionally IGNORED here: Gemini honors
    ``outputDimensionality`` at the request level and applies no post-parse
    normalization. NO embed shaper consumes ``EmbedOptions.normalize`` at parse
    time — ``LlmClient.embed`` applies L2 normalization uniformly, client-side,
    for every wire (#1720 Wave-B1).
    """
    if not isinstance(payload, dict):
        raise TypeError(
            f"parse_response expects a dict payload; got {type(payload).__name__}"
        )
    embeddings = payload.get("embeddings")
    if not isinstance(embeddings, list):
        raise InvalidResponse("google_embeddings: missing or non-list 'embeddings'")

    vectors: List[List[float]] = []
    for item in embeddings:
        if not isinstance(item, dict):
            raise InvalidResponse("google_embeddings: 'embeddings' entry is not a dict")
        values = item.get("values")
        if not isinstance(values, list):
            raise InvalidResponse(
                "google_embeddings: 'embeddings' entry missing 'values' list"
            )
        for v in values:
            if not isinstance(v, (int, float)) or isinstance(v, bool):
                raise InvalidResponse(
                    "google_embeddings: 'values' contains non-numeric value"
                )
        vectors.append([float(v) for v in values])

    return {
        "vectors": vectors,
        # Gemini's :batchEmbedContents response does not echo the model id;
        # report None (the model is fixed by the caller's deployment/URL).
        "model": payload.get("model"),
        # No token/usage metadata on this endpoint — report absent honestly
        # (same shape as huggingface_embeddings' no-usage response).
        "usage": {
            "input_tokens": None,
            "total_tokens": None,
        },
    }


__all__ = ["build_request_payload", "parse_response"]

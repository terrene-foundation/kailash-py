# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""OpenAI Embeddings wire protocol shaper (#462).

Shapes the on-the-wire request/response for OpenAI's ``POST /v1/embeddings``
endpoint. Consumed by ``LlmClient.embed(...)`` via its OpenAI dispatch path.

Request schema (OpenAI documented contract):

* ``model`` (str)   — required; e.g. ``"text-embedding-3-small"``.
* ``input`` (list of str)  — required; one or more strings to embed. The
  helper rejects empty lists at ``build_request_payload`` time to give a
  typed error at the shaper boundary rather than a 400 from OpenAI.
* ``dimensions`` (int, optional) — output vector dimension for models that
  support truncation (``text-embedding-3-*``). Omitted when unset so legacy
  ``text-embedding-ada-002`` callers work without a schema change.
* ``user`` (str, optional) — opaque caller identifier for abuse tracking.
* ``encoding_format`` is deliberately NOT exposed: we always request the
  default ``float`` format and parse the response as ``list[list[float]]``.
  Supporting ``base64`` would require a second decode path without adding
  value for the RAG / semantic-search use cases driving #462.

Response schema (OpenAI documented contract):

    {
      "object": "list",
      "data": [
        {"object": "embedding", "index": 0, "embedding": [0.1, ...]},
        ...
      ],
      "model": "text-embedding-3-small",
      "usage": {"prompt_tokens": N, "total_tokens": N}
    }

``parse_response`` extracts the normalized ``{vectors, model, usage}`` view.
The ``data`` array MUST be sorted by ``index`` before vectors are pulled —
OpenAI returns them in index order today, but the shape contract does not
guarantee it, and a future partial-response ordering change would silently
corrupt aligned caller arrays. The sort is O(n log n) on a list that is
typically short; round-trip correctness outweighs the cost.

Cross-SDK parity: this shaper's output for a fixed input is byte-identical
to the kailash-rs OpenAI embeddings payload builder (#393).
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
    """Build the ``/v1/embeddings`` request body for OpenAI.

    * Rejects ``texts=[]`` with ``ValueError`` at the shaper boundary so
      the caller gets a typed error before the HTTP round-trip.
    * Rejects non-string elements in ``texts`` so a caller passing, e.g.,
      ``[b"bytes"]`` fails with a shape error rather than a 400 echoing
      the raw bytes.
    * ``dimensions`` / ``user`` are only written to the payload when the
      caller actually set them; callers relying on model defaults do NOT
      get a silent override.
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
            "read from os.environ['OPENAI_EMBEDDING_MODEL'] per rules/env-models.md"
        )

    payload: Dict[str, Any] = {
        "model": model,
        "input": list(texts),
    }
    if options is not None:
        if not isinstance(options, EmbedOptions):
            raise TypeError(
                f"options must be EmbedOptions; got {type(options).__name__}"
            )
        if options.dimensions is not None:
            payload["dimensions"] = options.dimensions
        if options.user is not None:
            payload["user"] = options.user
    return payload


def parse_response(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Extract ``{vectors, model, usage}`` from an OpenAI embeddings response.

    Raises ``InvalidResponse`` with a stable ``reason`` when the payload
    shape violates the documented contract. The ``reason`` strings are
    caller-controlled constants (not user-supplied) and are safe to log.
    """
    if not isinstance(payload, dict):
        raise TypeError(
            f"parse_response expects a dict payload; got {type(payload).__name__}"
        )
    data = payload.get("data")
    if not isinstance(data, list):
        raise InvalidResponse("openai_embeddings: missing or non-list 'data'")
    # Sort by reported `index` so vectors are returned in request order
    # regardless of server-side reordering. Entries without an index
    # default to 0, which preserves stable order for single-text calls.
    try:
        data_sorted = sorted(data, key=lambda item: int(item.get("index", 0)))
    except (TypeError, ValueError):
        raise InvalidResponse(
            "openai_embeddings: 'data' entry has non-integer 'index'"
        )
    vectors: List[List[float]] = []
    for item in data_sorted:
        if not isinstance(item, dict):
            raise InvalidResponse(
                "openai_embeddings: 'data' entry is not a dict"
            )
        embedding = item.get("embedding")
        if not isinstance(embedding, list):
            raise InvalidResponse(
                "openai_embeddings: 'data' entry missing 'embedding' list"
            )
        # Validate each element is a float / int (JSON numbers decode as
        # either). Reject strings / nulls at the shape boundary rather
        # than let them propagate into caller arrays where a later numpy
        # coercion would fail with an opaque message.
        for v in embedding:
            if not isinstance(v, (int, float)) or isinstance(v, bool):
                raise InvalidResponse(
                    "openai_embeddings: 'embedding' contains non-numeric value"
                )
        vectors.append([float(v) for v in embedding])
    usage = payload.get("usage") or {}
    return {
        "vectors": vectors,
        "model": payload.get("model"),
        "usage": {
            "input_tokens": usage.get("prompt_tokens"),
            "total_tokens": usage.get("total_tokens"),
        },
    }


__all__ = ["build_request_payload", "parse_response"]

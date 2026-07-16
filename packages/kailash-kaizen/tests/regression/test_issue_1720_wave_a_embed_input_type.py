# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""#1720 Wave-A invariant #4 — EmbedOptions.input_type byte-shape pin.

Legacy Cohere embeddings pass ``input_type="search_document"``
(nodes/ai/embedding_generator.py::_generate_provider_embedding). The four-axis
``EmbedOptions`` carries an optional ``input_type: str | None = None`` field
(landed additive in Wave-1a/1b) and ``client.embed`` threads it through the
Cohere embed shaper. This regression PINS the byte-shape contract so a future
refactor cannot silently drop the field or make an unset field non-neutral:

* ``EmbedOptions(input_type="search_document")`` -> the Cohere embed request
  payload carries ``"input_type": "search_document"``;
* ``input_type=None`` (or no options) -> the payload is BYTE-IDENTICAL to
  today (the field is never emitted) — the additive-neutrality invariant.

The Cohere embed REQUEST PAYLOAD is exactly what
``cohere_embeddings.build_request_payload`` produces (the shaper
``client.embed`` dispatches to for ``WireProtocol.CohereGenerate``); pinning
it here is deterministic + offline (no network, no live keys).

Behavioral asserts (call build_request_payload, assert the returned dict) per
rules/testing.md § "Behavioral Regression Tests Over Source-Grep".
"""

from __future__ import annotations

import pytest

from kaizen.llm.deployment import EmbedOptions
from kaizen.llm.wire_protocols import cohere_embeddings

# Synthetic fixture model — this is an offline byte-shape pin, not a live
# call; a deterministic literal is required to assert exact payload bytes
# (env-sourced models would make the pin non-deterministic).
_MODEL = "test-embed-model"
_TEXTS = ["hello", "world"]


@pytest.mark.regression
def test_embedoptions_input_type_field_defaults_none():
    """The field is additive + backward-safe: default None, frozen model."""
    assert EmbedOptions().input_type is None
    assert EmbedOptions(input_type="search_document").input_type == "search_document"


@pytest.mark.regression
def test_cohere_payload_carries_input_type_when_set():
    payload = cohere_embeddings.build_request_payload(
        _TEXTS, _MODEL, EmbedOptions(input_type="search_document")
    )
    assert payload == {
        "model": _MODEL,
        "texts": _TEXTS,
        "input_type": "search_document",
    }


@pytest.mark.regression
def test_cohere_payload_byte_neutral_when_input_type_unset():
    """input_type=None (options present) AND options=None BOTH produce the
    exact pre-input_type payload — no ``input_type`` key emitted."""
    baseline = cohere_embeddings.build_request_payload(_TEXTS, _MODEL, None)
    with_unset_option = cohere_embeddings.build_request_payload(
        _TEXTS, _MODEL, EmbedOptions(input_type=None)
    )
    assert baseline == {"model": _MODEL, "texts": _TEXTS}
    assert "input_type" not in baseline
    assert with_unset_option == baseline  # byte-identical to today

# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Tier-1 unit tests for the #1720 Wave-1b EMBED-REMAINDER shard.

Covers the two new embedding shapers (cohere / huggingface), the azure
api-version URL fix (preset query_params + _build_embed_url append), and the
_EMBED_DISPATCH wiring. Offline by construction — no network, no live keys.

Behavioral asserts only (call build/parse, assert the payload/normalized
shape) per rules/testing.md; no source-grep-as-assertion.
"""

from __future__ import annotations

import math

import pytest

from kaizen.llm import LlmClient
from kaizen.llm.auth.azure import AzureEntra
from kaizen.llm.deployment import EmbedOptions, WireProtocol
from kaizen.llm.errors import InvalidResponse
from kaizen.llm.presets import (
    AZURE_OPENAI_DEFAULT_API_VERSION,
    azure_openai_preset,
    huggingface_preset,
)
from kaizen.llm.wire_protocols import cohere_embeddings, huggingface_embeddings

# ---------------------------------------------------------------------------
# cohere_embeddings.build_request_payload
# ---------------------------------------------------------------------------


def test_cohere_build_minimal_shape() -> None:
    payload = cohere_embeddings.build_request_payload(
        ["hello", "world"], "embed-english-v3.0"
    )
    # Deterministic byte-shape pin: no input_type when options unset.
    assert payload == {"model": "embed-english-v3.0", "texts": ["hello", "world"]}


def test_cohere_build_emits_input_type_only_when_set() -> None:
    opts = EmbedOptions(input_type="search_document")
    payload = cohere_embeddings.build_request_payload(["q"], "embed-english-v3.0", opts)
    assert payload["input_type"] == "search_document"
    # dimensions / user are NOT emitted for Cohere even when set.
    payload_no_it = cohere_embeddings.build_request_payload(
        ["q"], "embed-english-v3.0", EmbedOptions(dimensions=256, user="u")
    )
    assert "input_type" not in payload_no_it
    assert "dimensions" not in payload_no_it and "user" not in payload_no_it


def test_cohere_build_rejects_empty_and_non_str() -> None:
    with pytest.raises(ValueError):
        cohere_embeddings.build_request_payload([], "embed-english-v3.0")
    with pytest.raises(TypeError):
        cohere_embeddings.build_request_payload([b"bytes"], "embed-english-v3.0")  # type: ignore[list-item]
    with pytest.raises(ValueError):
        cohere_embeddings.build_request_payload(["ok"], "")


def test_cohere_parse_extracts_vectors_in_request_order() -> None:
    resp = {
        "embeddings": [[0.1, 0.2], [0.3, 0.4]],
        "model": "embed-english-v3.0",
        "meta": {"billed_units": {"input_tokens": 7}},
    }
    out = cohere_embeddings.parse_response(resp)
    assert out["vectors"] == [[0.1, 0.2], [0.3, 0.4]]
    assert out["model"] == "embed-english-v3.0"
    assert out["usage"]["input_tokens"] == 7


def test_cohere_parse_rejects_malformed() -> None:
    with pytest.raises(InvalidResponse):
        cohere_embeddings.parse_response({"embeddings": "nope"})
    with pytest.raises(InvalidResponse):
        cohere_embeddings.parse_response({"embeddings": [["x"]]})  # non-numeric
    with pytest.raises(InvalidResponse):
        cohere_embeddings.parse_response({"embeddings": [[True]]})  # bool rejected


# ---------------------------------------------------------------------------
# huggingface_embeddings.build_request_payload / parse_response
# ---------------------------------------------------------------------------


def test_hf_build_inputs_shape_model_not_in_body() -> None:
    payload = huggingface_embeddings.build_request_payload(
        ["a", "b"], "sentence-transformers/all-MiniLM-L6-v2"
    )
    # Deterministic byte-shape pin: model is URL-path only, not in the body.
    assert payload == {"inputs": ["a", "b"]}


def test_hf_build_rejects_empty_and_non_str() -> None:
    with pytest.raises(ValueError):
        huggingface_embeddings.build_request_payload([], "m")
    with pytest.raises(TypeError):
        huggingface_embeddings.build_request_payload([1], "m")  # type: ignore[list-item]


def test_hf_parse_pooled_shape() -> None:
    out = huggingface_embeddings.parse_response([[0.1, 0.2], [0.3, 0.4]])
    assert out["vectors"] == [[0.1, 0.2], [0.3, 0.4]]
    assert out["model"] is None


def test_hf_parse_unpooled_mean_pools_tokens() -> None:
    # One input text, two token vectors → mean-pool to one sentence vector.
    out = huggingface_embeddings.parse_response([[[0.0, 2.0], [2.0, 4.0]]])
    assert out["vectors"] == [[1.0, 3.0]]


def test_hf_parse_normalizes_when_option_set() -> None:
    out = huggingface_embeddings.parse_response(
        [[3.0, 4.0]], EmbedOptions(normalize=True)
    )
    v = out["vectors"][0]
    assert math.isclose(math.sqrt(v[0] ** 2 + v[1] ** 2), 1.0, rel_tol=1e-9)
    # Without normalize, the raw vector passes through.
    out_raw = huggingface_embeddings.parse_response([[3.0, 4.0]])
    assert out_raw["vectors"] == [[3.0, 4.0]]


def test_hf_parse_rejects_non_list_top_level() -> None:
    with pytest.raises(InvalidResponse):
        huggingface_embeddings.parse_response({"not": "an array"})


# ---------------------------------------------------------------------------
# _EMBED_DISPATCH wiring (structural: the two new wires are routable)
# ---------------------------------------------------------------------------


def test_embed_dispatch_wires_cohere_and_huggingface() -> None:
    from kaizen.llm.client import _EMBED_DISPATCH

    assert WireProtocol.CohereGenerate in _EMBED_DISPATCH
    assert WireProtocol.HuggingFaceInference in _EMBED_DISPATCH
    assert _EMBED_DISPATCH[WireProtocol.CohereGenerate]["shaper"] is cohere_embeddings
    assert (
        _EMBED_DISPATCH[WireProtocol.HuggingFaceInference]["shaper"]
        is huggingface_embeddings
    )


# ---------------------------------------------------------------------------
# Azure api-version — guards BOTH the preset AND _build_embed_url append.
# ---------------------------------------------------------------------------


def test_azure_preset_carries_api_version_query_param() -> None:
    dep = azure_openai_preset(
        "myresource", "gpt-4o-embed", AzureEntra(api_key="test-azure-api-key")
    )
    assert dep.endpoint.query_params == {
        "api-version": AZURE_OPENAI_DEFAULT_API_VERSION
    }


def test_azure_embed_url_carries_api_version() -> None:
    dep = azure_openai_preset(
        "myresource", "gpt-4o-embed", AzureEntra(api_key="test-azure-api-key")
    )
    client = LlmClient.from_deployment(dep)
    url = client._build_embed_url("/embeddings")
    # The api-version MUST reach the embed URL (else Azure embed 400s).
    assert "?api-version=" in url
    assert AZURE_OPENAI_DEFAULT_API_VERSION in url
    assert url.endswith(f"api-version={AZURE_OPENAI_DEFAULT_API_VERSION}")


def test_non_azure_embed_url_has_no_query_string() -> None:
    # Byte-neutrality: a deployment WITHOUT query_params emits no '?' suffix.
    from kaizen.llm.deployment import LlmDeployment

    dep = LlmDeployment.openai(api_key="sk-test", model="text-embedding-3-small")
    client = LlmClient.from_deployment(dep)
    url = client._build_embed_url("/embeddings")
    assert "?" not in url


# ---------------------------------------------------------------------------
# /redteam Round-1 FIX 1 (CRITICAL) — HuggingFace embed 100% broken:
# `_build_embed_url` was called with no `model=`, so the HuggingFace wire's
# `"/models/{model}"` path suffix substituted an EMPTY string, and
# `_validate_completion_model("")` raised ValueError on EVERY hf embed call.
# This pins the exact call-site shape `embed()` now uses.
# ---------------------------------------------------------------------------


def test_hf_embed_url_carries_model_in_path() -> None:
    dep = huggingface_preset(
        api_key="hf_x", model="sentence-transformers/all-MiniLM-L6-v2"
    )
    client = LlmClient.from_deployment(dep)
    # No ValueError — the exact regression: _build_embed_url called with no
    # model= substituted "" into "{model}" and _validate_completion_model("")
    # raised on every hf embed call.
    url = client._build_embed_url(
        "/models/{model}", model="sentence-transformers/all-MiniLM-L6-v2"
    )
    assert "sentence-transformers/all-MiniLM-L6-v2" in url
    assert "{model}" not in url

# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""#1720 Wave-B1b — embedding path cutover onto the four-axis ``LlmClient``.

Pins the behavioral contract of the embed cutover shard:

* ``EmbeddingGeneratorNode._generate_provider_embedding`` returns a vector via
  the four-axis embed path (``resolve_deployment_for`` -> ``from_deployment_sync``
  -> ``embed`` -> first vector) for openai.
* ``LlmClient.embed(..., options=EmbedOptions(normalize=True))`` returns UNIT
  vectors (L2 norm ~= 1.0) UNIFORMLY for openai AND ollama AND cohere -- the
  folded F2-MEDIUM applies one client-side normalize for EVERY wire (not the
  former HuggingFace-only copy).
* ``normalize`` unset / ``None`` leaves the returned vectors BYTE-IDENTICAL to
  the raw wire output for every wire (additive-neutrality).
* A zero vector is returned UNCHANGED under ``normalize=True`` (norm==0 guard).
* The new ``timeout`` kwarg on ``LlmClient.embed`` is accepted and THREADED into
  the underlying ``LlmHttpClient`` request (proven by an injected transport that
  records the ``timeout`` it receives); omitting it injects no ``timeout`` kwarg.

Tier-1 offline + deterministic: every wire call is served by a Protocol-
satisfying canned-bytes transport (``rules/testing.md`` § "Protocol Adapters" --
NOT a mock), the same shared-canned-bytes injection style the #1720 parity
harness uses. No network, no live credentials, no env mutation.
Behavioral asserts (call ``embed`` / the node method, assert the returned
vectors) per ``rules/testing.md`` § "Behavioral Regression Tests Over
Source-Grep".
"""

from __future__ import annotations

import math
from typing import Any

import httpx
import pytest

from kaizen.llm import LlmClient, resolve_deployment_for
from kaizen.llm.deployment import EmbedOptions
from kaizen.nodes.ai.embedding_generator import EmbeddingGeneratorNode

# Synthetic offline fixtures — deterministic literals are required to assert
# exact returned vectors; env-sourced models/keys would make the pin
# non-deterministic (and no live call is made — the transport is canned).
_OPENAI_MODEL = "fixture-openai-embed"
_OLLAMA_MODEL = "fixture-ollama-embed"
_COHERE_MODEL = "fixture-cohere-embed"


def _openai_body(vec: list[float]) -> dict:
    return {
        "data": [{"index": 0, "embedding": vec}],
        "model": "fixture-model",
        "usage": {"prompt_tokens": 1, "total_tokens": 1},
    }


def _ollama_body(vec: list[float]) -> dict:
    return {"embeddings": [vec], "model": "fixture-model"}


def _cohere_body(vec: list[float]) -> dict:
    return {"embeddings": [vec], "model": "fixture-model"}


class _CannedEmbedTransport:
    """Protocol-satisfying offline transport: replays a FIXED embeddings body
    and RECORDS the ``timeout`` kwarg each ``post`` receives.

    Satisfies the ``LlmHttpClient`` surface ``LlmClient.embed`` calls (``post``
    + ``aclose``); never opens a socket. An injected transport is owned by the
    caller, so ``embed`` never closes it -- ``aclose`` is provided for contract
    completeness only.
    """

    def __init__(self, body: Any) -> None:
        self._body = body
        self.timeouts: list[Any] = []
        self.calls: list[dict[str, Any]] = []
        self._closed = False

    @property
    def is_closed(self) -> bool:
        return self._closed

    async def post(self, url: str, **kwargs: Any) -> httpx.Response:
        self.timeouts.append(kwargs.get("timeout"))
        self.calls.append(
            {
                "url": url,
                "json": kwargs.get("json"),
                "timeout": kwargs.get("timeout"),
            }
        )
        return httpx.Response(200, json=self._body, request=httpx.Request("POST", url))

    async def aclose(self) -> None:
        self._closed = True


# Per-wire (provider, model, api_key, base_url, body-builder) matrix. api_key /
# base_url are passed EXPLICITLY to resolve_deployment_for so no env var is read
# (no env-mutation, no lock needed per rules/testing.md § env serialization).
_WIRES = [
    ("openai", _OPENAI_MODEL, "sk-fixture", None, _openai_body),
    ("ollama", _OLLAMA_MODEL, None, "http://localhost:11434", _ollama_body),
    ("cohere", _COHERE_MODEL, "co-fixture", None, _cohere_body),
]


def _client_for(provider: str, api_key, base_url, model: str) -> LlmClient:
    deployment = resolve_deployment_for(
        provider, model, api_key=api_key, base_url=base_url
    )
    assert deployment is not None, (
        f"resolve_deployment_for({provider!r}) returned None; the wire must "
        "resolve for the embed cutover matrix"
    )
    return LlmClient.from_deployment(deployment)


# ---------------------------------------------------------------------------
# (b) UNIFORM client-side normalize — openai AND ollama AND cohere
# ---------------------------------------------------------------------------


@pytest.mark.regression
@pytest.mark.asyncio
@pytest.mark.parametrize("provider,model,api_key,base_url,body_fn", _WIRES)
async def test_embed_normalize_true_unit_vectors_every_wire(
    provider, model, api_key, base_url, body_fn
):
    """``EmbedOptions(normalize=True)`` L2-unit-normalizes the returned vector
    for EVERY wire (uniform client-side, not HF-only). [3, 4] -> [0.6, 0.8]."""
    client = _client_for(provider, api_key, base_url, model)
    transport = _CannedEmbedTransport(body_fn([3.0, 4.0]))

    vectors = await client.embed(
        ["x"], model=model, options=EmbedOptions(normalize=True), http_client=transport
    )

    v = vectors[0]
    assert math.isclose(math.hypot(v[0], v[1]), 1.0, rel_tol=1e-9)
    assert math.isclose(v[0], 0.6, rel_tol=1e-9)
    assert math.isclose(v[1], 0.8, rel_tol=1e-9)


# ---------------------------------------------------------------------------
# (c) normalize unset / None -> byte-identical raw wire output, every wire
# ---------------------------------------------------------------------------


@pytest.mark.regression
@pytest.mark.asyncio
@pytest.mark.parametrize("provider,model,api_key,base_url,body_fn", _WIRES)
async def test_embed_normalize_none_byte_identical_raw(
    provider, model, api_key, base_url, body_fn
):
    """No options AND ``EmbedOptions(normalize=None)`` both leave the raw wire
    vector untouched (additive-neutrality)."""
    client = _client_for(provider, api_key, base_url, model)

    no_opts = await client.embed(
        ["x"], model=model, http_client=_CannedEmbedTransport(body_fn([3.0, 4.0]))
    )
    assert no_opts == [[3.0, 4.0]]

    explicit_none = await client.embed(
        ["x"],
        model=model,
        options=EmbedOptions(normalize=None),
        http_client=_CannedEmbedTransport(body_fn([3.0, 4.0])),
    )
    assert explicit_none == [[3.0, 4.0]]


@pytest.mark.regression
@pytest.mark.asyncio
async def test_embed_normalize_true_zero_vector_unchanged():
    """A zero vector (L2 norm == 0) is returned UNCHANGED under normalize=True
    (the norm==0 guard divides nothing)."""
    client = _client_for("openai", "sk-fixture", None, _OPENAI_MODEL)
    transport = _CannedEmbedTransport(_openai_body([0.0, 0.0, 0.0]))

    vectors = await client.embed(
        ["x"],
        model=_OPENAI_MODEL,
        options=EmbedOptions(normalize=True),
        http_client=transport,
    )
    assert vectors[0] == [0.0, 0.0, 0.0]


# ---------------------------------------------------------------------------
# (d) timeout kwarg accepted + threaded into the http client
# ---------------------------------------------------------------------------


@pytest.mark.regression
@pytest.mark.asyncio
async def test_embed_timeout_threaded_to_http_client():
    """A caller-supplied ``timeout`` reaches the injected http client's
    request; omitting it injects NO ``timeout`` kwarg (byte-neutral)."""
    client = _client_for("openai", "sk-fixture", None, _OPENAI_MODEL)

    with_timeout = _CannedEmbedTransport(_openai_body([1.0, 2.0]))
    await client.embed(
        ["x"], model=_OPENAI_MODEL, timeout=12.5, http_client=with_timeout
    )
    assert with_timeout.timeouts == [12.5]

    without_timeout = _CannedEmbedTransport(_openai_body([1.0, 2.0]))
    await client.embed(["x"], model=_OPENAI_MODEL, http_client=without_timeout)
    assert without_timeout.timeouts == [None]


# ---------------------------------------------------------------------------
# (a) EmbeddingGeneratorNode cutover — four-axis embed path for openai
# ---------------------------------------------------------------------------


class _CannedEmbedClient(LlmClient):
    """``LlmClient`` subclass that injects the canned transport into ``embed``
    so the node's four-axis embed path runs fully offline. The node calls
    ``LlmClient.from_deployment_sync(...).embed(...)`` with NO http_client;
    this subclass supplies it, exercising the REAL embed parse end-to-end."""

    _canned_body: Any = None

    async def embed(self, texts, **kwargs):  # type: ignore[override]
        kwargs.setdefault("http_client", _CannedEmbedTransport(self._canned_body))
        return await super().embed(texts, **kwargs)


@pytest.mark.regression
def test_node_generate_provider_embedding_uses_four_axis_path(monkeypatch):
    """``EmbeddingGeneratorNode._generate_provider_embedding`` returns a vector
    through the four-axis embed path (resolver -> from_deployment_sync ->
    embed -> first vector) for openai. Both ``resolve_deployment_for`` and
    ``LlmClient`` are patched on the ``kaizen.llm`` module the node imports from
    (the node does a function-local ``from kaizen.llm import ...``), keeping the
    test offline WITHOUT mutating any env var."""
    import kaizen.llm as kllm

    real_deployment = resolve_deployment_for(
        "openai", _OPENAI_MODEL, api_key="sk-fixture"
    )
    assert real_deployment is not None

    _CannedEmbedClient._canned_body = _openai_body([3.0, 4.0, 0.0])
    monkeypatch.setattr(kllm, "resolve_deployment_for", lambda *a, **k: real_deployment)
    monkeypatch.setattr(kllm, "LlmClient", _CannedEmbedClient)

    node = EmbeddingGeneratorNode()
    vector = node._generate_provider_embedding(
        "hello", "openai", _OPENAI_MODEL, None, 60, 3
    )

    assert vector == [3.0, 4.0, 0.0]


@pytest.mark.regression
def test_node_generate_provider_embedding_cohere_sets_input_type(monkeypatch):
    """The node threads the cohere ``input_type="search_document"`` field into
    ``EmbedOptions`` (Cohere v3 embed requires it) — asserted via the request
    body the injected transport records."""
    import kaizen.llm as kllm

    real_deployment = resolve_deployment_for(
        "cohere", _COHERE_MODEL, api_key="co-fixture"
    )
    assert real_deployment is not None

    captured = _CannedEmbedTransport(_cohere_body([0.1, 0.2]))

    class _Client(LlmClient):
        async def embed(self, texts, **kwargs):  # type: ignore[override]
            kwargs.setdefault("http_client", captured)
            return await super().embed(texts, **kwargs)

    monkeypatch.setattr(kllm, "resolve_deployment_for", lambda *a, **k: real_deployment)
    monkeypatch.setattr(kllm, "LlmClient", _Client)

    node = EmbeddingGeneratorNode()
    node._generate_provider_embedding("hi", "cohere", _COHERE_MODEL, None, 60, 3)

    assert captured.calls, "the cohere embed request never reached the transport"
    assert captured.calls[0]["json"].get("input_type") == "search_document"

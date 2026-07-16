# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""#1720 Wave-1b remainder — holistic multi-wave /redteam Round-2 hardening pins.

Round-1 fixes (hf embed model=, o4 reasoning family, hf/ollama drop WARN,
byok control-char guard, google truthiness) are each pinned in their own
per-feature test file. This file pins the Round-2 completeness items whose
regression would otherwise be invisible:

* CRITICAL call-site pin — `LlmClient.embed()` end-to-end for the HuggingFace
  `/models/{model}` wire (Round-1's fix was in the embed() CALL SITE; the
  Round-1 per-shaper test exercised `_build_embed_url` in isolation and would
  NOT catch a call-site revert).
* embed() unsupported-wire message enumerates the newly-added wires.
* the per-request `api_key=` override guard rejects DEL + non-ASCII with the
  SAME typed `InvalidApiKeyOverride` (never an opaque `UnicodeEncodeError`),
  fingerprint-only, and does NOT over-reject valid printable specials.
"""

from __future__ import annotations

import httpx
import pytest
import respx

from kaizen.llm import LlmClient
from kaizen.llm.client import _validate_api_key_override
from kaizen.llm.errors import InvalidApiKeyOverride
from kaizen.llm.http_client import LlmHttpClient, SafeDnsResolver
from kaizen.llm.presets import anthropic_preset, huggingface_preset

_HF_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


class _AllowAllResolver(SafeDnsResolver):
    """Skip the real DNS lookup (test-only) so respx can intercept."""

    __slots__ = ()

    def check_host(self, host: str) -> None:
        return None


@pytest.mark.regression
@pytest.mark.asyncio
@respx.mock
async def test_hf_embed_builds_model_url_end_to_end() -> None:
    """client.embed() against a HuggingFace deployment must reach
    /hf-inference/models/{model}. A regression to `_build_embed_url(path)`
    (missing model=) raises ValueError before any request and fails here."""
    expected_url = f"https://router.huggingface.co/hf-inference/models/{_HF_MODEL}"
    route = respx.post(expected_url).mock(
        return_value=httpx.Response(200, json=[[0.1, 0.2, 0.3]])
    )
    dep = huggingface_preset(api_key="hf_test_key", model=_HF_MODEL)
    client = LlmClient.from_deployment(dep)
    http = LlmHttpClient(deployment_preset=dep.wire.name, resolver=_AllowAllResolver())
    try:
        vectors = await client.embed(["hello"], model=_HF_MODEL, http_client=http)
    finally:
        await http.aclose()
    assert route.called, "HF embed never reached the /models/{model} endpoint"
    assert str(route.calls.last.request.url) == expected_url
    assert vectors == [[0.1, 0.2, 0.3]]


@pytest.mark.regression
@pytest.mark.asyncio
async def test_embed_unsupported_wire_message_lists_cohere_and_hf() -> None:
    """A wire with no _EMBED_DISPATCH entry (AnthropicMessages) raises with a
    message enumerating the supported wires, incl. the two added this wave."""
    dep = anthropic_preset(api_key="sk-ant-test", model="claude-haiku-4-5")
    client = LlmClient.from_deployment(dep)
    with pytest.raises(NotImplementedError) as exc:
        await client.embed(["x"], model="text-embedding-x")
    msg = str(exc.value)
    assert "CohereGenerate" in msg
    assert "HuggingFaceInference" in msg


@pytest.mark.regression
def test_api_key_override_rejects_del_char() -> None:
    with pytest.raises(InvalidApiKeyOverride) as exc:
        _validate_api_key_override("sk-good\x7fbad")
    # Fingerprint-only: the raw key never appears in the message.
    assert "sk-good" not in str(exc.value)
    assert "\x7f" not in str(exc.value)


@pytest.mark.regression
def test_api_key_override_rejects_non_ascii_with_typed_error() -> None:
    # A non-ASCII key must raise the SAME typed error, NOT a raw
    # UnicodeEncodeError from httpx's ascii header-encode downstream.
    with pytest.raises(InvalidApiKeyOverride) as exc:
        _validate_api_key_override("sk-café-key")
    assert "caf" not in str(exc.value)


@pytest.mark.regression
def test_api_key_override_accepts_valid_printable_specials() -> None:
    # Printable non-alphanumerics (@ # $ - _ .) are valid credential chars —
    # the guard must NOT over-reject them.
    key = "sk-Ab9_.-@#$%wxyz"
    assert _validate_api_key_override(key) == key

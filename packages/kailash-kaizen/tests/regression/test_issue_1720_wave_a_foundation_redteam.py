"""#1720 Wave-A foundation holistic-redteam regression tests.

A holistic red-team of the MERGED Waves 1+2+A four-axis foundation (run before
the Wave-B consumer cutover) surfaced three genuine defects in already-shipped
code. Each is fixed and pinned here behaviorally (call + assert, never
source-grep — ``rules/testing.md``).

F1 — ``legacy_tool_choice_default`` was stream-BLIND: it returned openai's
     non-stream chat default ("required") even for streaming calls, whereas
     legacy ``OpenAIProvider.stream_chat`` sends "auto". A streaming tool-using
     openai agent therefore diverged from legacy (the exact false-divergence
     class Wave-A's tool_choice fix targets). Fixed: the helper is now
     stream-aware and the node threads the live request's ``streaming`` mode
     into the dual-run shadow.

F2 — ``EmbedOptions.normalize`` was a silent no-op on the HuggingFace embed
     wire: ``LlmClient.embed`` called ``shaper.parse_response(payload_json)``
     WITHOUT the ``options`` argument, so the HF shaper's L2-normalization
     never fired (``rules/zero-tolerance.md`` Rule 3c — documented kwarg with
     zero effect). Fixed: ``options`` is threaded into the embed parse site.

BYOK — a per-request ``api_key`` supplied to ``resolve_deployment_for`` was
     installed directly into an HTTP header (via ``ApiKeyBearer.apply``) with
     NO control-char / CRLF validation, while the sibling BYOK entry point
     ``LlmClient.complete(api_key=)`` fail-closes on exactly that input. An
     enforcement-surface-parity gap (``rules/security.md``). Fixed:
     ``resolve_deployment_for`` routes a caller-supplied override through the
     same shared ``_validate_api_key_override``.
"""

import math

import httpx
import pytest

from kaizen.llm.client import InvalidApiKeyOverride, LlmClient
from kaizen.llm.deployment import EmbedOptions
from kaizen.llm.deployment_resolver import (
    legacy_tool_choice_default,
    resolve_deployment_for,
)
from kaizen.llm.presets import huggingface_preset
from kaizen.nodes.ai.llm_agent import _legacy_tool_choice_default

_TOOLS = [{"type": "function", "function": {"name": "x", "parameters": {}}}]


# ---------------------------------------------------------------------------
# F1 — streaming tool_choice parity
# ---------------------------------------------------------------------------


def test_openai_stream_tool_choice_is_auto_non_stream_is_required():
    """openai is the ONLY provider whose legacy stream default differs:
    ``stream_chat`` -> "auto", ``chat`` -> "required"."""
    assert (
        legacy_tool_choice_default("openai", _TOOLS, None, stream=False) == "required"
    )
    assert legacy_tool_choice_default("openai", _TOOLS, None, stream=True) == "auto"


def test_azure_docker_tool_choice_auto_regardless_of_stream():
    """azure/azure_openai/docker send "auto" on BOTH the chat and stream_chat
    paths — the stream flag must NOT change their result."""
    for provider in ("azure", "azure_openai", "docker"):
        assert (
            legacy_tool_choice_default(provider, _TOOLS, None, stream=False) == "auto"
        )
        assert legacy_tool_choice_default(provider, _TOOLS, None, stream=True) == "auto"


def test_stream_flag_defaults_false_byte_neutral():
    """Omitting ``stream`` reproduces the pre-fix behavior exactly, so every
    existing (non-streaming) caller is byte-identical."""
    assert legacy_tool_choice_default("openai", _TOOLS, None) == "required"
    assert legacy_tool_choice_default("azure", _TOOLS, None) == "auto"
    assert legacy_tool_choice_default("cohere", _TOOLS, None) is None


def test_explicit_choice_honored_even_when_streaming():
    assert legacy_tool_choice_default("openai", _TOOLS, "none", stream=True) == "none"


def test_no_tools_returns_none_even_when_streaming():
    assert legacy_tool_choice_default("openai", None, None, stream=True) is None
    assert legacy_tool_choice_default("openai", [], None, stream=True) is None


def test_llm_agent_wrapper_threads_stream():
    """The node-level seam ``_legacy_tool_choice_default`` (patched by the
    shadow) must thread ``stream`` to the shared helper."""
    assert _legacy_tool_choice_default("openai", _TOOLS, None, stream=True) == "auto"
    assert (
        _legacy_tool_choice_default("openai", _TOOLS, None, stream=False) == "required"
    )
    # default remains non-stream
    assert _legacy_tool_choice_default("openai", _TOOLS, None) == "required"


# ---------------------------------------------------------------------------
# F2 — EmbedOptions.normalize threaded into the HuggingFace embed wire
# ---------------------------------------------------------------------------


class _CannedEmbedHttp:
    """Minimal ``LlmHttpClient`` stub returning a FIXED embeddings body, so the
    test exercises ``LlmClient.embed``'s option-threading (the F2 fix site) end
    to end — NOT the shaper in isolation (which already normalized correctly)."""

    def __init__(self, body):
        self._body = body

    async def post(self, url, **kwargs):
        return httpx.Response(200, json=self._body, request=httpx.Request("POST", url))

    async def aclose(self):
        return None


@pytest.mark.asyncio
async def test_client_embed_threads_normalize_option_to_hf_wire():
    """``EmbedOptions(normalize=True)`` MUST reach the HF shaper THROUGH
    ``client.embed`` (was dropped before F2 — a silent no-op)."""
    dep = huggingface_preset(
        api_key="hf_x", model="sentence-transformers/all-MiniLM-L6-v2"
    )
    client = LlmClient.from_deployment(dep)

    vectors = await client.embed(
        ["x"],
        options=EmbedOptions(normalize=True),
        http_client=_CannedEmbedHttp([[3.0, 4.0]]),
    )
    v = vectors[0]
    # [3, 4] L2-normalized -> [0.6, 0.8]; magnitude 1.0
    assert math.isclose(math.hypot(v[0], v[1]), 1.0, rel_tol=1e-9)
    assert math.isclose(v[0], 0.6, rel_tol=1e-9)
    assert math.isclose(v[1], 0.8, rel_tol=1e-9)


@pytest.mark.asyncio
async def test_client_embed_no_normalize_is_byte_neutral():
    """Omitting normalize leaves the raw vector untouched (F2 fix is
    behavior-neutral when the option is not set)."""
    dep = huggingface_preset(
        api_key="hf_x", model="sentence-transformers/all-MiniLM-L6-v2"
    )
    client = LlmClient.from_deployment(dep)

    vectors = await client.embed(["x"], http_client=_CannedEmbedHttp([[3.0, 4.0]]))
    assert vectors[0] == [3.0, 4.0]


# ---------------------------------------------------------------------------
# BYOK — control-char / CRLF api_key rejected at resolve_deployment_for
# (enforcement-surface parity with LlmClient.complete(api_key=))
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad_key",
    [
        "sk-good\r\nX-Injected: value",  # CRLF header-injection primitive
        "sk-good\nbad",  # bare LF
        "sk-good\x00bad",  # NUL (C0)
        "sk-good\x7fbad",  # DEL
        "sk-café",  # non-ASCII (cannot be a valid header credential)
    ],
)
def test_resolve_deployment_rejects_malformed_byok_key(bad_key):
    """A per-request BYOK key with a control char / CRLF / non-ASCII must
    fail closed on the resolve_deployment_for path, exactly as it does on the
    complete(api_key=) path — same shared validator, same typed error."""
    with pytest.raises(InvalidApiKeyOverride):
        resolve_deployment_for("openai", "gpt-x", api_key=bad_key)


def test_resolve_deployment_azure_byok_path_also_guarded():
    """The azure branch installs the key into an ``api-key`` header via
    AzureEntra — it MUST be guarded too (validation runs before the branch)."""
    with pytest.raises(InvalidApiKeyOverride):
        resolve_deployment_for(
            "azure",
            "my-deployment",
            api_key="k\r\nX-Injected: 1",
            base_url="https://x.openai.azure.com",
        )


def test_resolve_deployment_accepts_valid_byok_key():
    """A clean ASCII key still resolves — no false rejection, byte-preserving."""
    dep = resolve_deployment_for("openai", "gpt-x", api_key="sk-valid-ASCII-key-123")
    assert dep is not None

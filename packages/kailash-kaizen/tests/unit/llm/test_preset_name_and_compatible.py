# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Tests for `preset_name` retrofit + new compatible-endpoint presets.

Covers terrene-foundation/kailash-py#761 (`openai_compatible`) and
terrene-foundation/kailash-py#762 (`anthropic_compatible`), and the
`preset_name` field added to `LlmDeployment` in the same PR. Cross-SDK
parity with kailash-rs PR #722 / PR #724.

Per `rules/zero-tolerance.md` Rule 6 (Implement Fully): the new
`preset_name` field is wired into ALL existing presets in the same PR,
not only the new compatible variants — leaving the field as ``None``
for established presets would ship a half-implemented public contract.
"""

from __future__ import annotations

import pytest

from kaizen.llm.auth.bearer import ApiKeyBearer, ApiKeyHeaderKind
from kaizen.llm.deployment import LlmDeployment, WireProtocol
from kaizen.llm.errors import InvalidEndpoint
from kaizen.llm.presets import (
    anthropic_compatible_preset,
    list_presets,
    openai_compatible_preset,
)

# A non-loopback, DNS-resolvable, RFC-2606 reserved hostname. Used for
# happy-path construction; we never make a real HTTP request to it.
_RESOLVABLE_HOST = "https://example.com"


# ---------------------------------------------------------------------------
# `openai_compatible` preset (#761)
# ---------------------------------------------------------------------------


def test_openai_compatible_preset_shape() -> None:
    d = LlmDeployment.openai_compatible(_RESOLVABLE_HOST + "/v1", "sk-test")
    assert d.wire == WireProtocol.OpenAiChat
    assert d.preset_name == "openai_compatible"
    assert str(d.endpoint.base_url).startswith("https://example.com")
    assert isinstance(d.auth, ApiKeyBearer)
    assert d.auth.kind == ApiKeyHeaderKind.Authorization_Bearer
    # default_model is intentionally unset for compatible presets — the
    # caller pins per-request via ResolvedModel.
    assert d.default_model is None


def test_openai_compatible_classmethod_matches_free_function() -> None:
    cm = LlmDeployment.openai_compatible(_RESOLVABLE_HOST, "sk-test")
    fn = openai_compatible_preset(_RESOLVABLE_HOST, "sk-test")
    assert cm.wire == fn.wire
    assert cm.preset_name == fn.preset_name == "openai_compatible"


def test_openai_compatible_rejects_empty_base_url() -> None:
    with pytest.raises(ValueError, match=r"base_url"):
        LlmDeployment.openai_compatible("", "sk-test")


def test_openai_compatible_rejects_empty_api_key() -> None:
    with pytest.raises(ValueError, match=r"OPENAI_COMPATIBLE_API_KEY|api_key"):
        LlmDeployment.openai_compatible(_RESOLVABLE_HOST, "")


@pytest.mark.parametrize(
    "blocked_url",
    [
        "http://127.0.0.1",  # loopback (literal IP)
        # NB: `http://localhost` (named) is intentionally allowed by the
        # SSRF guard for local-server presets (ollama, lm_studio) — only
        # literal-IP loopback is rejected.
        "http://10.0.0.5",  # RFC1918 private
        "http://192.168.1.1",  # RFC1918 private
        "http://169.254.169.254",  # AWS / GCP / Azure cloud metadata
        "http://fd00::1",  # IPv6 ULA
        "ftp://example.com",  # non-HTTP(S) scheme
    ],
)
def test_openai_compatible_ssrf_guard_rejects(blocked_url: str) -> None:
    """SSRF guard runs on Endpoint.base_url for the new compatible presets.

    Spec § 5.1 + spec § 6.M2: compatible presets MUST inherit the same
    SSRF guard as the rest of the deployment surface — loopback,
    private, link-local, cloud metadata, and non-HTTP(S) URLs are
    rejected at construction.
    """
    with pytest.raises(InvalidEndpoint):
        LlmDeployment.openai_compatible(blocked_url, "sk-test")


# ---------------------------------------------------------------------------
# `anthropic_compatible` preset (#762)
# ---------------------------------------------------------------------------


def test_anthropic_compatible_preset_shape() -> None:
    d = LlmDeployment.anthropic_compatible(_RESOLVABLE_HOST, "sk-test")
    assert d.wire == WireProtocol.AnthropicMessages
    assert d.preset_name == "anthropic_compatible"
    assert isinstance(d.auth, ApiKeyBearer)
    assert d.auth.kind == ApiKeyHeaderKind.X_Api_Key
    assert d.default_model is None
    # `anthropic-version` MUST be set on required_headers (default 2023-06-01).
    assert d.endpoint.required_headers.get("anthropic-version") == "2023-06-01"


def test_anthropic_compatible_accepts_custom_anthropic_version() -> None:
    d = anthropic_compatible_preset(
        _RESOLVABLE_HOST, "sk-test", anthropic_version="2024-09-01"
    )
    assert d.endpoint.required_headers["anthropic-version"] == "2024-09-01"


def test_anthropic_compatible_rejects_empty_base_url() -> None:
    with pytest.raises(ValueError, match=r"base_url"):
        LlmDeployment.anthropic_compatible("", "sk-test")


def test_anthropic_compatible_rejects_empty_api_key() -> None:
    with pytest.raises(ValueError, match=r"ANTHROPIC_COMPATIBLE_API_KEY|api_key"):
        LlmDeployment.anthropic_compatible(_RESOLVABLE_HOST, "")


@pytest.mark.parametrize(
    "blocked_url",
    [
        "http://127.0.0.1",
        "http://10.0.0.5",
        "http://169.254.169.254",
        "ftp://example.com",
    ],
)
def test_anthropic_compatible_ssrf_guard_rejects(blocked_url: str) -> None:
    with pytest.raises(InvalidEndpoint):
        LlmDeployment.anthropic_compatible(blocked_url, "sk-test")


# ---------------------------------------------------------------------------
# Preset name retrofit (cross-cutting — verifies every existing preset
# returns its canonical literal). Same-bug-class fix-immediately per
# `rules/autonomous-execution.md` MUST Rule 4 — without retrofit, the
# capability matrix in PR-B (#763) cannot reliably look up presets.
# ---------------------------------------------------------------------------


def test_preset_name_field_present_on_all_constructions() -> None:
    """`LlmDeployment.preset_name` is set to the canonical literal for
    every preset that admits a no-side-effect smoke construction.

    Bedrock / Vertex / Azure presets need region / auth-instance kwargs
    that aren't smoke-testable here; their retrofit is verified by the
    helper-internal `preset_name=` keyword to `_build_*_deployment`,
    which threads to `LlmDeployment(preset_name=...)`. Coverage at the
    helper level is structural (the helpers have no other code path).
    """
    cases = [
        # (preset_name, callable form, kwargs for happy-path construction)
        ("openai", LlmDeployment.openai, {"api_key": "sk-test", "model": "m"}),
        ("anthropic", LlmDeployment.anthropic, {"api_key": "sk-test", "model": "m"}),
        ("google", LlmDeployment.google, {"api_key": "sk-test", "model": "m"}),
        ("cohere", LlmDeployment.cohere, {"api_key": "sk-test", "model": "m"}),
        ("mistral", LlmDeployment.mistral, {"api_key": "sk-test", "model": "m"}),
        ("perplexity", LlmDeployment.perplexity, {"api_key": "sk-test", "model": "m"}),
        (
            "huggingface",
            LlmDeployment.huggingface,
            {"api_key": "sk-test", "model": "m"},
        ),
        ("groq", LlmDeployment.groq, {"api_key": "sk-test", "model": "m"}),
        ("together", LlmDeployment.together, {"api_key": "sk-test", "model": "m"}),
        ("fireworks", LlmDeployment.fireworks, {"api_key": "sk-test", "model": "m"}),
        ("openrouter", LlmDeployment.openrouter, {"api_key": "sk-test", "model": "m"}),
        ("deepseek", LlmDeployment.deepseek, {"api_key": "sk-test", "model": "m"}),
        (
            "ollama",
            LlmDeployment.ollama,
            {"base_url": "http://localhost:11434", "model": "m"},
        ),
        (
            "docker_model_runner",
            LlmDeployment.docker_model_runner,
            {"base_url": "http://localhost:12434", "model": "m"},
        ),
        (
            "lm_studio",
            LlmDeployment.lm_studio,
            {"base_url": "http://localhost:1234", "model": "m"},
        ),
        (
            "llama_cpp",
            LlmDeployment.llama_cpp,
            {"base_url": "http://localhost:8080", "model": "m"},
        ),
    ]
    for canonical_name, factory, kwargs in cases:
        d = factory(**kwargs)
        assert d.preset_name == canonical_name, (
            f"preset {canonical_name!r} retrofit incomplete: "
            f"got preset_name={d.preset_name!r}"
        )


def test_bedrock_claude_preset_name_threads_through_standalone_path() -> None:
    """`bedrock_claude` is the only Bedrock preset on a non-helper code
    path — verify directly. Other Bedrock families (`bedrock_llama`,
    `bedrock_titan`, `bedrock_mistral`, `bedrock_cohere`) all share the
    `_build_bedrock_deployment` helper which threads `preset_name`
    through structurally; the helper IS a single code path so verifying
    one variant proves the whole family.
    """
    d = LlmDeployment.bedrock_claude(
        api_key="test-tok", region="us-east-1", model="claude-sonnet-4-6"
    )
    assert d.preset_name == "bedrock_claude"


def test_compatible_presets_appear_in_registry() -> None:
    """Both new presets MUST be reachable via the registry, not only via
    the classmethod surface — this is the contract `rules/orphan-detection.md`
    Rule 1 protects (every facade has a registered call site).
    """
    presets = list_presets()
    assert "openai_compatible" in presets
    assert "anthropic_compatible" in presets


def test_total_preset_count_after_retrofit() -> None:
    """Lock the registry size so future regressions surface loudly.

    Composition (cumulative across releases):

    * S1 + 15 S3 (direct providers) + 4 S4b (bedrock non-claude) + 1 S4a
      (bedrock claude) + 2 S5 (vertex) + 1 S6 (azure openai) +
      `azure_entra` factory registered via S6 = 24 (pre-2.15.0 baseline).
    * + 2 compatible presets (`openai_compatible`, `anthropic_compatible`,
      #761 / #762) shipped in 2.15.0 → 26.
    * + 4 default-URL convenience presets (`ollama_default`,
      `lm_studio_default`, `llama_cpp_default`,
      `docker_model_runner_default`, #787) shipped in 2.16.2 → 30.
    * + 12 `<provider>_from_env` convenience presets (#791) for OpenAI,
      Anthropic, Google, Cohere, Mistral, Perplexity, HuggingFace, Groq,
      Together, Fireworks, OpenRouter, DeepSeek → 42.
    * + 1 `huggingface_chat` chat-schema-routing preset (#1720 F3) → 43.
    * + 1 `azure_ai_foundry` four-axis preset (#1892 -- the unified,
      model-agnostic Azure AI Foundry model-inference wire, replacing the
      legacy `AzureAIFoundryProvider`) → 44.

    NB: `azure_entra` is registered as a preset name even though it is
    really an auth-strategy factory; this is pre-existing in the kaizen
    LLM surface. If a future cleanup removes it, decrement this count.
    """
    assert len(list_presets()) == 44

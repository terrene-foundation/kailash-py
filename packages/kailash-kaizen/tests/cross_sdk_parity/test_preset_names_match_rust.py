# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Cross-SDK parity: preset names match Rust literals byte-for-byte (#498 S9).

Per specs/kaizen-llm-deployments.md § Cross-SDK Parity, the following
MUST be byte-identical between kailash-py and kailash-rs:

* Preset names (24 byte-identical cross-SDK names in RUST_PRESET_NAMES; the
  18 Python-idiom convenience presets in _PYTHON_CONVENIENCE_PRESETS extend the
  registry with capability-parity, cross-SDK-verified by the sibling tests)
* Region allowlist (BEDROCK_SUPPORTED_REGIONS)
* Scope constants (CLOUD_PLATFORM_SCOPE, COGNITIVE_SERVICES_SCOPE)
* Default api-version (AZURE_OPENAI_DEFAULT_API_VERSION)
* auth_strategy_kind() labels
* grammar_kind() labels
"""

from __future__ import annotations

from kaizen.llm.presets import list_presets


# Source of truth: the exact preset-name literals shipped in
# kailash-rs/crates/kailash-kaizen/src/llm/deployment/presets.rs.
# Any drift between this tuple and the Rust SDK is a cross-SDK parity
# violation (EATP D6: independent implementation, matching semantics).
RUST_PRESET_NAMES = frozenset(
    {
        # Direct providers (S3)
        "openai",
        "anthropic",
        "google",
        "cohere",
        "mistral",
        "perplexity",
        "huggingface",
        "ollama",
        "docker_model_runner",
        "groq",
        "together",
        "fireworks",
        "openrouter",
        "deepseek",
        "lm_studio",
        "llama_cpp",
        # Bedrock (S4a + S4b-ii)
        "bedrock_claude",
        "bedrock_llama",
        "bedrock_titan",
        "bedrock_mistral",
        "bedrock_cohere",
        # Vertex (S5)
        "vertex_claude",
        "vertex_gemini",
        # Azure (S6)
        "azure_openai",
    }
)


# Python-idiom convenience presets. These extend the byte-identical cross-SDK
# catalog above with Python-registry-idiom names, and their cross-SDK CAPABILITY
# parity is independently pinned by the sibling parity tests (each name maps to a
# Rust classmethod per EATP D6 — the suffix is the Python idiom difference):
#   * `<provider>_from_env`  → Rust zero-arg `<provider>()`  — test_from_env_presets.py::_FROM_ENV_PRESETS_RUST_PARITY
#   * `<provider>_default`   → Rust `<provider>_default()`    — test_default_url_presets.py::_DEFAULT_URL_PRESETS_RUST_PARITY
#   * `<provider>_compatible`→ Rust `<provider>_compatible()` — test_preset_name_and_compatible.py (#761/#762)
# They are NOT byte-identical top-level preset NAMES (so they are excluded from
# RUST_PRESET_NAMES), but they ARE an accounted-for, cross-SDK-verified extension
# of `list_presets()` — not rogue Python-only leaks. Any preset OUTSIDE both sets
# is an unexpected leak and MUST fail (see test below).
_PYTHON_CONVENIENCE_PRESETS = frozenset(
    {
        # <provider>_from_env (12)
        "openai_from_env",
        "anthropic_from_env",
        "google_from_env",
        "cohere_from_env",
        "mistral_from_env",
        "perplexity_from_env",
        "huggingface_from_env",
        "groq_from_env",
        "together_from_env",
        "fireworks_from_env",
        "openrouter_from_env",
        "deepseek_from_env",
        # <provider>_default (4)
        "ollama_default",
        "lm_studio_default",
        "llama_cpp_default",
        "docker_model_runner_default",
        # <provider>_compatible (2)
        "openai_compatible",
        "anthropic_compatible",
    }
)


# Presets NEW to the Python SDK whose Rust sibling is a PENDING cross-repo issue
# (rules/cross-sdk-inspection.md Rule 1). These are NOT drift/leaks — they are a
# genuine capability the Python SDK gained first; the Rust equivalent MUST be
# filed against the Rust SDK BUILD repo (surfaced by the orchestrator for user
# authorization — this session does NOT self-file cross-repo). Each entry names
# the originating issue; the entry moves into RUST_PRESET_NAMES once the Rust
# sibling lands with a byte-identical preset name.
#
#   * `huggingface_chat` (#1720 F3) — HuggingFace router OpenAI-compatible
#     chat-completions schema routing (`/v1/chat/completions` + `use_chat_schema`
#     body transform), reaching tool-calling that the classic `huggingface`
#     preset's `/models/{model}` text-generation path drops. Rust sibling: a
#     PENDING HF chat-schema-routing preset on the Rust SDK.
#   * `azure_ai_foundry` (#1892) — four-axis Azure AI Foundry unified
#     model-inference wire (`/models/chat/completions` + `api-key` auth),
#     distinct from `azure_openai`'s `/openai/deployments/{deployment}` path;
#     the Python SDK gained it first (#1720 legacy-provider consolidation, the
#     four-axis replacement for the removed legacy `AzureAIFoundryProvider`).
#     Rust sibling: a PENDING four-axis azure_ai_foundry preset on the Rust SDK.
_PENDING_RUST_PARITY_PRESETS = frozenset(
    {
        "huggingface_chat",
        "azure_ai_foundry",
    }
)


def test_every_rust_preset_is_registered_in_python() -> None:
    """Every preset in the Rust literal is registered in the Python SDK."""
    py_presets = set(list_presets())
    missing = RUST_PRESET_NAMES - py_presets
    assert not missing, (
        f"Python SDK is missing {len(missing)} preset(s) present in Rust: "
        f"{sorted(missing)}. Cross-SDK parity violated."
    )


def test_no_unexpected_presets_leak_public_surface() -> None:
    """Python registers NO preset outside the two accounted-for sets.

    Every registered preset MUST be either (a) a byte-identical cross-SDK
    name in RUST_PRESET_NAMES, or (b) a documented Python-idiom convenience
    preset in _PYTHON_CONVENIENCE_PRESETS (whose cross-SDK CAPABILITY parity
    is pinned by the sibling parity tests). Anything else is a genuine
    Python-only leak that would silently break on Rust port.
    """
    py_presets = set(list_presets())
    accounted = (
        RUST_PRESET_NAMES | _PYTHON_CONVENIENCE_PRESETS | _PENDING_RUST_PARITY_PRESETS
    )
    unexpected = py_presets - accounted
    assert not unexpected, (
        f"Python SDK has {len(unexpected)} UNEXPECTED preset(s) accounted for "
        f"in none of RUST_PRESET_NAMES / _PYTHON_CONVENIENCE_PRESETS / "
        f"_PENDING_RUST_PARITY_PRESETS: {sorted(unexpected)}. Add to the Rust "
        f"catalog + RUST_PRESET_NAMES, or to the documented convenience family "
        f"(+ its sibling parity test), or to the pending-Rust-parity set (+ a "
        f"filed cross-repo issue), or remove from Python."
    )


def test_preset_registry_size_matches_catalog() -> None:
    """Strict count check — the three accounted-for sets are pairwise disjoint
    and their union is the full registry (no silent add/remove of any preset)."""
    assert len(RUST_PRESET_NAMES) == 24
    assert len(_PYTHON_CONVENIENCE_PRESETS) == 18
    assert len(_PENDING_RUST_PARITY_PRESETS) == 2
    assert not (
        RUST_PRESET_NAMES & _PYTHON_CONVENIENCE_PRESETS
    ), "a preset appears in BOTH the byte-identical and convenience sets"
    assert not (
        (RUST_PRESET_NAMES | _PYTHON_CONVENIENCE_PRESETS) & _PENDING_RUST_PARITY_PRESETS
    ), "a pending-Rust-parity preset also appears in an accounted-for set"
    assert len(list_presets()) == (
        len(RUST_PRESET_NAMES)
        + len(_PYTHON_CONVENIENCE_PRESETS)
        + len(_PENDING_RUST_PARITY_PRESETS)
    )


def test_cloud_platform_scope_matches_rust() -> None:
    """GCP scope literal is cross-SDK stable."""
    from kaizen.llm.auth.gcp import CLOUD_PLATFORM_SCOPE

    assert CLOUD_PLATFORM_SCOPE == "https://www.googleapis.com/auth/cloud-platform"


def test_cognitive_services_scope_matches_rust() -> None:
    """Azure Entra audience scope is cross-SDK stable."""
    from kaizen.llm.auth.azure import COGNITIVE_SERVICES_SCOPE

    assert COGNITIVE_SERVICES_SCOPE == "https://cognitiveservices.azure.com/.default"


def test_azure_openai_default_api_version_matches_rust() -> None:
    """Pinned default Azure api-version stays cross-SDK stable."""
    from kaizen.llm.presets import AZURE_OPENAI_DEFAULT_API_VERSION

    assert AZURE_OPENAI_DEFAULT_API_VERSION == "2024-06-01"


def test_bedrock_supported_regions_cross_sdk_contract() -> None:
    """Region allowlist shape is stable; operators expect the same regions
    to work against both SDKs."""
    from kaizen.llm.auth.aws import BEDROCK_SUPPORTED_REGIONS

    # Every region MUST match the AWS region shape (e.g. us-east-1).
    import re

    aws_region_re = re.compile(r"^[a-z]{2,3}-[a-z]+(-[a-z]+)?-\d{1,2}$")
    for region in BEDROCK_SUPPORTED_REGIONS:
        assert aws_region_re.match(
            region
        ), f"BEDROCK_SUPPORTED_REGIONS contains non-canonical region: {region!r}"
    # At least the core US regions MUST be present.
    assert "us-east-1" in BEDROCK_SUPPORTED_REGIONS
    assert "us-west-2" in BEDROCK_SUPPORTED_REGIONS


def test_auth_strategy_kind_labels_cross_sdk() -> None:
    """auth_strategy_kind() labels match Rust byte-for-byte."""
    from kaizen.llm.auth.aws import AwsBearerToken
    from kaizen.llm.auth.azure import AzureEntra
    from kaizen.llm.auth.bearer import ApiKey, ApiKeyBearer, ApiKeyHeaderKind

    api_key_bearer = ApiKeyBearer(
        kind=ApiKeyHeaderKind.Authorization_Bearer, key=ApiKey("test")
    )
    # api-key labels
    assert api_key_bearer.auth_strategy_kind() == "api_key"

    # Azure api-key variant
    azure_api_key = AzureEntra(api_key="test")
    assert azure_api_key.auth_strategy_kind() == "azure_entra_api_key"


def test_grammar_kind_labels_cross_sdk() -> None:
    """grammar_kind() labels match Rust byte-for-byte."""
    from kaizen.llm.grammar.azure_openai import AzureOpenAIGrammar
    from kaizen.llm.grammar.bedrock import (
        BedrockClaudeGrammar,
        BedrockCohereGrammar,
        BedrockLlamaGrammar,
        BedrockMistralGrammar,
        BedrockTitanGrammar,
    )
    from kaizen.llm.grammar.vertex import VertexClaudeGrammar, VertexGeminiGrammar

    assert BedrockClaudeGrammar().grammar_kind() == "bedrock_claude"
    assert BedrockLlamaGrammar().grammar_kind() == "bedrock_llama"
    assert BedrockTitanGrammar().grammar_kind() == "bedrock_titan"
    assert BedrockMistralGrammar().grammar_kind() == "bedrock_mistral"
    assert BedrockCohereGrammar().grammar_kind() == "bedrock_cohere"
    assert VertexClaudeGrammar().grammar_kind() == "vertex_claude"
    assert VertexGeminiGrammar().grammar_kind() == "vertex_gemini"
    assert AzureOpenAIGrammar().grammar_kind() == "azure_openai"

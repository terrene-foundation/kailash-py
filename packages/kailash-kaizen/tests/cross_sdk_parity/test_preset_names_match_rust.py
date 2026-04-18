# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Cross-SDK parity: preset names match Rust literals byte-for-byte (#498 S9).

Per specs/kaizen-llm-deployments.md § Cross-SDK Parity, the following
MUST be byte-identical between kailash-py and kailash-rs:

* Preset names (25 primary presets)
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


def test_every_rust_preset_is_registered_in_python() -> None:
    """Every preset in the Rust literal is registered in the Python SDK."""
    py_presets = set(list_presets())
    missing = RUST_PRESET_NAMES - py_presets
    assert not missing, (
        f"Python SDK is missing {len(missing)} preset(s) present in Rust: "
        f"{sorted(missing)}. Cross-SDK parity violated."
    )


def test_no_python_only_presets_leak_public_surface() -> None:
    """Python SDK registers NO presets beyond the Rust catalog.

    Python-specific additions (ollama helpers, etc.) belong in a separate
    namespace or behind a feature flag, never in the primary preset
    registry — otherwise code written against Python silently breaks on
    Rust port.
    """
    py_presets = set(list_presets())
    extras = py_presets - RUST_PRESET_NAMES
    assert not extras, (
        f"Python SDK has {len(extras)} extra preset(s) not in Rust: "
        f"{sorted(extras)}. These MUST be added to Rust or removed from Python."
    )


def test_preset_registry_size_matches_rust_catalog() -> None:
    """Strict count check — 24 primary presets total (no silent add/remove)."""
    assert len(RUST_PRESET_NAMES) == 24
    assert len(list_presets()) == len(RUST_PRESET_NAMES)


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

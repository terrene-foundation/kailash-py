# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Session 2 (S3) — shape tests for every direct-provider preset.

Invariant 1: every preset registered in ``_PRESETS`` has a snake_case name
that matches the Rust SDK's literal exactly.

Invariant 2: every preset constructs a non-frozen-failing ``LlmDeployment``
with the correct wire protocol, endpoint, and auth strategy.

Invariant 3: model is REQUIRED on every preset. Empty / None / missing
raises a typed error at construction time (never a silent default).

Follows the shape of ``test_deployment_openai_preset.py`` — one test per
provider covering happy-path + negative cases.
"""

from __future__ import annotations

import pytest

from kaizen.llm.auth.bearer import ApiKeyBearer, ApiKeyHeaderKind, StaticNone
from kaizen.llm.deployment import Endpoint, LlmDeployment, WireProtocol
from kaizen.llm.presets import (
    anthropic_preset,
    cohere_preset,
    deepseek_preset,
    docker_model_runner_preset,
    fireworks_preset,
    google_preset,
    groq_preset,
    huggingface_preset,
    list_presets,
    llama_cpp_preset,
    lm_studio_preset,
    mistral_preset,
    ollama_preset,
    openrouter_preset,
    perplexity_preset,
    together_preset,
)

# ---------------------------------------------------------------------------
# Cross-SDK parity: preset names match the Rust literals byte-for-byte
# ---------------------------------------------------------------------------

# Source of truth: kailash-rs specs/llm-deployments.md preset table. Any
# rename here requires a coordinated cross-SDK edit + parity fixture.
_S3_PRESET_NAMES_RUST_PARITY = frozenset(
    {
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
    }
)


def test_s3_preset_names_match_rust_spec_literal() -> None:
    """Every S3 preset name MUST byte-match the Rust SDK spec literal.

    Invariant 1 from the session todo. Failure here means Python and Rust
    callers would have to translate preset names between SDKs, breaking
    the "same name, same shape" cross-SDK contract.
    """
    registered = set(list_presets())
    missing = _S3_PRESET_NAMES_RUST_PARITY - registered
    assert not missing, (
        f"S3 presets missing from registry: {sorted(missing)}. "
        f"Every preset in the Rust spec MUST be registered in Python."
    )


# ---------------------------------------------------------------------------
# Anthropic
# ---------------------------------------------------------------------------


def test_anthropic_preset_shape() -> None:
    d = LlmDeployment.anthropic("sk-test", model="claude-3-5-sonnet-20241022")
    assert isinstance(d, LlmDeployment)
    assert d.wire == WireProtocol.AnthropicMessages
    assert isinstance(d.endpoint, Endpoint)
    assert str(d.endpoint.base_url).startswith("https://api.anthropic.com")
    assert d.endpoint.path_prefix == "/v1"
    assert d.endpoint.required_headers.get("anthropic-version") == "2023-06-01"
    assert d.default_model == "claude-3-5-sonnet-20241022"
    assert isinstance(d.auth, ApiKeyBearer)
    assert d.auth.kind == ApiKeyHeaderKind.X_Api_Key


def test_anthropic_preset_rejects_empty_api_key() -> None:
    with pytest.raises(ValueError):
        LlmDeployment.anthropic("", model="claude-3-5-sonnet-20241022")


def test_anthropic_preset_rejects_empty_model() -> None:
    with pytest.raises(ValueError, match=r"ANTHROPIC_PROD_MODEL"):
        LlmDeployment.anthropic("sk-test", model="")


def test_anthropic_preset_rejects_missing_model_positional() -> None:
    with pytest.raises(TypeError):
        LlmDeployment.anthropic("sk-test")  # type: ignore[call-arg]


def test_anthropic_preset_free_function_matches_classmethod() -> None:
    cls_form = LlmDeployment.anthropic("sk-test", model="claude-3-5-sonnet-20241022")
    fn_form = anthropic_preset("sk-test", model="claude-3-5-sonnet-20241022")
    assert cls_form.wire == fn_form.wire
    assert cls_form.default_model == fn_form.default_model


# ---------------------------------------------------------------------------
# Google Gemini
# ---------------------------------------------------------------------------


def test_google_preset_shape() -> None:
    d = LlmDeployment.google("k", model="gemini-2.0-flash")
    assert d.wire == WireProtocol.GoogleGenerateContent
    assert str(d.endpoint.base_url).startswith(
        "https://generativelanguage.googleapis.com"
    )
    assert d.endpoint.path_prefix == "/v1beta"
    assert d.default_model == "gemini-2.0-flash"
    assert isinstance(d.auth, ApiKeyBearer)
    assert d.auth.kind == ApiKeyHeaderKind.X_Goog_Api_Key


def test_google_preset_rejects_empty_key() -> None:
    with pytest.raises(ValueError):
        LlmDeployment.google("", model="gemini-2.0-flash")


def test_google_preset_rejects_empty_model() -> None:
    with pytest.raises(ValueError, match=r"GOOGLE_PROD_MODEL"):
        LlmDeployment.google("k", model="")


def test_google_preset_free_function_matches_classmethod() -> None:
    a = LlmDeployment.google("k", model="gemini-2.0-flash")
    b = google_preset("k", model="gemini-2.0-flash")
    assert a.wire == b.wire


# ---------------------------------------------------------------------------
# Cohere
# ---------------------------------------------------------------------------


def test_cohere_preset_shape() -> None:
    d = LlmDeployment.cohere("k", model="command-r-plus")
    assert d.wire == WireProtocol.CohereGenerate
    assert str(d.endpoint.base_url).startswith("https://api.cohere.com")
    assert d.endpoint.path_prefix == "/v1"
    assert d.default_model == "command-r-plus"
    assert isinstance(d.auth, ApiKeyBearer)
    assert d.auth.kind == ApiKeyHeaderKind.Authorization_Bearer


def test_cohere_preset_rejects_empty_key() -> None:
    with pytest.raises(ValueError):
        LlmDeployment.cohere("", model="command-r-plus")


def test_cohere_preset_rejects_empty_model() -> None:
    with pytest.raises(ValueError, match=r"COHERE_PROD_MODEL"):
        LlmDeployment.cohere("k", model="")


def test_cohere_preset_free_function_matches_classmethod() -> None:
    assert (
        cohere_preset("k", model="command-r-plus").wire
        == LlmDeployment.cohere("k", model="command-r-plus").wire
    )


# ---------------------------------------------------------------------------
# Mistral
# ---------------------------------------------------------------------------


def test_mistral_preset_shape() -> None:
    d = LlmDeployment.mistral("k", model="mistral-large-latest")
    assert d.wire == WireProtocol.MistralChat
    assert str(d.endpoint.base_url).startswith("https://api.mistral.ai")
    assert d.endpoint.path_prefix == "/v1"
    assert d.default_model == "mistral-large-latest"
    assert isinstance(d.auth, ApiKeyBearer)
    assert d.auth.kind == ApiKeyHeaderKind.Authorization_Bearer


def test_mistral_preset_rejects_empty_inputs() -> None:
    with pytest.raises(ValueError):
        LlmDeployment.mistral("", model="mistral-large-latest")
    with pytest.raises(ValueError, match=r"MISTRAL_PROD_MODEL"):
        LlmDeployment.mistral("k", model="")


def test_mistral_preset_free_function_matches_classmethod() -> None:
    assert (
        mistral_preset("k", model="mistral-large-latest").wire
        == LlmDeployment.mistral("k", model="mistral-large-latest").wire
    )


# ---------------------------------------------------------------------------
# Perplexity (OpenAI-compatible wire)
# ---------------------------------------------------------------------------


def test_perplexity_preset_shape() -> None:
    d = LlmDeployment.perplexity("k", model="sonar-large-online")
    assert d.wire == WireProtocol.OpenAiChat
    assert str(d.endpoint.base_url).startswith("https://api.perplexity.ai")
    assert d.default_model == "sonar-large-online"
    assert isinstance(d.auth, ApiKeyBearer)
    assert d.auth.kind == ApiKeyHeaderKind.Authorization_Bearer


def test_perplexity_preset_rejects_empty_inputs() -> None:
    with pytest.raises(ValueError):
        LlmDeployment.perplexity("", model="sonar-large-online")
    with pytest.raises(ValueError, match=r"PERPLEXITY_PROD_MODEL"):
        LlmDeployment.perplexity("k", model="")


def test_perplexity_preset_free_function_matches_classmethod() -> None:
    assert (
        perplexity_preset("k", model="sonar-large-online").wire
        == LlmDeployment.perplexity("k", model="sonar-large-online").wire
    )


# ---------------------------------------------------------------------------
# HuggingFace Inference
# ---------------------------------------------------------------------------


def test_huggingface_preset_shape() -> None:
    d = LlmDeployment.huggingface("k", model="meta-llama/Llama-3.1-8B-Instruct")
    assert d.wire == WireProtocol.HuggingFaceInference
    assert str(d.endpoint.base_url).startswith("https://api-inference.huggingface.co")
    assert d.default_model == "meta-llama/Llama-3.1-8B-Instruct"
    assert isinstance(d.auth, ApiKeyBearer)
    assert d.auth.kind == ApiKeyHeaderKind.Authorization_Bearer


def test_huggingface_preset_rejects_empty_inputs() -> None:
    with pytest.raises(ValueError):
        LlmDeployment.huggingface("", model="meta-llama/Llama-3.1-8B-Instruct")
    with pytest.raises(ValueError, match=r"HUGGINGFACE_PROD_MODEL"):
        LlmDeployment.huggingface("k", model="")


def test_huggingface_preset_free_function_matches_classmethod() -> None:
    assert (
        huggingface_preset("k", model="meta-llama/Llama-3.1-8B-Instruct").wire
        == LlmDeployment.huggingface("k", model="meta-llama/Llama-3.1-8B-Instruct").wire
    )


# ---------------------------------------------------------------------------
# Ollama (no-auth, base_url first)
# ---------------------------------------------------------------------------


def test_ollama_preset_shape() -> None:
    d = LlmDeployment.ollama("http://localhost:11434", model="llama3.1:8b")
    assert d.wire == WireProtocol.OllamaNative
    assert str(d.endpoint.base_url).startswith("http://localhost")
    assert d.default_model == "llama3.1:8b"
    assert isinstance(d.auth, StaticNone)


def test_ollama_preset_rejects_empty_base_url() -> None:
    with pytest.raises(ValueError):
        LlmDeployment.ollama("", model="llama3.1:8b")


def test_ollama_preset_rejects_empty_model() -> None:
    with pytest.raises(ValueError, match=r"OLLAMA_PROD_MODEL"):
        LlmDeployment.ollama("http://localhost:11434", model="")


def test_ollama_preset_rejects_missing_model_positional() -> None:
    with pytest.raises(TypeError):
        LlmDeployment.ollama("http://localhost:11434")  # type: ignore[call-arg]


def test_ollama_preset_ssrf_guard_rejects_non_localhost_http() -> None:
    """The SSRF guard in Endpoint.base_url rejects http:// for non-localhost hosts.

    Proves the no-auth Ollama preset cannot be used to reach a non-local
    HTTP endpoint — any such attempt raises at construction, not at send.
    """
    from kaizen.llm.errors import InvalidEndpoint

    with pytest.raises(InvalidEndpoint):
        LlmDeployment.ollama("http://public.example.com:11434", model="llama3.1:8b")


def test_ollama_preset_free_function_matches_classmethod() -> None:
    a = LlmDeployment.ollama("http://localhost:11434", model="llama3.1:8b")
    b = ollama_preset("http://localhost:11434", model="llama3.1:8b")
    assert a.wire == b.wire


# ---------------------------------------------------------------------------
# Docker Model Runner (OpenAI-compatible, no-auth, base_url first)
# ---------------------------------------------------------------------------


def test_docker_model_runner_preset_shape() -> None:
    d = LlmDeployment.docker_model_runner("http://localhost:12434", model="ai/llama3.2")
    assert d.wire == WireProtocol.OpenAiChat
    assert d.endpoint.path_prefix == "/engines/v1"
    assert d.default_model == "ai/llama3.2"
    assert isinstance(d.auth, StaticNone)


def test_docker_model_runner_rejects_empty_inputs() -> None:
    with pytest.raises(ValueError):
        LlmDeployment.docker_model_runner("", model="ai/llama3.2")
    with pytest.raises(ValueError, match=r"DOCKER_MODEL_RUNNER_PROD_MODEL"):
        LlmDeployment.docker_model_runner("http://localhost:12434", model="")


def test_docker_model_runner_free_function_matches_classmethod() -> None:
    assert (
        docker_model_runner_preset("http://localhost:12434", model="ai/llama3.2").wire
        == LlmDeployment.docker_model_runner(
            "http://localhost:12434", model="ai/llama3.2"
        ).wire
    )


# ---------------------------------------------------------------------------
# Groq (OpenAI-compatible)
# ---------------------------------------------------------------------------


def test_groq_preset_shape() -> None:
    d = LlmDeployment.groq("k", model="llama-3.3-70b-versatile")
    assert d.wire == WireProtocol.OpenAiChat
    assert str(d.endpoint.base_url).startswith("https://api.groq.com")
    assert d.endpoint.path_prefix == "/openai/v1"
    assert d.default_model == "llama-3.3-70b-versatile"
    assert isinstance(d.auth, ApiKeyBearer)


def test_groq_preset_rejects_empty_inputs() -> None:
    with pytest.raises(ValueError):
        LlmDeployment.groq("", model="llama-3.3-70b-versatile")
    with pytest.raises(ValueError, match=r"GROQ_PROD_MODEL"):
        LlmDeployment.groq("k", model="")


def test_groq_preset_free_function_matches_classmethod() -> None:
    assert (
        groq_preset("k", model="llama-3.3-70b-versatile").wire
        == LlmDeployment.groq("k", model="llama-3.3-70b-versatile").wire
    )


# ---------------------------------------------------------------------------
# Together (OpenAI-compatible)
# ---------------------------------------------------------------------------


def test_together_preset_shape() -> None:
    d = LlmDeployment.together("k", model="meta-llama/Llama-3.3-70B-Instruct-Turbo")
    assert d.wire == WireProtocol.OpenAiChat
    assert str(d.endpoint.base_url).startswith("https://api.together.xyz")
    assert d.endpoint.path_prefix == "/v1"
    assert isinstance(d.auth, ApiKeyBearer)


def test_together_preset_rejects_empty_inputs() -> None:
    with pytest.raises(ValueError):
        LlmDeployment.together("", model="meta-llama/Llama-3.3-70B-Instruct-Turbo")
    with pytest.raises(ValueError, match=r"TOGETHER_PROD_MODEL"):
        LlmDeployment.together("k", model="")


def test_together_preset_free_function_matches_classmethod() -> None:
    assert (
        together_preset("k", model="meta-llama/Llama-3.3-70B-Instruct-Turbo").wire
        == LlmDeployment.together(
            "k", model="meta-llama/Llama-3.3-70B-Instruct-Turbo"
        ).wire
    )


# ---------------------------------------------------------------------------
# Fireworks (OpenAI-compatible)
# ---------------------------------------------------------------------------


def test_fireworks_preset_shape() -> None:
    d = LlmDeployment.fireworks(
        "k", model="accounts/fireworks/models/llama-v3p1-70b-instruct"
    )
    assert d.wire == WireProtocol.OpenAiChat
    assert str(d.endpoint.base_url).startswith("https://api.fireworks.ai")
    assert d.endpoint.path_prefix == "/inference/v1"


def test_fireworks_preset_rejects_empty_inputs() -> None:
    with pytest.raises(ValueError):
        LlmDeployment.fireworks(
            "", model="accounts/fireworks/models/llama-v3p1-70b-instruct"
        )
    with pytest.raises(ValueError, match=r"FIREWORKS_PROD_MODEL"):
        LlmDeployment.fireworks("k", model="")


def test_fireworks_preset_free_function_matches_classmethod() -> None:
    assert (
        fireworks_preset(
            "k", model="accounts/fireworks/models/llama-v3p1-70b-instruct"
        ).wire
        == LlmDeployment.fireworks(
            "k", model="accounts/fireworks/models/llama-v3p1-70b-instruct"
        ).wire
    )


# ---------------------------------------------------------------------------
# OpenRouter (OpenAI-compatible)
# ---------------------------------------------------------------------------


def test_openrouter_preset_shape() -> None:
    d = LlmDeployment.openrouter("k", model="anthropic/claude-3.5-sonnet")
    assert d.wire == WireProtocol.OpenAiChat
    assert str(d.endpoint.base_url).startswith("https://openrouter.ai")
    assert d.endpoint.path_prefix == "/api/v1"


def test_openrouter_preset_rejects_empty_inputs() -> None:
    with pytest.raises(ValueError):
        LlmDeployment.openrouter("", model="anthropic/claude-3.5-sonnet")
    with pytest.raises(ValueError, match=r"OPENROUTER_PROD_MODEL"):
        LlmDeployment.openrouter("k", model="")


def test_openrouter_preset_free_function_matches_classmethod() -> None:
    assert (
        openrouter_preset("k", model="anthropic/claude-3.5-sonnet").wire
        == LlmDeployment.openrouter("k", model="anthropic/claude-3.5-sonnet").wire
    )


# ---------------------------------------------------------------------------
# DeepSeek (OpenAI-compatible)
# ---------------------------------------------------------------------------


def test_deepseek_preset_shape() -> None:
    d = LlmDeployment.deepseek("k", model="deepseek-chat")
    assert d.wire == WireProtocol.OpenAiChat
    assert str(d.endpoint.base_url).startswith("https://api.deepseek.com")
    assert d.endpoint.path_prefix == "/v1"


def test_deepseek_preset_rejects_empty_inputs() -> None:
    with pytest.raises(ValueError):
        LlmDeployment.deepseek("", model="deepseek-chat")
    with pytest.raises(ValueError, match=r"DEEPSEEK_PROD_MODEL"):
        LlmDeployment.deepseek("k", model="")


def test_deepseek_preset_free_function_matches_classmethod() -> None:
    assert (
        deepseek_preset("k", model="deepseek-chat").wire
        == LlmDeployment.deepseek("k", model="deepseek-chat").wire
    )


# ---------------------------------------------------------------------------
# LM Studio (OpenAI-compatible, no-auth, base_url first)
# ---------------------------------------------------------------------------


def test_lm_studio_preset_shape() -> None:
    d = LlmDeployment.lm_studio(
        "http://localhost:1234", model="lmstudio-community/Llama-3.2-3B-Instruct-GGUF"
    )
    assert d.wire == WireProtocol.OpenAiChat
    assert d.endpoint.path_prefix == "/v1"
    assert isinstance(d.auth, StaticNone)


def test_lm_studio_rejects_empty_inputs() -> None:
    with pytest.raises(ValueError):
        LlmDeployment.lm_studio("", model="m")
    with pytest.raises(ValueError, match=r"LM_STUDIO_PROD_MODEL"):
        LlmDeployment.lm_studio("http://localhost:1234", model="")


def test_lm_studio_free_function_matches_classmethod() -> None:
    assert (
        lm_studio_preset("http://localhost:1234", model="m").wire
        == LlmDeployment.lm_studio("http://localhost:1234", model="m").wire
    )


# ---------------------------------------------------------------------------
# LlamaCpp (OpenAI-compatible, no-auth, base_url first)
# ---------------------------------------------------------------------------


def test_llama_cpp_preset_shape() -> None:
    d = LlmDeployment.llama_cpp("http://localhost:8080", model="local-gguf")
    assert d.wire == WireProtocol.OpenAiChat
    assert d.endpoint.path_prefix == "/v1"
    assert isinstance(d.auth, StaticNone)


def test_llama_cpp_rejects_empty_inputs() -> None:
    with pytest.raises(ValueError):
        LlmDeployment.llama_cpp("", model="local-gguf")
    with pytest.raises(ValueError, match=r"LLAMA_CPP_PROD_MODEL"):
        LlmDeployment.llama_cpp("http://localhost:8080", model="")


def test_llama_cpp_free_function_matches_classmethod() -> None:
    assert (
        llama_cpp_preset("http://localhost:8080", model="local-gguf").wire
        == LlmDeployment.llama_cpp("http://localhost:8080", model="local-gguf").wire
    )


# ---------------------------------------------------------------------------
# Frozen contract — every S3 deployment is immutable post-construction
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "factory",
    [
        lambda: LlmDeployment.anthropic("k", model="claude-3-5-sonnet-20241022"),
        lambda: LlmDeployment.google("k", model="gemini-2.0-flash"),
        lambda: LlmDeployment.cohere("k", model="command-r-plus"),
        lambda: LlmDeployment.mistral("k", model="mistral-large-latest"),
        lambda: LlmDeployment.perplexity("k", model="sonar-large-online"),
        lambda: LlmDeployment.huggingface("k", model="m"),
        lambda: LlmDeployment.ollama("http://localhost:11434", model="llama3.1:8b"),
        lambda: LlmDeployment.docker_model_runner(
            "http://localhost:12434", model="ai/m"
        ),
        lambda: LlmDeployment.groq("k", model="llama-3.3-70b-versatile"),
        lambda: LlmDeployment.together("k", model="m"),
        lambda: LlmDeployment.fireworks("k", model="m"),
        lambda: LlmDeployment.openrouter("k", model="a/b"),
        lambda: LlmDeployment.deepseek("k", model="deepseek-chat"),
        lambda: LlmDeployment.lm_studio("http://localhost:1234", model="m"),
        lambda: LlmDeployment.llama_cpp("http://localhost:8080", model="m"),
    ],
)
def test_every_s3_deployment_is_frozen(factory) -> None:
    d = factory()
    with pytest.raises((ValueError, TypeError)):
        d.wire = WireProtocol.OpenAiChat  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Remaining deferred presets still raise (bedrock_*, azure_*, vertex_*)
# ---------------------------------------------------------------------------


def test_remaining_deferred_presets_raise_not_implemented() -> None:
    """bedrock_llama/titan/mistral / azure_* / vertex_* stay deferred.

    `bedrock_claude` is wired as a real preset in Session 3 (S4a); this
    test excludes it. The remaining bedrock_* families land in S4b-ii.
    """
    with pytest.raises(NotImplementedError, match=r"session"):
        LlmDeployment.bedrock_llama("k")
    with pytest.raises(NotImplementedError, match=r"session"):
        LlmDeployment.bedrock_titan("k")
    with pytest.raises(NotImplementedError, match=r"session"):
        LlmDeployment.bedrock_mistral("k")
    with pytest.raises(NotImplementedError, match=r"session"):
        LlmDeployment.azure_openai("k")
    with pytest.raises(NotImplementedError, match=r"session"):
        LlmDeployment.azure_entra("k")
    with pytest.raises(NotImplementedError, match=r"session"):
        LlmDeployment.vertex_gemini("k")

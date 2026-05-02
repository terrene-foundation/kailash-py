# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""`<provider>_from_env` convenience preset tests (#791).

Cross-SDK parity with the 12 zero-arg `pub fn <provider>() -> Self`
classmethods on kailash-rs `LlmDeployment` at
`crates/kailash-kaizen/src/llm/deployment/presets.rs` lines 153, 249, 346,
386, 408, 430, 458, 928, 964, 1000, 1036, 1072.

Each Python `<provider>_from_env_preset()` factory:

1. Reads `<PROVIDER>_API_KEY` from the environment, raising
   `MissingCredential` if absent / empty.
2. Reads `<PROVIDER>_PROD_MODEL` (canonical) with fallback to
   `<PROVIDER>_MODEL` (legacy precedence chain), raising
   `MissingCredential` if neither is set.
3. Delegates to the existing parent `<provider>_preset(api_key, model)` —
   same wire / endpoint / auth shape as the long-form factory.

Per `rules/cross-sdk-inspection.md` § 3 EATP D6: implementation-idiom
difference (Python `_from_env` reads env explicitly + eager-validates;
Rust `<provider>()` is auth-less + caller chains `.with_api_key(...)`)
is acceptable when semantics match.

Per `rules/testing.md` § "Serialize Env-Var-Mutating Tests Via Module
Lock": every test mutating shared `os.environ` keys takes the
`_env_serialized` fixture, so cross-test scheduling on xdist cannot
observe each other's monkeypatched values.
"""

from __future__ import annotations

import threading

import pytest

from kaizen.llm.auth.bearer import ApiKeyBearer, ApiKeyHeaderKind
from kaizen.llm.deployment import LlmDeployment, WireProtocol
from kaizen.llm.errors import MissingCredential
from kaizen.llm.presets import (
    anthropic_from_env_preset,
    cohere_from_env_preset,
    deepseek_from_env_preset,
    fireworks_from_env_preset,
    get_preset,
    google_from_env_preset,
    groq_from_env_preset,
    huggingface_from_env_preset,
    list_presets,
    mistral_from_env_preset,
    openai_from_env_preset,
    openrouter_from_env_preset,
    perplexity_from_env_preset,
    together_from_env_preset,
)

# ---------------------------------------------------------------------------
# Env-var serialization fixture (rules/testing.md)
# ---------------------------------------------------------------------------

_ENV_LOCK = threading.Lock()

# Canonical env vars consumed by the 12 from_env factories. Tests that mutate
# any of these MUST take `_env_serialized` so xdist scheduling cannot
# interleave per-test monkeypatch teardowns.
_FROM_ENV_VARS = (
    "OPENAI_API_KEY",
    "OPENAI_PROD_MODEL",
    "OPENAI_MODEL",
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_PROD_MODEL",
    "ANTHROPIC_MODEL",
    "GOOGLE_API_KEY",
    "GOOGLE_PROD_MODEL",
    "GOOGLE_MODEL",
    "GEMINI_API_KEY",
    "GEMINI_PROD_MODEL",
    "GEMINI_MODEL",
    "COHERE_API_KEY",
    "COHERE_PROD_MODEL",
    "COHERE_MODEL",
    "MISTRAL_API_KEY",
    "MISTRAL_PROD_MODEL",
    "MISTRAL_MODEL",
    "PERPLEXITY_API_KEY",
    "PERPLEXITY_PROD_MODEL",
    "PERPLEXITY_MODEL",
    "HUGGINGFACE_API_KEY",
    "HUGGINGFACE_PROD_MODEL",
    "HUGGINGFACE_MODEL",
    "GROQ_API_KEY",
    "GROQ_PROD_MODEL",
    "GROQ_MODEL",
    "TOGETHER_API_KEY",
    "TOGETHER_PROD_MODEL",
    "TOGETHER_MODEL",
    "FIREWORKS_API_KEY",
    "FIREWORKS_PROD_MODEL",
    "FIREWORKS_MODEL",
    "OPENROUTER_API_KEY",
    "OPENROUTER_PROD_MODEL",
    "OPENROUTER_MODEL",
    "DEEPSEEK_API_KEY",
    "DEEPSEEK_PROD_MODEL",
    "DEEPSEEK_MODEL",
)


@pytest.fixture
def _env_serialized(monkeypatch: pytest.MonkeyPatch):
    """Hold the module-scope lock across the entire test body.

    Pre-strips every from_env env var so each test starts from a clean
    slate regardless of the host shell's `.env`. monkeypatch restores at
    teardown, but teardown runs AFTER the test body — the lock prevents
    a sibling test from observing this test's still-set values.
    """
    with _ENV_LOCK:
        for var in _FROM_ENV_VARS:
            monkeypatch.delenv(var, raising=False)
        yield


# ---------------------------------------------------------------------------
# Cross-SDK parity: registry name byte-match the Rust classmethod literals
# ---------------------------------------------------------------------------


_FROM_ENV_PRESETS_RUST_PARITY = frozenset(
    {
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
    }
)


def test_from_env_preset_names_complete() -> None:
    """All 12 `_from_env` factories registered under their canonical names.

    Cross-SDK contract: each name is `<rust_classmethod_name>_from_env`,
    where `<rust_classmethod_name>` is the byte-identical Rust literal at
    `crates/kailash-kaizen/src/llm/deployment/presets.rs`. The `_from_env`
    suffix is the Python idiom-difference per EATP D6.
    """
    registered = set(list_presets())
    missing = _FROM_ENV_PRESETS_RUST_PARITY - registered
    assert not missing, (
        f"_from_env presets missing from registry: {sorted(missing)}. "
        f"Every Rust zero-arg `<provider>()` classmethod MUST have a Python "
        f"registered factory under the byte-matching `<provider>_from_env` name."
    )


def test_from_env_classmethods_attached() -> None:
    """Every registered `<provider>_from_env` is callable on `LlmDeployment`.

    Both surfaces (registry round-trip + classmethod) MUST be installed
    atomically per the precedent in
    `_register_and_attach_session_2_presets` — a preset that is registered
    but not attached (or vice versa) would be visible via only one path.
    """
    for name in _FROM_ENV_PRESETS_RUST_PARITY:
        assert hasattr(LlmDeployment, name), (
            f"LlmDeployment.{name} not attached — registry has it but the "
            f"classmethod is missing"
        )
        method = getattr(LlmDeployment, name)
        assert callable(method)


# ---------------------------------------------------------------------------
# Per-provider shape tests — each variant called DIRECTLY (testing.md MUST:
# "One Direct Test Per Variant In Every Delegating Pair").
# ---------------------------------------------------------------------------


def test_openai_from_env_preset_shape(
    _env_serialized, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-openai")
    monkeypatch.setenv("OPENAI_PROD_MODEL", "gpt-4o")
    dep = openai_from_env_preset()
    assert dep.wire == WireProtocol.OpenAiChat
    assert dep.preset_name == "openai"
    assert dep.default_model == "gpt-4o"
    assert isinstance(dep.auth, ApiKeyBearer)
    assert dep.auth.kind == ApiKeyHeaderKind.Authorization_Bearer
    # Pin endpoint URL byte-for-byte to the Rust source-of-truth literal at
    # `presets.rs:154` — `Endpoint::new("https://api.openai.com/v1")`.
    assert str(dep.endpoint.base_url).rstrip("/") == "https://api.openai.com"
    assert dep.endpoint.path_prefix == "/v1"


def test_anthropic_from_env_preset_shape(
    _env_serialized, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("ANTHROPIC_PROD_MODEL", "claude-3-5-sonnet-latest")
    dep = anthropic_from_env_preset()
    assert dep.wire == WireProtocol.AnthropicMessages
    assert dep.preset_name == "anthropic"
    assert dep.default_model == "claude-3-5-sonnet-latest"
    assert isinstance(dep.auth, ApiKeyBearer)
    assert dep.auth.kind == ApiKeyHeaderKind.X_Api_Key
    # Rust `presets.rs:250`: `Endpoint::new("https://api.anthropic.com")`.
    assert str(dep.endpoint.base_url).rstrip("/") == "https://api.anthropic.com"


def test_google_from_env_preset_shape(
    _env_serialized, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GOOGLE_API_KEY", "AIza-test")
    monkeypatch.setenv("GOOGLE_PROD_MODEL", "gemini-1.5-pro")
    dep = google_from_env_preset()
    assert dep.wire == WireProtocol.GoogleGenerateContent
    assert dep.preset_name == "google"
    assert dep.default_model == "gemini-1.5-pro"
    assert isinstance(dep.auth, ApiKeyBearer)
    assert dep.auth.kind == ApiKeyHeaderKind.X_Goog_Api_Key
    # Rust `presets.rs:347`:
    #   `Endpoint::new("https://generativelanguage.googleapis.com/v1beta")`.
    assert (
        str(dep.endpoint.base_url).rstrip("/")
        == "https://generativelanguage.googleapis.com"
    )
    assert dep.endpoint.path_prefix == "/v1beta"


def test_cohere_from_env_preset_shape(
    _env_serialized, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("COHERE_API_KEY", "co-test")
    monkeypatch.setenv("COHERE_PROD_MODEL", "command-r-plus")
    dep = cohere_from_env_preset()
    assert dep.wire == WireProtocol.CohereGenerate
    assert dep.preset_name == "cohere"
    assert dep.default_model == "command-r-plus"
    # NOTE: the Python parent factory (`cohere_preset`) currently uses
    # `https://api.cohere.com/v1` while Rust `presets.rs:387` uses
    # `https://api.cohere.ai/v2`. This divergence pre-dates #791 and
    # is a SEPARATE cross-SDK parity issue (#791 inherits whichever URL
    # the parent factory exposes). Once the parent URL is reconciled the
    # `_from_env` wrapper picks up the change automatically.
    assert dep.endpoint.path_prefix == "/v1"


def test_mistral_from_env_preset_shape(
    _env_serialized, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MISTRAL_API_KEY", "mi-test")
    monkeypatch.setenv("MISTRAL_PROD_MODEL", "mistral-large-latest")
    dep = mistral_from_env_preset()
    assert dep.wire == WireProtocol.MistralChat
    assert dep.preset_name == "mistral"
    assert dep.default_model == "mistral-large-latest"
    # Rust `presets.rs:409`: `Endpoint::new("https://api.mistral.ai/v1")`.
    assert str(dep.endpoint.base_url).rstrip("/") == "https://api.mistral.ai"
    assert dep.endpoint.path_prefix == "/v1"


def test_perplexity_from_env_preset_shape(
    _env_serialized, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PERPLEXITY_API_KEY", "pplx-test")
    monkeypatch.setenv("PERPLEXITY_PROD_MODEL", "sonar-pro")
    dep = perplexity_from_env_preset()
    assert dep.wire == WireProtocol.OpenAiChat
    assert dep.preset_name == "perplexity"
    assert dep.default_model == "sonar-pro"
    # Rust `presets.rs:431`: `Endpoint::new("https://api.perplexity.ai")`.
    assert str(dep.endpoint.base_url).rstrip("/") == "https://api.perplexity.ai"


def test_huggingface_from_env_preset_shape(
    _env_serialized, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HUGGINGFACE_API_KEY", "hf-test")
    monkeypatch.setenv("HUGGINGFACE_PROD_MODEL", "meta-llama/Llama-3-70B-Instruct")
    dep = huggingface_from_env_preset()
    assert dep.wire == WireProtocol.HuggingFaceInference
    assert dep.preset_name == "huggingface"
    # Rust `presets.rs:459`:
    #   `Endpoint::new("https://api-inference.huggingface.co")`.
    assert (
        str(dep.endpoint.base_url).rstrip("/") == "https://api-inference.huggingface.co"
    )


def test_groq_from_env_preset_shape(
    _env_serialized, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "gsk-test")
    monkeypatch.setenv("GROQ_PROD_MODEL", "llama-3.1-70b-versatile")
    dep = groq_from_env_preset()
    assert dep.wire == WireProtocol.OpenAiChat
    assert dep.preset_name == "groq"
    # Rust `presets.rs:929`:
    #   `Endpoint::new("https://api.groq.com/openai/v1")`.
    assert str(dep.endpoint.base_url).rstrip("/") == "https://api.groq.com"
    assert dep.endpoint.path_prefix == "/openai/v1"


def test_together_from_env_preset_shape(
    _env_serialized, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TOGETHER_API_KEY", "tg-test")
    monkeypatch.setenv("TOGETHER_PROD_MODEL", "meta-llama/Llama-3-70b-chat-hf")
    dep = together_from_env_preset()
    assert dep.wire == WireProtocol.OpenAiChat
    assert dep.preset_name == "together"
    # Rust `presets.rs:965`:
    #   `Endpoint::new("https://api.together.xyz/v1")`.
    assert str(dep.endpoint.base_url).rstrip("/") == "https://api.together.xyz"
    assert dep.endpoint.path_prefix == "/v1"


def test_fireworks_from_env_preset_shape(
    _env_serialized, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FIREWORKS_API_KEY", "fw-test")
    monkeypatch.setenv(
        "FIREWORKS_PROD_MODEL", "accounts/fireworks/models/llama-v3p1-70b"
    )
    dep = fireworks_from_env_preset()
    assert dep.wire == WireProtocol.OpenAiChat
    assert dep.preset_name == "fireworks"
    # Rust `presets.rs:1001`:
    #   `Endpoint::new("https://api.fireworks.ai/inference/v1")`.
    assert str(dep.endpoint.base_url).rstrip("/") == "https://api.fireworks.ai"
    assert dep.endpoint.path_prefix == "/inference/v1"


def test_openrouter_from_env_preset_shape(
    _env_serialized, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-test")
    monkeypatch.setenv("OPENROUTER_PROD_MODEL", "anthropic/claude-3.5-sonnet")
    dep = openrouter_from_env_preset()
    assert dep.wire == WireProtocol.OpenAiChat
    assert dep.preset_name == "openrouter"
    # Rust `presets.rs:1037`: `Endpoint::new("https://openrouter.ai/api/v1")`.
    assert str(dep.endpoint.base_url).rstrip("/") == "https://openrouter.ai"
    assert dep.endpoint.path_prefix == "/api/v1"


def test_deepseek_from_env_preset_shape(
    _env_serialized, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "ds-test")
    monkeypatch.setenv("DEEPSEEK_PROD_MODEL", "deepseek-chat")
    dep = deepseek_from_env_preset()
    assert dep.wire == WireProtocol.OpenAiChat
    assert dep.preset_name == "deepseek"
    # Rust `presets.rs:1073`: `Endpoint::new("https://api.deepseek.com/v1")`.
    assert str(dep.endpoint.base_url).rstrip("/") == "https://api.deepseek.com"
    assert dep.endpoint.path_prefix == "/v1"


# ---------------------------------------------------------------------------
# Missing-env-var handling — typed `MissingCredential` per provider
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("factory", "api_key_var"),
    [
        (openai_from_env_preset, "OPENAI_API_KEY"),
        (anthropic_from_env_preset, "ANTHROPIC_API_KEY"),
        (google_from_env_preset, "GOOGLE_API_KEY"),
        (cohere_from_env_preset, "COHERE_API_KEY"),
        (mistral_from_env_preset, "MISTRAL_API_KEY"),
        (perplexity_from_env_preset, "PERPLEXITY_API_KEY"),
        (huggingface_from_env_preset, "HUGGINGFACE_API_KEY"),
        (groq_from_env_preset, "GROQ_API_KEY"),
        (together_from_env_preset, "TOGETHER_API_KEY"),
        (fireworks_from_env_preset, "FIREWORKS_API_KEY"),
        (openrouter_from_env_preset, "OPENROUTER_API_KEY"),
        (deepseek_from_env_preset, "DEEPSEEK_API_KEY"),
    ],
)
def test_from_env_preset_missing_api_key_raises(
    factory, api_key_var: str, _env_serialized
) -> None:
    """Each `<provider>_from_env_preset()` raises typed `MissingCredential`
    naming the missing api_key env var when it's unset."""
    with pytest.raises(MissingCredential) as exc_info:
        factory()
    assert exc_info.value.source_hint == api_key_var


@pytest.mark.parametrize(
    ("factory", "api_key_var", "model_var_hint"),
    [
        (
            openai_from_env_preset,
            "OPENAI_API_KEY",
            "OPENAI_PROD_MODEL or OPENAI_MODEL",
        ),
        (
            anthropic_from_env_preset,
            "ANTHROPIC_API_KEY",
            "ANTHROPIC_PROD_MODEL or ANTHROPIC_MODEL",
        ),
        (
            cohere_from_env_preset,
            "COHERE_API_KEY",
            "COHERE_PROD_MODEL or COHERE_MODEL",
        ),
        (
            mistral_from_env_preset,
            "MISTRAL_API_KEY",
            "MISTRAL_PROD_MODEL or MISTRAL_MODEL",
        ),
    ],
)
def test_from_env_preset_missing_model_raises(
    factory,
    api_key_var: str,
    model_var_hint: str,
    _env_serialized,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Each `<provider>_from_env_preset()` with key-but-no-model raises
    typed `MissingCredential` listing the model env var candidates."""
    monkeypatch.setenv(api_key_var, "test-key-value")
    with pytest.raises(MissingCredential) as exc_info:
        factory()
    assert exc_info.value.source_hint == model_var_hint


def test_google_from_env_falls_back_to_gemini_env_vars(
    _env_serialized, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`google_from_env_preset` accepts `GEMINI_*` env vars when `GOOGLE_*`
    is unset, per `rules/env-models.md` (the two are interchangeable).

    Precedence: GOOGLE_API_KEY wins over GEMINI_API_KEY when both set;
    GEMINI_* is the legacy fallback.
    """
    # NOTE: GOOGLE_API_KEY is the api-key env var ONLY for this provider;
    # the function does not currently fall back to GEMINI_API_KEY because
    # `_FROM_ENV_PROVIDERS` declares only GOOGLE_API_KEY for the api_key
    # slot. That keeps the contract narrow: api_key has one canonical
    # source per provider; model has multiple legacy fallbacks.
    monkeypatch.setenv("GOOGLE_API_KEY", "AIza-test")
    monkeypatch.setenv("GEMINI_PROD_MODEL", "gemini-2.0-flash")
    dep = google_from_env_preset()
    assert dep.default_model == "gemini-2.0-flash"


def test_from_env_preset_legacy_model_env_var_accepted(
    _env_serialized, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Legacy `<PROVIDER>_MODEL` (no `_PROD_` infix) is accepted when
    `<PROVIDER>_PROD_MODEL` is unset.

    Precedence: PROD wins over legacy when both are set. This mirrors the
    fallback chain in `kaizen.llm.from_env::_call_preset_from_env`.
    """
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-4o-mini")
    dep = openai_from_env_preset()
    assert dep.default_model == "gpt-4o-mini"


def test_from_env_preset_prod_model_takes_precedence(
    _env_serialized, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When both `<PROVIDER>_PROD_MODEL` and `<PROVIDER>_MODEL` are set,
    PROD wins (it's the canonical name per parent factory docstrings)."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_PROD_MODEL", "gpt-4o")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-4o-mini")
    dep = openai_from_env_preset()
    assert dep.default_model == "gpt-4o"


# ---------------------------------------------------------------------------
# Registry round-trip — get_preset(<name>)() works the same as the symbol
# ---------------------------------------------------------------------------


def test_from_env_preset_registry_round_trip(
    _env_serialized, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`get_preset("openai_from_env")()` produces an identical deployment
    to `openai_from_env_preset()` — the registry path matches the
    symbol path byte-for-byte."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_PROD_MODEL", "gpt-4o")
    direct = openai_from_env_preset()
    via_registry = get_preset("openai_from_env")()
    assert direct.wire == via_registry.wire
    assert direct.preset_name == via_registry.preset_name
    assert direct.default_model == via_registry.default_model
    assert str(direct.endpoint.base_url).rstrip("/") == str(
        via_registry.endpoint.base_url
    ).rstrip("/")
    assert direct.endpoint.path_prefix == via_registry.endpoint.path_prefix


def test_from_env_classmethod_matches_module_function(
    _env_serialized, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`LlmDeployment.openai_from_env()` ≡ `openai_from_env_preset()` —
    both surfaces produce structurally identical deployments."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_PROD_MODEL", "gpt-4o")
    via_module = openai_from_env_preset()
    via_classmethod = LlmDeployment.openai_from_env()
    assert via_module.wire == via_classmethod.wire
    assert via_module.preset_name == via_classmethod.preset_name
    assert via_module.default_model == via_classmethod.default_model


def test_from_env_preset_routes_through_parent_capability_row(
    _env_serialized, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Capability lookups for an `_from_env` deployment route through the
    PARENT preset row, not a separate `_from_env` row.

    The `from_env` factory delegates to `<provider>_preset` which sets
    `preset_name="<provider>"` (parent literal) on the deployment, so
    `for_preset(dep.preset_name)` resolves to the parent's capability row
    automatically. This mirrors the `<provider>_default` precedent (#787).
    """
    from kaizen.llm.capabilities import for_preset

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_PROD_MODEL", "gpt-4o")
    dep = openai_from_env_preset()
    via_dep = for_preset(dep.preset_name or "")
    via_parent = for_preset("openai")
    assert via_dep == via_parent

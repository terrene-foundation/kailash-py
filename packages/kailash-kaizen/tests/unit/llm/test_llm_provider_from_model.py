# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Tier-1 unit tests for `LlmProvider.from_model` + DeepSeek first-class support.

Covers issue #1609 acceptance criteria (network-free):

* `LlmProvider.from_model("deepseek-chat")` / `("deepseek-reasoner")` resolve
  to a DeepSeek provider.
* The DeepSeek provider exposes `api_key_env_vars == ["DEEPSEEK_API_KEY"]`,
  `base_url == "https://api.deepseek.com"`, and correct `capabilities`.
* `LlmClient.from_env()` selects DeepSeek when a `deepseek-*` model +
  `DEEPSEEK_API_KEY` are configured (legacy tier AND selector tier).
* Single-source-of-truth cross-checks: the provider's `base_url` matches the
  `deepseek_preset` default endpoint; its `api_key_env_vars` matches
  `presets._FROM_ENV_PROVIDERS`.

The live chat + streaming verification against the real DeepSeek
OpenAI-compatible API is key-gated in
`tests/integration/llm/test_deepseek_live.py` (skipped without
`DEEPSEEK_API_KEY`).
"""

from __future__ import annotations

import pytest

from kaizen.llm import LlmProvider, UnknownModelProvider
from kaizen.llm.client import LlmClient
from kaizen.llm.deployment import LlmDeployment
from kaizen.llm.errors import MissingCredential
from kaizen.llm.presets import deepseek_preset

# ---------------------------------------------------------------------------
# from_model — DeepSeek (the #1609 headline)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("model", ["deepseek-chat", "deepseek-reasoner"])
def test_from_model_deepseek_resolves_deepseek_provider(model: str) -> None:
    provider = LlmProvider.from_model(model)
    assert provider.name == "deepseek"
    assert provider.display_name == "DeepSeek"


def test_deepseek_provider_exposes_expected_coordinates() -> None:
    provider = LlmProvider.from_model("deepseek-chat")
    # AC: exact list equality (mirrors the Rust `LlmProvider` Vec shape).
    assert provider.api_key_env_vars == ["DEEPSEEK_API_KEY"]
    assert provider.base_url == "https://api.deepseek.com"
    assert provider.openai_compatible is True


def test_deepseek_capabilities_chat_streaming_openai_compatible() -> None:
    caps = LlmProvider.from_model("deepseek-reasoner").capabilities
    # OpenAI-compatible chat + streaming per the AC.
    assert caps["chat"] is True
    assert caps["streaming"] is True
    assert caps["openai_compatible"] is True
    # Deployment surface (delegated to the capabilities table): DeepSeek's
    # OpenAI-compatible endpoint serves text-only tool-calling, no vision.
    assert caps["tools"] is True
    assert caps["vision"] is False


def test_api_key_env_vars_is_independent_list_copy() -> None:
    provider = LlmProvider.from_name("deepseek")
    a = provider.api_key_env_vars
    a.append("MUTATED")
    # Mutating the returned list does not leak into the registry.
    assert provider.api_key_env_vars == ["DEEPSEEK_API_KEY"]


# ---------------------------------------------------------------------------
# from_model — sibling providers (the #1609 repro's working cases)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("model", "expected"),
    [
        ("gpt-4o", "openai"),
        ("o1-preview", "openai"),
        ("claude-3-5-sonnet", "anthropic"),
        ("gemini-2.0-flash", "google"),
        ("DeepSeek-Chat", "deepseek"),  # case-insensitive prefix match
    ],
)
def test_from_model_prefix_resolution(model: str, expected: str) -> None:
    assert LlmProvider.from_model(model).name == expected


@pytest.mark.parametrize("bad", ["mystery-model-x", "", "   ", "llama3.2"])
def test_from_model_unknown_prefix_fails_closed(bad: str) -> None:
    # Fail-closed: unknown prefix raises (a ValueError subclass), never a
    # silent default provider route.
    with pytest.raises(UnknownModelProvider):
        LlmProvider.from_model(bad)
    assert issubclass(UnknownModelProvider, ValueError)


def test_from_name_unknown_raises() -> None:
    with pytest.raises(UnknownModelProvider):
        LlmProvider.from_name("not-a-provider")


# ---------------------------------------------------------------------------
# Single-source-of-truth cross-checks (guard against data drift)
# ---------------------------------------------------------------------------


def test_deepseek_base_url_matches_preset_default() -> None:
    # The provider's base_url MUST equal the deepseek_preset default endpoint;
    # if a future edit changes one without the other, this fails loudly.
    provider = LlmProvider.from_name("deepseek")
    dep = deepseek_preset("k", model="deepseek-chat")
    assert provider.base_url == str(dep.endpoint.base_url).rstrip("/")


def test_deepseek_api_key_env_vars_match_from_env_registry() -> None:
    # Pin the provider's api_key_env_vars to presets._FROM_ENV_PROVIDERS so
    # the two registries cannot drift.
    from kaizen.llm.presets import _FROM_ENV_PROVIDERS

    spec = next(s for s in _FROM_ENV_PROVIDERS if s[0] == "deepseek")
    _name, api_key_env, _model_vars = spec
    assert LlmProvider.from_name("deepseek").api_key_env_vars == [api_key_env]


def test_every_registered_provider_name_is_a_known_preset() -> None:
    # Each provider name MUST resolve to a real preset factory (so
    # `.deployment()` can never reference a missing preset).
    from kaizen.llm.presets import get_preset

    for provider in LlmProvider.all():
        assert callable(get_preset(provider.name))


# ---------------------------------------------------------------------------
# deployment() bridge — real LlmDeployment, no re-implemented wire/auth
# ---------------------------------------------------------------------------


def test_deployment_bridges_to_preset() -> None:
    dep = LlmProvider.from_model("deepseek-chat").deployment(
        api_key="k", model="deepseek-chat"
    )
    assert isinstance(dep, LlmDeployment)
    assert dep.preset_name == "deepseek"
    assert str(dep.endpoint.base_url).rstrip("/") == "https://api.deepseek.com"
    assert dep.wire.name == "OpenAiChat"


def test_deployment_reads_api_key_from_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-env-key")
    dep = LlmProvider.from_name("deepseek").deployment(model="deepseek-chat")
    assert dep.preset_name == "deepseek"


def test_deployment_missing_key_raises_typed_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    with pytest.raises(MissingCredential):
        LlmProvider.from_name("deepseek").deployment(model="deepseek-chat")


# ---------------------------------------------------------------------------
# LlmClient.from_env() — DeepSeek selection (legacy + selector tiers)
# ---------------------------------------------------------------------------


def _clear_provider_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in [
        "KAILASH_LLM_DEPLOYMENT",
        "KAILASH_LLM_PROVIDER",
        "OPENAI_API_KEY",
        "OPENAI_PROD_MODEL",
        "OPENAI_MODEL",
        "AZURE_OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_MODEL",
        "GOOGLE_API_KEY",
        "GEMINI_API_KEY",
        "GOOGLE_MODEL",
        "GEMINI_MODEL",
        "DEEPSEEK_API_KEY",
        "DEEPSEEK_PROD_MODEL",
        "DEEPSEEK_MODEL",
    ]:
        monkeypatch.delenv(var, raising=False)


def test_from_env_legacy_tier_selects_deepseek(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Bare DEEPSEEK_API_KEY (no URI, no selector) → deepseek preset, with the
    # DeepSeek base_url flowing through intrinsically (#1609).
    _clear_provider_env(monkeypatch)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-deepseek-test")
    monkeypatch.setenv("DEEPSEEK_PROD_MODEL", "deepseek-chat")

    # Resolving via the legacy tier ALONE emits a DeprecationWarning
    # (kaizen/llm/from_env.py) -- assert it explicitly rather than let it
    # leak unhandled into the collection-wide warnings summary.
    with pytest.warns(DeprecationWarning, match="legacy per-provider-key"):
        client = LlmClient.from_env()
    dep = client.deployment
    assert dep is not None
    assert dep.preset_name == "deepseek"
    assert str(dep.endpoint.base_url).rstrip("/") == "https://api.deepseek.com"
    assert dep.default_model == "deepseek-chat"


def test_from_env_selector_tier_selects_deepseek(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_provider_env(monkeypatch)
    monkeypatch.setenv("KAILASH_LLM_PROVIDER", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-deepseek-test")
    monkeypatch.setenv("DEEPSEEK_MODEL", "deepseek-reasoner")

    dep = LlmClient.from_env().deployment
    assert dep is not None
    assert dep.preset_name == "deepseek"
    assert dep.default_model == "deepseek-reasoner"


def test_from_env_openai_still_wins_over_deepseek(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # DeepSeek is appended LAST in LEGACY_KEY_ORDER — it must never displace
    # an existing provider's precedence.
    _clear_provider_env(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai")
    monkeypatch.setenv("OPENAI_PROD_MODEL", "gpt-4o")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-deepseek")
    monkeypatch.setenv("DEEPSEEK_PROD_MODEL", "deepseek-chat")

    with pytest.warns(DeprecationWarning, match="legacy per-provider-key"):
        assert LlmClient.from_env().deployment.preset_name == "openai"


def test_from_env_deepseek_missing_model_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Key set, model unset → typed MissingCredential (no silent unauthenticated
    # or model-less deployment). The legacy-tier deprecation warning still
    # fires before resolution discovers the missing model.
    _clear_provider_env(monkeypatch)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-deepseek-test")
    with pytest.warns(DeprecationWarning, match="legacy per-provider-key"):
        with pytest.raises(MissingCredential):
            LlmClient.from_env()

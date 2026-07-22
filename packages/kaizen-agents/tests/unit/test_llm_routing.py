# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 1 unit tests for LLMBased routing strategy.

Mocks are permitted at Tier 1 per rules/testing.md.  The underlying
``llm_text_similarity`` and ``llm_capability_match`` functions are
mocked so the tests run without API keys.
"""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import patch

import pytest

from kaizen_agents.patterns.llm_routing import LLMBased

# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------


@dataclass
class _FakeCapability:
    """Minimal capability stub with name/description for routing tests."""

    name: str
    description: str


# --------------------------------------------------------------------------
# Tests
# --------------------------------------------------------------------------


class TestLLMBasedConstruction:
    """LLMBased can be constructed with or without config."""

    def test_construct_no_config(self):
        strategy = LLMBased()
        assert strategy._config is None

    def test_construct_with_config(self):
        from kaizen.core.base_agent import BaseAgentConfig

        cfg = BaseAgentConfig(llm_provider="mock", model="mock-model")
        strategy = LLMBased(config=cfg)
        assert strategy._config is cfg


class TestLLMBasedScore:
    """score() delegates to the correct reasoning helper and returns a float."""

    @pytest.mark.asyncio
    async def test_score_string_capability(self):
        strategy = LLMBased()
        with patch(
            "kaizen_agents.patterns.llm_routing.llm_text_similarity",
            return_value=0.85,
        ):
            result = await strategy.score("translate a document", "translation service")
            assert isinstance(result, float)
            assert result == pytest.approx(0.85)

    @pytest.mark.asyncio
    async def test_score_structured_capability(self):
        strategy = LLMBased()
        cap = _FakeCapability(name="translate", description="Translates documents")
        with patch(
            "kaizen_agents.patterns.llm_routing.llm_capability_match",
            return_value=0.92,
        ):
            result = await strategy.score("translate a document", cap)
            assert isinstance(result, float)
            assert result == pytest.approx(0.92)

    @pytest.mark.asyncio
    async def test_score_returns_zero_for_empty_task(self):
        """llm_text_similarity returns 0.0 for empty input."""
        strategy = LLMBased()
        with patch(
            "kaizen_agents.patterns.llm_routing.llm_text_similarity",
            return_value=0.0,
        ):
            result = await strategy.score("", "anything")
            assert result == 0.0


class TestLLMBasedSelectBest:
    """select_best() scores all candidates and returns the highest."""

    @pytest.mark.asyncio
    async def test_select_best_returns_highest(self):
        strategy = LLMBased()
        candidates = ["translation", "summarization", "code review"]
        scores = {
            "translation": 0.9,
            "summarization": 0.3,
            "code review": 0.1,
        }
        with patch(
            "kaizen_agents.patterns.llm_routing.llm_text_similarity",
            side_effect=lambda text_a, text_b, **kw: scores.get(text_b, 0.0),
        ):
            best = await strategy.select_best("translate this", candidates)
            assert best == "translation"

    @pytest.mark.asyncio
    async def test_select_best_empty_candidates(self):
        strategy = LLMBased()
        result = await strategy.select_best("translate", [])
        assert result is None

    @pytest.mark.asyncio
    async def test_select_best_structured_capabilities(self):
        strategy = LLMBased()
        caps = [
            _FakeCapability(name="translate", description="Translates documents"),
            _FakeCapability(name="summarize", description="Summarizes text"),
        ]
        scores = {"translate": 0.95, "summarize": 0.4}
        with patch(
            "kaizen_agents.patterns.llm_routing.llm_capability_match",
            side_effect=lambda capability_name, **kw: scores.get(capability_name, 0.0),
        ):
            best = await strategy.select_best("translate this document", caps)
            assert best is caps[0]


# ==========================================================================
# Issue #1918 — zero-config Delegate MUST infer the provider from the model
# prefix, not silently route claude-*/gemini-* to the OpenAI wire.
#
# Before the fix, KzConfig.provider defaulted to the truthy "openai", which
# AgentLoop._build_adapter forwarded to get_adapter_for_model as an EXPLICIT
# provider — short-circuiting the model-name-prefix fallback. A bare
# Delegate(model="claude-...") built an OpenAIStreamAdapter @ api.openai.com.
#
# These tests exercise the routing DISPATCH end-to-end through Delegate (the
# path the bug lived on — NOT get_adapter_for_model directly, whose own default
# provider="" already inferred correctly). Adapters construct without a live
# network call; ungoverned=True bypasses the #1779 governance gate and the
# api_key is a test-only fixture, not a real secret. The model-name literals are
# prefix-SHAPE fixtures for the detection logic, not production model selection
# (rules/env-models.md governs production paths; test fixtures are exempt).
# --------------------------------------------------------------------------

_FAKE_KEY = "test-routing-key"  # not a real secret; test-only fixture


def _loop_adapter(delegate):
    """The streaming adapter the delegate's loop will drive."""
    return delegate._loop._adapter


class TestZeroConfigDelegateProviderRouting:
    """A bare Delegate(model=...) infers the provider from the model prefix."""

    def test_zero_config_claude_routes_to_anthropic(self):
        """Delegate(model="claude-*") builds an Anthropic adapter, NOT OpenAI."""
        from kaizen_agents.delegate.adapters.anthropic_adapter import (
            AnthropicStreamAdapter,
        )
        from kaizen_agents.delegate.adapters.openai_adapter import OpenAIStreamAdapter
        from kaizen_agents.delegate.delegate import Delegate

        delegate = Delegate(
            model="claude-3-5-sonnet", api_key=_FAKE_KEY, ungoverned=True
        )
        adapter = _loop_adapter(delegate)
        assert isinstance(adapter, AnthropicStreamAdapter), (
            "zero-config claude-* must route to the Anthropic adapter, got "
            f"{type(adapter).__name__} (the #1918 regression: it hit OpenAI)"
        )
        assert not isinstance(adapter, OpenAIStreamAdapter)
        endpoint = str(adapter._client.base_url)
        assert (
            "api.openai.com" not in endpoint
        ), f"claude-* routed to {endpoint!r} — the OpenAI wire (issue #1918)"
        assert "anthropic" in endpoint

    def test_zero_config_gemini_routes_to_google(self):
        """Delegate(model="gemini-*") builds a Google adapter, NOT OpenAI."""
        from kaizen_agents.delegate.adapters.google_adapter import GoogleStreamAdapter
        from kaizen_agents.delegate.adapters.openai_adapter import OpenAIStreamAdapter
        from kaizen_agents.delegate.delegate import Delegate

        delegate = Delegate(
            model="gemini-2.0-flash", api_key=_FAKE_KEY, ungoverned=True
        )
        adapter = _loop_adapter(delegate)
        assert isinstance(adapter, GoogleStreamAdapter), (
            "zero-config gemini-* must route to the Google adapter, got "
            f"{type(adapter).__name__} (the #1918 regression: it hit OpenAI)"
        )
        # GoogleStreamAdapter constructs a genai.Client (no OpenAI wire); the
        # isinstance check above is the "not api.openai.com" guarantee.
        assert not isinstance(adapter, OpenAIStreamAdapter)

    def test_zero_config_gpt_still_routes_to_openai(self):
        """Non-regression: a bare gpt-* still routes to OpenAI @ api.openai.com."""
        from kaizen_agents.delegate.adapters.openai_adapter import OpenAIStreamAdapter
        from kaizen_agents.delegate.delegate import Delegate

        delegate = Delegate(model="gpt-4o", api_key=_FAKE_KEY, ungoverned=True)
        adapter = _loop_adapter(delegate)
        assert isinstance(adapter, OpenAIStreamAdapter)
        assert "api.openai.com" in str(adapter._client.base_url)

    def test_zero_config_unknown_prefix_still_defaults_to_openai(self):
        """Non-regression: an unknown-prefix model still defaults to OpenAI."""
        from kaizen_agents.delegate.adapters.openai_adapter import OpenAIStreamAdapter
        from kaizen_agents.delegate.delegate import Delegate

        delegate = Delegate(
            model="my-custom-deployment", api_key=_FAKE_KEY, ungoverned=True
        )
        adapter = _loop_adapter(delegate)
        assert isinstance(adapter, OpenAIStreamAdapter)
        assert "api.openai.com" in str(adapter._client.base_url)

    def test_explicit_provider_wins_over_model_prefix(self):
        """An explicit KzConfig.provider is authoritative over prefix inference:
        provider="openai" on a claude-* model still builds the OpenAI adapter."""
        from kaizen_agents.delegate.adapters.openai_adapter import OpenAIStreamAdapter
        from kaizen_agents.delegate.config.loader import KzConfig
        from kaizen_agents.delegate.delegate import Delegate

        # api_key lives on the KzConfig: when config= is passed, Delegate uses it
        # verbatim and does not thread the separate api_key= param onto it.
        cfg = KzConfig(model="claude-3-5-sonnet", provider="openai", api_key=_FAKE_KEY)
        delegate = Delegate(config=cfg, ungoverned=True)
        adapter = _loop_adapter(delegate)
        assert isinstance(adapter, OpenAIStreamAdapter), (
            "an explicit provider='openai' must win over the claude-* prefix, "
            f"got {type(adapter).__name__}"
        )
        assert "api.openai.com" in str(adapter._client.base_url)

    def test_explicit_base_url_still_wins_over_prefix(self):
        """Non-regression guard for #1899: a passed deployment endpoint on a
        claude-* model still routes to the OpenAI-compatible wire at that
        endpoint (base_url precedence unchanged by the #1918 fix)."""
        from kaizen_agents.delegate.adapters.openai_adapter import OpenAIStreamAdapter
        from kaizen_agents.delegate.delegate import Delegate

        endpoint = "https://my-deployment.example.com/v1"
        delegate = Delegate(
            model="claude-3-5-sonnet",
            base_url=endpoint,
            api_key=_FAKE_KEY,
            ungoverned=True,
        )
        adapter = _loop_adapter(delegate)
        assert isinstance(adapter, OpenAIStreamAdapter)
        assert str(adapter._client.base_url).rstrip("/") == endpoint

    def test_temperature_max_tokens_overrides_reach_config(self):
        """Regression guard (#1899-class, one field over): the documented
        temperature/max_tokens overrides on Delegate.__init__ MUST reach the
        KzConfig the loop reads. Previously both were accepted + documented but
        omitted from the zero-config KzConfig build, so the caller's override was
        silently dropped and the KzConfig defaults (0.4 / 16384) always won."""
        from kaizen_agents.delegate.delegate import Delegate

        delegate = Delegate(
            model="gpt-4o",
            temperature=0.91,
            max_tokens=1234,
            api_key=_FAKE_KEY,
            ungoverned=True,
        )
        assert delegate._config.temperature == 0.91, (
            "explicit temperature override was dropped before the KzConfig build "
            "(#1899-class documented-kwarg drop)"
        )
        assert delegate._config.max_tokens == 1234, (
            "explicit max_tokens override was dropped before the KzConfig build "
            "(#1899-class documented-kwarg drop)"
        )

    def test_unset_temperature_max_tokens_inherit_config_defaults(self):
        """A Delegate built WITHOUT temperature/max_tokens MUST inherit the
        KzConfig defaults (0.4 / 16384), not None — the override plumbing only
        forwards the values when the caller sets them (the dataclass fields are
        non-Optional, so forwarding None would clobber the default)."""
        from kaizen_agents.delegate.config.loader import KzConfig
        from kaizen_agents.delegate.delegate import Delegate

        delegate = Delegate(model="gpt-4o", api_key=_FAKE_KEY, ungoverned=True)
        assert delegate._config.temperature == KzConfig.temperature
        assert delegate._config.max_tokens == KzConfig.max_tokens

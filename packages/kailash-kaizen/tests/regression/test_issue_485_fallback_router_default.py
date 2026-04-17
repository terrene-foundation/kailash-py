"""
Regression test for GitHub Issue #485:
fix(kaizen): FallbackRouter.__init__ must not inherit OPENAI_PROD_MODEL as default.

Reported by @vflores-io. When a user constructs a FallbackRouter with a
Gemini-only (or Anthropic-only) fallback chain and does NOT pass
default_model, the pre-fix code silently read the process-wide
OPENAI_PROD_MODEL env var as the default. That value was an OpenAI model
name; the fallback chain then had to rescue every single call to make
the router appear to work against Gemini. Operators who had OPENAI_PROD_MODEL
set for unrelated reasons got invisible OpenAI coupling in every other
router they built.

Fix: if default_model is not provided, use fallback_chain[0] as the default.
Raise ValueError when neither is supplied. Never consult
OPENAI_PROD_MODEL / DEFAULT_LLM_MODEL from FallbackRouter.__init__.
"""

from unittest.mock import patch

import pytest

from kaizen.llm.routing.fallback import FallbackRouter


@pytest.mark.regression
class TestIssue485FallbackRouterDefaultModel:
    """Regression guards for GH #485 — OPENAI_PROD_MODEL leak into non-OpenAI routers."""

    def test_gemini_chain_does_not_inherit_openai_prod_model(self, monkeypatch):
        """Reproduction: Gemini-only chain must not pick up OPENAI_PROD_MODEL as default.

        Pre-fix: router.default_model would be "gpt-5-2025-08-07" (from env).
        Post-fix: router.default_model must be "gemini-3-flash-preview"
        (the first entry of the supplied fallback_chain).
        """
        monkeypatch.setenv("OPENAI_PROD_MODEL", "gpt-5-2025-08-07")
        monkeypatch.setenv("DEFAULT_LLM_MODEL", "gpt-5-2025-08-07")

        router = FallbackRouter(
            fallback_chain=[
                "gemini-3-flash-preview",
                "gemini-3-pro-preview",
            ],
        )

        assert router.default_model == "gemini-3-flash-preview"
        assert router.default_model != "gpt-5-2025-08-07"
        assert "gpt" not in router.default_model.lower()

    def test_anthropic_chain_does_not_inherit_openai_prod_model(self, monkeypatch):
        """Same issue, different non-OpenAI provider — Anthropic-only chain."""
        monkeypatch.setenv("OPENAI_PROD_MODEL", "gpt-5-2025-08-07")

        router = FallbackRouter(
            fallback_chain=["claude-sonnet-5", "claude-haiku-5"],
        )

        assert router.default_model == "claude-sonnet-5"
        assert router.default_model != "gpt-5-2025-08-07"

    def test_explicit_default_model_is_respected(self, monkeypatch):
        """Explicit default_model MUST win regardless of env vars or chain."""
        monkeypatch.setenv("OPENAI_PROD_MODEL", "gpt-5-2025-08-07")

        router = FallbackRouter(
            default_model="mistral-large-latest",
            fallback_chain=["claude-sonnet-5", "gemini-3-flash-preview"],
        )

        assert router.default_model == "mistral-large-latest"

    def test_no_default_no_chain_raises_value_error(self, monkeypatch):
        """No default_model AND no fallback_chain → explicit ValueError.

        Previous behaviour silently returned whatever OPENAI_PROD_MODEL or
        DEFAULT_LLM_MODEL happened to be set to (or None). That was a footgun.
        The new contract is loud-or-silent: the caller must opt in to a model.
        """
        monkeypatch.delenv("OPENAI_PROD_MODEL", raising=False)
        monkeypatch.delenv("DEFAULT_LLM_MODEL", raising=False)

        with pytest.raises(ValueError, match="default_model.*fallback_chain"):
            FallbackRouter()

    def test_no_default_no_chain_raises_even_when_env_is_set(self, monkeypatch):
        """Even with OPENAI_PROD_MODEL set, missing default AND chain must raise.

        This is the specific sharp edge: pre-fix, setting OPENAI_PROD_MODEL
        silently suppressed the error, producing a router with an OpenAI
        default that the caller never asked for.
        """
        monkeypatch.setenv("OPENAI_PROD_MODEL", "gpt-5-2025-08-07")
        monkeypatch.setenv("DEFAULT_LLM_MODEL", "gpt-5-2025-08-07")

        with pytest.raises(ValueError, match="default_model.*fallback_chain"):
            FallbackRouter()

    def test_default_from_chain_when_no_explicit_default(self):
        """default_model=None + chain → chain[0] is the default."""
        router = FallbackRouter(
            fallback_chain=["first-model", "second-model", "third-model"],
        )

        assert router.default_model == "first-model"

    def test_reproduction_from_issue_report(self, monkeypatch):
        """Exact snippet flavour from the issue reporter's setup.

        User @vflores-io: 'I'm running Gemini-only in staging, I had
        OPENAI_PROD_MODEL set from an earlier OpenAI experiment, and my
        FallbackRouter silently came up with gpt-5-2025-08-07 as default.'
        """
        # Simulate the reporter's environment — OPENAI_PROD_MODEL set for
        # unrelated reasons (previous OpenAI experiment, shared .env).
        monkeypatch.setenv("OPENAI_PROD_MODEL", "gpt-5-2025-08-07")

        # Reporter's router construction — Gemini-only fallback chain, no
        # explicit default_model.
        router = FallbackRouter(
            fallback_chain=[
                "gemini-3-flash-preview",
                "gemini-3-pro-preview",
            ],
        )

        # The bug: default was "gpt-5-2025-08-07". The fix: default is
        # the first entry of the chain the reporter supplied.
        assert router.default_model == "gemini-3-flash-preview"

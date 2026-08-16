"""
Test: Agent llm_provider parameter support

This test verifies that the Agent class correctly accepts and forwards
the llm_provider parameter to AgentConfig.

Bug Fix Summary (2026-01-15):
- Added llm_provider as explicit parameter to Agent.__init__
- Agent now forwards llm_provider to AgentConfig
- AgentConfig auto-detection only triggers when llm_provider is None

File References:
- /packages/kailash-kaizen/src/kaizen/agent.py:77 (llm_provider parameter)
- /packages/kailash-kaizen/src/kaizen/agent.py:175 (forwarding to AgentConfig)
- /packages/kailash-kaizen/src/kaizen/agent_config.py:253-257 (__post_init__ auto-detection)
"""

import inspect

import pytest


class TestAgentLLMProviderParameter:
    """Test Agent correctly accepts and uses llm_provider parameter."""

    def test_agent_config_respects_explicit_llm_provider(self):
        """AgentConfig should respect explicit llm_provider."""
        from kaizen.agent_config import AgentConfig

        config = AgentConfig(model="gpt-4", llm_provider="ollama")
        assert config.llm_provider == "ollama"

    def test_agent_config_auto_detects_when_not_provided(self):
        """AgentConfig should auto-detect provider when not specified."""
        from kaizen.agent_config import AgentConfig

        config = AgentConfig(model="gpt-4")
        assert config.llm_provider == "openai"

    def test_agent_has_llm_provider_parameter(self):
        """Agent.__init__ should have llm_provider as explicit parameter."""
        from kaizen.agent import Agent

        sig = inspect.signature(Agent.__init__)
        params = list(sig.parameters.keys())

        assert (
            "llm_provider" in params
        ), "Agent.__init__ should have llm_provider as explicit parameter"

    def test_agent_forwards_llm_provider_to_config(self):
        """Agent should forward llm_provider to AgentConfig."""
        from kaizen.agent import Agent

        source = inspect.getsource(Agent.__init__)
        config_call_start = source.find("self.config = AgentConfig(")
        assert config_call_start != -1, "Agent should create AgentConfig"

        # Verify llm_provider is passed to AgentConfig
        config_call_end = source.find(")", config_call_start + 100)
        config_call = source[config_call_start : config_call_end + 1]
        assert (
            "llm_provider=" in config_call
        ), "Agent should forward llm_provider to AgentConfig"

    def test_agent_respects_explicit_ollama_provider(self):
        """Agent should respect explicit llm_provider='ollama'."""
        from kaizen.agent import Agent

        agent = Agent(
            model="gpt-4",
            llm_provider="ollama",
            show_startup_banner=False,
        )
        assert agent.config.llm_provider == "ollama"

    def test_agent_respects_explicit_anthropic_provider(self):
        """Agent should respect explicit llm_provider='anthropic'."""
        from kaizen.agent import Agent

        agent = Agent(
            model="gpt-4",  # Model name suggests OpenAI
            llm_provider="anthropic",  # But user wants Anthropic
            show_startup_banner=False,
        )
        assert agent.config.llm_provider == "anthropic"

    def test_agent_respects_explicit_azure_provider(self):
        """Agent should respect explicit llm_provider='azure'."""
        from kaizen.agent import Agent

        agent = Agent(
            model="cashflow-gpt5",  # Azure deployment name
            llm_provider="azure",  # User explicitly wants Azure
            show_startup_banner=False,
        )
        # Without fix: would auto-detect "openai" from "gpt" in name
        # With fix: respects explicit "azure"
        assert agent.config.llm_provider == "azure"

    def test_agent_respects_explicit_google_provider(self):
        """Agent should respect explicit llm_provider='google'."""
        from kaizen.agent import Agent

        agent = Agent(
            model="custom-model",  # Unknown model
            llm_provider="google",  # Explicit Google provider
            show_startup_banner=False,
        )
        assert agent.config.llm_provider == "google"

    def test_agent_auto_detects_when_llm_provider_not_specified(self):
        """Agent should auto-detect provider when llm_provider is None."""
        from kaizen.agent import Agent

        agent = Agent(
            model="gpt-4",
            # llm_provider not specified - should auto-detect
            show_startup_banner=False,
        )
        assert agent.config.llm_provider == "openai"

    def test_agent_auto_detects_claude_as_anthropic(self):
        """Agent should auto-detect 'claude' models as anthropic provider."""
        from kaizen.agent import Agent

        agent = Agent(
            model="claude-3-opus",
            # llm_provider not specified
            show_startup_banner=False,
        )
        assert agent.config.llm_provider == "anthropic"


class TestAgentLLMProviderEdgeCases:
    """Test edge cases for llm_provider parameter validation."""

    def test_empty_string_provider_raises_error(self):
        """Empty string llm_provider should raise ValueError."""
        from kaizen.agent_config import AgentConfig

        with pytest.raises(ValueError) as exc_info:
            AgentConfig(model="gpt-4", llm_provider="")

        assert "cannot be empty string" in str(exc_info.value)

    def test_invalid_provider_raises_error(self):
        """Invalid llm_provider should raise ValueError."""
        from kaizen.agent_config import AgentConfig

        with pytest.raises(ValueError) as exc_info:
            AgentConfig(model="gpt-4", llm_provider="invalid_provider")

        assert "Invalid llm_provider" in str(exc_info.value)
        assert "invalid_provider" in str(exc_info.value)

    def test_typo_in_provider_raises_error(self):
        """Typo in provider name (e.g., 'azur') should raise ValueError."""
        from kaizen.agent_config import AgentConfig

        with pytest.raises(ValueError) as exc_info:
            AgentConfig(model="gpt-4", llm_provider="azur")

        assert "Invalid llm_provider" in str(exc_info.value)

    def test_case_insensitive_provider_validation(self):
        """Provider validation should be case-insensitive."""
        from kaizen.agent_config import AgentConfig

        # Uppercase should be valid
        config = AgentConfig(model="gpt-4", llm_provider="AZURE")
        assert config.llm_provider == "AZURE"  # Preserved as-is

        # Mixed case should be valid
        config2 = AgentConfig(model="gpt-4", llm_provider="Azure")
        assert config2.llm_provider == "Azure"

    def test_all_valid_providers_accepted(self):
        """All valid provider names should be accepted."""
        from kaizen.agent_config import AgentConfig

        valid_providers = [
            "openai",
            "azure",
            "anthropic",
            "ollama",
            "docker",
            "cohere",
            "huggingface",
            "google",
            "gemini",
            "perplexity",
            "pplx",
            "mock",
        ]

        for provider in valid_providers:
            config = AgentConfig(model="test-model", llm_provider=provider)
            assert (
                config.llm_provider == provider
            ), f"Provider {provider} should be valid"

    def test_agent_rejects_empty_string_provider(self):
        """Agent should reject empty string llm_provider."""
        from kaizen.agent import Agent

        with pytest.raises(ValueError) as exc_info:
            Agent(
                model="gpt-4",
                llm_provider="",
                show_startup_banner=False,
            )

        assert "cannot be empty string" in str(exc_info.value)

    def test_agent_rejects_invalid_provider(self):
        """Agent should reject invalid llm_provider."""
        from kaizen.agent import Agent

        with pytest.raises(ValueError) as exc_info:
            Agent(
                model="gpt-4",
                llm_provider="not_a_real_provider",
                show_startup_banner=False,
            )

        assert "Invalid llm_provider" in str(exc_info.value)


class TestAgentLLMProviderAutoDetection:
    """Test auto-detection of llm_provider from model names."""

    def test_auto_detect_gpt_models_as_openai(self):
        """GPT models should auto-detect as openai."""
        from kaizen.agent_config import AgentConfig

        for model in ["gpt-4", "gpt-3.5-turbo", "gpt-4o", "gpt-4-turbo"]:
            config = AgentConfig(model=model)
            assert config.llm_provider == "openai", f"{model} should detect as openai"

    def test_auto_detect_davinci_as_openai(self, monkeypatch):
        """Davinci resolves as openai via the ENV fallback, not a prefix row.

        #2069 changed the mechanism. Detection used to substring-match
        "davinci"; it now delegates to the shared resolver, whose prefix table
        is derived from the provider registry and has no davinci row. So the
        model falls through to the env fallback, which answers openai when an
        OpenAI credential is present — the correct answer, reached honestly.
        With no credential it raises rather than guessing, which is the point
        of the issue.
        """
        from kaizen.agent_config import AgentConfig

        monkeypatch.setenv("OPENAI_API_KEY", "sk-2069-placeholder-not-sent")
        config = AgentConfig(model="davinci-002")
        assert config.llm_provider == "openai"

    def test_auto_detect_claude_as_anthropic(self):
        """Claude models should auto-detect as anthropic."""
        from kaizen.agent_config import AgentConfig

        for model in ["claude-3-opus", "claude-3-sonnet", "claude-2"]:
            config = AgentConfig(model=model)
            assert (
                config.llm_provider == "anthropic"
            ), f"{model} should detect as anthropic"

    @pytest.mark.parametrize("model", ["llama-3.1", "mistral-7b"])
    def test_local_models_no_longer_auto_detect_as_ollama(self, model, monkeypatch):
        """BEHAVIOUR CHANGE (#2069): llama/mistral no longer imply ollama.

        The old substring table mapped these to ollama. Delegation removed
        that mapping along with the rest of the table, and the shared resolver
        has no ollama row — its prefix table is registry-derived and ollama
        serves arbitrary model names, so no prefix identifies it.

        The practical consequence, stated plainly because it is the one
        user-visible regression in this change: a local Ollama user who
        relied on `Agent(model="llama-3.1")` must now pass
        `llm_provider="ollama"` explicitly. That path is asserted below so the
        supported alternative is pinned, not merely described.

        If implicit ollama detection is wanted back, it belongs in the shared
        resolver where every caller gets it — re-adding a private table here
        would rebuild exactly the drift #2069 removed.
        """
        from kaizen.agent_config import AgentConfig

        monkeypatch.delenv("KAIZEN_ALLOW_KEYLESS_MOCK", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

        with pytest.raises(Exception, match=model):
            AgentConfig(model=model)

        # The supported path: say which provider serves it.
        assert AgentConfig(model=model, llm_provider="ollama").llm_provider == "ollama"

    def test_auto_detect_gemini_as_google(self):
        """Gemini models should auto-detect as google."""
        from kaizen.agent_config import AgentConfig

        config = AgentConfig(model="gemini-pro")
        assert config.llm_provider == "google"

    def test_unknown_model_fails_closed_not_defaults_to_openai(self, monkeypatch):
        """INVERTED by #2069 — this test used to assert the defect.

        It read "Unknown models should default to openai" and pinned exactly
        the silent wrong-vendor dispatch the issue was filed about: an
        unrecognised model went to OpenAI under whatever credential was
        configured, carrying the prompt with it. A test asserting the bug is
        why the bug survived, so it is inverted here rather than deleted —
        the same name should not quietly stop covering the same line.
        """
        from kaizen.agent_config import AgentConfig

        monkeypatch.delenv("KAIZEN_ALLOW_KEYLESS_MOCK", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

        with pytest.raises(Exception, match="some-custom-model"):
            AgentConfig(model="some-custom-model")

    def test_azure_deployment_not_auto_detected(self, monkeypatch):
        """Azure deployment names containing 'gpt' must not become openai.

        The conclusion is unchanged — Azure needs an explicit provider,
        because a deployment name cannot distinguish Azure from OpenAI — but
        #2069 made the mechanism honest. The old substring table matched "gpt"
        anywhere and silently answered openai for a name like "cashflow-gpt5".
        The registry table matches the "gpt-" PREFIX, so this name resolves
        through nothing and fails closed instead of being quietly misrouted to
        the wrong vendor.
        """
        from kaizen.agent_config import AgentConfig

        monkeypatch.delenv("KAIZEN_ALLOW_KEYLESS_MOCK", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

        with pytest.raises(Exception, match="cashflow-gpt5"):
            AgentConfig(model="cashflow-gpt5")

        # To use Azure, must be explicit — unchanged.
        config2 = AgentConfig(model="cashflow-gpt5", llm_provider="azure")
        assert config2.llm_provider == "azure"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

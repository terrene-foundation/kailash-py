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

    def test_auto_detect_davinci_as_openai(self):
        """Davinci models should auto-detect as openai."""
        from kaizen.agent_config import AgentConfig

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

    def test_auto_detect_llama_as_ollama(self):
        """Llama models should auto-detect as ollama."""
        from kaizen.agent_config import AgentConfig

        config = AgentConfig(model="llama-3.1")
        assert config.llm_provider == "ollama"

    def test_auto_detect_mistral_as_ollama(self):
        """Mistral models should auto-detect as ollama."""
        from kaizen.agent_config import AgentConfig

        config = AgentConfig(model="mistral-7b")
        assert config.llm_provider == "ollama"

    def test_auto_detect_gemini_as_google(self):
        """Gemini models should auto-detect as google."""
        from kaizen.agent_config import AgentConfig

        config = AgentConfig(model="gemini-pro")
        assert config.llm_provider == "google"

    def test_unknown_model_defaults_to_openai(self):
        """Unknown models should default to openai."""
        from kaizen.agent_config import AgentConfig

        config = AgentConfig(model="some-custom-model")
        assert config.llm_provider == "openai"

    def test_azure_deployment_not_auto_detected(self):
        """Azure deployment names with 'gpt' should NOT auto-detect azure.

        This documents the expected behavior: Azure deployments need explicit
        llm_provider='azure' because the model name alone cannot distinguish
        Azure from OpenAI.
        """
        from kaizen.agent_config import AgentConfig

        # Azure deployment with gpt in name - would be detected as openai
        config = AgentConfig(model="cashflow-gpt5")
        assert config.llm_provider == "openai"  # NOT azure

        # To use Azure, must be explicit
        config2 = AgentConfig(model="cashflow-gpt5", llm_provider="azure")
        assert config2.llm_provider == "azure"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

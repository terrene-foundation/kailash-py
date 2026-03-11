"""
Unit tests for async features in BaseAgentConfig.

Tests async configuration parameters without requiring node infrastructure.
"""

import pytest
from kaizen.core.config import BaseAgentConfig


class TestBaseAgentConfigAsyncFeatures:
    """Test async configuration parameters in BaseAgentConfig."""

    def test_use_async_llm_parameter_exists(self):
        """Test use_async_llm parameter exists in BaseAgentConfig."""
        config = BaseAgentConfig(
            llm_provider="openai", model="gpt-4", use_async_llm=True
        )
        assert hasattr(config, "use_async_llm")
        assert config.use_async_llm is True

    def test_use_async_llm_defaults_to_false(self):
        """Test use_async_llm defaults to False for backwards compatibility."""
        config = BaseAgentConfig(llm_provider="openai", model="gpt-4")
        assert config.use_async_llm is False

    def test_use_async_llm_with_openai_provider(self):
        """Test use_async_llm works with OpenAI provider."""
        config = BaseAgentConfig(
            llm_provider="openai", model="gpt-4", use_async_llm=True
        )
        assert config.use_async_llm is True
        assert config.llm_provider == "openai"

    def test_use_async_llm_with_none_provider(self):
        """Test use_async_llm works with None provider (will be set later)."""
        config = BaseAgentConfig(llm_provider=None, model="gpt-4", use_async_llm=True)
        assert config.use_async_llm is True
        assert config.llm_provider is None

    def test_use_async_llm_rejects_non_openai_provider(self):
        """Test use_async_llm rejects non-OpenAI providers."""
        with pytest.raises(
            ValueError, match="Async mode only supported for OpenAI provider"
        ):
            BaseAgentConfig(llm_provider="ollama", model="llama2", use_async_llm=True)

    def test_use_async_llm_rejects_anthropic_provider(self):
        """Test use_async_llm rejects Anthropic provider."""
        with pytest.raises(
            ValueError, match="Async mode only supported for OpenAI provider"
        ):
            BaseAgentConfig(
                llm_provider="anthropic", model="claude-3", use_async_llm=True
            )

    def test_use_async_llm_type_validation(self):
        """Test use_async_llm must be boolean."""
        # Valid boolean values
        config_true = BaseAgentConfig(llm_provider="openai", use_async_llm=True)
        assert config_true.use_async_llm is True

        config_false = BaseAgentConfig(llm_provider="openai", use_async_llm=False)
        assert config_false.use_async_llm is False

    def test_use_async_llm_with_all_parameters(self):
        """Test use_async_llm works with full configuration."""
        config = BaseAgentConfig(
            llm_provider="openai",
            model="gpt-4-turbo",
            temperature=0.7,
            max_tokens=1000,
            use_async_llm=True,
            strategy_type="single_shot",
            max_cycles=5,
        )
        assert config.use_async_llm is True
        assert config.llm_provider == "openai"
        assert config.model == "gpt-4-turbo"
        assert config.temperature == 0.7
        assert config.max_tokens == 1000

    def test_from_domain_config_preserves_use_async_llm_from_dict(self):
        """Test from_domain_config() preserves use_async_llm from dict."""
        domain_config_dict = {
            "llm_provider": "openai",
            "model": "gpt-4",
            "use_async_llm": True,
            "temperature": 0.5,
        }
        config = BaseAgentConfig.from_domain_config(domain_config_dict)
        assert config.use_async_llm is True
        assert config.llm_provider == "openai"
        assert config.temperature == 0.5

    def test_from_domain_config_defaults_use_async_llm_when_missing(self):
        """Test from_domain_config() defaults use_async_llm to False when missing."""
        domain_config_dict = {"llm_provider": "openai", "model": "gpt-4"}
        config = BaseAgentConfig.from_domain_config(domain_config_dict)
        assert config.use_async_llm is False

    def test_from_domain_config_preserves_use_async_llm_from_object(self):
        """Test from_domain_config() preserves use_async_llm from object."""
        from dataclasses import dataclass

        @dataclass
        class DomainConfig:
            llm_provider: str = "openai"
            model: str = "gpt-4"
            use_async_llm: bool = True
            temperature: float = 0.7

        domain_config_obj = DomainConfig()
        config = BaseAgentConfig.from_domain_config(domain_config_obj)
        assert config.use_async_llm is True
        assert config.llm_provider == "openai"
        assert config.temperature == 0.7

    def test_use_async_llm_false_allows_any_provider(self):
        """Test use_async_llm=False allows any provider (backwards compat)."""
        # Should not raise with any provider when use_async_llm=False
        config_ollama = BaseAgentConfig(
            llm_provider="ollama", model="llama2", use_async_llm=False
        )
        assert config_ollama.use_async_llm is False

        config_anthropic = BaseAgentConfig(
            llm_provider="anthropic", model="claude-3", use_async_llm=False
        )
        assert config_anthropic.use_async_llm is False

    def test_multiple_configs_with_different_async_settings(self):
        """Test multiple configs can have different async settings."""
        config_sync = BaseAgentConfig(
            llm_provider="openai", model="gpt-4", use_async_llm=False
        )

        config_async = BaseAgentConfig(
            llm_provider="openai", model="gpt-4", use_async_llm=True
        )

        assert config_sync.use_async_llm is False
        assert config_async.use_async_llm is True
        assert config_sync != config_async  # Should be different configs

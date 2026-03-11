"""Unit tests for Perplexity AI provider."""

import pytest

from kaizen.nodes.ai.ai_providers import PerplexityProvider


class TestPerplexityProviderAvailability:
    """Tests for provider availability checking."""

    def test_is_available_with_api_key(self, monkeypatch):
        """Should return True when PERPLEXITY_API_KEY is set."""
        monkeypatch.setenv("PERPLEXITY_API_KEY", "pplx-test-key")
        provider = PerplexityProvider()
        assert provider.is_available() is True

    def test_is_available_without_api_key(self, monkeypatch):
        """Should return False when PERPLEXITY_API_KEY is not set."""
        monkeypatch.delenv("PERPLEXITY_API_KEY", raising=False)
        provider = PerplexityProvider()
        # Reset cached availability
        provider._available = None
        assert provider.is_available() is False

    def test_is_available_caches_result(self, monkeypatch):
        """Should cache the availability check result."""
        monkeypatch.setenv("PERPLEXITY_API_KEY", "pplx-test-key")
        provider = PerplexityProvider()

        # First call
        result1 = provider.is_available()

        # Remove key but cached value should persist
        monkeypatch.delenv("PERPLEXITY_API_KEY")
        result2 = provider.is_available()

        assert result1 is True
        assert result2 is True  # Cached value


class TestPerplexityProviderCapabilities:
    """Tests for provider capabilities."""

    def test_capabilities_chat_only(self):
        """Should report chat capability only (no embeddings)."""
        provider = PerplexityProvider()
        caps = provider.get_capabilities()
        assert caps["chat"] is True
        assert caps["embeddings"] is False

    def test_supports_chat(self):
        """Should support chat operations."""
        provider = PerplexityProvider()
        assert provider.supports_chat() is True

    def test_does_not_support_embeddings(self):
        """Should not support embedding operations."""
        provider = PerplexityProvider()
        assert provider.supports_embeddings() is False


class TestPerplexityProviderInitialization:
    """Tests for provider initialization."""

    def test_default_initialization(self):
        """Should initialize with default values."""
        provider = PerplexityProvider()
        assert provider._use_async is False
        assert provider._sync_client is None
        assert provider._async_client is None

    def test_async_initialization(self):
        """Should accept use_async parameter."""
        provider = PerplexityProvider(use_async=True)
        assert provider._use_async is True

        provider = PerplexityProvider(use_async=False)
        assert provider._use_async is False

    def test_base_url_constant(self):
        """Should have correct base URL."""
        assert PerplexityProvider.BASE_URL == "https://api.perplexity.ai"

    def test_default_model_constant(self):
        """Should have correct default model."""
        assert PerplexityProvider.DEFAULT_MODEL == "sonar"


class TestPerplexityProviderApiKey:
    """Tests for API key retrieval."""

    def test_get_api_key_returns_value(self, monkeypatch):
        """Should return API key from environment."""
        monkeypatch.setenv("PERPLEXITY_API_KEY", "pplx-test-key-12345")
        provider = PerplexityProvider()
        assert provider._get_api_key() == "pplx-test-key-12345"

    def test_get_api_key_raises_without_key(self, monkeypatch):
        """Should raise RuntimeError when API key is not set."""
        monkeypatch.delenv("PERPLEXITY_API_KEY", raising=False)
        provider = PerplexityProvider()
        with pytest.raises(RuntimeError, match="PERPLEXITY_API_KEY not found"):
            provider._get_api_key()


class TestPerplexityProviderSupportedModels:
    """Tests for supported models information."""

    def test_get_supported_models(self):
        """Should return supported models info."""
        provider = PerplexityProvider()
        models = provider.get_supported_models()

        assert "sonar" in models
        assert "sonar-pro" in models
        assert "sonar-reasoning" in models
        assert "sonar-reasoning-pro" in models
        assert "sonar-deep-research" in models

    def test_sonar_model_info(self):
        """Should have correct info for sonar model."""
        provider = PerplexityProvider()
        models = provider.get_supported_models()

        sonar = models["sonar"]
        assert sonar["supports_search"] is True
        assert sonar["supports_citations"] is True
        assert sonar["context_length"] == 128000

    def test_sonar_deep_research_supports_reasoning_effort(self):
        """Should indicate reasoning_effort support for sonar-deep-research."""
        provider = PerplexityProvider()
        models = provider.get_supported_models()

        deep_research = models["sonar-deep-research"]
        assert deep_research["supports_reasoning_effort"] is True

    def test_get_supported_models_returns_copy(self):
        """Should return a copy to prevent modification."""
        provider = PerplexityProvider()
        models1 = provider.get_supported_models()
        models2 = provider.get_supported_models()

        # Modify one
        models1["test"] = "value"

        # Other should not be affected
        assert "test" not in models2


class TestPerplexityProviderProcessMessages:
    """Tests for message processing."""

    def test_process_simple_text_messages(self):
        """Should process simple text messages."""
        provider = PerplexityProvider()
        messages = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Hello!"},
        ]

        processed = provider._process_messages(messages)

        assert len(processed) == 2
        assert processed[0]["role"] == "system"
        assert processed[0]["content"] == "You are helpful."
        assert processed[1]["role"] == "user"
        assert processed[1]["content"] == "Hello!"

    def test_process_complex_text_content(self):
        """Should extract text from complex content."""
        provider = PerplexityProvider()
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Describe this:"},
                    {"type": "text", "text": "Additional context"},
                ],
            }
        ]

        processed = provider._process_messages(messages)

        assert len(processed) == 1
        assert processed[0]["role"] == "user"
        assert isinstance(processed[0]["content"], list)
        assert len(processed[0]["content"]) == 2
        assert processed[0]["content"][0]["type"] == "text"
        assert processed[0]["content"][0]["text"] == "Describe this:"

    def test_process_image_url_content(self):
        """Should handle image URLs in content."""
        provider = PerplexityProvider()
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "What is this?"},
                    {"type": "image", "url": "https://example.com/image.jpg"},
                ],
            }
        ]

        processed = provider._process_messages(messages)

        assert len(processed) == 1
        content = processed[0]["content"]
        assert len(content) == 2
        assert content[1]["type"] == "image_url"
        assert content[1]["image_url"]["url"] == "https://example.com/image.jpg"

    def test_process_empty_content(self):
        """Should handle empty content."""
        provider = PerplexityProvider()
        messages = [{"role": "user", "content": ""}]

        processed = provider._process_messages(messages)

        assert processed[0]["content"] == ""


class TestPerplexityProviderBuildRequestParams:
    """Tests for request parameter building."""

    def test_basic_params(self):
        """Should build basic request parameters."""
        provider = PerplexityProvider()
        messages = [{"role": "user", "content": "Hello"}]
        generation_config = {}

        params = provider._build_request_params(messages, "sonar", generation_config)

        assert params["model"] == "sonar"
        assert params["messages"] == messages
        assert params["temperature"] == 0.2  # Perplexity default
        assert params["top_p"] == 0.9  # Perplexity default

    def test_generation_config_params(self):
        """Should include generation config parameters."""
        provider = PerplexityProvider()
        messages = [{"role": "user", "content": "Hello"}]
        generation_config = {
            "temperature": 0.7,
            "max_tokens": 1000,
            "top_p": 0.95,
            "presence_penalty": 0.5,
            "frequency_penalty": 0.3,
            "stop": ["END"],
        }

        params = provider._build_request_params(
            messages, "sonar-pro", generation_config
        )

        assert params["temperature"] == 0.7
        assert params["max_tokens"] == 1000
        assert params["top_p"] == 0.95
        assert params["presence_penalty"] == 0.5
        assert params["frequency_penalty"] == 0.3
        assert params["stop"] == ["END"]

    def test_return_related_questions(self):
        """Should include return_related_questions in extra_body."""
        provider = PerplexityProvider()
        messages = [{"role": "user", "content": "Hello"}]

        params = provider._build_request_params(
            messages,
            "sonar",
            {},
            perplexity_config={"return_related_questions": True},
        )

        assert "extra_body" in params
        assert params["extra_body"]["return_related_questions"] is True

    def test_return_images(self):
        """Should include return_images in extra_body."""
        provider = PerplexityProvider()
        messages = [{"role": "user", "content": "Hello"}]

        params = provider._build_request_params(
            messages,
            "sonar",
            {},
            perplexity_config={"return_images": True},
        )

        assert "extra_body" in params
        assert params["extra_body"]["return_images"] is True

    def test_search_domain_filter(self):
        """Should include domain filter in extra_body."""
        provider = PerplexityProvider()
        messages = [{"role": "user", "content": "Hello"}]
        domains = ["example.com", "test.org"]

        params = provider._build_request_params(
            messages,
            "sonar",
            {},
            perplexity_config={"search_domain_filter": domains},
        )

        assert "extra_body" in params
        assert params["extra_body"]["search_domain_filter"] == domains

    def test_search_domain_filter_max_20(self):
        """Should reject more than 20 domains."""
        provider = PerplexityProvider()
        messages = [{"role": "user", "content": "Hello"}]
        domains = [f"domain{i}.com" for i in range(21)]

        with pytest.raises(ValueError, match="maximum 20 domains"):
            provider._build_request_params(
                messages,
                "sonar",
                {},
                perplexity_config={"search_domain_filter": domains},
            )

    def test_search_recency_filter_valid(self):
        """Should accept valid recency filters in extra_body."""
        provider = PerplexityProvider()
        messages = [{"role": "user", "content": "Hello"}]

        for recency in ["month", "week", "day", "hour"]:
            params = provider._build_request_params(
                messages,
                "sonar",
                {},
                perplexity_config={"search_recency_filter": recency},
            )
            assert "extra_body" in params
            assert params["extra_body"]["search_recency_filter"] == recency

    def test_search_recency_filter_invalid(self):
        """Should reject invalid recency filters."""
        provider = PerplexityProvider()
        messages = [{"role": "user", "content": "Hello"}]

        with pytest.raises(ValueError, match="search_recency_filter must be one of"):
            provider._build_request_params(
                messages,
                "sonar",
                {},
                perplexity_config={"search_recency_filter": "invalid"},
            )

    def test_search_mode_valid(self):
        """Should accept valid search modes in extra_body."""
        provider = PerplexityProvider()
        messages = [{"role": "user", "content": "Hello"}]

        for mode in ["web", "academic", "sec"]:
            params = provider._build_request_params(
                messages,
                "sonar",
                {},
                perplexity_config={"search_mode": mode},
            )
            assert "extra_body" in params
            assert params["extra_body"]["search_mode"] == mode

    def test_search_mode_invalid(self):
        """Should reject invalid search modes."""
        provider = PerplexityProvider()
        messages = [{"role": "user", "content": "Hello"}]

        with pytest.raises(ValueError, match="search_mode must be one of"):
            provider._build_request_params(
                messages,
                "sonar",
                {},
                perplexity_config={"search_mode": "invalid"},
            )

    def test_reasoning_effort_for_deep_research(self):
        """Should accept reasoning_effort for sonar-deep-research in extra_body."""
        provider = PerplexityProvider()
        messages = [{"role": "user", "content": "Hello"}]

        for effort in ["low", "medium", "high"]:
            params = provider._build_request_params(
                messages,
                "sonar-deep-research",
                {},
                perplexity_config={"reasoning_effort": effort},
            )
            assert "extra_body" in params
            assert params["extra_body"]["reasoning_effort"] == effort

    def test_reasoning_effort_ignored_for_other_models(self):
        """Should ignore reasoning_effort for non-deep-research models."""
        provider = PerplexityProvider()
        messages = [{"role": "user", "content": "Hello"}]

        params = provider._build_request_params(
            messages,
            "sonar",
            {},
            perplexity_config={"reasoning_effort": "high"},
        )

        # Should not have extra_body or reasoning_effort in it
        assert "extra_body" not in params or "reasoning_effort" not in params.get(
            "extra_body", {}
        )

    def test_reasoning_effort_invalid(self):
        """Should reject invalid reasoning effort values."""
        provider = PerplexityProvider()
        messages = [{"role": "user", "content": "Hello"}]

        with pytest.raises(ValueError, match="reasoning_effort must be one of"):
            provider._build_request_params(
                messages,
                "sonar-deep-research",
                {},
                perplexity_config={"reasoning_effort": "invalid"},
            )

    def test_language_preference(self):
        """Should include language_preference for supported models in extra_body."""
        provider = PerplexityProvider()
        messages = [{"role": "user", "content": "Hello"}]

        for model in ["sonar", "sonar-pro"]:
            params = provider._build_request_params(
                messages,
                model,
                {},
                perplexity_config={"language_preference": "Spanish"},
            )
            assert "extra_body" in params
            assert params["extra_body"]["language_preference"] == "Spanish"

    def test_language_preference_ignored_for_other_models(self):
        """Should ignore language_preference for unsupported models."""
        provider = PerplexityProvider()
        messages = [{"role": "user", "content": "Hello"}]

        params = provider._build_request_params(
            messages,
            "sonar-reasoning",
            {},
            perplexity_config={"language_preference": "Spanish"},
        )

        # Should not have extra_body or language_preference in it
        assert "extra_body" not in params or "language_preference" not in params.get(
            "extra_body", {}
        )

    def test_disable_search(self):
        """Should include disable_search in extra_body."""
        provider = PerplexityProvider()
        messages = [{"role": "user", "content": "Hello"}]

        params = provider._build_request_params(
            messages,
            "sonar",
            {},
            perplexity_config={"disable_search": True},
        )

        assert "extra_body" in params
        assert params["extra_body"]["disable_search"] is True

    def test_date_filters(self):
        """Should include date filter parameters in extra_body."""
        provider = PerplexityProvider()
        messages = [{"role": "user", "content": "Hello"}]

        params = provider._build_request_params(
            messages,
            "sonar",
            {},
            perplexity_config={
                "search_after_date_filter": "01/01/2024",
                "search_before_date_filter": "12/31/2024",
                "last_updated_after_filter": "06/01/2024",
                "last_updated_before_filter": "06/30/2024",
            },
        )

        assert "extra_body" in params
        assert params["extra_body"]["search_after_date_filter"] == "01/01/2024"
        assert params["extra_body"]["search_before_date_filter"] == "12/31/2024"
        assert params["extra_body"]["last_updated_after_filter"] == "06/01/2024"
        assert params["extra_body"]["last_updated_before_filter"] == "06/30/2024"

    def test_web_search_options(self):
        """Should include web_search_options in extra_body."""
        provider = PerplexityProvider()
        messages = [{"role": "user", "content": "Hello"}]

        web_options = {"context_size": "medium", "user_location": {"country": "US"}}
        params = provider._build_request_params(
            messages,
            "sonar",
            {},
            perplexity_config={"web_search_options": web_options},
        )

        assert "extra_body" in params
        assert params["extra_body"]["web_search_options"] == web_options

    def test_response_format(self):
        """Should include response_format for structured output."""
        provider = PerplexityProvider()
        messages = [{"role": "user", "content": "Hello"}]

        response_format = {"type": "json_object"}
        params = provider._build_request_params(
            messages,
            "sonar",
            {"response_format": response_format},
        )

        assert params["response_format"] == response_format

    def test_stream_param(self):
        """Should include stream parameter."""
        provider = PerplexityProvider()
        messages = [{"role": "user", "content": "Hello"}]

        params = provider._build_request_params(
            messages,
            "sonar",
            {},
            stream=True,
        )

        assert params["stream"] is True


class TestPerplexityProviderFormatResponse:
    """Tests for response formatting."""

    def test_format_basic_response(self):
        """Should format basic response correctly."""

        class MockUsage:
            prompt_tokens = 10
            completion_tokens = 20
            total_tokens = 30

        class MockMessage:
            content = "This is the response."
            role = "assistant"

        class MockChoice:
            message = MockMessage()
            finish_reason = "stop"

        class MockResponse:
            id = "resp-123"
            model = "sonar"
            created = 1234567890
            choices = [MockChoice()]
            usage = MockUsage()

        provider = PerplexityProvider()
        result = provider._format_response(MockResponse())

        assert result["id"] == "resp-123"
        assert result["content"] == "This is the response."
        assert result["role"] == "assistant"
        assert result["model"] == "sonar"
        assert result["created"] == 1234567890
        assert result["finish_reason"] == "stop"
        assert result["tool_calls"] == []
        assert result["usage"]["prompt_tokens"] == 10
        assert result["usage"]["completion_tokens"] == 20
        assert result["usage"]["total_tokens"] == 30

    def test_format_response_with_citations(self):
        """Should include citations in metadata."""

        class MockUsage:
            prompt_tokens = 10
            completion_tokens = 20
            total_tokens = 30

        class MockMessage:
            content = "Answer with citations."
            role = "assistant"

        class MockChoice:
            message = MockMessage()
            finish_reason = "stop"

        class MockResponse:
            id = "resp-123"
            model = "sonar"
            created = 1234567890
            choices = [MockChoice()]
            usage = MockUsage()
            citations = ["https://source1.com", "https://source2.com"]

        provider = PerplexityProvider()
        result = provider._format_response(MockResponse())

        assert "citations" in result["metadata"]
        assert result["metadata"]["citations"] == [
            "https://source1.com",
            "https://source2.com",
        ]

    def test_format_response_with_raw_response_citations(self):
        """Should extract citations from raw response dict."""

        class MockUsage:
            prompt_tokens = 10
            completion_tokens = 20
            total_tokens = 30

        class MockMessage:
            content = "Answer."
            role = "assistant"

        class MockChoice:
            message = MockMessage()
            finish_reason = "stop"

        class MockResponse:
            id = "resp-123"
            model = "sonar"
            created = 1234567890
            choices = [MockChoice()]
            usage = MockUsage()

        provider = PerplexityProvider()
        raw_response = {
            "citations": ["https://example.com/article"],
            "related_questions": ["What else?", "More info?"],
        }

        result = provider._format_response(MockResponse(), raw_response)

        assert result["metadata"]["citations"] == ["https://example.com/article"]
        assert result["metadata"]["related_questions"] == ["What else?", "More info?"]

    def test_format_response_empty_content(self):
        """Should handle empty content."""

        class MockUsage:
            prompt_tokens = 5
            completion_tokens = 0
            total_tokens = 5

        class MockMessage:
            content = None
            role = "assistant"

        class MockChoice:
            message = MockMessage()
            finish_reason = "stop"

        class MockResponse:
            id = "resp-456"
            model = "sonar"
            created = 1234567890
            choices = [MockChoice()]
            usage = MockUsage()

        provider = PerplexityProvider()
        result = provider._format_response(MockResponse())

        assert result["content"] == ""


class TestPerplexityProviderChat:
    """Tests for chat method error handling."""

    def test_chat_raises_without_api_key(self, monkeypatch):
        """Should raise RuntimeError when API key not set."""
        monkeypatch.delenv("PERPLEXITY_API_KEY", raising=False)
        provider = PerplexityProvider()
        provider._available = None

        messages = [{"role": "user", "content": "Hello"}]

        with pytest.raises(RuntimeError, match="PERPLEXITY_API_KEY"):
            provider.chat(messages)

    def test_chat_raises_without_openai_library(self, monkeypatch):
        """Should raise RuntimeError when openai library not installed."""
        monkeypatch.setenv("PERPLEXITY_API_KEY", "pplx-test-key")

        # Mock import to fail
        import builtins

        original_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "openai":
                raise ImportError("No module named 'openai'")
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", mock_import)

        provider = PerplexityProvider()
        messages = [{"role": "user", "content": "Hello"}]

        with pytest.raises(RuntimeError, match="OpenAI library not installed"):
            provider.chat(messages)


class TestPerplexityProviderChatAsync:
    """Tests for async chat method."""

    @pytest.mark.asyncio
    async def test_chat_async_raises_without_api_key(self, monkeypatch):
        """Should raise RuntimeError when API key not set."""
        monkeypatch.delenv("PERPLEXITY_API_KEY", raising=False)
        provider = PerplexityProvider()
        provider._available = None

        messages = [{"role": "user", "content": "Hello"}]

        with pytest.raises(RuntimeError, match="PERPLEXITY_API_KEY"):
            await provider.chat_async(messages)


class TestPerplexityProviderRegistry:
    """Tests for provider registration."""

    def test_provider_in_registry(self):
        """Should be registered in PROVIDERS dict."""
        from kaizen.nodes.ai.ai_providers import PROVIDERS

        assert "perplexity" in PROVIDERS
        assert PROVIDERS["perplexity"] is PerplexityProvider

    def test_pplx_alias_in_registry(self):
        """Should have pplx alias in PROVIDERS dict."""
        from kaizen.nodes.ai.ai_providers import PROVIDERS

        assert "pplx" in PROVIDERS
        assert PROVIDERS["pplx"] is PerplexityProvider

    def test_get_provider_returns_perplexity(self):
        """Should return PerplexityProvider from get_provider."""
        from kaizen.nodes.ai.ai_providers import get_provider

        provider = get_provider("perplexity")
        assert isinstance(provider, PerplexityProvider)

    def test_get_provider_with_alias(self):
        """Should return PerplexityProvider using pplx alias."""
        from kaizen.nodes.ai.ai_providers import get_provider

        provider = get_provider("pplx")
        assert isinstance(provider, PerplexityProvider)


class TestPerplexityProviderConfig:
    """Tests for provider configuration."""

    def test_check_perplexity_available_with_key(self, monkeypatch):
        """Should return True when API key is set."""
        from kaizen.config.providers import check_perplexity_available

        monkeypatch.setenv("PERPLEXITY_API_KEY", "pplx-test-key")
        assert check_perplexity_available() is True

    def test_check_perplexity_available_without_key(self, monkeypatch):
        """Should return False when API key not set."""
        from kaizen.config.providers import check_perplexity_available

        monkeypatch.delenv("PERPLEXITY_API_KEY", raising=False)
        assert check_perplexity_available() is False

    def test_get_perplexity_config_default(self, monkeypatch):
        """Should return default configuration."""
        from kaizen.config.providers import get_perplexity_config

        monkeypatch.setenv("PERPLEXITY_API_KEY", "pplx-test-key")
        monkeypatch.delenv("KAIZEN_PERPLEXITY_MODEL", raising=False)

        config = get_perplexity_config()

        assert config.provider == "perplexity"
        assert config.model == "sonar"
        assert config.api_key == "pplx-test-key"
        assert config.base_url == "https://api.perplexity.ai"

    def test_get_perplexity_config_custom_model(self, monkeypatch):
        """Should accept custom model."""
        from kaizen.config.providers import get_perplexity_config

        monkeypatch.setenv("PERPLEXITY_API_KEY", "pplx-test-key")

        config = get_perplexity_config(model="sonar-pro")

        assert config.model == "sonar-pro"

    def test_get_perplexity_config_env_model(self, monkeypatch):
        """Should use KAIZEN_PERPLEXITY_MODEL env var."""
        from kaizen.config.providers import get_perplexity_config

        monkeypatch.setenv("PERPLEXITY_API_KEY", "pplx-test-key")
        monkeypatch.setenv("KAIZEN_PERPLEXITY_MODEL", "sonar-reasoning")

        config = get_perplexity_config()

        assert config.model == "sonar-reasoning"

    def test_get_perplexity_config_raises_without_key(self, monkeypatch):
        """Should raise ConfigurationError without API key."""
        from kaizen.config.providers import ConfigurationError, get_perplexity_config

        monkeypatch.delenv("PERPLEXITY_API_KEY", raising=False)

        with pytest.raises(ConfigurationError, match="PERPLEXITY_API_KEY"):
            get_perplexity_config()

    def test_provider_type_includes_perplexity(self):
        """Should include perplexity in ProviderType."""
        from kaizen.config.providers import ProviderType

        # ProviderType is a Literal, verify via type checking
        # This test validates the type annotation exists
        assert "perplexity" in str(ProviderType)

    def test_get_provider_config_perplexity(self, monkeypatch):
        """Should return Perplexity config via get_provider_config."""
        from kaizen.config.providers import get_provider_config

        monkeypatch.setenv("PERPLEXITY_API_KEY", "pplx-test-key")

        config = get_provider_config(provider="perplexity")

        assert config.provider == "perplexity"
        assert config.model == "sonar"

    def test_get_provider_config_pplx_alias(self, monkeypatch):
        """Should return Perplexity config via pplx alias."""
        from kaizen.config.providers import get_provider_config

        monkeypatch.setenv("PERPLEXITY_API_KEY", "pplx-test-key")

        config = get_provider_config(provider="pplx")

        assert config.provider == "perplexity"

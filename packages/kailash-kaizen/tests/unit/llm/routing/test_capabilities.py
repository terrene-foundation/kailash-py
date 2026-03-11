"""
Unit Tests for LLMCapabilities and Model Registry (Tier 1)

Tests the LLMCapabilities dataclass and MODEL_REGISTRY:
- LLMCapabilities creation and properties
- Capability matching
- Cost estimation
- Registry operations
"""

import pytest

from kaizen.llm.routing.capabilities import (
    MODEL_REGISTRY,
    LLMCapabilities,
    get_best_quality_model,
    get_cheapest_model,
    get_model_capabilities,
    list_models,
    register_model,
)


class TestLLMCapabilitiesCreation:
    """Tests for LLMCapabilities dataclass creation."""

    def test_create_minimal(self):
        """Test creating with minimal parameters."""
        caps = LLMCapabilities(provider="test", model="test-model")

        assert caps.provider == "test"
        assert caps.model == "test-model"
        assert caps.supports_vision is False
        assert caps.supports_tool_calling is True
        assert caps.quality_score == 0.7

    def test_create_full(self):
        """Test creating with all parameters."""
        caps = LLMCapabilities(
            provider="openai",
            model="gpt-4",
            supports_vision=True,
            supports_audio=True,
            supports_tool_calling=True,
            supports_structured_output=True,
            supports_streaming=True,
            max_context=128000,
            max_output=8192,
            cost_per_1k_input=0.03,
            cost_per_1k_output=0.06,
            latency_p50_ms=2000,
            quality_score=0.95,
            specialties=["reasoning", "code"],
        )

        assert caps.provider == "openai"
        assert caps.model == "gpt-4"
        assert caps.supports_vision is True
        assert caps.supports_audio is True
        assert caps.max_context == 128000
        assert caps.cost_per_1k_input == 0.03
        assert caps.quality_score == 0.95
        assert "reasoning" in caps.specialties

    def test_full_name_property(self):
        """Test full_name property."""
        caps = LLMCapabilities(provider="anthropic", model="claude-3-opus")

        assert caps.full_name == "anthropic/claude-3-opus"

    def test_is_free_property(self):
        """Test is_free property for local models."""
        free_model = LLMCapabilities(
            provider="ollama",
            model="llama3",
            cost_per_1k_input=0.0,
            cost_per_1k_output=0.0,
        )
        paid_model = LLMCapabilities(
            provider="openai",
            model="gpt-4",
            cost_per_1k_input=0.03,
            cost_per_1k_output=0.06,
        )

        assert free_model.is_free is True
        assert paid_model.is_free is False

    def test_is_local_property(self):
        """Test is_local property."""
        local = LLMCapabilities(provider="ollama", model="llama3")
        cloud = LLMCapabilities(provider="openai", model="gpt-4")
        docker = LLMCapabilities(provider="docker", model="model")

        assert local.is_local is True
        assert cloud.is_local is False
        assert docker.is_local is True


class TestLLMCapabilitiesSpecialties:
    """Tests for specialty matching."""

    def test_supports_specialty_match(self):
        """Test specialty matching."""
        caps = LLMCapabilities(
            provider="test",
            model="test",
            specialties=["code", "reasoning", "math"],
        )

        assert caps.supports_specialty("code") is True
        assert caps.supports_specialty("CODE") is True  # Case insensitive
        assert caps.supports_specialty("math") is True

    def test_supports_specialty_no_match(self):
        """Test specialty not matching."""
        caps = LLMCapabilities(
            provider="test",
            model="test",
            specialties=["code"],
        )

        assert caps.supports_specialty("creative") is False
        assert caps.supports_specialty("vision") is False

    def test_supports_specialty_empty(self):
        """Test empty specialties."""
        caps = LLMCapabilities(provider="test", model="test")

        assert caps.supports_specialty("anything") is False


class TestLLMCapabilitiesCostEstimation:
    """Tests for cost estimation."""

    def test_estimate_cost_basic(self):
        """Test basic cost estimation."""
        caps = LLMCapabilities(
            provider="openai",
            model="gpt-4",
            cost_per_1k_input=0.03,
            cost_per_1k_output=0.06,
        )

        cost = caps.estimate_cost(1000, 500)

        # Expected: (1000/1000 * 0.03) + (500/1000 * 0.06) = 0.03 + 0.03 = 0.06
        assert abs(cost - 0.06) < 0.001

    def test_estimate_cost_free_model(self):
        """Test cost estimation for free model."""
        caps = LLMCapabilities(
            provider="ollama",
            model="llama3",
            cost_per_1k_input=0.0,
            cost_per_1k_output=0.0,
        )

        cost = caps.estimate_cost(10000, 5000)

        assert cost == 0.0

    def test_estimate_cost_large_request(self):
        """Test cost for large request."""
        caps = LLMCapabilities(
            provider="openai",
            model="gpt-4",
            cost_per_1k_input=0.03,
            cost_per_1k_output=0.06,
        )

        cost = caps.estimate_cost(100000, 4000)

        # Expected: (100 * 0.03) + (4 * 0.06) = 3.0 + 0.24 = 3.24
        assert abs(cost - 3.24) < 0.001


class TestLLMCapabilitiesRequirements:
    """Tests for matches_requirements."""

    def test_matches_requirements_all_met(self):
        """Test when all requirements are met."""
        caps = LLMCapabilities(
            provider="openai",
            model="gpt-4o",
            supports_vision=True,
            supports_tool_calling=True,
            supports_structured_output=True,
            max_context=128000,
            quality_score=0.95,
        )

        assert (
            caps.matches_requirements(
                requires_vision=True,
                requires_tools=True,
                requires_structured=True,
                min_context=100000,
                min_quality=0.9,
            )
            is True
        )

    def test_matches_requirements_vision_missing(self):
        """Test when vision is required but not supported."""
        caps = LLMCapabilities(
            provider="openai",
            model="gpt-4",
            supports_vision=False,
        )

        assert caps.matches_requirements(requires_vision=True) is False

    def test_matches_requirements_context_insufficient(self):
        """Test when context is insufficient."""
        caps = LLMCapabilities(
            provider="test",
            model="test",
            max_context=8192,
        )

        assert caps.matches_requirements(min_context=100000) is False

    def test_matches_requirements_quality_insufficient(self):
        """Test when quality is insufficient."""
        caps = LLMCapabilities(
            provider="test",
            model="test",
            quality_score=0.7,
        )

        assert caps.matches_requirements(min_quality=0.9) is False

    def test_matches_requirements_no_requirements(self):
        """Test with no requirements (always matches)."""
        caps = LLMCapabilities(provider="test", model="test")

        assert caps.matches_requirements() is True


class TestLLMCapabilitiesSerialization:
    """Tests for serialization."""

    def test_to_dict(self):
        """Test to_dict method."""
        caps = LLMCapabilities(
            provider="openai",
            model="gpt-4",
            supports_vision=True,
            quality_score=0.95,
            specialties=["code", "reasoning"],
        )

        data = caps.to_dict()

        assert data["provider"] == "openai"
        assert data["model"] == "gpt-4"
        assert data["supports_vision"] is True
        assert data["quality_score"] == 0.95
        assert data["specialties"] == ["code", "reasoning"]

    def test_from_dict(self):
        """Test from_dict method."""
        data = {
            "provider": "anthropic",
            "model": "claude-3-opus",
            "supports_vision": True,
            "max_context": 200000,
            "quality_score": 0.97,
            "specialties": ["reasoning"],
        }

        caps = LLMCapabilities.from_dict(data)

        assert caps.provider == "anthropic"
        assert caps.model == "claude-3-opus"
        assert caps.supports_vision is True
        assert caps.max_context == 200000
        assert caps.quality_score == 0.97

    def test_roundtrip(self):
        """Test roundtrip serialization."""
        original = LLMCapabilities(
            provider="google",
            model="gemini-pro",
            supports_vision=True,
            supports_audio=True,
            max_context=1000000,
            cost_per_1k_input=0.001,
            quality_score=0.92,
            specialties=["multimodal"],
        )

        data = original.to_dict()
        restored = LLMCapabilities.from_dict(data)

        assert restored.provider == original.provider
        assert restored.model == original.model
        assert restored.supports_vision == original.supports_vision
        assert restored.supports_audio == original.supports_audio
        assert restored.max_context == original.max_context
        assert restored.quality_score == original.quality_score


class TestModelRegistry:
    """Tests for MODEL_REGISTRY and registry functions."""

    def test_registry_populated(self):
        """Test that registry is populated with common models."""
        assert len(MODEL_REGISTRY) > 10

        # Check key models exist
        assert "gpt-4" in MODEL_REGISTRY
        assert "gpt-3.5-turbo" in MODEL_REGISTRY
        assert "claude-3-opus" in MODEL_REGISTRY
        assert "gemini-1.5-pro" in MODEL_REGISTRY

    def test_get_model_capabilities_exists(self):
        """Test getting existing model capabilities."""
        caps = get_model_capabilities("gpt-4")

        assert caps is not None
        assert caps.provider == "openai"
        assert caps.model == "gpt-4"
        assert caps.quality_score > 0.9

    def test_get_model_capabilities_not_exists(self):
        """Test getting non-existent model."""
        caps = get_model_capabilities("nonexistent-model")

        assert caps is None

    def test_register_model(self):
        """Test registering a new model."""
        custom = LLMCapabilities(
            provider="custom",
            model="my-model-v1",
            quality_score=0.85,
            specialties=["custom-task"],
        )

        register_model(custom)

        retrieved = get_model_capabilities("my-model-v1")
        assert retrieved is not None
        assert retrieved.provider == "custom"
        assert retrieved.quality_score == 0.85


class TestListModels:
    """Tests for list_models function."""

    def test_list_all_models(self):
        """Test listing all models."""
        models = list_models()

        assert len(models) > 10
        assert "gpt-4" in models

    def test_list_by_provider(self):
        """Test filtering by provider."""
        openai_models = list_models(provider="openai")
        anthropic_models = list_models(provider="anthropic")

        assert all(
            get_model_capabilities(m).provider == "openai" for m in openai_models
        )
        assert all(
            get_model_capabilities(m).provider == "anthropic" for m in anthropic_models
        )

    def test_list_by_vision_support(self):
        """Test filtering by vision support."""
        vision_models = list_models(supports_vision=True)
        no_vision_models = list_models(supports_vision=False)

        for model in vision_models:
            caps = get_model_capabilities(model)
            assert caps.supports_vision is True

        for model in no_vision_models:
            caps = get_model_capabilities(model)
            assert caps.supports_vision is False

    def test_list_by_min_quality(self):
        """Test filtering by minimum quality."""
        high_quality = list_models(min_quality=0.9)

        for model in high_quality:
            caps = get_model_capabilities(model)
            assert caps.quality_score >= 0.9

    def test_list_by_specialty(self):
        """Test filtering by specialty."""
        code_models = list_models(specialty="code")

        assert len(code_models) > 0
        for model in code_models:
            caps = get_model_capabilities(model)
            assert caps.supports_specialty("code")

    def test_list_combined_filters(self):
        """Test with multiple filters."""
        models = list_models(
            provider="openai",
            supports_tools=True,
            min_quality=0.8,
        )

        for model in models:
            caps = get_model_capabilities(model)
            assert caps.provider == "openai"
            assert caps.supports_tool_calling is True
            assert caps.quality_score >= 0.8


class TestGetCheapestModel:
    """Tests for get_cheapest_model function."""

    def test_get_cheapest_basic(self):
        """Test getting cheapest model."""
        model = get_cheapest_model()

        assert model is not None
        caps = get_model_capabilities(model)
        # Should be a cheap or free model
        assert caps.cost_per_1k_output <= 0.01 or caps.is_free

    def test_get_cheapest_with_vision(self):
        """Test getting cheapest model with vision."""
        model = get_cheapest_model(requires_vision=True)

        if model:
            caps = get_model_capabilities(model)
            assert caps.supports_vision is True

    def test_get_cheapest_with_quality(self):
        """Test getting cheapest model with quality requirement."""
        model = get_cheapest_model(min_quality=0.9)

        if model:
            caps = get_model_capabilities(model)
            assert caps.quality_score >= 0.9


class TestGetBestQualityModel:
    """Tests for get_best_quality_model function."""

    def test_get_best_quality_basic(self):
        """Test getting highest quality model."""
        model = get_best_quality_model()

        assert model is not None
        caps = get_model_capabilities(model)
        # Should be a high-quality model
        assert caps.quality_score >= 0.9

    def test_get_best_quality_with_vision(self):
        """Test getting best model with vision."""
        model = get_best_quality_model(requires_vision=True)

        if model:
            caps = get_model_capabilities(model)
            assert caps.supports_vision is True

    def test_get_best_quality_with_cost_limit(self):
        """Test getting best model with cost limit."""
        model = get_best_quality_model(max_cost_per_1k=0.01)

        if model:
            caps = get_model_capabilities(model)
            assert caps.cost_per_1k_output <= 0.01


class TestModelRegistryData:
    """Tests for specific models in the registry."""

    def test_gpt4_capabilities(self):
        """Test GPT-4 has expected capabilities."""
        caps = get_model_capabilities("gpt-4")

        assert caps is not None
        assert caps.provider == "openai"
        assert caps.supports_tool_calling is True
        assert caps.max_context >= 8000
        assert caps.quality_score >= 0.9
        assert "reasoning" in caps.specialties

    def test_claude3_opus_capabilities(self):
        """Test Claude 3 Opus has expected capabilities."""
        caps = get_model_capabilities("claude-3-opus")

        assert caps is not None
        assert caps.provider == "anthropic"
        assert caps.supports_vision is True
        assert caps.supports_tool_calling is True
        assert caps.max_context >= 100000
        assert caps.quality_score >= 0.95

    def test_ollama_llama_capabilities(self):
        """Test Ollama Llama has expected capabilities."""
        caps = get_model_capabilities("llama3.2")

        assert caps is not None
        assert caps.provider == "ollama"
        assert caps.is_local is True
        assert caps.is_free is True

    def test_gemini_capabilities(self):
        """Test Gemini has expected capabilities."""
        caps = get_model_capabilities("gemini-1.5-pro")

        assert caps is not None
        assert caps.provider == "google"
        assert caps.supports_vision is True
        assert caps.supports_audio is True
        assert caps.max_context >= 1000000

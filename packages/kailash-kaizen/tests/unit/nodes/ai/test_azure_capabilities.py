"""Unit tests for Azure capability registry.

Tests the AzureCapabilityRegistry class which handles feature gap detection
between Azure OpenAI Service and Azure AI Foundry.
"""

import warnings

import pytest

from kaizen.nodes.ai.azure_capabilities import (
    AzureCapabilityRegistry,
    FeatureDegradationWarning,
    FeatureInfo,
    FeatureNotSupportedError,
    GapHandling,
)


class TestAzureCapabilityRegistry:
    """Unit tests for capability detection and gap handling."""

    # Azure OpenAI Capability Tests

    @pytest.mark.parametrize(
        "feature,expected",
        [
            ("chat", True),
            ("embeddings", True),
            ("streaming", True),
            ("tool_calling", True),
            ("structured_output", True),
            ("vision", True),
            ("audio_input", True),
            ("reasoning_models", True),
            ("llama_models", False),
            ("mistral_models", False),
        ],
    )
    def test_azure_openai_capabilities(self, feature, expected):
        """Should correctly report Azure OpenAI capabilities."""
        registry = AzureCapabilityRegistry("azure_openai")
        assert registry.supports(feature) == expected

    # Azure AI Foundry Capability Tests

    @pytest.mark.parametrize(
        "feature,expected",
        [
            ("chat", True),
            ("embeddings", True),
            ("streaming", True),
            ("tool_calling", True),
            ("structured_output", True),
            ("vision", True),  # Partial support, model-dependent
            ("audio_input", False),
            ("reasoning_models", False),
            ("llama_models", True),
            ("mistral_models", True),
        ],
    )
    def test_ai_foundry_capabilities(self, feature, expected):
        """Should correctly report AI Foundry capabilities."""
        registry = AzureCapabilityRegistry("azure_ai_foundry")
        assert registry.supports(feature) == expected

    # Hard Gap Error Tests

    def test_audio_raises_error_on_ai_foundry(self):
        """Audio input should raise error with guidance on AI Foundry."""
        registry = AzureCapabilityRegistry("azure_ai_foundry")

        with pytest.raises(FeatureNotSupportedError) as exc:
            registry.check_feature("audio_input")

        assert exc.value.feature == "audio_input"
        assert exc.value.current_backend == "azure_ai_foundry"
        assert "Azure OpenAI" in str(exc.value)
        assert exc.value.guidance is not None
        assert (
            "transcribe" in exc.value.guidance.lower()
            or "openai" in exc.value.guidance.lower()
        )

    def test_reasoning_raises_error_on_ai_foundry(self):
        """Reasoning models should raise error on AI Foundry."""
        registry = AzureCapabilityRegistry("azure_ai_foundry")

        with pytest.raises(FeatureNotSupportedError) as exc:
            registry.check_feature("reasoning_models")

        assert exc.value.feature == "reasoning_models"
        assert "Azure OpenAI" in str(exc.value)

    def test_llama_raises_error_on_azure_openai(self):
        """Llama models should raise error on Azure OpenAI."""
        registry = AzureCapabilityRegistry("azure_openai")

        with pytest.raises(FeatureNotSupportedError) as exc:
            registry.check_feature("llama_models")

        assert "AI Foundry" in str(exc.value)

    def test_mistral_raises_error_on_azure_openai(self):
        """Mistral models should raise error on Azure OpenAI."""
        registry = AzureCapabilityRegistry("azure_openai")

        with pytest.raises(FeatureNotSupportedError) as exc:
            registry.check_feature("mistral_models")

        assert "AI Foundry" in str(exc.value)

    # Degradable Feature Tests

    def test_vision_warns_on_ai_foundry(self):
        """Vision should warn but proceed on AI Foundry (model-dependent)."""
        registry = AzureCapabilityRegistry("azure_ai_foundry")

        with pytest.warns(FeatureDegradationWarning):
            registry.check_feature("vision")

    def test_vision_no_warning_on_azure_openai(self):
        """Vision should not warn on Azure OpenAI."""
        registry = AzureCapabilityRegistry("azure_openai")

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            registry.check_feature("vision")
            # Filter for our specific warning
            our_warnings = [
                x for x in w if issubclass(x.category, FeatureDegradationWarning)
            ]
            assert len(our_warnings) == 0

    def test_supported_feature_no_warning(self):
        """Supported features should not produce warnings."""
        registry = AzureCapabilityRegistry("azure_openai")

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            registry.check_feature("chat")
            our_warnings = [
                x for x in w if issubclass(x.category, FeatureDegradationWarning)
            ]
            assert len(our_warnings) == 0

    # Model Requirement Tests

    @pytest.mark.parametrize(
        "model",
        ["o1", "o1-preview", "o1-mini", "o3", "o3-mini", "gpt-5", "GPT-5-turbo"],
    )
    def test_reasoning_model_detection_raises_on_foundry(self, model):
        """Should detect reasoning models and raise error on AI Foundry."""
        registry = AzureCapabilityRegistry("azure_ai_foundry")

        with pytest.raises(FeatureNotSupportedError):
            registry.check_model_requirements(model)

    @pytest.mark.parametrize(
        "model",
        ["gpt-4o", "gpt-4-turbo", "gpt-4", "text-embedding-3-small", "my-deployment"],
    )
    def test_standard_model_no_error_on_foundry(self, model):
        """Standard models should not raise errors on AI Foundry."""
        registry = AzureCapabilityRegistry("azure_ai_foundry")
        # Should not raise
        registry.check_model_requirements(model)

    @pytest.mark.parametrize("model", ["llama-3.1-8b", "Llama-3.1-70B", "meta-llama"])
    def test_llama_model_detection_raises_on_openai(self, model):
        """Should detect Llama models and raise error on Azure OpenAI."""
        registry = AzureCapabilityRegistry("azure_openai")

        with pytest.raises(FeatureNotSupportedError) as exc:
            registry.check_model_requirements(model)

        assert "llama" in exc.value.feature.lower()

    @pytest.mark.parametrize("model", ["mistral-large", "mixtral-8x7b", "Mistral-7B"])
    def test_mistral_model_detection_raises_on_openai(self, model):
        """Should detect Mistral models and raise error on Azure OpenAI."""
        registry = AzureCapabilityRegistry("azure_openai")

        with pytest.raises(FeatureNotSupportedError) as exc:
            registry.check_model_requirements(model)

        assert "mistral" in exc.value.feature.lower()

    def test_none_model_no_error(self):
        """None model should not raise error."""
        registry = AzureCapabilityRegistry("azure_openai")
        registry.check_model_requirements(None)  # Should not raise

    def test_empty_model_no_error(self):
        """Empty string model should not raise error."""
        registry = AzureCapabilityRegistry("azure_ai_foundry")
        registry.check_model_requirements("")  # Should not raise

    # Capability Enumeration Tests

    def test_get_capabilities_returns_all_features(self):
        """Should return all feature capabilities."""
        registry = AzureCapabilityRegistry("azure_openai")
        caps = registry.get_capabilities()

        assert "chat" in caps
        assert "embeddings" in caps
        assert "audio_input" in caps
        assert "llama_models" in caps
        assert "reasoning_models" in caps
        assert len(caps) >= 10

    def test_get_capabilities_values_match_supports(self):
        """get_capabilities values should match supports() calls."""
        registry = AzureCapabilityRegistry("azure_openai")
        caps = registry.get_capabilities()

        for feature, supported in caps.items():
            assert registry.supports(feature) == supported

    # Feature Info Tests

    def test_get_feature_info_returns_info(self):
        """Should return FeatureInfo for known features."""
        registry = AzureCapabilityRegistry("azure_openai")
        info = registry.get_feature_info("audio_input")

        assert info is not None
        assert isinstance(info, FeatureInfo)
        assert info.name == "audio_input"
        assert info.azure_openai is True
        assert info.azure_ai_foundry is False

    def test_get_feature_info_unknown_returns_none(self):
        """Should return None for unknown features."""
        registry = AzureCapabilityRegistry("azure_openai")
        info = registry.get_feature_info("unknown_feature")

        assert info is None

    def test_unknown_feature_supports_returns_true(self):
        """Unknown features should pass through (return True)."""
        registry = AzureCapabilityRegistry("azure_openai")
        assert registry.supports("unknown_feature") is True

    def test_unknown_feature_check_passes(self):
        """Unknown features should not raise on check_feature."""
        registry = AzureCapabilityRegistry("azure_openai")
        registry.check_feature("unknown_feature")  # Should not raise

    # Constructor Tests

    def test_invalid_backend_raises_error(self):
        """Should raise error for invalid backend name."""
        with pytest.raises(ValueError, match="Invalid backend"):
            AzureCapabilityRegistry("invalid_backend")

    def test_valid_backend_azure_openai(self):
        """Should accept 'azure_openai' backend."""
        registry = AzureCapabilityRegistry("azure_openai")
        assert registry.backend == "azure_openai"

    def test_valid_backend_ai_foundry(self):
        """Should accept 'azure_ai_foundry' backend."""
        registry = AzureCapabilityRegistry("azure_ai_foundry")
        assert registry.backend == "azure_ai_foundry"


class TestFeatureNotSupportedError:
    """Tests for the FeatureNotSupportedError exception."""

    def test_error_message_includes_feature(self):
        """Error message should include feature name."""
        error = FeatureNotSupportedError(
            feature="audio_input",
            current_backend="azure_ai_foundry",
        )
        assert "audio_input" in str(error)

    def test_error_message_includes_backend(self):
        """Error message should include current backend."""
        error = FeatureNotSupportedError(
            feature="audio_input",
            current_backend="azure_ai_foundry",
        )
        assert "azure_ai_foundry" in str(error)

    def test_error_message_includes_required_backend(self):
        """Error message should include required backend when provided."""
        error = FeatureNotSupportedError(
            feature="audio_input",
            current_backend="azure_ai_foundry",
            required_backend="Azure OpenAI Service",
        )
        assert "Azure OpenAI Service" in str(error)

    def test_error_message_includes_guidance(self):
        """Error message should include guidance when provided."""
        guidance = "Set AZURE_ENDPOINT to *.openai.azure.com"
        error = FeatureNotSupportedError(
            feature="audio_input",
            current_backend="azure_ai_foundry",
            guidance=guidance,
        )
        assert guidance in str(error)

    def test_error_attributes_accessible(self):
        """Error attributes should be accessible."""
        error = FeatureNotSupportedError(
            feature="audio_input",
            current_backend="azure_ai_foundry",
            required_backend="Azure OpenAI",
            guidance="Some guidance",
        )
        assert error.feature == "audio_input"
        assert error.current_backend == "azure_ai_foundry"
        assert error.required_backend == "Azure OpenAI"
        assert error.guidance == "Some guidance"


class TestGapHandling:
    """Tests for GapHandling enum."""

    def test_gap_handling_values(self):
        """GapHandling should have expected values."""
        assert GapHandling.PASSTHROUGH.value == "passthrough"
        assert GapHandling.TRANSLATE.value == "translate"
        assert GapHandling.WARN_PROCEED.value == "warn_proceed"
        assert GapHandling.ERROR.value == "error"

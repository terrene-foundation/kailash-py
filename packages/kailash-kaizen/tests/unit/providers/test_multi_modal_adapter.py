"""
Unit tests for MultiModalAdapter - provider abstraction for multi-modal processing.

Following TDD methodology: Write tests FIRST, then implement.
"""

from unittest.mock import Mock, patch

import pytest

# Test infrastructure
try:
    from kaizen.providers.multi_modal_adapter import (
        MultiModalAdapter,
        OllamaMultiModalAdapter,
        OpenAIMultiModalAdapter,
        get_multi_modal_adapter,
    )
    from kaizen.signatures.multi_modal import AudioField, ImageField

    IMPORTS_AVAILABLE = True
except ImportError:
    IMPORTS_AVAILABLE = False

pytestmark = pytest.mark.skipif(
    not IMPORTS_AVAILABLE, reason="MultiModalAdapter not yet implemented"
)


class TestMultiModalAdapterInterface:
    """Test MultiModalAdapter abstract interface."""

    def test_adapter_interface_definition(self):
        """Test that MultiModalAdapter defines required interface."""
        # Should be abstract base class
        from abc import ABC

        assert issubclass(MultiModalAdapter, ABC)

        # Should define required methods
        required_methods = [
            "is_available",
            "supports_vision",
            "supports_audio",
            "process_multi_modal",
            "estimate_cost",
        ]

        for method in required_methods:
            assert hasattr(MultiModalAdapter, method)

    def test_adapter_cannot_instantiate_directly(self):
        """Test that MultiModalAdapter cannot be instantiated directly."""
        with pytest.raises(TypeError):
            MultiModalAdapter()


class TestOllamaMultiModalAdapter:
    """Test Ollama multi-modal adapter implementation."""

    @patch("kaizen.providers.OLLAMA_AVAILABLE", True)
    def test_adapter_creation(self):
        """Test basic adapter creation."""
        adapter = OllamaMultiModalAdapter(model="llava:13b")
        assert adapter is not None
        assert adapter.model == "llava:13b"

    @patch("kaizen.providers.OLLAMA_AVAILABLE", True)
    def test_availability_check(self):
        """Test adapter availability check."""
        adapter = OllamaMultiModalAdapter()
        assert adapter.is_available() is True

    @patch("kaizen.providers.OLLAMA_AVAILABLE", False)
    def test_unavailable_when_ollama_missing(self):
        """Test adapter reports unavailable when Ollama not installed."""
        adapter = OllamaMultiModalAdapter()
        assert adapter.is_available() is False

    def test_supports_vision(self):
        """Test that Ollama adapter supports vision."""
        with patch("kaizen.providers.OLLAMA_AVAILABLE", True):
            adapter = OllamaMultiModalAdapter(model="llava:13b")
            assert adapter.supports_vision() is True

    def test_supports_audio_via_whisper(self):
        """Test that Ollama adapter supports audio via Whisper integration."""
        with patch("kaizen.providers.OLLAMA_AVAILABLE", True):
            adapter = OllamaMultiModalAdapter()
            # Audio supported via WhisperProcessor
            assert adapter.supports_audio() is True

    @patch("kaizen.providers.OLLAMA_AVAILABLE", True)
    def test_process_vision_only(self, tmp_path):
        """Test processing with vision only."""
        # Create test image
        from PIL import Image

        image_path = tmp_path / "test.png"
        Image.new("RGB", (100, 100)).save(image_path)

        adapter = OllamaMultiModalAdapter(model="llava:13b")

        with patch.object(adapter, "_call_ollama_vision") as mock_vision:
            mock_vision.return_value = {"description": "Test image"}

            result = adapter.process_multi_modal(
                image=str(image_path), prompt="Describe this image"
            )

            assert "description" in result
            mock_vision.assert_called_once()

    @patch("kaizen.providers.OLLAMA_AVAILABLE", True)
    def test_process_audio_only(self, tmp_path):
        """Test processing with audio only."""
        # Create test audio
        import struct
        import wave

        audio_path = tmp_path / "test.wav"
        with wave.open(str(audio_path), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(16000)
            for _ in range(16000):
                wav.writeframes(struct.pack("<h", 0))

        adapter = OllamaMultiModalAdapter()

        with patch.object(adapter, "_call_whisper") as mock_whisper:
            mock_whisper.return_value = {"text": "Test transcription"}

            result = adapter.process_multi_modal(audio=str(audio_path))

            assert "text" in result
            mock_whisper.assert_called_once()

    @patch("kaizen.providers.OLLAMA_AVAILABLE", True)
    def test_process_mixed_modalities(self, tmp_path):
        """Test processing with image + audio + text."""
        # Create test files
        from PIL import Image

        image_path = tmp_path / "test.png"
        Image.new("RGB", (100, 100)).save(image_path)

        import struct
        import wave

        audio_path = tmp_path / "test.wav"
        with wave.open(str(audio_path), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(16000)
            for _ in range(16000):
                wav.writeframes(struct.pack("<h", 0))

        adapter = OllamaMultiModalAdapter(model="llava:13b")

        with (
            patch.object(adapter, "_call_ollama_vision") as mock_vision,
            patch.object(adapter, "_call_whisper") as mock_whisper,
            patch.object(adapter, "_combine_results") as mock_combine,
        ):

            mock_vision.return_value = {"visual": "Image analysis"}
            mock_whisper.return_value = {"audio": "Audio transcription"}
            mock_combine.return_value = {"combined": "Full analysis"}

            result = adapter.process_multi_modal(
                image=str(image_path), audio=str(audio_path), text="Analyze this media"
            )

            assert "combined" in result
            mock_vision.assert_called_once()
            mock_whisper.assert_called_once()
            mock_combine.assert_called_once()

    @patch("kaizen.providers.OLLAMA_AVAILABLE", True)
    def test_estimate_cost_always_zero(self):
        """Test that Ollama adapter always estimates $0 cost."""
        adapter = OllamaMultiModalAdapter()

        # Vision cost
        vision_cost = adapter.estimate_cost(modality="vision", input_size=1000)
        assert vision_cost == 0.0

        # Audio cost
        audio_cost = adapter.estimate_cost(modality="audio", duration=60)
        assert audio_cost == 0.0

        # Mixed cost
        mixed_cost = adapter.estimate_cost(modality="mixed")
        assert mixed_cost == 0.0

    @patch("kaizen.providers.OLLAMA_AVAILABLE", True)
    def test_model_auto_download(self):
        """Test automatic model download when missing."""
        with patch(
            "kaizen.providers.ollama_model_manager.OllamaModelManager"
        ) as MockManager:
            mock_manager = MockManager.return_value
            mock_manager.ensure_model_available.return_value = True

            adapter = OllamaMultiModalAdapter(model="llava:13b", auto_download=True)

            adapter._ensure_model_ready()

            mock_manager.ensure_model_available.assert_called_with(
                "llava:13b", auto_download=True
            )


class TestOpenAIMultiModalAdapter:
    """Test OpenAI multi-modal adapter implementation."""

    def test_adapter_creation(self):
        """Test basic adapter creation."""
        adapter = OpenAIMultiModalAdapter(api_key="test-key")
        assert adapter is not None
        assert adapter.api_key == "test-key"

    def test_availability_check_with_key(self):
        """Test availability when API key is present."""
        adapter = OpenAIMultiModalAdapter(api_key="test-key")
        assert adapter.is_available() is True

    def test_unavailable_without_key(self):
        """Test unavailable when no API key."""
        # Temporarily clear env var to test explicit None behavior
        import os

        original_key = os.environ.pop("OPENAI_API_KEY", None)
        try:
            adapter = OpenAIMultiModalAdapter(api_key=None)
            assert adapter.is_available() is False
        finally:
            if original_key is not None:
                os.environ["OPENAI_API_KEY"] = original_key

    def test_supports_vision(self):
        """Test that OpenAI adapter supports vision (GPT-4V)."""
        adapter = OpenAIMultiModalAdapter(api_key="test-key")
        assert adapter.supports_vision() is True

    def test_supports_audio(self):
        """Test that OpenAI adapter supports audio (Whisper)."""
        adapter = OpenAIMultiModalAdapter(api_key="test-key")
        assert adapter.supports_audio() is True

    def test_process_vision_only(self, tmp_path):
        """Test processing with vision only."""
        from PIL import Image

        image_path = tmp_path / "test.png"
        Image.new("RGB", (100, 100)).save(image_path)

        adapter = OpenAIMultiModalAdapter(api_key="test-key")

        with patch.object(adapter, "_call_openai_vision") as mock_vision:
            mock_vision.return_value = {"description": "Test image via OpenAI"}

            result = adapter.process_multi_modal(
                image=str(image_path), prompt="Describe this image"
            )

            assert "description" in result
            mock_vision.assert_called_once()

    def test_process_audio_only(self, tmp_path):
        """Test processing with audio only."""
        import struct
        import wave

        audio_path = tmp_path / "test.wav"
        with wave.open(str(audio_path), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(16000)
            for _ in range(16000):
                wav.writeframes(struct.pack("<h", 0))

        adapter = OpenAIMultiModalAdapter(api_key="test-key")

        with patch.object(adapter, "_call_openai_whisper") as mock_whisper:
            mock_whisper.return_value = {"text": "OpenAI transcription"}

            result = adapter.process_multi_modal(audio=str(audio_path))

            assert "text" in result
            mock_whisper.assert_called_once()

    def test_estimate_cost_vision(self):
        """Test cost estimation for vision processing."""
        adapter = OpenAIMultiModalAdapter(api_key="test-key")

        # GPT-4V costs ~$0.01 per image
        cost = adapter.estimate_cost(modality="vision", input_size=1000)
        assert cost > 0
        assert 0.005 <= cost <= 0.02  # Reasonable range

    def test_estimate_cost_audio(self):
        """Test cost estimation for audio processing."""
        adapter = OpenAIMultiModalAdapter(api_key="test-key")

        # Whisper costs $0.006 per minute
        cost = adapter.estimate_cost(modality="audio", duration=60)
        assert cost > 0
        assert 0.005 <= cost <= 0.01  # ~$0.006

    def test_cost_warning_enabled(self):
        """Test cost warning before OpenAI calls."""
        adapter = OpenAIMultiModalAdapter(api_key="test-key", warn_before_call=True)

        assert adapter.warn_before_call is True

    def test_usage_tracking(self, tmp_path):
        """Test that adapter tracks API usage."""
        from PIL import Image

        image_path = tmp_path / "test.png"
        Image.new("RGB", (100, 100)).save(image_path)

        adapter = OpenAIMultiModalAdapter(api_key="test-key")

        # Mock OpenAI client instead of internal method so usage tracking still works
        with patch("openai.OpenAI") as MockClient:
            mock_response = Mock()
            mock_response.choices = [Mock(message=Mock(content="Test description"))]
            MockClient.return_value.chat.completions.create.return_value = mock_response

            adapter.process_multi_modal(image=str(image_path), prompt="Test")

            # Should track usage
            usage = adapter.get_usage_stats()
            assert usage["total_calls"] == 1
            assert usage["vision_calls"] == 1
            assert usage["total_cost"] == pytest.approx(0.01, abs=0.001)


class TestAdapterFactory:
    """Test adapter factory and auto-selection."""

    @patch("kaizen.providers.OLLAMA_AVAILABLE", True)
    def test_get_ollama_adapter_when_available(self):
        """Test automatic selection of Ollama when available."""
        adapter = get_multi_modal_adapter(prefer_local=True)
        assert isinstance(adapter, OllamaMultiModalAdapter)

    @patch("kaizen.providers.OLLAMA_AVAILABLE", False)
    def test_get_openai_adapter_when_ollama_unavailable(self):
        """Test fallback to OpenAI when Ollama unavailable."""
        # Clear cache first
        from kaizen.providers.multi_modal_adapter import _adapter_cache

        _adapter_cache.clear()

        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
            adapter = get_multi_modal_adapter(prefer_local=True)
            assert isinstance(adapter, OpenAIMultiModalAdapter)

    def test_explicit_provider_selection(self):
        """Test explicit provider selection."""
        # Clear cache
        from kaizen.providers.multi_modal_adapter import _adapter_cache

        _adapter_cache.clear()

        # Explicitly request OpenAI
        adapter = get_multi_modal_adapter(provider="openai", api_key="test-key")
        assert isinstance(adapter, OpenAIMultiModalAdapter)

        # Clear cache again
        _adapter_cache.clear()

        # Explicitly request Ollama
        with patch("kaizen.providers.OLLAMA_AVAILABLE", True):
            adapter = get_multi_modal_adapter(provider="ollama")
            assert isinstance(adapter, OllamaMultiModalAdapter)

    def test_error_when_no_adapter_available(self):
        """Test error when no adapter is available."""
        # Clear cache first
        from kaizen.providers.multi_modal_adapter import _adapter_cache

        _adapter_cache.clear()

        with (
            patch("kaizen.providers.OLLAMA_AVAILABLE", False),
            patch.dict("os.environ", {}, clear=True),
        ):
            with pytest.raises(ValueError, match="No multi-modal adapter available"):
                get_multi_modal_adapter()

    @patch("kaizen.providers.OLLAMA_AVAILABLE", True)
    def test_adapter_caching(self):
        """Test that adapters are cached for reuse."""
        adapter1 = get_multi_modal_adapter(prefer_local=True)
        adapter2 = get_multi_modal_adapter(prefer_local=True)

        # Should return same instance (cached)
        assert adapter1 is adapter2


class TestAdapterIntegration:
    """Test adapter integration with signature system."""

    @patch("kaizen.providers.OLLAMA_AVAILABLE", True)
    def test_image_field_integration(self, tmp_path):
        """Test ImageField integration with adapter."""
        from PIL import Image

        image_path = tmp_path / "test.png"
        Image.new("RGB", (100, 100)).save(image_path)

        adapter = OllamaMultiModalAdapter(model="llava:13b")

        # ImageField should be preprocessed by adapter
        image_field = ImageField()
        image_field.load(str(image_path))

        with patch.object(adapter, "_call_ollama_vision") as mock_vision:
            mock_vision.return_value = {"result": "Success"}

            result = adapter.process_multi_modal(image=image_field)

            assert "result" in result

    @patch("kaizen.providers.OLLAMA_AVAILABLE", True)
    def test_audio_field_integration(self, tmp_path):
        """Test AudioField integration with adapter."""
        import struct
        import wave

        audio_path = tmp_path / "test.wav"
        with wave.open(str(audio_path), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(16000)
            for _ in range(16000):
                wav.writeframes(struct.pack("<h", 0))

        adapter = OllamaMultiModalAdapter()

        # AudioField should be preprocessed by adapter
        audio_field = AudioField()
        audio_field.load(str(audio_path))

        with patch.object(adapter, "_call_whisper") as mock_whisper:
            mock_whisper.return_value = {"text": "Success"}

            result = adapter.process_multi_modal(audio=audio_field)

            assert "text" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

"""
Unit tests for TranscriptionAgent - Audio transcription agent.

Tests agent integration with WhisperProcessor for speech-to-text.
Written FIRST following TDD methodology.
"""

import math
import struct
import tempfile
import wave
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def temp_audio_file():
    """Create a temporary WAV audio file for testing."""
    sample_rate = 16000
    duration = 1.0
    frequency = 440.0

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        temp_path = f.name

    try:
        num_samples = int(sample_rate * duration)
        audio_data = []

        for i in range(num_samples):
            sample = math.sin(2.0 * math.pi * frequency * i / sample_rate)
            audio_data.append(int(sample * 32767))

        with wave.open(temp_path, "w") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(sample_rate)
            packed_data = struct.pack("<" + "h" * len(audio_data), *audio_data)
            wav_file.writeframes(packed_data)

        yield temp_path
    finally:
        import os

        if os.path.exists(temp_path):
            os.unlink(temp_path)


@pytest.fixture
def mock_whisper_result():
    """Mock WhisperProcessor transcription result."""
    return {
        "text": "This is a test transcription.",
        "language": "en",
        "language_probability": 0.95,
        "duration": 5.0,
        "segments": [
            {
                "start": 0.0,
                "end": 2.5,
                "text": "This is a test",
                "confidence": -0.3,
                "words": [
                    {"word": "This", "start": 0.0, "end": 0.5, "confidence": 0.95},
                    {"word": "is", "start": 0.5, "end": 0.8, "confidence": 0.93},
                    {"word": "a", "start": 0.8, "end": 1.0, "confidence": 0.92},
                    {"word": "test", "start": 1.0, "end": 2.5, "confidence": 0.94},
                ],
            },
            {
                "start": 2.5,
                "end": 5.0,
                "text": "transcription.",
                "confidence": -0.4,
                "words": [
                    {
                        "word": "transcription",
                        "start": 2.5,
                        "end": 5.0,
                        "confidence": 0.91,
                    }
                ],
            },
        ],
        "model": "base",
    }


class TestTranscriptionAgentCreation:
    """Test TranscriptionAgent initialization."""

    def test_transcription_agent_creation(self):
        """Test creating transcription agent with default config."""
        from kaizen.agents.multi_modal.transcription_agent import (
            TranscriptionAgent,
            TranscriptionAgentConfig,
        )

        config = TranscriptionAgentConfig(model_size="base")
        agent = TranscriptionAgent(config)

        assert agent.config.model_size == "base"
        assert agent.config.device == "cpu"
        assert agent.config.word_timestamps is True
        assert agent.processor is not None

    def test_transcription_agent_custom_config(self):
        """Test creating agent with custom configuration."""
        from kaizen.agents.multi_modal.transcription_agent import (
            TranscriptionAgent,
            TranscriptionAgentConfig,
        )

        config = TranscriptionAgentConfig(
            model_size="small",
            device="cpu",
            compute_type="float32",
            language="fr",
            word_timestamps=False,
        )
        agent = TranscriptionAgent(config)

        assert agent.config.model_size == "small"
        assert agent.config.device == "cpu"
        assert agent.config.compute_type == "float32"
        assert agent.config.language == "fr"
        assert agent.config.word_timestamps is False

    def test_transcription_agent_has_signature(self):
        """Test that agent has proper signature."""
        from kaizen.agents.multi_modal.transcription_agent import (
            TranscriptionAgent,
            TranscriptionAgentConfig,
            TranscriptionSignature,
        )

        config = TranscriptionAgentConfig(model_size="base")
        agent = TranscriptionAgent(config)

        assert hasattr(agent, "signature")
        assert isinstance(agent.signature, TranscriptionSignature)


class TestTranscriptionBasic:
    """Test basic transcription functionality."""

    @patch("kaizen.agents.multi_modal.transcription_agent.WhisperProcessor")
    def test_transcribe_audio_file(
        self, mock_processor_class, temp_audio_file, mock_whisper_result
    ):
        """Test basic audio file transcription."""
        from kaizen.agents.multi_modal.transcription_agent import (
            TranscriptionAgent,
            TranscriptionAgentConfig,
        )

        # Setup mock
        mock_processor = MagicMock()
        mock_processor.transcribe.return_value = mock_whisper_result
        mock_processor_class.return_value = mock_processor

        # Create agent and transcribe
        config = TranscriptionAgentConfig(model_size="base")
        agent = TranscriptionAgent(config)
        result = agent.transcribe(temp_audio_file, store_in_memory=False)

        # Verify result
        assert result["text"] == "This is a test transcription."
        assert result["language"] == "en"
        assert result["duration"] == 5.0
        assert len(result["segments"]) == 2
        assert "confidence" in result
        assert result["model"] == "base"

    @patch("kaizen.agents.multi_modal.transcription_agent.WhisperProcessor")
    def test_transcribe_with_language_hint(
        self, mock_processor_class, temp_audio_file, mock_whisper_result
    ):
        """Test transcription with language hint."""
        from kaizen.agents.multi_modal.transcription_agent import (
            TranscriptionAgent,
            TranscriptionAgentConfig,
        )

        # Setup mock
        mock_processor = MagicMock()
        mock_whisper_result_fr = mock_whisper_result.copy()
        mock_whisper_result_fr["language"] = "fr"
        mock_processor.transcribe.return_value = mock_whisper_result_fr
        mock_processor_class.return_value = mock_processor

        # Create agent and transcribe with language hint
        config = TranscriptionAgentConfig(model_size="base")
        agent = TranscriptionAgent(config)
        result = agent.transcribe(temp_audio_file, language="fr", store_in_memory=False)

        # Verify language was passed to processor
        mock_processor.transcribe.assert_called_once()
        call_kwargs = mock_processor.transcribe.call_args[1]
        assert call_kwargs["language"] == "fr"
        assert result["language"] == "fr"

    @patch("kaizen.agents.multi_modal.transcription_agent.WhisperProcessor")
    def test_transcribe_calculates_confidence(
        self, mock_processor_class, temp_audio_file, mock_whisper_result
    ):
        """Test that transcription calculates average confidence."""
        from kaizen.agents.multi_modal.transcription_agent import (
            TranscriptionAgent,
            TranscriptionAgentConfig,
        )

        # Setup mock
        mock_processor = MagicMock()
        mock_processor.transcribe.return_value = mock_whisper_result
        mock_processor_class.return_value = mock_processor

        # Create agent and transcribe
        config = TranscriptionAgentConfig(model_size="base")
        agent = TranscriptionAgent(config)
        result = agent.transcribe(temp_audio_file, store_in_memory=False)

        # Verify confidence is calculated (average of segment confidences)
        assert "confidence" in result
        assert isinstance(result["confidence"], float)
        assert result["confidence"] > 0  # Should be positive (abs of log prob)


class TestTranscriptionBatch:
    """Test batch transcription functionality."""

    @patch("kaizen.agents.multi_modal.transcription_agent.WhisperProcessor")
    def test_transcribe_batch(
        self, mock_processor_class, temp_audio_file, mock_whisper_result
    ):
        """Test batch transcription of multiple files."""
        from kaizen.agents.multi_modal.transcription_agent import (
            TranscriptionAgent,
            TranscriptionAgentConfig,
        )

        # Setup mock
        mock_processor = MagicMock()
        mock_processor.transcribe.return_value = mock_whisper_result
        mock_processor_class.return_value = mock_processor

        # Create agent and transcribe batch
        config = TranscriptionAgentConfig(model_size="base")
        agent = TranscriptionAgent(config)

        audio_files = [temp_audio_file, temp_audio_file, temp_audio_file]
        results = agent.transcribe_batch(audio_files)

        # Verify results
        assert len(results) == 3
        for result in results:
            assert result["text"] == "This is a test transcription."
            assert result["language"] == "en"

    @patch("kaizen.agents.multi_modal.transcription_agent.WhisperProcessor")
    def test_transcribe_batch_with_language(
        self, mock_processor_class, temp_audio_file, mock_whisper_result
    ):
        """Test batch transcription with language hint."""
        from kaizen.agents.multi_modal.transcription_agent import (
            TranscriptionAgent,
            TranscriptionAgentConfig,
        )

        # Setup mock
        mock_processor = MagicMock()
        mock_whisper_result_es = mock_whisper_result.copy()
        mock_whisper_result_es["language"] = "es"
        mock_processor.transcribe.return_value = mock_whisper_result_es
        mock_processor_class.return_value = mock_processor

        # Create agent and transcribe batch with language
        config = TranscriptionAgentConfig(model_size="base")
        agent = TranscriptionAgent(config)

        audio_files = [temp_audio_file, temp_audio_file]
        results = agent.transcribe_batch(audio_files, language="es")

        # Verify language was applied to all
        assert len(results) == 2
        for result in results:
            assert result["language"] == "es"


class TestTranscriptionMemory:
    """Test memory integration for transcription."""

    @patch("kaizen.agents.multi_modal.transcription_agent.WhisperProcessor")
    def test_transcription_memory_storage(
        self, mock_processor_class, temp_audio_file, mock_whisper_result
    ):
        """Test storing transcription results in agent memory."""
        from kaizen.agents.multi_modal.transcription_agent import (
            TranscriptionAgent,
            TranscriptionAgentConfig,
        )

        # Setup mock
        mock_processor = MagicMock()
        mock_processor.transcribe.return_value = mock_whisper_result
        mock_processor_class.return_value = mock_processor

        # Create agent with memory mocked
        config = TranscriptionAgentConfig(model_size="base")
        agent = TranscriptionAgent(config)

        # Mock write_to_memory method
        agent.write_to_memory = MagicMock()

        # Transcribe with memory storage
        agent.transcribe(temp_audio_file, store_in_memory=True)

        # Verify memory was written
        agent.write_to_memory.assert_called_once()
        call_kwargs = agent.write_to_memory.call_args[1]
        assert "content" in call_kwargs
        assert call_kwargs["content"]["text"] == "This is a test transcription."
        assert "tags" in call_kwargs
        assert "transcription" in call_kwargs["tags"]

    @patch("kaizen.agents.multi_modal.transcription_agent.WhisperProcessor")
    def test_transcription_no_memory_storage(
        self, mock_processor_class, temp_audio_file, mock_whisper_result
    ):
        """Test transcription without memory storage."""
        from kaizen.agents.multi_modal.transcription_agent import (
            TranscriptionAgent,
            TranscriptionAgentConfig,
        )

        # Setup mock
        mock_processor = MagicMock()
        mock_processor.transcribe.return_value = mock_whisper_result
        mock_processor_class.return_value = mock_processor

        # Create agent
        config = TranscriptionAgentConfig(model_size="base")
        agent = TranscriptionAgent(config)

        # Mock write_to_memory method
        agent.write_to_memory = MagicMock()

        # Transcribe without memory storage
        agent.transcribe(temp_audio_file, store_in_memory=False)

        # Verify memory was NOT written
        agent.write_to_memory.assert_not_called()


class TestLanguageDetection:
    """Test language detection functionality."""

    @patch("kaizen.agents.multi_modal.transcription_agent.WhisperProcessor")
    def test_detect_language(self, mock_processor_class, temp_audio_file):
        """Test language detection on audio file."""
        from kaizen.agents.multi_modal.transcription_agent import (
            TranscriptionAgent,
            TranscriptionAgentConfig,
        )

        # Setup mock
        mock_processor = MagicMock()
        mock_processor.detect_language.return_value = {
            "language": "de",
            "confidence": 0.89,
            "duration": 5.0,
        }
        mock_processor_class.return_value = mock_processor

        # Create agent and detect language
        config = TranscriptionAgentConfig(model_size="base")
        agent = TranscriptionAgent(config)
        result = agent.detect_language(temp_audio_file)

        # Verify result
        assert result["language"] == "de"
        assert result["confidence"] == 0.89
        assert result["duration"] == 5.0


class TestTranscriptionQuality:
    """Test transcription quality assessment."""

    @patch("kaizen.agents.multi_modal.transcription_agent.WhisperProcessor")
    def test_transcription_quality_assessment(
        self, mock_processor_class, temp_audio_file
    ):
        """Test assessment of transcription quality from confidence scores."""
        from kaizen.agents.multi_modal.transcription_agent import (
            TranscriptionAgent,
            TranscriptionAgentConfig,
        )

        # Setup mock with varying confidence
        mock_result = {
            "text": "High quality transcription",
            "language": "en",
            "language_probability": 0.98,
            "duration": 3.0,
            "segments": [
                {"start": 0.0, "end": 1.5, "text": "High quality", "confidence": -0.1},
                {"start": 1.5, "end": 3.0, "text": "transcription", "confidence": -0.2},
            ],
            "model": "base",
        }
        mock_processor = MagicMock()
        mock_processor.transcribe.return_value = mock_result
        mock_processor_class.return_value = mock_processor

        # Create agent and transcribe
        config = TranscriptionAgentConfig(model_size="base")
        agent = TranscriptionAgent(config)
        result = agent.transcribe(temp_audio_file, store_in_memory=False)

        # Verify quality indicators
        assert result["confidence"] > 0  # Higher confidence = better quality
        assert result["language_probability"] == 0.98  # High language certainty


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

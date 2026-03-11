"""
Unit tests for WhisperProcessor - Local Whisper integration.

Tests audio transcription using faster-whisper library.
Written FIRST following TDD methodology.
"""

import math
import os
import struct
import sys
import tempfile
import wave
from unittest.mock import MagicMock, patch

import pytest

# Check if faster-whisper is available
try:
    import faster_whisper

    FASTER_WHISPER_AVAILABLE = True
except ImportError:
    FASTER_WHISPER_AVAILABLE = False
    # Create a mock module for patching (only for unit tests in this file)
    # Integration tests should see ImportError naturally
    if "faster_whisper" not in sys.modules:
        sys.modules["faster_whisper"] = MagicMock()


# Test fixtures for audio file creation
@pytest.fixture
def temp_audio_file():
    """Create a temporary WAV audio file for testing."""
    # Create a simple sine wave audio file (1 second, 16kHz, mono)
    sample_rate = 16000
    duration = 1.0
    frequency = 440.0  # A4 note

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        temp_path = f.name

    try:
        # Generate audio data
        num_samples = int(sample_rate * duration)
        audio_data = []

        for i in range(num_samples):
            # Generate sine wave
            sample = math.sin(2.0 * math.pi * frequency * i / sample_rate)
            # Convert to 16-bit PCM
            audio_data.append(int(sample * 32767))

        # Write WAV file
        with wave.open(temp_path, "w") as wav_file:
            wav_file.setnchannels(1)  # Mono
            wav_file.setsampwidth(2)  # 16-bit
            wav_file.setframerate(sample_rate)

            # Pack audio data
            packed_data = struct.pack("<" + "h" * len(audio_data), *audio_data)
            wav_file.writeframes(packed_data)

        yield temp_path
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)


@pytest.fixture
def mock_whisper_model():
    """Mock faster-whisper WhisperModel."""
    mock_model = MagicMock()

    # Mock transcribe response
    mock_segment = MagicMock()
    mock_segment.start = 0.0
    mock_segment.end = 1.0
    mock_segment.text = "Test transcription"
    mock_segment.avg_logprob = -0.5
    mock_segment.words = []

    mock_info = MagicMock()
    mock_info.language = "en"
    mock_info.language_probability = 0.95
    mock_info.duration = 1.0

    mock_model.transcribe.return_value = ([mock_segment], mock_info)

    return mock_model


class TestWhisperProcessorInitialization:
    """Test WhisperProcessor initialization and configuration."""

    def test_whisper_processor_initialization(self):
        """Test basic initialization with default config."""
        from kaizen.audio.whisper_processor import WhisperConfig, WhisperProcessor

        config = WhisperConfig(model_size="base")
        processor = WhisperProcessor(config)

        assert processor.config.model_size == "base"
        assert processor.config.device == "cpu"
        assert processor.config.compute_type == "int8"
        assert processor.model is None  # Lazy loading

    def test_whisper_processor_invalid_model_size(self):
        """Test initialization with invalid model size raises error."""
        from kaizen.audio.whisper_processor import WhisperConfig, WhisperProcessor

        config = WhisperConfig(model_size="invalid_size")

        with pytest.raises(ValueError, match="Invalid model size"):
            WhisperProcessor(config)

    def test_whisper_processor_custom_config(self):
        """Test initialization with custom configuration."""
        from kaizen.audio.whisper_processor import WhisperConfig, WhisperProcessor

        config = WhisperConfig(
            model_size="small",
            device="cpu",
            compute_type="float32",
            language="en",
            task="translate",
            beam_size=10,
            temperature=0.2,
        )
        processor = WhisperProcessor(config)

        assert processor.config.model_size == "small"
        assert processor.config.device == "cpu"
        assert processor.config.compute_type == "float32"
        assert processor.config.language == "en"
        assert processor.config.task == "translate"
        assert processor.config.beam_size == 10
        assert processor.config.temperature == 0.2


class TestWhisperModelLoading:
    """Test Whisper model download and loading."""

    @patch("faster_whisper.WhisperModel")
    def test_model_download_base(self, mock_whisper_model_class):
        """Test downloading and loading base model."""
        from kaizen.audio.whisper_processor import WhisperConfig, WhisperProcessor

        mock_model_instance = MagicMock()
        mock_whisper_model_class.return_value = mock_model_instance

        config = WhisperConfig(model_size="base")
        processor = WhisperProcessor(config)

        # Trigger model loading
        processor._load_model()

        # Verify model was created
        mock_whisper_model_class.assert_called_once_with(
            "base", device="cpu", compute_type="int8"
        )
        assert processor.model is not None

    @patch("faster_whisper.WhisperModel")
    def test_model_download_small(self, mock_whisper_model_class):
        """Test downloading and loading small model."""
        from kaizen.audio.whisper_processor import WhisperConfig, WhisperProcessor

        mock_model_instance = MagicMock()
        mock_whisper_model_class.return_value = mock_model_instance

        config = WhisperConfig(model_size="small")
        processor = WhisperProcessor(config)
        processor._load_model()

        mock_whisper_model_class.assert_called_once_with(
            "small", device="cpu", compute_type="int8"
        )

    @patch("faster_whisper.WhisperModel")
    def test_model_lazy_loading(self, mock_whisper_model_class):
        """Test that model is not loaded until needed."""
        from kaizen.audio.whisper_processor import WhisperConfig, WhisperProcessor

        config = WhisperConfig(model_size="base")
        processor = WhisperProcessor(config)

        # Model should not be loaded yet
        assert processor.model is None
        mock_whisper_model_class.assert_not_called()


class TestWhisperTranscription:
    """Test audio transcription functionality."""

    @patch("faster_whisper.WhisperModel")
    def test_transcribe_audio_file(self, mock_whisper_model_class, temp_audio_file):
        """Test basic audio transcription."""
        from kaizen.audio.whisper_processor import WhisperConfig, WhisperProcessor

        # Setup mock
        mock_segment = MagicMock()
        mock_segment.start = 0.0
        mock_segment.end = 1.0
        mock_segment.text = "Hello world"
        mock_segment.avg_logprob = -0.3

        mock_info = MagicMock()
        mock_info.language = "en"
        mock_info.language_probability = 0.98
        mock_info.duration = 1.0

        mock_model = MagicMock()
        mock_model.transcribe.return_value = ([mock_segment], mock_info)
        mock_whisper_model_class.return_value = mock_model

        # Transcribe
        config = WhisperConfig(model_size="base")
        processor = WhisperProcessor(config)
        result = processor.transcribe(temp_audio_file)

        # Verify result
        assert result["text"] == "Hello world"
        assert result["language"] == "en"
        assert result["language_probability"] == 0.98
        assert result["duration"] == 1.0
        assert len(result["segments"]) == 1
        assert result["model"] == "base"

    @patch("faster_whisper.WhisperModel")
    def test_transcribe_with_timestamps(
        self, mock_whisper_model_class, temp_audio_file
    ):
        """Test transcription with word-level timestamps."""
        from kaizen.audio.whisper_processor import WhisperConfig, WhisperProcessor

        # Setup mock with word timestamps
        mock_word1 = MagicMock()
        mock_word1.word = "Hello"
        mock_word1.start = 0.0
        mock_word1.end = 0.5
        mock_word1.probability = 0.95

        mock_word2 = MagicMock()
        mock_word2.word = "world"
        mock_word2.start = 0.5
        mock_word2.end = 1.0
        mock_word2.probability = 0.93

        mock_segment = MagicMock()
        mock_segment.start = 0.0
        mock_segment.end = 1.0
        mock_segment.text = "Hello world"
        mock_segment.avg_logprob = -0.3
        mock_segment.words = [mock_word1, mock_word2]

        mock_info = MagicMock()
        mock_info.language = "en"
        mock_info.language_probability = 0.98
        mock_info.duration = 1.0

        mock_model = MagicMock()
        mock_model.transcribe.return_value = ([mock_segment], mock_info)
        mock_whisper_model_class.return_value = mock_model

        # Transcribe with timestamps
        config = WhisperConfig(model_size="base")
        processor = WhisperProcessor(config)
        result = processor.transcribe(temp_audio_file, word_timestamps=True)

        # Verify word timestamps
        assert len(result["segments"]) == 1
        segment = result["segments"][0]
        assert "words" in segment
        assert len(segment["words"]) == 2
        assert segment["words"][0]["word"] == "Hello"
        assert segment["words"][0]["start"] == 0.0
        assert segment["words"][1]["word"] == "world"

    @patch("faster_whisper.WhisperModel")
    def test_transcribe_nonexistent_file(self, mock_whisper_model_class):
        """Test transcription of nonexistent file raises error."""
        from kaizen.audio.whisper_processor import WhisperConfig, WhisperProcessor

        config = WhisperConfig(model_size="base")
        processor = WhisperProcessor(config)

        with pytest.raises(FileNotFoundError):
            processor.transcribe("/nonexistent/audio.wav")


class TestLanguageDetection:
    """Test language detection functionality."""

    @patch("faster_whisper.WhisperModel")
    def test_language_detection(self, mock_whisper_model_class, temp_audio_file):
        """Test automatic language detection."""
        from kaizen.audio.whisper_processor import WhisperConfig, WhisperProcessor

        # Setup mock for French audio
        mock_segment = MagicMock()
        mock_segment.start = 0.0
        mock_segment.end = 1.0
        mock_segment.text = "Bonjour"
        mock_segment.avg_logprob = -0.3

        mock_info = MagicMock()
        mock_info.language = "fr"
        mock_info.language_probability = 0.92
        mock_info.duration = 1.0

        mock_model = MagicMock()
        mock_model.transcribe.return_value = ([mock_segment], mock_info)
        mock_whisper_model_class.return_value = mock_model

        # Detect language
        config = WhisperConfig(model_size="base")
        processor = WhisperProcessor(config)
        result = processor.detect_language(temp_audio_file)

        # Verify detection
        assert result["language"] == "fr"
        assert result["confidence"] == 0.92
        assert result["duration"] == 1.0

    @patch("faster_whisper.WhisperModel")
    def test_translate_to_english(self, mock_whisper_model_class, temp_audio_file):
        """Test translation of non-English audio to English."""
        from kaizen.audio.whisper_processor import WhisperConfig, WhisperProcessor

        # Setup mock for translation
        mock_segment = MagicMock()
        mock_segment.start = 0.0
        mock_segment.end = 1.0
        mock_segment.text = "Hello"  # Translated from French
        mock_segment.avg_logprob = -0.3

        mock_info = MagicMock()
        mock_info.language = "fr"
        mock_info.language_probability = 0.92
        mock_info.duration = 1.0

        mock_model = MagicMock()
        mock_model.transcribe.return_value = ([mock_segment], mock_info)
        mock_whisper_model_class.return_value = mock_model

        # Transcribe with translation
        config = WhisperConfig(model_size="base")
        processor = WhisperProcessor(config)
        processor.transcribe(temp_audio_file, task="translate")

        # Verify model was called with translate task
        mock_model.transcribe.assert_called_once()
        call_kwargs = mock_model.transcribe.call_args[1]
        assert call_kwargs["task"] == "translate"


class TestBatchProcessing:
    """Test batch transcription functionality."""

    @patch("faster_whisper.WhisperModel")
    def test_batch_transcription(self, mock_whisper_model_class, temp_audio_file):
        """Test transcription of multiple audio files."""
        from kaizen.audio.whisper_processor import WhisperConfig, WhisperProcessor

        # Setup mock
        mock_segment = MagicMock()
        mock_segment.start = 0.0
        mock_segment.end = 1.0
        mock_segment.text = "Test audio"
        mock_segment.avg_logprob = -0.3

        mock_info = MagicMock()
        mock_info.language = "en"
        mock_info.language_probability = 0.95
        mock_info.duration = 1.0

        mock_model = MagicMock()
        mock_model.transcribe.return_value = ([mock_segment], mock_info)
        mock_whisper_model_class.return_value = mock_model

        # Batch transcribe
        config = WhisperConfig(model_size="base")
        processor = WhisperProcessor(config)

        audio_files = [temp_audio_file, temp_audio_file, temp_audio_file]
        results = processor.transcribe_batch(audio_files)

        # Verify results
        assert len(results) == 3
        for result in results:
            assert result["text"] == "Test audio"
            assert result["language"] == "en"

    @patch("faster_whisper.WhisperModel")
    def test_batch_transcription_with_errors(
        self, mock_whisper_model_class, temp_audio_file
    ):
        """Test batch transcription handles errors gracefully."""
        from kaizen.audio.whisper_processor import WhisperConfig, WhisperProcessor

        # Setup mock for valid files
        mock_segment = MagicMock()
        mock_segment.start = 0.0
        mock_segment.end = 1.0
        mock_segment.text = "Test audio"
        mock_segment.avg_logprob = -0.3

        mock_info = MagicMock()
        mock_info.language = "en"
        mock_info.language_probability = 0.95
        mock_info.duration = 1.0

        mock_model = MagicMock()
        mock_model.transcribe.return_value = ([mock_segment], mock_info)
        mock_whisper_model_class.return_value = mock_model

        config = WhisperConfig(model_size="base")
        processor = WhisperProcessor(config)

        # Mix valid and invalid files
        audio_files = [temp_audio_file, "/nonexistent/file.wav", temp_audio_file]
        results = processor.transcribe_batch(audio_files)

        # Verify results
        assert len(results) == 3
        assert "error" not in results[0]
        assert "error" in results[1]  # Error for nonexistent file
        assert "error" not in results[2]


class TestConvenienceFunction:
    """Test convenience function for quick transcription."""

    @patch("faster_whisper.WhisperModel")
    def test_transcribe_audio_convenience(
        self, mock_whisper_model_class, temp_audio_file
    ):
        """Test convenience function for quick transcription."""
        from kaizen.audio.whisper_processor import transcribe_audio

        # Setup mock
        mock_segment = MagicMock()
        mock_segment.start = 0.0
        mock_segment.end = 1.0
        mock_segment.text = "Quick transcription"
        mock_segment.avg_logprob = -0.3

        mock_info = MagicMock()
        mock_info.language = "en"
        mock_info.language_probability = 0.95
        mock_info.duration = 1.0

        mock_model = MagicMock()
        mock_model.transcribe.return_value = ([mock_segment], mock_info)
        mock_whisper_model_class.return_value = mock_model

        # Quick transcribe
        text = transcribe_audio(temp_audio_file, model_size="base")

        assert text == "Quick transcription"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

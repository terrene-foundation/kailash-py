"""
Tests for examples/8-multi-modal/audio-transcription example.

Tests the audio processing example using standardized fixtures.
"""

from pathlib import Path

import pytest

# Import helper
from example_import_helper import import_example_module


@pytest.fixture
def audio_transcription_example():
    """Load audio-transcription example."""
    return import_example_module("examples/8-multi-modal/audio-transcription")


class TestAudioTranscriptionExample:
    """Test audio transcription example workflow."""

    def test_example_imports(self, audio_transcription_example):
        """Test that example imports successfully."""
        assert audio_transcription_example is not None

    def test_uses_transcription_agent(self, audio_transcription_example):
        """Verify example uses TranscriptionAgent."""
        source = Path(audio_transcription_example.__file__).read_text()
        assert "TranscriptionAgent" in source or "WhisperProcessor" in source

    def test_example_structure(self, audio_transcription_example):
        """Verify example has expected structure."""
        source = Path(audio_transcription_example.__file__).read_text()

        # Check for audio processing patterns
        assert "audio" in source.lower() or "transcription" in source.lower()

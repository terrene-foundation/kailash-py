"""
Integration tests for audio support in AI providers.

These tests use REAL infrastructure (NO MOCKING) to validate
the audio processing pipeline.

Prerequisites:
- Real audio test files in tests/fixtures/audio/

NOTE: #1720 Wave-2 retired + DELETED the legacy ``GoogleGeminiProvider`` (and the
other six legacy chat providers). The live-API Gemini audio integration classes
that instantiated ``GoogleGeminiProvider().chat(...)`` were removed with it — the
provider under test no longer exists. Four-axis multimodal (audio/image) content
handling is covered at the wire level by
``tests/unit/llm/test_multimodal_content_parts.py``. The provider-independent
``AudioField`` encoding test below survives.
"""

import os
from pathlib import Path

import pytest

# Skip entire module if no API keys
pytestmark = pytest.mark.integration


def has_google_api():
    """Check if Google API key is available."""
    return bool(os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY"))


@pytest.fixture(scope="module")
def audio_fixtures_dir():
    """Get path to audio fixtures."""
    fixtures_dir = Path(__file__).parent.parent.parent / "fixtures" / "audio"
    if not fixtures_dir.exists():
        pytest.skip(f"Audio fixtures directory not found: {fixtures_dir}")
    return fixtures_dir


@pytest.fixture(scope="module")
def test_audio(audio_fixtures_dir):
    """Test audio file (440Hz tone)."""
    audio_file = audio_fixtures_dir / "test_tone.wav"
    if not audio_file.exists():
        pytest.skip(f"Test audio file not found: {audio_file}")
    return audio_file


class TestAudioFieldIntegration:
    """Test AudioField encoding (provider-independent)."""

    def test_audio_field_to_base64_for_provider(self, test_audio):
        """
        USER INTENT: AudioField.to_base64() should produce data URLs
        that work with providers.
        """
        from kaizen.signatures.multi_modal import AudioField

        field = AudioField()
        field.load(test_audio)

        data_url = field.to_base64()

        # Verify format
        assert data_url.startswith("data:audio/")
        assert ";base64," in data_url

        # Verify it can be decoded
        import base64

        _, b64_data = data_url.split(",", 1)
        decoded = base64.b64decode(b64_data)
        assert len(decoded) > 0

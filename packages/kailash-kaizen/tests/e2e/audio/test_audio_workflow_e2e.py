"""
End-to-end tests for audio support in Kaizen workflows.

Tests complete audio-handling workflows. Uses REAL infrastructure - NO MOCKING.

Prerequisites:
- Real audio test files in tests/fixtures/audio/

NOTE: #1720 Wave-2 retired + DELETED the legacy ``GoogleGeminiProvider`` (and the
other six legacy chat providers). The live-API Gemini audio-workflow classes that
instantiated ``GoogleGeminiProvider().chat(...)`` were removed with it — the
provider under test no longer exists. Four-axis multimodal content handling is
covered at the wire level by ``tests/unit/llm/test_multimodal_content_parts.py``.
The provider-independent audio-utils / AudioField validation + MIME-detection
tests below survive.
"""

from pathlib import Path

import pytest

pytestmark = [pytest.mark.e2e, pytest.mark.timeout(120)]


@pytest.fixture(scope="module")
def audio_fixtures_dir():
    """Get path to audio fixtures."""
    fixtures_dir = Path(__file__).parent.parent.parent / "fixtures" / "audio"
    return fixtures_dir


@pytest.fixture(scope="module")
def test_audio(audio_fixtures_dir):
    """Test audio file."""
    audio_file = audio_fixtures_dir / "test_tone.wav"
    if not audio_file.exists():
        pytest.skip(f"Test audio file not found: {audio_file}")
    return str(audio_file)


class TestAudioErrorHandlingE2E:
    """Test error handling in audio workflows (provider-independent)."""

    def test_e2e_nonexistent_audio_file(self):
        """
        USER STORY: As a user, I expect clear error messages when
        I provide an invalid audio file path.
        """
        from kaizen.nodes.ai.audio_utils import encode_audio

        with pytest.raises(FileNotFoundError, match="Audio file not found"):
            encode_audio("/nonexistent/path/audio.mp3")

    def test_e2e_empty_audio_validation(self, tmp_path):
        """
        USER STORY: As a user, I expect validation to catch
        empty or invalid audio files.
        """
        from kaizen.signatures.multi_modal import AudioField

        # Create empty file
        empty_audio = tmp_path / "empty.mp3"
        empty_audio.touch()

        field = AudioField()
        field.load(empty_audio)

        # Empty audio should fail validation (no data)
        # Note: The field loads but validation should catch issues
        assert field._size_bytes == 0, "Size should be 0 for empty file"

    def test_e2e_size_validation(self, tmp_path):
        """
        USER STORY: As a user, I want to know if my audio file
        is too large before sending to the API.
        """
        from kaizen.nodes.ai.audio_utils import validate_audio_size

        # Create a small file
        small_audio = tmp_path / "small.mp3"
        with open(small_audio, "wb") as f:
            f.write(b"\x00" * 1000)  # 1KB

        is_valid, error = validate_audio_size(str(small_audio), max_size_mb=0.0001)

        assert is_valid is False, "Should fail validation"
        assert error is not None, "Should have error message"
        assert "exceeds" in error.lower(), "Error should mention exceeding limit"


class TestAudioFormatsE2E:
    """Test audio-format MIME detection end-to-end (provider-independent)."""

    def test_e2e_mime_type_detection(self):
        """Test MIME type detection for various formats."""
        from kaizen.nodes.ai.audio_utils import get_audio_media_type

        test_cases = [
            ("audio.mp3", "audio/mpeg"),
            ("audio.wav", "audio/wav"),
            ("audio.m4a", "audio/mp4"),
            ("audio.ogg", "audio/ogg"),
            ("audio.flac", "audio/flac"),
            ("audio.webm", "audio/webm"),
        ]

        for filename, expected_mime in test_cases:
            actual_mime = get_audio_media_type(filename)
            assert (
                actual_mime == expected_mime
            ), f"Expected {expected_mime} for {filename}, got {actual_mime}"

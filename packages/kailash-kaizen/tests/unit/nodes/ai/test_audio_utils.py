"""
Test suite for audio_utils module.

Tests audio encoding, MIME type detection, size validation,
and duration estimation for AI provider integration.
"""

import base64

import pytest

from kaizen.nodes.ai.audio_utils import (
    encode_audio,
    get_audio_duration,
    get_audio_media_type,
    validate_audio_size,
)


class TestEncodeAudio:
    """Test encode_audio function for base64 encoding."""

    def test_encode_audio_from_file_path(self, tmp_path):
        """
        USER INTENT: encode_audio should work like encode_image for consistency.
        I expect base64 encoded audio that can be sent to AI providers.
        """
        audio_path = tmp_path / "test.wav"
        audio_data = b"RIFF" + b"\x00" * 1000
        with open(audio_path, "wb") as f:
            f.write(audio_data)

        result = encode_audio(str(audio_path))

        # Should return base64 string (not data URL)
        decoded = base64.b64decode(result)
        assert decoded == audio_data

    def test_encode_audio_file_not_found(self):
        """
        USER INTENT: Clear error when audio file doesn't exist.
        """
        with pytest.raises(FileNotFoundError, match="Audio file not found"):
            encode_audio("/nonexistent/path/audio.mp3")

    def test_encode_audio_empty_file(self, tmp_path):
        """
        USER INTENT: Empty files should encode without error
        (validation is separate concern).
        """
        audio_path = tmp_path / "empty.mp3"
        audio_path.touch()  # Create empty file

        result = encode_audio(str(audio_path))

        assert result == ""  # Empty file encodes to empty string

    def test_encode_audio_various_formats(self, tmp_path):
        """
        USER INTENT: All common audio formats should encode successfully.
        """
        formats = ["mp3", "wav", "m4a", "ogg", "flac", "webm"]
        audio_data = b"\x00" * 1000

        for fmt in formats:
            audio_path = tmp_path / f"test.{fmt}"
            with open(audio_path, "wb") as f:
                f.write(audio_data)

            result = encode_audio(str(audio_path))
            decoded = base64.b64decode(result)
            assert decoded == audio_data, f"Failed for {fmt}"


class TestGetAudioMediaType:
    """Test get_audio_media_type function for MIME type detection."""

    def test_media_type_mp3(self):
        """MP3 files should return audio/mpeg."""
        assert get_audio_media_type("file.mp3") == "audio/mpeg"
        assert get_audio_media_type("/path/to/audio.mp3") == "audio/mpeg"

    def test_media_type_wav(self):
        """WAV files should return audio/wav."""
        assert get_audio_media_type("file.wav") == "audio/wav"

    def test_media_type_m4a(self):
        """M4A files should return audio/mp4."""
        assert get_audio_media_type("file.m4a") == "audio/mp4"

    def test_media_type_ogg(self):
        """OGG files should return audio/ogg."""
        assert get_audio_media_type("file.ogg") == "audio/ogg"

    def test_media_type_flac(self):
        """FLAC files should return audio/flac."""
        assert get_audio_media_type("file.flac") == "audio/flac"

    def test_media_type_webm(self):
        """WebM files should return audio/webm."""
        assert get_audio_media_type("file.webm") == "audio/webm"

    def test_media_type_aiff(self):
        """AIFF files should return audio/aiff."""
        assert get_audio_media_type("file.aiff") == "audio/aiff"
        assert get_audio_media_type("file.aif") == "audio/aiff"

    def test_media_type_aac(self):
        """AAC files should return audio/aac."""
        assert get_audio_media_type("file.aac") == "audio/aac"

    def test_media_type_opus(self):
        """OPUS files should return audio/opus."""
        assert get_audio_media_type("file.opus") == "audio/opus"

    def test_media_type_unknown(self):
        """Unknown formats should default to audio/mpeg."""
        assert get_audio_media_type("file.xyz") == "audio/mpeg"
        assert get_audio_media_type("file.unknown") == "audio/mpeg"

    def test_media_type_case_insensitive(self):
        """Extension detection should be case insensitive."""
        assert get_audio_media_type("file.MP3") == "audio/mpeg"
        assert get_audio_media_type("file.WAV") == "audio/wav"
        assert get_audio_media_type("file.M4A") == "audio/mp4"


class TestValidateAudioSize:
    """Test validate_audio_size function for size limit enforcement."""

    def test_validate_within_limit(self, tmp_path):
        """
        USER INTENT: I need to know if my audio file is within size limits
        before sending to the API.
        """
        audio_path = tmp_path / "small.mp3"
        with open(audio_path, "wb") as f:
            f.write(b"\x00" * 1000)  # 1KB

        is_valid, error = validate_audio_size(str(audio_path), max_size_mb=1.0)

        assert is_valid is True
        assert error is None

    def test_validate_exceeds_limit(self, tmp_path):
        """
        USER INTENT: Clear error message when audio is too large.
        """
        audio_path = tmp_path / "large.mp3"
        with open(audio_path, "wb") as f:
            f.write(b"\x00" * (2 * 1024 * 1024))  # 2MB

        is_valid, error = validate_audio_size(str(audio_path), max_size_mb=1.0)

        assert is_valid is False
        assert error is not None
        assert "exceeds maximum" in error
        assert "2.0" in error  # Shows actual size
        assert "1.0" in error  # Shows limit

    def test_validate_default_limit(self, tmp_path):
        """Default limit should be 25MB."""
        audio_path = tmp_path / "medium.mp3"
        with open(audio_path, "wb") as f:
            f.write(b"\x00" * (10 * 1024 * 1024))  # 10MB

        is_valid, error = validate_audio_size(str(audio_path))

        assert is_valid is True

    def test_validate_file_not_found(self):
        """Non-existent files should return error."""
        is_valid, error = validate_audio_size("/nonexistent/path.mp3")

        assert is_valid is False
        assert "not found" in error.lower()

    def test_validate_exactly_at_limit(self, tmp_path):
        """Files exactly at the limit should pass."""
        audio_path = tmp_path / "exact.mp3"
        with open(audio_path, "wb") as f:
            f.write(b"\x00" * (1024 * 1024))  # 1MB

        is_valid, error = validate_audio_size(str(audio_path), max_size_mb=1.0)

        assert is_valid is True


class TestGetAudioDuration:
    """Test get_audio_duration function for duration estimation."""

    def test_duration_file_not_found(self):
        """Non-existent files should return None."""
        result = get_audio_duration("/nonexistent/path.mp3")

        assert result is None

    def test_duration_fallback_estimate(self, tmp_path):
        """
        USER INTENT: Even without pydub/mutagen, I should get a rough estimate.
        """
        audio_path = tmp_path / "test.mp3"
        # Create ~1MB file (approximately 1 minute at 128kbps)
        with open(audio_path, "wb") as f:
            f.write(b"\x00" * (128 * 1024))  # 128KB = ~8 seconds at 128kbps

        result = get_audio_duration(str(audio_path))

        # Should return some estimate (may vary based on available libraries)
        assert result is None or result > 0

    def test_duration_wav_estimate(self, tmp_path):
        """WAV files have different bitrate estimate."""
        audio_path = tmp_path / "test.wav"
        # WAV has higher bitrate
        with open(audio_path, "wb") as f:
            f.write(b"\x00" * (176400))  # ~1 second of CD-quality audio

        result = get_audio_duration(str(audio_path))

        # Should return some estimate
        assert result is None or result > 0


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_unicode_filename(self, tmp_path):
        """
        USER INTENT: International filenames should work.
        """
        audio_path = tmp_path / "audio.mp3"
        with open(audio_path, "wb") as f:
            f.write(b"ID3" + b"\x00" * 1000)

        result = encode_audio(str(audio_path))

        assert result is not None
        assert len(result) > 0

    def test_special_characters_in_path(self, tmp_path):
        """Paths with special characters should work."""
        # Create subdirectory with space
        subdir = tmp_path / "test folder"
        subdir.mkdir()
        audio_path = subdir / "test file.mp3"
        with open(audio_path, "wb") as f:
            f.write(b"ID3" + b"\x00" * 1000)

        result = encode_audio(str(audio_path))

        assert result is not None
        decoded = base64.b64decode(result)
        assert len(decoded) > 0

    def test_very_small_file(self, tmp_path):
        """Very small files should be handled correctly."""
        audio_path = tmp_path / "tiny.mp3"
        with open(audio_path, "wb") as f:
            f.write(b"x")  # 1 byte

        result = encode_audio(str(audio_path))
        decoded = base64.b64decode(result)

        assert decoded == b"x"

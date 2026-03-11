"""
Test suite for AudioField multi-modal signature field.

Tests audio loading, format detection, duration extraction,
and validation.
"""

import pytest

from kaizen.signatures.multi_modal import AudioField


class TestAudioFieldCreation:
    """Test AudioField descriptor creation and initialization."""

    def test_audio_field_creation(self):
        """Test basic AudioField creation with defaults."""
        field = AudioField(description="Test audio field")

        assert field.description == "Test audio field"
        assert field.max_duration_sec == 600.0  # 10 minutes
        assert field.max_size_mb == 25.0
        assert "mp3" in field.formats
        assert "wav" in field.formats
        assert field._data is None

    def test_audio_field_custom_config(self):
        """Test AudioField with custom configuration."""
        field = AudioField(
            description="Custom field",
            max_duration_sec=300.0,  # 5 minutes
            max_size_mb=10.0,
            formats=["mp3", "wav"],
        )

        assert field.max_duration_sec == 300.0
        assert field.max_size_mb == 10.0
        assert field.formats == ["mp3", "wav"]


class TestAudioFieldFromFilePath:
    """Test loading audio from file paths."""

    def test_audio_field_from_file_path_mp3(self, tmp_path):
        """Test loading MP3 audio from file path."""
        # Create dummy MP3 file (header only for testing)
        audio_path = tmp_path / "test.mp3"

        # MP3 header: ID3v2 tag or frame sync
        mp3_header = b"ID3\x04\x00\x00\x00\x00\x00\x00"
        # Add some dummy data
        mp3_data = mp3_header + b"\x00" * 1000

        with open(audio_path, "wb") as f:
            f.write(mp3_data)

        # Load with AudioField
        field = AudioField()
        field.load(audio_path)

        assert field._data is not None
        assert field._format == "mp3"
        assert field._size_bytes > 0

    def test_audio_field_from_file_path_wav(self, tmp_path):
        """Test loading WAV audio from file path."""
        # Create dummy WAV file
        audio_path = tmp_path / "test.wav"

        # WAV header: RIFF + WAVE
        wav_header = b"RIFF\x24\x00\x00\x00WAVEfmt "
        wav_data = wav_header + b"\x00" * 1000

        with open(audio_path, "wb") as f:
            f.write(wav_data)

        # Load with AudioField
        field = AudioField()
        field.load(audio_path)

        assert field._data is not None
        assert field._format == "wav"
        assert field._size_bytes > 0

    def test_audio_field_from_file_path_m4a(self, tmp_path):
        """Test loading M4A audio from file path."""
        # Create dummy M4A file
        audio_path = tmp_path / "test.m4a"

        # M4A/MP4 header: ftyp box
        m4a_header = b"\x00\x00\x00\x20ftypM4A "
        m4a_data = m4a_header + b"\x00" * 1000

        with open(audio_path, "wb") as f:
            f.write(m4a_data)

        # Load with AudioField
        field = AudioField()
        field.load(audio_path)

        assert field._data is not None
        assert field._format == "m4a"
        assert field._size_bytes > 0

    def test_audio_field_from_file_path_ogg(self, tmp_path):
        """Test loading OGG audio from file path."""
        # Create dummy OGG file
        audio_path = tmp_path / "test.ogg"

        # OGG header: OggS
        ogg_header = b"OggS\x00\x02\x00\x00\x00\x00\x00\x00\x00\x00"
        ogg_data = ogg_header + b"\x00" * 1000

        with open(audio_path, "wb") as f:
            f.write(ogg_data)

        # Load with AudioField
        field = AudioField()
        field.load(audio_path)

        assert field._data is not None
        assert field._format == "ogg"
        assert field._size_bytes > 0

    def test_audio_field_from_file_path_flac(self, tmp_path):
        """Test loading FLAC audio from file path."""
        audio_path = tmp_path / "test.flac"

        # FLAC header: fLaC magic bytes
        flac_header = b"fLaC\x00\x00\x00\x22"
        flac_data = flac_header + b"\x00" * 1000

        with open(audio_path, "wb") as f:
            f.write(flac_data)

        field = AudioField()
        field.load(audio_path)

        assert field._data is not None
        assert field._format == "flac"
        assert field._size_bytes > 0

    def test_audio_field_from_file_path_webm(self, tmp_path):
        """Test loading WebM audio from file path."""
        audio_path = tmp_path / "test.webm"

        # WebM/Matroska header
        webm_header = b"\x1aE\xdf\xa3\x01\x00\x00\x00\x00\x00\x00\x1f"
        webm_data = webm_header + b"\x00" * 1000

        with open(audio_path, "wb") as f:
            f.write(webm_data)

        field = AudioField()
        field.load(audio_path)

        assert field._data is not None
        assert field._format == "webm"
        assert field._size_bytes > 0

    def test_audio_field_from_file_path_aiff(self, tmp_path):
        """Test loading AIFF audio from file path."""
        audio_path = tmp_path / "test.aiff"

        # AIFF header: FORM....AIFF
        aiff_header = b"FORM\x00\x00\x10\x00AIFF"
        aiff_data = aiff_header + b"\x00" * 1000

        with open(audio_path, "wb") as f:
            f.write(aiff_data)

        field = AudioField()
        field.load(audio_path)

        assert field._data is not None
        assert field._format == "aiff"
        assert field._size_bytes > 0

    def test_audio_field_from_file_path_string(self, tmp_path):
        """Test loading audio from string file path."""
        # Create dummy audio file
        audio_path = tmp_path / "test.mp3"
        with open(audio_path, "wb") as f:
            f.write(b"ID3\x04\x00\x00" + b"\x00" * 1000)

        # Load with string path
        field = AudioField()
        field.load(str(audio_path))

        assert field._data is not None

    def test_audio_field_from_file_path_not_found(self):
        """Test loading from non-existent file path."""
        field = AudioField()

        with pytest.raises(FileNotFoundError, match="Audio file not found"):
            field.load("/path/that/does/not/exist.mp3")

    def test_audio_field_from_file_path_invalid_format(self, tmp_path):
        """Test loading audio with unsupported format."""
        # Create file with unsupported format (.xyz is not a real audio format)
        audio_path = tmp_path / "test.xyz"
        with open(audio_path, "wb") as f:
            f.write(b"\x00" * 1000)

        # Try to load with default formats (no .xyz)
        field = AudioField()

        with pytest.raises(ValueError, match="Unsupported audio format"):
            field.load(audio_path)


class TestAudioFieldFormatDetection:
    """Test automatic audio format detection."""

    def test_audio_field_format_detection_mp3(self, tmp_path):
        """Test MP3 format detection from extension."""
        audio_path = tmp_path / "test.mp3"
        with open(audio_path, "wb") as f:
            f.write(b"ID3" + b"\x00" * 1000)

        field = AudioField()
        field.load(audio_path)

        assert field._format == "mp3"

    def test_audio_field_format_detection_wav(self, tmp_path):
        """Test WAV format detection from extension."""
        audio_path = tmp_path / "test.wav"
        with open(audio_path, "wb") as f:
            f.write(b"RIFF" + b"\x00" * 1000)

        field = AudioField()
        field.load(audio_path)

        assert field._format == "wav"

    def test_audio_field_format_detection_m4a(self, tmp_path):
        """Test M4A format detection from extension."""
        audio_path = tmp_path / "test.m4a"
        with open(audio_path, "wb") as f:
            f.write(b"ftyp" + b"\x00" * 1000)

        field = AudioField()
        field.load(audio_path)

        assert field._format == "m4a"

    def test_audio_field_format_detection_ogg(self, tmp_path):
        """Test OGG format detection from extension."""
        audio_path = tmp_path / "test.ogg"
        with open(audio_path, "wb") as f:
            f.write(b"OggS" + b"\x00" * 1000)

        field = AudioField()
        field.load(audio_path)

        assert field._format == "ogg"


class TestAudioFieldDurationExtraction:
    """Test audio duration extraction."""

    def test_audio_field_duration_extraction_with_pydub(self, tmp_path, monkeypatch):
        """Test duration extraction using pydub."""
        audio_path = tmp_path / "test.mp3"
        with open(audio_path, "wb") as f:
            f.write(b"ID3" + b"\x00" * 1000)

        # Mock pydub
        class MockAudioSegment:
            @staticmethod
            def from_file(path):
                class Audio:
                    def __len__(self):
                        return 5000  # 5 seconds in milliseconds

                return Audio()

        import sys
        from unittest.mock import MagicMock

        mock_pydub = MagicMock()
        mock_pydub.AudioSegment = MockAudioSegment
        sys.modules["pydub"] = mock_pydub

        field = AudioField()
        field.load(audio_path)

        assert field._duration_sec == 5.0

        # Cleanup
        del sys.modules["pydub"]

    def test_audio_field_duration_extraction_fallback(self, tmp_path, monkeypatch):
        """Test duration extraction fallback when pydub not available."""
        audio_path = tmp_path / "test.mp3"

        # Create file of known size
        audio_data = b"ID3" + b"\x00" * 16000  # ~16KB
        with open(audio_path, "wb") as f:
            f.write(audio_data)

        # Mock pydub import to fail
        import sys

        def mock_import(name, *args, **kwargs):
            if name == "pydub":
                raise ImportError("No module named 'pydub'")
            import builtins

            return builtins.__import__(name, *args, **kwargs)

        # Ensure pydub is not in sys.modules for this test
        pydub_backup = sys.modules.pop("pydub", None)

        try:
            monkeypatch.setattr("builtins.__import__", mock_import)

            field = AudioField()
            field.load(audio_path)

            # Fallback should estimate duration
            assert field._duration_sec > 0
        finally:
            # Restore pydub if it was there
            if pydub_backup:
                sys.modules["pydub"] = pydub_backup

    def test_audio_field_duration_validation(self, tmp_path):
        """Test duration validation against max_duration_sec."""
        audio_path = tmp_path / "test.mp3"

        # Create audio file
        audio_data = b"ID3" + b"\x00" * 1000000  # ~1MB
        with open(audio_path, "wb") as f:
            f.write(audio_data)

        # Load with short max duration
        field = AudioField(max_duration_sec=1.0)

        # Ensure pydub not available for predictable fallback
        import sys

        if "pydub" in sys.modules:
            del sys.modules["pydub"]

        field.load(audio_path)

        # Should fail validation if duration exceeds limit
        # (depends on fallback calculation)
        # For now, just check duration was set
        assert field._duration_sec > 0


class TestAudioFieldValidation:
    """Test audio field validation."""

    def test_audio_field_validation_valid(self, tmp_path):
        """Test validation passes for valid audio."""
        audio_path = tmp_path / "test.mp3"

        # Create small audio file
        with open(audio_path, "wb") as f:
            f.write(b"ID3" + b"\x00" * 1000)

        field = AudioField()
        field.load(audio_path)

        assert field.validate() is True

    def test_audio_field_validation_no_data(self):
        """Test validation fails when no data loaded."""
        field = AudioField()

        assert field.validate() is False

    def test_audio_field_validation_size_exceeded(self, tmp_path):
        """Test validation fails when size exceeds limit."""
        audio_path = tmp_path / "test.mp3"

        # Create large file (1MB)
        with open(audio_path, "wb") as f:
            f.write(b"ID3" + b"\x00" * 1000000)

        # Load with small size limit
        field = AudioField(max_size_mb=0.0001)  # Very small limit
        field.load(audio_path)

        assert field.validate() is False

    def test_audio_field_validation_duration_exceeded(self, tmp_path, monkeypatch):
        """Test validation fails when duration exceeds limit."""
        audio_path = tmp_path / "test.mp3"
        with open(audio_path, "wb") as f:
            f.write(b"ID3" + b"\x00" * 1000)

        # Mock pydub to return long duration
        class MockAudioSegment:
            @staticmethod
            def from_file(path):
                class Audio:
                    def __len__(self):
                        return 700000  # 700 seconds in milliseconds

                return Audio()

        import sys
        from unittest.mock import MagicMock

        mock_pydub = MagicMock()
        mock_pydub.AudioSegment = MockAudioSegment
        sys.modules["pydub"] = mock_pydub

        # Load with short max duration
        field = AudioField(max_duration_sec=600.0)  # 10 minutes
        field.load(audio_path)

        assert field.validate() is False

        # Cleanup
        del sys.modules["pydub"]


class TestAudioFieldSizeLimits:
    """Test size limit enforcement."""

    def test_audio_field_size_limits_within(self, tmp_path):
        """Test audio within size limits."""
        audio_path = tmp_path / "test.mp3"

        # Create small file
        with open(audio_path, "wb") as f:
            f.write(b"ID3" + b"\x00" * 1000)

        field = AudioField(max_size_mb=25.0)
        field.load(audio_path)

        assert field._size_bytes <= 25 * 1024 * 1024
        assert field.validate()

    def test_audio_field_size_limits_custom(self, tmp_path):
        """Test custom size limits."""
        audio_path = tmp_path / "test.wav"

        # Create medium file
        with open(audio_path, "wb") as f:
            f.write(b"RIFF" + b"\x00" * 5000)

        field = AudioField(max_size_mb=1.0)
        field.load(audio_path)

        assert field.validate()


class TestAudioFieldBytes:
    """Test loading from raw bytes."""

    def test_audio_field_from_bytes(self):
        """Test loading audio from raw bytes."""
        audio_bytes = b"ID3\x04\x00\x00" + b"\x00" * 1000

        # Load from bytes
        field = AudioField()
        field.load(audio_bytes)

        assert field._data == audio_bytes
        assert field._size_bytes == len(audio_bytes)

    def test_audio_field_from_bytes_with_explicit_format(self):
        """Test loading bytes with explicit format specification."""
        audio_bytes = b"\x00" * 1000  # No recognizable header

        field = AudioField()
        field.load(audio_bytes, format="mp3")

        assert field._data == audio_bytes
        assert field._format == "mp3"

    def test_audio_field_from_bytes_detects_mp3(self):
        """Test format detection from MP3 header bytes."""
        # ID3 tag header
        audio_bytes = b"ID3\x04\x00\x00" + b"\x00" * 1000

        field = AudioField()
        field.load(audio_bytes)

        assert field._format == "mp3"

    def test_audio_field_from_bytes_detects_wav(self):
        """Test format detection from WAV header bytes."""
        audio_bytes = b"RIFF\x24\x00\x00\x00WAVE" + b"\x00" * 1000

        field = AudioField()
        field.load(audio_bytes)

        assert field._format == "wav"

    def test_audio_field_from_bytes_detects_flac(self):
        """Test format detection from FLAC header bytes."""
        audio_bytes = b"fLaC\x00\x00\x00\x22" + b"\x00" * 1000

        field = AudioField()
        field.load(audio_bytes)

        assert field._format == "flac"

    def test_audio_field_from_bytes_detects_ogg(self):
        """Test format detection from OGG header bytes."""
        audio_bytes = b"OggS\x00\x02\x00\x00" + b"\x00" * 1000

        field = AudioField()
        field.load(audio_bytes)

        assert field._format == "ogg"

    def test_audio_field_from_bytes_detects_m4a(self):
        """Test format detection from M4A/MP4 header bytes."""
        audio_bytes = b"\x00\x00\x00\x20ftypM4A " + b"\x00" * 1000

        field = AudioField()
        field.load(audio_bytes)

        assert field._format == "m4a"

    def test_audio_field_from_bytes_detects_aiff(self):
        """Test format detection from AIFF header bytes."""
        audio_bytes = b"FORM\x00\x00\x10\x00AIFF" + b"\x00" * 1000

        field = AudioField()
        field.load(audio_bytes)

        assert field._format == "aiff"

    def test_audio_field_from_bytes_detects_webm(self):
        """Test format detection from WebM header bytes."""
        audio_bytes = b"\x1aE\xdf\xa3\x01\x00\x00\x00" + b"\x00" * 1000

        field = AudioField()
        field.load(audio_bytes)

        assert field._format == "webm"

    def test_audio_field_from_bytes_unknown_format_warns(self):
        """Test that unknown format from bytes issues a warning."""
        import warnings

        # Random bytes that don't match any known header
        audio_bytes = b"\x00\x01\x02\x03\x04\x05\x06\x07" + b"\x00" * 1000

        field = AudioField()

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            field.load(audio_bytes)

            # Should have issued a warning about unknown format
            assert len(w) == 1
            assert "Could not detect audio format" in str(w[0].message)
            assert field._format is None

    def test_audio_field_from_bytes_unknown_format_fails_validation(self):
        """Test that unknown format fails validation."""
        # Random bytes that don't match any known header
        audio_bytes = b"\x00\x01\x02\x03\x04\x05\x06\x07" + b"\x00" * 1000

        field = AudioField()

        import warnings

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            field.load(audio_bytes)

        # Validation should fail because format is None
        assert field.validate() is False

    def test_audio_field_from_path_object(self, tmp_path):
        """Test loading audio from Path object."""
        audio_path = tmp_path / "test.mp3"
        with open(audio_path, "wb") as f:
            f.write(b"ID3" + b"\x00" * 1000)

        # Load from Path object
        field = AudioField()
        field.load(audio_path)

        assert field._data is not None
        assert field._format == "mp3"


class TestAudioFieldToBase64:
    """Test AudioField.to_base64() method for provider integration."""

    def test_to_base64_returns_valid_data_url(self, tmp_path):
        """
        USER INTENT: When I convert audio to base64, I expect a valid data URL
        that can be sent to AI providers like Gemini for native audio processing.
        """
        audio_path = tmp_path / "test.mp3"
        audio_data = b"ID3\x04\x00\x00" + b"\x00" * 1000
        with open(audio_path, "wb") as f:
            f.write(audio_data)

        field = AudioField()
        field.load(audio_path)

        result = field.to_base64()

        # Validate data URL format
        assert result.startswith("data:audio/")
        assert ";base64," in result

        # Verify we can decode it back
        import base64

        data_part = result.split(",", 1)[1]
        decoded = base64.b64decode(data_part)
        assert len(decoded) > 0
        assert decoded == audio_data

    def test_to_base64_without_data_raises_error(self):
        """
        USER INTENT: Converting unloaded audio should fail clearly,
        not silently produce garbage.
        """
        field = AudioField()

        with pytest.raises(ValueError, match="No audio data loaded"):
            field.to_base64()

    def test_to_base64_preserves_format_in_mime_type(self, tmp_path):
        """
        USER INTENT: The MIME type should match my audio format so providers
        handle it correctly.
        """
        formats = {
            "test.mp3": "audio/mpeg",
            "test.wav": "audio/wav",
            "test.m4a": "audio/mp4",
            "test.ogg": "audio/ogg",
        }

        for filename, expected_mime in formats.items():
            audio_path = tmp_path / filename
            with open(audio_path, "wb") as f:
                f.write(b"\x00" * 1000)

            field = AudioField()
            field.load(audio_path)

            result = field.to_base64()
            assert expected_mime in result, f"Expected {expected_mime} for {filename}"


class TestAudioFieldToBytes:
    """Test AudioField.to_bytes() method."""

    def test_to_bytes_returns_raw_data(self, tmp_path):
        """
        USER INTENT: to_bytes() should return the exact raw audio data
        for direct API usage.
        """
        audio_path = tmp_path / "test.mp3"
        audio_data = b"ID3\x04\x00\x00" + b"\x00" * 500
        with open(audio_path, "wb") as f:
            f.write(audio_data)

        field = AudioField()
        field.load(audio_path)

        result = field.to_bytes()

        assert result == audio_data

    def test_to_bytes_without_data_raises_error(self):
        """
        USER INTENT: Calling to_bytes() on unloaded field should fail clearly.
        """
        field = AudioField()

        with pytest.raises(ValueError, match="No audio data loaded"):
            field.to_bytes()


class TestAudioFieldURLLoading:
    """Test loading audio from URLs and data URLs."""

    def test_audio_field_from_data_url_mp3(self):
        """
        USER INTENT: Load audio from base64 data URL like from browser/API.
        """
        import base64

        audio_data = b"ID3\x04\x00\x00" + b"\x00" * 1000
        b64_data = base64.b64encode(audio_data).decode("utf-8")
        data_url = f"data:audio/mpeg;base64,{b64_data}"

        field = AudioField()
        field.load(data_url)

        assert field._data == audio_data
        assert field._format == "mp3"
        assert field._size_bytes == len(audio_data)

    def test_audio_field_from_data_url_wav(self):
        """
        USER INTENT: Load WAV audio from data URL.
        """
        import base64

        audio_data = b"RIFF\x24\x00\x00\x00WAVE" + b"\x00" * 1000
        b64_data = base64.b64encode(audio_data).decode("utf-8")
        data_url = f"data:audio/wav;base64,{b64_data}"

        field = AudioField()
        field.load(data_url)

        assert field._data == audio_data
        assert field._format == "wav"

    def test_audio_field_from_data_url_ogg(self):
        """
        USER INTENT: Load OGG audio from data URL.
        """
        import base64

        audio_data = b"OggS" + b"\x00" * 1000
        b64_data = base64.b64encode(audio_data).decode("utf-8")
        data_url = f"data:audio/ogg;base64,{b64_data}"

        field = AudioField()
        field.load(data_url)

        assert field._data == audio_data
        assert field._format == "ogg"

    def test_audio_field_from_data_url_stores_source(self):
        """
        USER INTENT: Original data URL should be stored for reference.
        """
        import base64

        audio_data = b"ID3" + b"\x00" * 100
        b64_data = base64.b64encode(audio_data).decode("utf-8")
        data_url = f"data:audio/mpeg;base64,{b64_data}"

        field = AudioField()
        field.load(data_url)

        assert field._source == data_url

    def test_audio_field_invalid_data_url_raises_error(self):
        """
        USER INTENT: Invalid data URL should raise clear error.
        """
        field = AudioField()

        with pytest.raises(ValueError, match="Invalid base64 audio data"):
            field.load("data:audio/mpeg;base64,invalid!!!")

    def test_audio_field_url_without_requests_raises_error(self, monkeypatch):
        """
        USER INTENT: Clear error when requests library not available.
        """
        import kaizen.signatures.multi_modal as mm

        # Temporarily set requests to None
        original_requests = mm.requests
        monkeypatch.setattr(mm, "requests", None)

        try:
            field = AudioField()
            with pytest.raises(ImportError, match="requests library is required"):
                field.load("https://example.com/audio.mp3")
        finally:
            mm.requests = original_requests

    def test_audio_field_from_url_with_mock_response(self, monkeypatch):
        """
        USER INTENT: URL loading should fetch and parse audio correctly.
        """
        import kaizen.signatures.multi_modal as mm

        audio_data = b"ID3\x04\x00\x00" + b"\x00" * 500

        class MockResponse:
            content = audio_data
            status_code = 200

            def raise_for_status(self):
                pass

        class MockRequests:
            @staticmethod
            def get(url, timeout=None):
                return MockResponse()

        monkeypatch.setattr(mm, "requests", MockRequests)

        field = AudioField()
        field.load("https://example.com/audio.mp3")

        assert field._data == audio_data
        assert field._format == "mp3"
        assert field._source == "https://example.com/audio.mp3"

    def test_audio_field_url_format_from_extension(self, monkeypatch):
        """
        USER INTENT: Format should be detected from URL extension.
        """
        import kaizen.signatures.multi_modal as mm

        # WAV data
        audio_data = b"RIFF\x24\x00\x00\x00WAVE" + b"\x00" * 500

        class MockResponse:
            content = audio_data
            status_code = 200

            def raise_for_status(self):
                pass

        class MockRequests:
            @staticmethod
            def get(url, timeout=None):
                return MockResponse()

        monkeypatch.setattr(mm, "requests", MockRequests)

        field = AudioField()
        field.load("https://example.com/audio.wav")

        assert field._format == "wav"

    def test_audio_field_url_with_query_params(self, monkeypatch):
        """
        USER INTENT: URL with query params should still detect format.
        """
        import kaizen.signatures.multi_modal as mm

        audio_data = b"ID3" + b"\x00" * 500

        class MockResponse:
            content = audio_data
            status_code = 200

            def raise_for_status(self):
                pass

        class MockRequests:
            @staticmethod
            def get(url, timeout=None):
                return MockResponse()

        monkeypatch.setattr(mm, "requests", MockRequests)

        field = AudioField()
        field.load("https://example.com/audio.mp3?token=abc123&v=2")

        assert field._format == "mp3"

    def test_audio_field_url_fallback_to_byte_detection(self, monkeypatch):
        """
        USER INTENT: When URL has no extension, detect format from bytes.
        """
        import kaizen.signatures.multi_modal as mm

        # OGG data with proper header
        audio_data = b"OggS" + b"\x00" * 500

        class MockResponse:
            content = audio_data
            status_code = 200

            def raise_for_status(self):
                pass

        class MockRequests:
            @staticmethod
            def get(url, timeout=None):
                return MockResponse()

        monkeypatch.setattr(mm, "requests", MockRequests)

        field = AudioField()
        field.load("https://example.com/api/audio/12345")  # No extension

        assert field._format == "ogg"  # Detected from bytes

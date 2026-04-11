"""Regression tests for issue #410: multimodal input detection.

The bug: ``_create_messages_from_inputs()`` coerced ALL input values to
strings via f-string interpolation.  Binary data (audio bytes, image bytes)
became ``b'\\xff\\xfb...'`` as text -- the LLM never saw the actual content.

The fix: detect bytes / structured-dict inputs and produce a multimodal
content list instead of a flat string.
"""

import base64
from unittest.mock import MagicMock

import pytest

from kaizen.strategies.async_single_shot import (
    AsyncSingleShotStrategy,
    _classify_input_value,
    _guess_media_type,
)

# ---------------------------------------------------------------------------
# Helper: build a minimal agent mock with signature input_fields
# ---------------------------------------------------------------------------


def _make_agent(input_fields: dict, response_format=None):
    """Build a lightweight agent mock for _create_messages_from_inputs."""
    agent = MagicMock()
    agent.signature.input_fields = input_fields
    if response_format is not None:
        agent.config.response_format = response_format
    else:
        # Ensure hasattr(agent.config, "response_format") is False
        del agent.config.response_format
    return agent


# ===================================================================
# _classify_input_value unit tests
# ===================================================================


class TestClassifyInputValue:
    """Unit tests for the multimodal input classifier."""

    @pytest.mark.regression
    def test_string_returns_none(self):
        """String values are text -- classifier returns None."""
        assert _classify_input_value("hello", "Greeting", {}) is None

    @pytest.mark.regression
    def test_int_returns_none(self):
        """Numeric values are text -- classifier returns None."""
        assert _classify_input_value(42, "Count", {}) is None

    @pytest.mark.regression
    def test_bytes_jpeg_detected(self):
        """JPEG magic bytes produce an image_url content part."""
        jpeg_header = b"\xff\xd8\xff\xe0" + b"\x00" * 100
        result = _classify_input_value(jpeg_header, "Photo", {})
        assert result is not None
        assert result["type"] == "image_url"
        assert "data:image/jpeg;base64," in result["image_url"]["url"]

    @pytest.mark.regression
    def test_bytes_png_detected(self):
        """PNG magic bytes produce an image_url content part."""
        png_header = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
        result = _classify_input_value(png_header, "Screenshot", {})
        assert result is not None
        assert result["type"] == "image_url"
        assert "data:image/png;base64," in result["image_url"]["url"]

    @pytest.mark.regression
    def test_bytes_mp3_detected_as_audio(self):
        """MP3 bytes produce an input_audio content part (not image_url)."""
        # ID3 tag header
        mp3_data = b"ID3" + b"\x00" * 100
        result = _classify_input_value(mp3_data, "Audio", {})
        assert result is not None
        assert result["type"] == "input_audio"
        assert result["input_audio"]["format"] == "mpeg"

    @pytest.mark.regression
    def test_bytes_mp3_sync_word(self):
        """MP3 sync word (0xFFE0+) detected as audio."""
        mp3_data = bytes([0xFF, 0xFB]) + b"\x00" * 100
        result = _classify_input_value(mp3_data, "Audio", {})
        assert result is not None
        assert result["type"] == "input_audio"
        assert result["input_audio"]["format"] == "mpeg"

    @pytest.mark.regression
    def test_bytes_with_explicit_media_type(self):
        """field_info media_type overrides magic-byte detection."""
        raw = b"\x00\x01\x02\x03"
        result = _classify_input_value(raw, "Audio", {"media_type": "audio/wav"})
        assert result is not None
        assert result["type"] == "input_audio"
        assert result["input_audio"]["format"] == "wav"

    @pytest.mark.regression
    def test_dict_with_type_key_passthrough(self):
        """Pre-built content-part dicts are passed through unchanged."""
        part = {
            "type": "image_url",
            "image_url": {"url": "https://example.com/img.png"},
        }
        result = _classify_input_value(part, "Image", {})
        assert result is part  # exact same object

    @pytest.mark.regression
    def test_dict_without_type_key_returns_none(self):
        """Regular dicts (no 'type' key) are treated as text."""
        data = {"key": "value", "count": 42}
        assert _classify_input_value(data, "Data", {}) is None

    @pytest.mark.regression
    def test_bytearray_treated_like_bytes(self):
        """bytearray inputs are handled the same as bytes."""
        png = bytearray(b"\x89PNG\r\n\x1a\n" + b"\x00" * 50)
        result = _classify_input_value(png, "Image", {})
        assert result is not None
        assert result["type"] == "image_url"

    @pytest.mark.regression
    def test_unknown_bytes_fallback(self):
        """Unknown binary falls back to application/octet-stream image_url."""
        raw = b"\x01\x02\x03\x04\x05"
        result = _classify_input_value(raw, "Binary", {})
        assert result is not None
        assert result["type"] == "image_url"
        assert "application/octet-stream" in result["image_url"]["url"]


# ===================================================================
# _guess_media_type unit tests
# ===================================================================


class TestGuessMediaType:
    """Unit tests for magic-byte media type detection."""

    @pytest.mark.regression
    def test_wav_detection(self):
        data = b"RIFF" + b"\x00\x00\x00\x00" + b"WAVE" + b"\x00" * 20
        assert _guess_media_type(data) == "audio/wav"

    @pytest.mark.regression
    def test_webp_detection(self):
        data = b"RIFF" + b"\x00\x00\x00\x00" + b"WEBP" + b"\x00" * 20
        assert _guess_media_type(data) == "image/webp"

    @pytest.mark.regression
    def test_flac_detection(self):
        assert _guess_media_type(b"fLaC" + b"\x00" * 20) == "audio/flac"

    @pytest.mark.regression
    def test_ogg_detection(self):
        assert _guess_media_type(b"OggS" + b"\x00" * 20) == "audio/ogg"

    @pytest.mark.regression
    def test_gif_detection(self):
        assert _guess_media_type(b"GIF89a" + b"\x00" * 20) == "image/gif"


# ===================================================================
# _create_messages_from_inputs integration tests
# ===================================================================


class TestCreateMessagesFromInputs:
    """Test the full message-building pipeline."""

    @pytest.mark.regression
    def test_string_only_produces_flat_content(self):
        """When all inputs are strings, content is a flat string (no regression)."""
        strategy = AsyncSingleShotStrategy()
        agent = _make_agent(
            {
                "question": {"desc": "The question"},
                "context": {"desc": "Context"},
            }
        )
        inputs = {"question": "What is AI?", "context": "Computer science"}

        messages = strategy._create_messages_from_inputs(agent, inputs)

        assert len(messages) == 1
        assert messages[0]["role"] == "user"
        # Content must be a plain string, not a list
        assert isinstance(messages[0]["content"], str)
        assert "What is AI?" in messages[0]["content"]
        assert "Computer science" in messages[0]["content"]

    @pytest.mark.regression
    def test_bytes_input_produces_content_list(self):
        """When an input is bytes, content becomes a multimodal list."""
        strategy = AsyncSingleShotStrategy()
        agent = _make_agent(
            {
                "question": {"desc": "The question"},
                "image": {"desc": "An image"},
            }
        )
        png_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 50
        inputs = {"question": "Describe this image", "image": png_bytes}

        messages = strategy._create_messages_from_inputs(agent, inputs)

        assert len(messages) == 1
        content = messages[0]["content"]
        # Content must be a list (multimodal)
        assert isinstance(
            content, list
        ), f"Expected list for multimodal content, got {type(content).__name__}"
        # Should have a text part and an image part
        types = [part["type"] for part in content]
        assert "text" in types
        assert "image_url" in types
        # Text part should contain the question
        text_part = next(p for p in content if p["type"] == "text")
        assert "Describe this image" in text_part["text"]
        # Image part should have base64 data
        img_part = next(p for p in content if p["type"] == "image_url")
        assert "data:image/png;base64," in img_part["image_url"]["url"]

    @pytest.mark.regression
    def test_audio_bytes_produce_input_audio_part(self):
        """Audio bytes produce input_audio content parts."""
        strategy = AsyncSingleShotStrategy()
        agent = _make_agent(
            {
                "prompt": {"desc": "Instruction"},
                "audio": {"desc": "Audio clip"},
            }
        )
        mp3_bytes = b"ID3" + b"\x00" * 100
        inputs = {"prompt": "Transcribe this", "audio": mp3_bytes}

        messages = strategy._create_messages_from_inputs(agent, inputs)

        content = messages[0]["content"]
        assert isinstance(content, list)
        types = [part["type"] for part in content]
        assert "input_audio" in types
        audio_part = next(p for p in content if p["type"] == "input_audio")
        assert audio_part["input_audio"]["format"] == "mpeg"

    @pytest.mark.regression
    def test_dict_content_part_passthrough(self):
        """Pre-built content-part dicts are included in the content list."""
        strategy = AsyncSingleShotStrategy()
        agent = _make_agent(
            {
                "question": {"desc": "Question"},
                "image": {"desc": "Image part"},
            }
        )
        pre_built = {
            "type": "image_url",
            "image_url": {"url": "https://example.com/photo.jpg"},
        }
        inputs = {"question": "What do you see?", "image": pre_built}

        messages = strategy._create_messages_from_inputs(agent, inputs)

        content = messages[0]["content"]
        assert isinstance(content, list)
        # The pre-built part should appear as-is
        img_parts = [p for p in content if p["type"] == "image_url"]
        assert len(img_parts) == 1
        assert img_parts[0]["image_url"]["url"] == "https://example.com/photo.jpg"

    @pytest.mark.regression
    def test_no_signature_input_fields_with_bytes(self):
        """Multimodal detection works even without signature input_fields."""
        strategy = AsyncSingleShotStrategy()
        agent = MagicMock()
        # Remove input_fields attribute so the else branch is taken
        del agent.signature.input_fields
        del agent.config.response_format

        png_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 50
        inputs = {"text": "Describe", "img": png_bytes}

        messages = strategy._create_messages_from_inputs(agent, inputs)

        content = messages[0]["content"]
        assert isinstance(content, list)
        types = [part["type"] for part in content]
        assert "image_url" in types

    @pytest.mark.regression
    def test_bytes_not_coerced_to_string(self):
        """The core bug: bytes must NOT appear as b'...' string in content."""
        strategy = AsyncSingleShotStrategy()
        agent = _make_agent(
            {
                "audio": {"desc": "Audio data"},
            }
        )
        audio_bytes = b"\xff\xfb\x90\x00" + b"\x00" * 100
        inputs = {"audio": audio_bytes}

        messages = strategy._create_messages_from_inputs(agent, inputs)

        content = messages[0]["content"]
        # If content is a string, the bug is back
        if isinstance(content, str):
            assert (
                "b'" not in content
            ), "Binary data was coerced to string representation -- issue #410 regression"
            pytest.fail("bytes input should produce a content list, not a string")
        # Content should be a list with an audio part
        assert isinstance(content, list)

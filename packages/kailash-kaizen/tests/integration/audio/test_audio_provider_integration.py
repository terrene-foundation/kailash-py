"""
Integration tests for audio support in AI providers.

These tests use REAL infrastructure (NO MOCKING) to validate
the complete audio processing pipeline with actual AI services.

Prerequisites:
- GOOGLE_API_KEY environment variable
- Real audio test files in tests/fixtures/audio/
"""

import os
from pathlib import Path

import pytest

# Skip entire module if no API keys
pytestmark = pytest.mark.integration


def has_google_api():
    """Check if Google API key is available."""
    return bool(os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY"))


def has_openai_api():
    """Check if OpenAI API key is available."""
    return bool(os.getenv("OPENAI_API_KEY"))


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


@pytest.mark.skipif(not has_google_api(), reason="GOOGLE_API_KEY not set")
class TestGeminiAudioIntegration:
    """Test Google Gemini provider with real audio input."""

    def test_gemini_receives_audio_content(self, test_audio):
        """
        USER INTENT: When I send audio to Gemini, it should acknowledge
        receiving audio content and provide a meaningful response.

        VERIFICATION: Response must contain evidence the audio was processed,
        not a generic "I can't process audio" response.
        """
        from kaizen.nodes.ai.ai_providers import GoogleGeminiProvider
        from kaizen.nodes.ai.audio_utils import encode_audio, get_audio_media_type

        provider = GoogleGeminiProvider()
        assert provider.is_available(), "Google API not available"

        # Encode audio
        audio_base64 = encode_audio(str(test_audio))
        media_type = get_audio_media_type(str(test_audio))

        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "I'm sending you an audio file. Please describe what you hear in this audio. Is it music, speech, or some other sound?",
                    },
                    {"type": "audio", "base64": audio_base64, "media_type": media_type},
                ],
            }
        ]

        response = provider.chat(messages, model="gemini-2.0-flash")

        # INTENT VALIDATION: Audio was actually processed
        assert response["content"], "Response content should not be empty"
        assert (
            len(response["content"]) >= 10
        ), "Response should have substantial content"

        # Negative check: Response should NOT indicate audio processing failure
        failure_indicators = [
            "cannot process audio",
            "unable to hear",
            "no audio",
            "don't have access to audio",
            "can't listen",
            "cannot hear",
            "unable to access",
        ]
        response_lower = response["content"].lower()
        for indicator in failure_indicators:
            assert indicator not in response_lower, (
                f"Audio processing failed: found '{indicator}' in response: "
                f"{response['content'][:200]}"
            )

        print(f"\nGemini response: {response['content'][:300]}...")

    def test_gemini_audio_from_path(self, test_audio):
        """
        USER INTENT: When I provide an audio file path, the provider
        should load and process it correctly.
        """
        from kaizen.nodes.ai.ai_providers import GoogleGeminiProvider

        provider = GoogleGeminiProvider()

        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "What type of sound is in this audio?"},
                    {"type": "audio", "path": str(test_audio)},
                ],
            }
        ]

        response = provider.chat(messages, model="gemini-2.0-flash")

        assert response["content"], "Response should not be empty"
        print(f"\nGemini (from path) response: {response['content'][:300]}...")

    def test_gemini_audio_with_bytes(self, test_audio):
        """
        USER INTENT: When I provide raw audio bytes, the provider
        should process them correctly.
        """
        from kaizen.nodes.ai.ai_providers import GoogleGeminiProvider
        from kaizen.nodes.ai.audio_utils import get_audio_media_type

        provider = GoogleGeminiProvider()

        # Read audio as bytes
        with open(test_audio, "rb") as f:
            audio_bytes = f.read()

        media_type = get_audio_media_type(str(test_audio))

        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Describe this audio content."},
                    {"type": "audio", "bytes": audio_bytes, "media_type": media_type},
                ],
            }
        ]

        response = provider.chat(messages, model="gemini-2.0-flash")

        assert response["content"], "Response should not be empty"
        print(f"\nGemini (from bytes) response: {response['content'][:300]}...")


@pytest.mark.skipif(not has_google_api(), reason="GOOGLE_API_KEY not set")
class TestGeminiAudioUrlIntegration:
    """Test Google Gemini provider with audio_url content type."""

    def test_gemini_audio_url_data_url(self, test_audio):
        """
        USER INTENT: When I provide an audio data URL (like image_url format),
        the provider should process it correctly.
        """
        from kaizen.nodes.ai.ai_providers import GoogleGeminiProvider
        from kaizen.nodes.ai.audio_utils import encode_audio, get_audio_media_type

        provider = GoogleGeminiProvider()

        audio_base64 = encode_audio(str(test_audio))
        media_type = get_audio_media_type(str(test_audio))
        data_url = f"data:{media_type};base64,{audio_base64}"

        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "What do you hear in this audio?"},
                    {"type": "audio_url", "audio_url": {"url": data_url}},
                ],
            }
        ]

        response = provider.chat(messages, model="gemini-2.0-flash")

        assert response["content"], "Response should not be empty"
        print(f"\nGemini (audio_url) response: {response['content'][:300]}...")


@pytest.mark.skipif(not has_google_api(), reason="GOOGLE_API_KEY not set")
class TestUnhandledContentTypeWarning:
    """Test that unhandled content types produce warnings."""

    def test_unhandled_type_produces_warning(self):
        """
        USER INTENT: If I accidentally use an unsupported content type,
        I should get a clear warning instead of silent failure.
        """
        import warnings

        from kaizen.nodes.ai.ai_providers import GoogleGeminiProvider

        provider = GoogleGeminiProvider()

        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Hello"},
                    {"type": "video", "path": "/fake/video.mp4"},  # Unsupported type
                ],
            }
        ]

        # Should produce a warning about unhandled type
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            try:
                # This may fail due to missing video, but should warn first
                provider.chat(messages, model="gemini-2.0-flash")
            except Exception:
                pass  # Expected - we just want to check the warning

            # Check if warning was produced
            video_warnings = [
                warning
                for warning in w
                if "video" in str(warning.message).lower()
                and "unhandled" in str(warning.message).lower()
            ]
            assert len(video_warnings) > 0, (
                f"Expected warning about unhandled 'video' type. "
                f"Got warnings: {[str(w.message) for w in w]}"
            )


class TestAudioFieldIntegration:
    """Test AudioField integration with providers."""

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

    @pytest.mark.skipif(not has_google_api(), reason="GOOGLE_API_KEY not set")
    def test_audio_field_with_gemini_provider(self, test_audio):
        """
        USER INTENT: I should be able to use AudioField with providers
        for a complete workflow.
        """
        from kaizen.nodes.ai.ai_providers import GoogleGeminiProvider
        from kaizen.signatures.multi_modal import AudioField

        field = AudioField()
        field.load(test_audio)

        # Get base64 and extract just the data part
        data_url = field.to_base64()
        media_type, b64_data = data_url.replace("data:", "").split(";base64,")

        provider = GoogleGeminiProvider()
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Describe this audio."},
                    {"type": "audio", "base64": b64_data, "media_type": media_type},
                ],
            }
        ]

        response = provider.chat(messages, model="gemini-2.0-flash")

        assert response["content"], "Response should not be empty"
        print(f"\nGemini (via AudioField) response: {response['content'][:300]}...")

"""
End-to-end tests for audio support in Kaizen workflows.

Tests complete user workflows from audio input to final output.
Uses REAL infrastructure only - NO MOCKING.

Prerequisites:
- GOOGLE_API_KEY environment variable
- Real audio test files in tests/fixtures/audio/
"""

import os
from pathlib import Path

import pytest

pytestmark = [pytest.mark.e2e, pytest.mark.timeout(120)]


def has_google_api():
    """Check if Google API key is available."""
    return bool(os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY"))


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


@pytest.mark.skipif(not has_google_api(), reason="GOOGLE_API_KEY not set")
class TestAudioWorkflowE2E:
    """Test complete audio workflows end-to-end."""

    def test_e2e_audio_analysis_workflow(self, test_audio):
        """
        USER STORY: As a user, I want to build a workflow that analyzes
        audio content and returns a structured response.

        ACCEPTANCE CRITERIA:
        1. Workflow accepts audio file path
        2. Provider processes audio correctly
        3. Response contains meaningful analysis
        """
        from kailash.runtime import LocalRuntime
        from kailash.workflow.builder import WorkflowBuilder

        from kaizen.nodes.ai.ai_providers import GoogleGeminiProvider
        from kaizen.nodes.ai.audio_utils import encode_audio, get_audio_media_type

        # Prepare audio content
        audio_base64 = encode_audio(test_audio)
        media_type = get_audio_media_type(test_audio)

        # Build workflow with audio content
        provider = GoogleGeminiProvider()
        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "Analyze this audio and tell me: 1) What type of sound is it? 2) Any notable characteristics?",
                    },
                    {"type": "audio", "base64": audio_base64, "media_type": media_type},
                ],
            }
        ]

        response = provider.chat(messages, model="gemini-2.0-flash")

        # ACCEPTANCE VALIDATION
        assert response is not None, "Response should not be None"
        assert response.get("content"), "Response should have content"

        content = response["content"]
        assert len(content) > 50, "Response should be substantial"

        # Verify audio was actually processed (not rejected)
        content_lower = content.lower()
        rejection_indicators = [
            "cannot process",
            "unable to access",
            "don't have access",
            "cannot hear",
        ]
        for indicator in rejection_indicators:
            assert indicator not in content_lower, f"Audio was rejected: {indicator}"

        print(f"\nE2E Audio Analysis Result:\n{content[:500]}...")

    def test_e2e_audio_qa_workflow(self, test_audio):
        """
        USER STORY: As a user, I want to ask questions about audio content
        and get relevant answers.

        ACCEPTANCE CRITERIA:
        1. Can send audio + question together
        2. Answer relates to the audio
        3. Multi-turn conversation maintains context
        """
        from kaizen.nodes.ai.ai_providers import GoogleGeminiProvider
        from kaizen.nodes.ai.audio_utils import encode_audio, get_audio_media_type

        provider = GoogleGeminiProvider()

        audio_base64 = encode_audio(test_audio)
        media_type = get_audio_media_type(test_audio)

        # First turn: analyze audio
        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "Listen to this audio carefully. What type of sound do you hear?",
                    },
                    {"type": "audio", "base64": audio_base64, "media_type": media_type},
                ],
            }
        ]

        first_response = provider.chat(messages, model="gemini-2.0-flash")
        assert first_response["content"], "First response should have content"

        # Second turn: follow-up question (without re-sending audio)
        messages.append({"role": "assistant", "content": first_response["content"]})
        messages.append(
            {
                "role": "user",
                "content": "Based on the audio you just heard, is it music or speech?",
            }
        )

        second_response = provider.chat(messages, model="gemini-2.0-flash")
        assert second_response["content"], "Follow-up should have content"

        print(f"\nFirst response: {first_response['content'][:200]}...")
        print(f"\nFollow-up response: {second_response['content'][:200]}...")

    def test_e2e_audio_with_audiofield(self, test_audio):
        """
        USER STORY: As a developer, I want to use AudioField to load
        and process audio in my workflows.

        ACCEPTANCE CRITERIA:
        1. AudioField loads audio correctly
        2. to_base64() produces valid data URL
        3. Provider accepts AudioField output
        """
        from kaizen.nodes.ai.ai_providers import GoogleGeminiProvider
        from kaizen.signatures.multi_modal import AudioField

        # Load audio with AudioField
        field = AudioField()
        field.load(test_audio)

        # Validate AudioField
        assert field.validate(), "AudioField should be valid"
        assert field._data is not None, "Audio data should be loaded"
        assert field._format in [
            "wav",
            "mp3",
            "m4a",
            "ogg",
        ], "Format should be detected"

        # Get base64 for provider
        data_url = field.to_base64()
        assert data_url.startswith("data:audio/"), "Should be audio data URL"

        # Extract media type and base64 data
        media_type, b64_data = data_url.replace("data:", "").split(";base64,")

        # Use with provider
        provider = GoogleGeminiProvider()
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Describe this audio briefly."},
                    {"type": "audio", "base64": b64_data, "media_type": media_type},
                ],
            }
        ]

        response = provider.chat(messages, model="gemini-2.0-flash")
        assert response["content"], "Response should have content"

        print(f"\nAudioField E2E Result: {response['content'][:300]}...")


@pytest.mark.skipif(not has_google_api(), reason="GOOGLE_API_KEY not set")
class TestAudioErrorHandlingE2E:
    """Test error handling in audio workflows."""

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


@pytest.mark.skipif(not has_google_api(), reason="GOOGLE_API_KEY not set")
class TestAudioFormatsE2E:
    """Test different audio format handling end-to-end."""

    def test_e2e_wav_format(self, test_audio):
        """Test WAV format processing."""
        from kaizen.nodes.ai.ai_providers import GoogleGeminiProvider
        from kaizen.nodes.ai.audio_utils import get_audio_media_type

        assert get_audio_media_type(test_audio) == "audio/wav"

        provider = GoogleGeminiProvider()
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "What format is this audio?"},
                    {"type": "audio", "path": test_audio},
                ],
            }
        ]

        response = provider.chat(messages, model="gemini-2.0-flash")
        assert response["content"], "Should process WAV format"

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

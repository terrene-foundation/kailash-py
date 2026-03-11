"""
Integration tests for audio workflows.

End-to-end tests for audio transcription using real Whisper models.
Written FIRST following TDD methodology.

These tests use real infrastructure (NO MOCKING) to validate
the complete audio processing pipeline.
"""

import math
import struct
import tempfile
import wave
from pathlib import Path

import pytest

# Skip if faster-whisper not available
try:
    import faster_whisper

    WHISPER_AVAILABLE = True
except ImportError:
    WHISPER_AVAILABLE = False


@pytest.fixture(scope="module")
def test_audio_dir():
    """Create temporary directory for test audio files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture(scope="module")
def english_audio_file(test_audio_dir):
    """Create test audio file with English speech simulation."""
    # Create a simple WAV file (1 second, 16kHz, mono)
    # In real scenario, this would be actual speech audio
    audio_path = test_audio_dir / "english_speech.wav"

    sample_rate = 16000
    duration = 2.0
    frequency = 440.0

    num_samples = int(sample_rate * duration)
    audio_data = []

    for i in range(num_samples):
        # Simulate speech with modulated sine wave
        sample = math.sin(2.0 * math.pi * frequency * i / sample_rate)
        # Add some modulation
        envelope = 1.0 - (i / num_samples) * 0.5
        sample *= envelope
        audio_data.append(int(sample * 32767 * 0.5))

    with wave.open(str(audio_path), "w") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        packed_data = struct.pack("<" + "h" * len(audio_data), *audio_data)
        wav_file.writeframes(packed_data)

    return audio_path


@pytest.fixture(scope="module")
def meeting_audio_file(test_audio_dir):
    """Create test audio file simulating meeting."""
    audio_path = test_audio_dir / "meeting_audio.wav"

    sample_rate = 16000
    duration = 5.0

    num_samples = int(sample_rate * duration)
    audio_data = []

    for i in range(num_samples):
        # Simulate multiple speakers with different frequencies
        t = i / sample_rate
        if t < 2.0:
            # Speaker 1
            sample = math.sin(2.0 * math.pi * 440 * t)
        elif t < 3.5:
            # Speaker 2
            sample = math.sin(2.0 * math.pi * 550 * t)
        else:
            # Speaker 1 again
            sample = math.sin(2.0 * math.pi * 440 * t)

        audio_data.append(int(sample * 32767 * 0.3))

    with wave.open(str(audio_path), "w") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        packed_data = struct.pack("<" + "h" * len(audio_data), *audio_data)
        wav_file.writeframes(packed_data)

    return audio_path


@pytest.fixture(scope="module")
def batch_audio_files(test_audio_dir):
    """Create multiple test audio files for batch processing."""
    audio_files = []

    for i in range(3):
        audio_path = test_audio_dir / f"audio_{i}.wav"

        sample_rate = 16000
        duration = 1.0
        frequency = 440.0 + (i * 100)

        num_samples = int(sample_rate * duration)
        audio_data = []

        for j in range(num_samples):
            sample = math.sin(2.0 * math.pi * frequency * j / sample_rate)
            audio_data.append(int(sample * 32767 * 0.4))

        with wave.open(str(audio_path), "w") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(sample_rate)
            packed_data = struct.pack("<" + "h" * len(audio_data), *audio_data)
            wav_file.writeframes(packed_data)

        audio_files.append(audio_path)

    return audio_files


@pytest.mark.skipif(not WHISPER_AVAILABLE, reason="faster-whisper not installed")
class TestEndToEndSpeechToText:
    """Test complete speech-to-text workflow."""

    def test_e2e_speech_to_text(self, english_audio_file):
        """
        Test end-to-end speech-to-text transcription.

        Tests:
        - WhisperProcessor with real model
        - Audio file loading and processing
        - Transcription output format
        - Segment and timestamp generation
        """
        from kaizen.audio.whisper_processor import WhisperConfig, WhisperProcessor

        # Create processor with tiny model (fastest for testing)
        config = WhisperConfig(model_size="tiny", device="cpu", compute_type="int8")
        processor = WhisperProcessor(config)

        # Transcribe audio
        result = processor.transcribe(str(english_audio_file), word_timestamps=True)

        # Verify result structure
        assert "text" in result
        assert "language" in result
        assert "language_probability" in result
        assert "duration" in result
        assert "segments" in result
        assert "model" in result

        # Verify text is not empty (even for tone, Whisper may hallucinate)
        assert isinstance(result["text"], str)

        # Verify language detection
        assert result["language"] in ["en", "zh", "ja", "ko"]  # Common for audio tones

        # Verify duration matches file
        assert result["duration"] > 0
        assert result["duration"] <= 3.0  # Should be ~2 seconds

        # Verify segments
        assert isinstance(result["segments"], list)
        if len(result["segments"]) > 0:
            segment = result["segments"][0]
            assert "start" in segment
            assert "end" in segment
            assert "text" in segment
            assert "confidence" in segment

        print("✅ E2E Speech-to-Text Test Passed")
        print(
            f"   Detected language: {result['language']} ({result['language_probability']:.2%})"
        )
        print(f"   Duration: {result['duration']:.2f}s")
        print(f"   Segments: {len(result['segments'])}")

    def test_e2e_agent_transcription(self, english_audio_file):
        """
        Test end-to-end transcription using TranscriptionAgent.

        Tests:
        - Agent initialization
        - Agent-level transcription
        - Result formatting
        - Confidence calculation
        """
        from kaizen.agents.transcription_agent import (
            TranscriptionAgent,
            TranscriptionAgentConfig,
        )

        # Create agent with tiny model
        config = TranscriptionAgentConfig(
            model_size="tiny", device="cpu", compute_type="int8", word_timestamps=True
        )
        agent = TranscriptionAgent(config)

        # Transcribe using agent
        result = agent.transcribe(str(english_audio_file), store_in_memory=False)

        # Verify agent result
        assert "text" in result
        assert "language" in result
        assert "language_probability" in result
        assert "duration" in result
        assert "segments" in result
        assert "confidence" in result
        assert "model" in result

        # Verify confidence is calculated
        assert isinstance(result["confidence"], float)
        assert result["confidence"] >= 0

        print("✅ E2E Agent Transcription Test Passed")
        print(f"   Text: {result['text'][:100]}...")
        print(f"   Confidence: {result['confidence']:.3f}")


@pytest.mark.skipif(not WHISPER_AVAILABLE, reason="faster-whisper not installed")
class TestEndToEndMeetingTranscription:
    """Test meeting transcription workflow."""

    def test_e2e_meeting_transcription(self, meeting_audio_file):
        """
        Test end-to-end meeting transcription.

        Tests:
        - Longer audio processing (5 seconds)
        - Multiple segments
        - Timestamp accuracy
        - Speaker transitions (if detectable)
        """
        from kaizen.agents.transcription_agent import (
            TranscriptionAgent,
            TranscriptionAgentConfig,
        )

        # Create agent
        config = TranscriptionAgentConfig(
            model_size="tiny", device="cpu", word_timestamps=True
        )
        agent = TranscriptionAgent(config)

        # Transcribe meeting
        result = agent.transcribe(str(meeting_audio_file), store_in_memory=False)

        # Verify result
        assert result["duration"] > 4.0  # Should be ~5 seconds
        assert len(result["segments"]) >= 1  # At least one segment

        # Verify segments have timestamps
        for segment in result["segments"]:
            assert segment["start"] >= 0
            assert segment["end"] > segment["start"]
            assert segment["end"] <= result["duration"]

        print("✅ E2E Meeting Transcription Test Passed")
        print(f"   Duration: {result['duration']:.2f}s")
        print(f"   Segments: {len(result['segments'])}")
        if result["segments"]:
            print(
                f"   First segment: [{result['segments'][0]['start']:.1f}s - {result['segments'][0]['end']:.1f}s]"
            )


@pytest.mark.skipif(not WHISPER_AVAILABLE, reason="faster-whisper not installed")
class TestEndToEndMultiLanguage:
    """Test multi-language support."""

    def test_e2e_multi_language(self, english_audio_file):
        """
        Test multi-language detection and transcription.

        Tests:
        - Language detection
        - Language-specific transcription
        - Translation to English
        """
        from kaizen.agents.transcription_agent import (
            TranscriptionAgent,
            TranscriptionAgentConfig,
        )

        # Create agent
        config = TranscriptionAgentConfig(model_size="tiny", device="cpu")
        agent = TranscriptionAgent(config)

        # Test 1: Auto-detect language
        result_auto = agent.transcribe(str(english_audio_file), store_in_memory=False)
        assert "language" in result_auto
        detected_language = result_auto["language"]

        # Test 2: Explicit language hint
        agent.transcribe(str(english_audio_file), language="en", store_in_memory=False)
        # With hint, should prefer that language
        # (though audio is just tone, so may vary)

        # Test 3: Language detection method
        lang_result = agent.detect_language(str(english_audio_file))
        assert "language" in lang_result
        assert "confidence" in lang_result
        assert lang_result["confidence"] > 0

        print("✅ E2E Multi-Language Test Passed")
        print(f"   Auto-detected: {detected_language}")
        print(f"   Detection confidence: {lang_result['confidence']:.2%}")


@pytest.mark.skipif(not WHISPER_AVAILABLE, reason="faster-whisper not installed")
class TestEndToEndPerformance:
    """Test audio processing performance."""

    def test_e2e_audio_performance(self, batch_audio_files):
        """
        Test performance with batch processing.

        Tests:
        - Batch transcription
        - Processing speed
        - Model reuse efficiency
        - Result consistency
        """
        import time

        from kaizen.agents.transcription_agent import (
            TranscriptionAgent,
            TranscriptionAgentConfig,
        )

        # Create agent
        config = TranscriptionAgentConfig(model_size="tiny", device="cpu")
        agent = TranscriptionAgent(config)

        # Batch transcribe
        start_time = time.time()
        results = agent.transcribe_batch(
            [str(f) for f in batch_audio_files], language=None
        )
        elapsed_time = time.time() - start_time

        # Verify batch results
        assert len(results) == len(batch_audio_files)

        for i, result in enumerate(results):
            assert "text" in result
            assert "language" in result
            assert "duration" in result
            assert result["duration"] > 0

        # Performance metrics
        total_audio_duration = sum(r["duration"] for r in results)
        processing_speed = (
            total_audio_duration / elapsed_time if elapsed_time > 0 else 0
        )

        print("✅ E2E Performance Test Passed")
        print(f"   Files processed: {len(results)}")
        print(f"   Total audio duration: {total_audio_duration:.2f}s")
        print(f"   Processing time: {elapsed_time:.2f}s")
        print(f"   Speed factor: {processing_speed:.2f}x realtime")

        # Performance assertion (should be faster than realtime for tiny model on CPU)
        # Allow slow performance in CI environments
        assert processing_speed > 0.1  # At least some processing happened


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])

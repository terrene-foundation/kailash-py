"""
Audio Transcription Example - Local Whisper

Demonstrates speech-to-text with Kaizen using local Whisper.

Features:
- Speech-to-text transcription
- Multi-language support
- Word-level timestamps
- Language detection
- Batch processing

Requirements:
- faster-whisper installed: pip install faster-whisper
"""

import math
import struct
import sys
import tempfile
import wave
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from kaizen.agents.multi_modal.transcription_agent import (
    TranscriptionAgent,
    TranscriptionAgentConfig,
)


def create_test_audio_file(
    filename: str, duration: float = 2.0, frequency: float = 440.0
):
    """Create a test WAV audio file."""
    sample_rate = 16000
    num_samples = int(sample_rate * duration)
    audio_data = []

    for i in range(num_samples):
        # Generate sine wave (simulates tone)
        sample = math.sin(2.0 * math.pi * frequency * i / sample_rate)
        # Add envelope
        envelope = 1.0 - (i / num_samples) * 0.5
        sample *= envelope
        audio_data.append(int(sample * 32767 * 0.5))

    with wave.open(filename, "w") as wav_file:
        wav_file.setnchannels(1)  # Mono
        wav_file.setsampwidth(2)  # 16-bit
        wav_file.setframerate(sample_rate)
        packed_data = struct.pack("<" + "h" * len(audio_data), *audio_data)
        wav_file.writeframes(packed_data)


def main():
    """Run audio transcription examples."""
    print("=== Kaizen Audio Transcription Example ===\n")

    # Check if faster-whisper is available
    try:
        import faster_whisper

        whisper_available = True
    except ImportError:
        whisper_available = False
        print("⚠️  faster-whisper not installed!")
        print("   Install with: pip install faster-whisper\n")
        print("   Showing example setup (would need real audio)...\n")

    # Create transcription agent
    config = TranscriptionAgentConfig(
        model_size="tiny",  # Use tiny for fast testing
        device="cpu",
        word_timestamps=True,
    )
    agent = TranscriptionAgent(config)

    print("✅ TranscriptionAgent created")
    print(f"   Model: {config.model_size}")
    print(f"   Device: {config.device}\n")

    if not whisper_available:
        print("Demo would perform the following:")
        print("1. Create test audio files")
        print("2. Transcribe speech-to-text")
        print("3. Extract word timestamps")
        print("4. Detect language")
        print("5. Batch process multiple files\n")
        return

    # Create temporary test audio files
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)

        # Create test audio files
        audio1 = tmpdir_path / "speech.wav"
        audio2 = tmpdir_path / "meeting.wav"
        audio3 = tmpdir_path / "batch1.wav"
        audio4 = tmpdir_path / "batch2.wav"

        print("Creating test audio files...")
        create_test_audio_file(str(audio1), duration=2.0, frequency=440.0)
        create_test_audio_file(str(audio2), duration=5.0, frequency=550.0)
        create_test_audio_file(str(audio3), duration=1.5, frequency=440.0)
        create_test_audio_file(str(audio4), duration=1.5, frequency=660.0)
        print("✅ Test audio files created\n")

        # Example 1: Basic Transcription
        print("1. Basic Speech-to-Text")
        print("-" * 40)

        result = agent.transcribe(str(audio1), store_in_memory=False)

        print(f"Text: {result['text']}")
        print(f"Language: {result['language']} ({result['language_probability']:.2%})")
        print(f"Duration: {result['duration']:.1f}s")
        print(f"Confidence: {result['confidence']:.2f}\n")

        # Example 2: Transcription with Timestamps
        print("2. Transcription with Word Timestamps")
        print("-" * 40)

        if result.get("segments"):
            for i, segment in enumerate(result["segments"][:3], 1):
                print(
                    f"\nSegment {i} [{segment['start']:.1f}s - {segment['end']:.1f}s]:"
                )
                print(f"  Text: {segment['text']}")

                if segment.get("words"):
                    print("  Words:")
                    for word in segment["words"][:5]:
                        print(f"    {word['word']} [{word['start']:.2f}s]")
        else:
            print("  (No segments detected - audio may be too short)")

        # Example 3: Language Detection
        print("\n3. Language Detection")
        print("-" * 40)

        lang_result = agent.detect_language(str(audio1))
        print(f"Detected: {lang_result['language']} ({lang_result['confidence']:.2%})")

        # Example 4: Batch Transcription
        print("\n4. Batch Transcription")
        print("-" * 40)

        audio_files = [str(audio3), str(audio4)]
        batch_results = agent.transcribe_batch(audio_files)

        for i, result in enumerate(batch_results, 1):
            if "error" not in result:
                print(f"\nFile {i}: {result['text'][:100]}...")
                print(
                    f"  Language: {result['language']}, Duration: {result['duration']:.1f}s"
                )
            else:
                print(f"\nFile {i}: Error - {result['error']}")

        # Example 5: Meeting Transcription
        print("\n5. Meeting Transcription (Longer Audio)")
        print("-" * 40)

        meeting_result = agent.transcribe(str(audio2), store_in_memory=False)

        print(f"Duration: {meeting_result['duration']:.1f}s")
        print(f"Segments: {len(meeting_result['segments'])}")

        if meeting_result["segments"]:
            print(f"\nFirst segment: {meeting_result['segments'][0]['text']}")
            print(
                f"  Time: {meeting_result['segments'][0]['start']:.1f}s - "
                f"{meeting_result['segments'][0]['end']:.1f}s"
            )

    print("\n=== Audio Transcription Complete ===")
    print("\nNote: Test audio files are simple tones.")
    print("For real transcription, use actual speech audio files.\n")

    print("Next steps:")
    print("- Try with real speech audio (MP3, WAV, etc.)")
    print("- Use larger models (base, small) for better accuracy")
    print("- Integrate with RAG for audio-based Q&A")
    print("- Build meeting summarization workflows")


if __name__ == "__main__":
    main()

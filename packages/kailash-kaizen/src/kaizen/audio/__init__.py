"""
Kaizen Audio Processing Module.

Provides audio transcription capabilities using local Whisper models.

Key Components:
- WhisperProcessor: Local Whisper integration for transcription
- WhisperConfig: Configuration for Whisper models
- transcribe_audio: Convenience function for quick transcription

Example:
    from kaizen.audio import WhisperProcessor, WhisperConfig

    config = WhisperConfig(model_size="base")
    processor = WhisperProcessor(config)
    result = processor.transcribe("audio.mp3")
    print(result['text'])
"""

from .whisper_processor import WhisperConfig, WhisperProcessor, transcribe_audio

__all__ = ["WhisperProcessor", "WhisperConfig", "transcribe_audio"]

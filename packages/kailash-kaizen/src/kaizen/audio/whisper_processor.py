"""Local Whisper processor for audio transcription."""

import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Union


@dataclass
class WhisperConfig:
    """Configuration for Whisper processor."""

    model_size: str = "base"  # tiny, base, small, medium, large
    device: str = "cpu"  # cpu or cuda
    compute_type: str = "int8"  # int8, float16, float32
    language: Optional[str] = None  # None for auto-detect
    task: str = "transcribe"  # transcribe or translate
    beam_size: int = 5
    best_of: int = 5
    temperature: float = 0.0


class WhisperProcessor:
    """
    Local Whisper processor for audio transcription.

    Uses faster-whisper for efficient CPU/GPU transcription.

    Features:
    - Automatic model download
    - Multiple model sizes (tiny to large)
    - Word-level timestamps
    - Language detection
    - Translation to English
    - Batch processing

    Example:
        processor = WhisperProcessor(WhisperConfig(model_size="base"))
        result = processor.transcribe("audio.mp3")
        print(result['text'])
    """

    MODEL_SIZES = ["tiny", "base", "small", "medium", "large", "large-v2", "large-v3"]

    def __init__(self, config: WhisperConfig = None):
        """Initialize Whisper processor."""
        self.config = config or WhisperConfig()

        # Validate model size
        if self.config.model_size not in self.MODEL_SIZES:
            raise ValueError(
                f"Invalid model size: {self.config.model_size}. "
                f"Valid: {self.MODEL_SIZES}"
            )

        # Initialize model (lazy loading)
        self.model = None
        self._ensure_whisper_available()

    def _ensure_whisper_available(self):
        """Ensure faster-whisper is installed."""
        try:
            import faster_whisper

            self._whisper_available = True
        except ImportError:
            warnings.warn(
                "faster-whisper not installed. Install with: "
                "pip install faster-whisper"
            )
            self._whisper_available = False

    def _load_model(self):
        """Load Whisper model (lazy loading)."""
        if self.model is not None:
            return

        if not self._whisper_available:
            raise RuntimeError(
                "faster-whisper not available. Install with: "
                "pip install faster-whisper"
            )

        try:
            from faster_whisper import WhisperModel

            print(f"Loading Whisper model: {self.config.model_size}")
            print(f"Device: {self.config.device}, Compute: {self.config.compute_type}")

            self.model = WhisperModel(
                self.config.model_size,
                device=self.config.device,
                compute_type=self.config.compute_type,
            )

            print(f"✅ Whisper model loaded: {self.config.model_size}")

        except Exception as e:
            raise RuntimeError(f"Failed to load Whisper model: {e}")

    def transcribe(
        self,
        audio_path: Union[str, Path],
        language: Optional[str] = None,
        task: Optional[str] = None,
        word_timestamps: bool = True,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Transcribe audio file.

        Args:
            audio_path: Path to audio file
            language: Language code (None for auto-detect)
            task: 'transcribe' or 'translate'
            word_timestamps: Include word-level timestamps
            **kwargs: Additional transcription parameters

        Returns:
            Dict with 'text', 'language', 'segments', 'duration'
        """
        # Ensure model is loaded
        self._load_model()

        # Validate audio file exists
        audio_path = Path(audio_path)
        if not audio_path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        # Transcribe
        try:
            segments, info = self.model.transcribe(
                str(audio_path),
                language=language or self.config.language,
                task=task or self.config.task,
                beam_size=kwargs.get("beam_size", self.config.beam_size),
                best_of=kwargs.get("best_of", self.config.best_of),
                temperature=kwargs.get("temperature", self.config.temperature),
                word_timestamps=word_timestamps,
            )

            # Convert segments to list
            segment_list = []
            full_text = []

            for segment in segments:
                segment_dict = {
                    "start": segment.start,
                    "end": segment.end,
                    "text": segment.text.strip(),
                    "confidence": segment.avg_logprob,
                }

                # Add word timestamps if available
                if word_timestamps and hasattr(segment, "words"):
                    segment_dict["words"] = [
                        {
                            "word": word.word,
                            "start": word.start,
                            "end": word.end,
                            "confidence": word.probability,
                        }
                        for word in segment.words
                    ]

                segment_list.append(segment_dict)
                full_text.append(segment.text.strip())

            return {
                "text": " ".join(full_text),
                "language": info.language,
                "language_probability": info.language_probability,
                "duration": info.duration,
                "segments": segment_list,
                "model": self.config.model_size,
            }

        except Exception as e:
            raise RuntimeError(f"Transcription failed: {e}")

    def transcribe_batch(
        self, audio_paths: List[Union[str, Path]], **kwargs
    ) -> List[Dict[str, Any]]:
        """
        Transcribe multiple audio files.

        Args:
            audio_paths: List of audio file paths
            **kwargs: Transcription parameters

        Returns:
            List of transcription results
        """
        results = []

        for audio_path in audio_paths:
            try:
                result = self.transcribe(audio_path, **kwargs)
                results.append(result)
            except Exception as e:
                results.append({"error": str(e), "file": str(audio_path)})

        return results

    def detect_language(self, audio_path: Union[str, Path]) -> Dict[str, Any]:
        """
        Detect language of audio file.

        Args:
            audio_path: Path to audio file

        Returns:
            Dict with 'language', 'confidence'
        """
        # Ensure model is loaded
        self._load_model()

        # Detect language by transcribing first 30 seconds
        try:
            segments, info = self.model.transcribe(
                str(audio_path),
                language=None,  # Auto-detect
                task="transcribe",
                beam_size=1,  # Fast detection
                best_of=1,
            )

            return {
                "language": info.language,
                "confidence": info.language_probability,
                "duration": info.duration,
            }

        except Exception as e:
            raise RuntimeError(f"Language detection failed: {e}")


# Convenience function for quick transcription
def transcribe_audio(
    audio_path: Union[str, Path],
    model_size: str = "base",
    language: Optional[str] = None,
    **kwargs,
) -> str:
    """
    Quick transcription of audio file.

    Args:
        audio_path: Path to audio file
        model_size: Whisper model size
        language: Language code (None for auto-detect)
        **kwargs: Additional parameters

    Returns:
        Transcribed text
    """
    config = WhisperConfig(model_size=model_size, language=language)
    processor = WhisperProcessor(config)
    result = processor.transcribe(audio_path, **kwargs)
    return result["text"]

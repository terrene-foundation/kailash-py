"""Audio utilities for AI providers - lazy loaded to avoid overhead.

This module provides utilities for processing audio content in AI provider
integrations, following the same pattern as vision_utils.py.

Supported audio formats:
- MP3 (audio/mpeg)
- WAV (audio/wav)
- M4A (audio/mp4)
- AAC (audio/aac)
- OGG (audio/ogg)
- OPUS (audio/opus)
- FLAC (audio/flac)
- WebM (audio/webm)
- AIFF (audio/aiff)
"""

from pathlib import Path
from typing import Optional, Tuple


def encode_audio(audio_path: str) -> str:
    """
    Encode audio file to base64 string.

    Args:
        audio_path: Path to the audio file

    Returns:
        Base64 encoded string of the audio

    Raises:
        FileNotFoundError: If audio file doesn't exist
        IOError: If unable to read the audio file

    Example:
        >>> base64_audio = encode_audio("/path/to/audio.mp3")
        >>> # Use in provider message content
        >>> content = {"type": "audio", "base64": base64_audio, "media_type": "audio/mpeg"}
    """
    # Lazy import to avoid overhead when not using audio
    import base64

    audio_path = Path(audio_path).resolve()
    if not audio_path.exists():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    try:
        with open(audio_path, "rb") as audio_file:
            return base64.b64encode(audio_file.read()).decode("utf-8")
    except Exception as e:
        raise IOError(f"Failed to read audio file: {e}")


def get_audio_media_type(audio_path: str) -> str:
    """
    Get media type from file extension.

    Args:
        audio_path: Path to the audio file

    Returns:
        Media type string (e.g., "audio/mpeg" for MP3)

    Example:
        >>> get_audio_media_type("/path/to/audio.mp3")
        'audio/mpeg'
        >>> get_audio_media_type("/path/to/audio.wav")
        'audio/wav'
    """
    ext = Path(audio_path).suffix.lower()
    media_types = {
        ".mp3": "audio/mpeg",
        ".wav": "audio/wav",
        ".m4a": "audio/mp4",
        ".aac": "audio/aac",
        ".ogg": "audio/ogg",
        ".opus": "audio/opus",
        ".flac": "audio/flac",
        ".webm": "audio/webm",
        ".wma": "audio/x-ms-wma",
        ".aiff": "audio/aiff",
        ".aif": "audio/aiff",
    }
    return media_types.get(ext, "audio/mpeg")


def validate_audio_size(
    audio_path: str, max_size_mb: float = 25.0
) -> Tuple[bool, Optional[str]]:
    """
    Validate audio file size.

    Args:
        audio_path: Path to the audio file
        max_size_mb: Maximum allowed size in megabytes (default 25MB for most providers)

    Returns:
        Tuple of (is_valid, error_message)
        - is_valid: True if file size is within limit
        - error_message: None if valid, error description if invalid

    Example:
        >>> is_valid, error = validate_audio_size("/path/to/audio.mp3")
        >>> if not is_valid:
        ...     print(f"Audio too large: {error}")
    """
    import os

    try:
        size_bytes = os.path.getsize(audio_path)
        size_mb = size_bytes / (1024 * 1024)

        if size_mb > max_size_mb:
            return (
                False,
                f"Audio size {size_mb:.1f}MB exceeds maximum {max_size_mb:.1f}MB",
            )

        return True, None
    except FileNotFoundError:
        return False, f"Audio file not found: {audio_path}"
    except Exception as e:
        return False, f"Failed to check audio size: {e}"


def get_audio_duration(audio_path: str) -> Optional[float]:
    """
    Get audio duration in seconds using available libraries.

    Attempts to get duration using:
    1. pydub (if installed)
    2. mutagen (if installed)
    3. Fallback estimate based on file size

    Args:
        audio_path: Path to the audio file

    Returns:
        Duration in seconds, or None if unable to determine

    Note:
        For accurate duration, install pydub or mutagen:
        pip install pydub
        pip install mutagen
    """
    audio_path = Path(audio_path)
    if not audio_path.exists():
        return None

    # Try pydub first (most accurate)
    try:
        from pydub import AudioSegment

        audio = AudioSegment.from_file(str(audio_path))
        return len(audio) / 1000.0  # Convert ms to seconds
    except ImportError:
        pass
    except Exception:
        pass

    # Try mutagen (lightweight alternative)
    try:
        import mutagen

        audio = mutagen.File(str(audio_path))
        if (
            audio is not None
            and hasattr(audio, "info")
            and hasattr(audio.info, "length")
        ):
            return audio.info.length
    except ImportError:
        pass
    except Exception:
        pass

    # Fallback: estimate based on file size and format
    # This is a rough estimate assuming common bitrates
    try:
        import os

        size_bytes = os.path.getsize(audio_path)
        ext = audio_path.suffix.lower()

        # Common bitrate estimates (bytes per second)
        bitrate_estimates = {
            ".mp3": 16000,  # ~128 kbps
            ".wav": 176400,  # 44.1kHz 16-bit stereo
            ".m4a": 20000,  # ~160 kbps AAC
            ".ogg": 16000,  # ~128 kbps
            ".flac": 88200,  # ~706 kbps (CD quality)
        }
        bytes_per_second = bitrate_estimates.get(ext, 16000)
        return size_bytes / bytes_per_second
    except Exception:
        return None

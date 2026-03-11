"""
Multi-Modal Adapter - Provider abstraction for multi-modal processing.

Provides unified interface for:
- Ollama (local, free) - PRIMARY
- OpenAI (cloud, paid) - VALIDATION ONLY

Following Phase 4 requirements: Provider abstraction, auto-selection, cost tracking.
"""

import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, Optional, Union

from kaizen.signatures.multi_modal import AudioField, ImageField


class MultiModalAdapter(ABC):
    """Abstract base class for multi-modal processing adapters."""

    @abstractmethod
    def is_available(self) -> bool:
        """Check if this adapter is available."""
        pass

    @abstractmethod
    def supports_vision(self) -> bool:
        """Check if adapter supports vision processing."""
        pass

    @abstractmethod
    def supports_audio(self) -> bool:
        """Check if adapter supports audio processing."""
        pass

    @abstractmethod
    def process_multi_modal(
        self,
        image: Optional[Union[str, Path, ImageField]] = None,
        audio: Optional[Union[str, Path, AudioField]] = None,
        text: Optional[str] = None,
        prompt: Optional[str] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Process multi-modal inputs.

        Args:
            image: Image input (file path, URL, or ImageField)
            audio: Audio input (file path or AudioField)
            text: Text input
            prompt: Processing prompt/question
            **kwargs: Additional provider-specific parameters

        Returns:
            Dict containing processing results
        """
        pass

    @abstractmethod
    def estimate_cost(
        self,
        modality: str,
        input_size: Optional[int] = None,
        duration: Optional[int] = None,
        **kwargs,
    ) -> float:
        """
        Estimate cost for processing.

        Args:
            modality: 'vision', 'audio', or 'mixed'
            input_size: Input size in bytes (for vision)
            duration: Duration in seconds (for audio)

        Returns:
            Estimated cost in USD
        """
        pass


class OllamaMultiModalAdapter(MultiModalAdapter):
    """
    Ollama multi-modal adapter (PRIMARY).

    - Vision: llava:13b, bakllava
    - Audio: Local Whisper integration
    - Cost: $0 (all local)
    """

    def __init__(
        self,
        model: str = "llava:13b",
        whisper_model: str = "base",
        auto_download: bool = True,
    ):
        """
        Initialize Ollama adapter.

        Args:
            model: Ollama vision model (llava:13b, bakllava)
            whisper_model: Whisper model size (tiny, base, small, medium)
            auto_download: Auto-download models if missing
        """
        self.model = model
        self.whisper_model = whisper_model
        self.auto_download = auto_download

        # Lazy imports
        self._ollama_provider = None
        self._ollama_vision_provider = None
        self._whisper_processor = None

    def is_available(self) -> bool:
        """Check if Ollama is available."""
        try:
            from kaizen.providers import OLLAMA_AVAILABLE

            return OLLAMA_AVAILABLE
        except ImportError:
            return False

    def supports_vision(self) -> bool:
        """Ollama supports vision via llava models."""
        return self.is_available()

    def supports_audio(self) -> bool:
        """Ollama supports audio via Whisper integration."""
        return True  # Local Whisper always available

    def _ensure_model_ready(self):
        """Ensure Ollama model is downloaded and ready."""
        if not self.is_available():
            return

        from kaizen.providers.ollama_model_manager import OllamaModelManager

        manager = OllamaModelManager()
        manager.ensure_model_available(self.model, auto_download=self.auto_download)

    def _get_ollama_vision_provider(self):
        """Get Ollama vision provider (lazy initialization)."""
        if self._ollama_vision_provider is None:
            from kaizen.providers.ollama_vision_provider import (
                OllamaVisionConfig,
                OllamaVisionProvider,
            )

            # Create config matching Phase 2 API
            config = OllamaVisionConfig(model=self.model)
            self._ollama_vision_provider = OllamaVisionProvider(config=config)
        return self._ollama_vision_provider

    def _get_whisper_processor(self):
        """Get Whisper processor (lazy initialization)."""
        if self._whisper_processor is None:
            from kaizen.audio.whisper_processor import WhisperProcessor

            self._whisper_processor = WhisperProcessor(model_size=self.whisper_model)
        return self._whisper_processor

    def _call_ollama_vision(
        self, image: Union[str, Path, ImageField], prompt: str, **kwargs
    ) -> Dict[str, Any]:
        """Call Ollama vision API."""
        provider = self._get_ollama_vision_provider()

        # Convert ImageField to path if needed
        if isinstance(image, ImageField):
            image_path = (
                image.data if isinstance(image.data, (str, Path)) else image.source
            )
        else:
            image_path = image

        return provider.analyze_image(image=image_path, prompt=prompt, **kwargs)

    def _call_whisper(
        self, audio: Union[str, Path, AudioField], **kwargs
    ) -> Dict[str, Any]:
        """Call local Whisper for transcription."""
        processor = self._get_whisper_processor()

        # Convert AudioField to path if needed
        if isinstance(audio, AudioField):
            audio_path = (
                audio.data if isinstance(audio.data, (str, Path)) else audio.source
            )
        else:
            audio_path = audio

        return processor.transcribe(audio_path, **kwargs)

    def _combine_results(
        self,
        vision_result: Optional[Dict[str, Any]] = None,
        audio_result: Optional[Dict[str, Any]] = None,
        text: Optional[str] = None,
        prompt: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Combine multi-modal results."""
        combined = {}

        if vision_result:
            combined["visual"] = vision_result
        if audio_result:
            combined["audio"] = audio_result
        if text:
            combined["text"] = text

        # If prompt provided, synthesize answer
        if prompt and (vision_result or audio_result or text):
            # Use Ollama to synthesize combined answer
            provider = self._get_ollama_vision_provider()
            synthesis_prompt = f"{prompt}\n\nContext:\n"
            if vision_result:
                synthesis_prompt += f"Visual: {vision_result}\n"
            if audio_result:
                synthesis_prompt += f"Audio: {audio_result}\n"
            if text:
                synthesis_prompt += f"Text: {text}\n"

            synthesis = provider._call_ollama_text(synthesis_prompt)
            combined["combined"] = synthesis

        return combined

    def process_multi_modal(
        self,
        image: Optional[Union[str, Path, ImageField]] = None,
        audio: Optional[Union[str, Path, AudioField]] = None,
        text: Optional[str] = None,
        prompt: Optional[str] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """Process multi-modal inputs with Ollama."""
        if not self.is_available():
            raise RuntimeError("Ollama not available")

        vision_result = None
        audio_result = None

        # Process image if provided
        if image is not None:
            if not self.supports_vision():
                raise ValueError("Ollama vision not available")
            vision_result = self._call_ollama_vision(
                image, prompt or "Describe this image", **kwargs
            )

        # Process audio if provided
        if audio is not None:
            audio_result = self._call_whisper(audio, **kwargs)

        # Single modality - return directly
        if sum([image is not None, audio is not None, text is not None]) == 1:
            if image is not None:
                return vision_result
            elif audio is not None:
                return audio_result
            else:
                # Text-only processing
                provider = self._get_ollama_vision_provider()
                return provider._call_ollama_text(prompt or text)

        # Multi-modality - combine results
        return self._combine_results(vision_result, audio_result, text, prompt)

    def estimate_cost(
        self,
        modality: str,
        input_size: Optional[int] = None,
        duration: Optional[int] = None,
        **kwargs,
    ) -> float:
        """Ollama is always free ($0)."""
        return 0.0


class OpenAIMultiModalAdapter(MultiModalAdapter):
    """
    OpenAI multi-modal adapter (VALIDATION ONLY).

    - Vision: GPT-4 Vision
    - Audio: Whisper API
    - Cost: Pay per use
    """

    # OpenAI pricing (as of 2025)
    VISION_COST_PER_IMAGE = 0.01  # ~$0.01 per image
    AUDIO_COST_PER_MINUTE = 0.006  # $0.006 per minute

    def __init__(self, api_key: Optional[str] = None, warn_before_call: bool = True):
        """
        Initialize OpenAI adapter.

        Args:
            api_key: OpenAI API key (or from env)
            warn_before_call: Warn before making paid API calls
        """
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.warn_before_call = warn_before_call

        # Usage tracking
        self._usage_stats = {
            "total_calls": 0,
            "total_cost": 0.0,
            "vision_calls": 0,
            "audio_calls": 0,
        }

    def is_available(self) -> bool:
        """Check if OpenAI API key is available."""
        return self.api_key is not None and len(self.api_key) > 0

    def supports_vision(self) -> bool:
        """OpenAI supports vision via GPT-4V."""
        return self.is_available()

    def supports_audio(self) -> bool:
        """OpenAI supports audio via Whisper API."""
        return self.is_available()

    def _call_openai_vision(
        self, image: Union[str, Path, ImageField], prompt: str, **kwargs
    ) -> Dict[str, Any]:
        """Call OpenAI vision API."""
        import openai

        # Prepare image
        if isinstance(image, ImageField):
            image_data = image.to_base64()
        else:
            # Load and encode image
            import base64
            from io import BytesIO

            from PIL import Image

            img = Image.open(image)
            buffer = BytesIO()
            img.save(buffer, format="JPEG")
            image_data = base64.b64encode(buffer.getvalue()).decode()

        # Call GPT-4o (latest vision model, replaces gpt-4-vision-preview)
        client = openai.OpenAI(api_key=self.api_key)
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{image_data}"
                            },
                        },
                    ],
                }
            ],
            **kwargs,
        )

        # Track usage
        self._usage_stats["vision_calls"] += 1
        self._usage_stats["total_calls"] += 1
        self._usage_stats["total_cost"] += self.VISION_COST_PER_IMAGE

        return {"description": response.choices[0].message.content}

    def _call_openai_whisper(
        self, audio: Union[str, Path, AudioField], **kwargs
    ) -> Dict[str, Any]:
        """Call OpenAI Whisper API."""
        import openai

        # Prepare audio
        if isinstance(audio, AudioField):
            audio_path = (
                audio.data if isinstance(audio.data, (str, Path)) else audio.source
            )
        else:
            audio_path = audio

        # Call Whisper
        client = openai.OpenAI(api_key=self.api_key)
        with open(audio_path, "rb") as audio_file:
            response = client.audio.transcriptions.create(
                model="whisper-1", file=audio_file, **kwargs
            )

        # Estimate duration for cost
        import wave

        with wave.open(str(audio_path), "rb") as wav:
            frames = wav.getnframes()
            rate = wav.getframerate()
            duration = frames / float(rate)

        cost = (duration / 60.0) * self.AUDIO_COST_PER_MINUTE

        # Track usage
        self._usage_stats["audio_calls"] += 1
        self._usage_stats["total_calls"] += 1
        self._usage_stats["total_cost"] += cost

        return {"text": response.text}

    def process_multi_modal(
        self,
        image: Optional[Union[str, Path, ImageField]] = None,
        audio: Optional[Union[str, Path, AudioField]] = None,
        text: Optional[str] = None,
        prompt: Optional[str] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """Process multi-modal inputs with OpenAI."""
        if not self.is_available():
            raise RuntimeError("OpenAI API key not available")

        results = {}

        # Process image
        if image is not None:
            if self.warn_before_call:
                print(
                    f"⚠️  OpenAI API call: ~${self.VISION_COST_PER_IMAGE:.3f} for vision"
                )
            results.update(
                self._call_openai_vision(image, prompt or "Describe", **kwargs)
            )

        # Process audio
        if audio is not None:
            if self.warn_before_call:
                print(
                    f"⚠️  OpenAI API call: ~${self.AUDIO_COST_PER_MINUTE:.3f}/min for audio"
                )
            results.update(self._call_openai_whisper(audio, **kwargs))

        # Process text-only
        if text and not image and not audio:
            # Use GPT-4 for text
            import openai

            client = openai.OpenAI(api_key=self.api_key)
            response = client.chat.completions.create(
                model="gpt-4",
                messages=[{"role": "user", "content": prompt or text}],
                **kwargs,
            )
            results["response"] = response.choices[0].message.content

        return results

    def estimate_cost(
        self,
        modality: str,
        input_size: Optional[int] = None,
        duration: Optional[int] = None,
        **kwargs,
    ) -> float:
        """Estimate OpenAI API cost."""
        if modality == "vision":
            return self.VISION_COST_PER_IMAGE
        elif modality == "audio":
            minutes = (duration or 60) / 60.0
            return minutes * self.AUDIO_COST_PER_MINUTE
        elif modality == "mixed":
            vision_cost = self.VISION_COST_PER_IMAGE if input_size else 0
            audio_cost = (
                ((duration or 60) / 60.0) * self.AUDIO_COST_PER_MINUTE
                if duration
                else 0
            )
            return vision_cost + audio_cost
        return 0.0

    def get_usage_stats(self) -> Dict[str, Any]:
        """Get usage statistics."""
        return self._usage_stats.copy()


# Adapter factory and caching
_adapter_cache: Dict[str, MultiModalAdapter] = {}


def get_multi_modal_adapter(
    provider: Optional[str] = None, prefer_local: bool = True, **kwargs
) -> MultiModalAdapter:
    """
    Get multi-modal adapter with auto-selection.

    Args:
        provider: Explicit provider ('ollama', 'openai')
        prefer_local: Prefer local (Ollama) over cloud (OpenAI)
        **kwargs: Provider-specific arguments

    Returns:
        MultiModalAdapter instance

    Raises:
        ValueError: If no adapter available
    """
    # Check cache
    cache_key = f"{provider}:{prefer_local}"
    if cache_key in _adapter_cache:
        return _adapter_cache[cache_key]

    # Explicit provider selection
    if provider == "ollama":
        from kaizen.providers import OLLAMA_AVAILABLE

        if not OLLAMA_AVAILABLE:
            raise ValueError("Ollama not available")
        adapter = OllamaMultiModalAdapter(**kwargs)
        _adapter_cache[cache_key] = adapter
        return adapter

    if provider == "openai":
        api_key = kwargs.pop("api_key", None) or os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OpenAI API key not available")
        adapter = OpenAIMultiModalAdapter(api_key=api_key, **kwargs)
        _adapter_cache[cache_key] = adapter
        return adapter

    # Auto-selection based on preference
    if prefer_local:
        # Try Ollama first
        try:
            from kaizen.providers import OLLAMA_AVAILABLE

            if OLLAMA_AVAILABLE:
                adapter = OllamaMultiModalAdapter(**kwargs)
                _adapter_cache[cache_key] = adapter
                return adapter
        except ImportError:
            pass

        # Fallback to OpenAI
        api_key = kwargs.pop("api_key", None) or os.getenv("OPENAI_API_KEY")
        if api_key:
            adapter = OpenAIMultiModalAdapter(api_key=api_key, **kwargs)
            _adapter_cache[cache_key] = adapter
            return adapter
    else:
        # Try OpenAI first
        api_key = kwargs.pop("api_key", None) or os.getenv("OPENAI_API_KEY")
        if api_key:
            adapter = OpenAIMultiModalAdapter(api_key=api_key, **kwargs)
            _adapter_cache[cache_key] = adapter
            return adapter

        # Fallback to Ollama
        try:
            from kaizen.providers import OLLAMA_AVAILABLE

            if OLLAMA_AVAILABLE:
                adapter = OllamaMultiModalAdapter(**kwargs)
                _adapter_cache[cache_key] = adapter
                return adapter
        except ImportError:
            pass

    raise ValueError(
        "No multi-modal adapter available. Install Ollama or provide OpenAI API key."
    )

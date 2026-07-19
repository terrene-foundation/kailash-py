"""Ollama provider integration for Kaizen multi-modal processing."""

from dataclasses import dataclass
from typing import Any, Dict, Iterator, Optional

from kailash.utils.url_credentials import mask_error_text


@dataclass
class OllamaConfig:
    """Configuration for Ollama provider."""

    model: str = "llama2"
    base_url: str = "http://localhost:11434"
    timeout: int = 120  # seconds
    temperature: float = 0.7
    top_p: float = 0.9
    stream: bool = False
    # #1803: explicit opt-out from the ``governance_required`` posture gate
    # enforced at construction (below) — this class makes real network
    # egress (``ollama.list()``) unconditionally in ``__init__``, so the
    # gate cannot defer to an egress method. Inherited by
    # ``OllamaVisionConfig`` (dataclass subclass). Default False.
    ungoverned: bool = False


class OllamaProvider:
    """
    Ollama LLM provider for Kaizen.

    Integrates with local Ollama models for:
    - Text generation
    - Vision processing (llava, bakllava)
    - Streaming responses
    """

    def __init__(self, config: Optional[OllamaConfig] = None):
        """Initialize Ollama provider."""
        self.config = config or OllamaConfig()
        # #1803 governance_required posture: this class is directly
        # standalone-constructible (``kaizen.providers.LegacyOllamaProvider``)
        # AND the ``OllamaMultiModalAdapter`` / ``OllamaVisionProvider``
        # (top-level) path. ``_check_ollama_available`` below makes a real
        # ``ollama.list()`` call unconditionally, so the gate MUST fire
        # before that call, not deferred to an egress method. No mock
        # concept exists for this provider (is_mock=False always); locality
        # (base_url defaults to localhost) is NOT a governance exemption —
        # parity with the four-axis LlmClient path, which gates Ollama
        # deployments too.
        from kaizen.llm.governance_gate import enforce_governance_posture

        enforce_governance_posture(
            is_mock=False,
            ungoverned=self.config.ungoverned,
            surface="OllamaProvider",
        )
        self._check_ollama_available()

    def _check_ollama_available(self):
        """Check if Ollama is available and running."""
        try:
            import ollama

            # Test connection
            ollama.list()
        except Exception as e:
            raise RuntimeError(
                "Ollama not available. Please install and start Ollama: "
                f"{mask_error_text(str(e))}\n"
                "Install: https://ollama.ai/download"
            )

    def generate(
        self, prompt: str, system: Optional[str] = None, **kwargs
    ) -> Dict[str, Any]:
        """
        Generate text completion.

        Args:
            prompt: User prompt
            system: Optional system prompt
            **kwargs: Additional generation parameters

        Returns:
            Dict with 'response' key containing generated text
        """
        try:
            import ollama

            # Prepare messages
            messages = []
            if system:
                messages.append({"role": "system", "content": system})
            messages.append({"role": "user", "content": prompt})

            # Generate response
            response = ollama.chat(
                model=self.config.model,
                messages=messages,
                stream=False,
                options={
                    "temperature": kwargs.get("temperature", self.config.temperature),
                    "top_p": kwargs.get("top_p", self.config.top_p),
                },
            )

            return {
                "response": response["message"]["content"],
                "model": response["model"],
                "done": response.get("done", True),
            }

        except Exception as e:
            raise RuntimeError(f"Ollama generation failed: {mask_error_text(str(e))}")

    def generate_stream(
        self, prompt: str, system: Optional[str] = None, **kwargs
    ) -> Iterator[str]:
        """
        Generate text completion with streaming.

        Args:
            prompt: User prompt
            system: Optional system prompt
            **kwargs: Additional generation parameters

        Yields:
            Text chunks as they are generated
        """
        try:
            import ollama

            # Prepare messages
            messages = []
            if system:
                messages.append({"role": "system", "content": system})
            messages.append({"role": "user", "content": prompt})

            # Stream response
            for chunk in ollama.chat(
                model=self.config.model,
                messages=messages,
                stream=True,
                options={
                    "temperature": kwargs.get("temperature", self.config.temperature),
                },
            ):
                if "message" in chunk:
                    content = chunk["message"].get("content", "")
                    if content:
                        yield content

        except Exception as e:
            raise RuntimeError(f"Ollama streaming failed: {mask_error_text(str(e))}")

    def generate_vision(
        self, prompt: str, image_path: str, system: Optional[str] = None, **kwargs
    ) -> Dict[str, Any]:
        """
        Generate response with vision (image) input.

        Args:
            prompt: Text prompt/question about image
            image_path: Path to image file
            system: Optional system prompt
            **kwargs: Additional generation parameters

        Returns:
            Dict with 'response' key containing analysis
        """
        try:
            import ollama

            # Prepare messages with image
            messages = []
            if system:
                messages.append({"role": "system", "content": system})

            messages.append(
                {
                    "role": "user",
                    "content": prompt,
                    "images": [image_path],  # Ollama format for images
                }
            )

            # Generate response
            response = ollama.chat(
                model=self.config.model,
                messages=messages,
                stream=False,
                options={
                    "temperature": kwargs.get("temperature", self.config.temperature),
                },
            )

            return {
                "response": response["message"]["content"],
                "model": response["model"],
                "done": response.get("done", True),
            }

        except Exception as e:
            raise RuntimeError(
                f"Ollama vision generation failed: {mask_error_text(str(e))}"
            )

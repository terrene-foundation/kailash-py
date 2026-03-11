"""Ollama vision provider for multi-modal image processing."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from ..signatures.multi_modal import ImageField
from .ollama_provider import OllamaConfig, OllamaProvider


@dataclass
class OllamaVisionConfig(OllamaConfig):
    """Configuration for Ollama vision provider."""

    model: str = "llava:13b"  # Default vision model
    max_images: int = 10  # Max images per request
    detail: str = "auto"  # Detail level: auto, low, high


class OllamaVisionProvider(OllamaProvider):
    """
    Ollama vision provider for image analysis.

    Supports:
    - Image classification
    - Visual question answering
    - Image description generation
    - Document analysis (OCR)
    - Multi-image processing

    Uses llava:13b or bakllava models via Ollama.
    """

    def __init__(self, config: OllamaVisionConfig = None):
        """Initialize Ollama vision provider."""
        self.vision_config = config or OllamaVisionConfig()
        super().__init__(config=self.vision_config)

        # Ensure vision model is available
        self._ensure_vision_model()

    def _ensure_vision_model(self):
        """Ensure vision model (llava) is downloaded."""
        from .ollama_model_manager import OllamaModelManager

        manager = OllamaModelManager()

        # Try to ensure model is available
        if not manager.model_exists(self.vision_config.model):
            print(f"Vision model {self.vision_config.model} not found.")
            print("Downloading... (this may take a while, ~7GB)")

            success = manager.download_model(self.vision_config.model)

            if not success:
                raise RuntimeError(
                    f"Failed to download vision model: {self.vision_config.model}\n"
                    f"Please run manually: ollama pull {self.vision_config.model}"
                )

    def analyze_image(
        self,
        image: Union[ImageField, str, Path],
        prompt: str,
        system: Optional[str] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Analyze image with text prompt.

        Args:
            image: ImageField, file path, or URL
            prompt: Text prompt/question about image
            system: Optional system prompt
            **kwargs: Additional generation parameters

        Returns:
            Dict with 'response' containing analysis
        """
        # For Ollama, pass file path directly (Ollama accepts file paths as strings)
        if isinstance(image, ImageField):
            # If ImageField has a source path, use it
            image_path = (
                str(image.source)
                if hasattr(image, "source") and image.source
                else str(image.data)
            )
        else:
            # String or Path - pass directly
            image_path = str(image)

        # Format for Ollama vision API
        return self.generate_vision(
            prompt=prompt, image_path=image_path, system=system, **kwargs
        )

    def analyze_images(
        self,
        images: List[Union[ImageField, str, Path]],
        prompt: str,
        system: Optional[str] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Analyze multiple images with text prompt.

        Args:
            images: List of ImageFields, file paths, or URLs
            prompt: Text prompt about all images
            system: Optional system prompt
            **kwargs: Additional generation parameters

        Returns:
            Dict with 'response' containing analysis
        """
        if len(images) > self.vision_config.max_images:
            raise ValueError(
                f"Too many images ({len(images)}). "
                f"Max: {self.vision_config.max_images}"
            )

        # Convert all to ImageFields
        image_fields = []
        for img in images:
            if not isinstance(img, ImageField):
                field = ImageField()
                field.load(img)
                image_fields.append(field)
            else:
                image_fields.append(img)

        # Format for Ollama (supports multiple images)
        try:
            import ollama

            # Prepare messages with multiple images
            messages = []
            if system:
                messages.append({"role": "system", "content": system})

            # Ollama format: single message with multiple images
            messages.append(
                {
                    "role": "user",
                    "content": prompt,
                    "images": [field.to_base64() for field in image_fields],
                }
            )

            # Generate response
            response = ollama.chat(
                model=self.vision_config.model,
                messages=messages,
                stream=False,
                options={
                    "temperature": kwargs.get(
                        "temperature", self.vision_config.temperature
                    ),
                },
            )

            return {
                "response": response["message"]["content"],
                "model": response["model"],
                "images_analyzed": len(image_fields),
            }

        except Exception as e:
            raise RuntimeError(f"Multi-image analysis failed: {e}")

    def describe_image(
        self, image: Union[ImageField, str, Path], detail: str = "auto", **kwargs
    ) -> str:
        """
        Generate description of image.

        Args:
            image: Image to describe
            detail: Detail level (auto, brief, detailed)
            **kwargs: Additional parameters

        Returns:
            Description string
        """
        prompts = {
            "brief": "Describe this image in one sentence.",
            "detailed": "Provide a detailed description of this image, including objects, people, setting, colors, and any text visible.",
            "auto": "Describe what you see in this image.",
        }

        result = self.analyze_image(
            image=image, prompt=prompts.get(detail, prompts["auto"]), **kwargs
        )

        return result["response"]

    def answer_visual_question(
        self, image: Union[ImageField, str, Path], question: str, **kwargs
    ) -> str:
        """
        Answer question about image.

        Args:
            image: Image to analyze
            question: Question about the image
            **kwargs: Additional parameters

        Returns:
            Answer string
        """
        result = self.analyze_image(
            image=image,
            prompt=question,
            system="You are a helpful vision assistant. Answer questions about images accurately and concisely.",
            **kwargs,
        )

        return result["response"]

    def extract_text(self, image: Union[ImageField, str, Path], **kwargs) -> str:
        """
        Extract text from image (OCR).

        Args:
            image: Image containing text
            **kwargs: Additional parameters

        Returns:
            Extracted text
        """
        result = self.analyze_image(
            image=image,
            prompt="Extract all visible text from this image. Provide the text exactly as it appears, maintaining formatting and structure.",
            system="You are an OCR system. Extract text accurately.",
            **kwargs,
        )

        return result["response"]

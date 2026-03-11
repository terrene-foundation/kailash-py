"""Ollama model management for Kaizen multi-modal processing."""

import subprocess
from dataclasses import dataclass
from typing import Callable, Dict, Optional


@dataclass
class ModelInfo:
    """Information about an Ollama model."""

    name: str
    size: int  # Size in bytes
    modified: str
    digest: str


class OllamaModelManager:
    """
    Manage Ollama models for Kaizen.

    Features:
    - Check if models exist locally
    - Auto-download models if missing
    - Track download progress
    - Validate model availability
    """

    RECOMMENDED_VISION_MODELS = {
        "llava:13b": {
            "size_gb": 7.4,
            "description": "Primary vision model (best quality)",
            "use_case": "Image analysis, VQA, OCR",
        },
        "bakllava": {
            "size_gb": 4.7,
            "description": "Faster vision model",
            "use_case": "Quick image analysis",
        },
    }

    def __init__(self):
        """Initialize Ollama model manager."""
        self._check_ollama_installed()

    def _check_ollama_installed(self) -> bool:
        """Check if Ollama is installed and accessible."""
        try:
            result = subprocess.run(
                ["ollama", "--version"], capture_output=True, text=True, timeout=5
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def is_ollama_running(self) -> bool:
        """Check if Ollama service is running."""
        try:
            import ollama

            # Try to list models - if this works, service is running
            ollama.list()
            return True
        except Exception:
            return False

    def list_models(self) -> list:
        """List all locally available Ollama models."""
        try:
            import ollama

            models_response = ollama.list()

            models = []
            # ollama.list() returns a ListResponse object with .models attribute
            for model_data in models_response.models:
                models.append(
                    ModelInfo(
                        name=model_data.model,  # .model not .name
                        size=model_data.size,
                        modified=str(model_data.modified_at),  # datetime object
                        digest=model_data.digest,
                    )
                )

            return models
        except Exception as e:
            raise RuntimeError(f"Failed to list Ollama models: {e}")

    def model_exists(self, model_name: str) -> bool:
        """Check if a specific model exists locally."""
        try:
            models = self.list_models()
            return any(m.name.startswith(model_name) for m in models)
        except Exception:
            return False

    def download_model(
        self,
        model_name: str,
        progress_callback: Optional[Callable[[str, float], None]] = None,
    ) -> bool:
        """
        Download an Ollama model with progress tracking.

        Args:
            model_name: Name of model to download (e.g., 'llava:13b')
            progress_callback: Optional callback(status, percent) for progress

        Returns:
            True if download successful, False otherwise
        """
        try:
            import ollama

            print(f"Downloading Ollama model: {model_name}")

            # Pull model with streaming progress
            for progress in ollama.pull(model_name, stream=True):
                status = progress.get("status", "")

                # Calculate progress percentage if available
                if "completed" in progress and "total" in progress:
                    completed = progress["completed"]
                    total = progress["total"]
                    percent = (completed / total * 100) if total > 0 else 0

                    if progress_callback:
                        progress_callback(status, percent)
                    else:
                        print(f"  {status}: {percent:.1f}%")
                else:
                    if progress_callback:
                        progress_callback(status, 0)
                    else:
                        print(f"  {status}")

            print(f"✅ Model {model_name} downloaded successfully")
            return True

        except Exception as e:
            print(f"❌ Failed to download model {model_name}: {e}")
            return False

    def ensure_model_available(
        self, model_name: str, auto_download: bool = True
    ) -> bool:
        """
        Ensure a model is available, download if missing.

        Args:
            model_name: Name of model to ensure
            auto_download: Download if missing (default: True)

        Returns:
            True if model is available, False otherwise
        """
        # Check if already available
        if self.model_exists(model_name):
            print(f"✅ Model {model_name} already available")
            return True

        # Download if requested
        if auto_download:
            print(f"📥 Model {model_name} not found, downloading...")
            return self.download_model(model_name)

        print(f"❌ Model {model_name} not available and auto_download=False")
        return False

    def get_model_info(self, model_name: str) -> Optional[ModelInfo]:
        """Get information about a specific model."""
        models = self.list_models()
        for model in models:
            if model.name.startswith(model_name):
                return model
        return None

    def setup_vision_models(self, auto_download: bool = True) -> Dict[str, bool]:
        """
        Setup recommended vision models for Kaizen.

        Args:
            auto_download: Download missing models (default: True)

        Returns:
            Dict mapping model names to availability status
        """
        results = {}

        for model_name in self.RECOMMENDED_VISION_MODELS.keys():
            print(f"\nChecking {model_name}...")
            available = self.ensure_model_available(model_name, auto_download)
            results[model_name] = available

        return results

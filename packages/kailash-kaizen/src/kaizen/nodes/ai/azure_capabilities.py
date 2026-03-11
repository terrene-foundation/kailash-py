"""Azure capability registry for Unified Azure Provider.

This module provides feature gap detection and handling between
Azure OpenAI Service and Azure AI Foundry.
"""

import logging
import re
import warnings
from dataclasses import dataclass
from enum import Enum
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class GapHandling(Enum):
    """Strategies for handling feature gaps between Azure backends."""

    PASSTHROUGH = "passthrough"  # Let request through, backend will handle
    TRANSLATE = "translate"  # Transform request for compatibility
    WARN_PROCEED = "warn_proceed"  # Warn user but proceed
    ERROR = "error"  # Raise error with guidance


@dataclass
class FeatureInfo:
    """Information about a feature's availability across Azure backends."""

    name: str
    azure_openai: bool
    azure_ai_foundry: bool
    gap_handling: GapHandling = GapHandling.ERROR
    guidance: Optional[str] = None
    notes: Optional[str] = None


class FeatureDegradationWarning(UserWarning):
    """Warning issued when a feature has degraded functionality on a backend."""

    pass


class FeatureNotSupportedError(Exception):
    """Error raised when a feature is not supported on the current backend."""

    def __init__(
        self,
        feature: str,
        current_backend: str,
        required_backend: Optional[str] = None,
        guidance: Optional[str] = None,
    ):
        self.feature = feature
        self.current_backend = current_backend
        self.required_backend = required_backend
        self.guidance = guidance

        # Build error message
        message = f"Feature '{feature}' is not supported on {current_backend}"
        if required_backend:
            message += f". Requires {required_backend}"
        if guidance:
            message += f". {guidance}"

        super().__init__(message)


# Feature registry with support information
FEATURE_REGISTRY: Dict[str, FeatureInfo] = {
    # Core capabilities - supported on both
    "chat": FeatureInfo(
        name="chat",
        azure_openai=True,
        azure_ai_foundry=True,
        gap_handling=GapHandling.PASSTHROUGH,
    ),
    "embeddings": FeatureInfo(
        name="embeddings",
        azure_openai=True,
        azure_ai_foundry=True,
        gap_handling=GapHandling.PASSTHROUGH,
    ),
    "streaming": FeatureInfo(
        name="streaming",
        azure_openai=True,
        azure_ai_foundry=True,
        gap_handling=GapHandling.PASSTHROUGH,
    ),
    "tool_calling": FeatureInfo(
        name="tool_calling",
        azure_openai=True,
        azure_ai_foundry=True,
        gap_handling=GapHandling.PASSTHROUGH,
    ),
    "structured_output": FeatureInfo(
        name="structured_output",
        azure_openai=True,
        azure_ai_foundry=True,
        gap_handling=GapHandling.TRANSLATE,
        notes="May require format translation on AI Foundry",
    ),
    # Vision - partial support on AI Foundry
    "vision": FeatureInfo(
        name="vision",
        azure_openai=True,
        azure_ai_foundry=True,  # Supported but model-dependent
        gap_handling=GapHandling.WARN_PROCEED,
        notes="AI Foundry vision support depends on model availability",
    ),
    # Azure OpenAI exclusive features
    "audio_input": FeatureInfo(
        name="audio_input",
        azure_openai=True,
        azure_ai_foundry=False,
        gap_handling=GapHandling.ERROR,
        guidance="Audio input requires Azure OpenAI Service. "
        "Set AZURE_ENDPOINT to *.openai.azure.com or use transcription API first.",
    ),
    "reasoning_models": FeatureInfo(
        name="reasoning_models",
        azure_openai=True,
        azure_ai_foundry=False,
        gap_handling=GapHandling.ERROR,
        guidance="Reasoning models (o1, o3, GPT-5) require Azure OpenAI Service. "
        "Set AZURE_ENDPOINT to *.openai.azure.com",
    ),
    # AI Foundry exclusive features
    "llama_models": FeatureInfo(
        name="llama_models",
        azure_openai=False,
        azure_ai_foundry=True,
        gap_handling=GapHandling.ERROR,
        guidance="Llama models require Azure AI Foundry. "
        "Set AZURE_ENDPOINT to *.inference.ai.azure.com",
    ),
    "mistral_models": FeatureInfo(
        name="mistral_models",
        azure_openai=False,
        azure_ai_foundry=True,
        gap_handling=GapHandling.ERROR,
        guidance="Mistral models require Azure AI Foundry. "
        "Set AZURE_ENDPOINT to *.inference.ai.azure.com",
    ),
}

# Model detection patterns
REASONING_MODEL_PATTERNS = [
    r"^o1",  # o1, o1-preview, o1-mini
    r"^o3",  # o3, o3-mini
    r"^gpt-5",  # gpt-5, gpt-5-turbo (case insensitive)
]

LLAMA_MODEL_PATTERNS = [
    r"llama",  # llama-3.1-8b, meta-llama, etc.
]

MISTRAL_MODEL_PATTERNS = [
    r"mistral",  # mistral-large, mistral-7b
    r"mixtral",  # mixtral-8x7b
]


class AzureCapabilityRegistry:
    """
    Registry for Azure backend capabilities and feature gaps.

    Provides:
    - Feature availability checking per backend
    - Model requirement validation
    - Gap handling with appropriate errors/warnings
    """

    VALID_BACKENDS = ("azure_openai", "azure_ai_foundry")

    def __init__(self, backend: str):
        """
        Initialize the capability registry.

        Args:
            backend: The Azure backend type ("azure_openai" or "azure_ai_foundry")

        Raises:
            ValueError: If backend is not valid
        """
        if backend not in self.VALID_BACKENDS:
            raise ValueError(
                f"Invalid backend: '{backend}'. "
                f"Must be one of: {', '.join(self.VALID_BACKENDS)}"
            )
        self._backend = backend

    @property
    def backend(self) -> str:
        """Return the current backend type."""
        return self._backend

    def supports(self, feature: str) -> bool:
        """
        Check if a feature is supported on the current backend.

        Args:
            feature: The feature name to check

        Returns:
            True if supported, False if not. Unknown features return True (passthrough).
        """
        info = FEATURE_REGISTRY.get(feature)
        if info is None:
            # Unknown features pass through
            return True

        if self._backend == "azure_openai":
            return info.azure_openai
        else:
            return info.azure_ai_foundry

    def check_feature(self, feature: str) -> None:
        """
        Check feature availability and raise appropriate error/warning.

        Args:
            feature: The feature name to check

        Raises:
            FeatureNotSupportedError: If feature is not supported (hard gap)

        Warns:
            FeatureDegradationWarning: If feature has degraded support
        """
        info = FEATURE_REGISTRY.get(feature)
        if info is None:
            # Unknown features pass through
            return

        supported = self.supports(feature)

        if not supported:
            # Hard gap - raise error
            required_backend = self._get_required_backend(info)
            raise FeatureNotSupportedError(
                feature=feature,
                current_backend=self._backend,
                required_backend=required_backend,
                guidance=info.guidance,
            )

        # Check for degraded support (warn_proceed)
        if info.gap_handling == GapHandling.WARN_PROCEED:
            # Only warn if we're on the backend with degraded support
            if self._backend == "azure_ai_foundry" and info.azure_openai:
                # AI Foundry has degraded support compared to Azure OpenAI
                warnings.warn(
                    f"Feature '{feature}' may have limited functionality on "
                    f"{self._backend}. {info.notes or ''}",
                    FeatureDegradationWarning,
                )

    def check_model_requirements(self, model: Optional[str]) -> None:
        """
        Check if a model has backend requirements.

        Args:
            model: The model name/deployment to check

        Raises:
            FeatureNotSupportedError: If model requires a different backend
        """
        if not model:
            return

        model_lower = model.lower()

        # Check reasoning models (Azure OpenAI only)
        for pattern in REASONING_MODEL_PATTERNS:
            if re.search(pattern, model_lower, re.IGNORECASE):
                if self._backend != "azure_openai":
                    info = FEATURE_REGISTRY["reasoning_models"]
                    raise FeatureNotSupportedError(
                        feature="reasoning_models",
                        current_backend=self._backend,
                        required_backend="Azure OpenAI Service",
                        guidance=info.guidance,
                    )
                return

        # Check Llama models (AI Foundry only)
        for pattern in LLAMA_MODEL_PATTERNS:
            if re.search(pattern, model_lower, re.IGNORECASE):
                if self._backend != "azure_ai_foundry":
                    info = FEATURE_REGISTRY["llama_models"]
                    raise FeatureNotSupportedError(
                        feature="llama_models",
                        current_backend=self._backend,
                        required_backend="Azure AI Foundry",
                        guidance=info.guidance,
                    )
                return

        # Check Mistral models (AI Foundry only)
        for pattern in MISTRAL_MODEL_PATTERNS:
            if re.search(pattern, model_lower, re.IGNORECASE):
                if self._backend != "azure_ai_foundry":
                    info = FEATURE_REGISTRY["mistral_models"]
                    raise FeatureNotSupportedError(
                        feature="mistral_models",
                        current_backend=self._backend,
                        required_backend="Azure AI Foundry",
                        guidance=info.guidance,
                    )
                return

    def get_capabilities(self) -> Dict[str, bool]:
        """
        Get all feature capabilities for the current backend.

        Returns:
            Dictionary mapping feature names to support status
        """
        return {feature: self.supports(feature) for feature in FEATURE_REGISTRY}

    def get_feature_info(self, feature: str) -> Optional[FeatureInfo]:
        """
        Get detailed information about a feature.

        Args:
            feature: The feature name

        Returns:
            FeatureInfo if known, None otherwise
        """
        return FEATURE_REGISTRY.get(feature)

    def _get_required_backend(self, info: FeatureInfo) -> Optional[str]:
        """Determine which backend is required for a feature."""
        if info.azure_openai and not info.azure_ai_foundry:
            return "Azure OpenAI Service"
        elif info.azure_ai_foundry and not info.azure_openai:
            return "Azure AI Foundry"
        return None

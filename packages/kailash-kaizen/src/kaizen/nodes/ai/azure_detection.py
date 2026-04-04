"""Azure backend detection for Unified Azure Provider.

This module provides intelligent detection of whether to use Azure OpenAI Service
or Azure AI Foundry based on endpoint URL patterns.

Also provides ``resolve_azure_env`` -- a shared helper for resolving Azure
environment variables with canonical-first, legacy-with-deprecation semantics.
"""

import logging
import os
import re
import warnings
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


def resolve_azure_env(canonical: str, *legacy: str) -> Optional[str]:
    """Resolve an Azure environment variable with canonical-first semantics.

    Checks the canonical name first. If not set, checks each legacy name in
    order and emits a :class:`DeprecationWarning` on the first match.

    The warning uses ``stacklevel=3`` so it points at the caller's caller
    (typically user code), not internal framework code.

    Args:
        canonical: The preferred environment variable name (e.g. ``AZURE_ENDPOINT``).
        *legacy: Zero or more legacy names to check as fallbacks.

    Returns:
        The resolved value, or ``None`` if no variable is set.
    """
    value = os.getenv(canonical)
    if value:
        return value
    for legacy_name in legacy:
        value = os.getenv(legacy_name)
        if value:
            warnings.warn(
                f"Environment variable {legacy_name} is deprecated. "
                f"Use {canonical} instead.",
                DeprecationWarning,
                stacklevel=3,
            )
            return value
    return None


# Endpoint patterns for Azure OpenAI Service
AZURE_OPENAI_PATTERNS = [
    r".*\.openai\.azure\.com",  # Standard Azure OpenAI
    r".*\.privatelink\.openai\.azure\.com",  # Private endpoint
    r".*cognitiveservices\.azure\.com.*openai",  # Legacy cognitive services with openai path
    r".*\.cognitiveservices\.azure\.com",  # Cognitive Services (India South, other regions)
]

# Endpoint patterns for Azure AI Foundry
AZURE_AI_FOUNDRY_PATTERNS = [
    r".*\.inference\.ai\.azure\.com",  # Standard inference
    r".*\.services\.ai\.azure\.com",  # AI services
    r".*\.api\.cognitive\.microsoft\.com(?!/openai)",  # Regional cognitive (not openai)
]


class AzureBackendDetector:
    """
    Intelligent Azure backend detection from endpoint URL.

    Detection Priority:
    1. Explicit ``AZURE_BACKEND`` env var
    2. Pattern matching on endpoint URL
    3. Default to Azure OpenAI (most common enterprise usage)

    Environment Variables (canonical -- recommended):
        AZURE_ENDPOINT: Endpoint URL
        AZURE_API_KEY: API key
        AZURE_API_VERSION: API version (default: 2024-10-21)
        AZURE_BACKEND: Explicit backend override ('openai' or 'foundry')
        AZURE_DEPLOYMENT: Deployment name

    Legacy (still supported, emit DeprecationWarning):
        AZURE_OPENAI_ENDPOINT -> use AZURE_ENDPOINT
        AZURE_OPENAI_API_KEY -> use AZURE_API_KEY
        AZURE_OPENAI_API_VERSION -> use AZURE_API_VERSION
        AZURE_AI_INFERENCE_ENDPOINT -> use AZURE_ENDPOINT
        AZURE_AI_INFERENCE_API_KEY -> use AZURE_API_KEY
    """

    def __init__(self):
        """Initialize the detector."""
        self._detected_backend: Optional[str] = None
        self._detection_source: Optional[str] = None
        self._endpoint: Optional[str] = None

    def detect(self) -> Tuple[Optional[str], dict]:
        """
        Detect appropriate Azure backend.

        Returns:
            Tuple of (backend_type, config_dict)
            backend_type: "azure_openai", "azure_ai_foundry", or None
            config_dict: Configuration parameters including endpoint, api_key, api_version
        """
        # Priority 1: Explicit override via AZURE_BACKEND
        explicit = os.getenv("AZURE_BACKEND")
        if explicit:
            backend = self._normalize_backend_name(explicit)
            self._detected_backend = backend
            self._detection_source = "explicit"
            logger.info(f"Azure backend explicitly set via AZURE_BACKEND: {backend}")
            return backend, self._get_config(backend)

        # Get endpoint for pattern matching
        endpoint = self._get_endpoint()
        if not endpoint:
            logger.debug("No Azure endpoint configured")
            return None, {}

        self._endpoint = endpoint

        # Priority 2: Pattern matching
        backend = self._detect_from_pattern(endpoint)
        if backend:
            self._detected_backend = backend
            self._detection_source = "pattern"
            logger.info(f"Azure backend detected from URL pattern: {backend}")
            return backend, self._get_config(backend)

        # Priority 3: Default to Azure OpenAI (80%+ of enterprise usage)
        self._detected_backend = "azure_openai"
        self._detection_source = "default"
        logger.warning(
            f"Could not determine Azure backend from endpoint URL: {endpoint}. "
            "Defaulting to Azure OpenAI. "
            "Set AZURE_BACKEND=openai or AZURE_BACKEND=foundry to specify explicitly."
        )
        return "azure_openai", self._get_config("azure_openai")

    def _detect_from_pattern(self, endpoint: str) -> Optional[str]:
        """
        Detect backend from endpoint URL pattern.

        Args:
            endpoint: The Azure endpoint URL

        Returns:
            "azure_openai", "azure_ai_foundry", or None if no pattern matches
        """
        endpoint_lower = endpoint.lower()

        # Check Azure OpenAI patterns
        for pattern in AZURE_OPENAI_PATTERNS:
            if re.search(pattern, endpoint_lower, re.IGNORECASE):
                return "azure_openai"

        # Check AI Foundry patterns
        for pattern in AZURE_AI_FOUNDRY_PATTERNS:
            if re.search(pattern, endpoint_lower, re.IGNORECASE):
                return "azure_ai_foundry"

        return None

    def _get_endpoint(self) -> Optional[str]:
        """Get endpoint from environment variables.

        Resolution: AZURE_ENDPOINT (canonical) -> AZURE_OPENAI_ENDPOINT
        -> AZURE_AI_INFERENCE_ENDPOINT (legacy, with deprecation warning).
        """
        return resolve_azure_env(
            "AZURE_ENDPOINT",
            "AZURE_OPENAI_ENDPOINT",
            "AZURE_AI_INFERENCE_ENDPOINT",
        )

    def _get_api_key(self) -> Optional[str]:
        """Get API key from environment variables.

        Resolution: AZURE_API_KEY (canonical) -> AZURE_OPENAI_API_KEY
        -> AZURE_AI_INFERENCE_API_KEY (legacy, with deprecation warning).
        """
        return resolve_azure_env(
            "AZURE_API_KEY",
            "AZURE_OPENAI_API_KEY",
            "AZURE_AI_INFERENCE_API_KEY",
        )

    def _get_config(self, backend: str) -> dict:
        """
        Get configuration dictionary for the specified backend.

        Args:
            backend: The backend type ("azure_openai" or "azure_ai_foundry")

        Returns:
            Configuration dictionary with endpoint, api_key, api_version, etc.
        """
        return {
            "endpoint": self._get_endpoint(),
            "api_key": self._get_api_key(),
            "api_version": (
                resolve_azure_env(
                    "AZURE_API_VERSION",
                    "AZURE_OPENAI_API_VERSION",
                )
                or "2024-10-21"
            ),
            "deployment": os.getenv("AZURE_DEPLOYMENT"),
            "backend": backend,
        }

    def _normalize_backend_name(self, name: str) -> str:
        """
        Normalize backend name to canonical form.

        Args:
            name: User-provided backend name

        Returns:
            Canonical backend name ("azure_openai" or "azure_ai_foundry")

        Raises:
            ValueError: If backend name is not recognized
        """
        name_lower = name.lower().strip()

        # Azure OpenAI variations
        if name_lower in ("openai", "azure_openai", "azureopenai", "azure-openai"):
            return "azure_openai"

        # AI Foundry variations
        if name_lower in (
            "foundry",
            "ai_foundry",
            "azure_ai_foundry",
            "aifoundry",
            "azure-ai-foundry",
            "inference",
        ):
            return "azure_ai_foundry"

        raise ValueError(
            f"Invalid AZURE_BACKEND value: '{name}'. Use 'openai' or 'foundry'."
        )

    @property
    def detected_backend(self) -> Optional[str]:
        """Return the currently detected backend type."""
        return self._detected_backend

    @property
    def detection_source(self) -> Optional[str]:
        """
        Return how the backend was detected.

        Values: "explicit", "pattern", "default", or None
        """
        return self._detection_source

    @property
    def endpoint(self) -> Optional[str]:
        """Return the endpoint URL being used."""
        return self._endpoint

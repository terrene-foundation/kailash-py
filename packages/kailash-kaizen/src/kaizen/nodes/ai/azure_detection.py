"""Azure backend detection for Unified Azure Provider.

This module provides intelligent detection of whether to use Azure OpenAI Service
or Azure AI Foundry based on endpoint URL patterns, with fallback mechanisms
for error-based correction.
"""

import logging
import os
import re
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# Endpoint patterns for Azure OpenAI Service
AZURE_OPENAI_PATTERNS = [
    r".*\.openai\.azure\.com",  # Standard Azure OpenAI
    r".*\.privatelink\.openai\.azure\.com",  # Private endpoint
    r".*cognitiveservices\.azure\.com.*openai",  # Legacy cognitive services with openai path
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
    1. Explicit AZURE_BACKEND env var
    2. Pattern matching on endpoint URL
    3. Default to Azure OpenAI (most common enterprise usage)
    4. Error-based correction on API failure

    Environment Variables:
        AZURE_ENDPOINT: Unified endpoint URL (recommended)
        AZURE_API_KEY: Unified API key
        AZURE_BACKEND: Explicit backend override ('openai' or 'foundry')
        AZURE_API_VERSION: API version (default: 2024-10-21)

        Legacy (backward compatible):
        AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_KEY
        AZURE_AI_INFERENCE_ENDPOINT, AZURE_AI_INFERENCE_API_KEY
    """

    # Error signatures indicating wrong backend was used
    FOUNDRY_ERROR_SIGNATURES = [
        "audience is incorrect",
        "token audience",
        "invalid audience",
    ]

    OPENAI_ERROR_SIGNATURES = [
        "deploymentnotfound",
        "resource not found",
        "the api deployment for this resource does not exist",
        "model not found",
    ]

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
            f"Unknown Azure endpoint pattern: {endpoint}. "
            "Defaulting to Azure OpenAI. Set AZURE_BACKEND=foundry to override."
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

    def handle_error(self, error: Exception) -> Optional[str]:
        """
        Analyze error to detect if wrong backend was used.

        This enables automatic fallback when the initial backend detection
        was incorrect (e.g., for custom domains or proxies).

        Args:
            error: The exception from the failed API call

        Returns:
            Correct backend type if detected from error, None otherwise
        """
        error_str = str(error).lower()

        # Check if error suggests we should switch to AI Foundry
        if self._detected_backend == "azure_openai":
            for sig in self.FOUNDRY_ERROR_SIGNATURES:
                if sig in error_str:
                    logger.info(
                        f"Error signature '{sig}' suggests Azure AI Foundry endpoint. "
                        "Switching backend."
                    )
                    self._detected_backend = "azure_ai_foundry"
                    self._detection_source = "error_fallback"
                    return "azure_ai_foundry"

        # Check if error suggests we should switch to Azure OpenAI
        elif self._detected_backend == "azure_ai_foundry":
            for sig in self.OPENAI_ERROR_SIGNATURES:
                if sig in error_str:
                    logger.info(
                        f"Error signature '{sig}' suggests Azure OpenAI endpoint. "
                        "Switching backend."
                    )
                    self._detected_backend = "azure_openai"
                    self._detection_source = "error_fallback"
                    return "azure_openai"

        # Error doesn't indicate wrong backend
        return None

    def _get_endpoint(self) -> Optional[str]:
        """
        Get endpoint from environment variables.

        Resolution priority:
        1. AZURE_ENDPOINT (unified)
        2. AZURE_OPENAI_ENDPOINT (legacy Azure OpenAI)
        3. AZURE_AI_INFERENCE_ENDPOINT (legacy AI Foundry)
        """
        return (
            os.getenv("AZURE_ENDPOINT")
            or os.getenv("AZURE_OPENAI_ENDPOINT")
            or os.getenv("AZURE_AI_INFERENCE_ENDPOINT")
        )

    def _get_api_key(self) -> Optional[str]:
        """
        Get API key from environment variables.

        Resolution priority:
        1. AZURE_API_KEY (unified)
        2. AZURE_OPENAI_API_KEY (legacy Azure OpenAI)
        3. AZURE_AI_INFERENCE_API_KEY (legacy AI Foundry)
        """
        return (
            os.getenv("AZURE_API_KEY")
            or os.getenv("AZURE_OPENAI_API_KEY")
            or os.getenv("AZURE_AI_INFERENCE_API_KEY")
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
            "api_version": os.getenv("AZURE_API_VERSION", "2024-10-21"),
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
            f"Invalid AZURE_BACKEND value: '{name}'. " "Use 'openai' or 'foundry'."
        )

    @property
    def detected_backend(self) -> Optional[str]:
        """Return the currently detected backend type."""
        return self._detected_backend

    @property
    def detection_source(self) -> Optional[str]:
        """
        Return how the backend was detected.

        Values: "explicit", "pattern", "default", "error_fallback", or None
        """
        return self._detection_source

    @property
    def endpoint(self) -> Optional[str]:
        """Return the endpoint URL being used."""
        return self._endpoint

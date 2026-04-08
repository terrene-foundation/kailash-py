# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Provider error types for the Kaizen AI framework.

Centralised exception hierarchy for all provider operations. Each provider
wraps SDK-specific exceptions into one of these types so that consumers
never need to depend on a particular provider SDK.
"""

from __future__ import annotations


class ProviderError(Exception):
    """Base class for all provider errors.

    Attributes:
        provider_name: Name of the provider that raised the error.
        original_error: The underlying SDK exception, if available.
    """

    def __init__(
        self,
        message: str,
        *,
        provider_name: str = "",
        original_error: Exception | None = None,
    ) -> None:
        self.provider_name = provider_name
        self.original_error = original_error
        super().__init__(message)


class UnknownProviderError(ProviderError):
    """Raised when a provider name cannot be resolved by the registry."""


class ProviderUnavailableError(ProviderError):
    """Raised when a provider's prerequisites are not met.

    Typical causes: missing API key, uninstalled SDK package, unreachable
    local service (Ollama, Docker Model Runner).
    """


class CapabilityNotSupportedError(ProviderError):
    """Raised when a provider does not support the requested capability.

    For example, requesting embeddings from a chat-only provider.
    """


class AuthenticationError(ProviderError):
    """Raised when API key or credential validation fails."""


class RateLimitError(ProviderError):
    """Raised when the provider returns a rate-limit / quota-exceeded response."""


class ModelNotFoundError(ProviderError):
    """Raised when the requested model is not available on the provider."""

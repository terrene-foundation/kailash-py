# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""kailash-align exception hierarchy."""
from __future__ import annotations

__all__ = [
    "AlignmentError",
    "AdapterNotFoundError",
    "TrainingError",
    "ServingError",
    "GGUFConversionError",
    "OllamaNotAvailableError",
    "EvaluationError",
    "CacheNotFoundError",
    "MergeError",
]


class AlignmentError(Exception):
    """Base exception for all kailash-align errors."""

    pass


class AdapterNotFoundError(AlignmentError):
    """Raised when a requested adapter is not found in the registry."""

    pass


class TrainingError(AlignmentError):
    """Raised when training fails."""

    pass


class ServingError(AlignmentError):
    """Raised when serving operations fail (GGUF conversion, Ollama, vLLM)."""

    pass


class GGUFConversionError(ServingError):
    """Raised when GGUF conversion or validation fails."""

    pass


class OllamaNotAvailableError(ServingError):
    """Raised when Ollama CLI is not found or not running."""

    pass


class EvaluationError(AlignmentError):
    """Raised when evaluation fails."""

    pass


class CacheNotFoundError(AlignmentError):
    """Raised when a model is not found in the on-prem cache."""

    pass


class MergeError(AlignmentError):
    """Raised when adapter merge fails."""

    pass

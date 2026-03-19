from __future__ import annotations

# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Composition error hierarchy.

All composition errors inherit from CompositionError, which carries a
``details`` dict for structured error context.

These errors are canonical -- ``models.py`` re-exports them for backward
compatibility, but new code should import from this module directly.
"""

import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)

__all__ = ["CompositionError", "CycleDetectedError", "SchemaIncompatibleError"]


class CompositionError(Exception):
    """Base error for all composition validation failures.

    Attributes:
        details: Structured error context for debugging and logging.
    """

    def __init__(self, message: str, details: Dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.details: Dict[str, Any] = details or {}


class CycleDetectedError(CompositionError):
    """Raised when a cycle is detected in the agent DAG."""


class SchemaIncompatibleError(CompositionError):
    """Raised when output/input schemas are incompatible."""

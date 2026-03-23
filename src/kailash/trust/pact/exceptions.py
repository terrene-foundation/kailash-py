# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""PACT governance error hierarchy.

All PACT governance errors inherit from ``PactError``, which provides a
``.details`` dict for structured context (parallel to ``TrustError`` in
``kailash.trust.exceptions``). This follows EATP SDK convention D-ERR:
every error carries a ``details: Dict[str, Any]`` parameter.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

__all__ = [
    "PactError",
]


class PactError(Exception):
    """Base class for all PACT governance errors.

    Attributes:
        details: Structured context about the error (e.g., addresses,
            constraint values, envelope IDs). Defaults to an empty dict.
    """

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.details = details or {}

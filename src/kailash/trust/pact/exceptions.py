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
from typing import Any as Any

from kailash._governance_errors import PactError, UngovernedEgressRefused

logger = logging.getLogger(__name__)

__all__ = [
    "PactError",
    "DeserializationError",
    "UngovernedEgressRefused",
]


class DeserializationError(PactError):
    """Raised when a persisted governance object fails re-validation on load.

    A ``CompiledOrg`` reconstructed from stored JSON is an authorization root
    consumed by ``pact.access.can_access``. If the persisted bytes were
    tampered with (grammar-invalid address, node keyed by a foreign address,
    or a node whose declared type disagrees with its address), the load MUST
    fail closed rather than hand back an unvalidated authorization root.
    """

    pass

# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Enforcement modes for PactEngine -- ENFORCE, SHADOW, and DISABLED.

Enforcement modes control how PactEngine applies governance verdicts:

    ENFORCE (default): Verdicts are binding. Blocked actions are rejected.
    SHADOW: Verdicts are logged but never block. Useful for calibrating
        envelopes before switching to ENFORCE.
    DISABLED: Governance is skipped entirely. Emergency use only -- requires
        PACT_ALLOW_DISABLED_MODE=true environment variable.

Design principles:
1. ENFORCE is the safe default -- governance is always binding unless
   explicitly relaxed.
2. SHADOW is observation-only -- operators review shadow verdicts to
   calibrate envelopes before enforcement.
3. DISABLED requires an environment variable guard to prevent accidental
   governance bypass.
"""

from __future__ import annotations

import logging
import os
from enum import Enum

from kailash.trust.pact.exceptions import PactError

logger = logging.getLogger(__name__)

__all__ = ["EnforcementMode", "validate_enforcement_mode"]


class EnforcementMode(str, Enum):
    """Controls how PactEngine applies governance verdicts.

    Members:
        ENFORCE: Default. Verdicts are binding -- blocked actions are rejected.
        SHADOW: Run governance but never block. Verdicts are logged for
            calibration. WorkResult includes governance_shadow=True metadata.
        DISABLED: Skip governance entirely. Emergency use only -- requires
            PACT_ALLOW_DISABLED_MODE=true environment variable.
    """

    ENFORCE = "enforce"
    SHADOW = "shadow"
    DISABLED = "disabled"


def validate_enforcement_mode(mode: EnforcementMode) -> None:
    """Validate that the enforcement mode is permitted.

    DISABLED mode requires the PACT_ALLOW_DISABLED_MODE=true environment
    variable as a safety guard against accidental governance bypass.

    Args:
        mode: The enforcement mode to validate.

    Raises:
        PactError: If DISABLED mode is requested without the required
            environment variable.
    """
    if mode == EnforcementMode.DISABLED:
        if os.environ.get("PACT_ALLOW_DISABLED_MODE", "").lower() != "true":
            raise PactError(
                "DISABLED enforcement mode requires PACT_ALLOW_DISABLED_MODE=true env var",
                details={"mode": mode.value},
            )

# Copyright 2026 Terrene Foundation
# Licensed under the Apache License, Version 2.0
"""Knowledge clearance -- per-role classification access independent of authority.

Implements the PACT knowledge clearance framework where clearance is
orthogonal to seniority -- a junior role can hold higher clearance
than a senior role if the knowledge domain requires it.

Clearance levels: PUBLIC < RESTRICTED < CONFIDENTIAL < SECRET < TOP_SECRET.

The effective clearance for any access decision is computed as:
    min(role.max_clearance, POSTURE_CEILING[current_posture])

This ensures that even a role with TOP_SECRET clearance cannot access
SECRET data if operating at SUPERVISED posture (ceiling = RESTRICTED).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from pact.build.config.schema import ConfidentialityLevel, TrustPostureLevel

logger = logging.getLogger(__name__)

__all__ = ["RoleClearance", "VettingStatus", "effective_clearance", "POSTURE_CEILING"]


class VettingStatus(str, Enum):
    """Vetting status for a role's clearance grant."""

    PENDING = "pending"
    ACTIVE = "active"
    EXPIRED = "expired"
    REVOKED = "revoked"


POSTURE_CEILING: dict[TrustPostureLevel, ConfidentialityLevel] = {
    TrustPostureLevel.PSEUDO_AGENT: ConfidentialityLevel.PUBLIC,
    TrustPostureLevel.SUPERVISED: ConfidentialityLevel.RESTRICTED,
    TrustPostureLevel.SHARED_PLANNING: ConfidentialityLevel.CONFIDENTIAL,
    TrustPostureLevel.CONTINUOUS_INSIGHT: ConfidentialityLevel.SECRET,
    TrustPostureLevel.DELEGATED: ConfidentialityLevel.TOP_SECRET,
}

# Numeric ordering for clearance comparisons
_CLEARANCE_ORDER: dict[ConfidentialityLevel, int] = {
    ConfidentialityLevel.PUBLIC: 0,
    ConfidentialityLevel.RESTRICTED: 1,
    ConfidentialityLevel.CONFIDENTIAL: 2,
    ConfidentialityLevel.SECRET: 3,
    ConfidentialityLevel.TOP_SECRET: 4,
}


def effective_clearance(
    role_clearance: RoleClearance,
    posture: TrustPostureLevel,
) -> ConfidentialityLevel:
    """Compute effective clearance = min(role.max_clearance, posture_ceiling).

    Args:
        role_clearance: The role's clearance assignment.
        posture: The current trust posture level.

    Returns:
        The effective confidentiality level -- the lower of the role's
        max clearance and the posture ceiling.

    Raises:
        KeyError: If the posture is not in POSTURE_CEILING (should not happen
            with valid TrustPostureLevel values).
    """
    ceiling = POSTURE_CEILING[posture]
    role_level = _CLEARANCE_ORDER[role_clearance.max_clearance]
    ceiling_level = _CLEARANCE_ORDER[ceiling]
    result_level = min(role_level, ceiling_level)
    # Reverse lookup: find the ConfidentialityLevel for the numeric result
    for level, order in _CLEARANCE_ORDER.items():
        if order == result_level:
            return level
    # Fail-closed: if somehow no match found (should never happen),
    # return the most restrictive level we can
    logger.error(
        "effective_clearance: no ConfidentialityLevel found for order=%d; "
        "returning PUBLIC (fail-closed). role=%s, posture=%s",
        result_level,
        role_clearance.role_address,
        posture.value,
    )
    return ConfidentialityLevel.PUBLIC


@dataclass(frozen=True)
class RoleClearance:
    """A clearance assignment for a specific role at a D/T/R address.

    Clearance is independent of authority -- a junior AML analyst may hold
    SECRET clearance for investigation data while their department head
    holds only CONFIDENTIAL.

    Attributes:
        role_address: The D/T/R positional address of the role.
        max_clearance: Maximum confidentiality level this role may access.
        compartments: Named compartments this role has access to.
            For SECRET and TOP_SECRET data, the role must hold ALL
            compartments the item belongs to.
        granted_by_role_address: The address of the role that granted this
            clearance (for audit trail).
        vetting_status: Current vetting status. Only ACTIVE clearances
            are valid for access decisions.
        review_at: When this clearance should be reviewed/renewed.
        nda_signed: Whether the role holder has signed an NDA.
            Required for SECRET and TOP_SECRET clearance.
    """

    role_address: str
    max_clearance: ConfidentialityLevel
    compartments: frozenset[str] = field(default_factory=frozenset)
    granted_by_role_address: str = ""
    vetting_status: VettingStatus = VettingStatus.ACTIVE
    review_at: datetime | None = None
    nda_signed: bool = False

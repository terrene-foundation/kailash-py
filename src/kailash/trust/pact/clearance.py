# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
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
from typing import Any

from kailash.trust.pact.config import ConfidentialityLevel, TrustPostureLevel

logger = logging.getLogger(__name__)

__all__ = [
    "RoleClearance",
    "VettingStatus",
    "_VALID_TRANSITIONS",
    "effective_clearance",
    "validate_transition",
    "POSTURE_CEILING",
]


class VettingStatus(str, Enum):
    """Vetting status for a role's clearance grant."""

    PENDING = "pending"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    EXPIRED = "expired"
    REVOKED = "revoked"


POSTURE_CEILING: dict[TrustPostureLevel, ConfidentialityLevel] = {
    TrustPostureLevel.PSEUDO: ConfidentialityLevel.PUBLIC,
    TrustPostureLevel.TOOL: ConfidentialityLevel.RESTRICTED,
    TrustPostureLevel.SUPERVISED: ConfidentialityLevel.CONFIDENTIAL,
    TrustPostureLevel.DELEGATING: ConfidentialityLevel.SECRET,
    TrustPostureLevel.AUTONOMOUS: ConfidentialityLevel.TOP_SECRET,
}

# Numeric ordering for clearance comparisons
_CLEARANCE_ORDER: dict[ConfidentialityLevel, int] = {
    ConfidentialityLevel.PUBLIC: 0,
    ConfidentialityLevel.RESTRICTED: 1,
    ConfidentialityLevel.CONFIDENTIAL: 2,
    ConfidentialityLevel.SECRET: 3,
    ConfidentialityLevel.TOP_SECRET: 4,
}

_VALID_TRANSITIONS: dict[VettingStatus, frozenset[VettingStatus]] = {
    VettingStatus.PENDING: frozenset({VettingStatus.ACTIVE, VettingStatus.REVOKED}),
    VettingStatus.ACTIVE: frozenset(
        {VettingStatus.SUSPENDED, VettingStatus.EXPIRED, VettingStatus.REVOKED}
    ),
    VettingStatus.SUSPENDED: frozenset({VettingStatus.ACTIVE, VettingStatus.REVOKED}),
    VettingStatus.EXPIRED: frozenset({VettingStatus.ACTIVE, VettingStatus.REVOKED}),
    VettingStatus.REVOKED: frozenset(),  # terminal
}


def validate_transition(from_status: VettingStatus, to_status: VettingStatus) -> None:
    """Validate an FSM transition between vetting statuses.

    Raises PactError if the transition is not valid.
    """
    valid_targets = _VALID_TRANSITIONS.get(from_status, frozenset())
    if to_status not in valid_targets:
        from kailash.trust.pact.exceptions import PactError

        raise PactError(
            f"Invalid vetting status transition: {from_status.value} -> {to_status.value}",
            details={
                "from_status": from_status.value,
                "to_status": to_status.value,
                "valid_targets": [
                    s.value for s in sorted(valid_targets, key=lambda s: s.value)
                ],
            },
        )


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

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict suitable for JSON encoding.

        Returns:
            A dict representation of this clearance assignment.
            Enums serialize as ``.value``, datetimes as ``.isoformat()``,
            frozensets as sorted lists (deterministic ordering).
        """
        return {
            "role_address": self.role_address,
            "max_clearance": self.max_clearance.value,
            "compartments": sorted(self.compartments),
            "granted_by_role_address": self.granted_by_role_address,
            "vetting_status": self.vetting_status.value,
            "review_at": (
                self.review_at.isoformat() if self.review_at is not None else None
            ),
            "nda_signed": self.nda_signed,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RoleClearance:
        """Deserialize from a dictionary.

        Args:
            data: Dict with serialized RoleClearance fields.

        Returns:
            A RoleClearance instance.

        Raises:
            KeyError: If required fields are missing.
            ValueError: If enum values are invalid.
        """
        review_at = data.get("review_at")
        if isinstance(review_at, str):
            review_at = datetime.fromisoformat(review_at)
        return cls(
            role_address=data["role_address"],
            max_clearance=ConfidentialityLevel(data["max_clearance"]),
            compartments=frozenset(data.get("compartments", [])),
            granted_by_role_address=data.get("granted_by_role_address", ""),
            vetting_status=VettingStatus(data.get("vetting_status", "active")),
            review_at=review_at,
            nda_signed=data.get("nda_signed", False),
        )

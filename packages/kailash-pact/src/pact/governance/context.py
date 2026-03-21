# Copyright 2026 Terrene Foundation
# Licensed under the Apache License, Version 2.0
"""GovernanceContext -- frozen read-only governance snapshot for agent consumption.

Agents receive a GovernanceContext, NOT the GovernanceEngine. This is the
anti-self-modification defense: agents get a frozen view of their governance
state. They cannot mutate posture, envelope, clearance, or any other field.

Per governance.md Rule 2: agents operate within governance constraints and
must not be able to modify the constraints they are subject to.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from pact.build.config.schema import (
    ConfidentialityLevel,
    ConstraintEnvelopeConfig,
    TrustPostureLevel,
)
from pact.governance.clearance import RoleClearance

logger = logging.getLogger(__name__)

__all__ = ["GovernanceContext"]


@dataclass(frozen=True)
class GovernanceContext:
    """Read-only governance snapshot for agent consumption.

    Agents receive this, NOT the GovernanceEngine. This is the anti-self-modification
    defense: agents get a frozen view of their governance state.

    frozen=True means: ctx.posture = "delegated" raises FrozenInstanceError.

    Attributes:
        role_address: The D/T/R positional address of the role this context is for.
        posture: The current trust posture level.
        effective_envelope: Snapshot of the effective constraint envelope at creation time.
            None means no envelope is assigned (maximally restrictive interpretation).
        clearance: The role's clearance assignment, or None if no clearance on record.
        effective_clearance_level: Posture-capped clearance level, computed as
            min(role.max_clearance, POSTURE_CEILING[posture]). None if no clearance.
        allowed_actions: Actions permitted by the operational envelope dimension.
            Empty frozenset if no envelope.
        compartments: Knowledge compartments from the clearance assignment.
            Empty frozenset if no clearance.
        org_id: The organization ID this context belongs to.
        created_at: When this snapshot was taken.
    """

    role_address: str
    posture: TrustPostureLevel
    effective_envelope: ConstraintEnvelopeConfig | None
    clearance: RoleClearance | None
    effective_clearance_level: ConfidentialityLevel | None
    allowed_actions: frozenset[str]
    compartments: frozenset[str]
    org_id: str
    created_at: datetime

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict for transport or storage.

        Returns:
            A dict with all fields serialized to JSON-safe types.
        """
        result: dict[str, Any] = {
            "role_address": self.role_address,
            "posture": self.posture.value,
            "effective_envelope": (
                self.effective_envelope.model_dump()
                if self.effective_envelope is not None
                else None
            ),
            "clearance": _clearance_to_dict(self.clearance) if self.clearance is not None else None,
            "effective_clearance_level": (
                self.effective_clearance_level.value
                if self.effective_clearance_level is not None
                else None
            ),
            "allowed_actions": sorted(self.allowed_actions),
            "compartments": sorted(self.compartments),
            "org_id": self.org_id,
            "created_at": self.created_at.isoformat(),
        }
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GovernanceContext:
        """Deserialize from a dict.

        Args:
            data: A dict as produced by to_dict().

        Returns:
            A new GovernanceContext instance.

        Raises:
            KeyError: If required fields are missing.
            ValueError: If field values are invalid.
        """
        # Parse envelope
        envelope_data = data.get("effective_envelope")
        effective_envelope: ConstraintEnvelopeConfig | None = None
        if envelope_data is not None:
            effective_envelope = ConstraintEnvelopeConfig(**envelope_data)

        # Parse clearance
        clearance_data = data.get("clearance")
        clearance: RoleClearance | None = None
        if clearance_data is not None:
            clearance = _clearance_from_dict(clearance_data)

        # Parse effective clearance level
        eff_level_raw = data.get("effective_clearance_level")
        effective_clearance_level: ConfidentialityLevel | None = None
        if eff_level_raw is not None:
            effective_clearance_level = ConfidentialityLevel(eff_level_raw)

        # Parse created_at
        created_at_raw = data["created_at"]
        if isinstance(created_at_raw, str):
            created_at = datetime.fromisoformat(created_at_raw)
        elif isinstance(created_at_raw, datetime):
            created_at = created_at_raw
        else:
            raise ValueError(
                f"created_at must be an ISO format string or datetime, got {type(created_at_raw).__name__}"
            )

        return cls(
            role_address=data["role_address"],
            posture=TrustPostureLevel(data["posture"]),
            effective_envelope=effective_envelope,
            clearance=clearance,
            effective_clearance_level=effective_clearance_level,
            allowed_actions=frozenset(data.get("allowed_actions", [])),
            compartments=frozenset(data.get("compartments", [])),
            org_id=data["org_id"],
            created_at=created_at,
        )


# ---------------------------------------------------------------------------
# Internal helpers for RoleClearance serialization
# ---------------------------------------------------------------------------


def _clearance_to_dict(clearance: RoleClearance) -> dict[str, Any]:
    """Serialize a RoleClearance to a dict.

    RoleClearance is a dataclass(frozen=True) without to_dict(),
    so we serialize it manually here.
    """
    return {
        "role_address": clearance.role_address,
        "max_clearance": clearance.max_clearance.value,
        "compartments": sorted(clearance.compartments),
        "granted_by_role_address": clearance.granted_by_role_address,
        "vetting_status": clearance.vetting_status.value,
        "review_at": clearance.review_at.isoformat() if clearance.review_at is not None else None,
        "nda_signed": clearance.nda_signed,
    }


def _clearance_from_dict(data: dict[str, Any]) -> RoleClearance:
    """Deserialize a RoleClearance from a dict."""
    from pact.governance.clearance import VettingStatus

    review_at = data.get("review_at")
    if review_at is not None and isinstance(review_at, str):
        review_at = datetime.fromisoformat(review_at)

    return RoleClearance(
        role_address=data["role_address"],
        max_clearance=ConfidentialityLevel(data["max_clearance"]),
        compartments=frozenset(data.get("compartments", [])),
        granted_by_role_address=data.get("granted_by_role_address", ""),
        vetting_status=VettingStatus(data.get("vetting_status", "active")),
        review_at=review_at,
        nda_signed=data.get("nda_signed", False),
    )

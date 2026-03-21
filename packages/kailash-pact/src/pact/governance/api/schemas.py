# Copyright 2026 Terrene Foundation
# Licensed under the Apache License, Version 2.0
"""Pydantic request/response models for governance REST API.

All request models include validation for:
- D/T/R address format (must contain D, T, or R segments)
- ConfidentialityLevel enum membership
- TrustPostureLevel enum membership
- NaN/Inf rejection on numeric fields (per governance.md rule 4)
- Bridge type whitelist
- Non-empty action strings

Response models are plain serialization wrappers.
"""

from __future__ import annotations

import math
from typing import Any

from pydantic import BaseModel, Field, field_validator

from pact.governance.config import ConstraintEnvelopeConfig, FinancialConstraintConfig

__all__ = [
    "CheckAccessRequest",
    "CheckAccessResponse",
    "CreateBridgeRequest",
    "CreateKSPRequest",
    "GrantClearanceRequest",
    "OrgNodeResponse",
    "OrgSummaryResponse",
    "SetEnvelopeRequest",
    "VerifyActionRequest",
    "VerifyActionResponse",
]

# ---------------------------------------------------------------------------
# Valid enum value sets (lowercase, matching the str Enum .value fields)
# ---------------------------------------------------------------------------

_VALID_CLASSIFICATIONS = frozenset(
    {"public", "restricted", "confidential", "secret", "top_secret"}
)
_VALID_POSTURES = frozenset(
    {"pseudo_agent", "supervised", "shared_planning", "continuous_insight", "delegated"}
)
_VALID_BRIDGE_TYPES = frozenset({"standing", "scoped", "ad_hoc"})
_VALID_VERIFICATION_LEVELS = frozenset({"auto_approved", "flagged", "held", "blocked"})


# ---------------------------------------------------------------------------
# Shared validators
# ---------------------------------------------------------------------------


def _validate_dtr_address(v: str) -> str:
    """Validate that a string contains at least one D, T, or R segment.

    A valid D/T/R address must contain at least one segment starting with
    D, T, or R (e.g., 'D1-R1', 'D1-R1-T1-R1').

    Raises:
        ValueError: If the address does not contain any D/T/R segments or is empty.
    """
    if not v or not v.strip():
        raise ValueError("Address must not be empty")
    # Check for at least one segment that starts with D, T, or R
    segments = v.split("-")
    has_dtr = any(seg and seg[0] in ("D", "T", "R") for seg in segments)
    if not has_dtr:
        raise ValueError(
            f"Invalid D/T/R address format: '{v}'. "
            f"Address must contain at least one D, T, or R segment."
        )
    return v


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class CheckAccessRequest(BaseModel):
    """Request model for POST /api/v1/governance/check-access.

    Evaluates whether a role at a given address can access a classified
    knowledge item, considering clearance, compartments, containment,
    KSPs, and bridges.
    """

    role_address: str = Field(
        description="D/T/R positional address of the requesting role"
    )
    item_id: str = Field(description="Unique identifier of the knowledge item")
    item_classification: str = Field(
        description="Confidentiality level of the item (public through top_secret)"
    )
    item_owning_unit: str = Field(
        description="D or T prefix that owns the knowledge item"
    )
    item_compartments: list[str] = Field(
        default_factory=list,
        description="Named compartments the item belongs to",
    )
    posture: str = Field(
        description="Current trust posture level of the requesting role"
    )

    @field_validator("role_address")
    @classmethod
    def validate_role_address(cls, v: str) -> str:
        return _validate_dtr_address(v)

    @field_validator("item_classification")
    @classmethod
    def validate_classification(cls, v: str) -> str:
        if v not in _VALID_CLASSIFICATIONS:
            raise ValueError(
                f"item_classification must be one of {sorted(_VALID_CLASSIFICATIONS)}, got '{v}'"
            )
        return v

    @field_validator("posture")
    @classmethod
    def validate_posture(cls, v: str) -> str:
        if v not in _VALID_POSTURES:
            raise ValueError(
                f"posture must be one of {sorted(_VALID_POSTURES)}, got '{v}'"
            )
        return v


class VerifyActionRequest(BaseModel):
    """Request model for POST /api/v1/governance/verify-action.

    Evaluates an action against the effective constraint envelope
    for a given role address.
    """

    role_address: str = Field(description="D/T/R positional address of the acting role")
    action: str = Field(
        description="The action being performed (e.g., 'read', 'write', 'deploy')",
        min_length=1,
    )
    cost: float | None = Field(
        default=None,
        description="Cost of the action in USD for financial constraint checks",
    )
    resource: str | None = Field(
        default=None,
        description="Optional resource path for knowledge access checks",
    )
    channel: str | None = Field(
        default=None,
        description="Optional communication channel for communication constraint checks",
    )

    @field_validator("role_address")
    @classmethod
    def validate_role_address(cls, v: str) -> str:
        return _validate_dtr_address(v)

    @field_validator("cost")
    @classmethod
    def validate_cost(cls, v: float | None) -> float | None:
        """Reject NaN, Inf, and negative cost values.

        NaN bypasses all numeric comparisons (NaN > X is always False).
        Inf bypasses budget checks. Negative costs make no business sense
        and could underflow session accumulators.
        """
        if v is not None:
            if not math.isfinite(v):
                raise ValueError(
                    f"cost must be finite, got {v!r}. "
                    f"NaN/Inf values bypass governance checks."
                )
            if v < 0:
                raise ValueError(
                    f"cost must be non-negative, got {v}. "
                    f"Negative costs are not meaningful."
                )
        return v


class GrantClearanceRequest(BaseModel):
    """Request model for POST /api/v1/governance/clearances.

    Grants knowledge clearance to a role at a given D/T/R address.
    """

    role_address: str = Field(
        description="D/T/R address of the role to grant clearance to"
    )
    max_clearance: str = Field(description="Maximum confidentiality level to grant")
    compartments: list[str] = Field(
        default_factory=list,
        description="Named compartments to grant access to",
    )
    granted_by_role_address: str = Field(
        description="D/T/R address of the role granting the clearance"
    )

    @field_validator("role_address")
    @classmethod
    def validate_role_address(cls, v: str) -> str:
        return _validate_dtr_address(v)

    @field_validator("max_clearance")
    @classmethod
    def validate_max_clearance(cls, v: str) -> str:
        if v not in _VALID_CLASSIFICATIONS:
            raise ValueError(
                f"max_clearance must be one of {sorted(_VALID_CLASSIFICATIONS)}, got '{v}'"
            )
        return v

    @field_validator("granted_by_role_address")
    @classmethod
    def validate_granted_by(cls, v: str) -> str:
        return _validate_dtr_address(v)


class CreateBridgeRequest(BaseModel):
    """Request model for POST /api/v1/governance/bridges.

    Creates a Cross-Functional Bridge connecting two roles.
    """

    role_a_address: str = Field(description="First role in the bridge")
    role_b_address: str = Field(description="Second role in the bridge")
    bridge_type: str = Field(description="Bridge type: standing, scoped, or ad_hoc")
    max_classification: str = Field(
        description="Maximum confidentiality level accessible via this bridge"
    )
    bilateral: bool = Field(
        default=True,
        description="Whether both roles have mutual access (True) or A->B only (False)",
    )
    operational_scope: list[str] = Field(
        default_factory=list,
        description="Limit bridge to specific operations (empty = all)",
    )

    @field_validator("role_a_address")
    @classmethod
    def validate_role_a(cls, v: str) -> str:
        return _validate_dtr_address(v)

    @field_validator("role_b_address")
    @classmethod
    def validate_role_b(cls, v: str) -> str:
        return _validate_dtr_address(v)

    @field_validator("bridge_type")
    @classmethod
    def validate_bridge_type(cls, v: str) -> str:
        if v not in _VALID_BRIDGE_TYPES:
            raise ValueError(
                f"bridge_type must be one of {sorted(_VALID_BRIDGE_TYPES)}, got '{v}'"
            )
        return v

    @field_validator("max_classification")
    @classmethod
    def validate_max_classification(cls, v: str) -> str:
        if v not in _VALID_CLASSIFICATIONS:
            raise ValueError(
                f"max_classification must be one of {sorted(_VALID_CLASSIFICATIONS)}, got '{v}'"
            )
        return v


class CreateKSPRequest(BaseModel):
    """Request model for POST /api/v1/governance/ksps.

    Creates a Knowledge Share Policy granting cross-unit access.
    """

    source_unit_address: str = Field(description="D/T prefix sharing knowledge")
    target_unit_address: str = Field(description="D/T prefix receiving access")
    max_classification: str = Field(description="Maximum classification level shared")
    created_by_role_address: str = Field(
        description="Role that created this policy (audit trail)"
    )
    compartments: list[str] = Field(
        default_factory=list,
        description="Restrict sharing to specific compartments (empty = all)",
    )

    @field_validator("max_classification")
    @classmethod
    def validate_max_classification(cls, v: str) -> str:
        if v not in _VALID_CLASSIFICATIONS:
            raise ValueError(
                f"max_classification must be one of {sorted(_VALID_CLASSIFICATIONS)}, got '{v}'"
            )
        return v

    @field_validator("created_by_role_address")
    @classmethod
    def validate_created_by(cls, v: str) -> str:
        return _validate_dtr_address(v)


class SetEnvelopeRequest(BaseModel):
    """Request model for POST /api/v1/governance/envelopes.

    Sets a role envelope with constraint dimensions.
    """

    defining_role_address: str = Field(
        description="D/T/R address of the role defining the envelope"
    )
    target_role_address: str = Field(
        description="D/T/R address of the role this envelope applies to"
    )
    envelope_id: str = Field(description="Unique identifier for this envelope")
    constraints: dict[str, Any] = Field(
        description=(
            "Constraint envelope configuration with dimension keys: "
            "financial, operational, temporal, data_access, communication"
        )
    )

    @field_validator("defining_role_address")
    @classmethod
    def validate_defining_address(cls, v: str) -> str:
        return _validate_dtr_address(v)

    @field_validator("target_role_address")
    @classmethod
    def validate_target_address(cls, v: str) -> str:
        return _validate_dtr_address(v)

    @field_validator("constraints")
    @classmethod
    def validate_constraints(cls, v: dict[str, Any]) -> dict[str, Any]:
        """Pre-validate constraints by attempting to construct Pydantic models.

        This catches NaN/Inf in financial fields and invalid configs before
        they reach the governance engine. We explicitly check numeric fields
        for NaN/Inf BEFORE delegating to Pydantic, because Pydantic's ge=0
        catches NaN with a less informative error message.
        """
        if "financial" in v and v["financial"] is not None:
            fin = v["financial"]
            # Explicit NaN/Inf check on all numeric fields before Pydantic validation
            _FINANCIAL_NUMERIC_FIELDS = (
                "max_spend_usd",
                "api_cost_budget_usd",
                "requires_approval_above_usd",
            )
            for field_name in _FINANCIAL_NUMERIC_FIELDS:
                val = fin.get(field_name)
                if val is not None and isinstance(val, (int, float)):
                    if not math.isfinite(val):
                        raise ValueError(
                            f"constraints.{field_name} must be finite, got {val!r}. "
                            f"NaN/Inf values bypass governance checks."
                        )
            # Validate remaining fields via the Pydantic model
            FinancialConstraintConfig(**fin)
        return v


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class CheckAccessResponse(BaseModel):
    """Response model for POST /api/v1/governance/check-access."""

    allowed: bool = Field(description="Whether access is granted")
    reason: str = Field(description="Human-readable explanation of the decision")
    step_failed: int | None = Field(
        default=None,
        description="Which step (1-5) denied access, or null if allowed",
    )
    audit_details: dict[str, Any] = Field(
        default_factory=dict,
        description="Structured details for audit logging",
    )


class VerifyActionResponse(BaseModel):
    """Response model for POST /api/v1/governance/verify-action."""

    level: str = Field(description="Verification gradient level")
    allowed: bool = Field(description="Whether the action is permitted")
    reason: str = Field(description="Human-readable explanation")
    role_address: str = Field(description="The role that requested the action")
    action: str = Field(description="The action that was evaluated")

    @field_validator("level")
    @classmethod
    def validate_level(cls, v: str) -> str:
        if v not in _VALID_VERIFICATION_LEVELS:
            raise ValueError(
                f"level must be one of {sorted(_VALID_VERIFICATION_LEVELS)}, got '{v}'"
            )
        return v


class OrgSummaryResponse(BaseModel):
    """Response model for GET /api/v1/governance/org."""

    org_id: str = Field(description="Organization identifier")
    name: str = Field(description="Organization name")
    department_count: int = Field(description="Number of departments")
    team_count: int = Field(description="Number of teams")
    role_count: int = Field(description="Number of roles")
    total_nodes: int = Field(description="Total number of nodes in the org tree")


class OrgNodeResponse(BaseModel):
    """Response model for GET /api/v1/governance/org/nodes/{address}."""

    address: str = Field(description="Positional D/T/R address")
    name: str = Field(description="Human-readable node name")
    node_type: str = Field(description="Node type: D, T, or R")
    parent_address: str | None = Field(
        default=None,
        description="Parent node address, or null for root",
    )
    is_vacant: bool = Field(default=False, description="Whether the role is vacant")
    children: list[str] = Field(
        default_factory=list,
        description="Addresses of direct child nodes",
    )

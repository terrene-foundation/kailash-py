# Copyright 2026 Terrene Foundation
# Licensed under the Apache License, Version 2.0
"""PACT governance audit -- maps PACT actions to EATP Audit Anchors.

Records all governance-layer decisions (access grants/denials, envelope
changes, clearance modifications) into the audit chain for compliance
review and forensic analysis.

Per thesis Section 5.7 normative mapping, every governance action maps
to one of 10 PactAuditAction types, which are recorded as EATP Audit
Anchors with structured details.
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)

__all__ = ["PactAuditAction", "create_pact_audit_details"]


class PactAuditAction(str, Enum):
    """PACT governance action types for EATP audit anchors.

    Per thesis Section 5.7 normative mapping. Each action type maps
    to a specific governance operation that must be recorded in the
    audit chain.
    """

    ENVELOPE_CREATED = "envelope_created"
    ENVELOPE_MODIFIED = "envelope_modified"
    CLEARANCE_GRANTED = "clearance_granted"
    CLEARANCE_REVOKED = "clearance_revoked"
    BARRIER_ENFORCED = "barrier_enforced"
    KSP_CREATED = "ksp_created"
    KSP_REVOKED = "ksp_revoked"
    BRIDGE_ESTABLISHED = "bridge_established"
    BRIDGE_REVOKED = "bridge_revoked"
    ADDRESS_COMPUTED = "address_computed"


def create_pact_audit_details(
    action: PactAuditAction,
    *,
    role_address: str = "",
    target_address: str = "",
    reason: str = "",
    step_failed: int | None = None,
    **extra: Any,
) -> dict[str, Any]:
    """Create audit details dict for a PACT governance action.

    Produces a structured details dictionary suitable for inclusion in an
    EATP AuditAnchor's metadata field. Optional fields are only included
    when they have non-empty/non-None values to keep audit records clean.

    Args:
        action: The PactAuditAction being recorded.
        role_address: The D/T/R address of the role performing the action.
        target_address: The D/T/R address of the target (if applicable).
        reason: Human-readable reason for the action.
        step_failed: For BARRIER_ENFORCED, which access enforcement step
            (1-5) denied access.
        **extra: Additional key-value pairs to include in the details dict.

    Returns:
        A dict with structured audit details. Always includes pact_action
        and role_address. Other fields are included only when non-empty.
    """
    details: dict[str, Any] = {
        "pact_action": action.value,
        "role_address": role_address,
    }
    if target_address:
        details["target_address"] = target_address
    if reason:
        details["reason"] = reason
    if step_failed is not None:
        details["step_failed"] = step_failed
    details.update(extra)
    return details

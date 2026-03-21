# Copyright 2026 Terrene Foundation
# Licensed under the Apache License, Version 2.0
"""Access enforcement -- 5-step algorithm combining addresses, clearance, and bridges.

Implements the PACT access enforcement algorithm:
    Step 1: Resolve role clearance (fail if missing or non-ACTIVE vetting)
    Step 2: Classification check (effective clearance >= item classification)
    Step 3: Compartment check (SECRET/TOP_SECRET: role must hold all item compartments)
    Step 4: Containment check (5 sub-paths):
        4a: Same unit -> ALLOW
        4b: Downward (role address is prefix of item owner) -> ALLOW
        4c: T-inherits-D (role in T, item in parent D) -> ALLOW
        4d: KSP exists -> ALLOW up to KSP max_classification
        4e: Bridge exists -> ALLOW up to bridge max_classification
    Step 5: No access path found -> DENY (fail-closed)

DEFAULT IS DENY. This is fail-closed by design.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from pact.build.config.schema import ConfidentialityLevel, TrustPostureLevel
from pact.governance.clearance import (
    RoleClearance,
    VettingStatus,
    _CLEARANCE_ORDER,
    effective_clearance,
)
from pact.governance.compilation import CompiledOrg
from pact.governance.knowledge import KnowledgeItem

logger = logging.getLogger(__name__)

__all__ = [
    "AccessDecision",
    "KnowledgeSharePolicy",
    "PactBridge",
    "can_access",
]


# ---------------------------------------------------------------------------
# TODO-2003: KnowledgeSharePolicy
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class KnowledgeSharePolicy:
    """A policy granting one organizational unit read access to another's knowledge.

    KSPs are directional: source_unit shares knowledge WITH target_unit.
    The max_classification caps what classification level may be shared.

    Attributes:
        id: Unique policy identifier.
        source_unit_address: D/T prefix sharing knowledge.
        target_unit_address: D/T prefix receiving access.
        max_classification: Maximum classification level shared.
        compartments: Restrict sharing to specific compartments (empty = all).
        created_by_role_address: Role that created this policy (audit trail).
        active: Whether this policy is currently active.
        expires_at: When this policy expires (None = no expiry).
    """

    id: str
    source_unit_address: str  # D/T prefix sharing knowledge
    target_unit_address: str  # D/T prefix receiving access
    max_classification: ConfidentialityLevel
    compartments: frozenset[str] = field(default_factory=frozenset)
    created_by_role_address: str = ""
    active: bool = True
    expires_at: datetime | None = None


# ---------------------------------------------------------------------------
# TODO-2004: PactBridge
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PactBridge:
    """A Cross-Functional Bridge connecting two roles across organizational boundaries.

    Bridges grant role-level access paths. A Standing bridge is permanent,
    a Scoped bridge is limited to specific operations, and an Ad-Hoc bridge
    is temporary.

    When bilateral=True, both roles can access each other's unit data.
    When bilateral=False, only role_a can access role_b's unit data
    (unilateral: A reads B, but B cannot read A).

    Attributes:
        id: Unique bridge identifier.
        role_a_address: First role in the bridge.
        role_b_address: Second role in the bridge.
        bridge_type: One of "standing", "scoped", "ad_hoc".
        max_classification: Maximum classification accessible via this bridge.
        operational_scope: Limit bridge to specific operations (empty = all).
        bilateral: Whether both roles have mutual access.
        expires_at: When this bridge expires (None = no expiry).
        active: Whether this bridge is currently active.
    """

    id: str
    role_a_address: str
    role_b_address: str
    bridge_type: str  # "standing", "scoped", "ad_hoc"
    max_classification: ConfidentialityLevel
    operational_scope: tuple[str, ...] = ()
    bilateral: bool = True
    expires_at: datetime | None = None
    active: bool = True


# ---------------------------------------------------------------------------
# TODO-2006: AccessDecision
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AccessDecision:
    """The result of a can_access() evaluation.

    Attributes:
        allowed: Whether access is granted.
        reason: Human-readable explanation of the decision.
        step_failed: Which step (1-5) denied access, or None if allowed.
        audit_details: Structured details for audit logging.
        valid_until: When this access decision expires, based on the
            minimum expiry of any KSP or bridge that granted access.
            None means no expiry (structural access or permanent policy).
            Only set for ALLOW decisions via KSP or bridge paths.
    """

    allowed: bool
    reason: str
    step_failed: int | None = None  # 1-5, or None if allowed
    audit_details: dict[str, Any] = field(default_factory=dict)
    valid_until: datetime | None = None


# ---------------------------------------------------------------------------
# TODO-2005: Knowledge cascade helper functions
# ---------------------------------------------------------------------------


def _get_containment_unit(role_address: str, compiled_org: CompiledOrg) -> str | None:
    """Find the nearest D or T ancestor for a role address.

    Walks backward through the address segments to find the most specific
    D or T unit the role belongs to.

    For example:
        D1-R1-D2-R1-T1-R1 -> "D1-R1-D2-R1-T1" (the team)
        D1-R1-D2-R1 -> "D1-R1-D2" (the department)
        D1-R1 -> "D1" (the top department)
        R1 -> None (standalone role, no containment unit)
    """
    parts = role_address.split("-")
    # Walk backward to find the last D or T segment
    for i in range(len(parts) - 1, -1, -1):
        seg = parts[i]
        if seg and seg[0] in ("D", "T"):
            return "-".join(parts[: i + 1])
    return None


def _is_same_unit(
    role_address: str,
    item_owning_address: str,
    compiled_org: CompiledOrg,
) -> bool:
    """Check if the role is in the same organizational unit as the item owner.

    A role is in the same unit if its containment unit (nearest D or T ancestor)
    matches the item's owning unit address or is a prefix match.

    Args:
        role_address: The D/T/R address of the requesting role.
        item_owning_address: The D/T address that owns the knowledge item.
        compiled_org: The compiled organization for structural lookups.

    Returns:
        True if the role is within the item's owning unit.
    """
    role_unit = _get_containment_unit(role_address, compiled_org)
    if role_unit is None:
        return False

    # Exact match: role's containment unit is the item's owning unit
    if role_unit == item_owning_address:
        return True

    # The role's unit is a child of the item's owning unit AND
    # the role address starts with the item owner (structural containment)
    if role_unit.startswith(item_owning_address + "-"):
        return True

    return False


def _is_downward(role_address: str, item_owning_address: str) -> bool:
    """Check if the role address is an ancestor of the item owning address.

    A role at D1-R1 has downward visibility to everything under D1-R1-*,
    including D1-R1-T1, D1-R1-D2, etc.

    Args:
        role_address: The D/T/R address of the requesting role.
        item_owning_address: The D/T address that owns the knowledge item.

    Returns:
        True if the role address is a proper prefix of the item owner address.
    """
    # role_address must be a prefix of item_owning_address
    # e.g., "D1-R1" is a prefix of "D1-R1-T1" or "D1-R1-D2"
    if item_owning_address.startswith(role_address + "-"):
        return True
    return False


def _t_inherits_d(
    role_address: str,
    item_owning_address: str,
    compiled_org: CompiledOrg,
) -> bool:
    """Check if a role in a Team (T) can access its parent Department (D) data.

    T-inherits-D: roles in a team inherit read access to data owned by
    the department that contains the team.

    For example, if role is at D1-R1-D2-R1-T1-R1 (in team T1 under dept D2),
    and the item is owned by D1-R1-D2 (dept D2), then the role inherits access
    because T1 is contained within D2.

    Additionally, the role might be deeply nested. We walk up the role's ancestry
    to find any D prefix that matches the item's owning address.

    Args:
        role_address: The D/T/R address of the requesting role.
        item_owning_address: The D/T address that owns the knowledge item.
        compiled_org: The compiled organization for structural lookups.

    Returns:
        True if the role is in a team that is a descendant of the item's owning
        department, or if any ancestor D/T of the role matches the item owner.
    """
    # Walk up the role's address, looking for the item owner as an ancestor
    parts = role_address.split("-")
    for i in range(len(parts)):
        prefix = "-".join(parts[: i + 1])
        if prefix == item_owning_address:
            return True
    return False


# ---------------------------------------------------------------------------
# TODO-2006: The 5-step access enforcement algorithm
# ---------------------------------------------------------------------------


def can_access(
    role_address: str,
    knowledge_item: KnowledgeItem,
    posture: TrustPostureLevel,
    compiled_org: CompiledOrg,
    clearances: dict[str, RoleClearance],  # address -> clearance
    ksps: list[KnowledgeSharePolicy],
    bridges: list[PactBridge],
) -> AccessDecision:
    """5-step access enforcement algorithm.

    Step 1: Resolve role clearance (must exist and be ACTIVE)
    Step 2: Classification check (effective clearance >= item classification)
    Step 3: Compartment check (SECRET/TOP_SECRET: role must have all item compartments)
    Step 4: Containment check (5 sub-steps):
        4a: Same unit -> ALLOW
        4b: Downward (role address is prefix of item owner) -> ALLOW
        4c: T-inherits-D (role in T, item in parent D) -> ALLOW
        4d: KSP exists -> ALLOW up to KSP max_classification
        4e: Bridge exists -> ALLOW up to bridge max_classification
    Step 5: No access path -> DENY

    DEFAULT IS DENY. This is fail-closed.

    Args:
        role_address: The D/T/R address of the requesting role.
        knowledge_item: The knowledge item being accessed.
        posture: The current trust posture level of the role.
        compiled_org: The compiled organization structure.
        clearances: Map of role addresses to their clearance assignments.
        ksps: All active Knowledge Share Policies.
        bridges: All active Cross-Functional Bridges.

    Returns:
        An AccessDecision indicating allow/deny with reason and audit details.
    """
    item = knowledge_item

    # --- Step 1: Resolve role clearance ---
    role_clearance = clearances.get(role_address)
    if role_clearance is None:
        logger.warning(
            "Access denied (step 1): no clearance found for role_address=%s",
            role_address,
        )
        return AccessDecision(
            allowed=False,
            reason=f"No clearance found for role at address '{role_address}'",
            step_failed=1,
            audit_details={
                "role_address": role_address,
                "item_id": item.item_id,
                "step": 1,
                "detail": "missing_clearance",
            },
        )

    # Check vetting status -- only ACTIVE clearances are valid
    if role_clearance.vetting_status != VettingStatus.ACTIVE:
        logger.warning(
            "Access denied (step 1): vetting status is %s for role_address=%s",
            role_clearance.vetting_status.value,
            role_address,
        )
        return AccessDecision(
            allowed=False,
            reason=(
                f"Clearance vetting status is '{role_clearance.vetting_status.value}' "
                f"for role at '{role_address}'; only ACTIVE clearances grant access"
            ),
            step_failed=1,
            audit_details={
                "role_address": role_address,
                "item_id": item.item_id,
                "step": 1,
                "detail": "vetting_not_active",
                "vetting_status": role_clearance.vetting_status.value,
            },
        )

    # --- Step 2: Classification check ---
    eff_clearance = effective_clearance(role_clearance, posture)
    eff_level = _CLEARANCE_ORDER[eff_clearance]
    item_level = _CLEARANCE_ORDER[item.classification]

    if eff_level < item_level:
        logger.info(
            "Access denied (step 2): effective_clearance=%s < item_classification=%s "
            "for role_address=%s, item_id=%s",
            eff_clearance.value,
            item.classification.value,
            role_address,
            item.item_id,
        )
        return AccessDecision(
            allowed=False,
            reason=(
                f"Effective clearance '{eff_clearance.value}' is below item "
                f"classification '{item.classification.value}'"
            ),
            step_failed=2,
            audit_details={
                "role_address": role_address,
                "item_id": item.item_id,
                "step": 2,
                "effective_clearance": eff_clearance.value,
                "item_classification": item.classification.value,
                "posture": posture.value,
                "role_max_clearance": role_clearance.max_clearance.value,
            },
        )

    # --- Step 3: Compartment check (SECRET and TOP_SECRET only) ---
    if item_level >= _CLEARANCE_ORDER[ConfidentialityLevel.SECRET]:
        if item.compartments:
            missing = item.compartments - role_clearance.compartments
            if missing:
                logger.info(
                    "Access denied (step 3): missing compartments %s for role_address=%s, "
                    "item_id=%s",
                    missing,
                    role_address,
                    item.item_id,
                )
                return AccessDecision(
                    allowed=False,
                    reason=(
                        f"Missing compartments: {sorted(missing)}. "
                        f"Role has {sorted(role_clearance.compartments)}, "
                        f"item requires {sorted(item.compartments)}"
                    ),
                    step_failed=3,
                    audit_details={
                        "role_address": role_address,
                        "item_id": item.item_id,
                        "step": 3,
                        "missing_compartments": sorted(missing),
                        "role_compartments": sorted(role_clearance.compartments),
                        "item_compartments": sorted(item.compartments),
                    },
                )

    # --- Step 4: Containment check ---

    # Step 4a: Same unit
    if _is_same_unit(role_address, item.owning_unit_address, compiled_org):
        logger.debug(
            "Access allowed (step 4a): same unit — role_address=%s, " "item_owner=%s",
            role_address,
            item.owning_unit_address,
        )
        return AccessDecision(
            allowed=True,
            reason=f"Same unit access: role is within '{item.owning_unit_address}'",
            audit_details={
                "role_address": role_address,
                "item_id": item.item_id,
                "step": "4a",
                "access_path": "same_unit",
            },
        )

    # Step 4b: Downward (role address is prefix of item owner)
    if _is_downward(role_address, item.owning_unit_address):
        logger.debug(
            "Access allowed (step 4b): downward visibility — role_address=%s, " "item_owner=%s",
            role_address,
            item.owning_unit_address,
        )
        return AccessDecision(
            allowed=True,
            reason=(
                f"Downward visibility: role at '{role_address}' is ancestor of "
                f"item owner '{item.owning_unit_address}'"
            ),
            audit_details={
                "role_address": role_address,
                "item_id": item.item_id,
                "step": "4b",
                "access_path": "downward",
            },
        )

    # Step 4c: T-inherits-D (role in T can access parent D's data)
    if _t_inherits_d(role_address, item.owning_unit_address, compiled_org):
        logger.debug(
            "Access allowed (step 4c): T-inherits-D — role_address=%s, " "item_owner=%s",
            role_address,
            item.owning_unit_address,
        )
        return AccessDecision(
            allowed=True,
            reason=(
                f"T-inherits-D: role at '{role_address}' inherits access to "
                f"data owned by ancestor unit '{item.owning_unit_address}'"
            ),
            audit_details={
                "role_address": role_address,
                "item_id": item.item_id,
                "step": "4c",
                "access_path": "t_inherits_d",
            },
        )

    # Step 4d: KSP check
    ksp_decision = _check_ksps(role_address, item, compiled_org, ksps)
    if ksp_decision is not None:
        return ksp_decision

    # Step 4e: Bridge check
    bridge_decision = _check_bridges(role_address, item, compiled_org, bridges)
    if bridge_decision is not None:
        return bridge_decision

    # --- Step 5: No access path found -> DENY ---
    logger.info(
        "Access denied (step 5): no access path found — role_address=%s, "
        "item_id=%s, item_owner=%s",
        role_address,
        item.item_id,
        item.owning_unit_address,
    )
    return AccessDecision(
        allowed=False,
        reason=(
            f"No access path found: role at '{role_address}' has no structural, "
            f"KSP, or bridge path to data owned by '{item.owning_unit_address}'"
        ),
        step_failed=5,
        audit_details={
            "role_address": role_address,
            "item_id": item.item_id,
            "step": 5,
            "detail": "no_access_path",
            "item_owner": item.owning_unit_address,
        },
    )


# ---------------------------------------------------------------------------
# Step 4d: KSP check helper
# ---------------------------------------------------------------------------


def _check_ksps(
    role_address: str,
    item: KnowledgeItem,
    compiled_org: CompiledOrg,
    ksps: list[KnowledgeSharePolicy],
) -> AccessDecision | None:
    """Check if any active KSP grants access.

    A KSP grants access when:
    1. The KSP is active.
    2. The KSP source_unit_address matches the item's owning_unit_address
       (source is sharing, so source must be the item owner or its ancestor).
    3. The KSP target_unit_address matches the role's containment unit
       (target receives, so target must contain the requesting role).
    4. The item's classification <= KSP max_classification.

    Returns:
        An AccessDecision(allowed=True) if a KSP grants access, or None
        if no KSP applies.
    """
    role_unit = _get_containment_unit(role_address, compiled_org)

    for ksp in ksps:
        if not ksp.active:
            continue

        # Expired KSP treated as non-existent (C1 security fix)
        if ksp.expires_at is not None:
            if ksp.expires_at < datetime.now(UTC):
                continue

        # Source must match item owner (exact or prefix)
        source_matches = (
            item.owning_unit_address == ksp.source_unit_address
            or item.owning_unit_address.startswith(ksp.source_unit_address + "-")
        )
        if not source_matches:
            continue

        # Target must contain the requesting role
        target_matches = False
        if role_unit is not None:
            target_matches = role_unit == ksp.target_unit_address or role_unit.startswith(
                ksp.target_unit_address + "-"
            )
        if not target_matches:
            # Also check if role_address itself starts with target unit
            target_matches = role_address.startswith(ksp.target_unit_address + "-")
        if not target_matches:
            continue

        # Classification cap
        ksp_level = _CLEARANCE_ORDER[ksp.max_classification]
        item_level = _CLEARANCE_ORDER[item.classification]
        if item_level > ksp_level:
            continue  # Item classification exceeds KSP limit

        logger.debug(
            "Access allowed (step 4d): KSP=%s — role_address=%s, " "item_owner=%s",
            ksp.id,
            role_address,
            item.owning_unit_address,
        )
        return AccessDecision(
            allowed=True,
            reason=(
                f"KSP '{ksp.id}' grants access: "
                f"source='{ksp.source_unit_address}' -> target='{ksp.target_unit_address}'"
            ),
            audit_details={
                "role_address": role_address,
                "item_id": item.item_id,
                "step": "4d",
                "access_path": "ksp",
                "ksp_id": ksp.id,
            },
            valid_until=ksp.expires_at,
        )

    return None


# ---------------------------------------------------------------------------
# Step 4e: Bridge check helper
# ---------------------------------------------------------------------------


def _check_bridges(
    role_address: str,
    item: KnowledgeItem,
    compiled_org: CompiledOrg,
    bridges: list[PactBridge],
) -> AccessDecision | None:
    """Check if any active bridge grants access.

    A bridge grants access when:
    1. The bridge is active.
    2. One side of the bridge matches the requesting role (or the role's
       ancestor -- a bridge to a dept head covers the entire dept).
    3. The other side of the bridge connects to the item's owning unit
       (the bridged role is within or has authority over the item owner).
    4. The item's classification <= bridge max_classification.
    5. If bilateral=False, only role_a can access role_b's data
       (A -> B direction only).

    Returns:
        An AccessDecision(allowed=True) if a bridge grants access, or None
        if no bridge applies.
    """
    for bridge in bridges:
        if not bridge.active:
            continue

        # Expired bridge treated as non-existent (C1 security fix)
        if bridge.expires_at is not None:
            if bridge.expires_at < datetime.now(UTC):
                continue

        # Determine direction: which side matches the requesting role,
        # and which side connects to the item owner?
        direction = _bridge_direction(role_address, item.owning_unit_address, bridge, compiled_org)
        if direction is None:
            continue

        requesting_side, item_side, is_a_to_b = direction

        # If unilateral (bilateral=False), only A->B direction is allowed
        # A->B means role_a is the one accessing role_b's data
        # So the requesting role must match role_a
        if not bridge.bilateral and not is_a_to_b:
            continue

        # Classification cap
        bridge_level = _CLEARANCE_ORDER[bridge.max_classification]
        item_level = _CLEARANCE_ORDER[item.classification]
        if item_level > bridge_level:
            continue

        logger.debug(
            "Access allowed (step 4e): bridge=%s — role_address=%s, " "item_owner=%s",
            bridge.id,
            role_address,
            item.owning_unit_address,
        )
        return AccessDecision(
            allowed=True,
            reason=(
                f"Bridge '{bridge.id}' ({bridge.bridge_type}) grants access: "
                f"'{requesting_side}' <-> '{item_side}'"
            ),
            audit_details={
                "role_address": role_address,
                "item_id": item.item_id,
                "step": "4e",
                "access_path": "bridge",
                "bridge_id": bridge.id,
                "bridge_type": bridge.bridge_type,
            },
            valid_until=bridge.expires_at,
        )

    return None


def _bridge_direction(
    role_address: str,
    item_owner: str,
    bridge: PactBridge,
    compiled_org: CompiledOrg,
) -> tuple[str, str, bool] | None:
    """Determine if a bridge connects the requesting role to the item owner.

    Returns:
        A tuple (requesting_side, item_side, is_a_to_b) if the bridge connects
        the role to the item, or None if the bridge does not apply.

        is_a_to_b is True when the requesting role is on the A side and the
        item owner is on the B side. This matters for unilateral bridges.
    """
    role_a = bridge.role_a_address
    role_b = bridge.role_b_address

    # Check A->B direction: requesting role matches A side, item is in B's domain
    if _role_matches_bridge_side(role_address, role_a) and _item_in_bridge_domain(
        item_owner, role_b, compiled_org
    ):
        return (role_a, role_b, True)

    # Check B->A direction: requesting role matches B side, item is in A's domain
    if _role_matches_bridge_side(role_address, role_b) and _item_in_bridge_domain(
        item_owner, role_a, compiled_org
    ):
        return (role_b, role_a, False)

    return None


def _role_matches_bridge_side(role_address: str, bridge_role: str) -> bool:
    """Check if the requesting role matches a bridge endpoint.

    Bridges are role-level access paths -- only the exact bridge endpoint
    role matches, not descendants. If VP Admin (D1-R1-D2-R1) has a bridge,
    the Finance Director (D1-R1-D2-R1-T2-R1) does NOT inherit that access.
    Descendant access is governed by KSPs (unit-level), not bridges (role-level).
    """
    return role_address == bridge_role


def _item_in_bridge_domain(
    item_owner: str,
    bridge_role: str,
    compiled_org: CompiledOrg,
) -> bool:
    """Check if the item owner is in the domain of a bridge role.

    The bridge role's domain includes:
    1. The role's own containment unit
    2. All descendants of the role's containment unit
    3. The role address itself and its descendants (for downward access)
    """
    # The bridge role's containment unit
    bridge_unit = _get_containment_unit(bridge_role, compiled_org)

    if bridge_unit is not None:
        # Item is in the bridge role's unit or a descendant
        if item_owner == bridge_unit or item_owner.startswith(bridge_unit + "-"):
            return True

    # Item owner is a descendant of the bridge role address
    if item_owner == bridge_role or item_owner.startswith(bridge_role + "-"):
        return True

    return False

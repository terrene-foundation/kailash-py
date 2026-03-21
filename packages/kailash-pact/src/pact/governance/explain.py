# Copyright 2026 Terrene Foundation
# Licensed under the Apache License, Version 2.0
"""Governance convenience/explain API -- human-readable traces of governance decisions.

Provides free functions for introspecting PACT governance structures:
- ``describe_address()``: human-readable description of a D/T/R address
- ``explain_envelope()``: dimension-by-dimension breakdown of effective envelope
- ``explain_access()``: step-by-step trace of the 5-step access algorithm

These functions are designed to be integrated into GovernanceEngine as methods
but are standalone so they can be used independently.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from pact.build.config.schema import ConfidentialityLevel, TrustPostureLevel
from pact.governance.access import (
    KnowledgeSharePolicy,
    PactBridge,
    can_access,
)
from pact.governance.addressing import NodeType
from pact.governance.clearance import (
    RoleClearance,
    VettingStatus,
    _CLEARANCE_ORDER,
    effective_clearance,
)
from pact.governance.compilation import CompiledOrg, OrgNode
from pact.governance.envelopes import compute_effective_envelope
from pact.governance.knowledge import KnowledgeItem

if TYPE_CHECKING:
    from pact.governance.store import EnvelopeStore

logger = logging.getLogger(__name__)

__all__ = [
    "describe_address",
    "explain_access",
    "explain_envelope",
]


# ---------------------------------------------------------------------------
# describe_address
# ---------------------------------------------------------------------------


def describe_address(address: str, compiled_org: CompiledOrg) -> str:
    """Return a human-readable description of a D/T/R positional address.

    Walks the address from leaf to root, building a path like:
        "CS Chair (CS Department > School of Engineering > Academic Affairs)"

    Args:
        address: A D/T/R positional address string (e.g., "D1-R1-D1-R1-T1-R1").
        compiled_org: The compiled organization for node lookups.

    Returns:
        A human-readable string describing the address. If the address is
        not found, returns a message indicating so.
    """
    node = compiled_org.nodes.get(address)
    if node is None:
        return f"Address '{address}' not found in organization '{compiled_org.org_id}'"

    # Build the ancestry path from leaf to root
    parts: list[str] = []
    current_addr = address

    while current_addr:
        current_node = compiled_org.nodes.get(current_addr)
        if current_node is None:
            break

        if current_node.node_type in (NodeType.DEPARTMENT, NodeType.TEAM):
            parts.append(current_node.name)

        parent = current_node.parent_address
        if parent is None:
            break
        current_addr = parent

    # The leaf node name
    role_name = node.name

    if parts:
        ancestry = " > ".join(parts)
        return f"{role_name} ({ancestry})"
    else:
        return role_name


# ---------------------------------------------------------------------------
# explain_envelope
# ---------------------------------------------------------------------------


def explain_envelope(
    role_address: str,
    compiled_org: CompiledOrg,
    envelope_store: EnvelopeStore,
    task_id: str | None = None,
) -> str:
    """Return a human-readable breakdown of the effective envelope for a role.

    Shows each ancestor's contribution to the effective envelope,
    dimension by dimension.

    Args:
        role_address: The D/T/R positional address of the target role.
        compiled_org: The compiled organization for node lookups.
        envelope_store: The store containing role and task envelopes.
        task_id: Optional task ID to include a task envelope in the computation.

    Returns:
        A multi-line string showing the envelope breakdown.
    """
    lines: list[str] = []

    # Identify the role
    node = compiled_org.nodes.get(role_address)
    if node is not None:
        lines.append(f"Envelope breakdown for {node.name} ({role_address}):")
    else:
        lines.append(f"Envelope breakdown for {role_address}:")

    # Gather ancestor envelopes
    ancestor_envelopes = envelope_store.get_ancestor_envelopes(role_address)

    if not ancestor_envelopes:
        lines.append("  No envelopes defined -- maximally permissive (unconstrained).")
        return "\n".join(lines)

    # Show each ancestor envelope
    lines.append("")
    lines.append("  Ancestor envelopes (from root to leaf):")
    for addr in sorted(ancestor_envelopes.keys(), key=len):
        env = ancestor_envelopes[addr]
        ancestor_node = compiled_org.nodes.get(addr)
        ancestor_name = ancestor_node.name if ancestor_node else addr

        lines.append(f"    [{addr}] {ancestor_name}:")
        lines.append(f"      Defined by: {env.defining_role_address}")
        lines.append(f"      Envelope ID: {env.id}")

        # Financial dimension
        if env.envelope.financial is not None:
            lines.append(f"      Financial: max_spend_usd={env.envelope.financial.max_spend_usd}")
            if env.envelope.financial.api_cost_budget_usd is not None:
                lines.append(
                    f"        api_cost_budget_usd={env.envelope.financial.api_cost_budget_usd}"
                )
        else:
            lines.append("      Financial: none (no financial capability)")

        # Operational dimension
        if env.envelope.operational.allowed_actions:
            lines.append(
                f"      Operational: allowed_actions={env.envelope.operational.allowed_actions}"
            )
        else:
            lines.append("      Operational: no allowed actions")

        # Temporal dimension
        if env.envelope.temporal.active_hours_start:
            lines.append(
                f"      Temporal: {env.envelope.temporal.active_hours_start}"
                f"-{env.envelope.temporal.active_hours_end}"
            )
        else:
            lines.append("      Temporal: unrestricted")

        # Data access dimension
        if env.envelope.data_access.read_paths:
            lines.append(f"      Data access: read_paths={env.envelope.data_access.read_paths}")
        else:
            lines.append("      Data access: unrestricted")

        # Communication dimension
        if env.envelope.communication.allowed_channels:
            lines.append(
                f"      Communication: channels={env.envelope.communication.allowed_channels}"
            )
        else:
            lines.append("      Communication: unrestricted")

        lines.append("")

    # Compute effective envelope
    role_envelopes = {addr: env for addr, env in ancestor_envelopes.items()}
    task_envelope = None
    if task_id is not None:
        task_envelope = envelope_store.get_active_task_envelope(role_address, task_id)

    effective = compute_effective_envelope(
        role_address=role_address,
        role_envelopes=role_envelopes,
        task_envelope=task_envelope,
    )

    if effective is not None:
        lines.append("  Effective envelope (intersection of all ancestors):")
        if effective.financial is not None:
            lines.append(f"    Financial: max_spend_usd={effective.financial.max_spend_usd}")
        else:
            lines.append("    Financial: none")
        lines.append(f"    Operational: allowed_actions={effective.operational.allowed_actions}")
        lines.append(f"    Confidentiality ceiling: {effective.confidentiality_clearance.value}")
    else:
        lines.append("  Effective envelope: none (maximally permissive)")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# explain_access
# ---------------------------------------------------------------------------


def explain_access(
    role_address: str,
    knowledge_item: KnowledgeItem,
    posture: TrustPostureLevel,
    compiled_org: CompiledOrg,
    clearances: dict[str, RoleClearance],
    ksps: list[KnowledgeSharePolicy],
    bridges: list[PactBridge],
) -> str:
    """Return a step-by-step trace of the 5-step access algorithm.

    Produces a human-readable trace showing each step's result and the
    final access decision.

    Args:
        role_address: The D/T/R address of the requesting role.
        knowledge_item: The knowledge item being accessed.
        posture: The current trust posture level.
        compiled_org: The compiled organization structure.
        clearances: Map of role addresses to clearance assignments.
        ksps: All active Knowledge Share Policies.
        bridges: All active Cross-Functional Bridges.

    Returns:
        A multi-line string showing the step-by-step access evaluation trace.
    """
    lines: list[str] = []
    item = knowledge_item

    # Header
    role_node = compiled_org.nodes.get(role_address)
    role_name = role_node.name if role_node else role_address
    lines.append(
        f"Access trace: {role_name} ({role_address}) -> "
        f"'{item.item_id}' ({item.classification.value}, "
        f"owned by {item.owning_unit_address})"
    )
    lines.append("")

    # --- Step 1: Resolve role clearance ---
    role_clearance = clearances.get(role_address)
    if role_clearance is None:
        lines.append("Step 1: Clearance check -- FAIL (no clearance found for role)")
        lines.append("")
        lines.append(f"Result: DENIED at Step 1 -- no clearance assigned to '{role_address}'")
        return "\n".join(lines)

    if role_clearance.vetting_status != VettingStatus.ACTIVE:
        lines.append(
            f"Step 1: Clearance check -- FAIL "
            f"(vetting status is '{role_clearance.vetting_status.value}', not ACTIVE)"
        )
        lines.append("")
        lines.append(f"Result: DENIED at Step 1 -- vetting status not ACTIVE")
        return "\n".join(lines)

    lines.append(
        f"Step 1: Clearance check -- PASS "
        f"(role has {role_clearance.max_clearance.value} clearance, "
        f"vetting={role_clearance.vetting_status.value})"
    )

    # --- Step 2: Classification check ---
    eff_clearance = effective_clearance(role_clearance, posture)
    eff_level = _CLEARANCE_ORDER[eff_clearance]
    item_level = _CLEARANCE_ORDER[item.classification]

    if eff_level < item_level:
        lines.append(
            f"Step 2: Classification check -- FAIL "
            f"(effective clearance={eff_clearance.value}, "
            f"item requires={item.classification.value})"
        )
        lines.append("")
        lines.append(
            f"Result: DENIED at Step 2 -- effective clearance "
            f"'{eff_clearance.value}' is below item classification "
            f"'{item.classification.value}'"
        )
        return "\n".join(lines)

    lines.append(
        f"Step 2: Classification check -- PASS "
        f"(effective clearance={eff_clearance.value} >= "
        f"item classification={item.classification.value})"
    )

    # --- Step 3: Compartment check ---
    if item_level >= _CLEARANCE_ORDER[ConfidentialityLevel.SECRET]:
        if item.compartments:
            missing = item.compartments - role_clearance.compartments
            if missing:
                lines.append(
                    f"Step 3: Compartment check -- FAIL "
                    f"(missing compartments: {sorted(missing)})"
                )
                lines.append("")
                lines.append(f"Result: DENIED at Step 3 -- missing compartments {sorted(missing)}")
                return "\n".join(lines)
            else:
                lines.append(
                    f"Step 3: Compartment check -- PASS "
                    f"(role has all required compartments: "
                    f"{sorted(item.compartments)})"
                )
        else:
            lines.append("Step 3: Compartment check -- SKIPPED (item has no compartments)")
    else:
        lines.append(
            f"Step 3: Compartment check -- SKIPPED "
            f"(item is {item.classification.value}, not SECRET+)"
        )

    # --- Step 4: Containment check ---
    # Run the actual access decision to determine which sub-step succeeds
    decision = can_access(
        role_address=role_address,
        knowledge_item=knowledge_item,
        posture=posture,
        compiled_org=compiled_org,
        clearances=clearances,
        ksps=ksps,
        bridges=bridges,
    )

    # Extract the access path from the decision's audit_details
    step = decision.audit_details.get("step", "")
    access_path = decision.audit_details.get("access_path", "")

    if decision.allowed:
        # Determine which sub-step of 4 granted access
        sub_step_labels = {
            "4a": "same unit",
            "4b": "downward visibility",
            "4c": "T-inherits-D",
            "4d": "KSP",
            "4e": "bridge",
        }
        step_str = str(step)
        sub_label = sub_step_labels.get(step_str, access_path)

        # Show 4a-4e checks
        for sub_id, sub_name in sub_step_labels.items():
            if sub_id == step_str:
                extra = ""
                if access_path == "ksp":
                    ksp_id = decision.audit_details.get("ksp_id", "")
                    extra = f" ({ksp_id})" if ksp_id else ""
                elif access_path == "bridge":
                    bridge_id = decision.audit_details.get("bridge_id", "")
                    extra = f" ({bridge_id})" if bridge_id else ""
                lines.append(f"Step 4{sub_id[-1]}: {sub_name} -- YES{extra}")
                break
            else:
                lines.append(f"Step 4{sub_id[-1]}: {sub_name} -- NO")

        lines.append("")
        lines.append(
            f"Result: ALLOWED via {sub_label}"
            + (f" ({decision.reason})" if decision.reason else "")
        )
    else:
        # All sub-steps failed
        lines.append("Step 4: Containment check:")
        lines.append("  4a: same unit -- NO")
        lines.append("  4b: downward visibility -- NO")
        lines.append("  4c: T-inherits-D -- NO")
        lines.append("  4d: KSP -- NO")
        lines.append("  4e: bridge -- NO")

        lines.append("")
        lines.append(f"Step 5: Result -- DENIED (no access path found)")

    return "\n".join(lines)

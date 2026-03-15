# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
EATP Vocabulary Documentation and Mapping.

Provides machine-readable vocabulary descriptions for EATP trust postures
and constraint types, along with bidirectional mapping functions between
Python enum values and EATP vocabulary identifiers.

EATP vocabulary identifiers follow the ``eatp:<namespace>:<value>``
convention:
    - Postures: ``eatp:posture:<posture_value>``
    - Constraints: ``eatp:constraint:<constraint_value>``

Adapter Scope:
    This module provides the canonical EATP vocabulary only. Adapter modules
    that bridge EATP vocabulary to external systems (e.g. CARE Platform,
    W3C Verifiable Credentials, DID specifications) belong in the CARE
    Platform or a dedicated bridge package -- they are explicitly out of
    scope for the EATP SDK itself.

Example::

    from eatp.vocabulary import posture_to_eatp, posture_from_eatp
    from eatp.postures import TrustPosture

    eatp_id = posture_to_eatp(TrustPosture.DELEGATED)
    # => "eatp:posture:delegated"

    posture = posture_from_eatp("eatp:posture:delegated")
    # => TrustPosture.DELEGATED
"""

from __future__ import annotations

from typing import Any, Dict

from eatp.chain import ConstraintType
from eatp.postures import TrustPosture

# ---------------------------------------------------------------------------
# Posture Vocabulary
# ---------------------------------------------------------------------------

POSTURE_VOCABULARY: Dict[str, Dict[str, Any]] = {
    "delegated": {
        "eatp_id": "eatp:posture:delegated",
        "autonomy_level": 5,
        "description": (
            "Agent operates with full autonomy under remote monitoring. "
            "Human oversight is asynchronous and review-based."
        ),
    },
    "continuous_insight": {
        "eatp_id": "eatp:posture:continuous_insight",
        "autonomy_level": 4,
        "description": (
            "Agent executes tasks autonomously while a human monitors in "
            "real-time. Intervention is possible but not required for each action."
        ),
    },
    "shared_planning": {
        "eatp_id": "eatp:posture:shared_planning",
        "autonomy_level": 3,
        "description": (
            "Human and agent co-plan task execution. Agent executes only "
            "plans that have been approved by the human collaborator."
        ),
    },
    "supervised": {
        "eatp_id": "eatp:posture:supervised",
        "autonomy_level": 2,
        "description": (
            "Agent proposes actions for human review. Each action requires "
            "explicit human approval before execution."
        ),
    },
    "pseudo_agent": {
        "eatp_id": "eatp:posture:pseudo_agent",
        "autonomy_level": 1,
        "description": (
            "Agent serves as an interface only. All reasoning and "
            "decision-making is performed by a human operator."
        ),
    },
}
"""Machine-readable vocabulary for EATP trust postures.

Each entry is keyed by the ``TrustPosture`` enum value and contains:
    - ``eatp_id``: Canonical EATP vocabulary identifier.
    - ``autonomy_level``: Integer autonomy level (1--5).
    - ``description``: Human-readable explanation of the posture.
"""

# Build reverse lookup for posture_from_eatp
_EATP_ID_TO_POSTURE: Dict[str, TrustPosture] = {
    entry["eatp_id"]: TrustPosture(posture_value)
    for posture_value, entry in POSTURE_VOCABULARY.items()
}


def posture_to_eatp(posture: TrustPosture) -> str:
    """Map a TrustPosture to its EATP vocabulary identifier.

    Args:
        posture: The trust posture to map.

    Returns:
        Canonical EATP identifier string (``eatp:posture:<value>``).
    """
    return f"eatp:posture:{posture.value}"


def posture_from_eatp(eatp_id: str) -> TrustPosture:
    """Map an EATP vocabulary identifier back to a TrustPosture.

    Args:
        eatp_id: The EATP vocabulary identifier to resolve.

    Returns:
        The corresponding ``TrustPosture`` enum member.

    Raises:
        ValueError: If the identifier does not start with ``eatp:posture:``
            or refers to an unknown posture.
    """
    if not eatp_id.startswith("eatp:posture:"):
        raise ValueError(
            f"Invalid EATP posture identifier: '{eatp_id}'. "
            f"Expected prefix 'eatp:posture:'."
        )
    result = _EATP_ID_TO_POSTURE.get(eatp_id)
    if result is None:
        posture_name = eatp_id.removeprefix("eatp:posture:")
        raise ValueError(
            f"Unknown EATP posture: '{posture_name}'. "
            f"Valid postures: {sorted(_EATP_ID_TO_POSTURE.keys())}"
        )
    return result


# ---------------------------------------------------------------------------
# Constraint Vocabulary
# ---------------------------------------------------------------------------

CONSTRAINT_VOCABULARY: Dict[str, Dict[str, Any]] = {
    "financial": {
        "eatp_id": "eatp:constraint:financial",
        "dimension": "cost_limit",
        "description": (
            "Cost and budget limits governing agent spending. "
            "Constrains the maximum financial expenditure an agent may incur."
        ),
    },
    "operational": {
        "eatp_id": "eatp:constraint:operational",
        "dimension": "resources",
        "description": (
            "Action restrictions and resource limits. Constrains which "
            "operations an agent may perform and what resources it can access."
        ),
    },
    "temporal": {
        "eatp_id": "eatp:constraint:temporal",
        "dimension": "time_window",
        "description": (
            "Time window constraints governing when agent actions are "
            "permitted. Defines valid start and end times for operations."
        ),
    },
    "data_access": {
        "eatp_id": "eatp:constraint:data_access",
        "dimension": "data_access",
        "description": (
            "Data classification and PII scope constraints. Controls which "
            "data classifications an agent may read or process."
        ),
    },
    "communication": {
        "eatp_id": "eatp:constraint:communication",
        "dimension": "communication",
        "description": (
            "External communication controls. Restricts which external "
            "endpoints or channels an agent may communicate with."
        ),
    },
    "audit_requirement": {
        "eatp_id": "eatp:constraint:audit_requirement",
        "dimension": "audit_requirement",
        "description": (
            "Cross-cutting audit requirement. When active, all agent "
            "actions must be logged to the immutable audit trail."
        ),
    },
    "reasoning_required": {
        "eatp_id": "eatp:constraint:reasoning_required",
        "dimension": "reasoning_required",
        "description": (
            "EATP v2.2 reasoning trace extension. When active, agents "
            "must include a cryptographically signed reasoning trace with "
            "every action for transparency and traceability."
        ),
    },
}
"""Machine-readable vocabulary for EATP constraint types.

Each entry is keyed by the ``ConstraintType`` enum value and contains:
    - ``eatp_id``: Canonical EATP vocabulary identifier.
    - ``dimension``: Name of the constraint dimension plugin that evaluates
      this constraint type.
    - ``description``: Human-readable explanation of the constraint.
"""

# Build reverse lookup for constraint_from_eatp
_EATP_ID_TO_CONSTRAINT: Dict[str, ConstraintType] = {
    entry["eatp_id"]: ConstraintType(ct_value)
    for ct_value, entry in CONSTRAINT_VOCABULARY.items()
}


def constraint_to_eatp(constraint_type: ConstraintType) -> str:
    """Map a ConstraintType to its EATP vocabulary identifier.

    Args:
        constraint_type: The constraint type to map.

    Returns:
        Canonical EATP identifier string (``eatp:constraint:<value>``).
    """
    return f"eatp:constraint:{constraint_type.value}"


def constraint_from_eatp(eatp_id: str) -> ConstraintType:
    """Map an EATP vocabulary identifier back to a ConstraintType.

    Args:
        eatp_id: The EATP vocabulary identifier to resolve.

    Returns:
        The corresponding ``ConstraintType`` enum member.

    Raises:
        ValueError: If the identifier does not start with ``eatp:constraint:``
            or refers to an unknown constraint type.
    """
    if not eatp_id.startswith("eatp:constraint:"):
        raise ValueError(
            f"Invalid EATP constraint identifier: '{eatp_id}'. "
            f"Expected prefix 'eatp:constraint:'."
        )
    result = _EATP_ID_TO_CONSTRAINT.get(eatp_id)
    if result is None:
        ct_name = eatp_id.removeprefix("eatp:constraint:")
        raise ValueError(
            f"Unknown EATP constraint: '{ct_name}'. "
            f"Valid constraints: {sorted(_EATP_ID_TO_CONSTRAINT.keys())}"
        )
    return result


__all__ = [
    "POSTURE_VOCABULARY",
    "CONSTRAINT_VOCABULARY",
    "posture_to_eatp",
    "posture_from_eatp",
    "constraint_to_eatp",
    "constraint_from_eatp",
]

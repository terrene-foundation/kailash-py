# Copyright 2026 Terrene Foundation
# Licensed under the Apache License, Version 2.0
"""University clearance assignments -- demonstrates clearance independent of authority.

Key demonstration:
- IRB Director (specialist, junior): SECRET clearance for 'human-subjects' compartment
- Dean of Engineering (senior): CONFIDENTIAL only (no human-subjects access)
- Disciplinary Officer: CONFIDENTIAL for 'student-records' compartment
- CS Faculty Member: RESTRICTED (standard academic)
- HR Director: CONFIDENTIAL for 'personnel' compartment

This proves that clearance is orthogonal to seniority -- a junior specialist
can hold higher clearance than a senior executive when the knowledge domain
requires it.
"""

from __future__ import annotations

import logging

from pact.build.config.schema import ConfidentialityLevel
from pact.governance.clearance import RoleClearance, VettingStatus
from pact.governance.compilation import CompiledOrg

logger = logging.getLogger(__name__)

__all__ = ["create_university_clearances"]


def create_university_clearances(compiled_org: CompiledOrg) -> dict[str, RoleClearance]:
    """Create clearance assignments for all roles in the university org.

    Args:
        compiled_org: The compiled university organization, used to validate
            that role addresses exist.

    Returns:
        Dict mapping role address to RoleClearance.

    Raises:
        KeyError: If a role address does not exist in the compiled org.
    """
    clearances: dict[str, RoleClearance] = {}

    # --- President: SECRET clearance (top executive) ---
    _add(
        clearances,
        compiled_org,
        "D1-R1",
        RoleClearance(
            role_address="D1-R1",
            max_clearance=ConfidentialityLevel.SECRET,
            nda_signed=True,
            granted_by_role_address="D1-R1",  # self-granted (root authority)
        ),
    )

    # --- Provost: CONFIDENTIAL (academic leadership) ---
    _add(
        clearances,
        compiled_org,
        "D1-R1-D1-R1",
        RoleClearance(
            role_address="D1-R1-D1-R1",
            max_clearance=ConfidentialityLevel.CONFIDENTIAL,
            granted_by_role_address="D1-R1",
        ),
    )

    # --- Dean of Engineering: CONFIDENTIAL (NO human-subjects access) ---
    _add(
        clearances,
        compiled_org,
        "D1-R1-D1-R1-D1-R1",
        RoleClearance(
            role_address="D1-R1-D1-R1-D1-R1",
            max_clearance=ConfidentialityLevel.CONFIDENTIAL,
            granted_by_role_address="D1-R1-D1-R1",
        ),
    )

    # --- CS Chair: RESTRICTED (standard academic) ---
    _add(
        clearances,
        compiled_org,
        "D1-R1-D1-R1-D1-R1-T1-R1",
        RoleClearance(
            role_address="D1-R1-D1-R1-D1-R1-T1-R1",
            max_clearance=ConfidentialityLevel.RESTRICTED,
            granted_by_role_address="D1-R1-D1-R1-D1-R1",
        ),
    )

    # --- CS Faculty Member: RESTRICTED (standard academic) ---
    _add(
        clearances,
        compiled_org,
        "D1-R1-D1-R1-D1-R1-T1-R1-R1",
        RoleClearance(
            role_address="D1-R1-D1-R1-D1-R1-T1-R1-R1",
            max_clearance=ConfidentialityLevel.RESTRICTED,
            granted_by_role_address="D1-R1-D1-R1-D1-R1-T1-R1",
        ),
    )

    # --- Dean of Medicine: CONFIDENTIAL ---
    _add(
        clearances,
        compiled_org,
        "D1-R1-D1-R1-D2-R1",
        RoleClearance(
            role_address="D1-R1-D1-R1-D2-R1",
            max_clearance=ConfidentialityLevel.CONFIDENTIAL,
            granted_by_role_address="D1-R1-D1-R1",
        ),
    )

    # --- IRB Director: SECRET + human-subjects compartment ---
    # This is the KEY demonstration: a junior specialist (IRB Director)
    # holds SECRET clearance while their organizational superior (Dean of
    # Engineering) only has CONFIDENTIAL.
    _add(
        clearances,
        compiled_org,
        "D1-R1-D1-R1-D2-R1-T1-R1",
        RoleClearance(
            role_address="D1-R1-D1-R1-D2-R1-T1-R1",
            max_clearance=ConfidentialityLevel.SECRET,
            compartments=frozenset({"human-subjects"}),
            nda_signed=True,
            granted_by_role_address="D1-R1-D1-R1-D2-R1",
        ),
    )

    # --- VP Administration: RESTRICTED ---
    _add(
        clearances,
        compiled_org,
        "D1-R1-D2-R1",
        RoleClearance(
            role_address="D1-R1-D2-R1",
            max_clearance=ConfidentialityLevel.RESTRICTED,
            granted_by_role_address="D1-R1",
        ),
    )

    # --- HR Director: CONFIDENTIAL + personnel compartment ---
    _add(
        clearances,
        compiled_org,
        "D1-R1-D2-R1-T1-R1",
        RoleClearance(
            role_address="D1-R1-D2-R1-T1-R1",
            max_clearance=ConfidentialityLevel.CONFIDENTIAL,
            compartments=frozenset({"personnel"}),
            granted_by_role_address="D1-R1-D2-R1",
        ),
    )

    # --- Finance Director: RESTRICTED ---
    _add(
        clearances,
        compiled_org,
        "D1-R1-D2-R1-T2-R1",
        RoleClearance(
            role_address="D1-R1-D2-R1-T2-R1",
            max_clearance=ConfidentialityLevel.RESTRICTED,
            granted_by_role_address="D1-R1-D2-R1",
        ),
    )

    # --- VP Student Affairs: CONFIDENTIAL ---
    _add(
        clearances,
        compiled_org,
        "D1-R1-D3-R1",
        RoleClearance(
            role_address="D1-R1-D3-R1",
            max_clearance=ConfidentialityLevel.CONFIDENTIAL,
            granted_by_role_address="D1-R1",
        ),
    )

    # --- Disciplinary Officer: CONFIDENTIAL + student-records compartment ---
    _add(
        clearances,
        compiled_org,
        "D1-R1-D3-R1-T1-R1",
        RoleClearance(
            role_address="D1-R1-D3-R1-T1-R1",
            max_clearance=ConfidentialityLevel.CONFIDENTIAL,
            compartments=frozenset({"student-records"}),
            granted_by_role_address="D1-R1-D3-R1",
        ),
    )

    return clearances


def _add(
    clearances: dict[str, RoleClearance],
    compiled_org: CompiledOrg,
    address: str,
    clearance: RoleClearance,
) -> None:
    """Add a clearance after validating the address exists in the compiled org.

    Args:
        clearances: The clearance dict to add to.
        compiled_org: The compiled org for address validation.
        address: The D/T/R address to validate.
        clearance: The RoleClearance to add.

    Raises:
        KeyError: If the address does not exist in the compiled org.
    """
    # Validate address exists -- fail-closed, no silent defaults
    compiled_org.get_node(address)
    clearances[address] = clearance

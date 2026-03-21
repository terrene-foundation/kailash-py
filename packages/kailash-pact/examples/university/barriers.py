# Copyright 2026 Terrene Foundation
# Licensed under the Apache License, Version 2.0
"""University barriers and bridges -- demonstrates architectural containment.

Information barriers prevent knowledge from flowing between organizational
units that should not share data. Bridges and KSPs create controlled
exceptions to these barriers.

Barriers:
- NO KSP between Student Affairs (D1-R1-D3) and Academic Affairs (D1-R1-D1)
  for student disciplinary records

Bridges:
- Provost <-> VP Admin (Standing, budget coordination, RESTRICTED)
- Dean of Engineering <-> Dean of Medicine (Scoped, joint research, CONFIDENTIAL,
  expires in 6 months)

KSPs:
- HR -> Academic Affairs (personnel records, RESTRICTED, one-way)
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from pact.build.config.schema import ConfidentialityLevel
from pact.governance.access import KnowledgeSharePolicy, PactBridge

logger = logging.getLogger(__name__)

__all__ = ["create_university_bridges", "create_university_ksps"]


def create_university_bridges() -> list[PactBridge]:
    """Create Cross-Functional Bridges for the university.

    Returns:
        List of PactBridge instances defining cross-divisional access paths.
    """
    return [
        # Standing Bridge: Provost -> VP Administration (budget coordination)
        # Unilateral: Provost (A) can read Admin (B) budget data,
        # but Admin descendants (Finance, HR) cannot read Academic data
        # through this bridge. Budget coordination is a leadership-level
        # read path, not a blanket data sharing agreement.
        PactBridge(
            id="bridge-provost-vpadmin",
            role_a_address="D1-R1-D1-R1",  # Provost
            role_b_address="D1-R1-D2-R1",  # VP Administration
            bridge_type="standing",
            max_classification=ConfidentialityLevel.RESTRICTED,
            bilateral=False,  # A->B only: Provost reads Admin, not reverse
        ),
        # Scoped Bridge: Dean of Engineering <-> Dean of Medicine (joint research)
        # Bilateral: both deans can read each other's CONFIDENTIAL research data
        # Expires in 6 months (scoped to a joint research initiative)
        PactBridge(
            id="bridge-eng-med-research",
            role_a_address="D1-R1-D1-R1-D1-R1",  # Dean of Engineering
            role_b_address="D1-R1-D1-R1-D2-R1",  # Dean of Medicine
            bridge_type="scoped",
            max_classification=ConfidentialityLevel.CONFIDENTIAL,
            operational_scope=("joint-research",),
            bilateral=True,
            expires_at=datetime.now(UTC) + timedelta(days=180),
        ),
    ]


def create_university_ksps() -> list[KnowledgeSharePolicy]:
    """Create Knowledge Share Policies for the university.

    Returns:
        List of KnowledgeSharePolicy instances defining one-way knowledge flows.
    """
    return [
        # KSP: Academic Affairs -> HR (personnel records, one-way)
        # HR (D1-R1-D2-R1-T1) can read personnel records from
        # Academic Affairs (D1-R1-D1) at RESTRICTED level.
        # Target is the HR team specifically — NOT all of Administration.
        # This prevents Finance (D1-R1-D2-R1-T2) from inheriting access.
        # This is one-way: HR can read Academic personnel data,
        # but Academic Affairs cannot read HR data via this KSP.
        KnowledgeSharePolicy(
            id="ksp-acad-to-hr",
            source_unit_address="D1-R1-D1",  # Academic Affairs shares
            target_unit_address="D1-R1-D2-R1-T1",  # HR team receives (not all of Admin)
            max_classification=ConfidentialityLevel.RESTRICTED,
            created_by_role_address="D1-R1",  # President authorized
            active=True,
        ),
    ]

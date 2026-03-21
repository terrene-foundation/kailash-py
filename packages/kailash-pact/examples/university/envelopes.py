# Copyright 2026 Terrene Foundation
# Licensed under the Apache License, Version 2.0
"""University envelope assignments -- demonstrates three-layer envelope model.

Envelopes define spending limits, allowed actions, and other constraints
for each role. The Dean of Engineering sets the CS Chair's envelope;
the CS Chair's effective envelope is the intersection of all ancestor
envelopes down to their position.

Key demonstration:
- President envelope: max_spend_usd=$100,000, all actions
- Dean of Engineering envelope: max_spend_usd=$50,000, subset of actions
- CS Chair envelope: max_spend_usd=$10,000, further restricted actions
- Monotonic tightening: each child is <= parent on every dimension
"""

from __future__ import annotations

import logging
from typing import Any

from pact.build.config.schema import (
    ConstraintEnvelopeConfig,
    FinancialConstraintConfig,
    OperationalConstraintConfig,
)
from pact.governance.compilation import CompiledOrg
from pact.governance.envelopes import RoleEnvelope

logger = logging.getLogger(__name__)

__all__ = ["create_university_envelopes"]


def create_university_envelopes(compiled_org: CompiledOrg) -> list[RoleEnvelope]:
    """Create envelope assignments for the university org.

    Demonstrates monotonic tightening: each child envelope is at most as
    permissive as its parent's envelope.

    Args:
        compiled_org: The compiled university organization, used to validate
            that role addresses exist.

    Returns:
        List of RoleEnvelope instances.
    """
    envelopes: list[RoleEnvelope] = []

    # --- Provost envelope (set by President) ---
    # Provost can spend up to $50,000 and perform all standard academic actions
    envelopes.append(
        RoleEnvelope(
            id="env-provost",
            defining_role_address="D1-R1",  # President
            target_role_address="D1-R1-D1-R1",  # Provost
            envelope=ConstraintEnvelopeConfig(
                id="env-provost",
                financial=FinancialConstraintConfig(
                    max_spend_usd=50000,
                    requires_approval_above_usd=20000,
                ),
                operational=OperationalConstraintConfig(
                    allowed_actions=[
                        "read",
                        "write",
                        "approve",
                        "hire",
                        "grant",
                        "revoke",
                        "review",
                    ],
                ),
            ),
        )
    )

    # --- Dean of Engineering envelope (set by Provost) ---
    # Dean can spend up to $25,000 (tighter than Provost's $50,000)
    envelopes.append(
        RoleEnvelope(
            id="env-dean-eng",
            defining_role_address="D1-R1-D1-R1",  # Provost
            target_role_address="D1-R1-D1-R1-D1-R1",  # Dean of Engineering
            envelope=ConstraintEnvelopeConfig(
                id="env-dean-eng",
                financial=FinancialConstraintConfig(
                    max_spend_usd=25000,
                    requires_approval_above_usd=10000,
                ),
                operational=OperationalConstraintConfig(
                    allowed_actions=[
                        "read",
                        "write",
                        "approve",
                        "hire",
                        "review",
                    ],
                ),
            ),
        )
    )

    # --- CS Chair envelope (set by Dean of Engineering) ---
    # CS Chair can spend up to $10,000 (tighter than Dean's $25,000)
    envelopes.append(
        RoleEnvelope(
            id="env-cs-chair",
            defining_role_address="D1-R1-D1-R1-D1-R1",  # Dean of Engineering
            target_role_address="D1-R1-D1-R1-D1-R1-T1-R1",  # CS Chair
            envelope=ConstraintEnvelopeConfig(
                id="env-cs-chair",
                financial=FinancialConstraintConfig(
                    max_spend_usd=10000,
                    requires_approval_above_usd=5000,
                ),
                operational=OperationalConstraintConfig(
                    allowed_actions=["read", "write", "approve"],
                ),
            ),
        )
    )

    # --- VP Administration envelope (set by President) ---
    envelopes.append(
        RoleEnvelope(
            id="env-vp-admin",
            defining_role_address="D1-R1",  # President
            target_role_address="D1-R1-D2-R1",  # VP Administration
            envelope=ConstraintEnvelopeConfig(
                id="env-vp-admin",
                financial=FinancialConstraintConfig(
                    max_spend_usd=75000,
                    requires_approval_above_usd=25000,
                ),
                operational=OperationalConstraintConfig(
                    allowed_actions=[
                        "read",
                        "write",
                        "approve",
                        "hire",
                        "audit",
                        "review",
                    ],
                ),
            ),
        )
    )

    # --- Finance Director envelope (set by VP Admin) ---
    envelopes.append(
        RoleEnvelope(
            id="env-finance-director",
            defining_role_address="D1-R1-D2-R1",  # VP Administration
            target_role_address="D1-R1-D2-R1-T2-R1",  # Finance Director
            envelope=ConstraintEnvelopeConfig(
                id="env-finance-director",
                financial=FinancialConstraintConfig(
                    max_spend_usd=0,  # Finance can audit but not spend
                ),
                operational=OperationalConstraintConfig(
                    allowed_actions=["read", "audit", "review"],
                ),
            ),
        )
    )

    return envelopes

# Copyright 2026 Terrene Foundation
# Licensed under the Apache License, Version 2.0
"""University example -- demonstrates all PACT concepts without domain expertise.

Organization Structure (4+ levels of D/T/R nesting):

  D1 (Office of the President)
    D1-R1 (President)
      D1-R1-D1 (Academic Affairs)
        D1-R1-D1-R1 (Provost)
          D1-R1-D1-R1-D1 (School of Engineering)
            D1-R1-D1-R1-D1-R1 (Dean of Engineering)
              D1-R1-D1-R1-D1-R1-T1 (CS Department)
                D1-R1-D1-R1-D1-R1-T1-R1 (CS Chair)
                  D1-R1-D1-R1-D1-R1-T1-R1-R1 (CS Faculty Member)
          D1-R1-D1-R1-D2 (School of Medicine)
            D1-R1-D1-R1-D2-R1 (Dean of Medicine)
              D1-R1-D1-R1-D2-R1-T1 (Research Lab)
                D1-R1-D1-R1-D2-R1-T1-R1 (IRB Director)
      D1-R1-D2 (Administration)
        D1-R1-D2-R1 (VP Administration)
          D1-R1-D2-R1-T1 (HR)
            D1-R1-D2-R1-T1-R1 (HR Director)
          D1-R1-D2-R1-T2 (Finance)
            D1-R1-D2-R1-T2-R1 (Finance Director)
      D1-R1-D3 (Student Affairs)
        D1-R1-D3-R1 (VP Student Affairs)
          D1-R1-D3-R1-T1 (Disciplinary Board)
            D1-R1-D3-R1-T1-R1 (Disciplinary Officer)
"""

from __future__ import annotations

import logging

from pact.build.config.schema import DepartmentConfig, TeamConfig
from pact.build.org.builder import OrgDefinition
from pact.governance.compilation import CompiledOrg, RoleDefinition, compile_org

logger = logging.getLogger(__name__)

__all__ = ["create_university_org"]


def create_university_org() -> tuple[CompiledOrg, OrgDefinition]:
    """Create and compile a university organizational structure.

    Returns:
        A tuple of (CompiledOrg, OrgDefinition) so callers can access both
        the compiled addresses and the original definition.
    """
    # --- Departments ---
    departments = [
        DepartmentConfig(
            department_id="d-president-office",
            name="Office of the President",
        ),
        DepartmentConfig(
            department_id="d-academic-affairs",
            name="Academic Affairs",
        ),
        DepartmentConfig(
            department_id="d-engineering",
            name="School of Engineering",
        ),
        DepartmentConfig(
            department_id="d-medicine",
            name="School of Medicine",
        ),
        DepartmentConfig(
            department_id="d-administration",
            name="Administration",
        ),
        DepartmentConfig(
            department_id="d-student-affairs",
            name="Student Affairs",
        ),
    ]

    # --- Teams ---
    teams = [
        TeamConfig(id="t-cs-dept", name="CS Department", workspace="ws-cs"),
        TeamConfig(id="t-research-lab", name="Research Lab", workspace="ws-research"),
        TeamConfig(id="t-hr", name="HR", workspace="ws-hr"),
        TeamConfig(id="t-finance", name="Finance", workspace="ws-finance"),
        TeamConfig(id="t-disciplinary", name="Disciplinary Board", workspace="ws-disciplinary"),
    ]

    # --- Roles (reports_to chains build the hierarchy) ---
    roles = [
        # Level 1: President heads the Office of the President
        RoleDefinition(
            role_id="r-president",
            name="President",
            reports_to_role_id=None,
            is_primary_for_unit="d-president-office",
        ),
        # Level 2: Provost heads Academic Affairs, reports to President
        RoleDefinition(
            role_id="r-provost",
            name="Provost",
            reports_to_role_id="r-president",
            is_primary_for_unit="d-academic-affairs",
        ),
        # Level 3: Dean of Engineering heads School of Engineering, reports to Provost
        RoleDefinition(
            role_id="r-dean-eng",
            name="Dean of Engineering",
            reports_to_role_id="r-provost",
            is_primary_for_unit="d-engineering",
        ),
        # Level 4: CS Chair heads CS Department team, reports to Dean of Engineering
        RoleDefinition(
            role_id="r-cs-chair",
            name="CS Chair",
            reports_to_role_id="r-dean-eng",
            is_primary_for_unit="t-cs-dept",
        ),
        # Level 5: CS Faculty Member (non-head role), reports to CS Chair
        RoleDefinition(
            role_id="r-cs-faculty",
            name="CS Faculty Member",
            reports_to_role_id="r-cs-chair",
        ),
        # Level 3: Dean of Medicine heads School of Medicine, reports to Provost
        RoleDefinition(
            role_id="r-dean-med",
            name="Dean of Medicine",
            reports_to_role_id="r-provost",
            is_primary_for_unit="d-medicine",
        ),
        # Level 4: IRB Director heads Research Lab, reports to Dean of Medicine
        RoleDefinition(
            role_id="r-irb-director",
            name="IRB Director",
            reports_to_role_id="r-dean-med",
            is_primary_for_unit="t-research-lab",
        ),
        # Level 2: VP Administration heads Administration, reports to President
        RoleDefinition(
            role_id="r-vp-admin",
            name="VP Administration",
            reports_to_role_id="r-president",
            is_primary_for_unit="d-administration",
        ),
        # Level 3: HR Director heads HR team, reports to VP Admin
        RoleDefinition(
            role_id="r-hr-director",
            name="HR Director",
            reports_to_role_id="r-vp-admin",
            is_primary_for_unit="t-hr",
        ),
        # Level 3: Finance Director heads Finance team, reports to VP Admin
        RoleDefinition(
            role_id="r-finance-director",
            name="Finance Director",
            reports_to_role_id="r-vp-admin",
            is_primary_for_unit="t-finance",
        ),
        # Level 2: VP Student Affairs heads Student Affairs, reports to President
        RoleDefinition(
            role_id="r-vp-student-affairs",
            name="VP Student Affairs",
            reports_to_role_id="r-president",
            is_primary_for_unit="d-student-affairs",
        ),
        # Level 3: Disciplinary Officer heads Disciplinary Board, reports to VP Student Affairs
        RoleDefinition(
            role_id="r-disciplinary-officer",
            name="Disciplinary Officer",
            reports_to_role_id="r-vp-student-affairs",
            is_primary_for_unit="t-disciplinary",
        ),
    ]

    org = OrgDefinition(
        org_id="university-001",
        name="State University",
        departments=departments,
        teams=teams,
        roles=roles,
    )

    compiled = compile_org(org)

    logger.info(
        "University org compiled: %d nodes, addresses: %s",
        len(compiled.nodes),
        sorted(compiled.nodes.keys()),
    )

    return compiled, org

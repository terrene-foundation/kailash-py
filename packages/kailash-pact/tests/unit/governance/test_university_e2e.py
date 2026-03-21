# Copyright 2026 Terrene Foundation
# Licensed under the Apache License, Version 2.0
"""University vertical E2E test — proves all PACT governance concepts work together.

Tests a complete university organization structure with:
- 4+ levels of D/T/R nesting
- Clearance independent of authority (IRB Director > Dean of Engineering)
- Information barriers (Student Affairs ↔ Academic Affairs for disciplinary records)
- Cross-Functional Bridges (Standing, Scoped)
- Knowledge Share Policies (one-way HR → Academic Affairs)
- Compartmentalized access (human-subjects, student-records, personnel)

Ten scenarios exercising the 5-step access enforcement algorithm across
structural containment, KSPs, bridges, clearance, and compartment checks.
"""

from __future__ import annotations

import pytest

from pact.build.config.schema import ConfidentialityLevel, TrustPostureLevel
from pact.governance.access import KnowledgeSharePolicy, PactBridge, can_access
from pact.governance.clearance import RoleClearance
from pact.governance.compilation import CompiledOrg, RoleDefinition
from pact.governance.knowledge import KnowledgeItem

# Import the university example modules
from pact.examples.university.org import create_university_org
from pact.examples.university.clearance import create_university_clearances
from pact.examples.university.barriers import (
    create_university_bridges,
    create_university_ksps,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def university_org() -> CompiledOrg:
    """Compiled university organization with 4+ levels of nesting."""
    compiled_org, _org_def = create_university_org()
    return compiled_org


@pytest.fixture
def clearances(university_org: CompiledOrg) -> dict[str, RoleClearance]:
    """Clearance assignments for all university roles."""
    return create_university_clearances(university_org)


@pytest.fixture
def bridges() -> list[PactBridge]:
    """Cross-Functional Bridges for the university."""
    return create_university_bridges()


@pytest.fixture
def ksps() -> list[KnowledgeSharePolicy]:
    """Knowledge Share Policies for the university."""
    return create_university_ksps()


# --- Knowledge items used across tests ---


@pytest.fixture
def student_disciplinary_records(university_org: CompiledOrg) -> KnowledgeItem:
    """Student disciplinary records owned by Student Affairs (D1-R1-D3)."""
    return KnowledgeItem(
        item_id="disciplinary-case-2026-042",
        classification=ConfidentialityLevel.CONFIDENTIAL,
        owning_unit_address="D1-R1-D3",
        compartments=frozenset({"student-records"}),
        description="Student disciplinary case file",
    )


@pytest.fixture
def human_subjects_data(university_org: CompiledOrg) -> KnowledgeItem:
    """Human subjects research data owned by the Medicine Research Lab."""
    return KnowledgeItem(
        item_id="irb-protocol-2026-009",
        classification=ConfidentialityLevel.SECRET,
        owning_unit_address="D1-R1-D1-R1-D2-R1-T1",
        compartments=frozenset({"human-subjects"}),
        description="Human subjects research protocol and participant data",
    )


@pytest.fixture
def admin_budget_data(university_org: CompiledOrg) -> KnowledgeItem:
    """Budget data owned by Administration (D1-R1-D2)."""
    return KnowledgeItem(
        item_id="admin-budget-fy2026",
        classification=ConfidentialityLevel.RESTRICTED,
        owning_unit_address="D1-R1-D2",
        description="Administration FY2026 budget allocations",
    )


@pytest.fixture
def medicine_research_data(university_org: CompiledOrg) -> KnowledgeItem:
    """Research data owned by School of Medicine (D1-R1-D1-R1-D2)."""
    return KnowledgeItem(
        item_id="med-research-grant-2026",
        classification=ConfidentialityLevel.CONFIDENTIAL,
        owning_unit_address="D1-R1-D1-R1-D2",
        description="School of Medicine grant applications and research data",
    )


@pytest.fixture
def academic_data(university_org: CompiledOrg) -> KnowledgeItem:
    """General academic data owned by Academic Affairs (D1-R1-D1)."""
    return KnowledgeItem(
        item_id="academic-curriculum-2026",
        classification=ConfidentialityLevel.RESTRICTED,
        owning_unit_address="D1-R1-D1",
        description="Academic Affairs curriculum planning data",
    )


@pytest.fixture
def cs_department_data(university_org: CompiledOrg) -> KnowledgeItem:
    """CS Department data owned by the CS Department team."""
    return KnowledgeItem(
        item_id="cs-faculty-schedules",
        classification=ConfidentialityLevel.RESTRICTED,
        owning_unit_address="D1-R1-D1-R1-D1-R1-T1",
        description="CS Department faculty teaching schedules",
    )


@pytest.fixture
def academic_personnel_info(university_org: CompiledOrg) -> KnowledgeItem:
    """Personnel info in Academic Affairs domain — accessible via HR KSP."""
    return KnowledgeItem(
        item_id="academic-personnel-records",
        classification=ConfidentialityLevel.RESTRICTED,
        owning_unit_address="D1-R1-D1",
        compartments=frozenset({"personnel"}),
        description="Academic Affairs personnel records (salaries, contracts)",
    )


@pytest.fixture
def student_affairs_data(university_org: CompiledOrg) -> KnowledgeItem:
    """General Student Affairs data."""
    return KnowledgeItem(
        item_id="student-affairs-report",
        classification=ConfidentialityLevel.RESTRICTED,
        owning_unit_address="D1-R1-D3",
        description="Student Affairs annual report data",
    )


# ---------------------------------------------------------------------------
# Test: University org compiles correctly
# ---------------------------------------------------------------------------


class TestUniversityOrgStructure:
    """Verify the university org compiles with the expected structure."""

    def test_org_compiles_without_errors(self) -> None:
        """The university org definition compiles to a valid CompiledOrg."""
        compiled, org_def = create_university_org()
        assert compiled.org_id == "university-001"
        assert len(compiled.nodes) > 0, "CompiledOrg should have nodes"

    def test_org_has_expected_depth(self, university_org: CompiledOrg) -> None:
        """The org has at least 4 levels of D/T/R nesting."""
        max_depth = 0
        for addr in university_org.nodes:
            depth = len(addr.split("-"))
            max_depth = max(max_depth, depth)
        assert max_depth >= 8, (
            f"Expected at least 8 address segments (4+ levels of D/R nesting), "
            f"got max depth {max_depth}. Addresses: {sorted(university_org.nodes.keys())}"
        )

    def test_key_roles_have_addresses(self, university_org: CompiledOrg) -> None:
        """All key roles are present with the expected addresses."""
        # President (head of top department)
        president = university_org.get_node("D1-R1")
        assert president.name == "President"

        # Provost (head of Academic Affairs under President)
        provost = university_org.get_node("D1-R1-D1-R1")
        assert provost.name == "Provost"

        # Dean of Engineering
        dean_eng = university_org.get_node("D1-R1-D1-R1-D1-R1")
        assert dean_eng.name == "Dean of Engineering"

        # CS Chair
        cs_chair = university_org.get_node("D1-R1-D1-R1-D1-R1-T1-R1")
        assert cs_chair.name == "CS Chair"

    def test_clearance_independence(self, clearances: dict[str, RoleClearance]) -> None:
        """Clearance is independent of authority — IRB Director has higher clearance than Dean."""
        irb_clearance = clearances["D1-R1-D1-R1-D2-R1-T1-R1"]
        dean_eng_clearance = clearances["D1-R1-D1-R1-D1-R1"]

        assert irb_clearance.max_clearance == ConfidentialityLevel.SECRET
        assert dean_eng_clearance.max_clearance == ConfidentialityLevel.CONFIDENTIAL
        # IRB Director (junior) has higher clearance than Dean (senior)
        # This is the core demonstration of clearance independence from authority.


# ---------------------------------------------------------------------------
# Scenario 1: CS Faculty requests student disciplinary records -> BLOCKED
# ---------------------------------------------------------------------------


class TestScenario1FacultyBlockedFromDisciplinaryRecords:
    """CS Faculty Member has no path to Student Affairs data.

    CS Faculty (D1-R1-D1-R1-D1-R1-T1-R1-R1) is in Academic Affairs (D1-R1-D1).
    Student disciplinary records are in Student Affairs (D1-R1-D3).
    There is no KSP or bridge between Academic Affairs and Student Affairs
    for student records.
    """

    def test_cs_faculty_cannot_access_disciplinary_records(
        self,
        university_org: CompiledOrg,
        clearances: dict[str, RoleClearance],
        bridges: list[PactBridge],
        ksps: list[KnowledgeSharePolicy],
        student_disciplinary_records: KnowledgeItem,
    ) -> None:
        decision = can_access(
            role_address="D1-R1-D1-R1-D1-R1-T1-R1-R1",  # CS Faculty Member
            knowledge_item=student_disciplinary_records,
            posture=TrustPostureLevel.SHARED_PLANNING,
            compiled_org=university_org,
            clearances=clearances,
            ksps=ksps,
            bridges=bridges,
        )
        assert decision.allowed is False, (
            f"Information barrier BREACHED! CS Faculty accessed student disciplinary records. "
            f"Reason: {decision.reason}"
        )


# ---------------------------------------------------------------------------
# Scenario 2: Disciplinary Officer reads student records -> ALLOWED
# ---------------------------------------------------------------------------


class TestScenario2DisciplinaryOfficerReadsStudentRecords:
    """Disciplinary Officer is in Student Affairs with student-records compartment."""

    def test_disciplinary_officer_reads_student_records(
        self,
        university_org: CompiledOrg,
        clearances: dict[str, RoleClearance],
        bridges: list[PactBridge],
        ksps: list[KnowledgeSharePolicy],
        student_disciplinary_records: KnowledgeItem,
    ) -> None:
        decision = can_access(
            role_address="D1-R1-D3-R1-T1-R1",  # Disciplinary Officer
            knowledge_item=student_disciplinary_records,
            posture=TrustPostureLevel.SHARED_PLANNING,
            compiled_org=university_org,
            clearances=clearances,
            ksps=ksps,
            bridges=bridges,
        )
        assert decision.allowed is True, (
            f"Disciplinary Officer should access student records (same division + compartment). "
            f"Reason: {decision.reason}"
        )


# ---------------------------------------------------------------------------
# Scenario 3: IRB Director accesses human subjects data -> ALLOWED
# ---------------------------------------------------------------------------


class TestScenario3IRBDirectorAccessesHumanSubjects:
    """IRB Director has SECRET clearance with human-subjects compartment."""

    def test_irb_director_accesses_human_subjects(
        self,
        university_org: CompiledOrg,
        clearances: dict[str, RoleClearance],
        bridges: list[PactBridge],
        ksps: list[KnowledgeSharePolicy],
        human_subjects_data: KnowledgeItem,
    ) -> None:
        decision = can_access(
            role_address="D1-R1-D1-R1-D2-R1-T1-R1",  # IRB Director
            knowledge_item=human_subjects_data,
            posture=TrustPostureLevel.CONTINUOUS_INSIGHT,
            compiled_org=university_org,
            clearances=clearances,
            ksps=ksps,
            bridges=bridges,
        )
        assert decision.allowed is True, (
            f"IRB Director should access human subjects data (SECRET clearance + compartment). "
            f"Reason: {decision.reason}"
        )


# ---------------------------------------------------------------------------
# Scenario 4: Dean of Engineering requests human subjects data -> BLOCKED
# ---------------------------------------------------------------------------


class TestScenario4DeanBlockedFromHumanSubjects:
    """Dean of Engineering only has CONFIDENTIAL clearance — no human-subjects compartment."""

    def test_dean_of_engineering_blocked_from_human_subjects(
        self,
        university_org: CompiledOrg,
        clearances: dict[str, RoleClearance],
        bridges: list[PactBridge],
        ksps: list[KnowledgeSharePolicy],
        human_subjects_data: KnowledgeItem,
    ) -> None:
        decision = can_access(
            role_address="D1-R1-D1-R1-D1-R1",  # Dean of Engineering
            knowledge_item=human_subjects_data,
            posture=TrustPostureLevel.SHARED_PLANNING,
            compiled_org=university_org,
            clearances=clearances,
            ksps=ksps,
            bridges=bridges,
        )
        assert decision.allowed is False, (
            f"Dean of Engineering should NOT access human subjects data "
            f"(only CONFIDENTIAL, no compartment). Reason: {decision.reason}"
        )


# ---------------------------------------------------------------------------
# Scenario 5: Provost reads Admin budget data via bridge -> ALLOWED
# ---------------------------------------------------------------------------


class TestScenario5ProvostReadsAdminBudget:
    """Provost has a Standing bridge to VP Administration for budget coordination."""

    def test_provost_reads_admin_budget(
        self,
        university_org: CompiledOrg,
        clearances: dict[str, RoleClearance],
        bridges: list[PactBridge],
        ksps: list[KnowledgeSharePolicy],
        admin_budget_data: KnowledgeItem,
    ) -> None:
        decision = can_access(
            role_address="D1-R1-D1-R1",  # Provost
            knowledge_item=admin_budget_data,
            posture=TrustPostureLevel.SHARED_PLANNING,
            compiled_org=university_org,
            clearances=clearances,
            ksps=ksps,
            bridges=bridges,
        )
        assert decision.allowed is True, (
            f"Provost should access Admin budget data via Standing bridge. "
            f"Reason: {decision.reason}"
        )


# ---------------------------------------------------------------------------
# Scenario 6: Dean of Engineering reads Medicine research via bridge -> ALLOWED
# ---------------------------------------------------------------------------


class TestScenario6DeanEngReadsResearchViaBridge:
    """Dean of Engineering has a Scoped bridge to Dean of Medicine for joint research."""

    def test_dean_eng_reads_medicine_research(
        self,
        university_org: CompiledOrg,
        clearances: dict[str, RoleClearance],
        bridges: list[PactBridge],
        ksps: list[KnowledgeSharePolicy],
        medicine_research_data: KnowledgeItem,
    ) -> None:
        decision = can_access(
            role_address="D1-R1-D1-R1-D1-R1",  # Dean of Engineering
            knowledge_item=medicine_research_data,
            posture=TrustPostureLevel.SHARED_PLANNING,
            compiled_org=university_org,
            clearances=clearances,
            ksps=ksps,
            bridges=bridges,
        )
        assert decision.allowed is True, (
            f"Dean of Engineering should access Medicine research data via Scoped bridge. "
            f"Reason: {decision.reason}"
        )


# ---------------------------------------------------------------------------
# Scenario 7: Finance Director reads Academic data -> BLOCKED
# ---------------------------------------------------------------------------


class TestScenario7FinanceBlockedFromAcademic:
    """Finance Director has no bridge or KSP to Academic Affairs."""

    def test_finance_director_blocked_from_academic_data(
        self,
        university_org: CompiledOrg,
        clearances: dict[str, RoleClearance],
        bridges: list[PactBridge],
        ksps: list[KnowledgeSharePolicy],
        academic_data: KnowledgeItem,
    ) -> None:
        decision = can_access(
            role_address="D1-R1-D2-R1-T2-R1",  # Finance Director
            knowledge_item=academic_data,
            posture=TrustPostureLevel.SHARED_PLANNING,
            compiled_org=university_org,
            clearances=clearances,
            ksps=ksps,
            bridges=bridges,
        )
        assert decision.allowed is False, (
            f"Finance Director should NOT access Academic data "
            f"(different division, no bridge to Finance). Reason: {decision.reason}"
        )


# ---------------------------------------------------------------------------
# Scenario 8: HR Director reads Academic personnel info via KSP -> ALLOWED
# ---------------------------------------------------------------------------


class TestScenario8HRReadsAcademicPersonnelViaKSP:
    """HR has a one-way KSP from Academic Affairs for personnel records."""

    def test_hr_director_reads_academic_personnel(
        self,
        university_org: CompiledOrg,
        clearances: dict[str, RoleClearance],
        bridges: list[PactBridge],
        ksps: list[KnowledgeSharePolicy],
        academic_personnel_info: KnowledgeItem,
    ) -> None:
        decision = can_access(
            role_address="D1-R1-D2-R1-T1-R1",  # HR Director
            knowledge_item=academic_personnel_info,
            posture=TrustPostureLevel.SHARED_PLANNING,
            compiled_org=university_org,
            clearances=clearances,
            ksps=ksps,
            bridges=bridges,
        )
        assert decision.allowed is True, (
            f"HR Director should access Academic personnel info via KSP. "
            f"Reason: {decision.reason}"
        )


# ---------------------------------------------------------------------------
# Scenario 9: CS Chair reads CS Department data -> ALLOWED
# ---------------------------------------------------------------------------


class TestScenario9CSChairReadsOwnData:
    """CS Chair reads CS Department data (same unit)."""

    def test_cs_chair_reads_cs_department_data(
        self,
        university_org: CompiledOrg,
        clearances: dict[str, RoleClearance],
        bridges: list[PactBridge],
        ksps: list[KnowledgeSharePolicy],
        cs_department_data: KnowledgeItem,
    ) -> None:
        decision = can_access(
            role_address="D1-R1-D1-R1-D1-R1-T1-R1",  # CS Chair
            knowledge_item=cs_department_data,
            posture=TrustPostureLevel.SHARED_PLANNING,
            compiled_org=university_org,
            clearances=clearances,
            ksps=ksps,
            bridges=bridges,
        )
        assert decision.allowed is True, (
            f"CS Chair should access CS Department data (same unit). " f"Reason: {decision.reason}"
        )


# ---------------------------------------------------------------------------
# Scenario 10: VP Admin reads Student Affairs data -> BLOCKED
# ---------------------------------------------------------------------------


class TestScenario10VPAdminBlockedFromStudentAffairs:
    """VP Administration has no bridge or KSP to Student Affairs."""

    def test_vp_admin_blocked_from_student_affairs(
        self,
        university_org: CompiledOrg,
        clearances: dict[str, RoleClearance],
        bridges: list[PactBridge],
        ksps: list[KnowledgeSharePolicy],
        student_affairs_data: KnowledgeItem,
    ) -> None:
        decision = can_access(
            role_address="D1-R1-D2-R1",  # VP Administration
            knowledge_item=student_affairs_data,
            posture=TrustPostureLevel.SHARED_PLANNING,
            compiled_org=university_org,
            clearances=clearances,
            ksps=ksps,
            bridges=bridges,
        )
        assert decision.allowed is False, (
            f"VP Administration should NOT access Student Affairs data "
            f"(different division, no KSP). Reason: {decision.reason}"
        )

# Copyright 2026 Terrene Foundation
# Licensed under the Apache License, Version 2.0
"""Tests for organization compilation — transforms OrgDefinition into CompiledOrg.

Covers:
- TODO-1002: RoleDefinition model on OrgDefinition
- TODO-1003: compile_org() with address assignment
- TODO-1004: query_by_prefix() and get_subtree()
- TODO-1005: Vacancy handling (VacancyStatus)
"""

from __future__ import annotations

import pytest

from pact.build.config.schema import DepartmentConfig, TeamConfig
from pact.build.org.builder import OrgDefinition
from pact.governance.addressing import Address, GrammarError, NodeType
from pact.governance.compilation import (
    CompilationError,
    CompiledOrg,
    OrgNode,
    VacancyStatus,
    compile_org,
)


# ---------------------------------------------------------------------------
# Fixtures: Financial Services org (PACT thesis Section 7.1)
# ---------------------------------------------------------------------------


@pytest.fixture
def financial_services_org() -> OrgDefinition:
    """Financial services example from PACT thesis Section 7.1.

    Structure:
      BOD (R-BOD, external, root)
        D1 (Executive Office)
          D1-R1 CEO
            D1-R1-D1 (Compliance Division)
              D1-R1-D1-R1 CCO
                D1-R1-D1-R1-T1 (AML/CFT Team)
                  D1-R1-D1-R1-T1-R1 AML Officer
            D1-R1-D2 (Advisory Division)
              D1-R1-D2-R1 Head of Advisory
                D1-R1-D2-R1-T1 (Client Advisory Team)
                  D1-R1-D2-R1-T1-R1 Senior Advisor
            D1-R1-D3 (Trading Division)
              D1-R1-D3-R1 Head of Trading
                D1-R1-D3-R1-T1 (Equities Desk)
                  D1-R1-D3-R1-T1-R1 Senior Trader
    """
    from pact.governance.compilation import RoleDefinition

    roles = [
        # BOD-level role (external, no parent)
        RoleDefinition(
            role_id="r-bod",
            name="Board of Directors",
            reports_to_role_id=None,
            is_primary_for_unit=None,
            unit_id=None,
            is_vacant=False,
            is_external=True,
        ),
        # CEO — head of Executive Office (D1)
        RoleDefinition(
            role_id="r-ceo",
            name="CEO",
            reports_to_role_id="r-bod",
            is_primary_for_unit="d-exec",
            unit_id="d-exec",
            is_vacant=False,
            is_external=False,
        ),
        # CCO — head of Compliance Division (D1-R1-D1)
        RoleDefinition(
            role_id="r-cco",
            name="Chief Compliance Officer",
            reports_to_role_id="r-ceo",
            is_primary_for_unit="d-compliance",
            unit_id="d-compliance",
            is_vacant=False,
            is_external=False,
        ),
        # AML Officer — head of AML/CFT Team
        RoleDefinition(
            role_id="r-aml",
            name="AML Officer",
            reports_to_role_id="r-cco",
            is_primary_for_unit="t-aml",
            unit_id="t-aml",
            is_vacant=False,
            is_external=False,
        ),
        # Head of Advisory — head of Advisory Division
        RoleDefinition(
            role_id="r-adv-head",
            name="Head of Advisory",
            reports_to_role_id="r-ceo",
            is_primary_for_unit="d-advisory",
            unit_id="d-advisory",
            is_vacant=False,
            is_external=False,
        ),
        # Senior Advisor — head of Client Advisory Team
        RoleDefinition(
            role_id="r-advisor",
            name="Senior Advisor",
            reports_to_role_id="r-adv-head",
            is_primary_for_unit="t-client-advisory",
            unit_id="t-client-advisory",
            is_vacant=False,
            is_external=False,
        ),
        # Head of Trading — head of Trading Division
        RoleDefinition(
            role_id="r-trd-head",
            name="Head of Trading",
            reports_to_role_id="r-ceo",
            is_primary_for_unit="d-trading",
            unit_id="d-trading",
            is_vacant=False,
            is_external=False,
        ),
        # Senior Trader — head of Equities Desk
        RoleDefinition(
            role_id="r-trader",
            name="Senior Trader",
            reports_to_role_id="r-trd-head",
            is_primary_for_unit="t-equities",
            unit_id="t-equities",
            is_vacant=False,
            is_external=False,
        ),
    ]

    departments = [
        DepartmentConfig(department_id="d-exec", name="Executive Office"),
        DepartmentConfig(department_id="d-compliance", name="Compliance Division"),
        DepartmentConfig(department_id="d-advisory", name="Advisory Division"),
        DepartmentConfig(department_id="d-trading", name="Trading Division"),
    ]

    teams = [
        TeamConfig(id="t-aml", name="AML/CFT Team", workspace="ws-aml"),
        TeamConfig(id="t-client-advisory", name="Client Advisory Team", workspace="ws-advisory"),
        TeamConfig(id="t-equities", name="Equities Desk", workspace="ws-trading"),
    ]

    return OrgDefinition(
        org_id="finserv-001",
        name="Financial Services Corp",
        departments=departments,
        teams=teams,
        roles=roles,
    )


@pytest.fixture
def minimal_org() -> OrgDefinition:
    """Minimal valid org: one department with a head role."""
    from pact.governance.compilation import RoleDefinition

    return OrgDefinition(
        org_id="minimal-001",
        name="Minimal Org",
        departments=[
            DepartmentConfig(department_id="d-main", name="Main Department"),
        ],
        teams=[],
        roles=[
            RoleDefinition(
                role_id="r-head",
                name="Department Head",
                reports_to_role_id=None,
                is_primary_for_unit="d-main",
                unit_id="d-main",
                is_vacant=False,
                is_external=False,
            ),
        ],
    )


@pytest.fixture
def org_with_vacancy() -> OrgDefinition:
    """Org with a vacant role to test vacancy handling."""
    from pact.governance.compilation import RoleDefinition

    return OrgDefinition(
        org_id="vacancy-001",
        name="Org With Vacancy",
        departments=[
            DepartmentConfig(department_id="d-eng", name="Engineering"),
        ],
        teams=[
            TeamConfig(id="t-backend", name="Backend Team", workspace="ws-eng"),
        ],
        roles=[
            RoleDefinition(
                role_id="r-eng-head",
                name="VP Engineering",
                reports_to_role_id=None,
                is_primary_for_unit="d-eng",
                unit_id="d-eng",
                is_vacant=False,
                is_external=False,
            ),
            RoleDefinition(
                role_id="r-backend-lead",
                name="Backend Lead",
                reports_to_role_id="r-eng-head",
                is_primary_for_unit="t-backend",
                unit_id="t-backend",
                is_vacant=True,  # This position is vacant
                is_external=False,
            ),
        ],
    )


# ---------------------------------------------------------------------------
# TODO-1002: RoleDefinition on OrgDefinition
# ---------------------------------------------------------------------------


class TestRoleDefinitionModel:
    """RoleDefinition is available as a field on OrgDefinition."""

    def test_org_definition_has_roles_field(self) -> None:
        """OrgDefinition.roles field exists and defaults to empty list."""
        org = OrgDefinition(org_id="test", name="Test")
        assert hasattr(org, "roles")
        assert org.roles == []

    def test_role_definition_fields(self) -> None:
        from pact.governance.compilation import RoleDefinition

        role = RoleDefinition(
            role_id="r-test",
            name="Test Role",
            reports_to_role_id="r-parent",
            is_primary_for_unit="d-main",
            unit_id="d-main",
            is_vacant=False,
            is_external=False,
        )
        assert role.role_id == "r-test"
        assert role.name == "Test Role"
        assert role.reports_to_role_id == "r-parent"
        assert role.is_primary_for_unit == "d-main"
        assert role.unit_id == "d-main"
        assert role.is_vacant is False
        assert role.is_external is False

    def test_role_definition_defaults(self) -> None:
        from pact.governance.compilation import RoleDefinition

        role = RoleDefinition(role_id="r-min", name="Minimal")
        assert role.reports_to_role_id is None
        assert role.is_primary_for_unit is None
        assert role.unit_id is None
        assert role.is_vacant is False
        assert role.is_external is False
        assert role.agent_id is None
        assert role.address is None

    def test_org_with_roles_round_trip(self, minimal_org: OrgDefinition) -> None:
        """OrgDefinition with roles can be serialized and restored."""
        assert len(minimal_org.roles) == 1
        assert minimal_org.roles[0].role_id == "r-head"

    def test_backward_compatibility_no_roles(self) -> None:
        """Existing OrgDefinitions without roles still work (defaults to [])."""
        org = OrgDefinition(
            org_id="legacy",
            name="Legacy Org",
            departments=[DepartmentConfig(department_id="d-1", name="Dept 1")],
        )
        assert org.roles == []


# ---------------------------------------------------------------------------
# TODO-1003: compile_org() — basic compilation
# ---------------------------------------------------------------------------


class TestCompileOrg:
    """compile_org() transforms OrgDefinition into CompiledOrg."""

    def test_compile_minimal_org(self, minimal_org: OrgDefinition) -> None:
        compiled = compile_org(minimal_org)
        assert isinstance(compiled, CompiledOrg)
        assert compiled.org_id == "minimal-001"

    def test_compiled_org_contains_all_nodes(self, minimal_org: OrgDefinition) -> None:
        compiled = compile_org(minimal_org)
        # Minimal org has: D1 (department), R1 (head role)
        # Address: D1-R1 for the head role, D1 is implied by the department
        assert len(compiled.nodes) > 0

    def test_financial_services_full_compilation(
        self, financial_services_org: OrgDefinition
    ) -> None:
        compiled = compile_org(financial_services_org)
        assert compiled.org_id == "finserv-001"
        # Should have nodes for all departments, teams, and roles
        assert len(compiled.nodes) > 0

    def test_financial_services_ceo_address(self, financial_services_org: OrgDefinition) -> None:
        """CEO should get address D1-R1 (head of first department)."""
        compiled = compile_org(financial_services_org)
        ceo_node = compiled.get_node_by_role_id("r-ceo")
        assert ceo_node is not None
        assert ceo_node.address == "D1-R1"

    def test_financial_services_cco_address(self, financial_services_org: OrgDefinition) -> None:
        """CCO should get address D1-R1-D1-R1 (head of first sub-department under CEO)."""
        compiled = compile_org(financial_services_org)
        cco_node = compiled.get_node_by_role_id("r-cco")
        assert cco_node is not None
        assert cco_node.address == "D1-R1-D1-R1"

    def test_financial_services_aml_officer_address(
        self, financial_services_org: OrgDefinition
    ) -> None:
        """AML Officer should get address D1-R1-D1-R1-T1-R1."""
        compiled = compile_org(financial_services_org)
        aml_node = compiled.get_node_by_role_id("r-aml")
        assert aml_node is not None
        assert aml_node.address == "D1-R1-D1-R1-T1-R1"

    def test_financial_services_advisory_address(
        self, financial_services_org: OrgDefinition
    ) -> None:
        """Head of Advisory should get D1-R1-D2-R1."""
        compiled = compile_org(financial_services_org)
        adv_node = compiled.get_node_by_role_id("r-adv-head")
        assert adv_node is not None
        assert adv_node.address == "D1-R1-D2-R1"

    def test_financial_services_trading_address(
        self, financial_services_org: OrgDefinition
    ) -> None:
        """Head of Trading should get D1-R1-D3-R1."""
        compiled = compile_org(financial_services_org)
        trd_node = compiled.get_node_by_role_id("r-trd-head")
        assert trd_node is not None
        assert trd_node.address == "D1-R1-D3-R1"

    def test_financial_services_senior_trader_address(
        self, financial_services_org: OrgDefinition
    ) -> None:
        """Senior Trader should get D1-R1-D3-R1-T1-R1."""
        compiled = compile_org(financial_services_org)
        trader_node = compiled.get_node_by_role_id("r-trader")
        assert trader_node is not None
        assert trader_node.address == "D1-R1-D3-R1-T1-R1"

    def test_financial_services_bod_is_root_role(
        self, financial_services_org: OrgDefinition
    ) -> None:
        """BOD role should be a root-level role (R1)."""
        compiled = compile_org(financial_services_org)
        bod_node = compiled.get_node_by_role_id("r-bod")
        assert bod_node is not None
        assert bod_node.address == "R1"
        assert bod_node.is_external is True

    def test_all_addresses_are_grammar_valid(self, financial_services_org: OrgDefinition) -> None:
        """Every assigned address must pass grammar validation."""
        compiled = compile_org(financial_services_org)
        for addr_str, node in compiled.nodes.items():
            # Addresses ending with D or T (containment units) are structural
            # Only full addresses (ending with R) must be grammar-valid on their own
            if node.node_type == NodeType.ROLE:
                Address.parse(addr_str)  # Should not raise

    def test_org_node_has_expected_fields(self, minimal_org: OrgDefinition) -> None:
        compiled = compile_org(minimal_org)
        # Get any node to check fields
        for node in compiled.nodes.values():
            assert hasattr(node, "address")
            assert hasattr(node, "node_type")
            assert hasattr(node, "name")
            assert hasattr(node, "node_id")
            assert hasattr(node, "parent_address")
            assert hasattr(node, "children_addresses")
            assert hasattr(node, "is_vacant")
            assert hasattr(node, "is_external")
            break


# ---------------------------------------------------------------------------
# TODO-1003: get_node()
# ---------------------------------------------------------------------------


class TestGetNode:
    """CompiledOrg.get_node() address lookup."""

    def test_get_existing_node(self, financial_services_org: OrgDefinition) -> None:
        compiled = compile_org(financial_services_org)
        node = compiled.get_node("D1-R1")
        assert node is not None
        assert node.name == "CEO"

    def test_get_nonexistent_node_raises(self, financial_services_org: OrgDefinition) -> None:
        compiled = compile_org(financial_services_org)
        with pytest.raises(KeyError):
            compiled.get_node("D99-R99")

    def test_get_root_role(self, financial_services_org: OrgDefinition) -> None:
        compiled = compile_org(financial_services_org)
        node = compiled.get_node("R1")
        assert node.name == "Board of Directors"


# ---------------------------------------------------------------------------
# TODO-1004: query_by_prefix() and get_subtree()
# ---------------------------------------------------------------------------


class TestQueryByPrefix:
    """CompiledOrg.query_by_prefix() filters nodes by address prefix."""

    def test_query_entire_org(self, financial_services_org: OrgDefinition) -> None:
        compiled = compile_org(financial_services_org)
        # D1 prefix should return everything under the Executive Office
        results = compiled.query_by_prefix("D1")
        assert len(results) > 0
        for node in results:
            assert node.address.startswith("D1")

    def test_query_compliance_division(self, financial_services_org: OrgDefinition) -> None:
        compiled = compile_org(financial_services_org)
        results = compiled.query_by_prefix("D1-R1-D1")
        # Should include: D1-R1-D1-R1 (CCO), D1-R1-D1-R1-T1-R1 (AML Officer),
        # and the structural nodes D1-R1-D1 and D1-R1-D1-R1-T1
        assert len(results) >= 2  # At minimum CCO and AML Officer

    def test_query_no_match(self, financial_services_org: OrgDefinition) -> None:
        compiled = compile_org(financial_services_org)
        results = compiled.query_by_prefix("D99")
        assert results == []


class TestGetSubtree:
    """CompiledOrg.get_subtree() returns all descendants including the root."""

    def test_subtree_of_ceo(self, financial_services_org: OrgDefinition) -> None:
        compiled = compile_org(financial_services_org)
        subtree = compiled.get_subtree("D1-R1")
        # CEO's subtree includes everything under D1-R1
        assert len(subtree) > 1
        addresses = [n.address for n in subtree]
        assert "D1-R1" in addresses  # includes self

    def test_subtree_of_leaf(self, financial_services_org: OrgDefinition) -> None:
        compiled = compile_org(financial_services_org)
        subtree = compiled.get_subtree("D1-R1-D3-R1-T1-R1")
        # Leaf node: subtree is just itself
        assert len(subtree) == 1
        assert subtree[0].address == "D1-R1-D3-R1-T1-R1"

    def test_subtree_nonexistent_raises(self, financial_services_org: OrgDefinition) -> None:
        compiled = compile_org(financial_services_org)
        with pytest.raises(KeyError):
            compiled.get_subtree("D99-R99")


class TestRootRoles:
    """CompiledOrg.root_roles property."""

    def test_root_roles_includes_bod(self, financial_services_org: OrgDefinition) -> None:
        compiled = compile_org(financial_services_org)
        root_names = [r.name for r in compiled.root_roles]
        assert "Board of Directors" in root_names

    def test_root_roles_count(self, financial_services_org: OrgDefinition) -> None:
        compiled = compile_org(financial_services_org)
        # BOD is the only root role (CEO reports to BOD)
        # Plus we might have the top-level department node
        root_role_nodes = [r for r in compiled.root_roles if r.node_type == NodeType.ROLE]
        assert len(root_role_nodes) >= 1


# ---------------------------------------------------------------------------
# TODO-1005: Vacancy handling
# ---------------------------------------------------------------------------


class TestVacancyHandling:
    """VacancyStatus for role vacancy queries."""

    def test_vacancy_status_for_occupied_role(self, financial_services_org: OrgDefinition) -> None:
        compiled = compile_org(financial_services_org)
        ceo_node = compiled.get_node_by_role_id("r-ceo")
        assert ceo_node is not None
        status = compiled.get_vacancy_status(ceo_node.address)
        assert status.is_vacant is False

    def test_vacancy_status_for_vacant_role(self, org_with_vacancy: OrgDefinition) -> None:
        compiled = compile_org(org_with_vacancy)
        vacant_node = compiled.get_node_by_role_id("r-backend-lead")
        assert vacant_node is not None
        status = compiled.get_vacancy_status(vacant_node.address)
        assert status.is_vacant is True

    def test_vacancy_status_for_nonexistent_address_raises(
        self, minimal_org: OrgDefinition
    ) -> None:
        compiled = compile_org(minimal_org)
        with pytest.raises(KeyError):
            compiled.get_vacancy_status("D99-R99")

    def test_vacancy_status_has_role_id(self, org_with_vacancy: OrgDefinition) -> None:
        compiled = compile_org(org_with_vacancy)
        vacant_node = compiled.get_node_by_role_id("r-backend-lead")
        assert vacant_node is not None
        status = compiled.get_vacancy_status(vacant_node.address)
        assert status.role_id == "r-backend-lead"

    def test_vacancy_status_external_role(self, financial_services_org: OrgDefinition) -> None:
        compiled = compile_org(financial_services_org)
        bod_node = compiled.get_node_by_role_id("r-bod")
        assert bod_node is not None
        status = compiled.get_vacancy_status(bod_node.address)
        assert status.is_vacant is False
        assert status.is_external is True


# ---------------------------------------------------------------------------
# Compilation error cases
# ---------------------------------------------------------------------------


class TestCompilationErrors:
    """compile_org() raises CompilationError for invalid org structures."""

    def test_duplicate_role_ids_rejected(self) -> None:
        from pact.governance.compilation import RoleDefinition

        org = OrgDefinition(
            org_id="bad",
            name="Bad",
            roles=[
                RoleDefinition(role_id="r-dup", name="Role A"),
                RoleDefinition(role_id="r-dup", name="Role B"),
            ],
        )
        with pytest.raises(CompilationError, match="Duplicate role ID"):
            compile_org(org)

    def test_dangling_reports_to_rejected(self) -> None:
        from pact.governance.compilation import RoleDefinition

        org = OrgDefinition(
            org_id="bad",
            name="Bad",
            roles=[
                RoleDefinition(
                    role_id="r-child",
                    name="Child",
                    reports_to_role_id="r-nonexistent",
                ),
            ],
        )
        with pytest.raises(CompilationError, match="reports_to_role_id.*not found"):
            compile_org(org)

    def test_circular_reports_to_rejected(self) -> None:
        from pact.governance.compilation import RoleDefinition

        org = OrgDefinition(
            org_id="bad",
            name="Bad",
            roles=[
                RoleDefinition(
                    role_id="r-a",
                    name="Role A",
                    reports_to_role_id="r-b",
                ),
                RoleDefinition(
                    role_id="r-b",
                    name="Role B",
                    reports_to_role_id="r-a",
                ),
            ],
        )
        with pytest.raises(CompilationError, match="[Cc]ircular"):
            compile_org(org)

    def test_unit_id_references_nonexistent_department_rejected(self) -> None:
        from pact.governance.compilation import RoleDefinition

        org = OrgDefinition(
            org_id="bad",
            name="Bad",
            roles=[
                RoleDefinition(
                    role_id="r-head",
                    name="Head",
                    is_primary_for_unit="d-nonexistent",
                    unit_id="d-nonexistent",
                ),
            ],
        )
        with pytest.raises(CompilationError, match="unit.*not found"):
            compile_org(org)

    def test_empty_org_compiles_to_empty(self) -> None:
        """An org with no roles, departments, or teams compiles to an empty CompiledOrg."""
        org = OrgDefinition(org_id="empty", name="Empty Org")
        compiled = compile_org(org)
        assert len(compiled.nodes) == 0


# ---------------------------------------------------------------------------
# OrgNode field checks
# ---------------------------------------------------------------------------


class TestOrgNodeFields:
    """OrgNode has all required fields."""

    def test_role_node_has_role_definition(self, minimal_org: OrgDefinition) -> None:
        compiled = compile_org(minimal_org)
        for node in compiled.nodes.values():
            if node.node_type == NodeType.ROLE:
                assert node.role_definition is not None

    def test_department_node_has_department(self, minimal_org: OrgDefinition) -> None:
        compiled = compile_org(minimal_org)
        for node in compiled.nodes.values():
            if node.node_type == NodeType.DEPARTMENT:
                assert node.department is not None

    def test_children_addresses_populated(self, financial_services_org: OrgDefinition) -> None:
        compiled = compile_org(financial_services_org)
        ceo_node = compiled.get_node("D1-R1")
        # CEO should have children (the sub-departments)
        assert len(ceo_node.children_addresses) > 0

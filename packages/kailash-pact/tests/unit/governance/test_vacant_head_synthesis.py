# Copyright 2026 Terrene Foundation
# Licensed under the Apache License, Version 2.0
"""Tests for auto-creation of vacant head roles in compile_org().

PACT spec Section 4.2: "When a D or T is created without an R, the system
auto-creates a vacant head role."

Covers:
- TODO-05: Headless departments get synthesized vacant heads
- TODO-05: Headless teams get synthesized vacant heads
- TODO-05: Synthesized roles get proper positional addresses
- TODO-05: Existing explicit heads are not affected
"""

from __future__ import annotations

import pytest

from kailash.trust.pact.config import DepartmentConfig, OrgDefinition, TeamConfig
from kailash.trust.pact.addressing import NodeType
from kailash.trust.pact.compilation import (
    RoleDefinition,
    compile_org,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def headless_dept_org() -> OrgDefinition:
    """Org with one department that has NO head role assigned."""
    return OrgDefinition(
        org_id="headless-dept-001",
        name="Headless Dept Org",
        departments=[
            DepartmentConfig(department_id="d-orphan", name="Orphan Department"),
        ],
        teams=[],
        roles=[],
    )


@pytest.fixture
def headless_team_org() -> OrgDefinition:
    """Org with one team that has NO head role assigned."""
    return OrgDefinition(
        org_id="headless-team-001",
        name="Headless Team Org",
        departments=[],
        teams=[
            TeamConfig(id="t-orphan", name="Orphan Team", workspace="ws-orphan"),
        ],
        roles=[],
    )


@pytest.fixture
def mixed_org() -> OrgDefinition:
    """Org with one headed dept, one headless dept, and one headless team."""
    return OrgDefinition(
        org_id="mixed-001",
        name="Mixed Org",
        departments=[
            DepartmentConfig(department_id="d-headed", name="Headed Department"),
            DepartmentConfig(department_id="d-headless", name="Headless Department"),
        ],
        teams=[
            TeamConfig(id="t-headless", name="Headless Team", workspace="ws-team"),
        ],
        roles=[
            RoleDefinition(
                role_id="r-head",
                name="Department Head",
                reports_to_role_id=None,
                is_primary_for_unit="d-headed",
                unit_id="d-headed",
                is_vacant=False,
                is_external=False,
            ),
        ],
    )


@pytest.fixture
def multiple_headless_depts_org() -> OrgDefinition:
    """Org with two headless departments."""
    return OrgDefinition(
        org_id="multi-headless-001",
        name="Multi Headless Org",
        departments=[
            DepartmentConfig(department_id="d-alpha", name="Alpha Department"),
            DepartmentConfig(department_id="d-beta", name="Beta Department"),
        ],
        teams=[],
        roles=[],
    )


# ---------------------------------------------------------------------------
# Test: Headless department gets vacant head
# ---------------------------------------------------------------------------


class TestHeadlessDeptGetsVacantHead:
    """A department with no head role must get a synthesized vacant head."""

    def test_headless_dept_gets_vacant_head(
        self, headless_dept_org: OrgDefinition
    ) -> None:
        """Headless department gets a synthesized vacant head role node."""
        compiled = compile_org(headless_dept_org)

        # The compiled org must NOT be empty -- the dept and its vacant head must appear
        assert len(compiled.nodes) > 0

        # Find the vacant head role node
        vacant_nodes = [
            n
            for n in compiled.nodes.values()
            if n.node_type == NodeType.ROLE and n.is_vacant is True
        ]
        assert len(vacant_nodes) == 1, (
            f"Expected exactly 1 vacant head role, got {len(vacant_nodes)}. "
            f"All nodes: {sorted(compiled.nodes.keys())}"
        )

        vacant_node = vacant_nodes[0]
        assert vacant_node.role_definition is not None
        assert vacant_node.role_definition.is_vacant is True
        assert vacant_node.role_definition.is_primary_for_unit == "d-orphan"


# ---------------------------------------------------------------------------
# Test: Headless team gets vacant head
# ---------------------------------------------------------------------------


class TestHeadlessTeamGetsVacantHead:
    """A team with no head role must get a synthesized vacant head."""

    def test_headless_team_gets_vacant_head(
        self, headless_team_org: OrgDefinition
    ) -> None:
        """Headless team gets a synthesized vacant head role node."""
        compiled = compile_org(headless_team_org)

        assert len(compiled.nodes) > 0

        vacant_nodes = [
            n
            for n in compiled.nodes.values()
            if n.node_type == NodeType.ROLE and n.is_vacant is True
        ]
        assert len(vacant_nodes) == 1, (
            f"Expected exactly 1 vacant head role, got {len(vacant_nodes)}. "
            f"All nodes: {sorted(compiled.nodes.keys())}"
        )

        vacant_node = vacant_nodes[0]
        assert vacant_node.role_definition is not None
        assert vacant_node.role_definition.is_vacant is True
        assert vacant_node.role_definition.is_primary_for_unit == "t-orphan"


# ---------------------------------------------------------------------------
# Test: Vacant head gets proper positional address
# ---------------------------------------------------------------------------


class TestVacantHeadGetsAddress:
    """Synthesized vacant heads must receive proper D{n}-R1 or T{n}-R1 addresses."""

    def test_vacant_dept_head_gets_d_r1_address(
        self, headless_dept_org: OrgDefinition
    ) -> None:
        """Vacant department head gets D{n}-R1 address."""
        compiled = compile_org(headless_dept_org)

        vacant_nodes = [
            n
            for n in compiled.nodes.values()
            if n.node_type == NodeType.ROLE and n.is_vacant is True
        ]
        assert len(vacant_nodes) == 1
        vacant_node = vacant_nodes[0]

        # The address must end with -R1 (it's the head of a department)
        assert vacant_node.address.endswith(
            "-R1"
        ), f"Vacant dept head address should end with '-R1', got '{vacant_node.address}'"
        # The address must contain 'D' (it's under a department)
        assert (
            "D" in vacant_node.address
        ), f"Vacant dept head address should contain 'D', got '{vacant_node.address}'"

    def test_vacant_team_head_gets_t_r1_address(
        self, headless_team_org: OrgDefinition
    ) -> None:
        """Vacant team head gets T{n}-R1 address."""
        compiled = compile_org(headless_team_org)

        vacant_nodes = [
            n
            for n in compiled.nodes.values()
            if n.node_type == NodeType.ROLE and n.is_vacant is True
        ]
        assert len(vacant_nodes) == 1
        vacant_node = vacant_nodes[0]

        assert vacant_node.address.endswith(
            "-R1"
        ), f"Vacant team head address should end with '-R1', got '{vacant_node.address}'"
        assert (
            "T" in vacant_node.address
        ), f"Vacant team head address should contain 'T', got '{vacant_node.address}'"


# ---------------------------------------------------------------------------
# Test: Vacancy flag on OrgNode
# ---------------------------------------------------------------------------


class TestVacantHeadIsVacantTrue:
    """The synthesized vacant head must have is_vacant=True on the OrgNode."""

    def test_vacant_dept_head_orgnode_is_vacant(
        self, headless_dept_org: OrgDefinition
    ) -> None:
        """OrgNode.is_vacant is True for synthesized dept head."""
        compiled = compile_org(headless_dept_org)

        vacant_nodes = [
            n
            for n in compiled.nodes.values()
            if n.node_type == NodeType.ROLE and n.is_vacant is True
        ]
        assert len(vacant_nodes) == 1
        assert vacant_nodes[0].is_vacant is True

    def test_vacancy_status_query(self, headless_dept_org: OrgDefinition) -> None:
        """get_vacancy_status() reports vacant for synthesized head."""
        compiled = compile_org(headless_dept_org)

        vacant_nodes = [
            n
            for n in compiled.nodes.values()
            if n.node_type == NodeType.ROLE and n.is_vacant is True
        ]
        assert len(vacant_nodes) == 1

        status = compiled.get_vacancy_status(vacant_nodes[0].address)
        assert status.is_vacant is True
        assert vacant_nodes[0].role_definition is not None
        assert status.role_id == vacant_nodes[0].role_definition.role_id


# ---------------------------------------------------------------------------
# Test: Existing heads are unaffected
# ---------------------------------------------------------------------------


class TestExistingHeadsUnaffected:
    """Departments with explicit head roles must NOT get additional vacant heads."""

    def test_existing_head_not_duplicated(self, mixed_org: OrgDefinition) -> None:
        """A department with an explicit head does not get a second (vacant) head."""
        compiled = compile_org(mixed_org)

        # Find the explicit head for d-headed
        headed_node = compiled.get_node_by_role_id("r-head")
        assert headed_node is not None
        assert headed_node.is_vacant is False

        # Count how many role nodes claim to head d-headed
        heads_for_headed_dept = [
            n
            for n in compiled.nodes.values()
            if n.node_type == NodeType.ROLE
            and n.role_definition is not None
            and n.role_definition.is_primary_for_unit == "d-headed"
        ]
        assert (
            len(heads_for_headed_dept) == 1
        ), f"Expected exactly 1 head for d-headed, got {len(heads_for_headed_dept)}"

    def test_headless_units_still_get_vacant_heads(
        self, mixed_org: OrgDefinition
    ) -> None:
        """Headless department and team in mixed org get vacant heads."""
        compiled = compile_org(mixed_org)

        # d-headless should have a vacant head
        headless_dept_heads = [
            n
            for n in compiled.nodes.values()
            if n.node_type == NodeType.ROLE
            and n.role_definition is not None
            and n.role_definition.is_primary_for_unit == "d-headless"
        ]
        assert len(headless_dept_heads) == 1
        assert headless_dept_heads[0].is_vacant is True

        # t-headless should have a vacant head
        headless_team_heads = [
            n
            for n in compiled.nodes.values()
            if n.node_type == NodeType.ROLE
            and n.role_definition is not None
            and n.role_definition.is_primary_for_unit == "t-headless"
        ]
        assert len(headless_team_heads) == 1
        assert headless_team_heads[0].is_vacant is True


# ---------------------------------------------------------------------------
# Test: Multiple headless units
# ---------------------------------------------------------------------------


class TestMultipleHeadlessUnits:
    """Multiple headless departments each get their own vacant head."""

    def test_two_headless_depts_get_two_vacant_heads(
        self, multiple_headless_depts_org: OrgDefinition
    ) -> None:
        """Two headless departments produce exactly 2 vacant head roles."""
        compiled = compile_org(multiple_headless_depts_org)

        vacant_roles = [
            n
            for n in compiled.nodes.values()
            if n.node_type == NodeType.ROLE and n.is_vacant is True
        ]
        assert len(vacant_roles) == 2, (
            f"Expected 2 vacant heads for 2 headless depts, got {len(vacant_roles)}. "
            f"All nodes: {sorted(compiled.nodes.keys())}"
        )

        # Each vacant head must reference a different department
        unit_ids = {
            n.role_definition.is_primary_for_unit
            for n in vacant_roles
            if n.role_definition is not None
        }
        assert unit_ids == {"d-alpha", "d-beta"}

    def test_each_vacant_head_has_unique_address(
        self, multiple_headless_depts_org: OrgDefinition
    ) -> None:
        """Each synthesized vacant head gets a distinct positional address."""
        compiled = compile_org(multiple_headless_depts_org)

        vacant_roles = [
            n
            for n in compiled.nodes.values()
            if n.node_type == NodeType.ROLE and n.is_vacant is True
        ]
        addresses = [n.address for n in vacant_roles]
        assert len(addresses) == len(
            set(addresses)
        ), f"Vacant head addresses must be unique, got: {addresses}"

    def test_each_vacant_head_has_unique_role_id(
        self, multiple_headless_depts_org: OrgDefinition
    ) -> None:
        """Each synthesized vacant head gets a distinct role_id."""
        compiled = compile_org(multiple_headless_depts_org)

        vacant_roles = [
            n
            for n in compiled.nodes.values()
            if n.node_type == NodeType.ROLE and n.is_vacant is True
        ]
        role_ids = [
            n.role_definition.role_id
            for n in vacant_roles
            if n.role_definition is not None
        ]
        assert len(role_ids) == len(
            set(role_ids)
        ), f"Vacant head role_ids must be unique, got: {role_ids}"

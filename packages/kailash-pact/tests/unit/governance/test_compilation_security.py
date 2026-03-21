# Copyright 2026 Terrene Foundation
# Licensed under the Apache License, Version 2.0
"""Security hardening tests for compilation.py — TODOs 7006, 7007, 7008.

TODO 7006: RoleDefinition must be frozen (immutable after construction).
TODO 7007: CompiledOrg.nodes must be read-only after compilation (MappingProxyType).
TODO 7008: Depth/breadth limits on compilation to prevent resource exhaustion.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from pact.build.config.schema import DepartmentConfig, TeamConfig
from pact.build.org.builder import OrgDefinition
from pact.governance.compilation import (
    MAX_CHILDREN_PER_NODE,
    MAX_COMPILATION_DEPTH,
    MAX_TOTAL_NODES,
    CompilationError,
    CompiledOrg,
    RoleDefinition,
    compile_org,
)


# ---------------------------------------------------------------------------
# TODO 7006: RoleDefinition must be frozen
# ---------------------------------------------------------------------------


class TestRoleDefinitionFrozen:
    """RoleDefinition is frozen=True — fields cannot be mutated after construction."""

    def test_cannot_mutate_is_external(self) -> None:
        """Attempting to set is_external on a frozen RoleDefinition raises FrozenInstanceError."""
        role_def = RoleDefinition(role_id="r-test", name="Test", is_external=False)
        with pytest.raises(FrozenInstanceError):
            role_def.is_external = True  # type: ignore[misc]

    def test_cannot_mutate_address(self) -> None:
        """Attempting to set address on a frozen RoleDefinition raises FrozenInstanceError."""
        role_def = RoleDefinition(role_id="r-test", name="Test")
        with pytest.raises(FrozenInstanceError):
            role_def.address = "D1-R1"  # type: ignore[misc]

    def test_cannot_mutate_role_id(self) -> None:
        """Attempting to set role_id on a frozen RoleDefinition raises FrozenInstanceError."""
        role_def = RoleDefinition(role_id="r-test", name="Test")
        with pytest.raises(FrozenInstanceError):
            role_def.role_id = "r-hacked"  # type: ignore[misc]

    def test_cannot_mutate_name(self) -> None:
        """Attempting to set name on a frozen RoleDefinition raises FrozenInstanceError."""
        role_def = RoleDefinition(role_id="r-test", name="Test")
        with pytest.raises(FrozenInstanceError):
            role_def.name = "Hacked"  # type: ignore[misc]

    def test_cannot_mutate_is_vacant(self) -> None:
        """Attempting to set is_vacant on a frozen RoleDefinition raises FrozenInstanceError."""
        role_def = RoleDefinition(role_id="r-test", name="Test", is_vacant=False)
        with pytest.raises(FrozenInstanceError):
            role_def.is_vacant = True  # type: ignore[misc]

    def test_cannot_mutate_reports_to(self) -> None:
        """Attempting to set reports_to_role_id raises FrozenInstanceError."""
        role_def = RoleDefinition(role_id="r-test", name="Test")
        with pytest.raises(FrozenInstanceError):
            role_def.reports_to_role_id = "r-evil"  # type: ignore[misc]

    def test_frozen_role_def_still_works_in_compilation(self) -> None:
        """A frozen RoleDefinition can still be compiled into an org without errors."""
        org = OrgDefinition(
            org_id="frozen-test",
            name="Frozen Test",
            departments=[DepartmentConfig(department_id="d-main", name="Main")],
            roles=[
                RoleDefinition(
                    role_id="r-head",
                    name="Head",
                    reports_to_role_id=None,
                    is_primary_for_unit="d-main",
                    unit_id="d-main",
                ),
            ],
        )
        compiled = compile_org(org)
        assert len(compiled.nodes) > 0
        # Verify the role was compiled correctly
        head_node = compiled.get_node_by_role_id("r-head")
        assert head_node is not None
        assert head_node.address == "D1-R1"


# ---------------------------------------------------------------------------
# TODO 7007: CompiledOrg.nodes must be read-only after compilation
# ---------------------------------------------------------------------------


class TestCompiledOrgNodesReadOnly:
    """CompiledOrg.nodes is wrapped in MappingProxyType after compilation."""

    def test_cannot_insert_into_nodes(self) -> None:
        """Inserting a new key into compiled_org.nodes raises TypeError."""
        from pact.governance.addressing import NodeType
        from pact.governance.compilation import OrgNode

        org = OrgDefinition(
            org_id="readonly-test",
            name="ReadOnly Test",
            departments=[DepartmentConfig(department_id="d-main", name="Main")],
            roles=[
                RoleDefinition(
                    role_id="r-head",
                    name="Head",
                    reports_to_role_id=None,
                    is_primary_for_unit="d-main",
                    unit_id="d-main",
                ),
            ],
        )
        compiled = compile_org(org)

        evil_node = OrgNode(
            address="EVIL",
            node_type=NodeType.ROLE,
            name="Evil Node",
            node_id="evil",
        )
        with pytest.raises(TypeError):
            compiled.nodes["EVIL"] = evil_node  # type: ignore[index]

    def test_cannot_delete_from_nodes(self) -> None:
        """Deleting a key from compiled_org.nodes raises TypeError."""
        org = OrgDefinition(
            org_id="readonly-test",
            name="ReadOnly Test",
            departments=[DepartmentConfig(department_id="d-main", name="Main")],
            roles=[
                RoleDefinition(
                    role_id="r-head",
                    name="Head",
                    reports_to_role_id=None,
                    is_primary_for_unit="d-main",
                    unit_id="d-main",
                ),
            ],
        )
        compiled = compile_org(org)
        # Get a known address
        known_addr = next(iter(compiled.nodes.keys()))
        with pytest.raises(TypeError):
            del compiled.nodes[known_addr]  # type: ignore[attr-defined]

    def test_cannot_clear_nodes(self) -> None:
        """Calling .clear() on compiled_org.nodes raises AttributeError."""
        org = OrgDefinition(
            org_id="readonly-test",
            name="ReadOnly Test",
            departments=[DepartmentConfig(department_id="d-main", name="Main")],
            roles=[
                RoleDefinition(
                    role_id="r-head",
                    name="Head",
                    reports_to_role_id=None,
                    is_primary_for_unit="d-main",
                    unit_id="d-main",
                ),
            ],
        )
        compiled = compile_org(org)
        with pytest.raises(AttributeError):
            compiled.nodes.clear()  # type: ignore[union-attr]

    def test_nodes_still_readable_after_compilation(self) -> None:
        """Read operations on compiled_org.nodes still work with MappingProxyType."""
        org = OrgDefinition(
            org_id="readonly-test",
            name="ReadOnly Test",
            departments=[DepartmentConfig(department_id="d-main", name="Main")],
            roles=[
                RoleDefinition(
                    role_id="r-head",
                    name="Head",
                    reports_to_role_id=None,
                    is_primary_for_unit="d-main",
                    unit_id="d-main",
                ),
            ],
        )
        compiled = compile_org(org)

        # All read operations must work
        assert len(compiled.nodes) > 0
        assert "D1-R1" in compiled.nodes
        node = compiled.nodes["D1-R1"]
        assert node.name == "Head"
        assert list(compiled.nodes.keys())
        assert list(compiled.nodes.values())
        assert list(compiled.nodes.items())

    def test_get_node_works_with_readonly_nodes(self) -> None:
        """CompiledOrg.get_node() still works with MappingProxyType."""
        org = OrgDefinition(
            org_id="readonly-test",
            name="ReadOnly Test",
            departments=[DepartmentConfig(department_id="d-main", name="Main")],
            roles=[
                RoleDefinition(
                    role_id="r-head",
                    name="Head",
                    reports_to_role_id=None,
                    is_primary_for_unit="d-main",
                    unit_id="d-main",
                ),
            ],
        )
        compiled = compile_org(org)
        node = compiled.get_node("D1-R1")
        assert node.name == "Head"

    def test_query_by_prefix_works_with_readonly_nodes(self) -> None:
        """CompiledOrg.query_by_prefix() still works with MappingProxyType."""
        org = OrgDefinition(
            org_id="readonly-test",
            name="ReadOnly Test",
            departments=[DepartmentConfig(department_id="d-main", name="Main")],
            roles=[
                RoleDefinition(
                    role_id="r-head",
                    name="Head",
                    reports_to_role_id=None,
                    is_primary_for_unit="d-main",
                    unit_id="d-main",
                ),
            ],
        )
        compiled = compile_org(org)
        results = compiled.query_by_prefix("D1")
        assert len(results) > 0

    def test_empty_org_nodes_also_readonly(self) -> None:
        """Even an empty org has read-only nodes after compilation."""
        org = OrgDefinition(org_id="empty", name="Empty")
        compiled = compile_org(org)
        with pytest.raises(TypeError):
            compiled.nodes["EVIL"] = None  # type: ignore[index]


# ---------------------------------------------------------------------------
# TODO 7008: Depth/breadth limits
# ---------------------------------------------------------------------------


class TestCompilationDepthLimit:
    """compile_org() raises CompilationError when depth exceeds MAX_COMPILATION_DEPTH."""

    def test_depth_limit_constant_exists(self) -> None:
        """MAX_COMPILATION_DEPTH is defined and has a reasonable value."""
        assert MAX_COMPILATION_DEPTH == 50

    def test_depth_51_raises_compilation_error(self) -> None:
        """An org tree with depth 51 (exceeding MAX_COMPILATION_DEPTH=50) is rejected."""
        # Build a chain of 51 roles where each reports to the previous.
        # Each role heads a department, creating depth via D-R nesting.
        # Address depth doubles per level: D1-R1-D1-R1-... so we need
        # enough roles to exceed depth 50 in address segments.
        # Each dept-head role adds 2 segments (D-R), so 26 levels = 52 segments > 50.
        num_roles = 26
        roles = []
        departments = []

        for i in range(num_roles):
            dept_id = f"d-{i}"
            role_id = f"r-{i}"
            reports_to = f"r-{i-1}" if i > 0 else None

            departments.append(DepartmentConfig(department_id=dept_id, name=f"Dept {i}"))
            roles.append(
                RoleDefinition(
                    role_id=role_id,
                    name=f"Head {i}",
                    reports_to_role_id=reports_to,
                    is_primary_for_unit=dept_id,
                    unit_id=dept_id,
                )
            )

        org = OrgDefinition(
            org_id="deep-org",
            name="Deep Org",
            departments=departments,
            roles=roles,
        )
        with pytest.raises(CompilationError, match="[Dd]epth"):
            compile_org(org)

    def test_depth_exactly_50_succeeds(self) -> None:
        """An org tree at exactly depth 50 compiles without error."""
        # 25 levels of D-R nesting = 50 address segments = exactly at limit.
        num_roles = 25
        roles = []
        departments = []

        for i in range(num_roles):
            dept_id = f"d-{i}"
            role_id = f"r-{i}"
            reports_to = f"r-{i-1}" if i > 0 else None

            departments.append(DepartmentConfig(department_id=dept_id, name=f"Dept {i}"))
            roles.append(
                RoleDefinition(
                    role_id=role_id,
                    name=f"Head {i}",
                    reports_to_role_id=reports_to,
                    is_primary_for_unit=dept_id,
                    unit_id=dept_id,
                )
            )

        org = OrgDefinition(
            org_id="boundary-org",
            name="Boundary Org",
            departments=departments,
            roles=roles,
        )
        # Should compile without error
        compiled = compile_org(org)
        assert len(compiled.nodes) > 0


class TestCompilationBreadthLimit:
    """compile_org() raises CompilationError when children per node exceed MAX_CHILDREN_PER_NODE."""

    def test_breadth_limit_constant_exists(self) -> None:
        """MAX_CHILDREN_PER_NODE is defined and has a reasonable value."""
        assert MAX_CHILDREN_PER_NODE == 500

    def test_501_children_raises_compilation_error(self) -> None:
        """A node with 501 children (exceeding MAX_CHILDREN_PER_NODE=500) is rejected."""
        roles = [
            RoleDefinition(
                role_id="r-root",
                name="Root",
                reports_to_role_id=None,
                is_primary_for_unit="d-root",
                unit_id="d-root",
            ),
        ]
        departments = [DepartmentConfig(department_id="d-root", name="Root")]

        # Create 501 child roles that all report to root
        for i in range(501):
            roles.append(
                RoleDefinition(
                    role_id=f"r-child-{i}",
                    name=f"Child {i}",
                    reports_to_role_id="r-root",
                )
            )

        org = OrgDefinition(
            org_id="wide-org",
            name="Wide Org",
            departments=departments,
            roles=roles,
        )
        with pytest.raises(CompilationError, match="[Cc]hildren|[Bb]readth"):
            compile_org(org)


class TestCompilationTotalNodesLimit:
    """compile_org() raises CompilationError when total nodes exceed MAX_TOTAL_NODES."""

    def test_total_nodes_limit_constant_exists(self) -> None:
        """MAX_TOTAL_NODES is defined and has a reasonable value."""
        assert MAX_TOTAL_NODES == 100_000


# ---------------------------------------------------------------------------
# Regression: normal orgs still compile fine after all security fixes
# ---------------------------------------------------------------------------


class TestNormalOrgStillCompiles:
    """Normal-sized organizations compile without errors after security hardening."""

    def test_university_org_compiles(self) -> None:
        """The university example org compiles without hitting any limits."""
        from pact.examples.university.org import create_university_org

        compiled, org_def = create_university_org()
        assert compiled.org_id == "university-001"
        assert len(compiled.nodes) > 0

        # Verify read access works
        president = compiled.get_node("D1-R1")
        assert president.name == "President"

        # Verify nodes are read-only after compilation
        with pytest.raises(TypeError):
            compiled.nodes["EVIL"] = None  # type: ignore[index]

    def test_financial_services_org_compiles(self) -> None:
        """The financial services org from existing tests compiles without issues."""
        roles = [
            RoleDefinition(
                role_id="r-bod",
                name="Board of Directors",
                reports_to_role_id=None,
                is_external=True,
            ),
            RoleDefinition(
                role_id="r-ceo",
                name="CEO",
                reports_to_role_id="r-bod",
                is_primary_for_unit="d-exec",
                unit_id="d-exec",
            ),
            RoleDefinition(
                role_id="r-cco",
                name="CCO",
                reports_to_role_id="r-ceo",
                is_primary_for_unit="d-compliance",
                unit_id="d-compliance",
            ),
        ]
        departments = [
            DepartmentConfig(department_id="d-exec", name="Executive Office"),
            DepartmentConfig(department_id="d-compliance", name="Compliance"),
        ]
        org = OrgDefinition(
            org_id="finserv-test",
            name="Financial Services",
            departments=departments,
            roles=roles,
        )
        compiled = compile_org(org)
        assert len(compiled.nodes) > 0

        # Verify frozen RoleDefinition still works
        ceo = compiled.get_node_by_role_id("r-ceo")
        assert ceo is not None
        assert ceo.role_definition is not None
        assert ceo.role_definition.role_id == "r-ceo"

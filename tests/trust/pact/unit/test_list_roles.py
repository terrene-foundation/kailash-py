# Copyright 2026 Terrene Foundation
# Licensed under the Apache License, Version 2.0
"""Tests for GovernanceEngine.list_roles() -- Issue #205.

Verifies the list_roles query method returns only Role nodes,
supports prefix filtering, and is thread-safe.
"""

from __future__ import annotations

import concurrent.futures

import pytest

from kailash.trust.pact.addressing import NodeType
from kailash.trust.pact.compilation import (
    CompiledOrg,
    OrgNode,
    RoleDefinition,
    compile_org,
)
from kailash.trust.pact.config import DepartmentConfig, OrgDefinition, TeamConfig
from kailash.trust.pact.engine import GovernanceEngine


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def compiled_org() -> CompiledOrg:
    """A small compiled org for testing list_roles.

    Structure:
      D1-R1 VP Engineering
        D1-R1-T1-R1 Backend Lead
        D1-R1-T2-R1 Frontend Lead
      D2-R1 VP Sales
    """
    roles = [
        RoleDefinition(
            role_id="r-vp-eng",
            name="VP Engineering",
            reports_to_role_id=None,
            is_primary_for_unit="d-eng",
        ),
        RoleDefinition(
            role_id="r-backend-lead",
            name="Backend Lead",
            reports_to_role_id="r-vp-eng",
            is_primary_for_unit="t-backend",
        ),
        RoleDefinition(
            role_id="r-frontend-lead",
            name="Frontend Lead",
            reports_to_role_id="r-vp-eng",
            is_primary_for_unit="t-frontend",
        ),
        RoleDefinition(
            role_id="r-vp-sales",
            name="VP Sales",
            reports_to_role_id=None,
            is_primary_for_unit="d-sales",
        ),
    ]
    departments = [
        DepartmentConfig(department_id="d-eng", name="Engineering"),
        DepartmentConfig(department_id="d-sales", name="Sales"),
    ]
    teams = [
        TeamConfig(id="t-backend", name="Backend", workspace="ws-eng"),
        TeamConfig(id="t-frontend", name="Frontend", workspace="ws-eng"),
    ]
    org = OrgDefinition(
        org_id="test-org",
        name="Test Organization",
        departments=departments,
        teams=teams,
        roles=roles,
    )
    return compile_org(org)


@pytest.fixture
def engine(compiled_org: CompiledOrg) -> GovernanceEngine:
    """Engine from compiled org."""
    return GovernanceEngine(compiled_org)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestListRoles:
    """GovernanceEngine.list_roles() query API."""

    def test_list_roles_returns_only_role_nodes(self, engine: GovernanceEngine) -> None:
        """All returned nodes must have node_type == ROLE."""
        roles = engine.list_roles()
        assert len(roles) > 0, "Org should have at least one role"
        for node in roles:
            assert (
                node.node_type == NodeType.ROLE
            ), f"Expected ROLE, got {node.node_type} at {node.address}"

    def test_list_roles_no_prefix_returns_all(
        self, engine: GovernanceEngine, compiled_org: CompiledOrg
    ) -> None:
        """Without prefix filter, list_roles returns every Role in the org."""
        roles = engine.list_roles()
        expected_count = sum(
            1 for n in compiled_org.nodes.values() if n.node_type == NodeType.ROLE
        )
        assert len(roles) == expected_count

    def test_list_roles_returns_expected_count(self, engine: GovernanceEngine) -> None:
        """Our test org has exactly 4 roles."""
        roles = engine.list_roles()
        assert len(roles) == 4

    def test_list_roles_with_prefix_filters(self, engine: GovernanceEngine) -> None:
        """With a prefix, only roles under that subtree are returned."""
        d1_roles = engine.list_roles(prefix="D1-R1")
        # D1-R1 itself plus roles under D1-R1-T1 and D1-R1-T2
        assert len(d1_roles) >= 1  # At least D1-R1 itself
        for node in d1_roles:
            assert node.address == "D1-R1" or node.address.startswith("D1-R1-")
        # Should not include D2-R1
        d1_addresses = {n.address for n in d1_roles}
        assert "D2-R1" not in d1_addresses

    def test_list_roles_exact_prefix_match(self, engine: GovernanceEngine) -> None:
        """Exact address match is included in prefix results."""
        d2_roles = engine.list_roles(prefix="D2-R1")
        assert len(d2_roles) >= 1
        assert any(n.address == "D2-R1" for n in d2_roles)

    def test_list_roles_nonexistent_prefix_returns_empty(
        self, engine: GovernanceEngine
    ) -> None:
        """A prefix that matches no nodes returns an empty list."""
        roles = engine.list_roles(prefix="D999-R999")
        assert roles == []

    def test_list_roles_thread_safe(self, engine: GovernanceEngine) -> None:
        """Concurrent list_roles calls should not raise."""
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            futures = [pool.submit(engine.list_roles) for _ in range(20)]
            results = [f.result() for f in futures]
        # All should return the same count
        counts = {len(r) for r in results}
        assert len(counts) == 1, f"Inconsistent results: {counts}"

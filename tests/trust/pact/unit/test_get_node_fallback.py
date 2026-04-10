# Copyright 2026 Terrene Foundation
# Licensed under the Apache License, Version 2.0
"""Regression tests for GovernanceEngine.get_node() fallback to role_id lookup.

Issue #389: get_node() only did exact dict lookup on compiled_org.nodes.
Non-head roles (analysts, members) whose config role_id is not the same
as their positional address returned None.

Fix: After exact lookup fails, fall back to get_node_by_role_id().
"""

from __future__ import annotations

from typing import Any

import pytest
from kailash.trust.pact.compilation import CompiledOrg, OrgNode
from kailash.trust.pact.engine import GovernanceEngine
from pact.examples.university.org import create_university_org

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def university_compiled() -> tuple[CompiledOrg, Any]:
    """Compiled university org and the original OrgDefinition."""
    return create_university_org()


@pytest.fixture
def compiled_org(university_compiled: tuple[CompiledOrg, Any]) -> CompiledOrg:
    """Just the compiled org."""
    return university_compiled[0]


@pytest.fixture
def org_definition(university_compiled: tuple[CompiledOrg, Any]) -> Any:
    """Just the OrgDefinition."""
    return university_compiled[1]


@pytest.fixture
def engine(compiled_org: CompiledOrg) -> GovernanceEngine:
    """Minimal engine for get_node tests."""
    return GovernanceEngine(compiled_org)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestGetNodeFallback:
    """Regression: #389 -- get_node() should fall back to role_id lookup."""

    @pytest.mark.regression
    def test_head_role_by_positional_address(self, engine: GovernanceEngine) -> None:
        """Head role found by exact positional address (existing behavior)."""
        node = engine.get_node("D1-R1")
        assert node is not None
        assert node.address == "D1-R1"
        assert node.role_definition is not None
        assert node.role_definition.role_id == "r-president"

    @pytest.mark.regression
    def test_non_head_role_by_config_role_id(self, engine: GovernanceEngine) -> None:
        """Non-head role found by config role_id via fallback.

        r-cs-faculty is a non-head role (no is_primary_for_unit). Its
        positional address is something like D1-R1-D1-R1-D1-R1-T1-R1-R1,
        but callers using the config role_id "r-cs-faculty" should still
        find it.
        """
        node = engine.get_node("r-cs-faculty")
        assert node is not None
        assert node.role_definition is not None
        assert node.role_definition.role_id == "r-cs-faculty"
        assert node.role_definition.name == "CS Faculty Member"

    @pytest.mark.regression
    def test_head_role_by_config_role_id(self, engine: GovernanceEngine) -> None:
        """Head role found by config role_id via fallback."""
        node = engine.get_node("r-president")
        assert node is not None
        assert node.role_definition is not None
        assert node.role_definition.role_id == "r-president"
        assert node.address == "D1-R1"

    @pytest.mark.regression
    def test_department_node_by_positional_address(
        self, engine: GovernanceEngine
    ) -> None:
        """Department nodes are found by positional address (not role_id)."""
        node = engine.get_node("D1")
        assert node is not None
        assert node.address == "D1"
        assert node.name == "Office of the President"

    @pytest.mark.regression
    def test_nonexistent_returns_none(self, engine: GovernanceEngine) -> None:
        """A completely nonexistent identifier returns None."""
        node = engine.get_node("does-not-exist")
        assert node is None

    @pytest.mark.regression
    def test_exact_match_takes_priority(self, engine: GovernanceEngine) -> None:
        """When the input matches a positional address exactly, use that
        even if a role_id happens to have the same string. Exact match
        is O(1); role_id scan is O(n) -- exact match should always win."""
        # D1-R1 is an exact address. It should be returned directly
        # without scanning by role_id.
        node = engine.get_node("D1-R1")
        assert node is not None
        assert node.address == "D1-R1"

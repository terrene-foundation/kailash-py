# Copyright 2026 Terrene Foundation
# Licensed under the Apache License, Version 2.0
"""Tests for MockGovernedAgent -- deterministic testing without LLM.

Covers:
- TODO 7035: MockGovernedAgent runs scripted scenarios
- Auto-registration of @governed_tool decorated functions
- Script-based execution order
- Governance enforcement during scripted execution
- Results collection
"""

from __future__ import annotations

from typing import Any

import pytest

from pact.governance.config import (
    ConstraintEnvelopeConfig,
    FinancialConstraintConfig,
    OperationalConstraintConfig,
    TrustPostureLevel,
)
from pact.examples.university.barriers import (
    create_university_bridges,
    create_university_ksps,
)
from pact.examples.university.clearance import create_university_clearances
from pact.examples.university.org import create_university_org
from pact.governance.access import KnowledgeSharePolicy, PactBridge
from pact.governance.agent import GovernanceBlockedError
from pact.governance.clearance import RoleClearance
from pact.governance.compilation import CompiledOrg
from pact.governance.decorators import governed_tool
from pact.governance.engine import GovernanceEngine
from pact.governance.envelopes import RoleEnvelope
from pact.governance.store import (
    MemoryAccessPolicyStore,
    MemoryClearanceStore,
)
from pact.governance.testing import MockGovernedAgent


# ---------------------------------------------------------------------------
# Sample governed tools for testing
# ---------------------------------------------------------------------------


@governed_tool("read", cost=0.0)
def tool_read() -> str:
    return "read_result"


@governed_tool("write", cost=10.0)
def tool_write() -> str:
    return "write_result"


@governed_tool("grade", cost=5.0)
def tool_grade() -> str:
    return "grade_result"


@governed_tool("delete", cost=0.0)
def tool_delete() -> str:
    return "delete_result"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def university_compiled() -> tuple[CompiledOrg, Any]:
    return create_university_org()


@pytest.fixture
def compiled_org(university_compiled: tuple[CompiledOrg, Any]) -> CompiledOrg:
    return university_compiled[0]


@pytest.fixture
def clearances(compiled_org: CompiledOrg) -> dict[str, RoleClearance]:
    return create_university_clearances(compiled_org)


@pytest.fixture
def bridges() -> list[PactBridge]:
    return create_university_bridges()


@pytest.fixture
def ksps() -> list[KnowledgeSharePolicy]:
    return create_university_ksps()


@pytest.fixture
def engine(
    compiled_org: CompiledOrg,
    clearances: dict[str, RoleClearance],
    bridges: list[PactBridge],
    ksps: list[KnowledgeSharePolicy],
) -> GovernanceEngine:
    clearance_store = MemoryClearanceStore()
    for clr in clearances.values():
        clearance_store.grant_clearance(clr)

    access_store = MemoryAccessPolicyStore()
    for bridge in bridges:
        access_store.save_bridge(bridge)
    for ksp in ksps:
        access_store.save_ksp(ksp)

    eng = GovernanceEngine(
        compiled_org,
        clearance_store=clearance_store,
        access_policy_store=access_store,
    )

    # Set up envelope for CS Chair
    envelope_config = ConstraintEnvelopeConfig(
        id="env-cs-chair",
        description="CS Chair envelope",
        financial=FinancialConstraintConfig(max_spend_usd=1000.0),
        operational=OperationalConstraintConfig(
            allowed_actions=["read", "write", "grade"],
            blocked_actions=["delete"],
        ),
    )
    role_env = RoleEnvelope(
        id="re-cs-chair",
        defining_role_address="D1-R1-D1-R1-D1-R1",
        target_role_address="D1-R1-D1-R1-D1-R1-T1-R1",
        envelope=envelope_config,
    )
    eng.set_role_envelope(role_env)

    return eng


CS_CHAIR_ADDR = "D1-R1-D1-R1-D1-R1-T1-R1"


# ---------------------------------------------------------------------------
# Construction Tests
# ---------------------------------------------------------------------------


class TestConstruction:
    """MockGovernedAgent construction."""

    def test_construction_succeeds(self, engine: GovernanceEngine) -> None:
        """Constructing a MockGovernedAgent should succeed."""
        mock = MockGovernedAgent(
            engine=engine,
            role_address=CS_CHAIR_ADDR,
            tools=[tool_read, tool_write],
            script=["read", "write"],
        )
        assert mock is not None

    def test_auto_registers_decorated_tools(self, engine: GovernanceEngine) -> None:
        """Tools with @governed_tool should be auto-registered."""
        mock = MockGovernedAgent(
            engine=engine,
            role_address=CS_CHAIR_ADDR,
            tools=[tool_read, tool_write, tool_grade],
            script=["read"],
        )
        # Should be able to run without default-deny blocking
        results = mock.run()
        assert len(results) == 1
        assert results[0] == "read_result"


# ---------------------------------------------------------------------------
# Script Execution Tests
# ---------------------------------------------------------------------------


class TestScriptExecution:
    """MockGovernedAgent runs actions in script order."""

    def test_runs_script_in_order(self, engine: GovernanceEngine) -> None:
        """Actions should be executed in the order specified by the script."""
        mock = MockGovernedAgent(
            engine=engine,
            role_address=CS_CHAIR_ADDR,
            tools=[tool_read, tool_write, tool_grade],
            script=["read", "write", "grade"],
        )
        results = mock.run()
        assert results == ["read_result", "write_result", "grade_result"]

    def test_empty_script_returns_empty(self, engine: GovernanceEngine) -> None:
        """An empty script should return an empty list."""
        mock = MockGovernedAgent(
            engine=engine,
            role_address=CS_CHAIR_ADDR,
            tools=[tool_read],
            script=[],
        )
        results = mock.run()
        assert results == []

    def test_single_action_script(self, engine: GovernanceEngine) -> None:
        """A single-action script should work."""
        mock = MockGovernedAgent(
            engine=engine,
            role_address=CS_CHAIR_ADDR,
            tools=[tool_read],
            script=["read"],
        )
        results = mock.run()
        assert results == ["read_result"]

    def test_repeated_action_in_script(self, engine: GovernanceEngine) -> None:
        """The same action can appear multiple times in the script."""
        mock = MockGovernedAgent(
            engine=engine,
            role_address=CS_CHAIR_ADDR,
            tools=[tool_read],
            script=["read", "read", "read"],
        )
        results = mock.run()
        assert results == ["read_result", "read_result", "read_result"]


# ---------------------------------------------------------------------------
# Governance Enforcement in Mock Tests
# ---------------------------------------------------------------------------


class TestGovernanceEnforcement:
    """MockGovernedAgent enforces governance during scripted execution."""

    def test_blocked_action_raises(self, engine: GovernanceEngine) -> None:
        """A blocked action in the script should raise GovernanceBlockedError."""
        mock = MockGovernedAgent(
            engine=engine,
            role_address=CS_CHAIR_ADDR,
            tools=[tool_read, tool_delete],
            script=["read", "delete"],
        )
        with pytest.raises(GovernanceBlockedError):
            mock.run()

    def test_unknown_tool_in_script_is_skipped(self, engine: GovernanceEngine) -> None:
        """A tool name in the script that has no matching tool is skipped."""
        mock = MockGovernedAgent(
            engine=engine,
            role_address=CS_CHAIR_ADDR,
            tools=[tool_read],
            script=["read", "nonexistent_tool", "read"],
        )
        # nonexistent_tool is not in tools, so it's skipped
        results = mock.run()
        assert len(results) == 2
        assert results == ["read_result", "read_result"]

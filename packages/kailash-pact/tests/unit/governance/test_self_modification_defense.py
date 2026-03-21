# Copyright 2026 Terrene Foundation
# Licensed under the Apache License, Version 2.0
"""Tests for anti-self-modification defense -- GovernanceContext immutability.

Covers:
- TODO 7036: All GovernanceContext field mutations raise FrozenInstanceError
- Agent cannot modify posture, envelope, clearance, org_id, or any field
- Agent cannot add new attributes to the context
- GovernanceContext from engine.get_context() is immutable
"""

from __future__ import annotations

from typing import Any

import pytest

from pact.governance.config import (
    ConfidentialityLevel,
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
from pact.governance.agent import PactGovernedAgent
from pact.governance.clearance import RoleClearance
from pact.governance.compilation import CompiledOrg
from pact.governance.context import GovernanceContext
from pact.governance.engine import GovernanceEngine
from pact.governance.envelopes import RoleEnvelope
from pact.governance.store import (
    MemoryAccessPolicyStore,
    MemoryClearanceStore,
)


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

    envelope_config = ConstraintEnvelopeConfig(
        id="env-cs-chair",
        description="CS Chair envelope",
        financial=FinancialConstraintConfig(max_spend_usd=1000.0),
        operational=OperationalConstraintConfig(
            allowed_actions=["read", "write"],
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


@pytest.fixture
def agent_context(engine: GovernanceEngine) -> GovernanceContext:
    """GovernanceContext as seen by the agent."""
    agent = PactGovernedAgent(
        engine=engine,
        role_address=CS_CHAIR_ADDR,
        posture=TrustPostureLevel.SHARED_PLANNING,
    )
    return agent.context


# ---------------------------------------------------------------------------
# Frozen Field Mutation Tests
# ---------------------------------------------------------------------------


class TestFrozenFieldMutations:
    """Every field on GovernanceContext must reject mutation attempts."""

    def test_cannot_mutate_role_address(self, agent_context: GovernanceContext) -> None:
        with pytest.raises(AttributeError):
            agent_context.role_address = "D99-R99"  # type: ignore[misc]

    def test_cannot_mutate_posture(self, agent_context: GovernanceContext) -> None:
        with pytest.raises(AttributeError):
            agent_context.posture = TrustPostureLevel.DELEGATED  # type: ignore[misc]

    def test_cannot_mutate_effective_envelope(
        self, agent_context: GovernanceContext
    ) -> None:
        with pytest.raises(AttributeError):
            agent_context.effective_envelope = None  # type: ignore[misc]

    def test_cannot_mutate_clearance(self, agent_context: GovernanceContext) -> None:
        with pytest.raises(AttributeError):
            agent_context.clearance = None  # type: ignore[misc]

    def test_cannot_mutate_effective_clearance_level(
        self, agent_context: GovernanceContext
    ) -> None:
        with pytest.raises(AttributeError):
            agent_context.effective_clearance_level = ConfidentialityLevel.TOP_SECRET  # type: ignore[misc]

    def test_cannot_mutate_allowed_actions(
        self, agent_context: GovernanceContext
    ) -> None:
        with pytest.raises(AttributeError):
            agent_context.allowed_actions = frozenset({"everything"})  # type: ignore[misc]

    def test_cannot_mutate_compartments(self, agent_context: GovernanceContext) -> None:
        with pytest.raises(AttributeError):
            agent_context.compartments = frozenset({"top-secret-data"})  # type: ignore[misc]

    def test_cannot_mutate_org_id(self, agent_context: GovernanceContext) -> None:
        with pytest.raises(AttributeError):
            agent_context.org_id = "hacked-org"  # type: ignore[misc]

    def test_cannot_mutate_created_at(self, agent_context: GovernanceContext) -> None:
        from datetime import datetime, UTC

        with pytest.raises(AttributeError):
            agent_context.created_at = datetime.now(UTC)  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Cannot Add New Attributes
# ---------------------------------------------------------------------------


class TestCannotAddNewAttributes:
    """Frozen dataclasses should reject adding new attributes."""

    def test_cannot_add_new_attribute(self, agent_context: GovernanceContext) -> None:
        with pytest.raises(AttributeError):
            agent_context.hacked_field = "injected"  # type: ignore[misc]

    def test_cannot_add_engine_reference(
        self, agent_context: GovernanceContext
    ) -> None:
        with pytest.raises(AttributeError):
            agent_context.engine = "some_engine_ref"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Context From Engine
# ---------------------------------------------------------------------------


class TestContextFromEngine:
    """GovernanceEngine.get_context() produces a frozen context."""

    def test_engine_get_context_returns_frozen(self, engine: GovernanceEngine) -> None:
        """get_context() should return a frozen GovernanceContext."""
        ctx = engine.get_context(CS_CHAIR_ADDR)
        assert isinstance(ctx, GovernanceContext)
        with pytest.raises(AttributeError):
            ctx.posture = TrustPostureLevel.DELEGATED  # type: ignore[misc]

    def test_engine_get_context_has_correct_role(
        self, engine: GovernanceEngine
    ) -> None:
        """get_context() should include the requested role_address."""
        ctx = engine.get_context(CS_CHAIR_ADDR)
        assert ctx.role_address == CS_CHAIR_ADDR

    def test_engine_get_context_has_envelope(self, engine: GovernanceEngine) -> None:
        """get_context() should include the effective envelope snapshot."""
        ctx = engine.get_context(CS_CHAIR_ADDR)
        assert ctx.effective_envelope is not None
        # CS Chair envelope has max_spend_usd=1000.0
        assert ctx.effective_envelope.financial is not None
        assert ctx.effective_envelope.financial.max_spend_usd == 1000.0

    def test_engine_get_context_has_clearance(self, engine: GovernanceEngine) -> None:
        """get_context() should include the clearance if one exists."""
        ctx = engine.get_context(CS_CHAIR_ADDR)
        # CS Chair has RESTRICTED clearance from university fixtures
        assert ctx.clearance is not None
        assert ctx.clearance.max_clearance == ConfidentialityLevel.RESTRICTED

    def test_engine_get_context_has_allowed_actions(
        self, engine: GovernanceEngine
    ) -> None:
        """get_context() should derive allowed_actions from the envelope."""
        ctx = engine.get_context(CS_CHAIR_ADDR)
        assert "read" in ctx.allowed_actions
        assert "write" in ctx.allowed_actions

    def test_engine_get_context_default_posture_supervised(
        self, engine: GovernanceEngine
    ) -> None:
        """get_context() without posture override defaults to SUPERVISED."""
        ctx = engine.get_context(CS_CHAIR_ADDR)
        assert ctx.posture == TrustPostureLevel.SUPERVISED

    def test_engine_get_context_custom_posture(self, engine: GovernanceEngine) -> None:
        """get_context() with posture override uses the specified posture."""
        ctx = engine.get_context(CS_CHAIR_ADDR, posture=TrustPostureLevel.DELEGATED)
        assert ctx.posture == TrustPostureLevel.DELEGATED

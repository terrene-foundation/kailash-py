# Copyright 2026 Terrene Foundation
# Licensed under the Apache License, Version 2.0
"""Tests for PactGovernedAgent -- governance-wrapped agent execution.

Covers:
- TODO 7030: PactGovernedAgent core lifecycle
- TODO 7037: Default-deny for unregistered tools
- GovernanceBlockedError on BLOCKED verdict
- GovernanceHeldError on HELD verdict
- FLAGGED actions proceed with warning
- AUTO_APPROVED actions proceed silently
- Agent receives GovernanceContext (frozen), NOT GovernanceEngine
- Unregistered tool access raises GovernanceBlockedError (default-deny)
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from pact.build.config.schema import (
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
from pact.governance.agent import (
    GovernanceBlockedError,
    GovernanceHeldError,
    PactGovernedAgent,
)
from pact.governance.clearance import RoleClearance
from pact.governance.compilation import CompiledOrg
from pact.governance.context import GovernanceContext
from pact.governance.engine import GovernanceEngine
from pact.governance.envelopes import RoleEnvelope
from pact.governance.store import (
    MemoryAccessPolicyStore,
    MemoryClearanceStore,
)
from pact.governance.verdict import GovernanceVerdict


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
def clearances(compiled_org: CompiledOrg) -> dict[str, RoleClearance]:
    """Clearance assignments for all university roles."""
    return create_university_clearances(compiled_org)


@pytest.fixture
def bridges() -> list[PactBridge]:
    """Cross-Functional Bridges for the university."""
    return create_university_bridges()


@pytest.fixture
def ksps() -> list[KnowledgeSharePolicy]:
    """Knowledge Share Policies for the university."""
    return create_university_ksps()


@pytest.fixture
def engine(
    compiled_org: CompiledOrg,
    clearances: dict[str, RoleClearance],
    bridges: list[PactBridge],
    ksps: list[KnowledgeSharePolicy],
) -> GovernanceEngine:
    """Engine built from a pre-compiled org with stores populated and envelopes set."""
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

    # Set up a constrained envelope for the CS Chair
    envelope_config = ConstraintEnvelopeConfig(
        id="env-cs-chair",
        description="CS Chair envelope",
        financial=FinancialConstraintConfig(
            max_spend_usd=1000.0,
            requires_approval_above_usd=500.0,
        ),
        operational=OperationalConstraintConfig(
            allowed_actions=["read", "write", "grade", "teach"],
            blocked_actions=["delete", "deploy"],
        ),
    )
    role_env = RoleEnvelope(
        id="re-cs-chair",
        defining_role_address="D1-R1-D1-R1-D1-R1",  # Dean defines
        target_role_address="D1-R1-D1-R1-D1-R1-T1-R1",  # CS Chair
        envelope=envelope_config,
    )
    eng.set_role_envelope(role_env)

    return eng


CS_CHAIR_ADDR = "D1-R1-D1-R1-D1-R1-T1-R1"


@pytest.fixture
def governed_agent(engine: GovernanceEngine) -> PactGovernedAgent:
    """A governed agent for the CS Chair role."""
    agent = PactGovernedAgent(
        engine=engine,
        role_address=CS_CHAIR_ADDR,
        posture=TrustPostureLevel.SHARED_PLANNING,
    )
    # Register known tools
    agent.register_tool("read", cost=0.0)
    agent.register_tool("write", cost=10.0)
    agent.register_tool("grade", cost=5.0)
    agent.register_tool("expensive_action", cost=600.0, resource="budget-data")
    return agent


# ---------------------------------------------------------------------------
# Construction Tests
# ---------------------------------------------------------------------------


class TestConstruction:
    """PactGovernedAgent construction and basic properties."""

    def test_construction_succeeds(self, engine: GovernanceEngine) -> None:
        """Constructing a PactGovernedAgent should succeed."""
        agent = PactGovernedAgent(
            engine=engine,
            role_address=CS_CHAIR_ADDR,
        )
        assert agent.context is not None
        assert agent.context.role_address == CS_CHAIR_ADDR

    def test_context_is_governance_context(self, governed_agent: PactGovernedAgent) -> None:
        """The agent's context property should return a GovernanceContext."""
        assert isinstance(governed_agent.context, GovernanceContext)

    def test_context_is_frozen(self, governed_agent: PactGovernedAgent) -> None:
        """GovernanceContext returned to the agent must be frozen (immutable)."""
        ctx = governed_agent.context
        with pytest.raises(AttributeError):
            ctx.posture = TrustPostureLevel.DELEGATED  # type: ignore[misc]

    def test_context_has_correct_org_id(self, governed_agent: PactGovernedAgent) -> None:
        """Context should contain the correct org_id."""
        assert governed_agent.context.org_id == "university-001"

    def test_default_posture_is_supervised(self, engine: GovernanceEngine) -> None:
        """Default posture should be SUPERVISED when not specified."""
        agent = PactGovernedAgent(
            engine=engine,
            role_address=CS_CHAIR_ADDR,
        )
        assert agent.context.posture == TrustPostureLevel.SUPERVISED


# ---------------------------------------------------------------------------
# Tool Registration Tests (TODO 7037: default-deny)
# ---------------------------------------------------------------------------


class TestToolRegistration:
    """Tool registration and default-deny behavior."""

    def test_register_tool(self, governed_agent: PactGovernedAgent) -> None:
        """register_tool should add the tool to the registered set."""
        governed_agent.register_tool("new_tool", cost=1.0)
        # Should not raise when executed (assuming within envelope)
        # Verification is deferred to execute_tool

    def test_unregistered_tool_blocked(self, governed_agent: PactGovernedAgent) -> None:
        """Executing an unregistered tool must raise GovernanceBlockedError."""
        with pytest.raises(GovernanceBlockedError) as exc_info:
            governed_agent.execute_tool(
                "unregistered_dangerous_tool",
                _tool_fn=lambda: "should never execute",
            )
        assert "not governance-registered" in str(exc_info.value)
        assert exc_info.value.verdict.level == "blocked"
        assert exc_info.value.verdict.action == "unregistered_dangerous_tool"

    def test_unregistered_tool_never_executes_fn(self, governed_agent: PactGovernedAgent) -> None:
        """The tool function must NEVER be called if the tool is not registered."""
        call_tracker = {"called": False}

        def dangerous_fn():
            call_tracker["called"] = True
            return "dangerous result"

        with pytest.raises(GovernanceBlockedError):
            governed_agent.execute_tool(
                "unregistered_tool",
                _tool_fn=dangerous_fn,
            )
        assert call_tracker["called"] is False


# ---------------------------------------------------------------------------
# Execute Tool -- Verdict Level Tests
# ---------------------------------------------------------------------------


class TestExecuteToolVerdicts:
    """execute_tool must respect verification gradient levels."""

    def test_auto_approved_action_succeeds(self, governed_agent: PactGovernedAgent) -> None:
        """An action within the envelope (AUTO_APPROVED) should succeed."""
        result = governed_agent.execute_tool(
            "read",
            _tool_fn=lambda: "read result",
        )
        assert result == "read result"

    def test_blocked_action_raises_error(self, governed_agent: PactGovernedAgent) -> None:
        """An action explicitly blocked by the envelope raises GovernanceBlockedError."""
        # "delete" is in the blocked_actions list. Register it so we get past default-deny.
        governed_agent.register_tool("delete", cost=0.0)
        with pytest.raises(GovernanceBlockedError) as exc_info:
            governed_agent.execute_tool(
                "delete",
                _tool_fn=lambda: "should never execute",
            )
        assert exc_info.value.verdict.level == "blocked"
        assert "blocked" in exc_info.value.verdict.reason.lower()

    def test_blocked_action_never_executes_fn(self, governed_agent: PactGovernedAgent) -> None:
        """The tool function must NEVER be called when governance blocks."""
        call_tracker = {"called": False}

        def dangerous_fn():
            call_tracker["called"] = True
            return "should not see this"

        governed_agent.register_tool("delete", cost=0.0)
        with pytest.raises(GovernanceBlockedError):
            governed_agent.execute_tool("delete", _tool_fn=dangerous_fn)
        assert call_tracker["called"] is False

    def test_held_action_raises_error(self, governed_agent: PactGovernedAgent) -> None:
        """An action that exceeds the approval threshold raises GovernanceHeldError."""
        # "expensive_action" is registered with cost=600.0,
        # but the envelope's requires_approval_above_usd=500.0.
        # However, "expensive_action" is not in allowed_actions for the CS Chair.
        # Register a tool that IS in allowed_actions with cost exceeding threshold.
        governed_agent.register_tool("write_expensive", cost=600.0)

        # We need an action that IS allowed but costs above threshold.
        # "write" is allowed; we'll use it with a high cost tool.
        # The governed agent uses the tool's registered cost when calling verify.
        # So register "grade" with high cost.
        governed_agent.register_tool("grade_papers", cost=600.0)

        # Actually, the envelope only allows: read, write, grade, teach
        # So we need to register a tool whose action_name matches an allowed action.
        # Let's use the existing "expensive_action" -- but that's not in allowed_actions.
        # Let's re-register "write" with high cost to trigger HELD.
        governed_agent._registered_tools["write"] = {"cost": 600.0, "resource": None}

        with pytest.raises(GovernanceHeldError) as exc_info:
            governed_agent.execute_tool(
                "write",
                _tool_fn=lambda: "should not execute",
            )
        assert exc_info.value.verdict.level == "held"

    def test_held_action_never_executes_fn(self, governed_agent: PactGovernedAgent) -> None:
        """The tool function must NEVER be called when governance holds."""
        call_tracker = {"called": False}

        def tracked_fn():
            call_tracker["called"] = True
            return "should not see this"

        governed_agent._registered_tools["write"] = {"cost": 600.0, "resource": None}
        with pytest.raises(GovernanceHeldError):
            governed_agent.execute_tool("write", _tool_fn=tracked_fn)
        assert call_tracker["called"] is False

    def test_flagged_action_succeeds_with_warning(
        self, engine: GovernanceEngine, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A FLAGGED action should succeed but emit a warning log.

        The engine checks approval threshold BEFORE the flagged zone.
        To reach FLAGGED, the cost must be > 80% of max_spend AND
        <= requires_approval_above_usd. So we use an envelope where
        the approval threshold is higher than the flagged zone start.
        """
        # Override envelope: max_spend=1000, approval_threshold=900
        # Flagged zone: 800..900. Cost 850 -> FLAGGED.
        envelope_config = ConstraintEnvelopeConfig(
            id="env-cs-chair-flagged",
            description="CS Chair envelope for flagged test",
            financial=FinancialConstraintConfig(
                max_spend_usd=1000.0,
                requires_approval_above_usd=900.0,
            ),
            operational=OperationalConstraintConfig(
                allowed_actions=["read", "write", "grade", "teach"],
            ),
        )
        role_env = RoleEnvelope(
            id="re-cs-chair-flagged",
            defining_role_address="D1-R1-D1-R1-D1-R1",
            target_role_address=CS_CHAIR_ADDR,
            envelope=envelope_config,
        )
        engine.set_role_envelope(role_env)

        agent = PactGovernedAgent(
            engine=engine,
            role_address=CS_CHAIR_ADDR,
            posture=TrustPostureLevel.SHARED_PLANNING,
        )
        agent.register_tool("grade", cost=850.0)
        with caplog.at_level(logging.WARNING):
            result = agent.execute_tool(
                "grade",
                _tool_fn=lambda: "flagged but ok",
            )
        assert result == "flagged but ok"
        assert any("FLAGGED" in record.message for record in caplog.records)


# ---------------------------------------------------------------------------
# GovernanceBlockedError and GovernanceHeldError Tests
# ---------------------------------------------------------------------------


class TestExceptionProperties:
    """Exception classes carry the verdict for inspection."""

    def test_blocked_error_has_verdict(self, governed_agent: PactGovernedAgent) -> None:
        """GovernanceBlockedError should contain the GovernanceVerdict."""
        with pytest.raises(GovernanceBlockedError) as exc_info:
            governed_agent.execute_tool(
                "unregistered",
                _tool_fn=lambda: None,
            )
        err = exc_info.value
        assert isinstance(err.verdict, GovernanceVerdict)
        assert err.verdict.level == "blocked"
        assert err.verdict.role_address == CS_CHAIR_ADDR

    def test_blocked_error_message_includes_reason(self, governed_agent: PactGovernedAgent) -> None:
        """GovernanceBlockedError message should include the reason."""
        with pytest.raises(GovernanceBlockedError, match="not governance-registered"):
            governed_agent.execute_tool(
                "bad_tool",
                _tool_fn=lambda: None,
            )

    def test_held_error_has_verdict(self, governed_agent: PactGovernedAgent) -> None:
        """GovernanceHeldError should contain the GovernanceVerdict."""
        governed_agent._registered_tools["write"] = {"cost": 600.0, "resource": None}
        with pytest.raises(GovernanceHeldError) as exc_info:
            governed_agent.execute_tool(
                "write",
                _tool_fn=lambda: None,
            )
        err = exc_info.value
        assert isinstance(err.verdict, GovernanceVerdict)
        assert err.verdict.level == "held"


# ---------------------------------------------------------------------------
# Engine Isolation Tests (TODO 7030: agent cannot access engine)
# ---------------------------------------------------------------------------


class TestEngineIsolation:
    """Agent must NOT have access to the GovernanceEngine or its mutation methods."""

    def test_agent_has_no_engine_attribute(self, governed_agent: PactGovernedAgent) -> None:
        """The governed agent should not expose the engine as a public attribute."""
        # _engine is private (underscore prefix), context is the public interface
        assert not hasattr(governed_agent, "engine")
        assert hasattr(governed_agent, "context")

    def test_context_has_no_mutation_methods(self, governed_agent: PactGovernedAgent) -> None:
        """GovernanceContext (the agent's view) must not have mutation methods."""
        ctx = governed_agent.context
        assert not hasattr(ctx, "grant_clearance")
        assert not hasattr(ctx, "revoke_clearance")
        assert not hasattr(ctx, "create_bridge")
        assert not hasattr(ctx, "set_role_envelope")
        assert not hasattr(ctx, "verify_action")

# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Integration tests: PACT governance + Kaizen agent composition.

Verifies that PactGovernedAgent correctly enforces governance decisions
when wrapping Kaizen agent tool execution. Tests the cross-package
boundary between kailash-pact and kailash-kaizen.

Covers:
- Governed agent with registered tools (ALLOWED execution)
- Governed agent with blocked actions (GovernanceBlockedError)
- Governed agent with unregistered tools (default-deny)
- Governance context is frozen (anti-self-modification)
- Audit trail records governance decisions
"""

from __future__ import annotations

import pytest

from kailash.trust.pact.agent import (
    GovernanceBlockedError,
    PactGovernedAgent,
)
from kailash.trust.pact.audit import AuditChain
from kailash.trust.pact.config import (
    ConstraintEnvelopeConfig,
    FinancialConstraintConfig,
    OperationalConstraintConfig,
    TrustPostureLevel,
    VerificationLevel,
)
from kailash.trust.pact.engine import GovernanceEngine
from kailash.trust.pact.envelopes import RoleEnvelope
from pact.examples.university.org import create_university_org

try:
    from kaizen import CoreAgent

    _HAS_KAIZEN = True
except ImportError:
    _HAS_KAIZEN = False


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def governed_engine() -> GovernanceEngine:
    """GovernanceEngine with a role envelope for CS Chair."""
    compiled, _ = create_university_org()
    engine = GovernanceEngine(compiled)

    envelope_config = ConstraintEnvelopeConfig(
        id="env-cs-chair",
        description="CS Chair envelope for integration tests",
        financial=FinancialConstraintConfig(
            max_spend_usd=500.0,
            requires_approval_above_usd=200.0,
        ),
        operational=OperationalConstraintConfig(
            allowed_actions=["read", "grade", "teach"],
            blocked_actions=["delete", "deploy"],
        ),
    )
    role_env = RoleEnvelope(
        id="re-cs-chair-int",
        defining_role_address="D1-R1-D1-R1-D1-R1",
        target_role_address="D1-R1-D1-R1-D1-R1-T1-R1",
        envelope=envelope_config,
    )
    engine.set_role_envelope(role_env)
    return engine


@pytest.fixture
def governed_agent(governed_engine: GovernanceEngine) -> PactGovernedAgent:
    """PactGovernedAgent wrapping the test engine."""
    agent = PactGovernedAgent(
        engine=governed_engine,
        role_address="D1-R1-D1-R1-D1-R1-T1-R1",
        posture=TrustPostureLevel.SUPERVISED,
    )
    agent.register_tool("read", cost=0.0)
    agent.register_tool("grade", cost=10.0)
    agent.register_tool("delete", cost=0.0)
    return agent


# ---------------------------------------------------------------------------
# Tests: Governed Agent Execution
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _HAS_KAIZEN, reason="kailash-kaizen not installed")
class TestKaizenGovernedAgent:
    """Integration: PACT governance wrapping Kaizen agent tools."""

    def test_allowed_action_executes(self, governed_agent: PactGovernedAgent) -> None:
        """A registered, allowed action should execute the tool function."""
        call_log: list[str] = []

        def read_tool() -> str:
            call_log.append("read executed")
            return "data"

        result = governed_agent.execute_tool("read", _tool_fn=read_tool)
        assert result == "data"
        assert call_log == ["read executed"]

    def test_blocked_action_raises(self, governed_agent: PactGovernedAgent) -> None:
        """A registered but blocked action should raise GovernanceBlockedError."""
        call_log: list[str] = []

        def delete_tool() -> str:
            call_log.append("delete executed")
            return "deleted"

        with pytest.raises(GovernanceBlockedError):
            governed_agent.execute_tool("delete", _tool_fn=delete_tool)

        # Tool function should NEVER have been called
        assert call_log == []

    def test_unregistered_tool_blocked(self, governed_agent: PactGovernedAgent) -> None:
        """An unregistered tool should be blocked (default-deny)."""
        call_log: list[str] = []

        def deploy_tool() -> str:
            call_log.append("deploy executed")
            return "deployed"

        with pytest.raises(GovernanceBlockedError, match="not governance-registered"):
            governed_agent.execute_tool("deploy_to_prod", _tool_fn=deploy_tool)

        assert call_log == []

    def test_governance_context_is_frozen(
        self, governed_agent: PactGovernedAgent
    ) -> None:
        """Agent receives GovernanceContext which is frozen (anti-self-modification)."""
        ctx = governed_agent.context
        assert ctx is not None

        # Attempting to modify frozen context should raise
        with pytest.raises(AttributeError):
            ctx.role_address = "D1-R1-HACKED"  # type: ignore[misc]

    def test_engine_not_accessible(self, governed_agent: PactGovernedAgent) -> None:
        """Agent should NOT have public access to GovernanceEngine."""
        # _engine is private (convention, not enforcement)
        assert not hasattr(governed_agent, "engine")
        # But _engine exists internally
        assert hasattr(governed_agent, "_engine")

    def test_governed_action_with_cost(self, governed_agent: PactGovernedAgent) -> None:
        """A tool with cost within budget should execute."""
        call_log: list[str] = []

        def grade_tool() -> str:
            call_log.append("grade executed")
            return "A+"

        result = governed_agent.execute_tool("grade", _tool_fn=grade_tool)
        assert result == "A+"
        assert call_log == ["grade executed"]


# ---------------------------------------------------------------------------
# Tests: Audit Trail Integration
# ---------------------------------------------------------------------------


class TestGovernanceAuditIntegration:
    """Verify audit trail records governance decisions."""

    def test_audit_chain_records_decisions(self) -> None:
        """GovernanceEngine with audit_chain should record verify_action calls."""
        compiled, _ = create_university_org()
        audit_chain = AuditChain(chain_id="integration-test-chain")
        engine = GovernanceEngine(compiled, audit_chain=audit_chain)

        # Set up envelope
        envelope_config = ConstraintEnvelopeConfig(
            id="env-audit-test",
            operational=OperationalConstraintConfig(
                allowed_actions=["read"],
                blocked_actions=["delete"],
            ),
        )
        role_env = RoleEnvelope(
            id="re-audit-test",
            defining_role_address="D1-R1-D1-R1-D1-R1",
            target_role_address="D1-R1-D1-R1-D1-R1-T1-R1",
            envelope=envelope_config,
        )
        engine.set_role_envelope(role_env)

        # Perform actions
        engine.verify_action("D1-R1-D1-R1-D1-R1-T1-R1", "read", {})
        engine.verify_action("D1-R1-D1-R1-D1-R1-T1-R1", "delete", {})

        # Audit chain should have recorded decisions
        assert audit_chain.length >= 2

        # Chain integrity should be valid
        is_valid, errors = audit_chain.verify_chain_integrity()
        assert is_valid, f"Chain integrity errors: {errors}"

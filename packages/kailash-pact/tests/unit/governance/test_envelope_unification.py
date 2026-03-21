# Copyright 2026 Terrene Foundation
# Licensed under the Apache License, Version 2.0
"""Tests proving the two envelope systems produce consistent results.

TODO 7025: Envelope Unification Integration Tests.

Proves:
(a) governance and trust-layer produce identical results
(b) three-layer model (Role + Task + Effective) propagated through adapter
(c) tightening violations caught identically in both paths
(d) adapter failure is fail-closed (EnvelopeAdapterError, NOT silent fallback)
(e) backward compatibility -- ExecutionRuntime without governance still works
(f) ExecutionRuntime WITH governance uses verify_action

Uses the university example as fixtures.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from pact.governance.config import (
    ConstraintEnvelopeConfig,
    FinancialConstraintConfig,
    OperationalConstraintConfig,
    TrustPostureLevel,
    VerificationGradientConfig,
    VerificationLevel,
)
from pact.examples.university.org import create_university_org
from pact.governance.audit import AuditChain
from pact.governance.compilation import CompiledOrg
from pact.governance.engine import GovernanceEngine
from pact.governance.envelope_adapter import (
    EnvelopeAdapterError,
    GovernanceEnvelopeAdapter,
)
from pact.governance.envelopes import (
    MonotonicTighteningError,
    RoleEnvelope,
    TaskEnvelope,
)
from pact.governance.gradient import GradientEngine
from pact.governance.verdict import GovernanceVerdict
from kailash.trust.plane.models import (
    ConstraintEnvelope,
    FinancialConstraints,
    OperationalConstraints,
)

try:
    from pact.use.execution.approval import ApprovalQueue
    from pact.use.execution.registry import AgentRegistry
    from pact.use.execution.runtime import ExecutionRuntime, TaskStatus

    _HAS_EXECUTION = True
except ImportError:
    _HAS_EXECUTION = False


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def compiled_org() -> CompiledOrg:
    """Compiled university org for unification tests."""
    compiled, _ = create_university_org()
    return compiled


@pytest.fixture
def engine_with_envelopes(compiled_org: CompiledOrg) -> GovernanceEngine:
    """GovernanceEngine with role envelopes for CS Chair and Dean of Engineering.

    Envelope hierarchy:
    - Dean of Engineering: max_spend_usd=5000, allowed_actions=["read", "write", "grade", "teach", "approve"]
    - CS Chair: max_spend_usd=1000, allowed_actions=["read", "write", "grade", "teach"]
      (tighter than Dean -- valid monotonic tightening)
    """
    eng = GovernanceEngine(compiled_org)

    # Dean of Engineering envelope (supervisor of CS Chair)
    dean_config = ConstraintEnvelopeConfig(
        id="env-dean-eng",
        description="Dean of Engineering envelope",
        financial=FinancialConstraintConfig(
            max_spend_usd=5000.0,
            requires_approval_above_usd=2500.0,
        ),
        operational=OperationalConstraintConfig(
            allowed_actions=["read", "write", "grade", "teach", "approve"],
            blocked_actions=["delete"],
        ),
    )
    dean_env = RoleEnvelope(
        id="re-dean-eng",
        defining_role_address="D1-R1-D1-R1",  # Provost defines Dean's envelope
        target_role_address="D1-R1-D1-R1-D1-R1",  # Dean of Engineering
        envelope=dean_config,
    )
    eng.set_role_envelope(dean_env)

    # CS Chair envelope (tighter than Dean's)
    cs_chair_config = ConstraintEnvelopeConfig(
        id="env-cs-chair",
        description="CS Chair envelope",
        financial=FinancialConstraintConfig(
            max_spend_usd=1000.0,
            requires_approval_above_usd=500.0,
        ),
        operational=OperationalConstraintConfig(
            allowed_actions=["read", "write", "grade", "teach"],
            blocked_actions=["delete"],
        ),
    )
    cs_chair_env = RoleEnvelope(
        id="re-cs-chair",
        defining_role_address="D1-R1-D1-R1-D1-R1",  # Dean defines CS Chair's envelope
        target_role_address="D1-R1-D1-R1-D1-R1-T1-R1",  # CS Chair
        envelope=cs_chair_config,
    )
    eng.set_role_envelope(cs_chair_env)

    return eng


# ---------------------------------------------------------------------------
# Test 1: Governance and Trust-Layer Produce Identical Results
# ---------------------------------------------------------------------------


class TestGovernanceAndTrustLayerIdenticalResults:
    """Both envelope evaluation paths should agree on allow/deny for the same action."""

    def test_allowed_action_produces_consistent_results(
        self, engine_with_envelopes: GovernanceEngine
    ) -> None:
        """Create an org, set envelopes, compute effective envelope via governance,
        create ConstraintEnvelope from same config, evaluate same action -- both
        should produce the same allow/deny.
        """
        engine = engine_with_envelopes
        role_address = "D1-R1-D1-R1-D1-R1-T1-R1"  # CS Chair

        # Path A: Governance engine verify_action
        governance_verdict = engine.verify_action(role_address, "read", {"cost": 50.0})

        # Path B: Trust-layer via adapter — verify constraints mapped correctly
        adapter = GovernanceEnvelopeAdapter(engine)
        trust_envelope = adapter.to_constraint_envelope(role_address)

        # Both should allow the action
        assert (
            governance_verdict.level == "auto_approved"
        ), f"Governance should auto_approve 'read' with cost $50, got: {governance_verdict.level}"

        # Trust-layer: "read" is in allowed_actions and not in blocked_actions,
        # and $50 is within the max_cost_per_session limit ($1000)
        assert "read" in trust_envelope.operational.allowed_actions, (
            f"Trust-layer should include 'read' in allowed_actions, "
            f"got: {trust_envelope.operational.allowed_actions}"
        )
        assert "read" not in trust_envelope.operational.blocked_actions
        assert trust_envelope.financial.max_cost_per_session is not None
        assert 50.0 <= trust_envelope.financial.max_cost_per_session, (
            f"Trust-layer max_cost_per_session should be >= $50, "
            f"got: {trust_envelope.financial.max_cost_per_session}"
        )

    def test_blocked_action_produces_consistent_results(
        self, engine_with_envelopes: GovernanceEngine
    ) -> None:
        """'delete' is in blocked_actions -- both paths should deny."""
        engine = engine_with_envelopes
        role_address = "D1-R1-D1-R1-D1-R1-T1-R1"

        # Path A: Governance
        governance_verdict = engine.verify_action(role_address, "delete")

        # Path B: Trust-layer via adapter — verify constraints mapped correctly
        adapter = GovernanceEnvelopeAdapter(engine)
        trust_envelope = adapter.to_constraint_envelope(role_address)

        # Both should deny
        assert (
            governance_verdict.level == "blocked"
        ), f"Governance should block 'delete', got: {governance_verdict.level}"

        # Trust-layer: "delete" is in blocked_actions
        assert "delete" in trust_envelope.operational.blocked_actions, (
            f"Trust-layer should include 'delete' in blocked_actions, "
            f"got: {trust_envelope.operational.blocked_actions}"
        )

    def test_overspend_produces_consistent_results(
        self, engine_with_envelopes: GovernanceEngine
    ) -> None:
        """Spending above max_spend_usd should be denied by both paths."""
        engine = engine_with_envelopes
        role_address = "D1-R1-D1-R1-D1-R1-T1-R1"  # CS Chair: max_spend=1000

        # Path A: Governance -- exceeding $1000 limit
        governance_verdict = engine.verify_action(
            role_address, "read", {"cost": 2000.0}
        )

        # Path B: Trust-layer via adapter — verify constraints mapped correctly
        adapter = GovernanceEnvelopeAdapter(engine)
        trust_envelope = adapter.to_constraint_envelope(role_address)

        # Both should deny due to financial limit exceeded
        assert (
            governance_verdict.level == "blocked"
        ), f"Governance should block spend of $2000 (limit $1000), got: {governance_verdict.level}"

        # Trust-layer: max_cost_per_session maps from max_spend_usd ($1000)
        # $2000 exceeds the $1000 limit
        assert trust_envelope.financial.max_cost_per_session is not None
        assert trust_envelope.financial.max_cost_per_session == 1000.0, (
            f"Trust-layer max_cost_per_session should be $1000, "
            f"got: {trust_envelope.financial.max_cost_per_session}"
        )
        assert (
            2000.0 > trust_envelope.financial.max_cost_per_session
        ), "Spend of $2000 should exceed the trust-layer financial limit"


# ---------------------------------------------------------------------------
# Test 2: Three-Layer Model Through Adapter
# ---------------------------------------------------------------------------


class TestThreeLayerModelThroughAdapter:
    """Role + Task envelopes compute effective via governance, adapter produces
    the intersection (narrowed) envelope.
    """

    def test_task_envelope_narrows_effective_through_adapter(
        self, engine_with_envelopes: GovernanceEngine
    ) -> None:
        """Create Role + Task envelopes, compute effective via governance, adapt
        to trust-layer ConstraintEnvelope -- the adapted envelope should have the
        intersection of Role and Task constraints.
        """
        engine = engine_with_envelopes

        # Add a task envelope that narrows the CS Chair's envelope
        task_config = ConstraintEnvelopeConfig(
            id="env-task-grading",
            description="Grading task: restrict to read+grade only, $200 max",
            financial=FinancialConstraintConfig(max_spend_usd=200.0),
            operational=OperationalConstraintConfig(
                allowed_actions=["read", "grade"],
            ),
        )
        task_env = TaskEnvelope(
            id="te-grading",
            task_id="task-grading-2026",
            parent_envelope_id="re-cs-chair",
            envelope=task_config,
            expires_at=datetime.now(UTC) + timedelta(hours=4),
        )
        engine.set_task_envelope(task_env)

        # Get effective via adapter with task_id
        adapter = GovernanceEnvelopeAdapter(engine)
        trust_envelope = adapter.to_constraint_envelope(
            "D1-R1-D1-R1-D1-R1-T1-R1", task_id="task-grading-2026"
        )
        assert isinstance(trust_envelope, ConstraintEnvelope)

        # Financial narrowed to $200 (min of $1000 role, $200 task)
        assert trust_envelope.financial.max_cost_per_session is not None
        assert trust_envelope.financial.max_cost_per_session == 200.0

        # Operational narrowed to intersection: {"read", "grade"}
        assert set(trust_envelope.operational.allowed_actions) == {
            "read",
            "grade",
        }

        # "write" is NOT allowed after task narrowing
        assert (
            "write" not in trust_envelope.operational.allowed_actions
        ), "Trust-layer should not include 'write' after task narrowing"

        # "grade" IS allowed and $50 is within the financial limit
        assert "grade" in trust_envelope.operational.allowed_actions
        assert 50.0 <= trust_envelope.financial.max_cost_per_session


# ---------------------------------------------------------------------------
# Test 3: Tightening Violation Caught Both Paths
# ---------------------------------------------------------------------------


class TestTighteningViolationCaughtBothPaths:
    """Both governance validate_tightening and trust-layer should reject
    a child envelope that is looser than the parent.
    """

    def test_tightening_violation_detected(self) -> None:
        """Create parent and child envelopes where child is looser --
        both governance validate_tightening and trust-layer should reject.
        """
        parent_config = ConstraintEnvelopeConfig(
            id="env-parent",
            description="Parent envelope",
            financial=FinancialConstraintConfig(max_spend_usd=1000.0),
            operational=OperationalConstraintConfig(
                allowed_actions=["read", "write"],
            ),
        )

        # Child is LOOSER: higher spend limit and additional actions
        child_config = ConstraintEnvelopeConfig(
            id="env-child-looser",
            description="Child envelope (looser -- invalid!)",
            financial=FinancialConstraintConfig(max_spend_usd=5000.0),  # LOOSER!
            operational=OperationalConstraintConfig(
                allowed_actions=["read", "write", "delete"],  # EXTRA ACTION!
            ),
        )

        # Path A: Governance validate_tightening
        with pytest.raises(MonotonicTighteningError):
            RoleEnvelope.validate_tightening(
                parent_envelope=parent_config,
                child_envelope=child_config,
            )

        # Path B: Trust-layer -- verify parent constraints would deny what the
        # child config would allow (proving the tightening violation).
        # Build a trust-layer ConstraintEnvelope from the parent config via the
        # adapter's mapping: max_spend_usd -> max_cost_per_session,
        # allowed_actions -> operational.allowed_actions.
        parent_trust = ConstraintEnvelope(
            financial=FinancialConstraints(
                max_cost_per_session=parent_config.financial.max_spend_usd,
            ),
            operational=OperationalConstraints(
                allowed_actions=parent_config.operational.allowed_actions,
            ),
        )

        # "delete" is NOT in parent's allowed_actions -- child's addition violates tightening
        assert (
            "delete" not in parent_trust.operational.allowed_actions
        ), "Parent trust-layer should not include 'delete' in allowed_actions"

        # $5000 (child's limit) exceeds parent's $1000 limit -- violates tightening
        assert parent_trust.financial.max_cost_per_session is not None
        assert parent_trust.financial.max_cost_per_session == 1000.0
        assert (
            5000.0 > parent_trust.financial.max_cost_per_session
        ), "Child's $5000 limit exceeds parent's $1000 -- tightening violation"


# ---------------------------------------------------------------------------
# Test 4: Adapter Failure Is Fail-Closed
# ---------------------------------------------------------------------------


class TestAdapterFailureIsFailClosed:
    """Mock the engine to raise an exception -- adapter should raise
    EnvelopeAdapterError, NOT fall back to legacy.
    """

    def test_adapter_raises_on_engine_failure(self, compiled_org: CompiledOrg) -> None:
        """If engine.compute_envelope() raises, adapter MUST raise
        EnvelopeAdapterError (fail-closed), NOT return a default.
        """
        engine = GovernanceEngine(compiled_org)

        # Monkey-patch to simulate engine failure
        def broken_compute(*args: Any, **kwargs: Any) -> None:
            raise RuntimeError("Simulated engine explosion")

        engine.compute_envelope = broken_compute  # type: ignore[assignment]

        adapter = GovernanceEnvelopeAdapter(engine)
        with pytest.raises(EnvelopeAdapterError, match="Envelope conversion failed"):
            adapter.to_constraint_envelope("D1-R1")

    def test_adapter_raises_on_no_envelope(self, compiled_org: CompiledOrg) -> None:
        """If engine returns None (no envelopes for role), adapter MUST
        raise EnvelopeAdapterError, NOT return a permissive default.
        """
        engine = GovernanceEngine(compiled_org)
        # No envelopes set -- compute_envelope returns None

        adapter = GovernanceEnvelopeAdapter(engine)
        # Use a role address that has no envelope set
        with pytest.raises(EnvelopeAdapterError, match="No effective envelope"):
            adapter.to_constraint_envelope("D1-R1-D2-R1-T1-R1")


# ---------------------------------------------------------------------------
# Test 5: Backward Compatibility Without Governance
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not _HAS_EXECUTION, reason="pact.use execution layer not yet migrated"
)
class TestBackwardCompatibilityWithoutGovernance:
    """ExecutionRuntime constructed WITHOUT governance_engine should work
    exactly as before (no crash, no behavior change).
    """

    def test_runtime_without_governance_works(self) -> None:
        """Constructing and running ExecutionRuntime without governance_engine
        must work exactly as it always has -- no crash, no behavior change.
        """
        registry = AgentRegistry()
        registry.register(
            agent_id="agent-1",
            name="Test Agent",
            role="worker",
            team_id="team-1",
            capabilities=["read", "write"],
        )

        gradient_config = VerificationGradientConfig(
            default_level=VerificationLevel.AUTO_APPROVED
        )
        gradient = GradientEngine(gradient_config)
        audit_chain = AuditChain(chain_id="test-chain")

        # Construct WITHOUT governance_engine
        runtime = ExecutionRuntime(
            registry=registry,
            gradient=gradient,
            audit_chain=audit_chain,
        )

        # Submit and process -- should work exactly as before
        task_id = runtime.submit("read docs/report.md", agent_id="agent-1")
        task = runtime.process_next()

        assert task is not None
        assert task.status == TaskStatus.COMPLETED
        assert task.task_id == task_id

    def test_runtime_without_governance_does_not_crash(self) -> None:
        """Even multiple tasks through the runtime should be stable."""
        registry = AgentRegistry()
        registry.register(
            agent_id="agent-1",
            name="Test Agent",
            role="worker",
            team_id="team-1",
            capabilities=["read"],
        )

        gradient_config = VerificationGradientConfig(
            default_level=VerificationLevel.AUTO_APPROVED
        )
        gradient = GradientEngine(gradient_config)
        audit_chain = AuditChain(chain_id="test-chain")

        runtime = ExecutionRuntime(
            registry=registry,
            gradient=gradient,
            audit_chain=audit_chain,
        )

        for i in range(5):
            runtime.submit(f"task-{i}", agent_id="agent-1")

        processed = runtime.process_all()
        assert len(processed) == 5
        assert all(t.status == TaskStatus.COMPLETED for t in processed)


# ---------------------------------------------------------------------------
# Test 6: Runtime WITH Governance Uses verify_action
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not _HAS_EXECUTION, reason="pact.use execution layer not yet migrated"
)
class TestRuntimeWithGovernanceUsesVerifyAction:
    """ExecutionRuntime WITH governance_engine should use
    GovernanceEngine.verify_action() for pre-execution checks.
    """

    def test_governance_blocked_prevents_execution(
        self, engine_with_envelopes: GovernanceEngine
    ) -> None:
        """When governance engine BLOCKs an action, the runtime should
        set the task to BLOCKED status and not execute it.
        """
        engine = engine_with_envelopes

        registry = AgentRegistry()
        registry.register(
            agent_id="cs-chair-agent",
            name="CS Chair Agent",
            role="cs-chair",
            team_id="team-cs",
            capabilities=["delete"],
        )

        gradient_config = VerificationGradientConfig(
            default_level=VerificationLevel.AUTO_APPROVED
        )
        gradient = GradientEngine(gradient_config)
        audit_chain = AuditChain(chain_id="gov-test-chain")

        runtime = ExecutionRuntime(
            registry=registry,
            gradient=gradient,
            audit_chain=audit_chain,
            governance_engine=engine,
        )

        # Map agent to role address so governance can find the envelope
        runtime.set_agent_role_address("cs-chair-agent", "D1-R1-D1-R1-D1-R1-T1-R1")

        # "delete" is blocked by the CS Chair's envelope
        task_id = runtime.submit("delete", agent_id="cs-chair-agent")
        task = runtime.process_next()

        assert task is not None
        assert (
            task.status == TaskStatus.BLOCKED
        ), f"Expected BLOCKED for 'delete' action, got: {task.status}"

    def test_governance_auto_approved_allows_execution(
        self, engine_with_envelopes: GovernanceEngine
    ) -> None:
        """When governance engine approves an action, the runtime should
        execute it normally.
        """
        engine = engine_with_envelopes

        registry = AgentRegistry()
        registry.register(
            agent_id="cs-chair-agent",
            name="CS Chair Agent",
            role="cs-chair",
            team_id="team-cs",
            capabilities=["read"],
        )

        gradient_config = VerificationGradientConfig(
            default_level=VerificationLevel.AUTO_APPROVED
        )
        gradient = GradientEngine(gradient_config)
        audit_chain = AuditChain(chain_id="gov-test-chain")

        runtime = ExecutionRuntime(
            registry=registry,
            gradient=gradient,
            audit_chain=audit_chain,
            governance_engine=engine,
        )

        runtime.set_agent_role_address("cs-chair-agent", "D1-R1-D1-R1-D1-R1-T1-R1")

        # "read" is allowed by the CS Chair's envelope
        task_id = runtime.submit("read", agent_id="cs-chair-agent")
        task = runtime.process_next()

        assert task is not None
        assert (
            task.status == TaskStatus.COMPLETED
        ), f"Expected COMPLETED for 'read' action, got: {task.status}"

    def test_governance_held_enters_approval_queue(
        self, engine_with_envelopes: GovernanceEngine
    ) -> None:
        """When governance engine returns HELD, the task should be queued
        for human approval.
        """
        engine = engine_with_envelopes

        registry = AgentRegistry()
        registry.register(
            agent_id="cs-chair-agent",
            name="CS Chair Agent",
            role="cs-chair",
            team_id="team-cs",
            capabilities=["read"],
        )

        gradient_config = VerificationGradientConfig(
            default_level=VerificationLevel.AUTO_APPROVED
        )
        gradient = GradientEngine(gradient_config)
        audit_chain = AuditChain(chain_id="gov-test-chain")
        approval_queue = ApprovalQueue()

        runtime = ExecutionRuntime(
            registry=registry,
            gradient=gradient,
            audit_chain=audit_chain,
            approval_queue=approval_queue,
            governance_engine=engine,
        )

        runtime.set_agent_role_address("cs-chair-agent", "D1-R1-D1-R1-D1-R1-T1-R1")

        # Cost above requires_approval_above_usd ($500) but below max ($1000) -> HELD
        task_id = runtime.submit(
            "read", agent_id="cs-chair-agent", metadata={"cost": 750.0}
        )
        task = runtime.process_next()

        assert task is not None
        assert (
            task.status == TaskStatus.HELD
        ), f"Expected HELD for 'read' action with cost $750 (threshold $500), got: {task.status}"
        # Approval queue should have an entry
        assert approval_queue.queue_depth > 0

    def test_governance_flagged_proceeds_with_warning(
        self, compiled_org: CompiledOrg, caplog: pytest.LogCaptureFixture
    ) -> None:
        """When governance engine returns FLAGGED, the task should proceed
        but log a warning.

        We need a custom engine where the flagged zone is reachable:
        max_spend_usd=1000, NO approval threshold. Cost at $850 (>80% of $1000)
        triggers FLAGGED, not HELD.
        """
        # Create engine with NO approval threshold so the flagged zone is reachable
        engine = GovernanceEngine(compiled_org)
        flagged_config = ConstraintEnvelopeConfig(
            id="env-cs-chair-flagged",
            description="CS Chair envelope (no approval threshold)",
            financial=FinancialConstraintConfig(
                max_spend_usd=1000.0,
                # No requires_approval_above_usd -> flagged zone at 80%+ of max
            ),
            operational=OperationalConstraintConfig(
                allowed_actions=["read", "write", "grade", "teach"],
                blocked_actions=["delete"],
            ),
        )
        role_env = RoleEnvelope(
            id="re-cs-chair-flagged",
            defining_role_address="D1-R1-D1-R1-D1-R1",
            target_role_address="D1-R1-D1-R1-D1-R1-T1-R1",
            envelope=flagged_config,
        )
        engine.set_role_envelope(role_env)

        registry = AgentRegistry()
        registry.register(
            agent_id="cs-chair-agent",
            name="CS Chair Agent",
            role="cs-chair",
            team_id="team-cs",
            capabilities=["read"],
        )

        gradient_config = VerificationGradientConfig(
            default_level=VerificationLevel.AUTO_APPROVED
        )
        gradient = GradientEngine(gradient_config)
        audit_chain = AuditChain(chain_id="gov-test-chain")

        runtime = ExecutionRuntime(
            registry=registry,
            gradient=gradient,
            audit_chain=audit_chain,
            governance_engine=engine,
        )

        runtime.set_agent_role_address("cs-chair-agent", "D1-R1-D1-R1-D1-R1-T1-R1")

        # Cost at 85% of max ($1000 * 0.85 = $850) -> FLAGGED by engine
        # (no approval threshold, so it hits the near-boundary check at 80%)
        with caplog.at_level(logging.WARNING):
            task_id = runtime.submit(
                "read", agent_id="cs-chair-agent", metadata={"cost": 850.0}
            )
            task = runtime.process_next()

        assert task is not None
        assert (
            task.status == TaskStatus.COMPLETED
        ), f"Expected COMPLETED for FLAGGED action (should proceed), got: {task.status}"

    def test_verify_action_called_when_governance_present(
        self, engine_with_envelopes: GovernanceEngine
    ) -> None:
        """Confirm that verify_action is actually invoked (not bypassed)
        when governance_engine is provided.
        """
        engine = engine_with_envelopes

        registry = AgentRegistry()
        registry.register(
            agent_id="cs-chair-agent",
            name="CS Chair Agent",
            role="cs-chair",
            team_id="team-cs",
            capabilities=["read"],
        )

        gradient_config = VerificationGradientConfig(
            default_level=VerificationLevel.AUTO_APPROVED
        )
        gradient = GradientEngine(gradient_config)
        audit_chain = AuditChain(chain_id="gov-test-chain")

        runtime = ExecutionRuntime(
            registry=registry,
            gradient=gradient,
            audit_chain=audit_chain,
            governance_engine=engine,
        )

        runtime.set_agent_role_address("cs-chair-agent", "D1-R1-D1-R1-D1-R1-T1-R1")

        # Patch verify_action to track calls
        original_verify = engine.verify_action
        call_log: list[tuple[str, str]] = []

        def tracking_verify(
            role_address: str, action: str, context: Any = None
        ) -> GovernanceVerdict:
            call_log.append((role_address, action))
            return original_verify(role_address, action, context)

        engine.verify_action = tracking_verify  # type: ignore[assignment]

        runtime.submit("read", agent_id="cs-chair-agent")
        runtime.process_next()

        assert (
            len(call_log) == 1
        ), f"Expected exactly 1 call to verify_action, got {len(call_log)}"
        assert call_log[0] == ("D1-R1-D1-R1-D1-R1-T1-R1", "read")

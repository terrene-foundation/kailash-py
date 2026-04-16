"""
Unit Tests for Trust Posture v2 Features (Tier 1)

Tests the 5-posture model and PostureStateMachine.
Part of CARE-026 posture upgrade.

Coverage:
- TrustPosture 5 postures with autonomy_level
- Comparison operators
- PostureTransition enum
- TransitionGuard dataclass
- PostureTransitionRequest dataclass
- TransitionResult dataclass
- PostureStateMachine
- Backward compatibility
"""

from datetime import datetime
from typing import Any, Dict, Optional

import pytest
from kailash.trust.posture.postures import (
    PostureConstraints,
    PostureResult,
    PostureStateMachine,
    PostureTransition,
    PostureTransitionRequest,
    TransitionGuard,
    TransitionResult,
    TrustPosture,
    TrustPostureMapper,
    get_posture_for_action,
    map_verification_to_posture,
)


class TestTrustPosture5Postures:
    """Test 5-posture model with autonomy levels.

    Canonical scale per Decision 007 (src/kailash/trust/posture/postures.py):
    AUTONOMOUS=5, DELEGATING=4, SUPERVISED=3, TOOL=2, PSEUDO=1. Wire values
    match the lowercase member name (``"autonomous"`` etc.).
    """

    def test_five_postures_exist(self):
        """Test all 5 canonical postures exist with lowercase wire values."""
        assert len(TrustPosture) == 5
        assert TrustPosture.AUTONOMOUS.value == "autonomous"
        assert TrustPosture.DELEGATING.value == "delegating"
        assert TrustPosture.SUPERVISED.value == "supervised"
        assert TrustPosture.TOOL.value == "tool"
        assert TrustPosture.PSEUDO.value == "pseudo"

    def test_autonomy_levels(self):
        """Test autonomy_level property for each posture."""
        assert TrustPosture.AUTONOMOUS.autonomy_level == 5
        assert TrustPosture.DELEGATING.autonomy_level == 4
        assert TrustPosture.SUPERVISED.autonomy_level == 3
        assert TrustPosture.TOOL.autonomy_level == 2
        assert TrustPosture.PSEUDO.autonomy_level == 1

    def test_can_upgrade_to(self):
        """Test can_upgrade_to method uses strict inequality of autonomy_level."""
        # PSEUDO (1) can upgrade to anything higher
        assert TrustPosture.PSEUDO.can_upgrade_to(TrustPosture.TOOL) is True
        assert TrustPosture.PSEUDO.can_upgrade_to(TrustPosture.SUPERVISED) is True
        assert TrustPosture.PSEUDO.can_upgrade_to(TrustPosture.DELEGATING) is True
        assert TrustPosture.PSEUDO.can_upgrade_to(TrustPosture.AUTONOMOUS) is True
        # Same posture is not an upgrade
        assert TrustPosture.PSEUDO.can_upgrade_to(TrustPosture.PSEUDO) is False

        # SUPERVISED (3) can upgrade to DELEGATING (4) and AUTONOMOUS (5)
        assert TrustPosture.SUPERVISED.can_upgrade_to(TrustPosture.DELEGATING) is True
        assert TrustPosture.SUPERVISED.can_upgrade_to(TrustPosture.AUTONOMOUS) is True
        # Cannot upgrade to lower or same
        assert TrustPosture.SUPERVISED.can_upgrade_to(TrustPosture.TOOL) is False
        assert TrustPosture.SUPERVISED.can_upgrade_to(TrustPosture.SUPERVISED) is False

        # AUTONOMOUS (5) is the top — no upgrades
        assert TrustPosture.AUTONOMOUS.can_upgrade_to(TrustPosture.AUTONOMOUS) is False
        assert TrustPosture.AUTONOMOUS.can_upgrade_to(TrustPosture.PSEUDO) is False

    def test_can_downgrade_to(self):
        """Test can_downgrade_to method uses strict inequality of autonomy_level."""
        # AUTONOMOUS (5) can downgrade to any lower posture
        assert TrustPosture.AUTONOMOUS.can_downgrade_to(TrustPosture.DELEGATING) is True
        assert TrustPosture.AUTONOMOUS.can_downgrade_to(TrustPosture.SUPERVISED) is True
        assert TrustPosture.AUTONOMOUS.can_downgrade_to(TrustPosture.TOOL) is True
        assert TrustPosture.AUTONOMOUS.can_downgrade_to(TrustPosture.PSEUDO) is True

        # SUPERVISED (3) can downgrade to TOOL (2) or PSEUDO (1)
        assert TrustPosture.SUPERVISED.can_downgrade_to(TrustPosture.TOOL) is True
        assert TrustPosture.SUPERVISED.can_downgrade_to(TrustPosture.PSEUDO) is True
        # Cannot downgrade to higher or same
        assert (
            TrustPosture.SUPERVISED.can_downgrade_to(TrustPosture.DELEGATING) is False
        )
        assert (
            TrustPosture.SUPERVISED.can_downgrade_to(TrustPosture.SUPERVISED) is False
        )

        # PSEUDO (1) is the bottom — no downgrades
        assert TrustPosture.PSEUDO.can_downgrade_to(TrustPosture.PSEUDO) is False


class TestPostureComparison:
    """Test comparison operators."""

    def test_less_than(self):
        """Test __lt__ operator against the five canonical postures."""
        # Strictly lower autonomy level → less-than is True
        assert TrustPosture.PSEUDO < TrustPosture.TOOL
        assert TrustPosture.PSEUDO < TrustPosture.SUPERVISED
        assert TrustPosture.TOOL < TrustPosture.SUPERVISED
        assert TrustPosture.SUPERVISED < TrustPosture.DELEGATING
        assert TrustPosture.DELEGATING < TrustPosture.AUTONOMOUS

        # Reverse and equal comparisons return False
        assert not (TrustPosture.AUTONOMOUS < TrustPosture.PSEUDO)
        assert not (TrustPosture.SUPERVISED < TrustPosture.SUPERVISED)

    def test_less_than_or_equal(self):
        """Test __le__ operator."""
        assert TrustPosture.PSEUDO <= TrustPosture.PSEUDO
        assert TrustPosture.SUPERVISED <= TrustPosture.SUPERVISED
        assert TrustPosture.SUPERVISED <= TrustPosture.AUTONOMOUS

        assert not (TrustPosture.AUTONOMOUS <= TrustPosture.PSEUDO)

    def test_greater_than(self):
        """Test __gt__ operator against the five canonical postures."""
        assert TrustPosture.AUTONOMOUS > TrustPosture.DELEGATING
        assert TrustPosture.DELEGATING > TrustPosture.SUPERVISED
        assert TrustPosture.SUPERVISED > TrustPosture.TOOL
        assert TrustPosture.TOOL > TrustPosture.PSEUDO

        assert not (TrustPosture.PSEUDO > TrustPosture.AUTONOMOUS)
        assert not (TrustPosture.SUPERVISED > TrustPosture.SUPERVISED)

    def test_greater_than_or_equal(self):
        """Test __ge__ operator."""
        assert TrustPosture.AUTONOMOUS >= TrustPosture.SUPERVISED
        assert TrustPosture.SUPERVISED >= TrustPosture.SUPERVISED
        assert TrustPosture.PSEUDO >= TrustPosture.PSEUDO

        assert not (TrustPosture.PSEUDO >= TrustPosture.AUTONOMOUS)

    def test_comparison_ordering(self):
        """Test that postures can be sorted by autonomy level."""
        postures = [
            TrustPosture.SUPERVISED,
            TrustPosture.AUTONOMOUS,
            TrustPosture.PSEUDO,
            TrustPosture.TOOL,
            TrustPosture.DELEGATING,
        ]
        sorted_postures = sorted(postures)

        assert sorted_postures == [
            TrustPosture.PSEUDO,
            TrustPosture.TOOL,
            TrustPosture.SUPERVISED,
            TrustPosture.DELEGATING,
            TrustPosture.AUTONOMOUS,
        ]


class TestPostureTransition:
    """Test PostureTransition enum."""

    def test_transition_values(self):
        """Test transition type values."""
        assert PostureTransition.UPGRADE.value == "upgrade"
        assert PostureTransition.DOWNGRADE.value == "downgrade"
        assert PostureTransition.MAINTAIN.value == "maintain"
        assert PostureTransition.EMERGENCY_DOWNGRADE.value == "emergency_downgrade"


class TestPostureTransitionRequest:
    """Test PostureTransitionRequest dataclass."""

    def test_upgrade_detection(self):
        """Test is_upgrade property with a strictly-higher target posture.

        transition_type compares ``from_posture.autonomy_level`` to
        ``to_posture.autonomy_level``; SUPERVISED→DELEGATING (3→4) is the
        canonical minimal upgrade step on the five-posture scale.
        """
        request = PostureTransitionRequest(
            agent_id="agent-001",
            from_posture=TrustPosture.SUPERVISED,
            to_posture=TrustPosture.DELEGATING,
        )
        assert request.is_upgrade is True
        assert request.is_downgrade is False
        assert request.transition_type == PostureTransition.UPGRADE

    def test_downgrade_detection(self):
        """Test is_downgrade property."""
        request = PostureTransitionRequest(
            agent_id="agent-001",
            from_posture=TrustPosture.AUTONOMOUS,
            to_posture=TrustPosture.SUPERVISED,
        )
        assert request.is_upgrade is False
        assert request.is_downgrade is True
        assert request.transition_type == PostureTransition.DOWNGRADE

    def test_maintain_detection(self):
        """Test maintain transition type."""
        request = PostureTransitionRequest(
            agent_id="agent-001",
            from_posture=TrustPosture.SUPERVISED,
            to_posture=TrustPosture.SUPERVISED,
        )
        assert request.is_upgrade is False
        assert request.is_downgrade is False
        assert request.transition_type == PostureTransition.MAINTAIN

    def test_request_metadata(self):
        """Test request with metadata."""
        request = PostureTransitionRequest(
            agent_id="agent-001",
            from_posture=TrustPosture.PSEUDO,
            to_posture=TrustPosture.SUPERVISED,
            reason="Agent behavior improved",
            requester_id="admin-001",
            metadata={"review_id": "review-123"},
        )
        assert request.agent_id == "agent-001"
        assert request.reason == "Agent behavior improved"
        assert request.requester_id == "admin-001"
        assert request.metadata == {"review_id": "review-123"}


class TestTransitionResult:
    """Test TransitionResult dataclass."""

    def test_successful_result(self):
        """Test successful transition result."""
        result = TransitionResult(
            success=True,
            from_posture=TrustPosture.SUPERVISED,
            to_posture=TrustPosture.SUPERVISED,
            transition_type=PostureTransition.UPGRADE,
            reason="Proven reliable",
        )
        assert result.success is True
        assert result.blocked_by is None

    def test_blocked_result(self):
        """Test blocked transition result."""
        result = TransitionResult(
            success=False,
            from_posture=TrustPosture.SUPERVISED,
            to_posture=TrustPosture.AUTONOMOUS,
            transition_type=PostureTransition.UPGRADE,
            reason="Missing approval",
            blocked_by="upgrade_approval_required",
        )
        assert result.success is False
        assert result.blocked_by == "upgrade_approval_required"

    def test_to_dict(self):
        """Test serialization using canonical posture wire strings.

        TransitionResult.to_dict serialises postures via ``.value``, which
        for the canonical enum is the lowercase member name. Pre-Decision-007
        strings like ``"blocked"`` are no longer emitted.
        """
        result = TransitionResult(
            success=True,
            from_posture=TrustPosture.PSEUDO,
            to_posture=TrustPosture.SUPERVISED,
            transition_type=PostureTransition.UPGRADE,
            reason="Test",
        )
        data = result.to_dict()

        assert data["success"] is True
        assert data["from_posture"] == "pseudo"
        assert data["to_posture"] == "supervised"
        assert data["transition_type"] == "upgrade"
        assert "timestamp" in data


class TestTransitionGuard:
    """Test TransitionGuard dataclass."""

    def test_guard_applies_to_upgrade(self):
        """Test guard that applies to upgrades.

        Guard.check returns True whenever the transition type is outside
        ``applies_to``. To exercise the ``applies_to`` match and the mismatch,
        the upgrade requests must cross an autonomy_level boundary
        (SUPERVISED→DELEGATING) and the non-upgrade request must go in the
        opposite direction (AUTONOMOUS→SUPERVISED).
        """
        guard = TransitionGuard(
            name="test_guard",
            check_fn=lambda req: req.requester_id is not None,
            applies_to=[PostureTransition.UPGRADE],
            reason_on_failure="Requester ID required",
        )

        # Upgrade without requester_id should fail
        upgrade_request = PostureTransitionRequest(
            agent_id="agent-001",
            from_posture=TrustPosture.SUPERVISED,
            to_posture=TrustPosture.DELEGATING,
        )
        assert guard.check(upgrade_request) is False

        # Upgrade with requester_id should pass
        upgrade_request_approved = PostureTransitionRequest(
            agent_id="agent-001",
            from_posture=TrustPosture.SUPERVISED,
            to_posture=TrustPosture.DELEGATING,
            requester_id="admin-001",
        )
        assert guard.check(upgrade_request_approved) is True

        # Downgrade should pass (guard doesn't apply)
        downgrade_request = PostureTransitionRequest(
            agent_id="agent-001",
            from_posture=TrustPosture.AUTONOMOUS,
            to_posture=TrustPosture.SUPERVISED,
        )
        assert guard.check(downgrade_request) is True  # Guard doesn't apply


class TestPostureStateMachine:
    """Test PostureStateMachine class."""

    def test_default_initialization(self):
        """Test default initialization.

        ``PostureStateMachine`` defaults ``default_posture`` to
        ``TrustPosture.TOOL`` per CARE spec RT-17: tool agents start at
        autonomy_level=2 and escalate from there.
        """
        machine = PostureStateMachine()
        assert machine.get_posture("unknown-agent") == TrustPosture.TOOL

    def test_set_and_get_posture(self):
        """Test set_posture and get_posture."""
        machine = PostureStateMachine()
        machine.set_posture("agent-001", TrustPosture.AUTONOMOUS)
        assert machine.get_posture("agent-001") == TrustPosture.AUTONOMOUS

    def test_successful_upgrade_with_approval(self):
        """Test successful upgrade when requester_id is provided.

        Upgrade = strictly higher autonomy_level. SUPERVISED(3)→DELEGATING(4)
        is the canonical minimal upgrade on the five-posture scale.
        """
        machine = PostureStateMachine()
        machine.set_posture("agent-001", TrustPosture.SUPERVISED)

        result = machine.transition(
            PostureTransitionRequest(
                agent_id="agent-001",
                from_posture=TrustPosture.SUPERVISED,
                to_posture=TrustPosture.DELEGATING,
                reason="Agent proven reliable",
                requester_id="admin-001",
            )
        )

        assert result.success is True
        assert result.transition_type == PostureTransition.UPGRADE
        assert machine.get_posture("agent-001") == TrustPosture.DELEGATING

    def test_upgrade_blocked_without_approval(self):
        """Test upgrade is blocked when requester_id is missing.

        The default ``upgrade_approval_required`` guard blocks any upgrade
        whose request carries no requester_id. The transition must be a
        real upgrade (SUPERVISED→DELEGATING) to invoke the guard.
        """
        machine = PostureStateMachine()
        machine.set_posture("agent-001", TrustPosture.SUPERVISED)

        result = machine.transition(
            PostureTransitionRequest(
                agent_id="agent-001",
                from_posture=TrustPosture.SUPERVISED,
                to_posture=TrustPosture.DELEGATING,
                reason="Upgrade attempt without approval",
            )
        )

        assert result.success is False
        assert result.blocked_by == "upgrade_approval_required"
        # Posture should not have changed
        assert machine.get_posture("agent-001") == TrustPosture.SUPERVISED

    def test_downgrade_allowed_without_approval(self):
        """Test downgrade works without requester_id."""
        machine = PostureStateMachine()
        machine.set_posture("agent-001", TrustPosture.AUTONOMOUS)

        result = machine.transition(
            PostureTransitionRequest(
                agent_id="agent-001",
                from_posture=TrustPosture.AUTONOMOUS,
                to_posture=TrustPosture.SUPERVISED,
                reason="Security concern",
            )
        )

        assert result.success is True
        assert result.transition_type == PostureTransition.DOWNGRADE
        assert machine.get_posture("agent-001") == TrustPosture.SUPERVISED

    def test_transition_posture_mismatch(self):
        """Test transition fails when from_posture doesn't match current."""
        machine = PostureStateMachine()
        machine.set_posture("agent-001", TrustPosture.SUPERVISED)

        result = machine.transition(
            PostureTransitionRequest(
                agent_id="agent-001",
                from_posture=TrustPosture.PSEUDO,  # Wrong!
                to_posture=TrustPosture.SUPERVISED,
                requester_id="admin-001",
            )
        )

        assert result.success is False
        assert "does not match" in result.reason

    def test_emergency_downgrade(self):
        """Test emergency_downgrade bypasses guards."""
        machine = PostureStateMachine()
        machine.set_posture("agent-001", TrustPosture.AUTONOMOUS)

        result = machine.emergency_downgrade(
            agent_id="agent-001",
            reason="Security breach detected",
            requester_id="security-system",
        )

        assert result.success is True
        assert result.transition_type == PostureTransition.EMERGENCY_DOWNGRADE
        assert result.to_posture == TrustPosture.PSEUDO
        assert machine.get_posture("agent-001") == TrustPosture.PSEUDO

    def test_emergency_downgrade_from_any_posture(self):
        """Test emergency_downgrade works from any posture."""
        machine = PostureStateMachine()

        for posture in TrustPosture:
            machine.set_posture("agent-001", posture)
            result = machine.emergency_downgrade("agent-001", "Emergency")
            assert result.success is True
            assert machine.get_posture("agent-001") == TrustPosture.PSEUDO

    def test_transition_history(self):
        """Test transition history is recorded."""
        machine = PostureStateMachine()
        machine.set_posture("agent-001", TrustPosture.SUPERVISED)

        # Perform some transitions — SUPERVISED→DELEGATING is a real upgrade
        machine.transition(
            PostureTransitionRequest(
                agent_id="agent-001",
                from_posture=TrustPosture.SUPERVISED,
                to_posture=TrustPosture.DELEGATING,
                requester_id="admin-001",
            )
        )
        machine.emergency_downgrade("agent-001", "Test emergency")

        history = machine.get_transition_history()
        assert len(history) == 2
        assert history[0].transition_type == PostureTransition.UPGRADE
        assert history[1].transition_type == PostureTransition.EMERGENCY_DOWNGRADE

    def test_transition_history_limit(self):
        """Test transition history with limit."""
        machine = PostureStateMachine()
        machine.set_posture("agent-001", TrustPosture.SUPERVISED)

        # Perform multiple transitions
        for i in range(5):
            machine.set_posture("agent-001", TrustPosture.SUPERVISED)
            machine.transition(
                PostureTransitionRequest(
                    agent_id="agent-001",
                    from_posture=TrustPosture.SUPERVISED,
                    to_posture=TrustPosture.SUPERVISED,
                    requester_id="admin-001",
                )
            )

        history = machine.get_transition_history(limit=3)
        assert len(history) == 3

    def test_add_guard(self):
        """Test adding custom guard."""
        machine = PostureStateMachine(require_upgrade_approval=False)

        # Add a guard that blocks upgrades to FULL_AUTONOMY
        machine.add_guard(
            TransitionGuard(
                name="no_full_autonomy",
                check_fn=lambda req: req.to_posture != TrustPosture.AUTONOMOUS,
                applies_to=[PostureTransition.UPGRADE],
                reason_on_failure="Full autonomy not allowed",
            )
        )

        machine.set_posture("agent-001", TrustPosture.SUPERVISED)

        result = machine.transition(
            PostureTransitionRequest(
                agent_id="agent-001",
                from_posture=TrustPosture.SUPERVISED,
                to_posture=TrustPosture.AUTONOMOUS,
            )
        )

        assert result.success is False
        assert result.blocked_by == "no_full_autonomy"

    def test_remove_guard(self):
        """Test removing a guard."""
        machine = PostureStateMachine()
        assert "upgrade_approval_required" in machine.list_guards()

        removed = machine.remove_guard("upgrade_approval_required")
        assert removed is True
        assert "upgrade_approval_required" not in machine.list_guards()

    def test_remove_nonexistent_guard(self):
        """Test removing a guard that doesn't exist."""
        machine = PostureStateMachine()
        removed = machine.remove_guard("nonexistent_guard")
        assert removed is False

    def test_list_guards(self):
        """Test listing guards."""
        machine = PostureStateMachine()
        guards = machine.list_guards()
        assert "upgrade_approval_required" in guards

    def test_no_approval_guard_when_disabled(self):
        """Test that approval guard is not added when disabled."""
        machine = PostureStateMachine(require_upgrade_approval=False)
        assert "upgrade_approval_required" not in machine.list_guards()


class TestBackwardCompatibility:
    """Test backward compatibility with existing classes."""

    def test_posture_constraints_still_works(self):
        """Test PostureConstraints still functions as before."""
        constraints = PostureConstraints(
            audit_required=True,
            approval_required=True,
            log_level="warning",
            allowed_capabilities=["read"],
            blocked_capabilities=["delete"],
            max_actions_before_review=5,
            require_human_approval_for=["execute_code"],
            metadata={"policy": "strict"},
        )

        assert constraints.audit_required is True
        assert constraints.approval_required is True
        assert constraints.log_level == "warning"

        data = constraints.to_dict()
        assert data["audit_required"] is True
        assert data["allowed_capabilities"] == ["read"]

    def test_posture_result_still_works(self):
        """Test PostureResult still functions as before."""
        result = PostureResult(
            posture=TrustPosture.SUPERVISED,
            constraints=PostureConstraints(audit_required=True),
            reason="Test reason",
            verification_details={"key": "value"},
        )

        assert result.posture == TrustPosture.SUPERVISED
        assert result.constraints.audit_required is True
        assert result.reason == "Test reason"

        data = result.to_dict()
        assert data["posture"] == "supervised"

    def test_trust_posture_mapper_still_works(self):
        """Test TrustPostureMapper still functions as before."""
        mapper = TrustPostureMapper()

        # Test map_to_posture
        result = mapper.map_to_posture(
            is_valid=True,
            trust_level="high",
        )
        assert result.posture == TrustPosture.AUTONOMOUS

        result = mapper.map_to_posture(
            is_valid=False,
        )
        assert result.posture == TrustPosture.PSEUDO

    def test_trust_posture_is_string_enum(self):
        """Test TrustPosture still inherits from str and emits canonical values."""
        assert isinstance(TrustPosture.AUTONOMOUS, str)
        assert TrustPosture.SUPERVISED == "supervised"
        # Canonical wire value is the lowercase member name
        assert TrustPosture.PSEUDO.value == "pseudo"

    def test_get_posture_for_action_returns_delegating_for_audit(self):
        """Test get_posture_for_action returns DELEGATING for audit-only.

        ``get_posture_for_action`` branch (src/kailash/trust/posture/postures.py):
        allowed + audit + no approval → DELEGATING. Pre-Decision-007 this was
        ASSISTED which lives today as DELEGATING on the canonical five-posture
        scale.
        """
        posture = get_posture_for_action(
            is_allowed=True,
            requires_audit=True,
        )
        assert posture == TrustPosture.DELEGATING

    def test_get_posture_for_action_still_returns_blocked(self):
        """Test get_posture_for_action still returns PSEUDO when not allowed.

        PSEUDO replaces the pre-Decision-007 BLOCKED name; the semantic
        (agent cannot execute) is preserved.
        """
        posture = get_posture_for_action(is_allowed=False)
        assert posture == TrustPosture.PSEUDO

    def test_get_posture_for_action_still_returns_tool_for_approval(self):
        """Test get_posture_for_action returns TOOL when approval is required.

        Pre-Decision-007 HUMAN_DECIDES branch collapses to TOOL — human
        co-plans the action and agent executes approved plans.
        """
        posture = get_posture_for_action(
            is_allowed=True,
            requires_approval=True,
        )
        assert posture == TrustPosture.TOOL


class TestAssistedPostureMapping:
    """Test DELEGATING posture (formerly ASSISTED) is used appropriately.

    Pre-Decision-007 the ASSISTED posture covered the "audit-required +
    normal-or-higher trust" case. That case now maps to DELEGATING: agent
    executes autonomously while the human monitors via audit, which matches
    the semantic of "operator watches, agent acts". The low-trust path
    still maps to SUPERVISED.
    """

    def test_mapper_returns_delegating_for_audit_with_normal_trust(self):
        """Test mapper returns DELEGATING when audit required with normal trust."""
        mapper = TrustPostureMapper()
        result = mapper.map_to_posture(
            is_valid=True,
            trust_level="normal",
            audit_required=True,
        )
        assert result.posture == TrustPosture.DELEGATING

    def test_mapper_returns_supervised_for_low_trust(self):
        """Test mapper returns SUPERVISED for low trust level."""
        mapper = TrustPostureMapper()
        result = mapper.map_to_posture(
            is_valid=True,
            trust_level="low",
        )
        assert result.posture == TrustPosture.SUPERVISED

    def test_mapper_verification_result_delegating(self):
        """Test map_verification_result uses DELEGATING for audit+normal trust."""

        class MockVerification:
            valid = True
            constraints = {"audit_required": True, "trust_level": "normal"}

        mapper = TrustPostureMapper()
        result = mapper.map_verification_result(MockVerification())
        assert result.posture == TrustPosture.DELEGATING


class TestAllExports:
    """Test all exports are available."""

    def test_all_exports(self):
        """Test all expected exports are in __all__."""
        from kailash.trust.posture.postures import __all__

        expected = [
            "TrustPosture",
            "PostureTransition",
            "PostureConstraints",
            "PostureResult",
            "TransitionGuard",
            "PostureTransitionRequest",
            "TransitionResult",
            "TrustPostureMapper",
            "PostureStateMachine",
            "map_verification_to_posture",
            "get_posture_for_action",
        ]

        for export in expected:
            assert export in __all__, f"{export} missing from __all__"

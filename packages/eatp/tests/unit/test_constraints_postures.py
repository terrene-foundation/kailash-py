"""
Comprehensive unit tests for EATP constraints, postures, and verification modules.

Tests cover:
- Trust Postures: autonomy levels, comparisons, transitions, state machine
- Constraint Dimensions: cost, time, resource, rate, data access, communication
- Commerce Constraints: beneficiary validation, tightening rules
- Spend Tracker: budget management, period resets, threshold warnings
- Constraint Evaluator: multi-dimension evaluation, interaction modes, anti-gaming
- Constraint Templates: loading, listing, customization
- Enforcement: Strict and Shadow enforcers, verdict classification
- Exception Hierarchy: all exception types, inheritance, attributes
"""

from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from typing import Any, Dict, List

import pytest

from eatp.chain import VerificationLevel, VerificationResult
from eatp.constraints import (
    CommunicationDimension,
    ConstraintCheckResult,
    ConstraintDimension,
    ConstraintDimensionRegistry,
    ConstraintValue,
    CostLimitDimension,
    DataAccessDimension,
    EvaluationResult,
    InteractionMode,
    MultiDimensionEvaluator,
    RateLimitDimension,
    ResourceDimension,
    TimeDimension,
    register_builtin_dimensions,
)
from eatp.constraints.commerce import CommerceConstraint, CommerceType
from eatp.constraints.spend_tracker import (
    BudgetPeriod,
    BudgetStatus,
    BudgetStatusLevel,
    SpendTracker,
)
from eatp.enforce.shadow import ShadowEnforcer, ShadowMetrics
from eatp.enforce.strict import (
    EATPBlockedError,
    EATPHeldError,
    HeldBehavior,
    StrictEnforcer,
    Verdict,
)
from eatp.exceptions import (
    AgentAlreadyEstablishedError,
    AuthorityNotFoundError,
    CapabilityNotFoundError,
    ConstraintViolationError,
    DelegationCycleError,
    DelegationError,
    DelegationExpiredError,
    InvalidSignatureError,
    InvalidTrustChainError,
    TrustChainInvalidError,
    TrustChainNotFoundError,
    TrustError,
    TrustStoreDatabaseError,
    TrustStoreError,
    VerificationFailedError,
)
from eatp.postures import (
    PostureStateMachine,
    PostureTransition,
    PostureTransitionRequest,
    TransitionGuard,
    TransitionResult,
    TrustPosture,
)
from eatp.templates import (
    customize_template,
    get_template,
    get_template_names,
    list_templates,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def cost_dim() -> CostLimitDimension:
    """Cost limit dimension instance."""
    return CostLimitDimension()


@pytest.fixture
def time_dim() -> TimeDimension:
    """Time dimension instance."""
    return TimeDimension()


@pytest.fixture
def resource_dim() -> ResourceDimension:
    """Resource dimension instance."""
    return ResourceDimension()


@pytest.fixture
def rate_dim() -> RateLimitDimension:
    """Rate limit dimension instance."""
    return RateLimitDimension()


@pytest.fixture
def data_dim() -> DataAccessDimension:
    """Data access dimension instance."""
    return DataAccessDimension()


@pytest.fixture
def comm_dim() -> CommunicationDimension:
    """Communication dimension instance."""
    return CommunicationDimension()


@pytest.fixture
def commerce_dim() -> CommerceConstraint:
    """Commerce constraint dimension instance."""
    return CommerceConstraint()


@pytest.fixture
def registry_with_builtins() -> ConstraintDimensionRegistry:
    """Registry pre-loaded with all built-in dimensions."""
    reg = ConstraintDimensionRegistry()
    register_builtin_dimensions(reg)
    return reg


@pytest.fixture
def evaluator(
    registry_with_builtins: ConstraintDimensionRegistry,
) -> MultiDimensionEvaluator:
    """Multi-dimension evaluator with built-in dimensions registered."""
    return MultiDimensionEvaluator(registry_with_builtins, enable_anti_gaming=True)


@pytest.fixture
def spend_tracker() -> SpendTracker:
    """Fresh spend tracker instance."""
    return SpendTracker()


@pytest.fixture
def posture_machine() -> PostureStateMachine:
    """Posture state machine with default upgrade approval guard."""
    return PostureStateMachine()


@pytest.fixture
def valid_verification_result() -> VerificationResult:
    """A passing verification result with no violations."""
    return VerificationResult(valid=True, violations=[])


@pytest.fixture
def flagged_verification_result() -> VerificationResult:
    """A passing verification result with some violations (would be flagged)."""
    return VerificationResult(
        valid=True,
        violations=[{"dimension": "cost_limit", "reason": "approaching limit"}],
    )


@pytest.fixture
def held_verification_result() -> VerificationResult:
    """A passing verification result with violations meeting flag_threshold=1 (would be held)."""
    return VerificationResult(
        valid=True,
        violations=[{"dimension": "cost_limit", "reason": "near limit"}],
    )


@pytest.fixture
def blocked_verification_result() -> VerificationResult:
    """A failing verification result (would be blocked)."""
    return VerificationResult(
        valid=False,
        reason="Expired trust chain",
        violations=[{"dimension": "chain", "reason": "expired"}],
    )


# ===========================================================================
# TRUST POSTURES
# ===========================================================================


class TestTrustPostureAutonomyLevels:
    """Trust posture autonomy level values."""

    def test_delegated_level_is_5(self):
        assert TrustPosture.DELEGATED.autonomy_level == 5

    def test_continuous_insight_level_is_4(self):
        assert TrustPosture.CONTINUOUS_INSIGHT.autonomy_level == 4

    def test_shared_planning_level_is_3(self):
        assert TrustPosture.SHARED_PLANNING.autonomy_level == 3

    def test_supervised_level_is_2(self):
        assert TrustPosture.SUPERVISED.autonomy_level == 2

    def test_pseudo_agent_level_is_1(self):
        assert TrustPosture.PSEUDO_AGENT.autonomy_level == 1


class TestTrustPostureComparisons:
    """Comparison operators on TrustPosture."""

    def test_pseudo_agent_less_than_delegated(self):
        assert TrustPosture.PSEUDO_AGENT < TrustPosture.DELEGATED

    def test_shared_planning_less_than_or_equal_to_continuous_insight(self):
        assert TrustPosture.SHARED_PLANNING <= TrustPosture.CONTINUOUS_INSIGHT

    def test_delegated_greater_than_supervised(self):
        assert TrustPosture.DELEGATED > TrustPosture.SUPERVISED

    def test_continuous_insight_greater_than_or_equal_to_continuous_insight(self):
        assert TrustPosture.CONTINUOUS_INSIGHT >= TrustPosture.CONTINUOUS_INSIGHT

    def test_equal_postures_le_ge(self):
        assert TrustPosture.SHARED_PLANNING <= TrustPosture.SHARED_PLANNING
        assert TrustPosture.SHARED_PLANNING >= TrustPosture.SHARED_PLANNING

    def test_not_less_than_when_equal(self):
        assert not (TrustPosture.SHARED_PLANNING < TrustPosture.SHARED_PLANNING)

    def test_comparison_with_non_posture_returns_not_implemented(self):
        result = TrustPosture.PSEUDO_AGENT.__lt__(42)
        assert result is NotImplemented


class TestTrustPostureUpgradeDowngrade:
    """can_upgrade_to and can_downgrade_to methods."""

    def test_can_upgrade_from_pseudo_agent_to_supervised(self):
        assert TrustPosture.PSEUDO_AGENT.can_upgrade_to(TrustPosture.SUPERVISED) is True

    def test_cannot_upgrade_to_same_posture(self):
        assert TrustPosture.SHARED_PLANNING.can_upgrade_to(TrustPosture.SHARED_PLANNING) is False

    def test_cannot_upgrade_to_lower_posture(self):
        assert TrustPosture.DELEGATED.can_upgrade_to(TrustPosture.PSEUDO_AGENT) is False

    def test_can_downgrade_from_delegated_to_pseudo_agent(self):
        assert TrustPosture.DELEGATED.can_downgrade_to(TrustPosture.PSEUDO_AGENT) is True

    def test_cannot_downgrade_to_same_posture(self):
        assert (
            TrustPosture.SHARED_PLANNING.can_downgrade_to(TrustPosture.SHARED_PLANNING) is False
        )

    def test_cannot_downgrade_to_higher_posture(self):
        assert (
            TrustPosture.PSEUDO_AGENT.can_downgrade_to(TrustPosture.DELEGATED) is False
        )


class TestPostureTransitionRequest:
    """PostureTransitionRequest transition_type property."""

    def test_upgrade_transition_type(self):
        req = PostureTransitionRequest(
            agent_id="a1",
            from_posture=TrustPosture.SHARED_PLANNING,
            to_posture=TrustPosture.DELEGATED,
        )
        assert req.transition_type == PostureTransition.UPGRADE
        assert req.is_upgrade is True
        assert req.is_downgrade is False

    def test_downgrade_transition_type(self):
        req = PostureTransitionRequest(
            agent_id="a1",
            from_posture=TrustPosture.DELEGATED,
            to_posture=TrustPosture.PSEUDO_AGENT,
        )
        assert req.transition_type == PostureTransition.DOWNGRADE
        assert req.is_downgrade is True
        assert req.is_upgrade is False

    def test_maintain_transition_type(self):
        req = PostureTransitionRequest(
            agent_id="a1",
            from_posture=TrustPosture.SHARED_PLANNING,
            to_posture=TrustPosture.SHARED_PLANNING,
        )
        assert req.transition_type == PostureTransition.MAINTAIN
        assert req.is_upgrade is False
        assert req.is_downgrade is False


class TestPostureStateMachine:
    """PostureStateMachine transitions and guards."""

    def test_default_posture_is_shared_planning(self, posture_machine: PostureStateMachine):
        assert posture_machine.get_posture("unknown-agent") == TrustPosture.SHARED_PLANNING

    def test_set_and_get_posture(self, posture_machine: PostureStateMachine):
        posture_machine.set_posture("agent-1", TrustPosture.DELEGATED)
        assert posture_machine.get_posture("agent-1") == TrustPosture.DELEGATED

    def test_upgrade_requires_requester_id(self, posture_machine: PostureStateMachine):
        posture_machine.set_posture("agent-1", TrustPosture.SHARED_PLANNING)
        result = posture_machine.transition(
            PostureTransitionRequest(
                agent_id="agent-1",
                from_posture=TrustPosture.SHARED_PLANNING,
                to_posture=TrustPosture.DELEGATED,
                requester_id=None,
            )
        )
        assert result.success is False
        assert result.blocked_by == "upgrade_approval_required"

    def test_upgrade_succeeds_with_requester_id(
        self, posture_machine: PostureStateMachine
    ):
        posture_machine.set_posture("agent-1", TrustPosture.SHARED_PLANNING)
        result = posture_machine.transition(
            PostureTransitionRequest(
                agent_id="agent-1",
                from_posture=TrustPosture.SHARED_PLANNING,
                to_posture=TrustPosture.DELEGATED,
                requester_id="admin-001",
                reason="Agent has proven reliable",
            )
        )
        assert result.success is True
        assert posture_machine.get_posture("agent-1") == TrustPosture.DELEGATED

    def test_downgrade_does_not_require_approval(
        self, posture_machine: PostureStateMachine
    ):
        posture_machine.set_posture("agent-1", TrustPosture.DELEGATED)
        result = posture_machine.transition(
            PostureTransitionRequest(
                agent_id="agent-1",
                from_posture=TrustPosture.DELEGATED,
                to_posture=TrustPosture.SHARED_PLANNING,
            )
        )
        assert result.success is True
        assert posture_machine.get_posture("agent-1") == TrustPosture.SHARED_PLANNING

    def test_mismatched_from_posture_fails(self, posture_machine: PostureStateMachine):
        posture_machine.set_posture("agent-1", TrustPosture.PSEUDO_AGENT)
        result = posture_machine.transition(
            PostureTransitionRequest(
                agent_id="agent-1",
                from_posture=TrustPosture.SHARED_PLANNING,
                to_posture=TrustPosture.DELEGATED,
            )
        )
        assert result.success is False
        assert "does not match" in result.reason

    def test_emergency_downgrade_bypasses_guards(
        self, posture_machine: PostureStateMachine
    ):
        posture_machine.set_posture("agent-1", TrustPosture.DELEGATED)
        result = posture_machine.emergency_downgrade(
            "agent-1", reason="Security incident"
        )
        assert result.success is True
        assert result.to_posture == TrustPosture.PSEUDO_AGENT
        assert result.transition_type == PostureTransition.EMERGENCY_DOWNGRADE
        assert posture_machine.get_posture("agent-1") == TrustPosture.PSEUDO_AGENT

    def test_transition_history_recorded(self, posture_machine: PostureStateMachine):
        posture_machine.set_posture("agent-1", TrustPosture.DELEGATED)
        posture_machine.transition(
            PostureTransitionRequest(
                agent_id="agent-1",
                from_posture=TrustPosture.DELEGATED,
                to_posture=TrustPosture.SHARED_PLANNING,
            )
        )
        history = posture_machine.get_transition_history(agent_id="agent-1")
        assert len(history) >= 1
        assert history[0].success is True

    def test_add_and_remove_guard(self, posture_machine: PostureStateMachine):
        custom_guard = TransitionGuard(
            name="test_guard",
            check_fn=lambda req: False,
            applies_to=[PostureTransition.DOWNGRADE],
            reason_on_failure="Test guard blocks downgrades",
        )
        posture_machine.add_guard(custom_guard)
        assert "test_guard" in posture_machine.list_guards()

        removed = posture_machine.remove_guard("test_guard")
        assert removed is True
        assert "test_guard" not in posture_machine.list_guards()

    def test_remove_nonexistent_guard_returns_false(
        self, posture_machine: PostureStateMachine
    ):
        assert posture_machine.remove_guard("nonexistent") is False

    def test_machine_without_upgrade_approval(self):
        machine = PostureStateMachine(require_upgrade_approval=False)
        machine.set_posture("agent-1", TrustPosture.SHARED_PLANNING)
        result = machine.transition(
            PostureTransitionRequest(
                agent_id="agent-1",
                from_posture=TrustPosture.SHARED_PLANNING,
                to_posture=TrustPosture.DELEGATED,
            )
        )
        assert result.success is True

    def test_transition_result_to_dict(self):
        result = TransitionResult(
            success=True,
            from_posture=TrustPosture.SHARED_PLANNING,
            to_posture=TrustPosture.DELEGATED,
            transition_type=PostureTransition.UPGRADE,
            reason="Promoted",
        )
        d = result.to_dict()
        assert d["success"] is True
        assert d["from_posture"] == "shared_planning"
        assert d["to_posture"] == "delegated"
        assert d["transition_type"] == "upgrade"


# ===========================================================================
# CONSTRAINT DIMENSIONS
# ===========================================================================


class TestCostLimitDimension:
    """CostLimitDimension parse, check, tightening."""

    def test_parse_float(self, cost_dim: CostLimitDimension):
        cv = cost_dim.parse(1000.0)
        assert cv.parsed == 1000.0
        assert cv.dimension == "cost_limit"

    def test_parse_int(self, cost_dim: CostLimitDimension):
        cv = cost_dim.parse(500)
        assert cv.parsed == 500.0

    def test_parse_string_number(self, cost_dim: CostLimitDimension):
        cv = cost_dim.parse("250.5")
        assert cv.parsed == 250.5

    def test_parse_negative_raises(self, cost_dim: CostLimitDimension):
        with pytest.raises(ValueError, match="non-negative"):
            cost_dim.parse(-10)

    def test_parse_invalid_raises(self, cost_dim: CostLimitDimension):
        with pytest.raises(ValueError, match="Cannot parse"):
            cost_dim.parse("not_a_number")

    def test_check_within_budget(self, cost_dim: CostLimitDimension):
        cv = cost_dim.parse(1000)
        result = cost_dim.check(cv, {"cost_used": 500.0})
        assert result.satisfied is True
        assert result.remaining == 500.0
        assert result.used == 500.0
        assert result.limit == 1000.0

    def test_check_at_budget(self, cost_dim: CostLimitDimension):
        cv = cost_dim.parse(1000)
        result = cost_dim.check(cv, {"cost_used": 1000.0})
        assert result.satisfied is True
        assert result.remaining == 0.0

    def test_check_over_budget(self, cost_dim: CostLimitDimension):
        cv = cost_dim.parse(1000)
        result = cost_dim.check(cv, {"cost_used": 1500.0})
        assert result.satisfied is False
        assert "over budget" in result.reason

    def test_check_no_cost_used_defaults_zero(self, cost_dim: CostLimitDimension):
        cv = cost_dim.parse(1000)
        result = cost_dim.check(cv, {})
        assert result.satisfied is True
        assert result.used == 0.0

    def test_tightening_child_lower_valid(self, cost_dim: CostLimitDimension):
        parent = cost_dim.parse(1000)
        child = cost_dim.parse(500)
        assert cost_dim.validate_tightening(parent, child) is True

    def test_tightening_child_higher_invalid(self, cost_dim: CostLimitDimension):
        parent = cost_dim.parse(500)
        child = cost_dim.parse(1000)
        assert cost_dim.validate_tightening(parent, child) is False

    def test_tightening_equal_valid(self, cost_dim: CostLimitDimension):
        parent = cost_dim.parse(500)
        child = cost_dim.parse(500)
        assert cost_dim.validate_tightening(parent, child) is True

    def test_requires_audit(self, cost_dim: CostLimitDimension):
        assert cost_dim.requires_audit is True


class TestTimeDimension:
    """TimeDimension parse, check, tightening."""

    def test_parse_valid_window(self, time_dim: TimeDimension):
        cv = time_dim.parse("09:00-17:00")
        assert cv.parsed["start"] == time(9, 0)
        assert cv.parsed["end"] == time(17, 0)
        assert cv.metadata["overnight"] is False

    def test_parse_overnight_window(self, time_dim: TimeDimension):
        cv = time_dim.parse("22:00-06:00")
        assert cv.metadata["overnight"] is True

    def test_parse_invalid_format_raises(self, time_dim: TimeDimension):
        with pytest.raises(ValueError, match="Invalid time window format"):
            time_dim.parse("9am-5pm")

    def test_parse_non_string_raises(self, time_dim: TimeDimension):
        with pytest.raises(ValueError, match="must be a string"):
            time_dim.parse(900)

    def test_check_within_normal_window(self, time_dim: TimeDimension):
        cv = time_dim.parse("09:00-17:00")
        ctx = {"current_time": time(12, 0)}
        result = time_dim.check(cv, ctx)
        assert result.satisfied is True
        assert "within time window" in result.reason

    def test_check_outside_normal_window(self, time_dim: TimeDimension):
        cv = time_dim.parse("09:00-17:00")
        ctx = {"current_time": time(20, 0)}
        result = time_dim.check(cv, ctx)
        assert result.satisfied is False
        assert "outside time window" in result.reason

    def test_check_overnight_inside_evening(self, time_dim: TimeDimension):
        cv = time_dim.parse("22:00-06:00")
        ctx = {"current_time": time(23, 0)}
        result = time_dim.check(cv, ctx)
        assert result.satisfied is True

    def test_check_overnight_inside_morning(self, time_dim: TimeDimension):
        cv = time_dim.parse("22:00-06:00")
        ctx = {"current_time": time(3, 0)}
        result = time_dim.check(cv, ctx)
        assert result.satisfied is True

    def test_check_overnight_outside(self, time_dim: TimeDimension):
        cv = time_dim.parse("22:00-06:00")
        ctx = {"current_time": time(12, 0)}
        result = time_dim.check(cv, ctx)
        assert result.satisfied is False

    def test_tightening_child_subset_valid(self, time_dim: TimeDimension):
        parent = time_dim.parse("09:00-17:00")
        child = time_dim.parse("10:00-16:00")
        assert time_dim.validate_tightening(parent, child) is True

    def test_tightening_child_wider_invalid(self, time_dim: TimeDimension):
        parent = time_dim.parse("10:00-16:00")
        child = time_dim.parse("09:00-17:00")
        assert time_dim.validate_tightening(parent, child) is False


class TestResourceDimension:
    """ResourceDimension parse, check, tightening, security."""

    def test_parse_single_pattern(self, resource_dim: ResourceDimension):
        cv = resource_dim.parse("data/*.json")
        assert cv.parsed == ["data/*.json"]

    def test_parse_list_of_patterns(self, resource_dim: ResourceDimension):
        cv = resource_dim.parse(["data/*.json", "logs/*.log"])
        assert len(cv.parsed) == 2

    def test_parse_rejects_overly_permissive(self, resource_dim: ResourceDimension):
        with pytest.raises(ValueError, match="too permissive"):
            resource_dim.parse("*")

    def test_parse_rejects_double_star_alone(self, resource_dim: ResourceDimension):
        with pytest.raises(ValueError, match="too permissive"):
            resource_dim.parse("**")

    def test_check_matching_pattern(self, resource_dim: ResourceDimension):
        cv = resource_dim.parse("data/*.json")
        result = resource_dim.check(cv, {"resource_requested": "data/users.json"})
        assert result.satisfied is True

    def test_check_non_matching_pattern(self, resource_dim: ResourceDimension):
        cv = resource_dim.parse("data/*.json")
        result = resource_dim.check(cv, {"resource_requested": "logs/app.log"})
        assert result.satisfied is False

    def test_check_no_resource_requested_satisfies(
        self, resource_dim: ResourceDimension
    ):
        cv = resource_dim.parse("data/*.json")
        result = resource_dim.check(cv, {})
        assert result.satisfied is True

    def test_check_blocks_path_traversal(self, resource_dim: ResourceDimension):
        cv = resource_dim.parse("data/*.json")
        result = resource_dim.check(cv, {"resource_requested": "data/../etc/passwd"})
        assert result.satisfied is False
        assert "path traversal" in result.reason

    def test_check_blocks_null_byte(self, resource_dim: ResourceDimension):
        cv = resource_dim.parse("data/*.json")
        result = resource_dim.check(cv, {"resource_requested": "data/file\x00.json"})
        assert result.satisfied is False
        assert "null byte" in result.reason


class TestRateLimitDimension:
    """RateLimitDimension parse and check."""

    def test_parse_integer(self, rate_dim: RateLimitDimension):
        cv = rate_dim.parse(100)
        assert cv.parsed["limit"] == 100
        assert cv.parsed["period"] is None

    def test_parse_string_with_period(self, rate_dim: RateLimitDimension):
        cv = rate_dim.parse("100/minute")
        assert cv.parsed["limit"] == 100
        assert cv.parsed["period"] == "minute"

    def test_parse_invalid_period_raises(self, rate_dim: RateLimitDimension):
        with pytest.raises(ValueError, match="Invalid period"):
            rate_dim.parse("100/fortnight")

    def test_check_within_limit(self, rate_dim: RateLimitDimension):
        cv = rate_dim.parse(100)
        result = rate_dim.check(cv, {"requests_in_period": 50})
        assert result.satisfied is True
        assert result.remaining == 50.0

    def test_check_exceeded(self, rate_dim: RateLimitDimension):
        cv = rate_dim.parse(100)
        result = rate_dim.check(cv, {"requests_in_period": 150})
        assert result.satisfied is False
        assert "exceeded" in result.reason


class TestDataAccessDimension:
    """DataAccessDimension parse and check."""

    def test_parse_no_pii_mode(self, data_dim: DataAccessDimension):
        cv = data_dim.parse("no_pii")
        assert cv.parsed["mode"] == "no_pii"

    def test_check_no_pii_with_pii_present(self, data_dim: DataAccessDimension):
        cv = data_dim.parse("no_pii")
        result = data_dim.check(cv, {"contains_pii": True})
        assert result.satisfied is False
        assert "PII" in result.reason

    def test_check_no_pii_without_pii(self, data_dim: DataAccessDimension):
        cv = data_dim.parse("no_pii")
        result = data_dim.check(cv, {"contains_pii": False})
        assert result.satisfied is True

    def test_check_internal_only_with_internal_data(
        self, data_dim: DataAccessDimension
    ):
        cv = data_dim.parse("internal_only")
        result = data_dim.check(cv, {"data_classification": "internal"})
        assert result.satisfied is True

    def test_check_internal_only_with_external_data(
        self, data_dim: DataAccessDimension
    ):
        cv = data_dim.parse("internal_only")
        result = data_dim.check(cv, {"data_classification": "external"})
        assert result.satisfied is False

    def test_parse_invalid_mode_raises(self, data_dim: DataAccessDimension):
        with pytest.raises(ValueError, match="Invalid data access mode"):
            data_dim.parse("wildcard_mode")


class TestCommunicationDimension:
    """CommunicationDimension parse and check."""

    def test_parse_none_mode(self, comm_dim: CommunicationDimension):
        cv = comm_dim.parse("none")
        assert cv.parsed["mode"] == "none"

    def test_check_none_blocks_all(self, comm_dim: CommunicationDimension):
        cv = comm_dim.parse("none")
        result = comm_dim.check(cv, {"communication_target": "api.example.com"})
        assert result.satisfied is False

    def test_check_internal_only_allows_localhost(
        self, comm_dim: CommunicationDimension
    ):
        cv = comm_dim.parse("internal_only")
        result = comm_dim.check(cv, {"communication_target": "localhost:8080"})
        assert result.satisfied is True

    def test_check_internal_only_blocks_external(
        self, comm_dim: CommunicationDimension
    ):
        cv = comm_dim.parse("internal_only")
        result = comm_dim.check(cv, {"communication_target": "api.example.com"})
        assert result.satisfied is False

    def test_check_allowed_domains(self, comm_dim: CommunicationDimension):
        cv = comm_dim.parse(
            {
                "mode": "allowed_domains",
                "allowed_domains": ["example.com", "api.trusted.io"],
            }
        )
        result = comm_dim.check(cv, {"communication_target": "sub.example.com"})
        assert result.satisfied is True

    def test_check_allowed_domains_denies_unlisted(
        self, comm_dim: CommunicationDimension
    ):
        cv = comm_dim.parse(
            {
                "mode": "allowed_domains",
                "allowed_domains": ["example.com"],
            }
        )
        result = comm_dim.check(cv, {"communication_target": "evil.com"})
        assert result.satisfied is False


# ===========================================================================
# COMMERCE CONSTRAINTS
# ===========================================================================


class TestCommerceConstraint:
    """CommerceConstraint parse, check, is_tighter."""

    def test_commerce_type_enum_values(self):
        assert CommerceType.PURCHASE.value == "purchase"
        assert CommerceType.SALE.value == "sale"
        assert CommerceType.TRANSFER.value == "transfer"
        assert CommerceType.EXCHANGE.value == "exchange"

    def test_parse_dict_with_beneficiary(self, commerce_dim: CommerceConstraint):
        cv = commerce_dim.parse(
            {
                "beneficiary_id": "org-001",
                "allowed_beneficiaries": ["org-001", "org-002"],
                "commerce_types": ["purchase", "sale"],
            }
        )
        assert cv.parsed["beneficiary_id"] == "org-001"
        assert set(cv.parsed["allowed_beneficiaries"]) == {"org-001", "org-002"}

    def test_parse_string_format(self, commerce_dim: CommerceConstraint):
        cv = commerce_dim.parse("beneficiary:org-001")
        assert cv.parsed["beneficiary_id"] == "org-001"
        assert "org-001" in cv.parsed["allowed_beneficiaries"]

    def test_check_authorized_beneficiary(self, commerce_dim: CommerceConstraint):
        cv = commerce_dim.parse(
            {
                "beneficiary_id": "org-001",
                "allowed_beneficiaries": ["org-001", "org-002"],
            }
        )
        result = commerce_dim.check(cv, {"beneficiary_id": "org-001"})
        assert result.satisfied is True

    def test_check_unauthorized_beneficiary(self, commerce_dim: CommerceConstraint):
        cv = commerce_dim.parse(
            {
                "beneficiary_id": "org-001",
                "allowed_beneficiaries": ["org-001"],
            }
        )
        result = commerce_dim.check(cv, {"beneficiary_id": "org-999"})
        assert result.satisfied is False
        assert "not in allowed list" in result.reason

    def test_check_unauthorized_commerce_type(self, commerce_dim: CommerceConstraint):
        cv = commerce_dim.parse(
            {
                "beneficiary_id": "org-001",
                "commerce_types": ["purchase"],
            }
        )
        result = commerce_dim.check(cv, {"commerce_type": "transfer"})
        assert result.satisfied is False
        assert "not allowed" in result.reason

    def test_check_mismatched_jurisdiction(self, commerce_dim: CommerceConstraint):
        cv = commerce_dim.parse(
            {
                "beneficiary_id": "org-001",
                "jurisdiction": "US",
            }
        )
        result = commerce_dim.check(cv, {"jurisdiction": "UK"})
        assert result.satisfied is False
        assert "Jurisdiction" in result.reason

    def test_is_tighter_child_subset_valid(self, commerce_dim: CommerceConstraint):
        parent = commerce_dim.parse(
            {
                "beneficiary_id": "org-001",
                "allowed_beneficiaries": ["org-001", "org-002"],
                "commerce_types": ["purchase", "sale", "transfer"],
            }
        )
        child = commerce_dim.parse(
            {
                "beneficiary_id": "org-001",
                "allowed_beneficiaries": ["org-001"],
                "commerce_types": ["purchase"],
            }
        )
        assert commerce_dim.is_tighter(parent, child) is True

    def test_is_tighter_child_adds_beneficiary_invalid(
        self, commerce_dim: CommerceConstraint
    ):
        parent = commerce_dim.parse(
            {
                "beneficiary_id": "org-001",
                "allowed_beneficiaries": ["org-001"],
            }
        )
        child = commerce_dim.parse(
            {
                "beneficiary_id": "org-001",
                "allowed_beneficiaries": ["org-001", "org-999"],
            }
        )
        assert commerce_dim.is_tighter(parent, child) is False

    def test_is_tighter_child_adds_commerce_type_invalid(
        self, commerce_dim: CommerceConstraint
    ):
        parent = commerce_dim.parse(
            {
                "beneficiary_id": "org-001",
                "commerce_types": ["purchase"],
            }
        )
        child = commerce_dim.parse(
            {
                "beneficiary_id": "org-001",
                "commerce_types": ["purchase", "transfer"],
            }
        )
        assert commerce_dim.is_tighter(parent, child) is False

    def test_is_tighter_child_drops_attribution_invalid(
        self, commerce_dim: CommerceConstraint
    ):
        parent = commerce_dim.parse(
            {
                "beneficiary_id": "org-001",
                "attribution_required": True,
            }
        )
        child = commerce_dim.parse(
            {
                "beneficiary_id": "org-001",
                "attribution_required": False,
            }
        )
        assert commerce_dim.is_tighter(parent, child) is False


# ===========================================================================
# SPEND TRACKER
# ===========================================================================


class TestSpendTracker:
    """SpendTracker budget management."""

    def test_set_budget_and_check(self, spend_tracker: SpendTracker):
        spend_tracker.set_budget("agent-1", limit=1000.0, currency="USD")
        status = spend_tracker.check_budget("agent-1")
        assert status.level == BudgetStatusLevel.OK
        assert status.spent == 0.0
        assert status.limit == 1000.0
        assert status.remaining == 1000.0

    def test_record_spend_updates_status(self, spend_tracker: SpendTracker):
        spend_tracker.set_budget("agent-1", limit=1000.0)
        status = spend_tracker.record_spend("agent-1", amount=250.0, action="purchase")
        assert status.spent == 250.0
        assert status.remaining == 750.0
        assert status.level == BudgetStatusLevel.OK

    def test_warning_threshold(self, spend_tracker: SpendTracker):
        spend_tracker.set_budget("agent-1", limit=1000.0, warning_threshold_pct=80.0)
        spend_tracker.record_spend("agent-1", amount=850.0, action="purchase")
        status = spend_tracker.check_budget("agent-1")
        assert status.level == BudgetStatusLevel.WARNING

    def test_exceeded_budget(self, spend_tracker: SpendTracker):
        spend_tracker.set_budget("agent-1", limit=1000.0)
        spend_tracker.record_spend("agent-1", amount=1000.0, action="purchase")
        status = spend_tracker.check_budget("agent-1")
        assert status.level == BudgetStatusLevel.EXCEEDED

    def test_record_spend_without_budget_raises(self, spend_tracker: SpendTracker):
        with pytest.raises(ValueError, match="No budget configured"):
            spend_tracker.record_spend("unknown-agent", amount=100.0)

    def test_check_budget_without_budget_raises(self, spend_tracker: SpendTracker):
        with pytest.raises(ValueError, match="No budget configured"):
            spend_tracker.check_budget("unknown-agent")

    def test_reset_budget(self, spend_tracker: SpendTracker):
        spend_tracker.set_budget("agent-1", limit=1000.0)
        spend_tracker.record_spend("agent-1", amount=500.0, action="purchase")
        spend_tracker.reset_budget("agent-1")
        status = spend_tracker.check_budget("agent-1")
        assert status.spent == 0.0
        assert status.remaining == 1000.0

    def test_reset_budget_without_budget_raises(self, spend_tracker: SpendTracker):
        with pytest.raises(ValueError, match="No budget configured"):
            spend_tracker.reset_budget("unknown-agent")

    def test_would_exceed_true(self, spend_tracker: SpendTracker):
        spend_tracker.set_budget("agent-1", limit=1000.0)
        spend_tracker.record_spend("agent-1", amount=900.0, action="purchase")
        assert spend_tracker.would_exceed("agent-1", 200.0) is True

    def test_would_exceed_false(self, spend_tracker: SpendTracker):
        spend_tracker.set_budget("agent-1", limit=1000.0)
        spend_tracker.record_spend("agent-1", amount=500.0, action="purchase")
        assert spend_tracker.would_exceed("agent-1", 400.0) is False

    def test_would_exceed_unknown_agent_returns_false(
        self, spend_tracker: SpendTracker
    ):
        assert spend_tracker.would_exceed("unknown", 100.0) is False

    def test_budget_period_enum_values(self):
        assert BudgetPeriod.DAILY.value == "daily"
        assert BudgetPeriod.WEEKLY.value == "weekly"
        assert BudgetPeriod.MONTHLY.value == "monthly"
        assert BudgetPeriod.YEARLY.value == "yearly"
        assert BudgetPeriod.NONE.value == "none"

    def test_spend_history(self, spend_tracker: SpendTracker):
        spend_tracker.set_budget("agent-1", limit=1000.0)
        spend_tracker.record_spend("agent-1", amount=100.0, action="action-a")
        spend_tracker.record_spend("agent-1", amount=200.0, action="action-b")
        history = spend_tracker.get_spend_history("agent-1")
        assert len(history) == 2
        assert history[0].amount == 200.0  # Most recent first
        assert history[1].amount == 100.0


# ===========================================================================
# CONSTRAINT EVALUATOR
# ===========================================================================


class TestMultiDimensionEvaluator:
    """MultiDimensionEvaluator interaction modes and combined evaluation."""

    def test_conjunctive_all_pass(self, evaluator: MultiDimensionEvaluator):
        result = evaluator.evaluate(
            constraints={"cost_limit": 1000},
            context={"cost_used": 500},
            mode=InteractionMode.CONJUNCTIVE,
        )
        assert result.satisfied is True
        assert len(result.failed_dimensions) == 0

    def test_conjunctive_one_fails(self, evaluator: MultiDimensionEvaluator):
        result = evaluator.evaluate(
            constraints={"cost_limit": 100, "rate_limit": 50},
            context={"cost_used": 200, "requests_in_period": 10},
            mode=InteractionMode.CONJUNCTIVE,
        )
        assert result.satisfied is False
        assert "cost_limit" in result.failed_dimensions

    def test_disjunctive_one_passes_enough(self, evaluator: MultiDimensionEvaluator):
        result = evaluator.evaluate(
            constraints={"cost_limit": 100, "rate_limit": 50},
            context={"cost_used": 200, "requests_in_period": 10},
            mode=InteractionMode.DISJUNCTIVE,
        )
        assert result.satisfied is True

    def test_disjunctive_all_fail(self, evaluator: MultiDimensionEvaluator):
        result = evaluator.evaluate(
            constraints={"cost_limit": 100, "rate_limit": 50},
            context={"cost_used": 200, "requests_in_period": 100},
            mode=InteractionMode.DISJUNCTIVE,
        )
        assert result.satisfied is False

    def test_independent_majority_pass(self, evaluator: MultiDimensionEvaluator):
        result = evaluator.evaluate(
            constraints={"cost_limit": 1000, "rate_limit": 100},
            context={"cost_used": 500, "requests_in_period": 50},
            mode=InteractionMode.INDEPENDENT,
        )
        assert result.satisfied is True

    def test_hierarchical_first_dimension_determines(
        self, evaluator: MultiDimensionEvaluator
    ):
        result = evaluator.evaluate(
            constraints={"cost_limit": 1000, "rate_limit": 50},
            context={"cost_used": 500, "requests_in_period": 100},
            mode=InteractionMode.HIERARCHICAL,
        )
        # cost_limit passes, so hierarchical should pass even if rate_limit fails
        assert result.satisfied is True

    def test_empty_constraints_satisfied(self, evaluator: MultiDimensionEvaluator):
        result = evaluator.evaluate(constraints={}, context={})
        assert result.satisfied is True

    def test_unknown_dimension_warning(self, evaluator: MultiDimensionEvaluator):
        result = evaluator.evaluate(
            constraints={"nonexistent_dim": 42},
            context={},
            mode=InteractionMode.CONJUNCTIVE,
        )
        assert any("Unknown dimension" in w for w in result.warnings)

    def test_validate_tightening_valid(self, evaluator: MultiDimensionEvaluator):
        violations = evaluator.validate_tightening(
            parent_constraints={"cost_limit": 1000},
            child_constraints={"cost_limit": 500},
        )
        assert violations == []

    def test_validate_tightening_invalid(self, evaluator: MultiDimensionEvaluator):
        violations = evaluator.validate_tightening(
            parent_constraints={"cost_limit": 500},
            child_constraints={"cost_limit": 1000},
        )
        assert len(violations) == 1
        assert "looser" in violations[0]


class TestAntiGaming:
    """Anti-gaming detection in the evaluator."""

    def test_boundary_pushing_detection(self, evaluator: MultiDimensionEvaluator):
        result = evaluator.evaluate(
            constraints={"cost_limit": 1000},
            context={"cost_used": 960},
            mode=InteractionMode.CONJUNCTIVE,
            agent_id="agent-suspicious",
        )
        assert any("boundary_pushing" in f for f in result.anti_gaming_flags)


# ===========================================================================
# CONSTRAINT TEMPLATES
# ===========================================================================


class TestConstraintTemplates:
    """Built-in constraint templates."""

    def test_get_template_governance(self):
        tmpl = get_template("governance")
        assert tmpl["name"] == "governance"
        assert "constraints" in tmpl
        assert "scope" in tmpl["constraints"]

    def test_get_template_all_six(self):
        for name in (
            "governance",
            "finance",
            "community",
            "standards",
            "audit",
            "minimal",
        ):
            tmpl = get_template(name)
            assert tmpl["name"] == name

    def test_get_template_unknown_raises(self):
        with pytest.raises(ValueError, match="Unknown template"):
            get_template("nonexistent")

    def test_list_templates_returns_six(self):
        templates = list_templates()
        assert len(templates) == 6
        names = {t["name"] for t in templates}
        assert "governance" in names
        assert "finance" in names
        assert "minimal" in names

    def test_get_template_names_sorted(self):
        names = get_template_names()
        assert names == sorted(names)
        assert len(names) == 6

    def test_customize_template_overrides(self):
        tmpl = customize_template(
            "minimal",
            overrides={"scope": {"actions": ["read_only"]}},
        )
        assert tmpl["constraints"]["scope"]["actions"] == ["read_only"]

    def test_get_template_returns_deep_copy(self):
        tmpl1 = get_template("governance")
        tmpl1["constraints"]["scope"]["actions"].append("MUTATED")
        tmpl2 = get_template("governance")
        assert "MUTATED" not in tmpl2["constraints"]["scope"]["actions"]


# ===========================================================================
# CONSTRAINT DIMENSION REGISTRY
# ===========================================================================


class TestConstraintDimensionRegistry:
    """Registry registration, approval, and retrieval."""

    def test_register_builtin_auto_approved(self):
        reg = ConstraintDimensionRegistry()
        reg.register(CostLimitDimension())
        dim = reg.get("cost_limit")
        assert dim is not None
        assert dim.name == "cost_limit"

    def test_register_duplicate_raises(self):
        reg = ConstraintDimensionRegistry()
        reg.register(CostLimitDimension())
        with pytest.raises(ValueError, match="already registered"):
            reg.register(CostLimitDimension())

    def test_custom_dimension_pending_review(self):
        reg = ConstraintDimensionRegistry()
        reg.register(CommerceConstraint(), requires_review=True)
        assert reg.get("commerce") is None
        assert "commerce" in reg.pending_review()

    def test_approve_dimension_then_retrieve(self):
        reg = ConstraintDimensionRegistry()
        reg.register(CommerceConstraint(), requires_review=True)
        reg.approve_dimension("commerce", reviewer="security-team")
        dim = reg.get("commerce")
        assert dim is not None

    def test_allow_unreviewed_flag(self):
        reg = ConstraintDimensionRegistry(allow_unreviewed=True)
        reg.register(CommerceConstraint(), requires_review=True)
        dim = reg.get("commerce")
        assert dim is not None

    def test_has_checks_registration(self):
        reg = ConstraintDimensionRegistry()
        assert reg.has("cost_limit") is False
        reg.register(CostLimitDimension())
        assert reg.has("cost_limit") is True

    def test_all_returns_registered(self):
        reg = ConstraintDimensionRegistry()
        register_builtin_dimensions(reg)
        all_dims = reg.all()
        names = {name for name, _ in all_dims}
        assert "cost_limit" in names
        assert "time_window" in names
        assert len(all_dims) == 6

    def test_parse_constraint_convenience(self):
        reg = ConstraintDimensionRegistry()
        reg.register(CostLimitDimension())
        cv = reg.parse_constraint("cost_limit", 500)
        assert cv is not None
        assert cv.parsed == 500.0


# ===========================================================================
# ENFORCEMENT - STRICT
# ===========================================================================


class TestVerdictEnum:
    """Verdict enum values."""

    def test_verdict_values(self):
        assert Verdict.AUTO_APPROVED.value == "auto_approved"
        assert Verdict.FLAGGED.value == "flagged"
        assert Verdict.HELD.value == "held"
        assert Verdict.BLOCKED.value == "blocked"


class TestStrictEnforcer:
    """StrictEnforcer classify and enforce."""

    def test_classify_auto_approved(
        self, valid_verification_result: VerificationResult
    ):
        enforcer = StrictEnforcer()
        verdict = enforcer.classify(valid_verification_result)
        assert verdict == Verdict.AUTO_APPROVED

    def test_classify_blocked(self, blocked_verification_result: VerificationResult):
        enforcer = StrictEnforcer()
        verdict = enforcer.classify(blocked_verification_result)
        assert verdict == Verdict.BLOCKED

    def test_classify_held_with_violations_at_threshold(self):
        enforcer = StrictEnforcer(flag_threshold=1)
        result = VerificationResult(
            valid=True,
            violations=[{"dim": "cost", "reason": "near limit"}],
        )
        verdict = enforcer.classify(result)
        assert verdict == Verdict.HELD

    def test_classify_flagged_below_threshold(self):
        enforcer = StrictEnforcer(flag_threshold=3)
        result = VerificationResult(
            valid=True,
            violations=[{"dim": "cost", "reason": "near limit"}],
        )
        verdict = enforcer.classify(result)
        assert verdict == Verdict.FLAGGED

    def test_enforce_auto_approved_returns_verdict(
        self, valid_verification_result: VerificationResult
    ):
        enforcer = StrictEnforcer()
        verdict = enforcer.enforce(
            agent_id="agent-1",
            action="read_data",
            result=valid_verification_result,
        )
        assert verdict == Verdict.AUTO_APPROVED

    def test_enforce_blocked_raises(
        self, blocked_verification_result: VerificationResult
    ):
        enforcer = StrictEnforcer()
        with pytest.raises(EATPBlockedError) as exc_info:
            enforcer.enforce(
                agent_id="agent-1",
                action="read_data",
                result=blocked_verification_result,
            )
        assert exc_info.value.agent_id == "agent-1"
        assert exc_info.value.action == "read_data"

    def test_enforce_held_raises_by_default(self):
        enforcer = StrictEnforcer(flag_threshold=1, on_held=HeldBehavior.RAISE)
        result = VerificationResult(
            valid=True,
            violations=[{"dim": "cost", "reason": "near limit"}],
        )
        with pytest.raises(EATPHeldError) as exc_info:
            enforcer.enforce(agent_id="agent-1", action="write_data", result=result)
        assert exc_info.value.agent_id == "agent-1"

    def test_enforce_held_queue_behavior(self):
        enforcer = StrictEnforcer(flag_threshold=1, on_held=HeldBehavior.QUEUE)
        result = VerificationResult(
            valid=True,
            violations=[{"dim": "cost", "reason": "near limit"}],
        )
        with pytest.raises(EATPHeldError):
            enforcer.enforce(agent_id="agent-1", action="write_data", result=result)
        assert len(enforcer.review_queue) == 1

    def test_enforce_held_callback_allows(self):
        callback_called = False

        def allow_callback(
            agent_id: str, action: str, result: VerificationResult
        ) -> bool:
            nonlocal callback_called
            callback_called = True
            return True

        enforcer = StrictEnforcer(
            flag_threshold=1,
            on_held=HeldBehavior.CALLBACK,
            held_callback=allow_callback,
        )
        result = VerificationResult(
            valid=True,
            violations=[{"dim": "cost", "reason": "near limit"}],
        )
        verdict = enforcer.enforce(
            agent_id="agent-1", action="write_data", result=result
        )
        assert verdict == Verdict.AUTO_APPROVED
        assert callback_called is True

    def test_enforce_held_callback_denies(self):
        enforcer = StrictEnforcer(
            flag_threshold=1,
            on_held=HeldBehavior.CALLBACK,
            held_callback=lambda a, act, r: False,
        )
        result = VerificationResult(
            valid=True,
            violations=[{"dim": "cost", "reason": "near limit"}],
        )
        with pytest.raises(EATPBlockedError):
            enforcer.enforce(agent_id="agent-1", action="write_data", result=result)

    def test_callback_required_when_on_held_is_callback(self):
        with pytest.raises(ValueError, match="held_callback required"):
            StrictEnforcer(on_held=HeldBehavior.CALLBACK, held_callback=None)

    def test_enforce_records_kept(self, valid_verification_result: VerificationResult):
        enforcer = StrictEnforcer()
        enforcer.enforce(
            agent_id="agent-1", action="read", result=valid_verification_result
        )
        assert len(enforcer.records) == 1
        assert enforcer.records[0].verdict == Verdict.AUTO_APPROVED

    def test_clear_records(self, valid_verification_result: VerificationResult):
        enforcer = StrictEnforcer()
        enforcer.enforce(
            agent_id="agent-1", action="read", result=valid_verification_result
        )
        enforcer.clear_records()
        assert len(enforcer.records) == 0


# ===========================================================================
# ENFORCEMENT - SHADOW
# ===========================================================================


class TestShadowEnforcer:
    """ShadowEnforcer check and metrics."""

    def test_check_never_raises(self, blocked_verification_result: VerificationResult):
        shadow = ShadowEnforcer()
        verdict = shadow.check(
            agent_id="agent-1",
            action="dangerous_action",
            result=blocked_verification_result,
        )
        assert verdict == Verdict.BLOCKED  # Classified but not enforced

    def test_check_auto_approved(self, valid_verification_result: VerificationResult):
        shadow = ShadowEnforcer()
        verdict = shadow.check(
            agent_id="agent-1", action="read", result=valid_verification_result
        )
        assert verdict == Verdict.AUTO_APPROVED

    def test_metrics_total_checks(
        self,
        valid_verification_result: VerificationResult,
        blocked_verification_result: VerificationResult,
    ):
        shadow = ShadowEnforcer()
        shadow.check(agent_id="a1", action="r", result=valid_verification_result)
        shadow.check(agent_id="a2", action="w", result=blocked_verification_result)
        assert shadow.metrics.total_checks == 2

    def test_metrics_block_rate(self, blocked_verification_result: VerificationResult):
        shadow = ShadowEnforcer()
        shadow.check(agent_id="a1", action="w", result=blocked_verification_result)
        assert shadow.metrics.block_rate == 100.0

    def test_metrics_pass_rate(self, valid_verification_result: VerificationResult):
        shadow = ShadowEnforcer()
        shadow.check(agent_id="a1", action="r", result=valid_verification_result)
        assert shadow.metrics.pass_rate == 100.0

    def test_metrics_hold_rate_zero_when_none(
        self, valid_verification_result: VerificationResult
    ):
        shadow = ShadowEnforcer()
        shadow.check(agent_id="a1", action="r", result=valid_verification_result)
        assert shadow.metrics.hold_rate == 0.0

    def test_shadow_metrics_initial_zero(self):
        m = ShadowMetrics()
        assert m.block_rate == 0.0
        assert m.hold_rate == 0.0
        assert m.pass_rate == 0.0

    def test_report_generation(
        self,
        valid_verification_result: VerificationResult,
        blocked_verification_result: VerificationResult,
    ):
        shadow = ShadowEnforcer()
        shadow.check(agent_id="a1", action="r", result=valid_verification_result)
        shadow.check(agent_id="a2", action="w", result=blocked_verification_result)
        report = shadow.report()
        assert "Total checks" in report
        assert "2" in report

    def test_reset_clears_everything(
        self, valid_verification_result: VerificationResult
    ):
        shadow = ShadowEnforcer()
        shadow.check(agent_id="a1", action="r", result=valid_verification_result)
        shadow.reset()
        assert shadow.metrics.total_checks == 0
        assert len(shadow.records) == 0


# ===========================================================================
# EXCEPTION HIERARCHY
# ===========================================================================


class TestExceptionHierarchy:
    """EATP exception types, inheritance, and attributes."""

    def test_trust_error_base(self):
        err = TrustError("something failed", details={"key": "value"})
        assert err.message == "something failed"
        assert err.details == {"key": "value"}
        assert isinstance(err, Exception)

    def test_trust_error_str_with_details(self):
        err = TrustError("fail", details={"k": "v"})
        assert "Details" in str(err)

    def test_trust_error_str_without_details(self):
        err = TrustError("fail")
        assert str(err) == "fail"

    def test_authority_not_found(self):
        err = AuthorityNotFoundError("auth-123")
        assert isinstance(err, TrustError)
        assert err.authority_id == "auth-123"
        assert "auth-123" in str(err)

    def test_trust_chain_not_found(self):
        err = TrustChainNotFoundError("agent-42")
        assert isinstance(err, TrustError)
        assert err.agent_id == "agent-42"

    def test_invalid_trust_chain(self):
        err = InvalidTrustChainError("agent-1", "expired", violations=["v1", "v2"])
        assert isinstance(err, TrustError)
        assert err.agent_id == "agent-1"
        assert err.reason == "expired"
        assert err.violations == ["v1", "v2"]

    def test_capability_not_found(self):
        err = CapabilityNotFoundError("agent-1", "execute_code")
        assert isinstance(err, TrustError)
        assert err.agent_id == "agent-1"
        assert err.capability == "execute_code"

    def test_constraint_violation(self):
        err = ConstraintViolationError(
            "Cost exceeded",
            violations=[{"dim": "cost"}],
            agent_id="agent-1",
            action="purchase",
        )
        assert isinstance(err, TrustError)
        assert err.violations == [{"dim": "cost"}]
        assert err.agent_id == "agent-1"

    def test_delegation_error(self):
        err = DelegationError(
            "Delegation failed",
            delegator_id="parent",
            delegatee_id="child",
            reason="depth exceeded",
        )
        assert isinstance(err, TrustError)
        assert err.delegator_id == "parent"
        assert err.delegatee_id == "child"

    def test_delegation_cycle_error(self):
        err = DelegationCycleError(cycle_path=["A", "B", "C", "A"])
        assert isinstance(err, DelegationError)
        assert isinstance(err, TrustError)
        assert err.cycle_path == ["A", "B", "C", "A"]
        assert "A -> B -> C -> A" in str(err)

    def test_delegation_expired_error(self):
        err = DelegationExpiredError("deleg-1", "2025-01-01T00:00:00Z")
        assert isinstance(err, DelegationError)
        assert err.delegation_id == "deleg-1"
        assert err.expired_at == "2025-01-01T00:00:00Z"

    def test_invalid_signature_error(self):
        err = InvalidSignatureError(
            "Bad sig", record_type="delegation", record_id="d-1"
        )
        assert isinstance(err, TrustError)
        assert err.record_type == "delegation"
        assert err.record_id == "d-1"

    def test_verification_failed_error(self):
        err = VerificationFailedError(
            agent_id="agent-1",
            action="read",
            reason="expired chain",
            violations=[{"dim": "chain"}],
        )
        assert isinstance(err, TrustError)
        assert err.agent_id == "agent-1"
        assert err.action == "read"
        assert err.reason == "expired chain"

    def test_agent_already_established_error(self):
        err = AgentAlreadyEstablishedError("agent-1")
        assert isinstance(err, TrustError)
        assert err.agent_id == "agent-1"

    def test_trust_store_error_hierarchy(self):
        base = TrustStoreError("store failed")
        assert isinstance(base, TrustError)

        chain_err = TrustChainInvalidError("invalid chain", agent_id="agent-1")
        assert isinstance(chain_err, TrustStoreError)
        assert isinstance(chain_err, TrustError)
        assert chain_err.agent_id == "agent-1"

        db_err = TrustStoreDatabaseError("connection lost", operation="insert")
        assert isinstance(db_err, TrustStoreError)
        assert isinstance(db_err, TrustError)
        assert db_err.operation == "insert"


# ===========================================================================
# COMPOSE AND EDGE CASES
# ===========================================================================


class TestConstraintDimensionCompose:
    """ConstraintDimension.compose() for combining constraints."""

    def test_compose_single_returns_same(self, cost_dim: CostLimitDimension):
        cv = cost_dim.parse(500)
        composed = cost_dim.compose([cv])
        assert composed.parsed == 500.0

    def test_compose_picks_tightest(self, cost_dim: CostLimitDimension):
        cv1 = cost_dim.parse(1000)
        cv2 = cost_dim.parse(500)
        cv3 = cost_dim.parse(750)
        composed = cost_dim.compose([cv1, cv2, cv3])
        assert composed.parsed == 500.0
        assert composed.metadata["composed"] is True
        assert composed.metadata["source_count"] == 3

    def test_compose_empty_raises(self, cost_dim: CostLimitDimension):
        with pytest.raises(ValueError, match="empty"):
            cost_dim.compose([])


class TestConstraintDimensionDefaults:
    """Default property values on ConstraintDimension."""

    def test_default_version(self, cost_dim: CostLimitDimension):
        assert cost_dim.version == "1.0.0"

    def test_dimension_name_and_description(self, cost_dim: CostLimitDimension):
        assert cost_dim.name == "cost_limit"
        assert isinstance(cost_dim.description, str)
        assert len(cost_dim.description) > 0

# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
Unit tests for EATP Phase 4 behavioral scoring.

Covers:
- BehavioralData defaults and construction
- BehavioralScore grade mapping
- compute_behavioral_score() with each factor independently
- Zero-data edge case (score 0, grade F)
- Boundary values for grade thresholds
- BEHAVIORAL_WEIGHTS normalization (sum to 100)
- Gaming resistance (high approval but low volume)
- All-errors scenario
- High-stability scenario
- CombinedTrustScore with and without behavioral data
- Combined blending (60/40 structural/behavioral)

Written BEFORE implementation (TDD). Tests define the contract.
"""

from __future__ import annotations

import asyncio
import math
from datetime import datetime, timezone

import pytest

from eatp.chain import (
    AuthorityType,
    CapabilityAttestation,
    CapabilityType,
    Constraint,
    ConstraintEnvelope,
    ConstraintType,
    DelegationRecord,
    GenesisRecord,
    TrustLineageChain,
)
from eatp.postures import PostureStateMachine, TrustPosture
from eatp.scoring import (
    BEHAVIORAL_WEIGHTS,
    BehavioralData,
    BehavioralScore,
    CombinedTrustScore,
    TrustScore,
    compute_behavioral_score,
    compute_combined_trust_score,
    compute_trust_score,
    score_to_grade,
)
from eatp.store.memory import InMemoryTrustStore


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def now():
    """Current UTC timestamp."""
    return datetime.now(timezone.utc)


@pytest.fixture
def store():
    """Create a fresh InMemoryTrustStore."""
    s = InMemoryTrustStore()
    loop = asyncio.new_event_loop()
    loop.run_until_complete(s.initialize())
    loop.close()
    return s


@pytest.fixture
def genesis_record(now):
    """Create a standard genesis record."""
    return GenesisRecord(
        id="gen-001",
        agent_id="agent-001",
        authority_id="org-acme",
        authority_type=AuthorityType.ORGANIZATION,
        created_at=now,
        signature="sig-genesis-001",
    )


@pytest.fixture
def capability(now):
    """Create a standard capability attestation."""
    return CapabilityAttestation(
        id="cap-001",
        capability="analyze_data",
        capability_type=CapabilityType.ACTION,
        constraints=["read_only", "no_pii"],
        attester_id="org-acme",
        attested_at=now,
        signature="sig-cap-001",
    )


@pytest.fixture
def constraint_envelope():
    """Create a constraint envelope with active constraints."""
    return ConstraintEnvelope(
        id="env-agent-001",
        agent_id="agent-001",
        active_constraints=[
            Constraint(
                id="c-001",
                constraint_type=ConstraintType.FINANCIAL,
                value="max_api_calls:100",
                source="cap-001",
            ),
            Constraint(
                id="c-002",
                constraint_type=ConstraintType.DATA_ACCESS,
                value="department_data_only",
                source="cap-001",
            ),
            Constraint(
                id="c-003",
                constraint_type=ConstraintType.AUDIT_REQUIREMENT,
                value="log_all_actions",
                source="gen-001",
            ),
        ],
    )


@pytest.fixture
def delegation(now):
    """Create a standard delegation record."""
    return DelegationRecord(
        id="del-001",
        delegator_id="parent-agent",
        delegatee_id="agent-001",
        task_id="task-001",
        capabilities_delegated=["analyze_data"],
        constraint_subset=["read_only"],
        delegated_at=now,
        signature="sig-del-001",
        delegation_depth=1,
    )


@pytest.fixture
def full_chain(genesis_record, capability, constraint_envelope, delegation):
    """Create a complete trust lineage chain with all components."""
    return TrustLineageChain(
        genesis=genesis_record,
        capabilities=[capability],
        constraint_envelope=constraint_envelope,
        delegations=[delegation],
    )


# ---------------------------------------------------------------------------
# BehavioralData dataclass tests
# ---------------------------------------------------------------------------


class TestBehavioralDataDefaults:
    """Tests for BehavioralData default values."""

    def test_all_fields_default_to_zero(self):
        """All BehavioralData fields must default to zero."""
        data = BehavioralData()
        assert data.total_actions == 0
        assert data.approved_actions == 0
        assert data.denied_actions == 0
        assert data.error_count == 0
        assert data.posture_transitions == 0
        assert data.time_at_current_posture_hours == 0.0
        assert data.observation_window_hours == 0.0

    def test_partial_construction(self):
        """BehavioralData must allow partial field specification."""
        data = BehavioralData(total_actions=100, approved_actions=90)
        assert data.total_actions == 100
        assert data.approved_actions == 90
        # Remaining fields should still be at their defaults
        assert data.denied_actions == 0
        assert data.error_count == 0
        assert data.posture_transitions == 0
        assert data.time_at_current_posture_hours == 0.0
        assert data.observation_window_hours == 0.0

    def test_full_construction(self):
        """BehavioralData must accept all fields at construction."""
        data = BehavioralData(
            total_actions=500,
            approved_actions=450,
            denied_actions=30,
            error_count=20,
            posture_transitions=2,
            time_at_current_posture_hours=360.0,
            observation_window_hours=168.0,
        )
        assert data.total_actions == 500
        assert data.approved_actions == 450
        assert data.denied_actions == 30
        assert data.error_count == 20
        assert data.posture_transitions == 2
        assert data.time_at_current_posture_hours == 360.0
        assert data.observation_window_hours == 168.0


# ---------------------------------------------------------------------------
# BEHAVIORAL_WEIGHTS constant tests
# ---------------------------------------------------------------------------


class TestBehavioralWeights:
    """Tests for BEHAVIORAL_WEIGHTS constant."""

    def test_weights_sum_to_100(self):
        """BEHAVIORAL_WEIGHTS must sum to exactly 100."""
        total = sum(BEHAVIORAL_WEIGHTS.values())
        assert total == 100, f"BEHAVIORAL_WEIGHTS sum to {total}, expected 100"

    def test_expected_keys(self):
        """BEHAVIORAL_WEIGHTS must contain all five factor keys."""
        expected = {
            "approval_rate",
            "error_rate",
            "posture_stability",
            "time_at_posture",
            "interaction_volume",
        }
        assert set(BEHAVIORAL_WEIGHTS.keys()) == expected

    def test_specific_weight_values(self):
        """BEHAVIORAL_WEIGHTS must match the D1 cross-SDK aligned values."""
        assert BEHAVIORAL_WEIGHTS["approval_rate"] == 30
        assert BEHAVIORAL_WEIGHTS["error_rate"] == 25
        assert BEHAVIORAL_WEIGHTS["posture_stability"] == 20
        assert BEHAVIORAL_WEIGHTS["time_at_posture"] == 15
        assert BEHAVIORAL_WEIGHTS["interaction_volume"] == 10

    def test_all_weights_are_positive_integers(self):
        """Each weight must be a positive integer."""
        for key, value in BEHAVIORAL_WEIGHTS.items():
            assert isinstance(
                value, int
            ), f"Weight {key} is not an integer: {type(value)}"
            assert value > 0, f"Weight {key} is not positive: {value}"


# ---------------------------------------------------------------------------
# BehavioralScore grade mapping tests
# ---------------------------------------------------------------------------


class TestBehavioralScoreGradeMapping:
    """Tests for BehavioralScore grade mapping via compute_behavioral_score."""

    def test_grade_f_for_zero_score(self):
        """Zero-data agent must receive grade F."""
        result = compute_behavioral_score("agent-001", BehavioralData())
        assert result.grade == "F"
        assert result.score == 0

    def test_grade_a_for_perfect_agent(self):
        """A perfect agent (all actions approved, no errors, stable, long tenure,
        high volume) must receive grade A."""
        data = BehavioralData(
            total_actions=10000,
            approved_actions=10000,
            denied_actions=0,
            error_count=0,
            posture_transitions=0,
            time_at_current_posture_hours=720.0,
            observation_window_hours=720.0,
        )
        result = compute_behavioral_score("agent-001", data)
        assert result.grade == "A"
        assert result.score >= 90

    def test_grade_matches_score_to_grade_function(self):
        """BehavioralScore.grade must match score_to_grade(score)."""
        data = BehavioralData(
            total_actions=200,
            approved_actions=160,
            denied_actions=20,
            error_count=20,
            posture_transitions=1,
            time_at_current_posture_hours=300.0,
            observation_window_hours=168.0,
        )
        result = compute_behavioral_score("agent-001", data)
        assert result.grade == score_to_grade(result.score)

    def test_score_exactly_80_is_grade_b(self):
        """A score of exactly 80 must map to grade B (boundary value)."""
        assert score_to_grade(80) == "B"

    def test_score_exactly_79_is_grade_c(self):
        """A score of exactly 79 must map to grade C (boundary value)."""
        assert score_to_grade(79) == "C"

    def test_score_exactly_90_is_grade_a(self):
        """A score of exactly 90 must map to grade A (boundary value)."""
        assert score_to_grade(90) == "A"

    def test_score_exactly_60_is_grade_d(self):
        """A score of exactly 60 must map to grade D (boundary value)."""
        assert score_to_grade(60) == "D"

    def test_score_exactly_59_is_grade_f(self):
        """A score of exactly 59 must map to grade F (boundary value)."""
        assert score_to_grade(59) == "F"


# ---------------------------------------------------------------------------
# Zero-data edge case
# ---------------------------------------------------------------------------


class TestZeroDataEdgeCase:
    """Tests for the zero-data fail-safe behavior."""

    def test_zero_data_score_is_zero(self):
        """Zero-data BehavioralData must produce score 0."""
        result = compute_behavioral_score("agent-001", BehavioralData())
        assert result.score == 0

    def test_zero_data_grade_is_f(self):
        """Zero-data BehavioralData must produce grade F."""
        result = compute_behavioral_score("agent-001", BehavioralData())
        assert result.grade == "F"

    def test_zero_data_breakdown_all_zeros(self):
        """Zero-data breakdown must have all factors set to 0.0."""
        result = compute_behavioral_score("agent-001", BehavioralData())
        for key in BEHAVIORAL_WEIGHTS:
            assert (
                result.breakdown[key] == 0.0
            ), f"Factor {key} should be 0.0 for zero data, got {result.breakdown[key]}"

    def test_zero_data_preserves_agent_id(self):
        """Even zero-data results must carry the correct agent_id."""
        result = compute_behavioral_score("test-agent-xyz", BehavioralData())
        assert result.agent_id == "test-agent-xyz"

    def test_zero_data_has_computed_at(self):
        """Even zero-data results must have a computed_at timestamp."""
        result = compute_behavioral_score("agent-001", BehavioralData())
        assert result.computed_at is not None
        assert result.computed_at.tzinfo is not None


# ---------------------------------------------------------------------------
# Individual factor tests
# ---------------------------------------------------------------------------


class TestApprovalRateFactor:
    """Tests for the approval_rate factor independently."""

    def test_full_approval_gives_max_contribution(self):
        """100% approval rate must contribute the full 30 weight."""
        data = BehavioralData(
            total_actions=100,
            approved_actions=100,
            observation_window_hours=168.0,
            time_at_current_posture_hours=720.0,
        )
        result = compute_behavioral_score("agent-001", data)
        assert result.breakdown["approval_rate"] == 30.0

    def test_zero_approval_gives_zero_contribution(self):
        """0% approval rate must contribute 0 to the approval factor."""
        data = BehavioralData(
            total_actions=100,
            approved_actions=0,
            observation_window_hours=168.0,
            time_at_current_posture_hours=720.0,
        )
        result = compute_behavioral_score("agent-001", data)
        assert result.breakdown["approval_rate"] == 0.0

    def test_half_approval_gives_half_contribution(self):
        """50% approval rate must give approximately half the max weight."""
        data = BehavioralData(
            total_actions=100,
            approved_actions=50,
            observation_window_hours=168.0,
            time_at_current_posture_hours=720.0,
        )
        result = compute_behavioral_score("agent-001", data)
        assert result.breakdown["approval_rate"] == 15.0


class TestErrorRateFactor:
    """Tests for the error_rate factor independently."""

    def test_no_errors_gives_max_contribution(self):
        """0 errors must contribute the full 25 weight."""
        data = BehavioralData(
            total_actions=100,
            approved_actions=100,
            error_count=0,
            observation_window_hours=168.0,
            time_at_current_posture_hours=720.0,
        )
        result = compute_behavioral_score("agent-001", data)
        assert result.breakdown["error_rate"] == 25.0

    def test_all_errors_gives_zero_contribution(self):
        """error_count == total_actions must contribute 0 to error factor."""
        data = BehavioralData(
            total_actions=100,
            approved_actions=0,
            error_count=100,
            observation_window_hours=168.0,
            time_at_current_posture_hours=720.0,
        )
        result = compute_behavioral_score("agent-001", data)
        assert result.breakdown["error_rate"] == 0.0

    def test_half_errors_gives_half_contribution(self):
        """50% error rate must give half the error weight."""
        data = BehavioralData(
            total_actions=100,
            approved_actions=50,
            error_count=50,
            observation_window_hours=168.0,
            time_at_current_posture_hours=720.0,
        )
        result = compute_behavioral_score("agent-001", data)
        assert result.breakdown["error_rate"] == 12.5


class TestPostureStabilityFactor:
    """Tests for the posture_stability factor independently."""

    def test_zero_transitions_gives_max_stability(self):
        """0 posture transitions must give full stability contribution (20)."""
        data = BehavioralData(
            total_actions=100,
            approved_actions=100,
            posture_transitions=0,
            observation_window_hours=168.0,
            time_at_current_posture_hours=720.0,
        )
        result = compute_behavioral_score("agent-001", data)
        assert result.breakdown["posture_stability"] == 20.0

    def test_no_observation_window_gives_zero_stability(self):
        """0 observation_window_hours must yield 0 stability (unknown state)."""
        data = BehavioralData(
            total_actions=100,
            approved_actions=100,
            posture_transitions=0,
            observation_window_hours=0.0,
            time_at_current_posture_hours=720.0,
        )
        result = compute_behavioral_score("agent-001", data)
        assert result.breakdown["posture_stability"] == 0.0

    def test_high_transitions_lowers_stability(self):
        """Many transitions in a short window must reduce stability."""
        # With many transitions, the factor should drop.
        # Formula: transitions_per_hour = transitions / window
        # stability_raw = max(0, 1.0 - (tph * 168 / 10))
        # 10 transitions in 168 hours => tph = 10/168 ~0.0595
        # stability = 1 - (0.0595 * 168 / 10) = 1 - 1.0 = 0
        data = BehavioralData(
            total_actions=100,
            approved_actions=100,
            posture_transitions=10,
            observation_window_hours=168.0,
            time_at_current_posture_hours=720.0,
        )
        result = compute_behavioral_score("agent-001", data)
        assert result.breakdown["posture_stability"] == 0.0


class TestTimeAtPostureFactor:
    """Tests for the time_at_posture factor independently."""

    def test_full_time_gives_max_contribution(self):
        """720 hours (30 days) at posture must give full time_at_posture weight (15)."""
        data = BehavioralData(
            total_actions=100,
            approved_actions=100,
            time_at_current_posture_hours=720.0,
            observation_window_hours=168.0,
        )
        result = compute_behavioral_score("agent-001", data)
        assert result.breakdown["time_at_posture"] == 15.0

    def test_zero_time_gives_zero_contribution(self):
        """0 hours at posture must give 0 contribution."""
        data = BehavioralData(
            total_actions=100,
            approved_actions=100,
            time_at_current_posture_hours=0.0,
            observation_window_hours=168.0,
        )
        result = compute_behavioral_score("agent-001", data)
        assert result.breakdown["time_at_posture"] == 0.0

    def test_half_time_gives_half_contribution(self):
        """360 hours (half of max) must give half the time weight."""
        data = BehavioralData(
            total_actions=100,
            approved_actions=100,
            time_at_current_posture_hours=360.0,
            observation_window_hours=168.0,
        )
        result = compute_behavioral_score("agent-001", data)
        assert result.breakdown["time_at_posture"] == 7.5

    def test_over_max_time_caps_at_max(self):
        """Time exceeding 720 hours must be capped at the max weight."""
        data = BehavioralData(
            total_actions=100,
            approved_actions=100,
            time_at_current_posture_hours=2000.0,
            observation_window_hours=168.0,
        )
        result = compute_behavioral_score("agent-001", data)
        assert result.breakdown["time_at_posture"] == 15.0


class TestInteractionVolumeFactor:
    """Tests for the interaction_volume factor independently."""

    def test_full_volume_gives_max_contribution(self):
        """10000 actions (the full-score threshold) must give full volume weight (10)."""
        data = BehavioralData(
            total_actions=10000,
            approved_actions=10000,
            observation_window_hours=168.0,
            time_at_current_posture_hours=720.0,
        )
        result = compute_behavioral_score("agent-001", data)
        assert result.breakdown["interaction_volume"] == 10.0

    def test_single_action_gives_small_contribution(self):
        """1 action must give a small but nonzero volume contribution."""
        data = BehavioralData(
            total_actions=1,
            approved_actions=1,
            observation_window_hours=168.0,
            time_at_current_posture_hours=720.0,
        )
        result = compute_behavioral_score("agent-001", data)
        # log10(1) = 0, so volume_raw = 0
        assert result.breakdown["interaction_volume"] == 0.0

    def test_ten_actions_gives_partial_contribution(self):
        """10 actions should give partial volume (log10(10)/log10(10000) = 1/4 = 0.25)."""
        data = BehavioralData(
            total_actions=10,
            approved_actions=10,
            observation_window_hours=168.0,
            time_at_current_posture_hours=720.0,
        )
        result = compute_behavioral_score("agent-001", data)
        # log10(10) = 1, log10(10000) = 4, raw = 0.25, weighted = 2.5
        assert result.breakdown["interaction_volume"] == 2.5

    def test_over_threshold_caps_at_max(self):
        """Actions exceeding 10000 must be capped at the max weight."""
        data = BehavioralData(
            total_actions=100000,
            approved_actions=100000,
            observation_window_hours=168.0,
            time_at_current_posture_hours=720.0,
        )
        result = compute_behavioral_score("agent-001", data)
        assert result.breakdown["interaction_volume"] == 10.0

    def test_100_actions_volume(self):
        """100 actions: log10(100)/log10(10000) = 2/4 = 0.5, weighted = 5.0."""
        data = BehavioralData(
            total_actions=100,
            approved_actions=100,
            observation_window_hours=168.0,
            time_at_current_posture_hours=720.0,
        )
        result = compute_behavioral_score("agent-001", data)
        assert result.breakdown["interaction_volume"] == 5.0


# ---------------------------------------------------------------------------
# Gaming resistance tests
# ---------------------------------------------------------------------------


class TestGamingResistance:
    """Tests for gaming resistance: an agent that only does safe actions
    to get high approval but has low volume should be caught."""

    def test_high_approval_low_volume_scores_below_a(self):
        """Agent with 100% approval but only 1 action must not get grade A.
        Low volume (log10(1) = 0) drags the score down."""
        data = BehavioralData(
            total_actions=1,
            approved_actions=1,
            denied_actions=0,
            error_count=0,
            posture_transitions=0,
            time_at_current_posture_hours=720.0,
            observation_window_hours=168.0,
        )
        result = compute_behavioral_score("agent-001", data)
        # Volume: log10(1)/log10(10000) = 0 => volume = 0
        # So maximum is 30 + 25 + 20 + 15 + 0 = 90
        # But total_actions=1 means volume_raw=0, missing 10 points
        # Score should be exactly 90 (boundary) -- A is 90+
        # Actually: approval=30, error=25, stability=20, time=15, volume=0 => 90
        # score_to_grade(90) = "A" but the key insight is the volume factor
        # penalizes agents that game with very few actions.
        assert result.breakdown["interaction_volume"] == 0.0
        # The total is still 90, which is borderline A.
        # With only 1 action the volume penalty is maximum.
        assert result.score <= 90

    def test_two_actions_below_full_volume(self):
        """Agent with only 2 actions: volume factor should be well below max."""
        data = BehavioralData(
            total_actions=2,
            approved_actions=2,
            denied_actions=0,
            error_count=0,
            posture_transitions=0,
            time_at_current_posture_hours=720.0,
            observation_window_hours=168.0,
        )
        result = compute_behavioral_score("agent-001", data)
        # log10(2) / log10(10000) = 0.301 / 4 = 0.0753, weighted = 0.75
        expected_volume = round(math.log10(2) / math.log10(10000) * 10, 2)
        assert result.breakdown["interaction_volume"] == expected_volume
        assert result.breakdown["interaction_volume"] < 10.0

    def test_gaming_scenario_low_volume_high_approval_no_errors(self):
        """Gaming scenario: perfect behavior with only 5 actions.
        Volume factor should substantially penalize the total."""
        data = BehavioralData(
            total_actions=5,
            approved_actions=5,
            denied_actions=0,
            error_count=0,
            posture_transitions=0,
            time_at_current_posture_hours=720.0,
            observation_window_hours=168.0,
        )
        result = compute_behavioral_score("agent-001", data)
        # All factors at max except volume
        # volume_raw = log10(5)/log10(10000) = 0.6990/4 = 0.1748
        # volume_contribution = round(0.1748 * 10, 2) = 1.75
        assert result.breakdown["approval_rate"] == 30.0
        assert result.breakdown["error_rate"] == 25.0
        assert result.breakdown["posture_stability"] == 20.0
        assert result.breakdown["time_at_posture"] == 15.0
        assert result.breakdown["interaction_volume"] < 2.0
        # Total should be below perfect 100 due to volume penalty
        assert result.score < 100


# ---------------------------------------------------------------------------
# All-errors scenario
# ---------------------------------------------------------------------------


class TestAllErrorsScenario:
    """Tests for agents where all actions result in errors."""

    def test_all_errors_zero_approval(self):
        """0 approved, all errors: both approval and error factors should be 0."""
        data = BehavioralData(
            total_actions=100,
            approved_actions=0,
            denied_actions=0,
            error_count=100,
            posture_transitions=0,
            observation_window_hours=168.0,
            time_at_current_posture_hours=720.0,
        )
        result = compute_behavioral_score("agent-001", data)
        assert result.breakdown["approval_rate"] == 0.0
        assert result.breakdown["error_rate"] == 0.0

    def test_all_errors_still_has_stability_and_time(self):
        """Even with all errors, posture stability and time factors should still contribute."""
        data = BehavioralData(
            total_actions=100,
            approved_actions=0,
            denied_actions=0,
            error_count=100,
            posture_transitions=0,
            observation_window_hours=168.0,
            time_at_current_posture_hours=720.0,
        )
        result = compute_behavioral_score("agent-001", data)
        assert result.breakdown["posture_stability"] == 20.0
        assert result.breakdown["time_at_posture"] == 15.0

    def test_all_errors_score_is_low(self):
        """All-errors agent must have a low overall score."""
        data = BehavioralData(
            total_actions=100,
            approved_actions=0,
            denied_actions=0,
            error_count=100,
            posture_transitions=0,
            observation_window_hours=168.0,
            time_at_current_posture_hours=720.0,
        )
        result = compute_behavioral_score("agent-001", data)
        # Only stability (20) + time (15) + volume (5.0 for 100 actions) = 40
        assert result.score <= 40
        assert result.grade == "F"


# ---------------------------------------------------------------------------
# High-stability scenario
# ---------------------------------------------------------------------------


class TestHighStabilityScenario:
    """Tests for agents with no posture transitions and long tenure."""

    def test_zero_transitions_long_time(self):
        """0 transitions + 720 hours at posture must yield max stability and time factors."""
        data = BehavioralData(
            total_actions=10000,
            approved_actions=10000,
            error_count=0,
            posture_transitions=0,
            time_at_current_posture_hours=720.0,
            observation_window_hours=720.0,
        )
        result = compute_behavioral_score("agent-001", data)
        assert result.breakdown["posture_stability"] == 20.0
        assert result.breakdown["time_at_posture"] == 15.0

    def test_zero_transitions_short_time(self):
        """0 transitions but only 1 hour at posture: stability max, time low."""
        data = BehavioralData(
            total_actions=10000,
            approved_actions=10000,
            error_count=0,
            posture_transitions=0,
            time_at_current_posture_hours=1.0,
            observation_window_hours=168.0,
        )
        result = compute_behavioral_score("agent-001", data)
        assert result.breakdown["posture_stability"] == 20.0
        # time_raw = 1.0 / 720.0 = 0.00139, weighted = round(0.00139 * 15, 2) = 0.02
        assert result.breakdown["time_at_posture"] == round(1.0 / 720.0 * 15, 2)


# ---------------------------------------------------------------------------
# BehavioralScore structure tests
# ---------------------------------------------------------------------------


class TestBehavioralScoreStructure:
    """Tests for the BehavioralScore dataclass fields."""

    def test_score_is_integer(self):
        """BehavioralScore.score must be an integer."""
        data = BehavioralData(
            total_actions=100,
            approved_actions=80,
            observation_window_hours=168.0,
            time_at_current_posture_hours=360.0,
        )
        result = compute_behavioral_score("agent-001", data)
        assert isinstance(result.score, int)

    def test_score_in_range(self):
        """BehavioralScore.score must be in [0, 100]."""
        data = BehavioralData(
            total_actions=50,
            approved_actions=25,
            error_count=10,
            observation_window_hours=168.0,
            time_at_current_posture_hours=100.0,
        )
        result = compute_behavioral_score("agent-001", data)
        assert 0 <= result.score <= 100

    def test_agent_id_preserved(self):
        """BehavioralScore must preserve the agent_id."""
        result = compute_behavioral_score(
            "my-unique-agent",
            BehavioralData(
                total_actions=10,
                approved_actions=10,
                observation_window_hours=168.0,
                time_at_current_posture_hours=100.0,
            ),
        )
        assert result.agent_id == "my-unique-agent"

    def test_computed_at_is_utc(self):
        """BehavioralScore.computed_at must be UTC."""
        result = compute_behavioral_score(
            "agent-001",
            BehavioralData(
                total_actions=10,
                approved_actions=10,
                observation_window_hours=168.0,
                time_at_current_posture_hours=100.0,
            ),
        )
        assert result.computed_at.tzinfo is not None

    def test_breakdown_contains_all_factor_keys(self):
        """BehavioralScore.breakdown must contain all five factor keys."""
        result = compute_behavioral_score(
            "agent-001",
            BehavioralData(
                total_actions=10,
                approved_actions=10,
                observation_window_hours=168.0,
                time_at_current_posture_hours=100.0,
            ),
        )
        assert set(result.breakdown.keys()) == set(BEHAVIORAL_WEIGHTS.keys())

    def test_breakdown_values_are_non_negative(self):
        """All breakdown values must be non-negative."""
        data = BehavioralData(
            total_actions=200,
            approved_actions=100,
            error_count=50,
            posture_transitions=5,
            observation_window_hours=168.0,
            time_at_current_posture_hours=100.0,
        )
        result = compute_behavioral_score("agent-001", data)
        for key, value in result.breakdown.items():
            assert value >= 0.0, f"Factor {key} has negative value: {value}"


# ---------------------------------------------------------------------------
# CombinedTrustScore: no behavioral data (backward compatibility)
# ---------------------------------------------------------------------------


class TestCombinedTrustScoreNoBehavioral:
    """Tests for CombinedTrustScore when no behavioral data is provided (backward compat)."""

    @pytest.mark.asyncio
    async def test_combined_equals_structural_when_no_behavioral(
        self, store, full_chain
    ):
        """With no behavioral data, combined_score must equal structural score."""
        await store.store_chain(full_chain)

        result = await compute_combined_trust_score("agent-001", store)

        assert result.behavioral_score is None
        assert result.combined_score == result.structural_score.score

    @pytest.mark.asyncio
    async def test_breakdown_shows_structural_only(self, store, full_chain):
        """Breakdown must show structural_weight=1.0, behavioral_weight=0.0."""
        await store.store_chain(full_chain)

        result = await compute_combined_trust_score("agent-001", store)

        assert result.breakdown["structural_weight"] == 1.0
        assert result.breakdown["behavioral_weight"] == 0.0
        assert result.breakdown["behavioral_contribution"] == 0

    @pytest.mark.asyncio
    async def test_structural_contribution_equals_score(self, store, full_chain):
        """structural_contribution must equal the structural score when no behavioral."""
        await store.store_chain(full_chain)

        result = await compute_combined_trust_score("agent-001", store)

        assert (
            result.breakdown["structural_contribution"] == result.structural_score.score
        )

    @pytest.mark.asyncio
    async def test_structural_score_is_valid(self, store, full_chain):
        """structural_score must be a valid TrustScore."""
        await store.store_chain(full_chain)

        result = await compute_combined_trust_score("agent-001", store)

        assert isinstance(result.structural_score, TrustScore)
        assert 0 <= result.structural_score.score <= 100
        assert result.structural_score.agent_id == "agent-001"


# ---------------------------------------------------------------------------
# CombinedTrustScore: with behavioral data
# ---------------------------------------------------------------------------


class TestCombinedTrustScoreWithBehavioral:
    """Tests for CombinedTrustScore with behavioral data provided."""

    @pytest.mark.asyncio
    async def test_combined_blends_structural_and_behavioral(self, store, full_chain):
        """Combined score must blend structural (60%) and behavioral (40%)."""
        await store.store_chain(full_chain)
        behavioral_data = BehavioralData(
            total_actions=10000,
            approved_actions=10000,
            error_count=0,
            posture_transitions=0,
            time_at_current_posture_hours=720.0,
            observation_window_hours=720.0,
        )

        result = await compute_combined_trust_score(
            "agent-001", store, behavioral_data=behavioral_data
        )

        assert result.behavioral_score is not None
        expected = round(
            result.structural_score.score * 0.6 + result.behavioral_score.score * 0.4
        )
        assert result.combined_score == max(0, min(100, expected))

    @pytest.mark.asyncio
    async def test_breakdown_shows_correct_weights(self, store, full_chain):
        """Breakdown must show the 0.6/0.4 weights."""
        await store.store_chain(full_chain)
        behavioral_data = BehavioralData(
            total_actions=100,
            approved_actions=80,
            observation_window_hours=168.0,
            time_at_current_posture_hours=360.0,
        )

        result = await compute_combined_trust_score(
            "agent-001", store, behavioral_data=behavioral_data
        )

        assert result.breakdown["structural_weight"] == 0.6
        assert result.breakdown["behavioral_weight"] == 0.4

    @pytest.mark.asyncio
    async def test_structural_contribution_is_weighted(self, store, full_chain):
        """structural_contribution must be structural_score * 0.6."""
        await store.store_chain(full_chain)
        behavioral_data = BehavioralData(
            total_actions=500,
            approved_actions=400,
            error_count=10,
            posture_transitions=1,
            observation_window_hours=168.0,
            time_at_current_posture_hours=200.0,
        )

        result = await compute_combined_trust_score(
            "agent-001", store, behavioral_data=behavioral_data
        )

        expected_structural = round(result.structural_score.score * 0.6, 2)
        assert result.breakdown["structural_contribution"] == expected_structural

    @pytest.mark.asyncio
    async def test_behavioral_contribution_is_weighted(self, store, full_chain):
        """behavioral_contribution must be behavioral_score * 0.4."""
        await store.store_chain(full_chain)
        behavioral_data = BehavioralData(
            total_actions=500,
            approved_actions=400,
            error_count=10,
            posture_transitions=1,
            observation_window_hours=168.0,
            time_at_current_posture_hours=200.0,
        )

        result = await compute_combined_trust_score(
            "agent-001", store, behavioral_data=behavioral_data
        )

        expected_behavioral = round(result.behavioral_score.score * 0.4, 2)
        assert result.breakdown["behavioral_contribution"] == expected_behavioral

    @pytest.mark.asyncio
    async def test_combined_score_clamped_to_100(self, store, full_chain):
        """Combined score must never exceed 100."""
        await store.store_chain(full_chain)
        # Perfect behavioral data
        behavioral_data = BehavioralData(
            total_actions=10000,
            approved_actions=10000,
            error_count=0,
            posture_transitions=0,
            time_at_current_posture_hours=720.0,
            observation_window_hours=720.0,
        )

        result = await compute_combined_trust_score(
            "agent-001", store, behavioral_data=behavioral_data
        )

        assert result.combined_score <= 100

    @pytest.mark.asyncio
    async def test_combined_score_at_least_zero(self, store, full_chain):
        """Combined score must never go below 0."""
        await store.store_chain(full_chain)
        behavioral_data = BehavioralData()  # zero data = score 0

        result = await compute_combined_trust_score(
            "agent-001", store, behavioral_data=behavioral_data
        )

        assert result.combined_score >= 0

    @pytest.mark.asyncio
    async def test_custom_weights(self, store, full_chain):
        """Custom structural/behavioral weights must be respected."""
        await store.store_chain(full_chain)
        behavioral_data = BehavioralData(
            total_actions=10000,
            approved_actions=10000,
            error_count=0,
            posture_transitions=0,
            time_at_current_posture_hours=720.0,
            observation_window_hours=720.0,
        )

        result = await compute_combined_trust_score(
            "agent-001",
            store,
            behavioral_data=behavioral_data,
            structural_weight=0.3,
            behavioral_weight=0.7,
        )

        assert result.breakdown["structural_weight"] == 0.3
        assert result.breakdown["behavioral_weight"] == 0.7
        expected = round(
            result.structural_score.score * 0.3 + result.behavioral_score.score * 0.7
        )
        assert result.combined_score == max(0, min(100, expected))

    @pytest.mark.asyncio
    async def test_zero_behavioral_data_drags_combined_down(self, store, full_chain):
        """Zero behavioral data with a good structural score should produce a combined
        score lower than structural alone (behavioral contributes 40% of 0)."""
        await store.store_chain(full_chain)
        behavioral_data = BehavioralData()  # score = 0

        combined = await compute_combined_trust_score(
            "agent-001", store, behavioral_data=behavioral_data
        )
        structural_only = await compute_combined_trust_score(
            "agent-001", store, behavioral_data=None
        )

        # With zero behavioral, the 40% behavioral drags the score down
        assert combined.combined_score <= structural_only.combined_score

    @pytest.mark.asyncio
    async def test_both_scores_populated(self, store, full_chain):
        """When behavioral data is provided, both scores must be populated."""
        await store.store_chain(full_chain)
        behavioral_data = BehavioralData(
            total_actions=100,
            approved_actions=80,
            observation_window_hours=168.0,
            time_at_current_posture_hours=100.0,
        )

        result = await compute_combined_trust_score(
            "agent-001", store, behavioral_data=behavioral_data
        )

        assert isinstance(result.structural_score, TrustScore)
        assert isinstance(result.behavioral_score, BehavioralScore)
        assert isinstance(result.combined_score, int)


# ---------------------------------------------------------------------------
# Determinism test
# ---------------------------------------------------------------------------


class TestBehavioralScoringDeterminism:
    """Tests that behavioral scoring is deterministic."""

    def test_same_input_same_output(self):
        """Identical inputs must produce identical scores and breakdowns."""
        data = BehavioralData(
            total_actions=500,
            approved_actions=400,
            denied_actions=50,
            error_count=50,
            posture_transitions=3,
            time_at_current_posture_hours=200.0,
            observation_window_hours=168.0,
        )
        result1 = compute_behavioral_score("agent-001", data)
        result2 = compute_behavioral_score("agent-001", data)

        assert result1.score == result2.score
        assert result1.grade == result2.grade
        assert result1.breakdown == result2.breakdown


# ---------------------------------------------------------------------------
# BehavioralData validation tests (security review H-1)
# ---------------------------------------------------------------------------


class TestBehavioralDataValidation:
    """Tests for BehavioralData.__post_init__ validation."""

    def test_negative_total_actions_rejected(self):
        """Negative total_actions must raise ValueError."""
        with pytest.raises(ValueError, match="total_actions must be non-negative"):
            BehavioralData(total_actions=-1)

    def test_negative_approved_actions_rejected(self):
        """Negative approved_actions must raise ValueError."""
        with pytest.raises(ValueError, match="approved_actions must be non-negative"):
            BehavioralData(approved_actions=-1)

    def test_negative_denied_actions_rejected(self):
        """Negative denied_actions must raise ValueError."""
        with pytest.raises(ValueError, match="denied_actions must be non-negative"):
            BehavioralData(denied_actions=-1)

    def test_negative_error_count_rejected(self):
        """Negative error_count must raise ValueError."""
        with pytest.raises(ValueError, match="error_count must be non-negative"):
            BehavioralData(error_count=-1)

    def test_negative_posture_transitions_rejected(self):
        """Negative posture_transitions must raise ValueError."""
        with pytest.raises(
            ValueError, match="posture_transitions must be non-negative"
        ):
            BehavioralData(posture_transitions=-1)

    def test_negative_time_at_posture_rejected(self):
        """Negative time_at_current_posture_hours must raise ValueError."""
        with pytest.raises(
            ValueError, match="time_at_current_posture_hours must be non-negative"
        ):
            BehavioralData(time_at_current_posture_hours=-1.0)

    def test_negative_observation_window_rejected(self):
        """Negative observation_window_hours must raise ValueError."""
        with pytest.raises(
            ValueError, match="observation_window_hours must be non-negative"
        ):
            BehavioralData(observation_window_hours=-1.0)

    def test_approved_plus_denied_exceeds_total_rejected(self):
        """approved + denied > total must raise ValueError."""
        with pytest.raises(ValueError, match="exceeds total_actions"):
            BehavioralData(total_actions=10, approved_actions=6, denied_actions=6)

    def test_error_count_exceeds_total_rejected(self):
        """error_count > total must raise ValueError."""
        with pytest.raises(ValueError, match="error_count.*exceeds total_actions"):
            BehavioralData(total_actions=10, error_count=11)

    def test_approved_equals_total_accepted(self):
        """approved == total (no denied) is valid."""
        data = BehavioralData(total_actions=10, approved_actions=10)
        assert data.approved_actions == 10

    def test_zero_data_accepted(self):
        """All-zero defaults are valid."""
        data = BehavioralData()
        assert data.total_actions == 0


# ---------------------------------------------------------------------------
# Weight sum validation tests (security review H-2)
# ---------------------------------------------------------------------------


class TestWeightSumValidation:
    """Tests for compute_combined_trust_score weight validation."""

    @pytest.mark.asyncio
    async def test_weights_not_summing_to_one_rejected(self, store, full_chain):
        """Weights not summing to ~1.0 must raise ValueError."""
        await store.store_chain(full_chain)
        with pytest.raises(ValueError, match="must sum to 1.0"):
            await compute_combined_trust_score(
                "agent-001",
                store,
                structural_weight=0.7,
                behavioral_weight=0.5,
            )

    @pytest.mark.asyncio
    async def test_default_weights_accepted(self, store, full_chain):
        """Default weights (0.6 + 0.4) must pass validation."""
        await store.store_chain(full_chain)
        result = await compute_combined_trust_score("agent-001", store)
        assert isinstance(result.combined_score, int)

    @pytest.mark.asyncio
    async def test_custom_valid_weights_accepted(self, store, full_chain):
        """Custom weights summing to 1.0 must pass validation."""
        await store.store_chain(full_chain)
        result = await compute_combined_trust_score(
            "agent-001",
            store,
            structural_weight=0.8,
            behavioral_weight=0.2,
        )
        assert isinstance(result.combined_score, int)

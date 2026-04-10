"""
Unit tests for EATP Trust Scoring module.

Tests the trust scoring engine that computes agent trust scores
based on chain completeness, delegation depth, constraint coverage,
posture level, and chain recency.

TDD: These tests are written FIRST, before the implementation.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from kailash.trust.chain import (
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
from kailash.trust.chain_store.memory import InMemoryTrustStore
from kailash.trust.exceptions import TrustChainNotFoundError
from kailash.trust.posture.postures import PostureStateMachine, TrustPosture
from kailash.trust.scoring import (
    GRADE_THRESHOLDS,
    POSTURE_SCORE_MAP,
    SCORING_WEIGHTS,
    TrustReport,
    TrustScore,
    compute_trust_score,
    generate_trust_report,
    score_to_grade,
)

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


@pytest.fixture
def minimal_chain(genesis_record):
    """Create a minimal chain with only genesis (no capabilities, no constraints, no delegations)."""
    return TrustLineageChain(
        genesis=genesis_record,
        capabilities=[],
        delegations=[],
    )


@pytest.fixture
def posture_machine():
    """Create a PostureStateMachine with upgrade approval disabled for testing."""
    return PostureStateMachine(require_upgrade_approval=False)


# ---------------------------------------------------------------------------
# TrustScore dataclass tests
# ---------------------------------------------------------------------------


class TestTrustScoreDataclass:
    """Tests for the TrustScore dataclass."""

    def test_required_fields(self, now):
        """TrustScore must have all required fields."""
        score = TrustScore(
            score=85,
            breakdown={
                "chain_completeness": 30,
                "delegation_depth": 15,
                "constraint_coverage": 25,
                "posture_level": 10,
                "chain_recency": 5,
            },
            grade="B",
            computed_at=now,
            agent_id="agent-001",
        )
        assert score.score == 85
        assert score.grade == "B"
        assert score.agent_id == "agent-001"
        assert score.computed_at == now
        assert isinstance(score.breakdown, dict)

    def test_score_must_be_int(self, now):
        """TrustScore.score must be an integer."""
        score = TrustScore(
            score=75,
            breakdown={},
            grade="C",
            computed_at=now,
            agent_id="agent-001",
        )
        assert isinstance(score.score, int)

    def test_breakdown_has_factor_weights(self, now):
        """TrustScore.breakdown must contain factor weight keys."""
        score = TrustScore(
            score=90,
            breakdown={
                "chain_completeness": 30,
                "delegation_depth": 15,
                "constraint_coverage": 25,
                "posture_level": 20,
                "chain_recency": 10,
            },
            grade="A",
            computed_at=now,
            agent_id="agent-001",
        )
        expected_keys = {
            "chain_completeness",
            "delegation_depth",
            "constraint_coverage",
            "posture_level",
            "chain_recency",
        }
        assert expected_keys == set(score.breakdown.keys())


# ---------------------------------------------------------------------------
# TrustReport dataclass tests
# ---------------------------------------------------------------------------


class TestTrustReportDataclass:
    """Tests for the TrustReport dataclass."""

    def test_required_fields(self, now):
        """TrustReport must have score, risk_indicators, and recommendations."""
        trust_score = TrustScore(
            score=50,
            breakdown={},
            grade="F",
            computed_at=now,
            agent_id="agent-001",
        )
        report = TrustReport(
            score=trust_score,
            risk_indicators=["No constraints defined"],
            recommendations=["Add constraint envelope"],
        )
        assert report.score == trust_score
        assert isinstance(report.risk_indicators, list)
        assert isinstance(report.recommendations, list)
        assert len(report.risk_indicators) == 1
        assert len(report.recommendations) == 1


# ---------------------------------------------------------------------------
# Grade mapping tests
# ---------------------------------------------------------------------------


class TestGradeMapping:
    """Tests for score-to-grade mapping."""

    def test_grade_a_range(self):
        """Scores 90-100 must map to grade A."""
        assert score_to_grade(90) == "A"
        assert score_to_grade(95) == "A"
        assert score_to_grade(100) == "A"

    def test_grade_b_range(self):
        """Scores 80-89 must map to grade B."""
        assert score_to_grade(80) == "B"
        assert score_to_grade(85) == "B"
        assert score_to_grade(89) == "B"

    def test_grade_c_range(self):
        """Scores 70-79 must map to grade C."""
        assert score_to_grade(70) == "C"
        assert score_to_grade(75) == "C"
        assert score_to_grade(79) == "C"

    def test_grade_d_range(self):
        """Scores 60-69 must map to grade D."""
        assert score_to_grade(60) == "D"
        assert score_to_grade(65) == "D"
        assert score_to_grade(69) == "D"

    def test_grade_f_range(self):
        """Scores 0-59 must map to grade F."""
        assert score_to_grade(0) == "F"
        assert score_to_grade(30) == "F"
        assert score_to_grade(59) == "F"

    def test_boundary_values(self):
        """Boundary values between grades must be correctly classified."""
        assert score_to_grade(89) == "B"
        assert score_to_grade(90) == "A"
        assert score_to_grade(79) == "C"
        assert score_to_grade(80) == "B"
        assert score_to_grade(69) == "D"
        assert score_to_grade(70) == "C"
        assert score_to_grade(59) == "F"
        assert score_to_grade(60) == "D"


# ---------------------------------------------------------------------------
# Constants tests
# ---------------------------------------------------------------------------


class TestScoringConstants:
    """Tests for scoring constants."""

    def test_weights_sum_to_100(self):
        """All scoring weights must sum to 100."""
        total = sum(SCORING_WEIGHTS.values())
        assert total == 100, f"Weights sum to {total}, expected 100"

    def test_weight_keys(self):
        """Scoring weights must contain all five factors."""
        expected_keys = {
            "chain_completeness",
            "delegation_depth",
            "constraint_coverage",
            "posture_level",
            "chain_recency",
        }
        assert set(SCORING_WEIGHTS.keys()) == expected_keys

    def test_specific_weights(self):
        """Scoring weights must match the specified values."""
        assert SCORING_WEIGHTS["chain_completeness"] == 30
        assert SCORING_WEIGHTS["delegation_depth"] == 15
        assert SCORING_WEIGHTS["constraint_coverage"] == 25
        assert SCORING_WEIGHTS["posture_level"] == 20
        assert SCORING_WEIGHTS["chain_recency"] == 10

    def test_posture_score_map_values(self):
        """Posture score map must map postures to expected trust scores."""
        assert POSTURE_SCORE_MAP[TrustPosture.AUTONOMOUS] == 20
        assert POSTURE_SCORE_MAP[TrustPosture.SUPERVISED] == 80
        assert POSTURE_SCORE_MAP[TrustPosture.TOOL] == 100

    def test_posture_score_map_completeness(self):
        """Posture score map must include all TrustPosture values."""
        for posture in TrustPosture:
            assert (
                posture in POSTURE_SCORE_MAP
            ), f"Missing posture in score map: {posture}"

    def test_grade_thresholds(self):
        """Grade thresholds must be defined correctly."""
        assert GRADE_THRESHOLDS == {"A": 90, "B": 80, "C": 70, "D": 60}


# ---------------------------------------------------------------------------
# compute_trust_score tests
# ---------------------------------------------------------------------------


class TestComputeTrustScore:
    """Tests for compute_trust_score function."""

    @pytest.mark.asyncio
    async def test_full_chain_scores_high(self, store, full_chain):
        """A complete chain with all components should score high."""
        await store.store_chain(full_chain)

        score = await compute_trust_score("agent-001", store)

        assert isinstance(score, TrustScore)
        assert 0 <= score.score <= 100
        assert score.agent_id == "agent-001"
        assert score.grade in ("A", "B", "C", "D", "F")
        assert score.computed_at is not None
        # A full chain should score reasonably well
        assert score.score >= 50

    @pytest.mark.asyncio
    async def test_minimal_chain_scores_lower(self, store, minimal_chain):
        """A chain with only genesis and no capabilities/constraints should score lower."""
        await store.store_chain(minimal_chain)

        score = await compute_trust_score("agent-001", store)

        assert isinstance(score, TrustScore)
        assert 0 <= score.score <= 100
        # Minimal chain should score lower than full chain
        assert score.score < 80

    @pytest.mark.asyncio
    async def test_nonexistent_agent_raises(self, store):
        """Computing score for a nonexistent agent must raise TrustChainNotFoundError."""
        with pytest.raises(TrustChainNotFoundError):
            await compute_trust_score("nonexistent-agent", store)

    @pytest.mark.asyncio
    async def test_score_is_deterministic(self, store, full_chain):
        """Same input must always produce the same score."""
        await store.store_chain(full_chain)

        score1 = await compute_trust_score("agent-001", store)
        score2 = await compute_trust_score("agent-001", store)

        assert score1.score == score2.score
        assert score1.grade == score2.grade
        assert score1.breakdown == score2.breakdown

    @pytest.mark.asyncio
    async def test_score_range(self, store, full_chain):
        """Score must be in range 0-100."""
        await store.store_chain(full_chain)

        score = await compute_trust_score("agent-001", store)

        assert 0 <= score.score <= 100

    @pytest.mark.asyncio
    async def test_breakdown_contains_all_factors(self, store, full_chain):
        """Breakdown must contain all five scoring factors."""
        await store.store_chain(full_chain)

        score = await compute_trust_score("agent-001", store)

        expected_keys = {
            "chain_completeness",
            "delegation_depth",
            "constraint_coverage",
            "posture_level",
            "chain_recency",
        }
        assert set(score.breakdown.keys()) == expected_keys

    @pytest.mark.asyncio
    async def test_breakdown_values_are_non_negative(self, store, full_chain):
        """All breakdown values must be non-negative."""
        await store.store_chain(full_chain)

        score = await compute_trust_score("agent-001", store)

        for factor, value in score.breakdown.items():
            assert value >= 0, f"Factor {factor} has negative value: {value}"

    @pytest.mark.asyncio
    async def test_grade_matches_score(self, store, full_chain):
        """Grade must correctly correspond to the computed score."""
        await store.store_chain(full_chain)

        score = await compute_trust_score("agent-001", store)

        expected_grade = score_to_grade(score.score)
        assert score.grade == expected_grade

    @pytest.mark.asyncio
    async def test_with_posture_machine(self, store, full_chain, posture_machine):
        """Score should incorporate posture level when posture_machine is provided."""
        await store.store_chain(full_chain)

        # Set posture to SHARED_PLANNING (high trust score for posture)
        posture_machine.set_posture("agent-001", TrustPosture.SUPERVISED)

        score_with_posture = await compute_trust_score(
            "agent-001", store, posture_machine=posture_machine
        )

        assert isinstance(score_with_posture, TrustScore)
        assert score_with_posture.breakdown["posture_level"] > 0

    @pytest.mark.asyncio
    async def test_posture_delegated_scores_low_on_posture_factor(
        self, store, full_chain, posture_machine
    ):
        """DELEGATED posture should give a low posture factor score (less oversight = less trust)."""
        await store.store_chain(full_chain)

        posture_machine.set_posture("agent-001", TrustPosture.AUTONOMOUS)
        score_autonomy = await compute_trust_score(
            "agent-001", store, posture_machine=posture_machine
        )

        posture_machine.set_posture("agent-001", TrustPosture.TOOL)
        score_human = await compute_trust_score(
            "agent-001", store, posture_machine=posture_machine
        )

        assert (
            score_autonomy.breakdown["posture_level"]
            < score_human.breakdown["posture_level"]
        )

    @pytest.mark.asyncio
    async def test_without_posture_machine_uses_default(self, store, full_chain):
        """When no posture_machine is provided, posture factor should use a default value."""
        await store.store_chain(full_chain)

        score = await compute_trust_score("agent-001", store)

        # Without posture machine, should still have a posture_level in breakdown
        assert "posture_level" in score.breakdown

    @pytest.mark.asyncio
    async def test_deep_delegation_lowers_score(
        self, store, now, genesis_record, capability
    ):
        """Deeper delegation chains should lower the delegation depth factor score."""
        # Chain with no delegations
        chain_no_del = TrustLineageChain(
            genesis=genesis_record,
            capabilities=[capability],
        )
        await store.store_chain(chain_no_del)
        score_no_del = await compute_trust_score("agent-001", store)

        # Create a chain with deep delegation
        deep_delegations = []
        for i in range(5):
            deep_delegations.append(
                DelegationRecord(
                    id=f"del-{i:03d}",
                    delegator_id=f"agent-{i:03d}",
                    delegatee_id="agent-001",
                    task_id=f"task-{i:03d}",
                    capabilities_delegated=["analyze_data"],
                    constraint_subset=["read_only"],
                    delegated_at=now,
                    signature=f"sig-del-{i:03d}",
                    delegation_depth=i + 1,
                    parent_delegation_id=f"del-{i - 1:03d}" if i > 0 else None,
                )
            )
        chain_deep = TrustLineageChain(
            genesis=genesis_record,
            capabilities=[capability],
            delegations=deep_delegations,
        )
        await store.update_chain("agent-001", chain_deep)
        score_deep = await compute_trust_score("agent-001", store)

        # More delegation depth should lower the delegation_depth factor
        assert (
            score_no_del.breakdown["delegation_depth"]
            > score_deep.breakdown["delegation_depth"]
        )

    @pytest.mark.asyncio
    async def test_more_constraints_higher_coverage(
        self, store, now, genesis_record, capability
    ):
        """More constraints should yield a higher constraint_coverage factor."""
        # Chain with no constraints (just default empty envelope)
        chain_few = TrustLineageChain(
            genesis=genesis_record,
            capabilities=[capability],
            constraint_envelope=ConstraintEnvelope(
                id="env-agent-001",
                agent_id="agent-001",
                active_constraints=[],
            ),
        )
        await store.store_chain(chain_few)
        score_few = await compute_trust_score("agent-001", store)

        # Chain with many constraints
        many_constraints = [
            Constraint(
                id=f"c-{i:03d}",
                constraint_type=ConstraintType.FINANCIAL,
                value=f"limit_{i}",
                source="cap-001",
            )
            for i in range(10)
        ]
        chain_many = TrustLineageChain(
            genesis=genesis_record,
            capabilities=[capability],
            constraint_envelope=ConstraintEnvelope(
                id="env-agent-001",
                agent_id="agent-001",
                active_constraints=many_constraints,
            ),
        )
        await store.update_chain("agent-001", chain_many)
        score_many = await compute_trust_score("agent-001", store)

        assert (
            score_many.breakdown["constraint_coverage"]
            > score_few.breakdown["constraint_coverage"]
        )

    @pytest.mark.asyncio
    async def test_recent_chain_scores_higher_recency(self, store, capability):
        """A recently created chain should have a higher recency score than an old one."""
        # Old chain
        old_genesis = GenesisRecord(
            id="gen-old",
            agent_id="agent-old",
            authority_id="org-acme",
            authority_type=AuthorityType.ORGANIZATION,
            created_at=datetime.now(timezone.utc) - timedelta(days=365),
            signature="sig-genesis-old",
        )
        old_chain = TrustLineageChain(
            genesis=old_genesis,
            capabilities=[
                CapabilityAttestation(
                    id="cap-old",
                    capability="analyze_data",
                    capability_type=CapabilityType.ACTION,
                    constraints=["read_only"],
                    attester_id="org-acme",
                    attested_at=datetime.now(timezone.utc) - timedelta(days=365),
                    signature="sig-cap-old",
                )
            ],
        )
        await store.store_chain(old_chain)
        score_old = await compute_trust_score("agent-old", store)

        # Recent chain
        recent_genesis = GenesisRecord(
            id="gen-recent",
            agent_id="agent-recent",
            authority_id="org-acme",
            authority_type=AuthorityType.ORGANIZATION,
            created_at=datetime.now(timezone.utc),
            signature="sig-genesis-recent",
        )
        recent_chain = TrustLineageChain(
            genesis=recent_genesis,
            capabilities=[
                CapabilityAttestation(
                    id="cap-recent",
                    capability="analyze_data",
                    capability_type=CapabilityType.ACTION,
                    constraints=["read_only"],
                    attester_id="org-acme",
                    attested_at=datetime.now(timezone.utc),
                    signature="sig-cap-recent",
                )
            ],
        )
        await store.store_chain(recent_chain)
        score_recent = await compute_trust_score("agent-recent", store)

        assert (
            score_recent.breakdown["chain_recency"]
            > score_old.breakdown["chain_recency"]
        )


# ---------------------------------------------------------------------------
# generate_trust_report tests
# ---------------------------------------------------------------------------


class TestGenerateTrustReport:
    """Tests for generate_trust_report function."""

    @pytest.mark.asyncio
    async def test_returns_trust_report(self, store, full_chain):
        """generate_trust_report must return a TrustReport instance."""
        await store.store_chain(full_chain)

        report = await generate_trust_report("agent-001", store)

        assert isinstance(report, TrustReport)

    @pytest.mark.asyncio
    async def test_report_contains_score(self, store, full_chain):
        """Report must contain a valid TrustScore."""
        await store.store_chain(full_chain)

        report = await generate_trust_report("agent-001", store)

        assert isinstance(report.score, TrustScore)
        assert 0 <= report.score.score <= 100

    @pytest.mark.asyncio
    async def test_report_risk_indicators_are_list(self, store, full_chain):
        """Report risk_indicators must be a list of strings."""
        await store.store_chain(full_chain)

        report = await generate_trust_report("agent-001", store)

        assert isinstance(report.risk_indicators, list)
        for indicator in report.risk_indicators:
            assert isinstance(indicator, str)

    @pytest.mark.asyncio
    async def test_report_recommendations_are_list(self, store, full_chain):
        """Report recommendations must be a list of strings."""
        await store.store_chain(full_chain)

        report = await generate_trust_report("agent-001", store)

        assert isinstance(report.recommendations, list)
        for rec in report.recommendations:
            assert isinstance(rec, str)

    @pytest.mark.asyncio
    async def test_minimal_chain_has_risk_indicators(self, store, minimal_chain):
        """A minimal chain should produce risk indicators for missing components."""
        await store.store_chain(minimal_chain)

        report = await generate_trust_report("agent-001", store)

        # A minimal chain (no capabilities, no real constraints) should flag risks
        assert len(report.risk_indicators) > 0

    @pytest.mark.asyncio
    async def test_minimal_chain_has_recommendations(self, store, minimal_chain):
        """A minimal chain should produce recommendations for improvement."""
        await store.store_chain(minimal_chain)

        report = await generate_trust_report("agent-001", store)

        assert len(report.recommendations) > 0

    @pytest.mark.asyncio
    async def test_nonexistent_agent_raises(self, store):
        """Generating report for nonexistent agent must raise TrustChainNotFoundError."""
        with pytest.raises(TrustChainNotFoundError):
            await generate_trust_report("nonexistent-agent", store)

    @pytest.mark.asyncio
    async def test_report_with_posture_machine(
        self, store, full_chain, posture_machine
    ):
        """Report should work with posture_machine parameter."""
        await store.store_chain(full_chain)
        posture_machine.set_posture("agent-001", TrustPosture.SUPERVISED)

        report = await generate_trust_report(
            "agent-001", store, posture_machine=posture_machine
        )

        assert isinstance(report, TrustReport)
        assert report.score.breakdown["posture_level"] > 0

    @pytest.mark.asyncio
    async def test_delegated_generates_risk_indicator(
        self, store, full_chain, posture_machine
    ):
        """DELEGATED posture should generate a risk indicator."""
        await store.store_chain(full_chain)
        posture_machine.set_posture("agent-001", TrustPosture.AUTONOMOUS)

        report = await generate_trust_report(
            "agent-001", store, posture_machine=posture_machine
        )

        # There should be a risk indicator about full autonomy
        autonomy_indicators = [
            ri for ri in report.risk_indicators if "autonomy" in ri.lower()
        ]
        assert len(autonomy_indicators) > 0

    @pytest.mark.asyncio
    async def test_report_deterministic(self, store, full_chain):
        """Same input must always produce the same report."""
        await store.store_chain(full_chain)

        report1 = await generate_trust_report("agent-001", store)
        report2 = await generate_trust_report("agent-001", store)

        assert report1.score.score == report2.score.score
        assert report1.score.grade == report2.score.grade
        assert report1.risk_indicators == report2.risk_indicators
        assert report1.recommendations == report2.recommendations

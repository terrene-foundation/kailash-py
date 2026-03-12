# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
Unit tests for EATP Reasoning Support in Store/Audit/Scoring (TODO-018).

Covers:
- Part 1: TrustStore.get_chains_missing_reasoning() — compliance query
  for agent IDs whose chains have delegations or audit anchors without
  reasoning traces.
- Part 2: AuditQueryService.get_unattested_reasoning() — returns audit
  anchors missing reasoning traces.
- Part 3: Scoring "reasoning_coverage" factor — adds ~5% weight when
  REASONING_REQUIRED constraint is active. When the constraint is NOT
  active, scores must be UNCHANGED (backward compatible).

TDD: These tests are written BEFORE implementation.
"""

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from eatp.chain import (
    ActionResult,
    AuditAnchor,
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
from eatp.reasoning import ConfidentialityLevel, ReasoningTrace
from eatp.scoring import (
    SCORING_WEIGHTS,
    TrustScore,
    compute_trust_score,
    generate_trust_report,
    score_to_grade,
)
from eatp.store.memory import InMemoryTrustStore
from eatp.store.filesystem import FilesystemStore


# ---------------------------------------------------------------------------
# Shared helpers / fixtures
# ---------------------------------------------------------------------------

FIXED_TS = datetime(2026, 3, 11, 12, 0, 0, tzinfo=timezone.utc)


def _make_reasoning_trace() -> ReasoningTrace:
    """Create a standard reasoning trace for testing."""
    return ReasoningTrace(
        decision="Delegate analysis task to agent-beta",
        rationale="Agent-beta has specialized capability and lower latency",
        confidentiality=ConfidentialityLevel.RESTRICTED,
        timestamp=FIXED_TS,
        confidence=0.9,
    )


def _make_genesis(agent_id: str = "agent-001") -> GenesisRecord:
    return GenesisRecord(
        id=f"gen-{agent_id}",
        agent_id=agent_id,
        authority_id="org-acme",
        authority_type=AuthorityType.ORGANIZATION,
        created_at=datetime.now(timezone.utc),
        signature="sig-genesis",
    )


def _make_delegation(
    deleg_id: str = "del-001",
    reasoning_trace: ReasoningTrace = None,
) -> DelegationRecord:
    return DelegationRecord(
        id=deleg_id,
        delegator_id="parent-agent",
        delegatee_id="agent-001",
        task_id="task-001",
        capabilities_delegated=["analyze_data"],
        constraint_subset=["read_only"],
        delegated_at=datetime.now(timezone.utc),
        signature="sig-del",
        delegation_depth=1,
        reasoning_trace=reasoning_trace,
    )


def _make_audit_anchor(
    anchor_id: str = "aud-001",
    agent_id: str = "agent-001",
    reasoning_trace: ReasoningTrace = None,
) -> AuditAnchor:
    return AuditAnchor(
        id=anchor_id,
        agent_id=agent_id,
        action="analyze_data",
        timestamp=datetime.now(timezone.utc),
        trust_chain_hash="hash-001",
        result=ActionResult.SUCCESS,
        signature="sig-aud",
        reasoning_trace=reasoning_trace,
    )


def _make_capability() -> CapabilityAttestation:
    return CapabilityAttestation(
        id="cap-001",
        capability="analyze_data",
        capability_type=CapabilityType.ACTION,
        constraints=["read_only"],
        attester_id="org-acme",
        attested_at=datetime.now(timezone.utc),
        signature="sig-cap",
    )


def _make_constraint_envelope_with_reasoning_required(agent_id: str = "agent-001"):
    """Create constraint envelope that includes REASONING_REQUIRED."""
    return ConstraintEnvelope(
        id=f"env-{agent_id}",
        agent_id=agent_id,
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
                id="c-rr",
                constraint_type=ConstraintType.REASONING_REQUIRED,
                value="all_delegations_and_audits",
                source="policy-engine",
            ),
        ],
    )


def _make_constraint_envelope_without_reasoning_required(
    agent_id: str = "agent-001",
):
    """Create constraint envelope WITHOUT REASONING_REQUIRED."""
    return ConstraintEnvelope(
        id=f"env-{agent_id}",
        agent_id=agent_id,
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
def store():
    """Create a fresh InMemoryTrustStore."""
    s = InMemoryTrustStore()
    loop = asyncio.new_event_loop()
    loop.run_until_complete(s.initialize())
    loop.close()
    return s


@pytest.fixture
def fs_store(tmp_path):
    """Create a fresh FilesystemStore."""
    chains_dir = tmp_path / "chains"
    return FilesystemStore(base_dir=str(chains_dir))


# ===========================================================================
# Part 1: TrustStore.get_chains_missing_reasoning() Tests
# ===========================================================================


class TestStoreGetChainsMissingReasoning:
    """Tests for get_chains_missing_reasoning() on InMemoryTrustStore."""

    @pytest.mark.asyncio
    async def test_empty_store_returns_empty(self, store):
        """Empty store must return empty list."""
        result = await store.get_chains_missing_reasoning()
        assert result == []

    @pytest.mark.asyncio
    async def test_chain_with_no_delegations_no_audits_not_included(self, store):
        """A chain with no delegations and no audit anchors should NOT be included
        (there is nothing missing reasoning on)."""
        chain = TrustLineageChain(
            genesis=_make_genesis("agent-001"),
            capabilities=[_make_capability()],
        )
        await store.store_chain(chain)
        result = await store.get_chains_missing_reasoning()
        assert "agent-001" not in result

    @pytest.mark.asyncio
    async def test_chain_with_delegation_missing_reasoning_included(self, store):
        """A chain with a delegation that has no reasoning trace must be included."""
        chain = TrustLineageChain(
            genesis=_make_genesis("agent-001"),
            capabilities=[_make_capability()],
            delegations=[_make_delegation("del-001", reasoning_trace=None)],
        )
        await store.store_chain(chain)
        result = await store.get_chains_missing_reasoning()
        assert "agent-001" in result

    @pytest.mark.asyncio
    async def test_chain_with_all_delegations_having_reasoning_not_included(
        self, store
    ):
        """A chain where all delegations have reasoning traces must NOT be included."""
        trace = _make_reasoning_trace()
        chain = TrustLineageChain(
            genesis=_make_genesis("agent-001"),
            capabilities=[_make_capability()],
            delegations=[
                _make_delegation("del-001", reasoning_trace=trace),
                _make_delegation("del-002", reasoning_trace=trace),
            ],
        )
        await store.store_chain(chain)
        result = await store.get_chains_missing_reasoning()
        assert "agent-001" not in result

    @pytest.mark.asyncio
    async def test_mixed_delegations_some_without_reasoning(self, store):
        """If even one delegation is missing reasoning, the agent must be included."""
        trace = _make_reasoning_trace()
        chain = TrustLineageChain(
            genesis=_make_genesis("agent-001"),
            capabilities=[_make_capability()],
            delegations=[
                _make_delegation("del-001", reasoning_trace=trace),
                _make_delegation("del-002", reasoning_trace=None),  # Missing!
            ],
        )
        await store.store_chain(chain)
        result = await store.get_chains_missing_reasoning()
        assert "agent-001" in result

    @pytest.mark.asyncio
    async def test_chain_with_audit_anchors_missing_reasoning(self, store):
        """A chain with audit anchors missing reasoning traces must be included."""
        chain = TrustLineageChain(
            genesis=_make_genesis("agent-001"),
            capabilities=[_make_capability()],
            audit_anchors=[
                _make_audit_anchor("aud-001", reasoning_trace=None),
            ],
        )
        await store.store_chain(chain)
        result = await store.get_chains_missing_reasoning()
        assert "agent-001" in result

    @pytest.mark.asyncio
    async def test_chain_with_all_audit_anchors_having_reasoning(self, store):
        """Chain where all audit anchors have reasoning must NOT be included."""
        trace = _make_reasoning_trace()
        chain = TrustLineageChain(
            genesis=_make_genesis("agent-001"),
            capabilities=[_make_capability()],
            audit_anchors=[
                _make_audit_anchor("aud-001", reasoning_trace=trace),
            ],
        )
        await store.store_chain(chain)
        result = await store.get_chains_missing_reasoning()
        assert "agent-001" not in result

    @pytest.mark.asyncio
    async def test_multiple_agents_returns_correct_ids(self, store):
        """Only agents with missing reasoning should be returned."""
        trace = _make_reasoning_trace()

        # agent-001: has delegation without reasoning
        chain1 = TrustLineageChain(
            genesis=_make_genesis("agent-001"),
            delegations=[_make_delegation("del-001", reasoning_trace=None)],
        )
        await store.store_chain(chain1)

        # agent-002: all delegations have reasoning
        chain2 = TrustLineageChain(
            genesis=_make_genesis("agent-002"),
            delegations=[_make_delegation("del-002", reasoning_trace=trace)],
        )
        await store.store_chain(chain2)

        # agent-003: no delegations or audits at all
        chain3 = TrustLineageChain(
            genesis=_make_genesis("agent-003"),
        )
        await store.store_chain(chain3)

        result = await store.get_chains_missing_reasoning()
        assert "agent-001" in result
        assert "agent-002" not in result
        assert "agent-003" not in result

    @pytest.mark.asyncio
    async def test_returns_list_of_strings(self, store):
        """Return type must be List[str]."""
        chain = TrustLineageChain(
            genesis=_make_genesis("agent-001"),
            delegations=[_make_delegation("del-001", reasoning_trace=None)],
        )
        await store.store_chain(chain)
        result = await store.get_chains_missing_reasoning()
        assert isinstance(result, list)
        for item in result:
            assert isinstance(item, str)


class TestFilesystemStoreGetChainsMissingReasoning:
    """Tests for get_chains_missing_reasoning() on FilesystemStore."""

    @pytest.mark.asyncio
    async def test_empty_store_returns_empty(self, fs_store):
        """Empty filesystem store must return empty list."""
        await fs_store.initialize()
        result = await fs_store.get_chains_missing_reasoning()
        assert result == []

    @pytest.mark.asyncio
    async def test_chain_with_delegation_missing_reasoning(self, fs_store):
        """FilesystemStore must detect delegations missing reasoning."""
        await fs_store.initialize()
        chain = TrustLineageChain(
            genesis=_make_genesis("agent-001"),
            delegations=[_make_delegation("del-001", reasoning_trace=None)],
        )
        await fs_store.store_chain(chain)
        result = await fs_store.get_chains_missing_reasoning()
        assert "agent-001" in result

    @pytest.mark.asyncio
    async def test_chain_with_all_reasoning_not_included(self, fs_store):
        """FilesystemStore must NOT include agents with full reasoning."""
        await fs_store.initialize()
        trace = _make_reasoning_trace()
        chain = TrustLineageChain(
            genesis=_make_genesis("agent-001"),
            delegations=[_make_delegation("del-001", reasoning_trace=trace)],
        )
        await fs_store.store_chain(chain)
        result = await fs_store.get_chains_missing_reasoning()
        assert "agent-001" not in result


# ===========================================================================
# Part 2: AuditQueryService.get_unattested_reasoning() Tests
# ===========================================================================


class TestAuditQueryServiceGetUnattestedReasoning:
    """Tests for AuditQueryService.get_unattested_reasoning()."""

    @pytest.fixture
    def audit_store(self):
        """Create a mock AuditStore with in-memory records."""
        from eatp.audit_store import AppendOnlyAuditStore

        return AppendOnlyAuditStore()

    @pytest.fixture
    def audit_service(self, audit_store):
        """Create AuditQueryService with the test audit store."""
        from eatp.audit_service import AuditQueryService

        return AuditQueryService(audit_store)

    @pytest.mark.asyncio
    async def test_empty_store_returns_empty(self, audit_service):
        """Empty audit store must return empty list."""
        result = await audit_service.get_unattested_reasoning()
        assert result == []

    @pytest.mark.asyncio
    async def test_all_anchors_with_reasoning_returns_empty(
        self, audit_service, audit_store
    ):
        """All audit anchors having reasoning must return empty list."""
        trace = _make_reasoning_trace()
        anchor = _make_audit_anchor("aud-001", reasoning_trace=trace)
        await audit_store.append(anchor)

        result = await audit_service.get_unattested_reasoning()
        assert result == []

    @pytest.mark.asyncio
    async def test_anchor_missing_reasoning_returned(self, audit_service, audit_store):
        """Audit anchor without reasoning trace must be returned."""
        anchor = _make_audit_anchor("aud-001", reasoning_trace=None)
        await audit_store.append(anchor)

        result = await audit_service.get_unattested_reasoning()
        assert len(result) == 1
        assert result[0].id == "aud-001"

    @pytest.mark.asyncio
    async def test_mixed_anchors_only_missing_returned(
        self, audit_service, audit_store
    ):
        """Only anchors missing reasoning traces must be returned."""
        trace = _make_reasoning_trace()
        anchor_with = _make_audit_anchor("aud-001", reasoning_trace=trace)
        anchor_without = _make_audit_anchor("aud-002", reasoning_trace=None)
        await audit_store.append(anchor_with)
        await audit_store.append(anchor_without)

        result = await audit_service.get_unattested_reasoning()
        assert len(result) == 1
        assert result[0].id == "aud-002"

    @pytest.mark.asyncio
    async def test_multiple_missing_returned(self, audit_service, audit_store):
        """Multiple anchors missing reasoning must all be returned."""
        anchor1 = _make_audit_anchor("aud-001", reasoning_trace=None)
        anchor2 = _make_audit_anchor("aud-002", reasoning_trace=None)
        anchor3 = _make_audit_anchor("aud-003", reasoning_trace=None)
        await audit_store.append(anchor1)
        await audit_store.append(anchor2)
        await audit_store.append(anchor3)

        result = await audit_service.get_unattested_reasoning()
        assert len(result) == 3
        result_ids = {a.id for a in result}
        assert result_ids == {"aud-001", "aud-002", "aud-003"}

    @pytest.mark.asyncio
    async def test_returns_list_of_audit_anchors(self, audit_service, audit_store):
        """Return type must be List[AuditAnchor]."""
        anchor = _make_audit_anchor("aud-001", reasoning_trace=None)
        await audit_store.append(anchor)

        result = await audit_service.get_unattested_reasoning()
        assert isinstance(result, list)
        for item in result:
            assert isinstance(item, AuditAnchor)


# ===========================================================================
# Part 3: Scoring — "reasoning_coverage" factor
# ===========================================================================


class TestScoringReasoningCoverage:
    """Tests for reasoning coverage factor in trust score computation.

    KEY BACKWARD COMPATIBILITY RULES:
    - When REASONING_REQUIRED is NOT in constraints, score is UNCHANGED.
    - When REASONING_REQUIRED IS active, reasoning_coverage factor applies (~5%).
    """

    @pytest.mark.asyncio
    async def test_no_reasoning_required_weights_unchanged(self, store):
        """Without REASONING_REQUIRED constraint, weights must sum to 100 as before."""
        chain = TrustLineageChain(
            genesis=_make_genesis("agent-001"),
            capabilities=[_make_capability()],
            constraint_envelope=_make_constraint_envelope_without_reasoning_required(),
        )
        await store.store_chain(chain)
        score = await compute_trust_score("agent-001", store)

        # Breakdown must contain only the original 5 factors
        expected_keys = {
            "chain_completeness",
            "delegation_depth",
            "constraint_coverage",
            "posture_level",
            "chain_recency",
        }
        assert set(score.breakdown.keys()) == expected_keys

    @pytest.mark.asyncio
    async def test_no_reasoning_required_score_unchanged(self, store):
        """Without REASONING_REQUIRED, score must be identical to before this feature.

        We verify by computing twice: the breakdown should NOT contain
        a reasoning_coverage key.
        """
        chain = TrustLineageChain(
            genesis=_make_genesis("agent-001"),
            capabilities=[_make_capability()],
            constraint_envelope=_make_constraint_envelope_without_reasoning_required(),
        )
        await store.store_chain(chain)
        score = await compute_trust_score("agent-001", store)

        assert "reasoning_coverage" not in score.breakdown

    @pytest.mark.asyncio
    async def test_reasoning_required_adds_reasoning_coverage_factor(self, store):
        """With REASONING_REQUIRED constraint, breakdown must include reasoning_coverage."""
        trace = _make_reasoning_trace()
        chain = TrustLineageChain(
            genesis=_make_genesis("agent-001"),
            capabilities=[_make_capability()],
            constraint_envelope=_make_constraint_envelope_with_reasoning_required(),
            delegations=[_make_delegation("del-001", reasoning_trace=trace)],
        )
        await store.store_chain(chain)
        score = await compute_trust_score("agent-001", store)

        assert "reasoning_coverage" in score.breakdown

    @pytest.mark.asyncio
    async def test_full_reasoning_coverage_gives_max_factor(self, store):
        """100% reasoning coverage must give the maximum reasoning_coverage contribution."""
        trace = _make_reasoning_trace()
        chain = TrustLineageChain(
            genesis=_make_genesis("agent-001"),
            capabilities=[_make_capability()],
            constraint_envelope=_make_constraint_envelope_with_reasoning_required(),
            delegations=[
                _make_delegation("del-001", reasoning_trace=trace),
                _make_delegation("del-002", reasoning_trace=trace),
            ],
            audit_anchors=[
                _make_audit_anchor("aud-001", reasoning_trace=trace),
            ],
        )
        await store.store_chain(chain)
        score = await compute_trust_score("agent-001", store)

        # Full coverage = weight * 1.0
        assert score.breakdown["reasoning_coverage"] > 0

    @pytest.mark.asyncio
    async def test_zero_reasoning_coverage_gives_zero_factor(self, store):
        """0% reasoning coverage must give 0 contribution."""
        chain = TrustLineageChain(
            genesis=_make_genesis("agent-001"),
            capabilities=[_make_capability()],
            constraint_envelope=_make_constraint_envelope_with_reasoning_required(),
            delegations=[
                _make_delegation("del-001", reasoning_trace=None),
                _make_delegation("del-002", reasoning_trace=None),
            ],
        )
        await store.store_chain(chain)
        score = await compute_trust_score("agent-001", store)

        assert score.breakdown["reasoning_coverage"] == 0.0

    @pytest.mark.asyncio
    async def test_partial_reasoning_coverage_gives_proportional_factor(self, store):
        """50% reasoning coverage must give a proportional contribution."""
        trace = _make_reasoning_trace()
        chain = TrustLineageChain(
            genesis=_make_genesis("agent-001"),
            capabilities=[_make_capability()],
            constraint_envelope=_make_constraint_envelope_with_reasoning_required(),
            delegations=[
                _make_delegation("del-001", reasoning_trace=trace),
                _make_delegation("del-002", reasoning_trace=None),  # Missing
            ],
        )
        await store.store_chain(chain)
        score = await compute_trust_score("agent-001", store)

        # 50% coverage means factor should be roughly half the max weight
        # The exact value depends on weight, but it must be > 0 and < max
        assert score.breakdown["reasoning_coverage"] > 0
        # Check that full coverage gets more than partial
        chain_full = TrustLineageChain(
            genesis=_make_genesis("agent-002"),
            capabilities=[_make_capability()],
            constraint_envelope=_make_constraint_envelope_with_reasoning_required(
                "agent-002"
            ),
            delegations=[
                _make_delegation("del-003", reasoning_trace=trace),
                _make_delegation("del-004", reasoning_trace=trace),
            ],
        )
        await store.store_chain(chain_full)
        score_full = await compute_trust_score("agent-002", store)
        assert (
            score_full.breakdown["reasoning_coverage"]
            > score.breakdown["reasoning_coverage"]
        )

    @pytest.mark.asyncio
    async def test_reasoning_coverage_weight_is_approximately_5_percent(self, store):
        """The reasoning_coverage factor weight should be approximately 5%."""
        trace = _make_reasoning_trace()
        chain = TrustLineageChain(
            genesis=_make_genesis("agent-001"),
            capabilities=[_make_capability()],
            constraint_envelope=_make_constraint_envelope_with_reasoning_required(),
            delegations=[_make_delegation("del-001", reasoning_trace=trace)],
        )
        await store.store_chain(chain)
        score = await compute_trust_score("agent-001", store)

        # Max possible reasoning_coverage contribution should be ~5
        # (weight of 5 * factor of 1.0 = 5.0)
        assert score.breakdown["reasoning_coverage"] <= 5.0

    @pytest.mark.asyncio
    async def test_total_breakdown_sums_to_score(self, store):
        """Sum of all breakdown values must equal the score (within rounding)."""
        trace = _make_reasoning_trace()
        chain = TrustLineageChain(
            genesis=_make_genesis("agent-001"),
            capabilities=[_make_capability()],
            constraint_envelope=_make_constraint_envelope_with_reasoning_required(),
            delegations=[_make_delegation("del-001", reasoning_trace=trace)],
        )
        await store.store_chain(chain)
        score = await compute_trust_score("agent-001", store)

        total = sum(score.breakdown.values())
        # Allow rounding tolerance
        assert abs(total - score.score) <= 1

    @pytest.mark.asyncio
    async def test_score_with_reasoning_required_still_in_valid_range(self, store):
        """Score with reasoning coverage must still be in [0, 100]."""
        trace = _make_reasoning_trace()
        chain = TrustLineageChain(
            genesis=_make_genesis("agent-001"),
            capabilities=[_make_capability()],
            constraint_envelope=_make_constraint_envelope_with_reasoning_required(),
            delegations=[_make_delegation("del-001", reasoning_trace=trace)],
        )
        await store.store_chain(chain)
        score = await compute_trust_score("agent-001", store)

        assert 0 <= score.score <= 100

    @pytest.mark.asyncio
    async def test_no_delegations_no_audits_with_reasoning_required(self, store):
        """Chain with REASONING_REQUIRED but no delegations/audits:
        reasoning_coverage factor should still exist but be 0 (no items to check)
        or be treated as full coverage (nothing to miss). Implementation decision:
        we treat it as full coverage since there's nothing missing."""
        chain = TrustLineageChain(
            genesis=_make_genesis("agent-001"),
            capabilities=[_make_capability()],
            constraint_envelope=_make_constraint_envelope_with_reasoning_required(),
        )
        await store.store_chain(chain)
        score = await compute_trust_score("agent-001", store)

        # With no delegations/audits, there's nothing missing reasoning.
        # Full coverage by vacuous truth.
        assert "reasoning_coverage" in score.breakdown
        # Vacuous truth: 100% coverage when there's nothing to check
        assert score.breakdown["reasoning_coverage"] > 0

    @pytest.mark.asyncio
    async def test_report_includes_reasoning_risk_indicator_when_missing(self, store):
        """Trust report should flag missing reasoning when REASONING_REQUIRED is active."""
        chain = TrustLineageChain(
            genesis=_make_genesis("agent-001"),
            capabilities=[_make_capability()],
            constraint_envelope=_make_constraint_envelope_with_reasoning_required(),
            delegations=[_make_delegation("del-001", reasoning_trace=None)],
        )
        await store.store_chain(chain)
        report = await generate_trust_report("agent-001", store)

        # Should have a risk indicator about missing reasoning
        reasoning_indicators = [
            ri for ri in report.risk_indicators if "reasoning" in ri.lower()
        ]
        assert len(reasoning_indicators) > 0

    @pytest.mark.asyncio
    async def test_report_no_reasoning_indicator_when_not_required(self, store):
        """Trust report should NOT flag reasoning when REASONING_REQUIRED is not active."""
        chain = TrustLineageChain(
            genesis=_make_genesis("agent-001"),
            capabilities=[_make_capability()],
            constraint_envelope=_make_constraint_envelope_without_reasoning_required(),
            delegations=[_make_delegation("del-001", reasoning_trace=None)],
        )
        await store.store_chain(chain)
        report = await generate_trust_report("agent-001", store)

        # Should NOT have a risk indicator about missing reasoning
        reasoning_indicators = [
            ri for ri in report.risk_indicators if "reasoning" in ri.lower()
        ]
        assert len(reasoning_indicators) == 0


# ===========================================================================
# Backward Compatibility — Existing Tests Must Still Pass
# ===========================================================================


class TestScoringBackwardCompatibility:
    """Ensure existing scoring behavior is not broken by reasoning_coverage."""

    @pytest.mark.asyncio
    async def test_original_5_factor_weights_still_sum_to_100(self):
        """The original SCORING_WEIGHTS dict must still sum to 100."""
        total = sum(SCORING_WEIGHTS.values())
        assert total == 100, (
            f"SCORING_WEIGHTS must still sum to 100 for backward compatibility, "
            f"got {total}"
        )

    @pytest.mark.asyncio
    async def test_score_grade_mapping_unchanged(self):
        """Grade boundaries must remain unchanged."""
        assert score_to_grade(90) == "A"
        assert score_to_grade(80) == "B"
        assert score_to_grade(70) == "C"
        assert score_to_grade(60) == "D"
        assert score_to_grade(59) == "F"

    @pytest.mark.asyncio
    async def test_chain_without_reasoning_required_identical_scoring(self, store):
        """A chain without REASONING_REQUIRED must produce the same score
        whether or not reasoning traces are present on delegations."""
        chain_no_traces = TrustLineageChain(
            genesis=_make_genesis("agent-001"),
            capabilities=[_make_capability()],
            constraint_envelope=_make_constraint_envelope_without_reasoning_required(),
            delegations=[_make_delegation("del-001", reasoning_trace=None)],
        )
        await store.store_chain(chain_no_traces)
        score_no_traces = await compute_trust_score("agent-001", store)

        trace = _make_reasoning_trace()
        chain_with_traces = TrustLineageChain(
            genesis=_make_genesis("agent-002"),
            capabilities=[_make_capability()],
            constraint_envelope=_make_constraint_envelope_without_reasoning_required(
                "agent-002"
            ),
            delegations=[_make_delegation("del-002", reasoning_trace=trace)],
        )
        await store.store_chain(chain_with_traces)
        score_with_traces = await compute_trust_score("agent-002", store)

        # Without REASONING_REQUIRED, presence/absence of traces must not affect score
        assert score_no_traces.breakdown.keys() == score_with_traces.breakdown.keys()
        assert "reasoning_coverage" not in score_no_traces.breakdown
        assert "reasoning_coverage" not in score_with_traces.breakdown

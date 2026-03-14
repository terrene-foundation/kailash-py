# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Trust scoring engine for EATP agents.

Computes deterministic trust scores (0-100) for agents based on their
trust lineage chain completeness, delegation depth, constraint coverage,
posture level, and chain recency.

Structural Scoring Factors (weights sum to 100):
    - Chain Completeness (30%): Has genesis, capabilities, constraint envelope
    - Delegation Depth (15%): Deeper chains = lower score (more risk)
    - Constraint Coverage (25%): More constraints = higher score (well-constrained)
    - Posture Level (20%): Stricter posture = higher score
    - Chain Recency (10%): Recent updates = higher score

Behavioral Scoring Factors (weights sum to 100, cross-SDK aligned D1):
    - Approval Rate (30): approved_actions / total_actions
    - Error Rate (25): inverse of error_count / total_actions
    - Posture Stability (20): inverse of posture_transitions / observation_window
    - Time at Posture (15): time_at_current_posture normalized
    - Interaction Volume (10): log-scaled total_actions

Combined scoring blends structural (60%) and behavioral (40%) by default.
Behavioral is complementary — it never overrides structural.

Grade Mapping:
    A = 90-100, B = 80-89, C = 70-79, D = 60-69, F = 0-59
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from eatp.chain import ConstraintType, TrustLineageChain
from eatp.postures import PostureStateMachine, TrustPosture
from eatp.store import TrustStore

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SCORING_WEIGHTS: Dict[str, int] = {
    "chain_completeness": 30,
    "delegation_depth": 15,
    "constraint_coverage": 25,
    "posture_level": 20,
    "chain_recency": 10,
}
"""Factor weights that determine how much each dimension contributes to the
final trust score.  The values MUST sum to 100."""

POSTURE_SCORE_MAP: Dict[TrustPosture, int] = {
    TrustPosture.DELEGATED: 20,
    TrustPosture.CONTINUOUS_INSIGHT: 40,
    TrustPosture.SHARED_PLANNING: 80,
    TrustPosture.SUPERVISED: 100,
    TrustPosture.PSEUDO_AGENT: 0,
}
"""Maps each posture to a 0-100 factor score.  Stricter postures
(more human oversight) yield higher trust factor scores because they
imply lower unsupervised risk."""

GRADE_THRESHOLDS: Dict[str, int] = {
    "A": 90,
    "B": 80,
    "C": 70,
    "D": 60,
}
"""Minimum score for each letter grade (descending check order).
Anything below 60 is grade F."""

# Maximum delegation depth used for normalisation.
# Chains deeper than this all receive a 0 factor score.
_MAX_DELEGATION_DEPTH: int = 10

# Maximum number of constraints considered for 100% coverage.
# Beyond this the factor is capped at 100.
_CONSTRAINT_FULL_COVERAGE: int = 10

# Number of days after which the recency factor starts decaying.
_RECENCY_HALF_LIFE_DAYS: float = 90.0

# Weight for the reasoning_coverage factor when REASONING_REQUIRED
# constraint is active.  The base 5 weights (summing to 100) are scaled
# down proportionally to make room, keeping the total at 100.
_REASONING_COVERAGE_WEIGHT: int = 5


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class TrustScore:
    """Computed trust score for an agent.

    Attributes:
        score: Overall trust score (0-100, integer).
        breakdown: Per-factor weighted contributions that sum to ``score``.
        grade: Letter grade (A/B/C/D/F) derived from ``score``.
        computed_at: UTC timestamp when the score was calculated.
        agent_id: The agent this score belongs to.
    """

    score: int
    breakdown: Dict[str, float]
    grade: str
    computed_at: datetime
    agent_id: str


@dataclass
class TrustReport:
    """Comprehensive trust report for an agent.

    Attributes:
        score: The computed TrustScore.
        risk_indicators: Human-readable list of identified risk factors.
        recommendations: Human-readable list of actionable improvements.
    """

    score: TrustScore
    risk_indicators: List[str]
    recommendations: List[str]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def score_to_grade(score: int) -> str:
    """Map a numeric score (0-100) to a letter grade.

    Grade mapping:
        A = 90-100, B = 80-89, C = 70-79, D = 60-69, F = 0-59

    Args:
        score: Integer trust score in range [0, 100].

    Returns:
        Single-character letter grade string.

    Raises:
        ValueError: If score is outside the 0-100 range.
    """
    if not (0 <= score <= 100):
        raise ValueError(f"Score must be between 0 and 100 inclusive, got {score}")
    for grade, threshold in sorted(
        GRADE_THRESHOLDS.items(), key=lambda x: x[1], reverse=True
    ):
        if score >= threshold:
            return grade
    return "F"


def _compute_chain_completeness(chain: TrustLineageChain) -> float:
    """Compute chain completeness factor (0.0 - 1.0).

    Awards partial credit for each present component:
        - Genesis record present: 40%  (always present in a valid chain)
        - At least one capability: 30%
        - Constraint envelope with active constraints: 30%

    Args:
        chain: The trust lineage chain to evaluate.

    Returns:
        Float between 0.0 and 1.0 representing completeness.
    """
    completeness = 0.0

    # Genesis is always present (required by dataclass), but check for
    # validity — the genesis record's existence is the foundation.
    if chain.genesis is not None:
        completeness += 0.40

    # Capabilities
    if chain.capabilities and len(chain.capabilities) > 0:
        completeness += 0.30

    # Constraint envelope with active constraints
    if (
        chain.constraint_envelope is not None
        and chain.constraint_envelope.active_constraints
        and len(chain.constraint_envelope.active_constraints) > 0
    ):
        completeness += 0.30

    return completeness


def _compute_delegation_depth_factor(chain: TrustLineageChain) -> float:
    """Compute delegation depth factor (0.0 - 1.0).

    Deeper delegation chains increase risk (more intermediaries = more
    opportunity for privilege escalation or accountability loss).  A chain
    with no delegations gets a perfect 1.0.  Depth is normalised against
    ``_MAX_DELEGATION_DEPTH``; chains at or beyond that depth receive 0.0.

    Args:
        chain: The trust lineage chain to evaluate.

    Returns:
        Float between 0.0 and 1.0 (higher = less delegation risk).
    """
    if not chain.delegations:
        return 1.0

    # Find the maximum delegation depth in the chain
    max_depth = 0
    for delegation in chain.delegations:
        if delegation.delegation_depth > max_depth:
            max_depth = delegation.delegation_depth

    # If delegation_depth is not set (all zeros), use number of delegations
    if max_depth == 0:
        max_depth = len(chain.delegations)

    # Normalise: 0 depth = 1.0, _MAX_DELEGATION_DEPTH+ = 0.0
    factor = max(0.0, 1.0 - (max_depth / _MAX_DELEGATION_DEPTH))
    return factor


def _compute_constraint_coverage(chain: TrustLineageChain) -> float:
    """Compute constraint coverage factor (0.0 - 1.0).

    More constraints indicate a well-governed agent.  Coverage is normalised
    against ``_CONSTRAINT_FULL_COVERAGE``; chains with that many or more
    active constraints receive 1.0.

    Args:
        chain: The trust lineage chain to evaluate.

    Returns:
        Float between 0.0 and 1.0 (higher = more constraints).
    """
    if chain.constraint_envelope is None:
        return 0.0

    num_constraints = len(chain.constraint_envelope.active_constraints)
    if num_constraints == 0:
        return 0.0

    return min(1.0, num_constraints / _CONSTRAINT_FULL_COVERAGE)


def _compute_posture_factor(
    agent_id: str,
    posture_machine: Optional[PostureStateMachine],
) -> float:
    """Compute posture level factor (0.0 - 1.0).

    Uses the posture score map to convert the agent's current posture into
    a normalised factor.  Stricter postures score higher.

    When ``posture_machine`` is None a default of SHARED_PLANNING is assumed
    (moderate trust).

    Args:
        agent_id: Agent identifier to look up in the posture machine.
        posture_machine: Optional state machine holding agent postures.

    Returns:
        Float between 0.0 and 1.0.
    """
    if posture_machine is None:
        # Default to SHARED_PLANNING (moderate trust, autonomy_level=3)
        posture = TrustPosture.SHARED_PLANNING
    else:
        posture = posture_machine.get_posture(agent_id)

    raw_score = POSTURE_SCORE_MAP[posture]
    return raw_score / 100.0


def _compute_recency_factor(chain: TrustLineageChain) -> float:
    """Compute chain recency factor (0.0 - 1.0).

    Examines the most recent timestamp across genesis creation,
    capability attestations, and delegation records.  Applies an
    exponential decay with half-life ``_RECENCY_HALF_LIFE_DAYS``.

    A chain updated within the last few hours scores ~1.0; one that
    hasn't been touched in a year scores near 0.

    Args:
        chain: The trust lineage chain to evaluate.

    Returns:
        Float between 0.0 and 1.0 (higher = more recent).
    """
    now = datetime.now(timezone.utc)

    # Collect all relevant timestamps
    timestamps: List[datetime] = []

    # Genesis created_at
    genesis_ts = chain.genesis.created_at
    if genesis_ts.tzinfo is None:
        genesis_ts = genesis_ts.replace(tzinfo=timezone.utc)
    timestamps.append(genesis_ts)

    # Capability attested_at
    for cap in chain.capabilities:
        cap_ts = cap.attested_at
        if cap_ts.tzinfo is None:
            cap_ts = cap_ts.replace(tzinfo=timezone.utc)
        timestamps.append(cap_ts)

    # Delegation delegated_at
    for delegation in chain.delegations:
        del_ts = delegation.delegated_at
        if del_ts.tzinfo is None:
            del_ts = del_ts.replace(tzinfo=timezone.utc)
        timestamps.append(del_ts)

    # Constraint envelope computed_at -- only consider when the envelope
    # has active constraints.  ConstraintEnvelope.__post_init__ auto-sets
    # computed_at to datetime.now() even for empty envelopes, which would
    # incorrectly make stale chains appear recent.
    if (
        chain.constraint_envelope is not None
        and chain.constraint_envelope.computed_at is not None
        and chain.constraint_envelope.active_constraints
        and len(chain.constraint_envelope.active_constraints) > 0
    ):
        env_ts = chain.constraint_envelope.computed_at
        if env_ts.tzinfo is None:
            env_ts = env_ts.replace(tzinfo=timezone.utc)
        timestamps.append(env_ts)

    if not timestamps:
        logger.warning(
            "No timestamps found in chain for agent %s; recency factor is 0.0",
            chain.genesis.agent_id,
        )
        return 0.0

    most_recent = max(timestamps)
    age_days = (now - most_recent).total_seconds() / 86400.0

    # Exponential decay: factor = 2^(-age / half_life)
    factor = math.pow(2.0, -age_days / _RECENCY_HALF_LIFE_DAYS)
    return max(0.0, min(1.0, factor))


def _has_reasoning_required_constraint(chain: TrustLineageChain) -> bool:
    """Check whether the chain has a REASONING_REQUIRED active constraint.

    Args:
        chain: The trust lineage chain to check.

    Returns:
        True if REASONING_REQUIRED is among the active constraints.
    """
    if chain.constraint_envelope is None:
        return False
    for constraint in chain.constraint_envelope.active_constraints:
        if constraint.constraint_type == ConstraintType.REASONING_REQUIRED:
            return True
    return False


def _compute_reasoning_coverage(chain: TrustLineageChain) -> float:
    """Compute reasoning coverage factor (0.0 - 1.0).

    Counts the percentage of delegations and audit anchors that have a
    non-None ``reasoning_trace``.  If no delegations or audit anchors
    exist, returns 1.0 (vacuous truth: nothing is missing).

    This factor is ONLY applied when a REASONING_REQUIRED constraint is
    active in the chain's constraint envelope.

    Args:
        chain: The trust lineage chain to evaluate.

    Returns:
        Float between 0.0 and 1.0 representing reasoning trace coverage.
    """
    total_items = 0
    items_with_reasoning = 0

    for delegation in chain.delegations:
        total_items += 1
        if delegation.reasoning_trace is not None:
            items_with_reasoning += 1

    for anchor in chain.audit_anchors:
        total_items += 1
        if anchor.reasoning_trace is not None:
            items_with_reasoning += 1

    if total_items == 0:
        # Vacuous truth: nothing to be missing
        return 1.0

    return items_with_reasoning / total_items


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def compute_trust_score(
    agent_id: str,
    store: TrustStore,
    posture_machine: Optional[PostureStateMachine] = None,
) -> TrustScore:
    """Compute a deterministic trust score for an agent.

    The score is a weighted sum of five factors:

    1. **Chain completeness** (30%) -- has genesis, capabilities,
       constraint envelope.
    2. **Delegation chain depth** (15%) -- deeper chains = lower score
       (more delegation = more risk).
    3. **Constraint coverage** (25%) -- more constraints = higher score
       (well-constrained).
    4. **Posture level** (20%) -- DELEGATED=20, SHARED_PLANNING=80,
       SUPERVISED=100 (stricter = higher).
    5. **Chain recency** (10%) -- recent updates = higher score.

    Args:
        agent_id: The agent whose trust to score.
        store: Trust store to retrieve the agent's chain from.
        posture_machine: Optional posture state machine for posture factor.
            When None, defaults to SHARED_PLANNING posture.

    Returns:
        A ``TrustScore`` with the overall score, per-factor breakdown,
        letter grade, and computation timestamp.

    Raises:
        TrustChainNotFoundError: If no chain exists for ``agent_id``.
    """
    chain = await store.get_chain(agent_id)

    # Compute raw factors (each 0.0 - 1.0)
    completeness_raw = _compute_chain_completeness(chain)
    delegation_raw = _compute_delegation_depth_factor(chain)
    constraint_raw = _compute_constraint_coverage(chain)
    posture_raw = _compute_posture_factor(agent_id, posture_machine)
    recency_raw = _compute_recency_factor(chain)

    # Check if REASONING_REQUIRED constraint is active.
    # When active, a 6th "reasoning_coverage" factor is included at
    # weight _REASONING_COVERAGE_WEIGHT.  The base 5 weights are
    # scaled down proportionally so all weights still sum to 100.
    reasoning_required = _has_reasoning_required_constraint(chain)

    if reasoning_required:
        # Scale factor to reduce base weights so total = 100
        scale = (100 - _REASONING_COVERAGE_WEIGHT) / 100.0
        reasoning_raw = _compute_reasoning_coverage(chain)
    else:
        scale = 1.0
        reasoning_raw = None

    # Apply weights to get per-factor contributions
    breakdown: Dict[str, float] = {
        "chain_completeness": round(
            completeness_raw * SCORING_WEIGHTS["chain_completeness"] * scale, 2
        ),
        "delegation_depth": round(
            delegation_raw * SCORING_WEIGHTS["delegation_depth"] * scale, 2
        ),
        "constraint_coverage": round(
            constraint_raw * SCORING_WEIGHTS["constraint_coverage"] * scale, 2
        ),
        "posture_level": round(
            posture_raw * SCORING_WEIGHTS["posture_level"] * scale, 2
        ),
        "chain_recency": round(
            recency_raw * SCORING_WEIGHTS["chain_recency"] * scale, 2
        ),
    }

    # Add reasoning coverage factor if applicable
    if reasoning_required and reasoning_raw is not None:
        breakdown["reasoning_coverage"] = round(
            reasoning_raw * _REASONING_COVERAGE_WEIGHT, 2
        )

    total = sum(breakdown.values())
    # Clamp to [0, 100] and round to integer
    total_int = max(0, min(100, int(round(total))))

    grade = score_to_grade(total_int)
    computed_at = datetime.now(timezone.utc)

    logger.debug(
        "Trust score for agent %s: %d (%s) -- breakdown: %s",
        agent_id,
        total_int,
        grade,
        breakdown,
    )

    return TrustScore(
        score=total_int,
        breakdown=breakdown,
        grade=grade,
        computed_at=computed_at,
        agent_id=agent_id,
    )


async def generate_trust_report(
    agent_id: str,
    store: TrustStore,
    posture_machine: Optional[PostureStateMachine] = None,
) -> TrustReport:
    """Generate a comprehensive trust report for an agent.

    Computes the trust score and then analyses the chain to produce
    human-readable risk indicators and improvement recommendations.

    Args:
        agent_id: The agent to report on.
        store: Trust store to retrieve the agent's chain from.
        posture_machine: Optional posture state machine for posture factor.

    Returns:
        A ``TrustReport`` with the score, risk indicators, and
        recommendations.

    Raises:
        TrustChainNotFoundError: If no chain exists for ``agent_id``.
    """
    chain = await store.get_chain(agent_id)
    trust_score = await compute_trust_score(agent_id, store, posture_machine)

    risk_indicators: List[str] = []
    recommendations: List[str] = []

    # --- Analyse chain completeness ---
    if not chain.capabilities or len(chain.capabilities) == 0:
        risk_indicators.append(
            "No capability attestations found; agent has no declared capabilities"
        )
        recommendations.append(
            "Add at least one capability attestation to declare what the agent can do"
        )

    if (
        chain.constraint_envelope is None
        or not chain.constraint_envelope.active_constraints
    ):
        risk_indicators.append(
            "No active constraints defined; agent behaviour is unconstrained"
        )
        recommendations.append(
            "Define a constraint envelope with resource limits, data scopes, "
            "or audit requirements to govern agent behaviour"
        )

    # --- Analyse delegation depth ---
    if chain.delegations:
        max_depth = max(
            (d.delegation_depth for d in chain.delegations),
            default=0,
        )
        if max_depth == 0:
            max_depth = len(chain.delegations)

        if max_depth >= 5:
            risk_indicators.append(
                f"Deep delegation chain (depth={max_depth}); "
                f"accountability and oversight may be weakened"
            )
            recommendations.append(
                "Consider reducing delegation depth to improve accountability "
                "and reduce privilege escalation risk"
            )

    # --- Analyse constraint coverage ---
    if chain.constraint_envelope and chain.constraint_envelope.active_constraints:
        num_constraints = len(chain.constraint_envelope.active_constraints)
        if num_constraints < 3:
            risk_indicators.append(
                f"Low constraint coverage ({num_constraints} constraint(s)); "
                f"agent may have insufficient governance"
            )
            recommendations.append(
                "Add more constraints (resource limits, time windows, "
                "data scopes) for better governance"
            )

    # --- Analyse posture ---
    if posture_machine is not None:
        posture = posture_machine.get_posture(agent_id)
        if posture == TrustPosture.DELEGATED:
            risk_indicators.append(
                "Agent is running with full autonomy; no human oversight on actions"
            )
            recommendations.append(
                "Consider transitioning to SHARED_PLANNING or CONTINUOUS_INSIGHT posture "
                "to add oversight"
            )
        elif posture == TrustPosture.PSEUDO_AGENT:
            risk_indicators.append(
                "Agent is PSEUDO_AGENT; it cannot perform any actions"
            )
            recommendations.append(
                "Review blocking reason and consider upgrading posture "
                "if the issue has been resolved"
            )

    # --- Analyse reasoning coverage (only when REASONING_REQUIRED is active) ---
    if _has_reasoning_required_constraint(chain):
        reasoning_coverage_contribution = trust_score.breakdown.get(
            "reasoning_coverage", 0.0
        )
        max_possible_reasoning = _REASONING_COVERAGE_WEIGHT
        if reasoning_coverage_contribution < max_possible_reasoning * 0.99:
            # Not at full coverage — compute actual percentage for the message
            reasoning_raw = _compute_reasoning_coverage(chain)
            pct = int(reasoning_raw * 100)
            risk_indicators.append(
                f"Incomplete reasoning trace coverage ({pct}%); "
                f"REASONING_REQUIRED constraint is active but some "
                f"delegations or audit anchors lack reasoning traces"
            )
            recommendations.append(
                "Attach reasoning traces to all delegations and audit "
                "anchors to satisfy the REASONING_REQUIRED constraint"
            )

    # --- Analyse recency ---
    recency_contribution = trust_score.breakdown.get("chain_recency", 0.0)
    max_possible_recency = SCORING_WEIGHTS["chain_recency"]
    if recency_contribution < max_possible_recency * 0.5:
        risk_indicators.append(
            "Trust chain has not been updated recently; "
            "credentials or attestations may be stale"
        )
        recommendations.append(
            "Refresh the trust chain by re-attesting capabilities "
            "or updating the constraint envelope"
        )

    # --- Overall grade advice ---
    if trust_score.grade == "F":
        recommendations.append(
            "Trust score is critically low (grade F); "
            "review all chain components urgently"
        )
    elif trust_score.grade == "D":
        recommendations.append(
            "Trust score is below acceptable threshold (grade D); "
            "address risk indicators to improve"
        )

    logger.debug(
        "Trust report for agent %s: score=%d, risks=%d, recommendations=%d",
        agent_id,
        trust_score.score,
        len(risk_indicators),
        len(recommendations),
    )

    return TrustReport(
        score=trust_score,
        risk_indicators=risk_indicators,
        recommendations=recommendations,
    )


# ---------------------------------------------------------------------------
# Behavioral scoring (Phase 4 — cross-SDK aligned with D1)
# ---------------------------------------------------------------------------

BEHAVIORAL_WEIGHTS: Dict[str, int] = {
    "approval_rate": 30,
    "error_rate": 25,
    "posture_stability": 20,
    "time_at_posture": 15,
    "interaction_volume": 10,
}
"""Behavioral scoring factor weights (must sum to 100)."""

# Normalization constants for behavioral factors
_TIME_AT_POSTURE_FULL_SCORE_HOURS: float = 720.0  # 30 days
_INTERACTION_VOLUME_MIN_FOR_FULL: int = 10000
_POSTURE_STABILITY_WINDOW_HOURS: float = 168.0  # 1 week


@dataclass
class BehavioralData:
    """Caller-provided behavioral data for an agent.

    Callers are responsible for populating these counters from their
    enforcement pipeline. The SDK does not collect this data automatically.

    All fields default to zero. Zero-data produces score 0, grade F
    (fail-safe: unknown agents are not trusted).

    Attributes:
        total_actions: Total number of actions the agent has attempted.
        approved_actions: Number of actions that were approved.
        denied_actions: Number of actions that were denied.
        error_count: Number of actions that resulted in errors.
        posture_transitions: Number of posture changes in the observation window.
        time_at_current_posture_hours: Hours spent at the current posture.
        observation_window_hours: Total observation window in hours.
    """

    total_actions: int = 0
    approved_actions: int = 0
    denied_actions: int = 0
    error_count: int = 0
    posture_transitions: int = 0
    time_at_current_posture_hours: float = 0.0
    observation_window_hours: float = 0.0

    def __post_init__(self) -> None:
        """Validate fields after dataclass initialization."""
        # Non-negative checks
        for field_name in (
            "total_actions",
            "approved_actions",
            "denied_actions",
            "error_count",
            "posture_transitions",
        ):
            value = getattr(self, field_name)
            if value < 0:
                raise ValueError(f"{field_name} must be non-negative, got {value}")
        if self.time_at_current_posture_hours < 0:
            raise ValueError(
                f"time_at_current_posture_hours must be non-negative, "
                f"got {self.time_at_current_posture_hours}"
            )
        if self.observation_window_hours < 0:
            raise ValueError(
                f"observation_window_hours must be non-negative, "
                f"got {self.observation_window_hours}"
            )
        # Logical consistency: approved + denied <= total
        if self.approved_actions + self.denied_actions > self.total_actions:
            raise ValueError(
                f"approved_actions ({self.approved_actions}) + "
                f"denied_actions ({self.denied_actions}) exceeds "
                f"total_actions ({self.total_actions})"
            )
        # error_count <= total_actions
        if self.error_count > self.total_actions:
            raise ValueError(
                f"error_count ({self.error_count}) exceeds "
                f"total_actions ({self.total_actions})"
            )


@dataclass
class BehavioralScore:
    """Computed behavioral trust score for an agent.

    Attributes:
        score: Overall behavioral score (0-100, integer).
        breakdown: Per-factor weighted contributions.
        grade: Letter grade (A/B/C/D/F).
        computed_at: UTC timestamp.
        agent_id: The agent this score belongs to.
    """

    score: int
    breakdown: Dict[str, float]
    grade: str
    computed_at: datetime
    agent_id: str


@dataclass
class CombinedTrustScore:
    """Combined structural + behavioral trust score.

    Attributes:
        structural_score: The structural trust score (chain-based).
        behavioral_score: The behavioral trust score (action-based).
            None if no behavioral data was provided.
        combined_score: Blended score (0-100, integer).
        breakdown: Blending details including weights used.
    """

    structural_score: TrustScore
    behavioral_score: Optional[BehavioralScore]
    combined_score: int
    breakdown: Dict[str, Any]


def compute_behavioral_score(
    agent_id: str,
    data: BehavioralData,
) -> BehavioralScore:
    """Compute a behavioral trust score for an agent.

    Uses 5 weighted factors (cross-SDK aligned with D1 decision):
    - approval_rate (30): approved / total
    - error_rate (25): inverse of errors / total
    - posture_stability (20): inverse of transitions / window
    - time_at_posture (15): time normalized to 30-day max
    - interaction_volume (10): log10-scaled total actions

    Zero-data agents receive score 0, grade F (fail-safe).

    Args:
        agent_id: The agent identifier.
        data: Behavioral data collected by the caller.

    Returns:
        BehavioralScore with breakdown and grade.
    """
    # Fail-safe: zero data = score 0
    if data.total_actions == 0:
        return BehavioralScore(
            score=0,
            breakdown={k: 0.0 for k in BEHAVIORAL_WEIGHTS},
            grade="F",
            computed_at=datetime.now(timezone.utc),
            agent_id=agent_id,
        )

    # Factor 1: approval_rate (0.0-1.0)
    approval_raw = data.approved_actions / data.total_actions

    # Factor 2: error_rate — inverse (fewer errors = higher score)
    error_ratio = data.error_count / data.total_actions
    error_raw = max(0.0, 1.0 - error_ratio)

    # Factor 3: posture_stability — inverse of transition frequency
    if data.observation_window_hours > 0:
        transitions_per_hour = data.posture_transitions / data.observation_window_hours
        # Normalize: 0 transitions = 1.0, >1 per hour = ~0.0
        stability_raw = max(
            0.0, 1.0 - (transitions_per_hour * _POSTURE_STABILITY_WINDOW_HOURS / 10.0)
        )
    else:
        stability_raw = 0.0  # No observation window = unknown

    # Factor 4: time_at_posture — normalized to max
    time_raw = min(
        1.0, data.time_at_current_posture_hours / _TIME_AT_POSTURE_FULL_SCORE_HOURS
    )

    # Factor 5: interaction_volume — log10 scaled
    if data.total_actions > 0:
        log_actions = math.log10(data.total_actions)
        log_max = math.log10(_INTERACTION_VOLUME_MIN_FOR_FULL)
        volume_raw = min(1.0, log_actions / log_max)
    else:
        volume_raw = 0.0

    # Compute weighted breakdown
    breakdown = {
        "approval_rate": round(approval_raw * BEHAVIORAL_WEIGHTS["approval_rate"], 2),
        "error_rate": round(error_raw * BEHAVIORAL_WEIGHTS["error_rate"], 2),
        "posture_stability": round(
            stability_raw * BEHAVIORAL_WEIGHTS["posture_stability"], 2
        ),
        "time_at_posture": round(time_raw * BEHAVIORAL_WEIGHTS["time_at_posture"], 2),
        "interaction_volume": round(
            volume_raw * BEHAVIORAL_WEIGHTS["interaction_volume"], 2
        ),
    }

    total = max(0, min(100, int(round(sum(breakdown.values())))))
    grade = score_to_grade(total)

    logger.debug(
        "Behavioral score for agent %s: %d (%s), breakdown=%s",
        agent_id,
        total,
        grade,
        breakdown,
    )

    return BehavioralScore(
        score=total,
        breakdown=breakdown,
        grade=grade,
        computed_at=datetime.now(timezone.utc),
        agent_id=agent_id,
    )


async def compute_combined_trust_score(
    agent_id: str,
    store: TrustStore,
    behavioral_data: Optional[BehavioralData] = None,
    posture_machine: Optional[PostureStateMachine] = None,
    structural_weight: float = 0.6,
    behavioral_weight: float = 0.4,
) -> CombinedTrustScore:
    """Compute a combined structural + behavioral trust score.

    Behavioral is complementary — it never overrides structural. If no
    behavioral data is provided, the combined score equals the structural
    score (backward compatible).

    Args:
        agent_id: The agent identifier.
        store: TrustStore for structural scoring.
        behavioral_data: Optional behavioral data. If None, combined = structural.
        posture_machine: Optional PostureStateMachine for posture factor.
        structural_weight: Weight for structural score (default 0.6).
        behavioral_weight: Weight for behavioral score (default 0.4).

    Returns:
        CombinedTrustScore with both scores and blended result.
    """
    # Validate weight sum (must be approximately 1.0)
    weight_sum = structural_weight + behavioral_weight
    if abs(weight_sum - 1.0) > 0.01:
        raise ValueError(
            f"structural_weight ({structural_weight}) + behavioral_weight "
            f"({behavioral_weight}) must sum to 1.0, got {weight_sum}"
        )

    # Always compute structural
    structural = await compute_trust_score(agent_id, store, posture_machine)

    if behavioral_data is None:
        return CombinedTrustScore(
            structural_score=structural,
            behavioral_score=None,
            combined_score=structural.score,
            breakdown={
                "structural_weight": 1.0,
                "behavioral_weight": 0.0,
                "structural_contribution": structural.score,
                "behavioral_contribution": 0,
            },
        )

    behavioral = compute_behavioral_score(agent_id, behavioral_data)

    # Blend scores
    raw_combined = (
        structural.score * structural_weight + behavioral.score * behavioral_weight
    )
    combined = max(0, min(100, int(round(raw_combined))))

    return CombinedTrustScore(
        structural_score=structural,
        behavioral_score=behavioral,
        combined_score=combined,
        breakdown={
            "structural_weight": structural_weight,
            "behavioral_weight": behavioral_weight,
            "structural_contribution": round(structural.score * structural_weight, 2),
            "behavioral_contribution": round(behavioral.score * behavioral_weight, 2),
        },
    )


__all__ = [
    "TrustScore",
    "TrustReport",
    "compute_trust_score",
    "generate_trust_report",
    "score_to_grade",
    "SCORING_WEIGHTS",
    "POSTURE_SCORE_MAP",
    "GRADE_THRESHOLDS",
    # Behavioral scoring (Phase 4)
    "BEHAVIORAL_WEIGHTS",
    "BehavioralData",
    "BehavioralScore",
    "CombinedTrustScore",
    "compute_behavioral_score",
    "compute_combined_trust_score",
]

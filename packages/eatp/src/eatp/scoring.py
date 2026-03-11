# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Trust scoring engine for EATP agents.

Computes deterministic trust scores (0-100) for agents based on their
trust lineage chain completeness, delegation depth, constraint coverage,
posture level, and chain recency.

Scoring Factors (weights sum to 100):
    - Chain Completeness (30%): Has genesis, capabilities, constraint envelope
    - Delegation Depth (15%): Deeper chains = lower score (more risk)
    - Constraint Coverage (25%): More constraints = higher score (well-constrained)
    - Posture Level (20%): Stricter posture = higher score
    - Chain Recency (10%): Recent updates = higher score

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
    TrustPosture.FULL_AUTONOMY: 20,
    TrustPosture.ASSISTED: 40,
    TrustPosture.SUPERVISED: 80,
    TrustPosture.HUMAN_DECIDES: 100,
    TrustPosture.BLOCKED: 0,
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

    When ``posture_machine`` is None a default of SUPERVISED is assumed
    (moderate trust).

    Args:
        agent_id: Agent identifier to look up in the posture machine.
        posture_machine: Optional state machine holding agent postures.

    Returns:
        Float between 0.0 and 1.0.
    """
    if posture_machine is None:
        # Default to SUPERVISED (moderate trust, autonomy_level=3)
        posture = TrustPosture.SUPERVISED
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
    4. **Posture level** (20%) -- FULL_AUTONOMY=20, SUPERVISED=80,
       HUMAN_DECIDES=100 (stricter = higher).
    5. **Chain recency** (10%) -- recent updates = higher score.

    Args:
        agent_id: The agent whose trust to score.
        store: Trust store to retrieve the agent's chain from.
        posture_machine: Optional posture state machine for posture factor.
            When None, defaults to SUPERVISED posture.

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
        if posture == TrustPosture.FULL_AUTONOMY:
            risk_indicators.append(
                "Agent is running with full autonomy; no human oversight on actions"
            )
            recommendations.append(
                "Consider transitioning to SUPERVISED or ASSISTED posture "
                "to add oversight"
            )
        elif posture == TrustPosture.BLOCKED:
            risk_indicators.append("Agent is BLOCKED; it cannot perform any actions")
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


__all__ = [
    "TrustScore",
    "TrustReport",
    "compute_trust_score",
    "generate_trust_report",
    "score_to_grade",
    "SCORING_WEIGHTS",
    "POSTURE_SCORE_MAP",
    "GRADE_THRESHOLDS",
]

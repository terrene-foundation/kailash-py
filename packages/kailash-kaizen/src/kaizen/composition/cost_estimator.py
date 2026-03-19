from __future__ import annotations

# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
Cost estimator for composite agent pipelines.

Estimates total cost from historical invocation data, with confidence
levels based on the amount of historical data available.
"""

import logging
from typing import Any, Dict, List

from kaizen.composition.models import CostEstimate

logger = logging.getLogger(__name__)

__all__ = ["estimate_cost"]

# Confidence thresholds (invocation counts)
_HIGH_CONFIDENCE_THRESHOLD = 100
_MEDIUM_CONFIDENCE_THRESHOLD = 10


def estimate_cost(
    composition: List[Dict[str, Any]],
    historical_data: Dict[str, Dict[str, Any]],
) -> CostEstimate:
    """Estimate total cost of a composite pipeline from historical data.

    Args:
        composition: List of agent descriptors, each with at least "name" (str).
        historical_data: Per-agent historical data mapping agent name to
            {"avg_cost_microdollars": int, "invocation_count": int}.

    Returns:
        CostEstimate with total cost, per-agent breakdown, confidence, and warnings.
    """
    if not composition:
        logger.debug("estimate_cost called with empty composition")
        return CostEstimate(
            estimated_total_microdollars=0,
            per_agent={},
            confidence="low",
            warnings=[],
        )

    per_agent: Dict[str, int] = {}
    warnings: List[str] = []
    total_microdollars = 0
    min_invocation_count: int | None = None
    has_missing_agent = False

    for agent in composition:
        agent_name = agent["name"]
        agent_history = historical_data.get(agent_name)

        if agent_history is None:
            per_agent[agent_name] = 0
            has_missing_agent = True
            warnings.append(
                f"Agent '{agent_name}' has no historical data; "
                f"cost estimate is 0 microdollars"
            )
            logger.warning(
                "No historical data for agent '%s'; using 0 cost",
                agent_name,
            )
            continue

        cost = agent_history.get("avg_cost_microdollars", 0)
        invocation_count = agent_history.get("invocation_count", 0)

        per_agent[agent_name] = cost
        total_microdollars += cost

        if min_invocation_count is None:
            min_invocation_count = invocation_count
        else:
            min_invocation_count = min(min_invocation_count, invocation_count)

    # Determine confidence level
    confidence = _compute_confidence(
        min_invocation_count=min_invocation_count,
        has_missing_agent=has_missing_agent,
    )

    logger.debug(
        "Cost estimate: %d microdollars, confidence=%s, agents=%d",
        total_microdollars,
        confidence,
        len(composition),
    )

    return CostEstimate(
        estimated_total_microdollars=total_microdollars,
        per_agent=per_agent,
        confidence=confidence,
        warnings=warnings,
    )


def _compute_confidence(
    min_invocation_count: int | None,
    has_missing_agent: bool,
) -> str:
    """Compute confidence level based on historical data coverage.

    Args:
        min_invocation_count: Lowest invocation count among known agents,
            or None if no agents had historical data.
        has_missing_agent: True if any agent lacked historical data.

    Returns:
        "high", "medium", or "low".
    """
    if has_missing_agent:
        return "low"

    if min_invocation_count is None:
        return "low"

    if min_invocation_count >= _HIGH_CONFIDENCE_THRESHOLD:
        return "high"

    if min_invocation_count >= _MEDIUM_CONFIDENCE_THRESHOLD:
        return "medium"

    return "low"

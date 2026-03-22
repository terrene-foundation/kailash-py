# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""EnvelopeTracker — stateful continuous budget tracking.

Maintains running totals of resource consumption across depletable
dimensions (financial, operational, temporal). Reports remaining budget,
usage percentages, and gradient zone transitions.

All mutations protected by asyncio.Lock per AD-L3-04-AMENDED.
Bounded cost_history (maxlen=10000).

Invariants enforced:
    INV-1: Monotonically decreasing budget (except reclamation)
    INV-4: Envelope violations always BLOCKED
    INV-5: Reclamation ceiling
    INV-7: Finite arithmetic only
    INV-8: Zero budget means blocked
    INV-9: Atomic cost recording
    INV-10: Gradient zone monotonicity per dimension
"""

from __future__ import annotations

import asyncio
import logging
import math
import uuid
from collections import deque
from datetime import UTC, datetime
from typing import Any

from kaizen.l3.envelope.errors import TrackerError
from kaizen.l3.envelope.types import (
    DEPLETABLE_DIMENSIONS,
    BudgetRemaining,
    CostEntry,
    DimensionUsage,
    EnforcementContext,
    GradientZone,
    PlanGradient,
    ReclaimResult,
    Verdict,
    zone_max,
)

__all__ = ["EnvelopeTracker"]

logger = logging.getLogger(__name__)

_MAX_COST_HISTORY = 10_000


class EnvelopeTracker:
    """Continuous runtime budget tracker.

    Tracks consumption across financial, operational, and temporal dimensions.
    Cannot be constructed without an envelope.

    Args:
        envelope: Dict with financial_limit, temporal_limit_seconds, action_limit.
        gradient: PlanGradient configuration for zone transitions.
    """

    def __init__(
        self,
        envelope: dict[str, Any],
        gradient: PlanGradient,
    ) -> None:
        if envelope is None:
            raise ValueError("EnvelopeTracker requires a non-None envelope")
        if gradient is None:
            raise ValueError("EnvelopeTracker requires a non-None gradient")

        self._envelope = envelope
        self._gradient = gradient
        self._created_at = datetime.now(UTC)

        # Mutable state — protected by asyncio.Lock (INV-9)
        self._lock = asyncio.Lock()
        self._consumed_financial: float = 0.0
        self._consumed_temporal: float = 0.0
        self._actions_performed: int = 0
        self._cost_history: deque[CostEntry] = deque(maxlen=_MAX_COST_HISTORY)
        self._child_allocations: dict[str, float] = {}
        self._reclaimed_total: float = 0.0

    @property
    def envelope(self) -> dict[str, Any]:
        """The envelope being tracked against (immutable reference)."""
        return self._envelope

    @property
    def gradient(self) -> PlanGradient:
        """The gradient configuration."""
        return self._gradient

    async def record_consumption(self, entry: CostEntry) -> Verdict:
        """Record a consumption event atomically.

        Spec 4.1.2. Zone determination:
        1. new_usage = (consumed + cost) / limit
        2. > 1.0 -> BLOCKED (don't record)
        3. >= hold_threshold -> HELD (record)
        4. >= flag_threshold -> APPROVED{FLAGGED} (record)
        5. else -> APPROVED{AUTO_APPROVED} (record)

        Args:
            entry: The cost entry to record.

        Returns:
            Verdict indicating the resulting gradient zone.

        Raises:
            TrackerError: If the dimension is unknown or cost is invalid.
        """
        # Validate dimension
        if entry.dimension not in DEPLETABLE_DIMENSIONS:
            raise TrackerError.unknown_dimension(dimension=entry.dimension)

        async with self._lock:
            return self._record_consumption_locked(entry)

    def _record_consumption_locked(self, entry: CostEntry) -> Verdict:
        """Record consumption under lock. Returns verdict."""
        dim = entry.dimension
        cost = entry.cost

        # Get current consumed and limit for this dimension
        consumed, limit = self._get_consumed_and_limit(dim)
        if limit is None:
            # Unbounded dimension — always approved, still record
            self._apply_cost(dim, cost)
            self._cost_history.append(entry)
            usage = self._compute_usage_locked()
            return Verdict.approved(
                zone=GradientZone.AUTO_APPROVED,
                dimension_usage=usage,
            )

        # Compute new usage
        new_consumed = consumed + cost
        new_usage = new_consumed / limit if limit > 0 else (1.1 if cost > 0 else 0.0)

        # INV-4: > 1.0 -> BLOCKED (don't record)
        if new_usage > 1.0:
            return Verdict.blocked(
                dimension=dim,
                detail=f"Budget exceeded for dimension '{dim}'",
                requested=cost,
                available=max(0.0, limit - consumed),
            )

        # Record the cost
        self._apply_cost(dim, cost)
        self._cost_history.append(entry)

        # Determine zone
        flag_threshold, hold_threshold = self._gradient.get_thresholds(dim)

        if new_usage >= hold_threshold:
            hold_id = str(uuid.uuid4())
            return Verdict.held(
                dimension=dim,
                current_usage=new_usage,
                threshold=hold_threshold,
                hold_id=hold_id,
            )

        zone = (
            GradientZone.FLAGGED
            if new_usage >= flag_threshold
            else GradientZone.AUTO_APPROVED
        )
        usage = self._compute_usage_locked()
        return Verdict.approved(zone=zone, dimension_usage=usage)

    async def remaining(self) -> BudgetRemaining:
        """Current remaining budget across all dimensions.

        Spec 4.1.3. Pure read under lock.
        """
        async with self._lock:
            return self._remaining_locked()

    def _remaining_locked(self) -> BudgetRemaining:
        """Compute remaining budget under lock."""
        fin_limit = self._envelope.get("financial_limit")
        temp_limit = self._envelope.get("temporal_limit_seconds")
        action_limit = self._envelope.get("action_limit")

        fin_remaining: float | None = None
        if fin_limit is not None:
            child_alloc_total = sum(self._child_allocations.values())
            fin_remaining = fin_limit - self._consumed_financial - child_alloc_total

        temp_remaining: float | None = None
        if temp_limit is not None:
            temp_remaining = temp_limit - self._consumed_temporal

        actions_remaining: int | None = None
        if action_limit is not None:
            actions_remaining = action_limit - self._actions_performed

        per_dim: dict[str, float] = {}
        if fin_remaining is not None:
            per_dim["financial"] = fin_remaining
        if temp_remaining is not None:
            per_dim["temporal"] = temp_remaining
        if actions_remaining is not None:
            per_dim["operational"] = float(actions_remaining)

        return BudgetRemaining(
            financial_remaining=fin_remaining,
            temporal_remaining=temp_remaining,
            actions_remaining=actions_remaining,
            per_dimension=per_dim,
        )

    async def usage_pct(self) -> DimensionUsage:
        """Current usage as a fraction per dimension plus highest zone.

        Spec 4.1.4. Pure read under lock.
        """
        async with self._lock:
            return self._compute_usage_locked()

    def _compute_usage_locked(self) -> DimensionUsage:
        """Compute usage percentages under lock."""
        fin_limit = self._envelope.get("financial_limit")
        temp_limit = self._envelope.get("temporal_limit_seconds")
        action_limit = self._envelope.get("action_limit")

        fin_pct: float | None = None
        temp_pct: float | None = None
        op_pct: float | None = None
        highest = GradientZone.AUTO_APPROVED

        per_dim: dict[str, float] = {}

        if fin_limit is not None and fin_limit > 0:
            fin_pct = self._consumed_financial / fin_limit
            per_dim["financial"] = fin_pct
            highest = zone_max(highest, self._zone_for_usage(fin_pct, "financial"))

        if temp_limit is not None and temp_limit > 0:
            temp_pct = self._consumed_temporal / temp_limit
            per_dim["temporal"] = temp_pct
            highest = zone_max(highest, self._zone_for_usage(temp_pct, "temporal"))

        if action_limit is not None and action_limit > 0:
            op_pct = self._actions_performed / action_limit
            per_dim["operational"] = op_pct
            highest = zone_max(highest, self._zone_for_usage(op_pct, "operational"))

        return DimensionUsage(
            financial_pct=fin_pct,
            temporal_pct=temp_pct,
            operational_pct=op_pct,
            per_dimension=per_dim,
            highest_zone=highest,
        )

    def _zone_for_usage(self, usage: float, dimension: str) -> GradientZone:
        """Determine gradient zone for a usage fraction."""
        if usage > 1.0:
            return GradientZone.BLOCKED
        flag_t, hold_t = self._gradient.get_thresholds(dimension)
        if usage >= hold_t:
            return GradientZone.HELD
        if usage >= flag_t:
            return GradientZone.FLAGGED
        return GradientZone.AUTO_APPROVED

    async def can_afford(self, context: EnforcementContext) -> bool:
        """Advisory check — can the estimated costs be afforded?

        Spec 4.1.5. Pure read, no side effects.
        """
        async with self._lock:
            for dim, cost in context.dimension_costs.items():
                consumed, limit = self._get_consumed_and_limit(dim)
                if limit is not None:
                    if consumed + cost > limit:
                        return False
            return True

    async def allocate_to_child(self, child_id: str, amount: float) -> None:
        """Allocate financial budget to a child.

        Spec 4.1.6.

        Args:
            child_id: Unique identifier for the child.
            amount: Financial amount to allocate (must be > 0, finite).

        Raises:
            TrackerError: On invalid amount, duplicate child, or insufficient budget.
        """
        # Validate amount
        if not math.isfinite(amount):
            raise TrackerError.invalid_amount(
                reason="amount must be finite", value=amount
            )
        if amount <= 0:
            raise TrackerError.invalid_amount(
                reason="amount must be positive", value=amount
            )

        async with self._lock:
            # Check duplicate
            if child_id in self._child_allocations:
                raise TrackerError.duplicate_child(child_id=child_id)

            # Check budget
            remaining = self._remaining_locked()
            if (
                remaining.financial_remaining is not None
                and amount > remaining.financial_remaining
            ):
                raise TrackerError.budget_exceeded(
                    dimension="financial",
                    requested=amount,
                    available=remaining.financial_remaining,
                )

            self._child_allocations[child_id] = amount

    async def reclaim(self, child_id: str, consumed: float) -> ReclaimResult:
        """Reclaim unused budget from a completed child.

        Spec 4.1.7.

        Args:
            child_id: The child to reclaim from.
            consumed: Amount the child actually consumed.

        Returns:
            ReclaimResult describing what was returned.

        Raises:
            TrackerError: On unknown child, invalid consumed amount.
        """
        # Validate consumed
        if not math.isfinite(consumed):
            raise TrackerError.invalid_amount(
                reason="consumed must be finite", value=consumed
            )
        if consumed < 0:
            raise TrackerError.invalid_amount(
                reason="consumed must be non-negative", value=consumed
            )

        async with self._lock:
            if child_id not in self._child_allocations:
                raise TrackerError.unknown_child(child_id=child_id)

            allocated = self._child_allocations[child_id]

            if consumed > allocated:
                raise TrackerError.consumed_exceeds_allocated(
                    child_id=child_id,
                    consumed=consumed,
                    allocated=allocated,
                )

            reclaimed = allocated - consumed
            # Record child's consumed portion as parent's consumption,
            # then remove the allocation entry. This ensures:
            #   remaining = limit - consumed_financial - sum(child_allocs)
            # After reclaim: consumed_financial increases by child's consumed,
            # child allocation removed, net effect: reclaimed amount returned.
            self._consumed_financial += consumed
            del self._child_allocations[child_id]

            return ReclaimResult(
                reclaimed_financial=reclaimed,
                reclaimed_actions=0,
                reclaimed_temporal=0.0,
                child_id=child_id,
                child_total_consumed=consumed,
                child_total_allocated=allocated,
            )

    async def get_cost_history(self) -> list[CostEntry]:
        """Ordered list of all recorded cost entries.

        Spec 4.1.8. Pure read.
        """
        async with self._lock:
            return list(self._cost_history)

    # -------------------------------------------------------------------
    # Internal helpers
    # -------------------------------------------------------------------

    def _get_consumed_and_limit(self, dimension: str) -> tuple[float, float | None]:
        """Get (current_consumed, limit) for a dimension."""
        if dimension == "financial":
            return self._consumed_financial, self._envelope.get("financial_limit")
        elif dimension == "temporal":
            return self._consumed_temporal, self._envelope.get("temporal_limit_seconds")
        elif dimension == "operational":
            return float(self._actions_performed), (
                float(self._envelope["action_limit"])
                if self._envelope.get("action_limit") is not None
                else None
            )
        raise TrackerError.unknown_dimension(dimension=dimension)

    def _apply_cost(self, dimension: str, cost: float) -> None:
        """Apply a cost to the appropriate running total."""
        if dimension == "financial":
            self._consumed_financial += cost
        elif dimension == "temporal":
            self._consumed_temporal += cost
        elif dimension == "operational":
            self._actions_performed += int(cost)

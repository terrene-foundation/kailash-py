# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""M6-04: NaN/Inf injection tests for L3 envelope numeric boundaries.

Every numeric field in the L3 envelope module must reject NaN, Inf, -Inf,
and negative values with an explicit ValueError. This prevents silent
bypass of budget checks (NaN comparison always returns False) and
infinite-budget exploits (Inf always passes upper-bound checks).

Red team milestone: M6-04 (INV-7 enforcement).
"""

from __future__ import annotations

import math
from datetime import UTC, datetime

import pytest

from kaizen.l3.envelope.splitter import EnvelopeSplitter
from kaizen.l3.envelope.tracker import EnvelopeTracker
from kaizen.l3.envelope.types import (
    AllocationRequest,
    CostEntry,
    DimensionGradient,
    EnforcementContext,
    PlanGradient,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW = datetime.now(UTC)

_POISON_VALUES: list[tuple[str, float]] = [
    ("NaN", float("nan")),
    ("positive_Inf", float("inf")),
    ("negative_Inf", float("-inf")),
]

_NEGATIVE_VALUES: list[tuple[str, float]] = [
    ("negative", -1.0),
    ("large_negative", -1e308),
]

_ALL_INVALID: list[tuple[str, float]] = _POISON_VALUES + _NEGATIVE_VALUES


def _make_cost_entry(
    cost: float,
    dimension: str = "financial",
    action: str = "test_action",
    agent_id: str = "agent-001",
) -> CostEntry:
    """Helper that constructs a CostEntry -- will raise if cost is invalid."""
    return CostEntry(
        action=action,
        dimension=dimension,
        cost=cost,
        timestamp=_NOW,
        agent_instance_id=agent_id,
    )


def _default_envelope() -> dict:
    return {
        "financial_limit": 1000.0,
        "temporal_limit_seconds": 3600.0,
        "action_limit": 100,
    }


def _default_gradient() -> PlanGradient:
    return PlanGradient()


# ===========================================================================
# 1. CostEntry: NaN / Inf / negative cost
# ===========================================================================


class TestCostEntryNaNInjection:
    """CostEntry.cost must be finite and non-negative (INV-7)."""

    @pytest.mark.parametrize("label,value", _POISON_VALUES)
    def test_cost_entry_rejects_non_finite_cost(self, label: str, value: float) -> None:
        """NaN and Inf costs must raise ValueError at construction time."""
        with pytest.raises(ValueError, match="cost must be finite"):
            _make_cost_entry(cost=value)

    @pytest.mark.parametrize("label,value", _NEGATIVE_VALUES)
    def test_cost_entry_rejects_negative_cost(self, label: str, value: float) -> None:
        """Negative costs must raise ValueError at construction time."""
        with pytest.raises(ValueError, match="cost must be non-negative"):
            _make_cost_entry(cost=value)

    def test_cost_entry_accepts_zero(self) -> None:
        """Zero cost is valid (no budget consumed)."""
        entry = _make_cost_entry(cost=0.0)
        assert entry.cost == 0.0

    def test_cost_entry_accepts_positive(self) -> None:
        """Positive finite cost is valid."""
        entry = _make_cost_entry(cost=42.5)
        assert entry.cost == 42.5

    @pytest.mark.parametrize("label,value", _POISON_VALUES)
    def test_cost_entry_from_dict_rejects_non_finite(
        self, label: str, value: float
    ) -> None:
        """from_dict() must also reject NaN/Inf (deserialization path)."""
        data = {
            "action": "test",
            "dimension": "financial",
            "cost": value,
            "timestamp": _NOW.isoformat(),
            "agent_instance_id": "agent-001",
        }
        with pytest.raises(ValueError, match="cost must be finite"):
            CostEntry.from_dict(data)


# ===========================================================================
# 2. AllocationRequest: NaN / Inf / negative / > 1.0 ratios
# ===========================================================================


class TestAllocationRequestNaNInjection:
    """AllocationRequest ratios must be finite, non-negative, and <= 1.0."""

    @pytest.mark.parametrize("label,value", _POISON_VALUES)
    def test_financial_ratio_rejects_non_finite(self, label: str, value: float) -> None:
        with pytest.raises(ValueError, match="financial_ratio must be finite"):
            AllocationRequest(
                child_id="child-1",
                financial_ratio=value,
                temporal_ratio=0.5,
            )

    @pytest.mark.parametrize("label,value", _POISON_VALUES)
    def test_temporal_ratio_rejects_non_finite(self, label: str, value: float) -> None:
        with pytest.raises(ValueError, match="temporal_ratio must be finite"):
            AllocationRequest(
                child_id="child-1",
                financial_ratio=0.5,
                temporal_ratio=value,
            )

    @pytest.mark.parametrize("label,value", _NEGATIVE_VALUES)
    def test_financial_ratio_rejects_negative(self, label: str, value: float) -> None:
        with pytest.raises(ValueError, match="financial_ratio must be non-negative"):
            AllocationRequest(
                child_id="child-1",
                financial_ratio=value,
                temporal_ratio=0.5,
            )

    @pytest.mark.parametrize("label,value", _NEGATIVE_VALUES)
    def test_temporal_ratio_rejects_negative(self, label: str, value: float) -> None:
        with pytest.raises(ValueError, match="temporal_ratio must be non-negative"):
            AllocationRequest(
                child_id="child-1",
                financial_ratio=0.5,
                temporal_ratio=value,
            )

    def test_financial_ratio_rejects_above_one(self) -> None:
        with pytest.raises(ValueError, match="financial_ratio must be <= 1.0"):
            AllocationRequest(
                child_id="child-1",
                financial_ratio=1.01,
                temporal_ratio=0.5,
            )

    def test_temporal_ratio_rejects_above_one(self) -> None:
        with pytest.raises(ValueError, match="temporal_ratio must be <= 1.0"):
            AllocationRequest(
                child_id="child-1",
                financial_ratio=0.5,
                temporal_ratio=1.01,
            )

    def test_boundary_value_one_is_accepted(self) -> None:
        """Ratio of exactly 1.0 is valid (allocate everything)."""
        req = AllocationRequest(
            child_id="child-1",
            financial_ratio=1.0,
            temporal_ratio=1.0,
        )
        assert req.financial_ratio == 1.0
        assert req.temporal_ratio == 1.0

    @pytest.mark.parametrize("label,value", _POISON_VALUES)
    def test_from_dict_rejects_non_finite_financial_ratio(
        self, label: str, value: float
    ) -> None:
        data = {
            "child_id": "child-1",
            "financial_ratio": value,
            "temporal_ratio": 0.5,
        }
        with pytest.raises(ValueError, match="financial_ratio must be finite"):
            AllocationRequest.from_dict(data)


# ===========================================================================
# 3. PlanGradient: NaN / Inf thresholds and timeout
# ===========================================================================


class TestPlanGradientNaNInjection:
    """PlanGradient thresholds and timeout must be finite."""

    @pytest.mark.parametrize("label,value", _POISON_VALUES)
    def test_budget_flag_threshold_rejects_non_finite(
        self, label: str, value: float
    ) -> None:
        with pytest.raises(ValueError, match="budget_flag_threshold must be finite"):
            PlanGradient(budget_flag_threshold=value)

    @pytest.mark.parametrize("label,value", _POISON_VALUES)
    def test_budget_hold_threshold_rejects_non_finite(
        self, label: str, value: float
    ) -> None:
        with pytest.raises(ValueError, match="budget_hold_threshold must be finite"):
            PlanGradient(budget_hold_threshold=value)

    @pytest.mark.parametrize("label,value", _POISON_VALUES)
    def test_resolution_timeout_rejects_non_finite(
        self, label: str, value: float
    ) -> None:
        with pytest.raises(ValueError, match="resolution_timeout must be finite"):
            PlanGradient(resolution_timeout=value)

    def test_flag_threshold_rejects_negative(self) -> None:
        with pytest.raises(ValueError, match="budget_flag_threshold must be >= 0.0"):
            PlanGradient(budget_flag_threshold=-0.1)

    def test_hold_threshold_rejects_above_one(self) -> None:
        with pytest.raises(ValueError, match="budget_hold_threshold must be <= 1.0"):
            PlanGradient(budget_hold_threshold=1.01)

    def test_flag_must_be_less_than_hold(self) -> None:
        with pytest.raises(
            ValueError, match="budget_flag_threshold must be < budget_hold_threshold"
        ):
            PlanGradient(budget_flag_threshold=0.95, budget_hold_threshold=0.80)

    def test_flag_equal_to_hold_rejected(self) -> None:
        with pytest.raises(
            ValueError, match="budget_flag_threshold must be < budget_hold_threshold"
        ):
            PlanGradient(budget_flag_threshold=0.80, budget_hold_threshold=0.80)

    def test_resolution_timeout_rejects_zero(self) -> None:
        with pytest.raises(ValueError, match="resolution_timeout must be > 0"):
            PlanGradient(resolution_timeout=0.0)

    def test_resolution_timeout_rejects_negative(self) -> None:
        with pytest.raises(ValueError, match="resolution_timeout must be > 0"):
            PlanGradient(resolution_timeout=-1.0)

    def test_retry_budget_rejects_negative(self) -> None:
        with pytest.raises(ValueError, match="retry_budget must be >= 0"):
            PlanGradient(retry_budget=-1)

    @pytest.mark.parametrize("label,value", _POISON_VALUES)
    def test_from_dict_rejects_non_finite_thresholds(
        self, label: str, value: float
    ) -> None:
        """from_dict() deserialization path must also validate."""
        data = {
            "budget_flag_threshold": value,
            "budget_hold_threshold": 0.95,
            "resolution_timeout": 300.0,
        }
        with pytest.raises(ValueError, match="must be finite"):
            PlanGradient.from_dict(data)


# ===========================================================================
# 4. EnforcementContext: NaN / Inf estimated_cost and dimension_costs
# ===========================================================================


class TestEnforcementContextNaNInjection:
    """EnforcementContext.estimated_cost and dimension_costs must be finite
    and non-negative."""

    @pytest.mark.parametrize("label,value", _POISON_VALUES)
    def test_estimated_cost_rejects_non_finite(self, label: str, value: float) -> None:
        with pytest.raises(ValueError, match="estimated_cost must be finite"):
            EnforcementContext(
                action="test",
                estimated_cost=value,
                agent_instance_id="agent-001",
            )

    @pytest.mark.parametrize("label,value", _NEGATIVE_VALUES)
    def test_estimated_cost_rejects_negative(self, label: str, value: float) -> None:
        with pytest.raises(ValueError, match="estimated_cost must be non-negative"):
            EnforcementContext(
                action="test",
                estimated_cost=value,
                agent_instance_id="agent-001",
            )

    @pytest.mark.parametrize("label,value", _POISON_VALUES)
    def test_dimension_costs_rejects_non_finite(self, label: str, value: float) -> None:
        with pytest.raises(ValueError, match="dimension cost .* must be finite"):
            EnforcementContext(
                action="test",
                estimated_cost=1.0,
                agent_instance_id="agent-001",
                dimension_costs={"financial": value},
            )

    @pytest.mark.parametrize("label,value", _NEGATIVE_VALUES)
    def test_dimension_costs_rejects_negative(self, label: str, value: float) -> None:
        with pytest.raises(ValueError, match="dimension cost .* must be non-negative"):
            EnforcementContext(
                action="test",
                estimated_cost=1.0,
                agent_instance_id="agent-001",
                dimension_costs={"financial": value},
            )

    def test_zero_estimated_cost_accepted(self) -> None:
        ctx = EnforcementContext(
            action="test",
            estimated_cost=0.0,
            agent_instance_id="agent-001",
        )
        assert ctx.estimated_cost == 0.0

    @pytest.mark.parametrize("label,value", _POISON_VALUES)
    def test_from_dict_rejects_non_finite_estimated_cost(
        self, label: str, value: float
    ) -> None:
        data = {
            "action": "test",
            "estimated_cost": value,
            "agent_instance_id": "agent-001",
        }
        with pytest.raises(ValueError, match="estimated_cost must be finite"):
            EnforcementContext.from_dict(data)


# ===========================================================================
# 5. DimensionGradient: NaN / Inf thresholds
# ===========================================================================


class TestDimensionGradientNaNInjection:
    """DimensionGradient thresholds must be finite and properly ordered."""

    @pytest.mark.parametrize("label,value", _POISON_VALUES)
    def test_flag_threshold_rejects_non_finite(self, label: str, value: float) -> None:
        with pytest.raises(ValueError, match="flag_threshold must be finite"):
            DimensionGradient(flag_threshold=value, hold_threshold=0.9)

    @pytest.mark.parametrize("label,value", _POISON_VALUES)
    def test_hold_threshold_rejects_non_finite(self, label: str, value: float) -> None:
        with pytest.raises(ValueError, match="hold_threshold must be finite"):
            DimensionGradient(flag_threshold=0.7, hold_threshold=value)

    def test_flag_rejects_negative(self) -> None:
        with pytest.raises(ValueError, match="flag_threshold must be >= 0.0"):
            DimensionGradient(flag_threshold=-0.1, hold_threshold=0.9)

    def test_hold_rejects_above_one(self) -> None:
        with pytest.raises(ValueError, match="hold_threshold must be <= 1.0"):
            DimensionGradient(flag_threshold=0.7, hold_threshold=1.1)

    def test_flag_must_be_less_than_hold(self) -> None:
        with pytest.raises(ValueError, match="flag_threshold must be < hold_threshold"):
            DimensionGradient(flag_threshold=0.9, hold_threshold=0.7)

    def test_flag_equal_to_hold_rejected(self) -> None:
        with pytest.raises(ValueError, match="flag_threshold must be < hold_threshold"):
            DimensionGradient(flag_threshold=0.8, hold_threshold=0.8)

    def test_valid_thresholds_accepted(self) -> None:
        dg = DimensionGradient(flag_threshold=0.7, hold_threshold=0.9)
        assert dg.flag_threshold == 0.7
        assert dg.hold_threshold == 0.9

    @pytest.mark.parametrize("label,value", _POISON_VALUES)
    def test_from_dict_rejects_non_finite(self, label: str, value: float) -> None:
        data = {"flag_threshold": value, "hold_threshold": 0.9}
        with pytest.raises(ValueError, match="flag_threshold must be finite"):
            DimensionGradient.from_dict(data)


# ===========================================================================
# 6. EnvelopeSplitter: NaN / Inf reserve_pct
# ===========================================================================


class TestEnvelopeSplitterNaNInjection:
    """EnvelopeSplitter.split() must reject NaN/Inf reserve_pct."""

    def _make_parent(self) -> dict:
        return {
            "financial_limit": 1000.0,
            "temporal_limit_seconds": 3600.0,
            "action_limit": 100,
        }

    def _make_allocation(self) -> AllocationRequest:
        return AllocationRequest(
            child_id="child-1",
            financial_ratio=0.5,
            temporal_ratio=0.5,
        )

    @pytest.mark.parametrize("label,value", _POISON_VALUES)
    def test_split_rejects_non_finite_reserve(self, label: str, value: float) -> None:
        from kaizen.l3.envelope.errors import SplitError

        with pytest.raises(SplitError):
            EnvelopeSplitter.split(
                parent=self._make_parent(),
                allocations=[self._make_allocation()],
                reserve_pct=value,
            )

    @pytest.mark.parametrize("label,value", _NEGATIVE_VALUES)
    def test_split_rejects_negative_reserve(self, label: str, value: float) -> None:
        from kaizen.l3.envelope.errors import SplitError

        with pytest.raises(SplitError):
            EnvelopeSplitter.split(
                parent=self._make_parent(),
                allocations=[self._make_allocation()],
                reserve_pct=value,
            )

    def test_split_rejects_reserve_above_one(self) -> None:
        from kaizen.l3.envelope.errors import SplitError

        with pytest.raises(SplitError):
            EnvelopeSplitter.split(
                parent=self._make_parent(),
                allocations=[self._make_allocation()],
                reserve_pct=1.5,
            )


# ===========================================================================
# 7. EnvelopeTracker: NaN / Inf in allocate_to_child and reclaim
# ===========================================================================


class TestEnvelopeTrackerNaNInjection:
    """EnvelopeTracker.allocate_to_child() and reclaim() must reject
    NaN/Inf amounts."""

    def _make_tracker(self) -> EnvelopeTracker:
        return EnvelopeTracker(
            envelope=_default_envelope(),
            gradient=_default_gradient(),
        )

    @pytest.mark.asyncio
    @pytest.mark.parametrize("label,value", _POISON_VALUES)
    async def test_allocate_rejects_non_finite(self, label: str, value: float) -> None:
        from kaizen.l3.envelope.errors import TrackerError

        tracker = self._make_tracker()
        with pytest.raises(TrackerError, match="amount must be finite"):
            await tracker.allocate_to_child("child-1", amount=value)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("label,value", _NEGATIVE_VALUES)
    async def test_allocate_rejects_negative(self, label: str, value: float) -> None:
        from kaizen.l3.envelope.errors import TrackerError

        tracker = self._make_tracker()
        with pytest.raises(TrackerError, match="amount must be positive"):
            await tracker.allocate_to_child("child-1", amount=value)

    @pytest.mark.asyncio
    async def test_allocate_rejects_zero(self) -> None:
        from kaizen.l3.envelope.errors import TrackerError

        tracker = self._make_tracker()
        with pytest.raises(TrackerError, match="amount must be positive"):
            await tracker.allocate_to_child("child-1", amount=0.0)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("label,value", _POISON_VALUES)
    async def test_reclaim_rejects_non_finite(self, label: str, value: float) -> None:
        from kaizen.l3.envelope.errors import TrackerError

        tracker = self._make_tracker()
        await tracker.allocate_to_child("child-1", amount=100.0)
        with pytest.raises(TrackerError, match="consumed must be finite"):
            await tracker.reclaim("child-1", consumed=value)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("label,value", _NEGATIVE_VALUES)
    async def test_reclaim_rejects_negative(self, label: str, value: float) -> None:
        from kaizen.l3.envelope.errors import TrackerError

        tracker = self._make_tracker()
        await tracker.allocate_to_child("child-1", amount=100.0)
        with pytest.raises(TrackerError, match="consumed must be non-negative"):
            await tracker.reclaim("child-1", consumed=value)

    @pytest.mark.asyncio
    async def test_record_consumption_blocks_nan_via_cost_entry(self) -> None:
        """NaN cost is rejected at CostEntry construction, which happens
        before record_consumption is even called -- defense in depth."""
        tracker = self._make_tracker()
        with pytest.raises(ValueError, match="cost must be finite"):
            entry = _make_cost_entry(cost=float("nan"))
            await tracker.record_consumption(entry)

    @pytest.mark.asyncio
    async def test_record_consumption_blocks_inf_via_cost_entry(self) -> None:
        tracker = self._make_tracker()
        with pytest.raises(ValueError, match="cost must be finite"):
            entry = _make_cost_entry(cost=float("inf"))
            await tracker.record_consumption(entry)


# ===========================================================================
# 8. Defense-in-depth: NaN/Inf cannot silently bypass budget checks
# ===========================================================================


class TestNaNCannotBypassBudgetChecks:
    """Even if NaN/Inf somehow entered the system (e.g., via a future code
    path), demonstrate that the validation layers would catch it."""

    def test_nan_comparison_is_why_validation_matters(self) -> None:
        """Demonstrate the attack vector: NaN bypasses all comparisons."""
        nan = float("nan")
        # All of these are False -- NaN would bypass budget checks silently
        assert not (nan > 100.0)
        assert not (nan < 0.0)
        assert not (nan == 0.0)
        assert not (nan >= 0.0)
        assert not (nan <= 1.0)
        # math.isfinite catches it
        assert not math.isfinite(nan)

    def test_inf_comparison_is_why_validation_matters(self) -> None:
        """Demonstrate the attack vector: Inf defeats upper-bound checks."""
        inf = float("inf")
        # Inf > any finite number -- budget appears unlimited
        assert inf > 1e308
        # math.isfinite catches it
        assert not math.isfinite(inf)

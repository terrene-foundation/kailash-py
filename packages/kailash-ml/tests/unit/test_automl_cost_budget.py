# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for :mod:`kailash_ml.automl.cost_budget`.

Covers the CostTracker microdollar contract, budget-exceeded fail-CLOSED
behaviour, and the USD<->microdollar conversion helpers.
"""
from __future__ import annotations

import math

import pytest
from kailash_ml.automl.cost_budget import (
    BudgetExceeded,
    CostRecord,
    CostTracker,
    microdollars_to_usd,
    usd_to_microdollars,
)


# ---------------------------------------------------------------------------
# USD <-> microdollar helpers
# ---------------------------------------------------------------------------


class TestConversions:
    def test_usd_round_trip(self) -> None:
        assert usd_to_microdollars(1.0) == 1_000_000
        assert microdollars_to_usd(1_000_000) == 1.0

    def test_usd_rejects_nan(self) -> None:
        with pytest.raises(ValueError, match="finite"):
            usd_to_microdollars(float("nan"))

    def test_usd_rejects_inf(self) -> None:
        with pytest.raises(ValueError, match="finite"):
            usd_to_microdollars(float("inf"))

    def test_usd_rejects_negative(self) -> None:
        with pytest.raises(ValueError, match="non-negative"):
            usd_to_microdollars(-0.01)

    def test_usd_rejects_non_numeric(self) -> None:
        with pytest.raises(TypeError):
            usd_to_microdollars("1.0")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# CostTracker construction invariants
# ---------------------------------------------------------------------------


class TestCostTrackerConstruction:
    def test_requires_int_ceiling(self) -> None:
        with pytest.raises(TypeError):
            CostTracker(ceiling_microdollars=1.5, tenant_id="t1")  # type: ignore[arg-type]

    def test_requires_non_negative_ceiling(self) -> None:
        with pytest.raises(ValueError):
            CostTracker(ceiling_microdollars=-1, tenant_id="t1")

    def test_requires_nonempty_tenant(self) -> None:
        with pytest.raises(ValueError):
            CostTracker(ceiling_microdollars=1_000, tenant_id="")

    def test_requires_positive_ledger_cap(self) -> None:
        with pytest.raises(ValueError):
            CostTracker(
                ceiling_microdollars=1_000, tenant_id="t1", max_ledger_entries=0
            )

    def test_from_usd_helper(self) -> None:
        tracker = CostTracker.from_usd(ceiling_usd=2.5, tenant_id="t1")
        assert tracker.ceiling_microdollars == 2_500_000
        assert tracker.tenant_id == "t1"


# ---------------------------------------------------------------------------
# Budget behaviour
# ---------------------------------------------------------------------------


class TestCostTrackerBudget:
    @pytest.mark.asyncio
    async def test_record_adds_to_cumulative(self) -> None:
        tracker = CostTracker(ceiling_microdollars=10_000, tenant_id="t1")
        await tracker.record(microdollars=1_500, kind="trial")
        await tracker.record(microdollars=500, kind="trial")
        assert tracker.cumulative_microdollars == 2_000
        assert tracker.remaining_microdollars == 8_000

    @pytest.mark.asyncio
    async def test_budget_exceeded_raises(self) -> None:
        tracker = CostTracker(ceiling_microdollars=1_000, tenant_id="t1")
        with pytest.raises(BudgetExceeded) as exc:
            await tracker.record(microdollars=1_500, kind="trial")
        assert exc.value.ceiling_microdollars == 1_000
        assert exc.value.proposed_microdollars == 1_500

    @pytest.mark.asyncio
    async def test_unbounded_ceiling_never_raises(self) -> None:
        tracker = CostTracker(ceiling_microdollars=0, tenant_id="t1")
        # A ceiling of 0 is "explicit unbounded" per the contract
        await tracker.record(microdollars=10**18, kind="trial")
        assert tracker.check_would_exceed(10**18) is False

    @pytest.mark.asyncio
    async def test_compensating_negative_entry_accepted(self) -> None:
        tracker = CostTracker(ceiling_microdollars=1_000, tenant_id="t1")
        await tracker.record(microdollars=500, kind="trial")
        await tracker.record(microdollars=-200, kind="correction", note="refund")
        assert tracker.cumulative_microdollars == 300

    @pytest.mark.asyncio
    async def test_ledger_records_every_entry(self) -> None:
        tracker = CostTracker(ceiling_microdollars=1_000, tenant_id="t1")
        rec = await tracker.record(microdollars=100, kind="trial", trial_number=0)
        assert isinstance(rec, CostRecord)
        assert rec.kind == "trial"
        assert rec.trial_number == 0
        assert len(tracker.ledger()) == 1

    @pytest.mark.asyncio
    async def test_ledger_bounded_by_max_entries(self) -> None:
        tracker = CostTracker(
            ceiling_microdollars=10**12,
            tenant_id="t1",
            max_ledger_entries=3,
        )
        for i in range(5):
            await tracker.record(microdollars=1, kind="trial", trial_number=i)
        # Oldest two fall off
        ledger = tracker.ledger()
        assert len(ledger) == 3
        assert [r.trial_number for r in ledger] == [2, 3, 4]

    @pytest.mark.asyncio
    async def test_check_would_exceed_pure_read(self) -> None:
        tracker = CostTracker(ceiling_microdollars=1_000, tenant_id="t1")
        assert tracker.check_would_exceed(500) is False
        assert tracker.check_would_exceed(1_500) is True
        # No state change
        assert tracker.cumulative_microdollars == 0


# ---------------------------------------------------------------------------
# Deterministic unit-friendly coverage (no asyncio)
# ---------------------------------------------------------------------------


class TestMicrodollarPresentation:
    def test_zero(self) -> None:
        assert microdollars_to_usd(0) == 0.0

    def test_is_finite(self) -> None:
        assert math.isfinite(microdollars_to_usd(1_000_000))

# Copyright 2026 Terrene Foundation
# Licensed under the Apache License, Version 2.0
"""Regression: #291 — WorkResult constructor accepts NaN cost_usd.

Before fix: WorkResult(success=True, cost_usd=float('nan')) silently
created an object with NaN cost. Downstream consumers that trust
WorkResult (dashboards, billing) would propagate NaN.

After fix: __post_init__ clamps NaN/Inf to 0.0 with a warning log.
"""
from __future__ import annotations

import math

import pytest

from pact.work import WorkResult


@pytest.mark.regression
class TestIssue291WorkResultNaN:
    """WorkResult must not carry NaN/Inf in financial fields."""

    def test_nan_cost_usd_clamped_to_zero(self) -> None:
        result = WorkResult(success=True, cost_usd=float("nan"))
        assert result.cost_usd == 0.0
        assert math.isfinite(result.cost_usd)

    def test_inf_cost_usd_clamped_to_zero(self) -> None:
        result = WorkResult(success=True, cost_usd=float("inf"))
        assert result.cost_usd == 0.0

    def test_neg_inf_cost_usd_clamped_to_zero(self) -> None:
        result = WorkResult(success=True, cost_usd=float("-inf"))
        assert result.cost_usd == 0.0

    def test_nan_budget_allocated_set_to_none(self) -> None:
        result = WorkResult(success=True, budget_allocated=float("nan"))
        assert result.budget_allocated is None

    def test_inf_budget_allocated_set_to_none(self) -> None:
        result = WorkResult(success=True, budget_allocated=float("inf"))
        assert result.budget_allocated is None

    def test_valid_cost_usd_preserved(self) -> None:
        result = WorkResult(success=True, cost_usd=42.5)
        assert result.cost_usd == 42.5

    def test_valid_budget_allocated_preserved(self) -> None:
        result = WorkResult(success=True, budget_allocated=100.0)
        assert result.budget_allocated == 100.0

    def test_zero_cost_usd_valid(self) -> None:
        result = WorkResult(success=True, cost_usd=0.0)
        assert result.cost_usd == 0.0

    def test_from_dict_still_rejects_nan(self) -> None:
        """from_dict uses _validated_cost which raises — stricter than constructor."""
        with pytest.raises(ValueError, match="finite"):
            WorkResult.from_dict({"success": True, "cost_usd": float("nan")})

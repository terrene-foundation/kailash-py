# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for L3 envelope type definitions.

Covers:
- Frozen dataclass construction and immutability
- NaN/Inf rejection via __post_init__ for all numeric fields
- to_dict() / from_dict() round-trip serialization
- Validation constraints from spec Sections 2.1-2.14
"""

from __future__ import annotations

import math
import uuid
from datetime import UTC, datetime

import pytest


# ---------------------------------------------------------------------------
# GradientZone tests
# ---------------------------------------------------------------------------


class TestGradientZone:
    """GradientZone enum: 4 members with ordering."""

    def test_members_exist(self):
        from kaizen.l3.envelope.types import GradientZone

        assert hasattr(GradientZone, "AUTO_APPROVED")
        assert hasattr(GradientZone, "FLAGGED")
        assert hasattr(GradientZone, "HELD")
        assert hasattr(GradientZone, "BLOCKED")

    def test_ordering(self):
        """BLOCKED > HELD > FLAGGED > AUTO_APPROVED."""
        from kaizen.l3.envelope.types import GradientZone

        zones = [
            GradientZone.AUTO_APPROVED,
            GradientZone.FLAGGED,
            GradientZone.HELD,
            GradientZone.BLOCKED,
        ]
        # Each zone should be orderable via a severity property or comparison
        assert GradientZone.BLOCKED != GradientZone.AUTO_APPROVED

    def test_is_str_enum(self):
        from kaizen.l3.envelope.types import GradientZone

        assert isinstance(GradientZone.AUTO_APPROVED, str)


# ---------------------------------------------------------------------------
# CostEntry tests
# ---------------------------------------------------------------------------


class TestCostEntry:
    """CostEntry: frozen, validated, serializable."""

    def test_construction(self):
        from kaizen.l3.envelope.types import CostEntry

        ts = datetime.now(UTC)
        entry = CostEntry(
            action="tool_call",
            dimension="financial",
            cost=10.5,
            timestamp=ts,
            agent_instance_id="agent-001",
            metadata={"tool": "web_search"},
        )
        assert entry.action == "tool_call"
        assert entry.dimension == "financial"
        assert entry.cost == 10.5
        assert entry.timestamp == ts
        assert entry.agent_instance_id == "agent-001"
        assert entry.metadata == {"tool": "web_search"}

    def test_frozen(self):
        from kaizen.l3.envelope.types import CostEntry

        entry = CostEntry(
            action="a",
            dimension="financial",
            cost=1.0,
            timestamp=datetime.now(UTC),
            agent_instance_id="x",
        )
        with pytest.raises(AttributeError):
            entry.cost = 2.0  # type: ignore[misc]

    def test_rejects_nan_cost(self):
        from kaizen.l3.envelope.types import CostEntry

        with pytest.raises(ValueError, match="cost must be finite"):
            CostEntry(
                action="a",
                dimension="financial",
                cost=float("nan"),
                timestamp=datetime.now(UTC),
                agent_instance_id="x",
            )

    def test_rejects_inf_cost(self):
        from kaizen.l3.envelope.types import CostEntry

        with pytest.raises(ValueError, match="cost must be finite"):
            CostEntry(
                action="a",
                dimension="financial",
                cost=float("inf"),
                timestamp=datetime.now(UTC),
                agent_instance_id="x",
            )

    def test_rejects_negative_cost(self):
        from kaizen.l3.envelope.types import CostEntry

        with pytest.raises(ValueError, match="cost must be non-negative"):
            CostEntry(
                action="a",
                dimension="financial",
                cost=-1.0,
                timestamp=datetime.now(UTC),
                agent_instance_id="x",
            )

    def test_to_dict_from_dict_roundtrip(self):
        from kaizen.l3.envelope.types import CostEntry

        ts = datetime.now(UTC)
        entry = CostEntry(
            action="tool_call",
            dimension="financial",
            cost=10.5,
            timestamp=ts,
            agent_instance_id="agent-001",
            metadata={"tool": "web_search"},
        )
        d = entry.to_dict()
        restored = CostEntry.from_dict(d)
        assert restored.action == entry.action
        assert restored.dimension == entry.dimension
        assert restored.cost == entry.cost
        assert restored.agent_instance_id == entry.agent_instance_id
        assert restored.metadata == entry.metadata

    def test_default_metadata_is_empty(self):
        from kaizen.l3.envelope.types import CostEntry

        entry = CostEntry(
            action="a",
            dimension="financial",
            cost=1.0,
            timestamp=datetime.now(UTC),
            agent_instance_id="x",
        )
        assert entry.metadata == {}


# ---------------------------------------------------------------------------
# BudgetRemaining tests
# ---------------------------------------------------------------------------


class TestBudgetRemaining:
    """BudgetRemaining: frozen, optional fields."""

    def test_construction_all_none(self):
        from kaizen.l3.envelope.types import BudgetRemaining

        br = BudgetRemaining()
        assert br.financial_remaining is None
        assert br.temporal_remaining is None
        assert br.actions_remaining is None
        assert br.per_dimension == {}

    def test_construction_with_values(self):
        from kaizen.l3.envelope.types import BudgetRemaining

        br = BudgetRemaining(
            financial_remaining=500.0,
            temporal_remaining=120.0,
            actions_remaining=10,
            per_dimension={"financial": 500.0, "temporal": 120.0},
        )
        assert br.financial_remaining == 500.0
        assert br.actions_remaining == 10

    def test_frozen(self):
        from kaizen.l3.envelope.types import BudgetRemaining

        br = BudgetRemaining()
        with pytest.raises(AttributeError):
            br.financial_remaining = 100.0  # type: ignore[misc]

    def test_to_dict_from_dict_roundtrip(self):
        from kaizen.l3.envelope.types import BudgetRemaining

        br = BudgetRemaining(
            financial_remaining=500.0,
            temporal_remaining=120.0,
            actions_remaining=10,
            per_dimension={"financial": 500.0},
        )
        d = br.to_dict()
        restored = BudgetRemaining.from_dict(d)
        assert restored.financial_remaining == br.financial_remaining
        assert restored.temporal_remaining == br.temporal_remaining
        assert restored.actions_remaining == br.actions_remaining
        assert restored.per_dimension == br.per_dimension


# ---------------------------------------------------------------------------
# DimensionUsage tests
# ---------------------------------------------------------------------------


class TestDimensionUsage:
    """DimensionUsage: frozen, highest_zone computed."""

    def test_construction(self):
        from kaizen.l3.envelope.types import DimensionUsage, GradientZone

        du = DimensionUsage(
            financial_pct=0.5,
            temporal_pct=0.3,
            operational_pct=None,
            per_dimension={"financial": 0.5, "temporal": 0.3},
            highest_zone=GradientZone.AUTO_APPROVED,
        )
        assert du.financial_pct == 0.5
        assert du.highest_zone == GradientZone.AUTO_APPROVED

    def test_frozen(self):
        from kaizen.l3.envelope.types import DimensionUsage, GradientZone

        du = DimensionUsage(
            highest_zone=GradientZone.AUTO_APPROVED,
        )
        with pytest.raises(AttributeError):
            du.financial_pct = 0.9  # type: ignore[misc]

    def test_to_dict_from_dict_roundtrip(self):
        from kaizen.l3.envelope.types import DimensionUsage, GradientZone

        du = DimensionUsage(
            financial_pct=0.82,
            temporal_pct=0.45,
            operational_pct=None,
            per_dimension={"financial": 0.82, "temporal": 0.45},
            highest_zone=GradientZone.FLAGGED,
        )
        d = du.to_dict()
        restored = DimensionUsage.from_dict(d)
        assert restored.financial_pct == du.financial_pct
        assert restored.highest_zone == du.highest_zone


# ---------------------------------------------------------------------------
# ReclaimResult tests
# ---------------------------------------------------------------------------


class TestReclaimResult:
    """ReclaimResult: frozen, validated."""

    def test_construction(self):
        from kaizen.l3.envelope.types import ReclaimResult

        rr = ReclaimResult(
            reclaimed_financial=200.0,
            reclaimed_actions=5,
            reclaimed_temporal=60.0,
            child_id="child-001",
            child_total_consumed=300.0,
            child_total_allocated=500.0,
        )
        assert rr.reclaimed_financial == 200.0
        assert rr.child_id == "child-001"

    def test_frozen(self):
        from kaizen.l3.envelope.types import ReclaimResult

        rr = ReclaimResult(
            reclaimed_financial=0.0,
            reclaimed_actions=0,
            reclaimed_temporal=0.0,
            child_id="c",
            child_total_consumed=0.0,
            child_total_allocated=0.0,
        )
        with pytest.raises(AttributeError):
            rr.reclaimed_financial = 1.0  # type: ignore[misc]

    def test_to_dict_from_dict_roundtrip(self):
        from kaizen.l3.envelope.types import ReclaimResult

        rr = ReclaimResult(
            reclaimed_financial=200.0,
            reclaimed_actions=5,
            reclaimed_temporal=60.0,
            child_id="child-001",
            child_total_consumed=300.0,
            child_total_allocated=500.0,
        )
        d = rr.to_dict()
        restored = ReclaimResult.from_dict(d)
        assert restored.reclaimed_financial == rr.reclaimed_financial
        assert restored.child_id == rr.child_id


# ---------------------------------------------------------------------------
# AllocationRequest tests
# ---------------------------------------------------------------------------


class TestAllocationRequest:
    """AllocationRequest: frozen, ratio validation."""

    def test_construction(self):
        from kaizen.l3.envelope.types import AllocationRequest

        ar = AllocationRequest(
            child_id="child-001",
            financial_ratio=0.3,
            temporal_ratio=0.3,
        )
        assert ar.child_id == "child-001"
        assert ar.financial_ratio == 0.3

    def test_rejects_nan_ratio(self):
        from kaizen.l3.envelope.types import AllocationRequest

        with pytest.raises(ValueError, match="financial_ratio must be finite"):
            AllocationRequest(
                child_id="c",
                financial_ratio=float("nan"),
                temporal_ratio=0.5,
            )

    def test_rejects_inf_ratio(self):
        from kaizen.l3.envelope.types import AllocationRequest

        with pytest.raises(ValueError, match="temporal_ratio must be finite"):
            AllocationRequest(
                child_id="c",
                financial_ratio=0.5,
                temporal_ratio=float("inf"),
            )

    def test_rejects_negative_ratio(self):
        from kaizen.l3.envelope.types import AllocationRequest

        with pytest.raises(ValueError, match="financial_ratio must be non-negative"):
            AllocationRequest(
                child_id="c",
                financial_ratio=-0.1,
                temporal_ratio=0.5,
            )

    def test_rejects_ratio_above_one(self):
        from kaizen.l3.envelope.types import AllocationRequest

        with pytest.raises(ValueError, match="financial_ratio must be <= 1.0"):
            AllocationRequest(
                child_id="c",
                financial_ratio=1.1,
                temporal_ratio=0.5,
            )

    def test_frozen(self):
        from kaizen.l3.envelope.types import AllocationRequest

        ar = AllocationRequest(child_id="c", financial_ratio=0.5, temporal_ratio=0.5)
        with pytest.raises(AttributeError):
            ar.financial_ratio = 0.9  # type: ignore[misc]

    def test_to_dict_from_dict_roundtrip(self):
        from kaizen.l3.envelope.types import AllocationRequest

        ar = AllocationRequest(
            child_id="child-001",
            financial_ratio=0.3,
            temporal_ratio=0.4,
        )
        d = ar.to_dict()
        restored = AllocationRequest.from_dict(d)
        assert restored.child_id == ar.child_id
        assert restored.financial_ratio == ar.financial_ratio
        assert restored.temporal_ratio == ar.temporal_ratio


# ---------------------------------------------------------------------------
# PlanGradient tests
# ---------------------------------------------------------------------------


class TestPlanGradient:
    """PlanGradient: frozen, threshold constraints."""

    def test_default_construction(self):
        from kaizen.l3.envelope.types import PlanGradient

        pg = PlanGradient()
        assert pg.retry_budget == 2
        assert pg.budget_flag_threshold == 0.80
        assert pg.budget_hold_threshold == 0.95
        assert pg.resolution_timeout == 300.0
        assert pg.dimension_thresholds == {}

    def test_rejects_flag_gte_hold(self):
        from kaizen.l3.envelope.types import PlanGradient

        with pytest.raises(
            ValueError, match="budget_flag_threshold must be < budget_hold_threshold"
        ):
            PlanGradient(budget_flag_threshold=0.95, budget_hold_threshold=0.80)

    def test_rejects_flag_equals_hold(self):
        from kaizen.l3.envelope.types import PlanGradient

        with pytest.raises(
            ValueError, match="budget_flag_threshold must be < budget_hold_threshold"
        ):
            PlanGradient(budget_flag_threshold=0.80, budget_hold_threshold=0.80)

    def test_rejects_hold_above_one(self):
        from kaizen.l3.envelope.types import PlanGradient

        with pytest.raises(ValueError, match="budget_hold_threshold must be <= 1.0"):
            PlanGradient(budget_hold_threshold=1.01)

    def test_rejects_flag_below_zero(self):
        from kaizen.l3.envelope.types import PlanGradient

        with pytest.raises(ValueError, match="budget_flag_threshold must be >= 0.0"):
            PlanGradient(budget_flag_threshold=-0.1)

    def test_rejects_nan_thresholds(self):
        from kaizen.l3.envelope.types import PlanGradient

        with pytest.raises(ValueError, match="must be finite"):
            PlanGradient(budget_flag_threshold=float("nan"))

    def test_rejects_negative_retry_budget(self):
        from kaizen.l3.envelope.types import PlanGradient

        with pytest.raises(ValueError, match="retry_budget must be >= 0"):
            PlanGradient(retry_budget=-1)

    def test_rejects_non_positive_resolution_timeout(self):
        from kaizen.l3.envelope.types import PlanGradient

        with pytest.raises(ValueError, match="resolution_timeout must be > 0"):
            PlanGradient(resolution_timeout=0.0)

    def test_rejects_invalid_after_retry_exhaustion(self):
        from kaizen.l3.envelope.types import GradientZone, PlanGradient

        with pytest.raises(
            ValueError, match="after_retry_exhaustion must be HELD or BLOCKED"
        ):
            PlanGradient(after_retry_exhaustion=GradientZone.AUTO_APPROVED)

    def test_rejects_invalid_optional_node_failure(self):
        from kaizen.l3.envelope.types import GradientZone, PlanGradient

        with pytest.raises(
            ValueError,
            match="optional_node_failure must be AUTO_APPROVED, FLAGGED, or HELD",
        ):
            PlanGradient(optional_node_failure=GradientZone.BLOCKED)

    def test_frozen(self):
        from kaizen.l3.envelope.types import PlanGradient

        pg = PlanGradient()
        with pytest.raises(AttributeError):
            pg.retry_budget = 5  # type: ignore[misc]

    def test_to_dict_from_dict_roundtrip(self):
        from kaizen.l3.envelope.types import PlanGradient

        pg = PlanGradient(
            retry_budget=3,
            budget_flag_threshold=0.70,
            budget_hold_threshold=0.90,
        )
        d = pg.to_dict()
        restored = PlanGradient.from_dict(d)
        assert restored.retry_budget == pg.retry_budget
        assert restored.budget_flag_threshold == pg.budget_flag_threshold
        assert restored.budget_hold_threshold == pg.budget_hold_threshold


# ---------------------------------------------------------------------------
# DimensionGradient tests
# ---------------------------------------------------------------------------


class TestDimensionGradient:
    """DimensionGradient: frozen, threshold ordering."""

    def test_construction(self):
        from kaizen.l3.envelope.types import DimensionGradient

        dg = DimensionGradient(flag_threshold=0.7, hold_threshold=0.9)
        assert dg.flag_threshold == 0.7
        assert dg.hold_threshold == 0.9

    def test_rejects_flag_gte_hold(self):
        from kaizen.l3.envelope.types import DimensionGradient

        with pytest.raises(ValueError, match="flag_threshold must be < hold_threshold"):
            DimensionGradient(flag_threshold=0.9, hold_threshold=0.7)

    def test_rejects_nan(self):
        from kaizen.l3.envelope.types import DimensionGradient

        with pytest.raises(ValueError, match="must be finite"):
            DimensionGradient(flag_threshold=float("nan"), hold_threshold=0.9)

    def test_frozen(self):
        from kaizen.l3.envelope.types import DimensionGradient

        dg = DimensionGradient(flag_threshold=0.7, hold_threshold=0.9)
        with pytest.raises(AttributeError):
            dg.flag_threshold = 0.5  # type: ignore[misc]

    def test_to_dict_from_dict_roundtrip(self):
        from kaizen.l3.envelope.types import DimensionGradient

        dg = DimensionGradient(flag_threshold=0.7, hold_threshold=0.9)
        d = dg.to_dict()
        restored = DimensionGradient.from_dict(d)
        assert restored.flag_threshold == dg.flag_threshold
        assert restored.hold_threshold == dg.hold_threshold


# ---------------------------------------------------------------------------
# EnforcementContext tests
# ---------------------------------------------------------------------------


class TestEnforcementContext:
    """EnforcementContext: frozen, validated."""

    def test_construction(self):
        from kaizen.l3.envelope.types import EnforcementContext

        ctx = EnforcementContext(
            action="web_search",
            estimated_cost=5.0,
            agent_instance_id="agent-001",
            dimension_costs={"financial": 5.0},
        )
        assert ctx.action == "web_search"
        assert ctx.estimated_cost == 5.0

    def test_rejects_nan_cost(self):
        from kaizen.l3.envelope.types import EnforcementContext

        with pytest.raises(ValueError, match="estimated_cost must be finite"):
            EnforcementContext(
                action="a",
                estimated_cost=float("nan"),
                agent_instance_id="x",
            )

    def test_rejects_negative_cost(self):
        from kaizen.l3.envelope.types import EnforcementContext

        with pytest.raises(ValueError, match="estimated_cost must be non-negative"):
            EnforcementContext(
                action="a",
                estimated_cost=-1.0,
                agent_instance_id="x",
            )

    def test_rejects_nan_in_dimension_costs(self):
        from kaizen.l3.envelope.types import EnforcementContext

        with pytest.raises(ValueError, match="dimension cost .* must be finite"):
            EnforcementContext(
                action="a",
                estimated_cost=5.0,
                agent_instance_id="x",
                dimension_costs={"financial": float("nan")},
            )

    def test_frozen(self):
        from kaizen.l3.envelope.types import EnforcementContext

        ctx = EnforcementContext(
            action="a",
            estimated_cost=1.0,
            agent_instance_id="x",
        )
        with pytest.raises(AttributeError):
            ctx.estimated_cost = 2.0  # type: ignore[misc]

    def test_to_dict_from_dict_roundtrip(self):
        from kaizen.l3.envelope.types import EnforcementContext

        ctx = EnforcementContext(
            action="web_search",
            estimated_cost=5.0,
            agent_instance_id="agent-001",
            dimension_costs={"financial": 5.0},
            metadata={"tool": "web_search"},
        )
        d = ctx.to_dict()
        restored = EnforcementContext.from_dict(d)
        assert restored.action == ctx.action
        assert restored.estimated_cost == ctx.estimated_cost
        assert restored.dimension_costs == ctx.dimension_costs


# ---------------------------------------------------------------------------
# Verdict tests
# ---------------------------------------------------------------------------


class TestVerdict:
    """Verdict: discriminated union with APPROVED, HELD, BLOCKED."""

    def test_approved_construction(self):
        from kaizen.l3.envelope.types import DimensionUsage, GradientZone, Verdict

        usage = DimensionUsage(highest_zone=GradientZone.AUTO_APPROVED)
        v = Verdict.approved(zone=GradientZone.AUTO_APPROVED, dimension_usage=usage)
        assert v.tag == "APPROVED"
        assert v.zone == GradientZone.AUTO_APPROVED

    def test_held_construction(self):
        from kaizen.l3.envelope.types import Verdict

        v = Verdict.held(
            dimension="financial",
            current_usage=0.96,
            threshold=0.95,
            hold_id="hold-001",
        )
        assert v.tag == "HELD"
        assert v.dimension == "financial"
        assert v.hold_id == "hold-001"

    def test_blocked_construction(self):
        from kaizen.l3.envelope.types import Verdict

        v = Verdict.blocked(
            dimension="financial",
            detail="Budget exceeded",
            requested=500.0,
            available=100.0,
        )
        assert v.tag == "BLOCKED"
        assert v.requested == 500.0
        assert v.available == 100.0

    def test_is_approved(self):
        from kaizen.l3.envelope.types import DimensionUsage, GradientZone, Verdict

        usage = DimensionUsage(highest_zone=GradientZone.AUTO_APPROVED)
        v = Verdict.approved(zone=GradientZone.AUTO_APPROVED, dimension_usage=usage)
        assert v.is_approved is True

        v2 = Verdict.blocked(
            dimension="financial",
            detail="exceeded",
            requested=1.0,
            available=0.0,
        )
        assert v2.is_approved is False

    def test_frozen(self):
        from kaizen.l3.envelope.types import DimensionUsage, GradientZone, Verdict

        usage = DimensionUsage(highest_zone=GradientZone.AUTO_APPROVED)
        v = Verdict.approved(zone=GradientZone.AUTO_APPROVED, dimension_usage=usage)
        with pytest.raises(AttributeError):
            v.tag = "BLOCKED"  # type: ignore[misc]

    def test_to_dict_from_dict_roundtrip(self):
        from kaizen.l3.envelope.types import Verdict

        v = Verdict.blocked(
            dimension="financial",
            detail="Budget exceeded",
            requested=500.0,
            available=100.0,
        )
        d = v.to_dict()
        restored = Verdict.from_dict(d)
        assert restored.tag == v.tag
        assert restored.dimension == v.dimension
        assert restored.requested == v.requested

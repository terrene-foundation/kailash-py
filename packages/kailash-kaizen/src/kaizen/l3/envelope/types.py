# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""L3 envelope type definitions.

All types are frozen dataclasses per AD-L3-15 (value types).
All numeric fields validated with math.isfinite() per INV-7.
All types support to_dict() / from_dict() round-trip serialization.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

__all__ = [
    "AllocationRequest",
    "BudgetRemaining",
    "CostEntry",
    "DimensionGradient",
    "DimensionUsage",
    "EnforcementContext",
    "GradientZone",
    "PlanGradient",
    "ReclaimResult",
    "Verdict",
]

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# GradientZone (aliased from pact.governance.config.VerificationLevel
#               per AD-L3-02-AMENDED, with standalone fallback)
# ---------------------------------------------------------------------------

try:
    from pact.governance.config import VerificationLevel as _VerificationLevel

    class GradientZone(str, Enum):
        """Budget gradient zones — maps to PACT VerificationLevel.

        Ordering: BLOCKED > HELD > FLAGGED > AUTO_APPROVED.
        A zone can only be tightened (moved toward BLOCKED), never loosened,
        within a single delegation chain.
        """

        AUTO_APPROVED = "AUTO_APPROVED"
        FLAGGED = "FLAGGED"
        HELD = "HELD"
        BLOCKED = "BLOCKED"

except ImportError:

    class GradientZone(str, Enum):  # type: ignore[no-redef]
        """Budget gradient zones (standalone — pact not available).

        Ordering: BLOCKED > HELD > FLAGGED > AUTO_APPROVED.
        """

        AUTO_APPROVED = "AUTO_APPROVED"
        FLAGGED = "FLAGGED"
        HELD = "HELD"
        BLOCKED = "BLOCKED"


# Severity ordering for comparisons
_ZONE_SEVERITY: dict[GradientZone, int] = {
    GradientZone.AUTO_APPROVED: 0,
    GradientZone.FLAGGED: 1,
    GradientZone.HELD: 2,
    GradientZone.BLOCKED: 3,
}


def zone_max(a: GradientZone, b: GradientZone) -> GradientZone:
    """Return the more restrictive (higher severity) zone."""
    if _ZONE_SEVERITY[a] >= _ZONE_SEVERITY[b]:
        return a
    return b


# ---------------------------------------------------------------------------
# Depletable dimension names (canonical)
# ---------------------------------------------------------------------------

DEPLETABLE_DIMENSIONS = frozenset({"financial", "operational", "temporal"})


# ---------------------------------------------------------------------------
# Helper: validate finite
# ---------------------------------------------------------------------------


def _validate_finite(value: float, name: str) -> None:
    """Raise ValueError if value is NaN or Inf."""
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite, got {value!r}")


def _validate_non_negative(value: float, name: str) -> None:
    """Raise ValueError if value is negative."""
    if value < 0:
        raise ValueError(f"{name} must be non-negative, got {value!r}")


# ---------------------------------------------------------------------------
# CostEntry
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CostEntry:
    """A single consumption event against a budget dimension.

    Spec Section 2.4. Costs are always non-negative and finite.
    """

    action: str
    dimension: str
    cost: float
    timestamp: datetime
    agent_instance_id: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _validate_finite(self.cost, "cost")
        _validate_non_negative(self.cost, "cost")

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "dimension": self.dimension,
            "cost": self.cost,
            "timestamp": self.timestamp.isoformat(),
            "agent_instance_id": self.agent_instance_id,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CostEntry:
        ts = data["timestamp"]
        if isinstance(ts, str):
            ts = datetime.fromisoformat(ts)
        return cls(
            action=data["action"],
            dimension=data["dimension"],
            cost=float(data["cost"]),
            timestamp=ts,
            agent_instance_id=data["agent_instance_id"],
            metadata=data.get("metadata", {}),
        )


# ---------------------------------------------------------------------------
# BudgetRemaining
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BudgetRemaining:
    """Current remaining budget across all dimensions.

    Spec Section 2.5. None = unbounded (no limit set).
    """

    financial_remaining: float | None = None
    temporal_remaining: float | None = None
    actions_remaining: int | None = None
    per_dimension: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "financial_remaining": self.financial_remaining,
            "temporal_remaining": self.temporal_remaining,
            "actions_remaining": self.actions_remaining,
            "per_dimension": self.per_dimension,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BudgetRemaining:
        return cls(
            financial_remaining=data.get("financial_remaining"),
            temporal_remaining=data.get("temporal_remaining"),
            actions_remaining=(
                int(data["actions_remaining"])
                if data.get("actions_remaining") is not None
                else None
            ),
            per_dimension=data.get("per_dimension", {}),
        )


# ---------------------------------------------------------------------------
# DimensionUsage
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DimensionUsage:
    """Current usage as a fraction per dimension, plus the highest zone.

    Spec Section 2.6. None = unbounded dimension.
    """

    highest_zone: GradientZone
    financial_pct: float | None = None
    temporal_pct: float | None = None
    operational_pct: float | None = None
    per_dimension: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "financial_pct": self.financial_pct,
            "temporal_pct": self.temporal_pct,
            "operational_pct": self.operational_pct,
            "per_dimension": self.per_dimension,
            "highest_zone": self.highest_zone.value,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DimensionUsage:
        return cls(
            financial_pct=data.get("financial_pct"),
            temporal_pct=data.get("temporal_pct"),
            operational_pct=data.get("operational_pct"),
            per_dimension=data.get("per_dimension", {}),
            highest_zone=GradientZone(data["highest_zone"]),
        )


# ---------------------------------------------------------------------------
# ReclaimResult
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ReclaimResult:
    """Result of reclaiming budget from a completed child.

    Spec Section 2.7.
    """

    reclaimed_financial: float
    reclaimed_actions: int
    reclaimed_temporal: float
    child_id: str
    child_total_consumed: float
    child_total_allocated: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "reclaimed_financial": self.reclaimed_financial,
            "reclaimed_actions": self.reclaimed_actions,
            "reclaimed_temporal": self.reclaimed_temporal,
            "child_id": self.child_id,
            "child_total_consumed": self.child_total_consumed,
            "child_total_allocated": self.child_total_allocated,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ReclaimResult:
        return cls(
            reclaimed_financial=float(data["reclaimed_financial"]),
            reclaimed_actions=int(data["reclaimed_actions"]),
            reclaimed_temporal=float(data["reclaimed_temporal"]),
            child_id=data["child_id"],
            child_total_consumed=float(data["child_total_consumed"]),
            child_total_allocated=float(data["child_total_allocated"]),
        )


# ---------------------------------------------------------------------------
# AllocationRequest
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AllocationRequest:
    """Request to allocate a portion of the parent's budget to a child.

    Spec Section 2.9. Ratios must be in [0.0, 1.0] and finite.
    """

    child_id: str
    financial_ratio: float
    temporal_ratio: float
    operational_override: Any | None = None
    data_access_override: Any | None = None
    communication_override: Any | None = None

    def __post_init__(self) -> None:
        _validate_finite(self.financial_ratio, "financial_ratio")
        _validate_non_negative(self.financial_ratio, "financial_ratio")
        if self.financial_ratio > 1.0:
            raise ValueError(
                f"financial_ratio must be <= 1.0, got {self.financial_ratio!r}"
            )

        _validate_finite(self.temporal_ratio, "temporal_ratio")
        _validate_non_negative(self.temporal_ratio, "temporal_ratio")
        if self.temporal_ratio > 1.0:
            raise ValueError(
                f"temporal_ratio must be <= 1.0, got {self.temporal_ratio!r}"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "child_id": self.child_id,
            "financial_ratio": self.financial_ratio,
            "temporal_ratio": self.temporal_ratio,
            "operational_override": self.operational_override,
            "data_access_override": self.data_access_override,
            "communication_override": self.communication_override,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AllocationRequest:
        return cls(
            child_id=data["child_id"],
            financial_ratio=float(data["financial_ratio"]),
            temporal_ratio=float(data["temporal_ratio"]),
            operational_override=data.get("operational_override"),
            data_access_override=data.get("data_access_override"),
            communication_override=data.get("communication_override"),
        )


# ---------------------------------------------------------------------------
# DimensionGradient
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DimensionGradient:
    """Per-dimension gradient thresholds.

    Spec Section 2.3. flag_threshold < hold_threshold, both in [0.0, 1.0].
    BLOCKED is always at 1.0 (non-configurable).
    """

    flag_threshold: float
    hold_threshold: float

    def __post_init__(self) -> None:
        _validate_finite(self.flag_threshold, "flag_threshold")
        _validate_finite(self.hold_threshold, "hold_threshold")
        if self.flag_threshold < 0.0:
            raise ValueError(
                f"flag_threshold must be >= 0.0, got {self.flag_threshold!r}"
            )
        if self.hold_threshold > 1.0:
            raise ValueError(
                f"hold_threshold must be <= 1.0, got {self.hold_threshold!r}"
            )
        if self.flag_threshold >= self.hold_threshold:
            raise ValueError(
                f"flag_threshold must be < hold_threshold, "
                f"got flag={self.flag_threshold!r} hold={self.hold_threshold!r}"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "flag_threshold": self.flag_threshold,
            "hold_threshold": self.hold_threshold,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DimensionGradient:
        return cls(
            flag_threshold=float(data["flag_threshold"]),
            hold_threshold=float(data["hold_threshold"]),
        )


# ---------------------------------------------------------------------------
# PlanGradient
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PlanGradient:
    """Gradient configuration for plan execution.

    Spec Section 2.2. Controls zone transitions and retry behavior.
    """

    retry_budget: int = 2
    after_retry_exhaustion: GradientZone = GradientZone.HELD
    resolution_timeout: float = 300.0
    optional_node_failure: GradientZone = GradientZone.FLAGGED
    budget_flag_threshold: float = 0.80
    budget_hold_threshold: float = 0.95
    dimension_thresholds: dict[str, DimensionGradient] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Finite checks
        _validate_finite(self.budget_flag_threshold, "budget_flag_threshold")
        _validate_finite(self.budget_hold_threshold, "budget_hold_threshold")
        _validate_finite(self.resolution_timeout, "resolution_timeout")

        # Range checks
        if self.budget_flag_threshold < 0.0:
            raise ValueError(
                f"budget_flag_threshold must be >= 0.0, "
                f"got {self.budget_flag_threshold!r}"
            )
        if self.budget_hold_threshold > 1.0:
            raise ValueError(
                f"budget_hold_threshold must be <= 1.0, "
                f"got {self.budget_hold_threshold!r}"
            )
        if self.budget_flag_threshold >= self.budget_hold_threshold:
            raise ValueError(
                f"budget_flag_threshold must be < budget_hold_threshold, "
                f"got flag={self.budget_flag_threshold!r} "
                f"hold={self.budget_hold_threshold!r}"
            )

        # Retry budget
        if self.retry_budget < 0:
            raise ValueError(f"retry_budget must be >= 0, got {self.retry_budget!r}")

        # Resolution timeout
        if self.resolution_timeout <= 0:
            raise ValueError(
                f"resolution_timeout must be > 0, got {self.resolution_timeout!r}"
            )

        # after_retry_exhaustion must be HELD or BLOCKED
        if self.after_retry_exhaustion not in (GradientZone.HELD, GradientZone.BLOCKED):
            raise ValueError(
                f"after_retry_exhaustion must be HELD or BLOCKED, "
                f"got {self.after_retry_exhaustion!r}"
            )

        # optional_node_failure must be AUTO_APPROVED, FLAGGED, or HELD
        if self.optional_node_failure not in (
            GradientZone.AUTO_APPROVED,
            GradientZone.FLAGGED,
            GradientZone.HELD,
        ):
            raise ValueError(
                f"optional_node_failure must be AUTO_APPROVED, FLAGGED, or HELD, "
                f"got {self.optional_node_failure!r}"
            )

    def get_thresholds(self, dimension: str) -> tuple[float, float]:
        """Get (flag_threshold, hold_threshold) for a dimension.

        Uses per-dimension override if set, otherwise global defaults.
        """
        if dimension in self.dimension_thresholds:
            dg = self.dimension_thresholds[dimension]
            return dg.flag_threshold, dg.hold_threshold
        return self.budget_flag_threshold, self.budget_hold_threshold

    def to_dict(self) -> dict[str, Any]:
        return {
            "retry_budget": self.retry_budget,
            "after_retry_exhaustion": self.after_retry_exhaustion.value,
            "resolution_timeout": self.resolution_timeout,
            "optional_node_failure": self.optional_node_failure.value,
            "budget_flag_threshold": self.budget_flag_threshold,
            "budget_hold_threshold": self.budget_hold_threshold,
            "dimension_thresholds": {
                k: v.to_dict() for k, v in self.dimension_thresholds.items()
            },
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PlanGradient:
        dim_thresholds = {}
        for k, v in data.get("dimension_thresholds", {}).items():
            dim_thresholds[k] = DimensionGradient.from_dict(v)
        return cls(
            retry_budget=int(data.get("retry_budget", 2)),
            after_retry_exhaustion=GradientZone(
                data.get("after_retry_exhaustion", "HELD")
            ),
            resolution_timeout=float(data.get("resolution_timeout", 300.0)),
            optional_node_failure=GradientZone(
                data.get("optional_node_failure", "FLAGGED")
            ),
            budget_flag_threshold=float(data.get("budget_flag_threshold", 0.80)),
            budget_hold_threshold=float(data.get("budget_hold_threshold", 0.95)),
            dimension_thresholds=dim_thresholds,
        )


# ---------------------------------------------------------------------------
# EnforcementContext
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EnforcementContext:
    """Context for an action to be checked/recorded by the enforcer.

    Spec Section 2.13.
    """

    action: str
    estimated_cost: float
    agent_instance_id: str
    dimension_costs: dict[str, float] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _validate_finite(self.estimated_cost, "estimated_cost")
        _validate_non_negative(self.estimated_cost, "estimated_cost")
        for dim, cost in self.dimension_costs.items():
            if not math.isfinite(cost):
                raise ValueError(
                    f"dimension cost for '{dim}' must be finite, got {cost!r}"
                )
            if cost < 0:
                raise ValueError(
                    f"dimension cost for '{dim}' must be non-negative, got {cost!r}"
                )

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "estimated_cost": self.estimated_cost,
            "agent_instance_id": self.agent_instance_id,
            "dimension_costs": self.dimension_costs,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EnforcementContext:
        return cls(
            action=data["action"],
            estimated_cost=float(data["estimated_cost"]),
            agent_instance_id=data["agent_instance_id"],
            dimension_costs=data.get("dimension_costs", {}),
            metadata=data.get("metadata", {}),
        )


# ---------------------------------------------------------------------------
# Verdict (discriminated union)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Verdict:
    """Verdict from envelope enforcement — discriminated union.

    Tags: APPROVED, HELD, BLOCKED.
    Spec Section 2.12.
    """

    tag: str

    # APPROVED fields
    zone: GradientZone | None = None
    dimension_usage: DimensionUsage | None = None

    # HELD fields
    dimension: str | None = None
    current_usage: float | None = None
    threshold: float | None = None
    hold_id: str | None = None

    # BLOCKED fields (dimension reused from HELD)
    detail: str | None = None
    requested: float | None = None
    available: float | None = None

    @property
    def is_approved(self) -> bool:
        """True if the action may proceed (APPROVED tag)."""
        return self.tag == "APPROVED"

    @classmethod
    def approved(cls, zone: GradientZone, dimension_usage: DimensionUsage) -> Verdict:
        """Create an APPROVED verdict."""
        return cls(tag="APPROVED", zone=zone, dimension_usage=dimension_usage)

    @classmethod
    def held(
        cls,
        dimension: str,
        current_usage: float,
        threshold: float,
        hold_id: str,
    ) -> Verdict:
        """Create a HELD verdict."""
        return cls(
            tag="HELD",
            dimension=dimension,
            current_usage=current_usage,
            threshold=threshold,
            hold_id=hold_id,
        )

    @classmethod
    def blocked(
        cls,
        dimension: str,
        detail: str,
        requested: float,
        available: float,
    ) -> Verdict:
        """Create a BLOCKED verdict."""
        return cls(
            tag="BLOCKED",
            dimension=dimension,
            detail=detail,
            requested=requested,
            available=available,
        )

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"tag": self.tag}
        if self.tag == "APPROVED":
            d["zone"] = self.zone.value if self.zone else None
            d["dimension_usage"] = (
                self.dimension_usage.to_dict() if self.dimension_usage else None
            )
        elif self.tag == "HELD":
            d["dimension"] = self.dimension
            d["current_usage"] = self.current_usage
            d["threshold"] = self.threshold
            d["hold_id"] = self.hold_id
        elif self.tag == "BLOCKED":
            d["dimension"] = self.dimension
            d["detail"] = self.detail
            d["requested"] = self.requested
            d["available"] = self.available
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Verdict:
        tag = data["tag"]
        if tag == "APPROVED":
            zone = GradientZone(data["zone"]) if data.get("zone") else None
            usage = (
                DimensionUsage.from_dict(data["dimension_usage"])
                if data.get("dimension_usage")
                else None
            )
            return cls(tag="APPROVED", zone=zone, dimension_usage=usage)
        elif tag == "HELD":
            return cls(
                tag="HELD",
                dimension=data.get("dimension"),
                current_usage=data.get("current_usage"),
                threshold=data.get("threshold"),
                hold_id=data.get("hold_id"),
            )
        elif tag == "BLOCKED":
            return cls(
                tag="BLOCKED",
                dimension=data.get("dimension"),
                detail=data.get("detail"),
                requested=data.get("requested"),
                available=data.get("available"),
            )
        raise ValueError(f"Unknown Verdict tag: {tag!r}")

# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""
EnvelopeAllocator and BudgetPolicy for the kaizen-agents orchestration layer.

EnvelopeAllocator decides allocation ratios for child agents within a parent
envelope. It supports both deterministic equal-split and LLM-assisted weighted
split based on task complexity analysis.

BudgetPolicy governs reserve percentages and reallocation strategy when child
agents approach or exhaust their budgets.

These are orchestration-layer constructs (they may use LLM judgment for weighted
splits). The underlying EnvelopeSplitter in the SDK is deterministic and performs
the actual envelope division.
"""

from __future__ import annotations

import enum
import logging
import math
from dataclasses import dataclass
from typing import Any, Optional

from kaizen.l3.envelope.errors import SplitError
from kaizen.l3.envelope.splitter import EnvelopeSplitter
from kaizen.l3.envelope.types import AllocationRequest as SdkAllocationRequest

from kaizen_agents.types import ConstraintEnvelope, GradientZone

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------


class ExhaustionAction(enum.Enum):
    """What to do when a child agent approaches its budget limit."""

    REALLOCATE = "reallocate"
    ESCALATE = "escalate"
    TERMINATE = "terminate"


@dataclass(frozen=True)
class Subtask:
    """A subtask description with complexity estimate for allocation planning."""

    child_id: str
    description: str
    complexity: float  # 0.0 to 1.0 relative complexity weight

    def __post_init__(self) -> None:
        if not self.child_id:
            raise ValueError("child_id must be a non-empty string")
        if not self.description:
            raise ValueError("description must be a non-empty string")
        if not math.isfinite(self.complexity):
            raise ValueError(f"complexity must be finite, got {self.complexity}")
        if self.complexity < 0.0:
            raise ValueError(f"complexity must be non-negative, got {self.complexity}")


@dataclass(frozen=True)
class AllocationRequest:
    """Per-child allocation ratios for depletable dimensions.

    Matches the spec definition from 01-envelope-extensions.md section 2.9.
    financial_ratio and temporal_ratio are fractions of the parent's budget
    (0.0 to 1.0). The sum of all allocations plus reserve must not exceed 1.0.
    """

    child_id: str
    financial_ratio: float
    temporal_ratio: float

    def __post_init__(self) -> None:
        _validate_ratio(self.financial_ratio, self.child_id, "financial_ratio")
        _validate_ratio(self.temporal_ratio, self.child_id, "temporal_ratio")
        if not self.child_id:
            raise ValueError("child_id must be a non-empty string")


@dataclass(frozen=True)
class SplitResult:
    """Result of an envelope allocation operation."""

    allocations: list[AllocationRequest]
    reserve_pct: float
    strategy: str  # "equal" or "weighted"


class AllocationError(Exception):
    """Raised when envelope allocation fails validation."""

    pass


# ---------------------------------------------------------------------------
# BudgetPolicy
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BudgetPolicy:
    """Governs reserve percentage and reallocation strategy for child agents.

    Attributes:
        reserve_pct: Fraction of parent budget kept as reserve (0.0 to 1.0).
            Default is 0.10 (10%).
        reallocation_enabled: Whether to redistribute unused budget from
            completed children to siblings that need it.
        exhaustion_action: What to do when a child approaches its budget limit.
            One of REALLOCATE, ESCALATE, or TERMINATE.
    """

    reserve_pct: float = 0.10
    reallocation_enabled: bool = True
    exhaustion_action: ExhaustionAction = ExhaustionAction.REALLOCATE

    def __post_init__(self) -> None:
        if not math.isfinite(self.reserve_pct):
            raise ValueError(f"reserve_pct must be finite, got {self.reserve_pct}")
        if self.reserve_pct < 0.0 or self.reserve_pct > 1.0:
            raise ValueError(f"reserve_pct must be between 0.0 and 1.0, got {self.reserve_pct}")
        if not isinstance(self.exhaustion_action, ExhaustionAction):
            raise ValueError(
                f"exhaustion_action must be an ExhaustionAction enum value, "
                f"got {self.exhaustion_action!r}"
            )

    def should_reallocate_on_exhaustion(self) -> bool:
        """Whether the policy calls for reallocation when a child runs low."""
        return self.reallocation_enabled and self.exhaustion_action == ExhaustionAction.REALLOCATE

    def should_escalate_on_exhaustion(self) -> bool:
        """Whether the policy calls for escalation when a child runs low."""
        return self.exhaustion_action == ExhaustionAction.ESCALATE

    def should_terminate_on_exhaustion(self) -> bool:
        """Whether the policy calls for termination when a child runs low."""
        return self.exhaustion_action == ExhaustionAction.TERMINATE


# ---------------------------------------------------------------------------
# EnvelopeAllocator
# ---------------------------------------------------------------------------


class EnvelopeAllocator:
    """Decides allocation ratios for child agents within a parent envelope.

    Supports two strategies:
    - **equal_split**: Deterministic, divides available budget equally among
      children. No LLM needed.
    - **weighted_split**: Uses task complexity estimates to assign proportional
      budgets. Can optionally use LLM for complexity analysis.

    Both strategies respect the configured BudgetPolicy reserve percentage.
    Both strategies validate that allocation ratios sum to <= 1.0 minus reserve.

    Usage:
        policy = BudgetPolicy(reserve_pct=0.10)
        allocator = EnvelopeAllocator(policy=policy)
        subtasks = [
            Subtask(child_id="research", description="Research topic", complexity=0.3),
            Subtask(child_id="write", description="Write report", complexity=0.7),
        ]
        result = allocator.weighted_split(subtasks)
    """

    def __init__(self, policy: Optional[BudgetPolicy] = None) -> None:
        self._policy = policy or BudgetPolicy()

    @property
    def policy(self) -> BudgetPolicy:
        """The budget policy governing this allocator."""
        return self._policy

    def equal_split(self, subtasks: list[Subtask]) -> SplitResult:
        """Divide budget equally among all subtasks, minus the reserve.

        Each child receives an equal fraction of the available (non-reserved)
        budget for both financial and temporal dimensions.

        Args:
            subtasks: List of subtasks to allocate budget across. Must be
                non-empty and contain unique child_ids.

        Returns:
            A SplitResult with equal allocation ratios.

        Raises:
            AllocationError: If subtasks list is empty, contains duplicate
                child_ids, or if the split would violate ratio constraints.
        """
        self._validate_subtasks(subtasks)

        n = len(subtasks)
        available = 1.0 - self._policy.reserve_pct
        ratio_per_child = available / n

        allocations = [
            AllocationRequest(
                child_id=task.child_id,
                financial_ratio=ratio_per_child,
                temporal_ratio=ratio_per_child,
            )
            for task in subtasks
        ]

        result = SplitResult(
            allocations=allocations,
            reserve_pct=self._policy.reserve_pct,
            strategy="equal",
        )
        _validate_allocation_sums(result)
        return result

    def weighted_split(self, subtasks: list[Subtask]) -> SplitResult:
        """Divide budget proportionally based on subtask complexity estimates.

        Each child receives a fraction of the available (non-reserved) budget
        proportional to its complexity weight relative to the total complexity.

        A subtask with complexity 0.7 in a set totaling 1.0 complexity would
        receive 70% of the available budget (after reserve).

        Args:
            subtasks: List of subtasks with complexity estimates. Must be
                non-empty, contain unique child_ids, and have a positive total
                complexity.

        Returns:
            A SplitResult with complexity-weighted allocation ratios.

        Raises:
            AllocationError: If subtasks list is empty, contains duplicate
                child_ids, total complexity is zero, or if the split would
                violate ratio constraints.
        """
        self._validate_subtasks(subtasks)

        total_complexity = sum(task.complexity for task in subtasks)
        if total_complexity <= 0.0:
            raise AllocationError(
                "Total complexity must be positive for weighted split. "
                "All subtasks have zero complexity -- use equal_split instead."
            )

        available = 1.0 - self._policy.reserve_pct

        allocations = []
        for task in subtasks:
            weight = task.complexity / total_complexity
            ratio = available * weight
            allocations.append(
                AllocationRequest(
                    child_id=task.child_id,
                    financial_ratio=ratio,
                    temporal_ratio=ratio,
                )
            )

        result = SplitResult(
            allocations=allocations,
            reserve_pct=self._policy.reserve_pct,
            strategy="weighted",
        )
        _validate_allocation_sums(result)
        return result

    def weighted_split_asymmetric(
        self,
        subtasks: list[Subtask],
        temporal_weights: Optional[dict[str, float]] = None,
    ) -> SplitResult:
        """Divide budget with different weights for financial vs temporal dimensions.

        Financial dimension uses the subtask complexity weights. Temporal dimension
        uses explicit temporal_weights if provided, otherwise falls back to the
        same complexity weights.

        This is useful when a subtask is financially expensive but time-cheap
        (e.g., a single expensive API call) or vice versa.

        Args:
            subtasks: List of subtasks with complexity estimates.
            temporal_weights: Optional mapping from child_id to temporal weight.
                If provided, must include an entry for every subtask child_id.
                Weights must be non-negative and finite.

        Returns:
            A SplitResult with asymmetric allocation ratios.

        Raises:
            AllocationError: If validation fails for any input.
        """
        self._validate_subtasks(subtasks)

        total_complexity = sum(task.complexity for task in subtasks)
        if total_complexity <= 0.0:
            raise AllocationError("Total complexity must be positive for weighted split.")

        available = 1.0 - self._policy.reserve_pct

        # Financial ratios from complexity
        financial_ratios: dict[str, float] = {}
        for task in subtasks:
            financial_ratios[task.child_id] = available * (task.complexity / total_complexity)

        # Temporal ratios from explicit weights or fallback to complexity
        if temporal_weights is not None:
            # Validate temporal weights
            for task in subtasks:
                if task.child_id not in temporal_weights:
                    raise AllocationError(
                        f"temporal_weights missing entry for child_id '{task.child_id}'"
                    )
            for child_id, weight in temporal_weights.items():
                if not math.isfinite(weight):
                    raise AllocationError(
                        f"temporal weight for '{child_id}' must be finite, got {weight}"
                    )
                if weight < 0.0:
                    raise AllocationError(
                        f"temporal weight for '{child_id}' must be non-negative, got {weight}"
                    )

            total_temporal = sum(temporal_weights[t.child_id] for t in subtasks)
            if total_temporal <= 0.0:
                raise AllocationError("Total temporal weight must be positive.")

            temporal_ratios: dict[str, float] = {}
            for task in subtasks:
                temporal_ratios[task.child_id] = available * (
                    temporal_weights[task.child_id] / total_temporal
                )
        else:
            temporal_ratios = dict(financial_ratios)

        allocations = [
            AllocationRequest(
                child_id=task.child_id,
                financial_ratio=financial_ratios[task.child_id],
                temporal_ratio=temporal_ratios[task.child_id],
            )
            for task in subtasks
        ]

        result = SplitResult(
            allocations=allocations,
            reserve_pct=self._policy.reserve_pct,
            strategy="weighted",
        )
        _validate_allocation_sums(result)
        return result

    def allocate_with_sdk(
        self,
        parent: ConstraintEnvelope,
        subtasks: list[Subtask],
    ) -> list[tuple[str, ConstraintEnvelope]]:
        """Allocate child envelopes from a parent using the SDK EnvelopeSplitter.

        Computes allocation ratios from subtask complexity (using weighted_split
        logic), converts the parent ConstraintEnvelope to SDK format, delegates
        to EnvelopeSplitter.split(), and converts the results back to local
        ConstraintEnvelope objects.

        This method bridges the orchestration-layer allocation logic with the
        SDK's deterministic envelope splitting, ensuring all three depletable
        dimensions (financial, temporal, operational/action_limit) are allocated.

        Args:
            parent: The parent ConstraintEnvelope to split among children.
            subtasks: List of subtasks with complexity estimates. Ratios are
                computed proportionally from complexity weights.

        Returns:
            List of (child_id, child_envelope) tuples, one per subtask.

        Raises:
            AllocationError: If subtasks are invalid (empty, duplicate IDs,
                zero total complexity) or if the SDK splitter rejects the
                allocation (e.g., ratio sum exceeds 1.0).
        """
        # Compute ratios using existing orchestration logic
        split_result = self.weighted_split(subtasks)

        # Convert parent envelope to SDK format (flat dict)
        sdk_parent = _envelope_to_sdk_parent(parent)

        # Create SDK AllocationRequest objects from our local ratios
        sdk_allocations = [
            SdkAllocationRequest(
                child_id=alloc.child_id,
                financial_ratio=alloc.financial_ratio,
                temporal_ratio=alloc.temporal_ratio,
            )
            for alloc in split_result.allocations
        ]

        # Delegate to SDK EnvelopeSplitter
        try:
            sdk_results = EnvelopeSplitter.split(
                parent=sdk_parent,
                allocations=sdk_allocations,
                reserve_pct=split_result.reserve_pct,
            )
        except SplitError as exc:
            raise AllocationError(f"SDK EnvelopeSplitter rejected the allocation: {exc}") from exc

        # Convert SDK results back to local ConstraintEnvelope objects
        return [
            (child_id, _sdk_result_to_envelope(child_dict, parent))
            for child_id, child_dict in sdk_results
        ]

    def _validate_subtasks(self, subtasks: list[Subtask]) -> None:
        """Validate the subtasks list for common errors.

        Args:
            subtasks: The list to validate.

        Raises:
            AllocationError: If the list is empty or contains duplicate child_ids.
        """
        if not subtasks:
            raise AllocationError("subtasks list must not be empty")

        child_ids = [task.child_id for task in subtasks]
        if len(child_ids) != len(set(child_ids)):
            duplicates = [cid for cid in child_ids if child_ids.count(cid) > 1]
            raise AllocationError(
                f"subtasks contain duplicate child_ids: {sorted(set(duplicates))}"
            )


# ---------------------------------------------------------------------------
# Module-level validation helpers
# ---------------------------------------------------------------------------


def _validate_ratio(value: float, child_id: str, field_name: str) -> None:
    """Validate a single allocation ratio value.

    Args:
        value: The ratio to validate.
        child_id: The child this ratio belongs to (for error messages).
        field_name: The field name (for error messages).

    Raises:
        ValueError: If the ratio is NaN, Inf, negative, or > 1.0.
    """
    if not math.isfinite(value):
        raise ValueError(f"{field_name} for '{child_id}' must be finite, got {value}")
    if value < 0.0:
        raise ValueError(f"{field_name} for '{child_id}' must be non-negative, got {value}")
    if value > 1.0:
        raise ValueError(f"{field_name} for '{child_id}' must be <= 1.0, got {value}")


def _validate_allocation_sums(result: SplitResult) -> None:
    """Validate that allocation ratios plus reserve do not exceed 1.0.

    Per spec INV-2 (Split Conservation): reserve_pct + sum(ratios) <= 1.0 for
    each depletable dimension. A small epsilon tolerance (1e-9) is applied to
    absorb floating-point rounding errors from ratio arithmetic.

    Args:
        result: The SplitResult to validate.

    Raises:
        AllocationError: If the sum of ratios plus reserve exceeds 1.0 in
            any dimension (beyond floating-point tolerance).
    """
    _EPSILON = 1e-9

    financial_sum = sum(a.financial_ratio for a in result.allocations)
    temporal_sum = sum(a.temporal_ratio for a in result.allocations)
    reserve = result.reserve_pct

    financial_total = reserve + financial_sum
    temporal_total = reserve + temporal_sum

    errors: list[str] = []

    if financial_total > 1.0 + _EPSILON:
        errors.append(
            f"financial dimension: reserve ({reserve:.4f}) + allocations "
            f"({financial_sum:.4f}) = {financial_total:.4f} exceeds 1.0"
        )

    if temporal_total > 1.0 + _EPSILON:
        errors.append(
            f"temporal dimension: reserve ({reserve:.4f}) + allocations "
            f"({temporal_sum:.4f}) = {temporal_total:.4f} exceeds 1.0"
        )

    if errors:
        raise AllocationError(
            "Allocation ratios violate split conservation (INV-2): " + "; ".join(errors)
        )


# ---------------------------------------------------------------------------
# SDK bridge helpers
# ---------------------------------------------------------------------------


def _envelope_to_sdk_parent(envelope: ConstraintEnvelope) -> dict[str, Any]:
    """Convert a local ConstraintEnvelope to the flat dict expected by SDK EnvelopeSplitter.

    The SDK EnvelopeSplitter expects a flat dict with keys:
        - financial_limit: float | None
        - temporal_limit_seconds: float | None
        - action_limit: int | None

    The local ConstraintEnvelope stores these in nested dimension dicts:
        - financial["limit"] -> financial_limit
        - temporal["limit_seconds"] -> temporal_limit_seconds
        - operational["action_limit"] -> action_limit

    Args:
        envelope: The local ConstraintEnvelope to convert.

    Returns:
        A flat dict suitable for EnvelopeSplitter.split(parent=...).
    """
    financial_limit = envelope.financial.get("limit")
    if financial_limit is not None:
        financial_limit = float(financial_limit)

    temporal_limit = envelope.temporal.get("limit_seconds")
    if temporal_limit is not None:
        temporal_limit = float(temporal_limit)

    action_limit = envelope.operational.get("action_limit")
    if action_limit is not None:
        action_limit = int(action_limit)

    return {
        "financial_limit": financial_limit,
        "temporal_limit_seconds": temporal_limit,
        "action_limit": action_limit,
    }


def _sdk_result_to_envelope(
    child_dict: dict[str, Any],
    parent: ConstraintEnvelope,
) -> ConstraintEnvelope:
    """Convert an SDK split result dict back to a local ConstraintEnvelope.

    The SDK returns flat dicts with financial_limit, temporal_limit_seconds,
    and action_limit. We reconstruct a ConstraintEnvelope inheriting the
    non-depletable dimensions (data_access, communication) from the parent
    and populating the depletable dimensions from the SDK result.

    The operational dimension's allowed/blocked lists are inherited from the
    parent (they are non-depletable), while action_limit is set from the
    SDK result.

    Args:
        child_dict: SDK result dict with financial_limit, temporal_limit_seconds,
            action_limit keys.
        parent: The parent ConstraintEnvelope from which non-depletable
            dimensions are inherited.

    Returns:
        A new ConstraintEnvelope for the child agent.
    """
    # Financial dimension
    child_financial: dict[str, Any] = dict(parent.financial)
    fin_limit = child_dict.get("financial_limit")
    if fin_limit is not None:
        child_financial["limit"] = fin_limit
    else:
        child_financial.pop("limit", None)

    # Temporal dimension
    child_temporal: dict[str, Any] = dict(parent.temporal)
    temp_limit = child_dict.get("temporal_limit_seconds")
    if temp_limit is not None:
        child_temporal["limit_seconds"] = temp_limit
    else:
        child_temporal.pop("limit_seconds", None)

    # Operational dimension — inherit allowed/blocked, set action_limit from SDK
    child_operational: dict[str, Any] = dict(parent.operational)
    action_limit = child_dict.get("action_limit")
    if action_limit is not None:
        child_operational["action_limit"] = action_limit
    else:
        child_operational.pop("action_limit", None)

    return ConstraintEnvelope(
        financial=child_financial,
        operational=child_operational,
        temporal=child_temporal,
        data_access=dict(parent.data_access),
        communication=dict(parent.communication),
    )

# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""L3 envelope error types.

Structured errors with variant tags and .details dicts for all envelope
operations: splitting, tracking, and enforcement.
"""

from __future__ import annotations

import logging
from typing import Any

__all__ = [
    "EnforcerError",
    "SplitError",
    "TrackerError",
]

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# SplitError
# ---------------------------------------------------------------------------


class SplitError(Exception):
    """Error during envelope splitting.

    Variants:
        RATIO_SUM_EXCEEDS_ONE, NEGATIVE_RATIO, NON_FINITE_RATIO,
        OVERRIDE_NOT_TIGHTER, RESERVE_INVALID, EMPTY_ALLOCATIONS,
        PARENT_DIMENSION_UNBOUNDED

    Carries structured .details dict and optionally .all_errors list
    when multiple validation errors are collected.
    """

    def __init__(
        self,
        message: str,
        *,
        variant: str,
        details: dict[str, Any] | None = None,
        all_errors: list[dict[str, Any]] | None = None,
    ) -> None:
        self.variant = variant
        self.details = details or {}
        self.all_errors = all_errors or [{"variant": variant, **(details or {})}]
        super().__init__(f"SplitError({variant}): {message}")

    # --- Factory methods ---

    @classmethod
    def ratio_sum_exceeds_one(cls, dimension: str, total: float) -> SplitError:
        return cls(
            f"Sum of ratios for dimension '{dimension}' is {total}, exceeds 1.0",
            variant="RATIO_SUM_EXCEEDS_ONE",
            details={"dimension": dimension, "total": total},
        )

    @classmethod
    def negative_ratio(cls, child_id: str, dimension: str, value: float) -> SplitError:
        return cls(
            f"Negative ratio {value} for child '{child_id}' dimension '{dimension}'",
            variant="NEGATIVE_RATIO",
            details={"child_id": child_id, "dimension": dimension, "value": value},
        )

    @classmethod
    def non_finite_ratio(
        cls, child_id: str, dimension: str, value: float
    ) -> SplitError:
        return cls(
            f"Non-finite ratio {value} for child '{child_id}' dimension '{dimension}'",
            variant="NON_FINITE_RATIO",
            details={"child_id": child_id, "dimension": dimension, "value": value},
        )

    @classmethod
    def override_not_tighter(cls, child_id: str, dimension: str) -> SplitError:
        return cls(
            f"Override for child '{child_id}' dimension '{dimension}' "
            f"is not tighter than parent",
            variant="OVERRIDE_NOT_TIGHTER",
            details={"child_id": child_id, "dimension": dimension},
        )

    @classmethod
    def reserve_invalid(cls, value: float) -> SplitError:
        return cls(
            f"Reserve percentage {value} is invalid (must be 0.0-1.0, finite)",
            variant="RESERVE_INVALID",
            details={"value": value},
        )

    @classmethod
    def empty_allocations(cls) -> SplitError:
        return cls(
            "At least one allocation is required",
            variant="EMPTY_ALLOCATIONS",
            details={},
        )

    @classmethod
    def parent_dimension_unbounded(cls, dimension: str) -> SplitError:
        return cls(
            f"Cannot split a ratio of unbounded dimension '{dimension}'",
            variant="PARENT_DIMENSION_UNBOUNDED",
            details={"dimension": dimension},
        )

    @classmethod
    def aggregate(cls, errors: list[SplitError]) -> SplitError:
        """Create an aggregate error from multiple SplitErrors.

        The first error's variant is used as the primary variant.
        All errors are collected in .all_errors.
        """
        if len(errors) == 1:
            return errors[0]
        all_errs: list[dict[str, Any]] = []
        for e in errors:
            all_errs.extend(e.all_errors)
        msg = "; ".join(str(e) for e in errors)
        return cls(
            msg,
            variant=errors[0].variant,
            details=errors[0].details,
            all_errors=all_errs,
        )


# ---------------------------------------------------------------------------
# TrackerError
# ---------------------------------------------------------------------------


class TrackerError(Exception):
    """Error during envelope tracking.

    Variants:
        InvalidCost, UnknownDimension, BudgetExceeded, DuplicateChild,
        UnknownChild, ConsumedExceedsAllocated, InvalidAmount
    """

    def __init__(
        self,
        message: str,
        *,
        variant: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.variant = variant
        self.details = details or {}
        super().__init__(f"TrackerError({variant}): {message}")

    # --- Factory methods ---

    @classmethod
    def invalid_cost(cls, reason: str, value: float) -> TrackerError:
        return cls(
            f"Invalid cost: {reason}",
            variant="InvalidCost",
            details={"reason": reason, "value": value},
        )

    @classmethod
    def unknown_dimension(cls, dimension: str) -> TrackerError:
        return cls(
            f"Unknown dimension: {dimension}",
            variant="UnknownDimension",
            details={"dimension": dimension},
        )

    @classmethod
    def budget_exceeded(
        cls, dimension: str, requested: float, available: float
    ) -> TrackerError:
        return cls(
            f"Budget exceeded for dimension '{dimension}': "
            f"requested={requested}, available={available}",
            variant="BudgetExceeded",
            details={
                "dimension": dimension,
                "requested": requested,
                "available": available,
            },
        )

    @classmethod
    def duplicate_child(cls, child_id: str) -> TrackerError:
        return cls(
            f"Duplicate child allocation: {child_id}",
            variant="DuplicateChild",
            details={"child_id": child_id},
        )

    @classmethod
    def unknown_child(cls, child_id: str) -> TrackerError:
        return cls(
            f"Unknown child: {child_id}",
            variant="UnknownChild",
            details={"child_id": child_id},
        )

    @classmethod
    def consumed_exceeds_allocated(
        cls, child_id: str, consumed: float, allocated: float
    ) -> TrackerError:
        return cls(
            f"Child '{child_id}' consumed {consumed} exceeds allocated {allocated}",
            variant="ConsumedExceedsAllocated",
            details={
                "child_id": child_id,
                "consumed": consumed,
                "allocated": allocated,
            },
        )

    @classmethod
    def invalid_amount(cls, reason: str, value: float) -> TrackerError:
        return cls(
            f"Invalid amount: {reason}",
            variant="InvalidAmount",
            details={"reason": reason, "value": value},
        )


# ---------------------------------------------------------------------------
# EnforcerError
# ---------------------------------------------------------------------------


class EnforcerError(Exception):
    """Error during envelope enforcement.

    Variants:
        InvalidContext, ActionNotApproved
    """

    def __init__(
        self,
        message: str,
        *,
        variant: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.variant = variant
        self.details = details or {}
        super().__init__(f"EnforcerError({variant}): {message}")

    @classmethod
    def invalid_context(cls, reason: str) -> EnforcerError:
        return cls(
            f"Invalid enforcement context: {reason}",
            variant="InvalidContext",
            details={"reason": reason},
        )

    @classmethod
    def action_not_approved(cls, action: str) -> EnforcerError:
        return cls(
            f"Action '{action}' was not approved via check_action()",
            variant="ActionNotApproved",
            details={"action": action},
        )

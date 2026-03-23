# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""EnvelopeSplitter — stateless pure functions for dividing parent envelopes.

Divides a parent envelope into child envelopes according to allocation ratios.
Enforces INV-2 (split conservation), INV-6 (child tighter than parent),
and INV-7 (finite arithmetic only).

Envelope representation: plain dicts with keys:
    - financial_limit: float | None
    - temporal_limit_seconds: float | None
    - action_limit: int | None
"""

from __future__ import annotations

import logging
import math
from typing import Any

from kaizen.l3.envelope.errors import SplitError
from kaizen.l3.envelope.types import AllocationRequest

__all__ = ["EnvelopeSplitter"]

logger = logging.getLogger(__name__)


class EnvelopeSplitter:
    """Stateless envelope splitting operations.

    All methods are pure functions (class methods / static methods).
    No mutable state.
    """

    @staticmethod
    def split(
        parent: dict[str, Any],
        allocations: list[AllocationRequest],
        reserve_pct: float,
    ) -> list[tuple[str, dict[str, Any]]]:
        """Divide a parent envelope into child envelopes.

        Args:
            parent: Parent envelope dict with financial_limit,
                    temporal_limit_seconds, action_limit.
            allocations: List of AllocationRequest, one per child.
            reserve_pct: Fraction of parent budget to keep as reserve (0.0-1.0).

        Returns:
            List of (child_id, child_envelope) tuples.

        Raises:
            SplitError: With all validation errors (not just the first).
        """
        errors = EnvelopeSplitter._validate(parent, allocations, reserve_pct)
        if errors:
            raise SplitError.aggregate(errors)

        # Build child envelopes
        result: list[tuple[str, dict[str, Any]]] = []
        for alloc in allocations:
            child_env: dict[str, Any] = {}

            # Financial dimension
            fin_limit = parent.get("financial_limit")
            if fin_limit is not None:
                child_env["financial_limit"] = fin_limit * alloc.financial_ratio
            else:
                child_env["financial_limit"] = None

            # Temporal dimension
            temp_limit = parent.get("temporal_limit_seconds")
            if temp_limit is not None:
                child_env["temporal_limit_seconds"] = temp_limit * alloc.temporal_ratio
            else:
                child_env["temporal_limit_seconds"] = None

            # Action limit — proportional by financial_ratio
            action_limit = parent.get("action_limit")
            if action_limit is not None:
                child_env["action_limit"] = int(action_limit * alloc.financial_ratio)
            else:
                child_env["action_limit"] = None

            result.append((alloc.child_id, child_env))

        return result

    @staticmethod
    def validate_split(
        parent: dict[str, Any],
        allocations: list[AllocationRequest],
        reserve_pct: float,
    ) -> list[dict[str, Any]] | None:
        """Validate a split without creating envelopes.

        Args:
            parent: Parent envelope dict.
            allocations: List of AllocationRequest.
            reserve_pct: Reserve percentage.

        Returns:
            None if valid, or list of error detail dicts if invalid.
        """
        errors = EnvelopeSplitter._validate(parent, allocations, reserve_pct)
        if not errors:
            return None
        result: list[dict[str, Any]] = []
        for err in errors:
            result.extend(err.all_errors)
        return result

    @staticmethod
    def _validate(
        parent: dict[str, Any],
        allocations: list[AllocationRequest],
        reserve_pct: float,
    ) -> list[SplitError]:
        """Collect all validation errors.

        Returns ALL errors, not just the first (spec requirement).
        """
        errors: list[SplitError] = []

        # Validate reserve
        if not math.isfinite(reserve_pct) or reserve_pct < 0.0 or reserve_pct > 1.0:
            errors.append(SplitError.reserve_invalid(value=reserve_pct))

        # Validate non-empty allocations
        if not allocations:
            errors.append(SplitError.empty_allocations())

        # Check for unbounded dimensions being split by ratio
        fin_limit = parent.get("financial_limit")
        temp_limit = parent.get("temporal_limit_seconds")

        has_financial_ratio = any(a.financial_ratio > 0 for a in allocations)
        has_temporal_ratio = any(a.temporal_ratio > 0 for a in allocations)

        if fin_limit is None and has_financial_ratio:
            errors.append(SplitError.parent_dimension_unbounded(dimension="financial"))

        if temp_limit is None and has_temporal_ratio:
            errors.append(SplitError.parent_dimension_unbounded(dimension="temporal"))

        # Validate ratio sums (only if reserve is valid).
        # A small epsilon tolerance (1e-9) absorbs floating-point rounding
        # errors from ratio arithmetic (e.g., 0.54 + 0.36 = 0.9000000000000001).
        _EPSILON = 1e-9
        if math.isfinite(reserve_pct) and reserve_pct >= 0.0:
            # Financial ratio sum
            if allocations and fin_limit is not None:
                fin_sum = sum(a.financial_ratio for a in allocations)
                if reserve_pct + fin_sum > 1.0 + _EPSILON:
                    errors.append(
                        SplitError.ratio_sum_exceeds_one(
                            dimension="financial",
                            total=reserve_pct + fin_sum,
                        )
                    )

            # Temporal ratio sum
            if allocations and temp_limit is not None:
                temp_sum = sum(a.temporal_ratio for a in allocations)
                if reserve_pct + temp_sum > 1.0 + _EPSILON:
                    errors.append(
                        SplitError.ratio_sum_exceeds_one(
                            dimension="temporal",
                            total=reserve_pct + temp_sum,
                        )
                    )

        return errors

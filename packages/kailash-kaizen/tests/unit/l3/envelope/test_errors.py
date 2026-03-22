# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for L3 envelope error types.

Covers:
- SplitError variant construction and structured details
- TrackerError variant construction and structured details
- EnforcerError variant construction and structured details
- All errors carry .details dict
"""

from __future__ import annotations

import pytest


class TestSplitError:
    """SplitError: structured error with variant tag and details."""

    def test_ratio_sum_exceeds_one(self):
        from kaizen.l3.envelope.errors import SplitError

        err = SplitError.ratio_sum_exceeds_one(dimension="financial", total=1.3)
        assert "RATIO_SUM_EXCEEDS_ONE" in str(err)
        assert err.details["dimension"] == "financial"
        assert err.details["total"] == 1.3

    def test_negative_ratio(self):
        from kaizen.l3.envelope.errors import SplitError

        err = SplitError.negative_ratio(
            child_id="child-001", dimension="financial", value=-0.1
        )
        assert "NEGATIVE_RATIO" in str(err)
        assert err.details["child_id"] == "child-001"
        assert err.details["value"] == -0.1

    def test_non_finite_ratio(self):
        from kaizen.l3.envelope.errors import SplitError

        err = SplitError.non_finite_ratio(
            child_id="child-001", dimension="financial", value=float("nan")
        )
        assert "NON_FINITE_RATIO" in str(err)
        assert err.details["child_id"] == "child-001"

    def test_override_not_tighter(self):
        from kaizen.l3.envelope.errors import SplitError

        err = SplitError.override_not_tighter(
            child_id="child-001", dimension="data_access"
        )
        assert "OVERRIDE_NOT_TIGHTER" in str(err)
        assert err.details["dimension"] == "data_access"

    def test_reserve_invalid(self):
        from kaizen.l3.envelope.errors import SplitError

        err = SplitError.reserve_invalid(value=1.5)
        assert "RESERVE_INVALID" in str(err)
        assert err.details["value"] == 1.5

    def test_empty_allocations(self):
        from kaizen.l3.envelope.errors import SplitError

        err = SplitError.empty_allocations()
        assert "EMPTY_ALLOCATIONS" in str(err)

    def test_parent_dimension_unbounded(self):
        from kaizen.l3.envelope.errors import SplitError

        err = SplitError.parent_dimension_unbounded(dimension="financial")
        assert "PARENT_DIMENSION_UNBOUNDED" in str(err)
        assert err.details["dimension"] == "financial"

    def test_inherits_from_exception(self):
        from kaizen.l3.envelope.errors import SplitError

        err = SplitError.empty_allocations()
        assert isinstance(err, Exception)


class TestTrackerError:
    """TrackerError: structured error with variant tag and details."""

    def test_invalid_cost(self):
        from kaizen.l3.envelope.errors import TrackerError

        err = TrackerError.invalid_cost(reason="cost is NaN", value=float("nan"))
        assert "InvalidCost" in str(err)
        assert err.details["reason"] == "cost is NaN"

    def test_unknown_dimension(self):
        from kaizen.l3.envelope.errors import TrackerError

        err = TrackerError.unknown_dimension(dimension="unknown_dim")
        assert "UnknownDimension" in str(err)
        assert err.details["dimension"] == "unknown_dim"

    def test_budget_exceeded(self):
        from kaizen.l3.envelope.errors import TrackerError

        err = TrackerError.budget_exceeded(
            dimension="financial", requested=500.0, available=100.0
        )
        assert "BudgetExceeded" in str(err)
        assert err.details["requested"] == 500.0
        assert err.details["available"] == 100.0

    def test_duplicate_child(self):
        from kaizen.l3.envelope.errors import TrackerError

        err = TrackerError.duplicate_child(child_id="child-001")
        assert "DuplicateChild" in str(err)
        assert err.details["child_id"] == "child-001"

    def test_unknown_child(self):
        from kaizen.l3.envelope.errors import TrackerError

        err = TrackerError.unknown_child(child_id="child-999")
        assert "UnknownChild" in str(err)

    def test_consumed_exceeds_allocated(self):
        from kaizen.l3.envelope.errors import TrackerError

        err = TrackerError.consumed_exceeds_allocated(
            child_id="child-001", consumed=600.0, allocated=500.0
        )
        assert "ConsumedExceedsAllocated" in str(err)
        assert err.details["consumed"] == 600.0
        assert err.details["allocated"] == 500.0

    def test_invalid_amount(self):
        from kaizen.l3.envelope.errors import TrackerError

        err = TrackerError.invalid_amount(reason="amount is negative", value=-1.0)
        assert "InvalidAmount" in str(err)

    def test_inherits_from_exception(self):
        from kaizen.l3.envelope.errors import TrackerError

        err = TrackerError.invalid_cost(reason="bad", value=0.0)
        assert isinstance(err, Exception)


class TestEnforcerError:
    """EnforcerError: structured error with variant tag and details."""

    def test_invalid_context(self):
        from kaizen.l3.envelope.errors import EnforcerError

        err = EnforcerError.invalid_context(reason="estimated_cost is NaN")
        assert "InvalidContext" in str(err)
        assert err.details["reason"] == "estimated_cost is NaN"

    def test_action_not_approved(self):
        from kaizen.l3.envelope.errors import EnforcerError

        err = EnforcerError.action_not_approved(action="web_search")
        assert "ActionNotApproved" in str(err)
        assert err.details["action"] == "web_search"

    def test_inherits_from_exception(self):
        from kaizen.l3.envelope.errors import EnforcerError

        err = EnforcerError.invalid_context(reason="test")
        assert isinstance(err, Exception)

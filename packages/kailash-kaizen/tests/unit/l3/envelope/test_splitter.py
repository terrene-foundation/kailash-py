# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for EnvelopeSplitter.

Covers:
- TV-2: Split and reclaim basic flow
- TV-3: Rejection of invalid splits
- TV-4: NaN / boundary condition handling
- INV-2: Split conservation
- INV-6: Child tighter than parent
- INV-7: Finite arithmetic only
"""

from __future__ import annotations

import math

import pytest


def _make_parent_envelope(
    financial_limit: float | None = 1000.0,
    temporal_limit_seconds: float | None = 3600.0,
    action_limit: int | None = 100,
) -> dict:
    """Create a parent envelope dict for testing."""
    return {
        "financial_limit": financial_limit,
        "temporal_limit_seconds": temporal_limit_seconds,
        "action_limit": action_limit,
    }


class TestEnvelopeSplitterSplit:
    """EnvelopeSplitter.split() — pure function, stateless."""

    def test_basic_two_child_split(self):
        """TV-2: Basic split into two children with reserve."""
        from kaizen.l3.envelope.splitter import EnvelopeSplitter
        from kaizen.l3.envelope.types import AllocationRequest

        parent = _make_parent_envelope(
            financial_limit=1000.0, temporal_limit_seconds=3600.0
        )
        allocations = [
            AllocationRequest(child_id="a", financial_ratio=0.3, temporal_ratio=0.3),
            AllocationRequest(child_id="b", financial_ratio=0.5, temporal_ratio=0.5),
        ]

        result = EnvelopeSplitter.split(parent, allocations, reserve_pct=0.1)

        assert len(result) == 2
        # Check child "a"
        child_a = dict(result)["a"]
        assert child_a["financial_limit"] == pytest.approx(300.0)
        assert child_a["temporal_limit_seconds"] == pytest.approx(1080.0)

        # Check child "b"
        child_b = dict(result)["b"]
        assert child_b["financial_limit"] == pytest.approx(500.0)
        assert child_b["temporal_limit_seconds"] == pytest.approx(1800.0)

    def test_exact_exhaustion_no_reserve(self):
        """Ratios summing to exactly 1.0 with 0% reserve is valid."""
        from kaizen.l3.envelope.splitter import EnvelopeSplitter
        from kaizen.l3.envelope.types import AllocationRequest

        parent = _make_parent_envelope(financial_limit=1000.0)
        allocations = [
            AllocationRequest(child_id="a", financial_ratio=0.5, temporal_ratio=0.5),
            AllocationRequest(child_id="b", financial_ratio=0.5, temporal_ratio=0.5),
        ]

        result = EnvelopeSplitter.split(parent, allocations, reserve_pct=0.0)
        assert len(result) == 2
        child_a = dict(result)["a"]
        child_b = dict(result)["b"]
        assert child_a["financial_limit"] + child_b["financial_limit"] == pytest.approx(
            1000.0
        )

    def test_single_child_full_allocation(self):
        """Single child can take up to 1.0 - reserve."""
        from kaizen.l3.envelope.splitter import EnvelopeSplitter
        from kaizen.l3.envelope.types import AllocationRequest

        parent = _make_parent_envelope(
            financial_limit=1000.0, temporal_limit_seconds=3600.0
        )
        allocations = [
            AllocationRequest(child_id="only", financial_ratio=0.9, temporal_ratio=0.9),
        ]

        result = EnvelopeSplitter.split(parent, allocations, reserve_pct=0.1)
        assert len(result) == 1
        child = dict(result)["only"]
        assert child["financial_limit"] == pytest.approx(900.0)

    def test_action_limit_split(self):
        """Action limits are split proportionally by financial_ratio."""
        from kaizen.l3.envelope.splitter import EnvelopeSplitter
        from kaizen.l3.envelope.types import AllocationRequest

        parent = _make_parent_envelope(
            financial_limit=1000.0,
            temporal_limit_seconds=3600.0,
            action_limit=100,
        )
        allocations = [
            AllocationRequest(child_id="a", financial_ratio=0.3, temporal_ratio=0.3),
            AllocationRequest(child_id="b", financial_ratio=0.5, temporal_ratio=0.5),
        ]

        result = EnvelopeSplitter.split(parent, allocations, reserve_pct=0.0)
        child_a = dict(result)["a"]
        child_b = dict(result)["b"]
        # Action limits split by financial_ratio
        assert child_a["action_limit"] == 30
        assert child_b["action_limit"] == 50


class TestEnvelopeSplitterRejection:
    """TV-3: EnvelopeSplitter rejects invalid splits."""

    def test_rejects_ratio_sum_exceeds_one(self):
        """INV-2: Sum of ratios + reserve > 1.0 is rejected."""
        from kaizen.l3.envelope.errors import SplitError
        from kaizen.l3.envelope.splitter import EnvelopeSplitter
        from kaizen.l3.envelope.types import AllocationRequest

        parent = _make_parent_envelope(financial_limit=1000.0)
        allocations = [
            AllocationRequest(child_id="a", financial_ratio=0.6, temporal_ratio=0.3),
            AllocationRequest(child_id="b", financial_ratio=0.5, temporal_ratio=0.3),
        ]

        with pytest.raises(SplitError) as exc_info:
            EnvelopeSplitter.split(parent, allocations, reserve_pct=0.0)
        assert "RATIO_SUM_EXCEEDS_ONE" in str(exc_info.value)

    def test_rejects_ratio_sum_with_reserve(self):
        """Ratios sum to 0.9, but with 20% reserve total is 1.1."""
        from kaizen.l3.envelope.errors import SplitError
        from kaizen.l3.envelope.splitter import EnvelopeSplitter
        from kaizen.l3.envelope.types import AllocationRequest

        parent = _make_parent_envelope(financial_limit=1000.0)
        allocations = [
            AllocationRequest(child_id="a", financial_ratio=0.5, temporal_ratio=0.3),
            AllocationRequest(child_id="b", financial_ratio=0.4, temporal_ratio=0.3),
        ]

        with pytest.raises(SplitError) as exc_info:
            EnvelopeSplitter.split(parent, allocations, reserve_pct=0.2)
        assert "RATIO_SUM_EXCEEDS_ONE" in str(exc_info.value)

    def test_rejects_empty_allocations(self):
        """At least one child required."""
        from kaizen.l3.envelope.errors import SplitError
        from kaizen.l3.envelope.splitter import EnvelopeSplitter

        parent = _make_parent_envelope()
        with pytest.raises(SplitError) as exc_info:
            EnvelopeSplitter.split(parent, [], reserve_pct=0.0)
        assert "EMPTY_ALLOCATIONS" in str(exc_info.value)

    def test_rejects_unbounded_financial_split(self):
        """Cannot split a ratio of an unbounded dimension."""
        from kaizen.l3.envelope.errors import SplitError
        from kaizen.l3.envelope.splitter import EnvelopeSplitter
        from kaizen.l3.envelope.types import AllocationRequest

        parent = _make_parent_envelope(financial_limit=None)
        allocations = [
            AllocationRequest(child_id="a", financial_ratio=0.5, temporal_ratio=0.3),
        ]

        with pytest.raises(SplitError) as exc_info:
            EnvelopeSplitter.split(parent, allocations, reserve_pct=0.0)
        assert "PARENT_DIMENSION_UNBOUNDED" in str(exc_info.value)

    def test_rejects_invalid_reserve(self):
        """Reserve must be 0.0-1.0."""
        from kaizen.l3.envelope.errors import SplitError
        from kaizen.l3.envelope.splitter import EnvelopeSplitter
        from kaizen.l3.envelope.types import AllocationRequest

        parent = _make_parent_envelope()
        allocations = [
            AllocationRequest(child_id="a", financial_ratio=0.5, temporal_ratio=0.5),
        ]

        with pytest.raises(SplitError) as exc_info:
            EnvelopeSplitter.split(parent, allocations, reserve_pct=-0.1)
        assert "RESERVE_INVALID" in str(exc_info.value)

    def test_rejects_reserve_above_one(self):
        from kaizen.l3.envelope.errors import SplitError
        from kaizen.l3.envelope.splitter import EnvelopeSplitter
        from kaizen.l3.envelope.types import AllocationRequest

        parent = _make_parent_envelope()
        allocations = [
            AllocationRequest(child_id="a", financial_ratio=0.1, temporal_ratio=0.1),
        ]

        with pytest.raises(SplitError) as exc_info:
            EnvelopeSplitter.split(parent, allocations, reserve_pct=1.1)
        assert "RESERVE_INVALID" in str(exc_info.value)

    def test_collects_all_errors(self):
        """Returns ALL errors, not just the first."""
        from kaizen.l3.envelope.errors import SplitError
        from kaizen.l3.envelope.splitter import EnvelopeSplitter

        parent = _make_parent_envelope(
            financial_limit=None, temporal_limit_seconds=None
        )
        # Empty allocations AND reserve invalid
        with pytest.raises(SplitError) as exc_info:
            EnvelopeSplitter.split(parent, [], reserve_pct=-0.5)
        # Should mention multiple problems
        err = exc_info.value
        assert len(err.all_errors) >= 2


class TestEnvelopeSplitterNaN:
    """TV-4: NaN/Inf boundary conditions."""

    def test_rejects_nan_reserve(self):
        from kaizen.l3.envelope.errors import SplitError
        from kaizen.l3.envelope.splitter import EnvelopeSplitter
        from kaizen.l3.envelope.types import AllocationRequest

        parent = _make_parent_envelope()
        allocations = [
            AllocationRequest(child_id="a", financial_ratio=0.5, temporal_ratio=0.5),
        ]
        with pytest.raises(SplitError) as exc_info:
            EnvelopeSplitter.split(parent, allocations, reserve_pct=float("nan"))
        assert "RESERVE_INVALID" in str(exc_info.value)

    def test_rejects_inf_reserve(self):
        from kaizen.l3.envelope.errors import SplitError
        from kaizen.l3.envelope.splitter import EnvelopeSplitter
        from kaizen.l3.envelope.types import AllocationRequest

        parent = _make_parent_envelope()
        allocations = [
            AllocationRequest(child_id="a", financial_ratio=0.5, temporal_ratio=0.5),
        ]
        with pytest.raises(SplitError) as exc_info:
            EnvelopeSplitter.split(parent, allocations, reserve_pct=float("inf"))
        assert "RESERVE_INVALID" in str(exc_info.value)


class TestEnvelopeSplitterValidateSplit:
    """validate_split() — pure validation, no envelope creation."""

    def test_valid_split_returns_none(self):
        """A valid split returns no errors."""
        from kaizen.l3.envelope.splitter import EnvelopeSplitter
        from kaizen.l3.envelope.types import AllocationRequest

        parent = _make_parent_envelope()
        allocations = [
            AllocationRequest(child_id="a", financial_ratio=0.3, temporal_ratio=0.3),
        ]
        errors = EnvelopeSplitter.validate_split(parent, allocations, reserve_pct=0.1)
        assert errors is None or errors == []

    def test_invalid_split_returns_errors(self):
        """An invalid split returns a list of error details."""
        from kaizen.l3.envelope.splitter import EnvelopeSplitter

        parent = _make_parent_envelope(financial_limit=None)
        errors = EnvelopeSplitter.validate_split(parent, [], reserve_pct=-0.5)
        assert errors is not None
        assert len(errors) >= 2

# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tests for L3-002: ScopedContext types (DataClassification, ContextValue, MergeResult)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from kaizen.l3.context.types import (
    ClassificationExceedsClearance,
    ClearanceExceedsParent,
    ConflictResolution,
    ContextError,
    ContextValue,
    DataClassification,
    MergeConflict,
    MergeResult,
    NotAChild,
    ProjectionNotSubset,
    WriteProjectionViolation,
)


# ---------------------------------------------------------------------------
# DataClassification
# ---------------------------------------------------------------------------


class TestDataClassification:
    """DataClassification: int-backed enum with 5 levels, numeric ordering."""

    def test_five_levels_exist(self):
        assert DataClassification.PUBLIC.value == 0
        assert DataClassification.RESTRICTED.value == 1
        assert DataClassification.CONFIDENTIAL.value == 2
        assert DataClassification.SECRET.value == 3
        assert DataClassification.TOP_SECRET.value == 4

    def test_total_count(self):
        assert len(DataClassification) == 5

    def test_ordering_via_value(self):
        """Ordering is numeric: PUBLIC < RESTRICTED < ... < TOP_SECRET."""
        assert DataClassification.PUBLIC.value < DataClassification.RESTRICTED.value
        assert (
            DataClassification.RESTRICTED.value < DataClassification.CONFIDENTIAL.value
        )
        assert DataClassification.CONFIDENTIAL.value < DataClassification.SECRET.value
        assert DataClassification.SECRET.value < DataClassification.TOP_SECRET.value

    def test_comparison_operators(self):
        """Direct comparison operators work on the enum values."""
        # Verify we can compare: clearance <= parent_clearance
        assert (
            DataClassification.RESTRICTED.value <= DataClassification.CONFIDENTIAL.value
        )
        assert DataClassification.TOP_SECRET.value >= DataClassification.SECRET.value
        assert not (
            DataClassification.SECRET.value <= DataClassification.RESTRICTED.value
        )


# ---------------------------------------------------------------------------
# ConflictResolution
# ---------------------------------------------------------------------------


class TestConflictResolution:
    def test_variants(self):
        assert ConflictResolution.CHILD_WINS.value == "child_wins"
        assert ConflictResolution.PARENT_WINS.value == "parent_wins"
        assert ConflictResolution.SKIPPED.value == "skipped"

    def test_str_backed(self):
        assert isinstance(ConflictResolution.CHILD_WINS.value, str)


# ---------------------------------------------------------------------------
# ContextValue
# ---------------------------------------------------------------------------


class TestContextValue:
    def test_construction(self):
        now = datetime.now(UTC)
        cv = ContextValue(
            value="hello",
            written_by="agent-001",
            updated_at=now,
            classification=DataClassification.PUBLIC,
        )
        assert cv.value == "hello"
        assert cv.written_by == "agent-001"
        assert cv.updated_at == now
        assert cv.classification == DataClassification.PUBLIC

    def test_frozen(self):
        """ContextValue is a frozen (immutable) dataclass."""
        now = datetime.now(UTC)
        cv = ContextValue(
            value="data",
            written_by="agent-001",
            updated_at=now,
            classification=DataClassification.RESTRICTED,
        )
        with pytest.raises(AttributeError):
            cv.value = "changed"  # type: ignore[misc]

    def test_to_dict(self):
        now = datetime.now(UTC)
        cv = ContextValue(
            value={"nested": True},
            written_by="agent-001",
            updated_at=now,
            classification=DataClassification.CONFIDENTIAL,
        )
        d = cv.to_dict()
        assert d["value"] == {"nested": True}
        assert d["written_by"] == "agent-001"
        assert d["updated_at"] == now.isoformat()
        assert d["classification"] == "CONFIDENTIAL"

    def test_from_dict(self):
        now = datetime.now(UTC)
        d = {
            "value": 42,
            "written_by": "agent-002",
            "updated_at": now.isoformat(),
            "classification": "RESTRICTED",
        }
        cv = ContextValue.from_dict(d)
        assert cv.value == 42
        assert cv.written_by == "agent-002"
        assert cv.classification == DataClassification.RESTRICTED


# ---------------------------------------------------------------------------
# MergeConflict
# ---------------------------------------------------------------------------


class TestMergeConflict:
    def test_construction(self):
        now = datetime.now(UTC)
        mc = MergeConflict(
            key="results.output",
            parent_value_updated_at=now,
            child_value_updated_at=now,
            resolution=ConflictResolution.CHILD_WINS,
        )
        assert mc.key == "results.output"
        assert mc.resolution == ConflictResolution.CHILD_WINS

    def test_frozen(self):
        now = datetime.now(UTC)
        mc = MergeConflict(
            key="k",
            parent_value_updated_at=now,
            child_value_updated_at=now,
            resolution=ConflictResolution.PARENT_WINS,
        )
        with pytest.raises(AttributeError):
            mc.key = "changed"  # type: ignore[misc]

    def test_to_dict(self):
        now = datetime.now(UTC)
        mc = MergeConflict(
            key="k",
            parent_value_updated_at=now,
            child_value_updated_at=now,
            resolution=ConflictResolution.SKIPPED,
        )
        d = mc.to_dict()
        assert d["key"] == "k"
        assert d["resolution"] == "skipped"


# ---------------------------------------------------------------------------
# MergeResult
# ---------------------------------------------------------------------------


class TestMergeResult:
    def test_construction(self):
        mr = MergeResult(merged_keys=["a", "b"], skipped_keys=["c"], conflicts=[])
        assert mr.merged_keys == ["a", "b"]
        assert mr.skipped_keys == ["c"]
        assert mr.conflicts == []

    def test_frozen(self):
        mr = MergeResult(merged_keys=[], skipped_keys=[], conflicts=[])
        with pytest.raises(AttributeError):
            mr.merged_keys = ["x"]  # type: ignore[misc]

    def test_to_dict(self):
        mr = MergeResult(merged_keys=["a"], skipped_keys=[], conflicts=[])
        d = mr.to_dict()
        assert d["merged_keys"] == ["a"]
        assert d["skipped_keys"] == []
        assert d["conflicts"] == []


# ---------------------------------------------------------------------------
# Error types
# ---------------------------------------------------------------------------


class TestErrorTypes:
    """All errors inherit from ContextError and carry structured details."""

    def test_context_error_base(self):
        err = ContextError("base error", details={"key": "val"})
        assert str(err) == "base error"
        assert err.details == {"key": "val"}

    def test_projection_not_subset(self):
        err = ProjectionNotSubset(
            "Read projection is not a subset of parent's",
            details={
                "violating_pattern": "secrets.**",
            },
        )
        assert isinstance(err, ContextError)
        assert err.details["violating_pattern"] == "secrets.**"

    def test_clearance_exceeds_parent(self):
        err = ClearanceExceedsParent(
            "Clearance exceeds parent",
            details={
                "parent_clearance": "CONFIDENTIAL",
                "requested_clearance": "TOP_SECRET",
            },
        )
        assert isinstance(err, ContextError)

    def test_write_projection_violation(self):
        err = WriteProjectionViolation(
            "Key not in write projection",
            details={"key": "project.name"},
        )
        assert isinstance(err, ContextError)

    def test_classification_exceeds_clearance(self):
        err = ClassificationExceedsClearance(
            "Classification exceeds clearance",
            details={
                "key": "secret.data",
                "value_classification": "SECRET",
                "scope_clearance": "RESTRICTED",
            },
        )
        assert isinstance(err, ContextError)

    def test_not_a_child(self):
        err = NotAChild(
            "Not a child of this scope",
            details={
                "expected_parent_id": "parent-uuid",
                "actual_parent_id": "other-uuid",
            },
        )
        assert isinstance(err, ContextError)

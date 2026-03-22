# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tests for L3-002: ContextScope — hierarchical scoped context with projections."""

from __future__ import annotations

import time
from datetime import UTC, datetime

import pytest

from kaizen.l3.context.projection import ScopeProjection
from kaizen.l3.context.scope import ContextScope
from kaizen.l3.context.types import (
    ClassificationExceedsClearance,
    ClearanceExceedsParent,
    ConflictResolution,
    DataClassification,
    NotAChild,
    ProjectionNotSubset,
    WriteProjectionViolation,
)


# ---------------------------------------------------------------------------
# Root scope creation
# ---------------------------------------------------------------------------


class TestRootScope:
    """ContextScope.root() factory (INV-6)."""

    def test_root_defaults(self):
        root = ContextScope.root(owner_id="root-001")
        assert root.parent is None
        assert root.owner_id == "root-001"
        assert root.effective_clearance == DataClassification.TOP_SECRET
        assert root.default_classification == DataClassification.RESTRICTED
        assert root.data == {}
        assert root.children == []
        assert root.scope_id is not None

    def test_root_custom_clearance(self):
        root = ContextScope.root(
            owner_id="root-001",
            clearance=DataClassification.CONFIDENTIAL,
            default_classification=DataClassification.PUBLIC,
        )
        assert root.effective_clearance == DataClassification.CONFIDENTIAL
        assert root.default_classification == DataClassification.PUBLIC

    def test_root_unrestricted_projections(self):
        root = ContextScope.root(owner_id="root-001")
        assert root.read_projection.permits("anything") is True
        assert root.read_projection.permits("a.b.c.d") is True
        assert root.write_projection.permits("anything") is True


# ---------------------------------------------------------------------------
# create_child — monotonic tightening
# ---------------------------------------------------------------------------


class TestCreateChild:
    """create_child() enforces monotonic tightening (INV-1, clearance)."""

    def test_basic_child_creation(self):
        root = ContextScope.root(owner_id="root-001")
        child = root.create_child(
            owner_id="child-001",
            read_projection=ScopeProjection(
                allow_patterns=["project.*"], deny_patterns=[]
            ),
            write_projection=ScopeProjection(
                allow_patterns=["results.*"], deny_patterns=[]
            ),
        )
        assert child.parent is root
        assert child.owner_id == "child-001"
        assert child.scope_id in [c.scope_id for c in root.children]
        assert child.effective_clearance == DataClassification.TOP_SECRET
        assert child.default_classification == DataClassification.RESTRICTED

    def test_child_inherits_parent_clearance(self):
        root = ContextScope.root(
            owner_id="root-001",
            clearance=DataClassification.CONFIDENTIAL,
        )
        child = root.create_child(
            owner_id="child-001",
            read_projection=ScopeProjection(
                allow_patterns=["project.*"], deny_patterns=[]
            ),
            write_projection=ScopeProjection(
                allow_patterns=["results.*"], deny_patterns=[]
            ),
        )
        assert child.effective_clearance == DataClassification.CONFIDENTIAL

    def test_child_lower_clearance(self):
        root = ContextScope.root(owner_id="root-001")
        child = root.create_child(
            owner_id="child-001",
            read_projection=ScopeProjection(
                allow_patterns=["project.*"], deny_patterns=[]
            ),
            write_projection=ScopeProjection(
                allow_patterns=["results.*"], deny_patterns=[]
            ),
            effective_clearance=DataClassification.RESTRICTED,
        )
        assert child.effective_clearance == DataClassification.RESTRICTED

    def test_child_clearance_exceeds_parent_raises(self):
        root = ContextScope.root(
            owner_id="root-001",
            clearance=DataClassification.CONFIDENTIAL,
        )
        with pytest.raises(ClearanceExceedsParent):
            root.create_child(
                owner_id="child-001",
                read_projection=ScopeProjection(
                    allow_patterns=["**"], deny_patterns=[]
                ),
                write_projection=ScopeProjection(
                    allow_patterns=["**"], deny_patterns=[]
                ),
                effective_clearance=DataClassification.TOP_SECRET,
            )

    def test_child_read_projection_not_subset_raises(self):
        root = ContextScope.root(owner_id="root-001")
        # Give root a restricted read projection
        root_proj = ScopeProjection(allow_patterns=["project.*"], deny_patterns=[])
        parent = root.create_child(
            owner_id="parent-001",
            read_projection=root_proj,
            write_projection=ScopeProjection(allow_patterns=["**"], deny_patterns=[]),
        )
        # Child tries to read secrets.** which parent cannot read
        with pytest.raises(ProjectionNotSubset):
            parent.create_child(
                owner_id="child-001",
                read_projection=ScopeProjection(
                    allow_patterns=["secrets.**"], deny_patterns=[]
                ),
                write_projection=ScopeProjection(
                    allow_patterns=["results.*"], deny_patterns=[]
                ),
            )

    def test_child_default_classification_exceeds_clearance_raises(self):
        """default_classification must be <= effective_clearance of the child."""
        root = ContextScope.root(owner_id="root-001")
        with pytest.raises(ClassificationExceedsClearance):
            root.create_child(
                owner_id="child-001",
                read_projection=ScopeProjection(
                    allow_patterns=["**"], deny_patterns=[]
                ),
                write_projection=ScopeProjection(
                    allow_patterns=["**"], deny_patterns=[]
                ),
                effective_clearance=DataClassification.RESTRICTED,
                default_classification=DataClassification.SECRET,
            )

    def test_grandchild_creation(self):
        root = ContextScope.root(owner_id="root-001")
        child = root.create_child(
            owner_id="child-001",
            read_projection=ScopeProjection(
                allow_patterns=["project.**"], deny_patterns=[]
            ),
            write_projection=ScopeProjection(
                allow_patterns=["results.*"], deny_patterns=[]
            ),
        )
        grandchild = child.create_child(
            owner_id="gc-001",
            read_projection=ScopeProjection(
                allow_patterns=["project.*"], deny_patterns=[]
            ),
            write_projection=ScopeProjection(
                allow_patterns=["output.*"], deny_patterns=[]
            ),
        )
        assert grandchild.parent is child
        assert grandchild.scope_id in [c.scope_id for c in child.children]


# ---------------------------------------------------------------------------
# get — local lookup + parent traversal (INV-7)
# ---------------------------------------------------------------------------


class TestGet:
    """get() checks projection, local data, classification, parent chain."""

    def test_get_local_value(self):
        root = ContextScope.root(owner_id="root-001")
        root.set("project.name", "kaizen")
        cv = root.get("project.name")
        assert cv is not None
        assert cv.value == "kaizen"

    def test_get_nonexistent_returns_none(self):
        root = ContextScope.root(owner_id="root-001")
        assert root.get("missing.key") is None

    def test_get_parent_traversal(self):
        """Child reads from parent when not in local data (INV-7)."""
        root = ContextScope.root(owner_id="root-001")
        root.set("project.name", "kaizen", classification=DataClassification.PUBLIC)
        child = root.create_child(
            owner_id="child-001",
            read_projection=ScopeProjection(
                allow_patterns=["project.*"], deny_patterns=[]
            ),
            write_projection=ScopeProjection(
                allow_patterns=["results.*"], deny_patterns=[]
            ),
        )
        cv = child.get("project.name")
        assert cv is not None
        assert cv.value == "kaizen"

    def test_get_projection_blocks_read(self):
        """Key not in read_projection returns None."""
        root = ContextScope.root(owner_id="root-001")
        root.set("secrets.key", "abc", classification=DataClassification.PUBLIC)
        child = root.create_child(
            owner_id="child-001",
            read_projection=ScopeProjection(
                allow_patterns=["project.*"], deny_patterns=[]
            ),
            write_projection=ScopeProjection(
                allow_patterns=["results.*"], deny_patterns=[]
            ),
        )
        assert child.get("secrets.key") is None

    def test_get_classification_filtering(self):
        """Value above clearance is invisible (INV-4)."""
        root = ContextScope.root(owner_id="root-001")
        root.set(
            "report.secret", "classified", classification=DataClassification.SECRET
        )
        child = root.create_child(
            owner_id="child-001",
            read_projection=ScopeProjection(
                allow_patterns=["report.*"], deny_patterns=[]
            ),
            write_projection=ScopeProjection(
                allow_patterns=["output.*"], deny_patterns=[]
            ),
            effective_clearance=DataClassification.RESTRICTED,
        )
        assert child.get("report.secret") is None

    def test_get_classification_at_boundary(self):
        """Value at exactly the clearance level IS visible."""
        root = ContextScope.root(owner_id="root-001")
        root.set(
            "report.internal",
            "revenue data",
            classification=DataClassification.RESTRICTED,
        )
        child = root.create_child(
            owner_id="child-001",
            read_projection=ScopeProjection(
                allow_patterns=["report.*"], deny_patterns=[]
            ),
            write_projection=ScopeProjection(
                allow_patterns=["output.*"], deny_patterns=[]
            ),
            effective_clearance=DataClassification.RESTRICTED,
        )
        cv = child.get("report.internal")
        assert cv is not None
        assert cv.value == "revenue data"

    def test_get_deny_blocks_allowed_key(self):
        """Deny pattern overrides allow (INV-2 applied to get)."""
        root = ContextScope.root(owner_id="root-001")
        root.set("project.budget", 50000, classification=DataClassification.PUBLIC)
        child = root.create_child(
            owner_id="child-001",
            read_projection=ScopeProjection(
                allow_patterns=["project.**"],
                deny_patterns=["project.budget"],
            ),
            write_projection=ScopeProjection(
                allow_patterns=["results.*"], deny_patterns=[]
            ),
        )
        assert child.get("project.budget") is None

    def test_local_value_shadows_parent(self):
        """Local value takes precedence over parent value."""
        root = ContextScope.root(owner_id="root-001")
        root.set("config.name", "root-value", classification=DataClassification.PUBLIC)
        child = root.create_child(
            owner_id="child-001",
            read_projection=ScopeProjection(
                allow_patterns=["config.*"], deny_patterns=[]
            ),
            write_projection=ScopeProjection(
                allow_patterns=["config.*"], deny_patterns=[]
            ),
        )
        child.set("config.name", "child-value")
        cv = child.get("config.name")
        assert cv is not None
        assert cv.value == "child-value"

    def test_deep_traversal(self):
        """get() traverses Root -> A -> B -> C (TV-5 / Edge Case 8.6)."""
        root = ContextScope.root(owner_id="root-001")
        root.set(
            "config.db_host",
            "prod.db.example.com",
            classification=DataClassification.RESTRICTED,
        )
        root.set(
            "config.app_name", "kaizen-root", classification=DataClassification.PUBLIC
        )
        root.set(
            "config.secret_key", "root-secret", classification=DataClassification.SECRET
        )

        middle = root.create_child(
            owner_id="middle-001",
            read_projection=ScopeProjection(
                allow_patterns=["config.**"], deny_patterns=[]
            ),
            write_projection=ScopeProjection(
                allow_patterns=["config.app_name", "results.*"], deny_patterns=[]
            ),
            effective_clearance=DataClassification.CONFIDENTIAL,
        )
        middle.set("config.app_name", "kaizen-middle")

        leaf = middle.create_child(
            owner_id="leaf-001",
            read_projection=ScopeProjection(
                allow_patterns=["config.*"], deny_patterns=[]
            ),
            write_projection=ScopeProjection(
                allow_patterns=["output.*"], deny_patterns=[]
            ),
            effective_clearance=DataClassification.RESTRICTED,
        )

        # Middle's local value shadows root
        cv = leaf.get("config.app_name")
        assert cv is not None
        assert cv.value == "kaizen-middle"

        # Traverses through middle to root
        cv = leaf.get("config.db_host")
        assert cv is not None
        assert cv.value == "prod.db.example.com"

        # SECRET > RESTRICTED clearance -> filtered
        assert leaf.get("config.secret_key") is None

    def test_dynamic_parent_update_visible(self):
        """Child sees parent's new keys written after creation (TV-6 / Edge Case 8.1)."""
        root = ContextScope.root(owner_id="root-001")
        root.set("project.name", "kaizen", classification=DataClassification.PUBLIC)

        child = root.create_child(
            owner_id="child-001",
            read_projection=ScopeProjection(
                allow_patterns=["project.*"], deny_patterns=[]
            ),
            write_projection=ScopeProjection(
                allow_patterns=["results.*"], deny_patterns=[]
            ),
        )

        # Key does not exist yet
        assert child.get("project.deadline") is None

        # Parent writes new key AFTER child creation
        root.set(
            "project.deadline", "2026-04-01", classification=DataClassification.PUBLIC
        )

        # Child sees it via lazy traversal
        cv = child.get("project.deadline")
        assert cv is not None
        assert cv.value == "2026-04-01"


# ---------------------------------------------------------------------------
# set — write projection enforcement (INV-3)
# ---------------------------------------------------------------------------


class TestSet:
    """set() enforces write projection and classification ceiling."""

    def test_set_within_projection(self):
        root = ContextScope.root(owner_id="root-001")
        child = root.create_child(
            owner_id="child-001",
            read_projection=ScopeProjection(allow_patterns=["**"], deny_patterns=[]),
            write_projection=ScopeProjection(
                allow_patterns=["results.*"], deny_patterns=[]
            ),
        )
        child.set("results.output", "analysis complete")
        cv = child.get("results.output")
        assert cv is not None
        assert cv.value == "analysis complete"

    def test_set_outside_projection_raises(self):
        """Write to unpermitted key raises WriteProjectionViolation (INV-3)."""
        root = ContextScope.root(owner_id="root-001")
        child = root.create_child(
            owner_id="child-001",
            read_projection=ScopeProjection(allow_patterns=["**"], deny_patterns=[]),
            write_projection=ScopeProjection(
                allow_patterns=["results.*"], deny_patterns=[]
            ),
        )
        with pytest.raises(WriteProjectionViolation):
            child.set("project.name", "tampered")

    def test_set_classification_exceeds_clearance_raises(self):
        """Cannot write value with classification above scope clearance."""
        root = ContextScope.root(owner_id="root-001")
        child = root.create_child(
            owner_id="child-001",
            read_projection=ScopeProjection(allow_patterns=["**"], deny_patterns=[]),
            write_projection=ScopeProjection(
                allow_patterns=["results.*"], deny_patterns=[]
            ),
            effective_clearance=DataClassification.CONFIDENTIAL,
        )
        with pytest.raises(ClassificationExceedsClearance):
            child.set(
                "results.classified",
                "top-secret-data",
                classification=DataClassification.SECRET,
            )

    def test_set_uses_default_classification(self):
        root = ContextScope.root(
            owner_id="root-001",
            default_classification=DataClassification.PUBLIC,
        )
        root.set("test.key", "val")
        cv = root.get("test.key")
        assert cv is not None
        assert cv.classification == DataClassification.PUBLIC

    def test_set_explicit_classification(self):
        root = ContextScope.root(owner_id="root-001")
        root.set("test.key", "val", classification=DataClassification.CONFIDENTIAL)
        cv = root.get("test.key")
        assert cv is not None
        assert cv.classification == DataClassification.CONFIDENTIAL

    def test_set_overwrites_existing(self):
        root = ContextScope.root(owner_id="root-001")
        root.set("key", "v1")
        root.set("key", "v2")
        cv = root.get("key")
        assert cv is not None
        assert cv.value == "v2"

    def test_set_records_owner(self):
        root = ContextScope.root(owner_id="root-001")
        root.set("key", "val")
        cv = root.get("key")
        assert cv is not None
        assert cv.written_by == "root-001"


# ---------------------------------------------------------------------------
# remove — local only (INV-8)
# ---------------------------------------------------------------------------


class TestRemove:
    """remove() removes from local data only."""

    def test_remove_existing_key(self):
        root = ContextScope.root(owner_id="root-001")
        root.set("key", "val")
        removed = root.remove("key")
        assert removed is not None
        assert removed.value == "val"
        assert root.get("key") is None

    def test_remove_nonexistent_returns_none(self):
        root = ContextScope.root(owner_id="root-001")
        assert root.remove("missing") is None

    def test_remove_local_reveals_parent(self):
        """After removing local key, get() traverses to parent (INV-8)."""
        root = ContextScope.root(owner_id="root-001")
        root.set("config.name", "root-value", classification=DataClassification.PUBLIC)

        child = root.create_child(
            owner_id="child-001",
            read_projection=ScopeProjection(
                allow_patterns=["config.*"], deny_patterns=[]
            ),
            write_projection=ScopeProjection(
                allow_patterns=["config.*"], deny_patterns=[]
            ),
        )
        child.set("config.name", "child-value")
        assert child.get("config.name").value == "child-value"

        child.remove("config.name")
        # Now traverses to parent
        cv = child.get("config.name")
        assert cv is not None
        assert cv.value == "root-value"


# ---------------------------------------------------------------------------
# visible_keys
# ---------------------------------------------------------------------------


class TestVisibleKeys:
    """visible_keys() returns union of local + parent (filtered)."""

    def test_root_visible_keys(self):
        root = ContextScope.root(owner_id="root-001")
        root.set("a", 1, classification=DataClassification.PUBLIC)
        root.set("b", 2, classification=DataClassification.PUBLIC)
        keys = root.visible_keys()
        assert sorted(keys) == ["a", "b"]

    def test_child_visible_keys_filtered(self):
        """TV-1: Child only sees keys matching projection and clearance."""
        root = ContextScope.root(owner_id="root-001")
        root.set("project.name", "kaizen", classification=DataClassification.PUBLIC)
        root.set(
            "project.budget", 50000, classification=DataClassification.CONFIDENTIAL
        )
        root.set(
            "secrets.api_key", "sk-abc123", classification=DataClassification.SECRET
        )
        root.set("shared.status", "active", classification=DataClassification.PUBLIC)

        child = root.create_child(
            owner_id="child-001",
            read_projection=ScopeProjection(
                allow_patterns=["project.**", "shared.*"],
                deny_patterns=["project.budget"],
            ),
            write_projection=ScopeProjection(
                allow_patterns=["results.*"], deny_patterns=[]
            ),
            effective_clearance=DataClassification.CONFIDENTIAL,
        )

        keys = child.visible_keys()
        assert sorted(keys) == ["project.name", "shared.status"]

    def test_classification_filter_in_visible_keys(self):
        """TV-3: Classification filtering applies to visible_keys."""
        root = ContextScope.root(owner_id="root-001")
        root.set(
            "report.public", "Q3 results", classification=DataClassification.PUBLIC
        )
        root.set(
            "report.internal",
            "Revenue: $12M",
            classification=DataClassification.RESTRICTED,
        )
        root.set(
            "report.board",
            "Acquire CompanyX",
            classification=DataClassification.CONFIDENTIAL,
        )
        root.set("report.legal", "Litigation", classification=DataClassification.SECRET)
        root.set(
            "report.crisis",
            "Scenario Alpha",
            classification=DataClassification.TOP_SECRET,
        )

        child = root.create_child(
            owner_id="analyst-001",
            read_projection=ScopeProjection(
                allow_patterns=["report.**"], deny_patterns=[]
            ),
            write_projection=ScopeProjection(
                allow_patterns=["analysis.*"], deny_patterns=[]
            ),
            effective_clearance=DataClassification.RESTRICTED,
        )

        keys = child.visible_keys()
        assert sorted(keys) == ["report.internal", "report.public"]

    def test_empty_projection_empty_keys(self):
        """TV-7: Scope with empty allow sees nothing."""
        root = ContextScope.root(owner_id="root-001")
        root.set("project.name", "kaizen", classification=DataClassification.PUBLIC)

        child = root.create_child(
            owner_id="sandboxed-001",
            read_projection=ScopeProjection(allow_patterns=[], deny_patterns=[]),
            write_projection=ScopeProjection(allow_patterns=[], deny_patterns=[]),
            effective_clearance=DataClassification.PUBLIC,
        )

        assert child.visible_keys() == []

    def test_visible_keys_deduplicated(self):
        """Same key in child and parent appears once."""
        root = ContextScope.root(owner_id="root-001")
        root.set("config.name", "root-val", classification=DataClassification.PUBLIC)

        child = root.create_child(
            owner_id="child-001",
            read_projection=ScopeProjection(
                allow_patterns=["config.*"], deny_patterns=[]
            ),
            write_projection=ScopeProjection(
                allow_patterns=["config.*"], deny_patterns=[]
            ),
        )
        child.set("config.name", "child-val")

        keys = child.visible_keys()
        assert keys.count("config.name") == 1


# ---------------------------------------------------------------------------
# snapshot
# ---------------------------------------------------------------------------


class TestSnapshot:
    """snapshot() materializes flat view of all visible keys."""

    def test_basic_snapshot(self):
        root = ContextScope.root(owner_id="root-001")
        root.set("a", 1, classification=DataClassification.PUBLIC)
        root.set("b", "two", classification=DataClassification.PUBLIC)
        snap = root.snapshot()
        assert snap == {"a": 1, "b": "two"}

    def test_snapshot_respects_projection(self):
        root = ContextScope.root(owner_id="root-001")
        root.set("project.name", "kaizen", classification=DataClassification.PUBLIC)
        root.set("secrets.key", "abc", classification=DataClassification.PUBLIC)

        child = root.create_child(
            owner_id="child-001",
            read_projection=ScopeProjection(
                allow_patterns=["project.*"], deny_patterns=[]
            ),
            write_projection=ScopeProjection(
                allow_patterns=["results.*"], deny_patterns=[]
            ),
        )
        snap = child.snapshot()
        assert snap == {"project.name": "kaizen"}

    def test_empty_projection_empty_snapshot(self):
        """TV-7: Empty projection -> empty snapshot."""
        root = ContextScope.root(owner_id="root-001")
        root.set("project.name", "kaizen", classification=DataClassification.PUBLIC)

        child = root.create_child(
            owner_id="sandboxed-001",
            read_projection=ScopeProjection(allow_patterns=[], deny_patterns=[]),
            write_projection=ScopeProjection(allow_patterns=[], deny_patterns=[]),
            effective_clearance=DataClassification.PUBLIC,
        )
        assert child.snapshot() == {}

    def test_snapshot_includes_parent_data(self):
        root = ContextScope.root(owner_id="root-001")
        root.set(
            "config.host", "db.example.com", classification=DataClassification.PUBLIC
        )

        child = root.create_child(
            owner_id="child-001",
            read_projection=ScopeProjection(
                allow_patterns=["config.*", "results.*"], deny_patterns=[]
            ),
            write_projection=ScopeProjection(
                allow_patterns=["results.*"], deny_patterns=[]
            ),
        )
        child.set("results.output", "done")

        snap = child.snapshot()
        assert snap == {"config.host": "db.example.com", "results.output": "done"}


# ---------------------------------------------------------------------------
# merge_child_results (INV-5)
# ---------------------------------------------------------------------------


class TestMergeChildResults:
    """merge_child_results() propagates child writes to parent."""

    def test_basic_merge(self):
        """TV-4: Merge child results into parent."""
        root = ContextScope.root(owner_id="root-001")
        root.set("project.name", "kaizen", classification=DataClassification.PUBLIC)

        child = root.create_child(
            owner_id="worker-001",
            read_projection=ScopeProjection(
                allow_patterns=["project.*"], deny_patterns=[]
            ),
            write_projection=ScopeProjection(
                allow_patterns=["results.*"], deny_patterns=[]
            ),
            effective_clearance=DataClassification.CONFIDENTIAL,
        )
        child.set("results.review", {"status": "approved", "score": 95})
        child.set("results.summary", "All tests passed")

        result = root.merge_child_results(child)
        assert sorted(result.merged_keys) == ["results.review", "results.summary"]
        assert result.skipped_keys == []
        assert result.conflicts == []

        # Parent now has the merged data
        cv = root.get("results.review")
        assert cv is not None
        assert cv.value == {"status": "approved", "score": 95}

        cv = root.get("results.summary")
        assert cv is not None
        assert cv.value == "All tests passed"

        # Original data preserved
        cv = root.get("project.name")
        assert cv is not None
        assert cv.value == "kaizen"

    def test_merge_skips_keys_outside_write_projection(self):
        """Keys outside child's write_projection are skipped (INV-5)."""
        root = ContextScope.root(owner_id="root-001")
        child = root.create_child(
            owner_id="child-001",
            read_projection=ScopeProjection(allow_patterns=["**"], deny_patterns=[]),
            write_projection=ScopeProjection(
                allow_patterns=["results.*"], deny_patterns=[]
            ),
        )
        child.set("results.ok", "yes")
        # Inject a key outside write_projection directly into data
        # (simulating a bug or test manipulation per spec INV-5)
        from kaizen.l3.context.types import ContextValue, DataClassification

        child.data["illegal.key"] = ContextValue(
            value="bad",
            written_by="child-001",
            updated_at=datetime.now(UTC),
            classification=DataClassification.RESTRICTED,
        )

        result = root.merge_child_results(child)
        assert "results.ok" in result.merged_keys
        assert "illegal.key" in result.skipped_keys
        assert root.get("illegal.key") is None

    def test_merge_conflict_child_wins(self):
        """Parent updated after child creation -> conflict with CHILD_WINS."""
        root = ContextScope.root(owner_id="root-001")
        root.set("results.score", 50, classification=DataClassification.PUBLIC)

        child = root.create_child(
            owner_id="child-001",
            read_projection=ScopeProjection(allow_patterns=["**"], deny_patterns=[]),
            write_projection=ScopeProjection(
                allow_patterns=["results.*"], deny_patterns=[]
            ),
        )

        # Parent updates AFTER child creation
        time.sleep(0.01)
        root.set("results.score", 75, classification=DataClassification.PUBLIC)

        # Child also writes
        time.sleep(0.01)
        child.set("results.score", 95)

        result = root.merge_child_results(child)
        assert "results.score" in result.merged_keys
        assert len(result.conflicts) == 1
        assert result.conflicts[0].key == "results.score"
        assert result.conflicts[0].resolution == ConflictResolution.CHILD_WINS

        # Child wins
        cv = root.get("results.score")
        assert cv is not None
        assert cv.value == 95

    def test_merge_not_a_child_raises(self):
        """Merging a scope that is not a child raises NotAChild."""
        root = ContextScope.root(owner_id="root-001")
        other = ContextScope.root(owner_id="other-001")
        with pytest.raises(NotAChild):
            root.merge_child_results(other)

    def test_merge_removes_child_from_parent(self):
        """After merge, child is removed from parent's children list."""
        root = ContextScope.root(owner_id="root-001")
        child = root.create_child(
            owner_id="child-001",
            read_projection=ScopeProjection(allow_patterns=["**"], deny_patterns=[]),
            write_projection=ScopeProjection(
                allow_patterns=["results.*"], deny_patterns=[]
            ),
        )
        assert child.scope_id in [c.scope_id for c in root.children]
        root.merge_child_results(child)
        assert child.scope_id not in [c.scope_id for c in root.children]

    def test_merge_preserves_child_written_by(self):
        """Merged values preserve the child's written_by and updated_at."""
        root = ContextScope.root(owner_id="root-001")
        child = root.create_child(
            owner_id="child-001",
            read_projection=ScopeProjection(allow_patterns=["**"], deny_patterns=[]),
            write_projection=ScopeProjection(
                allow_patterns=["results.*"], deny_patterns=[]
            ),
        )
        child.set("results.output", "done")
        root.merge_child_results(child)

        cv = root.get("results.output")
        assert cv is not None
        assert cv.written_by == "child-001"


# ---------------------------------------------------------------------------
# Full test vector scenarios (TV-1 through TV-7)
# ---------------------------------------------------------------------------


class TestSpecTestVectors:
    """Test vectors from the spec, consolidated."""

    def test_tv1_basic_projection_filtering(self):
        """TV-1: Child scope sees only keys matching read_projection; deny precedence."""
        root = ContextScope.root(owner_id="root-agent-001")
        root.set("project.name", "kaizen", classification=DataClassification.PUBLIC)
        root.set(
            "project.budget", 50000, classification=DataClassification.CONFIDENTIAL
        )
        root.set(
            "secrets.api_key", "sk-abc123", classification=DataClassification.SECRET
        )
        root.set("shared.status", "active", classification=DataClassification.PUBLIC)

        child = root.create_child(
            owner_id="child-agent-001",
            read_projection=ScopeProjection(
                allow_patterns=["project.**", "shared.*"],
                deny_patterns=["project.budget"],
            ),
            write_projection=ScopeProjection(
                allow_patterns=["results.*"], deny_patterns=[]
            ),
            effective_clearance=DataClassification.CONFIDENTIAL,
        )

        assert child.get("project.name").value == "kaizen"
        assert child.get("project.budget") is None  # denied
        assert child.get("secrets.api_key") is None  # not in allow + classification
        assert child.get("shared.status").value == "active"
        assert sorted(child.visible_keys()) == ["project.name", "shared.status"]

    def test_tv2_write_projection_enforcement(self):
        """TV-2: Child cannot write keys outside write_projection."""
        root = ContextScope.root(owner_id="root-agent-001")

        child = root.create_child(
            owner_id="child-agent-001",
            read_projection=ScopeProjection(allow_patterns=["**"], deny_patterns=[]),
            write_projection=ScopeProjection(
                allow_patterns=["results.*"], deny_patterns=[]
            ),
            effective_clearance=DataClassification.CONFIDENTIAL,
        )

        child.set("results.output", "analysis complete")
        assert child.get("results.output").value == "analysis complete"

        with pytest.raises(WriteProjectionViolation):
            child.set("project.name", "tampered")

        with pytest.raises(ClassificationExceedsClearance):
            child.set(
                "results.classified",
                "top-secret-data",
                classification=DataClassification.SECRET,
            )

    def test_tv3_classification_filtering(self):
        """TV-3: Agent cannot see values above its effective_clearance."""
        root = ContextScope.root(owner_id="root-agent-001")
        root.set(
            "report.public_summary",
            "Q3 results positive",
            classification=DataClassification.PUBLIC,
        )
        root.set(
            "report.internal_details",
            "Revenue: $12M",
            classification=DataClassification.RESTRICTED,
        )
        root.set(
            "report.board_strategy",
            "Acquire CompanyX",
            classification=DataClassification.CONFIDENTIAL,
        )
        root.set(
            "report.legal_privileged",
            "Litigation pending",
            classification=DataClassification.SECRET,
        )
        root.set(
            "report.crisis_plan",
            "Scenario Alpha",
            classification=DataClassification.TOP_SECRET,
        )

        child = root.create_child(
            owner_id="analyst-agent-001",
            read_projection=ScopeProjection(
                allow_patterns=["report.**"], deny_patterns=[]
            ),
            write_projection=ScopeProjection(
                allow_patterns=["analysis.*"], deny_patterns=[]
            ),
            effective_clearance=DataClassification.RESTRICTED,
        )

        assert child.get("report.public_summary").value == "Q3 results positive"
        assert child.get("report.internal_details").value == "Revenue: $12M"
        assert child.get("report.board_strategy") is None
        assert child.get("report.legal_privileged") is None
        assert child.get("report.crisis_plan") is None
        assert sorted(child.visible_keys()) == [
            "report.internal_details",
            "report.public_summary",
        ]

    def test_tv7_empty_projection_scope(self):
        """TV-7: Scope with empty allow_patterns sees and writes nothing."""
        root = ContextScope.root(owner_id="root-001")
        root.set("project.name", "kaizen", classification=DataClassification.PUBLIC)

        child = root.create_child(
            owner_id="sandboxed-001",
            read_projection=ScopeProjection(allow_patterns=[], deny_patterns=[]),
            write_projection=ScopeProjection(allow_patterns=[], deny_patterns=[]),
            effective_clearance=DataClassification.PUBLIC,
        )

        assert child.get("project.name") is None
        assert child.visible_keys() == []
        with pytest.raises(WriteProjectionViolation):
            child.set("anything", "test")
        assert child.snapshot() == {}

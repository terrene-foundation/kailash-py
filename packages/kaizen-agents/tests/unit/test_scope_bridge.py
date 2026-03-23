# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""
Unit tests for kaizen_agents.context._scope_bridge — ScopeBridge.

Tier 1: Unit tests using real SDK ContextScope (no mocking).
"""

from __future__ import annotations

import pytest

from kaizen.l3.context.scope import ContextScope
from kaizen.l3.context.types import DataClassification, ContextValue
from kaizen_agents.orchestration.context._scope_bridge import ScopeBridge


# ---------------------------------------------------------------------------
# ScopeBridge.create_root
# ---------------------------------------------------------------------------


class TestScopeBridgeCreateRoot:
    """Tests for ScopeBridge.create_root factory."""

    def test_create_root_returns_scope_bridge(self) -> None:
        """create_root returns a ScopeBridge instance."""
        bridge = ScopeBridge.create_root(owner_id="supervisor-1")
        assert isinstance(bridge, ScopeBridge)

    def test_create_root_default_clearance_is_confidential(self) -> None:
        """Default clearance is CONFIDENTIAL when not specified."""
        bridge = ScopeBridge.create_root(owner_id="supervisor-1")
        assert bridge.root_scope.effective_clearance == DataClassification.CONFIDENTIAL

    def test_create_root_with_explicit_clearance(self) -> None:
        """Clearance string maps to DataClassification correctly."""
        bridge = ScopeBridge.create_root(
            owner_id="supervisor-1",
            clearance="top_secret",
        )
        assert bridge.root_scope.effective_clearance == DataClassification.TOP_SECRET

    def test_create_root_owner_id_set(self) -> None:
        """Root scope has the correct owner_id."""
        bridge = ScopeBridge.create_root(owner_id="agent-42")
        assert bridge.root_scope.owner_id == "agent-42"

    def test_create_root_invalid_clearance_raises(self) -> None:
        """Invalid clearance string raises ValueError."""
        with pytest.raises(ValueError, match="Unknown classification"):
            ScopeBridge.create_root(owner_id="x", clearance="ultra_mega_secret")


# ---------------------------------------------------------------------------
# Classification string mapping
# ---------------------------------------------------------------------------


class TestClassificationMapping:
    """Tests for clearance string to DataClassification conversion."""

    @pytest.mark.parametrize(
        "clearance_str, expected",
        [
            ("public", DataClassification.PUBLIC),
            ("restricted", DataClassification.RESTRICTED),
            ("confidential", DataClassification.CONFIDENTIAL),
            ("secret", DataClassification.SECRET),
            ("top_secret", DataClassification.TOP_SECRET),
        ],
    )
    def test_all_classification_strings(
        self,
        clearance_str: str,
        expected: DataClassification,
    ) -> None:
        """Every valid classification string maps to the correct enum."""
        bridge = ScopeBridge.create_root(
            owner_id="test",
            clearance=clearance_str,
        )
        assert bridge.root_scope.effective_clearance == expected

    def test_case_insensitive_mapping(self) -> None:
        """Classification strings are case-insensitive."""
        bridge = ScopeBridge.create_root(owner_id="test", clearance="PUBLIC")
        assert bridge.root_scope.effective_clearance == DataClassification.PUBLIC

        bridge2 = ScopeBridge.create_root(owner_id="test", clearance="Top_Secret")
        assert bridge2.root_scope.effective_clearance == DataClassification.TOP_SECRET


# ---------------------------------------------------------------------------
# ScopeBridge.create_child_scope
# ---------------------------------------------------------------------------


class TestScopeBridgeCreateChildScope:
    """Tests for create_child_scope with controlled visibility."""

    def test_child_scope_returned_is_context_scope(self) -> None:
        """create_child_scope returns a ContextScope instance."""
        bridge = ScopeBridge.create_root(owner_id="supervisor")
        bridge.root_scope.set("project.name", "Alpha", classification=DataClassification.PUBLIC)
        child = bridge.create_child_scope(
            child_owner_id="worker-1",
            visible_keys=["project.*"],
            writable_prefix="results",
        )
        assert isinstance(child, ContextScope)

    def test_child_sees_only_visible_keys(self) -> None:
        """Child with restricted visibility cannot see excluded keys."""
        bridge = ScopeBridge.create_root(owner_id="supervisor", clearance="confidential")
        bridge.root_scope.set("project.name", "Alpha", classification=DataClassification.PUBLIC)
        bridge.root_scope.set("project.budget", 10000, classification=DataClassification.PUBLIC)
        bridge.root_scope.set("secrets.api_key", "sk-123", classification=DataClassification.PUBLIC)

        child = bridge.create_child_scope(
            child_owner_id="worker-1",
            visible_keys=["project.*"],
            writable_prefix="results",
        )

        visible = child.visible_keys()
        assert "project.name" in visible
        assert "project.budget" in visible
        assert "secrets.api_key" not in visible

    def test_child_can_write_under_writable_prefix(self) -> None:
        """Child can write keys under the writable_prefix."""
        bridge = ScopeBridge.create_root(owner_id="supervisor")
        child = bridge.create_child_scope(
            child_owner_id="worker-1",
            visible_keys=["project.**"],
            writable_prefix="results",
            clearance="public",
        )

        # Should succeed — key is under "results"
        child.set("results.analysis", "complete", classification=DataClassification.PUBLIC)
        cv = child.get("results.analysis")
        assert cv is not None
        assert cv.value == "complete"

    def test_child_clearance_applied(self) -> None:
        """Child scope has the correct effective clearance."""
        bridge = ScopeBridge.create_root(owner_id="supervisor", clearance="secret")
        child = bridge.create_child_scope(
            child_owner_id="worker-1",
            visible_keys=["**"],
            writable_prefix="output",
            clearance="restricted",
        )
        assert child.effective_clearance == DataClassification.RESTRICTED

    def test_child_default_clearance_matches_parent(self) -> None:
        """When clearance is not specified, child inherits parent's clearance."""
        bridge = ScopeBridge.create_root(owner_id="supervisor", clearance="confidential")
        child = bridge.create_child_scope(
            child_owner_id="worker-1",
            visible_keys=["**"],
            writable_prefix="output",
        )
        assert child.effective_clearance == DataClassification.CONFIDENTIAL


# ---------------------------------------------------------------------------
# Classification-based access control
# ---------------------------------------------------------------------------


class TestClassificationAccessControl:
    """Child with lower clearance cannot see higher-classified values."""

    def test_low_clearance_child_cannot_see_high_classification(self) -> None:
        """A PUBLIC-clearance child cannot read CONFIDENTIAL values."""
        bridge = ScopeBridge.create_root(owner_id="supervisor", clearance="confidential")
        bridge.root_scope.set("project.name", "Alpha", classification=DataClassification.PUBLIC)
        bridge.root_scope.set(
            "project.budget", 50000, classification=DataClassification.CONFIDENTIAL
        )

        child = bridge.create_child_scope(
            child_owner_id="worker-1",
            visible_keys=["project.**"],
            writable_prefix="results",
            clearance="public",
        )

        # PUBLIC child can see PUBLIC value
        name_cv = child.get("project.name")
        assert name_cv is not None
        assert name_cv.value == "Alpha"

        # PUBLIC child cannot see CONFIDENTIAL value
        budget_cv = child.get("project.budget")
        assert budget_cv is None

    def test_matching_clearance_can_read(self) -> None:
        """A RESTRICTED-clearance child can read RESTRICTED values."""
        bridge = ScopeBridge.create_root(owner_id="supervisor", clearance="confidential")
        bridge.root_scope.set(
            "data.report", "Q1 results", classification=DataClassification.RESTRICTED
        )

        child = bridge.create_child_scope(
            child_owner_id="worker-1",
            visible_keys=["data.**"],
            writable_prefix="output",
            clearance="restricted",
        )

        cv = child.get("data.report")
        assert cv is not None
        assert cv.value == "Q1 results"


# ---------------------------------------------------------------------------
# ScopeBridge.inject_context
# ---------------------------------------------------------------------------


class TestScopeBridgeInjectContext:
    """Tests for inject_context — extracts context as a flat dict."""

    def test_inject_returns_dict_of_visible_values(self) -> None:
        """inject_context returns values for the specified keys."""
        bridge = ScopeBridge.create_root(owner_id="supervisor", clearance="confidential")
        bridge.root_scope.set("project.name", "Alpha", classification=DataClassification.PUBLIC)
        bridge.root_scope.set("project.stack", "Python", classification=DataClassification.PUBLIC)
        bridge.root_scope.set(
            "internal.token", "secret123", classification=DataClassification.CONFIDENTIAL
        )

        result = bridge.inject_context(keys=["project.name", "project.stack"])
        assert result == {"project.name": "Alpha", "project.stack": "Python"}

    def test_inject_skips_nonexistent_keys(self) -> None:
        """Keys not present in root scope are silently omitted."""
        bridge = ScopeBridge.create_root(owner_id="supervisor")
        bridge.root_scope.set("project.name", "Alpha", classification=DataClassification.PUBLIC)

        result = bridge.inject_context(keys=["project.name", "nonexistent.key"])
        assert result == {"project.name": "Alpha"}

    def test_inject_empty_keys_returns_empty_dict(self) -> None:
        """Empty key list returns an empty dict."""
        bridge = ScopeBridge.create_root(owner_id="supervisor")
        bridge.root_scope.set("project.name", "Alpha", classification=DataClassification.PUBLIC)

        result = bridge.inject_context(keys=[])
        assert result == {}

    def test_inject_all_visible_when_keys_not_specified(self) -> None:
        """When keys is None, returns all visible values from root scope."""
        bridge = ScopeBridge.create_root(owner_id="supervisor", clearance="confidential")
        bridge.root_scope.set("project.name", "Alpha", classification=DataClassification.PUBLIC)
        bridge.root_scope.set("project.stack", "Python", classification=DataClassification.PUBLIC)

        result = bridge.inject_context(keys=None)
        assert "project.name" in result
        assert "project.stack" in result


# ---------------------------------------------------------------------------
# ScopeBridge.merge_child_results
# ---------------------------------------------------------------------------


class TestScopeBridgeMergeChildResults:
    """Tests for merge_child_results — brings child writes back to parent."""

    def test_merge_child_writes_to_parent(self) -> None:
        """Child writes are merged back into the root scope."""
        bridge = ScopeBridge.create_root(owner_id="supervisor", clearance="confidential")
        bridge.root_scope.set("project.name", "Alpha", classification=DataClassification.PUBLIC)

        child = bridge.create_child_scope(
            child_owner_id="worker-1",
            visible_keys=["project.**"],
            writable_prefix="results",
            clearance="public",
        )

        child.set("results.status", "done", classification=DataClassification.PUBLIC)
        child.set("results.score", 95, classification=DataClassification.PUBLIC)

        merged = bridge.merge_child_results(child)
        assert "results.status" in merged
        assert "results.score" in merged

        # Verify the parent now has the merged values
        status_cv = bridge.root_scope.get("results.status")
        assert status_cv is not None
        assert status_cv.value == "done"

        score_cv = bridge.root_scope.get("results.score")
        assert score_cv is not None
        assert score_cv.value == 95

    def test_merge_returns_merged_key_names(self) -> None:
        """merge_child_results returns the list of merged key names."""
        bridge = ScopeBridge.create_root(owner_id="supervisor", clearance="confidential")
        child = bridge.create_child_scope(
            child_owner_id="worker-1",
            visible_keys=["**"],
            writable_prefix="output",
            clearance="public",
        )
        child.set("output.result", "42", classification=DataClassification.PUBLIC)

        merged = bridge.merge_child_results(child)
        assert isinstance(merged, dict)
        assert "output.result" in merged

    def test_merge_empty_child_returns_empty(self) -> None:
        """Merging a child with no writes returns empty dict."""
        bridge = ScopeBridge.create_root(owner_id="supervisor")
        child = bridge.create_child_scope(
            child_owner_id="worker-1",
            visible_keys=["**"],
            writable_prefix="output",
        )

        merged = bridge.merge_child_results(child)
        assert merged == {}


# ---------------------------------------------------------------------------
# ScopeBridge from existing ContextScope
# ---------------------------------------------------------------------------


class TestScopeBridgeFromExistingScope:
    """Tests for ScopeBridge wrapping an existing ContextScope."""

    def test_wrap_existing_scope(self) -> None:
        """ScopeBridge can wrap an externally created ContextScope."""
        root = ContextScope.root(
            owner_id="external-owner",
            clearance=DataClassification.SECRET,
        )
        root.set("key.a", "value-a", classification=DataClassification.PUBLIC)

        bridge = ScopeBridge(root_scope=root)
        result = bridge.inject_context(keys=["key.a"])
        assert result == {"key.a": "value-a"}

    def test_root_scope_property(self) -> None:
        """root_scope property returns the underlying ContextScope."""
        root = ContextScope.root(owner_id="test")
        bridge = ScopeBridge(root_scope=root)
        assert bridge.root_scope is root

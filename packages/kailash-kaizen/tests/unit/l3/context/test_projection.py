# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tests for L3-002: ScopeProjection with custom dot-segment matching (AD-L3-13)."""

from __future__ import annotations

import pytest

from kaizen.l3.context.projection import ScopeProjection


# ---------------------------------------------------------------------------
# Single-star matching: exactly one dot-segment
# ---------------------------------------------------------------------------


class TestSingleStarMatching:
    """'*' matches exactly one segment (no dots)."""

    def test_star_matches_single_segment(self):
        proj = ScopeProjection(allow_patterns=["project.*"], deny_patterns=[])
        assert proj.permits("project.name") is True
        assert proj.permits("project.budget") is True

    def test_star_does_not_match_nested(self):
        proj = ScopeProjection(allow_patterns=["project.*"], deny_patterns=[])
        assert proj.permits("project.config.debug") is False

    def test_star_does_not_match_empty_segment(self):
        """'project.*' should NOT match 'project' alone."""
        proj = ScopeProjection(allow_patterns=["project.*"], deny_patterns=[])
        assert proj.permits("project") is False

    def test_star_in_middle(self):
        """'a.*.c' matches 'a.x.c' but not 'a.x.y.c'."""
        proj = ScopeProjection(allow_patterns=["a.*.c"], deny_patterns=[])
        assert proj.permits("a.x.c") is True
        assert proj.permits("a.x.y.c") is False

    def test_star_at_start(self):
        """'*.output' matches 'task.output', 'review.output'."""
        proj = ScopeProjection(allow_patterns=["*.output"], deny_patterns=[])
        assert proj.permits("task.output") is True
        assert proj.permits("review.output") is True
        assert proj.permits("a.b.output") is False


# ---------------------------------------------------------------------------
# Double-star matching: zero or more segments
# ---------------------------------------------------------------------------


class TestDoubleStarMatching:
    """'**' matches zero or more segments (including dots)."""

    def test_doublestar_matches_everything(self):
        proj = ScopeProjection(allow_patterns=["**"], deny_patterns=[])
        assert proj.permits("anything") is True
        assert proj.permits("a.b.c.d") is True

    def test_doublestar_suffix_matches_nested(self):
        proj = ScopeProjection(allow_patterns=["project.**"], deny_patterns=[])
        assert proj.permits("project.name") is True
        assert proj.permits("project.config.debug") is True
        assert proj.permits("project.a.b.c") is True

    def test_doublestar_suffix_matches_immediate_child(self):
        """'project.**' matches 'project.name' (one level)."""
        proj = ScopeProjection(allow_patterns=["project.**"], deny_patterns=[])
        assert proj.permits("project.name") is True

    def test_doublestar_suffix_does_not_match_unrelated(self):
        proj = ScopeProjection(allow_patterns=["project.**"], deny_patterns=[])
        assert proj.permits("other.name") is False
        assert proj.permits("project") is False

    def test_doublestar_zero_segments(self):
        """'a.**' should match 'a.b' (** = one segment) and deeper."""
        proj = ScopeProjection(allow_patterns=["a.**"], deny_patterns=[])
        assert proj.permits("a.b") is True
        assert proj.permits("a.b.c") is True
        # ** after a. means at least one more segment
        assert proj.permits("a") is False

    def test_doublestar_in_middle(self):
        """'a.**.z' matches 'a.z', 'a.b.z', 'a.b.c.z'."""
        proj = ScopeProjection(allow_patterns=["a.**.z"], deny_patterns=[])
        assert proj.permits("a.z") is True
        assert proj.permits("a.b.z") is True
        assert proj.permits("a.b.c.z") is True
        assert proj.permits("a.b.c") is False


# ---------------------------------------------------------------------------
# Deny precedence (INV-2)
# ---------------------------------------------------------------------------


class TestDenyPrecedence:
    """Deny takes absolute precedence over allow."""

    def test_deny_overrides_allow(self):
        proj = ScopeProjection(
            allow_patterns=["project.**"],
            deny_patterns=["project.budget"],
        )
        assert proj.permits("project.name") is True
        assert proj.permits("project.budget") is False

    def test_deny_with_glob(self):
        proj = ScopeProjection(
            allow_patterns=["project.**"],
            deny_patterns=["project.secret.*"],
        )
        assert proj.permits("project.secret.key") is False
        assert proj.permits("project.public.key") is True

    def test_deny_all_overrides_allow_all(self):
        """allow=['**'], deny=['**'] permits nothing (Edge Case 8.3)."""
        proj = ScopeProjection(allow_patterns=["**"], deny_patterns=["**"])
        assert proj.permits("anything") is False
        assert proj.permits("a.b.c") is False


# ---------------------------------------------------------------------------
# Empty projection (Edge Case 8.3)
# ---------------------------------------------------------------------------


class TestEmptyProjection:
    """Empty allow_patterns permits nothing."""

    def test_empty_allow_empty_deny(self):
        proj = ScopeProjection(allow_patterns=[], deny_patterns=[])
        assert proj.permits("anything") is False
        assert proj.permits("a.b.c") is False

    def test_empty_allow_with_deny(self):
        proj = ScopeProjection(allow_patterns=[], deny_patterns=["x"])
        assert proj.permits("x") is False
        assert proj.permits("y") is False


# ---------------------------------------------------------------------------
# Subset checks
# ---------------------------------------------------------------------------


class TestSubsetCheck:
    """ScopeProjection.is_subset_of() for monotonic tightening enforcement."""

    def test_identical_projections_are_subsets(self):
        a = ScopeProjection(allow_patterns=["project.*"], deny_patterns=[])
        b = ScopeProjection(allow_patterns=["project.*"], deny_patterns=[])
        assert a.is_subset_of(b) is True

    def test_narrower_is_subset_of_wider(self):
        narrow = ScopeProjection(allow_patterns=["project.*"], deny_patterns=[])
        wide = ScopeProjection(allow_patterns=["**"], deny_patterns=[])
        assert narrow.is_subset_of(wide) is True

    def test_wider_is_not_subset_of_narrower(self):
        wide = ScopeProjection(allow_patterns=["**"], deny_patterns=[])
        narrow = ScopeProjection(allow_patterns=["project.*"], deny_patterns=[])
        assert wide.is_subset_of(narrow) is False

    def test_empty_is_subset_of_everything(self):
        empty = ScopeProjection(allow_patterns=[], deny_patterns=[])
        any_proj = ScopeProjection(allow_patterns=["project.*"], deny_patterns=[])
        assert empty.is_subset_of(any_proj) is True

    def test_everything_is_subset_of_itself(self):
        all_proj = ScopeProjection(allow_patterns=["**"], deny_patterns=[])
        assert all_proj.is_subset_of(all_proj) is True

    def test_disjoint_not_subset(self):
        a = ScopeProjection(allow_patterns=["alpha.*"], deny_patterns=[])
        b = ScopeProjection(allow_patterns=["beta.*"], deny_patterns=[])
        assert a.is_subset_of(b) is False

    def test_deny_narrows_parent(self):
        """Child with extra deny is subset of parent without that deny."""
        child = ScopeProjection(
            allow_patterns=["project.**"],
            deny_patterns=["project.secret"],
        )
        parent = ScopeProjection(allow_patterns=["project.**"], deny_patterns=[])
        assert child.is_subset_of(parent) is True

    def test_child_allow_exceeds_parent_deny(self):
        """Child allows keys that parent denies -> not a subset."""
        child = ScopeProjection(allow_patterns=["project.**"], deny_patterns=[])
        parent = ScopeProjection(
            allow_patterns=["project.**"],
            deny_patterns=["project.secret"],
        )
        # child permits project.secret, parent does not
        assert child.is_subset_of(parent) is False


# ---------------------------------------------------------------------------
# Literal key matching
# ---------------------------------------------------------------------------


class TestLiteralKeyMatching:
    """Exact key strings (no glob chars) as patterns."""

    def test_exact_key(self):
        proj = ScopeProjection(allow_patterns=["project.name"], deny_patterns=[])
        assert proj.permits("project.name") is True
        assert proj.permits("project.budget") is False

    def test_multiple_exact_keys(self):
        proj = ScopeProjection(
            allow_patterns=["project.name", "project.budget"],
            deny_patterns=[],
        )
        assert proj.permits("project.name") is True
        assert proj.permits("project.budget") is True
        assert proj.permits("project.secret") is False


# ---------------------------------------------------------------------------
# Multiple patterns
# ---------------------------------------------------------------------------


class TestMultiplePatterns:
    """Multiple allow/deny patterns."""

    def test_multiple_allow_patterns(self):
        proj = ScopeProjection(
            allow_patterns=["project.*", "shared.*"],
            deny_patterns=[],
        )
        assert proj.permits("project.name") is True
        assert proj.permits("shared.status") is True
        assert proj.permits("secrets.key") is False

    def test_multiple_deny_patterns(self):
        proj = ScopeProjection(
            allow_patterns=["**"],
            deny_patterns=["secrets.*", "internal.*"],
        )
        assert proj.permits("project.name") is True
        assert proj.permits("secrets.key") is False
        assert proj.permits("internal.log") is False


# ---------------------------------------------------------------------------
# to_dict / from_dict round-trip
# ---------------------------------------------------------------------------


class TestProjectionSerialization:
    def test_to_dict(self):
        proj = ScopeProjection(
            allow_patterns=["project.**"],
            deny_patterns=["project.secret"],
        )
        d = proj.to_dict()
        assert d["allow_patterns"] == ["project.**"]
        assert d["deny_patterns"] == ["project.secret"]

    def test_from_dict(self):
        d = {"allow_patterns": ["a.*"], "deny_patterns": ["a.secret"]}
        proj = ScopeProjection.from_dict(d)
        assert proj.allow_patterns == ["a.*"]
        assert proj.deny_patterns == ["a.secret"]
        assert proj.permits("a.name") is True
        assert proj.permits("a.secret") is False

    def test_round_trip(self):
        original = ScopeProjection(
            allow_patterns=["x.**", "y.*"],
            deny_patterns=["x.secret"],
        )
        restored = ScopeProjection.from_dict(original.to_dict())
        assert restored.allow_patterns == original.allow_patterns
        assert restored.deny_patterns == original.deny_patterns

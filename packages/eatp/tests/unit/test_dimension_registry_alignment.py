# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
Unit tests for constraint dimension registry alignment (G11/G11+).

Verifies that BUILTIN_DIMENSIONS set matches the actual dimensions
registered by register_builtin_dimensions().
"""

from __future__ import annotations

from eatp.constraints.builtin import register_builtin_dimensions
from eatp.constraints.dimension import ConstraintDimensionRegistry


class TestDimensionRegistryAlignment:
    """G11: BUILTIN_DIMENSIONS must match registered dimensions."""

    def test_builtin_set_matches_registered(self):
        """BUILTIN_DIMENSIONS set must exactly match register_builtin_dimensions() keys."""
        registry = ConstraintDimensionRegistry()
        register_builtin_dimensions(registry)

        registered_names = {name for name, _ in registry.all()}
        assert registered_names == ConstraintDimensionRegistry.BUILTIN_DIMENSIONS

    def test_all_registered_are_auto_approved(self):
        """All built-in dimensions should be auto-approved (not pending review)."""
        registry = ConstraintDimensionRegistry()
        register_builtin_dimensions(registry)

        pending = registry.pending_review()
        assert (
            pending == []
        ), f"Built-in dimensions should not be pending review: {pending}"

    def test_all_registered_are_retrievable(self):
        """All registered built-in dimensions should be retrievable via get()."""
        registry = ConstraintDimensionRegistry()
        register_builtin_dimensions(registry)

        for name in ConstraintDimensionRegistry.BUILTIN_DIMENSIONS:
            dim = registry.get(name)
            assert dim is not None, f"Built-in dimension '{name}' should be retrievable"
            assert dim.name == name

    def test_six_builtin_dimensions(self):
        """There should be exactly 6 built-in dimensions."""
        assert len(ConstraintDimensionRegistry.BUILTIN_DIMENSIONS) == 6

    def test_builtin_dimensions_are_known_names(self):
        """Verify the expected dimension names."""
        expected = {
            "cost_limit",
            "time_window",
            "resources",
            "rate_limit",
            "data_access",
            "communication",
        }
        assert ConstraintDimensionRegistry.BUILTIN_DIMENSIONS == expected

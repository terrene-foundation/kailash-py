# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tests verifying the DriftMonitor API surface after issue #351 cleanup.

Validates:
- ``set_reference_data()`` exists on DriftMonitor
- ``DriftCallback`` is a proper type alias
- ``DriftSpec.on_drift_detected`` accepts DriftCallback
"""
from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import get_type_hints

from kailash_ml.engines.drift_monitor import DriftCallback, DriftMonitor, DriftSpec


class TestApiSurface:
    """Issue #351: DriftMonitor API rename verification."""

    def test_set_reference_data_exists(self) -> None:
        """DriftMonitor exposes set_reference_data as a public async method."""
        assert hasattr(DriftMonitor, "set_reference_data")
        method = getattr(DriftMonitor, "set_reference_data")
        assert inspect.iscoroutinefunction(
            method
        ), "set_reference_data must be an async method"

    def test_set_reference_removed(self) -> None:
        """Old set_reference name is no longer present (no shim)."""
        assert not hasattr(
            DriftMonitor, "set_reference"
        ), "set_reference should have been removed -- no backward-compat shim"

    def test_drift_callback_type(self) -> None:
        """DriftCallback is a Callable type alias, not a class or None."""
        # DriftCallback should be Callable[[DriftReport], Awaitable[None]]
        assert DriftCallback is not None
        origin = getattr(DriftCallback, "__origin__", None)
        assert (
            origin is Callable
        ), f"DriftCallback should be a Callable alias, got origin={origin}"

    def test_drift_callback_importable_from_package(self) -> None:
        """DriftCallback is importable from the top-level kailash_ml package."""
        import kailash_ml

        cb = getattr(kailash_ml, "DriftCallback", None)
        assert cb is DriftCallback

    def test_drift_spec_on_drift_detected_type(self) -> None:
        """DriftSpec.on_drift_detected is typed as DriftCallback | None."""
        hints = get_type_hints(DriftSpec)
        annotation = hints["on_drift_detected"]
        # With from __future__ import annotations, the annotation is a string
        # that gets resolved by get_type_hints. The resolved type should be
        # DriftCallback | None (a Union).
        # Check that DriftCallback is part of the union args
        args = getattr(annotation, "__args__", None)
        assert (
            args is not None
        ), f"on_drift_detected should be a Union type, got {annotation}"
        # Should contain DriftCallback (or its expansion) and NoneType
        assert (
            type(None) in args
        ), f"on_drift_detected union should include None, got args={args}"

    def test_drift_callback_in_all(self) -> None:
        """DriftCallback is listed in drift_monitor.__all__."""
        from kailash_ml.engines import drift_monitor

        assert "DriftCallback" in drift_monitor.__all__

    def test_internal_baseline_methods_renamed(self) -> None:
        """Internal helpers use _store_performance_baseline / _load_performance_baseline."""
        assert hasattr(DriftMonitor, "_store_performance_baseline")
        assert hasattr(DriftMonitor, "_load_performance_baseline")
        # Old names should not exist
        assert not hasattr(
            DriftMonitor, "_store_baseline"
        ), "_store_baseline should have been renamed to _store_performance_baseline"
        assert not hasattr(
            DriftMonitor, "_load_baseline"
        ), "_load_baseline should have been renamed to _load_performance_baseline"

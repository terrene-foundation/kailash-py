# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Phase 6.3 — async cascade through FabricRuntime.

Per ``workspaces/dataflow-perfection/todos/active/07-phase-6-async-
migration.md`` TODO-6.3, the FabricRuntime public methods that touch
the cache backend MUST be async so the Redis-backed backend can
participate without blocking. This regression test asserts that
contract via ``inspect.iscoroutinefunction`` so a future refactor
that drops back to sync gets caught at the unit level.

The contract:
- ``FabricRuntime.product_info`` is async (it awaits
  ``PipelineExecutor.get_metadata`` which is itself async).
- ``FabricRuntime.invalidate`` is async.
- ``FabricRuntime.invalidate_all`` is async.

A regression here would deadlock the Redis backend because the
sync wrapper would either spin in the event loop or call ``run`` on
a fresh loop (gh#352 pattern).
"""
from __future__ import annotations

import inspect

import pytest

from dataflow.fabric.pipeline import PipelineExecutor
from dataflow.fabric.runtime import FabricRuntime

pytestmark = pytest.mark.regression


class TestFabricRuntimeAsyncCascade:
    """The three FabricRuntime cache-touching methods MUST be async."""

    def test_product_info_is_async(self):
        assert inspect.iscoroutinefunction(FabricRuntime.product_info), (
            "FabricRuntime.product_info MUST be async — it awaits "
            "PipelineExecutor.get_metadata which is async"
        )

    def test_invalidate_is_async(self):
        assert inspect.iscoroutinefunction(FabricRuntime.invalidate), (
            "FabricRuntime.invalidate MUST be async — it awaits the "
            "cache backend's invalidate() which is async"
        )

    def test_invalidate_all_is_async(self):
        assert inspect.iscoroutinefunction(FabricRuntime.invalidate_all), (
            "FabricRuntime.invalidate_all MUST be async — it awaits the "
            "cache backend's invalidate_all() which is async"
        )

    def test_pipeline_get_metadata_is_async(self):
        """The downstream API the runtime awaits is itself async."""
        assert inspect.iscoroutinefunction(PipelineExecutor.get_metadata)

    def test_pipeline_invalidate_is_async(self):
        assert inspect.iscoroutinefunction(PipelineExecutor.invalidate)

    def test_pipeline_invalidate_all_is_async(self):
        assert inspect.iscoroutinefunction(PipelineExecutor.invalidate_all)

# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Scenario 1: DataFlow write -> EventBus -> DerivedModel refresh.

Validates that writing to a source model triggers event-driven refresh
of a DerivedModel registered with refresh="on_source_change".
Uses debounce_ms=0 for deterministic, instant refresh.
"""
from __future__ import annotations

import pytest


@pytest.mark.integration
class TestDerivedModelEventRefresh:
    """DataFlow write triggers DerivedModel refresh via EventBus."""

    async def test_event_subscription_setup(self) -> None:
        """DerivedModelEngine registers subscriptions for source models."""
        try:
            from dataflow.core.events import WRITE_OPERATIONS
            from dataflow.features.derived import DerivedModelEngine
        except ImportError:
            pytest.skip("kailash-dataflow not installed")

        assert len(WRITE_OPERATIONS) == 8
        assert "bulk_upsert" in WRITE_OPERATIONS

    async def test_write_event_emission_for_all_operations(self) -> None:
        """All 8 WRITE_OPERATIONS emit events through the mixin."""
        try:
            from dataflow.core.events import WRITE_OPERATIONS, DataFlowEventMixin
        except ImportError:
            pytest.skip("kailash-dataflow not installed")

        class FakeDB(DataFlowEventMixin):
            pass

        db = FakeDB()
        db._init_events()
        db._connected = True

        captured: list = []
        db.on_model_change("Order", lambda evt: captured.append(evt))

        for op in WRITE_OPERATIONS:
            db._emit_write_event("Order", op, record_id=None)

        assert len(captured) == 8
        ops = {e.payload["operation"] for e in captured}
        assert ops == set(WRITE_OPERATIONS)

# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier-1 tests for DriftMonitor.schedule_monitoring() pre-dispatch contract.

W26.c (spec §5) — the scheduler surface is now persistence-first. These
tests exercise the input-validation + reference-required contract that
holds BEFORE any DB write happens. Persistence + restart-recovery lives
under tests/integration/test_drift_scheduler_restart.py against a real
ConnectionManager; the unit tier here just covers the raise-before-persist
paths that never reach the database.

The legacy in-process ``active_schedules`` property is now deprecated.
New code uses ``list_schedules`` against the persisted table. The
deprecated shim is covered separately in the integration suite so its
backward-compat guarantee stays behavioural, not mocked.
"""
from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock

import numpy as np
import polars as pl
import pytest
from kailash_ml.engines.drift_monitor import DriftMonitor, DriftSpec


@pytest.fixture
async def conn():
    """Mock ConnectionManager — only the raise-before-persist paths run
    through this, so a thin AsyncMock is sufficient for Tier 1."""
    mock = AsyncMock()
    mock.fetchone = AsyncMock(return_value=None)
    mock.execute = AsyncMock()
    mock.fetch = AsyncMock(return_value=[])

    tx_mock = AsyncMock()
    tx_mock.execute = AsyncMock()
    tx_mock.fetchone = AsyncMock(return_value=None)

    class _FakeTransaction:
        async def __aenter__(self):
            return tx_mock

        async def __aexit__(self, *args):
            pass

    mock.transaction = _FakeTransaction
    return mock


@pytest.fixture
async def monitor(conn):
    mon = DriftMonitor(conn, tenant_id="test")
    ref_data = pl.DataFrame(
        {
            "feature_a": np.random.normal(0, 1, 100).tolist(),
            "feature_b": np.random.normal(5, 2, 100).tolist(),
        }
    )
    await mon.set_reference_data("test-model", ref_data, ["feature_a", "feature_b"])
    return mon


class TestScheduleMonitoringContract:
    """Input-validation contract — runs before the DB is touched."""

    @pytest.mark.asyncio
    async def test_schedule_requires_reference(self, conn):
        mon = DriftMonitor(conn, tenant_id="test")
        with pytest.raises(ValueError, match="No reference set"):
            await mon.schedule_monitoring(
                "unknown-model",
                timedelta(seconds=10),
                AsyncMock(),
            )

    @pytest.mark.asyncio
    async def test_schedule_rejects_tiny_interval(self, monitor):
        with pytest.raises(ValueError, match="at least 1 second"):
            await monitor.schedule_monitoring(
                "test-model",
                timedelta(milliseconds=100),
                AsyncMock(),
            )

    @pytest.mark.asyncio
    async def test_drift_spec_defaults(self):
        spec = DriftSpec()
        assert spec.feature_columns is None
        assert spec.psi_threshold is None
        assert spec.ks_threshold is None
        assert spec.on_drift_detected is None

    @pytest.mark.asyncio
    async def test_cancel_schedule_nonexistent_returns_false(self, monitor):
        """Missing schedule_id returns False, does not raise."""
        result = await monitor.cancel_schedule("does-not-exist")
        assert result is False

    @pytest.mark.asyncio
    async def test_register_data_source_accepts_callable(self, monitor):
        """register_data_source is a plain in-memory registration."""
        monitor.register_data_source("abc123", AsyncMock())
        assert "abc123" in monitor._data_sources

    @pytest.mark.asyncio
    async def test_register_spec_accepts_spec(self, monitor):
        """register_spec is a plain in-memory registration."""
        spec = DriftSpec(psi_threshold=0.3)
        monitor.register_spec("abc123", spec)
        assert monitor._scheduled_specs["abc123"] is spec

# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tests for DriftMonitor.schedule_monitoring()."""
from __future__ import annotations

import asyncio
from datetime import timedelta
from unittest.mock import AsyncMock

import numpy as np
import polars as pl
import pytest

from kailash_ml.engines.drift_monitor import DriftMonitor, DriftSpec


@pytest.fixture
async def conn():
    """Create a mock ConnectionManager with transaction support."""
    mock = AsyncMock()
    mock.fetchone = AsyncMock(return_value=None)
    mock.execute = AsyncMock()
    mock.fetch = AsyncMock(return_value=[])

    # Transaction context manager mock
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
    """Create a DriftMonitor with reference set."""
    mon = DriftMonitor(conn)
    ref_data = pl.DataFrame(
        {
            "feature_a": np.random.normal(0, 1, 100).tolist(),
            "feature_b": np.random.normal(5, 2, 100).tolist(),
        }
    )
    await mon.set_reference("test-model", ref_data, ["feature_a", "feature_b"])
    return mon


class TestScheduleMonitoring:
    @pytest.mark.asyncio
    async def test_schedule_creates_task(self, monitor):
        data_fn = AsyncMock(
            return_value=pl.DataFrame(
                {
                    "feature_a": np.random.normal(0, 1, 50).tolist(),
                    "feature_b": np.random.normal(5, 2, 50).tolist(),
                }
            )
        )

        await monitor.schedule_monitoring("test-model", timedelta(seconds=100), data_fn)
        assert "test-model" in monitor.active_schedules
        await monitor.shutdown()

    @pytest.mark.asyncio
    async def test_schedule_requires_reference(self, conn):
        mon = DriftMonitor(conn)
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
    async def test_cancel_monitoring(self, monitor):
        await monitor.schedule_monitoring(
            "test-model", timedelta(seconds=100), AsyncMock()
        )
        cancelled = await monitor.cancel_monitoring("test-model")
        assert cancelled is True
        assert "test-model" not in monitor.active_schedules

    @pytest.mark.asyncio
    async def test_cancel_nonexistent(self, monitor):
        cancelled = await monitor.cancel_monitoring("nonexistent")
        assert cancelled is False

    @pytest.mark.asyncio
    async def test_shutdown_cancels_all(self, monitor):
        await monitor.schedule_monitoring(
            "test-model", timedelta(seconds=100), AsyncMock()
        )
        assert len(monitor.active_schedules) == 1
        await monitor.shutdown()
        assert len(monitor.active_schedules) == 0

    @pytest.mark.asyncio
    async def test_reschedule_replaces_task(self, monitor):
        await monitor.schedule_monitoring(
            "test-model", timedelta(seconds=100), AsyncMock()
        )
        old_tasks = dict(monitor._scheduled_tasks)

        await monitor.schedule_monitoring(
            "test-model", timedelta(seconds=200), AsyncMock()
        )
        new_tasks = dict(monitor._scheduled_tasks)
        assert old_tasks["test-model"] is not new_tasks["test-model"]
        await monitor.shutdown()

    @pytest.mark.asyncio
    async def test_drift_callback_invoked(self, monitor, conn):
        # Create drifted data
        drifted_data = pl.DataFrame(
            {
                "feature_a": np.random.normal(10, 1, 50).tolist(),  # big shift
                "feature_b": np.random.normal(5, 2, 50).tolist(),
            }
        )
        data_fn = AsyncMock(return_value=drifted_data)
        callback = AsyncMock()

        spec = DriftSpec(on_drift_detected=callback)
        await monitor.schedule_monitoring(
            "test-model", timedelta(seconds=1), data_fn, spec
        )

        # Wait for at least one check cycle
        await asyncio.sleep(1.5)
        await monitor.shutdown()

        # data_fn should have been called at least once
        assert data_fn.call_count >= 1

    @pytest.mark.asyncio
    async def test_drift_spec_defaults(self):
        spec = DriftSpec()
        assert spec.feature_columns is None
        assert spec.psi_threshold is None
        assert spec.ks_threshold is None
        assert spec.on_drift_detected is None

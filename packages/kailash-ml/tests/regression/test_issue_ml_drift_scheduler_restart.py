# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression: drift schedules MUST survive DriftMonitor recreation.

Round-1 HIGH finding (mlops-governance §11): "DriftMonitor
.schedule_monitoring is in-process asyncio.create_task + stores in
self._scheduled_tasks. When the process dies, the schedule dies. No
cron, no journal, no resume."

W26.c closes that: schedules persist to ``_kml_drift_schedules`` before
dispatch, and a fresh DriftMonitor against the same ConnectionManager
(or, in the full restart case, a fresh ConnectionManager against the
same SQLite file) can recover every schedule via
``list_schedules(model_name=...)``.

This regression is intentionally minimal — the full restart-recovery
story lives in tests/integration/test_drift_scheduler_restart.py. The
file here guards the narrow contract: "a recreated DriftMonitor on the
SAME backing store sees every previously-registered schedule".
"""
from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock

import numpy as np
import polars as pl
import pytest
from kailash.db.connection import ConnectionManager
from kailash_ml.engines.drift_monitor import DriftMonitor


_FEATURES = ["feature_a", "feature_b"]


def _make_reference_df(n: int = 200) -> pl.DataFrame:
    rng = np.random.RandomState(42)
    return pl.DataFrame(
        {
            "feature_a": rng.normal(0, 1, n).tolist(),
            "feature_b": rng.normal(5, 2, n).tolist(),
        }
    )


@pytest.mark.regression
@pytest.mark.asyncio
async def test_issue_drift_scheduler_recreated_monitor_recovers_schedule(
    tmp_path,
) -> None:
    """Regression: schedule MUST be visible after DriftMonitor recreation.

    Pre-W26.c: ``schedule_monitoring`` stored in ``_scheduled_tasks``
    only — a recreated ``DriftMonitor`` had an empty task map and the
    schedule was gone.

    Post-W26.c: ``schedule_monitoring`` writes to ``_kml_drift_schedules``
    first; the recreated monitor reads it back via ``list_schedules``.
    """
    db_path = tmp_path / "regression.db"
    conn = ConnectionManager(f"sqlite:///{db_path}")
    await conn.initialize()
    try:
        monitor_v1 = DriftMonitor(conn, tenant_id="acme")
        await monitor_v1.set_reference_data("fraud", _make_reference_df(), _FEATURES)
        schedule_id = await monitor_v1.schedule_monitoring(
            "fraud",
            interval=timedelta(seconds=60),
            data_fn=AsyncMock(),
            actor_id="agent-42",
        )

        # Recreate the monitor against the SAME ConnectionManager — this
        # is the narrow regression the pre-W26.c code failed.
        monitor_v2 = DriftMonitor(conn, tenant_id="acme")
        schedules = await monitor_v2.list_schedules(model_name="fraud")
        assert len(schedules) == 1
        recovered = schedules[0]
        assert recovered["schedule_id"] == schedule_id
        assert recovered["enabled"] is True
        assert recovered["interval_seconds"] == 60
    finally:
        await conn.close()


@pytest.mark.regression
@pytest.mark.asyncio
async def test_issue_drift_scheduler_cross_tenant_schedules_do_not_leak_across_restart(
    tmp_path,
) -> None:
    """W26.e regression: two tenants schedule the same model_name; each
    recreated monitor sees ONLY its own schedule, even though both rows
    live in the same ``_kml_drift_schedules`` table.

    Pre-W26.e the pre-cancel lookup was not tenant-scoped, so a restart
    could surface rows across tenants if the schedule_id happened to
    collide in a future run.
    """
    db_path = tmp_path / "cross_tenant_restart.db"
    conn = ConnectionManager(f"sqlite:///{db_path}")
    await conn.initialize()
    try:
        # Pre-restart: both tenants schedule the same model_name.
        m_acme_v1 = DriftMonitor(conn, tenant_id="acme")
        m_bob_v1 = DriftMonitor(conn, tenant_id="bob")
        await m_acme_v1.set_reference_data("fraud", _make_reference_df(), _FEATURES)
        await m_bob_v1.set_reference_data("fraud", _make_reference_df(), _FEATURES)
        id_acme = await m_acme_v1.schedule_monitoring(
            "fraud", interval=timedelta(seconds=60), data_fn=AsyncMock()
        )
        id_bob = await m_bob_v1.schedule_monitoring(
            "fraud", interval=timedelta(seconds=60), data_fn=AsyncMock()
        )

        # Post-restart: fresh monitors against the same DB.
        m_acme_v2 = DriftMonitor(conn, tenant_id="acme")
        m_bob_v2 = DriftMonitor(conn, tenant_id="bob")

        acme_rows = await m_acme_v2.list_schedules()
        bob_rows = await m_bob_v2.list_schedules()

        assert [r["schedule_id"] for r in acme_rows] == [id_acme]
        assert [r["schedule_id"] for r in bob_rows] == [id_bob]
        # Cross-tenant non-leakage: acme MUST NOT see bob's row.
        assert id_bob not in {r["schedule_id"] for r in acme_rows}
        assert id_acme not in {r["schedule_id"] for r in bob_rows}
    finally:
        await conn.close()

# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier-1 tests for DriftMonitor.schedule_monitoring persistence contract.

W26.c (spec §5) — schedules are written to ``_kml_drift_schedules`` BEFORE
any in-process dispatch. These tests verify the row is written with the
expected shape via a direct SELECT through ConnectionManager against a
real SQLite :memory: backend. The scheduler worker is NOT started here —
that is exercised end-to-end in the integration suite.
"""
from __future__ import annotations

import re
from datetime import timedelta
from unittest.mock import AsyncMock

import numpy as np
import polars as pl
import pytest
from kailash.db.connection import ConnectionManager
from kailash_ml.engines.drift_monitor import DriftMonitor


_UUID4_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


@pytest.fixture
async def conn():
    cm = ConnectionManager("sqlite://:memory:")
    await cm.initialize()
    yield cm
    await cm.close()


@pytest.fixture
async def monitor(conn: ConnectionManager) -> DriftMonitor:
    mon = DriftMonitor(conn, tenant_id="acme")
    ref_data = pl.DataFrame(
        {
            "feature_a": np.random.normal(0, 1, 100).tolist(),
            "feature_b": np.random.normal(5, 2, 100).tolist(),
        }
    )
    await mon.set_reference_data("fraud", ref_data, ["feature_a", "feature_b"])
    await mon.set_reference_data("churn", ref_data, ["feature_a", "feature_b"])
    return mon


async def _fetch_schedule(conn: ConnectionManager, schedule_id: str):
    return await conn.fetchone(
        "SELECT * FROM _kml_drift_schedules WHERE schedule_id = ?",
        schedule_id,
    )


@pytest.mark.asyncio
async def test_schedule_monitoring_returns_uuid4(monitor: DriftMonitor) -> None:
    data_fn = AsyncMock()
    schedule_id = await monitor.schedule_monitoring(
        "fraud", timedelta(seconds=60), data_fn, actor_id="agent-42"
    )
    assert isinstance(schedule_id, str)
    assert _UUID4_RE.match(schedule_id), f"not a uuid4: {schedule_id!r}"


@pytest.mark.asyncio
async def test_schedule_monitoring_writes_row(
    monitor: DriftMonitor, conn: ConnectionManager
) -> None:
    schedule_id = await monitor.schedule_monitoring(
        "fraud",
        timedelta(seconds=120),
        AsyncMock(),
        actor_id="agent-42",
    )
    row = await _fetch_schedule(conn, schedule_id)
    assert row is not None
    assert row["model_name"] == "fraud"
    assert row["interval_seconds"] == 120
    # SQLite stores enabled as INTEGER 0/1 — bool check at the dict layer
    assert bool(row["enabled"]) is True
    # W26.e: tenant_id comes from the monitor's constructor, not a kwarg.
    assert row["tenant_id"] == "acme"
    assert row["created_by_actor_id"] == "agent-42"
    assert row["next_run_at"] is not None


@pytest.mark.asyncio
async def test_schedule_monitoring_accepts_caller_supplied_id(
    monitor: DriftMonitor, conn: ConnectionManager
) -> None:
    """Callers may supply a schedule_id to pre-assign the PK (useful
    when re-registering a schedule after a restart)."""
    fixed_id = "00000000-0000-4000-8000-000000000001"
    returned = await monitor.schedule_monitoring(
        "fraud",
        timedelta(seconds=60),
        AsyncMock(),
        schedule_id=fixed_id,
    )
    assert returned == fixed_id
    row = await _fetch_schedule(conn, fixed_id)
    assert row is not None
    assert row["schedule_id"] == fixed_id


@pytest.mark.asyncio
async def test_cancel_schedule_disables_row(
    monitor: DriftMonitor, conn: ConnectionManager
) -> None:
    schedule_id = await monitor.schedule_monitoring(
        "fraud", timedelta(seconds=60), AsyncMock()
    )
    result = await monitor.cancel_schedule(
        schedule_id, actor_id="agent-42", reason="unit-test"
    )
    assert result is True
    row = await _fetch_schedule(conn, schedule_id)
    assert row is not None
    assert bool(row["enabled"]) is False


@pytest.mark.asyncio
async def test_cancel_schedule_twice_returns_false(
    monitor: DriftMonitor,
) -> None:
    schedule_id = await monitor.schedule_monitoring(
        "fraud", timedelta(seconds=60), AsyncMock()
    )
    first = await monitor.cancel_schedule(schedule_id)
    assert first is True
    second = await monitor.cancel_schedule(schedule_id)
    # Already disabled — returns False (not raises).
    assert second is False


@pytest.mark.asyncio
async def test_cancel_schedule_missing_returns_false(
    monitor: DriftMonitor,
) -> None:
    assert await monitor.cancel_schedule("nonexistent-id") is False


@pytest.mark.asyncio
async def test_list_schedules_filters_by_model_name(
    monitor: DriftMonitor,
) -> None:
    id_fraud = await monitor.schedule_monitoring(
        "fraud", timedelta(seconds=60), AsyncMock()
    )
    id_churn = await monitor.schedule_monitoring(
        "churn", timedelta(seconds=60), AsyncMock()
    )
    fraud_rows = await monitor.list_schedules(model_name="fraud")
    churn_rows = await monitor.list_schedules(model_name="churn")
    assert [r["schedule_id"] for r in fraud_rows] == [id_fraud]
    assert [r["schedule_id"] for r in churn_rows] == [id_churn]


@pytest.mark.asyncio
async def test_list_schedules_enabled_only_filter(
    monitor: DriftMonitor,
) -> None:
    id_a = await monitor.schedule_monitoring(
        "fraud", timedelta(seconds=60), AsyncMock()
    )
    id_b = await monitor.schedule_monitoring(
        "fraud", timedelta(seconds=60), AsyncMock()
    )
    await monitor.cancel_schedule(id_b)

    enabled = await monitor.list_schedules(model_name="fraud", enabled_only=True)
    assert [r["schedule_id"] for r in enabled] == [id_a]

    all_rows = await monitor.list_schedules(model_name="fraud", enabled_only=False)
    ids = {r["schedule_id"] for r in all_rows}
    assert ids == {id_a, id_b}


@pytest.mark.asyncio
async def test_list_schedules_filters_by_monitor_tenant(
    conn: ConnectionManager,
) -> None:
    """W26.e: each DriftMonitor is bound to one tenant. list_schedules
    always filters by the monitor's tenant — cross-tenant lookups require
    constructing a second monitor."""
    ref_data = pl.DataFrame(
        {
            "feature_a": np.random.normal(0, 1, 100).tolist(),
            "feature_b": np.random.normal(5, 2, 100).tolist(),
        }
    )
    mon_acme = DriftMonitor(conn, tenant_id="acme")
    mon_bob = DriftMonitor(conn, tenant_id="bob")
    await mon_acme.set_reference_data("fraud", ref_data, ["feature_a", "feature_b"])
    await mon_bob.set_reference_data("fraud", ref_data, ["feature_a", "feature_b"])

    id_acme = await mon_acme.schedule_monitoring(
        "fraud", timedelta(seconds=60), AsyncMock()
    )
    id_bob = await mon_bob.schedule_monitoring(
        "fraud", timedelta(seconds=60), AsyncMock()
    )

    acme_rows = await mon_acme.list_schedules()
    bob_rows = await mon_bob.list_schedules()
    assert [r["schedule_id"] for r in acme_rows] == [id_acme]
    assert [r["schedule_id"] for r in bob_rows] == [id_bob]
    # Extra assertion: cross-tenant isolation — acme cannot see bob's row
    # and vice versa even though both live in the same table.
    assert id_bob not in [r["schedule_id"] for r in acme_rows]
    assert id_acme not in [r["schedule_id"] for r in bob_rows]


@pytest.mark.asyncio
async def test_list_schedules_returns_boolean_enabled(
    monitor: DriftMonitor,
) -> None:
    """SQLite stores enabled as INTEGER; list_schedules projects to bool."""
    await monitor.schedule_monitoring("fraud", timedelta(seconds=60), AsyncMock())
    rows = await monitor.list_schedules()
    assert len(rows) == 1
    assert isinstance(rows[0]["enabled"], bool)
    assert rows[0]["enabled"] is True

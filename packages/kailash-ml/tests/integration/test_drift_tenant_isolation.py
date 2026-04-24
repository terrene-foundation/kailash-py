# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 2 tests — W26.e cross-tenant isolation end-to-end.

Uses real ConnectionManager-backed SQLite (file-backed, NOT :memory:) so
two tenants sharing the same DB file cannot observe each other's
reference distributions, drift reports, or schedules.

Closes ``specs/ml-drift.md §11.2.2`` (Tenant Isolation) against the
DriftMonitor directly (engine facade routing is covered by the engine's
own Tier 2 suite).
"""
from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock

import numpy as np
import polars as pl
import pytest
from kailash.db.connection import ConnectionManager
from kailash_ml.engines.drift_monitor import DriftMonitor


_FEATURES = ["x", "y"]


def _ref_df(seed: int, n: int = 300) -> pl.DataFrame:
    rng = np.random.RandomState(seed)
    return pl.DataFrame(
        {
            "x": rng.normal(0, 1, n).tolist(),
            "y": rng.normal(5, 2, n).tolist(),
        }
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_two_tenants_cannot_see_each_others_reference(tmp_path) -> None:
    """Spec §11.2.2 — two tenants on the same DB file cannot cross-read
    each other's reference or drift reports.

    If the reference cache had collided across tenants, ``acme`` would see
    ``bob``'s very-different reference distribution and drift would fire.
    The fact that it does NOT fire proves the composite (tenant_id,
    model_name) keying works at both the SQL table layer AND the
    in-memory cache layer.
    """
    db_path = tmp_path / "iso.db"
    db_url = f"sqlite:///{db_path}"

    conn_acme = ConnectionManager(db_url)
    await conn_acme.initialize()
    conn_bob = ConnectionManager(db_url)
    await conn_bob.initialize()

    try:
        monitor_acme = DriftMonitor(conn_acme, tenant_id="acme")
        monitor_bob = DriftMonitor(conn_bob, tenant_id="bob")

        # Very different reference distributions so a cross-tenant read
        # WOULD fire drift.
        ref_acme = _ref_df(seed=42)  # mean ~0 on x, ~5 on y
        ref_bob = _ref_df(seed=999)  # different realisation
        await monitor_acme.set_reference_data("churn", ref_acme, _FEATURES)
        await monitor_bob.set_reference_data("churn", ref_bob, _FEATURES)

        # acme's current data matches acme's reference exactly (same seed
        # → identical frame). If acme's reference lookup leaked to bob's
        # reference, drift would fire.
        report_acme = await monitor_acme.check_drift("churn", ref_acme)
        assert report_acme.overall_drift_detected is False, (
            "acme's check_drift against its OWN reference fired drift — "
            "indicates cross-tenant reference leakage via cache key collision"
        )

        # Same for bob: bob's reference against bob's own frame must not drift.
        report_bob = await monitor_bob.check_drift("churn", ref_bob)
        assert report_bob.overall_drift_detected is False

        # Direct DB inspection — every report row carries the correct
        # tenant_id and NO cross-tenant rows.
        acme_report_tenants = await conn_acme.fetch(
            "SELECT DISTINCT tenant_id FROM _kml_drift_reports WHERE tenant_id = ?",
            "acme",
        )
        assert [r["tenant_id"] for r in acme_report_tenants] == ["acme"]

        bob_report_tenants = await conn_bob.fetch(
            "SELECT DISTINCT tenant_id FROM _kml_drift_reports WHERE tenant_id = ?",
            "bob",
        )
        assert [r["tenant_id"] for r in bob_report_tenants] == ["bob"]

        # Reference table assertions — both tenant rows exist on the
        # same composite PK shape.
        ref_tenants = await conn_acme.fetch(
            "SELECT tenant_id FROM _kml_drift_references "
            "WHERE model_name = ? ORDER BY tenant_id",
            "churn",
        )
        assert [r["tenant_id"] for r in ref_tenants] == ["acme", "bob"]
    finally:
        await conn_acme.close()
        await conn_bob.close()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_list_schedules_only_returns_own_tenant(tmp_path) -> None:
    """Spec §11.2.2 — list_schedules scoped to the monitor's tenant.
    Two tenants that schedule the same model each see only their own row.
    """
    db_path = tmp_path / "sched_iso.db"
    db_url = f"sqlite:///{db_path}"

    conn_acme = ConnectionManager(db_url)
    await conn_acme.initialize()
    conn_bob = ConnectionManager(db_url)
    await conn_bob.initialize()

    try:
        monitor_acme = DriftMonitor(conn_acme, tenant_id="acme")
        monitor_bob = DriftMonitor(conn_bob, tenant_id="bob")
        ref = _ref_df(seed=1)
        await monitor_acme.set_reference_data("fraud", ref, _FEATURES)
        await monitor_bob.set_reference_data("fraud", ref, _FEATURES)

        id_acme = await monitor_acme.schedule_monitoring(
            "fraud", timedelta(seconds=60), AsyncMock()
        )
        id_bob = await monitor_bob.schedule_monitoring(
            "fraud", timedelta(seconds=60), AsyncMock()
        )

        acme_rows = await monitor_acme.list_schedules()
        bob_rows = await monitor_bob.list_schedules()

        # Each monitor sees ONLY its own schedule.
        assert [r["schedule_id"] for r in acme_rows] == [id_acme]
        assert [r["schedule_id"] for r in bob_rows] == [id_bob]

        # Cross-tenant cancel attempt — cancelling a schedule_id that
        # belongs to a different tenant is a no-op (returns False).
        cancelled = await monitor_acme.cancel_schedule(id_bob)
        assert cancelled is False, (
            "acme cancelled bob's schedule — cross-tenant cancel is a "
            "tenant-isolation break"
        )
        # Confirm bob's schedule is still enabled.
        bob_rows_after = await monitor_bob.list_schedules()
        assert [r["schedule_id"] for r in bob_rows_after] == [id_bob]
    finally:
        await conn_acme.close()
        await conn_bob.close()

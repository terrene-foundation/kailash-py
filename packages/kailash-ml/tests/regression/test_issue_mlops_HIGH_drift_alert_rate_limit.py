# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression: ``max_alerts_per_hour`` enforces per-tenant.

Round-1 HIGH finding (mlops-governance §11): "Alert rate-limit is
global across tenants — one noisy tenant exhausts the hourly budget
for every other tenant."

W26.d introduced per-``(tenant_id, model_name)`` rolling-hour windows
in :class:`DriftAlertDispatcher`. W26.e makes the tenant scope
mandatory at ``DriftMonitor.__init__`` so the dispatcher ALWAYS
receives a real tenant on the cooldown / rate-limit key — no empty-
tenant fallback.

This regression exercises two DriftMonitor instances (one per tenant)
against the same shared DB + dispatcher channel list. Each tenant gets
its own hourly budget; filling tenant A's budget does NOT suppress
tenant B's alerts.
"""
from __future__ import annotations

import numpy as np
import polars as pl
import pytest
from kailash.db.connection import ConnectionManager
from kailash_ml.drift.alerts import (
    AlertConfig,
    AlertRule,
    DriftAlert,
)
from kailash_ml.engines.drift_monitor import DriftMonitor


class _RecordingChannel:
    def __init__(self) -> None:
        self.received: list[DriftAlert] = []

    async def send(self, alert: DriftAlert) -> None:
        self.received.append(alert)


def _make_reference_df(n: int = 200) -> pl.DataFrame:
    rng = np.random.RandomState(42)
    return pl.DataFrame({"x": rng.normal(0, 1, n).tolist()})


def _make_drifted_df(n: int = 200) -> pl.DataFrame:
    rng = np.random.RandomState(7)
    return pl.DataFrame({"x": rng.normal(3.0, 1, n).tolist()})


@pytest.mark.regression
@pytest.mark.asyncio
async def test_issue_drift_alert_rate_limit_is_per_tenant(tmp_path) -> None:
    """Each tenant carries its own hourly alert budget. Tenant ``acme``
    hitting the limit MUST NOT suppress tenant ``bob``'s alerts — both
    get their own budget."""
    db_path = tmp_path / "rate_limit.db"
    conn = ConnectionManager(f"sqlite:///{db_path}")
    await conn.initialize()
    try:
        # Each monitor gets its own channel so the assertions stay
        # tenant-scoped — we assert the per-channel count, which equals
        # the per-tenant dispatched count.
        ch_acme = _RecordingChannel()
        ch_bob = _RecordingChannel()
        cfg_acme = AlertConfig(
            channels=(ch_acme,),
            per_axis_rules={
                "feature": AlertRule(
                    trigger="any_column", threshold=0.1, severity="warning"
                )
            },
            cooldown_seconds=0,  # disable cooldown — isolate rate-limit
            max_alerts_per_hour=3,
        )
        cfg_bob = AlertConfig(
            channels=(ch_bob,),
            per_axis_rules={
                "feature": AlertRule(
                    trigger="any_column", threshold=0.1, severity="warning"
                )
            },
            cooldown_seconds=0,
            max_alerts_per_hour=3,
        )

        monitor_acme = DriftMonitor(conn, tenant_id="acme", alerts=cfg_acme)
        monitor_bob = DriftMonitor(conn, tenant_id="bob", alerts=cfg_bob)
        await monitor_acme.set_reference_data("m", _make_reference_df(), ["x"])
        await monitor_bob.set_reference_data("m", _make_reference_df(), ["x"])

        drifted = _make_drifted_df()

        # Fill acme's hourly budget — 10 checks, capped at 3 dispatches.
        for _ in range(10):
            await monitor_acme.check_drift("m", drifted)

        assert len(ch_acme.received) == 3, (
            f"acme dispatched {len(ch_acme.received)} alerts; expected "
            f"exactly 3 (max_alerts_per_hour). Rate limit not enforced."
        )

        # Now bob runs one check — MUST dispatch an alert because bob's
        # budget is independent. Pre-W26.d this was global state.
        await monitor_bob.check_drift("m", drifted)
        assert len(ch_bob.received) == 1, (
            f"bob dispatched {len(ch_bob.received)} alerts after one "
            f"check; expected exactly 1. Cross-tenant rate-limit "
            f"leakage detected."
        )
    finally:
        await conn.close()

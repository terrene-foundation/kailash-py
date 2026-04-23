# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression: W26.d drift alerting smoke test.

Guards the minimum contract that ``DriftMonitor(alerts=...)`` wires
the dispatcher and fires at least one alert on a known-drifted
dataset.

Behavioral per rules/testing.md § "Behavioral Regression Tests Over
Source-Grep": exercises the real ``check_drift`` path and asserts
the channel captured an alert with the expected axis + severity.
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


@pytest.mark.regression
@pytest.mark.asyncio
async def test_w26d_drift_alerts_smoke(tmp_path) -> None:
    """Regression: construct DriftMonitor with AlertConfig, run one
    check_drift with a known-drifted frame, assert one alert landed."""
    conn = ConnectionManager(f"sqlite:///{tmp_path}/smoke.db")
    await conn.initialize()

    channel = _RecordingChannel()
    cfg = AlertConfig(
        channels=(channel,),
        per_axis_rules={"feature": AlertRule("model_score", threshold=0.1)},
        cooldown_seconds=60,
        max_alerts_per_hour=5,
    )
    monitor = DriftMonitor(conn, alerts=cfg)

    rng = np.random.RandomState(42)
    ref = pl.DataFrame({"x": rng.normal(0, 1, 500).tolist()})
    drifted = pl.DataFrame({"x": rng.normal(3.0, 1, 500).tolist()})

    await monitor.set_reference_data("m", ref, ["x"])
    await monitor.check_drift("m", drifted, tenant_id="t1")

    assert len(channel.received) == 1
    alert = channel.received[0]
    assert alert.axis == "feature"
    assert alert.model_name == "m"
    assert alert.tenant_id == "t1"
    assert alert.severity == "warning"
    assert alert.drift_score >= 0.1

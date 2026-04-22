# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression: ``DriftMonitorReferencePolicy`` round-trips through SQLite.

Guards against the W26.b-recurrence failure mode where a refactor
drops the ``policy_json`` / ``timestamp_column`` columns from
``_kml_drift_references``, silently degrading every monitor back to
static mode on DB round-trip.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import polars as pl
import pytest
from kailash_ml.drift.policy import DriftMonitorReferencePolicy
from kailash_ml.engines.drift_monitor import DriftMonitor

from kailash.db.connection import ConnectionManager


@pytest.mark.regression
async def test_drift_policy_round_trip_through_sqlite(tmp_path) -> None:
    """W26.b: policy_json + timestamp_column persist across
    set_reference_data → raw DB read → policy deserialisation."""
    db_path = tmp_path / "drift_policy_regression.db"
    cm = ConnectionManager(f"sqlite:///{db_path}")
    await cm.initialize()
    try:
        monitor = DriftMonitor(cm)

        start = datetime(2026, 3, 2, 0, 0, 0, tzinfo=timezone.utc)
        rows = [
            {
                "ts": start + timedelta(hours=h),
                "value": float(h),
            }
            for h in range(168)
        ]
        df = pl.DataFrame(rows).with_columns(
            pl.col("ts").cast(pl.Datetime(time_unit="us", time_zone="UTC"))
        )

        policy = DriftMonitorReferencePolicy(mode="rolling", window=timedelta(days=7))
        await monitor.set_reference_data(
            "regression-m1",
            df,
            ["value"],
            policy=policy,
            timestamp_column="ts",
        )

        row = await cm.fetchone(
            "SELECT policy_json, timestamp_column "
            "FROM _kml_drift_references WHERE model_name = ?",
            "regression-m1",
        )
        assert row is not None
        assert row["timestamp_column"] == "ts"

        restored = DriftMonitorReferencePolicy.from_dict(json.loads(row["policy_json"]))
        assert restored == policy
    finally:
        await cm.close()

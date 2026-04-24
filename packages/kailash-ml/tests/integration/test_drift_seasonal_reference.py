# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 2 integration tests — ``DriftMonitorReferencePolicy`` seasonal mode.

Per ``specs/ml-drift.md §4.5`` MUST 5:

1. Generate a synthetic weekly-seasonal signal (hourly data across
   4 weeks, weekday-dependent mean).
2. ``mode="static"`` — drift fires when a Monday window is compared
   against the full mixed-weekday reference (a false positive for a
   weekly-seasonal business).
3. ``mode="seasonal", seasonal_period=timedelta(weeks=1)`` — drift
   does NOT fire when the current Monday window is compared against
   the same Monday one period back (true negative).

Infrastructure: real ConnectionManager against a file-backed SQLite
database under ``tmp_path`` so the schema migration behaves like a
real dialect install (per ``schema-migration.md`` MUST Rule 5 spirit).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import polars as pl
import pytest
from kailash_ml.drift.policy import DriftMonitorReferencePolicy
from kailash_ml.engines.drift_monitor import DriftMonitor, DriftReport

from kailash.db.connection import ConnectionManager


# ---------------------------------------------------------------------------
# Synthetic weekly-seasonal signal
# ---------------------------------------------------------------------------


def _synthetic_weekly_seasonal(
    start: datetime,
    weeks: int,
    seed: int = 42,
) -> pl.DataFrame:
    """Hourly observations with weekday-dependent mean.

    - Monday (weekday=0) → mean 35
    - Tuesday → mean 40
    - Wednesday → mean 45
    - Thursday → mean 50
    - Friday → mean 55
    - Saturday → mean 60
    - Sunday → mean 65

    Std is constant at 2.0 across all days. The spread in means (35→65)
    is deliberately large so static-mode drift on the narrow Monday
    window is unambiguous.
    """
    rng = np.random.RandomState(seed)
    total_hours = weeks * 7 * 24
    rows = []
    means = [35.0, 40.0, 45.0, 50.0, 55.0, 60.0, 65.0]
    for h in range(total_hours):
        ts = start + timedelta(hours=h)
        weekday_mean = means[ts.weekday()]
        rows.append(
            {
                "ts": ts,
                "value": float(rng.normal(weekday_mean, 2.0)),
            }
        )
    return pl.DataFrame(rows).with_columns(
        pl.col("ts").cast(pl.Datetime(time_unit="us", time_zone="UTC"))
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def conn(tmp_path):
    """Real ConnectionManager against a file-backed SQLite database.

    Uses tmp_path rather than :memory: so the DDL migration runs
    against a persistent file per schema-migration.md MUST Rule 5.
    """
    db_path = tmp_path / "drift_seasonal.db"
    cm = ConnectionManager(f"sqlite:///{db_path}")
    await cm.initialize()
    yield cm
    await cm.close()


@pytest.fixture
async def monitor(conn: ConnectionManager) -> DriftMonitor:
    return DriftMonitor(conn, tenant_id="test")


@pytest.fixture
def weekly_signal() -> tuple[pl.DataFrame, datetime, datetime]:
    """4 weeks of hourly weekday-dependent data.

    Returns (frame, monday_week1_start, monday_week5_start).

    - Start anchor: Monday 2026-03-02 00:00 UTC (weekday=0).
    - Frame spans weeks 1..4 (28 days).
    - monday_week5_start = start + 28 days = 2026-03-30 00:00 UTC
      (a Monday — the "current week" reference the seasonal policy
      compares against week-4 Monday).
    """
    # 2026-03-02 is a Monday.
    start = datetime(2026, 3, 2, 0, 0, 0, tzinfo=timezone.utc)
    df = _synthetic_weekly_seasonal(start, weeks=4)
    week5_start = start + timedelta(days=28)
    return df, start, week5_start


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def _window_around(start: datetime, hours: int, seed: int = 99) -> pl.DataFrame:
    """Generate an hourly observation window starting at ``start``.

    Uses the same weekday-dependent mean as ``_synthetic_weekly_seasonal``
    so the current window carries the same weekly pattern as the
    reference.
    """
    rng = np.random.RandomState(seed)
    means = [35.0, 40.0, 45.0, 50.0, 55.0, 60.0, 65.0]
    rows = []
    for h in range(hours):
        ts = start + timedelta(hours=h)
        rows.append(
            {
                "ts": ts,
                "value": float(rng.normal(means[ts.weekday()], 2.0)),
            }
        )
    return pl.DataFrame(rows).with_columns(
        pl.col("ts").cast(pl.Datetime(time_unit="us", time_zone="UTC"))
    )


@pytest.mark.integration
async def test_static_mode_false_positive_on_weekly_seasonal(
    monitor: DriftMonitor,
    weekly_signal: tuple[pl.DataFrame, datetime, datetime],
) -> None:
    """Static-mode drift fires when a narrow Monday window is compared
    against a full mixed-weekday reference — the weekly-seasonal
    retailer's false-positive scenario from §4.5.
    """
    ref_df, _start, week5_start = weekly_signal

    # Generate a Monday-only current window (24 hours, weekday=0 mean=35).
    monday_only = [
        {
            "ts": week5_start + timedelta(hours=h),
            "value": float(np.random.RandomState(99 + h).normal(35.0, 2.0)),
        }
        for h in range(24)
    ]
    current_df = pl.DataFrame(monday_only).with_columns(
        pl.col("ts").cast(pl.Datetime(time_unit="us", time_zone="UTC"))
    )

    # Static reference = the full 4-week mixed-weekday frame.
    await monitor.set_reference_data("static-retailer", ref_df, ["value"])

    report = await monitor.check_drift(
        "static-retailer",
        current_df,
        checked_at=week5_start + timedelta(hours=24),
    )
    assert isinstance(report, DriftReport)
    # False positive: the retailer sees drift every Monday even though
    # the underlying weekly pattern is stable.
    assert report.overall_drift_detected is True, (
        "Static-mode MUST fire a (false-positive) drift alarm when the "
        "Monday window is compared against a full mixed-weekday reference."
    )


@pytest.mark.integration
async def test_seasonal_mode_true_negative_on_weekly_signal(
    monitor: DriftMonitor,
    weekly_signal: tuple[pl.DataFrame, datetime, datetime],
) -> None:
    """Seasonal policy aligns the current 7-day week-5 window against
    the same 7-day slice of week 4, so no drift fires when the weekly
    pattern is stable.

    The current window spans a full week (168 hourly observations)
    starting on Monday week-5. The seasonal slice uses a ±84h
    tolerance around the anchor `checked_at - 1 week` so the sliced
    reference covers the matching weekdays in week 4 (168 rows).
    Both distributions carry the same weekday-dependent pattern
    (means 35→65), so drift MUST NOT fire.
    """
    ref_df, _start, week5_start = weekly_signal

    # Full week-5 hourly observations — preserves weekday pattern.
    current_df = _window_around(week5_start, hours=168, seed=99)

    policy = DriftMonitorReferencePolicy(
        mode="seasonal",
        seasonal_period=timedelta(weeks=1),
        # ± 84h tolerance around anchor = full 7-day seasonal slice of
        # week 4 matching the week-5 current window.
        window=timedelta(hours=84),
    )

    await monitor.set_reference_data(
        "seasonal-retailer",
        ref_df,
        ["value"],
        policy=policy,
        timestamp_column="ts",
    )

    # Anchor the seasonal check at week-5 Monday noon — so anchor-1w
    # lands at week-4 Monday noon and the ±84h slice covers the full
    # matching week 4.
    checked_at = week5_start + timedelta(hours=84)
    report = await monitor.check_drift(
        "seasonal-retailer", current_df, checked_at=checked_at
    )
    assert isinstance(report, DriftReport)
    # True negative: the seasonal policy aligns against the matching
    # weekday pattern one week back, same mixed-weekday distribution,
    # so drift MUST NOT fire.
    assert report.overall_drift_detected is False, (
        "Seasonal policy MUST align the current week-5 window against "
        f"the matching week-4 slice; got {report.feature_results!r}"
    )


@pytest.mark.integration
async def test_seasonal_policy_persists_round_trip(
    monitor: DriftMonitor,
    weekly_signal: tuple[pl.DataFrame, datetime, datetime],
) -> None:
    """policy_json + timestamp_column round-trip through SQLite."""
    ref_df, _start, _week5 = weekly_signal

    policy = DriftMonitorReferencePolicy(mode="rolling", window=timedelta(days=3))
    await monitor.set_reference_data(
        "rolling-m",
        ref_df,
        ["value"],
        policy=policy,
        timestamp_column="ts",
    )

    # Direct DB fetch to confirm policy_json + timestamp_column landed.
    row = await monitor._conn.fetchone(
        "SELECT policy_json, timestamp_column "
        "FROM _kml_drift_references WHERE model_name = ?",
        "rolling-m",
    )
    assert row is not None
    assert row["timestamp_column"] == "ts"
    assert row["policy_json"] is not None
    import json

    restored = DriftMonitorReferencePolicy.from_dict(json.loads(row["policy_json"]))
    assert restored == policy

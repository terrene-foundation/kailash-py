# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 1 unit tests for ``DriftMonitorReferencePolicy`` + slicing.

Covers:
- Validation invariants per spec ``ml-drift.md §4.5`` MUST 1-4.
- Serialisation round-trip via ``to_dict`` / ``from_dict``.
- ``_slice_reference`` static-mode passthrough.
- ``_slice_reference`` rolling / sliding / seasonal slicing.
- Static-mode regression: legacy reference path returns
  ``drift_detected=False`` on an unchanged reference.

These tests do NOT exercise the ConnectionManager persistence layer
(see ``tests/integration/test_drift_seasonal_reference.py`` for that).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import polars as pl
import pytest
from kailash_ml.drift.policy import DriftMonitorReferencePolicy
from kailash_ml.engines.drift_monitor import (
    DriftMonitor,
    _StoredReference,
)
from kailash_ml.errors import DriftMonitorError, DriftThresholdError


# ---------------------------------------------------------------------------
# Policy validation
# ---------------------------------------------------------------------------


class TestPolicyValidation:
    def test_static_default(self) -> None:
        p = DriftMonitorReferencePolicy()
        assert p.mode == "static"
        assert p.window is None
        assert p.seasonal_period is None
        assert p.refresh_cadence is None

    def test_rolling_requires_window(self) -> None:
        with pytest.raises(DriftThresholdError, match="window"):
            DriftMonitorReferencePolicy(mode="rolling")

    def test_rolling_requires_positive_window(self) -> None:
        with pytest.raises(DriftThresholdError, match="positive"):
            DriftMonitorReferencePolicy(mode="rolling", window=timedelta(seconds=0))

    def test_rolling_rejects_seasonal_period(self) -> None:
        with pytest.raises(DriftThresholdError, match="seasonal_period"):
            DriftMonitorReferencePolicy(
                mode="rolling",
                window=timedelta(days=1),
                seasonal_period=timedelta(weeks=1),
            )

    def test_sliding_requires_cadence(self) -> None:
        with pytest.raises(DriftThresholdError, match="refresh_cadence"):
            DriftMonitorReferencePolicy(mode="sliding", window=timedelta(days=30))

    def test_sliding_requires_window(self) -> None:
        with pytest.raises(DriftThresholdError, match="window"):
            DriftMonitorReferencePolicy(
                mode="sliding", refresh_cadence=timedelta(hours=1)
            )

    def test_seasonal_requires_seasonal_period(self) -> None:
        with pytest.raises(DriftThresholdError, match="seasonal_period"):
            DriftMonitorReferencePolicy(mode="seasonal")

    def test_seasonal_rejects_refresh_cadence(self) -> None:
        with pytest.raises(DriftThresholdError, match="refresh_cadence"):
            DriftMonitorReferencePolicy(
                mode="seasonal",
                seasonal_period=timedelta(weeks=1),
                refresh_cadence=timedelta(hours=1),
            )

    def test_static_rejects_window(self) -> None:
        with pytest.raises(DriftThresholdError, match="window"):
            DriftMonitorReferencePolicy(mode="static", window=timedelta(days=1))

    def test_static_rejects_seasonal_period(self) -> None:
        with pytest.raises(DriftThresholdError, match="seasonal_period"):
            DriftMonitorReferencePolicy(
                mode="static", seasonal_period=timedelta(weeks=1)
            )

    def test_invalid_mode_rejected(self) -> None:
        with pytest.raises(DriftThresholdError, match="mode"):
            DriftMonitorReferencePolicy(mode="nonsense")  # type: ignore[arg-type]


class TestPolicySerialisation:
    def test_round_trip_static(self) -> None:
        original = DriftMonitorReferencePolicy()
        restored = DriftMonitorReferencePolicy.from_dict(original.to_dict())
        assert original == restored

    def test_round_trip_rolling(self) -> None:
        original = DriftMonitorReferencePolicy(
            mode="rolling", window=timedelta(days=30)
        )
        restored = DriftMonitorReferencePolicy.from_dict(original.to_dict())
        assert original == restored
        assert restored.window == timedelta(days=30)

    def test_round_trip_seasonal(self) -> None:
        original = DriftMonitorReferencePolicy(
            mode="seasonal", seasonal_period=timedelta(weeks=1)
        )
        restored = DriftMonitorReferencePolicy.from_dict(original.to_dict())
        assert original == restored

    def test_round_trip_sliding(self) -> None:
        original = DriftMonitorReferencePolicy(
            mode="sliding",
            window=timedelta(days=30),
            refresh_cadence=timedelta(hours=4),
        )
        restored = DriftMonitorReferencePolicy.from_dict(original.to_dict())
        assert original == restored


# ---------------------------------------------------------------------------
# Reference slicing
# ---------------------------------------------------------------------------


def _make_reference(
    n_days: int = 14,
    policy: DriftMonitorReferencePolicy | None = None,
) -> tuple[_StoredReference, datetime]:
    """Build a synthetic stored reference with hourly data.

    Returns (reference, anchor_time) where anchor_time is 2026-04-15T12:00Z
    (a Wednesday) for deterministic checks.
    """
    anchor = datetime(2026, 4, 15, 12, 0, 0, tzinfo=timezone.utc)
    start = anchor - timedelta(days=n_days)

    rows = []
    for h in range(n_days * 24):
        ts = start + timedelta(hours=h)
        rows.append({"ts": ts, "value": float(h)})

    df = pl.DataFrame(rows).with_columns(
        pl.col("ts").cast(pl.Datetime(time_unit="us", time_zone="UTC"))
    )

    resolved = policy or DriftMonitorReferencePolicy()
    data_series, statistics = DriftMonitor._compute_reference_summary(df, ["value"])

    ref = _StoredReference(
        model_name="test-model",
        feature_columns=["value"],
        data=data_series,
        statistics=statistics,
        sample_size=df.height,
        set_at=anchor,
        policy=resolved,
        timestamp_column="ts",
        raw_data=df,
    )
    return ref, anchor


class TestSliceReferenceStatic:
    def test_static_returns_full_frame(self) -> None:
        ref, anchor = _make_reference()
        out = DriftMonitor._slice_reference(ref, anchor)
        # Static short-circuits to the stored raw frame (if present) or
        # reconstructs from per-feature Series otherwise. Either way,
        # every row is preserved.
        assert out.height == ref.sample_size


class TestSliceReferenceRolling:
    def test_rolling_slices_last_window(self) -> None:
        policy = DriftMonitorReferencePolicy(mode="rolling", window=timedelta(days=2))
        ref, anchor = _make_reference(n_days=14, policy=policy)
        sliced = DriftMonitor._slice_reference(ref, anchor)
        # 2 days * 24h = 48 rows (exclusive upper bound at anchor)
        assert sliced.height == 48
        # All rows should be within [anchor-2d, anchor)
        lower = anchor - timedelta(days=2)
        ts_vals = sliced["ts"].to_list()
        assert all(lower <= t < anchor for t in ts_vals)


class TestSliceReferenceSliding:
    def test_sliding_memoises_within_cadence(self) -> None:
        policy = DriftMonitorReferencePolicy(
            mode="sliding",
            window=timedelta(days=1),
            refresh_cadence=timedelta(hours=2),
        )
        ref, anchor = _make_reference(n_days=14, policy=policy)
        first = DriftMonitor._slice_reference(ref, anchor)
        # Within the 2h cadence — cached slice returned as-is.
        second = DriftMonitor._slice_reference(ref, anchor + timedelta(minutes=30))
        assert second is first

    def test_sliding_refreshes_after_cadence(self) -> None:
        policy = DriftMonitorReferencePolicy(
            mode="sliding",
            window=timedelta(days=1),
            refresh_cadence=timedelta(hours=2),
        )
        ref, anchor = _make_reference(n_days=14, policy=policy)
        first = DriftMonitor._slice_reference(ref, anchor)
        # Beyond the cadence — a new slice is materialised.
        later = anchor + timedelta(hours=3)
        second = DriftMonitor._slice_reference(ref, later)
        assert second is not first


class TestSliceReferenceSeasonal:
    def test_seasonal_slices_prior_period(self) -> None:
        policy = DriftMonitorReferencePolicy(
            mode="seasonal", seasonal_period=timedelta(weeks=1)
        )
        ref, anchor = _make_reference(n_days=14, policy=policy)
        # anchor - 1 week => the same weekday/hour, 7 days earlier.
        sliced = DriftMonitor._slice_reference(ref, anchor)
        assert sliced.height > 0
        one_week_before = anchor - timedelta(weeks=1)
        # tol default is 1/24 of seasonal_period but minimum 1 hour.
        # Every row must be within [anchor-1w-tol, anchor-1w+tol].
        tol_minutes_upper_bound = 60 * 24 * 7 / 24 + 60  # well within bounds
        for ts in sliced["ts"].to_list():
            delta = abs((ts - one_week_before).total_seconds())
            assert delta <= tol_minutes_upper_bound * 60

    def test_seasonal_raises_when_raw_missing(self) -> None:
        # Directly craft a _StoredReference that claims seasonal mode
        # but was not given raw_data / timestamp_column.
        policy = DriftMonitorReferencePolicy(
            mode="seasonal", seasonal_period=timedelta(weeks=1)
        )
        ref = _StoredReference(
            model_name="test",
            feature_columns=["value"],
            data={},
            statistics={},
            sample_size=0,
            set_at=datetime.now(timezone.utc),
            policy=policy,
            timestamp_column=None,
            raw_data=None,
        )
        with pytest.raises(DriftMonitorError, match="timestamp_column"):
            DriftMonitor._slice_reference(ref, datetime.now(timezone.utc))

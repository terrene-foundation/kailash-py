# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 2 wiring tests for W26.a DriftMonitor extensions.

Covers the wiring contract introduced by W26.a:

  - ``DriftMonitor`` accepts ``thresholds: DriftThresholds`` and
    ``tracker: Any`` at construction time and routes through both
    during ``check_drift``.
  - Categorical columns get chi² + JSD + new-category fraction; the
    continuous PSI+KS path is unchanged.
  - ``FeatureDriftResult`` carries the extended fields
    (``chi2_statistic``, ``chi2_pvalue``, ``jsd``,
    ``new_category_fraction``, ``statistics_used``, ``stability_note``)
    AND round-trips through ``to_dict`` / ``from_dict``.
  - The tracker receives ``log_metric("drift/{feature}/{statistic}",
    value)`` per spec §6.4 + todo invariant 4, plus a
    ``drift/{feature}/alert`` sentinel for filter dashboards.
  - A zero-variance reference column surfaces as a per-feature
    ``stability_note`` rather than aborting the whole check.
"""
from __future__ import annotations

import numpy as np
import polars as pl
import pytest
from kailash_ml.drift import DriftThresholds
from kailash_ml.engines.drift_monitor import DriftMonitor, FeatureDriftResult

from kailash.db.connection import ConnectionManager


class _RecordingTracker:
    """Duck-typed tracker — same ``log_metric(key, value, *, step=None)``
    contract RLDiagnostics / DLDiagnostics consume.  Real implementation
    (not a mock) per ``rules/testing.md`` § Tier 2 "Protocol-Satisfying
    Deterministic Adapters Are Not Mocks"."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, float]] = []

    def log_metric(self, key: str, value: float, *, step=None) -> None:  # noqa: ANN001
        self.calls.append((key, float(value)))


@pytest.fixture
async def conn():
    cm = ConnectionManager("sqlite://:memory:")
    await cm.initialize()
    yield cm
    await cm.close()


# ---------------------------------------------------------------------------
# DriftMonitor wiring — thresholds + tracker
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_drift_monitor_categorical_uses_chi2_and_jsd(conn) -> None:
    """A string feature with drift MUST populate chi2 + jsd + new_category."""
    tracker = _RecordingTracker()
    monitor = DriftMonitor(conn, tracker=tracker)

    ref = pl.DataFrame({"country": ["US"] * 200 + ["UK"] * 200})
    cur = pl.DataFrame({"country": ["FR"] * 400})
    await monitor.set_reference_data("m1", ref, ["country"])
    report = await monitor.check_drift("m1", cur)

    assert len(report.feature_results) == 1
    result = report.feature_results[0]
    assert result.feature_name == "country"
    assert result.statistics_used == sorted({"chi2", "jsd", "new_category"})
    assert result.chi2_statistic is not None and result.chi2_statistic > 0
    assert result.chi2_pvalue is not None and result.chi2_pvalue < 0.05
    assert result.jsd is not None and result.jsd > 0.5
    assert result.new_category_fraction == 1.0
    assert result.drift_detected


@pytest.mark.integration
async def test_drift_monitor_continuous_uses_ks_psi_jsd(conn) -> None:
    """A float feature gets KS + PSI + JSD; chi² is not computed."""
    monitor = DriftMonitor(conn)
    rng = np.random.default_rng(0)

    ref = pl.DataFrame({"age": rng.normal(35, 5, 500).tolist()})
    cur = pl.DataFrame({"age": rng.normal(50, 5, 500).tolist()})
    await monitor.set_reference_data("m1", ref, ["age"])
    report = await monitor.check_drift("m1", cur)

    result = report.feature_results[0]
    assert result.statistics_used == sorted({"ks", "psi", "jsd"})
    assert result.chi2_statistic is None
    assert result.chi2_pvalue is None
    assert result.jsd is not None and result.jsd > 0.3
    assert result.drift_detected


@pytest.mark.integration
async def test_drift_monitor_emits_tracker_metrics(conn) -> None:
    """Spec §6.4 + W26 invariant 4 — every computed statistic lands
    under ``drift/{feature}/{statistic}``, plus a ``.../alert`` sentinel."""
    tracker = _RecordingTracker()
    monitor = DriftMonitor(conn, tracker=tracker)
    rng = np.random.default_rng(0)

    ref = pl.DataFrame({"x": rng.normal(0, 1, 500).tolist()})
    cur = pl.DataFrame({"x": rng.normal(4, 1, 500).tolist()})
    await monitor.set_reference_data("m1", ref, ["x"])
    await monitor.check_drift("m1", cur)

    keys = {call[0] for call in tracker.calls}
    assert "drift/x/psi" in keys
    assert "drift/x/ks_pvalue" in keys
    assert "drift/x/jsd" in keys
    assert "drift/x/alert" in keys
    # Alert is the sentinel — 1.0 for detected, 0.0 otherwise.
    alert_value = [v for (k, v) in tracker.calls if k == "drift/x/alert"][0]
    assert alert_value == 1.0


@pytest.mark.integration
async def test_drift_monitor_per_column_threshold_override(conn) -> None:
    """Per-column overrides in ``DriftThresholds`` steer the drift verdict."""
    # Default ks_pvalue threshold 0.05 would detect drift on this borderline
    # distribution; override to 1e-6 to make the same shift not fire.
    thresholds = DriftThresholds(
        column_overrides={"x": {"psi": 100.0, "ks_pvalue": 1e-12, "jsd": 100.0}},
    )
    monitor = DriftMonitor(conn, thresholds=thresholds)
    rng = np.random.default_rng(0)

    ref = pl.DataFrame({"x": rng.normal(0, 1, 500).tolist()})
    cur = pl.DataFrame({"x": rng.normal(0.5, 1, 500).tolist()})  # small shift
    await monitor.set_reference_data("m1", ref, ["x"])
    report = await monitor.check_drift("m1", cur)

    # All thresholds blown out → no drift detected despite the shift.
    assert not report.feature_results[0].drift_detected


@pytest.mark.integration
async def test_drift_monitor_zero_variance_reference_emits_stability_note(
    conn,
) -> None:
    """Zero-variance reference → per-feature ``stability_note``; the rest
    of the features still report normally."""
    monitor = DriftMonitor(conn)
    rng = np.random.default_rng(0)

    ref = pl.DataFrame(
        {
            "constant": [7.0] * 500,  # zero variance
            "age": rng.normal(30, 5, 500).tolist(),
        }
    )
    cur = pl.DataFrame(
        {
            "constant": [7.0, 8.0] * 250,
            "age": rng.normal(30, 5, 500).tolist(),
        }
    )
    await monitor.set_reference_data("m1", ref, ["constant", "age"])
    report = await monitor.check_drift("m1", cur)

    by_name = {f.feature_name: f for f in report.feature_results}
    assert by_name["constant"].stability_note is not None
    assert "zero_variance_reference" in by_name["constant"].stability_note
    # JSD is None on the degenerate column but PSI / KS still populate.
    assert by_name["constant"].jsd is None
    # The other feature reports normally.
    assert by_name["age"].stability_note is None


# ---------------------------------------------------------------------------
# Regression — extended FeatureDriftResult round-trip
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_feature_drift_result_round_trips_extended_fields() -> None:
    """W26.a added 6 optional fields — ``to_dict`` / ``from_dict`` MUST
    round-trip every one of them without loss."""
    original = FeatureDriftResult(
        feature_name="age",
        psi=0.15,
        ks_statistic=0.1,
        ks_pvalue=0.03,
        drift_detected=True,
        drift_type="moderate",
        chi2_statistic=5.2,
        chi2_pvalue=0.02,
        jsd=0.12,
        new_category_fraction=0.0,
        statistics_used=["jsd", "ks", "psi"],
        stability_note=None,
    )
    restored = FeatureDriftResult.from_dict(original.to_dict())
    assert restored == original

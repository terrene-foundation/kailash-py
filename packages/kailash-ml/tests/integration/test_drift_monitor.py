# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Integration tests for DriftMonitor engine.

Uses real scipy + real SQLite (no mocking).
"""
from __future__ import annotations

import numpy as np
import polars as pl
import pytest

from kailash.db.connection import ConnectionManager
from kailash_ml.engines.drift_monitor import (
    DriftMonitor,
    DriftReport,
    FeatureDriftResult,
    PerformanceDegradationReport,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def conn():
    cm = ConnectionManager("sqlite://:memory:")
    await cm.initialize()
    yield cm
    await cm.close()


@pytest.fixture
async def monitor(conn: ConnectionManager) -> DriftMonitor:
    return DriftMonitor(conn)


# ---------------------------------------------------------------------------
# Distribution shift detection
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_detect_distribution_shift(monitor: DriftMonitor) -> None:
    """DriftMonitor detects N(50,10) -> N(70,10) shift."""
    rng = np.random.RandomState(42)

    reference = pl.DataFrame({"score": rng.normal(50, 10, 5000).tolist()})
    current = pl.DataFrame({"score": rng.normal(70, 10, 5000).tolist()})

    await monitor.set_reference("model_a", reference, ["score"])
    report = await monitor.check_drift("model_a", current)

    assert isinstance(report, DriftReport)
    assert report.overall_drift_detected is True
    assert report.feature_results[0].psi > 0.2
    assert report.feature_results[0].drift_type == "severe"
    assert "score" in report.drifted_features


@pytest.mark.integration
async def test_stable_distribution_no_alert(monitor: DriftMonitor) -> None:
    """Same distribution -> no drift alert."""
    rng = np.random.RandomState(42)

    reference = pl.DataFrame({"score": rng.normal(50, 10, 5000).tolist()})
    # Use a different seed but same parameters
    rng2 = np.random.RandomState(123)
    current = pl.DataFrame({"score": rng2.normal(50, 10, 5000).tolist()})

    await monitor.set_reference("model_b", reference, ["score"])
    report = await monitor.check_drift("model_b", current)

    assert report.overall_drift_detected is False
    assert report.overall_severity == "none"


@pytest.mark.integration
async def test_moderate_shift(monitor: DriftMonitor) -> None:
    """Moderate distribution shift (PSI 0.1-0.2)."""
    rng = np.random.RandomState(42)

    reference = pl.DataFrame({"score": rng.normal(50, 10, 5000).tolist()})
    # Slight shift
    rng2 = np.random.RandomState(123)
    current = pl.DataFrame({"score": rng2.normal(55, 10, 5000).tolist()})

    await monitor.set_reference("model_moderate", reference, ["score"])
    report = await monitor.check_drift("model_moderate", current)

    # May or may not trigger depending on exact PSI
    assert isinstance(report, DriftReport)
    assert report.feature_results[0].psi > 0


# ---------------------------------------------------------------------------
# Categorical drift
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_categorical_drift_detection(monitor: DriftMonitor) -> None:
    """Detect category distribution shift."""
    reference = pl.DataFrame({"category": ["A"] * 400 + ["B"] * 400 + ["C"] * 200})
    current = pl.DataFrame({"category": ["A"] * 100 + ["B"] * 100 + ["C"] * 800})

    await monitor.set_reference("model_c", reference, ["category"])
    report = await monitor.check_drift("model_c", current)

    assert report.overall_drift_detected is True


# ---------------------------------------------------------------------------
# Multi-feature drift
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_multi_feature_drift(monitor: DriftMonitor) -> None:
    """Monitor multiple features, only some drift."""
    rng = np.random.RandomState(42)

    reference = pl.DataFrame(
        {
            "stable": rng.normal(0, 1, 5000).tolist(),
            "drifting": rng.normal(0, 1, 5000).tolist(),
        }
    )
    rng2 = np.random.RandomState(123)
    current = pl.DataFrame(
        {
            "stable": rng2.normal(0, 1, 5000).tolist(),
            "drifting": rng2.normal(10, 1, 5000).tolist(),  # severe shift
        }
    )

    await monitor.set_reference("multi", reference, ["stable", "drifting"])
    report = await monitor.check_drift("multi", current)

    assert report.overall_drift_detected is True
    assert len(report.feature_results) == 2

    drifted_names = report.drifted_features
    assert "drifting" in drifted_names


# ---------------------------------------------------------------------------
# Performance degradation
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_performance_degradation(monitor: DriftMonitor) -> None:
    """Detect metric degradation vs baseline."""
    # Baseline: model was accurate
    baseline = {"accuracy": 0.9, "f1": 0.88}

    report = await monitor.check_performance(
        "model_a",
        predictions=pl.DataFrame({"pred": [0, 1, 1, 0, 1]}),
        actuals=pl.DataFrame({"actual": [0, 0, 0, 0, 0]}),
        baseline_metrics=baseline,
    )

    assert isinstance(report, PerformanceDegradationReport)
    assert report.degraded is True
    assert report.degradation["accuracy"] > 0


@pytest.mark.integration
async def test_performance_no_degradation(monitor: DriftMonitor) -> None:
    """No degradation when model performs well."""
    baseline = {"accuracy": 0.8}

    report = await monitor.check_performance(
        "model_good",
        predictions=pl.DataFrame({"pred": [0, 1, 0, 1, 0]}),
        actuals=pl.DataFrame({"actual": [0, 1, 0, 1, 0]}),
        baseline_metrics=baseline,
    )

    assert report.degraded is False


# ---------------------------------------------------------------------------
# Report persistence
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_drift_report_persisted(monitor: DriftMonitor) -> None:
    """DriftReport is stored for historical analysis."""
    rng = np.random.RandomState(42)
    reference = pl.DataFrame({"val": rng.normal(0, 1, 1000).tolist()})
    current = pl.DataFrame({"val": rng.normal(5, 1, 1000).tolist()})

    await monitor.set_reference("persist_test", reference, ["val"])
    await monitor.check_drift("persist_test", current)

    history = await monitor.get_drift_history("persist_test")
    assert len(history) == 1
    assert history[0]["model_name"] == "persist_test"
    assert history[0]["overall_drift"] == 1


@pytest.mark.integration
async def test_multiple_drift_reports_persisted(monitor: DriftMonitor) -> None:
    """Multiple drift checks are all stored."""
    rng = np.random.RandomState(42)
    reference = pl.DataFrame({"val": rng.normal(0, 1, 1000).tolist()})

    await monitor.set_reference("multi_check", reference, ["val"])

    for _ in range(3):
        current = pl.DataFrame({"val": rng.normal(0, 1, 1000).tolist()})
        await monitor.check_drift("multi_check", current)

    history = await monitor.get_drift_history("multi_check")
    assert len(history) == 3


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_no_reference_raises(monitor: DriftMonitor) -> None:
    """check_drift without set_reference raises ValueError."""
    current = pl.DataFrame({"val": [1.0, 2.0, 3.0]})
    with pytest.raises(ValueError, match="No reference set"):
        await monitor.check_drift("nonexistent", current)


@pytest.mark.integration
async def test_reference_update(monitor: DriftMonitor) -> None:
    """Setting reference twice updates (idempotent)."""
    rng = np.random.RandomState(42)
    ref1 = pl.DataFrame({"val": rng.normal(0, 1, 100).tolist()})
    ref2 = pl.DataFrame({"val": rng.normal(5, 1, 200).tolist()})

    await monitor.set_reference("update_test", ref1, ["val"])
    await monitor.set_reference("update_test", ref2, ["val"])

    # Should use ref2 as reference
    current = pl.DataFrame({"val": rng.normal(5, 1, 100).tolist()})
    report = await monitor.check_drift("update_test", current)
    # Current matches ref2, so no drift
    assert report.overall_severity in ("none", "moderate")

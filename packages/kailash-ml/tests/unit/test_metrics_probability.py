# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tests for probability metrics (TASK-ML-02).

Validates that:
- log_loss, brier_score_loss, average_precision work as standalone functions
- They accept polars Series and numpy arrays
- Missing y_prob raises ValueError
- compute_metrics_by_name accepts y_prob parameter
- 2D probability arrays are handled (positive class extraction)
"""
from __future__ import annotations

import numpy as np
import polars as pl
import pytest
from kailash_ml.metrics import (
    METRIC_REGISTRY,
    average_precision,
    brier_score_loss,
    compute_metric,
    compute_metrics,
    log_loss,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def binary_prob_data():
    """Binary classification data with probabilities."""
    y_true = np.array([0, 0, 1, 1])
    y_prob = np.array([0.1, 0.4, 0.6, 0.9])
    return y_true, y_prob


@pytest.fixture
def binary_prob_2d():
    """Binary classification data with 2D probability array."""
    y_true = np.array([0, 0, 1, 1])
    y_prob = np.array([[0.9, 0.1], [0.6, 0.4], [0.4, 0.6], [0.1, 0.9]])
    return y_true, y_prob


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


class TestProbabilityMetricsRegistered:
    """All 3 probability metrics are in the registry."""

    def test_log_loss_registered(self):
        assert "log_loss" in METRIC_REGISTRY
        assert METRIC_REGISTRY["log_loss"]["requires_prob"] is True

    def test_brier_score_loss_registered(self):
        assert "brier_score_loss" in METRIC_REGISTRY
        assert METRIC_REGISTRY["brier_score_loss"]["requires_prob"] is True

    def test_average_precision_registered(self):
        assert "average_precision" in METRIC_REGISTRY
        assert METRIC_REGISTRY["average_precision"]["requires_prob"] is True


# ---------------------------------------------------------------------------
# Standalone functions -- numpy
# ---------------------------------------------------------------------------


class TestProbabilityStandaloneNumpy:
    """Probability metrics with numpy input."""

    def test_log_loss(self, binary_prob_data):
        y_true, y_prob = binary_prob_data
        result = log_loss(y_true, y_prob)
        assert isinstance(result, float)
        assert result > 0.0

    def test_brier_score_loss(self, binary_prob_data):
        y_true, y_prob = binary_prob_data
        result = brier_score_loss(y_true, y_prob)
        assert isinstance(result, float)
        assert 0.0 <= result <= 1.0

    def test_average_precision(self, binary_prob_data):
        y_true, y_prob = binary_prob_data
        result = average_precision(y_true, y_prob)
        assert isinstance(result, float)
        assert 0.0 <= result <= 1.0

    def test_brier_score_loss_2d(self, binary_prob_2d):
        """2D probability array -- should auto-extract positive class."""
        y_true, y_prob = binary_prob_2d
        result = brier_score_loss(y_true, y_prob)
        assert isinstance(result, float)
        assert 0.0 <= result <= 1.0

    def test_average_precision_2d(self, binary_prob_2d):
        """2D probability array -- should auto-extract positive class."""
        y_true, y_prob = binary_prob_2d
        result = average_precision(y_true, y_prob)
        assert isinstance(result, float)
        assert 0.0 <= result <= 1.0

    def test_perfect_predictions(self):
        """Perfect probability predictions should yield optimal scores."""
        y_true = np.array([0, 0, 1, 1])
        y_prob = np.array([0.0, 0.0, 1.0, 1.0])
        brier = brier_score_loss(y_true, y_prob)
        assert brier == pytest.approx(0.0)

        ap = average_precision(y_true, y_prob)
        assert ap == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Standalone functions -- polars
# ---------------------------------------------------------------------------


class TestProbabilityStandalonePolars:
    """Probability metrics with polars Series input."""

    def test_log_loss_polars(self):
        y_true = pl.Series([0, 0, 1, 1])
        y_prob = pl.Series([0.1, 0.4, 0.6, 0.9])
        result = log_loss(y_true, y_prob)
        assert isinstance(result, float)
        assert result > 0.0

    def test_brier_score_loss_polars(self):
        y_true = pl.Series([0, 0, 1, 1])
        y_prob = pl.Series([0.1, 0.4, 0.6, 0.9])
        result = brier_score_loss(y_true, y_prob)
        assert isinstance(result, float)
        assert 0.0 <= result <= 1.0

    def test_average_precision_polars(self):
        y_true = pl.Series([0, 0, 1, 1])
        y_prob = pl.Series([0.1, 0.4, 0.6, 0.9])
        result = average_precision(y_true, y_prob)
        assert isinstance(result, float)
        assert 0.0 <= result <= 1.0


# ---------------------------------------------------------------------------
# Missing y_prob raises ValueError
# ---------------------------------------------------------------------------


class TestMissingYProbRaises:
    """Probability metrics raise when y_prob is missing."""

    def test_compute_metric_log_loss_no_prob(self):
        y_true = np.array([0, 1, 0, 1])
        y_pred = np.array([0, 1, 0, 1])
        with pytest.raises(ValueError, match="requires probability predictions"):
            compute_metric("log_loss", y_true, y_pred)

    def test_compute_metric_brier_no_prob(self):
        y_true = np.array([0, 1, 0, 1])
        y_pred = np.array([0, 1, 0, 1])
        with pytest.raises(ValueError, match="requires probability predictions"):
            compute_metric("brier_score_loss", y_true, y_pred)

    def test_compute_metric_average_precision_no_prob(self):
        y_true = np.array([0, 1, 0, 1])
        y_pred = np.array([0, 1, 0, 1])
        with pytest.raises(ValueError, match="requires probability predictions"):
            compute_metric("average_precision", y_true, y_pred)

    def test_compute_metrics_prob_skipped_without_y_prob(self):
        """compute_metrics (batch) should skip prob metrics without y_prob."""
        y_true = np.array([0, 1, 0, 1])
        y_pred = np.array([0, 1, 0, 1])
        results = compute_metrics(y_true, y_pred, ["accuracy", "log_loss"])
        assert "accuracy" in results
        assert "log_loss" not in results


# ---------------------------------------------------------------------------
# compute_metrics_by_name with y_prob (delegation from _shared)
# ---------------------------------------------------------------------------


class TestSharedWithYProb:
    """_shared.compute_metrics_by_name passes y_prob to registry."""

    def test_shared_log_loss_with_y_prob(self, binary_prob_data):
        from kailash_ml.engines._shared import compute_metrics_by_name

        y_true, y_prob = binary_prob_data
        y_pred = (y_prob > 0.5).astype(int)
        result = compute_metrics_by_name(y_true, y_pred, ["log_loss"], y_prob=y_prob)
        assert "log_loss" in result
        assert isinstance(result["log_loss"], float)
        assert result["log_loss"] > 0.0

    def test_shared_all_prob_metrics(self, binary_prob_data):
        from kailash_ml.engines._shared import compute_metrics_by_name

        y_true, y_prob = binary_prob_data
        y_pred = (y_prob > 0.5).astype(int)
        result = compute_metrics_by_name(
            y_true,
            y_pred,
            ["accuracy", "log_loss", "brier_score_loss", "average_precision"],
            y_prob=y_prob,
        )
        assert len(result) == 4
        assert "accuracy" in result
        assert "log_loss" in result
        assert "brier_score_loss" in result
        assert "average_precision" in result

    def test_shared_prob_metrics_without_y_prob_skipped(self):
        """Without y_prob, probability metrics should be skipped."""
        from kailash_ml.engines._shared import compute_metrics_by_name

        y_true = np.array([0, 1, 0, 1])
        y_pred = np.array([0, 1, 0, 1])
        result = compute_metrics_by_name(y_true, y_pred, ["accuracy", "log_loss"])
        assert "accuracy" in result
        assert "log_loss" not in result

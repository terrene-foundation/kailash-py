# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tests for the public metrics module (TASK-ML-01).

Validates that:
- All 9 original metrics are callable as standalone functions
- Metrics accept both polars Series and numpy arrays
- Registry-based compute_metrics works
- compute_metrics_by_name in _shared delegates to the registry
- Unknown metrics raise or warn appropriately
"""
from __future__ import annotations

import numpy as np
import polars as pl
import pytest
from kailash_ml.metrics import (
    METRIC_REGISTRY,
    accuracy,
    auc,
    compute_metric,
    compute_metrics,
    f1,
    list_metrics,
    mae,
    mse,
    precision,
    r2,
    recall,
    rmse,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def binary_classification_data():
    """Binary classification ground truth and predictions."""
    y_true = np.array([1, 0, 1, 1, 0, 1, 0, 0])
    y_pred = np.array([1, 0, 0, 1, 0, 1, 1, 0])
    return y_true, y_pred


@pytest.fixture
def regression_data():
    """Regression ground truth and predictions."""
    y_true = np.array([3.0, -0.5, 2.0, 7.0])
    y_pred = np.array([2.5, 0.0, 2.0, 8.0])
    return y_true, y_pred


# ---------------------------------------------------------------------------
# Standalone function tests -- numpy input
# ---------------------------------------------------------------------------


class TestStandaloneFunctionsNumpy:
    """Each of the 9 original metrics as a standalone function with numpy."""

    def test_accuracy(self, binary_classification_data):
        y_true, y_pred = binary_classification_data
        result = accuracy(y_true, y_pred)
        assert isinstance(result, float)
        assert 0.0 <= result <= 1.0
        # 6 correct out of 8
        assert result == pytest.approx(6 / 8)

    def test_f1(self, binary_classification_data):
        y_true, y_pred = binary_classification_data
        result = f1(y_true, y_pred)
        assert isinstance(result, float)
        assert 0.0 <= result <= 1.0

    def test_precision(self, binary_classification_data):
        y_true, y_pred = binary_classification_data
        result = precision(y_true, y_pred)
        assert isinstance(result, float)
        assert 0.0 <= result <= 1.0

    def test_recall(self, binary_classification_data):
        y_true, y_pred = binary_classification_data
        result = recall(y_true, y_pred)
        assert isinstance(result, float)
        assert 0.0 <= result <= 1.0

    def test_mse(self, regression_data):
        y_true, y_pred = regression_data
        result = mse(y_true, y_pred)
        assert isinstance(result, float)
        assert result >= 0.0
        # (0.5^2 + 0.5^2 + 0^2 + 1^2) / 4 = 0.375
        assert result == pytest.approx(0.375)

    def test_rmse(self, regression_data):
        y_true, y_pred = regression_data
        result = rmse(y_true, y_pred)
        assert isinstance(result, float)
        assert result >= 0.0
        assert result == pytest.approx(np.sqrt(0.375))

    def test_mae(self, regression_data):
        y_true, y_pred = regression_data
        result = mae(y_true, y_pred)
        assert isinstance(result, float)
        assert result >= 0.0
        # (0.5 + 0.5 + 0 + 1) / 4 = 0.5
        assert result == pytest.approx(0.5)

    def test_r2(self, regression_data):
        y_true, y_pred = regression_data
        result = r2(y_true, y_pred)
        assert isinstance(result, float)

    def test_auc_with_proba(self):
        y_true = np.array([0, 0, 1, 1])
        y_prob = np.array([[0.9, 0.1], [0.8, 0.2], [0.3, 0.7], [0.1, 0.9]])
        result = auc(y_true, y_prob)
        assert isinstance(result, float)
        assert 0.0 <= result <= 1.0
        assert result == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Standalone function tests -- polars input
# ---------------------------------------------------------------------------


class TestStandaloneFunctionsPolars:
    """Each metric with polars Series input."""

    def test_accuracy_polars(self):
        y_true = pl.Series([1, 0, 1, 1, 0])
        y_pred = pl.Series([1, 0, 0, 1, 0])
        result = accuracy(y_true, y_pred)
        assert isinstance(result, float)
        assert result == pytest.approx(4 / 5)

    def test_f1_polars(self):
        y_true = pl.Series([1, 0, 1, 1, 0])
        y_pred = pl.Series([1, 0, 0, 1, 0])
        result = f1(y_true, y_pred)
        assert isinstance(result, float)
        assert 0.0 <= result <= 1.0

    def test_precision_polars(self):
        y_true = pl.Series([1, 0, 1, 1, 0])
        y_pred = pl.Series([1, 0, 0, 1, 0])
        result = precision(y_true, y_pred)
        assert isinstance(result, float)

    def test_recall_polars(self):
        y_true = pl.Series([1, 0, 1, 1, 0])
        y_pred = pl.Series([1, 0, 0, 1, 0])
        result = recall(y_true, y_pred)
        assert isinstance(result, float)

    def test_mse_polars(self):
        y_true = pl.Series([3.0, -0.5, 2.0, 7.0])
        y_pred = pl.Series([2.5, 0.0, 2.0, 8.0])
        result = mse(y_true, y_pred)
        assert isinstance(result, float)
        assert result == pytest.approx(0.375)

    def test_rmse_polars(self):
        y_true = pl.Series([3.0, -0.5, 2.0, 7.0])
        y_pred = pl.Series([2.5, 0.0, 2.0, 8.0])
        result = rmse(y_true, y_pred)
        assert isinstance(result, float)
        assert result == pytest.approx(np.sqrt(0.375))

    def test_mae_polars(self):
        y_true = pl.Series([3.0, -0.5, 2.0, 7.0])
        y_pred = pl.Series([2.5, 0.0, 2.0, 8.0])
        result = mae(y_true, y_pred)
        assert isinstance(result, float)
        assert result == pytest.approx(0.5)

    def test_r2_polars(self):
        y_true = pl.Series([3.0, -0.5, 2.0, 7.0])
        y_pred = pl.Series([2.5, 0.0, 2.0, 8.0])
        result = r2(y_true, y_pred)
        assert isinstance(result, float)


# ---------------------------------------------------------------------------
# Registry tests
# ---------------------------------------------------------------------------


class TestRegistry:
    """Test registry-based metric computation."""

    def test_all_9_metrics_registered(self):
        expected = {
            "accuracy",
            "f1",
            "precision",
            "recall",
            "auc",
            "mse",
            "rmse",
            "mae",
            "r2",
        }
        assert expected.issubset(set(METRIC_REGISTRY.keys()))

    def test_list_metrics_returns_sorted(self):
        result = list_metrics()
        assert isinstance(result, list)
        assert result == sorted(result)
        assert "accuracy" in result
        assert "r2" in result

    def test_compute_metric_single(self, binary_classification_data):
        y_true, y_pred = binary_classification_data
        result = compute_metric("accuracy", y_true, y_pred)
        assert isinstance(result, float)
        assert result == pytest.approx(6 / 8)

    def test_compute_metric_unknown_raises(self, binary_classification_data):
        y_true, y_pred = binary_classification_data
        with pytest.raises(ValueError, match="Unknown metric"):
            compute_metric("nonexistent_metric", y_true, y_pred)

    def test_compute_metrics_multiple(self, binary_classification_data):
        y_true, y_pred = binary_classification_data
        results = compute_metrics(y_true, y_pred, ["accuracy", "f1", "precision"])
        assert len(results) == 3
        assert all(isinstance(v, float) for v in results.values())
        assert "accuracy" in results
        assert "f1" in results
        assert "precision" in results

    def test_compute_metrics_unknown_skipped(self, binary_classification_data):
        y_true, y_pred = binary_classification_data
        results = compute_metrics(y_true, y_pred, ["accuracy", "totally_unknown"])
        assert "accuracy" in results
        assert "totally_unknown" not in results

    def test_compute_metrics_polars_input(self):
        y_true = pl.Series([1, 0, 1, 1])
        y_pred = pl.Series([1, 0, 0, 1])
        results = compute_metrics(y_true, y_pred, ["accuracy", "f1"])
        assert len(results) == 2
        assert results["accuracy"] == pytest.approx(3 / 4)


# ---------------------------------------------------------------------------
# Delegation: _shared.compute_metrics_by_name -> registry
# ---------------------------------------------------------------------------


class TestSharedDelegation:
    """Verify _shared.compute_metrics_by_name delegates to the registry."""

    def test_shared_delegates_to_registry(self, binary_classification_data):
        from kailash_ml.engines._shared import compute_metrics_by_name

        y_true, y_pred = binary_classification_data
        shared_result = compute_metrics_by_name(y_true, y_pred, ["accuracy", "f1"])
        registry_result = compute_metrics(y_true, y_pred, ["accuracy", "f1"])
        assert shared_result == registry_result

    def test_shared_regression_metrics(self, regression_data):
        from kailash_ml.engines._shared import compute_metrics_by_name

        y_true, y_pred = regression_data
        result = compute_metrics_by_name(y_true, y_pred, ["mse", "rmse", "mae", "r2"])
        assert len(result) == 4
        assert result["mse"] == pytest.approx(0.375)


# ---------------------------------------------------------------------------
# Lazy loading from kailash_ml
# ---------------------------------------------------------------------------


class TestLazyLoading:
    """Verify metrics module is accessible via kailash_ml.metrics."""

    def test_import_metrics_module(self):
        import kailash_ml

        metrics = kailash_ml.metrics
        assert hasattr(metrics, "accuracy")
        assert hasattr(metrics, "compute_metrics")
        assert hasattr(metrics, "list_metrics")

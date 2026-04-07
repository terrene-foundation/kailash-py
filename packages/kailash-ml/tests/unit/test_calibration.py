# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for TrainingPipeline.calibrate() method."""
from __future__ import annotations

import numpy as np
import polars as pl
import pytest
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import RandomForestClassifier

from kailash_ml.engines.training_pipeline import TrainingPipeline


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_pipeline() -> TrainingPipeline:
    """Construct a TrainingPipeline without registry/feature_store.

    calibrate() is self-contained and does not need a database
    connection or model registry.
    """
    return TrainingPipeline.__new__(TrainingPipeline)


def _fit_rf_and_data(
    n_train: int = 400,
    n_val: int = 200,
    seed: int = 42,
) -> tuple[RandomForestClassifier, pl.DataFrame, pl.Series]:
    """Train a RandomForestClassifier and return (model, X_val, y_val).

    The synthetic dataset has 4 numeric features and a binary target.
    """
    rng = np.random.RandomState(seed)

    # Training data
    X_train = rng.randn(n_train, 4)
    y_train = (X_train[:, 0] + X_train[:, 1] > 0).astype(int)

    rf = RandomForestClassifier(n_estimators=20, random_state=seed)
    rf.fit(X_train, y_train)

    # Validation data (polars-native)
    X_val_np = rng.randn(n_val, 4)
    y_val_np = (X_val_np[:, 0] + X_val_np[:, 1] > 0).astype(int)

    X_val = pl.DataFrame(
        {
            "f0": X_val_np[:, 0].tolist(),
            "f1": X_val_np[:, 1].tolist(),
            "f2": X_val_np[:, 2].tolist(),
            "f3": X_val_np[:, 3].tolist(),
        }
    )
    y_val = pl.Series("target", y_val_np.tolist())

    return rf, X_val, y_val


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestCalibrateSigmoid:
    """Calibrate with method='sigmoid' (Platt scaling)."""

    @pytest.mark.asyncio
    async def test_returns_calibrated_model(self) -> None:
        """calibrate() returns a CalibratedClassifierCV instance."""
        pipe = _make_pipeline()
        model, X_val, y_val = _fit_rf_and_data()

        calibrated = await pipe.calibrate(model, X_val, y_val, method="sigmoid")

        assert isinstance(calibrated, CalibratedClassifierCV)

    @pytest.mark.asyncio
    async def test_has_predict_and_predict_proba(self) -> None:
        """Calibrated model exposes predict() and predict_proba()."""
        pipe = _make_pipeline()
        model, X_val, y_val = _fit_rf_and_data()

        calibrated = await pipe.calibrate(model, X_val, y_val, method="sigmoid")

        assert hasattr(calibrated, "predict")
        assert hasattr(calibrated, "predict_proba")

    @pytest.mark.asyncio
    async def test_predict_proba_valid_probabilities(self) -> None:
        """predict_proba() produces values in [0, 1] that sum to 1."""
        pipe = _make_pipeline()
        model, X_val, y_val = _fit_rf_and_data()

        calibrated = await pipe.calibrate(model, X_val, y_val, method="sigmoid")

        X_np = X_val.to_numpy()
        proba = calibrated.predict_proba(X_np)

        assert proba.shape == (X_val.height, 2)
        assert np.all(proba >= 0.0)
        assert np.all(proba <= 1.0)
        np.testing.assert_allclose(proba.sum(axis=1), 1.0, atol=1e-10)

    @pytest.mark.asyncio
    async def test_predict_returns_correct_shape(self) -> None:
        """predict() returns one label per validation sample."""
        pipe = _make_pipeline()
        model, X_val, y_val = _fit_rf_and_data()

        calibrated = await pipe.calibrate(model, X_val, y_val, method="sigmoid")

        X_np = X_val.to_numpy()
        preds = calibrated.predict(X_np)

        assert preds.shape == (X_val.height,)
        assert set(np.unique(preds)).issubset({0, 1})


class TestCalibrateIsotonic:
    """Calibrate with method='isotonic'."""

    @pytest.mark.asyncio
    async def test_returns_calibrated_model(self) -> None:
        """isotonic calibration produces a CalibratedClassifierCV."""
        pipe = _make_pipeline()
        model, X_val, y_val = _fit_rf_and_data()

        calibrated = await pipe.calibrate(model, X_val, y_val, method="isotonic")

        assert isinstance(calibrated, CalibratedClassifierCV)

    @pytest.mark.asyncio
    async def test_predict_proba_valid_probabilities(self) -> None:
        """isotonic calibration produces valid probabilities."""
        pipe = _make_pipeline()
        model, X_val, y_val = _fit_rf_and_data()

        calibrated = await pipe.calibrate(model, X_val, y_val, method="isotonic")

        X_np = X_val.to_numpy()
        proba = calibrated.predict_proba(X_np)

        assert proba.shape == (X_val.height, 2)
        assert np.all(proba >= 0.0)
        assert np.all(proba <= 1.0)
        np.testing.assert_allclose(proba.sum(axis=1), 1.0, atol=1e-10)


class TestCalibrateDefaultMethod:
    """Default method is sigmoid when not specified."""

    @pytest.mark.asyncio
    async def test_default_is_sigmoid(self) -> None:
        """Calling calibrate() without method= uses sigmoid."""
        pipe = _make_pipeline()
        model, X_val, y_val = _fit_rf_and_data()

        calibrated = await pipe.calibrate(model, X_val, y_val)

        assert isinstance(calibrated, CalibratedClassifierCV)
        # The underlying calibrators use sigmoid
        assert calibrated.method == "sigmoid"


class TestCalibrateValidation:
    """Validation of the method parameter."""

    @pytest.mark.asyncio
    async def test_invalid_method_raises(self) -> None:
        """An unsupported method raises ValueError."""
        pipe = _make_pipeline()
        model, X_val, y_val = _fit_rf_and_data()

        with pytest.raises(ValueError, match="method must be one of"):
            await pipe.calibrate(model, X_val, y_val, method="beta")

    @pytest.mark.asyncio
    async def test_empty_method_raises(self) -> None:
        """Empty string method raises ValueError."""
        pipe = _make_pipeline()
        model, X_val, y_val = _fit_rf_and_data()

        with pytest.raises(ValueError, match="method must be one of"):
            await pipe.calibrate(model, X_val, y_val, method="")


class TestCalibrateBrierScore:
    """Calibrated model should produce well-calibrated probabilities."""

    @pytest.mark.asyncio
    async def test_brier_score_not_degraded(self) -> None:
        """Brier score of calibrated model is not worse than uncalibrated.

        RandomForest is typically already well-calibrated, so we verify
        that calibration at least does not make things significantly worse.
        """
        from sklearn.metrics import brier_score_loss

        pipe = _make_pipeline()
        model, X_val, y_val = _fit_rf_and_data(n_val=500, seed=99)

        calibrated = await pipe.calibrate(model, X_val, y_val, method="sigmoid")

        X_np = X_val.to_numpy()
        y_np = y_val.to_numpy()

        raw_proba = model.predict_proba(X_np)[:, 1]
        cal_proba = calibrated.predict_proba(X_np)[:, 1]

        raw_brier = brier_score_loss(y_np, raw_proba)
        cal_brier = brier_score_loss(y_np, cal_proba)

        # Calibrated Brier should not be dramatically worse
        # (allow 10% relative degradation since we calibrate on same data)
        assert cal_brier < raw_brier * 1.10 + 0.01, (
            f"Calibrated Brier {cal_brier:.4f} is significantly worse "
            f"than raw {raw_brier:.4f}"
        )

# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tests for EnsembleEngine -- blending, stacking, bagging, boosting."""
from __future__ import annotations

import numpy as np
import polars as pl
import pytest
from sklearn.datasets import make_classification, make_regression
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.tree import DecisionTreeClassifier, DecisionTreeRegressor

from kailash_ml.engines.ensemble import (
    BagResult,
    BlendResult,
    BoostResult,
    EnsembleEngine,
    StackResult,
    _compute_metrics,
    _detect_task_type,
    _get_model_name,
    _split_data,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def engine() -> EnsembleEngine:
    return EnsembleEngine()


@pytest.fixture()
def classification_data() -> pl.DataFrame:
    """100-row classification dataset with 5 features."""
    X, y = make_classification(
        n_samples=100,
        n_features=5,
        n_informative=3,
        n_redundant=1,
        random_state=42,
    )
    data = {f"f{i}": X[:, i].tolist() for i in range(5)}
    data["target"] = y.tolist()
    return pl.DataFrame(data)


@pytest.fixture()
def regression_data() -> pl.DataFrame:
    """100-row regression dataset with 5 features."""
    X, y = make_regression(
        n_samples=100,
        n_features=5,
        n_informative=3,
        random_state=42,
    )
    data = {f"f{i}": X[:, i].tolist() for i in range(5)}
    data["target"] = y.tolist()
    return pl.DataFrame(data)


@pytest.fixture()
def fitted_classifiers(classification_data: pl.DataFrame) -> list:
    """Three pre-fitted classifiers."""
    feature_cols = [c for c in classification_data.columns if c != "target"]
    X = classification_data.select(feature_cols).to_numpy()
    y = classification_data["target"].to_numpy()

    models = [
        RandomForestClassifier(n_estimators=10, random_state=42),
        LogisticRegression(max_iter=200, random_state=42),
        DecisionTreeClassifier(random_state=42),
    ]
    for m in models:
        m.fit(X, y)
    return models


@pytest.fixture()
def fitted_regressors(regression_data: pl.DataFrame) -> list:
    """Three pre-fitted regressors."""
    feature_cols = [c for c in regression_data.columns if c != "target"]
    X = regression_data.select(feature_cols).to_numpy()
    y = regression_data["target"].to_numpy()

    models = [
        RandomForestRegressor(n_estimators=10, random_state=42),
        Ridge(alpha=1.0),
        DecisionTreeRegressor(random_state=42),
    ]
    for m in models:
        m.fit(X, y)
    return models


# ---------------------------------------------------------------------------
# Helper function tests
# ---------------------------------------------------------------------------


class TestDetectTaskType:
    """Tests for _detect_task_type."""

    def test_binary_classification(self) -> None:
        y = np.array([0, 1, 0, 1, 0, 1])
        assert _detect_task_type(y) == "classification"

    def test_multiclass_classification(self) -> None:
        y = np.array([0, 1, 2, 0, 1, 2, 0, 1, 2])
        assert _detect_task_type(y) == "classification"

    def test_regression(self) -> None:
        y = np.arange(100, dtype=np.float64)
        assert _detect_task_type(y) == "regression"

    def test_boundary_20_unique(self) -> None:
        y = np.arange(20, dtype=np.float64)
        assert _detect_task_type(y) == "classification"

    def test_boundary_21_unique(self) -> None:
        y = np.arange(21, dtype=np.float64)
        assert _detect_task_type(y) == "regression"


class TestGetModelName:
    """Tests for _get_model_name."""

    def test_sklearn_model(self) -> None:
        model = LogisticRegression()
        name = _get_model_name(model)
        assert "LogisticRegression" in name
        assert "sklearn" in name


class TestComputeMetrics:
    """Tests for _compute_metrics."""

    def test_classification_metrics(self) -> None:
        y_true = np.array([0, 1, 0, 1, 0, 1])
        y_pred = np.array([0, 1, 0, 1, 0, 0])
        metrics = _compute_metrics(y_true, y_pred, "classification")
        assert "accuracy" in metrics
        assert "f1" in metrics
        assert "precision" in metrics
        assert "recall" in metrics
        assert 0.0 <= metrics["accuracy"] <= 1.0

    def test_regression_metrics(self) -> None:
        y_true = np.array([1.0, 2.0, 3.0, 4.0])
        y_pred = np.array([1.1, 2.1, 2.9, 4.2])
        metrics = _compute_metrics(y_true, y_pred, "regression")
        assert "mse" in metrics
        assert "rmse" in metrics
        assert "mae" in metrics
        assert "r2" in metrics
        assert metrics["mse"] >= 0
        assert metrics["rmse"] >= 0
        assert metrics["mae"] >= 0


class TestSplitData:
    """Tests for _split_data."""

    def test_split_shapes(self) -> None:
        df = pl.DataFrame(
            {
                "f0": list(range(100)),
                "f1": [float(x) for x in range(100)],
                "target": [0, 1] * 50,
            }
        )
        X_train, X_test, y_train, y_test = _split_data(
            df, ["f0", "f1"], "target", test_size=0.2
        )
        assert X_train.shape[0] == 80
        assert X_test.shape[0] == 20
        assert len(y_train) == 80
        assert len(y_test) == 20

    def test_missing_target_raises(self) -> None:
        df = pl.DataFrame({"f0": [1.0, 2.0], "f1": [3.0, 4.0]})
        with pytest.raises((ValueError, pl.exceptions.ColumnNotFoundError)):
            _split_data(df, ["f0", "f1"], "nonexistent")


# ---------------------------------------------------------------------------
# EnsembleEngine.blend
# ---------------------------------------------------------------------------


class TestBlend:
    """Tests for EnsembleEngine.blend."""

    def test_soft_blend_classification(
        self,
        engine: EnsembleEngine,
        classification_data: pl.DataFrame,
        fitted_classifiers: list,
    ) -> None:
        result = engine.blend(
            fitted_classifiers, classification_data, "target", method="soft"
        )
        assert isinstance(result, BlendResult)
        assert result.method == "soft"
        assert result.n_models == 3
        assert "accuracy" in result.metrics
        assert 0.0 <= result.metrics["accuracy"] <= 1.0
        assert len(result.component_contributions) == 3
        assert result.ensemble_model is not None

    def test_hard_blend_classification(
        self,
        engine: EnsembleEngine,
        classification_data: pl.DataFrame,
        fitted_classifiers: list,
    ) -> None:
        result = engine.blend(
            fitted_classifiers, classification_data, "target", method="hard"
        )
        assert isinstance(result, BlendResult)
        assert result.method == "hard"
        assert "accuracy" in result.metrics

    def test_blend_regression(
        self,
        engine: EnsembleEngine,
        regression_data: pl.DataFrame,
        fitted_regressors: list,
    ) -> None:
        result = engine.blend(
            fitted_regressors, regression_data, "target", method="soft"
        )
        assert isinstance(result, BlendResult)
        assert "r2" in result.metrics
        assert "mse" in result.metrics

    def test_blend_with_custom_weights(
        self,
        engine: EnsembleEngine,
        classification_data: pl.DataFrame,
        fitted_classifiers: list,
    ) -> None:
        weights = [0.5, 0.3, 0.2]
        result = engine.blend(
            fitted_classifiers,
            classification_data,
            "target",
            weights=weights,
        )
        assert result.weights == weights

    def test_blend_empty_models_raises(
        self, engine: EnsembleEngine, classification_data: pl.DataFrame
    ) -> None:
        with pytest.raises(ValueError, match="must not be empty"):
            engine.blend([], classification_data, "target")

    def test_blend_invalid_method_raises(
        self,
        engine: EnsembleEngine,
        classification_data: pl.DataFrame,
        fitted_classifiers: list,
    ) -> None:
        with pytest.raises(ValueError, match="must be 'soft' or 'hard'"):
            engine.blend(
                fitted_classifiers,
                classification_data,
                "target",
                method="invalid",
            )

    def test_blend_mismatched_weights_raises(
        self,
        engine: EnsembleEngine,
        classification_data: pl.DataFrame,
        fitted_classifiers: list,
    ) -> None:
        with pytest.raises(ValueError, match="weights length"):
            engine.blend(
                fitted_classifiers,
                classification_data,
                "target",
                weights=[0.5, 0.5],  # 2 weights, 3 models
            )

    def test_blend_component_contributions(
        self,
        engine: EnsembleEngine,
        classification_data: pl.DataFrame,
        fitted_classifiers: list,
    ) -> None:
        result = engine.blend(fitted_classifiers, classification_data, "target")
        for contrib in result.component_contributions:
            assert "model_index" in contrib
            assert "model_class" in contrib
            assert "weight" in contrib
            assert "metrics" in contrib
            assert "accuracy" in contrib["metrics"]

    def test_blend_hard_regression_warns(
        self,
        engine: EnsembleEngine,
        regression_data: pl.DataFrame,
        fitted_regressors: list,
    ) -> None:
        # Hard voting for regression should fall back to soft with a warning
        result = engine.blend(
            fitted_regressors,
            regression_data,
            "target",
            method="hard",
        )
        assert isinstance(result, BlendResult)
        assert "r2" in result.metrics


# ---------------------------------------------------------------------------
# EnsembleEngine.stack
# ---------------------------------------------------------------------------


class TestStack:
    """Tests for EnsembleEngine.stack."""

    def test_stack_classification(
        self,
        engine: EnsembleEngine,
        classification_data: pl.DataFrame,
        fitted_classifiers: list,
    ) -> None:
        result = engine.stack(
            fitted_classifiers,
            classification_data,
            "target",
            fold=3,
        )
        assert isinstance(result, StackResult)
        assert result.n_base_models == 3
        assert result.fold == 3
        assert result.meta_model_class == "sklearn.linear_model.LogisticRegression"
        assert "accuracy" in result.metrics
        assert result.ensemble_model is not None

    def test_stack_regression(
        self,
        engine: EnsembleEngine,
        regression_data: pl.DataFrame,
        fitted_regressors: list,
    ) -> None:
        result = engine.stack(
            fitted_regressors,
            regression_data,
            "target",
            meta_model_class="sklearn.linear_model.Ridge",
            fold=3,
        )
        assert isinstance(result, StackResult)
        assert result.meta_model_class == "sklearn.linear_model.Ridge"
        assert "r2" in result.metrics

    def test_stack_custom_meta_model(
        self,
        engine: EnsembleEngine,
        classification_data: pl.DataFrame,
        fitted_classifiers: list,
    ) -> None:
        result = engine.stack(
            fitted_classifiers,
            classification_data,
            "target",
            meta_model_class="sklearn.tree.DecisionTreeClassifier",
            fold=3,
        )
        assert result.meta_model_class == "sklearn.tree.DecisionTreeClassifier"

    def test_stack_empty_models_raises(
        self, engine: EnsembleEngine, classification_data: pl.DataFrame
    ) -> None:
        with pytest.raises(ValueError, match="must not be empty"):
            engine.stack([], classification_data, "target")

    def test_stack_invalid_meta_model_raises(
        self,
        engine: EnsembleEngine,
        classification_data: pl.DataFrame,
        fitted_classifiers: list,
    ) -> None:
        with pytest.raises(ValueError, match="not in allowed prefixes"):
            engine.stack(
                fitted_classifiers,
                classification_data,
                "target",
                meta_model_class="os.system",
            )

    def test_stack_bare_class_name_raises(
        self,
        engine: EnsembleEngine,
        classification_data: pl.DataFrame,
        fitted_classifiers: list,
    ) -> None:
        # A bare class name (no module prefix) hits the allowlist check
        with pytest.raises(ValueError, match="not in allowed prefixes"):
            engine.stack(
                fitted_classifiers,
                classification_data,
                "target",
                meta_model_class="LogisticRegression",
            )

    def test_stack_component_contributions(
        self,
        engine: EnsembleEngine,
        classification_data: pl.DataFrame,
        fitted_classifiers: list,
    ) -> None:
        result = engine.stack(fitted_classifiers, classification_data, "target", fold=3)
        assert len(result.component_contributions) == 3
        for contrib in result.component_contributions:
            assert "model_index" in contrib
            assert "model_class" in contrib
            assert "metrics" in contrib


# ---------------------------------------------------------------------------
# EnsembleEngine.bag
# ---------------------------------------------------------------------------


class TestBag:
    """Tests for EnsembleEngine.bag."""

    def test_bag_classification(
        self, engine: EnsembleEngine, classification_data: pl.DataFrame
    ) -> None:
        base = DecisionTreeClassifier(random_state=42)
        result = engine.bag(base, classification_data, "target", n_estimators=5)
        assert isinstance(result, BagResult)
        assert result.n_estimators == 5
        assert result.max_samples == 1.0
        assert result.max_features == 1.0
        assert "accuracy" in result.metrics
        assert result.ensemble_model is not None

    def test_bag_regression(
        self, engine: EnsembleEngine, regression_data: pl.DataFrame
    ) -> None:
        base = DecisionTreeRegressor(random_state=42)
        result = engine.bag(base, regression_data, "target", n_estimators=5)
        assert isinstance(result, BagResult)
        assert "r2" in result.metrics
        assert "mse" in result.metrics

    def test_bag_custom_params(
        self, engine: EnsembleEngine, classification_data: pl.DataFrame
    ) -> None:
        base = DecisionTreeClassifier(random_state=42)
        result = engine.bag(
            base,
            classification_data,
            "target",
            n_estimators=20,
            max_samples=0.8,
            max_features=0.5,
        )
        assert result.n_estimators == 20
        assert result.max_samples == 0.8
        assert result.max_features == 0.5

    def test_bag_base_model_class_recorded(
        self, engine: EnsembleEngine, classification_data: pl.DataFrame
    ) -> None:
        base = DecisionTreeClassifier(random_state=42)
        result = engine.bag(base, classification_data, "target")
        assert "DecisionTreeClassifier" in result.base_model_class


# ---------------------------------------------------------------------------
# EnsembleEngine.boost
# ---------------------------------------------------------------------------


class TestBoost:
    """Tests for EnsembleEngine.boost."""

    def test_boost_classification(
        self, engine: EnsembleEngine, classification_data: pl.DataFrame
    ) -> None:
        base = DecisionTreeClassifier(max_depth=1, random_state=42)
        result = engine.boost(base, classification_data, "target", n_estimators=10)
        assert isinstance(result, BoostResult)
        assert result.n_estimators == 10
        assert result.learning_rate == 0.1
        assert "accuracy" in result.metrics
        assert result.ensemble_model is not None

    def test_boost_regression(
        self, engine: EnsembleEngine, regression_data: pl.DataFrame
    ) -> None:
        base = DecisionTreeRegressor(max_depth=3, random_state=42)
        result = engine.boost(base, regression_data, "target", n_estimators=10)
        assert isinstance(result, BoostResult)
        assert "r2" in result.metrics

    def test_boost_custom_learning_rate(
        self, engine: EnsembleEngine, classification_data: pl.DataFrame
    ) -> None:
        base = DecisionTreeClassifier(max_depth=1, random_state=42)
        result = engine.boost(
            base,
            classification_data,
            "target",
            n_estimators=20,
            learning_rate=0.05,
        )
        assert result.learning_rate == 0.05
        assert result.n_estimators == 20

    def test_boost_base_model_class_recorded(
        self, engine: EnsembleEngine, classification_data: pl.DataFrame
    ) -> None:
        base = DecisionTreeClassifier(max_depth=1, random_state=42)
        result = engine.boost(base, classification_data, "target")
        assert "DecisionTreeClassifier" in result.base_model_class


# ---------------------------------------------------------------------------
# Frozen dataclass validation
# ---------------------------------------------------------------------------


class TestResultImmutability:
    """Verify result dataclasses are frozen."""

    def test_blend_result_frozen(
        self,
        engine: EnsembleEngine,
        classification_data: pl.DataFrame,
        fitted_classifiers: list,
    ) -> None:
        result = engine.blend(fitted_classifiers, classification_data, "target")
        with pytest.raises(AttributeError):
            result.method = "changed"  # type: ignore[misc]

    def test_stack_result_frozen(
        self,
        engine: EnsembleEngine,
        classification_data: pl.DataFrame,
        fitted_classifiers: list,
    ) -> None:
        result = engine.stack(fitted_classifiers, classification_data, "target", fold=3)
        with pytest.raises(AttributeError):
            result.fold = 99  # type: ignore[misc]

    def test_bag_result_frozen(
        self, engine: EnsembleEngine, classification_data: pl.DataFrame
    ) -> None:
        base = DecisionTreeClassifier(random_state=42)
        result = engine.bag(base, classification_data, "target")
        with pytest.raises(AttributeError):
            result.n_estimators = 999  # type: ignore[misc]

    def test_boost_result_frozen(
        self, engine: EnsembleEngine, classification_data: pl.DataFrame
    ) -> None:
        base = DecisionTreeClassifier(max_depth=1, random_state=42)
        result = engine.boost(base, classification_data, "target")
        with pytest.raises(AttributeError):
            result.learning_rate = 999.0  # type: ignore[misc]

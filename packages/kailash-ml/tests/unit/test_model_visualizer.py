# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tests for ModelVisualizer (P2 experimental)."""
from __future__ import annotations

import warnings

import numpy as np
import pytest
from kailash_ml._decorators import ExperimentalWarning, _warned_classes
from kailash_ml.engines.model_visualizer import ModelVisualizer
from sklearn.datasets import make_classification, make_regression
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LinearRegression, LogisticRegression


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_experimental_warnings():
    """Reset the experimental warning tracker so each test is independent."""
    _warned_classes.discard("ModelVisualizer")
    yield
    _warned_classes.discard("ModelVisualizer")


@pytest.fixture()
def binary_data():
    """Binary classification dataset with a trained LogisticRegression."""
    X, y = make_classification(n_samples=200, n_features=5, random_state=42)
    model = LogisticRegression(random_state=42, max_iter=200)
    model.fit(X, y)
    return X, y, model


@pytest.fixture()
def multifeature_data():
    """Classification dataset with many features for importance testing."""
    X, y = make_classification(
        n_samples=200, n_features=10, n_informative=5, random_state=42
    )
    model = RandomForestClassifier(n_estimators=20, random_state=42)
    model.fit(X, y)
    feature_names = [f"feat_{i}" for i in range(10)]
    return X, y, model, feature_names


@pytest.fixture()
def regression_data():
    """Regression dataset with a trained LinearRegression."""
    X, y = make_regression(n_samples=200, n_features=5, noise=10, random_state=42)
    model = LinearRegression()
    model.fit(X, y)
    return X, y, model


# ---------------------------------------------------------------------------
# @experimental decorator
# ---------------------------------------------------------------------------


class TestExperimentalDecorator:
    """Tests for the @experimental decorator on ModelVisualizer."""

    def test_first_instantiation_warns(self) -> None:
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            ModelVisualizer()
            assert len(w) == 1
            assert issubclass(w[0].category, ExperimentalWarning)
            assert "ModelVisualizer" in str(w[0].message)
            assert "P2" in str(w[0].message)

    def test_second_instantiation_silent(self) -> None:
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            ModelVisualizer()  # first -- warns
            ModelVisualizer()  # second -- silent
            experimental_warnings = [
                x for x in w if issubclass(x.category, ExperimentalWarning)
            ]
            assert len(experimental_warnings) == 1

    def test_quality_tier_attribute(self) -> None:
        assert ModelVisualizer._quality_tier == "P2"


# ---------------------------------------------------------------------------
# confusion_matrix
# ---------------------------------------------------------------------------


class TestConfusionMatrix:
    """Tests for ModelVisualizer.confusion_matrix."""

    def test_returns_figure(self, binary_data) -> None:
        import plotly.graph_objects as go

        X, y, model = binary_data
        y_pred = model.predict(X)
        viz = ModelVisualizer()
        fig = viz.confusion_matrix(y, y_pred)
        assert isinstance(fig, go.Figure)

    def test_heatmap_data_shape(self, binary_data) -> None:
        X, y, model = binary_data
        y_pred = model.predict(X)
        viz = ModelVisualizer()
        fig = viz.confusion_matrix(y, y_pred)
        # Binary classification -> 2x2 matrix
        z_data = fig.data[0].z
        assert len(z_data) == 2
        assert len(z_data[0]) == 2

    def test_custom_labels(self, binary_data) -> None:
        X, y, model = binary_data
        y_pred = model.predict(X)
        viz = ModelVisualizer()
        fig = viz.confusion_matrix(y, y_pred, labels=["Negative", "Positive"])
        assert list(fig.data[0].x) == ["Negative", "Positive"]
        assert list(fig.data[0].y) == ["Negative", "Positive"]

    def test_title_set(self, binary_data) -> None:
        X, y, model = binary_data
        y_pred = model.predict(X)
        viz = ModelVisualizer()
        fig = viz.confusion_matrix(y, y_pred)
        assert "Confusion Matrix" in fig.layout.title.text


# ---------------------------------------------------------------------------
# roc_curve
# ---------------------------------------------------------------------------


class TestRocCurve:
    """Tests for ModelVisualizer.roc_curve."""

    def test_returns_figure(self, binary_data) -> None:
        import plotly.graph_objects as go

        X, y, model = binary_data
        y_scores = model.predict_proba(X)[:, 1]
        viz = ModelVisualizer()
        fig = viz.roc_curve(y, y_scores)
        assert isinstance(fig, go.Figure)

    def test_has_two_traces(self, binary_data) -> None:
        X, y, model = binary_data
        y_scores = model.predict_proba(X)[:, 1]
        viz = ModelVisualizer()
        fig = viz.roc_curve(y, y_scores)
        # ROC line + random baseline
        assert len(fig.data) == 2

    def test_auc_in_title(self, binary_data) -> None:
        X, y, model = binary_data
        y_scores = model.predict_proba(X)[:, 1]
        viz = ModelVisualizer()
        fig = viz.roc_curve(y, y_scores)
        assert "AUC" in fig.layout.title.text

    def test_auc_reasonable(self, binary_data) -> None:
        X, y, model = binary_data
        y_scores = model.predict_proba(X)[:, 1]
        viz = ModelVisualizer()
        fig = viz.roc_curve(y, y_scores)
        # ROC trace x values should start near 0 and end near 1
        roc_trace = fig.data[0]
        assert roc_trace.x[0] == pytest.approx(0.0, abs=0.01)
        assert roc_trace.x[-1] == pytest.approx(1.0, abs=0.01)


# ---------------------------------------------------------------------------
# precision_recall_curve
# ---------------------------------------------------------------------------


class TestPrecisionRecallCurve:
    """Tests for ModelVisualizer.precision_recall_curve."""

    def test_returns_figure(self, binary_data) -> None:
        import plotly.graph_objects as go

        X, y, model = binary_data
        y_scores = model.predict_proba(X)[:, 1]
        viz = ModelVisualizer()
        fig = viz.precision_recall_curve(y, y_scores)
        assert isinstance(fig, go.Figure)

    def test_ap_in_title(self, binary_data) -> None:
        X, y, model = binary_data
        y_scores = model.predict_proba(X)[:, 1]
        viz = ModelVisualizer()
        fig = viz.precision_recall_curve(y, y_scores)
        assert "AP" in fig.layout.title.text

    def test_has_one_trace(self, binary_data) -> None:
        X, y, model = binary_data
        y_scores = model.predict_proba(X)[:, 1]
        viz = ModelVisualizer()
        fig = viz.precision_recall_curve(y, y_scores)
        assert len(fig.data) == 1


# ---------------------------------------------------------------------------
# feature_importance
# ---------------------------------------------------------------------------


class TestFeatureImportance:
    """Tests for ModelVisualizer.feature_importance."""

    def test_returns_figure_tree_model(self, multifeature_data) -> None:
        import plotly.graph_objects as go

        X, y, model, names = multifeature_data
        viz = ModelVisualizer()
        fig = viz.feature_importance(model, names)
        assert isinstance(fig, go.Figure)

    def test_top_n_limits_bars(self, multifeature_data) -> None:
        X, y, model, names = multifeature_data
        viz = ModelVisualizer()
        fig = viz.feature_importance(model, names, top_n=5)
        # Horizontal bar chart data
        bar_data = fig.data[0]
        assert len(bar_data.y) == 5

    def test_coef_fallback_for_linear(self, binary_data) -> None:
        import plotly.graph_objects as go

        X, y, model = binary_data
        names = [f"f{i}" for i in range(X.shape[1])]
        viz = ModelVisualizer()
        fig = viz.feature_importance(model, names)
        assert isinstance(fig, go.Figure)

    def test_permutation_fallback(self, binary_data) -> None:
        """Test fallback to permutation importance for models without
        feature_importances_ or coef_."""
        from sklearn.neighbors import KNeighborsClassifier

        import plotly.graph_objects as go

        X, y, _ = binary_data
        knn = KNeighborsClassifier(n_neighbors=3)
        knn.fit(X, y)
        names = [f"f{i}" for i in range(X.shape[1])]
        viz = ModelVisualizer()
        fig = viz.feature_importance(knn, names, X=X, y=y)
        assert isinstance(fig, go.Figure)

    def test_raises_without_X_y_fallback(self, binary_data) -> None:
        from sklearn.neighbors import KNeighborsClassifier

        X, y, _ = binary_data
        knn = KNeighborsClassifier(n_neighbors=3)
        knn.fit(X, y)
        names = [f"f{i}" for i in range(X.shape[1])]
        viz = ModelVisualizer()
        with pytest.raises(ValueError, match="Provide X and y"):
            viz.feature_importance(knn, names)

    def test_mismatched_names_raises(self, multifeature_data) -> None:
        X, y, model, _ = multifeature_data
        viz = ModelVisualizer()
        with pytest.raises(ValueError, match="feature_names length"):
            viz.feature_importance(model, ["a", "b"])  # too few


# ---------------------------------------------------------------------------
# learning_curve
# ---------------------------------------------------------------------------


class TestLearningCurve:
    """Tests for ModelVisualizer.learning_curve."""

    def test_returns_figure(self, binary_data) -> None:
        import plotly.graph_objects as go

        X, y, model = binary_data
        viz = ModelVisualizer()
        fig = viz.learning_curve(model, X, y, cv=3)
        assert isinstance(fig, go.Figure)

    def test_has_training_and_validation_traces(self, binary_data) -> None:
        X, y, model = binary_data
        viz = ModelVisualizer()
        fig = viz.learning_curve(model, X, y, cv=3)
        # 2 named lines + 2 fill bands = 4 traces
        assert len(fig.data) == 4

    def test_title_set(self, binary_data) -> None:
        X, y, model = binary_data
        viz = ModelVisualizer()
        fig = viz.learning_curve(model, X, y, cv=3)
        assert "Learning Curve" in fig.layout.title.text


# ---------------------------------------------------------------------------
# residuals
# ---------------------------------------------------------------------------


class TestResiduals:
    """Tests for ModelVisualizer.residuals."""

    def test_returns_figure(self, regression_data) -> None:
        import plotly.graph_objects as go

        X, y, model = regression_data
        y_pred = model.predict(X)
        viz = ModelVisualizer()
        fig = viz.residuals(y, y_pred)
        assert isinstance(fig, go.Figure)

    def test_has_three_traces(self, regression_data) -> None:
        X, y, model = regression_data
        y_pred = model.predict(X)
        viz = ModelVisualizer()
        fig = viz.residuals(y, y_pred)
        # scatter + perfect line + histogram = 3 traces
        assert len(fig.data) == 3

    def test_title_set(self, regression_data) -> None:
        X, y, model = regression_data
        y_pred = model.predict(X)
        viz = ModelVisualizer()
        fig = viz.residuals(y, y_pred)
        assert "Residual" in fig.layout.title.text


# ---------------------------------------------------------------------------
# calibration_curve
# ---------------------------------------------------------------------------


class TestCalibrationCurve:
    """Tests for ModelVisualizer.calibration_curve."""

    def test_returns_figure(self, binary_data) -> None:
        import plotly.graph_objects as go

        X, y, model = binary_data
        y_proba = model.predict_proba(X)[:, 1]
        viz = ModelVisualizer()
        fig = viz.calibration_curve(y, y_proba)
        assert isinstance(fig, go.Figure)

    def test_has_two_traces(self, binary_data) -> None:
        X, y, model = binary_data
        y_proba = model.predict_proba(X)[:, 1]
        viz = ModelVisualizer()
        fig = viz.calibration_curve(y, y_proba)
        # calibration line + perfect diagonal
        assert len(fig.data) == 2

    def test_title_set(self, binary_data) -> None:
        X, y, model = binary_data
        y_proba = model.predict_proba(X)[:, 1]
        viz = ModelVisualizer()
        fig = viz.calibration_curve(y, y_proba)
        assert "Calibration" in fig.layout.title.text


# ---------------------------------------------------------------------------
# metric_comparison
# ---------------------------------------------------------------------------


class TestMetricComparison:
    """Tests for ModelVisualizer.metric_comparison."""

    def test_returns_figure(self) -> None:
        import plotly.graph_objects as go

        results = {
            "LogisticRegression": {"accuracy": 0.95, "f1": 0.93},
            "RandomForest": {"accuracy": 0.97, "f1": 0.96},
        }
        viz = ModelVisualizer()
        fig = viz.metric_comparison(results)
        assert isinstance(fig, go.Figure)

    def test_correct_number_of_traces(self) -> None:
        results = {
            "Model_A": {"accuracy": 0.9, "f1": 0.88, "precision": 0.91},
            "Model_B": {"accuracy": 0.85, "f1": 0.83, "precision": 0.87},
        }
        viz = ModelVisualizer()
        fig = viz.metric_comparison(results)
        # One trace per metric
        assert len(fig.data) == 3

    def test_empty_results_raises(self) -> None:
        viz = ModelVisualizer()
        with pytest.raises(ValueError, match="at least one model"):
            viz.metric_comparison({})

    def test_barmode_is_group(self) -> None:
        results = {"A": {"acc": 0.9}, "B": {"acc": 0.8}}
        viz = ModelVisualizer()
        fig = viz.metric_comparison(results)
        assert fig.layout.barmode == "group"


# ---------------------------------------------------------------------------
# training_history
# ---------------------------------------------------------------------------


class TestTrainingHistory:
    """Tests for ModelVisualizer.training_history."""

    def test_returns_figure(self) -> None:
        import plotly.graph_objects as go

        metrics = {"train_loss": [0.9, 0.5, 0.3], "val_loss": [1.0, 0.6, 0.4]}
        viz = ModelVisualizer()
        fig = viz.training_history(metrics)
        assert isinstance(fig, go.Figure)

    def test_one_trace_per_metric(self) -> None:
        metrics = {
            "train_loss": [0.9, 0.5, 0.3],
            "val_loss": [1.0, 0.6, 0.4],
            "lr": [0.01, 0.005, 0.001],
        }
        viz = ModelVisualizer()
        fig = viz.training_history(metrics)
        assert len(fig.data) == 3

    def test_x_axis_starts_at_one(self) -> None:
        metrics = {"loss": [0.9, 0.5, 0.3]}
        viz = ModelVisualizer()
        fig = viz.training_history(metrics)
        assert list(fig.data[0].x) == [1, 2, 3]

    def test_custom_x_label(self) -> None:
        metrics = {"loss": [0.9, 0.5]}
        viz = ModelVisualizer()
        fig = viz.training_history(metrics, x_label="Step")
        assert fig.layout.xaxis.title.text == "Step"

    def test_empty_metrics_raises(self) -> None:
        viz = ModelVisualizer()
        with pytest.raises(ValueError, match="at least one series"):
            viz.training_history({})


# ---------------------------------------------------------------------------
# Lazy-loading from top-level package
# ---------------------------------------------------------------------------


class TestLazyLoading:
    """Test that ModelVisualizer is accessible from kailash_ml top-level."""

    def test_import_from_package(self) -> None:
        from kailash_ml import ModelVisualizer as MV

        assert MV is ModelVisualizer

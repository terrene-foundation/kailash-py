# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tests for ModelExplainer -- SHAP-based model explainability (#328)."""
from __future__ import annotations

from unittest.mock import patch

import numpy as np
import polars as pl
import pytest
from sklearn.datasets import make_classification
from sklearn.ensemble import RandomForestClassifier

shap = pytest.importorskip("shap")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def clf_data() -> tuple[pl.DataFrame, RandomForestClassifier, list[str]]:
    """Binary classification dataset with fitted RandomForestClassifier.

    Returns (polars DataFrame of features, fitted model, feature names).
    """
    X_np, y_np = make_classification(
        n_samples=100, n_features=5, n_informative=3, random_state=42
    )
    feature_names = [f"feat_{i}" for i in range(5)]
    df = pl.DataFrame({name: X_np[:, i] for i, name in enumerate(feature_names)})
    model = RandomForestClassifier(n_estimators=10, random_state=42)
    model.fit(X_np, y_np)
    return df, model, feature_names


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


class TestModelExplainerInit:
    """Tests for ModelExplainer initialization."""

    def test_creates_from_polars_dataframe(self, clf_data) -> None:
        from kailash_ml.engines.model_explainer import ModelExplainer

        df, model, names = clf_data
        explainer = ModelExplainer(model, df)
        assert explainer._feature_names == names

    def test_custom_feature_names(self, clf_data) -> None:
        from kailash_ml.engines.model_explainer import ModelExplainer

        df, model, _ = clf_data
        custom = ["a", "b", "c", "d", "e"]
        explainer = ModelExplainer(model, df, feature_names=custom)
        assert explainer._feature_names == custom

    def test_rejects_non_polars_data(self, clf_data) -> None:
        from kailash_ml.engines.model_explainer import ModelExplainer

        _, model, _ = clf_data
        with pytest.raises(TypeError, match="polars DataFrame"):
            ModelExplainer(model, [[1, 2], [3, 4]])  # type: ignore[arg-type]

    def test_lazy_import_from_package(self) -> None:
        from kailash_ml import ModelExplainer
        from kailash_ml.engines.model_explainer import (
            ModelExplainer as DirectExplainer,
        )

        assert ModelExplainer is DirectExplainer


# ---------------------------------------------------------------------------
# explain_global
# ---------------------------------------------------------------------------


class TestExplainGlobal:
    """Tests for ModelExplainer.explain_global()."""

    def test_returns_expected_keys(self, clf_data) -> None:
        from kailash_ml.engines.model_explainer import ModelExplainer

        df, model, names = clf_data
        explainer = ModelExplainer(model, df)
        result = explainer.explain_global()
        assert "shap_values" in result
        assert "feature_importance" in result
        assert "feature_names" in result

    def test_shap_values_shape(self, clf_data) -> None:
        from kailash_ml.engines.model_explainer import ModelExplainer

        df, model, names = clf_data
        explainer = ModelExplainer(model, df)
        result = explainer.explain_global()
        shap_vals = result["shap_values"]
        assert shap_vals.shape == (100, 5)

    def test_feature_importance_is_dict(self, clf_data) -> None:
        from kailash_ml.engines.model_explainer import ModelExplainer

        df, model, names = clf_data
        explainer = ModelExplainer(model, df)
        result = explainer.explain_global()
        importance = result["feature_importance"]
        assert isinstance(importance, dict)
        assert len(importance) == 5
        # All values should be non-negative
        for val in importance.values():
            assert val >= 0.0

    def test_max_display_limits_features(self, clf_data) -> None:
        from kailash_ml.engines.model_explainer import ModelExplainer

        df, model, names = clf_data
        explainer = ModelExplainer(model, df)
        result = explainer.explain_global(max_display=3)
        assert len(result["feature_importance"]) == 3

    def test_feature_names_match(self, clf_data) -> None:
        from kailash_ml.engines.model_explainer import ModelExplainer

        df, model, names = clf_data
        explainer = ModelExplainer(model, df)
        result = explainer.explain_global()
        assert result["feature_names"] == names


# ---------------------------------------------------------------------------
# explain_local
# ---------------------------------------------------------------------------


class TestExplainLocal:
    """Tests for ModelExplainer.explain_local()."""

    def test_returns_expected_keys(self, clf_data) -> None:
        from kailash_ml.engines.model_explainer import ModelExplainer

        df, model, names = clf_data
        explainer = ModelExplainer(model, df)
        result = explainer.explain_local(df)
        assert "shap_values" in result
        assert "base_value" in result
        assert "feature_values" in result
        assert "feature_names" in result

    def test_shap_values_shape_single_row(self, clf_data) -> None:
        from kailash_ml.engines.model_explainer import ModelExplainer

        df, model, names = clf_data
        explainer = ModelExplainer(model, df)
        result = explainer.explain_local(df, index=0)
        assert result["shap_values"].shape == (5,)

    def test_feature_values_match_input(self, clf_data) -> None:
        from kailash_ml.engines.model_explainer import ModelExplainer

        df, model, names = clf_data
        explainer = ModelExplainer(model, df)
        result = explainer.explain_local(df, index=2)
        expected = df.row(2)
        for i, val in enumerate(expected):
            assert result["feature_values"][i] == pytest.approx(val, abs=1e-10)

    def test_base_value_is_scalar(self, clf_data) -> None:
        from kailash_ml.engines.model_explainer import ModelExplainer

        df, model, names = clf_data
        explainer = ModelExplainer(model, df)
        result = explainer.explain_local(df)
        assert isinstance(result["base_value"], float)

    def test_index_out_of_range_raises(self, clf_data) -> None:
        from kailash_ml.engines.model_explainer import ModelExplainer

        df, model, names = clf_data
        explainer = ModelExplainer(model, df)
        with pytest.raises(IndexError, match="out of range"):
            explainer.explain_local(df, index=999)

    def test_rejects_non_polars(self, clf_data) -> None:
        from kailash_ml.engines.model_explainer import ModelExplainer

        df, model, names = clf_data
        explainer = ModelExplainer(model, df)
        with pytest.raises(TypeError, match="polars DataFrame"):
            explainer.explain_local(np.zeros((5, 5)))  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# explain_dependence
# ---------------------------------------------------------------------------


class TestExplainDependence:
    """Tests for ModelExplainer.explain_dependence()."""

    def test_returns_expected_keys(self, clf_data) -> None:
        from kailash_ml.engines.model_explainer import ModelExplainer

        df, model, names = clf_data
        explainer = ModelExplainer(model, df)
        result = explainer.explain_dependence("feat_0")
        assert "feature_values" in result
        assert "shap_values" in result
        assert "interaction_values" in result

    def test_feature_values_shape(self, clf_data) -> None:
        from kailash_ml.engines.model_explainer import ModelExplainer

        df, model, names = clf_data
        explainer = ModelExplainer(model, df)
        result = explainer.explain_dependence("feat_0")
        assert result["feature_values"].shape == (100,)
        assert result["shap_values"].shape == (100,)

    def test_no_interaction_returns_none(self, clf_data) -> None:
        from kailash_ml.engines.model_explainer import ModelExplainer

        df, model, names = clf_data
        explainer = ModelExplainer(model, df)
        result = explainer.explain_dependence("feat_0")
        assert result["interaction_values"] is None

    def test_with_interaction_feature(self, clf_data) -> None:
        from kailash_ml.engines.model_explainer import ModelExplainer

        df, model, names = clf_data
        explainer = ModelExplainer(model, df)
        result = explainer.explain_dependence("feat_0", interaction_feature="feat_1")
        assert result["interaction_values"] is not None
        assert result["interaction_values"].shape == (100,)

    def test_unknown_feature_raises(self, clf_data) -> None:
        from kailash_ml.engines.model_explainer import ModelExplainer

        df, model, names = clf_data
        explainer = ModelExplainer(model, df)
        with pytest.raises(ValueError, match="not found"):
            explainer.explain_dependence("nonexistent")

    def test_unknown_interaction_feature_raises(self, clf_data) -> None:
        from kailash_ml.engines.model_explainer import ModelExplainer

        df, model, names = clf_data
        explainer = ModelExplainer(model, df)
        with pytest.raises(ValueError, match="not found"):
            explainer.explain_dependence("feat_0", interaction_feature="bad")


# ---------------------------------------------------------------------------
# to_plotly
# ---------------------------------------------------------------------------


class TestToPlotly:
    """Tests for ModelExplainer.to_plotly()."""

    def test_summary_returns_figure(self, clf_data) -> None:
        import plotly.graph_objects as go

        from kailash_ml.engines.model_explainer import ModelExplainer

        df, model, names = clf_data
        explainer = ModelExplainer(model, df)
        fig = explainer.to_plotly("summary")
        assert isinstance(fig, go.Figure)
        assert "SHAP" in fig.layout.title.text

    def test_beeswarm_returns_figure(self, clf_data) -> None:
        import plotly.graph_objects as go

        from kailash_ml.engines.model_explainer import ModelExplainer

        df, model, names = clf_data
        explainer = ModelExplainer(model, df)
        fig = explainer.to_plotly("beeswarm")
        assert isinstance(fig, go.Figure)
        assert "Beeswarm" in fig.layout.title.text

    def test_dependence_returns_figure(self, clf_data) -> None:
        import plotly.graph_objects as go

        from kailash_ml.engines.model_explainer import ModelExplainer

        df, model, names = clf_data
        explainer = ModelExplainer(model, df)
        fig = explainer.to_plotly("dependence", feature="feat_0")
        assert isinstance(fig, go.Figure)
        assert "feat_0" in fig.layout.title.text

    def test_dependence_without_feature_raises(self, clf_data) -> None:
        from kailash_ml.engines.model_explainer import ModelExplainer

        df, model, names = clf_data
        explainer = ModelExplainer(model, df)
        with pytest.raises(ValueError, match="requires a 'feature'"):
            explainer.to_plotly("dependence")

    def test_unknown_plot_type_raises(self, clf_data) -> None:
        from kailash_ml.engines.model_explainer import ModelExplainer

        df, model, names = clf_data
        explainer = ModelExplainer(model, df)
        with pytest.raises(ValueError, match="Unknown plot_type"):
            explainer.to_plotly("nonexistent")

    def test_summary_max_display(self, clf_data) -> None:
        from kailash_ml.engines.model_explainer import ModelExplainer

        df, model, names = clf_data
        explainer = ModelExplainer(model, df)
        fig = explainer.to_plotly("summary", max_display=3)
        # Horizontal bar chart should have 3 bars
        assert len(fig.data[0].y) == 3

    def test_dependence_with_interaction(self, clf_data) -> None:
        import plotly.graph_objects as go

        from kailash_ml.engines.model_explainer import ModelExplainer

        df, model, names = clf_data
        explainer = ModelExplainer(model, df)
        fig = explainer.to_plotly(
            "dependence", feature="feat_0", interaction_feature="feat_1"
        )
        assert isinstance(fig, go.Figure)
        assert "feat_1" in fig.layout.title.text


# ---------------------------------------------------------------------------
# ImportError when shap is not installed
# ---------------------------------------------------------------------------


class TestShapImportError:
    """Test that a clear error is raised when shap is not installed."""

    def test_import_error_message(self, clf_data) -> None:
        df, model, _ = clf_data

        with patch.dict("sys.modules", {"shap": None}):
            # Re-import to trigger the import check
            import importlib

            from kailash_ml.engines import model_explainer

            importlib.reload(model_explainer)

            with pytest.raises(
                ImportError, match="pip install kailash-ml\\[explain\\]"
            ):
                model_explainer.ModelExplainer(model, df)

            # Restore module so other tests are unaffected
            importlib.reload(model_explainer)

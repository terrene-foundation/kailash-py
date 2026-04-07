# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""ModelExplainer engine -- SHAP-based model explainability.

Provides global and local explanations for fitted sklearn-compatible models.
Requires the ``[explain]`` extra: ``pip install kailash-ml[explain]``.

All methods accept polars DataFrames (consistent with kailash-ml's
polars-native design) and convert to numpy at the framework boundary
via the interop pattern.
"""
from __future__ import annotations

import logging
from typing import Any

import numpy as np
import polars as pl

logger = logging.getLogger(__name__)

__all__ = [
    "ModelExplainer",
]


def _ensure_shap() -> Any:
    """Import and return the shap module; raise helpful error if missing."""
    try:
        import shap

        return shap
    except ImportError as exc:
        raise ImportError(
            "SHAP is required for model explainability. "
            "Install it with: pip install kailash-ml[explain]"
        ) from exc


def _polars_to_numpy(df: pl.DataFrame) -> np.ndarray:
    """Convert a polars DataFrame to a 2-D float64 numpy array.

    Handles boolean and categorical columns by casting to numeric.
    Nulls become NaN.
    """
    arrays: list[np.ndarray] = []
    for col_name in df.columns:
        col = df[col_name]
        dtype = col.dtype

        if dtype == pl.Boolean:
            arrays.append(col.cast(pl.Int8).fill_null(0).to_numpy().astype(np.float64))
        elif dtype == pl.Categorical:
            arrays.append(col.to_physical().fill_null(-1).to_numpy().astype(np.float64))
        elif dtype in (pl.Utf8, pl.String):
            raise ValueError(
                f"Column '{col_name}' is Utf8/String -- cast to pl.Categorical first."
            )
        else:
            arrays.append(col.fill_null(float("nan")).to_numpy().astype(np.float64))

    if not arrays:
        return np.empty((df.height, 0), dtype=np.float64)
    return np.column_stack(arrays)


class ModelExplainer:
    """SHAP-based model explainability engine.

    Provides global and local explanations for fitted sklearn-compatible
    models.  Requires the ``[explain]`` extra::

        pip install kailash-ml[explain]

    Parameters
    ----------
    model:
        A fitted sklearn-compatible model (must have ``predict`` or
        ``predict_proba``).
    X:
        Reference/background data as a polars DataFrame.  Used for
        SHAP value calculations.
    feature_names:
        Optional feature name override.  When ``None`` the column
        names from *X* are used.
    """

    def __init__(
        self,
        model: Any,
        X: pl.DataFrame,
        *,
        feature_names: list[str] | None = None,
    ) -> None:
        shap = _ensure_shap()

        if not isinstance(X, pl.DataFrame):
            raise TypeError("X must be a polars DataFrame")

        self._model = model
        self._feature_names = (
            feature_names if feature_names is not None else list(X.columns)
        )
        self._X_numpy = _polars_to_numpy(X)

        # shap.Explainer auto-selects the best algorithm:
        # TreeExplainer for tree-based, KernelExplainer for others.
        self._explainer = shap.Explainer(model, self._X_numpy)
        self._shap_values: np.ndarray | None = None

    def _compute_shap_values(self) -> np.ndarray:
        """Compute and cache SHAP values for the reference data."""
        if self._shap_values is None:
            explanation = self._explainer(self._X_numpy)
            values = explanation.values
            # For binary classification, shap may return 3-D array
            # (n_samples, n_features, n_classes).  Use the positive-class
            # slice for consistency.
            if values.ndim == 3:
                if values.shape[2] == 2:
                    values = values[:, :, 1]
                else:
                    # Multi-class: use mean absolute across classes
                    values = np.mean(np.abs(values), axis=2)
            self._shap_values = values
        assert self._shap_values is not None  # set above
        return self._shap_values

    def explain_global(self, *, max_display: int = 20) -> dict[str, Any]:
        """Compute global SHAP values -- feature importance across all samples.

        Parameters
        ----------
        max_display:
            Maximum number of features to include in the importance
            ranking.  Defaults to 20.

        Returns
        -------
        dict with:
            - ``shap_values``: numpy array of SHAP values (n_samples x n_features)
            - ``feature_importance``: dict mapping feature name to mean |SHAP|
            - ``feature_names``: list of feature names
        """
        shap_values = self._compute_shap_values()

        # Mean absolute SHAP value per feature
        mean_abs_shap = np.mean(np.abs(shap_values), axis=0)

        # Build importance dict sorted by value descending, limited to max_display
        indices = np.argsort(mean_abs_shap)[::-1][:max_display]
        feature_importance: dict[str, float] = {}
        for idx in indices:
            name = (
                self._feature_names[idx]
                if idx < len(self._feature_names)
                else f"feature_{idx}"
            )
            feature_importance[name] = float(mean_abs_shap[idx])

        return {
            "shap_values": shap_values,
            "feature_importance": feature_importance,
            "feature_names": self._feature_names,
        }

    def explain_local(self, X: pl.DataFrame, *, index: int = 0) -> dict[str, Any]:
        """Compute per-prediction SHAP values.

        Parameters
        ----------
        X:
            Data to explain as a polars DataFrame.
        index:
            Which row (prediction) to explain.

        Returns
        -------
        dict with:
            - ``shap_values``: SHAP values for the selected prediction
              (1-D array of length n_features)
            - ``base_value``: expected model output (scalar)
            - ``feature_values``: actual feature values for the selected row
              (1-D array)
            - ``feature_names``: list of feature names
        """
        if not isinstance(X, pl.DataFrame):
            raise TypeError("X must be a polars DataFrame")

        X_numpy = _polars_to_numpy(X)
        if index < 0 or index >= X_numpy.shape[0]:
            raise IndexError(
                f"index {index} out of range for data with {X_numpy.shape[0]} rows"
            )

        explanation = self._explainer(X_numpy)
        values = explanation.values

        # Handle multi-output (binary/multiclass)
        if values.ndim == 3:
            if values.shape[2] == 2:
                values = values[:, :, 1]
            else:
                values = np.mean(np.abs(values), axis=2)

        base_values = explanation.base_values
        if isinstance(base_values, np.ndarray):
            if base_values.ndim == 2:
                # Multi-class base values: pick positive class or mean
                if base_values.shape[1] == 2:
                    base_value = float(base_values[index, 1])
                else:
                    base_value = float(np.mean(base_values[index]))
            elif base_values.ndim == 1:
                base_value = float(base_values[index])
            else:
                base_value = float(base_values)
        else:
            base_value = float(base_values)

        return {
            "shap_values": values[index],
            "base_value": base_value,
            "feature_values": X_numpy[index],
            "feature_names": self._feature_names,
        }

    def explain_dependence(
        self, feature: str, *, interaction_feature: str | None = None
    ) -> dict[str, Any]:
        """Compute SHAP dependence for a specific feature.

        Shows how a feature's value affects the model's prediction,
        optionally colored by an interaction feature.

        Parameters
        ----------
        feature:
            Name of the feature to analyze.
        interaction_feature:
            Optional second feature for interaction coloring.

        Returns
        -------
        dict with:
            - ``feature_values``: values of the feature (1-D array)
            - ``shap_values``: SHAP values for that feature (1-D array)
            - ``interaction_values``: values of the interaction feature
              (1-D array, or ``None`` if not specified)
        """
        if feature not in self._feature_names:
            raise ValueError(
                f"Feature '{feature}' not found. "
                f"Available features: {self._feature_names}"
            )

        shap_values = self._compute_shap_values()
        feat_idx = self._feature_names.index(feature)

        result: dict[str, Any] = {
            "feature_values": self._X_numpy[:, feat_idx],
            "shap_values": shap_values[:, feat_idx],
            "interaction_values": None,
        }

        if interaction_feature is not None:
            if interaction_feature not in self._feature_names:
                raise ValueError(
                    f"Interaction feature '{interaction_feature}' not found. "
                    f"Available features: {self._feature_names}"
                )
            interact_idx = self._feature_names.index(interaction_feature)
            result["interaction_values"] = self._X_numpy[:, interact_idx]

        return result

    def to_plotly(self, plot_type: str = "summary", **kwargs: Any) -> Any:
        """Generate a plotly Figure for SHAP visualization.

        Parameters
        ----------
        plot_type:
            One of ``"summary"`` (bar chart of mean |SHAP|),
            ``"beeswarm"`` (dot plot showing value distribution),
            or ``"dependence"`` (dependence plot for a single feature,
            requires ``feature`` kwarg).
        **kwargs:
            Additional keyword arguments:

            - ``max_display`` (int): For summary/beeswarm, max features
              to show.  Default 20.
            - ``feature`` (str): For dependence plot, the feature name.
            - ``interaction_feature`` (str): For dependence plot, optional
              interaction feature.

        Returns
        -------
        plotly.graph_objects.Figure
        """
        import plotly.graph_objects as go

        max_display = kwargs.get("max_display", 20)

        if plot_type == "summary":
            return self._plot_summary(max_display=max_display)
        elif plot_type == "beeswarm":
            return self._plot_beeswarm(max_display=max_display)
        elif plot_type == "dependence":
            feature = kwargs.get("feature")
            if feature is None:
                raise ValueError(
                    "plot_type='dependence' requires a 'feature' keyword argument"
                )
            interaction_feature = kwargs.get("interaction_feature")
            return self._plot_dependence(
                feature=feature, interaction_feature=interaction_feature
            )
        else:
            raise ValueError(
                f"Unknown plot_type '{plot_type}'. "
                f"Choose from: 'summary', 'beeswarm', 'dependence'"
            )

    def _plot_summary(self, *, max_display: int = 20) -> Any:
        """Bar chart of mean |SHAP| values (global importance)."""
        import plotly.graph_objects as go

        global_result = self.explain_global(max_display=max_display)
        importance = global_result["feature_importance"]

        # Sort ascending for horizontal bar (top feature at top visually)
        sorted_items = sorted(importance.items(), key=lambda x: x[1])
        names = [item[0] for item in sorted_items]
        values = [item[1] for item in sorted_items]

        fig = go.Figure(
            data=go.Bar(
                x=values,
                y=names,
                orientation="h",
                marker_color="steelblue",
            )
        )
        fig.update_layout(
            title=f"SHAP Feature Importance (Top {len(names)})",
            xaxis_title="Mean |SHAP Value|",
            yaxis_title="Feature",
        )
        return fig

    def _plot_beeswarm(self, *, max_display: int = 20) -> Any:
        """Dot plot showing SHAP value distribution per feature."""
        import plotly.graph_objects as go

        shap_values = self._compute_shap_values()
        mean_abs = np.mean(np.abs(shap_values), axis=0)

        # Select top features by importance
        top_indices = np.argsort(mean_abs)[::-1][:max_display]
        # Reverse for display (most important at top)
        top_indices = top_indices[::-1]

        fig = go.Figure()

        for rank, feat_idx in enumerate(top_indices):
            feat_shap = shap_values[:, feat_idx]
            feat_vals = self._X_numpy[:, feat_idx]
            feat_name = (
                self._feature_names[feat_idx]
                if feat_idx < len(self._feature_names)
                else f"feature_{feat_idx}"
            )

            # Normalize feature values to [0, 1] for color mapping
            fmin, fmax = float(np.nanmin(feat_vals)), float(np.nanmax(feat_vals))
            if fmax > fmin:
                normed = (feat_vals - fmin) / (fmax - fmin)
            else:
                normed = np.full_like(feat_vals, 0.5)

            # Map to color: low=blue, high=red
            colors = [
                f"rgb({int(v * 255)}, {int((1 - abs(2 * v - 1)) * 100)}, {int((1 - v) * 255)})"
                for v in normed
            ]

            # Add jitter to y for readability
            jitter = np.random.default_rng(42).uniform(-0.2, 0.2, size=len(feat_shap))

            fig.add_trace(
                go.Scatter(
                    x=feat_shap,
                    y=np.full(len(feat_shap), rank) + jitter,
                    mode="markers",
                    marker=dict(
                        size=4,
                        color=colors,
                        opacity=0.6,
                    ),
                    name=feat_name,
                    showlegend=False,
                    hovertemplate=(
                        f"{feat_name}<br>" "SHAP: %{x:.4f}<br>" "<extra></extra>"
                    ),
                )
            )

        tick_labels = [
            (
                self._feature_names[idx]
                if idx < len(self._feature_names)
                else f"feature_{idx}"
            )
            for idx in top_indices
        ]
        fig.update_layout(
            title=f"SHAP Beeswarm Plot (Top {len(top_indices)})",
            xaxis_title="SHAP Value",
            yaxis=dict(
                tickmode="array",
                tickvals=list(range(len(top_indices))),
                ticktext=tick_labels,
            ),
        )
        return fig

    def _plot_dependence(
        self, *, feature: str, interaction_feature: str | None = None
    ) -> Any:
        """Scatter plot of feature value vs SHAP value."""
        import plotly.graph_objects as go

        dep = self.explain_dependence(feature, interaction_feature=interaction_feature)

        marker_kwargs: dict[str, Any] = {
            "size": 5,
            "opacity": 0.7,
        }

        if dep["interaction_values"] is not None:
            marker_kwargs["color"] = dep["interaction_values"]
            marker_kwargs["colorscale"] = "RdBu"
            marker_kwargs["colorbar"] = dict(title=interaction_feature)

        fig = go.Figure(
            data=go.Scatter(
                x=dep["feature_values"],
                y=dep["shap_values"],
                mode="markers",
                marker=marker_kwargs,
                hovertemplate=(
                    f"{feature}: " + "%{x:.4f}<br>"
                    "SHAP: %{y:.4f}<br>"
                    "<extra></extra>"
                ),
            )
        )

        title = f"SHAP Dependence: {feature}"
        if interaction_feature:
            title += f" (colored by {interaction_feature})"

        fig.update_layout(
            title=title,
            xaxis_title=feature,
            yaxis_title=f"SHAP Value for {feature}",
        )
        return fig

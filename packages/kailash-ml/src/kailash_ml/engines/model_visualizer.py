# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""ModelVisualizer engine -- ML model visualization with plotly.

Confusion matrix, ROC curve, precision-recall curve, feature importance,
learning curves, residual plots, calibration curves, metric comparison,
and training history.  All methods return plotly ``Figure`` objects for
interactive display.

PyCaret equivalent: ``plot_model()``.
"""
from __future__ import annotations

import logging
from typing import Any

import numpy as np

import plotly.express as px

from kailash_ml._decorators import experimental

logger = logging.getLogger(__name__)

__all__ = [
    "ModelVisualizer",
]


def _ensure_plotly() -> None:
    """Check that plotly is installed; raise helpful error if not."""
    try:
        import plotly  # noqa: F401
    except ImportError as exc:
        raise ImportError(
            "plotly is required for model visualization. "
            "Install it with: pip install plotly"
        ) from exc


def _to_numpy(arr: Any) -> np.ndarray:
    """Convert polars Series, lists, or array-likes to numpy."""
    if hasattr(arr, "to_numpy"):
        return arr.to_numpy()
    return np.asarray(arr)


@experimental
class ModelVisualizer:
    """[P2: Experimental] ML model visualization engine.

    Generates interactive plotly visualizations for model diagnostics:
    confusion matrix, ROC curve, precision-recall curve, feature importance,
    learning curves, residual plots, calibration curves, metric comparison,
    and training history.

    All methods return ``plotly.graph_objects.Figure`` instances.
    API may change in future versions.
    """

    def __init__(self) -> None:
        _ensure_plotly()

    def confusion_matrix(
        self,
        y_true: Any,
        y_pred: Any,
        labels: list[str] | None = None,
    ) -> Any:
        """Plot confusion matrix heatmap.

        Parameters
        ----------
        y_true:
            Ground truth labels.
        y_pred:
            Predicted labels.
        labels:
            Display labels for each class.  When ``None`` the unique sorted
            values from *y_true* are used.

        Returns
        -------
        plotly.graph_objects.Figure
        """
        from sklearn.metrics import confusion_matrix as sk_confusion_matrix

        import plotly.graph_objects as go

        y_true_np = _to_numpy(y_true)
        y_pred_np = _to_numpy(y_pred)

        cm = sk_confusion_matrix(y_true_np, y_pred_np)
        if labels is None:
            labels = [str(v) for v in sorted(set(y_true_np))]

        text = [[str(val) for val in row] for row in cm]

        fig = go.Figure(
            data=go.Heatmap(
                z=cm,
                x=labels,
                y=labels,
                text=text,
                texttemplate="%{text}",
                colorscale="Blues",
            )
        )
        fig.update_layout(
            title="Confusion Matrix",
            xaxis_title="Predicted",
            yaxis_title="Actual",
        )
        return fig

    def roc_curve(
        self,
        y_true: Any,
        y_scores: Any,
        pos_label: int | str = 1,
    ) -> Any:
        """Plot ROC curve with AUC.

        Supports binary classification.  For multiclass, pass the
        probability column for the positive class.

        Parameters
        ----------
        y_true:
            Ground truth binary labels.
        y_scores:
            Predicted scores or probabilities for the positive class.
        pos_label:
            The label of the positive class.

        Returns
        -------
        plotly.graph_objects.Figure
        """
        from sklearn.metrics import auc as sk_auc
        from sklearn.metrics import roc_curve as sk_roc_curve

        import plotly.graph_objects as go

        y_true_np = _to_numpy(y_true)
        y_scores_np = _to_numpy(y_scores)

        fpr, tpr, _ = sk_roc_curve(y_true_np, y_scores_np, pos_label=pos_label)
        roc_auc = sk_auc(fpr, tpr)

        fig = go.Figure()
        fig.add_trace(
            go.Scatter(
                x=fpr,
                y=tpr,
                mode="lines",
                name=f"ROC (AUC = {roc_auc:.3f})",
            )
        )
        fig.add_trace(
            go.Scatter(
                x=[0, 1],
                y=[0, 1],
                mode="lines",
                line=dict(dash="dash", color="gray"),
                name="Random",
                showlegend=True,
            )
        )
        fig.update_layout(
            title=f"ROC Curve (AUC = {roc_auc:.3f})",
            xaxis_title="False Positive Rate",
            yaxis_title="True Positive Rate",
        )
        return fig

    def precision_recall_curve(
        self,
        y_true: Any,
        y_scores: Any,
        pos_label: int | str = 1,
    ) -> Any:
        """Plot precision-recall curve with average precision (AP).

        Parameters
        ----------
        y_true:
            Ground truth binary labels.
        y_scores:
            Predicted scores or probabilities for the positive class.
        pos_label:
            The label of the positive class.

        Returns
        -------
        plotly.graph_objects.Figure
        """
        from sklearn.metrics import average_precision_score
        from sklearn.metrics import precision_recall_curve as sk_pr_curve

        import plotly.graph_objects as go

        y_true_np = _to_numpy(y_true)
        y_scores_np = _to_numpy(y_scores)

        precision, recall, _ = sk_pr_curve(y_true_np, y_scores_np, pos_label=pos_label)
        ap = average_precision_score(y_true_np, y_scores_np)

        fig = go.Figure()
        fig.add_trace(
            go.Scatter(
                x=recall,
                y=precision,
                mode="lines",
                name=f"PR (AP = {ap:.3f})",
            )
        )
        fig.update_layout(
            title=f"Precision-Recall Curve (AP = {ap:.3f})",
            xaxis_title="Recall",
            yaxis_title="Precision",
        )
        return fig

    def feature_importance(
        self,
        model: Any,
        feature_names: list[str],
        top_n: int = 20,
        *,
        X: Any | None = None,
        y: Any | None = None,
    ) -> Any:
        """Plot feature importance.

        For tree-based models (RandomForest, GradientBoosting, XGBoost, etc.)
        uses the built-in ``feature_importances_`` attribute.  For other
        models falls back to ``sklearn.inspection.permutation_importance``
        (requires *X* and *y*).

        Parameters
        ----------
        model:
            A fitted scikit-learn estimator.
        feature_names:
            Feature names matching the columns used during training.
        top_n:
            Number of top features to display.
        X:
            Validation data for permutation importance fallback.
        y:
            Validation labels for permutation importance fallback.

        Returns
        -------
        plotly.graph_objects.Figure
        """
        import plotly.graph_objects as go

        if hasattr(model, "feature_importances_"):
            importances = np.asarray(model.feature_importances_)
        elif hasattr(model, "coef_"):
            importances = np.abs(np.asarray(model.coef_).ravel())
        elif X is not None and y is not None:
            from sklearn.inspection import permutation_importance

            result = permutation_importance(
                model, _to_numpy(X), _to_numpy(y), n_repeats=10, random_state=42
            )
            importances = result.importances_mean
        else:
            raise ValueError(
                "Model has no feature_importances_ or coef_ attribute. "
                "Provide X and y for permutation importance fallback."
            )

        if len(importances) != len(feature_names):
            raise ValueError(
                f"feature_names length ({len(feature_names)}) does not match "
                f"importance length ({len(importances)})"
            )

        # Sort and take top_n
        indices = np.argsort(importances)[::-1][:top_n]
        sorted_names = [feature_names[i] for i in indices]
        sorted_importances = importances[indices]

        # Reverse for horizontal bar (top feature at top)
        sorted_names = sorted_names[::-1]
        sorted_importances = sorted_importances[::-1]

        fig = go.Figure(
            data=go.Bar(
                x=sorted_importances,
                y=sorted_names,
                orientation="h",
            )
        )
        fig.update_layout(
            title=f"Feature Importance (Top {min(top_n, len(feature_names))})",
            xaxis_title="Importance",
            yaxis_title="Feature",
        )
        return fig

    def learning_curve(
        self,
        model: Any,
        X: Any,
        y: Any,
        cv: int = 5,
        train_sizes: list[float] | None = None,
    ) -> Any:
        """Plot learning curve (training vs validation score).

        Parameters
        ----------
        model:
            A scikit-learn estimator (will be cloned internally).
        X:
            Training features.
        y:
            Training labels.
        cv:
            Number of cross-validation folds.
        train_sizes:
            Relative training set sizes.  Defaults to
            ``[0.1, 0.25, 0.5, 0.75, 1.0]``.

        Returns
        -------
        plotly.graph_objects.Figure
        """
        from sklearn.model_selection import learning_curve as sk_learning_curve

        import plotly.graph_objects as go

        if train_sizes is None:
            train_sizes = [0.1, 0.25, 0.5, 0.75, 1.0]

        X_np = _to_numpy(X)
        y_np = _to_numpy(y)

        train_sizes_abs, train_scores, val_scores = sk_learning_curve(
            model, X_np, y_np, cv=cv, train_sizes=train_sizes, n_jobs=-1
        )

        train_mean = train_scores.mean(axis=1)
        train_std = train_scores.std(axis=1)
        val_mean = val_scores.mean(axis=1)
        val_std = val_scores.std(axis=1)

        fig = go.Figure()
        # Training score
        fig.add_trace(
            go.Scatter(
                x=train_sizes_abs,
                y=train_mean,
                mode="lines+markers",
                name="Training Score",
                line=dict(color="blue"),
            )
        )
        fig.add_trace(
            go.Scatter(
                x=np.concatenate([train_sizes_abs, train_sizes_abs[::-1]]),
                y=np.concatenate(
                    [train_mean + train_std, (train_mean - train_std)[::-1]]
                ),
                fill="toself",
                fillcolor="rgba(0,0,255,0.1)",
                line=dict(color="rgba(0,0,0,0)"),
                showlegend=False,
            )
        )
        # Validation score
        fig.add_trace(
            go.Scatter(
                x=train_sizes_abs,
                y=val_mean,
                mode="lines+markers",
                name="Validation Score",
                line=dict(color="orange"),
            )
        )
        fig.add_trace(
            go.Scatter(
                x=np.concatenate([train_sizes_abs, train_sizes_abs[::-1]]),
                y=np.concatenate([val_mean + val_std, (val_mean - val_std)[::-1]]),
                fill="toself",
                fillcolor="rgba(255,165,0,0.1)",
                line=dict(color="rgba(0,0,0,0)"),
                showlegend=False,
            )
        )
        fig.update_layout(
            title="Learning Curve",
            xaxis_title="Training Set Size",
            yaxis_title="Score",
        )
        return fig

    def residuals(
        self,
        y_true: Any,
        y_pred: Any,
    ) -> Any:
        """Plot residuals for regression models.

        Creates a two-panel figure: predicted vs actual scatter (left) and
        residual distribution histogram (right).

        Parameters
        ----------
        y_true:
            Ground truth values.
        y_pred:
            Predicted values.

        Returns
        -------
        plotly.graph_objects.Figure
        """
        from plotly.subplots import make_subplots

        import plotly.graph_objects as go

        y_true_np = _to_numpy(y_true).ravel()
        y_pred_np = _to_numpy(y_pred).ravel()
        residual = y_true_np - y_pred_np

        fig = make_subplots(
            rows=1,
            cols=2,
            subplot_titles=("Predicted vs Actual", "Residual Distribution"),
        )

        # Predicted vs Actual
        fig.add_trace(
            go.Scatter(
                x=y_pred_np,
                y=y_true_np,
                mode="markers",
                name="Data",
                marker=dict(opacity=0.6),
            ),
            row=1,
            col=1,
        )
        all_vals = np.concatenate([y_true_np, y_pred_np])
        mn, mx = float(all_vals.min()), float(all_vals.max())
        fig.add_trace(
            go.Scatter(
                x=[mn, mx],
                y=[mn, mx],
                mode="lines",
                line=dict(dash="dash", color="red"),
                name="Perfect",
                showlegend=True,
            ),
            row=1,
            col=1,
        )

        # Residual distribution
        fig.add_trace(
            go.Histogram(x=residual, name="Residuals"),
            row=1,
            col=2,
        )

        fig.update_xaxes(title_text="Predicted", row=1, col=1)
        fig.update_yaxes(title_text="Actual", row=1, col=1)
        fig.update_xaxes(title_text="Residual", row=1, col=2)
        fig.update_yaxes(title_text="Count", row=1, col=2)
        fig.update_layout(title="Residual Analysis")
        return fig

    def calibration_curve(
        self,
        y_true: Any,
        y_proba: Any,
        n_bins: int = 10,
    ) -> Any:
        """Plot calibration curve (reliability diagram).

        Parameters
        ----------
        y_true:
            Ground truth binary labels.
        y_proba:
            Predicted probabilities for the positive class.
        n_bins:
            Number of bins for calibration.

        Returns
        -------
        plotly.graph_objects.Figure
        """
        from sklearn.calibration import calibration_curve as sk_calibration_curve

        import plotly.graph_objects as go

        y_true_np = _to_numpy(y_true)
        y_proba_np = _to_numpy(y_proba)

        prob_true, prob_pred = sk_calibration_curve(
            y_true_np, y_proba_np, n_bins=n_bins
        )

        fig = go.Figure()
        fig.add_trace(
            go.Scatter(
                x=prob_pred,
                y=prob_true,
                mode="lines+markers",
                name="Model",
            )
        )
        fig.add_trace(
            go.Scatter(
                x=[0, 1],
                y=[0, 1],
                mode="lines",
                line=dict(dash="dash", color="gray"),
                name="Perfectly Calibrated",
            )
        )
        fig.update_layout(
            title="Calibration Curve",
            xaxis_title="Mean Predicted Probability",
            yaxis_title="Fraction of Positives",
        )
        return fig

    def metric_comparison(
        self,
        results: dict[str, dict[str, float]],
    ) -> Any:
        """Plot bar chart comparing metrics across models.

        Parameters
        ----------
        results:
            Mapping of model name to metric dict.  Example::

                {
                    "LogisticRegression": {"accuracy": 0.95, "f1": 0.93},
                    "RandomForest": {"accuracy": 0.97, "f1": 0.96},
                }

        Returns
        -------
        plotly.graph_objects.Figure
        """
        import plotly.graph_objects as go

        if not results:
            raise ValueError("results must contain at least one model")

        model_names = list(results.keys())
        metric_names = list(next(iter(results.values())).keys())

        fig = go.Figure()
        for metric in metric_names:
            values = [results[m].get(metric, 0.0) for m in model_names]
            fig.add_trace(go.Bar(name=metric, x=model_names, y=values))

        fig.update_layout(
            title="Model Comparison",
            xaxis_title="Model",
            yaxis_title="Score",
            barmode="group",
        )
        return fig

    def training_history(
        self,
        metrics: dict[str, list[float]],
        x_label: str = "Epoch",
        y_label: str = "Value",
    ) -> Any:
        """Plot training metrics over time (loss curves, etc.).

        Parameters
        ----------
        metrics:
            Mapping of metric name to list of values per epoch/step.
            Example::

                {"train_loss": [0.9, 0.5, 0.3], "val_loss": [1.0, 0.6, 0.4]}
        x_label:
            Label for the x-axis.
        y_label:
            Label for the y-axis.

        Returns
        -------
        plotly.graph_objects.Figure
        """
        import plotly.graph_objects as go

        if not metrics:
            raise ValueError("metrics must contain at least one series")

        fig = go.Figure()
        for name, values in metrics.items():
            fig.add_trace(
                go.Scatter(
                    x=list(range(1, len(values) + 1)),
                    y=values,
                    mode="lines+markers",
                    name=name,
                )
            )
        fig.update_layout(
            title="Training History",
            xaxis_title=x_label,
            yaxis_title=y_label,
        )
        return fig

    # ------------------------------------------------------------------
    # EDA chart methods (#314)
    # ------------------------------------------------------------------

    def histogram(
        self,
        data: Any,
        column: str,
        *,
        bins: int = 30,
        title: str | None = None,
    ) -> Any:
        """Create a histogram for a single column.

        Unlike other ModelVisualizer methods that accept raw arrays,
        EDA methods accept a polars DataFrame with column names for
        richer context.

        Args:
            data: A polars DataFrame.
            column: Column name to plot.
            bins: Number of bins.
            title: Optional chart title.

        Returns:
            A plotly Figure.
        """
        import polars as pl

        import plotly.graph_objects as go

        if not isinstance(data, pl.DataFrame):
            msg = "data must be a polars DataFrame"
            raise TypeError(msg)
        if column not in data.columns:
            msg = f"Column '{column}' not found in DataFrame"
            raise ValueError(msg)

        series = data[column].drop_nulls().to_list()
        fig = go.Figure(data=[go.Histogram(x=series, nbinsx=bins)])
        fig.update_layout(
            title=title or f"Distribution of {column}",
            xaxis_title=column,
            yaxis_title="Count",
        )
        return fig

    def scatter(
        self,
        data: Any,
        x: str,
        y: str,
        *,
        color: str | None = None,
        title: str | None = None,
    ) -> Any:
        """Create a scatter plot of two columns.

        Args:
            data: A polars DataFrame.
            x: Column name for x-axis.
            y: Column name for y-axis.
            color: Optional column name for color grouping.
            title: Optional chart title.

        Returns:
            A plotly Figure.
        """
        import polars as pl

        if not isinstance(data, pl.DataFrame):
            msg = "data must be a polars DataFrame"
            raise TypeError(msg)
        for col_name in [x, y] + ([color] if color else []):
            if col_name not in data.columns:
                msg = f"Column '{col_name}' not found in DataFrame"
                raise ValueError(msg)

        pdf = data.select([x, y] + ([color] if color else [])).drop_nulls().to_pandas()
        fig = px.scatter(pdf, x=x, y=y, color=color)
        fig.update_layout(title=title or f"{y} vs {x}")
        return fig

    def box_plot(
        self,
        data: Any,
        column: str,
        *,
        group_by: str | None = None,
        title: str | None = None,
    ) -> Any:
        """Create a box plot for a column, optionally grouped.

        Args:
            data: A polars DataFrame.
            column: Column name for values.
            group_by: Optional column name for grouping.
            title: Optional chart title.

        Returns:
            A plotly Figure.
        """
        import polars as pl

        if not isinstance(data, pl.DataFrame):
            msg = "data must be a polars DataFrame"
            raise TypeError(msg)
        for col_name in [column] + ([group_by] if group_by else []):
            if col_name not in data.columns:
                msg = f"Column '{col_name}' not found in DataFrame"
                raise ValueError(msg)

        pdf = (
            data.select([column] + ([group_by] if group_by else []))
            .drop_nulls()
            .to_pandas()
        )
        if group_by:
            fig = px.box(pdf, x=group_by, y=column)
        else:
            fig = px.box(pdf, y=column)
        fig.update_layout(title=title or f"Distribution of {column}")
        return fig

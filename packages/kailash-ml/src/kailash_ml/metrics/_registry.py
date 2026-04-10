# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Registry-based metric computation wrapping sklearn metrics.

Every metric is registered as a callable with a standard signature. The
registry is the single source of truth -- ``compute_metrics_by_name`` in
``engines._shared`` delegates here.

Metrics accept **polars Series** or **numpy arrays**. Polars inputs are
converted to numpy at the boundary so callers can stay polars-native.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Union

import numpy as np
import polars as pl

logger = logging.getLogger(__name__)

__all__ = [
    "METRIC_REGISTRY",
    "register_metric",
    "compute_metric",
    "compute_metrics",
    "list_metrics",
    # Standalone metric functions
    "accuracy",
    "f1",
    "precision",
    "recall",
    "auc",
    "mse",
    "rmse",
    "mae",
    "r2",
    # Probability metrics (TASK-ML-02)
    "log_loss",
    "brier_score_loss",
    "average_precision",
]

ArrayLike = Union[np.ndarray, pl.Series]

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _to_numpy(arr: ArrayLike) -> np.ndarray:
    """Convert polars Series to numpy; pass numpy through unchanged."""
    if isinstance(arr, pl.Series):
        return arr.to_numpy()
    return np.asarray(arr)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

# Each entry maps name -> dict with:
#   "fn": Callable(y_true, y_pred, **kwargs) -> float
#   "requires_prob": bool  -- True if the metric needs y_prob instead of y_pred
METRIC_REGISTRY: dict[str, dict[str, Any]] = {}


def register_metric(
    name: str,
    fn: Callable[..., float],
    *,
    requires_prob: bool = False,
) -> None:
    """Register a metric function in the global registry.

    Parameters
    ----------
    name:
        Metric name (e.g. ``"accuracy"``, ``"log_loss"``).
    fn:
        Callable with signature ``(y_true, y_pred, **kwargs) -> float``.
        For probability metrics, signature is ``(y_true, y_prob, **kwargs) -> float``.
    requires_prob:
        If True, the metric requires probability predictions (``y_prob``).
    """
    METRIC_REGISTRY[name] = {"fn": fn, "requires_prob": requires_prob}


def list_metrics() -> list[str]:
    """Return sorted list of all registered metric names."""
    return sorted(METRIC_REGISTRY.keys())


# ---------------------------------------------------------------------------
# Core compute functions
# ---------------------------------------------------------------------------


def compute_metric(
    name: str,
    y_true: ArrayLike,
    y_pred: ArrayLike,
    *,
    y_prob: ArrayLike | None = None,
    model: Any = None,
    X_test: ArrayLike | None = None,
) -> float:
    """Compute a single metric by name.

    Parameters
    ----------
    name:
        Metric name (must be in ``METRIC_REGISTRY``).
    y_true:
        Ground truth labels/values. Accepts polars Series or numpy array.
    y_pred:
        Predicted labels/values. Accepts polars Series or numpy array.
    y_prob:
        Probability predictions (required for probability metrics).
        Accepts polars Series or numpy array.
    model:
        Fitted model (used by ``auc`` to call ``predict_proba`` when
        ``y_prob`` is not provided).
    X_test:
        Test features (used by ``auc`` with ``predict_proba``).

    Returns
    -------
    float
        Metric value.

    Raises
    ------
    ValueError
        If metric name is unknown or if a probability metric is called
        without ``y_prob``.
    """
    if name not in METRIC_REGISTRY:
        raise ValueError(f"Unknown metric: {name!r}. Available: {list_metrics()}")

    entry = METRIC_REGISTRY[name]
    yt = _to_numpy(y_true)
    yp = _to_numpy(y_pred)

    if entry["requires_prob"]:
        if y_prob is None:
            raise ValueError(
                f"Metric {name!r} requires probability predictions (y_prob). "
                f"Pass y_prob=... when computing this metric."
            )
        ypr = _to_numpy(y_prob)
        return float(entry["fn"](yt, ypr))

    # Non-probability metrics -- pass model and X_test for auc compatibility
    kwargs: dict[str, Any] = {}
    if model is not None:
        kwargs["model"] = model
    if X_test is not None:
        kwargs["X_test"] = (
            _to_numpy(X_test) if isinstance(X_test, pl.Series) else X_test
        )
    if y_prob is not None:
        kwargs["y_prob"] = _to_numpy(y_prob)

    return float(entry["fn"](yt, yp, **kwargs))


def compute_metrics(
    y_true: ArrayLike,
    y_pred: ArrayLike,
    metric_names: list[str],
    *,
    y_prob: ArrayLike | None = None,
    model: Any = None,
    X_test: ArrayLike | None = None,
) -> dict[str, float]:
    """Compute multiple metrics by name.

    Parameters
    ----------
    y_true:
        Ground truth labels/values.
    y_pred:
        Predicted labels/values.
    metric_names:
        List of metric names to compute.
    y_prob:
        Probability predictions (for probability metrics).
    model:
        Fitted model (for ``auc``).
    X_test:
        Test features (for ``auc``).

    Returns
    -------
    dict mapping metric name to float value. Metrics that fail are logged
    and skipped.
    """
    results: dict[str, float] = {}
    for name in metric_names:
        if name not in METRIC_REGISTRY:
            logger.warning("Unknown or unsupported metric: %s", name)
            continue
        entry = METRIC_REGISTRY[name]
        if entry["requires_prob"] and y_prob is None:
            logger.warning(
                "Metric %s requires y_prob but none provided, skipping.", name
            )
            continue
        try:
            results[name] = compute_metric(
                name,
                y_true,
                y_pred,
                y_prob=y_prob,
                model=model,
                X_test=X_test,
            )
        except Exception:
            logger.debug("Metric %s computation failed, skipping.", name)
    return results


# ---------------------------------------------------------------------------
# Classification metrics
# ---------------------------------------------------------------------------


def _accuracy_fn(y_true: np.ndarray, y_pred: np.ndarray, **_: Any) -> float:
    from sklearn.metrics import accuracy_score

    return float(accuracy_score(y_true, y_pred))


def _f1_fn(y_true: np.ndarray, y_pred: np.ndarray, **_: Any) -> float:
    from sklearn.metrics import f1_score

    return float(f1_score(y_true, y_pred, average="weighted", zero_division=0))


def _precision_fn(y_true: np.ndarray, y_pred: np.ndarray, **_: Any) -> float:
    from sklearn.metrics import precision_score

    return float(precision_score(y_true, y_pred, average="weighted", zero_division=0))


def _recall_fn(y_true: np.ndarray, y_pred: np.ndarray, **_: Any) -> float:
    from sklearn.metrics import recall_score

    return float(recall_score(y_true, y_pred, average="weighted", zero_division=0))


def _auc_fn(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    *,
    model: Any = None,
    X_test: np.ndarray | None = None,
    y_prob: np.ndarray | None = None,
    **_: Any,
) -> float:
    from sklearn.metrics import roc_auc_score

    # Prefer explicit y_prob, then try model.predict_proba
    proba = y_prob
    if proba is None and model is not None and X_test is not None:
        if hasattr(model, "predict_proba"):
            proba = model.predict_proba(X_test)

    if proba is None:
        raise ValueError(
            "AUC requires probability predictions. Provide y_prob, or "
            "model + X_test where model has predict_proba."
        )

    if proba.ndim == 2 and proba.shape[1] == 2:
        return float(roc_auc_score(y_true, proba[:, 1]))
    elif proba.ndim == 2:
        return float(
            roc_auc_score(y_true, proba, multi_class="ovr", average="weighted")
        )
    else:
        return float(roc_auc_score(y_true, proba))


# ---------------------------------------------------------------------------
# Regression metrics
# ---------------------------------------------------------------------------


def _mse_fn(y_true: np.ndarray, y_pred: np.ndarray, **_: Any) -> float:
    from sklearn.metrics import mean_squared_error

    return float(mean_squared_error(y_true, y_pred))


def _rmse_fn(y_true: np.ndarray, y_pred: np.ndarray, **_: Any) -> float:
    from sklearn.metrics import mean_squared_error

    return float(np.sqrt(mean_squared_error(y_true, y_pred)))


def _mae_fn(y_true: np.ndarray, y_pred: np.ndarray, **_: Any) -> float:
    from sklearn.metrics import mean_absolute_error

    return float(mean_absolute_error(y_true, y_pred))


def _r2_fn(y_true: np.ndarray, y_pred: np.ndarray, **_: Any) -> float:
    from sklearn.metrics import r2_score

    return float(r2_score(y_true, y_pred))


# ---------------------------------------------------------------------------
# Probability metrics (TASK-ML-02)
# ---------------------------------------------------------------------------


def _log_loss_fn(y_true: np.ndarray, y_prob: np.ndarray, **_: Any) -> float:
    from sklearn.metrics import log_loss as sk_log_loss

    return float(sk_log_loss(y_true, y_prob))


def _brier_score_loss_fn(y_true: np.ndarray, y_prob: np.ndarray, **_: Any) -> float:
    from sklearn.metrics import brier_score_loss as sk_brier

    # brier_score_loss expects 1D probability for the positive class
    if y_prob.ndim == 2 and y_prob.shape[1] == 2:
        y_prob = y_prob[:, 1]
    return float(sk_brier(y_true, y_prob))


def _average_precision_fn(y_true: np.ndarray, y_prob: np.ndarray, **_: Any) -> float:
    from sklearn.metrics import average_precision_score

    # average_precision_score expects 1D probability for the positive class
    if y_prob.ndim == 2 and y_prob.shape[1] == 2:
        y_prob = y_prob[:, 1]
    return float(average_precision_score(y_true, y_prob))


# ---------------------------------------------------------------------------
# Register all metrics at module load
# ---------------------------------------------------------------------------

register_metric("accuracy", _accuracy_fn)
register_metric("f1", _f1_fn)
register_metric("precision", _precision_fn)
register_metric("recall", _recall_fn)
register_metric("auc", _auc_fn)
register_metric("mse", _mse_fn)
register_metric("rmse", _rmse_fn)
register_metric("mae", _mae_fn)
register_metric("r2", _r2_fn)
register_metric("log_loss", _log_loss_fn, requires_prob=True)
register_metric("brier_score_loss", _brier_score_loss_fn, requires_prob=True)
register_metric("average_precision", _average_precision_fn, requires_prob=True)


# ---------------------------------------------------------------------------
# Standalone convenience functions (polars-native signatures)
# ---------------------------------------------------------------------------


def accuracy(y_true: ArrayLike, y_pred: ArrayLike) -> float:
    """Compute accuracy score."""
    return _accuracy_fn(_to_numpy(y_true), _to_numpy(y_pred))


def f1(y_true: ArrayLike, y_pred: ArrayLike) -> float:
    """Compute weighted F1 score."""
    return _f1_fn(_to_numpy(y_true), _to_numpy(y_pred))


def precision(y_true: ArrayLike, y_pred: ArrayLike) -> float:
    """Compute weighted precision."""
    return _precision_fn(_to_numpy(y_true), _to_numpy(y_pred))


def recall(y_true: ArrayLike, y_pred: ArrayLike) -> float:
    """Compute weighted recall."""
    return _recall_fn(_to_numpy(y_true), _to_numpy(y_pred))


def auc(
    y_true: ArrayLike,
    y_prob: ArrayLike,
    *,
    model: Any = None,
    X_test: ArrayLike | None = None,
) -> float:
    """Compute AUC-ROC score.

    Parameters
    ----------
    y_true:
        Ground truth labels.
    y_prob:
        Probability predictions (or predicted labels if using model+X_test).
    model:
        Fitted model with ``predict_proba`` (optional, used if y_prob is labels).
    X_test:
        Test features (optional, used with model).
    """
    return _auc_fn(
        _to_numpy(y_true),
        _to_numpy(y_prob),
        y_prob=_to_numpy(y_prob),
        model=model,
        X_test=_to_numpy(X_test) if isinstance(X_test, pl.Series) else X_test,
    )


def mse(y_true: ArrayLike, y_pred: ArrayLike) -> float:
    """Compute mean squared error."""
    return _mse_fn(_to_numpy(y_true), _to_numpy(y_pred))


def rmse(y_true: ArrayLike, y_pred: ArrayLike) -> float:
    """Compute root mean squared error."""
    return _rmse_fn(_to_numpy(y_true), _to_numpy(y_pred))


def mae(y_true: ArrayLike, y_pred: ArrayLike) -> float:
    """Compute mean absolute error."""
    return _mae_fn(_to_numpy(y_true), _to_numpy(y_pred))


def r2(y_true: ArrayLike, y_pred: ArrayLike) -> float:
    """Compute R-squared (coefficient of determination)."""
    return _r2_fn(_to_numpy(y_true), _to_numpy(y_pred))


def log_loss(y_true: ArrayLike, y_prob: ArrayLike) -> float:
    """Compute log loss (cross-entropy loss).

    Parameters
    ----------
    y_true:
        Ground truth labels (0/1 for binary, or class indices).
    y_prob:
        Predicted probabilities. For binary: 1D array of P(class=1) or
        2D array with columns [P(class=0), P(class=1)]. For multiclass:
        2D array with one column per class.
    """
    return _log_loss_fn(_to_numpy(y_true), _to_numpy(y_prob))


def brier_score_loss(y_true: ArrayLike, y_prob: ArrayLike) -> float:
    """Compute Brier score loss (binary classification only).

    Parameters
    ----------
    y_true:
        Ground truth binary labels (0/1).
    y_prob:
        Predicted probability of the positive class. If 2D with 2 columns,
        the second column (positive class) is used automatically.
    """
    return _brier_score_loss_fn(_to_numpy(y_true), _to_numpy(y_prob))


def average_precision(y_true: ArrayLike, y_prob: ArrayLike) -> float:
    """Compute average precision (area under precision-recall curve).

    Parameters
    ----------
    y_true:
        Ground truth binary labels (0/1).
    y_prob:
        Predicted probability of the positive class. If 2D with 2 columns,
        the second column (positive class) is used automatically.
    """
    return _average_precision_fn(_to_numpy(y_true), _to_numpy(y_prob))

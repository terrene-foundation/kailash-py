# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Shared constants and utilities used across multiple engines.

Centralizes duplicated definitions to prevent drift:
- ``NUMERIC_DTYPES``: polars numeric dtype tuple
- ``ALLOWED_MODEL_PREFIXES``: security allowlist for model class imports
- ``validate_model_class()``: model class validation
"""
from __future__ import annotations

import logging
from typing import Any

import numpy as np
import polars as pl

logger = logging.getLogger(__name__)

__all__ = [
    "NUMERIC_DTYPES",
    "ALLOWED_MODEL_PREFIXES",
    "validate_model_class",
    "compute_metrics_by_name",
]

# ---------------------------------------------------------------------------
# Numeric dtype tuple (used by data_explorer, feature_engineer, preprocessing)
# ---------------------------------------------------------------------------

NUMERIC_DTYPES = (
    pl.Float64,
    pl.Float32,
    pl.Int64,
    pl.Int32,
    pl.Int16,
    pl.Int8,
    pl.UInt64,
    pl.UInt32,
    pl.UInt16,
    pl.UInt8,
)

# ---------------------------------------------------------------------------
# Model class security allowlist (used by training_pipeline, ensemble)
# ---------------------------------------------------------------------------

ALLOWED_MODEL_PREFIXES = frozenset(
    {
        "sklearn.",
        "lightgbm.",
        "xgboost.",
        "catboost.",
        "kailash_ml.",
        "torch.",
        "lightning.",
    }
)


def validate_model_class(model_class: str) -> None:
    """Validate model_class against allowlist to prevent arbitrary code execution.

    Raises
    ------
    ValueError
        If model_class does not start with an allowed prefix.
    """
    if not any(model_class.startswith(prefix) for prefix in ALLOWED_MODEL_PREFIXES):
        raise ValueError(
            f"Model class '{model_class}' not in allowed prefixes: "
            f"{sorted(ALLOWED_MODEL_PREFIXES)}. "
            f"For custom models, use a prefix from the allowlist."
        )


# ---------------------------------------------------------------------------
# Shared metric computation (used by training_pipeline, ensemble)
# ---------------------------------------------------------------------------

_CLASSIFICATION_METRICS = ("accuracy", "f1", "precision", "recall", "auc")
_REGRESSION_METRICS = ("mse", "rmse", "mae", "r2")


def compute_metrics_by_name(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    metric_names: list[str],
    model: Any = None,
    X_test: np.ndarray | None = None,
    y_prob: np.ndarray | None = None,
) -> dict[str, float]:
    """Compute requested sklearn metrics by name.

    Delegates to :func:`kailash_ml.metrics.compute_metrics` -- the metrics
    registry is the single source of truth for all metric implementations.

    Parameters
    ----------
    y_true:
        Ground truth labels/values.
    y_pred:
        Predicted labels/values.
    metric_names:
        List of metric names to compute.
    model:
        Fitted model (needed for ``auc`` with ``predict_proba``).
    X_test:
        Test features (needed for ``auc`` with ``predict_proba``).
    y_prob:
        Probability predictions (needed for ``log_loss``,
        ``brier_score_loss``, ``average_precision``).

    Returns
    -------
    dict mapping metric name to float value.
    """
    from kailash_ml.metrics._registry import compute_metrics

    return compute_metrics(
        y_true,
        y_pred,
        metric_names,
        y_prob=y_prob,
        model=model,
        X_test=X_test,
    )

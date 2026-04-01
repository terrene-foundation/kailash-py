# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Shared constants and utilities used across multiple engines.

Centralizes duplicated definitions to prevent drift:
- ``NUMERIC_DTYPES``: polars numeric dtype tuple
- ``ALLOWED_MODEL_PREFIXES``: security allowlist for model class imports
- ``validate_model_class()``: model class validation
"""
from __future__ import annotations

import importlib
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
) -> dict[str, float]:
    """Compute requested sklearn metrics by name.

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

    Returns
    -------
    dict mapping metric name to float value.
    """
    from sklearn import metrics as skmetrics

    results: dict[str, float] = {}
    for name in metric_names:
        if name == "accuracy":
            results[name] = float(skmetrics.accuracy_score(y_true, y_pred))
        elif name == "f1":
            results[name] = float(
                skmetrics.f1_score(y_true, y_pred, average="weighted", zero_division=0)
            )
        elif name == "precision":
            results[name] = float(
                skmetrics.precision_score(
                    y_true, y_pred, average="weighted", zero_division=0
                )
            )
        elif name == "recall":
            results[name] = float(
                skmetrics.recall_score(
                    y_true, y_pred, average="weighted", zero_division=0
                )
            )
        elif name == "mse":
            results[name] = float(skmetrics.mean_squared_error(y_true, y_pred))
        elif name == "rmse":
            results[name] = float(np.sqrt(skmetrics.mean_squared_error(y_true, y_pred)))
        elif name == "mae":
            results[name] = float(skmetrics.mean_absolute_error(y_true, y_pred))
        elif name == "r2":
            results[name] = float(skmetrics.r2_score(y_true, y_pred))
        elif name == "auc" and model is not None and X_test is not None:
            if hasattr(model, "predict_proba"):
                try:
                    y_prob = model.predict_proba(X_test)
                    if y_prob.shape[1] == 2:
                        results[name] = float(
                            skmetrics.roc_auc_score(y_true, y_prob[:, 1])
                        )
                    else:
                        results[name] = float(
                            skmetrics.roc_auc_score(
                                y_true, y_prob, multi_class="ovr", average="weighted"
                            )
                        )
                except Exception:
                    logger.debug("AUC computation failed, skipping.")
        else:
            logger.warning("Unknown or unsupported metric: %s", name)
    return results

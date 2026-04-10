# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Public metrics module for kailash-ml.

Provides standalone metric functions that accept polars Series or numpy
arrays, plus a registry for programmatic metric lookup and computation.

Usage::

    from kailash_ml.metrics import accuracy, f1, mse, log_loss
    import polars as pl

    y_true = pl.Series([1, 0, 1, 1])
    y_pred = pl.Series([1, 0, 0, 1])

    print(accuracy(y_true, y_pred))   # 0.75
    print(f1(y_true, y_pred))         # weighted F1

    # Probability metrics
    y_prob = pl.Series([0.9, 0.1, 0.4, 0.8])
    print(log_loss(y_true, y_prob))

    # Registry-based computation
    from kailash_ml.metrics import compute_metrics
    results = compute_metrics(y_true, y_pred, ["accuracy", "f1"])
"""
from __future__ import annotations

from kailash_ml.metrics._registry import (
    METRIC_REGISTRY,
    accuracy,
    auc,
    average_precision,
    brier_score_loss,
    compute_metric,
    compute_metrics,
    f1,
    list_metrics,
    log_loss,
    mae,
    mse,
    precision,
    r2,
    recall,
    register_metric,
    rmse,
)

__all__ = [
    # Registry
    "METRIC_REGISTRY",
    "register_metric",
    "compute_metric",
    "compute_metrics",
    "list_metrics",
    # Classification
    "accuracy",
    "f1",
    "precision",
    "recall",
    "auc",
    # Regression
    "mse",
    "rmse",
    "mae",
    "r2",
    # Probability (TASK-ML-02)
    "log_loss",
    "brier_score_loss",
    "average_precision",
]

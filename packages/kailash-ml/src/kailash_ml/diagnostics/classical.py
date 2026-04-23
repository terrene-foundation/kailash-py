# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Classical-ML diagnostics for sklearn-compatible estimators.

Per ``specs/ml-diagnostics.md §6``, kailash-ml ships a classical-ML
diagnostic surface that operates on fitted sklearn models AND raw
``(X, y)`` data rather than on a DL training-loop. The adapters in
:mod:`kailash_ml.diagnostics.dl` remain the torch / Lightning path;
this module hosts the scikit-learn path.

Public surface (per spec §6):

    from kailash_ml.diagnostics import (
        diagnose_classifier,    # sklearn ClassifierMixin → ClassifierReport
        diagnose_regressor,     # sklearn RegressorMixin  → RegressorReport
    )

    report = diagnose_classifier(clf, X_test, y_test, tracker=run)
    report.metrics["accuracy"]          # float
    report.metrics["f1_macro"]          # float
    report.confusion_matrix             # polars.DataFrame, K×K (or None)
    report.severity["accuracy"]         # "HEALTHY" | "WARNING" | "CRITICAL"

The returned frozen dataclasses implement the ``kailash.diagnostics.
protocols.Diagnostic`` protocol via no-op ``__enter__`` / ``__exit__``
so callers can inspect ``report.metrics`` directly without entering a
``with`` block.

Tracker integration: when ``tracker is not None``, metrics are emitted
via ``tracker.log_metric(name, value, step=0)`` in a single batch.
Classical diagnostics are one-shot — there is no streaming step index.

This module has zero torch / transformers / vllm dependency. ``sklearn``
is a core dependency of kailash-ml so is always available.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Literal, Optional

import numpy as np

logger = logging.getLogger(__name__)

__all__ = [
    "ClassifierReport",
    "RegressorReport",
    "diagnose_classifier",
    "diagnose_regressor",
]


Severity = Literal["HEALTHY", "WARNING", "CRITICAL", "UNKNOWN"]


@dataclass(frozen=True)
class ClassifierReport:
    """Frozen one-shot diagnostic report for sklearn classifiers.

    Per ``specs/ml-diagnostics.md §6.1``. The dataclass form is
    friendlier than a context manager for a one-shot diagnosis:
    callers write ``report = diagnose_classifier(...)`` and access
    ``report.metrics["accuracy"]`` directly.
    """

    run_id: str
    model_class: str
    metrics: dict[str, Optional[float]]
    per_class: dict[str, dict[str, float]]
    confusion_matrix: Optional[list[list[int]]]
    class_balance: dict[str, float]
    severity: dict[str, Severity]
    reason: Optional[str] = None

    def __enter__(self) -> "ClassifierReport":
        """Protocol conformance — no-op."""
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Protocol conformance — no-op."""
        return None

    def report(self) -> dict[str, Any]:
        """Return a dict view of the report for Protocol conformance."""
        return {
            "run_id": self.run_id,
            "model_class": self.model_class,
            "metrics": dict(self.metrics),
            "per_class": {k: dict(v) for k, v in self.per_class.items()},
            "confusion_matrix": self.confusion_matrix,
            "class_balance": dict(self.class_balance),
            "severity": dict(self.severity),
            "reason": self.reason,
        }


@dataclass(frozen=True)
class RegressorReport:
    """Frozen one-shot diagnostic report for sklearn regressors.

    Per ``specs/ml-diagnostics.md §6.2``.
    """

    run_id: str
    model_class: str
    metrics: dict[str, Optional[float]]
    residuals_summary: dict[str, float]
    severity: dict[str, Severity]
    reason: Optional[str] = None

    def __enter__(self) -> "RegressorReport":
        """Protocol conformance — no-op."""
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Protocol conformance — no-op."""
        return None

    def report(self) -> dict[str, Any]:
        """Return a dict view of the report for Protocol conformance."""
        return {
            "run_id": self.run_id,
            "model_class": self.model_class,
            "metrics": dict(self.metrics),
            "residuals_summary": dict(self.residuals_summary),
            "severity": dict(self.severity),
            "reason": self.reason,
        }


def _as_array(value: Any) -> np.ndarray:
    """Convert polars/pandas/list/tuple to a 1- or 2-D numpy array.

    Accepts polars.DataFrame / polars.Series, numpy arrays, lists, and
    anything else that numpy can coerce. Polars support is best-effort
    — we only use ``to_numpy()`` when polars is the type.
    """
    try:
        import polars as pl  # noqa: PLC0415 — optional at helper-local scope
    except ImportError:  # pragma: no cover — polars is a core dep of kailash-ml
        pl = None  # type: ignore[assignment]
    if pl is not None and isinstance(value, (pl.DataFrame, pl.Series)):
        return value.to_numpy()
    return np.asarray(value)


def _emit_to_tracker(
    tracker: Any, metrics: dict[str, Optional[float]], run_id: str
) -> None:
    """Log finite metric values through ``tracker.log_metric`` at step 0.

    Silently skips ``None`` values and non-finite floats. Errors from
    the tracker are logged at WARN and otherwise swallowed — an
    observability write must not break the diagnostic return value.
    """
    if tracker is None:
        return
    log_metric = getattr(tracker, "log_metric", None)
    if log_metric is None:
        return
    for name, value in metrics.items():
        if value is None:
            continue
        try:
            float_value = float(value)
        except (TypeError, ValueError):
            continue
        if not np.isfinite(float_value):
            continue
        try:
            log_metric(name, float_value, step=0)
        except Exception as exc:  # noqa: BLE001 — tracker failures are non-fatal
            logger.warning(
                "classical_diagnose.tracker_log_failed",
                extra={
                    "classical_run_id": run_id,
                    "classical_metric": name,
                    "classical_error": str(exc),
                },
            )


def diagnose_classifier(
    model: Any,
    X: Any,
    y: Any,
    *,
    tracker: Optional[Any] = None,
    show: bool = True,  # noqa: ARG001 — accepted for spec-signature compat
    sensitive: bool = False,  # noqa: ARG001 — accepted for spec-signature compat
) -> ClassifierReport:
    """Run classifier diagnostics against a fitted sklearn estimator.

    Per ``specs/ml-diagnostics.md §6.1``. Computes accuracy, per-class
    precision/recall/F1, a K×K confusion matrix, and class balance.
    Severity thresholds:

    - ``accuracy = CRITICAL`` when accuracy < majority-class proportion
      (worse than guessing the majority).
    - ``class_balance = WARNING`` when worst/best class ratio < 0.1.

    When ``y`` contains only one unique label, returns a valid report
    with ``confusion_matrix=None`` and ``reason="single_class_in_split"``
    per spec §6.1 single-class edge case.

    Args:
        model: A fitted sklearn-compatible classifier (exposes
            ``.predict``; ``.predict_proba`` is optional).
        X: Feature matrix (polars DataFrame, numpy array, or anything
            the model's ``.predict`` accepts).
        y: Ground-truth labels (polars Series, numpy array, list).
        tracker: Optional run-like object with ``.log_metric(name,
            value, *, step)``. When provided every finite metric is
            logged at ``step=0``.
        show: Retained for spec-signature compatibility; this base
            implementation renders no figure.
        sensitive: Retained for spec-signature compatibility; feature
            names are not emitted by this implementation.

    Returns:
        A frozen :class:`ClassifierReport`.

    Raises:
        ValueError: when ``X`` has zero rows.
    """
    from sklearn.metrics import (  # noqa: PLC0415 — lazy for import cost
        accuracy_score,
        confusion_matrix as sk_confusion_matrix,
        f1_score,
        precision_recall_fscore_support,
        precision_score,
        recall_score,
    )

    run_id = str(uuid.uuid4())
    y_true = _as_array(y).ravel()
    if y_true.size == 0:
        raise ValueError("diagnose_classifier: y is empty")
    X_arr = _as_array(X)
    y_pred = np.asarray(model.predict(X_arr)).ravel()

    model_class = type(model).__name__
    labels_union = sorted(np.unique(np.concatenate([y_true, y_pred])).tolist())

    severity: dict[str, Severity] = {}
    reason: Optional[str] = None

    # Class-balance statistics — independent of single-class edge case.
    unique_true, counts_true = np.unique(y_true, return_counts=True)
    total = float(counts_true.sum())
    class_balance = {
        str(label): float(count) / total
        for label, count in zip(unique_true, counts_true)
    }
    if len(unique_true) >= 2:
        worst = float(counts_true.min())
        best = float(counts_true.max())
        severity["class_balance"] = (
            "WARNING" if best > 0 and (worst / best) < 0.1 else "HEALTHY"
        )
    else:
        severity["class_balance"] = "CRITICAL"

    # Single-class edge case per spec §6.1.
    if len(unique_true) < 2:
        accuracy = float(accuracy_score(y_true, y_pred))
        severity["accuracy"] = "UNKNOWN"
        severity["confusion"] = "UNKNOWN"
        metrics: dict[str, Optional[float]] = {
            "accuracy": accuracy,
            "f1_macro": None,
            "precision_macro": None,
            "recall_macro": None,
        }
        per_class: dict[str, dict[str, float]] = {}
        _emit_to_tracker(tracker, metrics, run_id)
        return ClassifierReport(
            run_id=run_id,
            model_class=model_class,
            metrics=metrics,
            per_class=per_class,
            confusion_matrix=None,
            class_balance=class_balance,
            severity=severity,
            reason="single_class_in_split",
        )

    accuracy = float(accuracy_score(y_true, y_pred))
    # Per spec §6.1 severity: accuracy CRITICAL when < majority-class proportion.
    majority_proportion = float(counts_true.max()) / total
    severity["accuracy"] = "CRITICAL" if accuracy < majority_proportion else "HEALTHY"
    severity["confusion"] = "HEALTHY"

    f1_macro = float(f1_score(y_true, y_pred, average="macro", zero_division=0))
    precision_macro = float(
        precision_score(y_true, y_pred, average="macro", zero_division=0)
    )
    recall_macro = float(recall_score(y_true, y_pred, average="macro", zero_division=0))
    metrics = {
        "accuracy": accuracy,
        "f1_macro": f1_macro,
        "precision_macro": precision_macro,
        "recall_macro": recall_macro,
    }

    per_class = {}
    prec, rec, f1, sup = precision_recall_fscore_support(
        y_true, y_pred, labels=labels_union, zero_division=0
    )
    for label, p, r, f, s in zip(labels_union, prec, rec, f1, sup):
        per_class[str(label)] = {
            "precision": float(p),
            "recall": float(r),
            "f1": float(f),
            "support": int(s),
        }

    cm = sk_confusion_matrix(y_true, y_pred, labels=labels_union)
    confusion_matrix = cm.astype(int).tolist()

    _emit_to_tracker(tracker, metrics, run_id)
    return ClassifierReport(
        run_id=run_id,
        model_class=model_class,
        metrics=metrics,
        per_class=per_class,
        confusion_matrix=confusion_matrix,
        class_balance=class_balance,
        severity=severity,
        reason=reason,
    )


def diagnose_regressor(
    model: Any,
    X: Any,
    y: Any,
    *,
    tracker: Optional[Any] = None,
    show: bool = True,  # noqa: ARG001 — spec-signature compat
    sensitive: bool = False,  # noqa: ARG001 — spec-signature compat
) -> RegressorReport:
    """Run regressor diagnostics against a fitted sklearn estimator.

    Per ``specs/ml-diagnostics.md §6.2``. Computes MAE, MSE, RMSE, R²,
    explained variance, and residual summary statistics. Severity
    thresholds:

    - ``fit_quality = CRITICAL`` when R² < -0.5 (substantially worse
      than predicting the mean).
    - ``fit_quality = WARNING`` when R² in [-0.5, 0.3].
    - ``fit_quality = HEALTHY`` otherwise.

    Args:
        model: A fitted sklearn-compatible regressor (exposes ``.predict``).
        X: Feature matrix.
        y: Ground-truth continuous labels.
        tracker: Optional tracker with ``.log_metric``.
        show: Retained for spec-signature compat.
        sensitive: Retained for spec-signature compat.

    Returns:
        A frozen :class:`RegressorReport`.

    Raises:
        ValueError: when ``X`` has zero rows.
    """
    from sklearn.metrics import (  # noqa: PLC0415 — lazy for import cost
        explained_variance_score,
        mean_absolute_error,
        mean_squared_error,
        r2_score,
    )

    run_id = str(uuid.uuid4())
    y_true = _as_array(y).ravel().astype(float)
    if y_true.size == 0:
        raise ValueError("diagnose_regressor: y is empty")
    X_arr = _as_array(X)
    y_pred = np.asarray(model.predict(X_arr)).ravel().astype(float)

    model_class = type(model).__name__

    mae = float(mean_absolute_error(y_true, y_pred))
    mse = float(mean_squared_error(y_true, y_pred))
    rmse = float(np.sqrt(mse))
    r2 = float(r2_score(y_true, y_pred))
    exp_var = float(explained_variance_score(y_true, y_pred))

    residuals = y_true - y_pred
    residuals_summary = {
        "mean": float(residuals.mean()) if residuals.size else 0.0,
        "std": float(residuals.std()) if residuals.size else 0.0,
        "min": float(residuals.min()) if residuals.size else 0.0,
        "max": float(residuals.max()) if residuals.size else 0.0,
        "count": float(residuals.size),
    }

    if r2 < -0.5:
        fit_severity: Severity = "CRITICAL"
    elif r2 < 0.3:
        fit_severity = "WARNING"
    else:
        fit_severity = "HEALTHY"

    metrics: dict[str, Optional[float]] = {
        "mae": mae,
        "mse": mse,
        "rmse": rmse,
        "r2": r2,
        "explained_variance": exp_var,
    }
    severity: dict[str, Severity] = {"fit_quality": fit_severity}

    _emit_to_tracker(tracker, metrics, run_id)
    return RegressorReport(
        run_id=run_id,
        model_class=model_class,
        metrics=metrics,
        residuals_summary=residuals_summary,
        severity=severity,
        reason=None,
    )

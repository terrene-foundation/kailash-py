# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""EnsembleEngine -- ensemble model creation via blending, stacking, bagging, boosting.

PyCaret equivalents: ensemble_model(), blend_models(), stack_models().
All data handling uses polars internally; conversion to numpy/sklearn
happens at the sklearn boundary via ``interop.py``.
"""
from __future__ import annotations

import importlib
import logging
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import polars as pl

from kailash_ml.interop import to_sklearn_input

logger = logging.getLogger(__name__)

__all__ = [
    "EnsembleEngine",
    "BlendResult",
    "StackResult",
    "BagResult",
    "BoostResult",
]


# ---------------------------------------------------------------------------
# Security: model class allowlist (shared definition)
# ---------------------------------------------------------------------------

from kailash_ml.engines._shared import validate_model_class as _validate_model_class


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BlendResult:
    """Result of blending multiple models."""

    ensemble_model: Any
    metrics: dict[str, float]
    weights: list[float]
    method: str  # "soft" or "hard"
    n_models: int
    component_contributions: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "ensemble_model": None,
            "metrics": dict(self.metrics),
            "weights": list(self.weights),
            "method": self.method,
            "n_models": self.n_models,
            "component_contributions": list(self.component_contributions),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BlendResult:
        return cls(
            ensemble_model=data.get("ensemble_model"),
            metrics=data["metrics"],
            weights=data["weights"],
            method=data["method"],
            n_models=data["n_models"],
            component_contributions=data.get("component_contributions", []),
        )


@dataclass(frozen=True)
class StackResult:
    """Result of stacking models with a meta-learner."""

    ensemble_model: Any
    metrics: dict[str, float]
    meta_model_class: str
    n_base_models: int
    fold: int
    component_contributions: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "ensemble_model": None,
            "metrics": dict(self.metrics),
            "meta_model_class": self.meta_model_class,
            "n_base_models": self.n_base_models,
            "fold": self.fold,
            "component_contributions": list(self.component_contributions),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StackResult:
        return cls(
            ensemble_model=data.get("ensemble_model"),
            metrics=data["metrics"],
            meta_model_class=data["meta_model_class"],
            n_base_models=data["n_base_models"],
            fold=data["fold"],
            component_contributions=data.get("component_contributions", []),
        )


@dataclass(frozen=True)
class BagResult:
    """Result of bagging a single model."""

    ensemble_model: Any
    metrics: dict[str, float]
    n_estimators: int
    max_samples: float
    max_features: float
    base_model_class: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "ensemble_model": None,
            "metrics": dict(self.metrics),
            "n_estimators": self.n_estimators,
            "max_samples": self.max_samples,
            "max_features": self.max_features,
            "base_model_class": self.base_model_class,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BagResult:
        return cls(
            ensemble_model=data.get("ensemble_model"),
            metrics=data["metrics"],
            n_estimators=data["n_estimators"],
            max_samples=data["max_samples"],
            max_features=data["max_features"],
            base_model_class=data["base_model_class"],
        )


@dataclass(frozen=True)
class BoostResult:
    """Result of boosting a single model."""

    ensemble_model: Any
    metrics: dict[str, float]
    n_estimators: int
    learning_rate: float
    base_model_class: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "ensemble_model": None,
            "metrics": dict(self.metrics),
            "n_estimators": self.n_estimators,
            "learning_rate": self.learning_rate,
            "base_model_class": self.base_model_class,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BoostResult:
        return cls(
            ensemble_model=data.get("ensemble_model"),
            metrics=data["metrics"],
            n_estimators=data["n_estimators"],
            learning_rate=data["learning_rate"],
            base_model_class=data["base_model_class"],
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _detect_task_type(y: np.ndarray) -> str:
    """Detect whether the target is classification or regression."""
    n_unique = len(np.unique(y[~np.isnan(y)]))
    if n_unique <= 20:
        return "classification"
    return "regression"


def _compute_metrics(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    task_type: str,
    model: Any = None,
    X_test: np.ndarray | None = None,
) -> dict[str, float]:
    """Compute standard metrics for classification or regression.

    Delegates to the shared metric computation, selecting metric names
    based on ``task_type``.
    """
    from kailash_ml.engines._shared import (
        _CLASSIFICATION_METRICS,
        _REGRESSION_METRICS,
        compute_metrics_by_name,
    )

    if task_type == "classification":
        metric_names = list(_CLASSIFICATION_METRICS)
    else:
        metric_names = list(_REGRESSION_METRICS)
    return compute_metrics_by_name(y_true, y_pred, metric_names, model, X_test)


def _split_data(
    data: pl.DataFrame,
    feature_cols: list[str],
    target: str,
    test_size: float = 0.2,
    seed: int = 42,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Split data into train/test numpy arrays."""
    X, y, _ = to_sklearn_input(data, feature_columns=feature_cols, target_column=target)
    if y is None:
        raise ValueError(f"Target column '{target}' not found in data.")

    n = len(y)
    split_idx = int(n * (1 - test_size))
    rng = np.random.RandomState(seed)
    indices = np.arange(n)
    rng.shuffle(indices)

    train_idx = indices[:split_idx]
    test_idx = indices[split_idx:]
    return X[train_idx], X[test_idx], y[train_idx], y[test_idx]


def _get_model_name(model: Any) -> str:
    """Get the fully qualified class name of a model."""
    cls = type(model)
    return f"{cls.__module__}.{cls.__qualname__}"


# ---------------------------------------------------------------------------
# EnsembleEngine
# ---------------------------------------------------------------------------


class EnsembleEngine:
    """[P1: Production with Caveats] Ensemble model creation -- blending,
    stacking, bagging, boosting.

    PyCaret equivalents: ``blend_models()``, ``stack_models()``,
    ``ensemble_model(method='Bagging')``, ``ensemble_model(method='Boosting')``.

    All methods accept polars DataFrames and convert at the sklearn boundary.
    Task type (classification vs regression) is auto-detected from the target
    column.
    """

    def blend(
        self,
        models: list[Any],
        data: pl.DataFrame,
        target: str,
        *,
        weights: list[float] | None = None,
        method: str = "soft",
        test_size: float = 0.2,
        seed: int = 42,
    ) -> BlendResult:
        """Blend multiple models via weighted averaging (soft) or voting (hard).

        PyCaret equivalent: ``blend_models()``.

        Parameters
        ----------
        models:
            List of fitted sklearn-compatible estimators.
        data:
            Polars DataFrame with features and target.
        target:
            Name of the target column.
        weights:
            Optional list of model weights (must sum to > 0). Defaults to
            equal weighting.
        method:
            ``"soft"`` uses predicted probabilities (classification) or
            averaged predictions (regression). ``"hard"`` uses majority
            voting (classification only).
        test_size:
            Fraction of data held out for evaluation.
        seed:
            Random seed for reproducibility.
        """
        from sklearn.ensemble import VotingClassifier, VotingRegressor

        if not models:
            raise ValueError("models list must not be empty.")
        if method not in ("soft", "hard"):
            raise ValueError(f"method must be 'soft' or 'hard', got '{method}'.")

        feature_cols = [c for c in data.columns if c != target]
        X_train, X_test, y_train, y_test = _split_data(
            data, feature_cols, target, test_size, seed
        )
        task_type = _detect_task_type(y_train)

        # Validate weights
        if weights is not None:
            if len(weights) != len(models):
                raise ValueError(
                    f"weights length ({len(weights)}) must match models "
                    f"length ({len(models)})."
                )
        else:
            weights = [1.0] * len(models)

        estimators = [(f"model_{i}", model) for i, model in enumerate(models)]

        if task_type == "classification":
            voting = "soft" if method == "soft" else "hard"
            # For soft voting, all models must support predict_proba
            if voting == "soft":
                for i, model in enumerate(models):
                    if not hasattr(model, "predict_proba"):
                        raise ValueError(
                            f"Model {i} ({type(model).__name__}) does not support "
                            f"predict_proba, required for soft voting. "
                            f"Use method='hard' instead."
                        )
            ensemble = VotingClassifier(
                estimators=estimators, voting=voting, weights=weights
            )
        else:
            if method == "hard":
                logger.warning(
                    "Hard voting not supported for regression, using soft (averaging)."
                )
            ensemble = VotingRegressor(estimators=estimators, weights=weights)

        # Fit the ensemble (sklearn refits estimators by default; we pass
        # pre-fitted models so we set the fitted attributes directly)
        ensemble.fit(X_train, y_train)

        y_pred = ensemble.predict(X_test)
        metrics = _compute_metrics(y_test, y_pred, task_type, ensemble, X_test)

        # Component contributions
        contributions = []
        for i, model in enumerate(models):
            model_pred = model.predict(X_test)
            model_metrics = _compute_metrics(
                y_test, model_pred, task_type, model, X_test
            )
            contributions.append(
                {
                    "model_index": i,
                    "model_class": _get_model_name(model),
                    "weight": weights[i],
                    "metrics": model_metrics,
                }
            )

        return BlendResult(
            ensemble_model=ensemble,
            metrics=metrics,
            weights=weights,
            method=method,
            n_models=len(models),
            component_contributions=contributions,
        )

    def stack(
        self,
        models: list[Any],
        data: pl.DataFrame,
        target: str,
        *,
        meta_model_class: str = "sklearn.linear_model.LogisticRegression",
        fold: int = 5,
        test_size: float = 0.2,
        seed: int = 42,
    ) -> StackResult:
        """Stack models with a meta-learner trained on CV predictions.

        PyCaret equivalent: ``stack_models()``.

        Parameters
        ----------
        models:
            List of fitted sklearn-compatible base estimators.
        data:
            Polars DataFrame with features and target.
        target:
            Name of the target column.
        meta_model_class:
            Fully qualified class name for the meta-learner. Must be in the
            allowed model prefixes.
        fold:
            Number of cross-validation folds for generating meta-features.
        test_size:
            Fraction of data held out for evaluation.
        seed:
            Random seed for reproducibility.
        """
        from sklearn.ensemble import StackingClassifier, StackingRegressor

        if not models:
            raise ValueError("models list must not be empty.")
        _validate_model_class(meta_model_class)

        feature_cols = [c for c in data.columns if c != target]
        X_train, X_test, y_train, y_test = _split_data(
            data, feature_cols, target, test_size, seed
        )
        task_type = _detect_task_type(y_train)

        # Instantiate meta-model
        parts = meta_model_class.rsplit(".", 1)
        if len(parts) != 2:
            raise ValueError(
                f"meta_model_class must be 'module.ClassName', "
                f"got '{meta_model_class}'"
            )
        module = importlib.import_module(parts[0])
        meta_cls = getattr(module, parts[1])
        meta_model = meta_cls()

        estimators = [(f"model_{i}", model) for i, model in enumerate(models)]

        if task_type == "classification":
            ensemble = StackingClassifier(
                estimators=estimators,
                final_estimator=meta_model,
                cv=fold,
            )
        else:
            ensemble = StackingRegressor(
                estimators=estimators,
                final_estimator=meta_model,
                cv=fold,
            )

        ensemble.fit(X_train, y_train)

        y_pred = ensemble.predict(X_test)
        metrics = _compute_metrics(y_test, y_pred, task_type, ensemble, X_test)

        # Component contributions
        contributions = []
        for i, model in enumerate(models):
            model_pred = model.predict(X_test)
            model_metrics = _compute_metrics(
                y_test, model_pred, task_type, model, X_test
            )
            contributions.append(
                {
                    "model_index": i,
                    "model_class": _get_model_name(model),
                    "metrics": model_metrics,
                }
            )

        return StackResult(
            ensemble_model=ensemble,
            metrics=metrics,
            meta_model_class=meta_model_class,
            n_base_models=len(models),
            fold=fold,
            component_contributions=contributions,
        )

    def bag(
        self,
        model: Any,
        data: pl.DataFrame,
        target: str,
        *,
        n_estimators: int = 10,
        max_samples: float = 1.0,
        max_features: float = 1.0,
        test_size: float = 0.2,
        seed: int = 42,
    ) -> BagResult:
        """Bootstrap aggregating (bagging).

        PyCaret equivalent: ``ensemble_model(method='Bagging')``.

        Parameters
        ----------
        model:
            A fitted sklearn-compatible estimator to use as the base.
        data:
            Polars DataFrame with features and target.
        target:
            Name of the target column.
        n_estimators:
            Number of base estimators in the ensemble.
        max_samples:
            Fraction of samples drawn per estimator (with replacement).
        max_features:
            Fraction of features drawn per estimator.
        test_size:
            Fraction of data held out for evaluation.
        seed:
            Random seed for reproducibility.
        """
        from sklearn.ensemble import BaggingClassifier, BaggingRegressor

        feature_cols = [c for c in data.columns if c != target]
        X_train, X_test, y_train, y_test = _split_data(
            data, feature_cols, target, test_size, seed
        )
        task_type = _detect_task_type(y_train)

        if task_type == "classification":
            ensemble = BaggingClassifier(
                estimator=model,
                n_estimators=n_estimators,
                max_samples=max_samples,
                max_features=max_features,
                random_state=seed,
            )
        else:
            ensemble = BaggingRegressor(
                estimator=model,
                n_estimators=n_estimators,
                max_samples=max_samples,
                max_features=max_features,
                random_state=seed,
            )

        ensemble.fit(X_train, y_train)

        y_pred = ensemble.predict(X_test)
        metrics = _compute_metrics(y_test, y_pred, task_type, ensemble, X_test)

        return BagResult(
            ensemble_model=ensemble,
            metrics=metrics,
            n_estimators=n_estimators,
            max_samples=max_samples,
            max_features=max_features,
            base_model_class=_get_model_name(model),
        )

    def boost(
        self,
        model: Any,
        data: pl.DataFrame,
        target: str,
        *,
        n_estimators: int = 100,
        learning_rate: float = 0.1,
        test_size: float = 0.2,
        seed: int = 42,
    ) -> BoostResult:
        """Boosting via AdaBoost.

        PyCaret equivalent: ``ensemble_model(method='Boosting')``.

        Parameters
        ----------
        model:
            A fitted sklearn-compatible estimator to use as the base.
            Must support ``sample_weight`` in ``fit()`` for AdaBoost.
        data:
            Polars DataFrame with features and target.
        target:
            Name of the target column.
        n_estimators:
            Maximum number of estimators at which boosting is terminated.
        learning_rate:
            Weight applied to each estimator's contribution.
        test_size:
            Fraction of data held out for evaluation.
        seed:
            Random seed for reproducibility.
        """
        from sklearn.ensemble import AdaBoostClassifier, AdaBoostRegressor

        feature_cols = [c for c in data.columns if c != target]
        X_train, X_test, y_train, y_test = _split_data(
            data, feature_cols, target, test_size, seed
        )
        task_type = _detect_task_type(y_train)

        if task_type == "classification":
            ensemble = AdaBoostClassifier(
                estimator=model,
                n_estimators=n_estimators,
                learning_rate=learning_rate,
                random_state=seed,
            )
        else:
            ensemble = AdaBoostRegressor(
                estimator=model,
                n_estimators=n_estimators,
                learning_rate=learning_rate,
                random_state=seed,
            )

        ensemble.fit(X_train, y_train)

        y_pred = ensemble.predict(X_test)
        metrics = _compute_metrics(y_test, y_pred, task_type, ensemble, X_test)

        return BoostResult(
            ensemble_model=ensemble,
            metrics=metrics,
            n_estimators=n_estimators,
            learning_rate=learning_rate,
            base_model_class=_get_model_name(model),
        )

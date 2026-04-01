# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""TrainingPipeline engine -- sklearn + LightGBM training orchestration.

Handles the full lifecycle: features -> train -> evaluate -> register.
Supports sklearn and LightGBM in v1. Interop conversion happens at
the sklearn/LightGBM boundary ONLY (no pandas/numpy inside pipeline logic).
"""
from __future__ import annotations

import importlib
import logging
import pickle
import time
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import polars as pl
from kailash_ml_protocols import (
    AgentInfusionProtocol,
    FeatureField,
    FeatureSchema,
    MetricSpec,
    ModelSignature,
)

from kailash_ml.engines.model_registry import ModelRegistry, ModelVersion
from kailash_ml.interop import to_lgb_dataset, to_sklearn_input

logger = logging.getLogger(__name__)

__all__ = [
    "TrainingPipeline",
    "ModelSpec",
    "EvalSpec",
    "TrainingResult",
]

# ---------------------------------------------------------------------------
# Security: model class allowlist (C1)
# ---------------------------------------------------------------------------

_ALLOWED_MODEL_PREFIXES = frozenset(
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


def _validate_model_class(model_class: str) -> None:
    """Validate model_class against allowlist to prevent arbitrary code execution."""
    if not any(model_class.startswith(prefix) for prefix in _ALLOWED_MODEL_PREFIXES):
        raise ValueError(
            f"Model class '{model_class}' not in allowed prefixes: {sorted(_ALLOWED_MODEL_PREFIXES)}. "
            f"For custom models, use a prefix from the allowlist."
        )


# ---------------------------------------------------------------------------
# Core types
# ---------------------------------------------------------------------------


@dataclass
class ModelSpec:
    """What to train."""

    model_class: str  # e.g. "sklearn.ensemble.RandomForestClassifier"
    hyperparameters: dict[str, Any] = field(default_factory=dict)
    framework: str = "sklearn"  # "sklearn" | "lightgbm"

    def instantiate(self) -> Any:
        """Create model instance from spec."""
        parts = self.model_class.rsplit(".", 1)
        if len(parts) != 2:
            raise ValueError(
                f"model_class must be 'module.ClassName', got '{self.model_class}'"
            )
        _validate_model_class(self.model_class)
        module = importlib.import_module(parts[0])
        cls = getattr(module, parts[1])
        return cls(**self.hyperparameters)


@dataclass
class EvalSpec:
    """How to evaluate."""

    metrics: list[str] = field(default_factory=lambda: ["accuracy"])
    split_strategy: str = (
        "holdout"  # "holdout", "kfold", "stratified_kfold", "walk_forward"
    )
    n_splits: int = 5
    test_size: float = 0.2
    min_threshold: dict[str, float] = field(default_factory=dict)


@dataclass
class TrainingResult:
    """Result of a training run."""

    model_version: ModelVersion | None  # None if threshold not met
    metrics: dict[str, float]
    training_time_seconds: float
    data_shape: tuple[int, int]
    registered: bool  # True if model was registered
    threshold_met: bool


# ---------------------------------------------------------------------------
# Metric evaluation helpers
# ---------------------------------------------------------------------------


def _compute_metrics(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    metric_names: list[str],
    model: Any = None,
    X_test: np.ndarray | None = None,
) -> dict[str, float]:
    """Compute requested metrics. Supports common sklearn metrics."""
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
                y_prob = model.predict_proba(X_test)
                if y_prob.shape[1] == 2:
                    results[name] = float(skmetrics.roc_auc_score(y_true, y_prob[:, 1]))
                else:
                    results[name] = float(
                        skmetrics.roc_auc_score(
                            y_true, y_prob, multi_class="ovr", average="weighted"
                        )
                    )
            else:
                results[name] = 0.0
        else:
            logger.warning("Unknown or unsupported metric: %s", name)
    return results


# ---------------------------------------------------------------------------
# TrainingPipeline
# ---------------------------------------------------------------------------


class TrainingPipeline:
    """[P0: Production] Training pipeline for automated model training.

    Parameters
    ----------
    feature_store:
        FeatureStore for data retrieval (used in retrain).
    registry:
        ModelRegistry for saving trained models.
    """

    def __init__(
        self,
        feature_store: Any,  # FeatureStore (avoid circular import at type level)
        registry: ModelRegistry,
    ) -> None:
        self._feature_store = feature_store
        self._registry = registry

    # ------------------------------------------------------------------
    # train
    # ------------------------------------------------------------------

    async def train(
        self,
        data: pl.DataFrame,
        schema: FeatureSchema,
        model_spec: ModelSpec,
        eval_spec: EvalSpec,
        experiment_name: str,
        *,
        agent: AgentInfusionProtocol | None = None,
    ) -> TrainingResult:
        """Full training pipeline.

        1. Validate data against schema
        2. Split data per eval_spec
        3. Convert via interop at boundary
        4. Fit model
        5. Evaluate
        6. If threshold met, register at STAGING
        """
        # Validate
        self._validate_data(data, schema)

        feature_cols = [f.name for f in schema.features]
        target_col = self._detect_target(data, schema)

        # Optional agent model suggestion
        if agent is not None:
            data_profile = self._compute_data_profile(data)
            try:
                await agent.suggest_model(data_profile, "auto")
            except Exception:
                logger.debug("Agent model suggestion failed, continuing with spec.")

        # Split
        train_data, test_data = self._split(data, eval_spec)

        # Train
        start = time.perf_counter()

        if model_spec.framework == "lightgbm":
            model = self._train_lightgbm(
                train_data, feature_cols, target_col, model_spec
            )
        else:
            model = self._train_sklearn(
                train_data, feature_cols, target_col, model_spec
            )

        training_time = time.perf_counter() - start

        # Evaluate
        metrics = self._evaluate(
            model, test_data, feature_cols, target_col, eval_spec, model_spec.framework
        )

        # Threshold check
        threshold_met = all(
            metrics.get(m, 0) >= t for m, t in eval_spec.min_threshold.items()
        )

        # Register if threshold met
        model_version: ModelVersion | None = None
        if threshold_met:
            signature = self._build_signature(schema, model_spec)
            metric_specs = [MetricSpec(k, v) for k, v in metrics.items()]
            artifact_bytes = pickle.dumps(model)
            model_version = await self._registry.register_model(
                experiment_name,
                artifact_bytes,
                metrics=metric_specs,
                signature=signature,
            )

        # Optional agent interpretation
        if agent is not None and model_version is not None:
            try:
                await agent.interpret_results(
                    {"metrics": metrics, "model_spec": model_spec.__dict__}
                )
            except Exception:
                logger.debug("Agent result interpretation failed.")

        return TrainingResult(
            model_version=model_version,
            metrics=metrics,
            training_time_seconds=training_time,
            data_shape=(data.height, data.width),
            registered=model_version is not None,
            threshold_met=threshold_met,
        )

    # ------------------------------------------------------------------
    # evaluate (standalone)
    # ------------------------------------------------------------------

    async def evaluate(
        self,
        model_name: str,
        version: int,
        data: pl.DataFrame,
        schema: FeatureSchema,
        eval_spec: EvalSpec,
    ) -> dict[str, float]:
        """Evaluate a registered model on new data (shadow mode).

        Returns metric dict.
        """
        mv = await self._registry.get_model(model_name, version)
        artifact_bytes = await self._registry.load_artifact(model_name, version)
        # SECURITY: pickle deserialization executes arbitrary code.
        # Only load artifacts from TRUSTED sources (models you trained yourself).
        # Do NOT load artifacts from untrusted users or external sources.
        model = pickle.loads(artifact_bytes)

        feature_cols = [f.name for f in schema.features]
        target_col = self._detect_target(data, schema)

        framework = "lightgbm" if "lightgbm" in type(model).__module__ else "sklearn"
        return self._evaluate(
            model, data, feature_cols, target_col, eval_spec, framework
        )

    # ------------------------------------------------------------------
    # retrain
    # ------------------------------------------------------------------

    async def retrain(
        self,
        model_name: str,
        schema: FeatureSchema,
        model_spec: ModelSpec,
        eval_spec: EvalSpec,
        data: pl.DataFrame,
    ) -> TrainingResult:
        """Retrain using new data, register as next version of existing model."""
        return await self.train(data, schema, model_spec, eval_spec, model_name)

    # ------------------------------------------------------------------
    # Private: training
    # ------------------------------------------------------------------

    def _train_sklearn(
        self,
        train_data: pl.DataFrame,
        feature_cols: list[str],
        target_col: str,
        model_spec: ModelSpec,
    ) -> Any:
        """Train an sklearn model."""
        X_train, y_train, _col_info = to_sklearn_input(
            train_data, feature_columns=feature_cols, target_column=target_col
        )
        model = model_spec.instantiate()
        model.fit(X_train, y_train)
        return model

    def _train_lightgbm(
        self,
        train_data: pl.DataFrame,
        feature_cols: list[str],
        target_col: str,
        model_spec: ModelSpec,
    ) -> Any:
        """Train a LightGBM model."""
        try:
            import lightgbm as lgb
        except ImportError as exc:
            raise ImportError(
                "lightgbm is required for LightGBM training. "
                "Install it with: pip install lightgbm"
            ) from exc

        # Use the instantiate path for LightGBM sklearn API
        model = model_spec.instantiate()
        X_train, y_train, _col_info = to_sklearn_input(
            train_data, feature_columns=feature_cols, target_column=target_col
        )
        model.fit(X_train, y_train)
        return model

    # ------------------------------------------------------------------
    # Private: evaluation
    # ------------------------------------------------------------------

    def _evaluate(
        self,
        model: Any,
        test_data: pl.DataFrame,
        feature_cols: list[str],
        target_col: str,
        eval_spec: EvalSpec,
        framework: str,
    ) -> dict[str, float]:
        """Evaluate model on test data."""
        X_test, y_test, _ = to_sklearn_input(
            test_data, feature_columns=feature_cols, target_column=target_col
        )
        if y_test is None:
            return {}

        y_pred = model.predict(X_test)
        return _compute_metrics(y_test, y_pred, eval_spec.metrics, model, X_test)

    # ------------------------------------------------------------------
    # Private: splitting
    # ------------------------------------------------------------------

    def _split(
        self, data: pl.DataFrame, eval_spec: EvalSpec
    ) -> tuple[pl.DataFrame, pl.DataFrame]:
        """Split data according to eval_spec strategy."""
        if eval_spec.split_strategy == "holdout":
            return self._holdout_split(data, eval_spec.test_size)
        elif eval_spec.split_strategy == "kfold":
            return self._kfold_first_fold(data, eval_spec.n_splits)
        elif eval_spec.split_strategy == "stratified_kfold":
            return self._stratified_kfold_first_fold(data, eval_spec.n_splits)
        elif eval_spec.split_strategy == "walk_forward":
            return self._walk_forward_split(data, eval_spec.test_size)
        else:
            raise ValueError(f"Unknown split strategy: {eval_spec.split_strategy}")

    def _holdout_split(
        self, data: pl.DataFrame, test_size: float
    ) -> tuple[pl.DataFrame, pl.DataFrame]:
        n = data.height
        split_idx = int(n * (1 - test_size))
        # Shuffle deterministically
        indices = np.arange(n)
        rng = np.random.RandomState(42)
        rng.shuffle(indices)
        train_idx = indices[:split_idx].tolist()
        test_idx = indices[split_idx:].tolist()
        return data[train_idx], data[test_idx]

    def _kfold_first_fold(
        self, data: pl.DataFrame, n_splits: int
    ) -> tuple[pl.DataFrame, pl.DataFrame]:
        fold_size = data.height // n_splits
        test_data = data[:fold_size]
        train_data = data[fold_size:]
        return train_data, test_data

    def _stratified_kfold_first_fold(
        self, data: pl.DataFrame, n_splits: int
    ) -> tuple[pl.DataFrame, pl.DataFrame]:
        # Fallback to regular kfold for simplicity in v1
        return self._kfold_first_fold(data, n_splits)

    def _walk_forward_split(
        self, data: pl.DataFrame, test_size: float
    ) -> tuple[pl.DataFrame, pl.DataFrame]:
        """Time-series aware split: no shuffle, tail is test."""
        n = data.height
        split_idx = int(n * (1 - test_size))
        return data[:split_idx], data[split_idx:]

    # ------------------------------------------------------------------
    # Private: validation & helpers
    # ------------------------------------------------------------------

    def _validate_data(self, data: pl.DataFrame, schema: FeatureSchema) -> None:
        """Validate DataFrame has required feature columns."""
        required_cols = {f.name for f in schema.features}
        available_cols = set(data.columns)
        missing = required_cols - available_cols
        if missing:
            raise ValueError(
                f"Data is missing columns for schema '{schema.name}': {sorted(missing)}"
            )

    def _detect_target(self, data: pl.DataFrame, schema: FeatureSchema) -> str:
        """Detect the target column (any column not in features or entity_id)."""
        feature_names = {f.name for f in schema.features}
        feature_names.add(schema.entity_id_column)
        if schema.timestamp_column:
            feature_names.add(schema.timestamp_column)
        for col in data.columns:
            if col not in feature_names:
                return col
        raise ValueError(
            f"Cannot detect target column. "
            f"Data columns: {data.columns}, schema features: {list(feature_names)}"
        )

    def _build_signature(
        self, schema: FeatureSchema, model_spec: ModelSpec
    ) -> ModelSignature:
        """Build a ModelSignature from the schema and spec."""
        # Determine model type from class name or spec
        model_type = "classifier"
        cls_lower = model_spec.model_class.lower()
        if "regress" in cls_lower:
            model_type = "regressor"
        elif "rank" in cls_lower:
            model_type = "ranker"

        return ModelSignature(
            input_schema=schema,
            output_columns=["prediction"],
            output_dtypes=["float64"],
            model_type=model_type,
        )

    def _compute_data_profile(self, data: pl.DataFrame) -> dict[str, Any]:
        """Compute a quick data profile for agent suggestion."""
        return {
            "shape": (data.height, data.width),
            "columns": data.columns,
            "dtypes": [str(dt) for dt in data.dtypes],
            "null_counts": {col: data[col].null_count() for col in data.columns},
        }
